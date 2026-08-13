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

// Agentic Control Panel - Global State & DOM References
// LOAD ORDER: #1 - Must be loaded before all other acp-*.js files.

// ---- DOM References (top-level, available globally) ----
const container = document.getElementById('agents-container');
const canvas = document.getElementById('monitor-container');
const submonitor = document.getElementById('submonitor-container');
const canvasContent = document.getElementById('canvas-content');
const chat = document.getElementById('main-agents-container');
const divider = document.getElementById('drag-divider');
const openBtn = document.getElementById('file-open-button');
const fileCloseBtn = document.getElementById('file-close-button');
const saveBtn = document.getElementById('save-as-button');
const filenameSpan = document.getElementById('filename');

// Control Panel Buttons
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const btnPause = document.getElementById('btn-pause');
const btnClear = document.getElementById('btn-clear');
const btnValidate = document.getElementById('btn-validate');

// ========================================
// GLOBAL RUNNING STATE MANAGEMENT
// ========================================
const GLOBAL_STATE = {
    STOPPED: 'STOPPED',
    RUNNING: 'RUNNING',
    PAUSED: 'PAUSED'
};
let globalRunningState = GLOBAL_STATE.STOPPED;

// Flow validation state
const VALIDATION_STATE = {
    VALID: 'VALID',
    INVALID: 'INVALID',
    NOT_VALIDATED: 'NOT-VALIDATED'
};
let flowValidationStatus = VALIDATION_STATE.NOT_VALIDATED;

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
    connections: [],        // { source, target, path, visiblePath, hitPath, inputSlot, outputSlot }
    selectedItems: new Set(), // Selected DOM elements (.canvas-item) and connection objects
    itemCounters: new Map(), // baseName -> count (for unique ID generation)
    nodeConfigs: new Map(), // nodeId -> configData (agent config cache)

    // SVG connection layer (DOM element - set during canvas init)
    svgLayer: null,

    // Selection box (DOM element - set during canvas init)
    selectionBox: null,
    isSelecting: false,
    initialBoxX: 0,
    initialBoxY: 0,

    // Connection drawing state
    tempPath: null,
    isConnecting: false,
    sourceNode: null,
    sourceOutputEl: null,  // Which output triangle was clicked (for Asker/Forker dual outputs)

    // Divider/layout state (local to acp-layout.js but stored here for access if needed)
    seamPct: 0,

    // Agent list drag state
    draggedItemContent: null,
    MAX_AGENTS: 128,
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
/**
 * Recompute #canvas-content's bounding size so the viewport shows scrollbars
 * whenever items extend beyond it. Never shrinks below 100% of the viewport.
 * Call after: item creation, drag end, .flw load, undo/redo item restoration.
 */
function updateCanvasContentSize() { // eslint-disable-line no-unused-vars
    if (!canvasContent || !submonitor) return;
    const margin = 240; // headroom so the user can always drop beyond current extent
    let maxRight = submonitor.clientWidth;
    let maxBottom = submonitor.clientHeight;
    const items = canvasContent.querySelectorAll('.canvas-item');
    items.forEach(item => {
        const right = item.offsetLeft + item.offsetWidth;
        const bottom = item.offsetTop + item.offsetHeight;
        if (right > maxRight) maxRight = right;
        if (bottom > maxBottom) maxBottom = bottom;
    });
    // Only set pixel sizes when content exceeds viewport; otherwise clear to let
    // the CSS min-width/min-height:100% rule track viewport size automatically.
    if (maxRight > submonitor.clientWidth) {
        canvasContent.style.width = (maxRight + margin) + 'px';
    } else {
        canvasContent.style.width = '';
    }
    if (maxBottom > submonitor.clientHeight) {
        canvasContent.style.height = (maxBottom + margin) + 'px';
    } else {
        canvasContent.style.height = '';
    }
}

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

/**
 * Read the currently displayed diagram filename from the ACP header.
 * @returns {string} Filename including extension, or empty string when none is shown.
 */
function getDisplayedDiagramFilename() {
    if (!filenameSpan) return '';
    const rawText = String(filenameSpan.textContent || '').trim();
    const match = rawText.match(/^<<\s*(.+?)\s*>>$/);
    return match ? match[1].trim() : '';
}

/**
 * Read the configured default filename from the FlowCreator node, if present.
 * @returns {string} FlowCreator filename candidate, or empty string when unset.
 */
function getFlowCreatorConfiguredFilename() {
    const flowCreatorConfig = ACP.nodeConfigs.get('flowcreator');
    if (!flowCreatorConfig || typeof flowCreatorConfig.flow_filename !== 'string') {
        return '';
    }
    return flowCreatorConfig.flow_filename.trim();
}

/**
 * Resolve the default filename to show in the ACP Save As prompt.
 * Priority:
 * 1. FlowCreator's configured flow_filename
 * 2. Currently displayed diagram filename
 * 3. Generic fallback
 * @returns {string} Default filename suggestion for Save As.
 */
function getDefaultDiagramSaveFilename() {
    const flowCreatorFilename = getFlowCreatorConfiguredFilename();
    if (flowCreatorFilename) {
        return flowCreatorFilename;
    }

    const displayedFilename = getDisplayedDiagramFilename();
    if (displayedFilename) {
        return displayedFilename;
    }

    return 'diagram';
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

// ============================================================
// DIALOG BUTTONS — the ACP mirror of agent_page_dialogs.js
// ------------------------------------------------------------
// Angela, 2026-08-12. jQuery `.css()` writes INLINE styles, which
// beat every stylesheet — so while the canvas dialogs painted their
// own buttons, `dialog_theme.css` was powerless over them and this
// page kept its old footer no matter how correct the CSS was.
//
// Three things were being done inline, and all three are gone:
//
//   1. `buttonPane.css({background:'none', border:'none'})` — this
//      ERASED the footer BAR (chrome fill + top hairline), which is
//      the single most recognisable half of the reference dialog;
//   2. Cancel was painted teal (or #777) — in the reference the pair
//      is teal-primary + outlined-secondary, so painting both made
//      them both read as "confirm";
//   3. `height: '4vh'` — a viewport-relative button height, i.e. the
//      one control in the app that resized with the window (43px on
//      1080p, 26px on a laptop).
//
// So: the PRIMARY button is the only thing still painted inline, it
// matches `--tlm-dlg-accent`, and everything else is left to the CSS.
// Keep this object byte-compatible with DIALOG_BUTTON_CSS on the chat
// page — `agent/test_dialog_theme.py` pins both.
// ============================================================

// ============================================================
// NATIVE POPUP REPLACEMENTS — acpAlert / acpConfirm
// ------------------------------------------------------------
// Angela, 2026-08-12: the canvas raised ~20 `window.alert()` boxes and one
// `window.confirm()` — "Only one FlowCreator agent is allowed per flow",
// "Invalid Connection: ...", "This will permanently delete all deployed
// agents...". Those are OS-CHROME popups: a grey Windows/Chrome strip with
// the page's URL in it, in the middle of a dark themed application. No
// amount of CSS could ever touch them, and they are the loudest possible
// "this is a different program" moment — louder than any of the eight
// private skins, because they are not even the same rendering engine.
//
// They also BLOCK: a native dialog freezes the page and stalls automation,
// which is why the Clear button could not be photographed at all.
//
// These two render the SAME jQuery-UI dialog every other canvas dialog
// uses, so they inherit dialog_theme.css for free. Both fail OPEN to the
// native popup if the markup is missing — a lost warning is worse than an
// ugly one.
// ============================================================

function _acpModal(primary, secondary, buttons, title) {
    const host = document.getElementById('confirmation-dialog-message');
    const primaryEl = document.getElementById('confirmation-primary-dialog-legend');
    const secondaryEl = document.getElementById('confirmation-secondary-dialog-legend');
    if (!host || !primaryEl || !secondaryEl || typeof $ !== 'function') return null;

    primaryEl.textContent = primary || '';
    primaryEl.style.display = primary ? '' : 'none';
    secondaryEl.textContent = secondary || '';

    const $host = $(host);
    if ($host.hasClass('ui-dialog-content')) {
        $host.dialog('destroy');
    }
    $host.dialog({
        title: title || 'Tlamatini',
        modal: true,
        width: 480,
        resizable: false,
        draggable: true,
        closeText: '',
        buttons: buttons,
        open: function () {
            styleAcpDialogButtons($(this).parent().find('.ui-dialog-buttonpane'));
        }
    });
    return $host;
}

/** Themed replacement for `window.alert`. */
function acpAlert(message, title) {                // eslint-disable-line no-unused-vars
    const $host = _acpModal('', String(message == null ? '' : message), [{
        text: 'OK',
        click: function () { $(this).dialog('close'); }
    }], title);
    if (!$host) {
        window.alert(message);                     // fail open — never lose a warning
    }
}

/**
 * Themed replacement for `window.confirm`. Returns a Promise<boolean>.
 * Closing the dialog any other way resolves FALSE: a destructive action is
 * never taken because a dialog was dismissed.
 */
function acpConfirm(primary, secondary, title) {   // eslint-disable-line no-unused-vars
    return new Promise((resolve) => {
        let decided = false;
        const finish = (value) => {
            if (!decided) { decided = true; resolve(value); }
        };
        const $host = _acpModal(primary, secondary, [
            {
                text: 'Cancel',
                click: function () { finish(false); $(this).dialog('close'); }
            },
            {
                text: 'Continue',
                click: function () { finish(true); $(this).dialog('close'); }
            }
        ], title || 'Please confirm');
        if (!$host) {
            finish(window.confirm([primary, secondary].filter(Boolean).join('\n\n')));
            return;
        }
        $host.off('dialogclose.acpconfirm')
            .on('dialogclose.acpconfirm', () => finish(false));
    });
}

const ACP_DIALOG_BUTTON_CSS = {
    'background-color': '#55BBAA',
    'color': 'white',
    'border-radius': '6px',
    'font-size': '0.88rem'
};

/**
 * Paint the CONFIRM button of a jQuery-UI dialog teal, and leave every
 * other button to dialog_theme.css.
 *
 * @param {jQuery} [$scope] Optional button-pane (or dialog) to limit the
 *   search to. Omit it to style the whole page, which is what the
 *   chat page's styleDialogButtons() does.
 */
function styleAcpDialogButtons($scope) {
    const selector = 'button:contains("Save"), button:contains("Go!"), '
        + 'button:contains("Continue"), button:contains("OK"), '
        + 'button:contains("Proceed"), button:contains("Start"), '
        + 'button:contains("Run")';
    const $buttons = $scope && $scope.length
        ? $scope.find(selector)
        : $('.ui-dialog-buttonpane').find(selector);
    $buttons.css(ACP_DIALOG_BUTTON_CSS);
}
