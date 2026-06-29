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
// agent_page_chat.js  –  Chat messaging, WebSocket & form submit
// ============================================================
/* global applyContextUiState, isSessionRestoredInfoMessage, showExecPermissionDialog */

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

// Sentinel inserted by the backend (response_parser.py::EXEC_REPORT_BOUNDARY)
// between the answer prose and the system-appended Execution Report / Ask-Execs
// denial banner. Keep this value byte-for-byte in sync with that constant.
const EXEC_REPORT_BOUNDARY = '<!--TLAMATINI_EXEC_REPORT_BOUNDARY-->';

function buildAutomatedMessageElement(message, addedContent = null) {
    const automatedMessage = document.createElement('div');

    automatedMessage.classList.add('automated-message');

    const raw = String(message ?? '');
    const boundaryIndex = raw.indexOf(EXEC_REPORT_BOUNDARY);
    if (boundaryIndex !== -1) {
        // Render the answer prose and the appended Execution Report in TWO
        // separate child elements, each with its own innerHTML parse. This is
        // what structurally prevents the execution tables from ever being
        // absorbed into a malformed / unclosed HTML table in the answer body
        // (the browser HTML-parser foster-parenting that mixed them before):
        // the two halves are parsed in completely independent DOM subtrees.
        const proseDiv = document.createElement('div');
        proseDiv.classList.add('automated-message-body');
        proseDiv.innerHTML = raw.slice(0, boundaryIndex);
        automatedMessage.appendChild(proseDiv);

        const systemDiv = document.createElement('div');
        systemDiv.classList.add('automated-message-execreport');
        systemDiv.innerHTML = raw.slice(boundaryIndex + EXEC_REPORT_BOUNDARY.length);
        automatedMessage.appendChild(systemDiv);
    } else {
        automatedMessage.innerHTML = raw;
    }

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
    } else if (lapseLoadingContext === true && isSessionRestoredInfoMessage(message)) {
        // The "Welcome back…" message arrives between the session-restored
        // event (which disabled the input) and the eventual loading-context
        // broadcast. It is purely informational — do NOT re-enable controls
        // here or the user would be allowed to send a request before the
        // contextual RAG chain has finished rebuilding.
        console.log("--- Session-restored welcome message received while context is loading — leaving controls disabled.");
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
    //     sub-prompt that classifies the answer as SUCCESS or FAILURE.
    //
    //     Additionally, every canonical agent name produced from the
    //     tool-calls log MUST exist in the Agents sidebar (registered in
    //     the DB). Otherwise the generated .flw would reference an agent
    //     type the canvas cannot resolve, breaking the flow at load time.
    //     We render the button asynchronously after _missingAgents()
    //     resolves so we can disable + tooltip it when validation fails.
    if (username === 'Tlamatini' && multiTurnUsed && _hasSuccessfulToolCalls(toolCallsLog) && answerSuccess === true) {
        const createFlowBtn = document.createElement('button');
        createFlowBtn.classList.add('create-flow');
        createFlowBtn.innerHTML = '<i class="bi bi-diagram-3"></i> Create Flow';
        usernameDiv.appendChild(createFlowBtn);

        // Start disabled until we've validated against the live agent
        // registry; flips back on if every canonical name resolves.
        createFlowBtn.disabled = true;
        createFlowBtn.classList.add('create-flow-validating');
        createFlowBtn.title = 'Validating agents…';

        _missingAgents(toolCallsLog).then(missing => {
            createFlowBtn.classList.remove('create-flow-validating');
            if (missing.length === 0) {
                createFlowBtn.disabled = false;
                createFlowBtn.title = '';
                createFlowBtn.addEventListener('click', () => {
                    _generateAndDownloadFlow(toolCallsLog);
                });
            } else {
                createFlowBtn.classList.add('create-flow-disabled');
                createFlowBtn.title = 'Cannot create flow: ' + missing.length
                    + ' agent type(s) not registered in the Agents sidebar — '
                    + missing.join(', ');
                console.warn('--- Create Flow: disabled, missing agents:', missing);
            }
        }).catch(err => {
            console.error('--- Create Flow: validation failed, hiding button:', err);
            createFlowBtn.remove();
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
 * Map wrapped-agent display names (from chat_agent_registry) to their
 * canonical DB agentDescription.  Needed because some wrapped agents use
 * display names that differ from the DB registration / template directory.
 */
const _DISPLAY_TO_CANONICAL = {
    'Send Email':       'Emailer',
    'Summarize Text':   'Summarizer',
    'Move File':        'Mover',
    'Kyber Deciph':     'Kyber-DeCipher',
    'Kyber Keygen':     'Kyber-KeyGen',
    'Kyber Cipher':     'Kyber-Cipher',
};

/** Resolve a display name to the canonical DB agent name. */
function _canonicalAgentName(displayName) {
    return _DISPLAY_TO_CANONICAL[displayName] || displayName;
}

/**
 * Lazy-loaded set of agentDescription values that exist in the DB
 * (i.e. are visible in the Agents sidebar). Cached for the lifetime of
 * the page so repeated Create-Flow validations don't re-hit the server.
 */
let _agentRegistryPromise = null;
function _loadAgentRegistry() {
    if (_agentRegistryPromise === null) {
        _agentRegistryPromise = fetch('/agent/list_all_agent_descriptions/')
            .then(r => {
                if (!r.ok) throw new Error('HTTP ' + r.status);
                return r.json();
            })
            .then(data => new Set((data && data.descriptions) || []))
            .catch(err => {
                // Reset so a later message can retry the fetch.
                _agentRegistryPromise = null;
                throw err;
            });
    }
    return _agentRegistryPromise;
}

/**
 * Given a tool_calls_log, return the list of canonical agent names that
 * the .flw generator would emit but that DON'T exist in the live Agents
 * sidebar. Empty list = every node will resolve at canvas load.
 *
 * Includes the implicit Starter and Ender wrappers added by
 * _generateAndDownloadFlow, so a flow with only Starter+Ender registered
 * is not falsely declared incomplete on a missing custom-agent install.
 */
async function _missingAgents(toolCallsLog) {
    const registry = await _loadAgentRegistry();
    const required = new Set(['Starter', 'Ender']);
    (toolCallsLog || [])
        .filter(entry => entry && entry.success)
        .forEach(entry => {
            const displayName = entry.agent_display_name
                || (entry.tool_name || 'Unknown')
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, c => c.toUpperCase());
            required.add(_canonicalAgentName(displayName));
        });
    const missing = [];
    required.forEach(name => {
        if (!registry.has(name)) missing.push(name);
    });
    return missing;
}

/**
 * Build a .flw JSON structure from the list of successful tool calls
 * and trigger a browser file download.
 *
 * Flow layout: Starter → Agent1 → Agent2 → … → Ender
 *
 * Key correctness invariants (these are the ones users previously lost):
 *
 * 1. **One node per successful tool call** — NOT one node per unique agent.
 *    If the LLM ran execute_command five times with five different
 *    commands, the flow must contain five Executer nodes, each with its
 *    own script. Collapsing by agent type throws away four of the five.
 *
 * 2. **Cardinal-suffixed pool names in every source_agents/target_agents
 *    list.** Pool folders on disk are always ``<base>_<N>`` (e.g. the
 *    second Executer ends up at ``pools/executer_2``), because the .flw
 *    loader calls ``registerItem`` which clears counters and increments
 *    per base name in node order. If ``target_agents`` emits a bare
 *    "executer" instead of "executer_2", Starter tries to launch a pool
 *    folder that does not exist and the chain dies on the first hop.
 *
 * 3. **Only set config fields the tool call actually populated.** Passing
 *    empty-string defaults forces a deep-merge overwrite that destroys
 *    the template's legitimate default value. Always prefer omission to
 *    an empty string.
 */
async function _generateAndDownloadFlow(toolCallsLog) {
    // 1) Keep EVERY successful tool call — preserves order + fidelity.
    //    Each entry → its own flow node; no dedup by agent type.
    const successfulCalls = (toolCallsLog || [])
        .filter(entry => entry && entry.success)
        .map(entry => {
            const displayName = entry.agent_display_name
                || (entry.tool_name || 'Unknown')
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, c => c.toUpperCase());
            return {
                displayName,
                canonical: _canonicalAgentName(displayName),
                args: entry.args || {},
                toolName: entry.tool_name,
            };
        });

    if (successfulCalls.length === 0) {
        console.warn('--- Create Flow: no eligible agents found in tool_calls_log');
        return;
    }

    // 2) Assign cardinal-suffixed pool names that will MATCH what the
    //    loader's `registerItem` increments to (counters reset per load,
    //    so the first Executer becomes executer_1, second → executer_2…).
    const baseCounters = {};
    const poolNames = successfulCalls.map(call => {
        const base = _poolBase(call.canonical);
        baseCounters[base] = (baseCounters[base] || 0) + 1;
        return `${base}_${baseCounters[base]}`;
    });
    const starterPool = 'starter_1';
    const enderPool = 'ender_1';

    // 3) Build nodes: Starter + one per tool call + Ender
    const HORIZONTAL_GAP = 220;
    const TOP_OFFSET = 80;
    const nodes = [];

    nodes.push({
        text: 'Starter',
        left: '50px',
        top: TOP_OFFSET + 'px',
        agentPurpose: 'Entry point, launches first agents',
        configData: { target_agents: [poolNames[0]] }
    });

    successfulCalls.forEach((call, idx) => {
        const configData = _mapToolArgsToAgentConfig(call.canonical, call.args, call.toolName);
        // Wire downstream → next call's pool name, or Ender if last.
        configData.target_agents = [idx < successfulCalls.length - 1 ? poolNames[idx + 1] : enderPool];
        // Wire upstream → previous call's pool name, or Starter if first.
        configData.source_agents = [idx === 0 ? starterPool : poolNames[idx - 1]];

        // Parametrizer uses singular source_agent / target_agent fields.
        if (call.canonical.toLowerCase() === 'parametrizer') {
            configData.source_agent = configData.source_agents[0] || '';
            configData.target_agent = configData.target_agents[0] || '';
        }

        nodes.push({
            text: call.canonical,
            left: (50 + (idx + 1) * HORIZONTAL_GAP) + 'px',
            top: TOP_OFFSET + 'px',
            agentPurpose: _agentPurpose(call.canonical),
            configData: configData
        });
    });

    nodes.push({
        text: 'Ender',
        left: (50 + (successfulCalls.length + 1) * HORIZONTAL_GAP) + 'px',
        top: TOP_OFFSET + 'px',
        agentPurpose: 'Terminates all agents, launches Cleaners',
        configData: {
            // Ender's target_agents is the list of ALL agents to terminate
            // (every pool name, not just the last one).
            target_agents: poolNames.slice(),
            source_agents: [poolNames[poolNames.length - 1]]
        }
    });

    // 4) Build connections: linear chain Starter → A → B → … → Ender
    const connections = [];
    for (let i = 0; i < nodes.length - 1; i++) {
        connections.push({
            sourceIndex: i,
            targetIndex: i + 1,
            inputSlot: 0,
            outputSlot: 0
        });
    }

    let flowData = { nodes: nodes, connections: connections };
    flowData = await _normalizeChatFlowBeforeDownload(toolCallsLog, flowData);

    // 5) Prompt user for filename and trigger download
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

async function _normalizeChatFlowBeforeDownload(toolCallsLog, flowData) {
    try {
        const response = await fetch('/agent/flow_from_tool_calls/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': typeof getCsrfToken === 'function' ? getCsrfToken() : ''
            },
            credentials: 'same-origin',
            body: JSON.stringify({ tool_calls_log: toolCallsLog || [], flow_data: flowData })
        });
        const result = await response.json();
        if (response.ok && result.success && result.flow) {
            return result.flow;
        }
        console.warn('--- Create Flow: backend normalization unavailable, using legacy flow:', result);
    } catch (err) {
        console.warn('--- Create Flow: backend normalization failed, using legacy flow:', err);
    }
    return flowData;
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
 *
 * IMPORTANT: The field names produced here MUST match the config.yaml
 * template fields exactly.  A mismatch means the deep-merge in the
 * backend adds an extra key while the template default stays unchanged.
 *
 * @param {string} canonicalName  Canonical DB agent name (e.g. "Executer")
 * @param {Object} rawArgs        Tool-call args dict
 * @param {string} _toolName      Raw tool name (unused, kept for API compat)
 */
function _mapToolArgsToAgentConfig(canonicalName, rawArgs, _toolName) {
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

    // ── Helper: safely build a nested sub-object from dotted pairs ──
    function collectDotted(prefix) {
        const obj = {};
        const dotPrefix = prefix + '.';
        for (const [k, v] of Object.entries(pairs)) {
            if (k.startsWith(dotPrefix)) {
                obj[k.slice(dotPrefix.length)] = v;
            }
        }
        return obj;
    }

    // Agent-specific config mapping — field names match config.yaml templates.
    //
    // **Rule:** only set a field when we have a NON-EMPTY value for it.
    // The backend deep-merges this dict over the template's config.yaml,
    // so ``config.foo = ''`` would overwrite a legitimate template default
    // with an empty string. Use the ``set(key, value)`` helper below so
    // the empty-string trap can't re-enter a branch by accident.
    const set = (key, value) => {
        if (value === undefined || value === null) return;
        if (typeof value === 'string' && value.trim() === '') return;
        config[key] = value;
    };
    const lower = canonicalName.toLowerCase();

    // ── Executer ─────────────────────────────────────────────────────
    // Template field: script (NOT "command")
    if (lower === 'executer') {
        set('script', pairs.command || pairs.script || requestStr);
        if (pairs.non_blocking !== undefined) {
            config.non_blocking = String(pairs.non_blocking) === 'true';
        }
        if (pairs.execute_forked_window !== undefined) {
            config.execute_forked_window = String(pairs.execute_forked_window) === 'true';
        }

    // ── Pythonxer ────────────────────────────────────────────────────
    // Template field: script
    } else if (lower === 'pythonxer') {
        set('script', pairs.script || pairs.command || requestStr);
        if (pairs.execute_forked_window !== undefined) {
            config.execute_forked_window = String(pairs.execute_forked_window) === 'true';
        }

    // ── SSHer (DB: "Ssher") ──────────────────────────────────────────
    // Template fields: user, ip, script
    } else if (lower === 'ssher') {
        set('user', pairs.username || pairs.user);
        set('ip', pairs.host || pairs.ip);
        set('script', pairs.command || pairs.script);

    // ── SCPer (DB: "Scper") ──────────────────────────────────────────
    // Template fields: user, ip, file, direction
    } else if (lower === 'scper') {
        set('user', pairs.username || pairs.user);
        set('ip', pairs.host || pairs.ip);
        set('file', pairs.local_path || pairs.file || pairs.remote_path);
        set('direction', pairs.direction);

    // ── SQLer (DB: "Sqler") ──────────────────────────────────────────
    // Template fields: sql_connection (nested), script
    } else if (lower === 'sqler') {
        set('script', pairs.query || pairs.script);
        const sqlConn = collectDotted('sql_connection');
        if (pairs.connection_string) sqlConn.server = pairs.connection_string;
        if (Object.keys(sqlConn).length > 0) config.sql_connection = sqlConn;

    // ── Gitter ───────────────────────────────────────────────────────
    // Template fields: repo_path, command, branch, commit_message, remote, custom_command
    } else if (lower === 'gitter') {
        set('repo_path', pairs.repo_path);
        set('command', pairs.operation || pairs.command);
        set('branch', pairs.branch);
        set('commit_message', pairs.commit_message);
        set('remote', pairs.remote);
        set('custom_command', pairs.args || pairs.custom_command);

    // ── Apirer ───────────────────────────────────────────────────────
    // Template fields: url, method, headers (object), body
    } else if (lower === 'apirer') {
        set('url', pairs.url);
        set('method', pairs.method);
        if (pairs.headers) {
            try { config.headers = JSON.parse(pairs.headers); }
            catch (_e) { config.headers = pairs.headers; }
        }
        set('body', pairs.body);

    // ── Unrealer ─────────────────────────────────────────────────────
    // Template fields: host, port, command, params (object), connect_timeout,
    // read_timeout. The LLM emits dotted ``params.<name>`` keys for individual
    // Unreal command arguments (e.g. params.name, params.location), which we
    // gather via collectDotted so the resulting node's ``params`` is a nested
    // YAML map matching the Unreal MCP {"type":<command>,"params":{...}}
    // wire format.
    } else if (lower === 'unrealer') {
        set('host', pairs.host);
        if (pairs.port !== undefined && pairs.port !== '') {
            const portNum = parseInt(pairs.port, 10);
            if (!Number.isNaN(portNum)) config.port = portNum;
        }
        set('command', pairs.command);
        const unrealParams = collectDotted('params');
        // Allow a bare ``params={...}`` form too (some LLMs embed full JSON).
        if (pairs.params && Object.keys(unrealParams).length === 0) {
            try {
                const parsed = JSON.parse(pairs.params);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    Object.assign(unrealParams, parsed);
                }
            } catch (_e) { /* leave unrealParams as-is */ }
        }
        // Coerce list-shaped params (location/rotation/scale) from string into array
        for (const k of Object.keys(unrealParams)) {
            const v = unrealParams[k];
            if (typeof v === 'string' && v.startsWith('[') && v.endsWith(']')) {
                try { unrealParams[k] = JSON.parse(v); }
                catch (_e) { /* keep string */ }
            }
        }
        if (Object.keys(unrealParams).length > 0) config.params = unrealParams;
        if (pairs.connect_timeout !== undefined && pairs.connect_timeout !== '') {
            const n = parseFloat(pairs.connect_timeout);
            if (!Number.isNaN(n)) config.connect_timeout = n;
        }
        if (pairs.read_timeout !== undefined && pairs.read_timeout !== '') {
            const n = parseFloat(pairs.read_timeout);
            if (!Number.isNaN(n)) config.read_timeout = n;
        }

    // ── Blenderer ────────────────────────────────────────────────────
    // Template fields: host, port, command, strict_json (bool), params
    // (object), connect_timeout, read_timeout. The Blender MCP wire format is
    // {"type":"execute","code":...} — the LLM emits dotted ``params.<name>``
    // keys (params.code, params.object_name, params.type, params.location,
    // params.color, params.output_path) which we gather via collectDotted into
    // the nested ``params`` map the agent forwards.
    } else if (lower === 'blenderer') {
        set('host', pairs.host);
        if (pairs.port !== undefined && pairs.port !== '') {
            const portNum = parseInt(pairs.port, 10);
            if (!Number.isNaN(portNum)) config.port = portNum;
        }
        set('command', pairs.command);
        if (pairs.strict_json !== undefined && pairs.strict_json !== '') {
            config.strict_json = (pairs.strict_json === true || String(pairs.strict_json).toLowerCase() === 'true');
        }
        const blenderParams = collectDotted('params');
        // Allow a bare ``params={...}`` form too (some LLMs embed full JSON).
        if (pairs.params && Object.keys(blenderParams).length === 0) {
            try {
                const parsed = JSON.parse(pairs.params);
                if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                    Object.assign(blenderParams, parsed);
                }
            } catch (_e) { /* leave blenderParams as-is */ }
        }
        // Coerce list-shaped params (location/color) from string into array
        for (const k of Object.keys(blenderParams)) {
            const v = blenderParams[k];
            if (typeof v === 'string' && v.startsWith('[') && v.endsWith(']')) {
                try { blenderParams[k] = JSON.parse(v); }
                catch (_e) { /* keep string */ }
            }
        }
        if (Object.keys(blenderParams).length > 0) config.params = blenderParams;
        if (pairs.connect_timeout !== undefined && pairs.connect_timeout !== '') {
            const n = parseFloat(pairs.connect_timeout);
            if (!Number.isNaN(n)) config.connect_timeout = n;
        }
        if (pairs.read_timeout !== undefined && pairs.read_timeout !== '') {
            const n = parseFloat(pairs.read_timeout);
            if (!Number.isNaN(n)) config.read_timeout = n;
        }

    // ── Playwrighter ─────────────────────────────────────────────────
    // Template fields: start_url, browser, headless (bool), timeout_ms (int),
    // nav_wait_until, user_agent, storage_state_in/out, output_file, and the
    // chat-only steps_json (a JSON array string). We parse steps_json into a
    // real ``steps`` list so the generated .flw node carries the canvas
    // authoring form (the runtime accepts either; the canvas dialog +
    // Parametrizer expect a parsed list).
    } else if (lower === 'playwrighter') {
        set('start_url', pairs.start_url || pairs.url);
        set('browser', pairs.browser);
        if (pairs.headless !== undefined && pairs.headless !== '') {
            config.headless = String(pairs.headless) === 'true';
        }
        if (pairs.timeout_ms !== undefined && pairs.timeout_ms !== '') {
            const n = parseInt(pairs.timeout_ms, 10);
            if (!Number.isNaN(n)) config.timeout_ms = n;
        }
        if (pairs.hold_open_seconds !== undefined && pairs.hold_open_seconds !== '') {
            const n = parseInt(pairs.hold_open_seconds, 10);
            if (!Number.isNaN(n)) config.hold_open_seconds = n;
        }
        if (pairs.hold_open_ms !== undefined && pairs.hold_open_ms !== '') {
            const n = parseInt(pairs.hold_open_ms, 10);
            if (!Number.isNaN(n)) config.hold_open_ms = n;
        }
        set('nav_wait_until', pairs.nav_wait_until);
        set('user_agent', pairs.user_agent);
        set('storage_state_in', pairs.storage_state_in);
        set('storage_state_out', pairs.storage_state_out);
        set('output_file', pairs.output_file);
        if (pairs.steps_json) {
            try {
                const parsed = JSON.parse(pairs.steps_json);
                if (Array.isArray(parsed) && parsed.length > 0) config.steps = parsed;
            } catch (_e) {
                // Parse failed — pass the raw string through; the runtime
                // json.loads it at execution time as a fallback.
                set('steps_json', pairs.steps_json);
            }
        }

    // ── Crawler ──────────────────────────────────────────────────────
    // Template fields: url, system_prompt, content_mode
    } else if (lower === 'crawler') {
        set('url', pairs.url);
        set('system_prompt', pairs.system_prompt);
        set('content_mode', pairs.content_mode);

    // ── Prompter ─────────────────────────────────────────────────────
    // Template field: prompt
    } else if (lower === 'prompter') {
        set('prompt', pairs.prompt || requestStr);

    // ── Googler ──────────────────────────────────────────────────────
    // Template fields: query, number_of_results
    } else if (lower === 'googler') {
        set('query', pairs.query || requestStr);
        if (pairs.number_of_results) {
            const n = parseInt(pairs.number_of_results, 10);
            if (!Number.isNaN(n)) config.number_of_results = n;
        }

    // ── Dockerer ─────────────────────────────────────────────────────
    // Template field: command
    } else if (lower === 'dockerer') {
        set('command', pairs.command || requestStr);

    // ── MCP Doctor ───────────────────────────────────────────────────
    // Template fields: server_key, catalog_path, source_url, mode,
    // include_catalog. This is the canvas/Multi-Turn diagnostic agent for
    // External MCP onboarding.
    } else if (lower === 'mcp doctor') {
        set('server_key', pairs.server_key || pairs.server || pairs.name);
        set('catalog_path', pairs.catalog_path || pairs.path);
        set('source_url', pairs.source_url || pairs.url);
        set('mode', pairs.mode || pairs.action);
        if (pairs.include_catalog !== undefined && pairs.include_catalog !== '') {
            config.include_catalog = String(pairs.include_catalog).toLowerCase() === 'true';
        }

    // ── Instant Messaging Doctor ─────────────────────────────────────
    // Template fields: mode, platform, contact_name, message, template,
    // retry_send, telegram.*, whatsapp.*, ollama.*.
    } else if (lower === 'instant messaging doctor') {
        set('mode', pairs.mode || pairs.action);
        set('platform', pairs.platform);
        set('contact_name', pairs.contact_name || pairs.contact);
        set('message', pairs.message || pairs.text);
        set('template', pairs.template);
        set('template_language', pairs.template_language || pairs.language);
        if (pairs.template_params) {
            config.template_params = pairs.template_params;
        }
        if (pairs.retry_send !== undefined && pairs.retry_send !== '') {
            config.retry_send = String(pairs.retry_send).toLowerCase() === 'true';
        }
        const telegramCfg = collectDotted('telegram');
        if (pairs.telegram_recipient) telegramCfg.chat_id = pairs.telegram_recipient;
        if (Object.keys(telegramCfg).length > 0) config.telegram = telegramCfg;
        const whatsappCfg = collectDotted('whatsapp');
        if (pairs.whatsapp_to) whatsappCfg.to = pairs.whatsapp_to;
        if (Object.keys(whatsappCfg).length > 0) config.whatsapp = whatsappCfg;
        const ollamaCfg = collectDotted('ollama');
        if (Object.keys(ollamaCfg).length > 0) config.ollama = ollamaCfg;
        set('failure_log_excerpt', pairs.failure_log_excerpt);
        set('failure_log_path', pairs.failure_log_path);

    // ── Kuberneter ───────────────────────────────────────────────────
    // Template fields: command, namespace, extra_args, custom_command
    } else if (lower === 'kuberneter') {
        set('command', pairs.command || requestStr);
        set('namespace', pairs.namespace);
        set('extra_args', pairs.extra_args);

    // ── Jenkinser ────────────────────────────────────────────────────
    // Template fields: jenkins_url, job_name, user, api_token
    } else if (lower === 'jenkinser') {
        set('jenkins_url', pairs.jenkins_url);
        set('job_name', pairs.job_name);
        set('user', pairs.user);
        set('api_token', pairs.api_token);

    // ── Mongoxer ─────────────────────────────────────────────────────
    // Template fields: mongo_connection (nested), script
    } else if (lower === 'mongoxer') {
        const mongoConn = collectDotted('mongodb');
        if (pairs.connection_string) mongoConn.connection_string = pairs.connection_string;
        if (pairs['mongodb.connection_string']) {
            mongoConn.connection_string = pairs['mongodb.connection_string'];
        }
        if (Object.keys(mongoConn).length > 0) config.mongo_connection = mongoConn;
        set('script', pairs['mongodb.operation'] || pairs.script);

    // ── File Creator ─────────────────────────────────────────────────
    // Template fields: file_path (with underscore!), content
    } else if (lower === 'file creator') {
        set('file_path', pairs.filepath || pairs.file_path);
        set('content', pairs.content);

    // ── File Extractor ───────────────────────────────────────────────
    // Template field: path_filenames
    } else if (lower === 'file extractor') {
        set('path_filenames', pairs.path || pairs.path_filenames);
        if (pairs.line_numbers !== undefined && pairs.line_numbers !== '') {
            config.line_numbers = (String(pairs.line_numbers).toLowerCase() === 'true');
        }
        for (const k of ['offset', 'limit']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }

    // ── File Interpreter ─────────────────────────────────────────────
    // Template fields: path_filenames, reading_type, llm.prompt
    } else if (lower === 'file interpreter') {
        set('path_filenames', pairs.path || pairs.path_filenames);
        set('reading_type', pairs.reading_type);
        if (pairs.system_prompt) config.llm = { prompt: pairs.system_prompt };

    // ── Image Interpreter ────────────────────────────────────────────
    // Template fields: images_pathfilenames, llm.prompt, recursive
    } else if (lower === 'image interpreter') {
        set('images_pathfilenames', pairs.images_pathfilenames || pairs.path_filename || pairs.path);
        if (pairs.system_prompt) config.llm = { prompt: pairs.system_prompt };
        if (pairs.recursive !== undefined) config.recursive = String(pairs.recursive) === 'true';

    // ── Summarizer ───────────────────────────────────────────────────
    // Template field: system_prompt (NO input_text field exists!)
    } else if (lower === 'summarizer') {
        set('system_prompt', pairs.system_prompt);

    // ── PSer (DB: "Pser") ────────────────────────────────────────────
    // Template field: likely_process_name
    } else if (lower === 'pser') {
        set('likely_process_name', pairs.command || pairs.likely_process_name || requestStr);

    // ── Emailer ──────────────────────────────────────────────────────
    // Template fields: smtp (nested), email (nested), pattern
    } else if (lower === 'emailer') {
        const smtp = collectDotted('smtp');
        if (smtp.port) smtp.port = parseInt(smtp.port, 10) || 587;
        if (Object.keys(smtp).length > 0) config.smtp = smtp;

        const email = {};
        if (pairs.to) email.to_addresses = [pairs.to];
        if (pairs.subject) email.subject = pairs.subject;
        if (pairs.body) email.body = pairs.body;
        if (pairs['email.from_address']) email.from_address = pairs['email.from_address'];
        if (pairs['email.to_addresses']) email.to_addresses = [pairs['email.to_addresses']];
        if (pairs['email.subject']) email.subject = pairs['email.subject'];
        if (pairs['email.body']) email.body = pairs['email.body'];
        const attach = pairs['email.attachments'] || pairs.attachments;
        if (attach) email.attachments = Array.isArray(attach) ? attach : [attach];
        if (Object.keys(email).length > 0) config.email = email;

    // ── Notifier ─────────────────────────────────────────────────────
    // Template fields: target (nested: search_strings, outcome_detail, sound_enabled)
    } else if (lower === 'notifier') {
        const target = collectDotted('target');
        // Map friendly title/message to template fields
        if (pairs.title && !target.search_strings) target.search_strings = pairs.title;
        if (pairs.message && !target.outcome_detail) target.outcome_detail = pairs.message;
        if (target.sound_enabled !== undefined) {
            target.sound_enabled = String(target.sound_enabled) === 'true';
        }
        if (Object.keys(target).length > 0) config.target = target;

    // ── Shoter ───────────────────────────────────────────────────────
    // Template field: output_dir
    } else if (lower === 'shoter') {
        set('output_dir', pairs.output_path || pairs.output_dir);

    // ── Camcorder ────────────────────────────────────────────────────
    // Template fields: camera_index, capture_mode, video_duration_seconds,
    //                  video_fps, resolution_width, resolution_height,
    //                  warmup_seconds, output_dir
    // -- Editor (surgical in-place edit) --
    } else if (lower === 'editor') {
        set('file_path', pairs.file_path);
        set('old_string', pairs.old_string);
        set('new_string', pairs.new_string);
        set('old_string_b64', pairs.old_string_b64);
        set('new_string_b64', pairs.new_string_b64);
        if (pairs.replace_all !== undefined && pairs.replace_all !== '') {
            config.replace_all = (String(pairs.replace_all).toLowerCase() === 'true');
        }
    // -- Grepper (regex content search) --
    } else if (lower === 'grepper') {
        set('pattern', pairs.pattern);
        set('path', pairs.path);
        set('glob', pairs.glob);
        set('output_mode', pairs.output_mode);
        if (pairs.case_insensitive !== undefined && pairs.case_insensitive !== '') {
            config.case_insensitive = (String(pairs.case_insensitive).toLowerCase() === 'true');
        }
        if (pairs.max_results !== undefined && pairs.max_results !== '') {
            const mr = parseInt(pairs.max_results, 10);
            if (!Number.isNaN(mr)) config.max_results = mr;
        }
    // -- Globber (file pattern search) --
    } else if (lower === 'globber') {
        set('pattern', pairs.pattern);
        set('path', pairs.path);
        set('sort_by', pairs.sort_by);
        if (pairs.max_results !== undefined && pairs.max_results !== '') {
            const mr = parseInt(pairs.max_results, 10);
            if (!Number.isNaN(mr)) config.max_results = mr;
        }
    } else if (lower === 'camcorder') {
        if (pairs.camera_index !== undefined && pairs.camera_index !== '') {
            const ci = parseInt(pairs.camera_index, 10);
            if (!Number.isNaN(ci)) config.camera_index = ci;
        }
        set('capture_mode', pairs.capture_mode);
        if (pairs.video_duration_seconds !== undefined && pairs.video_duration_seconds !== '') {
            const vd = parseInt(pairs.video_duration_seconds, 10);
            if (!Number.isNaN(vd)) config.video_duration_seconds = vd;
        }
        if (pairs.video_fps !== undefined && pairs.video_fps !== '') {
            const vf = parseFloat(pairs.video_fps);
            if (!Number.isNaN(vf)) config.video_fps = vf;
        }
        for (const k of ['resolution_width', 'resolution_height']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        if (pairs.warmup_seconds !== undefined && pairs.warmup_seconds !== '') {
            const ws = parseFloat(pairs.warmup_seconds);
            if (!Number.isNaN(ws)) config.warmup_seconds = ws;
        }
        set('output_dir', pairs.output_dir);

    // ── Recorder ─────────────────────────────────────────────────────
    // Template fields: device_index, device_name, record_seconds,
    //                  sample_rate, channels, input_gain_percent, output_dir
    } else if (lower === 'recorder') {
        if (pairs.device_index !== undefined && pairs.device_index !== '') {
            const di = parseInt(pairs.device_index, 10);
            if (!Number.isNaN(di)) config.device_index = di;
        }
        set('device_name', pairs.device_name);
        for (const k of ['record_seconds', 'sample_rate', 'channels', 'input_gain_percent']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        set('output_dir', pairs.output_dir);

    // ── Whisperer (speech-to-text) ───────────────────────────────────
    // Template fields: input_source, audio_file, record_seconds,
    //                  device_index, device_name, sample_rate, channels,
    //                  input_gain_percent, engine, model, device,
    //                  compute_type, language, task, beam_size, vad_filter,
    //                  cloud_api_key, cloud_base_url, cloud_model,
    //                  ollama_cleanup, cleanup_model, output_dir
    } else if (lower === 'whisperer') {
        set('input_source', pairs.input_source);
        set('audio_file', pairs.audio_file || pairs.file || pairs.path);
        if (pairs.device_index !== undefined && pairs.device_index !== '') {
            const di = parseInt(pairs.device_index, 10);
            if (!Number.isNaN(di)) config.device_index = di;
        }
        set('device_name', pairs.device_name);
        for (const k of ['record_seconds', 'sample_rate', 'channels', 'input_gain_percent', 'beam_size']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        set('engine', pairs.engine);
        set('model', pairs.model);
        set('device', pairs.device);
        set('compute_type', pairs.compute_type);
        set('language', pairs.language);
        set('task', pairs.task);
        if (pairs.vad_filter !== undefined && pairs.vad_filter !== '') {
            config.vad_filter = String(pairs.vad_filter).toLowerCase() === 'true';
        }
        if (pairs.ollama_cleanup !== undefined && pairs.ollama_cleanup !== '') {
            config.ollama_cleanup = String(pairs.ollama_cleanup).toLowerCase() === 'true';
        }
        set('cloud_model', pairs.cloud_model);
        set('cleanup_model', pairs.cleanup_model);
        set('output_dir', pairs.output_dir);

    // ── AudioPlayer ──────────────────────────────────────────────────
    // Template fields: audio_file, device_index, device_name,
    //                  volume_percent, time_played, sample_rate
    } else if (lower === 'audioplayer') {
        set('audio_file', pairs.audio_file || pairs.file || pairs.path);
        if (pairs.device_index !== undefined && pairs.device_index !== '') {
            const di = parseInt(pairs.device_index, 10);
            if (!Number.isNaN(di)) config.device_index = di;
        }
        set('device_name', pairs.device_name);
        for (const k of ['volume_percent', 'time_played', 'sample_rate']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = Number(pairs[k]);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }

    // ── VideoPlayer ──────────────────────────────────────────────────
    // Template fields: video_file, display_index, volume_percent,
    //                  time_played, window_width, window_height,
    //                  fullscreen, keep_aspect
    } else if (lower === 'videoplayer') {
        set('video_file', pairs.video_file || pairs.file || pairs.path);
        for (const k of ['display_index', 'window_width', 'window_height']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        for (const k of ['volume_percent', 'time_played']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = Number(pairs[k]);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        for (const k of ['fullscreen', 'keep_aspect']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                config[k] = String(pairs[k]).toLowerCase() === 'true';
            }
        }

    // ── Talker (TTS via Ollama) ──────────────────────────────────────
    // Template fields: input_text, ollama_url, ollama_token, model, language,
    //                  voice, gender, emotion, include_language_in_prompt,
    //                  temperature, top_p, top_k, min_p, repetition_penalty,
    //                  max_tokens, seed, request_timeout, play_audio,
    //                  device_index, device_name, volume_percent, sample_rate,
    //                  output_dir
    } else if (lower === 'talker') {
        set('input_text', pairs.input_text || pairs.text);
        set('ollama_url', pairs.ollama_url || pairs.url || pairs.host);
        set('ollama_token', pairs.ollama_token || pairs.token);
        set('model', pairs.model);
        set('language', pairs.language || pairs.lang);
        // FEMALE VOICE ONLY by design — Tlamatini is female and NEVER speaks with
        // a male voice (the Talker agent refuses a male voice at runtime by closing
        // its execution entirely; see talker.py::resolve_voice). As defence in
        // depth, only let a permitted FEMALE voice / gender='female' into the
        // generated .flw; silently drop a male or unverifiable voice/gender so no
        // male voice can ever be written into a flow artifact.
        const TALKER_FEMALE_VOICES = ['tara', 'leah', 'jess', 'mia', 'zoe'];
        const reqVoice = (pairs.voice || '').toString().trim().toLowerCase();
        if (reqVoice && TALKER_FEMALE_VOICES.includes(reqVoice)) {
            set('voice', pairs.voice);
        }
        if ((pairs.gender || '').toString().trim().toLowerCase() === 'female') {
            set('gender', pairs.gender);
        }
        set('emotion', pairs.emotion);
        set('device_name', pairs.device_name);
        set('output_dir', pairs.output_dir);
        for (const k of ['include_language_in_prompt', 'play_audio']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                config[k] = String(pairs[k]).toLowerCase() === 'true';
            }
        }
        if (pairs.device_index !== undefined && pairs.device_index !== '') {
            const di = parseInt(pairs.device_index, 10);
            if (!Number.isNaN(di)) config.device_index = di;
        }
        for (const k of ['top_k', 'max_tokens', 'seed', 'volume_percent', 'sample_rate', 'request_timeout']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        for (const k of ['temperature', 'top_p', 'min_p', 'repetition_penalty']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = Number(pairs[k]);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }

    // ── Windower ─────────────────────────────────────────────────────
    // Template fields: action, window_title, match_mode, match_index,
    //                  pos_x, pos_y, width, height, arrange_mode,
    //                  activate_after, fail_if_absent
    } else if (lower === 'windower') {
        set('action', pairs.action);
        set('window_title', pairs.window_title);
        set('match_mode', pairs.match_mode);
        if (pairs.match_index !== undefined && pairs.match_index !== '') {
            const mi = parseInt(pairs.match_index, 10);
            if (!Number.isNaN(mi)) config.match_index = mi;
        }
        for (const k of ['pos_x', 'pos_y', 'width', 'height']) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        }
        set('arrange_mode', pairs.arrange_mode);
        if (pairs.activate_after !== undefined && pairs.activate_after !== '') {
            config.activate_after = String(pairs.activate_after) === 'true';
        }
        if (pairs.fail_if_absent !== undefined && pairs.fail_if_absent !== '') {
            config.fail_if_absent = String(pairs.fail_if_absent) === 'true';
        }

    // ── Kalier ───────────────────────────────────────────────────────
    // Template fields: action, server_url, timeout, target, url, additional_args,
    //                  command, scan_type, ports, mode, wordlist, data, module,
    //                  options, service, username, username_file, password,
    //                  password_file, hash_file, format
    } else if (lower === 'discoverer') {
        set('tool', pairs.tool);
        set('target', pairs.target);
        set('targets_file', pairs.targets_file);
        set('output_dir', pairs.output_dir);
        set('extra_args', pairs.extra_args);
        set('subfinder_sources', pairs.subfinder_sources);
        set('subfinder_provider_config', pairs.subfinder_provider_config);
        set('httpx_probes', pairs.httpx_probes);
        set('naabu_ports', pairs.naabu_ports);
        set('naabu_top_ports', pairs.naabu_top_ports);
        set('naabu_scan_type', pairs.naabu_scan_type);
        set('nuclei_templates', pairs.nuclei_templates);
        set('nuclei_severity', pairs.nuclei_severity);
        set('nuclei_tags', pairs.nuclei_tags);
        set('nuclei_template_ids', pairs.nuclei_template_ids);
        set('cvemap_id', pairs.cvemap_id);
        set('cvemap_product', pairs.cvemap_product);
        set('cvemap_severity', pairs.cvemap_severity);
        set('pdcp_api_key', pairs.pdcp_api_key);
        set('go_dir', pairs.go_dir);
        set('tools_bin', pairs.tools_bin);
        set('go_version', pairs.go_version);
        set('install_method', pairs.install_method);
        ['json_output', 'subfinder_all_sources', 'subfinder_include_ip', 'httpx_follow_redirects',
         'katana_js_crawl', 'katana_headless', 'nuclei_automatic_scan', 'cloud_upload',
         'go_bootstrap', 'preflight', 'auto_update'].forEach(function (k) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                config[k] = (String(pairs[k]).toLowerCase() === 'true');
            }
        });
        ['katana_depth', 'rate_limit', 'concurrency', 'command_timeout'].forEach(function (k) {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        });
    } else if (lower === 'kalier') {
        set('action', pairs.action);
        set('server_url', pairs.server_url);
        if (pairs.timeout !== undefined && pairs.timeout !== '') {
            const t = parseInt(pairs.timeout, 10);
            if (!Number.isNaN(t)) config.timeout = t;
        }
        set('target', pairs.target);
        set('url', pairs.url);
        set('additional_args', pairs.additional_args);
        set('command', pairs.command);
        set('scan_type', pairs.scan_type);
        set('ports', pairs.ports);
        set('mode', pairs.mode);
        set('wordlist', pairs.wordlist);
        set('data', pairs.data);
        set('module', pairs.module);
        // metasploit options may arrive as a JSON string in the flat request grammar.
        if (pairs.options !== undefined && pairs.options !== '') {
            config.options = pairs.options;
        }
        set('service', pairs.service);
        set('username', pairs.username);
        set('username_file', pairs.username_file);
        set('password', pairs.password);
        set('password_file', pairs.password_file);
        set('hash_file', pairs.hash_file);
        set('format', pairs.format);

    // ── STM32er ──────────────────────────────────────────────────────
    // Template fields: action, server_script, mcp_python, template_dir, ide_root,
    //   startup_timeout, call_timeout, project_dir, name, dest_parent, overwrite,
    //   rel_path, content, system, jobs, clean_first, binary, discover_ide_root,
    //   port, baud, data, read_response, read_timeout, line_ending, serial_timeout,
    //   max_bytes, address, symbol, elf, count, width, value, variables,
    //   interval_ms, output_path, session_id, last_n, monitor_seconds
    } else if (lower === 'stm32er') {
        set('action', pairs.action);
        set('server_script', pairs.server_script);
        set('mcp_python', pairs.mcp_python);
        set('template_dir', pairs.template_dir);
        set('ide_root', pairs.ide_root);
        set('project_dir', pairs.project_dir);
        set('name', pairs.name);
        set('dest_parent', pairs.dest_parent);
        set('rel_path', pairs.rel_path);
        set('content', pairs.content);
        set('system', pairs.system);
        set('binary', pairs.binary);
        set('discover_ide_root', pairs.discover_ide_root);
        set('port', pairs.port);
        set('data', pairs.data);
        set('line_ending', pairs.line_ending);
        set('address', pairs.address);
        set('symbol', pairs.symbol);
        set('elf', pairs.elf);
        set('value', pairs.value);
        set('variables', pairs.variables);
        set('output_path', pairs.output_path);
        set('session_id', pairs.session_id);
        // integer fields
        ['startup_timeout', 'call_timeout', 'jobs', 'baud', 'count', 'width',
         'max_bytes', 'interval_ms', 'last_n', 'monitor_seconds'].forEach((k) => {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        });
        // float fields
        ['read_timeout', 'serial_timeout'].forEach((k) => {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const f = parseFloat(pairs[k]);
                if (!Number.isNaN(f)) config[k] = f;
            }
        });
        // boolean fields
        ['overwrite', 'clean_first', 'read_response'].forEach((k) => {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                config[k] = String(pairs[k]) === 'true';
            }
        });

    // ── ESP32er ──────────────────────────────────────────────────────
    // Template fields: action, pio_executable, pio_install_method, pio_core_dir,
    //   project_dir, board, framework, environment, rel_path, content,
    //   command_timeout, port, baud, monitor_seconds, boards_query, pkg_spec
    } else if (lower === 'esp32er') {
        set('action', pairs.action);
        set('pio_executable', pairs.pio_executable);
        set('pio_install_method', pairs.pio_install_method);
        set('pio_core_dir', pairs.pio_core_dir);
        set('project_dir', pairs.project_dir);
        set('board', pairs.board);
        set('framework', pairs.framework);
        set('environment', pairs.environment);
        set('rel_path', pairs.rel_path);
        set('content', pairs.content);
        set('port', pairs.port);
        set('boards_query', pairs.boards_query);
        set('pkg_spec', pairs.pkg_spec);
        // integer fields
        ['command_timeout', 'baud', 'monitor_seconds'].forEach((k) => {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        });

    // ── ESPHomer ─────────────────────────────────────────────────────
    // Template fields: action, esphome_executable, config_path, content,
    //   name, platform, board, led_pin, wifi_ssid, wifi_password,
    //   command_timeout, port, monitor_seconds
    } else if (lower === 'esphomer') {
        set('action', pairs.action);
        set('esphome_executable', pairs.esphome_executable);
        set('config_path', pairs.config_path);
        set('content', pairs.content);
        set('name', pairs.name);
        set('platform', pairs.platform);
        set('board', pairs.board);
        set('led_pin', pairs.led_pin);
        set('wifi_ssid', pairs.wifi_ssid);
        set('wifi_password', pairs.wifi_password);
        set('port', pairs.port);
        // integer fields
        ['command_timeout', 'monitor_seconds'].forEach((k) => {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        });

    // ── Arduiner ─────────────────────────────────────────────────────
    // Template fields: action, arduino_cli_executable, arduino_cli_install_dir,
    //   fqbn, sketch_path, auto_core_install, additional_urls, rel_path, content,
    //   core_spec, lib_spec, boards_query, warnings, build_property,
    //   extra_compile_args, command_timeout, port, programmer, baud, monitor_seconds
    } else if (lower === 'arduiner') {
        set('action', pairs.action);
        set('arduino_cli_executable', pairs.arduino_cli_executable);
        set('arduino_cli_install_dir', pairs.arduino_cli_install_dir);
        set('fqbn', pairs.fqbn);
        set('sketch_path', pairs.sketch_path);
        set('auto_core_install', pairs.auto_core_install);
        set('additional_urls', pairs.additional_urls);
        set('rel_path', pairs.rel_path);
        set('content', pairs.content);
        set('core_spec', pairs.core_spec);
        set('lib_spec', pairs.lib_spec);
        set('boards_query', pairs.boards_query);
        set('warnings', pairs.warnings);
        set('build_property', pairs.build_property);
        set('extra_compile_args', pairs.extra_compile_args);
        set('port', pairs.port);
        set('programmer', pairs.programmer);
        // integer fields
        ['command_timeout', 'baud', 'monitor_seconds'].forEach((k) => {
            if (pairs[k] !== undefined && pairs[k] !== '') {
                const n = parseInt(pairs[k], 10);
                if (!Number.isNaN(n)) config[k] = n;
            }
        });

    // ── Telegrammer ──────────────────────────────────────────────────
    // Official Telegram BOT API (bot_token from @BotFather). Top-level:
    // message, contact_name, mode, rx_max_seconds. Nested: telegram
    // (bot_token, chat_id). Sends or receives, then starts target_agents.
    } else if (lower === 'telegrammer') {
        set('message', pairs.message);
        set('contact_name', pairs.contact_name);
        set('mode', pairs.mode);
        set('rx_max_seconds', pairs.rx_max_seconds);
        const telegram = collectDotted('telegram');
        // Top-level shortcuts the LLM commonly passes, mapped into the nested block.
        if (pairs.bot_token) telegram.bot_token = pairs.bot_token;
        if (pairs.chat_id) telegram.chat_id = pairs.chat_id;
        if (Object.keys(telegram).length > 0) config.telegram = telegram;

    // ── Whatsapper ───────────────────────────────────────────────────
    // Official Meta WhatsApp Cloud API ONLY. Top-level: message,
    // contact_name, to, provider, template(+lang/params), mode,
    // rx_max_seconds. Nested: whatsapp (phone_number_id, access_token,
    // graph_base, api_version, to, verify_token, webhook_*).
    } else if (lower === 'whatsapper') {
        set('message', pairs.message);
        set('contact_name', pairs.contact_name);
        set('to', pairs.to || pairs.phone_number);
        set('provider', pairs.provider);
        set('template', pairs.template);
        set('template_language', pairs.template_language);
        set('template_params', pairs.template_params);
        set('mode', pairs.mode);
        set('rx_max_seconds', pairs.rx_max_seconds);
        const whatsapp = collectDotted('whatsapp');
        if (Object.keys(whatsapp).length > 0) config.whatsapp = whatsapp;

    // ── Recmailer ────────────────────────────────────────────────────
    // Template field: imap (nested)
    } else if (lower === 'recmailer') {
        const imap = collectDotted('imap');
        if (pairs['mail.username']) imap.username = pairs['mail.username'];
        if (pairs['mail.password']) imap.password = pairs['mail.password'];
        if (Object.keys(imap).length > 0) config.imap = imap;

    // ── Monitor Log ──────────────────────────────────────────────────
    // Template field: target (nested: logfile_path, keywords, ...)
    } else if (lower === 'monitor log' || lower === 'monitor-log') {
        const target = collectDotted('target');
        if (Object.keys(target).length > 0) config.target = target;

    // ── Monitor Netstat ──────────────────────────────────────────────
    // Template field: target (nested: port, keywords, ...)
    } else if (lower === 'monitor netstat' || lower === 'monitor-netstat') {
        const target = collectDotted('target');
        if (Object.keys(target).length > 0) config.target = target;

    // ── Mover ────────────────────────────────────────────────────────
    // Template fields: source_files, destination_folder, operation
    } else if (lower === 'mover') {
        if (pairs.source_path || pairs.source_files) {
            config.source_files = [pairs.source_path || pairs.source_files];
        }
        if (pairs.destination_path || pairs.destination_folder) {
            config.destination_folder = pairs.destination_path || pairs.destination_folder;
        }
        if (pairs.operation) config.operation = pairs.operation;

    // ── Deleter ──────────────────────────────────────────────────────
    // Template field: files_to_delete (list)
    } else if (lower === 'deleter') {
        const delTarget = pairs.target_path || pairs.path || pairs.files_to_delete
            || pairs.file || pairs.file_path || pairs.target;
        if (delTarget) {
            config.files_to_delete = [delTarget];
        }

    // ── Kyber-KeyGen ─────────────────────────────────────────────────
    } else if (lower === 'kyber-keygen') {
        set('kyber_variant', pairs.kyber_variant);
        set('output_directory', pairs.output_directory);

    // ── Kyber-Cipher ─────────────────────────────────────────────────
    } else if (lower === 'kyber-cipher') {
        set('kyber_variant', pairs.kyber_variant);
        set('public_key', pairs.public_key || pairs.public_key_path);
        set('buffer', pairs.buffer || pairs.input_data);

    // ── Kyber-DeCipher ───────────────────────────────────────────────
    } else if (lower === 'kyber-decipher') {
        set('kyber_variant', pairs.kyber_variant);
        set('private_key', pairs.private_key || pairs.private_key_path);
        set('cipher_text', pairs.ciphertext_path || pairs.cipher_text);

    // ── J-Decompiler ─────────────────────────────────────────────────
    // Template field: directory
    } else if (lower === 'j-decompiler' || lower === 'j decompiler') {
        set('directory', pairs.path_filename || pairs.directory);

    // ── De-Compresser ────────────────────────────────────────────────
    // Template fields: input (file or directory), output (directory or
    // archive file), passwordless (bool). Password (when passwordless is
    // false) is read from the DE_COMPRESSER_PWD env var by the agent
    // itself — it is never persisted in the .flw.
    } else if (lower === 'de-compresser' || lower === 'de compresser' || lower === 'decompresser') {
        set('input', pairs.input || pairs.source || pairs.archive);
        set('output', pairs.output || pairs.destination || pairs.target);
        if (pairs.passwordless !== undefined) {
            config.passwordless = String(pairs.passwordless).toLowerCase() === 'true';
        }

    // ── Parametrizer ─────────────────────────────────────────────────
    // Only connection fields — no content params.  source_agent / target_agent
    // are set by _generateAndDownloadFlow.
    } else if (lower === 'parametrizer') {
        // intentionally empty — avoid fallback copying garbage fields

    // ── Fallback (unknown agents) ────────────────────────────────────
    } else {
        Object.assign(config, pairs);
    }

    return config;
}

/**
 * Parse key='value' and key="value" pairs from a request string.
 *
 * Handles single-quoted, double-quoted, and unquoted values, including
 * apostrophes embedded inside single-quoted values (e.g.
 * ``message='Hi I'm here!!'``). The LLM rarely escapes inner quotes, so
 * the parser uses a transport-aware lookahead: an unescaped quote inside
 * a value is treated as the terminator ONLY when what follows is the end
 * of the string OR a conjunction (``and``/``with``/``,``/``;``) followed by
 * another ``KEY=`` token. Otherwise the quote is treated as embedded.
 *
 * This mirrors the Python-side ``_split_assignment_segments`` /
 * ``_closes_outer_quote`` heuristic in ``agent/tools.py`` so the .flw
 * generator preserves the same values the Python wrapped-agent dispatcher
 * sees at runtime. Without this, multi-arg wrapped chat-agent calls whose
 * values contain apostrophes (very common in English text) end up
 * truncated when round-tripped through Create Flow.
 */
function _parseKeyValuePairs(str) {
    const result = {};
    if (!str || typeof str !== 'string') return result;

    const n = str.length;
    let i = 0;

    const isSpace = (c) => c === ' ' || c === '\t' || c === '\n' || c === '\r';
    const isKeyChar = (c) => /[\w.]/.test(c);
    const skipSpaces = () => { while (i < n && isSpace(str[i])) i++; };

    // Lookahead: at position ``pos`` (just past a candidate closing quote),
    // does the remaining string look like an end-of-arg boundary? That is:
    // optional whitespace, then EOF / ``,`` / ``;`` / ``and`` / ``with``,
    // followed (after more whitespace) by ``KEY=``.
    const looksLikeArgBoundary = (pos) => {
        let p = pos;
        while (p < n && isSpace(str[p])) p++;
        if (p >= n) return true; // EOF
        if (str[p] === ',' || str[p] === ';') {
            p++;
            while (p < n && isSpace(str[p])) p++;
            return p >= n || /^[\w.]+\s*=/.test(str.slice(p));
        }
        // ``and`` or ``with`` conjunction
        const tail = str.slice(p);
        const conj = tail.match(/^(?:and|with)\s+/i);
        if (conj) {
            const after = tail.slice(conj[0].length);
            return /^[\w.]+\s*=/.test(after);
        }
        return false;
    };

    while (i < n) {
        skipSpaces();
        // Skip stray separators / conjunctions between pairs
        if (i < n && (str[i] === ',' || str[i] === ';')) { i++; continue; }
        const conjMatch = str.slice(i).match(/^(?:and|with)\s+/i);
        if (conjMatch && i + conjMatch[0].length < n) {
            // Only treat as a conjunction if a KEY= follows, otherwise
            // ``and``/``with`` is part of the next bareword.
            const after = str.slice(i + conjMatch[0].length);
            if (/^[\w.]+\s*=/.test(after)) {
                i += conjMatch[0].length;
                continue;
            }
        }
        if (i >= n) break;

        // ── Read key ──
        const keyStart = i;
        while (i < n && isKeyChar(str[i])) i++;
        if (i === keyStart) { i++; continue; } // unparseable, advance to avoid infinite loop
        const key = str.slice(keyStart, i);

        skipSpaces();
        if (str[i] !== '=') continue; // not a KEY= assignment
        i++;
        skipSpaces();

        // ── Read value ──
        let value;
        if (i < n && (str[i] === "'" || str[i] === '"')) {
            const quote = str[i];
            i++;
            let buf = '';
            while (i < n) {
                const c = str[i];
                if (c === '\\' && i + 1 < n) {
                    const next = str[i + 1];
                    // Mirror the Python-side _unquote_preserving_backslashes
                    // (agent/tools.py): ONLY a doubled backslash and an escaped
                    // outer-quote are real escapes. EVERY other backslash is
                    // kept VERBATIM so Windows paths (C:\Tlamatini\Templates\..)
                    // regexes and other backslash-bearing values survive Create
                    // Flow intact. Do NOT expand \n / \t and NEVER drop the
                    // backslash on an unrecognized escape -- that silently
                    // corrupted every path-bearing config field in a .flw.
                    if (next === '\\')  { buf += '\\';  i += 2; continue; }
                    if (next === quote) { buf += quote; i += 2; continue; }
                    buf += c; i += 1; continue;
                }
                // SQL / YAML single-quoted convention: a doubled outer quote
                // decodes to one literal quote ('I''m' -> I'm), matching the
                // Python decoder so the value byte-equals what the runtime saw.
                if (c === quote && i + 1 < n && str[i + 1] === quote) {
                    buf += quote; i += 2; continue;
                }
                if (c === quote) {
                    // Decide: real terminator or embedded apostrophe?
                    if (looksLikeArgBoundary(i + 1)) {
                        i++;
                        break;
                    }
                    buf += c;
                    i++;
                    continue;
                }
                buf += c;
                i++;
            }
            value = buf;
        } else if (i < n && (str[i] === '[' || str[i] === '{')) {
            // Bracketed bareword (JSON array/object): read to the MATCHING
            // close bracket so embedded commas survive. Without this the
            // plain bareword reader below stopped at the first comma, so
            // ``params.location=[0,0,200]`` was captured as just ``[0`` and
            // the truncated remainder corrupted the next pairs (this is the
            // bug that produced ``"location": "[0"`` in a generated .flw).
            const valStart = i;
            let depth = 0;
            while (i < n) {
                const c = str[i];
                if (c === '[' || c === '{') depth++;
                else if (c === ']' || c === '}') { depth--; if (depth === 0) { i++; break; } }
                i++;
            }
            value = str.slice(valStart, i);
        } else {
            // Bareword: read until whitespace, comma, or semicolon
            const valStart = i;
            while (i < n && !isSpace(str[i]) && str[i] !== ',' && str[i] !== ';') i++;
            value = str.slice(valStart, i);
        }

        if (!(key in result)) {
            result[key] = value;
        }
    }

    return result;
}

/**
 * Convert an agent display name to its pool-folder base name (no cardinal).
 * e.g. "File Creator" → "file_creator", "Executer" → "executer",
 *      "Kyber-KeyGen" → "kyber_keygen"
 *
 * Pool folders on disk always carry a trailing ``_<N>`` cardinal assigned
 * by the .flw loader's counter, so callers that need an actual target
 * name must append their own cardinal. Use ``_poolBase`` when you're
 * the one generating cardinals (flow-generator path); kept as
 * ``_toPoolName`` only for any legacy callers that predated the fix.
 */
function _poolBase(displayName) {
    return displayName.toLowerCase().replace(/[\s-]+/g, '_');
}

function _toPoolName(displayName) {
    return _poolBase(displayName);
}

/**
 * Return a short purpose string for well-known agent types.
 * Keys are canonical DB agentDescription names.
 */
function _agentPurpose(canonicalName) {
    const purposes = {
        'Starter': 'Entry point, launches first agents',
        'Ender': 'Terminates all agents, launches Cleaners',
        'Executer': 'Shell commands',
        'Pythonxer': 'Inline Python execution',
        'Crawler': 'Web crawling with LLM analysis',
        'Googler': 'Google search and text extraction',
        'Apirer': 'HTTP REST API calls',
        'Gitter': 'Git operations',
        'Ssher': 'SSH remote commands',
        'Scper': 'SCP file transfer',
        'Dockerer': 'Docker commands',
        'Kuberneter': 'kubectl commands',
        'Pser': 'PowerShell commands',
        'Jenkinser': 'Jenkins job triggers',
        'Sqler': 'SQL queries',
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
        'Telegrammer': 'Telegram messages',
        'Whatsapper': 'WhatsApp messages',
        'Monitor Log': 'LLM-powered log file monitor',
        'Monitor Netstat': 'LLM-powered network port monitor',
        'Parametrizer': 'Maps structured output between agents',
        'J-Decompiler': 'JAR/WAR decompilation',
        'Kyber-KeyGen': 'Post-quantum key pair generation',
        'Kyber-Cipher': 'Post-quantum encryption',
        'Kyber-DeCipher': 'Post-quantum decryption',
        'Deleter': 'File deletion',
        'Mover': 'File move/copy',
        'Mouser': 'Mouse simulation',
        'Keyboarder': 'Keyboard automation',
        'Sleeper': 'Timed delay',
        'Raiser': 'Pattern-based trigger',
        'Forker': 'Conditional branching',
        'Cleaner': 'Log/PID cleanup',
        'Barrier': 'Synchronization barrier',
        'Flowbacker': 'Session backup',
    };
    return purposes[canonicalName] || canonicalName;
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
    // Ask-Execs: the backend is blocked waiting for the user to approve the
    // next Multi-Turn tool execution. Pop the modal Proceed/Deny dialog.
    if (data.type === 'exec-permission-request') {
        // Flash the Tlamatini.exe taskbar button + log an uppercase banner so
        // the user notices the pending approval even with the browser minimized.
        if (window.SharedRuntimeDialogs && typeof window.SharedRuntimeDialogs.flashTlamatiniWindow === 'function') {
            window.SharedRuntimeDialogs.flashTlamatiniWindow('execution-approval', 'agent_page.html');
        }
        if (typeof showExecPermissionDialog === 'function') {
            showExecPermissionDialog(data.detail || {});
        } else {
            // Hard fallback: never leave the backend blocked if the dialog
            // module is unavailable — deny so the chain halts cleanly.
            sendChatSocketMessage(JSON.stringify({
                message: 'exec-permission-response',
                type: 'exec-permission-response',
                request_id: (data.detail || {}).request_id,
                decision: 'deny'
            }));
        }
        return;
    }
    // Handle session-restored: Context was restored from saved session
    if (data.type === 'session-restored') {
        console.log('--- Session restored from server:', data);
        if (data.context_path) {
            applyContextUiState(data.context_path, data.context_type, data.context_filename);
            console.log('--- Context UI restored: ' + data.context_path);
        }
        // When the server still has to (re)build the contextual RAG chain, it
        // sets ``loading: true``. Disable the chat input + buttons immediately
        // so the user cannot send a request before MSG_AGENT_LOADING_CONTEXT
        // (and later MSG_AGENT_READY) finish the lifecycle. Without this, the
        // welcome-back message between session-restored and the eventual
        // loading-context broadcast would otherwise leave controls enabled.
        if (data.loading === true) {
            setTitleBusy(true);
            disableControlsDuringOperation();
            lapseLoadingContext = true;
            console.log('--- Session-restored: contextual RAG chain is still loading — input disabled until ready.');
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
    if (data.username === 'system' && data.type === 'skill') {
        // Mirror of the 'agent' branch above — `skills[]` powers the
        // ACPX-Skills > Configure dialog (checkbox grid) and is the cache
        // the Browse dialog merges with the HTTP /agent/skills/ payload.
        const values = data.message.split('|');
        const skillName = values[0];
        const skillDescription = values[1] || '';
        const skillContent = values[2] || 'true'; // 'true' | 'false'
        const existing = skills.findIndex(s => s.name === skillName);
        if (existing !== -1) {
            skills[existing].description = skillDescription;
            skills[existing].content = skillContent;
        } else {
            skills.push({
                name: skillName,
                description: skillDescription,
                content: skillContent
            });
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

// Drain any frames the temporary buffer in agent_page_state.js captured
// before this real handler was installed. Critical for the auto-load case:
// the server's `session-restored` frame arrives immediately on connect,
// well before chat.js finishes loading, and without this drain the
// loading=true flag never reaches disableControlsDuringOperation() and
// the spinner is silently skipped.
try {
    if (typeof _pendingChatSocketMessages !== 'undefined'
        && _pendingChatSocketMessages.length) {
        const queued = _pendingChatSocketMessages.splice(0);
        console.log(`--- Draining ${queued.length} buffered WebSocket frame(s) into real onmessage handler`);
        for (const queuedEvent of queued) {
            try {
                chatSocket.onmessage(queuedEvent);
            } catch (err) {
                console.error('Error replaying buffered chat-socket frame:', err);
            }
        }
    }
} catch (err) {
    console.error('Buffer-drain failed:', err);
}

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
