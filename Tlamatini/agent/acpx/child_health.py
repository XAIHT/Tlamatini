# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
ACPX child-health classification — did the external CLI actually DELIVER?

Why this exists
---------------
An ACP child can exit **0** and still have done nothing the user asked for.
Measured live on 2026-09-07 (Angela's SETI research run):

    $ claude -p "Use WebSearch to find ..."
    Angela, the web search was blocked — permission wasn't granted, so I
    can't look up the current Python version.
    $ echo $?
    0

ACPX reported that turn as a SUCCESS, the Exec Report stamped it green, and
the orchestrating LLM went on believing it had research in hand. That is the
same *silent, plausible, WRONG deliverable* class as the missing-images PDFer
bug and the LaTeXer linter verdict: an exit code is one bit, and one bit
cannot describe what a coding agent did.

The same run also produced four **noisy** failures that ``acp_doctor`` had
already declared healthy, because ``--version`` answers fine on a CLI that is
broken everywhere else:

    gemini   -> Error authenticating: IneligibleTierError ...
    codex    -> Error loading config.toml: unknown variant `default`
    claude   -> Credit balance is too low
    copilot  -> (no output at all)

This module is the ONE place that decides "delivered vs not", and it is used
by BOTH callers so they can never drift:

    * ``runtime.AcpSession._oneshot_send_turn`` — stamps every finished turn.
    * ``runtime.AcpxRuntime.readiness_probe``   — powers ``acp_doctor(deep)``.

Contract (do NOT weaken)
------------------------
1. **A long, real answer is NEVER reclassified as a failure.** Only short or
   empty output is even examined for refusal markers. A 3 KB research briefing
   that happens to contain the words "rate limit" stays a success. This is the
   same anchoring discipline the self-healing status matcher learned the hard
   way — a substring match on a long answer creates false failures, and a
   false failure is worse than the missed one it replaces.
2. **Markers are read from the HEAD of the output only.** A refusal announces
   itself immediately; it does not bury the reason on line 90.
3. **Chrome is not a deliverable** — but SHORT IS NOT CHROME. Output only
   counts as chrome when it is both long enough to be more than a terse reply
   AND almost letter-free, i.e. a TUI that painted a box-drawing frame and no
   words. A 7-character "PEER_OK" is a complete, correct answer.
4. **FAIL-OPEN**: anything unrecognised is treated as DELIVERED. This module
   exists to stop ACPX lying about failure, not to invent new ones, and it
   must never raise into a caller.
5. Stdlib-only; imports nothing from ``agent.*`` so it behaves identically
   frozen and from source, and can never create an import cycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# A refusal is short. A deliverable is not. Output longer than this is
# accepted as real work without ever being scanned for refusal markers.
SHORT_ANSWER_CHARS = 1200

# Refusal markers must appear this early — a real reason leads, it does not
# hide behind 400 characters of preamble.
HEAD_CHARS = 400

# "Decorative" output: plenty of characters, almost no letters -- a TUI that
# painted a box frame and nothing else (kimi / copilot on the tui-repl
# transport did exactly this). BOTH conditions are required, and that pairing
# is load-bearing: an early draft tested the letter count ALONE and classified
# a perfectly good 7-character answer ("PEER_OK") as NO_OUTPUT. Short is not
# the same as empty, and a false failure is the one thing this module must
# never manufacture.
MIN_ALNUM_CHARS = 40
DECORATIVE_MIN_CHARS = 60

# ── The closed vocabulary of non-delivery codes ──────────────────────
#   Every code below means: the requested work did NOT happen.
PERMISSION_BLOCKED = "PERMISSION_BLOCKED"
WORKSPACE_NOT_TRUSTED = "WORKSPACE_NOT_TRUSTED"
NO_CREDIT = "NO_CREDIT"
USAGE_LIMIT = "USAGE_LIMIT"
AUTH_FAILED = "AUTH_FAILED"
CONFIG_INVALID = "CONFIG_INVALID"
UPSTREAM_ERROR = "UPSTREAM_ERROR"
NO_OUTPUT = "NO_OUTPUT"
CHILD_ERROR = "CHILD_ERROR"
DELIVERED = "DELIVERED"

NON_DELIVERY_CODES = frozenset({
    PERMISSION_BLOCKED, WORKSPACE_NOT_TRUSTED, NO_CREDIT, USAGE_LIMIT,
    AUTH_FAILED, CONFIG_INVALID, UPSTREAM_ERROR, NO_OUTPUT, CHILD_ERROR,
})

# Ordered most-specific-first. Each entry: (code, human reason, patterns).
# Patterns are matched case-insensitively against the HEAD of the output.
_SIGNATURES: List[Tuple[str, str, Tuple[str, ...]]] = [
    (WORKSPACE_NOT_TRUSTED,
     "the child's working directory is not trusted, so its permissions file was ignored",
     ("has not been trusted", "trust dialog",
      "not inside a trusted directory")),
    (NO_CREDIT,
     "the account behind this CLI has no credit left",
     ("credit balance is too low", "insufficient credit",
      "insufficient_quota", "billing")),
    (USAGE_LIMIT,
     "the account hit a plan / usage / rate limit",
     ("hit your session limit", "session limit", "usage limit",
      "rate limit", "rate_limit", "quota exceeded", "too many requests")),
    (PERMISSION_BLOCKED,
     "the child stopped at its own permission prompt and did no work",
     ("permission wasn't granted", "permission was not granted",
      "awaiting your permission", "hasn't been granted permission",
      "has not been granted permission", "was blocked because",
      "search was blocked", "need from you: approve",
      "please approve", "run `/permissions`", "/permissions",
      "requires permission", "permission denied for tool")),
    (AUTH_FAILED,
     "the CLI could not authenticate",
     ("error authenticating", "ineligibletiererror", "not authenticated",
      "api key is invalid", "invalid api key", "invalid_api_key",
      "no auth type is selected", "please log in", "login required",
      "unauthorized", "authentication failed", "oauth")),
    (CONFIG_INVALID,
     "the CLI refused to start because its own config file is invalid",
     ("error loading config", "unknown variant", "invalid configuration",
      "failed to parse config", "config error")),
    (UPSTREAM_ERROR,
     "the model provider returned a server-side error",
     ("server had an error", "server_error", "internal server error",
      "error code: 500", "error code: 502", "error code: 503",
      "service unavailable", "overloaded")),
]


@dataclass(frozen=True)
class ChildVerdict:
    """Typed answer to: did this ACP child actually deliver the work?"""
    delivered: bool
    code: str
    reason: str
    evidence: str = ""

    def as_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"delivered": self.delivered, "code": self.code}
        if not self.delivered:
            out["failure_reason"] = self.reason
            if self.evidence:
                out["failure_evidence"] = self.evidence
        return out


_DELIVERED = ChildVerdict(True, DELIVERED, "")


def _alnum_count(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def _is_decorative(text: str) -> bool:
    """True when the child emitted chrome instead of an answer.

    Requires BOTH "long enough to be more than a terse reply" AND "almost no
    letters". A short answer is never decorative -- see MIN_ALNUM_CHARS.
    """
    return (len(text) >= DECORATIVE_MIN_CHARS
            and _alnum_count(text) < MIN_ALNUM_CHARS)


def _match_signature(head: str) -> Optional[Tuple[str, str, str]]:
    """Return (code, reason, matched_marker) for the first signature hit."""
    low = head.lower()
    for code, reason, patterns in _SIGNATURES:
        for marker in patterns:
            if marker in low:
                return (code, reason, marker)
    return None


def _first_meaningful_line(text: str, limit: int = 180) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and _alnum_count(stripped) >= 3:
            return stripped[:limit]
    return text.strip()[:limit]


def classify_child_output(stdout: Any, stderr: Any = "",
                          exit_code: Any = 0) -> ChildVerdict:
    """Decide whether an ACP child delivered real work. NEVER raises.

    See the module docstring for the contract. The short version: only short,
    empty or letter-less output is ever suspected; everything else is work.
    """
    try:
        out = (stdout or "") if isinstance(stdout, str) else str(stdout or "")
        err = (stderr or "") if isinstance(stderr, str) else str(stderr or "")
        try:
            rc = int(exit_code)
        except (TypeError, ValueError):
            rc = 0

        out_stripped = out.strip()
        err_stripped = err.strip()

        # ── Rule 1 ── A substantial answer is work. Never second-guessed.
        if len(out_stripped) >= SHORT_ANSWER_CHARS and \
                _alnum_count(out_stripped) >= MIN_ALNUM_CHARS:
            return _DELIVERED

        # ── Rule 2 ── Nothing legible came back at all: either literally
        # empty, or pure chrome (a TUI frame with no words in it).
        if not out_stripped or _is_decorative(out_stripped):
            hit = _match_signature(err_stripped[:HEAD_CHARS]) if err_stripped else None
            if hit:
                code, reason, marker = hit
                return ChildVerdict(False, code, reason,
                                    _first_meaningful_line(err_stripped))
            if err_stripped:
                return ChildVerdict(
                    False, CHILD_ERROR,
                    "the child produced no usable answer and wrote to stderr",
                    _first_meaningful_line(err_stripped))
            return ChildVerdict(
                False, NO_OUTPUT,
                "the child produced no output at all "
                "(a TUI transport that never flushed, or a silent crash)",
                "")

        # ── Rule 3 ── Short but legible: this is where refusals live.
        hit = _match_signature(out_stripped[:HEAD_CHARS])
        if hit:
            code, reason, marker = hit
            return ChildVerdict(False, code, reason,
                                _first_meaningful_line(out_stripped))
        if err_stripped:
            hit = _match_signature(err_stripped[:HEAD_CHARS])
            if hit:
                code, reason, marker = hit
                return ChildVerdict(False, code, reason,
                                    _first_meaningful_line(err_stripped))

        # ── Rule 4 ── Short, legible, no known refusal, but the process
        # itself failed. Trust the exit code here — there is no deliverable
        # large enough to contradict it.
        if rc != 0:
            return ChildVerdict(
                False, CHILD_ERROR,
                "the child exited %s without producing a usable answer" % rc,
                _first_meaningful_line(out_stripped or err_stripped))

        # ── Rule 5 ── FAIL-OPEN. A short clean answer is still an answer.
        return _DELIVERED
    except Exception:                                   # pragma: no cover
        # A health classifier that can break the chat path is worse than the
        # mislabelled row it was written to fix.
        return _DELIVERED


def summarize_for_doctor(verdict: ChildVerdict) -> Dict[str, Any]:
    """Shape a ChildVerdict for the per-agent rows of ``acp_doctor(deep)``."""
    return {
        "ready": bool(verdict.delivered),
        "code": verdict.code,
        "reason": "" if verdict.delivered else verdict.reason,
        "evidence": "" if verdict.delivered else verdict.evidence,
    }


__all__ = [
    "ChildVerdict",
    "classify_child_output",
    "summarize_for_doctor",
    "NON_DELIVERY_CODES",
    "SHORT_ANSWER_CHARS",
    "HEAD_CHARS",
    "MIN_ALNUM_CHARS",
    "DELIVERED",
    "PERMISSION_BLOCKED",
    "WORKSPACE_NOT_TRUSTED",
    "NO_CREDIT",
    "USAGE_LIMIT",
    "AUTH_FAILED",
    "CONFIG_INVALID",
    "UPSTREAM_ERROR",
    "NO_OUTPUT",
    "CHILD_ERROR",
]
