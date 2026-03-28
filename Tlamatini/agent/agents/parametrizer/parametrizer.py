# Parametrizer Agent - Utility Interconnection Agent
# Maps structured outputs from a source agent's log to a target agent's config.yaml
# Reads interconnection-scheme.csv to know which output fields map to which config params
# If multiple structured output elements exist, iterates: fill config -> start target -> wait -> repeat

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import csv
import re
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


def get_source_base_name(agent_pool_name):
    """Extract base agent name from pool name: 'apirer_1' -> 'apirer', 'file_interpreter_2' -> 'file_interpreter'."""
    for known_base in OUTPUT_PARSERS:
        if agent_pool_name == known_base or agent_pool_name.startswith(known_base + '_'):
            suffix = agent_pool_name[len(known_base):]
            if suffix == '' or (suffix.startswith('_') and suffix[1:].isdigit()):
                return known_base
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
            if source_field and target_param:
                mappings.append({
                    'source_field': source_field,
                    'target_param': target_param
                })
    return mappings


def read_source_log(source_agent_name):
    """Read the log file of the source agent."""
    source_dir = get_agent_directory(source_agent_name)
    log_file = os.path.join(source_dir, f"{source_agent_name}.log")
    if not os.path.exists(log_file):
        # Try base name for log file
        parts = source_agent_name.rsplit('_', 1)
        if len(parts) == 2 and parts[1].isdigit():
            log_file = os.path.join(source_dir, f"{source_agent_name}.log")
    if not os.path.exists(log_file):
        logging.error(f"Source agent log not found: {log_file}")
        return ""
    with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


def apply_mappings_to_config(target_agent_name, mappings, output_block):
    """Apply field mappings from a structured output block to the target agent's config.yaml."""
    target_dir = get_agent_directory(target_agent_name)
    config_path = os.path.join(target_dir, 'config.yaml')

    if not os.path.exists(config_path):
        logging.error(f"Target config not found: {config_path}")
        return False

    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}

    applied_count = 0
    for mapping in mappings:
        source_field = mapping['source_field']
        target_param = mapping['target_param']

        if source_field in output_block:
            value = output_block[source_field]
            config[target_param] = value
            logging.info(f"   Mapped: {source_field} -> {target_param} ({len(str(value))} chars)")
            applied_count += 1
        else:
            logging.warning(f"   Source field '{source_field}' not found in output block")

    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    logging.info(f"   Applied {applied_count}/{len(mappings)} mappings to {target_agent_name}")
    return True


def main():
    config = load_config()
    write_pid_file()

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
            logging.info(f"   {m['source_field']} -> {m['target_param']}")

        # ===== PARSE SOURCE AGENT LOG =====
        log_text = read_source_log(source_agent)
        if not log_text:
            logging.error(f"Source agent '{source_agent}' log is empty or unreadable")
            sys.exit(1)

        parser = OUTPUT_PARSERS[source_base]
        output_blocks = parser(log_text)

        if not output_blocks:
            logging.error(f"No structured output elements found in '{source_agent}' log")
            sys.exit(1)

        logging.info(f"Found {len(output_blocks)} structured output element(s) in source log")

        # ===== ITERATE OVER OUTPUT BLOCKS =====
        # For each structured output element: fill target config -> start target -> wait for completion
        for idx, block in enumerate(output_blocks):
            block_num = idx + 1
            logging.info(f"--- Processing output element {block_num}/{len(output_blocks)} ---")

            # Apply mappings to target config
            success = apply_mappings_to_config(target_agent, mappings, block)
            if not success:
                logging.error(f"Failed to apply mappings for element {block_num}")
                continue

            # Wait for target to stop if still running from a previous iteration
            wait_for_agents_to_stop([target_agent])

            # Start the target agent
            logging.info(f"Starting target agent '{target_agent}' for element {block_num}")
            if start_agent(target_agent):
                logging.info(f"Target agent '{target_agent}' started for element {block_num}")
            else:
                logging.error(f"Failed to start target agent '{target_agent}' for element {block_num}")
                continue

            # Wait for target agent to complete before processing next element
            if block_num < len(output_blocks):
                logging.info(f"Waiting for target agent '{target_agent}' to finish before next element...")
                wait_for_agents_to_stop([target_agent])
                logging.info(f"Target agent '{target_agent}' finished element {block_num}")

        logging.info(
            f"Parametrizer agent finished. Processed {len(output_blocks)} element(s) "
            f"from '{source_agent}' into '{target_agent}'."
        )

    finally:
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
