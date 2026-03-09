from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from .models import AgentMessage
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
import json
import os
import sys
from typing import Optional
from .models import LLMProgram, LLMSnippet, Prompt, Omission, Mcp, Tool, Agent, SessionState
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import shutil
import psutil
import traceback
import yaml
import subprocess
import time

def home(request):
    return HttpResponse("Hello, World!")

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                # --- .FLW File Association Support ---
                # If a .flw file was passed on the command line (frozen mode),
                # redirect straight to the Agentic Control Panel instead of welcome.
                # Only check this in frozen mode to avoid stale env vars from previous runs.
                flw_file = os.environ.get('SYSTEMAGENT_FLW_FILE') if getattr(sys, 'frozen', False) else None
                if flw_file:
                    print(f"--- [FLW] Login success, redirecting to agentic_control_panel with flow: {flw_file}")
                    return redirect('agentic_control_panel')
                return redirect('welcome')
    else:
        form = AuthenticationForm()
    return render(request, 'agent/login.html', {'form': form})

@login_required
def welcome_view(request):
    return render(request, 'agent/welcome.html')

def logout_view(request):
    logout(request)
    return redirect('home')

@login_required
def agent_page(request):
    messages = AgentMessage.objects.order_by('timestamp').all()
    initial_messages = [
        {
            'username': m.user.username,
            'message': m.message,
            'timestamp': m.timestamp.strftime('%Y/%m/%d %H:%M:%S.%f')[:-3] if m.timestamp else '',
        }
        for m in messages
    ]

    # Load ollama_base_url from config.json
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    ollama_base_url = 'http://localhost:11434'  # default fallback
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            ollama_base_url = config.get('ollama_base_url', ollama_base_url)
    except Exception as e:
        print(f"Warning: Could not load ollama_base_url from config.json: {e}")

    return render(request, 'agent/agent_page.html', {
        'initial_messages': initial_messages,
        'ollama_base_url': ollama_base_url,
    })

def load_canvas_view(request, filename):
    try:
        program = LLMProgram.objects.get(programName=filename)
        content = program.programContent
        return HttpResponse(content, content_type="text/plain")
    except LLMProgram.DoesNotExist:
        pass  # Try LLMSnippet if not found in LLMProgram

    try:
        snippet = LLMSnippet.objects.get(snippetName=filename)
        content = snippet.snippetContent
        return HttpResponse(content, content_type="text/plain")
    except LLMSnippet.DoesNotExist:
        return HttpResponse("File not found in database", status=404)
    
def load_prompt_view(request, prompt_name):
    try:
        prompt = Prompt.objects.get(promptName=prompt_name)
        content = prompt.promptContent
        return HttpResponse(content, content_type="text/plain")
    except Prompt.DoesNotExist:
        return HttpResponse("Prompt not found in database", status=404)

def load_omissions_view(request, omission_name):
    try:
        omissions = Omission.objects.get(omissionName=omission_name)
        content = omissions.omissionContent
        return HttpResponse(content, content_type="text/plain")
    except Omission.DoesNotExist:
        return HttpResponse("Omission not found in database", status=404)

def load_mcp_view(request, mcp_name):
    try:
        mcp = Mcp.objects.get(mcpName=mcp_name)
        content = mcp.mcpContent
        return HttpResponse(content, content_type="text/plain")
    except Mcp.DoesNotExist:
        return HttpResponse("Mcp not found in database", status=404)

def load_tool_view(request, tool_name):
    try:
        tool = Tool.objects.get(toolName=tool_name)
        content = tool.toolContent
        return HttpResponse(content, content_type="text/plain")
    except Tool.DoesNotExist:
        return HttpResponse("Tool not found in database", status=404)

def load_agent_view(request, agent_name):
    try:
        agent = Agent.objects.get(agentName=agent_name)
        content = agent.agentContent
        return HttpResponse(content, content_type="text/plain")
    except Agent.DoesNotExist:
        return HttpResponse("Agent not found in database", status=404)

def load_agent_description_view(request, agent_name):
    try:
        agent = Agent.objects.get(agentName=agent_name)
        content = agent.agentDescription
        return HttpResponse(content, content_type="text/plain")
    except Agent.DoesNotExist:
        return HttpResponse("Agent not found in database", status=404)

@login_required
def agentic_control_panel(request):
    # Load ollama_base_url from config.json
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    ollama_base_url = 'http://localhost:11434'  # default fallback
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            ollama_base_url = config.get('ollama_base_url', ollama_base_url)
    except Exception as e:
        print(f"Warning: Could not load ollama_base_url from config.json: {e}")

    context = {
        'ollama_base_url': ollama_base_url,
    }

    # --- .FLW File Association Support ---
    # If a .flw file was passed via command line (frozen mode), read it
    # and inject the JSON data into the template context so the JS can auto-load it.
    # IMPORTANT: Only honour the env var when running as a frozen executable.
    # In development (non-frozen) mode, a stale env var from a previous run
    # must NOT cause auto-open of a .flw file.
    is_frozen = getattr(sys, 'frozen', False)
    flw_file = os.environ.get('SYSTEMAGENT_FLW_FILE') if is_frozen else None
    if flw_file:
        try:
            if os.path.isfile(flw_file):
                with open(flw_file, 'r', encoding='utf-8') as f:
                    flw_content = f.read()
                # Parse JSON so json_script outputs an object, not a double-encoded string
                flw_parsed = json.loads(flw_content)
                context['flw_data'] = flw_parsed
                context['flw_filename'] = os.path.basename(flw_file)
                print(f"--- [FLW] Loaded flow file for auto-open: {flw_file}")
                # Clear the env var so subsequent visits don't re-trigger
                del os.environ['SYSTEMAGENT_FLW_FILE']
            else:
                print(f"--- [FLW] Warning: Flow file not found: {flw_file}")
        except json.JSONDecodeError as e:
            print(f"--- [FLW] Warning: Invalid JSON in flow file {flw_file}: {e}")
        except Exception as e:
            print(f"--- [FLW] Warning: Error reading flow file {flw_file}: {e}")

    return render(request, 'agent/agentic_control_panel.html', context)


@csrf_exempt
def clear_pool_view(request):
    """
    Clear all contents of the agents/pool directory.
    First kills all running agent processes to release file locks.
    Returns JSON response with status.
    """
    pool_path = get_pool_path(request)
    if not pool_path:
        return HttpResponse(json.dumps({'status': 'error', 'message': 'Pool directory path could not be resolved'}), 
                          content_type='application/json', status=500)
    
    # Check if pool path exists before trying to clear it
    if not os.path.exists(pool_path):
        # Create it if it doesn't exist (ensure session dir exists)
        try:
            os.makedirs(pool_path, exist_ok=True)
            return HttpResponse(json.dumps({'status': 'success', 'message': 'Pool directory created (was empty)'}), 
                              content_type='application/json')
        except Exception as e:
             return HttpResponse(json.dumps({'status': 'error', 'message': f'Failed to create pool: {e}'}), status=500)
    
    try:
        # 1. Kill processes first to release file locks
        killed_count = _kill_and_clear_path(pool_path)
        
        # 2. Nuclear option: Remove the entire directory and recreate it
        # This ensures no artifacts remain (as requested by user)
        if os.path.exists(pool_path):
            try:
                shutil.rmtree(pool_path)
            except OSError as e:
                # Retry once if Windows file lock issue
                print(f"[CLEAR] rmtree failed ({e}), retrying...")
                time.sleep(0.5)
                shutil.rmtree(pool_path)
        
        # 3. Recreate empty directory
        os.makedirs(pool_path, exist_ok=True)
        
        return HttpResponse(json.dumps({'status': 'success', 'message': f'Pool directory completely reset (killed {killed_count} process(es))'}), 
                          content_type='application/json')
    except Exception as e:
        print(f"Error clearing pool: {e}")
        # traceback.print_exc() # Removed based on linting feedback earlier/cleanup
        return HttpResponse(json.dumps({'status': 'error', 'message': str(e)}), 
                          content_type='application/json', status=500)

@csrf_exempt
def clear_all_agent_logs_view(request):
    """
    Clear all agent log files in the pool directory.
    Called before starting the flow to ensure fresh logs.
    
    Returns JSON: {status, cleared_count, message}
    """
    pool_path = get_pool_path(request)
    if not pool_path:
        return HttpResponse(json.dumps({
            'status': 'error', 
            'message': 'Pool directory not found'
        }), content_type='application/json', status=404)
    
    if not os.path.exists(pool_path):
        return HttpResponse(json.dumps({
            'status': 'success',
            'cleared_count': 0,
            'message': 'Pool directory is empty'
        }), content_type='application/json')
    
    try:
        cleared_count = 0
        for folder_name in os.listdir(pool_path):
            folder_path = os.path.join(pool_path, folder_name)
            if os.path.isdir(folder_path):
                # Log files are named {folder_name}.log
                log_file = os.path.join(folder_path, f"{folder_name}.log")
                if os.path.exists(log_file):
                    os.remove(log_file)
                    cleared_count += 1
                    print(f"--- Cleared log file: {log_file}")
        
        return HttpResponse(json.dumps({
            'status': 'success',
            'cleared_count': cleared_count,
            'message': f'Cleared {cleared_count} log file(s)'
        }), content_type='application/json')
    except Exception as e:
        print(f"Error clearing agent logs: {e}")
        return HttpResponse(json.dumps({
            'status': 'error', 
            'message': str(e)
        }), content_type='application/json', status=500)

@login_required
def delete_agent_pool_dir_view(request, agent_name):
    """
    Delete a specific agent directory from the pool folder.
    Called when a canvas item is deleted with Delete/Supr key.
    
    agent_name: e.g., 'monitor-log-1' -> deletes 'pool/monitor_log_1'
    
    Returns JSON: {status, deleted, message}
    """
    try:
        # Convert agent_name (monitor-log-1) to pool folder name (monitor_log_1)
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({'status': 'error', 'deleted': False, 'message': 'Invalid agent name'}), 
                              content_type='application/json', status=400)
        
        # Construct full path to pool directory
        pool_base_path = get_pool_path(request)
        if not pool_base_path:
            return HttpResponse(json.dumps({'status': 'error', 'deleted': False, 'message': 'Pool directory not found'}), 
                              content_type='application/json', status=404)
        
        target_dir = os.path.join(pool_base_path, pool_folder_name)
        
        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            shutil.rmtree(target_dir)
            return HttpResponse(json.dumps({
                'status': 'success', 
                'deleted': True, 
                'message': f'Deleted {pool_folder_name}'
            }), content_type='application/json')
        else:
            # Directory doesn't exist - not an error, just wasn't deployed
            return HttpResponse(json.dumps({
                'status': 'success', 
                'deleted': False, 
                'message': f'Directory {pool_folder_name} did not exist'
            }), content_type='application/json')
            
    except Exception as e:
        return HttpResponse(json.dumps({'status': 'error', 'deleted': False, 'message': str(e)}), 
                          content_type='application/json', status=500)

def _find_path(folder_name) -> Optional[str]:
    """
    Locate agents dir in a robust way for both dev and PyInstaller builds.
    Search order:
    1) Directory of the executable when frozen (PyInstaller)
    2) Directory of this module (agent package dir)
    """
    # PyInstaller executable directory
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        agent_dir_path = os.path.join(exe_dir, 'agents', folder_name)
        return agent_dir_path

    # Module directory (development)
    module_dir = os.path.dirname(os.path.abspath(__file__))
    agent_dir_path = os.path.join(module_dir, 'agents', folder_name)
    return agent_dir_path

def get_pool_path(request):
    """
    Get the path to the agent pool for the current session.
    Extracts session_id from X-Agent-Session-ID header.
    Returns: .../agents/pools/{session_id} 
    """
    session_id = request.headers.get('X-Agent-Session-ID')
    
    # Base pools directory (renamed from pool)
    pools_base = _find_path('pools')
    
    if session_id:
        # Sanitize session_id to prevent path traversal
        session_id = os.path.basename(session_id)
        return os.path.join(pools_base, session_id)
    else:
        # Fallback for requests without session ID (e.g. legacy or direct browser access without JS)
        return os.path.join(pools_base, 'default')

def _kill_and_clear_path(target_path):
    """
    Helper to kill processes running from a path and then clear the path contents.
    Does NOT remove the target_path directory itself, only contents.
    NOW WITH GOD MODE: Recursively kills process trees.
    """
    if not os.path.exists(target_path):
        return 0

    killed_count = 0
    
    def recursive_kill(pid):
        """Recursively kill a process and all its children (God Mode)."""
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
        except psutil.NoSuchProcess:
            return

        # Kill children first
        for child in children:
            try:
                print(f"[KILL] Killing child process PID {child.pid} ({child.name()})...")
                child.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Kill parent
        try:
            print(f"[KILL] Killing process PID {parent.pid} ({parent.name()})...")
            parent.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # 1. First, kill tracked processes if we can map them (optional, but good)
    # Since we don't easily have PID->Path mapping in DB without query, 
    # we rely on the aggressive path scan below which is robust.
    
    # 2. Aggressive Scan
    # Kill processes running from the target path
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = proc.info.get('cmdline', [])
            if cmdline:
                cmdline_str = ' '.join(cmdline)
                # Check if process is running from target path
                if target_path in cmdline_str:
                    print(f"[KILL] Found target process PID {proc.info['pid']}: {cmdline_str[:50]}...")
                    recursive_kill(proc.info['pid'])
                    killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    if killed_count > 0:
        # Wait for release
        start = time.time()
        while time.time() - start < 3:
            # Simple wait, could verify pids are gone
            time.sleep(0.1)
            
    # Remove contents
    try:
        if os.path.exists(target_path):
            # Iterate only if path still exists
            for item in os.listdir(target_path):
                item_path = os.path.join(target_path, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except FileNotFoundError:
                    pass # Gone already
                except Exception as e:
                    print(f"Error removing {item_path}: {e}")
    except FileNotFoundError:
        pass # Directory itself gone
            
    return killed_count

@csrf_exempt
def cleanup_session_view(request):
    """
    Remove the pool directory for a specific session.
    Called via navigator.sendBeacon (POST) or explicit fetch.
    """
    session_id = request.GET.get('session_id') or request.POST.get('session_id')
    if not session_id:
        return HttpResponse(json.dumps({'status': 'error', 'message': 'Missing session_id'}), 
                          content_type='application/json', status=400)
    
    pools_base = _find_path('pools')
    if not pools_base:
        return HttpResponse(json.dumps({'status': 'error', 'message': 'Pools directory not found'}), status=500)
        
    session_id = os.path.basename(session_id) # Sanitize
    session_pool_path = os.path.join(pools_base, session_id)
    
    print(f"[CLEANUP] Requested cleanup for session: {session_id}")
    
    # Check existence
    if os.path.exists(session_pool_path):
        try:
            # Kill processes first
            _kill_and_clear_path(session_pool_path)
            
            # Remove the session directory itself
            # Check again before removal to avoid race condition errors
            if os.path.exists(session_pool_path):
                shutil.rmtree(session_pool_path)
                print(f"[CLEANUP] Removed session dir: {session_pool_path}")
                
            return HttpResponse(json.dumps({'status': 'success'}), content_type='application/json')

        except FileNotFoundError:
             # It was deleted by something else in the meantime
             print(f"[CLEANUP] Info: Session dir already gone: {session_pool_path}")
             return HttpResponse(json.dumps({'status': 'success', 'message': 'Already cleaned'}), content_type='application/json')
             
        except Exception as e:
             # If it's a "Path not found" WinError 3, treat as success
             if "WinError 3" in str(e) or isinstance(e, FileNotFoundError):
                 print(f"[CLEANUP] Info: Session dir not found during cleanup (ignoring error): {e}")
                 return HttpResponse(json.dumps({'status': 'success', 'message': 'Already cleaned'}), content_type='application/json')
                 
             print(f"[CLEANUP] Error: {e}")
             # Still return 500 for other genuine errors (permissions etc)
             return HttpResponse(json.dumps({'status': 'error', 'message': str(e)}), status=500)
    
    return HttpResponse(json.dumps({'status': 'success', 'message': 'Session pool did not exist'}), content_type='application/json')


def get_python_command():
    """
    Get the command to run a Python script.
    - In Dev: Use current sys.executable (handles venvs).
    - In Frozen (Windows): Check for bundled python.exe, else fallback to 'python'.
    - In Frozen (Unix): Fallback to 'python3'.
    """
    if not getattr(sys, 'frozen', False):
        return [sys.executable]
    
    # Prefer PYTHON_HOME from USER environment variables
    python_home = get_user_python_home()
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe' if sys.platform.startswith('win') else 'python3')
        if os.path.exists(python_exe):
            return [python_exe]

    if sys.platform.startswith('win'):
        # Check for bundled python.exe next to main executable
        bundled_python = os.path.join(os.path.dirname(sys.executable), 'python.exe')
        if os.path.exists(bundled_python):
            return [bundled_python]
        return ['python']
    
    return ['python3']

def get_user_python_home() -> str:
    """Read PYTHON_HOME exclusively from USER environment variables (Windows registry)."""
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
    """Build environment for child processes with PYTHON_HOME from USER env vars on PATH."""
    env = os.environ.copy()
    
    # Reset PyInstaller's DLL search path alteration on Windows
    # If we don't do this, child Python processes will WinError 1114 when loading C extensions (like torch)
    if sys.platform.startswith('win'):
        try:
            import ctypes
            if hasattr(ctypes.windll.kernel32, 'SetDllDirectoryW'):
                ctypes.windll.kernel32.SetDllDirectoryW(None)
        except Exception:
            pass

    # Remove PyInstaller's _MEIPASS from PATH to prevent DLL conflicts in child processes
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

def load_agent_config_view(request, agent_name):
    try:
        # agent_name comes in as 'agent-name-cardinal' or just 'agent-name'
        # Example: monitor-log-1 -> monitor_log (template) and monitor_log_1 (pool)
        
        # 1. Parse the agent name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
            
        # 2. Join back and replace hyphens with underscores for base name
        base_folder_name = "_".join(parts)
        
        # 3. Build pool folder name (with cardinal)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check: ensure no path traversal
        if '..' in base_folder_name or '/' in base_folder_name or '\\' in base_folder_name:
             return HttpResponse("Invalid agent name", status=400)

        # First try pool directory (deployed agent)
        pool_base_path = get_pool_path(request)
        pool_config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if os.path.exists(pool_config_path):
            with open(pool_config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                return HttpResponse(json.dumps(data), content_type="application/json")
        
        # Fall back to template directory
        agent_dir_path = _find_path(base_folder_name)
        config_path = os.path.join(agent_dir_path, 'config.yaml')
        
        if not os.path.exists(config_path):
             return HttpResponse(f"Config not found for agent: {base_folder_name}", status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return HttpResponse(json.dumps(data), content_type="application/json")

    except Exception as e:
        print(f"Error loading agent config: {e}")
        return HttpResponse(f"Error: {str(e)}", status=500)

def deploy_agent_template_view(request, agent_name):
    """
    Copy agent template to pool folder with default config.
    Called when an agent is dropped onto the canvas.
    
    agent_name: e.g., 'monitor-log-1' -> copies 'monitor_log' template to 'pool/monitor_log_1'
    
    Returns JSON: {success, path}
    """
    try:
        print(f"[DEPLOY] Received agent_name: {agent_name}")
        
        # Parse agent_name to get base folder and pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        print(f"[DEPLOY] base_folder_name: {base_folder_name}, pool_folder_name: {pool_folder_name}")
        
        # Security check
        for name in [base_folder_name, pool_folder_name]:
            if '..' in name or '/' in name or '\\' in name:
                return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}), 
                                  content_type='application/json', status=400)
        
        # Get paths (handles frozen mode)
        source_dir = _find_path(base_folder_name)
        print(f"[DEPLOY] source_dir: {source_dir}")
        print(f"[DEPLOY] source_dir exists: {os.path.exists(source_dir)}")
        
        # Construct pool destination path
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        
        print(f"[DEPLOY] pool_dir: {pool_dir}")
        
        # Verify source exists
        if not os.path.exists(source_dir):
            print(f"[DEPLOY] ERROR: Source not found: {source_dir}")
            return HttpResponse(json.dumps({"success": False, "message": f"Source agent not found: {base_folder_name}"}), 
                              content_type='application/json', status=404)
        
        # Copy directory (overwrite if exists)
        if os.path.exists(pool_dir):
            print(f"[DEPLOY] Pool dir exists, removing: {pool_dir}")
            shutil.rmtree(pool_dir)
        
        print(f"[DEPLOY] Copying {source_dir} -> {pool_dir}")
        shutil.copytree(source_dir, pool_dir)
        print(f"[DEPLOY] SUCCESS: Copied to {pool_dir}")
        
        # For monitor_log agents, update the logfile_path in config.yaml
        if base_folder_name == "monitor_log":
            config_path = os.path.join(pool_dir, 'config.yaml')
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f) or {}
                    
                    # Update logfile_path to use the pool_folder_name
                    if 'target' in config and isinstance(config['target'], dict):
                        config['target']['logfile_path'] = f"{pool_folder_name}.log"
                    
                    # Custom representer for multiline strings
                    def str_representer(dumper, data):
                        if '\n' in data:
                            if not data.endswith('\n'):
                                data = data + '\n'
                            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
                        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
                    
                    yaml.add_representer(str, str_representer)
                    
                    with open(config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                    
                    print(f"[DEPLOY] Updated logfile_path to: {pool_folder_name}.log")
                except Exception as e:
                    print(f"[DEPLOY] Warning: Could not update logfile_path: {e}")
        
        return HttpResponse(json.dumps({"success": True, "path": pool_dir}), content_type="application/json")
        
    except Exception as e:
        print(f"[DEPLOY] Error deploying agent template: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({"success": False, "message": str(e)}), 
                          content_type='application/json', status=500)

@csrf_exempt
def ensure_agent_exists_view(request, agent_name):
    """
    Ensure agent directory exists in pool WITHOUT overwriting existing configs.
    Only deploys from template if the pool directory doesn't exist.
    Called when Start button is pressed to ensure all canvas agents are ready.
    
    agent_name: e.g., 'monitor-log-1' -> ensures 'pool/monitor_log_1' exists
    
    Returns JSON: {success, existed, path}
    """
    try:
        # Parse agent_name to get base folder and pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        for name in [base_folder_name, pool_folder_name]:
            if '..' in name or '/' in name or '\\' in name:
                return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}), 
                                  content_type='application/json', status=400)
        
        # Construct pool destination path
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        
        # If pool directory already exists, ensure the Python script is up-to-date
        # This allows code fixes to propagate to deployed agents without resetting config
        if os.path.exists(pool_dir):
            try:
                # Find source script
                source_dir = _find_path(base_folder_name)
                source_script = os.path.join(source_dir, f"{base_folder_name}.py")

                # Destination script
                dest_script = os.path.join(pool_dir, f"{base_folder_name}.py")

                if os.path.exists(source_script):
                    print(f"[ENSURE] Updating script for {pool_folder_name}...")
                    shutil.copy2(source_script, dest_script)
                else:
                    print(f"[ENSURE] Warning: Source script not found: {source_script}")

                # Copy Telethon session file for telegramrx agents
                if base_folder_name == "telegramrx":
                    for session_file in ['telegramrx_session.session']:
                        src_session = os.path.join(source_dir, session_file)
                        if os.path.exists(src_session):
                            dst_session = os.path.join(pool_dir, session_file)
                            shutil.copy2(src_session, dst_session)
                            print(f"[ENSURE] Copied session file: {session_file}")

            except Exception as e:
                print(f"[ENSURE] Warning: Failed to update script for {pool_folder_name}: {e}")

            print(f"[ENSURE] Agent {pool_folder_name} already exists (script updated)")
            return HttpResponse(json.dumps({
                "success": True, 
                "existed": True, 
                "path": pool_dir
            }), content_type="application/json")
        
        # Pool directory doesn't exist - deploy from template
        source_dir = _find_path(base_folder_name)
        
        if not os.path.exists(source_dir):
            print(f"[ENSURE] ERROR: Source not found: {source_dir}")
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Source agent not found: {base_folder_name}"
            }), content_type='application/json', status=404)
        
        print(f"[ENSURE] Deploying {base_folder_name} -> {pool_dir}")
        shutil.copytree(source_dir, pool_dir)
        
        # For monitor_log agents, update the logfile_path in config.yaml
        if base_folder_name == "monitor_log":
            config_path = os.path.join(pool_dir, 'config.yaml')
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = yaml.safe_load(f) or {}
                    
                    if 'target' in config and isinstance(config['target'], dict):
                        config['target']['logfile_path'] = f"{pool_folder_name}.log"
                    
                    def str_representer(dumper, data):
                        if '\n' in data:
                            if not data.endswith('\n'):
                                data = data + '\n'
                            return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
                        return dumper.represent_scalar('tag:yaml.org,2002:str', data)
                    
                    yaml.add_representer(str, str_representer)
                    
                    with open(config_path, 'w', encoding='utf-8') as f:
                        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
                except Exception as e:
                    print(f"[ENSURE] Warning: Could not update logfile_path: {e}")
        
        print(f"[ENSURE] SUCCESS: Deployed {pool_folder_name}")
        return HttpResponse(json.dumps({
            "success": True, 
            "existed": False, 
            "path": pool_dir
        }), content_type="application/json")
        
    except Exception as e:
        print(f"[ENSURE] Error ensuring agent exists: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({"success": False, "message": str(e)}), 
                          content_type='application/json', status=500)

@csrf_exempt
@require_POST
def save_agent_config_view(request, agent_name):
    """
    Save agent config to pool folder WITHOUT overwriting existing files.
    If pool folder exists, only update config.yaml (preserving any fields not in the update).
    If pool folder doesn't exist, copy from template first.
    
    Expected POST body (JSON):
    {
        "llm": {"base_url": "...", "model": "...", ...},
        "target": {...},
        ...
    }
    """
    try:
        # Parse POSTed config data
        config_data = json.loads(request.body.decode('utf-8'))
        
        # agent_name comes in as 'agent-name-cardinal' (e.g., 'monitor-log-1')
        # We need:
        #   1. base folder name (e.g., 'monitor_log')
        #   2. pool folder name (e.g., 'monitor_log_1')
        
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        # Base folder: join remaining parts with underscore
        base_folder_name = "_".join(parts)
        
        # Pool folder: base + underscore + cardinal
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        for name in [base_folder_name, pool_folder_name]:
            if '..' in name or '/' in name or '\\' in name:
                return HttpResponse("Invalid agent name", status=400)
        
        # Get paths (handles frozen mode)
        source_dir = _find_path(base_folder_name)
        
        # Construct pool destination path
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        # Only copy from template if pool folder doesn't exist
        if not os.path.exists(pool_dir):
            # Verify source exists
            if not os.path.exists(source_dir):
                return HttpResponse(f"Source agent not found: {base_folder_name}", status=404)
            # Copy template to pool
            shutil.copytree(source_dir, pool_dir)
            print(f"[SAVE] Created new pool directory from template: {pool_dir}")
        else:
            print(f"[SAVE] Pool directory already exists, preserving files: {pool_dir}")
        
        # Load existing config to preserve fields not in the update
        existing_config = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    existing_config = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"[SAVE] Warning: Could not read existing config: {e}")
        
        # Deep merge: user updates take precedence over existing values
        def deep_merge(base, updates):
            """Recursively merge updates into base. Updates take precedence."""
            result = dict(base)
            for key, value in updates.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result
        
        # Merge: existing config is base, user updates override
        merged_config = deep_merge(existing_config, config_data)
        
        # Custom representer for multiline strings to use literal block style (|)
        def str_representer(dumper, data):
            if '\n' in data:
                # Ensure trailing newline to avoid "|-" (strip indicator)
                if not data.endswith('\n'):
                    data = data + '\n'
                # Use literal block style for multiline strings
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(merged_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"[SAVE] Config saved to: {config_path}")
        return HttpResponse(json.dumps({
            "success": True, 
            "path": pool_dir,
            "config": merged_config
        }), content_type="application/json")
        
    except json.JSONDecodeError as e:
        return HttpResponse(f"Invalid JSON: {str(e)}", status=400)
    except Exception as e:
        print(f"Error saving agent config: {e}")
        return HttpResponse(f"Error: {str(e)}", status=500)


def _write_pid_file(agent_dir, pid):
    """Write PID to agent.pid in the agent directory."""
    try:
        pid_path = os.path.join(agent_dir, "agent.pid")
        with open(pid_path, "w") as f:
            f.write(str(pid))
    except Exception as e:
        print(f"[PID] Failed to write PID file in {agent_dir}: {e}")


@csrf_exempt
@require_POST
def update_raiser_connection_view(request, agent_name):
    """
    Update a Raiser agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "connection_type": "source" | "target",
        "connected_agent": "agent-id",  # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    
    - connection_type: "source" means the connected_agent is connected to raiser's INPUT
      (add to source_agents list)
    - connection_type: "target" means the connected_agent is connected to raiser's OUTPUT
      (add to target_agents list)
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type')  # 'source' or 'target'
        connected_agent = data.get('connected_agent')  # e.g., 'monitor-log-1'
        action = data.get('action', 'add')  # 'add' or 'remove'
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing connection_type or connected_agent"
            }), content_type='application/json', status=400)
        
        if connection_type not in ['source', 'target']:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "connection_type must be 'source' or 'target'"
            }), content_type='application/json', status=400)
        
        # Parse raiser agent_name to get pool folder name
        # agent_name comes in as 'raiser-1' -> pool folder is 'raiser_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Raiser config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Convert connected_agent ID to pool folder format
        # e.g., 'monitor-log-1' -> 'monitor_log_1'
        connected_parts = connected_agent.split('-')
        connected_cardinal = None
        if connected_parts[-1].isdigit():
            connected_cardinal = connected_parts.pop()
        
        connected_base = "_".join(connected_parts)
        
        if connected_cardinal:
            connected_pool_name = f"{connected_base}_{connected_cardinal}"
        else:
            connected_pool_name = connected_base
        
        # Determine which list to update
        if connection_type == 'source':
            list_key = 'source_agents'
        else:
            list_key = 'target_agents'
        
        # Ensure the list exists
        if list_key not in config:
            config[list_key] = []
        
        # Make sure it's a list
        if not isinstance(config[list_key], list):
            config[list_key] = []
        
        # Add or remove the connected agent
        if action == 'add':
            if connected_pool_name not in config[list_key]:
                config[list_key].append(connected_pool_name)
        elif action == 'remove':
            if connected_pool_name in config[list_key]:
                config[list_key].remove(connected_pool_name)
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"{'Added' if action == 'add' else 'Removed'} {connected_pool_name} {'to' if action == 'add' else 'from'} {list_key}",
            "config": config
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating raiser connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_emailer_connection_view(request, agent_name):
    """
    Update an Emailer agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "connection_type": "source",
        "connected_agent": "agent-id",  # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    
    - connection_type: "source" means the connected_agent is connected to emailer's INPUT
      (add to source_agents list)
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type')  # 'source'
        connected_agent = data.get('connected_agent')  # e.g., 'monitor-log-1'
        action = data.get('action', 'add')  # 'add' or 'remove'
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing connection_type or connected_agent"
            }), content_type='application/json', status=400)
        
        if connection_type not in ['source']:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "connection_type must be 'source'"
            }), content_type='application/json', status=400)
        
        # Parse emailer agent_name to get pool folder name
        # agent_name comes in as 'emailer-1' -> pool folder is 'emailer_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Emailer config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Convert connected_agent ID to pool folder format
        # e.g., 'monitor-log-1' -> 'monitor_log_1'
        connected_parts = connected_agent.split('-')
        connected_cardinal = None
        if connected_parts[-1].isdigit():
            connected_cardinal = connected_parts.pop()
        
        connected_base = "_".join(connected_parts)
        
        if connected_cardinal:
            connected_pool_name = f"{connected_base}_{connected_cardinal}"
        else:
            connected_pool_name = connected_base
        
        # Emailer only has source_agents (input connections)
        list_key = 'source_agents'
        
        # Ensure the list exists
        if list_key not in config:
            config[list_key] = []
        
        # Make sure it's a list
        if not isinstance(config[list_key], list):
            config[list_key] = []
        
        # Add or remove the connected agent
        if action == 'add':
            if connected_pool_name not in config[list_key]:
                config[list_key].append(connected_pool_name)
        elif action == 'remove':
            if connected_pool_name in config[list_key]:
                config[list_key].remove(connected_pool_name)
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"{'Added' if action == 'add' else 'Removed'} {connected_pool_name} {'to' if action == 'add' else 'from'} {list_key}",
            "config": config
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating emailer connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_monitor_log_connection_view(request, agent_name):
    """
    Update a Monitor Log agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "source_agent": "agent-id",  # e.g., "monitor-netstat-1"
        "action": "add" | "remove"
    }
    
    When action is "add":
      - Sets target.logfile_path = "../{source_pool_folder}/{source_pool_folder}.log"
    
    When action is "remove":
      - Resets target.logfile_path to "{monitor_log_pool_folder}.log" (self-monitoring)
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        source_agent = data.get('source_agent')  # e.g., 'monitor-netstat-1'
        action = data.get('action', 'add')  # 'add' or 'remove'
        
        if not source_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing source_agent"
            }), content_type='application/json', status=400)
        
        # Parse monitor_log agent_name to get pool folder name
        # agent_name comes in as 'monitor-log-1' -> pool folder is 'monitor_log_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Monitor Log config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Ensure 'target' section exists
        if 'target' not in config:
            config['target'] = {}
        
        if action == 'add':
            # Parse source_agent to get source pool folder name
            # e.g., 'monitor-netstat-1' -> 'monitor_netstat_1'
            source_parts = source_agent.split('-')
            source_cardinal = None
            if source_parts[-1].isdigit():
                source_cardinal = source_parts.pop()
            
            source_base = "_".join(source_parts)
            
            if source_cardinal:
                source_pool_name = f"{source_base}_{source_cardinal}"
            else:
                source_pool_name = source_base
            
            # Build relative path: ../{source_pool_folder}/{source_pool_folder}.log
            # This works because monitor_log.py changes working directory to its own folder
            relative_log_path = f"../{source_pool_name}/{source_pool_name}.log"
            
            # IMPORTANT: Only auto-configure if the current value is a DEFAULT value
            # Default values are: self-monitoring path (pool_folder_name.log) or 
            # relative paths starting with ../ (auto-configured by connections)
            # If user has set an ABSOLUTE path (like F:\logs\file.log), DON'T overwrite!
            current_path = config['target'].get('logfile_path', '')
            is_default_value = (
                current_path == '' or
                current_path == f'{pool_folder_name}.log' or  # Self-monitoring default
                current_path.startswith('../') or            # Auto-configured by connection
                current_path == 'monitor_log.log'            # Template default
            )
            
            if is_default_value:
                config['target']['logfile_path'] = relative_log_path
                message = f"Set logfile_path to {relative_log_path}"
            else:
                # User has set a custom absolute path - DON'T overwrite
                message = f"Preserved user-configured logfile_path: {current_path}"
            
        elif action == 'remove':
            # Only reset if current path was auto-configured (starts with ../)
            current_path = config['target'].get('logfile_path', '')
            if current_path.startswith('../'):
                # Reset to self-monitoring (own log file)
                config['target']['logfile_path'] = f"{pool_folder_name}.log"
                message = f"Reset logfile_path to {pool_folder_name}.log"
            else:
                # User has set a custom path - DON'T reset
                message = f"Preserved user-configured logfile_path: {current_path}"
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": message,
            "logfile_path": config['target']['logfile_path']
        }), content_type='application/json')

    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating monitor log connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_or_agent_connection_view(request, agent_name):
    """
    Update an OR agent's config.yaml.
    
    Expected POST body (JSON):
    {
        "connection_type": "source_1" | "source_2" | "target",
        "connected_agent": "agent-id",
        "action": "add" | "remove"
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type') 
        connected_agent = data.get('connected_agent') 
        action = data.get('action', 'add') 
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing args"}), content_type='application/json', status=400)
            
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}), content_type='application/json', status=400)
            
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
             return HttpResponse(json.dumps({"success": False, "message": "Config not found"}), content_type='application/json', status=404)
             
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
            
        # Parse connected agent
        c_parts = connected_agent.split('-')
        c_cardinal = None
        if c_parts[-1].isdigit():
            c_cardinal = c_parts.pop()
        c_base = "_".join(c_parts)
        if c_cardinal:
            connected_pool_name = f"{c_base}_{c_cardinal}"
        else:
            connected_pool_name = c_base
        
        if connection_type == 'target':
            if 'target_agents' not in config:
                config['target_agents'] = []
            if not isinstance(config['target_agents'], list):
                config['target_agents'] = []
            
            if action == 'add':
                if connected_pool_name not in config['target_agents']:
                    config['target_agents'].append(connected_pool_name)
            elif action == 'remove':
                if connected_pool_name in config['target_agents']:
                    config['target_agents'].remove(connected_pool_name)
                    
        elif connection_type == 'source_1':
            if action == 'add':
                config['source_agent_1'] = connected_pool_name
            elif action == 'remove':
                # Only remove if it matches current (implicit safety)
                if config.get('source_agent_1') == connected_pool_name:
                    config['source_agent_1'] = ""
                    
        elif connection_type == 'source_2':
            if action == 'add':
                config['source_agent_2'] = connected_pool_name
            elif action == 'remove':
                if config.get('source_agent_2') == connected_pool_name:
                    config['source_agent_2'] = ""
        
        # Save
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        yaml.add_representer(str, str_representer)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
        return HttpResponse(json.dumps({"success": True, "message": "Updated OR config"}), content_type='application/json')
        
    except Exception as e:
        print(f"Error updating OR connection: {e}")
        return HttpResponse(json.dumps({"success": False, "message": str(e)}), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_and_agent_connection_view(request, agent_name):
    """
    Update an AND agent's config.yaml.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type') 
        connected_agent = data.get('connected_agent') 
        action = data.get('action', 'add') 
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing args"}), content_type='application/json', status=400)
            
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}), content_type='application/json', status=400)
            
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
             return HttpResponse(json.dumps({"success": False, "message": "Config not found"}), content_type='application/json', status=404)
             
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
            
        c_parts = connected_agent.split('-')
        c_cardinal = None
        if c_parts[-1].isdigit():
            c_cardinal = c_parts.pop()
        c_base = "_".join(c_parts)
        if c_cardinal:
            connected_pool_name = f"{c_base}_{c_cardinal}"
        else:
            connected_pool_name = c_base
        
        if connection_type == 'target':
            if 'target_agents' not in config:
                config['target_agents'] = []
            if not isinstance(config['target_agents'], list):
                config['target_agents'] = []
            
            if action == 'add':
                if connected_pool_name not in config['target_agents']:
                    config['target_agents'].append(connected_pool_name)
            elif action == 'remove':
                if connected_pool_name in config['target_agents']:
                    config['target_agents'].remove(connected_pool_name)
                    
        elif connection_type == 'source_1':
            if action == 'add':
                config['source_agent_1'] = connected_pool_name
            elif action == 'remove':
                if config.get('source_agent_1') == connected_pool_name:
                    config['source_agent_1'] = ""
                    
        elif connection_type == 'source_2':
            if action == 'add':
                config['source_agent_2'] = connected_pool_name
            elif action == 'remove':
                if config.get('source_agent_2') == connected_pool_name:
                    config['source_agent_2'] = ""
        
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        yaml.add_representer(str, str_representer)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
        return HttpResponse(json.dumps({"success": True, "message": "Updated AND config"}), content_type='application/json')
        
    except Exception as e:
        print(f"Error updating AND connection: {e}")
        return HttpResponse(json.dumps({"success": False, "message": str(e)}), content_type='application/json', status=500)
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating monitor_log connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_ender_connection_view(request, agent_name):
    """
    Update an Ender agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "source_agent": "agent-id",  # e.g., "raiser-1"
        "action": "add" | "remove"
    }

    When action is "add":
      - Appends source_agent to source_agents list

    When action is "remove":
      - Removes source_agent from source_agents list
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        source_agent = data.get('source_agent')  # agent to add/remove
        action = data.get('action', 'add')  # 'add' or 'remove'
        connection_type = data.get('connection_type', 'input') # 'input' (default) or 'output'
        
        if not source_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing source_agent"
            }), content_type='application/json', status=400)
        
        # Parse ender agent_name to get pool folder name
        # agent_name comes in as 'ender-1' -> pool folder is 'ender_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Ender config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Parse source_agent (which is actually the connected agent, could be target if output)
        source_parts = source_agent.split('-')
        source_cardinal = None
        if source_parts[-1].isdigit():
            source_cardinal = source_parts.pop()
        
        source_base = "_".join(source_parts)
        
        if source_cardinal:
            connected_pool_name = f"{source_base}_{source_cardinal}"
        else:
            connected_pool_name = source_base
            
        # Determine list name based on connection type
        list_name = 'source_agents'
        if connection_type == 'output':
             list_name = 'output_agents'
        
        # Ensure list exists
        if list_name not in config:
            config[list_name] = []
        
        if not isinstance(config[list_name], list):
            config[list_name] = []
        
        if action == 'add':
            if connected_pool_name not in config[list_name]:
                config[list_name].append(connected_pool_name)
            message = f"Added {connected_pool_name} to {list_name}"
        elif action == 'remove':
            if connected_pool_name in config[list_name]:
                config[list_name].remove(connected_pool_name)
            message = f"Removed {connected_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)

        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({
            "success": True,
            "message": message,
            "source_agents": config.get('source_agents', []),
            "output_agents": config.get('output_agents', [])
        }), content_type='application/json')

    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False,
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating ender connection: {e}")
        return HttpResponse(json.dumps({
            "success": False,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_stopper_connection_view(request, agent_name):
    """
    Update a Stopper agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "connection_type": "source" | "output",
        "connected_agent": "agent-id",  # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    
    - connection_type: "source" means the connected_agent is connected to stopper's INPUT
      (add to source_agents list)
    - connection_type: "output" means the connected_agent is connected to stopper's OUTPUT
      (add to output_agents list)
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type')  # 'source' or 'output'
        connected_agent = data.get('connected_agent')  # e.g., 'monitor-log-1'
        action = data.get('action', 'add')  # 'add' or 'remove'
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing connection_type or connected_agent"
            }), content_type='application/json', status=400)
        
        if connection_type not in ['source', 'output']:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "connection_type must be 'source' or 'output'"
            }), content_type='application/json', status=400)
        
        # Parse stopper agent_name to get pool folder name
        # agent_name comes in as 'stopper-1' -> pool folder is 'stopper_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Stopper config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Convert connected_agent ID to pool folder format
        # e.g., 'monitor-log-1' -> 'monitor_log_1'
        connected_parts = connected_agent.split('-')
        connected_cardinal = None
        if connected_parts[-1].isdigit():
            connected_cardinal = connected_parts.pop()
        
        connected_base = "_".join(connected_parts)
        
        if connected_cardinal:
            connected_pool_name = f"{connected_base}_{connected_cardinal}"
        else:
            connected_pool_name = connected_base
        
        # Determine which list to update
        if connection_type == 'source':
            list_key = 'source_agents'
        else:
            list_key = 'output_agents'
        
        # Ensure the list exists
        if list_key not in config:
            config[list_key] = []
        
        # Make sure it's a list
        if not isinstance(config[list_key], list):
            config[list_key] = []
        
        # Add or remove the connected agent
        if action == 'add':
            if connected_pool_name not in config[list_key]:
                config[list_key].append(connected_pool_name)
        elif action == 'remove':
            if connected_pool_name in config[list_key]:
                config[list_key].remove(connected_pool_name)
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"{'Added' if action == 'add' else 'Removed'} {connected_pool_name} {'to' if action == 'add' else 'from'} {list_key}",
            "config": config
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating stopper connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_notifier_connection_view(request, agent_name):
    """
    Update a Notifier agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "connection_type": "source" | "target",
        "connected_agent": "agent-id",  # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type') 
        connected_agent = data.get('connected_agent') 
        action = data.get('action', 'add') 
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing connection_type or connected_agent"
            }), content_type='application/json', status=400)
        
        if connection_type not in ['source', 'target']:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "connection_type must be 'source' or 'target'"
            }), content_type='application/json', status=400)
        
        # Parse notifier agent_name to get pool folder name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Notifier config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Convert connected_agent ID to pool folder format
        connected_parts = connected_agent.split('-')
        connected_cardinal = None
        if connected_parts[-1].isdigit():
            connected_cardinal = connected_parts.pop()
        
        connected_base = "_".join(connected_parts)
        
        if connected_cardinal:
            connected_pool_name = f"{connected_base}_{connected_cardinal}"
        else:
            connected_pool_name = connected_base
        
        # Determine which list to update
        if connection_type == 'source':
            list_key = 'source_agents'
        else:
            list_key = 'target_agents'
        
        # Ensure the list exists
        if list_key not in config:
            config[list_key] = []
        
        # Make sure it's a list
        if not isinstance(config[list_key], list):
            config[list_key] = []
        
        # Add or remove the connected agent
        if action == 'add':
            if connected_pool_name not in config[list_key]:
                config[list_key].append(connected_pool_name)
        elif action == 'remove':
            if connected_pool_name in config[list_key]:
                config[list_key].remove(connected_pool_name)
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"{'Added' if action == 'add' else 'Removed'} {connected_pool_name} {'to' if action == 'add' else 'from'} {list_key}",
            "config": config
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating notifier connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_starter_connection_view(request, agent_name):
    """
    Update a Starter agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "target_agent": "agent-id",  # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    
    When action is "add":
      - Appends target_agent to target_agents list
    
    When action is "remove":
      - Removes target_agent from target_agents list
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')  # e.g., 'monitor-log-1'
        action = data.get('action', 'add')  # 'add' or 'remove'
        
        if not target_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing target_agent"
            }), content_type='application/json', status=400)
        
        # Parse starter agent_name to get pool folder name
        # agent_name comes in as 'starter-1' -> pool folder is 'starter_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool config path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Starter config not found: {config_path}"
            }), content_type='application/json', status=404)
        
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        # Parse target_agent to get pool folder name
        # e.g., 'monitor-log-1' -> 'monitor_log_1'
        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        
        target_base = "_".join(target_parts)
        
        if target_cardinal:
            target_pool_name = f"{target_base}_{target_cardinal}"
        else:
            target_pool_name = target_base
        
        # Ensure target_agents list exists
        if 'target_agents' not in config:
            config['target_agents'] = []
        
        if not isinstance(config['target_agents'], list):
            config['target_agents'] = []
        
        if action == 'add':
            if target_pool_name not in config['target_agents']:
                config['target_agents'].append(target_pool_name)
            message = f"Added {target_pool_name} to target_agents"
        elif action == 'remove':
            if target_pool_name in config['target_agents']:
                config['target_agents'].remove(target_pool_name)
            message = f"Removed {target_pool_name} from target_agents"
        else:
            message = f"Unknown action: {action}"
        
        # Custom representer for multiline strings
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": message,
            "target_agents": config['target_agents']
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating starter connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@login_required
def load_session_state_view(request):
    """
    Load session state for the current user.
    Returns context_path, context_type, context_filename if valid (not expired).
    """
    try:
        user = request.user
        session_state = SessionState.objects.filter(user=user).first()
        
        if session_state is None:
            return HttpResponse(json.dumps({
                "success": True,
                "has_context": False,
                "context_path": None,
                "context_type": None,
                "context_filename": None
            }), content_type='application/json')
        
        # Check if expired (24 hours)
        if session_state.is_expired():
            session_state.delete()
            return HttpResponse(json.dumps({
                "success": True,
                "has_context": False,
                "context_path": None,
                "context_type": None,
                "context_filename": None,
                "message": "Session expired"
            }), content_type='application/json')
        
        return HttpResponse(json.dumps({
            "success": True,
            "has_context": bool(session_state.context_path),
            "context_path": session_state.context_path,
            "context_type": session_state.context_type,
            "context_filename": session_state.context_filename
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error loading session state: {e}")
        return HttpResponse(json.dumps({
            "success": False,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
@login_required
def save_session_state_view(request):
    """
    Save session state for the current user.
    Expected POST body (JSON):
    {
        "context_path": "...",
        "context_type": "directory" | "file",
        "context_filename": "..." (optional, for file type)
    }
    """
    try:
        user = request.user
        data = json.loads(request.body.decode('utf-8'))
        
        context_path = data.get('context_path')
        context_type = data.get('context_type')
        context_filename = data.get('context_filename')
        
        # Update or create session state
        session_state, created = SessionState.objects.update_or_create(
            user=user,
            defaults={
                'context_path': context_path,
                'context_type': context_type,
                'context_filename': context_filename
            }
        )
        
        return HttpResponse(json.dumps({
            "success": True,
            "created": created,
            "message": "Session state saved"
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False,
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error saving session state: {e}")
        return HttpResponse(json.dumps({
            "success": False,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def execute_starter_agent_view(request, agent_name):
    """
    Execute a Starter agent by running its Python script.
    This is called when the Start button is pressed in the control panel.
    
    agent_name: e.g., 'starter-1' -> looks for 'pool/starter_1/starter.py'
    
    Returns JSON: {success, message, pid}
    """
    try:
        # Parse agent_name to get pool folder name
        # agent_name comes in as 'starter-1' -> pool folder is 'starter_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool directory path
        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)
        
        if not os.path.exists(agent_dir):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Agent directory not found: {pool_folder_name}"
            }), content_type='application/json', status=404)
        
        # Find the starter.py script
        script_path = os.path.join(agent_dir, f"{base_folder_name}.py")
        
        if not os.path.exists(script_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Agent script not found: {base_folder_name}.py"
            }), content_type='application/json', status=404)
        
        # Execute the starter agent
        python_cmd = get_python_command()
        agent_env = get_agent_env()
        
        if sys.platform.startswith('win'):
            # Windows: create new process group
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Unix: start new session
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                start_new_session=True
            )
        
        # Write PID file for fast status checking
        _write_pid_file(agent_dir, process.pid)
        print(f"[EXECUTE] Started {pool_folder_name} with PID: {process.pid}")
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"Started {pool_folder_name}",
            "pid": process.pid
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error executing starter agent: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def check_starter_log_view(request, agent_name):
    """
    Check if a starter agent's log file exists and was created/modified 
    after the given timestamp.
    
    Query params:
    - timestamp: Unix timestamp in milliseconds
    
    Returns JSON: {exists, modified_after_timestamp, log_path, mtime}
    """
    try:
        # Get timestamp from query params (in milliseconds)
        timestamp_ms = request.GET.get('timestamp', '0')
        try:
            timestamp_ms = int(timestamp_ms)
        except ValueError:
            timestamp_ms = 0
        
        # Convert to seconds for comparison with file mtime
        timestamp_sec = timestamp_ms / 1000.0
        
        # Parse agent_name to get pool folder name
        # agent_name comes in as 'starter-1' -> pool folder is 'starter_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "exists": False, 
                "modified_after_timestamp": False,
                "error": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool directory path
        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)
        
        # Look for the log file (e.g., starter_1.log)
        log_file_path = os.path.join(agent_dir, f"{pool_folder_name}.log")
        
        if not os.path.exists(log_file_path):
            return HttpResponse(json.dumps({
                "exists": False,
                "modified_after_timestamp": False,
                "log_path": log_file_path,
                "mtime": None
            }), content_type='application/json')
        
        # Get file modification time
        file_mtime = os.path.getmtime(log_file_path)
        modified_after = file_mtime >= timestamp_sec
        
        return HttpResponse(json.dumps({
            "exists": True,
            "modified_after_timestamp": modified_after,
            "log_path": log_file_path,
            "mtime": file_mtime * 1000  # Return in milliseconds for JS
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error checking starter log: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "exists": False,
            "modified_after_timestamp": False,
            "error": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def check_ender_log_view(request, agent_name):
    """
    Check if an ender agent's log file exists and was created/modified 
    after the given timestamp.
    
    Query params:
    - timestamp: Unix timestamp in milliseconds
    
    Returns JSON: {exists, modified_after_timestamp, log_path, mtime}
    """
    try:
        # Get timestamp from query params (in milliseconds)
        timestamp_ms = request.GET.get('timestamp', '0')
        try:
            timestamp_ms = int(timestamp_ms)
        except ValueError:
            timestamp_ms = 0
        
        # Convert to seconds for comparison with file mtime
        timestamp_sec = timestamp_ms / 1000.0
        
        print(f"[CHECK_ENDER_LOG] agent_name: {agent_name}, timestamp_ms: {timestamp_ms}, timestamp_sec: {timestamp_sec}")
        
        # Parse agent_name to get pool folder name
        # agent_name comes in as 'ender-1' -> pool folder is 'ender_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        print(f"[CHECK_ENDER_LOG] base_folder_name: {base_folder_name}, pool_folder_name: {pool_folder_name}")
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "exists": False, 
                "modified_after_timestamp": False,
                "error": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool directory path
        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)
        
        # Look for the log file (e.g., ender_1.log)
        log_file_path = os.path.join(agent_dir, f"{pool_folder_name}.log")
        
        print(f"[CHECK_ENDER_LOG] Looking for log file: {log_file_path}")
        print(f"[CHECK_ENDER_LOG] File exists: {os.path.exists(log_file_path)}")
        
        if not os.path.exists(log_file_path):
            return HttpResponse(json.dumps({
                "exists": False,
                "modified_after_timestamp": False,
                "log_path": log_file_path,
                "mtime": None
            }), content_type='application/json')
        
        # Get file modification time
        file_mtime = os.path.getmtime(log_file_path)
        modified_after = file_mtime >= timestamp_sec
        
        print(f"[CHECK_ENDER_LOG] file_mtime: {file_mtime}, timestamp_sec: {timestamp_sec}, modified_after: {modified_after}")
        
        return HttpResponse(json.dumps({
            "exists": True,
            "modified_after_timestamp": modified_after,
            "log_path": log_file_path,
            "mtime": file_mtime * 1000  # Return in milliseconds for JS
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error checking ender log: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "exists": False,
            "modified_after_timestamp": False,
            "error": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def execute_ender_agent_view(request, agent_name):
    """
    Execute an Ender agent by running its Python script.
    This is called when the Stop button is pressed in the control panel.
    
    agent_name: e.g., 'ender-1' -> looks for 'pool/ender_1/ender.py'
    
    Returns JSON: {success, message, pid}
    """
    try:
        # Parse agent_name to get pool folder name
        # agent_name comes in as 'ender-1' -> pool folder is 'ender_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool directory path
        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)
        
        if not os.path.exists(agent_dir):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Agent directory not found: {pool_folder_name}"
            }), content_type='application/json', status=404)
        
        # Find the ender.py script
        script_path = os.path.join(agent_dir, f"{base_folder_name}.py")
        
        if not os.path.exists(script_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Agent script not found: {base_folder_name}.py"
            }), content_type='application/json', status=404)
        
        # Execute the ender agent
        # Execute the ender agent
        python_cmd = get_python_command()
        
        if sys.platform.startswith('win'):
            # Windows: create new process group
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Unix: start new session
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                start_new_session=True
            )
        
        # Write PID file for fast status checking
        _write_pid_file(agent_dir, process.pid)
        print(f"[EXECUTE] Started {pool_folder_name} with PID: {process.pid}")
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"Started {pool_folder_name}",
            "pid": process.pid
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error executing ender agent: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def check_agents_running_view(request, agent_name):
    """
    Check if target agents in an Ender agent's config are currently running.
    Returns JSON with running_count, total_count, and list of running agents.
    
    agent_name: e.g., 'ender-1' -> reads 'pool/ender_1/config.yaml'
    
    Returns JSON: {running_count, total_count, running_agents, all_down}
    """
    try:
        # Parse agent_name to get pool folder name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "running_count": 0,
                "total_count": 0,
                "running_agents": [],
                "all_down": True,
                "error": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool directory path
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "running_count": 0,
                "total_count": 0,
                "running_agents": [],
                "all_down": True,
                "error": f"Config not found: {pool_folder_name}"
            }), content_type='application/json', status=404)
        
        # Load config to get target_agents list
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
        
        target_agents = config.get('target_agents', [])
        
        if not target_agents:
            return HttpResponse(json.dumps({
                "running_count": 0,
                "total_count": 0,
                "running_agents": [],
                "all_down": True,
                "message": "No target agents configured"
            }), content_type='application/json')
        
        # Check which agents are running using psutil
        running_agents = []
        
        for agent_id in target_agents:
            # Get the script path for this agent
            agent_dir = os.path.join(pool_base_path, agent_id)
            
            # Get base name for script file (e.g., monitor_log_1 -> monitor_log)
            agent_parts = agent_id.rsplit('_', 1)
            if len(agent_parts) == 2 and agent_parts[1].isdigit():
                base_name = agent_parts[0]
            else:
                base_name = agent_id
            
            script_name = f"{base_name}.py"
            
            # Check all running processes
            is_running = False
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline:
                        cmdline_str = ' '.join(cmdline)
                        # Check if this process is running from the agent's directory
                        if agent_dir in cmdline_str or (script_name in cmdline_str and agent_id in cmdline_str):
                            is_running = True
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if is_running:
                running_agents.append(agent_id)
        
        return HttpResponse(json.dumps({
            "running_count": len(running_agents),
            "total_count": len(target_agents),
            "running_agents": running_agents,
            "all_down": len(running_agents) == 0
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error checking agents running: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "running_count": 0,
            "total_count": 0,
            "running_agents": [],
            "all_down": True,
            "error": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
@login_required
def clear_session_state_view(request):
    """
    Clear session state for the current user.
    """
    try:
        user = request.user
        SessionState.objects.filter(user=user).delete()
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": "Session state cleared"
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error clearing session state: {e}")
        return HttpResponse(json.dumps({
            "success": False,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def check_all_agents_status_view(request):
    """
    Check running status of ALL agents in the pool directory.
    Used by the frontend for LED indicator polling.
    
    Returns JSON: {
        success: boolean,
        agents: { [agent_canvas_id]: boolean (is_running) }
    }
    
    The agent_canvas_id matches the canvas item ID (e.g., 'monitor-log-1')
    """
    try:
        pool_base_path = get_pool_path(request)
        
        if not os.path.exists(pool_base_path):
            return HttpResponse(json.dumps({
                "success": True,
                "agents": {}
            }), content_type='application/json')
        
        agents_status = {}
        detailed_statuses = {}
        notifications = []
        
        # Iterate through all subdirectories in pool
        for folder_name in os.listdir(pool_base_path):
            folder_path = os.path.join(pool_base_path, folder_name)
            
            if not os.path.isdir(folder_path):
                continue
            
            # Convert pool folder name back to canvas ID
            # e.g., 'monitor_log_1' -> 'monitor-log-1'
            canvas_id = folder_name.replace('_', '-')
            
            # Check for agent.pid file
            pid_file_path = os.path.join(folder_path, "agent.pid")
            is_running = False
            
            if os.path.exists(pid_file_path):
                try:
                    with open(pid_file_path, "r") as f:
                        pid_str = f.read().strip()
                        if pid_str.isdigit():
                            pid = int(pid_str)
                            if psutil.pid_exists(pid):
                                # Double check it's a python process (optional but good sanity check)
                                try:
                                    proc = psutil.Process(pid)
                                    if proc.status() != psutil.STATUS_ZOMBIE:
                                        is_running = True
                                except (psutil.NoSuchProcess, psutil.AccessDenied):
                                    is_running = False
                except Exception as e:
                    print(f"Error checking PID file for {folder_name}: {e}")
            
            agents_status[canvas_id] = is_running

            # Check for agent.status file (for detailed states like "waiting_for_user_input")
            status_file_path = os.path.join(folder_path, "agent.status")
            if os.path.exists(status_file_path):
                try:
                    with open(status_file_path, "r") as f:
                        status_str = f.read().strip()
                        detailed_statuses[canvas_id] = status_str
                except Exception as e:
                    print(f"Error checking status file for {folder_name}: {e}")

            # Check for notification.json
            notif_file = os.path.join(folder_path, "notification.json")
            if os.path.exists(notif_file):
                try:
                    with open(notif_file, "r") as nf:
                        notif_data = json.load(nf)
                        # Ensure agent_id matches canvas_id format if possible, or just pass through
                        notif_data['agent_id'] = canvas_id 
                        notifications.append(notif_data)
                    # Remove the file so we don't alert again
                    try:
                        os.remove(notif_file)
                    except Exception as e:
                        print(f"Error removing notification file {notif_file}: {e}")
                except Exception as e:
                    print(f"Error processing notification for {folder_name}: {e}")
        
        return HttpResponse(json.dumps({
            "success": True,
            "agents": agents_status,
            "detailed_statuses": detailed_statuses,
            "notifications": notifications
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error checking all agents status: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "agents": {},
            "error": str(e)
        }), content_type='application/json', status=500)


def read_agent_log_view(request, agent_name):
    """
    Read the last 100 lines of an agent's log file.
    
    agent_name: e.g., 'monitor-log-1' -> reads 'pool/monitor_log_1/monitor_log_1.log'
    
    Returns JSON: {success, lines: [...], log_file: "..."}
    """
    try:
        # Parse agent_name to get pool folder name
        # agent_name comes in as 'monitor-log-1' -> pool folder is 'monitor_log_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool path
        pool_base_path = get_pool_path(request)
        if not pool_base_path:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Pool directory not found"
            }), content_type='application/json', status=404)
        
        # Log file path: pool/{folder}/{folder}.log
        if base_folder_name == 'flowcreator':
            # FlowCreator always writes to flowcreator.log in its dynamically named directory
            log_file_name = "flowcreator.log"
        else:
            log_file_name = f"{pool_folder_name}.log"
            
        log_file_path = os.path.join(pool_base_path, pool_folder_name, log_file_name)
        
        if not os.path.exists(log_file_path):
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Log file not found: {pool_folder_name}.log",
                "log_file": log_file_path
            }), content_type='application/json')
        
        # Read last 100 lines efficiently (tail-like approach)
        lines = []
        try:
            file_size = os.path.getsize(log_file_path)
            file_mtime = os.path.getmtime(log_file_path)
            
            # For small files (< 64KB), read all at once - it's fast enough
            if file_size < 65536:
                with open(log_file_path, 'r', encoding='utf-8', errors='replace') as f:
                    all_lines = f.readlines()
                    lines = all_lines[-100:] if len(all_lines) > 100 else all_lines
            else:
                # For larger files, read from the end (efficient tail)
                # Estimate: assume average line is ~150 bytes, read 20KB to get ~133 lines
                read_size = min(file_size, 20480)  # 20KB max
                with open(log_file_path, 'rb') as f:
                    # Seek to near the end
                    f.seek(-read_size, 2)  # 2 = os.SEEK_END
                    chunk = f.read()
                    
                # Decode and split
                text = chunk.decode('utf-8', errors='replace')
                all_lines = text.split('\n')
                
                # Skip the first (possibly partial) line if we didn't start at file beginning
                if read_size < file_size:
                    all_lines = all_lines[1:]
                
                lines = all_lines[-100:] if len(all_lines) > 100 else all_lines
            
            # Strip newlines for cleaner JSON
            lines = [line.rstrip('\r\n') for line in lines]
        except Exception as read_err:
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Error reading log file: {str(read_err)}",
                "log_file": log_file_path
            }), content_type='application/json', status=500)
        
        return HttpResponse(json.dumps({
            "success": True,
            "lines": lines,
            "log_file": log_file_path,
            "total_lines": len(lines),
            "mtime": file_mtime  # Include modification time for potential client-side caching
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error reading agent log: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def restart_agent_view(request, agent_name):
    """
    Restart (start) a single agent by running its Python script.
    This is called from the context menu "Restart" option.
    
    agent_name: e.g., 'monitor-log-1' -> runs 'pool/monitor_log_1/monitor_log.py'
    
    Returns JSON: {success, message, pid}
    """
    try:
        # Parse agent_name to get pool folder name
        # agent_name comes in as 'monitor-log-1' -> pool folder is 'monitor_log_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
        
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
        
        # Get pool directory path
        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)
        
        if not os.path.exists(agent_dir):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Agent directory not found: {pool_folder_name}"
            }), content_type='application/json', status=404)
        
        # Find the agent's script (named after base folder, e.g., monitor_log.py)
        script_path = os.path.join(agent_dir, f"{base_folder_name}.py")
        
        if not os.path.exists(script_path):
            return HttpResponse(json.dumps({
                "success": False, 
                "message": f"Agent script not found: {base_folder_name}.py"
            }), content_type='application/json', status=404)
        
        # Step 1: Aggressively kill any running process for this specific agent
        def recursive_kill_agent(pid):
            """Recursively kill a process and all its children."""
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
            except psutil.NoSuchProcess:
                return 0
            
            killed = 0
            # Kill children first
            for child in children:
                try:
                    print(f"[RESTART] Killing child process PID {child.pid} ({child.name()})...")
                    child.kill()
                    killed += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Kill parent
            try:
                print(f"[RESTART] Killing process PID {parent.pid} ({parent.name()})...")
                parent.kill()
                killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            return killed
        
        # Find and kill running processes for this agent
        killed_count = 0
        script_name = f"{base_folder_name}.py"
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline:
                    cmdline_str = ' '.join(cmdline)
                    # Check if this process is running this specific agent
                    if agent_dir in cmdline_str or (script_name in cmdline_str and pool_folder_name in cmdline_str):
                        print(f"[RESTART] Found running agent process PID {proc.info['pid']}: {cmdline_str[:100]}...")
                        killed_count += recursive_kill_agent(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        if killed_count > 0:
            print(f"[RESTART] Killed {killed_count} process(es) for {pool_folder_name}")
            # Brief wait for processes to fully terminate
            time.sleep(0.3)
        
        # Step 2: Delete any .pos files in the agent directory before restarting
        # This ensures a fresh start without stale reanimation position data
        pos_files_deleted = 0
        try:
            for filename in os.listdir(agent_dir):
                if filename.endswith('.pos'):
                    pos_file_path = os.path.join(agent_dir, filename)
                    try:
                        os.remove(pos_file_path)
                        print(f"[RESTART] Deleted .pos file: {pos_file_path}")
                        pos_files_deleted += 1
                    except Exception as del_err:
                        print(f"[RESTART] Warning: Could not delete {pos_file_path}: {del_err}")
        except Exception as scan_err:
            print(f"[RESTART] Warning: Error scanning for .pos files: {scan_err}")
        
        if pos_files_deleted > 0:
            print(f"[RESTART] Cleared {pos_files_deleted} .pos file(s) for {pool_folder_name}")
        
        # Execute the agent
        python_cmd = get_python_command()
        
        if sys.platform.startswith('win'):
            # Windows: create new process group
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            # Unix: start new session
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                start_new_session=True
            )
        
        # Write PID file for fast status checking
        _write_pid_file(agent_dir, process.pid)
        print(f"[RESTART] Started {pool_folder_name} with PID: {process.pid}")
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"Started {pool_folder_name}",
            "pid": process.pid
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error restarting agent: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def clear_pos_files_view(request):
    """
    Clear all .pos (reanimation position) files from the current session's pool directory.
    This is called when the Stop button completes successfully.
    
    SECURITY:
    - Only affects the current session's pool directory (via X-Agent-Session-ID header)
    - Uses get_pool_path() which correctly handles frozen/non-frozen modes
    - Only deletes files with .pos extension
    - Validates paths to prevent directory traversal
    
    Returns JSON: {success, cleared_count, message}
    """
    try:
        # Get the session-specific pool path (handles frozen/non-frozen modes)
        pool_base_path = get_pool_path(request)
        
        if not os.path.exists(pool_base_path):
            return HttpResponse(json.dumps({
                "success": True,
                "cleared_count": 0,
                "message": "Pool directory does not exist"
            }), content_type='application/json')
        
        # Ensure pool_base_path is an absolute, normalized path for safety
        pool_base_path = os.path.normpath(os.path.abspath(pool_base_path))
        
        cleared_count = 0
        errors = []
        
        # Walk through all subdirectories in the session's pool
        for root, dirs, files in os.walk(pool_base_path):
            # Verify we're still within the pool directory (prevent any traversal)
            if not os.path.normpath(os.path.abspath(root)).startswith(pool_base_path):
                print(f"[SECURITY] Skipping directory outside pool: {root}")
                continue
                
            for filename in files:
                # Only delete .pos files
                if filename.endswith('.pos'):
                    file_path = os.path.join(root, filename)
                    
                    # Double-check the file is within the pool directory
                    if not os.path.normpath(os.path.abspath(file_path)).startswith(pool_base_path):
                        print(f"[SECURITY] Skipping file outside pool: {file_path}")
                        continue
                    
                    try:
                        os.remove(file_path)
                        print(f"[CLEAR_POS] Deleted: {file_path}")
                        cleared_count += 1
                    except Exception as del_err:
                        print(f"[CLEAR_POS] Error deleting {file_path}: {del_err}")
                        errors.append(f"{filename}: {str(del_err)}")
        
        if errors:
            return HttpResponse(json.dumps({
                "success": True,
                "cleared_count": cleared_count,
                "message": f"Cleared {cleared_count} .pos file(s) with {len(errors)} error(s)",
                "errors": errors
            }), content_type='application/json')
        
        return HttpResponse(json.dumps({
            "success": True,
            "cleared_count": cleared_count,
            "message": f"Successfully cleared {cleared_count} .pos file(s)"
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error clearing .pos files: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "cleared_count": 0,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def get_session_running_processes_view(request):
    """
    Get all running processes for the current session.
    Returns detailed process info for storing before pause/kill.
    
    Returns JSON: {
        success: boolean,
        processes: [
            {
                canvas_id: string,      # e.g., 'monitor-log-1'
                folder_name: string,    # e.g., 'monitor_log_1'
                pid: int,
                cmdline: string,
                script_name: string     # e.g., 'monitor_log.py'
            }
        ]
    }
    """
    try:
        pool_base_path = get_pool_path(request)
        
        if not os.path.exists(pool_base_path):
            return HttpResponse(json.dumps({
                "success": True,
                "processes": []
            }), content_type='application/json')
        
        # Collect all running processes info
        processes = []
        
        # Iterate through all subdirectories in pool
        for folder_name in os.listdir(pool_base_path):
            folder_path = os.path.join(pool_base_path, folder_name)
            
            if not os.path.isdir(folder_path):
                continue
            
            # Convert pool folder name back to canvas ID
            canvas_id = folder_name.replace('_', '-')
            
            # Determine the script base name
            parts = folder_name.rsplit('_', 1)
            if len(parts) == 2 and parts[1].isdigit():
                base_name = parts[0]
            else:
                base_name = folder_name
            
            script_name = f"{base_name}.py"
            
            # Find running processes for this agent
            for proc in psutil.process_iter(['pid', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline', [])
                    if cmdline:
                        cmdline_str = ' '.join(cmdline)
                        # Check if this process is running from the agent's directory
                        if folder_path in cmdline_str or (script_name in cmdline_str and folder_name in cmdline_str):
                            processes.append({
                                'canvas_id': canvas_id,
                                'folder_name': folder_name,
                                'pid': proc.info['pid'],
                                'cmdline': cmdline_str,
                                'script_name': script_name
                            })
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
        
        return HttpResponse(json.dumps({
            "success": True,
            "processes": processes
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error getting session running processes: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "processes": [],
            "error": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
def kill_session_processes_view(request):
    """
    Aggressively kill ALL processes for the current session.
    Uses recursive kill to terminate entire process trees.
    
    Returns JSON: {
        success: boolean,
        killed_count: int,
        message: string
    }
    """
    try:
        pool_base_path = get_pool_path(request)
        
        if not os.path.exists(pool_base_path):
            return HttpResponse(json.dumps({
                "success": True,
                "killed_count": 0,
                "message": "No pool directory exists"
            }), content_type='application/json')
        
        def recursive_kill(pid):
            """Recursively kill a process and all its children."""
            try:
                parent = psutil.Process(pid)
                children = parent.children(recursive=True)
            except psutil.NoSuchProcess:
                return 0
            
            killed = 0
            # Kill children first
            for child in children:
                try:
                    print(f"[PAUSE-KILL] Killing child process PID {child.pid} ({child.name()})...")
                    child.kill()
                    killed += 1
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Kill parent
            try:
                print(f"[PAUSE-KILL] Killing process PID {parent.pid} ({parent.name()})...")
                parent.kill()
                killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
            
            return killed
        
        killed_count = 0
        
        # Kill processes running from the pool path
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline', [])
                if cmdline:
                    cmdline_str = ' '.join(cmdline)
                    if pool_base_path in cmdline_str:
                        print(f"[PAUSE-KILL] Found target process PID {proc.info['pid']}: {cmdline_str[:80]}...")
                        killed_count += recursive_kill(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        
        # Wait a moment for processes to fully terminate
        if killed_count > 0:
            time.sleep(0.5)
        
        return HttpResponse(json.dumps({
            "success": True,
            "killed_count": killed_count,
            "message": f"Killed {killed_count} process(es)"
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error killing session processes: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "killed_count": 0,
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def restart_agents_view(request):
    """
    Restart agents from stored process info.
    Receives POST with JSON body containing list of agents to restart.
    
    Expected POST body (JSON):
    {
        "agents": [
            {
                "canvas_id": "monitor-log-1",
                "folder_name": "monitor_log_1",
                "script_name": "monitor_log.py"
            }
        ]
    }
    
    Returns JSON: {
        success: boolean,
        restarted: [canvas_id, ...],
        failed: [canvas_id, ...],
        message: string
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        agents_to_restart = data.get('agents', [])
        
        if not agents_to_restart:
            return HttpResponse(json.dumps({
                "success": True,
                "restarted": [],
                "failed": [],
                "message": "No agents to restart"
            }), content_type='application/json')
        
        pool_base_path = get_pool_path(request)
        python_cmd = get_python_command()
        
        restarted = []
        failed = []
        
        for agent in agents_to_restart:
            canvas_id = agent.get('canvas_id', '')
            folder_name = agent.get('folder_name', '')
            script_name = agent.get('script_name', '')
            
            if not folder_name or not script_name:
                failed.append(canvas_id)
                continue
            
            agent_dir = os.path.join(pool_base_path, folder_name)
            script_path = os.path.join(agent_dir, script_name)
            
            if not os.path.exists(script_path):
                print(f"[RESTART] Script not found: {script_path}")
                failed.append(canvas_id)
                continue
            
            try:
                # Start the process
                cmd = python_cmd + [script_path]
                print(f"[RESTART] Starting: {' '.join(cmd)}")
                
                # Use creation flags for Windows to create detached process
                if sys.platform.startswith('win'):
                    CREATE_NO_WINDOW = 0x08000000
                    CREATE_NEW_PROCESS_GROUP = 0x00000200
                    DETACHED_PROCESS = 0x00000008
                    process = subprocess.Popen(
                        cmd,
                        cwd=agent_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                    )
                else:
                    process = subprocess.Popen(
                        cmd,
                        cwd=agent_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True
                    )
                
                # Write PID file
                _write_pid_file(agent_dir, process.pid)
                
                restarted.append(canvas_id)
                print(f"[RESTART] Successfully started: {canvas_id}")
                
            except Exception as start_err:
                print(f"[RESTART] Failed to start {canvas_id}: {start_err}")
                failed.append(canvas_id)
        
        success = len(failed) == 0
        
        return HttpResponse(json.dumps({
            "success": success,
            "restarted": restarted,
            "failed": failed,
            "message": f"Restarted {len(restarted)} agent(s), {len(failed)} failed"
        }), content_type='application/json')
        
    except Exception as e:
        print(f"Error restarting agents: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "restarted": [],
            "failed": [],
            "message": str(e)
        }), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_croner_connection_view(request, agent_name):
    """
    Update a Croner agent's config.yaml when connections are made/removed.
    
    Expected POST body (JSON):
    {
        "connection_type": "source" | "target",
        "connected_agent": "agent-id",  # e.g., "monitor-log-1" or "starter-1"
        "action": "add" | "remove"
    }
    """
    try:
        # Parse request body
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type')
        connected_agent = data.get('connected_agent')
        action = data.get('action', 'add')
        
        if not connection_type or not connected_agent:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Missing arguments"
            }), content_type='application/json', status=400)
            
        # Parse croner agent_name to get pool folder name
        # agent_name comes in as 'croner-1' -> pool folder is 'croner_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        
        base_folder_name = "_".join(parts)
        
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False, 
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)
            
        # Get pool config path
        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(agent_dir, 'config.yaml')
        
        # Auto-deploy fallback if missing (Session Robustness)
        if not os.path.exists(config_path):
            try:
                # Find template source
                source_dir = _find_path(base_folder_name)
                
                if os.path.exists(source_dir):
                    if not os.path.exists(pool_base_path):
                        os.makedirs(pool_base_path, exist_ok=True)
                        
                    import shutil
                    if os.path.exists(agent_dir):
                        shutil.rmtree(agent_dir)
                    shutil.copytree(source_dir, agent_dir)
                    print(f"[AUTO-DEPLOY] Deployed {agent_name} during connection update")
                else:
                    return HttpResponse(json.dumps({
                        "success": False, 
                        "message": f"Config not found and template {base_folder_name} missing"
                    }), content_type='application/json', status=404)
            except Exception as e:
                return HttpResponse(json.dumps({
                    "success": False, 
                    "message": f"Config not found and deploy failed: {e}"
                }), content_type='application/json', status=404)
                
        # Load existing config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
            
        # Parse connected_agent ID to pool folder format
        # e.g., 'monitor-log-1' -> 'monitor_log_1'
        connected_parts = connected_agent.split('-')
        connected_cardinal = None
        if connected_parts[-1].isdigit():
            connected_cardinal = connected_parts.pop()
        
        connected_base = "_".join(connected_parts)
        
        if connected_cardinal:
            connected_pool_name = f"{connected_base}_{connected_cardinal}"
        else:
            connected_pool_name = connected_base
            

        
        if connection_type == 'source':
            # Ensure source_agents list exists (migration from string source_agent)
            if 'source_agents' not in config:
                config['source_agents'] = []
                # Migration: if old source_agent exists, move it to list
                old_source = config.get('source_agent')
                if old_source and isinstance(old_source, str):
                    config['source_agents'].append(old_source)
                # Cleanup old key
                if 'source_agent' in config:
                    del config['source_agent']
            
            if not isinstance(config['source_agents'], list):
                config['source_agents'] = []

            if action == 'add':
                if connected_pool_name not in config['source_agents']:
                    config['source_agents'].append(connected_pool_name)
                    
                    # Only enable if not explicitly disabled by user in config
                    # If it's currently False, assume user meant it.
                    # If it's missing, default true.
                    if config.get('enable_keyword_search', None) is False:
                        pass # User explicitly set false, respect it
                    else:
                        config['enable_keyword_search'] = True
                    
                    # Smart Pattern Detection (unchanged logic, just sets if pattern is empty or generic)
                    # Note: With multiple sources, this might overwrite pattern. 
                    # We'll set it only if current pattern is empty or default.
                    current_pattern = config.get('pattern', '')
                    is_generic = current_pattern in ["", "EVENT DETECTED"]
                    
                    if is_generic:
                        if connected_pool_name.startswith('starter'):
                            config['pattern'] = "STARTER AGENT STARTED"
                        elif connected_pool_name.startswith('ender'):
                            config['pattern'] = "ENDER AGENT FINISHED"
                        else:
                            config['pattern'] = "EVENT DETECTED"
                    

            elif action == 'remove':
                if connected_pool_name in config['source_agents']:
                    config['source_agents'].remove(connected_pool_name)
                    # Disable keyword search if no sources left
                    if not config['source_agents']:
                        config['enable_keyword_search'] = False

                    
        elif connection_type == 'target':
            if 'target_agents' not in config:
                config['target_agents'] = []
            if not isinstance(config['target_agents'], list):
                config['target_agents'] = []
                
            if action == 'add':
                if connected_pool_name not in config['target_agents']:
                    config['target_agents'].append(connected_pool_name)

            elif action == 'remove':
                if connected_pool_name in config['target_agents']:
                    config['target_agents'].remove(connected_pool_name)

        
        # Standard YAML Representer (from other views)
        def str_representer(dumper, data):
            if '\n' in data:
                if not data.endswith('\n'):
                    data = data + '\n'
                return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
            return dumper.represent_scalar('tag:yaml.org,2002:str', data)
        
        yaml.add_representer(str, str_representer)
        
        # Save updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
        return HttpResponse(json.dumps({
            "success": True, 
            "message": f"Updated {agent_name} config",
            "config": config # Return config to match Raiser/others pattern
        }), content_type='application/json')
        
    except json.JSONDecodeError as e:
        return HttpResponse(json.dumps({
            "success": False, 
            "message": f"Invalid JSON: {str(e)}"
        }), content_type='application/json', status=400)
    except Exception as e:
        print(f"Error updating croner connection: {e}")
        return HttpResponse(json.dumps({
            "success": False, 
            "message": str(e)
        }), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_mover_agent_connection(request, agent_name):
    """
    Update a Mover agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    
    Expected POST body (JSON):
    {
        "connection_type": "source" | "target",  # Optional, defaults to source if missing for backward compat
        "connected_agent": "agent-id", # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source') # Default to source
        
        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Get configurations
        # Transform Mover Agent Name -> Pool Path
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        # Transform Connected Agent Name -> Pool Folder Name (for list)
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
             return HttpResponse(json.dumps({'error': 'Mover agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else: # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'
        
        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
             yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Mover connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
def update_sleeper_connection_view(request, agent_name):
    """
    Update Sleeper agent config based on connections.
    """
    if request.method != 'POST':
        return HttpResponse(json.dumps({"success": False, "message": "Invalid method"}), 
                          content_type='application/json', status=405)
    
    try:
        data = json.loads(request.body)
        connection_type = data.get('connection_type') # 'source' or 'target'
        connected_agent = data.get('connected_agent') # ID e.g., 'monitor-log-1'
        action = data.get('action') # 'add' or 'remove'
        
        # Resolve config path
        pool_path = get_pool_path(request)
        if not pool_path:
             return HttpResponse(json.dumps({"success": False, "message": "Pool not found"}), status=404)

        # Parse agent_id to folder name (sleeper-1 -> sleeper_1)
        # agent_name arg is passed from URL
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            agent_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            agent_folder_name = base_folder_name

        agent_dir = os.path.join(pool_path, agent_folder_name)
        config_path = os.path.join(agent_dir, 'config.yaml')

        if not os.path.exists(config_path):
             # Try auto-deploy if missing (copy from template)
             template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'agents', 'sleeper')
             if os.path.exists(template_path):
                 if not os.path.exists(agent_dir):
                     os.makedirs(agent_dir)
                 # Copy template contents
                 for item in os.listdir(template_path):
                     s = os.path.join(template_path, item)
                     d = os.path.join(agent_dir, item)
                     if os.path.isdir(s):
                         if not os.path.exists(d):
                             shutil.copytree(s, d)
                     else:
                         if not os.path.exists(d):
                             shutil.copy2(s, d)
             else:
                 return HttpResponse(json.dumps({"success": False, "message": "Config not found"}), status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected agent to pool name
        c_parts = connected_agent.split('-')
        c_card = None
        if c_parts[-1].isdigit():
            c_card = c_parts.pop()
        c_base = "_".join(c_parts)
        connected_pool_name = f"{c_base}_{c_card}" if c_card else c_base

        if connection_type == 'target':
            if 'target_agents' not in config:
                config['target_agents'] = []
            
            if action == 'add':
                if connected_pool_name not in config['target_agents']:
                    config['target_agents'].append(connected_pool_name)
            elif action == 'remove':
                if connected_pool_name in config['target_agents']:
                    config['target_agents'].remove(connected_pool_name)
        
        elif connection_type == 'source':
             # Sleeper might simply log its source or eventually trigger on event
             # For now, let's keep a list of sources if needed, similar to Mover/Croner
             if 'source_agents' not in config:
                 config['source_agents'] = []
                 
             if action == 'add':
                 if connected_pool_name not in config['source_agents']:
                     config['source_agents'].append(connected_pool_name)
             elif action == 'remove':
                 if connected_pool_name in config['source_agents']:
                     config['source_agents'].remove(connected_pool_name)

        # Save
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": "Updated sleeper config"}), content_type='application/json')


    except Exception as e:
        return HttpResponse(json.dumps({"success": False, "message": str(e)}), status=500)


@csrf_exempt
@require_POST
def update_cleaner_connection_view(request, agent_name):
    """
    Update a Cleaner agent's config.yaml.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connection_type = data.get('connection_type')
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        
        if not all([connection_type, connected_agent, action]):
            return HttpResponse("Missing data", status=400)

        # Get pool directory
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(f"Config not found for agent: {pool_folder_name}", status=404)
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
            
        # Parse connected agent internal name
        target_parts = connected_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        internal_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base
            
        changed = False
        
        # Cleaner inputs are Enders (source_agents)
        # Cleaner outputs are Agents to Start (output_agents)
        
        list_name = 'source_agents' if (connection_type == 'source' or connection_type == 'input') else 'output_agents'
        current_list = config.get(list_name, [])
        
        if action == 'add':
            if internal_name not in current_list:
                current_list.append(internal_name)
                changed = True
        elif action == 'remove':
            if internal_name in current_list:
                current_list.remove(internal_name)
                changed = True
                
        config[list_name] = current_list
        
        if list_name == 'source_agents' and changed:
            # Sync 'agents_to_clean' from connected Enders
            all_agents_to_clean = set()
            for source in config.get('source_agents', []):
                source_path = os.path.join(pool_base_path, source, 'config.yaml')
                if os.path.exists(source_path):
                    try:
                        with open(source_path, 'r', encoding='utf-8') as sf:
                            s_conf = yaml.safe_load(sf)
                            targets = s_conf.get('target_agents', [])
                            for t in targets:
                                all_agents_to_clean.add(t)
                    except Exception:
                        pass
            config['agents_to_clean'] = list(all_agents_to_clean)

        if changed:
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                
        return HttpResponse(json.dumps({"status": "success", "message": "Config updated"}), 
                          content_type='application/json')
                          
    except Exception as e:
        print(f"Error updating cleaner connection: {e}")
        return HttpResponse(json.dumps({"status": "error", "message": str(e)}), 
                          content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_deleter_connection_view(request, agent_name):
    """
    Update a Deleter agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    
    Expected POST body (JSON):
    {
        "connection_type": "source" | "target",
        "connected_agent": "agent-id", # e.g., "monitor-log-1"
        "action": "add" | "remove"
    }
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source') # Default to source
        
        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Get configurations
        # Transform Deleter Agent Name -> Pool Path
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        # Transform Connected Agent Name -> Pool Folder Name (for list)
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
             return HttpResponse(json.dumps({'error': 'Deleter agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else: # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'
        
        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
             yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Deleter connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_executer_connection_view(request, agent_name):
    """
    Update an Executer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')
        
        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Executer agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'
        
        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Executer connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_ssher_connection_view(request, agent_name):
    """
    Update a Ssher agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Ssher agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)

            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)

            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Ssher connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_scper_connection_view(request, agent_name):
    """
    Update a Scper agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Scper agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)

            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)

            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Scper connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_telegramrx_connection_view(request, agent_name):
    """
    Update a Telegramrx agent's config.yaml when connections are made/removed.
    Handles 'source' (input) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Telegramrx agent config not found'}), content_type='application/json', status=404)

        # Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)

            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)

            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        # Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Telegramrx connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_telegramer_connection_view(request, agent_name):
    """
    Update a Telegramer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Telegramer agent config not found'}), content_type='application/json', status=404)

        # Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)

            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)

            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        # Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Telegramer connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_pythonxer_connection_view(request, agent_name):
    """
    Update a Pythonxer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')
        
        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Pythonxer agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'
        
        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Pythonxer connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_whatsapper_connection_view(request, agent_name):
    """
    Update config.yaml for a Whatsapper agent when a connection is made or removed.
    Supports add/remove of source_agents.
    """
    try:
        data = json.loads(request.body)
        connected_agent = data.get('connected_agent')
        action = data.get('action', 'add')
        
        # Fallback for legacy calls that use 'source_agent' key
        if not connected_agent:
            connected_agent = data.get('source_agent')
        
        if not connected_agent:
            return HttpResponse(json.dumps({'status': 'error', 'message': 'No connected_agent provided'}),
                              content_type='application/json', status=400)
        
        # agent_name is the Whatsapper agent (e.g. whatsapper-1)
        if not agent_name.lower().startswith('whatsapper'):
             return HttpResponse("Invalid agent type", status=400)
             
        # Resolve pool path
        pool_base_path = get_pool_path(request)
        
        # Parse agent_name to get pool folder name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(f"Config not found for {agent_name}", status=404)
            
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Resolve connected agent pool name
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        connected_pool_name = f"{conn_base}_{conn_cardinal}" if conn_cardinal else conn_base

        # Handle source_agents list
        list_key = 'source_agents'
        current_list = config.get(list_key, [])
        if isinstance(current_list, str):
            current_list = [s.strip() for s in current_list.split(',') if s.strip()]
        
        changed = False
        if action == 'add':
            if connected_pool_name not in current_list:
                current_list.append(connected_pool_name)
                changed = True
                print(f"[WHATSAPPER] Added {connected_pool_name} to {agent_name} {list_key}")
        elif action == 'remove':
            if connected_pool_name in current_list:
                current_list.remove(connected_pool_name)
                changed = True
                print(f"[WHATSAPPER] Removed {connected_pool_name} from {agent_name} {list_key}")
        
        config[list_key] = current_list
        msg = f'Updated {list_key}: {current_list}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
        return HttpResponse(json.dumps({'status': 'success', 'message': msg, 'changed': changed}), 
                          content_type='application/json')

    except Exception as e:
        print(f"Error updating whatsapper connection: {e}")
        return HttpResponse(f"Error: {str(e)}", status=500)


@csrf_exempt
@require_POST
def update_asker_connection_view(request, agent_name):
    """
    Update config.yaml for an Asker agent when a connection is made or removed.
    Supports add/remove of target_agents_a, target_agents_b, and source_agents.
    The 'connection_type' field determines which list to update:
      - 'target_a' -> target_agents_a
      - 'target_b' -> target_agents_b
      - 'source'   -> source_agents
    """
    try:
        data = json.loads(request.body)
        connection_type = data.get('connection_type', 'source')
        connected_agent = data.get('connected_agent', '')
        action = data.get('action', 'add')

        if not connected_agent:
            return HttpResponse(json.dumps({'status': 'error', 'message': 'No connected_agent provided'}),
                              content_type='application/json', status=400)

        if not agent_name.lower().startswith('asker'):
            return HttpResponse("Invalid agent type", status=400)

        # Resolve pool path
        pool_base_path = get_pool_path(request)

        # Parse agent_name to get pool folder name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(f"Config not found for {agent_name}", status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Resolve connected agent pool name
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        connected_pool_name = f"{conn_base}_{conn_cardinal}" if conn_cardinal else conn_base

        # Determine which list to update
        if connection_type == 'target_a':
            list_key = 'target_agents_a'
        elif connection_type == 'target_b':
            list_key = 'target_agents_b'
        else:
            list_key = 'source_agents'

        current_list = config.get(list_key, [])
        if isinstance(current_list, str):
            current_list = [s.strip() for s in current_list.split(',') if s.strip()]

        changed = False
        if action == 'add':
            if connected_pool_name not in current_list:
                current_list.append(connected_pool_name)
                changed = True
                print(f"[ASKER] Added {connected_pool_name} to {agent_name} {list_key}")
        elif action == 'remove':
            if connected_pool_name in current_list:
                current_list.remove(connected_pool_name)
                changed = True
                print(f"[ASKER] Removed {connected_pool_name} from {agent_name} {list_key}")

        config[list_key] = current_list
        msg = f'Updated {list_key}: {current_list}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg, 'changed': changed}),
                          content_type='application/json')

    except Exception as e:
        print(f"Error updating asker connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_forker_connection_view(request, agent_name):
    """
    Update config.yaml for a Forker agent when a connection is made or removed.
    Supports add/remove of target_agents_a, target_agents_b, and source_agents.
    The 'connection_type' field determines which list to update:
      - 'target_a' -> target_agents_a
      - 'target_b' -> target_agents_b
      - 'source'   -> source_agents
    """
    try:
        data = json.loads(request.body)
        connection_type = data.get('connection_type', 'source')
        connected_agent = data.get('connected_agent', '')
        action = data.get('action', 'add')

        if not connected_agent:
            return HttpResponse(json.dumps({'status': 'error', 'message': 'No connected_agent provided'}),
                              content_type='application/json', status=400)

        if not agent_name.lower().startswith('forker'):
            return HttpResponse("Invalid agent type", status=400)

        # Resolve pool path
        pool_base_path = get_pool_path(request)

        # Parse agent_name to get pool folder name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(f"Config not found for {agent_name}", status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Resolve connected agent pool name
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        connected_pool_name = f"{conn_base}_{conn_cardinal}" if conn_cardinal else conn_base

        # Determine which list to update
        if connection_type == 'target_a':
            list_key = 'target_agents_a'
        elif connection_type == 'target_b':
            list_key = 'target_agents_b'
        else:
            list_key = 'source_agents'

        current_list = config.get(list_key, [])
        if isinstance(current_list, str):
            current_list = [s.strip() for s in current_list.split(',') if s.strip()]

        changed = False
        if action == 'add':
            if connected_pool_name not in current_list:
                current_list.append(connected_pool_name)
                changed = True
                print(f"[FORKER] Added {connected_pool_name} to {agent_name} {list_key}")
        elif action == 'remove':
            if connected_pool_name in current_list:
                current_list.remove(connected_pool_name)
                changed = True
                print(f"[FORKER] Removed {connected_pool_name} from {agent_name} {list_key}")

        config[list_key] = current_list
        msg = f'Updated {list_key}: {current_list}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg, 'changed': changed}),
                          content_type='application/json')

    except Exception as e:
        print(f"Error updating forker connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def asker_choice_view(request, agent_name):
    """
    Receive the user's A/B choice from the frontend dialog and write it
    to choice.txt in the agent's pool directory so the running asker.py can read it.
    """
    try:
        data = json.loads(request.body)
        choice = data.get('choice', '').upper()

        if choice not in ('A', 'B'):
            return HttpResponse(json.dumps({'status': 'error', 'message': 'Invalid choice, must be A or B'}),
                              content_type='application/json', status=400)

        if not agent_name.lower().startswith('asker'):
            return HttpResponse("Invalid agent type", status=400)

        # Resolve pool path
        pool_base_path = get_pool_path(request)

        # Parse agent_name to get pool folder name
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name

        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        choice_path = os.path.join(pool_dir, 'choice.txt')

        if not os.path.exists(pool_dir):
            return HttpResponse(f"Pool dir not found for {agent_name}", status=404)

        with open(choice_path, 'w', encoding='utf-8') as f:
            f.write(choice)

        print(f"[ASKER] User chose Path {choice} for {agent_name}")
        return HttpResponse(json.dumps({'success': True, 'message': f'Choice {choice} written'}),
                          content_type='application/json')

    except Exception as e:
        print(f"Error processing asker choice: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_recmailer_connection_view(request, agent_name):
    """
    Update a Recmailer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) connections.
    """
    try:
        # 1. Parse request
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')
        
        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # 2. Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        if cardinal:
            pool_folder_name = f"{base_folder_name}_{cardinal}"
        else:
            pool_folder_name = base_folder_name
            
        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        if conn_cardinal:
            conn_pool_name = f"{conn_base}_{conn_cardinal}"
        else:
            conn_pool_name = conn_base

        # 3. Path setup
        pool_base_path = get_pool_path(request)
        pool_dir = os.path.join(pool_base_path, pool_folder_name)
        config_path = os.path.join(pool_dir, 'config.yaml')
        
        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': 'Recmailer agent config not found'}), content_type='application/json', status=404)

        # 4. Load Config
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # 5. Modify Config
        
        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []

            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'

        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []

            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'
        
        # 6. Save Config
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Recmailer connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_shoter_connection_view(request, agent_name):
    """
    Update a Shoter agent's config.yaml when connections are made/removed.

    Expected POST body (JSON):
    {
        "target_agent": "agent-id",  # e.g., "sleeper-1"
        "action": "add" | "remove"
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')

        if not target_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing target_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'shoter-1' -> 'shoter_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()

        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)

        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Shoter config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse target_agent to pool folder name: 'sleeper-1' -> 'sleeper_1'
        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()

        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        if 'target_agents' not in config or not isinstance(config['target_agents'], list):
            config['target_agents'] = []

        if action == 'add':
            if target_pool_name not in config['target_agents']:
                config['target_agents'].append(target_pool_name)
            message = f"Added {target_pool_name} to target_agents"
        elif action == 'remove':
            if target_pool_name in config['target_agents']:
                config['target_agents'].remove(target_pool_name)
            message = f"Removed {target_pool_name} from target_agents"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')

    except Exception as e:
        print(f"Error updating Shoter connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)

@csrf_exempt
@csrf_exempt
@require_POST
def update_sqler_connection_view(request, agent_name):
    """
    Update a Sqler agent's config.yaml when connections are made/removed.

    Expected POST body (JSON):
    {
        "connected_agent": "agent-id",  # e.g., "emailer-1"
        "action": "add" | "remove",
        "connection_type": "source" | "target"
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'sqler-1' -> 'sqler_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()

        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        # Security check
        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Invalid agent name"
            }), content_type='application/json', status=400)

        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Sqler config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name: 'sleeper-1' -> 'sleeper_1'
        target_parts = connected_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()

        target_base = "_".join(target_parts)
        connected_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base
        
        # Determine which list to update
        list_key = 'source_agents' if connection_type == 'source' else 'target_agents'

        if list_key not in config or not isinstance(config[list_key], list):
            config[list_key] = []

        if action == 'add':
            if connected_pool_name not in config[list_key]:
                config[list_key].append(connected_pool_name)
            message = f"Added {connected_pool_name} to {list_key}"
        elif action == 'remove':
            if connected_pool_name in config[list_key]:
                config[list_key].remove(connected_pool_name)
            message = f"Removed {connected_pool_name} from {list_key}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')

    except Exception as e:
        print(f"Error updating Sqler connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_prompter_connection_view(request, agent_name):
    """
    Update a Prompter agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        conn_pool_name = f"{conn_base}_{conn_cardinal}" if conn_cardinal else conn_base

        # Path setup
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': f'Prompter config not found: {config_path}'}), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []
            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'
        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []
            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Prompter connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_gitter_connection_view(request, agent_name):
    """
    Update a Gitter agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        conn_pool_name = f"{conn_base}_{conn_cardinal}" if conn_cardinal else conn_base

        # Path setup
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': f'Gitter config not found: {config_path}'}), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []
            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'
        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []
            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Gitter connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_dockerer_connection_view(request, agent_name):
    """
    Update a Dockerer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent')
        action = data.get('action')
        connection_type = data.get('connection_type', 'source')

        if not connected_agent or not action:
            return HttpResponse(json.dumps({'error': 'Missing required fields'}), content_type='application/json', status=400)

        # Transform agent names to pool folder names
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        conn_parts = connected_agent.split('-')
        conn_cardinal = None
        if conn_parts[-1].isdigit():
            conn_cardinal = conn_parts.pop()
        conn_base = "_".join(conn_parts)
        conn_pool_name = f"{conn_base}_{conn_cardinal}" if conn_cardinal else conn_base

        # Path setup
        pool_base_path = get_pool_path(request)
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({'error': f'Dockerer config not found: {config_path}'}), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        if connection_type == 'target':
            target_agents = config.get('target_agents', [])
            if not isinstance(target_agents, list):
                target_agents = []
            if action == 'add':
                if conn_pool_name not in target_agents:
                    target_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in target_agents:
                    target_agents.remove(conn_pool_name)
            config['target_agents'] = target_agents
            msg = f'Updated target_agents: {target_agents}'
        else:  # source
            source_agents = config.get('source_agents', [])
            if not isinstance(source_agents, list):
                source_agents = []
            if action == 'add':
                if conn_pool_name not in source_agents:
                    source_agents.append(conn_pool_name)
            elif action == 'remove':
                if conn_pool_name in source_agents:
                    source_agents.remove(conn_pool_name)
            config['source_agents'] = source_agents
            msg = f'Updated source_agents: {source_agents}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Dockerer connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)



@csrf_exempt
def execute_flowcreator_view(request, agent_name):
    """
    Execute a FlowCreator agent by running its Python script.
    Called when Save is clicked in the FlowCreator config dialog.
    """
    try:
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        if '..' in pool_folder_name or '/' in pool_folder_name or '\\' in pool_folder_name:
            return HttpResponse(json.dumps({"success": False, "message": "Invalid agent name"}),
                                content_type='application/json', status=400)

        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)

        if not os.path.exists(agent_dir):
            return HttpResponse(json.dumps({"success": False, "message": f"Agent directory not found: {pool_folder_name}"}),
                                content_type='application/json', status=404)

        script_path = os.path.join(agent_dir, f"{base_folder_name}.py")
        if not os.path.exists(script_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Agent script not found: {base_folder_name}.py"}),
                                content_type='application/json', status=404)

        # Remove old flow_result.json before starting
        result_file = os.path.join(agent_dir, "flow_result.json")
        if os.path.exists(result_file):
            os.remove(result_file)

        python_cmd = get_python_command()
        agent_env = get_agent_env()

        if sys.platform.startswith('win'):
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                start_new_session=True
            )

        _write_pid_file(agent_dir, process.pid)
        print(f"[FLOWCREATOR] Started {pool_folder_name} with PID: {process.pid}")

        return HttpResponse(json.dumps({"success": True, "message": f"Started {pool_folder_name}", "pid": process.pid}),
                            content_type='application/json')
    except Exception as e:
        print(f"Error executing flowcreator agent: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({"success": False, "message": str(e)}),
                            content_type='application/json', status=500)


@csrf_exempt
def check_flowcreator_result_view(request, agent_name):
    """
    Check if the FlowCreator agent has finished and return the flow_result.json.
    Returns 202 if still running, 200 with result if done, 500 on error.
    """
    try:
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        pool_base_path = get_pool_path(request)
        agent_dir = os.path.join(pool_base_path, pool_folder_name)

        result_file = os.path.join(agent_dir, "flow_result.json")

        if not os.path.exists(result_file):
            # Check if agent is still running
            pid_file = os.path.join(agent_dir, "agent.pid")
            if os.path.exists(pid_file):
                return HttpResponse(json.dumps({"status": "running"}),
                                    content_type='application/json', status=202)
            # PID gone but no result - agent crashed without writing result
            return HttpResponse(json.dumps({"status": "error", "message": "Agent exited without producing a result. Check the agent log for details.", "nodes": [], "connections": []}),
                                content_type='application/json', status=200)

        with open(result_file, 'r', encoding='utf-8') as f:
            result = json.load(f)

        return HttpResponse(json.dumps(result), content_type='application/json')
    except Exception as e:
        print(f"Error checking flowcreator result: {e}")
        return HttpResponse(json.dumps({"status": "error", "message": str(e)}),
                            content_type='application/json', status=500)


@csrf_exempt
def clean_pool_except_view(request, agent_name):
    """
    Clean the pool directory EXCEPT the specified agent.
    Used by FlowCreator to clean all agents except itself before regenerating.
    """
    try:
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        pool_base_path = get_pool_path(request)

        if not os.path.exists(pool_base_path):
            return HttpResponse(json.dumps({"status": "success", "message": "Pool directory does not exist"}),
                                content_type='application/json')

        # Kill all running agents except the specified one
        removed_count = 0
        for item in os.listdir(pool_base_path):
            item_path = os.path.join(pool_base_path, item)
            if not os.path.isdir(item_path):
                continue
            if item == pool_folder_name:
                continue  # Skip the FlowCreator instance

            # Kill any running processes in this directory
            pid_file = os.path.join(item_path, "agent.pid")
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, 'r') as f:
                        pid = int(f.read().strip())
                    import psutil
                    if psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        proc.terminate()
                        proc.wait(timeout=5)
                except Exception:
                    pass

            # Remove the directory
            try:
                shutil.rmtree(item_path)
                removed_count += 1
            except Exception as e:
                print(f"Failed to remove {item_path}: {e}")

        return HttpResponse(json.dumps({"status": "success", "removed": removed_count}),
                            content_type='application/json')
    except Exception as e:
        print(f"Error cleaning pool except {agent_name}: {e}")
        return HttpResponse(json.dumps({"status": "error", "message": str(e)}),
                            content_type='application/json', status=500)

