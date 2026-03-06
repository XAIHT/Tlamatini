import os
import sys

# FIX: Disable Intel Fortran runtime Ctrl+C handler to prevent "forrtl: error (200)"
os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import time
import yaml
import logging
import subprocess
import shlex
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

# Use directory name for log file (e.g., monitor_netstat_1 -> monitor_netstat_1.log)
CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"
logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)

def load_config(path="config.yaml"):
    try:
        with open(path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logging.error("❌ Error: config.yaml not found.")
        sys.exit(1)

CONFIG = load_config()

def run_netstat_command() -> str:
    """
    Executes 'netstat -an' and returns the output.
    """
    command = "netstat -an"
    try:
        # Simple execution for windows/linux generic
        # Utilizing shell=False with split command is safer but netstat is simple
        if sys.platform == "win32":
            # On Windows, netstat is straightforward
            result = subprocess.run(command, capture_output=True, text=True, shell=False)
        else:
            # On Unix-like
            result = subprocess.run(shlex.split(command), capture_output=True, text=True)
            
        if result.returncode != 0:
            return f"Error: Command '{command}' failed with return code {result.returncode}. Output: {result.stderr}"
        else:
            return result.stdout
    except Exception as e:
        return f"Error executing command '{command}': {e}"

@tool
def execute_netstat() -> str:
    """
    Execute a 'netstat -an' command to check active ports and connections.
    """
    return "run_netstat"

class NetstatMonitorState(TypedDict):
    messages: List[Any]
    loop_count: int

def agent_node(state: NetstatMonitorState):
    """
    The Brain: Analyzes netstat content.
    """
    loop_n = state.get('loop_count', 1)
    
    logging.info(f"\n\n--- 🤖 AGENT THINKING (Loop {loop_n}) ---")
    
    llm = ChatOllama(
        base_url=CONFIG['llm']['base_url'],
        model=CONFIG['llm']['model'],
        temperature=CONFIG['llm']['temperature']
    )
    llm_with_tools = llm.bind_tools([execute_netstat])
    
    # Format system prompt
    sys_msg = SystemMessage(content=CONFIG['system_prompt'].format(
        port=CONFIG['target']['port'],
        keywords=CONFIG['target'].get('keywords', 'ESTABLISHED'),
        outcome_word=CONFIG['target'].get('outcome_word', 'PORT_FOUND')
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

def tool_node(state: NetstatMonitorState):
    """
    The Executor: Handles netstat execution.
    """
    last_message = state['messages'][-1]
    
    if last_message.tool_calls:
        logging.info("\n--- 🛠️ EXECUTING NETSTAT ---")
        tool_call = last_message.tool_calls[0]
        
        # Execute actual logic
        full_output = run_netstat_command()
        
        # Filter output to prevent context overflow (fix for blocking issue)
        target_port = str(CONFIG['target']['port'])
        lines = full_output.splitlines()
        
        # Keep headers (usually first 4 lines in Windows/Linux netstat) and matching lines
        filtered_lines = [line for line in lines if target_port in line]
        
        if not filtered_lines:
            netstat_output = f"No active connections found for port {target_port}."
        else:
            # Add a header for context if matches found
            netstat_output = f"Netstat entries for port {target_port}:\n" + "\n".join(filtered_lines)
            
        logging.info(f"📄 Netstat executed. Filtered Output length: {len(netstat_output)} chars (Original: {len(full_output)}).")

        tool_message = ToolMessage(
            tool_call_id=tool_call['id'],
            name=tool_call['name'],
            content=netstat_output
        )
        
        interval = CONFIG['target']['poll_interval']
        logging.info(f"⏳ Sleeping {interval}s ...")
        time.sleep(interval)
        
        return {
            "messages": [tool_message]
        }
    
    return {"messages": []}

def refresh_loop_node(state: NetstatMonitorState):
    """
    Injects a trigger to keep the loop going if no target found yet.
    """
    logging.info("\n--- 🔄 REFRESHING LOOP ---")
    return {"messages": [HumanMessage(content="Check netstat again for the target port.")]}

def router(state: NetstatMonitorState) -> Literal["tools", "evaluate", "__end__"]:
    last_message = state['messages'][-1]
    
    if last_message.tool_calls:
        return "tools"
    
    content = last_message.content.strip().upper()
    outcome_word = CONFIG['target'].get('outcome_word', 'PORT_FOUND').upper()
    
    if outcome_word in content:
        logging.critical("\n🚨🚨🚨 PORT EVENT DETECTED 🚨🚨🚨")
        logging.info(f"Analysis: {last_message.content}")
        return "__end__"
    
    return "evaluate"

workflow = StateGraph(NetstatMonitorState)
workflow.add_node("agent", agent_node)
workflow.add_node("tools", tool_node)
workflow.add_node("refresh", refresh_loop_node)
workflow.add_edge(START, "agent")
workflow.add_conditional_edges(
    "agent",
    router,
    {
        "tools": "tools",
        "evaluate": "refresh", 
        "__end__": END
    }
)
workflow.add_edge("tools", "agent")
workflow.add_edge("refresh", "agent")
app = workflow.compile()

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
    logging.info("🔥 NETSTAT MONITOR STARTED")
    logging.info("----------------------------------------------------------------")
    
    # Write PID file immediately
    write_pid_file()
    
    port = CONFIG['target']['port']
    initial_state = {
        "messages": [HumanMessage(content=f"Start monitoring for port {port}.")],
        "loop_count": 1
    }
    rec_limit = CONFIG['target'].get('recursion_limit', 1000)
    run_config = {"recursion_limit": rec_limit}
    
    try:
        app.invoke(initial_state, config=run_config)
    except Exception as e:
        logging.error(f"\n❌ PROGRAM STOPPED: {e}")
    finally:
        # Keep LED green for 400ms for visual feedback
        time.sleep(0.4)
        remove_pid_file()
