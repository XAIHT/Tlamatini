// Agentic Control Panel - Global State & DOM References
// LOAD ORDER: #1 - Must be loaded before all other acp-*.js files.

// ---- DOM References (top-level, available globally) ----
const container    = document.getElementById('agents-container');
const canvas       = document.getElementById('monitor-container');
const submonitor   = document.getElementById('submonitor-container');
const chat         = document.getElementById('main-agents-container');
const divider      = document.getElementById('drag-divider');
const openBtn      = document.getElementById('file-open-button');
const fileCloseBtn = document.getElementById('file-close-button');
const saveBtn      = document.getElementById('save-as-button');
const filenameSpan = document.getElementById('filename');

// Control Panel Buttons
const btnStart = document.getElementById('btn-start');
const btnStop  = document.getElementById('btn-stop');
const btnPause = document.getElementById('btn-pause');
const btnClear = document.getElementById('btn-clear');

// ========================================
// GLOBAL RUNNING STATE MANAGEMENT
// ========================================
const GLOBAL_STATE = {
    STOPPED: 'STOPPED',
    RUNNING: 'RUNNING',
    PAUSED:  'PAUSED'
};
let globalRunningState = GLOBAL_STATE.STOPPED;

// Multi-array to store paused processes per session (keyed by session ID)
// Structure: { [sessionId]: [{ canvas_id, folder_name, script_name, pid, cmdline }, ...] }
const pausedProcessesOnPause = {};

// Title hourglass prefix - updated by polling logic
let titleBusyPrefix = "";

// FlowCreator waiting flag to show hourglass even if not polling
let isFlowCreatorWaiting = false;

// Busy flag to prevent double-clicks while processing
let isBusyProcessing = false;

// Unsaved changes flag
let hasUnsavedChanges = false;

// ========================================
// ACP SHARED CANVAS STATE NAMESPACE
// ========================================
// Variables that were previously local to the main IIFE are now in window.ACP
// so they can be accessed across multiple split files.
const ACP = window.ACP = {
    // Canvas data structures
    connections:   [],        // { source, target, path, visiblePath, hitPath, inputSlot, outputSlot }
    selectedItems: new Set(), // Selected DOM elements (.canvas-item) and connection objects
    itemCounters:  new Map(), // baseName -> count (for unique ID generation)
    nodeConfigs:   new Map(), // nodeId -> configData (agent config cache)

    // SVG connection layer (DOM element - set during canvas init)
    svgLayer: null,

    // Selection box (DOM element - set during canvas init)
    selectionBox:  null,
    isSelecting:   false,
    initialBoxX:   0,
    initialBoxY:   0,

    // Connection drawing state
    tempPath:       null,
    isConnecting:   false,
    sourceNode:     null,
    sourceOutputEl: null,  // Which output triangle was clicked (for Asker/Forker dual outputs)

    // Divider/layout state (local to acp-layout.js but stored here for access if needed)
    seamPct: 0,

    // Agent list drag state
    draggedItemContent: null,
    MAX_AGENTS: 50,
};

// Expose nodeConfigs to global scope for contextual menus (backward compatibility)
window.nodeConfigs = ACP.nodeConfigs;

// ========================================
// FILE STATE HELPERS
// ========================================
// These are defined here (early) so all canvas/control files can call them.

/**
 * Update the save button enabled/disabled state based on canvas content.
 */
function updateSaveButtonState() {
    if (!saveBtn) return;
    const hasItems = submonitor.querySelectorAll('.canvas-item').length > 0;
    if (hasItems) {
        saveBtn.classList.remove('disabled');
        saveBtn.setAttribute('aria-disabled', 'false');
    } else {
        saveBtn.classList.add('disabled');
        saveBtn.setAttribute('aria-disabled', 'true');
    }
}

/**
 * Update the filename display in the header.
 * @param {string|null} filename - The filename to display (with .flw extension), or null to clear.
 */
function updateFilenameDisplay(filename) {
    if (!filenameSpan) return;
    if (filename) {
        filenameSpan.textContent = `<< ${filename} >>`;
    } else {
        filenameSpan.textContent = '';
    }
}

function markDirty() {
    hasUnsavedChanges = true;
    updateSaveButtonState();
}

function markClean() {
    hasUnsavedChanges = false;
}

// Warn user about unsaved changes when leaving the page
window.addEventListener('beforeunload', (e) => {
    if (hasUnsavedChanges) {
        e.preventDefault();
        e.returnValue = ''; // Chrome requires returnValue to be set
    }
});
