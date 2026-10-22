<!-- Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1 -->
# Release version pinning — 2026-10-22

## Failure and evidence

Angela reported a public release ending with `build_installer.py failed.` after
configuration restoration. Those final `WROTE` lines were the public builder's
restoration/re-keying step, not the cause of failure.

Read-only inspection of the existing artifacts established this sequence
(local time, UTC-06:00):

| Event | Time | Version |
|---|---|---|
| Application's generated version module | 02:10:02 | 1.89.0 |
| Annotated v1.90.0 tag created | 02:11:24 | 1.90.0 |
| Application pkg.zip completed | 02:27:29 | Receipt says 1.89.0 |
| Uninstaller.exe completed | 02:32:40 | ProductVersion 1.90.0 |
| Installer VERSIONINFO generated | 02:32:41 | 1.90.0 |

The installer's existing package verification correctly refused the mismatch.
Running `verify_package(Path("pkg.zip"), expected_version="1.90.0")` reproduced it.
The complete release wrappers had let each child resolve Git independently.
A child setting `os.environ["TLAMATINI_VERSION"]` cannot update its parent or
siblings. Explicit wrapper versions were also forwarded as bare positional
arguments, which the children's `extract_cli_version()` does not recognize.

## Change

Both complete release wrappers now resolve the version once, before preparation,
and pass `--version <resolved>` to the application, uninstaller and installer
builds. CLI overrides retain precedence over the caller's environment and Git;
the startup banner shows the pinned value. The sealed build Python keeps those
arguments when it re-executes a stage.

The package mismatch check remains mandatory and now names the actual and
requested versions. Public configuration restoration and private-data handling
are unchanged. No package receipt, generated runtime version, tag or installed
application was rewritten to conceal the mismatch.

## Verification

All commands ran in the verified visible console
**Tlamatini Build Fix - visible commands**. No real build was launched.

- Before the fix, the five new wrapper tests reported 14 failed subcases. They
  reproduced the 1.89.0 / 1.90.0 split and the ignored explicit override.
- After the fix, **90 tests passed** across release version pinning, regeneration,
  setup path recovery, runtime package integrity, sealed build environment and
  release payload ownership. Fixture-only wrapper tests cover default/explicit
  versions, environment precedence, tag changes, both self-modify flag choices
  and public configuration restoration at each failing build stage.
- The final 18 wrapper/sealed-environment checks also passed after adding explicit
  coverage of the version argument across the sealed-Python re-execution.
- The package integrity regression rejects an old version while preserving the
  package's exact bytes. Ruff and `git diff --check` passed.
- Local transcripts and the visible-console image are saved under
  `Temp/build-fix-2026-10-22/` (ignored development evidence).

At diagnosis, the existing pkg.zip contained **1.89.0**. During verification, a
separate public build started at **03:23:55**; its generated application version
was **1.90.0** at 03:23:58. It removed the earlier root pkg.zip as part of building.
The final read-only package probe therefore found a missing file, not a second
version-mismatch result. Its generic exit-code footer is not evidence of a
successful mismatch check; the original reproduction and fixture regression are.
No concurrent build was started, stopped or certified by this fix task.
These regression tests do not certify a newly compiled installer or an installed
release. See [VERSIONING.md](../../VERSIONING.md)
for the corrected build instructions. The separate
[documentation regeneration](2026-10-22-documentation-refresh.md) was completed
before this build incident was investigated.
