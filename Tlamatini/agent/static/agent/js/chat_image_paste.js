/* ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove
 *
 * chat_image_paste.js — screenshots into the chat box.
 *
 *   IMPR PANT (PrtScn) anywhere  →  Alt+Tab to Tlamatini  →  Ctrl+V
 *
 * The browser hands us the clipboard bitmap as a blob, so no Win32 clipboard
 * reading is needed. We POST it to /agent/paste_image/, which writes it to
 * <app>/Temp as image_<timestamp>.jpg (frozen/source resolved by path_guard),
 * then we splice the absolute path into the chat box AT THE CARET the user
 * left behind, and show a thumbnail chip above the input.
 *
 * Dropping image files onto the chat panel does exactly the same thing.
 *
 * Self-contained IIFE: it declares NO cross-file globals (see the const-poison
 * contract in docs/claude/frontend.md — this module owns all its state).
 */
(function () {
    'use strict';

    const ENDPOINT = '/agent/paste_image/';
    const MAX_BYTES = 25 * 1024 * 1024;

    // The caret the user left in the chat box before Alt+Tabbing away. The
    // textarea loses focus on Alt+Tab, so selectionStart alone is not enough —
    // we remember it on every interaction.
    let lastCaret = null;
    let dragDepth = 0;

    function chatInput() {
        return document.getElementById('chat-message-input');
    }

    function chipsHost() {
        return document.getElementById('chat-image-chips');
    }

    function dropOverlay() {
        return document.getElementById('chat-drop-overlay');
    }

    /* ── caret tracking ─────────────────────────────────────────────── */

    function rememberCaret() {
        const input = chatInput();
        if (input && typeof input.selectionStart === 'number') {
            lastCaret = input.selectionStart;
        }
    }

    function insertPathAtCaret(path) {
        const input = chatInput();
        if (!input || !path) return;

        const value = input.value;
        let position = value.length;
        if (document.activeElement === input && typeof input.selectionStart === 'number') {
            position = input.selectionStart;
        } else if (typeof lastCaret === 'number' && lastCaret >= 0 && lastCaret <= value.length) {
            position = lastCaret;
        }

        const before = value.slice(0, position);
        const after = value.slice(position);
        const lead = (before.length > 0 && !/\s$/.test(before)) ? ' ' : '';
        const trail = (after.length > 0 && !/^\s/.test(after)) ? ' ' : '';
        const chunk = lead + path + trail;

        input.value = before + chunk + after;
        const caret = before.length + chunk.length;
        lastCaret = caret;
        input.focus();
        try {
            input.setSelectionRange(caret, caret);
        } catch (e) {
            /* setSelectionRange is unavailable on some input types — harmless */
        }
        // Let the auto-grow / submit-enable listeners react to the new value.
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    function removePathFromInput(path) {
        const input = chatInput();
        if (!input || !path || input.value.indexOf(path) === -1) return;
        input.value = input.value
            .split(path).join('')
            .replace(/[ \t]{2,}/g, ' ')
            .replace(/^[ \t]+|[ \t]+$/g, '');
        lastCaret = input.value.length;
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }

    /* ── thumbnail chips ────────────────────────────────────────────── */

    function syncChipsVisibility() {
        const host = chipsHost();
        if (!host) return;
        host.classList.toggle('has-content', host.childElementCount > 0);
    }

    function addThumbnailChip(objectUrl, info) {
        const host = chipsHost();
        if (!host) return;

        const chip = document.createElement('div');
        chip.className = 'chat-img-chip';
        chip.title = info.path;

        const thumb = document.createElement('img');
        thumb.className = 'chat-img-chip-thumb';
        thumb.src = objectUrl;
        thumb.alt = info.filename || 'screenshot';

        const meta = document.createElement('div');
        meta.className = 'chat-img-chip-meta';

        const name = document.createElement('span');
        name.className = 'chat-img-chip-name';
        name.textContent = info.filename || 'screenshot.jpg';

        const dims = document.createElement('span');
        dims.className = 'chat-img-chip-dims';
        const kilobytes = Math.max(1, Math.round((info.bytes || 0) / 1024));
        dims.textContent = `${info.width}×${info.height} · ${kilobytes} KB`;

        meta.appendChild(name);
        meta.appendChild(dims);

        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'chat-img-chip-close';
        remove.title = 'Remove this image and its path from the message';
        remove.textContent = '×';
        remove.addEventListener('click', function () {
            removePathFromInput(info.path);
            try {
                URL.revokeObjectURL(objectUrl);
            } catch (e) {
                /* already revoked — harmless */
            }
            chip.remove();
            syncChipsVisibility();
        });

        chip.appendChild(thumb);
        chip.appendChild(meta);
        chip.appendChild(remove);
        host.appendChild(chip);
        syncChipsVisibility();
    }

    function showChipError(message) {
        const host = chipsHost();
        if (!host) return;
        const chip = document.createElement('div');
        chip.className = 'chat-img-chip chat-img-chip-error';
        chip.textContent = message;
        host.appendChild(chip);
        syncChipsVisibility();
        setTimeout(function () {
            chip.remove();
            syncChipsVisibility();
        }, 6000);
    }

    /* ── upload ─────────────────────────────────────────────────────── */

    function csrf() {
        return (typeof getCsrfToken === 'function') ? getCsrfToken() : '';
    }

    function uploadImage(file) {
        if (!file || !/^image\//i.test(file.type || '')) return;
        if (file.size > MAX_BYTES) {
            showChipError('That image is larger than 25 MB — Tlamatini did not save it.');
            return;
        }

        const objectUrl = URL.createObjectURL(file);
        const form = new FormData();
        form.append('image', file, file.name || 'clipboard.png');
        form.append('csrfmiddlewaretoken', csrf());

        fetch(ENDPOINT, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrf() },
            body: form
        }).then(function (response) {
            return response.json()
                .catch(function () { return {}; })
                .then(function (data) { return { ok: response.ok, status: response.status, data: data }; });
        }).then(function (result) {
            const data = result.data || {};
            if (!result.ok || !data.success || !data.path) {
                URL.revokeObjectURL(objectUrl);
                showChipError(data.message || `Tlamatini could not save the image (HTTP ${result.status}).`);
                return;
            }
            insertPathAtCaret(data.path);
            addThumbnailChip(objectUrl, data);
        }).catch(function (error) {
            URL.revokeObjectURL(objectUrl);
            showChipError('Tlamatini could not be reached to save the image.');
            console.error('--- [chat-image] upload failed:', error);
        });
    }

    function imagesFromClipboard(clipboardData) {
        const images = [];
        if (!clipboardData || !clipboardData.items) return images;
        for (let i = 0; i < clipboardData.items.length; i++) {
            const item = clipboardData.items[i];
            if (item.kind === 'file' && /^image\//i.test(item.type || '')) {
                const file = item.getAsFile();
                if (file) images.push(file);
            }
        }
        return images;
    }

    function dragCarriesFiles(event) {
        const transfer = event.dataTransfer;
        if (!transfer || !transfer.types) return false;
        for (let i = 0; i < transfer.types.length; i++) {
            if (transfer.types[i] === 'Files') return true;
        }
        return false;
    }

    /* ── wiring ─────────────────────────────────────────────────────── */

    function init() {
        const input = chatInput();
        if (input) {
            ['click', 'keyup', 'select', 'input', 'blur'].forEach(function (name) {
                input.addEventListener(name, rememberCaret);
            });
        }

        // Ctrl+V anywhere on the page: after Alt+Tab the focus is on <body>, so
        // listening on the textarea alone would miss Angela's exact flow. Plain
        // text pastes fall through untouched — we only act on image blobs.
        document.addEventListener('paste', function (event) {
            const images = imagesFromClipboard(event.clipboardData);
            if (!images.length) return;
            event.preventDefault();
            images.forEach(uploadImage);
        });

        // Drag-and-drop is scoped to the chat column on purpose: the External-MCP
        // dialog installs its own document-level .json drop handler, and the ACP
        // canvas has one too. Staying inside #main-chat-container keeps them apart.
        const zone = document.getElementById('main-chat-container');
        if (!zone) return;

        zone.addEventListener('dragenter', function (event) {
            if (!dragCarriesFiles(event)) return;
            event.preventDefault();
            dragDepth += 1;
            const overlay = dropOverlay();
            if (overlay) overlay.classList.add('show');
        });

        zone.addEventListener('dragover', function (event) {
            if (!dragCarriesFiles(event)) return;
            event.preventDefault();
            if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
        });

        zone.addEventListener('dragleave', function (event) {
            if (!dragCarriesFiles(event)) return;
            dragDepth = Math.max(0, dragDepth - 1);
            if (dragDepth === 0) {
                const overlay = dropOverlay();
                if (overlay) overlay.classList.remove('show');
            }
        });

        zone.addEventListener('drop', function (event) {
            if (!dragCarriesFiles(event)) return;
            event.preventDefault();
            dragDepth = 0;
            const overlay = dropOverlay();
            if (overlay) overlay.classList.remove('show');

            const files = Array.prototype.slice.call((event.dataTransfer && event.dataTransfer.files) || []);
            const images = files.filter(function (file) { return /^image\//i.test(file.type || ''); });
            if (!images.length) {
                showChipError('Only image files can be dropped into the chat.');
                return;
            }
            images.forEach(uploadImage);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
