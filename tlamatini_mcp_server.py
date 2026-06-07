#!/usr/bin/env python3
"""Tlamatini Agents — MCP server.

Exposes EVERY Tlamatini pool agent (Executer, Pythonxer, Croner, ACPXer,
STM32er, ESP32er, Arduiner, Shoter, Playwrighter, Kalier, … all 74) as an
MCP tool so an MCP client (Claude Code, etc.) can drive them directly.

It does NOT import the Django app. For each call it performs the exact
"launcher dance" Tlamatini's pool uses:

    1. copy  agent/agents/<name>/      ->  Temp/mcp_agent_runs/<name>__<runid>/
    2. write the tool args into that copy's config.yaml (deep-merged onto the
       template defaults; empty values are dropped so template defaults survive)
    3. run   python <name>.py          (in the copied dir)
    4. read  <name>__<runid>.log       (the agent writes its result there)

Short agents are awaited (default) and their full log is returned. Known
long-running agents (Croner, FlowHypervisor, TeleTlamatini, monitors, …) and
any call with wait=false return a run_id you poll with tlamatini_run_log /
tlamatini_run_status / tlamatini_run_stop.

Self-contained: only needs `mcp` + `pyyaml` (psutil used for tree-kill if
present). Resolves the agents directory relative to THIS file, so the working
directory of the launching client is irrelevant.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional

import yaml

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

# --------------------------------------------------------------------------- #
# Paths (resolved relative to this file — client cwd does not matter)
# --------------------------------------------------------------------------- #
HERE = os.path.dirname(os.path.abspath(__file__))
AGENTS_ROOT = os.path.join(HERE, "Tlamatini", "agent", "agents")
# Source-mode app-Temp is the repo-root /Temp (gitignored); see the 2026-06-02
# Temp policy in CLAUDE.md. Runtime agent copies live under it so they never
# pollute the working tree.
TEMP_ROOT = os.path.join(HERE, "Temp")
RUNS_ROOT = os.path.join(TEMP_ROOT, "mcp_agent_runs")
PYTHON_EXE = sys.executable

# Connection-wiring fields: never surfaced as tool params (single-agent runs
# don't wire flows). Left at their template defaults unless explicitly overridden.
CONNECTION_FIELDS = {
    "source_agents", "target_agents", "output_agents",
    "source_agent_1", "source_agent_2",
    "target_agents_a", "target_agents_b", "target_agents_l", "target_agents_g",
}

# Agents that never finish on their own → default to background (wait=false).
LONG_RUNNING = {
    "croner", "flowhypervisor", "teletlamatini", "whatstlamatini",
    "gatewayer", "gateway_relayer", "telegramrx", "recmailer",
    "monitor_log", "monitor_netstat", "node_manager",
}

DEFAULT_TIMEOUT = 180  # seconds to await a short agent before backgrounding it

# In-memory registry of launched runs (the stdio server is one long-lived process)
_RUNS: Dict[str, Dict[str, Any]] = {}
_RUN_COUNTER = 0


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
def discover_agents() -> Dict[str, Dict[str, Any]]:
    """Return {agent_name: {dir, config(dict), params(list)}} for every runnable
    agent (a directory holding both <name>.py and config.yaml)."""
    agents: Dict[str, Dict[str, Any]] = {}
    if not os.path.isdir(AGENTS_ROOT):
        return agents
    for name in sorted(os.listdir(AGENTS_ROOT)):
        d = os.path.join(AGENTS_ROOT, name)
        script = os.path.join(d, f"{name}.py")
        cfg = os.path.join(d, "config.yaml")
        if not (os.path.isfile(script) and os.path.isfile(cfg)):
            continue
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            config = {}
        if not isinstance(config, dict):
            config = {}
        params = [k for k in config.keys() if k not in CONNECTION_FIELDS]
        agents[name] = {"dir": d, "config": config, "params": params}
    return agents


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def build_tool(name: str, info: Dict[str, Any]) -> types.Tool:
    config = info["config"]
    props: Dict[str, Any] = {}
    for key in info["params"]:
        default = config.get(key)
        t = _json_type(default)
        schema: Dict[str, Any] = {"type": t}
        if t in ("array", "object"):
            # keep loose so the client can pass arbitrary structure
            schema = {"type": t}
        schema["description"] = f"{key} (template default: {json.dumps(default, default=str)})"
        props[key] = schema
    props["config"] = {
        "type": "object",
        "description": "Free-form overrides deep-merged onto config.yaml "
                       "(use for nested/uncommon keys, or to set source_agents/"
                       "target_agents wiring).",
    }
    props["wait"] = {
        "type": "boolean",
        "description": f"Wait for the agent to finish and return its full log. "
                       f"Default {name not in LONG_RUNNING} for this agent.",
    }
    props["timeout_seconds"] = {
        "type": "integer",
        "description": f"Max seconds to wait before backgrounding (default {DEFAULT_TIMEOUT}).",
    }
    param_list = ", ".join(info["params"]) or "(no configurable parameters)"
    lr = " [LONG-RUNNING: defaults to background — poll with tlamatini_run_log]" if name in LONG_RUNNING else ""
    desc = (f"Run the Tlamatini **{name}** pool agent.{lr}\n"
            f"Configurable parameters: {param_list}.\n"
            f"Returns the agent's execution log. Backgrounds (returns a run_id) "
            f"on timeout or wait=false.")
    return types.Tool(
        name=name,
        description=desc,
        inputSchema={"type": "object", "properties": props, "additionalProperties": True},
    )


# --------------------------------------------------------------------------- #
# Launcher
# --------------------------------------------------------------------------- #
def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in overrides.items():
        if v is None:
            continue  # never let an empty value clobber a template default
        if isinstance(v, str) and v == "":
            continue
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v
    return base


def _ignore(_dir: str, names: List[str]) -> List[str]:
    drop = []
    for n in names:
        if n == "__pycache__" or n.endswith(".log") or n.endswith(".pid"):
            drop.append(n)
        elif n.startswith("reanim") or n == "agent.pid":
            drop.append(n)
    return drop


def _log_path(run_dir: str) -> str:
    return os.path.join(run_dir, os.path.basename(run_dir) + ".log")


def _read_log(run_dir: str, max_chars: int = 12000) -> str:
    p = _log_path(run_dir)
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            data = f.read()
    except FileNotFoundError:
        return "(no log produced yet)"
    except Exception as e:
        return f"(could not read log: {e})"
    if len(data) > max_chars:
        return "…(truncated)…\n" + data[-max_chars:]
    return data


def run_agent_blocking(agent: str, info: Dict[str, Any], overrides: Dict[str, Any],
                       wait: bool, timeout: int) -> Dict[str, Any]:
    global _RUN_COUNTER
    os.makedirs(RUNS_ROOT, exist_ok=True)
    _RUN_COUNTER += 1
    run_id = f"{agent}__{int(time.time())}_{_RUN_COUNTER}"
    run_dir = os.path.join(RUNS_ROOT, run_id)

    shutil.copytree(info["dir"], run_dir, ignore=_ignore)

    # merge overrides onto the template config.yaml
    cfg_path = os.path.join(run_dir, "config.yaml")
    try:
        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = dict(info["config"])
    _deep_merge(cfg, overrides or {})
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    env = os.environ.copy()
    env["TLAMATINI_TEMP"] = TEMP_ROOT
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.pop("AGENT_REANIMATED", None)

    proc = subprocess.Popen(
        [PYTHON_EXE, f"{agent}.py"],
        cwd=run_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    _RUNS[run_id] = {"proc": proc, "dir": run_dir, "agent": agent, "started": time.time()}

    if not wait:
        return {"status": "launched", "run_id": run_id, "agent": agent,
                "note": "Running in background. Use tlamatini_run_log / "
                        "tlamatini_run_status / tlamatini_run_stop.",
                "config_used": cfg, "run_dir": run_dir}
    try:
        rc = proc.wait(timeout=timeout)
        return {"status": "finished", "run_id": run_id, "agent": agent,
                "return_code": rc, "config_used": cfg, "log": _read_log(run_dir)}
    except subprocess.TimeoutExpired:
        return {"status": "running", "run_id": run_id, "agent": agent,
                "note": f"Still running after {timeout}s — left in background. "
                        f"Poll with tlamatini_run_log('{run_id}').",
                "config_used": cfg, "log_excerpt": _read_log(run_dir, 4000)}


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        import psutil
        try:
            parent = psutil.Process(proc.pid)
        except psutil.NoSuchProcess:
            return
        for child in parent.children(recursive=True):
            try:
                child.terminate()
            except Exception:
                pass
        parent.terminate()
        gone, alive = psutil.wait_procs([parent], timeout=3)
        for p in alive:
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        try:
            proc.terminate()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# MCP server
# --------------------------------------------------------------------------- #
server = Server("tlamatini")
_AGENTS = discover_agents()

MANAGEMENT_TOOLS = {
    "tlamatini_list_agents", "tlamatini_run_status",
    "tlamatini_run_log", "tlamatini_run_stop", "tlamatini_list_runs",
}


@server.list_tools()
async def list_tools() -> List[types.Tool]:
    tools = [build_tool(name, info) for name, info in _AGENTS.items()]
    tools += [
        types.Tool(
            name="tlamatini_list_agents",
            description="List every available Tlamatini agent tool and its configurable parameters.",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="tlamatini_run_status",
            description="Status (alive / finished + return code) of a background agent run.",
            inputSchema={"type": "object",
                         "properties": {"run_id": {"type": "string"}},
                         "required": ["run_id"]},
        ),
        types.Tool(
            name="tlamatini_run_log",
            description="Read the log of a (running or finished) agent run.",
            inputSchema={"type": "object",
                         "properties": {"run_id": {"type": "string"},
                                        "max_chars": {"type": "integer"}},
                         "required": ["run_id"]},
        ),
        types.Tool(
            name="tlamatini_run_stop",
            description="Terminate a background agent run (kills the process tree).",
            inputSchema={"type": "object",
                         "properties": {"run_id": {"type": "string"}},
                         "required": ["run_id"]},
        ),
        types.Tool(
            name="tlamatini_list_runs",
            description="List all agent runs launched in this session and whether they are alive.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]
    return tools


def _result(obj: Any) -> List[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps(obj, indent=2, default=str))]


@server.call_tool()
async def call_tool(name: str, arguments: Optional[Dict[str, Any]]) -> List[types.TextContent]:
    arguments = arguments or {}

    if name == "tlamatini_list_agents":
        return _result({"agents": [
            {"name": n, "parameters": info["params"],
             "long_running": n in LONG_RUNNING}
            for n, info in _AGENTS.items()
        ]})

    if name == "tlamatini_list_runs":
        out = []
        for rid, r in _RUNS.items():
            rc = r["proc"].poll()
            out.append({"run_id": rid, "agent": r["agent"],
                        "alive": rc is None, "return_code": rc})
        return _result({"runs": out})

    if name == "tlamatini_run_status":
        rid = arguments.get("run_id", "")
        r = _RUNS.get(rid)
        if not r:
            return _result({"error": f"unknown run_id {rid!r}"})
        rc = r["proc"].poll()
        return _result({"run_id": rid, "agent": r["agent"],
                        "alive": rc is None, "return_code": rc})

    if name == "tlamatini_run_log":
        rid = arguments.get("run_id", "")
        r = _RUNS.get(rid)
        if not r:
            return _result({"error": f"unknown run_id {rid!r}"})
        return _result({"run_id": rid, "agent": r["agent"],
                        "alive": r["proc"].poll() is None,
                        "log": _read_log(r["dir"], int(arguments.get("max_chars", 12000)))})

    if name == "tlamatini_run_stop":
        rid = arguments.get("run_id", "")
        r = _RUNS.get(rid)
        if not r:
            return _result({"error": f"unknown run_id {rid!r}"})
        _kill_tree(r["proc"])
        return _result({"run_id": rid, "agent": r["agent"], "stopped": True})

    # ---- an agent tool ----
    info = _AGENTS.get(name)
    if not info:
        return _result({"error": f"unknown tool {name!r}"})

    reserved = {"config", "wait", "timeout_seconds"}
    overrides: Dict[str, Any] = {k: v for k, v in arguments.items() if k not in reserved}
    extra = arguments.get("config") or {}
    if isinstance(extra, dict):
        _deep_merge(overrides, extra)
    wait = bool(arguments.get("wait", name not in LONG_RUNNING))
    timeout = int(arguments.get("timeout_seconds", DEFAULT_TIMEOUT))

    try:
        res = await asyncio.to_thread(run_agent_blocking, name, info, overrides, wait, timeout)
    except Exception as e:
        return _result({"status": "error", "agent": name, "error": repr(e)})
    return _result(res)


async def _amain() -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    if "--list" in sys.argv:  # quick offline self-check
        for n, info in _AGENTS.items():
            print(f"{n:22s} params: {', '.join(info['params']) or '-'}")
        print(f"\n{len(_AGENTS)} agent tools + {len(MANAGEMENT_TOOLS)} management tools")
        return
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
