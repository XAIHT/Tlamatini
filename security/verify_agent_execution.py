"""Check real non-admin execution without running model jobs or applying policy.

Run in a confirmed visible persistent console. Each discovered Python writes and
reads unique scratch files in Temp, Desktop and Documents; it runs CMD/PowerShell
and transfers bytes over a loopback socket. Only its own temporary files are
removed. Results do not certify all agents, internet access, or external tools.

Created by Angela López Mendoza · @angelahack1 — Tlamatini Author Banner.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import winreg


def user_folder(name, fallback):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders') as key:
        try:
            value = winreg.QueryValueEx(key, name)[0]
        except FileNotFoundError:
            return Path.home() / fallback
        return Path(os.path.expandvars(value))


def check_interpreter():
    results = []

    def check(name, action):
        print(f'RUN {name} [{sys.executable}]', flush=True)
        try:
            action()
            result = {'name': name, 'passed': True}
        except Exception as exc:
            result = {'name': name, 'passed': False, 'error': str(exc)}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    def write_probe(folder):
        if not folder.is_dir():
            raise RuntimeError(f'Folder does not exist: {folder}')
        with tempfile.TemporaryDirectory(prefix='Tlamatini-execution-check-', dir=folder) as scratch:
            target = Path(scratch) / 'created.txt'
            content = 'Tlamatini: ñ, quoted "text", command execution verified.\n'
            with target.open('x', encoding='utf-8') as stream:
                stream.write(content)
            if target.read_text(encoding='utf-8') != content:
                raise RuntimeError('Created file contents differ')

    def loopback():
        with socket.socket() as listener:
            listener.settimeout(5)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            with socket.create_connection(listener.getsockname(), timeout=5) as sender:
                receiver, _ = listener.accept()
                with receiver:
                    receiver.settimeout(5)
                    sender.sendall(b'Tlamatini')
                    sender.shutdown(socket.SHUT_WR)
                    data = bytearray()
                    while chunk := receiver.recv(64):
                        data.extend(chunk)
                    if data != b'Tlamatini':
                        raise RuntimeError('Loopback bytes differ')

    check('Temp file create/read/remove', lambda: write_probe(Path(tempfile.gettempdir())))
    check('Desktop file create/read/remove', lambda: write_probe(user_folder('Desktop', 'Desktop')))
    check('Documents file create/read/remove', lambda: write_probe(user_folder('Personal', 'Documents')))
    check('CMD command execution', lambda: subprocess.run(
        [os.environ['COMSPEC'], '/d', '/c', 'echo Tlamatini CMD execution OK'], check=True, timeout=20))
    check('PowerShell command execution', lambda: subprocess.run(
        [str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'),
         '-NoProfile', '-Command', "Write-Host 'Tlamatini PowerShell execution OK'; exit 0"],
        check=True, timeout=20))
    check('Loopback network transfer', loopback)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visible-console-verified', action='store_true')
    parser.add_argument('--python', action='append', default=[], help='Additional interpreter to test')
    parser.add_argument('--child-result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not args.visible_console_verified:
        if input('Is this a visible, forked foreground console that will stay open? Type YES: ').strip() != 'YES':
            raise SystemExit('Visibility is unconfirmed; nothing was tested.')
    if args.child_result:
        results = check_interpreter()
        args.child_result.write_text(json.dumps(results, indent=2), encoding='utf-8')
        return int(any(not r['passed'] for r in results))

    root = Path(__file__).resolve().parent.parent
    pythons = [Path(sys.executable), root / 'python/python.exe']
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\XAIHT\Tlamatini') as key:
            pythons.append(Path(winreg.QueryValueEx(key, 'InstallLocation')[0]) / 'python/python.exe')
    except FileNotFoundError:
        pass
    pythons.extend(Path(p) for p in args.python)
    unique = {str(p.resolve()).casefold(): p.resolve() for p in pythons if p.is_file()}
    missing = [p for p in args.python if not Path(p).is_file()]
    if missing:
        raise SystemExit(f'Requested Python not found: {missing}')
    evidence = root / 'security/security_logs' / ('execution-' + time.strftime('%Y%m%d-%H%M%S'))
    evidence.mkdir(parents=True, exist_ok=False)
    failed = False
    for index, executable in enumerate(unique.values()):
        output = evidence / f'python-{index}.json'
        print(f'CHECK INTERPRETER: {executable}', flush=True)
        try:
            process = subprocess.run([str(executable), '-u', str(Path(__file__).resolve()),
                                      '--visible-console-verified', '--child-result', str(output)], timeout=90)
            failed = failed or process.returncode != 0 or not output.is_file()
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f'FAILED to run {executable}: {exc}', flush=True)
            failed = True
    print(f'EXECUTION CHECK: {"FAIL" if failed else "PASS"}; evidence: {evidence}', flush=True)
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
