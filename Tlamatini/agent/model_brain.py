# ═══════════════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""MODEL BRAIN - Tlamatini configures herself for EACH model, from formal sources.

Angela, 2026-10-08: "make it dynamic by model ... Tlamatini may use very different
models", "set the best parameters for models like GLM, Nemotron, DeepSeek, Gemma4 ...",
"based on formal documentation, not your stupid ideas", "a brain-model-configurator that
makes clever research for each model".

For the model that is about to be called, the brain decides four things:

1. SAMPLING - in this order, the first that exists wins:
   a. an explicit per-model override in config.json (``model_brain_overrides``);
   b. the vendor's own published values (``model_profiles.json``: generation_config.json,
      model card or API docs - every entry names its sources);
   c. values LEARNED automatically from the vendor's generation_config.json, found through
      the model's ollama.com page (``model_profiles.learned.json`` in
      ``%LOCALAPPDATA%\\Tlamatini\\model_brain``, outside the install folder);
   d. what Ollama publishes for the model (``/api/show`` "parameters");
   e. nothing at all - the model's own defaults.
2. REASONING CONTINUITY - a thinking model gets its own reasoning back inside the CURRENT
   tool loop.  Z.ai (GLM), OpenAI (gpt-oss, harmony guide), DeepSeek, Moonshot (Kimi) and
   Google (Gemma 4) all document this; each model's chat template decides how to render it,
   so nothing here is tied to one family.  Earlier user turns never carry reasoning:
   Tlamatini's chat history is plain text.
3. THINKING LEVEL - the model's own published default (``/api/show`` thinking.default)
   unless the user chose a level for that model; a level the model does not publish is
   refused, loudly, and the default is kept.
4. CONTEXT WINDOW - ``num_ctx`` is never set above the model's published context length.

Contracts - do NOT weaken:
* FAIL-OPEN.  A failed lookup or a broken file means "decide with what is known", never a
  broken chat; ``plan()`` never raises.  ``model_brain: "off"`` restores the exact
  pre-brain behaviour.
* NEVER BLOCKS A REQUEST ON THE INTERNET.  Research runs once per model, in a background
  thread; until it lands the model simply runs with what is already known.
* Stdlib only, and the only Tlamatini import is ``config_loader`` (also stdlib only).
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:  # the brain must load even where the package context is missing (tests, tools)
    from .config_loader import find_config_path
except Exception:  # noqa: BLE001
    def find_config_path():  # type: ignore[misc]
        return None

__all__ = [
    "BrainPlan",
    "ModelFacts",
    "SAMPLING_KEYS",
    "base_name",
    "describe",
    "match_profile",
    "plan",
    "research",
]

KB_FILENAME = "model_profiles.json"
LEARNED_FILENAME = "model_profiles.learned.json"

#: Ollama option names a profile may carry.
SAMPLING_KEYS = ("temperature", "top_p", "top_k", "min_p", "repeat_penalty",
                 "presence_penalty", "frequency_penalty")

_SHOW_TTL_SECONDS = 3600.0          # what a model can do changes rarely
_SHOW_FAIL_TTL_SECONDS = 60.0       # a failed lookup is retried soon, never hammered
_SHOW_TIMEOUT_SECONDS = 6.0
_RESEARCH_TIMEOUT_SECONDS = 12.0
_RESEARCH_RETRY_SECONDS = 7 * 24 * 3600.0
_USER_AGENT = "Tlamatini-ModelBrain/1.0 (+https://github.com/XAIHT/Tlamatini)"

_LOCK = threading.RLock()
_SHOW_CACHE: Dict[Tuple[str, str], Tuple[float, "ModelFacts"]] = {}
_FILE_CACHE: Dict[str, Tuple[float, Any]] = {}
_RESEARCH_STARTED: set = set()


def _say(message: str) -> None:
    try:
        print("--- [MODEL-BRAIN] " + message, flush=True)
    except Exception:  # noqa: BLE001 - diagnostics never break a call
        pass


# ── what the model is ────────────────────────────────────────────────────────
def base_name(model: Any) -> str:
    """``jcyhsiao/Qwen3.5cloud:latest`` -> ``qwen3.5cloud``: no namespace, no tag, lowercase."""
    name = str(model or "").strip().lower()
    name = name.rsplit("/", 1)[-1]
    return name.split(":", 1)[0]


@dataclass
class ModelFacts:
    """What Ollama itself publishes about a model (``/api/show``)."""

    model: str
    known: bool = False
    capabilities: List[str] = field(default_factory=list)
    thinking_values: List[Any] = field(default_factory=list)
    thinking_default: Any = None
    context_length: int = 0
    parameters: Dict[str, float] = field(default_factory=dict)

    @property
    def thinks(self) -> bool:
        return "thinking" in self.capabilities


def _parse_modelfile_parameters(text: Any) -> Dict[str, float]:
    """The numeric sampling lines of a Modelfile ``PARAMETER`` block."""
    found: Dict[str, float] = {}
    for line in str(text or "").splitlines():
        parts = line.split()
        if len(parts) != 2 or parts[0] not in SAMPLING_KEYS:
            continue
        try:
            found[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return found


def _facts_from_show(model: str, data: Dict[str, Any]) -> ModelFacts:
    facts = ModelFacts(model=model, known=True)
    facts.capabilities = [str(c) for c in (data.get("capabilities") or [])]
    thinking = data.get("thinking") or {}
    if isinstance(thinking, dict):
        facts.thinking_values = list(thinking.get("values") or [])
        facts.thinking_default = thinking.get("default")
    for key, value in (data.get("model_info") or {}).items():
        if str(key).endswith(".context_length"):
            try:
                facts.context_length = int(value)
            except (TypeError, ValueError):
                pass
    facts.parameters = _parse_modelfile_parameters(data.get("parameters"))
    return facts


def _fetch_show(model: str, base_url: str, headers: Optional[Dict[str, str]]) -> Dict[str, Any]:
    url = (base_url or "http://127.0.0.1:11434").rstrip("/") + "/api/show"
    request = urllib.request.Request(
        url, data=json.dumps({"model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(request, timeout=_SHOW_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def describe(model: str, base_url: str = "", headers: Optional[Dict[str, str]] = None) -> ModelFacts:
    """Ollama's own description of ``model`` (cached).  Never raises."""
    key = (str(base_url or ""), str(model or ""))
    now = time.time()
    with _LOCK:
        cached = _SHOW_CACHE.get(key)
        if cached and cached[0] > now:
            return cached[1]
    try:
        facts = _facts_from_show(model, _fetch_show(model, base_url, headers))
        ttl = _SHOW_TTL_SECONDS
    except Exception as exc:  # noqa: BLE001 - an unknown model is still a usable model
        _say("could not ask Ollama about %s (%s); deciding with what is known" % (model, exc))
        facts = ModelFacts(model=model)
        ttl = _SHOW_FAIL_TTL_SECONDS
    with _LOCK:
        _SHOW_CACHE[key] = (now + ttl, facts)
    return facts


# ── the knowledge ────────────────────────────────────────────────────────────
def _module_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _state_dir() -> str:
    """Where USER STATE lives: beside config.json (preserved by self-update)."""
    try:
        path = find_config_path()
        if path:
            return os.path.dirname(os.path.abspath(path))
    except Exception:  # noqa: BLE001
        pass
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return _module_dir()


def _kb_paths() -> List[str]:
    """A copy beside config.json (user-editable) wins over the one shipped with the code."""
    paths = []
    for folder in (_state_dir(), _module_dir()):
        candidate = os.path.join(folder, KB_FILENAME)
        if candidate not in paths:
            paths.append(candidate)
    return paths


def _read_json(path: str) -> Any:
    """Cached by modification time, so an edit is picked up without a restart."""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    with _LOCK:
        cached = _FILE_CACHE.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
    try:
        with open(path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except Exception as exc:  # noqa: BLE001
        _say("ignoring %s: %s" % (path, exc))
        data = None
    with _LOCK:
        _FILE_CACHE[path] = (mtime, data)
    return data


def _profiles_from(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    return [p for p in (data.get("profiles") or []) if isinstance(p, dict) and p.get("match")]


def knowledge_base() -> List[Dict[str, Any]]:
    for path in _kb_paths():
        profiles = _profiles_from(_read_json(path))
        if profiles:
            return profiles
    return []


def _learned_dir() -> str:
    """Per-user, OUTSIDE the install folder: survives every self-update and reinstall
    (the same home the External-MCP memory graph and the private runtimes use)."""
    override = os.environ.get("TLAMATINI_MODEL_BRAIN_DIR", "").strip()
    if override:
        return override
    base = os.environ.get("LOCALAPPDATA", "").strip()
    if base:
        return os.path.join(base, "Tlamatini", "model_brain")
    return os.path.join(os.path.expanduser("~"), ".tlamatini", "model_brain")


def _learned_path() -> str:
    return os.path.join(_learned_dir(), LEARNED_FILENAME)


def learned_profiles() -> List[Dict[str, Any]]:
    return _profiles_from(_read_json(_learned_path()))


def match_profile(model: Any) -> Optional[Dict[str, Any]]:
    """The first knowledge-base entry, then the first LEARNED entry, matching ``model``."""
    name = base_name(model)
    if not name:
        return None
    for source, profiles in (("formal", knowledge_base()), ("learned", learned_profiles())):
        for profile in profiles:
            if profile.get("unresolved"):
                continue
            try:
                if re.search(str(profile["match"]), name, re.IGNORECASE):
                    found = dict(profile)
                    found.setdefault("origin", source)
                    return found
            except re.error:
                continue
    return None


# ── the decision ─────────────────────────────────────────────────────────────
@dataclass
class BrainPlan:
    enabled: bool
    model: str
    sampling: Dict[str, Any] = field(default_factory=dict)
    sampling_origin: str = ""
    sources: List[str] = field(default_factory=list)
    think: Any = None
    think_note: str = ""
    keep_reasoning: bool = False
    num_ctx: Optional[int] = None
    facts: Optional[ModelFacts] = None
    profile_id: str = ""

    def summary(self) -> str:
        if not self.enabled:
            return "model=%s: OFF (model_brain=off) - the legacy fixed parameters are used" % self.model
        sampling = " ".join("%s=%s" % (k, v) for k, v in sorted(self.sampling.items())) or "none sent"
        return ("model=%s | sampling: %s [%s] | thinking: %s | reasoning returned inside the tool "
                "loop: %s | num_ctx=%s" % (
                    self.model, sampling, self.sampling_origin, self.think_note,
                    "yes" if self.keep_reasoning else "no", self.num_ctx))


def _override_for(config: Dict[str, Any], model: str) -> Dict[str, Any]:
    """``model_brain_overrides``: keys are a full model name, a base name, or ``re:<regex>``."""
    table = config.get("model_brain_overrides")
    if not isinstance(table, dict):
        return {}
    full, base = str(model or "").strip().lower(), base_name(model)
    merged: Dict[str, Any] = {}
    for key, value in table.items():
        if not isinstance(value, dict) or str(key).startswith("_"):
            continue
        key_text = str(key).strip()
        hit = False
        if key_text.lower() in (full, base):
            hit = True
        elif key_text.lower().startswith("re:"):
            try:
                hit = re.search(key_text[3:], base, re.IGNORECASE) is not None
            except re.error:
                hit = False
        if hit:
            merged.update(value)
    return merged


def _resolve_think(requested: Any, facts: ModelFacts) -> Tuple[Any, str]:
    default = facts.thinking_default
    if not facts.thinks:
        return None, "the model does not think"
    if requested is None or (isinstance(requested, str) and requested.strip().lower() in ("", "auto")):
        return None, "the model's own default (%s)" % default
    if isinstance(requested, str):
        requested = requested.strip().lower()
        if requested in ("true", "false"):
            requested = requested == "true"
    if facts.thinking_values and requested not in facts.thinking_values:
        _say("thinking level %r is not published by %s (it publishes %s) - keeping its default %r"
             % (requested, facts.model, facts.thinking_values, default))
        return None, "the model's own default (%s); requested %r is not published" % (default, requested)
    return requested, "%r (chosen in model_brain_overrides; the model's default is %s)" % (requested, default)


def _clamp_num_ctx(configured: Any, facts: ModelFacts) -> Optional[int]:
    try:
        value = int(configured) if configured not in (None, "") else None
    except (TypeError, ValueError):
        value = None
    if facts.context_length > 0:
        return min(value, facts.context_length) if value else facts.context_length
    return value


def _is_off(value: Any) -> bool:
    return str(value).strip().lower() in ("off", "false", "0", "no", "legacy")


def plan(model: str, base_url: str = "", config: Optional[Dict[str, Any]] = None,
         headers: Optional[Dict[str, str]] = None) -> BrainPlan:
    """Everything the brain decides for ``model``.  Never raises."""
    config = config if isinstance(config, dict) else {}
    try:
        if _is_off(config.get("model_brain", "auto")):
            return BrainPlan(enabled=False, model=model)
        facts = describe(model, base_url, headers)
        override = _override_for(config, model)
        think, think_note = _resolve_think(override.get("think"), facts)
        # A model whose published default is "no thinking" (Gemma 4) thinks only when asked.
        default_off = think is None and facts.thinking_default is False
        thinking_on = facts.thinks and think is not False and not default_off

        profile = match_profile(model)
        if profile is not None:
            sampling_src = profile.get("sampling_no_thinking") if (
                not thinking_on and isinstance(profile.get("sampling_no_thinking"), dict)) else profile.get("sampling")
            sampling = {k: v for k, v in (sampling_src or {}).items() if k in SAMPLING_KEYS}
            origin = "%s profile '%s'" % (profile.get("origin", "formal"), profile.get("id", "?"))
            sources = [str(s) for s in (profile.get("sources") or [])]
            profile_id = str(profile.get("id", ""))
        elif facts.parameters:
            sampling, origin, sources, profile_id = dict(facts.parameters), "published by Ollama for this model", [], ""
        else:
            sampling, origin, sources, profile_id = {}, "the model's own defaults (nothing published yet)", [], ""
            if not _is_off(config.get("model_brain_research", "on")):
                start_research(model)

        for key, value in override.items():
            if key in SAMPLING_KEYS:
                sampling[key] = value
                origin += " + model_brain_overrides"

        keep_reasoning = thinking_on and not _is_off(config.get("model_brain_keep_reasoning", "on"))
        result = BrainPlan(
            enabled=True, model=model, sampling=sampling, sampling_origin=origin, sources=sources,
            think=think, think_note=think_note, keep_reasoning=keep_reasoning,
            num_ctx=_clamp_num_ctx(config.get("ollama_num_ctx"), facts), facts=facts,
            profile_id=profile_id)
        _say(result.summary())
        if sources:
            _say("sources for %s: %s" % (model, " | ".join(sources)))
        return result
    except Exception as exc:  # noqa: BLE001 - the brain may never break a chat
        _say("could not plan %s (%s); the legacy fixed parameters are used" % (model, exc))
        return BrainPlan(enabled=False, model=model)


# ── research: learn an unknown model from its vendor ────────────────────────
def _http_get(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=_RESEARCH_TIMEOUT_SECONDS) as response:
        return response.read(2_000_000).decode("utf-8", "replace")


def _library_page(model: str) -> str:
    name = str(model or "").strip().split(":", 1)[0]
    return "https://ollama.com/" + (name if "/" in name else "library/" + name)


_HF_REPO = re.compile(r"https?://huggingface\.co/([A-Za-z0-9][\w.-]*/[\w.-]+)")
_HF_NOT_REPOS = ("datasets", "spaces", "papers", "blog", "docs", "collections", "models", "settings")


def _hf_repos(html: str) -> List[str]:
    repos: List[str] = []
    for repo in _HF_REPO.findall(html or ""):
        repo = repo.rstrip(".").split("#", 1)[0]
        if repo.split("/", 1)[0].lower() in _HF_NOT_REPOS or repo in repos:
            continue
        repos.append(repo)
    return repos[:4]


def _sampling_from_generation_config(data: Any) -> Dict[str, Any]:
    """The vendor's generation_config.json in Ollama's option names.  Only EXPLICIT values."""
    if not isinstance(data, dict):
        return {}
    mapping = {"temperature": "temperature", "top_p": "top_p", "top_k": "top_k", "min_p": "min_p",
               "repetition_penalty": "repeat_penalty", "presence_penalty": "presence_penalty"}
    found: Dict[str, Any] = {}
    for source_key, option in mapping.items():
        value = data.get(source_key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            found[option] = value
    if found and "repeat_penalty" not in found:
        found["repeat_penalty"] = 1.0       # transformers' default: no repetition penalty
    return found


def _save_learned(entry: Dict[str, Any]) -> None:
    path = _learned_path()
    with _LOCK:
        data = _read_json(path)
        if not isinstance(data, dict):
            data = {"_comment": ("Learned automatically by the Model Brain (agent/model_brain.py) from "
                                 "each vendor's generation_config.json, found through the model's "
                                 "ollama.com page. User state - edit or delete freely."),
                    "version": 1, "profiles": []}
        profiles = [p for p in data.get("profiles") or [] if p.get("id") != entry["id"]]
        profiles.append(entry)
        data["profiles"] = profiles
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp, path)
        _FILE_CACHE.pop(path, None)


def _already_researched(model: str) -> bool:
    base = base_name(model)
    for profile in learned_profiles():
        if profile.get("id") != "learned:" + base:
            continue
        if not profile.get("unresolved"):
            return True
        checked = profile.get("checked_at_epoch") or 0
        return (time.time() - float(checked)) < _RESEARCH_RETRY_SECONDS
    return False


def research(model: str) -> Optional[Dict[str, Any]]:
    """Find the vendor's generation_config.json for ``model`` and remember it.  Never raises."""
    base = base_name(model)
    page = _library_page(model)
    entry: Dict[str, Any] = {"id": "learned:" + base, "match": "^%s$" % re.escape(base),
                             "learned_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "checked_at_epoch": time.time(), "sources": [page]}
    try:
        for repo in _hf_repos(_http_get(page)):
            url = "https://huggingface.co/%s/raw/main/generation_config.json" % repo
            try:
                sampling = _sampling_from_generation_config(json.loads(_http_get(url)))
            except Exception:  # noqa: BLE001 - a repo without the file is not an error
                continue
            if sampling:
                entry.update({"sampling": sampling, "sources": [page, url],
                              "notes": "Learned from the vendor's generation_config.json."})
                _save_learned(entry)
                _say("learned %s from %s: %s" % (model, url, sampling))
                return entry
        entry.update({"unresolved": True, "notes": "No generation_config.json with sampling values found."})
        _save_learned(entry)
        _say("no published sampling found for %s (checked %s); it keeps its own defaults" % (model, page))
    except Exception as exc:  # noqa: BLE001
        _say("research for %s failed (%s); it keeps its own defaults" % (model, exc))
    return None


def start_research(model: str) -> bool:
    """Research ``model`` once, in the background.  True when a thread was started."""
    base = base_name(model)
    with _LOCK:
        if not base or base in _RESEARCH_STARTED:
            return False
        _RESEARCH_STARTED.add(base)
    try:
        if _already_researched(model):
            return False
        thread = threading.Thread(target=research, args=(model,), name="model-brain-research", daemon=True)
        thread.start()
        return True
    except Exception:  # noqa: BLE001
        return False


def forget(model: str) -> None:
    """Drop what Ollama said about ``model`` so the next ``describe`` asks again."""
    with _LOCK:
        for key in [k for k in _SHOW_CACHE if k[1] == str(model or "")]:
            _SHOW_CACHE.pop(key, None)


def reset_caches() -> None:
    """Tests and the Configure dialogs: forget what was looked up."""
    with _LOCK:
        _SHOW_CACHE.clear()
        _FILE_CACHE.clear()
        _RESEARCH_STARTED.clear()
