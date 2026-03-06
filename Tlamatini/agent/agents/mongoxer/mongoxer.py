
import os
import sys
import logging
import yaml
import subprocess
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
