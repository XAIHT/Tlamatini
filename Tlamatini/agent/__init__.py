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


