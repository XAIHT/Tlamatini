
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
