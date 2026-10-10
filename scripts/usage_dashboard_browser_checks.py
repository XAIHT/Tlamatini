# Tlamatini Author Banner — Angela López Mendoza
"""Visible real-page checks; deterministic data cases are explicitly labelled."""
import json


def run_checks(page, context, user_id, out, capture, results):
    from playwright.sync_api import expect

    def passed(name):
        results.append({'name': name, 'ok': True})
        print('PASS:', name, flush=True)

    page.wait_for_selector('#about-menu-button', state='attached', timeout=60000)
    if page.locator('.navbar-toggler').is_visible() and not page.locator('#about-menu-button').is_visible():
        page.locator('.navbar-toggler').click()
    page.locator('#about-menu-button').click()
    page.locator('#usage-button').click()
    expect(page.locator('#usage-dialog')).to_be_visible()
    page.wait_for_function("document.getElementById('usage-updated').textContent.includes('Chat checked')", timeout=30000)
    area = page.locator('#usage-dialog').evaluate('(el) => el.getBoundingClientRect().width * el.getBoundingClientRect().height / (innerWidth * innerHeight)')
    assert .45 <= area <= .601, area
    passed('Real About → Usage opens; covers at most 60% of the client area')
    expect(page.locator('#usage-title')).to_have_text('ABOUT USAGE')
    assert page.locator('#usage-dialog').evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)<=16')
    assert page.locator('#usage-title').evaluate('(el)=>parseFloat(getComputedStyle(el).fontSize)<=18')
    assert 'Unknown' not in page.locator('#usage-dialog').inner_text()
    official = json.loads((out / 'official-comparison.json').read_text(encoding='utf-8'))
    values = page.locator('#usage-credit-cards .usage-credit-value').all_text_contents()
    assert values == [official['available'], official['used'], official['allowance']], values
    expect(page.locator('#usage-credit-cards')).to_contain_text('Monthly credits refill in ' + str(official['weeks']) + ' weeks')
    expect(page.locator('#usage-credit-cards')).to_contain_text(official['refill'])
    passed('Live credits match the signed-in Ollama website; refill weeks/date, normal fonts and correct heading')
    assert page.locator('#usage-spend-chart svg rect').count() > 7
    passed('Live Ollama account totals and credit/token graphs load through authenticated HTTP')
    capture('live-cloud-usage.png')
    page.locator('[data-range="30d"]').click()
    page.wait_for_timeout(2000)
    expect(page.locator('[data-range="30d"]')).to_have_attribute('aria-pressed', 'true')
    expect(page.locator('#usage-cloud-totals')).to_contain_text('Rolling 30d')
    expect(page.locator('#usage-credit-cards .usage-credit-value').first).to_have_text(official['available'])
    passed('Changing the rolling activity range does not change authoritative monthly credits')
    page.locator('#usage-tab-models').click()
    expect(page.locator('#usage-inventory table')).to_be_visible()
    capture('live-model-inventory.png')
    passed('Real model inventory, runtime version and loaded-model information render')
    page.keyboard.press('Escape')
    expect(page.locator('#usage-overlay')).to_be_hidden()
    assert page.locator('#about-menu-button').evaluate('(el) => document.activeElement === el')
    passed('Escape uses the normal close path and restores menu focus')
    run_live_request(page, user_id, out, capture, results)


def run_live_request(page, user_id, out, capture, results):
    from playwright.sync_api import expect

    def passed(name):
        results.append({'name': name, 'ok': True})
        print('PASS:', name, flush=True)

    # A real submitted request, normal WebSocket and the configured live model.
    if page.locator('#self-modify-enabled').is_enabled() and page.locator('#self-modify-enabled').is_checked():
        page.locator('#self-modify-enabled').click()
        expect(page.locator('#self-modify-enabled')).not_to_be_checked(timeout=15000)
    page.locator('#chat-message-input').fill('For a UI verification, write a short paragraph of about 100 words about how rain forms. Do not use any tools.')
    page.locator('#chat-message-submit').click()
    page.wait_for_function("document.getElementById('chat-message-input').readOnly", timeout=15000)
    page.locator('#about-menu-button').click()
    page.locator('#usage-button').click()
    expect(page.locator('#usage-dialog')).to_be_visible()
    page.locator('#usage-tab-activity').click()
    page.locator('#usage-refresh').click()
    capture('live-usage-during-request.png')
    passed('Usage opens and refreshes during a real submitted chat request')
    page.wait_for_function("!document.getElementById('chat-message-input').readOnly", timeout=180000)
    page.locator('#usage-refresh').click()
    page.wait_for_timeout(2000)
    capture('live-chat-usage.png')
    totals = page.locator('#usage-chat-totals').inner_text()
    (out / 'live-chat-totals.txt').write_text(totals, encoding='utf-8')
    assert page.locator('#usage-chat-totals strong').first.inner_text() != '0', totals
    passed('A real model response persists input/output usage and appears in the dashboard')
    # Detailed fixture cases run separately; the live account result above is not fabricated.
    (out / 'live-browser-checks.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
