/* Tlamatini Author Banner — Angela López Mendoza */
/* The canvas's locally bundled text editor. No network or filesystem access. */
import { basicSetup } from 'codemirror';
import { Compartment, EditorState, Prec } from '@codemirror/state';
import { EditorView, keymap } from '@codemirror/view';
import { undo, redo, undoDepth, redoDepth, indentMore, indentLess } from '@codemirror/commands';
import { HighlightStyle, StreamLanguage, syntaxHighlighting } from '@codemirror/language';
import { openSearchPanel } from '@codemirror/search';
import { tags } from '@lezer/highlight';
import { cpp } from '@codemirror/lang-cpp';
import { css } from '@codemirror/lang-css';
import { html } from '@codemirror/lang-html';
import { java } from '@codemirror/lang-java';
import { javascript } from '@codemirror/lang-javascript';
import { json } from '@codemirror/lang-json';
import { markdown } from '@codemirror/lang-markdown';
import { python } from '@codemirror/lang-python';
import { rust } from '@codemirror/lang-rust';
import { sql } from '@codemirror/lang-sql';
import { xml } from '@codemirror/lang-xml';
import { yaml } from '@codemirror/lang-yaml';
import { powerShell } from '@codemirror/legacy-modes/mode/powershell';
import { shell } from '@codemirror/legacy-modes/mode/shell';
import { toml } from '@codemirror/legacy-modes/mode/toml';
import { go } from '@codemirror/legacy-modes/mode/go';
import { dockerFile } from '@codemirror/legacy-modes/mode/dockerfile';
import { createInteractorEditor, editOrigin } from '../Tlamatini/agent/interactor/editor.mjs';

const language = new Compartment();
const editing = new Compartment();
const wrapping = new Compartment();
const appearance = new Compartment();
let appearanceSettings = {};
let view = null;
let onChange = null;
let readOnly = false;
let wrap = false;
let currentName = '';
let currentText = '';
let currentLanguage = 'Plain text';
function newDocumentId() {
    return Array.from(window.crypto.getRandomValues(new Uint8Array(16)), byte => byte.toString(16).padStart(2, '0')).join('');
}
let documentId = newDocumentId();
let revision = 0;
const interactor = createInteractorEditor(() => view);

function announce(detail) {
    window.dispatchEvent(new CustomEvent('tlm:editor-state', { detail }));
}

function inspect() {
    const selection = view?.state.selection.main;
    return { document_id: documentId, revision, active: !!view && !readOnly,
        filename: currentName, language: currentLanguage, text: currentText,
        selection: { from: selection?.from || 0, to: selection?.to || 0 },
        guide: interactor.guide() };
}

const theme = EditorView.theme({
    '&': { height: '100%', color: '#dce4f3', backgroundColor: '#171c24', fontSize: '13px' },
    '&.cm-focused': { outline: 'none' },
    '.cm-scroller': { overflow: 'auto', fontFamily: 'Consolas, "Cascadia Code", monospace', lineHeight: '1.55' },
    '.cm-content': { padding: '10px 0', caretColor: '#8ae0cf' },
    '.cm-line': { padding: '0 12px' },
    '.cm-gutters': { backgroundColor: '#1e2530', color: '#8c9db6', borderRight: '1px solid #354152' },
    '.cm-activeLineGutter': { backgroundColor: '#2a3746', color: '#e8f6ff' },
    '.cm-activeLine': { backgroundColor: '#55bbaa0a' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#8ae0cf' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': { backgroundColor: '#345775' },
    '.cm-matchingBracket': { backgroundColor: '#55bbaa33', outline: '1px solid #55bbaa66' },
    '.cm-searchMatch': { backgroundColor: '#b58a3244', outline: '1px solid #bc984b' },
    '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: '#55bbaa55' },
    '.cm-panels': { backgroundColor: '#242d3a', color: '#e1e9f7' },
    '.cm-panels.cm-panels-bottom': { borderTop: '1px solid #465367' },
    '.cm-textfield': { backgroundColor: '#171c24', border: '1px solid #56677e', color: '#e1e9f7', borderRadius: '4px' },
    '.cm-button': { backgroundImage: 'none', backgroundColor: '#344354', border: '1px solid #62758b', color: '#edf5ff', borderRadius: '4px' },
    '.cm-tooltip': { backgroundColor: '#242d3a', border: '1px solid #56677e', color: '#e1e9f7' },
    '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: '#305a56', color: '#ffffff' },
}, { dark: true });

const highlighting = HighlightStyle.define([
    { tag: [tags.keyword, tags.modifier, tags.operatorKeyword], color: '#c5a6f7' },
    { tag: [tags.string, tags.special(tags.string)], color: '#c1d98b' },
    { tag: [tags.number, tags.bool, tags.null], color: '#f2bc7a' },
    { tag: [tags.comment, tags.meta], color: '#91a1b7' },
    { tag: [tags.function(tags.variableName), tags.function(tags.propertyName)], color: '#82cfec' },
    { tag: [tags.typeName, tags.className, tags.tagName], color: '#8cdbcb' },
    { tag: [tags.attributeName, tags.propertyName], color: '#ddd3ad' },
    { tag: tags.heading, color: '#8cdbcb', fontWeight: 'bold' },
    { tag: tags.link, color: '#82cfec', textDecoration: 'underline' },
    { tag: tags.invalid, color: '#ff9f9f' },
]);

function fileLanguage(filename) {
    const name = filename.split(/[\\/]/).pop().toLowerCase();
    const ext = name.includes('.') ? name.slice(name.lastIndexOf('.') + 1) : '';
    if (['js', 'mjs', 'cjs', 'jsx'].includes(ext)) return [javascript({ jsx: ext === 'jsx' }), 'JavaScript'];
    if (['ts', 'mts', 'cts', 'tsx'].includes(ext)) return [javascript({ typescript: true, jsx: ext === 'tsx' }), 'TypeScript'];
    if (['py', 'pyw', 'pyi'].includes(ext)) return [python(), 'Python'];
    if (ext === 'rs') return [rust(), 'Rust'];
    if (['c', 'h', 'cc', 'cpp', 'cxx', 'hpp', 'hh', 'hxx', 'ino', 'cu', 'cuh'].includes(ext)) return [cpp(), 'C / C++'];
    if (ext === 'java') return [java(), 'Java'];
    if (['html', 'htm', 'xhtml'].includes(ext)) return [html(), 'HTML'];
    if (['xml', 'svg', 'xsl', 'xslt', 'csproj', 'vbproj', 'vcxproj', 'pom'].includes(ext)) return [xml(), 'XML'];
    if (ext === 'css') return [css(), 'CSS'];
    if (ext === 'json') return [json(), 'JSON'];
    if (['md', 'markdown'].includes(ext)) return [markdown(), 'Markdown'];
    if (['yaml', 'yml'].includes(ext)) return [yaml(), 'YAML'];
    if (ext === 'sql') return [sql(), 'SQL'];
    if (['ps1', 'psm1', 'psd1'].includes(ext)) return [StreamLanguage.define(powerShell), 'PowerShell'];
    if (['sh', 'bash', 'zsh'].includes(ext) || ['.bashrc', '.zshrc', '.profile'].includes(name)) return [StreamLanguage.define(shell), 'Shell'];
    if (ext === 'toml') return [StreamLanguage.define(toml), 'TOML'];
    if (ext === 'go') return [StreamLanguage.define(go), 'Go'];
    if (name === 'dockerfile' || name.startsWith('dockerfile.') || ext === 'dockerfile') return [StreamLanguage.define(dockerFile), 'Dockerfile'];
    return [[], 'Plain text'];
}

function historyState() {
    return { undo: view ? undoDepth(view.state) : 0, redo: view ? redoDepth(view.state) : 0 };
}

function saveCommand(saveAs) {
    return editor => {
        editor.dom.dispatchEvent(new CustomEvent('tlm:canvas-save', { bubbles: true, detail: { saveAs } }));
        return true;
    };
}

function createState(content, filename) {
    const [support, label] = fileLanguage(filename);
    currentLanguage = label;
    return EditorState.create({
        doc: content,
        extensions: [
            interactor.extensions,
            basicSetup, theme, syntaxHighlighting(highlighting),
            language.of(support),
            editing.of([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]),
            wrapping.of(wrap ? EditorView.lineWrapping : []),
            Prec.highest(appearance.of(appearanceExtension())),
            EditorState.tabSize.of(4),
            EditorView.contentAttributes.of({ 'aria-label': 'File source editor', spellcheck: 'false' }),
            // Tab keeps its native focus-navigation behavior; Ctrl+[ / Ctrl+]
            // indent with the default CodeMirror keymap, without a keyboard trap.
            Prec.highest(keymap.of([
                { key: 'Mod-s', run: saveCommand(false), preventDefault: true },
                { key: 'Mod-Shift-s', run: saveCommand(true), preventDefault: true },
            ])),
            EditorView.updateListener.of(update => {
                if (update.docChanged) { currentText = update.state.doc.toString(); revision++; }
                if (update.docChanged || update.selectionSet) onChange?.(currentText, historyState());
                announce({ docChanged: update.docChanged, selectionSet: update.selectionSet,
                    origin: update.transactions.find(transaction => transaction.annotation(editOrigin))?.annotation(editOrigin) || 'user' });
            }),
        ],
    });
}

function destroy() {
    view?.destroy();
    view = null;
    onChange = null;
    currentName = '';
    currentText = '';
    currentLanguage = 'Plain text';
    documentId = newDocumentId();
    revision = 0;
    announce({ origin: 'load', docChanged: true });
}

function mount(parent, content, filename, changed) {
    destroy();
    currentName = filename;
    onChange = typeof changed === 'function' ? changed : null;
    view = new EditorView({ parent, state: createState(content, filename) });
    currentText = view.state.doc.toString();
    parent.classList.add('tlm-source-editor');
    announce({ origin: 'load', docChanged: true });
    return window.TlamatiniTextEditor;
}

function setDocument(content, filename) {
    if (!view) return;
    currentName = filename;
    documentId = newDocumentId();
    revision = 0;
    view.setState(createState(content, filename));
    currentText = view.state.doc.toString();
    view.scrollDOM.scrollTop = view.scrollDOM.scrollLeft = 0;
    announce({ origin: 'load', docChanged: true });
}

function command(action) {
    if (!view || readOnly) return false;
    const changed = action(view);
    view.focus();
    return changed;
}

function setFilename(filename) {
    currentName = filename;
    const [support, label] = fileLanguage(filename);
    currentLanguage = label;
    view?.dispatch({ effects: language.reconfigure(support) });
}

function find() {
    if (view) openSearchPanel(view);
}

function appearanceExtension() {
    return EditorView.theme({ '&': { fontSize: `${appearanceSettings.editor_font || 13}px` },
        '.cm-lineNumbers': { display: appearanceSettings.line_numbers === false ? 'none !important' : '' } });
}

function configureAppearance(settings) {
    appearanceSettings = settings;
    view?.dispatch({ effects: appearance.reconfigure(appearanceExtension()) });
}

window.TlamatiniTextEditor = {
    configureAppearance,
    mount, setDocument, destroy, historyState,
    inspect, interactor,
    getText: () => view?.state.doc.toString() || '',
    undo: () => command(undo), redo: () => command(redo),
    indent: () => command(indentMore), outdent: () => command(indentLess),
    find, search: find,
    focus: () => view?.focus(),
    requestMeasure: () => view?.requestMeasure(),
    setReadOnly: value => {
        readOnly = !!value;
        view?.dispatch({ effects: editing.reconfigure([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]) });
    },
    setWrap: value => {
        wrap = !!value;
        view?.dispatch({ effects: wrapping.reconfigure(wrap ? EditorView.lineWrapping : []) });
    },
    setFilename, rename: setFilename,
    snapshot: () => view ? { top: view.scrollDOM.scrollTop, left: view.scrollDOM.scrollLeft } : null,
    restore: position => {
        if (view && position) { view.scrollDOM.scrollTop = position.top; view.scrollDOM.scrollLeft = position.left; }
    },
    get language() { return currentLanguage; },
    get filename() { return currentName; },
    get active() { return view !== null; },
};
