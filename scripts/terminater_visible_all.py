# Tlamatini Author Banner — Angela López Mendoza
"""VISIBLE all-in-one run: the chat page (with and without its canvas), the Agentic Control Panel
(empty and with a loaded flow) and the Prompt Flow Panel (empty and with a loaded flow), in ONE
headed Chrome and ONE test server.

Run from a foreground PowerShell -NoExit console:  python scripts/terminater_visible_all.py
(the three single-page scripts do the same work one page at a time).
"""
from __future__ import annotations

import sys

import terminater_visible_acp as acp
import terminater_visible_chat as chat
import terminater_visible_pfp as pfp
from terminater_visible_common import Harness, api


def reset_between_pages(H, path):
    """Start the next page from the same clean point a single-page run starts from: no shell alive in
    the hub (they survive a page change on purpose), nothing remembered by the dock, dock hidden."""
    try:
        api('kill_all')
        api('layout', layout='tabs', area='dock', show=False)
    except Exception as error:  # noqa: BLE001 - a failed cleanup shows up in the first checks of the next page
        print('cleanup between pages failed: %s' % error, flush=True)
    H.page.evaluate("() => Object.keys(localStorage).filter(k => k.startsWith('tlamatini.terminals.')).forEach(k => localStorage.removeItem(k))")
    H.goto(path)
    H.wait_dock_ready()
    state = H.dock() or {}
    if state.get('visible'):
        H.page.keyboard.press('Control+`')
        H.page.wait_for_timeout(600)


def main():
    with Harness('all', '/agent/agent/') as H:
        chat.run(H)
        reset_between_pages(H, acp.PATH)
        acp.run(H)
        reset_between_pages(H, pfp.PATH)
        pfp.run(H)
    sys.exit(getattr(H, 'exit_code', 1))


if __name__ == '__main__':
    main()
