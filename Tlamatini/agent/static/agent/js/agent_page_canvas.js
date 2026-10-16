/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela López Mendoza.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// ============================================================
// agent_page_canvas.js  –  Canvas / code-editor operations
// ============================================================

// Shared filter for source/text files and the canvas's dedicated PDF renderer.
// Other binary formats are not supported. The trailing
// `text/*` also lets the dialog accept extensionless text files (Makefile,
// Dockerfile, LICENSE, README). The native dialog still offers "All Files" so
// nothing is permanently hidden — this just defaults the view to source code.
const SOURCE_CODE_ACCEPT = [
    '.txt', '.text', '.log', '.md', '.markdown', '.rst', '.adoc', '.asciidoc', '.org', '.tex',
    '.c', '.h', '.cc', '.cpp', '.cxx', '.c++', '.hh', '.hpp', '.hxx', '.h++', '.ino', '.cu', '.cuh',
    '.cs', '.java', '.kt', '.kts', '.scala', '.groovy', '.gradle', '.go', '.rs', '.swift', '.m', '.mm',
    '.py', '.pyw', '.pyi', '.rb', '.rake', '.php', '.phtml', '.pl', '.pm', '.lua', '.tcl', '.r', '.jl',
    '.dart', '.nim', '.cr', '.zig', '.d', '.v', '.sv', '.svh', '.vhd', '.vhdl',
    '.js', '.mjs', '.cjs', '.jsx', '.ts', '.mts', '.cts', '.tsx', '.vue', '.svelte', '.astro', '.coffee',
    '.html', '.htm', '.xhtml', '.xml', '.xsl', '.xslt', '.svg', '.css', '.scss', '.sass', '.less', '.styl',
    '.json', '.json5', '.jsonc', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf', '.config',
    '.properties', '.env', '.editorconfig',
    '.csv', '.tsv', '.sql', '.graphql', '.gql', '.proto', '.prisma',
    '.sh', '.bash', '.zsh', '.fish', '.bat', '.cmd', '.ps1', '.psm1', '.psd1', '.awk', '.sed', '.vim',
    '.asm', '.s', '.f', '.f90', '.f95', '.f03', '.for', '.pas', '.pp', '.ada', '.adb', '.ads',
    '.cob', '.cbl', '.clj', '.cljs', '.cljc', '.edn', '.ex', '.exs', '.erl', '.hrl', '.hs', '.lhs',
    '.ml', '.mli', '.fs', '.fsx', '.fsi', '.elm', '.lisp', '.lsp', '.scm', '.rkt',
    '.cmake', '.mk', '.mak', '.make', '.dockerfile', '.bazel', '.bzl',
    '.sln', '.csproj', '.vbproj', '.vcxproj', '.fsproj', '.pom', '.sbt',
    '.gitignore', '.gitattributes', '.dockerignore',
    '.jinja', '.jinja2', '.j2', '.twig', '.erb', '.ejs', '.hbs', '.handlebars', '.mustache',
    '.pug', '.haml', '.liquid',
    '.flw', '.pmt', '.fpmt', '.pdf', 'application/pdf',
    'text/*',
].join(',');

// Every replacement invalidates pending reads, PDF loads and text extractions.
let canvasLoadGeneration = 0;
// A File is a snapshot, not permission to reread its path. Keep the granted
// handle/entry in this tab only; never infer a server path from a local filename.
let canvasSource = null;
let canvasRefreshWork = null;
let canvasRefreshState = 'empty';
let canvasRefreshMessage = 'Open a file to refresh its content.';
const canvasRefreshStatus = document.getElementById('canvas-refresh-status');
const canvasRefreshCancel = document.getElementById('canvas-refresh-cancel');

function syncCanvasRefreshButton() {
    const busy = !!canvasRefreshWork;
    const locked = !openEnabled || !contextEnabled || inLongOperation;
    const state = busy ? 'refreshing' : locked ? 'locked' : canvasRefreshState;
    const message = locked && !busy ? 'Refresh is available when the current operation finishes.' : canvasRefreshMessage;
    reopenOpenCanvasButton.disabled = busy || locked || !canvasSource?.read;
    reopenOpenCanvasButton.textContent = busy ? 'Refreshing…'
        : canvasRefreshState === 'permission' && canvasSource?.handle?.requestPermission ? 'Allow refresh' : 'Refresh';
    reopenOpenCanvasButton.style.backgroundColor = reopenOpenCanvasButton.disabled ? '#808080' : 'darkgreen';
    reopenOpenCanvasButton.title = message;
    reopenOpenCanvasButton.dataset.state = state;
    reopenOpenCanvasButton.setAttribute('aria-busy', String(busy));
    if (canvasRefreshStatus) {
        canvasRefreshStatus.textContent = message;
        canvasRefreshStatus.parentElement.dataset.state = state;
    }
    if (canvasRefreshCancel) canvasRefreshCancel.hidden = !busy;
    if (busy) contextButton.disabled = true;
}

function canvasRefreshFeedback(state, message) {
    canvasRefreshState = state;
    canvasRefreshMessage = message;
    syncCanvasRefreshButton();
}

function cancelCanvasRefresh() {
    if (!canvasRefreshWork) return;
    const work = canvasRefreshWork;
    work.abort();
    if (work.contextPreparing) window.TlamatiniPdfProgress?.cancelPreparation();
    canvasRefreshWork = null;
    canvasRefreshFeedback(work.committed ? 'updated' : 'ready', work.committed
        ? 'Canvas refreshed. Context update cancelled; Use as context to update chat context.'
        : 'Refresh cancelled. The displayed content was kept.');
}

function forgetCanvasSource() {
    cancelCanvasRefresh();
    canvasSource = null;
    canvasRefreshFeedback('empty', 'Open a file to refresh its content.');
}

function rememberCanvasSource(source) {
    canvasSource = source;
    canvasRefreshFeedback(source.read ? 'ready' : 'unavailable', source.read
        ? 'Refresh reads the latest content of this file.'
        : 'This browser supplied a copy without access to the original. Open the file in Chrome or Edge on localhost or HTTPS to enable Refresh.');
}

function localCanvasSource(file, access, text = null) {
    const handle = access?.handle;
    const entry = access?.entry;
    return { name: file.name, file, text, handle,
        read: handle?.getFile ? () => handle.getFile()
            : entry?.file ? () => new Promise((resolve, reject) => entry.file(resolve, reject)) : null };
}

async function fetchCanvasSource(filename, signal) {
    const response = await fetch(`/agent/load_canvas/${encodeURIComponent(filename)}/`, {
        cache: 'no-store', credentials: 'same-origin', signal,
    });
    if (response.redirected || response.status === 401 || response.status === 403) {
        throw new Error('Your session expired. Sign in again before refreshing.');
    }
    if (!response.ok) throw new Error(response.status === 404
        ? 'The saved content is no longer available.' : `Could not read the saved content (${response.status}).`);
    return response.text();
}

window.TlamatiniCanvasRefresh = { sync: syncCanvasRefreshButton, cancel: cancelCanvasRefresh,
    contextSelected: () => { if (canvasSource) canvasSource.contextPending = false; },
    get busy() { return !!canvasRefreshWork; } };
canvasRefreshCancel?.addEventListener('click', () => {
    cancelCanvasRefresh();
    if (canvasLoaded && contextEnabled) enableCanvasButtons();
});
syncCanvasRefreshButton();

function getCanvasGeneration() { return canvasLoadGeneration; } // eslint-disable-line no-unused-vars
function getCanvasText() {
    return window.TlamatiniPdfCanvas?.active
        ? window.TlamatiniPdfCanvas.getText()
        : Promise.resolve(textEditorCode.textContent);
}

function getCanvasContextFilename() {
    const filename = filenameSpan.textContent.match(/<<< (.+?) >>>/s)?.[1];
    // The context endpoint writes UTF-8 text to disk. Never label extracted PDF
    // text as .pdf: the RAG file loader would attempt to parse it as PDF bytes.
    return window.TlamatiniPdfCanvas?.active
        ? (window.TlamatiniPdfCanvas.contextFilename || `${filename}.txt`) : filename;
}

async function getCanvasContextPayload() {
    if (window.TlamatiniPdfCanvas?.active) {
        const filename = window.TlamatiniPdfCanvas.file.name;
        const prepared = await window.TlamatiniPdfCanvas.prepareContext();
        window.TlamatiniPdfProgress?.loadingContext(prepared.token, prepared.analysis_warnings);
        return { type: 'set-pdf-canvas-as-context', message: filename, context_token: prepared.token };
    }
    return { type: 'set-canvas-as-context', message: getCanvasContextFilename(), content: textEditorCode.textContent };
}

/**
 * Map a file extension to a highlight.js language class.
 */
function getLanguageClass(extension) {
    if (extension.includes('py')) return 'language-python';
    if (extension.includes('java')) return 'language-java';
    if (extension.includes('js') || extension.includes('jsx') || extension.includes('astro')) return 'language-javascript';
    if (extension.includes('css')) return 'language-css';
    if (extension.includes('cpp') || extension.includes('hpp')) return 'language-cpp';
    if (extension.includes('cu')) return 'language-cpp';
    if (extension.includes('c') || extension.includes('h')) return 'language-c';
    if (extension.includes('sql')) return 'language-sql';
    if (extension.includes('jsp') || extension.includes('xml') || extension.includes('html') || extension.includes('xhtml') || extension.includes('vue')) return 'language-xml';
    if (extension.includes('yaml')) return 'language-yaml';
    if (extension.includes('bash')) return 'language-bash';
    if (extension.includes('ts') || extension.includes('tsx')) return 'language-typescript';
    if (extension.includes('kt')) return 'language-kotlin';
    if (extension.includes('toml')) return 'language-toml';
    if (extension.includes('rs')) return 'language-rust';
    return 'language-text';
}

/**
 * Extract the file extension from a filename.
 */
function extractExtension(filename) {
    return filename.slice((filename.lastIndexOf(".") - 1 >>> 0) + 2);
}

/**
 * Replace the code element in the editor with new content.
 */
function replaceCodeElement(langClass, content) {
    canvasLoadGeneration++;
    window.TlamatiniPdfCanvas?.close();
    window.TlamatiniMarkdownCanvas?.close();
    const newTextEditorCode = document.createElement('code');
    newTextEditorCode.classList.add(langClass);
    newTextEditorCode.textContent = content;
    textEditorCode.parentNode.replaceChild(newTextEditorCode, textEditorCode);
    textEditorCode = newTextEditorCode;
    textEditorCode.addEventListener('input', updateLineNumbers);
    // Markdown source stays verbatim; its separate preview highlights code fences.
    if (langClass !== 'language-markdown') hljs.highlightElement(textEditorCode);
    updateLineNumbers();
}

function displayCanvasText(filename, content, file = null) {
    const markdown = /\.(md|markdown)$/i.test(filename);
    replaceCodeElement(markdown ? 'language-markdown' : getLanguageClass(extractExtension(filename)), content);
    if (markdown) window.TlamatiniMarkdownCanvas?.open(filename, content, file);
}

function loadCanvas(filename) { // eslint-disable-line no-unused-vars
    window.TlamatiniViews?.setCanvasVisible(true);
    if (contextEnabled === false) {
        console.error("Lading canvas is not allowed while Tlamatini is processing a request, function will return false...");
        return false;
    }

    if (canvasSettedAsContext === true) {
        console.log("Detected context was active, so send the message to clean the context and rebuild the RAG...");
        const codeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(codeRegex);
        const type = "unset-canvas-as-context";
        if (result && result[1] && result[1].length > 0 && result[1].includes('...') === false) {
            const filename = result[1];
            sendChatSocketMessage(JSON.stringify({
                'type': type,
                'message': filename
            }));
        }
        console.log("...Rebuild rag action sent.");
    }

    forgetCanvasSource();
    const generation = ++canvasLoadGeneration;
    fetchCanvasSource(filename)
        .then(content => {
            if (generation !== canvasLoadGeneration) return;
            displayCanvasText(filename, content);
            filenameSpan.textContent = `<<< ${filename} >>>`;
            canvasLoaded = true;
            rememberCanvasSource({ name: filename, text: content, read: signal => fetchCanvasSource(filename, signal) });
            enableCanvasButtons();
            canvasSettedAsContext = false;
            contextButtonClicked = false;
            contextButton.textContent = "Use as context";
        })
        .catch(error => console.error('Error loading canvas:', error));
}

async function loadCanvasFromFileInContentGenerated(filename) { // eslint-disable-line no-unused-vars
    if (contextEnabled === false) {
        console.error("Loading canvas is not allowed while Tlamatini is processing a request, function will return false...");
        return false;
    }

    alert(`Please select the file: ${filename}\n\nIt should be located in the 'content_generated' directory.`);

    return loadFileContent();
}

function loadCanvasWithThisContent(content) {
    console.log("loadCanvasWithThisContent()...");
    forgetCanvasSource();
    replaceCodeElement('language-text', content);
    filenameSpan.textContent = `<<< Context, tree of content. >>>`;
    canvasLoaded = true;
    canvasRefreshFeedback('unavailable', 'This canvas contains a context summary, not a refreshable file.');
    enableCanvasButtons();
    canvasSettedAsContext = false;
    contextButtonClicked = false;
    contextButton.textContent = "Use as context";
    console.log("Successfully loaded file from parameter content.");
    console.log("...loadCanvasWithThisContent()");
}

function openCanvas() {
    if (openEnabled === false) {
        console.log("Open canvas is not allowed at this moment...");
        return;
    }
    loadFileContent();
    console.log("Canvas opened.");
}

async function refreshCanvas() {
    const source = canvasSource;
    if (!source?.read || canvasRefreshWork || !openEnabled || !contextEnabled || inLongOperation) return;
    const work = new AbortController();
    canvasRefreshWork = work;
    let generation = canvasLoadGeneration;
    let committed = false;
    const ownsCanvas = () => canvasSource === source && canvasRefreshWork === work &&
        generation === canvasLoadGeneration && !work.signal.aborted && openEnabled && contextEnabled && !inLongOperation;
    const permission = canvasRefreshState === 'permission';
    canvasRefreshFeedback('refreshing', 'Reading the latest file content…');
    try {
        // Permission can only be requested from the explicit button gesture.
        // Refresh never opens a file chooser, including after a refusal.
        if (permission && source.handle?.requestPermission &&
            await source.handle.requestPermission({ mode: 'read' }) !== 'granted') {
            throw new DOMException('Read permission was not granted.', 'NotAllowedError');
        }
        const latest = await source.read(work.signal);
        if (!ownsCanvas()) return;
        const isFile = typeof latest !== 'string';
        const isPdf = isFile && (latest.type === 'application/pdf' || /\.pdf$/i.test(latest.name));
        const content = isPdf ? null : isFile ? await latest.text() : latest;
        if (!ownsCanvas()) return;
        const unchanged = !isPdf && source.text === content;
        const wasContext = canvasSettedAsContext || source.contextPending;
        if (!unchanged) {
            if (isPdf) {
                // PDF remains range-backed. No whole-file scan/hash just to
                // report "unchanged"; reload the viewer from the fresh File.
                await window.TlamatiniPdfCanvas.refresh(latest, work.signal);
                if (!ownsCanvas()) return;
                canvasLoadGeneration++;
            } else {
                const scroll = { top: textEditorPre.scrollTop, left: textEditorPre.scrollLeft };
                const markdown = window.TlamatiniMarkdownCanvas?.snapshot();
                displayCanvasText(source.name, content, isFile ? latest : null);
                if (markdown) window.TlamatiniMarkdownCanvas.restore(markdown);
                textEditorPre.scrollTop = scroll.top;
                textEditorPre.scrollLeft = scroll.left;
            }
            generation = canvasLoadGeneration;
            committed = true;
            work.committed = true;
            source.text = content;
            source.contextPending = wasContext;
        }
        if (isFile) {
            source.file = latest;
            window.TlamatiniMarkdownCanvas?.updateFile(latest);
        }
        if (source.contextPending) {
            // The backend keeps its old context until the new package is ready.
            // Never enqueue an empty-context rebuild before its replacement.
            unsetContextButton();
            work.contextPreparing = true;
            const payload = await getCanvasContextPayload();
            work.contextPreparing = false;
            if (!ownsCanvas()) return;
            if (!sendChatSocketMessage(payload)) {
                if (payload.context_token) window.TlamatiniPdfProgress?.fail('The live connection is unavailable. Reconnect and try again.');
                throw new Error('The live connection is unavailable.');
            }
            source.contextPending = false;
            setContextButton();
            contextButton.disabled = true;
            openEnabled = contextEnabled = false;
            showPendingContextSelection(payload.message);
        }
        canvasRefreshFeedback(unchanged ? 'unchanged' : 'updated',
            `${unchanged ? 'Up to date — no content changes found.' : 'Refreshed from the latest file content.'} Checked ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}.`);
    } catch (error) {
        if (canvasSource !== source || canvasRefreshWork !== work || work.signal.aborted) return;
        if (committed || source.contextPending) {
            unsetContextButton();
            canvasRefreshFeedback('error', 'Canvas refreshed; chat context still uses the previous version. Use as context to update it.');
        } else if (error.name === 'NotAllowedError' || error.name === 'SecurityError') {
            canvasRefreshFeedback('permission', source.handle?.requestPermission
                ? 'Read access is needed. Allow refresh grants access to this same file.'
                : 'Read access was denied. Restore access or use Open to select the file again.');
        } else {
            const reason = error.name === 'NotFoundError' ? 'The file was moved or deleted.'
                : error.name === 'NotReadableError' ? 'The file is being written or is unreadable. Wait for the save to finish.'
                : error.message;
            canvasRefreshFeedback('error', `${reason} Displayed content was kept. Refresh to retry, or use Open to select a file.`);
        }
    } finally {
        if (canvasRefreshWork === work) {
            canvasRefreshWork = null;
            if (canvasLoaded && contextEnabled && !inLongOperation) enableCanvasButtons();
            syncCanvasRefreshButton();
        }
    }
}

function cleanCanvas(preserveContext = false) {
    forgetCanvasSource();
    const codeRegex = /<<<\s*(.+?)\s*>>>/s;
    const result1 = filenameSpan.textContent.match(codeRegex);
    const spanContextString = contextDataSpan.innerText;
    const result2 = spanContextString.match(codeRegex);
    const contextFilename = result2?.[1].split(/[\\/]/).pop();
    if (!preserveContext && canvasSettedAsContext === true && result1 && contextFilename === getCanvasContextFilename()) {
        console.log("Detected context was active, so send the message to clean the context and rebuild the RAG...");
        const innerCodeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(innerCodeRegex);
        const type = "unset-canvas-as-context";
        if (result && result[1] && result[1].length > 0 && result[1].includes('...') === false) {
            const filename = getCanvasContextFilename();
            sendChatSocketMessage(JSON.stringify({
                'type': type,
                'message': filename
            }));
        }
        clearContextEnabled = false;
        clearContextButton.setAttribute("style", "display: none !important;");
        contextDataSpan.innerText = "<<<" + "..." + ">>>  ";
        contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-invisible");
        console.log("...Rebuild rag action sent.");
    } else {
        console.log("Not Detected context active, message to rebuild RAG not sent.");
    }
    replaceCodeElement('language-python', "");
    lineNumbers.value = "...";
    filenameSpan.textContent = `<<<...>>>`;
    filenameSpan.removeAttribute('title');
    canvasLoaded = false;
    disableCanvasButtons();
    canvasSettedAsContext = false;
    contextButtonClicked = false;
    contextButton.textContent = "Use as context";
    copyCanvasButton.textContent = "Copy";
}

/**
 * Copy the canvas content to clipboard.
 */
async function copyCanvasToClipboard() {
    if (!canvasLoaded || !textEditorCode) {
        console.log("Cannot copy: canvas not loaded or no content");
        return;
    }

    const generation = canvasLoadGeneration;
    let content;
    try {
        content = await getCanvasText();
    } catch (error) {
        if (generation === canvasLoadGeneration) alert(error.message);
        return;
    }
    if (generation !== canvasLoadGeneration) return;
    if (!content || content.trim() === '') {
        console.log("Cannot copy: canvas content is empty");
        return;
    }

    navigator.clipboard.writeText(content).then(() => {
        console.log("--- Canvas content copied to clipboard");
        const originalText = copyCanvasButton.textContent;
        copyCanvasButton.textContent = "Copied!";
        copyCanvasButton.style.backgroundColor = "#55BBAA";
        setTimeout(() => {
            if (generation !== canvasLoadGeneration) return;
            copyCanvasButton.textContent = originalText;
            if (canvasLoaded) {
                copyCanvasButton.style.backgroundColor = "darkgreen";
            } else {
                copyCanvasButton.style.backgroundColor = "#808080";
            }
        }, 1500);
    }).catch(err => {
        console.error("Failed to copy canvas content:", err);
        alert("Failed to copy to clipboard");
    });
}

// Copy canvas button click handler
if (copyCanvasButton) {
    copyCanvasButton.addEventListener('click', copyCanvasToClipboard);
    copyCanvasButton.disabled = true;
    copyCanvasButton.style.backgroundColor = "#808080";
}

/**
 * Open a file picker and load content into the canvas editor.
 */
const loadFileContent = async (reOpened = false, callback = null) => {
    if (!openEnabled || !contextEnabled) return;
    const generation = canvasLoadGeneration;
    if (typeof window.showOpenFilePicker === 'function' && window.isSecureContext) {
        try {
            const [handle] = await window.showOpenFilePicker({ multiple: false, types: [{
                description: 'Documents and source files',
                accept: { 'application/octet-stream': SOURCE_CODE_ACCEPT.split(',').filter(value => value.startsWith('.')) },
            }] });
            if (!handle || generation !== canvasLoadGeneration) return;
            const file = await handle.getFile();
            if (generation !== canvasLoadGeneration) return;
            await loadSelectedCanvasFile(file, reOpened, callback, { handle });
            return;
        } catch (error) {
            if (error.name === 'AbortError') return;
            if (!['SecurityError', 'NotSupportedError'].includes(error.name)) {
                await window.tlmAlert(`Unable to open the file: ${error.message}`, 'Open file');
                return;
            }
            // Insecure/embedded/unsupported browsers can still open a snapshot.
            // Its Refresh state explains the missing ability to reread it.
        }
    }
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = SOURCE_CODE_ACCEPT;
    input.hidden = true;
    input.onchange = async e => {
        const file = e.target.files[0];
        input.remove();
        if (!file || generation !== canvasLoadGeneration) return;
        await loadSelectedCanvasFile(file, reOpened, callback);
    };
    input.addEventListener('cancel', () => input.remove(), { once: true });
    document.body.appendChild(input);
    input.click();
};

/** Read text normally; route PDFs to the complete, range-backed PDF viewer. */
/** Keep flow files out of chat context; reserve the tab before asynchronous work. */
async function openFlowEditor(file) {
    const tab = window.open('about:blank', '_blank');
    if (!tab) { await alert('Allow pop-ups for Tlamatini, then open the flow file again.'); return; }
    tab.document.title = 'Opening flow · Tlamatini';
    tab.document.body.textContent = 'Opening ' + file.name + '…';
    tab.document.body.style.cssText = 'background:#24252f;color:#eee;font:18px system-ui;padding:48px';
    tab.opener = null;
    try {
        if (file.size > 5 * 1024 * 1024) throw new Error('The flow file must be no larger than 5 MiB.');
        const body = new FormData(); body.append('file', file);
        const csrf = document.querySelector('[name=csrfmiddlewaretoken]')?.value ||
            decodeURIComponent(document.cookie.split('; ').find(v => v.startsWith('csrftoken='))?.slice(10) || '');
        const response = await fetch('/agent/flow_files/open/', {
            method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrf }, body
        });
        if (response.redirected) throw new Error('Your session expired. Sign in, then open the file again.');
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'The file could not be opened.');
        if (!tab.closed) tab.location.replace(result.url);
    } catch (error) {
        if (!tab.closed) tab.close();
        await alert('Could not open ' + file.name + ': ' + error.message);
    }
}

async function loadSelectedCanvasFile(file, reOpened = false, callback = null, access = null) {
    if (!openEnabled || !contextEnabled) return;
    if (/\.(flw|fpmt)$/i.test(file.name)) { await openFlowEditor(file); return; }
    window.TlamatiniViews?.setCanvasVisible(true);
    // Setting file context replaces it directly, avoiding an overlapping background
    // rebuild of empty context while the replacement document loads.
    cleanCanvas(reOpened && callback !== null);
    let generation = canvasLoadGeneration;
    const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
    try {
        if (isPdf) {
            filenameSpan.textContent = `<<< ${file.name} >>>`;
            filenameSpan.title = file.name;
            // Keep Clear available during loading and password entry.
            canvasLoaded = true;
            enableCanvasButtons();
            const loaded = await window.TlamatiniPdfCanvas.open(file);
            if (!loaded || generation !== canvasLoadGeneration) return;
            rememberCanvasSource(localCanvasSource(file, access));
        } else {
            const content = await file.text();
            if (generation !== canvasLoadGeneration) return;
            displayCanvasText(file.name, content, file);
            generation = canvasLoadGeneration;
            filenameSpan.textContent = `<<< ${file.name} >>>`;
            filenameSpan.title = file.name;
            canvasLoaded = true;
            rememberCanvasSource(localCanvasSource(file, access, content));
            enableCanvasButtons();
        }
        if (reOpened && callback) await callback();
    } catch (error) {
        // Closing/replacing a PDF cancels pending work without reopening it.
        if (generation !== canvasLoadGeneration) return;
        if (error.name === 'AbortError') return;
        if (isPdf && window.TlamatiniPdfProgress) {
            window.TlamatiniPdfProgress.fail(error.message);
            return;
        }
        console.error('Error opening canvas file:', error);
        alert(`Unable to load ${file.name}: ${error.message}`);
    }
}

// Save As button handler
saveAsButton.addEventListener('click', () => {
    const pdfFile = window.TlamatiniPdfCanvas?.file;
    const markdown = window.TlamatiniMarkdownCanvas;
    const markdownFile = markdown?.file;
    const text = textEditorCode.textContent;
    if (!pdfFile && !markdown?.active && (!text || text.trim().length === 0)) {
        console.log("Save As ignored: canvas is empty.");
        return;
    }
    let fileName = prompt("Save as...", pdfFile?.name || markdown?.name || "");
    if (fileName === null) return;
    if (pdfFile && !fileName.toLowerCase().endsWith('.pdf')) fileName += '.pdf';
    if (markdown?.active && !/\.(md|markdown)$/i.test(fileName)) fileName += '.md';
    const blob = pdfFile || markdownFile || new Blob([text], { type: markdown?.active ? 'text/markdown;charset=utf-8' : 'text/plain' });
    const anchor = document.createElement('a');
    anchor.download = fileName;
    anchor.href = window.URL.createObjectURL(blob);
    anchor.target = '_blank';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    setTimeout(() => window.URL.revokeObjectURL(anchor.href), 10000);
});

// Files dropped ANYWHERE on this page are claimed by file_drop_router.js, which
// recognises each one by its bytes and calls us only for what the canvas can show:
// documents, PDFs, Markdown, code and plain JSON. MCP configs, flows and images
// go to their own mechanisms (this used to open an MCP .json as text and swallow
// the event, so the import never saw it).
if (window.TlamatiniFileDrop) {
    window.TlamatiniFileDrop.register(['pdf', 'markdown', 'text'], async (files, items) => {
        if (!openEnabled || !contextEnabled) {
            return { ignored: files, note: 'The canvas is busy right now \u2014 drop the file again when Tlamatini has finished.' };
        }
        const generation = canvasLoadGeneration;
        const handle = await items?.[0]?.handlePromise;
        if (generation !== canvasLoadGeneration) return { ignored: files, note: 'The canvas changed while this drop was being read. Drop the file again.' };
        await loadSelectedCanvasFile(files[0], false, null, { handle, entry: items?.[0]?.entry });
        const rest = files.slice(1);
        return rest.length
            ? { ignored: rest, note: 'Opened ' + files[0].name + '; the canvas holds one document, so ' + rest.map(file => file.name).join(', ') + ' was not opened.' }
            : {};
    }, { label: 'Document (PDF, Markdown, code, JSON) \u2192 opens in the canvas' });
}

// Editor input / scroll sync
textEditorCode.addEventListener('input', updateLineNumbers);
textEditorPre.addEventListener('scroll', () => {
    lineNumbers.scrollTop = textEditorPre.scrollTop;
});

// Initial context button state
contextButton.style.backgroundColor = "gray";
contextButton.disabled = true;
