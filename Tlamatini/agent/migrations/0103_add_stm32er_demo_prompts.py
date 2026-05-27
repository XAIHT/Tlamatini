"""
Seed three Catalog-of-Prompts demos for **STM32F firmware programming** through
the wrapped **chat_agent_stm32er** Multi-Turn tool (the STM32 Template Project
MCP bridge). They run basic -> high complexity and showcase STM32er's full,
zero-config, fail-safe behavior:

    63  STM32 GENESIS         basic   bootstrap (STM32er DOWNLOADS + installs +
                                      validates the MCP itself) -> validate (full
                                      environment preflight) -> create_project ->
                                      build -> list_artifacts. NO board required.
    64  STM32 BLINKY          medium  validate -> create_project -> write_source
                                      (HAL GPIO blink main.c) -> build ->
                                      list_artifacts -> build_and_flash. The flash
                                      is board-OPTIONAL: the safety preflight
                                      refuses it cleanly if no ST-LINK is present.
    65  STM32 HIL OBSERVATORY  hard   validate (REQUIRES a connected board) ->
                                      create_project -> write_source (counter+UART
                                      firmware) -> build -> build_and_flash (REAL
                                      upload+verify) -> serial_session (VCP boot
                                      banner) -> live_monitor (sample g_blink_count
                                      from the RUNNING MCU over SWD) -> reset.
                                      Demo #3 USES THE HARDWARE end-to-end.

What changed vs. the first cut of these prompts: they now lead with STM32er's
**zero-config self-provisioning** (action='bootstrap' downloads the MCP from its
git repo and pip-installs/validates it — the user installs ONLY STM32CubeIDE) and
its **safety preflight** (action='validate' + the automatic pre-build/pre-flash
gate that validates the arm-none-eabi-gcc toolchain / STM32CubeIDE / programmer /
ST-LINK driver + probe / target device family, and REFUSES rather than producing
or flashing mis-targeted firmware). Compile-only actions need NO board; hardware
actions (flash/serial/SWD) require a positively-confirmed ST-LINK — so demo 63/64
run boardless and demo 65 drives a real STM32F407G-DISC1.

All three drive ONLY chat_agent_stm32er and remind the user to tick ONLY the
**Multi-Turn** checkbox (chat_agent_stm32er is NOT behind the ACPX/Skill surface,
so ACPX is not required — same as the Kalier 0099 and Unrealer 0100 demos).

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog
must stay a contiguous, gap-free 'prompt-1..N'. Slots 1-62 are occupied (0100
appended the Unreal demos at 60-62); these three APPEND at 63-65 with no shift of
any existing prompt. Reverse deletes 63-65. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# ST-blue banner palette (deep navy -> ST royal blue -> cyan), the same family as
# the ``.canvas-item.stm32er-agent`` gradient, with a text-shadow so the white
# label stays legible across the bright cyan end.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#061029 0%,#0B3A8F 40%,#1E63FF 72%,#22D3EE 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.45);'>"
)


STM32_GENESIS_DEMO = (
    "Tlamatini, run the **STM32 GENESIS** demo, please &mdash; a basic, end-to-end "
    "showcase of STM32er's *zero-config self-provisioning* and *safety preflight*, "
    "driven entirely from chat through the wrapped **chat_agent_stm32er** tool: from a "
    "clean machine it DOWNLOADS and installs the STM32 Template Project MCP itself, "
    "validates the whole build environment, scaffolds an STM32F4 project, then compiles "
    "+ LINKS it to a .elf and lists the .elf/.hex/.bin &mdash; all WITHOUT a board "
    "attached (this is a pure provision + build demo). "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; trust them and go "
    "straight to Step 1): (a) **the user installed ONLY STM32CubeIDE** (it bundles the "
    "GNU Arm toolchain + ST-LINK driver) &mdash; you do NOT need to install or configure "
    "the MCP server, STM32er downloads it automatically; (b) NO STM32 hardware is needed "
    "&mdash; nothing is flashed; (c) tick ONLY the **Multi-Turn** checkbox before sending "
    "(ACPX is NOT required &mdash; chat_agent_stm32er is the ONLY tool you may use; do NOT "
    "use chat_agent_executer / chat_agent_pythonxer / acp_spawn). "
    "Every step is exactly ONE chat_agent_stm32er call shaped \"Run STM32er with "
    "action='<action>' and <k>='<v>' ...\". After each call read the JSON return (an "
    "INI_SECTION_STM32ER block under the run's log_excerpt) and capture action / ok / "
    "returncode / success / project_dir / stage plus the body. If a step returns "
    "ok=false / success=false, record it verbatim, DO NOT abort, continue. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#9881;&#65039; STM32 GENESIS &#128295;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini STM32er &mdash; provision &middot; validate &middot; compile &middot; link</div></div>. "
    "\n\n"
    "Step 1 (ZERO-CONFIG provision): call **chat_agent_stm32er** with request "
    "\"Run STM32er with action='bootstrap'\". This makes STM32er DOWNLOAD the STM32 "
    "Template Project MCP from its git repo into a per-user cache, pip-install its deps "
    "(mcp, pyserial) if missing, and validate &mdash; with NO manual server setup. From "
    "the body capture the download action (cloned / present), deps (already-installed / "
    "pip-install), the install_dir, and 'overall : OK'. If overall is FAILED, the host "
    "likely has no internet / git &mdash; skip to the closing banner with a 'PROVISION "
    "FAILED' verdict. "
    "\n\n"
    "Step 2 (safety preflight): call **chat_agent_stm32er** with request "
    "\"Run STM32er with action='validate'\". This validates the environment WITHOUT "
    "building: capture each check &mdash; arm_none_eabi_gcc, stm32cubeide, make, cmake, "
    "programmer_cli, device_family_supported (and the discovered arm-none-eabi-gcc path). "
    "If arm_none_eabi_gcc is False, STM32CubeIDE is not installed/discoverable &mdash; "
    "note it and continue to the report. "
    "\n\n"
    "Step 3 (scaffold): call **chat_agent_stm32er** with request \"Run STM32er with "
    "action='create_project' and name='tlamatini_genesis' and dest_parent='C:/Temp/stm32' "
    "and overwrite='true'\". CAPTURE the **project_dir** &mdash; pass it to every later step. "
    "\n\n"
    "Step 4 (compile + LINK &rarr; .elf): call **chat_agent_stm32er** with request "
    "\"Run STM32er with action='build' and project_dir='<the project_dir from Step 3>' and "
    "system='make' and clean_first='true'\". Confirm returncode=0 and that the stdout shows "
    "arm-none-eabi-gcc compiling objects and linking firmware (the -T ...FLASH.ld linker "
    "script line is the proof of the link stage). "
    "\n\n"
    "Step 5 (artifacts): call **chat_agent_stm32er** with request \"Run STM32er with "
    "action='list_artifacts' and project_dir='<project_dir>'\". Capture the .elf / .hex / "
    ".bin paths from the artifacts map. "
    "\n\n"
    "Step 6: render an HTML table with class='exec-report-table' titled "
    "'<strong>STM32 Genesis &mdash; Provision &amp; Build Report</strong>' and columns "
    "<em>step</em>, <em>stage</em> (bootstrap|validate|project|build), <em>stm32_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (install_dir for bootstrap; the gcc path "
    "for validate; project_dir for create; returncode for build; the artifact paths for "
    "list_artifacts) &mdash; one row per call in execution order, status verbatim from the "
    "INI_SECTION_STM32ER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9), green tint ok, subtle red error. "
    "\n\n"
    "Step 7: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; TOOLCHAIN PROVISIONED &amp; FIRMWARE BUILT' (bootstrap OK, validate found the "
    "compiler, build returncode=0 and artifacts listed), '&#9888;&#65039; GENESIS PARTIAL' "
    "(some steps ok, some error), or '&#10060; PROVISION FAILED' (bootstrap overall FAILED), "
    "and underneath a one-line metric 'mcp: <download action> &middot; gcc: <...arm-none-eabi-gcc> "
    "&middot; project: <project_dir> &middot; build rc: <0> &middot; artifacts: .elf/.hex/.bin'. "
    "End with END-RESPONSE."
)


STM32_BLINKY_DEMO = (
    "Tlamatini, run the **STM32 BLINKY** demo, please &mdash; a medium-complexity take on the "
    "classic embedded 'hello world', driven entirely from chat through the wrapped "
    "**chat_agent_stm32er** tool: it preflight-validates the environment, scaffolds a project, "
    "AUTHORS a HAL GPIO blink main.c, compiles + links it, lists the artifacts, then attempts "
    "to upload it to an STM32F4 board over ST-LINK so the on-board LED blinks. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY STM32CubeIDE &mdash; STM32er auto-downloads/installs the MCP itself on first "
    "use, so you NEVER configure server paths; (b) the build needs NO board; the FLASH step "
    "needs an STM32F4 board (e.g. an STM32F407G-DISC1) on ST-LINK &mdash; BUT STM32er's safety "
    "preflight will REFUSE the flash with 'No ST-LINK probe detected' if no board is connected, "
    "which is EXPECTED and routable, NOT a crash: record it verbatim and CONTINUE; (c) tick ONLY "
    "the **Multi-Turn** checkbox (ACPX is NOT required). Use ONLY chat_agent_stm32er, ONE call "
    "per step shaped \"Run STM32er with action='<action>' and <k>='<v>' ...\". Read each JSON "
    "return (INI_SECTION_STM32ER block under log_excerpt), capture "
    "action/ok/returncode/success/project_dir/stage, and on ok=false record verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128161; STM32 BLINKY &#128161;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini STM32er &mdash; validate &middot; author &middot; build &middot; flash</div></div>. "
    "\n\n"
    "Step 1 (safety preflight): \"Run STM32er with action='validate'\" &mdash; capture "
    "arm_none_eabi_gcc / make / programmer_cli / device_family_supported and the discovered gcc "
    "path as the 'before' baseline (STM32er auto-provisions the MCP as part of this if needed). "
    "\n\n"
    "Step 2 (scaffold): \"Run STM32er with action='create_project' and name='tlamatini_blinky' "
    "and dest_parent='C:/Temp/stm32' and overwrite='true'\". CAPTURE the **project_dir**. "
    "\n\n"
    "Step 3 (author the firmware &mdash; write main.c): \"Run STM32er with action='write_source' "
    "and project_dir='<project_dir>' and rel_path='Core/Src/main.c' and content='''<CODE>'''\". "
    "For <CODE> author a MINIMAL, COMPILABLE STM32F4 HAL blink main.c that includes the HAL "
    "header, calls HAL_Init() + the project's SystemClock_Config(), enables the GPIO port clock, "
    "configures the on-board LED pin(s) (e.g. PD12&ndash;PD15 on an F407 Discovery) as push-pull "
    "outputs, and in the while(1) loop toggles them and calls HAL_Delay(500). Pass it as a "
    "TRIPLE-QUOTED content literal (content='''...''') so the newlines and braces survive the "
    "assignment parser. Keep it self-contained and buildable against the scaffold's HAL. "
    "\n\n"
    "Step 4 (compile + LINK): \"Run STM32er with action='build' and project_dir='<project_dir>' "
    "and system='make' and clean_first='true'\". Confirm returncode=0 and the link of firmware.elf. "
    "If returncode is non-zero, capture the compiler diagnostic from stderr &mdash; routable "
    "evidence; you may stop after the report with a 'BUILD FAILED' verdict. "
    "\n\n"
    "Step 5 (artifacts): \"Run STM32er with action='list_artifacts' and project_dir='<project_dir>'\". "
    "Capture the .hex and .bin paths. "
    "\n\n"
    "Step 6 (flash &mdash; upload over ST-LINK): \"Run STM32er with action='build_and_flash' and "
    "project_dir='<project_dir>'\". If a board is connected, the body shows the programmer "
    "verifying the download; if not, STM32er's preflight returns ok=false with 'No ST-LINK probe "
    "detected (... compile-only actions do NOT need a board)' &mdash; record it verbatim and "
    "CONTINUE (board-absent is the expected soft-fail for this demo). "
    "\n\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>STM32 Blinky &mdash; Run Report</strong>' and columns <em>step</em>, <em>stage</em> "
    "(validate|project|build|flash), <em>stm32_action</em>, <em>status</em> (ok|error), "
    "<em>headline</em> (gcc found; project_dir; build returncode; hex path; flash verify or "
    "'preflight refused: no board') &mdash; one row per call in execution order, status verbatim "
    "from the INI_SECTION_STM32ER block. Light body cells (background:#ffffff;color:#0f172a; or "
    "striped #f1f5f9); green tint ok, subtle red error. "
    "\n\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; BLINKY LIVE' (build returncode=0 AND flash verified), "
    "'&#9888;&#65039; BUILT, NO BOARD' (build ok but the preflight refused the flash / no board), "
    "or '&#10060; BUILD FAILED' (build returncode &ne; 0), and underneath a one-line metric "
    "'project: <project_dir> &middot; build rc: <0> &middot; flash: <verified|no-board> &middot; "
    "led: PD12&ndash;PD15 @ 500&nbsp;ms'. End with END-RESPONSE."
)


STM32_HIL_OBSERVATORY_DEMO = (
    "Tlamatini, run the **STM32 HIL OBSERVATORY** demo, please &mdash; an advanced "
    "**hardware-in-the-loop** showcase that USES A REAL BOARD end-to-end, driven entirely from "
    "chat through the wrapped **chat_agent_stm32er** tool: it preflight-validates that an ST-LINK "
    "is connected, scaffolds and AUTHORS firmware that increments a global counter and streams it "
    "over UART, builds + flashes it to the board, then PROVES it is running on real silicon two "
    "independent ways &mdash; reads the boot banner over the ST-LINK Virtual COM Port (serial), "
    "AND samples a live global variable from the RUNNING MCU's RAM over SWD (live memory) &mdash; "
    "before hardware-resetting the board. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY STM32CubeIDE (STM32er auto-provisions the MCP itself); (b) **an STM32F407 "
    "board (e.g. STM32F407G-DISC1) IS connected** via ST-LINK with its Virtual COM Port enabled "
    "&mdash; this demo REQUIRES hardware; (c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT "
    "required). Use ONLY chat_agent_stm32er, ONE call per step shaped \"Run STM32er with "
    "action='<action>' and <k>='<v>' ...\". Read each JSON return (INI_SECTION_STM32ER block under "
    "log_excerpt), capture action/ok/returncode/success/project_dir/session_id/stage, and on "
    "ok=false record verbatim and CONTINUE. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128300; STM32 HIL OBSERVATORY &#9889;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini STM32er &mdash; validate &middot; flash &middot; VCP serial &middot; live SWD memory</div></div>. "
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
    "GPIO + USART2 (the ST-LINK VCP, 115200 8N1), and in the while(1) loop: increments "
    "g_blink_count, toggles the LED, transmits a single newline-terminated status line of the form "
    "'BOOT tlamatini hil count=<n>' over USART2 with HAL_UART_Transmit, and HAL_Delay(500). Pass it "
    "as a TRIPLE-QUOTED content literal (content='''...''') so newlines and braces survive the "
    "parser. Keep it self-contained and buildable against the scaffold's HAL. "
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
    "Step 6 (HIL #1 &mdash; serial VCP boot banner): \"Run STM32er with action='serial_session' and "
    "port='COM7' and baud='115200' and serial_timeout='3'\" (substitute the actual ST-LINK VCP port "
    "&mdash; if unsure you MAY first call action='serial_list_ports' and pick the port flagged as an "
    "ST-LINK VCP). With no `data` set, serial_session connects, READS the board's output, then "
    "disconnects &mdash; capture the 'BOOT tlamatini hil count=<n>' line as proof the firmware is "
    "alive. "
    "\n\n"
    "Step 7 (HIL #2 &mdash; live SWD memory): \"Run STM32er with action='live_monitor' and "
    "variables='[\\\"g_blink_count\\\"]' and project_dir='<project_dir>' and monitor_seconds='4' and "
    "last_n='8'\". This starts an OpenOCD stream of the RUNNING MCU's RAM, samples the global for 4 "
    "seconds, returns the most-recent 8 samples, and stops. Capture the FIRST and LAST g_blink_count "
    "samples and confirm the value is INCREASING &mdash; direct, on-silicon proof the while(1) loop "
    "is executing (not just that the .hex flashed). "
    "\n\n"
    "Step 8 (HIL #3 &mdash; reset): \"Run STM32er with action='reset' and project_dir='<project_dir>'\" "
    "to hardware-reset the MCU and leave the board in a clean state. "
    "\n\n"
    "Step 9: render a STATUS SCOREBOARD &mdash; a row of HTML chips of the form "
    "<span style='display:inline-block;padding:8px 16px;margin:3px;border-radius:10px;"
    "font-weight:800;background:CHIP_BG;color:#ffffff;'>LABEL</span>: a 'validate: <ok|err>' chip, "
    "a 'build: <ok|err>' chip, a 'flash: <ok|err>' chip, a 'serial: <ok|err>' chip, a "
    "'live_mem: <ok|err>' chip, a 'reset: <ok|err>' chip (CHIP_BG #16a34a when ok else #dc2626), and "
    "a 'count: <first>&rarr;<last>' chip (CHIP_BG #2563EB). "
    "\n\n"
    "Step 10: render an HTML table with class='exec-report-table' titled "
    "'<strong>STM32 HIL Observatory &mdash; Run Report</strong>' and columns <em>step</em>, "
    "<em>stage</em> (validate|project|build|flash|serial|live_memory|reset), <em>stm32_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (stlink_connected; project_dir; build returncode; "
    "flash verify; the captured VCP boot line; g_blink_count first&rarr;last; reset ok) &mdash; one "
    "row per call in execution order, status verbatim from the INI_SECTION_STM32ER block (do NOT "
    "re-classify). Light body cells (background:#ffffff;color:#0f172a; or striped #f1f5f9). "
    "\n\n"
    "Step 11: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; SILICON VERIFIED' (build returncode=0 AND flash AND serial AND live_memory all ok "
    "&mdash; the counter was observed RISING over SWD), '&#9888;&#65039; NO BOARD' (Step 1 found no "
    "ST-LINK connected), or '&#10060; BUILD FAILED' (build returncode &ne; 0), and underneath a "
    "one-line metric 'project: <project_dir> &middot; build rc: <0> &middot; flash: <verified> "
    "&middot; VCP: \"<boot line>\" &middot; g_blink_count over SWD: <first>&rarr;<last>'. End with "
    "END-RESPONSE."
)


_NEW_PROMPTS = (
    (63, STM32_GENESIS_DEMO),
    (64, STM32_BLINKY_DEMO),
    (65, STM32_HIL_OBSERVATORY_DEMO),
)


def add_stm32er_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_stm32er_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0102_add_chat_agent_stm32er_tool'),
    ]

    operations = [
        migrations.RunPython(add_stm32er_demo_prompts, remove_stm32er_demo_prompts),
    ]
