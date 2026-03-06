
import os
import sys
import logging
import yaml
import subprocess
import traceback
import pyodbc

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
    
    # Use directory name for log file (e.g., sqler_1 -> sqler_1.log)
    CURRENT_DIR_NAME = os.path.basename(agent_dir)
    LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        filename=LOG_FILE_PATH,
                        filemode='a',
                        encoding='utf-8')
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logging.getLogger().addHandler(console_handler)
    
    pid = os.getpid()
    with open('agent.pid', 'w') as f:
        f.write(str(pid))
        
    logging.info(f"🚀 Sqler Agent started with PID: {pid}")

    try:
        config = yaml.safe_load(open("config.yaml"))
        
        sql_config = config.get('sql_connection', {})
        driver = sql_config.get('driver', '{ODBC Driver 17 for SQL Server}')
        server = sql_config.get('server', 'localhost')
        database = sql_config.get('database', '')
        username = sql_config.get('username', '')
        password = sql_config.get('password', '')

        logging.info(f"Loaded config. Server: '{server}', Database: '{database}', Driver: '{driver}'")

        conn_str = f"DRIVER={driver};SERVER={server};DATABASE={database};"
        if username and password:
            conn_str += f"UID={username};PWD={password};"
        else:
            conn_str += "Trusted_Connection=yes;"

        logging.info("Connecting to SQL Server...")
        conn = pyodbc.connect(conn_str)
        cursor = conn.cursor()
        logging.info("Connected to SQL Server successfully.")
        
        script_to_execute = config.get('script')
        
        if script_to_execute:
            logging.info("Executing custom script...")
            try:
                # The script is executed in an environment that has 'cursor' and 'logging' available.
                exec_globals = {'cursor': cursor, 'logging': logging, 'conn': conn}
                exec(script_to_execute, exec_globals)
                conn.commit()
                logging.info("✅ Script executed successfully.")
            except Exception as e:
                logging.error(f"❌ Error executing script: {e}")
                logging.error(traceback.format_exc())
                conn.rollback()
        
        cursor.close()
        conn.close()

        target_agents = config.get('target_agents', [])
        if target_agents:
            logging.info(f"Starting {len(target_agents)} dependent target agent(s)...")
        for target_agent_name in target_agents:
            logging.info(f"--> Starting target agent: {target_agent_name}")
            start_agent(target_agent_name, target_agent_name)
            
    except Exception as e:
        logging.error(f"❌ An error occurred: {e}")
        logging.error(traceback.format_exc())
    finally:
        if os.path.exists('agent.pid'):
            os.remove('agent.pid')
        logging.info("🛑 Sqler Agent stopped.")

if __name__ == "__main__":
    main()
