"""Print 3.5 s, not 10 s, as the Whisperer silence-window default (2026-09-18).

Angela: "set the default silence everywhere it corresponds to 3.5 seconds".

The sound gate's REAL default moved from 10 s to 3.5 s in
``agents/whisperer/config.yaml`` and ``whisperer.py::GATE_SILENCE_TIMEOUT_SECONDS``.
Three catalog cards PRINT that default back to the user in a ``[[ ... ]]``
fill-in line, and a card that promises 10 s while the agent actually stops after
3.5 s is a lie the user only discovers mid-sentence -- so the text moves with the
code, in the same pass.

Rows touched: prompt 74 (TLAMATINI LISTENS), 121 (YOUR FIRST VOICE COMMAND),
122 (SPEAK YOUR PROMPT).

CONTRACT -- identical to the 0182-0185 grammar batch and to 0200: this migration
rewrites ONLY ``promptContent``, and inside it only the one fill-in line that
states the default. ``idPrompt`` / ``promptName`` / ``category`` / ``sort_rank``
/ ``hidden`` are untouched, so catalog ordering, contiguity and the VOICE
COMMANDS section opener are all unaffected. Each swap is a literal string
replace that is a silent NO-OP when the row does not carry the old text, so a
hand-edited database is never clobbered and re-running is harmless.
"""

from django.db import migrations


# (idPrompt, text as it stands today, text it becomes).
# Prompt 74 writes its dashes as the HTML entity; 121/122 use a real em dash.
_SWAPS = (
    (74,
     "should end the recording? &mdash; OPTIONAL, default: 10 ]]",
     "should end the recording? &mdash; OPTIONAL, default: 3.5 ]]"),
    (121,
     "[[ silence_timeout_seconds — OPTIONAL, default: 10 ]]",
     "[[ silence_timeout_seconds — OPTIONAL, default: 3.5 ]]"),
    (122,
     "[[ silence_timeout_seconds — OPTIONAL, default: 10 ]]",
     "[[ silence_timeout_seconds — OPTIONAL, default: 3.5 ]]"),
)


def _retext(apps, swaps):
    Prompt = apps.get_model('agent', 'Prompt')
    for prompt_id, old, new in swaps:
        row = Prompt.objects.filter(idPrompt=prompt_id).first()
        if row is None:
            continue
        content = row.promptContent or ''
        if old not in content:
            continue
        row.promptContent = content.replace(old, new)
        row.save(update_fields=['promptContent'])


def set_silence_default_to_three_point_five(apps, schema_editor):
    _retext(apps, _SWAPS)


def restore_ten_second_silence_default(apps, schema_editor):
    _retext(apps, tuple((pid, new, old) for pid, old, new in _SWAPS))


class Migration(migrations.Migration):

    dependencies = [('agent', '0204_add_pptxer_demo_prompts')]

    operations = [
        migrations.RunPython(
            set_silence_default_to_three_point_five,
            restore_ten_second_silence_default,
        ),
    ]
