# Build migration dependency repair · 13 November 2026

Version remains **1.93.5**. The combined private build correctly predicted that
number for both editions. English completed; Spanish failed at frozen `migrate`
because `0224_remote_controller` referenced the English-only parent
`0223_create_superuser_console_handoff`.

Spanish now references its real predecessor, `0227_create_superuser_console_handoff`.
English retains its existing dependency. Migration identities are unchanged;
there is no fake migration, renumbering, history rewrite or backup/restore change.

## Early detection

Both editions' private/public wrappers and direct build entry points use
`build_runtime_assets.validate_migration_dependencies`. It reads Python syntax
without importing the application or connecting to a database and reports missing
literal local parents before mutable build steps. Dynamic/external dependencies
remain Django's responsibility. The combined launcher checks both editions before
launching either build; a version override does not bypass a missing migration.
It also prints an edition's failure details immediately instead of waiting for
the other edition to finish.

## Verification

Run `Tests/test_build_migrations.py`, `Tests/test_migration_graph.py` and
`Tests/test_release_version_pinning.py` separately with the prepared Python/Django
environment in a verified visible foreground console. Run `BuildTlamatinis.Tests.py`
with system Python 3.12 from the parent workspace. Scratch stays in application-owned
folders, never the Windows user profile.

The Django suite loads the actual graph and applies the real migrations to fresh
isolated SQLite databases. It tests fresh installation schema, upgrade from the
preceding migration, the profile/revocation models and reverse/reapply while
retaining an existing test account and user-edited prompt. It does not invoke
production startup hooks or use either working database.

The builder suite uses explicit fixture ZIPs for concurrency, failure and archive
checks; those are not compiled applications. Runtime packaging and source-snapshot
inclusion are checked separately. No full executable rebuild, installation,
Git tag, commit or push is part of this repair's verification.

### Observed results

- 67 regression tests passed across both editions and the combined launcher:
  26 migration-source checks, 6 real Django migration tests, 12 version-pinning
  checks and 23 combined-launcher tests.
- Django loaded 242 nodes in English and 246 in Spanish. Both graphs have the
  expected Remote-Controller leaf and no conflicting agent branches.
- The real private and public `BuildTlamatinis.cmd --check` invocations both
  report **1.93.5** for each edition and validate 224/228 local migration files.
- Python lint passed for every changed Python file. Source-snapshot generation
  and self-update inclusion sweeps passed for both editions with no findings.
  Their media-gallery omission and regenerated static/build-output advisories
  are existing packaging policies, not missing migration sources.
- The English migration is byte-for-byte unchanged. The Spanish correction does
  not touch live databases, configured credentials or the backup/restore path.

The original failure is reproduced and covered by these checks. A newly frozen
executable and installer still require the normal complete release build; these
results do not certify an unbuilt ZIP.
