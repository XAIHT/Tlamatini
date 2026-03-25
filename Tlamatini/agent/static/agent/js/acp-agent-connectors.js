// Agentic Control Panel - Agent Connection Updaters
// LOAD ORDER: #4 - Depends on: acp-session.js (getHeaders), acp-globals.js (ACP.connections)
//
// Contains all update*Connection functions that call the backend API to update
// agent config.yaml files when connections are added/removed on the canvas.
// Also contains graph traversal helpers (getAllUpstreamAgents, findDownstreamEnders).

// ========================================
// GRAPH TRAVERSAL HELPERS
// ========================================

/**
 * Get all upstream agents connected to a node by traversing the connection graph backwards.
 * Performs a breadth-first search through all connections to find every agent
 * that is upstream (connected via source -> target chains).
 *
 * @param {HTMLElement} startNode - The starting node to traverse from
 * @returns {Array<HTMLElement>} Array of all upstream nodes (including startNode)
 */
function getAllUpstreamAgents(startNode) {
    const visited = new Set();
    const queue = [startNode];
    const result = [];

    while (queue.length > 0) {
        const currentNode = queue.shift();
        const nodeId = currentNode.id;

        if (visited.has(nodeId)) {
            continue;
        }
        visited.add(nodeId);
        result.push(currentNode);

        // Find all connections where currentNode is the TARGET (i.e., find sources)
        for (const conn of ACP.connections) {
            if (conn.target === currentNode && !visited.has(conn.source.id)) {
                queue.push(conn.source);
            }
        }
    }

    return result;
}

/**
 * Find all Ender agents that are downstream from a given node.
 * Traverses the connection graph forward (source -> target) to find
 * any Ender nodes that this node eventually connects to.
 *
 * @param {HTMLElement} startNode - The starting node to traverse from
 * @returns {Array<HTMLElement>} Array of Ender nodes found downstream
 */
function findDownstreamEnders(startNode) {
    const visited = new Set();
    const queue = [startNode];
    const enders = [];

    while (queue.length > 0) {
        const currentNode = queue.shift();
        const nodeId = currentNode.id;

        if (visited.has(nodeId)) {
            continue;
        }
        visited.add(nodeId);

        // Check if this is an Ender
        const agentName = currentNode.dataset.agentName || '';
        if (agentName.toLowerCase() === 'ender') {
            enders.push(currentNode);
            continue; // Don't traverse past Ender
        }

        // Find all connections where currentNode is the SOURCE (i.e., find targets)
        for (const conn of ACP.connections) {
            if (conn.source === currentNode && !visited.has(conn.target.id)) {
                queue.push(conn.target);
            }
        }
    }

    return enders;
}

// ========================================
// AGENT-SPECIFIC CONNECTION UPDATERS
// ========================================
// Each function calls the backend API to update a specific agent's config.yaml
// when connections are added or removed on the canvas.

async function updateRaiserConnection(raiserAgentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_raiser_connection/${raiserAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Raiser ${raiserAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update raiser ${raiserAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating raiser ${raiserAgentId}:`, error);
    }
}

async function updateEmailerConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_emailer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Emailer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Emailer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Emailer ${agentId}:`, error);
    }
}

async function updateMonitorLogConnection(monitorLogAgentId, sourceAgentId, action) {
    try {
        const response = await fetch(`/agent/update_monitor_log_connection/${monitorLogAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ source_agent: sourceAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Monitor Log ${monitorLogAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update monitor log ${monitorLogAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating monitor log ${monitorLogAgentId}:`, error);
    }
}

async function updateStarterConnection(starterAgentId, targetAgentId, action) {
    try {
        const response = await fetch(`/agent/update_starter_connection/${starterAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Starter ${starterAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update starter ${starterAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating starter ${starterAgentId}:`, error);
    }
}

/**
 * Update Ender agent's config.yaml when connections are made/removed.
 *
 * Ender has three connection lists:
 *   - source_agents:  graphical input connections only (never killed, never started)
 *   - target_agents:  ALL upstream agents to KILL (populated via BFS traversal)
 *   - output_agents:  agents to LAUNCH after killing (typically Cleaners)
 *
 * When connecting TO Ender (Input):
 *   1. Adds the directly connected agent to source_agents (graphical metadata)
 *   2. Traverses ALL upstream agents and adds each to target_agents (kill list)
 * When connecting FROM Ender (Output):
 *   Adds the target agent to output_agents
 *
 * @param {string} enderAgentId - The ender agent's ID (e.g., 'ender-1')
 * @param {HTMLElement} connectedNode - The node connected to Ender
 * @param {string} action - 'add' or 'remove'
 * @param {string} connectionType - 'input' or 'output' (default: 'input')
 */
async function updateEnderConnection(enderAgentId, connectedNode, action, connectionType = 'input') {
    if (connectionType === 'output') {
        // Output connection: add the cleaner to output_agents
        console.log(`--- Ender ${enderAgentId}: Updating output connection to ${connectedNode.id}`);
        await _sendEnderUpdate(enderAgentId, connectedNode.id, action, 'output');
    } else {
        // Input connection:
        // 1. Add the directly connected agent to source_agents (graphical only)
        console.log(`--- Ender ${enderAgentId}: Adding ${connectedNode.id} to source_agents (graphical)`);
        await _sendEnderUpdate(enderAgentId, connectedNode.id, action, 'input');

        // 2. Traverse ALL upstream agents and add each to target_agents (kill list)
        const upstreamAgents = getAllUpstreamAgents(connectedNode);
        console.log(`--- Ender ${enderAgentId}: Found ${upstreamAgents.length} upstream agent(s) for kill list:`, upstreamAgents.map(n => n.id));

        for (const agentNode of upstreamAgents) {
            const agentName = agentNode.dataset.agentName || '';
            if (agentName.toLowerCase() === 'cleaner') {
                console.warn(`--- Ender ${enderAgentId}: SKIPPING Cleaner ${agentNode.id} for kill list.`);
                continue;
            }
            await _sendEnderUpdate(enderAgentId, agentNode.id, action, 'target');
        }
    }
}

/**
 * Send a single ender connection update to the backend.
 * @param {string} enderAgentId - The ender agent's ID
 * @param {string} agentId - The connected agent's ID
 * @param {string} action - 'add' or 'remove'
 * @param {string} connectionType - 'input', 'target', or 'output'
 */
async function _sendEnderUpdate(enderAgentId, agentId, action, connectionType) {
    try {
        const response = await fetch(`/agent/update_ender_connection/${enderAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ source_agent: agentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Ender ${enderAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update ender ${enderAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating ender ${enderAgentId}:`, error);
    }
}

async function updateCleanerConnection(cleanerAgentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_cleaner_connection/${cleanerAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Cleaner ${cleanerAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Cleaner ${cleanerAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Cleaner ${cleanerAgentId}:`, error);
    }
}

async function updateOrAgentConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_or_agent_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- OR ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update OR ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating OR ${agentId}:`, error);
    }
}

async function updateAndAgentConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_and_agent_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- AND ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update AND ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating AND ${agentId}:`, error);
    }
}

async function updateCronerConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_croner_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Croner ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Croner ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Croner ${agentId}:`, error);
    }
}

async function updateMoverConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_mover_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Mover ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Mover ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Mover ${agentId}:`, error);
    }
}

async function updateSleeperConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_sleeper_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Sleeper ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Sleeper ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Sleeper ${agentId}:`, error);
    }
}

async function updateShoterConnection(agentId, targetAgentId, action) {
    try {
        const response = await fetch(`/agent/update_shoter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Shoter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Shoter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Shoter ${agentId}:`, error);
    }
}

async function updateDeleterConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_deleter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Deleter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Deleter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Deleter ${agentId}:`, error);
    }
}

async function updateExecuterConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_executer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Executer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Executer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Executer ${agentId}:`, error);
    }
}

async function updateScperConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_scper_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Scper ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Scper ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Scper ${agentId}:`, error);
    }
}

async function updateSsherConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_ssher_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Ssher ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Ssher ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Ssher ${agentId}:`, error);
    }
}

async function updateNotifierConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_notifier_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Notifier ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Notifier ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Notifier ${agentId}:`, error);
    }
}

async function updateStopperConnection(stopperAgentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_stopper_connection/${stopperAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Stopper ${stopperAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update stopper ${stopperAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating stopper ${stopperAgentId}:`, error);
    }
}

async function updateWhatsapperConnection(whatsapperAgentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_whatsapper_connection/${whatsapperAgentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Whatsapper ${whatsapperAgentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update whatsapper ${whatsapperAgentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating whatsapper ${whatsapperAgentId}:`, error);
    }
}

async function updatePythonxerConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_pythonxer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Pythonxer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Pythonxer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Pythonxer ${agentId}:`, error);
    }
}

async function updateAskerConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_asker_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Asker ${agentId} config updated (${connectionType}):`, result.message);
        } else {
            console.error(`--- Failed to update Asker ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Asker ${agentId}:`, error);
    }
}

async function updateForkerConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_forker_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Forker ${agentId} config updated (${connectionType}):`, result.message);
        } else {
            console.error(`--- Failed to update Forker ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Forker ${agentId}:`, error);
    }
}

async function updateCounterConnection(agentId, connectionType, connectedAgentId, action) {
    try {
        const response = await fetch(`/agent/update_counter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connection_type: connectionType, connected_agent: connectedAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Counter ${agentId} config updated (${connectionType}):`, result.message);
        } else {
            console.error(`--- Failed to update Counter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Counter ${agentId}:`, error);
    }
}

async function updateTelegramrxConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_telegramrx_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Telegramrx ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Telegramrx ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Telegramrx ${agentId}:`, error);
    }
}

async function updateTelegramerConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_telegramer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Telegramer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Telegramer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Telegramer ${agentId}:`, error);
    }
}

async function updateRecmailerConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_recmailer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Recmailer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Recmailer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Recmailer ${agentId}:`, error);
    }
}

async function updateSqlerConnection(agentId, connectedAgentId, action, connectionType = 'target') {
    try {
        const response = await fetch(`/agent/update_sqler_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Sqler ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Sqler ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Sqler ${agentId}:`, error);
    }
}

// FlowCreator has no inputs/outputs, so this is a no-op stub for completeness
async function updateFlowcreatorConnection() { // eslint-disable-line no-unused-vars
    // FlowCreator does not connect to or from other agents
}

async function updatePrompterConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_prompter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Prompter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Prompter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Prompter ${agentId}:`, error);
    }
}

async function updateGitterConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_gitter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Gitter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Gitter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Gitter ${agentId}:`, error);
    }
}

async function updateDockererConnection(agentId, connectedAgentId, action, connectionType = 'source') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_dockerer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Dockerer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Dockerer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Dockerer ${agentId}:`, error);
    }
}

async function updatePserConnection(agentId, connectedAgentId, action, connectionType = 'source') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_pser_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Pser ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Pser ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Pser ${agentId}:`, error);
    }
}

async function updateKuberneterConnection(agentId, connectedAgentId, action, connectionType = 'target') {
    try {
        const response = await fetch(`/agent/update_kuberneter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Kuberneter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Kuberneter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Kuberneter ${agentId}:`, error);
    }
}

async function updateApirerConnection(agentId, connectedAgentId, action, connectionType = 'target') {
    try {
        const response = await fetch(`/agent/update_apirer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Apirer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Apirer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Apirer ${agentId}:`, error);
    }
}

async function updateJenkinserConnection(agentId, connectedAgentId, action, connectionType = 'target') {
    try {
        const response = await fetch(`/agent/update_jenkinser_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Jenkinser ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Jenkinser ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Jenkinser ${agentId}:`, error);
    }
}

async function updateCrawlerConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_crawler_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Crawler ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Crawler ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Crawler ${agentId}:`, error);
    }
}

async function updateSummarizerConnection(agentId, connectedAgentId, action, connectionType = 'source') {
    try {
        const response = await fetch(`/agent/update_summarizer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ connected_agent: connectedAgentId, action: action, connection_type: connectionType })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Summarizer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Summarizer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Summarizer ${agentId}:`, error);
    }
}

async function updateMouserConnection(agentId, targetAgentId, action) {
    try {
        const response = await fetch(`/agent/update_mouser_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Mouser ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Mouser ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Mouser ${agentId}:`, error);
    }
}

async function updateFileInterpreterConnection(agentId, targetAgentId, action, type = 'target') {
    try {
        const response = await fetch(`/agent/update_file_interpreter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- FileInterpreter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update FileInterpreter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating FileInterpreter ${agentId}:`, error);
    }
}

async function updateImageInterpreterConnection(agentId, targetAgentId, action, type = 'target') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_image_interpreter_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- ImageInterpreter ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update ImageInterpreter ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating ImageInterpreter ${agentId}:`, error);
    }
}

async function updateGatewayerConnection(agentId, targetAgentId, action, type = 'target') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_gatewayer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- Gatewayer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update Gatewayer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating Gatewayer ${agentId}:`, error);
    }
}

async function updateGatewayRelayerConnection(agentId, targetAgentId, action, type = 'target') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_gateway_relayer_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- GatewayRelayer ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update GatewayRelayer ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating GatewayRelayer ${agentId}:`, error);
    }
}

async function updateFileCreatorConnection(agentId, targetAgentId, action, type = 'target') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_file_creator_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- File-Creator ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update File-Creator ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating File-Creator ${agentId}:`, error);
    }
}

async function updateFileExtractorConnection(agentId, targetAgentId, action, type = 'target') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_file_extractor_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- File-Extractor ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update File-Extractor ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating File-Extractor ${agentId}:`, error);
    }
}

async function updateNodeManagerConnection(agentId, targetAgentId, action, type = 'target') { // eslint-disable-line no-unused-vars
    try {
        const response = await fetch(`/agent/update_node_manager_connection/${agentId}/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...getHeaders() },
            credentials: 'same-origin',
            body: JSON.stringify({ target_agent: targetAgentId, action: action, type: type })
        });
        if (response.ok) {
            const result = await response.json();
            console.log(`--- NodeManager ${agentId} config updated:`, result.message);
        } else {
            console.error(`--- Failed to update NodeManager ${agentId}:`, response.statusText);
        }
    } catch (error) {
        console.error(`--- Error updating NodeManager ${agentId}:`, error);
    }
}
