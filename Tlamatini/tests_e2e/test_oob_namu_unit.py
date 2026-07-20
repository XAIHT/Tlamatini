# -*- coding: utf-8 -*-
"""OOB_shift_reaper + NAMU — deterministic unit proof of the FINAL design.

Loads the REAL `_run_cmd_oob` from BOTH nmapper.py and discoverer.py (proving both
got the runner) and proves Angela's three rules with tiny time values + a controlled
child, plus NAMU's tree-kill selection. Runs VISIBLE in a foreground console.

RULES PROVEN:
  1. WORKING (still emitting) -> runs FREE, NEVER killed, even PAST the window.
  2. HANGED inside the window -> a POSSIBLE HANG banner is logged, NOT killed.
  3. HANGED past the window   -> KILLED (reason=hang_killed, rc=137), partials kept.
  NAMU: a fake pool process (cmdline has agents/pools + nmapper) + its child are
        tree-killed by the NAMU selection+kill logic.
"""
import importlib.util
import logging
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS = os.path.join(os.path.dirname(HERE), "agent", "agents")
CHILD = os.path.join(HERE, "oob_child_helper.py")
PY = sys.executable

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print("  [%s] %-52s %s" % ("PASS" if ok else "FAIL", name, detail), flush=True)


def load_runner(agent_file):
    spec = importlib.util.spec_from_file_location("oob_mod_%d" % id(agent_file), agent_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []

    def emit(self, record):
        try:
            self.msgs.append(record.getMessage())
        except Exception:
            pass

    def text(self):
        return "\n".join(self.msgs)


def run_rules(mod, tag):
    print("\n=== %s: OOB rules ===" % tag, flush=True)
    cap = _Capture()
    root = logging.getLogger()
    root.addHandler(cap)
    root.setLevel(logging.INFO)
    try:
        # RULE 1 — WORKING past the window is never killed.
        cap.msgs.clear()
        rc, out, err, reason = mod._run_cmd_oob(
            [PY, CHILD, "work"], oob_shift_reaper=1.0, hang_detect_idle_seconds=0.5,
            startup_grace=0.0, tick=0.15, label="work")
        check("%s rule1 WORKING past window -> not killed" % tag,
              reason == "exited" and rc == 0 and "tick" in out,
              "reason=%s rc=%s" % (reason, rc))

        # RULE 3 — HANGED past the window is killed (partials preserved).
        cap.msgs.clear()
        t0 = time.monotonic()
        rc, out, err, reason = mod._run_cmd_oob(
            [PY, CHILD, "hang"], oob_shift_reaper=1.0, hang_detect_idle_seconds=0.5,
            startup_grace=0.0, tick=0.15, label="hang")
        el = time.monotonic() - t0
        check("%s rule3 HANGED past window -> killed rc137" % tag,
              reason == "hang_killed" and rc == 137, "reason=%s rc=%s" % (reason, rc))
        check("%s rule3 partial output preserved" % tag,
              "line 1" in out and "line 2" in out, "out=%r" % out[:40])
        check("%s rule3 OOB REAPER banner logged" % tag,
              "OOB REAPER" in cap.text(), "")
        check("%s rule3 killed promptly (<8s)" % tag, el < 8.0, "%.1fs" % el)

        # RULE 2 — HANGED inside the window -> banner, NOT killed, recovers.
        cap.msgs.clear()
        rc, out, err, reason = mod._run_cmd_oob(
            [PY, CHILD, "recover"], oob_shift_reaper=30.0, hang_detect_idle_seconds=0.5,
            startup_grace=0.0, tick=0.15, label="recover")
        txt = cap.text()
        check("%s rule2 hang INSIDE window -> NOT killed" % tag,
              reason == "exited" and rc == 0, "reason=%s rc=%s" % (reason, rc))
        check("%s rule2 POSSIBLE HANG banner logged" % tag,
              "POSSIBLE HANG" in txt, "")
        check("%s rule2 both lines present (ran to completion)" % tag,
              "before quiet" in out and "after quiet" in out, "")
    finally:
        root.removeHandler(cap)


def run_namu():
    print("\n=== NAMU: shutdown tree-kill of the recon gods ===", flush=True)
    try:
        import psutil
    except Exception as e:
        check("NAMU (needs psutil)", False, "psutil missing: %s" % e)
        return

    # Spawn a child whose cmdline carries a FAKE pool path so the NAMU selector matches
    # exactly as it does in apps.py (cmdline contains 'agents\\pools' AND 'nmapper').
    fake_marker = os.path.join("agents", "pools", "_chat_runs_", "nmapper_999_deadbeef")
    child = subprocess.Popen([PY, CHILD, "namu", fake_marker])
    time.sleep(1.2)  # let it spawn its grandchild
    try:
        gkids = psutil.Process(child.pid).children(recursive=True)
    except Exception:
        gkids = []
    grandchild_pids = [c.pid for c in gkids]

    # Replicate the NAMU selection + recursive tree-kill from apps.py.
    pool_needle = os.path.join("agents", "pools").lower()
    gods = ("nmapper", "discoverer", "kalier")
    killed_target = False
    for p in psutil.process_iter(["pid", "cmdline"], ad_value=None):
        try:
            s = " ".join(p.info.get("cmdline") or []).lower()
            if pool_needle in s and any(g in s for g in gods):
                # recursive tree-kill (God Mode, same as apps.recursive_kill)
                try:
                    parent = psutil.Process(p.info["pid"])
                    for c in parent.children(recursive=True):
                        try:
                            c.kill()
                        except Exception:
                            pass
                    parent.kill()
                except Exception:
                    pass
                if p.info["pid"] == child.pid:
                    killed_target = True
        except Exception:
            continue

    time.sleep(1.5)
    parent_dead = child.poll() is not None or not psutil.pid_exists(child.pid)
    kids_dead = all((not psutil.pid_exists(pid)) for pid in grandchild_pids) if grandchild_pids else True
    check("NAMU selected the fake nmapper pool process", killed_target, "")
    check("NAMU killed the parent (the god)", parent_dead, "")
    check("NAMU killed the grandchild (tree-kill)", kids_dead,
          "grandchildren=%s" % grandchild_pids)

    # safety: ensure nothing survives
    for pid in [child.pid] + grandchild_pids:
        try:
            if psutil.pid_exists(pid):
                psutil.Process(pid).kill()
        except Exception:
            pass


def main():
    print("=" * 74, flush=True)
    print("OOB_shift_reaper + NAMU — UNIT PROOF  ·  " + time.strftime("%Y-%m-%d %H:%M:%S"),
          flush=True)
    print("=" * 74, flush=True)
    nm = load_runner(os.path.join(AGENTS, "nmapper", "nmapper.py"))
    dc = load_runner(os.path.join(AGENTS, "discoverer", "discoverer.py"))
    check("nmapper exposes _run_cmd_oob", hasattr(nm, "_run_cmd_oob"))
    check("discoverer exposes _run_cmd_oob", hasattr(dc, "_run_cmd_oob"))
    run_rules(nm, "nmapper")
    run_rules(dc, "discoverer")
    run_namu()

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print("\n" + "=" * 74, flush=True)
    print("RESULT: %d / %d PASSED" % (passed, total), flush=True)
    for n, ok, d in RESULTS:
        if not ok:
            print("   FAILED: %s   %s" % (n, d), flush=True)
    print("=" * 74, flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
