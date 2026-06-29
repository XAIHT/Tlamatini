/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Crafted with heart by  Angela   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// ============================================================
// chat_page_runtime_poller.js
// Polls /agent/check_chat_runtimes_status/ from the chat page
// (agent_page.html) and surfaces Asker A/B dialogs and Notifier
// toasts via shared-runtime-dialogs.js for chat-launched agents.
//
// Loaded ONLY by agent_page.html. The ACP page has its own poller.
// ============================================================

(function () {
    'use strict';

    const POLL_INTERVAL_MS = 1500;
    const ENDPOINT_STATUS = '/agent/check_chat_runtimes_status/';
    const ENDPOINT_ASKER_CHOICE = '/agent/asker_choice/';
    const ENDPOINT_LOAD_CONFIG = '/agent/load_agent_config/';

    let pollerHandle = null;
    let inFlight = false;

    function getCsrfTokenSafe() {
        try {
            if (typeof getCsrfToken === 'function') return getCsrfToken();
        } catch (_e) { /* noop */ }
        const cookieValue = `; ${document.cookie}`;
        const parts = cookieValue.split('; csrftoken=');
        if (parts.length === 2) return parts.pop().split(';').shift() || '';
        return '';
    }

    function buildHeaders(extra) {
        const headers = Object.assign({}, extra || {});
        const csrf = getCsrfTokenSafe();
        if (csrf) headers['X-CSRFToken'] = csrf;
        return headers;
    }

    async function sendChatAskerChoice(runtimeName, choice) {
        const url = `${ENDPOINT_ASKER_CHOICE}${encodeURIComponent(runtimeName)}/`;
        try {
            const resp = await fetch(url, {
                method: 'POST',
                headers: buildHeaders({ 'Content-Type': 'application/json' }),
                credentials: 'same-origin',
                body: JSON.stringify({ choice: choice })
            });
            if (!resp.ok) {
                console.error(`Asker choice POST failed for ${runtimeName}: ${resp.status}`);
            }
        } catch (err) {
            console.error(`Asker choice POST error for ${runtimeName}:`, err);
        }
    }

    async function loadChatAskerConfig(runtimeName) {
        // For chat runtimes, load_agent_config_view will not find them under
        // the canvas pool. We attempt the call but tolerate failure — the
        // dialog renders with no legends if config can't be loaded.
        try {
            const resp = await fetch(`${ENDPOINT_LOAD_CONFIG}${encodeURIComponent(runtimeName)}/`, {
                headers: buildHeaders(),
                credentials: 'same-origin'
            });
            if (resp.ok) return await resp.json();
        } catch (_err) { /* noop */ }
        return null;
    }

    async function pollOnce() {
        if (inFlight) return;
        if (typeof document !== 'undefined' && document.hidden) return;
        if (!window.SharedRuntimeDialogs) return;

        inFlight = true;
        try {
            const resp = await fetch(ENDPOINT_STATUS, {
                method: 'GET',
                headers: buildHeaders(),
                credentials: 'same-origin'
            });
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data || !data.success) return;
            const runtimes = data.runtimes || {};

            for (const [runtimeName, info] of Object.entries(runtimes)) {
                if (info && info.status === 'waiting_for_user_input') {
                    if (!window.SharedRuntimeDialogs.isAskerRequestSubmitted(runtimeName)) {
                        window.SharedRuntimeDialogs.renderAskerChoiceDialog({
                            identifier: runtimeName,
                            sendChoice: sendChatAskerChoice,
                            loadConfig: loadChatAskerConfig
                        });
                    }
                } else {
                    // Clear the submitted flag once the runtime is no longer
                    // waiting (so a re-launched runtime with the same name —
                    // unlikely given the random suffix — would still show).
                    window.SharedRuntimeDialogs.clearSubmittedAskerRequest(runtimeName);
                }

                if (info && info.notification) {
                    window.SharedRuntimeDialogs.renderNotifierToast(info.notification);
                }
            }
        } catch (err) {
            console.warn('chat-runtime poll failed:', err);
        } finally {
            inFlight = false;
        }
    }

    function startChatRuntimePoller() {
        if (pollerHandle) return;
        pollerHandle = setInterval(pollOnce, POLL_INTERVAL_MS);
        // Kick off the first poll immediately for snappy first-dialog appearance.
        pollOnce();
    }

    function stopChatRuntimePoller() {
        if (pollerHandle) {
            clearInterval(pollerHandle);
            pollerHandle = null;
        }
    }

    // Expose for tests / manual control.
    window.ChatRuntimePoller = {
        start: startChatRuntimePoller,
        stop: stopChatRuntimePoller,
        pollOnce: pollOnce
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', startChatRuntimePoller);
    } else {
        startChatRuntimePoller();
    }
})();
