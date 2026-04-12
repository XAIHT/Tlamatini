// ============================================================
// agent_page_canvas.js  –  Canvas / code-editor operations
// ============================================================

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
    const newTextEditorCode = document.createElement('code');
    newTextEditorCode.classList.add(langClass);
    newTextEditorCode.textContent = content;
    textEditorCode.parentNode.replaceChild(newTextEditorCode, textEditorCode);
    textEditorCode = newTextEditorCode;
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

    fetch(`/agent/load_canvas/${filename}/`)
        .then(response => response.text())
        .then(content => {
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
        input.accept = '.txt,.py,.js,.java,.cpp,.c,.html,.css,.json,.xml,*';
        input.style.display = 'none';

        input.onchange = (e) => {
            const file = e.target.files[0];
            if (!file) {
                console.error("No file selected");
                document.body.removeChild(input);
                return false;
            }

            const reader = new FileReader();
            reader.onload = (event) => {
                const content = event.target.result;
                const actualFilename = file.name;
                const extension = extractExtension(actualFilename);
                replaceCodeElement(getLanguageClass(extension), content);
                filenameSpan.textContent = `<<< ${actualFilename} >>>`;
                canvasLoaded = true;
                enableCanvasButtons();
                canvasSettedAsContext = false;
                contextButtonClicked = false;
                contextButton.textContent = "Use as context";
                console.log("Successfully loaded file from content_generated: " + actualFilename);
                document.body.removeChild(input);
            };
            reader.readAsText(file);
        };
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

    const callback2Rag = () => {
        const type = "set-canvas-as-context";
        const codeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(codeRegex);
        const content = textEditorCode.textContent;
        const tokensNumber = genericTokenCounting(content);
        console.log("--- The number of tokens in file is: " + tokensNumber);
        if (tokensNumber > maximalTheoricTokens) {
            console.log("--- The number of tokens in file (if used as context) may not be completely processed by Tlamatini, it wont fit the context window.");
            alert("The number of tokens in the loaded file (if used as context) may not be completely processed by Tlamatini, it wont fit the context window.");
        }
        console.log("--- The content is: " + content);
        if (result) {
            const filename = result[1];
            sendChatSocketMessage(JSON.stringify({
                'type': type,
                'message': filename,
                'content': content
            }));
        }
        console.log("...Rebuild rag action sent.");
    };
    loadFileContent(canvasSettedAsContext, callback2Rag);
    console.log("Canvas reopened.");
}

function cleanCanvas() {
    const codeRegex = /<<<\s*(.+?)\s*>>>/s;
    const result1 = filenameSpan.textContent.match(codeRegex);
    const spanContextString = contextDataSpan.innerText;
    const result2 = spanContextString.match(codeRegex);
    if (canvasSettedAsContext === true && result1 && result2 && result1[1] === result2[1]) {
        console.log("Detected context was active, so send the message to clean the context and rebuild the RAG...");
        const innerCodeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(innerCodeRegex);
        const type = "unset-canvas-as-context";
        if (result && result[1] && result[1].length > 0 && result[1].includes('...') === false) {
            const filename = result[1];
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
    canvasLoaded = false;
    disableCanvasButtons();
    canvasSettedAsContext = false;
    contextButtonClicked = false;
    contextButton.textContent = "Use as context";
}

/**
 * Copy the canvas content to clipboard.
 */
function copyCanvasToClipboard() {
    if (!canvasLoaded || !textEditorCode) {
        console.log("Cannot copy: canvas not loaded or no content");
        return;
    }

    const content = textEditorCode.textContent;
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
    input.onchange = e => {
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

        const reader = new FileReader();
        const filename = file.name;
        const extension = extractExtension(filename);
        reader.onload = event => {
            replaceCodeElement(getLanguageClass(extension), event.target.result);
            filenameSpan.textContent = "<<< " + filename + " >>>";
            canvasLoaded = true;
            enableCanvasButtons();

            console.log("loaded file: " + filename + " !!!");
            if (reOpened === false) {
                contextButton.style.backgroundColor = "darkgreen";
                contextButton.disabled = false;
                canvasSettedAsContext = false;
                contextButtonClicked = false;
                contextButton.textContent = "Use as context";
            } else {
                if (callback != null) {
                    callback();
                }
            }
        };
        reader.readAsText(file);
    };
    input.click();
};

// Save As button handler
saveAsButton.addEventListener('click', () => {
    const text = textEditorCode.textContent;
    if (!text || text.trim().length === 0) {
        console.log("Save As ignored: canvas is empty.");
        return;
    }
    const fileName = prompt("Save as...", "");
    if (fileName === null) return;
    const blob = new Blob([text], { type: 'text/plain' });
    const anchor = document.createElement('a');
    anchor.download = fileName;
    anchor.href = window.URL.createObjectURL(blob);
    anchor.target = '_blank';
    anchor.style.display = 'none';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
});

// Editor input / scroll sync
textEditorCode.addEventListener('input', updateLineNumbers);
textEditorPre.addEventListener('scroll', () => {
    lineNumbers.scrollTop = textEditorPre.scrollTop;
});

// Initial context button state
contextButton.style.backgroundColor = "gray";
contextButton.disabled = true;
