/* Tlamatini Author Banner — Angela López Mendoza */
/* exported canvasLoaded, canvasSettedAsContext, contextButtonClicked, actualContextDir, clearContextEnabled */
/* global canvasSource:writable, canvasLoaded:writable, canvasSettedAsContext:writable, contextButtonClicked:writable,
   filenameSpan, canvasRefreshState:writable, canvasRefreshMessage:writable,
   contextButton, enableCanvasButtons, invalidateCanvasReads,
   syncCanvasRefreshButton, sendChatSocketMessage, getCanvasContextPayload,
   contextEnabled, cleanCanvas, showPendingContextSelection, restorePendingContextSelection,
   getCanvasGeneration, actualContextDir:writable, clearContextEnabled:writable, clearContextButton,
   contextInfoDiv, updateViewContextDirMenuState, setContextText */
(() => {
    'use strict';
    const bar = document.getElementById('canvas-tabs');
    if (!bar) return;
    const contextBar = document.getElementById('canvas-context-documents');
    const es = bar.dataset.language === 'es';
    const say = (en, spanish) => es ? spanish : en;
    const docs = new Map();
    let active = null, switching = false, signature = '', pendingContext = null, contextNotice = '';
    let selected = new Map();
    const uuid = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), x => x.toString(16).padStart(2, '0')).join('');
    const editing = () => window.TlamatiniCanvasEditing;
    const textEditor = () => window.TlamatiniTextEditor;
    const pdf = () => window.TlamatiniPdfCanvas;

    function metadata(doc) {
        const live = active === doc.id && !switching;
        const inspect = live && doc.kind !== 'pdf' ? textEditor().inspect() : doc.editor?.editor;
        const text = live ? editing().text : doc.editor?.editor.currentText || '';
        const dirty = doc.kind !== 'pdf' && (live ? editing().dirty : !!doc.editor &&
            (!doc.editor.current.persisted || text !== doc.editor.current.baseline));
        const context = selected.get(doc.id);
        const filename = live ? (pdf()?.file?.name || textEditor().filename || doc.name) : doc.name;
        return { document_id: doc.id, filename,
            revision: inspect?.revision ?? doc.revision ?? 0, active: live, dirty: !!dirty,
            context: !!context, kind: doc.kind,
            stale: !!context && (context.filename !== filename ||
                (doc.kind !== 'pdf' && context.content !== text) || context.revision !== (inspect?.revision ?? doc.revision ?? 0)) };
    }
    const list = () => [...docs.values()].map(metadata);
    const anyUnsaved = () => list().some(doc => doc.dirty);
    const hasSaving = () => !!editing()?.busy;

    function renderContext() {
        const meta = active && docs.has(active) ? metadata(docs.get(active)) : null;
        canvasSettedAsContext = !!meta?.context;
        contextButtonClicked = !!meta?.context && !meta.stale;
        contextButton.textContent = pendingContext ? say('Updating context…', 'Actualizando contexto…')
            : meta?.stale ? say('Update context', 'Actualizar contexto')
            : meta?.context ? say('Remove from context', 'Quitar del contexto') : say('Use as context', 'Usar como contexto');
        contextButton.disabled = !meta || !contextEnabled || !!pendingContext ||
            (meta.kind === 'pdf' && !pdf()?.ready);
        contextButton.classList.toggle('canvas-context-selected', !!meta?.context);
        contextBar.replaceChildren();
        contextBar.hidden = !selected.size && !pendingContext && !contextNotice;
        if (contextNotice) {
            const notice = document.createElement('span');
            notice.textContent = contextNotice;
            notice.setAttribute('role', 'status');
            contextBar.append(notice);
        }
        if (selected.size) {
            const label = document.createElement('span');
            label.textContent = say('Chat context:', 'Contexto del chat:');
            contextBar.append(label);
        }
        for (const [id, source] of selected) {
            const chip = document.createElement('button');
            chip.type = 'button';
            chip.textContent = `${source.filename} ×`;
            chip.title = say('Remove this saved snapshot from chat context', 'Quitar esta captura del contexto del chat');
            chip.setAttribute('aria-label', `${say('Remove context', 'Quitar contexto')}: ${source.filename}`);
            chip.disabled = !!pendingContext || !contextEnabled;
            chip.addEventListener('click', () => changeContext(id, true));
            contextBar.append(chip);
        }
    }

    function updated() {
        if (switching) return;
        const surface = document.getElementById('canvas-document-surface');
        if (active) surface?.setAttribute('aria-labelledby', `canvas-tab-${active}`);
        else surface?.removeAttribute('aria-labelledby');
        if (active && docs.has(active)) {
            const doc = docs.get(active);
            doc.name = pdf()?.file?.name || textEditor().filename || doc.name;
        }
        const items = list();
        const next = JSON.stringify(items.map(item => ({ ...item, revision: 0 })));
        if (next !== signature) {
            signature = next;
            const focused = bar.contains(document.activeElement) ? document.activeElement?.closest('[data-document-id]')?.dataset.documentId : null;
            bar.replaceChildren(...items.map(item => {
                const slot = document.createElement('div');
                slot.className = 'canvas-document-tab';
                slot.dataset.documentId = item.document_id;
                slot.classList.toggle('is-active', item.active);
                const button = document.createElement('button');
                button.type = 'button'; button.setAttribute('role', 'tab');
                button.id = `canvas-tab-${item.document_id}`;
                button.dataset.documentId = item.document_id;
                button.setAttribute('aria-controls', 'canvas-document-surface');
                button.setAttribute('aria-selected', String(item.active));
                button.tabIndex = item.active ? 0 : -1;
                button.title = docs.get(item.document_id).title || item.filename;
                const name = document.createElement('span'); name.className = 'canvas-tab-name'; name.textContent = item.filename;
                const type = document.createElement('span'); type.className = 'canvas-tab-kind';
                type.textContent = item.kind === 'pdf' ? 'PDF' : item.filename.split('.').pop().slice(0, 10).toUpperCase();
                button.append(type, name);
                if (item.dirty) { const star = document.createElement('span'); star.className = 'canvas-tab-dirty'; star.textContent = '*'; star.setAttribute('aria-label', say('Unsaved changes', 'Cambios sin guardar')); button.append(star); }
                if (item.context) { const badge = document.createElement('span'); badge.className = 'canvas-tab-context'; badge.textContent = item.stale ? say('Context · older', 'Contexto · anterior') : say('Context', 'Contexto'); button.append(badge); }
                button.addEventListener('click', () => activate(item.document_id));
                button.addEventListener('keydown', event => {
                    if (!['ArrowLeft', 'ArrowRight', 'Home', 'End', 'Delete'].includes(event.key)) return;
                    event.preventDefault();
                    if (event.key === 'Delete') { void close(item.document_id); return; }
                    const ids = [...docs.keys()], at = ids.indexOf(item.document_id);
                    const to = event.key === 'Home' ? 0 : event.key === 'End' ? ids.length - 1 : (at + (event.key === 'ArrowRight' ? 1 : -1) + ids.length) % ids.length;
                    void activate(ids[to]).then(() => document.getElementById(`canvas-tab-${ids[to]}`)?.focus());
                });
                const exit = document.createElement('button'); exit.type = 'button'; exit.className = 'canvas-tab-close'; exit.textContent = '×';
                exit.setAttribute('aria-label', `${say('Close', 'Cerrar')} ${item.filename}`);
                exit.addEventListener('click', () => close(item.document_id));
                slot.append(button, exit); return slot;
            }));
            if (focused) document.getElementById(`canvas-tab-${focused}`)?.focus({ preventScroll: true });
            document.getElementById(`canvas-tab-${active}`)?.parentElement.scrollIntoView({ block: 'nearest', inline: 'nearest' });
        }
        renderContext();
    }

    function capture() {
        if (!active || !docs.has(active)) return;
        const doc = docs.get(active), meta = metadata(doc);
        doc.name = meta.filename; doc.revision = meta.revision;
        doc.source = canvasSource;
        doc.title = filenameSpan.title;
        doc.label = filenameSpan.textContent;
        doc.refreshState = canvasRefreshState; doc.refreshMessage = canvasRefreshMessage;
        doc.markdown = window.TlamatiniMarkdownCanvas?.snapshot();
        doc.editor = editing().suspend();
        doc.pdf = pdf().suspend();
        window.TlamatiniMarkdownCanvas?.close();
    }

    function beforeSwitch(origin, next) {
        if (hasSaving()) throw new Error(say('Wait for the save to finish before switching documents.', 'Espera a que termine el guardado para cambiar de documento.'));
        window.dispatchEvent(new CustomEvent('tlm:canvas-document-switch', { detail: { origin, previous: active, document_id: next } }));
        invalidateCanvasReads();
        capture();
        switching = true;
    }

    function beginOpen(origin = 'user') {
        if (docs.size >= 32) throw new Error(say('Close a document before opening more than 32 Canvas tabs.', 'Cierra un documento antes de abrir más de 32 pestañas del Canvas.'));
        beforeSwitch(origin, null);
        active = null; canvasSource = null; canvasLoaded = false;
        canvasSettedAsContext = contextButtonClicked = false;
        return true;
    }

    function commitOpen(kind = 'text') {
        const state = textEditor().inspect();
        const id = kind === 'pdf' ? uuid() : state.document_id;
        const name = pdf()?.file?.name || state.filename;
        docs.set(id, { id, name, kind, revision: state.revision, title: filenameSpan.title });
        active = id; switching = false;
        updated(); editing().sync();
        return id;
    }

    async function activate(id, { origin = 'user' } = {}) {
        if (!docs.has(id)) throw new Error(say('This document is no longer open.', 'Este documento ya no está abierto.'));
        if (active === id) return true;
        try { beforeSwitch(origin, id); }
        catch (error) { if (origin === 'interactor') throw error; await window.tlmAlert(error.message); return false; }
        const doc = docs.get(id);
        active = id;
        canvasSource = doc.source; canvasLoaded = true;
        filenameSpan.textContent = doc.label; filenameSpan.title = doc.title;
        canvasRefreshState = doc.refreshState; canvasRefreshMessage = doc.refreshMessage;
        editing().resume(doc.editor);
        pdf().resume(doc.pdf);
        if (doc.markdown && doc.editor) {
            window.TlamatiniMarkdownCanvas.open(doc.name, textEditor().getText(), doc.editor.current.file);
            window.TlamatiniMarkdownCanvas.restore(doc.markdown);
        }
        switching = false;
        enableCanvasButtons(); syncCanvasRefreshButton(); updated(); editing().sync();
        return true;
    }

    async function close(id = active) {
        if (!docs.has(id)) return false;
        if (!await activate(id)) return false;
        if (!await editing().confirmDiscard()) return false;
        const ids = [...docs.keys()], index = ids.indexOf(id);
        beforeSwitch('user', null);
        const doc = docs.get(id);
        pdf().dispose(doc.pdf);
        docs.delete(id); active = null;
        switching = false;
        // A pinned snapshot remains explicitly listed in the context strip even
        // when its editor closes. Closing an editor never silently changes RAG.
        if (docs.size) await activate([...docs.keys()][Math.min(index, docs.size - 1)]);
        else { await cleanCanvas(true, true, true); updated(); editing().sync(); }
        return true;
    }

    function cancelPendingContext() {
        const operation = pendingContext;
        pendingContext = null;
        if (!operation) return;
        if (operation.headerPending) restorePendingContextSelection();
        if (operation.pdfToken) window.TlamatiniPdfProgress?.finish(operation.pdfToken, false);
        if (operation.preparing) pdf()?.cancelContextPreparation();
    }

    async function changeContext(id = active, remove = false) {
        if (pendingContext || !contextEnabled || switching) return false;
        if (!remove && (id !== active || !docs.has(id))) return false;
        const operation = { request_id: uuid(), candidate: new Map(selected), pdfToken: null,
            preparing: false, headerPending: false };
        pendingContext = operation;
        updated();
        try {
            const candidate = operation.candidate;
            if (remove) candidate.delete(id);
            else {
                const meta = metadata(docs.get(id));
                if (meta.context && !meta.stale) candidate.delete(id);
                else {
                    const generation = getCanvasGeneration();
                    operation.preparing = true;
                    const payload = await getCanvasContextPayload();
                    operation.preparing = false;
                    if (pendingContext !== operation) {
                        if (payload.context_token) window.TlamatiniPdfProgress?.finish(payload.context_token, false);
                        return false;
                    }
                    operation.pdfToken = payload.context_token || null;
                    if (id !== active || generation !== getCanvasGeneration() ||
                        metadata(docs.get(id)).revision !== meta.revision) {
                        cancelPendingContext();
                        return false;
                    }
                    candidate.set(id, { document_id: id, filename: meta.filename, revision: meta.revision,
                        ...(payload.context_token ? { context_token: payload.context_token } : { content: payload.content }) });
                }
            }
            if (!sendChatSocketMessage({ type: 'set-canvas-documents-as-context', message: '', request_id: operation.request_id,
                documents: [...candidate.values()] })) {
                if (pendingContext === operation) cancelPendingContext();
                return false;
            }
            operation.headerPending = true;
            showPendingContextSelection([...candidate.values()].map(doc => doc.filename).join(', ') || say('No documents', 'Sin documentos'));
            return true;
        } catch (error) {
            if (pendingContext === operation) cancelPendingContext();
            if (error.name === 'AbortError') return false;
            throw error;
        } finally { updated(); }
    }

    function contextResult(data) {
        if (!pendingContext || data.request_id !== pendingContext.request_id) return false;
        const operation = pendingContext;
        if (data.success) { selected = operation.candidate; contextNotice = ''; }
        else {
            restorePendingContextSelection();
            if (!operation.pdfToken) void window.tlmAlert(data.message || say('Context was not changed.', 'El contexto no cambió.'));
        }
        pendingContext = null;
        if (operation.pdfToken) window.TlamatiniPdfProgress?.finish(operation.pdfToken, data.success === true, data.message);
        if (data.success && !selected.size) {
            actualContextDir = null; clearContextEnabled = false;
            clearContextButton.setAttribute('style', 'display:none!important');
            updateViewContextDirMenuState(); setContextText('<<<...>>>');
            contextInfoDiv.classList.add('context-info-invisible');
        }
        updated();
        return true;
    }

    function connectionLost() {
        cancelPendingContext();
        // A committed update can lose its acknowledgement. Do not present the
        // old or proposed set as confirmed while the server state is unknown.
        selected.clear();
        contextNotice = say('Connection lost. Reconnect to verify chat context; open documents are kept.',
            'Conexión perdida. Reconecta para verificar el contexto; los documentos abiertos se conservan.');
        updated();
    }

    function clearContext() {
        cancelPendingContext();
        selected.clear(); contextNotice = '';
        updated();
    }

    function keydown(event) {
        const surface = document.getElementById('canvas-document-surface');
        if (event.defaultPrevented || event.isComposing || event.metaKey || !(surface.contains(document.activeElement) || bar.contains(document.activeElement)) ||
            document.querySelector('dialog[open], .modal.show')) return;
        const ctrl = event.ctrlKey && !event.altKey && event.key === 'Tab';
        const alternate = event.altKey && !event.ctrlKey && !event.shiftKey && ['PageUp', 'PageDown'].includes(event.key);
        if (!ctrl && !alternate) return;
        if (docs.size < 2) return;
        event.preventDefault(); event.stopPropagation();
        void cycle(ctrl ? (event.shiftKey ? -1 : 1) : event.key === 'PageUp' ? -1 : 1);
    }
    async function cycle(direction) {
        if (![1, -1].includes(direction) || docs.size < 2) return;
        const ids = [...docs.keys()];
        const id = ids[(ids.indexOf(active) + direction + ids.length) % ids.length];
        const changed = await activate(id);
        if (changed) document.getElementById(`canvas-tab-${id}`)?.focus();
        return changed;
    }
    document.addEventListener('keydown', keydown, true);
    window.TlamatiniCanvasTabs = { list, get: id => docs.get(id), activeId: () => active, activate, close, cycle,
        beginOpen, commitOpen, updated, anyUnsaved, hasSaving, changeContext, contextResult, connectionLost, clearContext,
        sessionRestored: clearContext,
        pdfRefreshed: () => {
            const doc = docs.get(active);
            if (doc?.kind === 'pdf') { doc.revision = (doc.revision || 0) + 1; updated(); }
        },
        adoptEditor: previous => {
            if (!switching && active && docs.has(active)) {
                const doc = docs.get(active);
                const revision = previous?.document_id === active ? previous.revision : 0;
                textEditor().adoptIdentity(active, Math.max(revision, doc.revision ?? 0) + 1);
            }
        },
        get transitioning() { return switching; },
        get contextPending() { return !!pendingContext; },
    };
    updated();
})();
