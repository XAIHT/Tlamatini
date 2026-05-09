// Agentic Control Panel - Flow Snapshot / Contract Compiler bridge
// LOAD ORDER: after acp-canvas-core.js; runtime dependency on getHeaders().

function buildACPFlowSnapshot() {
    const nodes = Array.from(document.querySelectorAll('#submonitor-container .canvas-item'));
    const nodeMap = new Map();
    const nodesData = [];
    const parametrizerMappings = {};

    nodes.forEach((node, index) => {
        nodeMap.set(node, index);
        const agentName = node.dataset.agentName || node.firstChild.textContent;
        const rawConfig = (typeof ACP !== 'undefined' && ACP.nodeConfigs)
            ? (ACP.nodeConfigs.get(node.id) || null)
            : null;
        const configData = rawConfig ? JSON.parse(JSON.stringify(rawConfig)) : null;

        if (configData && Array.isArray(configData._parametrizer_mappings)) {
            parametrizerMappings[node.id] = configData._parametrizer_mappings;
        }

        nodesData.push({
            id: node.id,
            text: agentName,
            left: node.style.left,
            top: node.style.top,
            agentPurpose: node.dataset.agentPurpose || (
                typeof window.getAgentPurposeForName === 'function'
                    ? window.getAgentPurposeForName(agentName)
                    : ''
            ),
            configData
        });
    });

    const connectionsData = (ACP.connections || [])
        .filter(conn => nodeMap.has(conn.source) && nodeMap.has(conn.target))
        .map(conn => ({
            sourceIndex: nodeMap.get(conn.source),
            targetIndex: nodeMap.get(conn.target),
            sourceId: conn.source.id,
            targetId: conn.target.id,
            inputSlot: conn.inputSlot || 0,
            outputSlot: conn.outputSlot || 0
        }));

    return {
        schemaVersion: 2,
        nodes: nodesData,
        connections: connectionsData,
        artifacts: {
            parametrizerMappings
        }
    };
}

async function compileCurrentACPFlow(options = {}) {
    const mode = options.mode || (options.write ? 'write' : 'dry_run');
    const snapshot = buildACPFlowSnapshot();
    const response = await fetch('/agent/compile_flow/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getHeaders() },
        credentials: 'same-origin',
        body: JSON.stringify({ mode, flow: snapshot })
    });

    let result;
    try {
        result = await response.json();
    } catch (_err) {
        result = {};
    }

    if (!response.ok || result.success === false) {
        throw new Error(result.error || result.message || `Flow compile failed with HTTP ${response.status}`);
    }

    return result;
}

window.buildACPFlowSnapshot = buildACPFlowSnapshot;
window.compileCurrentACPFlow = compileCurrentACPFlow;
