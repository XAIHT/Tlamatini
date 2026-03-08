// Agentic Control Panel - Canvas Core: Items, Connections, Selection, Drag & Drop
// LOAD ORDER: #7 - Depends on: acp-globals.js, acp-session.js, acp-undo-manager.js,
//                              acp-agent-connectors.js

// ========================================
// ITEM COUNTER / REGISTRATION
// ========================================

/**
 * Register a new canvas item and generate a unique ID.
 * @param {string} text - The agent display name (e.g., "starter", "mover")
 * @returns {{ id: string, count: number, baseName: string }}
 */
function registerItem(text) {
    const baseName = text.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    const currentCount = ACP.itemCounters.get(baseName) || 0;
    const newCount = currentCount + 1;
    ACP.itemCounters.set(baseName, newCount);
    return { id: `${baseName}-${newCount}`, count: newCount, baseName: baseName };
}

// ========================================
// AGENT TYPE CLASS HELPERS
// ========================================

/**
 * Apply the correct CSS agent-type class to a canvas item element based on its name.
 * @param {HTMLElement} el - The canvas item element
 * @param {string} agentName - Lowercase agent name
 */
function applyAgentTypeClass(el, agentName) {
    const classMap = {
        'ender': 'ender-agent',
        'starter': 'starter-agent',
        'or': 'or-agent',
        'and': 'and-agent',
        'croner': 'croner-agent',
        'mover': 'mover-agent',
        'cleaner': 'cleaner-agent',
        'sleeper': 'sleeper-agent',
        'shoter': 'shoter-agent',
        'recmailer': 'recmailer-agent',
        'notifier': 'notifier-agent',
        'deleter': 'deleter-agent',
        'executer': 'executer-agent',
        'stopper': 'stopper-agent',
        'whatsapper': 'whatsapper-agent',
        'telegramrx': 'telegramrx-agent',
        'telegramer': 'telegramer-agent',
        'pythonxer': 'pythonxer-agent',
        'asker': 'asker-agent',
        'forker': 'forker-agent',
        'raiser': 'raiser-agent',
        'emailer': 'emailer-agent',
        'monitor-log': 'monitor-log-agent',
        'monitor-netstat': 'monitor-netstat-agent',
        'ssher': 'ssher-agent',
        'scper': 'scper-agent',
        'sqler': 'sqler-agent',
        'prompter': 'prompter-agent',
        'flowcreator': 'flowcreator-agent',
        'gitter': 'gitter-agent',
        'dockerer': 'dockerer-agent',
    };
    const cls = classMap[agentName];
    if (cls) el.classList.add(cls);
}

/**
 * Append input triangle(s) to a canvas item based on agent type.
 * Starter agents get no input. OR/AND agents get two inputs. Others get one.
 */
function appendInputTriangles(el, agentName) {
    if (agentName === 'starter' || agentName === 'flowcreator') return;
    if (agentName === 'or' || agentName === 'and') {
        const inputTri1 = document.createElement('div');
        inputTri1.classList.add('input-triangle', 'input-1');
        inputTri1.title = "Input 1";
        el.appendChild(inputTri1);
        const inputTri2 = document.createElement('div');
        inputTri2.classList.add('input-triangle', 'input-2');
        inputTri2.title = "Input 2";
        el.appendChild(inputTri2);
    } else {
        const inputTri = document.createElement('div');
        inputTri.classList.add('input-triangle');
        el.appendChild(inputTri);
    }
}

/**
 * Append output triangle(s) to a canvas item based on agent type.
 * Asker/Forker agents get two outputs (A and B). Others get one.
 * Agents that never start downstream agents get a dark-gray output triangle.
 */
const AGENTS_NEVER_START_OTHERS = [
    'cleaner', 'emailer', 'monitor log', 'monitor-log',
    'monitor netstat', 'monitor-netstat',
    'recmailer', 'stopper', 'whatsapper', 'telegramrx',
    'flowcreator'
];

function appendOutputTriangles(el, agentName) {
    if (agentName === 'flowcreator') return; // FlowCreator has no outputs
    const neverStarts = AGENTS_NEVER_START_OTHERS.includes(agentName);

    if (agentName === 'asker' || agentName === 'forker') {
        const outputTri1 = document.createElement('div');
        outputTri1.classList.add('output-triangle', 'output-1');
        outputTri1.title = "Output A";
        el.appendChild(outputTri1);
        const labelA = document.createElement('div');
        labelA.classList.add('output-label', 'label-a');
        labelA.textContent = 'A';
        el.appendChild(labelA);
        const outputTri2 = document.createElement('div');
        outputTri2.classList.add('output-triangle', 'output-2');
        outputTri2.title = "Output B";
        el.appendChild(outputTri2);
        const labelB = document.createElement('div');
        labelB.classList.add('output-label', 'label-b');
        labelB.textContent = 'B';
        el.appendChild(labelB);
    } else {
        const outputTri = document.createElement('div');
        outputTri.classList.add('output-triangle');
        if (neverStarts) {
            outputTri.style.borderLeftColor = '#555';
            outputTri.title = "This agent does not start downstream agents";
        }
        el.appendChild(outputTri);
    }
}

/**
 * Append the LED status indicator to a canvas item.
 */
function appendLedIndicator(el) {
    const led = document.createElement('div');
    led.classList.add('canvas-item-led', 'led-idle');
    led.title = 'Agent Status';
    el.appendChild(led);
}

// ========================================
// CANVAS ITEM CREATION (Drag-Drop)
// ========================================

/**
 * Create and place a new canvas item at the given client coordinates.
 * Deploys the agent template to the pool directory.
 */
async function createCanvasItem(clientX, clientY, textContent) {
    const rect = submonitor.getBoundingClientRect();
    let x = clientX - rect.left;
    let y = clientY - rect.top;

    const newItem = document.createElement('div');
    newItem.classList.add('canvas-item');

    const registration = registerItem(textContent);
    newItem.textContent = `${textContent} (${registration.count})`;
    newItem.id = registration.id;
    newItem.dataset.agentName = textContent;

    const lowerName = textContent.toLowerCase();
    applyAgentTypeClass(newItem, lowerName);
    appendInputTriangles(newItem, lowerName);
    appendOutputTriangles(newItem, lowerName);
    appendLedIndicator(newItem);

    submonitor.appendChild(newItem); // Append first to read offsetWidth/Height

    const width = newItem.offsetWidth;
    const height = newItem.offsetHeight;

    x -= width / 2;
    y -= height / 2;

    const maxX = rect.width - width;
    const maxY = rect.height - height;
    x = Math.max(0, Math.min(x, maxX));
    y = Math.max(0, Math.min(y, maxY));

    newItem.style.left = x + 'px';
    newItem.style.top = y + 'px';

    makeDraggable(newItem);
    updateSaveButtonState();

    // Deploy agent template to pool directory
    try {
        const response = await fetch(`/agent/deploy_agent_template/${newItem.id}/`, {
            method: 'GET', headers: getHeaders(), credentials: 'same-origin'
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Deployed agent template ${newItem.id} to pool:`, result.path);
        } else {
            console.error(`--- Failed to deploy agent template ${newItem.id}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error deploying agent template ${newItem.id}:`, error);
    }

    // Record undo action for item creation
    const itemState = captureItemState(newItem);
    undoManager.record({
        type: 'ADD_ITEM',
        data: itemState,
        undo: async function () { await deleteCanvasItemWithoutUndo(this.data.id); },
        redo: async function () { await recreateCanvasItem(this.data); }
    });

    markDirty();
}

/**
 * Clone an existing canvas item (used during Ctrl+Drag copy).
 * Registers the clone with a new ID and deploys it.
 * @param {HTMLElement} originalItem - The item to clone
 * @returns {HTMLElement} The new cloned item
 */
function cloneAndRegister(originalItem) {
    const agentName = originalItem.dataset.agentName || originalItem.textContent.split(' (')[0];
    const registration = registerItem(agentName);
    const lowerName = agentName.toLowerCase();

    const newItem = document.createElement('div');
    newItem.classList.add('canvas-item');
    newItem.textContent = `${agentName} (${registration.count})`;
    newItem.id = registration.id;
    newItem.dataset.agentName = agentName;
    newItem.style.left = originalItem.style.left;
    newItem.style.top = originalItem.style.top;

    applyAgentTypeClass(newItem, lowerName);
    appendInputTriangles(newItem, lowerName);
    appendOutputTriangles(newItem, lowerName);
    appendLedIndicator(newItem);

    submonitor.appendChild(newItem);
    makeDraggable(newItem);
    return newItem;
}

// ========================================
// CANVAS ITEM DRAGGING
// ========================================

/**
 * Make a canvas item draggable within the submonitor container.
 * Supports multi-selection group drag and Ctrl+Drag copy.
 * @param {HTMLElement} el - The canvas item to make draggable
 */
function makeDraggable(el) {
    let isMoving = false;
    let hasCloned = false;
    let startX, startY;
    let initialPositions = new Map();

    el.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('input-triangle') || e.target.classList.contains('output-triangle')) return;

        if (e.ctrlKey) {
            if (!ACP.selectedItems.has(el)) selectItem(el, true);
        } else {
            if (!ACP.selectedItems.has(el)) selectItem(el, false);
        }

        isMoving = true;
        hasCloned = false;
        startX = e.clientX;
        startY = e.clientY;

        initialPositions.clear();
        ACP.selectedItems.forEach(item => {
            if (item.classList && item.classList.contains('canvas-item')) {
                initialPositions.set(item, { left: item.offsetLeft, top: item.offsetTop });
            }
        });

        el.style.zIndex = 1100;
        e.preventDefault();
        e.stopPropagation();
    });

    window.addEventListener('mousemove', (e) => {
        if (!isMoving) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        // Ctrl+Drag: clone selected items on first meaningful move
        if (!hasCloned && e.ctrlKey && (Math.abs(dx) > 3 || Math.abs(dy) > 3)) {
            const newSelection = new Set();
            const newInitialPositions = new Map();
            const originalToClone = new Map();

            ACP.selectedItems.forEach(original => {
                if (original.classList && original.classList.contains('canvas-item')) {
                    const clone = cloneAndRegister(original);
                    newSelection.add(clone);
                    originalToClone.set(original, clone);
                    const origPos = initialPositions.get(original);
                    if (origPos) newInitialPositions.set(clone, origPos);
                }
            });

            // Deploy pool directories for cloned items (async, fire-and-forget)
            originalToClone.forEach((clone, _original) => {
                fetch(`/agent/deploy_agent_template/${clone.id}/`, {
                    method: 'GET', headers: getHeaders(), credentials: 'same-origin'
                }).then(response => {
                    if (response.ok) console.log(`[Clone] Deployed pool directory for ${clone.id}`);
                    else console.error(`[Clone] Failed to deploy pool for ${clone.id}:`, response.statusText);
                }).catch(error => {
                    console.error(`[Clone] Error deploying pool for ${clone.id}:`, error);
                });
            });

            // Clone connections between selected items
            const existingConnections = [...ACP.connections];
            existingConnections.forEach(conn => {
                const sourceClone = originalToClone.get(conn.source);
                const targetClone = originalToClone.get(conn.target);
                if (sourceClone && targetClone) {
                    const groupData = createConnectionGroup();
                    ACP.connections.push({
                        source: sourceClone,
                        target: targetClone,
                        path: groupData.group,
                        visiblePath: groupData.visiblePath,
                        hitPath: groupData.hitPath,
                        inputSlot: conn.inputSlot || 0,
                        outputSlot: conn.outputSlot || 0
                    });
                }
            });

            deselectAll();
            newSelection.forEach(clone => selectItem(clone, true));
            initialPositions = newInitialPositions;
            hasCloned = true;
        }

        const containerRect = submonitor.getBoundingClientRect();
        initialPositions.forEach((startPos, item) => {
            let newLeft = startPos.left + dx;
            let newTop = startPos.top + dy;
            const maxLeft = containerRect.width - item.offsetWidth;
            const maxTop = containerRect.height - item.offsetHeight;
            newLeft = Math.max(0, Math.min(newLeft, maxLeft));
            newTop = Math.max(0, Math.min(newTop, maxTop));
            item.style.left = newLeft + 'px';
            item.style.top = newTop + 'px';
            updateAttachedConnections(item);
        });
    });

    window.addEventListener('mouseup', () => {
        if (isMoving) {
            isMoving = false;
            el.style.zIndex = '';
            initialPositions.clear();
            markDirty();
        }
    });
}

// ========================================
// SELECTION LOGIC
// ========================================

function selectItem(item, multi = false) {
    if (!multi) deselectAll();
    if (!ACP.selectedItems.has(item)) {
        ACP.selectedItems.add(item);
        if (item.classList) item.classList.add('selected');
    }
}

function toggleSelection(item) { // eslint-disable-line no-unused-vars
    if (ACP.selectedItems.has(item)) {
        ACP.selectedItems.delete(item);
        if (item.classList) item.classList.remove('selected');
    } else {
        ACP.selectedItems.add(item);
        if (item.classList) item.classList.add('selected');
    }
}

function selectConnection(conn, multi = false) {
    if (!multi) deselectAll();
    if (!ACP.selectedItems.has(conn)) {
        ACP.selectedItems.add(conn);
        conn.path.classList.add('selected');
    }
}

function toggleConnectionSelection(conn) {
    if (ACP.selectedItems.has(conn)) {
        ACP.selectedItems.delete(conn);
        conn.path.classList.remove('selected');
    } else {
        ACP.selectedItems.add(conn);
        conn.path.classList.add('selected');
    }
}

function deselectAll() {
    ACP.selectedItems.forEach(item => {
        if (item.classList) item.classList.remove('selected');
        if (item.path) item.path.classList.remove('selected');
    });
    ACP.selectedItems.clear();
}

// ========================================
// SELECTION BOX
// ========================================

function startSelectionBox(e) {
    ACP.isSelecting = true;
    const rect = submonitor.getBoundingClientRect();
    ACP.initialBoxX = e.clientX - rect.left + submonitor.scrollLeft;
    ACP.initialBoxY = e.clientY - rect.top + submonitor.scrollTop;
    ACP.selectionBox.style.left = ACP.initialBoxX + 'px';
    ACP.selectionBox.style.top = ACP.initialBoxY + 'px';
    ACP.selectionBox.style.width = '0px';
    ACP.selectionBox.style.height = '0px';
    ACP.selectionBox.style.display = 'block';
}

function isIntersecting(r1, r2) {
    return !(r2.left > r1.right || r2.right < r1.left || r2.top > r1.bottom || r2.bottom < r1.top);
}

// ========================================
// SVG CONNECTION HELPERS
// ========================================

function getCenter(el) {
    const rect = el.getBoundingClientRect();
    const containerRect = submonitor.getBoundingClientRect();
    return {
        x: rect.left + rect.width / 2 - containerRect.left,
        y: rect.top + rect.height / 2 - containerRect.top
    };
}

function setPathD(x1, y1, x2, y2, ...paths) {
    const dist = Math.abs(x2 - x1) * 0.5;
    const cp1x = x1 + dist, cp1y = y1;
    const cp2x = x2 - dist, cp2y = y2;
    const d = `M ${x1} ${y1} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${x2} ${y2}`;
    paths.forEach(p => p.setAttribute('d', d));
}

function createConnectionGroup() {
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.classList.add('connection-group');
    const visiblePath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    visiblePath.classList.add('connection-path');
    const hitPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    hitPath.classList.add('connection-hit-area');
    group.appendChild(visiblePath);
    group.appendChild(hitPath);
    ACP.svgLayer.appendChild(group);
    return { group, visiblePath, hitPath };
}

/**
 * Redraw all connections attached to the given node.
 * Uses outputSlot/inputSlot to pick the correct triangle anchors.
 */
function updateAttachedConnections(node) {
    ACP.connections.forEach(conn => {
        if (conn.source !== node && conn.target !== node) return;

        const outputSlot = parseInt(conn.outputSlot) || 0;
        let startEl;
        if (outputSlot === 1) startEl = conn.source.querySelector('.output-triangle.output-1');
        else if (outputSlot === 2) startEl = conn.source.querySelector('.output-triangle.output-2');
        if (!startEl) startEl = conn.source.querySelector('.output-triangle');
        if (!startEl) {
            console.warn(`[Draw] Missing output triangle for ${conn.source.id} (Slot: ${outputSlot})`);
            return;
        }

        const inputSlot = parseInt(conn.inputSlot) || 0;
        let endEl;
        if (inputSlot === 1) endEl = conn.target.querySelector('.input-triangle.input-1');
        else if (inputSlot === 2) endEl = conn.target.querySelector('.input-triangle.input-2');
        if (!endEl) endEl = conn.target.querySelector('.input-triangle');
        if (!endEl) {
            console.warn(`[Draw] Missing input triangle for ${conn.target.id} (Slot: ${inputSlot})`);
            return;
        }

        const startPos = getCenter(startEl);
        const endPos = getCenter(endEl);
        if (isNaN(startPos.x) || isNaN(startPos.y) || isNaN(endPos.x) || isNaN(endPos.y)) {
            console.error(`[Draw] Invalid coordinates for connection ${conn.source.id}->${conn.target.id}`);
            return;
        }
        setPathD(startPos.x, startPos.y, endPos.x, endPos.y, conn.visiblePath, conn.hitPath);
    });
}

// ========================================
// CONNECTION REMOVAL
// ========================================

/**
 * Remove a connection and update backend configs.
 * @param {Object} conn - The connection object to remove
 */
function removeConnection(conn) {
    const idx = ACP.connections.indexOf(conn);
    if (idx > -1) {
        const sourceAgentName = conn.source.dataset.agentName || '';
        const targetAgentName = conn.target.dataset.agentName || '';
        const sourceId = conn.source.id;
        const targetId = conn.target.id;

        if (targetAgentName.toLowerCase() === 'raiser') updateRaiserConnection(targetId, 'source', sourceId, 'remove');
        if (targetAgentName.toLowerCase() === 'emailer') updateEmailerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'raiser') updateRaiserConnection(sourceId, 'target', targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'monitor-log') updateMonitorLogConnection(targetId, sourceId, 'remove');
        if (targetAgentName.toLowerCase() === 'ender') updateEnderConnection(targetId, conn.source, 'remove', 'input');
        if (sourceAgentName.toLowerCase() === 'ender') updateEnderConnection(sourceId, conn.target, 'remove', 'output');
        if (sourceAgentName.toLowerCase() === 'starter') updateStarterConnection(sourceId, targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'notifier') updateNotifierConnection(targetId, 'source', sourceId, 'remove');
        if (sourceAgentName.toLowerCase() === 'notifier') updateNotifierConnection(sourceId, 'target', targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'croner') updateCronerConnection(targetId, 'source', sourceId, 'remove');
        if (sourceAgentName.toLowerCase() === 'croner') updateCronerConnection(sourceId, 'target', targetId, 'remove');

        if (targetAgentName.toLowerCase() === 'or') {
            if (conn.inputSlot === 1) updateOrAgentConnection(targetId, 'source_1', sourceId, 'remove');
            else if (conn.inputSlot === 2) updateOrAgentConnection(targetId, 'source_2', sourceId, 'remove');
        }
        if (sourceAgentName.toLowerCase() === 'or') updateOrAgentConnection(sourceId, 'target', targetId, 'remove');

        if (targetAgentName.toLowerCase() === 'and') {
            if (conn.inputSlot === 1) updateAndAgentConnection(targetId, 'source_1', sourceId, 'remove');
            else if (conn.inputSlot === 2) updateAndAgentConnection(targetId, 'source_2', sourceId, 'remove');
        }
        if (sourceAgentName.toLowerCase() === 'and') updateAndAgentConnection(sourceId, 'target', targetId, 'remove');

        if (targetAgentName.toLowerCase() === 'cleaner') updateCleanerConnection(targetId, 'source', sourceId, 'remove');
        if (sourceAgentName.toLowerCase() === 'cleaner') updateCleanerConnection(sourceId, 'target', targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'mover') updateMoverConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'mover') updateMoverConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'deleter') updateDeleterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'deleter') updateDeleterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'executer') updateExecuterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'executer') updateExecuterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'ssher') updateSsherConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'ssher') updateSsherConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'scper') updateScperConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'scper') updateScperConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'sqler') updateSqlerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'sqler') updateSqlerConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'prompter') updatePrompterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'prompter') updatePrompterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'gitter') updateGitterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'gitter') updateGitterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'dockerer') updateDockererConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'dockerer') updateDockererConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'telegramrx') updateTelegramrxConnection(targetId, sourceId, 'remove', 'source');
        if (targetAgentName.toLowerCase() === 'telegramer') updateTelegramerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'telegramer') updateTelegramerConnection(sourceId, targetId, 'remove', 'target');

        conn.path.remove();
        ACP.connections.splice(idx, 1);
        ACP.selectedItems.delete(conn);
    }
}

/**
 * Remove all connections for a node (with optional skip list for batch deletes).
 * @param {HTMLElement} node
 * @param {Set|null} deletingNodes - Nodes being deleted (skip config updates for them)
 */
function removeConnectionsFor(node, deletingNodes = null) { // eslint-disable-line no-unused-vars
    for (let i = ACP.connections.length - 1; i >= 0; i--) {
        const conn = ACP.connections[i];
        if (conn.source !== node && conn.target !== node) continue;

        const sourceAgentName = conn.source.dataset.agentName || '';
        const targetAgentName = conn.target.dataset.agentName || '';
        const sourceId = conn.source.id;
        const targetId = conn.target.id;
        const sourceBeingDeleted = deletingNodes && deletingNodes.has(conn.source);
        const targetBeingDeleted = deletingNodes && deletingNodes.has(conn.target);

        if (targetAgentName.toLowerCase() === 'raiser' && !targetBeingDeleted) updateRaiserConnection(targetId, 'source', sourceId, 'remove');
        if (targetAgentName.toLowerCase() === 'emailer' && !targetBeingDeleted) updateEmailerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'raiser' && !sourceBeingDeleted) updateRaiserConnection(sourceId, 'target', targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'monitor-log' && !targetBeingDeleted) updateMonitorLogConnection(targetId, sourceId, 'remove');
        if (targetAgentName.toLowerCase() === 'ender' && !targetBeingDeleted) updateEnderConnection(targetId, conn.source, 'remove');
        if (sourceAgentName.toLowerCase() === 'starter' && !sourceBeingDeleted) updateStarterConnection(sourceId, targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'cleaner' && !targetBeingDeleted) updateCleanerConnection(targetId, 'source', sourceId, 'remove');
        if (sourceAgentName.toLowerCase() === 'cleaner' && !sourceBeingDeleted) updateCleanerConnection(sourceId, 'target', targetId, 'remove');
        if (targetAgentName.toLowerCase() === 'mover' && !targetBeingDeleted) updateMoverConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'mover' && !sourceBeingDeleted) updateMoverConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'deleter' && !targetBeingDeleted) updateDeleterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'deleter' && !sourceBeingDeleted) updateDeleterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'executer' && !targetBeingDeleted) updateExecuterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'executer' && !sourceBeingDeleted) updateExecuterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'pythonxer' && !targetBeingDeleted) updatePythonxerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'pythonxer' && !sourceBeingDeleted) updatePythonxerConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'ssher' && !targetBeingDeleted) updateSsherConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'ssher' && !sourceBeingDeleted) updateSsherConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'scper' && !targetBeingDeleted) updateScperConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'scper' && !sourceBeingDeleted) updateScperConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'sqler' && !targetBeingDeleted) updateSqlerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'sqler' && !sourceBeingDeleted) updateSqlerConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'prompter' && !targetBeingDeleted) updatePrompterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'prompter' && !sourceBeingDeleted) updatePrompterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'gitter' && !targetBeingDeleted) updateGitterConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'gitter' && !sourceBeingDeleted) updateGitterConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'dockerer' && !targetBeingDeleted) updateDockererConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'dockerer' && !sourceBeingDeleted) updateDockererConnection(sourceId, targetId, 'remove', 'target');
        if (targetAgentName.toLowerCase() === 'telegramrx' && !targetBeingDeleted) updateTelegramrxConnection(targetId, sourceId, 'remove', 'source');
        if (targetAgentName.toLowerCase() === 'telegramer' && !targetBeingDeleted) updateTelegramerConnection(targetId, sourceId, 'remove', 'source');
        if (sourceAgentName.toLowerCase() === 'telegramer' && !sourceBeingDeleted) updateTelegramerConnection(sourceId, targetId, 'remove', 'target');

        if (targetAgentName.toLowerCase() === 'asker' && !targetBeingDeleted) updateAskerConnection(targetId, 'source', sourceId, 'remove');
        if (sourceAgentName.toLowerCase() === 'asker' && !sourceBeingDeleted) {
            if (conn.outputSlot === 1) updateAskerConnection(sourceId, 'target_a', targetId, 'remove');
            else if (conn.outputSlot === 2) updateAskerConnection(sourceId, 'target_b', targetId, 'remove');
        }
        if (targetAgentName.toLowerCase() === 'forker' && !targetBeingDeleted) updateForkerConnection(targetId, 'source', sourceId, 'remove');
        if (sourceAgentName.toLowerCase() === 'forker' && !sourceBeingDeleted) {
            if (conn.outputSlot === 1) updateForkerConnection(sourceId, 'target_a', targetId, 'remove');
            else if (conn.outputSlot === 2) updateForkerConnection(sourceId, 'target_b', targetId, 'remove');
        }

        conn.path.remove();
        ACP.connections.splice(i, 1);
        ACP.selectedItems.delete(conn);
    }
}

// ========================================
// AGENT LIST POPULATION
// ========================================

/**
 * Fetch the description/type for an agent slot from the backend.
 * @param {string} agentName - e.g., "agent-1"
 * @returns {string|null} Description text or null if not found
 */
async function loadAgentDescription(agentName) {
    try {
        const response = await fetch(`/agent/load_agent_description/${agentName}/`, {
            headers: getHeaders()
        });
        if (response.status === 404) return null;
        if (!response.ok) { console.error('HTTP Error: ' + response.status); return null; }
        const content = await response.text();
        if (content === 'Agent not found in database') return null;
        return content;
    } catch (error) {
        console.error('Error loading agent description:', error);
        return null;
    }
}

/**
 * Populate the agents list panel with draggable agent tool items.
 */
async function populateAgentsList() {
    const agentsList = document.getElementById('agents-list');
    if (!agentsList) return;
    agentsList.innerHTML = '';

    for (let i = 1; i <= ACP.MAX_AGENTS; i++) {
        const agentName = `agent-${i}`;
        const description = await loadAgentDescription(agentName);
        if (description === null) break; // Stop on first missing agent

        const atomDiv = document.createElement('div');
        atomDiv.classList.add('agent-tool-item');
        atomDiv.setAttribute('draggable', 'true');
        atomDiv.dataset.content = description;

        const iconDiv = document.createElement('div');
        iconDiv.classList.add('agent-tool-icon');

        // Set icon color based on agent type
        const lowerDesc = description.toLowerCase();
        if (lowerDesc === 'ender') iconDiv.style.backgroundColor = '#8B5CF6';
        else if (lowerDesc === 'starter') iconDiv.style.backgroundColor = '#10B981';
        else if (lowerDesc === 'or') iconDiv.style.backgroundColor = '#F59E0B';
        else if (lowerDesc === 'cleaner') iconDiv.style.backgroundColor = '#00008B';
        else if (lowerDesc === 'and') iconDiv.style.backgroundColor = '#06b6d4';
        else if (lowerDesc === 'croner') iconDiv.style.backgroundColor = '#F87171';
        else if (lowerDesc === 'mover') iconDiv.style.backgroundColor = '#795548';
        else if (lowerDesc === 'sleeper') iconDiv.style.backgroundColor = '#607d8b';
        else if (lowerDesc === 'deleter') iconDiv.style.backgroundColor = '#DC2626';
        else if (lowerDesc === 'recmailer') iconDiv.style.backgroundColor = '#06b6d4';
        else if (lowerDesc === 'executer') iconDiv.style.backgroundColor = '#FACC15';
        else if (lowerDesc === 'pythonxer') iconDiv.style.backgroundColor = '#306998';
        else if (lowerDesc === 'asker') iconDiv.style.background = 'linear-gradient(135deg, #EF4444 0%, #3B82F6 100%)';
        else if (lowerDesc === 'forker') iconDiv.style.background = 'linear-gradient(135deg, #000000 0%, #FFFFFF 100%)';
        else if (lowerDesc === 'ssher') iconDiv.style.background = 'linear-gradient(135deg, #1a237e 0%, #e53935 100%)';
        else if (lowerDesc === 'scper') iconDiv.style.background = 'linear-gradient(135deg, #424242 0%, #e53935 100%)';
        else if (lowerDesc === 'sqler') iconDiv.style.background = 'linear-gradient(135deg, #f97316 0%, #10b981 100%)';
        else if (lowerDesc === 'telegramrx') iconDiv.style.background = 'linear-gradient(135deg, #1a237e 0%, #000000 100%)';
        else if (lowerDesc === 'telegramer') iconDiv.style.background = 'linear-gradient(135deg, #1a237e 0%, #10B981 100%)';
        else if (lowerDesc === 'prompter') iconDiv.style.background = 'linear-gradient(135deg, #795548 0%, #1a237e 100%)';
        else if (lowerDesc === 'flowcreator') iconDiv.style.background = 'linear-gradient(135deg, #1565C0 0%, #C62828 50%, #2E7D32 100%)';
        else if (lowerDesc === 'gitter') iconDiv.style.background = 'linear-gradient(135deg, #FFFFFF 0%, #000000 100%)';
        else if (lowerDesc === 'dockerer') iconDiv.style.background = 'linear-gradient(135deg, #2496ED 0%, #FFFFFF 100%)';
        // Default blue (#7289da) is set in CSS for other agents

        const span = document.createElement('span');
        span.textContent = description;

        atomDiv.appendChild(iconDiv);
        atomDiv.appendChild(span);
        agentsList.appendChild(atomDiv);
    }
}

// ========================================
// CANVAS EVENT HANDLERS (Connection drawing, Selection, Double-click)
// These are registered during initACPCanvas() in acp-layout.js
// ========================================

/**
 * Initialize all canvas event listeners.
 * Must be called after the DOM is ready and ACP.svgLayer / ACP.selectionBox are set.
 */
function initCanvasEvents() {
    // Wire up the SVG connections layer
    ACP.svgLayer = document.getElementById('connections-layer');

    // Create the rubber-band selection box element if it doesn't exist
    if (!document.getElementById('selection-box')) {
        const sb = document.createElement('div');
        sb.id = 'selection-box';
        submonitor.appendChild(sb);
    }
    ACP.selectionBox = document.getElementById('selection-box');

    const agentsList = document.getElementById('agents-list');

    // ---- Agent List: Drag Start ----
    agentsList.addEventListener('dragstart', (e) => {
        const item = e.target.closest('.agent-tool-item');
        if (item) {
            ACP.draggedItemContent = item.dataset.content;
            e.dataTransfer.effectAllowed = 'copy';
            e.dataTransfer.setData('text/plain', ACP.draggedItemContent);
        }
    });

    // ---- Canvas: DragOver and Drop ----
    submonitor.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
    });

    submonitor.addEventListener('drop', (e) => {
        e.preventDefault();
        const content = e.dataTransfer.getData('text/plain');
        if (content) createCanvasItem(e.clientX, e.clientY, content);
    });

    // ---- Canvas Background: Deselect + Start Selection Box ----
    submonitor.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('input-triangle') ||
            e.target.classList.contains('output-triangle') ||
            e.target.classList.contains('connection-hit-area') ||
            e.target.closest('.canvas-item')) {
            return;
        }
        if (e.target === submonitor || e.target.id === 'connections-layer') {
            if (!e.ctrlKey) deselectAll();
            startSelectionBox(e);
        }
    });

    // ---- Canvas: Start Connection (mousedown on output-triangle) + Select Connection ----
    submonitor.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('output-triangle')) {
            e.preventDefault();
            e.stopPropagation();
            ACP.isConnecting = true;
            ACP.sourceNode = e.target.closest('.canvas-item');
            ACP.sourceOutputEl = e.target;
            const startPos = getCenter(e.target);
            const created = createConnectionGroup();
            ACP.tempPath = created;
            created.group.style.pointerEvents = 'none';
            setPathD(startPos.x, startPos.y, startPos.x, startPos.y, created.visiblePath, created.hitPath);
        } else if (e.target.classList.contains('connection-hit-area')) {
            e.stopPropagation();
            const group = e.target.closest('.connection-group');
            const conn = ACP.connections.find(c => c.path === group);
            if (conn) {
                if (e.ctrlKey) toggleConnectionSelection(conn);
                else selectConnection(conn, false);
                updateSaveButtonState();
            }
        }
    });

    // ---- Double-click on canvas item: open config editor ----
    submonitor.addEventListener('dblclick', async (e) => {
        const item = e.target.closest('.canvas-item');
        if (item) {
            e.preventDefault();
            e.stopPropagation();
            const agentId = item.id;

            const onConfigSaved = (savedData) => {
                console.log("Configuration saved:", savedData);
                ACP.nodeConfigs.set(agentId, savedData);
                markDirty();
            };

            try {
                const response = await fetch(`/agent/load_agent_config/${agentId}/`, { headers: getHeaders() });
                if (response.ok) {
                    const configData = await response.json();
                    ACP.nodeConfigs.set(agentId, configData);
                    preRenderCanvasItemDialog({ id: agentId, data: configData }, onConfigSaved);
                    renderCanvasItemDialog();
                } else {
                    console.warn("No config found for", agentId);
                    preRenderCanvasItemDialog({ id: agentId, data: {} }, onConfigSaved);
                    renderCanvasItemDialog();
                }
            } catch (err) {
                console.error("Error loading config:", err);
            }
        }
    });

    // ---- Window: Draw temporary connection line ----
    window.addEventListener('mousemove', (e) => {
        if (ACP.isConnecting && ACP.tempPath) {
            const startEl = ACP.sourceNode.querySelector('.output-triangle');
            const startPos = getCenter(startEl);
            const rect = submonitor.getBoundingClientRect();
            setPathD(startPos.x, startPos.y, e.clientX - rect.left, e.clientY - rect.top,
                ACP.tempPath.visiblePath, ACP.tempPath.hitPath);
        }
    });

    // ---- Window: Selection Box resize ----
    window.addEventListener('mousemove', (e) => {
        if (!ACP.isSelecting) return;
        const rect = submonitor.getBoundingClientRect();
        const currentX = e.clientX - rect.left;
        const currentY = e.clientY - rect.top;
        ACP.selectionBox.style.width = Math.abs(currentX - ACP.initialBoxX) + 'px';
        ACP.selectionBox.style.height = Math.abs(currentY - ACP.initialBoxY) + 'px';
        ACP.selectionBox.style.left = Math.min(currentX, ACP.initialBoxX) + 'px';
        ACP.selectionBox.style.top = Math.min(currentY, ACP.initialBoxY) + 'px';
    });

    // ---- Window: Finish connection / Finish selection box ----
    window.addEventListener('mouseup', (e) => {
        // --- Finalize Selection Box ---
        if (ACP.isSelecting) {
            ACP.isSelecting = false;
            const boxRect = ACP.selectionBox.getBoundingClientRect();
            if (parseFloat(ACP.selectionBox.style.width) > 5 || parseFloat(ACP.selectionBox.style.height) > 5) {
                document.querySelectorAll('.canvas-item').forEach(node => {
                    if (isIntersecting(boxRect, node.getBoundingClientRect())) {
                        ACP.selectedItems.add(node);
                        node.classList.add('selected');
                    }
                });
                ACP.connections.forEach(conn => {
                    if (isIntersecting(boxRect, conn.visiblePath.getBoundingClientRect())) {
                        ACP.selectedItems.add(conn);
                        conn.path.classList.add('selected');
                    }
                });
            }
            ACP.selectionBox.style.display = 'none';
        }

        // --- Finalize Connection ---
        if (ACP.isConnecting) {
            const targetEl = e.target;
            let created = false;

            if (targetEl.classList.contains('input-triangle')) {
                const targetNode = targetEl.closest('.canvas-item');
                const alreadyExists = ACP.connections.some(c => c.source === ACP.sourceNode && c.target === targetNode);

                if (ACP.sourceNode !== targetNode && !alreadyExists) {
                    const targetAgentName = targetNode.dataset.agentName || '';
                    const sourceAgentName = ACP.sourceNode.dataset.agentName || '';
                    const isTargetCleaner = targetAgentName.toLowerCase() === 'cleaner';
                    const isSourceEnder = sourceAgentName.toLowerCase() === 'ender';

                    if (isTargetCleaner && !isSourceEnder) {
                        alert('Invalid Connection: Cleaner Agent only accepts input from Ender Agents.');
                        ACP.tempPath.group.remove(); ACP.tempPath = null; ACP.isConnecting = false;
                        isBusyProcessing = false; document.body.classList.remove('connecting'); return;
                    }
                    if (isTargetCleaner && isSourceEnder) {
                        const existingInputs = ACP.connections.filter(c => c.target === targetNode);
                        if (existingInputs.length >= 1) {
                            alert('Invalid Connection: Cleaner Agent can only accept ONE Ender Agent connection.');
                            ACP.tempPath.group.remove(); ACP.tempPath = null; ACP.isConnecting = false;
                            isBusyProcessing = false; document.body.classList.remove('connecting'); return;
                        }
                    }
                    if (isSourceEnder && !isTargetCleaner) {
                        alert('Invalid Connection: Ender Agent outputs can ONLY connect to Cleaner Agents.');
                        ACP.tempPath.group.remove(); ACP.tempPath = null; ACP.isConnecting = false;
                        isBusyProcessing = false; document.body.classList.remove('connecting'); return;
                    }

                    // Finalize the connection
                    ACP.tempPath.group.style.pointerEvents = '';
                    const newConn = {
                        source: ACP.sourceNode, target: targetNode,
                        path: ACP.tempPath.group, visiblePath: ACP.tempPath.visiblePath, hitPath: ACP.tempPath.hitPath
                    };

                    newConn.inputSlot = targetEl.classList.contains('input-1') ? 1 :
                        (targetEl.classList.contains('input-2') ? 2 : 0);
                    newConn.outputSlot = (ACP.sourceOutputEl && ACP.sourceOutputEl.classList.contains('output-1')) ? 1 :
                        ((ACP.sourceOutputEl && ACP.sourceOutputEl.classList.contains('output-2')) ? 2 : 0);

                    ACP.connections.push(newConn);
                    updateAttachedConnections(targetNode);
                    created = true;
                    markDirty();

                    const sourceId = ACP.sourceNode.id;
                    const targetId = targetNode.id;

                    // Auto-configure all agent types
                    if (targetAgentName.toLowerCase() === 'raiser') updateRaiserConnection(targetId, 'source', sourceId, 'add');
                    if (targetAgentName.toLowerCase() === 'emailer') updateEmailerConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'raiser') updateRaiserConnection(sourceId, 'target', targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'monitor-log') updateMonitorLogConnection(targetId, sourceId, 'add');
                    // Only auto-configure Ender if the user has NOT already set it via the config dialog.
                    // User-saved config (ACP.nodeConfigs entry set by the dialog) always takes priority.
                    if (targetAgentName.toLowerCase() === 'ender') {
                        if (!ACP.nodeConfigs.has(targetId)) {
                            updateEnderConnection(targetId, ACP.sourceNode, 'add', 'input');
                        } else {
                            console.log(`--- Ender ${targetId} has user config — skipping auto input-connection update.`);
                        }
                    }
                    if (sourceAgentName.toLowerCase() === 'ender') {
                        if (!ACP.nodeConfigs.has(sourceId)) {
                            updateEnderConnection(sourceId, targetNode, 'add', 'output');
                        } else {
                            console.log(`--- Ender ${sourceId} has user config — skipping auto output-connection update.`);
                        }
                    }

                    if (targetAgentName.toLowerCase() !== 'ender') {
                        const downstreamEnders = findDownstreamEnders(targetNode);
                        for (const enderNode of downstreamEnders) {
                            if (!ACP.nodeConfigs.has(enderNode.id)) {
                                console.log(`--- Found downstream Ender: ${enderNode.id}, adding ${sourceId}`);
                                updateEnderConnection(enderNode.id, ACP.sourceNode, 'add');
                            } else {
                                console.log(`--- Downstream Ender ${enderNode.id} has user config — skipping auto-add.`);
                            }
                        }
                    }

                    if (sourceAgentName.toLowerCase() === 'starter') updateStarterConnection(sourceId, targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'croner') updateCronerConnection(targetId, 'source', sourceId, 'add');
                    if (sourceAgentName.toLowerCase() === 'croner') updateCronerConnection(sourceId, 'target', targetId, 'add');

                    if (targetAgentName.toLowerCase() === 'or') {
                        const slot = newConn.inputSlot === 1 ? 'source_1' : (newConn.inputSlot === 2 ? 'source_2' : null);
                        if (slot) updateOrAgentConnection(targetId, slot, sourceId, 'add');
                    }
                    if (sourceAgentName.toLowerCase() === 'or') updateOrAgentConnection(sourceId, 'target', targetId, 'add');

                    if (targetAgentName.toLowerCase() === 'and') {
                        const slot = newConn.inputSlot === 1 ? 'source_1' : (newConn.inputSlot === 2 ? 'source_2' : null);
                        if (slot) updateAndAgentConnection(targetId, slot, sourceId, 'add');
                    }
                    if (sourceAgentName.toLowerCase() === 'and') updateAndAgentConnection(sourceId, 'target', targetId, 'add');

                    if (targetAgentName.toLowerCase() === 'mover') updateMoverConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'mover') updateMoverConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'sleeper') updateSleeperConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'sleeper') updateSleeperConnection(sourceId, targetId, 'add', 'target');
                    if (sourceAgentName.toLowerCase() === 'shoter') updateShoterConnection(sourceId, targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'deleter') updateDeleterConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'deleter') updateDeleterConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'executer') updateExecuterConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'executer') updateExecuterConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'notifier') updateNotifierConnection(targetId, 'source', sourceId, 'add');
                    if (sourceAgentName.toLowerCase() === 'notifier') updateNotifierConnection(sourceId, 'target', targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'stopper') updateStopperConnection(targetId, 'source', sourceId, 'add');
                    if (sourceAgentName.toLowerCase() === 'stopper') updateStopperConnection(sourceId, 'output', targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'whatsapper') updateWhatsapperConnection(targetId, 'source', sourceId, 'add');
                    if (targetAgentName.toLowerCase() === 'telegramrx') updateTelegramrxConnection(targetId, sourceId, 'add', 'source');
                    if (targetAgentName.toLowerCase() === 'telegramer') updateTelegramerConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'telegramer') updateTelegramerConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'pythonxer') updatePythonxerConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'pythonxer') updatePythonxerConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'asker') updateAskerConnection(targetId, 'source', sourceId, 'add');
                    if (sourceAgentName.toLowerCase() === 'asker' && newConn.outputSlot === 1) updateAskerConnection(sourceId, 'target_a', targetId, 'add');
                    if (sourceAgentName.toLowerCase() === 'asker' && newConn.outputSlot === 2) updateAskerConnection(sourceId, 'target_b', targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'forker') updateForkerConnection(targetId, 'source', sourceId, 'add');
                    if (sourceAgentName.toLowerCase() === 'forker' && newConn.outputSlot === 1) updateForkerConnection(sourceId, 'target_a', targetId, 'add');
                    if (sourceAgentName.toLowerCase() === 'forker' && newConn.outputSlot === 2) updateForkerConnection(sourceId, 'target_b', targetId, 'add');
                    if (targetAgentName.toLowerCase() === 'ssher') updateSsherConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'ssher') updateSsherConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'scper') updateScperConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'scper') updateScperConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'sqler') updateSqlerConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'sqler') updateSqlerConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'prompter') updatePrompterConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'prompter') updatePrompterConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'gitter') updateGitterConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'gitter') updateGitterConnection(sourceId, targetId, 'add', 'target');
                    if (targetAgentName.toLowerCase() === 'dockerer') updateDockererConnection(targetId, sourceId, 'add', 'source');
                    if (sourceAgentName.toLowerCase() === 'dockerer') updateDockererConnection(sourceId, targetId, 'add', 'target');

                    // Record undo action for connection creation
                    const connState = captureConnectionState(newConn);
                    undoManager.record({
                        type: 'ADD_CONNECTION',
                        data: connState,
                        undo: async function () { await removeConnectionWithoutUndo(this.data.sourceId, this.data.targetId); },
                        redo: async function () { await recreateConnection(this.data); }
                    });
                }
            }

            if (!created && ACP.tempPath) ACP.tempPath.group.remove();
            ACP.isConnecting = false;
            ACP.tempPath = null;
            ACP.sourceNode = null;
        }
    });
}

// ========================================
// PUBLIC API
// ========================================

/**
 * Get all connections as simple {source, target} text pairs.
 */
window.getAgentConnections = function () {
    return ACP.connections.map(c => ({ source: c.source.innerText, target: c.target.innerText }));
};

/**
 * Clear all canvas items, connections, selections, and reset counters.
 */
window.clearAllCanvasItems = function () {
    const canvasItems = submonitor.querySelectorAll('.canvas-item');
    canvasItems.forEach(item => item.remove());

    ACP.connections.forEach(conn => { if (conn.path) conn.path.remove(); });
    ACP.connections.length = 0;

    ACP.selectedItems.clear();
    ACP.itemCounters.clear();

    updateSaveButtonState();
    markClean();
    console.log('--- All canvas items, connections and counters cleared');
};
