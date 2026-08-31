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
test_public_release_targets.py -- `.private_targets.json` is OPTIONAL and is NEVER
a runtime dependency.

Angela, 2026-08-30: "improve the build of the public release to not be necessary
the file .private_targets.json ... and analyze that it should be no runtime
problem if in the first run Tlamatini can't run because the file may be missing."

WHAT THIS PINS, and why each one is load-bearing
------------------------------------------------
1. RUNTIME INDEPENDENCE. The file is BUILD-TIME ONLY. No module the running app
   loads may ever open it, and no build carrier may ship it. If a future change
   wires it into runtime, a MISSING file (its normal state -- it is gitignored)
   becomes a first-run crash on every user's machine. That is the exact failure
   Angela asked to be made impossible, so it is asserted rather than assumed.

2. THE FRESH-CLONE CONTRACT. A clone with no targets file must BUILD. This is
   verified the only honest way: by reconstructing what a fresh clone actually
   has -- the COMMITTED blobs of every tracked config -- and running the real
   pre-flight over them. Testing the maintainer's own keyed tree proves nothing
   about anybody else's clone. The first version of this feature passed every
   hand-written case and still refused a fresh clone on SEVEN committed
   defaults (`host: 127.0.0.1`, `max_body_bytes: 1048576`,
   `verify_token: "tlamatini"`, `password: "YourStrongPassword"`); each is
   pinned below by value.

3. THE TEMPLATE MUST STAY INERT. `private_targets.example.json` is tracked
   documentation. If it were auto-loaded, or if its placeholder values counted
   as targets, an unfilled copy would make the target list non-empty and so
   SILENCE the refusal -- producing a build that prints VERIFIED CLEAN having
   scrubbed nothing real. That is strictly worse than the refusal it replaced.

4. THE REFUSAL MUST SURVIVE. A tree that really holds private material and has
   no targets list must still be refused. Deleting the refusal outright was the
   obvious, wrong fix.

5. FAIL TOWARD REFUSAL. Every probe treats an unreadable file as evidence. This
   is the deliberate inverse of Tlamatini's usual fail-open rule.

6. REGEN IS AUTOMATIC AND FULLY BACKED UP. `regen_secrets.py --mode push-able`
   runs inside the builder (nobody has to call it first), and every file it
   rewrites is backed up BEFORE it runs. The hand-typed list carried 5 of the 7
   agent config.yaml files; `zavuerer` and `discoverer` were scrubbed with no
   backup, which loses the operator's keys on a machine without `data.keys`.

Run:  python Tlamatini/manage.py test agent.test_public_release_targets
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from django.test import SimpleTestCase

# Tlamatini/agent/ -> Tlamatini/ -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_BUILDER_PATH = _REPO_ROOT / "build_complete_public_release.py"
_TEMPLATE = _REPO_ROOT / "private_targets.example.json"
_TARGETS_BASENAMES = (".private_targets.json", "private_targets.json")

#: Every agent config.yaml that regen_secrets.py rewrites.
_REGEN_AGENTS = ("telegrammer", "whatsapper", "teletlamatini", "emailer",
                 "recmailer", "zavuerer", "discoverer")


def _load_builder():
    """Import the repo-root builder by path (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location(
        "_tlm_public_release_builder", _BUILDER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(_REPO_ROOT), *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


# =============================================================================
# 1. RUNTIME INDEPENDENCE -- the whole point of Angela's "no runtime problem"
# =============================================================================
class TargetsFileIsBuildTimeOnlyTests(SimpleTestCase):
    """A missing targets file can NEVER affect a running Tlamatini."""

    def test_no_runtime_module_reads_the_targets_file(self):
        """Not one module the app loads may open it.

        It is gitignored, so ABSENT is its normal state on every machine but the
        maintainer's. A runtime read would therefore fail for literally every
        user on first run -- the failure mode this whole change exists to rule
        out. Tests and the build scripts are exempt: they are not the app.
        """
        agent_root = _REPO_ROOT / "Tlamatini" / "agent"
        offenders = []
        for path in agent_root.rglob("*.py"):
            parts = set(path.parts)
            if parts & {"pools", "__pycache__", "TlamatiniSourceCode"}:
                continue
            if path.name.startswith("test_") or path.name == "tests.py":
                continue
            if "private_targets" in _read(path):
                offenders.append(str(path.relative_to(_REPO_ROOT)))
        self.assertEqual(
            offenders, [],
            "these RUNTIME modules reference the targets file: %s. It is "
            "gitignored and normally absent, so reading it at runtime breaks "
            "first launch for every user." % offenders)

    def test_the_build_never_ships_the_targets_file(self):
        """Shipping it would put the maintainer's PII list inside the release."""
        for script in ("build.py", "install.py"):
            src = _read(_REPO_ROOT / script)
            self.assertNotIn(
                "private_targets", src,
                f"{script} references the targets file. It must never be a build "
                f"input NOR a shipped artifact -- it is a list of Angela's "
                f"private data.")

    def test_the_snapshot_excludes_the_real_targets_file(self):
        """The self-modify source snapshot must not carry her PII list."""
        src = _read(_REPO_ROOT / "copy_source_assets.py")
        for name in _TARGETS_BASENAMES:
            self.assertIn(name, src,
                          f"copy_source_assets.py must exclude {name} from the "
                          f"TlamatiniSourceCode snapshot.")

    def test_both_spellings_are_gitignored_and_the_template_is_not(self):
        """DEFAULT_TARGETS_FILES auto-discovers BOTH spellings, so a
        leading-dot typo must not make a file full of real PII committable."""
        ignored = _read(_REPO_ROOT / ".gitignore")
        for name in _TARGETS_BASENAMES:
            self.assertRegex(
                ignored, rf"(?m)^{re.escape(name)}\s*$",
                f"{name} is auto-loaded by the public builder and holds real "
                f"private data -- it must be gitignored.")
        self.assertNotRegex(
            ignored, r"(?m)^private_targets\.example\.json\s*$",
            "the TEMPLATE is documentation and must stay TRACKED.")


# =============================================================================
# 2. THE FRESH-CLONE CONTRACT -- test the machine you do not have
# =============================================================================
class FreshCloneCanBuildTests(SimpleTestCase):
    """A clone with no targets file must build, or the change did nothing."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_builder()

    def _materialize_committed_configs(self, dest: Path) -> int:
        """Recreate what a FRESH CLONE has: the COMMITTED content of every
        tracked config. Unmodified files are copied from disk (fast); modified
        ones are pulled from HEAD, so the maintainer's local keys never leak
        into the fixture and skew the result."""
        listed = _git("ls-files", "Tlamatini/agent/agents/*/config.yaml",
                      "Tlamatini/agent/config.json")
        if listed.returncode != 0:
            self.skipTest("git unavailable; cannot reconstruct a fresh clone")
        tracked = [p for p in listed.stdout.splitlines() if p.strip()]
        modified = set(
            p for p in _git("ls-files", "-m").stdout.splitlines() if p.strip())
        count = 0
        for rel in tracked:
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            if rel in modified:
                blob = _git("show", f"HEAD:{rel}")
                if blob.returncode != 0:
                    continue
                dst.write_text(blob.stdout, encoding="utf-8")
            else:
                src = _REPO_ROOT / rel
                if not src.is_file():
                    continue
                shutil.copy2(src, dst)
            count += 1
        return count

    def test_a_fresh_clone_produces_no_evidence_and_therefore_builds(self):
        """THE decisive test.

        A fresh clone has no data.keys, no contacts book, no *.key files and
        only COMMITTED configs. The pre-flight must find nothing, so the builder
        proceeds in CLEAN-TREE mode instead of refusing.
        """
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td)
            n = self._materialize_committed_configs(clone)
            self.assertGreater(n, 50, "expected the full committed config set")
            saved = self.mod.REPO_ROOT
            try:
                self.mod.REPO_ROOT = clone
                evidence = self.mod.privacy_preflight()
            finally:
                self.mod.REPO_ROOT = saved
        self.assertEqual(
            evidence, [],
            "a FRESH CLONE would be REFUSED, which defeats the whole change. "
            "Every item here is a committed default being misread as private "
            "data:\n  " + "\n  ".join(evidence))

    def test_committed_defaults_that_once_broke_this_stay_fixed(self):
        """The seven real false positives, pinned by value.

        Each is a committed default. Any regression in the shape rules brings
        the fresh-clone refusal straight back.
        """
        for value in ("127.0.0.1", "0.0.0.0", "1048576", "5242880", "100000000"):
            self.assertFalse(
                self.mod._looks_like_pii(value),
                f"{value!r} is a bind address / byte count, not a person. A "
                f"phone-shape test that accepts it blocks every fresh clone.")
        self.assertFalse(self.mod._is_live_secret("verify_token", "tlamatini"),
                         "the product's own name is the shipped default "
                         "verify_token, not a credential.")
        self.assertFalse(self.mod._is_live_secret("password", "YourStrongPassword"),
                         "sqler's committed placeholder password.")

    def test_settings_that_merely_look_credential_shaped_are_ignored(self):
        for key, value in (("max_tokens", "4096"), ("sort_key", "mtime"),
                           ("key", "id"), ("pdcp_api_key", ""),
                           ("ANTHROPIC_API_KEY", "<KEY goes here>")):
            self.assertFalse(
                self.mod._is_live_secret(key, value),
                f"{key}: {value!r} is a setting or a placeholder, not a secret.")

    def test_real_credentials_and_real_pii_are_still_caught(self):
        self.assertTrue(self.mod._is_live_secret(
            "bot_token", "8123456789:AAH7xQvZk3mNpQrStUvWxYz012345678abc"))
        self.assertTrue(self.mod._is_live_secret("smtp_password", "hunter2hunter2"))
        self.assertTrue(self.mod._looks_like_pii("real.person@gmail.com"))
        self.assertTrue(self.mod._looks_like_pii("+52 55 1234 5678"))


# =============================================================================
# 3. THE TEMPLATE MUST STAY INERT
# =============================================================================
class TemplateIsInertTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_builder()

    def test_the_template_exists_and_is_valid_json(self):
        self.assertTrue(_TEMPLATE.is_file(),
                        "the tracked shape-only template must exist so a cloner "
                        "can see what a targets file looks like.")
        json.loads(_read(_TEMPLATE))

    def test_the_template_is_never_auto_discovered(self):
        """Auto-loading it would silence the refusal with fake targets."""
        for cand in self.mod.DEFAULT_TARGETS_FILES:
            self.assertNotEqual(
                cand.name, _TEMPLATE.name,
                "the template must NEVER be in DEFAULT_TARGETS_FILES: its "
                "placeholder values would make the target set non-empty and so "
                "silence the refusal, yielding a build that reports VERIFIED "
                "CLEAN having scrubbed nothing real.")

    def test_an_unfilled_template_yields_zero_targets(self):
        """The trap, end to end: a cloner copies the template, forgets to fill
        it in, and runs the builder. It must behave as 'no targets given'."""
        ns = type("NS", (), {"targets_file": str(_TEMPLATE), "target": None})
        self.assertEqual(
            self.mod.load_targets_values(ns), [],
            "an UNFILLED template produced targets. The build would then run a "
            "full 'verified' pass against placeholder strings and scrub nothing.")

    def test_every_template_value_is_placeholder_shaped(self):
        doc = json.loads(_read(_TEMPLATE))
        for key, values in doc.items():
            if key.startswith("_"):
                continue
            for value in values:
                self.assertTrue(
                    self.mod._is_placeholder(value),
                    f"template value {value!r} under {key!r} is not recognised "
                    f"as a placeholder, so it would be scrubbed for real.")

    def test_documentation_keys_are_not_treated_as_targets(self):
        """cpd.load_targets turns EVERY dict key into a category and every value
        into a target, so a `_README` string would become a 'private value'."""
        with tempfile.TemporaryDirectory() as td:
            probe = Path(td) / "t.json"
            probe.write_text(json.dumps({
                "_README": "this line is documentation, never a target",
                "_note": ["also documentation"],
                "names": ["Real Person Name"],
            }), encoding="utf-8")
            ns = type("NS", (), {"targets_file": str(probe), "target": None})
            self.assertEqual(self.mod.load_targets_values(ns),
                             ["Real Person Name"])

    def test_angelas_name_and_handle_are_never_scrubbed(self):
        """Unchanged rule, re-pinned here because the filter chain grew."""
        for kept in ("Angela", "Angela Lopez Mendoza", "Ángela López Mendoza",
                     "@angelahack1", "angelahack1"):
            self.assertTrue(self.mod._is_kept_name(kept), kept)


# =============================================================================
# 4 + 5. THE REFUSAL SURVIVES, AND IT FAILS TOWARD REFUSAL
# =============================================================================
class RefusalStillProtectsAKeyedTreeTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_builder()

    def _preflight_in(self, root: Path) -> list:
        saved = self.mod.REPO_ROOT
        try:
            self.mod.REPO_ROOT = root
            return self.mod.privacy_preflight()
        finally:
            self.mod.REPO_ROOT = saved

    def test_a_keyed_agent_config_is_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "Tlamatini" / "agent" / "agents" / "telegrammer"
            d.mkdir(parents=True)
            (d / "config.yaml").write_text(
                "bot_token: '8123456789:AAH7xQvZk3mNpQrStUvWxYz012345678abc'\n"
                "recipient: 'someone.real@gmail.com'\n", encoding="utf-8")
            evidence = self._preflight_in(root)
        self.assertTrue(evidence, "a live bot token must block a no-targets build.")
        self.assertIn("bot_token", " ".join(evidence))

    def test_a_secrets_vault_is_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Tlamatini" / "agent").mkdir(parents=True)
            (root / "data.keys").write_text("SOME_KEY=abc123\n", encoding="utf-8")
            evidence = self._preflight_in(root)
        self.assertTrue(evidence, "data.keys means this is a keyed tree.")

    def test_a_contacts_book_is_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            agent = root / "Tlamatini" / "agent"
            agent.mkdir(parents=True)
            (agent / "contacts.json").write_text(
                json.dumps({"someone": {"phone": "+52 55 1234 5678"}}),
                encoding="utf-8")
            evidence = self._preflight_in(root)
        self.assertTrue(evidence, "real contacts must block a no-targets build.")

    def test_an_unreadable_file_counts_as_evidence(self):
        """FAIL TOWARD REFUSAL -- the deliberate inverse of fail-open.

        A file that could not be checked must never be called clean: the cost of
        a wrong 'clean' verdict is publishing Angela's private data.
        """
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            agent = root / "Tlamatini" / "agent"
            agent.mkdir(parents=True)
            (agent / "config.json").write_text("{ this is not json",
                                               encoding="utf-8")
            evidence = self._preflight_in(root)
        self.assertTrue(evidence, "a malformed config must be treated as "
                                  "private data present, not silently skipped.")
        self.assertIn("UNREADABLE", " ".join(evidence))

    def test_the_override_is_explicit_and_documented_as_dangerous(self):
        src = _read(_BUILDER_PATH)
        self.assertIn('"--assume-clean-tree"', src)
        self.assertIn("DANGEROUS", src)

    def test_the_pristine_verdict_never_claims_a_pii_verification(self):
        """NO LYING: a clean-tree build must not imply a check it never ran."""
        src = _read(_BUILDER_PATH)
        self.assertIn("STRUCTURAL-ONLY", src)
        self.assertIn("structural_only", src)
        self.assertIn("STRUCTURAL_ONLY_SENTINEL", src,
                      "check_private_data exits 2 with no targets, so a sentinel "
                      "keeps the structural layers running instead of silently "
                      "dropping the only post-build audit.")


# =============================================================================
# 6. REGEN IS AUTOMATIC, AND EVERY FILE IT REWRITES IS BACKED UP FIRST
# =============================================================================
class RegenIsAutomaticAndFullyBackedUpTests(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mod = _load_builder()

    def test_push_able_runs_inside_the_builder(self):
        """Nobody should have to run regen_secrets.py before building."""
        src = _read(_BUILDER_PATH)
        self.assertRegex(
            src, r'run\(\[py,\s*str\(REGEN\),\s*"--mode",\s*"push-able"\]\)',
            "the public builder must invoke regen_secrets --mode push-able "
            "itself, so a keyed tree can never be built by forgetting a step.")
        self.assertLess(
            src.index('"push-able"'), src.index("str(BUILD)"),
            "secrets must become placeholders BEFORE build.py reads the tree.")

    def test_the_finally_block_restores_and_rekeys(self):
        src = _read(_BUILDER_PATH)
        tail = src.split("finally:", 1)[1]
        self.assertIn("restore_all", tail)
        self.assertIn('"--mode", "keyed"', tail,
                      "the tree must be re-keyed from data.keys afterwards.")

    def test_every_regen_touched_file_is_backed_up_first(self):
        """The hand-typed list carried 5 of 7 agent configs.

        `zavuerer` and `discoverer` were rewritten with NO backup, so on a
        machine without data.keys (where the `finally` re-key is skipped) the
        operator lost those keys silently.
        """
        names = {p.parent.name if p.name == "config.yaml" else p.name
                 for p in self.mod.REGEN_TOUCHED}
        for agent in _REGEN_AGENTS:
            self.assertIn(
                agent, names,
                f"regen_secrets rewrites agents/{agent}/config.yaml but the "
                f"builder does not back it up first.")
        self.assertIn("config.json", names)
        self.assertIn("external_mcps.json", names)

    def test_the_backup_list_is_derived_not_hand_typed(self):
        src = _read(_BUILDER_PATH)
        self.assertIn("def _regen_touched_files", src)
        self.assertIn("REGEN_TOUCHED = _regen_touched_files()", src,
                      "read the paths from regen_secrets itself, so the NEXT "
                      "managed config file is covered the day it is added.")

    def test_the_derived_list_matches_regen_secrets_exactly(self):
        """Cross-check against the real regen_secrets module."""
        spec = importlib.util.spec_from_file_location(
            "_tlm_regen_for_test", _REPO_ROOT / "regen_secrets.py")
        regen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(regen)
        expected = {v for name, v in vars(regen).items()
                    if name.isupper() and isinstance(v, Path)
                    and v.name in ("config.json", "config.yaml",
                                   "external_mcps.json")}
        self.assertTrue(expected, "regen_secrets exposes no managed paths")
        self.assertTrue(
            expected.issubset(set(self.mod.REGEN_TOUCHED)),
            "these regen-managed files are not backed up: %s"
            % sorted(str(p) for p in expected - set(self.mod.REGEN_TOUCHED)))

    def test_the_keys_vault_and_targets_file_are_never_scrubbed(self):
        """Scrubbing the sources of truth turned real values into <REDACTED>
        inside them and produced the historical 737-false-positive run."""
        for name in ("data.keys",) + _TARGETS_BASENAMES:
            self.assertIn(name, self.mod.SCRUB_SKIP_FILES, name)


if __name__ == "__main__":  # pragma: no cover
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tlamatini.settings")
    unittest.main()
