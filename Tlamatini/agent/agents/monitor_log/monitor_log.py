import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import re
import time
import yaml
import logging
from typing import TypedDict, Literal, List, Any
from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import StateGraph, START, END


try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as e:
    sys.stderr.write(f"Critical Error: Failed to set working directory to {os.path.dirname(os.path.abspath(__file__))}: {e}\n")

# Use directory name for log file (e.g., monitor_log_1 -> monitor_log_1.log)
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

# Reanimation detection: AGENT_REANIMATED=1 means resume from pause
_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()

# Custom handler that flushes immediately to avoid buffering delays
class FlushingFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()  # Force flush to disk after each log entry

# Configure logging with immediate flush
logger = logging.getLogger()
logger.setLevel(logging.INFO)
file_handler = FlushingFileHandler(LOG_FILE_PATH, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)

def load_config(path="config.yaml"):
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("❌ Error: config.yaml not found.")
        sys.exit(1)

CONFIG = load_config()
REANIM_FILE = "reanim.pos"

def save_reanim_offset(offset: int):
    """Saves the current file offset to reanim.pos."""
    try:
        with open(REANIM_FILE, "w") as f:
            f.write(str(offset))
    except Exception as e:
        logging.warning(f"⚠️ Warning: Could not save reanimation offset: {e}")

def get_reanim_offset(log_file_path: str) -> int:
    """
    Reads the last known offset from reanim.pos.
    Validates it against the actual log file size.
    """
    if not os.path.exists(REANIM_FILE):
        return 0

    try:
        with open(REANIM_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                return 0
            saved_offset = int(content)

        if os.path.exists(log_file_path):
            file_size = os.path.getsize(log_file_path)
            if saved_offset > file_size:
                logging.warning(f"[SYSTEM] ⚠️ Log file smaller than saved offset ({file_size} < {saved_offset}). Starting from 0.")
                return 0

        logging.info(f"[SYSTEM] 🔄 Resuming from offset {saved_offset} (loaded from {REANIM_FILE})")
        return saved_offset

    except ValueError:
        logging.warning("⚠️ Warning: Corrupt reanim.pos file. Starting from 0.")
        return 0
    except Exception as e:
        logging.error(f"⚠️ Error reading reanim.pos: {e}")
        return 0

def read_log_delta(file_path: str, current_offset: int, max_bytes: int = 0):
    """
    Reads the log file starting from 'current_offset'.
    Handles file rotation (if file size < offset, resets to 0).
    If max_bytes > 0 and the delta exceeds that limit, only the LAST
    max_bytes of the delta are returned (the offset still advances to EOF).
    Returns: (new_content, new_offset)
    """
    if not os.path.exists(file_path):
        return "Error: Log file not found.", current_offset

    file_size = os.path.getsize(file_path)

    if file_size < current_offset:
        logging.warning(f"\n[SYSTEM] ⚠️ Log rotation detected (Size {file_size} < Offset {current_offset}). Resetting pointer.")
        current_offset = 0

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            delta_size = file_size - current_offset

            # If max_bytes is set and delta exceeds it, skip ahead
            if max_bytes > 0 and delta_size > max_bytes:
                skip_offset = file_size - max_bytes
                logging.info(f"[SYSTEM] ✂️ Delta too large ({delta_size} bytes). Reading only last {max_bytes} bytes.")
                f.seek(skip_offset)
                new_content = f.read()
                # Discard the first partial line (we may have landed mid-line)
                first_newline = new_content.find('\n')
                if first_newline != -1:
                    new_content = new_content[first_newline + 1:]
            else:
                f.seek(current_offset)
                new_content = f.read()

            new_offset = f.tell()
            return new_content, new_offset
    except Exception as e:
        return f"Error reading file: {e}", current_offset


def build_keyword_pattern(keywords_str: str) -> re.Pattern:
    """
    Builds a compiled regex pattern from a comma-separated keywords string.
    The match is case-insensitive.
    """
    keywords = [kw.strip() for kw in keywords_str.split(',') if kw.strip()]
    # Escape regex special characters and join with OR
    escaped = [re.escape(kw) for kw in keywords]
    pattern_str = '|'.join(escaped)
    return re.compile(pattern_str, re.IGNORECASE)


def filter_matching_lines(raw_text: str, pattern: re.Pattern, context_lines: int = 2) -> str:
    """
    Deterministic keyword pre-filter using regex.
    Returns only the lines that match any keyword, plus surrounding context lines.
    If no lines match, returns an empty string.
    """
    if not raw_text.strip():
        return ""

    lines = raw_text.splitlines()
    matched_indices = set()

    for i, line in enumerate(lines):
        if pattern.search(line):
            # Add this line and surrounding context
            for j in range(max(0, i - context_lines), min(len(lines), i + context_lines + 1)):
                matched_indices.add(j)

    if not matched_indices:
        return ""

    # Build output with the matched lines in order
    sorted_indices = sorted(matched_indices)
    result_lines = []
    prev_idx = -2
    for idx in sorted_indices:
        if idx > prev_idx + 1:
            result_lines.append("---")  # Visual separator between non-contiguous blocks
        result_lines.append(lines[idx])
        prev_idx = idx

    return '\n'.join(result_lines)


# Build the keyword regex once at startup
KEYWORD_PATTERN = build_keyword_pattern(
    CONFIG['target'].get('keywords', 'FATAL, ERROR, EXCEPTION, WARN')
)
CONTEXT_LINES = CONFIG['target'].get('context_lines', 2)
MAX_READ_BYTES = CONFIG['target'].get('max_read_bytes', 32768)


@tool
def check_log_file() -> str:
    """
    Triggers the system to read the latest lines from the log file.
    Use this tool to fetch new log entries for analysis.
    """
    return "fetch_logs"

class LogMonitorState(TypedDict):
    messages: List[Any]
    loop_count: int
    file_offset: int

def agent_node(state: LogMonitorState):
    """
    The Brain: Analyzes log content.
    """
    loop_n = state.get('loop_count', 1)
    offset = state.get('file_offset', 0)

    logging.info(f"\n\n--- 🤖 AGENT THINKING (Loop {loop_n} | Offset {offset}) ---")

    llm = ChatOllama(
        base_url=CONFIG['llm']['base_url'],
        model=CONFIG['llm']['model'],
        temperature=CONFIG['llm']['temperature']
    )
    llm_with_tools = llm.bind_tools([check_log_file])
    sys_msg = SystemMessage(content=CONFIG['system_prompt'].format(
        filepath=CONFIG['target']['logfile_path'],
        keywords=CONFIG['target'].get('keywords', 'FATAL, ERROR, EXCEPTION, WARN, exception, error, warn'),
        outcome_word=CONFIG['target'].get('outcome_word', 'TARGET_FOUND')
    ))
    incoming_messages = state.get('messages', [])
    last_msg = incoming_messages[-1] if incoming_messages else None
    messages_to_send = [sys_msg]
    if last_msg:
        messages_to_send.append(last_msg)

    response = llm_with_tools.invoke(messages_to_send)
    logging.info(f"\n[AGENT RESPONSE]: {response.content}")
    return {
        "messages": [response],
        "loop_count": loop_n + 1
    }

def tool_node(state: LogMonitorState):
    """
    The Executor: Handles smart file reading with offset tracking.
    Uses deterministic keyword pre-filtering before sending to LLM.
    """
    last_message = state['messages'][-1]
    current_offset = state.get('file_offset', 0)
    target_file = CONFIG['target']['logfile_path']

    if last_message.tool_calls:
        logging.info("\n--- 🛠️ READING LOG DELTA ---")
        tool_call = last_message.tool_calls[0]
        raw_content, new_offset = read_log_delta(target_file, current_offset, MAX_READ_BYTES)
        save_reanim_offset(new_offset)

        if not raw_content.strip():
            log_content = "No new log lines found since last check."
            logging.info("📄 No new content in log file.")
        else:
            total_lines = len(raw_content.splitlines())
            logging.info(f"📄 Read {total_lines} new lines. (Offset: {current_offset} -> {new_offset})")

            # ── Deterministic keyword pre-filtering ──
            filtered = filter_matching_lines(raw_content, KEYWORD_PATTERN, CONTEXT_LINES)

            if filtered:
                matched_count = sum(1 for line in filtered.splitlines() if line != '---' and KEYWORD_PATTERN.search(line))
                logging.info(f"🔍 Pre-filter: {matched_count} keyword matches found out of {total_lines} lines.")
                log_content = (
                    f"[PRE-FILTERED RESULTS] {matched_count} lines matched keywords "
                    f"({CONFIG['target'].get('keywords', '')}) out of {total_lines} total new lines.\n"
                    f"Below are the matching lines with surrounding context:\n\n{filtered}"
                )
            else:
                log_content = "No new log lines found since last check."
                logging.info(f"🔍 Pre-filter: 0 keyword matches out of {total_lines} lines. Skipping LLM analysis.")

        tool_message = ToolMessage(
            tool_call_id=tool_call['id'],
            name=tool_call['name'],
            content=log_content
        )

        interval = CONFIG['target']['poll_interval']
        logging.info(f"⏳ Sleeping {interval}s ...")
        time.sleep(interval)

        return {
            "messages": [tool_message],
            "file_offset": new_offset
        }

    return {"messages": []}

def router(state: LogMonitorState) -> Literal["tools", "__end__"]:
    last_message = state['messages'][-1]

    if last_message.tool_calls:
        return "tools"

    # Log event detection but do NOT stop — the outer loop continues forever.
    content = last_message.content.strip().upper()
    outcome_word = CONFIG['target'].get('outcome_word', 'TARGET_FOUND').strip().upper()
    if outcome_word in content:
        logging.critical("\n🚨🚨🚨 LOG EVENT DETECTED 🚨🚨🚨")
        logging.info(f"Analysis: {last_message.content}")

    # Always end this graph cycle; the outer while-loop in __main__ restarts it.
    return "__end__"

workflow = StateGraph(LogMonitorState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    router,
    {
        "tools": "tools",
        "__end__": END
    }
)
workflow.add_edge("tools", "agent")
app = workflow.compile()

# PID Management (Added for reliability)
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

if __name__ == "__main__":
    target_log = CONFIG['target']['logfile_path']

    if not os.path.exists(target_log):
        logging.warning(f"⚠️ Warning: {target_log} does not exist. Creating empty file...")
        with open(target_log, 'w') as f:
            f.write("")

    write_pid_file()
    if _IS_REANIMATED:
        logging.info(f"🔄 {CURRENT_DIR_NAME} REANIMATED (resuming from pause)")
        logging.info("=" * 60)

    try:
        logging.info(f"🔥 LOG MONITOR STARTED | File: {target_log}")
        logging.info(f"🔑 Keywords: {CONFIG['target'].get('keywords', 'N/A')} | Max read: {MAX_READ_BYTES} bytes | Context lines: {CONTEXT_LINES}")
        logging.info("----------------------------------------------------------------")

        current_offset = get_reanim_offset(target_log)
        loop_count = 1
        rec_limit = CONFIG['target'].get('recursion_limit', 1000)
        run_config = {"recursion_limit": rec_limit}

        # Outer infinite loop — runs until the process is killed (Ender agent, restart, or cleanup).
        while True:
            cycle_state = {
                "messages": [HumanMessage(content="Check the log file for new errors.")],
                "loop_count": loop_count,
                "file_offset": current_offset
            }
            result = app.invoke(cycle_state, config=run_config)
            current_offset = result.get('file_offset', current_offset)
            loop_count = result.get('loop_count', loop_count)

    except KeyboardInterrupt:
        logging.info("\n🛑 Monitor stopped (KeyboardInterrupt).")
    except Exception as e:
        logging.error(f"\n❌ PROGRAM STOPPED: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
