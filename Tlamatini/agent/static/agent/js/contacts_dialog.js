/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Crafted with heart by  Angela   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// ============================================================
// contacts_dialog.js — Config ▸ Contacts CRUD dialog
// ============================================================
//
//   OpenContactsDialog(event)
//     -- "Contacts book" dialog. Full CRUD over contacts.json: a
//        searchable master list (left) + a detail editor (right).
//        Add / edit / delete happen in-memory; "Save" POSTs the whole
//        list to /agent/contacts/save/. The modal is viewport bounded
//        and centered (native, focus-trapped, Esc/backdrop to close),
//        matching the External ▸ MCPs dialog look and feel.

let _contactsKeydownHandler = null;

function _ctbCsrf() {
    const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : '';
}

function OpenContactsDialog(event) { // eslint-disable-line no-unused-vars
    if (event && event.preventDefault) event.preventDefault();
    const dlg = document.getElementById('contacts-dialog-message');
    if (!dlg) { console.error('contacts-dialog: container missing'); return; }

    const listEl = document.getElementById('contacts-list');
    const search = document.getElementById('contacts-search');
    const legend = document.getElementById('contacts-legend');
    const warn = document.getElementById('contacts-warn');
    const editTitle = document.getElementById('contacts-edit-title');
    const closeBtn = document.getElementById('contacts-close');
    const cancelBtn = document.getElementById('contacts-cancel');
    const saveBtn = document.getElementById('contacts-save');
    const addBtn = document.getElementById('contacts-add');
    const applyBtn = document.getElementById('contacts-apply');
    const revertBtn = document.getElementById('contacts-revert');
    const f = {
        name: document.getElementById('contacts-f-name'),
        aliases: document.getElementById('contacts-f-aliases'),
        telegram: document.getElementById('contacts-f-telegram'),
        whatsapp: document.getElementById('contacts-f-whatsapp'),
        email: document.getElementById('contacts-f-email'),
        note: document.getElementById('contacts-f-note')
    };
    if (!listEl || !search || !legend || !warn || !editTitle || !closeBtn ||
        !cancelBtn || !saveBtn || !addBtn || !applyBtn || !revertBtn ||
        !f.name || !f.aliases || !f.telegram || !f.whatsapp || !f.email || !f.note) {
        return;
    }

    let contacts = [];
    let editingIndex = -1;   // index in `contacts` being edited; -1 = new/unsaved
    let dirty = false;
    let isSaving = false;
    let warnTimer = null;

    function flash(msg, isErr) {
        warn.textContent = msg;
        warn.classList.toggle('err', !!isErr);
        if (warnTimer) clearTimeout(warnTimer);
        if (msg) warnTimer = setTimeout(() => { warn.textContent = ''; }, 3000);
    }

    function renderLegend() {
        const n = contacts.length;
        legend.textContent = n === 1
            ? '1 contact. Click one to edit, or press “New”.'
            : n + ' contacts. Click one to edit, or press “New”.';
    }

    function listMessage(text) {
        const node = document.createElement('div');
        node.className = 'ctb-empty';
        node.textContent = text;
        return node;
    }

    function appendChannel(parent, cls, label) {
        const span = document.createElement('span');
        span.className = 'ctb-chan ' + cls;
        span.textContent = label;
        parent.appendChild(span);
    }

    function renderList() {
        const q = (search.value || '').trim().toLowerCase();
        listEl.innerHTML = '';
        const shown = [];
        contacts.forEach((c, idx) => {
            const hay = ((c.name || '') + ' ' + (c.aliases || '') + ' ' +
                (c.telegram || '') + ' ' + (c.whatsapp || '') + ' ' +
                (c.email || '')).toLowerCase();
            if (!q || hay.includes(q)) shown.push(idx);
        });
        if (!contacts.length) {
            listEl.appendChild(listMessage('No contacts yet. Press “New” to add one.'));
            return;
        }
        if (!shown.length) {
            listEl.appendChild(listMessage('No match.'));
            return;
        }
        const fragment = document.createDocumentFragment();
        for (const idx of shown) {
            const c = contacts[idx];
            const row = document.createElement('div');
            row.className = 'ctb-row' + (idx === editingIndex ? ' selected' : '');
            row.dataset.index = String(idx);
            row.setAttribute('role', 'button');
            row.tabIndex = 0;
            row.innerHTML =
                '<div class="ctb-info"><div class="ctb-name"></div>' +
                (c.aliases ? '<div class="ctb-sub"></div>' : '') +
                '<div class="ctb-chanrow"></div></div>' +
                '<button type="button" class="ctb-del" title="Delete contact">' +
                '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">' +
                '<path d="M9 3h6l1 2h4v2H4V5h4l1-2zm-3 6h12l-1 12H7L6 9zm4 2v8h2v-8h-2zm4 0v8h2v-8h-2z"/>' +
                '</svg></button>';
            row.querySelector('.ctb-name').textContent = c.name || '(no name)';
            const sub = row.querySelector('.ctb-sub');
            if (sub) sub.textContent = 'aka ' + c.aliases;
            const chans = row.querySelector('.ctb-chanrow');
            if (c.telegram) appendChannel(chans, 'ctb-chan-tg', 'TG ' + c.telegram);
            if (c.whatsapp) appendChannel(chans, 'ctb-chan-wa', 'WA ' + c.whatsapp);
            if (c.email) appendChannel(chans, 'ctb-chan-em', '@ ' + c.email);
            if (!c.telegram && !c.whatsapp && !c.email) {
                appendChannel(chans, 'ctb-chan-em', 'no channels');
            }
            row.querySelector('.ctb-del')
                .setAttribute('aria-label', 'Delete ' + (c.name || 'contact'));
            fragment.appendChild(row);
        }
        listEl.appendChild(fragment);
    }

    function renderAll() { renderLegend(); renderList(); }

    function fillForm(c) {
        f.name.value = c ? (c.name || '') : '';
        f.aliases.value = c ? (c.aliases || '') : '';
        f.telegram.value = c ? (c.telegram || '') : '';
        f.whatsapp.value = c ? (c.whatsapp || '') : '';
        f.email.value = c ? (c.email || '') : '';
        f.note.value = c ? (c.note || '') : '';
    }

    function selectRow(idx) {
        const c = contacts[idx];
        if (!c) return;
        editingIndex = idx;
        fillForm(c);
        editTitle.textContent = 'Editing: ' + (c.name || '(no name)');
        renderList();
        window.setTimeout(() => f.name.focus(), 0);
    }

    function newContact() {
        editingIndex = -1;
        fillForm(null);
        editTitle.textContent = 'New contact';
        renderList();
        window.setTimeout(() => f.name.focus(), 0);
    }

    function readForm() {
        return {
            name: f.name.value.trim(),
            aliases: f.aliases.value.trim(),
            telegram: f.telegram.value.trim(),
            whatsapp: f.whatsapp.value.trim(),
            email: f.email.value.trim(),
            note: f.note.value.trim()
        };
    }

    function applyForm() {
        const c = readForm();
        if (!c.name) {
            flash('A name is required.', true);
            f.name.focus();
            return;
        }
        if (editingIndex >= 0 && contacts[editingIndex]) {
            contacts[editingIndex] = c;
        } else {
            contacts.push(c);
            editingIndex = contacts.length - 1;
        }
        dirty = true;
        editTitle.textContent = 'Editing: ' + c.name;
        renderAll();
        flash('Applied “' + c.name + '” — press Save to persist.');
    }

    function removeContact(idx) {
        const c = contacts[idx];
        if (!c) return;
        const label = c.name || 'this contact';
        if (!confirm('Delete “' + label + '” from the contacts book?\n\n' +
            'It is removed when you press Save.')) {
            return;
        }
        contacts.splice(idx, 1);
        dirty = true;
        if (editingIndex === idx) {
            newContact();
        } else {
            if (editingIndex > idx) editingIndex -= 1;
            renderAll();
        }
        flash('Removed “' + label + '” — press Save to persist.');
    }

    listEl.onclick = (e) => {
        const delBtn = e.target.closest('.ctb-del');
        if (delBtn) {
            e.stopPropagation();
            const delRow = delBtn.closest('.ctb-row');
            if (delRow) removeContact(parseInt(delRow.dataset.index, 10));
            return;
        }
        const row = e.target.closest('.ctb-row');
        if (row) selectRow(parseInt(row.dataset.index, 10));
    };
    listEl.onkeydown = (e) => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        if (e.target.closest('.ctb-del')) return;
        const row = e.target.closest('.ctb-row');
        if (!row) return;
        e.preventDefault();
        selectRow(parseInt(row.dataset.index, 10));
    };
    search.value = '';
    search.oninput = () => { listEl.scrollTop = 0; renderList(); };
    addBtn.onclick = newContact;
    applyBtn.onclick = applyForm;
    revertBtn.onclick = newContact;

    function setSaving(next) {
        isSaving = next;
        saveBtn.disabled = next;
        saveBtn.textContent = next ? 'Saving...' : 'Save';
    }

    function closeDialog() {
        if (dirty && !confirm('Discard unsaved contact changes?')) return;
        if (warnTimer) clearTimeout(warnTimer);
        if (_contactsKeydownHandler) {
            document.removeEventListener('keydown', _contactsKeydownHandler);
            _contactsKeydownHandler = null;
        }
        dlg.classList.remove('is-open');
        dlg.hidden = true;
        document.body.classList.remove('ctb-dialog-open');
    }

    function focusableElements() {
        return Array.from(dlg.querySelectorAll(
            'button:not([disabled]), input:not([disabled]), textarea:not([disabled]),' +
            ' [tabindex]:not([tabindex="-1"])'
        )).filter(el => el.getClientRects().length > 0);
    }

    function onDialogKeydown(e) {
        if (e.key === 'Escape') { e.preventDefault(); closeDialog(); return; }
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
        if (_contactsKeydownHandler) {
            document.removeEventListener('keydown', _contactsKeydownHandler);
        }
        dlg.hidden = false;
        dlg.classList.add('is-open');
        document.body.classList.add('ctb-dialog-open');
        _contactsKeydownHandler = onDialogKeydown;
        document.addEventListener('keydown', _contactsKeydownHandler);
        window.setTimeout(() => search.focus(), 0);
    }

    function saveAll() {
        if (isSaving) return;
        const c = readForm();
        // Auto-commit a non-empty in-progress editor entry so a user who typed
        // a contact and pressed Save (without Apply) does not lose it.
        if (c.name && (editingIndex < 0 ||
            JSON.stringify(contacts[editingIndex]) !== JSON.stringify(c))) {
            applyForm();
        }
        setSaving(true);
        fetch('/agent/contacts/save/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': _ctbCsrf(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ contacts })
        }).then(r => r.json()).then(d => {
            setSaving(false);
            if (d.ok) {
                dirty = false;
                flash('Saved ' + d.count + (d.count === 1 ? ' contact.' : ' contacts.'));
            } else {
                flash('Save failed: ' + (d.error || 'unknown error'), true);
            }
        }).catch(err => { setSaving(false); flash('Save failed: ' + err, true); });
    }

    closeBtn.onclick = closeDialog;
    cancelBtn.onclick = closeDialog;
    saveBtn.onclick = saveAll;
    dlg.onclick = (e) => { if (e.target === dlg) closeDialog(); };

    // Initial state
    contacts = [];
    editingIndex = -1;
    dirty = false;
    fillForm(null);
    editTitle.textContent = 'Pick a contact, or press “New”';
    listEl.innerHTML = '';
    listEl.appendChild(listMessage('Loading...'));
    warn.textContent = '';
    setSaving(false);
    legend.textContent = '';
    openDialog();

    fetch('/agent/contacts/', { credentials: 'same-origin' })
        .then(r => r.json())
        .then(payload => {
            if (!payload || payload.ok === false) {
                listEl.innerHTML = '';
                listEl.appendChild(listMessage(
                    'Load failed: ' + ((payload && payload.error) || 'unknown error')));
                return;
            }
            contacts = (payload.contacts || []).map(c => Object.assign({}, c));
            renderAll();
        })
        .catch(err => {
            listEl.innerHTML = '';
            listEl.appendChild(listMessage('Load failed: ' + err));
        });
}
