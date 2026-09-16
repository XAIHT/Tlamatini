/* Tlamatini Author Banner — Angela López Mendoza */
/* PDF canvas lifecycle and request bridge. PDF.js runs in an isolated frame. */
(() => {
    'use strict';
    const CHANNEL = 'tlamatini-pdf-canvas';
    const host = document.getElementById('pdf-canvas-host');
    const editor = document.getElementById('editor-container');
    let current = null;
    let requestId = 0;

    function createRequestId() {
        if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
        // Frozen Tlamatini also serves plain HTTP over LAN addresses, where
        // randomUUID is unavailable. getRandomValues still provides secure bytes.
        const bytes = crypto.getRandomValues(new Uint8Array(16));
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
        return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
    }

    function cancelPreparation(state) {
        state.contextAbort?.abort();
        if (state.contextRequestId && state.contextJobPending) {
            const form = new FormData();
            form.append('request_id', state.contextRequestId);
            void fetch('/agent/cancel_pdf_context/', {
                method: 'POST', credentials: 'same-origin', keepalive: true,
                headers: { 'X-CSRFToken': getCsrfToken() }, body: form,
            }).catch(() => {});
        }
    }

    function uploadContext(form, state) {
        return new Promise((resolve, reject) => {
            const request = new XMLHttpRequest();
            const signal = state.contextAbort.signal;
            const abort = () => request.abort();
            request.open('POST', '/agent/prepare_pdf_context/');
            request.setRequestHeader('X-CSRFToken', getCsrfToken());
            request.responseType = 'json';
            request.upload.onprogress = event => {
                window.TlamatiniPdfProgress?.update('upload', event.loaded, event.lengthComputable ? event.total : 0);
            };
            request.onload = () => {
                signal.removeEventListener('abort', abort);
                if (request.status >= 200 && request.status < 300 && request.response?.job) resolve(request.response);
                else reject(new Error(request.response?.error || 'PDF upload failed. Please try again.'));
            };
            request.onerror = () => { signal.removeEventListener('abort', abort); reject(new Error('PDF upload failed. Check the connection.')); };
            request.onabort = () => { signal.removeEventListener('abort', abort); reject(new DOMException('PDF context preparation cancelled.', 'AbortError')); };
            signal.addEventListener('abort', abort, { once: true });
            request.send(form);
            if (signal.aborted) abort();
        });
    }

    function syncButtons() {
        if (!current) return;
        for (const button of [copyCanvasButton, contextButton]) {
            button.disabled = !current.ready || inLongOperation || !contextEnabled ||
                (button === contextButton && current.contextBusy);
            button.style.backgroundColor = button.disabled ? '#808080' : 'darkgreen';
        }
        if (canvasSettedAsContext) {
            contextButton.style.backgroundColor = 'gray';
            contextButtonClicked = true;
            contextButton.textContent = 'Used as context';
        }
    }

    function close() {
        if (!current) return;
        current.resolve(false);
        current.textRequest?.reject(new Error('PDF was closed.'));
        if (current.contextBusy) window.TlamatiniPdfProgress?.cancelPreparation();
        cancelPreparation(current);
        // Removing the browsing context terminates its worker, rendering tasks,
        // range reads and observers, even during password/loading/extraction.
        current.frame.remove();
        current = null;
        host.hidden = true;
        editor.hidden = false;
    }

    function open(file) {
        close();
        const frame = document.createElement('iframe');
        frame.title = `PDF: ${file.name}`;
        frame.src = host.dataset.viewerUrl;
        const ready = new Promise(resolve => {
            current = { file, frame, resolve, ready: false, textRequest: null, preparedByMode: new Map() };
        });
        frame.addEventListener('error', () => {
            if (current?.frame === frame) current.resolve(false);
        });
        editor.hidden = true;
        host.hidden = false;
        host.replaceChildren(frame);
        syncButtons();
        return ready;
    }

    function getText() {
        if (!current?.ready) return Promise.reject(new Error('The PDF is still loading or could not be opened.'));
        if (current.textRequest) return current.textRequest.promise;
        const id = ++requestId;
        let resolve, reject;
        const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
        current.textRequest = { id, promise, resolve, reject };
        current.frame.contentWindow.postMessage({ channel: CHANNEL, type: 'text', requestId: id }, window.location.origin);
        return promise;
    }

    function prepareContext() {
        if (!current?.ready) return Promise.reject(new Error('The PDF is not ready.'));
        if (current.contextRequest) return current.contextRequest;
        const state = current;
        state.contextAbort = new AbortController();
        state.contextRequestId = null;
        state.contextJobPending = false;
        state.contextBusy = true;
        syncButtons();
        const showStatus = message => state.frame.contentWindow?.postMessage({
            channel: CHANNEL, type: 'context-status', message,
        }, window.location.origin);
        let prepared = null;
        state.contextRequest = (async () => {
            try {
                const processImages = await window.TlamatiniPdfProgress.open(state.file, () => cancelPreparation(state));
                if (current !== state || state.contextAbort.signal.aborted) {
                    throw new DOMException('PDF context preparation cancelled.', 'AbortError');
                }
                prepared = state.preparedByMode.get(processImages);
                if (prepared) {
                    state.prepared = prepared;
                    return prepared;
                }
                state.contextRequestId = createRequestId();
                state.contextJobPending = true;
                showStatus(processImages ? 'Preparing PDF context: extracting all pages, text and images…' : 'Preparing PDF context: extracting selectable text…');
                const form = new FormData();
                form.append('process_images', String(processImages));
                form.append('request_id', state.contextRequestId);
                form.append('pdf', state.file, state.file.name);
                // Kept only in this document's memory, never localStorage or logs.
                form.append('password', state.password || '');
                const started = await uploadContext(form, state);
                state.contextJob = started.job;
                if (current !== state || state.contextAbort.signal.aborted) cancelPreparation(state);
                while (current === state && !state.contextAbort.signal.aborted) {
                    const poll = await fetch(`/agent/pdf_context_status/?job=${encodeURIComponent(started.job)}`, {
                        credentials: 'same-origin', signal: state.contextAbort.signal,
                    });
                    const result = await poll.json();
                    if (!poll.ok || ['error', 'cancelled'].includes(result.status)) {
                        throw new Error(result.error || result.message || 'PDF context preparation failed.');
                    }
                    if (result.status === 'complete') {
                        state.contextJobPending = false;
                        prepared = result.result;
                        state.prepared = prepared;
                        state.preparedByMode.set(processImages, prepared);
                        return prepared;
                    }
                    showStatus(result.message || 'Preparing PDF context…');
                    window.TlamatiniPdfProgress?.update(result.stage || 'extract', result.completed || 0, result.total || 0, result.message);
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
                throw new DOMException('PDF context preparation cancelled.', 'AbortError');
            } catch (error) {
                if (error.name !== 'AbortError' && current === state) window.TlamatiniPdfProgress?.fail(error.message);
                cancelPreparation(state);
                throw error;
            } finally {
                state.contextBusy = false;
                state.contextJobPending = false;
                state.contextRequest = null;
                if (current === state) {
                    showStatus(prepared?.analysis_warnings
                        ? `PDF context includes ${prepared.analysis_warnings} image analysis warnings. See the saved analysis reports.` : '');
                    syncButtons();
                }
            }
        })();
        return state.contextRequest;
    }

    window.addEventListener('message', event => {
        if (!current || event.source !== current.frame.contentWindow || event.origin !== window.location.origin || event.data?.channel !== CHANNEL) return;
        const message = event.data;
        if (message.type === 'initialized') {
            current.frame.contentWindow.postMessage({ channel: CHANNEL, type: 'open', file: current.file }, window.location.origin);
        } else if (message.type === 'ready') {
            current.ready = true;
            current.password = message.password || '';
            syncButtons();
            current.resolve(true);
        } else if (message.type === 'error') {
            current.ready = false;
            syncButtons();
            current.resolve(false);
            current.textRequest?.reject(new Error(message.message));
            current.textRequest = null;
        } else if (['text', 'text-error'].includes(message.type) && current.textRequest?.id === message.requestId) {
            if (message.type === 'text') current.textRequest.resolve(message.text);
            else current.textRequest.reject(new Error(message.message));
            current.textRequest = null;
        }
    });
    window.TlamatiniPdfCanvas = {
        open, close, getText, prepareContext, syncButtons,
        get active() { return current !== null; },
        get file() { return current?.file || null; },
        get contextFilename() { return current?.prepared?.context_filename || null; },
    };
})();
