# Tlamatini — "one who knows"
# Created by Angela López Mendoza · @angelahack1
# Tlamatini Author Banner — do not remove
"""Versioned .fpmt graph contract and deterministic prompt-flow-panel interpreter.

No Django or model imports: the runner receives an adapter for model/context work.
Files are data, never executable Python/JavaScript. A decision evaluates only the
documented string comparisons; cycles have an explicit execution budget.
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import datetime, timezone

# Keep the JSON contract stable when existing flow files are renamed to .fpmt.
FORMAT = "tlamatini-prompting-flow"
VERSION = 1
MAX_FILE_BYTES = 5 * 1024 * 1024
OPERATIONS = {
    "prompt", "programmed_prompt", "decision", "feed_embeddings",
    "flush_embeddings", "clean_history", "user_commentary",
}
COMPARISONS = {"contains", "not_contains", "equals", "is_empty", "user"}


class FlowError(ValueError):
    """A malformed document or an operation that could not complete."""


class FlowStopped(Exception):
    """Cooperative stop: no subsequent operation may start."""


def _text(value, label, maximum=100_000):
    if not isinstance(value, str) or len(value) > maximum:
        raise FlowError(f"{label} must be text of at most {maximum:,} characters.")
    return value


def _number(value, label, minimum, maximum, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FlowError(f"{label} must be a number.")
    if not math.isfinite(value) or not minimum <= value <= maximum or (integer and value != int(value)):
        raise FlowError(f"{label} must be between {minimum} and {maximum}.")
    return int(value) if integer else value


def scheduled_time(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("timezone missing")
        return result
    except (TypeError, ValueError) as exc:
        raise FlowError("Scheduled time must be an ISO date with a timezone.") from exc


def validate_flow(payload, *, playable=False):
    """Return a fresh, allowlisted document; do not mutate input or trust IDs."""
    if not isinstance(payload, dict) or payload.get("format") != FORMAT:
        raise FlowError("Open a Prompt Flow Panel .fpmt document (legacy prompt.pmt text is not a diagram).")
    if payload.get("version") != VERSION:
        raise FlowError("Unsupported .fpmt version. This panel supports version 1.")
    nodes, edges = payload.get("nodes"), payload.get("edges")
    if not isinstance(nodes, list) or len(nodes) > 500 or not isinstance(edges, list) or len(edges) > 1000:
        raise FlowError("A flow may contain up to 500 operations and 1,000 connections.")
    result = {
        "format": FORMAT, "version": VERSION,
        "name": _text(payload.get("name", "Untitled"), "Flow name", 120),
        "start": payload.get("start"),
        "max_steps": _number(payload.get("max_steps", 500), "Step limit", 1, 5000, True),
        "nodes": [], "edges": [],
    }
    known = {}
    for node in nodes:
        if not isinstance(node, dict):
            raise FlowError("Every operation must be an object.")
        node_id = _text(node.get("id"), "Operation ID", 80)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", node_id) or node_id in known:
            raise FlowError("Operation IDs must be unique letters, digits, underscores or dashes.")
        kind = node.get("type")
        if kind not in OPERATIONS:
            raise FlowError(f"Unknown operation: {kind!r}.")
        config = node.get("config", {})
        if not isinstance(config, dict):
            raise FlowError("Operation settings must be an object.")
        clean = {"text": _text(config.get("text", ""), "Operation text")}
        if kind in {"prompt", "programmed_prompt"}:
            for key in ("multi_turn", "acpx"):
                clean[key] = config.get(key, False)
                if not isinstance(clean[key], bool):
                    raise FlowError(f"{key} must be true or false.")
            if clean["acpx"] and not clean["multi_turn"]:
                raise FlowError("ACPX requires Multi-Turn.")
            if playable and not clean["text"].strip():
                raise FlowError(f"{node.get('label', kind)} needs prompt text.")
        if kind == "programmed_prompt":
            clean["delay_seconds"] = _number(config.get("delay_seconds", 0), "Delay", 0, 86400)
            clean["scheduled_at"] = _text(config.get("scheduled_at", ""), "Scheduled time", 60)
            scheduled_time(clean["scheduled_at"])
        if kind == "decision":
            clean["comparison"] = config.get("comparison", "contains")
            if clean["comparison"] not in COMPARISONS:
                raise FlowError("Unknown decision comparison.")
            clean["value"] = _text(config.get("value", ""), "Comparison value", 10000)
            clean["case_sensitive"] = config.get("case_sensitive", False)
            if not isinstance(clean["case_sensitive"], bool):
                raise FlowError("Case sensitivity must be true or false.")
            if playable and clean["comparison"] in {"contains", "not_contains", "equals"} and not clean["value"]:
                raise FlowError("Set a decision comparison value, or choose 'Output is empty'.")
        if kind == "feed_embeddings" and playable and not clean["text"].strip():
            raise FlowError("Feed embeddings needs text or {{last_output}}.")
        item = {
            "id": node_id, "type": kind,
            "label": _text(node.get("label", kind.replace("_", " ").title()), "Operation label", 120),
            "x": _number(node.get("x", 0), "X position", 0, 100000),
            "y": _number(node.get("y", 0), "Y position", 0, 100000),
            "config": clean,
        }
        known[node_id] = item
        result["nodes"].append(item)
    slots, edge_ids = set(), set()
    for edge in edges:
        if not isinstance(edge, dict):
            raise FlowError("Every connection must be an object.")
        edge_id = _text(edge.get("id"), "Connection ID", 80)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", edge_id) or edge_id in edge_ids:
            raise FlowError("Connection IDs must be unique letters, digits, underscores or dashes.")
        source, target = edge.get("source"), edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str) or source not in known or target not in known:
            raise FlowError("Every connection must join existing operations.")
        branch = edge.get("branch", "next")
        allowed = {"yes", "no"} if known[source]["type"] == "decision" else {"next"}
        if branch not in allowed or (source, branch) in slots:
            raise FlowError("Each output accepts one connection. Decisions have separate Yes and No outputs.")
        slots.add((source, branch))
        edge_ids.add(edge_id)
        result["edges"].append({"id": edge_id, "source": source, "target": target, "branch": branch})
    if result["start"] is not None and (not isinstance(result["start"], str) or result["start"] not in known):
        raise FlowError("The start operation does not exist.")
    if playable:
        if not nodes or result["start"] is None:
            raise FlowError("Add an operation and choose where the flow starts.")
        reachable, pending = set(), [result["start"]]
        while pending:
            current = pending.pop()
            if current in reachable:
                continue
            reachable.add(current)
            pending.extend(e["target"] for e in result["edges"] if e["source"] == current)
        if len(reachable) != len(nodes):
            raise FlowError("Some operations are unreachable from Start. Connect them or choose another Start.")
        for node in nodes:
            if node["type"] == "decision" and not all((node["id"], branch) in slots for branch in ("yes", "no")):
                raise FlowError("Connect both Yes and No outputs of every decision.")
    return result


def expand_text(text, last_output):
    return text.replace("{{last_output}}", last_output)


def decide(config, output):
    value = config["value"]
    if not config["case_sensitive"]:
        output, value = output.casefold(), value.casefold()
    return {"contains": lambda: value in output, "not_contains": lambda: value not in output,
            "equals": lambda: output.strip() == value.strip(), "is_empty": lambda: not output.strip()}[config["comparison"]]()


class FlowRunner:
    def __init__(self, flow, runtime, emit):
        self.flow = validate_flow(flow, playable=True)
        self.runtime, self.emit = runtime, emit
        self.stopped = asyncio.Event()
        self.resumed = asyncio.Event()
        self.resumed.set()
        self.reply_future = None
        self.reply_id = None
        self.last_output = ""
        self.step = 0

    async def gate(self):
        while not self.resumed.is_set() and not self.stopped.is_set():
            try:
                await asyncio.wait_for(self.stopped.wait(), 0.1)
            except asyncio.TimeoutError:
                pass
        if self.stopped.is_set():
            raise FlowStopped()

    def stop(self):
        self.stopped.set()
        self.resumed.set()
        self.runtime.cancel()
        if self.reply_future and not self.reply_future.done():
            self.reply_future.set_exception(FlowStopped())

    async def wait_delay(self, seconds):
        # Delay counts active time; a scheduled wall-clock time remains absolute.
        remaining = seconds
        while remaining > 0:
            await self.gate()
            interval = min(0.2, remaining)
            try:
                await asyncio.wait_for(self.stopped.wait(), interval)
            except asyncio.TimeoutError:
                remaining -= interval
        await self.gate()

    async def ask_user(self, node, kind):
        self.reply_id = f"{node['id']}-{self.step}"
        self.reply_future = asyncio.get_running_loop().create_future()
        await self.emit("input", node_id=node["id"], request_id=self.reply_id, kind=kind,
                        message=expand_text(node["config"]["text"], self.last_output))
        try:
            return await self.reply_future
        finally:
            self.reply_future = None
            self.reply_id = None

    def reply(self, request_id, value):
        if self.reply_future is None or self.reply_future.done() or request_id != self.reply_id:
            raise FlowError("This input request is no longer active.")
        self.reply_future.set_result(_text(value, "Reply"))

    async def run(self):
        nodes = {n["id"]: n for n in self.flow["nodes"]}
        edges = {(e["source"], e["branch"]): e for e in self.flow["edges"]}
        current = self.flow["start"]
        while current:
            await self.gate()
            self.step += 1
            if self.step > self.flow["max_steps"]:
                raise FlowError("Step limit reached. Inspect the loop or raise the flow's step limit.")
            node = nodes[current]
            kind, config = node["type"], node["config"]
            await self.emit("node", node_id=current, status="running", step=self.step)
            branch, output = "next", None
            if kind == "programmed_prompt":
                scheduled = scheduled_time(config["scheduled_at"])
                if scheduled:
                    await self.emit("waiting", node_id=current, message=f"Scheduled for {scheduled.isoformat()}")
                    while datetime.now(timezone.utc) < scheduled:
                        await self.wait_delay(min(0.5, (scheduled - datetime.now(timezone.utc)).total_seconds()))
                if config["delay_seconds"]:
                    await self.emit("waiting", node_id=current, message=f"Waiting {config['delay_seconds']:g} active seconds")
                    await self.wait_delay(config["delay_seconds"])
            await self.gate()
            if kind in {"prompt", "programmed_prompt"}:
                output = await self.runtime.prompt(expand_text(config["text"], self.last_output), config)
            elif kind == "feed_embeddings":
                await self.runtime.feed(expand_text(config["text"], self.last_output))
            elif kind == "flush_embeddings":
                await self.runtime.flush()
            elif kind == "clean_history":
                await self.runtime.clean_history()
                self.last_output = ""
            elif kind == "user_commentary":
                output = await self.ask_user(node, "commentary")
                await self.runtime.comment(output)
            elif kind == "decision":
                if config["comparison"] == "user":
                    response = await self.ask_user(node, "decision")
                    if response not in {"yes", "no"}:
                        raise FlowError("A decision reply must be Yes or No.")
                    branch = response
                else:
                    branch = "yes" if decide(config, self.last_output) else "no"
            await self.gate()
            if output is not None:
                self.last_output = output
                await self.emit("output", node_id=current, text=output)
            await self.emit("node", node_id=current, status="completed", step=self.step)
            edge = edges.get((current, branch))
            if edge:
                await self.emit("edge", edge_id=edge["id"], branch=branch)
            current = edge["target"] if edge else None

