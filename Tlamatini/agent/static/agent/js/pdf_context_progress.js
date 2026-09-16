/* Tlamatini Author Banner — Angela López Mendoza */
/* Accessible native modal; all behavior lives outside the HTML template. */
(() => {
    'use strict';
    const dialog = document.getElementById('pdf-context-progress');
    const message = document.getElementById('pdf-context-progress-message');
    const action = document.getElementById('pdf-context-progress-action');
    const proceed = document.getElementById('pdf-context-continue');
    const processImages = document.getElementById('pdf-context-process-images');
    const elapsed = document.getElementById('pdf-context-progress-elapsed');
    const stages = ['upload', 'extract', 'analyze', 'rag'];
    let cancel = null;
    let timer = null;
    let started = 0;
    let expectedToken = null;
    let warningCount = 0;
    let pendingChoice = null;
    let fileSize = 0;

    function tick() {
        const seconds = Math.floor((performance.now() - started) / 1000);
        elapsed.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    }
    function stopTimer() { clearInterval(timer); timer = null; }
    function close() {
        if (pendingChoice) {
            pendingChoice.reject(new DOMException('PDF context preparation cancelled.', 'AbortError'));
            pendingChoice = null;
        }
        const callback = cancel;
        cancel = null;
        stopTimer();
        // Closing during RAG only hides the dialog; that work is still active.
        if (callback) setTitleBusy(false, 'pdf-context');
        dialog.close();
        callback?.();
    }
    function update(stage, completed, total, detail) {
        const position = stages.indexOf(stage);
        stages.forEach((name, index) => {
            const row = dialog.querySelector(`[data-pdf-stage="${name}"]`);
            const bar = row.querySelector('progress');
            const count = row.querySelector('output');
            if (name === 'analyze' && !processImages.checked) {
                row.dataset.state = 'skipped';
                bar.max = 1; bar.value = 0; count.textContent = 'Skipped';
                return;
            }
            row.dataset.state = index < position ? 'complete' : index === position ? 'active' : 'pending';
            if (index < position) { bar.max = 1; bar.value = 1; count.textContent = 'Done'; }
            else if (index === position) {
                if (total > 0) {
                    bar.max = total; bar.value = completed;
                    count.textContent = stage === 'upload' ? `${Math.round(completed / total * 100)}%` : `${completed} / ${total}`;
                } else { bar.removeAttribute('value'); count.textContent = 'Working…'; }
            }
        });
        if (detail) message.textContent = detail;
    }
    function open(file, onCancel) {
        if (dialog.open) dialog.close();
        stopTimer();
        cancel = onCancel;
        expectedToken = null;
        warningCount = 0;
        fileSize = file.size;
        processImages.checked = false;
        processImages.disabled = false;
        proceed.hidden = false;
        document.getElementById('pdf-context-progress-file').textContent = file.name;
        document.getElementById('pdf-context-progress-size').textContent = file.size < 1024 * 1024
            ? `${(file.size / 1024).toFixed(1)} KB` : `${(file.size / 1024 / 1024).toFixed(1)} MB`;
        stages.forEach(name => {
            const row = dialog.querySelector(`[data-pdf-stage="${name}"]`);
            row.dataset.state = 'pending';
            row.querySelector('progress').value = 0;
            row.querySelector('progress').max = 1;
            row.querySelector('output').textContent = 'Pending';
        });
        action.textContent = 'Cancel';
        elapsed.textContent = '0:00';
        updateImageOption();
        const choice = new Promise((resolve, reject) => { pendingChoice = { resolve, reject }; });
        dialog.showModal();
        return choice;
    }
    function updateImageOption() {
        document.getElementById('pdf-context-extract-label').textContent = processImages.checked
            ? '2. Read text and extract images' : '2. Read document text';
        const row = dialog.querySelector('[data-pdf-stage="analyze"]');
        row.dataset.state = processImages.checked ? 'pending' : 'skipped';
        row.querySelector('output').textContent = processImages.checked ? 'Pending' : 'Skipped';
        message.textContent = processImages.checked
            ? 'Ready to prepare text and analyze images. Press Continue to begin.'
            : 'Ready to prepare selectable text. Press Continue to begin.';
    }
    function loadingContext(token, warnings = 0) {
        expectedToken = token;
        warningCount = warnings;
        cancel = null;
        action.textContent = 'Close';
        update('rag', 0, 0, (processImages.checked
            ? 'PDF processing is complete. Loading its text and image analyses into Tlamatini’s context…'
            : 'PDF text extraction is complete. Loading its text into Tlamatini’s context…') +
            (warningCount ? ` ${warningCount} image analyses were incomplete; details are included in the context.` : ''));
    }
    function finish(token, success) {
        if (token !== expectedToken) return;
        expectedToken = null;
        setTitleBusy(false, 'pdf-context');
        stopTimer();
        action.textContent = 'Close';
        cancel = null;
        if (success) {
            update('rag', 1, 1, 'Your PDF context is ready. You can now ask Tlamatini about the document.' +
                (warningCount ? ` ${warningCount} image analyses were incomplete. Check the saved analysis reports before relying on visual details.` : ''));
            dialog.close();
        } else fail('The PDF was processed, but context loading failed. Please retry and check the configured model service if the problem persists.');
    }
    function fail(detail) {
        if (pendingChoice) { pendingChoice.reject(new Error(detail)); pendingChoice = null; }
        proceed.hidden = true;
        processImages.disabled = true;
        stopTimer(); cancel = null; action.textContent = 'Close';
        expectedToken = null;
        setTitleBusy(false, 'pdf-context');
        message.textContent = detail;
    }
    function connectionLost() {
        if (expectedToken) fail('The live connection was lost during context loading. Reconnect to check the context status.');
    }
    action.addEventListener('click', close);
    processImages.addEventListener('change', updateImageOption);
    proceed.addEventListener('click', () => {
        if (!pendingChoice) return;
        const { resolve } = pendingChoice;
        pendingChoice = null;
        processImages.disabled = true;
        proceed.hidden = true;
        setTitleBusy(true, 'pdf-context');
        started = performance.now(); tick(); timer = setInterval(tick, 1000);
        update('upload', 0, fileSize, 'Uploading the PDF to Tlamatini…');
        resolve(processImages.checked);
    });
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    // Also handle dismissal through the native close API or another UI control.
    // A queued close event from an earlier run must not cancel a newly opened one.
    dialog.addEventListener('close', () => { if (!dialog.open && cancel) close(); });
    window.TlamatiniPdfProgress = { open, update, loadingContext, finish, fail, connectionLost, cancelPreparation: close };
})();
