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
        console.log('--- Cannot start while system is PAUSED');
        alert('The system is currently paused. Click the Pause button to resume, or click Stop to fully stop.');
        return;
    }

    isBusyProcessing = true;

    btnStart.disabled = true;
    btnStart.style.opacity = '0.5';
    btnStart.style.cursor = 'not-allowed';
    if (btnStop) {
        btnStop.disabled = true;
        btnStop.style.opacity = '0.5';
    }

    const starterAgents = document.querySelectorAll('#submonitor-container .canvas-item.starter-agent');

    if (starterAgents.length === 0) {
        console.log('--- No Starter agents found on canvas');
        alert('No Starter agents found on the canvas. Add a Starter agent and connect it to other agents to begin.');
        isBusyProcessing = false;
        btnStart.disabled = false;
        btnStart.style.opacity = '';
        btnStart.style.cursor = '';
        if (btnStop) {
            btnStop.disabled = false;
            btnStop.style.opacity = '';
        }
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
    if (btnStart) { btnStart.disabled = false; btnStart.style.opacity = ''; btnStart.style.cursor = ''; }
    if (btnStop)  { btnStop.disabled = false; btnStop.style.opacity = ''; }

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

        btnStop.disabled = true;
        btnStop.style.opacity = '0.5';
        btnStop.style.cursor = 'not-allowed';
        if (btnStart) { btnStart.disabled = true; btnStart.style.opacity = '0.5'; }

        const enderAgents = document.querySelectorAll('#submonitor-container .canvas-item.ender-agent');

        if (enderAgents.length === 0) {
            console.log('--- No Ender agents found on canvas');
            alert('No Ender agents found on the canvas. Add an Ender agent and connect it to other agents to enable stop functionality.');
            isBusyProcessing = false;
            btnStop.disabled = false;
            btnStop.style.opacity = '';
            btnStop.style.cursor = '';
            if (btnStart) { btnStart.disabled = false; btnStart.style.opacity = ''; }
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
 * Show the result in the ender dialog (success or failure).
 */
function showEnderResult(success, failedAgentNames, dialog) {
    const titleEl = document.getElementById('ender-execution-title');
    const spinnerContainer = document.getElementById('ender-execution-spinner-container');
    const resultContainer = document.getElementById('ender-execution-result');
    const iconEl = document.getElementById('ender-execution-icon');
    const messageEl = document.getElementById('ender-execution-message');
    const failedListEl = document.getElementById('ender-execution-failed-list');

    spinnerContainer.style.display = 'none';
    resultContainer.style.display = 'block';

    if (success) {
        titleEl.innerText = "Termination Complete";
        iconEl.innerHTML = '✅';
        iconEl.className = 'success';
        messageEl.innerText = 'All Ender agents have been successfully executed!';
        messageEl.className = 'success';
        failedListEl.innerHTML = '';

        setGlobalRunningState(GLOBAL_STATE.STOPPED);

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
    if (btnStart) { btnStart.disabled = false; btnStart.style.opacity = ''; btnStart.style.cursor = ''; }
    if (btnStop)  { btnStop.disabled = false; btnStop.style.opacity = ''; btnStop.style.cursor = ''; }

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
    if (btnStart) { btnStart.disabled = false; btnStart.style.opacity = ''; btnStart.style.cursor = ''; }
    if (btnStop)  { btnStop.disabled = false; btnStop.style.opacity = ''; btnStop.style.cursor = ''; }

    spinnerContainer.style.display = 'none';
    resultContainer.style.display = 'block';
    failedListEl.innerHTML = '';

    titleEl.innerText = "All Agents Already Down";
    iconEl.innerHTML = 'ℹ️';
    iconEl.className = 'info';
    messageEl.innerText = 'All target agents are already stopped. No termination was needed.';
    messageEl.className = 'info';

    setGlobalRunningState(GLOBAL_STATE.STOPPED);

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
 * Pause execution: get running processes, store them, kill them, update UI.
 */
async function pauseExecution() {
    isBusyProcessing = true;

    if (btnPause) { btnPause.disabled = true; btnPause.style.opacity = '0.5'; }
    if (btnStart) { btnStart.disabled = true; btnStart.style.opacity = '0.5'; }
    if (btnStop)  { btnStop.disabled = true; btnStop.style.opacity = '0.5'; }

    try {
        console.log('--- Fetching running processes...');
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
        console.log(`--- Found ${runningProcesses.length} running process(es)`);

        if (runningProcesses.length === 0) {
            console.log('--- No running processes to pause');
            alert('No running processes found to pause.');
            resetPauseButtons();
            return;
        }

        pausedProcessesOnPause[SESSION_ID] = runningProcesses;
        console.log(`--- Stored ${runningProcesses.length} process(es) in pausedProcessesOnPause[${SESSION_ID}]`);

        console.log('--- Killing all session processes...');
        const killResponse = await fetch('/agent/kill_session_processes/', {
            method: 'POST', headers: getHeaders(), credentials: 'same-origin'
        });
        const killResult = await killResponse.json();

        if (killResult.success) {
            console.log(`--- Killed ${killResult.killed_count} process(es)`);
        } else {
            console.warn('--- Kill operation reported issues:', killResult.message);
        }

        setGlobalRunningState(GLOBAL_STATE.PAUSED);

    } catch (error) {
        console.error('--- Error during pause:', error);
        alert('Error during pause operation: ' + error.message);
    } finally {
        resetPauseButtons();
    }
}

/**
 * Resume from pause: restart stored processes, update UI.
 */
async function resumeFromPause() {
    isBusyProcessing = true;

    if (btnPause) { btnPause.disabled = true; btnPause.style.opacity = '0.5'; }
    if (btnStart) { btnStart.disabled = true; btnStart.style.opacity = '0.5'; }
    if (btnStop)  { btnStop.disabled = true; btnStop.style.opacity = '0.5'; }

    try {
        const storedProcesses = pausedProcessesOnPause[SESSION_ID] || [];

        if (storedProcesses.length === 0) {
            console.log('--- No stored processes to resume');
            setGlobalRunningState(GLOBAL_STATE.STOPPED);
            resetPauseButtons();
            return;
        }

        console.log(`--- Restarting ${storedProcesses.length} agent(s)...`);

        const agentsToRestart = storedProcesses.map(proc => ({
            canvas_id: proc.canvas_id,
            folder_name: proc.folder_name,
            script_name: proc.script_name
        }));

        // Remove duplicates based on canvas_id
        const uniqueAgents = [];
        const seenIds = new Set();
        for (const agent of agentsToRestart) {
            if (!seenIds.has(agent.canvas_id)) {
                seenIds.add(agent.canvas_id);
                uniqueAgents.push(agent);
            }
        }
        console.log(`--- Unique agents to restart: ${uniqueAgents.length}`);

        const restartResponse = await fetch('/agent/restart_agents/', {
            method: 'POST',
            headers: { ...getHeaders(), 'Content-Type': 'application/json' },
            credentials: 'same-origin',
            body: JSON.stringify({ agents: uniqueAgents })
        });
        const restartResult = await restartResponse.json();

        if (restartResult.success) {
            console.log(`--- Successfully restarted ${restartResult.restarted.length} agent(s)`);
        } else {
            console.warn('--- Some agents failed to restart:', restartResult.failed);
            if (restartResult.failed.length > 0) {
                alert(`Warning: ${restartResult.failed.length} agent(s) failed to restart.`);
            }
        }

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
    if (btnPause) { btnPause.disabled = false; btnPause.style.opacity = ''; }
    if (btnStart) { btnStart.disabled = false; btnStart.style.opacity = ''; }
    if (btnStop)  { btnStop.disabled = false; btnStop.style.opacity = ''; }
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






