import ast
from datetime import datetime
import difflib
import json
from langchain.tools import Tool, tool
import os
import re
import sys
import subprocess
import threading
import pathlib
import webbrowser
import shlex
import psutil
import yaml
from django.utils import timezone

from .chat_agent_registry import (
    WRAPPED_CHAT_AGENT_SPECS,
)
from .chat_agent_runtime import (
    create_isolated_runtime_copy,
    get_chat_agent_run,
    list_chat_agent_runs,
    register_chat_agent_run,
    resolve_runtime_script_path,
    serialize_chat_agent_run,
    start_chat_agent_subprocess,
    stop_chat_agent_run,
    tail_runtime_log,
    wait_briefly_for_initial_state,
)
from .imaging.image_interpreter import opus_analyze_image, qwen_analyze_image
from .global_state import get_request_state, global_state
from .models import Agent, AgentProcess
import zipfile
from .path_guard import validate_tool_path


_FLOW_ONLY_PARAM_PREFIXES = (
    'source_agent',
    'source_agents',
    'target_agent',
    'target_agents',
    'output_agent',
    'output_agents',
)

_PARAMETRIZE_AGENT_PATTERNS = [
    r'\bparametriz(?:e|ing)?\s+(?:the\s+)?(?:template\s+)?(?P<name>[a-z0-9 _-]+?)\s+agent\b',
    r'\bconfigure\s+(?:the\s+)?(?:template\s+)?(?P<name>[a-z0-9 _-]+?)\s+agent\b',
    r'\btemplate\s+(?P<name>[a-z0-9 _-]+?)\s+agent\b',
]

_START_AGENT_PATTERNS = [
    r'\bstart(?:-?up)?\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\braise\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\bexecute\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\brun\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
]

_STOP_AGENT_PATTERNS = [
    r'\bstop\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\bterminate\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\bkill\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\bshut\s+down\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
]

_STATUS_AGENT_PATTERNS = [
    r'\b(?:get|check|show)\s+(?:the\s+)?(?:status|state)\s+(?:of\s+)?(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\bwhat(?:\'?s| is)\s+(?:the\s+)?(?:status|state)\s+(?:of\s+)?(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\b(?:[.!?]|$)',
    r'\bis\s+(?:the\s+)?(?:agent\s+)?(?P<name>[a-z0-9 _-]+?)\s+(?:running|alive|up)\b(?:[.!?]|$)',
]

_COMMENT_REQUIRED_HINTS = (
    'required',
    'replace with',
    'at least one',
    'must use',
    'must instruct',
)


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
    if _suppress_visible_console_launches():
        return _launch_python_in_background(python_exe, clean_path, arguments)

    quoted_path = f'"{clean_path}"'

    if ' ' in python_exe and not python_exe.startswith('"'):
        python_exe = f'"{python_exe}"'

    if arguments and arguments.strip():
        cmd_args = f'{quoted_path} {arguments}'
    else:
        cmd_args = f'{quoted_path}'

    full_command = f'start "Tlamatini Console" cmd /k {python_exe} {cmd_args}'
    return subprocess.Popen(full_command, shell=True)


def _suppress_visible_console_launches() -> bool:
    return bool(get_request_state('suppress_visible_consoles', False))


def _parse_script_arguments(arguments):
    if not arguments or not arguments.strip():
        return []
    try:
        return shlex.split(arguments, posix=not sys.platform.startswith('win'))
    except ValueError:
        return arguments.split()


def _build_detached_subprocess_kwargs():
    kwargs = {
        'stdout': subprocess.DEVNULL,
        'stderr': subprocess.DEVNULL,
        'stdin': subprocess.DEVNULL,
    }
    if sys.platform.startswith('win'):
        kwargs['creationflags'] = (
            getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            | getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            | getattr(subprocess, 'DETACHED_PROCESS', 0)
        )
    else:
        kwargs['start_new_session'] = True
    return kwargs


def _launch_python_in_background(python_exe, script_pathfilename, arguments=None, cwd=None):
    command = [python_exe, script_pathfilename, *_parse_script_arguments(arguments)]
    kwargs = _build_detached_subprocess_kwargs()
    if cwd:
        kwargs['cwd'] = cwd
    return subprocess.Popen(command, **kwargs)


def _start_template_agent_process(python_exe, script_path, agent_dir):
    if _suppress_visible_console_launches():
        return _launch_python_in_background(
            python_exe,
            script_path,
            cwd=agent_dir,
        )

    kwargs = {'cwd': agent_dir}
    if sys.platform == 'win32':
        kwargs['creationflags'] = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
    return subprocess.Popen([python_exe, script_path], **kwargs)

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


def _normalize_identifier(value):
    return re.sub(r'[^a-z0-9]+', '', str(value).lower())


def _normalize_param_name(value):
    return re.sub(r'[^a-z0-9]+', '_', str(value).lower()).strip('_')


def _is_flow_only_param_name(param_name):
    normalized = _normalize_param_name(param_name)
    if not normalized:
        return False
    return any(
        normalized == prefix or normalized.startswith(prefix + '_')
        for prefix in _FLOW_ONLY_PARAM_PREFIXES
    )


def _is_path_within_base(base_path, candidate_path):
    try:
        normalized_base = os.path.realpath(os.path.abspath(base_path))
        normalized_candidate = os.path.realpath(os.path.abspath(candidate_path))
        return os.path.commonpath([normalized_base, normalized_candidate]) == normalized_base
    except Exception:
        return False


def _safe_join_under(base_path, *parts):
    candidate = os.path.realpath(os.path.abspath(os.path.join(base_path, *parts)))
    if _is_path_within_base(base_path, candidate):
        return candidate
    return None


def _get_template_agents_roots():
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.realpath(os.path.abspath(os.path.dirname(sys.executable)))
        candidates.extend([
            os.path.join(exe_dir, 'agents'),
            os.path.join(exe_dir, 'Tlamatini', 'agent', 'agents'),
        ])
    else:
        module_dir = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
        candidates.append(os.path.join(module_dir, 'agents'))

    roots = []
    for candidate in candidates:
        resolved = os.path.realpath(os.path.abspath(candidate))
        if os.path.isdir(resolved) and resolved not in roots:
            roots.append(resolved)
    return roots


def _discover_template_agents():
    agents = {}
    for root in _get_template_agents_roots():
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if not entry.is_dir():
                        continue
                    config_path = os.path.join(entry.path, 'config.yaml')
                    if not os.path.isfile(config_path):
                        continue
                    resolved_dir = os.path.realpath(os.path.abspath(entry.path))
                    agents[resolved_dir] = {
                        'root': root,
                        'dir_name': entry.name,
                        'normalized_name': _normalize_identifier(entry.name),
                        'agent_dir': resolved_dir,
                        'config_path': os.path.realpath(os.path.abspath(config_path)),
                    }
        except OSError:
            continue
    return sorted(agents.values(), key=lambda item: item['dir_name'])


def _extract_agent_name_fragment(request_text, patterns=None):
    active_patterns = patterns or _PARAMETRIZE_AGENT_PATTERNS
    for pattern in active_patterns:
        match = re.search(pattern, request_text, flags=re.IGNORECASE | re.DOTALL)
        if match:
            candidate = ' '.join(match.group('name').split())
            candidate = re.sub(
                r'(?:\b(?:please|now|immediately)\b|\bfor\s+me\b)\s*$',
                '',
                candidate,
                flags=re.IGNORECASE,
            ).strip(" \t\r\n,;:!?\"'")
            if candidate:
                return candidate
    return None


def _resolve_template_agent(request_text, patterns=None, action_label='use'):
    available_agents = _discover_template_agents()
    if not available_agents:
        return None, (
            "Error: No template agent directories were found. "
            "Expected either '<install_dir>\\agents\\<agent>' in frozen mode or "
            "'Tlamatini\\agent\\agents\\<agent>' in source mode."
        )

    fragment = _extract_agent_name_fragment(request_text, patterns=patterns)
    if fragment:
        fragment_key = _normalize_identifier(fragment)
        direct_matches = [
            agent for agent in available_agents
            if agent['normalized_name'] == fragment_key
        ]
        if len(direct_matches) == 1:
            return direct_matches[0], None
        close_matches = difflib.get_close_matches(
            fragment_key,
            [agent['normalized_name'] for agent in available_agents],
            n=1,
            cutoff=0.72,
        )
        if close_matches:
            for agent in available_agents:
                if agent['normalized_name'] == close_matches[0]:
                    return agent, None

    normalized_request = _normalize_identifier(request_text)
    request_matches = [
        agent for agent in available_agents
        if agent['normalized_name'] and agent['normalized_name'] in normalized_request
    ]
    if len(request_matches) == 1:
        return request_matches[0], None

    available_names = ', '.join(agent['dir_name'] for agent in available_agents)
    return None, (
        f"Error: Could not determine which template agent to {action_label} from the request. "
        f"Available template agents: {available_names}."
    )


def _find_first_assignment_index(request_text):
    match = re.search(r'[A-Za-z_][A-Za-z0-9_.-]*\s*=', request_text)
    if match:
        return match.start()
    return -1


def _split_assignment_segments(assignments_text):
    segments = []
    current = []
    quote_char = None
    escape_next = False
    bracket_stack = []

    for char in assignments_text:
        if quote_char:
            current.append(char)
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == quote_char:
                quote_char = None
            continue

        if char in ('"', "'"):
            quote_char = char
            current.append(char)
            continue

        if char in '[{(':
            bracket_stack.append(char)
            current.append(char)
            continue

        if char in ']})':
            if bracket_stack:
                bracket_stack.pop()
            current.append(char)
            continue

        if char in ',;\n' and not bracket_stack:
            segment = ''.join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            continue

        current.append(char)

    tail = ''.join(current).strip()
    if tail:
        segments.append(tail)

    return segments


def _split_assignment_segment(segment):
    current = []
    quote_char = None
    escape_next = False
    bracket_stack = []

    for idx, char in enumerate(segment):
        if quote_char:
            current.append(char)
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == quote_char:
                quote_char = None
            continue

        if char in ('"', "'"):
            quote_char = char
            current.append(char)
            continue

        if char in '[{(':
            bracket_stack.append(char)
            current.append(char)
            continue

        if char in ']})':
            if bracket_stack:
                bracket_stack.pop()
            current.append(char)
            continue

        if char == '=' and not bracket_stack:
            key = ''.join(current).strip()
            value = segment[idx + 1:].strip()
            return key, value

        current.append(char)

    return None, None


def _coerce_assignment_value(raw_value):
    value_text = raw_value.strip()
    if value_text == '':
        return ''

    if (
        len(value_text) >= 2
        and value_text[0] == value_text[-1]
        and value_text[0] in ('"', "'")
    ):
        try:
            return ast.literal_eval(value_text)
        except Exception:
            return value_text[1:-1]

    if value_text[0] in '[{(' and value_text[-1] in ']})':
        try:
            return ast.literal_eval(value_text)
        except Exception:
            try:
                return yaml.safe_load(value_text)
            except Exception:
                return value_text

    lowered = value_text.lower()
    if lowered == 'true':
        return True
    if lowered == 'false':
        return False
    if lowered in ('none', 'null'):
        return None
    if re.fullmatch(r'[+-]?\d+', value_text):
        return int(value_text)
    if re.fullmatch(r'[+-]?\d+\.\d+', value_text):
        return float(value_text)

    return value_text


def _parse_requested_assignments(request_text):
    start_index = _find_first_assignment_index(request_text)
    if start_index < 0:
        return [], "Error: No parameter assignments were found. Use key=value pairs."

    assignments_text = request_text[start_index:]
    parsed = []
    ignored = []

    for raw_segment in _split_assignment_segments(assignments_text):
        segment = re.sub(r'^(and|with)\s+', '', raw_segment.strip(), flags=re.IGNORECASE)
        key, value = _split_assignment_segment(segment)
        if not key:
            continue
        clean_key = key.strip().strip('"').strip("'")
        if not clean_key:
            continue
        if _is_flow_only_param_name(clean_key):
            ignored.append(clean_key)
            continue
        parsed.append({
            'requested_key': clean_key,
            'value': _coerce_assignment_value(value),
        })

    if not parsed and ignored:
        return [], (
            "Error: Only flow-wiring parameters were provided. "
            "source_agent/source_agents/target_agent/target_agents/output_agent/output_agents "
            "are ignored by this tool."
        )

    if not parsed:
        return [], "Error: No valid parameter assignments were found after parsing the request."

    return {'assignments': parsed, 'ignored': ignored}, None


def _collect_config_paths(node, prefix=()):
    all_paths = {}
    leaf_paths = {}

    if not isinstance(node, dict):
        return all_paths, leaf_paths

    def walk(current_node, current_prefix):
        for key, value in current_node.items():
            path = current_prefix + (str(key),)
            all_paths[path] = value
            if isinstance(value, dict):
                walk(value, path)
            else:
                leaf_paths[path] = value

    walk(node, prefix)
    return all_paths, leaf_paths


def _format_config_path(path_parts):
    return '.'.join(path_parts)


def _resolve_config_path(requested_key, all_paths, leaf_paths):
    if _is_flow_only_param_name(requested_key):
        return {'ignored': True}

    key_parts = [part for part in re.split(r'[./\\]+', requested_key.strip()) if part]
    normalized_parts = tuple(_normalize_identifier(part) for part in key_parts)

    if len(normalized_parts) > 1:
        exact_path_matches = [
            path for path in all_paths
            if tuple(_normalize_identifier(part) for part in path) == normalized_parts
            and not _is_flow_only_param_name(path[-1])
        ]
        if len(exact_path_matches) == 1:
            return {'path': exact_path_matches[0]}
        if len(exact_path_matches) > 1:
            options = ', '.join(_format_config_path(path) for path in exact_path_matches)
            return {
                'error': (
                    f"Parameter '{requested_key}' is ambiguous. "
                    f"Use one of these dotted paths: {options}."
                )
            }

    normalized_key = _normalize_identifier(requested_key)
    leaf_matches = [
        path for path in leaf_paths
        if _normalize_identifier(path[-1]) == normalized_key
        and not _is_flow_only_param_name(path[-1])
    ]
    if len(leaf_matches) == 1:
        return {'path': leaf_matches[0]}
    if len(leaf_matches) > 1:
        options = ', '.join(_format_config_path(path) for path in leaf_matches)
        return {
            'error': (
                f"Parameter '{requested_key}' is ambiguous for this agent. "
                f"Use one of these dotted paths instead: {options}."
            )
        }

    candidate_names = sorted({
        _format_config_path(path)
        for path in all_paths
        if path and not _is_flow_only_param_name(path[-1])
    })
    suggestions = difflib.get_close_matches(requested_key, candidate_names, n=3, cutoff=0.55)
    suggestion_suffix = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ''
    return {
        'error': (
            f"Parameter '{requested_key}' was not found in the target agent config."
            f"{suggestion_suffix}"
        )
    }


def _set_config_value(config, path_parts, value):
    current = config
    for key in path_parts[:-1]:
        next_value = current.get(key)
        if not isinstance(next_value, dict):
            next_value = {}
            current[key] = next_value
        current = next_value
    current[path_parts[-1]] = value


def _extract_string_key_from_get_call(node):
    if not isinstance(node, ast.Call):
        return None
    if not isinstance(node.func, ast.Attribute) or node.func.attr != 'get':
        return None
    if not node.args:
        return None
    key_node = node.args[0]
    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
        return key_node.value
    return None


def _safe_literal_eval(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


class _ConfigRequirementAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.variable_to_key = {}
        self.required_keys = set()

    def visit_Assign(self, node):
        key_name = _extract_string_key_from_get_call(node.value)
        if key_name:
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.variable_to_key[target.id] = key_name
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        key_name = _extract_string_key_from_get_call(node.value)
        if key_name and isinstance(node.target, ast.Name):
            self.variable_to_key[node.target.id] = key_name
        self.generic_visit(node)

    def visit_If(self, node):
        self.required_keys.update(self._extract_required_keys(node.test))
        self.generic_visit(node)

    def _extract_required_keys(self, node):
        if isinstance(node, ast.BoolOp):
            required = set()
            for value in node.values:
                required.update(self._extract_required_keys(value))
            return required

        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return self._extract_keys_from_reference(node.operand)

        if isinstance(node, ast.Compare) and len(node.ops) == 1 and len(node.comparators) == 1:
            if isinstance(node.ops[0], (ast.Eq, ast.Is)) and self._is_empty_literal(node.comparators[0]):
                return self._extract_keys_from_reference(node.left)

        return set()

    def _extract_keys_from_reference(self, node):
        if isinstance(node, ast.Name):
            return {self.variable_to_key.get(node.id, node.id)}

        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == 'len' and node.args:
                return self._extract_keys_from_reference(node.args[0])

            if isinstance(node.func, ast.Attribute):
                if node.func.attr == 'get':
                    key_name = _extract_string_key_from_get_call(node)
                    if key_name:
                        return {key_name}
                if node.func.attr in ('strip', 'lower', 'upper', 'rstrip', 'lstrip'):
                    return self._extract_keys_from_reference(node.func.value)

        return set()

    def _is_empty_literal(self, node):
        literal = _safe_literal_eval(node)
        return literal in (None, '', [], {}, ())


def _extract_required_key_names(agent_script_path):
    try:
        script_text = pathlib.Path(agent_script_path).read_text(encoding='utf-8')
    except OSError:
        return set()

    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return set()

    analyzer = _ConfigRequirementAnalyzer()
    analyzer.visit(tree)
    return {_normalize_identifier(key) for key in analyzer.required_keys if key}


def _extract_config_comment_hints(config_path):
    comment_hints = {}
    try:
        lines = pathlib.Path(config_path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return comment_hints

    pending_comments = []
    path_stack = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith('#'):
            pending_comments.append(stripped.lstrip('#').strip())
            continue

        match = re.match(r'^(?P<indent>\s*)(?P<key>[A-Za-z0-9_]+):', line)
        if not match:
            pending_comments = []
            continue

        indent = len(match.group('indent').replace('\t', '    '))
        key_name = match.group('key')

        while path_stack and path_stack[-1][0] >= indent:
            path_stack.pop()
        path_stack.append((indent, key_name))

        if pending_comments:
            path = tuple(item[1] for item in path_stack)
            comment_hints[path] = ' '.join(comment for comment in pending_comments if comment).strip()
            pending_comments = []

    return comment_hints


def _comment_requires_value(comment_text):
    if not comment_text:
        return False
    lowered = comment_text.lower()
    return any(hint in lowered for hint in _COMMENT_REQUIRED_HINTS)


def _is_effectively_empty_value(value):
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ''
    if isinstance(value, dict):
        return len(value) == 0
    if isinstance(value, (list, tuple, set)):
        if len(value) == 0:
            return True
        return all(_is_effectively_empty_value(item) for item in value)
    return False


def _find_missing_required_config_paths(config, config_path, agent_script_path):
    all_paths, _leaf_paths = _collect_config_paths(config)
    required_keys = _extract_required_key_names(agent_script_path)
    comment_hints = _extract_config_comment_hints(config_path)
    missing_items = []

    for path_parts, value in all_paths.items():
        if not _is_effectively_empty_value(value):
            continue

        normalized_leaf = _normalize_identifier(path_parts[-1])
        comment_text = comment_hints.get(path_parts, '')
        if normalized_leaf not in required_keys and not _comment_requires_value(comment_text):
            continue

        missing_items.append({
            'path': path_parts,
            'comment': comment_text,
        })

    missing_items.sort(key=lambda item: _format_config_path(item['path']))
    return missing_items


def _resolve_template_agent_script_path(template_agent):
    primary_script = _safe_join_under(template_agent['agent_dir'], f"{template_agent['dir_name']}.py")
    if primary_script and os.path.isfile(primary_script):
        return primary_script

    candidates = []
    try:
        with os.scandir(template_agent['agent_dir']) as entries:
            for entry in entries:
                if entry.is_file() and entry.name.endswith('.py') and entry.name != '__init__.py':
                    candidates.append(os.path.realpath(os.path.abspath(entry.path)))
    except OSError:
        return None

    if len(candidates) == 1:
        return candidates[0]
    return None


def _resolve_python_executable():
    python_home = os.environ.get('PYTHON_HOME', '')
    if python_home:
        python_exe = os.path.join(python_home, 'python.exe')
        if os.path.isfile(python_exe):
            return python_exe, None
        return None, f"PYTHON_HOME is set to '{python_home}' but python.exe was not found there."

    if getattr(sys, 'frozen', False):
        return 'python', None

    return sys.executable, None


def _get_agent_process_label(template_agent):
    for agent in get_all_agents():
        description = agent.get('agentDescription', '')
        if _normalize_identifier(description) == template_agent['normalized_name']:
            return description
    return template_agent['dir_name']


def _read_running_pid(agent_dir):
    pid_path = os.path.join(agent_dir, 'agent.pid')
    if not os.path.exists(pid_path):
        return None

    try:
        with open(pid_path, 'r', encoding='utf-8') as file_handle:
            pid = int(file_handle.read().strip())
    except (OSError, ValueError):
        return None

    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        return pid
    except Exception:
        return None


def _remove_pid_file(agent_dir):
    pid_path = os.path.join(agent_dir, 'agent.pid')
    if not os.path.exists(pid_path):
        return False
    try:
        os.remove(pid_path)
        return True
    except OSError:
        return False


def _get_live_process(pid):
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        return process
    except Exception:
        return None


def _find_processes_by_script(script_path):
    if not script_path or not os.path.isfile(script_path):
        return []

    normalized_script = os.path.normcase(os.path.realpath(os.path.abspath(script_path)))
    matches = {}

    for process in psutil.process_iter(['pid', 'cmdline']):
        try:
            cmdline = process.info.get('cmdline') or []
        except Exception:
            continue

        for arg in cmdline:
            if not arg:
                continue
            try:
                normalized_arg = os.path.normcase(os.path.realpath(os.path.abspath(arg)))
            except Exception:
                continue
            if normalized_arg == normalized_script:
                matches[process.pid] = process
                break

    return [matches[pid] for pid in sorted(matches)]


def _get_template_agent_runtime_state(template_agent, script_path=None):
    process_label = _get_agent_process_label(template_agent)
    processes_by_pid = {}
    stale_pid_file = False
    stale_registry = False

    running_pid = _read_running_pid(template_agent['agent_dir'])
    pid_path = os.path.join(template_agent['agent_dir'], 'agent.pid')
    if running_pid:
        process = _get_live_process(running_pid)
        if process:
            processes_by_pid[process.pid] = process
    elif os.path.exists(pid_path):
        stale_pid_file = True

    tracked_process = get_agent_process_by_description(process_label)
    if tracked_process:
        process = _get_live_process(tracked_process.agentProcessPid)
        if process:
            processes_by_pid[process.pid] = process
        else:
            stale_registry = True
            delete_agent_process_by_description(process_label)

    for process in _find_processes_by_script(script_path):
        processes_by_pid[process.pid] = process

    if stale_pid_file and not processes_by_pid:
        _remove_pid_file(template_agent['agent_dir'])

    return {
        'label': process_label,
        'processes': [processes_by_pid[pid] for pid in sorted(processes_by_pid)],
        'stale_pid_file': stale_pid_file,
        'stale_registry': stale_registry,
    }


def _terminate_process_tree(process):
    targeted = {}
    try:
        for child in process.children(recursive=True):
            targeted[child.pid] = child
    except Exception:
        pass
    targeted[process.pid] = process

    ordered_processes = [targeted[pid] for pid in sorted(targeted, reverse=True)]
    errors = []

    for current in ordered_processes:
        try:
            current.terminate()
        except psutil.NoSuchProcess:
            continue
        except Exception as exc:
            errors.append(f"{current.pid}: {exc}")

    _gone, alive = psutil.wait_procs(ordered_processes, timeout=3)
    if alive:
        for current in alive:
            try:
                current.kill()
            except psutil.NoSuchProcess:
                continue
            except Exception as exc:
                errors.append(f"{current.pid}: {exc}")
        _gone, alive = psutil.wait_procs(alive, timeout=3)

    surviving_pids = {current.pid for current in alive}
    stopped_pids = sorted(pid for pid in targeted if pid not in surviving_pids)

    return {
        'stopped_pids': stopped_pids,
        'surviving_pids': sorted(surviving_pids),
        'errors': errors,
    }

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


def _tool_status_key(tool_description):
    return f"tool_{str(tool_description).lower()}_status"


def _tool_output(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _find_template_agent_by_dir_name(dir_name):
    normalized = _normalize_identifier(dir_name)
    for agent in _discover_template_agents():
        if agent['normalized_name'] == normalized:
            return agent
    return None


def _maybe_parse_requested_assignments(request_text):
    if _find_first_assignment_index(request_text) < 0:
        return {'assignments': [], 'ignored': []}, None
    return _parse_requested_assignments(request_text)


def _apply_requested_assignments_to_config(config, request_text):
    parse_result, parse_error = _maybe_parse_requested_assignments(request_text)
    if parse_error:
        return None, parse_error, []

    if not isinstance(parse_result, dict):
        return None, "Error: Could not parse agent parameter assignments.", []

    all_paths, leaf_paths = _collect_config_paths(config)
    pending_updates = []
    resolution_errors = []
    ignored_params = list(parse_result.get('ignored', []))

    if all_paths:
        for assignment in parse_result.get('assignments', []):
            requested_key = assignment['requested_key']
            resolution = _resolve_config_path(requested_key, all_paths, leaf_paths)
            if resolution.get('ignored'):
                ignored_params.append(requested_key)
                continue
            if resolution.get('error'):
                resolution_errors.append(resolution['error'])
                continue
            pending_updates.append({
                'path': resolution['path'],
                'value': assignment['value'],
            })
    elif parse_result.get('assignments'):
        resolution_errors.append("The target agent config has no assignable YAML keys.")

    if resolution_errors:
        return None, " ".join(resolution_errors), ignored_params

    changed_paths = []
    for update in pending_updates:
        _set_config_value(config, update['path'], update['value'])
        changed_paths.append(_format_config_path(update['path']))

    return config, None, ignored_params + changed_paths


def _non_flow_missing_required_paths(config, config_path, script_path):
    missing_items = _find_missing_required_config_paths(config, config_path, script_path)
    filtered = []
    for item in missing_items:
        path = item.get('path') or ()
        if not path:
            continue
        if _is_flow_only_param_name(path[-1]):
            continue
        filtered.append(item)
    return filtered


def _launch_wrapped_chat_agent(spec, request):
    if not request or not str(request).strip():
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"No request was provided to {spec.display_name}.",
        })

    template_agent = _find_template_agent_by_dir_name(spec.template_dir)
    if template_agent is None:
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": (
                f"Template agent directory '{spec.template_dir}' was not found. "
                "The wrapped chat agent could not be launched."
            ),
        })

    try:
        run_id, runtime_dir, log_path = create_isolated_runtime_copy(
            template_agent['agent_dir'],
            spec.template_dir,
        )
    except Exception as exc:
        return _tool_output({
            "status": "error",
            "retryable": True,
            "message": f"Failed to create the isolated runtime copy for {spec.display_name}: {exc}",
        })

    runtime_config_path = os.path.join(runtime_dir, "config.yaml")
    try:
        with open(runtime_config_path, "r", encoding="utf-8") as file_handle:
            runtime_config = yaml.safe_load(file_handle) or {}
    except Exception as exc:
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"Failed to load runtime config.yaml for {spec.display_name}: {exc}",
            "runtime_dir": runtime_dir,
        })

    if not isinstance(runtime_config, dict):
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": "The runtime config.yaml is not a YAML mapping.",
            "runtime_dir": runtime_dir,
        })

    runtime_config, assignment_error, assignment_notes = _apply_requested_assignments_to_config(
        runtime_config,
        str(request),
    )
    if assignment_error:
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": assignment_error,
            "runtime_dir": runtime_dir,
        })

    try:
        with open(runtime_config_path, "w", encoding="utf-8") as file_handle:
            yaml.safe_dump(
                runtime_config,
                file_handle,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )
    except Exception as exc:
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"Failed to write runtime config.yaml for {spec.display_name}: {exc}",
            "runtime_dir": runtime_dir,
        })

    runtime_script_path = resolve_runtime_script_path(runtime_dir, spec.template_dir)
    if not runtime_script_path:
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"Could not resolve the runtime startup script for {spec.display_name}.",
            "runtime_dir": runtime_dir,
        })

    missing_required = _non_flow_missing_required_paths(runtime_config, runtime_config_path, runtime_script_path)
    if missing_required:
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": (
                f"{spec.display_name} is still missing mandatory non-flow parameters: "
                + ", ".join(_format_config_path(item['path']) for item in missing_required)
            ),
            "runtime_dir": runtime_dir,
            "log_path": log_path,
        })

    run = register_chat_agent_run(
        run_id=run_id,
        tool_description=spec.tool_description,
        template_dir=spec.template_dir,
        runtime_dir=runtime_dir,
        log_path=log_path,
        request_text=str(request),
    )

    try:
        start_chat_agent_subprocess(run, runtime_script_path)
    except Exception as exc:
        run.status = "failed"
        run.finishedAt = timezone.now()
        run.save(update_fields=["status", "finishedAt"])
        return _tool_output({
            "status": "error",
            "retryable": True,
            "message": f"Failed to start {spec.display_name}: {exc}",
            "run_id": run.runId,
            "runtime_dir": runtime_dir,
            "log_path": log_path,
        })

    run = wait_briefly_for_initial_state(run, seconds=spec.poll_window_seconds)
    payload = serialize_chat_agent_run(run, include_log_excerpt=True)
    payload["tool"] = spec.tool_name
    payload["display_name"] = spec.display_name
    payload["assignment_notes"] = assignment_notes
    payload["long_running"] = spec.long_running

    if run.status == "running":
        payload["message"] = (
            f"{spec.display_name} started in an isolated runtime copy and is still running. "
            "Use chat_agent_run_status, chat_agent_run_log, and chat_agent_run_stop with this run_id."
        )
    elif run.status == "completed":
        payload["message"] = f"{spec.display_name} completed in the isolated runtime copy."
    elif run.status == "failed":
        payload["message"] = f"{spec.display_name} finished with a failure state. Inspect the log excerpt."
        payload["retryable"] = False
    else:
        payload["message"] = f"{spec.display_name} ended with status '{run.status}'."

    return _tool_output(payload)


_WRAPPED_CHAT_AGENT_TOOLS = {}


def _build_wrapped_chat_agent_tool(spec):
    cached = _WRAPPED_CHAT_AGENT_TOOLS.get(spec.tool_name)
    if cached is not None:
        return cached

    def _runner(request: str) -> str:
        return _launch_wrapped_chat_agent(spec, request)

    _runner.__name__ = spec.tool_name
    description = (
        f"Launch the {spec.display_name} template agent in an isolated subprocess runtime copy. "
        f"Use it when you need to {spec.purpose.lower()} "
        f"Pass the full natural-language intent plus explicit key=value assignments when needed. "
        f"Example: {spec.example_request}. "
        "The template directory is never mutated; the tool returns JSON with run_id, status, runtime_dir, log_path, and log_excerpt."
    )
    wrapped_tool = Tool.from_function(
        func=_runner,
        name=spec.tool_name,
        description=description,
    )
    _WRAPPED_CHAT_AGENT_TOOLS[spec.tool_name] = wrapped_tool
    return wrapped_tool

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
        if _suppress_visible_console_launches():
            return (
                f"Command '{command}' executed successfully in the background without "
                "opening a console window."
            )
        return f"Command '{command}' executed successfully in a new terminal window."
    except Exception as e:
        return f"Error executing command '{command}': {e}"

@tool
def execute_command(command: str) -> str:
    """
    Execute a shell/system command. Use this for ANY command-line operation: installing packages,
    building software, running scripts, checking system state, git, pip, npm, choco, winget, cmake, etc.

    CRITICAL: Pass the COMPLETE command exactly as the user specified, including all arguments.

    Examples of what to pass:
    - 'pip install requests'
    - 'git clone https://github.com/open-quantum-safe/liboqs.git'
    - 'cmake -G "Visual Studio 17 2022" ..'
    - 'dir *.log'
    - 'python manage.py migrate'
    - 'choco install cmake --yes'
    - If under your process to answer the user you need the execution of a command that is in certain directory you MUST pass the command with its complete path.

    Input:
    - command: The complete command string to execute
               (e.g., "pip install flask", "git status", "cmake --build .", "dir /s", "ipconfig", "ping 8.8.8.8")
    """
    try:
        if not command or command.strip() == "":
            return "Error: No command provided. Please specify the command to execute."

        _is_windows = sys.platform.startswith("win")

        # ── Path guard: validate any path-like tokens in the command ──
        try:
            tokens = shlex.split(command, posix=not _is_windows)
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

        # On Windows, always use shell=True so that builtins (dir, type, mkdir,
        # echo, copy, move, del, set, cd) and commands with backslash paths work
        # correctly.  On Unix, try non-shell first and fall back to shell=True.
        if _is_windows:
            result = subprocess.run(command, capture_output=True, text=True, shell=True)
        else:
            try:
                cmd_list = shlex.split(command)
                result = subprocess.run(cmd_list, capture_output=True, text=True, shell=False)
            except (ValueError, FileNotFoundError):
                result = subprocess.run(command, shell=True, capture_output=True, text=True)

        output = result.stdout or ""
        error_output = result.stderr or ""
        # Many CLI tools write progress/info to stderr even on success
        combined = output
        if error_output:
            combined = f"{output}\nStderr: {error_output}" if output else f"Stderr: {error_output}"

        if result.returncode != 0:
            return f"Error: Command '{command}' failed with return code {result.returncode}. Output: {combined}"
        else:
            return f"Command '{command}' executed successfully. Output: {combined}"
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


@tool
def agent_parametrizer(request: str) -> str:
    """
    Parametrize a template agent by updating its config.yaml without starting it.

    CRITICAL: Pass the COMPLETE instruction, including the target template agent name
    and every parameter assignment as key=value pairs.

    Rules:
    - This tool only changes template-agent config files under:
      - source mode: Tlamatini\\agent\\agents\\<agent_name>
      - frozen mode: <install_dir>\\agents\\<agent_name>
    - This tool NEVER starts the agent.
    - Do NOT send source_agent/source_agents/target_agent/target_agents/output_agent/output_agents.
      Those flow-only parameters are ignored.
    - If a parameter name is ambiguous, use its dotted config path.

    Examples of what to pass:
    - Parametrize the template Telegramer agent to set api_id=123456, api_hash='adcb5adcbbad6676adc98112345678910', chat_id='Angela-Bennet', message='Telegramer parametrized and launched'
    - Parametrize the template Emailer agent to set host='smtp.gmail.com', port=587, username='user@gmail.com', password='secret', from_address='user@gmail.com', to_addresses=['ops@example.com','soc@example.com'], subject='Alert generated', body='Emailer parametrized'
    - Parametrize the template Gatewayer agent to set http.host='0.0.0.0', http.port=8787, auth.mode='bearer', auth.bearer_token='super-secret-token', payload.required_fields=['event_type','session_id']
    - Parametrize the template J-Decompiler agent to set directory='C:\\Temp\\*.class,*.jar,*.war,*.ear', recursive=true

    Input:
    - request: A full natural-language parametrization instruction.
    """
    try:
        if not request or not request.strip():
            return "Error: No parametrization request was provided."

        template_agent, resolve_error = _resolve_template_agent(
            request,
            patterns=_PARAMETRIZE_AGENT_PATTERNS,
            action_label='parametrize',
        )
        if resolve_error:
            return resolve_error

        config_path = template_agent['config_path']
        if not _is_path_within_base(template_agent['root'], config_path):
            return (
                "Error: Resolved template agent config escaped the template agents directory. "
                "No changes were written."
            )

        parse_result, parse_error = _parse_requested_assignments(request)
        if parse_error:
            return parse_error

        with open(config_path, 'r', encoding='utf-8') as file_handle:
            config = yaml.safe_load(file_handle) or {}

        if not isinstance(config, dict):
            return (
                f"Error: Agent config '{config_path}' is not a YAML mapping. "
                "No changes were written."
            )

        all_paths, leaf_paths = _collect_config_paths(config)
        if not all_paths:
            return (
                f"Error: Agent '{template_agent['dir_name']}' has no assignable parameters "
                "in config.yaml."
            )

        pending_updates = []
        resolution_errors = []
        ignored_params = list(parse_result['ignored'])

        for assignment in parse_result['assignments']:
            requested_key = assignment['requested_key']
            resolution = _resolve_config_path(requested_key, all_paths, leaf_paths)
            if resolution.get('ignored'):
                ignored_params.append(requested_key)
                continue
            if resolution.get('error'):
                resolution_errors.append(resolution['error'])
                continue
            pending_updates.append({
                'path': resolution['path'],
                'value': assignment['value'],
            })

        if resolution_errors:
            return "Error parametrizing agent config: " + " ".join(resolution_errors)

        if not pending_updates:
            if ignored_params:
                ignored_summary = ', '.join(sorted(set(ignored_params)))
                return (
                    "Error: No assignable parameters were left after ignoring flow-only fields. "
                    f"Ignored: {ignored_summary}."
                )
            return "Error: No matching config parameters were resolved."

        changed_paths = []
        for update in pending_updates:
            _set_config_value(config, update['path'], update['value'])
            changed_paths.append(_format_config_path(update['path']))

        with open(config_path, 'w', encoding='utf-8') as file_handle:
            yaml.safe_dump(
                config,
                file_handle,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

        changed_summary = ', '.join(changed_paths)
        ignored_suffix = ''
        if ignored_params:
            ignored_summary = ', '.join(sorted(set(ignored_params)))
            ignored_suffix = f" Ignored flow-only parameters: {ignored_summary}."

        return (
            f"Template agent '{template_agent['dir_name']}' parametrized successfully. "
            f"Updated config keys: {changed_summary}. Config path: '{config_path}'."
            f"{ignored_suffix}"
        )
    except Exception as e:
        return f"Error parametrizing template agent: {e}"


@tool
def agent_starter(request: str) -> str:
    """
    Start a template agent only after validating that its mandatory config values are not empty.

    CRITICAL: Pass the COMPLETE instruction exactly as the user requested, including the
    agent name.

    Rules:
    - This tool starts template agents only, never pool instances.
    - Before starting, it validates the template config.yaml and blocks startup if required
      values are still empty.
    - It auto-detects the template agents directory in both source and frozen installs.

    Examples of what to pass:
    - Start-up the agent Telegrammer
    - Start-up the agent Crawler
    - Raise the agent Summarizer
    - Execute the agent Telegramrx
    - Run the agent J-Decompiler

    Input:
    - request: A full natural-language startup instruction.
    """
    try:
        if not request or not request.strip():
            return "Error: No startup request was provided."

        template_agent, resolve_error = _resolve_template_agent(
            request,
            patterns=_START_AGENT_PATTERNS,
            action_label='start',
        )
        if resolve_error:
            return resolve_error

        script_path = _resolve_template_agent_script_path(template_agent)
        if not script_path or not os.path.isfile(script_path):
            return (
                f"Error: Could not resolve the startup script for template agent "
                f"'{template_agent['dir_name']}'."
            )

        config_path = template_agent['config_path']
        with open(config_path, 'r', encoding='utf-8') as file_handle:
            config = yaml.safe_load(file_handle) or {}

        if not isinstance(config, dict):
            return (
                f"Error: Agent config '{config_path}' is not a YAML mapping. "
                "The agent was not started."
            )

        missing_items = _find_missing_required_config_paths(config, config_path, script_path)
        if missing_items:
            missing_summary = ', '.join(_format_config_path(item['path']) for item in missing_items)
            return (
                f"Template agent '{template_agent['dir_name']}' was not started because "
                f"mandatory config values are still empty: {missing_summary}. "
                f"Config path: '{config_path}'."
            )

        runtime_state = _get_template_agent_runtime_state(template_agent, script_path)
        if runtime_state['processes']:
            running_pid = runtime_state['processes'][0].pid
            return (
                f"Template agent '{template_agent['dir_name']}' is already running with "
                f"process ID: {running_pid}."
            )

        python_exe, python_error = _resolve_python_executable()
        if python_error:
            return python_error

        process = _start_template_agent_process(
            python_exe,
            script_path,
            template_agent['agent_dir'],
        )

        process_label = _get_agent_process_label(template_agent)
        save_agent_process(process_label, process.pid)

        launch_suffix = ""
        if _suppress_visible_console_launches():
            launch_suffix = " The process was launched in the background without opening a console window."

        return (
            f"Template agent '{template_agent['dir_name']}' started successfully with "
            f"process ID: {process.pid}. Script path: '{script_path}'."
            f"{launch_suffix}"
        )
    except Exception as e:
        return f"Error starting template agent: {e}"


@tool
def agent_stopper(request: str) -> str:
    """
    Stop a running template agent and clean stale runtime tracking if needed.

    CRITICAL: Pass the COMPLETE instruction exactly as the user requested, including the
    agent name.

    Rules:
    - This tool stops template agents only, never pool instances.
    - It auto-detects the template agents directory in both source and frozen installs.
    - It reconciles PID files, AgentProcess rows, and real OS processes before stopping.

    Examples of what to pass:
    - Stop the agent Telegrammer
    - Stop the agent Crawler
    - Terminate the agent Summarizer
    - Shut down the agent Telegramrx
    - Kill the agent Sleeper

    Input:
    - request: A full natural-language stop instruction.
    """
    try:
        if not request or not request.strip():
            return "Error: No stop request was provided."

        template_agent, resolve_error = _resolve_template_agent(
            request,
            patterns=_STOP_AGENT_PATTERNS,
            action_label='stop',
        )
        if resolve_error:
            return resolve_error

        script_path = _resolve_template_agent_script_path(template_agent)
        runtime_state = _get_template_agent_runtime_state(template_agent, script_path)
        processes = runtime_state['processes']

        if not processes:
            cleanup_notes = []
            if runtime_state['stale_pid_file']:
                cleanup_notes.append('removed a stale agent.pid file')
            if runtime_state['stale_registry']:
                cleanup_notes.append('removed a stale AgentProcess row')

            cleanup_suffix = ''
            if cleanup_notes:
                cleanup_suffix = ' Runtime cleanup: ' + ', '.join(cleanup_notes) + '.'

            return (
                f"Template agent '{template_agent['dir_name']}' is not currently running."
                f"{cleanup_suffix}"
            )

        stopped_pids = []
        surviving_pids = []
        errors = []

        for process in processes:
            termination_result = _terminate_process_tree(process)
            stopped_pids.extend(termination_result['stopped_pids'])
            surviving_pids.extend(termination_result['surviving_pids'])
            errors.extend(termination_result['errors'])

        delete_agent_process_by_description(runtime_state['label'])
        _remove_pid_file(template_agent['agent_dir'])

        surviving_pids = sorted(set(surviving_pids))
        stopped_pids = sorted(set(stopped_pids))

        if surviving_pids:
            error_suffix = ''
            if errors:
                error_suffix = f" Errors: {'; '.join(errors)}."
            return (
                f"Template agent '{template_agent['dir_name']}' could not be fully stopped. "
                f"Still running process IDs: {', '.join(str(pid) for pid in surviving_pids)}."
                f"{error_suffix}"
            )

        details = ''
        if errors:
            details = f" Notes: {'; '.join(errors)}."

        stopped_summary = ', '.join(str(pid) for pid in stopped_pids) if stopped_pids else 'unknown'
        return (
            f"Template agent '{template_agent['dir_name']}' stopped successfully. "
            f"Terminated process IDs: {stopped_summary}.{details}"
        )
    except Exception as e:
        return f"Error stopping template agent: {e}"


@tool
def agent_stat_getter(request: str) -> str:
    """
    Report whether a template agent is currently running.

    CRITICAL: Pass the COMPLETE instruction exactly as the user requested, including the
    agent name.

    Rules:
    - This tool checks template agents only, never pool instances.
    - It auto-detects the template agents directory in both source and frozen installs.
    - It reconciles PID files, AgentProcess rows, and real OS processes before answering.

    Examples of what to pass:
    - Get the status of agent Telegrammer
    - Check the status of agent Crawler
    - Show the state of agent Summarizer
    - Is the agent Telegramrx running
    - What is the status of agent Sleeper

    Input:
    - request: A full natural-language status instruction.
    """
    try:
        if not request or not request.strip():
            return "Error: No status request was provided."

        template_agent, resolve_error = _resolve_template_agent(
            request,
            patterns=_STATUS_AGENT_PATTERNS,
            action_label='inspect',
        )
        if resolve_error:
            return resolve_error

        script_path = _resolve_template_agent_script_path(template_agent)
        runtime_state = _get_template_agent_runtime_state(template_agent, script_path)
        processes = runtime_state['processes']

        if not processes:
            cleanup_notes = []
            if runtime_state['stale_pid_file']:
                cleanup_notes.append('removed a stale agent.pid file')
            if runtime_state['stale_registry']:
                cleanup_notes.append('removed a stale AgentProcess row')

            cleanup_suffix = ''
            if cleanup_notes:
                cleanup_suffix = ' Runtime cleanup: ' + ', '.join(cleanup_notes) + '.'

            return (
                f"Template agent '{template_agent['dir_name']}' is not currently running."
                f"{cleanup_suffix}"
            )

        pid_list = []
        status_list = []
        for process in processes:
            pid_list.append(str(process.pid))
            try:
                status_list.append(f"{process.pid}:{process.status()}")
            except Exception:
                status_list.append(f"{process.pid}:unknown")

        return (
            f"Template agent '{template_agent['dir_name']}' is currently running. "
            f"Process IDs: {', '.join(pid_list)}. "
            f"Observed states: {', '.join(status_list)}."
        )
    except Exception as e:
        return f"Error getting template agent status: {e}"


def _normalize_run_id(run_id):
    if run_id is None:
        return ""
    return str(run_id).strip().strip('"').strip("'")


@tool
def chat_agent_run_list() -> str:
    """
    List recent wrapped chat-agent runs.

    Use this tool when you need the latest run IDs before checking status,
    reading logs, or stopping a running isolated chat-agent subprocess.
    """
    runs = list_chat_agent_runs()
    return _tool_output({
        "status": "ok",
        "runs": [serialize_chat_agent_run(run, include_log_excerpt=False) for run in runs],
    })


@tool
def chat_agent_run_status(run_id: str) -> str:
    """
    Get the current status of a wrapped chat-agent runtime by run_id.
    """
    normalized = _normalize_run_id(run_id)
    run = get_chat_agent_run(normalized)
    if run is None:
        return _tool_output({
            "status": "error",
            "message": f"Wrapped chat-agent run '{normalized}' was not found.",
        })
    return _tool_output(serialize_chat_agent_run(run, include_log_excerpt=True))


@tool
def chat_agent_run_log(run_id: str) -> str:
    """
    Read the latest log excerpt of a wrapped chat-agent runtime by run_id.
    """
    normalized = _normalize_run_id(run_id)
    run = get_chat_agent_run(normalized)
    if run is None:
        return _tool_output({
            "status": "error",
            "message": f"Wrapped chat-agent run '{normalized}' was not found.",
        })
    payload = serialize_chat_agent_run(run, include_log_excerpt=False)
    payload["log_excerpt"] = tail_runtime_log(run.logPath)
    return _tool_output(payload)


@tool
def chat_agent_run_stop(run_id: str) -> str:
    """
    Stop a wrapped chat-agent runtime by run_id.
    """
    normalized = _normalize_run_id(run_id)
    run = get_chat_agent_run(normalized)
    if run is None:
        return _tool_output({
            "status": "error",
            "message": f"Wrapped chat-agent run '{normalized}' was not found.",
        })
    termination = stop_chat_agent_run(run)
    payload = serialize_chat_agent_run(run, include_log_excerpt=True)
    payload["stopped_pids"] = termination["stopped_pids"]
    payload["surviving_pids"] = termination["surviving_pids"]
    payload["errors"] = termination["errors"]
    return _tool_output(payload)


def _extract_readable_text(html_content):
    """Extract readable text from HTML content, stripping tags, scripts, and styles."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html_content, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)
    except ImportError:
        import html as html_mod
        text = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = html_mod.unescape(text)
        text = re.sub(r'[ \t]+', ' ', text)
        lines = [line.strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line)


_GOOGLER_BROWSER_ARGS = [
    '--disable-blink-features=AutomationControlled',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
]

_GOOGLER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_GOOGLER_RESULT_SELECTORS = [
    '#rso a:has(h3)',
    '#search a:has(h3)',
    'div.g a[href^="http"]',
    '#rso a[href^="http"]',
    'div#search a[href^="http"]',
]

_GOOGLER_DDG_RESULT_SELECTORS = [
    'article[data-testid="result"] a[data-testid="result-title-a"]',
    'a.result__a',
    'h2 a[href^="http"]',
]

_GOOGLER_BINARY_EXTENSIONS = {
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.gz', '.tar', '.rar', '.7z', '.exe', '.dmg',
    '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp',
    '.mp3', '.mp4', '.avi', '.mov', '.wav',
}

_GOOGLER_BINARY_CONTENT_TYPES = {
    'application/pdf', 'application/octet-stream',
    'application/zip', 'application/gzip',
    'application/msword', 'application/vnd.ms-excel',
    'application/vnd.ms-powerpoint',
    'application/vnd.openxmlformats-officedocument',
}


def _dismiss_consent_banner(page) -> None:
    """Try to dismiss Google's cookie consent banner if present."""
    consent_selectors = [
        'button:has-text("Accept all")',
        'button:has-text("Accept")',
        'button:has-text("Acepto")',
        'button:has-text("Aceptar todo")',
        'button:has-text("Tout accepter")',
        'button:has-text("Alle akzeptieren")',
        'button:has-text("Accetta tutto")',
        'button#L2AGLb',
        'button[aria-label="Accept all"]',
        'div[role="dialog"] button:first-of-type',
    ]
    for selector in consent_selectors:
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue


def _googler_extract_links(page, selectors, skip_domains=None):
    """Try each selector in order; return first non-empty list of unique URLs."""
    from urllib.parse import urlparse as _urlparse
    if skip_domains is None:
        skip_domains = {'google.com', 'google.co', 'accounts.google', 'support.google',
                        'maps.google', 'policies.google'}
    for selector in selectors:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue
        if not elements:
            continue

        urls, seen = [], set()
        for elem in elements:
            href = elem.get_attribute("href")
            if not href or not href.startswith("http"):
                continue
            try:
                domain = _urlparse(href).netloc.lower()
            except Exception:
                continue
            if any(sd in domain for sd in skip_domains):
                continue
            if domain in seen:
                continue
            seen.add(domain)
            urls.append(href)
        if urls:
            return urls
    return []


def _googler_is_binary(url: str, content_type: str = '') -> bool:
    """Check if URL or Content-Type indicates binary content."""
    from urllib.parse import urlparse as _urlparse
    path = _urlparse(url).path.lower().split('?')[0]
    if any(path.endswith(ext) for ext in _GOOGLER_BINARY_EXTENSIONS):
        return True
    if content_type:
        ct = content_type.lower().split(';')[0].strip()
        if ct in _GOOGLER_BINARY_CONTENT_TYPES:
            return True
        if ct.startswith(('image/', 'audio/', 'video/')):
            return True
        if 'officedocument' in ct:
            return True
    return False


def _googler_fetch_page_text(page, url: str) -> dict:
    """Navigate Playwright page to URL and extract rendered visible text.
    Skips binary content (PDFs, images, etc.)."""
    if _googler_is_binary(url):
        return {"url": url, "error": "Binary file detected from URL extension, skipped"}

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        return {"url": url, "error": str(e)}

    if not response:
        return {"url": url, "error": "No response received"}

    status = response.status
    content_type = response.headers.get('content-type', '')
    if _googler_is_binary('', content_type):
        return {"url": url, "status_code": status,
                "error": f"Binary content-type ({content_type}), skipped"}

    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass

    try:
        text = page.inner_text('body')
    except Exception:
        text = ""

    if text:
        lines = text.splitlines()
        cleaned, blank_count = [], 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_count += 1
                if blank_count <= 1:
                    cleaned.append('')
            else:
                blank_count = 0
                cleaned.append(stripped)
        text = '\n'.join(cleaned).strip()

    max_chars = 50000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"

    return {"url": url, "status_code": status, "content": text}


@tool
def googler(query: str, number_of_results: int = 5) -> str:
    """
    Search Google for a topic and return the top results with their readable text content.
    Falls back to DuckDuckGo if Google returns no results.
    Automatically skips binary content (PDFs, images, etc.).

    Use this tool when the user asks to search the internet, Google something,
    look up information online, or needs current real-time information.

    Examples of what to pass:
    - User says "Google Python asyncio tutorial" → pass query="Python asyncio tutorial"
    - User says "Search the internet for Django 5.2 release notes" → pass query="Django 5.2 release notes"
    - User says "Look up the latest CVE vulnerabilities" → pass query="latest CVE vulnerabilities 2026"
    - User says "Find online info about Kubernetes ingress" → pass query="Kubernetes ingress controllers"
    - User says "Google nginx reverse proxy, top 3" → pass query="nginx reverse proxy", number_of_results=3

    Input:
    - query: The search query or phrase to look up on Google.
    - number_of_results: Number of top sites to fetch (default 5, max 10).
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return (
            "Error: Playwright is not installed. "
            "Install it with: pip install playwright && playwright install chromium"
        )

    if not query or not str(query).strip():
        return "Error: No search query provided. Please specify what to search for."

    number_of_results = max(1, min(int(number_of_results), 10))
    outcomes = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=_GOOGLER_BROWSER_ARGS)
            context = browser.new_context(
                user_agent=_GOOGLER_USER_AGENT,
                viewport={'width': 1920, 'height': 1080},
                locale='en-US',
            )
            context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = context.new_page()

            try:
                # --- Google search ---
                page.goto("https://www.google.com", wait_until="domcontentloaded", timeout=15000)
                _dismiss_consent_banner(page)

                search_box = page.wait_for_selector(
                    'textarea[name="q"], input[name="q"]', timeout=10000
                )
                search_box.fill(str(query))
                search_box.press("Enter")

                try:
                    page.wait_for_selector('#rso, #search, div.g', timeout=15000)
                except Exception:
                    pass
                page.wait_for_timeout(2000)

                top_links = _googler_extract_links(page, _GOOGLER_RESULT_SELECTORS)

                # --- DuckDuckGo fallback ---
                if not top_links:
                    page.goto(
                        f"https://duckduckgo.com/?q={str(query).replace(' ', '+')}&t=h_&ia=web",
                        wait_until="domcontentloaded", timeout=15000
                    )
                    try:
                        page.wait_for_selector(
                            'article[data-testid="result"], a.result__a, h2 a', timeout=15000
                        )
                    except Exception:
                        pass
                    page.wait_for_timeout(2000)
                    top_links = _googler_extract_links(
                        page, _GOOGLER_DDG_RESULT_SELECTORS, skip_domains={'duckduckgo.com'}
                    )

                top_links = top_links[:number_of_results]

                if not top_links:
                    return f"No search results found for '{query}'."

                # Fetch content using Playwright (handles JS-rendered pages)
                for url in top_links:
                    result = _googler_fetch_page_text(page, url)
                    outcomes.append(result)

            except Exception as e:
                return f"Error during Google search: {e}"
            finally:
                browser.close()

    except Exception as e:
        return f"Error launching browser for Google search: {e}"

    output_parts = [f"Google search for '{query}' - {len(outcomes)} results:\n"]
    for i, outcome in enumerate(outcomes, 1):
        output_parts.append(f"=== Result {i} ===")
        output_parts.append(f"URL: {outcome.get('url', 'unknown')}")
        if "error" in outcome:
            output_parts.append(f"Fetch error: {outcome['error']}")
        else:
            output_parts.append(f"HTTP status: {outcome.get('status_code', 'unknown')}")
            output_parts.append(outcome.get("content", "[empty page]"))
        output_parts.append("")

    return "\n".join(output_parts)


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
    if global_state.get_state('tool_execute-netstat_status', 'enabled') == 'enabled': 
        tools.append(execute_netstat)
    if global_state.get_state('tool_unzip-file_status', 'enabled') == 'enabled': 
        tools.append(unzip_file)
    if global_state.get_state('tool_decompile-java_status', 'enabled') == 'enabled': 
        tools.append(decompile_java)
    if global_state.get_state('tool_agent-parametrizer_status', 'enabled') == 'enabled':
        tools.append(agent_parametrizer)
    if global_state.get_state('tool_agent-starter_status', 'enabled') == 'enabled':
        tools.append(agent_starter)
    if global_state.get_state('tool_agent-stopper_status', 'enabled') == 'enabled':
        tools.append(agent_stopper)
    if global_state.get_state('tool_agent-stat-getter_status', 'enabled') == 'enabled':
        tools.append(agent_stat_getter)
    if global_state.get_state('tool_chat-agent-run-list_status', 'enabled') == 'enabled':
        tools.append(chat_agent_run_list)
    if global_state.get_state('tool_chat-agent-run-status_status', 'enabled') == 'enabled':
        tools.append(chat_agent_run_status)
    if global_state.get_state('tool_chat-agent-run-log_status', 'enabled') == 'enabled':
        tools.append(chat_agent_run_log)
    if global_state.get_state('tool_chat-agent-run-stop_status', 'enabled') == 'enabled':
        tools.append(chat_agent_run_stop)
    if global_state.get_state('tool_googler_status', 'enabled') == 'enabled':
        tools.append(googler)
    for spec in WRAPPED_CHAT_AGENT_SPECS:
        if global_state.get_state(_tool_status_key(spec.tool_description), 'enabled') == 'enabled':
            tools.append(_build_wrapped_chat_agent_tool(spec))
    return tools
