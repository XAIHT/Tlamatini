# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.db import migrations


# Catalog-of-Prompts demo for STM32er's NEW PlatformIO backend (Phase 1 — the
# Blue Pill → whole-ST-line widening). Showcases the headline capability: build
# (and flash-if-connected) a classic LED blink for an STM32F103 Blue Pill in ONE
# call, choosing the target purely by `board` (which routes to the PlatformIO
# backend automatically). SAFE for the daily chat test: `scaffold_build_flash` is
# fail-safe — it CREATES the project and COMPILES the firmware, and only flashes
# over the ST-LINK when a probe is actually connected; with no board attached it
# reports "built OK — connect the ST-LINK and run action=flash", which is a SUCCESS,
# not an error. No destructive op. Appends at the next free idPrompt (gaps allowed
# since migration 0176) and tags the row into the existing 'firmware_iot' category.
DEMO = (
    "Tlamatini, run the **STM32er BLUE PILL DEMO** — build (and flash it if a board is "
    "connected) a classic LED blink for an **STM32F103 \"Blue Pill\"** using your new "
    "PlatformIO backend, in ONE call.\n"
    "\n"
    "In Multi-Turn, using ONLY the chat_agent_stm32er tool, call it EXACTLY ONCE with:\n"
    "  - action='scaffold_build_flash'\n"
    "  - stm32_backend='platformio'   (this routes to the PlatformIO backend — no MCP server)\n"
    "  - board='bluepill_f103c8'      (the pio board id for the Blue Pill; it fixes the memory map/linker)\n"
    "  - framework='arduino'          (stm32duino — a board-agnostic LED_BUILTIN blink)\n"
    "  - project_dir='<your Templates directory>/bluepill_blink'  (default to YOUR Templates directory unless I name another path)\n"
    "  - content= this Arduino sketch, passed VERBATIM:\n"
    "\n"
    "        #include <Arduino.h>\n"
    "        void setup() { pinMode(LED_BUILTIN, OUTPUT); }\n"
    "        void loop() {\n"
    "          digitalWrite(LED_BUILTIN, HIGH); delay(500);\n"
    "          digitalWrite(LED_BUILTIN, LOW);  delay(500);\n"
    "        }\n"
    "\n"
    "ZERO-CONFIG: if PlatformIO Core is not installed yet, STM32er auto-installs it (shared "
    "with ESP32er) on first use — and the FIRST build also downloads the STM32 Arduino "
    "toolchain, so it can take a few minutes; that is normal, let it finish.\n"
    "\n"
    "FAIL-SAFE: this creates the project and COMPILES the firmware; it flashes over the "
    "ST-LINK only when a probe is connected. With NO board it reports 'built OK — connect the "
    "ST-LINK and run action=flash', which is a SUCCESS. Do NOT loop-retry a failed toolchain "
    "download — report the stderr and stop.\n"
    "\n"
    "When it returns, read the INI_SECTION_STM32ER result and give me a short, tidy HTML "
    "summary of: the backend used, the board, whether the BUILD succeeded, and whether it "
    "FLASHED or skipped the flash (and why). If you want to double-check the environment "
    "first, you MAY do a quick action='validate' with the same board before the scaffold.\n"
    "\n"
    "Tick ONLY the Multi-Turn checkbox; use ONLY chat_agent_stm32er. End with END-RESPONSE."
)


def add_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    if Prompt.objects.filter(promptContent=DEMO).exists():
        return
    next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
    Prompt.objects.update_or_create(
        idPrompt=next_id,
        defaults={
            'promptName': f'prompt-{next_id}',
            'promptContent': DEMO,
            'category': 'firmware_iot',
        },
    )


def remove_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent=DEMO).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0176_delete_duplicate_acpx_prompts')]
    operations = [migrations.RunPython(add_demo_prompt, remove_demo_prompt)]
