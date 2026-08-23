# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Catalog of Prompts — the NETSPEED-CALCULATOR demo (Angela, 2026-08-23).

A Multi-Turn prompt that measures this machine's real Internet connection and
reports the result WITH its error bar, which is the whole point of the agent:
one CDN can flatter a link, several disagreeing CDNs cannot.

Contract compliance (all of it, deliberately):
  * APPEND-ONLY id. 0194 left the catalog at 118 (verified against the live DB:
    MAX(idPrompt)=118 with 118 rows, i.e. contiguous 1..118), so this is id 119
    — appended, never renumbered (``test_ids_are_contiguous_1_to_n_no_gaps``).
  * ``category='run_execute'`` — the section for "make Tlamatini DO a system
    operation". It is not security_recon: this measures a link, it does not
    probe anyone else's.
  * ``sort_rank = 70`` is the next free slot in that section (it currently runs
    10,20,30,40,50,60) and last is the RIGHT place: a multi-provider network
    measurement is the most complex item there, and sections read
    least-complex -> most-complex. Rank 10 stays RESERVED for the section's
    Step-by-Step opener. Ranks are unique within a section
    (``test_ranks_are_unique_within_a_section``).
  * Parameter grammar v1.44.0: ``[[ ... — OPTIONAL, default: X ]]`` collected at
    the TOP, followed by the unfilled-guard sentence so a one-click demo still
    runs on the stated defaults. No hardcoded scratch path (Rules 15/16) — the
    agent writes its JSON artifact under the app's own Temp directory itself.
  * SAFE and repeatable: it measures, it mutates nothing, and every provider is
    a public keyless endpoint. The one honest cost is BANDWIDTH, which the
    prompt states out loud because the run really does move ~100-200 MB.
  * CLASSIFIER MODES: the closing PRE-FLIGHT line names the **Multi-Turn**
    checkbox, so ``classifyPromptModes`` (tools_dialog.js) badges the card
    Multi-turn + Exec-report and clicking it ticks exactly those two toolbar
    checkboxes. No ``acp_*`` tool and no "step-by-step" wording appears here —
    either would wrongly tick ACPX / Step-by-Step too.

Reverse deletes exactly this one row.
"""
from django.db import migrations

NETSPEED_DEMO = (
    "<div style=\"background:linear-gradient(135deg,#041E2B 0%,#0E6BA8 33%,"
    "#21D4B4 66%,#F9C80E 100%);color:#ffffff;padding:10px 14px;border-radius:8px;"
    "font-weight:600;\">📡 NetSpeed-Calculator — how fast is this connection, "
    "really?</div>\n\n"
    "FILL IN (optional — leave them as they are for a one-click demo):\n"
    "  · Providers to measure against: "
    "[[ providers — OPTIONAL, default: cloudflare,ookla,fast ]]\n"
    "  · Seconds of steady-state measurement per direction: "
    "[[ test_duration_seconds — OPTIONAL, default: 10 ]]\n"
    "If you left the blanks above untouched, use the stated defaults and run "
    "anyway — do not ask me to fill them in.\n\n"
    "Tlamatini, measure THIS machine's real Internet connection with "
    "chat_agent_netspeed_calculator using action='full', and then tell me, in "
    "plain language:\n"
    "  1. My download and upload speed in Mbps, each WITH its 95% confidence "
    "interval — I want the error bar, not a single flattering number.\n"
    "  2. My idle latency, my jitter, and my BUFFERBLOAT grade (A+ to F), and "
    "what that grade means for video calls and voice.\n"
    "  3. Whether the providers AGREED with each other (the I² heterogeneity "
    "figure) — and if they did not, say so plainly and tell me which one was "
    "the outlier, because that is a peering story, not a speed story.\n"
    "  4. One sentence on whether this link looks healthy for everyday work.\n\n"
    "Report the absolute path of the saved JSON artifact at the end. Please note "
    "this consumes real, possibly METERED bandwidth (roughly 100-200 MB), so run "
    "it once — do not repeat it to 'double-check'.\n\n"
    "PRE-FLIGHT: this run needs the **Multi-Turn** mode with the **Exec report** "
    "— clicking this card ticks both toolbar checkboxes for you."
)


def add_netspeed_calculator_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.update_or_create(
        idPrompt=119,
        defaults={
            'promptName': 'prompt-119',
            'promptContent': NETSPEED_DEMO,
            'category': 'run_execute',
            'hidden': False,
            'sort_rank': 70,
        },
    )


def remove_netspeed_calculator_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt=119).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0196_add_chat_agent_netspeed_calculator_tool'),
    ]

    operations = [
        migrations.RunPython(add_netspeed_calculator_prompt, remove_netspeed_calculator_prompt),
    ]
