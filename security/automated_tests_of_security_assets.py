#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
automated_tests_of_security_assets.py
=====================================================================
PERSISTENT, VISIBLE automated regression test for Tlamatini's security
arsenal (the hacker-combat assets in this ``security/`` folder):

    - tlamatini_defender.ps1       (Active Defender, monitoring + response)
    - tlamatini_whitelist_v2.ps1   (grants Tlamatini monitoring privileges)
    - run_defender.bat             (UAC launcher -> defender)
    - enable_tlamatini_v2.bat      (UAC launcher -> whitelist)

WHAT IT PROVES (no admin required, non-destructive):
    1. Both PowerShell scripts PARSE with ZERO errors (the v2.0 defender
       shipped with 5 fatal parse errors and never ran once - this guards
       against that ever regressing).
    2. The defender's SELF-SAFE classifier is correct:
         nmap      -> dualuse  (ALERT only; Tlamatini's Nmapper runs it)
         mimikatz  -> malware  (auto-kill)
         a Tlamatini path is recognised as "self" (never killed).
    3. The new combat modules are present (ransomware / Defender-tamper /
       account-abuse / -Watch / -DetectOnly / -Aggressive).
    4. The whitelist's dead ``$OCTUALLY`` WMI block is gone and the real
       Get-CimInstance verification + cmdline/script-block auditing are in.
    5. The .bat launchers point at the right .ps1 files.

GOLDEN RULES honoured (Angela, MANDATORY, FOREVER):
    - VISIBLE + HEADED + FOREGROUND: the PowerShell checks run in a real,
      visible FORKED FOREGROUND console window; the results are shown in a
      HEADED Chrome window (Playwright headless=False, real Chrome preferred).
    - SCREENSHOTS are taken by Tlamatini's SHOTER agent (all_screens=True,
      the WHOLE desktop). PIL.ImageGrab is FORBIDDEN here; if Shoter cannot
      run, this test REPORTS it and FAILS - it never falls back to Pillow.
    - NO LYING: every check records a real, observed PASS/FAIL.

USAGE:
    python automated_tests_of_security_assets.py

Exit code 0 = all PASS, 1 = at least one FAIL.

Author: Tlamatini (created by Angela Lopez Mendoza, @angelahack1)
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

# --- Windows CreateProcess flag for a real, visible, separate console -------
CREATE_NEW_CONSOLE = 0x00000010

SCRIPT_DIR = Path(__file__).resolve().parent          # ...\security
ROOT_DIR = SCRIPT_DIR.parent                          # install / dev root
DEFENDER = SCRIPT_DIR / "tlamatini_defender.ps1"
WHITELIST = SCRIPT_DIR / "tlamatini_whitelist_v2.ps1"
RUN_BAT = SCRIPT_DIR / "run_defender.bat"
ENABLE_BAT = SCRIPT_DIR / "enable_tlamatini_v2.bat"

# Artifacts live under security_logs/ (gitignored, never shipped, never snapshotted).
RUN_STAMP = time.strftime("%Y%m%d_%H%M%S")
WORK_DIR = SCRIPT_DIR / "security_logs" / "asset_tests"
WORK_DIR.mkdir(parents=True, exist_ok=True)
HARNESS_PS1 = WORK_DIR / "asset_test_harness.ps1"
RESULTS_JSON = WORK_DIR / f"results_{RUN_STAMP}.json"
SUMMARY_HTML = WORK_DIR / "SUMMARY.html"
RUN_LOG = WORK_DIR / f"run_{RUN_STAMP}.log"

# results collected as (name, passed, detail)
RESULTS = []
_LOG_LINES = []


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    _LOG_LINES.append(line)


def record(name, passed, detail=""):
    RESULTS.append((name, bool(passed), str(detail)))
    log(f"{'PASS' if passed else 'FAIL'}  {name}  {('- ' + detail) if detail else ''}")


# ---------------------------------------------------------------------------
# SHOTER: full-desktop screenshot via Tlamatini's own agent (never PIL).
# ---------------------------------------------------------------------------
def find_shoter_dir():
    for cand in (
        ROOT_DIR / "agents" / "shoter",                          # frozen install
        ROOT_DIR / "Tlamatini" / "agent" / "agents" / "shoter",  # dev / source tree
    ):
        if (cand / "shoter.py").is_file():
            return cand
    return None


def take_shot(filename, out_dir):
    """Capture the WHOLE desktop with Shoter. Returns (ok, path_or_reason).

    Angela's rule: NEVER fall back to PIL. If Shoter cannot run, REPORT it.
    """
    shoter_src = find_shoter_dir()
    if shoter_src is None:
        return False, "Shoter agent not found (agents/shoter). REPORTED, no PIL fallback."
    run_dir = WORK_DIR / f"_shoter_{RUN_STAMP}" / "shoter"
    run_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(shoter_src / "shoter.py", run_dir / "shoter.py")
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not stage Shoter: {exc}"
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = (
        f"output_dir: \"{out_dir.as_posix()}\"\n"
        f"all_screens: true\n"
        f"filename: \"{filename}\"\n"
        f"target_agents: []\n"
    )
    (run_dir / "config.yaml").write_text(cfg, encoding="utf-8")
    try:
        proc = subprocess.run(
            [sys.executable, "shoter.py"],
            cwd=str(run_dir),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=90,
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"Shoter launch failed: {exc}"
    expected = out_dir / filename
    if expected.is_file() and expected.stat().st_size > 0:
        return True, str(expected)
    tail = (proc.stdout or "") + (proc.stderr or "")
    return False, f"Shoter produced no image. Output tail: {tail[-300:]}"


# ---------------------------------------------------------------------------
# VISIBLE FOREGROUND PowerShell harness: parse-checks + classifier smoke.
# ---------------------------------------------------------------------------
def build_harness_ps1():
    dfn = str(DEFENDER)
    wl = str(WHITELIST)
    root = str(ROOT_DIR)
    res = str(RESULTS_JSON)
    content = f"""# Auto-generated by automated_tests_of_security_assets.py - visible test harness.
$ErrorActionPreference = 'Continue'
Write-Host ''
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host '  TLAMATINI SECURITY ASSET TESTS  (visible foreground window)'    -ForegroundColor Cyan
Write-Host '  Created by Angela Lopez Mendoza (@angelahack1)'                  -ForegroundColor Cyan
Write-Host '================================================================' -ForegroundColor Cyan
Write-Host ''

function Get-ParseErrorCount([string]$p) {{
    $e = $null; $t = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$t, [ref]$e)
    return @($e).Count
}}

$res = [ordered]@{{}}
$res.defender_parse_errors  = Get-ParseErrorCount '{dfn}'
$res.whitelist_parse_errors = Get-ParseErrorCount '{wl}'

# Classifier smoke: load ONLY the defender's function defs (skip the main block).
try {{
    $src   = Get-Content '{dfn}' -Raw
    $fnStart = $src.IndexOf('function Test-IsSelf')
    $fnEnd   = $src.IndexOf('# MAIN EXECUTION')
    $funcs   = $src.Substring($fnStart, $fnEnd - $fnStart)
    Invoke-Expression $funcs
    $script:SelfRoots = @('{root}')
    $nmap = [pscustomobject]@{{ ProcessName = 'nmap';     Id = 1; Path = 'C:\\Program Files\\Nmap\\nmap.exe' }}
    $mk   = [pscustomobject]@{{ ProcessName = 'mimikatz'; Id = 2; Path = 'C:\\Users\\Public\\mk.exe' }}
    $res.tier_nmap         = [string](Get-ThreatTier $nmap)
    $res.tier_mimikatz     = [string](Get-ThreatTier $mk)
    $res.isself_dev        = [bool](Test-IsSelf '{root}\\Go\\bin\\nmap.exe')
    $res.isself_pub        = [bool](Test-IsSelf 'C:\\Users\\Public\\mk.exe')
    $res.classifier_loaded = $true
}} catch {{
    $res.classifier_loaded = $false
    $res.classifier_error  = $_.Exception.Message
}}

$res | ConvertTo-Json | Set-Content '{res}' -Encoding UTF8

Write-Host ('  Defender parse errors : ' + $res.defender_parse_errors)  -ForegroundColor White
Write-Host ('  Whitelist parse errors: ' + $res.whitelist_parse_errors) -ForegroundColor White
Write-Host ('  nmap classifier tier  : ' + $res.tier_nmap + '   (expect dualuse)')  -ForegroundColor White
Write-Host ('  mimikatz classifier   : ' + $res.tier_mimikatz + '   (expect malware)') -ForegroundColor White
Write-Host ('  self dev-path safe    : ' + $res.isself_dev + '   (expect True)')    -ForegroundColor White
Write-Host ('  self public-path safe : ' + $res.isself_pub + '   (expect False)')   -ForegroundColor White
Write-Host ''
Write-Host '  Results written. This window stays visible for a few seconds...' -ForegroundColor Yellow
Start-Sleep -Seconds 7
"""
    HARNESS_PS1.write_text(content, encoding="utf-8")
    return HARNESS_PS1


def run_visible_harness():
    build_harness_ps1()
    if RESULTS_JSON.exists():
        RESULTS_JSON.unlink()
    log("Launching VISIBLE FOREGROUND PowerShell test window...")
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(HARNESS_PS1)],
            creationflags=CREATE_NEW_CONSOLE,
        )
    except Exception as exc:  # noqa: BLE001
        return None, f"Could not spawn visible PowerShell window: {exc}"
    # Wait for the harness to drop results.json (it writes before its 7s pause).
    deadline = time.time() + 40
    while time.time() < deadline:
        if RESULTS_JSON.exists():
            try:
                data = json.loads(RESULTS_JSON.read_text(encoding="utf-8-sig"))
                return data, ""
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        time.sleep(0.5)
    return None, "Timed out waiting for the harness results.json"


# ---------------------------------------------------------------------------
# Static content checks (read the files directly in Python).
# ---------------------------------------------------------------------------
def static_checks():
    dtxt = DEFENDER.read_text(encoding="utf-8", errors="replace") if DEFENDER.exists() else ""
    wtxt = WHITELIST.read_text(encoding="utf-8", errors="replace") if WHITELIST.exists() else ""
    rbat = RUN_BAT.read_text(encoding="utf-8", errors="replace") if RUN_BAT.exists() else ""
    ebat = ENABLE_BAT.read_text(encoding="utf-8", errors="replace") if ENABLE_BAT.exists() else ""

    record("defender file present", bool(dtxt), str(DEFENDER))
    record("whitelist file present", bool(wtxt), str(WHITELIST))

    for token in ("-Watch", "-DetectOnly", "-Aggressive", "Test-IsSelf",
                  "Monitor-Ransomware", "Monitor-DefenderHealth", "Monitor-AccountThreats"):
        record(f"defender has {token}", token in dtxt)
    record("defender bounds the watch interval",
           "[ValidateRange(5, 86400)]" in dtxt)
    certainty_phrase = "Those are your " + "hackers"
    record("defender does not present alerts as confirmed attackers",
           certainty_phrase not in dtxt)

    # The old fatal bug: unquoted wildcard entries in the pattern array.
    record("defender has no unquoted-wildcard bug", ", *metasploit*" not in dtxt,
           "the v2.0 parse-error pattern is gone")

    # Whitelist fixes.
    record("whitelist WMI uses Get-CimInstance",
           "Get-CimInstance -ClassName Win32_OperatingSystem" in wtxt)
    # $OCTUALLY may only survive in the changelog comment, never as live code.
    live_octually = any(
        ("OCTUALLY" in ln and not ln.lstrip().startswith("#")) for ln in wtxt.splitlines()
    )
    record("whitelist has no live $OCTUALLY dead code", not live_octually)
    record("whitelist enables cmdline-in-4688",
           "ProcessCreationIncludeCmdLine_Enabled" in wtxt)
    record("whitelist enables script-block logging",
           "EnableScriptBlockLogging" in wtxt)

    official_asr_guids = (
        "d4f940ab-401b-4efc-aadc-ad5f3c50688a",
        "9e6c4e1f-7d60-472f-ba1a-a39ef669e4b2",
        "e6db77e5-3df2-4cf1-b95a-636979351e5b",
        "be9ba2d9-53ea-4cdc-84e5-9b1eeee46550",
        "b2b3f03d-6a65-4f7b-a9c7-1c7ef74a9ba4",
        "d1e49aac-8f56-4280-b9ba-993a6d77406c",
    )
    for guid in official_asr_guids:
        record(f"whitelist has official ASR GUID {guid}", guid in wtxt)
    record("whitelist verifies effective ASR actions",
           "AttackSurfaceReductionRules_Actions" in wtxt and
           "verified in Audit mode" in wtxt)

    audit_policy_guids = (
        "{0CCE9215-69AE-11D9-BED3-505054503030}",
        "{0CCE922B-69AE-11D9-BED3-505054503030}",
        "{0CCE923F-69AE-11D9-BED3-505054503030}",
        "{0CCE9228-69AE-11D9-BED3-505054503030}",
        "{0CCE9235-69AE-11D9-BED3-505054503030}",
    )
    record("whitelist uses locale-neutral audit subcategory GUIDs",
           all(guid in wtxt for guid in audit_policy_guids))
    record("whitelist checks auditpol exit status", "$LASTEXITCODE" in wtxt)

    # Launchers point at the right scripts.
    record("run_defender.bat -> defender.ps1", "tlamatini_defender.ps1" in rbat)
    record("enable_tlamatini_v2.bat -> whitelist", "tlamatini_whitelist_v2.ps1" in ebat)
    for name, text in (("run_defender.bat", rbat), ("enable_tlamatini_v2.bat", ebat)):
        direct_elevation = (
            'set "TLAMATINI_LAUNCHER=%~f0"' in text
            and "Start-Process -FilePath $env:TLAMATINI_LAUNCHER" in text
        )
        record(f"{name} safely self-elevates paths with spaces", direct_elevation)
        record(f"{name} propagates PowerShell failures",
               'set "TLAMATINI_EXIT=%errorlevel%"' in text and
               "exit /b %TLAMATINI_EXIT%" in text)


def evaluate_harness(data):
    if data is None:
        record("PowerShell parse+classifier harness", False, "no results returned")
        return
    de = data.get("defender_parse_errors")
    we = data.get("whitelist_parse_errors")
    record("defender parses with 0 errors", de == 0, f"errors={de}")
    record("whitelist parses with 0 errors", we == 0, f"errors={we}")
    record("classifier: nmap -> dualuse", str(data.get("tier_nmap")).lower() == "dualuse",
           f"got {data.get('tier_nmap')}")
    record("classifier: mimikatz -> malware", str(data.get("tier_mimikatz")).lower() == "malware",
           f"got {data.get('tier_mimikatz')}")
    record("self-safe: dev path is self", bool(data.get("isself_dev")) is True)
    record("self-safe: public path is NOT self", bool(data.get("isself_pub")) is False)


# ---------------------------------------------------------------------------
# SUMMARY.html + headed browser.
# ---------------------------------------------------------------------------
def write_summary(shot_console):
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = total - passed
    status = "ALL PASS" if failed == 0 else f"{failed} FAILED"
    color = "#1f9d55" if failed == 0 else "#c0392b"
    rows = []
    for name, ok, detail in RESULTS:
        badge = "PASS" if ok else "FAIL"
        bg = "#e8f8f0" if ok else "#fdecea"
        fg = "#1f9d55" if ok else "#c0392b"
        rows.append(
            f"<tr style='background:{bg}'><td style='color:{fg};font-weight:700'>{badge}</td>"
            f"<td>{name}</td><td style='color:#555'>{detail}</td></tr>"
        )
    shot_html = ""
    if shot_console and os.path.isfile(shot_console):
        shot_uri = Path(shot_console).as_uri()
        shot_html = (
            "<h3>Visible proof (Shoter full-desktop capture)</h3>"
            f"<img src='{shot_uri}' style='max-width:100%;border:1px solid #ccc;border-radius:8px'/>"
        )
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>Tlamatini Security Asset Tests</title>
<style>
 body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#0f1420;color:#e8ecf3}}
 .card{{background:#161c2b;border-radius:12px;padding:20px 26px;box-shadow:0 6px 24px rgba(0,0,0,.4)}}
 h1{{margin:0 0 6px}} .sub{{color:#9aa4b2;margin-bottom:16px}}
 .status{{display:inline-block;padding:8px 18px;border-radius:999px;color:#fff;font-weight:800;background:{color}}}
 table{{width:100%;border-collapse:collapse;margin-top:18px;background:#fff;color:#222;border-radius:8px;overflow:hidden}}
 th,td{{padding:8px 12px;text-align:left;border-bottom:1px solid #eee;font-size:14px}}
 th{{background:#20283a;color:#fff}}
 img{{margin-top:10px}}
 .foot{{margin-top:18px;color:#9aa4b2;font-size:13px}}
</style></head><body>
<div class="card">
 <h1>TLAMATINI - Security Asset Tests</h1>
 <div class="sub">Run {RUN_STAMP} &middot; {passed}/{total} checks passed</div>
 <div class="status">{status}</div>
 <table><thead><tr><th>Result</th><th>Check</th><th>Detail</th></tr></thead>
 <tbody>{''.join(rows)}</tbody></table>
 {shot_html}
 <div class="foot">Created by Angela Lopez Mendoza (@angelahack1) &middot; Tlamatini - the one who knows</div>
</div></body></html>"""
    SUMMARY_HTML.write_text(html, encoding="utf-8")
    return SUMMARY_HTML


def open_headed_browser(html_path):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return False, f"Playwright not available: {exc}"
    url = Path(html_path).as_uri()
    try:
        with sync_playwright() as p:
            browser = None
            for kw in ({"channel": "chrome", "headless": False}, {"headless": False}):
                try:
                    browser = p.chromium.launch(**kw)
                    break
                except Exception:  # noqa: BLE001
                    browser = None
            if browser is None:
                return False, "Could not launch a headed browser"
            page = browser.new_page(no_viewport=True)
            page.goto(url)
            page.wait_for_timeout(1500)
            # Give Shoter a moment to photograph the visible browser.
            ok_shot, shot = take_shot("asset_tests_browser.png", WORK_DIR / "shots")
            record("Shoter photographed the headed browser", ok_shot, shot)
            page.wait_for_timeout(6000)
            browser.close()
        return True, "headed browser shown"
    except Exception as exc:  # noqa: BLE001
        return False, f"Headed browser error: {exc}"


# ---------------------------------------------------------------------------
def main():
    log("=== Tlamatini security-asset automated tests START ===")
    log(f"Script dir : {SCRIPT_DIR}")
    log(f"Root dir   : {ROOT_DIR}")

    # 1) static checks (Python-side)
    static_checks()

    # 2) visible foreground PowerShell harness (parse + classifier)
    data, err = run_visible_harness()
    if err:
        log(f"Harness note: {err}")
    evaluate_harness(data)

    # 3) Shoter full-desktop shot of the run (visible-proof)
    ok_shot, shot = take_shot("asset_tests_console.png", WORK_DIR / "shots")
    record("Shoter full-desktop capture (console)", ok_shot, shot)
    console_shot = shot if ok_shot else None

    # 4) SUMMARY.html
    summary = write_summary(console_shot)
    log(f"Summary written: {summary}")

    # 5) headed browser shows the summary + a second Shoter proof
    ok_browser, bdetail = open_headed_browser(summary)
    record("Headed browser displayed the summary", ok_browser, bdetail)

    # write the run log
    RUN_LOG.write_text("\n".join(_LOG_LINES), encoding="utf-8")

    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = total - passed
    print("")
    print("================================================================")
    print(f"  SECURITY ASSET TESTS: {passed}/{total} PASSED"
          + ("  -> ALL PASS" if failed == 0 else f"  -> {failed} FAILED"))
    print(f"  Summary : {summary}")
    print(f"  Log     : {RUN_LOG}")
    print("================================================================")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
