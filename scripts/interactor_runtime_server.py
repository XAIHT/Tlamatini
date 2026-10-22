# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Test driver loaded by manage.py shell (source or the actual frozen EXE).

Not a product endpoint. Commands travel through files in a disposable evidence
directory; the real tool, hub, authenticated WebSocket and save views execute
unchanged. Launch only from interactor_runtime_visible.py in a verified console.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time
import traceback


def main():
    output = Path(os.environ['TLAMATINI_INTERACTOR_TEST_DIR']).resolve()
    output.mkdir(parents=True, exist_ok=True)
    from django.conf import settings
    from django.db import connections
    connections.close_all()
    settings.DATABASES['default']['NAME'] = output / 'isolated.sqlite3'
    connections['default'].settings_dict['NAME'] = settings.DATABASES['default']['NAME']
    from django.core.management import call_command
    call_command('migrate', interactive=False, verbosity=0)
    from django.contrib.auth import get_user_model
    password = secrets.token_urlsafe(24)
    user, _ = get_user_model().objects.get_or_create(username='interactor-modes-review')
    user.set_password(password)
    user.save()
    (output / 'credentials.json').write_text(json.dumps({'username': user.username, 'password': password}), encoding='utf-8')
    from agent.interactor.context import Request, current
    from agent.interactor.hub import hub
    from agent.interactor.tool import perform
    from agent.cancellation import begin_llm_run, reset_for_tests
    from agent.path_guard import get_app_temp_root
    import agent.interactor.tool as tool
    proof = {'frozen': bool(getattr(sys, 'frozen', False)), 'executable': sys.executable,
             'executable_sha256': hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
             'tool_module': tool.__file__, 'tool_loader': type(tool.__loader__).__name__,
             'app_temp': get_app_temp_root(), 'debug': settings.DEBUG}
    (output / 'runtime.json').write_text(json.dumps(proof, indent=2), encoding='utf-8')
    print('RUNTIME PROOF:', json.dumps(proof), flush=True)

    def commands():
        request = None
        while not (output / 'stop-server').exists():
            pending = output / 'command.json'
            if not pending.exists():
                time.sleep(.03)
                continue
            frame = json.loads(pending.read_text(encoding='utf-8'))
            pending.unlink()
            try:
                if frame['method'] == 'turn':
                    client = frame['client']
                    owner = hub.clients[client].owner
                    reset_for_tests(int(owner[0]))
                    request = Request(owner, client, int(owner[0]), begin_llm_run(int(owner[0])))
                    value = {'ok': True}
                else:
                    token = current.set(request)
                    try:
                        value = json.loads(perform(**frame['args']))
                    finally:
                        current.reset(token)
                result = {'value': value}
            except Exception:
                result = {'error': traceback.format_exc()}
            staged = output / 'reply.tmp'
            staged.write_text(json.dumps(result), encoding='utf-8')
            staged.replace(output / 'reply.json')
            print('EDITOR TEST ACTION:', frame.get('args', {}).get('action', frame['method']),
                  result.get('value', {}).get('status', 'ready'), flush=True)

    threading.Thread(target=commands, name='interactor-visible-test-driver', daemon=True).start()
    from tlamatini.asgi import application
    from daphne.server import Server
    if settings.DEBUG:
        from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler
        application = ASGIStaticFilesHandler(application)
    server = Server(application, endpoints=[f"tcp:port={os.environ['TLAMATINI_INTERACTOR_TEST_PORT']}:interface=127.0.0.1"],
                    signal_handlers=False)

    def watch_stop():
        while not (output / 'stop-server').exists():
            time.sleep(.1)
        from twisted.internet import reactor
        reactor.callFromThread(reactor.stop)
    threading.Thread(target=watch_stop, daemon=True).start()
    server.run()


main()
