# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
Password-quoting contract tests for Emailer and Recmailer.

Every code path that writes an Emailer or Recmailer `config.yaml` MUST emit
the password embraced by double quotes. The four paths exercised here:

    1. `dump_agent_config_yaml` directly (the central helper).
    2. `compile_flow_spec(write=True)` (Start sequence + .flw load via the
       Flow Compiler).
    3. `update_emailer_connection_view` / `update_recmailer_connection_view`
       (canvas connection updates).
    4. `regen_secrets._patch_yaml_text` (the push-able / keyed scrubber).

The tests also confirm the round-trip property: yaml.safe_load on the written
file returns the original unquoted password string, so wrapping the value with
`_QuotedStr` only changes the on-disk presentation, not the parsed value.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml
from django.test import RequestFactory, SimpleTestCase

from agent.services.agent_contracts import (
    get_agent_contract,
    get_password_paths,
)
from agent.services.flow_compiler import (
    _QuotedStr,
    _wrap_password_values,
    compile_flow_spec,
    dump_agent_config_yaml,
)
from agent.services.flow_spec import FlowConnection, FlowNode, FlowSpec


# Make the regen_secrets script importable. It lives at the repo root, two
# levels up from `Tlamatini/agent/`. This mirrors what `python regen_secrets.py`
# does on the command line.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import regen_secrets  # noqa: E402


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class PasswordContractTests(SimpleTestCase):
    """The contracts that declare which fields must be force-quoted."""

    def test_emailer_contract_declares_smtp_password_path(self):
        contract = get_agent_contract("emailer")
        self.assertIn("smtp.password", contract.password_paths)

    def test_recmailer_contract_declares_imap_password_path(self):
        contract = get_agent_contract("recmailer")
        self.assertIn("imap.password", contract.password_paths)

    def test_get_password_paths_helper_returns_tuple_for_known_agents(self):
        self.assertEqual(get_password_paths("emailer"), ("smtp.password",))
        self.assertEqual(get_password_paths("recmailer"), ("imap.password",))

    def test_get_password_paths_returns_empty_for_unknown_agent(self):
        self.assertEqual(get_password_paths(""), ())
        self.assertEqual(get_password_paths("starter"), ())


class WrapPasswordValuesTests(SimpleTestCase):
    """The pre-dump walk that swaps in `_QuotedStr` markers."""

    def test_wraps_emailer_password_in_quoted_str(self):
        config = {"smtp": {"username": "u", "password": "<REDACTED>"}}
        wrapped = _wrap_password_values(config, ("smtp.password",))
        self.assertIsInstance(wrapped["smtp"]["password"], _QuotedStr)
        # Plain str fields are untouched.
        self.assertNotIsInstance(wrapped["smtp"]["username"], _QuotedStr)

    def test_wraps_empty_password_as_empty_quoted_str(self):
        config = {"smtp": {"password": ""}}
        wrapped = _wrap_password_values(config, ("smtp.password",))
        self.assertIsInstance(wrapped["smtp"]["password"], _QuotedStr)
        self.assertEqual(str(wrapped["smtp"]["password"]), "")

    def test_wraps_none_password_as_empty_quoted_str(self):
        config = {"smtp": {"password": None}}
        wrapped = _wrap_password_values(config, ("smtp.password",))
        self.assertIsInstance(wrapped["smtp"]["password"], _QuotedStr)
        self.assertEqual(str(wrapped["smtp"]["password"]), "")

    def test_does_not_create_missing_keys(self):
        config = {"smtp": {"username": "u"}}  # no password key
        wrapped = _wrap_password_values(config, ("smtp.password",))
        self.assertNotIn("password", wrapped["smtp"])

    def test_empty_password_paths_returns_input_untouched(self):
        config = {"smtp": {"password": "<REDACTED>"}}
        wrapped = _wrap_password_values(config, ())
        # Same identity — no copy was made.
        self.assertIs(wrapped, config)


class DumpAgentConfigYamlTests(SimpleTestCase):
    """The single dump helper that every write site funnels through."""

    def _dump_and_read(self, config: dict, agent_type: str) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as handle:
            tmp_path = Path(handle.name)
        try:
            dump_agent_config_yaml(config, tmp_path, agent_type)
            return _read(tmp_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_emailer_password_is_double_quoted(self):
        config = {
            "source_agents": [],
            "smtp": {
                "host": "smtp.gmail.com",
                "port": 587,
                "username": "alice",
                "password": "<REDACTED>",
                "use_tls": True,
            },
        }
        text = self._dump_and_read(config, "emailer")
        self.assertIn('password: "wvqt jved ymfm kexc"', text)
        # username is NOT force-quoted.
        self.assertIn("username: alice", text)
        # Round-trip: yaml.safe_load returns the original unquoted value.
        loaded = yaml.safe_load(text)
        self.assertEqual(loaded["smtp"]["password"], "wvqt jved ymfm kexc")

    def test_recmailer_password_is_double_quoted(self):
        config = {
            "source_agents": [],
            "imap": {
                "host": "imap.gmail.com",
                "port": 993,
                "username": "alice",
                "password": "<REDACTED>",
                "use_ssl": True,
            },
        }
        text = self._dump_and_read(config, "recmailer")
        self.assertIn('password: "abcd efgh ijkl mnop"', text)
        loaded = yaml.safe_load(text)
        self.assertEqual(loaded["imap"]["password"], "abcd efgh ijkl mnop")

    def test_empty_password_is_emitted_as_double_quoted_empty_string(self):
        config = {"smtp": {"password": ""}}
        text = self._dump_and_read(config, "emailer")
        self.assertIn('password: ""', text)
        loaded = yaml.safe_load(text)
        self.assertEqual(loaded["smtp"]["password"], "")

    def test_password_with_embedded_double_quote_is_escaped(self):
        config = {"smtp": {"password": 'has"quote'}}
        text = self._dump_and_read(config, "emailer")
        # The on-disk form must double-quote and backslash-escape the embedded ".
        self.assertIn('password: "has\\"quote"', text)
        loaded = yaml.safe_load(text)
        self.assertEqual(loaded["smtp"]["password"], 'has"quote')

    def test_unknown_agent_does_not_force_quote(self):
        # When agent_type doesn't declare password_paths, the dump path falls
        # back to PyYAML defaults — the test pins that we did NOT accidentally
        # apply the password layer to unrelated agents.
        config = {"smtp": {"password": "<REDACTED>"}}
        text = self._dump_and_read(config, "starter")
        # Bare scalar (no surrounding quotes).
        self.assertIn("password: secret", text)
        self.assertNotIn('password: "secret"', text)

    def test_multiline_string_still_uses_block_literal_style(self):
        # Existing behavior: multi-line strings get the `|` block style. The
        # password layer must not have broken this.
        config = {"email": {"body": "line one\nline two\n"}}
        text = self._dump_and_read(config, "emailer")
        self.assertIn("body: |", text)
        self.assertIn("line one", text)
        self.assertIn("line two", text)


class FlowCompilerWritePathTests(SimpleTestCase):
    """End-to-end through `compile_flow_spec(write=True)` — the path hit by
    the canvas Start button and the .flw deploy after FlowCreator generates a
    flow."""

    def test_compile_writes_emailer_config_with_quoted_password(self):
        spec = FlowSpec(
            nodes=[
                FlowNode(id="starter-1", text="Starter"),
                FlowNode(
                    id="emailer-1",
                    text="Emailer",
                    config={
                        "smtp": {
                            "host": "smtp.gmail.com",
                            "port": 587,
                            "username": "alice",
                            "password": "<REDACTED>",
                            "use_tls": True,
                            "use_ssl": False,
                        },
                    },
                ),
            ],
            connections=[FlowConnection(source_id="starter-1", target_id="emailer-1")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            pool_path = Path(tmp) / "pools" / "session"
            with patch(
                "agent.services.flow_compiler.get_session_pool_path",
                return_value=pool_path,
            ):
                compile_flow_spec(spec, write=True)

            written = _read(pool_path / "emailer_1" / "config.yaml")
            self.assertIn('password: "wvqt jved ymfm kexc"', written)
            loaded = yaml.safe_load(written)
            self.assertEqual(loaded["smtp"]["password"], "wvqt jved ymfm kexc")

    def test_compile_writes_recmailer_config_with_quoted_password(self):
        spec = FlowSpec(
            nodes=[
                FlowNode(id="starter-1", text="Starter"),
                FlowNode(
                    id="recmailer-1",
                    text="Recmailer",
                    config={
                        "imap": {
                            "host": "imap.gmail.com",
                            "port": 993,
                            "username": "alice",
                            "password": "<REDACTED>",
                            "use_ssl": True,
                        },
                    },
                ),
            ],
            connections=[FlowConnection(source_id="starter-1", target_id="recmailer-1")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            pool_path = Path(tmp) / "pools" / "session"
            with patch(
                "agent.services.flow_compiler.get_session_pool_path",
                return_value=pool_path,
            ):
                compile_flow_spec(spec, write=True)

            written = _read(pool_path / "recmailer_1" / "config.yaml")
            self.assertIn('password: "abcd efgh ijkl mnop"', written)
            loaded = yaml.safe_load(written)
            self.assertEqual(loaded["imap"]["password"], "abcd efgh ijkl mnop")

    def test_compile_does_not_force_quote_other_agents(self):
        # Sanity guard: a non-credential field on an unrelated agent stays
        # bare so we can tell the password layer is scoped, not global.
        spec = FlowSpec(
            nodes=[
                FlowNode(id="starter-1", text="Starter"),
                FlowNode(
                    id="executer-1",
                    text="Executer",
                    config={"script": "echo hi"},
                ),
            ],
            connections=[FlowConnection(source_id="starter-1", target_id="executer-1")],
        )

        with tempfile.TemporaryDirectory() as tmp:
            pool_path = Path(tmp) / "pools" / "session"
            with patch(
                "agent.services.flow_compiler.get_session_pool_path",
                return_value=pool_path,
            ):
                compile_flow_spec(spec, write=True)

            written = _read(pool_path / "executer_1" / "config.yaml")
            self.assertIn("script: echo hi", written)
            self.assertNotIn('script: "echo hi"', written)


class ConnectionUpdateViewTests(SimpleTestCase):
    """The two `update_*_connection_view` endpoints. They preserve and rewrite
    config.yaml when canvas wiring changes — and must keep the password
    embraced by `"` in the rewritten file."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _make_pool(self, agent_folder: str, config: dict) -> Path:
        pool_dir = Path(self.tmp.name) / agent_folder
        pool_dir.mkdir(parents=True, exist_ok=True)
        # Use the helper itself so the seed file already has quoted passwords.
        dump_agent_config_yaml(
            config, pool_dir / "config.yaml", agent_folder.split("_")[0]
        )
        return pool_dir

    def _post(self, view, agent_name: str, payload: dict, pool_root: Path):
        request = self.factory.post(
            f"/agent/update_{agent_name}_connection/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        with patch("agent.views.get_pool_path", return_value=str(pool_root)):
            return view(request, agent_name)

    def test_update_emailer_connection_keeps_password_quoted(self):
        from agent.views import update_emailer_connection_view

        pool_root = Path(self.tmp.name)
        emailer_config = {
            "source_agents": [],
            "smtp": {
                "host": "smtp.gmail.com",
                "port": 587,
                "username": "alice",
                "password": "<REDACTED>",
                "use_tls": True,
            },
        }
        self._make_pool("emailer_1", emailer_config)
        response = self._post(
            update_emailer_connection_view,
            "emailer-1",
            {
                "connection_type": "source",
                "connected_agent": "monitor-log-1",
                "action": "add",
            },
            pool_root,
        )
        self.assertEqual(response.status_code, 200)

        written = _read(pool_root / "emailer_1" / "config.yaml")
        self.assertIn('password: "wvqt jved ymfm kexc"', written)
        loaded = yaml.safe_load(written)
        self.assertEqual(loaded["smtp"]["password"], "wvqt jved ymfm kexc")
        self.assertEqual(loaded["source_agents"], ["monitor_log_1"])

    def test_update_recmailer_connection_keeps_password_quoted(self):
        from agent.views import update_recmailer_connection_view

        pool_root = Path(self.tmp.name)
        recmailer_config = {
            "source_agents": [],
            "imap": {
                "host": "imap.gmail.com",
                "port": 993,
                "username": "alice",
                "password": "<REDACTED>",
                "use_ssl": True,
            },
        }
        self._make_pool("recmailer_1", recmailer_config)
        response = self._post(
            update_recmailer_connection_view,
            "recmailer-1",
            {
                "connection_type": "source",
                "connected_agent": "monitor-log-1",
                "action": "add",
            },
            pool_root,
        )
        self.assertEqual(response.status_code, 200)

        written = _read(pool_root / "recmailer_1" / "config.yaml")
        self.assertIn('password: "abcd efgh ijkl mnop"', written)
        loaded = yaml.safe_load(written)
        self.assertEqual(loaded["imap"]["password"], "abcd efgh ijkl mnop")


class SaveAgentConfigViewTests(SimpleTestCase):
    """The canvas item-dialog Save endpoint. This is the path hit when the
    user edits an Emailer/Recmailer config in the canvas dialog (or when
    `acp-file-io.js` deploys a `.flw` produced by FlowCreator)."""

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _post(self, agent_name: str, payload: dict, pool_root: Path):
        from agent.views import save_agent_config_view

        request = self.factory.post(
            f"/agent/save_agent_config/{agent_name}/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        with patch("agent.views.get_pool_path", return_value=str(pool_root)):
            return save_agent_config_view(request, agent_name)

    def test_save_emailer_config_quotes_password(self):
        pool_root = Path(self.tmp.name)
        payload = {
            "source_agents": [],
            "smtp": {
                "host": "smtp.gmail.com",
                "port": 587,
                "username": "alice",
                "password": "<REDACTED>",
                "use_tls": True,
                "use_ssl": False,
            },
            "email": {"to_addresses": [""]},
        }
        response = self._post("emailer-1", payload, pool_root)
        self.assertEqual(response.status_code, 200)

        written = _read(pool_root / "emailer_1" / "config.yaml")
        self.assertIn('password: "wvqt jved ymfm kexc"', written)
        loaded = yaml.safe_load(written)
        self.assertEqual(loaded["smtp"]["password"], "wvqt jved ymfm kexc")

    def test_save_recmailer_config_quotes_password(self):
        pool_root = Path(self.tmp.name)
        payload = {
            "source_agents": [],
            "imap": {
                "host": "imap.gmail.com",
                "port": 993,
                "username": "alice",
                "password": "<REDACTED>",
                "use_ssl": True,
                "folder": "INBOX",
            },
        }
        response = self._post("recmailer-1", payload, pool_root)
        self.assertEqual(response.status_code, 200)

        written = _read(pool_root / "recmailer_1" / "config.yaml")
        self.assertIn('password: "abcd efgh ijkl mnop"', written)
        loaded = yaml.safe_load(written)
        self.assertEqual(loaded["imap"]["password"], "abcd efgh ijkl mnop")


class RegenSecretsPasswordQuotingTests(SimpleTestCase):
    """The push-able / keyed scrubber. Both modes must emit the password
    line with double quotes around the value."""

    def test_emailer_push_able_mode_double_quotes_password_placeholder(self):
        original = (
            "smtp:\n"
            "  username: alice\n"
            "  password: wvqt jved ymfm kexc\n"
        )
        new_text, _ = regen_secrets._patch_yaml_text(
            original,
            regen_secrets.EMAILER_RULES,
            mode="push-able",
            keys={},
            file_label="emailer/config.yaml",
            force_quote_passwords=True,
        )
        self.assertIn('password: "<EMAILER_PASSWORD goes here>"', new_text)

    def test_emailer_keyed_mode_double_quotes_real_password(self):
        original = (
            "smtp:\n"
            "  username: alice\n"
            "  password: <EMAILER_PASSWORD goes here>\n"
        )
        new_text, _ = regen_secrets._patch_yaml_text(
            original,
            regen_secrets.EMAILER_RULES,
            mode="keyed",
            keys={
                "EMAILER_USERNAME": "alice",
                "EMAILER_PASSWORD": "wvqt jved ymfm kexc",
            },
            file_label="emailer/config.yaml",
            force_quote_passwords=True,
        )
        self.assertIn('password: "wvqt jved ymfm kexc"', new_text)
        loaded = yaml.safe_load(new_text)
        self.assertEqual(loaded["smtp"]["password"], "wvqt jved ymfm kexc")

    def test_recmailer_keyed_mode_double_quotes_real_password(self):
        original = (
            "imap:\n"
            "  username: alice\n"
            "  password: <RECMAILER_PASSWORD goes here>\n"
        )
        new_text, _ = regen_secrets._patch_yaml_text(
            original,
            regen_secrets.RECMAILER_RULES,
            mode="keyed",
            keys={
                "RECMAILER_USERNAME": "alice",
                "RECMAILER_PASSWORD": "abcd efgh ijkl mnop",
            },
            file_label="recmailer/config.yaml",
            force_quote_passwords=True,
        )
        self.assertIn('password: "abcd efgh ijkl mnop"', new_text)
        loaded = yaml.safe_load(new_text)
        self.assertEqual(loaded["imap"]["password"], "abcd efgh ijkl mnop")

    def test_empty_password_in_keyed_mode_renders_as_quoted_empty_string(self):
        original = (
            "smtp:\n"
            "  username: alice\n"
            "  password: <EMAILER_PASSWORD goes here>\n"
        )
        new_text, _ = regen_secrets._patch_yaml_text(
            original,
            regen_secrets.EMAILER_RULES,
            mode="keyed",
            keys={"EMAILER_USERNAME": "alice"},  # no EMAILER_PASSWORD entry
            file_label="emailer/config.yaml",
            force_quote_passwords=True,
        )
        self.assertIn('password: ""', new_text)


class TemplateConfigYamlOnDiskTests(SimpleTestCase):
    """The static template files that ship with the source tree. After this
    pass they MUST contain a double-quoted `password:` line so they themselves
    are the source of truth for what every write site is supposed to emit."""

    def _project_agent_root(self) -> Path:
        # Tlamatini/agent/agents
        return Path(__file__).resolve().parent / "agents"

    def test_emailer_template_password_is_double_quoted(self):
        path = self._project_agent_root() / "emailer" / "config.yaml"
        self.assertTrue(path.exists(), f"missing template file: {path}")
        text = _read(path)
        # Look for `password: "<...>"` (push-able) or `password: "..."` (keyed).
        # Either way, the password line must START with `password: "`.
        password_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("password:")
        ]
        self.assertTrue(password_lines, "no `password:` line found in emailer template")
        for line in password_lines:
            # Drop trailing inline comments (e.g. `  # Use App Password...`).
            value_part = line.split("#", 1)[0].strip()
            self.assertTrue(
                value_part.startswith('password: "') and value_part.rstrip().endswith('"'),
                f"emailer template password not double-quoted: {line!r}",
            )

    def test_recmailer_template_password_is_double_quoted(self):
        path = self._project_agent_root() / "recmailer" / "config.yaml"
        self.assertTrue(path.exists(), f"missing template file: {path}")
        text = _read(path)
        password_lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip().startswith("password:")
        ]
        self.assertTrue(password_lines, "no `password:` line found in recmailer template")
        for line in password_lines:
            value_part = line.split("#", 1)[0].strip()
            self.assertTrue(
                value_part.startswith('password: "') and value_part.rstrip().endswith('"'),
                f"recmailer template password not double-quoted: {line!r}",
            )
