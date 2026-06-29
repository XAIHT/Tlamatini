#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
check_private_data.py -- god-of-gods private-data leak auditor.

Scans a repository (local working tree and/or its git remote) for any occurrence
of YOUR private data -- names, phone numbers, messaging handles, private keys,
certificates, post-quantum (Kyber) key material, and generic secrets -- across
every layer it can reach:

  * plain text          (utf-8 / utf-16 / latin-1)
  * binary / hex        (raw bytes, hex-encoded, UTF-16LE Windows strings)
  * encoded variants    (base64 / base32 / hex / url-encode / rot13 / reversed /
                         leetspeak)            -> the "homomorphic" fuzzy layer
  * steganographic      (printable strings carved from binaries/images, data
                         trailing an image EOF, EXIF/metadata, LSB bit-planes)
  * filesystem forensics(size, owner/account, ctime/mtime/atime in ns, a femto
                         display, inode/device, git author/committer/date)
  * process forensics   (this process's memory maps, parent-process chain,
                         logged-in account)
  * LLM deep review     (an Ollama model, default glm-5.2:cloud, fallback
                         kimi-k2.7-code:cloud, reads each candidate file and
                         reports obfuscated / steganographic leaks regex misses)

YOUR PRIVATE DATA IS NEVER HARDCODED HERE. Supply it at run time via:
  --targets-file <path>   JSON {"names":[...],"phones":[...],"handles":[...]}
                          or a plain newline-separated list of strings
  env  CHECK_PRIVATE_DATA_TARGETS   (same JSON or newline list)
  --target "value"        (repeatable)

Modes:
  --local    scan only the local repo (here)        [default if none given]
  --remote   clone the remote into a temp dir and scan only it
  --both     scan both and merge the report

Examples:
  python check_private_data.py --local --targets-file my_secrets.json
  python check_private_data.py --both  --remote-url https://github.com/me/repo.git
  python check_private_data.py --local --no-llm --target "Some Name" --target "5551234"
"""

from __future__ import annotations

import argparse
import base64
import binascii
import codecs
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

# ----- optional dependencies (all degrade gracefully) ------------------------
try:
    import psutil  # process + memory forensics
except Exception:  # pragma: no cover
    psutil = None

try:
    from PIL import Image  # steganographic image carving
    from PIL.ExifTags import TAGS as _EXIF_TAGS
except Exception:  # pragma: no cover
    Image = None
    _EXIF_TAGS = {}

try:
    import win32security  # windows file owner / account
except Exception:  # pragma: no cover
    win32security = None

try:
    import numpy as np  # vectorized LSB bit-plane extraction
except Exception:  # pragma: no cover
    np = None

DEFAULT_MODEL = "glm-5.2:cloud"
DEFAULT_FALLBACK_MODEL = "kimi-k2.7-code:cloud"


# =============================================================================
# Target loading -- the private data is supplied, NEVER hardcoded
# =============================================================================
def _normalize(s: str) -> str:
    """Strip accents + lowercase so 'Lopez' matches 'Lopez' with an accent."""
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def load_targets(args) -> list[dict]:
    """Return a list of target dicts: {label, value, category}."""
    raw: list[tuple[str, str]] = []

    def absorb(blob: str):
        blob = blob.strip()
        if not blob:
            return
        try:
            data = json.loads(blob)
        except Exception:
            for line in blob.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    raw.append(("generic", line))
            return
        if isinstance(data, dict):
            for cat, vals in data.items():
                if isinstance(vals, (list, tuple)):
                    for v in vals:
                        raw.append((str(cat), str(v)))
                else:
                    raw.append((str(cat), str(vals)))
        elif isinstance(data, list):
            for v in data:
                raw.append(("generic", str(v)))

    if getattr(args, "targets_file", None):
        with open(args.targets_file, "r", encoding="utf-8", errors="replace") as fh:
            absorb(fh.read())
    env_blob = os.environ.get("CHECK_PRIVATE_DATA_TARGETS")
    if env_blob:
        absorb(env_blob)
    for t in getattr(args, "target", None) or []:
        raw.append(("generic", t))

    seen = set()
    targets = []
    for cat, val in raw:
        val = val.strip()
        if not val or val in seen:
            continue
        seen.add(val)
        targets.append({"label": val, "value": val, "category": cat})
    return targets


def compile_targets(targets: list[dict]) -> dict:
    """Pre-build byte variants + fuzzy regex for every target (keyed by value)."""
    return {t["value"]: {"variants": byte_variants(t["value"]),
                         "fuzzy": fuzzy_regex(t["value"])} for t in targets}


# =============================================================================
# Variant generation -- the "homomorphic / alien" obfuscation layer
# =============================================================================
_LEET = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5", "t": "7"})


def byte_variants(value: str) -> dict[str, bytes]:
    """Every byte-level form of a target a leak might hide behind."""
    out: dict[str, bytes] = {}
    u8 = value.encode("utf-8", "replace")
    out["utf-8"] = u8
    try:
        out["utf-16-le"] = value.encode("utf-16-le")
    except Exception:
        pass
    out["hex"] = binascii.hexlify(u8)
    out["base64"] = base64.b64encode(u8)
    out["base32"] = base64.b32encode(u8)
    try:
        out["url"] = urllib.request.quote(value).encode()
    except Exception:
        pass
    try:
        out["rot13"] = codecs.encode(value, "rot_13").encode("utf-8", "replace")
    except Exception:
        pass
    out["reversed"] = value[::-1].encode("utf-8", "replace")
    out["leet"] = value.lower().translate(_LEET).encode("utf-8", "replace")
    out["normalized"] = _normalize(value).encode("utf-8", "replace")
    # de-dupe by bytes, keep first label
    final, used = {}, set()
    for label, b in out.items():
        if b and b not in used:
            used.add(b)
            final[label] = b
    return final


def fuzzy_regex(value: str) -> re.Pattern:
    """Separator-tolerant, accent-insensitive regex for a target."""
    chars = [re.escape(ch) for ch in _normalize(value) if ch.strip()]
    if not chars:
        return re.compile(r"(?!x)x")  # never matches
    body = r"[\s\W_]{0,3}".join(chars)
    return re.compile(body, re.IGNORECASE)


# =============================================================================
# Structural secret patterns (keys, certs, kyber, generic tokens)
# =============================================================================
STRUCT_PATTERNS: dict[str, re.Pattern] = {
    "private_key_pem": re.compile(
        rb"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----"
    ),
    "certificate_pem": re.compile(rb"-----BEGIN CERTIFICATE-----"),
    "ssh_private": re.compile(rb"-----BEGIN OPENSSH PRIVATE KEY-----"),
    "putty_key": re.compile(rb"PuTTY-User-Key-File-\d"),
    "kyber_keyword": re.compile(rb"(?i)\b(kyber|crystals[-_ ]?kyber|ml[-_ ]?kem)\b"),
    "aws_access_key": re.compile(rb"AKIA[0-9A-Z]{16}"),
    "google_api_key": re.compile(rb"AIza[0-9A-Za-z\-_]{35}"),
    "slack_token": re.compile(rb"xox[baprs]-[0-9A-Za-z-]{10,}"),
    "generic_bearer": re.compile(rb"(?i)bearer\s+[a-z0-9._\-]{20,}"),
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),
    "high_entropy_b64": re.compile(rb"[A-Za-z0-9+/]{60,}={0,2}"),
}


# =============================================================================
# Filesystem + git forensics
# =============================================================================
def femto_display(ns: int) -> str:
    """fs gives nanoseconds; show a femtosecond-scaled figure (x1e6), labelled."""
    return f"{ns * 1_000_000} fs (from {ns} ns; fs resolution ~100 ns)"


def file_owner(path: str) -> str:
    if win32security is not None:
        try:
            sd = win32security.GetFileSecurity(
                path, win32security.OWNER_SECURITY_INFORMATION
            )
            sid = sd.GetSecurityDescriptorOwner()
            name, domain, _ = win32security.LookupAccountSid(None, sid)
            return f"{domain}\\{name}"
        except Exception:
            pass
    try:
        st = os.stat(path)
        return f"uid={getattr(st, 'st_uid', '?')} gid={getattr(st, 'st_gid', '?')}"
    except Exception:
        return "unknown"


def git_blame_meta(repo: str, rel: str) -> dict:
    try:
        out = subprocess.run(
            ["git", "-C", repo, "log", "-1", "--format=%an|%ae|%cn|%ce|%cI|%H", "--", rel],
            capture_output=True, text=True, timeout=20,
        )
        if out.returncode == 0 and out.stdout.strip():
            an, ae, cn, ce, ci, h = (out.stdout.strip().split("|") + [""] * 6)[:6]
            return {"author": an, "author_email": ae, "committer": cn,
                    "committer_email": ce, "commit_date": ci, "commit": h}
    except Exception:
        pass
    return {}


def file_forensics(path: str, repo: str) -> dict:
    st = os.stat(path)
    rel = os.path.relpath(path, repo)
    meta = {
        "path": path,
        "relpath": rel,
        "size_bytes": st.st_size,
        "owner_account": file_owner(path),
        "inode": getattr(st, "st_ino", None),
        "device": getattr(st, "st_dev", None),
        "mode": oct(st.st_mode),
        "mtime_ns": st.st_mtime_ns,
        "ctime_ns": st.st_ctime_ns,
        "atime_ns": st.st_atime_ns,
        "mtime_iso": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        "ctime_iso": datetime.fromtimestamp(st.st_ctime, timezone.utc).isoformat(),
        "mtime_femto": femto_display(st.st_mtime_ns),
        "sha256": None,
    }
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        meta["sha256"] = h.hexdigest()
    except Exception:
        pass
    meta["git"] = git_blame_meta(repo, rel)
    return meta


# =============================================================================
# Process / memory forensics
# =============================================================================
def process_forensics() -> dict:
    info = {"pid": os.getpid(), "login": None, "parents": [], "memory_maps": []}
    try:
        info["login"] = os.getlogin()
    except Exception:
        info["login"] = os.environ.get("USERNAME") or os.environ.get("USER")
    if psutil is None:
        info["note"] = "psutil not installed -- parent chain / memory maps limited"
        return info
    try:
        p = psutil.Process()
        while p is not None:
            info["parents"].append({
                "pid": p.pid, "name": p.name(),
                "exe": (p.exe() if p.is_running() else ""),
                "user": (p.username() if p.is_running() else ""),
            })
            p = p.parent()
        cur = psutil.Process()
        try:
            for m in cur.memory_maps(grouped=False)[:64]:
                info["memory_maps"].append({
                    "addr": getattr(m, "addr", ""),
                    "path": getattr(m, "path", ""),
                    "rss": getattr(m, "rss", 0),
                })
        except Exception:
            mi = cur.memory_info()
            info["memory_info"] = {"rss": mi.rss, "vms": mi.vms}
    except Exception as e:  # pragma: no cover
        info["note"] = f"process introspection error: {e}"
    return info


# =============================================================================
# Content + binary + hex + variant scanning
# =============================================================================
_FUZZY_TEXT_CAP = 5_000_000  # cap the decoded-text fuzzy layer for huge blobs


def scan_bytes(data: bytes, targets: list[dict],
               compiled: dict[str, dict]) -> list[dict]:
    hits = []
    low = data.lower()
    # decode + accent-normalize ONCE (not once per target); cap for huge files.
    # Exact byte-variant search below still covers the FULL file; only the
    # fuzzy separator-tolerant layer is capped (it is a heuristic).
    try:
        norm_text = _normalize(data[:_FUZZY_TEXT_CAP].decode("utf-8", "ignore"))
    except Exception:
        norm_text = ""
    for t in targets:
        c = compiled[t["value"]]
        for label, b in c["variants"].items():
            idx = low.find(b.lower()) if label in ("utf-8", "normalized") else data.find(b)
            if idx >= 0:
                hits.append({"target": t["label"], "category": t["category"],
                             "layer": f"bytes:{label}", "offset": idx})
        if norm_text:
            m = c["fuzzy"].search(norm_text)
            if m:
                hits.append({"target": t["label"], "category": t["category"],
                             "layer": "fuzzy-regex", "offset": m.start()})
    return hits


def scan_struct(data: bytes) -> list[dict]:
    hits = []
    for name, pat in STRUCT_PATTERNS.items():
        for m in pat.finditer(data):
            hits.append({"secret_type": name, "offset": m.start(),
                         "sample": data[m.start():m.start() + 24].decode("latin-1", "replace")})
            if name == "high_entropy_b64":
                break  # one sample is enough; avoid noise
    return hits


# =============================================================================
# Steganographic carving
# =============================================================================
_PRINTABLE = re.compile(rb"[\x20-\x7e]{4,}")


def carve_strings(data: bytes, limit: int = 4000) -> bytes:
    # finditer is lazy: stop at `limit` instead of materializing every match
    # (a 20 MB text-ish blob can yield millions of runs -> RAM + time blowup).
    out = []
    for m in _PRINTABLE.finditer(data):
        out.append(m.group())
        if len(out) >= limit:
            break
    return b"\n".join(out)


def extract_lsb_bytes(img) -> bytes:
    """Pack the 1-bit LSB plane of an image into bytes (MSB-first per byte).

    Vectorized with numpy when available (milliseconds); a small-capped
    pure-Python fallback otherwise so a numpy-less host never hangs.
    """
    rgb = img.convert("RGB")
    if np is not None:
        arr = np.asarray(rgb, dtype=np.uint8).reshape(-1)
        return np.packbits(arr & 1).tobytes()
    px = list(rgb.getdata())[:200_000]  # fallback cap keeps it fast
    bits = []
    for r, g, b in px:
        bits.extend((r & 1, g & 1, b & 1))
    out = bytearray()
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | bits[i + j]
        out.append(byte)
    return bytes(out)


def steg_scan(path: str, data: bytes, targets: list[dict],
              compiled: dict[str, dict]) -> list[dict]:
    hits = []
    carved = carve_strings(data)
    hits += [dict(h, layer="steg:carved-strings") for h in scan_bytes(carved, targets, compiled)]

    ext = os.path.splitext(path)[1].lower()
    if Image is None or ext not in (".png", ".bmp", ".gif", ".jpg", ".jpeg", ".tiff"):
        return hits
    try:
        img = Image.open(path)
        meta_blob = b""
        exif = getattr(img, "_getexif", lambda: None)()
        if exif:
            for k, v in exif.items():
                meta_blob += f"{_EXIF_TAGS.get(k, k)}={v}\n".encode("utf-8", "replace")
        hits += [dict(h, layer="steg:exif") for h in scan_bytes(meta_blob, targets, compiled)]

        eof_markers = (b"\xff\xd9", b"\x49\x45\x4e\x44\xae\x42\x60\x82")
        for marker in eof_markers:
            pos = data.rfind(marker)
            if pos >= 0 and pos + len(marker) < len(data) - 8:
                trailing = data[pos + len(marker):]
                hits += [dict(h, layer="steg:trailing-after-eof")
                         for h in scan_bytes(trailing, targets, compiled)]

        if img.mode in ("RGB", "RGBA", "L") and (img.width * img.height) <= 16_000_000:
            lsb_bytes = extract_lsb_bytes(img)
            hits += [dict(h, layer="steg:lsb-bitplane")
                     for h in scan_bytes(lsb_bytes, targets, compiled)]
            hits += [dict(h, layer="steg:lsb-bitplane-strings")
                     for h in scan_bytes(carve_strings(lsb_bytes), targets, compiled)]
    except Exception as e:  # pragma: no cover
        hits.append({"layer": "steg:error", "note": str(e)})
    return hits


# =============================================================================
# LLM deep review (Ollama) -- primary model + fallback chain
# =============================================================================
def build_models(primary: str, fallback: str) -> list[str]:
    models = []
    for m in (primary, fallback):
        if m and m not in models:
            models.append(m)
    return models


def _llm_system_prompt(targets: list[dict]) -> str:
    cats = sorted({t["category"] for t in targets})
    return (
        "You are an elite data-leak auditor. You are given the text of ONE file. "
        "Report ONLY whether it contains personal/private data of these kinds: "
        + ", ".join(cats) + ", plus private keys, certificates, "
        "Kyber/post-quantum key material, or steganographically/obfuscated hidden "
        "secrets (base64, hex, reversed, leetspeak, zero-width chars). "
        "Answer concisely: LEAK or CLEAN, then a one-line reason and any offsets."
    )


def ollama_chat(text: str, model: str, url: str, targets: list[dict],
                opener=None) -> str:
    """Single Ollama /api/chat call. Returns content or a '[llm-...]' error str."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _llm_system_prompt(targets)},
            {"role": "user", "content": text[:12000]},
        ],
        "stream": False,
    }
    req = urllib.request.Request(
        url.rstrip("/") + "/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    api_key = os.environ.get("OLLAMA_API_KEY")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    opener = opener or urllib.request.urlopen
    try:
        with opener(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        return (body.get("message") or {}).get("content", "").strip()
    except urllib.error.URLError as e:
        return f"[llm-unavailable: {e}]"
    except Exception as e:  # pragma: no cover
        return f"[llm-error: {e}]"


def llm_review(text: str, models: list[str], url: str, targets: list[dict],
               opener=None) -> dict:
    """Try each model in order; return the first usable verdict.

    Returns {"model": <model or None>, "verdict": <str>}.
    """
    if not text.strip():
        return {"model": None, "verdict": ""}
    last = ""
    for model in models:
        res = ollama_chat(text, model, url, targets, opener=opener)
        if res and not res.startswith("["):
            return {"model": model, "verdict": res}
        last = res
    return {"model": None, "verdict": last}


# =============================================================================
# Repo walking
# =============================================================================
SKIP_DIRS = {".git", "node_modules", "__pycache__", "venv", ".venv", "dist",
             "build", ".mypy_cache", ".ruff_cache", ".pytest_cache",
             "staticfiles", "Temp",
             # Carried THIRD-PARTY runtimes bundled into the package — their
             # binaries trip the structural/fuzzy patterns by the thousand and
             # can never hold an intentional leak of your data. Skip them.
             "python", "jre", "git", "ms-playwright"}
TEXT_REVIEW_EXT = {".py", ".js", ".ts", ".json", ".yaml", ".yml", ".md", ".txt",
                   ".env", ".cfg", ".ini", ".toml", ".html", ".css", ".csv",
                   ".pem", ".key", ".crt", ".keys"}


def iter_files(root: str, max_bytes: int):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            full = os.path.join(dirpath, name)
            try:
                if os.path.getsize(full) > max_bytes:
                    continue
            except OSError:
                continue
            yield full


def scan_repo(root: str, targets: list[dict], compiled: dict, args) -> dict:
    findings = []
    n_files = 0
    models = getattr(args, "models", None) or build_models(
        getattr(args, "model", DEFAULT_MODEL), getattr(args, "fallback_model", DEFAULT_FALLBACK_MODEL))
    for path in iter_files(root, args.max_bytes):
        n_files += 1
        if n_files % 200 == 0:
            print(f"    [*] scanned {n_files} files, {len(findings)} flagged so far...",
                  file=sys.stderr, flush=True)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except Exception:
            continue
        file_hits = []
        file_hits += scan_bytes(data, targets, compiled)
        file_hits += [dict(h, layer="struct:" + h.get("secret_type", "?"))
                      for h in scan_struct(data)]
        file_hits += steg_scan(path, data, targets, compiled)

        review = {"model": None, "verdict": ""}
        ext = os.path.splitext(path)[1].lower()
        if (not args.no_llm) and (file_hits or ext in TEXT_REVIEW_EXT):
            try:
                text = data.decode("utf-8", "ignore")
            except Exception:
                text = carve_strings(data).decode("latin-1", "ignore")
            review = llm_review(text, models, args.ollama_url, targets)
        llm_verdict = review["verdict"]

        flagged_by_llm = (llm_verdict and "CLEAN" not in llm_verdict.upper()
                          and not llm_verdict.startswith("["))
        if file_hits or flagged_by_llm:
            findings.append({
                "forensics": file_forensics(path, root),
                "matches": file_hits,
                "llm_model": review["model"],
                "llm_verdict": llm_verdict,
            })
    return {"root": root, "files_scanned": n_files, "findings": findings}


# =============================================================================
# Remote handling
# =============================================================================
def clone_remote(remote_url: str) -> str:
    tmp = tempfile.mkdtemp(prefix="cpd_remote_")
    subprocess.run(["git", "clone", "--depth", "50", remote_url, tmp],
                   check=True, timeout=600)
    return tmp


def detect_remote_url(repo: str) -> str:
    out = subprocess.run(["git", "-C", repo, "remote", "get-url", "origin"],
                         capture_output=True, text=True, timeout=20)
    return out.stdout.strip() if out.returncode == 0 else ""


# =============================================================================
# main
# =============================================================================
def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="God-of-gods private-data leak auditor.")
    scope = ap.add_argument_group("scope (default: --local)")
    scope.add_argument("--local", action="store_true", help="scan the local repo")
    scope.add_argument("--remote", action="store_true", help="scan the git remote only")
    scope.add_argument("--both", action="store_true", help="scan local AND remote")
    ap.add_argument("--repo", default=os.getcwd(), help="local repo path (default: cwd)")
    ap.add_argument("--remote-url", default="", help="remote git url (default: origin)")
    ap.add_argument("--targets-file", help="JSON or newline list of private values")
    ap.add_argument("--target", action="append", help="one private value (repeatable)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="primary Ollama model")
    ap.add_argument("--fallback-model", default=DEFAULT_FALLBACK_MODEL,
                    help="fallback Ollama model if the primary fails")
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--no-llm", action="store_true", help="skip the LLM review layer")
    ap.add_argument("--max-bytes", type=int, default=25_000_000, help="per-file size cap")
    ap.add_argument("--output", default="private_data_audit_report.json", help="JSON report path")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if not (args.local or args.remote or args.both):
        args.local = True

    targets = load_targets(args)
    if not targets:
        print("ERROR: no private-data targets supplied. Use --targets-file, "
              "--target, or env CHECK_PRIVATE_DATA_TARGETS.", file=sys.stderr)
        print("       (By design, NOTHING private is hardcoded in this script.)",
              file=sys.stderr)
        return 2

    args.models = build_models(args.model, args.fallback_model)
    compiled = compile_targets(targets)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "both" if args.both else ("remote" if args.remote else "local"),
        "targets_count": len(targets),
        "target_categories": sorted({t["category"] for t in targets}),
        "llm_models": (None if args.no_llm else args.models),
        "process_forensics": process_forensics(),
        "scans": [],
    }

    do_local = args.local or args.both
    do_remote = args.remote or args.both

    if do_local:
        print(f"[*] scanning LOCAL: {args.repo}")
        report["scans"].append({"mode": "local",
                                "result": scan_repo(args.repo, targets, compiled, args)})

    if do_remote:
        url = args.remote_url or detect_remote_url(args.repo)
        if not url:
            print("[!] no remote url found; skipping remote scan", file=sys.stderr)
        else:
            print(f"[*] cloning + scanning REMOTE: {url}")
            try:
                tmp = clone_remote(url)
                report["scans"].append({"mode": "remote", "url": url,
                                        "result": scan_repo(tmp, targets, compiled, args)})
            except Exception as e:
                report["scans"].append({"mode": "remote", "url": url, "error": str(e)})

    total = sum(len(s.get("result", {}).get("findings", [])) for s in report["scans"])
    report["total_files_with_findings"] = total

    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False)

    print("\n=== AUDIT COMPLETE ===")
    print(f"  targets        : {len(targets)} ({', '.join(report['target_categories'])})")
    print(f"  scope          : {report['scope']}")
    print(f"  files w/ leaks : {total}")
    print(f"  report         : {args.output}")
    if total:
        print("  !!! POTENTIAL PRIVATE-DATA LEAKS FOUND -- review the report. !!!")
    else:
        print("  clean: no private-data matches found.")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
