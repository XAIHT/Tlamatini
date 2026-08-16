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
* A DEGRADED result is NOT a clean success.  When the deliverable is missing
  or compromised -- audio tokens with nothing audible, a PDF that only built
  because content was quarantined -- the row goes RED.  Weigh the two ways of
  being wrong: a false green makes Angela doubt her speakers, a false red costs
  her one glance at a row that names the fix.
* THE VOCABULARY IS CLOSED, and a guard keeps it that way.  Every status token
  a pool agent can emit must live in exactly one of the five sets below;
  `agent/test_status_vocabulary.py` statically lifts them out of every agent and
  fails on any it does not recognise.  Without that guard an invented token was
  indistinguishable from an approved one -- both fell to R8's default and came
  out green -- which is how 22 of them accumulated in silence (review,
  2026-08-16).
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
    "WORK_COMPLETED_STATUSES",
    "WORK_DEGRADED_STATUSES",
    "WORK_NOT_DONE_STATUSES",
    "AGENT_ERROR_STATUSES",
    "KNOWN_STATUSES",
    "status_class",
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

#: The agent DID THE WORK and the DELIVERABLE IS INTACT.  Green, EXPLICITLY.
#:
#: Before 2026-08-16 no such set existed: a completed action fell all the way
#: through to R8's anonymous default.  That silence WAS the hole.  A status no
#: rule had ever heard of came out exactly the same colour as a status every
#: rule approved -- which is how 22 invented tokens entered this codebase
#: without a single thing failing.  Naming the green set is what lets the guard
#: (``agent/test_status_vocabulary.py``) tell those two cases apart.
#:
#: Membership test: "the user got what they asked for."  A FAULT-TOLERANT path
#: still belongs here when its OUTPUT survived whole -- Image-Interpreter
#: merging from the one vision model that answered still hands back a complete
#: interpretation, which is precisely what that fallback was designed to do.
WORK_COMPLETED_STATUSES = frozenset({
    # generic completions
    "success", "ok", "done", "complete", "completed",
    # authoring / building
    "created", "edited", "written", "compiled", "built", "scaffolded",
    "installed", "cleaned", "saved", "merged",
    # transport / delivery
    "sent", "delivered", "forwarded", "accepted", "duplicate",
    # media capture + output
    "spoken", "played", "recorded", "captured", "transcribed",
    # liveness / lifecycle probes
    "pong", "healthy", "connected", "started", "stopped",
    # fault-tolerant paths whose DELIVERABLE is still whole
    "partial_interpreter_1_only", "partial_interpreter_2_only",
    "merge_fallback_concat",
})

#: The agent produced SOMETHING, but the DELIVERABLE is COMPROMISED or ABSENT.
#: NOT a clean success -- and since this engine returns one bit, it goes RED.
#:
#: THE DECISION AND ITS REASONING (Angela, 2026-08-16).  Weigh the two ways of
#: being wrong.  A false GREEN on ``tokens_only`` tells Angela that Tlamatini
#: SPOKE, when nothing was ever audible -- she is left doubting her speakers
#: instead of her build.  A false RED costs her one glance at a row that then
#: names the missing vocoder.  The cheap mistake wins.  LaTeXer already wrote
#: the same rule in its own words: "a degraded build is NOT a success and must
#: never be reported as one" (``latexer.py::_attach_ladder_trace``).
#:
#: The boundary against WORK_COMPLETED_STATUSES is the DELIVERABLE, never the
#: path taken to it: fault tolerance that still delivers is green; a PDF missing
#: the paragraphs the repair ladder quarantined is not.
WORK_DEGRADED_STATUSES = frozenset({
    "degraded",               # LaTeXer: a PDF exists ONLY because content was cut
    "compiled_with_errors",   # LaTeXer: a PDF exists but LaTeX reported errors
    "tokens_only",            # Talker: tokens saved, NO audible speech at all
    "operator_required",      # parked pending a human -- the work has not happened
    "assert_failed",          # Playwrighter: the flow's own assertion did not hold
    "partial", "partial_success", "incomplete",
})

#: The agent behaved CORRECTLY but the work the user asked for did NOT happen.
#: Red is honest here -- the user got no PDF, no edit, no build, no message.
WORK_NOT_DONE_STATUSES = frozenset({
    "refused", "not_found", "not_unique", "engine_unavailable",
    "unavailable", "skipped", "timeout", "timed_out", "cancelled", "canceled",
    "noop", "blocked", "denied",
    # -- added 2026-08-16, all four PROVEN to be emitted by a shipping agent:
    "unreachable",            # Zavuerer: the messaging endpoint could not be reached
    "forward_failed",         # Gateway-Relayer: the relay leg did not deliver
    "rejected",               # Gatewayer / Gateway-Relayer: the payload was refused
    "ignored",                # Gateway-Relayer: the event matched no forwarding rule
})

#: The agent itself is declaring a malfunction.
AGENT_ERROR_STATUSES = frozenset({"error", "failed", "failure", "crashed", "exception"})

#: EVERY status token this system understands -- the guard's oracle.
#:
#: ``agent/test_status_vocabulary.py`` statically walks every pool agent, lifts
#: each literal status it can emit, and requires membership here.  THAT is the
#: guard item 4 of the 2026-08-16 review asked for: an invented token now fails
#: LOUDLY at test time instead of defaulting to green in silence forever.
#:
#: To add a token: put it in the ONE set whose verdict it deserves, above.  The
#: five sets are kept pairwise DISJOINT (pinned by the guard) so exactly one
#: rule can ever claim a token, and ``_classify_status``'s order is therefore a
#: readability choice rather than a tie-break.
KNOWN_STATUSES = frozenset(
    DIAGNOSTIC_COMPLETED_STATUSES
    | WORK_COMPLETED_STATUSES
    | WORK_DEGRADED_STATUSES
    | WORK_NOT_DONE_STATUSES
    | AGENT_ERROR_STATUSES
)

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
CLASS_COMPLETED = "work_completed"
CLASS_DEGRADED = "work_degraded"
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
    if low in WORK_DEGRADED_STATUSES:
        return CLASS_DEGRADED
    if low in DIAGNOSTIC_COMPLETED_STATUSES:
        return CLASS_DIAGNOSTIC
    if low in WORK_COMPLETED_STATUSES:
        return CLASS_COMPLETED
    return CLASS_UNKNOWN


def status_class(text: str) -> str:
    """Public, TOTAL classifier for ONE status token.

    The five vocabularies are disjoint, so this is a lookup, not a ranking.  A
    token nobody declared resolves to :data:`CLASS_UNKNOWN` -- which is exactly
    the case the guard exists to make impossible in shipped code, and which the
    engine still survives at runtime (see rule R8).  Never raises.
    """
    try:
        return _classify_status(text)
    except Exception:                                   # fail-open, always
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

    # -- R3b: the agent produced SOMETHING, but DEGRADED -- the deliverable is
    #         either compromised (content quarantined out of a PDF) or missing
    #         outright (audio tokens saved, nothing audible).  It MUST outrank
    #         R4/R5/R6: LaTeXer's degraded build already sets `ok: False` and so
    #         lands red anyway, but Talker's `tokens_only` carries NO boolean at
    #         all -- so before this rule it fell all the way to R8 and rendered
    #         GREEN, telling Angela that Tlamatini had SPOKEN when not one
    #         sample was ever played. (Found in review, 2026-08-16.)
    if status is not None and status.status_class == CLASS_DEGRADED:
        return Verdict(False, "R3b.work_degraded",
                       f"the agent delivered a DEGRADED result ({status.value}) "
                       f"-- not a clean success",
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

    # -- R7b: the agent NAMED a completion ("sent" / "created" / "compiled").
    #         Deliberately placed AFTER R5, R6 and R7 so it can never overrule a
    #         truthful `success: False`, a non-zero error count, or a non-zero
    #         exit code: against every verdict this engine could already reach,
    #         it is a NO-OP.  Its job is to replace R8's anonymous default with
    #         a NAMED, auditable success -- which is precisely what makes an
    #         UNKNOWN token (R8b) legible as the anomaly it is, instead of
    #         hiding it among the legitimate greens.
    if status is not None and status.status_class == CLASS_COMPLETED:
        return Verdict(True, "R7b.work_completed",
                       f"the agent completed the work ({status.value})",
                       str(status), "agent")

    # -- R8b: a status was reported that NO vocabulary knows.  The verdict is
    #         deliberately UNCHANGED -- fail-open is the contract, and an
    #         unrecognised token is not evidence of failure -- and the source
    #         stays "default" so every downstream consumer keeps the exact
    #         fall-through it had before.  The ONLY thing this rule adds is a
    #         NAME: the token is quoted in the reason, so an invented status is
    #         greppable in tlamatini.log the day it first runs, instead of
    #         surfacing in a review two years later.  The static guard
    #         `agent/test_status_vocabulary.py` is what stops it ever shipping.
    if status is not None and status.raw.strip() and status.status_class == CLASS_UNKNOWN:
        return Verdict(True, "R8b.unknown_status",
                       f"unrecognised status token {status.value!r}: no rule "
                       f"claims it, defaulting to success (fail-open)",
                       str(status))

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
