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
        '#prompts-catalog', '.acp-param-overlay', '.tlm-modal-overlay',
        '#tlm-popup-host'
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
     * A sealed dialog tells the user why and refuses.
     *
     * Stays SYNCHRONOUS on purpose — callers use the boolean to decide whether
     * to close right now. tlmAlert is fire-and-forget here: the refusal does
     * not depend on the notice being acknowledged.
     */
    function mayClose(key) {
        if (!isSealed(key)) return true;
        tlmAlert(sealed[key], 'Please wait');
        return false;
    }

    // ---- 6. Themed popups — tlmAlert / tlmConfirm ------------------------
    // Angela's review, 2026-08-16: nine `alert()` / `confirm()` calls survived
    // in contacts_dialog.js and external_mcps_dialog.js after every other
    // dialog was themed. The canvas page got acpAlert/acpConfirm on
    // 2026-08-12; the CHAT page never got its pair, so the two newest, most
    // polished dialogs in the app were the two that still raised a grey
    // Windows/Chrome strip with the page URL in it.
    //
    // ⚠️ WHY NOT REUSE acpAlert's jQuery-UI HOST: contacts (`ctb-*`) and
    // External ▸ MCPs (`emx-*`) are NATIVE CSS modals at `z-index: 20000`,
    // while a jQuery-UI dialog sits on `.ui-front` (~100). Rendering the
    // confirm through jQuery UI would put it UNDERNEATH the dialog that asked
    // for it — an invisible modal, i.e. a hang. This host is a native overlay
    // at 100001, above every layer the app defines.
    //
    // Policy-compliant by construction: no outside-click dismissal, Escape is
    // swallowed (the host is in CUSTOM_OVERLAYS above), and X === Cancel ===
    // false — a destructive action is never taken because a dialog was
    // dismissed. Fails OPEN to the native popup: an ugly warning beats a lost
    // one, exactly as acp-globals.js decided.
    var POPUP_HOST_ID = 'tlm-popup-host';

    function _popupTeardown(host, onDone, value) {
        try {
            if (host && host.parentNode) host.parentNode.removeChild(host);
        } catch (err) { /* never let teardown throw at the caller */ }
        if (typeof onDone === 'function') onDone(value);
    }

    function _popupEl(tag, cls, text) {
        var el = document.createElement(tag);
        if (cls) el.className = cls;
        if (text != null) el.textContent = String(text);
        return el;
    }

    /**
     * Build and show the popup. `buttons` is [{label, value, primary}], LAST
     * one focused. Returns TRUE when it rendered, FALSE when the caller must
     * fall back to the native popup.
     */
    function _showPopup(opts, onDone) {
        if (!document.body) return false;
        var existing = document.getElementById(POPUP_HOST_ID);
        if (existing && existing.parentNode) existing.parentNode.removeChild(existing);

        var host = _popupEl('div', 'tlmpop-overlay');
        host.id = POPUP_HOST_ID;
        host.style.display = 'flex';

        var card = _popupEl('div', 'tlmpop-card');
        card.setAttribute('role', 'dialog');
        card.setAttribute('aria-modal', 'true');

        var head = _popupEl('div', 'tlmpop-head');
        head.appendChild(_popupEl('span', 'tlmpop-title', opts.title || 'Tlamatini'));
        var x = _popupEl('button', 'tlmpop-x', '×');
        x.type = 'button';
        x.setAttribute('aria-label', 'Close');
        head.appendChild(x);
        card.appendChild(head);

        var body = _popupEl('div', 'tlmpop-body');
        if (opts.primary) body.appendChild(_popupEl('p', 'tlmpop-msg', opts.primary));
        if (opts.secondary) body.appendChild(_popupEl('p', 'tlmpop-sub', opts.secondary));
        card.appendChild(body);

        var foot = _popupEl('div', 'tlmpop-foot');
        var buttons = opts.buttons || [];
        var focusTarget = null;
        buttons.forEach(function (spec) {
            var btn = _popupEl('button',
                'tlmpop-btn' + (spec.primary ? ' tlmpop-btn-primary' : ''), spec.label);
            btn.type = 'button';
            btn.onclick = function () { _popupTeardown(host, onDone, spec.value); };
            foot.appendChild(btn);
            if (spec.primary) focusTarget = btn;
        });
        card.appendChild(foot);

        // X behaves EXACTLY like Cancel — the app-wide rule.
        x.onclick = function () { _popupTeardown(host, onDone, opts.dismissValue); };

        // Outside click does NOT dismiss. Swallow it so it cannot reach the
        // dialog underneath either.
        host.addEventListener('mousedown', function (ev) {
            if (ev.target === host) { ev.preventDefault(); ev.stopPropagation(); }
        });

        // Keep Tab inside the popup while it owns the screen.
        host.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' || ev.key === 'Esc') {
                ev.preventDefault();
                ev.stopPropagation();
                return;
            }
            if (ev.key !== 'Tab') return;
            var focusable = card.querySelectorAll('button');
            if (!focusable.length) return;
            var first = focusable[0];
            var last = focusable[focusable.length - 1];
            if (ev.shiftKey && document.activeElement === first) {
                ev.preventDefault(); last.focus();
            } else if (!ev.shiftKey && document.activeElement === last) {
                ev.preventDefault(); first.focus();
            }
        });

        host.appendChild(card);
        document.body.appendChild(host);
        if (focusTarget) {
            window.setTimeout(function () {
                try { focusTarget.focus(); } catch (err) { /* focus is best effort */ }
            }, 0);
        }
        return true;
    }

    /**
     * Themed replacement for `window.alert`. Returns a Promise that resolves
     * when the user acknowledges (so a caller MAY sequence on it).
     */
    function tlmAlert(message, title) {
        return new Promise(function (resolve) {
            var text = String(message == null ? '' : message);
            var shown = false;
            try {
                shown = _showPopup({
                    title: title,
                    secondary: text,
                    dismissValue: true,
                    buttons: [{ label: 'OK', value: true, primary: true }]
                }, resolve);
            } catch (err) {
                // `shown` is still false — fall through to the native popup,
                // but say WHY, so a broken theme is diagnosable instead of
                // just looking like an old-style alert box.
                console.warn('tlmAlert: themed popup failed, using the native one', err);
            }
            if (!shown) {
                window.alert(text);        // fail open — never lose a warning
                resolve(true);
            }
        });
    }

    /**
     * Themed replacement for `window.confirm`. Returns a Promise<boolean>.
     * Anything other than pressing Continue resolves FALSE.
     */
    function tlmConfirm(primary, secondary, title) {
        return new Promise(function (resolve) {
            var decided = false;
            var finish = function (value) {
                if (decided) return;
                decided = true;
                resolve(value === true);
            };
            var shown = false;
            try {
                shown = _showPopup({
                    title: title || 'Please confirm',
                    primary: primary,
                    secondary: secondary,
                    dismissValue: false,
                    buttons: [
                        { label: 'Cancel', value: false },
                        { label: 'Continue', value: true, primary: true }
                    ]
                }, finish);
            } catch (err) {
                console.warn('tlmConfirm: themed popup failed, using the native one', err);
            }
            if (!shown) {
                var joined = [primary, secondary].filter(Boolean).join('\n\n');
                finish(window.confirm(joined));
            }
        });
    }

    window.tlmAlert = tlmAlert;
    window.tlmConfirm = tlmConfirm;


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
        mayClose: mayClose,
        alert: tlmAlert,
        confirm: tlmConfirm
    };
})();
