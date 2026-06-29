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
agent/skills_pkg/. Calls the same logic as agent/skills_pkg/_meta/lint.py
but without the standalone sys.path bootstrap.

Usage:
    python manage.py acpx_lint
    python manage.py acpx_lint --json
"""
from __future__ import annotations

import json
import sys

from django.core.management.base import BaseCommand

from agent.skills.frontmatter import (
    SkillParseError,
    find_skill_files,
    parse_skill_md,
)
from agent.skills.registry import skill_registry


class Command(BaseCommand):
    help = "Lint every Tlamatini SKILL.md package."

    def add_arguments(self, parser):
        parser.add_argument(
            "--json", action="store_true",
            help="Emit machine-readable JSON instead of human-readable lines.",
        )

    def handle(self, *args, **options):
        roots = skill_registry._roots  # noqa: SLF001 — intentional read
        results = []
        rc = 0
        seen: dict = {}
        for root in roots:
            for path in find_skill_files(root):
                row = {"path": str(path), "ok": True, "errors": []}
                try:
                    text = path.read_text(encoding="utf-8")
                    fm, body = parse_skill_md(text, source_label=str(path))
                    row["name"] = fm.name
                    row["runtime"] = fm.runtime
                    row["body_size"] = len(body)
                    if not body:
                        row["ok"] = False
                        row["errors"].append("empty body")
                    if len(body) > 8 * 1024:
                        row["ok"] = False
                        row["errors"].append(
                            f"body too large ({len(body)} bytes > 8 KiB)"
                        )
                    if fm.name in seen:
                        row["ok"] = False
                        row["errors"].append(
                            f"duplicate name '{fm.name}' (also {seen[fm.name]})"
                        )
                    else:
                        seen[fm.name] = path
                except SkillParseError as e:
                    row["ok"] = False
                    row["errors"].append(str(e))
                except Exception as e:
                    row["ok"] = False
                    row["errors"].append(f"unexpected error: {e}")
                if not row["ok"]:
                    rc = 1
                results.append(row)

        if options["json"]:
            self.stdout.write(json.dumps({"ok": rc == 0, "rows": results,
                                          "total": len(results)}))
        else:
            for r in results:
                marker = "[OK]" if r["ok"] else "[FAIL]"
                self.stdout.write(
                    f"{marker} {r['path']}: "
                    + (f"name={r.get('name')!r} runtime={r.get('runtime')} body={r.get('body_size')}B"
                       if r["ok"] else "; ".join(r["errors"]))
                )
            ok_count = sum(1 for r in results if r["ok"])
            self.stdout.write(
                f"acpx_lint: {ok_count}/{len(results)} skills ok."
            )
        sys.exit(rc)
