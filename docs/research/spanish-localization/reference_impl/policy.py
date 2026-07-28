"""Conversation-sticky language routing with hysteresis.

REFERENCE IMPLEMENTATION -- not wired into Tlamatini. See PAPER.md section 7.8
and DESIGN.md section 5.

WHY HYSTERESIS IS NOT OPTIONAL
------------------------------
A per-message detector with no memory oscillates, and the oscillation is
user-triggerable inside one ordinary conversation::

    turn 3  "ok"                        -> too short          -> und
    turn 4  "y ahora el log"            -> es
    turn 5  "chat_agent_grepper ..."    -> no prose after mask -> und

If 'und' falls back to the UI language, the conversation alternates
ES/EN/ES/EN. That produces a mixed-language history, which then degrades the
history-aware chain AND the question rewriter -- and if the language were
allowed to change the CHAIN's prompt, each flip would trigger a full
FAISS/BM25 rebuild on the request path.

Two rules remove the whole failure class:

  1. 'und' INHERITS the conversation language. It never falls back to the UI.
  2. A switch requires N consecutive confident turns of sufficient length,
     or an explicit user action.

And one architectural rule removes the rebuild entirely: the chain-level
prompt block is LOCALE-INDEPENDENT (a mirroring rule); the concrete language
rides only in a per-request SystemMessage. ``chain_rebuild_required`` therefore
does not exist in this design.

ROUTE IS A VECTOR, NOT A SCALAR
-------------------------------
A model may write excellent Spanish prose and still mangle a
``chat_agent_stm32er`` argument list. One scalar cannot express that, so the
decision carries ``qa_route`` and ``operator_route`` separately, and the tier
is PINNED at conversation start so turn 1 and turn 2 never run two different
generation architectures.

Stdlib only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Callable, Optional, Sequence

__all__ = [
    "LangSettings",
    "ProbeVerdict",
    "ConversationLanguageState",
    "LanguageDecision",
    "decide",
]

# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LangSettings:
    """Resolved from config.json by langconfig.py. Every field has a default,
    so a PRESERVED old config.json (which will not gain the new keys after a
    self-update) behaves exactly like a fresh one."""

    ui_language: str = "en"
    answer_language_mode: str = "mirror_user"   # english|match_ui|mirror_user|forced
    answer_language_forced: str = ""
    available_languages: Sequence[str] = ("en", "es")
    detection_enabled: bool = True
    detection_min_chars: int = 12
    detection_confidence_min: float = 0.35      # CALIBRATED, see DESIGN 6.2
    hysteresis_turns: int = 2
    probe_enabled: bool = True


@dataclass(frozen=True)
class ProbeVerdict:
    """What the out-of-band prober measured for one (model, language)."""

    model_id: str
    lang: str
    qa_route: str = "english"        # native | scaffold | english
    operator_route: str = "english"  # native | scaffold | english | unmeasured
    sentinels_ok: bool = False
    checked_at: float = 0.0
    ttl_seconds: float = 604800.0
    suite_version: str = ""

    def stale(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        return (now - self.checked_at) > self.ttl_seconds


@dataclass
class ConversationLanguageState:
    """Per-conversation memory. Lives beside the chat session, not per message."""

    language: str = ""            # resolved language; '' until first resolution
    pending: str = ""             # candidate language being counted toward a switch
    pending_count: int = 0
    pinned_qa_route: str = ""     # route tier frozen at conversation start
    pinned_operator_route: str = ""
    turns: int = 0
    history: list = field(default_factory=list)


@dataclass(frozen=True)
class LanguageDecision:
    ui_lang: str
    answer_lang: str
    qa_route: str
    operator_route: str
    mode: str
    detected: str
    detect_confidence: float
    switched: bool
    reason: str


# ---------------------------------------------------------------------------
# The decision
# ---------------------------------------------------------------------------


def decide(
    text: str,
    state: ConversationLanguageState,
    settings: LangSettings = LangSettings(),
    detect_fn: Optional[Callable[..., object]] = None,
    verdict_lookup: Optional[Callable[[str], Optional[ProbeVerdict]]] = None,
    explicit_language: str = "",
    user_ui_language: str = "",
) -> LanguageDecision:
    """Resolve the language for ONE request, mutating ``state`` in place.

    ``detect_fn(text) -> object`` must expose ``.lang`` and ``.confidence``
    (the sibling ``detector.detect`` does). ``verdict_lookup(lang)`` returns the
    cached ProbeVerdict, or None when the model has never been probed.

    FAIL-OPEN CONTRACT, and note the asymmetry, which is deliberate:

      * NEVER-PROBED (verdict is None)  -> HONOUR the user's language, arm the
        read-only guard, and surface a one-line "verifying support" notice.
        A silent permanent English downgrade because a cache file is missing is
        a capability denial, not a safe default.
      * PROBE ACTUALLY FAILED           -> English, with an explicit reason the
        UI can show, plus a model-switch suggestion.
      * SENTINELS FAILED                -> operator_route is forced to English
        even when the prose route is native. This gate is non-negotiable: a
        mangled INI_SECTION or VERDICT token corrupts downstream routing
        silently.
    """
    state.turns += 1
    ui = (user_ui_language or settings.ui_language or "en").strip() or "en"
    if ui not in settings.available_languages:
        ui = "en"

    mode = settings.answer_language_mode or "mirror_user"
    detected, confidence, switched = "und", 0.0, False
    reason = mode

    # ---- 1. explicit user action always wins, immediately -------------------
    if explicit_language:
        target = explicit_language if explicit_language in settings.available_languages else "en"
        switched = target != state.language
        state.language = target
        state.pending, state.pending_count = "", 0
        reason = "explicit"

    # ---- 2. otherwise apply the mode ---------------------------------------
    elif mode == "english":
        state.language = "en"
        reason = "mode_english"
    elif mode == "forced":
        state.language = (
            settings.answer_language_forced
            if settings.answer_language_forced in settings.available_languages
            else "en"
        )
        reason = "mode_forced"
    elif mode == "match_ui":
        state.language = ui
        reason = "mode_match_ui"
    else:  # mirror_user -- the only mode that runs detection
        if settings.detection_enabled and detect_fn is not None:
            try:
                det = detect_fn(text)
                detected = getattr(det, "lang", "und") or "und"
                confidence = float(getattr(det, "confidence", 0.0) or 0.0)
            except Exception:
                detected, confidence = "und", 0.0

        strong = (
            detected in settings.available_languages
            and confidence >= settings.detection_confidence_min
            and len((text or "").strip()) >= settings.detection_min_chars
        )

        if not state.language:
            # First resolution of the conversation.
            state.language = detected if strong else ui
            reason = "first_turn_detect" if strong else "first_turn_ui"
        elif not strong:
            # RULE 1: 'und' inherits. It must NEVER fall back to the UI.
            state.pending, state.pending_count = "", 0
            reason = "inherit_und"
        elif detected == state.language:
            state.pending, state.pending_count = "", 0
            reason = "stable"
        else:
            # RULE 2: a switch needs N consecutive confident turns.
            if state.pending == detected:
                state.pending_count += 1
            else:
                state.pending, state.pending_count = detected, 1
            if state.pending_count >= max(1, settings.hysteresis_turns):
                state.language = detected
                state.pending, state.pending_count = "", 0
                switched = True
                reason = "hysteresis_switch"
            else:
                reason = (
                    f"pending_switch:{detected}"
                    f"[{state.pending_count}/{settings.hysteresis_turns}]"
                )

    answer_lang = state.language or "en"

    # ---- 3. capability gate, with the route PINNED at conversation start ----
    qa_route, operator_route = "native", "native"
    if answer_lang != "en" and settings.probe_enabled:
        if state.pinned_qa_route:
            qa_route = state.pinned_qa_route
            operator_route = state.pinned_operator_route
            reason += "|pinned"
        else:
            verdict = None
            if verdict_lookup is not None:
                try:
                    verdict = verdict_lookup(answer_lang)
                except Exception:
                    verdict = None

            if verdict is None:
                # Never probed: honour the user, arm the guard, tell them.
                qa_route, operator_route = "native", "scaffold"
                reason += "|unprobed_honour_user"
            elif verdict.stale():
                qa_route, operator_route = "native", "scaffold"
                reason += "|stale_verdict"
            else:
                qa_route = verdict.qa_route
                operator_route = verdict.operator_route
                if not verdict.sentinels_ok:
                    # HARD GATE.
                    operator_route = "english"
                    reason += "|sentinel_gate"

            state.pinned_qa_route = qa_route
            state.pinned_operator_route = operator_route
    else:
        qa_route = operator_route = "native" if answer_lang == "en" else qa_route

    state.history.append((state.turns, detected, round(confidence, 3), answer_lang))
    return LanguageDecision(
        ui_lang=ui,
        answer_lang=answer_lang,
        qa_route=qa_route,
        operator_route=operator_route,
        mode=mode,
        detected=detected,
        detect_confidence=round(confidence, 4),
        switched=switched,
        reason=reason,
    )


def _demo() -> None:  # pragma: no cover - developer aid
    try:
        from detector import detect as _detect
    except ImportError:  # running from another cwd
        from .detector import detect as _detect  # type: ignore

    settings = LangSettings(hysteresis_turns=2, detection_confidence_min=0.20)
    verdict = ProbeVerdict(
        model_id="glm-5.2:cloud", lang="es",
        qa_route="native", operator_route="native",
        sentinels_ok=True, checked_at=time.time(), ttl_seconds=604800,
    )

    turns = [
        "Necesito que revises los archivos temporales de la carpeta y me digas cuantos hay",
        "ok",
        "y ahora el log",
        "chat_agent_grepper pattern='TODO'",
        "gracias, ahora dime cuanto espacio ocupan todos esos archivos en disco",
        "Now switch me to English please and summarise everything you just did",
        "Yes, do that and also tell me which of those files are the largest ones",
    ]

    print("--- WITH hysteresis (this design) ---")
    st = ConversationLanguageState()
    for t in turns:
        d = decide(t, st, settings, detect_fn=_detect,
                   verdict_lookup=lambda _l: verdict)
        print(f"  turn {st.turns}: detected={d.detected:<4} "
              f"-> answer={d.answer_lang:<3} switched={str(d.switched):<5} "
              f"[{d.reason}]")

    print("\n--- WITHOUT hysteresis (naive per-message, for contrast) ---")
    naive = []
    for t in turns:
        det = _detect(t)
        naive.append(det.lang if det.lang in ("en", "es") else "en(ui-fallback)")
    print("  " + " -> ".join(naive))
    print("\n  The naive column is the ES/EN/ES/EN flapping that mixes the\n"
          "  conversation history and, if the language touched the chain,\n"
          "  would rebuild FAISS/BM25 on alternating turns.")

    print("\n--- fail-open matrix ---")
    for label, lookup in (
        ("never probed", lambda _l: None),
        ("stale verdict", lambda _l: replace(verdict, checked_at=0.0)),
        ("sentinels failed", lambda _l: replace(verdict, sentinels_ok=False)),
    ):
        st2 = ConversationLanguageState()
        d = decide(turns[0], st2, settings, detect_fn=_detect,
                   verdict_lookup=lookup)
        print(f"  {label:<18} answer={d.answer_lang} qa={d.qa_route:<9} "
              f"operator={d.operator_route:<9} [{d.reason}]")


if __name__ == "__main__":  # pragma: no cover
    _demo()
