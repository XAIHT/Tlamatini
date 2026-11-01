# Tlamatini Author Banner — Created by Angela López Mendoza · @angelahack1
"""The model gets actions and explicit arguments. HTTP destinations and credentials are private."""

import uuid
from typing import Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from .agents.torrenter.contract import DURABLE, FIELDS, TorrentError, validated
from .context_governor import current_user
from .torrenter_bridge import profile_for


class TorrenterInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal[tuple(FIELDS)]
    arguments: dict = Field(
        default_factory=dict,
        description=(
            "Named JSON fields for the chosen action. IDs are the Jobs IDs, revision is the last observed integer. "
            + " | ".join(
                k + "(" + r + (" [" + o + "]" if o else "") + ")"
                for k, (r, o) in FIELDS.items()
            )
            + ". A durable write may take operation_key (32 lowercase hex), reused only for an identical retry."
        ),
    )


def build_tool(spec, launch, output):
    def refuse(message):
        return output(
            {
                "status": "refused",
                "success": False,
                "error_kind": "request",
                "message": message,
            }
        )

    def run(action, arguments=None):
        try:
            fields = validated(action, arguments or {})
            profile_for(current_user())
        except TorrentError as exc:
            return refuse(str(exc))
        if action in DURABLE:
            fields.setdefault("operation_key", uuid.uuid4().hex)
        return launch(
            spec,
            "Torrenter " + action,
            config_overrides={"action": action, "arguments": fields},
        )

    return StructuredTool.from_function(
        func=run,
        name=spec.tool_name,
        description=spec.purpose,
        args_schema=TorrenterInput,
        handle_validation_error=lambda _: refuse(
            "Use a documented action and a named arguments object."
        ),
    )
