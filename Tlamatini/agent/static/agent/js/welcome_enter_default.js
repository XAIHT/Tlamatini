/* ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove
 *
 * welcome_enter_default.js — ENTER is the default action on the welcome page.
 *
 *   welcome.html renders  →  press Enter  →  you are in the chat.
 *
 * Nothing has to be clicked, tabbed or focused first. "Go to Chat" is the one
 * thing anybody opens this page to do, so the keyboard should not have to hunt
 * for it.
 *
 * TWO LAYERS, DELIBERATELY:
 *   1. The link is FOCUSED as soon as the page is ready, so the BROWSER itself
 *      activates it on Enter — and its focus ring shows the user exactly where
 *      the key will go. (welcome.css sets no `outline: none`, so Bootstrap's
 *      own ring is visible.)
 *   2. A document-level keydown fallback catches Enter when focus was never
 *      granted — a stray click on the card body, or a browser that refuses the
 *      programmatic focus. Layer 1 normally wins and layer 2 stands down,
 *      because it defers whenever something activatable already holds focus.
 *
 * ⚠️ THAT DEFERRAL IS THE WHOLE REASON THIS INSPECTS activeElement. Fire Enter
 * blindly and tabbing to "Logout" then pressing Enter would silently send the
 * user to the chat instead — the opposite of what they asked for. Enter belongs
 * to the browser whenever the browser already has a target for it.
 *
 * FAIL-OPEN: every step is guarded. A missing link or a focus() that throws
 * leaves the page exactly as it was, and both buttons still work by mouse — a
 * broken shortcut must never cost the user the page itself.
 *
 * Self-contained IIFE: it declares NO cross-file globals (see the const-poison
 * contract in docs/claude/frontend.md — this module owns all its state).
 */
(function () {
    'use strict';

    const GO_TO_CHAT_ID = 'go-to-chat';

    // Elements that own Enter themselves. When one of these holds focus this
    // module keeps its hands off and lets the browser do the obvious thing.
    const ACTIVATABLE = 'a, button, input, textarea, select, [contenteditable="true"]';

    function focusGoToChat(link) {
        // preventScroll stops a short page jumping under the user; older
        // browsers ignore the options object, so fall back to a bare focus().
        try {
            link.focus({ preventScroll: true });
        } catch (err) {
            try {
                link.focus();
            } catch (err2) {
                /* Focus is a nicety — layer 2 still delivers the shortcut. */
            }
        }
    }

    function isPlainEnter(event) {
        if (event.key !== 'Enter') { return false; }
        if (event.isComposing) { return false; }        // mid-IME composition
        if (event.defaultPrevented) { return false; }
        return !(event.altKey || event.ctrlKey || event.metaKey || event.shiftKey);
    }

    function browserAlreadyOwnsEnter() {
        const active = document.activeElement;
        return Boolean(active && active.closest && active.closest(ACTIVATABLE));
    }

    function install() {
        const link = document.getElementById(GO_TO_CHAT_ID);
        if (!link) { return; }

        focusGoToChat(link);

        document.addEventListener('keydown', function (event) {
            if (!isPlainEnter(event) || browserAlreadyOwnsEnter()) { return; }
            event.preventDefault();
            link.click();
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', install);
    } else {
        install();
    }
})();
