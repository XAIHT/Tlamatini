# Tlamatini ↔ Kali Linux — Zero-Client Setup (Kalier)

**Who this is for:** Anyone (human or AI) who wants Tlamatini to drive Kali Linux
penetration-testing tools straight from the chat box. You type
*"Tlamatini, scan 10.0.0.5 and give me a report"* in Multi-Turn mode and Tlamatini
runs nmap on Kali, reads the output, and writes you a report — no Claude Desktop,
no Windows `client.py`, no MCP settings file.

> **What changed vs. the old Claude-Desktop guide**
> (`Claude-Desktop-KALI-MCP-Session.md`): the **client half is now embedded in
> Tlamatini**. The old setup needed a Windows `client.py` MCP bridge that Claude
> Desktop spawned. Tlamatini's built-in **Kalier** tool *is* that client — it POSTs
> directly to the Kali `server.py` over HTTP. So the Windows side is **zero steps**.
> You only paste the Linux block, tell Tlamatini the Kali box URL **once**, and chat.

---

## The whole thing, in 3 steps

```
            ┌──────────────────────────────────────────────────────────┐
 STEP 1     │  Paste the Linux block (below) into a Kali terminal.      │
 (Kali)     │  It installs the tools, writes server.py, opens the       │
            │  firewall, auto-starts on boot, and starts the server.    │
            └──────────────────────────────────────────────────────────┘
                                     │
            ┌──────────────────────────────────────────────────────────┐
 STEP 2     │  In Tlamatini: Config ▸ URLs ▸ "Kali server (Kalier)".    │
 (one-time) │  Set it to http://<KALI_IP>:5000  (the block prints the   │
            │  exact IP). If Kali is WSL2 on THIS Windows box, the       │
            │  default http://127.0.0.1:5000 usually already works —    │
            │  in that case you can SKIP this step entirely.            │
            └──────────────────────────────────────────────────────────┘
                                     │
            ┌──────────────────────────────────────────────────────────┐
 STEP 3     │  In the chat toolbar tick ✅ Multi-Turn and ✅ Exec Report.│
 (every     │  Then just ask:                                           │
  session)  │     "Tlamatini, scan the machine 10.0.0.5 and give me     │
            │      a report"                                            │
            └──────────────────────────────────────────────────────────┘
```

That's it. Tlamatini picks the right Kali tool, targets the configured box
automatically (you never repeat the Kali URL), runs it, and the **Exec Report**
table shows you exactly which commands fired with SUCCESS/FAILURE.

---

## Architecture (who talks to whom)

```
YOU  ──►  Tlamatini chat (Multi-Turn + Exec Report)
              │  the LLM calls the built-in `chat_agent_kalier` tool
              │  (Tlamatini IS the client — the embedded client.py replacement)
              ▼
          Kalier  ──HTTP POST──►  server.py on Kali  (port 5000)
              │                        │ runs the actual tool as a subprocess
              ▼                        ▼
   INI_SECTION_KALIER          nmap / gobuster / nikto / sqlmap /
   + Exec Report row           hydra / john / wpscan / enum4linux /
                               metasploit / arbitrary shell command
```

The Kali server URL lives **once** in Tlamatini's `config.json`
(`kali_server_url`, editable from **Config ▸ URLs**). Kalier auto-injects it on
every run, so a plain prompt works without ever naming the box. The LLM can still
override it for a one-off different box ("…on the Kali at 10.0.0.9").

---

## STEP 1 — Kali setup (copy-paste this whole block into a Kali terminal)

This installs every tool, writes the network-reachable `server.py`
(`0.0.0.0:5000` + a startup banner), creates a venv with just Flask (Tlamatini is
the client, so **no** `mcp`/`fastmcp`/`requests` are needed on Kali), opens the
firewall, adds a `@reboot` auto-start, starts the server, and prints the IP you'll
put into Tlamatini. Look for `==OK==` after each line.

```bash
sudo apt update && sudo apt install -y nmap gobuster dirb nikto sqlmap hydra john wpscan enum4linux metasploit-framework python3 python3-venv curl ufw && echo "==OK== PACKAGES DONE" || echo "==FAIL== PACKAGES"

for tool in nmap gobuster dirb nikto sqlmap hydra john wpscan enum4linux msfconsole python3 curl ufw; do command -v $tool &>/dev/null && echo "  OK  $tool" || echo "  XX  $tool MISSING"; done

mkdir -p ~/Development/Mcp-Kali-Server && echo "==OK== FOLDER READY"

cat > ~/Development/Mcp-Kali-Server/server.py << 'ENDOFFILE'
#!/usr/bin/env python3
import argparse, logging, os, re, shlex, subprocess, sys, traceback, threading, socket
from typing import Dict, Any
from flask import Flask, request, jsonify
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", handlers=[logging.StreamHandler(sys.stdout)])
logger = logging.getLogger(__name__)
API_PORT = int(os.environ.get("API_PORT", 5000))
DEBUG_MODE = os.environ.get("DEBUG_MODE", "0").lower() in ("1", "true", "yes", "y")
COMMAND_TIMEOUT = 180
app = Flask(__name__)
class CommandExecutor:
    def __init__(self, command, timeout=COMMAND_TIMEOUT):
        self.command = command; self.timeout = timeout
        self.use_shell = isinstance(command, str)
        self.process = None; self.stdout_data = ""; self.stderr_data = ""
        self.stdout_thread = None; self.stderr_thread = None
        self.return_code = None; self.timed_out = False
    def _read_stdout(self):
        for line in iter(self.process.stdout.readline, ''): self.stdout_data += line
    def _read_stderr(self):
        for line in iter(self.process.stderr.readline, ''): self.stderr_data += line
    def execute(self):
        logger.info(f"Executing command: {self.command}")
        try:
            self.process = subprocess.Popen(self.command, shell=self.use_shell, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
            self.stdout_thread = threading.Thread(target=self._read_stdout); self.stderr_thread = threading.Thread(target=self._read_stderr)
            self.stdout_thread.daemon = True; self.stderr_thread.daemon = True
            self.stdout_thread.start(); self.stderr_thread.start()
            try:
                self.return_code = self.process.wait(timeout=self.timeout)
                self.stdout_thread.join(); self.stderr_thread.join()
            except subprocess.TimeoutExpired:
                self.timed_out = True; self.process.terminate()
                try: self.process.wait(timeout=5)
                except subprocess.TimeoutExpired: self.process.kill()
                self.return_code = -1
            success = True if self.timed_out and (self.stdout_data or self.stderr_data) else (self.return_code == 0)
            return {"stdout": self.stdout_data, "stderr": self.stderr_data, "return_code": self.return_code, "success": success, "timed_out": self.timed_out, "partial_results": self.timed_out and (self.stdout_data or self.stderr_data)}
        except Exception as e:
            logger.error(traceback.format_exc())
            return {"stdout": self.stdout_data, "stderr": f"Error: {str(e)}\n{self.stderr_data}", "return_code": -1, "success": False, "timed_out": False, "partial_results": bool(self.stdout_data or self.stderr_data)}
def execute_command(command): return CommandExecutor(command).execute()
@app.route("/api/command", methods=["POST"])
def generic_command():
    try:
        params = request.json; command = params.get("command", "")
        if not command: return jsonify({"error": "Command parameter is required"}), 400
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/nmap", methods=["POST"])
def nmap():
    try:
        params = request.json; target = params.get("target", "")
        if not target: return jsonify({"error": "Target parameter is required"}), 400
        command = ["nmap"] + shlex.split(params.get("scan_type", "-sCV"))
        if params.get("ports"): command += ["-p", params["ports"]]
        if params.get("additional_args", "-T4 -Pn"): command += shlex.split(params.get("additional_args", "-T4 -Pn"))
        command.append(target); return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/gobuster", methods=["POST"])
def gobuster():
    try:
        params = request.json; url = params.get("url", ""); mode = params.get("mode", "dir")
        if not url: return jsonify({"error": "URL parameter is required"}), 400
        if mode not in ["dir","dns","fuzz","vhost"]: return jsonify({"error": f"Invalid mode: {mode}"}), 400
        command = ["gobuster", mode, "-u", url, "-w", params.get("wordlist", "/usr/share/wordlists/dirb/common.txt")]
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/dirb", methods=["POST"])
def dirb():
    try:
        params = request.json; url = params.get("url", "")
        if not url: return jsonify({"error": "URL parameter is required"}), 400
        command = ["dirb", url, params.get("wordlist", "/usr/share/wordlists/dirb/common.txt")]
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/nikto", methods=["POST"])
def nikto():
    try:
        params = request.json; target = params.get("target", "")
        if not target: return jsonify({"error": "Target parameter is required"}), 400
        command = ["nikto", "-h", target]
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/sqlmap", methods=["POST"])
def sqlmap():
    try:
        params = request.json; url = params.get("url", "")
        if not url: return jsonify({"error": "URL parameter is required"}), 400
        command = ["sqlmap", "-u", url, "--batch"]
        if params.get("data"): command += ["--data", params["data"]]
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/metasploit", methods=["POST"])
def metasploit():
    try:
        params = request.json; module = params.get("module", ""); options = params.get("options", {})
        if not module: return jsonify({"error": "Module parameter is required"}), 400
        if not re.match(r'^[a-zA-Z0-9/_-]+$', module): return jsonify({"error": "Invalid module name"}), 400
        rc = f"use {module}\n"
        for k, v in options.items():
            if not re.match(r'^[a-zA-Z0-9_]+$', str(k)): return jsonify({"error": f"Invalid option key: {k}"}), 400
            rc += f"set {k} {v}\n"
        rc += "exploit\n"
        with open("/tmp/mks_msf_resource.rc", "w") as f: f.write(rc)
        result = execute_command(["msfconsole", "-q", "-r", "/tmp/mks_msf_resource.rc"])
        try: os.remove("/tmp/mks_msf_resource.rc")
        except: pass
        return jsonify(result)
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/hydra", methods=["POST"])
def hydra():
    try:
        params = request.json; target = params.get("target",""); service = params.get("service","")
        if not target or not service: return jsonify({"error": "Target and service are required"}), 400
        username = params.get("username",""); username_file = params.get("username_file","")
        password = params.get("password",""); password_file = params.get("password_file","")
        if not (username or username_file) or not (password or password_file): return jsonify({"error": "Username and password required"}), 400
        command = ["hydra", "-t", "4"]
        if username: command += ["-l", username]
        elif username_file: command += ["-L", username_file]
        if password: command += ["-p", password]
        elif password_file: command += ["-P", password_file]
        command += [target, service]
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/john", methods=["POST"])
def john():
    try:
        params = request.json; hash_file = params.get("hash_file","")
        if not hash_file: return jsonify({"error": "Hash file parameter is required"}), 400
        command = ["john"]
        if params.get("format"): command.append(f"--format={params['format']}")
        command.append(f"--wordlist={params.get('wordlist','/usr/share/wordlists/rockyou.txt')}")
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        command.append(hash_file); return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/wpscan", methods=["POST"])
def wpscan():
    try:
        params = request.json; url = params.get("url","")
        if not url: return jsonify({"error": "URL parameter is required"}), 400
        command = ["wpscan", "--url", url]
        if params.get("additional_args"): command += shlex.split(params["additional_args"])
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/api/tools/enum4linux", methods=["POST"])
def enum4linux():
    try:
        params = request.json; target = params.get("target","")
        if not target: return jsonify({"error": "Target parameter is required"}), 400
        command = ["enum4linux"] + shlex.split(params.get("additional_args","-a")) + [target]
        return jsonify(execute_command(command))
    except Exception as e: return jsonify({"error": f"Server error: {str(e)}"}), 500
@app.route("/health", methods=["GET"])
def health_check():
    tools = {}
    for t in ["nmap","gobuster","dirb","nikto"]:
        try: tools[t] = execute_command(["which",t])["success"]
        except: tools[t] = False
    return jsonify({"status":"healthy","message":"Kali Linux Tools API Server is running","tools_status":tools,"all_essential_tools_available":all(tools.values())})
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "unknown"
def print_server_banner(ip, port):
    lan_ip = get_local_ip()
    tools = ["nmap","gobuster","dirb","nikto","sqlmap","msfconsole","hydra","john","wpscan","enum4linux"]
    rows = []
    for t in tools:
        ok = subprocess.run(["which",t], capture_output=True).returncode == 0
        rows.append(f"  {chr(27)}[92m OK {chr(27)}[0m  {t}" if ok else f"  {chr(27)}[91m XX {chr(27)}[0m  {t}")
    print(f"""\n{chr(27)}[91m  KALI MCP — Tlamatini bridge{chr(27)}[0m\n{chr(27)}[90m{"-"*58}{chr(27)}[0m\n  {chr(27)}[93m> Listening :{chr(27)}[0m  {ip}:{port}\n  {chr(27)}[93m> LAN IP    :{chr(27)}[0m  {lan_ip}\n  {chr(27)}[93m> Tlamatini :{chr(27)}[0m  http://{lan_ip}:{port}  (put this in Config > URLs)\n  {chr(27)}[93m> Health    :{chr(27)}[0m  http://{lan_ip}:{port}/health\n{chr(27)}[90m{"-"*58}{chr(27)}[0m\n{chr(10).join(rows)}\n{chr(27)}[90m{"-"*58}{chr(27)}[0m\n  {chr(27)}[92m OK  Server READY — waiting for connections{chr(27)}[0m\n{chr(27)}[90m{"-"*58}{chr(27)}[0m""")
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--port", type=int, default=API_PORT)
    parser.add_argument("--ip", type=str, default="0.0.0.0")
    return parser.parse_args()
if __name__ == "__main__":
    args = parse_args()
    if args.debug: DEBUG_MODE = True; os.environ["DEBUG_MODE"] = "1"; logger.setLevel(logging.DEBUG)
    if args.port != API_PORT: API_PORT = args.port
    print_server_banner(args.ip, API_PORT)
    logger.info(f"Starting Kali Linux Tools API Server on {args.ip}:{API_PORT}")
    app.run(host=args.ip, port=API_PORT, debug=DEBUG_MODE)
ENDOFFILE

grep -q '0.0.0.0' ~/Development/Mcp-Kali-Server/server.py && echo "==OK== server.py — 0.0.0.0 binding" || echo "==FAIL== server.py binding"

cd ~/Development/Mcp-Kali-Server && python3 -m venv .venv && echo "==OK== VENV" || echo "==FAIL== VENV"

.venv/bin/pip install --upgrade pip --quiet && .venv/bin/pip install flask --quiet && echo "==OK== FLASK INSTALLED" || echo "==FAIL== PIP"

sudo ufw --force enable && sudo ufw allow ssh && sudo ufw allow 5000/tcp && sudo ufw reload && echo "==OK== FIREWALL (ssh + 5000)" || echo "==FAIL== UFW"

(crontab -l 2>/dev/null | grep -v "Mcp-Kali-Server"; echo "@reboot sleep 10 && cd /home/${USER}/Development/Mcp-Kali-Server && nohup .venv/bin/python server.py > /tmp/server.log 2>&1 &") | crontab - && echo "==OK== CRONTAB AUTO-START" || echo "==FAIL== CRONTAB"

ps aux | grep "server.py" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null; sleep 1

cd ~/Development/Mcp-Kali-Server && nohup .venv/bin/python server.py > /tmp/server.log 2>&1 & disown

sleep 5 && ss -tlnp | grep 5000 && echo "==OK== PORT 5000 LISTENING" || echo "==FAIL== PORT NOT LISTENING"

curl -s http://127.0.0.1:5000/health | python3 -m json.tool && echo "==OK== HEALTH" || echo "==FAIL== HEALTH"

echo "" && echo "================ PUT THIS IN TLAMATINI ================" && echo "  Config > URLs > 'Kali server (Kalier)':" && echo "    http://$(ip -4 addr show eth0 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1):5000" && echo "  (If Kali is WSL2 on the same Windows box, leave the default" && echo "   http://127.0.0.1:5000 — it usually already works.)" && echo "======================================================="
```

---

## STEP 2 — Point Tlamatini at the Kali box (one-time)

The last line of the Linux block prints the URL to use.

1. In the Tlamatini chat page, open the navbar **Config ▸ URLs** dialog.
2. Set **Kali server (Kalier)** to `http://<KALI_IP>:5000` (from the block's output).
3. Save.

**Shortcut — WSL2 on the same Windows machine:** the default
`http://127.0.0.1:5000` usually already reaches a WSL2 server bound to
`0.0.0.0` (WSL2 localhost forwarding). Try a prompt first; only set the explicit
IP if Kalier reports it can't reach the server.

> Prefer the file? You can also edit `Tlamatini/agent/config.json` directly:
> `"kali_server_url": "http://172.17.48.44:5000"`. Same effect.

---

## STEP 3 — Use it (every session)

1. In the chat toolbar, tick **✅ Multi-Turn** and **✅ Exec Report**.
2. Ask in plain language. Tlamatini routes to the Kalier tool, targets your
   configured box automatically, runs the right Kali tool, and appends an
   **Exec Report** table (one row per command, with SUCCESS/FAILURE).

### Sample prompts

| You type | What Tlamatini does |
|---|---|
| *Tlamatini, scan the machine 10.0.0.5 and give me a report* | nmap `-sCV` against 10.0.0.5, then a written summary + Exec Report |
| *Is the Kali server up? Which tools are installed?* | `health` probe |
| *Recon 10.0.0.5: full port scan, then enumerate any web service you find* | nmap → (asks you to confirm scope) → gobuster/nikto on the open web port |
| *Brute-force SSH on 10.0.0.5 with user root and rockyou* | hydra (ssh, `-l root`, `-P rockyou.txt`) |
| *Crack the hashes in /root/hashes.txt* | john with rockyou |
| *Run `whatweb http://10.0.0.5` on Kali* | the `command` escape hatch (any tool not wrapped) |

> **Authorized targets only.** Kalier is a thin transport to offensive tooling.
> Only run it against machines you own or are explicitly authorized to test
> (engagement, lab, CTF). Tlamatini treats all tool output as untrusted data and
> will ask you to confirm scope before pivoting to a host that only appeared
> inside a result.

---

## Re-IP after a WSL2 reboot

WSL2 reassigns the Kali IP on reboot. If a prompt suddenly reports the server is
unreachable:

```bash
ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}'
```

Put the new IP into **Config ▸ URLs ▸ Kali server (Kalier)** and you're back.
(The `@reboot` crontab entry already restarts `server.py` for you.)

---

## Tear down the Kali side

Run on Kali to stop the server, close the port, drop the firewall rule, and remove
the auto-start:

```bash
ps aux | grep "server.py" | grep -v grep | awk '{print $2}' | xargs kill 2>/dev/null; sleep 1; ss -tlnp | grep 5000 && echo "XX PORT STILL OPEN" || echo "==OK== PORT CLOSED"; sudo ufw delete allow 5000/tcp && sudo ufw reload && echo "==OK== UFW RULE REMOVED" || echo "==OK== UFW RULE WAS ALREADY GONE"; crontab -l 2>/dev/null | grep -v "Mcp-Kali-Server" | crontab -; echo "==DONE== KALI TORN DOWN"
```

To stop Tlamatini using it, just blank the **Kali server (Kalier)** field (or
disable the **chat_agent_kalier** tool in the Tools dialog).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Kalier says it can't reach the server | Is `server.py` running on Kali? `ss -tlnp \| grep 5000`. Is the IP in Config ▸ URLs correct (`ip addr show eth0`)? Is UFW open (`sudo ufw status`)? |
| Tools show `false` in the health check | A package didn't install — re-run the package line in STEP 1. |
| Tlamatini doesn't seem to use Kali | Make sure **Multi-Turn** is ticked. Phrase the ask as an action ("scan…", "enumerate…", "crack…"). |
| Want a different box for one prompt | Just say so: *"…against the Kali at 10.0.0.9"* — the LLM passes `server_url` for that call only. |
| It still shows the old localhost | Save the Config ▸ URLs field again, or check `kali_server_url` in `config.json`. The chat path injects this on every run. |

---

## How the embedding works (for maintainers)

- **`agent/agents/kalier/kalier.py`** — the Kali client, ported inline (stdlib
  `urllib`, no `requests`/`mcp`). POSTs to the same `server.py` endpoints the old
  `client.py` used.
- **`config.json` → `kali_server_url`** — the single source of truth for the Kali
  box URL (the embedded equivalent of `client.py --server http://IP:5000`).
  Editable via **Config ▸ URLs** (`CONFIG_URL_KEYS` / `CONFIG_URL_URL_FIELDS` in
  `agent/views.py`).
- **`agent/tools.py` → `_seed_global_agent_defaults()`** — injects
  `kali_server_url` as the default `server_url` into the wrapped
  `chat_agent_kalier` runtime config *before* the LLM's per-call assignments, so a
  plain prompt targets the configured box and an explicit `server_url` still wins.
- **`chat_agent_kalier`** (registered in `agent/chat_agent_registry.py`) — the
  Multi-Turn tool the LLM calls. Captured in the Exec Report under
  `agent_key="kalier"`.
