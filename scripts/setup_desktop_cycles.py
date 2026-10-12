# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Five real desktop lifecycle cases, started manually in a visible console.

The development launcher and Explorer have demonstrably different registry
views on this machine. Start this fixed harness from Explorer. It performs no
security changes, accepts no external command queue and never launches, clicks,
activates or closes Uninstaller.exe. Uninstaller input remains manual.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import traceback

from markdown_canvas_visible import visible_console
import setup_release_cycles as cycles
from setup_windows import WindowsSnapshot

cycles.EVIDENCE = cycles.OUT / "evidence/desktop-campaign"
cycles.CASES = {case: "desktop/" + label for case, label in cycles.CASES.items()}
STATE = cycles.EVIDENCE / "campaign-state.json"


def state(case, phase, **details):
    data = dict(case=case, phase=phase, pid=os.getpid(), **details)
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(STATE)
    print(f"CAMPAIGN CASE {case}: {phase}", flush=True)


def passed(case, phase):
    record = cycles.EVIDENCE / f"case-{case}-{phase}.json"
    return record.is_file() and json.loads(record.read_text(encoding='utf-8')).get('passed')


def real_crash():
    import setup_crash_agents_visible as crash
    server = None
    try:
        visible_console()
        crash.prepare()
        server = subprocess.Popen(
            [str(crash.DST / 'Tlamatini.exe'), 'runserver', '--noreload', '127.0.0.1:8896'],
            cwd=crash.DST,
            env={**os.environ, 'TLAMATINI_COMMAND_TIMEOUT': '1800', 'PYTHONIOENCODING': 'utf-8'},
        )
        crash.save('server', crash.identity(server.pid))
        for _ in range(36):
            if server.poll() is not None:
                raise RuntimeError('Installed server exited before the real crash fixture was ready')
            try:
                with socket.create_connection(('127.0.0.1', 8896), timeout=1):
                    break
            except OSError:
                print('WAITING FOR INSTALLED SERVER; startup output remains visible above.', flush=True)
                time.sleep(5)
        else:
            raise TimeoutError('Installed server did not become ready within three minutes')
        state(5, 'real-crash-and-manual-removal', target=str(crash.DST))
        crash.agents()
    finally:
        # Cleanup is restricted to exact identities recorded by this fixture.
        cleanup = []
        for name in ('before-crash', 'orphaned'):
            path = crash.OUT / (name + '.json')
            if path.is_file():
                data = json.loads(path.read_text(encoding='utf-8'))
                cleanup.extend(data.get('agents', []))
                if data.get('unrelated_control'):
                    cleanup.append(data['unrelated_control'])
        path = crash.OUT / 'server.json'
        if path.is_file():
            cleanup.append(json.loads(path.read_text(encoding='utf-8')))
        stopped = []
        for row in {row['pid']: row for row in cleanup}.values():
            if crash.same_alive(row):
                crash.terminate_recorded(row)
                stopped.append(row['pid'])
        crash.save('fixture-final-cleanup', {'stopped_by_fixture': stopped})


def main():
    visible_console()
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    cycles.EVIDENCE.mkdir(parents=True, exist_ok=True)
    baseline = cycles.EVIDENCE / 'original-windows-state'
    if baseline.exists() and not args.resume:
        raise RuntimeError('Campaign already started. Use the fixed ResumeDesktopValidation.cmd after inspecting its state.')
    if not baseline.exists():
        # The earlier development-view entry must not be mistaken for real
        # desktop state. Refuse that known invalid launch environment.
        owner = WindowsSnapshot._read_value(r'Software\Microsoft\Windows\CurrentVersion\Uninstall\Tlamatini', 'InstallLocation')
        if owner and 'setup-release-validation' in str(owner['value']):
            raise RuntimeError('A prior test registration is visible. Inspect the launch context before starting a new desktop campaign.')
        cycles.clean_baseline()
        (cycles.EVIDENCE / 'launch-context.json').write_text(json.dumps({
            'manual_desktop_launch': True, 'pid': os.getpid(), 'initial_installed_apps_owner': owner,
            'purpose': 'Independent Windows-state checks in the same desktop context as manual uninstallation',
        }, indent=2), encoding='utf-8')
    for case in cycles.CASES:
        if passed(case, 'uninstalled'):
            continue
        state(case, 'preparing')
        if not passed(case, 'installed'):
            if not cycles.target(case).exists():
                cycles.prepare(case)
            state(case, 'installation', parent=str(cycles.target(case).parent))
            cycles.watch(case, 'install', launch=True)
            visible_console()
            cycles.verify_install(case)
        state(case, 'awaiting-manual-uninstaller', executable=str(cycles.target(case) / 'Uninstaller.exe'))
        if case == 5 and not (cycles.EVIDENCE / 'crash-agents/result.json').exists():
            real_crash()
        cycles.watch(case, 'uninstall', launch=False)
        visible_console()
        cycles.verify_uninstall(case)
        state(case, 'complete')
    WindowsSnapshot(baseline).restore()
    state(5, 'all-five-cycles-complete', original_windows_state_restored=True)
    cycles.write_report()
    print('PASS: FIVE COMPLETE DESKTOP INSTALLATIONS AND FIVE COMPLETE DESKTOP UNINSTALLATIONS.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        cycles.EVIDENCE.mkdir(parents=True, exist_ok=True)
        previous = json.loads(STATE.read_text(encoding='utf-8')) if STATE.is_file() else {}
        state(previous.get('case', 0), 'needs-attention', previous_phase=previous.get('phase'), error=str(exc))
        traceback.print_exc()
        sys.exit(1)
