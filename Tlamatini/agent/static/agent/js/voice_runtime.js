/* Tlamatini Author Banner — Angela López Mendoza */
/* Shared speech lifecycle for chat, editor tutoring and the two flow panels. */
(() => {
    'use strict';
    if (window.TLM_VOICE) return;
    const FEMALE = /female|zira|jenny|aria|michelle|clara|nanami|sara|hazel|heera|catherine|hedda|elsa|paulina|helena|laura|isabel|sabina|woman|girl|monica|google us english|google uk english female|samantha|victoria|karen|tessa|fiona|moira|serena|allison|ava|susan|zoe|nora|mia|jess|tara|leah/i;
    const MALE = /\bmale\b|david|mark|guy|ryan|george|james|richard|paul\b|thomas|daniel|alex\b|fred|diego|jorge|pablo|\bman\b|\bboy\b/i;
    const defaults = { mode: 'notify', voiceURI: '', volume: 100, rate: 1, pitch: 1.05 };
    let memory = { ...defaults }, active = null, listening = false;
    const queue = [];
    function loadSettings() {
        try { memory = { ...defaults, ...JSON.parse(localStorage.getItem('tlm_voice_settings') || '{}') }; }
        catch { /* Keep the usable in-memory settings. */ }
        return { ...memory };
    }
    function saveSettings(value) {
        memory = { ...defaults, ...value };
        try { localStorage.setItem('tlm_voice_settings', JSON.stringify(memory)); } catch { /* This tab retains the choice. */ }
        if (memory.mode === 'silent') stop('muted');
        window.dispatchEvent(new CustomEvent('tlm:voice-settings'));
    }
    function femaleVoices() {
        return (window.speechSynthesis?.getVoices() || []).filter(voice => FEMALE.test(voice.name) && !MALE.test(voice.name));
    }
    function pickVoice(settings = loadSettings()) {
        const voices = femaleVoices();
        return voices.find(voice => voice.voiceURI === settings.voiceURI)
            || voices.find(voice => /zira|jenny|aria|samantha|google us english|hazel/i.test(voice.name)) || voices[0] || null;
    }
    function finish(item, status) {
        if (item.done) return;
        item.done = true;
        clearTimeout(item.timer);
        item.signal?.removeEventListener('abort', item.abort);
        if (active === item) active = null;
        item.resolve(status);
        queueMicrotask(pump);
    }
    function stop(reason = 'cancelled') {
        const pending = queue.splice(0);
        if (active) pending.unshift(active);
        pending.forEach(item => finish(item, reason));
        try { window.speechSynthesis?.cancel(); } catch { /* Speech may be unavailable. */ }
        window.dispatchEvent(new CustomEvent('tlm:voice-stopped', { detail: reason }));
    }
    function pump() {
        if (active || !queue.length) return;
        const item = queue.shift();
        active = item;
        const settings = item.settings || loadSettings();
        if (item.signal?.aborted) return finish(item, 'cancelled');
        if (listening || settings.mode === 'silent' && !item.force || Number(settings.volume) === 0) return finish(item, 'muted');
        const voice = pickVoice(settings);
        if (!voice || !window.speechSynthesis || !window.SpeechSynthesisUtterance) return finish(item, 'unavailable');
        // Queue a chunk only after the previous chunk ends. Cancel never leaves stale chunks.
        const pieces = item.text.match(/[\s\S]{1,170}(?:\s|$)|[\s\S]{1,170}/g) || [];
        let index = 0;
        item.timer = setTimeout(() => { stop('unavailable'); }, 100000);
        function next() {
            if (item.done) return;
            if (index >= pieces.length) return finish(item, 'spoken');
            const utterance = new SpeechSynthesisUtterance(pieces[index++]);
            utterance.voice = voice; utterance.lang = voice.lang;
            utterance.volume = Math.max(0, Math.min(1, settings.volume / 100));
            utterance.rate = Math.max(.5, Math.min(2, settings.rate));
            utterance.pitch = Math.max(0, Math.min(2, settings.pitch));
            utterance.onend = next;
            utterance.onerror = () => finish(item, 'unavailable');
            try { window.speechSynthesis.speak(utterance); } catch { finish(item, 'unavailable'); }
        }
        next();
    }
    function speak(text, options = {}) {
        text = String(text || '').trim();
        if (!text) return Promise.resolve('spoken');
        if (!options.queue && !active?.interaction) stop();
        return new Promise(resolve => {
            const item = { ...options, text, resolve, done: false };
            item.abort = () => {
                if (active === item) stop();
                else { const index = queue.indexOf(item); if (index >= 0) queue.splice(index, 1); finish(item, 'cancelled'); }
            };
            item.signal?.addEventListener('abort', item.abort, { once: true });
            queue.push(item);
            pump();
        });
    }
    function setSilent(on) { const settings = loadSettings(); settings.mode = on ? 'silent' : 'notify'; saveSettings(settings); return settings.mode; }
    // Speech begins only from a user-enabled feature. A click can resume a paused browser engine.
    function prime() { try { window.speechSynthesis?.resume(); } catch { /* Optional browser capability. */ } }
    window.TLM_VOICE = { speak, stop, prime, loadSettings, saveSettings, femaleVoices, pickVoice, setSilent,
        notify: () => speak("I've finished your request."),
        setListening: on => { listening = !!on; if (on) stop('muted'); },
        get listening() { return listening; } };
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') stop();
        if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === 'm') {
            event.preventDefault(); event.stopImmediatePropagation(); setSilent(loadSettings().mode !== 'silent');
        }
    }, true);
    window.addEventListener('storage', event => { if (event.key === 'tlm_voice_settings' && loadSettings().mode === 'silent') stop('muted'); });
    document.addEventListener('click', prime, { once: true });
})();
