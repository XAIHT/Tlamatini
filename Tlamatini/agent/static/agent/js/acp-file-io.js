// Agentic Control Panel - File I/O: Save, Open, Close, Load Diagram
// LOAD ORDER: #9 - Depends on: acp-globals.js, acp-session.js, acp-canvas-core.js,
//                              acp-canvas-undo.js, acp-agent-connectors.js

// ========================================
// SAVE BUTTON
// ========================================

if (saveBtn) {
    saveBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (saveBtn.classList.contains('disabled')) return;

        let filename = prompt("Enter filename to save:", "diagram");
        if (filename === null) return; // User cancelled

        if (!filename.toLowerCase().endsWith('.flw')) {
            filename += '.flw';
        }

        const nodes = Array.from(document.querySelectorAll('.canvas-item'));
        const nodeMap = new Map();
        const nodesData = [];

        nodes.forEach((node, index) => {
            nodeMap.set(node, index);
            const agentName = node.dataset.agentName || node.firstChild.textContent;
            nodesData.push({
                text: agentName,
                left: node.style.left,
                top: node.style.top,
                configData: ACP.nodeConfigs.get(node.id) || null
            });
        });

        const connectionsData = ACP.connections.map(conn => ({
            sourceIndex: nodeMap.get(conn.source),
            targetIndex: nodeMap.get(conn.target),
            inputSlot: conn.inputSlot || 0,
            outputSlot: conn.outputSlot || 0
        }));

        const data = { nodes: nodesData, connections: connectionsData };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        updateFilenameDisplay(filename);
        markClean();
    });
}

// ========================================
// OPEN BUTTON
// ========================================

if (openBtn) {
    openBtn.addEventListener('click', (e) => {
        e.preventDefault();
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.flw';

        input.onchange = (event) => {
            const file = event.target.files[0];
            if (!file) return;

            const reader = new FileReader();
            reader.onload = (ev) => {
                try {
                    const data = JSON.parse(ev.target.result);
                    loadDiagram(data);
                    updateFilenameDisplay(file.name);
                } catch (err) {
                    console.error("Failed to load diagram", err);
                    alert("Error loading diagram file.");
                }
            };
            reader.readAsText(file);
        };
        input.click();
    });
}

// ========================================
// CLOSE BUTTON
// ========================================

if (fileCloseBtn) {
    fileCloseBtn.addEventListener('click', async (e) => {
        e.preventDefault();

        if (hasUnsavedChanges) {
            if (!confirm('You have unsaved changes. Are you sure you want to close the current diagram?')) {
                return;
            }
        }

        try {
            const response = await fetch('/agent/clear_pool/', {
                method: 'POST',
                headers: getHeaders(),
                credentials: 'same-origin'
            });

            const result = await response.json();
            if (result.status === 'success') {
                console.log('--- Pool directory cleared successfully');
            } else {
                console.error('--- Failed to clear pool directory:', result.message);
                alert('Failed to clear pool directory: ' + result.message);
                return;
            }

            window.clearAllCanvasItems();
            updateFilenameDisplay(null);
            console.log('--- Diagram closed');

        } catch (error) {
            console.error('--- Error during close operation:', error);
            alert('Error during close operation: ' + error.message);
        }
    });
}

// ========================================
// LOAD DIAGRAM
// ========================================

/**
 * Load a diagram from a parsed JSON data object.
 * Clears existing canvas, deploys agents, restores connections.
 * @param {Object} data - Parsed .flw file data
 */
async function loadDiagram(data) {
    // 1. Clear existing connections
    [...ACP.connections].forEach(conn => removeConnection(conn));

    // 2. Clear existing nodes
    document.querySelectorAll('.canvas-item').forEach(el => el.remove());

    // 3. Clear selection
    ACP.selectedItems.clear();

    // 4. Clear pool directory before deploying new agents
    try {
        const clearResponse = await fetch('/agent/clear_pool/', {
            method: 'POST',
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        const clearResult = await clearResponse.json();
        if (clearResult.status === 'success') {
            console.log('--- Pool directory cleared before loading diagram');
        } else {
            console.warn('--- Could not clear pool directory:', clearResult.message);
        }
    } catch (error) {
        console.warn('--- Error clearing pool directory:', error);
    }

    const loadedNodes = [];

    // 5. Recreate nodes
    ACP.itemCounters.clear();
    ACP.nodeConfigs.clear();

    if (data.nodes && Array.isArray(data.nodes)) {
        for (const nodeData of data.nodes) {
            const lowerName = nodeData.text.toLowerCase();

            // Enforce single FlowCreator rule during file load
            if (lowerName === 'flowcreator') {
                const existing = loadedNodes.find(n => (n.dataset.agentName || '').toLowerCase() === 'flowcreator');
                if (existing) {
                    console.warn(`[Load] Skipping extra FlowCreator agent: ${nodeData.text}`);
                    alert('Only one FlowCreator agent is allowed per flow. Extra instances have been removed from the loaded diagram.');
                    continue;
                }
            }

            const newItem = document.createElement('div');
            newItem.classList.add('canvas-item');

            let agentText = nodeData.text;

            // Clean up old Flowcreator (1) saved data
            if (lowerName === 'flowcreator') {
                agentText = 'Flowcreator';
                newItem.textContent = agentText;
                newItem.id = 'flowcreator';
                newItem.dataset.agentName = agentText;
            } else {
                const registration = registerItem(agentText);
                newItem.textContent = `${agentText} (${registration.count})`;
                newItem.id = registration.id;
                newItem.dataset.agentName = agentText;
            }

            applyAgentTypeClass(newItem, lowerName);
            appendInputTriangles(newItem, lowerName);
            appendOutputTriangles(newItem, lowerName);
            appendLedIndicator(newItem);

            newItem.style.left = nodeData.left;
            newItem.style.top = nodeData.top;

            submonitor.appendChild(newItem);
            makeDraggable(newItem);

            // Deploy agent to pool directory
            try {
                if (nodeData.configData) {
                    // Sanitize Ender config: never allow cleaners in source_agents
                    if (lowerName === 'ender' &&
                        nodeData.configData.source_agents &&
                        Array.isArray(nodeData.configData.source_agents)) {

                        const oldLen = nodeData.configData.source_agents.length;
                        nodeData.configData.source_agents = nodeData.configData.source_agents.filter(
                            agName => !agName.toLowerCase().includes('cleaner')
                        );
                        if (nodeData.configData.source_agents.length !== oldLen) {
                            console.warn('--- Sanitized Ender config: Removed cleaner(s) from source_agents.');
                        }
                    }

                    ACP.nodeConfigs.set(newItem.id, nodeData.configData);

                    const response = await fetch(`/agent/save_agent_config/${newItem.id}/`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', ...getHeaders() },
                        credentials: 'same-origin',
                        body: JSON.stringify(nodeData.configData)
                    });
                    if (response.ok) {
                        const result = await response.json();
                        console.log(`--- Deployed agent ${newItem.id} with saved config:`, result.path);
                    } else {
                        console.error(`--- Failed to deploy agent ${newItem.id}:`, response.statusText);
                    }
                } else {
                    const response = await fetch(`/agent/deploy_agent_template/${newItem.id}/`, {
                        method: 'POST',
                        headers: getHeaders(),
                        credentials: 'same-origin'
                    });
                    if (response.ok) {
                        const result = await response.json();
                        console.log(`--- Deployed agent template ${newItem.id}:`, result.path);
                    } else {
                        console.error(`--- Failed to deploy template ${newItem.id}:`, response.statusText);
                    }
                }
            } catch (error) {
                console.error(`--- Error deploying agent ${newItem.id}:`, error);
            }

            loadedNodes.push(newItem);
        }
    }

    // 6. Recreate connections
    if (data.connections && Array.isArray(data.connections)) {
        console.log(`[Load] Restoring ${data.connections.length} connections...`);
        for (const connData of data.connections) {
            if (connData.sourceIndex !== undefined && connData.targetIndex !== undefined) {
                const sourceNode = loadedNodes[connData.sourceIndex];
                const targetNode = loadedNodes[connData.targetIndex];

                if (sourceNode && targetNode) {
                    try {
                        const startPos = getCenter(sourceNode);
                        const endPos = getCenter(targetNode);
                        const created = createConnectionGroup();
                        setPathD(startPos.x, startPos.y, endPos.x, endPos.y, created.visiblePath, created.hitPath);

                        const newConn = {
                            source: sourceNode,
                            target: targetNode,
                            path: created.group,
                            visiblePath: created.visiblePath,
                            hitPath: created.hitPath,
                            inputSlot: parseInt(connData.inputSlot) || 0,
                            outputSlot: parseInt(connData.outputSlot) || 0
                        };
                        ACP.connections.push(newConn);

                        await restoreAgentConnection(sourceNode, targetNode, connData);

                    } catch (err) {
                        console.error(`[Load] Error creating connection between ${connData.sourceIndex} and ${connData.targetIndex}:`, err);
                    }
                } else {
                    console.warn(`[Load] Skipping connection: node not found. Src:${connData.sourceIndex}, Tgt:${connData.targetIndex}`);
                }
            }
        }
        console.log('[Load] Finished connection restoration.');
    }

    // 7. Force layout update after DOM rendering
    setTimeout(() => {
        console.log('--- [Load] Performing final connection layout update...');
        loadedNodes.forEach(node => updateAttachedConnections(node));
    }, 200);

    updateSaveButtonState();
    markClean();
}

// ========================================
// CONNECTION RESTORATION HELPER
// ========================================

/**
 * Restore all agent-specific backend configuration for a single connection during load.
 * @param {HTMLElement} sourceNode
 * @param {HTMLElement} targetNode
 * @param {Object} connData - Connection data with inputSlot/outputSlot
 */
async function restoreAgentConnection(sourceNode, targetNode, connData) {
    const sourceAgentName = (sourceNode.dataset.agentName || '').toLowerCase();
    const targetAgentName = (targetNode.dataset.agentName || '').toLowerCase();
    const sourceId = sourceNode.id;
    const targetId = targetNode.id;
    const inputSlot = parseInt(connData.inputSlot) || 0;
    const outputSlot = parseInt(connData.outputSlot) || 0;

    console.log(`[Restore] ${sourceAgentName}(${sourceId}) -> ${targetAgentName}(${targetId}) [In=${inputSlot}, Out=${outputSlot}]`);

    try {
        // --- SOURCE-SIDE UPDATES ---
        // If the source node has saved configData it was already fully deployed in step 5.
        // Never let connection-restoration overwrite what the user explicitly saved.
        if (ACP.nodeConfigs.has(sourceId)) {
            console.log(`[Restore] ${sourceAgentName}(${sourceId}) has saved configData — skipping source-side update.`);
        } else {
            // Asker/Forker output slots (A/B)
            if (sourceAgentName === 'asker') {
                if (outputSlot === 1) {
                    await updateAskerConnection(sourceId, 'target_a', targetId, 'add');
                } else if (outputSlot === 2) {
                    await updateAskerConnection(sourceId, 'target_b', targetId, 'add');
                } else {
                    console.warn(`[Restore] Asker output slot invalid: ${outputSlot}`);
                }
            }
            if (sourceAgentName === 'forker') {
                if (outputSlot === 1) {
                    await updateForkerConnection(sourceId, 'target_a', targetId, 'add');
                } else if (outputSlot === 2) {
                    await updateForkerConnection(sourceId, 'target_b', targetId, 'add');
                } else {
                    console.warn(`[Restore] Forker output slot invalid: ${outputSlot}`);
                }
            }

            switch (sourceAgentName) {
                case 'notifier': await updateNotifierConnection(sourceId, 'target', targetId, 'add'); break;
                case 'recmailer': await updateRecmailerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'emailer': await updateEmailerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'executer': await updateExecuterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'sleeper': await updateSleeperConnection(sourceId, targetId, 'add', 'target'); break;
                case 'shoter': await updateShoterConnection(sourceId, targetId, 'add'); break;
                case 'deleter': await updateDeleterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'mover': await updateMoverConnection(sourceId, targetId, 'add', 'target'); break;
                case 'pythonxer': await updatePythonxerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'cleaner': await updateCleanerConnection(sourceId, 'target', targetId, 'add'); break;
                case 'croner': await updateCronerConnection(sourceId, 'target', targetId, 'add'); break;
                case 'stopper': await updateStopperConnection(sourceId, 'output', targetId, 'add'); break;
                case 'ssher': await updateSsherConnection(sourceId, targetId, 'add', 'target'); break;
                case 'scper': await updateScperConnection(sourceId, targetId, 'add', 'target'); break;
                case 'telegramer': await updateTelegramerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'raiser': await updateRaiserConnection(sourceId, 'target', targetId, 'add'); break;
                case 'starter': await updateStarterConnection(sourceId, targetId, 'add'); break;
                case 'ender': await updateEnderConnection(sourceId, targetNode, 'add', 'output'); break;
                case 'or': await updateOrAgentConnection(sourceId, 'target', targetId, 'add'); break;
                case 'and': await updateAndAgentConnection(sourceId, 'target', targetId, 'add'); break;
                case 'gitter': await updateGitterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'dockerer': await updateDockererConnection(sourceId, targetId, 'add', 'target'); break;
                case 'pser': await updatePserConnection(sourceId, targetId, 'add', 'target'); break;
                case 'kuberneter': await updateKuberneterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'apirer': await updateApirerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'jenkinser': await updateJenkinserConnection(sourceId, targetId, 'add', 'target'); break;
                case 'crawler': await updateCrawlerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'summarizer': await updateSummarizerConnection(sourceId, targetId, 'add', 'target'); break;
            }
        }

        // --- TARGET-SIDE UPDATES ---
        // Same rule: if the target node has saved configData, trust it and skip.
        if (ACP.nodeConfigs.has(targetId)) {
            console.log(`[Restore] ${targetAgentName}(${targetId}) has saved configData — skipping target-side update.`);
        } else {
            // OR/AND need slot-specific calls
            if (targetAgentName === 'or') {
                const slot = inputSlot === 1 ? 'source_1' : (inputSlot === 2 ? 'source_2' : null);
                if (slot) await updateOrAgentConnection(targetId, slot, sourceId, 'add');
            }
            if (targetAgentName === 'and') {
                const slot = inputSlot === 1 ? 'source_1' : (inputSlot === 2 ? 'source_2' : null);
                if (slot) await updateAndAgentConnection(targetId, slot, sourceId, 'add');
            }

            switch (targetAgentName) {
                case 'asker': await updateAskerConnection(targetId, 'source', sourceId, 'add'); break;
                case 'forker': await updateForkerConnection(targetId, 'source', sourceId, 'add'); break;
                case 'notifier': await updateNotifierConnection(targetId, 'source', sourceId, 'add'); break;
                case 'recmailer': await updateRecmailerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'emailer': await updateEmailerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'executer': await updateExecuterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'sleeper': await updateSleeperConnection(targetId, sourceId, 'add', 'source'); break;
                case 'deleter': await updateDeleterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'mover': await updateMoverConnection(targetId, sourceId, 'add', 'source'); break;
                case 'pythonxer': await updatePythonxerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'cleaner': await updateCleanerConnection(targetId, 'source', sourceId, 'add'); break;
                case 'croner': await updateCronerConnection(targetId, 'source', sourceId, 'add'); break;
                case 'stopper': await updateStopperConnection(targetId, 'source', sourceId, 'add'); break;
                case 'whatsapper': await updateWhatsapperConnection(targetId, 'source', sourceId, 'add'); break;
                case 'telegramrx': await updateTelegramrxConnection(targetId, sourceId, 'add', 'source'); break;
                case 'telegramer': await updateTelegramerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'raiser': await updateRaiserConnection(targetId, 'source', sourceId, 'add'); break;
                case 'ender': await updateEnderConnection(targetId, sourceNode, 'add', 'input'); break;
                case 'monitor-log': await updateMonitorLogConnection(targetId, sourceId, 'add'); break;
                case 'ssher': await updateSsherConnection(targetId, sourceId, 'add', 'source'); break;
                case 'scper': await updateScperConnection(targetId, sourceId, 'add', 'source'); break;
                case 'gitter': await updateGitterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'dockerer': await updateDockererConnection(targetId, sourceId, 'add', 'source'); break;
                case 'pser': await updatePserConnection(targetId, sourceId, 'add', 'source'); break;
                case 'kuberneter': await updateKuberneterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'apirer': await updateApirerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'jenkinser': await updateJenkinserConnection(targetId, sourceId, 'add', 'source'); break;
                case 'crawler': await updateCrawlerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'summarizer': await updateSummarizerConnection(targetId, sourceId, 'add', 'source'); break;
            }
        }

    } catch (error) {
        console.error(`[Restore] Failed to restore connection ${sourceId}->${targetId}:`, error);
    }
}

// ========================================
// PAGE LIFECYCLE: LOAD PENDING FLW DATA
// ========================================

document.addEventListener('DOMContentLoaded', () => {
    let pendingData = null;
    let pendingFilename = null;

    // Source 1: Server-injected data via Django json_script tags
    const serverFlwDataEl = document.getElementById('server-flw-data');
    const serverFlwFilenameEl = document.getElementById('server-flw-filename');
    if (serverFlwDataEl) {
        try {
            pendingData = JSON.parse(serverFlwDataEl.textContent);
            pendingFilename = serverFlwFilenameEl ? JSON.parse(serverFlwFilenameEl.textContent) : null;
            console.log('--- [FLW] Found server-injected flow data for auto-load:', pendingFilename);
        } catch (err) {
            console.error('--- [FLW] Failed to parse server-injected flow data:', err);
        }
    }

    // Source 2: localStorage (from agent_page.html Open menu)
    if (!pendingData) {
        const storedData = localStorage.getItem('pendingFlwData');
        const storedFilename = localStorage.getItem('pendingFlwFilename');
        const storedTimestamp = localStorage.getItem('pendingFlwTimestamp');

        if (storedData) {
            let isFresh = false;
            if (storedTimestamp) {
                const now = Date.now();
                const ts = parseInt(storedTimestamp, 10);
                if (!isNaN(ts) && (now - ts < 30000)) {
                    isFresh = true;
                } else {
                    console.warn('--- [FLW] Ignoring stale pending flow data:', storedFilename);
                }
            } else {
                console.warn('--- [FLW] Ignoring pending flow data without timestamp:', storedFilename);
            }

            if (isFresh) {
                try {
                    pendingData = JSON.parse(storedData);
                    pendingFilename = storedFilename;
                    console.log('--- [FLW] Found fresh pending flow data in localStorage:', pendingFilename);
                } catch (err) {
                    console.error('--- [FLW] Failed to parse localStorage flow data:', err);
                }
            }

            localStorage.removeItem('pendingFlwData');
            localStorage.removeItem('pendingFlwFilename');
            localStorage.removeItem('pendingFlwTimestamp');
        }
    }

    if (pendingData) {
        setTimeout(async () => {
            console.log('--- [FLW] Loading pending flow data...');
            await loadDiagram(pendingData);
            if (pendingFilename) {
                updateFilenameDisplay(pendingFilename);
            }
            console.log('--- [FLW] Loaded flow file: ' + (pendingFilename || 'unknown'));
        }, 500);
    }
});

