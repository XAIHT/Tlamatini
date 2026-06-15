"""
Seed two Catalog-of-Prompts demos for **ESPHome device programming** through the
wrapped **chat_agent_esphomer** Multi-Turn tool (the `esphome` CLI bridge). They run
basic -> medium and mirror the ESP32er demos (0107), but built to ESPHomer's grain:
ESPHome devices are described in a SIMPLE YAML config (NO C++), ESPHomer drives the
`esphome` CLI DIRECTLY (no MCP server), and "provisioning" means pip-installing
ESPHome itself.

    79  ESPHOME GENESIS   basic   bootstrap (ESPHomer pip-installs + validates ESPHome
                                  itself) -> validate (full environment preflight) ->
                                  new_config (GENERATE a device YAML) -> config
                                  (validate the YAML) -> compile -> list_artifacts.
                                  NO board required (pure provision + build).
    80  SMART LIGHT       medium  validate -> new_config (a phone-controlled on/off
                                  light on the onboard LED) -> config -> compile ->
                                  list_artifacts -> upload. The upload is board-OPTIONAL:
                                  ESPHomer's safety preflight refuses it cleanly with
                                  'No serial port detected' if no board is attached
                                  (expected + routable, not a crash).

Both drive ONLY chat_agent_esphomer and remind the user to tick ONLY the **Multi-Turn**
checkbox (chat_agent_esphomer is NOT behind the ACPX/Skill surface, so ACPX is not
required — same as the ESP32er 0107, STM32er 0103 demos).

Placement (append, no renumber)
-------------------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1','prompt-2',... and BREAKS at the first missing slot, so the catalog must
stay a contiguous, gap-free 'prompt-1..N'. Slots 1-78 are occupied (0137 appended the
Globber demo at 78); these two APPEND at 79-80 with no shift of any existing prompt.
Reverse deletes 79-80. (MAX_PROMPTS=100.)
"""
from django.db import migrations


# ESPHome green banner palette (deep forest -> emerald -> spring green -> pale mint),
# the same family as the ``.canvas-item.esphomer-agent`` gradient, with a text-shadow
# so the white label stays legible across the bright mint end.
_BANNER_OPEN = (
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#06281C 0%,#0E8A4F 33%,#36D399 66%,#D7FBE8 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.5);'>"
)


ESPHOME_GENESIS_DEMO = (
    "Tlamatini, run the **ESPHOME GENESIS** demo, please &mdash; a basic, end-to-end "
    "showcase of ESPHomer's *zero-config self-provisioning* and *safety preflight*, driven "
    "entirely from chat through the wrapped **chat_agent_esphomer** tool: from a clean machine "
    "it pip-INSTALLS ESPHome itself, validates the whole environment, GENERATES a smart-home "
    "device YAML, validates and compiles it to a firmware image, then lists the .bin &mdash; all "
    "WITHOUT a board attached (this is a pure provision + build demo). "
    "PRECONDITIONS you can assume are TRUE (do NOT verify them &mdash; trust them and go straight "
    "to Step 1): (a) **the user installed ONLY Tlamatini** (plus, for a real upload later, the "
    "board's USB-serial driver) &mdash; you do NOT need to install or configure ESPHome, ESPHomer "
    "pip-installs it automatically; (b) NO board is needed &mdash; nothing is flashed; (c) tick "
    "ONLY the **Multi-Turn** checkbox before sending (ACPX is NOT required &mdash; "
    "chat_agent_esphomer is the ONLY tool you may use; do NOT use chat_agent_executer / "
    "chat_agent_pythonxer / acp_spawn). Every step is exactly ONE chat_agent_esphomer call shaped "
    "\"Run ESPHomer with action='<action>' and <k>='<v>' ...\". After each call read the JSON "
    "return (an INI_SECTION_ESPHOMER block under the run's log_excerpt) and capture action / tool / "
    "ok / returncode / success / config_path / name / stage plus the body. If a step returns "
    "ok=false / success=false, record it verbatim, DO NOT abort, continue. "
    "\\n\\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#127968; ESPHOME GENESIS &#9889;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini ESPHomer &mdash; provision &middot; validate &middot; author &middot; compile</div></div>. "
    "\\n\\n"
    "Step 1 (ZERO-CONFIG provision): call **chat_agent_esphomer** with request "
    "\"Run ESPHomer with action='bootstrap'\". This makes ESPHomer `pip install esphome` into its "
    "Python with NO manual setup. From the body capture the install action (present / pip-install) "
    "and 'overall : OK'. If overall is FAILED, the host likely has no internet &mdash; skip to the "
    "closing banner with a 'PROVISION FAILED' verdict. "
    "\\n\\n"
    "Step 2 (safety preflight): call **chat_agent_esphomer** with request "
    "\"Run ESPHomer with action='validate'\". This validates the environment WITHOUT building: "
    "capture esphome_resolvable and (since validate also probes for hardware) the serial summary "
    "(present). A missing serial port is FINE here &mdash; this demo never flashes. "
    "\\n\\n"
    "Step 3 (GENERATE the device YAML): call **chat_agent_esphomer** with request \"Run ESPHomer "
    "with action='new_config' and config_path='<TEMPLATES>/esphome/genesis/tlamatini-genesis.yaml' "
    "and name='tlamatini-genesis' and platform='esp32' and board='esp32dev'\", where <TEMPLATES> is "
    "your Templates directory (the absolute path the system prompt gives you). CAPTURE the "
    "**config_path** &mdash; pass it to every later step. "
    "\\n\\n"
    "Step 4 (validate the YAML): call **chat_agent_esphomer** with request \"Run ESPHomer with "
    "action='config' and config_path='<the path from Step 3>'\". Confirm returncode=0 (ESPHome "
    "expanded and validated the YAML). "
    "\\n\\n"
    "Step 5 (compile &rarr; firmware): call **chat_agent_esphomer** with request \"Run ESPHomer "
    "with action='compile' and config_path='<the path from Step 3>'\". Confirm returncode=0. NOTE: "
    "the FIRST compile downloads the platform + toolchain (via PlatformIO under the hood) so it can "
    "take a few minutes &mdash; that is normal. "
    "\\n\\n"
    "Step 6 (artifacts): call **chat_agent_esphomer** with request \"Run ESPHomer with "
    "action='list_artifacts' and config_path='<the path from Step 3>'\". Capture the firmware.bin "
    "path from the body. "
    "\\n\\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>ESPHome Genesis &mdash; Provision &amp; Build Report</strong>' and columns "
    "<em>step</em>, <em>stage</em> (bootstrap|validate|author|config|compile), <em>esphome_action</em>, "
    "<em>status</em> (ok|error), <em>headline</em> (overall for bootstrap; esphome_resolvable for "
    "validate; config_path for new_config; returncode for config/compile; the firmware path for "
    "list_artifacts) &mdash; one row per call in execution order, status verbatim from the "
    "INI_SECTION_ESPHOMER block (do NOT re-classify). Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9), green tint ok, subtle red error. "
    "\\n\\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing, in big letters, "
    "'&#9989; ESPHOME PROVISIONED &amp; FIRMWARE BUILT' (bootstrap OK, validate resolved esphome, "
    "compile returncode=0 and artifacts listed), '&#9888;&#65039; GENESIS PARTIAL' (some steps ok, "
    "some error), or '&#10060; PROVISION FAILED' (bootstrap overall FAILED), and underneath a "
    "one-line metric 'esphome: <install action> &middot; config: <config_path> &middot; compile rc: "
    "<0> &middot; artifact: firmware.bin'. End with END-RESPONSE."
)


SMART_LIGHT_DEMO = (
    "Tlamatini, run the **SMART LIGHT** demo, please &mdash; a medium-complexity showcase that "
    "builds a *phone-controlled light* with ESPHome, driven entirely from chat through the wrapped "
    "**chat_agent_esphomer** tool: it preflight-validates the environment, GENERATES a device YAML "
    "for an on/off light on the board's onboard LED (exposed over the ESPHome native API so a "
    "smart-home hub can toggle it from a phone), validates and compiles it, lists the artifacts, "
    "then attempts to upload it to a board. "
    "PRECONDITIONS you can assume are TRUE (do NOT verify; go straight to Step 1): (a) the user "
    "installed ONLY Tlamatini &mdash; ESPHomer pip-installs ESPHome itself on first use, so you "
    "NEVER configure tool paths; (b) the build needs NO board; the UPLOAD step needs an ESP32 board "
    "on USB (ESPHome flashes the first time over USB-serial, OTA after) &mdash; BUT ESPHomer's "
    "safety preflight will REFUSE the upload with 'No serial port detected' if no board is "
    "connected, which is EXPECTED and routable, NOT a crash: record it verbatim and CONTINUE; "
    "(c) tick ONLY the **Multi-Turn** checkbox (ACPX is NOT required). Use ONLY chat_agent_esphomer, "
    "ONE call per step shaped \"Run ESPHomer with action='<action>' and <k>='<v>' ...\". Read each "
    "JSON return (INI_SECTION_ESPHOMER block under log_excerpt), capture "
    "action/tool/ok/returncode/success/config_path/name/port/stage, and on ok=false record verbatim "
    "and CONTINUE. "
    "\\n\\n"
    "Step 0: open with one HTML banner &mdash; " + _BANNER_OPEN +
    "<h2 style='margin:0;letter-spacing:2px;'>&#128161; SMART LIGHT &#128241;</h2>"
    "<div style='opacity:.92;margin-top:4px;'>Tlamatini ESPHomer &mdash; validate &middot; author &middot; compile &middot; upload</div></div>. "
    "\\n\\n"
    "Step 1 (safety preflight): \"Run ESPHomer with action='validate'\" &mdash; capture "
    "esphome_resolvable and the serial summary (present) as the 'before' baseline (ESPHomer "
    "auto-provisions ESPHome as part of this if needed). "
    "\\n\\n"
    "Step 2 (GENERATE the smart-light YAML): \"Run ESPHomer with action='new_config' and "
    "config_path='<TEMPLATES>/esphome/light/tlamatini-light.yaml' and name='tlamatini-light' and "
    "platform='esp32' and board='esp32dev' and led_pin='GPIO2' and wifi_ssid='YOUR_WIFI' and "
    "wifi_password='YOUR_PASS'\", where <TEMPLATES> is your Templates directory. This writes a valid "
    "ESPHome config with esp32/logger/api/ota/wifi blocks and a binary light named 'Tlamatini Light' "
    "on GPIO2. CAPTURE the **config_path**. "
    "\\n\\n"
    "Step 3 (validate the YAML): \"Run ESPHomer with action='config' and config_path='<the path "
    "from Step 2>'\". Confirm returncode=0. "
    "\\n\\n"
    "Step 4 (compile): \"Run ESPHomer with action='compile' and config_path='<the path from Step "
    "2>'\". Confirm returncode=0. (First compile pulls the toolchain &mdash; can take a few minutes.) "
    "If returncode is non-zero, capture the diagnostic from stderr &mdash; routable evidence; you "
    "may stop after the report with a 'BUILD FAILED' verdict. "
    "\\n\\n"
    "Step 5 (artifacts): \"Run ESPHomer with action='list_artifacts' and config_path='<the path "
    "from Step 2>'\". Capture the firmware.bin path. "
    "\\n\\n"
    "Step 6 (upload &mdash; flash over USB-serial): \"Run ESPHomer with action='upload' and "
    "config_path='<the path from Step 2>'\". If a board is connected, the body shows esphome writing "
    "+ verifying the firmware; if not, ESPHomer's preflight returns ok=false with 'No serial port "
    "detected' &mdash; record it verbatim and CONTINUE (board-absent is the expected soft-fail). "
    "\\n\\n"
    "Step 7: render an HTML table with class='exec-report-table' titled "
    "'<strong>Smart Light &mdash; Run Report</strong>' and columns <em>step</em>, <em>stage</em> "
    "(validate|author|config|compile|upload), <em>esphome_action</em>, <em>status</em> (ok|error), "
    "<em>headline</em> (esphome resolved; config_path; compile returncode; firmware.bin path; upload "
    "verify or 'preflight refused: no board') &mdash; one row per call in execution order, status "
    "verbatim from the INI_SECTION_ESPHOMER block. Light body cells "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9); green tint ok, subtle red error. "
    "\\n\\n"
    "Step 8: close with one HTML banner reusing the Step 0 style printing "
    "'&#9989; LIGHT READY' (compile returncode=0 AND upload verified), "
    "'&#9888;&#65039; BUILT, NO BOARD' (compile ok but the preflight refused the upload / no board), "
    "or '&#10060; BUILD FAILED' (compile returncode &ne; 0), and underneath a one-line metric "
    "'config: <config_path> &middot; compile rc: <0> &middot; upload: <verified|no-board> &middot; "
    "light: \"Tlamatini Light\" on GPIO&nbsp;2'. End with END-RESPONSE."
)


_NEW_PROMPTS = (
    (79, ESPHOME_GENESIS_DEMO),
    (80, SMART_LIGHT_DEMO),
)


def add_esphomer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_esphomer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0139_add_chat_agent_esphomer_tool'),
    ]

    operations = [
        migrations.RunPython(add_esphomer_demo_prompts, remove_esphomer_demo_prompts),
    ]
