# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Bounded .flw / .fpmt opening across Explorer, startup, login and browser uploads.

The URL carries an unpredictable, short-lived capability, never a filesystem
path. Opening only transfers validated data to the editor; it cannot start a run.
This module is stdlib-only apart from the pure graph validator, and is safe to
use before Django startup. In particular, an already-running app is reused BEFORE
manage.py performs any startup work on the application's database.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

from .services.prompt_flow_panel import FlowError, MAX_FILE_BYTES, validate_flow

REQUEST_TTL = 15 * 60
MAX_PENDING = 32
TOKEN_RE = re.compile(r"[0-9a-f]{64}\Z")
SERVER_PATH = '/agent/flow_files/status/'
OPEN_PATHS = {'.fpmt': '/agent/prompt_flow_panel/?open=',
              '.flw': '/agent/agentic_control_panel/?open='}
_MUTEX = None


def config_path() -> Path:
    override = os.environ.get('CONFIG_PATH')
    if override:
        return Path(override).resolve()
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent / 'config.json'
    return Path(__file__).resolve().parent / 'config.json'


def instance_id() -> str:
    return hashlib.sha256(os.path.normcase(str(config_path())).encode('utf-8')).hexdigest()


def configured_port() -> int:
    try:
        value = int(json.loads(config_path().read_text(encoding='utf-8-sig')).get('django_port', 8000))
        if 1 <= value <= 65535:
            return value
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return 8000


def request_directory() -> Path:
    # The user's profile supplies the Windows ACL; no shared installation folder
    # or world-readable Temp location stores a user's flow contents.
    profile = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
    return profile / 'Tlamatini' / 'FlowFileOpen' / instance_id()


def validate_agent_flow(value: object) -> dict:
    """Validate the on-disk ACP structure without silently dropping saved data."""
    if not isinstance(value, dict) or 'format' in value:
        raise FlowError('This is not an Agentic Control Panel .flw file.')
    if value.get('schemaVersion', 1) not in (1, 2):
        raise FlowError('This .flw version is not supported by this Tlamatini.')
    nodes, connections = value.get('nodes'), value.get('connections')
    if not isinstance(nodes, list) or not isinstance(connections, list):
        raise FlowError('A .flw file must contain nodes and connections arrays.')
    if len(nodes) > 2000 or len(connections) > 10000:
        raise FlowError('This agent flow contains too many nodes or connections.')
    ids, singletons = set(), set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get('text'), str) or not node['text'].strip():
            raise FlowError('Every agent node must have a nonempty text name.')
        if node.get('configData') is not None and not isinstance(node['configData'], dict):
            raise FlowError('An agent configuration must be an object.')
        for axis in ('left', 'top'):
            if not isinstance(node.get(axis), str) or not re.fullmatch(r'-?\d+(?:\.\d+)?px', node[axis]):
                raise FlowError('Agent positions must be pixel coordinates.')
        identifier = node.get('id')
        if identifier is not None:
            if not isinstance(identifier, str) or not identifier or identifier in ids:
                raise FlowError('Agent node IDs must be unique nonempty strings.')
            ids.add(identifier)
        name = node['text'].lower()
        if name in ('flowcreator', 'flowhypervisor'):
            if name in singletons:
                raise FlowError(f'A flow can contain only one {node["text"]}.')
            singletons.add(name)
    for edge in connections:
        if not isinstance(edge, dict):
            raise FlowError('Every connection must be an object.')
        for key in ('sourceIndex', 'targetIndex'):
            index = edge.get(key)
            if type(index) is not int or not 0 <= index < len(nodes):
                raise FlowError('A connection references a missing agent node.')
        for key in ('inputSlot', 'outputSlot'):
            if type(edge.get(key, 0)) is not int or not 0 <= edge.get(key, 0) <= 1000:
                raise FlowError('A connection slot must be a nonnegative integer.')
    return value


def validate_document(value: object, filename: str) -> dict:
    extension = Path(filename).suffix.lower()
    if extension == '.fpmt':
        return validate_flow(value)
    if extension == '.flw':
        return validate_agent_flow(value)
    raise FlowError('Choose a .flw agent flow or a .fpmt prompting flow.')


def decode_file(data: bytes, filename: str) -> dict:
    if len(data) > MAX_FILE_BYTES:
        raise FlowError('The flow file must be no larger than 5 MiB.')
    try:
        value = json.loads(data.decode('utf-8-sig'), parse_constant=_invalid_number, parse_float=_finite_float)
        return validate_document(value, filename)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise FlowError(f'Could not open {Path(filename).name}: {exc}') from exc


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        _invalid_number(value)
    return result


def _invalid_number(value):
    raise FlowError(f'Invalid JSON number: {value}.')


def opening_path(filename: str, token: str) -> str:
    return OPEN_PATHS[Path(filename).suffix.lower()] + token


def create_request(data: bytes, filename: str, *, user_id=None) -> str:
    flow = decode_file(data, filename)
    directory = request_directory()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = time.time()
    pending = 0
    for path in directory.glob('*.json'):
        if not TOKEN_RE.fullmatch(path.stem):
            continue
        try:
            if now - path.stat().st_mtime > REQUEST_TTL:
                path.unlink()
            else:
                pending += 1
        except FileNotFoundError:
            pass
    if pending >= MAX_PENDING:
        raise FlowError('Too many unopened flows. Open an existing request or try again in 15 minutes.')
    token = secrets.token_hex(32)
    record = {'created': now, 'filename': Path(filename).name, 'flow': flow,
              'owner': None if user_id is None else str(user_id)}
    temporary = directory / (token + '.tmp')
    try:
        with temporary.open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, allow_nan=False)
        temporary.replace(directory / (token + '.json'))
    finally:
        temporary.unlink(missing_ok=True)
    return token


def consume_request(token: str, user_id, extension: str) -> dict:
    if not TOKEN_RE.fullmatch(token):
        raise FlowError('This flow-file opening link is invalid. Open the flow file again.')
    path = request_directory() / (token + '.json')
    try:
        if time.time() - path.stat().st_mtime > REQUEST_TTL:
            path.unlink(missing_ok=True)
            raise FlowError('This flow-file opening link expired. Open the flow file again.')
        with path.open('rb') as handle:
            data = handle.read(MAX_FILE_BYTES * 3 + 1)
        if len(data) > MAX_FILE_BYTES * 3:
            raise FlowError('The opening request is too large.')
        record = json.loads(data)
        if record.get('owner') not in (None, str(user_id)):
            raise FlowError('This prompt flow was opened by another signed-in user.')
        if Path(record['filename']).suffix.lower() != extension:
            raise FlowError('This file belongs in the other flow editor. Open the original file again.')
        flow = validate_document(record['flow'], record['filename'])
        # Atomic claim: two tabs cannot both consume the same capability.
        claimed = path.with_suffix('.claimed-' + secrets.token_hex(8))
        path.rename(claimed)
        claimed.unlink()
        return {'flow': flow, 'filename': record['filename']}
    except FileNotFoundError as exc:
        raise FlowError('This flow-file opening link has already been used or is unavailable. Open the flow file again.') from exc
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, FlowError):
            raise
        raise FlowError('The flow-file opening request is damaged. Open the flow file again.') from exc


def status_payload() -> dict:
    return {'application': 'Tlamatini', 'flow_file_open': 1, 'instance': instance_id()}


def running_instance(port: int) -> str:
    """Return ready, absent or occupied; never send a file to an unrelated listener."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}{SERVER_PATH}', timeout=2) as response:
            data = response.read(4097)
        if len(data) <= 4096 and json.loads(data) == status_payload():
            return 'ready'
        return 'occupied'
    except (ValueError, urllib.error.HTTPError):
        return 'occupied'
    except (urllib.error.URLError, TimeoutError, OSError):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=.5):
                return 'occupied'
        except OSError:
            return 'absent'


def acquire_launch_mutex() -> bool:
    """Hold a Windows named mutex until process exit to serialize cold launches."""
    global _MUTEX
    if os.name != 'nt':
        return True
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, 'Local\\Tlamatini.FlowFile.' + instance_id())
    if not handle:
        raise OSError(ctypes.get_last_error(), 'Could not coordinate prompt-flow startup')
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        return False
    _MUTEX = handle
    return True


def wait_ready(port: int, timeout: float = 120) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if running_instance(port) == 'ready':
            return True
        time.sleep(.5)
    return False


def schedule_open(url: str, port: int) -> None:
    def open_when_ready():
        if wait_ready(port):
            webbrowser.open(url, new=2)
        else:
            print('--- [FLOW] Startup did not become ready. Open the flow file again after Tlamatini starts.', flush=True)
    threading.Thread(target=open_when_ready, name='flow-file-browser', daemon=True).start()


def prepare_launch(filename: str) -> tuple[str, int, bool]:
    """Validate/snapshot a local file and return (URL, port, already_opened).

    Existing-instance return happens before Django, migrations and other startup
    effects. A source-mode file invocation is supported as well as the frozen exe.
    """
    path = Path(filename).expanduser().resolve()
    if not path.is_file():
        raise FlowError('The flow file does not exist or is not a regular file.')
    with path.open('rb') as handle:
        data = handle.read(MAX_FILE_BYTES + 1)
    token = create_request(data, path.name)
    port = configured_port()
    url = f'http://localhost:{port}{opening_path(path.name, token)}'
    try:
        state = running_instance(port)
        if state == 'ready':
            if not webbrowser.open(url, new=2):
                raise FlowError('Windows could not open a browser. Choose a default web browser and try again.')
            return url, port, True
        first = acquire_launch_mutex()
        if not first:
            print('--- [FLOW] Waiting for Tlamatini to finish starting...', flush=True)
            if wait_ready(port):
                if not webbrowser.open(url, new=2):
                    raise FlowError('Windows could not open a browser. Choose a default web browser and try again.')
                return url, port, True
            raise FlowError('Tlamatini did not finish starting. Check its main console, then open the file again.')
        if state == 'occupied':
            raise FlowError(f'Port {port} is already used by another application or an older Tlamatini. Close it or configure a different Tlamatini web port.')
        return url, port, False
    except Exception:
        (request_directory() / (token + '.json')).unlink(missing_ok=True)
        raise


def launch_error(error: Exception) -> None:
    message = f'Could not open the flow file.\n\n{error}'
    print('--- [FLOW] ' + message, flush=True)
    if os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, 'Tlamatini — Open flow file', 0x10)
