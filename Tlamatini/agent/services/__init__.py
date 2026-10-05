# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# Pure format validators are also used before Django starts (Explorer opening).
# Load the DB-backed public helpers only when callers actually request them.
def __getattr__(name):
    if name in ('generate_tree_view_content', 'save_files_from_db'):
        from . import filesystem
        return getattr(filesystem, name)
    if name == 'process_llm_response':
        from .response_parser import process_llm_response
        return process_llm_response
    raise AttributeError(name)

__all__ = [
    'generate_tree_view_content',
    'save_files_from_db',
    'process_llm_response'
]
