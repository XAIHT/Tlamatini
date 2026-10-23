/* Tlamatini Author Banner — Angela López Mendoza */
/* CodeMirror extension: field guidance, optional ghost text and observable typing. */
import { Annotation, StateEffect, StateField, Prec, Transaction } from '@codemirror/state';
import { Decoration, EditorView, WidgetType, keymap } from '@codemirror/view';
import { isolateHistory } from '@codemirror/commands';

export const editOrigin = Annotation.define();
const guideEffect = StateEffect.define();

class Ghost extends WidgetType {
    constructor(text) { super(); this.text = text; }
    eq(other) { return this.text === other.text; }
    toDOM() {
        const node = document.createElement('span');
        node.className = 'tlm-interactor-ghost';
        node.textContent = this.text;
        node.setAttribute('aria-hidden', 'true');
        return node;
    }
}

function candidate(state, guide) {
    if (!guide?.enabled || guide.composing) return null;
    const selection = state.selection.main;
    if (!selection.empty || selection.head !== guide.end) return null;
    const prefix = state.doc.sliceString(guide.start, guide.end);
    if (!prefix || prefix === guide.dismissedPrefix) return null;
    const choice = guide.choices.find(item => item.text.startsWith(prefix) && item.text !== prefix);
    return choice ? { ...choice, suffix: choice.text.slice(prefix.length) } : null;
}

const field = StateField.define({
    create: () => null,
    update(guide, transaction) {
        if (guide && transaction.docChanged) {
            let outside = false;
            transaction.changes.iterChanges((from, to) => {
                if (from < guide.start || to > guide.end) outside = true;
            });
            guide = outside ? null : { ...guide, dismissedPrefix: null,
                start: transaction.changes.mapPos(guide.start, -1),
                end: transaction.changes.mapPos(guide.end, 1) };
        }
        for (const effect of transaction.effects) if (effect.is(guideEffect)) guide = effect.value;
        return guide;
    },
    provide: source => EditorView.decorations.compute([source, 'selection', 'doc'], state => {
        const guide = state.field(source);
        if (!guide) return Decoration.none;
        const ranges = [];
        if (guide.end > guide.start) ranges.push(Decoration.mark({ class: 'tlm-interactor-field' }).range(guide.start, guide.end));
        const suggestion = candidate(state, guide);
        if (suggestion && guide.ghost !== false) ranges.push(Decoration.widget({ widget: new Ghost(suggestion.suffix), side: 1 }).range(guide.end));
        else if (guide.enabled && guide.ghost !== false && guide.start === guide.end) ranges.push(Decoration.widget({ widget: new Ghost('‹your choice›'), side: 1 }).range(guide.end));
        return Decoration.set(ranges, true);
    }),
});

export function createInteractorEditor(getView) {
    function guide() { return getView()?.state.field(field, false) || null; }
    function setGuide(value) {
        getView()?.dispatch({ effects: guideEffect.of(value), annotations: editOrigin.of('interactor') });
    }
    function accept(text = null, word = false) {
        const view = getView(), current = guide();
        if (!view || !current || view.composing) return false;
        const option = candidate(view.state, current);
        const prefix = view.state.doc.sliceString(current.start, current.end);
        let suffix = text ? (text.startsWith(prefix) ? text.slice(prefix.length) : '') : option?.suffix;
        if (!suffix || !view.state.selection.main.empty || view.state.selection.main.head !== current.end) return false;
        if (word) suffix = suffix.match(/^\s*\S+\s*/)?.[0] || suffix;
        view.dispatch({ changes: { from: current.end, insert: suffix },
            selection: { anchor: current.end + suffix.length }, scrollIntoView: true,
            annotations: [editOrigin.of('completion'), isolateHistory.of('full')] });
        view.focus();
        return true;
    }
    function takeover() {
        window.dispatchEvent(new CustomEvent('tlm:editor-takeover'));
        return false;
    }
    const extensions = [field,
        Prec.highest(keymap.of([
            { key: 'Tab', run: () => accept() },
            { key: 'Mod-ArrowRight', run: () => accept(null, true) },
            { key: 'Escape', run: view => {
                takeover();
                const current = guide();
                if (!current) return false;
                setGuide({ ...current, dismissedPrefix: view.state.doc.sliceString(current.start, current.end) });
                return true;
            } },
        ])),
        EditorView.domEventHandlers({
            beforeinput: takeover, paste: takeover, drop: takeover, pointerdown: takeover,
            keydown: event => {
                if (!['Shift', 'Control', 'Alt', 'Meta'].includes(event.key)) takeover();
                return false;
            },
            compositionstart: () => { takeover(); const current = guide(); if (current) setGuide({ ...current, composing: true }); return false; },
            compositionend: () => { const current = guide(); if (current) setGuide({ ...current, composing: false }); return false; },
        }),
    ];

    async function type({ start, end, text, typing_wpm, preferences = {} }, signal, waitForView = async () => {}) {
        const view = getView();
        if (!view || view.composing) throw new Error('Finish the current input composition before Tlamatini types.');
        setGuide(null);
        const delay = Math.max(30, 60000 / (5 * typing_wpm));
        const stepTime = Date.now();
        let cursor = start, first = true;
        let following = preferences.follow_typing !== false;
        const suspendFollowing = () => { following = false; };
        view.scrollDOM.addEventListener('wheel', suspendFollowing, { passive: true });
        view.scrollDOM.addEventListener('touchstart', suspendFollowing, { passive: true });
        view.focus();
        try {
            for (const char of text) {
                await waitForView();
                if (signal.aborted || view !== getView()) throw new Error('Typing stopped; your editor content is kept.');
                if (!view.dom.getClientRects().length) {
                    takeover();
                    throw new Error('Typing stopped because the source editor is hidden. Your content is kept.');
                }
                view.dispatch({ changes: { from: cursor, to: first ? end : cursor, insert: char },
                    selection: { anchor: cursor + char.length }, scrollIntoView: following,
                    annotations: [editOrigin.of('interactor'), Transaction.time.of(stepTime), ...(first ? [isolateHistory.of('before')] : [])],
                    userEvent: 'input.type.interactor' });
                first = false;
                cursor += char.length;
                await new Promise(resolve => {
                    const finish = () => { clearTimeout(timer); signal.removeEventListener('abort', finish); resolve(); };
                    const timer = setTimeout(finish, delay);
                    signal.addEventListener('abort', finish, { once: true });
                });
            }
            if (signal.aborted) throw new Error('Typing stopped; your editor content is kept.');
        } finally {
            view.scrollDOM.removeEventListener('wheel', suspendFollowing);
            view.scrollDOM.removeEventListener('touchstart', suspendFollowing);
            if (view === getView()) view.dispatch({ annotations: [editOrigin.of('interactor'), isolateHistory.of('after')] });
        }
    }

    return { extensions, guide, setGuide, type, accept,
        suggestion: () => getView() ? candidate(getView().state, guide()) : null,
        select: (start, end) => {
            const view = getView();
            view?.dispatch({ selection: { anchor: start, head: end }, scrollIntoView: true,
                annotations: editOrigin.of('interactor') });
            view?.focus();
        },
    };
}
