from datetime import datetime
from langchain.tools import tool
import os
import sys
import subprocess
import threading
import pathlib
import webbrowser
import shlex
import signal
import psutil
from .imaging.image_interpreter import opus_analyze_image, qwen_analyze_image
from .global_state import global_state
from .models import Agent, AgentProcess
import zipfile
from .path_guard import validate_tool_path


def launch_in_new_terminal(script_pathfilename, arguments=None):
    script_path = os.path.normpath(script_pathfilename)
    # Use PYTHON_HOME env var to resolve the Python interpreter
    python_home = os.environ.get('PYTHON_HOME', '')
    if python_home and os.path.isfile(os.path.join(python_home, 'python.exe')):
        python_exe = os.path.join(python_home, 'python.exe')
    elif getattr(sys, 'frozen', False):
        python_exe = "python"
    else:
        python_exe = sys.executable

    clean_path = script_path.strip('"')
    quoted_path = f'"{clean_path}"'
    
    if ' ' in python_exe and not python_exe.startswith('"'):
        python_exe = f'"{python_exe}"'
    
    if arguments and arguments.strip():
        cmd_args = f'{quoted_path} {arguments}'
    else:
        cmd_args = f'{quoted_path}'
    
    full_command = f'start "Tlamatini Console" cmd /k {python_exe} {cmd_args}'
    subprocess.Popen(full_command, shell=True)

def _resolve_script_path(script_path):
    """Resolve script path, checking CWD and frozen/executable directory."""
    if os.path.exists(script_path):
        return script_path
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        frozen_path = os.path.join(exe_dir, script_path)
        if os.path.exists(frozen_path):
            return frozen_path
    return None

def get_all_agents():
    """Return all Agent records (name, content) as list of dicts."""
    return list(Agent.objects.values('agentName', 'agentDescription', 'agentContent'))

def get_all_agent_processes():
    """Return all AgentProcess records (name, content) as list of dicts."""
    return list(AgentProcess.objects.values('agentProcessDescription', 'agentProcessPid'))

def save_agent_process(agentProcessDescription, agentProcessPid):
    AgentProcess.objects.filter(agentProcessPid=agentProcessPid).delete()
    AgentProcess.objects.create(agentProcessDescription=agentProcessDescription, agentProcessPid=agentProcessPid)

def get_agent_process_by_pid(pid):
    try:
        return AgentProcess.objects.get(agentProcessPid=pid)
    except AgentProcess.DoesNotExist:
        return None

def delete_agent_process_by_pid(pid):
    AgentProcess.objects.filter(agentProcessPid=pid).delete()

def get_agent_process_by_description(description):
    try:
        return AgentProcess.objects.get(agentProcessDescription=description)
    except AgentProcess.DoesNotExist:
        return None

def delete_agent_process_by_description(description):
    AgentProcess.objects.filter(agentProcessDescription=description).delete()

@tool
def get_current_time() -> str:
    """
    Returns the current date and time in ISO format.
    Use this tool whenever the user asks for the current time, date, or day.
    """
    return datetime.now().isoformat()

@tool
def execute_file(command: str) -> str:
    """
    Open a new forked terminal window to execute a Python script with optional arguments.
    
    CRITICAL: Pass the COMPLETE command exactly as the user specified, including all arguments.
    
    Examples of what to pass:
    - User says "Run whatever.py located at desktop" → Check the 'Files Context' (if available) to see if 'whatever.py' was found. If yes, pass the full path found.
    - User says "Run the sccript whatever.py located at u:\\path" → Pass the provided path and filename like this: "u:\\path\\whatever.py".
    - User says "Execute the sccript whatever.py located at u:\\path" → Pass the provided path and filename like this: "u:\\path\\whatever.py".
    - User says "Execute manage.py collectstatic" → pass "manage.py collectstatic"
    - User says "Run C:\\Users\\Downloads\\cat_art.py" → pass "C:\\Users\\Downloads\\cat_art.py"
    - User says "Execute ./scripts/test.py --verbose" → pass "./scripts/test.py --verbose"
    - User says "Run python manage.py migrate" → pass "manage.py migrate" (omit python, it's added automatically)
    - If under your process to answer the user you need the execution of a python script that is in certain directory you MUST pass the filename with its complete path.
    
    Input:
    - command: The complete command string including the script path AND any arguments/parameters
               (e.g., "manage.py collectstatic", "C:\\path\\script.py --arg value", "myscript.py")
    
    The script will be launched in a new terminal window.
    """
    try:
        if not command or command.strip() == "":
            return "Error: No command provided. Please specify the Python file and any arguments."
        
        parts = command.strip().split(None, 1)  # Split on first whitespace
        script_path_raw = parts[0]
        arguments = parts[1] if len(parts) > 1 else None
        script_path = _resolve_script_path(script_path_raw)
        if not script_path:
            return f"Error: Script '{script_path_raw}' does not exist. Please provide a valid file path."
        # ── Path guard: validate resolved script path ──
        rejection = validate_tool_path(os.path.abspath(script_path))
        if rejection:
            return rejection
        launch_in_new_terminal(script_path, arguments)
        return f"Command '{command}' executed successfully in a new terminal window."
    except Exception as e:
        return f"Error executing command '{command}': {e}"

@tool
def execute_command(command: str) -> str:
    """
    Execute a command in the current terminal window, exclusively for commands that cannot be executed by the execute_file tool.    

    CRITICAL: Pass the COMPLETE command exactly as the user specified, including all arguments.
    
    Examples of what to pass:
    - User asks 'Execute command dir *.log' →You MUST pass 'dir *.log'.
    - User asks 'Execute command echo "Hello, World!"' → You MUST pass 'echo "Hello, World!"'.
    - User asks 'Execute command python manage.py migrate' → You MUST pass 'python manage.py migrate'.
    - User asks 'Run command dir *.log' → You MUST pass 'dir *.log'.
    - User asks 'Run command echo "Hello, World!"' → You MUST pass 'echo "Hello, World!"'.
    - User asks 'Run command python manage.py migrate' → You MUST pass 'python manage.py migrate'.
    - If under your process to answer the user you need the execution of a command that is in certain directory you MUST pass the command with its complete path.
    
    Input:
    - command: The complete command string to execute
               (e.g., "ls -la", "echo 'Hello, World!'", "python myscript.py", "netstat -an", "ipconfig", "ping 8.8.8.8')
    """
    try:
        if not command or command.strip() == "":
            return "Error: No command provided. Please specify the command to execute."
        
        # ── Path guard: validate any path-like tokens in the command ──
        try:
            tokens = shlex.split(command)
        except ValueError:
            tokens = command.split()
        for token in tokens:
            # Skip tokens that don't look like filesystem paths
            if not any(ch in token for ch in ('\\', '/', ':')):
                continue
            # Skip drive-letter-only tokens like "C:" or protocol URIs
            if len(token) <= 2:
                continue
            resolved_token = os.path.abspath(token)
            if os.path.exists(resolved_token) or os.path.exists(os.path.dirname(resolved_token)):
                rejection = validate_tool_path(resolved_token)
                if rejection:
                    return rejection

        try:
            cmd_list = shlex.split(command)
            result = subprocess.run(cmd_list, capture_output=True, text=True, shell=False)
        except ValueError:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error: Command '{command}' failed with return code {result.returncode}. Output: {result.stderr}"
        else:
            return f"Command '{command}' executed successfully. Output: {result.stdout}"
    except Exception as e:
        return f"Error executing command '{command}': {e}"

@tool
def execute_netstat() -> str:
    """
    Execute a 'netstat -an' command in the current terminal window, exclusively for 'netstat' that cannot be executed by the execute_file tool.    

    Examples of what to pass:
    - User asks 'Execute netstat' →You MUST execute this tool with no arguments.
    - User asks 'Run netstat' → You MUST execute this tool with no arguments.   
    - If under your process to answer the user you need the detection of certain port status you MUST execute this tool and search for the port number in the output.
    
    """
    try:
        command = "netstat -an"
        try:
            cmd_list = shlex.split(command)
            result = subprocess.run(cmd_list, capture_output=True, text=True, shell=False)
        except ValueError:
            result = subprocess.run(command, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            return f"Error: Command '{command}' failed with return code {result.returncode}. Output: {result.stderr}"
        else:
            return f"Command '{command}' executed successfully. Output: {result.stdout}"
    except Exception as e:
        return f"Error executing command '{command}': {e}"

@tool
def execute_agent(agent_name: str) -> str:
    """
    Start the execution of an agent by name.
    
    CRITICAL: Pass the COMPLETE agent name exactly as the user specified.
    
    Examples of what to pass:
    - User says "Start agent Agent-Name" → Pass "Agent-Name".
    - User says "Execute agent Agent-Name" → Pass "Agent-Name".
    - User says "Run agent Agent-Name" → Pass "Agent-Name".
    - User says "Re-start agent Agent-Name" → Pass "Agent-Name".
    - User says "Re-execute agent Agent-Name" → Pass "Agent-Name".
    - User says "Re-run agent Agent-Name" → Pass "Agent-Name".
    
    Input:
    - agent_name: The complete agent name to execute
               (e.g., "Agent-Name")
    
    The agent will be launched as a secon plane process.
    """
    foundAgent = False
    agentDescription = ""
    agents = get_all_agents()
    for agent in agents:
        agentDescription = agent['agentDescription']
        if agentDescription == agent_name:
            print(f"Agent to be executed found: {agentDescription}")
            foundAgent = True
            break
    
    if not foundAgent:
        return f"Agent '{agent_name}' not found."
    
    application_path = ""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))

    agentDir = os.path.join(application_path, 'agents', agentDescription.lower().replace("-", "_"))
    
    if not os.path.exists(agentDir):
        return f"Agent '{agentDescription}' not found in directory: {agentDir}."

    agentScript = agentDescription.lower().replace("-", "_") + ".py"
    agentScript = os.path.join(agentDir, agentScript)
    if not os.path.exists(agentScript):
        return f"Agent '{agentDescription}' script not found in directory: {agentScript}."

    # Use the Python interpreter from PYTHON_HOME user environment variable
    python_home = os.environ.get('PYTHON_HOME', '')
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe')
        if not os.path.isfile(python_exe):
            return f"PYTHON_HOME is set to '{python_home}' but python.exe not found there."
    else:
        python_exe = 'python'

    agentCommand = f'"{python_exe}" "{agentScript}"'
    agentProcess = subprocess.Popen(agentCommand)
    save_agent_process(agentDescription, agentProcess.pid)
    returnString = f"Agent '{agentDescription}' started successfully with process ID: {agentProcess.pid}."
    return returnString

@tool
def stop_agent(agent_name: str) -> str:
    """
    Stop the execution of an agent by name.
    
    CRITICAL: Pass the COMPLETE agent name exactly as the user specified.
    
    Examples of what to pass:
    - User says "Stop agent Agent-Name" → Pass "Agent-Name".
    - User says "Kill agent Agent-Name" → Pass "Agent-Name".
    - User says "Terminate agent Agent-Name" → Pass "Agent-Name".
    - User says "Stop again agent Agent-Name" → Pass "Agent-Name".
    - User says "Kill again agent Agent-Name" → Pass "Agent-Name".
    - User says "Terminate again agent Agent-Name" → Pass "Agent-Name".
    - If under your process to answer the user you need to stop an agent that is in certain directory you MUST pass the agent name with its complete path.

    
    Input:
    - agent_name: The complete agent name to stop
               (e.g., "Agent-Name")
    
    The agent will be terminated.
    """
    foundAgent = False
    agentProcessDescription = ""
    returnString = ""
    agents = get_all_agents()
    for agent in agents:
        agentProcessDescription = agent['agentDescription']
        if agentProcessDescription == agent_name:
            print(f"Agent to look for: {agentProcessDescription}")
            foundAgent = True
            break
    if not foundAgent:
        returnString = f"Agent '{agent_name}': NAME IS NOT Valid!."
        return returnString
    
    agentProcess = get_agent_process_by_description(agentProcessDescription)
    if agentProcess:
        print(f"--- Getting status of agent {agent_name}, with Pid: {agentProcess.agentProcessPid} from OS...")
        try:
            process = psutil.Process(agentProcess.agentProcessPid)
            processStatus = process.status()
            if processStatus == psutil.STATUS_RUNNING or processStatus == psutil.STATUS_SLEEPING or processStatus == psutil.STATUS_STOPPED:
                print(f"Sending Kill to agent '{agentProcessDescription}' with process ID: {agentProcess.agentProcessPid}...")
                processPid = int(agentProcess.agentProcessPid)
                os.kill(processPid, signal.SIGTERM)
                delete_agent_process_by_description(agentProcess.agentProcessDescription)
                returnString = f"Agent '{agentProcessDescription}' WAS Stopped successfully with process ID: {agentProcess.agentProcessPid}."
            else:
                returnString = f"Agent '{agentProcessDescription}' WAS NOT Stopped, its state is invalid: {processStatus}."
        except psutil.NoSuchProcess:
            returnString = f"Agent '{agentProcessDescription}' WAS NOT running."
            return returnString
        except psutil.AccessDenied:
            returnString = f"Agent '{agent_name}' WAS NOT stopped,FORBIDDEN TO KILL IT!, with process ID: [{agentProcess.agentProcessPid}]."
            return returnString
        except Exception:
            returnString = f"Agent '{agentProcessDescription}' WAS NOT stopped, KILL FAILED!, with process ID: {agentProcess.agentProcessPid}."
            return returnString
    else:
        returnString = f"Agent '{agentProcessDescription}' WAS NOT stopped, NOT FOUND!."
    return returnString

@tool
def agent_status(agent_name: str) -> str:
    """
    Get the execution status of the process related to the agent provided name.
    
    CRITICAL: Pass the COMPLETE agent name exactly as the user specified.
    
    Examples of what to pass:
    - User says "Get agent Agent-Name status" → Pass "Agent-Name".
    - User says "Get agent Agent-Name status again" → Pass "Agent-Name".
    - If under your process to answer the user you need to get the status of an agent that is in certain directory you MUST pass the agent name with its complete path.    
    
    Input:
    - agent_name: The complete agent name to get status
               (e.g., "Agent-Name")
    
    The status of the process pid related to the agent will be returned.
    """
    foundAgent = False
    agentProcessDescription = ""
    returnString = ""
    agents = get_all_agents()
    for agent in agents:
        agentProcessDescription = agent['agentDescription']
        if agentProcessDescription == agent_name:
            print(f"Agent to look for: {agentProcessDescription}")
            foundAgent = True
            break
    if not foundAgent:
        returnString = f"Agent '{agent_name}': NAME IS NOT Valid!."
        return returnString
    
    agentProcess = get_agent_process_by_description(agentProcessDescription)
    if agentProcess:
        print(f"--- Getting status of agent {agent_name}, with Pid: {agentProcess.agentProcessPid} from OS...")
        try:
            process = psutil.Process(agentProcess.agentProcessPid)
            processStatus = process.status()
            if processStatus == psutil.STATUS_RUNNING:
                returnString = f"Agent '{agentProcessDescription}' STATUS: IS RUNNING with process ID: {agentProcess.agentProcessPid}."
            elif processStatus == psutil.STATUS_SLEEPING:
                returnString = f"Agent '{agentProcessDescription}' STATUS: IS SLEEPING with process ID: {agentProcess.agentProcessPid}."
            elif processStatus == psutil.STATUS_STOPPED:
                returnString = f"Agent '{agentProcessDescription}' STATUS: IS STOPPED with process ID: {agentProcess.agentProcessPid}."
            else:
                returnString = f"Agent '{agentProcessDescription}' STATUS: HAS AN UNKNOWN STATUS with process ID: {agentProcess.agentProcessPid} and status: {processStatus}."
        except psutil.NoSuchProcess:
            returnString = f"Agent '{agentProcessDescription}' STATUS: IS NOT running."
            return returnString
        except psutil.AccessDenied:
            returnString = f"Agent '{agent_name}' STATUS: FORBIDDEN TO GET ITS STATUS with process ID: [{agentProcess.agentProcessPid}]."
            return returnString
        except Exception:
            returnString = f"Agent '{agentProcessDescription}' STATUS: UNKNOWN STATUS with process ID: {agentProcess.agentProcessPid}."
            return returnString
    else:
        returnString = f"Agent '{agent_name}' STATUS CAN NOT BE DETERMINED (Process not currently running)."
    return returnString

@tool
def launch_view_image(path_filename: str) -> str:
    """
    Open a new forked window to show the provided image with its path-filename, which its path can be relative to the current working directory or absolute,

    **CRITICAL: If the user prompt begins with "View image" or "Show image" or "View the image" or "Show the image", you MUST use THIS TOOL.**

    Examples of what to pass:
    - User says "View image whatever.jpg located at desktop" → Check the 'Files Context' (if available) to see if 'whatever.jpg' was found. If yes, pass the full path found.
    - User says "View image agent.jpg" → pass only the image name (agent.jpg).
    - User says "View image whatever.jpg" located at U:\\path\\to → pass the complete path-filename (U:\\path\\to\\whatever.jpg).
    - User says "Show me the image path\\agent.jpg" → pass the complete path of the image (path\\agent.jpg).
    - User says "Show the image <image_name> located at <path>" → pass the <path>\\<image_name>.
    - User says "View the image cat.gif" → pass only the image name (cat.gif).
    - User says "Show image whatever.jpg located at Downloads" → **You MUST Use FileSearchRAGChain** if you need to find the exact location of the file (prompt: find the file whatever.jpg in Downloads) and pass the complete path-filename to the tool.
    - User says "View image whatever.jpg located at Downloads" → **You MUST Use FileSearchRAGChain** if you need to find the exact location of the file (prompt: find the file whatever.jpg in Downloads) and pass the complete path-filename to the tool.
    - If under your process to answer the user you need to show an image that is in certain directory you MUST pass the image name with its complete path.

    Input:
    - path_filename: The path and the filename of the image to show, if there is only a filename and not its path you should assume the file is in the current directory.
       (e.g., "barbie.jpg", "c:\\Downloads\\Ken.svg", ...)
    
    A new window is opened that will not block the main thread
    """
    try:
        if not path_filename or not path_filename.strip():
            print(" --- Error: No image path provided.")
            return "Error: No image path provided."

        raw = path_filename.strip().strip('"').strip("'")
        expanded = os.path.expandvars(os.path.expanduser(raw))
        resolved = os.path.abspath(expanded)

        # ── Path guard: validate resolved image path ──
        rejection = validate_tool_path(resolved)
        if rejection:
            return rejection

        if not os.path.exists(resolved):
            print(f" --- Error: File '{path_filename}' not found at '{resolved}'.")
            return f"Error: File '{path_filename}' not found at '{resolved}'."

        def _open_image(p: str):
            try:
                if sys.platform.startswith('win'):
                    try:
                        print(" --- Opening Image with: os.startfile(...)...")
                        os.startfile(p)
                        return
                    except Exception as ex:
                        print(f"--- Exception: {ex} while starting the opening of image file (os.startfile(...)).")
                    try:
                        print(" --- Opening Image with: cmd = f'start ...")
                        cmd = f'start "" "{p}"'
                        subprocess.Popen(cmd, shell=True)
                        return
                    except Exception as ex:
                        print(f" --- Exception {ex} while starting the opening of image file (subprocess.Popen(cmd, shell=True)).")
                    try:
                        print(" --- Opening Image with: PowerShell Start-Process ...")
                        subprocess.Popen([
                            'powershell', '-NoProfile', '-Command', f'Start-Process -FilePath "{p}"'
                        ])
                        return
                    except Exception as ex:
                        print(f" --- Exception {ex} while starting the opening of image file (subprocess.Popen([...(1)")
                else:
                    opener = 'open' if sys.platform == 'darwin' else 'xdg-open'
                    try:
                        print(" --- Opening Image with: subprocess.Popen([opener, p])...")
                        subprocess.Popen([opener, p])
                        return
                    except Exception as ex:
                        print(f" --- Exception {ex} while starting the opening of image file (subprocess.Popen([...(2)")
                try:
                    print(" --- Opening Image with: webbrowser.open(...)...")
                    webbrowser.open(pathlib.Path(p).resolve().as_uri(), new=2)
                except Exception as ex:
                    print(f" --- Exception {ex} while starting the opening of image file (webbrowser.open(...)")
            except Exception as ex:
                print(f" --- General Exception error {ex} in launch_view_image(...)!!!.")

        threading.Thread(target=_open_image, args=(resolved,), daemon=True).start()
        print(f"Image '{path_filename}' has been opened in a new window.")
        return f"Image '{path_filename}' has been opened in a new window."
    except Exception as e:
        print(f"Error opening image '{path_filename}': {e}")
        return f"Error opening image '{path_filename}': {e}"

@tool
def unzip_file(path_filename: str) -> str:
    """
    Unzip a file into a subdirectory with the same name as the zip file.
    
    CRITICAL: Pass the COMPLETE path of the file to unzip.
    
    Examples of what to pass:
    - User asks 'Unzip file C:\\Users\\Downloads\\file.zip' → You MUST pass 'C:\\Users\\Downloads\\file.zip'.
    - User asks 'Unzip file file.zip' → You MUST pass 'file.zip'.
    - If under your process to answer the user you need the decompression of a ZIP file that is in certain directory you MUST pass the filename with its complete path, the files decompressed will be in a subdirectory with the same name of the ZIP file.
    """
    try:
        # Resolve to absolute path to handle relative paths correctly in frozen/non-frozen mode
        abs_path = os.path.abspath(path_filename)
        
        # ── Path guard: validate zip file path ──
        rejection = validate_tool_path(abs_path)
        if rejection:
            return rejection

        # Validate input file exists
        if not os.path.exists(abs_path):
            return f"Error: File '{path_filename}' does not exist."
        
        # Validate file extension
        file_ext = os.path.splitext(abs_path)[1].lower()
        if file_ext != '.zip':
            return f"Error: File '{path_filename}' is not a ZIP file. Expected .zip extension."
        
        # Create destination directory with zip file's name (without extension)
        zip_basename = os.path.splitext(os.path.basename(abs_path))[0]
        dest_dir = os.path.join(os.path.dirname(abs_path), zip_basename)
        
        # Create destination directory if it doesn't exist
        os.makedirs(dest_dir, exist_ok=True)
        
        with zipfile.ZipFile(abs_path, 'r') as zip_ref:
            zip_ref.extractall(dest_dir)
        return f"File '{path_filename}' has been unzipped to '{dest_dir}'."
    except Exception as e:
        return f"Error unzipping file '{path_filename}': {e}"

@tool
def decompile_java(path_filename: str) -> str:
    """
    Decompile a JAR or WAR file into Java source code.
    
    CRITICAL: Pass the COMPLETE path of the JAR/WAR file to decompile.
    
    Examples of what to pass:
    - User asks 'Decompile file C:\\Users\\Downloads\\app.jar' → You MUST pass 'C:\\Users\\Downloads\\app.jar'.
    - User asks 'Decompile app.war' → You MUST pass 'app.war'.
    - User asks 'Decompile Java file mylib.jar' → You MUST pass 'mylib.jar'.
    - If under your process to answer the user you need the decompilation of a JAR/WAR file that is in certain directory you MUST pass the filename with its complete path, the decompiled files will be in a subdirectory with the same name of the JAR/WAR file.
    """
    try:
        # Validate input file exists
        if not os.path.exists(path_filename):
            return f"Error: File '{path_filename}' does not exist."
        
        # ── Path guard: validate JAR/WAR file path ──
        rejection = validate_tool_path(os.path.abspath(path_filename))
        if rejection:
            return rejection

        # Validate file extension
        file_ext = os.path.splitext(path_filename)[1].lower()
        if file_ext not in ['.jar', '.war']:
            return f"Error: File '{path_filename}' is not a JAR or WAR file. Expected .jar or .war extension."
        
        # Create destination directory with file's name (without extension)
        file_basename = os.path.splitext(os.path.basename(path_filename))[0]
        dest_dir = os.path.join(os.path.dirname(path_filename), file_basename)
        
        # Determine jd-cli directory based on frozen or non-frozen mode
        if getattr(sys, 'frozen', False):
            # Frozen mode (PyInstaller): jd-cli is relative to the executable
            application_path = os.path.dirname(sys.executable)
        else:
            # Development mode: jd-cli is in Tlamatini/Tlamatini/jd-cli
            # tools.py is in Tlamatini/Tlamatini/agent/tools.py
            application_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        jd_cli_dir = os.path.join(application_path, 'jd-cli')
        jd_cli_bat = os.path.join(jd_cli_dir, 'jd-cli.bat')
        
        # Validate jd-cli.bat exists
        if not os.path.exists(jd_cli_bat):
            return f"Error: jd-cli.bat not found at '{jd_cli_bat}'. Please ensure jd-cli is properly installed."
        
        # Create destination directory if it doesn't exist
        os.makedirs(dest_dir, exist_ok=True)
        
        # Run jd-cli.bat to decompile
        # Command: jd-cli.bat <input_file> <output_dir>
        # Note: We use shell=True to execute the batch file properly on Windows
        cmd = [
            jd_cli_bat,
            path_filename,
            dest_dir
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=jd_cli_dir, shell=True)
        
        if result.returncode != 0:
            error_msg = result.stderr if result.stderr else result.stdout
            return f"Error decompiling '{path_filename}': {error_msg}"
        
        return f"File '{path_filename}' has been decompiled to '{dest_dir}'."
    except Exception as e:
        return f"Error decompiling file '{path_filename}': {e}"


def get_mcp_tools():
    """
    Returns a list of all tools available to the MCP.
    NOTE: File operations (read_file, list_files, search_files) are handled by FileSearchRAGChain,
    not by any of the tools below. The unified agent should rely on the context provided by FileSearchRAGChain.
    """

    tools = []
    if global_state.get_state('tool_current-time_status', 'enabled') == 'enabled': 
        tools.append(get_current_time)
    if global_state.get_state('tool_execute-file_status', 'enabled') == 'enabled': 
        tools.append(execute_file)
    if global_state.get_state('tool_execute-command_status', 'enabled') == 'enabled': 
        tools.append(execute_command)
    if global_state.get_state('tool_view-image_status', 'enabled') == 'enabled': 
        tools.append(launch_view_image)
    if global_state.get_state('tool_opus-analyze-image_status', 'enabled') == 'enabled': 
        tools.append(opus_analyze_image)
    if global_state.get_state('tool_qwen-analyze-image_status', 'enabled') == 'enabled': 
        tools.append(qwen_analyze_image)
    if global_state.get_state('tool_execute-agent_status', 'enabled') == 'enabled': 
        tools.append(execute_agent)
    if global_state.get_state('tool_stop-agent_status', 'enabled') == 'enabled': 
        tools.append(stop_agent)
    if global_state.get_state('tool_agent-status_status', 'enabled') == 'enabled': 
        tools.append(agent_status)
    if global_state.get_state('tool_execute-netstat_status', 'enabled') == 'enabled': 
        tools.append(execute_netstat)
    if global_state.get_state('tool_unzip-file_status', 'enabled') == 'enabled': 
        tools.append(unzip_file)
    if global_state.get_state('tool_decompile-java_status', 'enabled') == 'enabled': 
        tools.append(decompile_java)
    return tools
