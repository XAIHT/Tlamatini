// ============================================================
// access_keys_wizard.js - graphical one-page key setup wizard
// ============================================================

let _accessKeysWizardStatus = null;

function _akwEscape(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    })[ch]);
}

function _akwDialogEl() {
    return document.getElementById('access-keys-wizard-dialog-message');
}

function _akwNavEl() {
    return document.getElementById('access-keys-wizard-nav');
}

function _akwContentEl() {
    return document.getElementById('access-keys-wizard-content');
}

function _akwSummaryEl() {
    return document.getElementById('access-keys-wizard-summary');
}

function _akwNoticeEl() {
    return document.getElementById('access-keys-wizard-notice');
}

function _akwSetNotice(message, kind) {
    const notice = _akwNoticeEl();
    if (!notice) return;
    if (!message) {
        notice.innerHTML = '';
        return;
    }
    notice.innerHTML = '<div class="akw-notice ' + _akwEscape(kind || 'ok') + '">' +
        _akwEscape(message) + '</div>';
}

function _akwPill(row) {
    if (row && row.weak_default) {
        return '<span class="akw-pill warn">Weak</span>';
    }
    if (row && row.configured) {
        return '<span class="akw-pill ok">Ready</span>';
    }
    return '<span class="akw-pill missing">Missing</span>';
}

function _akwCommandPill(command) {
    if (command && command.resolvable) {
        return '<span class="akw-pill ok">Found</span>';
    }
    return '<span class="akw-pill missing">Missing</span>';
}

function _akwFieldPlaceholder(row) {
    if (row.configured) {
        return row.kind === 'secret'
            ? 'Configured - paste a new value only to replace it'
            : 'Configured - type a new value only to replace it';
    }
    return row.kind === 'secret' ? 'Paste key or password' : 'Type value';
}

function _akwScrollContentTo(section, targetKey) {
    const content = _akwContentEl();
    if (!content || !section) return;
    const contentRect = content.getBoundingClientRect();
    const sectionRect = section.getBoundingClientRect();
    const top = content.scrollTop + sectionRect.top - contentRect.top;
    content.scrollTo({
        top: Math.max(0, top),
        behavior: 'smooth'
    });
    const nav = _akwNavEl();
    if (nav) {
        nav.querySelectorAll('.akw-nav-button').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-target') === targetKey);
        });
    }
}

function _akwRenderNav(status) {
    const nav = _akwNavEl();
    if (!nav || !status) return;
    const buttons = [];
    let index = 1;
    (status.groups || []).forEach(group => {
        buttons.push({
            key: group.key,
            label: group.title,
            index: index
        });
        index += 1;
    });
    buttons.push({ key: 'commands', label: 'ACPX Commands', index: index });
    buttons.push({ key: 'review', label: 'Review', index: index + 1 });

    nav.innerHTML = buttons.map(btn =>
        '<button type="button" class="akw-nav-button" data-target="' + _akwEscape(btn.key) + '">' +
        '<span class="akw-nav-index">' + _akwEscape(btn.index) + '</span>' +
        '<span class="akw-nav-label">' + _akwEscape(btn.label) + '</span>' +
        '</button>'
    ).join('');

    nav.querySelectorAll('.akw-nav-button').forEach(button => {
        button.addEventListener('click', event => {
            event.preventDefault();
            event.stopPropagation();
            const target = button.getAttribute('data-target');
            const section = document.getElementById('akw-section-' + target);
            if (section) {
                _akwScrollContentTo(section, target);
            }
        });
    });
}

function _akwRenderField(row) {
    const type = row.kind === 'secret' ? 'password' : 'text';
    const note = row.note
        ? '<div class="akw-field-note">' + _akwEscape(row.note) + '</div>'
        : '';
    return (
        '<label class="akw-field-label" for="akw-field-' + _akwEscape(row.key) + '">' +
        _akwEscape(row.label) +
        '</label>' +
        '<input class="akw-field-input" id="akw-field-' + _akwEscape(row.key) + '" ' +
        'data-key="' + _akwEscape(row.key) + '" type="' + type + '" ' +
        'autocomplete="off" spellcheck="false" placeholder="' + _akwEscape(_akwFieldPlaceholder(row)) + '">' +
        _akwPill(row) +
        note
    );
}

function _akwRenderGroup(group) {
    const fields = (group.fields || []).map(_akwRenderField).join('');
    const extra = group.key === 'acpx'
        ? '<label class="akw-option-row">' +
        '<input id="akw-mirror-google-alias" type="checkbox" checked>' +
        '<span>Use the Gemini key as GOOGLE_API_KEY when GOOGLE_API_KEY is left blank.</span>' +
        '</label>'
        : '';
    return (
        '<section id="akw-section-' + _akwEscape(group.key) + '" class="akw-section">' +
        '<h6 class="akw-section-title">' + _akwEscape(group.title) + '</h6>' +
        '<p class="akw-section-help">Blank fields keep the existing local value. Typed values replace that one setting.</p>' +
        '<div class="akw-field-grid">' + fields + '</div>' +
        extra +
        '</section>'
    );
}

function _akwRenderCommands(commands) {
    const rows = (commands || []).map(command => (
        '<tr>' +
        '<td><div class="akw-command-name">' + _akwEscape(command.agent_id) + '</div>' +
        '<div class="akw-command-desc">' + _akwEscape(command.description || '') + '</div></td>' +
        '<td>' + _akwCommandPill(command) + '</td>' +
        '<td><input class="akw-command-input" data-agent-id="' + _akwEscape(command.agent_id) + '" ' +
        'data-original="' + _akwEscape(command.command || '') + '" value="' + _akwEscape(command.command || '') + '" ' +
        'autocomplete="off" spellcheck="false"></td>' +
        '</tr>'
    )).join('');

    return (
        '<section id="akw-section-commands" class="akw-section">' +
        '<h6 class="akw-section-title">ACPX Commands</h6>' +
        '<p class="akw-section-help">Set a full CLI path only when a command is not found on PATH.</p>' +
        '<table class="akw-command-table">' +
        '<thead><tr><th>Agent</th><th>Status</th><th>Command or path</th></tr></thead>' +
        '<tbody>' + rows + '</tbody>' +
        '</table>' +
        '</section>'
    );
}

function _akwRenderReview(status) {
    const summary = status.summary || {};
    const missingFields = [];
    (status.groups || []).forEach(group => {
        (group.fields || []).forEach(row => {
            if (!row.configured) missingFields.push(row.label);
        });
    });
    const missingCommands = (status.commands || [])
        .filter(command => !command.resolvable)
        .map(command => command.agent_id);
    const missingFieldText = missingFields.length ? missingFields.join(', ') : 'None';
    const missingCommandText = missingCommands.length ? missingCommands.join(', ') : 'None';

    return (
        '<section id="akw-section-review" class="akw-section">' +
        '<h6 class="akw-section-title">Review</h6>' +
        '<ul class="akw-review-list">' +
        '<li><strong>Configured fields</strong><span>' +
        _akwEscape(summary.configured_fields || 0) + ' / ' + _akwEscape(summary.total_fields || 0) +
        '</span></li>' +
        '<li><strong>Missing values</strong><span>' + _akwEscape(missingFieldText) + '</span></li>' +
        '<li><strong>Missing ACPX commands</strong><span>' + _akwEscape(missingCommandText) + '</span></li>' +
        '<li><strong>Vault</strong><span>' + _akwEscape(status.data_keys_path || '') + '</span></li>' +
        '<li><strong>Runtime config</strong><span>' + _akwEscape(status.config_path || '') + '</span></li>' +
        '</ul>' +
        '</section>'
    );
}

function _akwRenderStatus(status) {
    _accessKeysWizardStatus = status;
    const summary = _akwSummaryEl();
    if (summary) {
        const s = status.summary || {};
        summary.innerHTML = '<strong>' + _akwEscape(s.configured_fields || 0) + '</strong> / ' +
            _akwEscape(s.total_fields || 0) + '<br><span>configured</span>';
    }
    _akwRenderNav(status);
    const content = _akwContentEl();
    if (!content) return;
    content.innerHTML = [
        ...(status.groups || []).map(_akwRenderGroup),
        _akwRenderCommands(status.commands || []),
        _akwRenderReview(status)
    ].join('');
}

async function _akwLoadStatus() {
    const response = await fetch('/agent/access_keys_wizard/', {
        method: 'GET',
        credentials: 'same-origin'
    });
    const body = await response.json();
    if (!response.ok || !body || body.success !== true) {
        throw new Error((body && body.error) || ('HTTP ' + response.status));
    }
    return body;
}

function _akwCollectPayload() {
    const fields = {};
    document.querySelectorAll('.akw-field-input[data-key]').forEach(input => {
        const key = input.getAttribute('data-key');
        const value = (input.value || '').trim();
        if (key && value) {
            fields[key] = value;
        }
    });

    const commands = {};
    document.querySelectorAll('.akw-command-input[data-agent-id]').forEach(input => {
        const agentId = input.getAttribute('data-agent-id');
        const original = input.getAttribute('data-original') || '';
        const value = (input.value || '').trim();
        if (agentId && value && value !== original) {
            commands[agentId] = value;
        }
    });

    const mirrorCheckbox = document.getElementById('akw-mirror-google-alias');
    return {
        fields,
        commands,
        mirror_google_alias: mirrorCheckbox ? mirrorCheckbox.checked : true
    };
}

async function _akwSave() {
    const payload = _akwCollectPayload();
    if (Object.keys(payload.fields).length === 0 && Object.keys(payload.commands).length === 0) {
        _akwSetNotice('No new values were entered. Existing secrets were left untouched.', 'warn');
        return false;
    }

    const response = await fetch('/agent/save_access_keys_wizard/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(payload)
    });
    const body = await response.json();
    if (!response.ok || !body || body.success !== true) {
        throw new Error((body && body.error) || ('HTTP ' + response.status));
    }

    _akwRenderStatus(body.status);
    const updatedKeyCount = (body.updated_keys || []).length;
    const updatedCommandCount = (body.updated_commands || []).length;
    const fileCount = (body.files_changed || []).length;
    const restart = body.restart_required
        ? ' Restart Tlamatini so every runtime reloads the new values.'
        : '';
    _akwSetNotice(
        'Saved ' + updatedKeyCount + ' value(s) and ' + updatedCommandCount +
        ' command override(s) across ' + fileCount + ' file(s).' + restart,
        'ok'
    );
    return true;
}

function _akwStyleButtons() {
    const css = typeof DIALOG_BUTTON_CSS === 'object' ? DIALOG_BUTTON_CSS : {};
    $('.ui-dialog-buttonpane button:contains("Save")').css(css);
    $('.ui-dialog-buttonpane button:contains("Close")').css(css);
}

function _akwOpenDialog() {
    const dlg = _akwDialogEl();
    if (!dlg) return;
    try {
        if ($('#access-keys-wizard-dialog-message').hasClass('ui-dialog-content')) {
            $('#access-keys-wizard-dialog-message').dialog('destroy');
        }
    } catch (err) {
        console.log('access-keys wizard dialog destroy ignored:', err);
    }
    $('#access-keys-wizard-dialog-message').dialog({
        autoOpen: false,
        modal: true,
        dialogClass: 'access-keys-wizard-ui-dialog',
        width: Math.min(Math.floor(window.innerWidth * 0.9), 1180),
        height: Math.floor(window.innerHeight * 0.84),
        resizable: false,
        draggable: true,
        closeText: '',
        open: function () {
            document.body.style.overflow = 'hidden';
            _akwStyleButtons();
        },
        close: function () { document.body.style.overflow = ''; },
        create: function () { _akwStyleButtons(); },
        buttons: [
            {
                text: 'Save',
                click: function () {
                    const $dlg = $(this);
                    const saveBtn = $dlg.parent().find('.ui-dialog-buttonpane button:contains("Save")');
                    const closeBtn = $dlg.parent().find('.ui-dialog-buttonpane button:contains("Close")');
                    saveBtn.prop('disabled', true);
                    closeBtn.prop('disabled', true);
                    _akwSetNotice('Saving...', 'ok');
                    _akwSave()
                        .catch(err => {
                            console.error('Access Keys Wizard save failed:', err);
                            _akwSetNotice('Save failed: ' + (err.message || 'unknown error'), 'error');
                        })
                        .finally(() => {
                            saveBtn.prop('disabled', false);
                            closeBtn.prop('disabled', false);
                            _akwStyleButtons();
                        });
                }
            },
            {
                text: 'Close',
                click: function () { $(this).dialog('close'); }
            }
        ]
    });
    $('#access-keys-wizard-dialog-message').dialog('open');
    $('#access-keys-wizard-dialog-message').dialog('option', 'position',
        { my: 'center', at: 'center', of: window });
    _akwStyleButtons();
}

function openAccessKeysWizardDialog() { // eslint-disable-line no-unused-vars
    const content = _akwContentEl();
    const nav = _akwNavEl();
    if (content) content.innerHTML = '<div class="akw-notice ok">Loading...</div>';
    if (nav) nav.innerHTML = '';
    _akwSetNotice('', '');
    _akwOpenDialog();
    _akwLoadStatus()
        .then(status => {
            _akwRenderStatus(status);
            _akwSetNotice('Paste only the values you want to add or replace. Blank fields keep what is already configured.', 'ok');
        })
        .catch(err => {
            console.error('Access Keys Wizard load failed:', err);
            _akwSetNotice('Could not load Access Keys Wizard: ' + (err.message || 'unknown error'), 'error');
        });
}
