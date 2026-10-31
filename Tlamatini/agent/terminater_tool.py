# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""terminater_tool.py -- the TYPED door from the chat model to Terminater.

WHY THIS EXISTS (a Rust tutorial, 2026-10-21).  The wrapped Terminater tool used to take ONE
free-text sentence ("Type into the terminal with terminal='t2' (title Rust Lesson) using
action='run', ... submit=false -- type the line but do NOT press Enter ...") that a regex then
tore into key=value pairs.  The tear was wrong more often than anyone saw: a title swallowed the
next parameter, so the command ran in a NEW terminal nobody was watching; and a sentence glued to
``submit=false`` was read as TRUE, so Enter was pressed on a line the user meant to run
themselves.

Here every parameter is its OWN typed field.  Nothing is parsed out of prose.  A field that is
not what it should be is REFUSED, with a reason the model can act on - never guessed.  The values
go straight into the agent's config (``_launch_wrapped_chat_agent(..., config_overrides=...)``),
so no text parser sits between the model and the terminal.

Everything in :func:`prepare` is pure (no I/O) and is tested without a shell.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from . import terminal_guard

logger = logging.getLogger(__name__)

TOOL_NAME = "chat_agent_terminater"

#: Kept equal to ``terminater_engine.ACTIONS`` by a drift test.
ACTIONS = (
    "run", "open", "type", "send_key", "wait", "read", "commands", "abort", "kill", "force_kill",
    "kill_all", "list", "status", "focus", "rename", "layout", "clear", "resize", "watch_user",
    "warn_user", "handover",
)
#: Kept equal to ``terminater_engine._ACTION_ALIASES`` by a drift test.
ACTION_ALIASES = {
    "execute": "run", "exec": "run", "command": "run", "launch": "open", "new": "open", "spawn": "open",
    "raise": "open", "create": "open", "press": "send_key", "key": "send_key", "keys": "send_key",
    "output": "read", "result": "read", "get_output": "read", "interrupt": "abort", "cancel": "abort",
    "ctrl_c": "abort", "terminate": "kill", "close": "kill", "destroy": "force_kill", "tile": "layout",
    "arrange": "layout", "show": "layout", "hide": "layout", "watch": "watch_user", "observe": "watch_user",
    "warn": "warn_user", "advise": "warn_user", "ask_user": "handover", "history": "commands",
    "force": "force_kill", "kill_force": "force_kill", "forcekill": "force_kill", "killall": "kill_all",
}

KINDS = ("cmd", "powershell", "pwsh")
_KIND_ALIASES = {"ps": "powershell", "windows_powershell": "powershell", "powershell7": "pwsh",
                 "pwsh7": "pwsh", "command_prompt": "cmd", "cmd.exe": "cmd", "powershell.exe": "powershell"}
SEVERITIES = ("info", "hint", "warning", "danger")

#: (name, python type, schema default, description).  ONE argument each - this table IS the schema.
#: The defaults are informational (they equal config.yaml's): only the arguments the model really
#: passed ever reach :func:`prepare`, so "not given" and "given" stay distinguishable.
_FIELDS = (
    ("action", str, "", "What to do: run (default when `text` is given), open, type, send_key, wait, read, "
                        "commands, abort, kill, force_kill, kill_all, list, status, focus, rename, layout, "
                        "clear, resize, watch_user, warn_user, handover."),
    ("terminal", str, "", "Which terminal: its id exactly as open/list returned it (like 't2'), or its exact "
                          "title. Empty = the active one. A terminal that is not there is REFUSED."),
    ("kind", str, "", "cmd | powershell | pwsh - only used when a terminal is opened."),
    ("title", str, "", "Title for a terminal being opened (or the new title for rename)."),
    ("cwd", str, "", "Working folder for a terminal being opened."),
    ("text", str, "", "The command, EXACTLY as it must be typed (backslashes and quotes verbatim, no escaping). "
                      "<<USER:hint>> hands the keyboard to the user at that point."),
    ("text_b64", str, "", "Same as text, base64 of UTF-8 (byte-exact)."),
    ("submit", bool, True, "true = press Enter so the command RUNS. false = only TYPE the line and leave it "
                           "waiting for the USER to press Enter. A real true/false - never a sentence."),
    ("wait", bool, True, "Wait for the command to finish."),
    ("wait_seconds", float, 120.0, "Stop waiting after this many seconds."),
    ("hang_seconds", float, 45.0, "Flag the command as hung after this long without output."),
    ("user_wait_seconds", float, 300.0, "How long to wait for the user's part of a <<USER:...>> hand-over."),
    ("typing_wpm", int, 50, "Typing speed, 20-250 words per minute. Never instant."),
    ("explanation", str, "", "Brief non-secret explanation for command narration. Never include passwords or private input."),
    ("secret", bool, False, "true = the typed text is a secret: never logged or returned."),
    ("keys", str, "", "send_key: key names, e.g. 'ctrl+c', 'enter', 'up up enter'."),
    ("which", str, "last", "read: 'last', a command number, 'screen' (what is visible now) or 'all'."),
    ("read_chars", int, 20000, "read: maximum characters to return."),
    ("offset", int, 0, "read: start at this character of a long output."),
    ("until", str, "", "wait: prompt | pattern | idle.  watch_user: idle | submit | key."),
    ("pattern", str, "", "wait with until='pattern': a regular expression to wait for."),
    ("idle_seconds", float, 2.0, "wait/watch_user: seconds of silence that count as idle."),
    ("cursor", int, 0, "watch_user: the cursor value from the previous reply."),
    ("message", str, "", "warn_user: the warning shown in the user's terminal."),
    ("severity", str, "warning", "warn_user: info | hint | warning | danger."),
    ("suggestion", str, "", "warn_user: a suggested replacement line."),
    ("hint", str, "", "handover: what the user should type."),
    ("layout", str, "", "layout: tabs | tile | tile-h | tile-v | grid."),
    ("area", str, "", "layout: dock | full (full = the whole canvas area)."),
    ("show", bool, True, "Show the Terminals area when the action runs."),
    ("close_after", bool, False, "run: close the terminal when the command completed."),
    ("load_profile", bool, True, "PowerShell: load the user's profile."),
    ("advisor", bool, True, "Warn the user about dangerous or mistyped commands."),
    ("create_if_missing", bool, False, "run: allow raising a NEW terminal named `terminal` when none has that "
                                       "name. A name that is not there is a mistake, not a request."),
    ("clear_line", bool, False, "type/run: replace a line already waiting on the prompt instead of refusing."),
    ("check_line", bool, True, "Read the prompt back before and after typing. Leave it on."),
)

FIELD_NAMES = tuple(name for name, _kind, _default, _doc in _FIELDS)

_TEXT_KEYS = ("text", "text_b64", "message", "suggestion", "hint", "explanation")      # never stripped / reshaped
_STRING_KEYS = ("terminal", "kind", "title", "cwd", "keys", "which", "until", "pattern", "severity",
                "layout", "area")
_BOOL_KEYS = ("submit", "wait", "secret", "show", "close_after", "load_profile", "advisor",
              "create_if_missing", "clear_line", "check_line")
_INT_KEYS = ("typing_wpm", "read_chars", "offset", "cursor")
_FLOAT_KEYS = ("wait_seconds", "hang_seconds", "user_wait_seconds", "idle_seconds")
#: A model that echoes a schema default as 0 means "not set": 0 seconds of hang detection would
#: flag every command as hung, 0 words per minute is not a speed.
_POSITIVE_ONLY = ("typing_wpm", "read_chars", "wait_seconds", "hang_seconds", "user_wait_seconds",
                  "idle_seconds")
_NEEDS_TEXT = ("run", "type")


class ArgError(Exception):
    """A request the tool refuses, with a code and a sentence the model can act on."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Prepared:
    cfg: Dict[str, Any]
    action: str
    request_text: str
    notes: List[str] = field(default_factory=list)


def _terminal_ref_to_text(value: Any) -> Any:
    """``terminal=2`` is a plain way to say 't2'; anything else is left for the checks below."""
    if isinstance(value, int) and not isinstance(value, bool):
        return f"t{value}"
    return value


def build_args_model() -> Any:
    """The pydantic model that is the tool's argument schema (one simple field per setting).

    ``extra='forbid'`` matters: with the default (ignore) a misspelt ``submitt=false`` would be
    dropped without a word and the line would run.
    """
    from typing import Annotated

    from pydantic import BeforeValidator, Field, create_model

    options: Dict[str, Any] = {}
    try:
        from pydantic import ConfigDict

        options["__config__"] = ConfigDict(extra="forbid")
    except ImportError:  # pragma: no cover - pydantic v1 ignores unknown keys
        pass

    definitions: Dict[str, Any] = {}
    for name, kind, default, doc in _FIELDS:
        annotation = Annotated[str, BeforeValidator(_terminal_ref_to_text)] if name == "terminal" else kind
        definitions[name] = (annotation, Field(default=default, description=doc))
    return create_model("TerminaterArgs", **options, **definitions)


def _text_module() -> Any:
    """``terminater_text`` (loaded with the engine, by path).  None when it cannot be loaded."""
    try:
        from . import terminal_hub

        return terminal_hub.load_engine()._tx
    except Exception:  # noqa: BLE001 -- the engine validates again; this is only the early, crisp refusal
        return None


def _short(value: Any, limit: int = 160) -> str:
    text = str(value)
    return repr(text if len(text) <= limit else text[:limit] + "...")


def normalize_action(value: Any, has_text: bool) -> str:
    token = re.sub(r"[\s\-]+", "_", str(value or "").strip().lower())
    if not token:
        if has_text:
            return "run"
        raise ArgError(
            "missing_action",
            "Pass `action` (for example action='run' with text='...', action='open', action='list' or "
            "action='read'). Each setting is its own argument - do not describe the call in a sentence.")
    token = ACTION_ALIASES.get(token, token)
    if token not in ACTIONS:
        raise ArgError("unknown_action", f"Unknown action {str(value)[:60]!r}. Valid actions: {', '.join(ACTIONS)}.")
    return token


def legacy_arguments(request: Any) -> Dict[str, Any]:
    """An old-style single string is accepted ONLY when it is a JSON object of the same fields."""
    text = str(request or "").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            data = None
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if v is not None}
    raise ArgError(
        "sentence_not_accepted",
        "This tool takes typed arguments, not a sentence. Call it again with separate fields, e.g. "
        "action='run', terminal='t2', text='cargo build', submit=false.")


def _normalize_kind(value: str) -> str:
    token = re.sub(r"[\s\-]+", "_", value.strip().lower())
    token = _KIND_ALIASES.get(token, token)
    if token not in KINDS:
        raise ArgError("bad_kind", f"`kind` must be one of {', '.join(KINDS)} (got {value[:40]!r}).")
    return token


def prepare(kwargs: Dict[str, Any], user_runs: bool = False) -> Prepared:
    """Typed arguments -> the agent's config.  Raises :class:`ArgError`; never guesses."""
    raw = {k: v for k, v in dict(kwargs or {}).items() if v is not None}
    unknown = sorted(set(raw) - set(FIELD_NAMES))
    if unknown:
        raise ArgError("unknown_argument", "Unknown argument(s): " + ", ".join(unknown[:6])
                       + ". Valid arguments: " + ", ".join(FIELD_NAMES) + ".")
    notes: List[str] = []
    cfg: Dict[str, Any] = {}

    has_text = bool(str(raw.get("text") or "").strip() or str(raw.get("text_b64") or "").strip())
    action = normalize_action(raw.get("action"), has_text)
    cfg["action"] = action

    for key in _STRING_KEYS:
        value = raw.get(key)
        if value is None:
            continue
        value = str(_terminal_ref_to_text(value)).strip()
        if value:
            cfg[key] = value
    for key in _TEXT_KEYS:
        value = raw.get(key)
        if value is not None and str(value) != "":
            cfg[key] = str(value)
    for key in _BOOL_KEYS:
        if raw.get(key) is not None:
            cfg[key] = bool(raw[key])
    for key in _INT_KEYS:
        if raw.get(key) is not None:
            cfg[key] = int(raw[key])
    for key in _FLOAT_KEYS:
        if raw.get(key) is not None:
            cfg[key] = float(raw[key])
    for key in _POSITIVE_ONLY:
        if key in cfg and cfg[key] <= 0:
            cfg.pop(key)

    if "kind" in cfg:
        cfg["kind"] = _normalize_kind(cfg["kind"])
    if "severity" in cfg:
        cfg["severity"] = cfg["severity"].lower()
        if cfg["severity"] not in SEVERITIES:
            raise ArgError("bad_severity", f"`severity` must be one of {', '.join(SEVERITIES)}.")

    # A name that is not there is a MISTAKE unless the caller says a missing one may be created.
    cfg["create_if_missing"] = bool(raw.get("create_if_missing")) if raw.get("create_if_missing") is not None else False

    text_module = _text_module()
    ref = cfg.get("terminal", "")
    if ref and text_module is not None:
        problem = text_module.terminal_ref_problem(ref)
        if problem:
            raise ArgError(
                "bad_terminal_ref",
                f"`terminal` {str(ref)[:70]!r} cannot be a terminal id or title: {problem}. Pass the exact "
                "terminal_id returned by action='open' or action='list' (like 't2'), as its own argument.")

    if cfg.get("text") and cfg.get("text_b64"):
        notes.append("both text and text_b64 were given; text_b64 was used and text ignored")
        cfg.pop("text", None)

    if action in _NEEDS_TEXT and not (cfg.get("text") or cfg.get("text_b64")):
        raise ArgError("empty_text", f"action='{action}' needs `text` - the command to type, exactly as it must be typed.")
    if action == "send_key" and not (cfg.get("keys") or cfg.get("text")):
        raise ArgError("missing_keys", "action='send_key' needs `keys`, for example keys='ctrl+c' or keys='up up enter'.")

    if user_runs:
        _apply_user_runs(cfg, action, notes)

    return Prepared(cfg=cfg, action=action, request_text=render_request(cfg), notes=notes)


_ENTER_KEY = re.compile(r"(?:^|[\s,+])(?:enter|return|ctrl\s*\+\s*m)(?=$|[\s,+])", re.IGNORECASE)


def _line_count(text: str) -> int:
    return len([ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()])


def _apply_user_runs(cfg: Dict[str, Any], action: str, notes: List[str]) -> None:
    """LIVE-TUTORIAL MODE: the user presses Enter.  Tlamatini may type the line, never run it."""
    if action in ("run", "type", "handover"):
        if _line_count(cfg.get("text") or "") > 1:
            raise ArgError(
                "user_runs_multiline",
                "LIVE-TUTORIAL MODE: the user runs the commands, and every line break in `text` would press Enter "
                "and run the lines before the last one. Send ONE line per call (join steps with ';' when they belong "
                "together), with submit=false.")
        if cfg.get("submit") is not False:
            cfg["submit"] = False
            notes.append("LIVE-TUTORIAL MODE: the user runs the commands, so Enter was NOT pressed - "
                         "the line is only typed and the USER presses Enter")
    elif action == "send_key" and _ENTER_KEY.search(cfg.get("keys") or cfg.get("text") or ""):
        raise ArgError(
            "user_runs_enter",
            "LIVE-TUTORIAL MODE: the user runs the commands, so you must not press Enter for them. Type the line "
            "with action='run' (submit=false) and let the user press Enter.")


def render_request(cfg: Dict[str, Any]) -> str:
    """A readable one-liner for logs and the run record (never parsed back)."""
    parts = []
    for key, value in cfg.items():
        if key == "text_b64":
            parts.append("text_b64=<base64>")
        else:
            parts.append(f"{key}={_short(value)}")
    return "Terminater " + " ".join(parts)


def shell_kind(tool_input: Any) -> str:
    """cmd | powershell | pwsh for the Ask-Execs dialog (typed `kind`, or a legacy sentence)."""
    try:
        text = ""
        if isinstance(tool_input, dict):
            text = str(tool_input.get("kind") or "")
            if not text:
                text = str(tool_input.get("request") or tool_input.get("__arg1") or "")
        elif isinstance(tool_input, str):
            text = tool_input
        found = re.search(r"(pwsh|powershell\s*7|cmd|powershell)", text, re.IGNORECASE)
        if not found:
            from .context_governor import current_user
            from .interaction_settings import snapshot
            return snapshot(current_user())[0]['shell']
        token = found.group(1).lower().replace(" ", "")
        if token in ("pwsh", "powershell7"):
            return "pwsh"
        return "cmd" if token == "cmd" else "powershell"
    except Exception:  # noqa: BLE001
        return "powershell"


def refusal(code: str, message: str, wrap_output: Callable[[Any], str]) -> str:
    """The standard JSON reply for a request that was refused before anything ran."""
    return wrap_output({
        "tool": TOOL_NAME, "status": "refused", "agent_status": "refused", "success": False,
        "code": code, "message": message, "retryable": True, "error_kind": "request",
    })


def _annotate(result: Any, prepared: Prepared, wrap_output: Callable[[Any], str]) -> Any:
    """Add what THIS layer decided (coercions) to the launcher's JSON reply."""
    if not prepared.notes:
        return result
    try:
        payload = json.loads(result) if isinstance(result, str) else result
        if not isinstance(payload, dict):
            return result
        payload["request_notes"] = list(prepared.notes)
        if any(note.startswith("LIVE-TUTORIAL MODE") for note in prepared.notes):
            payload["live_tutorial_mode"] = True
        return wrap_output(payload)
    except Exception:  # noqa: BLE001
        return result


def tool_description(spec: Any) -> str:
    return (f"{spec.purpose}\n\nPass each setting as its own argument (never a sentence). "
            f"Example: {spec.example_request}")


def build_tool(spec: Any, launch: Callable[..., str], wrap_output: Callable[[Any], str]) -> Any:
    """The tool the model binds.  ``launch`` is ``tools._launch_wrapped_chat_agent``."""
    from langchain_core.tools import StructuredTool

    class TerminaterTool(StructuredTool):
        """A StructuredTool that treats ``null`` like "not given" (models echo schema fields as null)."""

        def _parse_input(self, tool_input, *args, **kwargs):  # noqa: ANN001
            if isinstance(tool_input, dict):
                tool_input = {k: v for k, v in tool_input.items() if v is not None}
            return super()._parse_input(tool_input, *args, **kwargs)

    def _run(*args: Any, **kwargs: Any) -> str:
        try:
            if args:
                kwargs = dict(kwargs, **legacy_arguments(args[0]))
            prepared = prepare(kwargs, user_runs=terminal_guard.user_runs_active())
        except ArgError as exc:
            return refusal(exc.code, exc.message, wrap_output)
        except Exception as exc:  # noqa: BLE001
            return refusal("bad_arguments", f"The arguments could not be read: {exc}", wrap_output)
        result = launch(spec, prepared.request_text, config_overrides=prepared.cfg)
        return _annotate(result, prepared, wrap_output)

    def _on_validation_error(error: Any) -> str:
        problems = []
        try:
            for item in error.errors():
                where = ".".join(str(p) for p in item.get("loc", ())) or "arguments"
                problems.append(f"{where}: {item.get('msg', 'invalid')}")
        except Exception:  # noqa: BLE001
            problems.append(str(error)[:300])
        return refusal(
            "bad_argument",
            "These arguments are not valid - " + "; ".join(problems[:6]) + ". Pass each setting as its own "
            "argument; yes/no settings must be real true or false, numbers must be numbers.", wrap_output)

    return TerminaterTool.from_function(
        func=_run,
        name=spec.tool_name,
        description=tool_description(spec),
        args_schema=build_args_model(),
        handle_validation_error=_on_validation_error,
    )
