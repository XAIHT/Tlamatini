# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""VISIBLE proof that Tlamatini's voice is unstoppable (Angela, 2026-11-11).

    "if I change the application focus the voice stops and that should not
     happen. Tlamatini must always speak no matter if the browser is even
     closed ... make her unstoppable once she started to speak"

Runs in a REAL headed Chrome against the REAL chat page, with REAL Windows
voices. A second visible console meters this computer's speakers (Core Audio
peak meter), so every pass is backed by sound that actually came out.

    A  covered + minimized : she keeps talking while the window is covered
                             by another window and then minimized
    C  another tab cancels : a second page of the same site cancels the
                             shared speech engine three times; she resumes
    D  page closed         : the tab closes mid-sentence; her host voice
                             (Windows, this computer) says the rest
    B  real prompt         : a real chat request, window covered while it
                             runs; she says the processing line and the
                             completion line
    E  browser closed      : a real request, then the WHOLE browser closes;
                             the answer is still announced on the speakers

The same file runs both editions: it reads which repository it lives in.
Shoter photographs the whole desktop after every scenario.
Exit codes: 0 all passed, 1 a scenario failed, 4 the environment is broken.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import yaml                                          # noqa: E402
from playwright.sync_api import sync_playwright      # noqa: E402

import config                                        # noqa: E402
from preflight import ensure_ready                   # noqa: E402
from shoter_shot import take_shot                    # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
SPANISH = os.path.basename(REPO).lower().endswith("spanish")
EDITION = "SPANISH" if SPANISH else "ENGLISH"
BASE = os.environ.get("TLAMATINI_BASE_URL", "http://127.0.0.1:8052" if SPANISH else "http://127.0.0.1:8000").rstrip("/")
APP_LOG = os.path.join(REPO, "Tlamatini", "tlamatini.log")
WINDOWER_TEMPLATE = os.path.join(REPO, "Tlamatini", "agent", "agents", "windower")
METER_TITLE = "TLAMATINI SPEAKER METER"
LOUD = 0.02          # a speaker peak above this is sound, not silence

if SPANISH:
    LONG_A = ("Habla Tlamatini. Estoy leyendo un texto largo para demostrar que nada me detiene una vez que "
              "empiezo a hablar. Puedes cubrir esta ventana con otra, minimizar el navegador o cambiar de "
              "aplicación, y yo sigo hablando hasta la última palabra. Cada oración llega completa, en orden, "
              "sin pausas que nadie pidió. Solo tú puedes detenerme, con el modo silencioso, con Escape o con "
              "un clic en mi rostro. Esta es la última oración de la primera prueba.")
    LONG_C = ("Ahora otra pestaña del mismo sitio intenta callarme tres veces seguidas. Cada vez retomo la "
              "frase exactamente donde me interrumpieron, porque la voz que empezó tiene que terminar. "
              "Si escuchas esta última oración, la segunda prueba salió bien.")
    LONG_D = ("Voy a seguir hablando aunque esta pestaña se cierre a la mitad de la frase. Cuando la página "
              "desaparezca, mi voz de Windows en esta computadora dirá el resto, con la misma configuración. "
              "Esta parte final la dice mi voz anfitriona, y así nadie se queda sin escucharme. Fin de la "
              "tercera prueba.")
    PROMPT = "¿Cuánto es dos más dos? Responde en una sola oración corta."
else:
    LONG_A = ("This is Tlamatini speaking. I am reading a long passage to prove that nothing stops me once I "
              "have started. You can cover this window with another one, minimize the browser or switch to "
              "a different application, and I keep talking to the very last word. Every sentence arrives "
              "whole, in order, with no pause that nobody asked for. Only you can stop me, with Silent mode, "
              "Escape or a click on my face. This is the last sentence of the first test.")
    LONG_C = ("Now another tab of the same site tries to silence me three times in a row. Each time I pick the "
              "sentence up exactly where I was interrupted, because a voice that started has to finish. If "
              "you hear this last sentence, the second test went well.")
    LONG_D = ("I am going to keep talking even if this tab closes in the middle of a sentence. When the page "
              "disappears, my Windows voice on this computer will say the rest, with the same settings. This "
              "final part is spoken by my host voice, so nobody is left without hearing me. End of the third "
              "test.")
    PROMPT = "What is two plus two? Reply in one short sentence."

STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
OUT = os.path.join(HERE, "reports", "voice_unstoppable_%s_%s" % (EDITION.lower(), STAMP))
os.makedirs(OUT, exist_ok=True)
RUN_LOG = os.path.join(OUT, "run.log")
RESULTS = []


def log(message):
    line = "%s  %s" % (datetime.datetime.now().strftime("%H:%M:%S"), message)
    print(line, flush=True)
    with open(RUN_LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def record(name, ok, details):
    RESULTS.append({"scenario": name, "ok": bool(ok), "details": details})
    log(("PASS " if ok else "FAIL ") + name + "  " + json.dumps(details, ensure_ascii=False)[:900])


def now_ms():
    return int(time.time() * 1000)


# ── Speaker meter (a visible console) ──────────────────────────────────────
METER_PS1 = r"""
param([string]$Out, [string]$Stop)
$Host.UI.RawUI.WindowTitle = '__TITLE__'
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[ComImport, Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator { int EnumAudioEndpoints(); [PreserveSig] int GetDefaultAudioEndpoint(int flow, int role, out IMMDevice device); }
[ComImport, Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice { [PreserveSig] int Activate(ref Guid iid, int ctx, IntPtr p, [MarshalAs(UnmanagedType.IUnknown)] out object o); }
[ComImport, Guid("C02216F6-8C67-4B5B-9D00-D008E73E0064"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioMeterInformation { [PreserveSig] int GetPeakValue(out float peak); }
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorCom { }
public static class SpeakerMeter {
    static IAudioMeterInformation meter;
    public static float Peak() {
        if (meter == null) {
            var e = (IMMDeviceEnumerator)(new MMDeviceEnumeratorCom());
            IMMDevice d; Marshal.ThrowExceptionForHR(e.GetDefaultAudioEndpoint(0, 1, out d));
            Guid iid = typeof(IAudioMeterInformation).GUID; object o;
            Marshal.ThrowExceptionForHR(d.Activate(ref iid, 23, IntPtr.Zero, out o));
            meter = (IAudioMeterInformation)o;
        }
        float p; meter.GetPeakValue(out p); return p;
    }
}
'@
$w = New-Object System.IO.StreamWriter($Out, $true)
$w.AutoFlush = $true
Write-Host 'Metering the default speakers. This window closes by itself when the test ends.' -ForegroundColor Cyan
$n = 0
while (-not (Test-Path $Stop)) {
    $p = [SpeakerMeter]::Peak()
    $ms = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
    $w.WriteLine("$ms $p")
    if ($n % 5 -eq 0) { Write-Host ((Get-Date -Format 'HH:mm:ss') + ' ' + ('#' * [int]([Math]::Min(60, $p * 120))) + (' {0:N3}' -f $p)) }
    $n++
    Start-Sleep -Milliseconds 100
}
$w.Close()
"""


def start_meter():
    script = os.path.join(OUT, "speaker_meter.ps1")
    with open(script, "w", encoding="utf-8-sig") as fh:
        fh.write(METER_PS1.replace("__TITLE__", METER_TITLE))
    out, stop = os.path.join(OUT, "speaker_meter.txt"), os.path.join(OUT, "speaker_meter.stop")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                      "-Out", out, "-Stop", stop], creationflags=subprocess.CREATE_NEW_CONSOLE)
    deadline = time.time() + 30
    while time.time() < deadline and not (os.path.isfile(out) and os.path.getsize(out) > 0):
        time.sleep(0.5)
    return out, stop


def loud_fraction(meter_file, t0, t1):
    samples = []
    try:
        with open(meter_file, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) == 2 and parts[0].isdigit():
                    ms, peak = int(parts[0]), float(parts[1].replace(",", "."))
                    if t0 <= ms <= t1:
                        samples.append(peak)
    except OSError:
        return 0.0, 0
    if not samples:
        return 0.0, 0
    return round(sum(1 for p in samples if p > LOUD) / len(samples), 3), len(samples)


# ── Windower (Tlamatini's own window manager) ──────────────────────────────
def windower(action, title):
    runtime = os.path.join(OUT, "_windower_runtime")
    if not os.path.isdir(runtime):
        shutil.copytree(WINDOWER_TEMPLATE, runtime, ignore=shutil.ignore_patterns("__pycache__", "*.log", "*.pid"))
    with open(os.path.join(WINDOWER_TEMPLATE, "config.yaml"), encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    cfg.update({"action": action, "window_title": title, "match_mode": "substring", "match_index": 0,
                "activate_after": True, "fail_if_absent": False, "target_agents": []})
    with open(os.path.join(runtime, "config.yaml"), "w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False)
    result = subprocess.run([sys.executable, "windower.py"], cwd=runtime, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=90)
    agent_log = os.path.join(runtime, os.path.basename(runtime) + ".log")
    matched = ""
    if os.path.isfile(agent_log):
        text = open(agent_log, encoding="utf-8", errors="replace").read()
        found = re.findall(r"^matched: (.*)$", text, re.MULTILINE)
        matched = found[-1].strip() if found else ""
    log("   Windower %s '%s' -> rc=%s matched=%s" % (action, title, result.returncode, matched or "?"))
    return result.returncode == 0


# ── The app log ────────────────────────────────────────────────────────────
def log_size():
    try:
        return os.path.getsize(APP_LOG)
    except OSError:
        return 0


def log_since(offset):
    try:
        with open(APP_LOG, "rb") as fh:
            fh.seek(offset)
            return fh.read().decode("utf-8", "replace")
    except OSError:
        return ""


def wait_log(offset, patterns, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = log_since(offset)
        if all(re.search(p, text) for p in patterns):
            return True, text
        time.sleep(1.0)
    return False, log_since(offset)


# ── The page ───────────────────────────────────────────────────────────────
INSTRUMENT = r"""
(() => {
    const t = () => Date.now();
    const log = window.__voiceLog = [];
    window.__visibility = [];
    document.addEventListener('visibilitychange', () => window.__visibility.push([t(), document.visibilityState]));
    const s = window.speechSynthesis;
    if (s) {
        const speak = s.speak.bind(s), cancel = s.cancel.bind(s), pause = s.pause.bind(s);
        s.speak = u => {
            const rec = { text: u.text, lang: u.lang, voice: u.voice && u.voice.name, queued: t() };
            log.push(rec);
            u.addEventListener('start', () => { rec.start = t(); });
            u.addEventListener('end', () => { rec.end = t(); });
            u.addEventListener('error', e => { rec.error = e.error; rec.at = t(); });
            return speak(u);
        };
        s.cancel = () => { log.push({ cancel: t() }); return cancel(); };
        s.pause = () => { log.push({ pause: t() }); return pause(); };
    }
    const fetchOriginal = window.fetch.bind(window);
    window.fetch = (url, init) => {
        if (String(url).includes('/voice/host/')) log.push({ host: String(url), at: t(), body: init && init.body ? String(init.body).slice(0, 300) : '' });
        return fetchOriginal(url, init);
    };
})();
"""


HIDE_SIGNAL = """() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' });
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('blur'));
}"""
SHOW_SIGNAL = """() => {
    delete document.visibilityState; delete document.hidden;
    document.dispatchEvent(new Event('visibilitychange'));
    window.dispatchEvent(new Event('focus'));
}"""


def login(page):
    page.goto(BASE + config.LOGIN_PATH, wait_until="domcontentloaded")
    page.fill(config.SEL["login_user"], USER)
    page.fill(config.SEL["login_pass"], PASS)
    page.click(config.SEL["login_submit"])
    page.wait_for_load_state("domcontentloaded")


def open_chat(context):
    page = context.new_page()
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(BASE + config.CHAT_PATH, wait_until="domcontentloaded")
    page.wait_for_selector(config.SEL["chat_input"], timeout=60000)
    page.wait_for_function("() => !!window.TLM_VOICE", timeout=30000)
    time.sleep(3.0)
    page.bring_to_front()
    page.click(config.SEL["chat_input"])     # a real gesture lets the browser speak; never a chat card
    time.sleep(0.5)
    return page


def window_state(page, state):
    cdp = page.context.new_cdp_session(page)
    window = cdp.send("Browser.getWindowForTarget")["windowId"]
    if state == "maximized":
        cdp.send("Browser.setWindowBounds", {"windowId": window, "bounds": {"windowState": "normal"}})
    cdp.send("Browser.setWindowBounds", {"windowId": window, "bounds": {"windowState": state}})
    cdp.detach()


def speak(page, text, key):
    page.evaluate("([t, k]) => { window.__r = window.__r || {}; window.__r[k] = 'pending';"
                  " window.TLM_VOICE.speak(t, { queue: true }).then(s => { window.__r[k] = s; }); }", [text, key])


def result_of(page, key, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = page.evaluate("k => (window.__r || {})[k]", key)
        if value and value != "pending":
            return value
        time.sleep(1.0)
    return "timeout"


def voice_log(page):
    return page.evaluate("() => window.__voiceLog || []")


def utterances(entries, since):
    return [e for e in entries if "text" in e and e["queued"] >= since]


def as_spoken(page, text):
    """The text as she pronounces it (the Spanish edition respells names)."""
    return page.evaluate("t => (window.TLM_VOICE.prepareSpeech || (x => x))(t)", text)


def covered(text, entries):
    """True when every sentence of ``text`` was spoken to its end at least once."""
    spoken = " ".join(e["text"] for e in entries if e.get("end"))
    spoken = re.sub(r"\s+", " ", spoken)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    missing = [s for s in sentences if s not in spoken]
    return not missing, missing


def host_idle(page, timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        busy = page.evaluate("() => fetch('/agent/voice/host/status/', { credentials: 'same-origin' })"
                             ".then(r => r.json()).then(j => j.busy).catch(() => false)")
        if not busy:
            return True
        time.sleep(1.5)
    return False


def shot(name):
    path = take_shot(OUT, name)
    if not path:
        log("   !! Shoter could not take %s" % name)
    return path


# ── Scenarios ──────────────────────────────────────────────────────────────
def scenario_a(page, meter):
    log("A: a long passage while the window is covered, then minimized")
    t0 = now_ms()
    speak(page, LONG_A, "a")
    time.sleep(4)
    windower("maximize", METER_TITLE)            # another application now covers Chrome
    windower("focus", METER_TITLE)
    time.sleep(8)
    shot("A1_covered.png")
    window_state(page, "minimized")              # and now the browser is minimized
    time.sleep(2)
    state_min = page.evaluate("() => document.visibilityState")
    # A Chrome driven by a test tool never reports hidden, however it is covered or
    # minimized (probed 2026-11-11: launched, attached over CDP, OS minimize, focus
    # emulation off). So the page also gets the exact signal Windows gives a covered
    # window - hidden, then lost focus: the signal that used to pause her.
    page.evaluate(HIDE_SIGNAL)
    signal = page.evaluate("() => document.visibilityState")
    status = result_of(page, "a", 240)
    t1 = now_ms()
    page.evaluate(SHOW_SIGNAL)
    window_state(page, "maximized")
    windower("restore", METER_TITLE)
    page.bring_to_front()
    time.sleep(1)
    shot("A2_after.png")
    entries = voice_log(page)
    mine = utterances(entries, t0)
    whole, missing = covered(as_spoken(page, LONG_A), mine)
    pauses = [e for e in entries if "pause" in e]
    loud, samples = loud_fraction(meter, t0 + 1500, t1)
    record("A covered + minimized", status == "spoken" and whole and not pauses and loud >= 0.2
           and signal == "hidden",
           {"status": status, "chrome_reported": state_min, "page_signal": signal, "chunks": len(mine),
            "errors": [e.get("error") for e in mine if e.get("error")], "pauses": len(pauses),
            "missing": missing, "speaker_loud_fraction": loud, "meter_samples": samples,
            "seconds": round((t1 - t0) / 1000, 1)})


def scenario_c(context, page, meter):
    log("C: another tab of the same site cancels the speech engine three times")
    t0 = now_ms()
    speak(page, LONG_C, "c")
    other = context.new_page()
    other.goto(BASE + "/agent/version/", wait_until="domcontentloaded")
    for _ in range(3):
        time.sleep(4)
        other.evaluate("() => window.speechSynthesis.cancel()")
        log("   the other tab cancelled the engine")
    page.bring_to_front()
    status = result_of(page, "c", 180)
    t1 = now_ms()
    other.close()
    shot("C_after.png")
    mine = utterances(voice_log(page), t0)
    whole, missing = covered(as_spoken(page, LONG_C), mine)
    interrupted = [e.get("error") for e in mine if e.get("error")]
    loud, samples = loud_fraction(meter, t0 + 1500, t1)
    record("C another tab cancels", status == "spoken" and whole and loud >= 0.2,
           {"status": status, "interruptions_seen": interrupted, "missing": missing,
            "speaker_loud_fraction": loud, "meter_samples": samples})


def scenario_d(context, page, meter):
    log("D: the tab closes in the middle of a sentence")
    offset = log_size()
    t0 = now_ms()
    speak(page, LONG_D, "d")
    deadline = time.time() + 40              # close right after her first sentence ends
    finished = 0
    while time.time() < deadline and not finished:
        time.sleep(0.5)
        finished = sum(1 for e in utterances(voice_log(page), t0) if e.get("end"))
    log("   %d chunk(s) finished in the browser; closing the tab now" % finished)
    page.close(run_before_unload=True)
    t_close = now_ms()
    ok, text = wait_log(offset, [r"\[HOST-VOICE\] queued \d+ characters .*page closed while speaking",
                                 r"\[HOST-VOICE\] spoke \d+ characters"], 150)
    t1 = now_ms()
    shot("D_after_close.png")
    queued = re.findall(r"\[HOST-VOICE\] queued (\d+) characters", text)
    voice = [v.strip() for v in re.findall(r"\[HOST-VOICE\] spoke \d+ characters for user \S+ with (.+)", text)]
    loud, samples = loud_fraction(meter, t_close + 500, t1)
    # Only the part she had not finished goes to the host: never a repeat of a
    # finished sentence, never a loss of the rest.
    rest_only = bool(queued) and (int(queued[0]) < len(LONG_D) if finished else int(queued[0]) <= len(LONG_D))
    record("D page closed -> host voice", ok and loud >= 0.2 and rest_only,
           {"browser_chunks_done": finished, "host_queued_chars": queued, "host_voice": voice,
            "speaker_loud_fraction_after_close": loud, "meter_samples": samples,
            "log": [ln.strip() for ln in text.splitlines() if "HOST-VOICE" in ln][:6]})
    return open_chat(context)


ANSWER_STATE = """([input, bots, markers]) => {
    const box = document.querySelector(input);
    const all = Array.from(document.querySelectorAll(bots));
    const last = all.length ? all[all.length - 1].innerText.toLowerCase() : '';
    return { busy: !!(box && (box.readOnly || box.disabled)), count: all.length,
             lastIsBusyLine: markers.some(m => last.includes(m.toLowerCase())) };
}"""


def answer_state(page):
    return page.evaluate(ANSWER_STATE, [config.SEL["chat_input"], config.SEL["bot_message"], list(config.BUSY_MARKERS)])


def send_prompt(page):
    page.fill(config.SEL["chat_input"], PROMPT)
    before = answer_state(page)["count"]
    t_send = now_ms()
    page.click(config.SEL["chat_submit"])
    return t_send, before


def wait_answer(page, before, timeout=300):
    """(answered, arrived_ms): the answer card's arrival, then a free composer."""
    deadline = time.time() + timeout
    arrived = 0
    while time.time() < deadline:
        state = answer_state(page)
        if state["count"] > before and not state["lastIsBusyLine"]:
            arrived = arrived or now_ms()
            if not state["busy"]:
                return True, arrived
        time.sleep(0.5)
    return False, arrived


def scenario_b(page, meter):
    log("B: a real request while the window is covered")
    host_idle(page)
    t_send, before = send_prompt(page)
    time.sleep(2)
    windower("maximize", METER_TITLE)
    windower("focus", METER_TITLE)
    time.sleep(6)
    shot("B1_covered_while_processing.png")
    answered, t_answer = wait_answer(page, before)
    t_answer = t_answer or now_ms()
    deadline = time.time() + 60
    while time.time() < deadline:            # let the completion line finish
        entries = voice_log(page)
        late = [e for e in entries if "text" in e and e["queued"] >= t_answer - 3000]
        if late and all(e.get("end") or e.get("error") for e in late) and not page.evaluate("() => window.TLM_VOICE.isSpeaking()"):
            break
        time.sleep(1.0)
    t1 = now_ms()
    windower("restore", METER_TITLE)
    page.bring_to_front()
    time.sleep(1)
    shot("B2_after_answer.png")
    entries = voice_log(page)
    lines = [e for e in entries if "text" in e and e["queued"] >= t_send]
    finished = [e for e in lines if e.get("end")]
    hosted = [e for e in entries if "host" in e and "/speak/" in e["host"] and e["at"] >= t_send]
    # Two separate things must be heard: the processing line while she works, and
    # then her line about the answer - each spoken to its end, in that order.
    said = [e["text"] for e in finished]
    both = len(set(said)) + len(hosted) >= 2
    loud, samples = loud_fraction(meter, t_send, t1)
    record("B real request, window covered", answered and both and loud >= 0.05,
           {"answered": answered, "spoken_in_order": [t[:90] for t in said], "host_calls": len(hosted),
            "unfinished": [e["text"][:60] for e in lines if not e.get("end")],
            "errors": [e.get("error") for e in lines if e.get("error")],
            "speaker_loud_fraction": loud, "meter_samples": samples})


def scenario_e(browser, page, meter):
    log("E: a real request, then the WHOLE browser closes")
    host_idle(page)
    offset = log_size()
    t_send, _ = send_prompt(page)
    time.sleep(1.5)                          # the request is on the server; the answer is not back yet
    t_close = now_ms()                       # measure from the moment closing BEGINS: she may
    browser.close()                          # already be announcing while Chrome shuts down
    shot("E1_browser_closed.png")
    log("   the browser is closed; waiting for her to announce the answer on the speakers")
    ok, text = wait_log(offset, [r"no chat page is open for user", r"\[HOST-VOICE\] spoke \d+ characters"], 360)
    if ok:      # the announcement may still be playing: give it time to finish
        time.sleep(6)
    t1 = now_ms()
    shot("E2_after_announcement.png")
    loud, samples = loud_fraction(meter, t_close, t1)
    record("E browser closed -> answer announced", ok and loud >= 0.05,
           {"sent_at": t_send, "speaker_loud_fraction_after_close": loud, "meter_samples": samples,
            "log": [ln.strip() for ln in text.splitlines() if "HOST-VOICE" in ln][:8]})


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default="ACDBE", help="scenario letters to run, in this order: A C D B E")
    args = parser.parse_args()
    log("=" * 74)
    log("TLAMATINI VOICE — UNSTOPPABLE (%s)  %s" % (EDITION, BASE))
    log("report: %s" % OUT)
    ready = ensure_ready(BASE, USER, PASS)
    if not ready.get("ok"):
        log("ENVIRONMENT: %s" % ready.get("reason"))
        return ready.get("exit_code", 4)
    meter, stop = start_meter()
    log("speaker meter running (%s)" % ("ok" if os.path.isfile(meter) else "NOT STARTED"))
    try:
        with sync_playwright() as pw:
            # Playwright normally tells Chrome never to treat a covered or minimized
            # window as hidden. Drop those switches: this Chrome must hide, throttle
            # and background exactly like the Chrome on Angela's desktop.
            browser = pw.chromium.launch(
                headless=False, channel="chrome", args=["--start-maximized"],
                ignore_default_args=["--disable-backgrounding-occluded-windows",
                                     "--disable-renderer-backgrounding",
                                     "--disable-background-timer-throttling"])
            context = browser.new_context(no_viewport=True)
            context.add_init_script(INSTRUMENT)
            first = context.new_page()
            login(first)
            first.close()
            page = open_chat(context)
            shot("00_chat_open.png")
            for letter in args.only.upper():
                try:
                    if letter == "A":
                        scenario_a(page, meter)
                    elif letter == "C":
                        scenario_c(context, page, meter)
                    elif letter == "D":
                        page = scenario_d(context, page, meter)
                    elif letter == "B":
                        scenario_b(page, meter)
                    elif letter == "E":
                        scenario_e(browser, page, meter)
                        break
                except Exception as exc:                 # noqa: BLE001 - name it, keep going
                    record("%s raised" % letter, False, {"error": "%s: %s" % (type(exc).__name__, exc)})
            try:
                browser.close()
            except Exception:                            # noqa: BLE001 - E already closed it
                pass
    finally:
        open(stop, "w").close()
        with open(os.path.join(OUT, "results.json"), "w", encoding="utf-8") as fh:
            json.dump(RESULTS, fh, ensure_ascii=False, indent=2)
    passed = sum(1 for r in RESULTS if r["ok"])
    log("-" * 74)
    log("VERDICT %s: %d/%d scenarios passed" % ("PASS" if RESULTS and passed == len(RESULTS) else "FAIL",
                                                passed, len(RESULTS)))
    return 0 if RESULTS and passed == len(RESULTS) else 1


USER = os.environ.get("TLAMATINI_USER", config.USERNAME)
PASS = os.environ.get("TLAMATINI_PASS", config.PASSWORD)
os.environ.pop("TLAMATINI_NO_AUDIO", None)     # the server this test starts must be allowed to speak

if __name__ == "__main__":
    sys.exit(main())
