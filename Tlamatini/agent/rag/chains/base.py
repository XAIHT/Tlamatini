# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from typing import Optional, Dict, Any
from langchain_core.callbacks import BaseCallbackHandler
from ...global_state import global_state
from ...context_governor import measure_async as _context_measure_async


class GenerationCancelledException(Exception):
    """Exception raised when generation is cancelled by user."""
    pass


class Callbacks(BaseCallbackHandler):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.cancelled = False

    def on_llm_new_token(self, token, **kwargs):
        # Check for cancellation on EVERY token - this is the key to fast cancellation
        if global_state.get_state('cancel_generation'):
            self.cancelled = True
            print("\n--- [CANCEL] Generation cancelled by user during streaming ---")
            raise GenerationCancelledException("Generation cancelled by user")
        print(token, end='', flush=True)

    def on_llm_start(self, *args, **kwargs):
        # Check before starting
        if global_state.get_state('cancel_generation'):
            self.cancelled = True
            raise GenerationCancelledException("Generation cancelled before start")

    def on_chat_model_start(self, serialized, messages, **kwargs):
        """EVERY chat-model call in EVERY chain passes through here.

        This is the One-Shot / RAG counterpart of the Multi-Turn executor's
        ``_model_step``. LangChain hands us the REAL messages it is about to
        send, so the context gauge now updates for a plain One-Shot question
        too - it never did before, and the ring simply sat frozen on whatever
        the last Multi-Turn request had left there (Angela, 2026-09-21).

        SNAPSHOT AND SIGNAL ONLY. The meter's worker thread does the
        arithmetic; nothing here is allowed to cost the user latency, and the
        whole body is guarded because a gauge must never break an answer.

        NOTE: this deliberately does NOT repeat ``on_llm_start``'s cancellation
        check. Changing when a generation can be cancelled is a separate
        decision from measuring it, and must not ride in on this change.
        """
        try:
            batch = messages
            if isinstance(messages, (list, tuple)) and messages and \
                    isinstance(messages[0], (list, tuple)):
                batch = messages[0]          # List[List[BaseMessage]]
            _context_measure_async(
                None,                        # the request bound the user id
                batch,
                label=(self.config or {}).get('label') or 'answering',
                source='one-shot',
                prefix_message_count=1,
            )
        except Exception:  # noqa: BLE001 - the gauge owes the answer nothing
            pass

    def on_llm_end(self, *args, **kwargs):
        # Reset cancelled state
        self.cancelled = False
