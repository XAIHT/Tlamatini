/* Tlamatini Author Banner — Angela López Mendoza · @angelahack1 */
/* global ACP, canvasContent, submonitor, undoManager, globalRunningState, GLOBAL_STATE,
   isBusyProcessing, markDirty, updateCanvasContentSize, updateSaveButtonState,
   selectItem, deselectAll, cloneAndRegister, captureItemState, captureConnectionState,
   recreateCanvasItem, recreateConnection, deleteCanvasItemWithoutUndo, getHeaders, restoreParametrizerMappings,
   updateAttachedConnections, loadDiagram, acpAlert */

// Loaded after the existing canvas modules: all editing goes through their APIs.
(() => {
    'use strict';
    const UI = window.FlowCanvasInteractions;
    const byId = id => document.getElementById(id);
    const nodes = () => [...canvasContent.querySelectorAll('.canvas-item')];
    const selected = () => [...ACP.selectedItems].filter(item => item.matches?.('.canvas-item') && item.isConnected);
    const singleton = item => ['flowcreator', 'flowhypervisor'].includes(item.dataset.agentName.toLowerCase());
    let startersSignature = '';
    let scheduled = false;

    ACP.canEdit = ({ withinEditorOperation = false } = {}) => globalRunningState === GLOBAL_STATE.STOPPED &&
        !isBusyProcessing && (!ACP.editorBusy || withinEditorOperation) && !ACP.fileLoading && !undoManager.isProcessing;

    ACP.refreshEditor = () => {
        const items = nodes();
        const selection = selected();
        const locked = !ACP.canEdit();
        if (locked) ACP.cancelConnection?.();
        canvasContent.querySelectorAll('.input-triangle, .output-triangle').forEach(port => { port.setAttribute('aria-disabled', String(locked)); port.tabIndex = locked ? -1 : 0; });
        byId('acp-undo').disabled = locked || !undoManager.canUndo();
        byId('acp-redo').disabled = locked || !undoManager.canRedo();
        byId('acp-configure').disabled = locked || selection.length !== 1;
        byId('acp-duplicate').disabled = locked || !selection.length || selection.some(singleton);
        byId('acp-delete').disabled = locked || !ACP.selectedItems.size;
        byId('acp-example').disabled = locked;
        byId('acp-flow-settings').disabled = locked;
        byId('acp-empty').hidden = items.length > 0;
        const starters = items.filter(item => item.classList.contains('starter-agent'));
        const signature = starters.map(item => item.id + ':' + item.textContent).join('|');
        const select = byId('acp-starter-select');
        if (signature !== startersSignature || !select.dataset.ready) {
            const previous = select.value;
            select.replaceChildren(new Option(starters.length ? 'All Starters run together' : 'Add a Starter', ''));
            starters.forEach(item => select.add(new Option(item.textContent.trim(), item.id)));
            if (starters.some(item => item.id === previous)) select.value = previous;
            select.dataset.ready = 'true';
            startersSignature = signature;
        }
        select.disabled = locked || !starters.length;
        byId('acp-zoom-label').value = Math.round(ACP.zoom * 100) + '%';
        byId('acp-zoom-out').disabled = ACP.zoom <= .25;
        byId('acp-zoom-in').disabled = ACP.zoom >= 2;
    };

    ACP.performEdit = async action => {
        if (!ACP.canEdit()) return;
        ACP.cancelConnection?.();
        ACP.editorBusy = true;
        ACP.refreshEditor();
        try { await action(); }
        catch (error) { await acpAlert(error.message || 'The edit could not be completed.'); }
        finally {
            ACP.editorBusy = false;
            updateCanvasContentSize();
            updateSaveButtonState();
            ACP.refreshEditor();
        }
    };

    function setZoom(value, center = true) {
        ACP.cancelConnection?.();
        const zoom = UI.clampZoom(value);
        const x = (submonitor.scrollLeft + submonitor.clientWidth / 2) / ACP.zoom;
        const y = (submonitor.scrollTop + submonitor.clientHeight / 2) / ACP.zoom;
        ACP.zoom = zoom;
        canvasContent.style.zoom = String(zoom);
        updateCanvasContentSize();
        nodes().forEach(updateAttachedConnections);
        if (center) {
            submonitor.scrollLeft = x * zoom - submonitor.clientWidth / 2;
            submonitor.scrollTop = y * zoom - submonitor.clientHeight / 2;
        }
        ACP.refreshEditor();
    }

    function fit() {
        const items = nodes();
        if (!items.length) { setZoom(1, false); submonitor.scrollTo(0, 0); return; }
        const left = Math.min(...items.map(item => item.offsetLeft));
        const top = Math.min(...items.map(item => item.offsetTop));
        const right = Math.max(...items.map(item => item.offsetLeft + item.offsetWidth));
        const bottom = Math.max(...items.map(item => item.offsetTop + item.offsetHeight));
        const view = UI.fitView(submonitor, { left, top, right, bottom });
        setZoom(view.zoom, false);
        submonitor.scrollLeft = view.left;
        submonitor.scrollTop = view.top;
    }

    function locate(item) {
        selectItem(item);
        submonitor.scrollLeft = (item.offsetLeft + item.offsetWidth / 2) * ACP.zoom - submonitor.clientWidth / 2;
        submonitor.scrollTop = (item.offsetTop + item.offsetHeight / 2) * ACP.zoom - submonitor.clientHeight / 2;
        ACP.refreshEditor();
    }

    async function duplicate({ offset = 40, deferHistory = false } = {}) {
        const originals = selected();
        if (!originals.length || originals.some(singleton)) return;
        // Read real configurations before creating anything. A failed read leaves
        // the original diagram untouched instead of creating an incomplete copy.
        const configs = new Map();
        for (const item of originals) {
            const response = await fetch('/agent/load_agent_config/' + item.id + '/', { headers: getHeaders() });
            if (!response.ok) throw new Error('Could not read configuration for ' + item.id);
            const config = await response.json();
            // Mapping artifacts are saved separately from config.yaml. Their
            // current UI value is maintained by the mapping dialog and .flw load.
            const mappings = ACP.nodeConfigs.get(item.id)?._parametrizer_mappings;
            if (item.dataset.agentName.toLowerCase() === 'parametrizer' && Array.isArray(mappings)) {
                config._parametrizer_mappings = JSON.parse(JSON.stringify(mappings));
            }
            configs.set(item, config);
        }
        const copies = new Map();
        const connections = ACP.connections.filter(conn => originals.includes(conn.source) && originals.includes(conn.target));
        try {
            for (const item of originals) {
                const copy = cloneAndRegister(item);
                copies.set(item, copy);
                copy.style.left = item.offsetLeft + offset + 'px';
                copy.style.top = item.offsetTop + offset + 'px';
                const response = await fetch('/agent/deploy_agent_template/' + copy.id + '/', {
                    method: 'POST', headers: getHeaders(), credentials: 'same-origin'
                });
                if (!response.ok) throw new Error('Could not deploy ' + copy.id);
            }
            const ids = new Map([...copies].flatMap(([old, copy]) => [
                [old.id, copy.id], [old.id.replaceAll('-', '_'), copy.id.replaceAll('-', '_')]
            ]));
            const remap = (value, reference = false) => {
                if (typeof value === 'string') return reference ? ids.get(value) || value : value;
                if (Array.isArray(value)) return value.map(entry => remap(entry, reference));
                if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, entry]) => [key,
                    remap(entry, /^(source|target|output)_agents?(_[a-z0-9]+)?$/.test(key))]));
                return value;
            };
            for (const [original, copy] of copies) {
                const config = remap(configs.get(original));
                const response = await fetch('/agent/save_agent_config/' + copy.id + '/', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', ...getHeaders() },
                    credentials: 'same-origin', body: JSON.stringify(config)
                });
                if (!response.ok) throw new Error('Could not save configuration for ' + copy.id);
                if (copy.dataset.agentName.toLowerCase() === 'parametrizer') await restoreParametrizerMappings(copy.id, config);
                ACP.nodeConfigs.set(copy.id, config);
            }
            for (const conn of connections) await recreateConnection({
                ...captureConnectionState(conn), sourceId: copies.get(conn.source).id, targetId: copies.get(conn.target).id
            });
        } catch (error) {
            for (const copy of copies.values()) await deleteCanvasItemWithoutUndo(copy.id);
            throw error;
        }
        const record = () => {
        const states = [...copies.values()].map(captureItemState);
        const links = ACP.connections.filter(conn => [...copies.values()].includes(conn.source) && [...copies.values()].includes(conn.target)).map(captureConnectionState);
        undoManager.record({ type: 'DUPLICATE',
            undo: async () => { for (const state of states) await deleteCanvasItemWithoutUndo(state.id); },
            redo: async () => {
                for (const state of states) await recreateCanvasItem(state);
                for (const link of links) await recreateConnection(link);
            }
        });
        };
        if (!deferHistory) record();
        deselectAll();
        copies.forEach(copy => selectItem(copy, true));
        markDirty();
        return { copies, record };
    }
    ACP.duplicateSelection = duplicate;

    function dialog(title, content, buttons = [{ text: 'Close', click() { $(this).dialog('close'); } }]) {
        const element = $('<div class="acp-editor-dialog">').append(content).appendTo(document.body);
        element.dialog({ title, modal: true, dialogClass: 'acp-editor-dialog-window', width: Math.min(660, window.innerWidth - 32),
            maxHeight: window.innerHeight - 40, buttons,
            open() { element.parent().find('.ui-dialog-buttonpane button').addClass('ui-button'); },
            close() { element.dialog('destroy').remove(); }
        });
        return element;
    }

    function help() {
        dialog('Agentic Control Panel — Help', $('<div>').append(
            $('<p>').text('Build a .flw diagram from the Agents bar. Search by name, then drag an agent onto the dotted canvas.'),
            $('<ul>').append([
                'Connect an output triangle to an input triangle. Starter agents define entry points; Start runs all Starters together.',
                'Click an agent to select it. Ctrl+click adds agents to the selection; drag the canvas background to select an area.',
                'Configure opens the selected agent’s existing settings. You can also double-click an agent or use its context menu.',
                'Duplicate copies selected agents, their settings, and connections within the selection. FlowCreator and FlowHypervisor are limited to one per flow.',
                'Undo: Ctrl+Z. Redo: Ctrl+Y or Ctrl+Shift+Z. Delete removes the selected agents or connections.',
                'Use −, +, and Fit to view the flow. Zoom and the dot grid do not change saved agent coordinates.',
                'Editing controls are locked while a flow is running or paused. Stop the flow to edit it.',
                'Use File → Open or Save as for .flw files. A leading • in the browser title means unsaved changes.'
            ].map(text => $('<li>').text(text)))
        ));
    }

    function settings() {
        const content = $('<div>');
        content.append($('<p>').text(nodes().length + ' agents · ' + ACP.connections.length + ' connections'));
        content.append($('<p>').text('Start runs all Starter agents. Configure each Starter’s targets on the canvas. FlowCreator and FlowHypervisor keep their existing per-agent settings.'));
        const grid = $('<input type="checkbox" class="tlm-dlg-check" id="acp-setting-grid">').prop('checked', !canvasContent.classList.contains('acp-grid-hidden'));
        content.append($('<label for="acp-setting-grid">').append(grid, ' Show canvas dots'));
        const zoom = $('<select class="tlm-dlg-input" id="acp-setting-zoom">');
        [...new Set([.25, .5, .75, 1, 1.2, 1.5, 2, ACP.zoom])].sort((a, b) => a - b)
            .forEach(value => zoom.append(new Option(Math.round(value * 100) + '%', value)));
        zoom.val(String(ACP.zoom));
        content.append($('<label for="acp-setting-zoom">').append('Canvas zoom', zoom));
        content.append($('<p class="tlm-dlg-hint">').text('Canvas preferences apply to this browser. Agent settings are saved in the .flw file.'));
        const buttons = nodes().filter(item => ['starter', 'flowcreator', 'flowhypervisor'].includes(item.dataset.agentName.toLowerCase())).map(item => ({
            text: 'Configure ' + item.textContent.trim(), click() {
                $(this).dialog('close'); locate(item); ACP.performEdit(() => ACP.configureItem(item));
            }
        }));
        buttons.push({ text: 'Apply', click() {
            if (!ACP.canEdit()) return;
            canvasContent.classList.toggle('acp-grid-hidden', !grid.prop('checked'));
            setZoom(Number(zoom.val()));
            try { localStorage.setItem('acp-canvas-grid', String(grid.prop('checked'))); } catch (_error) { /* Private storage may be unavailable. */ }
            $(this).dialog('close');
        } }, { text: 'Cancel', click() { $(this).dialog('close'); } });
        dialog('Flow settings', content, buttons);
    }

    async function example() {
        if (nodes().length) return;
        const loaded = await loadDiagram({ nodes: [
            { text: 'Starter', left: '100px', top: '140px' },
            { text: 'Sleeper', left: '380px', top: '140px', configData: { duration_ms: 1000, source_agents: ['starter_1'], target_agents: ['ender_1'] } },
            { text: 'Ender', left: '660px', top: '140px' }
        ], connections: [
            { sourceIndex: 0, targetIndex: 1, inputSlot: 0, outputSlot: 0 },
            { sourceIndex: 1, targetIndex: 2, inputSlot: 0, outputSlot: 0 }
        ] }, 'example.flw', { withinEditorOperation: true });
        if (!loaded) return;
        const states = nodes().map(captureItemState);
        const links = ACP.connections.map(captureConnectionState);
        undoManager.record({ type: 'EXAMPLE',
            undo: async () => { for (const state of states) await deleteCanvasItemWithoutUndo(state.id); },
            redo: async () => {
                for (const state of states) await recreateCanvasItem(state);
                for (const link of links) await recreateConnection(link);
            }
        });
        markDirty(); fit();
    }

    const edit = (id, action) => byId(id).addEventListener('click', () => ACP.performEdit(action));
    edit('acp-undo', async () => { if (await undoManager.undo()) markDirty(); });
    edit('acp-redo', async () => { if (await undoManager.redo()) markDirty(); });
    edit('acp-configure', () => ACP.configureItem(selected()[0]));
    edit('acp-delete', () => ACP.deleteSelection());
    edit('acp-duplicate', duplicate);
    edit('acp-example', example);
    byId('acp-help').addEventListener('click', event => { event.preventDefault(); help(); });
    byId('acp-flow-settings').addEventListener('click', settings);
    byId('acp-zoom-out').addEventListener('click', () => setZoom(Math.round((ACP.zoom - .1) * 100) / 100));
    byId('acp-zoom-in').addEventListener('click', () => setZoom(Math.round((ACP.zoom + .1) * 100) / 100));
    byId('acp-fit').addEventListener('click', fit);
    byId('acp-starter-select').addEventListener('change', event => {
        const item = document.getElementById(event.target.value);
        if (item?.matches('.canvas-item.starter-agent')) locate(item);
    });
    // Keyboard and wheel gestures match the Prompt Flow editor.
    submonitor.addEventListener('wheel', event => {
        if (!UI.modified(event)) return;
        event.preventDefault(); setZoom(ACP.zoom + (event.deltaY < 0 ? .1 : -.1));
    }, { passive: false });
    document.addEventListener('keydown', event => {
        if (UI.isTyping(event) || event.target.matches('#drag-divider')) return;
        const key = event.key.toLowerCase(), mod = UI.modified(event);
        if (mod && ['a', 'd', 's', 'o'].includes(key)) {
            event.preventDefault();
            if (key === 'a') { deselectAll(); nodes().forEach(item => selectItem(item, true)); ACP.refreshEditor(); }
            else if (key === 'd') ACP.performEdit(duplicate);
            else byId(key === 's' ? 'save-as-button' : 'file-open-button').click();
        } else if (event.key === 'Escape') {
            ACP.cancelConnection?.(); ACP.cancelMove?.();
            ACP.cancelSelection?.();
            deselectAll(); ACP.refreshEditor();
        } else if (event.key === 'Enter' && selected().length === 1 && !event.target.matches('button, a')) {
            event.preventDefault(); ACP.performEdit(() => ACP.configureItem(selected()[0]));
        } else if (event.key.startsWith('Arrow') && selected().length && ACP.canEdit()) {
            event.preventDefault();
            const amount = event.shiftKey ? 40 : 10;
            const moves = selected().map(item => ({ item, left: item.offsetLeft, top: item.offsetTop }));
            const dx = event.key === 'ArrowRight' ? amount : event.key === 'ArrowLeft' ? -amount : 0;
            const dy = event.key === 'ArrowDown' ? amount : event.key === 'ArrowUp' ? -amount : 0;
            const apply = (forward) => moves.forEach(({ item, left, top }) => {
                item.style.left = Math.max(0, left + (forward ? dx : 0)) + 'px';
                item.style.top = Math.max(0, top + (forward ? dy : 0)) + 'px';
                updateAttachedConnections(item); updateCanvasContentSize();
            });
            ACP.cancelConnection?.(); apply(true);
            undoManager.record({ type: 'MOVE_ITEMS', undo: () => apply(false), redo: () => apply(true) });
            markDirty(); ACP.refreshEditor();
        }
    });
    const refresh = () => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => { scheduled = false; ACP.refreshEditor(); });
    };
    new MutationObserver(refresh).observe(canvasContent, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
    new MutationObserver(refresh).observe(byId('monitor-controls'), { subtree: true, attributes: true, attributeFilter: ['disabled'] });
    new ResizeObserver(() => updateCanvasContentSize()).observe(submonitor);
    try { canvasContent.classList.toggle('acp-grid-hidden', localStorage.getItem('acp-canvas-grid') === 'false'); } catch (_error) { /* Use the default dots. */ }
    updateCanvasContentSize();
    ACP.refreshEditor();
})();
