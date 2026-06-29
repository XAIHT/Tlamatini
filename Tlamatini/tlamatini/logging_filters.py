# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
import logging


class SuppressHttpGet200(logging.Filter):
    """Drop daphne's per-request access log line for any HTTP GET that
    returned 200. Non-200 GETs (4xx, 5xx, redirects) and non-GET methods
    still log normally so signal is preserved when something actually
    goes wrong."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, dict):
            return True
        method = str(args.get("method", "")).upper()
        if method != "GET":
            return True
        status = args.get("status")
        try:
            status_int = int(status) if status is not None else None
        except (TypeError, ValueError):
            return True
        return status_int != 200
