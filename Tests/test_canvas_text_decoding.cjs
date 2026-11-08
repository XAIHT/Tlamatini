/* Tlamatini Author Banner — Angela López Mendoza */
// Run with node --test Tests/test_canvas_text_decoding.cjs from a visible console.
// Exercise the shipped adapter, including its Save path, without a browser DOM.
const assert = require('node:assert/strict');
const { File } = require('node:buffer');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

function adapter() {
    let text = '';
    const element = () => ({ disabled: false, dataset: {}, textContent: '',
        classList: { add() {}, remove() {} }, setAttribute() {}, addEventListener() {} });
    const nodes = new Map();
    const sandbox = {
        TextDecoder, Uint8Array, DataView, Blob, File,
        document: { getElementById(id) {
            if (!nodes.has(id)) nodes.set(id, element());
            return nodes.get(id);
        }, addEventListener() {}, querySelectorAll: () => [] },
        window: { addEventListener() {}, removeEventListener() {},
            TlamatiniTextEditor: { getText: () => text, historyState: () => ({}),
                mount(_host, value) { text = value; }, setWrap() {}, setFilename() {} } },
        textEditorCode: element(), filenameSpan: element(), saveAsButton: element(),
        canvasSource: null, canvasSettedAsContext: false, getCanvasGeneration: () => 1,
        rememberCanvasSource(source) { sandbox.canvasSource = source; },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,
        '../Tlamatini/agent/static/agent/js/agent_page_editing.js'), 'utf8'), sandbox);
    return { api: sandbox.window.TlamatiniCanvasEditing, sandbox,
        edit(value) { text = value; } };
}

const source = '# README\n\nSource: \u0007ssets/, \u0008enchmarks/.\n\n' +
    'Readable Markdown with a few accidental PowerShell escape characters.\n';

function encoded(value, encoding) {
    if (encoding === 'utf8') return Buffer.from(value);
    if (encoding === 'utf8-bom') return Buffer.concat([Buffer.from([239, 187, 191]), Buffer.from(value)]);
    const body = Buffer.from(value, 'utf16le');
    return encoding === 'utf16le'
        ? Buffer.concat([Buffer.from([255, 254]), body])
        : Buffer.concat([Buffer.from([254, 255]), body.swap16()]);
}

for (const encoding of ['utf8', 'utf8-bom', 'utf16le', 'utf16be']) {
    test(`README with sparse control characters opens and saves losslessly (${encoding})`, async () => {
        const { api, sandbox, edit } = adapter();
        const original = encoded(source.replaceAll('\n', '\r\n'), encoding);
        const file = new File([original], 'README.md');
        const decoded = await api.decodeFile(file);
        assert.equal(decoded.text, source.replaceAll('\n', '\r\n'));
        let written;
        const handle = { name: file.name, requestPermission: async () => 'granted',
            getFile: async () => file,
            createWritable: async () => ({ write: async blob => { written = Buffer.from(await blob.arrayBuffer()); }, close() {} }) };
        sandbox.canvasSource = { name: file.name, handle };
        api.open(file.name, decoded.text, file, decoded.format);
        assert.equal(await api.save(), true, api.notice);
        assert.deepEqual(written, original, 'Unedited Save must retain every original byte.');
        edit(source + '\nEdited in the canvas.\n');
        assert.equal(await api.save(), true, api.notice);
        assert.deepEqual(written, encoded((source + '\nEdited in the canvas.\n').replaceAll('\n', '\r\n'), encoding));
    });
}

for (const [name, bytes, message] of [
    ['NUL in Markdown', Buffer.from('# Heading\n\nText\0text'), /binary file/],
    ['control-dominated payload', Buffer.from([1, 2, 3, 4, 5, 6, 7, 8]), /binary file/],
    ['single binary byte', Buffer.from([1]), /binary file/],
    ['UTF-16 NUL', encoded('# Heading\n\0', 'utf16le'), /binary file/],
    ['UTF-16 controls', encoded('\u0001\u0002\u0003', 'utf16be'), /binary file/],
    ['malformed UTF-8', Buffer.from([0xc3, 0x28]), /not valid UTF-8/],
    ['truncated UTF-16', Buffer.from([0xff, 0xfe, 65]), /not valid UTF-8/],
    ['UTF-32', Buffer.from([0xff, 0xfe, 0, 0, 65, 0, 0, 0]), /UTF-32/],
]) {
    test(`Still refuses ${name}, regardless of .md extension`, async () => {
        await assert.rejects(adapter().api.decodeFile(new File([bytes], 'README.md')), message);
    });
}

test('Ordinary Unicode Markdown, empty files, and text whitespace remain accepted', async () => {
    for (const text of ['', '# Guía — 日本語 🚀\n', '\t\n\r\f\v']) {
        assert.equal((await adapter().api.decodeFile(new File([text], 'README.MD'))).text, text);
    }
});
