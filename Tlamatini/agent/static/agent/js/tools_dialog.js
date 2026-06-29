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


function appendPrompt(content) { // eslint-disable-line no-unused-vars
    const toolsBody = document.getElementById('tools-body');
    const textBox = document.createElement('div');
    textBox.classList.add('text-box');
    textBox.textContent = content;
    toolsBody.appendChild(textBox);
}

function condenseWhitespace(text) {
    return text.replace(/\s+/g, ' ').trim();
}

function extractPromptTitle(raw) {
    // Catalog prompts now follow the convention
    //   "Tlamatini, run the <Title> demo, please. ..."
    // so we lift the title from between "run the" and "demo".
    const m = raw.match(/run\s+the\s+(.+?)\s+demo/i);
    if (m && m[1]) {
        return condenseWhitespace(m[1]);
    }
    const stripped = condenseWhitespace(raw);
    const firstSentence = stripped.split(/(?<=[.!?])\s/)[0] || stripped;
    return firstSentence.length > 80 ? firstSentence.slice(0, 77) + '...' : firstSentence;
}

function buildPromptPreview(raw, maxChars = 240) {
    const cleaned = condenseWhitespace(raw)
        .replace(/Tlamatini,\s*run the[^.]+demo,?\s*please\.?\s*/i, '')
        .replace(/Tlamatini,\s*/, '')
        .replace(/Step\s*\d+\s*\([^)]*\)\s*:\s*/gi, '• ')
        .replace(/Step\s*\d+\s*:\s*/gi, '• ')
        .trim();
    if (cleaned.length <= maxChars) return cleaned;
    return cleaned.slice(0, maxChars - 1).replace(/\s+\S*$/, '') + '…';
}

// Each catalog prompt is run best with a specific set of toolbar checkboxes. The
// badges below tell the user which ones, and clicking the card sets them.
const PROMPT_MODE_META = {
    oneshot: {
        label: 'One-Shot',
        cls: 'prompt-mode-badge-oneshot',
        tip: 'Single-shot prompt — selecting it turns Multi-Turn AND ACPX OFF.'
    },
    multiturn: {
        label: 'Multi-turn',
        cls: 'prompt-mode-badge-multiturn',
        tip: 'Needs Multi-Turn — selecting it checks the Multi-Turn box.'
    },
    acpx: {
        label: 'ACPX',
        cls: 'prompt-mode-badge-acpx',
        tip: 'Needs ACPX (with Multi-Turn) — selecting it checks the ACPX box.'
    },
    execreport: {
        label: 'Exec-report',
        cls: 'prompt-mode-badge-execreport',
        tip: 'Requires the Exec Report (with Multi-Turn) — selecting it checks the Exec Report box.'
    },
    stepbystep: {
        label: 'Step-by-Step',
        cls: 'prompt-mode-badge-stepbystep',
        tip: 'One action at a time, waiting for you between steps; ticks the Step-by-Step box (with Multi-Turn).'
    }
};

// Classify which toolbar checkboxes a catalog prompt needs, from its content.
// Mirrors a backend-verified rule set (validated against all 65 seeded prompts,
// 0 mismatches):
//   • ACPX  ⇔ the prompt actually CALLS an acp_* / skill tool, OR drives a named
//             Skill (code-review / security-audit). A "do NOT use acp_spawn"
//             disclaimer is scrubbed FIRST so a forbidden tool is never mistaken
//             for a requirement.
//   • Multi-turn ⇔ ACPX, OR it drives a chat_agent_* wrapped agent, OR it says
//             "multi-turn".
//   • One-Shot ⇔ neither (a plain single-shot Q&A / action).
//   • Exec-report ⇔ ANY Multi-turn prompt (so its run is verified); One-Shot omits it.
// Returns an ordered array, e.g. ['oneshot'] | ['multiturn','execreport'] |
//   ['multiturn','acpx','execreport'].
function classifyPromptModes(content) {
    const c = content || '';
    // Drop "do NOT use <…>" forbidden-tool clauses so a tool the prompt
    // EXPLICITLY forbids is never counted as one it requires.
    const scrubbed = c.replace(/(?:do\s+not|don['’]?t|never|not)\s+use\b[^.;]*[.;]?/gi, ' ');
    const acpx =
        /\b(?:acp_doctor|acp_spawn|acp_send|acp_send_and_wait|acp_relay|acp_kill|acp_transcript|acp_session_status|acp_list_sessions|list_acp_agents|invoke_skill|list_skills)\b/i.test(scrubbed)
        || /\b(?:code-review|security-audit)\b[\s\S]{0,16}\bskill\b/i.test(scrubbed)
        || /\bskill\b[\s\S]{0,16}\b(?:code-review|security-audit)\b/i.test(scrubbed);
    const multiturn = acpx
        || /\bchat_agent_\w+/i.test(c)
        || /\bmulti-?turn\b/i.test(c);
    // Step-by-Step is a Multi-Turn pacing modifier (do ONE action, then wait for
    // the user). Detect it ONLY from the HYPHENATED toolbar form ("step-by-step")
    // plus an intent word, so descriptive prose like "searches Wikipedia step by
    // step" (spaces) never trips it: step-?by-?step matches "step-by-step" /
    // "stepbystep" but NOT the spaced "step by step".
    const stepbystep =
        /step-?by-?step\s+(?:wizard|checkbox|toggle|mode|nature|guidance|pacing|cadence|setup)/i.test(c)
        || /(?:tick|check|enable|turn\s+on)[^.\n]{0,60}step-?by-?step/i.test(c);
    let modes;
    if (acpx) modes = ['multiturn', 'acpx'];
    else if (multiturn) modes = ['multiturn'];
    else modes = ['oneshot'];
    // Step-by-Step rides along when present (it implies Multi-Turn in practice).
    if (stepbystep) modes.push('stepbystep');
    // Every Multi-turn prompt (ACPX implies Multi-turn) ALSO carries the
    // Exec-report nature so its run is verified; only pure One-Shot prompts skip
    // it. Clicking the card therefore ticks Exec Report whenever Multi-Turn is
    // set.
    if (!modes.includes('oneshot')) modes.push('execreport');
    return modes;
}

// Build the badge cluster for a card header from a modes array.
function buildPromptModeBadges(modes) {
    const wrap = document.createElement('span');
    wrap.className = 'prompt-card-modes';
    modes.forEach((mode) => {
        const meta = PROMPT_MODE_META[mode];
        if (!meta) return;
        const chip = document.createElement('span');
        chip.className = 'prompt-mode-badge ' + meta.cls;
        chip.textContent = meta.label;
        chip.title = meta.tip;
        wrap.appendChild(chip);
    });
    return wrap;
}

// Set a toolbar checkbox to `desired` and fire its `change` handler so the app's
// existing persistence + dependent-state wiring (sessionStorage, Ask-Execs
// availability) runs exactly as if the user had clicked it.
function setToolbarToggle(checkboxId, desired) {
    const cb = document.getElementById(checkboxId);
    if (!cb) return;
    if (!!cb.checked !== !!desired) {
        cb.checked = !!desired;
        cb.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

// Apply a prompt's required modes to the Multi-Turn + ACPX checkboxes. ACPX
// always implies Multi-Turn; One-Shot turns both off. Multi-Turn is set first so
// the Ask-Execs availability re-sync sees the final Multi-Turn state.
function applyPromptModesToToggles(modes) {
    const wantAcpx = modes.includes('acpx');
    const wantMultiTurn = wantAcpx || modes.includes('multiturn');
    const wantExecReport = modes.includes('execreport');
    const wantStepByStep = modes.includes('stepbystep');
    setToolbarToggle('multi-turn-enabled', wantMultiTurn);
    setToolbarToggle('acpx-enabled', wantAcpx);
    // Multi-Turn is set above first, so the Exec Report toggle is meaningful.
    setToolbarToggle('exec-report-enabled', wantExecReport);
    // Step-by-Step is an independent Multi-Turn pacing modifier; set it to exactly
    // what this prompt needs (so clicking a non-step-by-step card clears it too).
    setToolbarToggle('step-by-step-enabled', wantStepByStep);
}

$(function () {
    const MAX_PROMPTS = 100;
    const catalogButton = document.getElementById('prompts-catalog');
    const modal = document.getElementById('modal');
    const modalContent = document.querySelector('.modal-content');

    async function loadPrompt(promptName, index) {
        try {
            const response = await fetch(`/agent/load_prompt/${promptName}/`);

            if (response.status === 404) {
                console.error('404 Error: Prompt not found - ' + promptName);
                return true;
            }
            if (!response.ok) {
                console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
                return true;
            }

            const content = await response.text();
            if (content === 'Prompt not found in database') {
                console.error('Prompt not found in database: ' + promptName);
                return true;
            }

            const modes = classifyPromptModes(content);

            const card = document.createElement('div');
            card.className = 'text-box prompt-card';
            card.id = promptName;
            card.dataset.fullContent = content;
            card.dataset.modes = modes.join(',');

            const header = document.createElement('div');
            header.className = 'prompt-card-header';

            const badge = document.createElement('span');
            badge.className = 'prompt-card-badge';
            badge.textContent = '#' + String(index).padStart(2, '0');

            const title = document.createElement('span');
            title.className = 'prompt-card-title';
            title.textContent = extractPromptTitle(content);

            header.appendChild(badge);
            header.appendChild(title);
            header.appendChild(buildPromptModeBadges(modes));

            const preview = document.createElement('p');
            preview.className = 'prompt-card-preview tool-box-entry';
            preview.textContent = buildPromptPreview(content);

            const footer = document.createElement('div');
            footer.className = 'prompt-card-footer';
            const sizeChip = document.createElement('span');
            sizeChip.className = 'prompt-card-chip';
            sizeChip.textContent = `${content.length.toLocaleString()} chars`;
            const insertChip = document.createElement('span');
            insertChip.className = 'prompt-card-chip prompt-card-chip-action';
            insertChip.textContent = 'click to insert →';
            footer.appendChild(sizeChip);
            footer.appendChild(insertChip);

            card.appendChild(header);
            card.appendChild(preview);
            card.appendChild(footer);

            const toolsBodyElement = document.getElementById('tools-body');
            toolsBodyElement.appendChild(card);

            return false;
        } catch (error) {
            console.error('Error loading prompt:', error);
            return true;
        }
    }

    async function loadPrompts() {
        const toolsBodyElement = document.getElementById('tools-body');
        toolsBodyElement.innerHTML = "";

        try {
            for (let i = 1; i < MAX_PROMPTS; i++) {
                const promptNameIterator = "prompt-" + i.toString();
                const errorDetected = await loadPrompt(promptNameIterator, i);
                if (errorDetected === true) {
                    break;
                }
            }
        } catch (error) {
            console.error('Error in loadPrompts:', error);
        }

        $('.prompt-card').on('click', function () {
            const fullContent = this.dataset.fullContent || '';
            const chatInput = document.getElementById('chat-message-input');
            chatInput.value = fullContent;
            // Set the toolbar checkboxes to what this prompt needs so it runs in
            // the right mode without the user hunting for the right toggles.
            const modes = (this.dataset.modes || 'oneshot').split(',').filter(Boolean);
            applyPromptModesToToggles(modes);
            closeModal();
        });
    }

    function positionModalNearCatalogButton() {
        const buttonRect = catalogButton.getBoundingClientRect();
        const margin = 12;
        const contentRect = modalContent.getBoundingClientRect();
        const contentWidth = contentRect.width || Math.min(760, window.innerWidth - (margin * 2));
        const contentHeight = contentRect.height || Math.min(window.innerHeight - (margin * 2), window.innerHeight * 0.82);
        const maxLeft = Math.max(margin, window.innerWidth - contentWidth - margin);
        const maxBottom = Math.max(margin, window.innerHeight - contentHeight - margin);
        const left = Math.min(Math.max(buttonRect.left, margin), maxLeft);
        const bottom = Math.min(Math.max(window.innerHeight - buttonRect.top, margin), maxBottom);
        modalContent.style.left = `${left}px`;
        modalContent.style.bottom = `${bottom}px`;
    }

    function openModal() {
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        positionModalNearCatalogButton();
        loadPrompts().finally(positionModalNearCatalogButton);
        setTimeout(() => {
            modal.classList.add('show');
        }, 10);
    }

    function closeModal() {
        modal.classList.remove('show');
        document.body.style.overflow = '';
        setTimeout(() => {
            modal.style.display = 'none';
        }, 300);
    }

    catalogButton.addEventListener('click', openModal);
    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });

});
