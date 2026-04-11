# Parametrizer Agent - Utility Interconnection Agent
# Maps structured outputs from a source agent's log to a target agent's config.yaml
# Reads interconnection-scheme.csv to know which output fields map to which config params
# If multiple structured output elements exist, iterates: fill config -> start target -> wait -> repeat

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import csv
import copy
import codecs
import re
import shutil
import time
import yaml
import logging
import subprocess

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Use directory name for log file
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

# Also log to console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)


# ========================================
# UNIFIED STRUCTURED OUTPUT PARSER
# ========================================
#
# Every section-generating agent writes its structured output to its log
# file using one single, universal format:
#
#   INI_SECTION_<AGENT_TYPE><<<
#   field1: value1
#   field2: value2
#
#   multi-line body content (becomes 'response_body')
#   >>>END_SECTION_<AGENT_TYPE>
#
# Format rules
# ------------
# 1. <AGENT_TYPE> is the UPPERCASE base name of the source agent
#    (e.g. APIRER, CRAWLER, KYBER_KEYGEN, FILE_INTERPRETER).
# 2. Lines before the FIRST blank line are key-value metadata.
#    Each line is split on the first ': ' (colon-space) delimiter.
# 3. Everything after the first blank line is stored under the key
#    'response_body'.
# 4. If there is NO blank line the entire content is key-value fields
#    (no response_body is produced).
# 5. Sections MUST be emitted as a SINGLE atomic logging.info() call
#    so that concurrent log writes cannot corrupt the block.

# All supported section-generating agent base names.
SECTION_AGENT_TYPES = [
    'apirer', 'gitter', 'kuberneter',
    'crawler', 'summarizer', 'prompter', 'flowcreator',
    'file_interpreter', 'image_interpreter', 'file_extractor',
    'kyber_keygen', 'kyber_cipher', 'kyber_decipher',
    'gatewayer', 'gateway_relayer',
    'googler',
]


def _parse_section_content(raw_content):
    """Parse a unified section block into a fields dictionary.

    KV header lines (before the first blank line) are split on the first
    ``': '`` into key / value pairs.  Content after the first blank line
    is stored under the key ``'response_body'``.
    """
    parts = raw_content.split('\n\n', 1)
    header_text = parts[0]
    body_text = parts[1].strip() if len(parts) > 1 else ''

    fields = {}
    for line in header_text.split('\n'):
        line = line.strip()
        if not line:
            continue
        sep_idx = line.find(': ')
        if sep_idx != -1:
            fields[line[:sep_idx]] = line[sep_idx + 2:]

    if body_text:
        fields['response_body'] = body_text

    return fields


def _section_regex(agent_type):
    """Return the compiled regex that matches one section for *agent_type*."""
    tag = re.escape(agent_type.upper())
    return re.compile(
        r'INI_SECTION_' + tag + r'<<<\s*\n(?P<content>.*?)\n\s*>>>END_SECTION_' + tag,
        re.DOTALL,
    )


def parse_unified_output(log_text, agent_type):
    """Parse ALL section blocks for *agent_type* from *log_text*."""
    blocks = []
    for match in _section_regex(agent_type).finditer(log_text):
        blocks.append(_parse_section_content(match.group('content')))
    return blocks


def parse_next_unified_output(log_text, agent_type):
    """Parse the first unread section block for *agent_type*.

    Returns ``(fields_dict, end_offset)`` or ``None``.
    """
    match = _section_regex(agent_type).search(log_text)
    if not match:
        return None
    return (_parse_section_content(match.group('content')), match.end())


# ---------------------------------------------------------------------------
# Build the OUTPUT_PARSERS and NEXT_OUTPUT_PARSERS registries automatically
# from the unified parser.  Each entry is a one-argument callable that
# accepts log_text and delegates to the generic parser with the correct
# agent type baked in.
# ---------------------------------------------------------------------------

def _make_output_parser(agent_type):
    def _parser(log_text):
        return parse_unified_output(log_text, agent_type)
    _parser.__name__ = f'parse_{agent_type}_output'
    _parser.__doc__ = f'Unified section parser for {agent_type}.'
    return _parser


def _make_next_output_parser(agent_type):
    def _parser(log_text):
        return parse_next_unified_output(log_text, agent_type)
    _parser.__name__ = f'parse_next_{agent_type}_output'
    _parser.__doc__ = f'Unified next-section parser for {agent_type}.'
    return _parser


OUTPUT_PARSERS = {at: _make_output_parser(at) for at in SECTION_AGENT_TYPES}
NEXT_OUTPUT_PARSERS = {at: _make_next_output_parser(at) for at in SECTION_AGENT_TYPES}

# ---------------------------------------------------------------------------
# Progress-state stage constants
# ---------------------------------------------------------------------------
STATE_STAGE_IDLE = 'idle'
STATE_STAGE_BACKUP_READY = 'backup_ready'
STATE_STAGE_CONFIG_APPLIED = 'config_applied'
STATE_STAGE_WAITING_TARGET = 'waiting_target'
STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING = 'target_finished_restore_pending'

# Polling interval (seconds) between checks on the source agent log
POLL_INTERVAL_SECONDS = 2


def get_source_base_name(source_agent_name):
    """Extract the base agent type from a source agent name.

    Agent names follow the pattern ``<base_type>`` or ``<base_type>_<N>``
    (e.g. ``apirer``, ``crawler_2``).  Returns the matching base type from
    ``SECTION_AGENT_TYPES``, or ``None`` if no match is found.
    """
    name = source_agent_name.strip().lower().replace('-', '_')
    # Try exact match first
    if name in OUTPUT_PARSERS:
        return name
    # Try stripping a trailing _N suffix (e.g. "apirer_2" -> "apirer")
    parts = name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit() and parts[0] in OUTPUT_PARSERS:
        return parts[0]
    # Try matching two-word bases like "file_interpreter_3"
    for base in SECTION_AGENT_TYPES:
        if name == base or name.startswith(base + '_'):
            suffix = name[len(base):]
            if suffix == '' or (suffix.startswith('_') and suffix[1:].isdigit()):
                return base
    return None


# ========================================
# HELPER FUNCTIONS (from shoter.py boilerplate)
# ========================================

def load_config(path="config.yaml"):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command():
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    python_home = get_user_python_home()
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe' if sys.platform.startswith('win') else 'python3')
        if os.path.exists(python_exe):
            return [python_exe]
    if sys.platform.startswith('win'):
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']
    return ['python3']


def get_user_python_home():
    if not sys.platform.startswith('win'):
        return os.environ.get('PYTHON_HOME', '')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'PYTHON_HOME')
            return str(value) if value else ''
    except (FileNotFoundError, OSError):
        return ''


def get_agent_env():
    env = os.environ.copy()
    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        meipass = getattr(sys, '_MEIPASS')
        if meipass:
            path_parts = env.get('PATH', '').split(os.pathsep)
            path_parts = [p for p in path_parts if os.path.normpath(p) != os.path.normpath(meipass)]
            env['PATH'] = os.pathsep.join(path_parts)
    python_home = get_user_python_home()
    if not python_home:
        return env
    env['PYTHON_HOME'] = python_home
    scripts_dir = os.path.join(python_home, 'Scripts')
    current_path = env.get('PATH', '')
    env['PATH'] = f"{python_home};{scripts_dir};{current_path}"
    return env


def get_pool_path():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(grandparent) == 'pools':
        return parent
    if os.path.basename(parent) == 'pools':
        return parent
    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name):
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name):
    agent_dir = get_agent_directory(agent_name)
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
            return os.path.join(agent_dir, f"{base}.py")
    return os.path.join(agent_dir, f"{agent_name}.py")


def is_agent_running(agent_name):
    agent_dir = get_agent_directory(agent_name)
    pid_path = os.path.join(agent_dir, "agent.pid")
    if not os.path.exists(pid_path):
        return False
    try:
        with open(pid_path, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, OSError):
        return False
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return False
        return True
    except Exception:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


def wait_for_agents_to_stop(agent_names):
    if not agent_names:
        return
    waited = 0.0
    poll_interval = 0.5
    while True:
        still_running = [name for name in agent_names if is_agent_running(name)]
        if not still_running:
            return
        if waited >= 10.0:
            logging.error(
                f"WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0
        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name):
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    if not os.path.exists(script_path):
        logging.error(f"Agent script not found: {script_path}")
        return False
    try:
        cmd = get_python_command() + [script_path]
        logging.info(f"   Command: {cmd}")
        process = subprocess.Popen(
            cmd,
            cwd=agent_dir,
            env=get_agent_env(),
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
        )
        try:
            pid_path = os.path.join(agent_dir, "agent.pid")
            with open(pid_path, "w") as f:
                f.write(str(process.pid))
        except Exception as pid_err:
            logging.error(f"Failed to write PID file for target {agent_name}: {pid_err}")
        logging.info(f"Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"Failed to start agent '{agent_name}': {e}")
        return False


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"Failed to remove PID file: {e}")
            return


# ========================================
# CORE PARAMETRIZER LOGIC
# ========================================

def load_interconnection_scheme(scheme_path="interconnection-scheme.csv"):
    """Load the interconnection scheme CSV that maps source output fields to target config params."""
    if not os.path.exists(scheme_path):
        logging.error(f"Interconnection scheme not found: {scheme_path}")
        return []
    mappings = []
    with open(scheme_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            source_field = row.get('source_field', '').strip()
            target_param = row.get('target_param', '').strip()
            target_marker = normalize_target_marker_name(row.get('target_marker', ''))
            if source_field and target_param:
                mappings.append({
                    'source_field': source_field,
                    'target_param': target_param,
                    'target_marker': target_marker,
                })
    return mappings


def get_source_log_path(source_agent_name):
    """Return the log path for the configured source agent instance."""
    return os.path.join(get_agent_directory(source_agent_name), f"{source_agent_name}.log")


def get_target_log_path(target_agent_name):
    """Return the live log path for the target agent instance."""
    return os.path.join(get_agent_directory(target_agent_name), f"{target_agent_name}.log")


def read_source_log(source_agent_name):
    """Read the full log file of the source agent."""
    log_file = get_source_log_path(source_agent_name)
    if not os.path.exists(log_file):
        logging.error(f"Source agent log not found: {log_file}")
        return ""
    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def get_progress_state_path(source_agent_name):
    """Return the persisted progress-state file for this source agent."""
    safe_name = source_agent_name.replace('-', '_').replace(' ', '_')
    return f"reanim_{safe_name}.pos"


def default_progress_state():
    return {
        'offset': 0,
        'file_size': -1,
        'processed_count': 0,
        'stage': STATE_STAGE_IDLE,
        'inflight_block': None,
        'inflight_end_offset': None,
    }


def _coerce_int(value, default):
    try:
        if value is None or value == '':
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_progress_state(data):
    state = default_progress_state()
    if isinstance(data, dict):
        state.update({
            'offset': _coerce_int(data.get('offset', 0), 0),
            'file_size': _coerce_int(data.get('file_size', -1), -1),
            'processed_count': _coerce_int(data.get('processed_count', 0), 0),
            'stage': str(data.get('stage') or STATE_STAGE_IDLE),
            'inflight_block': data.get('inflight_block'),
            'inflight_end_offset': data.get('inflight_end_offset'),
        })
    if state['stage'] == 'target_finished_restore_pending':
        state['stage'] = STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING
    if state['stage'] not in {
        STATE_STAGE_IDLE,
        STATE_STAGE_BACKUP_READY,
        STATE_STAGE_CONFIG_APPLIED,
        STATE_STAGE_WAITING_TARGET,
        STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING,
    }:
        state['stage'] = STATE_STAGE_IDLE
    if state['inflight_end_offset'] is not None:
        state['inflight_end_offset'] = _coerce_int(state['inflight_end_offset'], None)
    return state


def load_progress_state(source_agent_name):
    state_path = get_progress_state_path(source_agent_name)
    if not os.path.exists(state_path):
        return default_progress_state()
    try:
        with open(state_path, 'r', encoding='utf-8') as handle:
            return _normalize_progress_state(yaml.safe_load(handle) or {})
    except Exception as exc:
        logging.warning(f"Could not load progress state '{state_path}': {exc}")
        return default_progress_state()


def save_progress_state(source_agent_name, state):
    state_path = get_progress_state_path(source_agent_name)
    normalized_state = _normalize_progress_state(state)
    try:
        with open(state_path, 'w', encoding='utf-8') as handle:
            yaml.safe_dump(normalized_state, handle, sort_keys=False)
    except Exception as exc:
        logging.warning(f"Could not save progress state '{state_path}': {exc}")


def clear_progress_state(source_agent_name):
    state_path = get_progress_state_path(source_agent_name)
    try:
        if os.path.exists(state_path):
            os.remove(state_path)
    except Exception as exc:
        logging.warning(f"Could not delete progress state '{state_path}': {exc}")


def clear_inflight_state(state):
    state['stage'] = STATE_STAGE_IDLE
    state['inflight_block'] = None
    state['inflight_end_offset'] = None
    return state


def get_target_backup_path(target_agent_name):
    return get_target_config_path(target_agent_name) + '.bck'


def get_target_segment_log_path(target_agent_name, segment_number):
    """Return the archived log path for one completed target segment."""
    return os.path.join(
        get_agent_directory(target_agent_name),
        f"{target_agent_name}_segment_{int(segment_number)}.log",
    )


def backup_target_segment_log(target_agent_name, segment_number):
    """
    Archive the target agent's current log after one segment finishes.

    This is intentionally best-effort: the sequential queue must still be able to
    advance even if the target log is missing or cannot be copied.
    """
    source_log_path = get_target_log_path(target_agent_name)
    segment_log_path = get_target_segment_log_path(target_agent_name, segment_number)

    if not os.path.exists(source_log_path):
        logging.warning(
            f"Target log not found for segment backup: '{source_log_path}'. "
            f"Segment {segment_number} will continue without an archived target log."
        )
        return False

    try:
        shutil.copy2(source_log_path, segment_log_path)
        logging.info(
            f"Archived target log for segment {segment_number} to '{segment_log_path}'"
        )
        return True
    except Exception as exc:
        logging.warning(
            f"Failed to archive target log '{source_log_path}' for segment {segment_number}: {exc}"
        )
        return False


def backup_target_config(target_agent_name):
    config_path = get_target_config_path(target_agent_name)
    backup_path = get_target_backup_path(target_agent_name)
    if not os.path.exists(config_path):
        logging.error(f"Target config not found for backup: {config_path}")
        return False
    try:
        shutil.copy2(config_path, backup_path)
        logging.info(f"Backed up target config to '{backup_path}'")
        return True
    except Exception as exc:
        logging.error(f"Failed to back up target config '{config_path}': {exc}")
        return False


def restore_target_config_from_backup(target_agent_name, remove_backup=True):
    backup_path = get_target_backup_path(target_agent_name)
    config_path = get_target_config_path(target_agent_name)
    if not os.path.exists(backup_path):
        return False
    try:
        shutil.copy2(backup_path, config_path)
        if remove_backup and os.path.exists(backup_path):
            os.remove(backup_path)
        logging.info(f"Restored target config from '{backup_path}'")
        return True
    except Exception as exc:
        logging.error(f"Failed to restore target config from backup '{backup_path}': {exc}")
        return False


def _decode_incremental_log_bytes(log_bytes):
    """Decode a live-growing UTF-8 log while tolerating incomplete trailing bytes."""
    decoder = codecs.getincrementaldecoder('utf-8')('strict')
    try:
        text = decoder.decode(log_bytes, final=False)
        buffered, _flag = decoder.getstate()
        consumed_bytes = len(log_bytes) - len(buffered)
        return text, consumed_bytes
    except UnicodeDecodeError as exc:
        if exc.start <= 0:
            logging.warning("Source log contains undecodable bytes at the current offset; waiting for more data.")
            return "", 0
        valid_prefix = log_bytes[:exc.start]
        text = valid_prefix.decode('utf-8', errors='replace')
        logging.warning("Source log contains undecodable bytes; processing only the valid UTF-8 prefix.")
        return text, len(valid_prefix)


def read_source_log_delta(source_agent_name, state):
    """
    Read unread source-log content starting from the persisted byte offset.

    Returns:
        tuple[str, int, int, bool]: (decoded_text, effective_offset, current_file_size, log_exists)
    """
    log_path = get_source_log_path(source_agent_name)
    if not os.path.exists(log_path):
        return "", _coerce_int(state.get('offset', 0), 0), -1, False

    current_size = os.path.getsize(log_path)
    offset = _coerce_int(state.get('offset', 0), 0)
    last_size = _coerce_int(state.get('file_size', -1), -1)

    if current_size < offset or (last_size != -1 and current_size < last_size):
        logging.info(
            f"Source log '{log_path}' was truncated or recreated ({last_size} -> {current_size} bytes); "
            "resetting sequential read offset to 0."
        )
        offset = 0
        state['offset'] = 0

    with open(log_path, 'rb') as handle:
        handle.seek(offset)
        unread_bytes = handle.read()

    decoded_text, _consumed_bytes = _decode_incremental_log_bytes(unread_bytes)
    state['file_size'] = current_size
    return decoded_text, offset, current_size, True


def extract_next_output_block(source_base, unread_text):
    """Return the next complete structured output block plus its byte length within unread_text."""
    parser = NEXT_OUTPUT_PARSERS[source_base]
    parsed = parser(unread_text)
    if not parsed:
        return None, None

    output_block, end_char_offset = parsed
    end_bytes = len(unread_text[:end_char_offset].encode('utf-8'))
    return output_block, end_bytes


def normalize_target_marker_name(marker):
    """Normalize a configured marker such as ``{content}`` to ``content``."""
    marker_name = str(marker or '').strip()
    if marker_name.startswith('{') and marker_name.endswith('}'):
        marker_name = marker_name[1:-1].strip()
    return marker_name


def get_target_config_path(target_agent_name):
    """Return the config.yaml path for the target agent instance."""
    target_dir = get_agent_directory(target_agent_name)
    return os.path.join(target_dir, 'config.yaml')


def read_target_config(target_agent_name):
    """Load the target agent config.yaml."""
    config_path = get_target_config_path(target_agent_name)
    if not os.path.exists(config_path):
        logging.error(f"Target config not found: {config_path}")
        return None

    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def write_target_config(target_agent_name, config):
    """Persist the target agent config.yaml."""
    config_path = get_target_config_path(target_agent_name)
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return True
    except Exception as exc:
        logging.error(f"Failed to write target config '{config_path}': {exc}")
        return False


def _get_config_value(config, target_param):
    """Read a config value from a top-level or dot-notation key."""
    if '.' not in target_param:
        return config.get(target_param)

    current = config
    for key in target_param.split('.'):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _set_config_value(config, target_param, value):
    """Set a config value using a top-level or dot-notation key."""
    if '.' not in target_param:
        config[target_param] = value
        return

    keys = target_param.split('.')
    current = config
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _apply_marker_mapping(config, target_param, target_marker, value):
    """Replace a configured marker inside an existing target string value."""
    marker_name = normalize_target_marker_name(target_marker)
    token = '{' + marker_name + '}'
    current_value = _get_config_value(config, target_param)

    if current_value is None:
        logging.warning(
            f"   Target param '{target_param}' not found for marker-level mapping '{token}'"
        )
        return False

    if not isinstance(current_value, str):
        logging.warning(
            f"   Target param '{target_param}' is not a string, so marker '{token}' cannot be replaced"
        )
        return False

    if token not in current_value:
        logging.warning(
            f"   Marker '{token}' not found in target param '{target_param}'"
        )
        return False

    _set_config_value(config, target_param, current_value.replace(token, str(value)))
    return True


def restore_target_config(target_agent_name, template_config):
    """Restore the original target config template after marker-based execution."""
    return write_target_config(target_agent_name, copy.deepcopy(template_config))


def finalize_completed_target_segment(source_agent, target_agent, progress_state):
    """
    Archive the finished target log, restore the original config, and commit the source cursor.

    This helper is shared by the normal path and the reanimation-recovery path so the
    segment log archive is not skipped if Parametrizer resumes after the target already finished.
    """
    inflight_end_offset = progress_state.get('inflight_end_offset')
    if inflight_end_offset is None:
        raise RuntimeError(
            f"Cannot finalize completed target segment for '{target_agent}' without inflight_end_offset."
        )

    segment_number = int(progress_state.get('processed_count', 0) or 0) + 1
    backup_target_segment_log(target_agent, segment_number)

    if not restore_target_config_from_backup(target_agent):
        raise RuntimeError(
            f"Target agent '{target_agent}' finished, but config.yaml could not be restored from backup."
        )

    progress_state['offset'] = int(inflight_end_offset)
    progress_state['file_size'] = max(
        int(progress_state.get('file_size', -1) or -1),
        int(progress_state['offset']),
    )
    progress_state['processed_count'] = segment_number
    clear_inflight_state(progress_state)
    save_progress_state(source_agent, progress_state)
    return progress_state


def apply_mappings_to_config(target_agent_name, mappings, output_block, base_config=None):
    """Apply field mappings from a structured output block to the target agent's config.yaml."""
    config = copy.deepcopy(base_config) if base_config is not None else read_target_config(target_agent_name)
    if config is None:
        return False

    applied_count = 0
    for mapping in mappings:
        source_field = mapping['source_field']
        target_param = mapping['target_param']
        target_marker = normalize_target_marker_name(mapping.get('target_marker', ''))

        if source_field in output_block:
            value = output_block[source_field]

            if target_marker:
                applied = _apply_marker_mapping(config, target_param, target_marker, value)
                if applied:
                    logging.info(
                        f"   Mapped: {source_field} -> {target_param} {{{target_marker}}} ({len(str(value))} chars)"
                    )
            else:
                _set_config_value(config, target_param, value)
                applied = True
                logging.info(f"   Mapped: {source_field} -> {target_param} ({len(str(value))} chars)")

            if applied:
                applied_count += 1
        else:
            logging.warning(f"   Source field '{source_field}' not found in output block")

    if not write_target_config(target_agent_name, config):
        return False

    logging.info(f"   Applied {applied_count}/{len(mappings)} mappings to {target_agent_name}")
    return True


def reconcile_reanimation_state(source_agent, target_agent, progress_state):
    """
    Restore a paused/in-flight parametrization state to a clean sequential baseline.

    If the target had already completed, the current block is committed after restoration.
    Otherwise the source offset remains at the last committed boundary and the block is retried.
    """
    stage = progress_state.get('stage') or STATE_STAGE_IDLE
    inflight_end_offset = progress_state.get('inflight_end_offset')
    backup_exists = os.path.exists(get_target_backup_path(target_agent))

    if stage == STATE_STAGE_IDLE:
        if backup_exists:
            logging.warning(
                f"Found stale backup for '{target_agent}' while Parametrizer is idle; restoring clean target config."
            )
            restore_target_config_from_backup(target_agent)
        save_progress_state(source_agent, progress_state)
        return progress_state

    logging.info(
        f"Reanimation recovery detected unfinished stage '{stage}' for source '{source_agent}' -> target '{target_agent}'."
    )

    if stage == STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING:
        if not backup_exists and inflight_end_offset is not None:
            logging.info(
                f"Backup for '{target_agent}' was already removed before pause; assuming the target config was restored."
            )
            progress_state['offset'] = int(inflight_end_offset)
            progress_state['processed_count'] = int(progress_state.get('processed_count', 0) or 0) + 1
            progress_state['file_size'] = max(
                int(progress_state.get('file_size', -1) or -1),
                int(progress_state.get('offset', 0) or 0),
            )
            clear_inflight_state(progress_state)
            save_progress_state(source_agent, progress_state)
            logging.info("Recovered a completed target run; source cursor advanced to the next unread segment.")
            return progress_state

        finalize_completed_target_segment(source_agent, target_agent, progress_state)
        logging.info("Recovered a completed target run; source cursor advanced to the next unread segment.")
        return progress_state

    if backup_exists:
        restore_target_config_from_backup(target_agent)
    else:
        logging.warning(
            f"Expected backup for interrupted stage '{stage}' was missing for '{target_agent}'. "
            "The current source segment will be retried from the last committed offset."
        )

    clear_inflight_state(progress_state)
    save_progress_state(source_agent, progress_state)
    logging.info("Recovered interrupted target processing; the current source segment will be retried.")
    return progress_state


def process_output_block(source_agent, target_agent, mappings, output_block, block_end_offset, file_size, progress_state):
    """
    Process exactly one source segment in strict order:
    backup target config -> fill parameters -> start target -> wait -> restore config -> commit cursor.
    """
    wait_for_agents_to_stop([target_agent])

    if not backup_target_config(target_agent):
        raise RuntimeError(f"Failed to back up config.yaml for target agent '{target_agent}'.")

    progress_state['stage'] = STATE_STAGE_BACKUP_READY
    progress_state['inflight_block'] = copy.deepcopy(output_block)
    progress_state['inflight_end_offset'] = int(block_end_offset)
    progress_state['file_size'] = int(file_size)
    save_progress_state(source_agent, progress_state)

    if not apply_mappings_to_config(target_agent, mappings, output_block):
        restore_target_config_from_backup(target_agent)
        clear_inflight_state(progress_state)
        save_progress_state(source_agent, progress_state)
        raise RuntimeError(f"Failed to apply mappings for source segment ending at byte {block_end_offset}.")

    progress_state['stage'] = STATE_STAGE_CONFIG_APPLIED
    save_progress_state(source_agent, progress_state)

    logging.info(f"Starting target agent '{target_agent}' for the next sequential source segment.")
    if not start_agent(target_agent):
        restore_target_config_from_backup(target_agent)
        clear_inflight_state(progress_state)
        save_progress_state(source_agent, progress_state)
        raise RuntimeError(f"Failed to start target agent '{target_agent}'.")

    progress_state['stage'] = STATE_STAGE_WAITING_TARGET
    save_progress_state(source_agent, progress_state)

    logging.info(f"Waiting for target agent '{target_agent}' to finish before advancing the source cursor...")
    wait_for_agents_to_stop([target_agent])
    logging.info(f"Target agent '{target_agent}' finished; restoring original config.yaml before continuing.")

    progress_state['stage'] = STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING
    save_progress_state(source_agent, progress_state)

    finalize_completed_target_segment(source_agent, target_agent, progress_state)


def poll_and_process_next_segment(source_agent, target_agent, source_base, mappings, progress_state):
    """
    Attempt to process the next complete source segment.

    Returns:
        tuple[bool, bool, bool]:
            processed_segment,
            source_running,
            saw_unparsed_tail
    """
    unread_text, base_offset, current_file_size, log_exists = read_source_log_delta(source_agent, progress_state)
    if not log_exists:
        return False, is_agent_running(source_agent), False

    output_block, relative_end_bytes = extract_next_output_block(source_base, unread_text)
    if output_block is None:
        source_running = is_agent_running(source_agent)
        saw_unparsed_tail = bool(unread_text.strip())
        progress_state['file_size'] = int(current_file_size)
        save_progress_state(source_agent, progress_state)
        return False, source_running, saw_unparsed_tail

    block_end_offset = int(base_offset) + int(relative_end_bytes)
    logging.info(
        f"Queued sequential source segment ending at byte {block_end_offset} "
        f"(current committed offset: {progress_state.get('offset', 0)})."
    )
    process_output_block(
        source_agent,
        target_agent,
        mappings,
        output_block,
        block_end_offset,
        current_file_size,
        progress_state,
    )
    return True, is_agent_running(source_agent), False


def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        source_agent = config.get('source_agent', '')
        target_agent = config.get('target_agent', '')

        logging.info("PARAMETRIZER AGENT STARTED")
        logging.info(f"Source agent: {source_agent}")
        logging.info(f"Target agent: {target_agent}")

        # ===== RUNTIME VALIDATION =====
        # Validate exactly one source and one target
        source_agents_list = config.get('source_agents', [])
        target_agents_list = config.get('target_agents', [])

        if not source_agent and len(source_agents_list) == 1:
            source_agent = source_agents_list[0]
        if not target_agent and len(target_agents_list) == 1:
            target_agent = target_agents_list[0]

        if not source_agent:
            logging.error("VALIDATION FAILED: Exactly one source agent must be connected to Parametrizer's input.")
            sys.exit(1)

        if not target_agent:
            logging.error("VALIDATION FAILED: Exactly one target agent must be connected to Parametrizer's output.")
            sys.exit(1)

        if len(source_agents_list) > 1:
            logging.error(
                f"VALIDATION FAILED: Only one source agent allowed, but {len(source_agents_list)} are connected: "
                f"{source_agents_list}"
            )
            sys.exit(1)

        if len(target_agents_list) > 1:
            logging.error(
                f"VALIDATION FAILED: Only one target agent allowed, but {len(target_agents_list)} are connected: "
                f"{target_agents_list}"
            )
            sys.exit(1)

        # Validate source agent type is one that produces structured output
        source_base = get_source_base_name(source_agent)
        if source_base is None:
            logging.error(
                f"VALIDATION FAILED: Source agent '{source_agent}' is not a recognized structured output agent. "
                f"Allowed: {list(OUTPUT_PARSERS.keys())}"
            )
            sys.exit(1)

        # ===== LOAD INTERCONNECTION SCHEME =====
        mappings = load_interconnection_scheme()
        if not mappings:
            logging.error("No valid mappings found in interconnection-scheme.csv")
            sys.exit(1)

        logging.info(f"Loaded {len(mappings)} field mappings from interconnection-scheme.csv")
        for m in mappings:
            target_marker = normalize_target_marker_name(m.get('target_marker', ''))
            if target_marker:
                logging.info(f"   {m['source_field']} -> {m['target_param']} {{{target_marker}}}")
            else:
                logging.info(f"   {m['source_field']} -> {m['target_param']}")
        progress_state = default_progress_state()
        if _IS_REANIMATED:
            progress_state = load_progress_state(source_agent)
        else:
            clear_progress_state(source_agent)
            if os.path.exists(get_target_backup_path(target_agent)):
                logging.warning(
                    f"Fresh Parametrizer start found leftover backup for '{target_agent}'; restoring clean config state."
                )
                restore_target_config_from_backup(target_agent)

        progress_state = reconcile_reanimation_state(source_agent, target_agent, progress_state)

        logging.info(
            f"Sequential Parametrizer queue ready. Resuming from byte offset {progress_state.get('offset', 0)} "
            f"with {progress_state.get('processed_count', 0)} committed segment(s)."
        )

        ever_processed = int(progress_state.get('processed_count', 0) or 0) > 0

        while True:
            processed_segment, source_running, saw_unparsed_tail = poll_and_process_next_segment(
                source_agent,
                target_agent,
                source_base,
                mappings,
                progress_state,
            )

            if processed_segment:
                ever_processed = True
                continue

            if source_running:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            if saw_unparsed_tail:
                logging.warning(
                    f"Source agent '{source_agent}' stopped with trailing log content that did not form a complete "
                    "structured segment. Parametrizer will stop at the last committed boundary."
                )

            if ever_processed:
                logging.info(
                    f"Source agent '{source_agent}' has been completely parametrized into target '{target_agent}'. "
                    f"Processed {progress_state.get('processed_count', 0)} sequential segment(s). "
                    f"The source is stopped, the log has been consumed, and Parametrizer will stop now."
                )
            else:
                logging.info(
                    f"Source agent '{source_agent}' is stopped and no complete structured segments were available. "
                    "Parametrizer will stop without starting the target."
                )

            clear_progress_state(source_agent)
            break

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
