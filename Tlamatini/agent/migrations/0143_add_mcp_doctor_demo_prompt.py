from django.db import migrations


MCP_DOCTOR_DEMO = (
    "Tlamatini, run the **MCP DOCTOR** demo, please &mdash; a safe External MCP "
    "catalog diagnostic driven entirely through the wrapped **chat_agent_mcp_doctor** "
    "tool. Tick ONLY the **Multi-Turn** checkbox before sending. Use ONLY "
    "chat_agent_mcp_doctor; do NOT use chat_agent_executer, chat_agent_pythonxer, "
    "or acp_spawn. "
    "\\n\\n"
    "Step 0: open with one HTML banner: "
    "<div style='padding:18px;border-radius:14px;background:linear-gradient(135deg,"
    "#0F3D3E 0%,#1E7B73 33%,#E0A83A 66%,#FFF2C6 100%);color:#fff;font-family:Inter,"
    "Segoe UI,sans-serif;text-align:center;text-shadow:0 1px 3px rgba(0,0,0,.45);'>"
    "<h2 style='margin:0;letter-spacing:2px;'>MCP DOCTOR</h2>"
    "<div style='opacity:.92;margin-top:4px;'>External MCP catalog &middot; runtime &middot; transport &middot; setup readiness</div></div>. "
    "\\n\\n"
    "Step 1: call **chat_agent_mcp_doctor** with request "
    "\"Run MCP Doctor with mode='catalog'\". Read the JSON return and the "
    "INI_SECTION_MCP_DOCTOR block in log_excerpt. Capture status, server_key, "
    "transport, runtime, supported, catalog_path, and the response_body. "
    "\\n\\n"
    "Step 2: render one compact HTML table with class='exec-report-table' titled "
    "'<strong>MCP Doctor &mdash; Catalog Readiness</strong>' and columns "
    "<em>field</em> and <em>value</em>. Include at least catalog_path, status, "
    "server_key, transport, runtime, supported, and the first next-step sentence "
    "from the response body. "
    "\\n\\n"
    "Step 3: close with one sentence telling the user the next MCP setup action. "
    "End with END-RESPONSE."
)

_NEW_PROMPTS = (
    (81, MCP_DOCTOR_DEMO),
)


def add_mcp_doctor_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, content in _NEW_PROMPTS:
        Prompt.objects.update_or_create(
            idPrompt=prompt_id,
            defaults={'promptName': f'prompt-{prompt_id}', 'promptContent': content},
        )


def remove_mcp_doctor_demo_prompt(apps, schema_editor):
    Prompt = apps.get_model('agent', 'Prompt')
    Prompt.objects.filter(idPrompt__in=[pid for pid, _ in _NEW_PROMPTS]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('agent', '0142_add_chat_agent_mcp_doctor_tool'),
    ]

    operations = [
        migrations.RunPython(add_mcp_doctor_demo_prompt, remove_mcp_doctor_demo_prompt),
    ]
