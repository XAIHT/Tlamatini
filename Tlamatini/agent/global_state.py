import threading

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

global_state = GlobalState()
