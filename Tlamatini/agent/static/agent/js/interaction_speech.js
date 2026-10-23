/* Tlamatini Author Banner — Angela López Mendoza */
(() => {
    'use strict';
    const jobs = new Map();
    function notice(message, parent = document.body) {
        const box = document.createElement('div'); box.className = 'tlm-narration-notice'; box.setAttribute('role', 'status');
        const text = document.createElement('span'); text.textContent = message; box.append(text); parent.append(box);
        return box;
    }
    async function narrate({ id, text, wait = false, signal, terminal = '', deadline = Date.now() + 120000, preview = false }) {
        if (jobs.has(id)) return 'cancel';
        const controller = new AbortController();
        const abort = () => controller.abort();
        signal?.addEventListener('abort', abort, { once: true });
        if (signal?.aborted) abort();
        const timer = setTimeout(abort, Math.max(0, deadline - Date.now()));
        const job = { controller, terminal }; jobs.set(id, job);
        let box;
        try {
            const status = await window.TLM_VOICE.speak(text, { queue: true, interaction: true, signal: controller.signal });
            if (controller.signal.aborted || status === 'cancelled') return 'cancel';
            if (status === 'spoken') return 'spoken';
            if (status === 'muted') return 'skip';
            if (!wait || preview) {
                window.dispatchEvent(new CustomEvent('tlm:narration-unavailable'));
                return 'skip';
            }
            box = notice('Voice is unavailable. This step is paused before typing.');
            return await new Promise(resolve => {
                const settle = value => { controller.signal.removeEventListener('abort', cancel); resolve(value); };
                const cancel = () => settle('cancel');
                for (const [label, result] of [['Continue without voice', 'skip'], ['Stop this step', 'cancel']]) {
                    const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
                    button.addEventListener('click', () => settle(result), { once: true }); box.append(button);
                }
                controller.signal.addEventListener('abort', cancel, { once: true });
                if (controller.signal.aborted) cancel();
            });
        } finally {
            clearTimeout(timer); signal?.removeEventListener('abort', abort); jobs.delete(id); box?.remove();
        }
    }
    function cancel({ id, terminal } = {}) {
        for (const [key, job] of jobs) if ((!id && !terminal) || key === id || terminal && job.terminal === terminal) job.controller.abort();
    }
    async function around(settings, text, id, signal, action, waitForView = async () => {}) {
        let speech;
        const start = () => narrate({ id, text, signal, wait: settings.narration_when === 'before' && settings.narration_wait });
        if (settings.narrate_editor && settings.narration_when !== 'after') {
            speech = start();
            if (settings.narration_when === 'before' && settings.narration_wait && await speech === 'cancel') throw Object.assign(new Error('Narration stopped; the step was cancelled.'), { status: 'aborted' });
        }
        try {
            await waitForView();
            if (signal.aborted) throw Object.assign(new Error('The step was cancelled.'), { status: 'aborted' });
            await action();
            if (settings.narrate_editor && settings.narration_when === 'after') speech = start();
            // Keep cancellation connected until this segment's narration is finished.
            if (speech) await speech;
        } catch (error) { cancel({ id }); throw error; }
    }
    window.TlamatiniInteractionSpeech = { narrate, cancel, around };
    document.addEventListener('visibilitychange', () => {
        try { if (document.hidden) window.speechSynthesis?.pause(); else window.speechSynthesis?.resume(); }
        catch { /* The bounded speech lifecycle reports unavailable engines. */ }
    });
})();
