# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Two STEP-BY-STEP LED-blink walkthroughs for the STM32er PlatformIO backend
(Angela, 2026-07-15): a Blue Pill (STM32F103) over an external ST-LINK V2, and an
STM32F407G-DISC1 over its embedded ST-Link. Both are Multi-Turn + Exec-report +
Step-by-Step and go from installing the ST-Link driver, through a per-step
VERIFICATION at each stage, to confirming the LED actually blinks with the default
camera (Camcorder). Category 'firmware_iot'. Appended at the next free idPrompt;
the very next migration (0179) re-groups/re-sorts the whole catalog with no gaps.

Badge inference (tools_dialog.js::classifyPromptModes): driving chat_agent_stm32er
gives the Multi-turn badge (and Exec-report rides along automatically); the
UNFORMATTED phrase "Step-by-Step mode" (hyphenated + a keyword) lights the
Step-by-Step badge.
"""
from django.db import migrations


BLUEPILL_STEP_DEMO = (
    "Tlamatini, walk me through programming the **classic LED blink onto a Blue Pill "
    "(STM32F103C8), flashed over an external ST-LINK V2**, ONE step at a time, and prove the "
    "LED actually blinks with my default camera at the end. Before you start, tick **Multi-Turn**, "
    "**Exec report**, and the **Step-by-Step** checkbox.\n"
    "\n"
    "Because Step-by-Step mode is on, do EXACTLY ONE step per turn, then STOP and WAIT for me to "
    "reply `READY` (with whatever output/photo you asked for) before the next step. VERIFY each step "
    "yourself before moving on — if a check fails, tell me exactly what to fix and re-check; never "
    "skip ahead. Use ONLY your own agents: chat_agent_stm32er (PlatformIO backend) for build/flash "
    "and chat_agent_camcorder for the camera. The Blue Pill's user LED is on PC13; with "
    "framework 'arduino' that is LED_BUILTIN.\n"
    "\n"
    "STEP 1 — Install the ST-LINK V2 USB driver. Tell me to install the ST-Link driver (STSW-LINK009, "
    "or just install STM32CubeProgrammer — it bundles the driver), plug the ST-LINK V2 dongle into a "
    "USB port, and reply READY. THEN verify: run chat_agent_stm32er with action='validate', "
    "stm32_backend='platformio', board='bluepill_f103c8', and confirm STM32_Programmer_CLI is "
    "RESOLVABLE. (The board is not wired yet, so the ST-LINK probe may read absent here — that is "
    "expected; we only need the CLI/driver present at this step.) Report the check and wait.\n"
    "\n"
    "STEP 2 — Wire the Blue Pill to the ST-LINK V2 (SWD, 4 wires) and confirm the probe is seen. Tell "
    "me to connect ST-LINK 3.3V→Blue Pill 3V3, GND→GND, SWDIO→DIO, SWCLK→CLK, then reply READY. THEN "
    "verify: re-run action='validate' (same params) and confirm the ST-LINK probe now shows PRESENT. "
    "If it still reads absent, help me troubleshoot (cable, the BOOT0 jumper back to 0, the driver) "
    "and re-check. Wait.\n"
    "\n"
    "STEP 3 — Bootstrap PlatformIO (zero-config). Run chat_agent_stm32er with action='bootstrap', "
    "stm32_backend='platformio'. Confirm PlatformIO Core is ready (it auto-installs on first use — "
    "this can take a few minutes). Report and wait.\n"
    "\n"
    "STEP 4 — Create the project and BUILD the blink (no board access needed to compile). Run "
    "chat_agent_stm32er with action='create_project', stm32_backend='platformio', "
    "board='bluepill_f103c8', framework='arduino', project_dir='<your Templates directory>/"
    "bluepill_blink'. Then action='write_source', project_dir=<same>, rel_path='src/main.cpp', "
    "content= this sketch VERBATIM:\n"
    "\n"
    "    #include <Arduino.h>\n"
    "    void setup() { pinMode(LED_BUILTIN, OUTPUT); }\n"
    "    void loop() {\n"
    "      digitalWrite(LED_BUILTIN, HIGH); delay(500);\n"
    "      digitalWrite(LED_BUILTIN, LOW);  delay(500);\n"
    "    }\n"
    "\n"
    "Then action='build', project_dir=<same>. Confirm the build SUCCEEDED in the Exec report (the "
    "first build downloads the STM32 Arduino toolchain — let it finish). Report and wait.\n"
    "\n"
    "STEP 5 — FLASH it over the ST-LINK. Run chat_agent_stm32er with action='flash', "
    "stm32_backend='platformio', board='bluepill_f103c8', project_dir=<same>. Confirm the flash "
    "SUCCEEDED. (If it fails with a USB/OpenOCD error, the ST-LINK may need the WinUSB driver via "
    "Zadig — tell me and re-check.) The PC13 LED should now be blinking ~1 Hz. Report and wait.\n"
    "\n"
    "STEP 6 — VERIFY the blink with my default camera. Tell me to point the Blue Pill's PC13 LED at "
    "my webcam, then reply READY. THEN run chat_agent_camcorder with capture_mode='video', "
    "camera_index=0, video_duration_seconds=6 to record the board. Inspect the saved clip (you MAY "
    "pass it to chat_agent_video_analyzer or chat_agent_image_interpreter) and tell me PASS (the LED "
    "is blinking) or FAIL (steady/off), with the file path.\n"
    "\n"
    "Finish with a short, tidy HTML summary of all six steps and the final PASS/FAIL. End with "
    "END-RESPONSE."
)


DISCO_STEP_DEMO = (
    "Tlamatini, walk me through programming the **classic LED blink onto an STM32F407G-DISC1 "
    "Discovery board, flashed over its ON-BOARD (embedded) ST-Link/V2**, ONE step at a time, and "
    "prove the LED actually blinks with my default camera at the end. Before you start, tick "
    "**Multi-Turn**, **Exec report**, and the **Step-by-Step** checkbox.\n"
    "\n"
    "Because Step-by-Step mode is on, do EXACTLY ONE step per turn, then STOP and WAIT for me to "
    "reply `READY` (with whatever output/photo you asked for) before the next step. VERIFY each step "
    "yourself before moving on — if a check fails, tell me exactly what to fix and re-check; never "
    "skip ahead. Use ONLY your own agents: chat_agent_stm32er (PlatformIO backend) for build/flash "
    "and chat_agent_camcorder for the camera. The F407-DISC1 has four user LEDs on PD12–PD15 "
    "(green/orange/red/blue); with framework 'arduino' the green LED (PD12) is LED_BUILTIN. No "
    "external dongle or wiring is needed — the ST-Link is built into the board.\n"
    "\n"
    "STEP 1 — Install the ST-Link driver AND connect the board. Tell me to install the ST-Link/V2 USB "
    "driver (STSW-LINK009, or just install STM32CubeProgrammer — it bundles the driver), then plug "
    "the board into my PC using its ST-LINK USB port (the mini-USB connector CN1, labelled "
    "'ST-LINK' — NOT the micro-USB OTG port), and reply READY. THEN verify: run chat_agent_stm32er "
    "with action='validate', stm32_backend='platformio', board='disco_f407vg', and confirm BOTH that "
    "STM32_Programmer_CLI is resolvable AND that the embedded ST-Link probe shows PRESENT (the board "
    "powers its ST-Link from that USB port). If the probe reads absent, help me fix it (correct USB "
    "port, cable, driver) and re-check. Wait.\n"
    "\n"
    "STEP 2 — Bootstrap PlatformIO (zero-config). Run chat_agent_stm32er with action='bootstrap', "
    "stm32_backend='platformio'. Confirm PlatformIO Core is ready (it auto-installs on first use — a "
    "few minutes). Report and wait.\n"
    "\n"
    "STEP 3 — Create the project and BUILD the blink. Run chat_agent_stm32er with "
    "action='create_project', stm32_backend='platformio', board='disco_f407vg', framework='arduino', "
    "project_dir='<your Templates directory>/disc1_blink'. Then action='write_source', "
    "project_dir=<same>, rel_path='src/main.cpp', content= this sketch VERBATIM:\n"
    "\n"
    "    #include <Arduino.h>\n"
    "    void setup() { pinMode(LED_BUILTIN, OUTPUT); }\n"
    "    void loop() {\n"
    "      digitalWrite(LED_BUILTIN, HIGH); delay(500);\n"
    "      digitalWrite(LED_BUILTIN, LOW);  delay(500);\n"
    "    }\n"
    "\n"
    "Then action='build', project_dir=<same>. Confirm the build SUCCEEDED in the Exec report (the "
    "first build downloads the STM32 Arduino toolchain — let it finish). Report and wait.\n"
    "\n"
    "STEP 4 — FLASH it over the embedded ST-Link. Run chat_agent_stm32er with action='flash', "
    "stm32_backend='platformio', board='disco_f407vg', project_dir=<same>. Confirm the flash "
    "SUCCEEDED. The green LED (PD12) should now blink ~1 Hz. Report and wait.\n"
    "\n"
    "STEP 5 — VERIFY the blink with my default camera. Tell me to point the board's green PD12 LED at "
    "my webcam, then reply READY. THEN run chat_agent_camcorder with capture_mode='video', "
    "camera_index=0, video_duration_seconds=6. Inspect the clip (optionally via "
    "chat_agent_video_analyzer or chat_agent_image_interpreter) and tell me PASS (blinking) or FAIL "
    "(steady/off), with the file path.\n"
    "\n"
    "Finish with a short, tidy HTML summary of all five steps and the final PASS/FAIL. End with "
    "END-RESPONSE."
)


_NEW_PROMPTS = (BLUEPILL_STEP_DEMO, DISCO_STEP_DEMO)


def add_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for content in _NEW_PROMPTS:
        if Prompt.objects.filter(promptContent=content).exists():
            continue
        next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_id,
            defaults={
                'promptName': f'prompt-{next_id}',
                'promptContent': content,
                'category': 'firmware_iot',
            },
        )


def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent__in=list(_NEW_PROMPTS)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0177_add_stm32er_platformio_demo_prompt')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
