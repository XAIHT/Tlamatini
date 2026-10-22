# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""terminal_guard.py -- honesty rails for live terminal tutorials (Terminater).

WHY THIS EXISTS.  In a Rust tutorial (2026-10-21) the user said "you show me the commands and
I will execute them, not you".  Over eleven turns Tlamatini then (a) told the user a line was
"typed and sitting on your prompt" in turns where she had called NO tool at all, (b) ran
commands herself through invisible shells while the user watched an empty terminal, and
(c) said "I just executed the exe" about something she had run out of sight.  A model's prose is
not evidence.  Three deterministic jobs, none of them a model call:

1. USER-RUNS MODE.  When the user says THEY will run the commands, every general command runner
   (Executer, Pythonxer, SSHer, ...) is refused with an explanation, and Terminater is
   restricted to TYPING the line (``submit=false``): the user presses Enter.  The mode is read
   from the user's own words (English and Spanish), is sticky per user, and is lifted by
   "you run them" / "go ahead and run".
2. THE LEDGER.  Every Terminater / command-runner call of the request is recorded with what the
   tool REPORTED (status, whether the SCREEN showed the line, whether Enter was pressed).
3. THE CLAIM AUDIT.  Before an answer is final, sentences such as "I typed it", "is now sitting
   on your prompt" or "I just executed it" are checked against the ledger.  An unsupported
   claim gets ONE correction round, and if it survives, a visible warning is appended.

Nothing here may raise into a caller: every public function is total and fails OPEN (an error
means "no opinion"), because a guard that breaks the chat path is worse than the lie it hunts.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

TERMINATER_TOOL = "chat_agent_terminater"

#: Tools that RUN a command, script or program on the user's behalf.  In user-runs mode none of
#: them may run: the user is the one who executes.  (Terminater itself is handled separately - it
#: may still TYPE the line, but never press Enter.)
COMMAND_RUNNER_TOOLS = frozenset({
    "execute_command", "execute_file", "chat_agent_executer", "chat_agent_pythonxer",
    "chat_agent_ssher", "chat_agent_dockerer", "chat_agent_kuberneter", "chat_agent_gitter",
    "chat_agent_sqler", "chat_agent_mongoxer", "chat_agent_jenkinser", "chat_agent_kalier",
})

#: Terminater statuses that mean "a command was started / finished by Tlamatini's Enter".
_RAN_STATUSES = frozenset({"completed", "command_failed", "started", "hung", "timeout"})
#: Terminater statuses that mean "the line is on the terminal" (typed, or typed and run).
_TYPED_STATUSES = frozenset({"typed", "completed", "command_failed", "started", "hung", "timeout"})

MODE_TTL_SECONDS = 12 * 3600


def enabled() -> bool:
    """Master switch (config ``terminal_guard``, default on).  Fail-open to ON."""
    try:
        from .config_loader import get_config_value

        value = get_config_value("terminal_guard", True)
    except Exception:  # noqa: BLE001
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ("0", "false", "no", "off")
    return bool(value) if value is not None else True


# --------------------------------------------------------------------------- #
# 1. USER-RUNS MODE                                                            #
# --------------------------------------------------------------------------- #

@dataclass
class TutorialMode:
    user_runs: bool = False
    phrase: str = ""
    since: float = 0.0


_FLAGS = re.IGNORECASE

#: The user says THEY execute / type / run the commands (or that Tlamatini must not).
_TRIGGERS: Tuple["re.Pattern[str]", ...] = tuple(re.compile(p, _FLAGS) for p in (
    r"\bi\s*(?:'?ll|will|am\s+going\s+to|'?m\s+going\s+to|want\s+to|shall|can|prefer\s+to|would\s+like\s+to)"
    r"\s+(?:execute|run|type|enter|launch|do)\s+(?:them|those|these|it|that|each|every|all|the\s+(?:commands?|lines?|steps?))\b",
    r"\bi\s+(?:execute|run)\s+(?:them|the\s+commands?|each\s+command)\b",
    r"\b(?:you\s+(?:only\s+|just\s+)?|(?:just|only)\s+)(?:show|tell|give|dictate|teach)\s+me\s+"
    r"(?:the\s+)?(?:commands?|lines?|steps?)\b",
    r"\b(?:do\s*not|don'?t|dont|never)\s+(?:execute|run|press\s+enter|hit\s+enter)\b",
    r"\blet\s+me\s+(?:execute|run|type)\b",
    r"\b(?:execute|run|type)\b[^.\n]{0,40}\b(?:myself|by\s+myself)\b",
    r"\bi\s*(?:will|'?ll)\s+press\s+enter\b",
    # Spanish
    r"\byo\s+(?:los|las|lo|la)\s+(?:ejecuto|corro|escribo|tecleo|lanzo)\b",
    r"\bno\s+(?:los|las|lo|la)\s+(?:ejecutes|corras|escribas)\b",
    r"\bmu[eé]strame\s+(?:los\s+)?comandos\b",
    r"\byo\s+(?:voy\s+a\s+)?(?:ejecuto|ejecutar|corro|correr)\b",
))

#: The user gives the keyboard back to Tlamatini.
_LIFTS: Tuple["re.Pattern[str]", ...] = tuple(re.compile(p, _FLAGS) for p in (
    r"\byou\s+(?:can\s+|may\s+|should\s+|will\s+|please\s+|now\s+)*(?:go\s+ahead\s+and\s+)?"
    r"(?:execute|run|type)\s+(?:them|it|that|the\s+commands?|these|everything)\b",
    r"\b(?:execute|run)\s+(?:them|it|that|the\s+commands?)\s+(?:yourself|for\s+me|now)\b",
    r"\byou\s+(?:run|execute|do)\s+(?:them|it|that|the\s+commands?)\b",
    r"\byou\s+take\s+over\b",
    r"\bgo\s+ahead\s+and\s+(?:run|execute)\b",
    r"\bi\s+(?:no\s+longer|don'?t)\s+(?:want|need)\s+to\s+(?:run|execute|type)\b",
    r"\b(?:the\s+)?(?:live\s+)?tutorial\s+is\s+(?:over|done|finished)\b",
    # Spanish
    r"\bt[uú]\s+(?:los|las|lo|la)\s+(?:ejecutas|corres|escribes)\b",
    r"\bejec[uú]t(?:a|alo|alos|alas)\s+t[uú]\b",
    r"\bhazlo\s+t[uú]\b",
))

_LOCK = threading.RLock()
_MODES: Dict[str, TutorialMode] = {}
_USER_RUNS_ACTIVE: "contextvars.ContextVar[bool]" = contextvars.ContextVar(
    "tlamatini_terminal_user_runs", default=False)


def classify_message(text: Any) -> Tuple[str, str]:
    """``('user_runs' | 'lift' | '', matched phrase)`` for one user message.

    When a message holds both, the one that comes LAST in the text wins: people change their mind
    inside a sentence ("you run them - no, I will").
    """
    sample = str(text or "")[:6000]
    best_kind, best_phrase, best_at = "", "", -1
    for kind, patterns in (("lift", _LIFTS), ("user_runs", _TRIGGERS)):
        for rx in patterns:
            for found in rx.finditer(sample):
                if found.start() >= best_at:
                    best_kind, best_phrase, best_at = kind, found.group(0).strip(), found.start()
    return best_kind, best_phrase


def _human_texts(history: Any) -> Iterable[str]:
    if not isinstance(history, (list, tuple)):
        return
    for msg in history:
        try:
            if isinstance(msg, dict):
                role = str(msg.get("type") or msg.get("role") or "").lower()
                if role in ("human", "user"):
                    yield str(msg.get("content") or "")
            elif str(getattr(msg, "type", "")).lower() == "human":
                yield str(getattr(msg, "content", "") or "")
        except Exception:  # noqa: BLE001
            continue


def _key(user_id: Any) -> str:
    return str(user_id if user_id not in (None, "") else "-")


def observe(user_id: Any, current_text: Any, history: Any = None) -> TutorialMode:
    """Update and return the user's tutorial mode from the recent human messages + this one."""
    try:
        now = time.time()
        with _LOCK:
            mode = _MODES.get(_key(user_id)) or TutorialMode()
            if mode.user_runs and mode.since and now - mode.since > MODE_TTL_SECONDS:
                mode = TutorialMode()
            for text in list(_human_texts(history)) + [str(current_text or "")]:
                kind, phrase = classify_message(text)
                if kind == "lift":
                    mode = TutorialMode(False, phrase, now)
                elif kind == "user_runs":
                    mode = TutorialMode(True, phrase, now)
            _MODES[_key(user_id)] = mode
            return mode
    except Exception:  # noqa: BLE001 -- fail open: no mode
        return TutorialMode()


def get_mode(user_id: Any) -> TutorialMode:
    with _LOCK:
        return _MODES.get(_key(user_id)) or TutorialMode()


def reset(user_id: Any = None) -> None:
    """Forget the mode of one user (or of everybody)."""
    with _LOCK:
        if user_id is None:
            _MODES.clear()
        else:
            _MODES.pop(_key(user_id), None)


def enter_mode(user_runs: bool) -> "contextvars.Token[bool]":
    """Mark the CURRENT call context as user-runs, so the Terminater tool can force submit=false."""
    return _USER_RUNS_ACTIVE.set(bool(user_runs))


def leave_mode(token: "contextvars.Token[bool]") -> None:
    try:
        _USER_RUNS_ACTIVE.reset(token)
    except Exception:  # noqa: BLE001
        pass


def user_runs_active() -> bool:
    return bool(_USER_RUNS_ACTIVE.get())


def runner_block(tool_name: str, mode: Optional[TutorialMode]) -> str:
    """Why ``tool_name`` must NOT run now ('' = allowed).  The text goes to the model as the tool result."""
    try:
        if not enabled() or mode is None or not mode.user_runs:
            return ""
        if tool_name not in COMMAND_RUNNER_TOOLS:
            return ""
        said = f" ({mode.phrase!r})" if mode.phrase else ""
        return (
            "LIVE-TUTORIAL MODE - NOT EXECUTED. The user said they run the commands themselves" + said + ", so "
            f"'{tool_name}' was NOT run and nothing happened on their machine. Do this instead: put the line on "
            "THEIR terminal with chat_agent_terminater (action='run', terminal=<its terminal_id>, text=<the exact "
            "line>, submit=false), tell them exactly what is waiting there, and let THEM press Enter. To see a "
            "result, ask them to paste it or read their terminal with chat_agent_terminater (action='read', "
            "which='screen'). The user lifts this mode by saying that you may run commands yourself."
        )
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- #
# 2. THE LEDGER                                                                #
# --------------------------------------------------------------------------- #

@dataclass
class Evidence:
    tool: str
    action: str = ""
    terminal_id: str = ""
    status: str = ""
    ok: bool = False
    typed: str = ""
    verified: Optional[bool] = None
    enter_pressed: Optional[bool] = None
    ran: bool = False

    @property
    def typed_proof(self) -> bool:
        """The tool says a line is on the terminal, and the SCREEN did not contradict it."""
        return (self.tool == TERMINATER_TOOL and self.ok and self.status in _TYPED_STATUSES
                and self.verified is not False and bool(self.typed))


def _loads(text: Any) -> Dict[str, Any]:
    try:
        data = json.loads(text) if isinstance(text, str) else text
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _flag(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    text = str(value if value is not None else "").strip().lower()
    if text in ("true", "yes", "1"):
        return True
    if text in ("false", "no", "0"):
        return False
    return None


def evidence_from(tool_name: str, tool_input: Any, result_text: Any, success: bool) -> Optional[Evidence]:
    """One ledger entry for a call that matters here, else None.  Never raises."""
    try:
        if tool_name == TERMINATER_TOOL:
            args = tool_input if isinstance(tool_input, dict) else {}
            data = _loads(result_text)
            action = str(args.get("action") or data.get("action") or "").strip().lower()
            if not action and (args.get("text") or args.get("text_b64")):
                action = "run"
            status = str(data.get("agent_status") or data.get("status") or "").strip().lower()
            enter = _flag(data.get("enter_pressed"))
            ran = action in ("run", "type", "handover") and (enter is True or status in _RAN_STATUSES) and bool(success)
            return Evidence(
                tool=tool_name, action=action, terminal_id=str(data.get("terminal_id") or args.get("terminal") or ""),
                status=status, ok=bool(success), typed=str(data.get("typed") or ""),
                verified=_flag(data.get("verified")), enter_pressed=enter, ran=ran)
        if tool_name in COMMAND_RUNNER_TOOLS:
            return Evidence(tool=tool_name, ok=bool(success), ran=True)
    except Exception:  # noqa: BLE001
        return None
    return None


def describe_call(tool_input: Any) -> str:
    """A human line for a Terminater call: the Exec Report row and the Ask-Execs dialog."""
    try:
        if isinstance(tool_input, str):
            return tool_input
        args = dict(tool_input or {})
        legacy = str(args.get("request") or args.get("__arg1") or "").strip()
        action = str(args.get("action") or "").strip()
        if not action and (args.get("text") or args.get("text_b64")):
            action = "run"
        if not action and legacy:
            return legacy
        parts = [action or "run"]
        if args.get("terminal"):
            parts.append(f"[{args['terminal']}]")
        shown = args.get("text") or ("<base64 text>" if args.get("text_b64") else "") \
            or args.get("keys") or args.get("message") or args.get("title") or ""
        if shown:
            parts.append(str(shown))
        if action in ("run", "type", "handover", "") and _flag(args.get("submit")) is False:
            parts.append("(typed only - Enter NOT pressed)")
        return " ".join(parts)
    except Exception:  # noqa: BLE001
        return str(tool_input)


def result_summary(result_text: Any) -> str:
    """The tool's own verdict, in a few words (appended to the Exec Report row)."""
    try:
        data = _loads(result_text)
        status = str(data.get("agent_status") or data.get("status") or "").strip()
        bits: List[str] = [status] if status else []
        verified = _flag(data.get("verified"))
        if verified is True:
            bits.append("the screen shows it")
        elif verified is False:
            bits.append("NOT on the screen")
        enter = _flag(data.get("enter_pressed"))
        if enter is True:
            bits.append("Enter pressed")
        elif enter is False and status in ("typed", "typing_unverified"):
            bits.append("Enter NOT pressed")
        return ", ".join(bits)
    except Exception:  # noqa: BLE001
        return ""


def exec_report_command(tool_input: Any, result_text: Any) -> str:
    base = describe_call(tool_input)
    summary = result_summary(result_text)
    return f"{base}  ->  {summary}" if summary else base


# --------------------------------------------------------------------------- #
# 3. THE CLAIM AUDIT                                                           #
# --------------------------------------------------------------------------- #

@dataclass
class Problem:
    code: str       # claim_typed_no_call | claim_typed_unverified | claim_ran_no_call
    claim: str      # the offending sentence
    detail: str     # what the record shows


_TYPED_CLAIMS: Tuple["re.Pattern[str]", ...] = tuple(re.compile(p, _FLAGS) for p in (
    r"\bi\s*(?:'?ve|have|just|now|already)?\s*(?:typed|entered|put|placed|left)\b[^.\n]{0,160}"
    r"\b(?:prompt|terminal|console|shell)\b",
    r"\b(?:is|are|it'?s)\s+(?:now\s+)?(?:typed|sitting|waiting|staged|ready)\b[^.\n]{0,80}\b(?:prompt|terminal|console)\b",
    r"\b(?:sitting|waiting|staged|queued|parked)\s+(?:on|at|in)\s+(?:your|the)\s+(?:prompt|terminal|console)\b",
    r"\btyped\s+(?:and|&)\s+(?:sitting|waiting)\b",
    r"\b(?:ya\s+)?(?:escrib[ií]|tecle[eé])\b[^.\n]{0,120}\b(?:terminal|prompt|consola)\b",
))
_RAN_CLAIMS: Tuple["re.Pattern[str]", ...] = tuple(re.compile(p, _FLAGS) for p in (
    r"\bi\s*(?:'?ve|have|just|already)?\s*(?:ran|run|executed|launched|started)\s+(?:the|that|your|it|this|a|an|`|[a-z]:\\|\.\\)",
    r"\bi\s+(?:pressed|hit)\s+enter\b",
))
_SUBORDINATORS = re.compile(r"\b(?:if|once|when|whenever|after|before|unless|until|as\s+soon\s+as|so\s+that)\b", _FLAGS)
_FENCE = re.compile(r"```.*?```", re.DOTALL)
_BEGIN_CODE = re.compile(r"BEGIN-CODE<<<.*?>>>.*?END-CODE", re.DOTALL)
_TAGS = re.compile(r"<[^>]+>")
_SENTENCES = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(answer: Any) -> List[str]:
    text = str(answer or "")
    text = _FENCE.sub(" ", text)
    text = _BEGIN_CODE.sub(" ", text)
    text = _TAGS.sub(" ", text)
    text = text.replace("**", "").replace("`", "'")
    return [s.strip() for s in _SENTENCES.split(text) if s and s.strip()]


def _claims(answer: Any, patterns: Sequence["re.Pattern[str]"]) -> List[str]:
    found: List[str] = []
    for sentence in _sentences(answer):
        if sentence.endswith("?"):
            continue
        for rx in patterns:
            match = rx.search(sentence)
            if not match:
                continue
            if _SUBORDINATORS.search(sentence[:match.start()]):
                continue            # "once I type it ..." is a plan, not a claim
            found.append(sentence[:240])
            break
    return found


_TERMINAL_WORDS = re.compile(r"\b(?:terminals?|terminater|console|consola|powershell|cmd|shell)\b", _FLAGS)


def audit_answer(answer: Any, ledger: Sequence[Evidence], mode: Optional[TutorialMode] = None,
                 bound_tools: Optional[Iterable[str]] = None, user_text: Any = "") -> List[Problem]:
    """Claims in ``answer`` that this request's ledger does not support.  Never raises.

    Only a request that is ABOUT a terminal is audited: a Terminater call was made, the user runs
    the commands (a live tutorial), or the user's own message names a terminal.  "I put the line in
    the config" in an ordinary coding answer is not a claim about a terminal.
    """
    try:
        if not enabled():
            return []
        bound = set(bound_tools) if bound_tools is not None else None
        problems: List[Problem] = []
        terminater_calls = [e for e in ledger if e.tool == TERMINATER_TOOL]
        live = (bool(terminater_calls) or bool(mode is not None and mode.user_runs)
                or bool(_TERMINAL_WORDS.search(str(user_text or "")[:4000])))
        if not live:
            return []

        typed_claims = _claims(answer, _TYPED_CLAIMS)
        if typed_claims and (bound is None or TERMINATER_TOOL in bound):
            if not any(e.typed_proof for e in terminater_calls):
                if not terminater_calls:
                    problems.append(Problem(
                        "claim_typed_no_call", typed_claims[0],
                        "no chat_agent_terminater call was made in this turn, so nothing was typed"))
                else:
                    last = terminater_calls[-1]
                    problems.append(Problem(
                        "claim_typed_unverified", typed_claims[0],
                        f"the terminal call returned status={last.status or 'unknown'}, "
                        f"screen verified={last.verified}, so the line is not proven to be there"))

        ran_claims = _claims(answer, _RAN_CLAIMS)
        if ran_claims and not any(e.ran for e in ledger):
            problems.append(Problem(
                "claim_ran_no_call", ran_claims[0],
                "no command was executed in this turn (no Terminater run with Enter, no command runner)"))
        return problems
    except Exception:  # noqa: BLE001
        return []


def nudge_text(problems: Sequence[Problem]) -> str:
    """The internal correction handed to the model ONCE, before the answer is final."""
    lines = "\n".join(f"- \"{p.claim}\" -> {p.detail}" for p in problems)
    return (
        "[VERIFICATION - internal note, never mention it to the user] Your draft answer states things "
        "that this turn's tool record does NOT support:\n" + lines + "\n"
        "The user will read your answer as FACT, and they act on it. Do ONE of these now: (1) actually do it - "
        "call chat_agent_terminater with typed fields (action='run', terminal=<its terminal_id>, text=<the exact "
        "line>; submit=false when the user presses Enter themselves) and describe ONLY what its result says "
        "(status 'typed' + verified=true is proof the line is there); or "
        "(2) rewrite the answer WITHOUT those claims, saying plainly what is still to be done. Never say a line is "
        "typed, sitting on the prompt, or executed unless a tool result in THIS turn says so."
    )


def banner_text(problems: Sequence[Problem]) -> str:
    """A visible warning appended to an answer whose claims could not be verified."""
    items = "\n".join(f"- {p.claim[:200]} - {p.detail}." for p in problems)
    return (
        "\n\n---\n"
        "⚠️ **Please check before you act - I could not verify part of what I just said.** "
        "I compared my answer with what actually happened in this turn:\n"
        f"{items}\n"
        "Look at the terminal itself before you press anything, and tell me if it differs."
    )
