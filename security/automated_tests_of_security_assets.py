"""Non-admin regression checks, run only in a confirmed visible console.

Open a new foreground PowerShell with -NoExit, confirm that you can see it,
then run this script there. Child checks inherit that console; it stays open.
No Windows security policy is applied and no live defender sweep is run.

Created by Angela López Mendoza · @angelahack1 — Tlamatini Author Banner.
"""
from __future__ import annotations

import argparse
import ast
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from sync_enable_launcher import launcher_text

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT_DIR = SCRIPT_DIR.parent


def confirm_visible(confirmed=False):
    if os.name != 'nt':
        raise RuntimeError('These checks require Windows and a visible foreground console.')
    if not confirmed:
        answer = input('Is this a visible, forked foreground console that will stay open? Type YES: ')
        if answer.strip() != 'YES':
            raise RuntimeError('Visibility is unconfirmed; no checks were started.')


def take_shot(work):
    """Capture the full desktop through Shoter; never use a screenshot fallback."""
    candidates = (ROOT_DIR / 'agents/shoter', ROOT_DIR / 'Tlamatini/agent/agents/shoter')
    source = next((p for p in candidates if (p / 'shoter.py').is_file()), None)
    if source is None:
        raise RuntimeError('Shoter is unavailable; desktop evidence was not captured.')
    stage = work / 'shoter'
    stage.mkdir()
    shutil.copy2(source / 'shoter.py', stage / 'shoter.py')
    # JSON is also YAML; quoting paths this way preserves spaces and backslashes.
    (stage / 'config.yaml').write_text(json.dumps({
        'output_dir': str(work), 'all_screens': True,
        'filename': 'visible-console.png', 'target_agents': [],
    }), encoding='utf-8')
    subprocess.run([sys.executable, '-u', str(stage / 'shoter.py')], cwd=stage,
                   check=True, timeout=60, stderr=subprocess.STDOUT)
    shot = work / 'visible-console.png'
    if not shot.is_file() or not shot.stat().st_size:
        raise RuntimeError('Shoter did not produce a nonempty screenshot.')
    return str(shot)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visible-console-verified', action='store_true',
                        help='Use only after a human confirms this persistent foreground console.')
    args = parser.parse_args()
    confirm_visible(args.visible_console_verified)
    work = SCRIPT_DIR / 'security_logs/asset_tests' / time.strftime('%Y%m%d-%H%M%S')
    work.mkdir(parents=True, exist_ok=False)
    results = []

    def check(name, action):
        print(f'RUN {name}', flush=True)
        try:
            detail = action()
            results.append({'name': name, 'passed': True, 'detail': str(detail or '')})
        except Exception as exc:
            results.append({'name': name, 'passed': False, 'detail': str(exc)})
        print(('PASS ' if results[-1]['passed'] else 'FAIL ') + name + ': ' + results[-1]['detail'], flush=True)

    def parity():
        actual = (SCRIPT_DIR / 'enable_tlamatini_v2.bat').read_text(encoding='utf-8-sig')
        if actual != launcher_text(SCRIPT_DIR):
            raise RuntimeError('Embedded launcher is stale: run sync_enable_launcher.py visibly.')
        return 'Embedded helper and whitelist payloads match their reviewed source.'

    def python_syntax():
        for path in SCRIPT_DIR.glob('*.py'):
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))

    powershell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')

    def ps_check(name):
        subprocess.run([powershell, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                        str(SCRIPT_DIR / name)], check=True, timeout=60)

    def batch_check():
        # Exercise the real CMD parser from a path containing both spaces and an
        # apostrophe. --check exits before the launcher's UAC/apply branch.
        folder = work / "launcher path with spaces and apostrophe's"
        folder.mkdir()
        path = folder / 'enable_tlamatini_v2.bat'
        shutil.copy2(SCRIPT_DIR / path.name, path)
        # CMD has its own quoting rules; list2cmdline's backslash-escaped quotes
        # are not accepted by CMD. All variable values are quoted filesystem paths.
        command = f'"{os.environ["COMSPEC"]}" /d /s /c ""{path}" --check"'
        subprocess.run(command, check=True, timeout=30)

    check('Standalone payload parity', parity)
    check('Every Python asset parses', python_syntax)
    check('Every PowerShell asset parses', lambda: ps_check('test_security_syntax.ps1'))
    check('Mocked Windows access and defender behavior', lambda: ps_check('test_windows_access.ps1'))
    check('Standalone BAT syntax check from a complex path', batch_check)
    check('Shoter full-desktop evidence', lambda: take_shot(work))

    (work / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    rows = ''.join('<tr><td>' + ('PASS' if r['passed'] else 'FAIL') + '</td><td>' +
                   html.escape(r['name']) + '</td><td>' + html.escape(r['detail']) + '</td></tr>'
                   for r in results)
    (work / 'SUMMARY.html').write_text(
        '<!doctype html><meta charset="utf-8"><title>Tlamatini security checks</title>'
        '<style>body{font:16px Segoe UI;margin:2em}td{padding:.6em;border:1px solid #ccc}</style>'
        '<h1>Tlamatini security checks</h1><p>Non-admin, mocked policy tests; '
        'not proof that elevated settings were applied.</p><table>' + rows + '</table>', encoding='utf-8')
    passed = sum(r['passed'] for r in results)
    print(f'SECURITY ASSET CHECKS: {passed}/{len(results)} passed. Evidence: {work}', flush=True)
    return int(passed != len(results))


if __name__ == '__main__':
    raise SystemExit(main())
