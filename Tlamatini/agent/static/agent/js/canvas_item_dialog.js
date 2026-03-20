/* eslint-disable no-unused-vars */
const canvasItemDialogMessage = document.getElementById('canvas-item-dialog-message');
const canvasItemPrimaryDialogLegend = document.getElementById('canvas-item-primary-dialog-legend');
const canvasItemList = document.getElementById('canvas-item-list');


function preRenderCanvasItemDialog(itemInfo, callbackOnSave = null, callbackOnCancel = null) {
    // Reset & Style Container
    canvasItemList.innerHTML = '';
    canvasItemList.style.textAlign = "left"; // Override dialog center alignment
    // canvasItemList.style.maxHeight = "450px"; // REMOVED: Let dialog handle scroll
    // canvasItemList.style.overflowY = "auto"; // REMOVED: Managed by ui-dialog-content
    canvasItemList.style.paddingRight = "5px"; // Scrollbar spacing


    canvasItemDialogMessage.title = "Properties: " + (itemInfo.id || "Unknown");
    canvasItemPrimaryDialogLegend.innerText = "Config: " + (itemInfo.id || "Unknown");
    const dataObj = itemInfo.data || {};

    // Helper to recursively render form elements
    function renderFields(container, data, prefix = '') {
        Object.keys(data).forEach(key => {
            const val = data[key];
            const fieldKey = prefix ? `${prefix}.${key}` : key;

            const listElement = document.createElement('div');
            listElement.style.marginBottom = "12px";
            listElement.style.display = "flex";
            listElement.style.flexDirection = "column";

            // Check if it's an array (including empty arrays)
            if (Array.isArray(val)) {
                // Render arrays as comma-separated text input
                const label = document.createElement('label');
                label.innerText = key + " (comma-separated): ";
                label.style.fontWeight = "bold";
                label.style.fontSize = "0.9em";
                label.style.marginBottom = "4px";
                label.style.color = "#ddd";

                const input = document.createElement('input');
                input.type = 'text';
                input.id = 'prop-' + fieldKey;
                input.value = val.join(', '); // Join array to comma-separated string
                input.classList.add('form-control');
                input.dataset.key = fieldKey;
                input.dataset.isArray = 'true'; // Mark as array for reconstruction
                input.style.width = "100%";
                input.style.backgroundColor = "#fff";
                input.style.color = "#000";
                input.placeholder = "Enter values separated by commas";

                listElement.appendChild(label);
                listElement.appendChild(input);
                container.appendChild(listElement);

            } else if (typeof val === 'object' && val !== null) {
                // Fieldset for nested objects (but not arrays)
                const fieldset = document.createElement('fieldset');
                fieldset.style.border = "1px solid #555"; // Visible border on dark theme
                fieldset.style.padding = "10px";
                fieldset.style.borderRadius = "5px";
                fieldset.style.marginBottom = "15px";
                fieldset.style.backgroundColor = "rgba(0,0,0,0.1)"; // Slight dark bg

                const legend = document.createElement('legend');
                legend.innerText = key.toUpperCase();
                legend.style.color = "#fff";
                legend.style.fontWeight = "bold";
                legend.style.fontSize = "0.85em";
                legend.style.padding = "0 5px";
                legend.style.width = "auto"; // Fix for some browsers stretching legend
                legend.style.float = "none"; // Fix for bootstrap reset

                fieldset.appendChild(legend);
                renderFields(fieldset, val, fieldKey);
                container.appendChild(fieldset);
            } else if (key === 'trigger_mode' || key === 'operation' || key === 'direction' || key === 'crawl_type' || key === 'movement_type' || key === 'reading_type') {
                // Custom rendering for trigger_mode, operation, direction, crawl_type, movement_type, reading_type - Radio Buttons
                const label = document.createElement('label');
                label.innerText = key + ": ";
                label.style.fontWeight = "bold";
                label.style.fontSize = "0.9em";
                label.style.marginBottom = "8px";
                label.style.color = "#ddd";
                label.style.display = "block";

                const radioContainer = document.createElement('div');
                radioContainer.style.display = "flex";
                radioContainer.style.gap = "20px";
                radioContainer.style.marginBottom = "10px";

                let options = [];
                if (key === 'trigger_mode') {
                    options = ['immediate', 'event'];
                } else if (key === 'operation') {
                    options = ['copy', 'move'];
                } else if (key === 'direction') {
                    options = ['send', 'receive'];
                } else if (key === 'crawl_type') {
                    options = ['small-range', 'medium-range', 'large-range'];
                } else if (key === 'movement_type') {
                    options = ['random', 'localized'];
                } else if (key === 'reading_type') {
                    options = ['fast', 'complete', 'summarized'];
                }

                options.forEach(opt => {
                    const wrapper = document.createElement('div');
                    wrapper.style.display = "flex";
                    wrapper.style.alignItems = "center";
                    wrapper.style.cursor = "pointer";

                    const radioRes = document.createElement('input');
                    radioRes.type = 'radio';
                    radioRes.name = 'prop-' + fieldKey; // Group by field key
                    radioRes.value = opt;
                    radioRes.id = 'prop-' + fieldKey + '-' + opt;
                    if (val === opt) radioRes.checked = true;
                    radioRes.dataset.key = fieldKey; // Used for saving
                    radioRes.dataset.isRadio = 'true'; // Marker for saving logic

                    // Custom Radio Style
                    radioRes.style.marginRight = "8px";
                    radioRes.style.cursor = "pointer";
                    radioRes.style.width = "18px";
                    radioRes.style.height = "18px";
                    radioRes.style.accentColor = "#55BBAA";

                    const optLabel = document.createElement('label');
                    optLabel.innerText = opt.charAt(0).toUpperCase() + opt.slice(1);
                    optLabel.htmlFor = radioRes.id;
                    optLabel.style.cursor = "pointer";
                    optLabel.style.color = "#fff";
                    optLabel.style.fontSize = "0.95em";

                    wrapper.appendChild(radioRes);
                    wrapper.appendChild(optLabel);
                    radioContainer.appendChild(wrapper);
                });

                listElement.appendChild(label);
                listElement.appendChild(radioContainer);
                container.appendChild(listElement);

            } else if (typeof val === 'boolean') {
                // Boolean handling - Render as Checkbox
                const wrapper = document.createElement('div');
                wrapper.style.display = "flex";
                wrapper.style.alignItems = "center";
                wrapper.style.marginBottom = "5px";

                const input = document.createElement('input');
                input.type = 'checkbox';
                input.checked = val;
                input.id = 'prop-' + fieldKey;
                input.dataset.key = fieldKey;
                input.style.marginRight = "10px";
                input.style.width = "18px";
                input.style.height = "18px";
                input.style.accentColor = "#55BBAA";
                input.style.cursor = "pointer";

                const label = document.createElement('label');
                label.innerText = key; // Use key as label
                label.htmlFor = 'prop-' + fieldKey;
                label.style.cursor = "pointer";
                label.style.color = "#fff";

                wrapper.appendChild(input);
                wrapper.appendChild(label);
                container.appendChild(wrapper);

            } else {
                // Scalar value (string, number, boolean)
                const label = document.createElement('label');
                label.innerText = key + ": ";
                label.style.fontWeight = "bold";
                label.style.fontSize = "0.9em";
                label.style.marginBottom = "4px";
                label.style.color = "#ddd";

                let input;
                if (typeof val === 'string' && (val.includes('\n') || val.length > 50 || key === 'script' || key === 'prompt' || key === 'system_prompt' || key === 'user_instructions')) {
                    input = document.createElement('textarea');
                    input.rows = 4;
                } else {
                    input = document.createElement('input');
                    input.type = typeof val === 'number' ? 'number' : 'text';
                    if (typeof val === 'number') input.step = "any";
                }

                input.id = 'prop-' + fieldKey; // Not strictly needed for logic but good for debugging
                input.value = val;
                input.classList.add('form-control'); // Bootstrap class
                input.dataset.key = fieldKey;
                input.style.width = "100%";
                input.style.backgroundColor = "#fff";
                input.style.color = "#000"; // Ensure readable text

                listElement.appendChild(label);
                listElement.appendChild(input);
                container.appendChild(listElement);
            }
        });
    }

    // Customize based on Agent Type
    const agentName = (itemInfo.id || "").toLowerCase();

    // Check if it is a Cleaner Agent
    if (agentName.startsWith('cleaner')) {
        canvasItemList.innerHTML = ''; // Clear default recursive render

        const description = document.createElement('p');
        description.innerText = "Select agents to be cleaned (logs & pids deleted) before restart.";
        description.style.color = "#ddd";
        description.style.marginBottom = "10px";
        canvasItemList.appendChild(description);

        const formGroup = document.createElement('div');
        formGroup.style.display = 'flex';
        formGroup.style.flexDirection = 'column';
        formGroup.style.gap = '5px';
        formGroup.style.maxHeight = '300px';
        formGroup.style.overflowY = 'auto';
        formGroup.style.border = '1px solid #444';
        formGroup.style.padding = '10px';
        formGroup.style.borderRadius = '5px';

        // Get currently selected agents from config
        const currentSelected = dataObj['agents_to_clean'] || [];

        // We need the list of all agents on canvas to populate this.
        // We can access the global 'canvasItems' map from agentic_control_panel.js if available, 
        // OR iterate over DOM elements with .canvas-item class.
        // Since this script is loaded in the same context, we can try querySelectorAll.
        const allAgentItems = document.querySelectorAll('.canvas-item');

        if (allAgentItems.length === 0) {
            const noAgentsMsg = document.createElement('div');
            noAgentsMsg.innerText = "No other agents found on canvas.";
            noAgentsMsg.style.color = "#888";
            formGroup.appendChild(noAgentsMsg);
        } else {
            allAgentItems.forEach(item => {
                const itemId = item.id;
                // Don't show the cleaner itself
                if (itemId === itemInfo.id) return;

                const itemLabel = item.innerText; // e.g. "Monitor-Log (1)"

                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.id = `clean-select-${itemId}`;
                checkbox.value = itemId; // Store agent ID (e.g. monitor-log-1)
                checkbox.checked = currentSelected.includes(itemId);
                checkbox.classList.add('cleaner-agent-checkbox'); // Class for saving logic
                checkbox.style.marginRight = '8px';
                checkbox.style.accentColor = '#55BBAA';

                const label = document.createElement('label');
                label.htmlFor = `clean-select-${itemId}`;
                label.innerText = itemLabel;
                label.style.color = '#fff';
                label.style.cursor = 'pointer';

                wrapper.appendChild(checkbox);
                wrapper.appendChild(label);
                formGroup.appendChild(wrapper);
            });
        }

        canvasItemList.appendChild(formGroup);

        // Also show other props if any (Output agents are auto-managed, but maybe show them read-only?)
        // Let's stick to agents_to_clean for now.

    } else if (agentName.startsWith('scper')) {
        // Show SCP/SSH key warning legend before standard fields
        const scpLegend = document.createElement('p');
        scpLegend.innerHTML = '<strong>&#9888; Important:</strong> You must preconfigure SSH keys for passwordless authentication to the remote endpoint before using this agent.<br><em>For <b>send</b>: specify a Windows-like path (e.g. C:\\Users\\file.txt). For <b>receive</b>: specify a Linux-like path (e.g. /home/user/file.txt).</em>';
        scpLegend.style.color = '#f0ad4e';
        scpLegend.style.marginBottom = '12px';
        scpLegend.style.padding = '8px';
        scpLegend.style.border = '1px solid #f0ad4e';
        scpLegend.style.borderRadius = '5px';
        scpLegend.style.backgroundColor = 'rgba(240, 173, 78, 0.1)';
        canvasItemList.appendChild(scpLegend);
        renderFields(canvasItemList, dataObj);

    } else if (agentName.startsWith('telegramrx')) {
        // Show Telegram preconfiguration warning legend before standard fields
        const tgLegend = document.createElement('p');
        tgLegend.innerHTML = '<strong>&#9888; Important:</strong> You must preconfigure your application and the Telegramrx template, following the instructions on <a href="https://my.telegram.org/" target="_blank" style="color: #f0ad4e;">https://my.telegram.org/</a> before using this agent.';
        tgLegend.style.color = '#f0ad4e';
        tgLegend.style.marginBottom = '12px';
        tgLegend.style.padding = '8px';
        tgLegend.style.border = '1px solid #f0ad4e';
        tgLegend.style.borderRadius = '5px';
        tgLegend.style.backgroundColor = 'rgba(240, 173, 78, 0.1)';
        canvasItemList.appendChild(tgLegend);

        // Show session authentication notice
        const tgSessionLegend = document.createElement('p');
        tgSessionLegend.innerHTML = '<strong>&#9888; Important:</strong> Before deploying this agent, you must run <code style="color: #f0ad4e;">python telegramrx.py</code> once from the template directory <code style="color: #f0ad4e;">agent/agents/telegramrx/</code> to complete the Telegram phone+code authentication. This creates the <code style="color: #f0ad4e;">telegramrx_session.session</code> file that will be copied to the pool automatically.';
        tgSessionLegend.style.color = '#f0ad4e';
        tgSessionLegend.style.marginBottom = '12px';
        tgSessionLegend.style.padding = '8px';
        tgSessionLegend.style.border = '1px solid #f0ad4e';
        tgSessionLegend.style.borderRadius = '5px';
        tgSessionLegend.style.backgroundColor = 'rgba(240, 173, 78, 0.1)';
        canvasItemList.appendChild(tgSessionLegend);
        renderFields(canvasItemList, dataObj);

    } else if (agentName.startsWith('ssher')) {
        // Show SSH key warning legend before standard fields
        const sshLegend = document.createElement('p');
        sshLegend.innerHTML = '<strong>&#9888; Important:</strong> You must preconfigure SSH keys for passwordless authentication to the remote endpoint before using this agent.';
        sshLegend.style.color = '#f0ad4e';
        sshLegend.style.marginBottom = '12px';
        sshLegend.style.padding = '8px';
        sshLegend.style.border = '1px solid #f0ad4e';
        sshLegend.style.borderRadius = '5px';
        sshLegend.style.backgroundColor = 'rgba(240, 173, 78, 0.1)';
        canvasItemList.appendChild(sshLegend);
        renderFields(canvasItemList, dataObj);

    } else if (agentName.startsWith('flowcreator')) {
        // FlowCreator custom dialog
        canvasItemList.innerHTML = '';

        const legend = document.createElement('p');
        legend.innerHTML = '<strong>&#9889; FlowCreator</strong> — Design an agent flow using AI. Enter a prompt describing your flow objective, configure the LLM, and click <strong>Go!</strong> to generate the flow automatically.';
        legend.style.color = '#4FC3F7';
        legend.style.marginBottom = '12px';
        legend.style.padding = '8px';
        legend.style.border = '1px solid #4FC3F7';
        legend.style.borderRadius = '5px';
        legend.style.backgroundColor = 'rgba(79, 195, 247, 0.1)';
        canvasItemList.appendChild(legend);

        const warningNote = document.createElement('p');
        warningNote.innerHTML = '<strong>&#9888; Note:</strong> Each time you save, the canvas will be <strong>completely cleaned</strong> (except this FlowCreator instance) and the flow will be regenerated from scratch.';
        warningNote.style.color = '#f0ad4e';
        warningNote.style.marginBottom = '12px';
        warningNote.style.padding = '8px';
        warningNote.style.border = '1px solid #f0ad4e';
        warningNote.style.borderRadius = '5px';
        warningNote.style.backgroundColor = 'rgba(240, 173, 78, 0.1)';
        canvasItemList.appendChild(warningNote);

        renderFields(canvasItemList, dataObj);

    } else if (agentName.startsWith('mouser')) {
        // Mouser custom dialog with conditional field visibility
        canvasItemList.innerHTML = '';

        const mouserLegend = document.createElement('p');
        mouserLegend.innerHTML = '<strong>&#128433; Mouser</strong> — Move the mouse pointer randomly or to a specific screen position. <b>Random</b>: moves randomly for a duration. <b>Localized</b>: moves from one position to another.';
        mouserLegend.style.color = '#7C4DFF';
        mouserLegend.style.marginBottom = '12px';
        mouserLegend.style.padding = '8px';
        mouserLegend.style.border = '1px solid #7C4DFF';
        mouserLegend.style.borderRadius = '5px';
        mouserLegend.style.backgroundColor = 'rgba(124, 77, 255, 0.1)';
        canvasItemList.appendChild(mouserLegend);

        renderFields(canvasItemList, dataObj);

        // Wire up conditional enable/disable logic after fields are rendered
        setTimeout(() => {
            const radioRandom = document.getElementById('prop-movement_type-random');
            const radioLocalized = document.getElementById('prop-movement_type-localized');
            const checkActualPos = document.getElementById('prop-actual_position');
            const inputIniX = document.getElementById('prop-ini_posx');
            const inputIniY = document.getElementById('prop-ini_posy');
            const inputEndX = document.getElementById('prop-end_posx');
            const inputEndY = document.getElementById('prop-end_posy');
            const inputTotalTime = document.getElementById('prop-total_time');

            function applyMouserState() {
                const isLocalized = radioLocalized && radioLocalized.checked;
                const isActualPos = checkActualPos && checkActualPos.checked;

                // total_time: disabled when localized is selected
                if (inputTotalTime) {
                    inputTotalTime.disabled = isLocalized;
                    inputTotalTime.style.opacity = isLocalized ? '0.4' : '1';
                }

                // Initial/Final position fields: enabled only when localized
                if (inputEndX) { inputEndX.disabled = !isLocalized; inputEndX.style.opacity = isLocalized ? '1' : '0.4'; }
                if (inputEndY) { inputEndY.disabled = !isLocalized; inputEndY.style.opacity = isLocalized ? '1' : '0.4'; }
                if (checkActualPos) { checkActualPos.disabled = !isLocalized; checkActualPos.style.opacity = isLocalized ? '1' : '0.4'; }

                // ini_posx/ini_posy: disabled when NOT localized OR when actual_position is checked
                const disableIni = !isLocalized || isActualPos;
                if (inputIniX) { inputIniX.disabled = disableIni; inputIniX.style.opacity = disableIni ? '0.4' : '1'; }
                if (inputIniY) { inputIniY.disabled = disableIni; inputIniY.style.opacity = disableIni ? '0.4' : '1'; }
            }

            if (radioRandom) radioRandom.addEventListener('change', applyMouserState);
            if (radioLocalized) radioLocalized.addEventListener('change', applyMouserState);
            if (checkActualPos) checkActualPos.addEventListener('change', applyMouserState);

            // Apply initial state
            applyMouserState();
        }, 50);

    } else if (agentName.startsWith('crawler')) {
        // Crawler custom dialog with conditional depth field visibility
        canvasItemList.innerHTML = '';

        const crawlerLegend = document.createElement('p');
        crawlerLegend.innerHTML = '<strong>&#127760; Crawler</strong> — Crawl web pages and process their content with an LLM. <b>Small-range</b>: same-domain links only. <b>Medium-range</b>: all links (cross-domain). <b>Large-range</b>: all links recursively up to a configurable depth.';
        crawlerLegend.style.color = '#00BCD4';
        crawlerLegend.style.marginBottom = '12px';
        crawlerLegend.style.padding = '8px';
        crawlerLegend.style.border = '1px solid #00BCD4';
        crawlerLegend.style.borderRadius = '5px';
        crawlerLegend.style.backgroundColor = 'rgba(0, 188, 212, 0.1)';
        canvasItemList.appendChild(crawlerLegend);

        renderFields(canvasItemList, dataObj);

        // Wire up conditional depth field visibility based on crawl_type
        setTimeout(() => {
            const radioSmall = document.getElementById('prop-crawl_type-small-range');
            const radioMedium = document.getElementById('prop-crawl_type-medium-range');
            const radioLarge = document.getElementById('prop-crawl_type-large-range');
            const inputDepth = document.getElementById('prop-depth');

            function applyCrawlerState() {
                const isLargeRange = radioLarge && radioLarge.checked;

                // depth field: only enabled and visible when large-range is selected
                if (inputDepth) {
                    inputDepth.disabled = !isLargeRange;
                    inputDepth.style.opacity = isLargeRange ? '1' : '0.4';
                    // Also hide/show the parent container (label + input)
                    const depthContainer = inputDepth.closest('div');
                    if (depthContainer) {
                        depthContainer.style.display = isLargeRange ? 'flex' : 'none';
                    }
                }
            }

            if (radioSmall) radioSmall.addEventListener('change', applyCrawlerState);
            if (radioMedium) radioMedium.addEventListener('change', applyCrawlerState);
            if (radioLarge) radioLarge.addEventListener('change', applyCrawlerState);

            // Apply initial state
            applyCrawlerState();
        }, 50);

    } else if (agentName.startsWith('flowhypervisor')) {
        // FlowHypervisor custom dialog
        canvasItemList.innerHTML = '';

        const hvLegend = document.createElement('p');
        hvLegend.innerHTML = '<strong>&#128737; FlowHypervisor</strong> — LLM-powered flow monitoring. Configure the LLM and monitoring interval, then click <strong>Start Monitoring</strong> to begin.';
        hvLegend.style.color = '#AB47BC';
        hvLegend.style.marginBottom = '12px';
        hvLegend.style.padding = '8px';
        hvLegend.style.border = '1px solid #AB47BC';
        hvLegend.style.borderRadius = '5px';
        hvLegend.style.backgroundColor = 'rgba(171, 71, 188, 0.1)';
        canvasItemList.appendChild(hvLegend);

        const hvWarning = document.createElement('p');
        hvWarning.innerHTML = '<strong>&#9888; Note:</strong> This agent monitors all other agents in the flow and alerts when anomalies are detected.';
        hvWarning.style.color = '#f0ad4e';
        hvWarning.style.marginBottom = '12px';
        hvWarning.style.padding = '8px';
        hvWarning.style.border = '1px solid #f0ad4e';
        hvWarning.style.borderRadius = '5px';
        hvWarning.style.backgroundColor = 'rgba(240, 173, 78, 0.1)';
        canvasItemList.appendChild(hvWarning);

        renderFields(canvasItemList, dataObj);

        // Style the user_instructions textarea with placeholder and extra rows
        const instrTextarea = canvasItemList.querySelector('[data-key="user_instructions"]');
        if (instrTextarea) {
            instrTextarea.placeholder = 'e.g. "Ignore warnings from sleeper agents", "Alert immediately if executer runs longer than 2 minutes", "The crawler agent is expected to take 5+ minutes — do not flag it as stuck"';
            instrTextarea.rows = 5;
        }

    } else {
        // Standard Behavior
        renderFields(canvasItemList, dataObj);

        if (canvasItemList.children.length === 0) {
            const msg = document.createElement('p');
            msg.innerText = "No editable configuration found.";
            msg.style.textAlign = "center";
            canvasItemList.appendChild(msg);
        }
    }

    // Track if this is a FlowCreator or FlowHypervisor dialog for custom save behavior
    const isFlowCreatorDialog = agentName.startsWith('flowcreator');
    const isFlowHypervisorDialog = agentName.startsWith('flowhypervisor');

    $("#canvas-item-dialog-message").dialog({
        title: "Properties: " + (itemInfo.id || "Unknown"),
        autoOpen: false,
        modal: true,
        width: 800,
        maxHeight: 800,
        resizable: true,
        draggable: true,
        closeText: "",

        create: function () {
            // Ensure dialog content area is flex/column if needed, or just let custom div handle scroll
            // Fix button styles
            const buttonPane = $(this).parent().find('.ui-dialog-buttonpane');
            buttonPane.css({
                "background": "none",
                "border": "none",
                "padding": "10px 20px"
            });

            buttonPane.find('button:contains("Save"), button:contains("Go!"), button:contains("Start Monitoring")')
                .css({
                    'background-color': '#55BBAA',
                    'color': 'white',
                    'border': 'none',
                    'border-radius': '6px',
                    'font-size': '1em',
                    'padding': '8px 20px',
                    'cursor': 'pointer'
                });
            buttonPane.find('button:contains("Cancel")')
                .css({
                    'background-color': '#777', // Different color for cancel
                    'color': 'white',
                    'border': 'none',
                    'border-radius': '6px',
                    'font-size': '1em',
                    'padding': '8px 20px',
                    'cursor': 'pointer'
                });
        },
        open: function () {
            // Bind Enter key to trigger Save button (except in textareas)
            const dialogEl = $(this);
            dialogEl.off('keydown.enterSave').on('keydown.enterSave', function (e) {
                if (e.key === 'Enter' && !$(e.target).is('textarea')) {
                    e.preventDefault();
                    // Find and click the Save/Go! button
                    dialogEl.parent().find('.ui-dialog-buttonpane button:contains("Save"), .ui-dialog-buttonpane button:contains("Go!"), .ui-dialog-buttonpane button:contains("Start Monitoring")').click();
                }
            });
        },
        buttons: [
            {
                text: isFlowCreatorDialog ? "Go!" : isFlowHypervisorDialog ? "Start Monitoring" : "Save",
                click: async function () {
                    console.log("Saving item properties...");
                    const inputs = canvasItemList.querySelectorAll('input, textarea');
                    const updates = {};

                    // Special handling for Cleaner agent checkboxes
                    const cleanerCheckboxes = canvasItemList.querySelectorAll('.cleaner-agent-checkbox');
                    if (cleanerCheckboxes.length > 0) {
                        const selectedAgents = [];
                        cleanerCheckboxes.forEach(cb => {
                            if (cb.checked) {
                                selectedAgents.push(cb.value);
                            }
                        });
                        updates['agents_to_clean'] = selectedAgents;
                    }

                    // Reconstruct nested object from flat keys
                    inputs.forEach(inp => {
                        // Skip inputs without a key (like our custom cleaner checkboxes)
                        if (!inp.dataset.key) return;

                        const keys = inp.dataset.key.split('.');
                        let current = updates;
                        for (let i = 0; i < keys.length; i++) {
                            const k = keys[i];
                            if (i === keys.length - 1) {
                                // Check if this is an array field
                                if (inp.dataset.isArray === 'true') {
                                    // Parse comma-separated string back to array
                                    const val = inp.value.trim();
                                    if (val === '') {
                                        current[k] = [];
                                    } else {
                                        current[k] = val.split(',').map(s => s.trim()).filter(s => s !== '');
                                    }
                                } else if (inp.type === 'number' && inp.value !== '') {
                                    // Preserve number types
                                    current[k] = parseFloat(inp.value);
                                } else if (inp.type === 'checkbox' && !inp.dataset.isRadio) {
                                    // Handle boolean checkboxes
                                    current[k] = inp.checked;
                                } else if (inp.type === 'radio') {
                                    // For radio buttons, only set value if checked
                                    if (inp.checked) {
                                        current[k] = inp.value;
                                    }
                                    // If not checked, do nothing (don't overwrite with unchecked value)
                                } else {
                                    current[k] = inp.value;
                                }
                            } else {
                                current[k] = current[k] || {};
                                current = current[k];
                            }
                        }
                    });

                    // Get agent ID from dialog title
                    const agentId = itemInfo.id;

                    try {
                        const response = await fetch(`/agent/save_agent_config/${agentId}/`, {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json',
                                ...getHeaders()
                            },
                            body: JSON.stringify(updates)
                        });

                        if (response.ok) {
                            const result = await response.json();
                            console.log("Configuration saved to:", result.path);
                            $(canvasItemDialogMessage).dialog("close");

                            if (isFlowCreatorDialog) {
                                // FlowCreator: clean canvas, clean pool, start agent, poll for result
                                await _executeFlowCreator(agentId);
                            } else if (isFlowHypervisorDialog) {
                                // FlowHypervisor: start monitoring agent
                                await _executeFlowHypervisor(agentId);
                            } else {
                                showDeploymentResultDialog(true, agentId, result.path);
                            }
                            if (callbackOnSave != null) {
                                callbackOnSave(result.config || updates);
                            }
                        } else {
                            const errorText = await response.text();
                            console.error("Save failed:", errorText);
                            $(canvasItemDialogMessage).dialog("close");
                            showDeploymentResultDialog(false, agentId, "Failed to save configuration: " + errorText);
                        }
                    } catch (err) {
                        console.error("Error saving configuration:", err);
                        $(canvasItemDialogMessage).dialog("close");
                        showDeploymentResultDialog(false, agentId, "Error saving configuration: " + err.message);
                    }
                }
            },
            {
                text: "Cancel",
                click: function () {
                    console.log("Cancel item properties...");
                    $(this).dialog("close");
                    if (callbackOnCancel != null) {
                        callbackOnCancel();
                    }
                }
            }
        ]
    });
}

function renderCanvasItemDialog() {
    $('.ui-dialog-buttonpane button:contains("Save"), .ui-dialog-buttonpane button:contains("Go!"), .ui-dialog-buttonpane button:contains("Start Monitoring")')
        .css({
            'background-color': '#55BBAA',
            'color': 'white',
            'border-radius': '8px',
            'font-size': '1em',
            'height': '4vh'
        });
    $('.ui-dialog-buttonpane button:contains("Cancel")')
        .css({
            'background-color': '#55BBAA',
            'color': 'white',
            'border-radius': '8px',
            'font-size': '1em',
            'height': '4vh'
        });
    $("#canvas-item-dialog-message").dialog("open");
}

/**
 * Show deployment result dialog (success or error)
 * @param {boolean} success - Whether the deployment was successful
 * @param {string} agentName - Name of the agent (e.g., 'monitor-log-1')
 * @param {string} pathOrError - Path to created directory (success) or error message (failure)
 */
function showDeploymentResultDialog(success, agentName, pathOrError) {
    const dialog = $("#deployment-result-dialog");
    const iconEl = document.getElementById('deployment-result-icon');
    const titleEl = document.getElementById('deployment-result-title');
    const messageEl = document.getElementById('deployment-result-message');
    const pathEl = document.getElementById('deployment-result-path');

    if (success) {
        iconEl.innerHTML = '✅';
        iconEl.style.color = '#55BBAA';
        titleEl.innerText = 'Deployment Successful';
        titleEl.style.color = '#55BBAA';
        messageEl.innerText = `Agent "${agentName}" has been deployed successfully.`;
        pathEl.innerText = `Directory: ${pathOrError}`;
        pathEl.style.display = 'block';
    } else {
        iconEl.innerHTML = '❌';
        iconEl.style.color = '#e74c3c';
        titleEl.innerText = 'Deployment Failed';
        titleEl.style.color = '#e74c3c';
        messageEl.innerText = pathOrError;
        pathEl.style.display = 'none';
    }

    dialog.dialog({
        title: success ? "Deployment Complete" : "Deployment Error",
        autoOpen: true,
        modal: true,
        width: 500,
        resizable: false,
        draggable: true,
        closeText: "",
        create: function () {
            const buttonPane = $(this).parent().find('.ui-dialog-buttonpane');
            buttonPane.css({
                "background": "none",
                "border": "none",
                "padding": "10px 20px",
                "text-align": "center"
            });
            buttonPane.find('button:contains("OK")')
                .css({
                    'background-color': success ? '#55BBAA' : '#e74c3c',
                    'color': 'white',
                    'border': 'none',
                    'border-radius': '6px',
                    'font-size': '1em',
                    'padding': '8px 30px',
                    'cursor': 'pointer',
                    'min-width': '100px'
                });
        },
        open: function () {
            // Re-style button on open (in case dialog was reused)
            const buttonPane = $(this).parent().find('.ui-dialog-buttonpane');
            buttonPane.find('button:contains("OK")')
                .css({
                    'background-color': success ? '#55BBAA' : '#e74c3c'
                });
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

// ========================================
// FLOWCREATOR EXECUTION & RENDERING
// ========================================

/**
 * Execute the FlowCreator agent: clean canvas/pool, start agent, poll for result, render flow.
 * @param {string} agentId - The FlowCreator agent ID (e.g., 'flowcreator-1')
 */
async function _executeFlowCreator(agentId) {
    // Show progress dialog
    const progressDialog = _showFlowCreatorProgress('Initializing FlowCreator...');

    try {
        // 1. Clean canvas (except FlowCreator item)
        _updateFlowCreatorProgress(progressDialog, 'Cleaning canvas...');
        const flowCreatorItem = document.getElementById(agentId);
        const allItems = document.querySelectorAll('.canvas-item');
        const itemsToRemove = [];

        allItems.forEach(item => {
            if (item.id !== agentId) {
                itemsToRemove.push(item);
            }
        });

        // Remove connections not involving FlowCreator
        const connectionsToRemove = [...ACP.connections];
        connectionsToRemove.forEach(conn => {
            if (conn.path) conn.path.remove();
        });
        ACP.connections.length = 0;
        ACP.selectedItems.clear();

        // Remove items from canvas
        itemsToRemove.forEach(item => item.remove());

        // Reset counters but keep FlowCreator's count
        const fcBaseName = agentId.split('-').slice(0, -1).join('-');
        const fcCount = ACP.itemCounters.get(fcBaseName) || 1;
        ACP.itemCounters.clear();
        ACP.itemCounters.set(fcBaseName, fcCount);

        // Clear node configs except FlowCreator
        const fcConfig = ACP.nodeConfigs.get(agentId);
        ACP.nodeConfigs.clear();
        if (fcConfig) ACP.nodeConfigs.set(agentId, fcConfig);

        // 2. Clean pool directory (except FlowCreator)
        _updateFlowCreatorProgress(progressDialog, 'Cleaning pool directory...');
        try {
            await fetch(`/agent/clean_pool_except/${agentId}/`, {
                method: 'POST',
                headers: getHeaders(),
                credentials: 'same-origin'
            });
        } catch (cleanErr) {
            console.error('Failed to clean pool:', cleanErr);
        }

        // 3. Start the FlowCreator agent
        _updateFlowCreatorProgress(progressDialog, 'Starting FlowCreator agent... Sending prompt to LLM...');
        const execResponse = await fetch(`/agent/execute_flowcreator/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin'
        });

        if (!execResponse.ok) {
            const errData = await execResponse.json();
            throw new Error(errData.message || 'Failed to start FlowCreator agent');
        }

        // 4. Poll for flow_result.json
        _updateFlowCreatorProgress(progressDialog, 'Waiting for LLM response... This may take a minute...');

        // Show hourglass while waiting
        if (typeof isFlowCreatorWaiting !== 'undefined') {
            isFlowCreatorWaiting = true;
            titleBusyPrefix = "⏳ ";
        }

        const flowResult = await _pollFlowCreatorResult(agentId, progressDialog);

        if (!flowResult || flowResult.status === 'error') {
            const errMsg = flowResult ? flowResult.message : 'No result received from FlowCreator agent';
            _closeFlowCreatorProgress(progressDialog);
            showDeploymentResultDialog(false, agentId, 'FlowCreator failed: ' + errMsg);
            return;
        }

        // 5. Render the flow on canvas
        _updateFlowCreatorProgress(progressDialog, `Rendering flow with ${flowResult.nodes.length} agents...`);
        await _renderFlowCreatorResult(flowResult, agentId, flowCreatorItem);

        _closeFlowCreatorProgress(progressDialog);
        showDeploymentResultDialog(true, agentId,
            `Flow created successfully! ${flowResult.nodes.length} agents and ${flowResult.connections.length} connections generated.`);

    } catch (error) {
        console.error('FlowCreator execution error:', error);
        _closeFlowCreatorProgress(progressDialog);
        showDeploymentResultDialog(false, agentId, 'FlowCreator error: ' + error.message);
    } finally {
        if (typeof isFlowCreatorWaiting !== 'undefined') {
            isFlowCreatorWaiting = false;
            // Force title update if polling is not running
            titleBusyPrefix = "";
            if (typeof globalRunningState !== 'undefined' && typeof GLOBAL_STATE !== 'undefined' && globalRunningState === GLOBAL_STATE.RUNNING) {
                if (typeof pollAgentStatus === 'function') {
                    pollAgentStatus();
                }
            }
        }
    }
}

// ========================================
// FLOWHYPERVISOR EXECUTION
// ========================================

/**
 * Execute the FlowHypervisor agent: start monitoring, show success dialog.
 * Unlike FlowCreator, this does NOT clean the canvas or pool.
 * @param {string} agentId - The FlowHypervisor agent ID (e.g., 'flowhypervisor')
 */
async function _executeFlowHypervisor(agentId) {
    try {
        const execResponse = await fetch(`/agent/execute_flowhypervisor/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin'
        });

        if (!execResponse.ok) {
            const errData = await execResponse.json();
            throw new Error(errData.message || 'Failed to start FlowHypervisor agent');
        }

        const result = await execResponse.json();
        showDeploymentResultDialog(true, agentId,
            `FlowHypervisor started successfully (PID: ${result.pid}). Monitoring is now active.`);
    } catch (error) {
        console.error('FlowHypervisor execution error:', error);
        showDeploymentResultDialog(false, agentId, 'FlowHypervisor error: ' + error.message);
    }
}

/**
 * Poll the backend for flow_result.json until the agent finishes.
 * @param {string} agentId
 * @param {Object} progressDialog
 * @returns {Object|null} The flow result or null on timeout
 */
async function _pollFlowCreatorResult(agentId, progressDialog) {
    const maxWait = 600000; // 10 minutes
    const interval = 2000;  // 2 seconds
    let elapsed = 0;

    while (elapsed < maxWait) {
        try {
            const response = await fetch(`/agent/check_flowcreator_result/${agentId}/`, {
                method: 'GET',
                headers: getHeaders(),
                credentials: 'same-origin'
            });

            if (response.status === 200) {
                return await response.json();
            }
            // 202 = still running, keep polling
        } catch (err) {
            console.warn('Poll error:', err);
        }

        await new Promise(resolve => setTimeout(resolve, interval));
        elapsed += interval;

        const secs = Math.floor(elapsed / 1000);
        _updateFlowCreatorProgress(progressDialog, `Waiting for LLM response... (${secs}s elapsed)`);
    }

    return null; // Timeout
}

/**
 * Render the flow result on the canvas.
 * Creates canvas items, deploys templates, and draws connections.
 * @param {Object} flowResult - The flow_result.json data
 * @param {string} flowCreatorId - The FlowCreator's agent ID
 * @param {HTMLElement} flowCreatorItem - The FlowCreator's canvas item element
 */
async function _renderFlowCreatorResult(flowResult, flowCreatorId, flowCreatorItem) {
    const nodes = flowResult.nodes || [];
    const connections = flowResult.connections || [];
    const loadedNodes = [];

    // Create each agent node on the canvas
    for (const nodeData of nodes) {
        const agentText = nodeData.text || 'unknown';
        const newItem = document.createElement('div');
        newItem.classList.add('canvas-item');

        const registration = registerItem(agentText);
        newItem.textContent = `${agentText} (${registration.count})`;
        newItem.id = registration.id;
        newItem.dataset.agentName = agentText;

        const lowerName = agentText.toLowerCase().replace(/\s+/g, '-');
        applyAgentTypeClass(newItem, lowerName);
        appendInputTriangles(newItem, lowerName);
        appendOutputTriangles(newItem, lowerName);
        appendLedIndicator(newItem);

        newItem.style.left = nodeData.left || '50px';
        newItem.style.top = nodeData.top || '50px';

        submonitor.appendChild(newItem);
        makeDraggable(newItem);

        // Deploy agent to pool directory with config
        try {
            if (nodeData.configData && Object.keys(nodeData.configData).length > 0) {
                ACP.nodeConfigs.set(newItem.id, nodeData.configData);
                const saveResp = await fetch(`/agent/save_agent_config/${newItem.id}/`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', ...getHeaders() },
                    credentials: 'same-origin',
                    body: JSON.stringify(nodeData.configData)
                });
                if (saveResp.ok) {
                    const saveResult = await saveResp.json();
                    console.log(`[FlowCreator] Deployed ${newItem.id} with config:`, saveResult.path);
                } else {
                    console.error(`[FlowCreator] Failed to deploy ${newItem.id}:`, saveResp.statusText);
                }
            } else {
                const deployResp = await fetch(`/agent/deploy_agent_template/${newItem.id}/`, {
                    method: 'POST',
                    headers: getHeaders(),
                    credentials: 'same-origin'
                });
                if (deployResp.ok) {
                    console.log(`[FlowCreator] Deployed template ${newItem.id}`);
                }
            }
        } catch (deployErr) {
            console.error(`[FlowCreator] Error deploying ${newItem.id}:`, deployErr);
        }

        loadedNodes.push(newItem);
    }

    // Create connections
    for (const connData of connections) {
        const sourceNode = loadedNodes[connData.sourceIndex];
        const targetNode = loadedNodes[connData.targetIndex];

        if (!sourceNode || !targetNode) {
            console.warn(`[FlowCreator] Skip connection: invalid indices ${connData.sourceIndex}->${connData.targetIndex}`);
            continue;
        }

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

            // Restore backend connections
            await restoreAgentConnection(sourceNode, targetNode, connData);

        } catch (connErr) {
            console.error(`[FlowCreator] Error creating connection:`, connErr);
        }
    }

    // Force layout update
    setTimeout(() => {
        loadedNodes.forEach(node => updateAttachedConnections(node));
        if (flowCreatorItem) updateAttachedConnections(flowCreatorItem);
    }, 200);

    updateSaveButtonState();
    markDirty();
}

// ========================================
// FLOWCREATOR PROGRESS DIALOG HELPERS
// ========================================

function _showFlowCreatorProgress(message) {
    const overlay = document.createElement('div');
    overlay.id = 'flowcreator-progress-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.7);z-index:10000;display:flex;align-items:center;justify-content:center;';

    const box = document.createElement('div');
    box.style.cssText = 'background:#2a2a2a;border:1px solid #4FC3F7;border-radius:10px;padding:30px 40px;text-align:center;min-width:400px;';

    const spinner = document.createElement('div');
    spinner.style.cssText = 'width:40px;height:40px;border:4px solid #333;border-top:4px solid #4FC3F7;border-radius:50%;animation:fc-spin 1s linear infinite;margin:0 auto 15px;';

    const style = document.createElement('style');
    style.textContent = '@keyframes fc-spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}';
    document.head.appendChild(style);

    const msgEl = document.createElement('p');
    msgEl.id = 'flowcreator-progress-message';
    msgEl.style.cssText = 'color:#4FC3F7;font-size:1.1em;margin:0;';
    msgEl.textContent = message;

    box.appendChild(spinner);
    box.appendChild(msgEl);
    overlay.appendChild(box);
    document.body.appendChild(overlay);

    return overlay;
}

function _updateFlowCreatorProgress(overlay, message) {
    if (!overlay) return;
    const msgEl = overlay.querySelector('#flowcreator-progress-message');
    if (msgEl) msgEl.textContent = message;
}

function _closeFlowCreatorProgress(overlay) {
    if (overlay && overlay.parentNode) {
        overlay.parentNode.removeChild(overlay);
    }
}






