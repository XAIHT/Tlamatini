# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Inspect every actual ACP agent and round-trip its file through the visible UI.

This proves editor/configuration/file carriage, not external hardware or service
execution. Run only through the verified headed release harness.
"""
import json
import re

from playwright.sync_api import expect
import panel_search_title_visible as visible
from prompt_flow_connections_visible import require_browser_foreground


def run_agent_catalog_checks(page, out, checkpoint, only=None):
    page.bring_to_front()
    require_browser_foreground(page)
    expect(page.locator('#agents-list')).to_have_attribute('aria-busy', 'false', timeout=60000)
    names = page.locator('#agents-list .agent-tool-item').evaluate_all('els=>els.map(e=>e.dataset.content)')
    assert len(names) == 89 and len(set(names)) == 89, 'Incomplete or duplicate agent catalog'
    if only:
        assert only in names, 'Unknown catalog agent: ' + only
        names = [only]
    page.get_by_role('button', name='File', exact=True).click()
    page.locator('#file-close-button').click()
    expect(page.locator('.canvas-item')).to_have_count(0)
    results = []
    directory = out / 'agent-files'
    directory.mkdir(exist_ok=True)
    search = page.locator('#acp-agent-search')
    viewport = page.locator('#submonitor-container')

    def add_agent(name, x):
        search.fill(name)
        item = page.locator('#agents-list .agent-tool-item').filter(has=page.get_by_text(name, exact=True))
        expect(item).to_have_count(1)
        item.drag_to(viewport, target_position={'x': x, 'y': 260})
        expect(page.locator('#acp-flow-settings')).to_be_enabled(timeout=60000)
        return page.locator('.canvas-item').last

    def connect(source, target):
        a, b = source.locator('.output-triangle').first.bounding_box(), target.locator('.input-triangle').first.bounding_box()
        page.mouse.move(a['x'] + a['width'] / 2, a['y'] + a['height'] / 2)
        page.mouse.down()
        page.mouse.move(b['x'] + b['width'] / 2, b['y'] + b['height'] / 2, steps=12)
        page.mouse.up()
        expect(page.locator('#acp-flow-settings')).to_be_enabled(timeout=60000)

    def schema(properties):
        return properties.locator('[data-key], [data-field], [data-param], input[type=checkbox]').evaluate_all(
            'els=>els.map(e=>e.dataset.key||e.dataset.field||e.dataset.param||e.value)')

    for index, name in enumerate(names, 1):
        record = {'agent': name, 'index': index, 'status': 'FAIL'}
        print(f'AGENT EDITOR START {index}/{len(names)}: {name}', flush=True)
        try:
            page.bring_to_front()
            add_agent(name, 420 if name == 'Parametrizer' else 280)
            expect(page.locator('.canvas-item')).to_have_count(1)
            identity = page.locator('.canvas-item').get_attribute('id')
            node = page.locator('#' + identity)
            expected_nodes, expected_edges = 1, 0
            if name == 'Cleaner':
                add_agent('Sleeper', 700)
                expected_nodes = 2
            if name == 'Parametrizer':
                node.click()
                page.locator('#acp-configure').click()
                expect(page.locator('#parametrizer-error-overlay')).to_contain_text('No source agent connected')
                page.locator('#parametrizer-error-ok').click()
                source_id = add_agent('Apirer', 120).get_attribute('id')
                target_id = add_agent('Sleeper', 760).get_attribute('id')
                connect(page.locator('#' + source_id), node)
                connect(node, page.locator('#' + target_id))
                expected_nodes, expected_edges = 3, 2
                expect(page.locator('.connection-group')).to_have_count(2)
            node.click()
            page.locator('#acp-configure').click()
            properties = (page.locator('#parametrizer-dialog-overlay') if name == 'Parametrizer'
                          else page.locator('.ui-dialog:visible').filter(has=page.locator('#canvas-item-dialog-message')))
            expect(properties).to_be_visible(timeout=30000)
            fields = schema(properties)
            assert fields, 'No configuration fields rendered'
            record.update(fields=fields, ports=node.locator('.input-triangle, .output-triangle').count())
            if index % 10 == 1 or name in ('Starter', 'Sleeper', 'Ender', 'File-Creator'):
                page.wait_for_timeout(500)
                visible.photograph(f'agent-{index:02d}-configuration')
            if name == 'Parametrizer':
                properties.locator('.parametrizer-source-item').first.click()
                properties.locator('.parametrizer-target-item').first.click()
                expect(properties.locator('svg path')).to_have_count(1)
                properties.get_by_role('button', name='Save Mappings', exact=True).click()
            else:
                properties.get_by_role('button', name='Cancel', exact=True).click()
            expect(properties).to_be_hidden()
            filename = f'{index:02d}-' + re.sub(r'[^A-Za-z0-9_-]', '-', name) + '.flw'
            page.get_by_role('button', name='File', exact=True).click()
            page.once('dialog', lambda d, filename=filename: d.accept(filename))
            with page.expect_download() as download:
                page.locator('#save-as-button').click()
            saved = directory / filename
            download.value.save_as(saved)
            before = json.loads(saved.read_text(encoding='utf-8'))
            assert len(before['nodes']) == expected_nodes and len(before['connections']) == expected_edges
            assert identity in {n['id'] for n in before['nodes']}
            if name == 'Parametrizer':
                saved_node = next(n for n in before['nodes'] if n['id'] == identity)
                assert len(saved_node['configData']['_parametrizer_mappings']) == 1
            page.get_by_role('button', name='File', exact=True).click()
            with page.expect_file_chooser() as choice:
                page.locator('#file-open-button').click()
            choice.value.set_files(saved)
            expect(page.locator('.canvas-item')).to_have_count(expected_nodes)
            expect(page.locator('#' + identity)).to_be_visible()
            expect(page.locator('#filename')).to_contain_text(filename)
            node.click()
            page.locator('#acp-configure').click()
            expect(properties).to_be_visible()
            after_fields = schema(properties)
            assert after_fields == fields, 'Configuration schema changed after Save/Open'
            if name == 'Parametrizer':
                expect(properties.locator('svg path')).to_have_count(1)
            properties.get_by_role('button', name='Cancel', exact=True).click()
            page.get_by_role('button', name='File', exact=True).click()
            page.locator('#file-close-button').click()
            expect(page.locator('.canvas-item')).to_have_count(0)
            record.update(status='PASS', saved_file=str(saved), node_id=identity)
            print(f'AGENT EDITOR PASS {index}/{len(names)}: {name}; {len(fields)} fields; save/open preserved ID and schema', flush=True)
        except Exception as exc:
            record['error'] = str(exc)
            print(f'AGENT EDITOR FAIL {name}: {type(exc).__name__}: {str(exc)[:1000]}', flush=True)
            visible.photograph(f'agent-{index:02d}-failed')
            page.keyboard.press('Escape')
            # A fresh page gets a new isolated session after a failed editor
            # action; no application state is injected to rescue the test.
            page.reload()
            expect(page.locator('#agents-list')).to_have_attribute('aria-busy', 'false', timeout=60000)
        results.append(record)
        (out / 'all-agent-editor-results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    search.fill('')
    failures = [row for row in results if row['status'] != 'PASS']
    if failures:
        raise AssertionError(f'{len(failures)} agent editor checks failed: ' + ', '.join(row['agent'] for row in failures))
    case = '24-selected-agent-file-roundtrip' if only else '24-all-89-agents-inspected-and-file-roundtripped'
    checkpoint(case, page, {'agents': len(results), 'selection': only or 'all'})
