import logging


_RUNTIME_POLLER_PATH = "/agent/check_chat_runtimes_status/"


class SuppressRuntimePollerOk(logging.Filter):
    """Drop daphne's per-request access log line for the chat-runtime status
    poller when it returns HTTP 200. Non-200 responses still log normally."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, dict):
            if args.get("path") == _RUNTIME_POLLER_PATH and args.get("status") == 200:
                return False
        return True
