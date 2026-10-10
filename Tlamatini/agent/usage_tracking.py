# Tlamatini Author Banner — Angela López Mendoza
"""Metadata-only usage ledger; no prompts, responses or credentials are stored."""
import logging
from datetime import timedelta, timezone as dt_timezone
import queue
import threading

from django.db import close_old_connections, transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import UsageDaily

logger = logging.getLogger(__name__)
_QUEUE = queue.Queue(maxsize=2048)
_WORKER_LOCK = threading.Lock()
_WORKER = None
_FAILURES = 0


def enqueue_usage(**counts):
    """Do not block inference (including async callers) on a database write."""
    global _WORKER, _FAILURES
    with _WORKER_LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_write_pending, name="UsageLedger", daemon=True)
            _WORKER.start()
    try:
        _QUEUE.put_nowait(counts)
    except queue.Full:
        _FAILURES += 1
        logger.error("[USAGE] Ledger queue is full; one measured call could not be saved")


def _write_pending():
    while True:
        counts = _QUEUE.get()
        try:
            close_old_connections()
            record_usage(**counts)
        finally:
            close_old_connections()
            _QUEUE.task_done()


def record_usage(*, user_id, model, input_tokens, output_tokens, **_kwargs):
    """Called once per completed measured chat call, before the gauge publishes."""
    global _FAILURES
    now = timezone.now()
    key = {"user_id": user_id, "model": str(model or "Model name not reported")[:255],
           "day": now.astimezone(dt_timezone.utc).date()}
    increments = {"calls": 1, "input_tokens": input_tokens,
                  "output_tokens": output_tokens or 0,
                  "missing_output_calls": int(output_tokens is None)}
    try:
        with transaction.atomic():
            row, _ = UsageDaily.objects.get_or_create(**key, defaults={"first_seen": now})
            UsageDaily.objects.filter(pk=row.pk).update(
                **{k: F(k) + v for k, v in increments.items()}, last_seen=now)
    except Exception:
        # Accounting must never interrupt an answer, but failure must be visible.
        _FAILURES += 1
        logger.exception("[USAGE] Could not persist measured chat usage for user %s", user_id)


def activity(user_id, days, now=None):
    now = now or timezone.now()
    today = now.astimezone(dt_timezone.utc).date()
    start = today - timedelta(days=days - 1)
    all_rows = UsageDaily.objects.filter(user_id=user_id)
    rows = all_rows.filter(day__gte=start, day__lte=today)
    fields = ("calls", "input_tokens", "output_tokens", "missing_output_calls")
    aggregates = {k: Sum(k) for k in fields}
    totals = {k: v or 0 for k, v in rows.aggregate(**aggregates).items()}
    daily = {r["day"]: r for r in rows.values("day").annotate(**aggregates)}
    series = []
    for i in range(days):
        day = start + timedelta(days=i)
        series.append({"date": day.isoformat(), **{
            k: daily.get(day, {}).get(k, 0) for k in fields}})
    first = all_rows.order_by("first_seen").values_list("first_seen", flat=True).first()
    models = list(rows.values("model").annotate(**aggregates).order_by("-input_tokens", "model"))
    peaks = {}
    for row in rows.order_by("-calls", "day").values("model", "day", "calls"):
        peaks.setdefault(row["model"], {"peak_day": row["day"].isoformat(), "peak_calls": row["calls"]})
    for model in models:
        model.update(peaks[model["model"]])
    return {"totals": totals, "daily": series, "models": models,
            "pending": _QUEUE.unfinished_tasks, "recording_failures": _FAILURES,
            "since": first.isoformat() if first else None,
            "scope": "Measured Tlamatini chat calls for your user. External apps, child agents, "
                     "unmeasured calls and older history are not included. Dates are UTC."}
