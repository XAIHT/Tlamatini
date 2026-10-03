"""Tlamatini - the CONTEXT FITTER: every request fits the model it is sent to.

Angela, 2026-10-01: *"make it completely dynamic!!, so if the model is too
small, reduce everything!, but if it is big, include complete context!, and
of course all the one-shot invokes must work using small models!!!"* - and,
the same day: *"when used a small model all the Agents and MCPS activated must
be only System-Metrics, Files-Search, and Current-Time mcp, and ACPX must be
disabled, and all external mcps inactive!"*

WHY.  Tlamatini's complete request - her 87 KB system prompt plus the schemas
of 100+ tools - is about 200 KB, ~59,000 tokens.  A cloud model reads all of
it.  ``qwen2.5:latest`` on a local Ollama reads 16,384: Ollama silently threw
away two thirds of every request and the model answered "what is my CPU
usage?" with the time of day, while the real metrics sat in the part it never
saw.  Nothing was erased - it simply never fitted.

WHAT.  Two modes, decided per request from the model's REAL window
(``context_governor.resolve_ceiling_tokens`` - Ollama's own proof first):

* **FULL** - the complete request fits: it is sent exactly as before, byte for
  byte.  Only the dynamic parts (history, a huge loaded context) are trimmed,
  and only when they alone would overflow the window.
* **COMPACT** - it does not fit.  The tool surface becomes ONLY Current-Time
  (System-Metrics and Files-Search keep feeding live context into the
  question - they are not tools), ACPX is off, External MCPs are paused, and
  the system prompt is rebuilt from Angela's own rules by priority until it
  fits, beside an honest note that tells the model what it does not have.
  History and loaded context are fitted into what is left.

CONTRACTS (do NOT weaken):
  * FULL is byte-identical to the pre-fitter request when everything fits.
  * The user's explicit settings are obeyed: a capability she switched OFF is
    never switched back on; ``context_compact_mode`` = never / always is
    obeyed exactly ("auto" is the default).
  * Never silently: every fit is logged as one ``--- [CONTEXT-FIT]`` line and
    the verdict reaches the page (``context_governor.set_capacity``).
  * FAIL OPEN: any error returns the input unchanged.
  * Standard library only; imports nothing from ``agent.*`` except the
    governor (itself stdlib-only), so it behaves the same frozen and from
    source and can be unit-tested without Django.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import context_governor as cg

__all__ = [
    "MODE_FULL",
    "MODE_COMPACT",
    "COMPACT_TOOL_NAMES",
    "COMPACT_SIDECARS",
    "Window",
    "resolve_window",
    "answer_reserve_tokens",
    "compact_mode_setting",
    "split_prompt",
    "compact_prompt",
    "compact_tool_rule",
    "compact_answer_rules",
    "unwrap_display_tables",
    "fit_history",
    "fit_input",
    "message_chars",
    "ContextWindowExceeded",
]

MODE_FULL = "full"
MODE_COMPACT = "compact"

# The tool a compact request binds BEFORE the Compact-mode switch has
# rewritten the Configure rows: "Current-Time" (get_current_time).  Once the
# switch is ON (agent/compact_mode.py, 2026-10-02) a compact request binds
# EXACTLY the tools the user ticked - Current-Time to start with, then whatever
# she switches on one by one.  System-Metrics and Files-Search are context
# SIDECARS - they put live data into the question before the model is called.
COMPACT_TOOL_NAMES = frozenset({"get_current_time"})
COMPACT_SIDECARS = ("System-Metrics", "Files-Search")

# A small model still needs room to ANSWER: Ollama's window holds the prompt
# AND the generated tokens.  A fifth of the window, never less than 768 and
# never more than 8,192 tokens.
_RESERVE_RATIO = 0.20
_RESERVE_MIN = 768
_RESERVE_MAX = 8192

_OMIT_MARK = "\n[... {n} characters omitted so this request fits the model's context window ...]\n"


class ContextWindowExceeded(Exception):
    """Raised by the executor when Ollama CUT the first request of a turn.

    Nothing has run yet (no tool call was executed from a truncated answer),
    so the caller can re-fit the request to the window Ollama just proved and
    send it again.
    """

    def __init__(self, window: int, model: str = "") -> None:
        super().__init__(f"Ollama read only {window} tokens of the request to {model or 'the model'}")
        self.window = int(window or 0)
        self.model = str(model or "")


# ── The window ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Window:
    tokens: int
    source: str
    cloud: bool
    chars_per_token: float
    reserve_tokens: int

    @property
    def usable_tokens(self) -> int:
        return max(256, self.tokens - self.reserve_tokens)

    @property
    def usable_chars(self) -> int:
        return int(self.usable_tokens * self.chars_per_token)


def answer_reserve_tokens(window_tokens: int) -> int:
    try:
        return int(min(_RESERVE_MAX, max(_RESERVE_MIN, int(window_tokens) * _RESERVE_RATIO)))
    except Exception:  # noqa: BLE001
        return _RESERVE_MIN


def resolve_window(config: Any, model: str, base_url: str = "") -> Window:
    """The window this request must fit, from the governor's ONE resolver."""
    try:
        tokens, source = cg.resolve_ceiling_tokens(config, model=model, base_url=base_url)
        tokens = int(tokens or cg.FALLBACK_CEILING_TOKENS)
    except Exception:  # noqa: BLE001
        tokens, source = cg.FALLBACK_CEILING_TOKENS, "fallback"
    return Window(
        tokens=tokens,
        source=str(source),
        cloud=bool(cg.is_cloud_model(model)),
        chars_per_token=cg.fit_chars_per_token(model, base_url),
        reserve_tokens=answer_reserve_tokens(tokens),
    )


def compact_mode_setting(config: Any) -> str:
    """``auto`` (default) | ``always`` | ``never`` - an explicit value is obeyed."""
    try:
        value = str((config or {}).get("context_compact_mode", "auto") or "auto").strip().lower()
    except Exception:  # noqa: BLE001
        return "auto"
    return value if value in {"auto", "always", "never"} else "auto"


# ── Measuring messages ──────────────────────────────────────────────────────
def _content_of(message: Any) -> str:
    try:
        if isinstance(message, dict):
            return str(message.get("content", "") or "")
        content = getattr(message, "content", message)
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, dict):
                    parts.append(str(item.get("text", "") or ""))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content or "")
    except Exception:  # noqa: BLE001
        return ""


def message_chars(messages: Iterable[Any]) -> int:
    """Characters a model reads from these messages (plus a small per-message
    envelope, the role markers every chat template adds)."""
    total = 0
    try:
        for message in messages or []:
            total += len(_content_of(message)) + 16
            calls = getattr(message, "tool_calls", None)
            if calls:
                total += len(str(calls))
    except Exception:  # noqa: BLE001
        pass
    return total


def _with_content(message: Any, text: str) -> Any:
    """A copy of ``message`` carrying ``text``.  Never mutates the original."""
    try:
        if isinstance(message, dict):
            out = dict(message)
            out["content"] = text
            return out
        if hasattr(message, "model_copy"):
            return message.model_copy(update={"content": text})
        if hasattr(message, "copy"):
            return message.copy(update={"content": text})
    except Exception:  # noqa: BLE001
        pass
    return message


def _clip(text: str, limit: int) -> str:
    """Keep the head and the tail of ``text`` within ``limit`` characters."""
    text = str(text or "")
    if limit <= 0:
        return ""
    if len(text) <= limit:
        return text
    mark = _OMIT_MARK.format(n=len(text) - limit)
    room = max(0, limit - len(mark))
    head = int(room * 0.7)
    tail = room - head
    return text[:head] + mark + (text[-tail:] if tail > 0 else "")


# ── Fitting the history ─────────────────────────────────────────────────────
def fit_history(
    history: Sequence[Any],
    budget_chars: int,
    *,
    input_text: str = "",
    max_messages: int = 8,
    per_message_cap: int = 0,
) -> Tuple[List[Any], Dict[str, Any]]:
    """Keep the NEWEST messages that fit ``budget_chars``; clip long ones.

    The last message is often the current question itself (the chat saves it
    before the history is loaded); the executor drops that duplicate, so it is
    kept untouched and costs nothing here.
    """
    items = list(history or [])[-max(0, int(max_messages)):] if max_messages else []
    info = {"history_total": len(list(history or [])), "history_kept": 0, "history_clipped": 0}
    try:
        question = str(input_text or "").strip()
        tail_is_question = bool(items) and bool(question) and (
            question.endswith(_content_of(items[-1]).strip()) and _content_of(items[-1]).strip() != ""
        )
        kept_rev: List[Any] = []
        used = 0
        start = len(items) - 1
        if tail_is_question:
            kept_rev.append(items[-1])
            start -= 1
        for idx in range(start, -1, -1):
            msg = items[idx]
            text = _content_of(msg)
            cap = per_message_cap if per_message_cap > 0 else len(text)
            if len(text) > cap:
                text = _clip(text, cap)
                msg = _with_content(msg, text)
                info["history_clipped"] += 1
            cost = len(text) + 16
            if used + cost > budget_chars:
                room = budget_chars - used - 16
                if room >= 400:
                    msg = _with_content(msg, _clip(text, room))
                    kept_rev.append(msg)
                    info["history_clipped"] += 1
                break
            kept_rev.append(msg)
            used += cost
        kept = list(reversed(kept_rev))
        info["history_kept"] = len(kept) - (1 if tail_is_question else 0)
        return kept, info
    except Exception:  # noqa: BLE001
        return list(history or []), info


# ── Fitting the input (question + its attached context) ─────────────────────
_INPUT_BLOCKS: Tuple[Tuple[str, str], ...] = tuple(cg.CONTEXT_BLOCKS) + (
    ("Web Context: ", "\n\nSources:"),
    ("Web Context: ", "\n\n"),
    ("Files Context (file system search results):\n", "\n\nUser Question: "),
)


def _shrink_block(text: str, opener: str, closer: str, excess: int) -> Tuple[str, int]:
    start = text.find(opener)
    if start < 0:
        return text, 0
    body_start = start + len(opener)
    end = text.find(closer, body_start)
    if end < 0:
        return text, 0
    body = text[body_start:end]
    if len(body) < 600:
        return text, 0
    target = max(300, len(body) - excess)
    clipped = _clip(body, target)
    saved = len(body) - len(clipped)
    return text[:body_start] + clipped + text[end:], saved


def fit_input(text: str, budget_chars: int) -> Tuple[str, Dict[str, Any]]:
    """Fit the user's message (with its system / file / loaded / web context)
    into ``budget_chars``.  The QUESTION is the last thing ever cut: the
    attached context blocks shrink first, the question only if it alone is
    larger than the whole budget."""
    original = str(text or "")
    info = {"input_chars": len(original), "input_fitted_chars": len(original), "input_clipped": False}
    try:
        if budget_chars <= 0 or len(original) <= budget_chars:
            return original, info
        out = original
        for opener, closer in _INPUT_BLOCKS:
            excess = len(out) - budget_chars
            if excess <= 0:
                break
            out, _saved = _shrink_block(out, opener, closer, excess)
        if len(out) > budget_chars:
            out = _clip(out, budget_chars)
            # The question sits at the END; keep it whole when it is short.
            tail = original[-min(len(original), 1200):]
            if not out.endswith(tail) and len(tail) < budget_chars // 2:
                out = _clip(out, budget_chars - len(tail)) + tail
        info.update(input_fitted_chars=len(out), input_clipped=True)
        return out, info
    except Exception:  # noqa: BLE001
        return original, info


# ── The system prompt, rebuilt from Angela's own rules by priority ──────────
@dataclass(frozen=True)
class Section:
    kind: str           # head | general | prime | quickmap | envelope | rule | tail
    title: str
    text: str


_RULE_RE = re.compile(r"^(\d+[a-z]?)\) ")
_SENTINEL_BLOCK_RE = re.compile(r"<!--([A-Z_]+?)_BEGIN-->.*?<!--\1_END-->\n?", re.DOTALL)
_SENTINEL_MARK_RE = re.compile(r"<!--[A-Z_]+_(?:BEGIN|END)-->\n?")
_SELF_KNOWLEDGE_RE = re.compile(r"<self_knowledge>.*?</self_knowledge>\n?", re.DOTALL)
_PLACEHOLDER_BLOCK_RE = re.compile(
    r"<(system_context|files_context|context)>\s*\{\1\}\s*</\1>\n?")


def split_prompt(prompt: str) -> List[Section]:
    """Cut prompt.pmt into its sections: the head (identity + context
    placeholders), the general banner, the Prime Directive, the Quick Map,
    the Output Envelope and every numbered rule."""
    lines = str(prompt or "").split("\n")
    marks: List[Tuple[int, str, str]] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("**General Rules for user prompts"):
            marks.append((i, "general", stripped))
        elif stripped.startswith("**") and "PRIME DIRECTIVE" in stripped and "READ THIS" in stripped:
            marks.append((i, "prime", stripped))
        elif stripped.startswith("**") and "QUICK MAP" in stripped:
            marks.append((i, "quickmap", stripped))
        elif stripped.startswith("**") and "OUTPUT ENVELOPE" in stripped:
            marks.append((i, "envelope", stripped))
        elif _RULE_RE.match(line):
            marks.append((i, "rule", stripped))
    if not marks:
        return [Section("head", "", str(prompt or ""))]
    sections = [Section("head", "", "\n".join(lines[:marks[0][0]]))]
    for (start, kind, title), nxt in zip(marks, marks[1:] + [(len(lines), "", "")]):
        sections.append(Section(kind, title, "\n".join(lines[start:nxt[0]])))
    return sections


# Priority of each rule in COMPACT mode, matched on its title.  0 = always
# kept; higher = dropped earlier when the budget is tight.  ``None`` = about a
# capability a compact request does not have (agents, ACPX, External MCPs,
# voice...), so it would only confuse a small model - dropped always.
_RULE_PRIORITY: Tuple[Tuple[str, Optional[int]], ...] = (
    ("referenced rephrase", 0),
    ("system context rule", 0),
    ("files context rule", 0),
    ("end-response", 0),
    ("conflict resolution", 0),
    ("code generation", 1),
    ("tables rule", 1),
    ("answer quality", 1),
    ("context usage", 2),
    ("safety and hygiene", 2),
    ("diagrams", 3),
    ("whole-application awareness", 4),
    ("temporary files", 5),
    ("self-healing", 5),
    ("html styling", 6),
    ("model selection", None),
    ("diagnostic-finding", None),
    ("tool-usage", None),
    ("acpx", None),
    ("template / project", None),
    ("talker", None),
    ("netspeed", None),
    ("googler", None),
    ("voice command", None),
    ("external mcp", None),
    ("memory external", None),
)
_KIND_PRIORITY = {"general": 0, "envelope": 0, "prime": 2, "quickmap": None}


def _priority(section: Section) -> Optional[int]:
    if section.kind != "rule":
        return _KIND_PRIORITY.get(section.kind, 3)
    title = section.title.lower()
    for needle, prio in _RULE_PRIORITY:
        if needle in title:
            return prio
    return 4


def _compact_head(head: str) -> str:
    """The identity part of the head, without what a compact request lacks:
    the self-knowledge dump (tens of KB), and paragraphs about agents."""
    text = _SELF_KNOWLEDGE_RE.sub("", head)
    kept: List[str] = []
    for para in re.split(r"\n\s*\n", text):
        if "chat_agent_" in para or "TlamatiniSourceCode" in para or "Tlamatini.md" in para:
            # The self-knowledge bullets / agent-specific notes: drop just
            # those lines, keep the rest of the paragraph.
            lines = [ln for ln in para.split("\n")
                     if "chat_agent_" not in ln and "TlamatiniSourceCode" not in ln
                     and "Tlamatini.md" not in ln]
            para = "\n".join(lines)
        if para.strip():
            kept.append(para.strip("\n"))
    return "\n\n".join(kept)


MICRO_PROMPT = (
    "You are **Tlamatini** (\"one who knows\"), the AI assistant created by Angela "
    "López Mendoza; you are feminine (she/her). Answer accurately and concisely in the "
    "user's language. When the message carries a \"System Context\" (live CPU / memory / "
    "disk metrics) or a \"Files Context\", those are REAL, current values - use them "
    "directly. Put code ONLY inside BEGIN-CODE<<<filename.ext>>> ... END-CODE (never "
    "triple backticks). Tables are HTML only, body cells light background with dark "
    "text. End EVERY answer with a final line that is exactly END-RESPONSE."
)


def _placeholders_block() -> str:
    return ("<system_context>\n{system_context}\n</system_context>\n\n"
            "<files_context>\n{files_context}\n</files_context>\n\n"
            "<context>\n{context}\n</context>")


def compact_prompt(
    prompt: str,
    budget_chars: int,
    *,
    keep_placeholders: bool = False,
    context_loaded: bool = False,
) -> Tuple[str, Dict[str, Any]]:
    """Rebuild ``prompt`` (prompt.pmt, already loaded) to at most
    ``budget_chars``, keeping Angela's rules by priority and their order.

    ``keep_placeholders=True`` is for the tool-less chains whose prompt is a
    template (``{system_context}`` / ``{files_context}`` / ``{context}`` must
    survive, braces stay escaped).  ``False`` is for the agent, which gets
    the context inside the question: placeholders are removed and doubled
    template braces are turned back into the literal braces they stand for.
    """
    full = str(prompt or "")
    info: Dict[str, Any] = {"prompt_full_chars": len(full), "prompt_profile": "compact",
                            "sections_total": 0, "sections_kept": 0, "dropped": []}
    try:
        text = _SENTINEL_BLOCK_RE.sub("", full)          # ACPX / Templates / Talker ...
        text = _SENTINEL_MARK_RE.sub("", text)
        sections = split_prompt(text)
        head = _compact_head(sections[0].text) if sections else ""
        if not keep_placeholders:
            head = _PLACEHOLDER_BLOCK_RE.sub("", head)
        body = [(i, s, _priority(s)) for i, s in enumerate(sections[1:], start=1)]
        if context_loaded:
            # The user loaded a project: Rule 5 (the loaded-context-priority
            # rule) decides what "the project" means - never drop it then.
            body = [(i, s, 0 if (p is not None and "context usage" in s.title.lower()) else p)
                    for i, s, p in body]
        info["sections_total"] = len(body)
        chosen = {i for i, _s, p in body if p == 0}
        used = len(head) + sum(len(s.text) + 2 for i, s, _p in body if i in chosen)
        for level in range(1, 7):
            for i, s, p in body:
                if p == level and used + len(s.text) + 2 <= budget_chars:
                    chosen.add(i)
                    used += len(s.text) + 2
        info["dropped"] = [s.title[:60] for i, s, _p in body if i not in chosen]
        out = "\n\n".join([head.rstrip()] + [sections[i].text.strip("\n") for i in sorted(chosen)])
        if len(out) > budget_chars:
            # Even Angela's always-kept core does not fit: the micro prompt -
            # who she is, the live context, the four output rules.
            out = MICRO_PROMPT
            if keep_placeholders:
                out = MICRO_PROMPT.replace("{", "{{").replace("}", "}}") + "\n\n" + _placeholders_block()
            info.update(prompt_profile="micro", dropped=["(all rules; micro prompt)"])
            chosen = set()
        if not keep_placeholders:
            out = out.replace("{{", "{").replace("}}", "}")
        out = re.sub(r"\n{3,}", "\n\n", out).strip() + "\n"
        info.update(sections_kept=len(chosen), prompt_chars=len(out))
        return out, info
    except Exception:  # noqa: BLE001
        info.update(prompt_profile="unchanged (fitter error)", prompt_chars=len(full))
        return full, info


def compact_tool_rule(tool_names: Sequence[str], *, model: str = "",
                      window_tokens: int = 0, strict: bool = True) -> str:
    """The honest note a compact request carries instead of Rule 11's
    31,000-character tool manual.

    It is the LAST thing in the system prompt (closest to the conversation)
    and it is a short numbered list on purpose: a 7B model follows seven
    plain rules; it does not reliably follow the same rules spread across
    28 KB of prose.  Every rule here answers a failure measured on
    qwen2.5:latest in the visible test (2026-10-01):

    * it re-answered the previous question before the new one  -> rule 1;
    * it wrapped a table in ``` fences, which Tlamatini shows as source
      code, so the user saw tags instead of a table               -> rule 2;
    * asked to create a file with no file tools, it answered with an
      invented "use absolute paths" lecture instead of "I can't" -> rule 6.

    Since 2026-10-02 the tools listed in rule 5 are the ones the USER ticked
    in Compact mode, so rule 6 names what is missing instead of a fixed list.
    ``strict=False`` is a large model the user put in Compact mode herself.
    """
    names = [str(n) for n in tool_names if n]
    listed = ", ".join(f"`{n}`" for n in names) if names else "none"
    window = f" ({window_tokens:,} tokens)" if window_tokens else ""
    who = f"`{model}`" if model else "the current model"
    plain = model or "the current model"
    if strict:
        head = (who + " has a small context window" + window + ", so Tlamatini is running "
                "with a reduced surface.")
        because = "because " + plain + " is a small model"
    else:
        head = "Compact mode is switched on, so Tlamatini is running with a reduced surface."
        because = "because Compact mode is switched on"
    return (
        "**COMPACT MODE** - " + head + " Follow these rules exactly:\n"
        "1. Answer ONLY the user's newest message. Earlier messages in this conversation "
        "were already answered - never answer them again.\n"
        "2. To SHOW a table, write the raw HTML <table> element directly in your answer "
        "(light background, dark text in the cells). Never put a table inside ``` fences or "
        "BEGIN-CODE and never write a label such as \"html:\" before it - fenced HTML is "
        "shown to the user as source code, not as a table. Use BEGIN-CODE only when the "
        "user asks for a file or for source code.\n"
        "3. Code goes ONLY inside BEGIN-CODE<<<filename.ext>>> ... END-CODE, never in "
        "triple backticks.\n"
        "4. Live system metrics and file-search results, when relevant, are ALREADY inside "
        "the user's message as \"System Context\" / \"Files Context\": they are real, current "
        "values - answer from them directly, without calling a tool.\n"
        "5. Tools you may call now: " + listed + ". Never invent a tool and never claim you "
        "ran something you did not run.\n"
        "6. Only the tools listed in rule 5 are switched on. Creating, editing, moving or "
        "deleting files, running commands or scripts, browsing the web, launching agents, "
        "ACPX and External MCPs work ONLY through a listed tool. If the user asks for "
        "something no listed tool can do, begin your answer (in the user's language) with: "
        "\"I can't do that right now - Tlamatini is in Compact mode " + because + ".\" Then "
        "say that ticking the needed agent in Config > Configure Agents (the CONTEXT-WINDOW "
        "gauge shows whether it still fits) or choosing a larger model in Config > Models "
        "brings it back. Do not ask for paths and do not offer to do it.\n"
        "7. End every answer with a final line that is exactly END-RESPONSE."
    )


#: A ```html (or bare ```) fence in a model's answer.
_FENCED_HTML_RE = re.compile(
    r"```[ \t]*(?:html?)?[ \t]*\r?\n(?P<body>.*?)\r?\n?[ \t]*```", re.S | re.I)
#: Markup that must never be lifted out of a fence: anything beyond a table.
_UNSAFE_MARKUP_RE = re.compile(
    r"<\s*/?\s*(?:script|style|iframe|frame|object|embed|html|head|body|link|meta|base|form|"
    r"input|button|textarea|select|svg|math|img|video|audio)\b|\son[a-z]+\s*=|javascript:",
    re.I)
#: The user asked for the SOURCE (code, a file, a page) - then the fence is right.
_ASKS_FOR_SOURCE_RE = re.compile(
    r"\b(?:code|source|markup|snippet|file|page|template|raw|c[oó]digo|fuente|archivo|"
    r"p[aá]gina|plantilla)\b", re.I)
#: A Tlamatini file block named *.html / *.htm (it becomes a "Load in canvas"
#: link, so the user sees a link instead of the table they asked to see).
_HTML_FILE_BLOCK_RE = re.compile(
    r"BEGIN-CODE<<<[-\w./\\]+\.html?>>>[ \t]*\r?\n?(?P<body>.*?)\r?\n?[ \t]*END-CODE", re.S | re.I)
#: An HTML comment - never content a user asked to see.
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
#: The ```html fence a model sometimes puts INSIDE that file block.
_INNER_FENCE_RE = re.compile(r"^```[ \t]*(?:html?)?[ \t]*\r?\n?(?P<inner>.*?)\r?\n?[ \t]*```$",
                             re.S | re.I)


def unwrap_display_tables(answer: str, question: str = "") -> Tuple[str, int]:
    """Show a table the user asked to SEE as a table (Compact mode only).

    Tlamatini renders a raw HTML ``<table>`` in an answer, but shows anything
    inside a ``` fence as source code.  A small model wraps tables in
    ```html fences however plainly it is told not to (qwen2.5:latest did it
    twice in the visible test, rule 2 of the Compact note included), so the
    user saw tags instead of a table.

    The same model, told not to fence, then put the table in a file block
    (``BEGIN-CODE<<<planets_diameters.html>>>``), which Tlamatini turns into
    a "Load in canvas" link - the table still never appeared.  Both forms are
    handled.

    Only a block whose WHOLE body is one table (optionally inside one
    ``<div>``) is unwrapped, and only when the question did not ask for code,
    a file or a page.  Anything that is not plain table markup - scripts,
    style sheets, forms, images, event handlers - stays as it was.  Returns
    ``(answer, tables_unwrapped)``; never raises.
    """
    try:
        text = str(answer or "")
        if "<table" not in text.lower() or ("```" not in text and "BEGIN-CODE" not in text.upper()):
            return text, 0
        tail = str(question or "")[-600:]
        if _ASKS_FOR_SOURCE_RE.search(tail):
            return text, 0
        count = 0

        def _lift(match: "re.Match[str]") -> str:
            nonlocal count
            body = match.group("body").strip()
            inner = _INNER_FENCE_RE.match(body)
            if inner:
                body = inner.group("inner").strip()
            # qwen2.5 put "<!-- END-RESPONSE -->" inside the fence, after the
            # table: comments are not content - drop them, keep the sentinel.
            comments = _HTML_COMMENT_RE.findall(body)
            body = _HTML_COMMENT_RE.sub("", body).strip()
            sentinel = "\nEND-RESPONSE" if any("END-RESPONSE" in c for c in comments) else ""
            low = body.lower()
            starts = low.startswith("<table") or (low.startswith("<div") and "<table" in low)
            ends = low.endswith("</table>") or low.endswith("</div>")
            if not (starts and ends) or "</table>" not in low or _UNSAFE_MARKUP_RE.search(body):
                return match.group(0)
            count += 1
            return "\n" + body + sentinel + "\n"

        # File blocks first: a fence INSIDE one is part of that block.
        text = _HTML_FILE_BLOCK_RE.sub(_lift, text)
        return _FENCED_HTML_RE.sub(_lift, text), count
    except Exception:  # noqa: BLE001 - never break an answer
        return str(answer or ""), 0


def compact_answer_rules(*, model: str = "", window_tokens: int = 0) -> str:
    """The same rules for a TOOL-LESS compact chain (no tools at all).

    Safe inside a prompt TEMPLATE: it contains no ``{`` / ``}``.
    """
    return compact_tool_rule((), model=model, window_tokens=window_tokens)


@dataclass
class FitReport:
    """What one fit decided - logged, and sent to the page as ``capacity``."""

    mode: str = MODE_FULL
    model: str = ""
    window_tokens: int = 0
    window_source: str = ""
    reserve_tokens: int = 0
    chars_per_token: float = 0.0
    full_tokens_estimate: int = 0
    fitted_tokens_estimate: int = 0
    tools_total: int = 0
    tools_kept: List[str] = field(default_factory=list)
    acpx_requested: bool = False
    external_mcps_paused: List[str] = field(default_factory=list)
    agents_paused: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    setting: str = "auto"
    # The Compact-mode switch (agent/compact_mode.py, 2026-10-02).
    compact_active: bool = False
    strict: bool = False
    everything_tokens: int = 0
    acpx_bound: bool = False
    toggles_version: int = 0

    def as_capacity(self) -> Dict[str, Any]:
        return {
            "compact_active": bool(self.compact_active),
            "strict": bool(self.strict),
            "locked": bool(self.strict),
            "everything_tokens": int(self.everything_tokens),
            "toggles_version": int(self.toggles_version),
            "mode": self.mode,
            "model": self.model,
            "window_tokens": int(self.window_tokens),
            "window_source": self.window_source,
            "reserve_tokens": int(self.reserve_tokens),
            "full_tokens_estimate": int(self.full_tokens_estimate),
            "fitted_tokens_estimate": int(self.fitted_tokens_estimate),
            "tools_total": int(self.tools_total),
            "tools_kept": list(self.tools_kept),
            "tools_kept_count": int(self.details.get("tools_kept_count", len(self.tools_kept)) or 0),
            "sidecars": list(COMPACT_SIDECARS),
            "acpx_off": self.mode == MODE_COMPACT and not self.acpx_bound,
            "acpx_requested": bool(self.acpx_requested),
            "external_mcps_paused": list(self.external_mcps_paused),
            "agents_paused": int(self.agents_paused),
            "prompt_profile": self.details.get("prompt_profile", "full"),
            "prompt_chars": int(self.details.get("prompt_chars", 0) or 0),
            "prompt_full_chars": int(self.details.get("prompt_full_chars", 0) or 0),
            "sections_kept": int(self.details.get("sections_kept", 0) or 0),
            "sections_total": int(self.details.get("sections_total", 0) or 0),
            "history_kept": int(self.details.get("history_kept", 0) or 0),
            "history_total": int(self.details.get("history_total", 0) or 0),
            "input_clipped": bool(self.details.get("input_clipped", False)),
            "reason": self.reason,
            "setting": self.setting,
        }

    def log_line(self) -> str:
        d = self.details
        if self.mode == MODE_FULL:
            what = (f"FULL - complete request (~{self.full_tokens_estimate:,} tokens est.) fits "
                    f"{self.window_tokens:,} ({self.window_source})")
        else:
            why = (f"everything activated (~{self.everything_tokens:,} tokens est.) cannot fit "
                   f"{self.window_tokens:,} ({self.window_source})" if self.strict
                   else "the Compact-mode switch is ON")
            what = (f"COMPACT - {why}; sending "
                    f"~{self.fitted_tokens_estimate:,}: prompt {d.get('prompt_profile')} "
                    f"{d.get('prompt_chars', 0):,}/{d.get('prompt_full_chars', 0):,} chars "
                    f"({d.get('sections_kept', 0)}/{d.get('sections_total', 0)} sections), tools "
                    f"{self.tools_kept or '[]'} of {self.tools_total}, "
                    f"ACPX {'on' if self.acpx_bound else 'off'}, "
                    f"{len(self.external_mcps_paused)} External MCP(s) paused")
        extra = []
        if d.get("history_total") is not None and d.get("history_kept", d.get("history_total")) != d.get("history_total"):
            extra.append(f"history {d.get('history_kept')}/{d.get('history_total')}")
        if d.get("input_clipped"):
            extra.append(f"input {d.get('input_fitted_chars'):,}/{d.get('input_chars'):,} chars")
        tail = (" | " + ", ".join(extra)) if extra else ""
        return f"--- [CONTEXT-FIT] {self.model}: {what}{tail} | setting={self.setting}"
