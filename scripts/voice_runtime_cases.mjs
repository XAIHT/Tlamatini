// Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
// Runs the REAL voice_runtime.js (and interaction_speech.js) against a fake speech
// engine and a fake clock, and proves she finishes what she starts:
//   node scripts/voice_runtime_cases.mjs <voice_runtime.js> <interaction_speech.js> [page-lang]
// Exit code 0 only when every case passes. Deterministic: no real time, no audio.
import fs from 'node:fs';
import vm from 'node:vm';

const [, , runtimeFile, speechFile, pageLang = 'en-US'] = process.argv;
const runtimeSource = fs.readFileSync(runtimeFile, 'utf8');
const speechSource = speechFile ? fs.readFileSync(speechFile, 'utf8') : '';
const spanish = pageLang.toLowerCase().startsWith('es');
const VOICES = spanish
    ? [{ name: 'Microsoft Sabina - Spanish (Mexico)', lang: 'es-MX', voiceURI: 'sabina' }]
    : [{ name: 'Microsoft Zira - English (United States)', lang: 'en-US', voiceURI: 'zira' }];

function makeWorld(options = {}) {
    let now = 0, seq = 0;
    const timers = [];
    const setTimeoutF = (fn, ms = 0) => { const id = ++seq; timers.push({ id, at: now + Math.max(0, ms), fn }); return id; };
    const clearTimeoutF = id => { const i = timers.findIndex(t => t.id === id); if (i >= 0) timers.splice(i, 1); };
    const setIntervalF = (fn, ms) => {
        const id = ++seq;
        const tick = () => { fn(); timers.push({ id, at: now + ms, fn: tick }); };
        timers.push({ id, at: now + ms, fn: tick });
        return id;
    };
    const flush = async () => { for (let i = 0; i < 30; i++) await Promise.resolve(); };
    async function advance(ms) {
        const end = now + ms;
        for (;;) {
            await flush();
            timers.sort((a, b) => a.at - b.at || a.id - b.id);
            const next = timers[0];
            if (!next || next.at > end) break;
            timers.shift();
            now = next.at;
            next.fn();
        }
        now = end;
        await flush();
    }
    let voices = options.lateVoices ? [] : VOICES;
    const voiceListeners = [];
    const engine = {
        queue: [], current: null, speaking: false, pending: false, paused: false,
        calls: { pause: 0, cancel: 0, resume: 0, speak: 0 }, finished: [], attempts: {},
        getVoices: () => voices,
        addEventListener(type, fn) { if (type === 'voiceschanged') voiceListeners.push(fn); },
        removeEventListener(type, fn) { const i = voiceListeners.indexOf(fn); if (i >= 0) voiceListeners.splice(i, 1); },
        speak(u) { engine.calls.speak += 1; engine.queue.push(u); engine.next(); },
        cancel() {
            engine.calls.cancel += 1;
            const all = [engine.current, ...engine.queue].filter(Boolean);
            engine.queue = []; engine.current = null; engine.speaking = false;
            all.forEach(u => u.onerror?.({ error: 'canceled' }));
        },
        pause() { engine.calls.pause += 1; engine.paused = true; },
        resume() { engine.calls.resume += 1; engine.paused = false; engine.next(); },
        next() {
            if (engine.current || engine.paused || !engine.queue.length) return;
            const u = engine.queue.shift();
            engine.current = u;
            engine.attempts[u.text] = (engine.attempts[u.text] || 0) + 1;
            (options.behavior || defaultBehavior)(u, engine, api);
        },
        start(u) { if (engine.current !== u) return; engine.speaking = true; u.onstart?.(); },
        end(u) {
            if (engine.current !== u) return;
            engine.current = null; engine.speaking = false; engine.finished.push(u.text); u.onend?.(); engine.next();
        },
        fail(u, error) {
            if (engine.current !== u) return;
            engine.current = null; engine.speaking = false; u.onerror?.({ error }); engine.next();
        }
    };
    function defaultBehavior(u) {
        setTimeoutF(() => engine.start(u), 20);
        setTimeoutF(() => engine.end(u), 20 + u.text.length * 60);   // ~ 16 characters a second
    }
    // A closed page's sentence keeps the host voice busy for its first 5 seconds.
    const host = { calls: [], jobs: {}, busyUntil: options.hostBusy ? 5000 : 0 };
    function respond(data) { return Promise.resolve({ ok: true, json: () => Promise.resolve(data) }); }
    function fetchF(url, init = {}) {
        const body = init.body ? JSON.parse(init.body) : undefined;
        host.calls.push({ url, body, token: init.headers?.['X-CSRFToken'] });
        if (url.endsWith('/speak/')) {
            const id = 'job' + (Object.keys(host.jobs).length + 1);
            host.jobs[id] = { text: body.text, settings: body.settings, reason: body.reason, polls: 0 };
            return respond({ job_id: id, available: true });
        }
        if (url.includes('/status/')) {
            const id = (url.split('job=')[1] || '');
            if (!id) return respond({ state: '', busy: now < host.busyUntil });
            const job = host.jobs[decodeURIComponent(id)];
            job.polls += 1;
            return respond({ state: job.polls >= 3 ? 'done' : 'speaking', busy: job.polls < 3 });
        }
        return respond({});
    }
    const listeners = { window: {}, document: {} };
    const beacons = [], posted = [];
    const storage = new Map();
    const context = {
        console, Promise, Math, JSON, Object, Array, Number, String, Boolean, RegExp, Map, Set, Error, encodeURIComponent, decodeURIComponent,
        queueMicrotask, setTimeout: setTimeoutF, clearTimeout: clearTimeoutF, setInterval: setIntervalF,
        Date: { now: () => now },
        fetch: fetchF,
        localStorage: { getItem: k => storage.has(k) ? storage.get(k) : null, setItem: (k, v) => storage.set(k, String(v)) },
        navigator: { language: pageLang, sendBeacon: (url, body) => { beacons.push({ url, body }); return true; } },
        FormData: class { constructor() { this.fields = {}; } append(k, v) { this.fields[k] = v; } },
        BroadcastChannel: class { constructor() { this.onmessage = null; } postMessage(m) { posted.push(m); } },
        CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init?.detail; } },
        AbortController,
        SpeechSynthesisUtterance: class { constructor(text) { this.text = text; } },
        speechSynthesis: engine,
        document: {
            // Both editions' cookies are present on one computer: each must send its own.
            cookie: spanish ? 'csrftoken=english-token; tlm_csrf_es_mx=test-token'
                : 'tlm_csrf_es_mx=spanish-token; csrftoken=test-token',
            hidden: false, documentElement: { lang: pageLang },
            getElementById: () => null,
            addEventListener(type, fn) { (listeners.document[type] ||= []).push(fn); },
            createElement: () => ({ append() {}, setAttribute() {}, addEventListener() {}, remove() {} }),
            body: { append() {} }
        },
        addEventListener(type, fn) { (listeners.window[type] ||= []).push(fn); },
        removeEventListener() {},
        dispatchEvent(event) { (listeners.window[event.type] || []).forEach(fn => fn(event)); return true; }
    };
    context.window = context;
    vm.createContext(context);
    vm.runInContext(runtimeSource, context, { filename: runtimeFile });
    if (speechSource) vm.runInContext(speechSource, context, { filename: speechFile });
    const api = {
        context, engine, host, beacons, posted, advance, setTimeout: setTimeoutF,
        get now() { return now; },
        voice: context.window.TLM_VOICE,
        windowEvent(type, extra = {}) { (listeners.window[type] || []).forEach(fn => fn({ type, defaultPrevented: false, ...extra })); },
        documentEvent(type) { (listeners.document[type] || []).forEach(fn => fn({ type })); },
        provideVoices() { voices = VOICES; voiceListeners.slice().forEach(fn => fn()); }
    };
    return api;
}

const text = n => Array.from({ length: n }, (_, i) => `Sentence number ${i + 1} of a long answer that she must finish no matter what happens on the page.`).join(' ');
const results = [];
async function check(name, body) {
    try { await body(); results.push({ name, ok: true }); }
    catch (error) { results.push({ name, ok: false, error: error.message }); }
}
function assert(condition, message) { if (!condition) throw new Error(message); }
async function settle(promise, world, ms) {
    let status = 'pending';
    promise.then(value => { status = value; });
    await world.advance(ms);
    return status;
}

await check('a message longer than 100 seconds is spoken to the end', async () => {
    const w = makeWorld();
    await w.advance(1000);
    const status = await settle(w.voice.speak(text(80), { queue: true }), w, 700000);
    assert(status === 'spoken', 'status ' + status);
    assert(w.engine.finished.join('').replace(/\s+/g, ' ').trim() === text(80), 'not every chunk was spoken');
    assert(w.engine.calls.cancel === 0, 'the engine was cancelled');
});

await check('a hidden or covered page never pauses her', async () => {
    const w = makeWorld();
    await w.advance(1000);
    const promise = w.voice.speak(text(10), { queue: true });
    await w.advance(5000);
    w.context.document.hidden = true;
    w.documentEvent('visibilitychange');
    w.windowEvent('blur');
    const status = await settle(promise, w, 200000);
    assert(w.engine.calls.pause === 0, 'speechSynthesis.pause() was called ' + w.engine.calls.pause + ' time(s)');
    assert(status === 'spoken', 'status ' + status);
});

await check('the processing line waits behind a long answer instead of being dropped', async () => {
    const w = makeWorld();
    await w.advance(1000);
    const first = w.voice.speak(text(8), { queue: true });
    const ack = w.voice.speak("I'm working on your request, Angela. Please wait a moment.", { queue: true });
    const done = w.voice.speak("I've finished your request, Angela.", { queue: true });
    let a = '', b = '', c = '';
    first.then(v => { a = v; }); ack.then(v => { b = v; }); done.then(v => { c = v; });
    await w.advance(300000);
    assert(a === 'spoken' && b === 'spoken' && c === 'spoken', `statuses ${a}/${b}/${c}`);
    assert(w.engine.finished.at(-1).startsWith("I've finished"), 'order lost');
});

await check('a chunk interrupted by another page is spoken again', async () => {
    let interrupted = false;
    const w = makeWorld({ behavior(u, engine, api) {
        api.setTimeout(() => engine.start(u), 20);
        if (!interrupted && u.text.includes('number 3 ')) {
            interrupted = true;
            api.setTimeout(() => engine.fail(u, 'interrupted'), 500);
            return;
        }
        api.setTimeout(() => engine.end(u), 20 + u.text.length * 60);
    } });
    await w.advance(1000);
    const status = await settle(w.voice.speak(text(6), { queue: true }), w, 200000);
    assert(status === 'spoken', 'status ' + status);
    assert(w.engine.finished.join('').replace(/\s+/g, ' ').trim() === text(6), 'the interrupted chunk was lost');
});

await check('a chunk the engine silently drops is retried', async () => {
    let dropped = false;
    const w = makeWorld({ behavior(u, engine, api) {
        if (!dropped) { dropped = true; engine.current = null; return; }   // accepted, never started
        api.setTimeout(() => engine.start(u), 20);
        api.setTimeout(() => engine.end(u), 20 + u.text.length * 60);
    } });
    await w.advance(1000);
    const status = await settle(w.voice.speak(text(3), { queue: true }), w, 200000);
    assert(status === 'spoken', 'status ' + status);
    assert(w.engine.finished.join('').replace(/\s+/g, ' ').trim() === text(3), 'dropped chunk not recovered');
});

await check('a browser that keeps failing hands the rest to the host voice', async () => {
    let good = 2;
    const w = makeWorld({ behavior(u, engine, api) {
        api.setTimeout(() => engine.start(u), 20);
        if (good > 0) { good -= 1; api.setTimeout(() => engine.end(u), 20 + u.text.length * 60); return; }
        api.setTimeout(() => engine.fail(u, 'synthesis-failed'), 100);
    } });
    await w.advance(1000);
    const status = await settle(w.voice.speak(text(6), { queue: true }), w, 200000);
    const job = Object.values(w.host.jobs)[0];
    assert(status === 'spoken', 'status ' + status);
    assert(job, 'nothing reached the host voice');
    const spoken = (w.engine.finished.join('') + job.text).replace(/\s+/g, ' ').trim();
    assert(spoken === text(6), 'host text does not continue where the browser stopped');
    assert(job.settings.voice === VOICES[0].name, 'host voice did not get the user voice');
    assert(w.host.calls.filter(c => c.url.endsWith('/speak/')).every(c => c.token === 'test-token'),
        'the host call carried the wrong security token');
});

await check('a page with no user gesture yet speaks through the host voice', async () => {
    const w = makeWorld({ behavior(u, engine, api) { api.setTimeout(() => engine.fail(u, 'not-allowed'), 10); } });
    await w.advance(1000);
    const status = await settle(w.voice.speak('Hello Angela.', { queue: true }), w, 20000);
    assert(status === 'spoken', 'status ' + status);
    assert(Object.values(w.host.jobs)[0]?.text === 'Hello Angela.', 'host did not speak it');
});

await check('voices that load late are waited for', async () => {
    const w = makeWorld({ lateVoices: true });
    await w.advance(1000);
    const promise = w.voice.speak('Ready, Angela.', { queue: true });
    await w.advance(500);
    w.provideVoices();
    const status = await settle(promise, w, 20000);
    assert(status === 'spoken', 'status ' + status);
    assert(w.engine.finished.join('').trim() === 'Ready, Angela.', 'not spoken by the browser');
});

await check('closing the page mid-sentence hands the rest to the host voice', async () => {
    const w = makeWorld();
    await w.advance(1000);
    w.voice.speak(text(6), { queue: true });
    w.voice.speak("I've finished your request, Angela.", { queue: true });
    await w.advance(25000);
    w.windowEvent('pagehide');
    assert(w.beacons.length === 1, 'no beacon');
    const payload = JSON.parse(w.beacons[0].body.fields.payload);
    assert(w.beacons[0].body.fields.csrfmiddlewaretoken === 'test-token', 'no CSRF token');
    assert(payload.text.endsWith("I've finished your request, Angela."), 'queued line missing');
    assert(!payload.text.startsWith('Sentence number 1 '), 'already-spoken text repeated');
    assert(payload.settings.voice === VOICES[0].name, 'voice setting missing');
});

await check('Escape that closed a dialog does not stop her; a free Escape does', async () => {
    const w = makeWorld();
    await w.advance(1000);
    let status = 'pending';
    w.voice.speak(text(4), { queue: true }).then(v => { status = v; });
    await w.advance(3000);
    w.windowEvent('keydown', { key: 'Escape', defaultPrevented: true });
    await w.advance(100);
    assert(status === 'pending', 'a dialog Escape stopped her');
    w.windowEvent('keydown', { key: 'Escape' });
    await w.advance(100);
    assert(status === 'cancelled', 'a free Escape did not stop her');
    assert(w.posted.some(m => m.type === 'stop'), 'other pages were not told to stop');
});

await check('a page that opens while the host is speaking queues behind it', async () => {
    const w = makeWorld({ hostBusy: true });
    const status = await settle(w.voice.speak('Second line.', { queue: true }), w, 20000);
    assert(status === 'spoken', 'status ' + status);
    assert(Object.values(w.host.jobs)[0]?.text === 'Second line.', 'it spoke over the host voice');
    assert(w.engine.calls.speak === 0, 'the browser spoke at the same time');
});

await check('Silent mode still mutes her', async () => {
    const w = makeWorld();
    await w.advance(1000);
    w.voice.setSilent(true);
    const status = await settle(w.voice.speak('Should not be heard.', { queue: true }), w, 5000);
    assert(status === 'muted', 'status ' + status);
    assert(w.engine.calls.speak === 0 && !Object.keys(w.host.jobs).length, 'something spoke');
});

const failed = results.filter(r => !r.ok);
for (const r of results) console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : ' -> ' + r.error));
console.log(`voice_runtime_cases (${pageLang}): ${results.length - failed.length}/${results.length} passed`);
process.exit(failed.length ? 1 : 0);
