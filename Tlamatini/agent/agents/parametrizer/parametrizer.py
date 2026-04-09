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
# STRUCTURED OUTPUT PARSERS
# ========================================

# Each source agent type has its own structured output pattern in its log file.
# This registry maps agent base names to parser functions.

def _parse_brace_blocks(log_text, pattern):
    """Parse blocks of format: <label> {\n<content>\n}"""
    results = []
    for match in re.finditer(pattern, log_text, re.DOTALL):
        label = match.group('label').strip()
        content = match.group('content').strip()
        results.append({'_label': label, '_content': content})
    return results


def parse_apirer_output(log_text):
    """Apirer: <url> RESPONSE {\\n...\\n}"""
    blocks = []
    pattern = r'<(?P<label>[^>]+)>\s*RESPONSE\s*\{\s*\n(?P<content>.*?)\n\}'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'url': match.group('label').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_gitter_output(log_text):
    """Gitter: <git command> RESPONSE {\\n...\\n}"""
    blocks = []
    pattern = r'<(?P<label>[^>]+)>\s*RESPONSE\s*\{\s*\n(?P<content>.*?)\n\}'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'git_command': match.group('label').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_kuberneter_output(log_text):
    """Kuberneter: KUBECTL EXECUTION PARAMETERS: ..., STATUS: code\\n{\\n...\\n}"""
    blocks = []
    pattern = (
        r'KUBECTL EXECUTION PARAMETERS:\s*(?P<params>[^,]+),\s*STATUS:\s*(?P<status>\d+)'
        r'\s*\{\s*\n(?P<content>.*?)\n\}'
    )
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'parameters': match.group('params').strip(),
            'status': match.group('status').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_ini_end_response(log_text, ini_marker, end_marker):
    """Parse INI_RESPONSE<<<...>>>END_RESPONSE style blocks."""
    blocks = []
    pattern = re.escape(ini_marker) + r'.*?\n(?P<content>.*?)\n.*?' + re.escape(end_marker)
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_crawler_output(log_text):
    """Crawler: INI_RESPONSE_<LABEL><<<\\n...\\n>>>END_RESPONSE_<LABEL>"""
    blocks = []
    pattern = r'INI_RESPONSE_(?P<label>\w+)<<<\s*\n(?P<content>.*?)\n\s*>>>END_RESPONSE_(?P=label)'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'label': match.group('label').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_summarizer_output(log_text):
    """Summarizer: INI_RESPONSE_SUMMARIZER<<<\\n...\\n>>>END_RESPONSE_SUMMARIZER"""
    return parse_ini_end_response(log_text, 'INI_RESPONSE_SUMMARIZER<<<', '>>>END_RESPONSE_SUMMARIZER')


def parse_prompter_output(log_text):
    """Prompter: INI_RESPONSE<<<\\n...\\n>>>END_RESPONSE"""
    return parse_ini_end_response(log_text, 'INI_RESPONSE<<<', '>>>END_RESPONSE')


def parse_flowcreator_output(log_text):
    """FlowCreator: INI_RESPONSE\\n...\\n>>>END_RESPONSE"""
    blocks = []
    pattern = r'INI_RESPONSE\s*\n(?P<content>.*?)\n\s*>>>END_RESPONSE'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_file_interpreter_output(log_text):
    """File-Interpreter: INI_FILE: [filepath] (mode)\\n...\\nEND_FILE"""
    blocks = []
    pattern = r'INI_FILE:\s*\[(?P<filepath>[^\]]+)\]\s*\((?P<mode>[^)]+)\)\s*\n(?P<content>.*?)\nEND_FILE'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'file_path': match.group('filepath').strip(),
            'mode': match.group('mode').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_image_interpreter_output(log_text):
    """Image-Interpreter: INI_IMAGE_FILE: [filepath]\\n...\\nEND_FILE"""
    blocks = []
    pattern = r'INI_IMAGE_FILE:\s*\[(?P<filepath>[^\]]+)\]\s*\n(?P<content>.*?)\nEND_FILE'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'file_path': match.group('filepath').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_file_extractor_output(log_text):
    """File-Extractor: INI_FILE: [filepath] (extracted)\\n...\\nEND_FILE"""
    blocks = []
    pattern = r'INI_FILE:\s*\[(?P<filepath>[^\]]+)\]\s*\(extracted\)\s*\n(?P<content>.*?)\nEND_FILE'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'file_path': match.group('filepath').strip(),
            'response_body': match.group('content').strip()
        })
    return blocks


def parse_kyber_keygen_output(log_text):
    """Kyber-KeyGen: KYBER PUBLIC KEY {\\n...\\n} and KYBER PRIVATE KEY {\\n...\\n}"""
    blocks = []
    pub_pattern = r'KYBER PUBLIC KEY\s*\{\s*\n(?P<content>.*?)\n\}'
    priv_pattern = r'KYBER PRIVATE KEY\s*\{\s*\n(?P<content>.*?)\n\}'
    pub_keys = [m.group('content').strip() for m in re.finditer(pub_pattern, log_text, re.DOTALL)]
    priv_keys = [m.group('content').strip() for m in re.finditer(priv_pattern, log_text, re.DOTALL)]
    for i in range(max(len(pub_keys), len(priv_keys))):
        block = {}
        if i < len(pub_keys):
            block['public_key'] = pub_keys[i]
        if i < len(priv_keys):
            block['private_key'] = priv_keys[i]
        blocks.append(block)
    return blocks


def parse_kyber_cipher_output(log_text):
    """Kyber-Cipher: KYBER GENERATED ENCAPSULATION/INIT VECTOR/CIPHER TEXT {\\n...\\n}"""
    blocks = []
    enc_pattern = r'KYBER GENERATED ENCAPSULATION\s*\{\s*\n(?P<content>.*?)\n\}'
    iv_pattern = r'KYBER GENERATED INIT VECTOR\s*\{\s*\n(?P<content>.*?)\n\}'
    ct_pattern = r'KYBER GENERATED CIPHER TEXT\s*\{\s*\n(?P<content>.*?)\n\}'
    encaps = [m.group('content').strip() for m in re.finditer(enc_pattern, log_text, re.DOTALL)]
    ivs = [m.group('content').strip() for m in re.finditer(iv_pattern, log_text, re.DOTALL)]
    cts = [m.group('content').strip() for m in re.finditer(ct_pattern, log_text, re.DOTALL)]
    count = max(len(encaps), len(ivs), len(cts))
    for i in range(count):
        block = {}
        if i < len(encaps):
            block['encapsulation'] = encaps[i]
        if i < len(ivs):
            block['initialization_vector'] = ivs[i]
        if i < len(cts):
            block['cipher_text'] = cts[i]
        blocks.append(block)
    return blocks


def parse_kyber_decipher_output(log_text):
    """Kyber-DeCipher: KYBER DECIPHERED BUFFER {\\n...\\n}"""
    blocks = []
    pattern = r'KYBER DECIPHERED BUFFER\s*\{\s*\n(?P<content>.*?)\n\}'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        blocks.append({
            'deciphered_buffer': match.group('content').strip()
        })
    return blocks


def _parse_kv_block(content):
    """Parse a block of ``key: value`` lines into a dictionary.

    Lines are split on the first ``: `` so that values can contain colons
    (e.g. URLs, JSON strings).  Empty values are included as empty strings.
    """
    result = {}
    for line in content.split('\n'):
        line = line.strip()
        if not line:
            continue
        sep_idx = line.find(': ')
        if sep_idx == -1:
            # Bare key with no value
            result[line.rstrip(':')] = ''
        else:
            result[line[:sep_idx]] = line[sep_idx + 2:]
    return result


def parse_gatewayer_output(log_text):
    """Gatewayer: INI_GATEWAY_EVENT<<<\\nkey: value\\n...\\n>>>END_GATEWAY_EVENT

    Extracted fields: event_id, event_type, session_id, correlation_id,
    content_type, method, path, body.
    """
    blocks = []
    pattern = r'INI_GATEWAY_EVENT<<<\s*\n(?P<content>.*?)\n>>>END_GATEWAY_EVENT'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        fields = _parse_kv_block(match.group('content'))
        blocks.append(fields)
    return blocks


def parse_gateway_relayer_output(log_text):
    """Gateway-Relayer: INI_RELAY_EVENT<<<\\nkey: value\\n...\\n>>>END_RELAY_EVENT

    Extracted fields: event_type, delivery_id, action, ref, repository,
    sender, body.
    """
    blocks = []
    pattern = r'INI_RELAY_EVENT<<<\s*\n(?P<content>.*?)\n>>>END_RELAY_EVENT'
    for match in re.finditer(pattern, log_text, re.DOTALL):
        fields = _parse_kv_block(match.group('content'))
        blocks.append(fields)
    return blocks


# Registry mapping source agent base name -> parser function
OUTPUT_PARSERS = {
    'apirer': parse_apirer_output,
    'gitter': parse_gitter_output,
    'kuberneter': parse_kuberneter_output,
    'crawler': parse_crawler_output,
    'summarizer': parse_summarizer_output,
    'file_interpreter': parse_file_interpreter_output,
    'image_interpreter': parse_image_interpreter_output,
    'file_extractor': parse_file_extractor_output,
    'prompter': parse_prompter_output,
    'flowcreator': parse_flowcreator_output,
    'kyber_keygen': parse_kyber_keygen_output,
    'kyber_cipher': parse_kyber_cipher_output,
    'kyber_decipher': parse_kyber_decipher_output,
    'gatewayer': parse_gatewayer_output,
    'gateway_relayer': parse_gateway_relayer_output,
}

PARAMETRIZER_MARKER_PATTERN = re.compile(r'\{([^{}\r\n]+)\}')
POLL_INTERVAL_SECONDS = 0.5
STATE_STAGE_IDLE = 'idle'
STATE_STAGE_BACKUP_READY = 'backup_ready'
STATE_STAGE_CONFIG_APPLIED = 'config_applied'
STATE_STAGE_WAITING_TARGET = 'waiting_target'
STATE_STAGE_TARGET_FINISHED_RESTORE_PENDING = 'target_finished_restore_pending'


def get_source_base_name(agent_pool_name):
    """Extract base agent name from pool name: 'apirer_1' -> 'apirer', 'file_interpreter_2' -> 'file_interpreter'."""
    for known_base in OUTPUT_PARSERS:
        if agent_pool_name == known_base or agent_pool_name.startswith(known_base + '_'):
            suffix = agent_pool_name[len(known_base):]
            if suffix == '' or (suffix.startswith('_') and suffix[1:].isdigit()):
                return known_base
    return None


def _parse_next_brace_response(log_text, label_field, content_field='response_body'):
    pattern = r'<(?P<label>[^>]+)>\s*RESPONSE\s*\{\s*\n(?P<content>.*?)\n\}'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        label_field: match.group('label').strip(),
        content_field: match.group('content').strip(),
    }, match.end())


def parse_next_apirer_output(log_text):
    return _parse_next_brace_response(log_text, 'url')


def parse_next_gitter_output(log_text):
    return _parse_next_brace_response(log_text, 'git_command')


def parse_next_kuberneter_output(log_text):
    pattern = (
        r'KUBECTL EXECUTION PARAMETERS:\s*(?P<params>[^,]+),\s*STATUS:\s*(?P<status>\d+)'
        r'\s*\{\s*\n(?P<content>.*?)\n\}'
    )
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'parameters': match.group('params').strip(),
        'status': match.group('status').strip(),
        'response_body': match.group('content').strip(),
    }, match.end())


def _parse_next_ini_end_response(log_text, ini_marker, end_marker):
    pattern = re.escape(ini_marker) + r'.*?\n(?P<content>.*?)\n.*?' + re.escape(end_marker)
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'response_body': match.group('content').strip(),
    }, match.end())


def parse_next_crawler_output(log_text):
    pattern = r'INI_RESPONSE_(?P<label>\w+)<<<\s*\n(?P<content>.*?)\n\s*>>>END_RESPONSE_(?P=label)'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'label': match.group('label').strip(),
        'response_body': match.group('content').strip(),
    }, match.end())


def parse_next_summarizer_output(log_text):
    return _parse_next_ini_end_response(log_text, 'INI_RESPONSE_SUMMARIZER<<<', '>>>END_RESPONSE_SUMMARIZER')


def parse_next_prompter_output(log_text):
    return _parse_next_ini_end_response(log_text, 'INI_RESPONSE<<<', '>>>END_RESPONSE')


def parse_next_flowcreator_output(log_text):
    pattern = r'INI_RESPONSE\s*\n(?P<content>.*?)\n\s*>>>END_RESPONSE'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'response_body': match.group('content').strip(),
    }, match.end())


def parse_next_file_interpreter_output(log_text):
    pattern = r'INI_FILE:\s*\[(?P<filepath>[^\]]+)\]\s*\((?P<mode>[^)]+)\)\s*\n(?P<content>.*?)\nEND_FILE'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'file_path': match.group('filepath').strip(),
        'mode': match.group('mode').strip(),
        'response_body': match.group('content').strip(),
    }, match.end())


def parse_next_image_interpreter_output(log_text):
    pattern = r'INI_IMAGE_FILE:\s*\[(?P<filepath>[^\]]+)\]\s*\n(?P<content>.*?)\nEND_FILE'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'file_path': match.group('filepath').strip(),
        'response_body': match.group('content').strip(),
    }, match.end())


def parse_next_file_extractor_output(log_text):
    pattern = r'INI_FILE:\s*\[(?P<filepath>[^\]]+)\]\s*\(extracted\)\s*\n(?P<content>.*?)\nEND_FILE'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'file_path': match.group('filepath').strip(),
        'response_body': match.group('content').strip(),
    }, match.end())


def parse_next_kyber_keygen_output(log_text):
    pattern = (
        r'KYBER PUBLIC KEY\s*\{\s*\n(?P<public_key>.*?)\n\}'
        r'.*?KYBER PRIVATE KEY\s*\{\s*\n(?P<private_key>.*?)\n\}'
    )
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'public_key': match.group('public_key').strip(),
        'private_key': match.group('private_key').strip(),
    }, match.end())


def parse_next_kyber_cipher_output(log_text):
    pattern = (
        r'KYBER GENERATED ENCAPSULATION\s*\{\s*\n(?P<encapsulation>.*?)\n\}'
        r'.*?KYBER GENERATED INIT VECTOR\s*\{\s*\n(?P<initialization_vector>.*?)\n\}'
        r'.*?KYBER GENERATED CIPHER TEXT\s*\{\s*\n(?P<cipher_text>.*?)\n\}'
    )
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'encapsulation': match.group('encapsulation').strip(),
        'initialization_vector': match.group('initialization_vector').strip(),
        'cipher_text': match.group('cipher_text').strip(),
    }, match.end())


def parse_next_kyber_decipher_output(log_text):
    pattern = r'KYBER DECIPHERED BUFFER\s*\{\s*\n(?P<content>.*?)\n\}'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return ({
        'deciphered_buffer': match.group('content').strip(),
    }, match.end())


def parse_next_gatewayer_output(log_text):
    pattern = r'INI_GATEWAY_EVENT<<<\s*\n(?P<content>.*?)\n>>>END_GATEWAY_EVENT'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return (_parse_kv_block(match.group('content')), match.end())


def parse_next_gateway_relayer_output(log_text):
    pattern = r'INI_RELAY_EVENT<<<\s*\n(?P<content>.*?)\n>>>END_RELAY_EVENT'
    match = re.search(pattern, log_text, re.DOTALL)
    if not match:
        return None
    return (_parse_kv_block(match.group('content')), match.end())


NEXT_OUTPUT_PARSERS = {
    'apirer': parse_next_apirer_output,
    'gitter': parse_next_gitter_output,
    'kuberneter': parse_next_kuberneter_output,
    'crawler': parse_next_crawler_output,
    'summarizer': parse_next_summarizer_output,
    'file_interpreter': parse_next_file_interpreter_output,
    'image_interpreter': parse_next_image_interpreter_output,
    'file_extractor': parse_next_file_extractor_output,
    'prompter': parse_next_prompter_output,
    'flowcreator': parse_next_flowcreator_output,
    'kyber_keygen': parse_next_kyber_keygen_output,
    'kyber_cipher': parse_next_kyber_cipher_output,
    'kyber_decipher': parse_next_kyber_decipher_output,
    'gatewayer': parse_next_gatewayer_output,
    'gateway_relayer': parse_next_gateway_relayer_output,
}


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
        if backup_exists:
            restore_target_config_from_backup(target_agent)
        elif inflight_end_offset is not None:
            logging.info(
                f"Backup for '{target_agent}' was already removed before pause; assuming the target config was restored."
            )

        if inflight_end_offset is not None:
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

    if not restore_target_config_from_backup(target_agent):
        raise RuntimeError(f"Target agent '{target_agent}' finished, but config.yaml could not be restored from backup.")

    progress_state['offset'] = int(block_end_offset)
    progress_state['file_size'] = int(file_size)
    progress_state['processed_count'] = int(progress_state.get('processed_count', 0) or 0) + 1
    clear_inflight_state(progress_state)
    save_progress_state(source_agent, progress_state)


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
