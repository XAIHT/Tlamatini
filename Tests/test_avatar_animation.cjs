/* Browser regression: run with node tests/test_avatar_animation.cjs.
 * Requires Playwright (or PLAYWRIGHT_MODULE pointing at its installed package).
 * No login, application requests, voice output, or user data are needed.
 * --before exercises the saved pre-fix assets to demonstrate the regression.
 * AVATAR_LIVE_URL optionally fetches CSS/JS/JPGs from the installed server.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const root = path.resolve(__dirname, '..');
const source = path.join(root, 'Tlamatini/agent');
const before = process.argv.includes('--before');
const live = process.env.AVATAR_LIVE_URL;
const reportDir = path.join(root, 'output/avatar_flash_fix', before ? 'before-test' : live ? 'installed-test' : 'after-test');
fs.mkdirSync(reportDir, { recursive: true });
const template = fs.readFileSync(path.join(source, 'templates/agent/agent_page.html'), 'utf8');
const dock = template.match(/<div id="tlm-avatar-dock"[^\n]+/)[0]
  .replace(/{% static '([^']+)' %}/g, '/static/$1')
  .replace(/{{ STATIC_VERSION }}/g, 'avatar-test');
const fixture = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/agent/css/avatar.css">
<style>body{margin:0;background:#343541}#tools-chat-form-container{height:360px;width:720px}
#chat-form{height:350px}#tlm-avatar-dock{width:264px;bottom:20px;right:20px}
#chat-message-input,#chat-message-submit{display:none}</style></head><body>
<div id="tools-chat-form-container"><form id="chat-form"><textarea id="chat-message-input"></textarea>
<button id="chat-message-submit">Send</button>${dock}</form></div>
<div id="tlm-avatar-bubble"></div><script src="/static/agent/js/avatar.js"></script></body></html>`;
const allowed = /^agent\/(css\/avatar\.css|js\/avatar\.js|img\/avatar\/(eo_mc|ec_mc|eo_mo|ec_mo)\.jpg)$/;
const server = http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    if (url.pathname === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(fixture); return;
    }
    const rel = url.pathname.replace(/^\/static\//, '');
    if (!allowed.test(rel)) { res.writeHead(404); res.end(); return; }
    let data;
    if (live) {
      const response = await fetch(`${live}/static/${rel}?avatar-regression=${Date.now()}`);
      assert.equal(response.status, 200, rel);
      data = Buffer.from(await response.arrayBuffer());
      assert.deepEqual(data, fs.readFileSync(path.join(source, 'static', rel)), `Live bytes differ: ${rel}`);
    } else {
      const file = before && /\.(css|js)$/.test(rel)
        ? path.join(root, 'output/avatar_flash_fix/before', path.basename(rel))
        : path.join(source, 'static', rel);
      data = fs.readFileSync(file);
    }
    res.writeHead(200, { 'Content-Type': rel.endsWith('.css') ? 'text/css' : rel.endsWith('.js') ? 'text/javascript' : 'image/jpeg' });
    res.end(data);
  } catch (error) { res.writeHead(500); res.end(String(error)); }
});

async function createPage(browser, options = {}) {
  const page = await browser.newPage({ viewport: { width: 740, height: 380 }, reducedMotion: options.reduced ? 'reduce' : 'no-preference' });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    Math.random = () => 0.5; // predictable blink at 4700 ms; no double blink
    window.testSpeech = { speaking: false, pending: false, paused: false, getVoices: () => [],
      speak() {}, cancel() { this.speaking = false; }, resume() {} };
    Object.defineProperty(window, 'speechSynthesis', { value: window.testSpeech, configurable: true });
    // Hold a single image's decode() promise to test the actual readiness gate.
    const decode = HTMLImageElement.prototype.decode;
    HTMLImageElement.prototype.decode = function () {
      const image = this;
      return decode.call(image).then(() => {
        if (window.testHoldDecode && image.id === 'tlm-s-eo-mo') {
          return new Promise(resolve => { window.testReleaseDecode = resolve; });
        }
      });
    };
  });
  if (options.holdDecode) await page.addInitScript(() => { window.testHoldDecode = true; });
  if (options.missing) await page.route('**/img/avatar/eo_mo.jpg*', route => route.fulfill({ status: 404, body: '' }));
  if (options.slow) await page.route('**/img/avatar/*.jpg*', async route => {
    if (!route.request().url().includes('/eo_mc.jpg')) await new Promise(resolve => setTimeout(resolve, 1200));
    await route.continue();
  });
  await page.goto(`http://127.0.0.1:${server.address().port}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => {
    const image = document.getElementById('tlm-s-eo-mc');
    return image.complete && image.naturalWidth === 1024 && window.TLM_VOICE;
  });
  await page.evaluate(() => {
    window.testSamples = [];
    function sample() {
      const images = [...document.querySelectorAll('#tlm-face img')];
      const states = images.map(image => {
        const style = getComputedStyle(image);
        return { id: image.id, opacity: Number(style.opacity), visible: style.visibility !== 'hidden' && style.display !== 'none',
          loaded: image.complete && image.naturalWidth > 0, active: image.classList.contains('tlm-on') };
      });
      const coverage = 1 - states.reduce((transparent, s) => transparent * (1 - (s.visible && s.loaded ? s.opacity : 0)), 1);
      const r = document.getElementById('tlm-face').getBoundingClientRect();
      window.testSamples.push({ coverage, states, box: [r.x, r.y, r.width, r.height] });
      window.testRaf = requestAnimationFrame(sample);
    }
    requestAnimationFrame(sample);
  });
  return { page, errors };
}

async function summary(page) {
  return page.evaluate(() => ({
    paints: testSamples.length,
    minCoverage: Math.min(...testSamples.map(s => s.coverage)),
    partialOpacityPaints: testSamples.filter(s => s.states.some(i => i.opacity > 0 && i.opacity < 1)).length,
    activeStates: [...new Set(testSamples.flatMap(s => s.states.filter(i => i.active).map(i => i.id)))],
    distinctBoxes: new Set(testSamples.map(s => JSON.stringify(s.box))).size
  }));
}

async function main() {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ headless: true });
  const results = {};
  try {
    const { page, errors } = await createPage(browser);
    await page.waitForFunction(() => [...document.querySelectorAll('#tlm-face img')].every(i => i.complete && i.naturalWidth === 1024));
    await page.screenshot({ path: path.join(reportDir, 'idle.png') });
    await page.evaluate(() => { window.testSpeech.speaking = true; });
    // Real browser paints through two natural blinks and repeated speech ticks.
    await page.waitForTimeout(before ? 1300 : 10100);
    results.speechAndBlink = await summary(page);
    if (before) {
      assert(results.speechAndBlink.minCoverage < 0.85, 'Expected the old opacity-compositing regression');
      // Freeze an observed intermediate paint, preserving the measured opacity.
      await page.waitForFunction(() => [...document.querySelectorAll('#tlm-face img')].some(i => {
        const opacity = Number(getComputedStyle(i).opacity); return opacity > 0.35 && opacity < 0.65;
      }));
      await page.evaluate(() => {
        const images = [...document.querySelectorAll('#tlm-face img')];
        const opacities = images.map(i => getComputedStyle(i).opacity);
        images.forEach((i, index) => { i.style.transition = 'none'; i.style.opacity = opacities[index]; });
      });
      await page.screenshot({ path: path.join(reportDir, 'observed-flash.png') });
    } else {
      assert.equal(results.speechAndBlink.minCoverage, 1, 'Background exposed during animation');
      assert.equal(results.speechAndBlink.partialOpacityPaints, 0, 'Cross-fade returned');
      assert.equal(results.speechAndBlink.activeStates.length, 4, 'Did not exercise every expression');
      assert.equal(results.speechAndBlink.distinctBoxes, 1, 'Avatar position/size changed');
      await page.screenshot({ path: path.join(reportDir, 'speaking.png') });
      await page.keyboard.press('Escape');
      await page.waitForTimeout(220);
      assert.equal(await page.locator('#tlm-s-eo-mc').getAttribute('class'), 'tlm-on');
      results.stop = 'PASS';
      // Snapshot all real expression states, with browser-drawn JPEGs.
      for (const id of ['eo-mc', 'ec-mc', 'eo-mo', 'ec-mo']) {
        await page.evaluate(id => {
          testSpeech.speaking = false;
          document.querySelectorAll('#tlm-face img').forEach(i => i.classList.toggle('tlm-on', i.id === 'tlm-s-' + id));
        }, id);
        await page.locator('#tlm-face').screenshot({ path: path.join(reportDir, id + '.png') });
      }
      await page.setViewportSize({ width: 390, height: 620 });
      await page.evaluate(() => { document.getElementById('tools-chat-form-container').style.width = '390px'; });
      await page.screenshot({ path: path.join(reportDir, 'narrow.png') });
    }
    assert.deepEqual(errors, []);
    await page.close();

    if (!before) {
      for (const name of ['slow', 'missing', 'holdDecode', 'reduced']) {
        const test = await createPage(browser, { [name]: true });
        await test.page.evaluate(() => { testSpeech.speaking = true; });
        await test.page.waitForTimeout(name === 'reduced' ? 5100 : 900);
        results[name] = await summary(test.page);
        assert.equal(results[name].minCoverage, 1, `${name}: blank/partly transparent frame`);
        assert.equal(results[name].partialOpacityPaints, 0);
        if (name === 'missing' || name === 'holdDecode' || name === 'reduced') {
          assert.deepEqual(results[name].activeStates, ['tlm-s-eo-mc'], `${name}: selected an unavailable/disabled frame`);
        }
        if (name === 'holdDecode') {
          await test.page.evaluate(() => testReleaseDecode());
          await test.page.waitForTimeout(350);
          assert((await summary(test.page)).activeStates.includes('tlm-s-eo-mo'));
        }
        if (name === 'slow') {
          await test.page.waitForTimeout(750);
          assert((await summary(test.page)).activeStates.includes('tlm-s-eo-mo'));
        }
        assert.deepEqual(test.errors, []);
        await test.page.close();
      }
    }
    fs.writeFileSync(path.join(reportDir, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
    console.log(before ? 'CONFIRMED: old CSS exposes the background between expression frames.' : 'PASS: no transparent paints, missing frames, decode races, or layout movement.');
  } finally { await browser.close(); server.closeAllConnections(); server.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; server.closeAllConnections(); server.close(); });
