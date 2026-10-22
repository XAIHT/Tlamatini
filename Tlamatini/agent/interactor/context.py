# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""The originating tab is request-scoped, never a global 'active editor'."""
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class Request:
    owner: tuple[str, str]
    client_id: str
    user_id: int
    run_epoch: int
    handed_off: bool = False
    stop_version: int | None = None
    document_id: str = ""
    revision: int = -1


current: ContextVar[Request | None] = ContextVar("interactor_request", default=None)


def bind(scope, client_id, run_epoch):
    scope = scope or {}
    user = scope.get("user")
    session_key = getattr(scope.get("session"), "session_key", None)
    request = None
    if user and user.is_authenticated and session_key and isinstance(client_id, str) and len(client_id) <= 96:
        request = Request((str(user.pk), session_key), client_id, user.pk, run_epoch)
    return current.set(request)


def cancelled(request):
    from ..cancellation import is_generation_cancelled
    return is_generation_cancelled(request.user_id, request.run_epoch)

