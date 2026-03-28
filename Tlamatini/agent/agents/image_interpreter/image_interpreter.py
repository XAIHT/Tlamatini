# Image-Interpreter Agent - Image analysis and description via LLM vision model
# Non-deterministic agent (uses LLM)
# Action: Resolve image paths -> Convert to base64 -> Query LLM -> Log results
#         -> Start downstream agents

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import base64
import glob
import json
import time
import yaml
import logging
import subprocess
import urllib.request
import urllib.error
from typing import Dict

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

# Supported image extensions
IMAGE_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif',
    '.webp', '.svg', '.ico', '.heic', '.heif', '.avif',
}


def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except Exception as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def get_python_command() -> list:
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


def get_user_python_home() -> str:
    if not sys.platform.startswith('win'):
        return os.environ.get('PYTHON_HOME', '')
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Environment') as key:
            value, _ = winreg.QueryValueEx(key, 'PYTHON_HOME')
            return str(value) if value else ''
    except (FileNotFoundError, OSError):
        return ''


def get_agent_env() -> dict:
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


def get_pool_path() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(grandparent) == 'pools':
        return parent
    if os.path.basename(parent) == 'pools':
        return parent
    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    if os.path.exists(os.path.join(agent_dir, f"{agent_name}.py")):
        return os.path.join(agent_dir, f"{agent_name}.py")
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        if os.path.exists(os.path.join(agent_dir, f"{base}.py")):
            return os.path.join(agent_dir, f"{base}.py")
    return os.path.join(agent_dir, f"{agent_name}.py")


def is_agent_running(agent_name: str) -> bool:
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


def wait_for_agents_to_stop(agent_names: list):
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
                f"❌ WAITING FOR AGENTS TO STOP: {still_running} still running "
                f"after {int(waited)}s. Will keep waiting..."
            )
            waited = 0.0
        time.sleep(poll_interval)
        waited += poll_interval


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    if not os.path.exists(script_path):
        logging.error(f"❌ Agent script not found: {script_path}")
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
            logging.error(f"⚠️ Failed to write PID file for target {agent_name}: {pid_err}")
        logging.info(f"✅ Started agent '{agent_name}' with PID: {process.pid}")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to start agent '{agent_name}': {e}")
        return False


# ==============================
# IMAGE INTERPRETATION FUNCTIONS
# ==============================

def extract_image_metadata(image_path: str) -> Dict:
    """Extract EXIF and other metadata from an image file. Returns a dict of available metadata."""
    metadata = {}
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        img = Image.open(image_path)
        metadata['format'] = img.format or ''
        metadata['size'] = f"{img.width}x{img.height}"
        metadata['mode'] = img.mode
        exif_data = img.getexif()
        if exif_data:
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                # Skip binary/raw data fields
                if isinstance(value, bytes):
                    continue
                metadata[tag_name] = str(value)
    except ImportError:
        logging.debug("Pillow not installed — skipping EXIF metadata extraction.")
    except Exception as e:
        logging.debug(f"Could not extract metadata from {image_path}: {e}")
    return metadata


def build_system_context(image_path: str, metadata: Dict) -> str:
    """
    Build a system prompt that provides the LLM with contextual hints
    derived from the image filename and any available metadata.
    """
    filename = os.path.basename(image_path)
    name_without_ext = os.path.splitext(filename)[0]
    # Clean up common filename separators to get readable tokens
    readable_name = name_without_ext.replace('_', ' ').replace('-', ' ').replace('.', ' ')

    parts = [
        "You are an expert image analyst. You have been given an image to analyze along with contextual information derived from the file itself.",
        "",
        "== FILE CONTEXT ==",
        f"File name: {filename}",
        f"Readable name tokens: {readable_name}",
    ]

    parent_dir = os.path.basename(os.path.dirname(image_path))
    if parent_dir:
        parts.append(f"Parent folder: {parent_dir}")

    if metadata:
        parts.append("")
        parts.append("== IMAGE METADATA ==")
        for key, value in metadata.items():
            parts.append(f"{key}: {value}")

    parts.append("")
    parts.append("== INSTRUCTIONS ==")
    parts.append(
        "Use the file name and metadata above as contextual hints when answering the user's question. "
        "For example, if the user asks who is the person in the image, the file name may contain "
        "the person's name — use it as a hint but always verify against what you actually see in the image. "
        "If the file name suggests a name (e.g. 'John_Smith.jpg'), mention it and confirm or deny based "
        "on visual evidence. Do NOT blindly trust the file name — treat it as a clue, not a fact. "
        "Similarly, metadata fields like 'Artist', 'ImageDescription', or 'XPComment' may contain "
        "relevant information about the subject."
    )

    return "\n".join(parts)


def convert_image_to_base64(image_path: str) -> str:
    """Convert an image file to a raw base64 encoded string."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')


def parse_exclusions(filetype_exclusions: str) -> tuple:
    """
    Parse a comma-separated exclusions string into (excluded_extensions, excluded_filenames).
    Entries with a dot and no other path chars are treated as extensions (e.g. "exe" -> ".exe").
    Entries that look like filenames (e.g. "thumbnail.png", ".profile") go into excluded_filenames.
    """
    excluded_extensions = set()
    excluded_filenames = set()
    if not filetype_exclusions or not filetype_exclusions.strip():
        return excluded_extensions, excluded_filenames
    for entry in filetype_exclusions.split(','):
        entry = entry.strip()
        if not entry:
            continue
        if '.' in entry and not entry.startswith('.'):
            excluded_filenames.add(entry.lower())
        elif entry.startswith('.') and len(entry) > 1 and '.' not in entry[1:]:
            excluded_filenames.add(entry.lower())
        else:
            ext = entry.lower() if entry.startswith('.') else f".{entry.lower()}"
            excluded_extensions.add(ext)
    return excluded_extensions, excluded_filenames


def apply_exclusions(files: list, excluded_extensions: set, excluded_filenames: set) -> list:
    """Filter out files matching excluded extensions or filenames."""
    if not excluded_extensions and not excluded_filenames:
        return files
    original_count = len(files)
    filtered = []
    for f in files:
        basename = os.path.basename(f).lower()
        ext = os.path.splitext(f)[1].lower()
        if ext in excluded_extensions or basename in excluded_filenames:
            continue
        filtered.append(f)
    excluded_count = original_count - len(filtered)
    if excluded_count > 0:
        logging.info(f"🚫 Excluded {excluded_count} file(s) by filetype_exclusions filter")
    return filtered


def resolve_image_paths(images_pathfilenames: str, recursive: bool = False) -> list:
    """
    Resolve the images_pathfilenames parameter to a list of actual image file paths.
    Supports:
      - Wildcards: "C:\\images\\*.jpg"
      - Directory path: "C:\\images" (scans for all image types)
      - File-Interpreter agent pool name: "file_interpreter_1"
      - Single file path: "D:\\photos\\sunset.jpg"
    When recursive=True, scans subdirectories as well.
    """
    if not images_pathfilenames:
        return []

    resolved = images_pathfilenames.strip()

    # Check if it's a File-Interpreter agent pool name
    pool_path = get_pool_path()
    fi_config_path = os.path.join(pool_path, resolved, 'config.yaml')
    if os.path.exists(fi_config_path):
        try:
            with open(fi_config_path, 'r', encoding='utf-8') as f:
                fi_config = yaml.safe_load(f) or {}
            fi_path = fi_config.get('path_filenames', '')
            if fi_path:
                logging.info(f"🔗 Resolved File-Interpreter agent '{resolved}' → path: {fi_path}")
                resolved = fi_path
            else:
                logging.warning(f"⚠️ File-Interpreter agent '{resolved}' has empty path_filenames.")
                return []
        except Exception as e:
            logging.error(f"❌ Failed to read File-Interpreter config: {e}")
            return []

    # Check if it's a directory → scan for all image types
    if os.path.isdir(resolved):
        scan_type = "Recursively scanning" if recursive else "Scanning"
        logging.info(f"📁 {scan_type} directory for images: {resolved}")
        image_files = []
        sub_pattern = '**' if recursive else ''
        for ext in IMAGE_EXTENSIONS:
            if recursive:
                image_files.extend(glob.glob(os.path.join(resolved, sub_pattern, f"*{ext}"), recursive=True))
                image_files.extend(glob.glob(os.path.join(resolved, sub_pattern, f"*{ext.upper()}"), recursive=True))
            else:
                image_files.extend(glob.glob(os.path.join(resolved, f"*{ext}")))
                image_files.extend(glob.glob(os.path.join(resolved, f"*{ext.upper()}")))
        return sorted(set(image_files))

    # Check if it contains wildcards
    if '*' in resolved or '?' in resolved:
        pattern = resolved
        if recursive and '**' not in pattern:
            parent = os.path.dirname(pattern)
            filename_part = os.path.basename(pattern)
            pattern = os.path.join(parent, '**', filename_part) if parent else os.path.join('**', filename_part)
            logging.info(f"🔄 Recursive mode: expanded pattern to '{pattern}'")
        matched = glob.glob(pattern, recursive=recursive)
        return [f for f in matched if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS]

    # Single file
    if os.path.isfile(resolved):
        ext = os.path.splitext(resolved)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            return [resolved]
        else:
            logging.warning(f"⚠️ File '{resolved}' is not a recognized image format (ext: {ext}).")
            return []

    logging.error(f"❌ Could not resolve images_pathfilenames: {resolved}")
    return []


def analyze_image_with_llm(image_path: str, llm_config: dict) -> str:
    """
    Analyze a single image using an LLM vision model via Ollama-compatible API.
    Adapted from qwen_analyze_image in imaging/image_interpreter.py.
    """
    host = llm_config.get('host', 'http://localhost:11434').rstrip('/')
    model = llm_config.get('model', 'llama3.2-vision:11b')
    prompt = llm_config.get('prompt', 'Describe this image in detail.')
    token = llm_config.get('token', '')

    try:
        image_base64 = convert_image_to_base64(image_path)
        if not image_base64:
            return "Error: Failed to convert image to base64"
        logging.info(f"   Image converted to base64, size: {len(image_base64)} chars.")
    except FileNotFoundError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error converting image: {e}"

    # Build system context with filename hints and metadata
    metadata = extract_image_metadata(image_path)
    system_context = build_system_context(image_path, metadata)
    logging.info(f"   System context built with {len(metadata)} metadata fields for: {os.path.basename(image_path)}")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_context
            },
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64]
            }
        ],
        "stream": True,
        "options": {
            "temperature": 0.0,
            "num_ctx": 32768,
            "repeat_penalty": 1.85,
            "top_p": 0.95,
            "top_k": 50,
            "stop": ["<|end_of_text|>", "<|eot_id|>", "assistant", "</html>", "</body>"]
        }
    }

    payload_bytes = json.dumps(payload).encode('utf-8')

    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    url = f"{host}/api/chat"
    logging.info(f"   Sending request to {model} at {url}...")

    try:
        req = urllib.request.Request(url, data=payload_bytes, headers=headers, method='POST')
        full_description = []

        with urllib.request.urlopen(req, timeout=300) as response:
            for line in response:
                if line:
                    try:
                        json_chunk = json.loads(line.decode('utf-8'))
                        content = ""
                        if "message" in json_chunk:
                            content = json_chunk["message"].get("content", "")
                        elif "response" in json_chunk:
                            content = json_chunk.get("response", "")

                        if content:
                            full_description.append(content)

                        if json_chunk.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue

        return "".join(full_description)

    except urllib.error.URLError as e:
        return f"Error: Could not connect to LLM at {host}. Check if the server is running. ({e})"
    except Exception as e:
        return f"Error analyzing image: {e}"


# PID Management
PID_FILE = "agent.pid"


def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


def main():
    config = load_config()

    # Write PID file immediately
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        images_pathfilenames = config.get('images_pathfilenames', '')
        recursive = config.get('recursive', False)
        filetype_exclusions = config.get('filetype_exclusions', '')
        target_agents = config.get('target_agents', [])
        llm_config = config.get('llm', {})

        logging.info("🖼️ IMAGE-INTERPRETER AGENT STARTED")
        logging.info(f"📁 images_pathfilenames: {images_pathfilenames}")
        logging.info(f"🔄 Recursive: {recursive}")
        if filetype_exclusions:
            logging.info(f"🚫 Exclusions: {filetype_exclusions}")
        logging.info(f"🤖 LLM model: {llm_config.get('model', 'N/A')} @ {llm_config.get('host', 'N/A')}")
        logging.info(f"🎯 Targets: {target_agents}")

        # Resolve image paths
        image_files = resolve_image_paths(images_pathfilenames, recursive=recursive)
        excl_exts, excl_names = parse_exclusions(filetype_exclusions)
        image_files = apply_exclusions(image_files, excl_exts, excl_names)

        if not image_files:
            logging.warning("⚠️ No image files found to process.")
        else:
            logging.info(f"📷 Found {len(image_files)} image(s) to process.")

            # Process each image
            for idx, image_path in enumerate(image_files, 1):
                logging.info(f"--- Processing image {idx}/{len(image_files)}: {image_path}")

                description = analyze_image_with_llm(image_path, llm_config)

                # Log in structured format
                logging.info(f"INI_IMAGE_FILE: [{image_path}]")
                logging.info("{")
                for line in description.split('\n'):
                    logging.info(f"    {line}")
                logging.info("}")
                logging.info("END_FILE")

            logging.info(f"✅ All {len(image_files)} image(s) processed successfully.")

        # Trigger downstream agents
        total_triggered = 0
        if target_agents:
            wait_for_agents_to_stop(target_agents)
            logging.info(f"🚀 Triggering {len(target_agents)} downstream agents...")
            for target in target_agents:
                if start_agent(target):
                    total_triggered += 1

        logging.info(f"🏁 Image-Interpreter agent finished. Triggered {total_triggered}/{len(target_agents)} agents.")

    finally:
        # Keep LED green briefly for visual feedback
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
