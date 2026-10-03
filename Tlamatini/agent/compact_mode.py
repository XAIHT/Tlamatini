"""
compact_mode.py - the COMPACT MODE switch (Angela, 2026-10-02).

Angela's design, in her words: in STRICT compact mode (a small model is really
active) the user must NOT be able to untick "Compact mode"; only a model that
can fit **everything activated** lets the box be ticked and unticked freely.
Compact mode starts with System-Metrics, Files-Search and Current-Time enabled,
"BUT THE USER MUST BE ABLE TO FOR EXAMPLE DEACTIVATE System Metrics, DEACTIVATE
Files Search, BUT ACTIVATE FOR EXAMPLE ESPHomer" - and the CONTEXT-WINDOW gauge
must tell the truth about what that costs.

So entering Compact mode REALLY unticks the real selections - the rows behind
Config > Configure MCPs, Configure Agents and ACPX-Skills - and unticking it
(a big model only) re-enables ALL of them.  This module is the ONE place that
rewrites those rows for the switch:

* ``state()`` / ``is_active()`` / ``is_strict()`` - the switch, cached in
  memory and persisted in the singleton ``CompactState`` row;
* ``enter_compact()`` / ``leave_compact()`` / ``set_active()`` - the atomic row
  rewrite, plus the External-MCP active list (saved, then restored);
* ``note_capacity()`` - the fitter's verdict for the current model; a STRICT
  model with Compact mode off switches it ON automatically;
* ``after_toggles_saved()`` - a Configure dialog was saved: chain each agent
  to its tool row, apply every row to ``global_state`` at once (no restart),
  and tell every open tab;
* ``apply_rows_to_global_state()`` + ``toggles_version()`` - the unified
  executor re-reads its tool surface whenever the version moves;
* ``cut_warning_html()`` - the line a CUT answer carries in the chat;
* ``costs()`` - what each row costs, for the Configure dialogs;
* ``set_self_modify()`` / ``note_self_modify()`` / ``self_modify_active()`` -
  the SELF-MODIFY switch (Angela, 2026-10-03): Tlamatini's self-knowledge
  rides along only in a build that can self-modify (always from source), when
  the user wants it, and when the model can hold it - locked OFF otherwise.

Every function is FAIL-OPEN: a broken switch must never cost the chat.  With no
database (a SimpleTestCase, a broken install) Compact mode simply reads OFF.
"""
from __future__ import annotations

import asyncio
import html
import json
import re
import threading
import time
from typing import Any, Dict, Iterable, List

from .global_state import global_state

#: Channels group every chat connection joins: a switch reaches every open tab.
GROUP = "tlamatini_compact_mode"
#: global_state key read by ``tools.get_mcp_tools`` on every call.
GLOBAL_ACTIVE_KEY = "compact_mode_active"

#: Kept ON when Compact mode starts.  The user may switch them off.
KEEP_MCPS = ("System-Metrics", "Files-Search")
KEEP_TOOLS = ("current-time",)

#: A wrapped agent answers with a run id; these let the model wait for it and
#: read its status.  Ticked with the first agent ticked in Compact mode.
COMPANION_TOOLS = ("chat-agent-run-wait", "chat-agent-run-status")

#: Direct tools that ALSO need a canvas agent's row (tools.get_mcp_tools).
AGENT_DIRECT_TOOLS = {
    "pythonxer": ("execute-file",),
    "executer": ("execute-command",),
    "googler": ("googler",),
}

#: "tool-12" - a row named only by its number (its description is the key).
_NUMBERED_ROW = re.compile(r"^tool-\d+$")

_LOCK = threading.RLock()
_STATE: Dict[str, Any] = {
    "loaded": False,
    "active": False,
    "strict": False,
    "model": "",
    "window_tokens": 0,
    "usable_tokens": 0,
    "everything_tokens": 0,
    "base_tokens": 0,
    "chars_per_token": 0.0,
    "setting": "auto",
    "reason": "",
    "since": 0.0,
    # The Self-modify switch (2026-10-03).  ``self_modify`` is the user's
    # choice (persisted, ON by default); ``self_modify_fits`` the fitter's last
    # verdict (None = not measured yet, False = locked OFF for this model).
    "self_modify": True,
    "self_modify_fits": None,
    "self_modify_tokens": 0,
    "self_modify_need_tokens": 0,
}
_VERSION = [1]
_NOTIFY: Dict[str, Any] = {"loop": None, "layer": None}
_COSTS: Dict[str, Any] = {}


# ── The switch ──────────────────────────────────────────────────────────────
def _row():
    from .models import CompactState
    row, _created = CompactState.objects.get_or_create(pk=1)
    return row


def _load(force: bool = False) -> None:
    with _LOCK:
        if _STATE["loaded"] and not force:
            return
    try:
        row = _row()
        with _LOCK:
            _STATE.update(
                loaded=True,
                active=bool(row.active),
                strict=bool(row.strict),
                model=str(row.model or ""),
                window_tokens=int(row.window_tokens or 0),
                reason=str(row.reason or ""),
                self_modify=bool(getattr(row, "self_modify", True)),
            )
        global_state.set_state(GLOBAL_ACTIVE_KEY, bool(row.active))
    except Exception:  # noqa: BLE001 - no database: Compact mode reads OFF
        pass


def reset_cache() -> None:
    """Forget the cached switch (tests, and after a database is swapped)."""
    with _LOCK:
        _STATE.update(loaded=False, active=False, strict=False, model="", window_tokens=0,
                      usable_tokens=0, everything_tokens=0, base_tokens=0,
                      chars_per_token=0.0, setting="auto", reason="", since=0.0,
                      self_modify=True, self_modify_fits=None, self_modify_tokens=0,
                      self_modify_need_tokens=0)
        _COSTS.clear()
    global_state.set_state(GLOBAL_ACTIVE_KEY, None)


def state() -> Dict[str, Any]:
    """A copy of the switch, safe to send to the page."""
    _load()
    with _LOCK:
        snap = {k: v for k, v in _STATE.items() if k != "loaded"}
    snap["version"] = _VERSION[0]
    snap["locked"] = bool(snap["strict"])
    available = self_modify_available()
    snap["self_modify_available"] = available
    snap["self_modify_locked"] = bool(available and snap["self_modify_fits"] is False)
    snap["self_modify_active"] = bool(available and snap["self_modify"]
                                      and snap["self_modify_fits"] is not False)
    return snap


def is_active() -> bool:
    _load()
    with _LOCK:
        return bool(_STATE["active"])


def is_strict() -> bool:
    _load()
    with _LOCK:
        return bool(_STATE["strict"])


def toggles_version() -> int:
    """Moves every time the Configure rows are applied; the executor watches it."""
    return int(_VERSION[0])


def _bump() -> int:
    with _LOCK:
        _VERSION[0] += 1
        return _VERSION[0]


# ── Applying the rows at once ───────────────────────────────────────────────
def apply_rows_to_global_state(reason: str = "") -> bool:
    """Copy every Mcp / Tool / Agent row into the gates ``get_mcp_tools`` reads.

    Exactly the keys ``rag.factory.setup_llm`` sets when a chain is built, so a
    saved dialog takes effect on the NEXT request - no reconnect, no rebuild.
    """
    try:
        from .models import Agent, Mcp, Tool
        for agent in Agent.objects.all().values("agentDescription", "agentContent"):
            descr = str(agent["agentDescription"] or "")
            if descr:
                global_state.set_state(
                    "agent_" + descr.lower() + "_status",
                    "enabled" if agent["agentContent"] == "true" else "disabled")
        mcps = list(Mcp.objects.all().values("mcpDescription", "mcpContent"))
        system_on = any(m["mcpDescription"] == "System-Metrics" and m["mcpContent"] == "true" for m in mcps)
        files_on = any(m["mcpDescription"] == "Files-Search" and m["mcpContent"] == "true" for m in mcps)
        global_state.set_state("mcp_system_status", "enabled" if system_on else "disabled")
        global_state.set_state("mcp_files_search_status", "enabled" if files_on else "disabled")
        for tool in Tool.objects.all().values("toolName", "toolDescription", "toolContent"):
            descr = str(tool["toolDescription"] or "")
            flag = "enabled" if tool["toolContent"] == "true" else "disabled"
            if descr:
                global_state.set_state("tool_" + descr.lower() + "_status", flag)
            name = str(tool["toolName"] or "")
            if name and not _NUMBERED_ROW.match(name):
                # The ACPX rows are gated by their NAME ("acpx-spawn").
                global_state.set_state("tool_" + name.lower() + "_status", flag)
        _load(force=True)
        version = _bump()
        print(f"--- [TOGGLES] Configure rows applied at once ({reason or 'saved'}) - version "
              f"{version}; the next request uses them, no restart needed")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"--- [TOGGLES] rows not applied ({exc}) - they apply on the next reconnect")
        return False


# ── External MCPs: paused, then restored ────────────────────────────────────
def _external_active() -> List[str]:
    try:
        from .external_mcp_manager import load_catalog
        data = load_catalog() or {}
        return [str(k) for k in (data.get("active") or [])]
    except Exception:  # noqa: BLE001
        return []


def _set_external_active(keys: Iterable[str]) -> None:
    try:
        from .external_mcp_manager import set_active as _ext_set_active
        _ext_set_active(list(keys))
    except Exception as exc:  # noqa: BLE001
        print(f"--- [COMPACT] External MCP selection not changed ({exc})")


# ── Entering and leaving ────────────────────────────────────────────────────
def enter_compact(reason: str = "", *, auto: bool = False) -> Dict[str, Any]:
    """Untick every MCP / tool / agent / skill row except System-Metrics,
    Files-Search and Current-Time, and pause the External MCPs.  Atomic."""
    try:
        from django.db import transaction

        from .models import Agent, Mcp, Skill, Tool
        saved_external = _external_active()
        with transaction.atomic():
            row = _row()
            if row.active:
                return {"ok": True, "changed": False, "state": state()}
            for mcp in Mcp.objects.all():
                want = "true" if mcp.mcpDescription in KEEP_MCPS else "false"
                if mcp.mcpContent != want:
                    mcp.mcpContent = want
                    mcp.save(update_fields=["mcpContent"])
            for tool in Tool.objects.all():
                want = "true" if str(tool.toolDescription or "").lower() in KEEP_TOOLS else "false"
                if tool.toolContent != want:
                    tool.toolContent = want
                    tool.save(update_fields=["toolContent"])
            Agent.objects.exclude(agentContent="false").update(agentContent="false")
            Skill.objects.filter(enabled=True).update(enabled=False)
            row.active = True
            row.saved_external_active = json.dumps(saved_external)
            row.reason = str(reason or "")[:300]
            row.save()
        if saved_external:
            _set_external_active([])
        with _LOCK:
            _STATE.update(loaded=True, active=True, reason=str(reason or ""), since=time.time())
        global_state.set_state(GLOBAL_ACTIVE_KEY, True)
        apply_rows_to_global_state("Compact mode ON")
        print(f"--- [COMPACT] Compact mode ON ({'automatic' if auto else 'by the user'}: "
              f"{reason or 'no reason given'}) - every MCP, tool, agent and skill row is unticked "
              f"except System-Metrics, Files-Search and Current-Time; External MCPs paused "
              f"({len(saved_external)} saved: {saved_external})")
        notify("on")
        return {"ok": True, "changed": True, "state": state()}
    except Exception as exc:  # noqa: BLE001
        print(f"--- [COMPACT] could not switch Compact mode ON ({exc})")
        return {"ok": False, "changed": False, "error": str(exc), "state": state()}


def leave_compact(reason: str = "", *, force: bool = False) -> Dict[str, Any]:
    """Re-enable EVERY row and restore the External MCPs - refused while the
    model cannot hold everything (strict), unless ``force``."""
    if is_strict() and not force:
        snap = state()
        return {
            "ok": False, "changed": False, "refused": "strict", "state": snap,
            "message": (f"Compact mode stays ON: {snap.get('model') or 'this model'} reads only "
                        f"{int(snap.get('window_tokens') or 0):,} tokens, and everything activated "
                        f"needs ~{int(snap.get('everything_tokens') or 0):,}. Choose a larger model "
                        "in Config > Models to switch it off."),
        }
    try:
        from django.db import transaction

        from .models import Agent, Mcp, Skill, Tool
        with transaction.atomic():
            row = _row()
            if not row.active:
                return {"ok": True, "changed": False, "state": state()}
            Mcp.objects.exclude(mcpContent="true").update(mcpContent="true")
            Tool.objects.exclude(toolContent="true").update(toolContent="true")
            Agent.objects.exclude(agentContent="true").update(agentContent="true")
            Skill.objects.filter(enabled=False).update(enabled=True)
            try:
                saved_external = [str(k) for k in json.loads(row.saved_external_active or "[]")]
            except (TypeError, ValueError):
                saved_external = []
            row.active = False
            row.saved_external_active = "[]"
            row.reason = str(reason or "")[:300]
            row.save()
        if saved_external:
            _set_external_active(saved_external)
        with _LOCK:
            _STATE.update(loaded=True, active=False, reason=str(reason or ""), since=time.time())
        global_state.set_state(GLOBAL_ACTIVE_KEY, False)
        apply_rows_to_global_state("Compact mode OFF")
        print(f"--- [COMPACT] Compact mode OFF ({reason or 'by the user'}) - every MCP, tool, "
              f"agent and skill row is ticked again; External MCPs restored: {saved_external}")
        notify("off")
        return {"ok": True, "changed": True, "state": state()}
    except Exception as exc:  # noqa: BLE001
        print(f"--- [COMPACT] could not switch Compact mode OFF ({exc})")
        return {"ok": False, "changed": False, "error": str(exc), "state": state()}


def set_active(enabled: bool, reason: str = "", *, force: bool = False) -> Dict[str, Any]:
    return enter_compact(reason) if enabled else leave_compact(reason, force=force)


# ── The fitter's verdict ────────────────────────────────────────────────────
def note_capacity(*, model: str, strict: bool, window_tokens: int, usable_tokens: int = 0,
                  everything_tokens: int = 0, base_tokens: int = 0,
                  chars_per_token: float = 0.0, setting: str = "auto",
                  auto_enter: bool = True) -> bool:
    """Remember what the current model can hold.  A STRICT model (it cannot
    hold everything activated) switches Compact mode ON automatically.
    Returns True when that switch happened now.  Never raises."""
    try:
        _load()
        model = str(model or "")
        with _LOCK:
            changed = (bool(strict) != _STATE["strict"] or model != _STATE["model"]
                       or int(window_tokens or 0) != int(_STATE["window_tokens"] or 0))
            _STATE.update(strict=bool(strict), model=model, window_tokens=int(window_tokens or 0),
                          usable_tokens=int(usable_tokens or 0),
                          everything_tokens=int(everything_tokens or 0),
                          base_tokens=int(base_tokens or 0),
                          chars_per_token=float(chars_per_token or 0.0), setting=str(setting or "auto"))
            active = bool(_STATE["active"])
        if changed:
            try:
                from .models import CompactState
                _row()
                CompactState.objects.filter(pk=1).update(
                    strict=bool(strict), model=model[:200], window_tokens=int(window_tokens or 0))
            except Exception:  # noqa: BLE001 - the verdict still lives in memory
                pass
            print(f"--- [COMPACT] {model or 'the model'}: window {int(window_tokens or 0):,} tokens; "
                  f"everything activated needs ~{int(everything_tokens or 0):,} -> "
                  + ("STRICT - Compact mode is locked ON" if strict
                     else "it fits - Compact mode can be ticked or unticked freely"))
        if strict and not active and auto_enter:
            result = enter_compact(
                f"{model or 'this model'} reads only {int(window_tokens or 0):,} tokens and everything "
                f"activated needs ~{int(everything_tokens or 0):,}", auto=True)
            return bool(result.get("changed"))
        if changed:
            notify("capacity")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"--- [COMPACT] capacity not noted ({exc})")
        return False


# ── The Self-modify switch (Angela, 2026-10-03) ───────────────────────────────
def self_modify_available() -> bool:
    """Can this build self-modify at all?  ALWAYS from source (dev mode); a
    frozen build only with ``--self-modify``.  False = the box is not even
    rendered.  Never raises."""
    try:
        from .rag.config import self_modify_available as _available
        return bool(_available())
    except Exception:  # noqa: BLE001
        return False


def self_modify_wanted() -> bool:
    """The user's choice (ON by default)."""
    _load()
    with _LOCK:
        return bool(_STATE["self_modify"])


def self_modify_active() -> bool:
    """Send Tlamatini's self-knowledge?  The build can, the user wants it, and
    the fitter did not find it too big for the model."""
    if not self_modify_available():
        return False
    _load()
    with _LOCK:
        return bool(_STATE["self_modify"]) and _STATE["self_modify_fits"] is not False


def set_self_modify(enabled: bool, reason: str = "") -> Dict[str, Any]:
    """The toolbar's "Self-modify" box.  Refused when the build cannot
    self-modify, and - tick only - while the model cannot hold it."""
    enabled = bool(enabled)
    if not self_modify_available():
        return {"ok": False, "changed": False, "refused": "unavailable", "state": state(),
                "message": ("Self-modify is not available: this build was made without "
                            "--self-modify, so it carries neither its source nor its self-knowledge.")}
    snap = state()
    if enabled and snap.get("self_modify_fits") is False:
        return {
            "ok": False, "changed": False, "refused": "too_small", "state": snap,
            "message": (f"Self-modify stays OFF: {snap.get('model') or 'this model'} reads only "
                        f"{int(snap.get('window_tokens') or 0):,} tokens, and your request with "
                        f"Tlamatini's self-knowledge (~{int(snap.get('self_modify_tokens') or 0):,} "
                        f"tokens) needs ~{int(snap.get('self_modify_need_tokens') or 0):,}. Choose a "
                        "larger model in Config > Models, or untick some agents."),
        }
    try:
        _load()
        with _LOCK:
            if bool(_STATE["self_modify"]) == enabled:
                return {"ok": True, "changed": False, "state": state()}
        from .models import CompactState
        _row()
        CompactState.objects.filter(pk=1).update(self_modify=enabled)
        with _LOCK:
            _STATE["self_modify"] = enabled
        print(f"--- [SELF-MODIFY] Self-modify {'ON' if enabled else 'OFF'} ({reason or 'by the user'}) - "
              + ("Tlamatini's self-knowledge rides along with every request that can hold it"
                 if enabled else "Tlamatini's self-knowledge is no longer sent"))
        notify("self_modify")
        return {"ok": True, "changed": True, "state": state()}
    except Exception as exc:  # noqa: BLE001
        print(f"--- [SELF-MODIFY] could not switch Self-modify {'ON' if enabled else 'OFF'} ({exc})")
        return {"ok": False, "changed": False, "error": str(exc), "state": state()}


def note_self_modify(*, fits: bool, tokens: int = 0, need_tokens: int = 0) -> bool:
    """The fitter's verdict: can this model hold the self-knowledge on top of
    the request?  Remembered, logged and sent to every tab when it changes.
    Returns True when it changed.  Never raises."""
    try:
        if not self_modify_available():
            return False
        _load()
        with _LOCK:
            changed = _STATE["self_modify_fits"] is None or bool(fits) != bool(_STATE["self_modify_fits"])
            _STATE.update(self_modify_fits=bool(fits), self_modify_tokens=int(tokens or 0),
                          self_modify_need_tokens=int(need_tokens or 0))
            model = str(_STATE["model"] or "the model")
            window = int(_STATE["window_tokens"] or 0)
        if changed:
            print(f"--- [SELF-MODIFY] {model}: window {window:,} tokens; the self-knowledge adds "
                  f"~{int(tokens or 0):,} (request with it ~{int(need_tokens or 0):,}) -> "
                  + ("it fits - Self-modify can be ticked or unticked freely" if fits
                     else "it does NOT fit - Self-modify is locked OFF"))
            notify("self_modify")
        return changed
    except Exception as exc:  # noqa: BLE001
        print(f"--- [SELF-MODIFY] verdict not noted ({exc})")
        return False


# ── A Configure dialog was saved ────────────────────────────────────────────
def _wrapped_maps():
    """display.lower() -> tool_description.lower(), and the reverse."""
    try:
        from .chat_agent_registry import WRAPPED_CHAT_AGENT_SPECS
        by_agent = {str(s.display_name).lower(): str(s.tool_description).lower()
                    for s in WRAPPED_CHAT_AGENT_SPECS}
    except Exception:  # noqa: BLE001
        by_agent = {}
    by_tool = {tool: agent for agent, tool in by_agent.items()}
    return by_agent, by_tool


def _rows_map(rows: Iterable[Dict[str, Any]], desc_key: str, content_key: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for row in rows or []:
        try:
            out[str(row.get(desc_key) or "").lower()] = str(row.get(content_key) or "")
        except Exception:  # noqa: BLE001
            continue
    return out


def _set_tools(descriptions: Iterable[str], content: str) -> int:
    from .models import Tool
    done = 0
    for descr in descriptions:
        done += Tool.objects.filter(toolDescription__iexact=descr).exclude(
            toolContent=content).update(toolContent=content)
    return done


def _set_agents(displays: Iterable[str], content: str) -> int:
    from .models import Agent
    done = 0
    for display in displays:
        done += Agent.objects.filter(agentDescription__iexact=display).exclude(
            agentContent=content).update(agentContent=content)
    return done


def _link_rows(kind: str, before: Iterable[Dict[str, Any]]) -> List[str]:
    """Chain each agent to the tool row(s) that gate it - both gates must be on
    for the model to SEE an agent, so ticking one ticks the other."""
    from .models import Agent, Tool
    by_agent, by_tool = _wrapped_maps()
    direct_by_tool = {t: a for a, tools in AGENT_DIRECT_TOOLS.items() for t in tools}
    linked: List[str] = []
    turned_on_agent = False
    if kind == "agent":
        old = _rows_map(before, "agentDescription", "agentContent")
        now = _rows_map(Agent.objects.all().values("agentDescription", "agentContent"),
                        "agentDescription", "agentContent")
        for display, content in now.items():
            if old.get(display) == content or content not in ("true", "false"):
                continue
            tools = [by_agent[display]] if display in by_agent else []
            tools += list(AGENT_DIRECT_TOOLS.get(display, ()))
            if tools and _set_tools(tools, content):
                linked.append(f"{display} -> {', '.join(tools)} = {content}")
            if content == "true" and (display in by_agent or display in AGENT_DIRECT_TOOLS):
                turned_on_agent = True
    elif kind == "tool":
        old = _rows_map(before, "toolDescription", "toolContent")
        now = _rows_map(Tool.objects.all().values("toolDescription", "toolContent"),
                        "toolDescription", "toolContent")
        for descr, content in now.items():
            if old.get(descr) == content or content not in ("true", "false"):
                continue
            if descr in by_tool:
                if _set_agents([by_tool[descr]], content):
                    linked.append(f"{descr} -> agent {by_tool[descr]} = {content}")
                turned_on_agent = turned_on_agent or content == "true"
            elif descr in direct_by_tool and content == "true":
                if _set_agents([direct_by_tool[descr]], "true"):
                    linked.append(f"{descr} -> agent {direct_by_tool[descr]} = true")
    if turned_on_agent and is_active():
        if _set_tools(COMPANION_TOOLS, "true"):
            linked.append(f"companions {', '.join(COMPANION_TOOLS)} = true")
    return linked


def after_toggles_saved(kind: str, before: Iterable[Dict[str, Any]] = ()) -> Dict[str, Any]:
    """A Configure dialog was saved: link, apply at once, notify.  Never raises."""
    linked: List[str] = []
    try:
        linked = _link_rows(kind, before)
        if linked:
            print(f"--- [TOGGLES] chained rows: {'; '.join(linked)}")
    except Exception as exc:  # noqa: BLE001
        print(f"--- [TOGGLES] rows not chained ({exc})")
    applied = apply_rows_to_global_state(f"{kind} rows saved")
    notify("rows")
    return {"applied": applied, "linked": linked}


# ── Telling every open tab ──────────────────────────────────────────────────
def register_loop(loop: Any, layer: Any) -> None:
    """The chat consumers' event loop + channel layer (one per process)."""
    with _LOCK:
        _NOTIFY.update(loop=loop, layer=layer)


def notify(kind: str = "state") -> bool:
    """Send ``compact_mode_changed`` to every chat tab.  Call it from a SYNC
    context (a worker thread); never raises."""
    with _LOCK:
        loop, layer = _NOTIFY["loop"], _NOTIFY["layer"]
    if loop is None or layer is None:
        return False
    try:
        payload = {"type": "compact_mode_changed", "kind": str(kind), "state": state()}
        coro = layer.group_send(GROUP, payload)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            loop.create_task(coro)
        else:
            asyncio.run_coroutine_threadsafe(coro, loop)
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"--- [COMPACT] tabs not notified ({exc})")
        return False


# ── What the chat shows after a CUT answer ──────────────────────────────────
def cut_warning_html(cut: Dict[str, Any]) -> str:
    """The warning line a CUT answer carries (Angela: "yes show the warning")."""
    try:
        model = html.escape(str(cut.get("model") or "the model"))
        window = int(cut.get("window") or 0)
        sent = int(cut.get("sent_tokens") or 0)
        sent_text = f" of the ~{sent:,} tokens sent" if sent > window else ""
        return (
            '<div class="tlm-cut-warning" role="alert">&#9888;&#65039; <b>CONTEXT-WINDOW exceeded</b> - '
            f"{model} could read only {window:,} tokens{sent_text}, so part of this request was cut "
            "and this answer may be incomplete or wrong. Untick some agents or tools in "
            "Config &gt; Configure Agents / Configure MCPs, shorten the request, or choose a larger "
            "model in Config &gt; Models.</div>\n"
        )
    except Exception:  # noqa: BLE001
        return ""


# ── What each row costs (the Configure dialogs) ─────────────────────────────
def costs() -> Dict[str, Any]:
    """What each Configure row costs, for the dialogs' labels and budget line.

    ``entries`` is the gate table (``tools.tool_gate_table``) with the tokens
    each tool's schema adds to every request - measured on the real schemas
    with the fitter's own estimate, cached for the process.  A tool is bound
    when its Tool row is on AND (if it has one) its Agent row is on, so the
    page can project ANY selection exactly.  ``enabled_tools`` /
    ``enabled_agents`` are the rows on right now (description lower-cased).
    Never raises.
    """
    snap = state()
    try:
        with _LOCK:
            entries = list(_COSTS.get("entries") or [])
        if not entries:
            from .mcp_agent import _estimate_tool_schema_tokens
            from .tools import tool_gate_table
            for key, agent_display, build in tool_gate_table():
                try:
                    tokens = int(_estimate_tool_schema_tokens(build()))
                except Exception:  # noqa: BLE001
                    continue
                entries.append({"key": str(key).lower(),
                                "agent": str(agent_display).lower() if agent_display else "",
                                "tokens": tokens})
            with _LOCK:
                _COSTS["entries"] = list(entries)
        # A row gated by its NAME (the ACPX rows) is shown by its DESCRIPTION:
        # the page looks rows up by the text it shows.
        try:
            from .models import Tool as _Tool
            by_name = {str(n or "").lower(): str(d or "").lower()
                       for n, d in _Tool.objects.values_list("toolName", "toolDescription")
                       if n and not _NUMBERED_ROW.match(str(n))}
        except Exception:  # noqa: BLE001
            by_name = {}
        entries = [dict(e, key=by_name.get(e["key"], e["key"])) for e in entries]
        tools: Dict[str, int] = {}
        agents: Dict[str, int] = {}
        for entry in entries:
            tools[entry["key"]] = tools.get(entry["key"], 0) + int(entry["tokens"])
            if entry["agent"]:
                agents[entry["agent"]] = agents.get(entry["agent"], 0) + int(entry["tokens"])
        enabled_tools: List[str] = []
        enabled_agents: List[str] = []
        try:
            from .models import Agent, Tool
            enabled_tools = [str(d or "").lower() for d in Tool.objects.filter(
                toolContent="true").values_list("toolDescription", flat=True)]
            enabled_agents = [str(d or "").lower() for d in Agent.objects.filter(
                agentContent="true").values_list("agentDescription", flat=True)]
        except Exception:  # noqa: BLE001 - no database: the page projects from its dialog only
            pass
        return {"ok": True, "entries": entries, "tools": tools, "agents": agents,
                "enabled_tools": enabled_tools, "enabled_agents": enabled_agents,
                "state": snap}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "entries": [], "tools": {}, "agents": {},
                "enabled_tools": [], "enabled_agents": [], "state": snap}
