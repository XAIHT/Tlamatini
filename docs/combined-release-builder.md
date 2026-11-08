# Combined English and Spanish releases

> Latest released version: **[v1.92.4](changes/2026-11-08-v1.92.4.md)**.

## v1.92.4 — Matching builds, explicit release identity and readable Markdown

The combined builder predicts both editions’ actual emitted version before building, pins one matching number, runs Private/Public pairs in parallel with `--self-modify`, and archives verified ZIPs by edition, type and minute. The application log identifies its embedded release type. Dependency setup stays in isolated, application-owned caches and stops safely when no healthy environment exists. Readable Markdown with occasional control characters opens without losing its original bytes; binary content is still refused. See the [1.92.4 release notes](changes/2026-11-08-v1.92.4.md).

Created for Angela López Mendoza · XAIHT

The workstation entry point is `C:\Development\XAIHT\BuildTlamatinis.cmd`;
keep its sibling `BuildTlamatinis.py` beside it. The detailed runbook is
`C:\Development\XAIHT\BuildTlamatinis.md`. These workstation files live
outside both repositories and are not part of installed Tlamatini.

From a visible Command Prompt:

```bat
cd /d C:\Development\XAIHT
BuildTlamatinis.cmd --build_type public --check
BuildTlamatinis.cmd --build_type public
```

Use `private` instead of `public` for a private keyed build. Both modes run the
corresponding complete-release wrapper in each checkout **in parallel**, always
with `--self-modify` and an explicit matching version. Before starting either build,
the launcher calls each checkout’s own `resolve_build_version()` and previews its
actual version emitter in memory. The exact application-reported numbers must
match. `TLAMATINI_VERSION` is honored as it is by the existing builders. No tag
on HEAD is required. The shared result is pinned with `--version` for both.
Use `--Override_versioning X.Y.Z` to force one common version; the bare flag uses
English’s detected number for both. `--check` previews without building.
No commit, tag, push or GitHub release is created. Working-tree edits are included.

Each successful new ZIP is CRC-checked, SHA-256 hashed and moved to
`C:\Development\XAIHT\Tlamatinis-Releases\<edition>\Public-or-Private\YYYY-MM-DD_HH-mm\`.
`<edition>` is `Tlamatini` or `Tlamatini-Spanish`; repeated runs within a minute
receive a numbered suffix. Logs/receipts live under `.runs\<date>\` in the release
root, separate from the ZIPs. Each edition has an independent build cache outside
user profiles. One failed edition does not discard the other edition's successful
ZIP; the overall result is nonzero unless both succeed. Old/failed ZIPs are not moved.

The original builders retain their prerequisites, privacy checks and side effects,
including development database and build-output recreation. Save development work
before running a real build. Private ZIPs contain private/keyed data and must not
be uploaded as public releases. Keep the build consoles open during cleanup.

## First lines of the application log

Complete-release wrappers now pass `--release-type private` or
`--release-type public` to `build.py`. The selected value is embedded in the
already-carried `agent._version` module, independently of the combo launcher.
The real console/log tee starts each `tlamatini.log` with:

```text
--- [VERSION] Tlamatini <version>
--- [RELEASE] Tlamatini | PRIVATE
```

Public builds print `PUBLIC`. Source runs print `DEVELOPMENT`; older binaries
and standalone builds with no explicit release type print `UNSPECIFIED`.
Runtime environment variables, installed directory names and the presence of
credentials never determine the label. The type is also returned by
`get_version_info()` as `release_type`. It describes build provenance, not an
independent assertion that a package passed a personal-data audit.

Rebuild and install to activate the new banner in a frozen application. Existing
installations are untouched by editing this source. The existing frozen-version
carrier and generic source snapshot include this change without new dependencies,
registry state or preservation rules.

## Validation — 2026-11-07

Visible launcher fixture tests cover real parallel worker processes, both build
modes, matching/missing/malformed/mismatched reachable tags, argument forwarding, failed and
stale/corrupt ZIPs, collisions, locks and generated PowerShell syntax. Both editions
pass `Tests/test_release_version_pinning.py` (6 tests) and
`Tests/test_release_type_banner.py` (5 tests, including the actual log tee).
Python lint and both source inclusion sweeps pass. No real release, installation,
database rebuild, project commit or project tag operation was performed.

### Final version-preview verification — 2026-11-07

The recreated launcher passed 21 visible regression tests and Python lint. Actual
CMD previews for both private and public builds resolve English and Spanish to
**1.92.3**, with no tag required on HEAD. Tests cover both real version emitters,
ancestor tags, environment precedence, overrides, metadata, read-only prediction,
parallel fixture workers, partial failures, stale/corrupt ZIPs and output placement.
Evidence: `C:\Development\XAIHT\Tlachihuani\artifacts\verification\combined-builder-final-20261107\console.log`.
No full frozen release builds were run in this verification.

### Dependency setup recovery — 2026-11-08

A failed package-index/DNS request must not send a release through the machine
Python’s legacy NumPy purge or `pip --user` path. `build_env.py` now stops before
those operations when no healthy isolated environment is available. Existing
healthy isolated caches remain reusable. Standalone builds default to the
application-owned `Temp/build-env`; the combined builder supplies separate
`.build-cache/<edition>/python-envs` locations under the release root. Neither
default writes a new cache under a Windows user profile.

### Complete private and public builds — 2026-11-08

All four real builds passed: English and Spanish private, then English and Spanish
public, with each pair built concurrently in verified visible consoles. All four
executables extracted from the final ZIPs report **1.92.3** and their correct
Private/Public type. The final ZIPs and SHA-256 sidecars are under
`C:\Development\XAIHT\Tlamatinis-Releases\<edition>\Private\2026-11-08_00-25`
and `...\<edition>\Public\2026-11-08_00-56`.

Payload integrity, public-data audits, frozen runtime gates, 26 build-isolation
tests and focused lint passed. Full evidence and archive names:
`C:\Development\XAIHT\Tlachihuani\artifacts\verification\complete-builds-20261107\VALIDATION.md`.
This verifies real builds and packaged executables; it is not a clean-install or
live model/chat acceptance run. Nothing was committed, tagged or pushed.
