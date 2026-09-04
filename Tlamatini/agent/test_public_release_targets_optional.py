# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""A PUBLIC release must build without ``.private_targets.json`` -- safely.

Angela, 2026-08-30. ``.private_targets.json`` is gitignored, so it exists ONLY on
a machine where somebody declared private data. Everyone else -- a fresh clone,
a public contributor, Tlamatini rebuilding herself from ``TlamatiniSourceCode/``
(which is FORBIDDEN to carry it) -- used to hit a hard ``REFUSING: no leak
targets`` with the schema documented nowhere but that error message.

The fix is deliberately TWO things, because neither alone covers the tree of
cases:

  * ``.private_targets.template.json`` -- TRACKED, always present, always EMPTY.
    It documents the schema and resolves to ZERO targets.
  * an evidence-based interlock. Zero targets is allowed only when the tree shows
    no private-data markers. With ``data.keys`` / a private contacts book present,
    "no targets" means the file went MISSING, every scrub would be a silent no-op,
    and the build would publish an unscrubbed release -- so it REFUSES instead.

And the runtime half of Angela's question: absence of the file can NEVER stop an
installed Tlamatini from starting, because nothing under ``Tlamatini/`` reads it.
``test_no_runtime_dependency_on_the_targets_file`` is what keeps that true.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / ".private_targets.template.json"
_PUBLIC = _REPO_ROOT / "build_complete_public_release.py"
_PRIVATE = _REPO_ROOT / "build_complete_private_release.py"
_BUILD = _REPO_ROOT / "build.py"
_REGEN = _REPO_ROOT / "regen_secrets.py"
_SNAPSHOT = _REPO_ROOT / "copy_source_assets.py"

_SCHEMA_KEYS = ("names", "phones", "handles", "emails")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _ensure_repo_on_path() -> None:
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))


def _lift(path: Path, names: set) -> types.SimpleNamespace:
    """Execute only the named module-level defs/assignments from a source file.

    build.py cannot be imported in a test process (it drives a real PyInstaller
    build and mutates the environment at import time), so its helpers are
    AST-lifted -- the same trick test_django_port_config.py uses for manage.py.
    """
    tree = ast.parse(_read(path))
    keep = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom) and (node.module or "") == "versioning":
                continue
            keep.append(node)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            targets = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if targets & names:
                keep.append(node)
    module = ast.Module(body=keep, type_ignores=[])
    namespace = {"__file__": str(path), "__name__": "_lifted_build"}
    exec(compile(ast.fix_missing_locations(module), str(path), "exec"), namespace)
    return types.SimpleNamespace(**namespace)


def _load_public():
    """Import the public release builder (safe: main() is under __main__)."""
    _ensure_repo_on_path()
    import importlib
    return importlib.import_module("build_complete_public_release")


class TemplateFileContractTests(unittest.TestCase):
    """The tracked template IS the schema, and it must stay EMPTY forever."""

    def test_template_exists_and_parses(self):
        self.assertTrue(_TEMPLATE.is_file(),
                        f"{_TEMPLATE.name} missing -> a fresh clone has no schema to copy.")
        json.loads(_read(_TEMPLATE))

    def test_template_is_tracked_by_git(self):
        res = subprocess.run(["git", "check-ignore", _TEMPLATE.name],
                             cwd=str(_REPO_ROOT), capture_output=True, text=True)
        self.assertNotEqual(
            res.returncode, 0,
            f"{_TEMPLATE.name} is gitignored -> it would reach neither a clone nor the "
            f"self-modify snapshot, which is the entire point of it existing.")

    def test_template_carries_the_full_schema_and_no_values(self):
        doc = json.loads(_read(_TEMPLATE))
        for key in _SCHEMA_KEYS:
            self.assertIn(key, doc, f"template lost the {key!r} category")
            self.assertEqual([], doc[key],
                             f"template category {key!r} is NOT empty -> this file is "
                             f"TRACKED, so a value here is published private data.")

    def test_template_yields_zero_targets(self):
        _ensure_repo_on_path()
        import check_private_data as cpd
        ns = types.SimpleNamespace(targets_file=str(_TEMPLATE), target=None)
        self.assertEqual([], cpd.load_targets(ns),
                         "the empty template must resolve to ZERO targets")

    def test_loader_ignores_underscore_comment_keys(self):
        """A ``_README`` line must never become a scrub target.

        Without this guard the tree-wide scrubber would replace that prose in
        every file, and the verifier would then "find" it in everything it had
        just rewritten.
        """
        _ensure_repo_on_path()
        import check_private_data as cpd
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps({
                "_README": ["this prose must never be scrubbed"],
                "_note": "nor this",
                "emails": ["someone@example.invalid"],
            }), encoding="utf-8")
            ns = types.SimpleNamespace(targets_file=str(path), target=None)
            values = [t["value"] for t in cpd.load_targets(ns)]
        self.assertEqual(["someone@example.invalid"], values)


class TargetsDiscoveryTests(unittest.TestCase):

    def test_default_targets_file_falls_back_to_the_template(self):
        pub = _load_public()
        self.assertTrue(hasattr(pub, "TEMPLATE_TARGETS_FILE"))
        self.assertEqual(_TEMPLATE.name, pub.TEMPLATE_TARGETS_FILE.name)
        self.assertIsNotNone(pub.default_targets_file(),
                             "discovery returned nothing even though the tracked "
                             "template is present")

    def test_template_is_never_scrubbed(self):
        pub = _load_public()
        self.assertIn(_TEMPLATE.name, pub.SCRUB_SKIP_FILES,
                      "scrubbing the targets template would rewrite the schema prose")


class RiskMarkerInterlockTests(unittest.TestCase):
    """"No targets" is safe on a clean tree and DANGEROUS on a keyed one."""

    def _markers_in(self, tmp: Path, files: dict) -> list:
        pub = _load_public()
        original = pub.REPO_ROOT
        try:
            pub.REPO_ROOT = tmp
            for rel, body in files.items():
                target = tmp / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            return pub.private_data_risk_markers()
        finally:
            pub.REPO_ROOT = original

    def test_clean_tree_reports_no_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual([], self._markers_in(Path(tmp), {}))

    def test_data_keys_is_a_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            markers = self._markers_in(Path(tmp), {"data.keys": "A=b\n"})
        self.assertTrue(any("data.keys" in m for m in markers), markers)

    def test_private_contacts_book_is_a_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            markers = self._markers_in(Path(tmp), {"contacts.private.json": "{}"})
        self.assertTrue(any("contacts.private" in m for m in markers), markers)

    def test_non_empty_contacts_json_is_a_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            markers = self._markers_in(Path(tmp), {
                "Tlamatini/agent/contacts.json":
                    json.dumps({"contacts": [{"name": "someone"}]}),
            })
        self.assertTrue(any("contacts.json" in m for m in markers), markers)

    def test_empty_contacts_json_is_not_a_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            markers = self._markers_in(Path(tmp), {
                "Tlamatini/agent/contacts.json": json.dumps({"contacts": []}),
            })
        self.assertEqual([], markers)

    def test_unreadable_contacts_json_fails_toward_safety(self):
        with tempfile.TemporaryDirectory() as tmp:
            markers = self._markers_in(Path(tmp), {
                "Tlamatini/agent/contacts.json": "{ not json at all",
            })
        self.assertTrue(markers, "an unparseable contacts book must be ASSUMED non-empty")


class DecideTargetsModeTests(unittest.TestCase):

    def _decide(self, values, markers, no_private_data=False):
        pub = _load_public()
        original = pub.private_data_risk_markers
        try:
            pub.private_data_risk_markers = lambda: list(markers)
            args = types.SimpleNamespace(no_private_data=no_private_data)
            return pub.decide_targets_mode(values, args)
        finally:
            pub.private_data_risk_markers = original

    def test_with_targets_runs_normal_mode(self):
        self.assertFalse(self._decide(["someone@example.invalid"], ["data.keys exists"]))

    def test_no_targets_clean_tree_enters_no_targets_mode(self):
        self.assertTrue(self._decide([], []))

    def test_no_targets_with_markers_REFUSES(self):
        with self.assertRaises(SystemExit) as ctx:
            self._decide([], ["data.keys exists (real secrets vault)"])
        message = str(ctx.exception)
        self.assertIn("REFUSING", message)
        self.assertIn("data.keys", message, "the refusal must name the evidence")
        self.assertIn(_TEMPLATE.name, message, "the refusal must name the template")
        self.assertIn("--no-private-data", message, "the refusal must name the override")

    def test_explicit_override_allows_no_targets_despite_markers(self):
        self.assertTrue(self._decide([], ["data.keys exists"], no_private_data=True))


class NoTargetsVerificationTests(unittest.TestCase):
    """NO-TARGETS MODE must be a NARROWER gate, never an ABSENT one."""

    def _audit(self, files: dict) -> int:
        pub = _load_public()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, body in files.items():
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(body, encoding="utf-8")
            return pub.verify_shipped_config_surface(root)

    def test_a_placeholder_config_is_clean(self):
        self.assertEqual(0, self._audit({
            "config.json": json.dumps({
                "ANTHROPIC_API_KEY": "<ANTHROPIC_API_KEY goes here>",
                "telegram_bot_token": "<telegram_bot_token goes here>",
                "ollama_base_url": "http://localhost:11434",
            }, indent=2),
            "contacts.json": json.dumps({"contacts": []}, indent=2),
        }))

    def test_a_live_looking_secret_blocks(self):
        self.assertGreater(self._audit({
            "config.json": json.dumps(
                {"ANTHROPIC_API_KEY": "sk-ant-api03-NOTREAL-0123456789abcdef"}, indent=2),
        }), 0)

    def test_an_email_address_blocks(self):
        self.assertGreater(self._audit({
            "agents/emailer/config.yaml": "smtp:\n  username: someone@somewhere.invalid\n",
        }), 0)

    def test_a_phone_number_in_contacts_blocks(self):
        self.assertGreater(self._audit({
            "contacts.json": json.dumps(
                {"contacts": [{"name": "x", "phone": "+52 55 1234 5678"}]}, indent=2),
        }), 0)

    def test_the_secrets_vault_inside_a_package_blocks(self):
        self.assertGreater(self._audit({"data.keys": "ANTHROPIC_API_KEY=whatever\n"}), 0)

    def test_a_yaml_comment_is_not_a_value(self):
        self.assertEqual(0, self._audit({
            "agents/telegrammer/config.yaml":
                "# bot_token: paste your real 0123456789:AAAAAAAAAAAA token here\n"
                "telegram:\n"
                "  bot_token: \"<TELEGRAM_BOT_TOKEN goes here>\"\n",
        }))


class RuntimeIndependenceTests(unittest.TestCase):
    """Angela's runtime question: a missing targets file can never break startup."""

    def test_no_runtime_dependency_on_the_targets_file(self):
        offenders = []
        app_root = _REPO_ROOT / "Tlamatini"
        skip_dirs = {"TlamatiniSourceCode", "__pycache__", "pools", "Temp",
                     "staticfiles", "node_modules", ".git", "Templates"}
        wanted = {".py", ".js", ".json", ".yaml", ".yml", ".pmt", ".html"}
        # Only THIS guard is exempt (it names the file in order to forbid it).
        # Every other file under Tlamatini/ -- including any other test -- still
        # trips the check, so the exemption cannot be widened by accident.
        self_path = Path(__file__).resolve()
        for dirpath, dirnames, filenames in os.walk(app_root):
            dirnames[:] = [d for d in dirnames if d not in skip_dirs]
            for name in filenames:
                if Path(name).suffix.lower() not in wanted:
                    continue
                path = Path(dirpath) / name
                if path.resolve() == self_path:
                    continue
                try:
                    if path.stat().st_size > 5_000_000:
                        continue
                    body = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                if "private_targets" in body:
                    offenders.append(str(path.relative_to(_REPO_ROOT)))
        self.assertEqual(
            [], offenders,
            "a RUNTIME file references the leak-target list. That file is gitignored "
            "and build-time only, so a runtime read would make an installed Tlamatini "
            "fail to start on every machine that never had it: " + ", ".join(offenders))


class PushableSecretsAreEnforcedByTheBuildTests(unittest.TestCase):
    """A bare ``python build.py`` must never freeze live keys."""

    def setUp(self):
        self.lifted = _lift(_BUILD, {"ensure_pushable_secrets",
                                     "_config_secret_offenders",
                                     "_is_placeholder_secret",
                                     "_SECRET_KEY_NAME_RE",
                                     "_KEYED_BUILD_ENV"})

    def test_main_calls_ensure_pushable_secrets_before_packaging(self):
        source = _read(_BUILD)
        self.assertIn("    ensure_pushable_secrets()", source)
        call = source.index("    ensure_pushable_secrets()")
        dist = source.index('dist_manage = Path("dist") / "manage"')
        self.assertLess(call, dist,
                        "the push-able pass must run BEFORE dist/ is populated, or the "
                        "artifact can contain what was never verified")

    def test_keyed_env_opt_out_exists(self):
        self.assertEqual("TLAMATINI_KEYED_BUILD", self.lifted._KEYED_BUILD_ENV)

    def test_placeholder_values_are_recognised(self):
        for value in ("<ANTHROPIC_API_KEY goes here>", "", None, "changeme", "{{token}}"):
            self.assertTrue(self.lifted._is_placeholder_secret(value), repr(value))

    def test_a_live_key_is_an_offender(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "ANTHROPIC_API_KEY": "sk-ant-api03-NOTREAL-abcdef0123456789",
                "ollama_base_url": "http://localhost:11434",
            }), encoding="utf-8")
            offenders = self.lifted._config_secret_offenders(path)
        self.assertEqual(["ANTHROPIC_API_KEY"], offenders)

    def test_acpx_env_secrets_are_covered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "acpx": {"agents": {"claude": {"env": {
                    "ANTHROPIC_API_KEY": "sk-ant-api03-NOTREAL-abcdef0123456789"}}}},
            }), encoding="utf-8")
            offenders = self.lifted._config_secret_offenders(path)
        self.assertEqual(["acpx.agents.claude.env.ANTHROPIC_API_KEY"], offenders)

    def test_a_fully_placeholder_config_has_no_offenders(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({
                "ANTHROPIC_API_KEY": "<ANTHROPIC_API_KEY goes here>",
                "zavu_api_key": "<zavu_api_key goes here>",
                "acpx": {"agents": {"codex": {"env": {
                    "OPENAI_API_KEY": "<OPENAI_API_KEY goes here>"}}}},
            }), encoding="utf-8")
            self.assertEqual([], self.lifted._config_secret_offenders(path))


class BuilderWiringTests(unittest.TestCase):

    def test_private_builder_sets_the_keyed_opt_out(self):
        self.assertIn('env["TLAMATINI_KEYED_BUILD"] = "1"', _read(_PRIVATE),
                      "the KEYED build must opt out of the forced push-able pass, or it "
                      "would ship placeholders where real values are the whole point")

    def test_public_builder_clears_the_keyed_opt_out(self):
        self.assertIn('env.pop("TLAMATINI_KEYED_BUILD", None)', _read(_PUBLIC),
                      "an ambient TLAMATINI_KEYED_BUILD left over from a private build "
                      "in the same shell must not disable the public guarantee")

    def test_regen_touched_covers_every_file_regen_secrets_patches(self):
        pub = _load_public()
        backed_up = {p.parent.name + "/" + p.name for p in pub.REGEN_TOUCHED}
        source = _read(_REGEN)
        missing = []
        for agent in ("telegrammer", "whatsapper", "teletlamatini", "emailer",
                      "recmailer", "zavuerer", "discoverer"):
            if '"' + agent + '" / "config.yaml"' not in source:
                continue
            if agent + "/config.yaml" not in backed_up:
                missing.append(agent)
        self.assertEqual(
            [], missing,
            "regen_secrets.py rewrites these agent config.yaml files, but the public "
            "builder never backs them up, so they are not restored byte-for-byte: "
            + ", ".join(missing))


class SelfModifySnapshotTests(unittest.TestCase):
    """Tlamatini rebuilding herself must find the schema, never the real list."""

    def test_real_targets_file_is_never_snapshotted(self):
        self.assertIn('".private_targets.json"', _read(_SNAPSHOT))

    def test_template_is_required_in_every_snapshot(self):
        source = _read(_SNAPSHOT)
        start = source.index("REQUIRED_SNAPSHOT_FILES")
        end = source.index("\n)", start)
        self.assertIn(".private_targets.template.json", source[start:end],
                      "without the template in the snapshot, a self-rebuild has no "
                      "schema and the public builder has nothing to fall back to")

    def test_template_is_not_excluded_by_name(self):
        _ensure_repo_on_path()
        import importlib
        snap = importlib.import_module("copy_source_assets")
        self.assertNotIn(".private_targets.template.json", snap.EXCLUDED_FILE_NAMES)
        self.assertFalse(snap._skip_file(".private_targets.template.json",
                                         ".private_targets.template.json"))


class DocumentationTests(unittest.TestCase):

    def test_public_builder_documents_the_optional_targets_file(self):
        doc = _read(_PUBLIC)
        for phrase in ("NO-TARGETS MODE", ".private_targets.template.json",
                       "--no-private-data"):
            self.assertIn(phrase, doc, f"{phrase!r} is undocumented in {_PUBLIC.name}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
