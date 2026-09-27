/* Tlamatini — "one who knows"
 * Created by Angela López Mendoza · @angelahack1
 * Tlamatini Author Banner — do not remove */
(() => {
    'use strict';
    const M = window.PromptFlowPanelModel, UI = window.FlowCanvasInteractions;
    const $id = id => document.getElementById(id);
    const viewport = $id('submonitor-container'), content = $id('canvas-content'), world = $id('pmt-world');
    const layer = $id('connections-layer'), nodesLayer = $id('pmt-nodes');
    // Preserve saved drafts across the panel rename.
    const storeKey = `tlamatini.prompting-flow.draft.v1.${document.body.dataset.userId}`;
    let flow = M.blank(), filename = 'Untitled.fpmt', clean = JSON.stringify(flow);
    let selected = new Set(), selectedEdge = null;
    const selectedEdges = new Set();
    let zoom = 1, undo = [], redo = [], gesture = null, dirty = false;
    let socket = null, connecting = null, runId = null, runState = 'idle', activeNode = null;
    let inputDialog = null, internalClose = false, draftTimer = null, socketReady = false;
    const nodeStates = new Map(), traversed = new Set();
    const editable = () => !['starting', 'running', 'paused', 'stopping'].includes(runState);
    const status = message => { $id('pmt-status').textContent = message; };
    const alertMessage = (message, title = 'Prompt Flow Panel') => window.tlmAlert(String(message), title);
    const confirm = (message, detail = '') => window.tlmConfirm(message, detail, 'Prompt Flow Panel');
    const svgNS = 'http://www.w3.org/2000/svg';
    function element(tag, className, text) {
        const el = document.createElement(tag);
        if (className) el.className = className;
        if (text !== undefined) el.textContent = text;
        return el;
    }
    function svg(tag, attrs = {}) {
        const el = document.createElementNS(svgNS, tag);
        for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
        return el;
    }
    function shape(type) {
        const info = M.operations[type], graphic = svg('svg', { viewBox: '0 0 200 128', 'aria-hidden': 'true' });
        graphic.style.setProperty('--pmt-color', info.color); graphic.style.setProperty('--pmt-fill', info.fill);
        graphic.append(svg('path', { d: info.path, class: 'pmt-shape' }));
        if (type === 'programmed_prompt') {
            graphic.append(svg('circle', { cx: 174, cy: 40, r: 20, class: 'pmt-clock' }), svg('path', { d: 'M174 25V40L185 46', fill: 'none', stroke: '#f3df9f', 'stroke-width': 2 }));
            for (let angle = 0; angle < 360; angle += 30) {
                const rad = angle * Math.PI / 180;
                graphic.append(svg('circle', { cx: 174 + Math.sin(rad) * 16, cy: 40 + Math.cos(rad) * 16, r: 1, fill: '#f3df9f' }));
            }
        }
        return graphic;
    }
    function snapshot() { return JSON.stringify(flow); }
    function persist() {
        clearTimeout(draftTimer);
        draftTimer = setTimeout(() => {
            try { localStorage.setItem(storeKey, JSON.stringify({ flow, filename, zoom })); }
            catch (error) { status(`Draft could not be stored in this browser. Save a .fpmt file: ${error.message}`); }
        }, 250);
    }
    function changed(before) {
        if (before !== snapshot()) {
            undo.push(before); if (undo.length > 100) undo.shift(); redo = [];
            nodeStates.clear(); traversed.clear(); dirty = snapshot() !== clean; persist();
        }
        render();
    }
    function mutate(fn) {
        if (!editable()) return;
        cancelConnection();
        const before = snapshot(); fn(); changed(before);
    }
    function resetSelection() { selected.clear(); selectedEdges.clear(); selectedEdge = null; }
    function position(event) {
        const rect = world.getBoundingClientRect();
        return { x: (event.clientX - rect.left) / zoom, y: (event.clientY - rect.top) / zoom };
    }
    const snap = value => Math.min(100000, Math.max(0, value));
    function extent() {
        const width = Math.max(1000, viewport.clientWidth / zoom, ...flow.nodes.map(n => n.x + 350));
        const height = Math.max(700, viewport.clientHeight / zoom, ...flow.nodes.map(n => n.y + 300));
        world.style.width = `${width}px`; world.style.height = `${height}px`;
        world.style.transform = `scale(${zoom})`;
        content.style.width = `${width * zoom}px`; content.style.height = `${height * zoom}px`;
        $id('pmt-zoom').textContent = `${Math.round(zoom * 100)}%`;
        updateButtons();
    }
    function anchor(node, port) {
        const info = M.operations[node.type], point = info[port === 'next' ? 'output' : port];
        // ACP wires join the centers of its 10 x 16 CSS triangles.
        return [node.x + point[0] + (port === 'input' ? -5 : 5), node.y + point[1]];
    }
    const connectionPath = UI.connectionPath;
    function selectEdge(event, edge) {
        if (event.button !== 0) return;
        event.preventDefault(); event.stopPropagation(); cancelConnection();
        if (!UI.modified(event)) resetSelection();
        if (UI.modified(event) && selectedEdges.has(edge.id)) selectedEdges.delete(edge.id); else selectedEdges.add(edge.id);
        selectedEdge = selectedEdges.size === 1 ? [...selectedEdges][0] : null;
        paintSelection();
    }
    function paintSelection() {
        nodesLayer.querySelectorAll('.pmt-node').forEach(n => n.classList.toggle('selected', selected.has(n.dataset.nodeId)));
        layer.querySelectorAll('.pmt-edge').forEach(e => e.classList.toggle('selected', selectedEdges.has(e.dataset.edgeId)));
        updateButtons();
    }
    function configureSelectedNode(node, event) {
        event?.preventDefault();
        if (editable()) { resetSelection(); selected.add(node.id); render(); configureNode(node); }
    }
    function showNodeMenu(node, event) {
        event.preventDefault(); event.stopPropagation(); endGesture();
        if (!selected.has(node.id)) { resetSelection(); selected.add(node.id); paintSelection(); }
        const menu = $id('agent-context-menu');
        menu.replaceChildren();
        for (const [icon, label, command] of [['⚙️', 'Configure', () => configureNode(node)], ['ℹ️', 'Description', () => alertMessage(M.operations[node.type].help, node.label)], ['▣', 'Duplicate', duplicate], ['⌫', 'Delete', deleteSelection]]) {
            const item = element('div', 'context-menu-item');
            const disabled = label !== 'Description' && !editable();
            item.classList.toggle('context-menu-item-disabled', disabled);
            item.append(element('span', 'context-menu-icon', icon), element('span', '', label));
            item.addEventListener('click', () => { menu.style.display = 'none'; if (!disabled) command(); });
            menu.append(item);
        }
        UI.showMenu(menu, event.clientX, event.clientY);
    }
    document.addEventListener('click', event => { if (!event.target.closest('#agent-context-menu')) $id('agent-context-menu').style.display = 'none'; });
    document.addEventListener('keydown', event => { if (event.key === 'Escape') $id('agent-context-menu').style.display = 'none'; });
    viewport.addEventListener('scroll', () => { $id('agent-context-menu').style.display = 'none'; });
    function nodeKey(event, node) {
        if (event.target.closest('.pmt-port')) return;
        if (event.key === 'Enter') configureSelectedNode(node, event);
    }
    function renderEdges() {
        layer.replaceChildren();
        const byId = new Map(flow.nodes.map(n => [n.id, n]));
        for (const edge of flow.edges) {
            const source = byId.get(edge.source), target = byId.get(edge.target);
            const [sx, sy] = anchor(source, edge.branch), [tx, ty] = anchor(target, 'input');
            const d = connectionPath(sx, sy, tx, ty);
            const group = svg('g', { class: `pmt-edge connection-group${selectedEdges.has(edge.id) ? ' selected' : ''}${traversed.has(edge.id) ? ' traversed' : ''}`, 'data-edge-id': edge.id });
            group.append(svg('path', { d, class: 'pmt-wire connection-path' }), svg('path', { d, class: 'pmt-wire-hit connection-hit-area' }));
            group.addEventListener('pointerdown', event => selectEdge(event, edge));
            group.addEventListener('dblclick', () => configureEdge(edge));
            layer.append(group);
        }
        if (connection.active) layer.append(connection.active.data.preview);
    }
    function addPort(el, node, name, point) {
        const direction = name === 'input' ? 'input' : 'output';
        const slot = name === 'yes' ? ' output-1' : name === 'no' ? ' output-2' : '';
        const button = element('button', `pmt-port ${direction} ${direction}-triangle${slot}`);
        button.type = 'button'; button.style.left = `${point[0]}px`; button.style.top = `${point[1]}px`;
        button.dataset.port = name;
        button.title = `${node.label}: ${name === 'next' ? 'output' : name}`;
        button.setAttribute('aria-label', button.title); button.disabled = !editable();
        button.addEventListener('pointerdown', event => {
            event.stopPropagation();
            if (event.button !== 0 || !editable()) return;
            event.preventDefault();
            if (name !== 'input') startConnection(node, name, button, event.pointerId);
        });
        // Keyboard users can activate an output, Tab to an input, then activate it.
        button.addEventListener('click', event => {
            event.stopPropagation();
            if (event.detail !== 0 || !editable()) return;
            if (name !== 'input') startConnection(node, name, button);
            else if (connection.active?.pointerId === undefined) connection.finish(button);
        });
        button.addEventListener('dblclick', event => event.stopPropagation());
        el.append(button);
        if (name === 'yes' || name === 'no') {
            const label = element('span', 'pmt-port-label output-label', name === 'yes' ? 'Y' : 'N');
            label.style.right = `${200 - point[0] + 6}px`; label.style.top = `${point[1]}px`; el.append(label);
        }
    }
    function render() {
        cancelConnection();
        nodesLayer.replaceChildren();
        for (const node of flow.nodes) {
            const info = M.operations[node.type], state = nodeStates.get(node.id) || '';
            const el = element('div', `pmt-node${selected.has(node.id) ? ' selected' : ''} ${state}`);
            el.dataset.nodeId = node.id; el.dataset.type = node.type; el.tabIndex = 0;
            el.setAttribute('role', 'group'); el.setAttribute('aria-label', `${node.label}, ${info.label}`);
            el.style.left = `${node.x}px`; el.style.top = `${node.y}px`; el.append(shape(node.type));
            const label = element('div', 'pmt-node-label'); label.append(element('strong', '', node.label));
            if (node.label !== info.label && !['decision', 'feed_embeddings', 'flush_embeddings'].includes(node.type)) label.append(element('small', '', info.label));
            el.append(label);
            if (flow.start === node.id) el.append(element('span', 'pmt-start-badge', 'START'));
            if (state) el.append(element('span', 'pmt-node-status', state));
            addPort(el, node, 'input', info.input);
            if (node.type === 'decision') { addPort(el, node, 'yes', info.yes); addPort(el, node, 'no', info.no); }
            else addPort(el, node, 'next', info.output);
            el.addEventListener('pointerdown', event => nodeDown(event, node));
            el.addEventListener('dblclick', event => configureSelectedNode(node, event));
            el.addEventListener('contextmenu', event => showNodeMenu(node, event));
            el.addEventListener('keydown', event => nodeKey(event, node));
            nodesLayer.append(el);
        }
        renderEdges(); extent();
        $id('pmt-empty').hidden = flow.nodes.length > 0;
        $id('filename').textContent = `${filename}${dirty ? ' •' : ''}`;
        document.title = `${dirty ? '• ' : ''}${flow.name} — Prompt Flow Panel`;
        $id('pmt-count').textContent = `${flow.nodes.length} operations · ${flow.edges.length} connections`;
        const select = $id('pmt-start'); select.replaceChildren();
        if (!flow.nodes.length) select.append(new Option('Add an operation', ''));
        for (const n of flow.nodes) select.append(new Option(n.label, n.id));
        select.value = flow.start || ''; select.disabled = !editable();
        updateButtons();
    }
    function updateButtons() {
        for (const button of document.querySelectorAll('[data-action]')) {
            const action = button.dataset.action;
            if (['new', 'open', 'example', 'settings', 'validate'].includes(action)) button.disabled = !editable();
            if (action === 'undo') button.disabled = !editable() || !undo.length;
            if (action === 'redo') button.disabled = !editable() || !redo.length;
            if (action === 'zoom-out') button.disabled = zoom <= .25;
            if (action === 'zoom-in') button.disabled = zoom >= 2;
            if (action === 'configure') button.disabled = !editable() || selected.size + selectedEdges.size !== 1;
            if (action === 'duplicate') button.disabled = !editable() || !selected.size;
            if (action === 'delete') button.disabled = !editable() || !(selected.size || selectedEdges.size);
            if (action === 'play') button.disabled = !socketReady || !editable() || !flow.nodes.length;
            if (action === 'reconnect') button.disabled = !!connecting || socketReady;
            if (action === 'pause') { button.disabled = !['running', 'paused'].includes(runState); button.textContent = runState === 'paused' ? '▶ Resume' : 'Ⅱ Pause'; }
            if (action === 'stop') button.disabled = !['running', 'paused'].includes(runState);
        }
        for (const button of document.querySelectorAll('.agent-tool-item')) { button.disabled = !editable(); button.draggable = editable(); }
    }
    function palette() {
        const list = $id('agents-list'); list.replaceChildren();
        for (const [type, info] of Object.entries(M.operations)) {
            const button = element('button', 'agent-tool-item'); button.type = 'button'; button.dataset.type = type; button.title = info.help;
            button.append(shape(type)); button.draggable = true;
            button.append(element('span', '', info.label));
            button.addEventListener('dragstart', event => { if (!editable()) { event.preventDefault(); return; } event.dataTransfer.setData('application/x-tlamatini-operation', type); event.dataTransfer.effectAllowed = 'copy'; });
            button.addEventListener('click', () => addNode(type));
            list.append(button);
        }
        updateButtons();
    }
    function addNode(type, point) {
        if (!Object.hasOwn(M.operations, type) || flow.nodes.length >= 500) return;
        const offset = (flow.nodes.length % 6) * 30;
        point = point || { x: viewport.scrollLeft / zoom + 70 + offset, y: viewport.scrollTop / zoom + 65 + offset };
        mutate(() => {
            const n = M.node(type, snap(point.x), snap(point.y));
            const labels = new Set(flow.nodes.map(node => node.label));
            if (labels.has(n.label)) n.label = M.uniqueLabel(n.label, labels);
            flow.nodes.push(n); flow.start ||= n.id; selected = new Set([n.id]); selectedEdge = null; selectedEdges.clear();
        });
        status('Operation added. Double-click it to configure.');
    }
    const connection = UI.connectionDrag({
        viewport, canEdit: editable,
        targetAt: event => {
            const port = document.elementFromPoint(event.clientX, event.clientY)?.closest('.pmt-port.input');
            return port && nodesLayer.contains(port) && !port.disabled ? port : null;
        },
        begin: port => {
            const node = flow.nodes.find(n => n.id === port.closest('.pmt-node').dataset.nodeId);
            const branch = port.dataset.port, [sx, sy] = anchor(node, branch);
            const preview = svg('path', { class: 'pmt-connection-preview connection-preview connection-path', d: connectionPath(sx, sy, sx, sy) });
            layer.append(preview);
            status('Drag to an input triangle. Escape cancels.');
            return { source: node.id, branch, preview, sx, sy };
        },
        move: (data, event) => {
            const p = position(event);
            data.preview.setAttribute('d', connectionPath(data.sx, data.sy, p.x, p.y));
        },
        complete: (source, port) => {
            const targetId = port.closest('.pmt-node').dataset.nodeId;
            mutate(() => {
                const existing = flow.edges.find(e => e.source === source.source && e.branch === source.branch);
                if (existing) existing.target = targetId;
                else flow.edges.push({ id: M.id(), source: source.source, target: targetId, branch: source.branch });
            });
            status('Connection saved. Each output leads to one next operation.');
        },
        dispose: data => data.preview.remove()
    });
    function cancelConnection() { return connection.cancel(); }
    function startConnection(_node, _branch, port, pointerId) {
        endGesture(); connection.start(port, pointerId);
    }
    const nodeMove = UI.nodeDrag({
        viewport,
        duplicate: data => {
            const copies = duplicateNodes(0);
            data.origins = new Map(copies.map(n => [n.id, { x: n.x, y: n.y }]));
        },
        move: (data, dx, dy) => {
            for (const n of flow.nodes) if (data.origins.has(n.id)) {
                const origin = data.origins.get(n.id);
                n.x = snap(origin.x + dx / data.zoom); n.y = snap(origin.y + dy / data.zoom);
            }
            render();
        },
        finish: (data, cancelled) => {
            if (cancelled) { flow = JSON.parse(data.before); selected = data.selection; render(); }
            else changed(data.before);
        },
        failed: error => { status(error.message); alertMessage(error.message); }
    });
    function nodeDown(event, node) {
        if (event.button !== 0 || event.target.closest('button')) return;
        event.stopPropagation();
        if (nodeMove.active) return;
        cancelConnection();
        if (!UI.modified(event) && !selected.has(node.id)) resetSelection();
        selected.add(node.id);
        if (editable() && selected.has(node.id)) {
            nodeMove.start(event, { before: snapshot(), zoom, selection: new Set(selected),
                origins: new Map(flow.nodes.filter(n => selected.has(n.id)).map(n => [n.id, { x: n.x, y: n.y }])) });
        }
        paintSelection(); event.preventDefault(); viewport.focus({ preventScroll: true });
    }
    function deleteSelection() {
        mutate(() => {
            flow.nodes = flow.nodes.filter(n => !selected.has(n.id));
            flow.edges = flow.edges.filter(e => !selectedEdges.has(e.id) && !selected.has(e.source) && !selected.has(e.target));
            if (selected.has(flow.start)) flow.start = flow.nodes[0]?.id || null;
            resetSelection();
        });
    }
    function duplicateNodes(offset = 40) {
            if (flow.nodes.length + selected.size > 500) throw new Error('The canvas supports up to 500 operations.');
            const labels = new Set(flow.nodes.map(n => n.label));
            const mapping = new Map(), copies = flow.nodes.filter(n => selected.has(n.id)).map(n => {
                const clone = M.copy(n); clone.id = M.id(); clone.label = M.uniqueLabel(n.label, labels);
                labels.add(clone.label); clone.x = snap(n.x + offset); clone.y = snap(n.y + offset); mapping.set(n.id, clone.id); return clone;
            });
            const links = flow.edges.filter(e => mapping.has(e.source) && mapping.has(e.target)).map(e => ({ ...e, id: M.id(), source: mapping.get(e.source), target: mapping.get(e.target) }));
            flow.nodes.push(...copies); flow.edges.push(...links); selected = new Set(mapping.values()); selectedEdge = null; selectedEdges.clear();
            return copies;
    }
    function duplicate() {
        mutate(() => duplicateNodes());
    }
    function restoreHistory(from, to) {
        if (!editable() || !from.length) return;
        to.push(snapshot()); flow = JSON.parse(from.pop()); dirty = snapshot() !== clean;
        selected = new Set([...selected].filter(id => flow.nodes.some(node => node.id === id)));
        for (const id of selectedEdges) if (!flow.edges.some(edge => edge.id === id)) selectedEdges.delete(id);
        selectedEdge = selectedEdges.size === 1 ? [...selectedEdges][0] : null;
        nodeStates.clear(); traversed.clear(); persist(); render();
    }
    function formDialog(title, build, accept, options = {}) {
        const form = element('form', 'pmt-form'); const fields = {};
        function field(name, label, type, value, choices) {
            const row = element('label', type === 'checkbox' ? 'pmt-checkbox' : '');
            const input = element(type === 'textarea' ? 'textarea' : type === 'select' ? 'select' : 'input');
            if (input.tagName === 'INPUT') input.type = type;
            if (choices) for (const [v, text] of choices) input.append(new Option(text, v));
            if (type === 'checkbox') input.checked = Boolean(value); else input.value = value ?? '';
            input.name = name; input.id = `pmt-field-${name}`; row.htmlFor = input.id;
            if (type === 'checkbox') row.append(input, document.createTextNode(label)); else row.append(document.createTextNode(label), input);
            form.append(row); fields[name] = input; return input;
        }
        build({ form, field, fields });
        const error = element('p', 'pmt-form-error'); error.setAttribute('role', 'alert'); form.append(error);
        document.body.append(form);
        let accepted = false;
        const close = () => window.jQuery(form).dialog('close');
        const submit = async () => {
            try {
                if (!form.reportValidity()) return;
                await accept(fields); accepted = true; close();
            } catch (e) { error.textContent = e.message; }
        };
        form.addEventListener('submit', event => { event.preventDefault(); submit(); });
        const buttons = options.buttons ? options.buttons(fields, close, () => { accepted = true; }) : [{ text: options.acceptLabel || 'Save', click: submit }, { text: 'Cancel', click: close }];
        window.jQuery(form).dialog({ title, modal: true, resizable: false, width: Math.min(640, window.innerWidth - 24), closeOnEscape: true,
            buttons,
            close() { window.jQuery(form).dialog('destroy'); form.remove(); options.onClose?.(accepted); },
            open() { form.querySelector('textarea, input, select')?.focus(); },
        });
        return { close, form };
    }
    function configureNode(node) {
        if (!editable()) return;
        const draft = M.copy(node), config = draft.config, kind = draft.type;
        formDialog(`Configure · ${M.operations[kind].label}`, ({ form, field, fields }) => {
            form.append(element('p', '', M.operations[kind].help));
            field('label', 'Label', 'text', draft.label).maxLength = 120;
            if (!['flush_embeddings', 'clean_history'].includes(kind)) {
                const title = kind === 'decision' ? 'Question (when asking the user)' : kind === 'user_commentary' ? 'Message to the user' : kind === 'feed_embeddings' ? 'Text to embed' : 'Prompt';
                field('text', title, 'textarea', config.text).maxLength = 100000;
                form.append(element('small', '', 'Use {{last_output}} to insert the previous prompt answer or user reply.'));
            }
            if (['prompt', 'programmed_prompt'].includes(kind)) {
                field('multi_turn', 'Multi-Turn — allow enabled tools and agents', 'checkbox', config.multi_turn);
                field('acpx', 'ACPX — allow external coding agents', 'checkbox', config.acpx).disabled = !config.multi_turn;
                fields.multi_turn.addEventListener('change', () => { fields.acpx.disabled = !fields.multi_turn.checked; if (!fields.multi_turn.checked) fields.acpx.checked = false; });
            }
            if (kind === 'programmed_prompt') {
                const delay = field('delay_seconds', 'Delay before sending (seconds of active playback)', 'number', config.delay_seconds); delay.min = 0; delay.max = 86400; delay.step = 'any';
                let local = '';
                if (config.scheduled_at) { const date = new Date(config.scheduled_at); local = new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19); }
                field('scheduled_at', 'Scheduled time (optional, your local timezone)', 'datetime-local', local).step = '1';
                form.append(element('small', '', 'Wait until this time, then apply the delay. Past times run immediately. Keep the page and Tlamatini open.'));
            }
            if (kind === 'decision') {
                field('comparison', 'Decision rule', 'select', config.comparison, [['contains', 'Last output contains'], ['not_contains', 'Last output does not contain'], ['equals', 'Last output equals'], ['is_empty', 'Last output is empty'], ['user', 'Ask the user: Yes or No']]);
                field('value', 'Comparison value', 'text', config.value).maxLength = 10000;
                field('case_sensitive', 'Match case', 'checkbox', config.case_sensitive);
            }
        }, fields => {
            if (!editable()) throw new Error('Stop playback before editing.');
            draft.label = fields.label.value.trim() || M.operations[kind].label;
            if (fields.text) config.text = fields.text.value;
            for (const name of ['multi_turn', 'acpx', 'case_sensitive']) if (fields[name]) config[name] = fields[name].checked;
            for (const name of ['comparison', 'value']) if (fields[name]) config[name] = fields[name].value;
            if (fields.delay_seconds) config.delay_seconds = Number(fields.delay_seconds.value);
            if (fields.scheduled_at) config.scheduled_at = fields.scheduled_at.value ? new Date(fields.scheduled_at.value).toISOString() : '';
            const candidate = M.copy(flow); candidate.nodes[candidate.nodes.findIndex(n => n.id === node.id)] = draft;
            M.validate(candidate); mutate(() => { flow = candidate; });
        });
    }
    function configureEdge(edge) {
        if (!editable()) return;
        const source = flow.nodes.find(n => n.id === edge.source);
        formDialog('Configure connection', ({ field }) => {
            field('target', 'Destination', 'select', edge.target, flow.nodes.map(n => [n.id, n.label]));
            field('branch', 'Output', 'select', edge.branch, source.type === 'decision' ? [['yes', 'Yes'], ['no', 'No']] : [['next', 'Next']]);
        }, fields => {
            const candidate = M.copy(flow), item = candidate.edges.find(e => e.id === edge.id);
            item.target = fields.target.value; item.branch = fields.branch.value; M.validate(candidate);
            mutate(() => { flow = candidate; });
        });
    }
    async function mayReplace() { return editable() && (!dirty || await confirm('Replace the current diagram?', 'Unsaved changes will be replaced. Save a .fpmt file first to keep them.')); }
    function load(value, name, saved = true) {
        flow = M.validate(value); filename = M.flowFilename(name); clean = saved ? snapshot() : ''; dirty = !saved;
        undo = []; redo = []; resetSelection(); nodeStates.clear(); traversed.clear();
        viewport.scrollTo(0, 0); persist(); render(); status(`Opened ${filename}`);
    }
    async function openFile(file) {
        if (!file || !editable()) return;
        if (!M.isFlowFilename(file.name)) throw new Error('Choose a .fpmt Prompt Flow Panel file.');
        if (file.size > 5 * 1024 * 1024) throw new Error('The .fpmt file must be smaller than 5 MiB.');
        let value;
        try { value = M.validate(JSON.parse((await file.text()).replace(/^\uFEFF/, ''))); }
        catch (e) { throw new Error(`Could not open ${file.name}: ${e.message}`, { cause: e }); }
        if (await mayReplace()) load(value, file.name);
    }
    function save() {
        formDialog('Save prompt flow', ({ field, form }) => {
            field('filename', 'File name', 'text', filename).maxLength = 150;
            form.append(element('p', '', 'The .fpmt file includes the diagram and operation settings. Run output stays in this page.'));
        }, fields => {
            let name = fields.filename.value.trim();
            if (!name || /[<>:"/\\|?*]/.test(name) || Array.from(name).some(c => c.charCodeAt(0) < 32)) throw new Error('Enter a file name without path separators or reserved characters.');
            name = M.flowFilename(name);
            const validated = M.validate(flow), data = JSON.stringify(validated, null, 2), blob = new Blob([data], { type: 'application/json;charset=utf-8' });
            if (blob.size > 5 * 1024 * 1024) throw new Error('The diagram exceeds the 5 MiB file limit.');
            const url = URL.createObjectURL(blob), a = element('a'); a.href = url; a.download = name; document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 60000);
            filename = name; clean = snapshot(); dirty = false; persist(); render(); status(`Downloaded ${name}`);
        }, { acceptLabel: 'Download .fpmt' });
    }
    function settings() {
        formDialog('Flow settings', ({ field, form }) => {
            field('name', 'Flow name', 'text', flow.name).maxLength = 120;
            const steps = field('max_steps', 'Maximum executed operations per run', 'number', flow.max_steps); steps.min = 1; steps.max = 5000; steps.step = 1;
            form.append(element('p', '', 'Loops are supported. The step limit stops a flow that keeps cycling.'));
        }, fields => {
            const candidate = { ...flow, name: fields.name.value.trim() || 'Untitled', max_steps: Number(fields.max_steps.value) }; M.validate(candidate); mutate(() => { flow = candidate; });
        });
    }
    function log(title, text, error = false) {
        const item = element('article', error ? 'error' : ''); item.append(element('strong', '', title), element('pre', '', text));
        const target = $id('pmt-run-log'); target.querySelector('.pmt-log-hint')?.remove(); target.append(item);
        while (target.children.length > 150) target.firstElementChild.remove(); target.scrollTop = target.scrollHeight;
    }
    function connectionLost(message) {
        socketReady = false;
        const bar = $id('connection-status');
        bar.textContent = 'Live connection lost. Use Reconnect or refresh before continuing.';
        bar.classList.remove('connection-status-hidden', 'connection-status-ok');
        bar.classList.add('connection-status-warning');
        status(message);
        if (!editable()) {
            runState = 'failed'; $id('pmt-run-state').textContent = runState;
            if (activeNode && nodeStates.get(activeNode) === 'running') nodeStates.set(activeNode, 'failed');
            closeInput();
            status('Connection lost. Playback stopped; the server cancels the active run.');
            log('Disconnected', 'The connection was lost. Save your diagram, reconnect and explicitly start a new run.', true);
            render();
        } else updateButtons();
    }
    function send(action, data = {}) {
        try {
            if (!socketReady || socket?.readyState !== WebSocket.OPEN) throw new Error('The live connection is unavailable. Use Reconnect or refresh before continuing.');
            socket.send(JSON.stringify({ action, run_id: runId, ...data }));
        } catch (error) {
            connectionLost(error.message); socket?.close(); throw error;
        }
    }
    function connectSocket() {
        if (connecting) return connecting;
        if (socketReady && socket?.readyState === WebSocket.OPEN) return Promise.resolve();
        socketReady = false;
        connecting = new Promise((resolve, reject) => {
            const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws/prompt-flow-panel/`);
            socket = ws;
            let failed = false, heartbeat = null, pongTimer = null;
            const timer = setTimeout(() => fail(new Error('Timed out connecting to Tlamatini.')), 15000);
            function fail(error) {
                if (failed) return;
                failed = true; clearTimeout(timer); clearInterval(heartbeat); clearTimeout(pongTimer);
                if (socket === ws) { socket = null; connectionLost(error.message); }
                ws.close(); reject(error);
            }
            function ping() {
                if (pongTimer !== null) return;
                if (ws.readyState !== WebSocket.OPEN) { fail(new Error('The live connection is unavailable.')); return; }
                pongTimer = setTimeout(() => fail(new Error('Tlamatini stopped responding. Use Reconnect when the server is available.')), 15000);
                try { ws.send(JSON.stringify({ action: 'ping' })); }
                catch (error) { fail(error); }
            }
            ws.onerror = () => fail(new Error('Could not connect to Tlamatini. Check that the server is running.'));
            ws.onmessage = event => {
                if (socket !== ws || failed) return;
                try {
                    const data = JSON.parse(event.data);
                    if (data.event === 'ready') {
                        clearTimeout(timer); socketReady = true;
                        const bar = $id('connection-status'), wasDisconnected = bar.classList.contains('connection-status-warning');
                        bar.textContent = ''; bar.classList.add('connection-status-hidden'); bar.classList.remove('connection-status-warning', 'connection-status-ok');
                        if (wasDisconnected) status('Connected to Tlamatini. Press Play to start a new run.');
                        clearInterval(heartbeat); heartbeat = setInterval(ping, 8000);
                        updateButtons(); resolve();
                    } else if (data.event === 'pong') { clearTimeout(pongTimer); pongTimer = null; }
                    else receive(data);
                } catch (e) { log('Connection error', e.message, true); }
            };
            ws.onclose = () => fail(new Error('Connection closed. Sign in to Tlamatini and use Reconnect to try again.'));
        }).catch(error => { connectionLost(error.message); throw error; }).finally(() => { connecting = null; updateButtons(); });
        updateButtons();
        return connecting;
    }
    async function play() {
        if (!editable() || !socketReady) return;
        const validated = M.validate(flow, true);
        if (new Blob([JSON.stringify(validated)]).size > 5 * 1024 * 1024) throw new Error('The flow exceeds the 5 MiB playback limit.');
        runState = 'starting'; runId = null; activeNode = null; nodeStates.clear(); traversed.clear();
        render(); $id('pmt-run-state').textContent = runState; $id('pmt-run-panel').open = true; $id('pmt-run-log').replaceChildren(); status('Connecting to Tlamatini…');
        try { await connectSocket(); send('start', { flow: validated }); }
        catch (e) { runState = 'failed'; $id('pmt-run-state').textContent = runState; render(); throw e; }
    }
    function closeInput() { if (inputDialog) { internalClose = true; inputDialog.close(); inputDialog = null; internalClose = false; } }
    function receive(data) {
        if (data.event === 'pong') return;
        if (data.event === 'state' && data.status === 'running' && runState === 'starting') runId = data.run_id;
        if (runId && data.run_id !== runId) return;
        if (data.event === 'state') {
            runState = data.status; $id('pmt-run-state').textContent = runState;
            const hints = { running: 'Flow is playing', paused: 'Paused. The current model request may finish; the next operation waits.', stopping: 'Stopping. Waiting for the active request to finish cancelling…' };
            status(data.message || hints[runState] || runState);
            if (editable()) {
                closeInput();
                if (activeNode && nodeStates.get(activeNode) === 'running') nodeStates.set(activeNode, runState === 'failed' ? 'failed' : 'stopped');
                log(runState === 'failed' ? 'Flow failed' : 'Run finished', data.message || runState, runState === 'failed');
            }
            render();
        } else if (data.event === 'node') {
            activeNode = data.node_id; nodeStates.set(data.node_id, data.status); render();
            const node = flow.nodes.find(n => n.id === data.node_id);
            if (data.status === 'running') { status(`Step ${data.step}: ${node?.label || data.node_id}`); log(`Step ${data.step}`, `${node?.label || data.node_id} — ${M.operations[node?.type]?.label || ''}`); }
        } else if (data.event === 'edge') { traversed.add(data.edge_id); renderEdges(); }
        else if (data.event === 'output') log(flow.nodes.find(n => n.id === data.node_id)?.label || 'Output', data.text);
        else if (data.event === 'progress' || data.event === 'waiting') { status(data.message); log('Progress', data.message); }
        else if (data.event === 'error') {
            log('Flow error', data.message, true); status(data.message);
            if (runState === 'starting') { runState = 'failed'; $id('pmt-run-state').textContent = runState; render(); }
        } else if (data.event === 'input') showInput(data);
    }
    function showInput(data) {
        closeInput();
        const decision = data.kind === 'decision';
        inputDialog = formDialog(decision ? 'Decision · choose a branch' : 'User Commentary', ({ form, field }) => {
            form.append(element('p', '', data.message || (decision ? 'Which branch should the flow take?' : 'Enter your commentary to continue.')));
            if (!decision) field('reply', 'Your reply', 'textarea', '').maxLength = 100000;
        }, fields => send('reply', { request_id: data.request_id, value: fields.reply.value }), {
            acceptLabel: 'Continue flow',
            buttons: decision ? (_fields, close, accepted) => [
                { text: 'Yes', click() { send('reply', { request_id: data.request_id, value: 'yes' }); accepted(); close(); } },
                { text: 'No', click() { send('reply', { request_id: data.request_id, value: 'no' }); accepted(); close(); } },
                { text: 'Cancel', click: close },
            ] : undefined,
            onClose(accepted) { inputDialog = null; if (!accepted && !internalClose && !editable()) { try { send('stop'); } catch (e) { status(e.message); } } },
        });
    }
    function setZoom(value) {
        cancelConnection();
        const centerX = (viewport.scrollLeft + viewport.clientWidth / 2) / zoom, centerY = (viewport.scrollTop + viewport.clientHeight / 2) / zoom;
        zoom = UI.clampZoom(value); extent();
        viewport.scrollLeft = Math.max(0, centerX * zoom - viewport.clientWidth / 2); viewport.scrollTop = Math.max(0, centerY * zoom - viewport.clientHeight / 2); persist();
    }
    function fit() {
        cancelConnection();
        if (!flow.nodes.length) { setZoom(1); viewport.scrollTo(0, 0); return; }
        const minX = Math.min(...flow.nodes.map(n => n.x)), minY = Math.min(...flow.nodes.map(n => n.y));
        const maxX = Math.max(...flow.nodes.map(n => n.x + 200)), maxY = Math.max(...flow.nodes.map(n => n.y + 128));
        const view = UI.fitView(viewport, { left: minX, top: minY, right: maxX, bottom: maxY });
        zoom = view.zoom; extent(); viewport.scrollLeft = view.left; viewport.scrollTop = view.top; persist();
    }
    async function action(name) {
        try {
            if (name === 'new' && await mayReplace()) load(M.blank(), 'Untitled.fpmt');
            else if (name === 'open' && editable()) $id('pmt-file-input').click();
            else if (name === 'save') save();
            else if (name === 'example' && await mayReplace()) { load(M.example(), 'Prompting kickoff.fpmt', false); fit(); }
            else if (name === 'undo') restoreHistory(undo, redo);
            else if (name === 'redo') restoreHistory(redo, undo);
            else if (name === 'duplicate') duplicate();
            else if (name === 'delete') deleteSelection();
            else if (name === 'configure') { if (selectedEdge) configureEdge(flow.edges.find(e => e.id === selectedEdge)); else if (selected.size === 1) configureNode(flow.nodes.find(n => selected.has(n.id))); }
            else if (name === 'settings' && editable()) settings();
            else if (name === 'validate') { M.validate(flow, true); await alertMessage('The flow is ready to play. Cycles stop at the configured step limit.', 'Flow validated'); }
            else if (name === 'play') await play();
            else if (name === 'reconnect') await connectSocket();
            else if (name === 'pause') send(runState === 'paused' ? 'resume' : 'pause');
            else if (name === 'stop') { send('stop'); closeInput(); }
            else if (name === 'zoom-in') setZoom(zoom + .1);
            else if (name === 'zoom-out') setZoom(zoom - .1);
            else if (name === 'fit') fit();
            else if (name === 'help') await alertMessage('Drag or click an operation to add it. Double-click a figure to edit its settings. Drag a right-side output triangle to a left-side input triangle, then release to connect, just like the Agentic Control Panel. The curve follows your pointer and the triangles highlight. Release on empty canvas or press Escape to cancel. Reconnecting an occupied output replaces that connection. Decision figures have Y and N outputs on the right. With the keyboard, activate an output, Tab to an input and activate it.\n\nCtrl+click selects multiple figures; drag empty canvas to select a group. Delete removes the selection, Ctrl+D duplicates, Ctrl+Z undoes, Ctrl+Shift+Z redoes. Use arrow keys to move selected figures.\n\nChoose Start, Validate, then Play. Each run has its own conversation and embeddings. {{last_output}} inserts the last answer or user commentary. Clean History clears that run’s conversation and last output; Flush Embeddings clears its retrieval context.\n\nPause takes effect between operations. Stop requests cancellation and waits for the active model call to drain. Closing an input dialog stops the flow. Keep this page and Tlamatini open for scheduled prompts. Files never run merely by opening them.\n\nSave downloads a versioned .fpmt diagram. The panel also keeps a local draft in this browser. Legacy system prompt.pmt text files remain separate.', 'Using the Prompt Flow Panel');
        } catch (e) { status(e.message); await alertMessage(e.message); }
    }
    document.querySelectorAll('[data-action]').forEach(button => button.addEventListener('click', event => { event.preventDefault(); action(button.dataset.action); }));
    $id('pmt-start').addEventListener('change', event => mutate(() => { flow.start = event.target.value || null; }));
    $id('pmt-file-input').addEventListener('change', async event => { try { await openFile(event.target.files[0]); } catch (e) { await alertMessage(e.message); } finally { event.target.value = ''; } });
    viewport.addEventListener('dragover', event => { if (editable()) { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; } });
    viewport.addEventListener('drop', async event => {
        event.preventDefault(); if (!editable()) return;
        try {
            if (event.dataTransfer.files.length) await openFile(event.dataTransfer.files[0]);
            else { const point = position(event); addNode(event.dataTransfer.getData('application/x-tlamatini-operation'), { x: point.x - 100, y: point.y - 64 }); }
        } catch (e) { await alertMessage(e.message); }
    });
    viewport.addEventListener('pointerdown', event => {
        if (event.button !== 0 || event.target.closest('.pmt-node, .pmt-edge, button')) return;
        const p = position(event);
        if (!event.ctrlKey && !event.metaKey) resetSelection();
        endGesture(); gesture = { kind: 'select', from: p, initial: new Set(selected), initialEdges: new Set(selectedEdges) }; render(); event.preventDefault(); viewport.focus({ preventScroll: true });
    });
    document.addEventListener('pointermove', event => {
        if (!gesture) return;
        const p = position(event);
        {
            const left = Math.min(p.x, gesture.from.x), top = Math.min(p.y, gesture.from.y), width = Math.abs(p.x - gesture.from.x), height = Math.abs(p.y - gesture.from.y);
            const box = $id('pmt-marquee'); box.hidden = false; Object.assign(box.style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px` });
            selected = new Set(gesture.initial);
            selectedEdges.clear(); gesture.initialEdges.forEach(id => selectedEdges.add(id));
            if (width > 5 || height > 5) {
                const bounds = box.getBoundingClientRect();
                nodesLayer.querySelectorAll('.pmt-node').forEach(n => { if (UI.intersects(bounds, n.getBoundingClientRect())) selected.add(n.dataset.nodeId); });
                layer.querySelectorAll('.pmt-edge').forEach(edge => { if (UI.intersects(bounds, edge.querySelector('.connection-path').getBoundingClientRect())) selectedEdges.add(edge.dataset.edgeId); });
            }
            selectedEdge = selectedEdges.size === 1 ? [...selectedEdges][0] : null;
            paintSelection();
        }
    });
    function endGesture() {
        if (cancelConnection()) return;
        nodeMove.cancel();
        if (!gesture) return;
        const previous = gesture; gesture = null; $id('pmt-marquee').hidden = true; document.body.classList.remove('resizing');
        if (previous.pointerId !== undefined && viewport.hasPointerCapture(previous.pointerId)) viewport.releasePointerCapture(previous.pointerId);
        paintSelection();
    }
    document.addEventListener('pointerup', () => { if (gesture) endGesture(); });
    viewport.addEventListener('lostpointercapture', () => { if (gesture) endGesture(); });
    document.addEventListener('pointercancel', endGesture); window.addEventListener('blur', endGesture);
    UI.bindDivider({
        element: $id('drag-divider'), before: endGesture,
        value: () => $id('main-agents-container').getBoundingClientRect().width / $id('agents-container').clientWidth * 100,
        atPointer: x => (x - $id('agents-container').getBoundingClientRect().left) / $id('agents-container').clientWidth * 100,
        apply: value => { document.body.style.setProperty('--pmt-sidebar', Math.max(15, Math.min(70, value)) + '%'); extent(); }
    });
    viewport.addEventListener('wheel', event => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); setZoom(zoom + (event.deltaY < 0 ? .1 : -.1)); } }, { passive: false });
    document.addEventListener('keydown', event => {
        if (UI.isTyping(event)) return;
        const key = event.key.toLowerCase(), mod = event.ctrlKey || event.metaKey;
        if (mod && ['s', 'o', 'z', 'y', 'd', 'a'].includes(key)) {
            event.preventDefault();
            if (key === 'a') { selected = new Set(flow.nodes.map(n => n.id)); selectedEdge = null; selectedEdges.clear(); render(); }
            else action({ s: 'save', o: 'open', z: event.shiftKey ? 'redo' : 'undo', y: 'redo', d: 'duplicate' }[key]);
        } else if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); action('delete'); }
        else if (event.key === 'Escape') { endGesture(); resetSelection(); render(); status('Selection cleared'); }
        else if (event.key === 'Enter' && selected.size === 1 && !event.target.closest('button, a')) { event.preventDefault(); action('configure'); }
        else if (event.key.startsWith('Arrow') && selected.size && editable()) {
            event.preventDefault(); const amount = event.shiftKey ? 40 : 10;
            mutate(() => { for (const n of flow.nodes) if (selected.has(n.id)) { n.x = snap(n.x + (event.key === 'ArrowRight' ? amount : event.key === 'ArrowLeft' ? -amount : 0)); n.y = snap(n.y + (event.key === 'ArrowDown' ? amount : event.key === 'ArrowUp' ? -amount : 0)); } });
        }
    });
    window.addEventListener('beforeunload', event => { if (dirty || !editable()) { event.preventDefault(); event.returnValue = ''; } });
    window.addEventListener('resize', extent);
    try {
        const saved = JSON.parse(localStorage.getItem(storeKey) || 'null');
        if (saved) { flow = M.validate(saved.flow); filename = M.flowFilename(typeof saved.filename === 'string' && saved.filename.trim() ? saved.filename : 'Recovered.fpmt'); zoom = Math.min(2, Math.max(.25, Number(saved.zoom) || 1)); clean = ''; dirty = true; status('Restored your local draft. Save a .fpmt file to keep a portable copy.'); }
    } catch (e) { status(`Local draft could not be restored: ${e.message}`); }
    palette(); render();
    // Monitor idle pages too. A connection never starts or resumes a flow.
    connectSocket().catch(error => status(error.message));
})();
