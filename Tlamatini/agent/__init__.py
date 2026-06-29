# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import sys as _sys

# Ensure absolute imports for generated protobuf modules resolve when code
# tries to import them as top-level names.
try:
    from . import filesearch_pb2 as _filesearch_pb2
    _sys.modules.setdefault('filesearch_pb2', _filesearch_pb2)
except Exception:
    pass

try:
    from . import filesearch_pb2_grpc as _filesearch_pb2_grpc
    _sys.modules.setdefault('filesearch_pb2_grpc', _filesearch_pb2_grpc)
except Exception:
    pass


