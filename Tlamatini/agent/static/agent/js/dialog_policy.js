/* Tlamatini Author Banner - do not remove (releases scrub the name automatically)
 *
 * DIALOG DISMISSAL POLICY  (Angela, 2026-08-13; ESCAPE STANDARDISED 2026-08-16)
 * ============================================================================
 * ONE rule, enforced in ONE place, for EVERY dialog on EVERY page:
 *
 *     A dialog disappears ONLY by its titlebar X, its Cancel/dismiss button,
 *     its Continue/OK button, or the ESCAPE KEY.
 *     X behaves EXACTLY like Cancel, and ESCAPE behaves EXACTLY like X.
 *     Clicking OUTSIDE still never closes.
 *
 * CHANGED 2026-08-16, ON ANGELA'S EXPLICIT INSTRUCTION. Until today the rule
 * ended "Escape never closes", and this module spent its section 4 SWALLOWING
 * the key. Escape is now the third, keyboard-shaped spelling of Cancel: it
 * dismisses, and dismissing does NOTHING ELSE - no save, no submit, no
 * destructive action, no affirmative button ever pressed on the user's behalf.
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
    // One assignment ARMS Escape for every jQuery UI dialog in the app,
    // including ones created later. jQuery UI's own handler calls this.close(),
    // i.e. byte-for-byte the titlebar-X path, so every beforeClose/close
    // callback still runs. Its modal overlay already ignores clicks, so
    // outside-click dismissal stays off.
    //
    // This is a DEFAULT, not the enforcement: a module may still pass an
    // explicit `closeOnEscape: false` in its own options and win. Section 4's
    // dispatcher is what actually guarantees the rule holds everywhere.
    function applyJqueryUiPolicy() {
        var jq = window.jQuery;
        if (!jq || !jq.ui || !jq.ui.dialog || !jq.ui.dialog.prototype) return false;
        jq.ui.dialog.prototype.options.closeOnEscape = true;

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
    // Escape on a native <dialog> fires the `cancel` event and then closes it -
    // which is exactly the behaviour the policy now wants, so THERE IS NOTHING
    // TO DO HERE. A document-level `cancel` interceptor used to sit at this
    // spot calling preventDefault(); it was removed on 2026-08-16 with the rest
    // of the Escape swallowing. Do not put it back: `cancel` is the platform's
    // own word for "the user dismissed this without choosing", i.e. Cancel.

    // ---- 3. Bootstrap modals --------------------------------------------
    // Data-attribute modals read these defaults too, so this covers markup we
    // never touch. The two knobs are INDEPENDENT and only one of them flipped
    // on 2026-08-16:
    //   keyboard: true   -> Escape hides the modal (Bootstrap preventDefault()s
    //                       the keydown, which is how section 4 knows to keep
    //                       its hands off).
    //   backdrop:'static'-> an OUTSIDE CLICK still does not dismiss. Unchanged.
    function applyBootstrapPolicy() {
        var bs = window.bootstrap;
        if (!bs || !bs.Modal || !bs.Modal.Default) return false;
        bs.Modal.Default.backdrop = 'static';
        bs.Modal.Default.keyboard = true;
        return true;
    }

    // ---- 4. THE ESCAPE DISPATCHER ---------------------------------------
    // Sections 1-3 arm Escape for the three dialog TECHNOLOGIES. This section
    // is what makes the rule true for the ~100 HAND-ROLLED dialogs that use no
    // technology at all - #about-overlay, #update-overlay, the voice, log
    // viewer, agent description, parametrizer and FlowCreator overlays, the
    // Catalog of prompts, the native emx-/ctb- modals - plus any jQuery UI
    // dialog that passes an explicit `closeOnEscape: false` of its own.
    //
    // ⚠️ IT NEVER "HIDES" A DIALOG ITSELF (except as a last resort, loudly).
    // It finds the TOPMOST open dialog and invokes THAT DIALOG'S OWN dismissal
    // - the very click the user would make on its X or Cancel. Everything a
    // dialog does on dismissal therefore keeps happening, for free, with zero
    // per-dialog wiring:
    //     * the exec-permission prompt still answers DENY (its close handler),
    //     * acpConfirm / tlmConfirm still resolve FALSE,
    //     * the SEALED updater still REFUSES (CloseUpdateDialog -> mayClose),
    //     * body.style.overflow is still restored by each dialog's own close.
    // A dispatcher that hid nodes itself would silently skip all four. Same
    // reasoning as checkbox_bulk_toggle.js clicking a checkbox instead of
    // assigning .checked.
    //
    // ⚠️ BUBBLE PHASE, NOT CAPTURE - and this is load-bearing. An inner widget
    // must get first refusal: the Catalog's search box clears the query on
    // Escape and stops the event there, so the FIRST Escape empties the search
    // and only the SECOND closes the catalog. The old capture-phase listener
    // stole both. Being registered before every application module (the pages
    // load this file right after jQuery UI) also puts us first among the
    // document-level handlers, so stopImmediatePropagation() below can stop a
    // second dialog underneath from eating the same keystroke.

    // What can be an open dialog. Deliberately SHAPE-BASED, not a hand-kept
    // inventory: an overlay named `#foo-overlay` tomorrow is covered with no
    // edit here. The list this replaces had already drifted - it carried
    // '#prompts-catalog', which is the BUTTON that opens the catalog and is
    // therefore always visible, so Escape was in fact being swallowed across
    // the whole chat page rather than only over an open dialog.
    var LAYER_SELECTOR = [
        '.tlmpop-overlay',                        // themed tlmAlert / tlmConfirm
        '.ui-dialog',                             // jQuery UI
        '.modal.show', '.modal.in', '#modal',     // Bootstrap-shaped + Catalog
        'dialog[open]',                           // native <dialog>
        '[role="dialog"]', '[role="alertdialog"]',
        '[id$="-overlay"]', '[class*="-overlay"]',
        '.tlm-modal-overlay', '.emx-modal', '.ctb-modal'
    ].join(',');

    // A backdrop is NOT a dialog. Dismissing one would leave its panel floating
    // over an undimmed page - and `.ui-widget-overlay` also wears the
    // `.starter-execution-overlay` / `.ender-execution-overlay` classes, so it
    // is matched by the `-overlay` shape above and must be excluded by name.
    var NOT_A_DIALOG = '.ui-widget-overlay, .modal-backdrop';

    // Dismiss controls, in priority order, X FIRST. Escape must never be able
    // to land on a button that DOES something (Continue, Update now, Delete).
    var DISMISS_SELECTORS = [
        '[data-dialog-dismiss]',
        '.ui-dialog-titlebar-close',
        '[data-bs-dismiss="modal"]', '.btn-close',
        '.tlmpop-x', '.tlm-modal-x', '.about-close-btn',
        '.emx-icon-button', '.ctb-icon-button',
        'button[aria-label="Close"]', 'button[title="Close"]'
    ];

    // Labels that mean "go away and do nothing". NEVER an affirmative word.
    var DISMISS_WORDS = ['cancel', 'close', 'dismiss', 'cancelar', 'cerrar', 'no'];
    var X_GLYPHS = ['×', '✕', '✖', '✗', 'x'];

    function isShowing(el) {
        if (!el || el.nodeType !== 1 || el.hidden) return false;
        try {
            return el.getClientRects().length > 0;
        } catch (err) {
            return false;
        }
    }

    function matches(el, selector) {
        try {
            return !!(el.matches && el.matches(selector));
        } catch (err) {
            return false;
        }
    }

    /** Highest z-index on the element or any ancestor. */
    function stackRank(el) {
        var rank = 0;
        var node = el;
        while (node && node.nodeType === 1) {
            var z = parseInt(window.getComputedStyle(node).zIndex, 10);
            if (!isNaN(z) && z > rank) rank = z;
            node = node.parentNode;
        }
        return rank;
    }

    /**
     * Two of the canvas dialogs are a bare backdrop div (`#x-overlay`) with the
     * actual panel as its SIBLING (`#x-dialog`) - the panel is where the X is.
     */
    function panelFor(el) {
        if (el.id && /-overlay$/.test(el.id)) {
            var panel = document.getElementById(el.id.replace(/-overlay$/, '-dialog'));
            if (isShowing(panel)) return panel;
        }
        return el;
    }

    function topmostOpenDialog() {
        var nodes = document.querySelectorAll(LAYER_SELECTOR);
        var best = null;
        var bestRank = -1;
        // querySelectorAll yields DOCUMENT ORDER, so `>=` makes the later - and
        // for nested candidates the INNER - element win a tie. That is what we
        // want twice over: a panel inside its own overlay owns the X, and the
        // most recently opened sibling dialog is the one on top.
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (matches(el, NOT_A_DIALOG)) continue;
            if (!isShowing(el)) continue;
            var rank = stackRank(el);
            if (rank >= bestRank) {
                best = el;
                bestRank = rank;
            }
        }
        return best ? panelFor(best) : null;
    }

    function findDismissControl(root) {
        var i;
        for (i = 0; i < DISMISS_SELECTORS.length; i++) {
            var direct = root.querySelector(DISMISS_SELECTORS[i]);
            if (direct) return direct;
        }
        var buttons = root.querySelectorAll(
            'button, a[role="button"], .tlm-native-button, .ui-button');
        var visible = [];
        for (i = 0; i < buttons.length; i++) {
            if (isShowing(buttons[i])) visible.push(buttons[i]);
        }
        for (i = 0; i < visible.length; i++) {
            var label = (visible[i].textContent || '').trim().toLowerCase();
            if (!label) continue;
            if (X_GLYPHS.indexOf(label) !== -1) return visible[i];
            if (DISMISS_WORDS.indexOf(label) !== -1) return visible[i];
        }
        // A dialog with exactly ONE button is an acknowledgement (the
        // parametrizer error box has only "OK", the starter result only
        // "Continue!"); that button IS its way out, so pressing it is the
        // dismissal. With two or more buttons we never guess - a wrong guess
        // there could press something destructive.
        if (visible.length === 1) return visible[0];
        return null;
    }

    /**
     * Dismiss ONE dialog exactly the way its own Cancel/X would.
     * Returns TRUE when something was dismissed.
     */
    function dismissDialog(el) {
        if (!el) return false;

        // ---- SEALED => INVULNERABLE. Checked FIRST, before every path. ----
        // Angela, 2026-08-16: *"make the Check for updates dialog invulnerable
        // to Esc (MUST IGNORE EVERY ESCAPE AND CLOSE OF ANY TYPE) while there
        // is a download in progress."*
        //
        // A dialog declares `el.tlmSealKey`; while that key is sealed NOTHING
        // here dismisses it - not Escape, not a synthesised click on its X, and
        // above all not the last-resort hide at the bottom of this function.
        // That hide is why the test has to be HERE and not inside
        // CloseUpdateDialog: a dialog whose X went missing would otherwise be
        // hidden by the fallback with the seal never consulted at all.
        var sealKey = el.tlmSealKey
            || (el.dataset ? el.dataset.tlmSealKey : '')
            || '';
        if (sealKey && isSealed(sealKey)) return false;

        var jq = window.jQuery;

        // jQuery UI: the widget's own close() IS the titlebar-X path, and it
        // works even when a module has hidden that X to force a choice.
        if (jq && jq.fn && jq.fn.dialog && el.classList.contains('ui-dialog')) {
            var content = el.querySelector('.ui-dialog-content');
            if (content) {
                try {
                    jq(content).dialog('close');
                    return true;
                } catch (err) { /* fall through to the generic paths */ }
            }
        }

        // Bootstrap: the instance owns the hide AND the backdrop teardown.
        var bs = window.bootstrap;
        if (bs && bs.Modal && bs.Modal.getInstance && el.classList.contains('modal')) {
            var inst = bs.Modal.getInstance(el);
            if (inst) {
                inst.hide();
                return true;
            }
        }

        // Native <dialog> that our own code opened.
        if (el.tagName === 'DIALOG' && typeof el.close === 'function') {
            el.close();
            return true;
        }

        // An explicit hook, for a dialog whose dismissal is a FUNCTION rather
        // than a button - the Catalog of prompts is the one such case in the
        // app (it also restores body.style.overflow, which a blind hide would
        // leave clamped, freezing the page's scroll).
        if (typeof el.tlmDismiss === 'function') {
            el.tlmDismiss();
            return true;
        }

        var control = findDismissControl(el);
        if (control) {
            control.click();      // a REAL click, so the dialog's handler runs
            return true;
        }

        // Last resort: a dialog that offers the user no way out at all (the
        // spinner overlays). Hiding beats trapping them, but say so - a dialog
        // reaching this line should get an X or an `el.tlmDismiss`.
        console.warn('dialog policy: no dismiss control on',
            el.id || el.className || el.tagName,
            '- hiding it. Give it an X, a Cancel, or an el.tlmDismiss().');
        el.style.display = 'none';
        return true;
    }

    /** Public: dismiss whatever dialog is on top. Returns TRUE if one was. */
    function dismissTopDialog() {
        return dismissDialog(topmostOpenDialog());
    }

    /**
     * Escape on a SEALED dialog: ignore it, but not INVISIBLY.
     *
     * Deliberately NOT a modal. `mayClose()` raises an explanatory notice, which
     * is right for a DELIBERATE click on the X - but wrong for a keystroke: hold
     * Escape and you would stack notice on notice, and each notice becomes the
     * new topmost dialog, so the next Escape dismisses the notice instead. The
     * dialog would look like it was fighting the user. A 600 ms shake says "not
     * this one" and costs nothing.
     */
    function nudgeSealed(el) {
        try {
            el.classList.remove('tlm-dlg-sealed-nudge');
            // Reading offsetWidth restarts the CSS animation; without it a
            // second Escape inside the same 600 ms does nothing visible.
            void el.offsetWidth;
            el.classList.add('tlm-dlg-sealed-nudge');
            window.setTimeout(function () {
                try { el.classList.remove('tlm-dlg-sealed-nudge'); } catch (err) { /* gone */ }
            }, 600);
        } catch (err) { /* a nudge must never break a sealed dialog */ }
    }

    document.addEventListener('keydown', function (ev) {
        if (ev.key !== 'Escape' && ev.key !== 'Esc') return;
        // Already handled by jQuery UI / Bootstrap / a native <dialog>, all of
        // which preventDefault() the keydown when they close on Escape.
        if (ev.defaultPrevented) return;
        var target = topmostOpenDialog();
        // No dialog open -> Escape belongs to the page. The ACP canvas hides
        // its agent tooltip with it and the avatar stops speaking; neither may
        // be stolen just because this module exists.
        if (!target) return;
        var dismissed = dismissDialog(target);
        // THE KEY IS CONSUMED EITHER WAY. A refusal means the dialog is SEALED,
        // and letting the event travel on would hand it to that module's own
        // document-level Escape handler, which would call its close function
        // again and raise a SECOND "please wait" notice for one keystroke.
        ev.preventDefault();
        // stopIMMEDIATEPropagation, not stopPropagation: several dialogs bind
        // their own Escape handler on `document` too (External MCPs, Contacts,
        // About/Update, the image preview). Without this, Escape on a
        // tlmConfirm raised OVER the External-MCPs dialog would dismiss the
        // confirm here and then let that module close the whole dialog
        // underneath it - two layers for one keystroke.
        ev.stopImmediatePropagation();
        if (!dismissed) nudgeSealed(target);
    });

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

    //: key -> the dialog element it protects, so a blocked keystroke can shake
    //: the RIGHT dialog even when it is not the topmost one.
    var sealedElements = Object.create(null);

    /** Mark `element` as belonging to seal `key`. Safe to call repeatedly. */
    function bindSeal(element, key) {
        if (!element || !key) return;
        try {
            element.tlmSealKey = key;
            sealedElements[key] = element;
        } catch (err) { /* a frozen node must never break sealing */ }
    }

    /**
     * Seal a key. While it is sealed `mayClose(key)` refuses, AND any dialog
     * bound to that key is invulnerable in `dismissDialog` - Escape included.
     *
     * The optional `element` binds the dialog to the key at the exact moment
     * the seal is taken, so the two can never drift apart. A dialog may also
     * bind itself by setting `el.tlmSealKey` when it opens; doing both is the
     * belt-and-braces the updater uses, because a dialog that is sealed but
     * NOT bound would still be dismissible by Escape.
     */
    function seal(key, message, element) {
        sealed[key] = message || 'This operation cannot be interrupted.';
        bindSeal(element, key);
    }

    function unseal(key) {
        delete sealed[key];
        // Drop the element too, or a dialog that was sealed once keeps a stale
        // reference for the life of the page.
        delete sealedElements[key];
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

    // ---- 5b. SEALED: swallow every close/reload keystroke we are ALLOWED to
    // Angela, 2026-08-16: *"blind the downloading dialog from Ctrl+F4 too"*.
    //
    // ⚠️ HONEST SPLIT, because half of these are NOT ours to block. Anyone
    // maintaining this must know which half they are looking at:
    //
    //   WE REALLY DO WIN (the browser delivers the keydown and honours
    //   preventDefault):  F5 · Ctrl+R · Ctrl+Shift+R · Ctrl+F5 · Alt+Left ·
    //   Alt+Right · Ctrl+F4 and Ctrl+W *in the browsers that deliver them*.
    //   Reload is the important one - it destroys the page and the dialog with
    //   it, and it is the accident a user is most likely to have.
    //
    //   WE CANNOT WIN, EVER, IN ANY WEB PAGE:  Alt+F4, the window's own X, and
    //   in Chrome specifically Ctrl+W / Ctrl+Shift+W / Ctrl+F4, which Chrome
    //   RESERVES and never delivers to the document. No API overrides that; a
    //   page that claims otherwise is lying. For those the only defence the
    //   platform offers is `beforeunload` below, which raises the browser's own
    //   "Leave site?" prompt - and the user may still confirm it.
    //
    // WHY THAT IS ACCEPTABLE ANYWAY: the update swap runs in an EXTERNAL
    // PowerShell process. A closed tab does not abort an update in flight; it
    // only costs the user the progress bar. So this guard is about preventing
    // an ACCIDENT, not about imprisoning anyone.
    function isSealedCloseKey(ev) {
        var key = ev.key || '';
        var ctrl = ev.ctrlKey || ev.metaKey;
        if (key === 'F5' || key === 'BrowserRefresh') return true;          // reload
        if (ctrl && (key === 'r' || key === 'R')) return true;              // reload
        if (ctrl && (key === 'w' || key === 'W')) return true;              // close tab
        if (ctrl && key === 'F4') return true;                              // close tab
        if (ev.altKey && key === 'F4') return true;                         // close window
        if (ev.altKey && (key === 'ArrowLeft' || key === 'ArrowRight')) return true;
        if (key === 'BrowserBack' || key === 'BrowserForward') return true;
        return false;
    }

    document.addEventListener('keydown', function (ev) {
        var key = anySealed();
        if (!key) return;                      // nothing sealed -> not our business
        if (!isSealedCloseKey(ev)) return;     // an ordinary key -> leave it alone
        ev.preventDefault();
        ev.stopImmediatePropagation();
        nudgeSealed(sealedElements[key] || topmostOpenDialog());
    }, true);   // CAPTURE: get there before any application shortcut handler.

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
    // Policy-compliant by construction: no outside-click dismissal, and
    // Escape === X === Cancel === false — a destructive action is never taken
    // because a dialog was dismissed. Fails OPEN to the native popup: an ugly
    // warning beats a lost one, exactly as acp-globals.js decided.
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

        // Escape === X === Cancel. It resolves with `dismissValue`, which is
        // FALSE for tlmConfirm - so a destructive action is never taken because
        // the user pressed Escape. Handled here rather than left to section 4
        // because the popup owns the screen and knows its own resolve value.
        host.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' || ev.key === 'Esc') {
                ev.preventDefault();
                ev.stopPropagation();
                _popupTeardown(host, onDone, opts.dismissValue);
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
        bindSeal: bindSeal,
        mayClose: mayClose,
        alert: tlmAlert,
        confirm: tlmConfirm,
        // Exported so the HEADED Playwright run can assert the rule directly,
        // and so any future keyboard surface (a "close all" command) dismisses
        // through the SAME path Escape uses instead of inventing a second one.
        topmostOpenDialog: topmostOpenDialog,
        dismissTopDialog: dismissTopDialog
    };
})();
