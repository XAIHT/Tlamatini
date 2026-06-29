# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Seed four ACPX + Skills demo prompts that exercise every tool in the new
ACPX/Skills surface (acp_doctor, list_acp_agents, acp_spawn, acp_send,
acp_kill, list_skills, invoke_skill) and explicitly frame the output as
parity-with-OpenClaw so the user can see, in one Multi-Turn run, that
Tlamatini covers the full ACPX mechanism.

Slots: idPrompt 36-41 (placed AFTER the simplified plain-text versions at
29-35 from 0074 so the catalog ramps from "easy to read" to "visually
loud, HTML-leaky"). Order within the group follows the same learning
progression used by the simplified and Gemini-pinned siblings: Health
Parade → Skill Catalog → Permission Gate → End-to-End Pipeline →
ACPX Auditor → Multi-CLI Relay.
"""
from django.db import migrations


def add_acpx_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')

    Prompt.objects.get_or_create(
        idPrompt=36,
        defaults={
            'promptName': 'prompt-36',
            'promptContent': (
                "Tlamatini, run the **ACPX Health & Roster Parade** demo, please. "
                "Step 1: open the report with a flashy banner — emit one HTML block "
                "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#ff5f3a 0%,#ff8b5e 30%,#9d3bff 65%,#0d0d12 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
                "<h2 style='margin:0;letter-spacing:2px;'>&#128293; ACPX HEALTH &amp; ROSTER PARADE &#128293;</h2>"
                "<div style='opacity:.9;margin-top:4px;'>Tlamatini ACPX &mdash; OpenClaw-parity demonstration</div></div>. "
                "Step 2: call **acp_doctor** and capture its `details` array. "
                "Step 3: call **list_acp_agents** and capture every entry, paying special attention to the `resolvable` flag. "
                "Step 4: render an HTML table with class='exec-report-table' titled "
                "'Tlamatini ACPX Roster vs. OpenClaw acp-router' whose columns are "
                "agent_id, command, description, resolvable_on_this_machine, openclaw_compatible "
                "(every row is openclaw_compatible='YES' because the agent_id keys are identical "
                "in both projects, per ACPX.md section 3.5). "
                "Step 5: call **invoke_skill** with skill_name='hello-world' and args_json='{\"who\":\"angel\"}' "
                "to prove the in-process Skill harness is alive end-to-end. "
                "Step 6: close with another HTML banner that prints, in big letters, "
                "either 'ACPX FULLY OPERATIONAL' (if acp_doctor.ok is true) or "
                "'ACPX RUNTIME UP, PROBE AGENT NOT INSTALLED' (if acp_doctor.ok is false but "
                "list_acp_agents returned at least one entry); the runtime is healthy in both "
                "cases because the Skill harness ran. End with END-RESPONSE."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=37,
        defaults={
            'promptName': 'prompt-37',
            'promptContent': (
                "Tlamatini, run the **Skill Catalog Carnival** demo, please. "
                "Step 1: emit an opening HTML banner "
                "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#7a1bff 0%,#3b5bff 35%,#13c2e0 70%,#1de9b6 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
                "<h2 style='margin:0;letter-spacing:2px;'>&#127881; SKILL CATALOG CARNIVAL &#127881;</h2>"
                "<div style='opacity:.9;margin-top:4px;'>20 seed skills &mdash; OpenClaw-format compatible</div></div>. "
                "Step 2: call **list_skills** with no filter and capture every entry. "
                "Step 3: render an HTML table with class='exec-report-table' titled "
                "'Tlamatini Skill Catalog (Phase 3 Seed)' whose columns are "
                "name, description, runtime, acpx_agent_or_in_process, openclaw_droppable. "
                "openclaw_droppable should be 'YES' for every skill because the SKILL.md "
                "frontmatter contract is OpenClaw-compatible verbatim per ACPX.md section 4.2. "
                "Step 4: call **invoke_skill** with skill_name='summarize' and "
                "args_json='{\"text\":\"Tlamatini ACPX implements the same agent_id mapping "
                "(claude, cursor, codex, copilot, gemini, qwen, pi, droid, iflow, kilocode, "
                "kimi, kiro, opencode) and the same permissionMode vocabulary (approve-reads, "
                "approve-all, deny-all) as OpenClaw, so any acp-router skill written for one "
                "project runs unmodified on the other.\",\"target_words\":40}'. "
                "Step 5: call **invoke_skill** with skill_name='acp-router' and "
                "args_json='{\"intent\":\"refactor a Python file\",\"prefer\":\"claude\"}' "
                "and capture which agent_id it picks. "
                "Step 6: close with an HTML banner that says, in big letters, "
                "'PARITY: 20 SKILLS, 14 ACP AGENTS, 1 PROTOCOL' and a one-line subtitle "
                "summarizing how the acp-router skill chose the agent. End with END-RESPONSE."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=39,
        defaults={
            'promptName': 'prompt-39',
            'promptContent': (
                "Tlamatini, run the **End-to-End ACPX Pipeline** demo, please &mdash; "
                "the showcase that proves Tlamatini covers OpenClaw's ACPX mechanism end to end. "
                "Step 1: emit an opening HTML banner "
                "<div style='padding:20px;border-radius:14px;background:linear-gradient(135deg,#ff2e63 0%,#ff8b3d 25%,#ffd23f 50%,#2ec4b6 75%,#0a0a23 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
                "<h2 style='margin:0;letter-spacing:2px;'>&#9889; END-TO-END ACPX PIPELINE &#9889;</h2>"
                "<div style='opacity:.9;margin-top:4px;'>spawn &rarr; converse &rarr; harvest &rarr; summarize &rarr; persist &rarr; notify</div></div>. "
                "Step 2: call **acp_doctor**; if `ok` is false, fall back to the in-process "
                "skill path and announce the fallback in a yellow HTML banner, but still "
                "complete every remaining step using the Skill harness. "
                "Step 3: call **acp_spawn** with agent_id='claude' (or whichever the doctor "
                "reports as resolvable; if none, simulate this step using **invoke_skill** "
                "with skill_name='summarize') and task='List the immediate children of the "
                "agent/ directory and describe each in one sentence.', cwd='C:/Development/Tlamatini'. "
                "Capture the returned session_id and transcript_path. "
                "Step 4: call **acp_send** on that session_id with text='Now identify which "
                "of those children would be the right place to add a new ACP agent_id called "
                "kimi-2.' Capture the events. "
                "Step 5: call **acp_kill** on the session_id and confirm killed=true. "
                "Step 6: call **invoke_skill** with skill_name='summarize' and "
                "args_json='{\"text\":\"<paste the joined text from the spawn + send events "
                "you collected above>\",\"target_words\":80}' to compress the transcript. "
                "Step 7: call **chat_agent_file_creator** with filepath="
                "'C:/Development/Tlamatini/_acpx_pipeline_demo_report.md' and content="
                "'<the summarized markdown plus a footer line that reads: \"Generated by "
                "Tlamatini ACPX &mdash; functional parity with OpenClaw confirmed.\"\\n>'. "
                "Step 8: call **chat_agent_notifier** with title='ACPX Pipeline Demo' and "
                "message='spawn &rarr; send &rarr; kill &rarr; summarize &rarr; persist &mdash; complete.'. "
                "Step 9: render an HTML closing banner with class='exec-report-table' "
                "titled 'ACPX vs OpenClaw &mdash; this run' showing five rows "
                "(spawn child process, multi-turn conversation, graceful kill, transcript "
                "harvested to disk, downstream skill chained) where every row's "
                "'covered_by_tlamatini' column is YES. End with END-RESPONSE."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=41,
        defaults={
            'promptName': 'prompt-41',
            'promptContent': (
                "Tlamatini, run the **Multi-CLI ACPX Relay** demo, please &mdash; the "
                "showcase that proves Tlamatini can orchestrate two distinct ACP children "
                "back-to-back, exactly like OpenClaw's multi-agent acp-router pattern. "
                "Step 1: emit an opening HTML banner "
                "<div style='padding:20px;border-radius:14px;background:linear-gradient(135deg,#00d4ff 0%,#7b2cbf 30%,#ff006e 65%,#fb5607 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
                "<h2 style='margin:0;letter-spacing:2px;'>&#128260; MULTI-CLI ACPX RELAY &#128260;</h2>"
                "<div style='opacity:.9;margin-top:4px;'>claude &rarr; transcript hand-off &rarr; gemini &rarr; verdict</div></div>. "
                "Step 2: call **acp_doctor** and capture the `details` array. "
                "Step 3: call **list_acp_agents** and pick TWO distinct resolvable agent_ids "
                "from the result. Prefer claude as the first leg and gemini as the second; "
                "if either is unresolvable, fall back to qwen, then cursor, then any "
                "remaining resolvable entry. If fewer than two are resolvable, simulate the "
                "second leg with **invoke_skill** skill_name='summarize' and announce that "
                "fallback in a yellow HTML banner that explicitly names which agent_id was "
                "missing &mdash; the demo still completes either way. "
                "Step 4 (LEG A): call **acp_spawn** with the first agent_id and task="
                "'In one paragraph, describe the trade-offs of an HTTP-based webhook gateway "
                "vs. a WebSocket-based chat gateway for triggering automation pipelines.' "
                "Capture session_id_A and the events. Then call **acp_kill** on session_id_A. "
                "Step 5: render an HTML <blockquote style='border-left:4px solid #7b2cbf;"
                "padding:8px 14px;background:#f5f0ff;'>...</blockquote> containing the "
                "joined text from leg A so the user can SEE what was relayed. "
                "Step 6 (LEG B): call **acp_spawn** with the second agent_id (or simulate "
                "via invoke_skill summarize per Step 3) and task='Read the following analysis "
                "from a peer ACP agent and produce a 4-bullet HTML <ul> verdict that either "
                "agrees, refutes, or extends each point. Analysis: <paste leg A text here>'. "
                "Capture session_id_B and the events; then call **acp_kill** on session_id_B. "
                "Step 7: render an HTML table with class='exec-report-table' titled "
                "'Multi-CLI Relay &mdash; covered behaviors' with columns "
                "(behavior, leg_a_agent, leg_b_agent, openclaw_pattern_match) and rows "
                "(spawn first child, harvest transcript, hand-off content, spawn second child "
                "with first transcript as input, dual graceful kill). The "
                "openclaw_pattern_match column is YES on every row because OpenClaw's "
                "documented multi-agent acp-router relay does exactly this sequence. "
                "Step 8: close with an HTML banner that prints, in big letters, "
                "'TWO CLIs &mdash; ONE PIPELINE &mdash; ZERO BRANDING' and a one-line subtitle "
                "naming the two agent_ids actually used. End with END-RESPONSE."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=40,
        defaults={
            'promptName': 'prompt-40',
            'promptContent': (
                "Tlamatini, run the **ACPX Auditor's Replay** demo, please &mdash; the "
                "showcase that proves the on-disk transcript and skill-audit trails are real, "
                "structured, and replayable, exactly the way OpenClaw's audit story promises. "
                "Step 1: emit an opening HTML banner "
                "<div style='padding:20px;border-radius:14px;background:linear-gradient(135deg,#1b1b3a 0%,#693668 35%,#a74482 70%,#f1c453 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
                "<h2 style='margin:0;letter-spacing:2px;'>&#128196; ACPX AUDITOR&#39;S REPLAY &#128196;</h2>"
                "<div style='opacity:.9;margin-top:4px;'>NDJSON on disk &mdash; structured &mdash; replayable</div></div>. "
                "Step 2: call **invoke_skill** with skill_name='hello-world' and "
                "args_json='{\"who\":\"auditor\"}' to GUARANTEE we have at least one fresh "
                "audit record on disk. Capture the returned audit_id. "
                "Step 3: call **acp_doctor** and report the active stateDir from its details. "
                "Step 4: call **execute_command** with command='dir /b /o:-d "
                "%USERPROFILE%\\.tlamatini\\skill-audit 2>NUL || ls -1t ~/.tlamatini/skill-audit/ 2>/dev/null' "
                "to list the most recent audit-month subdirectories. (Use whichever shell "
                "syntax matches the host platform; both are included so the demo runs on "
                "Windows or POSIX.) "
                "Step 5: call **execute_command** with command="
                "'dir /b /o:-d %USERPROFILE%\\.tlamatini\\skill-audit\\* 2>NUL | findstr /i hello_world | findstr /i auditor || ls -1t ~/.tlamatini/skill-audit/*/ 2>/dev/null | grep -i hello_world | grep -i auditor || true' "
                "to locate the NDJSON file matching the audit_id captured in Step 2. "
                "Step 6: call **chat_agent_file_extractor** with filepath set to the "
                "located NDJSON path so we can read the structured event stream. "
                "Step 7: call **invoke_skill** with skill_name='summarize' and "
                "args_json='{\"text\":\"<paste the joined NDJSON event lines here>\","
                "\"target_words\":60}' to produce a human-readable replay narrative of "
                "what happened during that hello-world invocation. "
                "Step 8: render an HTML table with class='exec-report-table' titled "
                "'Audit Trail &mdash; What's Actually On Disk' with columns "
                "(artifact, location, format, openclaw_equivalent_present) and three rows: "
                "skill_invocation_audit (~/.tlamatini/skill-audit/&lt;YYYY-MM&gt;/&lt;...&gt;.ndjson, NDJSON, YES), "
                "acp_session_transcript (&lt;stateDir&gt;/&lt;session&gt;.transcript.ndjson, NDJSON, YES), "
                "acp_session_record (&lt;stateDir&gt;/&lt;session&gt;.json, JSON, YES). "
                "Step 9: close with an HTML banner that prints, in big letters, "
                "'EVERY ACTION &mdash; EVERY EVENT &mdash; ON DISK' and a one-line subtitle "
                "naming the audit_id from Step 2 and the absolute path of the NDJSON "
                "file located in Step 5 so the user can open it with any text editor "
                "and verify the replay byte-for-byte. End with END-RESPONSE."
            ),
        }
    )

    Prompt.objects.get_or_create(
        idPrompt=38,
        defaults={
            'promptName': 'prompt-38',
            'promptContent': (
                "Tlamatini, run the **ACPX Permission Gate &amp; Audit Tour** demo, please. "
                "Step 1: emit an opening HTML banner "
                "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,#0a0a23 0%,#3a0ca3 30%,#7209b7 60%,#f72585 100%);color:#fff;font-family:Inter,Segoe UI,sans-serif;text-align:center;'>"
                "<h2 style='margin:0;letter-spacing:2px;'>&#128274; PERMISSION GATE &amp; AUDIT TOUR &#128274;</h2>"
                "<div style='opacity:.9;margin-top:4px;'>three modes &mdash; one gate &mdash; full audit trail</div></div>. "
                "Step 2: call **acp_doctor** and report what permissionMode and "
                "nonInteractivePermissions are currently active in the runtime. "
                "Step 3: render an HTML table titled "
                "'ACPX Permission Modes &mdash; Tlamatini implements the OpenClaw matrix verbatim' "
                "with three rows (approve-reads, approve-all, deny-all) and four columns "
                "(mode, what_it_does, when_to_use, openclaw_equivalent). The "
                "openclaw_equivalent column is the same string as `mode` for all three rows "
                "because the vocabulary is identical (per ACPX.md section 3.3). "
                "Step 4: call **invoke_skill** with skill_name='hello-world' and "
                "args_json='{\"who\":\"audit-tour\"}' &mdash; this WILL succeed and produce an "
                "audit_id; capture and report that audit_id. "
                "Step 5: call **invoke_skill** with skill_name='__definitely_does_not_exist__' "
                "and args_json='{}' &mdash; this MUST fail with code='UNKNOWN_SKILL'; capture the "
                "failure envelope and quote the `code` and `reason` fields verbatim. "
                "Step 6: call **list_skills** with filter_keywords='kyber' to demonstrate "
                "keyword filtering on the registry (returns zero or more entries; either is "
                "acceptable as a demonstration of the filter mechanism). "
                "Step 7: render an HTML closing banner that prints, in big letters, "
                "'GATE ENFORCED &mdash; AUDIT WRITTEN &mdash; PARITY PROVEN' with a one-line "
                "subtitle naming the captured audit_id from Step 4 so the user can locate "
                "the per-invocation NDJSON file under ~/.tlamatini/skill-audit/. "
                "End with END-RESPONSE."
            ),
        }
    )


def remove_acpx_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=(36, 37, 38, 39, 40, 41)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0071_acpx_skills'),
    ]

    operations = [
        migrations.RunPython(
            add_acpx_demo_prompts,
            remove_acpx_demo_prompts,
        ),
    ]
