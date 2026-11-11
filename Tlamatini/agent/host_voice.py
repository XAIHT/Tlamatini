# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""Tlamatini's host voice: she keeps talking through this computer's speakers
when no browser page can do it for her.

Angela, 2026-11-11: "Tlamatini must always speak no matter if the browser is
even closed ... make her unstoppable once she started to speak." The browser
speaks first (voice_runtime.js). This module takes over when:

* the page closes or reloads in the middle of a sentence (the page hands the
  rest of what she was saying over here with ``navigator.sendBeacon``);
* the browser's own speech engine cannot speak (no female voice, no user
  gesture yet, a chunk that keeps failing);
* an answer finishes while no chat page of that account is open.

It speaks with Windows SAPI (System.Speech) in a hidden PowerShell child, one
message at a time, in the user's own voice settings (mode, volume, rate, voice
and language). FEMALE VOICES ONLY: Tlamatini never speaks with a male voice, so
a machine without a female voice stays silent rather than substitute one.

Stdlib-only, imports nothing from ``agent.*`` at module level, and fail-open:
nothing here may raise into a caller, and a missing speech engine only means
she is silent, exactly as before.
"""

import base64
import json
import math
import os
import re
import subprocess
import threading
import time
import uuid
from collections import deque
from html import unescape
from xml.sax.saxutils import escape as xml_escape

# ── Edition ──────────────────────────────────────────────────────────────────
EDITION_LANG = "en-US"
# The English edition may use any installed female voice when none matches the
# page language; the Spanish edition never falls back to an English one.
ANY_LANGUAGE_FALLBACK = True
COMPLETE_PHRASE = "I've finished your request, {name}."

MODES = ("speak", "notify", "silent")
DEFAULTS = {"mode": "notify", "volume": 100.0, "rate": 1.0, "pitch": 1.05, "voice": "", "lang": ""}
MAX_TEXT = 20000
_KEEP_JOBS = 200

_LOCK = threading.Condition()
_QUEUE = deque()
_JOBS = {}
_SETTINGS = {}
_PAGES = {}
_CURRENT = {"job": None, "proc": None}
_WORKER = {"thread": None}

# Speaks one message: the voice is chosen inside SAPI so its culture and gender
# are the installed engine's own facts, never a guess from a display name.
_SAPI_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$raw = [Console]::In.ReadToEnd()
$job = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($raw.Trim())) | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$female = [System.Speech.Synthesis.VoiceGender]::Female
$voices = @($s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Gender -eq $female } | ForEach-Object { $_.VoiceInfo })
$lang = ([string]$job.lang).ToLower()
$base = ($lang -split '-')[0]
$pick = $null
$skip = @('microsoft', 'desktop', 'online', 'natural', 'google', 'english', 'spanish', 'united', 'states', 'mexico')
$want = @(([string]$job.voice) -split '[^A-Za-z]+' | Where-Object { $_ -and ($skip -notcontains $_.ToLower()) })
if ($want.Count) { $pick = $voices | Where-Object { $_.Name -match [regex]::Escape($want[0]) } | Select-Object -First 1 }
if ($pick -and $base -and -not $pick.Culture.Name.ToLower().StartsWith($base)) { $pick = $null }
if (-not $pick -and $lang) { $pick = $voices | Where-Object { $_.Culture.Name.ToLower() -eq $lang } | Select-Object -First 1 }
if (-not $pick -and $base) { $pick = $voices | Where-Object { $_.Culture.TwoLetterISOLanguageName -eq $base } | Select-Object -First 1 }
if (-not $pick -and $job.any) { $pick = $voices | Select-Object -First 1 }
if (-not $pick) { [Console]::Out.WriteLine('NO-FEMALE-VOICE'); exit 3 }
$s.SelectVoice($pick.Name)
$s.Volume = [int]$job.volume
$s.Rate = [int]$job.rate
$s.SetOutputToDefaultAudioDevice()
[Console]::Out.WriteLine('VOICE ' + $pick.Name + ' ' + $pick.Culture.Name)
[Console]::Out.Flush()
$s.SpeakSsml(([string]$job.ssml).Replace('__LANG__', $pick.Culture.Name))
$s.Dispose()
[Console]::Out.WriteLine('DONE')
"""


def _log(message):
    try:
        print(f"--- [HOST-VOICE] {message}")
    except Exception:  # noqa: BLE001 - logging must never cost the voice
        pass


def available():
    """True on Windows, where System.Speech exists. Test runs stay silent."""
    return os.name == "nt" and os.environ.get("TLAMATINI_NO_AUDIO") != "1"


# ── Text ─────────────────────────────────────────────────────────────────────
_TAGS = re.compile(r"<[^>]+>")
_DROP_BLOCKS = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1\s*>|<table\b[^>]*exec-report[^>]*>.*?</table\s*>",
    re.IGNORECASE | re.DOTALL)


def plain_text(value):
    """What may be read aloud: no markup, no END-RESPONSE sentinel, no Exec Report."""
    text = str(value or "")
    if "<" in text:
        text = _DROP_BLOCKS.sub(" ", text)
        text = _TAGS.sub(" ", text)
    text = unescape(text).replace("END-RESPONSE", " ")
    return re.sub(r"\s+", " ", text).strip()[:MAX_TEXT]


def prepare(text, user=None):
    """Edition hook for spoken spelling (the Spanish edition accents names)."""
    return text


# ── Settings and open pages ──────────────────────────────────────────────────
def _clean_settings(data, base=None):
    clean = dict(DEFAULTS)
    clean.update(base or {})
    if not isinstance(data, dict):
        return clean
    mode = str(data.get("mode", clean["mode"]))
    if mode in MODES:
        clean["mode"] = mode
    for key, low, high in (("volume", 0.0, 100.0), ("rate", 0.5, 2.0), ("pitch", 0.0, 2.0)):
        try:
            number = float(data.get(key, clean[key]))
            if math.isfinite(number):
                clean[key] = min(high, max(low, number))
        except (TypeError, ValueError):
            pass
    clean["voice"] = str(data.get("voice", clean["voice"]) or "")[:120]
    clean["lang"] = re.sub(r"[^A-Za-z-]", "", str(data.get("lang", clean["lang"]) or ""))[:20]
    return clean


def update_settings(user_id, data):
    """Store the voice settings a page reported for this account."""
    with _LOCK:
        clean = _clean_settings(data, _SETTINGS.get(user_id))
        _SETTINGS[user_id] = clean
    if clean["mode"] == "silent" or clean["volume"] <= 0:
        stop(user_id)
    return dict(clean)


def settings_for(user_id):
    with _LOCK:
        return dict(_SETTINGS.get(user_id) or DEFAULTS)


def page_opened(user_id):
    with _LOCK:
        _PAGES[user_id] = _PAGES.get(user_id, 0) + 1


def page_closed(user_id):
    with _LOCK:
        count = _PAGES.get(user_id, 0) - 1
        if count > 0:
            _PAGES[user_id] = count
        else:
            _PAGES.pop(user_id, None)


def has_page(user_id):
    with _LOCK:
        return _PAGES.get(user_id, 0) > 0


# ── Jobs ─────────────────────────────────────────────────────────────────────
def speak(user_id, text, settings=None, reason="", markup=False):
    """Queue one message; return its job id, or None when nothing will be said.

    A page sends text that is already plain (and already spelled for speech);
    only server-side answers carry markup to remove.
    """
    try:
        text = plain_text(text) if markup else re.sub(r"\s+", " ", str(text or "")).strip()[:MAX_TEXT]
        if not text or not available():
            return None
        current = update_settings(user_id, settings) if isinstance(settings, dict) else settings_for(user_id)
        if current["mode"] == "silent" or current["volume"] <= 0:
            return None
        job_id = uuid.uuid4().hex
        with _LOCK:
            _JOBS[job_id] = {"user": user_id, "text": text, "settings": current,
                             "state": "queued", "reason": str(reason or "")[:80], "at": time.time()}
            _QUEUE.append(job_id)
            _prune_locked()
            _ensure_worker_locked()
            _LOCK.notify_all()
        _log(f"queued {len(text)} characters for user {user_id} ({reason or 'request'})")
        return job_id
    except Exception as exc:  # noqa: BLE001 - the voice is fail-open
        _log(f"could not queue speech: {exc}")
        return None


def status(user_id, job_id=""):
    """The state of one job of this account, and whether she is talking for it."""
    with _LOCK:
        job = _JOBS.get(job_id) if job_id else None
        state = job["state"] if job and job["user"] == user_id else ("unknown" if job_id else "")
        busy = any(_JOBS[j]["user"] == user_id for j in _QUEUE if j in _JOBS)
        current = _CURRENT["job"]
        if current and current in _JOBS and _JOBS[current]["user"] == user_id:
            busy = True
        return {"state": state, "busy": busy, "available": available()}


def stop(user_id):
    """Stop everything she is saying, or about to say, for this account."""
    with _LOCK:
        for job_id in list(_QUEUE):
            job = _JOBS.get(job_id)
            if job and job["user"] == user_id:
                _QUEUE.remove(job_id)
                job["state"] = "stopped"
        current, proc = _CURRENT["job"], _CURRENT["proc"]
        stopping = bool(current and current in _JOBS and _JOBS[current]["user"] == user_id)
        if stopping:
            _JOBS[current]["state"] = "stopped"
    if stopping and proc is not None:
        try:
            proc.kill()  # the PowerShell child only; it starts no children of its own
        except Exception:  # noqa: BLE001 - it may have finished on its own
            pass
        _log(f"stopped for user {user_id}")
    return stopping


def answer_finished(user, answer):
    """An answer finished. Say it here when no page of this account is open."""
    try:
        user_id = getattr(user, "id", None)
        if user_id is None or has_page(user_id):
            return None
        current = settings_for(user_id)
        if current["mode"] == "silent":
            return None
        if current["mode"] == "speak":
            text = plain_text(answer)
        else:
            from .constants import display_name, say  # noqa: PLC0415 - Django-side only
            text = say(COMPLETE_PHRASE, display_name(user))
        text = prepare(text, user)
        job = speak(user_id, text, reason="answer finished with no page open")
        if job:
            _log(f"no chat page is open for user {user_id}: she announces the answer here")
        return job
    except Exception as exc:  # noqa: BLE001 - an announcement must never cost the answer
        _log(f"answer announcement skipped: {exc}")
        return None


# ── Worker ───────────────────────────────────────────────────────────────────
def _prune_locked():
    if len(_JOBS) <= _KEEP_JOBS:
        return
    finished = [j for j, job in _JOBS.items() if job["state"] in ("done", "failed", "stopped")]
    finished.sort(key=lambda j: _JOBS[j]["at"])
    for job_id in finished[:len(_JOBS) - _KEEP_JOBS]:
        _JOBS.pop(job_id, None)


def _ensure_worker_locked():
    thread = _WORKER["thread"]
    if thread is None or not thread.is_alive():
        thread = threading.Thread(target=_worker, name="tlamatini-host-voice", daemon=True)
        _WORKER["thread"] = thread
        thread.start()


def _sapi_rate(rate):
    # Browser rate 0.5..2.0 (1 = normal) -> SAPI -10..10 (0 = normal).
    return int(max(-10, min(10, round(10 * math.log2(max(0.5, min(2.0, rate)))))))


def _ssml(text, pitch):
    body = xml_escape(text)
    if pitch <= 0.75:
        body = f'<prosody pitch="low">{body}</prosody>'
    elif pitch >= 1.3:
        body = f'<prosody pitch="high">{body}</prosody>'
    return ('<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xml:lang="__LANG__">{body}</speak>')


def _run(job_id, job):
    s = job["settings"]
    payload = {"voice": s["voice"], "lang": (s["lang"] or EDITION_LANG), "any": ANY_LANGUAGE_FALLBACK,
               "volume": int(round(s["volume"])), "rate": _sapi_rate(s["rate"]),
               "ssml": _ssml(job["text"], s["pitch"])}
    data = base64.b64encode(json.dumps(payload).encode("utf-8"))
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        # -EncodedCommand: the script reaches PowerShell byte for byte, with no
        # shell and no quoting rules in between. The text itself goes on stdin.
        script = base64.b64encode(_SAPI_SCRIPT.encode("utf-16-le")).decode("ascii")
        proc = subprocess.Popen(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
             "-EncodedCommand", script],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=flags)
    except OSError as exc:
        _log(f"PowerShell could not start: {exc}")
        return False
    with _LOCK:
        _CURRENT["proc"] = proc
        stopped = _JOBS[job_id]["state"] == "stopped"
    if stopped:
        proc.kill()
    # Generous: about 6 characters a second at the slowest rate, plus start-up.
    budget = 60 + len(job["text"]) / (6 * max(0.5, s["rate"]))
    try:
        out, err = proc.communicate(data, timeout=budget)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        _log(f"job {job_id[:8]} ran past {int(budget)} s and was ended")
        return False
    text = (out or b"").decode("utf-8", "replace")
    voice = next((line[6:].strip() for line in text.splitlines() if line.startswith("VOICE ")), "")
    if proc.returncode == 0 and "DONE" in text:
        _log(f"spoke {len(job['text'])} characters for user {job['user']} with {voice or 'a female voice'}")
        return True
    if "NO-FEMALE-VOICE" in text:
        _log("no female Windows voice for this language is installed; she stays silent")
    elif job["state"] != "stopped":
        detail = (err or b"").decode("utf-8", "replace").strip().splitlines()[-1:] or [f"exit {proc.returncode}"]
        _log(f"job {job_id[:8]} failed: {detail[0][:200]}")
    return False


def _worker():
    while True:
        with _LOCK:
            while not _QUEUE:
                _LOCK.wait()
            job_id = _QUEUE.popleft()
            job = _JOBS.get(job_id)
            if not job or job["state"] != "queued":
                continue
            job["state"] = "speaking"
            _CURRENT["job"] = job_id
        try:
            ok = _run(job_id, job)
        except Exception as exc:  # noqa: BLE001 - the worker must survive any job
            _log(f"job {job_id[:8]} raised: {exc}")
            ok = False
        with _LOCK:
            if job["state"] == "speaking":
                job["state"] = "done" if ok else "failed"
            _CURRENT["job"] = None
            _CURRENT["proc"] = None
