# Tlamatini Author Banner — Angela López Mendoza
"""Bounded, read-only Ollama usage adapter. Credentials never reach the browser."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import errno
import json
import logging
import math
import socket
import ssl
import threading
import time
from email.utils import parsedate_to_datetime
import urllib.error
import urllib.parse
import urllib.request

from .config_loader import load_config

_CACHE = {}
_LOCK = threading.Lock()
TTL = 60
ERROR_TTL = 15
logger = logging.getLogger(__name__)
METRICS = ("usage_usd", "request_count", "input_tokens", "cached_input_tokens", "output_tokens")


def number(value, *, signed=False):
    if value is None or isinstance(value, bool):
        return None
    try:
        n = Decimal(str(value))
        limit = Decimal("1e18")
        return float(n) if n.is_finite() and (-limit if signed else 0) <= n <= limit else None
    except (ValueError, InvalidOperation):
        return None


def instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def normalize_usage(data):
    if not isinstance(data, dict) or not isinstance(data.get("totals"), dict) or not isinstance(data.get("buckets"), list):
        return None
    daily = []
    for bucket in data["buckets"][:400]:
        if not isinstance(bucket, dict):
            continue
        date = instant(bucket.get("from") or bucket.get("date"))
        if not date:
            continue
        daily.append({"date": date.date().isoformat(), "from": date.isoformat(),
                      "until": bucket.get("until"), "partial": bool(bucket.get("partial")),
                      **{k: number(bucket.get(k)) for k in METRICS}})
    return {"totals": {k: number(data["totals"].get(k)) for k in METRICS},
            "daily": sorted(daily, key=lambda x: x["date"]),
            "from": data.get("from"), "until": data.get("until"),
            "scope": str(data.get("scope", "Account"))[:100]}


def normalize_balance(data):
    """Use /api/balance, never a rolling usage window or a plan-name estimate.

    Contract: https://docs.ollama.com/api/balance (monthly or legacy limits).
    Keep source precision for arithmetic; the UI formats money to two decimals.
    """
    if not isinstance(data, dict):
        return None
    included, purchased = data.get("included"), data.get("purchased")
    if not isinstance(included, dict):
        included = {}
    if not isinstance(purchased, dict):
        purchased = {}
    extra = number(purchased.get("balance_usd"), signed=True)
    remaining, allowance = number(included.get("balance_usd"), signed=True), number(included.get("allowance_usd"))
    period = included.get("period")
    period = period if isinstance(period, dict) else {}
    start, end = instant(period.get("from")), instant(period.get("until"))
    common = {"purchased": extra, "start": start.isoformat() if start else None,
              "end": end.isoformat() if end else None}
    if remaining is not None and allowance is not None and remaining <= allowance:
        used = float(Decimal(str(allowance)) - Decimal(str(remaining)))
        return {**common, "kind": "credits", "allowance": allowance, "monthly_remaining": remaining,
                "used": used, "remaining": float(Decimal(str(remaining)) + Decimal(str(extra))) if extra is not None else None,
                "percent": used / allowance * 100 if allowance else None}
    limits = []
    for label in ("session", "weekly"):
        limit = included.get(label)
        if not isinstance(limit, dict):
            continue
        percent, reset = number(limit.get("remaining_percent")), instant(limit.get("resets_at"))
        if percent is not None and percent <= 100:
            limits.append({"name": label, "remaining_percent": percent,
                           "resets_at": reset.isoformat() if reset else None})
    if limits:
        return {**common, "kind": "legacy", "limits": limits}
    # A purchased-only response carries no claim about included credits.
    if extra is not None and not included:
        return {**common, "kind": "purchased"}
    return None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a saved bearer token to another server.


def _failure(path, kind, message, retry_after=TTL, *, request_not_sent=False):
    # Fixed request paths and failure kinds only: never log tokens, bodies or
    # raw exception text (a proxy can echo credentials in its response).
    logger.warning("[USAGE] %s failed (%s); next attempt in %ss", path, kind, retry_after)
    return {"error": message, "error_kind": kind, "retry_after": retry_after,
            "request_not_sent": request_not_sent}


def _retry_after(headers):
    value = headers.get("Retry-After", "") if headers else ""
    seconds = number(value)
    if seconds is None:
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            seconds = TTL
    return max(TTL, math.ceil(seconds))


def _fetch(base, token, path, method="GET"):
    headers = {"Accept": "application/json"}
    if method == "POST":
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    # /api/me is a bodyless POST in Ollama's own Whoami client. Sending an
    # unused {} body resets the connection on supported Windows servers.
    request = urllib.request.Request(base + path, headers=headers, method=method)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10 if path == '/api/me' else 6) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return _failure(path, "response_size", "Ollama's usage response exceeds the size limit.")
            return {"data": json.loads(raw)}
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            return _failure(path, "rate_limit", "Ollama temporarily limited usage requests.", _retry_after(exc.headers))
        if exc.code in (401, 403):
            return _failure(path, "authentication", "Ollama refused account access. Check its sign-in or configured API key.")
        if exc.code == 404:
            return _failure(path, "unsupported", "This Ollama server does not provide the requested usage endpoint.")
        delay = _retry_after(exc.headers) if (exc.headers or {}).get("Retry-After") else ERROR_TTL if exc.code >= 500 else TTL
        return _failure(path, "http_" + str(exc.code), f"Ollama returned HTTP {exc.code}.", delay)
    except (OSError, ValueError, urllib.error.URLError) as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, ssl.SSLError):
            return _failure(path, "tls", "Ollama's secure connection could not be verified. Check its certificate and connection settings.")
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return _failure(path, "timeout", "Ollama did not respond before the usage request timed out.", ERROR_TTL)
        if isinstance(reason, (ConnectionResetError, ConnectionAbortedError)):
            return _failure(path, "connection_reset", "Ollama closed this usage connection before the response completed. The request will be retried automatically.", ERROR_TTL)
        if isinstance(exc, ValueError):
            return _failure(path, "invalid_json", "Ollama returned an invalid usage response.", ERROR_TTL)
        refused = isinstance(reason, ConnectionRefusedError) or getattr(reason, 'errno', None) in (errno.ECONNREFUSED, 10061)
        return _failure(path, "connection", "Cannot connect to the configured Ollama server. Check that Ollama is running.", ERROR_TTL,
                        request_not_sent=refused)


def _cached_value(entry):
    value = dict(entry.get("value") or {})
    if entry.get("loading"):
        value["pending"] = True
    elif entry.get("failed"):
        value["retry_after_seconds"] = max(1, math.ceil(entry["ttl"] - (time.monotonic() - entry["at"])))
    return value


def connection():
    config = load_config(force_reload=True) or {}
    base = str(config.get("unified_agent_base_url") or config.get("ollama_base_url") or "http://localhost:11434").rstrip("/")
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("The configured Ollama URL is not a supported HTTP address.")
    token = str(config.get("ollama_token") or "").strip()
    if token.startswith("<") and token.endswith(">"):
        token = ""
    key = hashlib.sha256((base + "\0" + token).encode()).hexdigest()
    return base, token, key


def snapshot(*, refresh=False):
    base, token, key = connection()
    now = time.monotonic()
    with _LOCK:
        entry = _CACHE.get(key)
        # Explicit Refresh/reopen may retry an entirely refused connection:
        # no HTTP request reached Ollama, so there is no cloud quota to bypass.
        # Healthy billing and HTTP errors still obey their cache/delay. A
        # transient identity failure can be retried independently on demand.
        retry_refused = refresh and entry and entry.get("refused")
        requests = (entry or {}).get("requests", {})
        account_request = requests.get("account", {})
        retry_account = (refresh and account_request.get("result", {}).get("error_kind")
                         in {"connection", "connection_reset", "timeout", "invalid_json"})
        if entry and (entry.get("loading") or (not retry_refused and not retry_account and now - entry.get("at", 0) < entry.get("ttl", TTL))):
            return _cached_value(entry)
        previous = entry.get("value") if entry else None
        # Bound cached endpoints if config is edited repeatedly.
        if len(_CACHE) >= 8:
            _CACHE.clear()
        _CACHE[key] = {"loading": True, "value": previous or {"pending": True}}
    paths = {"7d": "/api/usage?range=7d", "30d": "/api/usage?range=30d",
             "account": "/api/me", "balance": "/api/balance", "models": "/api/tags", "running": "/api/ps", "version": "/api/version"}
    try:
        # Retry only endpoints whose own delay expired. An account-name outage
        # must not repeat successful billing requests or inherit their delays.
        due = {name: path for name, path in paths.items() if (
            name not in requests or now - requests[name]["at"] >= requests[name]["ttl"]
            or retry_refused or (name == "account" and retry_account))}
        with ThreadPoolExecutor(max_workers=7, thread_name_prefix="UsageRead") as pool:
            jobs = {name: pool.submit(_fetch, base, token, path, "POST" if name == "account" else "GET")
                    for name, path in due.items()}
            requests = dict(requests)
            for name, future in jobs.items():
                result = future.result()
                requests[name] = {"result": result, "at": time.monotonic(),
                                  "checked_at": datetime.now(timezone.utc).isoformat(),
                                  "ttl": result.get("retry_after", TTL) if result.get("error") else TTL}
        results = {name: request["result"] for name, request in requests.items()}
        account = results["account"].get("data") or {}
        if not isinstance(account, dict):
            account = {}
        identity = str(account.get("id") or account.get("email") or account.get("name") or "")
        account_key = hashlib.sha256((key + identity).encode()).hexdigest()
        for name in ("7d", "30d", "balance"):
            if name in due:
                requests[name]["account_key"] = account_key
        if "account" in due:
            # Cached billing responses must never be relabelled as belonging
            # to a newly verified account. Recheck them once after identity
            # recovery/change, while keeping an explicit server Retry-After.
            billing = {name: paths[name] for name in ("7d", "30d", "balance")
                       if name not in due and identity and not results[name].get("error")
                       and requests[name].get("account_key") != account_key}
            with ThreadPoolExecutor(max_workers=3, thread_name_prefix="UsageIdentity") as pool:
                jobs = {name: pool.submit(_fetch, base, token, path, "GET") for name, path in billing.items()}
                for name, future in jobs.items():
                    result = future.result()
                    results[name] = result
                    requests[name] = {"result": result, "at": time.monotonic(),
                                      "checked_at": datetime.now(timezone.utc).isoformat(),
                                      "account_key": account_key,
                                      "ttl": result.get("retry_after", TTL) if result.get("error") else TTL}
            if not identity:
                for name in ("7d", "30d", "balance"):
                    if (name not in due and not results[name].get("error")
                            and requests[name].get("account_key") != account_key):
                        results[name] = {"error": "Account identity could not be verified for the saved figures."}
        if not identity or (previous or {}).get("account_key") != account_key:
            previous = None
        ranges = {}
        for name in ("7d", "30d"):
            parsed = normalize_usage(results[name].get("data"))
            old = (previous or {}).get("ranges", {}).get(name)
            ranges[name] = {"data": parsed or (old or {}).get("data"), "stale": parsed is None,
                            "error": None if parsed else results[name].get("error", "Usage data is not available from this Ollama server."),
                            "updated_at": requests[name]["checked_at"] if parsed else (old or {}).get("updated_at")}
        parsed_balance = normalize_balance(results["balance"].get("data"))
        old_balance = (previous or {}).get("balance") or {}
        balance = {"data": parsed_balance or old_balance.get("data"), "stale": parsed_balance is None,
                   "error": None if parsed_balance else results["balance"].get("error", "Ollama did not return a supported balance. Open Ollama Usage to check your account."),
                   "updated_at": requests["balance"]["checked_at"] if parsed_balance else old_balance.get("updated_at")}
        models_data = results["models"].get("data") or {}
        running_data = results["running"].get("data") or {}
        running = (running_data.get("models") or []) if isinstance(running_data, dict) else []
        if not isinstance(running, list):
            running = []
        names = {m.get("name") for m in running if isinstance(m, dict)}
        models = []
        inventory = (models_data.get("models") or []) if isinstance(models_data, dict) else []
        for m in (inventory if isinstance(inventory, list) else [])[:1000]:
            if not isinstance(m, dict):
                continue
            details = m.get("details") or {}
            if not isinstance(details, dict):
                details = {}
            name = str(m.get("name") or m.get("model") or "").strip()
            if not name:
                continue
            models.append({"name": name[:255],
                           "size": number(m.get("size")), "cloud": bool(m.get("remote_host")),
                           "loaded": m.get("name") in names, "modified_at": m.get("modified_at"),
                           "parameters": str(details.get("parameter_size") or ""),
                           "family": str(details.get("family") or ""),
                           "remote_host": str(m.get("remote_host") or "")[:255],
                           "quantization": str(details.get("quantization_level") or "")})
        version = results["version"].get("data") or {}
        value = {"ranges": ranges, "balance": balance, "account_key": account_key,
                 "account": str(account.get("name") or account.get("email") or "Ollama account")[:200],
                 "plan": str(account.get("plan") or "")[:100],
                 "account_available": bool(identity), "models": models,
                 "account_error": None if identity else results['account'].get('error', 'Account identity was not returned.'),
                 "account_error_kind": results['account'].get('error_kind') if not identity else None,
                 "models_error": results["models"].get("error"),
                 "running_error": results["running"].get("error"),
                 "running": [{"name": str(m.get("name", ""))[:255], "size": number(m.get("size")),
                              "expires_at": m.get("expires_at")} for m in running if isinstance(m, dict)][:1000],
                 "version": str(version.get("version", ""))[:50] if isinstance(version, dict) else "",
                 "endpoint": base,
                 "checked_at": datetime.now(timezone.utc).isoformat()}
        failures = [result for result in results.values() if result.get("error")]
        failed = bool(failures or balance["stale"] or any(r["stale"] for r in ranges.values()) or not identity)
        # Short negative caching recovers from an Ollama startup/outage without
        # making Refresh repeat a one-minute-old failure. At 15 seconds the two
        # usage ranges remain below their shared 10 requests/minute limit.
        # Retry-After always wins; healthy snapshots retain the normal minute.
        finished = time.monotonic()
        ttl = max(0, min(request["at"] + request["ttl"] for request in requests.values()) - finished)
        refused = len(failures) == len(results) and all(result.get("request_not_sent") for result in failures)
        entry = {"at": finished, "ttl": ttl, "failed": failed, "refused": refused,
                 "value": value, "requests": requests}
        with _LOCK:
            _CACHE[key] = entry
        return _cached_value(entry)
    except Exception:
        with _LOCK:
            _CACHE.pop(key, None)
        raise

