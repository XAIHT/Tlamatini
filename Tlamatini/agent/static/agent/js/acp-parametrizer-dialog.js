// Agentic Control Panel - Parametrizer Mapping Dialog
// LOAD ORDER: #11 - Depends on: acp-globals.js, acp-session.js
/* global ACP, getHeaders, markDirty */

// ========================================
// PARAMETRIZER CONFIGURATION DIALOG
// ========================================

/**
 * Open the Parametrizer mapping dialog.
 * Fetches source output fields and target config params from the backend,
 * then renders a two-column UI with SVG curved lines for mapping.
 */
async function openParametrizerDialog(agentId) { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/get_parametrizer_dialog_data/${agentId}/`, {
            headers: getHeaders(),
            credentials: 'same-origin'
        });
        const data = await response.json();

        if (!data.success) {
            _showParametrizerError(data.message || 'Failed to load Parametrizer configuration.');
            return;
        }

        _renderParametrizerMappingDialog(agentId, data);
    } catch (err) {
        console.error('Error opening Parametrizer dialog:', err);
        _showParametrizerError('Failed to communicate with the server.');
    }
}


/**
 * Show an error dialog when Parametrizer validation fails.
 */
function _showParametrizerError(message) {
    // Remove any existing overlay
    const existing = document.getElementById('parametrizer-error-overlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'parametrizer-error-overlay';
    Object.assign(overlay.style, {
        position: 'fixed', top: '0', left: '0', width: '100%', height: '100%',
        backgroundColor: 'rgba(0,0,0,0.6)', zIndex: '10000',
        display: 'flex', alignItems: 'center', justifyContent: 'center'
    });

    const dialog = document.createElement('div');
    Object.assign(dialog.style, {
        background: '#2d2d30', color: '#fff', borderRadius: '10px', padding: '30px',
        maxWidth: '500px', width: '90%', textAlign: 'center',
        boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
        border: '2px solid #AA00FF'
    });

    dialog.innerHTML = `
        <h3 style="margin-top:0; color:#FF6D00;">Parametrizer Validation Error</h3>
        <p style="color:#ccc; line-height:1.6;">${message}</p>
        <button id="parametrizer-error-ok" style="
            margin-top:15px; padding:8px 30px; border:none; border-radius:5px;
            background:linear-gradient(135deg, #311B92, #AA00FF);
            color:white; cursor:pointer; font-size:14px;
        ">OK</button>
    `;

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    document.getElementById('parametrizer-error-ok').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
}


function _normalizeParametrizerTargetMarker(marker) {
    const normalized = String(marker || '').trim();
    if (normalized.startsWith('{') && normalized.endsWith('}')) {
        return normalized.slice(1, -1).trim();
    }
    return normalized;
}


function _buildParametrizerTargetSlotKey(targetParam, targetMarker = '') {
    return `${targetParam}::${_normalizeParametrizerTargetMarker(targetMarker)}`;
}


function _buildParametrizerMappingKey(mapping) {
    return `${mapping.source_field}=>${_buildParametrizerTargetSlotKey(mapping.target_param, mapping.target_marker)}`;
}


/**
 * Render the two-column mapping dialog with SVG curved connection lines.
 */
function _renderParametrizerMappingDialog(agentId, data) {
    // Remove any existing dialog
    const existing = document.getElementById('parametrizer-dialog-overlay');
    if (existing) existing.remove();

    const {
        source_agent,
        target_agent,
        source_fields,
        target_params,
        target_markers = {},
        existing_mappings
    } = data;

    // Track current mappings as individual source -> target-slot records.
    const mappings = [];
    const seenMappings = new Set();
    if (existing_mappings) {
        for (const mapping of existing_mappings) {
            const normalized = {
                source_field: mapping.source_field,
                target_param: mapping.target_param,
                target_marker: _normalizeParametrizerTargetMarker(mapping.target_marker)
            };
            const mappingKey = _buildParametrizerMappingKey(normalized);
            if (!seenMappings.has(mappingKey)) {
                seenMappings.add(mappingKey);
                mappings.push(normalized);
            }
        }
    }

    // Build overlay
    const overlay = document.createElement('div');
    overlay.id = 'parametrizer-dialog-overlay';
    Object.assign(overlay.style, {
        position: 'fixed', top: '0', left: '0', width: '100%', height: '100%',
        backgroundColor: 'rgba(0,0,0,0.6)', zIndex: '10000',
        display: 'flex', alignItems: 'center', justifyContent: 'center'
    });

    const dialog = document.createElement('div');
    dialog.id = 'parametrizer-dialog';
    Object.assign(dialog.style, {
        background: '#1e1e1e', color: '#fff', borderRadius: '12px', padding: '25px',
        maxWidth: '800px', width: '90%', maxHeight: '80vh', overflowY: 'auto',
        boxShadow: '0 8px 32px rgba(0,0,0,0.6)',
        border: '2px solid #AA00FF', position: 'relative'
    });

    // Header
    const header = document.createElement('div');
    header.style.marginBottom = '20px';
    header.innerHTML = `
        <h3 style="margin:0 0 5px; background: linear-gradient(135deg, #311B92, #AA00FF, #FF6D00, #00E5FF);
            -webkit-background-clip: text; -webkit-text-fill-color: transparent;
            background-clip: text; font-size: 1.3em;">
            Parametrizer Mapping: ${agentId}
        </h3>
        <p style="margin:0; color:#999; font-size:0.85em;">
            Source: <strong style="color:#00E5FF">${source_agent}</strong> &rarr;
            Target: <strong style="color:#FF6D00">${target_agent}</strong>
        </p>
        <p style="margin:5px 0 0; color:#777; font-size:0.8em;">
            Click a source field (left), then click a target parameter (right) to create a mapping.
            Click an existing line to remove it.
        </p>
        <p style="margin:5px 0 0; color:#777; font-size:0.8em;">
            If a target value already contains configured markers such as {content}, they appear as indented target slots
            so Parametrizer can replace only that marker instead of overwriting the entire parameter.
        </p>
    `;
    dialog.appendChild(header);

    // Two-column container with SVG overlay
    const container = document.createElement('div');
    container.style.position = 'relative';
    container.style.display = 'flex';
    container.style.gap = '60px';
    container.style.minHeight = '200px';

    // Left column - Source Fields
    const leftCol = document.createElement('div');
    leftCol.style.flex = '1';
    const leftHeader = document.createElement('div');
    leftHeader.innerHTML = `<strong style="color:#00E5FF; font-size:0.9em;">Source Output Fields</strong>`;
    leftHeader.style.marginBottom = '10px';
    leftCol.appendChild(leftHeader);

    const sourceItems = [];
    for (const field of source_fields) {
        const item = document.createElement('div');
        item.dataset.field = field;
        item.className = 'parametrizer-source-item';
        Object.assign(item.style, {
            padding: '8px 12px', margin: '5px 0', borderRadius: '6px',
            background: '#2a2a2e', border: '1px solid #444', cursor: 'pointer',
            transition: 'all 0.2s', fontSize: '0.85em', textAlign: 'right'
        });
        item.textContent = field;
        leftCol.appendChild(item);
        sourceItems.push(item);
    }

    // Right column - Target Params
    const rightCol = document.createElement('div');
    rightCol.style.flex = '1';
    const rightHeader = document.createElement('div');
    rightHeader.innerHTML = `<strong style="color:#FF6D00; font-size:0.9em;">Target Config Parameters</strong>`;
    rightHeader.style.marginBottom = '10px';
    rightCol.appendChild(rightHeader);

    const targetItems = [];
    for (const param of target_params) {
        const markers = Array.isArray(target_markers[param]) ? target_markers[param] : [];
        const group = document.createElement('div');
        group.style.marginBottom = '8px';

        const item = document.createElement('div');
        item.dataset.param = param;
        item.dataset.marker = '';
        item.className = 'parametrizer-target-item';
        Object.assign(item.style, {
            padding: '8px 12px', margin: '5px 0', borderRadius: '6px',
            background: '#2a2a2e', border: '1px solid #444', cursor: 'pointer',
            transition: 'all 0.2s', fontSize: '0.85em'
        });
        if (markers.length > 0) {
            item.innerHTML = `
                <span>${param}</span>
                <span style="float:right; color:#AA00FF; font-size:0.75em;">${markers.length} marker${markers.length === 1 ? '' : 's'}</span>
            `;
        } else {
            item.textContent = param;
        }
        group.appendChild(item);
        targetItems.push({
            element: item,
            targetParam: param,
            targetMarker: '',
            slotKey: _buildParametrizerTargetSlotKey(param)
        });

        for (const rawMarker of markers) {
            const marker = _normalizeParametrizerTargetMarker(rawMarker);
            if (!marker) continue;

            const markerItem = document.createElement('div');
            markerItem.dataset.param = param;
            markerItem.dataset.marker = marker;
            markerItem.className = 'parametrizer-target-marker-item';
            Object.assign(markerItem.style, {
                padding: '6px 12px', margin: '4px 0 0 18px', borderRadius: '6px',
                background: '#242428', border: '1px dashed #555', cursor: 'pointer',
                transition: 'all 0.2s', fontSize: '0.8em', color: '#ddd'
            });
            markerItem.textContent = `{${marker}}`;
            group.appendChild(markerItem);
            targetItems.push({
                element: markerItem,
                targetParam: param,
                targetMarker: marker,
                slotKey: _buildParametrizerTargetSlotKey(param, marker)
            });
        }

        rightCol.appendChild(group);
    }

    container.appendChild(leftCol);
    container.appendChild(rightCol);

    // SVG overlay for curved lines
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.style.position = 'absolute';
    svg.style.top = '0';
    svg.style.left = '0';
    svg.style.width = '100%';
    svg.style.height = '100%';
    svg.style.pointerEvents = 'none';
    svg.style.overflow = 'visible';
    container.appendChild(svg);

    dialog.appendChild(container);

    // Buttons
    const btnRow = document.createElement('div');
    btnRow.style.marginTop = '20px';
    btnRow.style.textAlign = 'right';

    const clearBtn = document.createElement('button');
    clearBtn.textContent = 'Clear All';
    Object.assign(clearBtn.style, {
        padding: '8px 20px', border: '1px solid #666', borderRadius: '5px',
        background: '#333', color: '#fff', cursor: 'pointer', marginRight: '10px', fontSize: '13px'
    });

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancel';
    Object.assign(cancelBtn.style, {
        padding: '8px 20px', border: '1px solid #666', borderRadius: '5px',
        background: '#333', color: '#fff', cursor: 'pointer', marginRight: '10px', fontSize: '13px'
    });

    const saveBtn = document.createElement('button');
    saveBtn.textContent = 'Save Mappings';
    Object.assign(saveBtn.style, {
        padding: '8px 24px', border: 'none', borderRadius: '5px',
        background: 'linear-gradient(135deg, #311B92, #AA00FF)',
        color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 'bold'
    });

    btnRow.appendChild(clearBtn);
    btnRow.appendChild(cancelBtn);
    btnRow.appendChild(saveBtn);
    dialog.appendChild(btnRow);

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    // ---- INTERACTION LOGIC ----
    let selectedSource = null;

    function removeMappingByKey(mappingKey) {
        const index = mappings.findIndex((mapping) => _buildParametrizerMappingKey(mapping) === mappingKey);
        if (index >= 0) {
            mappings.splice(index, 1);
        }
    }

    function clearMappingsForTargetSlot(targetParam, targetMarker = '') {
        const normalizedMarker = _normalizeParametrizerTargetMarker(targetMarker);
        for (let index = mappings.length - 1; index >= 0; index -= 1) {
            const mapping = mappings[index];
            if (mapping.target_param !== targetParam) continue;

            const mappingMarker = _normalizeParametrizerTargetMarker(mapping.target_marker);
            if (!normalizedMarker) {
                mappings.splice(index, 1);
                continue;
            }

            if (!mappingMarker || mappingMarker === normalizedMarker) {
                mappings.splice(index, 1);
            }
        }
    }

    function updateLines() {
        // Clear existing lines
        while (svg.firstChild) svg.removeChild(svg.firstChild);

        const defs = document.createElementNS(svgNS, 'defs');
        const grad = document.createElementNS(svgNS, 'linearGradient');
        grad.id = 'param-grad';
        const start = document.createElementNS(svgNS, 'stop');
        start.setAttribute('offset', '0%');
        start.setAttribute('stop-color', '#00E5FF');
        const end = document.createElementNS(svgNS, 'stop');
        end.setAttribute('offset', '100%');
        end.setAttribute('stop-color', '#FF6D00');
        grad.appendChild(start);
        grad.appendChild(end);
        defs.appendChild(grad);
        svg.appendChild(defs);

        const containerRect = container.getBoundingClientRect();

        for (const mapping of mappings) {
            const srcEl = sourceItems.find((el) => el.dataset.field === mapping.source_field);
            const targetItem = targetItems.find((item) => item.slotKey === _buildParametrizerTargetSlotKey(mapping.target_param, mapping.target_marker));
            if (!srcEl || !targetItem) continue;

            const tgtEl = targetItem.element;
            const mappingKey = _buildParametrizerMappingKey(mapping);

            const srcRect = srcEl.getBoundingClientRect();
            const tgtRect = tgtEl.getBoundingClientRect();

            const x1 = srcRect.right - containerRect.left;
            const y1 = srcRect.top + srcRect.height / 2 - containerRect.top;
            const x2 = tgtRect.left - containerRect.left;
            const y2 = tgtRect.top + tgtRect.height / 2 - containerRect.top;

            const cpOffset = Math.abs(x2 - x1) * 0.5;

            const path = document.createElementNS(svgNS, 'path');
            path.setAttribute('d', `M ${x1} ${y1} C ${x1 + cpOffset} ${y1}, ${x2 - cpOffset} ${y2}, ${x2} ${y2}`);
            path.setAttribute('stroke', 'url(#param-grad)');
            path.setAttribute('stroke-width', '2.5');
            path.setAttribute('fill', 'none');
            path.style.pointerEvents = 'stroke';
            path.style.cursor = 'pointer';
            path.dataset.mappingKey = mappingKey;

            // Click to remove mapping
            path.addEventListener('click', () => {
                removeMappingByKey(mappingKey);
                updateHighlights();
                updateLines();
            });

            svg.appendChild(path);
        }
    }

    function updateHighlights() {
        for (const el of sourceItems) {
            const isMapped = mappings.some((mapping) => mapping.source_field === el.dataset.field);
            const isSelected = (selectedSource === el);
            el.style.border = isSelected ? '2px solid #00E5FF' :
                (isMapped ? '1px solid #00E5FF' : '1px solid #444');
            el.style.background = isSelected ? '#1a3a4a' :
                (isMapped ? '#1a2a2e' : '#2a2a2e');
        }
        for (const item of targetItems) {
            const exactMapped = mappings.some((mapping) => item.slotKey === _buildParametrizerTargetSlotKey(mapping.target_param, mapping.target_marker));
            const paramMapped = !item.targetMarker && mappings.some((mapping) => mapping.target_param === item.targetParam);

            if (item.targetMarker) {
                item.element.style.border = exactMapped ? '1px solid #FFB74D' : '1px dashed #555';
                item.element.style.background = exactMapped ? '#362b18' : '#242428';
            } else {
                item.element.style.border = exactMapped ? '1px solid #FF6D00' :
                    (paramMapped ? '1px solid #6D4C41' : '1px solid #444');
                item.element.style.background = exactMapped ? '#2e2a1a' :
                    (paramMapped ? '#26211d' : '#2a2a2e');
            }
        }
    }

    // Source item click
    for (const el of sourceItems) {
        el.addEventListener('click', () => {
            if (selectedSource === el) {
                selectedSource = null;
            } else {
                selectedSource = el;
            }
            updateHighlights();
        });
        el.addEventListener('mouseenter', () => { el.style.background = '#3a3a3e'; });
        el.addEventListener('mouseleave', () => { updateHighlights(); });
    }

    // Target item click
    for (const item of targetItems) {
        item.element.addEventListener('click', () => {
            if (!selectedSource) return;
            const sf = selectedSource.dataset.field;
            const tp = item.targetParam;
            const tm = item.targetMarker;

            clearMappingsForTargetSlot(tp, tm);
            mappings.push({ source_field: sf, target_param: tp, target_marker: tm });
            selectedSource = null;
            updateHighlights();
            updateLines();
        });
        item.element.addEventListener('mouseenter', () => {
            if (selectedSource) {
                item.element.style.background = item.targetMarker ? '#3a311a' : '#3e3a1a';
            }
        });
        item.element.addEventListener('mouseleave', () => { updateHighlights(); });
    }

    // Clear all
    clearBtn.addEventListener('click', () => {
        mappings.clear();
        selectedSource = null;
        updateHighlights();
        updateLines();
    });

    // Cancel
    cancelBtn.addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

    // Save
    saveBtn.addEventListener('click', async () => {
        const mappingsList = mappings.map((mapping) => ({
            source_field: mapping.source_field,
            target_param: mapping.target_param,
            target_marker: _normalizeParametrizerTargetMarker(mapping.target_marker)
        }));

        try {
            const resp = await fetch(`/agent/save_parametrizer_scheme/${agentId}/`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', ...getHeaders() },
                credentials: 'same-origin',
                body: JSON.stringify({ mappings: mappingsList })
            });
            const result = await resp.json();
            if (result.success) {
                console.log('Parametrizer scheme saved:', result.message);
                if (typeof ACP !== 'undefined' && ACP.nodeConfigs) {
                    ACP.nodeConfigs.set(agentId, {
                        ...(ACP.nodeConfigs.get(agentId) || {}),
                        _parametrizer_mappings: mappingsList
                    });
                }
                if (typeof markDirty === 'function') markDirty();
                overlay.remove();
            } else {
                _showParametrizerError(result.message || 'Failed to save mappings.');
            }
        } catch (err) {
            console.error('Error saving Parametrizer scheme:', err);
            _showParametrizerError('Failed to save mappings to server.');
        }
    });

    // Initial render
    updateHighlights();
    // Delay line rendering to allow layout to settle
    requestAnimationFrame(() => { updateLines(); });
}
