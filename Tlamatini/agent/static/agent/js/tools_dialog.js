
function appendPrompt(content) { // eslint-disable-line no-unused-vars
    const toolsBody = document.getElementById('tools-body');
    const textBox = document.createElement('div');
    textBox.classList.add('text-box');
    textBox.innerHTML = content;
    toolsBody.appendChild(textBox);
}

$(function () {
    const MAX_PROMPTS = 100;
    const catalogButton = document.getElementById('prompts-catalog');
    const modal = document.getElementById('modal');
    const modalContent = document.querySelector('.modal-content');

    async function loadPrompt(promptName) {
        try {
            const response = await fetch(`/agent/load_prompt/${promptName}/`);

            if (response.status === 404) {
                console.error('404 Error: Prompt not found - ' + promptName);
                return true; // Return true for error
            }
            if (!response.ok) {
                console.error('HTTP Error: ' + response.status + ' - ' + response.statusText);
                return true; // Return true for error
            }

            const content = await response.text();
            if (content === 'Prompt not found in database') {
                console.error('Prompt not found in database: ' + promptName);
                return true; // Return true for error
            }

            // Success - create the prompt element
            const promptContentDiv = document.createElement('div');
            promptContentDiv.className = 'text-box';
            promptContentDiv.id = promptName;
            const promptContentDivParaghraph = document.createElement('p');
            promptContentDivParaghraph.className = 'tool-box-entry';
            promptContentDivParaghraph.innerText = content;
            promptContentDiv.appendChild(promptContentDivParaghraph);
            const toolsBodyElement = document.getElementById('tools-body');
            toolsBodyElement.appendChild(promptContentDiv);

            return false; // Return false for success
        } catch (error) {
            console.error('Error loading prompt:', error);
            return true; // Return true for error
        }
    }

    async function loadPrompts() {
        // Clear the tools-body element before loading new prompts
        const toolsBodyElement = document.getElementById('tools-body');
        toolsBodyElement.innerHTML = "";

        try {
            for (let i = 1; i < MAX_PROMPTS; i++) {
                const promptNameIterator = "prompt-" + i.toString();
                const errorDetected = await loadPrompt(promptNameIterator);
                if (errorDetected === true) {
                    break;
                }
            }
        } catch (error) {
            console.error('Error in loadPrompts:', error);
        }

        $('.tool-box-entry').on('click', function () {
            console.log(">>>>>>>>>>>>>>>>>>>>>>>>");
            console.log($(this).html());
            console.log("<<<<<<<<<<<<<<<<<<<<<<<<");
            const chatInput = document.getElementById('chat-message-input');
            chatInput.value = $(this).html();
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

