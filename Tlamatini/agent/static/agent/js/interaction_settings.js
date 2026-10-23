/* Tlamatini Author Banner — Angela López Mendoza */
(() => {
    'use strict';
    const overlay = document.getElementById('interaction-settings-overlay');
    if (!overlay) return;
    const form = document.getElementById('interaction-settings-form');
    form.noValidate = true; // Reveal an invalid field's tab before focusing it.
    const feedback = document.getElementById('interaction-settings-feedback');
    const controls = new Map();
    let data = null, local = {}, currentTab = 'editor', opener = null, saving = false, preview = null;
    const storageKey = () => `tlamatini.interaction.appearance.v1.${data.user}`;
    function snapshot() { return data ? { ...data.defaults, ...data.preferences, ...local } : {}; }
    function broadcast() {
        window.dispatchEvent(new CustomEvent('tlm:interaction-settings', { detail: snapshot() }));
        const appearance = snapshot();
        window.TlamatiniTextEditor?.configureAppearance?.(appearance);
    }
    function readLocal() {
        let raw = {};
        try { raw = JSON.parse(localStorage.getItem(storageKey()) || '{}'); } catch { /* Use current appearance defaults. */ }
        local = {};
        for (const [key, field] of Object.entries(data.fields)) {
            if (!field.local || raw[key] === undefined) continue;
            const value = raw[key];
            const valid = typeof field.default === 'boolean' ? typeof value === 'boolean'
                : field.options ? Object.hasOwn(field.options, value)
                    : Number.isFinite(value) && value >= field.min && value <= field.max;
            if (valid) local[key] = value;
        }
    }
    async function fetchSettings() {
        const response = await fetch('/agent/interaction-settings/', { credentials: 'same-origin', cache: 'no-store' });
        if (!response.ok) throw new Error('Settings could not be loaded. Reload this page and try again.');
        const incoming = await response.json();
        if (!incoming.fields || !incoming.preferences) throw new Error('The settings response was incomplete.');
        data = incoming; readLocal(); broadcast();
        return data;
    }
    function tab(name, focus = false) {
        currentTab = name;
        for (const button of form.querySelectorAll('[data-interaction-tab]')) {
            const selected = button.dataset.interactionTab === name;
            button.setAttribute('aria-selected', String(selected)); button.tabIndex = selected ? 0 : -1;
            document.getElementById(button.getAttribute('aria-controls')).hidden = !selected;
            if (selected && focus) button.focus();
        }
    }
    function renderFields() {
        controls.clear();
        for (const group of form.querySelectorAll('[data-interaction-fields]')) group.replaceChildren();
        const advanced = new Map();
        for (const [key, field] of Object.entries(data.fields)) {
            let parent = form.querySelector(`[data-interaction-fields="${field.tab}"]`);
            if (field.advanced) {
                if (!advanced.has(field.tab)) {
                    const details = document.createElement('details'); details.className = 'tlm-interaction-advanced';
                    const summary = document.createElement('summary'); summary.textContent = 'Waiting and handoff';
                    const fields = document.createElement('div'); details.append(summary, fields); parent.append(details); advanced.set(field.tab, fields);
                }
                parent = advanced.get(field.tab);
            }
            const label = document.createElement('label'); label.className = 'tlm-interaction-field';
            const title = document.createElement('span'); title.textContent = field.label;
            const control = document.createElement(field.options ? 'select' : 'input');
            control.id = `interaction-${key}`; control.dataset.setting = key;
            if (field.options) for (const [value, text] of Object.entries(field.options)) {
                const option = new Option(text, value);
                if (key === 'shell' && !data.shells.includes(value)) { option.disabled = true; option.textContent += ' (unavailable)'; }
                control.append(option);
            }
            else if (typeof field.default === 'boolean') control.type = 'checkbox';
            else { control.type = 'number'; control.min = field.min; control.max = field.max; control.step = field.step; control.required = true; }
            label.append(...(control.type === 'checkbox' ? [control, title] : [title, control])); parent.append(label); controls.set(key, control);
        }
    }
    function populate(values) {
        for (const [key, control] of controls) {
            if (control.type === 'checkbox') control.checked = values[key]; else control.value = values[key];
        }
        syncDependencies();
    }
    function collect() {
        const values = {};
        for (const [key, control] of controls) values[key] = control.type === 'checkbox' ? control.checked : control.type === 'number' ? Number(control.value) : control.value;
        if (values.link_speeds) values.terminal_wpm = values.editor_wpm;
        return values;
    }
    function validDraft() {
        const invalid = [...controls.values()].find(control => !control.checkValidity());
        if (!invalid) return true;
        tab(data.fields[invalid.dataset.setting].tab);
        const advanced = invalid.closest('details'); if (advanced) advanced.open = true;
        invalid.reportValidity(); return false;
    }
    function syncDependencies() {
        if (!controls.size) return;
        const linked = controls.get('link_speeds').checked;
        controls.get('terminal_wpm').disabled = linked;
        if (linked) controls.get('terminal_wpm').value = controls.get('editor_wpm').value;
        controls.get('narration_wait').disabled = controls.get('narration_when').value !== 'before';
        const access = document.getElementById('interactor-access');
        document.getElementById('interaction-access-row').hidden = !access;
        document.getElementById('interaction-access').checked = access?.checked || false;
        const voice = window.TLM_VOICE.loadSettings(), chosen = window.TLM_VOICE.pickVoice();
        document.getElementById('interaction-voice-description').textContent = voice.mode === 'silent' ? 'Voice is currently muted. Narration will stay silent until you unmute it.'
            : chosen ? `${chosen.name} · ${voice.volume}% volume · ${Number(voice.rate).toFixed(2)}× speech speed`
                : 'No supported female voice is currently available. Preview can check again.';
        document.getElementById('interaction-open-voice').hidden = !window.OpenVoiceDialog;
        document.getElementById('interaction-toggle-mute').textContent = voice.mode === 'silent' ? 'Unmute voice' : 'Mute voice';
    }
    function stopPreview() { preview?.abort(); preview = null; }
    function close() {
        stopPreview(); overlay.hidden = true; overlay.style.display = 'none'; opener?.focus();
    }
    async function open(name = 'editor', source = document.activeElement) {
        if (saving) return;
        opener = source;
        // Opening a modal is an explicit user takeover, never a reason to edit behind it.
        window.TlamatiniInteractor?.stop?.();
        overlay.hidden = false; overlay.style.display = 'flex'; feedback.textContent = 'Loading your settings…';
        document.getElementById('interaction-settings-save').disabled = true;
        document.getElementById('interaction-settings-close').focus();
        try {
            await fetchSettings(); renderFields(); populate(snapshot()); tab(name);
            document.getElementById('interaction-preset').value = 'custom';
            document.getElementById('interaction-preview').hidden = true;
            feedback.textContent = 'Changes apply to the next action. Stop and mute are always immediate.';
            document.getElementById('interaction-settings-save').disabled = false;
        } catch (error) { feedback.textContent = error.message; }
    }
    async function save(event) {
        event.preventDefault(); if (!data || !validDraft()) return;
        stopPreview(); saving = true; document.getElementById('interaction-settings-save').disabled = true;
        const values = collect();
        const preferences = Object.fromEntries(Object.entries(values).filter(([key]) => !data.fields[key].local));
        try {
            const response = await fetch('/agent/interaction-settings/', { method: 'POST', credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': form.querySelector('[name="csrfmiddlewaretoken"]').value },
                body: JSON.stringify({ preferences, revision: data.revision }) });
            const incoming = await response.json();
            if (!response.ok) throw new Error(incoming.error || 'Settings could not be saved.');
            data = incoming; local = Object.fromEntries(Object.entries(values).filter(([key]) => data.fields[key].local));
            let stored = true;
            try {
                localStorage.setItem(storageKey(), JSON.stringify(local));
                localStorage.setItem(`tlamatini.interaction.changed.${data.user}`, String(Date.now()));
            } catch { stored = false; }
            broadcast(); saving = false;
            if (stored) close(); else feedback.textContent = 'Account settings saved. Appearance applies in this tab; browser storage is unavailable.';
        } catch (error) { feedback.textContent = error.message; }
        finally { saving = false; document.getElementById('interaction-settings-save').disabled = false; }
    }
    async function runPreview() {
        if (!data || !validDraft()) return;
        stopPreview(); preview = new AbortController(); const signal = preview.signal;
        const values = collect(), output = document.getElementById('interaction-preview-text');
        document.getElementById('interaction-preview').hidden = false; output.textContent = '';
        const terminal = currentTab !== 'editor', sample = terminal ? 'echo Hello' : 'FROM ';
        const wpm = terminal ? values.terminal_wpm : values.editor_wpm;
        const explain = terminal ? 'I’ll prepare a command that prints Hello.' : 'I’ll begin a Dockerfile. You will choose the base image.';
        const text = values.narration_content === 'literal' ? sample : values.narration_content === 'both' ? `${explain} ${sample}` : explain;
        const enabled = terminal ? values.narrate_terminal : values.narrate_editor;
        const say = () => window.TlamatiniInteractionSpeech.narrate({ id: `preview-${Date.now()}`, text, signal, preview: true });
        let speech;
        if (enabled && values.narration_when !== 'after') {
            speech = say(); if (values.narration_when === 'before' && values.narration_wait) await speech;
        }
        for (const char of sample) {
            if (signal.aborted) return;
            output.textContent += char;
            await new Promise(resolve => setTimeout(resolve, 60000 / (5 * wpm)));
        }
        if (!signal.aborted && enabled && values.narration_when === 'after') speech = say();
        if (speech) await speech;
        if (!signal.aborted) feedback.textContent = `Preview complete at ${wpm} WPM. Nothing was executed or saved.`;
    }
    form.addEventListener('submit', save);
    for (const id of ['interaction-settings-close', 'interaction-settings-cancel']) document.getElementById(id).addEventListener('click', close);
    overlay.tlmDismiss = close;
    form.addEventListener('input', event => {
        if (event.target.id === 'interaction-preset') return;
        syncDependencies(); document.getElementById('interaction-preset').value = 'custom';
    });
    document.getElementById('interaction-access').addEventListener('change', event => {
        const access = document.getElementById('interactor-access');
        if (access) { access.checked = event.target.checked; access.dispatchEvent(new Event('change')); }
    });
    document.getElementById('interaction-settings-reset').addEventListener('click', () => {
        const values = collect(); for (const [key, field] of Object.entries(data.fields)) if (field.tab === currentTab) values[key] = field.default;
        populate(values); feedback.textContent = 'This tab’s defaults are restored in the draft. Save to apply.';
    });
    document.getElementById('interaction-preset').addEventListener('change', event => {
        if (event.target.value === 'custom') return;
        const values = { ...data.defaults };
        if (event.target.value === 'guided') Object.assign(values, { editor_wpm: 60, terminal_wpm: 40, segment_pause: 1,
            teaching_detail: 'detailed', execution: 'manual', narrate_editor: true, narrate_terminal: true, narration_content: 'both' });
        populate(values); feedback.textContent = 'Preset loaded into the draft. Save to apply.';
    });
    document.getElementById('interaction-preview-button').addEventListener('click', runPreview);
    document.getElementById('interaction-preview-stop').addEventListener('click', stopPreview);
    document.getElementById('interaction-open-voice').addEventListener('click', () => { close(); window.OpenVoiceDialog?.(); });
    document.getElementById('interaction-toggle-mute').addEventListener('click', () => {
        window.TLM_VOICE.setSilent(window.TLM_VOICE.loadSettings().mode !== 'silent'); syncDependencies();
    });
    window.addEventListener('tlm:voice-settings', syncDependencies);
    window.speechSynthesis?.addEventListener('voiceschanged', syncDependencies);
    form.addEventListener('keydown', event => {
        if (event.target.matches('[role="tab"]') && ['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
            event.preventDefault(); const tabs = ['editor', 'terminal', 'voice'];
            const index = event.key === 'Home' ? 0 : event.key === 'End' ? 2 : (tabs.indexOf(currentTab) + (event.key === 'ArrowRight' ? 1 : 2)) % 3;
            tab(tabs[index], true);
        }
        if (event.key === 'Tab') {
            const items = [...form.querySelectorAll('button, input, select, summary, [tabindex="0"]')].filter(el => !el.disabled && el.tabIndex !== -1 && el.getClientRects().length);
            if (event.shiftKey && document.activeElement === items[0]) { event.preventDefault(); items.at(-1)?.focus(); }
            else if (!event.shiftKey && document.activeElement === items.at(-1)) { event.preventDefault(); items[0]?.focus(); }
        }
    });
    document.addEventListener('click', event => {
        const trigger = event.target.closest('[data-interaction-settings]');
        if (trigger) { event.preventDefault(); open(trigger.dataset.interactionSettings || 'editor', trigger); }
        const selected = event.target.closest('[data-interaction-tab]'); if (selected) tab(selected.dataset.interactionTab);
    });
    window.addEventListener('storage', event => {
        if (!data || ![storageKey(), `tlamatini.interaction.changed.${data.user}`].includes(event.key)) return;
        if (!overlay.hidden) feedback.textContent = 'Settings changed in another tab. Close and reopen to load them before saving.';
        else fetchSettings().catch(() => {});
    });
    window.addEventListener('tlm:narration-unavailable', () => { feedback.textContent = 'Voice could not play. Check Config → Voice or try Preview again.'; });
    const ready = fetchSettings().catch(() => null);
    window.TlamatiniInteractionSettings = { open, snapshot, ready, refresh: fetchSettings };
})();
