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

function appendChatMessage(username, message, addedContent = null, timestampStr = null, toolCallsLog = null, multiTurnUsed = false, answerSuccess = null) {
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

    // --- "Create Flow" button: visible only for bot messages from a
    //     successful multi-turn execution that used tools.
    //     The `answerSuccess` flag is determined server-side by an LLM
    //     sub-prompt that classifies the answer as SUCCESS or FAILURE. ---
    if (username === 'Tlamatini' && multiTurnUsed && _hasSuccessfulToolCalls(toolCallsLog) && answerSuccess === true) {
        const createFlowBtn = document.createElement('button');
        createFlowBtn.classList.add('create-flow');
        createFlowBtn.innerHTML = '<i class="bi bi-diagram-3"></i> Create Flow';
        usernameDiv.appendChild(createFlowBtn);

        createFlowBtn.addEventListener('click', () => {
            _generateAndDownloadFlow(toolCallsLog);
        });
    }

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

// ============================================================
// Flow generation from multi-turn tool calls
// ============================================================

/**
 * Check whether the tool calls log contains at least one successful tool call.
 */
function _hasSuccessfulToolCalls(toolCallsLog) {
    if (!Array.isArray(toolCallsLog) || toolCallsLog.length === 0) return false;
    return toolCallsLog.some(entry => entry.success);
}

/**
 * Build a .flw JSON structure from the list of successful tool calls
 * and trigger a browser file download.
 *
 * Flow layout: Starter → Agent1 → Agent2 → … → Ender
 * Each agent node carries the configData derived from the tool call args.
 */
function _generateAndDownloadFlow(toolCallsLog) {
    // 1) Collect unique successful agents (preserve execution order,
    //    deduplicate by display name keeping the LAST config seen).
    const agentMap = new Map();   // displayName → {args, tool_name}
    const agentOrder = [];        // ordered unique display names
    for (const entry of toolCallsLog) {
        if (!entry.success) continue;
        // Use agent_display_name when available; otherwise derive a
        // human-readable name from the tool_name so every successful
        // tool call is represented in the generated flow.
        const name = entry.agent_display_name
            || (entry.tool_name || 'Unknown')
                .replace(/_/g, ' ')
                .replace(/\b\w/g, c => c.toUpperCase());
        if (!agentMap.has(name)) {
            agentOrder.push(name);
        }
        agentMap.set(name, { args: entry.args || {}, tool_name: entry.tool_name });
    }

    if (agentOrder.length === 0) {
        console.warn('--- Create Flow: no eligible agents found in tool_calls_log');
        return;
    }

    // 2) Build nodes: Starter + each agent + Ender
    const HORIZONTAL_GAP = 220;
    const TOP_OFFSET = 80;
    const nodes = [];

    // Starter node
    nodes.push({
        text: 'Starter',
        left: '50px',
        top: TOP_OFFSET + 'px',
        agentPurpose: 'Entry point, launches first agents',
        configData: { target_agents: [_toPoolName(agentOrder[0])] }
    });

    // Agent nodes (one per unique successful agent type)
    agentOrder.forEach((displayName, idx) => {
        const info = agentMap.get(displayName);
        const configData = _mapToolArgsToAgentConfig(displayName, info.args, info.tool_name);
        // Wire target_agents to next agent or Ender
        if (idx < agentOrder.length - 1) {
            configData.target_agents = [_toPoolName(agentOrder[idx + 1])];
        } else {
            configData.target_agents = [_toPoolName('Ender')];
        }
        // Wire source_agents to previous agent or Starter
        if (idx === 0) {
            configData.source_agents = [_toPoolName('Starter')];
        } else {
            configData.source_agents = [_toPoolName(agentOrder[idx - 1])];
        }

        nodes.push({
            text: displayName,
            left: (50 + (idx + 1) * HORIZONTAL_GAP) + 'px',
            top: TOP_OFFSET + 'px',
            agentPurpose: _agentPurpose(displayName),
            configData: configData
        });
    });

    // Ender node
    nodes.push({
        text: 'Ender',
        left: (50 + (agentOrder.length + 1) * HORIZONTAL_GAP) + 'px',
        top: TOP_OFFSET + 'px',
        agentPurpose: 'Terminates all agents, launches Cleaners',
        configData: {
            target_agents: agentOrder.map(n => _toPoolName(n)),
            source_agents: [_toPoolName(agentOrder[agentOrder.length - 1])]
        }
    });

    // 3) Build connections: linear chain Starter → A → B → … → Ender
    const connections = [];
    for (let i = 0; i < nodes.length - 1; i++) {
        connections.push({
            sourceIndex: i,
            targetIndex: i + 1,
            inputSlot: 0,
            outputSlot: 0
        });
    }

    const flowData = { nodes: nodes, connections: connections };

    // 4) Prompt user for filename and trigger download
    let filename = prompt('Enter a name for the flow file:', 'multi-turn-flow');
    if (filename === null) return;
    filename = filename.trim();
    if (!filename) return;
    if (!filename.toLowerCase().endsWith('.flw')) {
        filename += '.flw';
    }

    const blob = new Blob([JSON.stringify(flowData, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    console.log('--- Create Flow: downloaded ' + filename);
}

/**
 * Parse the raw tool-call args (which may contain an __arg1 request
 * string with key='value' pairs) into a proper config.yaml-compatible
 * dict for the given agent type.
 *
 * Wrapped chat-agent tools receive a single __arg1 string like:
 *   "Crawl url='https://example.com' system_prompt='Extract links'"
 * This function extracts the key='value' pairs and maps them to the
 * config keys each agent actually expects.
 */
function _mapToolArgsToAgentConfig(displayName, rawArgs, _toolName) {
    const config = {};

    // Extract key='value' pairs from the __arg1 request string.
    const requestStr = rawArgs.__arg1 || rawArgs.request || '';
    const pairs = _parseKeyValuePairs(requestStr);

    // Also include any direct key args (non __arg1) from the tool call.
    for (const [k, v] of Object.entries(rawArgs)) {
        if (k !== '__arg1' && k !== 'request') {
            pairs[k] = v;
        }
    }

    // Agent-specific config mapping.
    const lower = displayName.toLowerCase();
    if (lower === 'pythonxer') {
        config.script = pairs.script || requestStr || '';
        if (pairs.execute_forked_window !== undefined) {
            config.execute_forked_window = pairs.execute_forked_window === 'true';
        }
    } else if (lower === 'image interpreter') {
        config.images_pathfilenames = pairs.images_pathfilenames || pairs.path_filename || pairs.path || '';
        if (pairs.system_prompt) config.llm = { prompt: pairs.system_prompt };
        if (pairs.recursive) config.recursive = pairs.recursive === 'true';
    } else if (lower === 'prompter') {
        config.prompt = pairs.prompt || requestStr || '';
    } else if (lower === 'crawler') {
        config.url = pairs.url || '';
        if (pairs.system_prompt) config.system_prompt = pairs.system_prompt;
        if (pairs.content_mode) config.content_mode = pairs.content_mode;
    } else if (lower === 'executer') {
        config.command = pairs.command || requestStr || '';
        if (pairs.working_directory) config.working_directory = pairs.working_directory;
    } else if (lower === 'gitter') {
        config.repo_path = pairs.repo_path || '';
        config.operation = pairs.operation || '';
        if (pairs.args) config.args = pairs.args;
    } else if (lower === 'apirer') {
        config.url = pairs.url || '';
        config.method = pairs.method || 'GET';
        if (pairs.headers) config.headers = pairs.headers;
        if (pairs.body) config.body = pairs.body;
    } else if (lower === 'ssher') {
        config.host = pairs.host || '';
        config.command = pairs.command || '';
        if (pairs.username) config.username = pairs.username;
    } else if (lower === 'file creator') {
        config.filepath = pairs.filepath || '';
        config.content = pairs.content || '';
    } else if (lower === 'file extractor') {
        config.path = pairs.path || '';
    } else if (lower === 'file interpreter') {
        config.path = pairs.path || '';
        if (pairs.system_prompt) config.system_prompt = pairs.system_prompt;
        if (pairs.reading_type) config.reading_type = pairs.reading_type;
    } else if (lower === 'sqler') {
        config.connection_string = pairs.connection_string || '';
        config.query = pairs.query || '';
    } else if (lower === 'summarize text' || lower === 'summarizer') {
        config.input_text = pairs.input_text || '';
        if (pairs.system_prompt) config.system_prompt = pairs.system_prompt;
    } else if (lower === 'dockerer') {
        config.command = pairs.command || requestStr || '';
    } else if (lower === 'kuberneter') {
        config.command = pairs.command || requestStr || '';
    } else if (lower === 'googler') {
        config.query = pairs.query || requestStr || '';
    } else if (lower === 'notifier') {
        config.title = pairs.title || '';
        config.message = pairs.message || '';
    } else if (lower === 'send email' || lower === 'emailer') {
        if (pairs['smtp.host']) config['smtp.host'] = pairs['smtp.host'];
        if (pairs['smtp.username']) config['smtp.username'] = pairs['smtp.username'];
        config.to = pairs.to || '';
        config.subject = pairs.subject || '';
        config.body = pairs.body || '';
    } else {
        // Fallback: copy all parsed pairs as-is.
        Object.assign(config, pairs);
    }

    return config;
}

/**
 * Parse key='value' and key="value" pairs from a request string.
 * Handles single-quoted, double-quoted, and unquoted values.
 * Also handles dotted keys like smtp.host='...'
 */
function _parseKeyValuePairs(str) {
    const result = {};
    if (!str || typeof str !== 'string') return result;

    // Match: key='value' or key="value" (value can span multiple lines via \n)
    const regex = /([\w.]+)\s*=\s*'((?:[^'\\]|\\.)*)'/g;
    let match;
    while ((match = regex.exec(str)) !== null) {
        result[match[1]] = match[2].replace(/\\'/g, "'").replace(/\\n/g, '\n');
    }

    // Also match key="value"
    const regex2 = /([\w.]+)\s*=\s*"((?:[^"\\]|\\.)*)"/g;
    while ((match = regex2.exec(str)) !== null) {
        if (!(match[1] in result)) {
            result[match[1]] = match[2].replace(/\\"/g, '"').replace(/\\n/g, '\n');
        }
    }

    return result;
}

/**
 * Convert an agent display name to its pool folder name convention.
 * e.g. "File Creator" → "file_creator", "Executer" → "executer"
 */
function _toPoolName(displayName) {
    return displayName.toLowerCase().replace(/[\s-]+/g, '_');
}

/**
 * Return a short purpose string for well-known agent types.
 */
function _agentPurpose(displayName) {
    const purposes = {
        'Starter': 'Entry point, launches first agents',
        'Ender': 'Terminates all agents, launches Cleaners',
        'Executer': 'Shell commands',
        'Pythonxer': 'Inline Python execution',
        'Crawler': 'Web crawling with LLM analysis',
        'Googler': 'Google search and text extraction',
        'Apirer': 'HTTP REST API calls',
        'Gitter': 'Git operations',
        'SSHer': 'SSH remote commands',
        'SCPer': 'SCP file transfer',
        'Dockerer': 'Docker commands',
        'Kuberneter': 'kubectl commands',
        'PSer': 'PowerShell commands',
        'Jenkinser': 'Jenkins job triggers',
        'SQLer': 'SQL queries',
        'Mongoxer': 'MongoDB operations',
        'Prompter': 'LLM prompt execution',
        'Summarizer': 'LLM text summarization',
        'File Creator': 'Creates files with specified content',
        'File Interpreter': 'LLM reads and interprets file contents',
        'File Extractor': 'Raw text extraction from documents',
        'Image Interpreter': 'LLM vision analysis',
        'Shoter': 'Screenshot capture',
        'Notifier': 'Desktop notification with sound',
        'Emailer': 'SMTP email sending',
        'Recmailer': 'IMAP email receiver',
        'Telegramer': 'Telegram messages',
        'Whatsapper': 'WhatsApp messages',
        'Monitor Log': 'LLM-powered log file monitor',
        'Monitor Netstat': 'LLM-powered network port monitor',
        'Parametrizer': 'Maps structured output between agents',
        'J-Decompiler': 'JAR/WAR decompilation',
        'Kyber Keygen': 'Post-quantum key pair generation',
        'Kyber Cipher': 'Post-quantum encryption',
        'Kyber Deciph': 'Post-quantum decryption',
        'Deleter': 'File deletion',
        'Move File': 'File move/rename',
    };
    return purposes[displayName] || displayName;
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
    appendChatMessage(data.username, data.message, filesAnchorElement, null,
        data.tool_calls_log || null, data.multi_turn_used || false,
        data.answer_success != null ? data.answer_success : null);
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
