# Tlamatini Author Banner — Angela López Mendoza
"""Explicit synthetic-data UI cases, supplemental to the real-source checks."""
from datetime import datetime, timedelta, timezone
import json


def run_fixtures(page, context, user_id, out, capture, results):
    from playwright.sync_api import expect
    now = datetime.now(timezone.utc)
    state = {'mode': 'normal', 'requests': 0, 'revision': 0}
    models = ['Sample · Atlas', 'Sample · Cobalt', 'Sample · Ember', '<img src=x onerror="window.usageXSS=1">']

    def payload(days):
        daily = []
        for i in range(days):
            calls = 0 if state['mode'] == 'empty' else (i * 7 + 3) % 24 + state['revision']
            day = (now - timedelta(days=days - i - 1)).date().isoformat()
            daily.append({'date': day, 'usage_usd': calls * .023, 'request_count': calls,
                          'calls': calls, 'input_tokens': calls * 2450, 'cached_input_tokens': calls * 730,
                          'output_tokens': calls * 280, 'missing_output_calls': 0, 'partial': i == days - 1})
        totals = {key: sum(row[key] for row in daily) for key in ('calls', 'usage_usd', 'request_count', 'input_tokens', 'cached_input_tokens', 'output_tokens', 'missing_output_calls')}
        per_model = [{'model': name, 'calls': (4 - i) * 6, 'input_tokens': (4 - i) * 17500,
                      'output_tokens': (4 - i) * 2200, 'missing_output_calls': 0,
                      'peak_day': daily[-1 - i]['date'], 'peak_calls': 4 - i} for i, name in enumerate(models)]
        account = {'data': {'totals': totals, 'daily': daily}, 'stale': False, 'updated_at': now.isoformat()}
        result = {'user_id': user_id, 'range': f'{days}d', 'provider': {
            'account': 'SYNTHETIC UI TEST DATA', 'plan': state.get('plan', 'pro'), 'account_available': True, 'account_key': 'synthetic',
            'endpoint': 'Test fixture · no billing changes', 'ranges': {'7d': account, '30d': account},
            'models': [{'name': name, 'cloud': i % 2 == 0, 'loaded': i == 0, 'size': 4e9,
                        'family': 'sample', 'parameters': '8B', 'quantization': 'Q4',
                        'remote_host': 'test.invalid', 'modified_at': now.isoformat()} for i, name in enumerate(models)],
            'running': [{'name': models[0], 'size': 4e9, 'expires_at': now.isoformat()}], 'version': 'test'},
            'activity': {'totals': totals, 'daily': daily, 'models': [] if state['mode'] == 'empty' else per_model,
                         'scope': 'SYNTHETIC UI TEST DATA · deterministic chart and accessibility cases.', 'since': daily[0]['date']}}
        result['provider']['balance'] = {'data': {'kind': 'credits', 'allowance': 100,
            'monthly_remaining': 63.25, 'purchased': 20, 'remaining': 83.25, 'used': 36.75,
            'percent': 36.75, 'end': (now + timedelta(days=29)).isoformat()},
            'updated_at': now.isoformat(), 'stale': False}
        if state['mode'] == 'free':
            result['provider']['balance']['data'].update(allowance=0, monthly_remaining=0, purchased=0,
                                                       remaining=0, used=0, percent=None)
        if state['mode'] == 'max':
            result['provider']['balance']['data'].update(allowance=300, monthly_remaining=263.25,
                                                       remaining=283.25, percent=12.25)
        if state['mode'] == 'legacy':
            result['provider']['balance']['data'] = {'kind': 'legacy', 'purchased': 20,
                'limits': [{'name': 'session', 'remaining_percent': 75.123456,
                            'resets_at': now.isoformat()},
                           {'name': 'weekly', 'remaining_percent': 0, 'resets_at': now.isoformat()}]}
            for key in ('usage_usd', 'input_tokens', 'cached_input_tokens', 'output_tokens'):
                totals[key] = None
                for row in daily:
                    row[key] = None
        if state['mode'] == 'purchased':
            result['provider']['balance']['data'] = {'kind': 'purchased', 'purchased': 12.34567}
        if state['mode'] == 'unavailable':
            result['provider'] = {}
            result['provider_error'] = 'Synthetic account unavailable case.'
        if state['mode'] == 'pending':
            result['provider'] = {'pending': True}
        if state['mode'] == 'account-switch':
            result['user_id'] = user_id + 999
        return result

    def route_handler(route):
        state['requests'] += 1
        if state['mode'] == 'http-error':
            route.fulfill(status=503, content_type='application/json', body='{}')
        else:
            route.fulfill(content_type='application/json', body=json.dumps(payload(30 if '30d' in route.request.url else 7)))

    pattern = '**/agent/usage/?*'
    page.route(pattern, route_handler)

    def passed(name):
        results.append({'name': 'Synthetic: ' + name, 'ok': True})
        print('PASS synthetic:', name, flush=True)

    def refresh():
        page.locator('#usage-refresh').click()
        page.wait_for_timeout(1200)

    page.locator('#usage-tab-account').click()
    refresh()
    expect(page.locator('#usage-account-note')).to_contain_text('SYNTHETIC UI TEST DATA')
    page.locator('[data-range="30d"]').click()
    page.wait_for_timeout(1200)
    assert page.locator('#usage-spend-chart svg g').count() == 30
    assert '$36.75' in page.locator('#usage-credit-cards').inner_text()
    assert 'Cache hit rate' in page.locator('#usage-composition').inner_text()
    page.locator('#usage-spend-chart svg g').nth(8).focus()
    expect(page.locator('#usage-tooltip')).to_be_visible()
    passed('30-day colorful charts, credit arithmetic, token composition and focus tooltips')
    capture('synthetic-cloud-dashboard.png')
    import re
    for plan, mode, expected in [('free', 'free', '$0.00'), ('max', 'max', '$300.00'),
                                 ('pro', 'legacy', '75.12%'), ('max', 'legacy', '0.00%'),
                                 ('unlimited', 'purchased', '$12.35')]:
        state.update(plan=plan, mode=mode)
        refresh()
        cards = page.locator('#usage-credit-cards').inner_text()
        assert expected in cards, cards
        if mode == 'free':
            assert 'No monthly credit allowance' in cards
            assert '%' not in cards
        assert 'Unknown' not in page.locator('#usage-dialog').inner_text()
        assert not re.search(r'\$[\d,]+\.\d{3,}', page.locator('#usage-dialog').inner_text())
        if mode == 'legacy':
            assert 'Monthly allowance' not in cards
            expect(page.locator('#usage-spend-panel')).to_be_hidden()
            expect(page.locator('#usage-token-panel')).to_be_hidden()
            assert page.locator('#usage-cloud-table th').all_text_contents() == ['Date (UTC)', 'Requests']
        if plan == 'unlimited':
            assert 'Monthly allowance' not in cards
            assert 'unlimited' not in cards.lower()
        passed('Plan layout ' + plan + ' / ' + mode + ' uses returned values only, with at most two decimals')
        capture('synthetic-plan-' + plan + '-' + mode + '.png')
    state.update(plan='pro', mode='normal')
    refresh()
    page.locator('#usage-tab-activity').click()
    assert page.locator('.usage-calendar-cell').count() == 30
    before = page.locator('#usage-chat-totals').inner_text()
    baseline = state['requests']
    state['revision'] = 10
    page.evaluate("() => { for (let i=0;i<100;i++) document.dispatchEvent(new CustomEvent('tlm:context-gauge', {detail:{}})); }")
    page.wait_for_timeout(1800)
    assert page.locator('#usage-chat-totals').inner_text() != before
    assert 1 <= state['requests'] - baseline <= 2
    passed('Context-gauge events update totals and graphs, with request coalescing')
    capture('synthetic-chat-activity.png')
    page.locator('#usage-tab-models').click()
    assert page.locator('#usage-model-chart .usage-model-row').count() == 4
    assert page.locator('#usage-model-calls .usage-model-row').count() == 4
    assert page.locator('#usage-model-table tbody tr').count() == 4
    assert page.locator('#usage-models img').count() == 0
    assert not page.evaluate('window.usageXSS || false')
    passed('Per-model graphs, peak dates, exact statistics and escaped model names')
    capture('synthetic-model-statistics.png')
    page.locator('#usage-tab-models').focus()
    page.keyboard.press('ArrowLeft')
    expect(page.locator('#usage-tab-activity')).to_have_attribute('aria-selected', 'true')
    page.locator('.usage-footer .usage-close').focus()
    page.keyboard.press('Tab')
    assert page.locator('.usage-header .usage-close').evaluate('(el)=>el===document.activeElement')
    page.mouse.click(2, 140)
    expect(page.locator('#usage-dialog')).to_be_visible()
    passed('Keyboard tabs and focus trap work; backdrop does not dismiss the dialog')
    state['mode'] = 'empty'
    refresh()
    assert page.locator('#usage-chat-chart rect:not([fill="transparent"])').evaluate_all('(els)=>els.every(e=>Number(e.getAttribute("height"))===0)')
    passed('Zero-token days render no invented nonzero bars')
    state['mode'] = 'unavailable'
    refresh()
    assert 'unavailable' in page.locator('#usage-status').inner_text().lower()
    assert page.locator('#usage-chat-totals strong').first.inner_text() != 'Unavailable'
    passed('Unavailable cloud data keeps independent chat statistics usable')
    state['mode'] = 'pending'
    refresh()
    expect(page.locator('#usage-credit-cards')).to_contain_text('Refreshing your account credits')
    assert 'could not load' not in page.locator('#usage-credit-cards').inner_text()
    passed('A pending account request shows loading, without an invented failure or balance')
    state['mode'] = 'http-error'
    refresh()
    expect(page.locator('#usage-status')).to_contain_text('could not refresh')
    expect(page.locator('#usage-refresh')).to_be_enabled()
    passed('Network errors preserve content and leave a working retry button')
    state['mode'] = 'normal'
    refresh()
    page.set_viewport_size({'width': 390, 'height': 844})
    page.locator('#usage-tab-account').click()
    page.wait_for_timeout(500)
    assert page.locator('#usage-dialog').evaluate('(e)=>e.clientWidth>=innerWidth*.9')
    assert page.locator('#usage-dialog').evaluate('(e)=>e.getBoundingClientRect().width*e.getBoundingClientRect().height/(innerWidth*innerHeight)<=.601')
    assert page.locator('#usage-dialog').evaluate('(e)=>e.scrollWidth<=e.clientWidth+1')
    expect(page.locator('.usage-footer .usage-close')).to_be_in_viewport()
    passed('Narrow viewport preserves dialog width, readable cards and visible footer buttons')
    capture('synthetic-narrow-layout.png')
    page.set_viewport_size({'width': 1100, 'height': 900})
    state['mode'] = 'account-switch'
    refresh()
    expect(page.locator('#usage-status')).to_contain_text('signed-in user changed')
    expect(page.locator('#usage-refresh')).to_be_disabled()
    expect(page.locator('#usage-account')).to_be_hidden()
    passed('A changed signed-in user hides data and requires a reload')
    page.unroute(pattern, route_handler)
    page.keyboard.press('Escape')
    page.reload(wait_until='domcontentloaded')
    if page.locator('.navbar-toggler').is_visible() and not page.locator('#about-menu-button').is_visible():
        page.locator('.navbar-toggler').click()
    page.locator('#about-menu-button').click()
    page.locator('#usage-button').click()
    page.wait_for_timeout(1500)
    (out / 'fixture-browser-checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
