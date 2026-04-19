// Agentic Control Panel - Flow Validation Logic
// LOAD ORDER: #7 - Depends on: acp-globals.js, acp-session.js, acp-control-buttons.js

// ========================================
// VALIDATE BUTTON STATE MANAGEMENT
// ========================================

/**
 * Update the Validate button enabled/disabled state.
 * Enabled only when: flow is STOPPED and at least one non-FlowCreator agent is on canvas.
 */
function updateValidateButtonState() {
    if (!btnValidate) return;

    const isStopped = globalRunningState === GLOBAL_STATE.STOPPED;
    const canvasItems = document.querySelectorAll('#submonitor-container .canvas-item');
    const hasNonFlowCreator = Array.from(canvasItems).some(item => {
        const agentName = (item.getAttribute('data-agent-name') || item.id || '').toLowerCase();
        return !agentName.startsWith('flowcreator');
    });

    const shouldEnable = isStopped && hasNonFlowCreator;

    btnValidate.disabled = !shouldEnable;
    if (shouldEnable) {
        btnValidate.style.opacity = '';
        btnValidate.style.cursor = '';
    } else {
        btnValidate.style.opacity = '0.5';
        btnValidate.style.cursor = 'not-allowed';
    }
}

// ========================================
// ADJACENCY MATRIX CONSTRUCTION & VALIDATION
// ========================================

/**
 * Extract all output connections (target agent names) from an agent's config.
 * Handles: target_agents, target_agents_a, target_agents_b, output_agents.
 *
 * For Ender agents, target_agents are KILL targets (not flow connections),
 * so only output_agents are returned as actual flow outputs.
 *
 * @param {Object} config - The agent's config.yaml data
 * @param {string} [agentType] - The agent type (e.g. 'ender', 'starter')
 * @returns {string[]} - Array of connected agent folder names
 */
function extractOutputConnections(config, agentType) {
    const connections = [];

    // For Ender agents, target_agents are kill targets — NOT flow output connections.
    // Only output_agents (Cleaners to launch) are real flow outputs for Ender.
    if (agentType !== 'ender') {
        // Standard target_agents
        if (Array.isArray(config.target_agents)) {
            connections.push(...config.target_agents);
        }
    }

    // Asker/Forker dual outputs
    if (Array.isArray(config.target_agents_a)) {
        connections.push(...config.target_agents_a);
    }
    if (Array.isArray(config.target_agents_b)) {
        connections.push(...config.target_agents_b);
    }

    // Ender/Stopper/Cleaner output_agents
    if (Array.isArray(config.output_agents)) {
        connections.push(...config.output_agents);
    }

    return connections;
}

/**
 * Extract all source connections (source agent names) from an agent's config.
 * Handles: source_agents.
 * @param {Object} config - The agent's config.yaml data
 * @returns {string[]} - Array of source agent folder names
 */
function extractSourceConnections(config) {
    if (Array.isArray(config.source_agents)) {
        return [...config.source_agents];
    }
    return [];
}

/**
 * Run the full flow validation process.
 * Steps A-D as specified in the requirements.
 */
async function runFlowValidation() {
    console.log('--- [Validate] Starting flow validation...');

    // Step A: List all agents in the pool
    let agentsData;
    try {
        const response = await fetch('/agent/validate_flow/', {
            method: 'GET',
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        const result = await response.json();
        agentsData = result.agents || [];
    } catch (error) {
        console.error('--- [Validate] Error fetching pool agents:', error);
        showValidationResultDialog(false, ['Failed to read agent configurations: ' + error.message]);
        return;
    }

    if (agentsData.length === 0) {
        showValidationResultDialog(false, ['No agents found in the pool directory. Deploy agents to the canvas first.']);
        return;
    }

    console.log(`--- [Validate] Found ${agentsData.length} agent(s) in pool (excluding FlowCreator)`);

    // Step B: Configs are already loaded by the backend (FlowCreator excluded)

    // Step C: Build NxN adjacency matrix
    const N = agentsData.length;
    const agentNames = agentsData.map(a => a.folder_name);
    const agentTypes = agentsData.map(a => a.agent_type.toLowerCase());
    const nameToIndex = {};
    agentNames.forEach((name, idx) => { nameToIndex[name] = idx; });

    // Initialize NxN matrix with zeros
    const matrix = [];
    for (let i = 0; i < N; i++) {
        matrix.push(new Array(N).fill(0));
    }

    // Fill matrix: row = source agent outputs, col = target agent
    for (let i = 0; i < N; i++) {
        const config = agentsData[i].config;
        
        // Forward connections (this agent -> target agent)
        const outputs = extractOutputConnections(config, agentTypes[i]);
        for (const targetName of outputs) {
            const j = nameToIndex[targetName];
            if (j !== undefined) {
                matrix[i][j] = 1;
            }
        }

        // Backward connections (source agent -> this agent)
        const sources = extractSourceConnections(config);
        for (const sourceName of sources) {
            const j = nameToIndex[sourceName];
            if (j !== undefined) {
                matrix[j][i] = 1; // j is source, i is this agent
            }
        }
    }

    console.log('--- [Validate] Adjacency matrix built:', matrix);
    console.log('--- [Validate] Agent order:', agentNames.map((n, i) => `${i}:${n}(${agentTypes[i]})`));

    // Step D: Run verification checks
    const errors = [];
    const ENDER_OUTPUT_TYPES = ['cleaner', 'flowbacker'];
    const CLEANER_INPUT_TYPES = ['ender', 'flowbacker'];
    const FLOWBACKER_INPUT_TYPES = ['starter', 'ender', 'forker', 'asker'];
    const getOutgoingIndices = (row) => matrix[row]
        .map((value, idx) => (value === 1 ? idx : -1))
        .filter(idx => idx !== -1);
    const getIncomingIndices = (col) => matrix
        .map((rowValues, idx) => (rowValues[col] === 1 ? idx : -1))
        .filter(idx => idx !== -1);

    // i) Verify Starter columns have only zeros (no incoming connections)
    const starterErrors = [];
    for (let col = 0; col < N; col++) {
        if (agentTypes[col] !== 'starter') continue;
        for (let row = 0; row < N; row++) {
            if (matrix[row][col] === 1) {
                starterErrors.push(agentNames[col]);
                break;
            }
        }
    }
    if (starterErrors.length > 0) {
        errors.push({
            message: 'Starter agents must only have target_agents',
            agents: starterErrors
        });
    }

    // ii) Verify Ender rows have only 1s in Cleaner/FlowBacker columns
    const enderOutputErrors = [];
    for (let row = 0; row < N; row++) {
        if (agentTypes[row] !== 'ender') continue;
        for (let col = 0; col < N; col++) {
            if (matrix[row][col] === 1 && !ENDER_OUTPUT_TYPES.includes(agentTypes[col])) {
                enderOutputErrors.push(agentNames[row]);
                break;
            }
        }
    }
    if (enderOutputErrors.length > 0) {
        errors.push({
            message: 'Ender agents can only have output_agents of type Cleaner or FlowBacker',
            agents: enderOutputErrors
        });
    }

    // ii.b) Verify Ender does not launch Cleaner in parallel with FlowBacker
    const enderParallelCleanupErrors = [];
    for (let row = 0; row < N; row++) {
        if (agentTypes[row] !== 'ender') continue;
        const outputTypes = new Set(getOutgoingIndices(row).map(col => agentTypes[col]));
        if (outputTypes.has('flowbacker') && outputTypes.has('cleaner')) {
            enderParallelCleanupErrors.push(agentNames[row]);
        }
    }
    if (enderParallelCleanupErrors.length > 0) {
        errors.push({
            message: 'Ender agents must not launch Cleaner directly when they also launch FlowBacker. Route Cleaner only from FlowBacker so backup completes before logs are deleted',
            agents: enderParallelCleanupErrors
        });
    }

    // iii) Verify Cleaner columns have only 1s from Ender/FlowBacker rows
    const cleanerInputErrors = [];
    const cleanerMixedInputErrors = [];
    for (let col = 0; col < N; col++) {
        if (agentTypes[col] !== 'cleaner') continue;
        const incomingRows = getIncomingIndices(col);
        const incomingTypes = new Set(incomingRows.map(row => agentTypes[row]));
        for (const row of incomingRows) {
            if (!CLEANER_INPUT_TYPES.includes(agentTypes[row])) {
                cleanerInputErrors.push(agentNames[col]);
                break;
            }
        }
        if (incomingTypes.has('ender') && incomingTypes.has('flowbacker')) {
            cleanerMixedInputErrors.push(agentNames[col]);
        }
    }
    if (cleanerInputErrors.length > 0) {
        errors.push({
            message: 'Cleaner agents can only be connected from source_agents of type Ender or FlowBacker',
            agents: cleanerInputErrors
        });
    }
    if (cleanerMixedInputErrors.length > 0) {
        errors.push({
            message: 'Cleaner agents must be triggered by either Ender or FlowBacker, but never by both in the same flow branch',
            agents: cleanerMixedInputErrors
        });
    }

    // iv) Verify FlowBacker columns have only Starter/Ender/Forker/Asker inputs
    const flowBackerInputErrors = [];
    for (let col = 0; col < N; col++) {
        if (agentTypes[col] !== 'flowbacker') continue;
        for (let row = 0; row < N; row++) {
            if (matrix[row][col] === 1 && !FLOWBACKER_INPUT_TYPES.includes(agentTypes[row])) {
                flowBackerInputErrors.push(agentNames[col]);
                break;
            }
        }
    }
    if (flowBackerInputErrors.length > 0) {
        errors.push({
            message: 'FlowBacker agents can only be connected from Starter, Ender, Forker, or Asker source_agents',
            agents: flowBackerInputErrors
        });
    }

    // v) Verify FlowBacker rows have only Cleaner outputs
    const flowBackerOutputErrors = [];
    for (let row = 0; row < N; row++) {
        if (agentTypes[row] !== 'flowbacker') continue;
        for (let col = 0; col < N; col++) {
            if (matrix[row][col] === 1 && agentTypes[col] !== 'cleaner') {
                flowBackerOutputErrors.push(agentNames[row]);
                break;
            }
        }
    }
    if (flowBackerOutputErrors.length > 0) {
        errors.push({
            message: 'FlowBacker agents can only have target_agents of type Cleaner',
            agents: flowBackerOutputErrors
        });
    }

    // vi) Verify main diagonal is all zeros (no self-connections)
    const selfLoopErrors = [];
    for (let i = 0; i < N; i++) {
        if (matrix[i][i] === 1) {
            selfLoopErrors.push(agentNames[i]);
        }
    }
    if (selfLoopErrors.length > 0) {
        errors.push({
            message: "All of the agent's outputs must not connect to itself",
            agents: selfLoopErrors
        });
    }

    // vii) Verify all non-Starter columns have at least one incoming connection
    const noInputErrors = [];
    for (let col = 0; col < N; col++) {
        if (agentTypes[col] === 'starter') continue;
        let hasInput = false;
        for (let row = 0; row < N; row++) {
            if (matrix[row][col] === 1) {
                hasInput = true;
                break;
            }
        }
        if (!hasInput) {
            noInputErrors.push(agentNames[col]);
        }
    }
    if (noInputErrors.length > 0) {
        errors.push({
            message: 'Some agents have no connections to its input',
            agents: noInputErrors
        });
    }

    // viii) Verify all referenced agents (target_agents, output_agents, source_agents)
    //     exist in the flow. Target/output agents must also have an input triangle.
    // Agent types without input triangles: starter (flowcreator/flowhypervisor are already excluded)
    const TYPES_WITHOUT_INPUT = ['starter'];
    const missingTargetErrors = [];
    const noInputTriErrors = [];
    const missingSourceErrors = [];
    for (let i = 0; i < N; i++) {
        const config = agentsData[i].config;

        // Check target_agents, target_agents_a, target_agents_b, output_agents
        const outputs = extractOutputConnections(config, agentTypes[i]);
        for (const targetName of outputs) {
            const j = nameToIndex[targetName];
            if (j === undefined) {
                missingTargetErrors.push(`${agentNames[i]} references target "${targetName}" which is not present in the flow`);
            } else if (TYPES_WITHOUT_INPUT.includes(agentTypes[j])) {
                noInputTriErrors.push(`${agentNames[i]} references target "${targetName}" which is a ${agentTypes[j]} agent (no input)`);
            }
        }

        // For Ender agents: validate kill targets (target_agents) exist in the flow.
        // Ender CAN target any agent type including Starters (to kill them), so no input-triangle check.
        if (agentTypes[i] === 'ender' && Array.isArray(config.target_agents)) {
            for (const targetName of config.target_agents) {
                const j = nameToIndex[targetName];
                if (j === undefined) {
                    missingTargetErrors.push(`${agentNames[i]} references kill target "${targetName}" which is not present in the flow`);
                }
            }
        }

        // Check source_agents
        const sources = extractSourceConnections(config);
        for (const sourceName of sources) {
            if (nameToIndex[sourceName] === undefined) {
                missingSourceErrors.push(`${agentNames[i]} references source "${sourceName}" which is not present in the flow`);
            }
        }
    }
    if (missingTargetErrors.length > 0) {
        errors.push({
            message: 'Some agents reference target agents that are not present in the flow',
            agents: missingTargetErrors
        });
    }
    if (noInputTriErrors.length > 0) {
        errors.push({
            message: 'Some agents reference target agents that do not have an input (e.g. Starter agents cannot be targets)',
            agents: noInputTriErrors
        });
    }
    if (missingSourceErrors.length > 0) {
        errors.push({
            message: 'Some agents reference source agents that are not present in the flow',
            agents: missingSourceErrors
        });
    }

    // Set validation status and show result
    if (errors.length === 0) {
        flowValidationStatus = VALIDATION_STATE.VALID;
        console.log('--- [Validate] Flow is VALID');
        showValidationResultDialog(true, []);
    } else {
        flowValidationStatus = VALIDATION_STATE.INVALID;
        console.log('--- [Validate] Flow is INVALID, errors:', errors);
        showValidationResultDialog(false, errors);
    }
}

// ========================================
// VALIDATION RESULT DIALOG
// ========================================

/**
 * Show the validation result in a jQuery UI dialog.
 * @param {boolean} isValid - Whether validation passed
 * @param {Array} errors - Array of { message, agents } objects (or string[] for simple errors)
 */
function showValidationResultDialog(isValid, errors) {
    const dialogDiv = document.getElementById('validation-result-dialog');
    if (!dialogDiv) {
        console.error('--- [Validate] validation-result-dialog element not found');
        return;
    }

    const contentEl = document.getElementById('validation-result-content');

    if (isValid) {
        contentEl.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 15px;">✅</div>
            <h4 style="color: #10B981; margin-bottom: 10px;">Flow is Valid</h4>
            <p style="color: #ccc;">All verification checks passed successfully. The flow structure is correct.</p>
        `;
    } else {
        let errorHtml = '';
        for (const err of errors) {
            if (typeof err === 'string') {
                errorHtml += `<div style="margin-bottom: 10px; padding: 8px; background: #3a1a1a; border-left: 3px solid #e74c3c; border-radius: 4px;">
                    <p style="color: #f87171; margin: 0;">${err}</p>
                </div>`;
            } else {
                errorHtml += `<div style="margin-bottom: 10px; padding: 8px; background: #3a1a1a; border-left: 3px solid #e74c3c; border-radius: 4px;">
                    <p style="color: #f87171; font-weight: bold; margin: 0 0 5px 0;">⚠️ ${err.message}</p>
                    <p style="color: #ccc; margin: 0; font-size: 0.9em;">Agents: ${err.agents.join(', ')}</p>
                </div>`;
            }
        }

        contentEl.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 15px;">❌</div>
            <h4 style="color: #e74c3c; margin-bottom: 10px;">Validation Failed</h4>
            <div style="text-align: left; max-height: 300px; overflow-y: auto; margin-top: 10px;">
                ${errorHtml}
            </div>
        `;
    }

    const $dialog = $(dialogDiv);
    $dialog.dialog({
        title: isValid ? 'Flow Validation: Passed ✅' : 'Flow Validation: Failed ❌',
        autoOpen: true,
        modal: true,
        width: 520,
        resizable: false,
        draggable: true,
        closeOnEscape: true,
        closeText: "",
        dialogClass: "validation-result-dialog-wrapper",
        open: function () {
            document.body.style.overflow = 'hidden';
        },
        close: function () {
            document.body.style.overflow = '';
        },
        buttons: [{
            text: "Continue!",
            click: function () { $(this).dialog("close"); }
        }]
    });

    // Style the Continue button
    const buttonPane = $dialog.parent().find('.ui-dialog-buttonpane');
    buttonPane.find('button:contains("Continue")').css({
        'background-color': isValid ? '#10B981' : '#e74c3c',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '120px'
    });
}

// ========================================
// START BUTTON VALIDATION CHECK DIALOGS
// ========================================

/**
 * Show a dialog when user clicks Start and flow is INVALID or NOT-VALIDATED.
 * @param {string} status - VALIDATION_STATE.INVALID or VALIDATION_STATE.NOT_VALIDATED
 * @param {Function} proceedCallback - Function to call when user clicks "Run"
 */
function showStartValidationCheckDialog(status, proceedCallback) {
    const dialogDiv = document.getElementById('start-validation-check-dialog');
    if (!dialogDiv) {
        console.error('--- [Validate] start-validation-check-dialog element not found');
        proceedCallback();
        return;
    }

    const contentEl = document.getElementById('start-validation-check-content');

    if (status === VALIDATION_STATE.INVALID) {
        contentEl.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 15px;">⚠️</div>
            <h4 style="color: #F59E0B; margin-bottom: 10px;">Validation Errors Found</h4>
            <p style="color: #ccc;">Some errors were found during flow validation. Are you sure you want to start running it?</p>
        `;
    } else {
        contentEl.innerHTML = `
            <div style="font-size: 48px; margin-bottom: 15px;">ℹ️</div>
            <h4 style="color: #3B82F6; margin-bottom: 10px;">Flow Not Validated</h4>
            <p style="color: #ccc;">No validation has been executed for the present flow. Would you like to verify it or start running without verification?</p>
        `;
    }

    const $dialog = $(dialogDiv);
    $dialog.dialog({
        title: status === VALIDATION_STATE.INVALID ? '⚠️ Validation Errors Found' : 'ℹ️ Flow Not Validated',
        autoOpen: true,
        modal: true,
        width: 500,
        resizable: false,
        draggable: true,
        closeOnEscape: true,
        closeText: "",
        dialogClass: "start-validation-check-dialog-wrapper",
        open: function () {
            document.body.style.overflow = 'hidden';
        },
        close: function () {
            document.body.style.overflow = '';
        },
        buttons: [
            {
                text: "Run",
                click: function () {
                    $(this).dialog("close");
                    proceedCallback();
                }
            },
            {
                text: "Verify",
                click: function () {
                    $(this).dialog("close");
                    // Trigger the Validate process
                    runFlowValidation();
                }
            }
        ]
    });

    // Style the buttons
    const buttonPane = $dialog.parent().find('.ui-dialog-buttonpane');
    buttonPane.find('button:contains("Run")').css({
        'background-color': status === VALIDATION_STATE.INVALID ? '#e74c3c' : '#3B82F6',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '100px'
    });
    buttonPane.find('button:contains("Verify")').css({
        'background-color': '#EAB308',
        'color': 'white', 'border': 'none', 'border-radius': '6px',
        'font-size': '1em', 'padding': '8px 30px', 'cursor': 'pointer', 'min-width': '100px'
    });
}

// ========================================
// VALIDATE BUTTON CLICK HANDLER
// ========================================
if (btnValidate) {
    btnValidate.addEventListener('click', async (e) => {
        e.preventDefault();
        console.log('--- Validate button clicked');

        if (btnValidate.disabled) {
            console.log('--- Validate button is disabled, ignoring');
            return;
        }

        btnValidate.disabled = true;
        btnValidate.style.opacity = '0.5';

        try {
            await runFlowValidation();
        } finally {
            updateValidateButtonState();
        }
    });
}

// ========================================
// CANVAS CHANGE OBSERVER — Reset validation on changes
// ========================================

/**
 * Reset validation status when the canvas content changes.
 * This is called from acp-canvas-core.js when agents/connections are added/removed.
 */
function resetFlowValidation() {
    if (flowValidationStatus !== VALIDATION_STATE.NOT_VALIDATED) {
        console.log('--- [Validate] Canvas changed, resetting validation status to NOT-VALIDATED');
        flowValidationStatus = VALIDATION_STATE.NOT_VALIDATED;
    }
    updateValidateButtonState();
}

// Hook into MutationObserver for canvas changes
document.addEventListener('DOMContentLoaded', () => {
    // Canvas items now live inside #canvas-content (the scrollable content layer),
    // so the observer must watch that element — not the outer viewport — to detect
    // add/remove of items.
    const observedEl = document.getElementById('canvas-content')
        || document.getElementById('submonitor-container');
    if (observedEl) {
        const observer = new MutationObserver(() => {
            resetFlowValidation();
            // Also refresh all control button states (e.g. disable all when canvas is empty)
            if (typeof updateControlButtonStates === 'function') {
                updateControlButtonStates();
            }
        });
        observer.observe(observedEl, { childList: true, subtree: false });
    }

    // Initial state
    updateValidateButtonState();
});
