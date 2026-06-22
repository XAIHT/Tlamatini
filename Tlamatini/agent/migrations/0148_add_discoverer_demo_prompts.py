from django.db import migrations
from django.db.models import Max

# Two catalog prompts that drive the Discoverer agent (the ProjectDiscovery suite)
# end to end in Multi-Turn, with the Exec Report ON. Both are SAFE to run
# repeatedly (the daily chat test may execute them):
#   * PROMPT_RECON  — 100% PASSIVE / zero-touch: validate -> subfinder passive
#     subdomain enum (OSINT only, never touches the domain) -> cvemap CVE DB lookup.
#   * PROMPT_PROBE  — ACTIVE but only against scanme.nmap.org, the host Nmap
#     PUBLICLY AUTHORIZES for scan-tool testing: naabu connect-scan (no Npcap/admin)
#     + httpx probe.
# Both bake in the first-run note (the very first chat_agent_discoverer call
# downloads a private Go compiler into <install_dir>/Go and compiles the tool —
# slow once, cached after) and ask for a fancy Discovery-Violet HTML report.
#
# Catalog classifier (tools_dialog.js::classifyPromptModes) badges them
# Multi-turn / Exec-report from the keywords ("Multi-Turn", "Exec Report",
# "operator", "chat_agent_discoverer"); no acp_*/skill tokens -> NOT ACPX.
#
# NOTE: these run only once the Multi-Turn wrapper (chat_agent_discoverer) + the
# Discoverer Agent/Tool rows exist (the agent/tool migrations that follow). They
# seed fine now regardless — they are just Prompt rows.
#
# CONTIGUITY: the #prompts-catalog dropdown enumerates prompt-1, prompt-2, ... and
# BREAKS at the first gap, so these are APPENDED at max(idPrompt)+1 with no
# renumber (start computed at apply time so the live catalog stays gap-free).

PROMPT_RECON = r"""Tlamatini, operator mode — DISCOVERER RECON SWEEP (passive, zero-touch). Keep the Multi-Turn and Exec Report checkboxes ticked. Use ONLY the chat_agent_discoverer tool (the ProjectDiscovery suite). AUTHORIZED / PASSIVE ONLY — every step below queries public OSINT or the CVE database and sends NO traffic to any third-party target.

Heads-up: the VERY FIRST chat_agent_discoverer call downloads a private Go compiler into <install_dir>/Go and compiles the tool — that one run is slow (a minute or two). After that it's instant. Be patient on the first step and do NOT retry it.

Run these, ONE tool call each:
1. tool='validate' — show me where the Go toolchain (GOROOT), tools_bin (GOBIN) and output_dir resolve, and which ProjectDiscovery tools are already installed.
2. tool='subfinder', target='projectdiscovery.io', subfinder_all_sources=false, json_output=true — passive subdomain enumeration (it queries OSINT sources only and never touches projectdiscovery.io directly). Tell me how many subdomains were discovered (findings_count) and list a few.
3. tool='cvemap', cvemap_id='CVE-2021-44228', json_output=true — look up the Log4Shell CVE in the ProjectDiscovery CVE database (a pure DB query; works without a PDCP key, just rate-limited).

Finish with ONE fancy HTML report: a table whose header row uses style="background:linear-gradient(135deg,#2E1065,#7C3AED,#C026D3,#F0ABFC);color:#ffffff;" with columns step | tool | subject | findings | status, preceded by a bold one-line headline. Then END-RESPONSE.
"""


PROMPT_PROBE = r"""Tlamatini, operator mode — DISCOVERER AUTHORIZED PROBE of scanme.nmap.org. Keep the Multi-Turn and Exec Report checkboxes ticked. Use ONLY the chat_agent_discoverer tool. SAFETY: scanme.nmap.org is the host Nmap PUBLICLY AUTHORIZES for scan-tool testing — it is the ONLY active target here. Never point these tools at anything you do not own or are not authorized to test.

Heads-up: if a tool is not yet installed, the first chat_agent_discoverer call compiles it with the private Go toolchain in <install_dir>/Go — slow once, then cached. Be patient and do NOT retry the first step.

Run these, ONE tool call each:
1. tool='naabu', target='scanme.nmap.org', naabu_top_ports='100', naabu_scan_type='c', json_output=true — a CONNECT-scan (no Npcap / admin needed on Windows) of the top 100 ports. Report the open ports (findings_count).
2. tool='httpx', target='scanme.nmap.org', httpx_probes='status_code,title,tech_detect,server', json_output=true — probe it over HTTP and tell me the status code, page title, web server and any detected technology.

Finish with ONE fancy HTML report: a table whose header row uses style="background:linear-gradient(135deg,#2E1065,#7C3AED,#C026D3,#F0ABFC);color:#ffffff;" with columns step | tool | target | result | status, preceded by a bold one-line headline. Then END-RESPONSE.
"""


_NEW_PROMPTS = (PROMPT_RECON, PROMPT_PROBE)


def add_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    start = (Prompt.objects.aggregate(m=Max('idPrompt'))['m'] or 0) + 1
    for offset, content in enumerate(_NEW_PROMPTS):
        pid = start + offset
        Prompt.objects.update_or_create(
            idPrompt=pid,
            defaults={'promptName': f'prompt-{pid}', 'promptContent': content},
        )


def remove_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    # Appended at the end; remove the top len(_NEW_PROMPTS) rows.
    ids = list(
        Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True)[:len(_NEW_PROMPTS)]
    )
    Prompt.objects.filter(idPrompt__in=ids).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0147_add_unreal_game_demo_prompts')]
    operations = [migrations.RunPython(add_demo_prompts, remove_demo_prompts)]
