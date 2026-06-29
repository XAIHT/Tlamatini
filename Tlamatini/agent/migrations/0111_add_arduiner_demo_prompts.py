# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed three Catalog-of-Prompts demos for **Arduino firmware programming** through
the wrapped **chat_agent_arduiner** Multi-Turn tool (the Arduino CLI / `arduino-cli`
bridge). They run basic -> high complexity and mirror the ESP32er demos (0107) and
STM32er demos (0103), but built to Arduiner's grain: Arduiner drives the
`arduino-cli` binary DIRECTLY (no MCP server), the microcontroller is chosen by the
**FQBN** (e.g. arduino:avr:uno), "provisioning" means auto-downloading the
arduino-cli binary AND auto-installing the board's core, the project is a plain
Arduino sketch scaffolded from the bundled **ArduinoTemplateProject**, and the
firmware is Arduino-core C++ (.ino):

    70  ARDUINO GENESIS        basic   bootstrap (Arduiner DOWNLOADS + installs +
                                       validates the arduino-cli binary itself) ->
                                       validate -> create_project (from the bundled
                                       ArduinoTemplateProject) -> write_source (blink
                                       .ino) -> build (auto-installs arduino:avr) ->
                                       list_artifacts. NO board required.
    71  ARDUINO BLINKY         medium  validate -> create_project -> write_source
                                       (pin-13 blink + Serial prints) -> build ->
                                       list_artifacts -> build_and_upload. The upload
                                       is board-OPTIONAL: Arduiner's safety preflight
                                       refuses it cleanly with 'No serial port
                                       detected' if no board is attached (expected +
                                       routable, not a crash).
    72  ARDUINO HIL OBSERVATORY  hard  validate (REQUIRES a connected serial port)
                                       -> device_list -> create_project ->
                                       write_source (counter firmware that prints
                                       'BOOT tlamatini arduino count=<n>' over Serial)
                                       -> build -> build_and_upload (REAL flash over
                                       USB-serial) -> monitor (read the RUNNING
                                       board's serial stream and watch the counter
                                       climb). Demo #3 UPLOADS TO AND OBSERVES THE
                                       HARDWARE end-to-end.

Arduino hardware nuance baked into demo #72: a classic Arduino (Uno/Nano/Mega)
flashes over its USB-serial bridge (ATmega16U2 / CH340 / FTDI), and that SAME port
carries the firmware's `Serial.print` output — so, like the ESP32 (and unlike the
STM32F4-Discovery whose ST-LINK VCP is not routed to the MCU USART, see 0104), the
serial monitor reads the firmware output natively with NO extra wiring. The serial
`monitor` is therefore the authoritative hardware-in-the-loop proof here.

All three drive ONLY chat_agent_arduiner and remind the user to tick ONLY the
**Multi-Turn** checkbox (chat_agent_arduiner is NOT behind the ACPX/Skill surface,
so ACPX is not required — same as the ESP32er 0107, STM32er 0103, Kalier 0099 demos).

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog must
stay a contiguous, gap-free 'prompt-1..N'. Slots 1-69 are occupied (0108 appended
the flow-making demo at 69); these three APPEND at 70-72 with no shift of any
existing prompt. Reverse deletes 70-72. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# Arduino teal banner palette (deep teal -> Arduino teal -> bright cyan -> pale aqua),
# the same family as the ``.canvas-item.arduiner-agent`` gradient, with a text-shadow
# so the white label stays legible across the bright aqua end.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#00363A 0%,#008184 38%,#00C4CC 70%,#C8F2F0 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


ARDUINO_GENESIS_DEMO = (
    "Tlamatini, run the **ARDUINO GENESIS** demo, please &mdash; a basic, end-to-end showcase of "
    "Arduiner's *zero-config self-provisioning*, *auto-core-install* and *safety preflight*, driven "
    "entirely from chat through the wrapped **chat_agent_arduiner** tool: from a clean machine it "
    "DOWNLOADS and installs the arduino-cli binary itself, validates the build environment, scaffolds "
    "an Arduino sketch from the bundled ArduinoTemplateProject, AUTHORS a tiny blink .ino, then "
    "compiles + LINKS it to a firmware image (auto-installing the AVR core on the way) and lists the "
    ".hex/.elf &mdash; all WITHOUT a board attached (a pure provision + build demo). "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; trust them and go straight to "
    "Step 1): (a) **the user installed ONLY Tlamatini** (plus, for a real upload later, the board's "
    "USB-serial driver) &mdash; you do NOT install or configure arduino-cli, Arduiner downloads it "
    "automatically; (b) NO Arduino hardware is needed &mdash; nothing is flashed; (c) tick ONLY the "
    "**Multi-Turn** checkbox before sending (ACPX is NOT required &mdash; chat_agent_arduiner is the "
    "ONLY tool you may use; do NOT use chat_agent_executer / chat_agent_pythonxer / acp_spawn). Every "
    "step is exactly ONE chat_agent_arduiner call shaped \"Run Arduiner with action='<action>' and "
    "<k>='<v>' ...\". After each call read the JSON return (an INI_SECTION_ARDUINER block under the "
    "run's log_excerpt) and capture action / tool / ok / returncode / success / fqbn / sketch_path / "
    "stage plus the body. If a step returns ok=false / success=false, record it verbatim, DO NOT "
    "abort, continue. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128268; ARDUINO GENESIS &#128295;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Arduiner &mdash; provision &middot; validate &middot; author &middot; compile</div></div>. "
    "\n\n"
    "Step 1 (ZERO-CONFIG provision): call **chat_agent_arduiner** with request "
    "\"Run Arduiner with action='bootstrap'\". This makes Arduiner DOWNLOAD the official arduino-cli "
    "release binary into a per-user install dir and run config init + core update-index &mdash; with "
    "NO manual setup. From the body capture the install action (present / download-extract), the "
    "install_dir, and 'overall : OK'. If overall is FAILED, the host likely has no internet &mdash; "
    "skip to the closing banner with a 'PROVISION FAILED' verdict. "
    "\n\n"
    "Step 2 (safety preflight): call **chat_agent_arduiner** with request "
    "\"Run Arduiner with action='validate'\". This validates the environment WITHOUT building: "
    "capture arduino_cli_resolvable and (since validate also probes for hardware) the serial summary "
    "(present / arduino_like). A missing serial port is FINE here &mdash; this demo never flashes. "
    "\n\n"
    "Step 3 (scaffold from the template): call **chat_agent_arduiner** with request \"Run Arduiner "
    "with action='create_project' and sketch_path='C:/Temp/arduino/tlamatini_genesis' and "
    "fqbn='arduino:avr:uno'\". This copies the bundled ArduinoTemplateProject, renames its .ino to "
    "the folder name, and stamps the FQBN into sketch.yaml; CAPTURE the **sketch_path** &mdash; pass "
    "it to every later step. "
    "\n\n"
    "Step 4 (author the firmware &mdash; overwrite the .ino): call **chat_agent_arduiner** with "
    "request \"Run Arduiner with action='write_source' and "
    "sketch_path='C:/Temp/arduino/tlamatini_genesis' and rel_path='tlamatini_genesis.ino' and "
    "content='''<CODE>'''\". For <CODE> author a MINIMAL, COMPILABLE Arduino-core blink sketch: a "
    "`setup()` that calls pinMode(LED_BUILTIN, OUTPUT) and Serial.begin(115200), and a `loop()` that "
    "toggles the LED with digitalWrite + delay(500). Pass it as a TRIPLE-QUOTED content literal "
    "(content='''...''') so the newlines and braces survive the assignment parser. (NOTE: arduino-cli "
    "requires the primary .ino basename to equal the sketch folder name &mdash; hence "
    "'tlamatini_genesis.ino'.) "
    "\n\n"
    "Step 5 (compile + LINK &rarr; firmware): call **chat_agent_arduiner** with request \"Run Arduiner "
    "with action='build' and sketch_path='C:/Temp/arduino/tlamatini_genesis' and "
    "fqbn='arduino:avr:uno'\". Arduiner first AUTO-INSTALLS the arduino:avr core (arduino-cli does not "
    "auto-install platforms on compile), then compiles. Confirm returncode=0 and that the stdout shows "
    "'Sketch uses ... program storage space'. NOTE: the first core install + compile downloads the AVR "
    "toolchain so it can take a minute &mdash; that is normal. "
    "\n\n"
    "Step 6 (artifacts): call **chat_agent_arduiner** with request \"Run Arduiner with "
    "action='list_artifacts' and sketch_path='C:/Temp/arduino/tlamatini_genesis'\". Capture the "
    ".hex / .elf paths from the body (build is run with --export-binaries, so they land under "
    "<sketch>/build/). "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>Arduino Genesis &mdash; Provision &amp; Build Report</strong>' and columns "
    "<em>step</em>, <em>stage</em> (bootstrap|validate|project|author|build), <em>arduiner_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (install_dir for bootstrap; arduino_cli_resolvable "
    "for validate; sketch_path for create; .ino written for author; returncode for build; the firmware "
    "paths for list_artifacts) &mdash; one row per call in execution order, status verbatim from the "
    "INI_SECTION_ARDUINER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9), green tint ok, subtle red error. "
    "\n\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; ARDUINO-CLI PROVISIONED &amp; FIRMWARE BUILT' (bootstrap OK, validate resolved the CLI, "
    "build returncode=0 and artifacts listed), '&#9888;&#65039; GENESIS PARTIAL' (some steps ok, some "
    "error), or '&#10060; PROVISION FAILED' (bootstrap overall FAILED), and underneath a one-line "
    "metric 'arduino-cli: <install action> &middot; install_dir: <...> &middot; sketch: <sketch_path> "
    "&middot; build rc: <0> &middot; artifacts: .hex/.elf'. End with END-RESPONSE."
)


ARDUINO_BLINKY_DEMO = (
    "Tlamatini, run the **ARDUINO BLINKY** demo, please &mdash; a medium-complexity take on the "
    "classic embedded 'hello world', driven entirely from chat through the wrapped "
    "**chat_agent_arduiner** tool: it preflight-validates the environment, scaffolds a sketch from "
    "the bundled ArduinoTemplateProject, AUTHORS a pin-13 blink .ino that also prints over Serial, "
    "compiles + links it (auto-installing the AVR core), lists the artifacts, then attempts to upload "
    "it to an Arduino board so the on-board LED blinks. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY Tlamatini &mdash; Arduiner auto-downloads/installs arduino-cli itself on first "
    "use, so you NEVER configure tool paths; (b) the build needs NO board; the UPLOAD step needs an "
    "Arduino board on USB (it flashes over the board's USB-serial bridge &mdash; NO external "
    "programmer for the common path) &mdash; BUT Arduiner's safety preflight will REFUSE the upload "
    "with 'No serial port detected' if no board is connected, which is EXPECTED and routable, NOT a "
    "crash: record it verbatim and CONTINUE; (c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT "
    "required). Use ONLY chat_agent_arduiner, ONE call per step shaped \"Run Arduiner with "
    "action='<action>' and <k>='<v>' ...\". Read each JSON return (INI_SECTION_ARDUINER block under "
    "log_excerpt), capture action/tool/ok/returncode/success/fqbn/sketch_path/port/stage, and on "
    "ok=false record verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128161; ARDUINO BLINKY &#128161;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Arduiner &mdash; validate &middot; author &middot; build &middot; upload</div></div>. "
    "\n\n"
    "Step 1 (safety preflight): \"Run Arduiner with action='validate'\" &mdash; capture "
    "arduino_cli_resolvable and the serial summary (present / arduino_like) as the 'before' baseline "
    "(Arduiner auto-provisions arduino-cli as part of this if needed). "
    "\n\n"
    "Step 2 (scaffold): \"Run Arduiner with action='create_project' and "
    "sketch_path='C:/Temp/arduino/tlamatini_blinky' and fqbn='arduino:avr:uno'\". CAPTURE the "
    "**sketch_path**. "
    "\n\n"
    "Step 3 (author the firmware &mdash; overwrite the .ino): \"Run Arduiner with "
    "action='write_source' and sketch_path='C:/Temp/arduino/tlamatini_blinky' and "
    "rel_path='tlamatini_blinky.ino' and content='''<CODE>'''\". For <CODE> author a MINIMAL, "
    "COMPILABLE Arduino-core sketch: setup() with pinMode(LED_BUILTIN, OUTPUT) + Serial.begin(115200) "
    "+ a 'ARDUINO BLINKY starting' banner print, and a loop() that drives the LED HIGH "
    "(Serial.println \"LED ON\"), delay(500), LED LOW (Serial.println \"LED OFF\"), delay(500). Pass "
    "it as a TRIPLE-QUOTED content literal (content='''...''') so newlines and braces survive the "
    "parser. (arduino-cli requires the .ino basename to equal the folder name &mdash; hence "
    "'tlamatini_blinky.ino'.) "
    "\n\n"
    "Step 4 (compile + LINK): \"Run Arduiner with action='build' and "
    "sketch_path='C:/Temp/arduino/tlamatini_blinky' and fqbn='arduino:avr:uno'\". Arduiner "
    "auto-installs the arduino:avr core first, then compiles. Confirm returncode=0 and the 'Sketch "
    "uses ... program storage space' line. (First core install + build pulls the AVR toolchain &mdash; "
    "can take a minute.) If returncode is non-zero, capture the compiler diagnostic from stderr "
    "&mdash; routable evidence; you may stop after the report with a 'BUILD FAILED' verdict. "
    "\n\n"
    "Step 5 (artifacts): \"Run Arduiner with action='list_artifacts' and "
    "sketch_path='C:/Temp/arduino/tlamatini_blinky'\". Capture the .hex path. "
    "\n\n"
    "Step 6 (upload &mdash; flash over USB-serial): \"Run Arduiner with action='build_and_upload' and "
    "sketch_path='C:/Temp/arduino/tlamatini_blinky' and fqbn='arduino:avr:uno'\". If a board is "
    "connected, the body shows avrdude writing + verifying the firmware over the USB-serial bridge; if "
    "not, Arduiner's preflight returns ok=false with 'No serial port detected' &mdash; record it "
    "verbatim and CONTINUE (board-absent is the expected soft-fail for this demo). "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>Arduino Blinky &mdash; Run Report</strong>' and columns <em>step</em>, <em>stage</em> "
    "(validate|project|author|build|upload), <em>arduiner_action</em>, <em>status</em> (ok|error), "
    "<em>headline</em> (cli resolved; sketch_path; build returncode; .hex path; upload verify or "
    "'preflight refused: no board') &mdash; one row per call in execution order, status verbatim from "
    "the INI_SECTION_ARDUINER block. Light body cells (background:#ffffff;color:#0f172a; or striped "
    "#f1f5f9); green tint ok, subtle red error. "
    "\n\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; BLINKY LIVE' (build returncode=0 AND upload verified), "
    "'&#9888;&#65039; BUILT, NO BOARD' (build ok but the preflight refused the upload / no board), or "
    "'&#10060; BUILD FAILED' (build returncode &ne; 0), and underneath a one-line metric "
    "'sketch: <sketch_path> &middot; build rc: <0> &middot; upload: <verified|no-board> &middot; led: "
    "pin&nbsp;13 @ 500&nbsp;ms'. End with END-RESPONSE."
)


ARDUINO_HIL_OBSERVATORY_DEMO = (
    "Tlamatini, run the **ARDUINO HIL OBSERVATORY** demo, please &mdash; an advanced "
    "**hardware-in-the-loop** showcase that UPLOADS TO A REAL BOARD and OBSERVES it end-to-end, "
    "driven entirely from chat through the wrapped **chat_agent_arduiner** tool: it preflight-"
    "validates that a serial port is connected, scaffolds and AUTHORS firmware that increments a "
    "global counter and streams it over Serial, builds + UPLOADS it to the Arduino, then PROVES it is "
    "running on real silicon by reading the live serial stream from the RUNNING board and watching "
    "the counter climb. "
    "Arduino hardware note (do not skip): a classic Arduino (Uno/Nano/Mega) flashes over its "
    "**USB-serial bridge** (ATmega16U2 / CH340 / FTDI), and that SAME USB-serial port carries the "
    "firmware's `Serial.print` output &mdash; so, like the ESP32 (and UNLIKE the STM32F4-Discovery "
    "whose ST-LINK VCP is not routed to the MCU's USART), the serial monitor reads the firmware "
    "output natively with NO extra wiring. The serial monitor is therefore the authoritative HIL "
    "proof here. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY Tlamatini + the board's USB-serial driver (Arduiner auto-provisions arduino-cli "
    "itself); (b) **an Arduino board IS connected** over USB and enumerates as a serial port &mdash; "
    "this demo REQUIRES hardware; (c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT required). "
    "Use ONLY chat_agent_arduiner, ONE call per step shaped \"Run Arduiner with action='<action>' and "
    "<k>='<v>' ...\". Read each JSON return (INI_SECTION_ARDUINER block under log_excerpt), capture "
    "action/tool/ok/returncode/success/fqbn/sketch_path/port/stage, and on ok=false record verbatim "
    "and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128300; ARDUINO HIL OBSERVATORY &#9889;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini Arduiner &mdash; validate &middot; upload &middot; observe live serial</div></div>. "
    "\n\n"
    "Step 1 (safety preflight &mdash; CONFIRM THE BOARD): \"Run Arduiner with action='validate'\". "
    "This auto-provisions arduino-cli if needed and validates the environment INCLUDING the serial "
    "port (validate probes for a connected adapter). From the report capture arduino_cli_resolvable "
    "and the serial summary (present / arduino_like / ports / matched FQBN). **If no serial port is "
    "present, STOP**: skip to the closing banner with a 'NO BOARD' verdict and tell the user to "
    "connect the Arduino over USB (this is a hardware demo). Only proceed to Step 2 when a serial port "
    "is present. "
    "\n\n"
    "Step 2 (enumerate ports + discover the FQBN): \"Run Arduiner with action='device_list'\". From "
    "the JSON capture the connected serial port(s) (e.g. COM3 on Windows) and any matching_boards "
    "FQBN. Pick the Arduino's port &mdash; pass it as **port** to the upload/monitor steps &mdash; and, "
    "if a matching FQBN was reported, prefer it; else use **fqbn='arduino:avr:uno'**. "
    "\n\n"
    "Step 3 (scaffold): \"Run Arduiner with action='create_project' and "
    "sketch_path='C:/Temp/arduino/tlamatini_hil' and fqbn='<the FQBN from Step 2>'\". CAPTURE the "
    "**sketch_path**. "
    "\n\n"
    "Step 4 (author the firmware &mdash; overwrite the .ino): \"Run Arduiner with "
    "action='write_source' and sketch_path='C:/Temp/arduino/tlamatini_hil' and "
    "rel_path='tlamatini_hil.ino' and content='''<CODE>'''\". For <CODE> author a MINIMAL, COMPILABLE "
    "Arduino-core program that declares a file-scope `unsigned long g_count = 0;`, in setup() calls "
    "Serial.begin(115200) and pinMode(LED_BUILTIN, OUTPUT), and in loop() increments g_count, toggles "
    "the LED, prints a single newline-terminated status line of the EXACT form "
    "'BOOT tlamatini arduino count=<n>' with Serial.println, and delay(500). Pass it as a "
    "TRIPLE-QUOTED content literal (content='''...''') so newlines and braces survive the parser. "
    "(arduino-cli requires the .ino basename to equal the folder name &mdash; hence "
    "'tlamatini_hil.ino'.) "
    "\n\n"
    "Step 5 (compile + LINK): \"Run Arduiner with action='build' and "
    "sketch_path='C:/Temp/arduino/tlamatini_hil' and fqbn='<the FQBN from Step 2>'\". Arduiner "
    "auto-installs the board's core first. Require returncode=0. (First core install + build pulls "
    "the toolchain &mdash; can take a minute.) If the build fails, capture the diagnostic and you may "
    "stop after the report with 'BUILD FAILED'. "
    "\n\n"
    "Step 6 (UPLOAD &mdash; REAL flash over USB-serial): \"Run Arduiner with "
    "action='build_and_upload' and sketch_path='C:/Temp/arduino/tlamatini_hil' and fqbn='<the FQBN "
    "from Step 2>' and port='<the port from Step 2>'\". The preflight already confirmed the board in "
    "Step 1; the body should show avrdude 'writing' / 'reading on-chip flash data' / 'verified' over "
    "the USB-serial bridge. Capture the verify result &mdash; this is the actual UPLOAD of the program "
    "to the Arduino board. "
    "\n\n"
    "Step 7 (HIL proof &mdash; observe the live serial stream): \"Run Arduiner with action='monitor' "
    "and sketch_path='C:/Temp/arduino/tlamatini_hil' and port='<the port from Step 2>' and "
    "baud='115200' and monitor_seconds='6'\". This opens a bounded `arduino-cli monitor "
    "--config baudrate=115200`, drains the RUNNING board's serial output for 6 seconds, then stops. "
    "Capture the FIRST and LAST 'BOOT tlamatini arduino count=<n>' lines and confirm the count is "
    "INCREASING &mdash; direct, on-silicon proof the loop() is executing on real hardware (not merely "
    "that the .hex flashed). "
    "\n\n"
    "Step 8: render a STATUS SCOREBOARD &mdash; a row of HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'validate: <ok|err>' chip, a "
    "'port: <COMx>' chip, a 'build: <ok|err>' chip, an 'upload: <ok|err>' chip, a 'monitor: <ok|err>' "
    "chip (CHIP_BG #16a34a when ok else #dc2626), and a 'count: <first>&rarr;<last>' chip "
    "(CHIP_BG #008184). "
    "\n\n"
    "Step 9: render an HTML table with class='exec-report-table' titled "
    "'<strong>Arduino HIL Observatory &mdash; Run Report</strong>' and columns <em>step</em>, "
    "<em>stage</em> (validate|device_list|project|author|build|upload|monitor), <em>arduiner_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (serial present; chosen port; sketch_path; build "
    "returncode; upload verify; the captured serial count lines first&rarr;last) &mdash; one row per "
    "call in execution order, status verbatim from the INI_SECTION_ARDUINER block (do NOT re-classify). "
    "Light body cells (background:#ffffff;color:#0f172a; or striped #f1f5f9). "
    "\n\n"
    "Step 10: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; SILICON VERIFIED' (build returncode=0 AND upload AND monitor all ok &mdash; the counter "
    "was observed RISING over the live serial stream), '&#9888;&#65039; NO BOARD' (Step 1 found no "
    "serial port connected), or '&#10060; BUILD FAILED' (build returncode &ne; 0), and underneath a "
    "one-line metric 'sketch: <sketch_path> &middot; port: <COMx> &middot; build rc: <0> &middot; "
    "upload: <verified> &middot; serial count: <first>&rarr;<last>'. End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (70, ARDUINO_GENESIS_DEMO),
    (71, ARDUINO_BLINKY_DEMO),
    (72, ARDUINO_HIL_OBSERVATORY_DEMO),
)


def add_arduiner_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_arduiner_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0110_add_chat_agent_arduiner_tool'),
    ]

    operations = [
        migrations.RunPython(add_arduiner_demo_prompts, remove_arduiner_demo_prompts),
    ]
