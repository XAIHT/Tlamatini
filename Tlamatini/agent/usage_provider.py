# Tlamatini Author Banner — Angela López Mendoza
"""Bounded, read-only Ollama usage adapter. Credentials never reach the browser."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .config_loader import load_config

_CACHE = {}
_LOCK = threading.Lock()
TTL = 60
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


def _fetch(base, token, path, method="GET"):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + path, headers=headers, method=method,
                                     data=b"{}" if method == "POST" else None)
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=10 if path == '/api/me' else 6) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {"error": "Response exceeds the usage size limit."}
            return {"data": json.loads(raw)}
    except urllib.error.HTTPError as exc:
        return {"error": f"Ollama returned HTTP {exc.code}."}
    except (OSError, ValueError, urllib.error.URLError):
        return {"error": "Ollama is unavailable or returned invalid data."}


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


def snapshot():
    base, token, key = connection()
    with _LOCK:
        entry = _CACHE.get(key)
        if entry and (entry.get("loading") or time.monotonic() - entry.get("at", 0) < TTL):
            return entry.get("value", {"pending": True})
        previous = entry.get("value") if entry else None
        # Bound cached endpoints if config is edited repeatedly.
        if len(_CACHE) >= 8:
            _CACHE.clear()
        _CACHE[key] = {"loading": True, "value": previous or {"pending": True}}
    paths = {"7d": "/api/usage?range=7d", "30d": "/api/usage?range=30d",
             "account": "/api/me", "balance": "/api/balance", "models": "/api/tags", "running": "/api/ps", "version": "/api/version"}
    try:
        with ThreadPoolExecutor(max_workers=7, thread_name_prefix="UsageRead") as pool:
            jobs = {name: pool.submit(_fetch, base, token, path, "POST" if name == "account" else "GET")
                    for name, path in paths.items()}
            results = {name: future.result() for name, future in jobs.items()}
        account = results["account"].get("data") or {}
        if not isinstance(account, dict):
            account = {}
        identity = str(account.get("id") or account.get("email") or account.get("name") or "")
        account_key = hashlib.sha256((key + identity).encode()).hexdigest()
        if not identity or (previous or {}).get("account_key") != account_key:
            previous = None
        ranges = {}
        for name in ("7d", "30d"):
            parsed = normalize_usage(results[name].get("data"))
            old = (previous or {}).get("ranges", {}).get(name)
            ranges[name] = {"data": parsed or (old or {}).get("data"), "stale": parsed is None,
                            "error": None if parsed else results[name].get("error", "Usage data is not available from this Ollama server."),
                            "updated_at": datetime.now(timezone.utc).isoformat() if parsed else (old or {}).get("updated_at")}
        parsed_balance = normalize_balance(results["balance"].get("data"))
        old_balance = (previous or {}).get("balance") or {}
        balance = {"data": parsed_balance or old_balance.get("data"), "stale": parsed_balance is None,
                   "error": None if parsed_balance else results["balance"].get("error", "Ollama did not return a supported balance. Open Ollama Usage to check your account."),
                   "updated_at": datetime.now(timezone.utc).isoformat() if parsed_balance else old_balance.get("updated_at")}
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
                 "models_error": results["models"].get("error"),
                 "running_error": results["running"].get("error"),
                 "running": [{"name": str(m.get("name", ""))[:255], "size": number(m.get("size")),
                              "expires_at": m.get("expires_at")} for m in running if isinstance(m, dict)][:1000],
                 "version": str(version.get("version", ""))[:50] if isinstance(version, dict) else "",
                 "endpoint": base,
                 "checked_at": datetime.now(timezone.utc).isoformat()}
        with _LOCK:
            _CACHE[key] = {"at": time.monotonic(), "value": value}
        return value
    except Exception:
        with _LOCK:
            _CACHE.pop(key, None)
        raise

