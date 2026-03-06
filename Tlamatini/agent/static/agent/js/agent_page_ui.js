// ============================================================
// agent_page_ui.js  –  UI state helpers (enable/disable, busy, spinner)
// ============================================================

function setContextText(txt) {
    const full = txt || "";

    if (contextDataSpan) {
        contextDataSpan.textContent = full;
        contextDataSpan.title = full;
    }
    if (contextMobile) {
        contextMobile.title = full;
        if (window.bootstrap) {
            const tip = bootstrap.Tooltip.getInstance(contextMobile);
            if (tip) tip.dispose();
            new bootstrap.Tooltip(contextMobile);
        }
    }
}

function updateViewContextDirMenuState() {
    if (viewContextDirInCanvasMenu) {
        if (actualContextDir !== null && actualContextDir !== '') {
            viewContextDirInCanvasMenu.parentElement.style.display = 'block';
        } else {
            viewContextDirInCanvasMenu.parentElement.style.display = 'none';
        }
    }
}

function setTitleBusy(isBusy) {
    titleBusyPrefix = isBusy ? "⏳ " : "";
}

function isBusyMessageRequest(message) {
    if (!message) return false;
    const m = String(message);
    return (
        m.includes("Your request is being processed by the LLM.")
    );
}

function isBusyMessageContext(message) {
    if (!message) return false;
    const m = String(message);
    return (
        m.includes("Your agent is loading the context.")
    );
}

function debounce(func, wait = 250) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => { func.apply(this, args); }, wait);
    };
}

function genericTokenCounting(text) {
    return text.length / 4;
}

function updateLineNumbers() {
    const lines = textEditorCode.textContent.split('\n');
    lineNumbers.value = lines.map((_, i) => i + 1).join('\n');
}

/**
 * Disable all interactive controls during a long operation.
 */
function disableControlsDuringOperation() {
    chatInput.readOnly = true;
    chatInput.style.backgroundColor = 'gray';
    if (!document.getElementById(spinnerId)) {
        const waitWidget = document.createElement('img');
        waitWidget.id = spinnerId;
        waitWidget.src = '/static/agent/img/spinner.svg';
        waitWidget.style.width = '100px';
        waitWidget.style.height = '100px';
        waitWidget.style.position = 'absolute';
        waitWidget.style.top = '50%';
        waitWidget.style.left = '50%';
        waitWidget.style.transform = 'translate(-50%, -50%)';
        waitWidget.style.zIndex = '1000';
        chatLog.appendChild(waitWidget);
    }
    contextButton.disabled = true;
    openEnabled = false;
    contextEnabled = false;
    cleanCanvasEnabled = false;
    reConnectEnabled = false;
    reConnectButton.disabled = true;
    cleanHistoryButton.disabled = true;
    cleanHistoryButton.style.backgroundColor = "#808080";
    cleanHistoryEnabled = false;
    contextMenuButton.setAttribute('disabled', 'disabled');
    contextMenuButton.removeAttribute('data-bs-toggle');
    mcpsMenuButton.setAttribute('disabled', 'disabled');
    mcpsMenuButton.removeAttribute('data-bs-toggle');
    // Keep agentsMenuButton enabled so "Agentic Control Panel" remains accessible
    // Only disable the "Configure Agents" entry
    const configureAgentsItem = document.getElementById('enable-agents');
    if (configureAgentsItem) {
        configureAgentsItem.classList.add('disabled');
        configureAgentsItem.style.pointerEvents = 'none';
        configureAgentsItem.style.opacity = '0.5';
    }
    chatSubmitButton.textContent = 'Cancel';
    cleanCanvasButton.style.backgroundColor = "#808080";
    cleanCanvasButton.disabled = true;
    reopenOpenCanvasButton.style.backgroundColor = "#808080";
    reopenOpenCanvasButton.disabled = true;
    copyCanvasButton.style.backgroundColor = "#808080";
    copyCanvasButton.disabled = true;
    contextButton.style.backgroundColor = "#808080";
    contextButton.disabled = true;
    inLongOperation = true;
}

/**
 * Re-enable all controls after an operation completes.
 */
function enableControlsAfterOperation() {
    setTitleBusy(false);
    contextEnabled = true;
    contextButton.style.backgroundColor = "darkgreen";
    contextButton.disabled = false;
    contextButtonClicked = false;
    contextButton.textContent = "Use as context";
    chatInput.readOnly = false;
    chatInput.style.backgroundColor = '#40414F';
    const existingSpinner = document.getElementById(spinnerId);
    if (existingSpinner && existingSpinner.parentNode) {
        existingSpinner.parentNode.removeChild(existingSpinner);
    }

    if (canvasSettedAsContext) {
        contextButton.textContent = "Used as context";
        contextButton.style.backgroundColor = "#808080";
    } else {
        if (canvasLoaded) {
            contextButton.textContent = "Use as context";
            contextButton.style.backgroundColor = "darkgreen";
        } else {
            contextButton.textContent = "Use as context";
            contextButton.style.backgroundColor = "#808080";
        }
    }

    openEnabled = true;
    reConnectEnabled = true;
    contextEnabled = true;
    cleanCanvasEnabled = true;
    reConnectButton.disabled = false;
    cleanHistoryButton.disabled = false;
    cleanHistoryButton.style.backgroundColor = "darkgreen";
    cleanHistoryEnabled = true;
    contextMenuButton.removeAttribute('disabled', 'disabled');
    contextMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    mcpsMenuButton.removeAttribute('disabled', 'disabled');
    mcpsMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    // Re-enable the "Configure Agents" entry
    const configureAgentsItem = document.getElementById('enable-agents');
    if (configureAgentsItem) {
        configureAgentsItem.classList.remove('disabled');
        configureAgentsItem.style.pointerEvents = '';
        configureAgentsItem.style.opacity = '';
    }

    if (canvasLoaded === true) {
        cleanCanvasButton.style.backgroundColor = "darkgreen";
        cleanCanvasButton.disabled = false;
        reopenOpenCanvasButton.style.backgroundColor = "darkgreen";
        reopenOpenCanvasButton.disabled = false;
        copyCanvasButton.style.backgroundColor = "darkgreen";
        copyCanvasButton.disabled = false;
        contextButton.disabled = false;
    } else {
        cleanCanvasButton.style.backgroundColor = "#808080";
        cleanCanvasButton.disabled = true;
        reopenOpenCanvasButton.style.backgroundColor = "#808080";
        reopenOpenCanvasButton.disabled = true;
        copyCanvasButton.style.backgroundColor = "#808080";
        copyCanvasButton.disabled = true;
        contextButton.disabled = true;
    }

    chatSubmitButton.textContent = 'Send';
    inLongOperation = false;
    lapseLoadingContext = false;
}

/**
 * Enable canvas-related buttons (after canvas load).
 */
function enableCanvasButtons() {
    cleanCanvasButton.style.backgroundColor = "darkgreen";
    cleanCanvasButton.disabled = false;
    reopenOpenCanvasButton.style.backgroundColor = "darkgreen";
    reopenOpenCanvasButton.disabled = false;
    copyCanvasButton.style.backgroundColor = "darkgreen";
    copyCanvasButton.disabled = false;
    contextButton.style.backgroundColor = "darkgreen";
    contextButton.disabled = false;
}

/**
 * Disable canvas-related buttons (after canvas clean).
 */
function disableCanvasButtons() {
    cleanCanvasButton.style.backgroundColor = "#808080";
    cleanCanvasButton.disabled = true;
    reopenOpenCanvasButton.style.backgroundColor = "#808080";
    reopenOpenCanvasButton.disabled = true;
    copyCanvasButton.style.backgroundColor = "#808080";
    copyCanvasButton.disabled = true;
    contextButton.style.backgroundColor = "#808080";
    contextButton.disabled = true;
}
