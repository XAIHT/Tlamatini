"""
regen_secrets.py — toggle Tlamatini config files between two modes:

    --mode push-able   Replace every secret value with a generic placeholder
                       like "<ANTHROPIC_API_KEY goes here>" so the repo can be
                       pushed to GitHub without tripping push-protection.
    --mode keyed       Read real values from `data.keys` and write them back
                       into the same files for local development.

Targeted files (resolved relative to this script):

    Tlamatini/agent/config.json
        ANTHROPIC_API_KEY  (top + acpx.agents.claude.env)
        GEMINI_API_KEY     (top + acpx.agents.gemini.env)
        GOOGLE_API_KEY     (acpx.agents.gemini.env, alias)
        OPENAI_API_KEY     (acpx.agents.codex.env)
        ollama_token       (top)

    Tlamatini/agent/agents/telegramer/config.yaml
        telegram.api_id, telegram.api_hash, telegram.chat_id

    Tlamatini/agent/agents/telegramrx/config.yaml
        telegram.api_id, telegram.api_hash, telegram.listen_chat

    Tlamatini/agent/agents/teletlamatini/config.yaml
        telegram.api_id, telegram.api_hash, telegram.bot_token,
        password,
        tlamatini.username, tlamatini.password

    Tlamatini/agent/agents/emailer/config.yaml
        smtp.username, smtp.password (Gmail app password from
        https://myaccount.google.com/apppasswords)

    Tlamatini/agent/agents/recmailer/config.yaml
        imap.username, imap.password (Gmail app password from
        https://myaccount.google.com/apppasswords)

YAML files are edited line-by-line so all comments survive intact. The JSON
file is round-tripped through json.load/dump (its existing format already uses
indent=2 and pseudo "_section_*" comment-keys that survive verbatim).

All writes are atomic (write to .tmp, then os.replace).

Usage:
    python regen_secrets.py --mode push-able
    python regen_secrets.py --mode keyed
    python regen_secrets.py --mode keyed --keys-file other.keys
    python regen_secrets.py --mode keyed --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parent

CONFIG_JSON = REPO_ROOT / "Tlamatini" / "agent" / "config.json"
TELEGRAMER_YAML = REPO_ROOT / "Tlamatini" / "agent" / "agents" / "telegramer" / "config.yaml"
TELEGRAMRX_YAML = REPO_ROOT / "Tlamatini" / "agent" / "agents" / "telegramrx" / "config.yaml"
TELETLAMATINI_YAML = REPO_ROOT / "Tlamatini" / "agent" / "agents" / "teletlamatini" / "config.yaml"
EMAILER_YAML = REPO_ROOT / "Tlamatini" / "agent" / "agents" / "emailer" / "config.yaml"
RECMAILER_YAML = REPO_ROOT / "Tlamatini" / "agent" / "agents" / "recmailer" / "config.yaml"


def placeholder(name: str) -> str:
    """Generic, identifiable, non-secret-looking placeholder string."""
    return f"<{name} goes here>"


def parse_keys_file(path: Path) -> Dict[str, str]:
    """Parse a `KEY=VALUE` file. Comments (`#...`) and blank lines ignored."""
    if not path.exists():
        raise FileNotFoundError(
            f"keys file not found: {path}\n"
            f"Create it (see data.keys.example) before running --mode keyed."
        )
    out: Dict[str, str] = {}
    for raw_lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            print(f"WARN  {path.name}:{raw_lineno} no '=' — skipped: {line!r}",
                  file=sys.stderr)
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ────────────────────────────────────────────────────────────────────────
# JSON: config.json
# ────────────────────────────────────────────────────────────────────────

def resolve_value(mode: str, keys: Dict[str, str], data_key: str,
                  placeholder_label: str | None = None) -> str:
    if mode == "push-able":
        return placeholder(placeholder_label or data_key)
    # keyed
    return keys.get(data_key, "")


def patch_config_json(mode: str, keys: Dict[str, str], dry_run: bool) -> List[str]:
    if not CONFIG_JSON.exists():
        return [f"SKIP  {CONFIG_JSON} (missing)"]
    data: Dict[str, Any] = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))

    changes: List[str] = []

    def set_top(json_key: str, data_key: str) -> None:
        new_val = resolve_value(mode, keys, data_key, placeholder_label=json_key)
        if data.get(json_key) != new_val:
            changes.append(f"  config.json[{json_key!r}] <- {data_key}")
        data[json_key] = new_val

    def set_acpx_env(agent_id: str, env_key: str, data_key: str) -> None:
        acpx = data.setdefault("acpx", {})
        agents = acpx.setdefault("agents", {})
        agent = agents.get(agent_id)
        if not isinstance(agent, dict):
            return  # leave alone if the agent block doesn't exist
        env = agent.setdefault("env", {})
        new_val = resolve_value(mode, keys, data_key, placeholder_label=env_key)
        if env.get(env_key) != new_val:
            changes.append(f"  config.json[acpx.agents.{agent_id}.env.{env_key}] <- {data_key}")
        env[env_key] = new_val

    set_top("ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    set_top("GEMINI_API_KEY",    "GEMINI_API_KEY")
    set_top("ollama_token",      "OLLAMA_TOKEN")

    set_acpx_env("claude", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY")
    set_acpx_env("gemini", "GEMINI_API_KEY",    "GEMINI_API_KEY")
    set_acpx_env("gemini", "GOOGLE_API_KEY",    "GOOGLE_API_KEY")
    set_acpx_env("codex",  "OPENAI_API_KEY",    "OPENAI_API_KEY")

    serialized = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if not dry_run:
        atomic_write(CONFIG_JSON, serialized)
    return [f"WROTE {CONFIG_JSON.relative_to(REPO_ROOT)}"] + changes


# ────────────────────────────────────────────────────────────────────────
# YAML: surgical line-level edits (preserves every comment + ordering)
# ────────────────────────────────────────────────────────────────────────

# Each rule: (yaml_path, data_key) where yaml_path is a list of nested keys.
TELEGRAMER_RULES: List[Tuple[List[str], str]] = [
    (["telegram", "api_id"],   "TELEGRAMER_API_ID"),
    (["telegram", "api_hash"], "TELEGRAMER_API_HASH"),
    (["telegram", "chat_id"],  "TELEGRAMER_CHAT_ID"),
]

TELEGRAMRX_RULES: List[Tuple[List[str], str]] = [
    (["telegram", "api_id"],       "TELEGRAMRX_API_ID"),
    (["telegram", "api_hash"],     "TELEGRAMRX_API_HASH"),
    (["telegram", "listen_chat"],  "TELEGRAMRX_LISTEN_CHAT"),
]

TELETLAMATINI_RULES: List[Tuple[List[str], str]] = [
    (["telegram", "api_id"],    "TELETLAMATINI_API_ID"),
    (["telegram", "api_hash"],  "TELETLAMATINI_API_HASH"),
    (["telegram", "bot_token"], "TELETLAMATINI_BOT_TOKEN"),
    (["password"],              "TELETLAMATINI_PASSWORD"),
    (["tlamatini", "username"], "TLAMATINI_USERNAME"),
    (["tlamatini", "password"], "TLAMATINI_PASSWORD"),
]

EMAILER_RULES: List[Tuple[List[str], str]] = [
    (["smtp", "username"], "EMAILER_USERNAME"),
    (["smtp", "password"], "EMAILER_PASSWORD"),
]

RECMAILER_RULES: List[Tuple[List[str], str]] = [
    (["imap", "username"], "RECMAILER_USERNAME"),
    (["imap", "password"], "RECMAILER_PASSWORD"),
]


_KEY_RE = re.compile(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:(?P<rest>.*)$")


def _quote_value(value: str) -> str:
    """Render a YAML scalar that won't be re-parsed as int/bool/null/list/etc."""
    if value == "":
        return '""'
    # Numeric-looking → wrap in quotes only when the original spot expected a string.
    # We always quote to keep things deterministic; YAML accepts quoted ints in
    # any string-valued field, and Telethon coerces api_id back to int itself.
    # But api_id MUST be int — handle that by leaving bare digits unquoted.
    if re.fullmatch(r"-?\d+", value):
        return value
    if re.fullmatch(r"-?\d+\.\d+", value):
        return value
    # Anything containing special YAML chars or starting with reserved chars
    # gets double-quoted with backslash-escaping for `"` and `\`.
    needs_quote = (
        value[0] in "!&*[]{}|>%@`#," or
        value.lower() in ("true", "false", "yes", "no", "on", "off", "null", "~") or
        any(ch in value for ch in [':', '#', '\n', '\t']) or
        value != value.strip()
    )
    if needs_quote:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _patch_yaml_text(text: str, rules: List[Tuple[List[str], str]],
                     mode: str, keys: Dict[str, str],
                     file_label: str) -> Tuple[str, List[str]]:
    """
    Walk `text` line-by-line and rewrite the value of each `yaml_path`.
    Indent-based path tracking is good enough for our hand-written YAML files
    (no anchors, no flow-style nested mappings, no sequences-of-mappings).
    """
    lines = text.splitlines(keepends=False)
    # Pre-compute target last-key + parent-key chain by indent depth.
    # indent_stack: list of (indent, key) describing the current path.
    indent_stack: List[Tuple[int, str]] = []
    rule_index_by_full_path: Dict[str, Tuple[List[str], str]] = {
        ".".join(path): (path, dk) for path, dk in rules
    }
    matched_paths: set[str] = set()
    changes: List[str] = []

    out: List[str] = []
    for line in lines:
        m = _KEY_RE.match(line)
        if not m:
            out.append(line)
            continue
        indent = len(m.group("indent"))
        key = m.group("key")
        rest = m.group("rest")  # leading colon already consumed

        # Pop any deeper-or-equal-indent frames before recording this one.
        while indent_stack and indent_stack[-1][0] >= indent:
            indent_stack.pop()
        indent_stack.append((indent, key))

        full_path = ".".join(k for _, k in indent_stack)

        rule = rule_index_by_full_path.get(full_path)
        if rule is None:
            out.append(line)
            continue

        path, data_key = rule
        new_val = resolve_value(mode, keys, data_key)
        formatted = _quote_value(new_val)
        # Preserve any inline comment after the value.
        comment_match = re.search(r"\s+#.*$", rest)
        comment = comment_match.group(0) if comment_match else ""
        new_line = f"{m.group('indent')}{key}: {formatted}{comment}"
        if new_line != line:
            changes.append(f"  {file_label}:{full_path} <- {data_key}")
        out.append(new_line)
        matched_paths.add(full_path)

    # Note any rule that never fired — the caller sees this in the change log.
    for full_path in rule_index_by_full_path:
        if full_path not in matched_paths:
            changes.append(f"  WARN {file_label}:{full_path} not present in file (skipped)")

    final = "\n".join(out)
    if text.endswith("\n") and not final.endswith("\n"):
        final += "\n"
    return final, changes


def patch_yaml(path: Path, rules: List[Tuple[List[str], str]],
               mode: str, keys: Dict[str, str], dry_run: bool) -> List[str]:
    if not path.exists():
        return [f"SKIP  {path} (missing)"]
    original = path.read_text(encoding="utf-8")
    new_text, changes = _patch_yaml_text(
        original, rules, mode, keys,
        file_label=str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
    )
    if not dry_run:
        atomic_write(path, new_text)
    return [f"WROTE {path.relative_to(REPO_ROOT)}"] + changes


# ────────────────────────────────────────────────────────────────────────
# CLI
# ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Toggle Tlamatini config files between push-able and keyed mode.",
    )
    parser.add_argument(
        "--mode", required=True, choices=("push-able", "keyed"),
        help="push-able = generic placeholders; keyed = real values from data.keys",
    )
    parser.add_argument(
        "--keys-file", default=str(REPO_ROOT / "data.keys"),
        help="Path to the KEY=VALUE secrets file (default: data.keys next to script).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would change without writing any files.",
    )
    args = parser.parse_args()

    if args.mode == "keyed":
        keys = parse_keys_file(Path(args.keys_file))
    else:
        keys = {}  # push-able doesn't need any real values

    print(f"== Tlamatini regen_secrets.py — mode={args.mode}"
          f"{' (dry-run)' if args.dry_run else ''} ==")

    reports: List[List[str]] = [
        patch_config_json(args.mode, keys, args.dry_run),
        patch_yaml(TELEGRAMER_YAML,    TELEGRAMER_RULES,    args.mode, keys, args.dry_run),
        patch_yaml(TELEGRAMRX_YAML,    TELEGRAMRX_RULES,    args.mode, keys, args.dry_run),
        patch_yaml(TELETLAMATINI_YAML, TELETLAMATINI_RULES, args.mode, keys, args.dry_run),
        patch_yaml(EMAILER_YAML,       EMAILER_RULES,       args.mode, keys, args.dry_run),
        patch_yaml(RECMAILER_YAML,     RECMAILER_RULES,     args.mode, keys, args.dry_run),
    ]
    for block in reports:
        for line in block:
            print(line)

    print("== done ==")
    if args.mode == "push-able":
        print("Reminder: confirm with `git diff`, then commit + push.")
        print("After pushing, run `python regen_secrets.py --mode keyed` to restore real values.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
