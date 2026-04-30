"""
Permission gate for ACPX runtime.

The OpenClaw schema gives us three modes:

    - "approve-all"   : every action is auto-approved      (FLAGGED DANGEROUS)
    - "approve-reads" : reads auto-approved, writes deny   (default)
    - "deny-all"      : everything denied; effectively read-only

And a non-interactive policy:

    - "deny" : when no approval prompt can be shown, the action is denied
    - "fail" : when no approval prompt can be shown, the run fails hard

This module is the single decision point. The runtime never makes a
"should I let this happen?" call by hand; it always asks PermissionGate.

Action shape
------------
The `Action` is a structured intent the ACP child has expressed:
    { "kind": "shell" | "fs.read" | "fs.write" | "net" | "db", "detail": ... }

The gate returns:
    PermissionDecision(allowed=True/False, reason="...", needs_prompt=True/False)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Literal

ActionKind = Literal["shell", "fs.read", "fs.write", "net", "db", "tool"]


@dataclass
class Action:
    kind: ActionKind
    detail: Dict[str, Any]


@dataclass
class PermissionDecision:
    allowed: bool
    reason: str
    needs_prompt: bool = False


class PermissionGate:
    """
    Stateless permission gate. Construct with the runtime's permission_mode
    and non_interactive policy; call decide(action, interactive=...) to
    get a PermissionDecision.

    Note
    ----
    "interactive" is True when there is a UI/operator that can answer a
    permission prompt. In a Multi-Turn unattended run, it is False; the
    non-interactive policy then decides between deny / fail.
    """

    def __init__(self, permission_mode: str, non_interactive: str = "deny"):
        from .config import PERMISSION_MODES, NON_INTERACTIVE_POLICIES
        if permission_mode not in PERMISSION_MODES:
            permission_mode = "approve-reads"
        if non_interactive not in NON_INTERACTIVE_POLICIES:
            non_interactive = "deny"
        self.mode = permission_mode
        self.non_interactive = non_interactive

    def decide(self, action: Action, interactive: bool = False) -> PermissionDecision:
        # deny-all is a hard wall.
        if self.mode == "deny-all":
            return PermissionDecision(False, "permission_mode=deny-all", False)

        # approve-all auto-approves everything.
        if self.mode == "approve-all":
            return PermissionDecision(True, "permission_mode=approve-all", False)

        # approve-reads: reads auto-approved, writes need a prompt.
        if action.kind in ("fs.read",):
            return PermissionDecision(True, "read auto-approved", False)

        # Any non-read action requires an interactive prompt.
        if interactive:
            return PermissionDecision(True, "needs_prompt", needs_prompt=True)

        # Non-interactive: apply policy.
        if self.non_interactive == "fail":
            return PermissionDecision(
                False, "non_interactive=fail; cannot prompt for write", False
            )
        return PermissionDecision(False, "non_interactive=deny", False)


def is_dangerous_config(permission_mode: str) -> bool:
    """
    Mirrors OpenClaw's configContracts.dangerousFlags entry:
        permissionMode == "approve-all" is dangerous.
    """
    return permission_mode == "approve-all"
