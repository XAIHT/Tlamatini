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
from django.db.models import Max

# A catalog-of-prompts example that drives the Discoverer agent's cvemap
# (ProjectDiscovery's CVE-database CLI, now shipped as `vulnx`) end to end in
# Multi-Turn with the Exec Report ON, to answer the everyday question
# "what are the LATEST critical / high CVEs right now, sorted by criticality?".
#
# SAFE by design: cvemap only QUERIES ProjectDiscovery's CVE database — it sends
# NO traffic to any third-party target — so the daily chat regression can run it
# freely. It works without a key (rate-limited) and pulls the freshest data at
# full rate once the OPTIONAL ProjectDiscovery Cloud (PDCP) API key is set in
# Config ▸ Access Keys Wizard ▸ "Security Recon (ProjectDiscovery)" (auto-injected
# into every chat_agent_discoverer run; see 0148 for the recon/probe prompts).
#
# It uses ONLY the stable cvemap flags the agent maps today (`cvemap_severity`
# -> -severity, `json_output` -> -json); the LLM performs the "latest + sort by
# criticality" ordering from the returned JSON, so the prompt never gambles on an
# uncertain -limit/-sort flag that a given vulnx build might reject.
#
# Catalog classifier (tools_dialog.js::classifyPromptModes) badges it
# Multi-turn / Exec-report from the keywords ("Multi-Turn", "Exec Report",
# "operator", "chat_agent_discoverer"); no acp_*/skill tokens -> NOT ACPX.
#
# CONTIGUITY: the #prompts-catalog dropdown enumerates prompt-1, prompt-2, ... and
# BREAKS at the first gap, so this is APPENDED at max(idPrompt)+1 with no renumber
# (start computed at apply time so the live catalog stays gap-free).

PROMPT_LATEST_CVES = r"""Tlamatini, operator mode — DISCOVERER LATEST-CVE BRIEFING via ProjectDiscovery cvemap (a.k.a. vulnx). Keep the Multi-Turn and Exec Report checkboxes ticked. Use ONLY the chat_agent_discoverer tool. This is 100% PASSIVE: cvemap only QUERIES ProjectDiscovery's CVE database — it sends NO traffic to any third-party target, so it is always safe to run.

Heads-up: the VERY FIRST chat_agent_discoverer call downloads a private Go compiler into <install_dir>/Go and compiles the tool — that one run is slow (a minute or two), then it is cached. Be patient on the first step and do NOT retry it.

About the key: cvemap pulls the FRESHEST CVEs at full rate when a ProjectDiscovery Cloud (PDCP) API key is configured. It is set ONCE in Config ▸ Access Keys Wizard ▸ "Security Recon (ProjectDiscovery)" and chat_agent_discoverer auto-injects it — never paste it here. Without a key cvemap still works but is rate-limited and may lag behind the very latest.

Run these, ONE tool call each:
1. tool='validate' — confirm cvemap/vulnx is installed (compiling it via the private Go toolchain if this is the first run) and show where GOROOT / GOBIN / output_dir resolve. From the run, tell me whether the PDCP key was detected (the pdcp_used field) so I know whether I am getting full-rate, freshest data.
2. tool='cvemap', cvemap_severity='critical,high', json_output=true — pull the current CRITICAL and HIGH severity CVEs from the ProjectDiscovery CVE database as JSON.

Then give me ONE polished HTML briefing (NO further tool call), built ENTIRELY from the JSON returned in step 2 — do not invent anything:
- A bold one-line headline with the total count and how many are Critical vs High, plus a note saying whether the PDCP key was active (from step 1's pdcp_used).
- A table SORTED BY CRITICALITY: every Critical CVE first, then every High; and within each severity, most-recent first (use the published date / age field) and higher CVSS first. Cap it at the 20 most recent so it stays readable, and state how many more were omitted.
- The table header row must use style="background:linear-gradient(135deg,#2E1065,#7C3AED,#C026D3,#F0ABFC);color:#ffffff;" with columns: CVE ID | Severity | CVSS | Affected product / vendor | Published (age) | Summary. Render the severity as a small colored badge (Critical = #B91C1C, High = #EA580C).
- Finish with a short "🔴 Patch first" callout naming the top 3 by severity-then-CVSS.

If cvemap returns nothing (rate-limited with no key, or a transient error), say so plainly and give me the single fix — set the PDCP key in Config ▸ Access Keys Wizard ▸ "Security Recon (ProjectDiscovery)" — and do NOT fabricate CVEs. Then END-RESPONSE.
"""


_NEW_PROMPTS = (PROMPT_LATEST_CVES,)


def add_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for content in _NEW_PROMPTS:
        if Prompt.objects.filter(promptContent=content).exists():
            continue
        start = (Prompt.objects.aggregate(m=Max('idPrompt'))['m'] or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=start,
            defaults={'promptName': f'prompt-{start}', 'promptContent': content},
        )


def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(promptContent__in=list(_NEW_PROMPTS)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0168_add_video_analyzer_demo_prompt')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
