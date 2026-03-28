# FlowHypervisor Agent - LLM-powered flow monitoring agent
# Watches all running agents' processes and log files, uses an LLM to detect
# anomalies, and notifies the user when attention is needed.
# This agent is system-managed: started/stopped by the system, not by other agents.

import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import json
import logging
import urllib.request
import urllib.error
import psutil
from typing import Dict, List

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

# Custom handler that flushes immediately for real-time log visibility
class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logger = logging.getLogger()
logger.setLevel(logging.INFO)
file_handler = FlushingFileHandler(LOG_FILE_PATH, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(console_handler)


# ============================================================
# Configuration
# ============================================================

PID_FILE = "agent.pid"
REANIM_FILE = "reanim.json"
ALERT_FILE = "hypervisor_alert.json"
PROMPT_FILE = "monitoring-prompt.pmt"

EXCLUDED_AGENT_TYPES = {'flowcreator', 'flowhypervisor'}


def load_config(path: str = "config.yaml") -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error(f"❌ Error: {path} not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        logging.error(f"❌ Error parsing {path}: {e}")
        sys.exit(1)


def load_monitoring_prompt() -> str:
    prompt_path = os.path.join(script_dir, PROMPT_FILE)
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logging.error(f"❌ monitoring-prompt.pmt not found at {prompt_path}")
        return ""
    except Exception as e:
        logging.error(f"❌ Error reading monitoring prompt: {e}")
        return ""


# ============================================================
# Pool / Agent path helpers
# ============================================================

def get_pool_path() -> str:
    """Get the pool directory (session dir) where deployed agents reside."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)

    if os.path.basename(grandparent) == 'pools':
        return parent
    if os.path.basename(parent) == 'pools':
        return parent
    return os.path.join(os.path.dirname(current_dir), 'pools')


def get_agent_base_type(agent_folder_name: str) -> str:
    """Extract the base agent type from a pool folder name.
    e.g., 'monitor_log_1' -> 'monitor_log', 'starter_2' -> 'starter'
    """
    parts = agent_folder_name.rsplit('_', 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return agent_folder_name


# ============================================================
# Step A: Discover all agents in the flow
# ============================================================

def discover_agents(pool_path: str) -> List[str]:
    """List all agent directories in the pool, excluding FlowCreator and FlowHypervisor."""
    agents = []
    if not os.path.isdir(pool_path):
        logging.error(f"❌ Pool directory not found: {pool_path}")
        return agents

    for item in sorted(os.listdir(pool_path)):
        item_path = os.path.join(pool_path, item)
        if not os.path.isdir(item_path):
            continue
        base_type = get_agent_base_type(item)
        if base_type.lower() in EXCLUDED_AGENT_TYPES:
            continue
        agents.append(item)

    return agents


# ============================================================
# Step B: Load all config.yaml files
# ============================================================

def load_all_configs(pool_path: str, agents: List[str]) -> Dict[str, Dict]:
    """Load config.yaml for each agent. Returns {agent_name: config_dict}."""
    configs = {}
    for agent_name in agents:
        config_path = os.path.join(pool_path, agent_name, 'config.yaml')
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    configs[agent_name] = yaml.safe_load(f) or {}
            except Exception as e:
                logging.warning(f"⚠️ Could not load config for {agent_name}: {e}")
                configs[agent_name] = {}
        else:
            configs[agent_name] = {}
    return configs


# ============================================================
# Step C: Build connection matrix
# ============================================================

def build_connection_matrix(agents: List[str], configs: Dict[str, Dict]) -> List[List[int]]:
    """Build an NxN connection matrix. matrix[row][col] = 1 means agent[row] outputs to agent[col].
    Rows represent agent outputs; columns represent agent inputs.
    """
    n = len(agents)
    matrix = [[0] * n for _ in range(n)]
    agent_index = {name: i for i, name in enumerate(agents)}

    for agent_name, config in configs.items():
        row = agent_index.get(agent_name)
        if row is None:
            continue

        # Collect all outgoing connections from this agent's config
        targets = set()

        # target_agents — most agents
        for t in config.get('target_agents', []):
            targets.add(t)

        # output_agents — Ender, Stopper, Cleaner
        for t in config.get('output_agents', []):
            targets.add(t)

        # target_agents_a / target_agents_b — Asker, Forker
        for t in config.get('target_agents_a', []):
            targets.add(t)
        for t in config.get('target_agents_b', []):
            targets.add(t)

        for target_name in targets:
            col = agent_index.get(target_name)
            if col is not None:
                matrix[row][col] = 1

    return matrix


def format_matrix(agents: List[str], matrix: List[List[int]]) -> str:
    """Format the connection matrix as a readable string."""
    if not agents:
        return "(empty matrix)"

    # Find max agent name length for alignment
    max_len = max(len(a) for a in agents)
    header = " " * (max_len + 2) + "  ".join(
        f"{i:>2}" for i in range(len(agents))
    )
    lines = [header]
    for i, agent_name in enumerate(agents):
        row_str = "  ".join(f"{v:>2}" for v in matrix[i])
        lines.append(f"{agent_name:<{max_len}}  {row_str}")

    # Legend
    lines.append("")
    lines.append("Column legend:")
    for i, agent_name in enumerate(agents):
        lines.append(f"  {i}: {agent_name}")

    return "\n".join(lines)


# ============================================================
# Step E-F: Monitor PIDs and log files
# ============================================================

def check_agent_pid(pool_path: str, agent_name: str) -> int:
    """Check if an agent is running by reading its agent.pid file.
    Returns the PID if running, 0 otherwise.
    """
    pid_path = os.path.join(pool_path, agent_name, "agent.pid")
    if not os.path.exists(pid_path):
        return 0
    try:
        with open(pid_path, "r") as f:
            pid = int(f.read().strip())
        # Verify the process actually exists
        if psutil.pid_exists(pid):
            return pid
        return 0
    except (ValueError, OSError):
        return 0


def get_agent_log_path(pool_path: str, agent_name: str) -> str:
    """Get the path to an agent's log file."""
    return os.path.join(pool_path, agent_name, f"{agent_name}.log")


# ============================================================
# Step G: Incremental log reading with reanimation
# ============================================================

def save_reanim(offsets: Dict[str, int]):
    """Save log read offsets for crash recovery."""
    try:
        with open(REANIM_FILE, "w", encoding="utf-8") as f:
            json.dump(offsets, f)
    except Exception as e:
        logging.warning(f"⚠️ Could not save reanimation data: {e}")


def load_reanim() -> Dict[str, int]:
    """Load log read offsets from reanimation file."""
    if not os.path.exists(REANIM_FILE):
        return {}
    try:
        with open(REANIM_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {}
            return json.loads(content)
    except Exception:
        return {}


def collect_incremental_logs(
    pool_path: str,
    agents: List[str],
    offsets: Dict[str, int]
) -> tuple:
    """Read new content from all agent log files since last offset.
    Returns (combined_log_text, updated_offsets, per_agent_info).
    """
    per_agent_logs = {}
    combined_parts = []

    for agent_name in agents:
        log_path = get_agent_log_path(pool_path, agent_name)
        current_offset = offsets.get(agent_name, 0)

        if not os.path.exists(log_path):
            per_agent_logs[agent_name] = "(no log file)"
            continue

        try:
            file_size = os.path.getsize(log_path)

            # Handle log rotation / truncation
            if file_size < current_offset:
                current_offset = 0

            if file_size == current_offset:
                per_agent_logs[agent_name] = "(no new content)"
                continue

            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                f.seek(current_offset)
                new_content = f.read()
                new_offset = f.tell()

            offsets[agent_name] = new_offset

            if new_content.strip():
                per_agent_logs[agent_name] = new_content
                combined_parts.append(
                    f"--- [{agent_name}] ---\n{new_content}"
                )
            else:
                per_agent_logs[agent_name] = "(no new content)"

        except Exception as e:
            logging.error(f"❌ Error reading log for {agent_name}: {e}")
            per_agent_logs[agent_name] = f"(error: {e})"

    combined_text = "\n".join(combined_parts)
    return combined_text, offsets, per_agent_logs


# ============================================================
# Step H: LLM invocation
# ============================================================

def query_ollama(host: str, model: str, system_prompt: str,
                 context: str, temperature: float = 0.0,
                 user_instructions: str = "") -> str:
    """Send a prompt to Ollama and return the full response."""
    url = f"{host.rstrip('/')}/api/generate"

    # Build the user-instructions section if provided
    user_section = ""
    if user_instructions and user_instructions.strip():
        user_section = (
            f"\n\n═══ ADDITIONAL USER INSTRUCTIONS ═══\n\n"
            f"{user_instructions.strip()}\n\n"
            f"═══ END USER INSTRUCTIONS ═══\n"
        )

    full_prompt = (
        f"{system_prompt}"
        f"{user_section}\n\n"
        f"═══ MONITORING DATA ═══\n\n"
        f"{context}\n\n"
        f"═══ END MONITORING DATA ═══\n\n"
        f"Analyze the above data and respond with either "
        f"\"OK\" or \"ATTENTION NEEDED {{ explanation }}\"."
    )

    payload = json.dumps({
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {"temperature": temperature}
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response", "")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        raise RuntimeError(f"Ollama HTTP {e.code}: {error_body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Ollama at {host}: {e.reason}") from e


# ============================================================
# Step I-K: Parse LLM response and write alert file
# ============================================================

def parse_llm_response(response: str) -> tuple:
    """Parse the LLM response. Returns (is_ok, explanation)."""
    stripped = response.strip()

    # Check if the response is just "OK"
    if stripped.upper() == "OK":
        return True, ""

    # Check for ATTENTION NEEDED pattern
    upper = stripped.upper()
    if "ATTENTION NEEDED" in upper:
        # Extract everything after "ATTENTION NEEDED"
        idx = upper.index("ATTENTION NEEDED")
        explanation = stripped[idx + len("ATTENTION NEEDED"):].strip()
        # Remove surrounding braces if present
        if explanation.startswith("{") and explanation.endswith("}"):
            explanation = explanation[1:-1].strip()
        elif explanation.startswith("{"):
            explanation = explanation[1:].strip()
        return False, explanation if explanation else stripped

    # If neither pattern matched clearly, treat as suspicious
    # (LLM might have given a verbose answer)
    if any(word in upper for word in [
        "ERROR", "CRASH", "STUCK", "HUNG", "SUSPICIOUS", "FAILED", "ATTENTION"
    ]):
        return False, stripped

    # Default: treat as OK
    return True, ""


def write_alert_file(explanation: str):
    """Write an alert file for the frontend to detect."""
    try:
        alert_data = {
            "type": "hypervisor_alert",
            "agent_id": CURRENT_DIR_NAME,
            "message": explanation,
            "timestamp": time.time()
        }
        with open(ALERT_FILE, "w", encoding="utf-8") as f:
            json.dump(alert_data, f)
        logging.info("🚨 Alert file created for frontend.")
    except Exception as e:
        logging.error(f"❌ Failed to write alert file: {e}")


def clear_alert_file():
    """Remove the alert file if it exists."""
    try:
        if os.path.exists(ALERT_FILE):
            os.remove(ALERT_FILE)
    except Exception:
        pass


# ============================================================
# Step G: Build monitoring context for LLM
# ============================================================

def build_monitoring_context(
    agents: List[str],
    pool_path: str,
    matrix: List[List[int]],
    new_logs: str,
    per_agent_info: Dict[str, str],
    flow_start_time: float = 0.0,
    agent_first_seen: Dict[str, float] = None,
    last_alert_explanation: str = ""
) -> str:
    """Build the full context string to send to the LLM."""
    sections = []

    # 0. Flow elapsed time — hard fact the LLM can rely on
    now = time.time()
    if flow_start_time > 0:
        elapsed = now - flow_start_time
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        sections.append(f"FLOW ELAPSED TIME: {mins}m {secs}s ({int(elapsed)}s total)")
    sections.append(f"CURRENT TIME: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    sections.append("")

    # 1. Agent list with PID status and running duration
    if agent_first_seen is None:
        agent_first_seen = {}
    sections.append("AGENT STATUS:")
    for agent_name in agents:
        pid = check_agent_pid(pool_path, agent_name)
        status = f"RUNNING (PID: {pid})" if pid else "NOT RUNNING"
        log_status = per_agent_info.get(agent_name, "(unknown)")
        has_log = os.path.exists(get_agent_log_path(pool_path, agent_name))

        duration_str = ""
        if pid and agent_name in agent_first_seen:
            dur = now - agent_first_seen[agent_name]
            duration_str = f" | Running for: {int(dur)}s"

        sections.append(
            f"  {agent_name}: {status}{duration_str} | "
            f"Log file: {'exists' if has_log else 'missing'} | "
            f"New content: {log_status if log_status.startswith('(') else 'YES'}"
        )

    # 2. Connection matrix
    sections.append("")
    sections.append("CONNECTION MATRIX:")
    sections.append(format_matrix(agents, matrix))

    # 3. Previous alert (so LLM doesn't forget issues between cycles)
    if last_alert_explanation:
        sections.append("")
        sections.append("PREVIOUS CYCLE ALERT (still relevant unless resolved):")
        sections.append(f"  {last_alert_explanation}")

    # 4. Incremental log content
    sections.append("")
    if new_logs.strip():
        sections.append("NEW LOG CONTENT SINCE LAST CHECK:")
        sections.append(new_logs)
    else:
        sections.append(
            "NEW LOG CONTENT SINCE LAST CHECK: (none — no new log "
            "output from any agent since last poll)"
        )

    return "\n".join(sections)


# ============================================================
# PID Management
# ============================================================

def write_pid_file():
    try:
        with open(PID_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception as e:
        logging.error(f"❌ Failed to write PID file: {e}")


def remove_pid_file():
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as e:
            logging.error(f"❌ Failed to remove PID file: {e}")
            return


# ============================================================
# Step M: Check if any other agents are still running
# ============================================================

def any_agents_running(pool_path: str, agents: List[str]) -> bool:
    """Check if at least one monitored agent still has a running process."""
    for agent_name in agents:
        if check_agent_pid(pool_path, agent_name) > 0:
            return True
    return False


# ============================================================
# Main monitoring loop
# ============================================================

def main():
    config = load_config()
    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        llm_config = config.get('llm', {})
        host = llm_config.get('host', 'http://127.0.0.1:11434')
        model = llm_config.get('model', 'llama3.1:8b')
        temperature = llm_config.get('temperature', 0.0)
        poll_time = config.get('monitoring_poll_time', 10)
        user_instructions = config.get('user_instructions', '')

        # Load monitoring prompt
        monitoring_prompt = load_monitoring_prompt()
        if not monitoring_prompt:
            logging.error("❌ No monitoring prompt loaded. Cannot proceed.")
            return

        pool_path = get_pool_path()

        logging.info("🛡️ FLOWHYPERVISOR AGENT STARTED")
        logging.info(f"📁 Pool path: {pool_path}")
        logging.info(f"🤖 LLM: {model} @ {host}")
        logging.info(f"⏱️ Poll interval: {poll_time}s")
        if user_instructions and user_instructions.strip():
            logging.info(f"📝 User instructions: {user_instructions[:100]}{'...' if len(user_instructions) > 100 else ''}")
        logging.info("=" * 60)

        # Step A: Discover agents
        agents = discover_agents(pool_path)
        if not agents:
            logging.error("❌ No agents found in the flow. Nothing to monitor.")
            return

        logging.info(f"🔍 Discovered {len(agents)} agent(s) in the flow:")
        for agent_name in agents:
            logging.info(f"   • {agent_name}")

        # Step B: Load all configs
        configs = load_all_configs(pool_path, agents)
        logging.info(f"📋 Loaded {len(configs)} config file(s).")

        # Step C: Build connection matrix
        matrix = build_connection_matrix(agents, configs)
        logging.info("📊 Connection matrix built:")
        logging.info(f"\n{format_matrix(agents, matrix)}")
        logging.info("=" * 60)

        # Step G (partial): Load reanimation offsets
        offsets = load_reanim()
        logging.info(
            f"💾 Reanimation data: {len(offsets)} offset(s) loaded."
        )

        # Clear any stale alert file
        clear_alert_file()

        # ==========================================
        # Main monitoring loop (Steps E-M)
        # ==========================================
        cycle = 0
        consecutive_no_running = 0
        flow_start_time = time.time()
        agent_first_seen: Dict[str, float] = {}
        last_alert_explanation = ""

        while True:
            cycle += 1
            logging.info(f"\n{'─' * 40}")
            logging.info(f"🔄 Monitoring cycle #{cycle}")

            elapsed = time.time() - flow_start_time
            logging.info(f"   ⏱️ Flow elapsed: {int(elapsed)}s")

            # Step E-F: Check PIDs
            running_agents = []
            stopped_agents = []
            for agent_name in agents:
                pid = check_agent_pid(pool_path, agent_name)
                if pid:
                    running_agents.append((agent_name, pid))
                    # Track when each agent was first seen running
                    if agent_name not in agent_first_seen:
                        agent_first_seen[agent_name] = time.time()
                else:
                    stopped_agents.append(agent_name)
                    # Clear first-seen when agent stops (it finished)
                    agent_first_seen.pop(agent_name, None)

            logging.info(
                f"   Running: {len(running_agents)} | "
                f"Stopped: {len(stopped_agents)}"
            )

            for name, pid in running_agents:
                dur = int(time.time() - agent_first_seen.get(name, time.time()))
                logging.info(f"   ✅ {name} (PID: {pid}, running {dur}s)")
            for name in stopped_agents:
                logging.info(f"   ⏹️ {name} (not running)")

            # Step G: Collect incremental logs
            new_logs, offsets, per_agent_info = collect_incremental_logs(
                pool_path, agents, offsets
            )

            # Save offsets immediately for crash recovery
            save_reanim(offsets)

            # Check if any agents have log files
            agents_with_logs = [
                a for a in agents
                if os.path.exists(get_agent_log_path(pool_path, a))
            ]
            logging.info(
                f"   📄 {len(agents_with_logs)} agent(s) have log files."
            )

            # Step M: Check if flow is still alive
            if not running_agents:
                consecutive_no_running += 1
                logging.info(
                    f"   ⚠️ No agents running "
                    f"(consecutive: {consecutive_no_running})"
                )
                # If no agents have been running for 3 consecutive cycles,
                # the flow is done — exit
                if consecutive_no_running >= 3:
                    logging.info(
                        "🏁 No agents running for 3 consecutive cycles. "
                        "Flow appears complete. Exiting."
                    )
                    break
            else:
                consecutive_no_running = 0

            # Step H: Build context and query LLM
            context = build_monitoring_context(
                agents, pool_path, matrix, new_logs, per_agent_info,
                flow_start_time, agent_first_seen, last_alert_explanation
            )

            logging.info("   🤖 Querying LLM for analysis...")
            try:
                llm_response = query_ollama(
                    host, model, monitoring_prompt,
                    context, temperature, user_instructions
                )
                logging.info(
                    f"   📝 LLM Response: "
                    f"{llm_response[:200]}{'...' if len(llm_response) > 200 else ''}"
                )

                # Step I-J: Parse response
                is_ok, explanation = parse_llm_response(llm_response)

                if is_ok:
                    logging.info("   ✅ LLM verdict: OK")
                    clear_alert_file()
                    last_alert_explanation = ""
                else:
                    # Step K: Write alert for frontend
                    logging.warning(
                        "   🚨 LLM verdict: ATTENTION NEEDED"
                    )
                    logging.warning(f"   📋 {explanation}")
                    write_alert_file(explanation)
                    last_alert_explanation = explanation

            except RuntimeError as e:
                logging.error(f"   ❌ LLM query failed: {e}")
                write_alert_file(f"LLM query failed: {e}")
                logging.info(
                    "   ⏩ Continuing monitoring despite LLM failure..."
                )
            except Exception as e:
                logging.error(f"   ❌ Unexpected error in LLM query: {e}")
                write_alert_file(f"Unexpected error in LLM query: {e}")

            # Wait for next poll
            logging.info(f"   ⏳ Sleeping {poll_time}s...")
            time.sleep(poll_time)

        logging.info("🏁 FlowHypervisor agent finished.")

    except Exception as e:
        logging.error(f"❌ FlowHypervisor critical error: {e}")
    finally:
        clear_alert_file()
        time.sleep(0.4)
        remove_pid_file()

    sys.exit(0)


if __name__ == "__main__":
    main()
