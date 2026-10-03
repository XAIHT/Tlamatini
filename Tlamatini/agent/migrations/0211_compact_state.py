"""The Compact-mode switch (Angela, 2026-10-02).

ONE row (pk=1) owned by ``agent/compact_mode.py``: whether Compact mode is ON,
whether the current model locks it ON (strict), and the External-MCP active
list saved while Compact mode pauses it.  Additive only - no existing row is
touched; the switch starts OFF.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0210_strict_visual_analysis_prompt_contract'),
    ]

    operations = [
        migrations.CreateModel(
            name='CompactState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('active', models.BooleanField(default=False)),
                ('strict', models.BooleanField(default=False)),
                ('model', models.CharField(blank=True, default='', max_length=200)),
                ('window_tokens', models.IntegerField(default=0)),
                ('saved_external_active', models.TextField(blank=True, default='[]')),
                ('reason', models.CharField(blank=True, default='', max_length=300)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Compact mode state',
                'verbose_name_plural': 'Compact mode state',
            },
        ),
    ]
