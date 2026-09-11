/* Visible real-Django avatar regression. Never launches headless.
 * Start output/avatar_flash_fix/development_test.py serve after prepare.
 * PLAYWRIGHT_MODULE may name a bundled Playwright package.
 * The real login, Django templates, middleware, static files and native OS
 * speech synthesis are used. Only the LLM websocket is isolated: no prompts,
 * model jobs or mutations to the user's frozen application are performed.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const out = path.join(root, 'output/avatar_flash_fix/visible-test');
fs.mkdirSync(out, { recursive: true });
const origin = 'http://127.0.0.1:8001';

async function main() {
  const browser = await chromium.launch({ headless: false, args: ['--window-position=30,30', '--window-size=1500,1020'] });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' });
  // Stay inside the app's UI test boundary; don't launch RAG/model workers.
  await context.routeWebSocket('**/ws/agent/', socket => {
    socket.onMessage(() => {});
    setTimeout(() => socket.send(JSON.stringify({ username: 'Tlamatini', message: 'Your agent is ready. You can now start chatting with Tlamatini.' })), 200);
  });
  const page = await context.newPage();
  const errors = [], assetChecks = [], pendingAssets = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    const match = new URL(response.url()).pathname.match(/^\/static\/(agent\/(?:css\/avatar\.css|js\/avatar\.js|img\/avatar\/\w+\.jpg))$/);
    if (!match) return;
    pendingAssets.push((async () => {
      const data = await response.body();
      const expected = fs.readFileSync(path.join(root, 'Tlamatini/agent/static', match[1]));
      assert.equal(response.status(), 200);
      assert.deepEqual(data, expected, match[1] + ': browser did not get source bytes');
      assetChecks.push({ path: match[1], status: response.status(), bytes: data.length, sha256: crypto.createHash('sha256').update(data).digest('hex') });
    })());
  });
  try {
    await page.goto(origin, { waitUntil: 'domcontentloaded' });
    await page.locator('#id_username').fill('user');
    await page.locator('#id_password').fill('changeme');
    await page.getByRole('button', { name: 'Login', exact: true }).click();
    await page.waitForURL('**/welcome/');
    await page.goto(origin + '/agent/agent/', { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.TLM_VOICE && [...document.querySelectorAll('#tlm-face img')].length === 4 && [...document.querySelectorAll('#tlm-face img')].every(i => i.complete && i.naturalWidth === 1024));
    await page.waitForFunction(() => window.speechSynthesis.getVoices().length > 0, { timeout: 15000 });
    await page.evaluate(() => {
      const panel = document.createElement('section');
      panel.id = 'avatar-visible-test-panel';
      panel.style.cssText = 'position:fixed;left:14px;top:76px;width:365px;z-index:1000000;background:#122922;color:#e7fff6;border:2px solid #55bbaa;border-radius:10px;padding:16px;font:15px system-ui;box-shadow:0 4px 20px #0008';
      panel.innerHTML = '<strong>VISIBLE AVATAR REGRESSION · DJANGO</strong><p>Real page · native speech · 300 transitions</p><p id="avatar-test-status">Ready. Original JPGs preserved.</p><button id="avatar-test-start" style="padding:10px 14px">Start visible voice test</button>';
      document.body.appendChild(panel);
      window.avatarTest = { transitions: [], paints: 0, minCoverage: 1, failures: [], states: [], phase: 'native speech', lastKey: '', resizeAt: performance.now(), rectangles: {} };
      window.addEventListener('resize', () => { avatarTest.resizeAt = performance.now(); });
      function inspect() {
        const test = avatarTest;
        if (test.finished) return;
        const images = [...document.querySelectorAll('#tlm-face img')];
        const active = images.filter(i => i.classList.contains('tlm-on'));
        const key = active.map(i => i.id).join(',');
        const coverage = 1 - images.reduce((remaining, image) => {
          const s = getComputedStyle(image);
          const alpha = s.visibility !== 'hidden' && s.display !== 'none' && image.complete && image.naturalWidth > 0 ? Number(s.opacity) : 0;
          if (Number(s.opacity) !== 1) test.failures.push('Partly transparent image: ' + image.id);
          return remaining * (1 - alpha);
        }, 1);
        test.paints++;
        test.minCoverage = Math.min(test.minCoverage, coverage);
        if (coverage !== 1 || active.length !== 1) test.failures.push({ coverage, active: key });
        const r = document.getElementById('tlm-face').getBoundingClientRect();
        const rect = [r.x, r.y, r.width, r.height].map(v => Math.round(v * 100) / 100).join(',');
        const viewport = window.innerWidth + 'x' + window.innerHeight;
        if (performance.now() - test.resizeAt > 500) {
          if (test.rectangles[viewport] && test.rectangles[viewport] !== rect) test.failures.push('Layout moved at ' + viewport);
          test.rectangles[viewport] = rect;
        }
        if (key !== test.lastKey) {
          test.transitions.push({ index: test.transitions.length + 1, frame: key, phase: test.phase, coverage, viewport });
          if (!test.states.includes(key)) test.states.push(key);
          test.lastKey = key;
          const status = document.getElementById('avatar-test-status');
          if (status) status.textContent = test.transitions.length + ' transitions checked · ' + test.failures.length + ' failures · ' + test.paints + ' paints';
        }
        requestAnimationFrame(inspect);
      }
      requestAnimationFrame(inspect);
      document.getElementById('avatar-test-start').onclick = () => {
        const settings = TLM_VOICE.loadSettings();
        const voices = speechSynthesis.getVoices();
        const voice = voices.find(v => v.localService && /zira|hazel|female/i.test(v.name)) || voices.find(v => v.localService && /^en/i.test(v.lang));
        settings.mode = 'notify'; settings.volume = 20; settings.rate = 1.1;
        if (voice) settings.voiceURI = voice.voiceURI;
        TLM_VOICE.saveSettings(settings);
        avatarTest.voice = voice ? { name: voice.name, localService: voice.localService } : null;
        TLM_VOICE.prime();
        TLM_VOICE.speak(('This is the Tlamatini avatar test. Her eyes blink while she speaks, and her portrait stays steady. The original images are unchanged. ').repeat(60));
      };
    });
    await page.screenshot({ path: path.join(out, '01-real-django-page.png') });
    await page.locator('#avatar-test-start').click();
    await page.waitForFunction(() => speechSynthesis.speaking, { timeout: 15000 });
    console.log('Visible browser open. Authenticated real Django page. Native voice started.');
    for (let checkpoint = 50; checkpoint <= 300; checkpoint += 50) {
      await page.waitForFunction(n => avatarTest.transitions.length >= n, checkpoint, { timeout: 45000 });
      const stats = await page.evaluate(() => ({ transitions: avatarTest.transitions.length, paints: avatarTest.paints, minCoverage: avatarTest.minCoverage, failures: avatarTest.failures.length }));
      assert.equal(stats.failures, 0, JSON.stringify(stats));
      assert.equal(stats.minCoverage, 1);
      await page.screenshot({ path: path.join(out, `checkpoint-${checkpoint}.png`) });
      console.log('VISIBLE CHECKPOINT', JSON.stringify(stats));
      if (checkpoint === 100) await page.setViewportSize({ width: 1100, height: 780 });
      if (checkpoint === 200) await page.setViewportSize({ width: 1600, height: 1000 });
    }
    await page.evaluate(() => { avatarTest.phase = 'pause/resume'; speechSynthesis.pause(); });
    await page.waitForTimeout(400);
    assert.equal(await page.evaluate(() => [...document.querySelectorAll('#tlm-face img.tlm-on')].every(i => i.id.endsWith('-mc'))), true);
    await page.evaluate(() => speechSynthesis.resume());
    await page.waitForTimeout(500);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    assert.equal(await page.evaluate(() => speechSynthesis.speaking || speechSynthesis.pending), false);
    assert.equal(await page.evaluate(() => [...document.querySelectorAll('#tlm-face img.tlm-on')].every(i => i.id.endsWith('-mc'))), true);
    await page.evaluate(() => { avatarTest.phase = 'click greet/stop'; });
    await page.locator('#tlm-avatar-dock').click();
    await page.waitForFunction(() => speechSynthesis.speaking);
    await page.waitForTimeout(800);
    await page.locator('#tlm-avatar-dock').click();
    await page.waitForTimeout(400);
    assert.equal(await page.evaluate(() => speechSynthesis.speaking || speechSynthesis.pending), false);
    await page.locator('#tlm-avatar-dock').dblclick();
    assert.equal(await page.evaluate(() => TLM_VOICE.loadSettings().mode), 'silent');
    assert.equal(await page.evaluate(() => window.getSelection().containsNode(document.getElementById('tlm-face'), true)), false, 'Double-click selected/highlighted the portrait');
    await page.keyboard.press('Control+Shift+M');
    assert.equal(await page.evaluate(() => TLM_VOICE.loadSettings().mode), 'notify');
    await Promise.all(pendingAssets);
    assert.equal(assetChecks.length, 6);
    const result = await page.evaluate(() => { avatarTest.finished = true; return avatarTest; });
    assert.equal(result.failures.length, 0);
    assert.equal(result.states.length, 4);
    result.headless = false;
    result.url = page.url();
    result.controls = { pauseResume: 'PASS', escape: 'PASS', clickGreetStop: 'PASS', doubleClickMute: 'PASS', noSelectionHighlight: 'PASS', keyboardUnmute: 'PASS' };
    result.assetChecks = assetChecks;
    result.pageErrors = errors;
    // Whole-application errors are reported separately from avatar assertions.
    fs.writeFileSync(path.join(out, 'results.json'), JSON.stringify(result, null, 2));
    await page.evaluate(() => {
      TLM_VOICE.stop();
      document.getElementById('avatar-test-status').textContent = 'PASS — ' + avatarTest.transitions.length + ' transitions; ' + avatarTest.paints + ' browser paints; zero flashes.';
      document.getElementById('avatar-test-start').textContent = 'Replay voice test';
    });
    await page.screenshot({ path: path.join(out, 'final-passed.png') });
    console.log('VISIBLE_TESTS_COMPLETE', JSON.stringify({ transitions: result.transitions.length, paints: result.paints, minCoverage: result.minCoverage, failures: result.failures.length, states: result.states, controls: result.controls, voice: result.voice, pageErrors: errors }));
    if (process.env.AVATAR_TEST_AUTOCLOSE === '1') { await browser.close(); return; }
    console.log('Browser remains open on the test result; close its window when finished.');
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', command => { if (command.trim() === 'close') browser.close(); });
    await new Promise(resolve => browser.on('disconnected', resolve));
    process.stdin.pause();
  } catch (error) {
    console.error(error);
    await page.screenshot({ path: path.join(out, 'failure.png') }).catch(() => {});
    fs.writeFileSync(path.join(out, 'failure.txt'), String(error) + '\nPage errors: ' + JSON.stringify(errors));
    await browser.close();
    process.exitCode = 1;
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
