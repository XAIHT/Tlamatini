"""
Fix the **STM32 HIL OBSERVATORY** demo (catalog prompt #65, seeded by 0103).

WHY
---
Live run on a real STM32F407G-DISC1 exposed a board-specific flaw in the demo as
first written. The board flashed cleanly (green LED blinking) and the firmware
WAS running — proven by ``live_monitor`` reading ``g_blink_count`` climbing over
SWD (30 -> 31 -> 32). But the demo made the **serial VCP boot-banner read** a
PRIMARY proof step, and that read returns 0 bytes forever on this board:

    On the STM32F4-Discovery family (including the STM32F407G-DISC1) the on-board
    ST-LINK does NOT bridge its Virtual COM Port to the MCU's USART pins (unlike
    ST Nucleo boards, which route VCP <-> USART2 / PA2-PA3). A firmware that
    transmits on USART2 therefore produces NOTHING on the VCP, no matter the
    baud or timeout.

Because the demo gave the model no "empty VCP read is EXPECTED here, do NOT
retry" guidance, it thrashed: ~6 ``serial_session`` retries with escalating
timeouts (5/6/8/10/12 s, even injecting ``data='\\n'``), plus ``serial_connect``
+ ``serial_read`` + a stray ``reset`` — 21 STM32er calls for what should be ~9.

THE FIX (this migration rewrites prompt #65 only)
-------------------------------------------------
1. **live SWD memory (``live_monitor``) is now the PRIMARY, authoritative HIL
   proof** (it works on every ST-LINK board). It runs as Step 6, before serial.
2. **The serial VCP read is now best-effort, board-aware, and AT-MOST-ONCE.** The
   prompt states the F4-Discovery VCP-not-routed fact up front, tells the model an
   empty read (bytes=0) is the EXPECTED outcome on this board, and forbids the
   retry / connect-read loop. (Real UART would need an external USB-TTL adapter on
   PA2/PA3 — out of scope for an ST-LINK-only demo.)
3. **The "SILICON VERIFIED" verdict is re-keyed on build + flash + live_memory.**
   Serial is a bonus chip (green = data, amber = expected-empty, red = real connect
   error), never a gate, so the demo reaches a clean success on a Discovery board.

This is a content-only update of one ``Prompt`` row via ``update_or_create`` —
no schema change. Reverse restores the original 0103 text verbatim.
"""
import importlib

from django.db import migrations


_HIL_PROMPT_ID = 65


# Reuse the exact ST-blue banner palette from 0103 so the demo keeps its look.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#061029 0%,#0B3A8F 40%,#1E63FF 72%,#22D3EE 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.45);'>"
)


STM32_HIL_OBSERVATORY_DEMO_V2 = (
    "Tlamatini, run the **STM32 HIL OBSERVATORY** demo, please &mdash; an advanced "
    "**hardware-in-the-loop** showcase that USES A REAL BOARD end-to-end, driven entirely from "
    "chat through the wrapped **chat_agent_stm32er** tool: it preflight-validates that an ST-LINK "
    "is connected, scaffolds and AUTHORS firmware that increments a global counter (and also "
    "streams it over UART), builds + flashes it to the board, then PROVES it is running on real "
    "silicon &mdash; PRIMARILY by sampling a live global variable from the RUNNING MCU's RAM over "
    "SWD (this works on EVERY ST-LINK board), and as a best-effort BONUS by reading the ST-LINK "
    "Virtual COM Port &mdash; before hardware-resetting the board. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY STM32CubeIDE (STM32er auto-provisions the MCP itself); (b) **an STM32F407 "
    "board (e.g. STM32F407G-DISC1) IS connected** via ST-LINK &mdash; this demo REQUIRES hardware; "
    "(c) **IMPORTANT BOARD FACT &mdash; READ THIS:** on the STM32F4-Discovery family (including the "
    "STM32F407G-DISC1) the on-board ST-LINK does **NOT** bridge its Virtual COM Port to the MCU's "
    "USART pins the way ST **Nucleo** boards do (Nucleo routes VCP&harr;USART2 on PA2/PA3). So even "
    "though the firmware runs and transmits on USART2, reading the VCP on a Discovery board returns "
    "**EMPTY (bytes=0)** &mdash; this is EXPECTED, NOT a failure. The AUTHORITATIVE on-silicon proof "
    "in this demo is therefore the **live SWD memory read of the counter**, NOT the serial line. "
    "(Capturing real UART on a Discovery would require wiring an external USB-TTL adapter to PA2/PA3 "
    "&mdash; out of scope for this ST-LINK-only demo.) (d) tick ONLY the **Multi-Turn** checkbox "
    "(ACPX is NOT required). Use ONLY chat_agent_stm32er, ONE call per step shaped \"Run STM32er with "
    "action='<action>' and <k>='<v>' ...\". Read each JSON return (INI_SECTION_STM32ER block under "
    "log_excerpt), capture action/ok/returncode/success/project_dir/session_id/stage, and on "
    "ok=false record verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128300; STM32 HIL OBSERVATORY &#9889;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini STM32er &mdash; validate &middot; flash &middot; live SWD memory &middot; VCP serial (bonus)</div></div>. "
    "\n\n"
    "Step 1 (safety preflight &mdash; CONFIRM THE BOARD): \"Run STM32er with action='validate' and "
    "device='STM32F407VG'\". This auto-provisions the MCP if needed and validates the environment "
    "INCLUDING the ST-LINK. From the report capture stlink_connected and device_family_supported. "
    "**If stlink_connected is False, STOP**: skip to the closing banner with a 'NO BOARD' verdict "
    "and tell the user to connect the STM32F407G-DISC1 (this is a hardware demo). Only proceed to "
    "Step 2 when stlink_connected is True. "
    "\n\n"
    "Step 2 (scaffold): \"Run STM32er with action='create_project' and name='tlamatini_hil' and "
    "dest_parent='C:/Temp/stm32' and overwrite='true'\". CAPTURE the **project_dir**. "
    "\n\n"
    "Step 3 (author the firmware &mdash; write main.c): \"Run STM32er with action='write_source' "
    "and project_dir='<project_dir>' and rel_path='Core/Src/main.c' and content='''<CODE>'''\". "
    "For <CODE> author a MINIMAL, COMPILABLE STM32F4 HAL program that declares a file-scope "
    "`volatile uint32_t g_blink_count = 0;`, initialises HAL + the system clock + the on-board LED "
    "GPIO + USART2 (115200 8N1, on PA2/PA3), and in the while(1) loop: increments g_blink_count, "
    "toggles the LED, transmits a single newline-terminated status line of the form "
    "'BOOT tlamatini hil count=<n>' over USART2 with HAL_UART_Transmit, and HAL_Delay(500). "
    "**The counter `g_blink_count` is the proof that matters (read live over SWD in Step 6); the "
    "UART line is best-effort &mdash; it is harmless on a Discovery board and is what a Nucleo board "
    "WOULD echo on its VCP.** Pass it as a TRIPLE-QUOTED content literal (content='''...''') so "
    "newlines and braces survive the parser. Keep it self-contained and buildable against the "
    "scaffold's HAL. "
    "\n\n"
    "Step 4 (compile + LINK): \"Run STM32er with action='build' and project_dir='<project_dir>' and "
    "system='make' and clean_first='true'\". Require returncode=0 (the .elf carries the "
    "g_blink_count symbol the live-memory step reads). If the build fails, capture the diagnostic "
    "and you may stop after the report with 'BUILD FAILED'. "
    "\n\n"
    "Step 5 (flash &mdash; REAL upload over ST-LINK): \"Run STM32er with action='build_and_flash' "
    "and project_dir='<project_dir>'\". The preflight already confirmed the board in Step 1; the "
    "body should show the programmer reporting 'File download complete' / 'Verifying...'. Capture "
    "the verify result. "
    "\n\n"
    "Step 6 (HIL #1 &mdash; PRIMARY PROOF: live SWD memory): \"Run STM32er with action='live_monitor' "
    "and variables='[\\\"g_blink_count\\\"]' and project_dir='<project_dir>' and monitor_seconds='4' "
    "and last_n='8'\". This starts an OpenOCD stream of the RUNNING MCU's RAM, samples the global for "
    "4 seconds, returns the most-recent 8 samples, and stops. Capture the FIRST and LAST g_blink_count "
    "samples and confirm the value is INCREASING &mdash; this is the direct, board-agnostic, "
    "on-silicon proof the while(1) loop is executing (not just that the .hex flashed). THIS is the "
    "authoritative HIL proof for this demo. "
    "\n\n"
    "Step 7 (HIL #2 &mdash; BEST-EFFORT serial VCP, AT MOST ONCE, DO NOT RETRY): optionally read the "
    "ST-LINK VCP a SINGLE time: \"Run STM32er with action='serial_session' and port='<the ST-LINK VCP "
    "port>' and baud='115200' and serial_timeout='5'\" (you MAY first call action='serial_list_ports' "
    "and pick the port flagged stlink_vcp=true). With no `data` set, serial_session connects, READS, "
    "then disconnects. **If the read returns data, capture the 'BOOT tlamatini hil count=' line as a "
    "BONUS. If it returns EMPTY (bytes=0) &mdash; which is the EXPECTED result on the STM32F407G-DISC1, "
    "whose ST-LINK does not route the VCP to the MCU USART &mdash; record 'no VCP route on this board "
    "(Discovery)' and MOVE ON. Call serial_session AT MOST ONCE: DO NOT retry it with longer timeouts, "
    "DO NOT inject newlines, DO NOT fall back to serial_connect/serial_read loops. An empty VCP here "
    "is normal, not a fault, and the live SWD read in Step 6 has already proven the firmware is "
    "alive.** "
    "\n\n"
    "Step 8 (HIL #3 &mdash; reset): \"Run STM32er with action='reset' and project_dir='<project_dir>'\" "
    "to hardware-reset the MCU and leave the board in a clean state. "
    "\n\n"
    "Step 9: render a STATUS SCOREBOARD &mdash; a row of HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'validate: <ok|err>' chip, "
    "a 'build: <ok|err>' chip, a 'flash: <ok|err>' chip, a 'live_mem: <ok|err>' chip (THE key proof), "
    "a 'serial: <ok|n/a>' chip, a 'reset: <ok|err>' chip, and a 'count: <first>&rarr;<last>' chip. "
    "CHIP_BG is #16a34a (green) when ok; #dc2626 (red) on a real error; for the 'serial' chip use "
    "#d97706 (amber) with label 'serial: n/a (no VCP route)' when the read was EXPECTED-empty on this "
    "board (amber is NOT a failure); the 'count' chip is #2563EB (blue). "
    "\n\n"
    "Step 10: render an HTML table with class='exec-report-table' titled "
    "'<strong>STM32 HIL Observatory &mdash; Run Report</strong>' and columns <em>step</em>, "
    "<em>stage</em> (validate|project|build|flash|live_memory|serial|reset), <em>stm32_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (stlink_connected; project_dir; build returncode; "
    "flash verify; g_blink_count first&rarr;last; the captured VCP line OR 'no VCP route on this board'; "
    "reset ok) &mdash; one row per call in execution order, status verbatim from the INI_SECTION_STM32ER "
    "block (do NOT re-classify). Light body cells (background:#ffffff;color:#0f172a; or striped #f1f5f9). "
    "\n\n"
    "Step 11: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; SILICON VERIFIED' (build returncode=0 AND flash verified AND live_memory showed "
    "g_blink_count RISING over SWD &mdash; the serial VCP line is a BONUS and is NOT required for this "
    "verdict), '&#9888;&#65039; NO BOARD' (Step 1 found no ST-LINK connected), or '&#10060; BUILD FAILED' "
    "(build returncode &ne; 0), and underneath a one-line metric 'project: <project_dir> &middot; "
    "build rc: <0> &middot; flash: <verified> &middot; g_blink_count over SWD: <first>&rarr;<last> "
    "&middot; VCP: <\"<boot line>\" | n/a (no VCP route on F4-Discovery)>'. End with END-RESPONSE."
)


def _restore_original_0103_text():
    """Best-effort load of the original prompt-65 text from migration 0103 for the reverse."""
    try:
        m0103 = importlib.import_module("agent.migrations.0103_add_stm32er_demo_prompts")
        return getattr(m0103, "STM32_HIL_OBSERVATORY_DEMO", None)
    except Exception:
        return None


def fix_hil_serial_proof(apps, schema_editor):
    Prompt = apps.get_model("agent", "Prompt")
    Prompt.objects.update_or_create(
        idPrompt=_HIL_PROMPT_ID,
        defaults={"promptName": f"prompt-{_HIL_PROMPT_ID}", "promptContent": STM32_HIL_OBSERVATORY_DEMO_V2},
    )


def revert_hil_serial_proof(apps, schema_editor):
    original = _restore_original_0103_text()
    if not original:
        # 0103 unavailable (e.g. squashed) — leave the corrected text in place rather than wiping it.
        return
    Prompt = apps.get_model("agent", "Prompt")
    Prompt.objects.update_or_create(
        idPrompt=_HIL_PROMPT_ID,
        defaults={"promptName": f"prompt-{_HIL_PROMPT_ID}", "promptContent": original},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0103_add_stm32er_demo_prompts"),
    ]

    operations = [
        migrations.RunPython(fix_hil_serial_proof, revert_hil_serial_proof),
    ]
