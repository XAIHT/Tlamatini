# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""The two public-build guarantees that do NOT depend on a leak-target list.

Angela, 2026-08-30 / ported 2026-09-05. ``test_public_release_targets.py`` owns
the targets story: the privacy pre-flight, the inert tracked template, the
fail-toward-refusal interlock, and the derived regen backup list. This file owns
the two guarantees that hold *whether or not* a target list exists:

  1. **A bare ``python build.py`` can never freeze live keys.**
     ``build.py::ensure_pushable_secrets`` runs ``regen_secrets.py --mode
     push-able`` itself and then RE-READS ``config.json`` to PROVE no live-looking
     secret survived -- which also covers a stripped tree where the regen script is
     missing entirely and the pass silently did nothing. ``TLAMATINI_KEYED_BUILD=1``
     is the opt-out, set on purpose by the PRIVATE builder and cleared on purpose
     by the PUBLIC one.

  2. **A CLEAN-TREE build verifies something.**
     With no targets, ``check_private_data.py`` matches nothing BY CONSTRUCTION,
     so ``0 findings`` is true without inspecting anything. That was a real hole:
     the build printed "VERIFIED CLEAN" having looked at nothing.
     ``verify_shipped_config_surface()`` closes it from the other side -- it
     asserts the invariant a public package satisfies either way: the
     CONFIGURATION Tlamatini ships carries no live secret, no real e-mail address
     and no phone number, and ``data.keys`` is not inside the package at all.
"""

from __future__ import annotations

import ast
import json
import tempfile
import types
import sys
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "private_targets.example.json"
_PUBLIC = _REPO_ROOT / "build_complete_public_release.py"
_PRIVATE = _REPO_ROOT / "build_complete_private_release.py"
_BUILD = _REPO_ROOT / "build.py"
_REGEN = _REPO_ROOT / "regen_secrets.py"
_SNAPSHOT = _REPO_ROOT / "copy_source_assets.py"


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


# ---------------------------------------------------------------------------
# 1. A bare `python build.py` must never freeze live keys.
# ---------------------------------------------------------------------------

class PushableSecretsAreEnforcedByTheBuildTests(unittest.TestCase):

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
        """Every managed file must be backed up BEFORE regen rewrites it.

        The failure this pins is silent: on a machine with no ``data.keys`` the
        ``finally`` re-key is skipped, so a file regen scrubbed but nobody backed
        up stays redacted -- the operator loses their own credentials with no
        error anywhere.
        """
        pub = _load_public()
        backed_up = {p.name if p.parent.name == "agent" else p.parent.name + "/" + p.name
                     for p in pub.REGEN_TOUCHED}
        source = _read(_REGEN)
        missing = []
        for agent in ("telegrammer", "whatsapper", "teletlamatini", "emailer",
                      "recmailer", "zavuerer", "discoverer"):
            if '"' + agent + '" / "config.yaml"' not in source:
                continue
            if agent + "/config.yaml" not in backed_up:
                missing.append(agent + "/config.yaml")
        # external_mcps.json is managed too (patch_external_mcps_json can even
        # auto-vault its env secrets into data.keys), and it is the one the
        # hand-typed list historically forgot.
        if "external_mcps.json" in source and "external_mcps.json" not in backed_up:
            missing.append("external_mcps.json")
        self.assertEqual(
            [], missing,
            "regen_secrets.py rewrites these files, but the public builder never backs "
            "them up first, so they are not restored byte-for-byte: " + ", ".join(missing))


# ---------------------------------------------------------------------------
# 2. A CLEAN-TREE build must verify something.
# ---------------------------------------------------------------------------

class CleanTreePackageAuditTests(unittest.TestCase):
    """`verify_shipped_config_surface` is what makes CLEAN-TREE mode honest."""

    def setUp(self):
        self.pub = _load_public()

    def _audit(self, files: dict) -> int:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pkg"
            for rel, body in files.items():
                path = root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(body, encoding="utf-8")
            root.mkdir(parents=True, exist_ok=True)
            return self.pub.verify_shipped_config_surface(root)

    def test_a_placeholder_config_is_clean(self):
        self.assertEqual(0, self._audit({
            "Tlamatini/agent/config.json": json.dumps({
                "ANTHROPIC_API_KEY": "<ANTHROPIC_API_KEY goes here>",
                "ollama_base_url": "http://localhost:11434",
            }),
            "Tlamatini/agent/contacts.json": "[]",
            "Tlamatini/agent/external_mcps.json": '{"mcpServers": {}, "active": []}',
        }))

    def test_a_live_looking_secret_blocks(self):
        self.assertEqual(1, self._audit({
            "config.json": json.dumps(
                {"zavu_api_key": "zv_live_NOTREAL_abcdefghijklmnop"}),
        }))

    def test_a_real_email_blocks_but_an_example_domain_does_not(self):
        self.assertEqual(0, self._audit({
            "config.yaml": "smtp_user: someone@example.com\n"}))
        self.assertEqual(1, self._audit({
            "config.yaml": "smtp_user: a.real.person@realmail.net\n"}))

    def test_a_phone_number_in_the_contacts_book_blocks(self):
        self.assertEqual(1, self._audit({
            "contacts.json": '[{"name": "X", "whatsapp": "+52 55 1234 5678"}]'}))

    def test_the_secrets_vault_inside_a_package_always_blocks(self):
        self.assertEqual(1, self._audit({"data.keys": "ANTHROPIC_API_KEY=whatever\n"}))

    def test_a_yaml_comment_is_documentation_not_a_value(self):
        self.assertEqual(0, self._audit({
            "config.yaml": "# api_key: put your real key here\napi_key: ''\n"}))

    # -- ROW 9: private material, by NAME and by CONTENT ---------------------

    def test_forbidden_files_block_on_presence_alone(self):
        for name in ("data.keys", ".private_targets.json", "private_targets.json",
                     "contacts.private.json", ".env"):
            with self.subTest(name=name):
                self.assertEqual(1, self._audit({name: "anything at all\n"}),
                                 f"{name} must never be inside a public package")

    def test_a_pem_private_key_blocks_anywhere(self):
        key = ("-----BEGIN RSA PRIVATE KEY-----\n"
               "MIIEowIBAAKCAQEAxNOTREAL\n"
               "-----END RSA PRIVATE KEY-----\n")
        self.assertEqual(1, self._audit({"deploy.key": key}))
        self.assertEqual(1, self._audit({"python/Lib/site-packages/x/id.pem": key}),
                         "a private key is a defect even inside a vendored tree")

    def test_a_ca_bundle_is_not_a_private_key(self):
        """certifi's cacert.pem ships in every Python app. Blocking it would abort
        every release, which is how a guard gets deleted."""
        bundle = ("-----BEGIN CERTIFICATE-----\nMIIDdzCCAl+gAwIBAgIE\n"
                  "-----END CERTIFICATE-----\n")
        self.assertEqual(
            0, self._audit({"python/Lib/site-packages/certifi/cacert.pem": bundle}))

    # -- ROW 10: beyond the five known basenames -----------------------------

    def test_a_secret_in_an_unnamed_config_still_blocks(self):
        self.assertEqual(1, self._audit({
            "Tlamatini/agent/settings.local.json": json.dumps(
                {"api_key": "sk-NOTREAL-abcdefghijklmnop"})}),
            "a secret does not care what the file is called")

    def test_the_widened_scan_stops_at_vendored_runtimes(self):
        """Third-party fixtures are not Tlamatini's configuration."""
        fixture = json.dumps({"auth_token": "sample-token-abcdefghij"})
        for vendored in ("python/Lib/site-packages/pkg/fixture.json",
                         "_internal/pkg/meta.json",
                         "jre/conf/thing.json",
                         "node_modules/x/config.json"):
            with self.subTest(path=vendored):
                self.assertEqual(0, self._audit({vendored: fixture}))

    def test_a_NAMED_config_is_still_scanned_inside_a_vendored_tree(self):
        """Tlamatini's own frozen config.json lives under _internal."""
        self.assertEqual(1, self._audit({
            "_internal/Tlamatini/agent/config.json": json.dumps(
                {"zavu_api_key": "zv_live_NOTREAL_abcdefghij"})}),
            "the five NAMED configs must be scanned everywhere, vendored or not")

    # -- ROW 11: unreadable is a FINDING, never a silent skip ----------------

    def test_an_undecodable_config_is_a_finding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "pkg"
            root.mkdir(parents=True)
            (root / "config.yaml").write_bytes(b"\x80\x81\x82 not utf-8\n")
            self.assertEqual(1, self.pub.verify_shipped_config_surface(root),
                             "a file that could not be read must never be "
                             "reported as clean")

    def test_the_unreadable_path_fails_toward_refusal_like_layer_one(self):
        source = _read(_PUBLIC)
        block = source[source.index("def verify_shipped_config_surface"):]
        block = block[:block.index("    return len(findings)")]
        self.assertNotIn("            except (UnicodeDecodeError, OSError):\n"
                         "                continue", block,
                         "silently skipping an unreadable file is the exact "
                         "fail-OPEN this row fixed")
        # NB: the phrase is split across concatenated f-string literals in the
        # source, so only the tail is contiguous. Asserting the whole sentence
        # fails on a perfectly correct file.
        self.assertIn("never be called clean", block)

    def test_it_never_rebinds_the_preflights_own_secret_pattern(self):
        """Two audits, two patterns, two names -- the collision that would widen
        the pre-flight's idea of a credential and start refusing clean clones."""
        source = _read(_PUBLIC)
        self.assertIn("_SHIPPED_SECRET_NAME_RE = re.compile(", source)
        # ANCHOR at line start: "_SHIPPED_SECRET_NAME_RE = re.compile(" CONTAINS
        # "_SECRET_NAME_RE = re.compile(" as a substring, so an unanchored count
        # reports 2 for a perfectly correct file.
        defs = [ln for ln in source.splitlines()
                if ln.startswith("_SECRET_NAME_RE = re.compile(")]
        self.assertEqual(1, len(defs),
                         "the privacy pre-flight's _SECRET_NAME_RE must be defined "
                         "exactly once and never rebound by the package audit")


class CleanTreeAuditIsWiredIntoStepFourTests(unittest.TestCase):
    """A function nobody calls verifies nothing."""

    def setUp(self):
        self.source = _read(_PUBLIC)

    def test_the_audit_runs_in_clean_tree_mode(self):
        self.assertIn("config_findings = verify_shipped_config_surface(verify_root)",
                      self.source)

    def test_it_runs_before_the_extract_is_deleted(self):
        # `shutil.rmtree(VERIFY_EXTRACT, ...)` also appears in resolve_verify_root,
        # far earlier in the file, so scope the comparison to the STEP 4 block --
        # a bare .index() silently compares against the wrong occurrence.
        step4 = self.source.index("STEP 4/6")
        step5 = self.source.index("STEP 5/6")
        block = self.source[step4:step5]
        call = block.index("config_findings = verify_shipped_config_surface")
        rmtree = block.index("shutil.rmtree(VERIFY_EXTRACT, ignore_errors=True)")
        self.assertLess(call, rmtree,
                        "the audit reads the extracted package; deleting it first would "
                        "make the audit silently scan nothing")

    def test_a_finding_aborts_the_build(self):
        self.assertIn("if config_findings:", self.source)
        abort = self.source.index("if config_findings:")
        zip_step = self.source.index("STEP 6/6")
        self.assertLess(abort, zip_step,
                        "a configuration finding must abort BEFORE the public zip exists")

    def test_the_clean_tree_pass_message_does_not_overclaim(self):
        self.assertIn("Personal-VALUE matching was NOT performed", self.source,
                      "CLEAN-TREE mode must keep saying out loud that no personal-value "
                      "matching happened; the config audit does not replace it")


# ---------------------------------------------------------------------------
# 3. Tlamatini rebuilding herself must find the schema, never the real list.
# ---------------------------------------------------------------------------

class SelfModifySnapshotTests(unittest.TestCase):

    def test_real_targets_file_is_never_snapshotted(self):
        self.assertIn('".private_targets.json"', _read(_SNAPSHOT))

    def test_template_is_required_in_every_snapshot(self):
        source = _read(_SNAPSHOT)
        start = source.index("REQUIRED_SNAPSHOT_FILES")
        end = source.index("\n)", start)
        self.assertIn("private_targets.example.json", source[start:end],
                      "without the template in the snapshot, a self-rebuild has no "
                      "schema for the real list it is forbidden to carry")

    def test_template_is_not_excluded_by_name(self):
        _ensure_repo_on_path()
        import importlib
        snap = importlib.import_module("copy_source_assets")
        self.assertNotIn("private_targets.example.json", snap.EXCLUDED_FILE_NAMES)
        self.assertFalse(snap._skip_file("private_targets.example.json",
                                         "private_targets.example.json"))

    def test_the_tracked_template_exists_and_is_placeholder_only(self):
        self.assertTrue(_TEMPLATE.is_file(), f"{_TEMPLATE.name} must stay tracked")
        doc = json.loads(_TEMPLATE.read_text(encoding="utf-8-sig"))
        for key, values in doc.items():
            if key.startswith("_"):
                continue  # documentation key, never a target
            for value in values:
                self.assertTrue(
                    value.startswith("<") and value.endswith(">"),
                    f"{key} carries a non-placeholder value {value!r}; the template must "
                    f"never hold anything real")


if __name__ == "__main__":
    unittest.main(verbosity=2)
