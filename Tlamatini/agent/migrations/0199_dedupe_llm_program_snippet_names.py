"""Repair the duplicate LLMProgram / LLMSnippet names an older build created.

Angela, 2026-09-06. Program and snippet names are built as
``<UTC timestamp to the SECOND>_<name>`` (services/filesystem.get_time_stamp),
so two code blocks emitted in the SAME answer received the SAME name — while
every reader looked the file up by NAME with ``.get()``. That pair of rows was
then permanently unreachable:

* ``load_canvas_view`` raised ``MultipleObjectsReturned`` — an UNHANDLED 500,
  because ``except LLMProgram.DoesNotExist`` does not catch it — so "Load in
  canvas" simply failed.
* ``save_files_from_db`` hit the same exception and logged
  ``!!! ERROR while saving file: get() returned more than one LLMProgram``,
  for BOTH twins, so neither file could ever be written to disk.

The content was never lost, only unreachable. Newly saved rows are uniquified
at save time now (``services/response_parser._uniquify_name``) and every reader
was made collision-proof, but a database written by an OLDER build still
carries the duplicates — this migration repairs those.

NON-DESTRUCTIVE BY DESIGN: nothing is ever deleted. The lowest-id row keeps the
original name and each later twin is RENAMED to ``<name>_2`` / ``<name>_3`` …
(skipping any suffix already taken), so BOTH files become loadable and savable
again under distinct names. It is also idempotent and FAIL-OPEN: a database
that has no duplicates is untouched, and any unexpected error is swallowed
rather than blocking the whole migrate (a post-update migrate that aborts would
leave the user without her new agents/tools/prompts, which is far worse than an
unrepaired duplicate).
"""
from django.db import migrations
from django.db.models import Count

_SUFFIX_LIMIT = 999


def _dedupe(model, field):
    """Rename every duplicate of `field` except the lowest-id row. Returns count."""
    renamed = 0
    dupes = (
        model.objects.values(field)
        .annotate(n=Count(field))
        .filter(n__gt=1)
        .values_list(field, flat=True)
    )
    for name in list(dupes):
        rows = list(model.objects.filter(**{field: name}).order_by('pk'))
        for row in rows[1:]:  # the FIRST row keeps the original name
            for n in range(2, _SUFFIX_LIMIT + 1):
                candidate = f"{name}_{n}"
                if not model.objects.filter(**{field: candidate}).exists():
                    setattr(row, field, candidate)
                    row.save(update_fields=[field])
                    renamed += 1
                    print(f"--- [NAME-GUARD] repaired duplicate '{name}' -> '{candidate}'")
                    break
    return renamed


def dedupe_names(apps, schema_editor):
    try:
        total = 0
        total += _dedupe(apps.get_model('agent', 'LLMProgram'), 'programName')
        total += _dedupe(apps.get_model('agent', 'LLMSnippet'), 'snippetName')
        if total:
            print(f"--- [NAME-GUARD] {total} duplicate name(s) repaired - files are loadable again")
    except Exception as exc:  # FAIL-OPEN: never block a post-update migrate
        print(f"--- [NAME-GUARD] duplicate-name repair skipped: {exc}")


def noop_reverse(apps, schema_editor):
    """Irreversible on purpose — renaming back would recreate the broken state."""
    pass


class Migration(migrations.Migration):
    dependencies = [('agent', '0198_add_pdfer_nuance_demo_prompt')]
    operations = [migrations.RunPython(dedupe_names, noop_reverse)]
