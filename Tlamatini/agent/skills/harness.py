# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""
SkillHarness — one skill invocation: contract validation, secret redaction,
audit logging, and delivery of the skill's procedure to whoever will run it.

⚠️ WHAT THIS IS — AND WHAT IT IS NOT (settled 2026-09-23)
---------------------------------------------------------
``runtime: in-process`` is a **PLANNING HANDOFF, not an executor.** The
harness loads the skill, validates the arguments against its contract, and
hands the calling agent the COMPLETE procedure to carry out with its own
tool palette. It does not run the steps, and it does not produce the
skill's deliverables.

That was always the design (it is why this path opens no shell and writes
no file), but the envelope used to *read* like completed work: it returned
``ok: true`` beside schema-shaped placeholder values in the ``output`` key,
so a caller could not tell a stub from a result. A ``doctor_ok: false``
stub is not a failed doctor; it is a doctor that never ran.

The envelope now says so explicitly and carries no fabricated values:

    ``status``            planned | completed | failed
    ``completed``         False for a planning handoff — the work is ahead
    ``output``            ONLY real values. ``{}`` on a planning handoff.
    ``pending_outputs``   the contract the caller must still satisfy
    ``plan``              the full procedure + what it may use
    ``enforcement``       what the harness ACTUALLY enforces (see below)

**Do NOT reintroduce placeholder values under ``output``.** A schema-valid
stub is the plausible-but-wrong deliverable class this codebase keeps
paying for (the PDFer missing images, the LaTeXer linter verdict, the ACPX
blocked child). If a scoped executor is ever built, it sets
``status: "completed"`` and fills ``output`` with what it measured.

``runtime: "acpx"`` DOES execute: it spawns an ACPX child, and its result
is subject to the same delivery verdict the ``acp_*`` tools use, so a
blocked or empty child can never be reported as a success.

WHAT IS ACTUALLY ENFORCED (do not overstate it — R03)
-----------------------------------------------------
+------------------------+------------------------------------------------+
| input/output contract  | ENFORCED — validated here, failure is returned |
| secret redaction       | ENFORCED — audit + envelope, see redaction.py  |
| wall-clock deadline    | ENFORCED for this invocation (both runtimes)   |
| iteration cap          | ENFORCED for this invocation                   |
| token cap              | ADVISORY — the harness spends no model tokens; |
|                        |   the caller's own budget governs its work     |
| permissions / tools    | ADVISORY at this boundary — declared, surfaced |
|                        |   and carried in the plan; enforced by the      |
|                        |   caller's existing tool gates (Configure       |
|                        |   Mcps/Tools, Configure Agents, Ask-Execs)      |
+------------------------+------------------------------------------------+

The ``enforcement`` block in every envelope states this in machine-readable
form. **If you add real scoping, update that block in the same commit** —
a guarantee that is only documented is the bug this section exists to fix.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .io_contract import validate_inputs, validate_outputs
from .redaction import (
    redact_args,
    redact_structure,
    collect_secret_values,
    scrub_text,
    sensitive_input_names,
)
from .registry import Skill

logger = logging.getLogger(__name__)

#: Execution states. ``planned`` means the procedure was delivered and the
#: work is still ahead; ``completed`` means this harness observed the work.
STATUS_PLANNED = "planned"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

#: A skill body is delivered WHOLE (R02). This ceiling exists only so a
#: pathological file cannot blow the tool-result channel — and when it
#: fires it is stated in the envelope, never silent. Every shipped skill is
#: far below it (the largest is ~8.5k chars).
MAX_BODY_CHARS = 64_000

#: Reference files are listed with absolute paths and sizes rather than
#: inlined, so one skill's references cannot crowd out its own procedure.
#: ``plan.references_inlined`` states this; it is never implied.
_REFERENCE_SUFFIXES = (".md", ".txt", ".json", ".yaml", ".yml", ".py", ".ps1")
_MAX_REFERENCES_LISTED = 40


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

    def remaining_seconds(self) -> float:
        """Wall-clock left before ``max_seconds`` trips. Never negative."""
        return max(0.0, self.max_seconds - self.elapsed())


class SkillAuditLog:
    """Append-only audit file for one skill invocation.

    ⚠️ Every event passes through ``redaction`` before it is serialized.
    A credential must never reach this file; see ``redaction.py``.
    """

    def __init__(self, *, skill_name: str, user_id: Optional[int],
                 base_dir: Optional[Path] = None):
        self.id = uuid.uuid4().hex
        self.skill_name = skill_name
        self.user_id = user_id
        #: Literal secret values seen during this invocation. Populated by
        #: the harness as soon as the inputs are validated, so every LATER
        #: event (including exception text) is swept for them.
        self._secrets: set = set()
        if base_dir is None:
            # Keep state under the installation directory, not the user's
            # home folder (which may be permission-restricted on corporate
            # machines).  Same _app_base_dir logic as acpx/config.py.
            import sys
            if getattr(sys, "frozen", False):
                _app_base = Path(os.path.dirname(sys.executable))
            else:
                _app_base = Path(__file__).resolve().parent.parent  # agent/
            base_dir = _app_base / ".tlamatini" / "skill-audit"
        self.dir = base_dir / time.strftime("%Y-%m")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / f"{int(time.time())}_{skill_name}_{self.id[:8]}.ndjson"
        self._fp = self.path.open("a", encoding="utf-8")
        self._closed = False
        self.write({"event": "audit_open", "skill": skill_name,
                    "user_id": user_id, "audit_id": self.id})

    def register_secrets(self, secrets: Any) -> None:
        """Teach this log which literal strings must never appear in it."""
        try:
            for s in secrets or ():
                if isinstance(s, str) and s:
                    self._secrets.add(s)
        except Exception:
            logger.debug("[skill_audit] register_secrets ignored a bad value")

    def write(self, event: Dict[str, Any]) -> None:
        if self._closed:
            return
        try:
            safe = redact_structure(event, secrets=self._secrets)
            if not isinstance(safe, dict):
                safe = {"event": "redaction_failed"}
            safe = {**safe, "ts": time.time()}
            self._fp.write(json.dumps(safe, ensure_ascii=False) + "\n")
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
        #: Literal credential values for this invocation. Held only in
        #: memory, never serialized, used to sweep free-form text.
        self._secrets: set = set()

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
            # ⚠️ The error strings are built from the caller's own values, so
            # they are swept before they leave (a "expected number, got str"
            # message can quote the offending value).
            self._learn_secrets(args)
            return self._failure_envelope(
                "input_contract_violation",
                "; ".join(in_validation.errors),
            )
        coerced_args = in_validation.coerced
        # Learn the credentials BEFORE the first audit write, so no event in
        # this invocation can carry one.
        self._learn_secrets(coerced_args)
        self.audit.write({
            "event": "args_validated",
            "args": redact_args(self.skill.inputs, coerced_args),
        })

        # 2. Dispatch on runtime
        if self.skill.runtime == "in-process":
            return self._plan_envelope(coerced_args)
        if self.skill.runtime == "acpx":
            raw_output, delivery = self._run_acpx(coerced_args)
        else:
            raise SkillRuntimeError(f"unknown runtime: {self.skill.runtime}")

        # 3. A child that demonstrably did none of the work is NOT a success.
        #    Same shared verdict the acp_* tools use — one definition, never
        #    a second vocabulary (see acpx/child_health.py).
        if delivery and delivery.get("delivered") is False:
            return self._failure_envelope(
                "not_delivered",
                delivery.get("failure_reason")
                or "the ACPX child produced no usable answer",
                output=self._safe(raw_output),
                code=delivery.get("code") or "NOT_DELIVERED",
                evidence=delivery.get("failure_evidence") or "",
            )

        # 4. Validate outputs (only when output decls are present)
        if self.skill.outputs:
            out_validation = validate_outputs(self.skill.outputs, raw_output)
            if not out_validation.ok:
                return self._failure_envelope(
                    "output_contract_violation",
                    "; ".join(out_validation.errors),
                    output=self._safe(raw_output),
                )
            output = out_validation.coerced
        else:
            output = raw_output

        return self._envelope(
            status=STATUS_COMPLETED,
            completed=True,
            output=self._safe(output),
        )

    # ── Runtime: in-process (PLANNING HANDOFF) ──────────────────────
    def _plan_envelope(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deliver the skill's COMPLETE procedure to the calling agent.

        This path executes nothing: no shell, no file write, no model call.
        It returns ``status: "planned"`` and an empty ``output`` so a caller
        can never mistake it for finished work, plus ``pending_outputs`` —
        the contract the caller must satisfy once it has actually run the
        steps.
        """
        self.budget.tick_iteration()

        body = self.skill.body or ""
        truncated = len(body) > MAX_BODY_CHARS
        delivered_body = body[:MAX_BODY_CHARS] if truncated else body

        plan: Dict[str, Any] = {
            "skill_name": self.skill.name,
            "skill_description": self.skill.description,
            "body": delivered_body,
            "body_chars": len(body),
            "body_chars_delivered": len(delivered_body),
            # ⚠️ Explicit, never implied. The old envelope silently cut the
            # body at 2,000 characters and still called it "loaded".
            "body_truncated": truncated,
            "body_sha256": self.skill.body_sha256,
            "skill_md_path": str(self.skill.skill_md_path),
            "references": self._reference_index(),
            "references_inlined": False,
            "requires_tools": list(self.skill.requires_tools),
            "requires_mcps": list(self.skill.requires_mcps),
            "permissions": self.skill.permissions,
            "args": redact_args(self.skill.inputs, args),
        }
        if truncated:
            plan["body_truncation_note"] = (
                f"The body exceeds {MAX_BODY_CHARS} characters and was cut. "
                f"Read the remainder from skill_md_path before acting; do "
                f"NOT treat this plan as the complete procedure."
            )
        if plan["references"]:
            plan["references_note"] = (
                "Reference files are listed by absolute path, not inlined. "
                "Read one with chat_agent_grepper (output_mode='lines', "
                "line_numbers=false) before relying on it."
            )

        envelope = self._envelope(
            status=STATUS_PLANNED,
            completed=False,
            output={},
        )
        envelope["plan"] = plan
        envelope["pending_outputs"] = self._pending_output_contract()
        envelope["guidance"] = (
            f"PLANNING HANDOFF — nothing has run yet. The SkillHarness "
            f"validated your arguments and loaded the complete '"
            f"{self.skill.name}' procedure above; it did NOT execute it. "
            f"Carry out the steps in plan.body using the tools in "
            f"plan.requires_tools, respecting plan.permissions, then report "
            f"the real values for every field in pending_outputs. Do not "
            f"report any pending_outputs field as an observation until you "
            f"have actually measured it."
        )
        self.audit.write({"event": "skill_planned",
                          "skill": self.skill.name,
                          "body_chars": len(body),
                          "body_truncated": truncated,
                          "pending_outputs": [
                              d.get("name") for d in envelope["pending_outputs"]
                          ]})
        return envelope

    def _pending_output_contract(self) -> List[Dict[str, Any]]:
        """The declared outputs, as a contract — never as fabricated values."""
        pending: List[Dict[str, Any]] = []
        for decl in self.skill.outputs or []:
            if not isinstance(decl, dict):
                continue
            name = decl.get("name")
            if not name:
                continue
            pending.append({
                "name": name,
                "type": (decl.get("type") or "string"),
                "required": bool(decl.get("required", False)),
                "description": decl.get("description") or "",
            })
        return pending

    def _reference_index(self) -> List[Dict[str, Any]]:
        """
        Every retrievable file that ships beside this SKILL.md.

        Absolute paths, so the caller never has to guess the source layout
        (it differs between source mode, the frozen bundle and the
        user-editable install copy). Fail-open: an unreadable directory
        yields an empty list rather than breaking the handoff.
        """
        refs: List[Dict[str, Any]] = []
        try:
            root = Path(self.skill.skill_dir)
            if not root.exists():
                return refs
            for path in sorted(root.rglob("*")):
                if len(refs) >= _MAX_REFERENCES_LISTED:
                    break
                try:
                    if not path.is_file():
                        continue
                    if path.name == "SKILL.md":
                        continue
                    if path.suffix.lower() not in _REFERENCE_SUFFIXES:
                        continue
                    refs.append({
                        "path": str(path.resolve()),
                        "relative_path": str(path.relative_to(root)).replace("\\", "/"),
                        "bytes": path.stat().st_size,
                    })
                except Exception:
                    continue
        except Exception:
            logger.debug("[SkillHarness] reference index unavailable", exc_info=True)
        return refs

    # ── Runtime: acpx ───────────────────────────────────────────────
    def _run_acpx(self, args: Dict[str, Any]):
        """Spawn an ACPX child and return ``(output, delivery_verdict)``.

        ⚠️ Two contracts this path must keep (R22, 2026-09-23):

        1. **Use the shared assistant-text extractor.** A reverse scan for
           "any event with text" can select a stderr LOG line emitted after
           the real answer and return the noise as the deliverable.
           ``extract_last_assistant_text`` already separates the two.
        2. **Use the shared delivery verdict.** A child that refused, could
           not authenticate, had no credit or printed nothing exits 0; the
           ``done`` event carries ``delivered`` and the caller must honour
           it. Never invent a second vocabulary here.
        """
        from agent.acpx import (
            get_acpx_runtime,
            AcpRuntimeError,
            extract_last_assistant_text,
        )
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
            # The skill's OWN deadline bounds the child, not just the
            # transport default — otherwise a skill declaring max_seconds: 30
            # could sit inside a 180 s drain.
            deadline = self.budget.remaining_seconds()
            for ev in runtime.send(sess.record.session_id, rendered,
                                   timeout_seconds=deadline or None):
                self.budget.tick_iteration()
                events.append(ev)
                if isinstance(ev, dict) and ev.get("done"):
                    break
        finally:
            try:
                runtime.kill(sess.record.session_id)
            except Exception:
                logger.warning("[SkillHarness] acpx kill failed for %s",
                               sess.record.session_id, exc_info=True)

        delivery = self._delivery_verdict(events)
        answer = extract_last_assistant_text(events)
        return {"answer": answer or "", "events": events[-32:]}, delivery

    @staticmethod
    def _delivery_verdict(events: Any) -> Dict[str, Any]:
        """The ``done`` event's delivery verdict, or ``{}`` when the
        transport does not stamp one (older transports are left alone)."""
        if isinstance(events, list):
            for event in reversed(events):
                if isinstance(event, dict) and event.get("done") \
                        and "delivered" in event:
                    return event
        return {}

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

    # ── Envelope helpers ────────────────────────────────────────────
    def _learn_secrets(self, args: Dict[str, Any]) -> None:
        """Record this invocation's credential values for later scrubbing."""
        try:
            names = sensitive_input_names(self.skill.inputs)
            found = collect_secret_values(args, names)
            self._secrets |= found
            self.audit.register_secrets(found)
        except Exception:
            logger.debug("[SkillHarness] secret learning skipped", exc_info=True)

    def _safe(self, value: Any) -> Any:
        """Redact anything on its way out to the caller."""
        return redact_structure(
            value,
            sensitive_input_names(self.skill.inputs),
            self._secrets,
        )

    def _enforcement_block(self) -> Dict[str, Any]:
        """
        What this harness ACTUALLY enforces, in machine-readable form.

        ⚠️ Keep this truthful. It exists because ``invoke_skill``'s
        description used to claim the harness enforced permissions and a
        token budget, and it enforced neither.
        """
        return {
            "input_contract": "enforced",
            "output_contract": "enforced" if self.skill.outputs else "not_declared",
            "secret_redaction": "enforced",
            "max_seconds": "enforced_for_this_invocation",
            "max_iterations": "enforced_for_this_invocation",
            "max_tokens": "advisory",
            "permissions": "advisory_declared_not_sandboxed",
            "requires_tools": "advisory_declared_not_scoped",
            "note": (
                "Permissions and requires_tools are declared policy carried "
                "in the plan; they are not a sandbox. Tool access is governed "
                "by Tlamatini's existing gates (Configure Mcps/Tools, "
                "Configure Agents, Ask-Execs). max_tokens is advisory because "
                "this harness spends no model tokens of its own."
            ),
        }

    def _envelope(self, *, status: str, completed: bool,
                  output: Any) -> Dict[str, Any]:
        return {
            "ok": True,
            "status": status,
            "completed": completed,
            "skill": self.skill.name,
            "runtime": self.skill.runtime,
            "output": output,
            "enforcement": self._enforcement_block(),
            "iterations_used": self.budget.iterations,
            "tokens_used": self.budget.tokens,
            "elapsed_seconds": round(self.budget.elapsed(), 3),
            "audit_id": self.audit.id,
        }

    # ── Failure helpers ─────────────────────────────────────────────
    def _failure_envelope(self, reason: str, detail: str,
                          **extra: Any) -> Dict[str, Any]:
        # ⚠️ ``detail`` is frequently built from the caller's own values
        # (a validation message quoting the offending input, an exception
        # string carrying a command line). Sweep it before it is returned
        # OR written to the audit file.
        safe_detail = scrub_text(detail, self._secrets)
        env = {
            "ok": False,
            "status": STATUS_FAILED,
            "completed": False,
            "skill": self.skill.name,
            "runtime": self.skill.runtime,
            "reason": reason,
            "detail": safe_detail,
            "enforcement": self._enforcement_block(),
            "iterations_used": self.budget.iterations,
            "tokens_used": self.budget.tokens,
            "elapsed_seconds": round(self.budget.elapsed(), 3),
            "audit_id": self.audit.id,
        }
        env.update({k: self._safe(v) for k, v in extra.items()})
        self.audit.write({"event": "skill_failed", "reason": reason,
                          "detail": safe_detail})
        return env
