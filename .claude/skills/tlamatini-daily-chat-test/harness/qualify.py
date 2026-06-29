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
Answer qualification for the Tlamatini daily chat test.

Two stages, exactly as the user pinned ("Heuristic + LLM judge on failures"):

  1. heuristic_qualify(question, answer, completed) -> verdict dict
        Deterministic, free, runs on ALL 1000 answers. Produces one of:
            PASS  -- received, clean, long enough, expectations met
            WEAK  -- received but thin / missing expected keywords
            FAIL  -- empty, errored, or timed out (never completed)

  2. llm_judge(question, answer)  -> {"verdict": "pass"|"fail", "score": 1-5,
                                      "reason": "..."}
        Optional. Runs ONLY on the WEAK/FAIL answers from stage 1, to arbitrate.
        Uses the Anthropic SDK. The API key is resolved from (first hit wins):
            env ANTHROPIC_API_KEY
            Tlamatini/agent/config.json  ["ANTHROPIC_API_KEY"]
            data.keys                    (KEY=VALUE lines)
        If no key / SDK / network, it degrades to {"verdict":"skip"} so the run
        never breaks because of the judge.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

# Strong "this is an error, not an answer" signals (conservative on purpose:
# a normal answer may *mention* the word "error", so we only trip on these).
_ERROR_PATTERNS = [
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(r"Internal Server Error"),
    re.compile(r"\bfailed with return code\b", re.I),
    re.compile(r"^\s*Error:\s", re.I),
    re.compile(r"An (unexpected )?error occurred while processing", re.I),
    re.compile(r"\bPERMISSION_DENIED\b"),
    re.compile(r"WebSocket connection .* failed", re.I),
]


def heuristic_qualify(question: Dict[str, Any], answer: str, completed: bool) -> Dict[str, Any]:
    """Deterministic first-pass verdict. Never raises."""
    text = (answer or "").strip()
    reasons: List[str] = []

    if not completed:
        return {"status": "FAIL", "reasons": ["did-not-complete/timeout"], "chars": len(text)}

    if not text:
        return {"status": "FAIL", "reasons": ["empty-answer"], "chars": 0}

    for pat in _ERROR_PATTERNS:
        if pat.search(text):
            reasons.append(f"error-signal:{pat.pattern[:40]}")
            return {"status": "FAIL", "reasons": reasons, "chars": len(text)}

    min_len = int(question.get("min_len", 40))
    if len(text) < min_len:
        reasons.append(f"too-short(<{min_len})")

    expect = question.get("expect") or []
    if expect:
        low = text.lower()
        if not any(kw.lower() in low for kw in expect):
            reasons.append("missing-expected-keywords")

    if reasons:
        return {"status": "WEAK", "reasons": reasons, "chars": len(text)}
    return {"status": "PASS", "reasons": [], "chars": len(text)}


# --- LLM judge ------------------------------------------------------------
def _load_api_key() -> Optional[str]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and key.strip() and "PLACEHOLDER" not in key.upper():
        return key.strip()

    # Tlamatini/agent/config.json (relative to repo; resolve a few candidates)
    here = os.path.dirname(os.path.abspath(__file__))
    repo_guess = os.environ.get("TLAMATINI_REPO", r"C:\Development\Tlamatini")
    candidates = [
        os.path.join(repo_guess, "Tlamatini", "agent", "config.json"),
        os.path.join(here, "..", "..", "..", "..", "Tlamatini", "agent", "config.json"),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            v = str(cfg.get("ANTHROPIC_API_KEY", "")).strip()
            if v and "PLACEHOLDER" not in v.upper() and v.lower().startswith("sk-"):
                return v
        except Exception:
            continue

    # data.keys vault
    for path in (os.path.join(repo_guess, "data.keys"),
                 os.path.join(here, "..", "..", "..", "..", "data.keys")):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip().startswith("ANTHROPIC_API_KEY"):
                        _, _, val = line.partition("=")
                        val = val.strip().strip('"').strip("'")
                        if val.lower().startswith("sk-"):
                            return val
        except Exception:
            continue
    return None


class LLMJudge:
    """Lazy Anthropic-backed judge. Safe no-op when unavailable."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or os.environ.get("ANTHROPIC_JUDGE_MODEL", "claude-haiku-4-5-20251001")
        self._client = None
        self._tried = False
        self.available = False
        self.reason_unavailable = ""

    def _ensure(self):
        if self._tried:
            return
        self._tried = True
        try:
            import anthropic  # noqa
        except Exception as e:  # pragma: no cover
            self.reason_unavailable = f"anthropic SDK import failed: {e}"
            return
        key = _load_api_key()
        if not key:
            self.reason_unavailable = "no ANTHROPIC_API_KEY found (env/config.json/data.keys)"
            return
        try:
            import anthropic
            self._client = anthropic.Anthropic(api_key=key)
            self.available = True
        except Exception as e:  # pragma: no cover
            self.reason_unavailable = f"client init failed: {e}"

    def judge(self, question: str, answer: str) -> Dict[str, Any]:
        self._ensure()
        if not self.available:
            return {"verdict": "skip", "score": None, "reason": self.reason_unavailable}

        ans = (answer or "")[:4000]
        prompt = (
            "You are grading whether an AI assistant (named Tlamatini) gave an "
            "acceptable answer to a user's chat message. Be lenient: an answer is "
            "PASS if it is a relevant, coherent, on-topic response that a reasonable "
            "user would accept -- even if brief. It is FAIL only if it is empty, "
            "an error/stack trace, off-topic, refuses without reason, or clearly "
            "non-responsive.\n\n"
            f"USER MESSAGE:\n{question}\n\n"
            f"ASSISTANT ANSWER:\n{ans}\n\n"
            "Reply with ONLY a JSON object: "
            '{\"verdict\": \"pass\" or \"fail\", \"score\": 1-5, \"reason\": \"<=20 words\"}'
        )
        try:
            resp = self._client.messages.create(
                model=self.model,
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                block.text for block in resp.content if getattr(block, "type", "") == "text"
            ).strip()
            m = re.search(r"\{.*\}", raw, re.S)
            data = json.loads(m.group(0)) if m else {}
            verdict = str(data.get("verdict", "")).lower()
            if verdict not in ("pass", "fail"):
                verdict = "fail"
            return {
                "verdict": verdict,
                "score": data.get("score"),
                "reason": str(data.get("reason", ""))[:200],
            }
        except Exception as e:
            return {"verdict": "skip", "score": None, "reason": f"judge-error: {e}"}
