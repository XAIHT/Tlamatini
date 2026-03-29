// Agentic Control Panel - Control Panel Button Handlers (Start / Stop / Pause / Clear)
// LOAD ORDER: #6 - Depends on: acp-globals.js, acp-session.js, acp-running-state.js

/**
 * Execute the actual start sequence (the original Start button logic).
 * This is called either directly (validation VALID) or after user confirms in dialog.
 */
async function executeStartSequence() {
    if (isBusyProcessing) {
        console.log('--- Already processing, ignoring click');
        return;
    }

    if (globalRunningState === GLOBAL_STATE.PAUSED) {
        console.log('--- System is PAUSED, triggering resume from Start button');
        await resumeFromPause();
        return;
    }

    isBusyProcessing = true;

    // Disable all control buttons during the start sequence
    if (btnStart)    btnStart.disabled = true;
    if (btnStop)     btnStop.disabled  = true;
    if (btnPause)    btnPause.disabled = true;
    if (btnClear)    btnClear.disabled = true;
    if (btnValidate) btnValidate.disabled = true;

    const starterAgents = document.querySelectorAll('#submonitor-container .canvas-item.starter-agent');

    if (starterAgents.length === 0) {
        console.log('--- No Starter agents found on canvas');
        alert('No Starter agents found on the canvas. Add a Starter agent and connect it to other agents to begin.');
        isBusyProcessing = false;
        updateControlButtonStates();
        return;
    }

    console.log(`--- Found ${starterAgents.length} Starter agent(s) to execute`);

    const starterInfo = Array.from(starterAgents).map(agent => ({
        id: agent.id,
        displayName: agent.textContent.trim() || agent.id
    }));

    // SHOW DIALOG IMMEDIATELY - user sees instant feedback
    const justBeforeStartingTimestamp = Date.now();
    showStarterExecutionDialog(starterInfo, justBeforeStartingTimestamp);

    // Step 1: Pre-Start Cleanup - Kill all running processes to release file locks
    console.log('--- [Start Sequence] 1. Killing session processes...');
    try {
        const killResponse = await fetch('/agent/kill_session_processes/', {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        });
        const killResult = await killResponse.json();
        console.log(`--- [Start Sequence] Killed ${killResult.killed_count} process(es)`);
    } catch (killError) {
        console.warn('--- [Start Sequence] Warning: Error killing processes (continuing anyway):', killError);
    }

    // Step 2: Ensure ALL canvas agents exist in pool
    console.log('--- [Start Sequence] 2. Ensuring all canvas agents exist in pool directory...');
    const allCanvasItems = document.querySelectorAll('#submonitor-container .canvas-item');
    const deployPromises = Array.from(allCanvasItems).map(async (item) => {
        try {
            const response = await fetch(`/agent/ensure_agent_exists/${item.id}/`, {
                method: 'POST', headers: getHeaders(), credentials: 'same-origin'
            });
            if (response.ok) {
                const result = await response.json();
                console.log(result.existed ? `--- Agent ${item.id} already exists` : `--- Deployed ${item.id}`);
                return { id: item.id, success: true };
            } else {
                console.warn(`--- Failed to ensure ${item.id}: ${response.status}`);
                return { id: item.id, success: false };
            }
        } catch (error) {
            console.error(`--- Error ensuring ${item.id}:`, error);
            return { id: item.id, success: false };
        }
    });
    await Promise.all(deployPromises);
    console.log('--- [Start Sequence] Agent existence check complete');

    // Step 3: Clear all agent log files before starting
    console.log('--- [Start Sequence] 3. Clearing all agent log files...');
    try {
        const clearResponse = await fetch('/agent/clear_agent_logs/', {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        });
        const clearResult = await clearResponse.json();
        if (clearResult.status === 'success') {
            console.log(`--- Cleared ${clearResult.cleared_count} log file(s)`);
        } else {
            console.warn('--- Warning: Could not clear log files:', clearResult.message);
        }
    } catch (clearError) {
        console.warn('--- Warning: Error clearing log files (continuing anyway):', clearError);
    }

    // Step 4: Execute ALL starter agents in parallel (fire and forget)
    console.log('--- [Start Sequence] 4. Executing Starter agents...');
    const executionPromises = starterInfo.map(async ({ id }) => {
        try {
            const response = await fetch(`/agent/execute_starter_agent/${id}/`, {
                method: 'POST', headers: getHeaders(), credentials: 'same-origin'
            });
            const result = await response.json();
            return { agentId: id, success: result.success, pid: result.pid, message: result.message };
        } catch (error) {
            return { agentId: id, success: false, message: error.message };
        }
    });

    // Don't await - fire and forget; polling will detect success
    Promise.all(executionPromises).then(results => {
        console.log('--- All execution requests sent:', results);
    });

    // Step 5: Start FlowHypervisor if present on canvas
    const flowHypervisor = document.querySelector('#submonitor-container .canvas-item.flowhypervisor-agent');
    if (flowHypervisor) {
        console.log('--- [Start Sequence] 5. Executing FlowHypervisor...');
        startSystemManagedFlowHypervisor(flowHypervisor.id);
    }

    // Note: Button re-enabling happens in showStarterResult() after polling completes
}

// ========================================
// START BUTTON (with validation check)
// ========================================
if (btnStart) {
    btnStart.addEventListener('click', async (e) => {
        e.preventDefault();
        console.log('--- Start button clicked');

        if (isBusyProcessing) {
            console.log('--- Already processing, ignoring click');
            return;
        }

        // Check validation status before proceeding
        if (flowValidationStatus === VALIDATION_STATE.VALID) {
            // Validated OK — proceed normally
            executeStartSequence();
        } else if (flowValidationStatus === VALIDATION_STATE.INVALID) {
            // Validation failed — show warning dialog
            showStartValidationCheckDialog(VALIDATION_STATE.INVALID, executeStartSequence);
        } else {
            // Not validated — show info dialog
            showStartValidationCheckDialog(VALIDATION_STATE.NOT_VALIDATED, executeStartSequence);
        }
    });
}

// ========================================
// STARTER DIALOG & POLLING
// ========================================

/**
 * Show the Starter Execution Dialog with spinner and poll for log file creation.
 * @param {Array<{id: string, displayName: string}>} starterInfo
 * @param {number} justBeforeStartingTimestamp - Timestamp in ms before agents were started
 */
function showStarterExecutionDialog(starterInfo, justBeforeStartingTimestamp) {
    const dialog = $("#starter-execution-dialog");
    const titleEl = document.getElementById('starter-execution-title');
    const spinnerContainer = document.getElementById('starter-execution-spinner-container');
    const resultContainer = document.getElementById('starter-execution-result');
    const iconEl = document.getElementById('starter-execution-icon');
    const messageEl = document.getElementById('starter-execution-message');
    const failedListEl = document.getElementById('starter-execution-failed-list');

    titleEl.innerText = "The Tlamatini is awakening the Starter agents, wait a moment...";
    spinnerContainer.style.display = 'flex';
    resultContainer.style.display = 'none';
    failedListEl.innerHTML = '';
    iconEl.className = '';
    messageEl.className = '';

    dialog.dialog({
        title: "Starting agents...",
        autoOpen: true,
        modal: true,
        width: 500,
        resizable: false,
        draggable: false,
        closeOnEscape: false,
        closeText: "",
        dialogClass: "starter-execution-dialog-wrapper",
        open: function () {
            document.body.style.overflow = 'hidden';
            $(this).parent().find('.ui-dialog-titlebar-close').hide();
            $('.ui-widget-overlay').addClass('starter-execution-overlay');
        },
        close: function () {
            document.body.style.overflow = '';
        },
        buttons: []
    });

    pollForLogFiles(starterInfo, justBeforeStartingTimestamp, dialog);
}

/**
 * Poll for starter agent log files until all are found or timeout.
 */
async function pollForLogFiles(starterInfo, justBeforeStartingTimestamp, dialog) {
    const POLL_INTERVAL = 1000;
    const MAX_POLL_TIME = 60000;
    const startTime = Date.now();
    const verifiedStarters = new Set();
    const failedStarters = [];

    const poll = async () => {
        const elapsed = Date.now() - startTime;
        console.log(`--- Polling for log files (elapsed: ${elapsed}ms)`);

        for (const { id, displayName } of starterInfo) { // eslint-disable-line no-unused-vars
            if (verifiedStarters.has(id)) continue;
            try {
                const response = await fetch(`/agent/check_starter_log/${id}/?timestamp=${justBeforeStartingTimestamp}`, {
                    method: 'GET', headers: getHeaders(), credentials: 'same-origin'
                });
                const result = await response.json();
                if (result.exists && result.modified_after_timestamp) {
                    console.log(`✅ Verified log for ${id}`);
                    verifiedStarters.add(id);
                }
            } catch (error) {
                console.warn(`Warning: Error checking log for ${id}:`, error);
            }
        }

        if (verifiedStarters.size === starterInfo.length) {
            console.log('--- All starter agents verified successfully!');
            showStarterResult(true, [], dialog);
            return;
        }

        if (elapsed >= MAX_POLL_TIME) {
            console.warn('--- Polling timeout reached');
            for (const { id, displayName } of starterInfo) {
                if (!verifiedStarters.has(id)) failedStarters.push(displayName);
            }
            showStarterResult(false, failedStarters, dialog);
            return;
        }

        setTimeout(poll, POLL_INTERVAL);
    };

    poll();
}

/**
 * Show the result in the starter dialog (success or failure).
 */
function showStarterResult(success, failedAgentNames, dialog) {
    const titleEl = document.getElementById('starter-execution-title');
    const spinnerContainer = document.getElementById('starter-execution-spinner-container');
    const resultContainer = document.getElementById('starter-execution-result');
    const iconEl = document.getElementById('starter-execution-icon');
    const messageEl = document.getElementById('starter-execution-message');
    const failedListEl = document.getElementById('starter-execution-failed-list');

    spinnerContainer.style.display = 'none';
    resultContainer.style.display = 'block';

    if (success) {
        titleEl.innerText = "Startup Complete";
        iconEl.innerHTML = '✅';
        iconEl.className = 'success';
        messageEl.innerText = 'All Starter agents have been successfully awakened!';
        messageEl.className = 'success';
        failedListEl.innerHTML = '';
        setGlobalRunningState(GLOBAL_STATE.RUNNING);
    } else {
        titleEl.innerText = "Startup Failed";
        iconEl.innerHTML = '❌';
        iconEl.className = 'error';
        messageEl.innerText = 'The following Starter agents could not be verified:';
        messageEl.className = 'error';
        failedListEl.innerHTML = '';
        for (const name of failedAgentNames) {
            const li = document.createElement('li');
            li.textContent = name;
            failedListEl.appendChild(li);
        }
    }

    isBusyProcessing = false;
    updateControlButtonStates();

    dialog.dialog("option", "buttons", [{
        text: "Continue!",
        click: function () { $(this).dialog("close"); }
    }]);

    const buttonPane = dialog.parent().find('.ui-dialog-buttonpane');
    buttonPane.find('button:contains("Continue")').css({
        'background-color': success ? '#10B981' : '#e74c3c',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '120px'
    });
}

// ========================================
// STOP BUTTON
// ========================================
if (btnStop) {
    btnStop.addEventListener('click', async (e) => {
        e.preventDefault();
        console.log('--- Stop button clicked');

        if (isBusyProcessing) {
            console.log('--- Already processing, ignoring click');
            return;
        }
        isBusyProcessing = true;

        // Disable all control buttons during the stop sequence
        if (btnStart)    btnStart.disabled = true;
        if (btnStop)     btnStop.disabled  = true;
        if (btnPause)    btnPause.disabled = true;
        if (btnClear)    btnClear.disabled = true;
        if (btnValidate) btnValidate.disabled = true;

        const enderAgents = document.querySelectorAll('#submonitor-container .canvas-item.ender-agent');

        if (enderAgents.length === 0) {
            console.log('--- No Ender agents found on canvas');
            alert('No Ender agents found on the canvas. Add an Ender agent and connect it to other agents to enable stop functionality.');
            isBusyProcessing = false;
            updateControlButtonStates();
            return;
        }

        console.log(`--- Found ${enderAgents.length} Ender agent(s) to execute`);

        const enderInfo = Array.from(enderAgents).map(agent => ({
            id: agent.id,
            displayName: agent.textContent.trim() || agent.id
        }));
        console.log('--- Ender info collected:', enderInfo);

        const justBeforeEndingTimestamp = Date.now();
        showEnderExecutionDialog(enderInfo, justBeforeEndingTimestamp);

        // Pre-check if all target agents are already down
        let allAgentsAlreadyDown = true;
        let totalAgentsChecked = 0;

        for (const { id } of enderInfo) {
            try {
                const response = await fetch(`/agent/check_agents_running/${id}/`, {
                    method: 'GET', headers: getHeaders(), credentials: 'same-origin'
                });
                const result = await response.json();
                console.log(`--- Agent status check for ${id}:`, result);
                if (!result.all_down) allAgentsAlreadyDown = false;
                totalAgentsChecked += result.total_count || 0;
            } catch (error) {
                console.warn(`--- Error checking agent status for ${id}:`, error);
                allAgentsAlreadyDown = false;
            }
        }

        if (allAgentsAlreadyDown && totalAgentsChecked > 0) {
            console.log('--- All target agents are already down, updating dialog');
            $("#ender-execution-dialog").dialog("close");
            setTimeout(() => { showEnderAlreadyDownDialog(enderInfo); }, 100);
            return;
        }

        // Execute ALL ender agents in parallel (fire and forget)
        const executionPromises = enderInfo.map(async ({ id }) => {
            try {
                const response = await fetch(`/agent/execute_ender_agent/${id}/`, {
                    method: 'POST', headers: getHeaders(), credentials: 'same-origin'
                });
                const result = await response.json();
                return { agentId: id, success: result.success, pid: result.pid, message: result.message };
            } catch (error) {
                return { agentId: id, success: false, message: error.message };
            }
        });

        Promise.all(executionPromises).then(results => {
            console.log('--- All ender execution requests sent:', results);
        });
    });
}

// ========================================
// ENDER DIALOG & POLLING
// ========================================

/**
 * Show the Ender Execution Dialog with spinner and poll for log file creation.
 */
function showEnderExecutionDialog(enderInfo, justBeforeEndingTimestamp) {
    const dialog = $("#ender-execution-dialog");
    const titleEl = document.getElementById('ender-execution-title');
    const spinnerContainer = document.getElementById('ender-execution-spinner-container');
    const resultContainer = document.getElementById('ender-execution-result');
    const iconEl = document.getElementById('ender-execution-icon');
    const messageEl = document.getElementById('ender-execution-message');
    const failedListEl = document.getElementById('ender-execution-failed-list');

    titleEl.innerText = "The Tlamatini is awakening the Ender agents, wait a moment...";
    spinnerContainer.style.display = 'flex';
    resultContainer.style.display = 'none';
    failedListEl.innerHTML = '';
    iconEl.className = '';
    messageEl.className = '';

    dialog.dialog({
        title: "Ending agents...",
        autoOpen: true,
        modal: true,
        width: 500,
        resizable: false,
        draggable: false,
        closeOnEscape: false,
        closeText: "",
        dialogClass: "ender-execution-dialog-wrapper",
        open: function () {
            document.body.style.overflow = 'hidden';
            $(this).parent().find('.ui-dialog-titlebar-close').hide();
            $('.ui-widget-overlay').addClass('ender-execution-overlay');
        },
        close: function () {
            document.body.style.overflow = '';
        },
        buttons: []
    });

    pollForEnderLogFiles(enderInfo, justBeforeEndingTimestamp, dialog);
}

/**
 * Poll for ender agent log files until all are found or timeout.
 */
async function pollForEnderLogFiles(enderInfo, justBeforeEndingTimestamp, dialog) {
    const POLL_INTERVAL = 1000;
    const MAX_POLL_TIME = 60000;
    const startTime = Date.now();
    const verifiedEnders = new Set();
    const failedEnders = [];

    const poll = async () => {
        const elapsed = Date.now() - startTime;
        console.log(`--- Polling for ender log files (elapsed: ${elapsed}ms)`);

        for (const { id, displayName } of enderInfo) { // eslint-disable-line no-unused-vars
            if (verifiedEnders.has(id)) continue;
            try {
                const url = `/agent/check_ender_log/${id}/?timestamp=${justBeforeEndingTimestamp}`;
                console.log(`--- Fetching: ${url}`);
                const response = await fetch(url, { method: 'GET', headers: getHeaders(), credentials: 'same-origin' });
                const result = await response.json();
                console.log(`--- Response for ${id}:`, result);
                if (result.exists && result.modified_after_timestamp) {
                    console.log(`✅ Verified log for ${id}`);
                    verifiedEnders.add(id);
                } else {
                    console.log(`❌ Not verified yet for ${id}: exists=${result.exists}, modified_after=${result.modified_after_timestamp}`);
                }
            } catch (error) {
                console.warn(`Warning: Error checking log for ${id}:`, error);
            }
        }

        if (verifiedEnders.size === enderInfo.length) {
            console.log('--- All ender agents verified successfully!');
            showEnderResult(true, [], dialog);
            return;
        }

        if (elapsed >= MAX_POLL_TIME) {
            console.warn('--- Polling timeout reached for enders');
            for (const { id, displayName } of enderInfo) {
                if (!verifiedEnders.has(id)) failedEnders.push(displayName);
            }
            showEnderResult(false, failedEnders, dialog);
            return;
        }

        setTimeout(poll, POLL_INTERVAL);
    };

    poll();
}

/**
 * Collect all "shutdown chain" agents downstream from Ender output connections.
 * Traverses the canvas connection graph:
 *   Ender --output--> FlowBacker / Cleaner
 *   FlowBacker --output--> Cleaner
 *
 * @returns {Array<string>} Canvas IDs of all agents in the shutdown chain
 */
function collectEnderOutputChainAgents() {
    const enderNodes = document.querySelectorAll('#submonitor-container .canvas-item.ender-agent');
    const chainIds = new Set();
    const flowBackerNodes = [];

    // Step 1: Direct outputs from Enders (FlowBackers and/or Cleaners)
    for (const enderNode of enderNodes) {
        for (const conn of ACP.connections) {
            if (conn.source === enderNode) {
                chainIds.add(conn.target.id);
                const targetAgentName = (conn.target.dataset.agentName || '').toLowerCase();
                if (targetAgentName === 'flowbacker') {
                    flowBackerNodes.push(conn.target);
                }
            }
        }
    }

    // Step 2: Outputs from FlowBackers (typically Cleaners)
    for (const fbNode of flowBackerNodes) {
        for (const conn of ACP.connections) {
            if (conn.source === fbNode) {
                chainIds.add(conn.target.id);
            }
        }
    }

    return Array.from(chainIds);
}

/**
 * Finalize the stop sequence: transition to STOPPED, clean up, and show dialog result.
 * @param {Object} dialog - jQuery dialog reference
 */
function finalizeStopSequence(dialog) {
    const titleEl = document.getElementById('ender-execution-title');
    const spinnerContainer = document.getElementById('ender-execution-spinner-container');
    const resultContainer = document.getElementById('ender-execution-result');
    const iconEl = document.getElementById('ender-execution-icon');
    const messageEl = document.getElementById('ender-execution-message');
    const failedListEl = document.getElementById('ender-execution-failed-list');

    spinnerContainer.style.display = 'none';
    resultContainer.style.display = 'block';

    titleEl.innerText = "Termination Complete";
    iconEl.innerHTML = '✅';
    iconEl.className = 'success';
    messageEl.innerText = 'All agents (including output chain) have completed!';
    messageEl.className = 'success';
    failedListEl.innerHTML = '';

    setGlobalRunningState(GLOBAL_STATE.STOPPED);
    stopSystemManagedFlowHypervisor();

    // Clear .pos (reanimation position) files
    try {
        fetch('/agent/clear_pos_files/', {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        }).then(response => response.json())
            .then(result => {
                if (result.success) {
                    console.log(`--- Cleared ${result.cleared_count} .pos file(s)`);
                } else {
                    console.warn('--- Warning: Could not clear .pos files:', result.message);
                }
            }).catch(err => {
                console.warn('--- Warning: Error clearing .pos files:', err);
            });
    } catch (clearPosError) {
        console.warn('--- Warning: Error initiating .pos file cleanup:', clearPosError);
    }

    isBusyProcessing = false;
    updateControlButtonStates();

    dialog.dialog("option", "buttons", [{
        text: "Continue!",
        click: function () { $(this).dialog("close"); }
    }]);

    const buttonPane = dialog.parent().find('.ui-dialog-buttonpane');
    buttonPane.find('button:contains("Continue")').css({
        'background-color': '#8B5CF6',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '120px'
    });
}

/**
 * Poll until all output chain agents (FlowBackers, Cleaners) have finished.
 * Also waits for the Ender agents themselves to finish first (they launch the
 * output agents before exiting).
 *
 * Uses a confirmation re-check: after all agents appear stopped, waits 2 s and
 * checks once more to guard against the brief window between a FlowBacker
 * exiting and its downstream Cleaner's PID file appearing.
 *
 * @param {Array<string>} chainAgentIds - Canvas IDs of output chain agents
 * @param {Array<string>} enderIds - Canvas IDs of the Ender agents
 * @param {Object} dialog - jQuery dialog reference
 */
function pollForOutputChainCompletion(chainAgentIds, enderIds, dialog) {
    const POLL_INTERVAL = 1500;
    const MAX_POLL_TIME = 300000; // 5 minutes
    const CONFIRM_DELAY = 2000;   // re-check after 2 s of "all stopped"
    const startTime = Date.now();
    const allWatchIds = [...new Set([...enderIds, ...chainAgentIds])];
    let confirmPending = false;

    const titleEl = document.getElementById('ender-execution-title');

    const poll = async () => {
        const elapsed = Date.now() - startTime;

        try {
            const response = await fetch('/agent/check_all_agents_status/', {
                method: 'GET', headers: getHeaders(), credentials: 'same-origin'
            });
            const result = await response.json();
            const runningAgents = result.agents || {};

            const stillRunning = allWatchIds.filter(id => runningAgents[id] === true);

            if (stillRunning.length === 0) {
                if (!confirmPending) {
                    // First time all appear stopped — schedule confirmation re-check
                    confirmPending = true;
                    console.log('--- Output chain: all agents appear stopped, confirming in 2 s...');
                    titleEl.innerText = "Confirming all output agents have stopped...";
                    setTimeout(poll, CONFIRM_DELAY);
                    return;
                }
                // Confirmation passed — truly done
                console.log('--- Output chain: confirmed all agents stopped');
                finalizeStopSequence(dialog);
                return;
            }

            // Still running — reset confirmation flag
            confirmPending = false;
            const names = stillRunning.join(', ');
            console.log(`--- Output chain: ${stillRunning.length} agent(s) still running [${names}] (elapsed: ${elapsed}ms)`);
            titleEl.innerText = `Waiting for output agents: ${names}...`;
        } catch (error) {
            console.warn('--- Error polling output chain status:', error);
        }

        if (elapsed >= MAX_POLL_TIME) {
            console.warn('--- Output chain polling timeout (5 min), finalizing anyway');
            finalizeStopSequence(dialog);
            return;
        }

        setTimeout(poll, POLL_INTERVAL);
    };

    poll();
}

/**
 * Show the result in the ender dialog (success or failure).
 */
function showEnderResult(success, failedAgentNames, dialog) {
    const titleEl = document.getElementById('ender-execution-title');
    const spinnerContainer = document.getElementById('ender-execution-spinner-container');
    const resultContainer = document.getElementById('ender-execution-result');
    const iconEl = document.getElementById('ender-execution-icon');
    const messageEl = document.getElementById('ender-execution-message');
    const failedListEl = document.getElementById('ender-execution-failed-list');

    if (success) {
        // Collect output chain agents BEFORE deciding whether to finalize
        const chainAgentIds = collectEnderOutputChainAgents();
        const enderNodes = document.querySelectorAll('#submonitor-container .canvas-item.ender-agent');
        const enderIds = Array.from(enderNodes).map(n => n.id);

        if (chainAgentIds.length > 0) {
            // Output chain exists — keep spinner, enter output-chain polling phase
            console.log(`--- Enders verified. Waiting for output chain: ${chainAgentIds.join(', ')}`);
            titleEl.innerText = "Enders done. Waiting for output agents to complete...";
            // Spinner stays visible; result stays hidden — user sees continued progress
            pollForOutputChainCompletion(chainAgentIds, enderIds, dialog);
            return; // Do NOT finalize yet
        }

        // No output chain — finalize immediately (original behavior)
        spinnerContainer.style.display = 'none';
        resultContainer.style.display = 'block';

        titleEl.innerText = "Termination Complete";
        iconEl.innerHTML = '✅';
        iconEl.className = 'success';
        messageEl.innerText = 'All Ender agents have been successfully executed!';
        messageEl.className = 'success';
        failedListEl.innerHTML = '';

        setGlobalRunningState(GLOBAL_STATE.STOPPED);
        stopSystemManagedFlowHypervisor();

        // Clear .pos (reanimation position) files
        try {
            fetch('/agent/clear_pos_files/', {
                method: 'POST', headers: getHeaders(), credentials: 'same-origin'
            }).then(response => response.json())
                .then(result => {
                    if (result.success) {
                        console.log(`--- Cleared ${result.cleared_count} .pos file(s)`);
                    } else {
                        console.warn('--- Warning: Could not clear .pos files:', result.message);
                    }
                }).catch(err => {
                    console.warn('--- Warning: Error clearing .pos files:', err);
                });
        } catch (clearPosError) {
            console.warn('--- Warning: Error initiating .pos file cleanup:', clearPosError);
        }
    } else {
        spinnerContainer.style.display = 'none';
        resultContainer.style.display = 'block';

        titleEl.innerText = "Termination Failed";
        iconEl.innerHTML = '❌';
        iconEl.className = 'error';
        messageEl.innerText = 'The following Ender agents could not be verified:';
        messageEl.className = 'error';
        failedListEl.innerHTML = '';
        for (const name of failedAgentNames) {
            const li = document.createElement('li');
            li.textContent = name;
            failedListEl.appendChild(li);
        }
    }

    isBusyProcessing = false;
    updateControlButtonStates();

    dialog.dialog("option", "buttons", [{
        text: "Continue!",
        click: function () { $(this).dialog("close"); }
    }]);

    const buttonPane = dialog.parent().find('.ui-dialog-buttonpane');
    buttonPane.find('button:contains("Continue")').css({
        'background-color': success ? '#8B5CF6' : '#e74c3c',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '120px'
    });
}

/**
 * Show info dialog when all agents are already down.
 */
function showEnderAlreadyDownDialog(_enderInfo) {
    const dialog = $("#ender-execution-dialog");
    const titleEl = document.getElementById('ender-execution-title');
    const spinnerContainer = document.getElementById('ender-execution-spinner-container');
    const resultContainer = document.getElementById('ender-execution-result');
    const iconEl = document.getElementById('ender-execution-icon');
    const messageEl = document.getElementById('ender-execution-message');
    const failedListEl = document.getElementById('ender-execution-failed-list');

    isBusyProcessing = false;

    spinnerContainer.style.display = 'none';
    resultContainer.style.display = 'block';
    failedListEl.innerHTML = '';

    titleEl.innerText = "All Agents Already Down";
    iconEl.innerHTML = 'ℹ️';
    iconEl.className = 'info';
    messageEl.innerText = 'All target agents are already stopped. No termination was needed.';
    messageEl.className = 'info';

    setGlobalRunningState(GLOBAL_STATE.STOPPED);
    stopSystemManagedFlowHypervisor();

    // Clear .pos files
    try {
        fetch('/agent/clear_pos_files/', {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        }).then(response => response.json())
            .then(result => {
                if (result.success) {
                    console.log(`--- Cleared ${result.cleared_count} .pos file(s)`);
                } else {
                    console.warn('--- Warning: Could not clear .pos files:', result.message);
                }
            }).catch(err => {
                console.warn('--- Warning: Error clearing .pos files:', err);
            });
    } catch (clearPosError) {
        console.warn('--- Warning: Error initiating .pos file cleanup:', clearPosError);
    }

    dialog.dialog({
        title: "Stop Complete",
        autoOpen: true,
        modal: true,
        width: 500,
        resizable: false,
        draggable: false,
        closeOnEscape: true,
        closeText: "",
        dialogClass: "ender-execution-dialog-wrapper",
        open: function () {
            document.body.style.overflow = 'hidden';
            $(this).parent().find('.ui-dialog-titlebar-close').hide();
        },
        close: function () {
            document.body.style.overflow = '';
        },
        buttons: [{
            text: "Continue!",
            click: function () { $(this).dialog("close"); }
        }]
    });

    const buttonPane = dialog.parent().find('.ui-dialog-buttonpane');
    buttonPane.find('button:contains("Continue")').css({
        'background-color': '#3B82F6',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '120px'
    });
}

// ========================================
// PAUSE BUTTON
// ========================================
if (btnPause) {
    btnPause.addEventListener('click', async (e) => {
        e.preventDefault();
        console.log('--- Pause button clicked');

        if (isBusyProcessing) {
            console.log('--- Already processing, ignoring Pause click');
            return;
        }

        if (globalRunningState === GLOBAL_STATE.PAUSED) {
            console.log('--- Resuming from PAUSED state');
            await resumeFromPause();
        } else if (globalRunningState === GLOBAL_STATE.RUNNING) {
            console.log('--- Pausing from RUNNING state');
            await pauseExecution();
        } else {
            console.log('--- Cannot pause when system is STOPPED');
            alert('The system is not running. Start the flow before attempting to pause.');
        }
    });
}

/**
 * Pause execution: get running processes, save to paused_agents.reanim on server,
 * kill them (preserving logs and reanim state files), update UI with red LEDs.
 */
async function pauseExecution() {
    isBusyProcessing = true;

    // Disable all control buttons during the pause operation
    if (btnStart)    btnStart.disabled = true;
    if (btnStop)     btnStop.disabled  = true;
    if (btnPause)    btnPause.disabled = true;
    if (btnClear)    btnClear.disabled = true;
    if (btnValidate) btnValidate.disabled = true;

    try {
        // Step 1: Get currently running processes
        console.log('--- [Pause] Fetching running processes...');
        const getProcessesResponse = await fetch('/agent/get_session_running_processes/', {
            method: 'GET', headers: getHeaders(), credentials: 'same-origin'
        });
        const processesResult = await getProcessesResponse.json();

        if (!processesResult.success) {
            console.error('--- Failed to get running processes:', processesResult.error);
            alert('Failed to get running processes: ' + (processesResult.error || 'Unknown error'));
            resetPauseButtons();
            return;
        }

        const runningProcesses = processesResult.processes || [];
        console.log(`--- [Pause] Found ${runningProcesses.length} running process(es)`);

        if (runningProcesses.length === 0) {
            console.log('--- [Pause] No running processes to pause');
            alert('No running processes found to pause.');
            resetPauseButtons();
            return;
        }

        // Step 2: Save paused agents list to paused_agents.reanim file on server
        console.log('--- [Pause] Saving paused agents to paused_agents.reanim...');
        const saveResponse = await fetch('/agent/save_paused_agents/', {
            method: 'POST',
            headers: { ...getHeaders(), 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ agents: runningProcesses })
        });
        const saveResult = await saveResponse.json();
        if (saveResult.success) {
            console.log(`--- [Pause] Saved ${saveResult.saved_count} agent(s) to paused_agents.reanim`);
        } else {
            console.warn('--- [Pause] Warning: Could not save paused agents file:', saveResult.message);
        }

        // Step 3: Store in JS memory for LED display
        pausedProcessesOnPause[SESSION_ID] = runningProcesses;
        console.log(`--- [Pause] Stored ${runningProcesses.length} process(es) in pausedProcessesOnPause[${SESSION_ID}]`);

        // Step 4: Kill all session processes (do NOT erase logs or reanim files)
        console.log('--- [Pause] Killing all session processes...');
        const killResponse = await fetch('/agent/kill_session_processes/', {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        });
        const killResult = await killResponse.json();

        if (killResult.success) {
            console.log(`--- [Pause] Killed ${killResult.killed_count} process(es)`);
        } else {
            console.warn('--- [Pause] Kill operation reported issues:', killResult.message);
        }

        // Step 5: Set PAUSED state (all LEDs go yellow blinking)
        setGlobalRunningState(GLOBAL_STATE.PAUSED);

    } catch (error) {
        console.error('--- Error during pause:', error);
        alert('Error during pause operation: ' + error.message);
    } finally {
        resetPauseButtons();
    }
}

/**
 * Resume from pause: load agents from paused_agents.reanim on server,
 * reanimate them (with AGENT_REANIMATED=1 env var so they preserve logs
 * and load reanim state files), then delete paused_agents.reanim.
 */
async function resumeFromPause() {
    isBusyProcessing = true;

    // Disable all control buttons during the resume operation
    if (btnStart)    btnStart.disabled = true;
    if (btnStop)     btnStop.disabled  = true;
    if (btnPause)    btnPause.disabled = true;
    if (btnClear)    btnClear.disabled = true;
    if (btnValidate) btnValidate.disabled = true;

    try {
        // Step 1: Load paused agents list from paused_agents.reanim on server
        console.log('--- [Resume] Loading paused agents from paused_agents.reanim...');
        const loadResponse = await fetch('/agent/load_paused_agents/', {
            method: 'GET', headers: getHeaders(), credentials: 'same-origin'
        });
        const loadResult = await loadResponse.json();

        let storedProcesses = [];
        if (loadResult.success && loadResult.agents && loadResult.agents.length > 0) {
            storedProcesses = loadResult.agents;
            console.log(`--- [Resume] Loaded ${storedProcesses.length} agent(s) from server file`);
        } else {
            // Fallback to JS memory if server file is missing
            storedProcesses = pausedProcessesOnPause[SESSION_ID] || [];
            console.log(`--- [Resume] Fallback to JS memory: ${storedProcesses.length} agent(s)`);
        }

        if (storedProcesses.length === 0) {
            console.log('--- [Resume] No stored processes to resume');
            setGlobalRunningState(GLOBAL_STATE.STOPPED);
            resetPauseButtons();
            return;
        }

        // Step 2: Build unique agents list for reanimation
        const agentsToReanimate = storedProcesses.map(proc => ({
            canvas_id: proc.canvas_id,
            folder_name: proc.folder_name,
            script_name: proc.script_name
        }));

        const uniqueAgents = [];
        const seenIds = new Set();
        for (const agent of agentsToReanimate) {
            if (!seenIds.has(agent.canvas_id)) {
                seenIds.add(agent.canvas_id);
                uniqueAgents.push(agent);
            }
        }
        console.log(`--- [Resume] Unique agents to reanimate: ${uniqueAgents.length}`);

        // Step 3: Reanimate agents (uses AGENT_REANIMATED=1 env var)
        const reanimateResponse = await fetch('/agent/reanimate_agents/', {
            method: 'POST',
            headers: { ...getHeaders(), 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ agents: uniqueAgents })
        });
        const reanimateResult = await reanimateResponse.json();

        if (reanimateResult.success) {
            console.log(`--- [Resume] Successfully reanimated ${reanimateResult.reanimated.length} agent(s)`);
        } else {
            console.warn('--- [Resume] Some agents failed to reanimate:', reanimateResult.failed);
            if (reanimateResult.failed.length > 0) {
                alert(`Warning: ${reanimateResult.failed.length} agent(s) failed to reanimate.`);
            }
        }

        // Step 4: Delete paused_agents.reanim file from server
        console.log('--- [Resume] Deleting paused_agents.reanim...');
        try {
            await fetch('/agent/delete_paused_agents/', {
                method: 'POST', headers: getHeaders(), credentials: 'same-origin'
            });
            console.log('--- [Resume] paused_agents.reanim deleted');
        } catch (delErr) {
            console.warn('--- [Resume] Warning: Could not delete paused_agents.reanim:', delErr);
        }

        // Step 5: Clear JS memory and transition to RUNNING
        delete pausedProcessesOnPause[SESSION_ID];
        setGlobalRunningState(GLOBAL_STATE.RUNNING);

    } catch (error) {
        console.error('--- Error during resume:', error);
        alert('Error during resume operation: ' + error.message);
    } finally {
        resetPauseButtons();
    }
}

/**
 * Reset pause-related buttons after processing.
 */
function resetPauseButtons() {
    isBusyProcessing = false;
    updateControlButtonStates();
}

// ========================================
// CLEAR BUTTON
// ========================================
if (btnClear) {
    btnClear.addEventListener('click', async (e) => {
        e.preventDefault();
        console.log('--- Clear button clicked');

        if (!confirm('This will permanently delete all deployed agents in the pool directory and clear the canvas. Continue?')) {
            return;
        }

        const $cleaningDialog = $('#cleaning-progress-dialog');
        $cleaningDialog.dialog({
            modal: true,
            width: 400,
            height: 'auto',
            resizable: false,
            draggable: false,
            closeOnEscape: false,
            dialogClass: 'cleaning-progress-dialog-class',
            open: function () {
                $(this).closest('.ui-dialog').find('.ui-dialog-titlebar-close').hide();
            }
        });

        try {
            const response = await fetch('/agent/clear_pool/', {
                method: 'POST', headers: getHeaders(), credentials: 'same-origin'
            });
            const result = await response.json();
            if (result.status === 'success') {
                console.log('--- Pool directory cleared successfully');
            } else {
                console.error('--- Failed to clear pool directory:', result.message);
                $cleaningDialog.dialog('close');
                alert('Failed to clear pool directory: ' + result.message);
                return;
            }

            if (typeof window.clearAllCanvasItems === 'function') {
                window.clearAllCanvasItems();
            }
            updateFilenameDisplay(null);
            titleBusyPrefix = "";
            setGlobalRunningState(GLOBAL_STATE.STOPPED);
            stopSystemManagedFlowHypervisor();
            console.log('--- Canvas and pool cleared successfully');

        } catch (error) {
            console.error('--- Error during clear operation:', error);
            alert('Error during clear operation: ' + error.message);
        } finally {
            if ($cleaningDialog.hasClass('ui-dialog-content')) {
                $cleaningDialog.dialog('close');
            }
        }
    });
}

// ========================================
// FLOWHYPERVISOR LIFECYCLE & POLLING
// ========================================
// Uses a serial setTimeout chain (never setInterval) so that each poll
// completes fully before the next one starts — no concurrent invocations.
let flowHypervisorPollingActive = false;
let flowHypervisorPollBusy = false;
let flowHypervisorAgentId = null;

async function startSystemManagedFlowHypervisor(agentId) {
    flowHypervisorAgentId = agentId;
    try {
        const response = await fetch(`/agent/execute_flowhypervisor/${agentId}/`, {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        });
        const result = await response.json();
        if (result.success) {
            console.log(`--- FlowHypervisor started with PID ${result.pid}`);
        } else {
            console.warn('--- FlowHypervisor failed to start:', result.message);
        }
    } catch (error) {
        console.error('--- Error starting FlowHypervisor:', error);
    }

    // Start serial polling loop (only alerts, no reanimation)
    flowHypervisorPollingActive = true;
    scheduleNextFlowHypervisorPoll();
}

function stopSystemManagedFlowHypervisor() {
    // Stop the polling loop
    flowHypervisorPollingActive = false;
    flowHypervisorPollBusy = false;

    // Actually kill the FlowHypervisor process via kill_session_processes
    fetch('/agent/kill_session_processes/', {
        method: 'POST', headers: getHeaders(), credentials: 'same-origin'
    }).then(r => r.json()).then(result => {
        console.log(`--- FlowHypervisor stop: killed ${result.killed_count} process(es)`);
    }).catch(err => {
        console.warn('--- Error killing FlowHypervisor process:', err);
    });
}

function scheduleNextFlowHypervisorPoll() {
    if (!flowHypervisorPollingActive) return;
    setTimeout(() => pollFlowHypervisorAlertSerial(), 5000);
}

async function pollFlowHypervisorAlertSerial() {
    // Guard: skip if polling was stopped or previous poll still running
    if (!flowHypervisorPollingActive) return;
    if (flowHypervisorPollBusy) return;
    if (globalRunningState !== GLOBAL_STATE.RUNNING) {
        // Flow no longer running, stop polling
        flowHypervisorPollingActive = false;
        return;
    }

    flowHypervisorPollBusy = true;
    try {
        const response = await fetch(`/agent/check_flowhypervisor_alert/${flowHypervisorAgentId}/`, {
            method: 'GET', headers: getHeaders(), credentials: 'same-origin'
        });
        const result = await response.json();
        if (result.has_alert) {
            showHypervisorAlertDialog(result.message);
        }
        // Core auto-stop: if no non-system agents are running, the flow
        // is complete — stop the FlowHypervisor immediately from the core
        // (the agent also has its own 3-cycle self-stop as a safety net
        // for when the core/browser is killed or frozen)
        if (result.flow_alive === false) {
            console.log('--- [FlowHypervisor] No agents running in the flow. Stopping FlowHypervisor from core.');
            flowHypervisorPollingActive = false;
            flowHypervisorPollBusy = false;
            stopSystemManagedFlowHypervisor();
            return;
        }
    } catch (err) {
        // ignore network errors
    } finally {
        flowHypervisorPollBusy = false;
        // Schedule next poll AFTER this one completes (serial, never concurrent)
        scheduleNextFlowHypervisorPoll();
    }
}

function playHypervisorAlertSound() {
    try {
        const audio = new Audio('/static/agent/sounds/hypervisor_alert.wav');
        audio.volume = 1.0; // MAXIMUM volume
        audio.play().catch(e => console.warn("Hypervisor alert sound failed:", e));
    } catch (e) {
        console.warn("Could not create hypervisor alert audio:", e);
    }
}

function showHypervisorAlertDialog(message) {
    // Play crash-like alert sound at maximum volume
    playHypervisorAlertSound();

    // Determine if dialog already exists
    let dialogDiv = document.getElementById('hypervisor-alert-dialog');
    if (!dialogDiv) {
        dialogDiv = document.createElement('div');
        dialogDiv.id = 'hypervisor-alert-dialog';
        dialogDiv.title = 'FlowHypervisor Alert';
        dialogDiv.style.display = 'none';
        
        const iconDiv = document.createElement('div');
        iconDiv.innerHTML = '🚨';
        iconDiv.style.fontSize = '3em';
        iconDiv.style.textAlign = 'center';
        iconDiv.style.marginBottom = '15px';
        
        const titleDiv = document.createElement('div');
        titleDiv.textContent = 'ATTENTION NEEDED';
        titleDiv.style.fontSize = '1.3em';
        titleDiv.style.fontWeight = 'bold';
        titleDiv.style.textAlign = 'center';
        titleDiv.style.color = '#e74c3c';
        titleDiv.style.marginBottom = '20px';
        
        const messageDiv = document.createElement('div');
        messageDiv.id = 'hypervisor-alert-message';
        messageDiv.style.fontSize = '1.1em';
        messageDiv.style.lineHeight = '1.5';
        messageDiv.style.textAlign = 'left';
        messageDiv.style.wordBreak = 'break-word';
        messageDiv.style.padding = '10px';
        messageDiv.style.backgroundColor = '#2c2c2c';
        messageDiv.style.borderLeft = '4px solid #F59E0B';
        messageDiv.style.borderRadius = '4px';

        dialogDiv.appendChild(iconDiv);
        dialogDiv.appendChild(titleDiv);
        dialogDiv.appendChild(messageDiv);
        document.body.appendChild(dialogDiv);
    }

    document.getElementById('hypervisor-alert-message').textContent = message;

    if ($(dialogDiv).hasClass('ui-dialog-content') && $(dialogDiv).dialog('isOpen')) {
        // Already open, just updated message
        return;
    }

    $(dialogDiv).dialog({
        autoOpen: true,
        modal: false,
        width: 500,
        height: 'auto',
        resizable: true,
        dialogClass: 'hypervisor-dialog-class',
        buttons: [
            {
                text: "Stop Flow",
                click: function () { 
                    $(this).dialog("close"); 
                    if (btnStop && !btnStop.disabled) {
                        btnStop.click();
                    } else if (globalRunningState === GLOBAL_STATE.RUNNING) {
                        // Directly force kill if stop button is disabled or missing
                        fetch('/agent/kill_session_processes/', {
                            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
                        }).then(() => {
                            setGlobalRunningState(GLOBAL_STATE.STOPPED);
                            stopSystemManagedFlowHypervisor();
                        });
                    }
                }
            },
            {
                text: "Dismiss",
                click: function () { $(this).dialog("close"); }
            }
        ],
        open: function() {
            const buttonPane = $(this).parent().find('.ui-dialog-buttonpane');
            buttonPane.find('button:contains("Stop Flow")').css({
                'background-color': '#e74c3c',
                'color': 'white', 'border': 'none', 'border-radius': '6px',
                'padding': '8px 20px', 'margin-right': '10px'
            });
            buttonPane.find('button:contains("Dismiss")').css({
                'background-color': '#555',
                'color': 'white', 'border': 'none', 'border-radius': '6px',
                'padding': '8px 20px'
            });
            // Bring to top
            $(this).parent().css('z-index', 9999);
        }
    });
}
