import ast
from datetime import datetime
import difflib
import json
import logging
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
import zipfile
from django.utils import timezone

from .chat_agent_registry import (
    WRAPPED_CHAT_AGENT_SPECS,
)
from .config_loader import get_config_value
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
from .path_guard import validate_tool_path

logger = logging.getLogger(__name__)


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


def launch_in_new_terminal(script_pathfilename, arguments=None, force_foreground=False):
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
    # ``force_foreground`` lets an explicit "run in a visible window" request
    # (execute_file) override the request-scoped console suppression that
    # Multi-Turn turns on by default — otherwise the user asks for a foreground
    # window and silently gets a headless background process.
    if _suppress_visible_console_launches() and not force_foreground:
        return _launch_python_in_background(python_exe, clean_path, arguments)

    quoted_path = f'"{clean_path}"'

    if ' ' in python_exe and not python_exe.startswith('"'):
        python_exe = f'"{python_exe}"'

    if arguments and arguments.strip():
        cmd_args = f'{quoted_path} {arguments}'
    else:
        cmd_args = f'{quoted_path}'

    if sys.platform == 'win32':
        # RELIABLE visible console window. The old approach —
        #   subprocess.Popen('start "Tlamatini Console" cmd /k python ...', shell=True)
        # — was a confirmed *false-OK*: the outer ``cmd /c`` exits 0 instantly so
        # the launch "succeeds", but whether a window actually appears depends on
        # the spawning process having a usable console / window-station. The
        # Multi-Turn executor runs in a Daphne thread-pool worker with no such
        # console, so the window silently never showed (the user's "nothing
        # happened"). ``start`` via shell=True also fires cmd AutoRun (doskey
        # macros) which overwrote the window title, breaking title-based close.
        #
        # CREATE_NEW_CONSOLE + an explicit SW_SHOWNORMAL STARTUPINFO is the
        # documented mechanism that *forces* a brand-new on-screen console for the
        # child regardless of the parent's console state — the same flag the
        # visible wrapped-agent path (`_start_template_agent_process`) already uses
        # successfully. ``title`` stamps the script name into the window title so
        # Windower / Keyboarder can find and close the exact window afterwards.
        script_name = os.path.basename(clean_path)
        full_command = (
            f'cmd.exe /k title Tlamatini Console - {script_name} & {python_exe} {cmd_args}'
        )
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 1  # SW_SHOWNORMAL — guarantee the console is visible
        return subprocess.Popen(
            full_command,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            startupinfo=startupinfo,
            close_fds=True,
        )

    # Non-Windows fallback (the foreground-console concept is Windows-centric;
    # Multi-Turn desktop flows run on Windows). Kept for completeness.
    full_command = f'start "Tlamatini Console" cmd /k {python_exe} {cmd_args}'
    return subprocess.Popen(full_command, shell=True)


def _verify_foreground_window(script_path, timeout=2.5):
    """Best-effort proof that a VISIBLE console window for ``script_path`` actually
    appeared after a foreground launch.

    Returns:
        True  — a visible top-level window whose title contains the script's
                basename was found within ``timeout`` seconds (confirmed on screen);
        False — Windows, but no such window appeared within ``timeout`` (likely
                failed to open — caller must NOT report success);
        None  — could not verify (non-Windows host or enumeration error). Caller
                stays neutral/honest rather than claiming success or failure.

    Fail-open: never raises. This is the antidote to the historical *false-OK*
    where ``execute_file`` told the user a window "opened visibly on your desktop"
    while nothing actually appeared.
    """
    if sys.platform != 'win32':
        return None
    try:
        import time as _t
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        needle = os.path.basename(str(script_path)).lower()
        if not needle:
            return None

        def _scan_once():
            hits = []
            EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

            def _cb(hwnd, _lparam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        if needle in buf.value.lower():
                            hits.append(buf.value)
                return True

            user32.EnumWindows(EnumProc(_cb), 0)
            return hits

        deadline = _t.time() + max(0.2, timeout)
        while _t.time() < deadline:
            if _scan_once():
                return True
            _t.sleep(0.1)
        return False
    except Exception:
        return None


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
        logger.info("[tools._get_template_agents_roots] FROZEN mode, exe_dir = %s, candidates = %s", exe_dir, candidates)
    else:
        module_dir = os.path.realpath(os.path.abspath(os.path.dirname(__file__)))
        candidates.append(os.path.join(module_dir, 'agents'))
        logger.info("[tools._get_template_agents_roots] SOURCE mode, module_dir = %s, candidates = %s", module_dir, candidates)

    roots = []
    for candidate in candidates:
        resolved = os.path.realpath(os.path.abspath(candidate))
        exists = os.path.isdir(resolved)
        logger.info("[tools._get_template_agents_roots] candidate = %s -> resolved = %s, exists? %s", candidate, resolved, exists)
        if exists and resolved not in roots:
            roots.append(resolved)
    logger.info("[tools._get_template_agents_roots] final roots = %s", roots)
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


_CONJUNCTION_ASSIGNMENT_RE = re.compile(
    r'(and|with)\s+[A-Za-z_][A-Za-z0-9_.\-]*\s*=',
    flags=re.IGNORECASE,
)


def _looks_like_conjunction_assignment_start(text, pos):
    """Return True if ``text[pos:]`` begins with ``and KEY=`` or ``with KEY=``.

    Every ``example_request`` string in ``chat_agent_registry.py`` separates
    parameters with the natural-language conjunction ``and`` (occasionally
    ``with``) rather than a comma. LLMs reliably copy that style, so the
    assignment parser must treat those conjunctions as top-level separators
    between ``key=value`` segments. Without this, a call like
    ``filepath='X' and content='Y'`` collapses into a single segment whose
    file_path value silently absorbs the entire tail — which is how the
    file_creator chat agent kept writing literal ``C:\\...\\X' and content='/*...``
    paths to disk.
    """
    return bool(_CONJUNCTION_ASSIGNMENT_RE.match(text, pos))


def _starts_triple_quote(text, index):
    """Return the triple-quote token starting at ``index`` or ``None``.

    Recognizes ``'''`` and ``\"\"\"`` as atomic tokens so that multi-line
    Python scripts containing embedded apostrophes (``node's knapsack``,
    ``don't``) or double quotes don't prematurely close the enclosing
    single-char quote state.
    """
    if index + 2 < len(text):
        triple = text[index:index + 3]
        if triple == '"""' or triple == "'''":
            return triple
    return None


def _is_multiline_quote_open(text, quote_start_index):
    """Return ``True`` if the single-char quote opening at ``quote_start_index``
    is the start of a **multi-line** value.

    Heuristic: the LLM's multi-line quoted payloads always place a newline
    immediately after the opening quote (``script='\\nimport os…``). Single-line
    values like ``smtp.host='smtp.gmail.com'`` or ``command='npm run build'``
    have no newline immediately after the quote. Treating these two cases
    differently lets us keep simple comma-separated multi-assignment parsing
    working while also preserving large multi-line scripts verbatim.
    """
    probe = quote_start_index + 1
    # Skip leading spaces/tabs only — a newline counts as "multi-line start".
    while probe < len(text) and text[probe] in (' ', '\t'):
        probe += 1
    if probe >= len(text):
        return False
    return text[probe] == '\n' or text[probe] == '\r'


def _closes_outer_quote(text, index, quote_char, multiline_mode):
    """Return ``True`` if the quote char at ``index`` is a genuine closer.

    LLM-generated multi-line values embed apostrophes/quotes all over the
    place (``node's knapsack``, ``'w'`` inside ``open(…)``, ``"utf-8"`` in
    kwargs). Treating every occurrence of the same quote char as a closer
    truncates the value at the first internal apostrophe, which is what
    broke pythonxer_010.

    Decision rules:

    * **Multi-line mode** (opening quote followed by a newline): the quote
      is a closer only if it stands at the **end of the entire input**
      (optionally followed by whitespace), OR if it is followed by the
      natural-language conjunction ``and|with KEY=`` that starts a new
      assignment. Internal apostrophes inside the body stay literal. This
      mirrors how the LLM serializes a ``script='<multi-line body>'``
      payload — the closing ``'`` is either the last meaningful char or
      the boundary before the next ``and other_arg='…'`` pair.
    * **Single-line mode**: the quote is a closer if immediately followed
      by EOF, ``,``, ``;``, or the same ``and|with KEY=`` conjunction.
      Internal apostrophes in single-line values are rare; the common case
      is normal key=value splitting.

    The conjunction rule is essential because every ``example_request`` in
    ``chat_agent_registry.py`` teaches the LLM to separate parameters with
    ``and`` rather than a comma (``filepath='X' and content='Y'``). Without
    it, multi-arg calls collapse into a single segment.
    """
    # Check for the end-of-input closer (multi-line mode only) and the
    # conjunction closer (both modes) via the same whitespace probe.
    probe = index + 1
    ws_chars = (' ', '\t', '\r', '\n') if multiline_mode else (' ', '\t')
    while probe < len(text) and text[probe] in ws_chars:
        probe += 1
    if probe >= len(text):
        return True
    if _looks_like_conjunction_assignment_start(text, probe):
        return True

    if multiline_mode:
        # In multi-line mode, any non-EOF / non-conjunction follower means
        # we are still inside the script body — internal ``'`` stays literal.
        return False

    next_char = text[probe]
    if next_char in (',', ';'):
        return True
    return False


def _split_assignment_segments(assignments_text):
    segments = []
    current = []
    quote_char = None          # single-char quote: "'" or '"'
    quote_multiline = False    # True when the opening quote is multi-line
    triple_quote = None        # triple-char quote: '"""' or "'''"
    escape_next = False
    bracket_stack = []

    i = 0
    n = len(assignments_text)
    while i < n:
        char = assignments_text[i]

        if triple_quote:
            # Inside a triple-quoted block: only a matching triple-quote closes it.
            if assignments_text[i:i + 3] == triple_quote:
                current.append(triple_quote)
                i += 3
                triple_quote = None
                continue
            current.append(char)
            i += 1
            continue

        if quote_char:
            current.append(char)
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif (
                char == quote_char
                and _closes_outer_quote(assignments_text, i, quote_char, quote_multiline)
            ):
                quote_char = None
                quote_multiline = False
            i += 1
            continue

        # Prefer triple-quote detection over single-quote detection.
        triple = _starts_triple_quote(assignments_text, i)
        if triple is not None:
            triple_quote = triple
            current.append(triple)
            i += 3
            continue

        if char in ('"', "'"):
            quote_char = char
            quote_multiline = _is_multiline_quote_open(assignments_text, i)
            current.append(char)
            i += 1
            continue

        if char in '[{(':
            bracket_stack.append(char)
            current.append(char)
            i += 1
            continue

        if char in ']})':
            if bracket_stack:
                bracket_stack.pop()
            current.append(char)
            i += 1
            continue

        # ``,`` and ``;`` split top-level assignment segments. The LLM
        # serializes multi-parameter requests either as ``k1='v1', k2='v2'``
        # or as ``k1='v1' and k2='v2'`` (the style used by every
        # ``example_request`` in chat_agent_registry). We split on BOTH —
        # commas and semicolons for the first style, the ``and|with KEY=``
        # conjunction for the second. We deliberately do NOT split on
        # ``\n``: multi-line scripts and YAML blocks contain interior
        # apostrophes (``node's``, ``don't``) and newline-separated lines,
        # and splitting on them truncated pythonxer_010's script to just
        # ``'`` on line 1.
        if char in ',;' and not bracket_stack:
            segment = ''.join(current).strip()
            if segment:
                segments.append(segment)
            current = []
            i += 1
            continue

        # Conjunction split: match ``\s+(and|with)\s+KEY=`` at the current
        # whitespace boundary. We peek only when ``char`` is whitespace so
        # the regex cost is O(1) per char on average rather than O(n) per
        # char (which would make parsing a 50 KB script O(n²)).
        if char in (' ', '\t') and not bracket_stack:
            if _looks_like_conjunction_assignment_start(assignments_text, i + 1):
                segment = ''.join(current).strip()
                if segment:
                    segments.append(segment)
                current = []
                # Skip past the matched `and `/`with ` tokens so the next
                # iteration starts at the identifier. The leading conjunction
                # is already stripped by _parse_requested_assignments, but
                # skipping here keeps the segment boundaries clean.
                conj_match = _CONJUNCTION_ASSIGNMENT_RE.match(assignments_text, i + 1)
                if conj_match:
                    # Advance past ``\s+(and|with)\s+`` but stop at the
                    # identifier char so the next segment starts with ``KEY=``.
                    prefix = re.match(
                        r'(and|with)\s+',
                        assignments_text[i + 1:conj_match.end()],
                        flags=re.IGNORECASE,
                    )
                    if prefix:
                        i = i + 1 + prefix.end()
                        continue
                i += 1
                continue

        current.append(char)
        i += 1

    tail = ''.join(current).strip()
    if tail:
        segments.append(tail)

    return segments


def _split_assignment_segment(segment):
    current = []
    quote_char = None
    quote_multiline = False
    triple_quote = None
    escape_next = False
    bracket_stack = []

    i = 0
    n = len(segment)
    while i < n:
        char = segment[i]

        if triple_quote:
            if segment[i:i + 3] == triple_quote:
                current.append(triple_quote)
                i += 3
                triple_quote = None
                continue
            current.append(char)
            i += 1
            continue

        if quote_char:
            current.append(char)
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif (
                char == quote_char
                and _closes_outer_quote(segment, i, quote_char, quote_multiline)
            ):
                quote_char = None
                quote_multiline = False
            i += 1
            continue

        triple = _starts_triple_quote(segment, i)
        if triple is not None:
            triple_quote = triple
            current.append(triple)
            i += 3
            continue

        if char in ('"', "'"):
            quote_char = char
            quote_multiline = _is_multiline_quote_open(segment, i)
            current.append(char)
            i += 1
            continue

        if char in '[{(':
            bracket_stack.append(char)
            current.append(char)
            i += 1
            continue

        if char in ']})':
            if bracket_stack:
                bracket_stack.pop()
            current.append(char)
            i += 1
            continue

        if char == '=' and not bracket_stack:
            key = ''.join(current).strip()
            value = segment[i + 1:].strip()
            return key, value

        current.append(char)
        i += 1

    return None, None


def _unquote_preserving_backslashes(value_text):
    """Strip a surrounding matching single/double quote pair and decode the
    embedded-quote escape sequences that LLMs reliably produce:

    * ``\\\\`` → literal backslash
    * ``\\<outer-quote>`` → embedded matching quote (Python / C / shell style)
    * a doubled outer quote (SQL / YAML single-quoted style) decodes to a
      single literal quote: ``'I''m'`` → ``I'm`` (and analogously for double
      quotes). LLMs reach for SQL-style doubling whenever they need to
      escape an apostrophe inside ``input_sequence='Hi!, I''m Tlamatini'``
      — without this decode, ``''`` survives all the way into the
      keyboarder, which then types two consecutive apostrophes.

    Every other backslash-prefixed byte (``\\a``, ``\\b``, ``\\t``, ``\\v``,
    ``\\n``, ``\\r``, ``\\x07``, ``\\D``, ``\\A`` …) is kept verbatim. This
    mirrors YAML single-quoted / Python raw-string semantics and supersedes
    ``ast.literal_eval`` for scalar assignments, where Python literal
    semantics would turn ``C:\\angys`` into ``C:\\x07ngys`` and break
    ``chat_agent_file_creator`` / every other Windows-path-bearing wrapped
    agent. Multi-line scripts that actually need ``\\n`` / ``\\t`` expansion
    already flow through the triple-quoted branch, which keeps
    ``ast.literal_eval``.
    """
    outer_quote = value_text[0]
    inner = value_text[1:-1]
    if '\\' not in inner and (outer_quote * 2) not in inner:
        return inner

    out = []
    i = 0
    n = len(inner)
    while i < n:
        char = inner[i]
        if char == '\\' and i + 1 < n:
            nxt = inner[i + 1]
            if nxt == '\\':
                out.append('\\')
                i += 2
                continue
            if nxt == outer_quote:
                out.append(outer_quote)
                i += 2
                continue
        # SQL / YAML-single-quoted convention: a doubled outer quote inside
        # the literal decodes to a single literal quote. ``'I''m'`` → ``I'm``.
        if char == outer_quote and i + 1 < n and inner[i + 1] == outer_quote:
            out.append(outer_quote)
            i += 2
            continue
        out.append(char)
        i += 1
    return ''.join(out)


def _coerce_assignment_value(raw_value):
    value_text = raw_value.strip()
    if value_text == '':
        return ''

    # Python triple-quoted literals take precedence over single-char quotes
    # so that multi-line scripts with embedded apostrophes round-trip cleanly.
    for triple in ('"""', "'''"):
        if (
            value_text.startswith(triple)
            and value_text.endswith(triple)
            and len(value_text) >= 2 * len(triple)
        ):
            try:
                return ast.literal_eval(value_text)
            except Exception:
                return value_text[len(triple):-len(triple)]

    if (
        len(value_text) >= 2
        and value_text[0] == value_text[-1]
        and value_text[0] in ('"', "'")
    ):
        return _unquote_preserving_backslashes(value_text)

    if value_text[0] in '[{(' and value_text[-1] in ']})':
        try:
            return ast.literal_eval(value_text)
        except Exception:
            try:
                return yaml.safe_load(value_text)
            except Exception:
                return value_text

    # Salvage the common LLM failure mode: value begins with a stray quote
    # char (e.g. ``script='\nimport os\n...``) but the closing quote was
    # truncated by a premature match inside a multi-line Python literal.
    # Strip the dangling leading/trailing quote so the consumer (Pythonxer)
    # doesn't receive a script whose line 1 is just ``'`` → SyntaxError.
    if value_text[0] in ('"', "'") and (len(value_text) < 2 or value_text[-1] != value_text[0]):
        trimmed = value_text[1:].lstrip()
        if trimmed:
            return trimmed

    if value_text[-1] in ('"', "'") and (len(value_text) < 2 or value_text[0] != value_text[-1]):
        trimmed = value_text[:-1].rstrip()
        if trimmed:
            return trimmed

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


def _extract_default_from_get_call(node):
    """Return ``(has_default, default_value)`` for a ``config.get(key, default)``.

    ``has_default`` is True when the call site provides any second positional
    argument; ``default_value`` is the literal Python value if it can be
    statically evaluated (``''``, ``[]``, ``False``, ``None``, etc.) — otherwise
    a sentinel ``object()`` is returned and the caller should treat the default
    as opaque-but-present.
    """
    if not isinstance(node, ast.Call):
        return False, None
    if not isinstance(node.func, ast.Attribute) or node.func.attr != 'get':
        return False, None
    if len(node.args) < 2:
        return False, None
    default_node = node.args[1]
    literal = _safe_literal_eval(default_node)
    if literal is None and not isinstance(default_node, ast.Constant):
        # Default expression is non-literal (e.g. another variable). The
        # script clearly tolerates the key being absent, so signal "default
        # present but opaque" via a sentinel.
        return True, _DEFAULT_SENTINEL
    return True, literal


_DEFAULT_SENTINEL = object()


def _safe_literal_eval(node):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


class _ConfigRequirementAnalyzer(ast.NodeVisitor):
    def __init__(self):
        self.variable_to_key = {}
        self.required_keys = set()
        # Keys that are read via ``config.get(key, <default>)`` with an
        # explicit default literal. The caller is signalling that the
        # empty/absent case is supported, so even if a downstream
        # ``if not <var>`` guard exists, the key MUST NOT be flagged as
        # mandatory by the runtime gate. Without this exclusion,
        # ``filetype_exclusions: ""`` (a perfectly valid default) gets
        # rejected and the LLM has to guess strings like ``'[]'`` to
        # satisfy a check that never should have fired.
        self.keys_with_explicit_default = set()

    def visit_Assign(self, node):
        key_name = _extract_string_key_from_get_call(node.value)
        if key_name:
            has_default, _default_value = _extract_default_from_get_call(node.value)
            if has_default:
                self.keys_with_explicit_default.add(key_name)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.variable_to_key[target.id] = key_name
        self.generic_visit(node)

    def visit_AnnAssign(self, node):
        key_name = _extract_string_key_from_get_call(node.value)
        if key_name and isinstance(node.target, ast.Name):
            has_default, _default_value = _extract_default_from_get_call(node.value)
            if has_default:
                self.keys_with_explicit_default.add(key_name)
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
    # Exclude any key that is read with an explicit default at its call site —
    # ``config.get(key, '')`` / ``config.get(key, [])`` etc. signal that the
    # script tolerates the empty case, regardless of any downstream
    # ``if not <var>`` early-exit guard. Without this exclusion the
    # _find_missing_required_config_paths gate (tools.py:1029) rejects any
    # legitimately-empty default and forces the LLM into a retry storm.
    excluded = {_normalize_identifier(key) for key in analyzer.keys_with_explicit_default if key}
    return {
        _normalize_identifier(key)
        for key in analyzer.required_keys
        if key and _normalize_identifier(key) not in excluded
    }


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


# Wrapped chat-agents whose INI_SECTION_<TYPE><<< KV header should be
# promoted to top-level keys on the tool's JSON result. This lets the
# Multi-Turn LLM see e.g. ``output_path`` as a first-class field instead
# of having to grep the log_excerpt for a saved-file path.
_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR: dict = {
    "shoter": ("output_path", "output_dir", "filename"),
    "camcorder": ("output_path", "output_dir", "filename", "media_type", "resolution"),
    "recorder": (
        "output_path", "output_dir", "filename",
        "device_index", "device_name", "sample_rate", "channels",
        "duration_seconds", "gain_percent", "clipped_samples", "format",
    ),
    "audioplayer": (
        "input_path", "input_dir", "filename",
        "device_index", "device_name", "file_sample_rate", "play_sample_rate",
        "channels", "volume_percent", "clipped_samples",
        "file_duration_seconds", "played_seconds", "play_mode", "loops",
        "format", "status",
    ),
    "videoplayer": (
        "input_path", "input_dir", "filename",
        "display_index", "display_geometry", "video_width", "video_height",
        "window_width", "window_height", "fullscreen", "volume_percent",
        "backend", "has_audio", "file_duration_seconds", "played_seconds",
        "play_mode", "loops", "format", "status",
    ),
    "mouser": (
        "movement_type", "end_posx", "end_posy",
        "button_click", "clicked", "located_via",
    ),
}


_INI_SECTION_BLOCK_RE = re.compile(
    r"INI_SECTION_(?P<type>[A-Z0-9_]+)<<<\s*\n(?P<body>.*?)\n>>>END_SECTION_(?P=type)",
    re.DOTALL,
)


def _maybe_promote_section_fields_to_payload(payload, spec) -> None:
    """If the spec is in ``_PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR`` and the
    log_excerpt contains an ``INI_SECTION_<TYPE><<<`` block, lift its KV
    header fields onto ``payload`` (without overwriting existing keys).

    Called from ``_launch_wrapped_chat_agent``. Failure is silent — the
    feature is purely additive and must never block a successful run.
    """
    promote = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR.get(getattr(spec, "template_dir", ""))
    if not promote:
        return
    log_excerpt = payload.get("log_excerpt") or ""
    if not log_excerpt:
        return
    match = _INI_SECTION_BLOCK_RE.search(log_excerpt)
    if not match:
        return
    body = match.group("body")
    # The Parametrizer convention is: KV header lines until the first
    # blank line, then the body becomes ``response_body``.
    header_lines = []
    for raw_line in body.splitlines():
        if raw_line.strip() == "":
            break
        header_lines.append(raw_line)
    for line in header_lines:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key or key not in promote:
            continue
        payload.setdefault(key, value)


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
    logger.info("[tools._find_template_agent_by_dir_name] Looking for dir_name = %s (normalized = %s)", dir_name, normalized)
    discovered = _discover_template_agents()
    logger.info("[tools._find_template_agent_by_dir_name] Discovered %d template agents", len(discovered))
    for agent in discovered:
        if agent['normalized_name'] == normalized:
            logger.info("[tools._find_template_agent_by_dir_name] FOUND: agent_dir = %s", agent['agent_dir'])
            return agent
    logger.warning("[tools._find_template_agent_by_dir_name] NOT FOUND: %s (normalized: %s). Available: %s",
                   dir_name, normalized, [a['dir_name'] for a in discovered])
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


def _seed_global_agent_defaults(template_dir, runtime_config):
    """Inject Tlamatini-global defaults into a wrapped agent's runtime config
    BEFORE the LLM's per-call assignments are applied, so the LLM can still
    override any of them by naming the parameter explicitly.

    Kalier is the "embedded client" for the MCP-Kali-Server: instead of the
    user wiring Claude Desktop's ``client.py --server http://KALI_IP:5000``,
    Tlamatini itself is the client and the Kali box URL lives once in
    ``config.json`` (``kali_server_url`` — editable via Config -> URLs). We
    seed it as the default ``server_url`` here so plain prompts like
    "scan 10.0.0.5 and give me a report" target the configured Kali box
    without the LLM (or the user) ever repeating the URL.
    """
    if not isinstance(runtime_config, dict):
        return runtime_config

    if template_dir == "kalier":
        try:
            configured = get_config_value("kali_server_url", "")
        except Exception as exc:  # pragma: no cover - config read is best-effort
            logger.warning("[tools._seed_global_agent_defaults] could not read kali_server_url: %s", exc)
            configured = ""
        if isinstance(configured, str) and configured.strip():
            runtime_config["server_url"] = configured.strip()
            logger.info(
                "[tools._seed_global_agent_defaults] Kalier server_url seeded from config: %s",
                configured.strip(),
            )

    if template_dir == "stm32er":
        # STM32er is the "embedded client" for the STM32 Template Project MCP:
        # the server path / interpreter / scaffold root / IDE root live once in
        # config.json (Config -> URLs) so firmware prompts never repeat them.
        # Each global maps to the matching config.yaml field; only non-empty
        # configured values are seeded, so an explicit per-call value still wins.
        for cfg_key, field in (
            ("stm32_mcp_server_script", "server_script"),
            ("stm32_mcp_python", "mcp_python"),
            ("stm32_template_dir", "template_dir"),
            ("stm32_ide_root", "ide_root"),
            ("stm32_mcp_repo_url", "mcp_repo_url"),
            ("stm32_mcp_install_dir", "mcp_install_dir"),
        ):
            try:
                configured = get_config_value(cfg_key, "")
            except Exception as exc:  # pragma: no cover - config read is best-effort
                logger.warning("[tools._seed_global_agent_defaults] could not read %s: %s", cfg_key, exc)
                continue
            if isinstance(configured, str) and configured.strip():
                runtime_config[field] = configured.strip()
                logger.info(
                    "[tools._seed_global_agent_defaults] STM32er %s seeded from config %s: %s",
                    field, cfg_key, configured.strip(),
                )

    if template_dir == "esp32er":
        # ESP32er is the "embedded client" for PlatformIO Core: the `pio` executable
        # path and core dir live once in config.json (Config -> URLs) so firmware
        # prompts never repeat them. Only non-empty configured values are seeded, so
        # an explicit per-call value still wins.
        for cfg_key, field in (
            ("pio_executable", "pio_executable"),
            ("pio_core_dir", "pio_core_dir"),
        ):
            try:
                configured = get_config_value(cfg_key, "")
            except Exception as exc:  # pragma: no cover - config read is best-effort
                logger.warning("[tools._seed_global_agent_defaults] could not read %s: %s", cfg_key, exc)
                continue
            if isinstance(configured, str) and configured.strip():
                runtime_config[field] = configured.strip()
                logger.info(
                    "[tools._seed_global_agent_defaults] ESP32er %s seeded from config %s: %s",
                    field, cfg_key, configured.strip(),
                )

    if template_dir == "arduiner":
        # Arduiner is the "embedded client" for the Arduino CLI: the `arduino-cli`
        # binary path and install dir live once in config.json (Config -> URLs) so
        # firmware prompts never repeat them. Only non-empty configured values are
        # seeded, so an explicit per-call value still wins.
        for cfg_key, field in (
            ("arduino_cli_executable", "arduino_cli_executable"),
            ("arduino_cli_install_dir", "arduino_cli_install_dir"),
        ):
            try:
                configured = get_config_value(cfg_key, "")
            except Exception as exc:  # pragma: no cover - config read is best-effort
                logger.warning("[tools._seed_global_agent_defaults] could not read %s: %s", cfg_key, exc)
                continue
            if isinstance(configured, str) and configured.strip():
                runtime_config[field] = configured.strip()
                logger.info(
                    "[tools._seed_global_agent_defaults] Arduiner %s seeded from config %s: %s",
                    field, cfg_key, configured.strip(),
                )

    return runtime_config


# ----------------------------------------------------------------------------
# Pre-launch action preview (visibility into tlamatini.log BEFORE the spawn)
# ----------------------------------------------------------------------------
# Surfaces the exact action Tlamatini is ABOUT to hand off, immediately before
# _launch_wrapped_chat_agent spawns the agent subprocess. This is the user's
# "see what's going to run, in plain text, in the log file" moment -- a single
# atomic INFO entry so concurrent log writes can't interleave it (same rule the
# Parametrizer-section emitters in agents/*/<name>.py follow).
#
# Two shapes per agent, both optional:
#   - body  : (config_field, payload_label) -- a long, free-form payload
#             rendered between `--- begin <label> ---` and `--- end <label> ---`
#             markers (e.g. Executer's shell command, Pythonxer's python code,
#             SSHer's remote command, Apirer's HTTP body, File-Creator's file
#             content). Truncated past _PRE_LAUNCH_PREVIEW_MAX_CHARS.
#   - params: tuple of dotted config paths rendered as `key : value` lines
#             (e.g. SSHer's user/ip, Apirer's method/url, Deleter's file glob).
#
# An agent can declare body, params, or both. Agents whose work is purely
# observational (Crawler, Summarizer, Prompter, File-Interpreter,
# File-Extractor, Image-Interpreter, Shoter, Monitor-*, Recmailer, Sleeper,
# Googler) are deliberately ABSENT from the registry -- there is no
# "about-to-mutate" surface worth pre-announcing for a read-only agent.
_PRE_LAUNCH_PREVIEW_MAX_CHARS = 8000  # cap so a giant inlined payload can't flood the log

# Keys whose values must NOT land in the log under any circumstance. Matched
# case-insensitively against the LEAF key name (so 'smtp.password' and
# 'tlamatini.password' both redact). Belt-and-braces beyond the existing
# `secret_paths` in agent_contracts.py.
_PRE_LAUNCH_PREVIEW_SECRET_LEAF_PATTERNS = (
    'password', 'secret', 'api_hash', 'api_token', 'apikey', 'api_key',
    'access_token', 'bot_token', 'private_key', 'verify_token',
)

_PRE_LAUNCH_PREVIEW_BY_TEMPLATE = {
    # --- direct execution -----------------------------------------------
    'executer':       {'title': 'EXECUTER COMMAND TO RUN',
                       'body': ('script', 'command')},
    'pythonxer':      {'title': 'PYTHONXER SCRIPT TO RUN',
                       'body': ('script', 'python script')},

    # --- remote shell / file transfer -----------------------------------
    'ssher':          {'title': 'SSHER REMOTE COMMAND TO RUN',
                       'body': ('script', 'remote command'),
                       'params': ('user', 'ip')},
    'scper':          {'title': 'SCPER FILE TRANSFER TO PERFORM',
                       'params': ('direction', 'user', 'ip', 'file')},

    # --- containers / infra ---------------------------------------------
    'dockerer':       {'title': 'DOCKERER COMMAND TO RUN',
                       'body': ('command', 'docker command')},
    'kuberneter':     {'title': 'KUBERNETER kubectl COMMAND TO RUN',
                       'params': ('command', 'namespace', 'extra_args', 'custom_command')},

    # --- vcs ------------------------------------------------------------
    'gitter':         {'title': 'GITTER GIT COMMAND TO RUN',
                       'params': ('repo_path', 'command', 'branch', 'commit_message',
                                  'remote', 'custom_command')},

    # --- databases ------------------------------------------------------
    'sqler':          {'title': 'SQLER SCRIPT TO EXECUTE',
                       'body': ('script', 'sql / python script'),
                       'params': ('sql_connection.server', 'sql_connection.database',
                                  'sql_connection.username')},
    'mongoxer':       {'title': 'MONGOXER SCRIPT TO RUN',
                       'body': ('script', 'pymongo script'),
                       'params': ('mongo_connection.connection_string',
                                  'mongo_connection.database',
                                  'mongo_connection.login')},

    # --- ci -------------------------------------------------------------
    'jenkinser':      {'title': 'JENKINSER JOB TO TRIGGER',
                       'params': ('jenkins_url', 'job_name', 'user',
                                  'parameters', 'use_parameters')},

    # --- http -----------------------------------------------------------
    'apirer':         {'title': 'APIRER HTTP REQUEST TO SEND',
                       'body': ('body', 'request body'),
                       'params': ('method', 'url', 'headers',
                                  'expected_status', 'timeout')},

    # --- filesystem -----------------------------------------------------
    'file_creator':   {'title': 'FILE-CREATOR FILE TO WRITE',
                       'body': ('content', 'file content'),
                       'params': ('file_path',)},
    'mover':          {'title': 'MOVER FILE OPERATION TO PERFORM',
                       'params': ('operation', 'source_files', 'destination_folder',
                                  'recursive', 'filetype_exclusions', 'trigger_mode',
                                  'trigger_event_string')},
    'deleter':        {'title': 'DELETER FILE DELETION TO PERFORM',
                       'params': ('files_to_delete', 'recursive',
                                  'filetype_exclusions', 'trigger_mode',
                                  'trigger_event_string')},

    # --- messaging ------------------------------------------------------
    'emailer':        {'title': 'EMAILER MESSAGE TO SEND',
                       'body': ('email.body', 'email body'),
                       'params': ('smtp.host', 'smtp.port', 'smtp.username',
                                  'smtp.use_tls', 'smtp.use_ssl',
                                  'email.from_address', 'email.to_addresses',
                                  'email.cc_addresses', 'email.bcc_addresses',
                                  'email.subject', 'pattern', 'attach_log')},
    'telegramer':     {'title': 'TELEGRAMER MESSAGE TO SEND',
                       'body': ('telegram.message', 'telegram message'),
                       'params': ('telegram.api_id', 'telegram.chat_id')},
    'whatsapper':     {'title': 'WHATSAPPER MONITORING / SEND TO PERFORM',
                       'params': ('textmebot.phone', 'keywords', 'poll_interval',
                                  'llm.base_url', 'llm.model')},
    'notifier':       {'title': 'NOTIFIER DESKTOP ALERT TO RAISE',
                       'params': ('target.mode', 'target.search_strings',
                                  'target.outcome_detail', 'target.sound_enabled',
                                  'target.shutdown_on_match', 'target.poll_interval')},

    # --- desktop ui -----------------------------------------------------
    'keyboarder':     {'title': 'KEYBOARDER KEYSTROKES TO TYPE',
                       'body': ('input_sequence', 'key sequence'),
                       'params': ('stride_delay',)},
    'mouser':         {'title': 'MOUSER POINTER ACTION TO PERFORM',
                       'params': ('movement_type', 'actual_position',
                                  'ini_posx', 'ini_posy', 'end_posx', 'end_posy',
                                  'button_click', 'total_time',
                                  'window_title', 'window_anchor',
                                  'locate_image_path', 'locate_confidence',
                                  'scroll_amount')},
    'windower':       {'title': 'WINDOWER WINDOW OPERATION TO PERFORM',
                       'params': ('action', 'window_title', 'match_mode',
                                  'match_index', 'pos_x', 'pos_y',
                                  'width', 'height', 'arrange_mode',
                                  'activate_after', 'fail_if_absent')},

    # --- offensive security ---------------------------------------------
    'kalier':         {'title': 'KALIER PENTEST ACTION TO RUN',
                       'body': ('command', 'shell command'),
                       'params': ('action', 'server_url', 'target', 'url',
                                  'additional_args', 'scan_type', 'ports',
                                  'mode', 'wordlist', 'data', 'module', 'options',
                                  'service', 'username', 'username_file',
                                  'password_file', 'hash_file', 'format', 'timeout')},

    # --- embedded firmware ----------------------------------------------
    'stm32er':        {'title': 'STM32ER FIRMWARE ACTION TO RUN',
                       'body': ('content', 'source content (write_source)'),
                       'params': ('action', 'device', 'project_dir', 'name',
                                  'dest_parent', 'rel_path', 'system',
                                  'binary', 'port', 'baud', 'data',
                                  'address', 'symbol', 'value', 'variables',
                                  'monitor_seconds', 'server_script',
                                  'mcp_python', 'auto_bootstrap', 'preflight')},
    'esp32er':        {'title': 'ESP32ER FIRMWARE ACTION TO RUN',
                       'body': ('content', 'source content (write_source)'),
                       'params': ('action', 'project_dir', 'board', 'framework',
                                  'environment', 'rel_path', 'boards_query',
                                  'monitor_seconds', 'pio_executable',
                                  'auto_bootstrap', 'preflight')},
    'arduiner':       {'title': 'ARDUINER FIRMWARE ACTION TO RUN',
                       'body': ('content', 'source content (write_source)'),
                       'params': ('action', 'fqbn', 'sketch_path', 'port', 'baud',
                                  'rel_path', 'core_spec', 'lib_spec', 'boards_query',
                                  'additional_urls', 'auto_core_install',
                                  'arduino_cli_executable', 'auto_bootstrap',
                                  'preflight', 'monitor_seconds')},

    # --- browser automation ---------------------------------------------
    'playwrighter':   {'title': 'PLAYWRIGHTER BROWSER SCRIPT TO RUN',
                       'body': ('steps_json', 'steps json (overrides yaml steps)'),
                       'params': ('start_url', 'browser', 'headless', 'timeout_ms',
                                  'nav_wait_until', 'viewport_width', 'viewport_height',
                                  'hold_open_seconds', 'hold_open_ms',
                                  'storage_state_in', 'storage_state_out',
                                  'output_file')},

    # --- ue editor ------------------------------------------------------
    'unrealer':       {'title': 'UNREALER COMMAND TO SEND TO UE5 EDITOR',
                       'body': ('params.code', 'python code (execute_python)'),
                       'params': ('host', 'port', 'command',
                                  'params.name', 'params.actor_name',
                                  'params.blueprint_name', 'params.console_command',
                                  'params.class_name', 'params.path',
                                  'params.source_file', 'params.destination_path',
                                  'connect_timeout', 'read_timeout')},

    # --- post-quantum crypto --------------------------------------------
    'kyber_keygen':   {'title': 'KYBER-KEYGEN KEY PAIR TO GENERATE',
                       'params': ('kyber_variant',)},
    'kyber_cipher':   {'title': 'KYBER-CIPHER ENCRYPTION TO PERFORM',
                       'body': ('buffer', 'plaintext to encrypt'),
                       'params': ('kyber_variant', 'public_key')},
    'kyber_decipher': {'title': 'KYBER-DECIPHER DECRYPTION TO PERFORM',
                       'params': ('kyber_variant', 'private_key',
                                  'encapsulation', 'initialization_vector',
                                  'cipher_text')},

    # --- archives -------------------------------------------------------
    'de_compresser':  {'title': 'DE-COMPRESSER ARCHIVE OPERATION TO PERFORM',
                       'params': ('input', 'output', 'passwordless')},

    # --- decompilation --------------------------------------------------
    'j_decompiler':   {'title': 'J-DECOMPILER DECOMPILATION TO PERFORM',
                       'params': ('directory', 'recursive')},

    # --- user interaction -----------------------------------------------
    # Asker pops a runtime A/B choice dialog. Surfacing the two legends
    # BEFORE the dialog appears lets the user see the question Tlamatini is
    # about to ask (and confirm the wording matches the intent).
    'asker':          {'title': 'ASKER USER CHOICE TO PROMPT',
                       'params': ('legend_path_a', 'legend_path_b')},
}

# Wrapped chat-agents deliberately NOT in _PRE_LAUNCH_PREVIEW_BY_TEMPLATE.
# Read-only / observational / trivial -- no destructive intent worth surfacing
# before the spawn. The contract test in tests.py asserts every wrapped
# chat-agent is in exactly one of these two sets.
_PRE_LAUNCH_PREVIEW_OBSERVATIONAL_TEMPLATES = frozenset({
    'crawler', 'summarizer', 'prompter', 'file_interpreter', 'file_extractor',
    'image_interpreter', 'shoter', 'monitor_log', 'monitor_netstat',
    'recmailer', 'sleeper', 'pser',
})


def _looks_like_secret_key(dotted_path):
    """Substring-match the leaf segment of a dotted key against the secret
    pattern list. Defense-in-depth alongside agent_contracts.secret_paths."""
    if not dotted_path:
        return False
    leaf = dotted_path.rsplit('.', 1)[-1].lower()
    return any(pat in leaf for pat in _PRE_LAUNCH_PREVIEW_SECRET_LEAF_PATTERNS)


def _lookup_dotted_config_value(runtime_config, dotted_path):
    """Walk ``dotted_path`` (e.g. ``'smtp.host'``) through ``runtime_config``.

    Returns the resolved value or the sentinel string ``'<MISSING>'`` if any
    segment is absent. ``'<MISSING>'`` is logged literally so the user sees the
    field was checked but not configured (vs. printed empty)."""
    cursor = runtime_config
    for seg in dotted_path.split('.'):
        if not isinstance(cursor, dict) or seg not in cursor:
            return '<MISSING>'
        cursor = cursor[seg]
    return cursor


def _format_preview_value(value, dotted_path):
    """Render a config value for the preview block.

    - Secret-looking keys -> ``<REDACTED N chars>`` so the user knows the
      value is set without ever exposing it.
    - None / empty string -> ``(unset)``.
    - dict / list / tuple -> compact JSON for one-line readability.
    - everything else -> ``repr()``-free ``str()``.
    """
    if _looks_like_secret_key(dotted_path):
        try:
            length = len(value) if value is not None else 0
        except TypeError:
            length = 0
        if not value:
            return '(unset)'
        return f'<REDACTED {length} chars>'
    if value is None or value == '':
        return '(unset)'
    if value == '<MISSING>':
        return '(missing from config)'
    if isinstance(value, (dict, list, tuple)):
        try:
            return json.dumps(value, default=str, separators=(', ', ': '))
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _render_pre_launch_script_preview(spec, runtime_config, runtime_dir, log_path):
    """Return the atomic multi-line log body for a state-changing chat-agent
    launch. Returns ``None`` for agents not in the preview registry so the
    launcher's call site can ``if body: logger.info(body)`` without branching
    on template_dir."""
    if not spec or not isinstance(runtime_config, dict):
        return None
    entry = _PRE_LAUNCH_PREVIEW_BY_TEMPLATE.get(getattr(spec, 'template_dir', ''))
    if entry is None:
        return None
    title = entry.get('title', f'{spec.display_name} ACTION TO RUN'.upper())
    body_spec = entry.get('body')
    param_paths = entry.get('params', ()) or ()

    out = [
        "=" * 80,
        f"[tools._launch_wrapped_chat_agent] ===== {title} =====",
        f"[tools._launch_wrapped_chat_agent] agent          : {spec.display_name}",
        f"[tools._launch_wrapped_chat_agent] runtime_dir    : {runtime_dir}",
        f"[tools._launch_wrapped_chat_agent] log_path       : {log_path}",
    ]

    # Surface non_blocking / execute_forked_window only when the agent's
    # config actually carries them (avoids noise for agents that don't).
    if 'non_blocking' in runtime_config:
        out.append(f"[tools._launch_wrapped_chat_agent] non_blocking   : "
                   f"{bool(runtime_config.get('non_blocking', False))}")
    if 'execute_forked_window' in runtime_config:
        out.append(f"[tools._launch_wrapped_chat_agent] forked_window  : "
                   f"{bool(runtime_config.get('execute_forked_window', False))}")

    # Key parameters as `key : value` lines (key-redacted; long values inlined).
    for path in param_paths:
        value = _lookup_dotted_config_value(runtime_config, path)
        out.append(
            f"[tools._launch_wrapped_chat_agent] param {path:<24} : "
            f"{_format_preview_value(value, path)}"
        )

    # Optional long body, with --- begin/end --- markers + size/truncation.
    if body_spec:
        body_field, body_label = body_spec
        raw = _lookup_dotted_config_value(runtime_config, body_field)
        if raw == '<MISSING>':
            body_text = ''
        else:
            body_text = raw if isinstance(raw, str) else str(raw)
        line_count = body_text.count('\n') + 1 if body_text else 0
        char_count = len(body_text)
        truncated = False
        if char_count > _PRE_LAUNCH_PREVIEW_MAX_CHARS:
            body_text = (
                body_text[:_PRE_LAUNCH_PREVIEW_MAX_CHARS]
                + f"\n... (truncated; {char_count - _PRE_LAUNCH_PREVIEW_MAX_CHARS} chars omitted)"
            )
            truncated = True
        # Body fields whose KEY name looks secret never have their content
        # printed -- only a size summary.
        if _looks_like_secret_key(body_field):
            out.append(
                f"[tools._launch_wrapped_chat_agent] body {body_field:<25} : "
                f"<REDACTED {char_count} chars>"
            )
        else:
            out.append(
                f"[tools._launch_wrapped_chat_agent] body size      : "
                f"{line_count} line(s), {char_count} char(s)"
                + ("  [TRUNCATED]" if truncated else "")
            )
            out.append(f"[tools._launch_wrapped_chat_agent] --- begin {body_label} ---")
            out.append(body_text if body_text else "(empty)")
            out.append(f"[tools._launch_wrapped_chat_agent] --- end {body_label} ---")

    out.append("=" * 80)
    return "\n".join(out)


def _launch_wrapped_chat_agent(spec, request):
    logger.info("=" * 80)
    logger.info("[tools._launch_wrapped_chat_agent] ===== LAUNCH START =====")
    logger.info("[tools._launch_wrapped_chat_agent] spec.key = %s, spec.template_dir = %s, spec.display_name = %s",
                spec.key, spec.template_dir, spec.display_name)
    logger.info("[tools._launch_wrapped_chat_agent] request = %.300s", str(request))
    logger.info("[tools._launch_wrapped_chat_agent] sys.frozen = %s", getattr(sys, 'frozen', False))
    if getattr(sys, 'frozen', False):
        logger.info("[tools._launch_wrapped_chat_agent] sys.executable = %s", sys.executable)
    else:
        logger.info("[tools._launch_wrapped_chat_agent] __file__ = %s", __file__)

    if not request or not str(request).strip():
        logger.warning("[tools._launch_wrapped_chat_agent] No request provided, aborting")
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"No request was provided to {spec.display_name}.",
        })

    template_agent = _find_template_agent_by_dir_name(spec.template_dir)
    if template_agent is None:
        logger.error("[tools._launch_wrapped_chat_agent] Template agent NOT FOUND for dir_name = %s", spec.template_dir)
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": (
                f"Template agent directory '{spec.template_dir}' was not found. "
                "The wrapped chat agent could not be launched."
            ),
        })

    logger.info("[tools._launch_wrapped_chat_agent] template_agent found: agent_dir = %s", template_agent['agent_dir'])

    try:
        run_id, runtime_dir, log_path = create_isolated_runtime_copy(
            template_agent['agent_dir'],
            spec.template_dir,
        )
        logger.info("[tools._launch_wrapped_chat_agent] Isolated copy created:")
        logger.info("[tools._launch_wrapped_chat_agent]   run_id      = %s", run_id)
        logger.info("[tools._launch_wrapped_chat_agent]   runtime_dir = %s", runtime_dir)
        logger.info("[tools._launch_wrapped_chat_agent]   log_path    = %s", log_path)
    except Exception as exc:
        logger.error("[tools._launch_wrapped_chat_agent] FAILED to create isolated runtime copy: %s", exc, exc_info=True)
        return _tool_output({
            "status": "error",
            "retryable": True,
            "message": f"Failed to create the isolated runtime copy for {spec.display_name}: {exc}",
        })

    runtime_config_path = os.path.join(runtime_dir, "config.yaml")
    logger.info("[tools._launch_wrapped_chat_agent] runtime_config_path = %s, exists? %s", runtime_config_path, os.path.isfile(runtime_config_path))
    try:
        with open(runtime_config_path, "r", encoding="utf-8") as file_handle:
            runtime_config = yaml.safe_load(file_handle) or {}
        logger.info("[tools._launch_wrapped_chat_agent] config.yaml loaded OK, keys: %s", list(runtime_config.keys()) if isinstance(runtime_config, dict) else type(runtime_config).__name__)
    except Exception as exc:
        logger.error("[tools._launch_wrapped_chat_agent] FAILED to load config.yaml: %s", exc)
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"Failed to load runtime config.yaml for {spec.display_name}: {exc}",
            "runtime_dir": runtime_dir,
        })

    if not isinstance(runtime_config, dict):
        logger.error("[tools._launch_wrapped_chat_agent] config.yaml is not a dict, type = %s", type(runtime_config).__name__)
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": "The runtime config.yaml is not a YAML mapping.",
            "runtime_dir": runtime_dir,
        })

    # Seed Tlamatini-global defaults (e.g. Kalier's configured Kali server URL)
    # BEFORE applying the LLM's assignments, so an explicit per-call value wins.
    runtime_config = _seed_global_agent_defaults(spec.template_dir, runtime_config)

    runtime_config, assignment_error, assignment_notes = _apply_requested_assignments_to_config(
        runtime_config,
        str(request),
    )
    if assignment_error:
        logger.error("[tools._launch_wrapped_chat_agent] Config assignment error: %s", assignment_error)
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": assignment_error,
            "runtime_dir": runtime_dir,
        })
    logger.info("[tools._launch_wrapped_chat_agent] Config assignments applied OK, notes: %s", assignment_notes)

    # Pre-flight syntax check for Pythonxer scripts. The agent itself invokes
    # Ruff via ``python -m ruff`` (works in both source and frozen modes
    # because ``requirements.txt`` ships ``ruff`` and the build installs it
    # into PYTHON_HOME), but Ruff only flags style/lint issues and a hard
    # SyntaxError will still propagate as a non-zero exit. Catching syntax
    # errors *before* we spawn the subprocess lets the LLM see a clean,
    # actionable error ("line 1: unterminated string literal") without
    # leaving a failed run directory behind and without burning a Multi-Turn
    # iteration on a guaranteed failure.
    if spec.template_dir == "pythonxer":
        script_value = runtime_config.get("script") if isinstance(runtime_config, dict) else None
        if isinstance(script_value, str) and script_value.strip():
            try:
                ast.parse(script_value)
            except SyntaxError as syn:
                detail = f"line {syn.lineno}: {syn.msg}" if syn.lineno else syn.msg
                first_line = script_value.splitlines()[0] if script_value else ""
                logger.warning(
                    "[tools._launch_wrapped_chat_agent] Pythonxer pre-flight SyntaxError: %s (first line: %r)",
                    detail, first_line,
                )
                return _tool_output({
                    "status": "error",
                    "retryable": True,
                    "message": (
                        f"Pythonxer script has a Python SyntaxError at {detail}. "
                        "The script was not executed. If you intended to write files, "
                        "prefer chat_agent_file_creator (one call per file) over embedding "
                        "large multi-line content in a Python string literal. "
                        "If you must use Pythonxer, send the script as a plain block without "
                        "wrapping it in outer quotes."
                    ),
                    "runtime_dir": runtime_dir,
                    "syntax_error": detail,
                    "first_line": first_line,
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
        logger.info("[tools._launch_wrapped_chat_agent] config.yaml written back to: %s", runtime_config_path)
    except Exception as exc:
        logger.error("[tools._launch_wrapped_chat_agent] FAILED to write config.yaml: %s", exc)
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"Failed to write runtime config.yaml for {spec.display_name}: {exc}",
            "runtime_dir": runtime_dir,
        })

    runtime_script_path = resolve_runtime_script_path(runtime_dir, spec.template_dir)
    logger.info("[tools._launch_wrapped_chat_agent] runtime_script_path = %s", runtime_script_path)
    if not runtime_script_path:
        logger.error("[tools._launch_wrapped_chat_agent] Could not resolve startup script for %s in %s", spec.display_name, runtime_dir)
        return _tool_output({
            "status": "error",
            "retryable": False,
            "message": f"Could not resolve the runtime startup script for {spec.display_name}.",
            "runtime_dir": runtime_dir,
        })

    missing_required = _non_flow_missing_required_paths(runtime_config, runtime_config_path, runtime_script_path)
    if missing_required:
        logger.error("[tools._launch_wrapped_chat_agent] Missing required params: %s",
                     [_format_config_path(item['path']) for item in missing_required])
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

    logger.info("[tools._launch_wrapped_chat_agent] All checks passed, registering run in DB...")
    run = register_chat_agent_run(
        run_id=run_id,
        tool_description=spec.tool_description,
        template_dir=spec.template_dir,
        runtime_dir=runtime_dir,
        log_path=log_path,
        request_text=str(request),
    )

    # Surface the Executer command / Pythonxer code to the central log file
    # BEFORE the subprocess starts, so the user can see in tlamatini.log
    # exactly what's about to run. No-op for any other wrapped chat-agent.
    preview = _render_pre_launch_script_preview(spec, runtime_config, runtime_dir, log_path)
    if preview:
        logger.info("%s", preview)

    logger.info("[tools._launch_wrapped_chat_agent] Starting subprocess...")
    try:
        start_chat_agent_subprocess(run, runtime_script_path)
        logger.info("[tools._launch_wrapped_chat_agent] Subprocess started OK, PID = %s", run.pid)
    except Exception as exc:
        logger.error("[tools._launch_wrapped_chat_agent] FAILED to start subprocess: %s", exc, exc_info=True)
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
    # Surface INI_SECTION_<TYPE><<< KV header fields (e.g. shoter's
    # ``output_path``) as top-level keys on the wrapped tool result, so the
    # LLM does not have to parse the log_excerpt to discover the agent's
    # primary output. Existing keys are NOT overwritten — this is purely
    # additive. Safe for canvas behaviour because the agent itself emits
    # the same block to its own log unchanged.
    _maybe_promote_section_fields_to_payload(payload, spec)

    logger.info("[tools._launch_wrapped_chat_agent] ===== LAUNCH RESULT =====")
    logger.info("[tools._launch_wrapped_chat_agent]   run_id      = %s", run.runId)
    logger.info("[tools._launch_wrapped_chat_agent]   status      = %s", run.status)
    logger.info("[tools._launch_wrapped_chat_agent]   PID         = %s", run.pid)
    logger.info("[tools._launch_wrapped_chat_agent]   runtime_dir = %s", runtime_dir)
    logger.info("[tools._launch_wrapped_chat_agent]   log_path    = %s", log_path)
    logger.info("[tools._launch_wrapped_chat_agent]   runtime_dir exists? %s", os.path.isdir(runtime_dir))
    logger.info("[tools._launch_wrapped_chat_agent]   log_path exists?    %s", os.path.isfile(log_path))

    # List final runtime directory contents
    if os.path.isdir(runtime_dir):
        try:
            final_contents = os.listdir(runtime_dir)
            logger.info("[tools._launch_wrapped_chat_agent]   runtime_dir contents: %s", final_contents)
        except Exception:
            pass

    if run.status == "running":
        payload["message"] = (
            f"{spec.display_name} started in an isolated runtime copy and is still running. "
            "Use chat_agent_run_status, chat_agent_run_log, and chat_agent_run_stop with this run_id."
        )
    elif run.status == "completed":
        payload["message"] = f"{spec.display_name} completed in the isolated runtime copy."
    elif run.status == "failed":
        payload["message"] = (
            f"{spec.display_name} FAILED with a non-zero exit (exit_code={run.exitCode}). "
            "Read 'log_excerpt' for the EXACT cause — e.g. a SyntaxError, the "
            "'RUFF FAILED' banner with [Ruff] findings, or a Python traceback. "
            "REWRITE the script to fix exactly what the log reports (rewrite it IN "
            "FULL if it was truncated), then call this SAME tool again with the "
            "corrected script. Repeat fix -> re-run -> re-check until it passes "
            "(syntax OK + Ruff clean + exit 0). Never re-send the identical failing "
            "input, and do NOT report failure to the user until a corrected retry "
            "has actually been attempted."
        )
        payload["retryable"] = True
    else:
        payload["message"] = f"{spec.display_name} ended with status '{run.status}'."

    logger.info("[tools._launch_wrapped_chat_agent] ===== LAUNCH END =====")
    logger.info("=" * 80)
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
def execute_file(command: str, foreground: bool = False) -> str:
    """
    Execute a Python script with optional arguments — pass the script path (plus any
    arguments) in `command`. Runs in the background by default, or in a visible
    foreground terminal window (set `foreground=True`) when the user explicitly asks for one.

    PREFERRED over chat_agent_keyboarder for running a Python script: pass the script path here —
    NEVER drive Keyboarder to open IDLE / VS Code / a terminal and type/run the script. For creating
    the `.py` file first, use chat_agent_file_creator; for inline Python without a file, use
    chat_agent_pythonxer. Keyboarder and Mouser are reserved for explicit desktop-UI automation
    requests, not for running scripts.

    WINDOW vs BACKGROUND — this choice is the USER'S, never yours:
    - Set `foreground=True` ONLY when the user explicitly asks to run it in a
      VISIBLE / FOREGROUND / FORKED / "in a window I can see" terminal. That opens
      a real console window even in Multi-Turn.
    - If the user says NOTHING about a window (just "run"/"execute" the script),
      leave `foreground=False` — the script runs in the BACKGROUND with no window.
    - Never pop a window the user didn't ask for, and never hide one they did.

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
    - foreground: True only if the user explicitly asked for a visible/foreground/forked
                  window; otherwise False (default) and the script runs in the background.

    Default is background (no window). A window opens only when foreground=True
    (or when Multi-Turn is off, where launches are visible by default).
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
        # ── Parse-gate (fix #2): a .py that does not even compile would crash
        # instantly — and under Multi-Turn it crashes headlessly into DEVNULL,
        # invisibly — yet the launch would still report "success". Catch it here
        # and return the real SyntaxError so the caller fixes the file instead of
        # being told OK. Fails open on unreadable/odd files (never the reason a
        # valid launch is blocked).
        if script_path.lower().endswith(('.py', '.pyw')):
            try:
                with open(script_path, 'r', encoding='utf-8', errors='replace') as _f:
                    _src = _f.read()
                compile(_src, script_path, 'exec')
            except SyntaxError as se:
                loc = f"line {se.lineno}" + (f", col {se.offset}" if se.offset else "")
                detail = f"{type(se).__name__}: {se.msg} ({loc})"
                snippet = (se.text or "").rstrip()
                if snippet:
                    detail += f"\n    {snippet}"
                return (
                    f"Error: '{script_path}' has a syntax error and would crash "
                    f"instead of running, so it was NOT launched. {detail}\n"
                    "The file is most likely truncated or has bad escaping (e.g. a "
                    "literal \\n or \\\" inside the source). Rewrite it IN FULL with "
                    "chat_agent_file_creator / file_creator (do not patch a truncated "
                    "file), then run it again."
                )
            except (ValueError, OSError):
                pass  # NUL byte / unreadable — fail open; let the launch surface it
        # Fix #1: the foreground/background choice is the USER'S. `foreground=True`
        # (the user explicitly asked for a visible window) overrides the Multi-Turn
        # console suppression; otherwise we honor the suppression and run headless.
        # A window therefore opens iff the user asked for one OR suppression is off.
        launch_in_new_terminal(script_path, arguments, force_foreground=foreground)
        window_should_open = foreground or not _suppress_visible_console_launches()
        if window_should_open:
            # Bullet-proof the old false-OK: don't ASSUME the window opened — verify
            # a visible console for this script actually appeared, and report the
            # truth. (verified is True/False/None — see _verify_foreground_window.)
            script_name = os.path.basename(script_path)
            verified = _verify_foreground_window(script_path)
            if verified is True:
                return (
                    f"Launched '{command}' in a foreground terminal window and CONFIRMED a "
                    f"visible window for '{script_name}' is now open on the user's desktop. "
                    "(Confirms the window opened, not that the script ran to completion.)"
                )
            if verified is False:
                return (
                    f"Attempted to launch '{command}' in a foreground terminal window, but a "
                    f"visible window for '{script_name}' did NOT appear within the verification "
                    "window — it most likely failed to open. DO NOT report this as success. "
                    "Likely causes: the script crashed on startup, there is no interactive "
                    "desktop session, or the path is wrong. Investigate before continuing."
                )
            # verified is None -> could not check (non-Windows / enumeration error).
            return (
                f"Launched '{command}' in a foreground terminal window — check that window for "
                "its output. (Confirms the launch was issued; the window could not be "
                "auto-verified on this host.)"
            )
        return (
            f"Launched '{command}' in the background (no window, since no foreground/"
            "forked window was requested). Its console output is not captured here. "
            "(This confirms it was launched, not that the script ran to completion.)"
        )
    except Exception as e:
        return f"Error executing command '{command}': {e}"

@tool
def execute_command(command: str) -> str:
    """
    Execute a shell/system command. Use this for ANY command-line operation: installing packages,
    building software, running scripts, checking system state, git, pip, npm, choco, winget, cmake, etc.

    PREFERRED over chat_agent_keyboarder for running anything from the command line: pass the full
    command here directly — NEVER drive Keyboarder to open a terminal and type the command into it.
    For creating a source file first, use file_creator / chat_agent_file_creator, then execute it
    here. Keyboarder and Mouser are reserved for explicit desktop-UI automation requests, not for
    running commands.

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

    **THIS TOOL ONLY OPENS A VIEWER WINDOW — IT PRODUCES NO ANALYSIS.** It cannot
    interpret, describe, read, OCR, or analyze what is in the image. It exists
    SOLELY to pop the image up on the user's screen.

    **NEVER call this tool to satisfy an interpret / describe / analyze / read /
    "what's in this image" request.** For image *interpretation* use a vision
    tool that returns TEXT without opening any window — `chat_agent_image_interpreter`
    (preferred), `opus_analyze_image` (Claude), or `qwen_analyze_image` (Qwen).
    Only use launch_view_image when the user EXPLICITLY asks to view / show / open /
    display the image (e.g. "View image cat.png", "Show me agent.jpg"). A request to
    describe or analyze an image is NOT a request to open a window showing it.

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

    def _run_playwright_search(search_query, num_results):
        """Run the Playwright search in an isolated thread to avoid async event-loop conflicts."""
        results = []
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
                search_box.fill(str(search_query))
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
                        f"https://duckduckgo.com/?q={str(search_query).replace(' ', '+')}&t=h_&ia=web",
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

                top_links = top_links[:num_results]

                if not top_links:
                    return None  # Signal: no results

                # Fetch content using Playwright (handles JS-rendered pages)
                for url in top_links:
                    result = _googler_fetch_page_text(page, url)
                    results.append(result)
            finally:
                browser.close()

        return results

    # Run Playwright in a dedicated thread to avoid conflicts with
    # Django Channels' async event loop (sync_playwright cannot be called
    # from inside a running asyncio loop).
    from concurrent.futures import ThreadPoolExecutor
    outcomes = []
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run_playwright_search, query, number_of_results)
            result = future.result(timeout=120)
            if result is None:
                return f"No search results found for '{query}'."
            outcomes = result
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


@tool
def window_present(title: str) -> str:
    """Check whether a desktop window matching ``title`` is currently visible.

    Fast (<100 ms) yes/no helper for desktop-UI flows. Uses
    ``pyautogui.getWindowsWithTitle`` (case-insensitive substring match)
    to enumerate top-level windows and returns a JSON string with::

        {"present": true/false, "matches": [{"title": ..., "is_active": true/false}, ...]}

    Use this tool — NOT ``chat_agent_image_interpreter`` — when you only need
    to know "is window X open?". It costs <100 ms vs. the 20–30 s vision-LLM
    round-trip and never blocks the multi-turn budget. Good for: confirming
    Notepad opened after `chat_agent_executer`, confirming the window is
    gone after `alt+f4`, checking that a save dialog is or isn't on screen.

    Reserve `chat_agent_image_interpreter` for genuine vision tasks
    (reading text from a screenshot, describing chart contents, OCR).

    Input:
    - title: substring to match against window titles (e.g. "Notepad",
      "Save As", "Untitled"). Case-insensitive. Empty string returns all
      visible windows.
    """
    try:
        import pyautogui
    except Exception as exc:
        return _tool_output({
            "present": False,
            "matches": [],
            "error": f"pyautogui import failed: {exc}",
        })
    try:
        needle = (title or "").strip().lower()
        windows = pyautogui.getAllWindows()
        matches = []
        active_handle = None
        try:
            active = pyautogui.getActiveWindow()
            active_handle = getattr(active, "_hWnd", None) if active else None
        except Exception:
            active_handle = None
        for window in windows:
            window_title = getattr(window, "title", "") or ""
            if not window_title:
                continue
            if needle and needle not in window_title.lower():
                continue
            handle = getattr(window, "_hWnd", None)
            matches.append({
                "title": window_title,
                "is_active": bool(active_handle is not None and handle == active_handle),
            })
        return _tool_output({
            "present": bool(matches),
            "matches": matches[:32],  # cap to avoid flooding the LLM
            "match_count": len(matches),
            "title_query": title,
        })
    except Exception as exc:
        return _tool_output({
            "present": False,
            "matches": [],
            "error": f"window_present failed: {exc}",
        })


@tool
def chat_agent_run_wait(run_id: str, max_seconds: int = 120, poll_interval_seconds: int = 2) -> str:
    """Block until a chat-agent run finishes, OR ``max_seconds`` elapses.

    Sister tool to ``chat_agent_run_status`` / ``chat_agent_run_log`` /
    ``chat_agent_run_stop``. Use this INSTEAD of looping
    ``chat_agent_run_status`` calls when you launched a long-running wrapped
    chat-agent (image_interpreter, crawler, etc.) and only need the final
    result. One call replaces a 5+ iteration polling loop.

    Returns the same JSON envelope as ``chat_agent_run_status`` once the run
    has finished (or once the timeout fires — in that case the run is still
    running and ``status`` will be ``"running"``; the LLM should call
    ``chat_agent_run_stop`` if it wants to give up, or ``chat_agent_run_wait``
    again with a longer timeout).

    Input:
    - run_id: full run_id or short prefix returned by the launching tool.
    - max_seconds: hard upper bound on the wait (default 120, max 600).
    - poll_interval_seconds: server-side poll cadence (default 2; min 1).
    """
    normalized = _normalize_run_id(run_id)
    run = get_chat_agent_run(normalized)
    if run is None:
        return _tool_output({
            "status": "error",
            "message": f"Wrapped chat-agent run '{normalized}' was not found.",
        })
    try:
        max_s = max(1, min(int(max_seconds), 600))
    except Exception:
        max_s = 120
    try:
        poll_s = max(1, int(poll_interval_seconds))
    except Exception:
        poll_s = 2
    elapsed = 0
    import time as _time
    while elapsed < max_s:
        run.refresh_from_db()
        if str(run.status or "").lower() != "running":
            break
        _time.sleep(poll_s)
        elapsed += poll_s
    payload = serialize_chat_agent_run(run, include_log_excerpt=True)
    payload["waited_seconds"] = elapsed
    return _tool_output(payload)


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
    if global_state.get_state('tool_chat-agent-run-wait_status', 'enabled') == 'enabled':
        tools.append(chat_agent_run_wait)
    if global_state.get_state('tool_window-present_status', 'enabled') == 'enabled':
        tools.append(window_present)
    if global_state.get_state('tool_googler_status', 'enabled') == 'enabled':
        tools.append(googler)
    for spec in WRAPPED_CHAT_AGENT_SPECS:
        if global_state.get_state(_tool_status_key(spec.tool_description), 'enabled') == 'enabled':
            tools.append(_build_wrapped_chat_agent_tool(spec))

    # ── ACPX runtime tools ───────────────────────────────────────────
    # Each tool is independently toggleable through the existing pattern.
    try:
        from .acpx import (
            acp_spawn,
            acp_send,
            acp_send_and_wait,
            acp_kill,
            acp_doctor,
            acp_transcript,
            acp_session_status,
            acp_list_sessions,
            acp_relay,
            list_acp_agents,
            invoke_skill,
            list_skills,
        )
        if global_state.get_state('tool_acpx-spawn_status', 'enabled') == 'enabled':
            tools.append(acp_spawn)
        if global_state.get_state('tool_acpx-send_status', 'enabled') == 'enabled':
            tools.append(acp_send)
        if global_state.get_state('tool_acpx-send-and-wait_status', 'enabled') == 'enabled':
            tools.append(acp_send_and_wait)
        if global_state.get_state('tool_acpx-kill_status', 'enabled') == 'enabled':
            tools.append(acp_kill)
        if global_state.get_state('tool_acpx-doctor_status', 'enabled') == 'enabled':
            tools.append(acp_doctor)
        if global_state.get_state('tool_acpx-transcript_status', 'enabled') == 'enabled':
            tools.append(acp_transcript)
        if global_state.get_state('tool_acpx-session-status_status', 'enabled') == 'enabled':
            tools.append(acp_session_status)
        if global_state.get_state('tool_acpx-list-sessions_status', 'enabled') == 'enabled':
            tools.append(acp_list_sessions)
        if global_state.get_state('tool_acpx-relay_status', 'enabled') == 'enabled':
            tools.append(acp_relay)
        if global_state.get_state('tool_acpx-list-agents_status', 'enabled') == 'enabled':
            tools.append(list_acp_agents)
        if global_state.get_state('tool_acpx-invoke-skill_status', 'enabled') == 'enabled':
            tools.append(invoke_skill)
        if global_state.get_state('tool_acpx-list-skills_status', 'enabled') == 'enabled':
            tools.append(list_skills)
    except Exception:
        # Never let an ACPX import error block tool initialization. Log only.
        logger.exception("[ACPX] failed to register tools")

    return tools
