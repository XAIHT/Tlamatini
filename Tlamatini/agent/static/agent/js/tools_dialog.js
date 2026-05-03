
function appendPrompt(content) { // eslint-disable-line no-unused-vars
    const toolsBody = document.getElementById('tools-body');
    const textBox = document.createElement('div');
    textBox.classList.add('text-box');
    textBox.innerHTML = content;
    toolsBody.appendChild(textBox);
}

function decodeHtmlEntities(text) {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = text;
    return textarea.value;
}

function stripHtmlAndCondense(raw) {
    let text = raw.replace(/<[^>]+>/g, ' ');
    text = decodeHtmlEntities(text);
    text = text.replace(/\s+/g, ' ').trim();
    return text;
}

function extractPromptTitle(raw) {
    const bold = raw.match(/\*\*([^*]{3,120})\*\*/);
    if (bold && bold[1]) {
        return decodeHtmlEntities(bold[1]).replace(/\s+/g, ' ').trim();
    }
    const stripped = stripHtmlAndCondense(raw);
    const firstSentence = stripped.split(/(?<=[.!?])\s/)[0] || stripped;
    return firstSentence.length > 80 ? firstSentence.slice(0, 77) + '...' : firstSentence;
}

// Decode &lt; / &gt; / &amp; / &quot; / &mdash; / &middot; etc. so that the
// hero-banner HTML the prompt embeds can actually be parsed by the browser.
// The DB stores the prompts with `&` encoded so the LLM sees literal
// `&mdash;` in its instruction, but for *visual preview* we want the
// rendered glyphs.
function decodeForRender(raw) {
    return decodeHtmlEntities(raw);
}

// Pull the FIRST balanced <div ...>...</div> block out of the prompt text.
// Every demo prompt starts with `Step 1: emit a hero banner <div ...>...</div>.`
// so this gives us the eye-candy that should sit at the top of the card.
// Returns null when no balanced <div> block is found.
function extractFirstDivBlock(raw) {
    const decoded = decodeForRender(raw);
    const openRegex = /<div\b[^>]*>/i;
    const openMatch = decoded.match(openRegex);
    if (!openMatch) return null;
    const start = openMatch.index;
    let depth = 0;
    let i = start;
    const tagRegex = /<\/?div\b[^>]*>/gi;
    tagRegex.lastIndex = start;
    let m;
    while ((m = tagRegex.exec(decoded)) !== null) {
        if (m[0][1] === '/') {
            depth -= 1;
            if (depth === 0) {
                i = m.index + m[0].length;
                return decoded.slice(start, i);
            }
        } else {
            depth += 1;
        }
        if (depth < 0) return null;
    }
    return null;
}

function buildPromptPreview(raw, maxChars = 240) {
    let text = raw;
    // Strip the first hero banner (we render it separately above).
    const banner = extractFirstDivBlock(raw);
    if (banner) {
        const decoded = decodeForRender(raw);
        text = decoded.replace(banner, ' ');
    }
    const stripped = stripHtmlAndCondense(text);
    const cleaned = stripped
        .replace(/Tlamatini,\s*run the\s*\*\*[^*]+\*\*\s*demo,?\s*please\.?\s*/i, '')
        .replace(/Tlamatini,\s*/, '')
        .replace(/\*\*([^*]+)\*\*/g, '$1')
        .replace(/Step\s*\d+\s*\([^)]*\)\s*:\s*/gi, '• ')
        .replace(/Step\s*\d+\s*:\s*/gi, '• ')
        .trim();
    if (cleaned.length <= maxChars) return cleaned;
    return cleaned.slice(0, maxChars - 1).replace(/\s+\S*$/, '') + '…';
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

            const card = document.createElement('div');
            card.className = 'text-box prompt-card';
            card.id = promptName;
            card.dataset.fullContent = content;

            // Live-rendered hero banner ribbon (the first <div>...</div>
            // block from the prompt content), if present.
            const bannerHtml = extractFirstDivBlock(content);
            if (bannerHtml) {
                const heroWrap = document.createElement('div');
                heroWrap.className = 'prompt-card-hero';
                const heroInner = document.createElement('div');
                heroInner.className = 'prompt-card-hero-inner';
                heroInner.innerHTML = bannerHtml;
                heroWrap.appendChild(heroInner);
                card.appendChild(heroWrap);
            }

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

            const preview = document.createElement('p');
            preview.className = 'prompt-card-preview tool-box-entry';
            preview.textContent = buildPromptPreview(content);

            const footer = document.createElement('div');
            footer.className = 'prompt-card-footer';
            const sizeChip = document.createElement('span');
            sizeChip.className = 'prompt-card-chip';
            sizeChip.textContent = `${content.length.toLocaleString()} chars`;
            const renderedChip = document.createElement('span');
            renderedChip.className = 'prompt-card-chip';
            renderedChip.textContent = bannerHtml ? 'banner: rendered' : 'banner: none';
            const insertChip = document.createElement('span');
            insertChip.className = 'prompt-card-chip prompt-card-chip-action';
            insertChip.textContent = 'click to insert →';
            footer.appendChild(sizeChip);
            footer.appendChild(renderedChip);
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
            closeModal();
        });
    }

    function openModal() {
        const buttonRect = catalogButton.getBoundingClientRect();
        modalContent.style.left = `${buttonRect.left}px`;
        modalContent.style.bottom = `${window.innerHeight - buttonRect.top}px`;
        modal.style.display = 'block';
        document.body.style.overflow = 'hidden';
        loadPrompts();
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

