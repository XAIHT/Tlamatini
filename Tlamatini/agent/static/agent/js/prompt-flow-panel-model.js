/* Tlamatini — "one who knows"
 * Created by Angela López Mendoza · @angelahack1
 * Tlamatini Author Banner — do not remove */
(() => {
    'use strict';
    // The JSON contract stays stable when a flow file is renamed to .fpmt.
    const FORMAT = 'tlamatini-prompting-flow';
    const EXTENSION = '.fpmt';
    const VERSION = 2;
    const commentColors = [['#fbcfe8', 'Pink'], ['#fef3c7', 'Yellow'], ['#dcfce7', 'Green'], ['#dbeafe', 'Blue'], ['#ede9fe', 'Purple'], ['#ffedd5', 'Orange'], ['#ffffff', 'White'], ['#e5e7eb', 'Grey']];
    const commentTextColors = [['#202938', 'Ink'], ['#000000', 'Black'], ['#1d4ed8', 'Blue'], ['#166534', 'Green'], ['#7e22ce', 'Purple'], ['#b91c1c', 'Red'], ['#92400e', 'Brown'], ['#ffffff', 'White']];
    const commentFonts = ['Nunito', 'Arial', 'Verdana', 'Georgia', 'Times New Roman', 'Courier New'];
    const isFlowFilename = name => /\.fpmt$/i.test(name);
    // Migrate old flow draft/save names without changing system prompt files.
    const flowFilename = name => isFlowFilename(name) ? name : name.replace(/\.pmt$/i, '') + EXTENSION;
    const operations = {
        // Side ports sit on each outline; Decision uses ACP's 33%/66% dual outputs.
        prompt: { label: 'Prompt', color: '#83c0f3', fill: '#304965', path: 'M4 20H196V108H4Z', input: [4, 64], output: [196, 64], help: 'Send a prompt to the configured Tlamatini model.' },
        programmed_prompt: { label: 'Programmed Prompt', color: '#d7b9f5', fill: '#4d3867', path: 'M4 20H196V108H4Z', input: [4, 64], output: [196, 64], help: 'Wait for a delay or scheduled time, then send a prompt.' },
        decision: { label: 'Decision', color: '#f0cf72', fill: '#61512e', path: 'M100 4L196 64L100 124L4 64Z', input: [4, 64], yes: [161.184, 42.24], no: [163.232, 84.48], help: 'Route through Yes or No using the last output, or ask the user.' },
        feed_embeddings: { label: 'Feed embeddings', color: '#77d8b2', fill: '#285849', path: 'M100 4L196 120H4Z', input: [100 - 96 * 60 / 116, 64], output: [100 + 96 * 60 / 116, 64], help: 'Add text to this run’s retrieval context.' },
        flush_embeddings: { label: 'Flush embeddings', color: '#f0a88b', fill: '#684237', path: 'M4 8H196L100 124Z', input: [4 + 96 * 56 / 116, 64], output: [196 - 96 * 56 / 116, 64], help: 'Remove this run’s embeddings while retaining its conversation.' },
        clean_history: { label: 'Clean History', color: '#90cddc', fill: '#315665', path: 'M4 14H196L160 114H40Z', input: [22, 64], output: [178, 64], help: 'Clear this run’s conversation and last output; keep its embeddings.' },
        user_input: { label: 'User Input', color: '#eaaed6', fill: '#653d59', path: 'M52 4L100 38L148 4V88L100 124L52 88Z', input: [52, 64], output: [148, 64], help: 'Pause for a user reply and add it to the conversation.' },
        user_commentary: { label: 'User Commentary', color: '#eaaed6', fill: '#653d59', path: 'M28 10H172Q196 10 196 34V82Q196 106 172 106H70L48 124L33 106H28Q4 106 4 82V34Q4 10 28 10Z', static: true, help: 'A static review note. Double-click to write. Use the floating toolbar to format; drag any edge or corner to resize. It never runs.' },
    };
    const copy = value => JSON.parse(JSON.stringify(value));
    function uniqueLabel(label, used) {
        const base = label.replace(/ \(\d+\)$/, '');
        let index = 2, candidate;
        do {
            const suffix = ` (${index++})`;
            candidate = base.slice(0, 120 - suffix.length) + suffix;
        } while (used.has(candidate));
        return candidate;
    }
    const id = () => 'pmt_' + (globalThis.crypto?.randomUUID?.() || Date.now().toString(36) + Math.random().toString(36).slice(2));
    const blank = () => ({ format: FORMAT, version: VERSION, name: 'Untitled', start: null, max_steps: 500, nodes: [], edges: [] });
    const isComment = n => n.type === 'user_commentary';
    const size = n => isComment(n) ? { width: n.config.width, height: n.config.height } : { width: 200, height: 128 };
    function node(type, x, y) {
        const config = { text: '' };
        if (type === 'prompt' || type === 'programmed_prompt') Object.assign(config, { multi_turn: false, acpx: false });
        if (type === 'programmed_prompt') Object.assign(config, { delay_seconds: 5, scheduled_at: '' });
        if (type === 'decision') Object.assign(config, { comparison: 'contains', value: '', case_sensitive: false });
        if (type === 'user_commentary') Object.assign(config, { width: 360, height: 160, color: '#fef3c7', text_color: '#202938', font_family: 'Nunito', font_size: 16, bold: false, italic: false, underline: false, align: 'left', runs: [] });
        return { id: id(), type, label: operations[type].label, x, y, config };
    }
    const commentStyleKeys = ['font_family', 'font_size', 'text_color', 'bold', 'italic', 'underline'];
    const commentStyle = c => Object.fromEntries(commentStyleKeys.map(key => [key, key === 'underline' ? !!c[key] : c[key]]));
    function mergeCommentRuns(runs) {
        const merged = [];
        for (const run of runs) {
            if (!run.text) continue;
            const last = merged[merged.length - 1];
            if (last && commentStyleKeys.every(key => last[key] === run[key])) last.text += run.text;
            else merged.push({ text: run.text, ...commentStyle(run) });
        }
        return merged;
    }
    function sliceCommentRuns(runs, start, end) {
        let offset = 0;
        return runs.flatMap(run => {
            const from = Math.max(0, start - offset), to = Math.min(run.text.length, end - offset);
            offset += run.text.length;
            return to > from ? [{ ...run, text: run.text.slice(from, to) }] : [];
        });
    }
    const commentRuns = c => c.runs || (c.text ? [{ text: c.text, ...commentStyle(c) }] : []);
    function replaceCommentRange(c, start, end, replacement) {
        const runs = commentRuns(c);
        c.runs = mergeCommentRuns([...sliceCommentRuns(runs, 0, start), ...replacement, ...sliceCommentRuns(runs, end, c.text.length)]);
        c.text = c.runs.map(run => run.text).join('');
    }
    function validate(value, playable = false) {
        const fail = message => { throw new Error(message); };
        if (!value || value.format !== FORMAT) fail('This is not a Prompt Flow Panel document. Legacy prompt.pmt text is not a diagram.');
        if (![1, VERSION].includes(value.version)) fail('Unsupported .fpmt version. This panel supports versions 1 and 2.');
        const legacy = value.version === 1;
        const flow = copy(value);
        const text = (s, max, label) => { if (typeof s !== 'string' || s.length > max) fail(`${label} must be text of at most ${max.toLocaleString()} characters.`); return s; };
        const number = (n, min, max, label) => { if (typeof n !== 'number' || !Number.isFinite(n) || n < min || n > max) fail(`${label} must be between ${min} and ${max}.`); return n; };
        text(flow.name, 120, 'Flow name');
        number(flow.max_steps, 1, 5000, 'Step limit');
        if (!Number.isInteger(flow.max_steps)) fail('The step limit must be a whole number.');
        if (!Array.isArray(flow.nodes) || flow.nodes.length > 500 || !Array.isArray(flow.edges) || flow.edges.length > 1000) fail('Use up to 500 operations and 1,000 connections.');
        const known = new Map(), slots = new Set(), edgeIds = new Set();
        for (const n of flow.nodes) {
            if (!n || typeof n.id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(n.id) || known.has(n.id)) fail('Operation IDs must be unique letters, digits, underscores or dashes.');
            if (legacy && n.type === 'user_commentary') { n.type = 'user_input'; if (n.label === 'User Commentary') n.label = 'User Input'; }
            if (!Object.hasOwn(operations, n.type)) fail('Unknown operation type.');
            text(n.label, 120, 'Label'); number(n.x, 0, 100000, 'X'); number(n.y, 0, 100000, 'Y');
            if (!n.config || typeof n.config !== 'object' || Array.isArray(n.config)) fail('Missing operation settings.');
            text(n.config.text, 100000, 'Operation text');
            if (isComment(n)) {
                const c = n.config;
                for (const [key, fallback, min, max] of [['width', 320, 200, 2400], ['height', 200, 128, 2400], ['font_size', 16, 10, 48]]) { if (c[key] === undefined) c[key] = fallback; number(c[key], min, max, `Comment ${key}`); }
                for (const [key, fallback] of [['color', '#fbcfe8'], ['text_color', '#202938'], ['font_family', 'Nunito'], ['align', 'left'], ['bold', false], ['italic', false], ['underline', false]]) if (c[key] === undefined) c[key] = fallback;
                if (!commentColors.some(([color]) => color === c.color) || !commentTextColors.some(([color]) => color === c.text_color) || !commentFonts.includes(c.font_family) || !['left', 'center', 'right'].includes(c.align)) fail('Choose a supported comment color, font and alignment.');
                if (typeof c.bold !== 'boolean' || typeof c.italic !== 'boolean' || typeof c.underline !== 'boolean') fail('Comment style switches must be true or false.');
                if (c.runs === undefined) c.runs = c.text ? [{ text: c.text, ...commentStyle(c) }] : [];
                if (!Array.isArray(c.runs) || c.runs.length > 10000) fail('Use at most 10,000 formatted text runs per comment.');
                c.runs = c.runs.map(run => {
                    if (!run || typeof run !== 'object' || Array.isArray(run)) fail('A formatted text run must be an object.');
                    text(run.text, 100000, 'Comment run text');
                    const style = { ...commentStyle(c), ...run };
                    number(style.font_size, 10, 48, 'Comment run font size');
                    if (!commentFonts.includes(style.font_family) || !commentTextColors.some(([color]) => color === style.text_color)) fail('Choose a supported comment font and text color.');
                    if (['bold', 'italic', 'underline'].some(key => typeof style[key] !== 'boolean')) fail('Comment run style switches must be true or false.');
                    return { text: run.text, ...commentStyle(style) };
                });
                if (c.runs.map(run => run.text).join('') !== c.text) fail('Comment runs must contain exactly the comment text.');
                c.runs = mergeCommentRuns(c.runs);
                n.config = Object.fromEntries(['text', 'runs', 'width', 'height', 'color', 'text_color', 'font_family', 'font_size', 'bold', 'italic', 'underline', 'align'].map(key => [key, c[key]]));
            }
            if (['prompt', 'programmed_prompt'].includes(n.type)) {
                if (typeof n.config.multi_turn !== 'boolean' || typeof n.config.acpx !== 'boolean') fail('Prompt switches must be true or false.');
                if (n.config.acpx && !n.config.multi_turn) fail('ACPX requires Multi-Turn.');
            }
            if (playable && ['prompt', 'programmed_prompt', 'feed_embeddings'].includes(n.type) && !n.config.text.trim()) fail(`${n.label} needs text. Double-click to configure it.`);
            if (n.type === 'programmed_prompt') {
                number(n.config.delay_seconds, 0, 86400, 'Delay');
                text(n.config.scheduled_at, 60, 'Scheduled time');
                if (n.config.scheduled_at && (!Number.isFinite(Date.parse(n.config.scheduled_at)) || !/(Z|[+-]\d{2}:\d{2})$/.test(n.config.scheduled_at))) fail('Scheduled time needs a valid date and timezone.');
            }
            if (n.type === 'decision') {
                if (!['contains', 'not_contains', 'equals', 'is_empty', 'user'].includes(n.config.comparison)) fail('Unknown decision comparison.');
                text(n.config.value, 10000, 'Comparison value');
                if (typeof n.config.case_sensitive !== 'boolean') fail('Case sensitivity must be true or false.');
                if (playable && ['contains', 'not_contains', 'equals'].includes(n.config.comparison) && !n.config.value) fail(`${n.label} needs a comparison value.`);
            }
            known.set(n.id, n);
        }
        for (const e of flow.edges) {
            if (!e || typeof e.id !== 'string' || !/^[A-Za-z0-9_-]{1,80}$/.test(e.id) || edgeIds.has(e.id)) fail('Invalid or duplicate connection ID.');
            edgeIds.add(e.id);
            if (!known.has(e.source) || !known.has(e.target)) fail('A connection points to a missing operation.');
            if (isComment(known.get(e.source)) || isComment(known.get(e.target))) fail('Static User Commentary assets cannot have connections.');
            const allowed = known.get(e.source).type === 'decision' ? ['yes', 'no'] : ['next'];
            const slot = `${e.source}:${e.branch}`;
            if (!allowed.includes(e.branch) || slots.has(slot)) fail('Each output supports one connection; decisions use Yes and No.');
            slots.add(slot);
        }
        if (flow.start !== null && !known.has(flow.start)) fail('The Start operation is missing.');
        if (flow.start !== null && isComment(known.get(flow.start))) fail('A static User Commentary cannot be the Start operation.');
        if (playable) {
            if (!known.size || !flow.start) fail('Add an operation and choose Start.');
            const reached = new Set(), pending = [flow.start];
            while (pending.length) {
                const current = pending.pop();
                if (reached.has(current)) continue;
                reached.add(current);
                pending.push(...flow.edges.filter(e => e.source === current).map(e => e.target));
            }
            if (reached.size !== flow.nodes.filter(n => !isComment(n)).length) fail('Some operations are unreachable from Start. Connect them or choose another Start.');
            for (const n of flow.nodes) if (n.type === 'decision' && !['yes', 'no'].every(b => slots.has(`${n.id}:${b}`))) fail('Connect both Yes and No outputs of every decision.');
        }
        // Keep the document a data contract, discarding any unrelated fields.
        return { format: FORMAT, version: VERSION, name: flow.name, start: flow.start, max_steps: flow.max_steps, nodes: flow.nodes.map(n => ({ id: n.id, type: n.type, label: n.label, x: n.x, y: n.y, config: n.config })), edges: flow.edges.map(e => ({ id: e.id, source: e.source, target: e.target, branch: e.branch })) };
    }
    function example() {
        const flow = blank(); flow.name = 'Prompting kickoff';
        const a = node('user_input', 80, 60), b = node('decision', 80, 260), c = node('prompt', 370, 440), d = node('programmed_prompt', 40, 620);
        a.label = 'Choose a subject'; a.config.text = 'What would you like to explore? Include the word “code” to take the coding branch.';
        b.label = 'About code?'; b.config.value = 'code';
        c.label = 'Explain the code'; c.config.text = 'Explain this coding subject and give one short example: {{last_output}}';
        d.label = 'Explore the subject'; d.config.text = 'Explain this subject in three clear points: {{last_output}}'; d.config.delay_seconds = 2;
        flow.nodes = [a, b, c, d]; flow.start = a.id;
        flow.edges = [{ id: id(), source: a.id, target: b.id, branch: 'next' }, { id: id(), source: b.id, target: c.id, branch: 'yes' }, { id: id(), source: b.id, target: d.id, branch: 'no' }];
        return flow;
    }
    window.PromptFlowPanelModel = Object.freeze({ FORMAT, VERSION, EXTENSION, commentColors, commentTextColors, commentFonts, commentStyleKeys, commentStyle, commentRuns, mergeCommentRuns, sliceCommentRuns, replaceCommentRange, isComment, size, isFlowFilename, flowFilename, operations, copy, uniqueLabel, id, blank, node, validate, example });
})();
