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
Django management command to lint every SKILL.md package in
agent/skills_pkg/.

⚠️ This command owns NO validation rules of its own. Every check lives in
``agent/skills/validation.py``.

It used to carry a FOURTH inline copy of the rules — its own "8 KiB" body cap
measured with ``len(str)``, i.e. CHARACTERS, while calling them bytes. That is
the same defect `_meta/lint.py` had, and it is exactly why one shared routine
exists: four copies of a rule is four chances to disagree. This command,
`_meta/lint.py`, `skill_creator/scripts/quick_validate.py` and the Skills
Diagnostics endpoint now give identical verdicts on the same package.

Exit code 0 when nothing would make the registry refuse a package; warnings are
reported and do NOT fail the command.

Usage:
    python manage.py acpx_lint
    python manage.py acpx_lint --json
    python manage.py acpx_lint --strict   # warnings also fail
"""
from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand

from agent.skills.frontmatter import find_skill_files
from agent.skills.registry import skill_registry
from agent.skills.validation import check_duplicate_names, validate_skill_file


class Command(BaseCommand):
    help = "Lint every Tlamatini SKILL.md package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true",
            help="Emit machine-readable JSON instead of human-readable lines.",
        )
        parser.add_argument(
            "--strict", action="store_true",
            help="Treat warnings as failures too.",
        )

    def handle(self, *args, **options):
        # ⚠️ Roots are de-duplicated and resolved FIRST-WINS by the registry,
        # so the same package is linted once even when an install copy shadows
        # a bundled one.
        roots = skill_registry._dedupe_roots(  # noqa: SLF001 — intentional read
            skill_registry._roots  # noqa: SLF001
        )
        strict = bool(options.get("strict"))
        results = []
        rows = []
        rc = 0

        seen_paths: set = set()
        for root in roots:
            for path in find_skill_files(root):
                key = str(path).lower()
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                v = validate_skill_file(path)
                results.append(v)
                ok = v.ok and (not v.warnings or not strict)
                if not ok:
                    rc = 1
                rows.append({
                    "path": str(path),
                    "ok": ok,
                    "name": v.name,
                    "runtime": v.runtime,
                    "body_size": v.body_bytes,
                    "body_chars": v.body_chars,
                    "errors": [f"{f.code}: {f.message}" for f in v.errors],
                    "warnings": [f"{f.code}: {f.message}" for f in v.warnings],
                })

        # A duplicate name WITHIN the linted set is a real collision.
        duplicate_findings = check_duplicate_names(results)
        for f in duplicate_findings:
            rc = 1

        if options["json"]:
            self.stdout.write(json.dumps({
                "ok": rc == 0,
                "rows": rows,
                "total": len(rows),
                "duplicates": [f.message for f in duplicate_findings],
            }))
        else:
            for r in rows:
                for w in r["warnings"]:
                    self.stdout.write(f"[WARN] {r['path']}: {w}")
                if r["ok"]:
                    self.stdout.write(
                        f"[OK] {r['path']}: name={r['name']!r} "
                        f"runtime={r['runtime']} body={r['body_size']}B "
                        f"({r['body_chars']} chars)"
                    )
                else:
                    self.stdout.write(
                        f"[FAIL] {r['path']}: " + "; ".join(
                            r["errors"] or r["warnings"])
                    )
            for f in duplicate_findings:
                self.stdout.write(f"[FAIL] {f.message}")
            ok_count = sum(1 for r in rows if r["ok"])
            self.stdout.write(f"acpx_lint: {ok_count}/{len(rows)} skills ok.")
        sys.exit(rc)
