# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer design consultation — asking Tlamatini's own model for an art direction.

WHAT ANGELA ASKED FOR
---------------------
    *"may be you must provide it with an ollama connection inside it to make
    calls to the default model of Tlamatini (according to her configuration),
    in order to ask the LLM that based in the content, with colors the LLM use
    for each part of the document to be created"*

So PDFer can consult a model about art direction: which nuance this content
really is, which colours to use *per part* (title, headings, rules, table
headers, callouts, footer), which type pairing, and how much ornament.

WHY IT IS **OFF BY DEFAULT**, AND WHY THAT IS THE RIGHT DEFAULT
----------------------------------------------------------------
The deterministic path already produces a complete, contrast-validated,
audited design for every document (`pdfer_nuance` → `pdfer_theme`). The model
is an *upgrade*, not a dependency. Making it mandatory would mean:

* a network round-trip on every single PDF, including the ones a flow renders
  unattended at 03:00,
* a different-looking document every run, since a model is not deterministic —
  and a report that changes appearance between renders is one nobody trusts,
* a hard failure mode where Ollama being down means no document at all.

With it off, PDFer is fast, deterministic and offline. With
``ollama_design: true`` it gains taste. That is the correct shape for an
optional intelligence: **the floor is competent, the ceiling is higher.**

THE HARD PART IS NOT THE CALL — IT IS THE DISTRUST
---------------------------------------------------
A model asked for JSON will, eventually: wrap it in prose, wrap it in a
```json fence, invent a colour name, return ``"navy blue-ish"``, emit eight
keys instead of seven, hallucinate a font that is not installed, propose white
text on a white page, or return a nuance that is not in the catalog.

So **every field is validated against reality before it is allowed to touch a
document**:

* colours through `pdfer_color.parse_color`, which fails open to the theme's
  own value rather than raising;
* the nuance through `pdfer_nuance.normalise_nuance`, so an unknown one is
  dropped rather than guessed at;
* the font pairing against **`FontBook.available_pairings()`** — the pairings
  that actually resolve *on this machine*, not the ones the catalog lists;
* the decoration level against the content-safety budget, which the model
  **cannot raise** (a model that decides a contract should have a gradient
  cover does not get to);
* and finally the assembled palette through `Palette.validated()`, exactly
  like any other palette. A model's colour scheme has no privileges.

The result is that the worst a bad model response can do is be *ignored*.

CONTRACTS (do NOT weaken)
-------------------------
1. **NEVER RAISES, NEVER BLOCKS A RENDER.** Timeout, refusal, garbage,
   unreachable host — all return ``None`` and the deterministic design stands.
2. **THE SAFETY BUDGET IS NOT NEGOTIABLE BY THE MODEL.** It may lower
   ornament; it may never raise it.
3. **CONTRAST IS RE-VALIDATED AFTER MERGING.** No exceptions, no "the model
   said so".
4. **Stdlib only** (``urllib``) — the Talker / Whisperer / Reviewer pattern.
   No SDK, no ``agent.*`` import.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import json
import re

import pdfer_color as pc
import pdfer_nuance as pn

__all__ = ["consult_design", "build_prompt", "parse_response",
           "DESIGN_SCHEMA_HINT"]


#: The per-part colour roles the model is invited to choose. Deliberately a
#: SHORT list: a model asked for 38 roles produces 38 mediocre ones, while a
#: model asked for 8 produces 8 considered ones and the palette derivation
#: fills in the rest coherently.
_MODEL_ROLES = ("background", "text", "primary", "secondary", "accent",
                "heading", "table_header_bg", "footer")

DESIGN_SCHEMA_HINT = """{
  "nuance": "<one of the catalog names>",
  "reasoning": "<one short sentence>",
  "dark": true,
  "palette": {
    "background": "#RRGGBB",
    "text": "#RRGGBB",
    "primary": "#RRGGBB",
    "secondary": "#RRGGBB",
    "accent": "#RRGGBB",
    "heading": "#RRGGBB",
    "table_header_bg": "#RRGGBB",
    "footer": "#RRGGBB"
  },
  "gradient": {"from": "#RRGGBB", "to": "#RRGGBB"},
  "font_pairing": "<one of the offered pairings>",
  "decoration": "none|restrained|moderate|rich"
}"""


def build_prompt(excerpt, verdict, pairings, nuances=None, language="en"):
    """The consultation prompt.

    Three things make it produce usable answers instead of an essay:

    1. **The catalog is enumerated.** A model asked to "pick a style" invents
       one; a model given twenty named options picks one of them.
    2. **The deterministic verdict is disclosed** as a starting point, so the
       model is *revising* a proposal rather than starting cold — and its
       disagreements become informative.
    3. **The offered pairings are the ones this machine can actually set.**
       Asking for a font that is not installed wastes the round-trip.
    """
    catalog = nuances or list(pn.NUANCES)
    lines = []
    for key in catalog:
        spec = pn.NUANCES.get(key, {})
        lines.append("  - %s: %s" % (key, spec.get("summary", "")))

    return (
        "You are the art director for a document typesetting system. Choose "
        "the visual treatment for the document below.\n\n"
        "AVAILABLE STYLES (pick exactly one 'nuance'):\n"
        + "\n".join(lines) + "\n\n"
        "AVAILABLE FONT PAIRINGS (pick exactly one, these are installed):\n  "
        + ", ".join(pairings) + "\n\n"
        "OUR AUTOMATIC ANALYSIS SAYS:\n"
        "  nuance=%s (confidence %.0f%%), language=%s, "
        "%d words, %d headings, %d tables, %d code blocks.\n"
        "  Its decoration safety ceiling is '%s' — you may choose LESS "
        "ornament than this, never more.\n\n"
        % (verdict.nuance, verdict.confidence * 100, language,
           verdict.metrics.get("words", 0), verdict.metrics.get("headings", 0),
           verdict.metrics.get("tables", 0),
           verdict.metrics.get("code_blocks", 0), verdict.decoration_budget)
        + "RULES:\n"
        "  1. Reply with ONE JSON object and NOTHING else. No prose, no "
        "markdown fence, no explanation outside the JSON.\n"
        "  2. Every colour MUST be a 6-digit hex string like \"#1A2B3C\".\n"
        "  3. 'text' must be clearly readable on 'background' — dark text on "
        "a light background, or light text on a dark one.\n"
        "  4. Choose colours that suit THIS content's subject and register, "
        "not a generic corporate scheme.\n"
        "  5. If the content is a contract, a clinical document or a "
        "financial statement, choose decoration \"none\".\n\n"
        "SHAPE:\n" + DESIGN_SCHEMA_HINT + "\n\n"
        "DOCUMENT EXCERPT:\n" + (excerpt or "")[:6000] + "\n")


def _extract_json(text):
    """Find the JSON object in a model reply. Tolerant by necessity.

    Handles: a bare object; a ```json fence; prose before and/or after; and
    the very common "here is your JSON:" preamble. Returns a dict or None.
    """
    if not text:
        return None
    body = text.strip()

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", body, re.DOTALL)
    if fence:
        body = fence.group(1)
    else:
        start = body.find("{")
        end = body.rfind("}")
        if start < 0 or end <= start:
            return None
        body = body[start:end + 1]

    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    # One salvage pass: models love a trailing comma.
    try:
        return json.loads(re.sub(r",\s*([}\]])", r"\1", body))
    except Exception:
        return None


def parse_response(text, verdict, pairings, logger=None):
    """Validate a model reply into a config-shaped override dict.

    Returns ``(overrides, report)``. *overrides* uses the SAME key names the
    config file uses (``predominant_color``, ``accent_color``, ``nuance``…),
    so the result flows into `pdfer_theme.build_design_system` through the
    ordinary path — the model gets no private channel into the renderer.
    """
    report = {"accepted": [], "rejected": [], "raw_keys": []}
    data = _extract_json(text)
    if not data:
        report["rejected"].append("no JSON object found in the reply")
        return {}, report
    report["raw_keys"] = sorted(str(k) for k in data)

    overrides = {}

    # ── nuance ──────────────────────────────────────────────────────────
    proposed = pn.normalise_nuance(str(data.get("nuance", "")))
    if proposed:
        overrides["nuance"] = proposed
        report["accepted"].append("nuance=%s" % proposed)
    elif data.get("nuance"):
        report["rejected"].append(
            "nuance %r is not in the catalog" % str(data.get("nuance"))[:40])

    # ── dark / light ────────────────────────────────────────────────────
    if isinstance(data.get("dark"), bool):
        overrides["background_mode"] = "dark" if data["dark"] else "light"
        report["accepted"].append("background_mode=%s"
                                  % overrides["background_mode"])

    # ── palette, role by role ───────────────────────────────────────────
    palette = data.get("palette")
    if isinstance(palette, dict):
        mapping = {
            "primary": "predominant_color",
            "accent": "accent_color",
            "text": "text_color",
            "background": "background_color",
            "heading": "heading_color",
            "table_header_bg": "table_header_color",
        }
        for role, config_key in mapping.items():
            raw = palette.get(role)
            if not raw:
                continue
            text_value = str(raw).strip()
            # parse_color fails open, so compare against a sentinel to learn
            # whether it actually understood the value.
            probe_a = pc.parse_color(text_value, "#010203")
            probe_b = pc.parse_color(text_value, "#040506")
            if probe_a.hex != probe_b.hex:
                report["rejected"].append("%s=%r is not a colour"
                                          % (role, text_value[:24]))
                continue
            overrides[config_key] = probe_a.hex
            report["accepted"].append("%s=%s" % (config_key, probe_a.hex))

    # A background the model chose must agree with the dark/light flag it
    # chose, or the two fight and the palette derivation gets a contradiction.
    if "background_color" in overrides:
        ground = pc.parse_color(overrides["background_color"])
        implied = "dark" if ground.is_dark else "light"
        if overrides.get("background_mode") not in (None, implied):
            report["rejected"].append(
                "dark=%s contradicts background %s — trusting the background"
                % (data.get("dark"), overrides["background_color"]))
        overrides["background_mode"] = implied

    # ── font pairing, against what this machine HAS ─────────────────────
    pairing = str(data.get("font_pairing", "")).strip().lower()
    if pairing:
        if pairing in pairings:
            overrides["font_pairing"] = pairing
            report["accepted"].append("font_pairing=%s" % pairing)
        else:
            report["rejected"].append(
                "font_pairing %r is not available here (offered: %s)"
                % (pairing[:24], ", ".join(sorted(pairings)[:6])))

    # ── decoration: the model may LOWER it, never raise it ──────────────
    decoration = str(data.get("decoration", "")).strip().lower()
    if decoration in pn.DECORATION_LEVELS:
        ceiling = verdict.decoration_budget
        chosen = min(decoration, ceiling,
                     key=lambda level: pn.DECORATION_LEVELS.index(level))
        overrides["decorations"] = chosen
        if chosen != decoration:
            report["rejected"].append(
                "decoration=%s exceeds the content safety ceiling %s — "
                "capped" % (decoration, ceiling))
        else:
            report["accepted"].append("decorations=%s" % chosen)
    elif decoration:
        report["rejected"].append("decoration %r is not a level" % decoration[:20])

    if logger:
        try:
            logger("🎨 design consultation: accepted %s%s"
                   % (", ".join(report["accepted"]) or "nothing",
                      ("; rejected " + "; ".join(report["rejected"]))
                      if report["rejected"] else ""))
        except Exception:
            pass
    return overrides, report


def consult_design(excerpt, verdict, font_book, config, logger=None):
    """Ask the configured Ollama model for an art direction. NEVER raises.

    Returns ``(overrides, report)``; ``({}, report)`` on any failure at all,
    which leaves the deterministic design in place. The report is surfaced in
    the agent log so a consultation that was ignored is *visible* rather than
    mysterious.
    """
    import urllib.error
    import urllib.request

    report = {"attempted": True, "ok": False, "error": "", "accepted": [],
              "rejected": [], "model": "", "elapsed": 0.0}
    try:
        base = str(config.get("ollama_url") or "").strip().rstrip("/")
        model = str(config.get("ollama_model") or "").strip()
        token = str(config.get("ollama_token") or "").strip()
        timeout = float(config.get("ollama_timeout") or 120)
        if not base or not model:
            report["error"] = ("no ollama_url/ollama_model configured — "
                               "keeping the deterministic design")
            return {}, report
        report["model"] = model

        pairings = font_book.available_pairings() or ["neutral"]
        prompt = build_prompt(excerpt, verdict, pairings,
                              language=verdict.language)

        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "stream": False,
            # Low temperature: this is a classification-and-selection task,
            # not a creative writing one. A hot model invents font names.
            "options": {"temperature": 0.25, "top_p": 0.9},
            "format": "json",
        }).encode("utf-8")
        request = urllib.request.Request(
            base + "/api/generate", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        if token:
            request.add_header("Authorization", "Bearer %s" % token)

        import time
        started = time.time()
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
        report["elapsed"] = round(time.time() - started, 2)

        answer = (json.loads(body).get("response") or "").strip()
        if not answer:
            report["error"] = "the model returned an empty response"
            return {}, report

        overrides, parsed = parse_response(answer, verdict, pairings, logger)
        report.update(parsed)
        report["ok"] = bool(overrides)
        if not overrides:
            report["error"] = ("nothing in the reply survived validation — "
                               "keeping the deterministic design")
        return overrides, report

    except urllib.error.URLError as exc:
        report["error"] = "Ollama unreachable (%s)" % exc
    except Exception as exc:
        report["error"] = "%s: %s" % (type(exc).__name__, exc)
    if logger:
        try:
            logger("⚠️ design consultation failed (%s) — the deterministic "
                   "design stands, and the document is unaffected"
                   % report["error"])
        except Exception:
            pass
    return {}, report
