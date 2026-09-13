
#!/usr/bin/env python3
# ollama_credits.py - Zero-dependency Ollama Cloud credits/usage checker.
#
# Queries your Ollama Cloud account activity and monthly usage directly
# from the ollama.com web API, using the SAME authentication the official
# Ollama client uses: an ed25519-signed Authorization header built from
# the key Ollama generated at ~/.ollama/id_ed25519 when you ran
# "ollama signin".
#
# ENDPOINTS (verified live 2026-09-12 by Tlamatini):
#   GET  https://ollama.com/api/usage  -> activity cost + monthly limits
#   POST https://ollama.com/api/me     -> account info (email, plan)
#   The LOCAL server (localhost:11434) has NO credits endpoint - the data
#   lives on ollama.com and needs the signed header.
#
# AUTH FORMAT (from ollama/ollama api/client.go + auth/auth.go):
#   challenge     = "<METHOD>,<path>?ts=<unix_seconds>"
#   Authorization = "<pubkey_base64>:<signature_base64>"
#   The same ts value must also appear in the URL query string.
#
# USAGE:
#   python ollama_credits.py          # human-readable report
#   python ollama_credits.py --json   # raw JSON
#
# DEPENDENCIES: NONE - pure Python standard library (ed25519 implemented
# from RFC 8032, OpenSSH key parsing implemented from the openssh-key-v1
# format spec). Works on any Python 3.8+.

import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request

HOST = "https://ollama.com"


# ============================================================
# Pure-Python ed25519 signing (RFC 8032 reference implementation)
# ============================================================
_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493


def _sha512(b):
    return hashlib.sha512(b).digest()


def _modp_inv(x):
    return pow(x, _P - 2, _P)


_D = -121665 * _modp_inv(121666) % _P


def _sha512_modq(s):
    return int.from_bytes(_sha512(s), "little") % _Q


def _point_add(P, Q):
    # Points are (X, Y, Z, T) extended coordinates: x = X/Z, y = Y/Z
    A = (P[1] - P[0]) * (Q[1] - Q[0]) % _P
    B = (P[1] + P[0]) * (Q[1] + Q[0]) % _P
    C = 2 * P[3] * Q[3] * _D % _P
    D = 2 * P[2] * Q[2] % _P
    E, F, G, H = B - A, D - C, D + C, B + A
    return (E * F % _P, G * H % _P, F * G % _P, E * H % _P)


def _point_mul(s, P):
    Q = (0, 1, 1, 0)
    while s > 0:
        if s & 1:
            Q = _point_add(Q, P)
        P = _point_add(P, P)
        s >>= 1
    return Q


_MODP_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * _modp_inv(_D * y * y + 1)
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _MODP_SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_G_Y = 4 * _modp_inv(5) % _P
_G_X = _recover_x(_G_Y, 0)
_G = (_G_X, _G_Y, 1, _G_X * _G_Y % _P)


def _point_compress(P):
    zinv = _modp_inv(P[2])
    x = P[0] * zinv % _P
    y = P[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _secret_expand(secret):
    if len(secret) != 32:
        raise ValueError("Bad size of private key")
    h = _sha512(secret)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= (1 << 254)
    return (a, h[32:])


def _ed25519_sign(secret, msg):
    a, prefix = _secret_expand(secret)
    A = _point_compress(_point_mul(a, _G))
    r = _sha512_modq(prefix + msg)
    R = _point_mul(r, _G)
    Rs = _point_compress(R)
    h = _sha512_modq(Rs + A + msg)
    s = (r + h * a) % _Q
    return Rs + int.to_bytes(s, 32, "little")


# ============================================================
# OpenSSH private key parsing (unencrypted openssh-key-v1 format)
# ============================================================
def _read_string(buf, off):
    (n,) = struct.unpack_from(">I", buf, off)
    off += 4
    return buf[off:off + n], off + n


def load_ollama_key():
    """Parse ~/.ollama/id_ed25519 -> (seed_32_bytes, pubkey_blob_b64)."""
    key_path = os.path.join(os.path.expanduser("~"), ".ollama", "id_ed25519")
    if not os.path.exists(key_path):
        sys.exit("ERROR: " + key_path + " not found. Run: ollama signin")
    with open(key_path, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    b64 = "".join(ln for ln in lines if not ln.startswith("-----"))
    blob = base64.b64decode(b64)

    magic = b"openssh-key-v1\x00"
    if not blob.startswith(magic):
        sys.exit("ERROR: unsupported key format (expected openssh-key-v1)")
    off = len(magic)
    cipher, off = _read_string(blob, off)
    kdf, off = _read_string(blob, off)
    _kdfopts, off = _read_string(blob, off)
    if cipher != b"none" or kdf != b"none":
        sys.exit("ERROR: key is passphrase-protected; decrypt it first")
    (nkeys,) = struct.unpack_from(">I", blob, off)
    off += 4
    _pub, off = _read_string(blob, off)
    priv_section, off = _read_string(blob, off)
    po = 8  # skip checkint1 + checkint2
    ktype, po = _read_string(priv_section, po)
    if ktype != b"ssh-ed25519":
        sys.exit("ERROR: expected ssh-ed25519 key, got " + ktype.decode())
    pub_bytes, po = _read_string(priv_section, po)
    priv_bytes, po = _read_string(priv_section, po)
    # OpenSSH stores ed25519 private keys as 64 bytes: seed(32) || pubkey(32)
    if len(priv_bytes) == 64:
        seed = priv_bytes[:32]
    elif len(priv_bytes) == 32:
        seed = priv_bytes
    else:
        sys.exit("ERROR: unexpected ed25519 private key size: " + str(len(priv_bytes)))

    # Rebuild the ssh public key blob: string "ssh-ed25519" + string pubkey
    pub_blob = struct.pack(">I", 11) + b"ssh-ed25519" + struct.pack(">I", 32) + pub_bytes
    return seed, base64.b64encode(pub_blob).decode()


# ============================================================
# Signed request to ollama.com
# ============================================================
def signed_request(seed, pub_b64, method, path, data=None, timeout=20):
    """Send a request to ollama.com signed exactly like the official client."""
    now = str(int(time.time()))
    challenge = method + "," + path + "?ts=" + now
    sig = _ed25519_sign(seed, challenge.encode())
    auth = pub_b64 + ":" + base64.b64encode(sig).decode()

    url = HOST + path + "?ts=" + now
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": auth,
    }
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


# ============================================================
# Report
# ============================================================
def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Ollama Cloud credits/usage")
    parser.add_argument("--json", action="store_true", help="raw JSON output")
    parser.add_argument("--reset-day", type=int, default=3, help="day of month the monthly window resets on (inferred from the reference screenshot, 0 hides the caption)")
    args = parser.parse_args()

    seed, pub_b64 = load_ollama_key()

    status, usage_body = signed_request(seed, pub_b64, "GET", "/api/usage")
    if status != 200:
        sys.exit("GET /api/usage failed: " + str(status) + " " + usage_body[:300])
    usage = json.loads(usage_body)

    status, me_body = signed_request(seed, pub_b64, "POST", "/api/me")
    me = json.loads(me_body) if status == 200 else {}

    if args.json:
        print(json.dumps({"account": me, "usage": usage}, indent=2))
        return

    plan = me.get("Plan") or me.get("plan") or "?"
    email = str(me.get("Email", "?"))

    monthly = usage.get("limits", {}).get("monthly", {})
    frac = float(monthly.get("usage", 0) or 0)
    total = 300.0  # plan "max" includes $300 of monthly usage (per the reference card)
    current = frac * total
    models = monthly.get("models", []) or []

    # ---- card renderer: replicates the Ollama desktop "Included usage" card ----
    E = chr(27)  # ANSI escape
    COLOR = sys.stdout.isatty()
    if COLOR:
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.GetStdHandle(-11)
            cmode = ctypes.c_uint32()
            if k32.GetConsoleMode(h, ctypes.byref(cmode)):
                k32.SetConsoleMode(h, cmode.value | 4)  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
        except Exception:
            pass

    def paint(code, text):
        if COLOR:
            return E + "[" + code + "m" + text + E + "[0m"
        return text

    def model_color(name):
        n = str(name).lower()
        if "qwen" in n:
            return "208"  # orange
        if "gemma" in n:
            return "40"  # green
        return "33"  # blue (glm, kimi, others)

    BAR_W = 60
    GREY = "245"

    # header: title + plan badge
    badge = paint("48;5;236;38;5;250", " " + str(plan).capitalize() + " ")
    print(paint("1", "Included usage") + "  " + badge)

    # description, dim grey, wrapped
    desc = ("Cloud models and capabilities such as web search draw from "
            "your monthly included usage.")
    words = desc.split(" ")
    line = ""
    for w in words:
        if len(line) + 1 + len(w) > 62:
            print(paint(GREY, line))
            line = w
        else:
            line = w if not line else line + " " + w
    if line:
        print(paint(GREY, line))

    print()

    # usage row: label left, amount right-aligned to the bar width
    label = "Monthly usage"
    amount = "$" + format(current, ".2f") + " of $" + format(total, ".0f") + " used"
    pad = max(1, BAR_W - len(label) - len(amount))
    print(paint("1", label) + " " * pad + paint("1", amount))

    # progress bar: one segment per model, width proportional to its requests
    reqs = [int(m.get("request_count", 0) or 0) for m in models]
    total_req = sum(reqs)
    fill = int(round(frac * BAR_W))
    segs = []
    if total_req > 0:
        if fill > 0:
            edge = 0
            cum = 0
            for r in reqs:
                cum = cum + r
                new_edge = int(round(fill * cum / total_req))
                segs.append(new_edge - edge)
                edge = new_edge
    bar = ""
    for m, s in zip(models, segs):
        if s > 0:
            bar = bar + paint("38;5;" + model_color(m.get("name", "")), chr(9608) * s)
    bar = bar + paint("38;5;238", chr(9617) * (BAR_W - sum(segs)))
    print(bar)

    # reset caption (reset day inferred from the reference card)
    if args.reset_day > 0:
        t = time.localtime()
        y = t.tm_year
        mo = t.tm_mon
        if t.tm_mday >= args.reset_day:
            mo = mo + 1
            if mo > 12:
                mo = 1
                y = y + 1
        target = time.mktime((y, mo, args.reset_day, 0, 0, 0, 0, 0, -1))
        days = int((target - time.time()) // 86400) + 1
        if days >= 14:
            caption = "Resets in " + str(days // 7) + " weeks."
        else:
            if days >= 7:
                caption = "Resets in 1 week."
            else:
                if days == 1:
                    caption = "Resets in 1 day."
                else:
                    caption = "Resets in " + str(days) + " days."
        print(paint(GREY, caption))

    print()

    # per-model list: colored swatch + name, right-aligned request count
    print(paint("1", "Models used this month"))
    for m in models:
        name = str(m.get("name", "?"))
        cnt = str(m.get("request_count", 0))
        swatch = paint("38;5;" + model_color(name), chr(9632))
        plain = 2 + 2 + len(name)
        gap = max(1, BAR_W - plain - len(cnt))
        print("  " + swatch + " " + name + " " * gap + paint(GREY, cnt))

    print()

    # dim footer: account + 4-week activity (extra data the card does not show)
    activity = usage.get("activity", {})
    print(paint(GREY, "Account: " + email + " (plan: " + str(plan) + ")"))
    bits = []
    for m in activity.get("models", []):
        bits.append(str(m.get("name", "?")) + " " + str(m.get("request_count", 0))
                    + " reqs ($" + str(m.get("cost", "?")) + ")")
    aline = "Activity (last 4 weeks): $" + str(activity.get("cost", "?"))
    if bits:
        aline = aline + " - " + ", ".join(bits)
    print(paint(GREY, aline))

    # hold a real console window open so the report can be read (piped runs skip this)
    if sys.stdin is not None and hasattr(sys.stdin, "isatty") and sys.stdin.isatty():
        try:
            input()
        except Exception:
            pass


if __name__ == "__main__":
    main()
