/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela López Mendoza.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// ============================================================
// checkbox_bulk_toggle.js  –  SPACE-bar bulk check/uncheck of every
// checkbox the current text selection covers.
//
// WHY IT EXISTS
//   The Configure Mcps / Tools / Agents / Skills / External-MCPs dialogs
//   list dozens of checkboxes. Turning 20 of them off used to cost 20
//   clicks. Now: swipe the mouse across the labels you care about (an
//   ordinary text selection) and hit SPACE — every checkbox the
//   selection touches flips in ONE keystroke.
//
// THE RULE (deliberately asymmetric, so it is predictable)
//   ANY selected checkbox CHECKED  ->  uncheck them ALL
//   ALL of them already unchecked  ->  check them ALL
//   So the first SPACE over a checked (or mixed) block always CLEARS it,
//   which is what a human means by "unselect these". Press SPACE again
//   to turn the same block back on.
//
// WHY IT IS SAFE
//   * It only acts when there is a NON-COLLAPSED text selection that
//     STRICTLY overlaps a checkbox's own label/row. No selection ->
//     the browser's native SPACE behaviour is untouched.
//   * It never fires inside a text input / textarea / select /
//     contenteditable, so typing a space always types a space.
//   * It toggles with checkbox.click() — a REAL click — so every
//     existing click/change handler still runs (state persistence, the
//     External-MCPs 5-server cap, the ACP canvas config dialogs, ...).
//   * Lists that RE-RENDER themselves on every toggle (the External-MCPs
//     catalog rebuilds all its rows from its model) are handled by
//     re-resolving each checkbox immediately before it is clicked; a row
//     that vanished is skipped, never clicked while detached.
//   * Every step is wrapped in try/catch: a failure degrades to "SPACE
//     did nothing", never to a broken page.
//
// This is a self-contained IIFE that declares NO cross-file globals (the
// same shape as chat_image_paste.js), so it cannot trip the const-poison
// contract and needs no eslint.config.mjs globals entry.
// ============================================================

(function () {
    'use strict';

    // Range.compareBoundaryPoints() constants, spelled out locally so this
    // module needs no `Range` global of its own.
    const START_TO_END = 1;   // compares THIS range's END with the other's START
    const END_TO_START = 3;   // compares THIS range's START with the other's END

    const MAX_ROW_HOPS = 4;   // how far up from the <input> we look for its text row
    const PULSE_MS = 420;     // how long the teal confirmation ring stays on
    const ACCENT = '#55BBAA'; // the app-wide Tlamatini teal (DIALOG_BUTTON_CSS)

    const HINT_TEXT = 'Tip: select several labels with the mouse and press ' +
        'SPACE to check / uncheck all of them at once.';

    // Widgets that already OWN the space bar for their own activation and
    // must keep it. (The External-MCPs / Contacts rows also bind Space, but
    // those we deliberately take over — see the capture-phase note below.)
    const SPACE_OWNER_SELECTOR = '#tlm-avatar-dock';

    // ------------------------------------------------------------------
    // Guards
    // ------------------------------------------------------------------

    /** True for any field where SPACE must keep typing a space. */
    function isTextEntry(el) {
        if (!el || el.nodeType !== 1) return false;
        if (el.isContentEditable) return true;
        const tag = (el.tagName || '').toLowerCase();
        if (tag === 'textarea' || tag === 'select') return true;
        if (tag !== 'input') return false;
        const type = (el.getAttribute('type') || 'text').toLowerCase();
        return ['checkbox', 'radio', 'button', 'submit', 'reset',
            'file', 'image', 'range', 'color'].indexOf(type) === -1;
    }

    /** Escape a value so it is safe inside a "double-quoted" attribute selector. */
    function attrEscape(value) {
        return String(value).replace(/(["\\])/g, '\\$1');
    }

    // ------------------------------------------------------------------
    // Selection geometry
    // ------------------------------------------------------------------

    /**
     * STRICT overlap between the live selection and a node's contents.
     * Strict means a zero-length touch at a boundary does NOT count, so
     * selecting label A never drags in the first character of label B.
     */
    function selectionOverlaps(selection, node) {
        let nodeRange;
        try {
            nodeRange = document.createRange();
            nodeRange.selectNodeContents(node);
        } catch (e) {
            return false;
        }
        for (let i = 0; i < selection.rangeCount; i++) {
            let r;
            try { r = selection.getRangeAt(i); } catch (e) { continue; }
            if (!r || r.collapsed) continue;
            try {
                // r.start < node.end   &&   r.end > node.start
                if (r.compareBoundaryPoints(END_TO_START, nodeRange) < 0 &&
                    r.compareBoundaryPoints(START_TO_END, nodeRange) > 0) {
                    return true;
                }
            } catch (e) { /* ranges in different documents - ignore */ }
        }
        return false;
    }

    /**
     * The element(s) carrying a checkbox's VISIBLE TEXT — what the user
     * actually drags the mouse over. A checkbox is a replaced element with
     * no text of its own, so a selection can never touch it directly.
     *
     * The "owns exactly one checkbox" test is the important guard: without
     * it a whole list container could be mistaken for a single row, and any
     * selection would then toggle every checkbox in the dialog.
     */
    function textRegionsFor(checkbox) {
        const regions = [];
        const own = checkbox.closest ? checkbox.closest('label') : null;
        if (own) regions.push(own);
        if (checkbox.id) {
            try {
                const bound = document.querySelector(
                    'label[for="' + attrEscape(checkbox.id) + '"]');
                if (bound && regions.indexOf(bound) === -1) regions.push(bound);
            } catch (e) { /* exotic id - ignore */ }
        }
        let node = checkbox.parentElement;
        let hops = 0;
        while (node && hops < MAX_ROW_HOPS) {
            if (node.querySelectorAll('input[type="checkbox"]').length !== 1) break;
            if ((node.textContent || '').trim()) {
                if (regions.indexOf(node) === -1) regions.push(node);
                break;
            }
            node = node.parentElement;
            hops++;
        }
        return regions;
    }

    /**
     * Late-binding lookup so a self-re-rendering list can still be driven:
     * the checkbox is resolved again right before it is clicked.
     */
    function makeResolver(checkbox) {
        if (checkbox.id) {
            const id = checkbox.id;
            return function () { return document.getElementById(id); };
        }
        let node = checkbox.parentElement;
        let hops = 0;
        while (node && hops < MAX_ROW_HOPS) {
            const key = node.getAttribute ? node.getAttribute('data-key') : null;
            if (key) {
                const sel = '[data-key="' + attrEscape(key) + '"] input[type="checkbox"]';
                return function () {
                    try { return document.querySelector(sel); } catch (e) { return null; }
                };
            }
            node = node.parentElement;
            hops++;
        }
        return function () { return checkbox.isConnected ? checkbox : null; };
    }

    // ------------------------------------------------------------------
    // Collect + apply
    // ------------------------------------------------------------------

    /** Every enabled checkbox whose own label/row the selection overlaps. */
    function collectTargets(selection) {
        const out = [];
        let all;
        try {
            all = document.querySelectorAll('input[type="checkbox"]');
        } catch (e) {
            return out;
        }
        for (let i = 0; i < all.length; i++) {
            const cb = all[i];
            if (cb.disabled) continue;
            const regions = textRegionsFor(cb);
            for (let j = 0; j < regions.length; j++) {
                if (selectionOverlaps(selection, regions[j])) {
                    out.push({ checkbox: cb, resolve: makeResolver(cb) });
                    break;
                }
            }
        }
        return out;
    }

    function applyToggle(targets) {
        let desired = true;
        for (let i = 0; i < targets.length; i++) {
            if (targets[i].checkbox.checked) { desired = false; break; }
        }
        let changed = 0;
        let skipped = 0;
        for (let k = 0; k < targets.length; k++) {
            let live;
            try { live = targets[k].resolve(); } catch (e) { live = null; }
            if (!live && targets[k].checkbox.isConnected) live = targets[k].checkbox;
            if (!live || live.disabled) { skipped++; continue; }
            if (!!live.checked === desired) continue;   // already where we want it
            try {
                live.click();   // a REAL click, so every existing handler runs
                changed++;
                pulse(live);
            } catch (e) {
                skipped++;
            }
        }
        return {
            desired: desired, changed: changed,
            skipped: skipped, total: targets.length
        };
    }

    /** A short teal ring on each row we just flipped. Cosmetic and fail-safe. */
    function pulse(checkbox) {
        const regions = textRegionsFor(checkbox);
        const el = regions.length ? regions[regions.length - 1] : checkbox;
        if (!el || !el.style) return;
        try {
            const prevShadow = el.style.boxShadow;
            const prevTransition = el.style.transition;
            el.style.transition = 'box-shadow 120ms ease-out';
            el.style.boxShadow = '0 0 0 2px ' + ACCENT;
            window.setTimeout(function () {
                try {
                    el.style.boxShadow = prevShadow;
                    el.style.transition = prevTransition;
                } catch (e) { /* row already gone - fine */ }
            }, PULSE_MS);
        } catch (e) { /* cosmetic only */ }
    }

    // ------------------------------------------------------------------
    // The SPACE handler
    // ------------------------------------------------------------------

    function onKeyDown(event) {
        if (!event) return;
        if (event.key !== ' ' && event.key !== 'Spacebar' && event.keyCode !== 32) return;
        if (event.ctrlKey || event.metaKey || event.altKey) return;
        if (event.defaultPrevented) return;
        if (isTextEntry(event.target) || isTextEntry(document.activeElement)) return;
        if (event.target && event.target.closest &&
            event.target.closest(SPACE_OWNER_SELECTOR)) return;

        let selection;
        try { selection = window.getSelection(); } catch (e) { return; }
        if (!selection || !selection.rangeCount || selection.isCollapsed) return;

        const targets = collectTargets(selection);
        if (!targets.length) return;   // nothing selected -> native SPACE, untouched

        event.preventDefault();        // no page scroll
        event.stopPropagation();       // no second toggle from a per-list key handler

        const result = applyToggle(targets);
        console.log('--- [BULK-TOGGLE] ' + result.changed + '/' + result.total +
            ' checkbox(es) ' + (result.desired ? 'checked' : 'unchecked') +
            (result.skipped ? ' (' + result.skipped + ' skipped)' : ''));
    }

    // Capture phase: we must run BEFORE a list's own keydown handler so the
    // same SPACE can never be counted twice. We only ever stop propagation
    // for a SPACE we actually consumed, so Escape / Tab / Enter / Ctrl+Z and
    // every other key reach their handlers exactly as before.
    document.addEventListener('keydown', onKeyDown, true);

    // ------------------------------------------------------------------
    // Discoverability: one muted hint line inside any jQuery-UI dialog that
    // shows more than one checkbox. Purely cosmetic, fully fail-safe.
    // ------------------------------------------------------------------

    const HINT_CLASS = 'tlm-bulk-toggle-hint';

    function injectHint(dialogEl) {
        try {
            if (!dialogEl || !dialogEl.querySelector) return;
            if (dialogEl.querySelector('.' + HINT_CLASS)) return;
            if (dialogEl.querySelectorAll('input[type="checkbox"]').length < 2) return;
            const hint = document.createElement('div');
            hint.className = HINT_CLASS;
            hint.textContent = HINT_TEXT;
            hint.style.cssText =
                'margin:8px 0 0;font-size:0.82em;opacity:0.75;font-style:italic;';
            dialogEl.appendChild(hint);
        } catch (e) { /* cosmetic only */ }
    }

    if (typeof window.jQuery === 'function') {
        window.jQuery(document).on('dialogopen', function (event) {
            // Let the dialog's own open: handler build its list first.
            window.setTimeout(function () { injectHint(event.target); }, 0);
        });
    }
}());
