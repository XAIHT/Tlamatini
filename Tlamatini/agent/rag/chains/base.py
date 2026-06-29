# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from typing import Optional, Dict, Any
from langchain_core.callbacks import BaseCallbackHandler
from ...global_state import global_state


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

    def on_llm_end(self, *args, **kwargs):
        # Reset cancelled state
        self.cancelled = False
