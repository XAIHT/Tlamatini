// ============================================================
// external_mcps_dialog.js — External ▸ MCPs menu
// ============================================================
//
//   OpenExternalMcpsDialog(event)
//     -- "Activate MCPs" dialog. Lists the external_mcps.json catalog as a
//        searchable checkbox grid capped at 5 active. Continue POSTs the
//        active set to /agent/external_mcps/activate/. The modal is viewport
//        bounded and centered; only the catalog panes scroll.
//
//   Drag-to-import (self-attaching IIFE below)
//     -- Drop an MCP `.json` (mcpServers shape) anywhere on the page to merge
//        it into the catalog via /agent/external_mcps/import/. Shows a
//        full-screen drop hint and a confirm() before saving (the file
//        carries an executable command — never imported silently).

const EXTERNAL_MCPS_MAX_ACTIVE = 5;
const EXTERNAL_MCPS_RENDER_LIMIT = 700;
let _externalMcpsKeydownHandler = null;

function _emxCsrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
}

function _emxDestroyLegacyJqueryDialog(dlg) {
    if (!window.jQuery || !window.jQuery.fn || !window.jQuery.fn.dialog) return;
    const $dlg = window.jQuery(dlg);
    if ($dlg.hasClass('ui-dialog-content')) {
        $dlg.dialog('destroy');
    }
}

function OpenExternalMcpsDialog(event) { // eslint-disable-line no-unused-vars
    if (event && event.preventDefault) event.preventDefault();
    const dlg = document.getElementById('external-mcps-dialog-message');
    if (!dlg) { console.error('external-mcps-dialog: container missing'); return; }
    _emxDestroyLegacyJqueryDialog(dlg);

    const listEl = document.getElementById('external-mcps-list');
    const sumEl = document.getElementById('external-mcps-sum');
    const chip = document.getElementById('external-mcps-chip');
    const warn = document.getElementById('external-mcps-warn');
    const search = document.getElementById('external-mcps-search');
    const legend = document.getElementById('external-mcps-legend');
    const closeBtn = document.getElementById('external-mcps-close');
    const cancelBtn = document.getElementById('external-mcps-cancel');
    const saveBtn = document.getElementById('external-mcps-continue');
    if (!listEl || !sumEl || !chip || !warn || !search || !legend ||
        !closeBtn || !cancelBtn || !saveBtn) return;

    let servers = [];
    let maxActive = EXTERNAL_MCPS_MAX_ACTIVE;
    let warnTimer = null;
    let isSaving = false;
    const activeCount = () => servers.filter(s => s.active).length;

    function renderLegend() {
        legend.textContent = 'Select up to ' + maxActive +
            ' services. Search filters the catalog; inactive services stay catalog-only.';
    }

    function statusClass(s) {
        const st = s.status || (s.connecting ? 'connecting' :
            (s.error ? 'error' :
                (s.active && s.tool_count === 0 ? 'no_tools' :
                    (s.active && s.tool_count ? 'ready' : 'inactive'))));
        if (st === 'ready') return 'emx-pill-ok';
        if (st === 'connecting' || st === 'pending') return 'emx-pill-warn';
        if (st === 'no_tools') return 'emx-pill-zero';
        if (st === 'error') return 'emx-pill-err';
        return 'emx-pill-muted';
    }

    function statusLabel(s) {
        if (s.status_label) return s.status_label;
        if (s.connecting) return 'connecting';
        if (s.error) return 'error';
        if (s.active && s.tool_count === 0) return '0 tools';
        if (s.active && s.tool_count) return 'ready';
        return 'inactive';
    }

    function diagnosticText(s) {
        return s.diagnostic || s.error || '';
    }

    function flash(msg) {
        warn.textContent = msg;
        if (warnTimer) clearTimeout(warnTimer);
        warnTimer = setTimeout(() => { warn.textContent = ''; }, 2400);
    }

    function listMessage(text) {
        const node = document.createElement('div');
        node.className = 'emx-empty';
        node.textContent = text;
        return node;
    }

    function renderList() {
        const q = (search.value || '').trim().toLowerCase();
        listEl.innerHTML = '';
        const shown = servers.filter(s =>
            ((s.display || '') + ' ' + (s.key || '') + ' ' +
                (s.command || '') + ' ' + (s.transport || '')).toLowerCase().includes(q));
        if (!shown.length) {
            listEl.appendChild(listMessage('No match.'));
            return;
        }
        const rendered = shown.slice(0, EXTERNAL_MCPS_RENDER_LIMIT);
        const fragment = document.createDocumentFragment();
        for (const s of rendered) {
            const row = document.createElement('div');
            row.className = 'emx-row' + (s.active ? ' on' : '');
            row.dataset.key = s.key;
            row.setAttribute('role', 'checkbox');
            row.setAttribute('aria-checked', s.active ? 'true' : 'false');
            row.tabIndex = 0;
            const tc = (s.tool_count === null || s.tool_count === undefined)
                ? '' : (s.tool_count + ' tools');
            const diag = diagnosticText(s);
            row.innerHTML =
                '<div class="emx-acc"></div>' +
                '<input type="checkbox" class="emx-cb"' +
                (s.active ? ' checked' : '') + '>' +
                '<div class="emx-info"><div class="emx-name"></div>' +
                '<div class="emx-desc"></div>' +
                (diag ? '<div class="emx-diag"></div>' : '') + '</div>' +
                '<div class="emx-badges">' +
                (tc ? '<span class="emx-badge"></span>' : '') +
                '<span class="emx-status"></span>' +
                '<span class="emx-trans"></span></div>' +
                '<button type="button" class="emx-del" title="Remove from catalog">' +
                '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
                '<path d="M9 3h6l1 2h4v2H4V5h4l1-2zm-3 6h12l-1 12H7L6 9zm4 2v8h2v-8h-2zm4 0v8h2v-8h-2z"/>' +
                '</svg></button>';
            row.querySelector('.emx-name').textContent = s.display;
            row.querySelector('.emx-desc').textContent =
                s.command || s.transport || 'configured server';
            const diagEl = row.querySelector('.emx-diag');
            if (diagEl) diagEl.textContent = diag;
            if (tc) row.querySelector('.emx-badge').textContent = tc;
            const statusEl = row.querySelector('.emx-status');
            statusEl.className = 'emx-status ' + statusClass(s);
            statusEl.textContent = statusLabel(s);
            row.querySelector('.emx-trans').textContent = s.transport || 'unknown';
            const cb = row.querySelector('.emx-cb');
            cb.setAttribute('aria-label', s.display);
            const delBtn = row.querySelector('.emx-del');
            if (delBtn) delBtn.setAttribute('aria-label', 'Remove ' + s.display + ' from catalog');
            fragment.appendChild(row);
        }
        if (shown.length > rendered.length) {
            fragment.appendChild(listMessage('Showing ' + rendered.length +
                ' of ' + shown.length + ' matches. Search to narrow the catalog.'));
        }
        listEl.appendChild(fragment);
    }

    function renderSum() {
        const active = servers.filter(s => s.active);
        sumEl.innerHTML = '';
        if (!active.length) {
            sumEl.innerHTML = '<tr><td class="empty" colspan="4">' +
                'No services active yet.</td></tr>';
            return;
        }
        for (const s of active) {
            const tr = document.createElement('tr');
            const tc = (s.tool_count === null || s.tool_count === undefined)
                ? '—' : s.tool_count;
            tr.innerHTML = '<td></td><td class="mono"></td>' +
                '<td class="mono"></td>' +
                '<td><span></span></td>';
            const tds = tr.querySelectorAll('td');
            tds[0].textContent = s.display;
            tds[1].textContent = tc;
            tds[2].textContent = s.transport || 'unknown';
            const pill = tr.querySelector('span');
            pill.className = statusClass(s);
            pill.textContent = statusLabel(s);
            const diag = diagnosticText(s);
            if (diag) {
                const diagRow = document.createElement('tr');
                diagRow.className = 'emx-sum-diag';
                diagRow.innerHTML = '<td colspan="4"></td>';
                diagRow.querySelector('td').textContent = diag;
                sumEl.appendChild(tr);
                sumEl.appendChild(diagRow);
                continue;
            }
            sumEl.appendChild(tr);
        }
    }

    function renderChip() {
        const c = activeCount();
        chip.textContent = c + ' / ' + maxActive + ' active';
        chip.classList.toggle('full', c >= maxActive);
    }

    function renderAll() { renderList(); renderSum(); renderChip(); }

    function toggleServer(key) {
        const s = servers.find(x => x.key === key);
        if (!s) return;
        if (!s.active && activeCount() >= maxActive) {
            flash('You can run ' + maxActive +
                ' at once — switch one off first.');
            return;
        }
        s.active = !s.active;
        warn.textContent = '';
        renderAll();
    }

    function removeServer(key) {
        const s = servers.find(x => x.key === key);
        if (!s) return;
        const label = s.display || key;
        if (!confirm('Remove "' + label + '" from the catalog?\n\n' +
            'This deletes the saved server config. You can add it back any time by ' +
            'dropping its .json onto the page again.')) {
            return;
        }
        fetch('/agent/external_mcps/remove/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': _emxCsrf(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ keys: [key] })
        }).then(r => r.json()).then(d => {
            if (d.ok) {
                servers = servers.filter(x => x.key !== key);
                renderAll();
                flash('Removed "' + label + '" from the catalog.');
            } else {
                flash('Remove failed: ' + (d.error || 'unknown error'));
            }
        }).catch(err => flash('Remove failed: ' + err));
    }

    listEl.onclick = (e) => {
        const delBtn = e.target.closest('.emx-del');
        if (delBtn) {
            e.stopPropagation();
            const delRow = delBtn.closest('.emx-row');
            if (delRow) removeServer(delRow.dataset.key);
            return;
        }
        const row = e.target.closest('.emx-row');
        if (!row) return;
        toggleServer(row.dataset.key);
    };
    listEl.onkeydown = (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        if (e.target.closest('.emx-del')) return; // let the delete button handle its own keys
        const row = e.target.closest('.emx-row');
        if (!row) return;
        e.preventDefault();
        toggleServer(row.dataset.key);
    };
    search.value = '';
    search.oninput = () => {
        listEl.scrollTop = 0;
        renderList();
    };

    function setSaving(nextSaving) {
        isSaving = nextSaving;
        saveBtn.disabled = nextSaving;
        saveBtn.textContent = nextSaving ? 'Saving...' : 'Continue';
    }

    function closeDialog() {
        if (warnTimer) clearTimeout(warnTimer);
        if (_externalMcpsKeydownHandler) {
            document.removeEventListener('keydown', _externalMcpsKeydownHandler);
            _externalMcpsKeydownHandler = null;
        }
        dlg.classList.remove('is-open');
        dlg.hidden = true;
        document.body.classList.remove('emx-dialog-open');
    }

    function focusableElements() {
        return Array.from(dlg.querySelectorAll(
            'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )).filter(el => el.getClientRects().length > 0);
    }

    function onDialogKeydown(e) {
        if (e.key === 'Escape') {
            e.preventDefault();
            closeDialog();
            return;
        }
        if (e.key !== 'Tab') return;
        const focusable = focusableElements();
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
            e.preventDefault();
            first.focus();
        }
    }

    function openDialog() {
        if (_externalMcpsKeydownHandler) {
            document.removeEventListener('keydown', _externalMcpsKeydownHandler);
        }
        dlg.hidden = false;
        dlg.classList.add('is-open');
        document.body.classList.add('emx-dialog-open');
        _externalMcpsKeydownHandler = onDialogKeydown;
        document.addEventListener('keydown', _externalMcpsKeydownHandler);
        window.setTimeout(() => search.focus(), 0);
    }

    closeBtn.onclick = closeDialog;
    cancelBtn.onclick = closeDialog;
    dlg.onclick = (e) => {
        if (e.target === dlg) closeDialog();
    };

    listEl.innerHTML = '';
    listEl.appendChild(listMessage('Loading...'));
    sumEl.innerHTML = '';
    chip.textContent = '';
    warn.textContent = '';
    setSaving(false);
    renderLegend();
    openDialog();

    fetch('/agent/external_mcps/', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(payload => {
            maxActive = Number(payload.max_active) || EXTERNAL_MCPS_MAX_ACTIVE;
            servers = (payload.servers || []).map(s => Object.assign({}, s));
            renderLegend();
            renderAll();
        })
        .catch(err => {
            listEl.innerHTML = '';
            listEl.appendChild(listMessage('Load failed: ' + err));
        });

    function saveActive() {
        if (isSaving) return;
        setSaving(true);
        const active = servers.filter(s => s.active).map(s => s.key);
        fetch('/agent/external_mcps/activate/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': _emxCsrf(),
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ active })
        }).then(r => r.json()).then(d => {
            if (d.ok) {
                closeDialog();
            } else {
                setSaving(false);
                flash('Save failed: ' + (d.error || 'unknown error'));
            }
        }).catch(err => {
            setSaving(false);
            flash('Save failed: ' + err);
        });
    }
    saveBtn.onclick = saveActive;
}

// ----------------------------------------------------------------
// Drag-to-import an MCP .json file anywhere onto the page
// ----------------------------------------------------------------

(function () {
    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }
    function hasFiles(e) {
        return e.dataTransfer &&
            Array.from(e.dataTransfer.types || []).indexOf('Files') !== -1;
    }
    ready(function () {
        let overlay = document.getElementById('emx-drop-overlay');
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'emx-drop-overlay';
            overlay.className = 'emx-drop-overlay';
            overlay.textContent = 'Drop an MCP .json to add it to the catalog';
            document.body.appendChild(overlay);
        }
        let depth = 0;
        document.addEventListener('dragenter', function (e) {
            if (!hasFiles(e)) return;
            depth += 1;
            overlay.classList.add('show');
        });
        document.addEventListener('dragover', function (e) {
            if (!hasFiles(e)) return;
            e.preventDefault();
        });
        document.addEventListener('dragleave', function (e) {
            if (!hasFiles(e)) return;
            depth = Math.max(0, depth - 1);
            if (depth === 0) overlay.classList.remove('show');
        });
        document.addEventListener('drop', function (e) {
            if (!hasFiles(e)) return;
            e.preventDefault();
            depth = 0;
            overlay.classList.remove('show');
            const file = e.dataTransfer.files && e.dataTransfer.files[0];
            if (!file || !/\.json$/i.test(file.name)) return;
            const reader = new FileReader();
            reader.onload = function () {
                let parsed;
                try {
                    const text = String(reader.result || '').replace(/^\uFEFF/, '').trim();
                    parsed = JSON.parse(text);
                } catch (err) {
                    alert('Not valid JSON: ' + err);
                    return;
                }
                let map = (parsed && parsed.mcpServers) ? parsed.mcpServers : null;
                if (!map && parsed && parsed.servers && typeof parsed.servers === 'object') {
                    map = parsed.servers;
                }
                if (!map && parsed && typeof parsed === 'object' &&
                    (parsed.command || parsed.url || parsed.endpoint || parsed.sseUrl ||
                        parsed.streamableHttpUrl || parsed.wsUrl || parsed.websocketUrl ||
                        (parsed.host && parsed.port))) {
                    const inferredName = (parsed.name || file.name.replace(/\.json$/i, '') || 'Imported_MCP')
                        .toString()
                        .trim()
                        .replace(/[^\w.-]+/g, '_') || 'Imported_MCP';
                    map = {};
                    map[inferredName] = parsed;
                }
                if (!map && parsed && typeof parsed === 'object') {
                    map = parsed;
                }
                const names = (map && typeof map === 'object') ? Object.keys(map) : [];
                if (!names.length) {
                    alert('No mcpServers found in ' + file.name);
                    return;
                }
                if (!confirm('Add ' + names.length + ' MCP server(s) to the catalog?\n\n' +
                    names.join(', '))) {
                    return;
                }
                fetch('/agent/external_mcps/import/', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: {
                        'X-CSRFToken': _emxCsrf(),
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ mcpServers: map })
                }).then(r => r.json()).then(d => {
                    if (d.ok) {
                        const added = (d.added || []).length;
                        const updated = (d.updated || []).length;
                        alert('Catalog updated — ' + added + ' added, ' + updated +
                            ' updated.\nOpen External ▸ MCPs to activate them.');
                    } else {
                        alert('Import failed: ' + (d.error || 'unknown error'));
                    }
                }).catch(err => alert('Import failed: ' + err));
            };
            reader.readAsText(file);
        });
    });
})();
