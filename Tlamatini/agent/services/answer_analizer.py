"""
answer_analizer.py — LLM-based success/failure classifier for multi-turn answers.

Instead of fragile regex or keyword matching, this module sends the
complete LLM answer to the same chained-model and asks it to judge
whether the answer indicates a successful outcome or a failure.

Usage (async):
    from agent.services.answer_analizer import analyze_answer_success
    is_success = await analyze_answer_success(llm_response_text)
"""

import logging
from asgiref.sync import sync_to_async
from langchain_core.prompts import ChatPromptTemplate

logger = logging.getLogger(__name__)

# ── Classification prompt ────────────────────────────────────────────
# The prompt is intentionally narrow: one job, one word output.
_SYSTEM_PROMPT = (
    "You are a strict binary classifier. Your ONLY job is to decide "
    "whether an AI assistant's answer indicates that the requested task "
    "was completed successfully or that it failed / could not be done.\n\n"
    "Rules:\n"
    "- If the answer shows the task was accomplished, results were "
    "delivered, information was provided, or the objective was met "
    "in any form, respond with exactly: SUCCESS\n"
    "- If the answer shows the task failed, encountered errors it could "
    "not recover from, was refused, or the assistant could not fulfill "
    "the request, respond with exactly: FAILURE\n"
    "- Partial results that still provide useful output count as SUCCESS.\n"
    "- A polite refusal or an apology for not being able to help counts "
    "as FAILURE.\n"
    "- Respond with ONLY one word: SUCCESS or FAILURE. "
    "No explanation, no punctuation, no extra text."
)

_HUMAN_TEMPLATE = (
    "Classify the following AI assistant answer as SUCCESS or FAILURE:\n\n"
    "--- BEGIN ANSWER ---\n"
    "{answer}\n"
    "--- END ANSWER ---"
)

_PROMPT = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM_PROMPT),
    ("human", _HUMAN_TEMPLATE),
])

# Maximum characters of the answer to send for classification.
# Keeps token usage bounded for very long responses.
_MAX_ANSWER_LENGTH = 4000


def _build_llm():
    """Create a lightweight OllamaLLM using the chained-model from config.json."""
    from agent.config_loader import load_config

    try:
        from langchain_ollama import OllamaLLM
    except ImportError:
        from langchain_community.llms import Ollama as OllamaLLM

    config = load_config()
    token = config.get("ollama_token")
    client_kwargs = (
        {"headers": {"Authorization": f"Bearer {token}"}} if token else {}
    )

    return OllamaLLM(
        model=config.get("chained-model"),
        base_url=config.get("ollama_base_url"),
        streaming=False,
        temperature=0.0,
        client_kwargs=client_kwargs,
    )


def _classify_sync(answer_text: str) -> bool:
    """Synchronous classification — returns True for SUCCESS, False for FAILURE."""
    if not answer_text or not answer_text.strip():
        return False

    truncated = answer_text[:_MAX_ANSWER_LENGTH]

    try:
        llm = _build_llm()
        chain = _PROMPT | llm
        raw = chain.invoke({"answer": truncated})
        verdict = (
            getattr(raw, "content", str(raw))
            .strip()
            .upper()
            .rstrip(".")
        )
        logger.info("[AnswerAnalizer] LLM verdict: %s", verdict)
        return verdict == "SUCCESS"
    except Exception as exc:
        logger.error(
            "[AnswerAnalizer] Classification failed (%s), defaulting to True",
            exc,
        )
        # On error, default to showing the button — safer UX than hiding it.
        return True


async def analyze_answer_success(answer_text: str) -> bool:
    """Async entry-point: classify the LLM answer as success or failure.

    Returns ``True`` when the answer indicates the task succeeded,
    ``False`` otherwise.  On any internal error the function defaults
    to ``True`` so the Create-Flow button is not hidden unnecessarily.
    """
    return await sync_to_async(_classify_sync, thread_sensitive=False)(answer_text)
