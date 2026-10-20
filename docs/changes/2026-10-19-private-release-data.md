<!-- Tlamatini — Created by Angela López Mendoza · @angelahack1
Tlamatini Author Banner — do not remove -->
# 2026-10-19 — The private release carries the data of the machine that built it

**Status: on `main`, uncommitted, not released.** This changes only the *private (keyed)*
builder, `build_complete_private_release.py`. The public builder produces the same
scrubbed release as before and now refuses, in two places, to carry any of this.

## Why

A keyed release exists so that Angela does not have to reconfigure Tlamatini after
installing it. Measured before the change (a build made earlier that day compared with the
installed copy in `C:\Tlamatini`):

| Data | Installed app | Private release |
| --- | --- | --- |
| Secrets in `config.json` and the agent YAML files | set | set (23 vault entries are projected by `regen_secrets.py --mode keyed`) |
| Contacts | 4 | 4 (synced from the dev tree and the running install) |
| External MCP servers | **13**, **5 active** | **2** (`memory`, `sequential-thinking`), none active |
| `data.keys` | not installed | not shipped; 2 entries (`OPENROUTER_API_KEY`, `DASHSCOPE_API_KEY`) are placed by nothing |

A fresh install of the private release therefore lost eleven MCP servers, her active
selection and two vault entries.

## What it does now

1. **Step 0 (unchanged): contacts.** `contacts.private.json` is merged from the dev tree
   and the running install.
2. **Step 1 (unchanged): `regen_secrets.py --mode keyed`** projects the vault into
   `config.json`, the six agent YAML files and the dev MCP catalog.
3. **Step 1b (new): `external_mcps.private.json`.** `sync_external_mcps_private()` merges
   the tracked dev catalog with the catalog of the running install (`TLAMATINI_INSTALL`,
   `%LOCALAPPDATA%\Tlamatini`, `C:\Tlamatini`, first one found). Rules
   (`merge_external_mcps`):
   * every server of either catalog is kept;
   * for a server both have, the **dev spec wins**, and only an **empty or placeholder**
     `env` / `headers` value is filled from the install, never overwritten;
   * `active` is the install's own selection (else the dev one), restricted to servers that
     exist and capped at **5**, like the manager (`MAX_ACTIVE`; a test keeps the two equal);
   * with no install, the previous private snapshot stands in, so a build on another machine
     never drops servers;
   * the file is rewritten only when its content changes, and only server **names** and
     counts are printed, never a value.
   `build.py` still merges the two code-owned defaults and applies its tombstones. The file
   is gitignored and excluded from the self-modify snapshot, and the public builder counts
   it as "keyed evidence" when deciding whether a tree needs scrubbing.
4. **Step 1b (new): the vault.** `choose_data_keys()` selects `--keys-file` (default
   `data.keys`); the builder exports `TLAMATINI_BUNDLE_DATA_KEYS` and `build.py` copies it to
   `<install>/data.keys`, where the Access Keys Wizard reads it, so **every** entry arrives,
   including the ones no config file consumes. The message prints entry counts only.

## Guards

* `build_complete_public_release.py` pops `TLAMATINI_BUNDLE_DATA_KEYS` from the environment
  of every child, next to the existing pops for contacts and MCPs.
* `build.py` aborts (`SystemExit`) if the vault is requested while the MCP catalog is the
  PUBLIC one, so a half-set shell can never ship the vault with a public build.
* `.gitignore` lists `external_mcps.private.json`; `copy_source_assets.py` excludes it from
  the self-modify snapshot (it already excluded `data.keys` and `contacts.private.json`).

## Dry run on this machine (names and counts only)

The release would ship **13** External-MCP servers (`Snyk`, `Stream-Downloader`,
`deepwebresearch`, `exploit-db`, `ghidra`, `lumen-book-reader`, `memory`, `octocode`,
`onion-search-mcp`, `sequential-thinking`, `torrent-search-mcp`, `wireshark-mcp`,
`youtube`), the five active ones preserved, the two secret-bearing fields (`Snyk`,
`youtube`) holding real values, and a `data.keys` of **26** entries (23 with a value). No
release was built: `build.py` erases the development database and `dist/`, so a full build
is a separate decision.

## Tests

`Tests/test_release_regeneration.py` grew to **19 tests**, all passing (2026-10-19): merge
rules, input immutability, the 5-server cap against the manager's constant, the dev-active
fallback, an idempotent write, the previous-snapshot fallback, the environment the builder
hands to `build.py` (private catalog wins, stale vault variable dropped), counts-only
output, and source pins for the public builder, `build.py`, `.gitignore` and the snapshot
exclusion. The public-release target tests (26) and the preserved-state and provisioner
suites also pass; `agent.test_public_release_targets` needs the repository root on
`PYTHONPATH` when run through `manage.py test` (its loader imports `build_runtime_assets`).

## Not solved (open, by design)

* **An in-app update does not preserve `data.keys`.** `apply_update.ps1` keeps
  `config.json`, `external_mcps.json` and `contacts.json` but not the vault. The values that
  have a consumer survive inside `config.json`; the vault file itself would be dropped.
* **Two entries have no consumer.** `OPENROUTER_API_KEY` (nothing reads it) and
  `DASHSCOPE_API_KEY` (read only by the wizard, for a `qwen` ACPX block that
  `config.json` does not have) travel only inside `data.keys`.
* **Name drift.** The wizard writes Telegram and WhatsApp keys under `TELEGRAMMER_*` and
  `WHATSAPPER_*` names, while `regen_secrets.py` reads `TELEGRAM_*` and `WHATSAPP_*`; a key
  entered through the wizard is not restored by a keyed regen.
* **Installing over an existing install keeps the old catalog.** `external_mcps.json`,
  `contacts.json` and `config.json` are user state, preserved across reinstalls; the new
  catalog reaches a fresh install, not an overwritten one.
