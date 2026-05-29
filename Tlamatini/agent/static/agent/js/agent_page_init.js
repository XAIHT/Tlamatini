// ============================================================
// agent_page_init.js  –  Initialization, event wiring & actions
// ============================================================
/* global syncClearContextMenuState, isMultiTurnEnabled, applyStoredMultiTurnState, multiTurnCheckbox, persistMultiTurnState, isExecReportEnabled, applyStoredExecReportState, execReportCheckbox, persistExecReportState, isAcpxEnabled, applyStoredAcpxState, acpxCheckbox, persistAcpxState, isAskExecsEnabled, applyStoredAskExecsState, syncAskExecsAvailability, askExecsCheckbox, persistAskExecsState */

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
    skills = [];
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
// ACPX-Skills dropdown handlers — see skills_dialog.js for the
// jQuery-UI dialog implementations they delegate to.
// ----------------------------------------------------------------
function OpenSkillsConfigureDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Dialog Skills can't be opened during a long operation...");
        return;
    }
    const callbackOnCont = () => {
        if (!Array.isArray(skills) || skills.length === 0) {
            console.log("--- No skills to save.");
            return true;
        }
        // Payload mirrors set-tools / set-agents: `name=description=true/false,...`
        // The skill name is the SKILL.md frontmatter `name` directly (no
        // `skill-N` prefix because the Skill DB row keys on `name`).
        let completeSkills = "";
        for (const skill of skills) {
            if (!skill || !skill.name) continue;
            const checked = $("#skill-checkbox-" + CSS.escape(skill.name)).is(":checked");
            const desc = (skill.description || '').replace(/[,=]/g, ' ');
            completeSkills += skill.name + "=" + desc + "=" + checked + ",";
        }
        sendChatSocketMessage(JSON.stringify({
            'type': 'set-skills',
            'message': completeSkills
        }));
        console.log("--- Sent set-skills message:", completeSkills);
        return true;
    };
    const callbackOnCanc = () => false;
    preRenderSkillsConfigureDialog(
        "Configure ACPX-Skills...",
        "Toggle SKILL.md packages on or off. Disabled skills are hidden from list_skills and rejected by invoke_skill.",
        callbackOnCont, callbackOnCanc
    );
    renderSkillsConfigureDialog();
}

function OpenSkillsBrowseDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Dialog Skills-Browse can't be opened during a long operation...");
        return;
    }
    openSkillsBrowseDialog();
}

function OpenSkillsDiagnosticsDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Dialog Skills-Diagnostics can't be opened during a long operation...");
        return;
    }
    openSkillsDiagnosticsDialog();
}

function ReloadSkillRegistry(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    reloadSkillRegistry();
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
            'exec_report_enabled': isExecReportEnabled(),
            'acpx_enabled': isAcpxEnabled(),
            'ask_execs_enabled': isAskExecsEnabled()
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
    applyStoredAcpxState();
    applyStoredAskExecsState();
    syncAskExecsAvailability();
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
            try {
                // Native server-side picker returns the FULL absolute path,
                // so a project nested any number of levels deep under the
                // application root loads correctly (the old
                // window.showDirectoryPicker() only sent the leaf folder name
                // and broke every non-direct-child directory).
                const chosenPath = await _pickContextDirectory();
                if (!chosenPath) {
                    // User canceled, or picker unavailable and no path typed.
                    return;
                }
                const sent = sendChatSocketMessage(JSON.stringify({
                    'type': 'set-directory-as-context',
                    'message': chosenPath
                }));
                if (!sent) {
                    return;
                }
                const dirLabel = chosenPath.split(/[\\/]/).filter(Boolean).pop() || chosenPath;
                actualContextDir = null;
                updateViewContextDirMenuState();
                clearContextEnabled = false;
                clearContextButton.setAttribute("style", "display: none !important;");
                setContextText("<<< pending directory context: " + dirLabel + " >>>");
                contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-visible");
                console.log("--- Waiting for server confirmation of directory context: " + chosenPath);
            } catch (err) {
                console.error("Catched error in listener of setDirContextMenu: " + err);
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
            // Ask-Execs availability depends on Multi-Turn — re-sync the
            // enabled/disabled state of its checkbox on every toggle.
            syncAskExecsAvailability();
        });
    }
    if (execReportCheckbox) {
        execReportCheckbox.addEventListener('change', function () {
            persistExecReportState(!!this.checked);
        });
    }
    if (acpxCheckbox) {
        acpxCheckbox.addEventListener('change', function () {
            persistAcpxState(!!this.checked);
        });
    }
    if (askExecsCheckbox) {
        askExecsCheckbox.addEventListener('change', function () {
            persistAskExecsState(!!this.checked);
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

function getConfiguredOllamaBaseUrl() {
    const ollamaConfigScript = document.getElementById('ollama_config');
    let ollamaBaseUrl = 'http://localhost:11434';

    if (ollamaConfigScript && ollamaConfigScript.textContent) {
        try {
            ollamaBaseUrl = JSON.parse(ollamaConfigScript.textContent);
        } catch (e) {
            console.error('Error parsing ollama_base_url from config:', e);
        }
    }
    return ollamaBaseUrl;
}

/**
 * Fetch the model catalog from the configured Ollama server and return the
 * list of model names as a Promise. Resolves to ``string[]`` on success.
 * Rejects when the server is unreachable or returns a malformed payload —
 * callers use that rejection to surface the "Ollama not running" alert.
 *
 * The function ALSO keeps its legacy side effect of logging the catalog to
 * the console so existing diagnostic flows that called it without awaiting
 * the result still work the same way.
 */
function listOllamaModels(options = {}) {
    const { silent = false, overrideBaseUrl = null, timeoutMs = 10000 } = options;
    const ollamaBaseUrl = overrideBaseUrl || getConfiguredOllamaBaseUrl();

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    return fetch(`${ollamaBaseUrl}/api/tags`, { signal: controller.signal })
        .then(response => {
            if (!response.ok) {
                throw new Error(`Ollama returned HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (!data || !Array.isArray(data.models)) {
                throw new Error('Ollama response has no "models" array');
            }
            const names = data.models
                .map(m => (m && typeof m.name === 'string') ? m.name : null)
                .filter(n => !!n);
            if (!silent) {
                console.log('Available Ollama models:');
                names.forEach(n => console.log(" - " + n));
            }
            return names;
        })
        .finally(() => clearTimeout(timer));
}

// ----------------------------------------------------------------
// Config dialog handlers (Models / URLs)
// ----------------------------------------------------------------

let _configModelsBaseline = null;
let _configUrlsBaseline = null;

function _snapshotConfigValues(values) {
    const snapshot = {};
    Object.keys(values || {}).forEach(key => {
        snapshot[key] = String(values[key] == null ? '' : values[key]);
    });
    return snapshot;
}

function _configValuesDiffer(baseline, current) {
    if (!baseline || !current) return false;
    const keys = new Set([...Object.keys(baseline), ...Object.keys(current)]);
    for (const key of keys) {
        const a = String(baseline[key] == null ? '' : baseline[key]);
        const b = String(current[key] == null ? '' : current[key]);
        if (a !== b) return true;
    }
    return false;
}

function _showReconnectRequiredAfterDialogClose() {
    setTimeout(() => {
        preRenderReconnectRequiredDialog(
            'Reconnection required...',
            'You must execute a reconnection (Reconnect) in order to get/set the new configured values.',
            'Click the Reconnect button in the toolbar to apply the changes to the live session.'
        );
        renderReconnectRequiredDialog();
    }, 100);
}

async function _loadConfigSectionValues(section) {
    const response = await fetch(`/agent/load_config_section/${section}/`, {
        credentials: 'same-origin'
    });
    if (!response.ok) {
        throw new Error(`Failed to load ${section} config: HTTP ${response.status}`);
    }
    const data = await response.json();
    if (!data || data.success !== true || !data.values) {
        throw new Error(`Failed to load ${section} config: bad payload`);
    }
    return data.values;
}

function _populateConfigForm(form, values) {
    if (!form) return;
    const inputs = form.querySelectorAll('input[data-config-key]');
    inputs.forEach(input => {
        const key = input.getAttribute('data-config-key');
        input.value = (values && Object.prototype.hasOwnProperty.call(values, key)) ? String(values[key]) : '';
        input.classList.remove('config-form-invalid');
    });
}

function _collectConfigFormValues(form) {
    const values = {};
    if (!form) return values;
    const inputs = form.querySelectorAll('input[data-config-key]');
    inputs.forEach(input => {
        const key = input.getAttribute('data-config-key');
        values[key] = input.value.trim();
    });
    return values;
}

function _markInvalidInputs(form, invalidKeys) {
    if (!form) return;
    const inputs = form.querySelectorAll('input[data-config-key]');
    inputs.forEach(input => {
        const key = input.getAttribute('data-config-key');
        if (invalidKeys.has(key)) {
            input.classList.add('config-form-invalid');
        } else {
            input.classList.remove('config-form-invalid');
        }
    });
}

async function _saveConfigSection(endpoint, payload) {
    const response = await fetch(endpoint, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        body: JSON.stringify(payload)
    });
    let body = null;
    try {
        body = await response.json();
    } catch (_e) {
        // Non-JSON body (e.g. 500 HTML page); fall through with body=null.
    }
    if (!response.ok) {
        const err = new Error(`Save failed: HTTP ${response.status}`);
        err.body = body;
        throw err;
    }
    if (!body || body.success !== true) {
        const err = new Error('Save failed on server');
        err.body = body;
        throw err;
    }
    return body;
}

function OpenConfigModelsDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Config Models dialog can't be opened during a long operation...");
        return;
    }

    _loadConfigSectionValues('models')
        .then(values => {
            _populateConfigForm(configModelsForm, values);
            _configModelsBaseline = _snapshotConfigValues(_collectConfigFormValues(configModelsForm));
            preRenderConfigModelsDialog(
                'Configure Models...',
                'Set the Ollama model used for each subsystem.',
                'Each model must already exist in the Ollama catalog before saving.'
            );
            renderConfigModelsDialog();
        })
        .catch(err => {
            console.error('Failed to load Models config:', err);
            alert('Could not load the current configuration from the server. Please try again.');
        });
}

function OpenConfigUrlsDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Config URLs dialog can't be opened during a long operation...");
        return;
    }

    _loadConfigSectionValues('urls')
        .then(values => {
            _populateConfigForm(configUrlsForm, values);
            _configUrlsBaseline = _snapshotConfigValues(_collectConfigFormValues(configUrlsForm));
            preRenderConfigUrlsDialog(
                'Configure URLs...',
                'Set the base URLs, hosts and ports used by Tlamatini.',
                'URLs must include an http(s):// or ws(s):// scheme; ports must be 1-65535.'
            );
            renderConfigUrlsDialog();
        })
        .catch(err => {
            console.error('Failed to load URLs config:', err);
            alert('Could not load the current configuration from the server. Please try again.');
        });
}

/**
 * Validate the URLs form client-side, by data-config-type. Returns
 * { ok, errors } where errors is { key: humanReason } when ok is false.
 */
function _validateUrlsForm(form) {
    const errors = {};
    if (!form) return { ok: false, errors };
    const inputs = form.querySelectorAll('input[data-config-key]');
    inputs.forEach(input => {
        const key = input.getAttribute('data-config-key');
        const type = input.getAttribute('data-config-type') || 'url';
        const raw = (input.value || '').trim();
        if (!raw) {
            errors[key] = 'must not be empty';
            return;
        }
        if (type === 'url') {
            let parsed;
            try {
                parsed = new URL(raw);
            } catch (_e) {
                errors[key] = 'is not a valid URL';
                return;
            }
            const scheme = (parsed.protocol || '').replace(':', '').toLowerCase();
            if (!['http', 'https', 'ws', 'wss'].includes(scheme)) {
                errors[key] = 'must use http(s):// or ws(s):// scheme';
                return;
            }
            if (!parsed.host) {
                errors[key] = 'must include a host';
                return;
            }
        } else if (type === 'host') {
            const ipv4 = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
            const hostname = /^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(?:\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$/;
            if (!ipv4.test(raw) && !hostname.test(raw)) {
                errors[key] = 'must be a hostname (e.g. localhost) or IPv4 address';
            }
        } else if (type === 'port') {
            const port = Number(raw);
            if (!Number.isInteger(port) || port < 1 || port > 65535) {
                errors[key] = 'must be an integer between 1 and 65535';
            }
        }
    });
    return { ok: Object.keys(errors).length === 0, errors };
}

function _labelForConfigInput(input) {
    if (!input || !input.id) return '';
    const label = document.querySelector(`label[for="${input.id}"]`);
    return label ? label.textContent.trim() : input.id;
}

function _formatErrorsForAlert(form, errors) {
    const lines = [];
    Object.keys(errors).forEach(key => {
        const input = form ? form.querySelector(`input[data-config-key="${key}"]`) : null;
        const label = input ? _labelForConfigInput(input) : key;
        lines.push(`  • ${label}: ${errors[key]}`);
    });
    return lines.join('\n');
}

/**
 * Save handler for the Models dialog. Returns a Promise that resolves to
 * ``true`` on success (so the dialog can close) or ``false`` on validation
 * failure (so the dialog stays open and the user can correct the inputs).
 */
async function _saveConfigModels() {
    const values = _collectConfigFormValues(configModelsForm);

    // 1) Basic non-empty check before bothering Ollama
    const invalidKeys = new Set();
    const emptyErrors = {};
    Object.keys(values).forEach(key => {
        if (!values[key]) {
            emptyErrors[key] = 'must not be empty';
            invalidKeys.add(key);
        }
    });
    if (invalidKeys.size > 0) {
        _markInvalidInputs(configModelsForm, invalidKeys);
        alert('The following fields are required:\n\n' + _formatErrorsForAlert(configModelsForm, emptyErrors));
        return false;
    }

    // 2) Fetch the live Ollama catalog. If this fails, Ollama is likely down.
    let catalog;
    try {
        catalog = await listOllamaModels({ silent: true });
    } catch (err) {
        console.error('Failed to query Ollama for model catalog:', err);
        alert('Could not reach the Ollama server.\n\nPlease make sure the Ollama server is running before clicking "Save" again.');
        return false;
    }

    if (!Array.isArray(catalog) || catalog.length === 0) {
        alert('The Ollama server replied with an empty catalog.\n\nPlease make sure at least one model is installed in Ollama before clicking "Save" again.');
        return false;
    }

    const catalogSet = new Set(catalog);

    // 3) Every model in the form must be in the catalog.
    const missing = {};
    Object.keys(values).forEach(key => {
        if (!catalogSet.has(values[key])) {
            missing[key] = `model "${values[key]}" is not installed in Ollama`;
            invalidKeys.add(key);
        }
    });
    if (Object.keys(missing).length > 0) {
        _markInvalidInputs(configModelsForm, invalidKeys);
        alert('The following models are NOT installed in Ollama:\n\n'
            + _formatErrorsForAlert(configModelsForm, missing)
            + '\n\nPlease correct them (or install them in Ollama) before clicking "Save" again.');
        return false;
    }

    // 4) All validated — persist on the server.
    try {
        await _saveConfigSection('/agent/save_config_models/', values);
    } catch (err) {
        console.error('Failed to save Models config:', err);
        const serverErrors = err && err.body && err.body.errors;
        if (serverErrors && typeof serverErrors === 'object') {
            _markInvalidInputs(configModelsForm, new Set(Object.keys(serverErrors)));
            alert('Server-side validation failed:\n\n' + _formatErrorsForAlert(configModelsForm, serverErrors));
        } else {
            alert('Saving the configuration failed: ' + (err.message || 'unknown error'));
        }
        return false;
    }

    _markInvalidInputs(configModelsForm, new Set());
    console.log('--- Saved Models config.');

    const changed = _configValuesDiffer(_configModelsBaseline, _snapshotConfigValues(values));
    _configModelsBaseline = null;
    if (changed) {
        _showReconnectRequiredAfterDialogClose();
    }
    return true;
}

/**
 * Save handler for the URLs dialog. Same return convention as Models.
 */
async function _saveConfigUrls() {
    const { ok, errors } = _validateUrlsForm(configUrlsForm);
    if (!ok) {
        _markInvalidInputs(configUrlsForm, new Set(Object.keys(errors)));
        alert('The following fields are invalid:\n\n'
            + _formatErrorsForAlert(configUrlsForm, errors)
            + '\n\nPlease correct them before clicking "Save" again.');
        return false;
    }

    const values = _collectConfigFormValues(configUrlsForm);
    // Send ports as numbers (the server is strict about it).
    const payload = { ...values };
    const portInputs = configUrlsForm.querySelectorAll('input[data-config-type="port"]');
    portInputs.forEach(input => {
        const key = input.getAttribute('data-config-key');
        payload[key] = Number(values[key]);
    });

    try {
        await _saveConfigSection('/agent/save_config_urls/', payload);
    } catch (err) {
        console.error('Failed to save URLs config:', err);
        const serverErrors = err && err.body && err.body.errors;
        if (serverErrors && typeof serverErrors === 'object') {
            _markInvalidInputs(configUrlsForm, new Set(Object.keys(serverErrors)));
            alert('Server-side validation failed:\n\n' + _formatErrorsForAlert(configUrlsForm, serverErrors));
        } else {
            alert('Saving the configuration failed: ' + (err.message || 'unknown error'));
        }
        return false;
    }

    _markInvalidInputs(configUrlsForm, new Set());
    console.log('--- Saved URLs config.');

    const changed = _configValuesDiffer(_configUrlsBaseline, _snapshotConfigValues(values));
    _configUrlsBaseline = null;
    if (changed) {
        _showReconnectRequiredAfterDialogClose();
    }
    return true;
}

// ----------------------------------------------------------------
// DB -> Backup database dialog
// ----------------------------------------------------------------

let _backupDbValidationTimer = null;
let _backupDbInputListenerAttached = false;

function _setBackupDbStatus(text, kind) {
    if (!backupDbStatusElement) return;
    backupDbStatusElement.innerText = text || '';
    backupDbStatusElement.classList.remove('backup-db-status-ok', 'backup-db-status-warn', 'backup-db-status-error');
    if (kind === 'ok') {
        backupDbStatusElement.classList.add('backup-db-status-ok');
    } else if (kind === 'warn') {
        backupDbStatusElement.classList.add('backup-db-status-warn');
    } else if (kind === 'error') {
        backupDbStatusElement.classList.add('backup-db-status-error');
    }
}

async function _checkBackupDbDirectory(rawPath) {
    const url = '/agent/check_backup_directory/?path=' + encodeURIComponent(rawPath);
    const response = await fetch(url, {
        method: 'GET',
        credentials: 'same-origin'
    });
    let body = null;
    try {
        body = await response.json();
    } catch (_e) {
        // Non-JSON; fall through.
    }
    if (!response.ok) {
        const err = new Error(`Validation failed: HTTP ${response.status}`);
        err.body = body;
        throw err;
    }
    return body || {};
}

function _onBackupDbInputChanged() {
    if (!backupDbTargetDirInput) return;
    const raw = (backupDbTargetDirInput.value || '').trim();
    if (_backupDbValidationTimer) {
        clearTimeout(_backupDbValidationTimer);
        _backupDbValidationTimer = null;
    }
    backupDbTargetDirInput.classList.remove('config-form-invalid');
    if (!raw) {
        _setBackupDbStatus('', '');
        return;
    }
    _setBackupDbStatus('Checking path...', '');
    _backupDbValidationTimer = setTimeout(() => {
        _checkBackupDbDirectory(raw)
            .then(info => {
                const currentRaw = (backupDbTargetDirInput.value || '').trim();
                if (currentRaw !== raw) {
                    return; // user kept typing; a newer check will fire
                }
                if (info.kind === 'directory') {
                    _setBackupDbStatus('Directory exists. db.sqlite3 will be saved here.', 'ok');
                    backupDbTargetDirInput.classList.remove('config-form-invalid');
                } else if (info.kind === 'file') {
                    _setBackupDbStatus('A filename was specified — please specify the directory only.', 'warn');
                    backupDbTargetDirInput.classList.add('config-form-invalid');
                } else {
                    _setBackupDbStatus('Directory does not exist.', 'error');
                    backupDbTargetDirInput.classList.add('config-form-invalid');
                }
            })
            .catch(err => {
                console.error('Failed to validate backup directory:', err);
                _setBackupDbStatus('Could not validate the directory.', 'error');
            });
    }, 350);
}

// Friendly handler for a failed native picker. When the server reports the
// picker is unavailable (no GUI, or a frozen build whose Tcl/Tk data tree
// wasn't bundled — "Can't find a usable init.tcl"), we steer the user to
// the manual path field instead of dumping a raw multi-line Tcl error in
// an alert. The dialog stays usable either way: the path can always be
// typed. `inputEl` is the dialog's manual-path field; `kindLabel` is
// 'folder' or 'file' for the generic fallback wording.
function _notifyPickerUnavailable(body, fallbackReason, inputEl, kindLabel) {
    const unavailable = !!(body && body.picker_unavailable);
    const friendly = (body && body.message)
        || ('Could not open the ' + kindLabel + ' picker: '
            + (fallbackReason || 'unknown error'));
    if (unavailable && inputEl) {
        // Make the manual path field the obvious next step.
        try { inputEl.focus(); } catch (_e) { /* ignore */ }
        try {
            inputEl.setAttribute(
                'placeholder',
                'Native browser unavailable — type the full path here'
            );
        } catch (_e) { /* ignore */ }
    }
    alert(friendly);
}

// Native server-side folder picker for the chat "Set directory as context"
// menu. Returns the chosen ABSOLUTE path, or '' when the user canceled or no
// path was provided.
//
// Why not window.showDirectoryPicker(): that browser API only exposes the
// LEAF folder name (FileSystemDirectoryHandle.name), never the full path, so
// the server could only locate a directory that was a direct child of the
// runtime root. A project nested several levels deep
// (<app>/applications/proj/src) was impossible to load. The native Win32
// picker returns the real full path, which path_guard accepts for any depth
// under the application root. On hosts without a native dialog (e.g.
// non-Windows) we fall back to a manual path prompt.
async function _pickContextDirectory() {
    try {
        const response = await fetch('/agent/pick_context_directory/', {
            method: 'GET',
            credentials: 'same-origin'
        });
        let body = null;
        try { body = await response.json(); } catch (_e) { /* non-JSON */ }
        if (response.ok && body) {
            if (typeof body.path === 'string' && body.path) {
                return body.path;
            }
            if (body.canceled) {
                return '';  // user closed the dialog — respect it, no fallback
            }
            if (body.error || body.picker_unavailable) {
                return _promptForContextDirectory(body);
            }
        }
        if (!response.ok) {
            return _promptForContextDirectory(body);
        }
    } catch (err) {
        console.error('Native context-directory picker failed:', err);
        return _promptForContextDirectory(null);
    }
    return '';
}

// Manual-entry fallback used when the native folder picker is unavailable
// (no GUI / non-Windows). Mirrors the Set-DB / Backup-DB "type the path"
// guidance. Returns the trimmed path the user typed, or '' if canceled.
function _promptForContextDirectory(body) {
    const friendly = (body && body.message)
        || ('The native folder browser is unavailable on this machine. '
            + 'Please type or paste the FULL absolute path to the project '
            + 'directory (it must live under the application root).');
    try {
        const typed = window.prompt(friendly, '');
        return (typed && typed.trim()) ? typed.trim() : '';
    } catch (_e) {
        return '';
    }
}

// Browse button — opens a native folder picker on the server host and
// drops the chosen absolute path into the dialog's input so the existing
// live-validation pipeline (`_onBackupDbInputChanged`) classifies it.
async function _browseBackupDbDirectory() { // eslint-disable-line no-unused-vars
    const browseBtn = document.getElementById('backup-db-browse-btn');
    if (!backupDbTargetDirInput) return;
    if (browseBtn) browseBtn.disabled = true;
    try {
        const response = await fetch('/agent/pick_backup_directory/', {
            method: 'GET',
            credentials: 'same-origin'
        });
        let body = null;
        try { body = await response.json(); } catch (_e) { /* non-JSON */ }
        if (!response.ok) {
            _notifyPickerUnavailable(body, 'HTTP ' + response.status, backupDbTargetDirInput, 'folder');
            return;
        }
        if (body && (body.error || body.picker_unavailable)) {
            _notifyPickerUnavailable(body, body.error, backupDbTargetDirInput, 'folder');
            return;
        }
        const chosen = (body && typeof body.path === 'string') ? body.path : '';
        if (!chosen) {
            // User canceled the dialog — leave the input untouched.
            return;
        }
        backupDbTargetDirInput.value = chosen;
        backupDbTargetDirInput.dispatchEvent(new Event('input', { bubbles: true }));
        backupDbTargetDirInput.focus();
    } catch (err) {
        console.error('Browse for backup directory failed:', err);
        alert('Could not open the folder picker: ' + (err.message || 'network error'));
    } finally {
        if (browseBtn) browseBtn.disabled = false;
    }
}

function OpenBackupDbDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Backup DB dialog can't be opened during a long operation...");
        return;
    }

    if (backupDbTargetDirInput) {
        backupDbTargetDirInput.value = '';
        backupDbTargetDirInput.classList.remove('config-form-invalid');
        if (!_backupDbInputListenerAttached) {
            backupDbTargetDirInput.addEventListener('input', _onBackupDbInputChanged);
            _backupDbInputListenerAttached = true;
        }
    }
    _setBackupDbStatus('', '');

    preRenderBackupDbDialog(
        'Backup database...',
        'Specify the target directory where db.sqlite3 will be backed up.',
        'Provide ONLY the directory — Tlamatini will save the file as "db.sqlite3" so it can be loaded back correctly later.'
    );
    renderBackupDbDialog();
}

async function _saveBackupDb() { // eslint-disable-line no-unused-vars
    const raw = (backupDbTargetDirInput ? backupDbTargetDirInput.value : '').trim();

    if (!raw) {
        backupDbTargetDirInput.classList.add('config-form-invalid');
        _setBackupDbStatus('The target directory must not be empty.', 'error');
        alert('The target directory must not be empty.\n\nPlease specify an existing directory before clicking "Backup".');
        return false;
    }

    let info;
    try {
        info = await _checkBackupDbDirectory(raw);
    } catch (err) {
        console.error('Failed to validate backup directory:', err);
        alert('Could not validate the target directory: ' + (err.message || 'unknown error'));
        return false;
    }

    if (info.kind === 'file') {
        backupDbTargetDirInput.classList.add('config-form-invalid');
        _setBackupDbStatus('A filename was specified — please specify the directory only.', 'warn');
        alert('It is NOT recommended to change the file name.\n\nIf you rename db.sqlite3 the system will not be able to load it back correctly. Please specify only the target directory — Tlamatini will save the file as "db.sqlite3".');
        return false;
    }

    if (info.kind !== 'directory') {
        backupDbTargetDirInput.classList.add('config-form-invalid');
        _setBackupDbStatus('Directory does not exist.', 'error');
        alert('The target directory does not exist:\n\n' + raw + '\n\nPlease specify an existing directory before clicking "Backup".');
        return false;
    }

    let response;
    try {
        response = await fetch('/agent/backup_db/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ target_dir: raw })
        });
    } catch (err) {
        console.error('Backup request failed:', err);
        alert('Backup failed: ' + (err.message || 'network error'));
        return false;
    }

    let body = null;
    try {
        body = await response.json();
    } catch (_e) {
        // Non-JSON body; body stays null.
    }

    if (!response.ok || !body || body.success !== true) {
        const reason = (body && (body.error || body.reason)) || ('HTTP ' + response.status);
        if (body && body.kind === 'file') {
            backupDbTargetDirInput.classList.add('config-form-invalid');
            alert('It is NOT recommended to change the file name.\n\nIf you rename db.sqlite3 the system will not be able to load it back correctly. Please specify only the target directory — Tlamatini will save the file as "db.sqlite3".');
        } else {
            alert('Backup failed: ' + reason);
        }
        return false;
    }

    console.log('--- Backup completed at:', body.path);
    alert('Database backed up successfully to:\n\n' + body.path);
    return true;
}

// ----------------------------------------------------------------
// DB -> Set DB dialog
// ----------------------------------------------------------------

let _setDbValidationTimer = null;
let _setDbInputListenerAttached = false;

function _setSetDbStatus(text, kind) {
    if (!setDbStatusElement) return;
    setDbStatusElement.innerText = text || '';
    setDbStatusElement.classList.remove('set-db-status-ok', 'set-db-status-warn', 'set-db-status-error');
    if (kind === 'ok') {
        setDbStatusElement.classList.add('set-db-status-ok');
    } else if (kind === 'warn') {
        setDbStatusElement.classList.add('set-db-status-warn');
    } else if (kind === 'error') {
        setDbStatusElement.classList.add('set-db-status-error');
    }
}

async function _checkSetDbFile(rawPath) {
    const url = '/agent/check_set_db_file/?path=' + encodeURIComponent(rawPath);
    const response = await fetch(url, {
        method: 'GET',
        credentials: 'same-origin'
    });
    let body = null;
    try {
        body = await response.json();
    } catch (_e) {
        // Non-JSON; fall through.
    }
    if (!response.ok) {
        const err = new Error(`Validation failed: HTTP ${response.status}`);
        err.body = body;
        throw err;
    }
    return body || {};
}

function _renderSetDbValidationFeedback(info) {
    if (info.kind === 'file') {
        if (info.sqlite === false) {
            _setSetDbStatus('The selected file does not look like a SQLite database.', 'error');
            setDbSourcePathInput.classList.add('config-form-invalid');
            return;
        }
        if (info.basename_ok === false) {
            _setSetDbStatus('File found, but its name is not "db.sqlite3". Tlamatini will still stage it as db.sqlite3.', 'warn');
            setDbSourcePathInput.classList.remove('config-form-invalid');
            return;
        }
        _setSetDbStatus('File exists. It will be loaded on the next start-up.', 'ok');
        setDbSourcePathInput.classList.remove('config-form-invalid');
    } else if (info.kind === 'directory') {
        _setSetDbStatus('Specify the full path to a db.sqlite3 file, not a directory.', 'warn');
        setDbSourcePathInput.classList.add('config-form-invalid');
    } else {
        _setSetDbStatus('File does not exist.', 'error');
        setDbSourcePathInput.classList.add('config-form-invalid');
    }
}

function _onSetDbInputChanged() {
    if (!setDbSourcePathInput) return;
    const raw = (setDbSourcePathInput.value || '').trim();
    if (_setDbValidationTimer) {
        clearTimeout(_setDbValidationTimer);
        _setDbValidationTimer = null;
    }
    setDbSourcePathInput.classList.remove('config-form-invalid');
    if (!raw) {
        _setSetDbStatus('', '');
        return;
    }
    _setSetDbStatus('Checking path...', '');
    _setDbValidationTimer = setTimeout(() => {
        _checkSetDbFile(raw)
            .then(info => {
                const currentRaw = (setDbSourcePathInput.value || '').trim();
                if (currentRaw !== raw) {
                    return; // newer keystroke will trigger its own check
                }
                _renderSetDbValidationFeedback(info);
            })
            .catch(err => {
                console.error('Failed to validate db file path:', err);
                _setSetDbStatus('Could not validate the file path.', 'error');
            });
    }, 350);
}

// Browse button — opens a native file picker on the server host
// restricted to files named ``db.sqlite3`` and drops the chosen
// absolute path into the dialog's input so the existing live-validation
// pipeline (`_onSetDbInputChanged`) classifies it (SQLite-header check,
// basename match, etc.).
async function _browseSetDbFile() { // eslint-disable-line no-unused-vars
    const browseBtn = document.getElementById('set-db-browse-btn');
    if (!setDbSourcePathInput) return;
    if (browseBtn) browseBtn.disabled = true;
    try {
        const response = await fetch('/agent/pick_db_sqlite_file/', {
            method: 'GET',
            credentials: 'same-origin'
        });
        let body = null;
        try { body = await response.json(); } catch (_e) { /* non-JSON */ }
        if (!response.ok) {
            _notifyPickerUnavailable(body, 'HTTP ' + response.status, setDbSourcePathInput, 'file');
            return;
        }
        if (body && (body.error || body.picker_unavailable)) {
            _notifyPickerUnavailable(body, body.error, setDbSourcePathInput, 'file');
            return;
        }
        const chosen = (body && typeof body.path === 'string') ? body.path : '';
        if (!chosen) {
            // User canceled the dialog — leave the input untouched.
            return;
        }
        setDbSourcePathInput.value = chosen;
        setDbSourcePathInput.dispatchEvent(new Event('input', { bubbles: true }));
        setDbSourcePathInput.focus();
    } catch (err) {
        console.error('Browse for db.sqlite3 file failed:', err);
        alert('Could not open the file picker: ' + (err.message || 'network error'));
    } finally {
        if (browseBtn) browseBtn.disabled = false;
    }
}

function OpenSetDbDialog(e) { // eslint-disable-line no-unused-vars
    e.preventDefault();
    if (inLongOperation === true) {
        console.log("Set DB dialog can't be opened during a long operation...");
        return;
    }

    if (setDbSourcePathInput) {
        setDbSourcePathInput.value = '';
        setDbSourcePathInput.classList.remove('config-form-invalid');
        if (!_setDbInputListenerAttached) {
            setDbSourcePathInput.addEventListener('input', _onSetDbInputChanged);
            _setDbInputListenerAttached = true;
        }
    }
    _setSetDbStatus('', '');

    preRenderSetDbDialog(
        'Set database...',
        'Specify the full path to a db.sqlite3 file to load on the next start-up.',
        'Tlamatini will stage the file under DB/ToLoad/ and swap it in BEFORE Django opens its database on the next launch. The current db.sqlite3 is moved into DB/Older/<timestamp>/ so it can be recovered later.'
    );
    renderSetDbDialog();
}

function _showSetDbLoadedNextSessionWarning() {
    preRenderSetDbWarningDialog(
        'Database staged for next session',
        'The selected database will be loaded the next time Tlamatini starts.',
        'If you want it loaded immediately, you must restart Tlamatini completely so the swap-in can run BEFORE Django opens the live database.'
    );
    renderSetDbWarningDialog();
}

async function _saveSetDb() { // eslint-disable-line no-unused-vars
    const raw = (setDbSourcePathInput ? setDbSourcePathInput.value : '').trim();

    if (!raw) {
        setDbSourcePathInput.classList.add('config-form-invalid');
        _setSetDbStatus('The file path must not be empty.', 'error');
        alert('The file path must not be empty.\n\nPlease specify an existing db.sqlite3 file before clicking "Set".');
        return false;
    }

    let info;
    try {
        info = await _checkSetDbFile(raw);
    } catch (err) {
        console.error('Failed to validate db file path:', err);
        alert('Could not validate the file path: ' + (err.message || 'unknown error'));
        return false;
    }

    if (info.kind === 'directory') {
        setDbSourcePathInput.classList.add('config-form-invalid');
        _setSetDbStatus('Specify the full path to a db.sqlite3 file, not a directory.', 'warn');
        alert('The path points to a directory.\n\nPlease specify the full path to a db.sqlite3 file (e.g. C:\\Backups\\Tlamatini\\db.sqlite3).');
        return false;
    }

    if (info.kind !== 'file') {
        setDbSourcePathInput.classList.add('config-form-invalid');
        _setSetDbStatus('File does not exist.', 'error');
        alert('The file does not exist:\n\n' + raw + '\n\nPlease specify an existing db.sqlite3 file before clicking "Set".');
        return false;
    }

    if (info.sqlite === false) {
        setDbSourcePathInput.classList.add('config-form-invalid');
        _setSetDbStatus('The selected file does not look like a SQLite database.', 'error');
        alert('The selected file does not look like a SQLite database.\n\nPlease specify a real db.sqlite3 file.');
        return false;
    }

    let response;
    try {
        response = await fetch('/agent/set_db/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken()
            },
            body: JSON.stringify({ source_path: raw })
        });
    } catch (err) {
        console.error('Set DB request failed:', err);
        alert('Set DB failed: ' + (err.message || 'network error'));
        return false;
    }

    let body = null;
    try {
        body = await response.json();
    } catch (_e) {
        // Non-JSON body; body stays null.
    }

    if (!response.ok || !body || body.success !== true) {
        const reason = (body && (body.error || body.reason)) || ('HTTP ' + response.status);
        alert('Set DB failed: ' + reason);
        return false;
    }

    console.log('--- Set DB staged at:', body.path);
    _showSetDbLoadedNextSessionWarning();
    return true;
}

