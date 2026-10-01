/*
 * chat_table_contrast.js - every table in an answer stays READABLE
 * (Angela Lopez Mendoza, 2026-10-01).
 *
 * Tlamatini renders the HTML tables a model writes.  A model that paints the
 * table WHITE but gives its cells no text colour leaves them inheriting the
 * chat bubble's near-white text: white on white.  Measured on qwen2.5:latest
 * in the visible Compact-mode test - the planets table rendered, and nobody
 * could read it.  Bigger models do it too, less often.
 *
 * After an answer is drawn, every cell of every answer table is measured:
 * its own text colour against the background actually behind it (the first
 * opaque background found walking up the page).  Below a 3:1 contrast ratio
 * the cell gets dark text on a light background, light text on a dark one.
 * Nothing else is touched - a readable table keeps every colour the model
 * chose.
 *
 * Exec Report tables have their own design and are never touched.  A cell
 * whose background is a gradient or an image is left alone: its colour
 * cannot be measured, and guessing could make it worse.  Fail-open: an
 * error here costs one fix-up, never the answer.  Declares no globals.
 */
(function () {
    'use strict';

    const DARK_TEXT = '#0f172a';
    const LIGHT_TEXT = '#f8fafc';
    const MIN_RATIO = 3.0;
    const CELLS = 'td, th, caption';

    function parseColor(value) {
        const m = /rgba?\(([^)]+)\)/.exec(value || '');
        if (!m) {
            return null;
        }
        const p = m[1].split(',').map(function (x) { return parseFloat(x); });
        return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }

    function luminance(c) {
        function channel(v) {
            v /= 255;
            return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
        }
        return 0.2126 * channel(c.r) + 0.7152 * channel(c.g) + 0.0722 * channel(c.b);
    }

    function contrast(a, b) {
        const x = luminance(a);
        const y = luminance(b);
        return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
    }

    // The background really behind an element, or null when it cannot be known.
    function backgroundBehind(el) {
        for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
            const style = window.getComputedStyle(node);
            if (style.backgroundImage && style.backgroundImage !== 'none') {
                return null;
            }
            const c = parseColor(style.backgroundColor);
            if (c && c.a >= 0.5) {
                return c;
            }
        }
        return null;
    }

    function fixTable(table) {
        if (!table || table.closest('.exec-report-table, .exec-report')) {
            return;
        }
        const cells = table.querySelectorAll(CELLS);
        for (let i = 0; i < cells.length; i++) {
            try {
                const cell = cells[i];
                const bg = backgroundBehind(cell);
                const fg = parseColor(window.getComputedStyle(cell).color);
                if (!bg || !fg || contrast(fg, bg) >= MIN_RATIO) {
                    continue;
                }
                cell.style.color = luminance(bg) > 0.35 ? DARK_TEXT : LIGHT_TEXT;
            } catch (cellErr) {
                // one unreadable cell must never stop the rest of the table
            }
        }
    }

    function fixWithin(root) {
        try {
            if (!root || root.nodeType !== 1) {
                return;
            }
            if (root.tagName === 'TABLE') {
                fixTable(root);
                return;
            }
            let tables = root.querySelectorAll('.bot-message table');
            if (!tables.length && root.closest && root.closest('.bot-message')) {
                tables = root.querySelectorAll('table');
            }
            for (let i = 0; i < tables.length; i++) {
                fixTable(tables[i]);
            }
        } catch (err) {
            // fail-open
        }
    }

    function start() {
        const log = document.getElementById('chat-log');
        if (!log) {
            return;
        }
        fixWithin(log);                                   // the history already drawn
        if (typeof MutationObserver !== 'function') {
            return;
        }
        let pending = [];
        let scheduled = false;
        new MutationObserver(function (records) {
            records.forEach(function (rec) {
                rec.addedNodes.forEach(function (n) {
                    if (n.nodeType === 1) {
                        pending.push(n);
                    }
                });
            });
            if (!scheduled && pending.length) {
                scheduled = true;
                window.requestAnimationFrame(function () {
                    const batch = pending;
                    pending = [];
                    scheduled = false;
                    batch.forEach(fixWithin);
                });
            }
        }).observe(log, { childList: true, subtree: true });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
}());
