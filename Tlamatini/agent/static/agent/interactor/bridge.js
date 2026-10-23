/* Tlamatini Author Banner — Angela López Mendoza */
/* global inLongOperation, chatInput, isMultiTurnEnabled */
(() => {
    'use strict';
    const editor = window.TlamatiniTextEditor;
    const ui = Object.fromEntries(['access', 'status', 'explain', 'stop', 'card', 'label', 'hint',
        'choices', 'completion', 'continue', 'ask', 'suggestions'].map(key => [key, document.getElementById(`interactor-${key}`)]));
    if (!editor || !ui.access) return;
    const MAX_UNITS = 262144;
    const preference = `tlamatini.interactor.enabled.${document.body.dataset.layoutUser}`;
    let enabled = true, socket = null, clientId = '', retry = null, closed = false;
    let active = null, lastMessage = '', userStopped = false, guided = false;
    const seen = new Set();
    try { enabled = localStorage.getItem(preference) !== 'false'; } catch { /* optional preference */ }

    function send(message) {
        if (socket?.readyState !== WebSocket.OPEN) return false;
        socket.send(JSON.stringify(message));
        return true;
    }

    function snapshot() {
        const state = editor.inspect();
        if (state.text.length > MAX_UNITS) throw new Error('Live tutoring supports up to 256 Ki characters. The editor keeps the complete file; no content was sent or truncated.');
        return { ...state, dirty: window.TlamatiniCanvasEditing?.dirty || false,
            busy: !!active || window.TlamatiniCanvasEditing?.busy || false };
    }

    function render() {
        const guide = editor.interactor.guide();
        if (guided && !guide && lastMessage === 'Your turn · fill the marked field') lastMessage = 'Guided field closed · your changes are kept';
        guided = !!guide;
        ui.access.checked = enabled;
        ui.status.dataset.state = active?.waiting ? 'waiting' : active ? 'typing' : guide ? 'waiting' : clientId && enabled ? 'ready' : 'offline';
        const status = active?.waiting ? 'Editing paused · return to this tab to resume · Stop cancels'
            : active ? 'Tlamatini is editing · Esc or type to take over'
            : lastMessage || (!enabled ? 'Live editor paused' : clientId ? 'Live editor connected' : 'Connecting to live editor…');
        if (ui.status.textContent !== status) ui.status.textContent = status;
        ui.stop.disabled = !active && !guide;
        ui.explain.disabled = !editor.active || !enabled || !clientId || !!inLongOperation;
        ui.card.hidden = !guide;
        if (!guide) return;
        ui.label.textContent = `Your turn · ${guide.label}`;
        ui.hint.textContent = guide.hint;
        ui.suggestions.checked = guide.enabled;
        const value = editor.getText().slice(guide.start, guide.end);
        const suggestion = editor.interactor.suggestion();
        const message = suggestion ? 'Tab accepts · Ctrl+Right accepts a word · Esc dismisses'
            : value ? 'Your own value is welcome. Continue when you are ready.' : 'Start typing in the marked space. Suggestions are optional.';
        if (ui.completion.textContent !== message) ui.completion.textContent = message;
        // Rebuild only when choices change; ordinary selection updates must not
        // remove a focused button or create repeated screen-reader announcements.
        const options = guide.enabled && value ? guide.choices.filter(choice => choice.text.startsWith(value) && choice.text !== value).slice(0, 3) : [];
        const signature = JSON.stringify([guide.id, options]);
        if (ui.choices.dataset.signature !== signature) {
            ui.choices.dataset.signature = signature;
            ui.choices.replaceChildren(...options.map(choice => {
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'interactor-choice';
                const code = document.createElement('code'); code.textContent = choice.text;
                const detail = document.createElement('span'); detail.textContent = choice.detail;
                button.append(code, detail);
                button.addEventListener('click', () => {
                    const current = editor.interactor.guide();
                    if (!current || current.id !== guide.id) return;
                    editor.interactor.select(current.end, current.end);
                    editor.interactor.accept(choice.text);
                });
                return button;
            }));
        }
        ui.continue.disabled = !value.trim() || !!active || !!inLongOperation || !clientId;
        ui.ask.disabled = !!active || !!inLongOperation || !clientId;
    }

    function stop(message = 'Typing stopped. Your changes are kept.', endGuide = false, notify = true) {
        const wasTyping = !!active;
        active?.controller.abort();
        if (endGuide) editor.interactor.setGuide(null);
        if (wasTyping || endGuide) {
            userStopped = true;
            lastMessage = message;
            if (notify) send({ t: 'stop' });
        }
        render();
    }

    function checkExpected(payload, editable = true, ownAction = false) {
        if (!enabled || userStopped) throw new Error('The user paused or took over the editor. Wait for their next chat request.');
        const current = snapshot();
        if (current.document_id !== payload.document_id || current.revision !== payload.revision) {
            throw new Error('The document changed. Read the live editor again; this edit was not applied.');
        }
        if (window.TlamatiniCanvasEditing?.busy || (active && !ownAction)) throw new Error('Wait for the current save or typing action to finish.');
        if (editable && !current.active) throw new Error('This document is not an editable text file.');
        return current;
    }

    function showSource() {
        window.TlamatiniViews?.setCanvasVisible(true);
        window.TlamatiniMarkdownCanvas?.selectView(false);
    }

    // Visibility is a temporary presentation state, not permission withdrawal.
    // Keep the same command/Undo group; user edits and cancellation still win.
    async function visibleAction(message, run) {
        const controller = new AbortController();
        const operation = { id: message.id, controller, waiting: false };
        active = operation;
        const timer = setTimeout(() => controller.abort(), Math.max(0, message.deadline - Date.now()));
        async function waitForView() {
            if (document.hidden && !controller.signal.aborted) {
                operation.waiting = true;
                render();
                await new Promise(resolve => {
                    const finish = () => {
                        if (document.hidden && !controller.signal.aborted) return;
                        document.removeEventListener('visibilitychange', finish);
                        controller.signal.removeEventListener('abort', finish);
                        resolve();
                    };
                    document.addEventListener('visibilitychange', finish);
                    controller.signal.addEventListener('abort', finish, { once: true });
                    finish();
                });
                operation.waiting = false;
            }
            if (controller.signal.aborted || Date.now() > message.deadline) {
                throw Object.assign(new Error('Editor action ended. Your content is kept; read it before continuing.'), { status: 'aborted' });
            }
            render();
        }
        try {
            await waitForView();
            // A file or selection can change while we wait. Never apply stale work.
            checkExpected(message.payload, !['prepare', 'open'].includes(message.action), true);
            showSource();
            operation.opening = message.action === 'open';
            return await run(controller.signal, waitForView);
        } catch (error) {
            lastMessage = error.message;
            throw error;
        } finally {
            clearTimeout(timer);
            if (active === operation) active = null;
            render();
        }
    }

    async function command(message) {
        if (!enabled) throw new Error('Live editor access is paused.');
        if (!Number.isFinite(message.deadline) || Date.now() > message.deadline) throw new Error('This editor action expired before it arrived.');
        const payload = message.payload || {};
        const action = message.action;
        if (action === 'read') return { ok: true, status: 'read', snapshot: snapshot() };
        if (action === 'stop') { stop('Tlamatini handed the editor back to you.', true, false); return { ok: true, status: 'stopped', snapshot: snapshot() }; }
        const current = checkExpected(payload, !['prepare', 'open'].includes(action));
        if (action === 'prepare') {
            if (current.dirty) throw new Error('Save your unsaved changes before opening another file.');
            await visibleAction(message, async () => {});
            return { ok: true, status: 'ready', snapshot: current };
        }
        if (action === 'open') {
            if (current.dirty) throw new Error('Unsaved changes were kept. Save before opening another file.');
            const data = payload.file;
            if (!data || typeof data.bytes !== 'string' || data.bytes.length > 1500000) throw new Error('Invalid file payload.');
            const bytes = Uint8Array.from(atob(data.bytes), value => value.charCodeAt(0));
            const file = new File([bytes], data.name, { type: 'text/plain' });
            await visibleAction(message, signal => window.TlamatiniCanvasEditing.openNative(file, data.native, data.path, payload,
                () => signal.aborted || !enabled || userStopped || Date.now() > message.deadline || socket?.readyState !== WebSocket.OPEN));
            lastMessage = 'File opened · edits stay unsaved until Save';
        } else if (action === 'type') {
            lastMessage = '';
            await visibleAction(message, async (signal, waitForView) => {
                const preferences = payload.preferences || {};
                const type = async () => {
                    checkExpected(payload, true, true);
                    await editor.interactor.type(payload, signal, waitForView);
                    const delay = Number(preferences.segment_pause || 0) * 1000;
                    if (delay) await new Promise(resolve => {
                        const done = () => { clearTimeout(timer); signal.removeEventListener('abort', done); resolve(); };
                        const timer = setTimeout(done, delay); signal.addEventListener('abort', done, { once: true });
                    });
                    await waitForView();
                };
                if (window.TlamatiniInteractionSpeech) await window.TlamatiniInteractionSpeech.around(preferences, payload.narration || '', message.id, signal, type, waitForView);
                else await type();
            });
            lastMessage = 'Tlamatini finished this step · changes are unsaved';
        } else if (action === 'guide') {
            await visibleAction(message, async () => {
                editor.interactor.select(payload.start, payload.end);
                editor.interactor.setGuide({ id: message.id, start: payload.start, end: payload.end,
                    label: payload.label, hint: payload.hint, choices: payload.choices || [],
                    enabled: payload.preferences?.suggestions !== false,
                    ghost: payload.preferences?.suggestion_display !== 'choices' });
            });
            lastMessage = 'Your turn · fill the marked field';
        } else if (action === 'select') {
            await visibleAction(message, async () => editor.interactor.select(payload.start, payload.end));
        } else if (action === 'save') {
            if (!window.TlamatiniCanvasEditing.nativeTarget) throw new Error('Choose a destination with Save first. Tlamatini cannot grant browser file permissions for you.');
            if (!await window.TlamatiniCanvasEditing.save()) throw new Error(window.TlamatiniCanvasEditing.notice || 'The file was not saved.');
            lastMessage = window.TlamatiniCanvasEditing.dirty ? 'Saved earlier content · newer changes remain unsaved' : 'Saved the editor content';
        } else throw new Error('Unsupported editor action.');
        render();
        return { ok: true, status: action === 'guide' ? 'waiting_for_user' : action === 'type' ? 'typed' : action === 'save' ? 'saved' : 'completed', snapshot: snapshot(),
            ...(action === 'save' ? { saved_revision: payload.revision, newer_unsaved_changes: window.TlamatiniCanvasEditing.dirty } : {}) };
    }

    function connect() {
        if (closed || socket?.readyState === WebSocket.OPEN || socket?.readyState === WebSocket.CONNECTING) return;
        const connection = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/interactor/`);
        socket = connection;
        connection.onmessage = async event => {
            let message;
            try { message = JSON.parse(event.data); } catch { return; }
            if (connection !== socket) return;
            if (message.t === 'hello') {
                clientId = message.client_id;
                seen.clear();
                send({ t: 'access', enabled });
                lastMessage = ''; render();
            } else if (message.t === 'cancel' && active?.id === message.id) {
                stop('The chat action stopped. Your editor content is kept.', false, false);
            } else if (message.t === 'command') {
                if (typeof message.id !== 'string' || seen.has(message.id)) return;
                seen.add(message.id);
                if (seen.size > 256) seen.delete(seen.values().next().value);
                let result;
                try { result = await command(message); }
                catch (error) { result = { ok: false, status: userStopped ? 'aborted' : error.status || 'refused', message: error.message }; }
                if (connection === socket && connection.readyState === WebSocket.OPEN) connection.send(JSON.stringify({ t: 'receipt', id: message.id, result }));
            }
        };
        connection.onclose = () => {
            if (connection !== socket) return;
            clientId = '';
            stop('Live editor disconnected · your unsaved text is kept', false, false);
            editor.interactor.setGuide(null);
            render();
            if (!closed) retry = setTimeout(connect, 2000);
        };
        connection.onerror = () => { lastMessage = 'Live editor connection unavailable'; render(); };
    }

    function ask(prompt, finish = false) {
        if (inLongOperation || !clientId || !enabled) return;
        if (chatInput.value.trim()) {
            lastMessage = 'Your chat draft is kept. Send or clear it before asking about the editor.';
            render(); chatInput.focus(); return;
        }
        if (!isMultiTurnEnabled()) {
            lastMessage = 'Enable Multi-Turn to let Tlamatini read and guide the live editor.';
            render(); return;
        }
        chatInput.value = prompt;
        if (finish) editor.interactor.setGuide(null);
        document.getElementById('chat-form').requestSubmit();
    }

    ui.access.addEventListener('change', () => {
        enabled = ui.access.checked;
        if (!enabled) stop('Live editor paused', true);
        else { userStopped = false; lastMessage = ''; }
        try { localStorage.setItem(preference, String(enabled)); } catch { /* optional preference */ }
        send({ t: 'access', enabled }); render();
    });
    ui.stop.addEventListener('click', () => stop('Tutor stopped. Your editor content is kept.', true));
    ui.explain.addEventListener('click', () => ask('Please read the fresh unsaved content in your text editor and explain my selection (or the current file if nothing is selected). Guide me without changing it.'));
    ui.ask.addEventListener('click', () => {
        const guide = editor.interactor.guide();
        if (guide) ask(`Read my live editor and give me another hint for “${guide.label}”. Do not fill it in for me.`);
    });
    ui.continue.addEventListener('click', () => {
        const guide = editor.interactor.guide();
        if (guide) ask(`I have filled “${guide.label}” in your text editor. Read the fresh unsaved content, review my choice, and guide me through the next small step.`, true);
    });
    ui.suggestions.addEventListener('change', () => {
        const guide = editor.interactor.guide();
        if (guide) editor.interactor.setGuide({ ...guide, enabled: ui.suggestions.checked });
    });
    window.addEventListener('tlm:editor-takeover', () => { if (active) stop(); });
    window.addEventListener('tlm:editor-state', event => {
        const ownLoad = active?.opening && event.detail?.origin === 'load';
        if (active && !ownLoad && event.detail?.origin !== 'interactor' && (event.detail?.docChanged || event.detail?.selectionSet)) stop();
        render();
    });
    document.addEventListener('tlm-chat-submitted', render);
    // The chat's busy state is reflected in its Send/Cancel button. Observe that
    // existing signal rather than adding a background polling timer.
    const submit = document.querySelector('#chat-form button[type="submit"]');
    if (submit) new MutationObserver(render).observe(submit, { childList: true, attributes: true, subtree: true });
    window.addEventListener('pagehide', () => { closed = true; clearTimeout(retry); stop('', false, false); socket?.close(); });
    window.addEventListener('pageshow', event => { if (event.persisted) { closed = false; connect(); } });
    window.TlamatiniInteractor = {
        stop: () => { if (active) stop('Tutor stopped. Your editor content is kept.', true); },
        get clientId() { return enabled ? clientId : ''; },
        get enabled() { return enabled; },
        beforeChat: () => { if (active) stop(); userStopped = false; lastMessage = ''; render(); return enabled ? clientId : ''; },
        cancel: () => stop('Chat cancelled. Your editor content is kept.', false),
    };
    render(); connect();
})();
