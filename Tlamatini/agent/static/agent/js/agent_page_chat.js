// ============================================================
// agent_page_chat.js  –  Chat messaging, WebSocket & form submit
// ============================================================
/* global applyContextUiState */

const HTML_ENTITY_MAP = {
    '&amp;': '&',
    '&lt;': '<',
    '&gt;': '>',
    '&quot;': '"',
    '&#39;': "'",
    '&#x27;': "'",
};

function decodeHtmlEntities(text) {
    return String(text ?? '').replace(/&(amp|lt|gt|quot|#39|#x27);/g, (match) => HTML_ENTITY_MAP[match] || match);
}

function isSafeLoadCanvasFilename(filename) {
    return typeof filename === 'string'
        && filename.length > 0
        && !filename.split('').some(ch => ch.charCodeAt(0) <= 0x1F || '\\/><:"|?*'.includes(ch));
}

function appendPlainBotText(targetNode, text) {
    if (!text) {
        return;
    }

    targetNode.appendChild(document.createTextNode(decodeHtmlEntities(text)));
}

function buildSafeLoadCanvasLink(anchorHtml) {
    const match = String(anchorHtml).match(/<a\b[^>]*\bonclick=['"]loadCanvas\("([^"]+)"\);?['"][^>]*>([\s\S]*?)<\/a>/i);
    if (!match) {
        return null;
    }

    const filename = decodeHtmlEntities(match[1]);
    if (!isSafeLoadCanvasFilename(filename)) {
        return null;
    }

    const safeAnchor = document.createElement('a');
    const anchorLabel = decodeHtmlEntities(match[2].replace(/<[^>]*>/g, ''));

    safeAnchor.href = '#';
    safeAnchor.classList.add('chat-load-canvas-link');
    safeAnchor.style.fontWeight = '600';
    safeAnchor.style.color = 'white';
    safeAnchor.textContent = anchorLabel || `---Load in canvas: ${filename}---`;
    safeAnchor.addEventListener('click', (event) => {
        event.preventDefault();
        loadCanvas(filename);
    });
    return safeAnchor;
}

function appendFormattedBotContent(targetNode, message) {
    const source = String(message ?? '');
    let index = 0;

    while (index < source.length) {
        const nextTagIndex = source.indexOf('<', index);
        if (nextTagIndex === -1) {
            appendPlainBotText(targetNode, source.slice(index));
            return;
        }

        if (nextTagIndex > index) {
            appendPlainBotText(targetNode, source.slice(index, nextTagIndex));
        }

        const remaining = source.slice(nextTagIndex);
        const brMatch = remaining.match(/^<br\s*\/?>/i);
        if (brMatch) {
            targetNode.appendChild(document.createElement('br'));
            index = nextTagIndex + brMatch[0].length;
            continue;
        }

        if (remaining.startsWith('<strong>')) {
            const closeIndex = source.indexOf('</strong>', nextTagIndex + '<strong>'.length);
            if (closeIndex !== -1) {
                const strong = document.createElement('strong');
                appendFormattedBotContent(strong, source.slice(nextTagIndex + '<strong>'.length, closeIndex));
                targetNode.appendChild(strong);
                index = closeIndex + '</strong>'.length;
                continue;
            }
        }

        if (remaining.startsWith('<code>')) {
            const closeIndex = source.indexOf('</code>', nextTagIndex + '<code>'.length);
            if (closeIndex !== -1) {
                const code = document.createElement('code');
                code.textContent = decodeHtmlEntities(source.slice(nextTagIndex + '<code>'.length, closeIndex));
                targetNode.appendChild(code);
                index = closeIndex + '</code>'.length;
                continue;
            }
        }

        if (/^<a\b/i.test(remaining)) {
            const closeIndex = source.indexOf('</a>', nextTagIndex);
            if (closeIndex !== -1) {
                const anchorHtml = source.slice(nextTagIndex, closeIndex + '</a>'.length);
                const safeAnchor = buildSafeLoadCanvasLink(anchorHtml);
                if (safeAnchor) {
                    targetNode.appendChild(safeAnchor);
                } else {
                    appendPlainBotText(targetNode, anchorHtml);
                }
                index = closeIndex + '</a>'.length;
                continue;
            }
        }

        appendPlainBotText(targetNode, '<');
        index = nextTagIndex + 1;
    }
}

function buildAutomatedMessageElement(message, addedContent = null) {
    const automatedMessage = document.createElement('div');

    automatedMessage.classList.add('automated-message');
    automatedMessage.innerHTML = String(message ?? '');

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
        automatedMessage.appendChild(document.createElement('br'));
        automatedMessage.appendChild(addedContent);
        console.log("xxxxxxxxxxxxxxxxxx");
        console.log(addedContent.data);
        console.log("xxxxxxxxxxxxxxxxxx");
    }

    return automatedMessage;
}

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
    } else if (
        message.toLowerCase().includes("out of the root directory")
        || message.toLowerCase().includes("outside the application root")
        || message.toLowerCase().includes("not a valid directory")
        || (message.toLowerCase().includes("directory") && message.toLowerCase().includes("does not exist"))
    ) {
        console.log("--- Context directory selection failed. message received: " + message);
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

    if (username === 'Tlamatini') {
        messageDiv.classList.add('bot-message');
        usernameDiv.style.color = '#55BBAA';
        messageContentDiv.appendChild(buildAutomatedMessageElement(message, addedContent));
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
    sendChatSocketMessage(JSON.stringify({
        'type': 'save-files-from-db',
        'message': files,
        'content': ''
    }));
}

// --- WebSocket message handler ---
chatSocket.onmessage = function (e) {
    const data = JSON.parse(e.data);

    if (data && data.username === 'Tlamatini' && !isBusyMessageRequest(data.message)) {
        setTitleBusy(false);
    }
    if (data && data.username === 'Tlamatini' && !isBusyMessageContext(data.message)) {
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
            applyContextUiState(data.context_path, data.context_type, data.context_filename);
            console.log('--- Context UI restored: ' + data.context_path);
        }
        return;
    }
    // Handle context-path-set: Server confirms full context path after set operation
    if (data.type === 'context-path-set') {
        console.log('--- Context path set by server:', data.context_path, 'type:', data.context_type);
        if (data.context_path) {
            applyContextUiState(data.context_path, data.context_type, data.context_filename);
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
    if (data && data.username === 'Tlamatini' && data.message.startsWith('_tree_:') === true) {
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

chatSocket.onopen = function () {
    console.log('--- Chat socket connected');
    restoreConnectedSocketUi();
};

chatSocket.onerror = function (_e) {
    console.error('Chat socket reported an error');
    applyDisconnectedSocketUi('Live connection problem. Use Reconnect or refresh before continue.');
};

chatSocket.onclose = function (_e) {
    console.error('Chat socket closed unexpectedly');
    applyDisconnectedSocketUi('Live connection lost. Use Reconnect or refresh before continue.');
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
