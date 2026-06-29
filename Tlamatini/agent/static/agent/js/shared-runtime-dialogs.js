/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 *
 *   Every line of this file was written by Angela López Mendoza.
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 */

// ============================================================
// shared-runtime-dialogs.js
// Reusable Asker A/B dialog + Notifier toast renderers used by
// both agent_page.html (chat) and agentic_control_panel.html (ACP).
// ============================================================
//
// This module is NEW: it intentionally does NOT depend on ACP-only
// globals (e.g., ACP, getHeaders, SESSION_ID). Callers pass an
// options object that supplies any page-specific helpers they need.

(function (root) {
    'use strict';

    // Track which agents/runtimes have already had a choice submitted in this
    // page-load session. Keyed by the same identifier the caller uses (canvas
    // id for ACP, runtime name for chat).
    const submittedAskerRequests = new Set();

    function escapeHtmlShared(str) {
        const div = document.createElement('div');
        div.textContent = str == null ? '' : String(str);
        return div.innerHTML;
    }

    // Detect which Tlamatini page this module is running on, so the backend
    // attention banner can name the right surface.
    function detectCurrentPage() {
        const p = ((window.location && window.location.pathname) || '').toLowerCase();
        if (p.indexOf('agentic_control_panel') !== -1) return 'agentic_control_panel.html';
        return 'agent_page.html';
    }

    /**
     * Ask the backend to flash the Tlamatini.exe console taskbar button and log
     * an uppercase attention banner. Page JavaScript cannot flash its OWN
     * browser taskbar button (sandbox), but the Django process can flash the
     * .exe window it owns. Best-effort: failures are silently ignored.
     * @param {string} reason - 'execution-approval' | 'notification'.
     * @param {string} [page] - Override the auto-detected page identifier.
     */
    function flashTlamatiniWindow(reason, page) {
        try {
            const targetPage = page || detectCurrentPage();
            const cookieValue = `; ${document.cookie}`;
            const parts = cookieValue.split('; csrftoken=');
            const csrf = parts.length === 2 ? (parts.pop().split(';').shift() || '') : '';
            const headers = { 'Content-Type': 'application/json' };
            if (csrf) headers['X-CSRFToken'] = csrf;
            fetch('/agent/flash_window/', {
                method: 'POST',
                headers: headers,
                credentials: 'same-origin',
                body: JSON.stringify({ page: targetPage, reason: reason || '' })
            }).catch(() => { /* attention flash is best-effort */ });
        } catch (_e) { /* best-effort; never break the caller */ }
    }

    /**
     * Render the Notifier toast for a single notification payload.
     * @param {Object} notification - Payload as emitted by notifier.py.
     */
    function renderNotifierToast(notification) {
        if (!notification) return;
        // Flash the Tlamatini.exe taskbar button + log banner. The backend
        // dedupes notifications (notification.json is deleted after one read),
        // so this fires exactly once per notification.
        flashTlamatiniWindow('notification');
        const matchesArray = notification.matches || [];
        const matches = matchesArray.join(', ');
        const sourceAgent = notification.source_agent || notification.runtime_name || 'unknown';
        const timestamp = notification.timestamp || '';
        const soundEnabled = !!notification.sound_enabled;
        const outcomeDetail = notification.outcome_detail || '';

        const matchesLower = matches.toLowerCase();
        const errorPatterns = ['error', 'fatal'];
        const warningPatterns = ['warn', 'warning'];
        const hasError = errorPatterns.some(p => matchesLower.includes(p));
        const hasWarning = warningPatterns.some(p => matchesLower.includes(p));

        let severity = 'success';
        let severityIcon = '✅';
        let severityColor = '#10B981';
        let severityBgColor = '#D1FAE5';
        let severityTextColor = '#065F46';
        let dialogTitle = 'Pattern Detected';

        if (hasError) {
            severity = 'error';
            severityIcon = '🚨';
            severityColor = '#DC2626';
            severityBgColor = '#FEE2E2';
            severityTextColor = '#991B1B';
            dialogTitle = 'Error Detected';
        } else if (hasWarning) {
            severity = 'warning';
            severityIcon = '⚠️';
            severityColor = '#F59E0B';
            severityBgColor = '#FEF3C7';
            severityTextColor = '#92400E';
            dialogTitle = 'Warning Detected';
        }

        if (soundEnabled) {
            try {
                const audio = new Audio('/static/agent/sounds/notification.wav');
                audio.play().catch(e => console.warn('Audio play failed:', e));
            } catch (e) {
                console.warn('Audio init failed:', e);
            }
        }

        const dialogId = `notification-dialog-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
        const dialogDiv = document.createElement('div');
        dialogDiv.id = dialogId;
        dialogDiv.title = `${severityIcon} ${dialogTitle}: ${sourceAgent}`;
        const outcomeDetailHtml = outcomeDetail
            ? `<div style="margin: 10px 0 6px; padding: 8px 12px; background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02)); border-left: 3px solid ${severityColor}; border-radius: 0 4px 4px 0;">
                   <p style="margin: 0; font-size: 0.9em; color: #c0c0c0; line-height: 1.4; font-style: italic;">${escapeHtmlShared(outcomeDetail)}</p>
               </div>`
            : '';
        dialogDiv.innerHTML = `
            <p style="text-align: center; color: ${severityColor}; font-weight: bold; font-size: 1.1em;">
                ${dialogTitle}!
            </p>
            <p><strong>Agent:</strong> ${escapeHtmlShared(sourceAgent)}</p>
            <p><strong>Found:</strong> <span style="background-color: ${severityBgColor}; padding: 2px 5px; border-radius: 3px; color: ${severityTextColor};">${escapeHtmlShared(matches)}</span></p>
            ${outcomeDetailHtml}
            <p style="font-size: 0.8em; color: #888;">${escapeHtmlShared(timestamp)}</p>
        `;
        document.body.appendChild(dialogDiv);

        $(dialogDiv).dialog({
            modal: false,
            width: 350,
            resizable: false,
            draggable: true,
            closeText: 'Dismiss',
            dialogClass: `notification-dialog-class notification-${severity}`,
            buttons: {
                'Dismiss': function () { $(this).dialog('close'); }
            },
            close: function () {
                $(this).dialog('destroy');
                dialogDiv.remove();
            },
            position: { my: 'right bottom', at: 'right-20 bottom-20', of: window },
            open: function () {
                $(this).parent().css('border-left', `4px solid ${severityColor}`);
            }
        });
    }

    /**
     * Render the Asker A/B choice dialog. Caller supplies:
     *   - identifier:       the id used in the dialog DOM and the submit URL.
     *   - sendChoice(id, c): function that POSTs the user's choice ('A' | 'B').
     *   - loadConfig(id):   optional async function returning {legend_path_a, legend_path_b}.
     */
    async function renderAskerChoiceDialog(options) {
        const identifier = options.identifier;
        const sendChoice = options.sendChoice;
        const loadConfig = options.loadConfig;

        if (!identifier || typeof sendChoice !== 'function') return;

        if (submittedAskerRequests.has(identifier)) return;
        const dialogId = `asker-dialog-${identifier}`;
        if (document.getElementById(dialogId)) return;

        let legendA = '';
        let legendB = '';
        if (typeof loadConfig === 'function') {
            try {
                const cfg = await loadConfig(identifier);
                if (cfg) {
                    legendA = cfg.legend_path_a || '';
                    legendB = cfg.legend_path_b || '';
                }
            } catch (err) {
                console.warn(`Could not load Asker config for ${identifier}:`, err);
            }
        }

        if (submittedAskerRequests.has(identifier)) return;
        if (document.getElementById(dialogId)) return;

        const hasLegends = legendA || legendB;
        const safeA = escapeHtmlShared(legendA);
        const safeB = escapeHtmlShared(legendB);

        const dialogDiv = document.createElement('div');
        dialogDiv.id = dialogId;
        dialogDiv.title = 'User Input Needed';
        dialogDiv.innerHTML = `
            <p style="text-align: center; font-size: 1.1em;">
                <strong>${escapeHtmlShared(identifier)}</strong> needs your input!
            </p>
            <p style="text-align: center;">Choose a path to continue:</p>
            <div style="display: flex; justify-content: space-around; margin-top: 15px; gap: 16px;">
                <div style="display: flex; flex-direction: column; align-items: center; flex: 1;">
                    <button id="btn-choice-a-${identifier}" class="asker-choice-btn" style="background: #EF4444; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%;">Path A</button>
                    ${safeA ? `<p style="margin: 8px 0 0; font-size: 0.85em; color: #ccc; text-align: center; word-wrap: break-word;">${safeA}</p>` : ''}
                </div>
                <div style="display: flex; flex-direction: column; align-items: center; flex: 1;">
                    <button id="btn-choice-b-${identifier}" class="asker-choice-btn" style="background: #3B82F6; color: white; padding: 10px 20px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold; width: 100%;">Path B</button>
                    ${safeB ? `<p style="margin: 8px 0 0; font-size: 0.85em; color: #ccc; text-align: center; word-wrap: break-word;">${safeB}</p>` : ''}
                </div>
            </div>
        `;
        document.body.appendChild(dialogDiv);

        const $dialog = $(dialogDiv).dialog({
            modal: false,
            width: hasLegends ? 420 : 350,
            resizable: false,
            draggable: true,
            closeText: '',
            dialogClass: 'asker-dialog-wrapper',
            close: function () {
                $(this).dialog('destroy');
                dialogDiv.remove();
            },
            position: { my: 'center', at: 'center', of: window },
            open: function () {
                $(this).parent().css('border-top', '4px solid #8B5CF6');
            }
        });

        const btnA = document.getElementById(`btn-choice-a-${identifier}`);
        const btnB = document.getElementById(`btn-choice-b-${identifier}`);

        if (btnA) {
            btnA.addEventListener('click', () => {
                submittedAskerRequests.add(identifier);
                btnA.textContent = 'Sending...';
                btnA.disabled = true;
                if (btnB) btnB.disabled = true;
                Promise.resolve(sendChoice(identifier, 'A')).catch(err =>
                    console.error('sendChoice(A) failed:', err)
                );
                $dialog.dialog('close');
            });
        }
        if (btnB) {
            btnB.addEventListener('click', () => {
                submittedAskerRequests.add(identifier);
                btnB.textContent = 'Sending...';
                btnB.disabled = true;
                if (btnA) btnA.disabled = true;
                Promise.resolve(sendChoice(identifier, 'B')).catch(err =>
                    console.error('sendChoice(B) failed:', err)
                );
                $dialog.dialog('close');
            });
        }
    }

    function clearSubmittedAskerRequest(identifier) {
        submittedAskerRequests.delete(identifier);
    }

    function isAskerRequestSubmitted(identifier) {
        return submittedAskerRequests.has(identifier);
    }

    root.SharedRuntimeDialogs = {
        renderNotifierToast: renderNotifierToast,
        renderAskerChoiceDialog: renderAskerChoiceDialog,
        escapeHtml: escapeHtmlShared,
        clearSubmittedAskerRequest: clearSubmittedAskerRequest,
        isAskerRequestSubmitted: isAskerRequestSubmitted,
        submittedAskerRequests: submittedAskerRequests,
        flashTlamatiniWindow: flashTlamatiniWindow
    };
})(typeof window !== 'undefined' ? window : this);
