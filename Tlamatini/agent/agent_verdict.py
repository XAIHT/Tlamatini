"""Deterministic verdict engine for wrapped-agent results.

WHY THIS MODULE EXISTS
======================

A pool agent finishes and TWO completely different questions get asked about
it, and they have TWO different answers:

    PROCESS QUESTION : "did the child process exit 0?"
    AGENT QUESTION   : "did the agent do the job it was asked to do,
                        and what did it FIND?"

Until 2026-08-06 the runtime collapsed both into ONE string.
``tools._launch_wrapped_chat_agent`` set ``payload["status"]`` from the exit
code, and ``_maybe_promote_section_fields_to_payload`` then tried to lift the
agent's OWN ``status:`` out of its ``INI_SECTION`` block with
``payload.setdefault(key, value)`` -- which, on the key that mattered most, was
a silent NO-OP.  The agent's truthful self-report was DISCARDED and the crude
exit-code verdict survived.

The live consequence (Angela, LaTeXer wizard STEP 4): a linter was asked to
check a deliberately broken document, found the bug exactly as designed, and
the Exec Report stamped it a red **FAILURE**.  Worse, ``mcp_agent`` already
had a ``_DIAGNOSTIC_COMPLETED_STATUSES`` set containing ``invalid`` written to
prevent precisely that -- but it was UNREACHABLE, because the value it tested
had already been overwritten with ``"failed"`` upstream.

This module replaces that string-sniffing with an actual small expert system:

    1. a LEXER/PARSER that turns the agent's ``INI_SECTION`` self-report into a
       TYPED SYNTAX TREE (``SectionNode`` -> ``KVNode`` -> typed values), and
    2. an INFERENCE ENGINE that walks that tree through an ORDERED, EXPLICIT
       production-rule table and returns a ``Verdict`` carrying its rule id and
       the exact evidence that fired it.

It is 100% DETERMINISTIC -- no model call, no heuristics, no guessing.  A
verdict engine that is itself probabilistic could not be trusted to say whether
something failed, and it would cost a round-trip on every tool call.  The
agents already emit a precise, machine-readable self-report; the only thing
that was ever missing was somebody actually READING it.

CONTRACT (do NOT weaken)
------------------------
* The AGENT'S OWN self-report OUTRANKS the process exit code.  An exit code is
  one bit; the self-report is a typed record.
* An agent's self-report is NEVER dropped or overwritten.  On a key collision
  the caller keeps BOTH -- process view under the original key, agent view
  under ``agent_<key>``.
* A READ-ONLY DIAGNOSTIC that reports an adverse finding has SUCCEEDED.  The
  finding is the DELIVERABLE, not a malfunction.  A red row must mean "the tool
  malfunctioned", never "the tool found something".
* FAIL-OPEN: every parse/coercion error resolves to "no opinion" and falls
  through to the next rule.  Nothing in here may raise into a caller.

Stdlib only, and it imports nothing from ``agent.*`` -- so it behaves
identically in source and frozen mode, and can never create an import cycle
between ``tools.py`` and ``mcp_agent.py`` (both import it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Tuple

__all__ = [
    "DIAGNOSTIC_COMPLETED_STATUSES",
    "WORK_NOT_DONE_STATUSES",
    "AGENT_ERROR_STATUSES",
    "KVNode",
    "SectionNode",
    "Verdict",
    "parse_section",
    "evaluate",
    "classify_payload",
    "reconcile_payload_verdict",
]


# =====================================================================
# 1. KNOWLEDGE BASE -- the status vocabulary
# =====================================================================
# ONE definition, imported by both tools.py and mcp_agent.py.  Two copies of
# this vocabulary would drift, and a drifted copy silently mis-colours rows.

#: The agent RAN TO COMPLETION and is REPORTING WHAT IT FOUND.  An adverse
#: finding here is the DELIVERABLE.  Deliberately narrow: read-only /
#: diagnostic verdicts only.
DIAGNOSTIC_COMPLETED_STATUSES = frozenset({
    # linters / validators
    "validated", "valid", "invalid",
    # analysers / inspectors
    "analyzed", "analysed", "analysis", "structure", "inspected", "triaged",
    # searches and listings
    "listed", "read", "matches", "no_matches", "found", "not_matched",
    # scanners
    "findings", "clean", "reported",
})

#: The agent behaved CORRECTLY but the work the user asked for did NOT happen.
#: Red is honest here -- the user got no PDF, no edit, no build.
WORK_NOT_DONE_STATUSES = frozenset({
    "refused", "not_found", "not_unique", "engine_unavailable",
    "unavailable", "skipped", "timeout", "timed_out", "cancelled", "canceled",
    "noop", "blocked", "denied",
})

#: The agent itself is declaring a malfunction.
AGENT_ERROR_STATUSES = frozenset({"error", "failed", "failure", "crashed", "exception"})

_FALSEY_STRINGS = frozenset({"false", "no", "0", "off", "none", "null"})
_TRUEY_STRINGS = frozenset({"true", "yes", "1", "on"})

#: Keys whose value is a VERDICT, not free text.
_STATUS_KEYS = ("status",)
#: Keys whose value is a BOOLEAN self-assessment.
_BOOL_KEYS = ("success", "ok")
#: Keys whose value is an ERROR COUNT.
_COUNT_KEYS = ("errors", "error")

_INI_SECTION_RE = re.compile(
    r"INI_SECTION_(?P<type>[A-Z0-9_]+)<<<\r?\n(?P<body>.*?)>>>END_SECTION_(?P=type)",
    re.DOTALL,
)


# =====================================================================
# 2. THE TYPED AST
# =====================================================================

#: Value kinds a KVNode can carry after coercion.
KIND_STATUS = "status"
KIND_BOOL = "bool"
KIND_COUNT = "count"
KIND_TEXT = "text"

#: Semantic classes a STATUS value resolves to.
CLASS_DIAGNOSTIC = "diagnostic_completed"
CLASS_WORK_NOT_DONE = "work_not_done"
CLASS_ERROR = "agent_error"
CLASS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class KVNode:
    """One ``key: value`` line of an agent's INI_SECTION header, TYPED.

    ``raw`` is always the verbatim text.  ``kind`` says how the value was
    coerced, and ``value`` is the coerced result (``None`` when the text could
    not be coerced -- which is "no opinion", never an error).
    """

    key: str
    raw: str
    kind: str = KIND_TEXT
    value: object = None
    status_class: str = CLASS_UNKNOWN
    line_no: int = 0

    def __str__(self) -> str:                     # evidence string for logs
        return f"{self.key}: {self.raw}"


@dataclass(frozen=True)
class SectionNode:
    """A parsed ``INI_SECTION_<TYPE><<< ... >>>END_SECTION_<TYPE>`` block."""

    agent_type: str
    header: Tuple[KVNode, ...] = field(default_factory=tuple)
    body: str = ""

    def get(self, key: str) -> Optional[KVNode]:
        target = (key or "").strip().lower()
        for node in self.header:
            if node.key == target:
                return node
        return None


@dataclass(frozen=True)
class Verdict:
    """The engine's decision, with the evidence that produced it.

    ``rule`` and ``evidence`` exist so a verdict is AUDITABLE: when a row is
    coloured, the log can say exactly which rule fired and on what text.
    """

    ok: bool
    rule: str
    reason: str = ""
    evidence: str = ""
    source: str = "default"          # 'agent' | 'process' | 'default'

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "rule": self.rule,
            "reason": self.reason,
            "evidence": self.evidence,
            "source": self.source,
        }


# =====================================================================
# 3. LEXER / PARSER  --  text  ->  typed AST
# =====================================================================

def _coerce_bool(text: str) -> Optional[bool]:
    low = (text or "").strip().lower()
    if low in _TRUEY_STRINGS:
        return True
    if low in _FALSEY_STRINGS:
        return False
    return None


def _coerce_count(text: str) -> Optional[int]:
    """Coerce to an int COUNT.  ``"0"`` means ZERO -- that is the whole point.

    A pool agent's KV header is TEXT, so a perfect run reports ``errors: 0`` as
    the STRING ``"0"`` -- and ``bool("0")`` is ``True``.  Reading that value
    with plain truthiness is what once stamped every flawless build FAILURE.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return int(float(raw))
    except ValueError:
        return None


def _classify_status(text: str) -> str:
    low = (text or "").strip().lower()
    if not low:
        return CLASS_UNKNOWN
    if low in AGENT_ERROR_STATUSES:
        return CLASS_ERROR
    if low in WORK_NOT_DONE_STATUSES:
        return CLASS_WORK_NOT_DONE
    if low in DIAGNOSTIC_COMPLETED_STATUSES:
        return CLASS_DIAGNOSTIC
    return CLASS_UNKNOWN


def _make_node(key: str, raw: str, line_no: int) -> KVNode:
    """Coerce ONE header line into a typed node.  Never raises."""
    k = (key or "").strip().lower()
    if k in _STATUS_KEYS:
        low = (raw or "").strip().lower()
        return KVNode(k, raw, KIND_STATUS, low, _classify_status(low), line_no)
    if k in _BOOL_KEYS:
        return KVNode(k, raw, KIND_BOOL, _coerce_bool(raw), CLASS_UNKNOWN, line_no)
    if k in _COUNT_KEYS:
        return KVNode(k, raw, KIND_COUNT, _coerce_count(raw), CLASS_UNKNOWN, line_no)
    return KVNode(k, raw, KIND_TEXT, raw, CLASS_UNKNOWN, line_no)


def parse_section(text: str) -> Optional[SectionNode]:
    """Parse the FIRST ``INI_SECTION`` block in ``text`` into a SectionNode.

    Grammar (the project-wide Parametrizer convention):

        section := 'INI_SECTION_' TYPE '<<<' NEWLINE header body
                   '>>>END_SECTION_' TYPE
        header  := (KEY ':' VALUE NEWLINE)*        -- until the first blank line
        body    := .*                              -- becomes ``response_body``

    Returns ``None`` when there is no parsable block.  NEVER raises: a
    malformed self-report must degrade to "no opinion", not to an exception on
    the chat path.
    """
    try:
        if not text:
            return None
        match = _INI_SECTION_RE.search(text)
        if not match:
            return None
        body_text = match.group("body")
        header: list = []
        rest: list = []
        in_header = True
        for idx, line in enumerate(body_text.splitlines(), start=1):
            if in_header:
                if line.strip() == "":
                    in_header = False
                    continue
                if ":" not in line:
                    continue
                key, _, value = line.partition(":")
                node = _make_node(key, value.strip(), idx)
                if node.key:
                    header.append(node)
            else:
                rest.append(line)
        return SectionNode(match.group("type").lower(), tuple(header), "\n".join(rest))
    except Exception:                                   # fail-open, always
        return None


# =====================================================================
# 4. INFERENCE ENGINE  --  ordered production rules over the AST
# =====================================================================
#
# ORDER IS THE ALGORITHM.  First rule to fire wins, and the ordering encodes
# the precedence lattice:
#
#     the agent's EXPLICIT verdict   >   the agent's derived signals
#                                    >   the process exit code
#
# R4 MUST outrank R5 and R6.  A linter that worked perfectly reports
# ``status: invalid`` AND ``success: False`` AND ``errors: 2`` in the same
# breath -- the last two describe the DOCUMENT, not the agent.  Testing them
# before R4 is exactly the bug this module was written to kill.

def evaluate(section: Optional[SectionNode], exit_code: Optional[int] = None) -> Verdict:
    """Decide whether the AGENT succeeded.  Deterministic and total."""

    # -- R1: no self-report at all -> the process exit code is all we have.
    if section is None or not section.header:
        if exit_code is None:
            return Verdict(True, "R1.no_signal", "no self-report and no exit code")
        if exit_code == 0:
            return Verdict(True, "R1.exit_zero", "process exited 0",
                           f"exit_code={exit_code}", "process")
        return Verdict(False, "R1.exit_nonzero", "process exited non-zero and the "
                       "agent published no self-report",
                       f"exit_code={exit_code}", "process")

    status = section.get("status")

    # -- R2: the agent DECLARES a malfunction.  Believe it immediately.
    if status is not None and status.status_class == CLASS_ERROR:
        return Verdict(False, "R2.agent_declared_error",
                       "the agent reported an error", str(status), "agent")

    # -- R3: the agent behaved correctly but THE WORK DID NOT HAPPEN.
    #        (refused / not_found / not_unique / engine_unavailable / ...)
    #        Red is honest: the user asked for a thing and did not get it.
    if status is not None and status.status_class == CLASS_WORK_NOT_DONE:
        return Verdict(False, "R3.work_not_done",
                       f"the agent did not perform the work ({status.value})",
                       str(status), "agent")

    # -- R4: THE FIX.  A read-only DIAGNOSTIC ran to completion and is
    #        reporting what it FOUND.  Finding a problem IS the job.
    #        This MUST come before R5/R6 -- see the note above.
    if status is not None and status.status_class == CLASS_DIAGNOSTIC:
        return Verdict(True, "R4.diagnostic_completed",
                       f"diagnostic completed and reported its findings "
                       f"({status.value})", str(status), "agent")

    # -- R5: an EXPLICIT boolean self-assessment.
    for key in _BOOL_KEYS:
        node = section.get(key)
        if node is not None and isinstance(node.value, bool):
            if node.value:
                return Verdict(True, "R5.agent_flag_true",
                               "the agent reported success", str(node), "agent")
            return Verdict(False, "R5.agent_flag_false",
                           "the agent reported failure", str(node), "agent")

    # -- R6: a NON-ZERO error COUNT (zero is not a failure; see _coerce_count).
    for key in _COUNT_KEYS:
        node = section.get(key)
        if node is not None and isinstance(node.value, int) and node.value > 0:
            return Verdict(False, "R6.error_count",
                           f"{node.value} {key}", str(node), "agent")

    # -- R7: the agent said nothing decisive -> fall back to the process.
    if exit_code is not None and exit_code != 0:
        return Verdict(False, "R7.exit_nonzero",
                       "the agent published no decisive verdict and the process "
                       "exited non-zero", f"exit_code={exit_code}", "process")

    # -- R8: nothing argued for failure.
    return Verdict(True, "R8.default", "no failure signal found")


# =====================================================================
# 5. INTEGRATION -- the two call sites
# =====================================================================

def _as_int(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def reconcile_payload_verdict(payload: dict) -> None:
    """Make a wrapped-agent payload tell the truth.  Mutates ``payload``.

    Called by ``tools._launch_wrapped_chat_agent`` AFTER the INI_SECTION
    fields have been promoted.  It:

    * runs the AST + rule engine over the agent's own self-report;
    * records ``verdict`` / ``verdict_rule`` / ``verdict_reason`` /
      ``verdict_source`` so the decision is auditable in the log and readable
      by the LLM;
    * PRESERVES the process view under ``process_status`` -- nothing is lost;
    * and, ONLY when the agent proved it completed a diagnostic (rule R4),
      repairs the top-level ``status`` that the exit code had wrongly set to
      ``"failed"``, so the LLM does not narrate a failure that never happened.

    Deliberately conservative: every other case leaves ``status`` untouched, so
    existing consumers that key off ``status == "failed"`` (e.g. the
    Instant-Messaging-Doctor auto-launch) keep working exactly as before.

    Never raises -- a verdict engine that can break the chat path is worse than
    the mislabelled row it was written to fix.
    """
    try:
        if not isinstance(payload, dict):
            return
        section = parse_section(payload.get("log_excerpt") or "")
        verdict = evaluate(section, _as_int(payload.get("exit_code")))

        payload["verdict"] = "ok" if verdict.ok else "failed"
        payload["verdict_rule"] = verdict.rule
        payload["verdict_reason"] = verdict.reason
        payload["verdict_source"] = verdict.source
        if verdict.evidence:
            payload["verdict_evidence"] = verdict.evidence

        process_status = str(payload.get("status") or "")
        payload.setdefault("process_status", process_status)

        if verdict.rule == "R4.diagnostic_completed" and process_status.lower() == "failed":
            # The exit code was WRONG about this run.  Publish the agent's own
            # verdict as the headline status; the process view survives under
            # ``process_status`` and ``exit_code``.
            node = section.get("status") if section else None
            if node is not None and node.value:
                payload["status"] = str(node.value)
    except Exception:                                   # fail-open, always
        return


def classify_payload(payload: dict) -> Verdict:
    """Verdict for an ALREADY-BUILT payload dict (the Exec-Report side).

    Prefers a ``verdict`` stamped by :func:`reconcile_payload_verdict`; falls
    back to re-deriving it from ``agent_status`` / ``log_excerpt`` so a payload
    that never went through reconciliation is still judged by the same rules.
    """
    try:
        if not isinstance(payload, dict):
            return Verdict(True, "R8.default", "not a dict")

        stamped = str(payload.get("verdict") or "").strip().lower()
        if stamped in ("ok", "failed"):
            return Verdict(stamped == "ok",
                           str(payload.get("verdict_rule") or "stamped"),
                           str(payload.get("verdict_reason") or ""),
                           str(payload.get("verdict_evidence") or ""),
                           str(payload.get("verdict_source") or "agent"))

        # ``agent_status`` is where a COLLIDING self-report is preserved.
        agent_status = str(payload.get("agent_status") or "").strip().lower()
        if agent_status:
            node = KVNode("status", agent_status, KIND_STATUS, agent_status,
                          _classify_status(agent_status))
            return evaluate(SectionNode("payload", (node,)),
                            _as_int(payload.get("exit_code")))

        return evaluate(parse_section(payload.get("log_excerpt") or ""),
                        _as_int(payload.get("exit_code")))
    except Exception:                                   # fail-open, always
        return Verdict(True, "R8.default", "verdict engine error")
