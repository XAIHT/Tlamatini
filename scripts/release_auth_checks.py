# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Normal UI authentication and disposable nonstaff user lifecycle checks."""
import re
import time

from playwright.sync_api import expect
import prompt_flow_connections_visible as browser_visibility
from prompt_flow_connections_visible import require_browser_foreground


def run_auth_checks(admin, base, checkpoint):
    username = 'release_access_' + str(time.time_ns())
    password = 'Release-Only-Access!42'
    member_context = None
    user_url = None
    staff_window = browser_visibility.TEST_BROWSER_WINDOW
    admin.bring_to_front()
    require_browser_foreground(admin)
    try:
        admin.goto(base + '/admin/auth/user/add/')
        admin.locator('#id_username').fill(username)
        admin.locator('#id_password1').fill(password)
        admin.locator('#id_password2').fill(password)
        admin.locator('input[name=_save]').click()
        expect(admin.locator('.success')).to_contain_text('successfully')
        admin.goto(base + '/admin/auth/user/?q=' + username)
        expect(admin.locator('#result_list tbody tr')).to_have_count(1)
        admin.get_by_role('link', name=username, exact=True).click()
        user_url = admin.url
        expect(admin.locator('#id_is_staff')).not_to_be_checked()
        expect(admin.locator('#id_is_superuser')).not_to_be_checked()
        admin.locator('#id_first_name').fill('Release access fixture')
        admin.locator('input[name=_save]').click()
        expect(admin.locator('.success')).to_contain_text('successfully')
        admin.goto(user_url)
        expect(admin.locator('#id_first_name')).to_have_value('Release access fixture')
        admin.get_by_role('link', name='History', exact=True).click()
        expect(admin.locator('#change-history')).to_contain_text(re.compile('first name', re.I))
        checkpoint('auth-01-user-create-edit-search-and-history', admin)

        # A second normal browser context keeps staff and nonstaff cookies apart.
        # This is the existing headed Chrome, not a headless browser launch.
        member_context = admin.context.browser.new_context(no_viewport=True)
        member = member_context.new_page()
        target = base + '/agent/prompt_flow_panel/'
        member.goto(target)
        member.bring_to_front()
        browser_visibility.TEST_BROWSER_WINDOW = None
        require_browser_foreground(member)
        expect(member.locator('#id_username')).to_be_visible()
        member.locator('#id_username').fill(username)
        member.locator('#id_password').fill('Incorrect-password-for-rejection')
        member.locator('button[type=submit], input[type=submit]').first.click()
        expect(member.locator('#id_username')).to_be_visible()
        expect(member.locator('body')).to_contain_text('Please enter a correct username and password')
        checkpoint('auth-02-wrong-password-rejected', member)
        member.locator('#id_password').fill(password)
        member.locator('button[type=submit], input[type=submit]').first.click()
        expect(member.locator('#pmt-play')).to_be_visible(timeout=60000)
        checkpoint('auth-03-login-returns-to-requested-panel', member)

        for path in ('/admin/', '/admin/auth/user/', '/admin/auth/user/add/'):
            member.goto(base + path)
            expect(member.locator('#login-form')).to_be_visible()
            expect(member.locator('#result_list')).to_have_count(0)
            expect(member.locator('#user_form')).to_have_count(0)
        checkpoint('auth-04-nonstaff-admin-actions-denied', member)
        member.goto(base + '/agent/agent/')
        # Follow the product's own logout link/form instead of synthesizing a request.
        logout = member.locator('#logout-button')
        expect(logout).to_be_visible(timeout=60000)
        logout.click()
        expect(member.locator('#id_username')).to_be_visible(timeout=30000)
        member.goto(target)
        expect(member.locator('#id_username')).to_be_visible()
        checkpoint('auth-05-logout-protects-panel', member)
    finally:
        if member_context:
            member_context.close()
        browser_visibility.TEST_BROWSER_WINDOW = staff_window
        if user_url:
            admin.bring_to_front()
            admin.goto(user_url)
            admin.locator('.deletelink').click()
            admin.locator('input[type=submit]').click()
            expect(admin.locator('.success')).to_contain_text('successfully')
            admin.goto(base + '/admin/auth/user/?q=' + username)
            expect(admin.locator('#result_list tbody tr')).to_have_count(0)
            checkpoint('auth-06-test-user-removed', admin)
