/*
 * ═══════════════════════════════════════════════════════════════════
 *   ✦  T L A M A T I N I  ✦   —   "one who knows"
 *
 *   Created by  Angela López Mendoza   ·   @angelahack1
 *   Developer · Architect · Creator of Tlamatini
 * ═══════════════════════════════════════════════════════════════════
 *   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
 *
 * compact_costs.js — what each Configure row COSTS (Angela, 2026-10-02).
 *
 * "when the user may activate for example PDFer (a big one) but the gauge is
 * very red then she/he must be REALLY EXPECTING NOT EVERYTHING MAY WORK
 * CORRECTLY".  So the user sees the price BEFORE she clicks Continue:
 *
 *   1. every row in Config ▸ Configure MCPs and Configure Agents carries a
 *      small "≈1.2K" label - the tokens that row adds to EVERY request,
 *      measured by the server on the real tool schemas
 *      (GET /agent/compact_mode/costs/);
 *   2. a budget line above each list projects the whole selection AS TICKED
 *      RIGHT NOW against the model's usable window, and updates on every
 *      tick: green fits, amber is tight, red does not fit.
 *
 * The projection is exact about WHICH tools are bound (a tool is bound when
 * its Tool row is on AND, if it has one, its Agent row is on - the same gate
 * table the server binds from) and an estimate about tokens, and says
 * "est.": the CONTEXT-WINDOW gauge measures the real request after Continue.
 *
 * Contracts: self-contained IIFE, NO globals; it only DECORATES the dialogs
 * agent_page_dialogs.js builds (it never changes what they save); fail-open
 * everywhere - a missing price must never cost the user a dialog.
 */
(function () {
    'use strict';

    const COSTS_URL = '/agent/compact_mode/costs/';
    const LISTS = [
        { listId: 'tool-mcps-list', budgetId: 'tlm-budget-tools', kind: 'tool' },
        { listId: 'agents-list', budgetId: 'tlm-budget-agents', kind: 'agent' }
    ];
    const MCP_LABELS = { 'system-metrics': 'live metrics', 'files-search': 'file results' };
    const CACHE_MS = 15000;
    // Ticked along with any agent while Compact mode is ON (compact_mode.COMPANION_TOOLS).
    const COMPANIONS = ['chat-agent-run-wait', 'chat-agent-run-status'];

    let costs = null;
    let fetchedAt = 0;
    let inflight = null;

    function shortTokens(n) {
        const v = Number(n) || 0;
        if (v >= 1000) { return (Math.round(v / 100) / 10) + 'K'; }
        return String(v);
    }

    function fmt(n) {
        try { return (Number(n) || 0).toLocaleString('en-US'); } catch (err) { return String(n); }
    }

    function load(force) {
        if (!force && costs && Date.now() - fetchedAt < CACHE_MS) { return Promise.resolve(costs); }
        if (inflight) { return inflight; }
        inflight = fetch(COSTS_URL, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (data) {
                inflight = null;
                if (data && data.ok) {
                    costs = data;
                    fetchedAt = Date.now();
                }
                return costs;
            })
            .catch(function () { inflight = null; return costs; });
        return inflight;
    }

    function rowsOf(list) {
        const out = [];
        list.querySelectorAll('input[type="checkbox"]').forEach(function (box) {
            const label = list.querySelector('label[for="' + CSS.escape(box.id) + '"]');
            if (!label) { return; }
            const text = (label.getAttribute('data-tlm-name') || label.textContent || '').trim();
            if (!label.getAttribute('data-tlm-name')) { label.setAttribute('data-tlm-name', text); }
            out.push({ box: box, label: label, key: text.toLowerCase() });
        });
        return out;
    }

    function selection() {
        // What is ticked RIGHT NOW: the open dialog's checkboxes win over the
        // rows the server last reported.
        const serverTools = new Set((costs && costs.enabled_tools) || []);
        const serverAgents = new Set((costs && costs.enabled_agents) || []);
        const tools = new Set(serverTools);
        const agents = new Set(serverAgents);
        LISTS.forEach(function (spec) {
            const list = document.getElementById(spec.listId);
            if (!list || !list.offsetParent) { return; }
            rowsOf(list).forEach(function (row) {
                const set = spec.kind === 'tool' ? tools : agents;
                if (row.box.checked) { set.add(row.key); } else { set.delete(row.key); }
            });
        });
        // Saving CHAINS the rows (compact_mode._link_rows): an agent ticked or
        // unticked here takes its tool rows with it, and a tool ticked here
        // switches its agent on - so the projection must do the same, or a
        // freshly ticked agent would cost nothing until after Continue.
        let agentTurnedOn = false;
        ((costs && costs.entries) || []).forEach(function (entry) {
            if (!entry.agent) { return; }
            const agentMoved = agents.has(entry.agent) !== serverAgents.has(entry.agent);
            const toolMoved = tools.has(entry.key) !== serverTools.has(entry.key);
            if (agentMoved && !toolMoved) {
                if (agents.has(entry.agent)) { tools.add(entry.key); } else { tools.delete(entry.key); }
            } else if (toolMoved && !agentMoved && tools.has(entry.key)) {
                agents.add(entry.agent);
            }
            if (agentMoved && agents.has(entry.agent)) { agentTurnedOn = true; }
        });
        if (agentTurnedOn && costs.state && costs.state.active) {
            COMPANIONS.forEach(function (key) { tools.add(key); });
        }
        return { tools: tools, agents: agents };
    }

    function projectedTokens() {
        const sel = selection();
        let sum = 0;
        ((costs && costs.entries) || []).forEach(function (entry) {
            if (!sel.tools.has(entry.key)) { return; }
            if (entry.agent && !sel.agents.has(entry.agent)) { return; }
            sum += Number(entry.tokens) || 0;
        });
        return sum;
    }

    function paintBudget(spec, list) {
        let line = document.getElementById(spec.budgetId);
        if (!line) {
            line = document.createElement('div');
            line.id = spec.budgetId;
            line.className = 'tlm-budget';
            line.setAttribute('role', 'status');
            line.setAttribute('aria-live', 'polite');
            list.parentNode.insertBefore(line, list);
        }
        const st = (costs && costs.state) || {};
        const tools = projectedTokens();
        const base = Number(st.base_tokens) || 0;
        const usable = Number(st.usable_tokens) || 0;
        const total = tools + base;
        let zone = 'unknown';
        let text;
        if (usable > 0) {
            const pct = Math.round(total * 100 / usable);
            zone = pct > 100 ? 'red' : (pct > 85 ? 'amber' : 'green');
            text = 'Your selection: ≈' + fmt(total) + ' of ' + fmt(usable) + ' usable tokens (' + pct +
                '%) · prompt ≈' + fmt(base) + ' + tools ≈' + fmt(tools) + ' · est.' +
                (zone === 'red' ? ' - does NOT fit ' + (st.model || 'this model') + ': not everything will work.' : '');
        } else {
            text = 'Tools you have ticked: ≈' + fmt(tools) + ' tokens est. - send a message to measure this model\'s window.';
        }
        line.textContent = text;
        line.setAttribute('data-zone', zone);
        line.title = 'Projected from what is ticked right now. The CONTEXT-WINDOW gauge measures the real '
            + 'request after you click Continue.' + (st.active ? ' Compact mode is ON.' : '');
    }

    function paintLabels(spec, list) {
        const table = spec.kind === 'tool' ? (costs && costs.tools) : (costs && costs.agents);
        rowsOf(list).forEach(function (row) {
            let tag = row.label.querySelector('.tlm-cost');
            const tokens = table ? table[row.key] : undefined;
            const live = MCP_LABELS[row.key];
            if (tokens === undefined && !live) {
                if (tag) { tag.remove(); }
                return;
            }
            if (!tag) {
                tag = document.createElement('span');
                tag.className = 'tlm-cost';
                row.label.appendChild(tag);
            }
            tag.textContent = tokens !== undefined ? ('≈' + shortTokens(tokens)) : live;
            tag.title = tokens !== undefined
                ? ('≈' + fmt(tokens) + ' tokens added to every request (est.)')
                : 'Adds live context to the questions that need it - its size varies.';
            if (!row.box.dataset.tlmCostWired) {
                row.box.dataset.tlmCostWired = '1';
                row.box.addEventListener('change', function () { repaint(); });
            }
        });
    }

    function repaint() {
        try {
            LISTS.forEach(function (spec) {
                const list = document.getElementById(spec.listId);
                if (!list || !costs) { return; }
                paintLabels(spec, list);
                paintBudget(spec, list);
            });
        } catch (err) {
            try { window.console.warn('[compact-costs] repaint skipped:', err); } catch (e) { /* noop */ }
        }
    }

    function markMeasuring() {
        LISTS.forEach(function (spec) {
            const line = document.getElementById(spec.budgetId);
            if (line) {
                line.textContent = 'Measuring what your selection costs...';
                line.setAttribute('data-zone', 'unknown');
            }
        });
    }

    let timer = null;
    function schedule(force) {
        if (timer) { window.clearTimeout(timer); }
        timer = window.setTimeout(function () {
            timer = null;
            // The prices never change: paint them AT ONCE from the last answer
            // (the server can be busy finishing a reply), then refresh which
            // rows it has on.  A budget line left over from the previous
            // opening must never stand in for the selection shown now.
            if (costs) { repaint(); } else { markMeasuring(); }
            load(force).then(repaint);
        }, 120);
    }

    function watch() {
        LISTS.forEach(function (spec) {
            const list = document.getElementById(spec.listId);
            if (!list || list.dataset.tlmCostWatched) { return; }
            list.dataset.tlmCostWatched = '1';
            try {
                new MutationObserver(function (records) {
                    // Our own label tags also mutate the list; only a rebuild
                    // (a dialog opening) needs a fresh price list.
                    const rebuilt = records.some(function (r) {
                        return r.target === list && r.addedNodes && r.addedNodes.length;
                    });
                    if (rebuilt) { schedule(true); }
                }).observe(list, { childList: true });
            } catch (err) { /* no observer: no prices, the dialog still works */ }
        });
    }

    // A switch or a saved dialog changes what is on: forget the cached prices.
    document.addEventListener('tlm:compact-mode-state', function () { fetchedAt = 0; });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', watch);
    } else {
        watch();
    }
}());
