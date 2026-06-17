// ============================================================
// external_mcps_dialog.js — External ▸ MCPs menu
// ============================================================
//
//   OpenExternalMcpsDialog(event)
//     -- "Activate MCPs" dialog. Lists the external_mcps.json catalog as a
//        searchable checkbox grid capped at 5 active. Continue POSTs the
//        active set to /agent/external_mcps/activate/. Mirrors the dark
//        tools/skills dialog identity (jQuery-UI .ui-dialog + teal buttons).
//
//   Drag-to-import (self-attaching IIFE below)
//     -- Drop an MCP `.json` (mcpServers shape) anywhere on the page to merge
//        it into the catalog via /agent/external_mcps/import/. Shows a
//        full-screen drop hint and a confirm() before saving (the file
//        carries an executable command — never imported silently).

const EXTERNAL_MCPS_MAX_ACTIVE = 5;

function _emxCsrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
}

function OpenExternalMcpsDialog(event) { // eslint-disable-line no-unused-vars
    if (event && event.preventDefault) event.preventDefault();
    const dlg = document.getElementById('external-mcps-dialog-message');
    if (!dlg) { console.error('external-mcps-dialog: container missing'); return; }
    dlg.title = 'Activate MCPs';

    const listEl = document.getElementById('external-mcps-list');
    const sumEl = document.getElementById('external-mcps-sum');
    const chip = document.getElementById('external-mcps-chip');
    const warn = document.getElementById('external-mcps-warn');
    const search = document.getElementById('external-mcps-search');
    const legend = document.getElementById('external-mcps-legend');
    if (!listEl || !sumEl || !chip || !warn || !search || !legend) return;

    legend.textContent = 'Pick up to 5 services. Only active ones connect and ' +
        'reach the model — the rest stay in the catalog.';

    let servers = [];
    let warnTimer = null;
    const activeCount = () => servers.filter(s => s.active).length;

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

    function renderList() {
        const q = (search.value || '').trim().toLowerCase();
        listEl.innerHTML = '';
        const shown = servers.filter(s =>
            (s.display + ' ' + s.key).toLowerCase().includes(q));
        if (!shown.length) {
            listEl.innerHTML = '<div class="emx-desc" style="padding:14px;' +
                'text-align:center;">No match.</div>';
            return;
        }
        for (const s of shown) {
            const row = document.createElement('div');
            row.className = 'emx-row' + (s.active ? ' on' : '');
            row.dataset.key = s.key;
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
                '<span class="emx-trans"></span></div>';
            row.querySelector('.emx-name').textContent = s.display;
            row.querySelector('.emx-desc').textContent = s.command || s.transport;
            const diagEl = row.querySelector('.emx-diag');
            if (diagEl) diagEl.textContent = diag;
            if (tc) row.querySelector('.emx-badge').textContent = tc;
            const statusEl = row.querySelector('.emx-status');
            statusEl.className = 'emx-status ' + statusClass(s);
            statusEl.textContent = statusLabel(s);
            row.querySelector('.emx-trans').textContent = s.transport;
            const cb = row.querySelector('.emx-cb');
            cb.setAttribute('aria-label', s.display);
            listEl.appendChild(row);
        }
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
            tds[2].textContent = s.transport;
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
        chip.textContent = c + ' / ' + EXTERNAL_MCPS_MAX_ACTIVE + ' active';
        chip.classList.toggle('full', c >= EXTERNAL_MCPS_MAX_ACTIVE);
    }

    function renderAll() { renderList(); renderSum(); renderChip(); }

    listEl.onclick = (e) => {
        const row = e.target.closest('.emx-row');
        if (!row) return;
        const s = servers.find(x => x.key === row.dataset.key);
        if (!s) return;
        if (!s.active && activeCount() >= EXTERNAL_MCPS_MAX_ACTIVE) {
            flash('You can run ' + EXTERNAL_MCPS_MAX_ACTIVE +
                ' at once — switch one off first.');
            return;
        }
        s.active = !s.active;
        warn.textContent = '';
        renderAll();
    };
    search.value = '';
    search.oninput = renderList;

    listEl.innerHTML = '<div class="emx-desc" style="padding:14px;' +
        'text-align:center;">Loading…</div>';
    sumEl.innerHTML = '';
    chip.textContent = '';
    warn.textContent = '';

    fetch('/agent/external_mcps/', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(payload => {
            servers = (payload.servers || []).map(s => Object.assign({}, s));
            renderAll();
        })
        .catch(err => {
            listEl.innerHTML = '<div class="emx-desc" style="padding:14px;' +
                'text-align:center;">Load failed: ' + err + '</div>';
        });

    function saveActive() {
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
                $('#external-mcps-dialog-message').dialog('close');
            } else {
                flash('Save failed: ' + (d.error || 'unknown error'));
            }
        }).catch(err => flash('Save failed: ' + err));
    }

    $('#external-mcps-dialog-message').dialog({
        autoOpen: false,
        modal: true,
        width: 600,
        resizable: false,
        draggable: true,
        closeText: '',
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Continue")').css(DIALOG_BUTTON_CSS);
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: [
            { text: 'Continue', click: saveActive },
            { text: 'Cancel', click: function () { $(this).dialog('close'); } }
        ]
    });
    $('#external-mcps-dialog-message').dialog('open');
    $('#external-mcps-dialog-message').dialog('option', 'position',
        { my: 'center', at: 'center', of: window });
    $('#external-mcps-dialog-message').parent()
        .find('.ui-dialog-buttonpane button').css(DIALOG_BUTTON_CSS);
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
