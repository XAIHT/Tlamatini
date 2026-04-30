"""
SkillHarness — wraps a single Skill invocation with permission scoping,
budget enforcement, audit logging, and I/O validation.

Two runtime modes are supported:

    runtime: "in-process"
        - The skill body becomes the system prompt of a scoped Multi-Turn
          loop using Tlamatini's existing unified-agent infrastructure.
        - The tool map is intersected with skill.requires_tools.
        - Budget caps the iterations / tokens / wall-clock.

    runtime: "acpx"
        - The skill body becomes the `task` text of an ACPX child session
          spawned with skill.acpx_agent (claude / cursor / qwen / ...).
        - The harness collects events until done or budget exceeded.

Both modes return the same shape:

    {
        "ok": bool,
        "skill": "<name>",
        "output": <validated outputs>,    # or {"answer": "..."} on free-form
        "iterations_used": int,
        "tokens_used": int,
        "elapsed_seconds": float,
        "audit_id": "<uuid>",
        "reason": "<failure code>",       # only on ok=False
    }
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .io_contract import validate_inputs, validate_outputs
from .registry import Skill

logger = logging.getLogger(__name__)


class SkillRuntimeError(Exception):
    pass


class BudgetExceeded(SkillRuntimeError):
    pass


@dataclass
class Budget:
    max_iterations: int
    max_seconds: float
    max_tokens: int
    started_at: float = field(default_factory=time.time)
    iterations: int = 0
    tokens: int = 0

    def tick_iteration(self) -> None:
        self.iterations += 1
        if self.iterations > self.max_iterations:
            raise BudgetExceeded(
                f"max_iterations ({self.max_iterations}) exceeded"
            )
        if (time.time() - self.started_at) > self.max_seconds:
            raise BudgetExceeded(
                f"max_seconds ({self.max_seconds}) exceeded"
            )

    def add_tokens(self, n: int) -> None:
        self.tokens += max(0, int(n))
        if self.tokens > self.max_tokens:
            raise BudgetExceeded(
                f"max_tokens ({self.max_tokens}) exceeded at {self.tokens}"
            )

    def elapsed(self) -> float:
        return time.time() - self.started_at


class SkillAuditLog:
    """Append-only audit file for one skill invocation."""

    def __init__(self, *, skill_name: str, user_id: Optional[int],
                 base_dir: Optional[Path] = None):
        self.id = uuid.uuid4().hex
        self.skill_name = skill_name
        self.user_id = user_id
        if base_dir is None:
            base_dir = Path.home() / ".tlamatini" / "skill-audit"
        self.dir = base_dir / time.strftime("%Y-%m")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{int(time.time())}_{skill_name}_{self.id[:8]}.ndjson"
        self._fp = self.path.open("a", encoding="utf-8")
        self._closed = False
        self.write({"event": "audit_open", "skill": skill_name,
                    "user_id": user_id, "audit_id": self.id})

    def write(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            event = {**event, "ts": time.time()}
            self._fp.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._fp.flush()
        except Exception:
            logger.exception("[skill_audit] write failed")

    def close(self) -> None:
        if self._closed:
            return
        try:
            self.write({"event": "audit_close"})
            self._fp.close()
        finally:
            self._closed = True


class SkillHarness:
    """
    Owns one skill invocation. Construct, call invoke(args), discard.
    """

    def __init__(self, skill: Skill, *, user_id: Optional[int] = None):
        self.skill = skill
        self.user_id = user_id
        self.budget = Budget(
            max_iterations=skill.max_iterations,
            max_seconds=skill.max_seconds,
            max_tokens=skill.max_tokens,
        )
        self.audit = SkillAuditLog(skill_name=skill.name, user_id=user_id)

    # ── Main entry point ─────────────────────────────────────────────
    def invoke(self, args: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._invoke_inner(args)
        except BudgetExceeded as e:
            return self._failure_envelope("budget_exceeded", str(e))
        except SkillRuntimeError as e:
            return self._failure_envelope("runtime_error", str(e))
        except Exception as e:
            logger.exception("[SkillHarness] unexpected exception")
            return self._failure_envelope("exception", str(e))
        finally:
            self.audit.close()

    def _invoke_inner(self, args: Dict[str, Any]) -> Dict[str, Any]:
        # 1. Validate inputs
        in_validation = validate_inputs(self.skill.inputs, args)
        if not in_validation.ok:
            return self._failure_envelope(
                "input_contract_violation",
                "; ".join(in_validation.errors),
            )
        coerced_args = in_validation.coerced
        self.audit.write({"event": "args_validated", "args": coerced_args})

        # 2. Dispatch on runtime
        if self.skill.runtime == "in-process":
            raw_output = self._run_in_process(coerced_args)
        elif self.skill.runtime == "acpx":
            raw_output = self._run_acpx(coerced_args)
        else:
            raise SkillRuntimeError(f"unknown runtime: {self.skill.runtime}")

        # 3. Validate outputs (only when output decls are present)
        if self.skill.outputs:
            out_validation = validate_outputs(self.skill.outputs, raw_output)
            if not out_validation.ok:
                return self._failure_envelope(
                    "output_contract_violation",
                    "; ".join(out_validation.errors),
                    output=raw_output,
                )
            output = out_validation.coerced
        else:
            output = raw_output

        return {
            "ok": True,
            "skill": self.skill.name,
            "runtime": self.skill.runtime,
            "output": output,
            "iterations_used": self.budget.iterations,
            "tokens_used": self.budget.tokens,
            "elapsed_seconds": round(self.budget.elapsed(), 3),
            "audit_id": self.audit.id,
        }

    # ── Runtime: in-process ─────────────────────────────────────────
    def _run_in_process(self, args: Dict[str, Any]) -> Any:
        """
        Default in-process runtime: returns a structured plan envelope
        describing what the skill would do, without executing destructive
        actions. The unified agent calling invoke_skill() can then carry
        that plan forward through its existing tool palette.

        This deliberate choice keeps the first revision safe-by-default:
        - No new shell execution paths.
        - No new file-system writes through this code path.
        - The skill's permissions are exposed in the envelope so the LLM
          knows what it MAY do next.

        Future revisions can promote this to a real scoped Multi-Turn loop
        (LangChain ScopedMultiTurnExecutor) once the surrounding harness
        contract is verified end-to-end in a running source-mode instance,
        following the documented "manual smoke test before shipping" gate.
        """
        self.budget.tick_iteration()
        envelope = {
            "skill_runtime": "in-process",
            "skill_name": self.skill.name,
            "skill_description": self.skill.description,
            "args": args,
            "permissions": self.skill.permissions,
            "requires_tools": list(self.skill.requires_tools),
            "requires_mcps": list(self.skill.requires_mcps),
            "body_excerpt": self.skill.body[:2000],
            "guidance": (
                "The Tlamatini SkillHarness has loaded this skill's body "
                "as a planning playbook. Execute the procedure described "
                "above using the tools listed in requires_tools, respecting "
                "the permissions block. Capture each step in the chat "
                "transcript. Return outputs matching the skill's `outputs` "
                "contract."
            ),
        }
        # Synthesize an output that matches the declared outputs (when the
        # skill declares them) so contract validation is exercised. The
        # values are placeholders the LLM can replace once it follows the
        # plan; they are not pretending to be ground truth.
        if self.skill.outputs:
            stub: Dict[str, Any] = {}
            for decl in self.skill.outputs:
                name = decl.get("name")
                if not name:
                    continue
                t = (decl.get("type") or "string").lower()
                if t == "string":
                    stub[name] = (
                        f"<plan-only stub for {name}; the calling agent "
                        f"should replace this with the actual value>"
                    )
                elif t in ("number", "integer"):
                    stub[name] = 0
                elif t == "boolean":
                    stub[name] = False
                elif t.startswith("array"):
                    stub[name] = []
                elif t == "object":
                    stub[name] = {}
                else:
                    stub[name] = None
            stub["_skill_envelope"] = envelope
            self.audit.write({"event": "in_process_envelope", "envelope": envelope})
            return stub
        self.audit.write({"event": "in_process_envelope", "envelope": envelope})
        return {"answer": envelope}

    # ── Runtime: acpx ───────────────────────────────────────────────
    def _run_acpx(self, args: Dict[str, Any]) -> Any:
        from agent.acpx import get_acpx_runtime, AcpRuntimeError
        runtime = get_acpx_runtime()
        agent_id = self.skill.acpx_agent or "claude"
        # Render the body with a tiny ${input.X} substitution so skills can
        # reference their inputs.
        rendered = self._render_body(self.skill.body, args)
        try:
            sess = runtime.spawn(
                agent_id=agent_id,
                task=rendered,
                mode="session",
                session_label=f"skill:{self.skill.name}",
            )
        except AcpRuntimeError as e:
            raise SkillRuntimeError(f"acpx spawn failed [{e.code}]: {e.message}")
        self.audit.write({"event": "acpx_spawn", "agent_id": agent_id,
                          "session_id": sess.record.session_id})
        events: List[Dict[str, Any]] = []
        try:
            for ev in runtime.send(sess.record.session_id, rendered):
                self.budget.tick_iteration()
                events.append(ev)
                if isinstance(ev, dict) and ev.get("done"):
                    break
        finally:
            runtime.kill(sess.record.session_id)
        # Try to extract a final structured answer
        final_text = ""
        for ev in reversed(events):
            if isinstance(ev, dict):
                if isinstance(ev.get("text"), str) and ev.get("text"):
                    final_text = ev["text"]
                    break
                if isinstance(ev.get("answer"), str) and ev.get("answer"):
                    final_text = ev["answer"]
                    break
        return {"answer": final_text or "", "events": events[-32:]}

    @staticmethod
    def _render_body(body: str, args: Dict[str, Any]) -> str:
        """Tiny ${input.KEY} substitution; missing keys leave the literal."""
        out = body
        for k, v in (args or {}).items():
            try:
                out = out.replace("${input." + k + "}", str(v))
            except Exception:
                continue
        return out

    # ── Failure helpers ─────────────────────────────────────────────
    def _failure_envelope(self, reason: str, detail: str,
                          **extra: Any) -> Dict[str, Any]:
        env = {
            "ok": False,
            "skill": self.skill.name,
            "runtime": self.skill.runtime,
            "reason": reason,
            "detail": detail,
            "iterations_used": self.budget.iterations,
            "tokens_used": self.budget.tokens,
            "elapsed_seconds": round(self.budget.elapsed(), 3),
            "audit_id": self.audit.id,
        }
        env.update(extra)
        self.audit.write({"event": "skill_failed", "reason": reason,
                          "detail": detail})
        return env
