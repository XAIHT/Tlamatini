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
    '.flw', '.pmt', '.pdf', 'application/pdf',
    'text/*',
].join(',');

// Every replacement invalidates pending reads, PDF loads and text extractions.
let canvasLoadGeneration = 0;
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
    const newTextEditorCode = document.createElement('code');
    newTextEditorCode.classList.add(langClass);
    newTextEditorCode.textContent = content;
    textEditorCode.parentNode.replaceChild(newTextEditorCode, textEditorCode);
    textEditorCode = newTextEditorCode;
    textEditorCode.addEventListener('input', updateLineNumbers);
    hljs.highlightElement(textEditorCode);
    updateLineNumbers();
}

function loadCanvas(filename) { // eslint-disable-line no-unused-vars
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

    const generation = ++canvasLoadGeneration;
    fetch(`/agent/load_canvas/${encodeURIComponent(filename)}/`)
        .then(response => response.text())
        .then(content => {
            if (generation !== canvasLoadGeneration) return;
            const extension = extractExtension(filename);
            replaceCodeElement(getLanguageClass(extension), content);
            filenameSpan.textContent = `<<< ${filename} >>>`;
            canvasLoaded = true;
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

    try {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = SOURCE_CODE_ACCEPT;
        input.style.display = 'none';

        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) {
                console.error("No file selected");
                document.body.removeChild(input);
                return false;
            }

            await loadSelectedCanvasFile(file);
            input.remove();
        };
        input.addEventListener('cancel', () => input.remove(), { once: true });
        document.body.appendChild(input);
        input.click();
    } catch (error) {
        console.error('Error loading canvas from content_generated:', error);
        alert('Error loading file: ' + filename);
    }
}

function loadCanvasWithThisContent(content) {
    console.log("loadCanvasWithThisContent()...");
    replaceCodeElement('language-text', content);
    filenameSpan.textContent = `<<< Context, tree of content. >>>`;
    canvasLoaded = true;
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

function reopenCanvas() {
    console.log("Reopening canvas with file...");

    const callback2Rag = async () => {
        const codeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(codeRegex);
        const generation = canvasLoadGeneration;
        const payload = await getCanvasContextPayload();
        const content = payload.content || '';
        if (generation !== canvasLoadGeneration || !contextEnabled) return;
        const tokensNumber = genericTokenCounting(content);
        console.log("--- The number of tokens in file is: " + tokensNumber);
        if (tokensNumber > maximalTheoricTokens) {
            console.log("--- The number of tokens in file (if used as context) may not be completely processed by Tlamatini, it wont fit the context window.");
            alert("The number of tokens in the loaded file (if used as context) may not be completely processed by Tlamatini, it wont fit the context window.");
        }
        console.log("--- The content is: " + content);
        if (result) {
            const sent = sendChatSocketMessage(payload);
            if (sent) {
                canvasSettedAsContext = true;
                contextButtonClicked = true;
                contextButton.textContent = 'Used as context';
                contextButton.style.backgroundColor = 'gray';
                contextButton.disabled = true;
                openEnabled = false;
                contextEnabled = false;
                showPendingContextSelection(payload.message);
            } else if (payload.context_token) {
                window.TlamatiniPdfProgress?.fail('The live connection is unavailable. Reconnect and try again.');
            }
        }
        console.log("...Rebuild rag action sent.");
    };
    loadFileContent(canvasSettedAsContext, callback2Rag);
    console.log("Canvas reopened.");
}

function cleanCanvas(preserveContext = false) {
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
const loadFileContent = (reOpened = false, callback = null) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = SOURCE_CODE_ACCEPT;
    input.onchange = async e => {
        const file = e.target.files[0];
        if (file == null) {
            console.error("No file selected, so load file content is not allowed, function will return false...");
            return false;
        }

        // Check for .flw extension - redirect to Agentic Control Panel
        if (file.name.toLowerCase().endsWith('.flw')) {
            const flwReader = new FileReader();
            flwReader.onload = flwEvent => {
                try {
                    const flwData = JSON.parse(flwEvent.target.result);
                    localStorage.setItem('pendingFlwData', JSON.stringify(flwData));
                    localStorage.setItem('pendingFlwFilename', file.name);
                    localStorage.setItem('pendingFlwTimestamp', Date.now().toString()); // Add timestamp
                    window.open('/agent/agentic_control_panel/', '_blank');
                    console.log('--- Opened .flw file in Agentic Control Panel: ' + file.name);
                } catch (err) {
                    console.error('Failed to parse .flw file:', err);
                    alert('Invalid .flw file format. The file could not be parsed as JSON.');
                }
            };
            flwReader.readAsText(file);
            return;
        }

        await loadSelectedCanvasFile(file, reOpened, callback);
    };
    input.click();
};

/** Read text normally; route PDFs to the complete, range-backed PDF viewer. */
async function loadSelectedCanvasFile(file, reOpened = false, callback = null) {
    // Reopen replaces context directly, avoiding an overlapping background
    // rebuild of empty context while the replacement document loads.
    cleanCanvas(reOpened && callback !== null);
    let generation = canvasLoadGeneration;
    const isPdf = file.name.toLowerCase().endsWith('.pdf') || file.type === 'application/pdf';
    try {
        if (isPdf) {
            filenameSpan.textContent = `<<< ${file.name} >>>`;
            filenameSpan.title = file.name;
            // Keep Clear/Reopen available during loading and password entry.
            canvasLoaded = true;
            enableCanvasButtons();
            const loaded = await window.TlamatiniPdfCanvas.open(file);
            if (!loaded || generation !== canvasLoadGeneration) return;
        } else {
            const content = await file.text();
            if (generation !== canvasLoadGeneration) return;
            replaceCodeElement(getLanguageClass(extractExtension(file.name)), content);
            generation = canvasLoadGeneration;
            filenameSpan.textContent = `<<< ${file.name} >>>`;
            filenameSpan.title = file.name;
            canvasLoaded = true;
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
    const text = textEditorCode.textContent;
    if (!pdfFile && (!text || text.trim().length === 0)) {
        console.log("Save As ignored: canvas is empty.");
        return;
    }
    let fileName = prompt("Save as...", pdfFile?.name || "");
    if (fileName === null) return;
    if (pdfFile && !fileName.toLowerCase().endsWith('.pdf')) fileName += '.pdf';
    const blob = pdfFile || new Blob([text], { type: 'text/plain' });
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

// Editor input / scroll sync
textEditorCode.addEventListener('input', updateLineNumbers);
textEditorPre.addEventListener('scroll', () => {
    lineNumbers.scrollTop = textEditorPre.scrollTop;
});

// Initial context button state
contextButton.style.backgroundColor = "gray";
contextButton.disabled = true;
