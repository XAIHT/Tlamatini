/* ═══════════════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove
 *
 * file_drop_router.js — ONE smart listener for every file dropped on ANY
 * Tlamatini page.
 *
 * WHY IT EXISTS (Angela, 2026-10-14): every page used to have its own, blind
 * drop handler, and they fought each other. A dropped MCP `.json` was reported
 * as an error by the chat's image handler, OPENED AS TEXT by the canvas handler
 * (which also swallowed the event, so the import never saw it), and on the
 * Agentic Control Panel / Prompt Flow Panel / welcome page it simply made the
 * browser NAVIGATE AWAY to the file. There was no single place that knew what a
 * dropped file *is*.
 *
 * HOW IT WORKS
 *   1. Capture-phase listeners on `window` claim EVERY file drag, before any
 *      page handler can see it, so no private overlay or state is ever started
 *      by a file drag and the browser never navigates to the file.
 *   2. Each dropped item is CLASSIFIED — never trusting the extension alone:
 *      extension → MIME → magic bytes (PDF/PNG/JPEG/GIF/WEBP/…) → BOM-aware
 *      text/binary test → for JSON, a real parse that recognises an MCP server
 *      config in every shape found in the wild.
 *   3. Each kind is DISPATCHED to a different mechanism:
 *        mcp-json     → confirm, then add to the External MCP catalog   (built in, every page)
 *        flow-agent   → Agentic Control Panel canvas / a new editor tab (.flw)
 *        flow-prompt  → Prompt Flow Panel / a new editor tab            (.fpmt)
 *        image        → chat: saved to Temp, path put in the message    (page-registered)
 *        pdf / markdown / text → the chat canvas                        (page-registered)
 *        folder / archive / binary → a clear explanation, never garbage
 *      A page registers what it can do with `TlamatiniFileDrop.register(...)`;
 *      what a page cannot do falls back to a built-in or to a plain-words toast
 *      that says where the file CAN be used.
 *   4. While dragging, one overlay tells the user — from the MIME types the
 *      browser exposes — exactly what will happen on THIS page.
 *
 * CONTRACTS (do NOT weaken)
 *   · Claimed in the CAPTURE phase on `window`, and only for drags that carry
 *     `Files`. Text / `application/x-tlamatini-*` drags are never touched.
 *   · A drop onto a native <input type="file"> is left to the browser.
 *   · A flow tab is reserved SYNCHRONOUSLY inside the drop task (popup blockers
 *     refuse window.open after an await).
 *   · MCP configs carry executable commands: they are NEVER imported without an
 *     explicit confirmation that lists what will be added.
 *   · FAIL-OPEN: every step is guarded. A router that throws must never cost
 *     the user the page.
 *   · Self-contained IIFE: it declares NO cross-file globals (see the
 *     const-poison contract in docs/claude/frontend.md). Its only export is
 *     window.TlamatiniFileDrop.
 */
(function () {
    'use strict';

    if (typeof window === 'undefined' || typeof document === 'undefined') return;
    if (window.TlamatiniFileDrop) return;

    // ── page facts ─────────────────────────────────────────────────────────
    const CURRENT_SCRIPT = document.currentScript;
    // The login page loads this with data-auth="none": nothing can be imported
    // or opened before sign-in, but the drop must still never navigate away.
    const AUTHENTICATED = !(CURRENT_SCRIPT && CURRENT_SCRIPT.getAttribute &&
        CURRENT_SCRIPT.getAttribute('data-auth') === 'none');
    const IN_FRAME = (function () {
        try { return !!window.parent && window.parent !== window; } catch (e) { return false; }
    }());

    // ── kinds ──────────────────────────────────────────────────────────────
    const MCP = 'mcp-json';
    const FLOW_AGENT = 'flow-agent';
    const FLOW_PROMPT = 'flow-prompt';
    const IMAGE = 'image';
    const PDF = 'pdf';
    const MARKDOWN = 'markdown';
    const TEXT = 'text';
    const ARCHIVE = 'archive';
    const BINARY = 'binary';
    const SNIFF = 'sniff'; // internal: the name alone cannot decide
    const ORDER = [MCP, FLOW_AGENT, FLOW_PROMPT, IMAGE, PDF, MARKDOWN, TEXT, ARCHIVE, BINARY];

    const MAX_FILES = 25;
    const MAX_JSON_BYTES = 2 * 1024 * 1024;
    const MAX_FLOW_BYTES = 5 * 1024 * 1024;
    const HEAD_BYTES = 8192;

    const IMAGE_EXT = new Set(['png', 'jpg', 'jpeg', 'jpe', 'jfif', 'gif', 'webp', 'bmp', 'tif', 'tiff',
        'ico', 'avif', 'heic', 'heif']);
    const ARCHIVE_EXT = new Set(['zip', '7z', 'rar', 'tar', 'gz', 'tgz', 'bz2', 'xz']);
    const BINARY_EXT = new Set(['exe', 'dll', 'so', 'dylib', 'bin', 'dat', 'iso', 'msi', 'class', 'jar', 'pyc',
        'o', 'obj', 'lib', 'mp3', 'wav', 'flac', 'ogg', 'mp4', 'mkv', 'avi', 'mov', 'webm', 'docx', 'xlsx',
        'pptx', 'doc', 'xls', 'ppt', 'odt', 'ods', 'odp', 'otf', 'ttf', 'woff', 'woff2', 'db', 'sqlite']);
    const TEXT_EXT = new Set(('txt text log rst adoc asciidoc org tex c h cc cpp cxx c++ hh hpp hxx h++ ino cu cuh ' +
        'cs java kt kts scala groovy gradle go rs swift m mm py pyw pyi rb rake php phtml pl pm lua tcl r jl ' +
        'dart nim cr zig d v sv svh vhd vhdl js mjs cjs jsx ts mts cts tsx vue svelte astro coffee html htm ' +
        'xhtml xml xsl xslt svg css scss sass less styl json5 jsonc yaml yml toml ini cfg conf config ' +
        'properties env editorconfig csv tsv sql graphql gql proto prisma sh bash zsh fish bat cmd ps1 psm1 ' +
        'psd1 awk sed vim asm s f f90 f95 f03 for pas pp ada adb ads cob cbl clj cljs cljc edn ex exs erl hrl ' +
        'hs lhs ml mli fs fsx fsi elm lisp lsp scm rkt cmake mk mak make dockerfile bazel bzl sln csproj ' +
        'vbproj vcxproj fsproj pom sbt gitignore gitattributes dockerignore jinja jinja2 j2 twig erb ejs hbs ' +
        'handlebars mustache pug haml liquid pmt').split(' '));
    const TEXT_NAMES = new Set(['makefile', 'dockerfile', 'license', 'licence', 'readme', 'changelog',
        'authors', 'copying', 'notice', 'procfile', 'gemfile', 'rakefile']);

    // ── small helpers ──────────────────────────────────────────────────────
    function isObj(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }

    function extOf(name) {
        const m = /\.([^.\\/]+)$/.exec(String(name || ''));
        return m ? m[1].toLowerCase() : '';
    }

    function baseOf(name) {
        return String(name || '').replace(/^.*[\\/]/, '').replace(/\.[^.]*$/, '');
    }

    function namesOf(files) {
        return files.map(function (f) { return f && f.name ? f.name : 'file'; }).join(', ');
    }

    function csrfToken() {
        const m = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        if (m) return decodeURIComponent(m[1]);
        const input = document.querySelector('[name=csrfmiddlewaretoken]');
        return input ? input.value : '';
    }

    // Themed popups when dialog_policy.js is on the page; the native ones
    // otherwise — an ugly warning beats a lost one.
    function ask(primary, secondary, title, options) {
        if (typeof window.tlmConfirm === 'function') {
            return window.tlmConfirm(primary, secondary, title, options);
        }
        return Promise.resolve(window.confirm([primary, secondary].filter(Boolean).join('\n\n')));
    }

    function tell(message, title) {
        if (typeof window.tlmAlert === 'function') return window.tlmAlert(message, title);
        window.alert(String(message));
        return Promise.resolve(true);
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  CLASSIFICATION
    // ═══════════════════════════════════════════════════════════════════════

    /** Decide from the NAME / MIME alone; SNIFF when the bytes must decide. */
    function quickKind(file) {
        const name = (file && file.name) || '';
        const ext = extOf(name);
        const type = ((file && file.type) || '').toLowerCase();
        if (ext === 'flw') return FLOW_AGENT;
        if (ext === 'fpmt') return FLOW_PROMPT;
        if (ext === 'json') return SNIFF; // MCP config or plain JSON text
        if (ext === 'pdf' || type === 'application/pdf') return PDF;
        if (ext === 'md' || ext === 'markdown') return MARKDOWN;
        if (ext === 'svg') return TEXT; // vector markup is readable source
        if (IMAGE_EXT.has(ext) || (/^image\//.test(type) && type !== 'image/svg+xml')) return IMAGE;
        if (ARCHIVE_EXT.has(ext)) return ARCHIVE;
        if (BINARY_EXT.has(ext)) return BINARY;
        if (TEXT_EXT.has(ext) || /^text\//.test(type) || TEXT_NAMES.has(name.toLowerCase())) return TEXT;
        return SNIFF;
    }

    /** Byte-order mark → encoding name. Longest prefix first (UTF-32-LE starts with UTF-16-LE's). */
    function bomOf(b) {
        if (b.length >= 4 && b[0] === 0xFF && b[1] === 0xFE && b[2] === 0 && b[3] === 0) return 'utf-32le';
        if (b.length >= 4 && b[0] === 0 && b[1] === 0 && b[2] === 0xFE && b[3] === 0xFF) return 'utf-32be';
        if (b.length >= 3 && b[0] === 0xEF && b[1] === 0xBB && b[2] === 0xBF) return 'utf-8';
        if (b.length >= 2 && b[0] === 0xFF && b[1] === 0xFE) return 'utf-16le';
        if (b.length >= 2 && b[0] === 0xFE && b[1] === 0xFF) return 'utf-16be';
        return '';
    }

    /** Text from bytes, honouring a BOM (Windows PowerShell writes UTF-16 JSON). null = undecodable. */
    function decodeBytes(bytes) {
        const bom = bomOf(bytes);
        if (bom === 'utf-32le' || bom === 'utf-32be') return null;
        const offset = bom === 'utf-8' ? 3 : (bom ? 2 : 0);
        try {
            return new TextDecoder(bom || 'utf-8').decode(offset ? bytes.subarray(offset) : bytes);
        } catch (e) {
            return null;
        }
    }

    /** NUL / control-byte test — the BOM check MUST come first or UTF-16 text reads as binary. */
    function looksBinary(head) {
        if (bomOf(head)) return false;
        let control = 0;
        for (let i = 0; i < head.length; i += 1) {
            const b = head[i];
            if (b === 0) return true;
            if (b < 9 || (b > 13 && b < 32 && b !== 27)) control += 1;
        }
        return head.length >= 32 && control / head.length > 0.3;
    }

    /** Magic numbers beat a missing or lying extension. */
    function magicKind(h) {
        const at = function (i) { return h[i]; };
        if (h.length >= 5 && at(0) === 0x25 && at(1) === 0x50 && at(2) === 0x44 && at(3) === 0x46 && at(4) === 0x2D) return PDF;
        if (h.length >= 8 && at(0) === 0x89 && at(1) === 0x50 && at(2) === 0x4E && at(3) === 0x47) return IMAGE;
        if (h.length >= 3 && at(0) === 0xFF && at(1) === 0xD8 && at(2) === 0xFF) return IMAGE;
        if (h.length >= 6 && at(0) === 0x47 && at(1) === 0x49 && at(2) === 0x46 && at(3) === 0x38) return IMAGE;
        if (h.length >= 12 && at(0) === 0x52 && at(1) === 0x49 && at(2) === 0x46 && at(3) === 0x46 &&
            at(8) === 0x57 && at(9) === 0x45 && at(10) === 0x42 && at(11) === 0x50) return IMAGE;
        if (h.length >= 10 && at(0) === 0x42 && at(1) === 0x4D && at(6) === 0 && at(7) === 0 && at(8) === 0 && at(9) === 0) return IMAGE;
        if (h.length >= 4 && ((at(0) === 0x49 && at(1) === 0x49 && at(2) === 0x2A && at(3) === 0) ||
            (at(0) === 0x4D && at(1) === 0x4D && at(2) === 0 && at(3) === 0x2A))) return IMAGE;
        if (h.length >= 4 && at(0) === 0x50 && at(1) === 0x4B && at(2) === 0x03 && at(3) === 0x04) return ARCHIVE;
        if (h.length >= 6 && at(0) === 0x37 && at(1) === 0x7A && at(2) === 0xBC && at(3) === 0xAF) return ARCHIVE;
        if (h.length >= 2 && at(0) === 0x1F && at(1) === 0x8B) return ARCHIVE;
        if (h.length >= 4 && at(0) === 0x52 && at(1) === 0x61 && at(2) === 0x72 && at(3) === 0x21) return ARCHIVE;
        return '';
    }

    // ── MCP server config recognition ──────────────────────────────────────
    const URL_KEYS = ['url', 'endpoint', 'sseUrl', 'sse_url', 'streamableHttpUrl', 'streamable_http_url',
        'wsUrl', 'ws_url', 'websocketUrl', 'webSocketUrl', 'socketPath', 'namedPipe', 'pipe'];
    const CONTAINER_KEYS = ['mcpServers', 'mcp_servers', 'servers', 'context_servers', 'mcpservers'];

    /** Fold the command shapes other clients use into Tlamatini's command + args + env. */
    function normalizeSpec(spec) {
        if (!isObj(spec)) return null;
        const out = Object.assign({}, spec);
        if (Array.isArray(out.command)) { // opencode: ["npx", "-y", "pkg"]
            const parts = out.command.map(String).filter(function (p) { return p.length; });
            out.command = parts[0] || '';
            out.args = parts.slice(1).concat(Array.isArray(out.args) ? out.args.map(String) : []);
        } else if (isObj(out.command)) { // Zed: { path, args, env }
            const c = out.command;
            out.command = String(c.path || c.command || '');
            if (!Array.isArray(out.args) && Array.isArray(c.args)) out.args = c.args.map(String);
            if (!isObj(out.env) && isObj(c.env)) out.env = c.env;
        }
        if (!isObj(out.env) && isObj(out.environment)) out.env = out.environment;
        return out;
    }

    function isServerSpec(spec) {
        if (!isObj(spec)) return false;
        const s = normalizeSpec(spec);
        if (typeof s.command === 'string' && s.command.trim()) return true;
        for (let i = 0; i < URL_KEYS.length; i += 1) {
            const v = s[URL_KEYS[i]];
            if (typeof v === 'string' && v.trim()) return true;
        }
        return Boolean(s.host && s.port);
    }

    function mapFrom(container) {
        const out = {};
        if (Array.isArray(container)) {
            container.forEach(function (item, i) {
                if (!isServerSpec(item)) return;
                const name = String(item.name || item.id || item.key || ('server_' + (i + 1))).trim();
                if (name) out[name] = normalizeSpec(item);
            });
        } else if (isObj(container)) {
            Object.keys(container).forEach(function (key) {
                const name = String(key).trim();
                if (name && isServerSpec(container[key])) out[name] = normalizeSpec(container[key]);
            });
        }
        return out;
    }

    /**
     * Find MCP servers in any shape seen in the wild: Claude Desktop/Code
     * (`mcpServers`, also per-project in `.claude.json`), VS Code (`servers`,
     * `mcp.servers`), Zed (`context_servers`), opencode (`mcp` map), a bare
     * single server, a bare name→server map, or an array of named servers.
     * A generic JSON file is NOT mistaken for one: a bare map qualifies only
     * when EVERY value is a server.
     */
    function extractServers(parsed, fileName) {
        const servers = {};
        const take = function (container) {
            const found = mapFrom(container);
            Object.keys(found).forEach(function (k) { if (!(k in servers)) servers[k] = found[k]; });
        };
        if (Array.isArray(parsed)) {
            take(parsed);
        } else if (isObj(parsed)) {
            CONTAINER_KEYS.forEach(function (key) { if (key in parsed) take(parsed[key]); });
            if (isObj(parsed.mcp)) { take(parsed.mcp.servers); take(parsed.mcp.mcpServers); take(parsed.mcp); }
            if (isObj(parsed.projects)) {
                Object.keys(parsed.projects).slice(0, 200).forEach(function (p) {
                    if (isObj(parsed.projects[p])) take(parsed.projects[p].mcpServers);
                });
            }
            if (!Object.keys(servers).length) {
                if (isServerSpec(parsed)) {
                    const inferred = String(parsed.name || baseOf(fileName) || 'Imported_MCP')
                        .trim().replace(/[^\w.-]+/g, '_') || 'Imported_MCP';
                    servers[inferred] = normalizeSpec(parsed);
                } else {
                    const values = Object.keys(parsed).map(function (k) { return parsed[k]; });
                    if (values.length && values.every(isServerSpec)) take(parsed);
                }
            }
        }
        return { servers: servers, names: Object.keys(servers) };
    }

    async function readBytes(file, start, end) {
        return new Uint8Array(await file.slice(start, end).arrayBuffer());
    }

    /** Full classification — may read the head of the file (and parse JSON). */
    async function classify(file) {
        const quick = quickKind(file);
        if (quick !== SNIFF) return { kind: quick };
        const ext = extOf(file.name);
        let head;
        try { head = await readBytes(file, 0, HEAD_BYTES); } catch (e) { return { kind: BINARY, unreadable: true }; }
        if (!head.length) return { kind: TEXT, empty: true };
        const magic = magicKind(head);
        if (magic) return { kind: magic };
        if (looksBinary(head)) return { kind: BINARY };
        const startText = decodeBytes(head);
        const jsonish = ext === 'json' || (startText !== null && /^\s*[{[]/.test(startText));
        if (!jsonish) return { kind: TEXT };
        if (file.size > MAX_JSON_BYTES) return { kind: TEXT, json: true };
        let text;
        try { text = decodeBytes(await readBytes(file, 0, file.size)); } catch (e) { text = null; }
        if (text === null) return { kind: TEXT };
        let parsed;
        try {
            parsed = JSON.parse(text);
        } catch (error) {
            return ext === 'json'
                ? { kind: TEXT, invalidJson: String(error && error.message ? error.message : error) }
                : { kind: TEXT };
        }
        const found = extractServers(parsed, file.name);
        if (found.names.length) return { kind: MCP, servers: found.servers, names: found.names };
        return { kind: TEXT, json: true };
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  HANDLER REGISTRY
    // ═══════════════════════════════════════════════════════════════════════

    const handlers = new Map(); // kind -> { fn, label }

    /**
     * Teach THIS page what to do with a kind of dropped file.
     *   register('image', async files => {...}, { label: 'Image → attached to your message' })
     *   register(['pdf', 'markdown', 'text'], fn)   // one call for the whole group
     * `fn(files, items)` may return { ignored: File[], note: string } to report
     * what it could not use. Returns a function that removes the registration.
     */
    function register(kinds, fn, options) {
        const list = Array.isArray(kinds) ? kinds : [kinds];
        const label = (options && options.label) || '';
        list.forEach(function (kind) { handlers.set(kind, { fn: fn, label: label }); });
        return function unregister() {
            list.forEach(function (kind) {
                const current = handlers.get(kind);
                if (current && current.fn === fn) handlers.delete(kind);
            });
        };
    }

    // ── built-in: MCP import (works on every page) ─────────────────────────
    async function importServers(map) {
        const response = await fetch('/agent/external_mcps/import/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'X-CSRFToken': csrfToken(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ mcpServers: map })
        });
        const type = (response.headers && response.headers.get('content-type')) || '';
        if (response.redirected || !/json/i.test(type)) {
            throw new Error('Your session expired. Sign in, then drop the file again.');
        }
        const data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || ('HTTP ' + response.status));
        return data;
    }

    async function importMcpItems(files, items) {
        const merged = {};
        items.forEach(function (item) {
            const found = (item.info && item.info.servers) || {};
            Object.keys(found).forEach(function (k) { merged[k] = found[k]; });
        });
        const names = Object.keys(merged);
        if (!names.length) return { note: 'No MCP servers were found in ' + namesOf(files) + '.' };
        const plural = names.length === 1 ? '' : 's';
        const from = files.length > 1 ? (' from ' + files.length + ' files') : '';
        const proceed = await ask('Add ' + names.length + ' MCP server' + plural + ' to the catalog' + from + '?',
            names.join(', ') + '  —  these entries can launch programs on this computer; import only ' +
            'configurations you trust.', 'Import MCP servers');
        if (!proceed) return { note: 'Nothing was imported.' };
        let data;
        try {
            data = await importServers(merged);
        } catch (error) {
            await tell('Import failed: ' + (error && error.message ? error.message : error), 'Import failed');
            return {};
        }
        try {
            document.dispatchEvent(new CustomEvent('tlm:external-mcps-imported', { detail: data }));
        } catch (e) { /* the dialog refresh is a courtesy */ }
        const added = (data.added || []).length;
        const updated = (data.updated || []).length;
        const skipped = names.length - added - updated;
        if (!added && !updated) {
            await tell('Nothing was imported: none of the ' + names.length + ' entr' +
                (names.length === 1 ? 'y has' : 'ies has') + ' a command or a url.', 'Nothing to import');
            return {};
        }
        const summary = 'Catalog updated — ' + added + ' added, ' + updated + ' updated.' +
            (skipped > 0 ? ' ' + skipped + ' skipped (no command or url).' : '');
        if (typeof window.OpenExternalMcpsDialog === 'function') {
            const open = await ask(summary, 'Open External ▸ MCPs now to activate them?', 'Import complete',
                { confirmLabel: 'Open External ▸ MCPs', cancelLabel: 'Later' });
            if (open) {
                try { window.OpenExternalMcpsDialog(); } catch (e) { /* the menu entry still works */ }
            }
        } else {
            await tell(summary + '  Open External ▸ MCPs in the Tlamatini chat page to activate them.',
                'Import complete');
        }
        return {};
    }

    // ── built-in: flow files open in their own editor tab ──────────────────
    function openPlaceholderTab(file) {
        let tab;
        try { tab = window.open('about:blank', '_blank'); } catch (e) { return null; }
        if (!tab) return null;
        try {
            tab.document.title = 'Opening flow · Tlamatini';
            tab.document.body.textContent = 'Opening ' + file.name + '…';
            tab.document.body.style.cssText = 'background:#24252f;color:#eee;font:18px system-ui;padding:48px';
            tab.opener = null;
        } catch (e) { /* the placeholder is cosmetic */ }
        return tab;
    }

    async function openFlowInTab(item) {
        const file = item.file;
        const tab = item.tab;
        if (!tab) {
            toast('Allow pop-ups for Tlamatini, then drop ' + file.name + ' again.');
            return;
        }
        try {
            if (file.size > MAX_FLOW_BYTES) throw new Error('The flow file must be no larger than 5 MiB.');
            const body = new FormData();
            body.append('file', file);
            const response = await fetch('/agent/flow_files/open/', {
                method: 'POST', credentials: 'same-origin', headers: { 'X-CSRFToken': csrfToken() }, body: body
            });
            if (response.redirected) throw new Error('Your session expired. Sign in, then open the file again.');
            const result = await response.json();
            if (!response.ok) throw new Error(result.error || 'The file could not be opened.');
            if (!tab.closed) tab.location.replace(result.url);
        } catch (error) {
            if (!tab.closed) tab.close();
            await tell('Could not open ' + file.name + ': ' + (error && error.message ? error.message : error),
                'Open flow');
        }
    }

    async function openFlowItems(files, items) {
        await Promise.all(items.map(openFlowInTab));
        return {};
    }

    const BUILTIN = {};
    BUILTIN[MCP] = { fn: importMcpItems, label: 'MCP server config → added to the External MCP catalog' };
    BUILTIN[FLOW_AGENT] = { fn: openFlowItems, label: 'Agent flow (.flw) → opens in the Agentic Control Panel' };
    BUILTIN[FLOW_PROMPT] = { fn: openFlowItems, label: 'Prompt flow (.fpmt) → opens in the Prompt Flow Panel' };

    function lookup(kind) { return handlers.get(kind) || BUILTIN[kind] || null; }

    // ═══════════════════════════════════════════════════════════════════════
    //  UI — overlay (what will happen) and toast (what happened)
    // ═══════════════════════════════════════════════════════════════════════

    let overlay = null;
    let titleEl = null;
    let linesEl = null;
    let toastEl = null;
    let toastTimer = null;
    let depth = 0;
    let watchdog = null;
    let lastSignature = '';

    function injectStyle() {
        if (document.getElementById('tlm-file-drop-style')) return;
        const style = document.createElement('style');
        style.id = 'tlm-file-drop-style';
        style.textContent =
            '#tlm-file-drop-overlay{position:fixed;inset:0;z-index:2147483000;display:none;align-items:center;' +
            'justify-content:center;padding:24px;background:rgba(13,16,28,.80);pointer-events:none;' +
            "font-family:'Nunito',system-ui,sans-serif;color:#fff}" +
            '#tlm-file-drop-overlay.show{display:flex}' +
            '.tlm-fd-card{max-width:min(660px,92vw);padding:22px 30px;border:2px dashed #55BBAA;' +
            'border-radius:16px;background:rgba(0,0,0,.42);text-align:center}' +
            '.tlm-fd-title{font-size:1.25rem;font-weight:700;margin-bottom:10px}' +
            '.tlm-fd-lines{list-style:none;margin:0;padding:0;font-size:.95rem;line-height:1.5}' +
            '.tlm-fd-lines li{margin:5px 0}.tlm-fd-lines li.off{opacity:.62}' +
            '#tlm-file-drop-toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%);' +
            'z-index:2147483000;display:none;max-width:min(700px,92vw);padding:12px 18px;border-radius:12px;' +
            'background:#1f2937;color:#f9fafb;border:1px solid #55BBAA;white-space:pre-line;' +
            "font:600 .9rem/1.45 'Nunito',system-ui,sans-serif;box-shadow:0 8px 28px rgba(0,0,0,.45)}" +
            '#tlm-file-drop-toast.show{display:block}';
        (document.head || document.documentElement).appendChild(style);
    }

    function ensureUi() {
        injectStyle();
        const host = document.body || document.documentElement;
        if (!overlay) {
            overlay = document.createElement('div');
            overlay.id = 'tlm-file-drop-overlay';
            overlay.setAttribute('aria-hidden', 'true');
            const card = document.createElement('div');
            card.className = 'tlm-fd-card';
            titleEl = document.createElement('div');
            titleEl.className = 'tlm-fd-title';
            linesEl = document.createElement('ul');
            linesEl.className = 'tlm-fd-lines';
            card.appendChild(titleEl);
            card.appendChild(linesEl);
            overlay.appendChild(card);
            host.appendChild(overlay);
        }
        if (!toastEl) {
            toastEl = document.createElement('div');
            toastEl.id = 'tlm-file-drop-toast';
            toastEl.setAttribute('role', 'status');
            toastEl.setAttribute('aria-live', 'polite');
            host.appendChild(toastEl);
        }
    }

    /** A short, non-blocking message. Used for everything that needs no decision. */
    function toast(message, ms) {
        try {
            ensureUi();
            toastEl.textContent = String(message);
            toastEl.classList.add('show');
            window.clearTimeout(toastTimer);
            toastTimer = window.setTimeout(function () { toastEl.classList.remove('show'); },
                ms || Math.min(14000, 4500 + String(message).length * 45));
        } catch (e) { /* a lost toast must never break the page */ }
    }

    // What the drag LOOKS like, from the MIME types the browser exposes.
    function guessFromItems(dt) {
        const items = dt && dt.items ? Array.prototype.slice.call(dt.items) : [];
        const files = items.filter(function (i) { return i.kind === 'file'; });
        const kinds = {};
        files.forEach(function (item) {
            const type = (item.type || '').toLowerCase();
            let kind = 'unknown';
            if (type === 'application/json' || type === 'text/json') kind = 'json';
            else if (type === 'application/pdf') kind = PDF;
            else if (type === 'text/markdown') kind = MARKDOWN;
            else if (/^image\//.test(type) && type !== 'image/svg+xml') kind = IMAGE;
            else if (/^text\//.test(type) || type === 'image/svg+xml') kind = TEXT;
            kinds[kind] = true;
        });
        return { count: files.length || (dt && dt.files ? dt.files.length : 0), kinds: Object.keys(kinds) };
    }

    const NOT_USED = {
        image: 'Images are not used on this page — drop them on the Tlamatini chat',
        pdf: 'PDFs are not used on this page — drop them on the Tlamatini chat',
        markdown: 'Markdown is not used on this page — drop it on the Tlamatini chat',
        text: 'Text and code files are not used on this page — drop them on the Tlamatini chat'
    };

    function hintLines(guess) {
        const lines = [];
        const labelOf = function (kind) { const h = lookup(kind); return h ? h.label : ''; };
        guess.kinds.forEach(function (kind) {
            if (kind === 'json') {
                lines.push({ text: labelOf(MCP), off: false });
                const other = labelOf(TEXT);
                if (other) lines.push({ text: 'Any other JSON → ' + other.replace(/^.*?→\s*/, ''), off: false });
            } else if (kind === 'unknown') {
                lines.push({ text: 'Flows, documents, images and MCP configs are recognised when you drop them', off: false });
            } else {
                const label = labelOf(kind);
                lines.push(label ? { text: label, off: false } : { text: NOT_USED[kind] || '', off: true });
            }
        });
        if (!lines.length) lines.push({ text: 'Release to let Tlamatini decide what to do with it', off: false });
        return lines.filter(function (l) { return l.text; });
    }

    function showOverlay(dt) {
        try {
            ensureUi();
            const guess = guessFromItems(dt);
            const lines = (IN_FRAME && frameApi() && frameApi().hintLines) ? frameApi().hintLines(guess) : hintLines(guess);
            const title = guess.count > 1 ? 'Drop ' + guess.count + ' files' : 'Drop the file';
            const signature = title + '|' + lines.map(function (l) { return l.text; }).join('|');
            if (signature !== lastSignature) {
                lastSignature = signature;
                titleEl.textContent = title;
                linesEl.textContent = '';
                lines.forEach(function (line) {
                    const li = document.createElement('li');
                    li.textContent = line.text;
                    if (line.off) li.className = 'off';
                    linesEl.appendChild(li);
                });
            }
            overlay.classList.add('show');
            window.clearTimeout(watchdog);
            // dragover repeats while the pointer is over the page; if it stops (Escape,
            // the pointer left the window) nothing else tells us, so the overlay times out.
            watchdog = window.setTimeout(hideOverlay, 1200);
        } catch (e) { /* the hint is a courtesy */ }
    }

    function hideOverlay() {
        depth = 0;
        window.clearTimeout(watchdog);
        if (overlay) overlay.classList.remove('show');
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  DISPATCH
    // ═══════════════════════════════════════════════════════════════════════

    let processing = false;

    function folderNote(folders) {
        const where = document.getElementById('set-dir-context')
            ? 'Use Context ▸ Set directory as context to load a folder.'
            : 'Tlamatini loads folders from the chat page: Context ▸ Set directory as context.';
        return 'Folders cannot be dropped (' + folders.map(function (f) { return f.name || 'folder'; }).join(', ') +
            ') — the browser does not hand Tlamatini a folder path. ' + where;
    }

    function acceptedLabels() {
        const out = [];
        ORDER.forEach(function (kind) {
            const h = lookup(kind);
            if (h && h.label && out.indexOf(h.label) === -1) out.push(h.label);
        });
        return out;
    }

    function unhandledNote(items) {
        const KIND_WORD = { image: 'image', pdf: 'PDF', markdown: 'Markdown', text: 'text file',
            archive: 'archive', binary: 'binary file' };
        const list = items.map(function (i) {
            return i.file.name + ' (' + (KIND_WORD[i.kind] || i.kind) + ')';
        }).join(', ');
        const hints = [];
        const kinds = items.map(function (i) { return i.kind; });
        if (kinds.some(function (k) { return k === IMAGE; })) hints.push('images attach to a message on the Tlamatini chat page');
        if (kinds.some(function (k) { return k === PDF || k === MARKDOWN || k === TEXT; })) hints.push('documents open in the chat canvas');
        if (kinds.some(function (k) { return k === ARCHIVE || k === BINARY; })) hints.push('archives and binary files are not read');
        const accepts = acceptedLabels();
        return 'Skipped: ' + list + '.' + (hints.length ? ' (' + hints.join('; ') + ')' : '') +
            (accepts.length ? '\nThis page accepts: ' + accepts.join('  ·  ') : '');
    }

    async function runGroup(group, notes) {
        const files = group.items.map(function (i) { return i.file; });
        try {
            const result = await group.handler.fn(files, group.items);
            if (result && result.note) notes.push(result.note);
            else if (result && Array.isArray(result.ignored) && result.ignored.length) {
                notes.push('Not used: ' + namesOf(result.ignored));
            }
        } catch (error) {
            console.error('[file-drop] handler failed', error);
            await tell('Could not handle ' + namesOf(files) + ': ' + (error && error.message ? error.message : error),
                'File drop');
        }
    }

    async function run(entries) {
        const notes = [];
        let list = entries.filter(function (e) { return e && (e.isDirectory || e.file); });
        if (list.length > MAX_FILES) {
            notes.push('Only the first ' + MAX_FILES + ' of ' + list.length + ' dropped items were considered.');
            list = list.slice(0, MAX_FILES);
        }
        const folders = list.filter(function (e) { return e.isDirectory; });
        const files = list.filter(function (e) { return !e.isDirectory && e.file; });
        if (folders.length) notes.push(folderNote(folders.map(function (f) { return f.file || f; })));

        const plan = [];
        const pending = [];
        files.forEach(function (entry, index) {
            const kind = quickKind(entry.file);
            if (kind === SNIFF) { pending.push({ ...entry, index: index }); return; }
            const item = { ...entry, kind: kind, info: {}, index: index };
            // Reserve the editor tab NOW, still inside the drop task: popup blockers
            // refuse a window.open that happens after an await.
            if ((kind === FLOW_AGENT || kind === FLOW_PROMPT) && !handlers.get(kind)) {
                item.tab = openPlaceholderTab(entry.file);
            }
            plan.push(item);
        });
        for (let i = 0; i < pending.length; i += 1) {
            const info = await classify(pending[i].file);
            plan.push({ ...pending[i], kind: info.kind, info: info });
        }

        const groups = [];
        const byFn = new Map();
        const unhandled = [];
        ORDER.forEach(function (kind) {
            const items = plan.filter(function (p) { return p.kind === kind; });
            if (!items.length) return;
            const handler = lookup(kind);
            if (!handler) { unhandled.push.apply(unhandled, items); return; }
            let group = byFn.get(handler.fn);
            if (!group) { group = { handler: handler, items: [] }; byFn.set(handler.fn, group); groups.push(group); }
            group.items.push.apply(group.items, items);
        });
        groups.forEach(function (g) { g.items.sort(function (a, b) { return a.index - b.index; }); });

        for (let i = 0; i < groups.length; i += 1) await runGroup(groups[i], notes);

        plan.forEach(function (p) {
            if (p.info && p.info.invalidJson && lookup(p.kind)) {
                notes.push(p.file.name + ' is not valid JSON (' + p.info.invalidJson + ') — treated as plain text.');
            }
        });
        if (unhandled.length) notes.push(unhandledNote(unhandled));
        if (notes.length) toast(notes.join('\n'));
    }

    function route(entries) {
        if (!AUTHENTICATED) {
            toast('Sign in first, then drop the file on the Tlamatini chat page.');
            return Promise.resolve();
        }
        if (processing) {
            toast('Still working on the previous drop — try again in a moment.');
            return Promise.resolve();
        }
        processing = true;
        let promise;
        try {
            promise = run(entries);
        } catch (error) {
            processing = false;
            return Promise.reject(error);
        }
        return promise.catch(function (error) {
            console.error('[file-drop] failed', error);
            toast('That drop could not be processed: ' + (error && error.message ? error.message : error));
        }).then(function () { processing = false; });
    }

    // ═══════════════════════════════════════════════════════════════════════
    //  THE LISTENERS — claimed in the capture phase, for file drags only
    // ═══════════════════════════════════════════════════════════════════════

    function isFileDrag(event) {
        const types = event.dataTransfer && event.dataTransfer.types;
        if (!types) return false;
        for (let i = 0; i < types.length; i += 1) if (types[i] === 'Files') return true;
        return false;
    }

    function overNativeFileInput(event) {
        const el = event.target;
        return !!(el && el.closest && el.closest('input[type="file"]'));
    }

    function entriesFrom(dt) {
        const out = [];
        const items = dt.items ? Array.prototype.slice.call(dt.items) : [];
        items.forEach(function (item) {
            if (item.kind !== 'file') return;
            let isDirectory = false;
            let entry = null;
            let handlePromise = null;
            try {
                entry = item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
                isDirectory = !!(entry && entry.isDirectory);
            } catch (e) { /* an entry we cannot inspect is treated as a plain file */ }
            // Capture during the drop event, before the drag data store closes.
            // Attach a rejection handler immediately; unsupported access must
            // never prevent the ordinary drop/import/open path.
            try {
                if (!isDirectory && item.getAsFileSystemHandle) {
                    handlePromise = item.getAsFileSystemHandle().catch(function () { return null; });
                }
            } catch (e) { /* entry.file can still provide read access */ }
            const file = item.getAsFile();
            if (file || isDirectory) out.push({ file: file, isDirectory: isDirectory, entry: entry, handlePromise: handlePromise });
        });
        if (out.length) return out;
        return Array.prototype.slice.call(dt.files || []).map(function (file) {
            return { file: file, isDirectory: false };
        });
    }

    function frameApi() {
        try {
            const api = window.parent && window.parent.TlamatiniFileDrop;
            return api && typeof api.dropEntries === 'function' ? api : null;
        } catch (e) { return null; }
    }

    function claim(event) {
        event.preventDefault();
        event.stopPropagation();
    }

    window.addEventListener('dragenter', function (event) {
        if (!isFileDrag(event) || overNativeFileInput(event)) return;
        claim(event);
        depth += 1;
        showOverlay(event.dataTransfer);
    }, true);

    window.addEventListener('dragover', function (event) {
        if (!isFileDrag(event) || overNativeFileInput(event)) return;
        claim(event);
        try { event.dataTransfer.dropEffect = 'copy'; } catch (e) { /* read-only in some browsers */ }
        showOverlay(event.dataTransfer);
    }, true);

    window.addEventListener('dragleave', function (event) {
        if (!isFileDrag(event) || overNativeFileInput(event)) return;
        claim(event);
        depth = Math.max(0, depth - 1);
        const left = event.relatedTarget === null && (event.clientX <= 0 || event.clientY <= 0 ||
            event.clientX >= window.innerWidth || event.clientY >= window.innerHeight);
        if (depth === 0 || left) hideOverlay();
    }, true);

    window.addEventListener('drop', function (event) {
        if (!isFileDrag(event) || overNativeFileInput(event)) return;
        claim(event);
        hideOverlay();
        let entries;
        try { entries = entriesFrom(event.dataTransfer); } catch (e) { entries = []; }
        if (!entries.length) return;
        const parent = IN_FRAME ? frameApi() : null;
        if (parent) { // an embedded viewer (the PDF canvas) hands the drop to the page that owns it
            try { parent.dropEntries(entries); return; } catch (e) { /* fall through to local handling */ }
        }
        void route(entries);
    }, true);

    window.addEventListener('dragend', hideOverlay, true);
    window.addEventListener('blur', hideOverlay);

    // ── public surface ─────────────────────────────────────────────────────
    window.TlamatiniFileDrop = {
        version: 1,
        register: register,
        classify: classify,
        dropEntries: route,
        toast: toast,
        hintLines: hintLines,
        kinds: { MCP: MCP, FLOW_AGENT: FLOW_AGENT, FLOW_PROMPT: FLOW_PROMPT, IMAGE: IMAGE, PDF: PDF,
            MARKDOWN: MARKDOWN, TEXT: TEXT, ARCHIVE: ARCHIVE, BINARY: BINARY },
        // Test hooks: the pure functions the unit tests drive directly.
        _pure: { quickKind: quickKind, extractServers: extractServers, magicKind: magicKind,
            looksBinary: looksBinary, decodeBytes: decodeBytes, bomOf: bomOf, normalizeSpec: normalizeSpec }
    };
}());
