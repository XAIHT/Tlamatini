/**
 * Contextual Menus for Agentic Control Panel
 * Handles right-click context menus and log viewer modal for canvas agents
 */
/* global openParametrizerDialog */

// ========================================
// CONTEXT MENU STATE
// ========================================
let currentContextMenuItem = null;
let logViewerPollingInterval = null;
const LOG_POLL_INTERVAL = 500; // Poll every 500ms for fast updates
let logViewerUserScrolledUp = false; // Track if user has scrolled up manually

// ========================================
// CONTEXT MENU INITIALIZATION
// ========================================
document.addEventListener('DOMContentLoaded', () => {
    initContextMenu();
    initLogViewerModal();
    initDescriptionDialog();
});

function initContextMenu() {
    const contextMenu = document.getElementById('agent-context-menu');
    const submonitor = document.getElementById('submonitor-container');

    if (!contextMenu || !submonitor) {
        console.warn('Context menu or submonitor not found');
        return;
    }

    // Right-click on canvas items
    submonitor.addEventListener('contextmenu', (e) => {
        const canvasItem = e.target.closest('.canvas-item');
        if (canvasItem) {
            e.preventDefault();
            e.stopPropagation();
            showContextMenu(e.clientX, e.clientY, canvasItem);
        }
    });

    // Hide context menu on click outside
    document.addEventListener('click', (e) => {
        if (!contextMenu.contains(e.target)) {
            hideContextMenu();
        }
    });

    // Hide context menu on scroll
    submonitor.addEventListener('scroll', () => {
        hideContextMenu();
    });

    // Hide context menu on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            hideContextMenu();
            hideLogViewer();
            hideDescriptionDialog();
        }
    });

    // Menu item: Configure
    const configureMenuItem = document.getElementById('ctx-menu-configure');
    if (configureMenuItem) {
        configureMenuItem.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (currentContextMenuItem) {
                openConfigureDialog(currentContextMenuItem);
            }
            hideContextMenu();
        });
    }

    // Menu item: Description
    const descriptionMenuItem = document.getElementById('ctx-menu-description');
    if (descriptionMenuItem) {
        descriptionMenuItem.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (currentContextMenuItem) {
                openDescriptionDialog(currentContextMenuItem);
            }
            hideContextMenu();
        });
    }

    // Menu item: See last lines of log
    const logMenuItem = document.getElementById('ctx-menu-view-log');
    if (logMenuItem) {
        logMenuItem.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (currentContextMenuItem) {
                openLogViewer(currentContextMenuItem);
            }
            hideContextMenu();
        });
    }

    // Menu item: Explore agent instance directory
    const explorerMenuItem = document.getElementById('ctx-menu-open-explorer');
    if (explorerMenuItem) {
        explorerMenuItem.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (currentContextMenuItem) {
                await openInstancedAgentInApp(currentContextMenuItem, 'explorer');
            }
            hideContextMenu();
        });
    }

    // Menu item: Open CMD in agent instance directory
    const cmdMenuItem = document.getElementById('ctx-menu-open-cmd');
    if (cmdMenuItem) {
        cmdMenuItem.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (currentContextMenuItem) {
                await openInstancedAgentInApp(currentContextMenuItem, 'cmd');
            }
            hideContextMenu();
        });
    }

    // Menu item: Restart
    const restartMenuItem = document.getElementById('ctx-menu-restart');
    if (restartMenuItem) {
        restartMenuItem.addEventListener('click', async (e) => {
            e.preventDefault();
            e.stopPropagation();
            // Only act if not disabled
            if (!restartMenuItem.classList.contains('context-menu-item-disabled') && currentContextMenuItem) {
                await restartAgent(currentContextMenuItem);
            }
            hideContextMenu();
        });
    }
}

async function openInstancedAgentInApp(canvasItem, appId) {
    const formData = new FormData();
    formData.append('csrfmiddlewaretoken', getCsrfToken());
    formData.append('app_id', appId);
    formData.append('agent_name', canvasItem.id);

    try {
        const response = await fetch('/agent/open_in_app/', {
            method: 'POST',
            body: formData,
            headers: getHeaders(),
            credentials: 'same-origin'
        });

        const result = await response.json();
        if (!response.ok || result.error) {
            throw new Error(result.error || `Failed to open ${canvasItem.id}`);
        }
    } catch (err) {
        console.error(`[OPEN_IN_APP] Error opening ${canvasItem.id} in ${appId}:`, err);
        alert(`Error opening ${canvasItem.id}: ${err.message}`);
    }
}

function showContextMenu(x, y, canvasItem) {
    const contextMenu = document.getElementById('agent-context-menu');
    if (!contextMenu) return;

    currentContextMenuItem = canvasItem;

    // Update Restart menu item enabled state
    updateRestartMenuItemState(canvasItem);

    // Position menu at mouse coordinates
    contextMenu.style.left = x + 'px';
    contextMenu.style.top = y + 'px';
    contextMenu.style.display = 'block';

    // Ensure menu stays within viewport
    const menuRect = contextMenu.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    if (menuRect.right > viewportWidth) {
        contextMenu.style.left = (x - menuRect.width) + 'px';
    }
    if (menuRect.bottom > viewportHeight) {
        contextMenu.style.top = (y - menuRect.height) + 'px';
    }
}

/**
 * Update the Restart menu item enabled/disabled state.
 * Enabled only when: globalRunningState is RUNNING AND the agent's LED is off (agent is down)
 */
function updateRestartMenuItemState(canvasItem) {
    const restartMenuItem = document.getElementById('ctx-menu-restart');
    if (!restartMenuItem) return;

    // Check conditions:
    // 1. Global state must be RUNNING
    // 2. The specific agent must be down (LED shows led-off)
    const isGlobalRunning = typeof globalRunningState !== 'undefined' && globalRunningState === GLOBAL_STATE.RUNNING;
    const agentLed = canvasItem.querySelector('.canvas-item-led');
    const isAgentDown = agentLed && agentLed.classList.contains('led-off'); // eslint-disable-line no-unused-vars

    if (isGlobalRunning) {
        // Enable the Restart option
        restartMenuItem.classList.remove('context-menu-item-disabled');
    } else {
        // Disable the Restart option
        restartMenuItem.classList.add('context-menu-item-disabled');
    }
}

/**
 * Restart (start) a single agent by calling the backend endpoint.
 */
async function restartAgent(canvasItem) {
    const agentId = canvasItem.id;

    try {
        console.log(`[RESTART] Restarting agent: ${agentId}`);

        const response = await fetch(`/agent/restart_agent/${agentId}/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...getHeaders()
            },
            credentials: 'same-origin'
        });

        const result = await response.json();

        if (result.success) {
            console.log(`[RESTART] Successfully started ${agentId}: PID ${result.pid}`);
        } else {
            console.error(`[RESTART] Failed to start ${agentId}: ${result.message}`);
            alert(`Failed to restart agent: ${result.message}`);
        }
    } catch (err) {
        console.error(`[RESTART] Error restarting ${agentId}:`, err);
        alert(`Error restarting agent: ${err.message}`);
    }
}

function hideContextMenu() {
    const contextMenu = document.getElementById('agent-context-menu');
    if (contextMenu) {
        contextMenu.style.display = 'none';
    }
    currentContextMenuItem = null;
}

function initDescriptionDialog() {
    const descriptionDialog = document.getElementById('agent-description-dialog');
    const closeBtn = document.getElementById('agent-description-close');
    const overlay = document.getElementById('agent-description-overlay');

    if (!descriptionDialog) {
        console.warn('Agent description dialog not found');
        return;
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            hideDescriptionDialog();
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            hideDescriptionDialog();
        });
    }

    makeElementDraggable(descriptionDialog, document.getElementById('agent-description-header'));
}

function renderAgentDescriptionHtml(descriptionText) {
    const escapedText = String(descriptionText || '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');

    return escapedText
        .replace(/&lt;br\s*\/?&gt;/gi, '<br>')
        .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
        .replace(/`(.+?)`/g, '<code>$1</code>');
}

window.renderAgentDescriptionHtml = renderAgentDescriptionHtml;

function openDescriptionDialog(canvasItem) {
    const agentName = canvasItem.dataset.agentName || canvasItem.textContent.trim() || canvasItem.id;
    const descriptionDialog = document.getElementById('agent-description-dialog');
    const descriptionOverlay = document.getElementById('agent-description-overlay');
    const descriptionTitle = document.getElementById('agent-description-title');
    const descriptionContent = document.getElementById('agent-description-content');
    const purpose = canvasItem.dataset.agentPurpose || '';

    if (!descriptionDialog || !descriptionOverlay || !descriptionContent) {
        console.error('Agent description dialog elements not found');
        return;
    }

    if (descriptionTitle) {
        descriptionTitle.textContent = `Description: ${agentName}`;
    }

    if (purpose) {
        descriptionContent.innerHTML = renderAgentDescriptionHtml(purpose);
    } else {
        descriptionContent.textContent = 'No description was found for this agent in README.md.';
    }

    descriptionOverlay.style.display = 'block';
    descriptionDialog.style.display = 'flex';
    descriptionDialog.style.top = '50%';
    descriptionDialog.style.left = '50%';
    descriptionDialog.style.transform = 'translate(-50%, -50%)';
    descriptionDialog.style.margin = '';
}

function hideDescriptionDialog() {
    const descriptionDialog = document.getElementById('agent-description-dialog');
    const descriptionOverlay = document.getElementById('agent-description-overlay');

    if (descriptionDialog) {
        descriptionDialog.style.display = 'none';
    }
    if (descriptionOverlay) {
        descriptionOverlay.style.display = 'none';
    }
}

// ========================================
// CONFIGURE DIALOG (reuses existing logic)
// ========================================
async function openConfigureDialog(canvasItem) {
    const agentId = canvasItem.id;
    const agentDesc = (canvasItem.dataset.agentName || '').toLowerCase();

    // Intercept Parametrizer to show custom mapping dialog
    if (agentDesc === 'parametrizer') {
        if (typeof openParametrizerDialog === 'function') {
            openParametrizerDialog(agentId);
        } else {
            console.error('openParametrizerDialog function not found');
        }
        return;
    }

    // Callback to store config when saved (same as double-click behavior)
    const onConfigSaved = (savedData) => {
        console.log("Configuration saved from context menu:", savedData);
        // Update global nodeConfigs if available (for Save As consistency)
        if (typeof nodeConfigs !== 'undefined') {
            nodeConfigs.set(agentId, savedData);
        }
        // Trigger dirty state if available
        if (typeof markDirty === 'function') {
            markDirty();
        }
    };

    try {
        const response = await fetch(`/agent/load_agent_config/${agentId}/`, {
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        if (response.ok) {
            const configData = await response.json();

            // FIX: Sanitize Ender Config Display
            // If it's an Ender agent, hide any "cleaner" agents from the target list in the UI
            // This ensures that when the user saves, the clean list is persisted.
            const agentName = canvasItem.textContent.trim().toLowerCase();
            if (agentName.startsWith('ender') && configData.source_agents && Array.isArray(configData.source_agents)) {
                const originalLength = configData.source_agents.length;
                configData.source_agents = configData.source_agents.filter(
                    agent => !agent.toLowerCase().includes('cleaner')
                );
                if (configData.source_agents.length !== originalLength) {
                    console.log("Sanitized Ender config for dialog display (removed cleaner).");
                }
            }

            // Use existing dialog functions from canvas_item_dialog.js
            if (typeof preRenderCanvasItemDialog === 'function' && typeof renderCanvasItemDialog === 'function') {
                preRenderCanvasItemDialog({
                    id: agentId,
                    data: configData
                }, onConfigSaved);
                renderCanvasItemDialog();
            } else {
                console.error('Canvas item dialog functions not found');
            }
        } else {
            console.warn("No config found for", agentId);
            if (typeof preRenderCanvasItemDialog === 'function' && typeof renderCanvasItemDialog === 'function') {
                preRenderCanvasItemDialog({
                    id: agentId,
                    data: {}
                }, onConfigSaved);
                renderCanvasItemDialog();
            }
        }
    } catch (err) {
        console.error("Error loading config:", err);
    }
}

// ========================================
// LOG VIEWER MODAL
// ========================================
function initLogViewerModal() {
    const logViewer = document.getElementById('log-viewer-dialog');
    const closeBtn = document.getElementById('log-viewer-close');
    const overlay = document.getElementById('log-viewer-overlay');
    const logContent = document.getElementById('log-viewer-content');

    if (!logViewer) {
        console.warn('Log viewer dialog not found');
        return;
    }

    // Close button
    if (closeBtn) {
        closeBtn.addEventListener('click', () => {
            hideLogViewer();
        });
    }

    // Click on overlay to close
    if (overlay) {
        overlay.addEventListener('click', () => {
            hideLogViewer();
        });
    }

    // Track user scroll to prevent auto-scroll from overriding manual scroll
    if (logContent) {
        logContent.addEventListener('scroll', () => {
            const threshold = 30; // px from bottom to consider "at the bottom"
            const isAtBottom = (logContent.scrollHeight - logContent.scrollTop - logContent.clientHeight) <= threshold;
            logViewerUserScrolledUp = !isAtBottom;
        });
    }

    // Make dialog draggable
    makeElementDraggable(logViewer, document.getElementById('log-viewer-header'));
}

/**
 * Make an element draggable via a handle
 * Handles the transition from CSS transform centering to absolute positioning
 */
function makeElementDraggable(element, handle) {
    if (!element || !handle) return;

    let isDragging = false;
    let startX, startY;
    let initialLeft, initialTop;

    handle.style.cursor = 'move';

    handle.addEventListener('mousedown', (e) => {
        if (e.target.closest('button')) return; // Ignore close button clicks

        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;

        // If element is centered with transform, switch to absolute pixel positioning
        const computedStyle = window.getComputedStyle(element);
        const transform = computedStyle.transform;

        // Check if transform is active (matrix(...) or translate(...))
        if (transform && transform !== 'none') {
            const rect = element.getBoundingClientRect();
            element.style.transform = 'none';
            element.style.left = rect.left + 'px';
            element.style.top = rect.top + 'px';
            element.style.margin = '0'; // Clear any margins that might affect pos
        }

        // Get current position (now guaranteed to be numeric pixels or parseable)
        initialLeft = parseFloat(element.style.left) || 0;
        initialTop = parseFloat(element.style.top) || 0;

        // Add temporary listeners to window for smooth drag outside element
        window.addEventListener('mousemove', onMouseMove);
        window.addEventListener('mouseup', onMouseUp);

        // Prevent text selection
        e.preventDefault();
    });

    function onMouseMove(e) {
        if (!isDragging) return;

        const dx = e.clientX - startX;
        const dy = e.clientY - startY;

        element.style.left = `${initialLeft + dx}px`;
        element.style.top = `${initialTop + dy}px`;
    }

    function onMouseUp() {
        isDragging = false;
        window.removeEventListener('mousemove', onMouseMove);
        window.removeEventListener('mouseup', onMouseUp);
    }
}

async function openLogViewer(canvasItem) {
    const agentId = canvasItem.id;
    const agentName = canvasItem.textContent.trim() || agentId;

    const logViewer = document.getElementById('log-viewer-dialog');
    const logOverlay = document.getElementById('log-viewer-overlay');
    const logTitle = document.getElementById('log-viewer-title');
    const logContent = document.getElementById('log-viewer-content');

    if (!logViewer || !logOverlay) {
        console.error('Log viewer elements not found');
        return;
    }

    // Set title
    if (logTitle) {
        logTitle.textContent = `Log: ${agentName}`;
    }

    // Clear content and show loading
    if (logContent) {
        logContent.textContent = 'Loading log...';
    }

    // Show overlay and dialog IMMEDIATELY (don't wait for fetch)
    logOverlay.style.display = 'block';
    logViewer.style.display = 'flex';

    // Reset position logic to default (center) if it was moved previously?
    // User often prefers it remembers the last position, but if it's off screen...
    // Let's reset to center for consistency on re-open, as 'transform' is easier to restore.
    logViewer.style.top = '50%';
    logViewer.style.left = '50%';
    logViewer.style.transform = 'translate(-50%, -50%)';
    logViewer.style.margin = '';

    // Store agent ID for polling
    logViewer.dataset.agentId = agentId;

    // Reset user scroll tracking so the initial load scrolls to bottom
    logViewerUserScrolledUp = false;

    // Update Live indicator based on running state
    updateLiveIndicator();

    // Start polling IMMEDIATELY for fast updates (polling will do the initial fetch)
    startLogPolling(agentId, true);
}

/**
 * Update the Live indicator in the log viewer based on global running state.
 * Green and animated when RUNNING, gray when STOPPED.
 */
function updateLiveIndicator() {
    const liveDot = document.querySelector('.log-viewer-live-dot');
    const liveText = document.querySelector('.log-viewer-live-indicator span:last-child');
    const liveIndicator = document.querySelector('.log-viewer-live-indicator');

    if (!liveDot || !liveIndicator) return;

    // Check global running state (defined in agentic_control_panel.js)
    const isRunning = typeof globalRunningState !== 'undefined' && globalRunningState === GLOBAL_STATE.RUNNING;

    if (isRunning) {
        // Green and animated
        liveDot.classList.remove('live-stopped');
        liveDot.classList.add('live-running');
        liveIndicator.classList.remove('indicator-stopped');
        liveIndicator.classList.add('indicator-running');
        if (liveText) liveText.textContent = 'Live';
    } else {
        // Gray and static
        liveDot.classList.remove('live-running');
        liveDot.classList.add('live-stopped');
        liveIndicator.classList.remove('indicator-running');
        liveIndicator.classList.add('indicator-stopped');
        if (liveText) liveText.textContent = 'Stopped';
    }
}

function hideLogViewer() {
    const logViewer = document.getElementById('log-viewer-dialog');
    const logOverlay = document.getElementById('log-viewer-overlay');

    if (logViewer) {
        logViewer.style.display = 'none';
    }
    if (logOverlay) {
        logOverlay.style.display = 'none';
    }

    // Stop polling
    stopLogPolling();
}

async function fetchAndDisplayLog(agentId) {
    const logContent = document.getElementById('log-viewer-content');
    if (!logContent) return;

    try {
        const response = await fetch(`/agent/read_agent_log/${agentId}/`, {
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        const result = await response.json();

        if (result.success && result.lines && result.lines.length > 0) {
            logContent.textContent = result.lines.join('\n');
            // Only auto-scroll to bottom if the user hasn't scrolled up
            if (!logViewerUserScrolledUp) {
                logContent.scrollTop = logContent.scrollHeight;
            }
        } else if (result.success && (!result.lines || result.lines.length === 0)) {
            logContent.textContent = '(Log file is empty)';
        } else {
            logContent.textContent = result.message || 'No log file found yet.\n\nThe log file will be created when the agent starts running.';
        }
    } catch (err) {
        console.error('Error fetching log:', err);
        logContent.textContent = 'Error loading log: ' + err.message;
    }
}

function startLogPolling(agentId, fetchImmediately = false) {
    // Clear any existing interval
    stopLogPolling();

    // If requested, fetch immediately without waiting for first interval
    if (fetchImmediately) {
        fetchAndDisplayLog(agentId);
    }

    // Poll at regular intervals for fast updates
    logViewerPollingInterval = setInterval(() => {
        const logViewer = document.getElementById('log-viewer-dialog');
        // Only poll if dialog is still visible and for the same agent
        if (logViewer && logViewer.style.display !== 'none' && logViewer.dataset.agentId === agentId) {
            fetchAndDisplayLog(agentId);
            // Also update the Live indicator in case running state changed
            updateLiveIndicator();
        } else {
            stopLogPolling();
        }
    }, LOG_POLL_INTERVAL);
}

function stopLogPolling() {
    if (logViewerPollingInterval) {
        clearInterval(logViewerPollingInterval);
        logViewerPollingInterval = null;
    }
}
