# -*- coding: utf-8 -*-
"""Child process used by the OOB_shift_reaper unit test. Emits controlled output
patterns so the runner's 3 rules can be proven deterministically.

Modes (argv[1]):
  work    : print a line every 0.2s for ~3s, then exit 0        (rule 1: WORKING)
  hang    : print 2 lines, then sleep forever                   (rule 3: HANG)
  recover : print, go quiet ~1.0s, print again, exit 0          (rule 2: banner+recover)
  namu    : print once then sleep forever; spawn a grandchild   (NAMU tree-kill target)

argv[2..] are ignored markers (used to stamp a fake pool path into the cmdline).
"""
import subprocess
import sys
import time

mode = sys.argv[1] if len(sys.argv) > 1 else "work"

if mode == "work":
    for i in range(15):
        print("tick %d" % i, flush=True)
        time.sleep(0.2)
    sys.exit(0)

elif mode == "hang":
    print("line 1", flush=True)
    print("line 2", flush=True)
    time.sleep(60)

elif mode == "recover":
    print("before quiet", flush=True)
    time.sleep(1.0)
    print("after quiet", flush=True)
    sys.exit(0)

elif mode == "namu":
    # spawn a grandchild that also sleeps, so the tree-kill has something to reach
    try:
        subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    except Exception:
        pass
    print("namu child alive", flush=True)
    time.sleep(120)

else:
    sys.exit(3)
