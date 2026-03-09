// ============================================================
// agent_page_state.js  –  Shared state & DOM element references
// ============================================================

// --- Parsed page data ---
const userUsername = JSON.parse(document.getElementById('user_username').textContent);

// --- Core DOM references ---
const chatLog = document.getElementById('chat-log');
const chatSocket = new WebSocket(
    'ws://' + window.location.host + '/ws/agent/'
);

// --- Mutable UI flags ---
let contextButtonClicked = false;
let canvasSettedAsContext = false;
let confirmationByUser = false; // eslint-disable-line no-unused-vars
let inLongOperation = false;
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

// --- Constants ---
const loadCatalogOfPrompts = null; // eslint-disable-line no-unused-vars
const spinnerId = 'wait-spinner';
const maximalTheoricTokens = 12500;
const MAX_MCPS = 32;
const MAX_TOOLS = 32;
const MAX_AGENTS = 50;

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
const mcp1 = document.getElementById('mcp-1'); // eslint-disable-line no-unused-vars
const mcp2 = document.getElementById('mcp-2'); // eslint-disable-line no-unused-vars
const label_mcp1 = document.getElementById('label-mcp-1');
const label_mcp2 = document.getElementById('label-mcp-2');
const toolMcpsList = document.getElementById('tool-mcps-list');
const agentsList = document.getElementById('agents-list');

// --- Initial button state ---
contextButton.disabled = true;
contextButton.style.backgroundColor = "#808080";
contextButton.textContent = "Use as context";
