# Tlamatini Author Banner — Angela López Mendoza
"""Behavior checks run only in the verified, headed ui_sweep_visible session."""
import json


def check_splitters(page, window, base, capture):
    results = []
    for name, path, selectors in [
        ('chat', '/agent/agent/', ['#drag-divider', '#vertical-drag-divider']),
        ('agents', '/agent/agentic_control_panel/', ['#drag-divider']),
        ('prompts', '/agent/prompt_flow_panel/', ['#drag-divider', '#pmt-output-divider']),
    ]:
        page.goto(base + path, wait_until='load')
        page.wait_for_timeout(500)
        window.verify()
        for selector in selectors:
            bar = page.locator(selector)
            vertical = bar.get_attribute('aria-orientation') == 'vertical'
            key = 'ArrowRight' if vertical else 'ArrowDown'
            reverse = 'ArrowLeft' if vertical else 'ArrowUp'
            def number():
                return float(bar.get_attribute('aria-valuenow'))
            home = 'End' if selector == '#vertical-drag-divider' else 'Home'
            end = 'Home' if home == 'End' else 'End'
            bar.press(home)
            low = number()
            assert abs(low - float(bar.get_attribute('aria-valuemin'))) <= 1, (name, selector, home, low)
            # Composer describes the upper pane, so its Home has the inverse meaning.
            bar.press(end)
            high = number()
            assert abs(high - float(bar.get_attribute('aria-valuemax'))) <= 1, (name, selector, end, high)
            bar.press(home)
            before = number()
            bar.press(key)
            one = number()
            if abs(one-before) < .2:
                key, reverse = reverse, key
                bar.press(key)
                one = number()
            assert abs(one-before) > .5, (name, selector, 'arrows')
            bar.press('Shift+'+key)
            five = number()
            assert abs(five-one) > 3.5, (name, selector, 'Shift')
            # Move to the center of the valid range using real pointer input.
            box = bar.bounding_box()
            x, y = box['x']+box['width']/2, box['y']+box['height']/2
            page.mouse.move(x,y)
            page.mouse.down()
            assert bar.get_attribute('data-resizing') is not None
            page.mouse.move(x + (70 if vertical else 0), y + (0 if vertical else -70), steps=8)
            page.keyboard.press('Escape')
            assert bar.get_attribute('data-resizing') is None, (name, selector, 'Escape')
            page.mouse.up()
            for event in ['blur', 'pointercancel', 'lostpointercapture']:
                box = bar.bounding_box()
                page.mouse.move(box['x']+box['width']/2, box['y']+box['height']/2)
                page.mouse.down()
                if event == 'blur':
                    page.evaluate("window.dispatchEvent(new Event('blur'))")
                else:
                    bar.evaluate('(e,type)=>e.dispatchEvent(new PointerEvent(type,{pointerId:1}))', event)
                assert bar.get_attribute('data-resizing') is None, (name, selector, event)
                page.mouse.up()
            assert not page.evaluate("document.body.matches('.resizing,.resizing-vertical')")
            result = {'page':name,'bar':selector,'min':low,'max':high,'arrow':abs(one-before),'shift':abs(five-one)}
            results.append(result)
            print('RESIZE PASS', json.dumps(result), flush=True)
        capture('resizing-'+name+'.png')
    return results
