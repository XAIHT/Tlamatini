# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import yaml

from .agent_paths import (
    display_name_from_agent_type,
    get_agents_root,
    normalize_agent_type,
)


DEFAULT_CONNECTION_FIELDS = (
    "source_agents",
    "target_agents",
    "output_agents",
    "source_agent",
    "target_agent",
    "source_agent_1",
    "source_agent_2",
    "target_agents_a",
    "target_agents_b",
    "target_agents_l",
    "target_agents_g",
)


@dataclass(frozen=True)
class AgentContract:
    agent_type: str
    display_name: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)
    source_list_field: str = "source_agents"
    output_field_by_slot: dict[int, str] = field(default_factory=lambda: {0: "target_agents"})
    input_field_by_slot: dict[int, str] = field(default_factory=lambda: {0: "source_agents"})
    connection_fields: tuple[str, ...] = DEFAULT_CONNECTION_FIELDS
    no_input: bool = False
    no_output: bool = False
    exclude_from_validation: bool = False
    singleton: bool = False
    long_running: bool = False
    never_starts_targets: bool = False
    parametrizer_fields: tuple[str, ...] = field(default_factory=tuple)
    secret_paths: tuple[str, ...] = field(default_factory=tuple)
    password_paths: tuple[str, ...] = field(default_factory=tuple)
    special: str = ""

    def __post_init__(self):
        object.__setattr__(self, "agent_type", normalize_agent_type(self.agent_type))
        if not self.display_name:
            object.__setattr__(self, "display_name", display_name_from_agent_type(self.agent_type))

    @property
    def script_name(self) -> str:
        return f"{self.agent_type}.py"

    @property
    def normalized_aliases(self) -> tuple[str, ...]:
        values = {self.agent_type, normalize_agent_type(self.display_name)}
        values.update(normalize_agent_type(alias) for alias in self.aliases)
        return tuple(sorted(value for value in values if value))


def _contract(agent_type: str, **kwargs: Any) -> AgentContract:
    return AgentContract(agent_type=agent_type, **kwargs)


_PARAMETRIZER_OUTPUT_FIELDS: dict[str, tuple[str, ...]] = {
    "apirer": ("url", "response_body"),
    "gitter": ("git_command", "response_body"),
    "kuberneter": ("parameters", "status", "response_body"),
    "crawler": ("label", "model", "url", "crawl_type", "content_mode", "response_body"),
    "summarizer": ("model", "source", "response_body"),
    "file_interpreter": ("file_path", "mode", "response_body"),
    "image_interpreter": (
        "file_path", "interpreter_model_1", "interpreter_model_2",
        "merging_model", "status", "response_body",
    ),
    "video_analyzer": (
        "video_path", "verdict", "verdict_token", "confidence", "motion_score",
        "frames_analyzed", "interpreter_model_1", "interpreter_model_2",
        "merging_model", "status", "response_body",
    ),
    "file_extractor": ("file_path", "response_body"),
    "prompter": ("model", "response_body"),
    "flowcreator": ("model", "response_body"),
    "kyber_keygen": ("public_key", "private_key"),
    "kyber_cipher": ("encapsulation", "initialization_vector", "cipher_text"),
    "kyber_decipher": ("deciphered_buffer",),
    "gatewayer": ("event_id", "event_type", "session_id", "correlation_id", "content_type", "method", "path", "body"),
    "gateway_relayer": ("event_type", "delivery_id", "action", "ref", "repository", "sender", "body"),
    "de_compresser": ("operation", "extension", "input", "output", "passwordless", "success", "response_body"),
    "googler": ("url", "title", "status", "content_length", "response_body"),
    "acpxer": ("agent_id", "session_id", "transport", "settle", "transcript_path", "response_body"),
    "shoter": ("output_path", "output_dir", "filename", "response_body"),
    "camcorder": ("output_path", "output_dir", "filename", "media_type", "camera_index", "duration_seconds", "resolution", "fps", "response_body"),
    "globber": ("pattern", "path", "matches", "truncated", "status", "response_body"),
    "grepper": ("pattern", "path", "glob", "matches", "files_searched", "truncated", "status", "response_body"),
    "editor": ("file_path", "status", "occurrences", "replacements", "response_body"),
    "recorder": ("output_path", "output_dir", "filename", "device_index", "device_name", "sample_rate", "channels", "duration_seconds", "gain_percent", "clipped_samples", "format", "response_body"),
    "whisperer": ("transcript_path", "audio_path", "input_source", "engine", "model", "device", "language", "duration_seconds", "segments", "word_count", "status", "response_body"),
    "audioplayer": ("input_path", "input_dir", "filename", "device_index", "device_name", "file_sample_rate", "play_sample_rate", "channels", "volume_percent", "clipped_samples", "file_duration_seconds", "time_played_requested", "played_seconds", "play_mode", "loops", "partial_segment", "format", "status", "response_body"),
    "videoplayer": ("input_path", "input_dir", "filename", "display_index", "display_geometry", "video_width", "video_height", "window_width", "window_height", "fullscreen", "volume_percent", "backend", "has_audio", "file_duration_seconds", "time_played_requested", "played_seconds", "play_mode", "loops", "partial_segment", "format", "status", "response_body"),
    "talker": ("output_path", "output_dir", "filename", "model", "language", "voice", "gender", "emotion", "sample_rate", "audio_seconds", "char_count", "played", "status", "response_body"),
    "mouser": ("movement_type", "end_posx", "end_posy", "button_click", "clicked", "located_via", "response_body"),
    "windower": ("action", "window_title", "matched", "match_count", "state", "left", "top", "width", "height", "response_body"),
    "unrealer": ("host", "port", "command", "status", "error", "response_body"),
    "blenderer": ("host", "port", "command", "status", "error", "response_body"),
    "reviewer": ("repo_path", "diff_ref", "verdict", "model", "status", "response_body"),
    "analyzer": ("target_path", "tools_run", "tools_skipped", "total_findings", "status", "response_body"),
    "playwrighter": ("start_url", "final_url", "status", "steps_run", "assert_result", "response_body"),
    "kalier": ("action", "endpoint", "method", "subject", "return_code", "success", "timed_out", "server_url", "response_body"),
    "stm32er": ("action", "tool", "ok", "returncode", "success", "project_dir", "session_id", "stage", "server_script", "response_body"),
    "esp32er": ("action", "tool", "ok", "returncode", "success", "project_dir", "port", "environment", "stage", "response_body"),
    "esphomer": ("action", "tool", "ok", "returncode", "success", "config_path", "name", "port", "stage", "response_body"),
    "arduiner": ("action", "tool", "ok", "returncode", "success", "fqbn", "port", "sketch_path", "stage", "response_body"),
    "mcp_doctor": ("server_key", "transport", "runtime", "supported", "status", "catalog_path", "response_body"),
    "instant_messaging_doctor": ("platform", "status", "telegram_status", "whatsapp_status", "contact_status", "repair_status", "retry_status", "actions_required", "response_body"),
    "discoverer": ("tool", "target", "returncode", "success", "findings_count", "json_path", "pdcp_used", "stage", "response_body"),
    "telegrammer": ("chat_id", "status", "message_id", "response_body"),
    "whatsapper": ("recipient", "status", "message_id", "response_body"),
    "zavuerer": ("action", "channel", "to", "status", "message_id", "success", "base_url", "response_body"),
}


_BUILTIN_CONTRACTS: dict[str, AgentContract] = {
    "starter": _contract("starter", no_input=True),
    "flowcreator": _contract("flowcreator", no_input=True, no_output=True, singleton=True, exclude_from_validation=True),
    "flowhypervisor": _contract("flowhypervisor", no_input=True, no_output=True, singleton=True, exclude_from_validation=True, long_running=True),
    "ender": _contract("ender", output_field_by_slot={0: "output_agents"}, special="ender"),
    "stopper": _contract("stopper", output_field_by_slot={0: "output_agents"}, never_starts_targets=True),
    "cleaner": _contract("cleaner", output_field_by_slot={0: "output_agents"}, never_starts_targets=True),
    "asker": _contract("asker", output_field_by_slot={0: "target_agents_a", 1: "target_agents_a", 2: "target_agents_b"}),
    "forker": _contract("forker", output_field_by_slot={0: "target_agents_a", 1: "target_agents_a", 2: "target_agents_b"}),
    "counter": _contract("counter", output_field_by_slot={0: "target_agents_l", 1: "target_agents_l", 2: "target_agents_g"}),
    "and": _contract("and", input_field_by_slot={0: "source_agent_1", 1: "source_agent_1", 2: "source_agent_2"}),
    "or": _contract("or", input_field_by_slot={0: "source_agent_1", 1: "source_agent_1", 2: "source_agent_2"}),
    "parametrizer": _contract("parametrizer", special="parametrizer"),
    "teletlamatini": _contract(
        "teletlamatini",
        long_running=True,
        special="remote_chat_ingress",
        secret_paths=(
            "telegram.api_hash",
            "telegram.bot_token",
            "password",
            "tlamatini.password",
        ),
    ),
    "telegrammer": _contract(
        "telegrammer",
        parametrizer_fields=("chat_id", "status", "message_id", "response_body"),
        secret_paths=("telegram.bot_token",),
    ),
    "whatsapper": _contract(
        "whatsapper",
        parametrizer_fields=("recipient", "status", "message_id", "response_body"),
        secret_paths=("whatsapp.access_token",),
    ),
    "instant_messaging_doctor": _contract(
        "instant_messaging_doctor",
        parametrizer_fields=(
            "platform",
            "status",
            "telegram_status",
            "whatsapp_status",
            "contact_status",
            "repair_status",
            "retry_status",
            "actions_required",
            "response_body",
        ),
        secret_paths=("telegram.bot_token", "telegram.api_hash", "telegram.session_string", "whatsapp.access_token"),
    ),
    "gatewayer": _contract("gatewayer", long_running=True),
    "gateway_relayer": _contract("gateway_relayer", long_running=True, aliases=("gateway-relayer", "gateway relayer")),
    "node_manager": _contract("node_manager", long_running=True, aliases=("node-manager", "node manager")),
    # Kalier bridges to the MCP-Kali-Server HTTP API. Its hydra single-password
    # field is credential-shaped, so redact it from .flw exports.
    "kalier": _contract("kalier", secret_paths=("password",)),
    # Zavuerer bridges to the Zavu unified-messaging REST API; its zavu_api_key is a
    # credential, so redact it from .flw exports.
    "zavuerer": _contract("zavuerer", secret_paths=("zavu_api_key",)),
}


_NEVER_START_TARGETS = {
    "emailer",
    "monitor_log",
    "monitor_netstat",
    "recmailer",
}


# Dotted paths inside an agent's config.yaml whose value MUST be force-quoted
# (double-quoted) when written to disk. App passwords for Gmail/Outlook/etc.
# are word-tokens separated by spaces (e.g. "wvqt jved ymfm kexc"), and a
# default-flow yaml.dump of a string with leading-zero-like tokens or unusual
# characters can drift between quoted and unquoted forms across writes — which
# the user does not want for credentials. Forcing the quotes also makes the
# password visually delimited in the source file, so it cannot be silently
# truncated by an in-line trailing comment. The Flow Compiler, the canvas
# item-dialog save endpoint, and the per-agent connection-update views all
# go through the same dump helper and read this map.
_PASSWORD_PATHS_BY_AGENT: dict[str, tuple[str, ...]] = {
    "emailer": ("smtp.password",),
    "recmailer": ("imap.password",),
}


def _read_template_config(agent_type: str) -> dict[str, Any]:
    config_path = get_agents_root() / agent_type / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _discover_contracts_from_disk() -> dict[str, AgentContract]:
    root = get_agents_root()
    discovered: dict[str, AgentContract] = {}
    if not root.exists():
        return discovered

    for item in sorted(root.iterdir()):
        if not item.is_dir() or item.name.lower() in {"pools", "__pycache__"}:
            continue
        agent_type = normalize_agent_type(item.name)
        config = _read_template_config(agent_type)
        output_fields = {0: "target_agents"}
        input_fields = {0: "source_agents"}
        if "output_agents" in config and "target_agents" not in config:
            output_fields = {0: "output_agents"}

        discovered[agent_type] = _contract(
            agent_type,
            output_field_by_slot=output_fields,
            input_field_by_slot=input_fields,
            never_starts_targets=agent_type in _NEVER_START_TARGETS,
            parametrizer_fields=_PARAMETRIZER_OUTPUT_FIELDS.get(agent_type, ()),
            password_paths=_PASSWORD_PATHS_BY_AGENT.get(agent_type, ()),
        )
    return discovered


@lru_cache(maxsize=1)
def get_agent_contracts() -> dict[str, AgentContract]:
    contracts = _discover_contracts_from_disk()
    for agent_type, contract in _BUILTIN_CONTRACTS.items():
        parametrizer_fields = _PARAMETRIZER_OUTPUT_FIELDS.get(agent_type, contract.parametrizer_fields)
        password_paths = _PASSWORD_PATHS_BY_AGENT.get(agent_type, contract.password_paths)
        overrides: dict[str, Any] = {}
        if parametrizer_fields != contract.parametrizer_fields:
            overrides["parametrizer_fields"] = parametrizer_fields
        if password_paths != contract.password_paths:
            overrides["password_paths"] = password_paths
        if overrides:
            contract = AgentContract(
                **{
                    **contract.__dict__,
                    **overrides,
                }
            )
        contracts[agent_type] = contract
    return contracts


def get_password_paths(agent_type: str) -> tuple[str, ...]:
    """Return the dotted paths whose values must be force-quoted in YAML
    output for a given agent. Falls back to an empty tuple for unknown
    agent types so callers can pass it directly to the dump helper."""
    if not agent_type:
        return ()
    return get_agent_contract(agent_type).password_paths


@lru_cache(maxsize=1)
def _alias_map() -> dict[str, str]:
    result: dict[str, str] = {}
    for agent_type, contract in get_agent_contracts().items():
        for alias in contract.normalized_aliases:
            result[alias] = agent_type
    return result


def resolve_agent_type(value: str) -> str:
    normalized = normalize_agent_type(value)
    return _alias_map().get(normalized, normalized)


def get_agent_contract(value: str) -> AgentContract:
    agent_type = resolve_agent_type(value)
    contracts = get_agent_contracts()
    if agent_type in contracts:
        return contracts[agent_type]
    return _contract(agent_type)


def get_parametrizer_source_fields() -> dict[str, list[str]]:
    return {
        agent_type: list(contract.parametrizer_fields)
        for agent_type, contract in get_agent_contracts().items()
        if contract.parametrizer_fields
    }


def redact_config_for_export(agent_type: str, config: dict[str, Any]) -> dict[str, Any]:
    contract = get_agent_contract(agent_type)
    if not contract.secret_paths:
        return dict(config)

    redacted = deepcopy(config)
    for dotted_path in contract.secret_paths:
        parts = dotted_path.split(".")
        parent: Any = redacted
        for part in parts[:-1]:
            if not isinstance(parent, dict):
                parent = None
                break
            parent = parent.get(part)
        if isinstance(parent, dict) and parts[-1] in parent and parent[parts[-1]]:
            parent[parts[-1]] = "__REDACTED__"
    return redacted


def list_contract_summaries() -> list[dict[str, Any]]:
    summaries = []
    for contract in sorted(get_agent_contracts().values(), key=lambda c: c.agent_type):
        summaries.append(
            {
                "agent_type": contract.agent_type,
                "display_name": contract.display_name,
                "aliases": list(contract.normalized_aliases),
                "no_input": contract.no_input,
                "no_output": contract.no_output,
                "exclude_from_validation": contract.exclude_from_validation,
                "long_running": contract.long_running,
                "parametrizer_fields": list(contract.parametrizer_fields),
                "special": contract.special,
            }
        )
    return summaries
