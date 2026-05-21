"""
Seed two fancy, single-skill demo prompts that showcase the v1.4.2
**Reviewer** (code-review) and **Analyzer** (security-audit) agents from the
chat, then place them BEFORE the Multi-Turn sample prompts.

Both agents are canvas-only (no wrapped chat_agent_* tool); their chat-facing
surface is the SKILL.md twins `code-review` and `security-audit`, invoked via
`invoke_skill`. Each demo is therefore a single guided skill call rendered into
a banner + exec-report table + verdict/status banner, matching the fancy
house style of the Unrealer demo (slot 25) that immediately precedes them.

Placement & renumber
--------------------
The catalog dropdown (static/agent/js/tools_dialog.js) enumerates promptName
'prompt-1', 'prompt-2', ... and BREAKS at the first missing slot, so the
catalog must stay a contiguous, gap-free 'prompt-1..N' and its display order is
the numeric suffix. Slots 1-25 are fully occupied (Unrealer owns 25), so to
land the two new demos at 26-27 (right after Unrealer, right before the
Multi-Turn demos) this migration first shifts every existing Prompt with
idPrompt >= 26 UP by +2 -- renumbering BOTH idPrompt and promptName, processed
in collision-safe order -- then writes the two new prompts into the freed
slots. Post-shift catalog map:

    1-20    tiers 1-8 (context Q&A ... project-wide code mod)   (0002)
    21-23   agent control                                       (0062)
    24      telegrammer parametrize                             (0063)
    25      Unrealer end-to-end editor drive                    (0087)
    26      Reviewer / code-review showcase     <-- NEW          (THIS)
    27      Analyzer / security-audit showcase  <-- NEW          (THIS)
    28-30   Multi-Turn demos          (was 26-28)               (0002)
    31-37   simplified ACPX demos     (was 29-35)               (0074)
    38-43   rich-HTML ACPX demos      (was 36-41)               (0072)
    44-50   Gemini-pinned ACPX demos  (was 42-48)               (0073)

Reverse: delete 26-27, then shift idPrompt >= 28 back DOWN by -2, restoring the
pre-migration catalog (contiguous 1..48) exactly.

Note: invoke_skill lives behind the ACPX/Skill tool surface, so both prompts
remind the user to tick BOTH the Multi-Turn and ACPX toolbar checkboxes before
sending.
"""
from django.db import migrations


FIRST_SHIFTED_ID = 26
SHIFT = 2


# ── Demo-prompt content ────────────────────────────────────────────────

REVIEWER_DEMO = (
    "Tlamatini, run the **CODE REVIEW SPOTLIGHT** demo, please &mdash; a fancy, "
    "end-to-end showcase of the new **Reviewer** agent driven from chat through "
    "its **code-review** Skill (a senior-engineer git-diff review that returns a "
    "verdict plus line-anchored findings). "
    "PRECONDITIONS (tick these in the toolbar BEFORE sending): the **Multi-Turn** "
    "checkbox AND the **ACPX** checkbox must both be ON, because invoke_skill "
    "lives behind the ACPX/Skill tool surface; the target must be a git "
    "repository with at least one prior commit. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#0E7490 0%,#2563EB 33%,#4F46E5 66%,#7C3AED 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#128269; CODE REVIEW SPOTLIGHT &#128269;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Reviewer &mdash; the code-review Skill, senior-engineer verdict</div></div>. "
    "\n\n"
    "Step 1: call **invoke_skill** with skill_name='code-review' and "
    "args_json='{\"repo_path\":\"C:/Development/Tlamatini\",\"diff_ref\":\"HEAD~1\","
    "\"focus\":\"security and correctness regressions\"}'. If the returned summary "
    "says the diff was empty, call it once more with "
    "args_json='{\"repo_path\":\"C:/Development/Tlamatini\",\"diff_ref\":\"\","
    "\"focus\":\"uncommitted working-tree and staged changes\"}' so the demo always "
    "has something to review. "
    "\n\n"
    "Step 2: parse the skill envelope and capture three things: the verdict "
    "(APPROVE | REQUEST_CHANGES | COMMENT), the findings array (each is "
    "{file, line, severity, category, message, suggestion}), and the summary. "
    "\n\n"
    "Step 3: render a big VERDICT CHIP &mdash; one HTML "
    "<div style='display:inline-block;padding:10px 22px;border-radius:999px;"
    "font-weight:800;letter-spacing:1px;color:#ffffff;background:VERDICT_COLOR;'> "
    "block showing the verdict text, where VERDICT_COLOR is #16a34a for APPROVE, "
    "#d97706 for COMMENT, and #dc2626 for REQUEST_CHANGES. "
    "\n\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Code Review Findings</strong>' and columns "
    "<em>file</em>, <em>line</em>, <em>severity</em>, <em>category</em>, "
    "<em>message</em>, <em>suggestion</em>. One row per finding, ordered most "
    "severe first (critical, then high, then medium, then low, then nit). Keep "
    "every body cell light-background with dark text "
    "(background:#ffffff;color:#0f172a; or striped #f1f5f9) and tint ONLY the "
    "severity cell (critical #fee2e2, high #ffedd5, medium #fef9c3, low/nit "
    "#ecfccb) while keeping its text dark. If the findings array is empty, render "
    "a single celebratory row spanning the table that reads 'No substantive "
    "findings &mdash; the diff is clean.' "
    "\n\n"
    "Step 5: render the skill's summary inside an HTML "
    "<blockquote style='border-left:6px solid #4F46E5;padding:12px 18px;"
    "background:#ffffff;color:#0f172a;border-radius:8px;'>...summary...</blockquote>. "
    "\n\n"
    "Step 6: close with one HTML banner that reuses the Step 0 gradient and prints "
    "the verdict in big white letters, and underneath it a one-line metric "
    "'Verdict: <verdict> &middot; findings: <N> (critical <c>, high <h>, medium "
    "<m>, low/nit <l>)'. End with END-RESPONSE."
)

ANALYZER_DEMO = (
    "Tlamatini, run the **SECURITY AUDIT FLOODLIGHT** demo, please &mdash; a "
    "fancy, end-to-end showcase of the new **Analyzer** agent driven from chat "
    "through its **security-audit** Skill (deterministic SAST + secret + "
    "dependency scanning, no LLM guessing). "
    "PRECONDITIONS (tick these in the toolbar BEFORE sending): the **Multi-Turn** "
    "checkbox AND the **ACPX** checkbox must both be ON, because invoke_skill "
    "lives behind the ACPX/Skill tool surface. The skill runs whichever of "
    "bandit, semgrep, ruff, eslint, gitleaks and pip-audit are on PATH &mdash; any "
    "that are missing are reported as coverage gaps rather than failing the run. "
    "\n\n"
    "Step 0: open with one HTML banner &mdash; "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#7F1D1D 0%,#DC2626 33%,#F59E0B 66%,#FACC15 100%);color:#ffffff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
    "<h2 style='margin:0;letter-spacing:2px;color:#ffffff;'>&#128737;&#65039; SECURITY AUDIT FLOODLIGHT &#128737;&#65039;</h2>"
    "<div style='opacity:.92;margin-top:4px;color:#ffffff;'>Tlamatini Analyzer &mdash; the security-audit Skill, every scanner on PATH</div></div>. "
    "\n\n"
    "Step 1: call **invoke_skill** with skill_name='security-audit' and "
    "args_json='{\"path\":\"C:/Development/Tlamatini/Tlamatini/agent\","
    "\"min_severity\":\"low\"}'. "
    "\n\n"
    "Step 2: parse the skill envelope and capture: the findings array (each is "
    "{tool, file, line, severity, rule_id, message}), the severity_counts object "
    "({critical, high, medium, low}), the summary, and &mdash; from the summary "
    "&mdash; which scanners actually ran and which were unavailable. "
    "\n\n"
    "Step 3: render a SEVERITY SCOREBOARD &mdash; a row of four HTML chips of the "
    "form <span style='display:inline-block;padding:8px 16px;margin:3px;"
    "border-radius:10px;font-weight:800;background:CHIP_BG;color:CHIP_FG;'>"
    "<count> <label></span> for critical (CHIP_BG #7F1D1D / CHIP_FG #ffffff), high "
    "(CHIP_BG #DC2626 / CHIP_FG #ffffff), medium (CHIP_BG #F59E0B / CHIP_FG "
    "#0f172a) and low (CHIP_BG #FACC15 / CHIP_FG #0f172a). "
    "\n\n"
    "Step 4: render an HTML table with class='exec-report-table' titled "
    "'<strong>Static-Analysis &amp; Secret-Scan Findings</strong>' and columns "
    "<em>tool</em>, <em>file</em>, <em>line</em>, <em>severity</em>, "
    "<em>rule_id</em>, <em>message</em>. One row per finding, ordered most severe "
    "first (critical, then high, then medium, then low). Keep every body cell "
    "light-background with dark text (background:#ffffff;color:#0f172a; or striped "
    "#f1f5f9) and tint ONLY the severity cell (critical #fee2e2, high #ffedd5, "
    "medium #fef9c3, low #ecfccb) while keeping its text dark. If the findings "
    "array is empty, render a single celebratory row spanning the table that reads "
    "'No findings at or above the low threshold &mdash; clean scan.' "
    "\n\n"
    "Step 5: render the skill's remediation summary inside an HTML "
    "<blockquote style='border-left:6px solid #DC2626;padding:12px 18px;"
    "background:#ffffff;color:#0f172a;border-radius:8px;'>...summary...</blockquote>, "
    "and beneath it an HTML <ul> with two <li> bullets: 'Scanners run: <list>' and "
    "'Scanners unavailable (coverage gaps): <list>'. "
    "\n\n"
    "Step 6: close with one HTML banner that reuses the Step 0 gradient and prints, "
    "in big white letters, 'SECURITY: CLEAN' (if there are zero findings) or "
    "'SECURITY: <total> FINDINGS' (otherwise), and underneath a one-line metric "
    "'critical <c> &middot; high <h> &middot; medium <m> &middot; low <l> &middot; "
    "scanned C:/Development/Tlamatini/Tlamatini/agent'. End with END-RESPONSE."
)


# ── Shift helper ───────────────────────────────────────────────────────

def _shift_block(Prompt, threshold, delta):
    """Shift every Prompt with idPrompt >= threshold by `delta`, renumbering
    both idPrompt and promptName. Processed largest-first when moving up and
    smallest-first when moving down so the primary-key reassignment never
    collides with an as-yet-unmoved row."""
    ids = list(
        Prompt.objects.filter(idPrompt__gte=threshold).values_list('idPrompt', flat=True)
    )
    ids.sort(reverse=(delta > 0))
    for old_id in ids:
        new_id = old_id + delta
        Prompt.objects.filter(idPrompt=old_id).update(
            idPrompt=new_id,
            promptName=f'prompt-{new_id}',
        )


# ── Migration ops ──────────────────────────────────────────────────────

def add_reviewer_analyzer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')

    # 1) make room: 26..N -> 28..(N+2) so the Multi-Turn/ACPX block slides down
    _shift_block(Prompt, FIRST_SHIFTED_ID, SHIFT)

    # 2) seed the two new demos into the freed slots (idempotent on re-run)
    Prompt.objects.update_or_create(
        idPrompt=26,
        defaults={'promptName': 'prompt-26', 'promptContent': REVIEWER_DEMO},
    )
    Prompt.objects.update_or_create(
        idPrompt=27,
        defaults={'promptName': 'prompt-27', 'promptContent': ANALYZER_DEMO},
    )


def remove_reviewer_analyzer_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')

    # drop the two new demos, then slide the Multi-Turn/ACPX block back up
    Prompt.objects.filter(idPrompt__in=(26, 27)).delete()
    _shift_block(Prompt, FIRST_SHIFTED_ID + SHIFT, -SHIFT)


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0089_add_analyzer'),
    ]

    operations = [
        migrations.RunPython(
            add_reviewer_analyzer_demo_prompts,
            remove_reviewer_analyzer_demo_prompts,
        ),
    ]
