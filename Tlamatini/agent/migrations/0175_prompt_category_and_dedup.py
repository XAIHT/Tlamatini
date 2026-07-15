# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Catalog-of-Prompts: CATEGORY grouping + DEDUP (Angela, 2026-07-14).

WHY: the 106 catalog prompts were sorted purely by `idPrompt` — i.e. the order
each agent was ADDED over time. So related prompts were scattered, and prompts
33-52 were ~20 cards for only 7 real ACPX demos (each repeated 2-3× as
plain / banner / Gemini-edition). Angela's verdict: not intuitive, and
"I don't want duplicates".

WHAT THIS DOES — without ever renumbering `idPrompt`:
  * adds `category` (grouping key) and `hidden` (drop-from-catalog flag);
  * tags all 106 prompts into 13 categories (Phase 1 — grouping);
  * flags the 13 duplicate ACPX prompts hidden (Phase 2 — dedup), keeping the
    FIRST (most portable, non-Gemini-pinned) version of each of the 7 demos.

WHY HIDE, NOT DELETE (deliberate): hiding keeps `idPrompt` CONTIGUOUS (1..106),
so the offline fallback probe in tools_dialog.js (which breaks at the first gap)
keeps working, and the change is fully REVERSIBLE. The live catalog shows zero
duplicates either way. To physically delete them later, unhide is a one-liner.
"""

from django.db import migrations, models

# idPrompt -> category key. Every id 1..106 is assigned exactly once.
_CATEGORY_BY_ID = {
    # Getting Started — quick asks on the loaded project + system basics
    1: "getting_started", 2: "getting_started", 3: "getting_started",
    4: "getting_started", 5: "getting_started", 7: "getting_started",
    8: "getting_started", 9: "getting_started",
    # Files & Search — find / search / edit / read files
    10: "files_search", 11: "files_search", 78: "files_search",
    79: "files_search", 80: "files_search",
    # Run & Execute — run commands/scripts, decompile
    12: "run_execute", 13: "run_execute", 14: "run_execute",
    21: "run_execute", 22: "run_execute",
    # Code & Project Generation
    6: "code_gen", 15: "code_gen", 16: "code_gen", 17: "code_gen",
    # Images & Vision
    18: "images", 19: "images", 20: "images", 100: "images",
    # Agents & Flows — lifecycle, parametrize, multi-turn, flow-making
    23: "agents_flows", 24: "agents_flows", 25: "agents_flows",
    30: "agents_flows", 31: "agents_flows", 32: "agents_flows",
    71: "agents_flows",
    # ACPX, Skills & MCPs (33-52 demos + 83 MCP Doctor)
    33: "acpx_skills", 34: "acpx_skills", 35: "acpx_skills", 36: "acpx_skills",
    37: "acpx_skills", 38: "acpx_skills", 39: "acpx_skills", 40: "acpx_skills",
    41: "acpx_skills", 42: "acpx_skills", 43: "acpx_skills", 44: "acpx_skills",
    45: "acpx_skills", 46: "acpx_skills", 47: "acpx_skills", 48: "acpx_skills",
    49: "acpx_skills", 50: "acpx_skills", 51: "acpx_skills", 52: "acpx_skills",
    83: "acpx_skills",
    # Desktop Automation — Windower + Playwrighter
    53: "desktop_ui", 54: "desktop_ui", 55: "desktop_ui", 56: "desktop_ui",
    57: "desktop_ui", 58: "desktop_ui",
    # Games & 3D — Unreal + Blender
    27: "games_3d", 62: "games_3d", 63: "games_3d", 64: "games_3d",
    77: "games_3d", 84: "games_3d", 85: "games_3d", 86: "games_3d",
    106: "games_3d",
    # Firmware & IoT — STM32 / ESP32 / Arduino / ESPHome
    65: "firmware_iot", 66: "firmware_iot", 67: "firmware_iot",
    68: "firmware_iot", 69: "firmware_iot", 70: "firmware_iot",
    72: "firmware_iot", 73: "firmware_iot", 74: "firmware_iot",
    81: "firmware_iot", 82: "firmware_iot",
    # Security & Recon — Reviewer / Analyzer / Kali / Discoverer / Nmapper
    28: "security_recon", 29: "security_recon", 59: "security_recon",
    60: "security_recon", 61: "security_recon", 87: "security_recon",
    88: "security_recon", 102: "security_recon", 103: "security_recon",
    104: "security_recon", 105: "security_recon",
    # Messaging & Contacts — Telegram / WhatsApp / Zavu / contacts / IM doctor
    26: "messaging", 89: "messaging", 90: "messaging", 91: "messaging",
    92: "messaging", 93: "messaging", 94: "messaging", 95: "messaging",
    96: "messaging", 97: "messaging", 98: "messaging", 99: "messaging",
    # Media & Voice — TTS / STT / video
    75: "media_voice", 76: "media_voice", 101: "media_voice",
}

# The 13 DUPLICATE ACPX prompts to hide. We keep 33-39 (the first, most-portable
# version of each of the 7 demos) and hide the "banner" (40-45) + "Gemini-edition"
# (46-52) re-runs of the same 7 concepts.
_HIDDEN_IDS = list(range(40, 53))  # 40..52 inclusive


def apply(apps, schema_editor):
    Prompt = apps.get_model("agent", "Prompt")
    for pid, cat in _CATEGORY_BY_ID.items():
        Prompt.objects.filter(idPrompt=pid).update(category=cat)
    Prompt.objects.filter(idPrompt__in=_HIDDEN_IDS).update(hidden=True)


def revert(apps, schema_editor):
    Prompt = apps.get_model("agent", "Prompt")
    Prompt.objects.all().update(category="", hidden=False)


class Migration(migrations.Migration):
    dependencies = [("agent", "0174_unreal_scaffold_build_project_tip")]

    operations = [
        migrations.AddField(
            model_name="prompt",
            name="category",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="prompt",
            name="hidden",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(apply, revert),
    ]
