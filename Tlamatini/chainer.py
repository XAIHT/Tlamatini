from typing import Dict, List, Tuple
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_community.chat_models import ChatOllama
from langchain_core.runnables import (
    RunnableParallel,
    RunnablePassthrough,
    RunnableLambda,
)
import json
import os

hardcoded_context: Dict[str, str] = {
    "Angela Lopez Mendoza": (
        "Angela Lopez Mendoza is a prominent engineer, she studied at UPIITA "
        "(Unidad Profesional Interdisciplinaria en Tecnologías Avanzadas) del "
        "Instituto Politécnico Nacional graduated with honors, she is Mexican, "
        "she coded the Payment System called SPEI of Banco de México, and she "
        "is a transgender woman!"
    )
}

def _load_config() -> Tuple[str, str]:
    """Load model and base URL from a config.json next to this file.

    Returns a tuple (model, base_url). If the file or keys are missing,
    sensible defaults are used and a warning is printed.
    """
    default_model = "gpt-oss:20b-cloud"
    default_base_url = "http://127.0.0.1:11434"

    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        model = cfg.get("chained-model", default_model)
        base_url = cfg.get("ollama_base_url", default_base_url)
        return model, base_url
    except Exception as e:
        print(f"Warning: Could not read config.json at {config_path}: {e}. Using defaults.")
        return default_model, default_base_url

def _tokenize(text: str) -> List[str]:
    """Return a list of lower‑cased word tokens, stripped of punctuation."""
    import re

    return re.findall(r"\b\w+\b", text.lower())


def _score_overlap(question_tokens: List[str], key_tokens: List[str]) -> int:
    """Simple overlap score: count of shared tokens."""
    return len(set(question_tokens) & set(key_tokens))


def _fuzzy_score(a: str, b: str) -> float:
    """Return a fuzzy similarity ratio between two strings (0‑1)."""
    from difflib import SequenceMatcher

    return SequenceMatcher(None, a, b).ratio()


def get_context(question: str) -> str:
    """
    Retrieve the most relevant context entry for *question*.

    The algorithm works in two stages:
    1. Token‑overlap scoring – picks the entry with the highest word overlap.
    2. If the best overlap score is zero, fall back to fuzzy string similarity.
    3. When no entry scores above a minimal threshold, return all context values
       concatenated (as a generic fallback).

    Args:
        question: The user's query string.

    Returns:
        A context string that best matches the query.
    """
    if not question:
        # Empty query – return generic fallback.
        return "\n".join(hardcoded_context.values())

    q_tokens = _tokenize(question)

    # Stage 1: token overlap.
    overlap_scores: List[Tuple[str, int]] = []
    for key in hardcoded_context:
        key_tokens = _tokenize(key)
        score = _score_overlap(q_tokens, key_tokens)
        overlap_scores.append((key, score))

    # Find the key with the highest overlap.
    best_key, best_score = max(overlap_scores, key=lambda item: item[1])

    if best_score > 0:
        return hardcoded_context[best_key]

    # Stage 2: fuzzy matching when token overlap fails.
    fuzzy_scores = [
        (key, _fuzzy_score(question.lower(), key.lower())) for key in hardcoded_context
    ]
    best_key_fuzzy, best_fuzzy = max(fuzzy_scores, key=lambda item: item[1])

    # Use a modest threshold to avoid spurious matches.
    if best_fuzzy >= 0.4:
        return hardcoded_context[best_key_fuzzy]

    # Fallback: concatenate all available context entries.
    return "\n".join(hardcoded_context.values())

prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful AI assistant. Use the following context to answer the user's question. "
            "If the context does not contain the answer, say 'I don't have enough information to answer that question.'\n\n"
            "Context: {context}",
        ),
        ("user", "Question: {question}"),
    ]
)

# Read configuration values for the chained model and Ollama base URL
_model_name, _ollama_base_url = _load_config()

llm = ChatOllama(
    model=_model_name,
    base_url=_ollama_base_url,
)

output_parser = StrOutputParser()

rag_chain = (
    RunnableParallel({
        "context": RunnableLambda(get_context),
        "question": RunnablePassthrough(),
    })
    | prompt
    | llm
    | output_parser
)

try:
    # This question is directly answered by our context
    response_1 = rag_chain.invoke("Who is Angela Lopez Mendoza?")
    print("Question: Who is Angela Lopez Mendoza?")
    print(f"Response: {response_1}")

    print("-" * 50)

    # This question is also answered by our context
    response_2 = rag_chain.invoke("What gender is Angela Lopez Mendoza?")
    print("Question: What gender is Angela Lopez Mendoza")
    print(f"Response: {response_2}")

    print("-" * 50)

    # This question is not in our context, so the model should respond accordingly
    response_3 = rag_chain.invoke("What did Angela Lopez Mendoza code?")
    print("Question: What did Angela Lopez Mendoza code?")
    print(f"Response: {response_3}")

except Exception as e:
    print(f"An error occurred: {e}")
    print("Please make sure the Ollama server is running and the model is pulled.")
