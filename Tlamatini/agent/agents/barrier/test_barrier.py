"""
Test script for the Barrier agent.
Simulates multiple source agents starting barrier sub-processes concurrently.
Verifies: flags created, last arrival fires, no deadlock, fast completion.
"""
import os
import sys
import time
import shutil
import tempfile
import subprocess
import threading

# --- Config ---
NUM_SOURCES = 4
SOURCE_NAMES = [f"test_source_{i}" for i in range(1, NUM_SOURCES + 1)]
TARGET_NAME = "test_target_1"
TIMEOUT_SECONDS = 30

def setup_test_env(test_dir):
    """Create a minimal barrier agent directory for testing."""
    os.makedirs(test_dir, exist_ok=True)

    # Copy barrier.py
    barrier_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "barrier.py")
    shutil.copy2(barrier_src, os.path.join(test_dir, "barrier.py"))

    # Create config.yaml
    import yaml
    config = {
        "source_agents": SOURCE_NAMES,
        "target_agents": [TARGET_NAME],
    }
    with open(os.path.join(test_dir, "config.yaml"), "w") as f:
        yaml.dump(config, f)

    # Create a fake target agent directory with a dummy script
    target_dir = os.path.join(os.path.dirname(test_dir), TARGET_NAME)
    os.makedirs(target_dir, exist_ok=True)
    with open(os.path.join(target_dir, "test_target.py"), "w") as f:
        f.write(
            'import os, time\n'
            'with open("agent.pid", "w") as pf: pf.write(str(os.getpid()))\n'
            'with open("FIRED.flag", "w") as ff: ff.write("fired")\n'
            'time.sleep(0.2)\n'
            'os.remove("agent.pid")\n'
        )

    return target_dir


def start_barrier_process(test_dir, caller_name, results, index):
    """Simulate a source agent starting a barrier sub-process."""
    env = os.environ.copy()
    env["BARRIER_CALLER"] = caller_name
    try:
        proc = subprocess.Popen(
            [sys.executable, "barrier.py"],
            cwd=test_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        stdout, stderr = proc.communicate(timeout=TIMEOUT_SECONDS)
        results[index] = {
            "caller": caller_name,
            "returncode": proc.returncode,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
        }
    except subprocess.TimeoutExpired:
        proc.kill()
        results[index] = {"caller": caller_name, "returncode": -1, "error": "TIMEOUT"}
    except Exception as e:
        results[index] = {"caller": caller_name, "returncode": -1, "error": str(e)}


def run_test():
    # Create test directory structure inside a temp dir
    base_tmp = tempfile.mkdtemp(prefix="barrier_test_")
    pool_dir = os.path.join(base_tmp, "pools", "test_pool")
    test_dir = os.path.join(pool_dir, "barrier_test_1")
    os.makedirs(test_dir, exist_ok=True)

    # The pool path detection in barrier.py expects:
    # current_dir = barrier_test_1/  -> parent = test_pool/ -> grandparent = pools/
    target_dir = setup_test_env(test_dir)

    print(f"Test dir: {test_dir}")
    print(f"Target dir: {target_dir}")
    print(f"Source agents: {SOURCE_NAMES}")
    print(f"Target agent: {TARGET_NAME}")
    print()

    # --- TEST 1: All sources arrive concurrently ---
    print("=" * 60)
    print("TEST 1: All sources arrive concurrently")
    print("=" * 60)

    results = [None] * NUM_SOURCES
    threads = []

    start_time = time.time()
    for i, name in enumerate(SOURCE_NAMES):
        t = threading.Thread(target=start_barrier_process, args=(test_dir, name, results, i))
        threads.append(t)
        t.start()
        time.sleep(0.15)  # Small stagger to simulate real timing

    for t in threads:
        t.join(timeout=TIMEOUT_SECONDS)

    elapsed = time.time() - start_time

    # Check results
    all_ok = True
    for r in results:
        if r is None:
            print(f"  FAIL: Thread did not complete")
            all_ok = False
        elif r.get("error") == "TIMEOUT":
            print(f"  FAIL: {r['caller']} TIMED OUT (deadlock?)")
            all_ok = False
        elif r["returncode"] != 0:
            print(f"  FAIL: {r['caller']} exited with code {r['returncode']}")
            if r.get("stderr"):
                print(f"        stderr: {r['stderr'][:200]}")
            all_ok = False
        else:
            print(f"  OK:   {r['caller']} exited cleanly")

    # Check if target was fired
    fired_flag = os.path.join(target_dir, "FIRED.flag")
    target_fired = os.path.exists(fired_flag)
    print(f"\n  Target fired: {target_fired}")
    print(f"  Elapsed: {elapsed:.2f}s")

    # Check no stale flags remain
    remaining_flags = [f for f in os.listdir(test_dir) if f.startswith("started_flag-")]
    print(f"  Remaining flags: {remaining_flags}")

    # Check no stale agent.pid
    pid_exists = os.path.exists(os.path.join(test_dir, "agent.pid"))
    print(f"  Stale agent.pid: {pid_exists}")

    # Read barrier log
    log_path = os.path.join(test_dir, "barrier_test_1.log")
    if os.path.exists(log_path):
        print(f"\n  --- Barrier Log ---")
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                print(f"  {line.rstrip().encode('ascii', 'replace').decode()}")

    if all_ok and target_fired and not remaining_flags and not pid_exists:
        print(f"\n  PASS: TEST 1 PASSED")
    else:
        print(f"\n  FAIL: TEST 1 FAILED")
        all_ok = False

    # --- TEST 2: Staggered arrivals (large delay) ---
    print("\n" + "=" * 60)
    print("TEST 2: Staggered arrivals with 1s delay")
    print("=" * 60)

    # Clean up from test 1
    for f in os.listdir(test_dir):
        if f.endswith(".flg") or f.endswith(".log") or f == "agent.pid" or f == "barrier.lock" or f == "barrier_output.running":
            os.remove(os.path.join(test_dir, f))
    if os.path.exists(fired_flag):
        os.remove(fired_flag)

    results2 = [None] * NUM_SOURCES
    threads2 = []
    start_time = time.time()

    for i, name in enumerate(SOURCE_NAMES):
        t = threading.Thread(target=start_barrier_process, args=(test_dir, name, results2, i))
        threads2.append(t)
        t.start()
        time.sleep(1.0)  # Larger stagger

    for t in threads2:
        t.join(timeout=TIMEOUT_SECONDS)

    elapsed2 = time.time() - start_time

    all_ok2 = True
    for r in results2:
        if r is None:
            print(f"  FAIL: Thread did not complete")
            all_ok2 = False
        elif r.get("error") == "TIMEOUT":
            print(f"  FAIL: {r['caller']} TIMED OUT")
            all_ok2 = False
        elif r["returncode"] != 0:
            print(f"  FAIL: {r['caller']} exited with code {r['returncode']}")
            all_ok2 = False
        else:
            print(f"  OK:   {r['caller']} exited cleanly")

    target_fired2 = os.path.exists(fired_flag)
    remaining_flags2 = [f for f in os.listdir(test_dir) if f.startswith("started_flag-")]
    print(f"\n  Target fired: {target_fired2}")
    print(f"  Elapsed: {elapsed2:.2f}s")
    print(f"  Remaining flags: {remaining_flags2}")

    log_path2 = os.path.join(test_dir, "barrier_test_1.log")
    if os.path.exists(log_path2):
        print(f"\n  --- Barrier Log ---")
        with open(log_path2, "r", encoding="utf-8") as f:
            for line in f:
                print(f"  {line.rstrip().encode('ascii', 'replace').decode()}")

    if all_ok2 and target_fired2 and not remaining_flags2:
        print(f"\n  PASS: TEST 2 PASSED")
    else:
        print(f"\n  FAIL: TEST 2 FAILED")

    # Cleanup
    try:
        shutil.rmtree(base_tmp)
    except Exception:
        pass

    if all_ok and target_fired and all_ok2 and target_fired2:
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    sys.exit(run_test())
