import os
import sys
import time
import yaml
import logging
import threading
import requests
from typing import Dict, Optional

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

# Try to import LangChain/Ollama (graceful degradation if missing, though typically present)
try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
except ImportError:
    # This might happen if environment is not set up, but we assume it is based on other agents
    pass

# Set working directory to script location
try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {e}\n")

# Logging Setup
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

PID_FILE = "agent.pid"
REANIM_FILE = "reanim.pos"


# ─────────────────────────────────────────────────────────────
# Path resolution helpers (ported from Emailer/Raiser agents)
# ─────────────────────────────────────────────────────────────

def get_pool_path() -> str:
    """
    Get the pool directory path where deployed agents reside.
    Deployed agents with cardinals (e.g., starter_1, whatsapper_1) are here.
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'agents', 'pools')
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Check if deployed in session: pools/<session_id>/<agent_dir>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return parent

        # Fallback: agents/<agent_name> -> agents/pools
        return os.path.join(os.path.dirname(current_dir), 'pools')


def get_template_agents_path() -> str:
    """
    Get the template agents directory path (non-deployed agents).
    Template agents without cardinals (e.g., whatsapper, starter) are here.
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), 'agents')
    else:
        current_dir = os.path.dirname(os.path.abspath(__file__))

        # Check if deployed in session: pools/<session>/<agent>
        parent = os.path.dirname(current_dir)
        grandparent = os.path.dirname(parent)
        if os.path.basename(grandparent) == 'pools':
            return os.path.dirname(grandparent)

        # Fallback: agents/<agent_name> -> agents
        return os.path.dirname(current_dir)


def is_deployed_agent(agent_name: str) -> bool:
    """
    Check if an agent name has a cardinal suffix (is a deployed instance).
    Examples: starter_1 -> True, starter -> False
    """
    parts = agent_name.rsplit('_', 1)
    if len(parts) == 2:
        try:
            int(parts[1])
            return True
        except ValueError:
            return False
    return False


def get_agent_directory(agent_name: str) -> str:
    """
    Get the full path to an agent's directory.
    Deployed agents (with cardinal, e.g., starter_1) are in pool/.
    Template agents (without cardinal, e.g., starter) are in agents/.
    """
    if is_deployed_agent(agent_name):
        return os.path.join(get_pool_path(), agent_name)
    else:
        return os.path.join(get_template_agents_path(), agent_name)


def get_agent_log_path(agent_name: str) -> str:
    """
    Get the log file path for an agent.
    Examples:
    - starter_1 -> pool/starter_1/starter_1.log
    - starter   -> agents/starter/starter.log
    """
    agent_dir = get_agent_directory(agent_name)
    return os.path.join(agent_dir, f"{agent_name}.log")


# ─────────────────────────────────────────────────────────────
# Smart polling (ported from Emailer/Raiser pattern)
# ─────────────────────────────────────────────────────────────

def check_log_for_new_content(log_path: str, offset: int, file_sizes: Dict[str, int]) -> tuple:
    """
    Check a log file for new content starting from offset.
    Smart polling that handles:
    - Log files that don't exist initially (waits for appearance)
    - Log files that are truncated/recreated (resets offset to 0)
    - Log files that decrease in size (treats as new file)

    Args:
        log_path: Path to the log file
        offset: Current read offset
        file_sizes: Dictionary tracking last known file sizes (modified in-place)

    Returns: (new_content: str or None, new_offset: int)
    """
    last_known_size = file_sizes.get(log_path, -1)  # -1 means never seen

    if not os.path.exists(log_path):
        # File doesn't exist - reset tracking and wait
        file_sizes[log_path] = -1  # Mark as "waiting for file"
        return None, 0  # Reset offset to 0 to catch content when file appears

    try:
        current_size = os.path.getsize(log_path)

        # Detect file truncation/recreation scenarios:
        # 1. File size decreased (truncated or recreated with less content)
        # 2. File appeared after being absent (last_known_size was -1)
        # 3. Current offset is beyond file size (stale offset from reanim.pos)
        if current_size < offset or last_known_size == -1 or current_size < last_known_size:
            if last_known_size == -1:
                logging.info(f"📁 Log file appeared: {log_path}")
            elif current_size < last_known_size:
                logging.info(f"🔄 Log file truncated/recreated: {log_path} ({last_known_size} -> {current_size} bytes)")
            else:
                logging.info(f"🔄 Stale offset detected for {log_path}, resetting")
            offset = 0  # Read from beginning

        # Update tracking
        file_sizes[log_path] = current_size

        if current_size <= offset:
            return None, offset  # No new content

        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            f.seek(offset)
            new_content = f.read()
            new_offset = f.tell()

        if new_content.strip():
            return new_content, new_offset
        return None, new_offset

    except Exception as e:
        logging.error(f"Error reading log {log_path}: {e}")
        return None, offset


# ─────────────────────────────────────────────────────────────
# Config / PID / Reanim helpers
# ─────────────────────────────────────────────────────────────

def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"❌ Error loading config: {e}")
        return {}

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
        except Exception:
            return

def load_reanim_offsets() -> Dict[str, int]:
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}

def save_reanim_offsets(offsets: Dict[str, int]):
    try:
        with open(REANIM_FILE, "w", encoding="utf-8") as f:
            yaml.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Could not save offsets: {e}")


# ─────────────────────────────────────────────────────────────
# WhatsApp / LLM helpers
# ─────────────────────────────────────────────────────────────

def send_whatsapp_message(phone: str, apikey: str, message: str) -> bool:
    if not phone or not apikey:
        logging.warning("⚠️ TextMeBot Phone or API Key missing. Cannot send message.")
        return False

    # Truncate message to avoid URL length limits
    if len(message) > 500:
        message = message[:500] + "..."

    import urllib.parse
    encoded_msg = urllib.parse.quote(message, safe='')
    url = f"https://api.textmebot.com/send.php?recipient={phone}&apikey={apikey}&text={encoded_msg}"

    try:
        # TextMeBot API uses GET requests. Add Content-Length: 0 to avoid 411.
        headers = {"Content-Length": "0"}
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            logging.info(f"✅ WhatsApp sent to {phone}")
            return True
        else:
            # Log full details for debugging API issues
            logging.error(f"❌ WhatsApp failed: HTTP {response.status_code}")
            logging.error(f"   URL (truncated): {url[:150]}...")
            logging.error(f"   Response: {response.text[:300]}")
            return False
    except Exception as e:
        logging.error(f"❌ WhatsApp error: {e}")
        return False

def analyze_log_chunk(llm, config, chunk: str, source_agent: str) -> Optional[str]:
    """
    Analyze a log chunk using LLM. Returns a message if actionable, None otherwise.
    """
    if not chunk.strip():
        return None

    keywords_str = config.get('keywords', '')
    system_prompt_tmpl = config.get('system_prompt', '')

    # Hybrid approach: keyword pre-filter then LLM summarization
    keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
    chunk_lower = chunk.lower()

    hit = False
    for k in keywords:
        if k in chunk_lower:
            hit = True
            break

    if not hit and keywords:
        return None  # Skip if no keywords found (if keywords are defined)

    # Perform LLM Analysis
    try:
        prompt = system_prompt_tmpl.format(source_agent=source_agent, keywords=keywords_str)
        messages = [
            SystemMessage(content=prompt),
            HumanMessage(content=f"Log Entry:\n{chunk}")
        ]
        response = llm.invoke(messages)
        return response.content
    except Exception as e:
        logging.error(f"LLM Error: {e}")
        return None


# ─────────────────────────────────────────────────────────────
# Monitoring thread (with smart polling)
# ─────────────────────────────────────────────────────────────

def monitor_source(agent_name: str, stop_event: threading.Event, config: Dict,
                   global_offsets: Dict, offset_lock: threading.Lock):
    """
    Thread function to monitor a single source agent's log file.
    Uses smart polling to handle log files that don't exist yet or get truncated.
    """
    logging.info(f"👀 Started monitoring thread for: {agent_name}")

    # Initialize LLM for this thread
    try:
        llm = ChatOllama(
            base_url=config['llm']['base_url'],
            model=config['llm']['model'],
            temperature=config['llm']['temperature']
        )
    except Exception as e:
        logging.error(f"❌ Failed to init LLM for {agent_name}: {e}")
        return

    log_path = get_agent_log_path(agent_name)
    logging.info(f"   📄 {agent_name} log: {log_path} (exists: {os.path.exists(log_path)})")

    # Per-thread file size tracking for smart polling
    # -1 means file hasn't been seen yet (waiting for appearance)
    file_sizes: Dict[str, int] = {}

    # Initialize file size tracking
    if os.path.exists(log_path):
        file_sizes[log_path] = os.path.getsize(log_path)
    else:
        file_sizes[log_path] = -1  # Mark as waiting for file to appear

    # Initialize offset: start at 0 to catch all content (including pre-existing)
    with offset_lock:
        if agent_name not in global_offsets:
            global_offsets[agent_name] = 0

    poll_interval = config.get('poll_interval', 1)  # Default 1s

    while not stop_event.is_set():
        try:
            with offset_lock:
                current_offset = global_offsets.get(agent_name, 0)

            # Smart polling: handles missing files, truncation, appearing files
            new_content, new_offset = check_log_for_new_content(
                log_path, current_offset, file_sizes
            )

            with offset_lock:
                global_offsets[agent_name] = new_offset

            # Analyze if there's new content
            if new_content:
                alert_msg = analyze_log_chunk(llm, config, new_content, agent_name)

                if alert_msg:
                    logging.info(f"🚨 Keywords detected in {agent_name}!")
                    send_whatsapp_message(
                        config['textmebot']['phone'],
                        config['textmebot']['apikey'],
                        alert_msg
                    )

        except Exception as e:
            logging.error(f"Error monitoring {agent_name}: {e}")

        time.sleep(poll_interval)


def main():
    write_pid_file()
    config = load_config()

    source_agents = config.get('source_agents', [])
    if isinstance(source_agents, str):
        source_agents = [s.strip() for s in source_agents.split(',') if s.strip()]

    if not source_agents:
        logging.warning("⚠️ No source agents configured to monitor.")

    logging.info("📱 WHATSAPPER AGENT STARTED (Dark Green)")
    logging.info(f"📁 Pool path: {get_pool_path()}")
    logging.info(f"📁 Template path: {get_template_agents_path()}")
    logging.info(f"👀 Monitoring: {source_agents}")
    logging.info(f"🔍 Keywords: {config.get('keywords', '')}")
    logging.info(f"🤖 Model: {config['llm']['model']}")
    logging.info(f"⏱️ Poll interval: {config.get('poll_interval', 5)}s")

    # Log resolved paths for debugging
    for source in source_agents:
        log_path = get_agent_log_path(source)
        logging.info(f"   📄 {source} log: {log_path} (exists: {os.path.exists(log_path)})")

    logging.info("=" * 60)

    # Shared state
    offsets = load_reanim_offsets()
    offset_lock = threading.Lock()
    stop_event = threading.Event()
    threads = []

    # Initialize offsets for new sources (start at 0 to catch everything)
    for agent in source_agents:
        if agent not in offsets:
            offsets[agent] = 0

    # Start threads
    for agent in source_agents:
        t = threading.Thread(
            target=monitor_source,
            args=(agent, stop_event, config, offsets, offset_lock)
        )
        t.daemon = True
        t.start()
        threads.append(t)

    try:
        # Main loop: periodic offset saving
        while True:
            time.sleep(10)
            with offset_lock:
                save_reanim_offsets(offsets)

    except KeyboardInterrupt:
        logging.info("Stopping Whatsapper agent...")
        stop_event.set()
        for t in threads:
            t.join(timeout=2)
    except Exception as e:
        logging.error(f"Critical Error: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
        logging.info("Whatsapper Stopped.")

if __name__ == "__main__":
    main()
