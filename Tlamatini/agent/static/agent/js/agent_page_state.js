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

// ============================================================
// agent_page_state.js  –  Shared state & DOM element references
// ============================================================

// --- Parsed page data ---
const userUsername = JSON.parse(document.getElementById('user_username').textContent);

function getCookie(name) {
    const cookieValue = `; ${document.cookie}`;
    const parts = cookieValue.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift() || '';
    }
    return '';
}

function getCsrfToken() {
    return getCookie('csrftoken');
}

function sendPostBeacon(url, fields = {}) {
    const formData = new FormData();
    const csrfToken = getCsrfToken();
    if (csrfToken) {
        formData.append('csrfmiddlewaretoken', csrfToken);
    }

    Object.entries(fields).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
            formData.append(key, value);
        }
    });

    return navigator.sendBeacon(url, formData);
}

// --- Core DOM references ---
const chatLog = document.getElementById('chat-log');
const connectionStatusBar = document.getElementById('connection-status');
const defaultChatInputPlaceholder = 'Send a message...';

function buildAgentSocketUrl() {
    const socketProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${socketProtocol}//${window.location.host}/ws/agent/`;
}

const chatSocket = new WebSocket(buildAgentSocketUrl());

// Buffer messages received between WebSocket creation (here) and the real
// onmessage handler being installed in agent_page_chat.js (5 script tags
// later). The server's `session-restored` frame — which carries the
// loading=true flag that drives the context-load spinner — is sent
// immediately on connect; without this buffer, it lands in the WebSocket
// before chat.js binds .onmessage and is silently dropped, leaving the
// auto-load lifecycle without its spinner. The handler in chat.js drains
// _pendingChatSocketMessages after binding.
const _pendingChatSocketMessages = [];  
chatSocket.onmessage = function (e) {
    _pendingChatSocketMessages.push(e);
};

function setConnectionStatus(message, tone = 'warning') {
    if (!connectionStatusBar) {
        return;
    }

    connectionStatusBar.textContent = message || '';
    connectionStatusBar.classList.remove('connection-status-hidden', 'connection-status-warning', 'connection-status-ok');
    connectionStatusBar.classList.add(`connection-status-${tone}`);
}

function clearConnectionStatus() {
    if (!connectionStatusBar) {
        return;
    }

    connectionStatusBar.textContent = '';
    connectionStatusBar.classList.add('connection-status-hidden');
    connectionStatusBar.classList.remove('connection-status-warning', 'connection-status-ok');
}

function applyDisconnectedSocketUi(message) {
    if (typeof setTitleBusy === 'function') {
        setTitleBusy(false);
    }

    const existingSpinner = document.getElementById(spinnerId);
    if (existingSpinner && existingSpinner.parentNode) {
        existingSpinner.parentNode.removeChild(existingSpinner);
    }

    if (chatInput) {
        chatInput.disabled = true;
        chatInput.readOnly = true;
        chatInput.style.backgroundColor = 'gray';
        chatInput.placeholder = 'Connection lost. Use Reconnect or refresh before continue.';
    }

    if (chatSubmitButton) {
        chatSubmitButton.disabled = true;
        chatSubmitButton.textContent = 'Disconnected';
    }

    if (reConnectButton) {
        reConnectButton.disabled = false;
    }

    inLongOperation = false;
    lapseLoadingContext = false;
    setConnectionStatus(message || 'Live connection lost. Use Reconnect or refresh before continuing.', 'warning');
}

function restoreConnectedSocketUi() {
    clearConnectionStatus();

    if (!chatInput || !chatSubmitButton) {
        return;
    }

    chatInput.disabled = false;
    chatInput.placeholder = defaultChatInputPlaceholder;

    if (!inLongOperation) {
        chatInput.readOnly = false;
        chatInput.style.backgroundColor = '#40414F';
        chatSubmitButton.disabled = false;
        chatSubmitButton.textContent = 'Send';
    }
}

function isChatSocketOpen() {
    return !!chatSocket && chatSocket.readyState === WebSocket.OPEN;
}

function sendChatSocketMessage(payload, disconnectedMessage = 'Live connection lost. Use Reconnect or refresh before continue.') {
    if (!isChatSocketOpen()) {
        console.error('WebSocket is not connected. Message not sent.', payload);
        applyDisconnectedSocketUi(disconnectedMessage);
        return false;
    }

    try {
        const message = typeof payload === 'string' ? payload : JSON.stringify(payload);
        chatSocket.send(message);
        clearConnectionStatus();
        return true;
    } catch (err) {
        console.error('Failed to send WebSocket message:', err);
        applyDisconnectedSocketUi(disconnectedMessage);
        return false;
    }
}

// --- Mutable UI flags ---
let contextButtonClicked = false;
let canvasSettedAsContext = false;
let confirmationByUser = false; // eslint-disable-line no-unused-vars
let inLongOperation = false;
// Set the moment the user CONFIRMS Cancel on a running request; cleared on the next
// submit (and on Reconnect / Clean-History, which are full UI resets). While it is
// true, a LATE self-healing "Tactic #…" frame from the dying executor must NOT put the
// UI back into the busy state — that is exactly what flipped the Send button back to
// "Cancel" by itself, over and over, forever. See agent_page_chat.js::appendChatMessage.
// MUST stay `let` — it is reassigned from agent_page_init.js AND agent_page_chat.js. A
// `const` lints green per-file and then throws "Assignment to constant variable" in the
// browser, killing the chat page (the 2026-07-08 const-poison incident).
let userCancelledRun = false;
let canvasLoaded = false;
let openEnabled = true;
let reConnectEnabled = true;
let contextEnabled = true;
let cleanCanvasEnabled = true;
let actualContextDir = null;
let lapseLoadingContext = false;
let clearContextEnabled = false;
let cleanHistoryEnabled = true;
let fileTypeOmissions = "";
// MUST stay `let` — agent_page_canvas.js replaces the <code> element (to drop stale
// listeners) and reassigns this handle. A `const` here lints green per-file and then
// throws "Assignment to constant variable" in the browser. See the const-poison
// contract in docs/claude/frontend.md.
let textEditorCode = document.querySelector('#text-editor code');
let chatHistory = [];
let historyIndex = 0;
let tempInput = '';
let buildingInitial = false; // eslint-disable-line no-unused-vars
let titleBusyPrefix = "";
let mcp1_enabled = false;
let mcp2_enabled = false;
let tools = [];
let agents = [];
let skills = []; // populated by `type: 'skill'` system messages — see agent_page_chat.js

// --- Constants ---
const loadCatalogOfPrompts = null; // eslint-disable-line no-unused-vars
const spinnerId = 'wait-spinner';
const maximalTheoricTokens = 12500;
const MAX_MCPS = 32;
const MULTI_TURN_STORAGE_KEY = 'multiTurnEnabled';
const EXEC_REPORT_STORAGE_KEY = 'execReportEnabled';
const ACPX_STORAGE_KEY = 'acpxEnabled';
const ASK_EXECS_STORAGE_KEY = 'askExecsEnabled';
const STEP_BY_STEP_STORAGE_KEY = 'stepByStepEnabled';

// --- Static DOM references ---
const textEditorPre = document.querySelector('#text-editor pre');
const lineNumbers = document.getElementById('line-numbers');
const openButton = document.getElementById('open-button');
const saveAsButton = document.getElementById('save-as-button');
const contextButton = document.getElementById('context-button');
const cleanCanvasButton = document.getElementById('clean-canvas-button');
const chatInput = document.getElementById('chat-message-input');
const chatSubmitButton = document.getElementById('chat-message-submit');
const logoutButton = document.getElementById('logout-button');
const reopenOpenCanvasButton = document.getElementById('reopen-canvas-button');
const copyCanvasButton = document.getElementById('copy-canvas-button');
const confirmationDialogMessage = document.getElementById('confirmation-dialog-message');
const confirmationPrimaryDialogLegend = document.getElementById('confirmation-primary-dialog-legend');
const confirmationSecondaryDialogLegend = document.getElementById('confirmation-secondary-dialog-legend');
const reConnectButton = document.getElementById('re-connect-button');
const cleanHistoryButton = document.getElementById('clean-history');
const multiTurnCheckbox = document.getElementById('multi-turn-enabled');
const execReportCheckbox = document.getElementById('exec-report-enabled');
const execReportToggleLabel = document.getElementById('exec-report-toggle');
const acpxCheckbox = document.getElementById('acpx-enabled');
const askExecsCheckbox = document.getElementById('ask-execs-enabled');
const askExecsToggleLabel = document.getElementById('ask-execs-toggle');
const stepByStepCheckbox = document.getElementById('step-by-step-enabled');
const contextMenuButton = document.getElementById('context-menu-button');
const mcpsMenuButton = document.getElementById('mcps-menu-button');
const agentsMenuButton = document.getElementById('agents-menu-button');
const filenameDivRight = document.getElementById('filename-div-right'); // eslint-disable-line no-unused-vars
const filenameDivLeft = document.getElementById('filename-div-left'); // eslint-disable-line no-unused-vars
const filenameSpan = document.getElementById('filename'); // eslint-disable-line no-unused-vars
const setDirContextMenu = document.getElementById('set-dir-context');
const setFileContextMenu = document.getElementById('set-file-context');
const viewContextDirInCanvasMenu = document.getElementById('view-context-dir-in-canvas');
const contextInfoDiv = document.getElementById('contextInfo');
const contextDataSpan = document.getElementById('contextData');
const contextMobile = document.getElementById("contextMobile");
const clearContextButton = document.getElementById('clear-context');
const omissionsDialogMessage = document.getElementById('omissions-dialog-message');
const omissionsPrimaryDialogLegend = document.getElementById('omissions-primary-dialog-legend');
const omissionsSecondaryDialogLegend = document.getElementById('omissions-secondary-dialog-legend');
const omissionContentInput = document.getElementById("fileTypeOmissions");
const mcpsDialogMessage = document.getElementById('mcps-dialog-message');
const mcpsPrimaryDialogLegend = document.getElementById('mcps-primary-dialog-legend');
const mcpsSecondaryDialogLegend = document.getElementById('mcps-secondary-dialog-legend');
const mcpsThirdtiaryDialogLegend = document.getElementById('mcps-thirdtiary-dialog-legend');
const agentsDialogMessage = document.getElementById('agents-dialog-message');
const agentsPrimaryDialogLegend = document.getElementById('agents-primary-dialog-legend');
const agentsSecondaryDialogLegend = document.getElementById('agents-secondary-dialog-legend');
const configModelsDialogMessage = document.getElementById('config-models-dialog-message'); // eslint-disable-line no-unused-vars
const configModelsPrimaryDialogLegend = document.getElementById('config-models-primary-dialog-legend'); // eslint-disable-line no-unused-vars
const configModelsSecondaryDialogLegend = document.getElementById('config-models-secondary-dialog-legend'); // eslint-disable-line no-unused-vars
const configModelsForm = document.getElementById('config-models-form'); // eslint-disable-line no-unused-vars
const configUrlsDialogMessage = document.getElementById('config-urls-dialog-message'); // eslint-disable-line no-unused-vars
const configUrlsPrimaryDialogLegend = document.getElementById('config-urls-primary-dialog-legend'); // eslint-disable-line no-unused-vars
const configUrlsSecondaryDialogLegend = document.getElementById('config-urls-secondary-dialog-legend'); // eslint-disable-line no-unused-vars
const configUrlsForm = document.getElementById('config-urls-form'); // eslint-disable-line no-unused-vars
const configReconnectRequiredDialogMessage = document.getElementById('config-reconnect-required-dialog-message'); // eslint-disable-line no-unused-vars
const configReconnectRequiredPrimaryDialogLegend = document.getElementById('config-reconnect-required-primary-dialog-legend'); // eslint-disable-line no-unused-vars
const configReconnectRequiredSecondaryDialogLegend = document.getElementById('config-reconnect-required-secondary-dialog-legend'); // eslint-disable-line no-unused-vars
const configMenuButton = document.getElementById('config-menu-button');
const backupDbDialogMessage = document.getElementById('backup-db-dialog-message'); // eslint-disable-line no-unused-vars
const backupDbPrimaryDialogLegend = document.getElementById('backup-db-primary-dialog-legend'); // eslint-disable-line no-unused-vars
const backupDbSecondaryDialogLegend = document.getElementById('backup-db-secondary-dialog-legend'); // eslint-disable-line no-unused-vars
const backupDbForm = document.getElementById('backup-db-form'); // eslint-disable-line no-unused-vars
const backupDbTargetDirInput = document.getElementById('backup-db-target-dir'); // eslint-disable-line no-unused-vars
const backupDbStatusElement = document.getElementById('backup-db-status'); // eslint-disable-line no-unused-vars
const setDbDialogMessage = document.getElementById('set-db-dialog-message'); // eslint-disable-line no-unused-vars
const setDbPrimaryDialogLegend = document.getElementById('set-db-primary-dialog-legend'); // eslint-disable-line no-unused-vars
const setDbSecondaryDialogLegend = document.getElementById('set-db-secondary-dialog-legend'); // eslint-disable-line no-unused-vars
const setDbForm = document.getElementById('set-db-form'); // eslint-disable-line no-unused-vars
const setDbSourcePathInput = document.getElementById('set-db-source-path'); // eslint-disable-line no-unused-vars
const setDbStatusElement = document.getElementById('set-db-status'); // eslint-disable-line no-unused-vars
const setDbWarningDialogMessage = document.getElementById('set-db-warning-dialog-message'); // eslint-disable-line no-unused-vars
const setDbWarningPrimaryDialogLegend = document.getElementById('set-db-warning-primary-dialog-legend'); // eslint-disable-line no-unused-vars
const setDbWarningSecondaryDialogLegend = document.getElementById('set-db-warning-secondary-dialog-legend'); // eslint-disable-line no-unused-vars
const mcp1 = document.getElementById('mcp-1'); // eslint-disable-line no-unused-vars
const mcp2 = document.getElementById('mcp-2'); // eslint-disable-line no-unused-vars
const label_mcp1 = document.getElementById('label-mcp-1');
const label_mcp2 = document.getElementById('label-mcp-2');
const toolMcpsList = document.getElementById('tool-mcps-list');
const agentsList = document.getElementById('agents-list');

function isMultiTurnEnabled() { // eslint-disable-line no-unused-vars
    return !!(multiTurnCheckbox && multiTurnCheckbox.checked);
}

function persistMultiTurnState(enabled) { // eslint-disable-line no-unused-vars
    try {
        sessionStorage.setItem(MULTI_TURN_STORAGE_KEY, enabled ? 'true' : 'false');
    } catch (err) {
        console.error('Failed to persist multi-turn state:', err);
    }
}

function applyStoredMultiTurnState() { // eslint-disable-line no-unused-vars
    if (!multiTurnCheckbox) {
        return;
    }

    let enabled = false;
    try {
        enabled = sessionStorage.getItem(MULTI_TURN_STORAGE_KEY) === 'true';
    } catch (err) {
        console.error('Failed to restore multi-turn state:', err);
    }

    multiTurnCheckbox.checked = enabled;
}

function isExecReportEnabled() { // eslint-disable-line no-unused-vars
    // Exec report is a modifier of Multi-Turn — return false whenever
    // Multi-Turn is off so the backend can short-circuit all capture work.
    if (!multiTurnCheckbox || !multiTurnCheckbox.checked) {
        return false;
    }
    return !!(execReportCheckbox && execReportCheckbox.checked);
}

function persistExecReportState(enabled) { // eslint-disable-line no-unused-vars
    try {
        sessionStorage.setItem(EXEC_REPORT_STORAGE_KEY, enabled ? 'true' : 'false');
    } catch (err) {
        console.error('Failed to persist exec-report state:', err);
    }
}

function applyStoredExecReportState() { // eslint-disable-line no-unused-vars
    if (!execReportCheckbox) {
        return;
    }

    let enabled = false;
    try {
        enabled = sessionStorage.getItem(EXEC_REPORT_STORAGE_KEY) === 'true';
    } catch (err) {
        console.error('Failed to restore exec-report state:', err);
    }

    execReportCheckbox.checked = enabled;
}

function isAcpxEnabled() { // eslint-disable-line no-unused-vars
    return !!(acpxCheckbox && acpxCheckbox.checked);
}

function persistAcpxState(enabled) { // eslint-disable-line no-unused-vars
    try {
        sessionStorage.setItem(ACPX_STORAGE_KEY, enabled ? 'true' : 'false');
    } catch (err) {
        console.error('Failed to persist ACPX state:', err);
    }
}

function applyStoredAcpxState() { // eslint-disable-line no-unused-vars
    if (!acpxCheckbox) {
        return;
    }

    // Default OFF: when nothing has been persisted yet, leave ACPX disabled
    // so Tlamatini boots into the legacy Multi-Turn / one-shot behavior. The
    // user has to explicitly tick the box to opt into the ACPX-aided flow.
    let enabled = false;
    try {
        const stored = sessionStorage.getItem(ACPX_STORAGE_KEY);
        if (stored !== null) {
            enabled = stored === 'true';
        }
    } catch (err) {
        console.error('Failed to restore ACPX state:', err);
    }

    acpxCheckbox.checked = enabled;
}

// --- Ask-Execs (per-tool permission prompt) — Multi-Turn-only modifier ---
function isAskExecsEnabled() { // eslint-disable-line no-unused-vars
    // Ask-Execs only has meaning inside Multi-Turn (the permission prompt
    // lives in the multi-turn executor loop), so return false whenever
    // Multi-Turn is off — mirrors isExecReportEnabled().
    if (!multiTurnCheckbox || !multiTurnCheckbox.checked) {
        return false;
    }
    return !!(askExecsCheckbox && askExecsCheckbox.checked);
}

function persistAskExecsState(enabled) { // eslint-disable-line no-unused-vars
    try {
        sessionStorage.setItem(ASK_EXECS_STORAGE_KEY, enabled ? 'true' : 'false');
    } catch (err) {
        console.error('Failed to persist Ask-Execs state:', err);
    }
}

function applyStoredAskExecsState() { // eslint-disable-line no-unused-vars
    if (!askExecsCheckbox) {
        return;
    }
    let enabled = false;
    try {
        enabled = sessionStorage.getItem(ASK_EXECS_STORAGE_KEY) === 'true';
    } catch (err) {
        console.error('Failed to restore Ask-Execs state:', err);
    }
    askExecsCheckbox.checked = enabled;
}

// Enable the Ask-Execs checkbox ONLY when Multi-Turn is checked. When
// Multi-Turn is off the box is disabled + visually greyed (the backend
// ignores the flag anyway, but the UI must make the dependency obvious).
function syncAskExecsAvailability() { // eslint-disable-line no-unused-vars
    if (!askExecsCheckbox) {
        return;
    }
    const multiTurnOn = !!(multiTurnCheckbox && multiTurnCheckbox.checked);
    askExecsCheckbox.disabled = !multiTurnOn;
    if (askExecsToggleLabel) {
        askExecsToggleLabel.classList.toggle('toolbar-toggle-disabled', !multiTurnOn);
    }
}

// Enable the Exec-report checkbox ONLY when Multi-Turn is checked. Exec report
// is a Multi-Turn modifier (the backend already short-circuits capture when
// Multi-Turn is off — see isExecReportEnabled()), so the UI must make the
// dependency obvious: off Multi-Turn → the box is disabled + visually greyed.
// Mirrors syncAskExecsAvailability() exactly.
function syncExecReportAvailability() { // eslint-disable-line no-unused-vars
    if (!execReportCheckbox) {
        return;
    }
    const multiTurnOn = !!(multiTurnCheckbox && multiTurnCheckbox.checked);
    execReportCheckbox.disabled = !multiTurnOn;
    if (execReportToggleLabel) {
        execReportToggleLabel.classList.toggle('toolbar-toggle-disabled', !multiTurnOn);
    }
}

// --- Step-by-Step (interactive setup / troubleshooting mode) ---
function isStepByStepEnabled() { // eslint-disable-line no-unused-vars
    return !!(stepByStepCheckbox && stepByStepCheckbox.checked);
}

function persistStepByStepState(enabled) { // eslint-disable-line no-unused-vars
    try {
        sessionStorage.setItem(STEP_BY_STEP_STORAGE_KEY, enabled ? 'true' : 'false');
    } catch (err) {
        console.error('Failed to persist Step-by-Step state:', err);
    }
}

function applyStoredStepByStepState() { // eslint-disable-line no-unused-vars
    if (!stepByStepCheckbox) {
        return;
    }
    let enabled = false;
    try {
        enabled = sessionStorage.getItem(STEP_BY_STEP_STORAGE_KEY) === 'true';
    } catch (err) {
        console.error('Failed to restore Step-by-Step state:', err);
    }
    stepByStepCheckbox.checked = enabled;
}

// --- Open in... dropdown references ---
const openInDropdownItem = document.getElementById('open-in-dropdown-item');
const openInMenuButton = document.getElementById('open-in-menu-button');
const openInMenuList = document.getElementById('open-in-menu-list');
let installedApps = [];

// --- Initial button state ---
contextButton.disabled = true;
contextButton.style.backgroundColor = "#808080";
contextButton.textContent = "Use as context";


