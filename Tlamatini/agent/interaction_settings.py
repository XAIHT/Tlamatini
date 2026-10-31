# Tlamatini Author Banner — Angela López Mendoza · @angelahack1
"""Account preferences for real editor/terminal actions; presentation stays local."""
from __future__ import annotations

import json
import math

from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods


# The API supplies this same schema to the dialog. No parallel browser defaults.
FIELDS = {
    "editor_wpm": dict(tab="editor", label="Typing speed (WPM)", default=100, min=40, max=250, step=1),
    "link_speeds": dict(tab="editor", label="Use the same typing speed for both", default=False),
    "segment_pause": dict(tab="editor", label="Pause after each segment (seconds)", default=0, min=0, max=3, step=.1),
    "teaching_detail": dict(tab="editor", label="Teaching detail", default="balanced", options={"brief": "Brief", "balanced": "Balanced", "detailed": "Detailed"}),
    "suggestions": dict(tab="editor", label="Offer suggestions for each new field", default=True),
    "suggestion_display": dict(tab="editor", label="Suggestion presentation", default="both", options={"both": "Ghost text and choices", "choices": "Choices only"}),
    "follow_typing": dict(tab="editor", label="Follow Tlamatini’s typing", default=True),
    "editor_font": dict(tab="editor", label="Editor font size (px)", default=13, min=12, max=24, step=1, local=True),
    "line_numbers": dict(tab="editor", label="Show line numbers", default=True, local=True),
    "wrap": dict(tab="editor", label="Wrap long lines", default=False, local=True),
    "terminal_wpm": dict(tab="terminal", label="Typing speed (WPM)", default=50, min=20, max=250, step=1),
    "shell": dict(tab="terminal", label="Default shell", default="powershell", options={"powershell": "PowerShell", "cmd": "CMD", "pwsh": "PowerShell 7"}),
    "execution": dict(tab="terminal", label="Command execution", default="task", options={"task": "Follow the task’s instructions", "manual": "I always press Enter"}),
    "advisor": dict(tab="terminal", label="Enable advisor in new terminals", default=True),
    "wait_seconds": dict(tab="terminal", label="Command wait window (seconds)", default=120, min=1, max=3600, step=1, advanced=True),
    "hang_seconds": dict(tab="terminal", label="No-output threshold (seconds)", default=45, min=3, max=3600, step=1, advanced=True),
    "user_wait_seconds": dict(tab="terminal", label="User handoff wait (seconds)", default=300, min=5, max=3600, step=1, advanced=True),
    "terminal_font": dict(tab="terminal", label="Terminal font size (px)", default=13, min=12, max=24, step=1, local=True),
    "cursor_style": dict(tab="terminal", label="Cursor style", default="block", options={"block": "Block", "bar": "Bar", "underline": "Underline"}, local=True),
    "cursor_blink": dict(tab="terminal", label="Blink terminal cursor", default=True, local=True),
    "terminal_layout": dict(tab="terminal", label="Preferred terminal layout", default="tabs", options={"tabs": "Tabs", "tile": "Tile", "tile-h": "Side by side", "tile-v": "Stacked", "grid": "Grid"}, local=True),
    "narrate_terminal": dict(tab="voice", label="Narrate every Terminater command", default=False),
    "narrate_editor": dict(tab="voice", label="Narrate each Live Editor teaching segment", default=False),
    "narration_content": dict(tab="voice", label="What to say", default="explanation", options={"explanation": "Brief explanation", "literal": "Command or code", "both": "Both"}),
    "narration_when": dict(tab="voice", label="When to speak", default="before", options={"before": "Before typing", "during": "While typing", "after": "After typing"}),
    "narration_wait": dict(tab="voice", label="Wait for narration before typing", default=True),
    "announce_outcomes": dict(tab="voice", label="Announce command outcomes", default="errors", options={"errors": "Errors and user-input requests", "all": "All results", "off": "Off"}),
}
DEFAULTS = {key: field["default"] for key, field in FIELDS.items()}
ACCOUNT_DEFAULTS = {key: value for key, value in DEFAULTS.items() if not FIELDS[key].get("local")}
DETAIL = {
    "brief": "Use one short explanation and one clear question for each field.",
    "balanced": "Explain what the field does, recommend a value, and ask the learner to choose.",
    "detailed": "Explain why the field matters, alternatives and one example, then ask the learner to choose. Keep edits small.",
}


def validate(values):
    if not isinstance(values, dict) or set(values) - set(ACCOUNT_DEFAULTS):
        raise ValueError("Unknown account preference. Reload the settings dialog.")
    clean = dict(ACCOUNT_DEFAULTS)
    for key, value in values.items():
        field, default = FIELDS[key], DEFAULTS[key]
        if isinstance(default, bool):
            valid = type(value) is bool
        elif isinstance(default, str):
            valid = isinstance(value, str) and value in field["options"]
        else:
            valid = type(value) in (int, float) and math.isfinite(value) and field["min"] <= value <= field["max"]
            if valid and field["step"] == 1:
                valid = int(value) == value
        if not valid:
            raise ValueError(f"Invalid {field['label'].lower()}.")
        clean[key] = value
    if clean["link_speeds"]:
        clean["terminal_wpm"] = clean["editor_wpm"]
    return clean


def snapshot(user_id):
    """No cache: each action sees the last committed account preferences."""
    from .models import InteractionSettings
    if not str(user_id or "").isdigit():
        return dict(ACCOUNT_DEFAULTS), 0
    row = InteractionSettings.objects.filter(user_id=int(user_id)).values("preferences", "revision").first()
    return (validate(row["preferences"]), row["revision"]) if row else (dict(ACCOUNT_DEFAULTS), 0)


@require_http_methods(["GET", "POST"])
def settings_view(request):
    from .models import InteractionSettings
    if request.method == "POST":
        if len(request.body) > 16_384:
            return JsonResponse({"error": "Settings request is too large."}, status=413)
        try:
            data = json.loads(request.body)
            clean = validate(data["preferences"])
            revision = data["revision"]
            if type(revision) is not int or revision < 0:
                raise ValueError("Invalid settings revision.")
        except (ValueError, TypeError, KeyError, UnicodeError):
            return JsonResponse({"error": "Invalid settings. Check the values and reload if necessary."}, status=400)
        with transaction.atomic():
            row, _ = InteractionSettings.objects.get_or_create(user=request.user)
            updated = InteractionSettings.objects.filter(pk=row.pk, revision=revision).update(preferences=clean, revision=revision + 1)
            if not updated:
                return JsonResponse({"error": "Settings changed in another tab. Reload them before saving."}, status=409)
    preferences, revision = snapshot(request.user.pk)
    from .terminal_hub import terminal_kinds
    return JsonResponse({"preferences": preferences, "revision": revision, "fields": FIELDS,
                         "defaults": DEFAULTS, "user": str(request.user.pk), "shells": terminal_kinds()})


def terminal_preferences(action, params, engine):
    """Called by the ONE hub before dispatch, including jobs and in-process flows."""
    preferences, revision = snapshot(params.get("user"))
    params = dict(params)
    inherit = engine._tx.parse_flag(params.get("use_my_defaults"), False, False)[0]
    if inherit and revision:
        for target, source in {"typing_wpm": "terminal_wpm", "kind": "shell", "advisor": "advisor",
                               "wait_seconds": "wait_seconds", "hang_seconds": "hang_seconds",
                               "user_wait_seconds": "user_wait_seconds"}.items():
            params[target] = preferences[source]
    # Omitted fields inherit even on an explicit flow; old saved fields remain explicit.
    for target, source in {"typing_wpm": "terminal_wpm", "kind": "shell", "advisor": "advisor",
                           "wait_seconds": "wait_seconds", "hang_seconds": "hang_seconds",
                           "user_wait_seconds": "user_wait_seconds"}.items():
        params.setdefault(target, preferences[source])
    if preferences["execution"] == "manual":
        if action in {"run", "type", "handover"}:
            text = engine.TerminalHub._text(params)
            if any(ord(c) < 32 for c in text):
                raise engine.TerminaterError("I always press Enter is on. Send one line without control characters; the user submits it.", "manual_enter")
            params["submit"] = False
        if action == "send_key":
            keys = engine._tx.parse_key_sequence(str(params.get("keys") or params.get("text") or ""))[0]
            if any("\r" in key or "\n" in key for key in keys):
                raise engine.TerminaterError("I always press Enter is on. Only the user may submit the command.", "manual_enter")
    params["_interaction"] = preferences
    return params


def chat_preferences(config, explicit, user_id):
    """Preserve a typed call's shell choice while applying the user's pacing.

    The template's literal defaults cannot distinguish an omitted model field.
    Resolve at the authenticated launcher, where the explicit fields are known.
    """
    preferences, revision = snapshot(user_id)
    if not revision:
        return config
    resolved = dict(config)
    for target, source in {'typing_wpm': 'terminal_wpm', 'advisor': 'advisor',
                           'wait_seconds': 'wait_seconds', 'hang_seconds': 'hang_seconds',
                           'user_wait_seconds': 'user_wait_seconds'}.items():
        resolved[target] = preferences[source]
    resolved['kind'] = explicit.get('kind') or preferences['shell']
    resolved['use_my_defaults'] = False
    return resolved


def spoken_text(text, explanation, preferences, *, secret=False, editor=False):
    """Never send secret text or handoff values to a browser speech queue."""
    if secret or "<<USER" in text:
        return "I’ll prepare this step. Enter the private value yourself when prompted."
    explanation = (explanation or ("I’ll write the next teaching segment." if editor else "I’ll prepare this command."))[:1000]
    content = preferences["narration_content"]
    return explanation if content == "explanation" else text[:4000] if content == "literal" else explanation + " " + text[:4000]
