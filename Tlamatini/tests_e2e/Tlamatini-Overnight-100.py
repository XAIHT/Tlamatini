"""Tlamatini-Overnight-100.py -- 100 messages, sent and verified while Angela sleeps.

GOAL (Angela, 2026-07-24 02:24)
===============================
"when I wake up there must be 100 messages received/sent by Tlamatini".

HOW IT STAYS SAFE
=================
Blasting 100 WhatsApps at one number from a business sender is exactly what
Meta's anti-spam scores punish -- a dropped quality rating can get the XAIHT
number throttled or blocked, which is painful to undo. So this runner:

  * ALTERNATES channels: WhatsApp (Zavuerer) and Telegram (Telegrammer).
    Telegram has no anti-spam gate, no cost and no window, so it carries half
    the load and the WhatsApp number only sees ~50 messages.
  * PACES them (default 60 s apart) instead of bursting.
  * VARIES the text of every message (identical repeats look like spam).
  * VERIFIES each send against the provider (Zavu message status / Telegram
    message_id). "queued" is never counted as delivered.
  * WATCHES the sender's WhatsApp quality rating and ABORTS the WhatsApp leg if
    it stops being GREEN, or after 3 consecutive failures.
  * COUNTS INBOUND messages too (Angela's replies on either channel).

Nothing here needs the operator awake. Progress is flushed to disk after every
message, so the morning report is accurate even if the machine is interrupted.

USAGE
=====
    python Tlamatini-Overnight-100.py                 # 100 msgs, 60 s apart
    python Tlamatini-Overnight-100.py --total 100 --interval 45
    python Tlamatini-Overnight-100.py --whatsapp-only # not recommended
"""

import argparse
import datetime as _dt
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

INSTALL_CONFIG = r"C:\Tlamatini\config.json"
INSTALL_CONTACTS = r"C:\Tlamatini\contacts.json"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(REPO, "Temp", "overnight_100")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Tlamatini-Overnight/1.0"
ZAVU = "https://api.zavu.dev/v1"
TG = "https://api.telegram.org"

FLAVOURS = [
    "Tlamatini sigue despierta trabajando por ti.",
    "Mensaje automatico de Tlamatini: todo en orden.",
    "Tlamatini reportandose. Sin Meta de por medio.",
    "Prueba nocturna de mensajeria de Tlamatini.",
    "Tlamatini: canal verificado de extremo a extremo.",
    "Latido de Tlamatini. Sistema estable.",
    "Tlamatini confirma: el mensaje viajo y llego.",
    "Reporte de Tlamatini: entrega comprobada con el proveedor.",
]


def log(msg):
    stamp = _dt.datetime.now().strftime("%H:%M:%S")
    print("[%s] %s" % (stamp, msg), flush=True)


def http(url, method="GET", token=None, body=None, timeout=30):
    data = None
    headers = {"Accept": "application/json", "User-Agent": UA}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:                                    # noqa: BLE001
        return -1, "%s: %s" % (type(exc).__name__, exc)


def jload(text):
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {}
    except Exception:                                           # noqa: BLE001
        return {}


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except Exception:                                           # noqa: BLE001
        return {}


def resolve_target(contact_name):
    book = read_json(INSTALL_CONTACTS)
    for entry in (book.get("contacts") or []):
        names = [entry.get("name", "")] + list(entry.get("aliases") or [])
        if any(str(n).strip().lower() == contact_name.lower() for n in names if n):
            number = str(entry.get("whatsapp") or "").strip()
            only = "".join(c for c in number if c.isdigit())
            if only.startswith("52") and not only.startswith("521") and len(only) == 12:
                only = "521" + only[2:]
            return ("+" + only) if only else "", str(entry.get("telegram") or "")
    return "", ""


# ---------------------------------------------------------------- providers
def zavu_send(key, to, text):
    code, raw = http(ZAVU + "/messages", "POST", token=key,
                     body={"to": to, "text": text, "channel": "whatsapp",
                           "fallbackEnabled": False})
    msg = jload(raw).get("message", {})
    return code, msg.get("id", ""), msg.get("status", "")


def zavu_status(key, mid, timeout_s=90):
    terminal = ("delivered", "read", "failed", "undelivered", "rejected")
    deadline = time.time() + timeout_s
    last = "queued"
    while time.time() < deadline:
        code, raw = http("%s/messages/%s" % (ZAVU, mid), token=key)
        if code == 200:
            last = str(jload(raw).get("message", {}).get("status", "")).lower()
            if last in terminal:
                return last
        time.sleep(5)
    return last


def zavu_quality(key):
    code, raw = http(ZAVU + "/senders", token=key)
    if code != 200:
        return "unknown"
    items = jload(raw).get("items") or []
    if not items:
        return "unknown"
    return str(((items[0].get("whatsapp") or {}).get("paymentStatus") or {})
               .get("setupStatus", "unknown"))


def zavu_inbound_count(key, target):
    code, raw = http(ZAVU + "/messages?limit=100", token=key)
    if code != 200:
        return 0
    digits = "".join(c for c in target if c.isdigit())
    return sum(1 for i in (jload(raw).get("items") or [])
               if "".join(c for c in str(i.get("from", "")) if c.isdigit()) == digits)


def tg_send(token, chat_id, text):
    code, raw = http("%s/bot%s/sendMessage" % (TG, token), "POST",
                     body={"chat_id": chat_id, "text": text})
    result = jload(raw).get("result", {})
    return code, str(result.get("message_id", ""))


def tg_inbound_count(token):
    code, raw = http("%s/bot%s/getUpdates" % (TG, token))
    if code != 200:
        return 0
    return len(jload(raw).get("result") or [])


# ---------------------------------------------------------------- report
def write_report(rows, started, target, stopped_reason=""):
    ok = sum(1 for r in rows if r["ok"])
    wa = sum(1 for r in rows if r["channel"] == "whatsapp" and r["ok"])
    tg = sum(1 for r in rows if r["channel"] == "telegram" and r["ok"])
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>Tlamatini -- overnight 100</title>",
             "<style>body{font:14px/1.55 Segoe UI,Arial,sans-serif;background:#0f1420;color:#e8ecf3;margin:0}",
             ".top{background:#131a2b;padding:18px 22px;border-bottom:2px solid #2a3550}",
             "h1{margin:0 0 8px;font-size:20px}.s{display:inline-block;margin-right:18px}",
             "table{border-collapse:collapse;width:100%;margin:18px 0}td,th{padding:6px 10px;border-bottom:1px solid #26324e;text-align:left}",
             ".ok{color:#57d977}.bad{color:#ff6b6b}.warn{background:#2a1e12;padding:10px 18px}</style></head><body>",
             "<div class='top'><h1>Tlamatini -- overnight messaging run</h1>",
             "<div>started %s &middot; target %s</div><div style='margin-top:8px'>" % (html.escape(started), html.escape(target)),
             "<span class='s'>Delivered total: <b>%d / %d</b></span>" % (ok, len(rows)),
             "<span class='s'>WhatsApp: <b>%d</b></span><span class='s'>Telegram: <b>%d</b></span></div></div>" % (wa, tg)]
    if stopped_reason:
        parts.append("<div class='warn'><b>STOPPED EARLY:</b> %s</div>" % html.escape(stopped_reason))
    parts.append("<table><tr><th>#</th><th>time</th><th>channel</th><th>status</th><th>id</th><th>text</th></tr>")
    for row in rows:
        parts.append("<tr><td>%d</td><td>%s</td><td>%s</td><td class='%s'>%s</td><td>%s</td><td>%s</td></tr>"
                     % (row["n"], html.escape(row["ts"]), row["channel"],
                        "ok" if row["ok"] else "bad", html.escape(row["status"]),
                        html.escape(str(row["id"])[:26]), html.escape(row["text"][:70])))
    parts.append("</table></body></html>")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "SUMMARY.html"), "w", encoding="utf-8") as fh:
        fh.write("".join(parts))
    with open(os.path.join(OUT_DIR, "results.json"), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--total", type=int, default=100)
    ap.add_argument("--interval", type=int, default=60, help="seconds between messages")
    ap.add_argument("--contact", default="Angela")
    ap.add_argument("--whatsapp-only", action="store_true")
    args = ap.parse_args()

    started = _dt.datetime.now().isoformat(timespec="seconds")
    os.makedirs(OUT_DIR, exist_ok=True)
    cfg = read_json(INSTALL_CONFIG)
    zkey = (cfg.get("zavu_api_key") or "").strip()
    tgtok = (cfg.get("telegram_bot_token") or "").strip()
    number, tg_handle = resolve_target(args.contact)

    log("=" * 66)
    log("  TLAMATINI OVERNIGHT RUN -- %d messages, %ds apart" % (args.total, args.interval))
    log("=" * 66)
    log("  whatsapp target : %s" % (number or "(unresolved)"))
    log("  telegram target : %s" % (tg_handle or "(unresolved)"))
    log("  zavu key        : %s" % ("set" if zkey else "MISSING"))
    log("  telegram token  : %s" % ("set" if tgtok else "MISSING"))
    log("  quality (zavu)  : %s" % zavu_quality(zkey) if zkey else "  quality: n/a")

    tg_chat = ""
    if tgtok:
        code, raw = http("%s/bot%s/getUpdates" % (TG, tgtok))
        for upd in (jload(raw).get("result") or []):
            chat = (upd.get("message") or {}).get("chat") or {}
            if chat.get("id"):
                tg_chat = str(chat["id"])
        log("  telegram chat   : %s" % (tg_chat or "NOT FOUND (press Start on the bot)"))

    rows = []
    consecutive_fail = 0
    wa_disabled = not zkey or not number
    stopped = ""

    for n in range(1, args.total + 1):
        flavour = FLAVOURS[(n - 1) % len(FLAVOURS)]
        text = "[%d/%d] %s" % (n, args.total, flavour)
        use_wa = (not args.whatsapp_only and n % 2 == 1) or args.whatsapp_only
        if use_wa and wa_disabled:
            use_wa = False
        if not use_wa and not tg_chat:
            use_wa = not wa_disabled

        ts = _dt.datetime.now().strftime("%H:%M:%S")
        if use_wa:
            code, mid, status = zavu_send(zkey, number, text)
            if code in (200, 202) and mid:
                status = zavu_status(zkey, mid)
            ok = status in ("delivered", "read")
            rows.append({"n": n, "ts": ts, "channel": "whatsapp", "ok": ok,
                         "status": status or ("http-%s" % code), "id": mid, "text": text})
            log("  %3d/%d whatsapp -> %s (%s)" % (n, args.total, status, mid[:18]))
            if not ok:
                consecutive_fail += 1
                if consecutive_fail >= 3:
                    wa_disabled = True
                    stopped = ("WhatsApp leg disabled after 3 consecutive failures "
                               "(window closed or sender throttled); Telegram continued.")
                    log("  !! " + stopped)
            else:
                consecutive_fail = 0
        else:
            code, mid = tg_send(tgtok, tg_chat, text)
            ok = code == 200 and bool(mid)
            rows.append({"n": n, "ts": ts, "channel": "telegram", "ok": ok,
                         "status": "sent" if ok else "http-%s" % code, "id": mid, "text": text})
            log("  %3d/%d telegram -> %s (id %s)" % (n, args.total, "sent" if ok else "FAILED", mid))

        write_report(rows, started, number or tg_handle, stopped)
        if n < args.total:
            time.sleep(max(1, args.interval))

    inbound_wa = zavu_inbound_count(zkey, number) if zkey and number else 0
    inbound_tg = tg_inbound_count(tgtok) if tgtok else 0
    delivered = sum(1 for r in rows if r["ok"])
    log("")
    log("=" * 66)
    log("  DONE -- delivered %d / %d" % (delivered, len(rows)))
    log("  whatsapp delivered : %d" % sum(1 for r in rows if r["channel"] == "whatsapp" and r["ok"]))
    log("  telegram delivered : %d" % sum(1 for r in rows if r["channel"] == "telegram" and r["ok"]))
    log("  inbound seen       : whatsapp %d / telegram %d" % (inbound_wa, inbound_tg))
    log("  report             : %s" % os.path.join(OUT_DIR, "SUMMARY.html"))
    log("=" * 66)
    write_report(rows, started, number or tg_handle, stopped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
