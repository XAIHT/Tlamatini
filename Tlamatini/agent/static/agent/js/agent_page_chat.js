// ============================================================
// agent_page_chat.js  –  Chat messaging, WebSocket & form submit
// ============================================================

function appendChatMessage(username, message, addedContent = null, timestampStr = null) {
    const messageDiv = document.createElement('div');
    const messageContentDiv = document.createElement('div');
    const usernameDiv = document.createElement('div');
    const usernameTextSpan = document.createElement('span');
    const copyBtn = document.createElement('button');

    messageDiv.classList.add('message');
    messageContentDiv.classList.add('message-content');
    usernameDiv.classList.add('username');
    copyBtn.classList.add('message-copy-btn');
    copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Copy';

    if (isBusyMessageRequest(message)) {
        setTitleBusy(true);
        disableControlsDuringOperation();
    } else if (isBusyMessageContext(message)) {
        setTitleBusy(true);
        disableControlsDuringOperation();
        lapseLoadingContext = true;
    } else if (message.toLowerCase().includes("out of the root directory") || message.toLowerCase().includes("outside the application root")) {
        console.log("--- Selected directory is outside the application root path and is not allowed. message received: " + message);
        lapseLoadingContext = false;
        clearContextEnabled = false;
        clearContextButton.setAttribute("style", "display: none !important;");
        setContextText("<<<" + "..." + ">>>  ");
        contextInfoDiv.setAttribute("class", "col-md-2 col-lg-3 col-xl-4 col-xxl-4 flex-nowrap p-0 m-0 context-info-invisible");
        lapseLoadingContext = false;

        if (actualContextDir !== null && actualContextDir !== '') {
            actualContextDir = null;
            updateViewContextDirMenuState();
        }
        clearContextEnabled = false;
        clearContextButton.setAttribute("style", "display: none !important;");
        enableControlsAfterOperation();
    } else if (message.toLowerCase().includes("referenced rephrase:")) {
        setTitleBusy(true);
        console.log("--- Referenced Rephrase: message received: " + message);
    } else {
        enableControlsAfterOperation();
    }

    if (username === 'LLM_Bot') {
        messageDiv.classList.add('bot-message');
        usernameDiv.style.color = '#55BBAA';
        const formatted = String(message);
        messageContentDiv.innerHTML = '<div class="automated-message">' + formatted + '</div>';
        if (addedContent != null) {
            $(addedContent).off('click').on('click', function (e) {
                e.preventDefault();
                console.log("wwwwwwwwwwwwwwwwww");
                console.log($(this).data('files'));
                send2SaveFiles($(this).data('files'));
                console.log("wwwwwwwwwwwwwwwwww");
                $(this).off('click');
                $(this).remove();
            });
            messageContentDiv.firstChild.appendChild(document.createElement('br'));
            messageContentDiv.firstChild.appendChild(addedContent);
            console.log("xxxxxxxxxxxxxxxxxx");
            console.log(addedContent.data);
            console.log("xxxxxxxxxxxxxxxxxx");
        }
    } else {
        messageDiv.classList.add('user-message');
        usernameDiv.style.color = '#A893F3';
        messageContentDiv.innerText = message;
    }

    let finalTimestamp = timestampStr;
    if (!finalTimestamp) {
        const now = new Date();
        const yyyy = now.getFullYear();
        const mm = String(now.getMonth() + 1).padStart(2, '0');
        const dd = String(now.getDate()).padStart(2, '0');
        const hh = String(now.getHours()).padStart(2, '0');
        const min = String(now.getMinutes()).padStart(2, '0');
        const ss = String(now.getSeconds()).padStart(2, '0');
        const ms = String(now.getMilliseconds()).padStart(3, '0');
        finalTimestamp = `${yyyy}/${mm}/${dd} ${hh}:${min}:${ss}.${ms}`;
    }

    usernameTextSpan.textContent = `${username} (${finalTimestamp})`;
    usernameDiv.appendChild(usernameTextSpan);
    usernameDiv.appendChild(copyBtn);
    messageContentDiv.prepend(usernameDiv);
    messageDiv.appendChild(messageContentDiv);
    chatLog.appendChild(messageDiv);

    copyBtn.addEventListener('click', () => {
        let textToCopy;
        if (messageDiv.classList.contains('bot-message')) {
            const botContentDiv = messageContentDiv.querySelector('.automated-message');
            // Build the copy text explicitly to avoid duplication from the prepended usernameDiv.
            textToCopy = `${usernameTextSpan.textContent}\n\n${botContentDiv ? botContentDiv.innerText : messageContentDiv.innerText.replace(usernameDiv.innerText, '').trim()}`;
        } else {
            // User message: messageContentDiv.innerText includes the username (since it's prepended) but we want a clean copy
            const cleanMessage = messageContentDiv.innerText.replace(usernameDiv.innerText, '').trim();
            textToCopy = `${usernameTextSpan.textContent}\n\n${cleanMessage}`;
        }

        navigator.clipboard.writeText(textToCopy).then(() => {
            const originalHTML = copyBtn.innerHTML;
            copyBtn.innerHTML = '<i class="bi bi-check2"></i> Copied!';
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.innerHTML = originalHTML;
                copyBtn.classList.remove('copied');
            }, 2000);
        }).catch(err => {
            console.error('Failed to copy message: ', err);
            copyBtn.innerHTML = '<i class="bi bi-x"></i> Error';
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="bi bi-clipboard"></i> Copy';
            }, 2000);
        });
    });
}

function renderInitialMessages(messages) {
    if (!Array.isArray(messages)) return;
    chatLog.innerHTML = '';
    buildingInitial = true;
    for (const msg of messages) {
        if (!msg) continue;
        appendChatMessage(msg.username, msg.message, null, msg.timestamp);
    }
    buildingInitial = false;
    chatLog.scrollTop = chatLog.scrollHeight;
}

function parseToFindFiles(data) {
    let someFileExtracted = false;
    console.log("----------------");
    console.log(data);
    console.log("----------------");
    const stream = data.message;
    let stringFileNames = "";
    if (stream) {
        console.log("Trying to find files into: " + stream + "...");
        const loadCanvasPattern = /loadCanvas\("([^"]+)"\)/g;
        const extractedStrings = [];
        let match;
        console.log(">>>>>>>>>>>>>>>>>>messsage: " + data.message);

        match = "1";
        while (match !== null) {
            match = loadCanvasPattern.exec(data.message);
            if (!match) break;
            extractedStrings.push(match[1]);
            stringFileNames += match[1] + "|";
            someFileExtracted = true;
        }

        if (someFileExtracted === false) {
            console.log("No files found in message...");
            return null;
        }
        stringFileNames = stringFileNames.slice(0, -1);
        const link2BeAppended = document.createElement('a');
        $(link2BeAppended).data('files', stringFileNames);
        link2BeAppended.href = '#';
        link2BeAppended.className = 'save-files-anchor';
        link2BeAppended.innerText = 'Save all files received';
        console.log('Extracted loadCanvas strings (files in message):', extractedStrings);
        console.log("Link generated: ");
        console.log("+++++++++++++++++++++");
        const textLink2BeAppended = link2BeAppended.outerHTML;
        console.log(textLink2BeAppended);
        console.log("+++++++++++++++++++++");
        return link2BeAppended;
    }
    console.error("No files found in message...");
    return null;
}

function send2SaveFiles(files) {
    if (!files) return;
    chatSocket.send(JSON.stringify({
        'type': 'save-files-from-db',
        'message': files,
        'content': ''
    }));
}

// --- WebSocket message handler ---
chatSocket.onmessage = function (e) {
    const data = JSON.parse(e.data);

    if (data && data.username === 'LLM_Bot' && !isBusyMessageRequest(data.message)) {
        setTitleBusy(false);
    }
    if (data && data.username === 'LLM_Bot' && !isBusyMessageContext(data.message)) {
        setTitleBusy(false);
    }
    if (data.username === 'ping') {
        console.log('--- Received heartbeat message from server');
        return;
    }
    // Handle session-restored: Context was restored from saved session
    if (data.type === 'session-restored') {
        console.log('--- Session restored from server:', data);
        if (data.context_path) {
            setContextText('<<< ' + data.context_path + ' >>>');
            contextInfoDiv.classList.remove('context-info-invisible');
            contextInfoDiv.classList.add('context-info-visible');
            actualContextDir = data.context_path;
            clearContextEnabled = true;
            clearContextButton.removeAttribute('style');
            updateViewContextDirMenuState();
            console.log('--- Context UI restored: ' + data.context_path);
        }
        return;
    }
    // Handle context-path-set: Server confirms full context path after set operation
    if (data.type === 'context-path-set') {
        console.log('--- Context path set by server:', data.context_path);
        if (data.context_path) {
            setContextText('<<< ' + data.context_path + ' >>>');
        }
        return;
    }
    if (data.username === 'system' && data.type === 'mcp') {
        console.log('--- Received system message from server, message: ' + data.message);
        const values = data.message.split('|');
        const mcpName = values[0];
        const mcpContent = values[2];
        if (mcpName === 'mcp-1') {
            mcp1_enabled = (mcpContent === 'true') ? true : false;
            console.log("MCP-1: Enabled?: " + mcp1_enabled);
        }
        if (mcpName === 'mcp-2') {
            mcp2_enabled = (mcpContent === 'true') ? true : false;
            console.log("MCP-2: Enabled?: " + mcp2_enabled);
        }
        tools = [];
        return;
    }
    if (data.username === 'system' && data.type === 'tool') {
        console.log('--- Received system message from server, message: ' + data.message);
        const values = data.message.split('|');
        const toolName = values[0];
        const toolDescription = values[1];
        const toolContent = values[2];
        tools.push({
            name: toolName,
            description: toolDescription,
            content: toolContent
        });
        console.log("--- Tool added: " + toolName + " - " + toolDescription + " - " + toolContent);
        return;
    }
    if (data.username === 'system' && data.type === 'agent') {
        console.log('--- Received system message from server, message: ' + data.message);
        const values = data.message.split('|');
        const agentName = values[0];
        const agentDescription = values[1];
        const agentContent = values[2];
        const existingAgentIndex = agents.findIndex(a => a.name === agentName);
        if (existingAgentIndex !== -1) {
            agents[existingAgentIndex].description = agentDescription;
            agents[existingAgentIndex].content = agentContent;
            console.log("--- Agent updated: " + agentName + " - " + agentDescription + " - " + agentContent);
        } else {
            agents.push({
                name: agentName,
                description: agentDescription,
                content: agentContent
            });
            console.log("--- Agent added: " + agentName + " - " + agentDescription + " - " + agentContent);
        }
        return;
    }
    if (data && data.username === 'LLM_Bot' && data.message.startsWith('_tree_:') === true) {
        console.log("--- Received tree_view content message from server.");
        console.log("--- The message(tree_view content) is: " + data.message);
        const finalContent = data.message.substring(7);
        loadCanvasWithThisContent(finalContent);
        return;
    }

    const filesAnchorElement = parseToFindFiles(data);
    if (filesAnchorElement) {
        console.log("<<<<<<<<<<<<<<<<<");
        console.log(filesAnchorElement.outerHTML);
        console.log(">>>>>>>>>>>>>>>>>");
    }
    appendChatMessage(data.username, data.message, filesAnchorElement);
    chatLog.scrollTop = chatLog.scrollHeight;
};

chatSocket.onclose = function (_e) {
    console.error('Chat socket closed unexpectedly');
};

// --- Chat input history (arrow up/down) ---
const handleHistoryKeydown = (e) => {
    if (chatInput.disabled) {
        e.preventDefault();
        return;
    }
    const key = e.key || '';
    const code = e.keyCode || e.which || 0;
    const isUp = key === 'ArrowUp' || code === 38;
    const isDown = key === 'ArrowDown' || code === 40;
    if (key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        document.getElementById('chat-form').dispatchEvent(new Event('submit'));
        return;
    }
    if (isUp && chatInput.selectionStart === 0) {
        e.preventDefault();
        if (historyIndex === chatHistory.length) {
            tempInput = chatInput.value;
        }
        if (historyIndex > 0) {
            historyIndex -= 1;
            chatInput.value = chatHistory[historyIndex] || '';
            const end = chatInput.value.length;
            chatInput.setSelectionRange(end, end);
        }
    } else if (isDown && chatInput.selectionEnd === chatInput.value.length) {
        e.preventDefault();
        if (historyIndex < chatHistory.length) {
            historyIndex += 1;
            if (historyIndex === chatHistory.length) {
                chatInput.value = tempInput;
            } else {
                chatInput.value = chatHistory[historyIndex] || '';
            }
            const end = chatInput.value.length;
            chatInput.setSelectionRange(end, end);
        }
    }
};

chatInput.addEventListener('keydown', handleHistoryKeydown);
