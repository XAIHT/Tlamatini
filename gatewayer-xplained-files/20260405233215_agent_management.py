
def get_python_command() -> list:
    """Determine Python executable to use."""
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    # Check PYTHON_HOME, bundled python, fallback to 'python'/'python3'

def get_user_python_home() -> str:
    """Get PYTHON_HOME from environment or Windows registry."""
    # Windows: reads HKCU\Environment\PYTHON_HOME
    # Unix: reads PYTHON_HOME env var

def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)

def get_agent_script_path(agent_name: str) -> str:
    """Find agent script, handling instance naming (e.g., agent_1)."""

def is_agent_running(agent_name: str) -> bool:
    """Check if agent is running via PID file and psutil."""

def wait_for_agents_to_stop(agents: list):
    """Block until all specified agents have stopped."""

def start_agent(agent_name: str):
    """Launch target agent as subprocess."""
