"""The Self-modify switch (Angela, 2026-10-03).

One more column on the Compact-mode row (pk=1, owned by
``agent/compact_mode.py``): the user's Self-modify choice.  Additive only - no
existing row changes meaning; the switch starts ON, which is exactly what a
self-able-modify build sent before the switch existed.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('agent', '0211_compact_state'),
    ]

    operations = [
        migrations.AddField(
            model_name='compactstate',
            name='self_modify',
            field=models.BooleanField(default=True),
        ),
    ]
