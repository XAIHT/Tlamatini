# Avatar flashing fix — verification and handoff

## Run it yourself from a clone

```powershell
.\python\python.exe Tests\run_avatar_tests.py
```

Use `python Tests/run_avatar_tests.py` with another project-ready Python. `--check` validates dependencies; `--prepare-only` runs database setup and collectstatic; `--auto-close` runs the full visible test then closes its browser/server. The launcher detects existing Node.js/Playwright/Chromium and never silently downloads dependencies. Read the [main README](../../README.md#avatar-animation-assets-and-visible-tests) and [Book walkthrough](../../BookOfTlamatini.md#avatar-animation-repair-and-reproducible-visible-tests) for setup and scope.

All deliverables in this folder are published. The included `development-test.sqlite3` is a session-free fixture with seeded project data and only the generic test user. New test runs use a separate live database and logs in ignored `Temp/avatar_flash_fix/`. Original local test sessions were backed up privately there, then removed from the published fixture; no production database was used.

## Outcome

The source fix passed the final **visible, non-headless Chromium run against the real Django login and chat page**: **311 expression transitions, 10,813 sampled browser paints, zero transparency/coverage failures, zero layout jumps within each viewport, and zero JavaScript errors**. All four expression states were exercised at 1440 × 900, 1100 × 780, and 1600 × 1000 viewports.

Native **Microsoft Zira — English (United States)** speech was used. Pause/resume, Escape-to-stop, click-to-greet/stop, double-click mute, keyboard unmute, and avoiding selection highlights passed. An earlier visible run covered another 312 transitions; screenshot inspection exposed a blue double-click selection highlight, which was fixed before the final run.

## Cause and changes

- `Tlamatini/agent/static/agent/css/avatar.css`: the old 90 ms opacity cross-fade made both full portraits partially transparent. Two 50% opaque layers cover only 75% of their dark background, producing the flash. The old browser regression measured minimum coverage of 0.753. Frames now change visibility immediately at full opacity, with the neutral portrait underneath as a fallback. The clickable avatar also disables selection so double-clicking cannot tint it blue.
- `Tlamatini/agent/static/agent/js/avatar.js`: each image must finish `decode()` before selection. A slow, broken, or undecoded frame cannot replace the last valid portrait. Paused speech, hidden tabs, and reduced-motion mode no longer keep alternating the mouth.
- `Tlamatini/agent/templates/agent/agent_page.html`: avatar CSS and JS URLs have a new matching cache-busting suffix. The existing startup-generated `STATIC_VERSION` behavior is preserved.

## Images and collectstatic

The four original source JPGs were **not edited**. All remain 1024 × 1024 RGB. SHA-256 checks matched the source, development `staticfiles`, installed application static tree, installed collected tree, installed source copy, and initially served frozen HTTP responses.

An isolated real Django 5.2.15 collector first verified exact byte copies. The full project `collectstatic` was then run after migrations: two changed static files copied initially; the final selection fix copied one more CSS file. The final development browser received all six avatar assets with bytes identical to source. `collectstatic` did not resize, recompress, or convert the JPGs.

## Test environment

- Development URL: http://127.0.0.1:8001/agent/agent/
- Local test account: `user` / `changeme` (ordinary user, not superuser).
- Initial test database / published sanitized fixture: `output/avatar_flash_fix/development-test.sqlite3`. New runs use `Temp/avatar_flash_fix/development-test.sqlite3`.
- All project migrations completed successfully.
- Existing databases and the frozen installation at `C:/Tlamatini` were left unchanged.
- These are avatar/voice/frontend tests. Django authentication, templates, middleware, static delivery, and native speech are real. The browser test isolates the LLM WebSocket so it does not launch model jobs or modify the running frozen session; LLM-response behavior is not claimed as tested.
- Earlier focused browser tests also passed slow downloads, failed-image responses, delayed decoding, reduced motion, and normal blinking/talking. The final requested runs were visible, not headless.

## Evidence

- Final visible run: `visible-test/results.json`
- Final screenshot: `visible-test/final-passed.png`
- Size/checkpoint screenshots: `visible-test/checkpoint-*.png`
- Original fade reproduction: `before-test/results.json` and `before-test/observed-flash.png`
- Earlier loading/decode regression tests: `after-test/results.json`
- Backups before edits: `before/` and `deployment-backups/`

## Reproduce

From the repository root, with the existing prepared test database:

```powershell
.\python\python.exe output\avatar_flash_fix\development_test.py collect
.\python\python.exe output\avatar_flash_fix\development_test.py serve
```

Then run `node Tests/test_avatar_visible.cjs` with Playwright available. `PLAYWRIGHT_MODULE` can point to an installed Playwright package. The test always launches visibly and leaves its browser open after completion. Close that browser when finished.

The source parses and passes ESLint's error checks; the repository's parse check passed all 38 targeted JavaScript files. No build, reinstall, or frozen-server restart was performed during the repair. Publication now includes the source changes, all evidence, asset packages, and the runnable Python launcher. Rebuild/reinstall normally when ready, then reload the frozen app to pick up the changed assets and templates.
