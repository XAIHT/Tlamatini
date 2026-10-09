# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""HTTP surface of the MODEL BRAIN's Auto-tuning dialog (Config -> Models -> Save).

GET  /agent/model_brain/models/  the configured Ollama models, who uses each one, and
                                 whether the brain applies to it directly.
POST /agent/model_brain/tune/    {"model": "..."} - tune ONE model for real: ask Ollama,
                                 match the vendor's formal profile, research an unknown
                                 model, and return every step with its result.

Nothing here invents a value: every number shown comes from Ollama's /api/show, the
knowledge base (with its sources) or a vendor's generation_config.json.
"""
from __future__ import annotations

import json

from django.http import JsonResponse

from . import model_brain
from .agents.model_settings import FIELDS as MODEL_FIELDS
from .config_loader import load_config

#: The settings whose model the brain configures directly (the chat / Multi-Turn brain).
BRAIN_KEYS = ("unified_agent_model", "chained-model")


def _token_headers(config) -> dict:
    token = str(config.get("ollama_token") or "").strip()
    if not token or (token.startswith("<") and token.endswith(">")):
        return {}
    return {"Authorization": "Bearer " + token}


def _base_url(config) -> str:
    return str(config.get("unified_agent_base_url") or config.get("ollama_base_url")
               or "http://127.0.0.1:11434").rstrip("/")


def configured_models(config) -> list:
    """Distinct Ollama models in config.json, brain models first, with their users."""
    rows: dict = {}
    for field in MODEL_FIELDS:
        if field.get("kind") != "ollama":
            continue
        value = str(config.get(field["key"]) or field.get("default") or "").strip()
        if not value or value.startswith("@"):
            continue
        row = rows.setdefault(value, {"model": value, "used_by": [], "applied": False})
        row["used_by"].append(field.get("label") or field["key"])
        if field["key"] in BRAIN_KEYS:
            row["applied"] = True
    return sorted(rows.values(), key=lambda r: (not r["applied"], r["model"].lower()))


def model_brain_models_view(request):
    config = load_config(force_reload=True)
    return JsonResponse({
        "success": True,
        "enabled": not model_brain._is_off(config.get("model_brain", "auto")),
        "models": configured_models(config),
    })


def _facts_dict(facts) -> dict:
    return {
        "known": bool(facts and facts.known),
        "capabilities": list(facts.capabilities) if facts else [],
        "thinking_values": list(facts.thinking_values) if facts else [],
        "thinking_default": facts.thinking_default if facts else None,
        "context_length": int(facts.context_length) if facts else 0,
    }


def model_brain_tune_view(request):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "invalid JSON"}, status=400)
    model = str((payload or {}).get("model") or "").strip()
    config = load_config(force_reload=True)
    known_models = {row["model"] for row in configured_models(config)}
    if model not in known_models:
        return JsonResponse({"success": False, "error": "not a configured model: %s" % model}, status=400)

    steps = []
    base_url, headers = _base_url(config), _token_headers(config)

    # 1. What the model is - fresh from Ollama.
    model_brain.forget(model)
    facts = model_brain.describe(model, base_url, headers)
    steps.append({"step": "ollama", "ok": facts.known,
                  "detail": ("capabilities: %s | thinking levels: %s (default %s) | context %s tokens" % (
                      ", ".join(facts.capabilities) or "-", facts.thinking_values or "-",
                      facts.thinking_default, facts.context_length or "?"))
                  if facts.known else "Ollama did not describe this model"})

    if facts.known and "completion" not in facts.capabilities:
        steps.append({"step": "skip", "ok": True,
                      "detail": "not a text-generation model (%s) - nothing to tune" % ", ".join(facts.capabilities)})
        return JsonResponse({"success": True, "model": model, "tunable": False, "steps": steps,
                             "facts": _facts_dict(facts)})

    # 2. The vendor's formal profile - or research it now.
    profile = model_brain.match_profile(model)
    if profile is None and not model_brain._is_off(config.get("model_brain_research", "on")):
        steps.append({"step": "research", "ok": True,
                      "detail": "no formal profile yet - researching the vendor's generation_config.json"})
        model_brain.research(model)
        profile = model_brain.match_profile(model)
    if profile is not None:
        steps.append({"step": "profile", "ok": True,
                      "detail": "%s profile '%s'%s" % (profile.get("origin", "formal"), profile.get("id"),
                                                       (" - " + profile.get("vendor")) if profile.get("vendor") else "")})
    else:
        steps.append({"step": "profile", "ok": False,
                      "detail": "no published sampling found - the model keeps its own defaults"})

    # 3. The plan the brain will really use.
    plan = model_brain.plan(model, base_url, config, headers)
    return JsonResponse({
        "success": True, "model": model, "tunable": True, "enabled": plan.enabled,
        "steps": steps, "facts": _facts_dict(plan.facts or facts),
        "sampling": plan.sampling, "sampling_origin": plan.sampling_origin,
        "sources": plan.sources, "notes": (profile or {}).get("notes", ""),
        "think_note": plan.think_note, "keep_reasoning": plan.keep_reasoning,
        "num_ctx": plan.num_ctx, "summary": plan.summary(),
    })
