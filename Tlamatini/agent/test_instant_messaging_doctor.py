"""Instant Messaging Doctor contract and Parametrizer integration tests."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import tempfile
from pathlib import Path

from django.test import SimpleTestCase
import yaml

from agent.services.agent_contracts import get_parametrizer_source_fields

_AGENT_DIR = Path(__file__).resolve().parent


def _load_agent_module(rel_parts, mod_name):
    path = _AGENT_DIR.joinpath(*rel_parts)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    root = logging.getLogger()
    before = list(root.handlers)
    cwd = os.getcwd()
    try:
        spec.loader.exec_module(module)
    finally:
        os.chdir(cwd)
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
    return module


PARAM = _load_agent_module(["agents", "parametrizer", "parametrizer.py"], "param_mod_for_im_doc_test")
IM_DOCTOR = _load_agent_module(
    ["agents", "instant_messaging_doctor", "instant_messaging_doctor.py"],
    "im_doc_mod_for_param_test",
)


def _emit_and_capture(result):
    captured = []

    class _Cap(logging.Handler):
        def emit(self, record):
            captured.append(record.getMessage())

    handler = _Cap()
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        IM_DOCTOR._emit_section(result)
    finally:
        root.removeHandler(handler)
    for message in captured:
        if "INI_SECTION_INSTANT_MESSAGING_DOCTOR" in message:
            return message
    raise AssertionError("Instant Messaging Doctor did not emit its INI section")


class InstantMessagingDoctorTests(SimpleTestCase):
    def test_config_defaults_are_parseable_and_official_only(self):
        config_path = _AGENT_DIR / "agents" / "instant_messaging_doctor" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle)

        self.assertEqual(config["platform"], "both")
        self.assertEqual(config["ollama"]["model"], "glm-5.2:cloud")
        self.assertIn(config["telegram"]["provider"], {"auto", "bot", "user"})
        self.assertEqual(config["whatsapp"]["graph_base"], "https://graph.facebook.com")

    def test_registry_contract_and_parametrizer_membership(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS

        spec = next((item for item in WRAPPED_CHAT_AGENT_SPECS if item.key == "instant_messaging_doctor"), None)
        self.assertIsNotNone(spec)
        self.assertEqual(spec.tool_name, "chat_agent_instant_messaging_doctor")

        self.assertIn("instant_messaging_doctor", PARAM.SECTION_AGENT_TYPES)
        fields = get_parametrizer_source_fields()["instant_messaging_doctor"]
        for key in (
            "platform",
            "status",
            "telegram_status",
            "whatsapp_status",
            "contact_status",
            "repair_status",
            "retry_status",
            "actions_required",
            "response_body",
        ):
            self.assertIn(key, fields)

    def test_diagnose_missing_credentials_emits_parseable_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_json = os.path.join(tmp, "config.json")
            contacts_json = os.path.join(tmp, "contacts.json")
            with open(config_json, "w", encoding="utf-8") as handle:
                json.dump({}, handle)
            with open(contacts_json, "w", encoding="utf-8") as handle:
                json.dump({"contacts": [{"name": "Angela", "telegram": "@angela_user", "whatsapp": "+525500000001"}]}, handle)

            result = IM_DOCTOR.diagnose({
                "config_path": config_json,
                "contacts_path": contacts_json,
                "contact_name": "Angela",
                "platform": "both",
                "use_llm": False,
            })

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["contact_status"], "ready")
        section = _emit_and_capture(result)
        fields = PARAM.parse_unified_output(section, "instant_messaging_doctor")[0]
        self.assertEqual(fields["platform"], "both")
        self.assertEqual(fields["status"], "blocked")
        self.assertEqual(fields["contact_status"], "ready")
        self.assertIn("response_body", fields)

    def test_contract_fields_all_resolve_against_real_emission(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_json = os.path.join(tmp, "config.json")
            contacts_json = os.path.join(tmp, "contacts.json")
            with open(config_json, "w", encoding="utf-8") as handle:
                json.dump({}, handle)
            with open(contacts_json, "w", encoding="utf-8") as handle:
                json.dump({"contacts": []}, handle)

            result = IM_DOCTOR.diagnose({
                "config_path": config_json,
                "contacts_path": contacts_json,
                "platform": "whatsapp",
                "use_llm": False,
            })

        fields = PARAM.parse_unified_output(_emit_and_capture(result), "instant_messaging_doctor")[0]
        advertised = set(get_parametrizer_source_fields()["instant_messaging_doctor"]) - {"response_body"}
        missing = advertised - set(fields.keys())
        self.assertEqual(missing, set(), f"contract advertises unparseable fields: {missing}")

    def test_overall_status_order(self):
        self.assertEqual(IM_DOCTOR._overall_status(["ready", "skipped"]), "ready")
        self.assertEqual(IM_DOCTOR._overall_status(["ready", "needs_operator"]), "needs_operator")
        self.assertEqual(IM_DOCTOR._overall_status(["sent", "ready"]), "sent")
        self.assertEqual(IM_DOCTOR._overall_status(["missing", "ready"]), "blocked")
