"""Stop sequences every Ollama model will accept.

Angela, 2026-10-03: a plain Multi-Turn prompt failed before any work was done
with ``too many stop sequences; maximum is 4 (status code: 400)``. Tlamatini's
chat LLM carried NINE stop sequences (``rag/factory.py``). Ollama's cloud
models (measured: ``glm-5.3:cloud`` and ``glm-5.2:cloud``) refuse any request
with more than four - 5 or 9 is an HTTP 400, 4 is accepted - so every call
made through that LLM (the chat-history summary, the question rewriter, the
one-shot answer) died at once.

THE RULE: no request ever carries more than ``STOP_LIMIT`` stop sequences, for
ANY model - local or cloud. It is not decided by the model's name, because a
local alias of a cloud model, a remote Ollama that proxies to the cloud, or a
new cloud naming scheme would slip past a name check and fail again. Four is
also the limit of the OpenAI-style APIs that cloud models are served behind.

Callers list the sequences that matter MOST first; the rest are dropped. A
local model loses nothing that matters: it always stops at its own
end-of-generation token (``<|im_end|>``, ``<|eot_id|>``, ...) natively.

Stdlib-only and imports nothing from ``agent.*``; it never raises.
"""

from __future__ import annotations

from urllib.parse import urlparse

STOP_LIMIT = 4
CLOUD_STOP_LIMIT = STOP_LIMIT  # the name the first version of this fix used


def is_cloud_model(model, base_url=None) -> bool:
    """True for an Ollama CLOUD model (used for log messages only).

    Ollama names them ``<name>:cloud`` or ``<name>:<size>-cloud``
    (``glm-5.3:cloud``, ``gpt-oss:120b-cloud``). A base URL on ``ollama.com``
    means every model it serves is a cloud model.
    """
    try:
        name = str(model or "").strip().lower()
        if name.endswith(":cloud") or name.endswith("-cloud"):
            return True
        host = (urlparse(str(base_url or "")).hostname or "").lower()
        return host == "ollama.com" or host.endswith(".ollama.com")
    except Exception:
        return False


def fit_stop_sequences(stops, model=None, base_url=None, limit=STOP_LIMIT):
    """The stop sequences to send: duplicates and empty entries dropped, and
    never more than ``limit`` (the first ones, in the caller's order).

    ``model`` and ``base_url`` are accepted for the callers' log messages; the
    cap applies to every model.
    """
    try:
        cap = max(0, min(int(limit), STOP_LIMIT))
    except Exception:
        cap = STOP_LIMIT
    cleaned = []
    try:
        for stop in stops or []:
            if isinstance(stop, str) and stop and stop not in cleaned:
                cleaned.append(stop)
    except Exception:
        cleaned = []
    return cleaned[:cap]
