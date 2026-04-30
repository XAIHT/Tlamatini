"""
Migration for ACPX + Skills models.

Creates four new tables:
    - AcpAgent          — registered ACP agent_ids (claude/cursor/...)
    - Skill             — registered SKILL.md packages
    - AcpSession        — one row per ACP child-process session
    - SkillInvocation   — one row per SkillHarness invocation (audit trail)

Also seeds two new Tool rows so the existing tool-toggle UI exposes the
new ACPX tools and the skill-runner tools to the operator. The existing
seed pattern (idTool primary key, toolName/toolDescription/toolContent)
is preserved.
"""
from django.db import migrations, models


def seed_acpx_tools(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    base_seed = [
        ("acpx-spawn",         "ACP spawn",      "true"),
        ("acpx-send",          "ACP send",       "true"),
        ("acpx-kill",          "ACP kill",       "true"),
        ("acpx-doctor",        "ACP doctor",     "true"),
        ("acpx-list-agents",   "ACP list agents","true"),
        ("acpx-invoke-skill",  "Invoke skill",   "true"),
        ("acpx-list-skills",   "List skills",    "true"),
    ]
    # Pick a free idTool block well above the existing range.
    next_id = (Tool.objects.order_by("-idTool").first().idTool + 1) if Tool.objects.exists() else 1
    next_id = max(next_id, 200)
    for name, desc, content in base_seed:
        if not Tool.objects.filter(toolName=name).exists():
            Tool.objects.create(
                idTool=next_id, toolName=name,
                toolDescription=desc, toolContent=content,
            )
            next_id += 1


def unseed_acpx_tools(apps, schema_editor):
    Tool = apps.get_model("agent", "Tool")
    Tool.objects.filter(toolName__in=[
        "acpx-spawn", "acpx-send", "acpx-kill", "acpx-doctor",
        "acpx-list-agents", "acpx-invoke-skill", "acpx-list-skills",
    ]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("agent", "0070_add_teletlamatini"),
    ]

    operations = [
        migrations.CreateModel(
            name="AcpAgent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("agent_id", models.CharField(max_length=64, unique=True)),
                ("command", models.CharField(max_length=512)),
                ("description", models.CharField(blank=True, default="", max_length=500)),
                ("enabled", models.BooleanField(default=True)),
                ("healthy", models.BooleanField(default=False)),
                ("last_probe_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
            ],
            options={"verbose_name": "ACP Agent", "verbose_name_plural": "ACP Agents"},
        ),
        migrations.CreateModel(
            name="Skill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("runtime", models.CharField(default="in-process", max_length=32)),
                ("acpx_agent", models.CharField(blank=True, default="", max_length=64)),
                ("enabled", models.BooleanField(default=True)),
                ("frontmatter_json", models.TextField(blank=True, default="")),
                ("body_sha256", models.CharField(blank=True, default="", max_length=64)),
                ("last_loaded_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "Skill", "verbose_name_plural": "Skills"},
        ),
        migrations.CreateModel(
            name="AcpSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("session_uuid", models.CharField(max_length=64, unique=True)),
                ("agent_id", models.CharField(max_length=64)),
                ("cwd", models.CharField(blank=True, default="", max_length=1024)),
                ("state_path", models.CharField(blank=True, default="", max_length=1024)),
                ("transcript_path", models.CharField(blank=True, default="", max_length=1024)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("ended_at", models.DateTimeField(blank=True, null=True)),
                ("ok", models.BooleanField(blank=True, null=True)),
                ("pid", models.IntegerField(blank=True, null=True)),
                ("label", models.CharField(blank=True, default="", max_length=200)),
                ("user", models.ForeignKey(blank=True, null=True,
                                            on_delete=models.deletion.CASCADE,
                                            related_name="acp_sessions",
                                            to="auth.user")),
            ],
        ),
        migrations.CreateModel(
            name="SkillInvocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name="ID")),
                ("skill_name", models.CharField(max_length=128)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("ok", models.BooleanField(blank=True, null=True)),
                ("iterations", models.IntegerField(blank=True, null=True)),
                ("tokens", models.IntegerField(blank=True, null=True)),
                ("args_json", models.TextField(blank=True, default="")),
                ("output_json", models.TextField(blank=True, default="")),
                ("audit_path", models.CharField(blank=True, default="", max_length=1024)),
                ("failure_reason", models.CharField(blank=True, default="", max_length=64)),
                ("acp_session", models.ForeignKey(blank=True, null=True,
                                                   on_delete=models.deletion.SET_NULL,
                                                   related_name="skill_invocations",
                                                   to="agent.acpsession")),
                ("user", models.ForeignKey(blank=True, null=True,
                                            on_delete=models.deletion.CASCADE,
                                            related_name="skill_invocations",
                                            to="auth.user")),
            ],
        ),
        migrations.RunPython(seed_acpx_tools, unseed_acpx_tools),
    ]
