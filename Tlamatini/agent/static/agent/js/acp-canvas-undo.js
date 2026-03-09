// Agentic Control Panel - Canvas Undo/Redo Helpers & Keyboard Handler
// LOAD ORDER: #8 - Depends on: acp-globals.js, acp-session.js, acp-undo-manager.js,
//                              acp-agent-connectors.js, acp-canvas-core.js

// ========================================
// CAPTURE HELPERS (read-only snapshots)
// ========================================

/**
 * Capture the state of a canvas item for undo/redo.
 * @param {HTMLElement} item - The canvas item DOM element
 * @returns {Object} Serializable state object
 */
function captureItemState(item) {
    return {
        id: item.id,
        agentName: item.dataset.agentName || '',
        displayText: item.textContent.trim(),
        position: {
            x: parseFloat(item.style.left) || 0,
            y: parseFloat(item.style.top) || 0
        },
        classes: Array.from(item.classList)
    };
}

/**
 * Capture the state of a connection for undo/redo.
 * @param {Object} conn - Connection object with source, target, path, etc.
 * @returns {Object} Serializable state object
 */
function captureConnectionState(conn) {
    return {
        sourceId: conn.source.id,
        targetId: conn.target.id,
        inputSlot: conn.inputSlot || 0,
        outputSlot: conn.outputSlot || 0
    };
}

/**
 * Find all connections related to a set of items being deleted.
 * @param {Array<HTMLElement>} items - Canvas items being deleted
 * @returns {Array<Object>} Connection state objects
 */
function captureRelatedConnections(items) {
    const itemIds = new Set(items.map(item => item.id));
    const capturedConns = [];
    for (const conn of ACP.connections) {
        if (itemIds.has(conn.source.id) || itemIds.has(conn.target.id)) {
            capturedConns.push(captureConnectionState(conn));
        }
    }
    return capturedConns;
}

// ========================================
// ITEM RESTORATION (Undo Delete)
// ========================================

/**
 * Recreate a canvas item from captured state (for undo delete).
 * @param {Object} state - The captured item state
 * @returns {HTMLElement} The recreated DOM element
 */
async function recreateCanvasItem(state) {
    const newItem = document.createElement('div');
    newItem.className = state.classes.join(' ');
    newItem.id = state.id;
    newItem.dataset.agentName = state.agentName;
    newItem.textContent = state.displayText;

    const agentName = state.agentName.toLowerCase();
    appendInputTriangles(newItem, agentName);
    appendOutputTriangles(newItem, agentName);
    appendLedIndicator(newItem);

    newItem.style.left = state.position.x + 'px';
    newItem.style.top = state.position.y + 'px';

    submonitor.appendChild(newItem);
    makeDraggable(newItem);

    try {
        const response = await fetch(`/agent/deploy_agent_template/${state.id}/`, {
            method: 'GET',
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        if (response.ok) {
            console.log(`[Undo] Re-deployed pool directory for ${state.id}`);
        }
    } catch (error) {
        console.error(`[Undo] Failed to re-deploy ${state.id}:`, error);
    }

    return newItem;
}

// ========================================
// ITEM/CONNECTION DELETION WITHOUT UNDO
// ========================================

/**
 * Delete a canvas item without recording undo (used during redo).
 * @param {string} itemId - The ID of the item to delete
 */
async function deleteCanvasItemWithoutUndo(itemId) {
    const item = document.getElementById(itemId);
    if (!item) return;

    for (let i = ACP.connections.length - 1; i >= 0; i--) {
        const conn = ACP.connections[i];
        if (conn.source === item || conn.target === item) {
            conn.path.remove();
            ACP.connections.splice(i, 1);
            ACP.selectedItems.delete(conn);
        }
    }

    item.remove();
    ACP.selectedItems.delete(item);

    try {
        await fetch(`/agent/delete_agent_pool_dir/${itemId}/`, {
            method: 'GET',
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        console.log(`[Redo] Deleted pool directory for ${itemId}`);
    } catch (error) {
        console.error(`[Redo] Failed to delete pool dir ${itemId}:`, error);
    }
}

/**
 * Remove a connection without recording undo (used during redo).
 * Fires all relevant backend config updates.
 * @param {string} sourceId - Source node ID
 * @param {string} targetId - Target node ID
 */
async function removeConnectionWithoutUndo(sourceId, targetId) {
    for (let i = ACP.connections.length - 1; i >= 0; i--) {
        const conn = ACP.connections[i];
        if (conn.source.id === sourceId && conn.target.id === targetId) {
            const sourceAgentName = conn.source.dataset.agentName || '';
            const targetAgentName = conn.target.dataset.agentName || '';

            if (targetAgentName.toLowerCase() === 'raiser') {
                await updateRaiserConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'raiser') {
                await updateRaiserConnection(sourceId, 'target', targetId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'monitor-log') {
                await updateMonitorLogConnection(targetId, sourceId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'emailer') {
                await updateEmailerConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'starter') {
                await updateStarterConnection(sourceId, targetId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'croner') {
                await updateCronerConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'croner') {
                await updateCronerConnection(sourceId, 'target', targetId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'ender') {
                await updateEnderConnection(targetId, conn.source, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'sleeper') {
                await updateSleeperConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'sleeper') {
                await updateSleeperConnection(sourceId, targetId, 'remove', 'target');
            }
            if (sourceAgentName.toLowerCase() === 'shoter') {
                await updateShoterConnection(sourceId, targetId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'cleaner') {
                await updateCleanerConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'cleaner') {
                await updateCleanerConnection(sourceId, 'target', targetId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'stopper') {
                await updateStopperConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'stopper') {
                await updateStopperConnection(sourceId, 'output', targetId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'whatsapper') {
                await updateWhatsapperConnection(targetId, 'source', sourceId, 'remove');
            }
            if (targetAgentName.toLowerCase() === 'pythonxer') {
                await updatePythonxerConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'pythonxer') {
                await updatePythonxerConnection(sourceId, targetId, 'remove', 'target');
            }
            if (targetAgentName.toLowerCase() === 'asker') {
                await updateAskerConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'asker') {
                if (conn.outputSlot === 1) {
                    await updateAskerConnection(sourceId, 'target_a', targetId, 'remove');
                } else if (conn.outputSlot === 2) {
                    await updateAskerConnection(sourceId, 'target_b', targetId, 'remove');
                }
            }
            if (targetAgentName.toLowerCase() === 'forker') {
                await updateForkerConnection(targetId, 'source', sourceId, 'remove');
            }
            if (sourceAgentName.toLowerCase() === 'forker') {
                if (conn.outputSlot === 1) {
                    await updateForkerConnection(sourceId, 'target_a', targetId, 'remove');
                } else if (conn.outputSlot === 2) {
                    await updateForkerConnection(sourceId, 'target_b', targetId, 'remove');
                }
            }
            if (targetAgentName.toLowerCase() === 'gitter') {
                await updateGitterConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'gitter') {
                await updateGitterConnection(sourceId, targetId, 'remove', 'target');
            }
            if (targetAgentName.toLowerCase() === 'dockerer') {
                await updateDockererConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'dockerer') {
                await updateDockererConnection(sourceId, targetId, 'remove', 'target');
            }
            if (targetAgentName.toLowerCase() === 'pser') {
                await updatePserConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'pser') {
                await updatePserConnection(sourceId, targetId, 'remove', 'target');
            }
            if (targetAgentName.toLowerCase() === 'kuberneter') {
                await updateKuberneterConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'kuberneter') {
                await updateKuberneterConnection(sourceId, targetId, 'remove', 'target');
            }
            if (targetAgentName.toLowerCase() === 'apirer') {
                await updateApirerConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'apirer') {
                await updateApirerConnection(sourceId, targetId, 'remove', 'target');
            }
            if (targetAgentName.toLowerCase() === 'jenkinser') {
                await updateJenkinserConnection(targetId, sourceId, 'remove', 'source');
            }
            if (sourceAgentName.toLowerCase() === 'jenkinser') {
                await updateJenkinserConnection(sourceId, targetId, 'remove', 'target');
            }

            conn.path.remove();
            ACP.connections.splice(i, 1);
            ACP.selectedItems.delete(conn);
            console.log(`[Redo] Removed connection: ${sourceId} -> ${targetId}`);
            return;
        }
    }
}

// ========================================
// CONNECTION RECREATION (Undo Delete)
// ========================================

/**
 * Recreate a connection from captured state (for undo delete).
 * Re-fires all relevant backend configuration updates.
 * @param {Object} state - The captured connection state
 */
async function recreateConnection(state) {
    const sourceNode = document.getElementById(state.sourceId);
    const targetNode = document.getElementById(state.targetId);

    if (!sourceNode || !targetNode) {
        console.error('[Undo] Cannot recreate connection: source or target not found');
        return;
    }

    const { group, visiblePath, hitPath } = createConnectionGroup();

    const newConn = {
        source: sourceNode,
        target: targetNode,
        path: group,
        visiblePath: visiblePath,
        hitPath: hitPath,
        inputSlot: state.inputSlot || 0,
        outputSlot: state.outputSlot || 0
    };

    ACP.connections.push(newConn);
    updateAttachedConnections(targetNode);

    const sourceAgentName = (sourceNode.dataset.agentName || '').toLowerCase();
    const targetAgentName = (targetNode.dataset.agentName || '').toLowerCase();
    const sourceId = sourceNode.id;
    const targetId = targetNode.id;

    if (targetAgentName === 'raiser') {
        updateRaiserConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'raiser') {
        await updateRaiserConnection(sourceId, 'target', targetId, 'add');
    }
    if (targetAgentName === 'monitor-log') {
        await updateMonitorLogConnection(targetId, sourceId, 'add');
    }
    if (targetAgentName === 'emailer') {
        await updateEmailerConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'starter') {
        await updateStarterConnection(sourceId, targetId, 'add');
    }
    if (targetAgentName === 'croner') {
        await updateCronerConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'croner') {
        await updateCronerConnection(sourceId, 'target', targetId, 'add');
    }
    if (targetAgentName === 'sleeper') {
        await updateSleeperConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'sleeper') {
        await updateSleeperConnection(sourceId, targetId, 'add', 'target');
    }
    if (sourceAgentName === 'shoter') {
        await updateShoterConnection(sourceId, targetId, 'add');
    }
    if (targetAgentName === 'cleaner') {
        await updateCleanerConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'cleaner') {
        await updateCleanerConnection(sourceId, 'target', targetId, 'add');
    }
    if (targetAgentName === 'ender') {
        await updateEnderConnection(targetId, sourceNode, 'add');
    }
    if (targetAgentName === 'or') {
        const slot = state.inputSlot === 1 ? 'source_1' : (state.inputSlot === 2 ? 'source_2' : null);
        if (slot) await updateOrAgentConnection(targetId, slot, sourceId, 'add');
    }
    if (targetAgentName === 'and') {
        const slot = state.inputSlot === 1 ? 'source_1' : (state.inputSlot === 2 ? 'source_2' : null);
        if (slot) await updateAndAgentConnection(targetId, slot, sourceId, 'add');
    }
    if (sourceAgentName === 'or') {
        await updateOrAgentConnection(sourceId, 'target', targetId, 'add');
    }
    if (sourceAgentName === 'and') {
        await updateAndAgentConnection(sourceId, 'target', targetId, 'add');
    }
    if (targetAgentName === 'stopper') {
        await updateStopperConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'stopper') {
        await updateStopperConnection(sourceId, 'output', targetId, 'add');
    }
    if (targetAgentName === 'whatsapper') {
        await updateWhatsapperConnection(targetId, 'source', sourceId, 'add');
    }
    if (targetAgentName === 'pythonxer') {
        await updatePythonxerConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'pythonxer') {
        await updatePythonxerConnection(sourceId, targetId, 'add', 'target');
    }
    if (targetAgentName === 'asker') {
        await updateAskerConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'asker') {
        if (state.outputSlot === 1) {
            await updateAskerConnection(sourceId, 'target_a', targetId, 'add');
        } else if (state.outputSlot === 2) {
            await updateAskerConnection(sourceId, 'target_b', targetId, 'add');
        }
    }
    if (targetAgentName === 'forker') {
        await updateForkerConnection(targetId, 'source', sourceId, 'add');
    }
    if (sourceAgentName === 'forker') {
        if (state.outputSlot === 1) {
            await updateForkerConnection(sourceId, 'target_a', targetId, 'add');
        } else if (state.outputSlot === 2) {
            await updateForkerConnection(sourceId, 'target_b', targetId, 'add');
        }
    }
    if (targetAgentName === 'gitter') {
        await updateGitterConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'gitter') {
        await updateGitterConnection(sourceId, targetId, 'add', 'target');
    }
    if (targetAgentName === 'dockerer') {
        await updateDockererConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'dockerer') {
        await updateDockererConnection(sourceId, targetId, 'add', 'target');
    }
    if (targetAgentName === 'pser') {
        await updatePserConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'pser') {
        await updatePserConnection(sourceId, targetId, 'add', 'target');
    }
    if (targetAgentName === 'kuberneter') {
        await updateKuberneterConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'kuberneter') {
        await updateKuberneterConnection(sourceId, targetId, 'add', 'target');
    }
    if (targetAgentName === 'apirer') {
        await updateApirerConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'apirer') {
        await updateApirerConnection(sourceId, targetId, 'add', 'target');
    }
    if (targetAgentName === 'jenkinser') {
        await updateJenkinserConnection(targetId, sourceId, 'add', 'source');
    }
    if (sourceAgentName === 'jenkinser') {
        await updateJenkinserConnection(sourceId, targetId, 'add', 'target');
    }

    console.log(`[Undo] Recreated connection: ${state.sourceId} -> ${state.targetId}`);
}

// ========================================
// KEYBOARD HANDLER: Ctrl+Z / Ctrl+Y / Delete
// ========================================

window.addEventListener('keydown', async (e) => {
    const tag = e.target.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select' || e.target.isContentEditable) {
        return;
    }

    // Ctrl+Z - Undo
    if (e.ctrlKey && (e.key === 'z' || e.key === 'Z') && !e.shiftKey) {
        e.preventDefault();
        const undone = await undoManager.undo();
        if (undone) {
            console.log('--- Undo performed');
            updateSaveButtonState();
            markDirty();
        }
        return;
    }

    // Ctrl+Y or Ctrl+Shift+Z - Redo
    if ((e.ctrlKey && (e.key === 'y' || e.key === 'Y')) ||
        (e.ctrlKey && e.shiftKey && (e.key === 'z' || e.key === 'Z'))) {
        e.preventDefault();
        const redone = await undoManager.redo();
        if (redone) {
            console.log('--- Redo performed');
            updateSaveButtonState();
            markDirty();
        }
        return;
    }

    // Delete key - delete selected items and connections
    if ((e.key === 'Delete' || e.key === 'Del') && ACP.selectedItems.size > 0) {
        const canvasItemsToDelete = [];
        const connectionsToDelete = [];

        for (const item of ACP.selectedItems) {
            if (item.classList && item.classList.contains('canvas-item')) {
                canvasItemsToDelete.push(item);
            } else if (item.path && item.path.classList.contains('connection-group')) {
                connectionsToDelete.push(item);
            }
        }

        const deletingNodes = new Set(canvasItemsToDelete);

        // STEP 0: Capture state for undo (before any modifications)
        const undoState = {
            items: canvasItemsToDelete.map(captureItemState),
            itemConnections: captureRelatedConnections(canvasItemsToDelete),
            standaloneConnections: connectionsToDelete.map(captureConnectionState)
        };

        // STEP 1: Collect all config updates BEFORE removing connections
        // (graph traversal needs connections intact)
        const configUpdates = [];

        for (const item of canvasItemsToDelete) {
            for (const conn of ACP.connections) {
                if (conn.source === item || conn.target === item) {
                    const sourceAgentName = conn.source.dataset.agentName || '';
                    const targetAgentName = conn.target.dataset.agentName || '';
                    const sourceId = conn.source.id;
                    const targetId = conn.target.id;

                    const sourceBeingDeleted = deletingNodes.has(conn.source);
                    const targetBeingDeleted = deletingNodes.has(conn.target);

                    if (targetAgentName.toLowerCase() === 'raiser' && !targetBeingDeleted) {
                        configUpdates.push({ type: 'raiser', id: targetId, role: 'source', agentId: sourceId, action: 'remove' });
                    }
                    if (sourceAgentName.toLowerCase() === 'raiser' && !sourceBeingDeleted) {
                        configUpdates.push({ type: 'raiser', id: sourceId, role: 'target', agentId: targetId, action: 'remove' });
                    }
                    if (targetAgentName.toLowerCase() === 'monitor-log' && !targetBeingDeleted) {
                        configUpdates.push({ type: 'monitor-log', id: targetId, sourceId: sourceId, action: 'remove' });
                    }
                    if (targetAgentName.toLowerCase() === 'ender' && !targetBeingDeleted) {
                        const allUpstream = getAllUpstreamAgents(conn.source);
                        for (const upstreamNode of allUpstream) {
                            configUpdates.push({ type: 'ender', enderId: targetId, agentId: upstreamNode.id, action: 'remove' });
                        }
                    }
                    if (sourceAgentName.toLowerCase() === 'starter' && !sourceBeingDeleted) {
                        configUpdates.push({ type: 'starter', id: sourceId, targetId: targetId, action: 'remove' });
                    }
                    if (targetAgentName.toLowerCase() === 'mover' && !targetBeingDeleted) {
                        configUpdates.push({ type: 'mover', id: targetId, sourceId: sourceId, action: 'remove', connType: 'source' });
                    }
                    if (sourceAgentName.toLowerCase() === 'mover' && !sourceBeingDeleted) {
                        configUpdates.push({ type: 'mover', id: sourceId, targetId: targetId, action: 'remove', connType: 'target' });
                    }
                }
            }
        }

        // STEP 2: Execute all config updates in parallel
        const configUpdatePromises = configUpdates.map(async (update) => {
            try {
                if (update.type === 'raiser') {
                    await updateRaiserConnection(update.id, update.role, update.agentId, 'remove');
                } else if (update.type === 'monitor-log') {
                    await updateMonitorLogConnection(update.id, update.sourceId, 'remove');
                } else if (update.type === 'ender') {
                    const response = await fetch(`/agent/update_ender_connection/${update.enderId}/`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json', ...getHeaders() },
                        credentials: 'same-origin',
                        body: JSON.stringify({ source_agent: update.agentId, action: 'remove' })
                    });
                    if (response.ok) {
                        const result = await response.json();
                        console.log(`--- Ender ${update.enderId} config updated:`, result.message);
                    }
                } else if (update.type === 'starter') {
                    await updateStarterConnection(update.id, update.targetId, 'remove');
                } else if (update.type === 'mover') {
                    const connected = update.connType === 'target' ? update.targetId : update.sourceId;
                    await updateMoverConnection(update.id, connected, 'remove', update.connType);
                }
                return { success: true };
            } catch (err) {
                console.error('Config update failed:', err);
                return { success: false };
            }
        });
        await Promise.all(configUpdatePromises);

        // STEP 3: Delete all pool directories
        const deletePromises = canvasItemsToDelete.map(async (item) => {
            if (item.id) {
                try {
                    const response = await fetch(`/agent/delete_agent_pool_dir/${item.id}/`, {
                        method: 'GET',
                        headers: getHeaders(),
                        credentials: 'same-origin'
                    });
                    const result = await response.json();
                    if (result.deleted) {
                        console.log(`Deleted pool directory for ${item.id}: ${result.message}`);
                    }
                    return { agentId: item.id, success: true };
                } catch (err) {
                    console.error(`Could not delete pool directory for ${item.id}:`, err);
                    return { agentId: item.id, success: false };
                }
            }
            return { agentId: item.id, success: true };
        });
        await Promise.all(deletePromises);

        // STEP 4: Remove canvas items and their connections from DOM
        for (const item of canvasItemsToDelete) {
            for (let i = ACP.connections.length - 1; i >= 0; i--) {
                const conn = ACP.connections[i];
                if (conn.source === item || conn.target === item) {
                    conn.path.remove();
                    ACP.connections.splice(i, 1);
                    ACP.selectedItems.delete(conn);
                }
            }
            item.remove();
        }

        // Remove selected standalone connections (with config updates)
        for (const conn of connectionsToDelete) {
            removeConnection(conn);
        }

        // STEP 5: Record undo action
        undoManager.record({
            type: 'DELETE_BATCH',
            data: undoState,
            undo: async function () {
                for (const itemState of this.data.items) {
                    await recreateCanvasItem(itemState);
                }
                for (const connState of this.data.itemConnections) {
                    await recreateConnection(connState);
                }
                for (const connState of this.data.standaloneConnections) {
                    await recreateConnection(connState);
                }
            },
            redo: async function () {
                for (const itemState of this.data.items) {
                    await deleteCanvasItemWithoutUndo(itemState.id);
                }
                for (const connState of this.data.standaloneConnections) {
                    await removeConnectionWithoutUndo(connState.sourceId, connState.targetId);
                }
            }
        });

        ACP.selectedItems.clear();
        updateSaveButtonState();
        markDirty();
    }
});
