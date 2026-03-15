
import os
import sys
import logging
import yaml
import subprocess
import time
from pymongo import MongoClient
import traceback

def get_agent_env(agent_name, pool_dir_name):
    agent_dir = os.path.dirname(os.path.realpath(__file__))
    
    new_env = os.environ.copy()
    new_env['PYTHON_HOME'] = f"{agent_dir};{os.path.join(agent_dir, '..')}"
    new_env['POOL_DIR_NAME'] = pool_dir_name
    return new_env

def start_agent(agent_name, pool_dir_name):
    agent_dir = os.path.dirname(os.path.realpath(__file__))
    agent_script_path = os.path.join(agent_dir, '..', agent_name, f'{agent_name}.py')
    
    py_executable = sys.executable
    
    new_env = get_agent_env(agent_name, pool_dir_name)

    # Use CREATE_NEW_CONSOLE for Windows to run the agent in a new console window
    creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
    
    subprocess.Popen([py_executable, agent_script_path], env=new_env, creationflags=creationflags)


def is_agent_running(agent_name: str) -> bool:
    """Check if an agent is currently running by verifying its PID file and process."""
    agent_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), '..', agent_name)
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
    """
    Wait until ALL specified agents have stopped running.
    Logs ERROR every 10 seconds while waiting. Never proceeds until all have stopped.
    """
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


def main():
    os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'
    
    agent_dir = os.path.dirname(os.path.realpath(__file__))
    os.chdir(agent_dir)
    
    pool_dir_name = os.environ.get('POOL_DIR_NAME', agent_dir)

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        filename=f'{pool_dir_name}.log',
                        filemode='a')
    
    pid = os.getpid()
    with open('agent.pid', 'w') as f:
        f.write(str(pid))
        
    logging.info(f"Agent started with PID: {pid}")

    try:
        config = yaml.safe_load(open("config.yaml"))
        
        mongo_config = config.get('mongo_connection', {})
        
        login = mongo_config.get('login', '')
        password = mongo_config.get('password', '')
        client_kwargs = {}
        if login and password:
            client_kwargs['username'] = login
            client_kwargs['password'] = password
            
        client = MongoClient(mongo_config.get('connection_string'), **client_kwargs)
        db = client[mongo_config.get('database')]
        
        script_to_execute = config.get('script')
        
        if script_to_execute:
            logging.info(f"Executing script: {script_to_execute}")
            try:
                # The script is executed in an environment that has 'db' and 'logging' available.
                exec_globals = {'db': db, 'logging': logging}
                exec(script_to_execute, exec_globals)
                logging.info("Script executed successfully.")
            except Exception as e:
                logging.error(f"Error executing script: {e}")
                logging.error(traceback.format_exc())
        
        client.close()

        target_agents = config.get('target_agents', [])
        if target_agents:
            wait_for_agents_to_stop(target_agents)
        for agent_name in target_agents:
            start_agent(agent_name, pool_dir_name)
            
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        logging.error(traceback.format_exc())
    finally:
        if os.path.exists('agent.pid'):
            os.remove('agent.pid')
        logging.info("Agent stopped.")

if __name__ == "__main__":
    main()
