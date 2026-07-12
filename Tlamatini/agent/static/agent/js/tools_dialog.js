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

// ═══════════════════════════════════════════════════════════════════════
//  Smart prompt search — substring + word-start + acronym + fuzzy
//  subsequence scoring, so "imd", "instant msg", "#91", "telegram wizard"
//  or "whatsapp" all surface the right card, ranked best-first, with the
//  matched letters highlighted live as the user types.
// ═══════════════════════════════════════════════════════════════════════

// Escape a raw string for safe insertion into innerHTML.
function escapeHtmlForSearch(s) {
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// True when the char at `i` begins a new word (start of string, or preceded
// by a non-alphanumeric character).
function isWordStart(text, i) {
    if (i <= 0) return true;
    return /[^a-z0-9]/i.test(text.charAt(i - 1));
}

// Contiguous-substring score within `hay` (already lowercased). Rewards an
// earlier position, a word/field start, and covering more of a short field.
function substringMatchScore(token, hay) {
    const idx = hay.indexOf(token);
    if (idx === -1) return 0;
    let score = 60;
    if (isWordStart(hay, idx)) score += 30;
    if (idx === 0) score += 20;
    score += Math.max(0, 18 - idx * 0.4);
    score += Math.min(20, (token.length / Math.max(hay.length, 1)) * 40);
    return score;
}

// Fuzzy subsequence score: do the chars of `token` appear in `hay` in order?
// Rewards tight, contiguous, word-start-aligned runs (the VS Code / Sublime
// "fuzzy finder" feel). Returns 0 when the subsequence is not present.
function subsequenceMatchScore(token, hay) {
    if (!token) return 0;
    let ti = 0, score = 0, run = 0, prev = -2, firstIdx = -1;
    for (let hi = 0; hi < hay.length && ti < token.length; hi++) {
        if (hay.charAt(hi) === token.charAt(ti)) {
            if (firstIdx === -1) firstIdx = hi;
            if (hi === prev + 1) { run += 1; score += 6 + run * 2; }
            else { run = 0; score += 2; }
            if (isWordStart(hay, hi)) score += 5;
            prev = hi;
            ti += 1;
        }
    }
    if (ti < token.length) return 0;
    score += Math.max(0, 10 - firstIdx * 0.3);
    return score;
}

// Acronym score: does `token` match the initials of consecutive words in
// `hay`? e.g. "imd" → "Instant Messaging Doctor". A strong title signal.
function acronymMatchScore(token, hay) {
    if (token.length < 2) return 0;
    const initials = (hay.match(/\b[a-z0-9]/gi) || []).join('').toLowerCase();
    const idx = initials.indexOf(token);
    if (idx === -1) return 0;
    let score = 70 + (token.length - 2) * 8;
    if (idx === 0) score += 20;
    return score;
}

// Best score for one token within one field, scaled by the field's weight.
function scoreTokenInField(token, field, weight) {
    if (!field) return 0;
    const best = Math.max(
        substringMatchScore(token, field),
        acronymMatchScore(token, field),
        subsequenceMatchScore(token, field)
    );
    return best * weight;
}

// Score a whole card against the query. AND semantics: every typed token must
// land somewhere. Returns { score, matched } — matched=false ⇒ hide the card.
function scorePromptCardFields(query, f) {
    const q = (query || '').trim().toLowerCase();
    if (!q) return { score: 0, matched: true };
    const tokens = q.split(/\s+/).filter(Boolean);

    // Whole-query contiguous-phrase bonus (so "instant messaging" beats a card
    // that merely contains both words far apart).
    let phraseBonus = 0;
    if (f.title.includes(q)) phraseBonus += 120;
    else if (f.preview.includes(q)) phraseBonus += 45;
    else if (f.content.includes(q)) phraseBonus += 20;

    // Pure "#NN" / "NN" query → match by catalog index.
    const numQuery = q.replace(/^#/, '');
    if (/^\d+$/.test(numQuery)) {
        if (f.numberStr === numQuery) return { score: 10000, matched: true };
        if (f.numberStr.indexOf(numQuery) !== -1) return { score: 4000 + phraseBonus, matched: true };
    }

    let total = phraseBonus;
    for (const token of tokens) {
        const tnum = token.replace(/^#/, '');
        if (/^\d+$/.test(tnum)) {
            if (f.numberStr === tnum) { total += 400; continue; }
            if (f.numberStr.indexOf(tnum) !== -1) { total += 150; continue; }
        }
        const best = Math.max(
            scoreTokenInField(token, f.title, 1.0),
            scoreTokenInField(token, f.modes, 0.7),
            scoreTokenInField(token, f.preview, 0.5),
            scoreTokenInField(token, f.content, 0.18)
        );
        if (best <= 0) return { score: 0, matched: false };
        total += best;
    }
    return { score: total, matched: true };
}

// Wrap every query-token match inside `text` in <mark> (contiguous hits, or a
// greedy subsequence fallback), returning an HTML-escaped, highlighted string.
function highlightMatches(text, query) {
    const raw = String(text);
    const q = (query || '').trim().toLowerCase();
    if (!q) return escapeHtmlForSearch(raw);
    const lower = raw.toLowerCase();
    const tokens = q.split(/\s+/).filter(Boolean).filter((t) => !/^#?\d+$/.test(t));
    if (!tokens.length) return escapeHtmlForSearch(raw);
    const marks = new Array(raw.length).fill(false);

    tokens.forEach((token) => {
        let hit = false;
        let from = 0;
        let idx = lower.indexOf(token, from);
        while (idx !== -1) {
            for (let k = idx; k < idx + token.length; k++) marks[k] = true;
            hit = true;
            from = idx + token.length;
            idx = lower.indexOf(token, from);
        }
        if (hit) return;
        let ti = 0;
        for (let hi = 0; hi < lower.length && ti < token.length; hi++) {
            if (lower.charAt(hi) === token.charAt(ti)) { marks[hi] = true; ti += 1; }
        }
    });

    let out = '';
    let i = 0;
    while (i < raw.length) {
        const on = marks[i];
        let j = i;
        while (j < raw.length && marks[j] === on) j++;
        const segment = escapeHtmlForSearch(raw.slice(i, j));
        out += on ? '<mark class="prompt-search-hit">' + segment + '</mark>' : segment;
        i = j;
    }
    return out;
}

$(function () {
    const MAX_PROMPTS = 256;
    const catalogButton = document.getElementById('prompts-catalog');
    const modal = document.getElementById('modal');
    const searchInput = document.getElementById('prompt-search-input');
    const searchClear = document.getElementById('prompt-search-clear');
    const searchCount = document.getElementById('prompt-search-count');

    function renderPromptCard(promptName, index, content) {
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

        // Cache the searchable fields + node refs the live search needs.
        card._promptIndex = index;
        card._titleEl = title;
        card._previewEl = preview;
        card._titleText = title.textContent;
        card._previewText = preview.textContent;
        card._searchFields = {
            numberStr: String(index),
            title: title.textContent.toLowerCase(),
            preview: preview.textContent.toLowerCase(),
            modes: modes
                .map((m) => (PROMPT_MODE_META[m] ? PROMPT_MODE_META[m].label : m))
                .join(' ')
                .toLowerCase(),
            content: (content || '').toLowerCase()
        };

        const toolsBodyElement = document.getElementById('tools-body');
        toolsBodyElement.appendChild(card);
    }

    async function loadPrompt(promptName, index) {
        try {
            const response = await fetch(`/agent/load_prompt/${promptName}/`);

            if (response.status === 404) {
                return true;
            }
            if (!response.ok) {
                console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
                return true;
            }

            const content = await response.text();
            if (content === 'Prompt not found in database') {
                return true;
            }

            renderPromptCard(promptName, index, content);
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
            const response = await fetch('/agent/list_prompts/', { credentials: 'same-origin' });
            if (response.ok) {
                const payload = await response.json();
                (payload.prompts || []).forEach((prompt, idx) => {
                    renderPromptCard(
                        prompt.name || ('prompt-' + String(idx + 1)),
                        Number(prompt.index) || idx + 1,
                        prompt.content || ''
                    );
                });
            } else {
                for (let i = 1; i <= MAX_PROMPTS; i++) {
                    const promptNameIterator = "prompt-" + i.toString();
                    const errorDetected = await loadPrompt(promptNameIterator, i);
                    if (errorDetected === true) {
                        break;
                    }
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

    // Live, ranked, fuzzy filter of the catalog. Reorders matches to the top
    // (best-first), highlights the matched letters, shows a live count (red on
    // zero), and scrolls the list back to the top so the best match is always
    // in view as the user types.
    function applyPromptSearch(rawQuery) {
        const toolsBodyElement = document.getElementById('tools-body');
        const cards = Array.prototype.slice.call(toolsBodyElement.querySelectorAll('.prompt-card'));
        const query = (rawQuery || '').trim();

        const priorEmpty = toolsBodyElement.querySelector('.prompt-search-empty');
        if (priorEmpty) priorEmpty.remove();
        cards.forEach((card) => card.classList.remove('prompt-card-top'));

        // Empty query → restore the original order, show everything, no marks.
        if (!query) {
            cards
                .sort((a, b) => a._promptIndex - b._promptIndex)
                .forEach((card) => {
                    card.classList.remove('prompt-card-hidden');
                    if (card._titleEl) card._titleEl.textContent = card._titleText;
                    if (card._previewEl) card._previewEl.textContent = card._previewText;
                    toolsBodyElement.appendChild(card);
                });
            if (searchClear) searchClear.classList.remove('is-visible');
            if (searchCount) {
                searchCount.classList.remove('is-zero');
                searchCount.textContent = cards.length ? cards.length + ' prompts' : '';
            }
            toolsBodyElement.scrollTop = 0;
            return;
        }

        if (searchClear) searchClear.classList.add('is-visible');

        const matched = [];
        cards.forEach((card) => {
            const res = scorePromptCardFields(query, card._searchFields || {});
            if (res.matched && res.score > 0) {
                matched.push({ card: card, score: res.score });
            } else {
                card.classList.add('prompt-card-hidden');
                if (card._titleEl) card._titleEl.textContent = card._titleText;
                if (card._previewEl) card._previewEl.textContent = card._previewText;
            }
        });

        // Rank best-first; stable tie-break by original catalog order.
        matched.sort((a, b) => (b.score - a.score) || (a.card._promptIndex - b.card._promptIndex));
        matched.forEach((entry) => {
            const card = entry.card;
            card.classList.remove('prompt-card-hidden');
            if (card._titleEl) card._titleEl.innerHTML = highlightMatches(card._titleText, query);
            if (card._previewEl) card._previewEl.innerHTML = highlightMatches(card._previewText, query);
            toolsBodyElement.appendChild(card);
        });
        if (matched.length) matched[0].card.classList.add('prompt-card-top');

        if (searchCount) {
            searchCount.classList.toggle('is-zero', matched.length === 0);
            searchCount.textContent = matched.length
                ? matched.length + (matched.length === 1 ? ' match' : ' matches')
                : 'no matches';
        }

        if (!matched.length) {
            const empty = document.createElement('div');
            empty.className = 'prompt-search-empty';
            empty.innerHTML = 'No prompt matches &ldquo;' + escapeHtmlForSearch(query)
                + '&rdquo;. Try fewer letters, initials (e.g. <b>imd</b>), or a #number.';
            toolsBodyElement.appendChild(empty);
        }

        toolsBodyElement.scrollTop = 0;
    }

    // The catalog panel's geometry is 100% CSS-driven (.modal-content in
    // tools_dialog.css): pinned to the VIEWPORT's top-left and capped at
    // calc(100dvh - 24px), so it never depends on the chat input's height and
    // the header + search bar are always on screen.
    //
    // It replaced positionModalNearCatalogButton(), which anchored the panel's
    // BOTTOM to the "Catalog of prompts" button — whose y moves with the chat
    // textarea — and sized the clamp from a .modal-content still sitting at
    // transform: scale(0), i.e. a 0x0 rect. So the height cap never engaged and
    // a large catalog grew straight off the TOP of the window, taking the search
    // box out of reach. Do NOT re-introduce JS positioning here.

    function openModal() {
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        if (searchInput) searchInput.value = '';
        loadPrompts().finally(() => {
            applyPromptSearch('');
            if (searchInput) searchInput.focus();
        });
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

    if (searchInput) {
        searchInput.addEventListener('input', () => applyPromptSearch(searchInput.value));
        searchInput.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && searchInput.value) {
                event.stopPropagation();
                searchInput.value = '';
                applyPromptSearch('');
            } else if (event.key === 'Enter') {
                // Insert the top-ranked (first visible) prompt.
                const top = document.querySelector('#tools-body .prompt-card:not(.prompt-card-hidden)');
                if (top) {
                    event.preventDefault();
                    top.click();
                }
            }
        });
    }
    if (searchClear) {
        searchClear.addEventListener('click', () => {
            if (searchInput) {
                searchInput.value = '';
                searchInput.focus();
            }
            applyPromptSearch('');
        });
    }

    window.addEventListener('click', (event) => {
        if (event.target === modal) {
            closeModal();
        }
    });

});
