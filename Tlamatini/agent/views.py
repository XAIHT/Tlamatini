from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.contrib.auth.decorators import login_required
from .models import AgentMessage
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
import json
import os
import sys
from typing import Optional
from .models import LLMProgram, LLMSnippet, Prompt, Omission, Mcp, Tool, Agent, SessionState, Skill
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import shutil
import psutil
import threading
import traceback
import yaml
import subprocess
import queue as _queue
import time
import re

from .chat_agent_runtime import CHAT_RUNTIME_ROOT_NAME
from .config_loader import load_config, save_config_updates
from .services.agent_contracts import (
    get_parametrizer_source_fields,
    list_contract_summaries,
)
from .services.agent_paths import pool_name_to_agent_type
from .services.flow_compiler import (
    compile_flow_payload,
    dump_agent_config_yaml,
    list_pool_agents_for_validation,
)
from .services.flow_spec import normalize_flow_payload, flow_spec_to_legacy_json


def _normalize_agent_purpose_key(value: str) -> str:
    """Normalize agent identifiers so README rows and canvas names resolve to the same key."""
    return re.sub(r'[^a-z0-9]+', '', (value or '').lower())


def _resolve_agent_descriptions_search_paths() -> list[str]:
    """
    Build the ordered list of locations to probe for the workflow-agents
    description tables. ``agents_descriptions.md`` is the authoritative
    source; ``README.md`` is kept as a legacy fallback so older deployments
    that haven't been re-bundled yet still produce tooltips.

    The list works for both source-mode (file lives at the repo root next to
    ``manage.py``) and frozen-mode (file is copied next to the executable
    by ``build.py`` and resolved via ``sys.executable``'s directory).
    """
    candidates: list[str] = []

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    candidates.extend([
        os.path.join(project_root, 'agents_descriptions.md'),
        os.path.join(project_root, 'README.md'),
    ])

    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend([
            os.path.join(exe_dir, 'agents_descriptions.md'),
            os.path.join(exe_dir, 'README.md'),
        ])

    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in candidates:
        normalized = os.path.normcase(os.path.abspath(candidate))
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(candidate)
    return ordered


def _parse_agent_purpose_map(lines) -> dict[str, str]:
    """
    Parse a Markdown stream and extract every ``## Workflow Agents`` table
    row of the form ``| **Name** | <description> |``. The resulting map is
    keyed by an alphanumeric-normalized agent identifier.
    """
    purpose_map: dict[str, str] = {}
    in_workflow_agents_section = False
    row_pattern = re.compile(r'^\|\s*\*\*(.+?)\*\*\s*\|\s*(.+?)\s*\|')

    for raw_line in lines:
        line = raw_line.strip()

        if line == '## Workflow Agents':
            in_workflow_agents_section = True
            continue

        if in_workflow_agents_section and line.startswith('## ') and line != '## Workflow Agents':
            break

        if not in_workflow_agents_section:
            continue

        match = row_pattern.match(line)
        if not match:
            continue

        agent_name = match.group(1).strip()
        purpose = match.group(2).strip()
        normalized_key = _normalize_agent_purpose_key(agent_name)

        if normalized_key and purpose:
            purpose_map[normalized_key] = purpose

    return purpose_map


def _load_agent_purpose_map() -> dict[str, str]:
    """
    Load the Workflow Agents description map from the first available source.
    Probes ``agents_descriptions.md`` first (authoritative) and falls back to
    ``README.md`` for backward compatibility, in both source-mode and
    frozen-mode locations.
    """
    last_error: Optional[Exception] = None
    for path in _resolve_agent_descriptions_search_paths():
        try:
            with open(path, 'r', encoding='utf-8') as handle:
                lines = handle.readlines()
        except OSError as exc:
            last_error = exc
            continue

        purpose_map = _parse_agent_purpose_map(lines)
        if purpose_map:
            return purpose_map

    if last_error is not None:
        print(f"Warning: Could not load agent purposes from any known source: {last_error}")
    return {}


# Legacy alias preserved so any out-of-tree callers (e.g. dev scripts or
# scheduled remote agents that imported the old name) keep working.
_load_agent_purpose_map_from_readme = _load_agent_purpose_map

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
    messages = AgentMessage.objects.filter(conversation_user=request.user).order_by('timestamp')
    initial_messages = [
        {
            'username': m.user.username,
            'message': m.message,
            'timestamp': m.timestamp.strftime('%Y/%m/%d %H:%M:%S.%f')[:-3] if m.timestamp else '',
        }
        for m in messages
    ]

    # Resolve ollama_base_url through config_loader so source AND frozen builds
    # read from the same file the Config dialogs save to. Hardcoding __file__
    # here used to ship the stale bundled copy in frozen mode and would
    # silently desync from a freshly-saved <exe_dir>/config.json.
    ollama_base_url = 'http://localhost:11434'
    try:
        config = load_config(force_reload=True)
        ollama_base_url = config.get('ollama_base_url', ollama_base_url)
    except Exception as e:
        print(f"Warning: Could not load ollama_base_url via config_loader: {e}")

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

def list_all_agent_descriptions_view(request):
    # Used by the chat UI's "Create Flow" gate to validate that every
    # canonical agent name produced from the tool-calls log corresponds
    # to a real entry in the Agents sidebar. Returns a JSON array of
    # agentDescription strings (the same value the sidebar shows).
    descriptions = list(
        Agent.objects.order_by('idAgent').values_list('agentDescription', flat=True)
    )
    return JsonResponse({'descriptions': descriptions})

@login_required
def agentic_control_panel(request):
    # Resolve ollama_base_url through config_loader so source AND frozen builds
    # read from the same file the Config dialogs save to. Hardcoding __file__
    # here used to ship the stale bundled copy in frozen mode and would
    # silently desync from a freshly-saved <exe_dir>/config.json.
    ollama_base_url = 'http://localhost:11434'
    try:
        config = load_config(force_reload=True)
        ollama_base_url = config.get('ollama_base_url', ollama_base_url)
    except Exception as e:
        print(f"Warning: Could not load ollama_base_url via config_loader: {e}")

    context = {
        'ollama_base_url': ollama_base_url,
        'agent_purpose_map': _load_agent_purpose_map(),
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


def _parse_canvas_agent_name(agent_name: str) -> tuple[str, str]:
    """
    Convert a canvas agent id like 'monitor-log-1' into:
    ('monitor_log', 'monitor_log_1')
    """
    parts = (agent_name or '').split('-')
    cardinal = None
    if parts and parts[-1].isdigit():
        cardinal = parts.pop()

    base_folder_name = "_".join(part for part in parts if part)
    pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

    if (
        not base_folder_name
        or '..' in pool_folder_name
        or '/' in pool_folder_name
        or '\\' in pool_folder_name
    ):
        raise ValueError("Invalid agent name")

    return base_folder_name, pool_folder_name


def _resolve_canvas_agent_directory(request, agent_name: str) -> str:
    """
    Resolve the deployed directory for a canvas agent instance in the current session.
    Uses get_pool_path(), so frozen and non-frozen layouts are handled consistently.
    """
    _, pool_folder_name = _parse_canvas_agent_name(agent_name)
    pool_path = os.path.realpath(get_pool_path(request))
    agent_dir = os.path.realpath(os.path.join(pool_path, pool_folder_name))

    try:
        if os.path.commonpath([pool_path, agent_dir]) != pool_path:
            raise ValueError("Invalid agent name")
    except ValueError as exc:
        raise ValueError("Invalid agent name") from exc

    if not os.path.isdir(agent_dir):
        raise FileNotFoundError(f"Agent directory not found: {pool_folder_name}")

    return agent_dir

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

        # Sanitize Ender config: remove any unknown keys (e.g., corrupted "utput_agents")
        if base_folder_name == 'ender':
            ender_known_keys = {'target_agents', 'source_agents', 'output_agents'}
            merged_config = {k: v for k, v in merged_config.items() if k in ender_known_keys}

        # Sanitize TeleTlamatini config: drop legacy user-account-mode keys that
        # are now dead weight (Telegramer / TelegramRX cover that direction).
        # Without this, deep_merge would preserve `telegram.listen_chat` and the
        # whole `access.*` block forever in pool configs from older deploys.
        if base_folder_name == 'teletlamatini':
            tg = merged_config.get('telegram')
            if isinstance(tg, dict) and 'listen_chat' in tg:
                tg.pop('listen_chat', None)
            # The old `access:` block held 9 customizable strings; the new
            # agent uses hardcoded user-facing strings and reads only the
            # password (which it also accepts at top-level). Migrate the
            # password if needed and drop the rest.
            access = merged_config.get('access')
            if isinstance(access, dict):
                pwd_from_access = access.get('password')
                if pwd_from_access and not merged_config.get('password'):
                    merged_config['password'] = pwd_from_access
                merged_config.pop('access', None)
            # The old `llm:` block has been replaced by `completeness_check:`.
            # Migrate fields if user hasn't already set the new shape.
            llm_legacy = merged_config.get('llm')
            cc = merged_config.get('completeness_check') or {}
            if isinstance(llm_legacy, dict) and not cc:
                merged_config['completeness_check'] = {
                    'enabled': False,
                    'host': llm_legacy.get('host', 'http://localhost:11434'),
                    'model': llm_legacy.get('model', 'llama3'),
                    'instruction': llm_legacy.get('understanding_prompt', ''),
                }
                merged_config.pop('llm', None)
            # `poll_interval` was unused — drop.
            merged_config.pop('poll_interval', None)

        # Sanitize WhatsTlamatini config: same idea as TeleTlamatini — drop
        # the legacy `access:` text-overrides block, migrate the password if
        # present, and migrate any legacy `llm:` block into the new
        # `completeness_check:` shape. Also drop unused `poll_interval`.
        if base_folder_name == 'whatstlamatini':
            access = merged_config.get('access')
            if isinstance(access, dict):
                pwd_from_access = access.get('password')
                if pwd_from_access and not merged_config.get('password'):
                    merged_config['password'] = pwd_from_access
                merged_config.pop('access', None)
            llm_legacy = merged_config.get('llm')
            cc = merged_config.get('completeness_check') or {}
            if isinstance(llm_legacy, dict) and not cc:
                merged_config['completeness_check'] = {
                    'enabled': False,
                    'host': llm_legacy.get('host', 'http://localhost:11434'),
                    'model': llm_legacy.get('model', 'llama3'),
                    'instruction': llm_legacy.get('understanding_prompt', ''),
                }
                merged_config.pop('llm', None)
            merged_config.pop('poll_interval', None)

        # Centralized dump path: handles multiline-string literal-block style
        # AND force-double-quotes any registered password field for the agent
        # (e.g. emailer's smtp.password, recmailer's imap.password). Using the
        # shared helper keeps the canvas item-dialog save, the .flw deploy,
        # the Start sequence, and the connection-update views in lockstep.
        dump_agent_config_yaml(merged_config, config_path, base_folder_name)

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

        # Save updated config via the shared dump helper so the SMTP password
        # (declared as `password_paths=("smtp.password",)` on the emailer
        # contract) is force-double-quoted on every write — including this
        # connection-update path, not just FlowCreator's compile path.
        dump_agent_config_yaml(config, config_path, 'emailer')

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
        "source_agent": "agent-id",       # e.g., "raiser-1"
        "action": "add" | "remove",
        "connection_type": "input" | "target" | "output"
    }

    connection_type determines which config list is modified:
      - "input"  -> source_agents (graphical connections only, never killed/started)
      - "target" -> target_agents (agents to KILL)
      - "output" -> output_agents (agents to LAUNCH, e.g. Cleaners)
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
        # 'input' -> source_agents (graphical connections only)
        # 'target' -> target_agents (agents to kill)
        # 'output' -> output_agents (agents to launch, e.g. Cleaners)
        list_name = 'source_agents'
        if connection_type == 'output':
            list_name = 'output_agents'
        elif connection_type == 'target':
            list_name = 'target_agents'
        
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
            "target_agents": config.get('target_agents', []),
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
            # Windows: detached, no console — without CREATE_NO_WINDOW the
            # child python.exe would inherit a console and leave conhost.exe
            # orphans bearing the Tlamatini icon when the request finishes.
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                    | subprocess.DETACHED_PROCESS
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
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
        
        python_cmd = get_python_command()
        agent_env = get_agent_env()
        
        if sys.platform.startswith('win'):
            # Windows: detached, no console — without CREATE_NO_WINDOW the
            # child python.exe would inherit a console and leave conhost.exe
            # orphans bearing the Tlamatini icon when the request finishes.
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                    | subprocess.DETACHED_PROCESS
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
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

        log_file_path = os.path.join(agent_dir, f"{pool_folder_name}.log")
        time.sleep(0.2)
        exit_code = process.poll()
        if exit_code is not None and not os.path.exists(log_file_path):
            try:
                os.remove(os.path.join(agent_dir, "agent.pid"))
            except OSError:
                pass
            return HttpResponse(json.dumps({
                "success": False,
                "message": (
                    f"{pool_folder_name} exited before creating its log "
                    f"(exit code {exit_code}). Check Python/PYTHON_HOME dependencies."
                ),
                "pid": process.pid
            }), content_type='application/json', status=500)
        
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
            if folder_name == CHAT_RUNTIME_ROOT_NAME:
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


_CHAT_RUNTIME_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+_\d{3,}_[0-9a-f]{6,}$")


def _get_chat_runtime_root_path() -> str:
    """Resolve the absolute path to the chat-runtime root (_chat_runs_).
    Mirrors chat_agent_runtime.get_chat_runtime_root() but without importing
    that module's logging side effects each time."""
    if getattr(sys, "frozen", False):
        agents_root = os.path.join(os.path.dirname(sys.executable), "agents")
    else:
        agents_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")
    return os.path.join(agents_root, "pools", CHAT_RUNTIME_ROOT_NAME)


def _is_valid_chat_runtime_name(name: str) -> bool:
    """Validate a chat-runtime directory name to prevent path traversal."""
    if not name or os.sep in name or "/" in name or ".." in name:
        return False
    return bool(_CHAT_RUNTIME_NAME_PATTERN.match(name))


def _resolve_chat_runtime_dir(runtime_name: str) -> Optional[str]:
    """Return the absolute path to a chat-runtime dir if it exists and is
    contained inside the chat-runtime root. Returns None otherwise."""
    if not _is_valid_chat_runtime_name(runtime_name):
        return None
    root = _get_chat_runtime_root_path()
    candidate = os.path.abspath(os.path.join(root, runtime_name))
    try:
        common = os.path.commonpath([os.path.abspath(root), candidate])
    except ValueError:
        return None
    if common != os.path.abspath(root):
        return None
    if not os.path.isdir(candidate):
        return None
    return candidate


@csrf_exempt
def check_chat_runtimes_status_view(request):
    """
    Scan _chat_runs_ for currently-running chat-agent runtimes and surface
    Asker `waiting_for_user_input` statuses + Notifier `notification.json`
    payloads to the chat page poller.

    Returns JSON: {
        success: bool,
        runtimes: { <runtime_name>: { is_running, status?, notification? } }
    }
    """
    try:
        runtime_root = _get_chat_runtime_root_path()
        runtimes: dict = {}

        if not os.path.isdir(runtime_root):
            return HttpResponse(json.dumps({
                "success": True,
                "runtimes": {}
            }), content_type='application/json')

        for entry_name in os.listdir(runtime_root):
            entry_path = os.path.join(runtime_root, entry_name)
            if not os.path.isdir(entry_path):
                continue

            info: dict = {"is_running": False}

            # PID liveness
            pid_file_path = os.path.join(entry_path, "agent.pid")
            if os.path.exists(pid_file_path):
                try:
                    with open(pid_file_path, "r") as f:
                        pid_str = f.read().strip()
                    if pid_str.isdigit():
                        pid = int(pid_str)
                        if psutil.pid_exists(pid):
                            try:
                                proc = psutil.Process(pid)
                                if proc.status() != psutil.STATUS_ZOMBIE:
                                    info["is_running"] = True
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                except Exception as exc:
                    print(f"Error reading PID for {entry_name}: {exc}")

            # Detailed status (e.g., Asker waiting for input)
            status_file_path = os.path.join(entry_path, "agent.status")
            if os.path.exists(status_file_path):
                try:
                    with open(status_file_path, "r") as f:
                        info["status"] = f.read().strip()
                except Exception as exc:
                    print(f"Error reading status for {entry_name}: {exc}")

            # Notifier payload (consumed-once: file is removed after read)
            notif_file_path = os.path.join(entry_path, "notification.json")
            if os.path.exists(notif_file_path):
                try:
                    with open(notif_file_path, "r", encoding="utf-8") as nf:
                        notif_data = json.load(nf)
                    notif_data['runtime_name'] = entry_name
                    info["notification"] = notif_data
                    try:
                        os.remove(notif_file_path)
                    except Exception as exc:
                        print(f"Error removing notification {notif_file_path}: {exc}")
                except Exception as exc:
                    print(f"Error reading notification for {entry_name}: {exc}")

            # Skip purely idle, signal-less runtimes to keep the response small.
            if info["is_running"] or "status" in info or "notification" in info:
                runtimes[entry_name] = info

        return HttpResponse(json.dumps({
            "success": True,
            "runtimes": runtimes
        }), content_type='application/json')

    except Exception as e:
        print(f"Error checking chat runtimes status: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "runtimes": {},
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

def _find_agent_processes_for_restart(agent_dir, pool_folder_name, script_name):
    """Find all running processes that belong to a deployed agent instance."""
    processes = []
    seen_pids = set()

    is_windows = sys.platform.startswith('win')
    agent_dir_normalized = agent_dir.lower() if is_windows else agent_dir
    pool_folder_normalized = pool_folder_name.lower() if is_windows else pool_folder_name
    script_name_normalized = script_name.lower() if is_windows else script_name

    for proc in psutil.process_iter(['pid', 'cmdline', 'cwd']):
        try:
            cmdline = proc.info.get('cmdline', []) or []
            proc_cwd = proc.info.get('cwd', '') or ''
            cmdline_str = ' '.join(str(part) for part in cmdline)

            cmdline_check = cmdline_str.lower() if is_windows else cmdline_str
            cwd_check = proc_cwd.lower() if is_windows else proc_cwd

            cmdline_dir_match = agent_dir_normalized in cmdline_check
            cmdline_script_match = (
                script_name_normalized in cmdline_check and
                pool_folder_normalized in cmdline_check
            )
            cwd_match = agent_dir_normalized in cwd_check

            if (cmdline_dir_match or cmdline_script_match or cwd_match) and proc.pid not in seen_pids:
                processes.append(proc)
                seen_pids.add(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    return processes


def _terminate_process_tree_for_restart(proc, graceful_timeout=3.0, kill_timeout=3.0):
    """Terminate a process tree and wait until it is gone."""
    try:
        parent = psutil.Process(proc.pid)
    except psutil.NoSuchProcess:
        return True

    try:
        children = parent.children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        children = []

    targets = []
    seen_pids = set()
    for target in children + [parent]:
        if target.pid not in seen_pids:
            targets.append(target)
            seen_pids.add(target.pid)

    for child in children:
        try:
            print(f"[RESTART] Terminating child process PID {child.pid} ({child.name()})...")
            child.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    try:
        print(f"[RESTART] Terminating process PID {parent.pid} ({parent.name()})...")
        parent.terminate()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    _, alive = psutil.wait_procs(targets, timeout=graceful_timeout)

    if alive:
        for target in alive:
            try:
                print(f"[RESTART] Force killing PID {target.pid} ({target.name()})...")
                target.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        _, alive = psutil.wait_procs(alive, timeout=kill_timeout)

    return not alive


def _stop_running_agent_processes_for_restart(agent_dir, pool_folder_name, script_name):
    """
    Ensure a matching agent instance is fully stopped before restart.
    Returns (success, stopped_count, error_message).
    """
    stopped_pids = set()

    for attempt in range(4):
        processes = _find_agent_processes_for_restart(agent_dir, pool_folder_name, script_name)
        if not processes:
            return True, len(stopped_pids), None

        for proc in processes:
            stopped_pids.add(proc.pid)
            print(f"[RESTART] Found running agent process PID {proc.pid} on attempt {attempt + 1}.")
            _terminate_process_tree_for_restart(proc)

        time.sleep(0.2)

    remaining = _find_agent_processes_for_restart(agent_dir, pool_folder_name, script_name)
    if remaining:
        remaining_pids = [proc.pid for proc in remaining]
        return (
            False,
            len(stopped_pids),
            f"Agent '{pool_folder_name}' could not be fully stopped before restart. Remaining PID(s): {remaining_pids}",
        )

    return True, len(stopped_pids), None


@csrf_exempt
def restart_agent_view(request, agent_name):
    """
    Restart a single agent by fully stopping its current process tree, then starting it again.
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
        
        script_name = f"{base_folder_name}.py"
        stop_ok, killed_count, stop_error = _stop_running_agent_processes_for_restart(
            agent_dir,
            pool_folder_name,
            script_name,
        )
        if not stop_ok:
            return HttpResponse(json.dumps({
                "success": False,
                "message": stop_error,
                "killed_count": killed_count,
            }), content_type='application/json', status=409)

        if killed_count > 0:
            print(f"[RESTART] Confirmed stop of {killed_count} process(es) for {pool_folder_name}")
        else:
            print(f"[RESTART] No running process found for {pool_folder_name}; starting fresh.")
        
        # Execute the agent
        python_cmd = get_python_command()
        
        if sys.platform.startswith('win'):
            # Windows: detached, no console — see views.py Starter/Ender
            # spawn for why CREATE_NO_WINDOW is mandatory here.
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=get_agent_env(),
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                    | subprocess.DETACHED_PROCESS
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            # Unix: start new session
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=get_agent_env(),
                start_new_session=True
            )
        
        # Write PID file for fast status checking
        _write_pid_file(agent_dir, process.pid)
        print(f"[RESTART] Started {pool_folder_name} with PID: {process.pid}")
        
        return HttpResponse(json.dumps({
            "success": True,
            "message": f"Restarted {pool_folder_name}",
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
            if folder_name == CHAT_RUNTIME_ROOT_NAME:
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
                    chat_runtime_root = os.path.join(pool_base_path, CHAT_RUNTIME_ROOT_NAME)
                    if pool_base_path in cmdline_str and chat_runtime_root not in cmdline_str:
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
def reanimate_agents_view(request):
    """
    Reanimate agents from stored process info (resume from pause).
    Same as restart_agents but passes AGENT_REANIMATED=1 env var so agents
    know to preserve logs and load reanimation state files.

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
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        agents_to_reanimate = data.get('agents', [])

        if not agents_to_reanimate:
            return HttpResponse(json.dumps({
                "success": True,
                "reanimated": [],
                "failed": [],
                "message": "No agents to reanimate"
            }), content_type='application/json')

        pool_base_path = get_pool_path(request)
        python_cmd = get_python_command()

        reanimated = []
        failed = []

        for agent in agents_to_reanimate:
            canvas_id = agent.get('canvas_id', '')
            folder_name = agent.get('folder_name', '')
            script_name = agent.get('script_name', '')

            if not folder_name or not script_name:
                failed.append(canvas_id)
                continue

            agent_dir = os.path.join(pool_base_path, folder_name)
            script_path = os.path.join(agent_dir, script_name)

            if not os.path.exists(script_path):
                print(f"[REANIMATE] Script not found: {script_path}")
                failed.append(canvas_id)
                continue

            try:
                cmd = python_cmd + [script_path]
                print(f"[REANIMATE] Starting: {' '.join(cmd)}")

                # Build env with AGENT_REANIMATED=1 so agent preserves logs & state
                agent_env = os.environ.copy()
                agent_env['AGENT_REANIMATED'] = '1'

                if sys.platform.startswith('win'):
                    CREATE_NO_WINDOW = 0x08000000
                    CREATE_NEW_PROCESS_GROUP = 0x00000200
                    DETACHED_PROCESS = 0x00000008
                    process = subprocess.Popen(
                        cmd,
                        cwd=agent_dir,
                        env=agent_env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        creationflags=CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS
                    )
                else:
                    process = subprocess.Popen(
                        cmd,
                        cwd=agent_dir,
                        env=agent_env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                        start_new_session=True
                    )

                _write_pid_file(agent_dir, process.pid)

                reanimated.append(canvas_id)
                print(f"[REANIMATE] Successfully reanimated: {canvas_id}")

            except Exception as start_err:
                print(f"[REANIMATE] Failed to reanimate {canvas_id}: {start_err}")
                failed.append(canvas_id)

        success = len(failed) == 0

        return HttpResponse(json.dumps({
            "success": success,
            "reanimated": reanimated,
            "failed": failed,
            "message": f"Reanimated {len(reanimated)} agent(s), {len(failed)} failed"
        }), content_type='application/json')

    except Exception as e:
        print(f"Error reanimating agents: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "reanimated": [],
            "failed": [],
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def save_paused_agents_view(request):
    """
    Save the list of running agents to paused_agents.reanim in the pool directory.
    Called when the Pause button is pressed.

    Expected POST body (JSON):
    {
        "agents": [
            {
                "canvas_id": "monitor-log-1",
                "folder_name": "monitor_log_1",
                "script_name": "monitor_log.py",
                "pid": 12345,
                "cmdline": "..."
            }
        ]
    }
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        agents = data.get('agents', [])
        pool_base_path = get_pool_path(request)

        if not os.path.exists(pool_base_path):
            os.makedirs(pool_base_path, exist_ok=True)

        reanim_path = os.path.join(pool_base_path, 'paused_agents.reanim')

        with open(reanim_path, 'w', encoding='utf-8') as f:
            yaml.dump({'paused_agents': agents}, f, default_flow_style=False)

        print(f"[PAUSE] Saved {len(agents)} agent(s) to {reanim_path}")

        return HttpResponse(json.dumps({
            "success": True,
            "saved_count": len(agents),
            "message": f"Saved {len(agents)} paused agent(s)"
        }), content_type='application/json')

    except Exception as e:
        print(f"Error saving paused agents: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "message": str(e)
        }), content_type='application/json', status=500)


def load_paused_agents_view(request):
    """
    Load the list of paused agents from paused_agents.reanim.
    Called when resuming from pause.
    """
    try:
        pool_base_path = get_pool_path(request)
        reanim_path = os.path.join(pool_base_path, 'paused_agents.reanim')

        if not os.path.exists(reanim_path):
            return HttpResponse(json.dumps({
                "success": True,
                "agents": [],
                "message": "No paused_agents.reanim file found"
            }), content_type='application/json')

        with open(reanim_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        agents = data.get('paused_agents', []) if data else []
        print(f"[RESUME] Loaded {len(agents)} paused agent(s) from {reanim_path}")

        return HttpResponse(json.dumps({
            "success": True,
            "agents": agents,
            "message": f"Loaded {len(agents)} paused agent(s)"
        }), content_type='application/json')

    except Exception as e:
        print(f"Error loading paused agents: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
            "agents": [],
            "message": str(e)
        }), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def delete_paused_agents_view(request):
    """
    Delete the paused_agents.reanim file after successful resume.
    """
    try:
        pool_base_path = get_pool_path(request)
        reanim_path = os.path.join(pool_base_path, 'paused_agents.reanim')

        if os.path.exists(reanim_path):
            os.remove(reanim_path)
            print(f"[RESUME] Deleted {reanim_path}")

        return HttpResponse(json.dumps({
            "success": True,
            "message": "paused_agents.reanim deleted"
        }), content_type='application/json')

    except Exception as e:
        print(f"Error deleting paused agents file: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({
            "success": False,
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
def update_teletlamatini_connection_view(request, agent_name):
    """
    Update a TeleTlamatini agent's config.yaml when connections are made/removed.
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
            return HttpResponse(json.dumps({'error': 'TeleTlamatini agent config not found'}), content_type='application/json', status=404)

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
        print(f"Error updating TeleTlamatini connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_whatstlamatini_connection_view(request, agent_name):
    """
    Update a WhatsTlamatini agent's config.yaml when connections are made/removed.
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
            return HttpResponse(json.dumps({'error': 'WhatsTlamatini agent config not found'}), content_type='application/json', status=404)

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
        print(f"Error updating WhatsTlamatini connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_acpxer_connection_view(request, agent_name):
    """
    Update an ACPXer agent's config.yaml when connections are made/removed.
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
            return HttpResponse(json.dumps({'error': 'ACPXer agent config not found'}), content_type='application/json', status=404)

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
        print(f"Error updating ACPXer connection: {e}")
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
def update_counter_connection_view(request, agent_name):
    """
    Update config.yaml for a Counter agent when a connection is made or removed.
    Supports add/remove of target_agents_l, target_agents_g, and source_agents.
    The 'connection_type' field determines which list to update:
      - 'target_l' -> target_agents_l
      - 'target_g' -> target_agents_g
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

        if not agent_name.lower().startswith('counter'):
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
        if connection_type == 'target_l':
            list_key = 'target_agents_l'
        elif connection_type == 'target_g':
            list_key = 'target_agents_g'
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
                print(f"[COUNTER] Added {connected_pool_name} to {agent_name} {list_key}")
        elif action == 'remove':
            if connected_pool_name in current_list:
                current_list.remove(connected_pool_name)
                changed = True
                print(f"[COUNTER] Removed {connected_pool_name} from {agent_name} {list_key}")

        config[list_key] = current_list
        msg = f'Updated {list_key}: {current_list}'

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({'success': True, 'message': msg, 'changed': changed}),
                          content_type='application/json')

    except Exception as e:
        print(f"Error updating counter connection: {e}")
        return HttpResponse(json.dumps({'error': str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def asker_choice_view(request, agent_name):
    """
    Receive the user's A/B choice from the frontend dialog and write it
    to choice.txt in the asker agent's directory so the running asker.py
    can read it.

    Two address modes are supported:
      1. Canvas id (e.g., 'asker-1') -> resolves to the ACP session pool
         directory at <pools>/<session>/asker_1/.
      2. Chat-runtime name (e.g., 'asker_001_a1b2c3d4') -> resolves to
         <pools>/_chat_runs_/asker_001_a1b2c3d4/. Used by Multi-Turn chat.
    """
    try:
        data = json.loads(request.body)
        choice = data.get('choice', '').upper()

        if choice not in ('A', 'B'):
            return HttpResponse(json.dumps({'status': 'error', 'message': 'Invalid choice, must be A or B'}),
                              content_type='application/json', status=400)

        if not agent_name.lower().startswith('asker'):
            return HttpResponse("Invalid agent type", status=400)

        # Mode 2: chat-runtime name (validated against traversal)
        chat_runtime_dir = _resolve_chat_runtime_dir(agent_name)
        if chat_runtime_dir is not None:
            choice_path = os.path.join(chat_runtime_dir, 'choice.txt')
            with open(choice_path, 'w', encoding='utf-8') as f:
                f.write(choice)
            print(f"[ASKER] User chose Path {choice} for chat runtime {agent_name}")
            return HttpResponse(json.dumps({'success': True, 'message': f'Choice {choice} written'}),
                              content_type='application/json')

        # Mode 1: canvas id (existing ACP behavior)
        # Reject anything that looks like an attempted chat-runtime name but
        # didn't match _is_valid_chat_runtime_name (e.g., traversal attempts).
        if '..' in agent_name or os.sep in agent_name or '/' in agent_name:
            return HttpResponse("Invalid agent name", status=400)

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

        # 6. Save Config — shared dump helper so the IMAP password
        # (declared as `password_paths=("imap.password",)` on the recmailer
        # contract) is force-double-quoted on every write — including this
        # connection-update path, not just FlowCreator's compile path.
        dump_agent_config_yaml(config, config_path, 'recmailer')

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
@require_POST
def update_pser_connection_view(request, agent_name):
    """
    Update a Pser agent's config.yaml when connections are made/removed.
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
            return HttpResponse(json.dumps({'error': f'Pser config not found: {config_path}'}), content_type='application/json', status=404)

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
        print(f"Error updating Pser connection: {e}")
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
            # Detached + no-window — prevents conhost.exe orphans (see
            # views.py Starter/Ender spawn for the contract).
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP
                    | subprocess.CREATE_NO_WINDOW
                    | subprocess.DETACHED_PROCESS
                ),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
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


@csrf_exempt
@require_POST
def update_kuberneter_connection_view(request, agent_name):
    """
    Update a Kuberneter agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'kuberneter-1' -> 'kuberneter_1'
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
                "message": f"Kuberneter config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name
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
        print(f"Error updating Kuberneter connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_apirer_connection_view(request, agent_name):
    """
    Update an Apirer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'apirer-1' -> 'apirer_1'
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
                "message": f"Apirer config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name
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
        print(f"Error updating Apirer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_unrealer_connection_view(request, agent_name):
    """
    Update an Unrealer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'unrealer-1' -> 'unrealer_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()

        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

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
                "message": f"Unrealer config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = connected_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        connected_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

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
        print(f"Error updating Unrealer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_reviewer_connection_view(request, agent_name):
    """
    Update a Reviewer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'reviewer-1' -> 'reviewer_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()

        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

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
                "message": f"Reviewer config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = connected_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        connected_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

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
        print(f"Error updating Reviewer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_analyzer_connection_view(request, agent_name):
    """
    Update an Analyzer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'analyzer-1' -> 'analyzer_1'
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()

        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

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
                "message": f"Analyzer config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = connected_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        connected_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

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
        print(f"Error updating Analyzer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_jenkinser_connection_view(request, agent_name):
    """
    Update a Jenkinser agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'jenkinser-1' -> 'jenkinser_1'
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
                "message": f"Jenkinser config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name
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
        print(f"Error updating Jenkinser connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_crawler_connection_view(request, agent_name):
    """
    Update a Crawler agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'crawler-1' -> 'crawler_1'
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
                "message": f"Crawler config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name
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
        print(f"Error updating Crawler connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_summarizer_connection_view(request, agent_name):
    """
    Update a Summarizer agent's config.yaml when connections are made/removed.
    Handles 'source' (input) and 'target' (output) connections.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'summarizer-1' -> 'summarizer_1'
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
                "message": f"Summarizer config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name
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
        print(f"Error updating Summarizer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_flowhypervisor_connection_view(request, agent_name):
    """
    Update a FlowHypervisor agent's config.yaml when connections are made/removed.
    Note: FlowHypervisor has no inputs/outputs, but this view exists for framework consistency.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        connected_agent = data.get('connected_agent') or data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target') if 'type' in data else data.get('connection_type', 'target')

        if not connected_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "Missing connected_agent"
            }), content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'flowhypervisor-1' -> 'flowhypervisor_1'
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
                "message": f"FlowHypervisor config not found: {config_path}"
            }), content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse connected_agent to pool folder name
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
        print(f"Error updating FlowHypervisor connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
def execute_flowhypervisor_view(request, agent_name):
    """
    Execute a FlowHypervisor agent by running its Python script.
    Called by the frontend when the flow starts.
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

        # Guard: prevent concurrent instances — only one FlowHypervisor at a time
        pid_file = os.path.join(agent_dir, "agent.pid")
        if os.path.exists(pid_file):
            try:
                with open(pid_file, "r") as pf:
                    existing_pid = int(pf.read().strip())
                if psutil.pid_exists(existing_pid):
                    print(f"[FLOWHYPERVISOR] Already running with PID {existing_pid}, skipping launch")
                    return HttpResponse(json.dumps({
                        "success": True,
                        "message": f"Already running as PID {existing_pid}",
                        "pid": existing_pid
                    }), content_type='application/json')
            except (ValueError, OSError):
                pass  # stale PID file, proceed to launch

        python_cmd = get_python_command()
        agent_env = get_agent_env()

        if sys.platform.startswith('win'):
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        else:
            process = subprocess.Popen(
                python_cmd + [script_path],
                cwd=agent_dir,
                env=agent_env,
                start_new_session=True
            )

        _write_pid_file(agent_dir, process.pid)
        print(f"[FLOWHYPERVISOR] Started {pool_folder_name} with PID: {process.pid}")

        return HttpResponse(json.dumps({"success": True, "message": f"Started {pool_folder_name}", "pid": process.pid}),
                            content_type='application/json')
    except Exception as e:
        print(f"Error executing flowhypervisor agent: {e}")
        traceback.print_exc()
        return HttpResponse(json.dumps({"success": False, "message": str(e)}),
                            content_type='application/json', status=500)


def check_flowhypervisor_alert_view(request, agent_name):
    """
    Check if the FlowHypervisor has written an alert file.
    Returns the alert data if found, or empty response if no alert.
    Also returns `flow_alive` indicating whether any non-system agents
    are still running in the pool — the frontend uses this to stop the
    FlowHypervisor immediately when the flow is complete.
    The frontend polls this endpoint to detect ATTENTION NEEDED alerts.
    """
    try:
        parts = agent_name.split('-')
        cardinal = None
        if parts[-1].isdigit():
            cardinal = parts.pop()
        base_folder_name = "_".join(parts)
        pool_folder_name = f"{base_folder_name}_{cardinal}" if cardinal else base_folder_name

        pool_base_path = get_pool_path(request)
        alert_path = os.path.join(pool_base_path, pool_folder_name, "hypervisor_alert.json")

        # Check if any non-system agents are still running in the pool
        excluded_types = {'flowcreator', 'flowhypervisor'}
        flow_alive = False
        if os.path.isdir(pool_base_path):
            for folder in os.listdir(pool_base_path):
                folder_path = os.path.join(pool_base_path, folder)
                if not os.path.isdir(folder_path):
                    continue
                # Extract base agent type (e.g. 'starter_1' -> 'starter')
                folder_parts = folder.rsplit('_', 1)
                agent_type = folder_parts[0] if len(folder_parts) == 2 and folder_parts[1].isdigit() else folder
                if agent_type.lower() in excluded_types:
                    continue
                pid_path = os.path.join(folder_path, "agent.pid")
                if os.path.exists(pid_path):
                    try:
                        with open(pid_path, "r") as pf:
                            pid = int(pf.read().strip())
                        if psutil.pid_exists(pid):
                            flow_alive = True
                            break
                    except (ValueError, OSError):
                        pass

        if not os.path.exists(alert_path):
            return HttpResponse(json.dumps({"has_alert": False, "flow_alive": flow_alive}),
                                content_type='application/json')

        with open(alert_path, 'r', encoding='utf-8') as f:
            alert_data = json.load(f)

        # Remove the alert file after reading (consumed)
        try:
            os.remove(alert_path)
        except Exception:
            pass

        alert_data["has_alert"] = True
        alert_data["flow_alive"] = flow_alive
        return HttpResponse(json.dumps(alert_data), content_type='application/json')

    except Exception as e:
        print(f"Error checking flowhypervisor alert: {e}")
        return HttpResponse(json.dumps({"has_alert": False, "flow_alive": True, "error": str(e)}),
                            content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_mouser_connection_view(request, agent_name):
    """
    Update a Mouser agent's config.yaml when connections are made/removed.

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

        # Parse agent_name to pool folder name: 'mouser-1' -> 'mouser_1'
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
                "message": f"Mouser config not found: {config_path}"
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
        print(f"Error updating Mouser connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


# ============================================================================
# Config dialog endpoints (Config -> Models / URLs in the navbar)
# ----------------------------------------------------------------------------
# Both dialogs share the same load endpoint, which returns the exact subset of
# config.json the dialog needs. The save endpoints validate types server-side
# (defense in depth — the browser already validated, but never trust the wire)
# before merging into config.json through ``save_config_updates``.
# ============================================================================

CONFIG_MODEL_KEYS: tuple[str, ...] = (
    "embeding-model",
    "chained-model",
    "access_aimed_prompt_model",
    "unified_agent_model",
    "image_interpreter_model",
    "mcp_files_search_model",
    "internet_classifier_model",
    "web_summarizer_model",
)

CONFIG_URL_KEYS: tuple[str, ...] = (
    "ollama_base_url",
    "unified_agent_base_url",
    "image_interpreter_base_url",
    "mcp_system_server_host",
    "mcp_system_server_port",
    "mcp_system_client_uri",
    "mcp_files_search_server_host",
    "mcp_files_search_server_port",
    "mcp_files_search_client_uri",
)

CONFIG_URL_URL_FIELDS: frozenset[str] = frozenset({
    "ollama_base_url",
    "unified_agent_base_url",
    "image_interpreter_base_url",
    "mcp_system_client_uri",
    "mcp_files_search_client_uri",
})
CONFIG_URL_HOST_FIELDS: frozenset[str] = frozenset({
    "mcp_system_server_host",
    "mcp_files_search_server_host",
})
CONFIG_URL_PORT_FIELDS: frozenset[str] = frozenset({
    "mcp_system_server_port",
    "mcp_files_search_server_port",
})

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)"
    r"(?!-)[A-Za-z0-9-]{1,63}(?<!-)"
    r"(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}"
    r"(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
)


def _validate_url_value(value) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    candidate = value.strip()
    if not candidate:
        return "must not be empty"
    try:
        from urllib.parse import urlparse
        parsed = urlparse(candidate)
    except Exception:
        return "is not a valid URL"
    if parsed.scheme not in {"http", "https", "ws", "wss"}:
        return "must use http(s):// or ws(s):// scheme"
    if not parsed.netloc:
        return "must include a host"
    return None


def _validate_host_value(value) -> str | None:
    if not isinstance(value, str):
        return "must be a string"
    candidate = value.strip()
    if not candidate:
        return "must not be empty"
    if _IPV4_RE.match(candidate):
        return None
    if _HOSTNAME_RE.match(candidate):
        return None
    return "must be a hostname (e.g. localhost) or IPv4 address"


def _validate_port_value(value) -> tuple[str | None, int | None]:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return ("must be an integer between 1 and 65535", None)
    if port < 1 or port > 65535:
        return ("must be between 1 and 65535", None)
    return (None, port)


@login_required
def load_config_section_view(request, section: str):
    """
    Return the current values for the ``models`` or ``urls`` config dialog.
    Always returns strings (or stringified ints) so the frontend can drop them
    straight into ``<input>`` values.
    """
    section = (section or "").strip().lower()
    if section not in {"models", "urls"}:
        return JsonResponse({"success": False, "error": f"unknown config section: {section}"}, status=400)

    config = load_config(force_reload=True)
    keys = CONFIG_MODEL_KEYS if section == "models" else CONFIG_URL_KEYS
    values: dict[str, str] = {}
    for key in keys:
        raw = config.get(key, "")
        if raw is None:
            values[key] = ""
        else:
            values[key] = str(raw)
    return JsonResponse({"success": True, "section": section, "values": values})


@csrf_exempt
@require_POST
@login_required
def save_config_models_view(request):
    """
    Persist the 8 model fields from the Config -> Models dialog. Each value
    must be a non-empty string. The browser already validates against the
    Ollama catalog; this endpoint only enforces type/shape so a malformed
    request never lands in config.json.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        return JsonResponse({"success": False, "error": f"invalid JSON: {exc}"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"success": False, "error": "payload must be a JSON object"}, status=400)

    errors: dict[str, str] = {}
    updates: dict[str, str] = {}
    for key in CONFIG_MODEL_KEYS:
        if key not in payload:
            errors[key] = "missing"
            continue
        value = payload[key]
        if not isinstance(value, str):
            errors[key] = "must be a string"
            continue
        trimmed = value.strip()
        if not trimmed:
            errors[key] = "must not be empty"
            continue
        updates[key] = trimmed

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    try:
        path_written = save_config_updates(updates)
    except Exception as exc:
        print(f"[CONFIG] Error saving models config: {exc}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

    return JsonResponse({"success": True, "path": path_written, "updated_keys": list(updates.keys())})


@csrf_exempt
@require_POST
@login_required
def save_config_urls_view(request):
    """
    Persist the 9 URL/host/port fields from the Config -> URLs dialog.
    URLs must parse with an http(s)://ws(s):// scheme and a host. Hostnames
    must match an IPv4 or RFC-1123 hostname pattern. Ports must be 1..65535.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        return JsonResponse({"success": False, "error": f"invalid JSON: {exc}"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"success": False, "error": "payload must be a JSON object"}, status=400)

    errors: dict[str, str] = {}
    updates: dict[str, object] = {}
    for key in CONFIG_URL_KEYS:
        if key not in payload:
            errors[key] = "missing"
            continue
        value = payload[key]
        if key in CONFIG_URL_URL_FIELDS:
            err = _validate_url_value(value)
            if err:
                errors[key] = err
            else:
                updates[key] = value.strip()
        elif key in CONFIG_URL_HOST_FIELDS:
            err = _validate_host_value(value)
            if err:
                errors[key] = err
            else:
                updates[key] = value.strip()
        elif key in CONFIG_URL_PORT_FIELDS:
            err, port = _validate_port_value(value)
            if err:
                errors[key] = err
            else:
                updates[key] = port

    if errors:
        return JsonResponse({"success": False, "errors": errors}, status=400)

    try:
        path_written = save_config_updates(updates)
    except Exception as exc:
        print(f"[CONFIG] Error saving urls config: {exc}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

    return JsonResponse({"success": True, "path": path_written, "updated_keys": list(updates.keys())})


def _resolve_db_sqlite_path() -> str:
    """
    Return the absolute path of the live SQLite database, valid in both
    source mode (next to ``manage.py``) and frozen mode (next to the
    executable). Django's ``settings.DATABASES['default']['NAME']`` already
    points to the right file because ``BASE_DIR`` is recomputed from
    ``settings.py``'s location at startup.
    """
    db_name = settings.DATABASES.get('default', {}).get('NAME')
    if not db_name:
        raise RuntimeError("Default database NAME is not configured")
    return os.path.abspath(str(db_name))


@login_required
def check_backup_directory_view(request):
    """
    Live-validate the target directory typed by the user in the
    DB -> Backup database dialog. Returns one of:

        {"kind": "directory", "path": <abs>}   - exists and is a directory
        {"kind": "file",      "path": <abs>}   - exists but is a regular file
        {"kind": "missing",   "path": <abs>}   - does not exist on disk

    Plus ``{"kind": "empty"}`` when the caller did not provide a path at all.
    The endpoint never raises to the browser; any unexpected failure is
    reported as ``{"kind": "error", "error": <msg>}`` with HTTP 200 so the
    frontend can render a friendly message instead of a stack trace.
    """
    raw = (request.GET.get('path') or '').strip()
    if not raw:
        return JsonResponse({"kind": "empty"})

    try:
        absolute = os.path.abspath(raw)
        if os.path.isdir(absolute):
            return JsonResponse({"kind": "directory", "path": absolute})
        if os.path.isfile(absolute):
            return JsonResponse({"kind": "file", "path": absolute})
        return JsonResponse({"kind": "missing", "path": absolute})
    except Exception as exc:
        print(f"[BACKUP DB] check_backup_directory failed: {exc}")
        return JsonResponse({"kind": "error", "error": str(exc)})


@csrf_exempt
@require_POST
@login_required
def backup_db_view(request):
    """
    Copy the live ``db.sqlite3`` file into the target directory specified
    by the user. The target MUST be an existing directory; a path that
    points at a file is rejected with ``{"success": False, "kind": "file"}``
    so the frontend can show the "do not rename the file" guidance.

    The destination filename is always ``db.sqlite3`` (the same basename
    Django expects) so the resulting backup is drop-in compatible with a
    future restore.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        return JsonResponse({"success": False, "error": f"invalid JSON: {exc}"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"success": False, "error": "payload must be a JSON object"}, status=400)

    raw = payload.get("target_dir")
    if not isinstance(raw, str) or not raw.strip():
        return JsonResponse({"success": False, "kind": "missing", "error": "target_dir must be a non-empty string"}, status=400)

    target_dir = os.path.abspath(raw.strip())

    if os.path.isfile(target_dir):
        return JsonResponse({
            "success": False,
            "kind": "file",
            "error": "The path points to a file. Please specify only the directory; the backup is always saved as db.sqlite3.",
        }, status=400)

    if not os.path.isdir(target_dir):
        return JsonResponse({
            "success": False,
            "kind": "missing",
            "error": f"Target directory does not exist: {target_dir}",
        }, status=400)

    try:
        source_path = _resolve_db_sqlite_path()
    except Exception as exc:
        print(f"[BACKUP DB] Could not resolve source db path: {exc}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

    if not os.path.isfile(source_path):
        return JsonResponse({
            "success": False,
            "error": f"Live database file not found at: {source_path}",
        }, status=500)

    destination_path = os.path.join(target_dir, "db.sqlite3")

    try:
        if os.path.normcase(os.path.abspath(source_path)) == os.path.normcase(os.path.abspath(destination_path)):
            return JsonResponse({
                "success": False,
                "error": "Source and destination resolve to the same file — choose a different target directory.",
            }, status=400)
        shutil.copy2(source_path, destination_path)
    except Exception as exc:
        print(f"[BACKUP DB] Copy failed: {exc}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

    print(f"[BACKUP DB] Copied {source_path} -> {destination_path}")
    return JsonResponse({"success": True, "path": destination_path, "source": source_path})


def _resolve_db_to_load_directory() -> str:
    """Return the absolute path of ``<base>/DB/ToLoad/`` for the running
    deployment.  Mirrors ``manage.py::_resolve_db_folder_root`` so the
    upload target the Django view writes to is the same directory the
    early-startup swap-in reads from.
    """
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        # ``settings.BASE_DIR`` is the directory that holds ``manage.py``
        # in source mode (it is ``Path(settings.py).resolve().parent.parent``).
        base = str(settings.BASE_DIR)
    return os.path.join(base, 'DB', 'ToLoad')


def _file_looks_like_sqlite(path: str) -> bool:
    """Best-effort SQLite-header check.  Returns ``True`` for files whose
    first 16 bytes match the documented magic string ``SQLite format 3\\x00``.
    Used as a sanity guard, not a strong validation (a corrupt SQLite file
    still starts with the magic).
    """
    try:
        with open(path, 'rb') as fh:
            header = fh.read(16)
    except OSError:
        return False
    return header.startswith(b'SQLite format 3\x00')


@login_required
def check_set_db_file_view(request):
    """
    Live-validate the database file path the user types in the
    DB -> Set DB dialog.  Returns one of:

        {"kind": "file",      "path": <abs>, "sqlite": True/False, "basename_ok": True/False}
        {"kind": "directory", "path": <abs>}
        {"kind": "missing",   "path": <abs>}
        {"kind": "empty"}                            - no path supplied

    Never raises to the browser; any unexpected failure is reported as
    ``{"kind": "error", "error": <msg>}`` with HTTP 200.
    """
    raw = (request.GET.get('path') or '').strip()
    if not raw:
        return JsonResponse({"kind": "empty"})

    try:
        absolute = os.path.abspath(raw)
        if os.path.isdir(absolute):
            return JsonResponse({"kind": "directory", "path": absolute})
        if os.path.isfile(absolute):
            basename_ok = os.path.basename(absolute).lower() == 'db.sqlite3'
            return JsonResponse({
                "kind": "file",
                "path": absolute,
                "sqlite": _file_looks_like_sqlite(absolute),
                "basename_ok": basename_ok,
            })
        return JsonResponse({"kind": "missing", "path": absolute})
    except Exception as exc:
        print(f"[SET DB] check_set_db_file failed: {exc}")
        return JsonResponse({"kind": "error", "error": str(exc)})


@csrf_exempt
@require_POST
@login_required
def set_db_view(request):
    """
    Stage a user-provided ``db.sqlite3`` file into ``<base>/DB/ToLoad/``
    so the next start-up's swap-in promotes it to the live database.

    Why this view *only stages* (and does not hot-swap): SQLite is open
    while Django runs, so replacing it mid-process would corrupt the live
    connection pool.  The swap-in is performed at start-up by
    ``manage.py::_apply_pending_db_swap`` BEFORE Django is imported, which
    is the only safe window to move the file.
    """
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        return JsonResponse({"success": False, "error": f"invalid JSON: {exc}"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"success": False, "error": "payload must be a JSON object"}, status=400)

    raw = payload.get("source_path")
    if not isinstance(raw, str) or not raw.strip():
        return JsonResponse({"success": False, "kind": "missing", "error": "source_path must be a non-empty string"}, status=400)

    source_path = os.path.abspath(raw.strip())

    if os.path.isdir(source_path):
        return JsonResponse({
            "success": False,
            "kind": "directory",
            "error": "The path points to a directory. Please specify the full path to a db.sqlite3 file.",
        }, status=400)

    if not os.path.isfile(source_path):
        return JsonResponse({
            "success": False,
            "kind": "missing",
            "error": f"Source file does not exist: {source_path}",
        }, status=400)

    if not _file_looks_like_sqlite(source_path):
        return JsonResponse({
            "success": False,
            "kind": "not_sqlite",
            "error": "The selected file does not look like a SQLite database (missing magic header).",
        }, status=400)

    try:
        to_load_dir = _resolve_db_to_load_directory()
        os.makedirs(to_load_dir, exist_ok=True)
        destination_path = os.path.join(to_load_dir, "db.sqlite3")

        if os.path.normcase(source_path) == os.path.normcase(destination_path):
            return JsonResponse({
                "success": False,
                "error": "Source already is the staged file — choose a different db.sqlite3 file.",
            }, status=400)

        # The swap-in expects ``DB/ToLoad/db.sqlite3``; overwrite any
        # previously-staged file so the latest user pick wins.
        shutil.copy2(source_path, destination_path)
    except Exception as exc:
        print(f"[SET DB] Could not stage db.sqlite3: {exc}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(exc)}, status=500)

    print(f"[SET DB] Staged {source_path} -> {destination_path}")
    return JsonResponse({"success": True, "path": destination_path, "source": source_path})


def _run_native_picker(kind: str, title: str) -> str:
    """
    Open a native modal picker dialog (Tkinter) on the host running the
    Tlamatini server and return the absolute path the user chose, or the
    empty string if the dialog was canceled.

    Tlamatini is a locally-deployed Django server, so the user driving the
    browser is the same user sitting at the keyboard — opening a native
    picker on the server is a legitimate way to give the Browse buttons a
    real filesystem path (something the browser sandbox cannot provide on
    its own). The dialog runs in a dedicated daemon thread with its own
    ``Tk`` root because Tkinter does not tolerate being driven from the
    Daphne worker thread that handles the HTTP request on Windows.

    ``kind`` is either ``"directory"`` (Backup database dialog) or
    ``"db_sqlite_file"`` (Set DB dialog — restricts the file filter to
    files named ``db.sqlite3``).
    """
    result_q: _queue.Queue = _queue.Queue()

    def _runner() -> None:
        try:
            import tkinter as _tk
            from tkinter import filedialog as _filedialog
            root = _tk.Tk()
            root.withdraw()
            try:
                root.attributes('-topmost', True)
            except Exception:
                pass
            try:
                if kind == 'directory':
                    chosen = _filedialog.askdirectory(
                        title=title,
                        mustexist=True,
                        parent=root,
                    )
                elif kind == 'db_sqlite_file':
                    chosen = _filedialog.askopenfilename(
                        title=title,
                        filetypes=[('SQLite database (db.sqlite3)', 'db.sqlite3')],
                        parent=root,
                    )
                else:
                    raise ValueError(f"Unknown picker kind: {kind!r}")
            finally:
                try:
                    root.destroy()
                except Exception:
                    pass
            result_q.put(('ok', chosen or ''))
        except Exception as exc:
            result_q.put(('err', str(exc)))

    picker_thread = threading.Thread(target=_runner, name='tlamatini-native-picker', daemon=True)
    picker_thread.start()
    picker_thread.join()
    status, value = result_q.get_nowait()
    if status == 'err':
        raise RuntimeError(value)
    return value or ''


@login_required
def pick_backup_directory_view(request):
    """
    Open a native folder-picker on the server host for the Backup
    database dialog's Browse button. Returns ``{"path": "<abs>"}`` or
    ``{"path": "", "canceled": true}`` when the user closed the dialog.
    Any backend failure is reported as ``{"path": "", "error": "..."}``
    so the frontend can render a friendly message.
    """
    try:
        chosen = _run_native_picker('directory', 'Select backup target directory')
    except Exception as exc:
        print(f"[BACKUP DB] folder picker failed: {exc}")
        traceback.print_exc()
        return JsonResponse({"path": "", "error": str(exc)})
    if not chosen:
        return JsonResponse({"path": "", "canceled": True})
    return JsonResponse({"path": os.path.abspath(chosen)})


@login_required
def pick_db_sqlite_file_view(request):
    """
    Open a native file-picker on the server host for the Set DB dialog's
    Browse button. The dialog's file filter restricts visible files to
    those literally named ``db.sqlite3`` (matching the basename the
    next-start-up swap-in expects).
    """
    try:
        chosen = _run_native_picker('db_sqlite_file', 'Select db.sqlite3 file to load on next start-up')
    except Exception as exc:
        print(f"[SET DB] file picker failed: {exc}")
        traceback.print_exc()
        return JsonResponse({"path": "", "error": str(exc)})
    if not chosen:
        return JsonResponse({"path": "", "canceled": True})
    return JsonResponse({"path": os.path.abspath(chosen)})


@csrf_exempt
@require_POST
def compile_flow_view(request):
    """
    Compile a client-side flow snapshot against the backend agent contracts.

    mode='dry_run' returns the same agent/config shape used by Validate
    without writing to disk. mode='write' updates the current session pool.
    """
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
        flow_data = data.get('flow') if isinstance(data.get('flow'), dict) else data
        mode = str(data.get('mode') or '').lower()
        write = bool(data.get('write')) or mode in {'write', 'sync', 'start'}
        result = compile_flow_payload(flow_data, request=request, write=write)
        return JsonResponse(result)
    except Exception as e:
        print(f"[FLOW COMPILE] Error compiling flow: {e}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@csrf_exempt
@require_POST
def flow_from_tool_calls_view(request):
    """
    Normalize a Chat-created flow before download.

    The browser still provides a legacy .flw-shaped draft during the staged
    rollout. The backend normalizes it through FlowSpec and redacts known
    secret fields, so the saved artifact is portable in source and frozen
    modes.
    """
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
        flow_data = data.get('flow_data') or data.get('flow')
        if not isinstance(flow_data, dict):
            return JsonResponse({"success": False, "message": "Missing flow_data"}, status=400)
        spec = normalize_flow_payload(flow_data)
        return JsonResponse({
            "success": True,
            "flow": flow_spec_to_legacy_json(spec, redact=True),
        })
    except Exception as e:
        print(f"[CHAT FLOW] Error normalizing flow: {e}")
        traceback.print_exc()
        return JsonResponse({"success": False, "error": str(e)}, status=500)


def agent_contracts_view(request):
    """Return the backend agent-contract registry for diagnostics/UI use."""
    return JsonResponse({"success": True, "contracts": list_contract_summaries()})


def version_view(request):
    """Return the running Tlamatini version (SemVer 2.0.0) as JSON.

    Open endpoint (no login required) so health-check / monitoring tooling
    can hit it without credentials.  See VERSIONING.md for resolution
    semantics.

    Response shape::

        {
          "version": "1.1.1",                       # public SemVer (clean, no suffix)
          "build":   "1.1.1",                       # build descriptor (same as version)
          "commit":  "abc1234",
          "date":    "2026-05-15T18:42:11Z",
          "source":  "generated" | "git" | "unknown"
        }
    """
    try:
        from .version import get_version_info
        return JsonResponse(get_version_info())
    except Exception as exc:
        return JsonResponse(
            {
                "version": "0.0.0+unknown",
                "build":   "0.0.0+unknown",
                "commit":  "unknown",
                "date":    "",
                "source":  "unknown",
                "error":   str(exc),
            },
            status=500,
        )


def validate_flow_view(request):
    """
    List all agents in the session pool and return their config.yaml data.
    Excludes non-runtime validation agents. Used by the Validate button to build
    the NxN adjacency matrix on the frontend.

    Returns JSON: { agents: [ { folder_name, agent_type, config }, ... ] }
    """
    pool_path = get_pool_path(request)
    if not pool_path or not os.path.exists(pool_path):
        return HttpResponse(json.dumps({
            'agents': [],
            'message': 'Pool directory not found or empty'
        }), content_type='application/json')

    try:
        agents = list_pool_agents_for_validation(request)
    except Exception as e:
        print(f"[VALIDATE] Error listing pool agents: {e}")
        return HttpResponse(json.dumps({
            'agents': [],
            'error': str(e)
        }), content_type='application/json', status=500)

    return HttpResponse(json.dumps({'agents': agents}), content_type='application/json')


@csrf_exempt
@require_POST
def update_file_interpreter_connection_view(request, agent_name):
    """Update a File-Interpreter agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating File-Interpreter connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_image_interpreter_connection_view(request, agent_name):
    """Update an Image-Interpreter agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Image-Interpreter connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_gatewayer_connection_view(request, agent_name):
    """Update a Gatewayer agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Gatewayer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_gateway_relayer_connection_view(request, agent_name):
    """Update a GatewayRelayer agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating GatewayRelayer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


def update_node_manager_connection_view(request, agent_name):
    """Update a NodeManager agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating NodeManager connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


def update_file_creator_connection_view(request, agent_name):
    """Update a File-Creator agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating File-Creator connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


def update_file_extractor_connection_view(request, agent_name):
    """Update a File-Extractor agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating File-Extractor connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_kyber_keygen_connection_view(request, agent_name):
    """Update a Kyber-KeyGen agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Kyber-KeyGen connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_kyber_cipher_connection_view(request, agent_name):
    """Update a Kyber-Cipher agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Kyber-Cipher connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_kyber_decipher_connection_view(request, agent_name):
    """Update a Kyber-DeCipher agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Kyber-DeCipher connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_parametrizer_connection_view(request, agent_name):
    """Update a Parametrizer agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        # For Parametrizer, also update singular source_agent / target_agent fields
        if connection_type == 'source':
            list_name = 'source_agents'
            singular_field = 'source_agent'
        else:
            list_name = 'target_agents'
            singular_field = 'target_agent'

        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            config[singular_field] = target_pool_name
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            if config.get(singular_field) == target_pool_name:
                config[singular_field] = config[list_name][0] if config[list_name] else ""
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Parametrizer connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


# Structured output field definitions for each source agent type.
# Every section-generating agent uses the unified INI_SECTION / END_SECTION
# format.  KV header fields appear before the first blank line; content
# after the blank line is stored as 'response_body'.
PARAMETRIZER_SOURCE_OUTPUT_FIELDS = get_parametrizer_source_fields()

# Allowed source agent base names
PARAMETRIZER_ALLOWED_SOURCES = set(PARAMETRIZER_SOURCE_OUTPUT_FIELDS.keys())
PARAMETRIZER_MARKER_PATTERN = re.compile(r'\{([^{}\r\n]+)\}')


def _normalize_parametrizer_marker_name(marker):
    """Normalize a configured placeholder name to its bare marker form."""
    marker_name = str(marker or '').strip()
    if marker_name.startswith('{') and marker_name.endswith('}'):
        marker_name = marker_name[1:-1].strip()
    return marker_name


def _extract_parametrizer_markers(value):
    """Return placeholder names found in a scalar config value."""
    if not isinstance(value, str):
        return []

    markers = []
    seen = set()
    for match in PARAMETRIZER_MARKER_PATTERN.finditer(value):
        marker_name = _normalize_parametrizer_marker_name(match.group(1))
        if marker_name and marker_name not in seen:
            seen.add(marker_name)
            markers.append(marker_name)
    return markers


def _flatten_parametrizer_target_config(config, excluded_keys, parent_key=''):
    """Flatten target config keys and collect configured placeholders for each key."""
    target_params = []
    target_markers = {}

    if not isinstance(config, dict):
        return target_params, target_markers

    for key, value in config.items():
        new_key = f"{parent_key}.{key}" if parent_key else key
        if not parent_key and new_key in excluded_keys:
            continue

        target_params.append(new_key)

        markers = _extract_parametrizer_markers(value)
        if markers:
            target_markers[new_key] = markers

        if isinstance(value, dict):
            nested_params, nested_markers = _flatten_parametrizer_target_config(
                value,
                excluded_keys,
                new_key,
            )
            target_params.extend(nested_params)
            target_markers.update(nested_markers)

    return target_params, target_markers


def _get_source_base_name(agent_pool_name):
    """Extract base agent name from pool name for Parametrizer validation."""
    source_base = pool_name_to_agent_type(agent_pool_name)
    if source_base in PARAMETRIZER_ALLOWED_SOURCES:
        return source_base
    return None


def get_parametrizer_dialog_data_view(request, agent_name):
    """
    Return the dynamic config dialog data for a Parametrizer agent.
    Validates connections and returns source output fields + target config params.
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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": "Config not found"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        source_agent = config.get('source_agent', '')
        target_agent = config.get('target_agent', '')

        # Also check source_agents/target_agents lists
        source_agents_list = config.get('source_agents', [])
        target_agents_list = config.get('target_agents', [])

        if not source_agent and len(source_agents_list) == 1:
            source_agent = source_agents_list[0]
        if not target_agent and len(target_agents_list) == 1:
            target_agent = target_agents_list[0]

        # Validate: exactly one source and one target
        if not source_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "No source agent connected to Parametrizer's input. "
                           "Connect exactly one source agent before opening the configuration dialog."
            }), content_type='application/json', status=400)

        if not target_agent:
            return HttpResponse(json.dumps({
                "success": False,
                "message": "No target agent connected to Parametrizer's output. "
                           "Connect exactly one target agent before opening the configuration dialog."
            }), content_type='application/json', status=400)

        if len(source_agents_list) > 1:
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Only one source agent allowed but {len(source_agents_list)} are connected."
            }), content_type='application/json', status=400)

        if len(target_agents_list) > 1:
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Only one target agent allowed but {len(target_agents_list)} are connected."
            }), content_type='application/json', status=400)

        # Validate source agent type
        source_base = _get_source_base_name(source_agent)
        if source_base is None:
            return HttpResponse(json.dumps({
                "success": False,
                "message": f"Source agent '{source_agent}' does not produce structured output. "
                           "Only Apirer, Gitter, Kuberneter, Crawler, Summarizer, File-Interpreter, "
                           "Image-Interpreter, File-Extractor, Prompter, FlowCreator, "
                           "Kyber-KeyGen, Kyber-Cipher, Kyber-DeCipher, Gatewayer, "
                           "and Gateway-Relayer are allowed."
            }), content_type='application/json', status=400)

        # Get source output field names
        source_fields = PARAMETRIZER_SOURCE_OUTPUT_FIELDS.get(source_base, [])

        # Get target agent config params
        target_config_path = os.path.join(pool_base_path, target_agent, 'config.yaml')
        target_params = []
        if os.path.exists(target_config_path):
            with open(target_config_path, 'r', encoding='utf-8') as f:
                target_config = yaml.safe_load(f) or {}
            # Return all params except internal connection fields
            excluded_keys = {'source_agents', 'target_agents', 'output_agents',
                             'source_agent_1', 'source_agent_2',
                             'target_agents_a', 'target_agents_b'}

            target_params, target_markers = _flatten_parametrizer_target_config(
                target_config,
                excluded_keys,
            )
        else:
            target_markers = {}

        # Load existing interconnection scheme if present
        scheme_path = os.path.join(pool_base_path, pool_folder_name, 'interconnection-scheme.csv')
        existing_mappings = []
        if os.path.exists(scheme_path):
            import csv
            with open(scheme_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sf = row.get('source_field', '').strip()
                    tp = row.get('target_param', '').strip()
                    tm = _normalize_parametrizer_marker_name(row.get('target_marker', ''))
                    if sf and tp:
                        existing_mappings.append({
                            'source_field': sf,
                            'target_param': tp,
                            'target_marker': tm,
                        })

        return HttpResponse(json.dumps({
            "success": True,
            "source_agent": source_agent,
            "target_agent": target_agent,
            "source_fields": source_fields,
            "target_params": target_params,
            "target_markers": target_markers,
            "existing_mappings": existing_mappings
        }), content_type='application/json')

    except Exception as e:
        print(f"Error getting Parametrizer dialog data: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def save_parametrizer_scheme_view(request, agent_name):
    """Save the interconnection-scheme.csv for a Parametrizer agent."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        mappings = data.get('mappings', [])

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
        scheme_path = os.path.join(pool_base_path, pool_folder_name, 'interconnection-scheme.csv')

        import csv
        with open(scheme_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['source_field', 'target_param', 'target_marker'])
            writer.writeheader()
            saved_count = 0
            for m in mappings:
                sf = m.get('source_field', '').strip()
                tp = m.get('target_param', '').strip()
                tm = _normalize_parametrizer_marker_name(m.get('target_marker', ''))
                if sf and tp:
                    writer.writerow({
                        'source_field': sf,
                        'target_param': tp,
                        'target_marker': tm,
                    })
                    saved_count += 1

        return HttpResponse(json.dumps({
            "success": True,
            "message": f"Saved {saved_count} mapping(s) to interconnection-scheme.csv"
        }), content_type='application/json')

    except Exception as e:
        print(f"Error saving Parametrizer scheme: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


def detect_installed_apps_view(request):
    """
    Detect which IDEs/editors are installed on the system.
    Checks for Visual Studio Code and Antigravity IDE.
    File Explorer is always available on Windows.
    """
    apps = []

    # Always include File Explorer (Windows)
    apps.append({"id": "explorer", "name": "File Explorer", "available": True})

    # Detect Visual Studio Code
    vscode_available = shutil.which("code") is not None
    if not vscode_available:
        # Check common install paths on Windows
        vscode_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
        ]
        for p in vscode_paths:
            if os.path.isfile(p):
                vscode_available = True
                break
    apps.append({"id": "vscode", "name": "VS Code", "available": vscode_available})

    # Detect Antigravity IDE
    antigravity_available = shutil.which("antigravity") is not None
    if not antigravity_available:
        antigravity_paths = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%ProgramFiles%\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Antigravity\Antigravity.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\antigravity\Antigravity.exe"),
        ]
        for p in antigravity_paths:
            if os.path.isfile(p):
                antigravity_available = True
                break
    apps.append({"id": "antigravity", "name": "Antigravity", "available": antigravity_available})

    return HttpResponse(json.dumps({"success": True, "apps": apps}), content_type='application/json')


def open_in_app_view(request):
    """
    Open a directory in the specified application.
    Expects POST with 'app_id' plus either:
    - 'directory' for an explicit path, or
    - 'agent_name' to resolve a deployed canvas-agent instance directory.
    """
    try:
        app_id = request.POST.get('app_id', '').strip()
        directory = request.POST.get('directory', '').strip()
        agent_name = request.POST.get('agent_name', '').strip()

        if not app_id or (not directory and not agent_name):
            return HttpResponse(
                json.dumps({"error": "app_id and directory or agent_name are required"}),
                content_type='application/json', status=400
            )

        if directory:
            resolved = os.path.realpath(directory)
        else:
            try:
                resolved = _resolve_canvas_agent_directory(request, agent_name)
            except ValueError as exc:
                return HttpResponse(
                    json.dumps({"error": str(exc)}),
                    content_type='application/json', status=400
                )
            except FileNotFoundError as exc:
                return HttpResponse(
                    json.dumps({"error": str(exc)}),
                    content_type='application/json', status=404
                )

        if not os.path.isdir(resolved):
            return HttpResponse(
                json.dumps({"error": "Directory does not exist"}),
                content_type='application/json', status=400
            )

        if app_id == 'explorer':
            subprocess.Popen(['explorer', resolved])
        elif app_id == 'vscode':
            code_cmd = shutil.which("code")
            if not code_cmd:
                # Try common paths
                for p in [
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
                    os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft VS Code\Code.exe"),
                ]:
                    if os.path.isfile(p):
                        code_cmd = p
                        break
            if not code_cmd:
                return HttpResponse(
                    json.dumps({"error": "VS Code not found"}),
                    content_type='application/json', status=404
                )
            subprocess.Popen([code_cmd, resolved])
        elif app_id == 'antigravity':
            ag_cmd = shutil.which("antigravity")
            if not ag_cmd:
                for p in [
                    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Antigravity\Antigravity.exe"),
                    os.path.expandvars(r"%ProgramFiles%\Antigravity\Antigravity.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Antigravity\Antigravity.exe"),
                    os.path.expandvars(r"%LOCALAPPDATA%\antigravity\Antigravity.exe"),
                ]:
                    if os.path.isfile(p):
                        ag_cmd = p
                        break
            if not ag_cmd:
                return HttpResponse(
                    json.dumps({"error": "Antigravity not found"}),
                    content_type='application/json', status=404
                )
            subprocess.Popen([ag_cmd, resolved])
        elif app_id == 'cmd':
            if os.name != 'nt':
                return HttpResponse(
                    json.dumps({"error": "CMD is only supported on Windows"}),
                    content_type='application/json', status=400
                )
            subprocess.Popen(
                ['cmd.exe', '/K'],
                cwd=resolved,
                creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0),
            )
        else:
            return HttpResponse(
                json.dumps({"error": f"Unknown app: {app_id}"}),
                content_type='application/json', status=400
            )

        return HttpResponse(json.dumps({"success": True}), content_type='application/json')
    except Exception as e:
        print(f"Error opening in app: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_flowbacker_connection_view(request, agent_name):
    """Update a FlowBacker agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'

        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating FlowBacker connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


def update_barrier_connection_view(request, agent_name):
    """Update a Barrier agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'

        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Barrier connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


@csrf_exempt
@require_POST
def update_j_decompiler_connection_view(request, agent_name):
    """Update a J-Decompiler agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'

        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating J-Decompiler connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_de_compresser_connection_view(request, agent_name):
    """Update a De-Compresser agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'

        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating De-Compresser connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_keyboarder_connection_view(request, agent_name):
    """Update a Keyboarder agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')  # 'source' or 'target'

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'agent-1' -> 'agent_1'
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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse target_agent to pool name
        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        # Determine which config list to modify
        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Keyboarder connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)

@csrf_exempt
@require_POST
def update_googler_connection_view(request, agent_name):
    """Update a Googler agent's config.yaml when connections are made/removed."""
    try:
        data = json.loads(request.body.decode('utf-8'))
        target_agent = data.get('target_agent')
        action = data.get('action', 'add')
        connection_type = data.get('type', 'target')  # 'source' or 'target'

        if not target_agent:
            return HttpResponse(json.dumps({"success": False, "message": "Missing target_agent"}),
                                content_type='application/json', status=400)

        # Parse agent_name to pool folder name: 'agent-1' -> 'agent_1'
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
        config_path = os.path.join(pool_base_path, pool_folder_name, 'config.yaml')

        if not os.path.exists(config_path):
            return HttpResponse(json.dumps({"success": False, "message": f"Config not found: {config_path}"}),
                                content_type='application/json', status=404)

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}

        # Parse target_agent to pool name
        target_parts = target_agent.split('-')
        target_cardinal = None
        if target_parts[-1].isdigit():
            target_cardinal = target_parts.pop()
        target_base = "_".join(target_parts)
        target_pool_name = f"{target_base}_{target_cardinal}" if target_cardinal else target_base

        # Determine which config list to modify
        list_name = 'source_agents' if connection_type == 'source' else 'target_agents'
        if list_name not in config or not isinstance(config[list_name], list):
            config[list_name] = []

        if action == 'add':
            if target_pool_name not in config[list_name]:
                config[list_name].append(target_pool_name)
            message = f"Added {target_pool_name} to {list_name}"
        elif action == 'remove':
            if target_pool_name in config[list_name]:
                config[list_name].remove(target_pool_name)
            message = f"Removed {target_pool_name} from {list_name}"
        else:
            message = f"Unknown action: {action}"

        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

        return HttpResponse(json.dumps({"success": True, "message": message}), content_type='application/json')
    except Exception as e:
        print(f"Error updating Googler connection: {e}")
        return HttpResponse(json.dumps({"error": str(e)}), content_type='application/json', status=500)


# ─────────────────────────────────────────────────────────────────────
# ACPX-Skills admin endpoints
# ─────────────────────────────────────────────────────────────────────
# Backing layer for the "ACPX-Skills" navbar dropdown. Read-mostly: the
# Configure dialog (toggle enable/disable) is wired through the existing
# WebSocket `set-skills` channel for symmetry with Mcps/Agents/Tools. The
# HTTP endpoints here power Browse (rich detail), Diagnostics (cross-checks
# against Tool/Mcp/AcpAgent rows), and Reload (re-runs boot_skills()).
#
# Per project preference, the DB stays at "enumeration + enable/disable"
# only. The deep frontmatter / body / triggers / inputs / outputs come
# from agent.skills.registry (the SKILL.md on disk is the source of truth).


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_skill_summary_row(reg_skill, enabled: bool) -> dict:
    """Shape one Browse row by merging the live registry record with the DB toggle."""
    return {
        "name": reg_skill.name,
        "description": reg_skill.description,
        "runtime": reg_skill.runtime,
        "acpx_agent": reg_skill.acpx_agent or "",
        "enabled": bool(enabled),
        "requires_tools": list(reg_skill.requires_tools),
        "requires_mcps": list(reg_skill.requires_mcps),
        "max_iterations": reg_skill.max_iterations,
        "max_seconds": reg_skill.max_seconds,
        "max_tokens": reg_skill.max_tokens,
        "triggers_keywords": list(reg_skill.triggers_keywords),
        "triggers_file_globs": list(reg_skill.triggers_file_globs),
        "body_sha256": reg_skill.body_sha256,
        "skill_md_path": str(reg_skill.skill_md_path),
    }


@login_required
def list_skills_view(request):
    """
    Browse-pane payload. Returns every discovered skill with merged
    enable/disable state from the Skill DB table, plus the orphaned rows
    (DB has them, disk doesn't) so the UI can flag drift.
    """
    try:
        from .skills.registry import skill_registry
        skill_registry.reload_if_stale()
        disk_skills = {s.name: s for s in skill_registry.all()}
        db_rows = {row.name: row for row in Skill.objects.all()}

        out_skills = []
        for name in sorted(disk_skills.keys()):
            db_row = db_rows.get(name)
            enabled = db_row.enabled if db_row else True
            out_skills.append(_build_skill_summary_row(disk_skills[name], enabled))

        orphans = sorted(set(db_rows.keys()) - set(disk_skills.keys()))
        return JsonResponse({
            "skills": out_skills,
            "count": len(out_skills),
            "orphan_db_rows": orphans,
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@login_required
def skill_detail_view(request, skill_name):
    """
    Detail-pane payload for one skill. Includes the rendered body so the
    Browse modal can show the full SKILL.md content without a second
    round-trip.
    """
    try:
        from .skills.registry import skill_registry
        skill_registry.reload_if_stale()
        skill = skill_registry.get(skill_name)
        if skill is None:
            return JsonResponse({"error": f"unknown skill '{skill_name}'"}, status=404)
        db_row = Skill.objects.filter(name=skill_name).first()
        enabled = db_row.enabled if db_row else True
        summary = _build_skill_summary_row(skill, enabled)
        summary["body"] = skill.body
        summary["inputs"] = list(skill.inputs)
        summary["outputs"] = list(skill.outputs)
        summary["permissions"] = dict(skill.permissions) if skill.permissions else {}
        summary["frontmatter_json"] = skill.frontmatter_json
        summary["last_loaded_at"] = skill.last_loaded_at
        return JsonResponse(summary)
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def reload_skills_view(request):
    """
    Reload the skill registry from disk and refresh the Skill DB rows via
    boot_skills(). Cheap and idempotent. Returns the new count.
    """
    try:
        before = Skill.objects.count()
        from .acpx.service import boot_skills
        boot_skills()
        after = Skill.objects.count()
        from .skills.registry import skill_registry
        return JsonResponse({
            "ok": True,
            "skills_loaded": len(skill_registry.all()),
            "db_rows_before": before,
            "db_rows_after": after,
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@login_required
def skills_diagnostics_view(request):
    """
    Cross-check the live registry against Tool / Mcp / AcpAgent rows. Surfaces:
      - skills that require a Tool row that's disabled
      - skills that require an MCP that's disabled
      - skills with runtime=acpx whose acpx_agent isn't a known AcpAgent
      - orphan Skill DB rows (no SKILL.md on disk)
      - duplicate-name candidates (later-wins shadowing)
    Pure read; no writes. Safe to call repeatedly.
    """
    try:
        from .skills.registry import skill_registry
        skill_registry.reload_if_stale()

        live = list(skill_registry.all())
        disk_names = {s.name for s in live}

        tool_enabled = {
            t.toolDescription: (t.toolContent or '').strip().lower() == 'true'
            for t in Tool.objects.all()
        }
        mcp_enabled = {
            m.mcpDescription: (m.mcpContent or '').strip().lower() == 'true'
            for m in Mcp.objects.all()
        }
        try:
            from .models import AcpAgent
            known_acpx_ids = {a.agent_id for a in AcpAgent.objects.all()}
        except Exception:
            known_acpx_ids = set()

        missing_tools = []
        missing_mcps = []
        unknown_acpx_agents = []
        for s in live:
            unmet_tools = [
                t for t in s.requires_tools
                if t in tool_enabled and tool_enabled[t] is False
            ]
            if unmet_tools:
                missing_tools.append({"skill": s.name, "disabled_tools": unmet_tools})
            unmet_mcps = [
                m for m in s.requires_mcps
                if m in mcp_enabled and mcp_enabled[m] is False
            ]
            if unmet_mcps:
                missing_mcps.append({"skill": s.name, "disabled_mcps": unmet_mcps})
            if (s.runtime or '').lower() == 'acpx':
                if s.acpx_agent and known_acpx_ids and s.acpx_agent not in known_acpx_ids:
                    unknown_acpx_agents.append({
                        "skill": s.name,
                        "acpx_agent": s.acpx_agent,
                    })

        orphan_db_rows = sorted(
            row.name for row in Skill.objects.all() if row.name not in disk_names
        )

        return JsonResponse({
            "skill_count": len(live),
            "db_row_count": Skill.objects.count(),
            "missing_tools": missing_tools,
            "missing_mcps": missing_mcps,
            "unknown_acpx_agents": unknown_acpx_agents,
            "orphan_db_rows": orphan_db_rows,
            "tools_known": len(tool_enabled),
            "mcps_known": len(mcp_enabled),
            "acpx_agents_known": len(known_acpx_ids),
        })
    except Exception as e:
        traceback.print_exc()
        return JsonResponse({"error": str(e)}, status=500)
