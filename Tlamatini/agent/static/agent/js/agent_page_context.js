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

// What the context header showed before a selection replaced it with
// "pending context". If the server REFUSES that selection, the header goes
// back to exactly this state instead of staying on "pending" forever (Angela,
// 2026-10-08). A refusal happens before the server touches the context, so the
// previous state is the true one.
let pendingContextPrevious = null;

function showPendingContextSelection(label) {
    pendingContextPrevious = {
        text: contextDataSpan ? contextDataSpan.textContent : '',
        infoClass: contextInfoDiv.getAttribute("class"),
        dir: actualContextDir,
        clearEnabled: clearContextEnabled,
        clearStyle: clearContextButton.getAttribute("style"),
    };
    clearContextEnabled = false;
    clearContextButton.setAttribute("style", "display: none !important;");
    actualContextDir = null;
    updateViewContextDirMenuState();
    setContextText("<<< pending context: " + label + " >>>");
    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-visible");
}

function restorePendingContextSelection() {
    const previous = pendingContextPrevious;
    pendingContextPrevious = null;
    if (!previous) return;
    actualContextDir = previous.dir;
    clearContextEnabled = previous.clearEnabled;
    if (previous.clearStyle === null) clearContextButton.removeAttribute("style");
    else clearContextButton.setAttribute("style", previous.clearStyle);
    updateViewContextDirMenuState();
    setContextText(previous.text);
    if (previous.infoClass) contextInfoDiv.setAttribute("class", previous.infoClass);
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
contextButton.addEventListener('click', async (event) => {
    if (contextEnabled === false) {
        event.preventDefault();
        return;
    }

    event.preventDefault();

    if (!contextButtonClicked) {
        const codeRegex = /<<< (.+?) >>>/s;
        const result = filenameSpan.textContent.match(codeRegex);
        const generation = getCanvasGeneration();
        let payload;
        try {
            payload = await getCanvasContextPayload();
        } catch (error) {
            if (error.name === 'AbortError') return;
            if (generation === getCanvasGeneration()) {
                if (window.TlamatiniPdfCanvas?.active && window.TlamatiniPdfProgress) window.TlamatiniPdfProgress.fail(error.message);
                else alert(error.message);
            }
            return;
        }
        if (generation !== getCanvasGeneration() || !contextEnabled) return;
        const content = payload.content || '';
        const tokensNumber = genericTokenCounting(content);
        console.log("--- The number of tokens in file is: " + tokensNumber);
        if (tokensNumber > maximalTheoricTokens) {
            console.log("--- The number of tokens in file (if used as context) may not be completely processed by Tlamatini, it wont fit the context window.");
            alert("The number of tokens in the loaded file (if used as context) may not be completely processed by Tlamatini, it wont fit the context window.");
        }
        console.log("--- The content is: " + content);
        if (!result) {
            return;
        }

        const filename = payload.message;
        const sent = sendChatSocketMessage(payload);
        if (!sent) {
            unsetContextButton();
            if (payload.context_token) window.TlamatiniPdfProgress?.fail('The live connection is unavailable. Reconnect and try again.');
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

    const codeRegex = /<<< (.+?) >>>/s;
    const result = filenameSpan.textContent.match(codeRegex);
    if (!result) {
        return;
    }

    const filename = getCanvasContextFilename();
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
