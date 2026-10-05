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
    let commentEditor = null;
    let socket = null, connecting = null, runId = null, runState = 'idle', activeNode = null;
    let inputDialog = null, internalClose = false, draftTimer = null, socketReady = false;
    const nodeStates = new Map(), traversed = new Set();
    const commentarySizes = new WeakMap();
    const nodeSize = node => commentarySizes.get(node) || M.size(node);
    const playbackActive = () => ['starting', 'running', 'paused', 'stopping'].includes(runState);
    const editable = () => !commentEditor && !playbackActive();
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
            try { localStorage.setItem(storeKey, JSON.stringify({ flow: commentEditor ? JSON.parse(commentEditor.before) : flow, filename, zoom })); }
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
        const width = Math.max(1000, viewport.clientWidth / zoom, ...flow.nodes.map(n => n.x + nodeSize(n).width + 150));
        const height = Math.max(700, viewport.clientHeight / zoom, ...flow.nodes.map(n => n.y + nodeSize(n).height + 150));
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
        if (editable()) { resetSelection(); selected.add(node.id); render(); if (M.isComment(node)) editCommentary(node); else configureNode(node); }
    }
    function showNodeMenu(node, event) {
        event.preventDefault(); event.stopPropagation(); endGesture();
        if (!selected.has(node.id)) { resetSelection(); selected.add(node.id); paintSelection(); }
        const menu = $id('agent-context-menu');
        menu.replaceChildren();
        for (const [icon, label, command] of [[M.isComment(node) ? '✎' : '⚙️', M.isComment(node) ? 'Edit comment' : 'Configure', () => configureNode(node)], ['ℹ️', 'Description', () => alertMessage(M.operations[node.type].help, node.label)], ['▣', 'Duplicate', duplicate], ['⌫', 'Delete', deleteSelection]]) {
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
    viewport.addEventListener('scroll', () => { $id('agent-context-menu').style.display = 'none'; positionCommentTools(); });
    function nodeKey(event, node) {
        if (event.target.closest('.pmt-port, .pmt-comment-handle, button, textarea')) return;
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
    // Notes are edited on the canvas. Their controls never cover the text.
    let commentToolbar = null, commentToolbarKey = '';
    function commentElement(node) { return [...nodesLayer.children].find(el => el.dataset.nodeId === node.id); }
    function commentTypography(text, config) {
        Object.assign(text.style, { fontFamily: config.font_family, fontSize: `${config.font_size}px`, fontWeight: config.bold ? '700' : '400', fontStyle: config.italic ? 'italic' : 'normal', textAlign: config.align || '', color: config.text_color || '#202938', textDecoration: config.underline ? 'underline' : 'none' });
    }
    function paintCommentText(text, config, editing = false) {
        text.replaceChildren();
        M.commentRuns(config).forEach((run, index) => {
            const span = element('span', '', run.text); span.dataset.commentRun = index;
            commentTypography(span, run); text.append(span);
        });
        if (editing && (!config.text || config.text.endsWith('\n'))) text.append(document.createElement('br'));
        if (!editing && !config.text) text.textContent = 'Write a note…';
    }
    function commentSelection() {
        const editor = commentEditor, selection = window.getSelection();
        if (!editor || !selection.rangeCount) return editor?.selection;
        const range = selection.getRangeAt(0);
        if (!editor.input.contains(range.startContainer) || !editor.input.contains(range.endContainer)) return editor.selection;
        const offset = (container, end) => {
            const prefix = document.createRange(); prefix.selectNodeContents(editor.input); prefix.setEnd(container, end); return prefix.toString().length;
        };
        const next = { start: offset(range.startContainer, range.startOffset), end: offset(range.endContainer, range.endOffset) };
        if (next.start !== editor.selection.start || next.end !== editor.selection.end) editor.typingStyle = null;
        editor.selection = next;
        return next;
    }
    function restoreCommentSelection() {
        const editor = commentEditor;
        if (!editor) return;
        const point = offset => {
            const walker = document.createTreeWalker(editor.input, NodeFilter.SHOW_TEXT);
            let text, last;
            while ((text = walker.nextNode())) {
                last = text;
                if (offset <= text.length) return [text, offset];
                offset -= text.length;
            }
            return last ? [last, last.length] : [editor.input, 0];
        };
        const range = document.createRange();
        range.setStart(...point(editor.selection.start)); range.setEnd(...point(editor.selection.end));
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
    }
    function selectedCommentStyle() {
        const c = currentComment()?.config;
        if (!c) return {};
        const editor = commentEditor;
        if (editor?.typingStyle && editor.selection.start === editor.selection.end) return editor.typingStyle;
        const { start, end } = editor?.selection || { start: 0, end: c.text.length };
        const runs = M.sliceCommentRuns(M.commentRuns(c), start === end ? Math.max(0, start - 1) : start, start === end ? Math.max(1, end) : end);
        if (!runs.length) return M.commentStyle(c);
        return Object.fromEntries(M.commentStyleKeys.map(key => [key, runs.every(run => run[key] === runs[0][key]) ? runs[0][key] : null]));
    }
    function editorState() {
        return { x: commentEditor.node.x, y: commentEditor.node.y, config: M.copy(commentEditor.node.config), selection: { ...commentEditor.selection }, typingStyle: commentEditor.typingStyle && { ...commentEditor.typingStyle } };
    }
    function rememberCommentEdit() {
        const editor = commentEditor; editor.undo.push(editorState());
        if (editor.undo.length > 100) editor.undo.shift();
        editor.redo = [];
    }
    function replayCommentEdit(backwards) {
        const editor = commentEditor, source = backwards ? editor.undo : editor.redo, target = backwards ? editor.redo : editor.undo;
        if (!source.length) return;
        target.push(editorState()); const saved = source.pop();
        editor.node.config = saved.config; editor.node.x = saved.x; editor.node.y = saved.y; editor.selection = saved.selection; editor.typingStyle = saved.typingStyle;
        repaintCommentEditor();
    }
    function repaintCommentEditor() {
        const editor = commentEditor;
        paintCommentText(editor.input, editor.node.config, true);
        editor.renderedRuns = M.copy(M.commentRuns(editor.node.config));
        refreshComment(editor.node); restoreCommentSelection(); syncCommentTools();
    }
    function formatCommentText(patch) {
        const node = currentComment(); if (!node || playbackActive()) return;
        const c = node.config, editor = commentEditor;
        if (editor) commentSelection();
        const { start, end } = editor?.selection || { start: 0, end: c.text.length };
        const apply = () => {
            if (start === end && editor) {
                editor.typingStyle = { ...selectedCommentStyle(), ...patch };
                if (!c.text) Object.assign(c, patch);
            } else {
                const replacement = M.sliceCommentRuns(M.commentRuns(c), start, end).map(run => ({ ...run, ...patch }));
                const candidate = M.copy(c); M.replaceCommentRange(candidate, start, end, replacement);
                if (candidate.runs.length > 10000) { status('This comment has reached its formatting limit.'); return; }
                c.runs = candidate.runs; c.text = candidate.text;
                if (start === 0 && end === c.text.length) Object.assign(c, patch);
                if (editor) editor.typingStyle = null;
            }
        };
        if (editor) { rememberCommentEdit(); apply(); repaintCommentEditor(); editor.input.focus({ preventScroll: true }); restoreCommentSelection(); }
        else mutate(() => { apply(); if (!c.text) Object.assign(c, patch); });
    }
    function insertCommentText(text, range = commentSelection(), formatted = null) {
        const editor = commentEditor, c = editor.node.config;
        text = text.replace(/\r\n?/g, '\n');
        if (c.text.length - (range.end - range.start) + text.length > 100000) { status('A comment can contain up to 100,000 characters.'); return; }
        const style = editor.typingStyle || M.commentStyle(M.sliceCommentRuns(M.commentRuns(c), range.start, range.start + 1)[0] || c);
        const candidate = M.copy(c);
        M.replaceCommentRange(candidate, range.start, range.end, formatted || (text ? [{ text, ...style }] : []));
        if (candidate.runs.length > 10000) { status('This comment has reached its formatting limit.'); return; }
        rememberCommentEdit(); c.text = candidate.text; c.runs = candidate.runs;
        editor.selection = { start: range.start + text.length, end: range.start + text.length };
        editor.typingStyle = style;
        repaintCommentEditor();
    }
    function commentBeforeInput(event) {
        const editor = commentEditor;
        if (editor.composing || event.isComposing) return;
        commentSelection();
        const type = event.inputType;
        if (type === 'historyUndo' || type === 'historyRedo') { event.preventDefault(); replayCommentEdit(type === 'historyUndo'); return; }
        if (['formatBold', 'formatItalic', 'formatUnderline'].includes(type)) {
            event.preventDefault(); const key = type.slice(6).toLowerCase(); formatCommentText({ [key]: !selectedCommentStyle()[key] }); return;
        }
        if (['insertText', 'insertParagraph', 'insertLineBreak'].includes(type)) {
            event.preventDefault(); insertCommentText(type === 'insertParagraph' || type === 'insertLineBreak' ? '\n' : event.data || ''); return;
        }
        if (type.startsWith('delete')) {
            event.preventDefault(); let { start, end } = editor.selection;
            const targets = event.getTargetRanges?.();
            if (targets?.length) {
                const range = targets[0], prefix = document.createRange(); prefix.selectNodeContents(editor.input);
                prefix.setEnd(range.startContainer, range.startOffset); start = prefix.toString().length;
                prefix.setEnd(range.endContainer, range.endOffset); end = prefix.toString().length;
            } else if (start === end) {
                const boundaries = [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(editor.node.config.text)].map(part => part.index);
                boundaries.push(editor.node.config.text.length);
                if (type.includes('Backward')) start = boundaries.filter(index => index < start).pop() ?? 0;
                else end = boundaries.find(index => index > end) ?? end;
            }
            if (start !== end) insertCommentText('', { start, end });
        }
    }
    function readNativeCommentEdit() {
        const editor = commentEditor;
        if (!editor || editor.composing) return;
        commentSelection();
        const runs = [], walker = document.createTreeWalker(editor.input, NodeFilter.SHOW_TEXT);
        let text;
        while ((text = walker.nextNode())) {
            const index = text.parentElement.closest('[data-comment-run]')?.dataset.commentRun;
            runs.push({ text: text.data, ...M.commentStyle(editor.renderedRuns[index] || editor.node.config) });
        }
        const value = runs.map(run => run.text).join('');
        if (value.length > 100000) { repaintCommentEditor(); status('A comment can contain up to 100,000 characters.'); return; }
        rememberCommentEdit(); editor.node.config.text = value; editor.node.config.runs = M.mergeCommentRuns(runs);
        repaintCommentEditor();
    }
    document.addEventListener('selectionchange', () => {
        if (!commentEditor || commentEditor.composing) return;
        commentSelection(); syncCommentTools();
    });
    function fitCommentary(el, node, text) {
        // Measure in document coordinates, so changing zoom never changes wrapping.
        el.style.width = `${node.config.width}px`;
        commentTypography(text, node.config); text.style.textDecoration = 'none';
        text.style.height = '0px';
        const textHeight = Math.ceil(text.scrollHeight);
        const height = Math.max(node.config.height, textHeight + 82);
        text.style.height = `${height - 82}px`;
        commentarySizes.set(node, { width: node.config.width, height });
        el.style.height = `${height}px`;
        el.style.setProperty('--comment-color', node.config.color);
        const width = node.config.width, bottom = height - 18, graphic = el.querySelector('svg');
        graphic.setAttribute('viewBox', `0 0 ${width} ${height}`);
        graphic.style.setProperty('--pmt-fill', node.config.color);
        // Constant corner radius and tail: the drawing does not stretch with the text.
        graphic.querySelector('path').setAttribute('d', `M20 1H${width - 20}Q${width - 1} 1 ${width - 1} 20V${bottom - 19}Q${width - 1} ${bottom} ${width - 20} ${bottom}H72L53 ${height - 1}L35 ${bottom}H20Q1 ${bottom} 1 ${bottom - 19}V20Q1 1 20 1Z`);
    }
    function refreshComment(node) {
        const el = commentElement(node);
        if (!el) return;
        fitCommentary(el, node, el.querySelector('.pmt-comment-text'));
        el.style.left = `${node.x}px`; el.style.top = `${node.y}px`;
        extent();
    }
    function changeComment(node, patch) {
        if (playbackActive()) return;
        if (commentEditor?.node === node) {
            rememberCommentEdit(); Object.assign(node.config, patch); refreshComment(node); syncCommentTools();
        } else mutate(() => Object.assign(node.config, patch));
    }
    function fitCommentText(node) {
        changeComment(node, { height: 128 });
        status('Comment fitted to its text. Drag any edge or corner to reshape it.');
    }
    function resizeComment(drag, dx, dy) {
        const { node, direction, x, y, width, height, minimum } = drag;
        const east = direction.includes('e'), west = direction.includes('w');
        const north = direction.includes('n'), south = direction.includes('s');
        if (east || west) {
            node.config.width = Math.max(200, Math.min(2400, width + (west ? -dx : dx), west ? x + width : 2400));
            node.x = west ? x + width - node.config.width : x;
        }
        node.config.height = north || south ? Math.max(128, Math.min(2400, height + (north ? -dy : dy), north ? y + height : 2400)) : minimum;
        refreshComment(node);
        if (north) { node.y = Math.max(0, y + height - nodeSize(node).height); refreshComment(node); }
    }
    function beginCommentResize(event, node, direction) {
        event.preventDefault(); event.stopPropagation();
        if (event.button !== 0 || playbackActive() || (commentEditor && commentEditor.node !== node)) return;
        endGesture();
        if (commentEditor) rememberCommentEdit();
        selected = new Set([node.id]); selectedEdges.clear(); selectedEdge = null;
        gesture = { kind: 'resize', node, direction, before: snapshot(), x: node.x, y: node.y,
            ...nodeSize(node), minimum: node.config.height, fromX: event.clientX, fromY: event.clientY, scale: zoom, pointerId: event.pointerId };
        viewport.setPointerCapture(event.pointerId);
        document.body.style.cursor = `${direction}-resize`;
        commentElement(node).classList.add('comment-resizing'); paintSelection();
    }
    function renderCommentary(el, node) {
        const heading = element('div', 'pmt-comment-heading');
        heading.append(element('span', 'pmt-comment-kicker', node.label === 'User Commentary' ? 'Comment' : node.label));
        const edit = element('button', 'pmt-comment-edit', 'Edit');
        edit.type = 'button'; edit.title = 'Edit comment'; edit.setAttribute('aria-label', 'Edit comment'); edit.disabled = playbackActive();
        edit.addEventListener('click', event => { event.stopPropagation(); editCommentary(node); });
        edit.addEventListener('dblclick', event => event.stopPropagation()); heading.append(edit); el.append(heading);
        const text = element('div', 'pmt-comment-text'); paintCommentText(text, node.config);
        text.classList.toggle('pmt-comment-empty', !node.config.text); el.append(text); fitCommentary(el, node, text);
        const directions = { n: 'top edge', e: 'right edge', s: 'bottom edge', w: 'left edge', nw: 'top left corner', ne: 'top right corner', sw: 'bottom left corner', se: 'bottom right corner' };
        for (const [direction, label] of Object.entries(directions)) {
            const handle = element('button', `pmt-comment-handle handle-${direction}`);
            handle.type = 'button'; handle.dataset.resize = direction; handle.disabled = playbackActive();
            handle.title = `Resize comment ${label}`; handle.setAttribute('aria-label', handle.title);
            handle.addEventListener('pointerdown', event => beginCommentResize(event, node, direction));
            handle.addEventListener('dblclick', event => { event.preventDefault(); event.stopPropagation(); fitCommentText(node); });
            handle.addEventListener('keydown', event => resizeCommentKey(event, node, direction));
            el.append(handle);
        }
    }
    function resizeCommentKey(event, node, direction) {
        if (!event.key.startsWith('Arrow') || playbackActive()) return;
        event.preventDefault(); event.stopPropagation();
        const before = snapshot(), amount = event.shiftKey ? 40 : 10;
        if (commentEditor) rememberCommentEdit();
        resizeComment({ node, direction, x: node.x, y: node.y, ...nodeSize(node), minimum: node.config.height },
            event.key === 'ArrowRight' ? amount : event.key === 'ArrowLeft' ? -amount : 0,
            event.key === 'ArrowDown' ? amount : event.key === 'ArrowUp' ? -amount : 0);
        if (!commentEditor) { changed(before); commentElement(node)?.querySelector(`[data-resize="${direction}"]`)?.focus({ preventScroll: true }); }
    }
    function finishCommentary(save) {
        if (!commentEditor) return;
        if (gesture?.kind === 'resize') endGesture();
        const { node, before } = commentEditor;
        commentEditor = null;
        if (save) { changed(before); }
        else { flow = JSON.parse(before); persist(); render(); }
        commentElement(node)?.focus({ preventScroll: true });
        status(save ? 'Comment saved.' : 'Comment changes discarded.');
    }
    function editCommentary(node) {
        if (commentEditor?.node === node) { commentEditor.input.focus({ preventScroll: true }); return; }
        if (!editable()) return;
        endGesture(); resetSelection(); selected.add(node.id);
        const el = commentElement(node), display = el.querySelector('.pmt-comment-text');
        const input = element('div', 'pmt-comment-text pmt-comment-editor');
        input.contentEditable = 'true'; input.spellcheck = true; input.setAttribute('role', 'textbox'); input.setAttribute('aria-multiline', 'true');
        input.setAttribute('aria-label', 'Static User Commentary text');
        commentEditor = { node, input, before: snapshot(), selection: { start: 0, end: 0 }, typingStyle: null, undo: [], redo: [], composing: false, renderedRuns: M.copy(M.commentRuns(node.config)) };
        paintCommentText(input, node.config, true);
        display.replaceWith(input); el.classList.add('editing');
        input.addEventListener('pointerdown', event => event.stopPropagation());
        input.addEventListener('dblclick', event => event.stopPropagation());
        input.addEventListener('beforeinput', commentBeforeInput);
        input.addEventListener('input', readNativeCommentEdit);
        input.addEventListener('compositionstart', () => { commentEditor.composing = true; });
        input.addEventListener('compositionend', () => { commentEditor.composing = false; readNativeCommentEdit(); });
        const clipboardType = 'application/x-tlamatini-comment-runs+json';
        const copySelection = event => {
            const range = commentSelection();
            if (range.start === range.end) return;
            event.preventDefault();
            const runs = M.sliceCommentRuns(M.commentRuns(node.config), range.start, range.end);
            event.clipboardData.setData('text/plain', runs.map(run => run.text).join(''));
            event.clipboardData.setData(clipboardType, JSON.stringify(runs));
            if (event.type === 'cut') insertCommentText('', range);
        };
        input.addEventListener('copy', copySelection); input.addEventListener('cut', copySelection);
        input.addEventListener('paste', event => {
            event.preventDefault();
            const text = event.clipboardData.getData('text/plain');
            let runs = null;
            try {
                const encoded = event.clipboardData.getData(clipboardType);
                if (encoded && encoded.length <= 5 * 1024 * 1024) {
                    const note = M.copy(node); note.config.text = text; note.config.runs = JSON.parse(encoded);
                    runs = M.validate({ ...M.blank(), nodes: [note] }).nodes[0].config.runs;
                }
            } catch { /* Unrecognized clipboard formatting falls back to literal text. */ }
            insertCommentText(text, commentSelection(), runs);
        });
        input.addEventListener('drop', event => { event.preventDefault(); });
        input.addEventListener('keydown', event => {
            event.stopPropagation();
            if (event.isComposing) return;
            const control = event.ctrlKey || event.metaKey, key = event.key.toLowerCase();
            if (event.key === 'Escape') { event.preventDefault(); if (gesture) endGesture(); else finishCommentary(false); }
            else if (control && event.key === 'Enter') { event.preventDefault(); finishCommentary(true); }
            else if (control && ['b', 'i', 'u'].includes(key)) { event.preventDefault(); const property = { b: 'bold', i: 'italic', u: 'underline' }[key]; formatCommentText({ [property]: !selectedCommentStyle()[property] }); }
            else if (control && (key === 'z' || key === 'y')) { event.preventDefault(); replayCommentEdit(key === 'z' && !event.shiftKey); }
        });
        refreshComment(node); paintSelection(); input.focus({ preventScroll: true });
        status('Write directly in the note. Drag its borders to resize; Done saves, Escape cancels.');
    }
    function syncCommentTools() {
        const node = selected.size === 1 && !selectedEdges.size ? flow.nodes.find(n => selected.has(n.id) && M.isComment(n)) : null;
        if (!commentToolbar) {
            commentToolbar = element('div', 'pmt-comment-toolbar'); commentToolbar.id = 'pmt-comment-toolbar';
            commentToolbar.setAttribute('role', 'region'); commentToolbar.setAttribute('aria-label', 'Comment formatting');
            document.body.append(commentToolbar);
            commentToolbar.addEventListener('pointerdown', event => {
                if (!commentEditor) return;
                commentSelection();
                if (event.target.closest('button')) event.preventDefault();
            });
            commentToolbar.addEventListener('keydown', event => {
                event.stopPropagation();
                if (event.key === 'Escape' && commentEditor) { event.preventDefault(); finishCommentary(false); }
                else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter' && commentEditor) { event.preventDefault(); finishCommentary(true); }
            });
        }
        const visible = !!node && !playbackActive();
        commentToolbar.hidden = !visible;
        if (!visible) { commentToolbarKey = ''; return; }
        const key = `${node.id}:${!!commentEditor}`;
        if (commentToolbarKey !== key) {
            commentToolbarKey = key; commentToolbar.replaceChildren();
            const title = element('span', 'pmt-comment-tools-title', commentEditor ? 'Select text to format' : 'Commentary');
            commentToolbar.append(title);
            const colors = element('div', 'pmt-comment-swatches'); colors.setAttribute('role', 'group'); colors.setAttribute('aria-label', 'Comment color');
            for (const [value, name] of M.commentColors) {
                const button = element('button', 'pmt-comment-swatch'); button.type = 'button'; button.dataset.color = value;
                button.style.setProperty('--swatch', value); button.title = name; button.setAttribute('aria-label', `${name} comment`);
                button.addEventListener('click', () => changeComment(currentComment(), { color: value })); colors.append(button);
            }
            commentToolbar.append(colors);
            const typography = element('div', 'pmt-comment-tool-group');
            const font = element('select', 'pmt-comment-font'); font.setAttribute('aria-label', 'Comment font');
            for (const family of M.commentFonts) { const option = new Option(family, family); option.style.fontFamily = family; font.append(option); }
            font.prepend(new Option('Mixed fonts', '')); font.options[0].disabled = true;
            font.addEventListener('change', () => formatCommentText({ font_family: font.value }));
            const size = element('select', 'pmt-comment-size'); size.setAttribute('aria-label', 'Comment text size');
            for (const [value, label] of [[10, 'Fine'], [12, 'Small'], [16, 'Body'], [20, 'Large'], [28, 'Heading'], [36, 'Title'], [48, 'Display']]) size.append(new Option(label, value));
            size.prepend(new Option('Mixed sizes', '')); size.options[0].disabled = true;
            size.addEventListener('change', () => formatCommentText({ font_size: Number(size.value) }));
            typography.append(font, size);
            const ink = element('details', 'pmt-comment-ink');
            const inkToggle = element('summary', '', 'A'); inkToggle.title = 'Text color'; inkToggle.setAttribute('aria-label', 'Text color');
            const inkColors = element('div', 'pmt-comment-ink-colors'); inkColors.setAttribute('role', 'group'); inkColors.setAttribute('aria-label', 'Text color palette');
            for (const [value, name] of M.commentTextColors) {
                const button = element('button', 'pmt-comment-swatch'); button.type = 'button'; button.dataset.textColor = value; button.style.setProperty('--swatch', value);
                button.title = name; button.setAttribute('aria-label', `${name} text`);
                button.addEventListener('click', () => { formatCommentText({ text_color: value }); ink.open = false; }); inkColors.append(button);
            }
            ink.append(inkToggle, inkColors); typography.append(ink);
            for (const [property, label, glyph] of [['bold', 'Bold', 'B'], ['italic', 'Italic', 'I'], ['underline', 'Underline', 'U']]) {
                const button = toolButton(glyph, label, () => formatCommentText({ [property]: !selectedCommentStyle()[property] }));
                button.dataset.emphasis = property; typography.append(button);
            }
            commentToolbar.append(typography);
            const alignment = element('div', 'pmt-comment-tool-group'); alignment.setAttribute('role', 'group'); alignment.setAttribute('aria-label', 'Comment alignment');
            for (const value of ['left', 'center', 'right']) {
                const button = toolButton('', `Align ${value}`, () => changeComment(currentComment(), { align: value }));
                button.dataset.align = value;
                const icon = svg('svg', { viewBox: '0 0 20 20', 'aria-hidden': 'true' });
                const short = value === 'left' ? 3 : value === 'right' ? 8 : 5.5;
                icon.append(svg('path', { d: `M3 4H17M${short} 8h9M3 12H17M${short} 16h9`, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.7, 'stroke-linecap': 'round' }));
                button.append(icon); alignment.append(button);
            }
            commentToolbar.append(alignment, toolButton('Fit text', 'Fit bubble to text', () => fitCommentText(currentComment())));
            const actions = element('div', 'pmt-comment-actions');
            if (commentEditor) {
                actions.append(toolButton('Cancel', 'Cancel comment changes', () => finishCommentary(false)), toolButton('Done', 'Done', () => finishCommentary(true), 'primary'));
            } else actions.append(toolButton('Edit text', 'Edit comment text', () => editCommentary(currentComment()), 'primary'));
            commentToolbar.append(actions);
        }
        const c = { ...node.config, ...selectedCommentStyle() };
        for (const button of commentToolbar.querySelectorAll('[data-text-color]')) button.setAttribute('aria-pressed', String(button.dataset.textColor === (c.text_color || '#202938')));
        commentToolbar.querySelector('.pmt-comment-ink summary').style.textDecorationColor = c.text_color || '#202938';
        for (const button of commentToolbar.querySelectorAll('[data-color]')) button.setAttribute('aria-pressed', String(button.dataset.color === c.color));
        commentToolbar.querySelector('.pmt-comment-font').value = c.font_family || '';
        const size = commentToolbar.querySelector('.pmt-comment-size');
        size.querySelector('[data-saved-size]')?.remove();
        if (c.font_size !== null && ![...size.options].some(option => Number(option.value) === c.font_size)) {
            const option = new Option('Saved size', c.font_size); option.dataset.savedSize = ''; size.append(option);
        }
        size.value = c.font_size ?? '';
        for (const button of commentToolbar.querySelectorAll('[data-emphasis]')) button.setAttribute('aria-pressed', c[button.dataset.emphasis] === null ? 'mixed' : String(c[button.dataset.emphasis]));
        for (const button of commentToolbar.querySelectorAll('[data-align]')) button.setAttribute('aria-pressed', String(button.dataset.align === c.align));
        positionCommentTools();
    }
    function positionCommentTools() {
        if (!commentToolbar || commentToolbar.hidden) return;
        const node = currentComment(), el = node && commentElement(node);
        if (!el) return;
        const box = el.getBoundingClientRect(), view = viewport.getBoundingClientRect();
        const margin = 12, width = Math.min(420, view.width - margin * 2);
        commentToolbar.style.width = Math.max(260, width) + 'px';
        const height = commentToolbar.offsetHeight;
        const lowX = Math.max(margin, view.left + margin), highX = Math.min(window.innerWidth - margin, view.right - margin) - commentToolbar.offsetWidth;
        const lowY = Math.max(margin, view.top + margin), highY = Math.min(window.innerHeight - margin, view.bottom - margin) - height;
        let left = box.left, top = box.top - height - margin;
        if (top < lowY) {
            if (box.right + margin <= highX) { left = box.right + margin; top = box.top; }
            else if (box.left - margin - commentToolbar.offsetWidth >= lowX) { left = box.left - margin - commentToolbar.offsetWidth; top = box.top; }
            else top = box.bottom + margin;
        }
        commentToolbar.style.left = Math.max(lowX, Math.min(highX, left)) + 'px';
        commentToolbar.style.top = Math.max(lowY, Math.min(highY, top)) + 'px';
    }
    function currentComment() { return flow.nodes.find(n => selected.has(n.id) && M.isComment(n)); }
    function toolButton(text, label, action, extra = '') {
        const button = element('button', `pmt-comment-tool ${extra}`, text); button.type = 'button';
        button.title = label; button.setAttribute('aria-label', label); button.addEventListener('click', action); return button;
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
            nodesLayer.append(el);
            if (M.isComment(node)) renderCommentary(el, node);
            else {
                const label = element('div', 'pmt-node-label'); label.append(element('strong', '', node.label));
                if (node.label !== info.label && !['decision', 'feed_embeddings', 'flush_embeddings'].includes(node.type)) label.append(element('small', '', info.label));
                el.append(label);
            }
            if (flow.start === node.id) el.append(element('span', 'pmt-start-badge', 'START'));
            if (state) el.append(element('span', 'pmt-node-status', state));
            if (!M.isComment(node)) {
                addPort(el, node, 'input', info.input);
                if (node.type === 'decision') { addPort(el, node, 'yes', info.yes); addPort(el, node, 'no', info.no); }
                else addPort(el, node, 'next', info.output);
            }
            el.addEventListener('pointerdown', event => nodeDown(event, node));
            el.addEventListener('dblclick', event => configureSelectedNode(node, event));
            el.addEventListener('contextmenu', event => showNodeMenu(node, event));
            el.addEventListener('keydown', event => nodeKey(event, node));
        }
        renderEdges(); extent();
        $id('pmt-empty').hidden = flow.nodes.length > 0;
        $id('filename').textContent = `${filename}${dirty ? ' •' : ''}`;
        document.title = `${dirty ? '• ' : ''}${flow.name} — Prompt Flow Panel`;
        const operations = flow.nodes.filter(n => !M.isComment(n));
        const counted = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
        $id('pmt-count').textContent = `${counted(operations.length, 'operation')} · ${counted(flow.nodes.length - operations.length, 'comment')} · ${counted(flow.edges.length, 'connection')}`;
        const select = $id('pmt-start'); select.replaceChildren();
        if (!operations.length) select.append(new Option('Add an operation', ''));
        for (const n of operations) select.append(new Option(n.label, n.id));
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
            if (action === 'configure') {
                button.disabled = !editable() || selected.size + selectedEdges.size !== 1;
                button.textContent = currentComment() && selected.size === 1 && !selectedEdges.size ? '✎ Edit comment' : '⚙ Configure';
            }
            if (action === 'duplicate') button.disabled = !editable() || !selected.size;
            if (action === 'delete') button.disabled = !editable() || !(selected.size || selectedEdges.size);
            if (action === 'play') button.disabled = !socketReady || !editable() || !flow.nodes.some(n => !M.isComment(n));
            if (action === 'save') button.disabled = !!commentEditor;
            if (action === 'reconnect') button.disabled = !!connecting || socketReady;
            if (action === 'pause') { button.disabled = !['running', 'paused'].includes(runState); button.textContent = runState === 'paused' ? '▶ Resume' : 'Ⅱ Pause'; }
            if (action === 'stop') button.disabled = !['running', 'paused'].includes(runState);
        }
        for (const button of document.querySelectorAll('.agent-tool-item')) { button.disabled = !editable(); button.draggable = editable(); }
        syncCommentTools();
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
            flow.nodes.push(n); if (!M.isComment(n)) flow.start ||= n.id; selected = new Set([n.id]); selectedEdge = null; selectedEdges.clear();
        });
        status(type === 'user_commentary' ? 'Comment added. Double-click to write; drag any edge or corner to resize.' : 'Operation added. Double-click it to configure.');
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
        if (commentEditor) return;
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
            if (selected.has(flow.start)) flow.start = flow.nodes.find(n => !M.isComment(n))?.id || null;
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
        if (M.isComment(node)) { editCommentary(node); return; }
        if (!editable()) return;
        const draft = M.copy(node), config = draft.config, kind = draft.type;
        formDialog(`Configure · ${M.operations[kind].label}`, ({ form, field, fields }) => {
            form.append(element('p', '', M.operations[kind].help));
            field('label', 'Label', 'text', draft.label).maxLength = 120;
            if (!['flush_embeddings', 'clean_history'].includes(kind)) {
                const title = kind === 'decision' ? 'Question (when asking the user)' : kind === 'user_input' ? 'Message to the user' : kind === 'feed_embeddings' ? 'Text to embed' : 'Prompt';
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
            field('target', 'Destination', 'select', edge.target, flow.nodes.filter(n => !M.isComment(n)).map(n => [n.id, n.label]));
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
        if (playbackActive()) {
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
        inputDialog = formDialog(decision ? 'Decision · choose a branch' : 'User Input', ({ form, field }) => {
            form.append(element('p', '', data.message || (decision ? 'Which branch should the flow take?' : 'Enter your reply to continue.')));
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
        const maxX = Math.max(...flow.nodes.map(n => n.x + nodeSize(n).width)), maxY = Math.max(...flow.nodes.map(n => n.y + nodeSize(n).height));
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
            else if (name === 'help') await alertMessage('Drag or click an operation to add it. Double-click a figure to edit its settings. Drag a right-side output triangle to a left-side input triangle, then release to connect, just like the Agentic Control Panel. The curve follows your pointer and the triangles highlight. Release on empty canvas or press Escape to cancel. Reconnecting an occupied output replaces that connection. Decision figures have Y and N outputs on the right. With the keyboard, activate an output, Tab to an input and activate it.\n\nCtrl+click selects multiple figures; drag empty canvas to select a group. Delete removes the selection, Ctrl+D duplicates, Ctrl+Z undoes, Ctrl+Shift+Z redoes. Use arrow keys to move selected figures.\n\nUser Commentary is a static speech-bubble note. Double-click to write in it; Done or Ctrl+Enter saves, Escape cancels. Select a passage to mix fonts, sizes, text colors, bold, italic and underline using the floating mini toolbar. With a caret, formatting styles newly typed text. Bubble color and alignment apply to the note. Drag any edge or corner to resize; Fit text removes spare vertical space. There is no commentary configuration dialog. The bubble grows to fit the text without scrollbars. Notes are saved with the diagram and never run. User Input uses the notched figure and asks for a runtime reply.\n\nChoose Start, Validate, then Play. Each run has its own conversation and embeddings. {{last_output}} inserts the last answer or user input. Clean History clears that run’s conversation and last output; Flush Embeddings clears its retrieval context.\n\nPause takes effect between operations. Stop requests cancellation and waits for the active model call to drain. Closing an input dialog stops the flow. Keep this page and Tlamatini open for scheduled prompts. Files never run merely by opening them.\n\nSave downloads a versioned .fpmt diagram. The panel also keeps a local draft in this browser. Legacy system prompt.pmt text files remain separate.', 'Using the Prompt Flow Panel');
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
        if (commentEditor || event.button !== 0 || event.target.closest('.pmt-node, .pmt-edge, button')) return;
        const p = position(event);
        if (!event.ctrlKey && !event.metaKey) resetSelection();
        endGesture(); gesture = { kind: 'select', from: p, initial: new Set(selected), initialEdges: new Set(selectedEdges) }; render(); event.preventDefault(); viewport.focus({ preventScroll: true });
    });
    document.addEventListener('pointermove', event => {
        if (!gesture) return;
        if (gesture.kind === 'resize') {
            resizeComment(gesture, (event.clientX - gesture.fromX) / gesture.scale, (event.clientY - gesture.fromY) / gesture.scale);
            return;
        }
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
        if (previous.kind === 'resize') {
            document.body.style.cursor = ''; commentElement(previous.node)?.classList.remove('comment-resizing');
            if (commentEditor) { Object.assign(previous.node, JSON.parse(previous.before).nodes.find(n => n.id === previous.node.id)); refreshComment(previous.node); }
            else { flow = JSON.parse(previous.before); render(); }
        }
        if (previous.pointerId !== undefined && viewport.hasPointerCapture(previous.pointerId)) viewport.releasePointerCapture(previous.pointerId);
        paintSelection();
    }
    document.addEventListener('pointerup', () => {
        if (gesture?.kind === 'resize') {
            const previous = gesture; gesture = null; document.body.style.cursor = '';
            commentElement(previous.node)?.classList.remove('comment-resizing');
            if (viewport.hasPointerCapture(previous.pointerId)) viewport.releasePointerCapture(previous.pointerId);
            if (!commentEditor) changed(previous.before); else syncCommentTools();
        }
        else if (gesture) endGesture();
    });
    viewport.addEventListener('lostpointercapture', () => { if (gesture) endGesture(); });
    document.addEventListener('pointercancel', endGesture); window.addEventListener('blur', endGesture);
    UI.bindDivider({
        element: $id('drag-divider'), before: endGesture,
        value: () => $id('main-agents-container').getBoundingClientRect().width / $id('agents-container').clientWidth * 100,
        atPointer: x => (x - $id('agents-container').getBoundingClientRect().left) / $id('agents-container').clientWidth * 100,
        apply: value => { document.body.style.setProperty('--pmt-sidebar', Math.max(15, Math.min(70, value)) + '%'); extent(); }
    });
    // Layout is a per-user browser preference, never a flow edit or a zoom operation.
    const workspace = $id('pmt-workspace'), outputPanel = $id('pmt-run-panel'), outputDivider = $id('pmt-output-divider');
    const layoutKey = `tlamatini.prompting-flow.layout.v1.${document.body.dataset.userId}`;
    let outputPercent = 20, layoutTimer = null;
    try {
        const saved = JSON.parse(localStorage.getItem(layoutKey) || 'null');
        if (typeof saved?.outputPercent === 'number' && Number.isFinite(saved.outputPercent)) outputPercent = Math.max(5, Math.min(95, saved.outputPercent));
    } catch (_) { /* A blocked or invalid preference must not prevent editing. */ }
    function paneHeight() {
        return Math.max(0, workspace.clientHeight - workspace.querySelector('.pmt-status-strip').offsetHeight - outputDivider.offsetHeight);
    }
    function sizeOutput() {
        outputDivider.hidden = !outputPanel.open;
        const height = paneHeight() * outputPercent / 100;
        outputPanel.style.height = outputPanel.open ? `${height}px` : '';
        // Native details has an anonymous content wrapper: percentage log heights
        // resolve against that wrapper rather than the pane in some browsers.
        $id('pmt-run-log').style.height = outputPanel.open ? `${Math.max(0, height - outputPanel.querySelector('summary').offsetHeight)}px` : '';
        outputDivider.setAttribute('aria-valuenow', String(Math.round(outputPercent)));
        outputDivider.setAttribute('aria-valuetext', `${Math.round(outputPercent)}% Run output`);
        extent();
    }
    function setOutputPercent(value) {
        outputPercent = Math.max(5, Math.min(95, value));
        sizeOutput();
        clearTimeout(layoutTimer);
        layoutTimer = setTimeout(() => {
            try { localStorage.setItem(layoutKey, JSON.stringify({ outputPercent })); }
            catch (_) { /* Resizing remains available without browser storage. */ }
        }, 150);
    }
    UI.bindDivider({
        element: outputDivider, axis: 'y', keyDirection: -1, before: endGesture,
        value: () => outputPercent,
        atPointer: y => (workspace.getBoundingClientRect().bottom - y - outputDivider.offsetHeight / 2) / Math.max(1, paneHeight()) * 100,
        apply: setOutputPercent
    });
    outputDivider.addEventListener('keydown', event => {
        if (!['Home', 'End'].includes(event.key)) return;
        event.preventDefault(); endGesture(); setOutputPercent(event.key === 'Home' ? 5 : 95);
    });
    outputPanel.addEventListener('toggle', sizeOutput);
    const paneObserver = new ResizeObserver(sizeOutput);
    paneObserver.observe(workspace);
    paneObserver.observe(workspace.querySelector('.pmt-status-strip'));
    sizeOutput();
    viewport.addEventListener('wheel', event => { if (event.ctrlKey || event.metaKey) { event.preventDefault(); setZoom(zoom + (event.deltaY < 0 ? .1 : -.1)); } }, { passive: false });
    document.addEventListener('keydown', event => {
        if (commentEditor) {
            if (event.key === 'Escape') { event.preventDefault(); if (gesture) endGesture(); else finishCommentary(false); }
            else if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') { event.preventDefault(); finishCommentary(true); }
            return;
        }
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
    async function openIncomingFile() {
        const incoming = $id('server-fpmt-data'), error = $id('flow-open-error');
        if (!incoming && !error) return;
        const address = new URL(window.location.href);
        address.searchParams.delete('open');
        history.replaceState(null, '', address);
        if (error) { await alertMessage(JSON.parse(error.textContent), 'Could not open flow'); return; }
        try {
            const value = M.validate(JSON.parse(incoming.textContent));
            if (await mayReplace()) load(value, JSON.parse($id('server-fpmt-filename').textContent));
            else status('Opening cancelled. Your current diagram was kept.');
        } catch (error) { await alertMessage(error.message, 'Could not open flow'); }
    }
    openIncomingFile();
    document.fonts.ready.then(() => {
        if (commentEditor) { fitCommentary(commentEditor.input.closest('.pmt-node'), commentEditor.node, commentEditor.input); extent(); }
        else if (!gesture) render();
    });
    // Monitor idle pages too. A connection never starts or resumes a flow.
    connectSocket().catch(error => status(error.message));
})();
