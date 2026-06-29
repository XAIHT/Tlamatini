# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Plain-text-only versions of the seven ACPX demos. The rich-HTML siblings
in 0072 (idPrompt 36-41) and 0073 (idPrompt 42-48) embed literal banner
blocks (<div style='...'>...) into the prompt text so the LLM would
mimic them; in practice that HTML leaks into the chat-message input box
and the user-message bubble in the chat history as raw, unreadable noise.

This migration adds short, readable paragraph versions (10-20 seconds
to scan) at slots idPrompt 29-35 — the FIRST ACPX block in the catalog,
ahead of the rich-HTML (36-41) and Gemini-pinned (42-48) blocks, because
"plain-text only, works against ANY resolvable agent_id, no API key
pin" is the lowest-complexity ACPX entry point. The LLM is still told
to render its OUTPUT with banners and tables (the chat output supports
HTML); only the *prompt text the user sends* is now plain-text-only.

Order within the group follows the same Health Parade → Skill Catalog →
Permission Gate → End-to-End Pipeline → ACPX Auditor → Multi-CLI Relay →
Gemini Live Reasoning learning progression used by the two sibling groups.

idempotent via update_or_create.
"""
from django.db import migrations


P25_HEALTH_PARADE = (
    "Tlamatini, run the ACPX Health and Roster Parade demo, please. "
    "Step 1: call acp_doctor and capture its details array. "
    "Step 2: call list_acp_agents and capture every entry, paying "
    "special attention to the resolvable flag. "
    "Step 3: render an HTML table titled 'Tlamatini ACPX Roster vs "
    "OpenClaw acp-router' with columns agent_id, command, description, "
    "resolvable_on_this_machine, openclaw_compatible. Every row is "
    "openclaw_compatible YES because the agent_id keys are identical "
    "in both projects. "
    "Step 4: call invoke_skill with skill_name 'hello-world' and "
    "args_json '{\"who\":\"angel\"}' to prove the in-process Skill "
    "harness is alive. "
    "Step 5: close with a short verdict line saying either "
    "'ACPX FULLY OPERATIONAL' if acp_doctor.ok is true, or "
    "'ACPX RUNTIME UP, PROBE AGENT NOT INSTALLED' otherwise. "
    "End with END-RESPONSE."
)

P26_SKILL_CARNIVAL = (
    "Tlamatini, run the Skill Catalog Carnival demo, please. "
    "Step 1: call list_skills with no filter and capture every entry. "
    "Step 2: render an HTML table titled 'Tlamatini Skill Catalog "
    "(Phase 3 Seed)' with columns name, description, runtime, "
    "acpx_agent_or_in_process, openclaw_droppable. Every row is "
    "openclaw_droppable YES because the SKILL.md frontmatter contract "
    "is OpenClaw-compatible verbatim. "
    "Step 3: call invoke_skill with skill_name 'summarize' and "
    "args_json '{\"text\":\"Tlamatini ACPX implements the same agent_id "
    "mapping and the same permissionMode vocabulary as OpenClaw, so "
    "any acp-router skill written for one project runs unmodified on "
    "the other.\",\"target_words\":40}'. Quote the resulting summary. "
    "Step 4: call invoke_skill with skill_name 'acp-router' and "
    "args_json '{\"intent\":\"reason about a complex codebase\","
    "\"prefer\":\"gemini\"}' and capture which agent_id it picks. "
    "Step 5: close with a one-line verdict naming the chosen agent_id. "
    "End with END-RESPONSE."
)

P27_PIPELINE = (
    "Tlamatini, run the End-to-End ACPX Pipeline demo, please. "
    "Step 1: call acp_doctor. If ok is false, fall back to invoke_skill "
    "summarize for every reasoning step instead of acp_spawn / acp_send, "
    "and announce the fallback in one short line. "
    "Step 2: call acp_spawn with agent_id 'gemini' and task 'Read the "
    "directory tree at C:/Development/Tlamatini/agent/ as a senior "
    "engineer reviewing a multi-agent framework. In 6 sentences, "
    "identify which subdirectory is the most architecturally important "
    "and explain why concretely.' and cwd 'C:/Development/Tlamatini'. "
    "Capture session_id and transcript_path. "
    "Step 3: call acp_send on that session_id with text 'Now propose a "
    "concrete improvement to that subdirectory in 4 sentences, "
    "prioritizing changes that help a new contributor.' Capture events. "
    "Step 4: call acp_kill on the session_id and confirm killed=true. "
    "Step 5: call invoke_skill skill_name 'summarize' with args_json "
    "'{\"text\":\"<paste joined text from spawn + send events>\","
    "\"target_words\":80}' to compress the transcript. "
    "Step 6: call chat_agent_file_creator with filepath "
    "'C:/Development/Tlamatini/_acpx_pipeline_demo_report.md' and "
    "content set to the summarized markdown plus a footer line "
    "stating the report was generated by Tlamatini ACPX. "
    "Step 7: call chat_agent_notifier with title 'ACPX Pipeline Demo' "
    "and a one-line completion message. "
    "Step 8: render an HTML table titled 'ACPX vs OpenClaw - this run' "
    "with columns behavior, covered_by_tlamatini, evidence and rows: "
    "spawn external CLI child; multi-turn conversation; graceful kill; "
    "transcript harvested to disk; downstream skill chained. Every row "
    "is YES; evidence cites session_id, transcript path, or audit_id. "
    "End with END-RESPONSE."
)

P28_PERMISSION_TOUR = (
    "Tlamatini, run the Permission Gate and Audit Tour demo, please. "
    "Step 1: call acp_doctor and report the active permissionMode and "
    "nonInteractivePermissions from its details. "
    "Step 2: render an HTML table titled 'ACPX Permission Modes - "
    "Tlamatini implements the OpenClaw matrix verbatim' with three "
    "rows (approve-reads, approve-all, deny-all) and four columns "
    "(mode, what_it_does, when_to_use, openclaw_equivalent). The "
    "openclaw_equivalent column equals the mode column on every row. "
    "Step 3: call invoke_skill with skill_name 'hello-world' and "
    "args_json '{\"who\":\"audit-tour\"}'. This will succeed and return "
    "an audit_id; capture and report it verbatim. "
    "Step 4: call invoke_skill with skill_name "
    "'__definitely_does_not_exist__' and args_json '{}'. This must "
    "fail with code UNKNOWN_SKILL; quote code and reason verbatim. "
    "Step 5: call list_skills with filter_keywords 'kyber' to "
    "demonstrate keyword filtering on the registry. "
    "Step 6: close with a one-line verdict naming the audit_id from "
    "Step 3 so the user can locate the per-invocation NDJSON file under "
    "~/.tlamatini/skill-audit/. End with END-RESPONSE."
)

P29_RELAY = (
    "Tlamatini, run the Multi-CLI ACPX Relay demo, please. "
    "Step 1: call acp_doctor and capture its details array. "
    "Step 2: call list_acp_agents. Pin leg A to agent_id 'gemini'. For "
    "leg B, pick the first resolvable agent_id from the list that is "
    "not gemini. If only gemini is resolvable, simulate leg B with "
    "invoke_skill skill_name 'summarize' and announce the fallback in "
    "one short line. "
    "Step 3 (LEG A - gemini): call acp_spawn with agent_id 'gemini' "
    "and task 'You are a senior systems architect. In one paragraph "
    "(max 6 sentences), describe the trade-offs of an HTTP-based "
    "webhook gateway vs a WebSocket-based chat gateway for triggering "
    "automation pipelines. Be concrete and opinionated.' Capture "
    "session_id_A and the events. Then call acp_kill on session_id_A. "
    "Step 4 (LEG B - peer): call acp_spawn with the second agent_id "
    "(or simulate via invoke_skill summarize per Step 2) and task "
    "'Read the following analysis from a peer ACP agent and produce a "
    "4-bullet verdict that either AGREES, REFUTES, or EXTENDS each "
    "point. Be specific. Analysis: <paste leg A text here>'. Capture "
    "session_id_B and events; then call acp_kill on session_id_B. "
    "Step 5: render an HTML table titled 'Multi-CLI Relay - covered "
    "behaviors' with columns behavior, leg_a_agent, leg_b_agent, "
    "openclaw_pattern_match and rows (spawn first child, harvest "
    "transcript, hand-off content, spawn second child with first "
    "transcript as input, dual graceful kill). openclaw_pattern_match "
    "is YES on every row. "
    "Step 6: close with a one-line verdict naming the two agent_ids "
    "actually used. End with END-RESPONSE."
)

P30_AUDITOR = (
    "Tlamatini, run the ACPX Auditor's Replay demo, please. "
    "Step 1: call invoke_skill with skill_name 'hello-world' and "
    "args_json '{\"who\":\"auditor\"}' to guarantee a fresh audit "
    "record on disk. Capture the returned audit_id. "
    "Step 2: call acp_doctor and report the active stateDir from its "
    "details. "
    "Step 3: call execute_command with command 'dir /b /o:-d "
    "%USERPROFILE%\\.tlamatini\\skill-audit 2>NUL || ls -1t "
    "~/.tlamatini/skill-audit/ 2>/dev/null' to list audit-month "
    "subdirectories. "
    "Step 4: call execute_command with command 'dir /b /s /o:-d "
    "%USERPROFILE%\\.tlamatini\\skill-audit\\*hello_world*auditor* "
    "2>NUL || find ~/.tlamatini/skill-audit -name "
    "\"*hello_world*auditor*\" 2>/dev/null | head -1 || true' to "
    "locate the NDJSON file matching the audit_id from Step 1. "
    "Step 5: call chat_agent_file_extractor with filepath set to the "
    "located NDJSON path so we can read the structured event stream. "
    "Step 6: call invoke_skill with skill_name 'summarize' and "
    "args_json '{\"text\":\"<paste joined NDJSON event lines here>\","
    "\"target_words\":60}' to produce a human-readable replay narrative. "
    "Step 7: render an HTML table titled 'Audit Trail - what is on "
    "disk' with columns artifact, location, format, "
    "openclaw_equivalent_present and three rows for "
    "skill_invocation_audit, acp_session_transcript, "
    "acp_session_record (all NDJSON or JSON, all YES). "
    "Step 8: close with a one-line verdict naming the audit_id from "
    "Step 1 and the absolute NDJSON path located in Step 4. End with "
    "END-RESPONSE."
)

P31_GEMINI_LIVE = (
    "Tlamatini, run the Gemini Live Reasoning Showcase demo, please. "
    "Step 1: call acp_doctor and confirm the probe agent is gemini. "
    "If ok is false, report 'Gemini is not on PATH - install "
    "@google/gemini-cli, then retry.' and END-RESPONSE immediately. "
    "Otherwise proceed. "
    "Step 2 (TURN 1): call acp_spawn with agent_id 'gemini', cwd "
    "'C:/Development/Tlamatini', and task 'You are advising a solo "
    "developer building a self-hosted AI developer assistant. List, "
    "in one short paragraph, the three most underrated architectural "
    "pillars of such a system - pillars whose importance only becomes "
    "obvious after 12+ months of usage. Be concrete; cite specific "
    "failure modes that show up if a pillar is absent.' Capture "
    "session_id and the events; quote them under heading 'Turn 1 - "
    "Gemini speaks'. "
    "Step 3 (TURN 2): call acp_send on the same session_id with text "
    "'Of those three pillars, pick the ONE you would prioritize for "
    "the next 30 days of work, and write a 4-line action plan "
    "describing what to ship, in what order, with what success "
    "metric.' Quote the events under heading 'Turn 2 - the plan'. "
    "Step 4 (TURN 3): call acp_send on the same session_id with text "
    "'Now anticipate the most likely way that 30-day plan will fail. "
    "Write a 3-line risk register: each line names the failure mode, "
    "the early-warning signal, and the cheapest mitigation.' Quote "
    "the events under heading 'Turn 3 - the risk register'. "
    "Step 5: call acp_kill on session_id and confirm killed=true. "
    "Step 6: call invoke_skill with skill_name 'summarize' and "
    "args_json '{\"text\":\"<paste joined text from turns 1+2+3>\","
    "\"target_words\":120}'. Quote the digest under heading "
    "'Executive Digest'. "
    "Step 7: call chat_agent_file_creator with filepath "
    "'C:/Development/Tlamatini/_gemini_live_reasoning.md' and content "
    "set to a markdown report containing all three turns and the "
    "executive digest, with a footer noting the report was generated "
    "by Tlamatini ACPX through a real Gemini child. "
    "Step 8: call chat_agent_notifier with title 'Gemini Live "
    "Reasoning' and a one-line completion message. "
    "Step 9: render an HTML table titled 'Gemini Live Reasoning - "
    "Capability Scoreboard' with columns capability, "
    "demonstrated_this_run, evidence and rows: real_external_LLM_spawned; "
    "api_key_injected_via_acpx_env; multi_turn_conversation_3_turns; "
    "transcript_persisted_NDJSON; downstream_skill_chained; "
    "audit_trail_written; openclaw_protocol_compatible. "
    "demonstrated_this_run is YES on every row; evidence cites "
    "session_id, transcript path, audit_id, or output filepath. "
    "End with END-RESPONSE."
)


DEMO_PROMPTS = [
    (29, P25_HEALTH_PARADE),
    (30, P26_SKILL_CARNIVAL),
    (31, P28_PERMISSION_TOUR),
    (32, P27_PIPELINE),
    (33, P30_AUDITOR),
    (34, P29_RELAY),
    (35, P31_GEMINI_LIVE),
]


def simplify_demo_prompts(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for id_prompt, content in DEMO_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=id_prompt,
            defaults={
                'promptName': f'prompt-{id_prompt}',
                'promptContent': content,
            },
        )


def downgrade_simplified_demo_prompts(apps, schema_editor):
    # Drop the plain-text slots this migration introduced (29-35).
    # The rich-HTML versions at 36-41 (from 0072) and Gemini-pinned
    # versions at 42-48 (from 0073) are untouched, so a partial rollback
    # leaves a coherent catalog (1-28 + 36-48).
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=(29, 30, 31, 32, 33, 34, 35)).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0073_acpx_demo_gemini_uplift'),
    ]

    operations = [
        migrations.RunPython(
            simplify_demo_prompts,
            downgrade_simplified_demo_prompts,
        ),
    ]
