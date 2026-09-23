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
Secret redaction for the skill boundary — the ONE definition of
"is this input a credential, and what may leave the harness".

WHY THIS EXISTS
---------------
``setup-new-acpx-key`` declares an ``api_key`` input. The harness used to
record every coerced argument verbatim in

    * the audit event stream (serialized to NDJSON on disk), and
    * the plan envelope returned to the LLM / chat transcript,

so a real credential travelled into an ordinary audit file and into
tool-visible output. Nothing had leaked externally, but the data path was
unredacted and a credential belongs only in the authorized operation that
consumes it.

CONTRACTS (do NOT weaken)
-------------------------
1. **A redacted value NEVER carries a prefix, suffix, length or hash of the
   secret.** ``sk-ant-…`` identifies the provider and the account family;
   a length narrows a brute force. The placeholder is content-free and
   carries only the FIELD name, which the caller already knows.
2. **Explicit beats heuristic.** ``sensitive: true`` on an input declaration
   is authoritative. The name heuristic is the safety net for a skill whose
   author forgot the flag — it can only ever redact MORE, never less.
3. **Redact the whole tree**, not the top level: nested dicts, lists,
   failure details and exception strings all pass through here.
4. **Scrub by VALUE too.** Once a secret's literal text is known, it is
   removed from free-form strings (a stack trace, an error message, a
   command line the skill echoed back), because those are exactly where a
   credential reappears after the structured field was cleaned.
5. **FAIL-SAFE, not fail-open.** Everywhere else in Tlamatini an error
   resolves to "carry on"; here an error resolves to "redact". A dropped
   log line is recoverable, a published credential is not. Nothing in this
   module may raise into a caller.

Stdlib-only; imports nothing from ``agent.*`` so it behaves identically in
source and frozen mode and can never create an import cycle.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Set

#: Substrings that mark a field name as carrying a credential. Matched
#: case-insensitively against the declared input name with separators
#: removed, so ``api_key``, ``apiKey``, ``API-KEY`` and ``apikey`` all hit.
SENSITIVE_NAME_TOKENS: frozenset = frozenset({
    "apikey",
    "accesskey",
    "secretkey",
    "privatekey",
    "token",
    "password",
    "passwd",
    "secret",
    "credential",
    "authorization",
    "bearer",
    "passphrase",
    "clientsecret",
    "sessionkey",
    "signingkey",
})

#: What replaces a secret. Content-free by design — see contract 1.
REDACTED_PLACEHOLDER = "<redacted>"

#: Below this length a "secret" is almost certainly a placeholder the user
#: typed ("x", "TODO", "") and scrubbing it by value would blank unrelated
#: prose. The STRUCTURED field is still redacted; only the free-text sweep
#: skips it.
_MIN_VALUE_SCRUB_LEN = 8

#: Hard ceiling on recursion so a self-referential structure cannot spin.
_MAX_DEPTH = 12


def _normalize_name(name: Any) -> str:
    """Lowercase a field name and drop separators for token matching."""
    try:
        return "".join(ch for ch in str(name).lower() if ch.isalnum())
    except Exception:
        return ""


def is_sensitive_name(name: Any) -> bool:
    """True when a FIELD NAME alone marks the value as a credential."""
    flat = _normalize_name(name)
    if not flat:
        return False
    return any(token in flat for token in SENSITIVE_NAME_TOKENS)


def is_sensitive_decl(decl: Any) -> bool:
    """
    True when this input declaration carries a credential.

    An explicit ``sensitive: true`` is authoritative (contract 2). The name
    heuristic then runs as the safety net; it can only add fields.
    """
    try:
        if isinstance(decl, dict):
            flag = decl.get("sensitive")
            if isinstance(flag, bool):
                if flag:
                    return True
                # An explicit ``sensitive: false`` is a deliberate authoring
                # decision and is honoured — but NOT for a field whose very
                # name says "credential", because that combination is far
                # more likely a mistake than an intent.
                return is_sensitive_name(decl.get("name"))
            return is_sensitive_name(decl.get("name"))
    except Exception:
        # Fail-SAFE: an unreadable declaration is treated as sensitive.
        return True
    return False


def sensitive_input_names(input_decls: Optional[Iterable[Any]]) -> List[str]:
    """Names of every declared input that carries a credential."""
    names: List[str] = []
    try:
        for decl in input_decls or []:
            if not isinstance(decl, dict):
                continue
            name = decl.get("name")
            if isinstance(name, str) and name and is_sensitive_decl(decl):
                names.append(name)
    except Exception:
        return names
    return names


def collect_secret_values(args: Optional[Dict[str, Any]],
                          sensitive_names: Iterable[str]) -> Set[str]:
    """
    The literal secret strings present in ``args``, for the free-text sweep.

    Values shorter than ``_MIN_VALUE_SCRUB_LEN`` are excluded: scrubbing a
    3-character "key" would blank innocent substrings all over the envelope
    (contract 4 is about credentials, not about mangling prose).
    """
    found: Set[str] = set()
    try:
        wanted = set(sensitive_names or ())
        for key, value in (args or {}).items():
            if key in wanted or is_sensitive_name(key):
                if isinstance(value, str) and len(value) >= _MIN_VALUE_SCRUB_LEN:
                    found.add(value)
    except Exception:
        return found
    return found


def scrub_text(text: Any, secrets: Optional[Iterable[str]]) -> Any:
    """Remove every known literal secret from a free-form string."""
    if not isinstance(text, str):
        return text
    try:
        out = text
        # Longest first, so a secret that contains another is replaced whole.
        for secret in sorted({s for s in (secrets or ()) if s}, key=len,
                             reverse=True):
            if secret in out:
                out = out.replace(secret, REDACTED_PLACEHOLDER)
        return out
    except Exception:
        # Fail-SAFE: if we cannot prove the text is clean, do not emit it.
        return REDACTED_PLACEHOLDER


def redact_structure(value: Any,
                     sensitive_names: Optional[Iterable[str]] = None,
                     secrets: Optional[Iterable[str]] = None,
                     _depth: int = 0) -> Any:
    """
    Return a redacted deep copy of ``value``.

    A dict key that is a declared sensitive input, or whose name matches the
    heuristic, has its value replaced wholesale. Every remaining string is
    additionally swept for the literal secret values (contract 4), which is
    what catches a credential that was interpolated into a message rather
    than stored in its own field.
    """
    if _depth > _MAX_DEPTH:
        return REDACTED_PLACEHOLDER
    try:
        names = set(sensitive_names or ())
        if isinstance(value, dict):
            out: Dict[Any, Any] = {}
            for k, v in value.items():
                if (isinstance(k, str) and (k in names or is_sensitive_name(k))):
                    out[k] = REDACTED_PLACEHOLDER
                else:
                    out[k] = redact_structure(v, names, secrets, _depth + 1)
            return out
        if isinstance(value, (list, tuple)):
            seq = [redact_structure(v, names, secrets, _depth + 1) for v in value]
            return seq if isinstance(value, list) else tuple(seq)
        if isinstance(value, str):
            return scrub_text(value, secrets)
        return value
    except Exception:
        # Fail-SAFE: an unwalkable structure is replaced entirely rather
        # than emitted on the chance that it is clean.
        return REDACTED_PLACEHOLDER


def redact_args(input_decls: Optional[Iterable[Any]],
                args: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Redact a validated argument mapping for audit / envelope serialization.

    This is the call site the harness uses. The UNredacted mapping stays in
    memory for the authorized operation; only this copy is ever written to
    disk or returned to the caller.
    """
    try:
        names = sensitive_input_names(input_decls)
        secrets = collect_secret_values(args, names)
        redacted = redact_structure(args or {}, names, secrets)
        return redacted if isinstance(redacted, dict) else {}
    except Exception:
        return {}
