# Published Tlamatini deliverables

This directory is intentionally committed to Git. It contains the complete image-conversion work, avatar repair evidence, reproducible test setup, before-change code snapshots, and generated packages.

## Run the real, visible avatar test

From the repository root:

```powershell
.\python\python.exe Tests\run_avatar_tests.py
```

For another project-ready Python, use `python Tests/run_avatar_tests.py`. The launcher checks dependencies, prepares the isolated test database, applies migrations, creates `user / changeme`, runs `collectstatic`, starts Django at `127.0.0.1:8001`, and opens a **visible** browser for 300+ expression transitions and native voice-control checks. `--auto-close` closes the browser/server after a successful run. See [setup and verification](avatar_flash_fix/README.md).

## Everything in this delivery

- [Gemini_girl_animation](Gemini_girl_animation/): four aligned PNGs, four exact quadrant crops, four JPG conversions, a sprite sheet, HTML preview, contact sheet, screenshot, registration metadata, reproduction source, and JPG ZIP.
- [Complete image ZIP](Gemini_girl_animation.zip): the original packaged frame-splitting delivery.
- [avatar_flash_fix](avatar_flash_fix/): test scripts/settings, a sanitized SQLite fixture, screenshots, JSON results, original code snapshots, and deployment-code backups.
- [ASSET_MANIFEST.json](ASSET_MANIFEST.json): file-by-file sizes and SHA-256 hashes for this delivery (the manifest excludes itself to avoid a circular hash).

The latest Python-launcher verification completed **313 expression transitions and 10,609 browser paints** with zero detected coverage/layout failures, zero JavaScript errors, and passing native Windows Zira speech, pause/resume, stop, and mute checks. Earlier test records are retained as historical evidence.

The SQLite fixture contains seeded project data and only the generic ordinary test account, with no active login sessions or private conversation data. Real test sessions and server logs now live separately in ignored `Temp/avatar_flash_fix/`. Before-code backups contain source/template code, not personal configuration files. The frozen application was not rebuilt or replaced.

The application fix and tests are outside this output folder, in the tracked `Tlamatini/agent/static/agent/`, `Tlamatini/agent/templates/agent/`, and `Tests/` trees. See the updated [README](../README.md#avatar-animation-assets-and-visible-tests) and [Book of Tlamatini](../BookOfTlamatini.md#avatar-animation-repair-and-reproducible-visible-tests).
