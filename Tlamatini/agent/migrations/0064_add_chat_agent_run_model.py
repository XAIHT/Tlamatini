from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0063_add_agent_parametrizer_prompt"),
    ]

    operations = [
        migrations.CreateModel(
            name="ChatAgentRun",
            fields=[
                ("runId", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("toolDescription", models.CharField(max_length=200)),
                ("templateAgentDir", models.CharField(max_length=200)),
                ("runtimeDir", models.CharField(max_length=1000)),
                ("logPath", models.CharField(max_length=1000)),
                ("requestText", models.TextField(blank=True)),
                ("pid", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(default="created", max_length=32)),
                ("exitCode", models.IntegerField(blank=True, null=True)),
                ("startedAt", models.DateTimeField(auto_now_add=True)),
                ("finishedAt", models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
