# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog-of-Prompts examples for the new Nmapper agent (#85) — the "copy → parametrize
→ send → win" CTF openers.

Nmapper is LOCAL and USE-ONLY: it runs a real nmap the user installed themselves (Nmapper
NEVER bundles/redistributes nmap — nmap's NPSL forbids embedding it without a paid OEM
licence). The default is an UNPRIVILEGED TCP CONNECT SCAN (-sT) that needs NO Npcap and NO
admin, so a fresh install can scan immediately; if nmap is absent Nmapper refuses gracefully
and the `install` action fetches the official free installer (admin/UAC; also brings Npcap).

All three prompts target scanme.nmap.org — the Nmap project's OWN explicitly-authorized
test host — so they are SAFE to run repeatedly (the daily chat test may execute them).
AUTHORIZED TARGETS ONLY.

Appended at MAX+1 (contiguity contract: the #prompts-catalog dropdown enumerates
prompt-1..N and BREAKS at the first gap, so we never renumber and never leave a hole;
MAX_PROMPTS=256). The wording ("Multi-Turn checkbox" + "chat_agent_nmapper") makes the
catalog mode-classifier light up Multi-Turn.
"""
from django.db import migrations


NMAPPER_QUICK_DEMO = (
    "Tlamatini, run the **NMAPPER CTF RECON** demo, please — tick ONLY the Multi-Turn "
    "checkbox. Do a quick LOCAL nmap scan of scanme.nmap.org (the Nmap project's OWN "
    "officially-authorized test host) with chat_agent_nmapper using action='quick', "
    "target='scanme.nmap.org'. This is an UNPRIVILEGED TCP connect scan "
    "(-sT -sV -sC -Pn -T4 --top-ports 1000) that needs NO admin and NO Npcap, so it works "
    "the moment nmap is installed. Report the open ports, the detected services + versions, "
    "and any default-script (-sC) findings a CTF player could act on. If nmap is not "
    "installed, tell me exactly how to get it (the `install` action fetches the official "
    "free installer). Use ONLY chat_agent_nmapper. AUTHORIZED TARGETS ONLY. End with END-RESPONSE."
)

NMAPPER_FULL_DEMO = (
    "Tlamatini, run the **NMAPPER FULL SWEEP** — tick ONLY the Multi-Turn checkbox. Use "
    "chat_agent_nmapper with action='full', target='scanme.nmap.org' (the Nmap project's "
    "authorized test host), timing='T4' to connect-scan ALL 65535 TCP ports with version "
    "detection, catching any service on an odd high port that a top-1000 scan would miss. "
    "Summarize which ports are open and what is listening on each. Multi-Turn ONLY, "
    "chat_agent_nmapper ONLY, AUTHORIZED TARGETS ONLY. End with END-RESPONSE."
)

NMAPPER_SCRIPTS_DEMO = (
    "Tlamatini, run the **NMAPPER SERVICE ENUM** — tick ONLY the Multi-Turn checkbox. Use "
    "chat_agent_nmapper with action='scripts', target='scanme.nmap.org' (the Nmap project's "
    "authorized test host), ports='22,80', nse_scripts='banner,http-title,ssh2-enum-algos' "
    "for focused CONNECT-based NSE enumeration (no raw packets, no admin). Extract the "
    "banners / page titles / SSH algorithms into a short findings list. Multi-Turn ONLY, "
    "chat_agent_nmapper ONLY, AUTHORIZED TARGETS ONLY. End with END-RESPONSE."
)

_NEW_PROMPTS = (NMAPPER_QUICK_DEMO, NMAPPER_FULL_DEMO, NMAPPER_SCRIPTS_DEMO)


def add_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for content in _NEW_PROMPTS:
        if Prompt.objects.filter(promptContent=content).exists():
            continue
        next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_id,
            defaults={'promptName': f'prompt-{next_id}', 'promptContent': content},
        )


def remove_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent__in=list(_NEW_PROMPTS)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0171_add_chat_agent_nmapper_tool')]
    operations = [migrations.RunPython(add_prompts, remove_prompts)]
