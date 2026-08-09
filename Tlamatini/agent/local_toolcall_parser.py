"""Recover a tool call that a LOCAL model emitted as PLAIN TEXT.

WHY THIS EXISTS
---------------
Cloud models (``glm-5.2:cloud`` and friends) return tool calls in the structured
``tool_calls`` field, which LangChain/Ollama hand to the executor directly. Many
SMALL LOCAL models (qwen2.5-coder:7b, llama3.x:8b, mistral:7b ...) instead write
the call as ORDINARY TEXT in the message content::

    {"name": "current_time", "arguments": {}}

``MultiTurnToolAgentExecutor`` only ever read ``response.tool_calls``, so it saw
"no tool calls", treated that JSON as the model's FINAL ANSWER and shipped it
verbatim to the user. Measured live on 2026-08-08 (``tlamatini.log`` line 2192)::

    --- UnifiedAgentChain: output value: '{"name": "current_time", "arguments": {}}'

The user asked "What is the current time now?" and Tlamatini answered with raw
JSON. The model was not stupid — it picked the right tool — the RUNTIME dropped
the call on the floor. That is what this module repairs.

CONTRACT (do NOT weaken)
------------------------
* **ONLY runs when ``tool_calls`` is EMPTY.** A cloud model always populates that
  field, so this code path is never even reached for one — that is the primary
  reason the fix is cloud-safe.
* **WHOLE-CONTENT RULE.** The content must consist ENTIRELY of the call (after
  stripping a code fence / ``<tool_call>`` wrapper). Content that merely
  *contains* JSON somewhere is prose and is LEFT ALONE. This is what stops a
  legitimate answer — "here is how you would call that tool: {...}" — from being
  executed instead of shown.
* **NAME MUST BE BOUND.** The parsed name must match a tool actually bound for
  this request. An unknown name is prose, not a call.
* **FAIL-OPEN, ALWAYS.** Every error path returns ``[]`` meaning "not a tool
  call, treat it as an answer". Nothing here may raise into the executor: a
  parser that can break the chat loop is worse than the bug it fixes.
* **STDLIB ONLY**, and imports nothing from ``agent.*`` — so it can never create
  an import cycle and behaves identically frozen and from source.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, Iterable, List, Optional

__all__ = [
    "extract_text_tool_calls",
    "describe_toolcall_shape",
    "is_recovery_eligible_model",
    "looks_like_tool_call_attempt",
    "suggest_tool_names",
]

# ``<tool_call> ... </tool_call>`` is Qwen's / Hermes' native emission format and
# is what qwen2.5-coder falls back to when the server-side template does not
# capture it. Also accept the ``<|tool_call|>`` sentinel some builds use.
_TAG_PATTERNS = (
    re.compile(r"<tool_call>\s*(?P<body>.+?)\s*</tool_call>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<\|tool_call\|>\s*(?P<body>.+?)\s*(?:<\|/tool_call\|>|$)", re.DOTALL | re.IGNORECASE),
    re.compile(r"<function_call>\s*(?P<body>.+?)\s*</function_call>", re.DOTALL | re.IGNORECASE),
)

# ```json { ... } ```   /   ``` { ... } ```
_FENCE_PATTERN = re.compile(
    r"^\s*```(?:json|tool_code|python)?\s*(?P<body>.+?)\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)

# Key aliases seen in the wild across local models.
_NAME_KEYS = ("name", "tool", "tool_name", "function", "function_name", "action")
_ARGS_KEYS = ("arguments", "args", "parameters", "params", "input", "action_input")


def _strip_wrappers(content: str) -> List[str]:
    """Return candidate JSON bodies extracted from ``content``.

    Each candidate is a string that, for the whole-content rule to hold, must
    itself be the entire meaningful payload.
    """
    text = (content or "").strip()
    if not text:
        return []

    candidates: List[str] = []

    # 1) Explicit tool-call tags anywhere in the content. A tagged call is an
    #    unambiguous statement of intent, so the surrounding prose (usually the
    #    model's reasoning) does not disqualify it.
    for pattern in _TAG_PATTERNS:
        for match in pattern.finditer(text):
            body = (match.group("body") or "").strip()
            if body:
                candidates.append(body)
    if candidates:
        return candidates

    # 2) A fenced block that is the ENTIRE content.
    fence = _FENCE_PATTERN.match(text)
    if fence:
        body = (fence.group("body") or "").strip()
        if body:
            return [body]

    # 3) The bare content itself — only if it looks like a single JSON object.
    if text.startswith("{") and text.endswith("}"):
        return [text]

    return []


def _coerce_args(raw: Any) -> Optional[Dict[str, Any]]:
    """Normalise an arguments payload to a dict, or ``None`` if unusable."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    # Double-encoded arguments: {"arguments": "{\"path\": \"x\"}"}
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except (ValueError, TypeError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _first_key(payload: Dict[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


# Prefixes local models routinely drop when naming a tool from memory.
#
# ⚠️ "chat_agent_" IS DELIBERATELY ABSENT (review finding, 2026-08-08).
# With it, prose containing {"name": "deleter"} resolved to chat_agent_deleter
# and would have DELETED FILES; {"name": "whatsapper"} would have MESSAGED A
# REAL PERSON. Those agents are not Ask-Execs gated, so nothing downstream would
# have stopped it. A wrapped agent must be named IN FULL to be recovered.
_DROPPABLE_PREFIXES = ("get_",)


def _resolve_name(raw: str, valid: set) -> Optional[str]:
    """Map a model-written tool name onto a REAL bound tool name, or None.

    Small local models name tools approximately: they wrote ``current_time``
    when the bound tool is ``get_current_time`` (measured live 2026-08-08), and
    they vary the case. Demanding a byte-exact match therefore rejected a call
    the model got RIGHT in substance, and the raw JSON was shown to the user.

    Resolution is deliberately conservative and ORDERED, and every fuzzy step
    requires a UNIQUE winner — an ambiguous name resolves to None (treated as
    prose) rather than guessing which tool to run.
    """
    if not raw:
        return None

    # 1) Exact — the overwhelmingly common case.
    if raw in valid:
        return raw

    # 2) Case-insensitive exact.
    lowered = raw.lower()
    ci = [n for n in valid if n.lower() == lowered]
    if len(ci) == 1:
        return ci[0]

    # 3) The model dropped a known prefix: current_time -> get_current_time.
    prefixed = [n for n in valid
                if any(n.lower() == p + lowered for p in _DROPPABLE_PREFIXES)]
    if len(prefixed) == 1:
        return prefixed[0]

    # 4) The model ADDED a prefix the real tool does not have.
    for prefix in _DROPPABLE_PREFIXES:
        if lowered.startswith(prefix):
            stripped = lowered[len(prefix):]
            hit = [n for n in valid if n.lower() == stripped]
            if len(hit) == 1:
                return hit[0]

    # 5) Separator drift only (current-time / currenttime -> get_current_time).
    def _norm(value: str) -> str:
        return "".join(ch for ch in value.lower() if ch.isalnum())

    target = _norm(raw)
    loose = [n for n in valid
             if _norm(n) == target
             or any(_norm(n) == _norm(p) + target for p in _DROPPABLE_PREFIXES)]
    if len(loose) == 1:
        return loose[0]

    return None


def _parse_one(body: str, valid_tool_names: set) -> Optional[Dict[str, Any]]:
    """Parse ONE candidate body into a LangChain-shaped tool call."""
    try:
        payload = json.loads(body)
    except (ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None

    # Some models nest the call: {"tool_call": {"name": ..., "arguments": ...}}
    for wrapper in ("tool_call", "function_call", "function"):
        inner = payload.get(wrapper)
        if isinstance(inner, dict) and _first_key(inner, _NAME_KEYS) is not None:
            payload = inner
            break

    name = _first_key(payload, _NAME_KEYS)
    if not isinstance(name, str):
        return None
    # THE decisive guard: the name must resolve to a REAL bound tool. An
    # unresolvable name means the content was prose, not a call.
    name = _resolve_name(name.strip(), valid_tool_names)
    if not name:
        return None

    args = _coerce_args(_first_key(payload, _ARGS_KEYS))
    if args is None:
        return None

    return {
        "name": name,
        "args": args,
        "id": f"local_text_{uuid.uuid4().hex[:12]}",
        "type": "tool_call",
    }


def is_recovery_eligible_model(model_name: Any) -> bool:
    """Should text-tool-call recovery run for this model at all?

    ⚠️ THE CLOUD GATE — do NOT remove (added 2026-08-08 after review).
    The original design claimed the recovery "can never be reached for a cloud
    model because cloud always populates tool_calls". THAT WAS WRONG: the hook
    fires on ``if not tool_calls:``, which is the SAME condition the executor
    uses to decide the model has FINISHED and is answering. So a cloud model
    enters the parser on essentially every request, and a false positive would
    DISCARD its answer and run a tool instead.

    Cloud models emit proper structured tool calls, so they never NEED the
    recovery. Gating on the model name makes cloud behaviour byte-identical to
    before the fix — the property Angela required.
    """
    try:
        name = (model_name or "").strip().lower()
        if not name:
            return False          # unknown model => do NOT take the risk
        return ":cloud" not in name and not name.endswith("-cloud")
    except Exception:  # pragma: no cover - totality guard
        return False


def extract_text_tool_calls(content: Any, valid_tool_names: Iterable[str],
                            model_name: Any = None) -> List[Dict[str, Any]]:
    """Recover tool calls a local model wrote as text. NEVER raises.

    Returns ``[]`` — meaning "this is a normal answer, leave it alone" — for
    anything that is not unambiguously a call to a BOUND tool.

    ``model_name`` engages the CLOUD GATE above. It is optional ONLY so the unit
    tests can exercise the parser directly; every production call site passes it.
    """
    try:
        if not content or not isinstance(content, str):
            return []
        if model_name is not None and not is_recovery_eligible_model(model_name):
            return []             # cloud model => byte-identical to pre-fix
        names = {n for n in (valid_tool_names or ()) if isinstance(n, str)}
        if not names:
            return []

        calls: List[Dict[str, Any]] = []
        for body in _strip_wrappers(content):
            parsed = _parse_one(body, names)
            if parsed is not None:
                calls.append(parsed)
        return calls
    except Exception:  # pragma: no cover - totality guard
        # FAIL-OPEN: an unparseable response is an ANSWER, never an exception.
        return []


def looks_like_tool_call_attempt(content: Any) -> Optional[str]:
    """Is this content a tool call the model MEANT, whatever it named?

    Returns the attempted tool name, or ``None`` if the content is ordinary
    prose. NEVER raises.

    WHY THIS IS SEPARATE FROM ``extract_text_tool_calls``: small local models
    routinely invent tool names that do not exist — measured live 2026-08-08,
    qwen2.5-coder asked for ``system_info`` and ``system_status``, neither of
    which Tlamatini binds. Recovery correctly REFUSES to run a non-existent
    tool, but the executor then treated the leftover JSON as the final answer
    and printed it to the user. That is the "stupid empty JSON" symptom.

    With this, the executor can tell the difference between "the model wrote
    prose" and "the model tried to call a tool and got the name wrong", and
    answer the second case by correcting the model instead of dumping JSON on
    the user.
    """
    try:
        if not content or not isinstance(content, str):
            return None
        for body in _strip_wrappers(content):
            try:
                payload = json.loads(body)
            except (ValueError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            for wrapper in ("tool_call", "function_call", "function"):
                inner = payload.get(wrapper)
                if isinstance(inner, dict) and _first_key(inner, _NAME_KEYS) is not None:
                    payload = inner
                    break
            name = _first_key(payload, _NAME_KEYS)
            if isinstance(name, str) and name.strip():
                # Require an arguments-ish key too, so a random JSON object
                # that merely has a "name" field is not mistaken for a call.
                if any(k in payload for k in _ARGS_KEYS):
                    return name.strip()
        return None
    except Exception:  # pragma: no cover - totality guard
        return None


def suggest_tool_names(attempted: str, valid_tool_names: Iterable[str],
                       limit: int = 8) -> List[str]:
    """Best-guess real tool names for a name the model invented. NEVER raises."""
    try:
        names = [n for n in (valid_tool_names or ()) if isinstance(n, str)]
        if not attempted:
            return names[:limit]
        tokens = {t for t in re.split(r"[^a-z0-9]+", attempted.lower()) if len(t) > 2}
        if not tokens:
            return names[:limit]
        scored = []
        for n in names:
            low = n.lower()
            hits = sum(1 for t in tokens if t in low)
            if hits:
                scored.append((hits, -len(n), n))
        scored.sort(reverse=True)
        return [n for _, _, n in scored[:limit]]
    except Exception:  # pragma: no cover - totality guard
        return []


def describe_toolcall_shape(response: Any, recovered: Optional[List[Dict[str, Any]]] = None) -> str:
    """One-line diagnostic for the ``--- [TOOLCALL-SHAPE]`` log line. NEVER raises."""
    try:
        structured = list(getattr(response, "tool_calls", None) or [])
        if structured:
            names = ", ".join(str(c.get("name", "?")) for c in structured[:6])
            return f"structured ({len(structured)}): {names}"
        if recovered:
            names = ", ".join(str(c.get("name", "?")) for c in recovered[:6])
            return f"TEXT-JSON RECOVERED ({len(recovered)}): {names}"
        content = getattr(response, "content", "") or ""
        if not isinstance(content, str):
            content = str(content)
        snippet = content.strip().replace("\n", " ")[:200]
        return f"none - answering with {len(content)} chars: {snippet!r}"
    except Exception:  # pragma: no cover - totality guard
        return "none - (shape probe failed)"
