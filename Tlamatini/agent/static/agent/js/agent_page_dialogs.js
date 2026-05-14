// ============================================================
// agent_page_dialogs.js  –  jQuery UI dialogs & loader helpers
// ============================================================

const DIALOG_BUTTON_CSS = {
    'background-color': '#55BBAA',
    'color': 'white',
    'border-radius': '8px',
    'font-size': '1em',
    'height': '4vh'
};

/**
 * Apply consistent styling to dialog buttons.
 */
function styleDialogButtons() {
    $('.ui-dialog-buttonpane button:contains("Continue")').css(DIALOG_BUTTON_CSS);
    $('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
}

/**
 * Compute a grid layout (columns + dialog width) for a checkbox list that
 * never exceeds the viewport. Returns {cols, width}.
 *
 * Why: the previous formula (`cols = ceil(sqrt(N * 1.618))`, `width = cols * 220`)
 * had no upper bound. With 60+ wrapped chat-agent tools the dialog grew past
 * 2000 px and clipped the right edge off-screen on a 1280-wide window.
 *
 * How to apply: golden-ratio still picks the natural shape, but the width is
 * clamped to 90vw, then cols is reduced (down to a 1-col minimum) until each
 * column gets at least `minColWidth` px of usable space inside the dialog.
 */
function computeCheckboxGridLayout(itemCount, options = {}) {
    const minDialogWidth = options.minDialogWidth || 450;
    const minColWidth = options.minColWidth || 200;
    const dialogChrome = options.dialogChrome || 60; // padding + scrollbar room
    const viewportCap = Math.max(minDialogWidth, Math.floor(window.innerWidth * 0.9));

    if (itemCount <= 10) {
        return { cols: 1, width: minDialogWidth };
    }

    let cols = Math.max(2, Math.ceil(Math.sqrt(itemCount * 1.618)));
    let width = Math.max(minDialogWidth, cols * (minColWidth + 20));

    if (width > viewportCap) {
        width = viewportCap;
        const usable = Math.max(minColWidth, width - dialogChrome);
        cols = Math.max(1, Math.floor(usable / minColWidth));
    }
    return { cols, width };
}

/**
 * Build the standard two-button array for jQuery UI dialogs.
 */
function makeDialogButtons(callbackOnContinue, callbackOnCancel) {
    return [
        {
            text: "Continue",
            click: function () {
                console.log("Continue...");
                confirmationByUser = true;
                $(this).dialog("close");
                if (callbackOnContinue != null) {
                    callbackOnContinue();
                }
            }
        },
        {
            text: "Cancel",
            click: function () {
                console.log("Cancel...");
                confirmationByUser = false;
                $(this).dialog("close");
                if (callbackOnCancel != null) {
                    callbackOnCancel();
                }
            }
        }
    ];
}

// ----------------------------------------------------------------
// Confirmation dialog
// ----------------------------------------------------------------

function preRenderConfirmationDialog(message, primaryDialogText, secondaryDialogText, callbackOnContinue = null, callbackOnCancel = null) {
    console.log("--- preRenderConfirmationDialog called with callbacks:", callbackOnContinue != null, callbackOnCancel != null);
    confirmationDialogMessage.title = message;
    confirmationPrimaryDialogLegend.innerText = primaryDialogText;
    confirmationSecondaryDialogLegend.innerText = secondaryDialogText;

    // Destroy existing dialog to ensure new callbacks are used
    try {
        if ($("#confirmation-dialog-message").hasClass('ui-dialog-content')) {
            $("#confirmation-dialog-message").dialog("destroy");
        }
    } catch (e) {
        console.log("Dialog destroy ignored:", e);
    }

    $("#confirmation-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 450,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Continue")').css(DIALOG_BUTTON_CSS);
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeDialogButtons(callbackOnContinue, callbackOnCancel)
    });
}

function renderConfirmationDialog() {
    confirmationByUser = false;
    styleDialogButtons();
    $("#confirmation-dialog-message").dialog("open");
}

// ----------------------------------------------------------------
// Omissions dialog
// ----------------------------------------------------------------

function preRenderOmissionsDialog(message, primaryDialogText, secondaryDialogText, callbackOnContinue = null, callbackOnCancel = null) {
    omissionsDialogMessage.title = message;
    omissionsPrimaryDialogLegend.innerText = primaryDialogText;
    omissionsSecondaryDialogLegend.innerText = secondaryDialogText;

    $("#omissions-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 450,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Continue")').css(DIALOG_BUTTON_CSS);
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeDialogButtons(callbackOnContinue, callbackOnCancel)
    });
    loadOmission('omission-1');
}

function renderOmissionsDialog() {
    confirmationByUser = false;
    styleDialogButtons();
    $("#omissions-dialog-message").dialog("open");
}

// ----------------------------------------------------------------
// MCPs dialog
// ----------------------------------------------------------------

function preRenderMcpsDialog(message, primaryDialogText, secondaryDialogText, thirtiaryDialogText, callbackOnContinue = null, callbackOnCancel = null) {
    mcpsDialogMessage.title = message;
    mcpsPrimaryDialogLegend.innerText = primaryDialogText;
    mcpsSecondaryDialogLegend.innerText = secondaryDialogText;
    mcpsThirdtiaryDialogLegend.innerText = thirtiaryDialogText;

    $("#mcps-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 450,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () {
            document.body.style.overflow = 'hidden';

            const { cols, width: dialogWidth } = computeCheckboxGridLayout(tools.length);
            $(this).dialog("option", "width", dialogWidth);
            $(this).dialog("option", "maxWidth", Math.floor(window.innerWidth * 0.9));
            $(this).dialog("option", "maxHeight", Math.floor(window.innerHeight * 0.9));

            // Apply Grid Layout to the list container
            toolMcpsList.style.display = 'grid';
            toolMcpsList.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
            toolMcpsList.style.gap = '8px 15px'; // row gap, column gap
            toolMcpsList.style.listStyleType = 'none'; // Remove bullets
            toolMcpsList.style.padding = '0';
            toolMcpsList.style.margin = '15px 0';
            toolMcpsList.style.maxHeight = '60vh'; // Prevent it from getting too tall before scrolling
            toolMcpsList.style.overflowY = 'auto'; // allow scroll if needed
            toolMcpsList.style.overflowX = 'hidden';

            // Clear and rebuild the tool MCPs list each time the dialog opens
            toolMcpsList.innerHTML = '';
            for (const tool of tools) {
                const listElement = document.createElement('li');
                listElement.style.minWidth = '0';
                const checkbox = document.createElement('input');
                const label = document.createElement('label');
                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';
                wrapper.style.marginBottom = '4px';
                wrapper.style.minWidth = '0';

                checkbox.type = 'checkbox';
                checkbox.id = tool.name;
                checkbox.style.marginRight = '8px';
                checkbox.style.accentColor = '#55BBAA';
                checkbox.style.flexShrink = '0';

                label.htmlFor = tool.name;
                label.innerText = tool.description;
                label.setAttribute('id', 'label-' + tool.name);
                label.style.color = '#fff';
                label.style.cursor = 'pointer';
                label.style.margin = '0';
                label.style.fontSize = '0.95em';
                label.style.wordBreak = 'break-word';
                label.style.overflowWrap = 'anywhere';
                label.style.minWidth = '0';
                
                wrapper.appendChild(checkbox);
                wrapper.appendChild(label);
                listElement.appendChild(wrapper);
                
                if (tool.enabled === true) {
                    checkbox.checked = true;
                }
                toolMcpsList.appendChild(listElement);
            }
            // Load tool states after rebuilding the list
            loadTools().then(() => {
                 // Re-center after content loads
                 $(this).dialog("option", "position", { my: "center", at: "center", of: window });
            });
        },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Continue")').css(DIALOG_BUTTON_CSS);
            $('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeDialogButtons(callbackOnContinue, callbackOnCancel)
    });
    loadMcps();
}

function renderMcpsDialog() {
    confirmationByUser = false;
    styleDialogButtons();
    $("#mcps-dialog-message").dialog("open");
    // Ensure centering whenever rendered
    $("#mcps-dialog-message").dialog("option", "position", { my: "center", at: "center", of: window });
}

// ----------------------------------------------------------------
// Agents dialog
// ----------------------------------------------------------------

function preRenderAgentsDialog(message, primaryDialogText, secondaryDialogText, callbackOnContinue = null, callbackOnCancel = null) {
    agentsDialogMessage.title = message;
    agentsPrimaryDialogLegend.innerText = primaryDialogText;
    agentsSecondaryDialogLegend.innerText = secondaryDialogText;

    $("#agents-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 450,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () {
            document.body.style.overflow = 'hidden';

            const { cols, width: dialogWidth } = computeCheckboxGridLayout(agents.length);
            $(this).dialog("option", "width", dialogWidth);
            $(this).dialog("option", "maxWidth", Math.floor(window.innerWidth * 0.9));
            $(this).dialog("option", "maxHeight", Math.floor(window.innerHeight * 0.9));

            // Apply Grid Layout
            agentsList.style.display = 'grid';
            agentsList.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
            agentsList.style.gap = '8px 15px';
            agentsList.style.listStyleType = 'none';
            agentsList.style.padding = '0';
            agentsList.style.margin = '15px 0';
            agentsList.style.maxHeight = '60vh';
            agentsList.style.overflowY = 'auto';
            agentsList.style.overflowX = 'hidden';

            // Clear and rebuild the agents list each time the dialog opens
            agentsList.innerHTML = '';
            for (const agent of agents) {
                const listElement = document.createElement('li');
                listElement.style.minWidth = '0';
                const checkbox = document.createElement('input');
                const label = document.createElement('label');
                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';
                wrapper.style.marginBottom = '4px';
                wrapper.style.minWidth = '0';

                checkbox.type = 'checkbox';
                checkbox.id = agent.name;
                checkbox.style.marginRight = '8px';
                checkbox.style.accentColor = '#55BBAA';
                checkbox.style.flexShrink = '0';

                label.htmlFor = agent.name;
                // Use description if available, fallback to upper-cased name
                label.innerText = agent.description || (agent.name.charAt(0).toUpperCase() + agent.name.slice(1));
                label.setAttribute('id', 'label-' + agent.name);
                label.style.color = '#fff';
                label.style.cursor = 'pointer';
                label.style.margin = '0';
                label.style.fontSize = '0.95em';
                label.style.wordBreak = 'break-word';
                label.style.overflowWrap = 'anywhere';
                label.style.minWidth = '0';
                
                wrapper.appendChild(checkbox);
                wrapper.appendChild(label);
                listElement.appendChild(wrapper);
                
                if (agent.enabled === true) {
                    checkbox.checked = true;
                }
                agentsList.appendChild(listElement);
            }
            // Load agent states after rebuilding the list
            loadAgents().then(() => {
                // Re-center after content loads
                $(this).dialog("option", "position", { my: "center", at: "center", of: window });
            });
        },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Continue")').css(DIALOG_BUTTON_CSS);
            $('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeDialogButtons(callbackOnContinue, callbackOnCancel)
    });
}

function renderAgentsDialog() {
    confirmationByUser = false;
    styleDialogButtons();
    $("#agents-dialog-message").dialog("open");
    // Ensure centering whenever rendered
    $("#agents-dialog-message").dialog("option", "position", { my: "center", at: "center", of: window });
}

// ----------------------------------------------------------------
// Config dialogs (Models / URLs)
// ----------------------------------------------------------------

/**
 * Build a Save/Cancel button pair for the config dialogs. The "Save"
 * callback returns a Promise<boolean>: when it resolves to ``true`` the
 * dialog closes; when ``false`` the dialog stays open so the user can
 * correct the invalid inputs and try again.
 */
function makeSaveCancelButtons(asyncOnSave, onCancel) {
    return [
        {
            text: "Save",
            click: function () {
                const $dlg = $(this);
                const saveBtn = $dlg.parent().find('.ui-dialog-buttonpane button:contains("Save")');
                const cancelBtn = $dlg.parent().find('.ui-dialog-buttonpane button:contains("Cancel")');
                saveBtn.prop('disabled', true);
                cancelBtn.prop('disabled', true);
                Promise.resolve()
                    .then(() => (asyncOnSave ? asyncOnSave() : true))
                    .then(success => {
                        saveBtn.prop('disabled', false);
                        cancelBtn.prop('disabled', false);
                        if (success === true) {
                            $dlg.dialog("close");
                        }
                    })
                    .catch(err => {
                        console.error('Save handler threw:', err);
                        saveBtn.prop('disabled', false);
                        cancelBtn.prop('disabled', false);
                    });
            }
        },
        {
            text: "Cancel",
            click: function () {
                $(this).dialog("close");
                if (onCancel != null) {
                    onCancel();
                }
            }
        }
    ];
}

function _styleSaveCancelButtons() {
    $('.ui-dialog-buttonpane button:contains("Save")').css(DIALOG_BUTTON_CSS);
    $('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
}

function preRenderConfigModelsDialog(message, primaryText, secondaryText) { // eslint-disable-line no-unused-vars
    configModelsDialogMessage.title = message;
    configModelsPrimaryDialogLegend.innerText = primaryText;
    configModelsSecondaryDialogLegend.innerText = secondaryText;

    try {
        if ($("#config-models-dialog-message").hasClass('ui-dialog-content')) {
            $("#config-models-dialog-message").dialog("destroy");
        }
    } catch (e) {
        console.log("config-models dialog destroy ignored:", e);
    }

    $("#config-models-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 600,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Save")').css(DIALOG_BUTTON_CSS);
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeSaveCancelButtons(typeof _saveConfigModels === 'function' ? _saveConfigModels : null, null)
    });
}

function renderConfigModelsDialog() { // eslint-disable-line no-unused-vars
    _styleSaveCancelButtons();
    $("#config-models-dialog-message").dialog("open");
    $("#config-models-dialog-message").dialog("option", "position", { my: "center", at: "center", of: window });
    _styleSaveCancelButtons();
}

function preRenderConfigUrlsDialog(message, primaryText, secondaryText) { // eslint-disable-line no-unused-vars
    configUrlsDialogMessage.title = message;
    configUrlsPrimaryDialogLegend.innerText = primaryText;
    configUrlsSecondaryDialogLegend.innerText = secondaryText;

    try {
        if ($("#config-urls-dialog-message").hasClass('ui-dialog-content')) {
            $("#config-urls-dialog-message").dialog("destroy");
        }
    } catch (e) {
        console.log("config-urls dialog destroy ignored:", e);
    }

    $("#config-urls-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 600,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Save")').css(DIALOG_BUTTON_CSS);
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeSaveCancelButtons(typeof _saveConfigUrls === 'function' ? _saveConfigUrls : null, null)
    });
}

function renderConfigUrlsDialog() { // eslint-disable-line no-unused-vars
    _styleSaveCancelButtons();
    $("#config-urls-dialog-message").dialog("open");
    $("#config-urls-dialog-message").dialog("option", "position", { my: "center", at: "center", of: window });
    _styleSaveCancelButtons();
}

function preRenderReconnectRequiredDialog(message, primaryText, secondaryText) { // eslint-disable-line no-unused-vars
    configReconnectRequiredDialogMessage.title = message;
    configReconnectRequiredPrimaryDialogLegend.innerText = primaryText;
    configReconnectRequiredSecondaryDialogLegend.innerText = secondaryText;

    try {
        if ($("#config-reconnect-required-dialog-message").hasClass('ui-dialog-content')) {
            $("#config-reconnect-required-dialog-message").dialog("destroy");
        }
    } catch (e) {
        console.log("config-reconnect-required dialog destroy ignored:", e);
    }

    $("#config-reconnect-required-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 520,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("OK")').css(DIALOG_BUTTON_CSS);
        },
        buttons: [
            {
                text: "OK",
                click: function () {
                    $(this).dialog("close");
                }
            }
        ]
    });
}

function renderReconnectRequiredDialog() { // eslint-disable-line no-unused-vars
    $('.ui-dialog-buttonpane button:contains("OK")').css(DIALOG_BUTTON_CSS);
    $("#config-reconnect-required-dialog-message").dialog("open");
    $("#config-reconnect-required-dialog-message").dialog("option", "position", { my: "center", at: "center", of: window });
    $('.ui-dialog-buttonpane button:contains("OK")').css(DIALOG_BUTTON_CSS);
}

// ----------------------------------------------------------------
// Backup database dialog
// ----------------------------------------------------------------

/**
 * Build a Backup/Cancel button pair. Same async-Promise convention as the
 * Save/Cancel pair used by the Config dialogs: when ``asyncOnBackup``
 * resolves to ``true`` the dialog closes; when ``false`` it stays open.
 */
function makeBackupCancelButtons(asyncOnBackup, onCancel) { // eslint-disable-line no-unused-vars
    return [
        {
            text: "Backup",
            click: function () {
                const $dlg = $(this);
                const backupBtn = $dlg.parent().find('.ui-dialog-buttonpane button:contains("Backup")');
                const cancelBtn = $dlg.parent().find('.ui-dialog-buttonpane button:contains("Cancel")');
                backupBtn.prop('disabled', true);
                cancelBtn.prop('disabled', true);
                Promise.resolve()
                    .then(() => (asyncOnBackup ? asyncOnBackup() : true))
                    .then(success => {
                        backupBtn.prop('disabled', false);
                        cancelBtn.prop('disabled', false);
                        if (success === true) {
                            $dlg.dialog("close");
                        }
                    })
                    .catch(err => {
                        console.error('Backup handler threw:', err);
                        backupBtn.prop('disabled', false);
                        cancelBtn.prop('disabled', false);
                    });
            }
        },
        {
            text: "Cancel",
            click: function () {
                $(this).dialog("close");
                if (onCancel != null) {
                    onCancel();
                }
            }
        }
    ];
}

function _styleBackupCancelButtons() {
    $('.ui-dialog-buttonpane button:contains("Backup")').css(DIALOG_BUTTON_CSS);
    $('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
}

function preRenderBackupDbDialog(message, primaryText, secondaryText) { // eslint-disable-line no-unused-vars
    backupDbDialogMessage.title = message;
    backupDbPrimaryDialogLegend.innerText = primaryText;
    backupDbSecondaryDialogLegend.innerText = secondaryText;

    try {
        if ($("#backup-db-dialog-message").hasClass('ui-dialog-content')) {
            $("#backup-db-dialog-message").dialog("destroy");
        }
    } catch (e) {
        console.log("backup-db dialog destroy ignored:", e);
    }

    $("#backup-db-dialog-message").dialog({
        autoOpen: false,
        modal: true,
        width: 600,
        resizable: false,
        draggable: true,
        closeText: "",
        open: function () { document.body.style.overflow = 'hidden'; },
        close: function () { document.body.style.overflow = ''; },
        create: function () {
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Backup")').css(DIALOG_BUTTON_CSS);
            $(this).parent().find('.ui-dialog-buttonpane button:contains("Cancel")').css(DIALOG_BUTTON_CSS);
        },
        buttons: makeBackupCancelButtons(typeof _saveBackupDb === 'function' ? _saveBackupDb : null, null)
    });
}

function renderBackupDbDialog() { // eslint-disable-line no-unused-vars
    _styleBackupCancelButtons();
    $("#backup-db-dialog-message").dialog("open");
    $("#backup-db-dialog-message").dialog("option", "position", { my: "center", at: "center", of: window });
    _styleBackupCancelButtons();
}

// ----------------------------------------------------------------
// Async loaders (omissions, MCPs, tools, agents)
// ----------------------------------------------------------------

async function loadOmission(omissionName) {
    try {
        const response = await fetch(`/agent/load_omissions/${omissionName}/`);

        if (response.status === 404) {
            console.error('404 Error: Omission not found - ' + omissionName);
            return true;
        }
        if (!response.ok) {
            console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
            return true;
        }

        const content = await response.text();
        if (content === 'Omission not found in database') {
            console.error('Omission not found in database: ' + omissionName);
            return true;
        }

        fileTypeOmissions = content;
        omissionContentInput.value = content;
        return false;
    } catch (error) {
        console.error('Error loading omission:', error);
        return true;
    }
}

async function loadMcp(mcpName) {
    try {
        const response = await fetch(`/agent/load_mcp/${mcpName}/`);

        if (response.status === 404) {
            console.error('404 Error: Mcp not found - ' + mcpName);
            return true;
        }
        if (!response.ok) {
            console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
            return true;
        }

        const content = await response.text();
        if (content === 'Mcp not found in database') {
            console.error('Mcp not found in database: ' + mcpName);
            return true;
        }

        const mcpEnabled = (content === 'true') ? true : false;
        if (mcpEnabled === true)
            $('#' + mcpName).prop('checked', true);
        else
            $('#' + mcpName).prop('checked', false);
        return false;
    } catch (error) {
        console.error('Error loading omission:', error);
        return true;
    }
}

async function loadTool(toolName) {
    try {
        const response = await fetch(`/agent/load_tool/${toolName}/`);

        if (response.status === 404) {
            console.error('404 Error: Tool not found - ' + toolName);
            return true;
        }
        if (!response.ok) {
            console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
            return true;
        }

        const content = await response.text();
        if (content === 'Tool not found in database') {
            console.error('Tool not found in database: ' + toolName);
            return true;
        }

        const toolEnabled = (content === 'true') ? true : false;
        if (toolEnabled === true)
            $('#' + toolName).prop('checked', true);
        else
            $('#' + toolName).prop('checked', false);
        return false;
    } catch (error) {
        console.error('Error loading tool:', error);
        return true;
    }
}

async function loadAgent(agentName) {
    try {
        const response = await fetch(`/agent/load_agent/${agentName}/`);

        if (response.status === 404) {
            console.error('404 Error: Agent not found - ' + agentName);
            return true;
        }
        if (!response.ok) {
            console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
            return true;
        }

        const content = await response.text();
        if (content === 'Agent not found in database') {
            console.error('Agent not found in database: ' + agentName);
            return true;
        }

        const agentEnabled = (content === 'true') ? true : false;
        if (agentEnabled === true)
            $('#' + agentName).prop('checked', true);
        else
            $('#' + agentName).prop('checked', false);
        return false;
    } catch (error) {
        console.error('Error loading agent:', error);
        return true;
    }
}

async function loadMcps() {
    try {
        for (let i = 1; i < MAX_MCPS; i++) {
            const mcpNameIterator = "mcp-" + i.toString();
            const errorDetected = await loadMcp(mcpNameIterator);
            if (errorDetected === true) {
                break;
            }
        }
    } catch (error) {
        console.error('Error in loadMcps:', error);
    }
}

async function loadTools() {
    try {
        for (const tool of tools) {
            if (!tool || !tool.name) {
                continue;
            }
            await loadTool(tool.name);
        }
    } catch (error) {
        console.error('Error in loadTools:', error);
    }
}

async function loadAgents() {
    try {
        for (const agent of agents) {
            if (!agent || !agent.name) {
                continue;
            }
            await loadAgent(agent.name);
        }
    } catch (error) {
        console.error('Error in loadAgents:', error);
    }
}

// ============================================================
// About dialog
// ============================================================

function OpenAboutDialog(event) {
    event.preventDefault();
    const overlay = document.getElementById('about-overlay');
    const video = document.getElementById('about-video');
    overlay.style.display = 'flex';
    video.currentTime = 0;
    video.play();
}

function CloseAboutDialog(event) {
    event.preventDefault();
    const overlay = document.getElementById('about-overlay');
    const video = document.getElementById('about-video');
    overlay.style.display = 'none';
    video.pause();
}
