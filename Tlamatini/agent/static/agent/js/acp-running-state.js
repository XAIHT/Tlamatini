/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Crafted with heart by  Angela   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// Agentic Control Panel - Global Running State & Agent Status Polling
// LOAD ORDER: #5 - Depends on: acp-globals.js, acp-session.js, acp-undo-manager.js

// ========================================
// ASKER AGENT INTERACTION STATE
// ========================================
// Track which Asker agents have already had a choice submitted in this session.
// Delegated to the shared-runtime-dialogs module so chat & ACP share state
// (avoids the dialog re-appearing on either page after a click).
const submittedAskerRequests = (window.SharedRuntimeDialogs
    ? window.SharedRuntimeDialogs.submittedAskerRequests
    : new Set());

// ========================================
// GLOBAL RUNNING STATE MANAGEMENT
// ========================================

/**
 * Update all control button enabled/disabled states based on globalRunningState
 * and whether agents are present on the canvas.
 *
 * State rules:
 *   - No agents on canvas → ALL buttons disabled
 *   - STOPPED  → Start=enabled, Stop=disabled, Pause=disabled, Clear=enabled
 *   - RUNNING  → Start=disabled, Stop=enabled, Pause=enabled, Clear=disabled
 *   - PAUSED   → Start=enabled (resume), Stop=enabled, Pause=enabled, Clear=disabled
 *
 * Validate is handled separately by updateValidateButtonState() which applies
 * the same STOPPED-only rule plus a canvas-content check.
 */
function updateControlButtonStates() {
    const canvasItems = document.querySelectorAll('#submonitor-container .canvas-item');
    const hasAgents = canvasItems.length > 0;

    const isStopped = globalRunningState === GLOBAL_STATE.STOPPED;

    if (!hasAgents) {
        // No agents on canvas → everything disabled
        if (btnStart)    btnStart.disabled = true;
        if (btnStop)     btnStop.disabled  = true;
        if (btnPause)    btnPause.disabled = true;
        if (btnClear)    btnClear.disabled = true;
        if (btnValidate) btnValidate.disabled = true;
    } else {
        // Start: enabled when STOPPED or PAUSED (PAUSED → resume)
        const isPaused = globalRunningState === GLOBAL_STATE.PAUSED;
        if (btnStart) btnStart.disabled = !(isStopped || isPaused);

        // Stop: enabled when RUNNING or PAUSED
        if (btnStop) btnStop.disabled = isStopped;

        // Pause: enabled when RUNNING or PAUSED
        if (btnPause) btnPause.disabled = isStopped;

        // Clear: enabled only when STOPPED
        if (btnClear) btnClear.disabled = !isStopped;

        // Validate: delegated to its own function (checks STOPPED + canvas content)
        if (typeof updateValidateButtonState === 'function') {
            updateValidateButtonState();
        }
    }
}

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

    // Update all control button enabled/disabled states
    updateControlButtonStates();
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
            // ALL agents in the flow show yellow blinking LED when paused
            led.classList.add('led-paused');
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
        // (Delegated to shared-runtime-dialogs.js)
        // ========================================
        if (result.notifications && Array.isArray(result.notifications)) {
            result.notifications.forEach(notification => {
                const agentId = notification.agent_id;
                const sourceAgent = notification.source_agent;
                const matchesArray = notification.matches || [];
                console.log(`🚨 Notification from ${agentId}: Found "${matchesArray.join(', ')}" in ${sourceAgent}`);
                if (window.SharedRuntimeDialogs) {
                    window.SharedRuntimeDialogs.renderNotifierToast(notification);
                }
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
 * Escape HTML special characters to prevent injection in template literals.
 * Thin wrapper over SharedRuntimeDialogs.escapeHtml so existing call sites
 * keep working.
 * @param {string} str - Raw string
 * @returns {string} HTML-safe string
 */
function escapeHtml(str) {
    if (window.SharedRuntimeDialogs) {
        return window.SharedRuntimeDialogs.escapeHtml(str);
    }
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/**
 * Show the Asker Choice Dialog for a specific canvas Asker agent.
 * Delegates to shared-runtime-dialogs.js for the actual rendering.
 * Provides ACP-specific config loading (canvas node configs first, server fallback).
 * @param {string} agentId - The canvas ID of the Asker agent (e.g., 'asker-1')
 */
function showAskerChoiceDialog(agentId) {
    if (!window.SharedRuntimeDialogs) {
        console.error('SharedRuntimeDialogs module not loaded; cannot render Asker dialog.');
        return;
    }
    return window.SharedRuntimeDialogs.renderAskerChoiceDialog({
        identifier: agentId,
        sendChoice: sendAskerChoice,
        loadConfig: async (id) => {
            let config = typeof ACP !== 'undefined' ? ACP.nodeConfigs.get(id) : null;
            if (!config) {
                const resp = await fetch(`/agent/load_agent_config/${id}/`, {
                    headers: getHeaders(),
                    credentials: 'same-origin'
                });
                if (resp.ok) {
                    config = await resp.json();
                }
            }
            return config;
        }
    });
}

// ========================================
// PAGE LIFECYCLE: CLEAR POOL ON LOAD
// ========================================
document.addEventListener('DOMContentLoaded', async () => {
    // Set initial button states (STOPPED, possibly no agents)
    updateControlButtonStates();

    console.log('--- Page loaded: Clearing pool directory for fresh start...');
    try {
        const response = await fetch('/agent/clear_pool/', {
            method: 'POST',
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




