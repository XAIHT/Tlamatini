# Tlamatini Author Banner — Angela López Mendoza
"""Offline panel checks for source and real frozen releases.

Run from a verified visible foreground console and leave its output open.
This command does not contact a model, start a browser or modify user flows.
"""

import asyncio
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

from asgiref.testing import ApplicationCommunicator
from channels.routing import URLRouter
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.management.base import BaseCommand, CommandError
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse

from agent.path_guard import get_app_temp_root
from agent.routing import websocket_urlpatterns
from agent.services.prompt_flow_panel import FORMAT, OPERATIONS, VERSION, validate_flow


class PageAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'script' and values.get('src'):
            self.urls.add(values['src'])
        if tag == 'link' and values.get('href'):
            self.urls.add(values['href'])


async def check_websocket():
    """Exercise the actual consumer/adapter through ASGI, without model calls."""
    scope = {'type': 'websocket', 'path': '/ws/prompt-flow-panel/',
             'user': SimpleNamespace(pk=1, is_authenticated=True)}
    communicator = ApplicationCommunicator(URLRouter(websocket_urlpatterns), scope)
    try:
        await communicator.send_input({'type': 'websocket.connect'})
        if (await communicator.receive_output(timeout=5))['type'] != 'websocket.accept':
            raise CommandError('Prompt Flow Panel websocket did not accept an authenticated connection')

        async def event():
            message = await communicator.receive_output(timeout=5)
            return json.loads(message['text'])

        if (await event())['event'] != 'ready':
            raise CommandError('Prompt Flow Panel websocket did not become ready')
        flow = {'format': FORMAT, 'version': VERSION, 'name': 'Offline release check',
                'start': 'comment', 'nodes': [
                    {'id': 'comment', 'type': 'user_commentary', 'config': {'text': 'Release check'}},
                    {'id': 'clean', 'type': 'clean_history'},
                ], 'edges': [{'id': 'edge', 'source': 'comment', 'target': 'clean'}]}
        await communicator.send_input({'type': 'websocket.receive', 'text': json.dumps({
            'action': 'start', 'flow': flow})})
        outputs, completed = [], set()
        for _ in range(16):
            data = await event()
            if data['event'] == 'input':
                await communicator.send_input({'type': 'websocket.receive', 'text': json.dumps({
                    'action': 'reply', 'run_id': data['run_id'], 'request_id': data['request_id'],
                    'value': 'Frozen/source playback: ñ ✓'})})
            elif data['event'] == 'output':
                outputs.append(data['text'])
            elif data['event'] == 'node' and data['status'] == 'completed':
                completed.add(data['node_id'])
            elif data['event'] == 'error':
                raise CommandError(data['message'])
            elif data['event'] == 'state' and data['status'] in {'completed', 'failed', 'stopped'}:
                if (data['status'] != 'completed' or completed != {'comment', 'clean'}
                        or outputs != ['Frozen/source playback: ñ ✓']):
                    raise CommandError('Prompt Flow Panel playback did not complete the expected operations')
                return
        raise CommandError('Prompt Flow Panel playback did not report completion')
    finally:
        await communicator.send_input({'type': 'websocket.disconnect', 'code': 1000})
        await communicator.wait(timeout=5)


class Command(BaseCommand):
    help = 'Check panel templates, static assets, .fpmt example, Temp path and offline ASGI playback.'

    def handle(self, *args, **options):
        frozen = bool(getattr(sys, 'frozen', False))
        temp_root = Path(get_app_temp_root()).resolve()
        app_root = temp_root.parent
        if frozen and app_root != Path(sys.executable).resolve().parent:
            raise CommandError('Frozen Prompt Flow Panel runs must use Temp beside the executable')
        with tempfile.TemporaryDirectory(prefix='prompt-flow-panel-check-', dir=temp_root) as scratch:
            probe = Path(scratch) / 'context.txt'
            probe.write_text('Prompt flow context: ñ ✓', encoding='utf-8')
            if probe.read_text(encoding='utf-8') != 'Prompt flow context: ñ ✓':
                raise CommandError('Prompt Flow Panel UTF-8 context round trip failed')

        if reverse('prompt_flow_panel') != '/agent/prompt_flow_panel/':
            raise CommandError('Prompt Flow Panel route is not registered correctly')
        request = HttpRequest()
        request.user = SimpleNamespace(pk=1, is_authenticated=True)
        html = render_to_string('agent/prompt_flow_panel.html', request=request)
        if 'data-user-id="1"' not in html or 'Operations bar' not in html:
            raise CommandError('Prompt Flow Panel template rendered incompletely')
        page = PageAssets()
        page.feed(html)
        static_prefix = urlsplit(settings.STATIC_URL).path
        for url in sorted(page.urls):
            parsed = urlsplit(url)
            if parsed.netloc or not parsed.path.startswith(static_prefix):
                raise CommandError(f'Panel asset is not locally bundled: {url}')
            name = unquote(parsed.path[len(static_prefix):])
            target = Path(settings.STATIC_ROOT) / name if frozen else finders.find(name)
            if not target or not Path(target).is_file() or not Path(target).stat().st_size:
                raise CommandError(f'Panel asset is missing: {name}')
        if not page.urls:
            raise CommandError('Panel page did not reference any assets')
        sample = app_root / 'docs/examples/prompting-kickoff.fpmt'
        flow = validate_flow(json.loads(sample.read_text(encoding='utf-8-sig')), playable=True)
        if {node['type'] for node in flow['nodes']} != OPERATIONS:
            raise CommandError('Kickoff example does not contain all prompting operations')
        asyncio.run(check_websocket())
        self.stdout.write(self.style.SUCCESS(json.dumps({
            'frozen': frozen, 'assets_resolved': len(page.urls), 'operations_in_example': len(OPERATIONS),
            'template_rendered': True, 'context_roundtrip': True, 'offline_websocket_playback': True,
            'live_model_checked': False,
        })))
