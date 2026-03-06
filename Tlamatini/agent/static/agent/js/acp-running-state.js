// Agentic Control Panel - Global Running State & Agent Status Polling
// LOAD ORDER: #5 - Depends on: acp-globals.js, acp-session.js, acp-undo-manager.js

// ========================================
// ASKER AGENT INTERACTION STATE
// ========================================
// Track which Asker agents have already had a choice submitted in this session
const submittedAskerRequests = new Set();

// ========================================
// GLOBAL RUNNING STATE MANAGEMENT
// ========================================

/**
 * Set the global running state and update UI accordingly.
 * @param {string} newState - One of GLOBAL_STATE.RUNNING / STOPPED / PAUSED
 */
function setGlobalRunningState(newState) {
    const previousState = globalRunningState;
    globalRunningState = newState;

    console.log(`--- Global state changed: ${previousState} -> ${newState}`);

    // Remove all state classes first
    if (btnStart) btnStart.classList.remove('pressed');
    if (btnPause) btnPause.classList.remove('paused');

    if (newState === GLOBAL_STATE.RUNNING) {
        if (btnStart) btnStart.classList.add('pressed');
        if (btnPause) btnPause.classList.remove('paused');
        startAgentStatusPolling();

    } else if (newState === GLOBAL_STATE.STOPPED) {
        if (btnStart) btnStart.classList.remove('pressed');
        if (btnPause) btnPause.classList.remove('paused');
        // Clear any stored paused processes for this session
        if (pausedProcessesOnPause[SESSION_ID]) {
            delete pausedProcessesOnPause[SESSION_ID];
            console.log(`--- Cleared pausedProcessesOnPause for session ${SESSION_ID}`);
        }
        stopAgentStatusPolling();
        titleBusyPrefix = "";
        updateAllLedIndicators({});

    } else if (newState === GLOBAL_STATE.PAUSED) {
        if (btnStart) btnStart.classList.add('pressed');
        if (btnPause) btnPause.classList.add('paused');
        stopAgentStatusPolling();
        titleBusyPrefix = "";
        updateAllLedIndicators({});
    }
}

/**
 * Update LED indicators on all canvas items based on running status.
 * @param {Object} runningAgents - Map of agentId -> isRunning (boolean)
 */
function updateAllLedIndicators(runningAgents) {
    const canvasItems = document.querySelectorAll('#submonitor-container .canvas-item');

    // For PAUSED state, get the list of paused agents for this session
    const pausedAgents = pausedProcessesOnPause[SESSION_ID] || [];
    const pausedAgentIds = new Set(pausedAgents.map(p => p.canvas_id));

    canvasItems.forEach(item => {
        const led = item.querySelector('.canvas-item-led');
        if (!led) return;

        led.classList.remove('led-idle', 'led-on', 'led-off', 'led-paused');

        if (globalRunningState === GLOBAL_STATE.STOPPED) {
            led.classList.add('led-idle');
        } else if (globalRunningState === GLOBAL_STATE.RUNNING) {
            const isRunning = runningAgents[item.id] === true;
            led.classList.add(isRunning ? 'led-on' : 'led-off');
        } else if (globalRunningState === GLOBAL_STATE.PAUSED) {
            led.classList.add(pausedAgentIds.has(item.id) ? 'led-paused' : 'led-idle');
        }
    });
}

// ========================================
// AGENT STATUS POLLING
// ========================================

/**
 * Start polling for agent running status.
 */
function startAgentStatusPolling() {
    if (agentStatusPollerInterval) {
        clearInterval(agentStatusPollerInterval);
    }
    console.log('--- Starting agent status polling...');
    pollAgentStatus(); // Poll immediately once
    agentStatusPollerInterval = setInterval(pollAgentStatus, AGENT_STATUS_POLL_INTERVAL);
}

/**
 * Stop polling for agent running status.
 */
function stopAgentStatusPolling() {
    if (agentStatusPollerInterval) {
        clearInterval(agentStatusPollerInterval);
        agentStatusPollerInterval = null;
        console.log('--- Stopped agent status polling');
    }
}

/**
 * Poll the backend to check which agents are currently running.
 * Also handles Asker user-input requests and Notifier notifications.
 */
async function pollAgentStatus() {
    try {
        const response = await fetch('/agent/check_all_agents_status/', {
            method: 'GET',
            headers: getHeaders(),
            credentials: 'same-origin'
        });

        if (!response.ok) {
            console.warn('--- Failed to poll agent status:', response.statusText);
            return;
        }

        const result = await response.json();

        // If the state changed while we were fetching (e.g. user clicked Stop), discard the stale result
        // to prevent overwriting correct titleBusyPrefix and LED states.
        if (globalRunningState !== GLOBAL_STATE.RUNNING) {
            console.log('--- Discarding poll result because system is no longer RUNNING');
            return;
        }

        // result.agents is expected to be a map of agentId -> isRunning
        const runningAgents = result.agents || {};

        // Ensure we only consider an agent running if it is actually present on the canvas
        const canvasItems = document.querySelectorAll('#submonitor-container .canvas-item');
        const anyRunning = Array.from(canvasItems).some(item => runningAgents[item.id] === true);

        // Update title hourglass based on running state or if FlowCreator is waiting for LLM
        if (typeof isFlowCreatorWaiting !== 'undefined' && isFlowCreatorWaiting) {
            titleBusyPrefix = "⏳ ";
        } else {
            titleBusyPrefix = anyRunning ? "⏳ " : "";
        }

        // Update LED indicators
        updateAllLedIndicators(runningAgents);

        // ========================================
        // ASKER AGENT: HANDLE USER INPUT REQUESTS
        // ========================================
        const detailedStatuses = result.detailed_statuses || {};

        // 1. Check for new requests
        for (const [agentId, status] of Object.entries(detailedStatuses)) {
            if (status === 'waiting_for_user_input') {
                showAskerChoiceDialog(agentId);
            } else {
                // Agent is NOT waiting - clear submitted flag so dialog can show again later
                if (submittedAskerRequests.has(agentId)) {
                    submittedAskerRequests.delete(agentId);
                }
            }
        }

        // 2. Clear flags for agents no longer in detailedStatuses (e.g., stopped/removed)
        for (const submittedId of submittedAskerRequests) {
            if (!Object.prototype.hasOwnProperty.call(detailedStatuses, submittedId)) {
                submittedAskerRequests.delete(submittedId);
            }
        }

        // ========================================
        // NOTIFIER AGENT: HANDLE NOTIFICATIONS
        // ========================================
        if (result.notifications && Array.isArray(result.notifications)) {
            result.notifications.forEach(notification => {
                const agentId = notification.agent_id;
                const matchesArray = notification.matches || [];
                const matches = matchesArray.join(', ');
                const sourceAgent = notification.source_agent;
                const timestamp = notification.timestamp;
                const soundEnabled = notification.sound_enabled;

                console.log(`🚨 Notification from ${agentId}: Found "${matches}" in ${sourceAgent}`);

                // ========================================
                // SEVERITY DETECTION
                // ========================================
                const matchesLower = matches.toLowerCase();
                const errorPatterns = ['error', 'fatal'];
                const warningPatterns = ['warn', 'warning'];
                const hasError = errorPatterns.some(pattern => matchesLower.includes(pattern));
                const hasWarning = warningPatterns.some(pattern => matchesLower.includes(pattern));

                let severity = 'success';
                let severityIcon = '✅';
                let severityColor = '#10B981';
                let severityBgColor = '#D1FAE5';
                let severityTextColor = '#065F46';
                let dialogTitle = 'Pattern Detected';

                if (hasError) {
                    severity = 'error';
                    severityIcon = '🚨';
                    severityColor = '#DC2626';
                    severityBgColor = '#FEE2E2';
                    severityTextColor = '#991B1B';
                    dialogTitle = 'Error Detected';
                } else if (hasWarning) {
                    severity = 'warning';
                    severityIcon = '⚠️';
                    severityColor = '#F59E0B';
                    severityBgColor = '#FEF3C7';
                    severityTextColor = '#92400E';
                    dialogTitle = 'Warning Detected';
                }

                // 1. Play Sound (if enabled)
                if (soundEnabled) {
                    const audio = new Audio('/static/agent/sounds/notification.wav');
                    audio.play().catch(e => console.warn("Audio play failed (user interaction needed?):", e));
                }

                // 2. Show Dialog (Non-modal) with severity-based styling
                const dialogId = `notification-dialog-${Date.now()}`;
                const dialogDiv = document.createElement('div');
                dialogDiv.id = dialogId;
                dialogDiv.title = `${severityIcon} ${dialogTitle}: ${sourceAgent}`;
                dialogDiv.innerHTML = `
                    <p style="text-align: center; color: ${severityColor}; font-weight: bold; font-size: 1.1em;">
                        ${dialogTitle}!
                    </p>
                    <p><strong>Agent:</strong> ${sourceAgent}</p>
                    <p><strong>Found:</strong> <span style="background-color: ${severityBgColor}; padding: 2px 5px; border-radius: 3px; color: ${severityTextColor};">${matches}</span></p>
                    <p style="font-size: 0.8em; color: #888;">${timestamp}</p>
                `;
                document.body.appendChild(dialogDiv);

                $(dialogDiv).dialog({
                    modal: false,
                    width: 350,
                    resizable: false,
                    draggable: true,
                    closeText: "Dismiss",
                    dialogClass: `notification-dialog-class notification-${severity}`,
                    buttons: {
                        "Dismiss": function () {
                            $(this).dialog("close");
                        }
                    },
                    close: function () {
                        $(this).dialog("destroy");
                        dialogDiv.remove();
                    },
                    position: { my: "right bottom", at: "right-20 bottom-20", of: window },
                    open: function () {
                        $(this).parent().css('border-left', `4px solid ${severityColor}`);
                    }
                });
            });
        }

        // If no agents are running and we thought we were running, transition to STOPPED
        if (globalRunningState === GLOBAL_STATE.RUNNING && !anyRunning) {
            console.log('--- No agents running, transitioning to STOPPED state');
            setGlobalRunningState(GLOBAL_STATE.STOPPED);
        }

    } catch (error) {
        console.error('--- Error polling agent status:', error);
    }
}

// ========================================
// ASKER AGENT: USER CHOICE DIALOG
// ========================================

/**
 * Send the user's A/B choice to the backend for a running Asker agent.
 * @param {string} agentId - The Asker agent's canvas ID
 * @param {string} choice - 'A' or 'B'
 */
async function sendAskerChoice(agentId, choice) {
    try {
        const response = await fetch(`/agent/asker_choice/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ choice: choice })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Asker ${agentId} choice sent: Path ${choice}`, result.message);
        } else {
            console.error(`--- Failed to send Asker ${agentId} choice:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error sending Asker ${agentId} choice:`, error);
    }
}

/**
 * Show the Asker Choice Dialog for a specific agent.
 * @param {string} agentId - The canvas ID of the Asker agent
 */
function showAskerChoiceDialog(agentId) {
    // If we already submitted a choice for this agent, don't show again
    if (submittedAskerRequests.has(agentId)) return;

    const dialogId = `asker-dialog-${agentId}`;
    if (document.getElementById(dialogId)) return; // Dialog already open

    const dialogDiv = document.createElement('div');
    dialogDiv.id = dialogId;
    dialogDiv.title = "User Input Needed";
    dialogDiv.innerHTML = `
        <p style="text-align: center; font-size: 1.1em;">
            <strong>${agentId}</strong> needs your input!
        </p>
        <p style="text-align: center;">Choose a path to continue:</p>
        <div style="display: flex; justify-content: space-around; margin-top: 15px;">
            <button id="btn-choice-a-${agentId}" class="asker-choice-btn" style="background: #EF4444; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Path A</button>
            <button id="btn-choice-b-${agentId}" class="asker-choice-btn" style="background: #3B82F6; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">Path B</button>
        </div>
    `;
    document.body.appendChild(dialogDiv);

    const $dialog = $(dialogDiv).dialog({
        modal: false,
        width: 350,
        resizable: false,
        draggable: true,
        closeText: "",
        dialogClass: "asker-dialog-wrapper",
        close: function () {
            $(this).dialog("destroy");
            dialogDiv.remove();
        },
        position: { my: "center", at: "center", of: window },
        open: function () {
            $(this).parent().css('border-top', '4px solid #8B5CF6');
        }
    });

    const btnA = document.getElementById(`btn-choice-a-${agentId}`);
    const btnB = document.getElementById(`btn-choice-b-${agentId}`);

    if (btnA) {
        btnA.addEventListener('click', () => {
            submittedAskerRequests.add(agentId);
            btnA.textContent = "Sending...";
            btnA.disabled = true;
            if (btnB) btnB.disabled = true;
            sendAskerChoice(agentId, 'A');
            $dialog.dialog("close");
        });
    }

    if (btnB) {
        btnB.addEventListener('click', () => {
            submittedAskerRequests.add(agentId);
            btnB.textContent = "Sending...";
            btnB.disabled = true;
            if (btnA) btnA.disabled = true;
            sendAskerChoice(agentId, 'B');
            $dialog.dialog("close");
        });
    }
}

// ========================================
// PAGE LIFECYCLE: CLEAR POOL ON LOAD
// ========================================
document.addEventListener('DOMContentLoaded', async () => {
    console.log('--- Page loaded: Clearing pool directory for fresh start...');
    try {
        const response = await fetch('/agent/clear_pool/', {
            method: 'GET',
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        const result = await response.json();
        if (result.status === 'success') {
            console.log('--- Pool directory cleared on page load');
        } else {
            console.warn('--- Failed to clear pool on load:', result.message);
        }
    } catch (error) {
        console.error('--- Error clearing pool on load:', error);
    }
});
