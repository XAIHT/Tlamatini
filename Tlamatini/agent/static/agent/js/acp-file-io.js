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

// Agentic Control Panel - File I/O: Save, Open, Close, Load Diagram
// LOAD ORDER: #9 - Depends on: acp-globals.js, acp-session.js, acp-canvas-core.js,
//                              acp-canvas-undo.js, acp-agent-connectors.js
/* global updatePptxerConnection, updateMouserConnection, updateFileInterpreterConnection, updateImageInterpreterConnection, updateGatewayerConnection, updateGatewayRelayerConnection, updateNodeManagerConnection, updateFileCreatorConnection, updateFileExtractorConnection, updateKyberKeygenConnection, updateKyberCipherConnection, updateKyberDecipherConnection, updateParametrizerConnection, updateFlowBackerConnection, updateBarrierConnection, updateJDecompilerConnection, updateDeCompresserConnection, updateGooglerConnection, updateTeletlamatiniConnection, updateTelegrammerConnection, updateWhatsapperConnection, updateAcpxerConnection, updatePlaywrighterConnection, updateWindowerConnection, updateKalierConnection, updateZavuererConnection, updateStm32erConnection, updateEsp32erConnection, updateEsphomerConnection, updateArduinerConnection, updateMcpDoctorConnection, updateInstantMessagingDoctorConnection, updateCamcorderConnection, updateEditorConnection, updateGrepperConnection, updateGlobberConnection, updateRecorderConnection, updateWhispererConnection, updateAudioPlayerConnection, updateVideoPlayerConnection, updateTalkerConnection, getAgentPurposeForName, setCanvasItemMetadata, getDefaultDiagramSaveFilename, getHeaders */

// ========================================
// SAVE BUTTON
// ========================================

if (saveBtn) {
    saveBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        if (saveBtn.classList.contains('disabled')) return;

        const defaultFilename = typeof getDefaultDiagramSaveFilename === 'function'
            ? getDefaultDiagramSaveFilename()
            : 'diagram';

        let filename = prompt("Enter filename to save:", defaultFilename);
        if (filename === null) return; // User cancelled
        filename = filename.trim();
        if (!filename) return;

        if (!filename.toLowerCase().endsWith('.flw')) {
            filename += '.flw';
        }

        let data;
        if (typeof window.buildACPFlowSnapshot === 'function') {
            data = window.buildACPFlowSnapshot();
        } else {
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
                    agentPurpose: node.dataset.agentPurpose || getAgentPurposeForName(agentName),
                    configData: ACP.nodeConfigs.get(node.id) || null
                });
            });

            const connectionsData = ACP.connections.map(conn => ({
                sourceIndex: nodeMap.get(conn.source),
                targetIndex: nodeMap.get(conn.target),
                inputSlot: conn.inputSlot || 0,
                outputSlot: conn.outputSlot || 0
            }));

            data = { nodes: nodesData, connections: connectionsData };
        }

        // Redact secrets (SMTP/IMAP/DB passwords, API tokens, Kyber private
        // keys, ...) BEFORE the .flw leaves the browser. Save used to Blob the
        // RAW snapshot, so every credential typed into a node dialog shipped in
        // the shared file. The backend masks only secret fields per each agent's
        // contract and preserves the snapshot shape byte-for-byte, so the loader
        // round-trips it losslessly. A failed redaction leaves the flow unsaved
        // and explains the error; raw credentials must never be downloaded.
        try { data = await _redactFlowSnapshotBeforeSave(data); }
        catch (error) { await acpAlert(error.message); return; }

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

/**
 * POST the flow snapshot to the backend so it can mask secret fields (per each
 * agent's contract secret_paths) before the .flw is downloaded. Mirrors the
 * A failed redaction keeps the diagram dirty and reports an actionable error.
 * Raw credentials must never be downloaded as a fallback.
 */
async function _redactFlowSnapshotBeforeSave(flowData) {
    try {
        const response = await fetch('/agent/redact_flow_snapshot/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ flow: flowData })
        });
        const result = await response.json();
        if (response.ok && result.success && result.flow) {
            return result.flow;
        }
        console.warn('--- Save: backend redaction unavailable:', result);
    } catch (err) {
        console.warn('--- Save: backend redaction failed:', err);
    }
    throw new Error('The diagram could not be saved because credential protection is unavailable. Check your connection and sign-in, then try Save again.');
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

        input.onchange = async (event) => {
            const file = event.target.files[0];
            if (!file) return;
            try {
                if (!/\.flw$/i.test(file.name)) throw new Error('Choose a .flw agent flow.');
                if (file.size > 5 * 1024 * 1024) throw new Error('The flow file must be no larger than 5 MiB.');
                const data = JSON.parse((await file.text()).replace(/^\uFEFF/, ''));
                if (await loadDiagram(data, file.name)) updateFilenameDisplay(file.name);
            } catch (err) {
                console.error('Failed to load diagram', err);
                await acpAlert('Could not open diagram: ' + err.message);
            }
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
            const closeApproved = await acpConfirm(
                'Close this diagram?',
                'You have unsaved changes. Closing now discards them.',
                'Unsaved changes');
            if (!closeApproved) {
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
                acpAlert('Failed to clear pool directory: ' + result.message);
                return;
            }

            window.clearAllCanvasItems();
            updateFilenameDisplay(null);
            console.log('--- Diagram closed');

        } catch (error) {
            console.error('--- Error during close operation:', error);
            acpAlert('Error during close operation: ' + error.message);
        }
    });
}

// ========================================
// LOAD DIAGRAM
// ========================================

function getSavedParametrizerMappings(data, nodeData, resolvedNodeId, configData) {
    if (configData && Array.isArray(configData._parametrizer_mappings)) {
        return configData._parametrizer_mappings;
    }
    const artifacts = data && data.artifacts ? data.artifacts : {};
    const stores = [
        artifacts.parametrizerMappings,
        artifacts.parametrizer_mappings,
        artifacts.parametrizerSchemes,
        artifacts.parametrizer_schemes
    ];
    const keys = [resolvedNodeId, nodeData && nodeData.id, nodeData && nodeData.text].filter(Boolean);
    for (const store of stores) {
        if (!store || typeof store !== 'object') continue;
        for (const key of keys) {
            if (Array.isArray(store[key])) return store[key];
        }
    }
    return [];
}

/**
 * Load a diagram from a parsed JSON data object.
 * Clears existing canvas, deploys agents, restores connections.
 * @param {Object} data - Parsed .flw file data
 */
async function loadDiagram(data, filename = 'diagram.flw', { withinEditorOperation = false } = {}) {
    // The built-in example already owns performEdit's busy state. External
    // file opens keep the default and cannot bypass that editing lock.
    const locked = () => ACP.canEdit ? !ACP.canEdit({ withinEditorOperation }) : ACP.fileLoading || (ACP.editorBusy && !withinEditorOperation) || isBusyProcessing || globalRunningState !== GLOBAL_STATE.STOPPED;
    if (locked()) throw new Error('Stop the flow and finish the current operation before opening a diagram.');
    const body = new FormData();
    body.append('file', new Blob([JSON.stringify(data)], { type: 'application/json' }), filename);
    const response = await fetch('/agent/flow_files/validate/', {
        method: 'POST', headers: getHeaders(), credentials: 'same-origin', body
    });
    if (response.redirected) throw new Error('Your session expired. Sign in again before opening a diagram.');
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Invalid .flw file.');
    data = result.flow;
    if (hasUnsavedChanges && !await acpConfirm('Replace this diagram?', 'Unsaved changes will be replaced. Save the diagram first to keep them.', 'Unsaved changes')) return false;
    if (locked()) throw new Error('The flow is busy. Try opening the file again after it stops.');
    ACP.fileLoading = true;
    ACP.refreshEditor?.();
    try {
    // Validate and prepare the session before changing the visible diagram.
    const clearResponse = await fetch('/agent/clear_pool/', {
        method: 'POST', headers: getHeaders(), credentials: 'same-origin'
    });
    const clearResult = await clearResponse.json();
    if (!clearResponse.ok || clearResult.status !== 'success') {
        throw new Error(clearResult.message || 'The previous flow could not be closed. Your diagram was kept.');
    }
    undoManager.clear();
    [...ACP.connections].forEach(conn => removeConnection(conn));
    document.querySelectorAll('.canvas-item').forEach(el => el.remove());
    ACP.selectedItems.clear();

    const loadedNodes = [];

    // 5. Recreate nodes
    ACP.itemCounters.clear();
    ACP.nodeConfigs.clear();
    // Saved IDs can have gaps after deletions. Preserve them so config references
    // still point to the same agent, and reserve their numbers before adding any
    // legacy nodes without IDs or creating future nodes on the canvas.
    function savedRegistration(node) {
        const base = node.text.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
        const prefix = base + '-', id = node.id;
        if (typeof id !== 'string' || !id.startsWith(prefix)) return null;
        const suffix = id.slice(prefix.length), count = Number(suffix);
        return /^[1-9]\d*$/.test(suffix) && Number.isSafeInteger(count) && count < 1000000000
            ? { id, count, baseName: base } : null;
    }
    for (const node of data.nodes) {
        const saved = savedRegistration(node);
        if (saved) ACP.itemCounters.set(saved.baseName, Math.max(ACP.itemCounters.get(saved.baseName) || 0, saved.count));
    }

    if (data.nodes && Array.isArray(data.nodes)) {
        for (const nodeData of data.nodes) {
            const lowerName = nodeData.text.toLowerCase();

            // Enforce single FlowCreator/FlowHypervisor rule during file load
            if (lowerName === 'flowcreator') {
                const existing = loadedNodes.find(n => (n.dataset.agentName || '').toLowerCase() === 'flowcreator');
                if (existing) {
                    console.warn(`[Load] Skipping extra FlowCreator agent: ${nodeData.text}`);
                    acpAlert('Only one FlowCreator agent is allowed per flow. Extra instances have been removed from the loaded diagram.');
                    continue;
                }
            } else if (lowerName === 'flowhypervisor') {
                const existing = loadedNodes.find(n => (n.dataset.agentName || '').toLowerCase() === 'flowhypervisor');
                if (existing) {
                    console.warn(`[Load] Skipping extra FlowHypervisor agent: ${nodeData.text}`);
                    acpAlert('Only one FlowHypervisor agent is allowed per flow. Extra instances have been removed from the loaded diagram.');
                    continue;
                }
            }

            const newItem = document.createElement('div');
            newItem.classList.add('canvas-item');

            let agentText = nodeData.text;

            // Clean up old saved data
            if (lowerName === 'flowcreator') {
                agentText = 'Flowcreator';
                newItem.textContent = agentText;
                newItem.id = 'flowcreator';
            } else if (lowerName === 'flowhypervisor') {
                agentText = 'FlowHypervisor';
                newItem.textContent = agentText;
                newItem.id = 'flowhypervisor';
            } else {
                const registration = savedRegistration(nodeData) || registerItem(agentText);
                newItem.textContent = `${agentText} (${registration.count})`;
                newItem.id = registration.id;
            }
            setCanvasItemMetadata(
                newItem,
                agentText,
                nodeData.agentPurpose || getAgentPurposeForName(agentText)
            );

            applyAgentTypeClass(newItem, lowerName);
            appendInputTriangles(newItem, lowerName);
            appendOutputTriangles(newItem, lowerName);
            appendLedIndicator(newItem);

            newItem.style.left = nodeData.left;
            newItem.style.top = nodeData.top;

            canvasContent.appendChild(newItem);
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
                        if (lowerName === 'parametrizer') {
                            const mappings = getSavedParametrizerMappings(data, nodeData, newItem.id, nodeData.configData);
                            if (mappings.length > 0) {
                                await fetch(`/agent/save_parametrizer_scheme/${newItem.id}/`, {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json', ...getHeaders() },
                                    credentials: 'same-origin',
                                    body: JSON.stringify({ mappings })
                                });
                                ACP.nodeConfigs.set(newItem.id, {
                                    ...(ACP.nodeConfigs.get(newItem.id) || {}),
                                    _parametrizer_mappings: mappings
                                });
                            }
                        }
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
        // Grow #canvas-content first so far-flung items are scrollable, then redraw
        // connections against the final, settled layout.
        updateCanvasContentSize();
        loadedNodes.forEach(node => updateAttachedConnections(node));
    }, 200);

    // Initial resize so scrollbars appear immediately, before the settled redraw.
    updateCanvasContentSize();
    updateSaveButtonState();
    markClean();
    return true;
    } finally {
        ACP.fileLoading = false;
        ACP.refreshEditor?.();
    }
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
        // Parametrizer's mapping dialog can save only _parametrizer_mappings.
        // That artifact is not a saved target list: the visible edge must still
        // restore its runtime wiring. Explicit saved lists remain authoritative.
        const sourceConfig = ACP.nodeConfigs.get(sourceId);
        if (sourceConfig && (sourceAgentName !== 'parametrizer' || Object.prototype.hasOwnProperty.call(sourceConfig, 'target_agents'))) {
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
            if (sourceAgentName === 'counter') {
                if (outputSlot === 1) {
                    await updateCounterConnection(sourceId, 'target_l', targetId, 'add');
                } else if (outputSlot === 2) {
                    await updateCounterConnection(sourceId, 'target_g', targetId, 'add');
                } else {
                    console.warn(`[Restore] Counter output slot invalid: ${outputSlot}`);
                }
            }

            switch (sourceAgentName) {
                case 'notifier': await updateNotifierConnection(sourceId, 'target', targetId, 'add'); break;
                case 'recmailer': await updateRecmailerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'emailer': await updateEmailerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'executer': await updateExecuterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'sleeper': await updateSleeperConnection(sourceId, targetId, 'add', 'target'); break;
                case 'shoter': await updateShoterConnection(sourceId, targetId, 'add'); break;
                case 'camcorder': await updateCamcorderConnection(sourceId, targetId, 'add'); break;
                case 'globber': await updateGlobberConnection(sourceId, targetId, 'add'); break;
                case 'grepper': await updateGrepperConnection(sourceId, targetId, 'add'); break;
                case 'editor': await updateEditorConnection(sourceId, targetId, 'add'); break;
                case 'recorder': await updateRecorderConnection(sourceId, targetId, 'add'); break;
                case 'whisperer': await updateWhispererConnection(sourceId, targetId, 'add'); break;
                case 'audioplayer': await updateAudioPlayerConnection(sourceId, targetId, 'add'); break;
                case 'videoplayer': await updateVideoPlayerConnection(sourceId, targetId, 'add'); break;
                case 'talker': await updateTalkerConnection(sourceId, targetId, 'add'); break;
                case 'deleter': await updateDeleterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'mover': await updateMoverConnection(sourceId, targetId, 'add', 'target'); break;
                case 'pythonxer': await updatePythonxerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'cleaner': await updateCleanerConnection(sourceId, 'target', targetId, 'add'); break;
                case 'croner': await updateCronerConnection(sourceId, 'target', targetId, 'add'); break;
                case 'stopper': await updateStopperConnection(sourceId, 'output', targetId, 'add'); break;
                case 'ssher': await updateSsherConnection(sourceId, targetId, 'add', 'target'); break;
                case 'scper': await updateScperConnection(sourceId, targetId, 'add', 'target'); break;
                case 'telegrammer': await updateTelegrammerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'whatsapper': await updateWhatsapperConnection(sourceId, targetId, 'add', 'target'); break;
                case 'raiser': await updateRaiserConnection(sourceId, 'target', targetId, 'add'); break;
                case 'starter': await updateStarterConnection(sourceId, targetId, 'add'); break;
                case 'ender': await updateEnderConnection(sourceId, targetNode, 'add', 'output'); break;
                case 'or': await updateOrAgentConnection(sourceId, 'target', targetId, 'add'); break;
                case 'and': await updateAndAgentConnection(sourceId, 'target', targetId, 'add'); break;
                case 'gitter': await updateGitterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'dockerer': await updateDockererConnection(sourceId, targetId, 'add', 'target'); break;
                case 'mcp doctor':
                case 'mcp-doctor': await updateMcpDoctorConnection(sourceId, targetId, 'add', 'target'); break;
                case 'instant messaging doctor':
                case 'instant-messaging-doctor': await updateInstantMessagingDoctorConnection(sourceId, targetId, 'add', 'target'); break;
                case 'pser': await updatePserConnection(sourceId, targetId, 'add', 'target'); break;
                case 'kuberneter': await updateKuberneterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'apirer': await updateApirerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'unrealer': await updateUnrealerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'blenderer': await updateBlendererConnection(sourceId, targetId, 'add', 'target'); break;
                case 'playwrighter': await updatePlaywrighterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'reviewer': await updateReviewerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'analyzer': await updateAnalyzerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'jenkinser': await updateJenkinserConnection(sourceId, targetId, 'add', 'target'); break;
                case 'crawler': await updateCrawlerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'summarizer': await updateSummarizerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'mouser': await updateMouserConnection(sourceId, targetId, 'add'); break;
                case 'windower': await updateWindowerConnection(sourceId, targetId, 'add'); break;
                case 'discoverer': await updateDiscovererConnection(sourceId, targetId, 'add'); break;
                case 'nmapper': await updateNmapperConnection(sourceId, targetId, 'add'); break;
                case 'pptxer': await updatePptxerConnection(sourceId, targetId, 'add'); break;
                case 'pdfer': await updatePdferConnection(sourceId, targetId, 'add'); break;
                case 'latexer': await updateLatexerConnection(sourceId, targetId, 'add'); break;
                case 'kalier': await updateKalierConnection(sourceId, targetId, 'add'); break;
                case 'zavuerer': await updateZavuererConnection(sourceId, targetId, 'add'); break;
                case 'stm32er': await updateStm32erConnection(sourceId, targetId, 'add'); break;
                case 'esp32er': await updateEsp32erConnection(sourceId, targetId, 'add'); break;
                case 'esphomer': await updateEsphomerConnection(sourceId, targetId, 'add'); break;
                case 'arduiner': await updateArduinerConnection(sourceId, targetId, 'add'); break;
                case 'file-interpreter': await updateFileInterpreterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'image-interpreter': await updateImageInterpreterConnection(sourceId, targetId, 'add', 'target'); break;
                case 'video-analyzer': await updateVideoAnalyzerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'netspeed-calculator': await updateNetSpeedCalculatorConnection(sourceId, targetId, 'add', 'target'); break;
                case 'gatewayer': await updateGatewayerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'gateway relayer':
                case 'gateway-relayer': await updateGatewayRelayerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'node manager':
                case 'node-manager': await updateNodeManagerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'file-creator': await updateFileCreatorConnection(sourceId, targetId, 'add', 'target'); break;
                case 'file-extractor': await updateFileExtractorConnection(sourceId, targetId, 'add', 'target'); break;
                case 'kyber-keygen': await updateKyberKeygenConnection(sourceId, targetId, 'add', 'target'); break;
                case 'kyber-cipher': await updateKyberCipherConnection(sourceId, targetId, 'add', 'target'); break;
                case 'kyber-decipher': await updateKyberDecipherConnection(sourceId, targetId, 'add', 'target'); break;
                case 'flowbacker': await updateFlowBackerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'barrier': await updateBarrierConnection(sourceId, targetId, 'add', 'target'); break;
                case 'j-decompiler': await updateJDecompilerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'de-compresser': await updateDeCompresserConnection(sourceId, targetId, 'add', 'target'); break;
                case 'parametrizer': await updateParametrizerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'googler': await updateGooglerConnection(sourceId, targetId, 'add', 'target'); break;
                case 'teletlamatini': await updateTeletlamatiniConnection(sourceId, targetId, 'add', 'target'); break;
                case 'acpxer': await updateAcpxerConnection(sourceId, targetId, 'add', 'target'); break;
            }
        }

        // --- TARGET-SIDE UPDATES ---
        // Same rule: if the target node has saved configData, trust it and skip.
        const targetConfig = ACP.nodeConfigs.get(targetId);
        if (targetConfig && (targetAgentName !== 'parametrizer' || Object.prototype.hasOwnProperty.call(targetConfig, 'source_agents'))) {
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
                case 'counter': await updateCounterConnection(targetId, 'source', sourceId, 'add'); break;
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
                case 'whatsapper': await updateWhatsapperConnection(targetId, sourceId, 'add', 'source'); break;
                case 'telegrammer': await updateTelegrammerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'raiser': await updateRaiserConnection(targetId, 'source', sourceId, 'add'); break;
                case 'ender': await updateEnderConnection(targetId, sourceNode, 'add', 'input'); break;
                case 'monitor-log': await updateMonitorLogConnection(targetId, sourceId, 'add'); break;
                case 'ssher': await updateSsherConnection(targetId, sourceId, 'add', 'source'); break;
                case 'scper': await updateScperConnection(targetId, sourceId, 'add', 'source'); break;
                case 'gitter': await updateGitterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'dockerer': await updateDockererConnection(targetId, sourceId, 'add', 'source'); break;
                case 'mcp doctor':
                case 'mcp-doctor': await updateMcpDoctorConnection(targetId, sourceId, 'add', 'source'); break;
                case 'instant messaging doctor':
                case 'instant-messaging-doctor': await updateInstantMessagingDoctorConnection(targetId, sourceId, 'add', 'source'); break;
                case 'pser': await updatePserConnection(targetId, sourceId, 'add', 'source'); break;
                case 'kuberneter': await updateKuberneterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'apirer': await updateApirerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'unrealer': await updateUnrealerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'blenderer': await updateBlendererConnection(targetId, sourceId, 'add', 'source'); break;
                case 'playwrighter': await updatePlaywrighterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'reviewer': await updateReviewerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'analyzer': await updateAnalyzerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'jenkinser': await updateJenkinserConnection(targetId, sourceId, 'add', 'source'); break;
                case 'crawler': await updateCrawlerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'summarizer': await updateSummarizerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'file-interpreter': await updateFileInterpreterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'image-interpreter': await updateImageInterpreterConnection(targetId, sourceId, 'add', 'source'); break;
                case 'video-analyzer': await updateVideoAnalyzerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'netspeed-calculator': await updateNetSpeedCalculatorConnection(targetId, sourceId, 'add', 'source'); break;
                case 'gatewayer': await updateGatewayerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'gateway relayer':
                case 'gateway-relayer': await updateGatewayRelayerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'node manager':
                case 'node-manager': await updateNodeManagerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'file-creator': await updateFileCreatorConnection(targetId, sourceId, 'add', 'source'); break;
                case 'file-extractor': await updateFileExtractorConnection(targetId, sourceId, 'add', 'source'); break;
                case 'kyber-keygen': await updateKyberKeygenConnection(targetId, sourceId, 'add', 'source'); break;
                case 'kyber-cipher': await updateKyberCipherConnection(targetId, sourceId, 'add', 'source'); break;
                case 'kyber-decipher': await updateKyberDecipherConnection(targetId, sourceId, 'add', 'source'); break;
                case 'flowbacker': await updateFlowBackerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'barrier': await updateBarrierConnection(targetId, sourceId, 'add', 'source'); break;
                case 'j-decompiler': await updateJDecompilerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'de-compresser': await updateDeCompresserConnection(targetId, sourceId, 'add', 'source'); break;
                case 'parametrizer': await updateParametrizerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'googler': await updateGooglerConnection(targetId, sourceId, 'add', 'source'); break;
                case 'teletlamatini': await updateTeletlamatiniConnection(targetId, sourceId, 'add', 'source'); break;
                case 'acpxer': await updateAcpxerConnection(targetId, sourceId, 'add', 'source'); break;
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
    // Retire the old global, cross-user single-slot handoff without consuming it.
    for (const key of ['pendingFlwData', 'pendingFlwFilename', 'pendingFlwTimestamp']) {
        try { localStorage.removeItem(key); } catch (_) { /* Storage may be disabled. */ }
    }
    const incoming = document.getElementById('server-flw-data');
    const error = document.getElementById('flow-open-error');
    if (!incoming && !error) return;
    const address = new URL(window.location.href);
    address.searchParams.delete('open'); history.replaceState(null, '', address);
    if (error) { acpAlert(JSON.parse(error.textContent)); return; }
    // Let the canvas and session initialize before deploying saved configurations.
    setTimeout(async () => {
        try {
            const filename = JSON.parse(document.getElementById('server-flw-filename').textContent);
            if (await loadDiagram(JSON.parse(incoming.textContent), filename)) {
                updateFilenameDisplay(filename);
            }
        } catch (error) { await acpAlert('Could not open diagram: ' + error.message); }
    }, 500);
});
