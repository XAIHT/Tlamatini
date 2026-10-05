# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Exercise the installed Windows file association using actual ShellExecute."""
import os

import psutil
from playwright.sync_api import expect
from flow_files_visible import console_foreground
from prompt_flow_connections_visible import require_browser_foreground


def run_shell_file_checks(context, fpmt, flw, install, browser_command, checkpoint):
    def main_processes():
        expected = os.path.normcase(str(install / 'Tlamatini.exe'))
        result = set()
        for process in psutil.process_iter(['pid', 'exe', 'create_time']):
            if os.path.normcase(process.info['exe'] or '') == expected:
                result.add((process.pid, process.info['create_time']))
        return result

    original = main_processes()
    assert original, 'The installed server must already be running for the warm-open check'
    def open_registered(file):
        console_foreground()
        with context.expect_page(timeout=60000) as opened:
            # Only the destination browser is selected; Windows resolves the real
            # extension, ProgID and registered command. No launcher is substituted.
            previous_browser = os.environ.get('BROWSER')
            try:
                os.environ['BROWSER'] = browser_command
                os.startfile(str(file), 'open')
            finally:
                if previous_browser is None:
                    os.environ.pop('BROWSER', None)
                else:
                    os.environ['BROWSER'] = previous_browser
        target = opened.value
        target.wait_for_load_state()
        target.bring_to_front()
        require_browser_foreground(target)
        target.evaluate('document.fonts.ready')
        return target

    # A recovered local draft is intentionally dirty. Verify the user's real
    # Cancel and Continue choices instead of treating the safeguard as a failure.
    cancelled = open_registered(fpmt)
    expect(cancelled.get_by_text('Replace the current diagram?', exact=True)).to_be_visible()
    draft = cancelled.locator('.pmt-node').evaluate_all('(nodes) => nodes.map(n => n.outerHTML)')
    cancelled.get_by_role('button', name='Cancel', exact=True).click()
    expect(cancelled.locator('#pmt-status')).to_have_text('Opening cancelled. Your current diagram was kept.')
    assert cancelled.locator('.pmt-node').evaluate_all('(nodes) => nodes.map(n => n.outerHTML)') == draft
    checkpoint('shell-open-fpmt-cancel-keeps-recovered-draft', cancelled)
    cancelled.close()

    for file in (fpmt, flw):
        target = open_registered(file)
        if file.suffix.lower() == '.fpmt':
            expect(target.get_by_text('Replace the current diagram?', exact=True)).to_be_visible()
            target.get_by_role('button', name='Continue', exact=True).click()
            expect(target.locator('#filename')).to_have_text(file.name, timeout=30000)
            expect(target.locator('.pmt-node')).to_have_count(4)
            expect(target.locator('#pmt-run-state')).to_have_text('Idle')
        else:
            expect(target.locator('.canvas-item')).to_have_count(2, timeout=30000)
            expect(target.locator('#sleeper-3')).to_be_visible()
            expect(target.locator('#btn-stop')).to_be_disabled()
        # A warm dispatcher may take a moment to exit after opening Chrome.
        for _ in range(40):
            if main_processes() == original:
                break
            target.wait_for_timeout(250)
        assert main_processes() == original, 'Windows open left an extra application process'
        checkpoint('shell-open-' + file.suffix[1:].lower() + '-unicode-and-instance-reuse', target)
        target.close()
