// ============================================================
// agent_page_context.js  –  Context management
// ============================================================

function setContextButton() {
    contextButton.style.backgroundColor = "gray";
    contextButton.disabled = false;
    canvasSettedAsContext = true;
    contextButtonClicked = true;
    contextButton.textContent = "Used as context";
}

function unsetContextButton() {
    contextButton.style.backgroundColor = "darkgreen";
    contextButton.disabled = false;
    canvasSettedAsContext = false;
    contextButtonClicked = false;
    contextButton.textContent = "Use as context";
}

function showPendingContextSelection(label) {
    clearContextEnabled = false;
    clearContextButton.setAttribute("style", "display: none !important;");
    actualContextDir = null;
    updateViewContextDirMenuState();
    setContextText("<<< pending context: " + label + " >>>");
    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-visible");
}

function ClearContext(e) {
    e.preventDefault();
    if (clearContextEnabled === false) {
        console.log("Clear context is not allowed at this moment...");
        return;
    }

    if (!sendChatSocketMessage({
        'type': 'clear-context',
        'message': '...'
    })) {
        return;
    }

    if (canvasLoaded === true) {
        contextButton.style.backgroundColor = "darkgreen";
        contextButton.disabled = false;
        contextButtonClicked = false;
        contextButton.textContent = "Use as context";
        enableCanvasButtons();
    } else {
        contextButton.style.backgroundColor = "gray";
        contextButton.disabled = true;
        contextButtonClicked = false;
        contextButton.textContent = "Use as context";
        disableCanvasButtons();
    }

    actualContextDir = null;
    updateViewContextDirMenuState();
    console.log("--- actualContextDir reset to null on clear context.");

    clearContextEnabled = false;
    clearContextButton.setAttribute("style", "display: none !important;");
    setContextText("<<<" + "..." + ">>>  ");
    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-invisible");
    console.log("--- Clear context message sent to server.");
}

// --- Context button click handler (toggle set/unset) ---
contextButton.addEventListener('click', (event) => {
    if (contextEnabled === false) {
        event.preventDefault();
        return;
    }

    event.preventDefault();

    if (!contextButtonClicked) {
        const codeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(codeRegex);
        const content = textEditorCode.textContent;
        const tokensNumber = genericTokenCounting(content);
        console.log("--- The number of tokens in file is: " + tokensNumber);
        if (tokensNumber > maximalTheoricTokens) {
            console.log("--- The number of tokens in file (if used as context) may not be completely processed by the LLM, it wont fit the context window.");
            alert("The number of tokens in the loaded file (if used as context) may not be completely processed by the LLM, it wont fit the context window.");
        }
        console.log("--- The content is: " + content);
        if (!result) {
            return;
        }

        const filename = result[1];
        const sent = sendChatSocketMessage({
            'type': 'set-canvas-as-context',
            'message': filename,
            'content': content
        });
        if (!sent) {
            unsetContextButton();
            return;
        }

        setContextButton();
        contextButton.disabled = true;
        contextButton.style.backgroundColor = "gray";
        openEnabled = false;
        contextEnabled = false;
        showPendingContextSelection(filename);
        return;
    }

    const codeRegex = /<<< ([\w.-]+) >>>/s;
    const result = filenameSpan.textContent.match(codeRegex);
    if (!result) {
        return;
    }

    const filename = result[1];
    const sent = sendChatSocketMessage({
        'type': 'unset-canvas-as-context',
        'message': filename
    });
    if (!sent) {
        return;
    }

    unsetContextButton();
    clearContextEnabled = false;
    clearContextButton.setAttribute("style", "display: none !important;");
    actualContextDir = null;
    updateViewContextDirMenuState();
    setContextText("<<<...>>>  ");
    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-visible");
});
