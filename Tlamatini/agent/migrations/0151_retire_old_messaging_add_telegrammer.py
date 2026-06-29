# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Retire the old messaging agents and wire the two new official-only agents.

Angela (2026-06-22) moved the old agent directories to Trash and asked for
exactly two messaging agents, each using ONLY the official service:

  * RETIRE  : Telegramer, TelegramRX, WhatsTlamatini  (dirs already trashed)
  * ADD     : Telegrammer  (the single Telegram send/receive agent, official
                             Telegram Bot API plus optional official user session)
  * KEEP    : Whatsapper    (rebuilt onto Meta WhatsApp Cloud API; row already
                             exists from migration 0009 — we just ensure its
                             wrapped-tool row is present)

It also seeds the two "wizard" Catalog-of-Prompts examples (Telegram + WhatsApp)
that walk a user through giving Tlamatini the one/two assets each needs.
"""
from django.db import migrations

RETIRE_AGENTS = ("Telegramer", "TelegramRX", "WhatsTlamatini")
RETIRE_TOOLS = ("Chat-Agent-Telegramer",)

NEW_AGENT = "Telegrammer"
NEW_TOOLS = ("Chat-Agent-Telegrammer", "Chat-Agent-Whatsapper")

# Two step-by-step wizard prompts (Multi-Turn + Step-by-Step). SAFE: they only
# GUIDE setup and ask the user for the asset(s) — no destructive action.
TELEGRAM_WIZARD = (
    "Tlamatini, run the **TELEGRAMMER SETUP WIZARD** for me, step by step. "
    "Tick Multi-Turn AND Step-by-Step. Goal: get my Telegram working with the "
    "Telegrammer agent. First, point me to the guide "
    "agent/agents/telegrammer/HOW_TO_GET_YOUR_TELEGRAM_ASSETS.md and ask me for "
    "the ONE required asset it needs — my **Bot Token** from @BotFather (and who to "
    "message as a readable @username). Give me ONE concrete action at a time and "
    "WAIT for my reply before the next. When I give the token, store it for the "
    "Telegrammer agent and send a test message, then confirm. End with END-RESPONSE."
)
WHATSAPP_WIZARD = (
    "Tlamatini, run the **WHATSAPPER SETUP WIZARD** for me, step by step. "
    "Tick Multi-Turn AND Step-by-Step. Goal: get my WhatsApp working with the "
    "Whatsapper agent using ONLY Meta's official WhatsApp Cloud API (no third "
    "party). First, point me to the guide "
    "agent/agents/whatsapper/HOW_TO_GET_YOUR_WHATSAPP_ASSETS.md and ask me for "
    "the TWO assets it needs — my **Phone number ID** and **Access token** from "
    "Meta. Give me ONE concrete action at a time and WAIT for my reply before the "
    "next. When I give them, store them for the Whatsapper agent and send a test "
    "(a hello_world template if it's a cold message), then confirm. End with END-RESPONSE."
)


def apply(apps, schema_editor):
    Agent = apps.get_model('agent', 'Agent')
    Tool = apps.get_model('agent', 'Tool')
    Prompt = apps.get_model('agent', 'Prompt')

    # 1) Retire old agents + their wrapped-tool rows.
    Agent.objects.filter(agentDescription__in=RETIRE_AGENTS).delete()
    Tool.objects.filter(toolDescription__in=RETIRE_TOOLS).delete()

    # 2) Add the new Telegrammer agent row (skip if somehow present).
    if not Agent.objects.filter(agentDescription=NEW_AGENT).exists():
        next_id = (Agent.objects.order_by('-idAgent').values_list('idAgent', flat=True).first() or 0) + 1
        Agent.objects.create(idAgent=next_id, agentName=f'agent-{next_id}',
                             agentDescription=NEW_AGENT, agentContent='true')

    # 3) Ensure both wrapped chat-agent Tool rows exist (enabled by default).
    for desc in NEW_TOOLS:
        if not Tool.objects.filter(toolDescription=desc).exists():
            next_id = (Tool.objects.order_by('-idTool').values_list('idTool', flat=True).first() or 0) + 1
            Tool.objects.create(idTool=next_id, toolName=f'tool-{next_id}',
                                toolDescription=desc, toolContent='true')

    # 4) Seed the two wizard catalog prompts, contiguously appended.
    for content in (TELEGRAM_WIZARD, WHATSAPP_WIZARD):
        next_id = (Prompt.objects.order_by('-idPrompt').values_list('idPrompt', flat=True).first() or 0) + 1
        Prompt.objects.update_or_create(
            idPrompt=next_id,
            defaults={'promptName': f'prompt-{next_id}', 'promptContent': content},
        )


def revert(apps, schema_editor):
    # Best-effort reverse: drop the new agent/tool/prompts. The old agents are
    # re-created by their original migrations if you migrate back past them.
    Agent = apps.get_model('agent', 'Agent')
    Tool = apps.get_model('agent', 'Tool')
    Prompt = apps.get_model('agent', 'Prompt')
    Agent.objects.filter(agentDescription=NEW_AGENT).delete()
    Tool.objects.filter(toolDescription='Chat-Agent-Telegrammer').delete()
    Prompt.objects.filter(promptContent__in=(TELEGRAM_WIZARD, WHATSAPP_WIZARD)).delete()


class Migration(migrations.Migration):
    dependencies = [('agent', '0150_add_chat_agent_discoverer_tool')]
    operations = [migrations.RunPython(apply, revert)]
