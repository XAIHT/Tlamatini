# Glitches found in Tlamatini (English) — reported from the Tlamatini-Spanish session

**Written:** 2026-08-26
**By:** the Claude Code session working in `C:\Development\Tlamatini-Spanish`
**For:** the Claude Code session working in `C:\Development\Tlamatini` (the English tree)
**Requested by:** Angela López Mendoza (@angelahack1)

---

## How to use this file

While sweeping the `security/` Blue-hat toolkit in the **Spanish** tree, several problems
turned out to be **inherited from the English tree**, because `security/` was copied there
byte-for-byte. Each one below was **verified against the English working tree on 2026-08-26**,
with the evidence quoted.

**Read this as a lead, not as a patch.** Verify every claim yourself before changing anything —
the English tree may have moved since this was written. Every item names exactly what to check.

Each glitch gives you: the **evidence**, **why it is silent**, the **fix**, and the
**Spanish-tree reference implementation** you can read (do not blind-copy — see
*§ What is Spanish-only* at the bottom).

Priority order below is real: **G1 first.** It is losing data right now.

---

## G1 — 🔴 HIGH · A self-update DESTROYS the operator's security evidence

### Evidence (verified 2026-08-26)

```
C:\Development\Tlamatini\apply_update.ps1
  $Preserve = 'config.json','external_mcps.json','contacts.json','DB','application',
              'applications','content_generated','Temp','context_files','doc_generated',
              'documentation','Templates','Uninstaller.exe'
  occurrences of the word "security": 0
```

```
C:\Development\Tlamatini\security\security_logs\   ->  29 files, 3,923,301 bytes
  asset_tests\results_20260825_111720.json
  asset_tests\results_20260825_112000.json
  asset_tests\results_20260825_171720.json
  asset_tests\results_20260825_173336.json
  ...
```

**This is not hypothetical. That evidence exists on this machine today and the next
"About ▸ Check for updates" deletes all 3.9 MB of it.**

### What happens

`apply_update.ps1` step 4 deletes every top-level entry that is not in `$Preserve`.
`security` is (correctly!) not in `$Preserve` — it is **application code**, and a release
*must* be able to replace `tlamatini_defender.ps1` so a fixed defender can reach a user who
already installed a broken one.

But `security/security_logs/` is **not** application code. It is the operator's own evidence —
`alerts.log`, `monitor.log`, and the visible asset-test proof — and it lives *inside* that
replaced directory. This is structurally the **same situation as `db.sqlite3`**, which lives
inside the replaced `_internal/` and already gets special handling in **step 3b**.

### Why it is silent

The update reports success. Nothing errors. The user only discovers the loss the next time
they go looking for an incident trail — which is exactly the moment it matters.

### Do NOT fix it this way

**Do not add `'security'` to `$Preserve`.** That freezes the defender and whitelist scripts
on every existing install forever: a security fix could never be delivered. The whole point is
that the *code* is replaced and only the *evidence* is carried across.

### The fix

Mirror step 3b. Two halves, both required, both fail-open.

**(a) Before the delete loop** (insert immediately before the `# 4) Delete the old install`
comment):

```powershell
    # 3c) Preserve the Blue-hat toolkit's EVIDENCE across the update.
    #     security\ is application code: the new release MUST replace the
    #     defender/whitelist scripts. But security\security_logs\ is the
    #     operator's own evidence -- alerts.log, monitor.log and the visible
    #     asset-test proof -- and it lives INSIDE security\, so like the
    #     database it cannot be protected by the top-level $Preserve set.
    #     A blind delete-and-replace destroys incident history at exactly the
    #     moment it matters. Stash it under the preserved Temp\ (same volume,
    #     so this is a rename, not a copy) and restore it in step 5b.
    #     FAIL-OPEN: losing the logs is bad, but blocking the update is worse.
    $securityLogs = Join-Path $InstallDir "security\security_logs"
    $logsCarryover = Join-Path $InstallDir "Temp\_security_logs_carryover"
    try {
        if (Test-Path -LiteralPath $securityLogs) {
            if (Test-Path -LiteralPath $logsCarryover) {
                Remove-Item -LiteralPath $logsCarryover -Recurse -Force -ErrorAction SilentlyContinue
            }
            $carryParent = Split-Path -Parent $logsCarryover
            if (-not (Test-Path -LiteralPath $carryParent)) {
                New-Item -ItemType Directory -Path $carryParent -Force | Out-Null
            }
            Invoke-WithRetry { Move-Item -LiteralPath $securityLogs -Destination $logsCarryover -Force }
            Write-Log "Preserved your security evidence -> Temp\_security_logs_carryover." "Green"
        }
        else {
            Write-Log "No security\security_logs to preserve (toolkit never run?)." "Yellow"
        }
    }
    catch {
        Write-Log "WARN: could not stash security\security_logs -- continuing: $($_.Exception.Message)" "Yellow"
    }
```

**(b) After the move-in loop** (insert immediately before the `# 6) Clean up the staging area`
comment):

```powershell
    # 5b) Put the Blue-hat evidence back inside the NEW security\ tree.
    #     The new release ships security\ without security_logs\ (build.py
    #     ignores it on purpose), so this simply moves the operator's history
    #     back where the defender expects to append to it. FAIL-OPEN: on any
    #     error the stash is LEFT in Temp\_security_logs_carryover rather than
    #     deleted, so the evidence still exists and can be recovered by hand.
    try {
        if (Test-Path -LiteralPath $logsCarryover) {
            $securityDir = Join-Path $InstallDir "security"
            if (-not (Test-Path -LiteralPath $securityDir)) {
                New-Item -ItemType Directory -Path $securityDir -Force | Out-Null
            }
            if (Test-Path -LiteralPath $securityLogs) {
                Remove-Item -LiteralPath $securityLogs -Recurse -Force -ErrorAction SilentlyContinue
            }
            Invoke-WithRetry { Move-Item -LiteralPath $logsCarryover -Destination $securityLogs -Force }
            Write-Log "Restored your security evidence -> security\security_logs." "Green"
        }
    }
    catch {
        Write-Log "WARN: security evidence kept in Temp\_security_logs_carryover -- move it back by hand: $($_.Exception.Message)" "Yellow"
    }
```

`Temp` is in `$Preserve` and on the same volume, so the stash is a rename, not a 3.9 MB copy.

### Contract that must not be weakened

- **Both halves or neither.** A stash with no restore is *worse* than the original bug: it
  silently moves the evidence somewhere nobody looks, so the operator believes it is gone.
- **Fail-open both ways.** An update must never be blocked by log preservation, and a failed
  restore must **leave** the stash rather than delete it.
- `$Preserve` itself must stay unchanged — `security` stays out of it.

### Also update

`Tlamatini/agent/self_update.py` — its module docstring documents the preserve set and the
special-cased database. Add the same paragraph for the security evidence. Keep it near the
existing DB paragraph so the two special cases read as one idea.

⚠️ **Check the preserve-parity sweep still passes** after editing either file:
`python .claude\skills\tlamatini-self-update-inclusion\scripts\sweep_self_update.py`
It parses `$Preserve` out of `apply_update.ps1` and compares it to the `self_update.py`
docstring. The changes above do not touch `$Preserve`, so it should stay CLEAN — confirm it.

### Reference implementation

`C:\Development\Tlamatini-Spanish\apply_update.ps1` (steps 3c and 5b) and the docstring in
`C:\Development\Tlamatini-Spanish\Tlamatini\agent\self_update.py`. Verified there:
`apply_update.ps1` parses with **0** errors and the sweep stays CLEAN.

---

## G2 — 🟠 MEDIUM · The release scrubber and the private-data scanner both walk the evidence

### Evidence (verified 2026-08-26)

```
build_complete_public_release.py    security_logs in SKIP_DIRS: False
check_private_data.py               security_logs in SKIP_DIRS: False
```

### Why it matters

Two separate consequences, both wrong:

1. **`build_complete_public_release.py::scrub_tree`** walks the working tree and rewrites
   files whose extension is in `TEXT_EXT` — which includes `.json` and `.html`. That means it
   opens and rewrites the operator's own forensic artifacts (`asset_tests/results_*.json`,
   `SUMMARY.html`) in place. They are restored in the `finally` block, so this is not
   destructive today, but **a release build has no business editing forensic evidence**, and
   the existing `SKIP_DIRS` comment already states the correct rationale for exactly this
   case: *"never published, so never scrubbed."*

2. **`check_private_data.py`** scans it for private data. `security_logs` is, by design, full
   of usernames, IP addresses, administrator-group membership, process paths and full command
   lines — i.e. thousands of matches on data that **cannot leak**, because `build.py` never
   copies it into a release. That is noise in the one report that must stay trustworthy.

### The fix

Add `"security_logs"` to `SKIP_DIRS` in **both** files, beside the other gitignored runtime
trees, with a comment explaining why. Keep the two lists mirrored — `build_complete_public_release.py`
already says *"Mirrors the SKIP_DIRS in check_private_data.py."*

### Note — the docs are already correct here

`README.md` and `security/README.md` claim `security_logs/` is *"excluded from public builds"*.
**That claim is TRUE** and does not need changing: the exclusion is enforced by `build.py`'s
`shutil.ignore_patterns("security_logs", "*.log", "__pycache__")`, not by `SKIP_DIRS`. This fix
is about not *touching* / not *scanning* it, not about whether it ships.

---

## G3 — 🟠 MEDIUM · The entire security toolkit has ZERO automated coverage

### Evidence (verified 2026-08-26)

```
Tlamatini\agent\test_security*.py            -> NONE
agent\test_*.py mentioning security_logs /
  tlamatini_defender / automated_tests_of_security   -> none at all
```

`security/automated_tests_of_security_assets.py` exists, but **nothing runs it** and nothing
guards the contracts *around* it. So every one of these can rot with no test going red:

- `build.py` still copies `security/` and still omits `security_logs`
- `copy_source_assets.py` still prunes `security_logs`
- `.gitignore` still excludes `/security/security_logs/`
- the G1 stash/restore pair (once added) stays a **pair**
- the launchers still point at the right `.ps1` files
- the docs still describe behaviour that actually exists

### The fix

Add `Tlamatini/agent/test_security_assets_carriage.py`. A working, passing implementation
exists in the Spanish tree:

`C:\Development\Tlamatini-Spanish\Tlamatini\agent\test_security_assets_carriage.py`

**Port it, do not copy it.** Concrete changes needed for the English tree:

| Spanish assertion | English equivalent |
|---|---|
| `def toma_foto(` present, `def take_shot(` absent | **inverted** — English keeps `take_shot` |
| `"Activa a Tlamatini como agente Blue-hat"` in README/Book | `"Enable Tlamatini as a Blue-hat agent"` |
| `"Kit de seguridad Blue-hat de Tlamatini"` in `security/README.md` | `"Tlamatini Blue-hat Security Toolkit"` |
| Spanish section names (`Empieza en detect-only`, …) | English ones (`Start with detect-only`, `The ten monitor families`, `Blue-hat deployment checklist`) |
| the whole `SpanishEditionAdaptationTests` class | **drop it** — it pins a Spanish-only convention |

The genuinely portable classes are `AssetsPresentTests`, `BuildCarriageTests`,
`SelfUpdateEvidenceTests` and `DocumentationTests`.

⚠️ One trap worth inheriting: an early version of that test asserted
`assertNotIn("ImageGrab", harness)` and failed — because the harness *names* `ImageGrab` in
order to **forbid** it. Assert on real use (`from PIL`, `import PIL`, `ImageGrab.grab(`) and
separately assert the prohibition text is still there.

---

## G4 — 🟡 LOW · The docs describe the update behaviour in a way that reads as safe

### Evidence (verified 2026-08-26)

`BookOfTlamatini.md` line 333:

> `build.py` copies the entire repository `security/` tree beside the installed executable and
> excludes `security_logs`, `*.log`, and `__pycache__`. **The self-update swap treats
> `security/` as application code, so a new release replaces the scripts while runtime logs are
> not shipped as release content.** `copy_source_assets.py` includes the `.ps1`, `.bat`, `.py`,
> and Markdown source in self-modify snapshots while pruning every directory named
> `security_logs`. `.gitignore` likewise excludes `/security/security_logs/`.

`README.md` line 433 carries the same claim in shorter form.

### Why it is wrong

Every clause is literally true, and the paragraph as a whole is **misleading**. "runtime logs
are not shipped as release content" describes what does *not* go **out**; a reader naturally
concludes their logs are simply left alone. In fact they are **deleted**. A reader who trusted
this paragraph would not think to back anything up before updating.

### The fix

After G1 lands, replace that sentence with what actually happens:

> On self-update, `security/` is treated as **application code**: a new release replaces the
> scripts, which is what you want — a fixed defender has to be able to reach a user who already
> installed a broken one. But `security/security_logs/` is the **operator's evidence** and lives
> inside that replaced directory, so like the database it needs separate handling:
> `apply_update.ps1` moves it to `Temp/_security_logs_carryover` before the delete (step 3c) and
> moves it back into the new `security/` afterwards (step 5b). Both halves fail open — on any
> error the update still completes and the evidence is *left* in the carryover directory rather
> than removed.

Update `README.md` and `security/README.md` to match. **Do not write this documentation before
the code exists** — a doc describing a carryover that has not been implemented is worse than
the current wording.

---

## G5 — 🟡 LOW · Hardening only — NOT a live bug in the English tree

**Read the qualifier first: this is not currently broken in English.** It is included because
the Spanish tree got badly bitten by it and the English tree has the same shape of exposure.

### What the Spanish tree hit

Tlamatini-Spanish tags releases with a trailing edition letter (`v1.50.0s`). That is not valid
SemVer, so `version.py::parse_semver()` returned `None`, and **two callers failed open in
opposite, invisible directions**:

- `semver_to_win32_tuple()` fell back to `(0, 0, 0, 0)` — every Spanish `.exe` reported
  **ProductVersion `0.0.0.0`** to Windows Explorer, installers and upgrade-detection logic,
  while the About dialog and startup banner still showed the correct string;
- `self_update._version_tuple()` fell through to its crude numeric split, which stops at the
  first non-digit field and therefore **dropped the patch number** — `1.49.1s` compared equal
  to `1.49.0s`, so **a patch release was never offered to a user**.

### Why it does not affect English today (verified)

```
EN Tlamatini\agent\version.py
  has strip_edition_suffix : False       (correct - the English tree does not need it)
  fails open to (0, 0, 0, 0): True       (the shared fail-open path)
EN tags: v1.50.0, v1.49.1, v1.48.17 ...  (plain SemVer - parse_semver succeeds)
```

English tags are clean SemVer, so both paths work. **Do not port `strip_edition_suffix` into
the English tree** — it would be dead code there.

### What is worth doing

The English tree has **no version guard test at all**
(`Tlamatini\agent\test_*version*.py` -> NONE). Both failure modes above are invisible from the
UI, so a small test that pins the *English* expectations is cheap insurance against a future
tag shape (`v2.0.0-rc.1`, a date-stamped tag, a `+build` local part) silently zeroing the
`.exe` metadata or breaking update detection:

```python
self.assertEqual(semver_to_win32_tuple("1.50.0"), (1, 50, 0, 0))
self.assertEqual(semver_to_win32_tuple("2.0.0-rc.1"), (2, 0, 0, 0))
self.assertTrue(self_update.is_newer("1.50.1", "1.50.0"))   # patch-level detection
self.assertTrue(self_update.is_newer("1.50.0", "1.49.1"))
```

The Spanish version of this file — adapt, do not copy — is
`C:\Development\Tlamatini-Spanish\Tlamatini\agent\test_edition_version_suffix.py`.

---

## G6 — 🟠 MEDIUM · `Tlamatini.md` is a system-prompt payload with no guard against going stale

*(Added after Angela pointed at the self-modify snapshot and asked us to look harder. She was
right: the snapshot **ships** correctly, but its **content** had rotted.)*

### What happened in the Spanish tree

`agent/Tlamatini.md` is not documentation *about* Tlamatini — `rag/config.py` injects it into
her **system prompt** as `{self_knowledge}`, and it is what she answers from when a user asks
what she is. In the Spanish tree it had drifted a full release behind source:

| | source truth | `Tlamatini.md` claimed |
|---|---|---|
| workflow agents | 88 | **87** |
| wrapped `chat_agent_*` launchers | 66 | **65** |
| built-in Multi-Turn tools | 108 | **107** |
| skills | 29 | **28** |

NetSpeed-Calculator and the 29th skill had landed; her self-description never followed. **A
stale number there is not a typo — it makes her state a falsehood about herself, confidently,
with nothing for the user to check it against.** It shipped inside every `--self-modify` build
for a whole release.

### What to check in the English tree

The English `Tlamatini.md` numbers were **correct when checked on 2026-08-26** (66 wrapped /
108 tools / 29 skills) — so there is probably nothing to fix *today*. **The gap is that
nothing stops it drifting tomorrow**, and English has no version/self-knowledge guard at all
(see also G5).

Re-derive before assuming:

```powershell
# agents: <name>/<name>.py + <name>/config.yaml under agent/agents (excluding pools)
# wrapped: count of "ChatWrappedAgentSpec(" in agent/chat_agent_registry.py
# skills: directories under agent/skills_pkg containing SKILL.md
```

then compare against every count asserted inside `agent/Tlamatini.md`.

### The fix

Port `Tlamatini/agent/test_self_knowledge_is_current.py` from the Spanish tree. **Every
expectation in it is DERIVED from source — nothing is hand-typed**, so agent #89 makes it fail
and name the file to update. It also checks that the Multi-Turn breakdown *adds up*
(`total == core + wrapped + acpx + supervisors`), which is how an inconsistent edit gets caught.

**Drop the `SpanishEditionSelfKnowledgeTests` class entirely** — it pins the Spanish golden
rule and is meaningless in English. Keep `SelfKnowledgeCountsMatchSourceTests`, and keep
`BlueHatToolkitSelfKnowledgeTests` only after doing G7.

⚠️ One trap: the paths quoted inside `Tlamatini.md` (`agent/tts_piper.py`, …) are relative to
the **Django root** (`Tlamatini/`), not the repo root. Resolving them from the repo root makes
the "does this file exist" check fail on four correct paths.

---

## G7 — 🟡 LOW · Tlamatini does not know her own Blue-hat toolkit exists

### Evidence (verified 2026-08-26, BOTH trees)

```
'Blue-hat'            in EN Tlamatini.md: no
'tlamatini_defender'  in EN Tlamatini.md: no
'whitelist'           in EN Tlamatini.md: no
```

### Why it matters

Ask her *"can you scan this machine for intruders?"* and she has no idea the toolkit is part of
her at all. The two failure modes are opposite and both bad: she **denies** having any security
capability, or — worse, once she notices `security/` on disk — she **claims she ran a sweep**
she cannot run. There is no `chat_agent_*` for the defender, no Agent row, no canvas node: it
is operator-launched only.

### The fix

Add a bullet to `agent/Tlamatini.md` §1 stating, precisely:

- the toolkit exists and where (`security/`, beside the executable when frozen);
- what the four assets are;
- **that she cannot invoke any of it** — a human administrator launches it, reads the evidence
  and owns the Windows policy changes, so she should *explain and point*, never claim to have
  run it;
- that the whitelist deliberately **relaxes** enforcement around her own tree (exclusions +
  six ASR rules moved to Audit), which makes her install a privileged trust boundary;
- that `security/security_logs/` survives a self-update via the G1 carryover;
- where the full runbook is (`README.md` / `BookOfTlamatini.md` / `security/README.md`).

The Spanish wording is in `C:\Development\Tlamatini-Spanish\Tlamatini\agent\Tlamatini.md`
(the bullet right after the five pillars). It is already in English prose — it can be reused
almost verbatim, minus the Spanish section titles.

⚠️ **Do this AFTER G1**, or the bullet will describe a carryover that does not exist yet.

---

## What is Spanish-only — do NOT port these

The Spanish tree deliberately diverges in ways that would be **wrong** in English. If you find
yourself "syncing" any of these back, stop:

1. **The `s` edition letter** and `strip_edition_suffix` / `_semver_body` — Spanish-only
   (see G5). English tags are plain SemVer.
2. **`toma_foto()`** — the Spanish tree's Shoter helper name in
   `security/automated_tests_of_security_assets.py`. **English correctly uses `take_shot()`.**
3. **Spanish operator-facing text** — `security/README.md`, the harness console banner and the
   `SUMMARY.html` chrome are Spanish over there by design.
4. **The Spanish GOLDEN RULE.** `Tlamatini-Spanish` never speaks English — its hierarchy is
   Latin-American Spanish → Castilian → **error and silence**, with no English rung, enforced
   by `EnglishVoiceForbiddenError` and friends. That rule is now written into the Spanish
   `Tlamatini.md` (G6/G7 work). **The English tree correctly speaks English**; porting any part
   of this would be actively harmful.
5. **Commit hashes.** The Spanish docs had copied four English commits
   (`ae6fec4c`, `d161098e`, `834eaa16`, `f948be7b`) that do not exist in that repository.
   Never quote a commit hash across the two trees, in either direction.

Also worth knowing, since it explains a deliberate non-change: in **both** trees the two
`.ps1` files keep their **English** console strings on purpose. The harness asserts on exact
phrases inside them (e.g. `verified in Audit mode`), so translating one side without the other
leaves a test that passes while proving nothing. If they are ever translated, both sides move
in the same commit.

---

## Verification checklist for the English session

Run these after the changes and require the stated result:

```powershell
# G1 - the updater still parses
powershell -NoProfile -Command "$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile('C:\Development\Tlamatini\apply_update.ps1',[ref]$t,[ref]$e); @($e).Count"
#   -> 0

# G1 - preserve parity + self-update invariants
python .claude\skills\tlamatini-self-update-inclusion\scripts\sweep_self_update.py
#   -> RESULT: CLEAN

# G2/G3 - the snapshot still carries every security asset and prunes the logs
python .claude\skills\tlamatini-self-modify-inclusion\scripts\sweep_self_modify.py
#   -> RESULT: CLEAN

# G3/G6/G7 - the new guards
cd Tlamatini
python manage.py test agent.test_security_assets_carriage agent.test_self_knowledge_is_current agent.test_preserved_user_state agent.test_self_update
#   -> OK

# G6 - derive the counts and compare them to what Tlamatini.md claims
python -c "import re,os; a=r'agent\agents'; print('agents', sum(1 for d in os.listdir(a) if os.path.isfile(os.path.join(a,d,d+'.py')) and os.path.isfile(os.path.join(a,d,'config.yaml')))); print('wrapped', len(re.findall(r'ChatWrappedAgentSpec\(', open(r'agent\chat_agent_registry.py',encoding='utf-8').read()))); s=r'agent\skills_pkg'; print('skills', sum(1 for d in os.listdir(s) if os.path.isfile(os.path.join(s,d,'SKILL.md'))))"

python -m ruff check
```

**A manual check worth doing once for G1**, because it is the whole point: put a known file in
`security\security_logs\`, run the update path against a scratch install, and confirm the file
is still there afterwards. A green unit test proves the *script contains* both halves; only
this proves the evidence actually survives.

---

## Status in the Spanish tree, for reference

All five were addressed in `C:\Development\Tlamatini-Spanish` on 2026-08-26 and verified:
`apply_update.ps1` parses with 0 errors, 62 guard tests pass, both inclusion sweeps report
CLEAN, and `ruff` is clean on every touched file. The dated write-up is
`docs/claude/recent-fixes.md` → **2026-08-26 — Blue-hat toolkit in the Spanish tree**.

That tree carries **19 pre-existing test failures** unrelated to this work (Spanish
agent-descriptions overlay, dialog policy/theme, prompt catalog, Talker/Piper voice). They are
Spanish-specific; do not go looking for them in English.

> **Created by Angela López Mendoza (@angelahack1)** — Tlamatini, the one who knows.
