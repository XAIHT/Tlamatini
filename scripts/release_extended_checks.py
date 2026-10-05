# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Real, headed UI acceptance cases; never inject application state or responses."""
import json
import time

from playwright.sync_api import expect


def run_extended_checks(chat, acp, prompting, out, checkpoint):
    failures = []
    inventory = chat.locator('button[id], a[id], input[type=checkbox][id]').evaluate_all(
        "els=>els.map(e=>({id:e.id,label:(e.innerText||e.getAttribute('aria-label')||e.title||'').trim()}))"
    )
    (out / 'chat-control-inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')

    def menu(menu_id, item_id):
        chat.bring_to_front()
        chat.locator('#' + menu_id).click()
        chat.locator('#' + item_id).click()

    def dialog(content_id):
        return chat.locator('.ui-dialog').filter(has=chat.locator('#' + content_id))

    def dismiss():
        for _ in range(3):
            pop = chat.locator('.ui-dialog:visible')
            if pop.count():
                cancel = pop.last.get_by_role('button', name='Cancel', exact=True)
                close = pop.last.get_by_role('button', name='Close', exact=True)
                if cancel.count():
                    cancel.click()
                elif close.count():
                    close.click()
                else:
                    pop.last.locator('.ui-dialog-titlebar-close').click()
            else:
                chat.keyboard.press('Escape')

    def case(name, action):
        print('EXTENDED START: ' + name, flush=True)
        try:
            details = action()
            checkpoint(name, chat, details)
        except Exception as exc:
            # Playwright includes the full rendered catalog in some assertion
            # errors. Keep the live console readable; retain full diagnostics
            # in the evidence file instead of flooding its output pipe.
            failures.append(dict(case=name, error=str(exc)))
            print(type(exc).__name__ + ': ' + str(exc)[:1500], flush=True)
            import panel_search_title_visible as visible
            visible.photograph(name + '-failed')
            dismiss()
        (out / 'extended-failures.json').write_text(json.dumps(failures, indent=2), encoding='utf-8')

    def models():
        menu('config-menu-button', 'config-models')
        box = dialog('config-models-dialog-message')
        expect(box).to_be_visible()
        expect(box.locator('[data-model-kind]')).to_have_count(38)
        expect(box.get_by_role('tab')).to_have_count(6)
        values = box.locator('[data-model-kind=ollama]').evaluate_all('els=>els.map(e=>e.value)')
        assert values and set(values) == {'nemotron-3-ultra:cloud'}, 'An Ollama model escaped the campaign restriction'
        for tab in box.get_by_role('tab').all():
            tab.click()
            expect(tab).to_have_attribute('aria-selected', 'true')
        search = box.locator('#config-models-search')
        search.fill('Talker')
        expect(box.locator('.model-settings-card:visible')).to_have_count(2)
        search.fill('no matching release test setting')
        expect(box.locator('#config-models-no-results')).to_be_visible()
        search.fill('')
        box.get_by_role('tab').first.click()
        field = box.locator('[data-config-key=unified_agent_model]')
        field.fill('')
        box.get_by_role('button', name='Save', exact=True).click()
        expect(box).to_be_visible()
        assert field.input_value() == ''
        box.get_by_role('button', name='Cancel', exact=True).click()
        menu('config-menu-button', 'config-models')
        expect(dialog('config-models-dialog-message').locator('[data-config-key=unified_agent_model]')).to_have_value('nemotron-3-ultra:cloud')
        dialog('config-models-dialog-message').get_by_role('button', name='Save', exact=True).click()
        expect(dialog('config-models-dialog-message')).to_be_hidden()
        dismiss()
        return {'settings': 38, 'categories': 6, 'ollama_model': 'nemotron-3-ultra:cloud', 'empty_rejected': True}

    case('12-models-tabs-search-validation-save-reopen', models)

    def agents():
        menu('config-menu-button', 'enable-agents')
        box = dialog('agents-dialog-message')
        expect(box.locator('#agents-list input[type=checkbox]')).to_have_count(89)
        box.get_by_role('button', name='Cancel', exact=True).click()
        return {'agents': 89}
    case('13-configure-all-agent-controls', agents)

    def mcps():
        menu('config-menu-button', 'enable-mcps')
        box = dialog('mcps-dialog-message')
        expect(box).to_be_visible()
        count = box.locator('input[type=checkbox]').count()
        assert count >= 3
        box.get_by_role('button', name='Cancel', exact=True).click()
        return {'rows': count}
    case('14-configure-mcp-controls', mcps)

    def browse_skills():
        menu('skills-menu-button', 'browse-skills')
        box = dialog('skills-browse-dialog-message')
        expect(box.locator('#skills-browse-list')).not_to_contain_text('Loading')
        expect(box.locator('#skills-browse-list li')).to_have_count(29)
        count = box.locator('#skills-browse-list li').count()
        box.locator('#skills-browse-search').fill('summarize')
        expect(box.locator('#skills-browse-list')).to_contain_text('summarize')
        box.get_by_role('button', name='Close', exact=True).click()
        return {'listed': count}
    case('15-skills-browse-search', browse_skills)

    def skills_config():
        menu('skills-menu-button', 'configure-skills')
        box = dialog('skills-configure-dialog-message')
        expect(box).to_be_visible()
        count = box.locator('input[type=checkbox]').count()
        assert count > 0
        box.get_by_role('button', name='Cancel', exact=True).click()
        return {'rows': count}
    case('16-skills-configuration', skills_config)

    def skills_diagnostics():
        menu('skills-menu-button', 'skills-diagnostics')
        box = dialog('skills-diagnostics-dialog-message')
        expect(box.locator('#skills-diagnostics-summary')).not_to_have_text('')
        expect(box.locator('#skills-diagnostics-summary')).not_to_contain_text('Loading')
        expect(box.locator('#skills-diagnostics-sections')).not_to_have_text('')
        summary = box.locator('#skills-diagnostics-summary').inner_text()
        box.get_by_role('button', name='Close', exact=True).click()
        return {'summary': summary}
    case('17-skills-diagnostics', skills_diagnostics)

    def microphone_settings():
        menu('config-menu-button', 'config-mic')
        box = chat.locator('#tlm-mic-overlay')
        expect(box).to_be_visible()
        original = box.locator('input[name=tlm-mic-mode]:checked').input_value()
        box.locator('input[name=tlm-mic-mode][value=draft]').check()
        box.locator('#tlm-mic-save').click()
        menu('config-menu-button', 'config-mic')
        expect(box.locator('input[name=tlm-mic-mode][value=draft]')).to_be_checked()
        box.locator(f'input[name=tlm-mic-mode][value={original}]').check()
        box.locator('#tlm-mic-save').click()
        return {'save_reopen_restore': True, 'recording_started': False}
    case('18-microphone-settings-save-reopen', microphone_settings)

    def voice_settings():
        menu('config-menu-button', 'config-voice')
        box = chat.locator('#tlm-voice-overlay')
        expect(box).to_be_visible()
        box.locator('input[name=tlm-voice-mode][value=silent]').check()
        box.locator('#tlm-voice-save').click()
        menu('config-menu-button', 'config-voice')
        expect(box.locator('input[name=tlm-voice-mode][value=silent]')).to_be_checked()
        box.locator('#tlm-voice-close').click()
        return {'silent_saved': True, 'speech_inference_started': False}
    case('19-voice-settings-save-reopen', voice_settings)

    def catalog():
        chat.locator('#prompts-catalog').click()
        expect(chat.locator('#modal')).to_be_visible()
        search = chat.locator('#prompt-search-input')
        search.fill('#121')
        expect(chat.locator('#tools-body')).to_contain_text('YOUR FIRST VOICE COMMAND')
        search.fill('release-test-no-such-prompt-123456789')
        expect(chat.locator('#prompt-search-count')).to_contain_text('0')
        chat.keyboard.press('Escape')
        expect(search).to_have_value('')
        expect(chat.locator('#modal')).to_be_visible()
        chat.keyboard.press('Escape')
        expect(chat.locator('#modal')).to_be_hidden()
        return {'search_and_no_results': True, 'escape_clears_then_dismisses': True}
    case('20-prompts-catalog-search-and-dismiss', catalog)

    def urls():
        menu('config-menu-button', 'config-urls')
        box = dialog('config-urls-dialog-message')
        expect(box).to_be_visible()
        count = box.locator('[data-config-key]').count()
        assert count >= 8
        box.get_by_role('button', name='Cancel', exact=True).click()
        return {'fields': count, 'settings_changed': False}
    case('20a-server-urls-dialog', urls)

    def contacts():
        menu('config-menu-button', 'config-contacts')
        box = chat.locator('#contacts-dialog-message')
        expect(box).to_be_visible()
        expect(box.locator('#contacts-search')).to_be_visible()
        box.locator('#contacts-search').fill('release-check-no-such-contact')
        box.locator('#contacts-cancel').click()
        expect(box).to_be_hidden()
        return {'search_and_cancel': True, 'messages_sent': 0}
    case('20b-contacts-search-cancel', contacts)

    def access_keys():
        menu('config-menu-button', 'access-keys-wizard')
        box = dialog('access-keys-wizard-dialog-message')
        expect(box.locator('#access-keys-wizard-nav button').first).to_be_visible()
        tabs = box.locator('#access-keys-wizard-nav button')
        count = tabs.count()
        assert count > 0
        for tab in tabs.all():
            tab.click()
            expect(box.locator('#access-keys-wizard-content')).not_to_have_text('')
        box.get_by_role('button', name='Close', exact=True).click()
        return {'sections': count, 'credentials_changed': False}
    case('20c-access-keys-wizard-sections', access_keys)

    def external_mcps():
        menu('external-menu-button', 'external-mcps')
        box = chat.locator('#external-mcps-dialog-message')
        expect(box).to_be_visible()
        expect(box.locator('#external-mcps-search')).to_be_visible()
        box.locator('#external-mcps-search').fill('memory')
        expect(box.locator('#external-mcps-list')).to_contain_text('memory')
        box.locator('#external-mcps-cancel').click()
        expect(box).to_be_hidden()
        return {'catalog_search': True, 'activation_changed': False}
    case('20d-external-mcp-catalog-search-cancel', external_mcps)

    def document_save():
        name = 'Chat document round trip ñ.txt'
        chat.once('dialog', lambda d: d.accept(name))
        with chat.expect_download() as download:
            chat.locator('#save-as-button').click()
        path = out / name
        download.value.save_as(path)
        assert path.read_text(encoding='utf-8') == (out / 'Keep the chat document.txt').read_text(encoding='utf-8')
        with chat.expect_file_chooser() as chooser:
            chat.locator('#open-button').click()
        chooser.value.set_files(path)
        expect(chat.locator('#filename')).to_contain_text(name)
        return {'literal_document_bytes_preserved': True}
    case('20e-main-chat-document-save-open', document_save)

    def compact():
        expect(chat.locator('#chat-message-input')).to_be_editable(timeout=180000)
        switch = chat.locator('#compact-mode-enabled')
        if not switch.is_checked():
            switch.click()
            expect(switch).to_be_checked(timeout=30000)
        menu('config-menu-button', 'enable-agents')
        box = dialog('agents-dialog-message')
        expect(box.locator('#agents-list input:checked')).to_have_count(0)
        box.get_by_role('button', name='Cancel', exact=True).click()
        if chat.locator('#self-modify-toggle').count() and chat.locator('#self-modify-toggle').is_enabled():
            if chat.locator('#self-modify-toggle').is_checked():
                chat.locator('#self-modify-toggle').click()
                expect(chat.locator('#self-modify-toggle')).not_to_be_checked()
        chat.locator('#multi-turn-enabled').uncheck()
        chat.locator('#internetEnabled').uncheck()
        chat.locator('#acpx-enabled').uncheck()
        return {'compact_real_agent_rows_unticked': True, 'multi_turn': False}
    case('21-compact-updates-real-configure-rows', compact)

    def ask(prompt, token):
        chat.bring_to_front()
        expect(chat.locator('#chat-message-input')).to_be_editable(timeout=180000)
        before = chat.locator('.bot-message[data-message-id]').count()
        chat.locator('#chat-message-input').fill(prompt)
        chat.locator('#chat-message-submit').click()
        started = time.monotonic()
        while time.monotonic() - started < 180:
            answers = chat.locator('.bot-message[data-message-id]')
            if answers.count() > before:
                response = answers.last.locator('.message-content').inner_text()
                if token in response:
                    expect(chat.locator('#chat-message-input')).to_be_editable(timeout=30000)
                    return {'elapsed_seconds': round(time.monotonic() - started, 2), 'answer': response}
                if chat.locator('#chat-message-input').is_editable():
                    raise AssertionError('Chat returned an unexpected completed answer: ' + response[:1200])
            print(f'CHAT WAIT: {round(time.monotonic() - started)}s; persisted answers={answers.count()}', flush=True)
            chat.wait_for_timeout(5000)
        raise AssertionError('Expected real answer did not arrive within 180 seconds')

    case('22-real-chat-nemotron-response', lambda: ask(
        'This is a chat release check. Do not use tools. Reply with the exact token TLAMATINI-CHAT-42 and the result of 16 + 26.',
        'TLAMATINI-CHAT-42'))
    case('23-real-chat-conversation-followup', lambda: ask(
        'Do not use tools. What result did I ask you to calculate in my previous message? Include the exact token FOLLOWUP-42 and the number.',
        'FOLLOWUP-42'))
    if failures:
        raise AssertionError(f'{len(failures)} extended checks failed; see extended-failures.json')
