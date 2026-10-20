# Tlamatini Author Banner — Angela López Mendoza
"""Offline Terminals / Terminater checks for source and real frozen releases.

Run from a verified visible foreground console and leave its output open.  It opens REAL PowerShell
and cmd.exe terminals through the Windows pseudo console, types into them and reads the result, runs
the shipped pool agent under the carried Python and talks to the hub through the browser's WebSocket
consumer.  It contacts no model, starts no browser and changes no user file.

Why it exists: the Terminater engine is a LOOSE file in the agents tree that the web process loads BY PATH,
and the dock's scripts come from the collected static files.  Neither is visible to the import graph, so
archive membership proves nothing -- only running it in the frozen layout does (the same reason
``check_agent_runtimes`` and ``check_prompt_flow_panel`` exist).
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand, CommandError
from django.template.loader import get_template
from django.urls import reverse

from agent import terminal_hub
from agent.path_guard import get_app_temp_root
from agent.routing import websocket_urlpatterns
from agent.services.agent_paths import get_agents_root

AGENT_FILES = ('terminater.py', 'terminater_engine.py', 'terminater_conpty.py', 'terminater_text.py', 'config.yaml')
STATIC_ASSETS = (
    'agent/js/terminater_dock.js', 'agent/css/terminater_dock.css',
    'agent/vendor/frontend/xterm/lib/xterm.js', 'agent/vendor/frontend/xterm/css/xterm.css',
    'agent/vendor/frontend/xterm-addon-fit/lib/addon-fit.js',
    'agent/vendor/frontend/xterm-addon-web-links/lib/addon-web-links.js',
)
PAGES = ('agent_page.html', 'agentic_control_panel.html', 'prompt_flow_panel.html')
SHELL_WAIT_SECONDS = 90          # a first PowerShell start can be slow under an antivirus scan


def fail(message):
    raise CommandError('Terminater check failed: ' + message)


def asset_path(relative, frozen):
    target = Path(settings.STATIC_ROOT) / relative if frozen else finders.find(relative)
    return Path(target) if target else None


async def websocket_round_trip(port):
    """Connect as a browser does (same origin), expect hello, ask for a terminal, expect opened."""
    from asgiref.testing import ApplicationCommunicator
    from channels.routing import URLRouter

    scope = {'type': 'websocket', 'path': '/ws/terminals/', 'server': ('127.0.0.1', port),
             'headers': [(b'host', f'127.0.0.1:{port}'.encode()), (b'origin', f'http://127.0.0.1:{port}'.encode())],
             'user': SimpleNamespace(pk=990, is_authenticated=True)}
    communicator = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
    frames = []

    async def until(kind, seconds):
        deadline = asyncio.get_event_loop().time() + seconds
        while kind not in frames and asyncio.get_event_loop().time() < deadline:
            message = await communicator.receive_output(timeout=seconds)
            if message.get('type') == 'websocket.send':
                frames.append(json.loads(message['text']).get('t'))
            elif message.get('type') == 'websocket.close':
                fail(f'the terminal socket was closed by the server (code {message.get("code")})')

    try:
        await communicator.send_input({'type': 'websocket.connect'})
        first = await communicator.receive_output(timeout=30)
        if first.get('type') != 'websocket.accept':
            fail(f'an authenticated same-origin socket was refused: {first}')
        await until('hello', 30)
        await communicator.send_input({'type': 'websocket.receive', 'text': json.dumps({'t': 'open', 'kind': 'powershell'})})
        await until('opened', SHELL_WAIT_SECONDS)
        return frames
    finally:
        try:
            await communicator.send_input({'type': 'websocket.disconnect', 'code': 1000})
            await communicator.wait(timeout=10)
        except Exception:  # noqa: BLE001 - the verdict does not depend on a tidy goodbye
            pass


class Command(BaseCommand):
    help = 'Real-terminal checks for the Terminals area and the Terminater agent (source and frozen).'

    def handle(self, *args, **options):
        frozen = bool(getattr(sys, 'frozen', False))
        if os.name != 'nt':
            self.stdout.write('Terminater terminals use the Windows pseudo console; nothing to check on this system.')
            return
        if not terminal_hub.terminals_enabled():
            fail('the configuration disables the terminals (terminater_enabled)')

        # 1) the agent template ships complete, and the engine loads BY PATH from it
        folder = Path(terminal_hub.engine_dir())
        for name in AGENT_FILES:
            if not (folder / name).is_file():
                fail(f'agents/terminater/{name} is not shipped (looked in {folder})')
        if frozen and Path(get_agents_root()).parent != Path(sys.executable).resolve().parent:
            fail(f'the agents tree does not sit next to the executable: {get_agents_root()}')
        engine = terminal_hub.load_engine()
        if Path(engine.__file__).resolve().parent != folder.resolve():
            fail(f'the engine was not loaded from the shipped agents tree: {engine.__file__}')
        for sibling in ('terminater_conpty', 'terminater_text'):
            if sibling not in sys.modules:
                fail(f'the engine did not import its sibling module {sibling}')

        # 2) the page assets and templates the browser needs
        for relative in STATIC_ASSETS:
            target = asset_path(relative, frozen)
            if not target or not target.is_file() or not target.stat().st_size:
                fail(f'static asset is missing: {relative}')
        for page in PAGES:
            source = get_template('agent/' + page).template.source
            if 'terminater_dock.js' not in source or 'data-tlm-terminals-host' not in source:
                fail(f'{page} does not load the dock or name its host')

        # 3) routes
        if not reverse('terminater_api').endswith('/terminater/api/') or not reverse('terminater_state').endswith('/terminater/state/'):
            fail('the loopback API routes do not resolve')
        if not any('ws/terminals' in str(pattern.pattern) for pattern in websocket_urlpatterns):
            fail('the terminals WebSocket route is not registered')

        # 4) REAL shells, typed into, in this (possibly frozen) process
        hub = engine.TerminalHub(max_terminals=3, hang_seconds=30)
        outcomes = {}
        try:
            for kind, command, marker in (('powershell', 'Write-Output terminater-gate-ps', 'terminater-gate-ps'),
                                          ('cmd', 'echo terminater-gate-cmd', 'terminater-gate-cmd')):
                result = hub.call('run', {'user': 'release-check', 'kind': kind, 'text': command, 'typing_wpm': 160,
                                          'wait_seconds': SHELL_WAIT_SECONDS, 'load_profile': False, 'show': False})
                if not result.get('ok') or result.get('status') != 'completed' or marker not in str(result.get('output')):
                    fail(f'a real {kind} did not run the typed command: ' + json.dumps({k: result.get(k) for k in ('status', 'code', 'message')}))
                outcomes[kind] = result.get('status')
        finally:
            hub.shutdown()

        # 5) the shipped POOL AGENT under the carried Python, with its own terminals
        outcomes['pool_agent'] = self.check_pool_agent(frozen, folder)

        # 6) the browser's WebSocket consumer over the process hub
        try:
            frames = asyncio.run(websocket_round_trip(8000))
        finally:
            terminal_hub.shutdown()          # kills every shell and removes the rendezvous file
        if 'hello' not in frames or 'opened' not in frames:
            fail(f'the terminals socket did not greet and open a terminal: {frames}')

        time.sleep(1.0)
        self.stdout.write(self.style.SUCCESS(json.dumps({
            'frozen': frozen, 'engine_loaded_from': str(folder), 'assets_resolved': len(STATIC_ASSETS),
            'pages_with_dock': len(PAGES), 'powershell': outcomes['powershell'], 'cmd': outcomes['cmd'],
            'pool_agent': outcomes['pool_agent'], 'websocket_frames': frames,
        })))

    def check_pool_agent(self, frozen, folder):
        """Run the shipped agent exactly as a pool does: its own directory, the carried interpreter."""
        python = Path(sys.executable).resolve().parent / 'python' / 'python.exe' if frozen else Path(sys.executable)
        if not python.is_file():
            fail(f'the carried Python is missing: {python}')
        pool = Path(get_app_temp_root()) / 'terminater-gate' / 'terminater_1'
        shutil.rmtree(pool.parent, ignore_errors=True)
        try:
            shutil.copytree(folder, pool, ignore=shutil.ignore_patterns('__pycache__'))
            import yaml
            config = pool / 'config.yaml'
            data = yaml.safe_load(config.read_text(encoding='utf-8')) or {}
            data.update(mode='standalone', action='run', kind='powershell', text='Write-Output terminater-gate-pool',
                        typing_wpm=160, wait_seconds=SHELL_WAIT_SECONDS, load_profile=False, target_agents=[], source_agents=[])
            config.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
            env = os.environ.copy()
            env.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8')
            for name in (terminal_hub.ENV_TOKEN, terminal_hub.ENV_URL):
                env.pop(name, None)               # standalone means standalone: never reach a real hub
            run = subprocess.run([str(python), '-u', 'terminater.py'], cwd=pool, env=env, capture_output=True,
                                 text=True, encoding='utf-8', errors='replace', timeout=SHELL_WAIT_SECONDS + 60)
            log_path = pool / 'terminater_1.log'
            log = log_path.read_text(encoding='utf-8', errors='replace') if log_path.is_file() else ''
            if run.returncode != 0 or 'INI_SECTION_TERMINATER' not in log:
                fail('the pool agent did not finish cleanly: ' + (log or run.stdout + run.stderr)[-600:])
            if 'status: completed' not in log or 'terminater-gate-pool' not in log:
                fail('the pool agent report is not "completed" with the typed output: ' + log[-600:])
            return 'completed'
        finally:
            shutil.rmtree(pool.parent, ignore_errors=True)
