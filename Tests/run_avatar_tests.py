r"""One-command, VISIBLE avatar regression for the real development Django app.

From the repository root: .\python\python.exe Tests\run_avatar_tests.py
Any Python with the project's Django dependencies also works.
Requires Node.js + Playwright. Existing project, PATH and Codex-bundled
runtimes are detected; nothing is silently downloaded or installed.
The published database is a session-free fixture. Live logins use Temp/.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "output/avatar_flash_fix/development_test.py"
RUNTIME = ROOT / "Temp/avatar_flash_fix"


def node_runtime():
    bundle = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node"
    candidates = [os.environ.get("TLAMATINI_TEST_NODE"), shutil.which("node"),
                  str(bundle / "bin/node.exe"), str(bundle / "bin/node")]
    node = next((p for p in candidates if p and Path(p).is_file()), None)
    if not node:
        raise RuntimeError("Node.js not found. Install Node.js or set TLAMATINI_TEST_NODE to its executable.")
    env = os.environ.copy()
    module = env.get("PLAYWRIGHT_MODULE")
    if not module:
        probe = subprocess.run([node, "-p", "require.resolve('playwright')"], cwd=ROOT, text=True, capture_output=True)
        if probe.returncode == 0:
            module = probe.stdout.strip()
        elif (bundle / "node_modules/playwright").is_dir():
            module = str(bundle / "node_modules/playwright")
    if not module:
        raise RuntimeError("Playwright for Node.js not found. Install it with npm install --no-save playwright, then npx playwright install chromium; or set PLAYWRIGHT_MODULE.")
    env["PLAYWRIGHT_MODULE"] = module
    probe = subprocess.run([node, "-e", "const fs=require('fs');const p=require(process.env.PLAYWRIGHT_MODULE);if(!fs.existsSync(p.chromium.executablePath()))process.exit(2)"], env=env, cwd=ROOT)
    if probe.returncode:
        raise RuntimeError("Playwright Chromium is missing. Run npx playwright install chromium for this Playwright installation.")
    return node, env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check dependencies without starting the app.")
    parser.add_argument("--prepare-only", action="store_true", help="Migrate the isolated DB, create user/changeme, collectstatic, then exit.")
    parser.add_argument("--auto-close", action="store_true", help="Close the visible browser and test server automatically after the tests pass.")
    args = parser.parse_args()
    if not importlib.util.find_spec("django"):
        raise RuntimeError("Django is missing from this Python. Run with the project's python/python.exe or install the project requirements.")
    node, env = node_runtime()
    print("Dependencies OK. Tests always run visibly, never headless.", flush=True)
    if args.check:
        return 0
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", 8001)) == 0:
            raise RuntimeError("Port 8001 is already in use. Close the previous avatar development test server before running this launcher. The frozen app on port 8000 is not touched.")
    subprocess.run([sys.executable, str(HELPER), "prepare"], cwd=ROOT, env=env, check=True)
    if args.prepare_only:
        return 0
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / "server.log").open("w", encoding="utf-8") as log:
        server = subprocess.Popen([sys.executable, "-u", str(HELPER), "serve"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise RuntimeError("Django stopped during startup; inspect Temp/avatar_flash_fix/server.log.")
                try:
                    with urlopen("http://127.0.0.1:8001/", timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.5)
            else:
                raise RuntimeError("Django did not become ready within 90 seconds. See Temp/avatar_flash_fix/server.log.")
            if args.auto_close:
                env["AVATAR_TEST_AUTOCLOSE"] = "1"
            print("Opening the visible browser. Login: user / changeme. Leave it visible during the 300-transition voice test.", flush=True)
            result = subprocess.run([node, str(ROOT / "Tests/test_avatar_visible.cjs")], cwd=ROOT, env=env)
            return result.returncode
        finally:
            if server.poll() is None:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print("Avatar test setup failed:", error, file=sys.stderr)
        raise SystemExit(1)
