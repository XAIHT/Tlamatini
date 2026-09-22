# ══════════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ══════════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""A RESTORED CONTEXT MUST LOOK AS BUSY AS IT IS (2026-09-22).

THE BUG. Tlamatini reopens with a context already saved in ``SessionState``
(the user loaded one, then the app was closed and started again). The consumer
sends ``session-restored`` with ``loading: true`` the instant the socket opens,
and the chat page correctly flips the Send button to 'Cancel', greys every
navbar entry and makes the input read-only -- and then shows NO SPINNER AT ALL.
The page is genuinely frozen while LOOKING perfectly idle, which is exactly how
a hung application looks. The same context loaded from the Context menu shows
the spinner normally.

WHY. ``#wait-spinner`` is a CHILD of ``#chat-log``, and ``renderInitialMessages()``
wipes ``#chat-log`` with ``innerHTML = ''``. On the restore path that wipe lands
AFTER the spinner was created, because the two events happen at very different
moments in the page's life:

    agent_page_state.js   the socket opens; arriving frames are buffered
    agent_page_chat.js    drains the buffer at SCRIPT-PARSE time
                          -> session-restored {loading: true}
                          -> disableControlsDuringOperation()   SPINNER ADDED
    agent_page_init.js    window.onload - fires only once every image, font and
                          stylesheet has landed, i.e. much later
                          -> renderInitialMessages() -> innerHTML = ''
                          -> SPINNER DESTROYED

``disableControlsDuringOperation()`` is idempotent (its spinner is guarded by
``if (!document.getElementById(spinnerId))``), so nothing ever put it back.

THE CONTRACT, in two layers, both pinned here:

  1. ``renderInitialMessages()`` captures the live spinner BEFORE the wipe and
     re-appends it after. A history render is a RENDER: it repaints old rows and
     must not delete a live UI widget.
  2. ``window.onload`` RE-ASSERTS the busy UI at its very end, because it is the
     layer that knows the busy latch and everything it does runs against a page
     that may already be busy.

Layer 2 alone would hide the symptom; layer 1 alone is the honest repair. Both
are kept so the visible state can never silently disagree with the logical one.

Visible end-to-end proof:
``.claude/skills/tlamatini-daily-chat-test/harness/context_restore_spinner_visible.py``
(headed Chrome, real GUI, Shoter photographs the busy window).
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent

CHAT_JS = Path("static") / "agent" / "js" / "agent_page_chat.js"
INIT_JS = Path("static") / "agent" / "js" / "agent_page_init.js"
UI_JS = Path("static") / "agent" / "js" / "agent_page_ui.js"


def _strip_block_comments(text: str) -> str:
    """Drop /* ... */ blocks so a quoted pattern in prose cannot satisfy a check."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _strip_line_comments(text: str) -> str:
    """Drop // lines. The fix carries a long explanatory comment that NAMES the
    very patterns these tests forbid - without this, the documentation would
    satisfy the assertions it exists to explain."""
    return re.sub(r"^\s*//.*$", "", text, flags=re.M)


def _code_only(text: str) -> str:
    return _strip_line_comments(_strip_block_comments(text))


class ContextRestoreSpinnerContractTests(unittest.TestCase):
    """Source contract. Runs against the working tree and the collected copy."""

    def _read(self, relative: Path) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def _read_collected(self, relative: Path):
        collected = PROJECT_ROOT / "staticfiles" / relative.relative_to("static")
        if not collected.exists():
            return None
        return collected.read_text(encoding="utf-8")

    # ── the function body we care about ───────────────────────────────────
    @staticmethod
    def _render_initial_messages_body(code: str) -> str:
        start = code.index("function renderInitialMessages(")
        depth = 0
        for i in range(code.index("{", start), len(code)):
            if code[i] == "{":
                depth += 1
            elif code[i] == "}":
                depth -= 1
                if depth == 0:
                    return code[start:i + 1]
        raise AssertionError("renderInitialMessages() body never closed.")

    def _assert_render_preserves_spinner(self, code: str, where: str) -> None:
        body = self._render_initial_messages_body(code)

        wipe = body.index("chatLog.innerHTML")
        capture = body.find("document.getElementById(spinnerId)")
        self.assertNotEqual(
            capture, -1,
            f"[{where}] renderInitialMessages() must capture the live spinner "
            "before it wipes #chat-log - the spinner is a CHILD of #chat-log.",
        )
        self.assertLess(
            capture, wipe,
            f"[{where}] the spinner must be captured BEFORE "
            "`chatLog.innerHTML = ''`; after the wipe it no longer exists.",
        )
        self.assertRegex(
            body[wipe:], r"chatLog\.appendChild\(\s*liveSpinner\s*\)",
            msg=(f"[{where}] renderInitialMessages() must re-append the captured "
                 "spinner after the wipe, or a restored context loads with the "
                 "chat frozen and nothing on screen saying so."),
        )

    def _assert_onload_reasserts_busy_ui(self, code: str, where: str) -> None:
        onload = code[code.index("window.onload = () => {"):]
        self.assertRegex(
            onload,
            r"if\s*\(\s*inLongOperation\s*===\s*true\s*\|\|\s*"
            r"lapseLoadingContext\s*===\s*true\s*\)",
            msg=(f"[{where}] window.onload must re-assert the busy UI: the busy "
                 "state is set at script-parse time, long before the load event, "
                 "and renderInitialMessages() runs in between."),
        )
        guard = onload.index("inLongOperation === true ||")
        self.assertRegex(
            onload[guard:], r"disableControlsDuringOperation\(\)",
            msg=(f"[{where}] the re-assert must call "
                 "disableControlsDuringOperation() - it is what rebuilds the "
                 "spinner and re-greys the navbar."),
        )
        self.assertRegex(
            onload[guard:], r"setTitleBusy\(true\)",
            msg=f"[{where}] the re-assert must also restore the busy title.",
        )

    # ── tests ─────────────────────────────────────────────────────────────
    def test_render_initial_messages_preserves_the_live_spinner(self):
        self._assert_render_preserves_spinner(
            _code_only(self._read(CHAT_JS)), "source")

    def test_window_onload_reasserts_the_busy_ui(self):
        self._assert_onload_reasserts_busy_ui(
            _code_only(self._read(INIT_JS)), "source")

    def test_the_reassert_is_the_last_thing_window_onload_does(self):
        """Anything after it could undo it again - that is the whole failure
        mode. The guard is the final statement of the handler."""
        code = _code_only(self._read(INIT_JS))
        onload = code[code.index("window.onload = () => {"):]
        guard = onload.index("inLongOperation === true ||")
        tail = onload[guard:]
        end = tail.index("\n};")
        after_guard = tail[:end]
        # Only the guard's own three statements may sit between the `if` and the
        # end of the handler.
        statements = [s.strip() for s in after_guard.splitlines() if s.strip()]
        self.assertLessEqual(
            len(statements), 6,
            "The busy re-assert must be the LAST thing window.onload does; "
            "anything running after it can undo it, which is the exact bug.",
        )

    def test_the_spinner_really_lives_inside_chat_log(self):
        """The whole contract exists because of this one parent-child fact. If
        the spinner ever moves out of #chat-log, these guards become noise and
        should be revisited deliberately rather than left lying around."""
        ui = _code_only(self._read(UI_JS))
        disable = ui[ui.index("function disableControlsDuringOperation()"):]
        self.assertRegex(
            disable[:2000], r"chatLog\.appendChild\(\s*waitWidget\s*\)",
            msg="disableControlsDuringOperation() is expected to append the "
                "spinner to #chat-log; update test_context_restore_spinner.py "
                "deliberately if that ever changes.",
        )

    def test_collected_static_carries_the_same_fix(self):
        """RELEASE builds serve staticfiles/, not the source tree. A stale
        collected copy would ship the bug to users while the source looks fixed."""
        chat = self._read_collected(CHAT_JS)
        init = self._read_collected(INIT_JS)
        if chat is None or init is None:
            self.skipTest("staticfiles/ not collected; run collectstatic.")
        self._assert_render_preserves_spinner(_code_only(chat), "staticfiles")
        self._assert_onload_reasserts_busy_ui(_code_only(init), "staticfiles")


if __name__ == "__main__":
    unittest.main()
