# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed three Catalog-of-Prompts demos for **ESP32 firmware programming** through
the wrapped **chat_agent_esp32er** Multi-Turn tool (the PlatformIO Core / `pio`
CLI bridge). They run basic -> high complexity and mirror the STM32er demos
(0103), but built to ESP32er's grain: ESP32er drives the `pio` CLI DIRECTLY (no
MCP server), so "provisioning" means auto-installing PlatformIO Core, the project
is a plain PlatformIO project, and the firmware is Arduino-framework C++:

    66  ESP32 GENESIS         basic   bootstrap (ESP32er DOWNLOADS + installs +
                                      validates PlatformIO Core itself via the
                                      official get-platformio.py) -> validate (full
                                      environment preflight) -> create_project
                                      (esp32dev/arduino) -> write_source (blink
                                      main.cpp) -> build -> list_artifacts. NO
                                      board required (pure provision + build).
    67  ESP32 BLINKY          medium  validate -> create_project -> write_source
                                      (Arduino GPIO-2 blink + Serial prints) ->
                                      build -> list_artifacts -> build_and_upload.
                                      The upload is board-OPTIONAL: ESP32er's
                                      safety preflight refuses it cleanly with
                                      'No serial port detected' if no board is
                                      attached (expected + routable, not a crash).
    68  ESP32 HIL OBSERVATORY  hard   validate (REQUIRES a connected serial port)
                                      -> device_list -> create_project ->
                                      write_source (counter firmware that prints
                                      'BOOT tlamatini esp32 count=<n>' over Serial)
                                      -> build -> build_and_upload (REAL flash over
                                      the onboard USB-serial bootloader) -> monitor
                                      (read the RUNNING board's serial stream and
                                      watch the counter climb). Demo #3 UPLOADS TO
                                      AND OBSERVES THE HARDWARE end-to-end.

ESP32 vs STM32 hardware nuance baked into demo #68: an ESP32 flashes over its
*onboard USB-serial bootloader*, and that SAME USB-serial port carries the
firmware's `Serial.print` output — so unlike the STM32F4-Discovery (whose ST-LINK
VCP is NOT routed to the MCU USART, see 0104), the ESP32's serial monitor reads
the firmware's output natively with NO extra wiring. The serial `monitor` is
therefore the authoritative hardware-in-the-loop proof here.

All three drive ONLY chat_agent_esp32er and remind the user to tick ONLY the
**Multi-Turn** checkbox (chat_agent_esp32er is NOT behind the ACPX/Skill surface,
so ACPX is not required — same as the STM32er 0103, Kalier 0099, Unrealer 0100
demos).

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-65 are occupied (0103
appended the STM32er demos at 63-65); these three APPEND at 66-68 with no shift of
any existing prompt. Reverse deletes 66-68. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Espressif red/amber banner palette (near-black -> ESP red -> warm amber ->
# cream), the same family as the ``.canvas-item.esp32er-agent`` gradient, with a
# text-shadow so the white label stays legible across the bright cream end.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#1A1A1A 0%,#E7352C 38%,#FF8A3D 70%,#FFE2C2 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


ESP32_GENESIS_DEMO = (
    "Tlamatini, run the **ESP32 GENESIS** demo, please &mdash; a basic, end-to-end "
    "showcase of ESP32er's *zero-config self-provisioning* and *safety preflight*, driven "
    "entirely from chat through the wrapped **chat_agent_esp32er** tool: from a clean "
    "machine it DOWNLOADS and installs PlatformIO Core itself, validates the whole build "
    "environment, scaffolds an ESP32 PlatformIO project, AUTHORS a tiny blink sketch, then "
    "compiles + LINKS it to a firmware image and lists the .elf/.bin &mdash; all WITHOUT a "
    "board attached (this is a pure provision + build demo). "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; trust them and go "
    "straight to Step 1): (a) **the user installed ONLY Tlamatini** (plus, for a real "
    "upload later, the board's USB-serial driver) &mdash; you do NOT need to install or "
    "configure PlatformIO, ESP32er downloads PlatformIO Core automatically; (b) NO ESP32 "
    "hardware is needed &mdash; nothing is flashed; (c) tick ONLY the **Multi-Turn** "
    "checkbox before sending (ACPX is NOT required &mdash; chat_agent_esp32er is the ONLY "
    "tool you may use; do NOT use chat_agent_executer / chat_agent_pythonxer / acp_spawn). "
    "Every step is exactly ONE chat_agent_esp32er call shaped \"Run ESP32er with "
    "action='<action>' and <k>='<v>' ...\". After each call read the JSON return (an "
    "INI_SECTION_ESP32ER block under the run's log_excerpt) and capture action / tool / ok / "
    "returncode / success / project_dir / stage plus the body. If a step returns ok=false / "
    "success=false, record it verbatim, DO NOT abort, continue. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#9889; ESP32 GENESIS &#128295;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini ESP32er &mdash; provision &middot; validate &middot; author &middot; compile</div></div>. "
    "\n\n"
    "Step 1 (ZERO-CONFIG provision): call **chat_agent_esp32er** with request "
    "\"Run ESP32er with action='bootstrap'\". This makes ESP32er DOWNLOAD the official "
    "get-platformio.py installer and install PlatformIO Core into a per-user "
    "PLATFORMIO_CORE_DIR (with a `pip install platformio` fallback) &mdash; with NO manual "
    "setup. From the body capture the install action (present / installer-script / "
    "pip-install), the core_dir, and 'overall : OK'. If overall is FAILED, the host likely "
    "has no internet &mdash; skip to the closing banner with a 'PROVISION FAILED' verdict. "
    "\n\n"
    "Step 2 (safety preflight): call **chat_agent_esp32er** with request "
    "\"Run ESP32er with action='validate'\". This validates the environment WITHOUT "
    "building: capture pio_resolvable and (since validate also probes for hardware) the "
    "serial summary (present / esp_like). A missing serial port is FINE here &mdash; this "
    "demo never flashes. "
    "\n\n"
    "Step 3 (scaffold): call **chat_agent_esp32er** with request \"Run ESP32er with "
    "action='create_project' and project_dir='C:/Temp/esp32/tlamatini_genesis' and "
    "board='esp32dev' and framework='arduino'\". This runs `pio project init`; CAPTURE the "
    "**project_dir** &mdash; pass it to every later step. "
    "\n\n"
    "Step 4 (author the firmware &mdash; write src/main.cpp): call **chat_agent_esp32er** with "
    "request \"Run ESP32er with action='write_source' and "
    "project_dir='C:/Temp/esp32/tlamatini_genesis' and rel_path='src/main.cpp' and "
    "content='''<CODE>'''\". For <CODE> author a MINIMAL, COMPILABLE Arduino-framework ESP32 "
    "blink sketch: `#include <Arduino.h>`, a `#define LED_PIN 2`, a setup() that calls "
    "pinMode(LED_PIN, OUTPUT) and Serial.begin(115200), and a loop() that toggles the LED with "
    "digitalWrite + delay(500). Pass it as a TRIPLE-QUOTED content literal (content='''...''') "
    "so the newlines and braces survive the assignment parser. "
    "\n\n"
    "Step 5 (compile + LINK &rarr; firmware): call **chat_agent_esp32er** with request "
    "\"Run ESP32er with action='build' and project_dir='C:/Temp/esp32/tlamatini_genesis'\". "
    "Confirm returncode=0 and that the stdout shows the espressif32 platform compiling and "
    "linking (the 'Linking .pio/build/esp32dev/firmware.elf' line is the proof of the link "
    "stage). NOTE: the FIRST build downloads the espressif32 platform + toolchain (hundreds of "
    "MB) so it can take a few minutes &mdash; that is normal. "
    "\n\n"
    "Step 6 (artifacts): call **chat_agent_esp32er** with request \"Run ESP32er with "
    "action='list_artifacts' and project_dir='C:/Temp/esp32/tlamatini_genesis'\". Capture the "
    "firmware.elf / firmware.bin paths from the body. "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>ESP32 Genesis &mdash; Provision &amp; Build Report</strong>' and columns "
    "<em>step</em>, <em>stage</em> (bootstrap|validate|project|author|build), <em>esp32_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (core_dir for bootstrap; pio_resolvable for "
    "validate; project_dir for create; src/main.cpp written for author; returncode for build; the "
    "firmware paths for list_artifacts) &mdash; one row per call in execution order, status verbatim "
    "from the INI_SECTION_ESP32ER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9), green tint ok, subtle red error. "
    "\n\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; PLATFORMIO PROVISIONED &amp; FIRMWARE BUILT' (bootstrap OK, validate resolved pio, "
    "build returncode=0 and artifacts listed), '&#9888;&#65039; GENESIS PARTIAL' (some steps ok, "
    "some error), or '&#10060; PROVISION FAILED' (bootstrap overall FAILED), and underneath a "
    "one-line metric 'pio: <install action> &middot; core_dir: <...> &middot; project: <project_dir> "
    "&middot; build rc: <0> &middot; artifacts: firmware.elf/.bin'. End with END-RESPONSE."
)


ESP32_BLINKY_DEMO = (
    "Tlamatini, run the **ESP32 BLINKY** demo, please &mdash; a medium-complexity take on the "
    "classic embedded 'hello world', driven entirely from chat through the wrapped "
    "**chat_agent_esp32er** tool: it preflight-validates the environment, scaffolds a PlatformIO "
    "project, AUTHORS an Arduino GPIO-2 blink sketch that also prints over Serial, compiles + "
    "links it, lists the artifacts, then attempts to upload it to an ESP32 board so the onboard "
    "LED blinks. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY Tlamatini &mdash; ESP32er auto-downloads/installs PlatformIO Core itself on "
    "first use, so you NEVER configure tool paths; (b) the build needs NO board; the UPLOAD step "
    "needs an ESP32 board on USB (ESP32 flashes over its onboard USB-serial bootloader &mdash; NO "
    "external JTAG probe) &mdash; BUT ESP32er's safety preflight will REFUSE the upload with 'No "
    "serial port detected' if no board is connected, which is EXPECTED and routable, NOT a crash: "
    "record it verbatim and CONTINUE; (c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT "
    "required). Use ONLY chat_agent_esp32er, ONE call per step shaped \"Run ESP32er with "
    "action='<action>' and <k>='<v>' ...\". Read each JSON return (INI_SECTION_ESP32ER block under "
    "log_excerpt), capture action/tool/ok/returncode/success/project_dir/port/stage, and on "
    "ok=false record verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128161; ESP32 BLINKY &#128161;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini ESP32er &mdash; validate &middot; author &middot; build &middot; upload</div></div>. "
    "\n\n"
    "Step 1 (safety preflight): \"Run ESP32er with action='validate'\" &mdash; capture "
    "pio_resolvable and the serial summary (present / esp_like) as the 'before' baseline (ESP32er "
    "auto-provisions PlatformIO Core as part of this if needed). "
    "\n\n"
    "Step 2 (scaffold): \"Run ESP32er with action='create_project' and "
    "project_dir='C:/Temp/esp32/tlamatini_blinky' and board='esp32dev' and framework='arduino'\". "
    "CAPTURE the **project_dir**. "
    "\n\n"
    "Step 3 (author the firmware &mdash; write src/main.cpp): \"Run ESP32er with "
    "action='write_source' and project_dir='C:/Temp/esp32/tlamatini_blinky' and "
    "rel_path='src/main.cpp' and content='''<CODE>'''\". For <CODE> author a MINIMAL, COMPILABLE "
    "Arduino-framework ESP32 sketch: `#include <Arduino.h>`, `#define LED_PIN 2` (the onboard LED "
    "on most ESP32 DevKitC boards), setup() with pinMode(LED_PIN, OUTPUT) + Serial.begin(115200) + "
    "a 'ESP32 BLINKY starting' banner print, and a loop() that drives the LED HIGH (Serial.println "
    "\"LED ON\"), delay(500), LED LOW (Serial.println \"LED OFF\"), delay(500). Pass it as a "
    "TRIPLE-QUOTED content literal (content='''...''') so newlines and braces survive the parser. "
    "\n\n"
    "Step 4 (compile + LINK): \"Run ESP32er with action='build' and "
    "project_dir='C:/Temp/esp32/tlamatini_blinky'\". Confirm returncode=0 and the link of "
    "firmware.elf/firmware.bin. (First build pulls the espressif32 toolchain &mdash; can take a few "
    "minutes; that is normal.) If returncode is non-zero, capture the compiler diagnostic from "
    "stderr &mdash; routable evidence; you may stop after the report with a 'BUILD FAILED' verdict. "
    "\n\n"
    "Step 5 (artifacts): \"Run ESP32er with action='list_artifacts' and "
    "project_dir='C:/Temp/esp32/tlamatini_blinky'\". Capture the firmware.bin path. "
    "\n\n"
    "Step 6 (upload &mdash; flash over USB-serial): \"Run ESP32er with action='build_and_upload' and "
    "project_dir='C:/Temp/esp32/tlamatini_blinky'\". If a board is connected, the body shows esptool "
    "writing + verifying the firmware over the USB-serial bootloader; if not, ESP32er's preflight "
    "returns ok=false with 'No serial port detected' &mdash; record it verbatim and CONTINUE "
    "(board-absent is the expected soft-fail for this demo). "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>ESP32 Blinky &mdash; Run Report</strong>' and columns <em>step</em>, <em>stage</em> "
    "(validate|project|author|build|upload), <em>esp32_action</em>, <em>status</em> (ok|error), "
    "<em>headline</em> (pio resolved; project_dir; build returncode; firmware.bin path; upload "
    "verify or 'preflight refused: no board') &mdash; one row per call in execution order, status "
    "verbatim from the INI_SECTION_ESP32ER block. Light body cells (background:#ffffff;color:#0f172a; "
    "or striped #f1f5f9); green tint ok, subtle red error. "
    "\n\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; BLINKY LIVE' (build returncode=0 AND upload verified), "
    "'&#9888;&#65039; BUILT, NO BOARD' (build ok but the preflight refused the upload / no board), "
    "or '&#10060; BUILD FAILED' (build returncode &ne; 0), and underneath a one-line metric "
    "'project: <project_dir> &middot; build rc: <0> &middot; upload: <verified|no-board> &middot; "
    "led: GPIO&nbsp;2 @ 500&nbsp;ms'. End with END-RESPONSE."
)


ESP32_HIL_OBSERVATORY_DEMO = (
    "Tlamatini, run the **ESP32 HIL OBSERVATORY** demo, please &mdash; an advanced "
    "**hardware-in-the-loop** showcase that UPLOADS TO A REAL BOARD and OBSERVES it end-to-end, "
    "driven entirely from chat through the wrapped **chat_agent_esp32er** tool: it preflight-"
    "validates that a serial port is connected, scaffolds and AUTHORS firmware that increments a "
    "global counter and streams it over Serial, builds + UPLOADS it to the ESP32, then PROVES it "
    "is running on real silicon by reading the live serial stream from the RUNNING board and "
    "watching the counter climb. "
    "ESP32 hardware note (do not skip): an ESP32 flashes over its **onboard USB-serial "
    "bootloader**, and that SAME USB-serial port carries the firmware's `Serial.print` output "
    "&mdash; so, UNLIKE the STM32F4-Discovery (whose ST-LINK VCP is not routed to the MCU's USART), "
    "the ESP32's serial monitor reads the firmware output natively with NO extra wiring. The "
    "serial monitor is therefore the authoritative HIL proof here. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY Tlamatini + the board's USB-serial driver (ESP32er auto-provisions PlatformIO "
    "Core itself); (b) **an ESP32 board IS connected** over USB and enumerates as a serial port "
    "&mdash; this demo REQUIRES hardware; (c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT "
    "required). Use ONLY chat_agent_esp32er, ONE call per step shaped \"Run ESP32er with "
    "action='<action>' and <k>='<v>' ...\". Read each JSON return (INI_SECTION_ESP32ER block under "
    "log_excerpt), capture action/tool/ok/returncode/success/project_dir/port/stage, and on "
    "ok=false record verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128300; ESP32 HIL OBSERVATORY &#9889;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini ESP32er &mdash; validate &middot; upload &middot; observe live serial</div></div>. "
    "\n\n"
    "Step 1 (safety preflight &mdash; CONFIRM THE BOARD): \"Run ESP32er with action='validate'\". "
    "This auto-provisions PlatformIO Core if needed and validates the environment INCLUDING the "
    "serial port (validate probes for a connected adapter). From the report capture pio_resolvable "
    "and the serial summary (present / esp_like / ports). **If no serial port is present, STOP**: "
    "skip to the closing banner with a 'NO BOARD' verdict and tell the user to connect the ESP32 "
    "over USB (this is a hardware demo). Only proceed to Step 2 when a serial port is present. "
    "\n\n"
    "Step 2 (enumerate ports): \"Run ESP32er with action='device_list'\". From the JSON capture the "
    "connected serial port(s) (e.g. COM5 on Windows) and pick the ESP32's port &mdash; pass it as "
    "**port** to the upload/monitor steps. "
    "\n\n"
    "Step 3 (scaffold): \"Run ESP32er with action='create_project' and "
    "project_dir='C:/Temp/esp32/tlamatini_hil' and board='esp32dev' and framework='arduino'\". "
    "CAPTURE the **project_dir**. "
    "\n\n"
    "Step 4 (author the firmware &mdash; write src/main.cpp): \"Run ESP32er with "
    "action='write_source' and project_dir='C:/Temp/esp32/tlamatini_hil' and "
    "rel_path='src/main.cpp' and content='''<CODE>'''\". For <CODE> author a MINIMAL, COMPILABLE "
    "Arduino-framework ESP32 program that declares a file-scope `uint32_t g_count = 0;`, in setup() "
    "calls Serial.begin(115200) and pinMode(2, OUTPUT), and in loop() increments g_count, toggles "
    "the GPIO-2 LED, prints a single newline-terminated status line of the EXACT form "
    "'BOOT tlamatini esp32 count=<n>' with Serial.println, and delay(500). Pass it as a "
    "TRIPLE-QUOTED content literal (content='''...''') so newlines and braces survive the parser. "
    "\n\n"
    "Step 5 (compile + LINK): \"Run ESP32er with action='build' and "
    "project_dir='C:/Temp/esp32/tlamatini_hil'\". Require returncode=0. (First build pulls the "
    "espressif32 toolchain &mdash; can take a few minutes.) If the build fails, capture the "
    "diagnostic and you may stop after the report with 'BUILD FAILED'. "
    "\n\n"
    "Step 6 (UPLOAD &mdash; REAL flash over USB-serial): \"Run ESP32er with "
    "action='build_and_upload' and project_dir='C:/Temp/esp32/tlamatini_hil' and port='<the port "
    "from Step 2>'\". The preflight already confirmed the board in Step 1; the body should show "
    "esptool 'Writing at 0x...' / 'Hash of data verified' over the USB-serial bootloader. Capture "
    "the verify result &mdash; this is the actual UPLOAD of the program to the ESP32 board. "
    "\n\n"
    "Step 7 (HIL proof &mdash; observe the live serial stream): \"Run ESP32er with action='monitor' "
    "and project_dir='C:/Temp/esp32/tlamatini_hil' and port='<the port from Step 2>' and baud='115200' "
    "and monitor_seconds='6'\". This opens a bounded `pio device monitor`, drains the RUNNING board's "
    "serial output for 6 seconds, then stops. Capture the FIRST and LAST 'BOOT tlamatini esp32 "
    "count=<n>' lines and confirm the count is INCREASING &mdash; direct, on-silicon proof the loop() "
    "is executing on real hardware (not merely that the .bin flashed). "
    "\n\n"
    "Step 8: render a STATUS SCOREBOARD &mdash; a row of HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'validate: <ok|err>' chip, "
    "a 'port: <COMx>' chip, a 'build: <ok|err>' chip, an 'upload: <ok|err>' chip, a "
    "'monitor: <ok|err>' chip (CHIP_BG #16a34a when ok else #dc2626), and a "
    "'count: <first>&rarr;<last>' chip (CHIP_BG #E7352C). "
    "\n\n"
    "Step 9: render an HTML table with class='exec-report-table' titled "
    "'<strong>ESP32 HIL Observatory &mdash; Run Report</strong>' and columns <em>step</em>, "
    "<em>stage</em> (validate|device_list|project|author|build|upload|monitor), <em>esp32_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (serial present; chosen port; project_dir; build "
    "returncode; upload verify; the captured serial count lines first&rarr;last) &mdash; one row per "
    "call in execution order, status verbatim from the INI_SECTION_ESP32ER block (do NOT re-classify). "
    "Light body cells (background:#ffffff;color:#0f172a; or striped #f1f5f9). "
    "\n\n"
    "Step 10: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; SILICON VERIFIED' (build returncode=0 AND upload AND monitor all ok &mdash; the counter "
    "was observed RISING over the live serial stream), '&#9888;&#65039; NO BOARD' (Step 1 found no "
    "serial port connected), or '&#10060; BUILD FAILED' (build returncode &ne; 0), and underneath a "
    "one-line metric 'project: <project_dir> &middot; port: <COMx> &middot; build rc: <0> &middot; "
    "upload: <verified> &middot; serial count: <first>&rarr;<last>'. End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (66, ESP32_GENESIS_DEMO),
    (67, ESP32_BLINKY_DEMO),
    (68, ESP32_HIL_OBSERVATORY_DEMO),
)


def add_esp32er_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_esp32er_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0106_add_chat_agent_esp32er_tool'),
    ]

    operations = [
        migrations.RunPython(add_esp32er_demo_prompts, remove_esp32er_demo_prompts),
    ]
