/* Tlamatini Author Banner — Angela López Mendoza */
(function () {
    'use strict';
    const overlay = document.getElementById('usage-overlay');
    const opener = document.getElementById('usage-button');
    if (!overlay || !opener) return;
    const dialog = document.getElementById('usage-dialog');
    const $ = id => document.getElementById('usage-' + id);
    const palette = ['#70c5ed', '#c0a0f3', '#75d8ba', '#f3b96e', '#ea9bbc', '#90aafa'];
    const integer = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
    const compact = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });
    const n = value => typeof value === 'number' && Number.isFinite(value);
    const count = value => n(value) ? integer.format(value) : '—';
    const money = value => n(value) ? '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—';
    const date = value => value ? String(value).slice(0, 10) : '—';
    const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
    let range = '7d', data = null, controller = null, interval = null, scheduled = null;
    let again = false, generation = 0, lastFocus = null, oldOverflow = '', inertSiblings = [];
    let sessionInvalid = false;

    function html(id, content) {
        const element = $(id);
        if (element.innerHTML === content) return;
        const focusedIndex = element.contains(document.activeElement) ? [...element.querySelectorAll('[data-tip]')].indexOf(document.activeElement) : -1;
        element.innerHTML = content;
        if (focusedIndex >= 0) element.querySelectorAll('[data-tip]')[focusedIndex]?.focus({ preventScroll: true });
    }
    function metrics(id, rows) {
        html(id, rows.map(([label, value, note]) => `<div class="usage-metric"><span class="usage-metric-label">${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></div>`).join(''));
    }
    function table(id, headings, rows) {
        html(id, rows.length ? `<table><thead><tr>${headings.map(h => `<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>` : '<p class="usage-empty">No data is available for this period.</p>');
    }
    function chart(id, rows, keys, currency = false) {
        if (!rows.length || !rows.some(r => keys.some(k => n(r[k])))) {
            html(id, '<p class="usage-empty">No usage data is available for this period.</p>'); return;
        }
        const width = 600, height = 166, left = 48, top = 12, bottom = 144;
        const maximum = Math.max(0, ...rows.map(r => keys.reduce((sum, k) => sum + (r[k] || 0), 0)));
        const scale = maximum || 1, slot = (width - left - 8) / rows.length;
        let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${esc(currency ? 'Daily credit usage in USD' : 'Daily input and output tokens')}. Exact values are in the table below.">`;
        for (let i = 0; i <= 3; i++) {
            const y = bottom - (bottom - top) * i / 3, value = maximum * i / 3;
            svg += `<line class="usage-gridline" x1="${left}" x2="592" y1="${y}" y2="${y}"/><text x="40" y="${y + 3}" text-anchor="end">${esc(currency ? '$' + compact.format(value) : compact.format(value))}</text>`;
        }
        rows.forEach((row, index) => {
            let y = bottom;
            const detail = `${row.date}${row.partial ? ' · partial day' : ''}\n` + keys.map(k => `${k.replaceAll('_', ' ')}: ${currency ? money(row[k]) : count(row[k])}`).join('\n');
            svg += `<g tabindex="0" data-tip="${esc(detail)}" aria-label="${esc(detail)}"><title>${esc(detail)}</title>`;
            keys.forEach((key, i) => {
                const h = (row[key] || 0) / scale * (bottom - top); y -= h;
                const color = row.partial && currency ? '#f3b96e' : currency ? palette[index % palette.length] : palette[i];
                svg += `<rect x="${left + index * slot + slot * .16}" y="${y}" width="${slot * .68}" height="${h}" rx="2" fill="${color}"/>`;
            });
            // A transparent full-height hit target keeps zero days inspectable without inventing a bar.
            svg += `<rect x="${left + index * slot}" y="${top}" width="${slot}" height="${bottom - top}" fill="transparent"/></g>`;
            if (index === 0 || index === rows.length - 1 || index % Math.ceil(rows.length / 7) === 0) svg += `<text x="${left + (index + .5) * slot}" y="162" text-anchor="middle">${esc(row.date.slice(5))}</text>`;
        });
        html(id, svg + '</svg>');
    }
    function peak(rows, key, formatter) {
        const valid = rows.filter(r => n(r[key]));
        const best = valid.reduce((a, b) => !a || b[key] > a[key] ? b : a, null);
        return best && best[key] > 0 ? `Peak: ${date(best.date)} · ${formatter(best[key])}${best.partial ? ' (partial day)' : ''}` : 'No measured usage in this period.';
    }
    function modelBars(id, rows, calls) {
        const value = r => calls ? r.calls : r.input_tokens + r.output_tokens;
        const ordered = [...rows].sort((a, b) => value(b) - value(a));
        const maximum = Math.max(1, ...ordered.map(value));
        html(id, ordered.length ? ordered.map((row, i) => `<div class="usage-model-row" tabindex="0" data-tip="${esc(row.model + '\n' + count(row.calls) + ' calls · ' + count(row.input_tokens) + ' input · ' + count(row.output_tokens) + ' output')}"><div><span>${esc(row.model)}</span><strong>${count(value(row))}</strong></div><div class="usage-stack">${calls ? `<span style="width:${100 * row.calls / maximum}%;background:${palette[i % palette.length]}"></span>` : `<span style="width:${100 * row.input_tokens / maximum}%;background:${palette[0]}"></span><span style="width:${100 * row.output_tokens / maximum}%;background:${palette[1]}"></span>`}</div></div>`).join('') : '<p class="usage-empty">Model statistics appear after your first measured chat call.</p>');
    }
    function refillCaption(end, now = Date.now()) {
        const remaining = Date.parse(end) - now;
        if (!Number.isFinite(remaining)) return '';
        if (remaining <= 0) return 'Monthly credits are due to refill; refreshing the account will confirm the new period.';
        const days = Math.max(1, Math.ceil(remaining / 86400000));
        const weeks = Math.floor(days / 7);
        return 'Monthly credits refill in ' + (weeks ? weeks + (weeks === 1 ? ' week' : ' weeks') : days + (days === 1 ? ' day' : ' days')) + '.';
    }
    function creditCards(balance, pending) {
        const cards = [];
        const card = (label, value, lines, color = palette[0], percent = null) => {
            cards.push(`<article class="usage-panel usage-credit-card" style="--usage-card-color:${color}"><span class="usage-credit-label">${esc(label)}</span><strong class="usage-credit-value">${esc(value)}</strong>${lines.filter(Boolean).map(line => `<p>${esc(line)}</p>`).join('')}${n(percent) ? `<div class="usage-credit-progress"><span style="width:${Math.min(100, Math.max(0, percent))}%"></span></div>` : ''}</article>`);
        };
        if (balance?.kind === 'credits') {
            if (n(balance.remaining)) card('Usage credits · available', money(balance.remaining), ['Monthly credits left: ' + money(balance.monthly_remaining), 'Added credits: ' + money(balance.purchased)], palette[2]);
            else card('Monthly credits · available', money(balance.monthly_remaining), ['Added-credit balance was not returned by Ollama.'], palette[2]);
            card('Monthly credits used', money(balance.used), [n(balance.percent) ? balance.percent.toFixed(2) + '% of the monthly allowance' : 'No monthly credit allowance'], palette[1], balance.percent);
            card('Monthly allowance', money(balance.allowance), [refillCaption(balance.end), balance.end ? 'Refills on ' + date(balance.end) + ' (UTC)' : 'Refill date was not returned by Ollama.'], palette[3]);
            $('plan-note').textContent = 'Included credits are used first, then added credits. Unused monthly credits do not carry over.';
        } else if (balance?.kind === 'legacy') {
            balance.limits.forEach(limit => card(limit.name === 'session' ? 'Session allowance remaining' : 'Weekly allowance remaining', limit.remaining_percent.toFixed(2) + '%', [limit.resets_at ? 'Resets ' + new Date(limit.resets_at).toLocaleString() : 'Reset date was not returned by Ollama.'], palette[cards.length], limit.remaining_percent));
            if (n(balance.purchased)) card('Added credits', money(balance.purchased), ['Unexpired purchased credits'], palette[3]);
            $('plan-note').textContent = 'This account uses legacy session and weekly limits. Ollama supplies request counts; dollar costs and token totals may be omitted for legacy requests.';
        } else if (balance?.kind === 'purchased') {
            card('Added credits', money(balance.purchased), ['Unexpired purchased credits'], palette[2]);
            $('plan-note').textContent = 'Ollama returned purchased credits without a monthly allowance or reset schedule.';
        } else {
            cards.push('<div class="usage-panel usage-credit-message"><p>' + (pending ? 'Refreshing your account credits…' : 'Account credits could not load. Check the Ollama connection, then choose Refresh or open Ollama Usage.') + '</p></div>');
            $('plan-note').textContent = '';
        }
        html('credit-cards', cards.join(''));
    }
    function render() {
        const provider = data.provider || {}, cloud = provider.ranges?.[range] || {};
        const totals = cloud.data?.totals || {}, daily = cloud.data?.daily || [];
        const balance = provider.balance || {}, activity = data.activity || {}, chatTotals = activity.totals || {};
        const notes = [data.provider_error, balance.error, cloud.error, data.activity_error];
        if (provider.account_error) notes.push('Account identity could not refresh. ' + provider.account_error);
        if (activity.recording_failures) notes.push('Some chat calls could not be saved during this app session; totals are incomplete.');
        if (activity.pending) { notes.push('New chat usage is being saved…'); schedule(); }
        if (provider.pending) notes.push('Ollama is refreshing. Your chat ledger is current.');
        if (cloud.stale && cloud.data) notes.push('Showing the last available account snapshot; figures may have changed.');
        if (balance.stale && balance.data) notes.push('Credits show the last verified balance; use Refresh to check again.');
        if (chatTotals.missing_output_calls) notes.push(`${count(chatTotals.missing_output_calls)} measured calls did not report output tokens. Output totals are partial.`);
        $('status').textContent = notes.filter(Boolean).join(' ') || 'Live account statistics and measured chat activity. Hover or focus a graph to inspect exact values.';
        $('status').classList.toggle('usage-warning', notes.some(Boolean));
        $('account-note').textContent = `${provider.account || 'Ollama account'}${provider.plan ? ' · ' + provider.plan.toUpperCase() : ''} · Account activity includes usage outside Tlamatini. Dates are UTC.`;
        creditCards(balance.data, provider.pending);
        const accountMetrics = [
            ['Period spend', totals.usage_usd, 'Rolling ' + range + ' · separate from monthly credits', money],
            ['Requests', totals.request_count, 'Your account · rolling ' + range, count],
            ['Input tokens', totals.input_tokens, 'Includes cached input · rolling ' + range, count],
            ['Output tokens', totals.output_tokens, 'Received · rolling ' + range, count]
        ];
        metrics('cloud-totals', accountMetrics.filter(row => n(row[1])).map(([label, value, note, format]) => [label, format(value), note]));
        $('spend-panel').hidden = !daily.some(row => n(row.usage_usd));
        $('token-panel').hidden = !daily.some(row => n(row.input_tokens) || n(row.output_tokens));
        $('composition-panel').hidden = ![totals.input_tokens, totals.cached_input_tokens, totals.output_tokens].every(n);
        chart('spend-chart', daily, ['usage_usd'], true);
        chart('token-chart', daily, ['input_tokens', 'output_tokens']);
        $('spend-peak').textContent = peak(daily, 'usage_usd', money) + ' Amber marks partial days.';
        const input = totals.input_tokens, cached = totals.cached_input_tokens, output = totals.output_tokens;
        if ([input, cached, output].every(n) && cached <= input) {
            const grand = input + output, fresh = input - cached, denom = grand || 1;
            html('composition', `<div class="usage-stack" aria-label="Token composition"><span style="width:${100 * fresh / denom}%;background:#70c5ed"></span><span style="width:${100 * cached / denom}%;background:#75d8ba"></span><span style="width:${100 * output / denom}%;background:#c0a0f3"></span></div><div class="usage-legend"><span class="usage-dot" style="--dot:#70c5ed">Fresh input: ${count(fresh)}</span><span class="usage-dot" style="--dot:#75d8ba">Cached input: ${count(cached)}</span><span class="usage-dot usage-output">Output: ${count(output)}</span></div><p>Total: ${count(grand)} tokens · Cache hit rate: ${input ? (cached / input * 100).toFixed(1) + '%' : 'No input tokens'}</p>`);
        } else html('composition', '<p>Complete token composition is unavailable from this response.</p>');
        const fields = [['usage_usd', 'Credits (USD)', money], ['request_count', 'Requests', count], ['input_tokens', 'Input', count], ['cached_input_tokens', 'Cached input', count], ['output_tokens', 'Output', count]].filter(([key]) => daily.some(row => n(row[key])));
        table('cloud-table', ['Date (UTC)', ...fields.map(row => row[1])], daily.map(r => [r.date + (r.partial ? ' · partial' : ''), ...fields.map(([key, , format]) => format(r[key]))]));
        $('activity-note').textContent = (activity.scope || data.activity_error || 'Waiting for recorded usage.') + (activity.since ? ` Tracking since ${date(activity.since)}.` : ' Tracking begins with your next measured chat call.');
        metrics('chat-totals', [['Model calls', count(chatTotals.calls), 'Completed, measured calls'], ['Input tokens', count(chatTotals.input_tokens), 'Processed by your chat models'], ['Output tokens', count(chatTotals.output_tokens), chatTotals.missing_output_calls ? 'Partial · some calls omitted counts' : 'Reported by your chat models'], ['Models used', activity.models ? count(activity.models.length) : '—', 'Unique model names in this period']]);
        chart('chat-chart', activity.daily || [], ['input_tokens', 'output_tokens']);
        const maxCalls = Math.max(1, ...(activity.daily || []).map(r => r.calls));
        html('calendar', (activity.daily || []).map(r => `<div tabindex="0" class="usage-calendar-cell" style="--cell-bg:rgba(85,187,170,${.08 + r.calls / maxCalls * .6})" data-tip="${esc(r.date + ' UTC\n' + count(r.calls) + ' calls\n' + count(r.input_tokens + r.output_tokens) + ' tokens')}">${esc(r.date.slice(8))}<small>${count(r.calls)} calls</small></div>`).join(''));
        $('chat-peak').textContent = peak(activity.daily || [], 'calls', v => count(v) + ' calls');
        table('chat-table', ['Date (UTC)', 'Calls', 'Input', 'Output', 'Missing output counts'], (activity.daily || []).map(r => [r.date, count(r.calls), count(r.input_tokens), count(r.output_tokens), count(r.missing_output_calls)]));
        modelBars('model-chart', activity.models || [], false); modelBars('model-calls', activity.models || [], true);
        table('model-table', ['Model', 'Calls', 'Input', 'Output', 'Total tokens', 'Peak date (UTC)', 'Peak calls', 'Missing output counts'], (activity.models || []).map(r => [r.model, count(r.calls), count(r.input_tokens), count(r.output_tokens), count(r.input_tokens + r.output_tokens), r.peak_day, count(r.peak_calls), count(r.missing_output_calls)]));
        $('ollama-version').textContent = provider.version ? 'Ollama ' + provider.version : '';
        const size = v => n(v) ? (v / 1024 ** 3).toFixed(2) + ' GiB' : 'Unavailable';
        $('running').textContent = provider.running_error || ((provider.running || []).length ? 'Loaded: ' + provider.running.map(m => `${m.name} (${size(m.size)}, expires ${m.expires_at ? new Date(m.expires_at).toLocaleString() : 'not reported'})`).join(' · ') : 'No models are currently loaded.');
        if (provider.models_error) html('inventory', `<p>${esc(provider.models_error)}</p>`);
        else table('inventory', ['Model', 'Origin', 'State', 'Size', 'Family', 'Parameters', 'Quantization', 'Modified'], (provider.models || []).map(m => [m.name, m.cloud ? 'Cloud · ' + m.remote_host : 'Local', m.loaded ? 'Loaded' : 'Available', size(m.size), m.family || '—', m.parameters || '—', m.quantization || '—', date(m.modified_at)]));
        $('updated').textContent = 'Chat checked ' + new Date().toLocaleTimeString() + (balance.updated_at ? ' · Credits ' + new Date(balance.updated_at).toLocaleTimeString() : ' · Account refresh needed');
    }

    async function refresh() {
        if (overlay.hidden || document.hidden || sessionInvalid) return;
        if (controller) { again = true; return; }
        const current = generation, selected = range;
        const abort = new AbortController(); controller = abort;
        const timeout = setTimeout(() => abort.abort(), 15000);
        $('refresh').disabled = true;
        try {
            const response = await fetch(overlay.dataset.url + '?range=' + range, { credentials: 'same-origin', cache: 'no-store', signal: abort.signal });
            if (!response.ok || response.redirected) throw Error('Usage could not refresh. Your session may have expired. Reload the chat to sign in again.');
            const next = await response.json();
            if (String(next.user_id) !== overlay.dataset.userId) {
                data = null; sessionInvalid = true;
                dialog.querySelectorAll('[role="tabpanel"]').forEach(p => { p.hidden = true; });
                dialog.querySelectorAll('button:not(.usage-close)').forEach(button => { button.disabled = true; });
                throw Error('The signed-in user changed in this browser. Reload the chat before viewing usage.');
            }
            if (current !== generation || overlay.hidden || selected !== range) return;
            data = next; render();
        } catch (error) {
            if (current === generation && !overlay.hidden) {
                $('status').textContent = error.name === 'AbortError' ? 'Refresh timed out. Existing figures may be stale; use Refresh to retry.' : error.message;
                $('status').classList.add('usage-warning');
            }
        } finally {
            clearTimeout(timeout);
            if (controller === abort) controller = null;
            $('refresh').disabled = sessionInvalid;
            if (again && !overlay.hidden) { again = false; schedule(); }
        }
    }
    function schedule() {
        if (overlay.hidden || scheduled) return;
        scheduled = setTimeout(() => { scheduled = null; refresh(); }, 900);
    }
    function close() {
        generation++; overlay.hidden = true; controller?.abort(); again = false;
        clearInterval(interval); clearTimeout(scheduled); scheduled = null;
        $('tooltip').hidden = true; document.body.style.overflow = oldOverflow;
        inertSiblings.forEach(([el, inert]) => { el.inert = inert; }); inertSiblings = [];
        (lastFocus?.isConnected && lastFocus.getClientRects().length ? lastFocus : document.getElementById('about-menu-button')).focus();
    }
    function open(event) {
        event?.preventDefault(); if (!overlay.hidden) return;
        generation++; lastFocus = document.activeElement; oldOverflow = document.body.style.overflow;
        // The overlay is a direct body child; preserve the existing inert states.
        inertSiblings = [...document.body.children].filter(el => el !== overlay && !['SCRIPT', 'STYLE'].includes(el.tagName)).map(el => [el, el.inert]);
        inertSiblings.forEach(([el]) => { el.inert = true; });
        document.body.style.overflow = 'hidden'; overlay.hidden = false;
        dialog.querySelector('[data-tab][aria-selected="true"]').focus(); refresh(); interval = setInterval(refresh, 30000);
    }
    overlay.tlmDismiss = close; dialog.tlmDismiss = close;
    opener.addEventListener('click', open);
    dialog.querySelectorAll('.usage-close').forEach(button => button.addEventListener('click', close));
    $('refresh').addEventListener('click', refresh);
    dialog.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => {
        range = button.dataset.range;
        dialog.querySelectorAll('[data-range]').forEach(el => el.setAttribute('aria-pressed', String(el === button)));
        $('status').textContent = 'Loading ' + range + ' usage…'; refresh();
    }));
    function selectTab(button) {
        dialog.querySelectorAll('[data-tab]').forEach(el => { el.setAttribute('aria-selected', String(el === button)); el.tabIndex = el === button ? 0 : -1; });
        dialog.querySelectorAll('[role="tabpanel"]').forEach(el => { el.hidden = el.id !== 'usage-' + button.dataset.tab; });
        $('tooltip').hidden = true;
    }
    dialog.querySelectorAll('[data-tab]').forEach(button => {
        button.addEventListener('click', () => selectTab(button));
        button.addEventListener('keydown', event => {
            const tabs = [...dialog.querySelectorAll('[data-tab]')], index = tabs.indexOf(button);
            const next = { ArrowRight: (index + 1) % 3, ArrowLeft: (index + 2) % 3, Home: 0, End: 2 }[event.key];
            if (next !== undefined) { event.preventDefault(); selectTab(tabs[next]); tabs[next].focus(); }
        });
    });
    dialog.addEventListener('keydown', event => {
        if (event.key !== 'Tab') return;
        const focusable = [...dialog.querySelectorAll('button,a[href],input,summary,[tabindex="0"]')].filter(el => !el.disabled && el.getClientRects().length);
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
    document.addEventListener('tlm:context-gauge', schedule);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) schedule(); });
    window.addEventListener('focus', schedule);
    function tooltip(event) {
        const target = event.target.closest('[data-tip]'); if (!target) return;
        const tip = $('tooltip'), rect = target.getBoundingClientRect(); tip.textContent = target.dataset.tip; tip.hidden = false;
        tip.style.left = Math.max(8, Math.min(rect.left, innerWidth - tip.offsetWidth - 12)) + 'px';
        tip.style.top = Math.max(8, Math.min(rect.top - tip.offsetHeight - 8, innerHeight - tip.offsetHeight - 12)) + 'px';
    }
    dialog.addEventListener('pointerover', tooltip);
    dialog.addEventListener('focusin', event => requestAnimationFrame(() => tooltip(event)));
    dialog.addEventListener('pointerout', event => {
        if (event.target.closest('[data-tip]') !== event.relatedTarget?.closest?.('[data-tip]')) $('tooltip').hidden = true;
    });
    dialog.addEventListener('focusout', () => { $('tooltip').hidden = true; });
    dialog.querySelector('.usage-body').addEventListener('scroll', () => {
        $('tooltip').hidden = true;
        if (document.activeElement.closest('[data-tip]')) requestAnimationFrame(() => tooltip({ target: document.activeElement }));
    }, { passive: true });
})();
