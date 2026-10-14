// ═══════════════════════════════════════════════════════════════════════════
//   ✦  T L A M A T I N I  ✦   —   "one who knows"
//
//   Created by  Angela López Mendoza   ·   @angelahack1
//   Developer · Architect · Creator of Tlamatini
// ═══════════════════════════════════════════════════════════════════════════
//   Tlamatini Author Banner — do not remove
//
// file_drop_router_cases.mjs — behaviour tests for static/agent/js/file_drop_router.js
//
// Loads the REAL router into a stub browser (vm) and drives it: classification
// of every kind of dropped file, every MCP config shape seen in the wild, and
// the dispatch (ordering, grouping, cancel, sign-in, popup timing, relay, lock).
// Run by agent/test_file_drop_router.py; exits non-zero on the first failure.
//
// NOTE: no unicode escapes in this file on purpose - the bytes are built with
// Uint8Array / String.fromCharCode so no tool can rewrite them.

import { readFileSync } from 'node:fs';
import { File } from 'node:buffer';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const routerPath = path.join(here, '..', 'Tlamatini', 'agent', 'static', 'agent', 'js', 'file_drop_router.js');
const source = readFileSync(routerPath, 'utf8');

let checks = 0;
function ok(condition, message) { assert.ok(condition, message); checks += 1; }
// Values built inside the vm sandbox carry that realm's Array.prototype, which a strict
// deep-equal rejects even when the contents are identical - compare their JSON form.
const plain = (value) => (value === undefined ? '(undefined)' : JSON.parse(JSON.stringify(value)));
function eq(actual, expected, message) { assert.deepStrictEqual(plain(actual), plain(expected), message); checks += 1; }

const settle = async () => { for (let i = 0; i < 60; i += 1) await new Promise((resolve) => setImmediate(resolve)); };

// ── helpers that build files WITHOUT unicode escapes ───────────────────────
const ascii = (text) => Uint8Array.from(Array.from(text).map((c) => c.charCodeAt(0)));
const bytes = (...parts) => {
    const out = [];
    parts.forEach((p) => { if (typeof p === 'number') out.push(p); else out.push(...p); });
    return Uint8Array.from(out);
};
const utf16 = (text, bigEndian) => {
    const out = [];
    Array.from(text).forEach((c) => {
        const code = c.charCodeAt(0);
        if (bigEndian) out.push(code >> 8, code & 255); else out.push(code & 255, code >> 8);
    });
    return Uint8Array.from(out);
};
const makeFile = (name, content, type = '') => {
    const data = typeof content === 'string' ? ascii(content) : content;
    return new File([data], name, { type });
};

// ── a stub browser the router can run in ───────────────────────────────────
function makeEl(tag) {
    const classes = new Set();
    return {
        tagName: tag, children: [], style: {}, attrs: {}, className: '', textContent: '', id: '',
        classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
        appendChild(child) { this.children.push(child); return child; },
        setAttribute(key, value) { this.attrs[key] = value; },
        getAttribute(key) { return this.attrs[key]; }
    };
}

function jsonResponse(data, init = {}) {
    return {
        ok: init.ok !== false, status: init.status || 200, redirected: !!init.redirected,
        headers: { get: () => init.type || 'application/json' }, json: async () => data
    };
}

function boot({ auth = 'yes', fetchImpl, parent, popups = true, openDialog = false } = {}) {
    const log = { confirms: [], alerts: [], fetches: [], opens: [], dispatched: [], calls: [] };
    const ctl = { confirm: true };
    const listeners = {};
    const body = makeEl('body');
    const tab = {
        closed: false, navigated: null, opener: 'x',
        document: { title: '', body: { textContent: '', style: {} } },
        location: { replace(url) { tab.navigated = url; } },
        close() { tab.closed = true; }
    };
    const document = {
        currentScript: auth === 'none' ? { getAttribute: (k) => (k === 'data-auth' ? 'none' : null) } : null,
        readyState: 'complete', cookie: 'csrftoken=tok', body, head: makeEl('head'), documentElement: makeEl('html'),
        getElementById: () => null, querySelector: () => null, createElement: makeEl, addEventListener() {},
        dispatchEvent(event) { log.dispatched.push(event); return true; }
    };
    const win = {
        document, innerWidth: 1280, innerHeight: 720,
        addEventListener(type, fn, capture) { (listeners[type] = listeners[type] || []).push({ fn, capture }); },
        setTimeout: () => 0, clearTimeout: () => {},
        open: (...args) => { log.opens.push(args); return popups ? tab : null; },
        alert: (m) => log.alerts.push({ native: m }), confirm: () => true,
        tlmConfirm: async (primary, secondary, title, options) => {
            log.confirms.push({ primary, secondary, title, options }); log.calls.push('confirm:' + title); return ctl.confirm;
        },
        tlmAlert: async (message, title) => { log.alerts.push({ message, title }); }
    };
    win.window = win;
    win.parent = parent || win;
    if (openDialog) win.OpenExternalMcpsDialog = () => log.calls.push('dialog-opened');
    class CustomEventStub { constructor(type, init) { this.type = type; this.detail = init && init.detail; } }
    const context = vm.createContext({
        window: win, document, TextDecoder, FormData, CustomEvent: CustomEventStub, console,
        fetch: (...args) => { log.fetches.push(args); return (fetchImpl || (async () => { throw new Error('unexpected fetch'); }))(...args); }
    });
    vm.runInContext(source, context, { filename: 'file_drop_router.js' });
    const toastText = () => {
        const el = body.children.find((c) => c.id === 'tlm-file-drop-toast');
        return el ? el.textContent : '';
    };
    return { api: win.TlamatiniFileDrop, win, log, ctl, listeners, tab, toastText, body };
}

const entry = (file) => ({ file, isDirectory: false });
const MCP_JSON = '{"mcpServers":{"fs":{"command":"npx","args":["-y","fs-server"]},"web":{"url":"http://h/mcp"}}}';

// ═══ 1. the router loads, claims in the capture phase, exports what it should ═══
{
    const t = boot();
    ok(t.api && t.api.version === 1, 'router exports TlamatiniFileDrop');
    ['dragenter', 'dragover', 'dragleave', 'drop', 'dragend'].forEach((type) => {
        ok(t.listeners[type] && t.listeners[type][0].capture === true, type + ' is claimed in the CAPTURE phase');
    });
    ok(t.listeners.blur && t.listeners.blur[0].capture !== true, 'blur only hides the overlay');
    const second = boot();
    ok(second.api !== t.api, 'each document gets its own router instance');
}

// ═══ 2. quickKind: what the NAME alone decides ═══
{
    const { quickKind } = boot().api._pure;
    const table = {
        'a.flw': 'flow-agent', 'a.FPMT': 'flow-prompt', 'a.json': 'sniff', 'a.PDF': 'pdf', 'a.png': 'image',
        'a.JPG': 'image', 'a.md': 'markdown', 'a.markdown': 'markdown', 'a.py': 'text', 'a.svg': 'text',
        'a.zip': 'archive', 'a.exe': 'binary', 'a.docx': 'binary', 'Makefile': 'text', 'blob': 'sniff',
        'notes.weirdext': 'sniff', 'prompt.pmt': 'text'
    };
    Object.keys(table).forEach((name) => eq(quickKind({ name, type: '' }), table[name], name));
    eq(quickKind({ name: 'x', type: 'image/jpeg' }), 'image', 'MIME decides a nameless image');
    eq(quickKind({ name: 'x', type: 'text/plain' }), 'text', 'MIME decides nameless text');
    eq(quickKind({ name: 'x', type: 'application/pdf' }), 'pdf', 'MIME decides a nameless pdf');
}

// ═══ 3. extractServers: every MCP config shape ═══
{
    const { extractServers } = boot().api._pure;
    const names = (value, file) => extractServers(value, file || 'x.json').names;
    eq(names({ mcpServers: { fs: { command: 'npx' }, web: { url: 'http://h' } } }), ['fs', 'web'], 'Claude Desktop');
    eq(names({ servers: { a: { type: 'stdio', command: 'node', args: ['s.js'] } }, inputs: [] }), ['a'], 'VS Code mcp.json');
    eq(names({ mcp: { servers: { b: { command: 'uvx', args: ['m'] } } }, 'editor.x': 1 }), ['b'], 'VS Code settings.json');
    const opencode = extractServers({ mcp: { c: { type: 'local', command: ['npx', '-y', 'pkg'], environment: { K: 'v' } } } }, 'o.json');
    eq(opencode.names, ['c'], 'opencode map');
    eq(opencode.servers.c.command, 'npx', 'opencode command array -> command');
    eq(opencode.servers.c.args, ['-y', 'pkg'], 'opencode command array -> args');
    eq(opencode.servers.c.env, { K: 'v' }, 'opencode environment -> env');
    const zed = extractServers({ context_servers: { d: { command: { path: '/bin/x', args: ['1'], env: { A: 'b' } } } } }, 'z.json');
    eq(zed.servers.d.command, '/bin/x', 'Zed command.path');
    eq(zed.servers.d.args, ['1'], 'Zed command.args');
    eq(zed.servers.d.env, { A: 'b' }, 'Zed command.env');
    eq(names({ command: 'docker', args: ['run', '-i', 'mcp/redis'], name: 'My Redis!' }), ['My_Redis_'], 'single server, sanitised name');
    eq(names({ command: 'node' }, 'redis-server.json'), ['redis-server'], 'single server named from the file');
    eq(names({ fetch: { command: 'uvx' }, git: { command: 'uvx' } }), ['fetch', 'git'], 'bare name->server map');
    eq(names({ fetch: { command: 'uvx' }, version: 3 }), [], 'a bare map with a non-server value is NOT an MCP config');
    eq(names({ name: 'pkg', version: '1.0.0', scripts: {} }), [], 'package.json is not an MCP config');
    eq(names([{ name: 'one', command: 'a' }, { id: 'two', url: 'http://b' }, { foo: 1 }]), ['one', 'two'], 'array of servers');
    eq(names({ projects: { 'C:/p': { mcpServers: { e: { command: 'x' } } } }, mcpServers: { f: { command: 'y' } } }), ['f', 'e'], '.claude.json');
    eq(extractServers({ mcpServers: { a: { command: '1' } }, servers: { a: { command: '2' } } }, 'x').servers.a.command, '1', 'first definition wins');
    eq(names({ mcpServers: { ok: { command: 'x' }, bad: { description: 'no command or url' } } }), ['ok'], 'entries without command/url are skipped');
    eq(names({}), [], 'empty object');
    eq(names([]), [], 'empty array');
    eq(names(null), [], 'null');
    eq(names('text'), [], 'string');
}

// ═══ 4. bytes: BOMs, text-vs-binary, magic numbers ═══
{
    const { decodeBytes, looksBinary, magicKind, bomOf } = boot().api._pure;
    eq(decodeBytes(bytes(0xEF, 0xBB, 0xBF, ascii('{}'))), '{}', 'UTF-8 BOM stripped');
    eq(decodeBytes(bytes(0xFF, 0xFE, utf16('{"a":1}', false))), '{"a":1}', 'UTF-16LE (Windows PowerShell)');
    eq(decodeBytes(bytes(0xFE, 0xFF, utf16('{"a":1}', true))), '{"a":1}', 'UTF-16BE');
    eq(decodeBytes(bytes(0xFF, 0xFE, 0, 0, 1, 0, 0, 0)), null, 'UTF-32 is not decodable');
    eq(bomOf(bytes(0xFF, 0xFE, 0, 0)), 'utf-32le', 'the UTF-32-LE BOM is tested before the UTF-16-LE one');
    ok(!looksBinary(bytes(0xFF, 0xFE, utf16('hello world, this is utf sixteen text', false))), 'UTF-16 text is NOT binary (BOM before NUL)');
    ok(looksBinary(bytes(ascii('abc'), 0, ascii('def'))), 'a NUL byte makes it binary');
    ok(!looksBinary(ascii('plain ascii text, nothing odd about it at all.')), 'ascii is text');
    ok(looksBinary(Uint8Array.from(new Array(100).fill(1))), 'mostly control bytes is binary');
    ok(!looksBinary(Uint8Array.from([65, 1, 66])), 'a tiny file is never condemned by the ratio');
    eq(magicKind(ascii('%PDF-1.7 rest')), 'pdf', 'PDF');
    eq(magicKind(bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)), 'image', 'PNG');
    eq(magicKind(bytes(0xFF, 0xD8, 0xFF, 0xE0)), 'image', 'JPEG');
    eq(magicKind(ascii('GIF89a....')), 'image', 'GIF');
    eq(magicKind(bytes(ascii('RIFF'), 1, 2, 3, 4, ascii('WEBP'))), 'image', 'WEBP');
    eq(magicKind(bytes(ascii('BM'), 1, 2, 3, 4, 0, 0, 0, 0)), 'image', 'BMP');
    eq(magicKind(ascii('BMW is a car')), '', 'text that starts with BM is NOT a bitmap');
    eq(magicKind(bytes(0x50, 0x4B, 0x03, 0x04)), 'archive', 'ZIP');
    eq(magicKind(bytes(0x1F, 0x8B, 8, 0)), 'archive', 'gzip');
    eq(magicKind(ascii('just text')), '', 'plain text has no magic');
}

// ═══ 5. classify: the real, async, byte-reading decision ═══
{
    const t = boot();
    const kindOf = async (file) => t.api.classify(file);
    const mcp = await kindOf(makeFile('claude_desktop_config.json', MCP_JSON));
    eq(mcp.kind, 'mcp-json', 'an MCP .json is recognised');
    eq(mcp.names, ['fs', 'web'], 'with its server names');
    const ps = await kindOf(makeFile('mcp.json', bytes(0xFF, 0xFE, utf16(MCP_JSON, false))));
    eq(ps.kind, 'mcp-json', 'a UTF-16 MCP .json (Out-File) is recognised');
    eq((await kindOf(makeFile('package.json', '{"name":"x","version":"1.0.0"}'))).kind, 'text', 'plain JSON opens as text');
    const broken = await kindOf(makeFile('broken.json', '{"mcpServers": {'));
    eq(broken.kind, 'text', 'broken JSON falls back to text');
    ok(broken.invalidJson, 'and says why');
    eq((await kindOf(makeFile('config', MCP_JSON))).kind, 'mcp-json', 'an extensionless MCP config is recognised by content');
    eq((await kindOf(makeFile('scan', bytes(ascii('%PDF-1.4 '), 1, 2, 3)))).kind, 'pdf', 'extensionless PDF by magic');
    eq((await kindOf(makeFile('shot', bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13)))).kind, 'image', 'extensionless PNG by magic');
    eq((await kindOf(makeFile('thing', bytes(ascii('abc'), 0, 1, 2, 3)))).kind, 'binary', 'unknown binary');
    eq((await kindOf(makeFile('empty.json', ''))).kind, 'text', 'an empty file is text');
    eq((await kindOf(makeFile('notes.weirdext', 'just some words'))).kind, 'text', 'unknown extension, readable content');
    const huge = '{"a":"' + 'x'.repeat(2.2 * 1024 * 1024) + '"}';
    eq((await kindOf(makeFile('huge.json', huge))).kind, 'text', 'a JSON over 2 MiB is never parsed as a config');
}

// ═══ 6. dispatch: a lone MCP .json, on a page that registered nothing ═══
{
    const t = boot({ fetchImpl: async () => jsonResponse({ ok: true, added: ['fs', 'web'], updated: [] }) });
    await t.api.dropEntries([entry(makeFile('c.json', MCP_JSON))]);
    eq(t.log.confirms.length, 1, 'the import is confirmed first');
    ok(t.log.confirms[0].primary.indexOf('2 MCP servers') !== -1, 'the confirm counts the servers');
    ok(t.log.confirms[0].secondary.indexOf('fs, web') !== -1, 'and names them');
    ok(t.log.confirms[0].secondary.indexOf('launch programs') !== -1, 'and warns they can run programs');
    eq(t.log.fetches.length, 1, 'one import request');
    eq(t.log.fetches[0][0], '/agent/external_mcps/import/', 'to the import endpoint');
    eq(t.log.fetches[0][1].headers['X-CSRFToken'], 'tok', 'with the CSRF token');
    eq(JSON.parse(t.log.fetches[0][1].body).mcpServers.fs.command, 'npx', 'carrying the servers');
    eq(t.log.dispatched[0].type, 'tlm:external-mcps-imported', 'the External MCPs dialog is told to refresh');
    ok(t.log.alerts.some((a) => a.title === 'Import complete'), 'the result is reported');
}

// ═══ 7. cancel, failure, session expiry ═══
{
    const t = boot({ fetchImpl: async () => jsonResponse({}) });
    t.ctl.confirm = false;
    await t.api.dropEntries([entry(makeFile('c.json', MCP_JSON))]);
    eq(t.log.fetches.length, 0, 'Cancel imports nothing');
    ok(t.toastText().indexOf('Nothing was imported') !== -1, 'and says so');
}
{
    const t = boot({ fetchImpl: async () => jsonResponse({ ok: false, error: 'disk full' }, { ok: false, status: 500 }) });
    await t.api.dropEntries([entry(makeFile('c.json', MCP_JSON))]);
    ok(t.log.alerts.some((a) => a.title === 'Import failed' && a.message.indexOf('disk full') !== -1), 'a server error is shown');
}
{
    const t = boot({ fetchImpl: async () => jsonResponse('<html>', { redirected: true, type: 'text/html' }) });
    await t.api.dropEntries([entry(makeFile('c.json', MCP_JSON))]);
    ok(t.log.alerts.some((a) => a.message.indexOf('session expired') !== -1), 'an expired session is explained');
}
{
    const t = boot({ fetchImpl: async () => jsonResponse({ ok: true, added: [], updated: [] }) });
    await t.api.dropEntries([entry(makeFile('c.json', MCP_JSON))]);
    ok(t.log.alerts.some((a) => a.title === 'Nothing to import'), 'importing zero servers is not called a success');
}

// ═══ 8. after an import, the chat page offers to activate ═══
{
    const t = boot({ openDialog: true, fetchImpl: async () => jsonResponse({ ok: true, added: ['fs'], updated: [] }) });
    await t.api.dropEntries([entry(makeFile('c.json', '{"command":"npx"}'))]);
    eq(t.log.confirms.length, 2, 'a second question follows the import');
    eq(t.log.confirms[1].options.cancelLabel, 'Later', 'activation can wait');
    ok(t.log.calls.indexOf('dialog-opened') !== -1, 'confirming opens External > MCPs');
}

// ═══ 9. mixed drop: right handler, right order, grouped once ═══
{
    const t = boot({ fetchImpl: async () => jsonResponse({ ok: true, added: ['fs', 'web'], updated: [] }) });
    t.api.register('image', (files) => { t.log.calls.push('image:' + files.map((f) => f.name).join(',')); }, { label: 'Image -> attached' });
    t.api.register(['pdf', 'markdown', 'text'], (files) => { t.log.calls.push('docs:' + files.map((f) => f.name).join(',')); }, { label: 'Document -> canvas' });
    await t.api.dropEntries([
        entry(makeFile('a.py', 'print(1)')),
        entry(makeFile('p.png', bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))),
        entry(makeFile('doc.pdf', ascii('%PDF-1.4'))),
        entry(makeFile('m.json', MCP_JSON))
    ]);
    eq(t.log.calls.filter((c) => c !== 'confirm:Import complete'), ['confirm:Import MCP servers', 'image:p.png', 'docs:a.py,doc.pdf'],
        'MCP first, then the image, then ONE call for the documents in drop order');
}

// ═══ 10. plain JSON goes to the text handler; broken JSON says so ═══
{
    const t = boot();
    const seen = [];
    t.api.register(['pdf', 'markdown', 'text'], (files) => { seen.push(...files.map((f) => f.name)); }, { label: 'Document -> canvas' });
    await t.api.dropEntries([entry(makeFile('package.json', '{"name":"x"}')), entry(makeFile('bad.json', '{"mcpServers": {'))]);
    eq(seen, ['package.json', 'bad.json'], 'JSON that is not an MCP config opens as a document');
    ok(t.toastText().indexOf('bad.json is not valid JSON') !== -1, 'and broken JSON is reported');
}

// ═══ 11. what a page cannot use is explained, never garbage ═══
{
    const t = boot();
    await t.api.dropEntries([entry(makeFile('p.png', bytes(0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))), entry(makeFile('a.zip', bytes(0x50, 0x4B, 0x03, 0x04)))]);
    const text = t.toastText();
    ok(text.indexOf('Skipped') !== -1, 'skipped files are announced');
    ok(text.indexOf('p.png (image)') !== -1 && text.indexOf('a.zip (archive)') !== -1, 'with their kind');
    ok(text.indexOf('chat page') !== -1, 'and where images can go');
    ok(text.indexOf('This page accepts') !== -1, 'and what this page does accept');
}
{
    const t = boot();
    await t.api.dropEntries([{ file: { name: 'project' }, isDirectory: true }]);
    ok(t.toastText().indexOf('Folders cannot be dropped') !== -1, 'a folder is explained');
}

// ═══ 12. the login page: never navigate, never import ═══
{
    const t = boot({ auth: 'none', fetchImpl: async () => { throw new Error('must not fetch'); } });
    await t.api.dropEntries([entry(makeFile('c.json', MCP_JSON))]);
    ok(t.toastText().indexOf('Sign in first') !== -1, 'asks the user to sign in');
    eq(t.log.confirms.length + t.log.fetches.length, 0, 'and does nothing else');
}

// ═══ 13. flows: the tab is reserved SYNCHRONOUSLY, then filled ═══
{
    const t = boot({ fetchImpl: async () => jsonResponse({ url: '/agent/agentic_control_panel/?flow=1' }) });
    const done = t.api.dropEntries([entry(makeFile('x.flw', '{}'))]);
    eq(t.log.opens.length, 1, 'window.open ran inside the drop task, before any await');
    await done;
    eq(t.tab.navigated, '/agent/agentic_control_panel/?flow=1', 'the tab was sent to the editor');
    eq(t.log.fetches[0][0], '/agent/flow_files/open/', 'through the flow-file endpoint');
}
{
    const t = boot({ popups: false });
    await t.api.dropEntries([entry(makeFile('x.fpmt', '{}'))]);
    ok(t.toastText().indexOf('Allow pop-ups') !== -1, 'a blocked pop-up is explained');
}
{
    const t = boot();
    let opened = null;
    t.api.register('flow-agent', (files) => { opened = files[0].name; }, { label: 'Agent flow -> canvas' });
    await t.api.dropEntries([entry(makeFile('x.flw', '{}'))]);
    eq(opened, 'x.flw', 'a page that can host the flow does');
    eq(t.log.opens.length, 0, 'and no tab is opened');
}

// ═══ 14. a failing handler is reported and does not wedge the router ═══
{
    const t = boot();
    t.api.register('text', () => { throw new Error('boom'); }, { label: 'x' });
    await t.api.dropEntries([entry(makeFile('a.py', 'x'))]);
    ok(t.log.alerts.some((a) => a.title === 'File drop' && a.message.indexOf('boom') !== -1), 'the failure is shown');
    let ran = false;
    t.api.register('text', () => { ran = true; }, { label: 'x' });
    await t.api.dropEntries([entry(makeFile('b.py', 'x'))]);
    ok(ran, 'the next drop still works');
}

// ═══ 15. one drop at a time ═══
{
    const t = boot();
    let release;
    t.api.register('text', () => new Promise((resolve) => { release = resolve; }), { label: 'x' });
    const first = t.api.dropEntries([entry(makeFile('a.py', 'x'))]);
    await settle();
    await t.api.dropEntries([entry(makeFile('b.py', 'x'))]);
    ok(t.toastText().indexOf('Still working') !== -1, 'a second drop during the first is told to wait');
    release();
    await first;
    let ran = false;
    t.api.register('text', () => { ran = true; }, { label: 'x' });
    await t.api.dropEntries([entry(makeFile('c.py', 'x'))]);
    ok(ran, 'and works once the first has finished');
}

// ═══ 16. a handler can say what it could not use ═══
{
    const t = boot();
    t.api.register(['pdf', 'markdown', 'text'], (files) => ({ ignored: files.slice(1), note: 'Opened ' + files[0].name + '; the rest was not opened.' }), { label: 'x' });
    await t.api.dropEntries([entry(makeFile('a.py', 'x')), entry(makeFile('b.py', 'x'))]);
    ok(t.toastText().indexOf('Opened a.py; the rest was not opened.') !== -1, 'the handler note reaches the user');
}

// ═══ 17. the listeners themselves ═══
{
    const t = boot();
    const eventOf = (type, over = {}) => ({
        type, target: over.target || { closest: () => null }, relatedTarget: null, clientX: 5, clientY: 5,
        dataTransfer: { types: over.types || ['Files'], items: over.items || [], files: over.files || [], dropEffect: '' },
        defaultPrevented: false, stopped: false,
        preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; }
    });
    const dragover = eventOf('dragover');
    t.listeners.dragover[0].fn(dragover);
    ok(dragover.defaultPrevented && dragover.stopped, 'a file drag is claimed');
    eq(dragover.dataTransfer.dropEffect, 'copy', 'and shown as a copy');
    const text = eventOf('dragover', { types: ['text/plain'] });
    t.listeners.dragover[0].fn(text);
    ok(!text.defaultPrevented && !text.stopped, 'a text drag (agent sidebar) is left alone');
    const operation = eventOf('drop', { types: ['application/x-tlamatini-operation'] });
    t.listeners.drop[0].fn(operation);
    ok(!operation.defaultPrevented, 'a palette drag (Prompt Flow Panel) is left alone');
    const input = eventOf('drop', { target: { closest: (sel) => (sel === 'input[type="file"]' ? {} : null) } });
    t.listeners.drop[0].fn(input);
    ok(!input.defaultPrevented, 'a drop on a native file input is left to the browser');
    const file = makeFile('a.py', 'x');
    const real = eventOf('drop', { files: [file], items: [{ kind: 'file', type: '', getAsFile: () => file, webkitGetAsEntry: () => ({ isDirectory: false }) }] });
    let received = null;
    t.api.register('text', (files) => { received = files[0].name; }, { label: 'x' });
    t.listeners.drop[0].fn(real);
    ok(real.defaultPrevented && real.stopped, 'a file drop is claimed (the browser never navigates to it)');
    await settle();
    eq(received, 'a.py', 'and routed to the registered handler');
}

// ═══ 18. an embedded viewer hands the drop to the page that owns it ═══
{
    const relayed = [];
    const owner = { TlamatiniFileDrop: { dropEntries: (entries) => { relayed.push(entries); return Promise.resolve(); } } };
    const t = boot({ parent: owner });
    let local = false;
    t.api.register('text', () => { local = true; }, { label: 'x' });
    const file = makeFile('a.py', 'x');
    const event = {
        type: 'drop', target: { closest: () => null }, relatedTarget: null,
        dataTransfer: { types: ['Files'], items: [{ kind: 'file', type: '', getAsFile: () => file, webkitGetAsEntry: () => ({ isDirectory: false }) }], files: [file] },
        preventDefault() {}, stopPropagation() {}
    };
    t.listeners.drop[0].fn(event);
    await settle();
    eq(relayed.length, 1, 'the PDF canvas iframe relays to its parent page');
    ok(!local, 'and does not handle it twice');
}

// ═══ 19. the overlay tells the truth about THIS page ═══
{
    const t = boot();
    const json = t.api.hintLines({ count: 1, kinds: ['json'] });
    ok(json[0].text.indexOf('MCP server config') === 0 && !json[0].off, 'JSON: the MCP import is announced everywhere');
    ok(!json.some((l) => l.text.indexOf('Any other JSON') === 0), 'with no document handler there is no "other JSON" line');
    const image = t.api.hintLines({ count: 1, kinds: ['image'] });
    ok(image[0].off && image[0].text.indexOf('Images are not used') === 0, 'images are marked unused on a page that cannot take them');
    t.api.register(['pdf', 'markdown', 'text'], () => {}, { label: 'Document -> opens in the canvas' });
    t.api.register('image', () => {}, { label: 'Image -> attached' });
    ok(t.api.hintLines({ count: 1, kinds: ['json'] }).some((l) => l.text.indexOf('Any other JSON') === 0), 'with a canvas, other JSON is announced too');
    eq(t.api.hintLines({ count: 1, kinds: ['image'] })[0].text, 'Image -> attached', 'a registered label is what the user reads');
    eq(t.api.hintLines({ count: 0, kinds: [] })[0].text.indexOf('Release to let Tlamatini decide'), 0, 'an unknown drag still gets a hint');
}

console.log('FILE_DROP_ROUTER_CASES_OK ' + checks);
