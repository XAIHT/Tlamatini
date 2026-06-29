# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# MCP Doctor Agent - External MCP catalog diagnostics and setup guidance

import os
import sys

os.environ['FOR_DISABLE_CONSOLE_CTRL_HANDLER'] = '1'

import json
import logging
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

import yaml

try:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
except Exception as exc:
    sys.stderr.write(f"Critical Error: Failed to set working directory: {exc}\n")

CURRENT_DIR_NAME = os.path.basename(os.path.dirname(os.path.abspath(__file__)))
LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"

_IS_REANIMATED = os.environ.get('AGENT_REANIMATED') == '1'
if not _IS_REANIMATED:
    open(LOG_FILE_PATH, 'w').close()

logging.basicConfig(
    filename=LOG_FILE_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    encoding='utf-8',
)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(console_handler)

PID_FILE = "agent.pid"

# Transports Tlamatini's External MCP connector can actually reach (kept in sync
# with agent/external_mcp_manager.py::_SUPPORTED_TRANSPORTS). stdio launches a
# local child; the rest connect to an already-running server over a network
# carrier. tcp / named-pipe stay catalogued-only until an adapter exists.
_SUPPORTED_TRANSPORTS = {"stdio", "streamable-http", "sse", "websocket"}


def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        logging.error("Error: config.yaml not found.")
        return {}
    except Exception as exc:
        logging.error("Error parsing config.yaml: %s", exc)
        return {}


def write_pid_file() -> None:
    try:
        with open(PID_FILE, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    except Exception as exc:
        logging.error("Failed to write PID file: %s", exc)


def remove_pid_file() -> None:
    for _attempt in range(5):
        try:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            return
        except PermissionError:
            time.sleep(0.1)
        except Exception as exc:
            logging.error("Failed to remove PID file: %s", exc)
            return


def get_python_command() -> List[str]:
    if not getattr(sys, "frozen", False):
        return [sys.executable]
    if sys.platform.startswith("win"):
        carried = os.path.join(os.path.dirname(sys.executable), "python", "python.exe")
        if os.path.exists(carried):
            return [carried]
        bundled = os.path.join(os.path.dirname(sys.executable), "python.exe")
        if os.path.exists(bundled):
            return [bundled]
        return ["python"]
    return ["python3"]


def get_agent_env() -> Dict[str, str]:
    env = os.environ.copy()
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = getattr(sys, "_MEIPASS") or ""
        if meipass:
            parts = [p for p in env.get("PATH", "").split(os.pathsep) if os.path.normpath(p) != os.path.normpath(meipass)]
            env["PATH"] = os.pathsep.join(parts)
    return env


def get_pool_path() -> str:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent = os.path.dirname(current_dir)
    grandparent = os.path.dirname(parent)
    if os.path.basename(grandparent) == "pools":
        return parent
    if os.path.basename(parent) == "pools":
        return parent
    return os.path.join(os.path.dirname(current_dir), "pools")


def get_agent_directory(agent_name: str) -> str:
    return os.path.join(get_pool_path(), agent_name)


def get_agent_script_path(agent_name: str) -> str:
    agent_dir = get_agent_directory(agent_name)
    direct = os.path.join(agent_dir, f"{agent_name}.py")
    if os.path.exists(direct):
        return direct
    parts = agent_name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        base = parts[0]
        base_path = os.path.join(agent_dir, f"{base}.py")
        if os.path.exists(base_path):
            return base_path
    return direct


def is_agent_running(agent_name: str) -> bool:
    pid_path = os.path.join(get_agent_directory(agent_name), PID_FILE)
    if not os.path.exists(pid_path):
        return False
    try:
        with open(pid_path, "r", encoding="utf-8") as handle:
            pid = int(handle.read().strip())
    except Exception:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_agents_to_stop(agent_names: List[str]) -> None:
    if not agent_names:
        return
    waited = 0.0
    while True:
        running = [name for name in agent_names if is_agent_running(name)]
        if not running:
            return
        if waited >= 10.0:
            logging.error("WAITING FOR AGENTS TO STOP: %s still running", running)
            waited = 0.0
        time.sleep(0.5)
        waited += 0.5


def start_agent(agent_name: str) -> bool:
    agent_dir = get_agent_directory(agent_name)
    script_path = get_agent_script_path(agent_name)
    if not os.path.exists(script_path):
        logging.error("Agent script not found: %s", script_path)
        return False
    kwargs: Dict[str, Any] = {
        "cwd": agent_dir,
        "env": get_agent_env(),
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(get_python_command() + [script_path], **kwargs)
        logging.info("Started agent '%s' with PID: %s", agent_name, proc.pid)
        return True
    except Exception as exc:
        logging.error("Failed to start agent '%s': %s", agent_name, exc)
        return False


def _normalize_args(args: Any) -> List[str]:
    if args is None:
        return []
    if isinstance(args, str):
        stripped = args.strip()
        return [stripped] if stripped else []
    if isinstance(args, (list, tuple)):
        return [str(item) for item in args if item is not None]
    return [str(args)]


def _normalize_env(env: Any) -> Dict[str, str]:
    if not isinstance(env, dict):
        return {}
    return {str(key): str(value) for key, value in env.items() if value is not None}


def _server_transport(spec: Dict[str, Any]) -> str:
    transport = str(spec.get("transport") or spec.get("type") or "").strip().lower()
    aliases = {
        "http": "streamable-http",
        "streamable_http": "streamable-http",
        "ws": "websocket",
        "socket": "tcp",
        "raw": "tcp",
        "pipe": "named-pipe",
    }
    known = {"stdio", "streamable-http", "streamable_http", "http", "sse", "websocket", "ws", "tcp", "socket", "raw", "pipe", "named-pipe"}
    if transport in known:
        return aliases.get(transport, transport)
    if spec.get("command"):
        return "stdio"
    url = str(spec.get("url") or "").strip().lower()
    if url.startswith(("ws://", "wss://")):
        return "websocket"
    if url.startswith(("tcp://", "socket://", "raw://")):
        return "tcp"
    if url.startswith(("pipe://", "npipe://", "unix://")):
        return "named-pipe"
    if url.startswith(("http://", "https://")):
        return "sse" if (spec.get("sse") or "sse" in url) else "streamable-http"
    if spec.get("host") and spec.get("port"):
        return "tcp"
    if spec.get("socketPath") or spec.get("namedPipe") or spec.get("pipe"):
        return "named-pipe"
    return "stdio"


def _normalize_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(spec or {})
    if normalized.get("command") is not None:
        normalized["command"] = str(normalized.get("command") or "").strip()
    normalized["args"] = _normalize_args(normalized.get("args"))
    normalized["env"] = _normalize_env(normalized.get("env"))
    if normalized.get("cwd") is not None:
        normalized["cwd"] = str(normalized.get("cwd") or "").strip()
    url = (
        normalized.get("url")
        or normalized.get("endpoint")
        or normalized.get("sseUrl")
        or normalized.get("sse_url")
        or normalized.get("streamableHttpUrl")
        or normalized.get("streamable_http_url")
        or normalized.get("wsUrl")
        or normalized.get("ws_url")
        or normalized.get("websocketUrl")
        or normalized.get("webSocketUrl")
    )
    if url:
        normalized["url"] = str(url).strip()
    if not normalized.get("transport") and not normalized.get("type"):
        if normalized.get("sseUrl") or normalized.get("sse_url"):
            normalized["transport"] = "sse"
        elif normalized.get("streamableHttpUrl") or normalized.get("streamable_http_url"):
            normalized["transport"] = "streamable-http"
        elif normalized.get("wsUrl") or normalized.get("ws_url") or normalized.get("websocketUrl") or normalized.get("webSocketUrl"):
            normalized["transport"] = "websocket"
        elif normalized.get("host") and normalized.get("port"):
            normalized["transport"] = "tcp"
            normalized.setdefault("url", f"tcp://{normalized.get('host')}:{normalized.get('port')}")
        elif normalized.get("socketPath") or normalized.get("namedPipe") or normalized.get("pipe"):
            normalized["transport"] = "named-pipe"
            normalized.setdefault("url", str(normalized.get("socketPath") or normalized.get("namedPipe") or normalized.get("pipe") or ""))
        elif normalized.get("command"):
            normalized["transport"] = "stdio"
    return normalized


def _candidate_catalog_paths(config: Dict[str, Any]) -> List[str]:
    candidates: List[str] = []
    configured = str(config.get("catalog_path") or "").strip().strip('"').strip("'")
    if configured:
        candidates.append(configured)
    env_path = str(os.environ.get("TLAMATINI_EXTERNAL_MCPS_PATH") or "").strip()
    if env_path:
        candidates.append(env_path)
    config_path = str(os.environ.get("CONFIG_PATH") or "").strip()
    if config_path:
        candidates.append(os.path.join(os.path.dirname(config_path), "external_mcps.json"))
    probe = script_dir
    for _idx in range(14):
        candidates.append(os.path.join(probe, "external_mcps.json"))
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    if getattr(sys, "frozen", False):
        candidates.append(os.path.join(os.path.dirname(sys.executable), "external_mcps.json"))
    if sys.platform.startswith("win"):
        candidates.append(r"C:\Tlamatini\external_mcps.json")
    seen = set()
    unique = []
    for path in candidates:
        norm = os.path.normcase(os.path.abspath(os.path.expandvars(path)))
        if norm not in seen:
            seen.add(norm)
            unique.append(path)
    return unique


def _load_catalog(config: Dict[str, Any]) -> tuple[str, Dict[str, Any], Optional[str]]:
    searched = _candidate_catalog_paths(config)
    for path in searched:
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8-sig") as handle:
                data = json.load(handle) or {}
            if isinstance(data, dict) and "mcpServers" not in data and ("command" in data or "url" in data):
                name = str(config.get("server_key") or data.get("name") or os.path.splitext(os.path.basename(path))[0] or "Imported")
                data = {"mcpServers": {name: data}, "active": [name]}
            if not isinstance(data.get("mcpServers"), dict):
                data["mcpServers"] = {}
            if not isinstance(data.get("active"), list):
                data["active"] = []
            return path, data, None
        except Exception as exc:
            return path, {"mcpServers": {}, "active": []}, str(exc)
    return "", {"mcpServers": {}, "active": []}, "external_mcps.json not found; searched " + "; ".join(searched[:8])


def _which_executable(command: str) -> Dict[str, Any]:
    expanded = os.path.expandvars(str(command or "").strip())
    if not expanded:
        return {"command": "", "found": False, "resolved": ""}
    if os.path.isabs(expanded) or os.sep in expanded or (os.altsep and os.altsep in expanded):
        return {"command": expanded, "found": os.path.exists(expanded), "resolved": expanded if os.path.exists(expanded) else ""}
    resolved = shutil.which(expanded) or ""
    return {"command": expanded, "found": bool(resolved), "resolved": resolved}


def _infer_runtime(command: str, args: List[str]) -> str:
    exe = os.path.basename(str(command or "").lower())
    joined = " ".join(str(arg).lower() for arg in args or [])
    if exe in {"docker", "docker.exe"} or "docker" in joined:
        return "docker"
    if exe in {"npx", "npx.cmd", "npm", "npm.cmd", "node", "node.exe"}:
        return "node/npm"
    if exe in {"uvx", "uvx.exe", "uv", "uv.exe"}:
        return "uv/uvx"
    if exe in {"python", "python.exe", "python3", "py", "py.exe"}:
        return "python"
    if exe in {"bun", "bun.exe"}:
        return "bun"
    if exe in {"deno", "deno.exe"}:
        return "deno"
    if exe in {"cargo", "cargo.exe"}:
        return "rust/cargo"
    if exe in {"dotnet", "dotnet.exe"}:
        return ".NET"
    if exe in {"java", "java.exe"}:
        return "java"
    if exe in {"cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}:
        return "shell wrapper"
    return exe or "unknown"


def _looks_like_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    return any(marker in lowered for marker in (
        "your_", "changeme", "change_me", "replace_me", "placeholder",
        "example_token", "api_key_here", "token_here", "<", ">", "${", "%", "xxx", "todo",
    ))


def _missing_secret_hints(spec: Dict[str, Any]) -> List[str]:
    hints: List[str] = []
    env = spec.get("env") if isinstance(spec.get("env"), dict) else {}
    for key, value in env.items():
        key_text = str(key)
        key_lower = key_text.lower()
        if any(part in key_lower for part in ("key", "token", "secret", "password", "auth", "bearer")) and _looks_like_placeholder(value):
            hints.append(key_text)
    for idx, arg in enumerate(spec.get("args") or []):
        text = str(arg)
        lower = text.lower()
        if any(part in lower for part in ("api_key", "apikey", "token", "secret", "password")) and _looks_like_placeholder(text):
            hints.append(f"args[{idx}]")
    return hints


def _source_urls(spec: Dict[str, Any], source_url: str) -> List[str]:
    urls: List[str] = []
    if source_url.strip().startswith(("http://", "https://")):
        urls.append(source_url.strip())
    for key in ("source", "homepage", "homePage", "repository", "repo", "docs", "documentation", "readme", "url"):
        value = spec.get(key)
        if isinstance(value, str) and value.strip().startswith(("http://", "https://")):
            urls.append(value.strip())
    return list(dict.fromkeys(urls))


def _diagnose_one(key: str, spec: Dict[str, Any], active: List[str], source_url: str) -> Dict[str, Any]:
    spec = _normalize_spec(spec)
    transport = _server_transport(spec)
    command = str(spec.get("command") or "").strip()
    args = _normalize_args(spec.get("args"))
    probe = _which_executable(command) if command else {"command": "", "found": False, "resolved": ""}
    runtime = _infer_runtime(command, args)
    missing = _missing_secret_hints(spec)
    url = str(spec.get("url") or "").strip()
    if transport == "stdio":
        supported = bool(command)
    elif transport in _SUPPORTED_TRANSPORTS:
        supported = bool(url)
    else:
        supported = False
    blockers: List[str] = []
    if transport not in _SUPPORTED_TRANSPORTS:
        blockers.append(f"transport not connectable here: {transport} (needs a stdio bridge)")
    elif transport == "stdio":
        if not command:
            blockers.append("stdio server has no command")
        elif not probe["found"]:
            blockers.append(f"command not found on PATH: {command}")
    elif not url:
        blockers.append(f"{transport} server has no url")
    if missing:
        blockers.append("missing or placeholder secret fields: " + ", ".join(missing))
    if transport not in _SUPPORTED_TRANSPORTS:
        next_step = f"Wrap the {transport} server behind a stdio MCP bridge, or expose it over streamable-http/sse/websocket."
    elif transport == "stdio" and not command:
        next_step = "Find the server command from the MCP documentation, add it to the JSON, and import again."
    elif transport == "stdio" and not probe["found"]:
        next_step = f"Install or expose `{command}` on PATH, then reconnect this MCP."
    elif transport != "stdio" and not url:
        next_step = f"Add the {transport} server url to the JSON, then import it again."
    elif missing:
        next_step = "Fill required secret/environment fields, then reconnect this MCP."
    elif key not in active:
        next_step = "Activate this MCP in External > MCPs so Tlamatini can warm-connect it."
    else:
        next_step = "Run status, list tools, then perform one small safe smoke-test tool call."
    return {
        "server_key": key,
        "transport": transport,
        "url": url,
        "runtime": runtime,
        "supported_by_current_connector": supported,
        "active": key in active,
        "command_probe": probe,
        "args": args,
        "missing_secret_fields": missing,
        "source_urls": _source_urls(spec, source_url),
        "blockers": blockers,
        "next_step": next_step,
    }


def _render_report(catalog_path: str, diagnostics: List[Dict[str, Any]], load_error: Optional[str]) -> str:
    lines: List[str] = []
    if load_error:
        lines.append(f"Catalog problem: {load_error}")
    lines.append(f"Catalog path: {catalog_path or '(not found)'}")
    lines.append(f"Servers diagnosed: {len(diagnostics)}")
    active_named = [d["server_key"] for d in diagnostics if d.get("active")]
    lines.append("Active servers: " + (", ".join(active_named) if active_named else "(none)"))
    for diag in diagnostics:
        lines.append("")
        lines.append(f"## {diag['server_key']}")
        lines.append(f"- transport: {diag['transport']}")
        if diag.get("url"):
            lines.append(f"- url: {diag['url']}")
        lines.append(f"- supported: {diag['supported_by_current_connector']}")
        lines.append(f"- runtime: {diag['runtime']}")
        lines.append(f"- active: {diag['active']}")
        lines.append(f"- command found: {diag['command_probe'].get('found')}")
        resolved = diag["command_probe"].get("resolved")
        if resolved:
            lines.append(f"- command path: {resolved}")
        if diag["source_urls"]:
            lines.append("- source/docs: " + ", ".join(diag["source_urls"]))
        if diag["missing_secret_fields"]:
            lines.append("- missing secrets: " + ", ".join(diag["missing_secret_fields"]))
        if diag["blockers"]:
            lines.append("- blockers: " + " | ".join(diag["blockers"]))
        else:
            lines.append("- blockers: none detected")
        lines.append(f"- next step: {diag['next_step']}")
    if not diagnostics:
        lines.append("No MCP servers are in the catalog yet. Drag a valid MCP JSON onto External > MCPs.")
    return "\n".join(lines)


def diagnose(config: Dict[str, Any]) -> Dict[str, Any]:
    catalog_path, catalog, load_error = _load_catalog(config)
    servers = catalog.get("mcpServers", {})
    active = [str(key) for key in catalog.get("active", []) if key in servers]
    wanted = str(config.get("server_key") or "").strip()
    source_url = str(config.get("source_url") or "").strip()
    if wanted and wanted not in servers:
        diagnostics: List[Dict[str, Any]] = []
        load_error = f"unknown MCP server: {wanted}"
    elif wanted:
        diagnostics = [_diagnose_one(wanted, servers.get(wanted, {}) or {}, active, source_url)]
    else:
        # Triage EVERY catalogued server. ACTIVE servers first (alphabetical
        # within each group) so the report always leads with the MCPs that are
        # actually wired up. The user must see ALL of them, never just the first.
        active_keys = sorted(k for k in servers if k in active)
        inactive_keys = sorted(k for k in servers if k not in active)
        keys = [str(k) for k in active_keys + inactive_keys]
        diagnostics = [_diagnose_one(key, servers.get(key, {}) or {}, active, source_url) for key in keys]
    body = _render_report(catalog_path, diagnostics, load_error)
    primary = diagnostics[0] if diagnostics else {}
    status = "error" if load_error or any(diag.get("blockers") for diag in diagnostics) else "ready"
    active_named = [d["server_key"] for d in diagnostics if d.get("active")]
    summary = "; ".join(
        f"{d['server_key']} [{'active' if d.get('active') else 'inactive'}, "
        f"{d.get('transport', '?')}, {'OK' if not d.get('blockers') else 'BLOCKED'}]"
        for d in diagnostics
    )
    result = {
        "server_key": wanted or ", ".join(d["server_key"] for d in diagnostics),
        "servers_diagnosed": len(diagnostics),
        "active_servers": ", ".join(active_named),
        "summary": summary,
        "catalog_path": catalog_path,
        "status": status,
        "body": body,
        "diagnostics": diagnostics,
        "load_error": load_error or "",
    }
    # A single-server run keeps the per-server scalars for backward
    # compatibility; a multi-server triage omits them because no single
    # transport/runtime/supported describes the whole set (each server is in
    # the body + the one-line summary above instead).
    if len(diagnostics) == 1:
        result["transport"] = primary.get("transport", "")
        result["runtime"] = primary.get("runtime", "")
        result["supported"] = str(bool(primary.get("supported_by_current_connector", False))).lower()
    return result


def _emit_section(result: Dict[str, Any]) -> None:
    header = [
        f"servers_diagnosed: {result.get('servers_diagnosed', 0)}",
        f"active_servers: {result.get('active_servers', '')}",
        f"server_key: {result.get('server_key', '')}",
        f"status: {result.get('status', '')}",
        f"catalog_path: {result.get('catalog_path', '')}",
        f"summary: {result.get('summary', '')}",
    ]
    # Per-server scalars only when exactly ONE server was diagnosed (a targeted
    # run). A multi-server triage describes each server in the body + the
    # single-line summary above, so it omits the misleading primary-only ones.
    if "transport" in result:
        header.append(f"transport: {result.get('transport', '')}")
        header.append(f"runtime: {result.get('runtime', '')}")
        header.append(f"supported: {result.get('supported', '')}")
    logging.info(
        "INI_SECTION_MCP_DOCTOR<<<\n"
        + "\n".join(header)
        + "\n\n"
        + str(result.get("body") or "")
        + "\n>>>END_SECTION_MCP_DOCTOR"
    )


def main() -> None:
    config = load_config()
    write_pid_file()
    try:
        if _IS_REANIMATED:
            logging.info("%s REANIMATED (resuming from pause)", CURRENT_DIR_NAME)
            logging.info("=" * 60)
        target_agents = config.get("target_agents", [])
        if not isinstance(target_agents, list):
            target_agents = []
        logging.info("MCP DOCTOR AGENT STARTED")
        logging.info("Target server_key: %s", config.get("server_key") or "(all)")

        result = diagnose(config)
        logging.info(result["body"])
        _emit_section(result)
        logging.info("MCP Doctor JSON summary: %s", json.dumps({
            "status": result.get("status"),
            "server_key": result.get("server_key"),
            "diagnostics": result.get("diagnostics", []),
        }, ensure_ascii=False))

        if target_agents:
            wait_for_agents_to_stop(target_agents)
            for target in target_agents:
                start_agent(target)
        logging.info("MCP Doctor agent finished.")
    finally:
        time.sleep(0.4)
        remove_pid_file()


if __name__ == "__main__":
    main()
