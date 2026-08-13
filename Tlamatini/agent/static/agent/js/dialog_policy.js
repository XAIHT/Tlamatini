/* Tlamatini Author Banner - do not remove (releases scrub the name automatically)
 *
 * DIALOG DISMISSAL POLICY  (Angela, 2026-08-13)
 * =============================================
 * ONE rule, enforced in ONE place, for EVERY dialog on EVERY page:
 *
 *     A dialog disappears ONLY by its titlebar X, its Cancel/dismiss button,
 *     or its Continue/OK button.  X behaves EXACTLY like Cancel.
 *     Clicking OUTSIDE never closes.  Escape never closes.
 *
 * Why a policy module instead of editing each dialog: there are ~100 dialog
 * sites across 9 modules and two pages. Patching them one by one guarantees
 * the next dialog someone writes is born non-compliant - the same way the
 * installer and the updater drifted apart over one preserve list. Here the
 * default is set on the WIDGET and on the DOCUMENT, so a dialog written
 * tomorrow inherits the policy with no wiring at all.
 *
 * Load order: AFTER jquery-ui (we patch its prototype defaults), BEFORE the
 * application dialog modules. Every hook is defensive - a missing library is
 * skipped, never thrown, because a dialog policy must not be able to break
 * the page it governs.
 */
(function () {
    'use strict';

    // ---- 1. jQuery UI dialogs -------------------------------------------
    // One assignment disarms Escape for every jQuery UI dialog in the app,
    // including ones created later. jQuery UI's modal overlay already ignores
    // clicks, so there is nothing to disarm there.
    function applyJqueryUiPolicy() {
        var jq = window.jQuery;
        if (!jq || !jq.ui || !jq.ui.dialog || !jq.ui.dialog.prototype) return false;
        jq.ui.dialog.prototype.options.closeOnEscape = false;

        // Every dialog must EXPOSE its X, and X must mean Cancel. Two sites in
        // the app hide the titlebar close button; this runs at document level,
        // i.e. AFTER each dialog's own `open:` callback, so it wins over them
        // without the callers having to remember.
        //
        // DEFERRED ON PURPOSE. jQuery UI's `_trigger` fires the `dialogopen`
        // EVENT first and calls the dialog's own `open:` option callback
        // AFTER it - so a callback that hides the X (acp-control-buttons.js
        // does exactly that) would win a synchronous handler. A macrotask tick
        // puts us last, after every open-time callback has had its say.
        jq(document).on('dialogopen', function (ev) {
            var target = ev.target;
            window.setTimeout(function () {
                try {
                    jq(target).closest('.ui-dialog')
                        .find('.ui-dialog-titlebar-close').show();
                } catch (err) { /* never break opening a dialog */ }
            }, 0);
        });
        return true;
    }

    // ---- 2. Native <dialog> ---------------------------------------------
    // Escape on a native dialog fires `cancel` and then closes it. Capture
    // phase on document sees it before the element's own handler, so this
    // covers present and future native dialogs alike.
    document.addEventListener('cancel', function (ev) {
        ev.preventDefault();
    }, true);

    // ---- 3. Bootstrap modals --------------------------------------------
    // Data-attribute modals read these defaults too, so this covers markup we
    // never touch.
    function applyBootstrapPolicy() {
        var bs = window.bootstrap;
        if (!bs || !bs.Modal || !bs.Modal.Default) return false;
        bs.Modal.Default.backdrop = 'static';
        bs.Modal.Default.keyboard = false;
        return true;
    }

    // ---- 4. Custom div overlays -----------------------------------------
    // Hand-rolled overlays (#about-overlay, #update-overlay, the voice and
    // parametrizer overlays, the prompts catalog) are plain divs: they get
    // neither the jQuery UI option nor the native `cancel` event. Escape is
    // swallowed ONLY while one of them is actually visible, so Escape keeps
    // working everywhere else on the page - notably the ACP canvas, where it
    // cancels an in-progress connection drag.
    var CUSTOM_OVERLAYS = [
        '#about-overlay', '#update-overlay', '#tlm-voice-overlay',
        '#prompts-catalog', '.acp-param-overlay', '.tlm-modal-overlay'
    ];

    function aCustomOverlayIsVisible() {
        for (var i = 0; i < CUSTOM_OVERLAYS.length; i++) {
            var nodes = document.querySelectorAll(CUSTOM_OVERLAYS[i]);
            for (var j = 0; j < nodes.length; j++) {
                var el = nodes[j];
                if (el.offsetParent !== null || el.style.display === 'flex') return true;
            }
        }
        return false;
    }

    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape' && ev.key !== 'Esc') return;
        if (!aCustomOverlayIsVisible()) return;
        ev.preventDefault();
        ev.stopPropagation();
    }, true);

    // ---- 5. Sealed dialogs (the updater) --------------------------------
    // A sealed dialog cannot be dismissed at all: no X, no Escape, no outside
    // click, and leaving the page raises the browser's own confirmation.
    //
    // HONEST LIMIT, stated so nobody later believes otherwise: a web page
    // CANNOT veto a tab close. `beforeunload` shows the browser's built-in
    // prompt and the user may still confirm it - no API overrides that. What
    // makes this safe anyway is that the update swap runs in an EXTERNAL
    // PowerShell process, so a closed tab does not abort an update in flight.
    var sealed = Object.create(null);

    function seal(key, message) {
        sealed[key] = message || 'This operation cannot be interrupted.';
    }

    function unseal(key) {
        delete sealed[key];
    }

    function isSealed(key) {
        return Object.prototype.hasOwnProperty.call(sealed, key);
    }

    function anySealed() {
        for (var k in sealed) { if (isSealed(k)) return k; }
        return null;
    }

    /**
     * Gate for a dismissal attempt. Returns TRUE when the caller may close.
     * A sealed dialog alerts the user and refuses.
     */
    function mayClose(key) {
        if (!isSealed(key)) return true;
        window.alert(sealed[key]);
        return false;
    }

    window.addEventListener('beforeunload', function (ev) {
        var key = anySealed();
        if (!key) return undefined;
        ev.preventDefault();
        ev.returnValue = sealed[key];   // required for the browser prompt
        return sealed[key];
    });

    // ---- wiring ---------------------------------------------------------
    // Libraries may not be parsed yet when this file runs; retry once the DOM
    // is ready. Both calls are idempotent.
    var jqDone = applyJqueryUiPolicy();
    var bsDone = applyBootstrapPolicy();
    if (!jqDone || !bsDone) {
        document.addEventListener('DOMContentLoaded', function () {
            if (!jqDone) jqDone = applyJqueryUiPolicy();
            if (!bsDone) bsDone = applyBootstrapPolicy();
        });
    }

    window.TlamatiniDialogPolicy = {
        seal: seal,
        unseal: unseal,
        isSealed: isSealed,
        mayClose: mayClose
    };
})();
