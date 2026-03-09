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
            
            // Layout Calculation
            const itemCount = tools.length;
            let cols = 1;
            let dialogWidth = 450;
            
            if (itemCount > 10) {
                // Golden ratio approximation for columns ~ sqrt(N / 1.618) or sqrt(N * 1.618)
                // We want wider than tall, so cols > rows. 
                // cols * rows >= N -> cols * (cols / 1.618) = N -> cols^2 = N * 1.618
                cols = Math.ceil(Math.sqrt(itemCount * 1.618));
                // Ensure cols is at least 2 if > 10
                cols = Math.max(2, cols);
                // Calculate appropriate width (e.g., ~220px per column minimum)
                dialogWidth = Math.max(450, cols * 220);
                
                // Set the dialog width dynamically
                $(this).dialog("option", "width", dialogWidth);
            } else {
                $(this).dialog("option", "width", 450);
            }
            
            // Apply Grid Layout to the list container
            toolMcpsList.style.display = 'grid';
            toolMcpsList.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
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
                const checkbox = document.createElement('input');
                const label = document.createElement('label');
                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';
                wrapper.style.marginBottom = '4px';

                checkbox.type = 'checkbox';
                checkbox.id = tool.name;
                checkbox.style.marginRight = '8px';
                checkbox.style.accentColor = '#55BBAA';
                
                label.htmlFor = tool.name;
                label.innerText = tool.description;
                label.setAttribute('id', 'label-' + tool.name);
                label.style.color = '#fff';
                label.style.cursor = 'pointer';
                label.style.margin = '0';
                label.style.fontSize = '0.95em';
                
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
            
            // Layout Calculation
            const itemCount = agents.length;
            let cols = 1;
            let dialogWidth = 450;
            
            if (itemCount > 10) {
                // Golden ratio approximation for columns ~ sqrt(N * 1.618)
                cols = Math.ceil(Math.sqrt(itemCount * 1.618));
                cols = Math.max(2, cols);
                dialogWidth = Math.max(450, cols * 220); // Give enough room per column
                
                $(this).dialog("option", "width", dialogWidth);
            } else {
                $(this).dialog("option", "width", 450);
            }
            
            // Apply Grid Layout
            agentsList.style.display = 'grid';
            agentsList.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
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
                const checkbox = document.createElement('input');
                const label = document.createElement('label');
                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';
                wrapper.style.marginBottom = '4px';

                checkbox.type = 'checkbox';
                checkbox.id = agent.name;
                checkbox.style.marginRight = '8px';
                checkbox.style.accentColor = '#55BBAA';
                
                label.htmlFor = agent.name;
                // Use description if available, fallback to upper-cased name
                label.innerText = agent.description || (agent.name.charAt(0).toUpperCase() + agent.name.slice(1));
                label.setAttribute('id', 'label-' + agent.name);
                label.style.color = '#fff';
                label.style.cursor = 'pointer';
                label.style.margin = '0';
                label.style.fontSize = '0.95em';
                
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
        for (let i = 1; i < MAX_TOOLS; i++) {
            const toolNameIterator = "tool-" + i.toString();
            const errorDetected = await loadTool(toolNameIterator);
            if (errorDetected === true) {
                break;
            }
        }
    } catch (error) {
        console.error('Error in loadTools:', error);
    }
}

async function loadAgents() {
    try {
        for (let i = 1; i < MAX_AGENTS; i++) {
            const agentNameIterator = "agent-" + i.toString();
            const errorDetected = await loadAgent(agentNameIterator);
            if (errorDetected === true) {
                break;
            }
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
