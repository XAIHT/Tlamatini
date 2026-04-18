// ============================================================
// agent_page_init.js  –  Initialization, event wiring & actions
// ============================================================
/* global syncClearContextMenuState, isMultiTurnEnabled, applyStoredMultiTurnState, multiTurnCheckbox, persistMultiTurnState, isExecReportEnabled, applyStoredExecReportState, execReportCheckbox, persistExecReportState */

// --- Prevent accidental close during long operations ---
window.addEventListener('beforeunload', (event) => {
    if (inLongOperation) {
        event.preventDefault();
        event.returnValue = '';
        sendPostBeacon('/agent/clear_session_state/'); // eslint-disable-line no-undef
        console.log('--- Page closing during long operation: Sent session cleanup via beacon');
    }
});

// ----------------------------------------------------------------
// Top-level actions
// ----------------------------------------------------------------

function Reconnect(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (reConnectEnabled === false) {
        console.log("Reconnect is not allowed at this moment...");
        return;
    }
    if (!isChatSocketOpen()) {
        console.log("--- WebSocket is closed, reloading page to rebuild the live session.");
        window.location.reload();
        return;
    }
    reConnectEnabled = true;
    reConnectButton.disabled = true;

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

    agents = [];
    tools = [];
    openEnabled = true;
    reConnectEnabled = true;
    contextEnabled = true;
    cleanCanvasEnabled = true;
    contextButtonClicked = false;
    canvasSettedAsContext = false;
    reConnectButton.disabled = false;
    contextMenuButton.removeAttribute('disabled', 'disabled');
    contextMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    mcpsMenuButton.removeAttribute('disabled', 'disabled');
    mcpsMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    agentsMenuButton.removeAttribute('disabled', 'disabled');
    agentsMenuButton.setAttribute('data-bs-toggle', 'dropdown');

    contextButton.textContent = "Use as context";
    contextButton.disabled = false;
    contextButton.style.backgroundColor = "darkgreen";

    if (canvasLoaded === true) {
        enableCanvasButtons();
    } else {
        disableCanvasButtons();
    }

    chatSubmitButton.textContent = 'Send';
    inLongOperation = false;
    actualContextDir = null;
    updateViewContextDirMenuState();
    console.log("--- actualContextDir reset to null on reconnect.");
    if (!sendChatSocketMessage(JSON.stringify({
        'type': 'reconnect-llm-agent',
        'message': 'reconnect'
    }))) {
        return;
    }
    clearContextEnabled = false;
    clearContextButton.setAttribute("style", "display: none !important;");
    contextDataSpan.innerText = "<<<" + "..." + ">>>  ";
    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-invisible");
    console.log("--- Reconnect message sent to server.");
}

function CleanHistory(e) {
    e.preventDefault();
    if (cleanHistoryEnabled === false) {
        console.log("Clean history is not allowed at this moment...");
        return;
    }

    const callbackOnCont = () => {
        const cleanHistorySent = sendChatSocketMessage(JSON.stringify({
            'type': 'clean-history-and-reconnect',
            'message': 'clean-history'
        }));
        if (!cleanHistorySent) {
            return false;
        }

        chatLog.innerHTML = '';
        chatHistory = [];
        historyIndex = 0;
        tempInput = '';
        sessionStorage.removeItem('chatHistory');

        setTitleBusy(false);
        agents = [];
        tools = [];
        openEnabled = true;
        reConnectEnabled = true;
        contextEnabled = true;
        cleanCanvasEnabled = true;
        cleanHistoryEnabled = true;
        contextButtonClicked = false;
        canvasSettedAsContext = false;
        reConnectButton.disabled = false;
        cleanHistoryButton.disabled = false;
        cleanHistoryButton.style.backgroundColor = "darkgreen";
        contextMenuButton.removeAttribute('disabled', 'disabled');
        contextMenuButton.setAttribute('data-bs-toggle', 'dropdown');
        mcpsMenuButton.removeAttribute('disabled', 'disabled');
        mcpsMenuButton.setAttribute('data-bs-toggle', 'dropdown');
        agentsMenuButton.removeAttribute('disabled', 'disabled');
        agentsMenuButton.setAttribute('data-bs-toggle', 'dropdown');

        contextButton.textContent = "Use as context";
        contextButton.disabled = false;
        contextButton.style.backgroundColor = "darkgreen";

        if (canvasLoaded === true) {
            enableCanvasButtons();
        } else {
            disableCanvasButtons();
        }

        chatSubmitButton.textContent = 'Send';
        inLongOperation = false;
        actualContextDir = null;
        updateViewContextDirMenuState();
        clearContextEnabled = false;
        clearContextButton.setAttribute("style", "display: none !important;");
        contextDataSpan.innerText = "<<<" + "..." + ">>>  ";
        contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-invisible");

        console.log("--- Clean history message sent to server.");
        return true;
    };

    const callbackOnCanc = () => {
        confirmationByUser = false;
        console.log("Clean history was dismissed...");
        return false;
    };

    confirmationByUser = false;
    preRenderConfirmationDialog('Confirmation...', 'Are you sure you want to clean the history?', 'This will clear the current context followed by Tlamatini and reset the conversation.', callbackOnCont, callbackOnCanc);
    renderConfirmationDialog();
}

function CancelAllAndLogout(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();

    const callbackOnCont = () => {
        try {
            sendChatSocketMessage(JSON.stringify({
                'type': 'cancel-all',
                'message': 'cancel'
            }));
            confirmationByUser = true;
            console.log("--- Cancel all message sent to server.");
        } catch (err) {
            console.error('Failed to send cancel message:', err);
        } finally {
            const addr = logoutButton.getAttribute('param');
            const debouncedFunction = debounce(() => { window.top.location.href = addr; });
            debouncedFunction();
        }
        return true;
    };

    const callbackOnCanc = () => {
        confirmationByUser = false;
        console.log("Cancel and Logout was dismissed...");
        return false;
    };

    if (inLongOperation === true) {
        confirmationByUser = false;
        preRenderConfirmationDialog('Confirmation...', 'Are you sure you want to cancel now?', 'Cancel will break the actual operation and drop the actual context', callbackOnCont, callbackOnCanc);
        renderConfirmationDialog();
    } else {
        const logoutBtn = document.getElementById('logout-button');
        const addr = logoutBtn.getAttribute('param');
        const debouncedFunction = debounce(() => { window.top.location.href = addr; });
        debouncedFunction();
    }
}

function OpenOmissionsDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();

    if (inLongOperation === true) {
        console.log("Dialog omissions can't be opened during a long operation...");
        return;
    }

    const callbackOnCont = () => {
        try {
            fileTypeOmissions = omissionContentInput.value;
            sendChatSocketMessage(JSON.stringify({
                'type': 'set-file-omissions',
                'message': fileTypeOmissions
            }));
            console.log("--- Sent set-file-omissions message sent to server.");
        } catch (err) {
            console.error('--- Failed to send omissions message:', err);
        }
        return true;
    };

    const callbackOnCanc = () => {
        console.log("--- Omissions dialog was dismissed...");
        return false;
    };

    preRenderOmissionsDialog("Omissions...", "Specify extensions or filenames to be omitted, separated by coma", "File omission will completely ignore this files in the retrieval process.", callbackOnCont, callbackOnCanc);
    renderOmissionsDialog();
}

function OpenMcpsDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();

    if (inLongOperation === true) {
        console.log("Dialog mcps can't be opened during a long operation...");
        return;
    }

    const callbackOnCont = () => {
        try {
            const mcp1Checked = $("#mcp-1").is(":checked");
            const mcp2Checked = $("#mcp-2").is(":checked");
            const message2send = JSON.stringify({
                'type': 'set-mcps',
                'message': '1=' + label_mcp1.innerText + "=" + mcp1Checked + "," + '2=' + label_mcp2.innerText + "=" + mcp2Checked
            });
            sendChatSocketMessage(message2send);
            console.log("Message sent to socket: ", message2send);
            console.log("--- Sent set-mcps message sent to server.");
        } catch (err) {
            console.error('--- Failed to send mcps message:', err);
        }

        console.log("--->>> tools: ", tools);
        if (tools.length > 0) {
            let completeTools = "";
            for (const tool of tools) {
                if (!tool || !tool.name) {
                    continue;
                }
                const checked = $("#" + tool.name).is(":checked");
                completeTools = completeTools + tool.name + "=" + tool.description + "=" + checked + ",";
            }
            console.log("--->>> complete tools: ", completeTools);
            sendChatSocketMessage(JSON.stringify({
                'type': 'set-tools',
                'message': completeTools
            }));
            console.log("--- Sent set-tools message sent to server, complete tools: ", completeTools);
        }
        return true;
    };

    const callbackOnCanc = () => {
        console.log("--- Mcps dialog was dismissed...");
        return false;
    };

    preRenderMcpsDialog("Configure Mcps...", "MCPs will be used to provide additional information to Tlamatini.", "Specify the Rag-MCPs to be used:", "Specify the Tool-MCPs to be used:", callbackOnCont, callbackOnCanc);
    renderMcpsDialog();
}

function OpenAgentsDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();

    if (inLongOperation === true) {
        console.log("Dialog Agents can't be opened during a long operation...");
        return;
    }

    const callbackOnCont = () => {
        console.log("--->>> agents: ", agents);
        if (agents.length > 0) {
            let completeAgents = "";
            for (const agent of agents) {
                if (!agent || !agent.name) {
                    continue;
                }
                const checked = $("#" + agent.name).is(":checked");
                completeAgents = completeAgents + agent.name + "=" + agent.description + "=" + checked + ",";
            }
            console.log("--->>> complete agents: ", completeAgents);
            sendChatSocketMessage(JSON.stringify({
                'type': 'set-agents',
                'message': completeAgents
            }));
            console.log("--- Sent set-agents message sent to server, complete agents: ", completeAgents);
        }
        return true;
    };

    const callbackOnCanc = () => {
        console.log("--- Agents dialog was dismissed...");
        return false;
    };

    preRenderAgentsDialog("Configure Agents...", "Agents will be used to provide additional information to Tlamatini.", "Specify the Rag-Agents to be used:", callbackOnCont, callbackOnCanc);
    renderAgentsDialog();
}

// ----------------------------------------------------------------
// Chat form submit handler
// ----------------------------------------------------------------

document.getElementById('chat-form').onsubmit = function (e) {
    e.preventDefault();

    const callbackOnCont = () => {
        console.log("--- Cancel confirmed by user, sending cancel-current message...");

        const cancelMsg = JSON.stringify({
            'type': 'cancel-current',
            'message': 'cancel'
        });
        console.log("--- Sending cancel message:", cancelMsg);
        if (!sendChatSocketMessage(cancelMsg, 'Live connection lost. Use Reconnect or refresh before cancelling the current request.')) {
            return;
        }
        console.log("--- cancel-current message sent to server successfully");
        const debouncedFunction = debounce(unsetContextButton);
        debouncedFunction();
        // Reset UI state after cancellation
        chatInput.readOnly = false;
        chatInput.style.backgroundColor = '#40414F';
        if (chatSubmitButton) chatSubmitButton.textContent = 'Send';
        chatSubmitButton.disabled = false;
        inLongOperation = false;
        lapseLoadingContext = false;
        const spinner = document.getElementById('wait-spinner');
        if (spinner && spinner.parentNode) spinner.parentNode.removeChild(spinner);
        contextEnabled = true;
        contextMenuButton.removeAttribute('disabled');
        contextMenuButton.setAttribute('data-bs-toggle', 'dropdown');
        mcpsMenuButton.removeAttribute('disabled', 'disabled');
        mcpsMenuButton.setAttribute('data-bs-toggle', 'dropdown');
        agentsMenuButton.removeAttribute('disabled', 'disabled');
        agentsMenuButton.setAttribute('data-bs-toggle', 'dropdown');
        cleanCanvasButton.style.backgroundColor = "darkgreen";
        cleanCanvasButton.disabled = false;
        cleanCanvasEnabled = true;
        reopenOpenCanvasButton.style.backgroundColor = "darkgreen";
        reopenOpenCanvasButton.disabled = false;
        copyCanvasButton.style.backgroundColor = "darkgreen";
        copyCanvasButton.disabled = false;
        clearContextEnabled = false;
        clearContextButton.setAttribute("style", "display: none !important;");
        setContextText("<<<" + "..." + ">>>  ");
        contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-invisible");
        actualContextDir = null;
        updateViewContextDirMenuState();
        console.log("--- actualContextDir reset to null on cancel.");
    };

    const callbackOnCanc = () => {
        console.log("Cancel was dismissed...");
        return false;
    };

    if ((inLongOperation === true && (chatSubmitButton && chatSubmitButton.textContent === 'Cancel')) || lapseLoadingContext === true) {
        console.log("--- Cancel dialog triggered. inLongOperation: " + inLongOperation + ", lapseLoadingContext: " + lapseLoadingContext);
        confirmationByUser = false;
        preRenderConfirmationDialog('Confirmation...', 'Are you sure you want to cancel now?', 'Cancel will break the actual operation and drop the actual context', callbackOnCont, callbackOnCanc);
        renderConfirmationDialog();
    } else {
        const rawMessage = chatInput.value;
        const message = rawMessage;
        console.log("message: " + message);
        if (rawMessage.trim() === '') return;
        const messageSent = sendChatSocketMessage(JSON.stringify({
            'message': rawMessage,
            'multi_turn_enabled': isMultiTurnEnabled(),
            'exec_report_enabled': isExecReportEnabled()
        }));
        if (!messageSent) {
            return;
        }
        chatHistory.push(rawMessage);
        historyIndex = chatHistory.length;
        tempInput = '';
        try {
            sessionStorage.setItem('chatHistory', JSON.stringify(chatHistory));
            sessionStorage.setItem('historyIndex', String(historyIndex));
        } catch (err) {
            console.error("Catched error in onsubmit(): " + err);
        }
        chatInput.value = '';
    }
};

// ----------------------------------------------------------------
// window.onload  –  wire up all event listeners
// ----------------------------------------------------------------

window.onload = () => {
    chatLog.scrollTop = chatLog.scrollHeight;
    updateViewContextDirMenuState();
    applyStoredMultiTurnState();
    applyStoredExecReportState();
    if (openButton) {
        openButton.addEventListener('click', (e) => {
            e.preventDefault();
            openCanvas();
        });
    }
    if (reopenOpenCanvasButton) {
        reopenOpenCanvasButton.addEventListener('click', (e) => {
            e.preventDefault();
            if (openEnabled === false) {
                console.log("Reopen canvas is not allowed at this moment...");
                return;
            }
            reopenCanvas();
        });
    }
    if (setDirContextMenu) {
        setDirContextMenu.addEventListener('click', async (e) => {
            e.preventDefault();
            if (contextEnabled === false) {
                return;
            }
            if (window && 'showDirectoryPicker' in window) {
                try {
                    const dirHandle = await window.showDirectoryPicker();
                    const dirName = (dirHandle && dirHandle.name) ? dirHandle.name : 'selected_directory';
                    const sent = sendChatSocketMessage(JSON.stringify({
                        'type': 'set-directory-as-context',
                        'message': dirName
                    }));
                    if (!sent) {
                        return;
                    }
                    actualContextDir = null;
                    updateViewContextDirMenuState();
                    clearContextEnabled = false;
                    clearContextButton.setAttribute("style", "display: none !important;");
                    setContextText("<<< pending directory context: " + dirName + " >>>");
                    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-visible");
                    console.log("--- Waiting for server confirmation of directory context: " + dirName);
                } catch (err) {
                    console.error("Catched error in listener of setDirContextMenu: " + err);
                }
            }
        });
    }
    if (setFileContextMenu) {
        setFileContextMenu.addEventListener('click', async (e) => {
            e.preventDefault();
            if (contextEnabled === false) {
                return;
            }

            const callback2SetFileAsContext = () => {
                const type = "set-canvas-as-context";
                const codeRegex = /<<< ([\w.-]+) >>>/s;
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
                    const sent = sendChatSocketMessage(JSON.stringify({
                        'type': type,
                        'message': filename,
                        'content': content
                    }));
                    if (!sent) {
                        return;
                    }
                    clearContextEnabled = false;
                    clearContextButton.setAttribute("style", "display: none !important;");
                    actualContextDir = null;
                    updateViewContextDirMenuState();
                    setContextText("<<< pending context: " + filename + " >>>");
                    contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-visible");
                    setContextButton();
                    console.log("--- Waiting for server confirmation of file context: " + filename);
                    console.log("...Rebuild rag action sent.");
                }
            };
            loadFileContent(true, callback2SetFileAsContext);
        });
    }
    if (viewContextDirInCanvasMenu) {
        viewContextDirInCanvasMenu.addEventListener('click', async (e) => {
            e.preventDefault();
            if (contextEnabled === false) {
                return;
            }
            if (actualContextDir === null || actualContextDir === '') {
                console.log("--- actualContextDir is null or empty, menu action ignored.");
                return;
            }
            if (actualContextDir !== null) {
                try {
                    const sent = sendChatSocketMessage(JSON.stringify({
                        'type': 'view-context-dir-in-canvas',
                        'message': actualContextDir
                    }));
                    if (!sent) {
                        return;
                    }
                    console.log("--- actualContextDir is: " + actualContextDir + ", message 'view-context-dir-in-canvas' has been sent.");
                    return;
                } catch (err) {
                    console.error("--- Catched error in listener of viewContextDirInCanvasMenu: " + err);
                }
            }
            if (actualContextDir == null)
                console.log("--- actualContextDir is null, message 'view-context-dir-in-canvas' not sent.");
        });
    }
    if (clearContextButton) {
        clearContextButton.addEventListener('click', async (e) => {
            e.preventDefault();
            ClearContext(e);
        });
    }
    if (cleanCanvasButton) {
        cleanCanvasButton.addEventListener('click', (e) => {
            e.preventDefault();
            if (cleanCanvasEnabled === false) {
                return;
            }
            cleanCanvas();
        });
    }
    if (cleanHistoryButton) {
        cleanHistoryButton.addEventListener('click', (e) => {
            CleanHistory(e);
        });
    }
    const initialDataScript = document.getElementById('initial_messages');
    if (initialDataScript && initialDataScript.textContent) {
        try {
            const initialMessages = JSON.parse(initialDataScript.textContent);
            renderInitialMessages(initialMessages);
            if (Array.isArray(initialMessages)) {
                chatHistory = initialMessages
                    .filter(m => m && m.username === userUsername && typeof m.message === 'string' && m.message.trim() !== '')
                    .map(m => m.message);
                historyIndex = chatHistory.length;
            }
            try {
                const stored = sessionStorage.getItem('chatHistory');
                if (stored) {
                    const parsed = JSON.parse(stored);
                    if (Array.isArray(parsed)) {
                        chatHistory = parsed;
                        const storedIndex = parseInt(sessionStorage.getItem('historyIndex') || String(parsed.length), 10);
                        historyIndex = isNaN(storedIndex) ? parsed.length : storedIndex;
                    }
                }
            } catch (err) {
                console.error("Catched error at getItem of ChatHistory: " + err);
            }
        } catch (e) {
            console.error('Failed to parse initial messages JSON:', e);
        }
    }
    rotateTitle();

    $('#internetEnabled').click(function () {
        const isChecked = this.checked;
        console.log('InternetEnabled is:', isChecked);
        if (isChecked) {
            sendChatSocketMessage(JSON.stringify({
                'type': 'enable-llm-internet-access',
                'message': ''
            }));
        } else {
            sendChatSocketMessage(JSON.stringify({
                'type': 'disable-llm-internet-access',
                'message': ''
            }));
        }
    });
    if (multiTurnCheckbox) {
        multiTurnCheckbox.addEventListener('change', function () {
            persistMultiTurnState(!!this.checked);
        });
    }
    if (execReportCheckbox) {
        execReportCheckbox.addEventListener('change', function () {
            persistExecReportState(!!this.checked);
        });
    }
    syncClearContextMenuState();
    updateViewContextDirMenuState();

    // Detect installed apps for "Open in..." dropdown
    detectInstalledApps();
};

// ----------------------------------------------------------------
// Ollama helper
// ----------------------------------------------------------------

function listOllamaModels() { // eslint-disable-line no-unused-vars
    const ollamaConfigScript = document.getElementById('ollama_config');
    let ollamaBaseUrl = 'http://localhost:11434';

    if (ollamaConfigScript && ollamaConfigScript.textContent) {
        try {
            ollamaBaseUrl = JSON.parse(ollamaConfigScript.textContent);
        } catch (e) {
            console.error('Error parsing ollama_base_url from config:', e);
        }
    }

    fetch(`${ollamaBaseUrl}/api/tags`)
        .then(response => response.json())
        .then(data => {
            console.log('Available Ollama models:');
            if (data.models && Array.isArray(data.models)) {
                data.models.forEach(model => {
                    if (model.name) {
                        console.log(" - " + model.name);
                    }
                });
            } else {
                console.warn('No models found in response');
            }
        })
        .catch(error => console.error('Error fetching Ollama models:', error));
}

