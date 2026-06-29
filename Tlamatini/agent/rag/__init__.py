# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from .factory import setup_llm, setup_llm_with_context
from .interface import (
    ask_rag,
    tokenCounterOfAsk,
    is_valid_prompt,
    get_program_by_name,
    request_cancel_generation,
    clear_cancel_generation
)
from .chains.base import Callbacks
from .chains.basic import BasicPromptOnlyChain
from .chains.history_aware import HistoryAwareNoDocsChain, OptimizedHistoryAwareRAGChain
from .chains.unified import UnifiedAgentChain, UnifiedAgentRAGChain

__all__ = [
    'setup_llm',
    'setup_llm_with_context',
    'ask_rag',
    'tokenCounterOfAsk',
    'is_valid_prompt',
    'get_program_by_name',
    'request_cancel_generation',
    'clear_cancel_generation',
    'Callbacks',
    'BasicPromptOnlyChain',
    'HistoryAwareNoDocsChain',
    'OptimizedHistoryAwareRAGChain',
    'UnifiedAgentChain',
    'UnifiedAgentRAGChain'
]
