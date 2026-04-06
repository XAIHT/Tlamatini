import threading
from contextlib import contextmanager
from contextvars import ContextVar

class GlobalState:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GlobalState, cls).__new__(cls)
                cls._instance._state = {}
        return cls._instance

    def set_state(self, key, value):
        with self._lock:
            self._state[key] = value

    def get_state(self, key, default=None):
        with self._lock:
            return self._state.get(key, default)


_request_state_var: ContextVar[dict | None] = ContextVar('agent_request_state', default=None)


def get_request_state(key, default=None):
    state = _request_state_var.get() or {}
    return state.get(key, default)


@contextmanager
def scoped_request_state(**values):
    current_state = dict(_request_state_var.get() or {})
    current_state.update(values)
    token = _request_state_var.set(current_state)
    try:
        yield current_state
    finally:
        _request_state_var.reset(token)


global_state = GlobalState()
