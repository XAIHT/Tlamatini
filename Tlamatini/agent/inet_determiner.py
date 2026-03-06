import os
import re
import sys
import json
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

_CONFIG_CACHE: Optional[Dict[str, Any]] = None

def _find_config_path() -> Optional[str]:
    """
    Locate config.json in a robust way for both dev and PyInstaller builds.
    Search order:
    1) CONFIG_PATH env var (if set)
    2) Directory of the executable when frozen (PyInstaller)
    3) Directory of this module (agent package dir)
    """
    # 1) Explicit override
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path
    # 2) PyInstaller executable dir
    try:
        if getattr(sys, 'frozen', False):
            exe_dir = os.path.dirname(sys.executable)
            p = os.path.join(exe_dir, 'config.json')
            if os.path.isfile(p):
                return p
    except Exception:
        pass
    # 3) Module directory (same path as rag_chain.py in dev)
    try:
        module_dir = os.path.dirname(os.path.abspath(__file__))
        p2 = os.path.join(module_dir, 'config.json')
        if os.path.isfile(p2):
            return p2
    except Exception:
        pass
    return None

def _load_config() -> Dict[str, Any]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE
    path = _find_config_path()
    cfg: Dict[str, Any] = {}
    if path and os.path.isfile(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except Exception:
            cfg = {}
    _CONFIG_CACHE = cfg
    return cfg

_BASE_INTERNET_HINT_WORDS = [
    r"\btoday\b",
    r"\bnow\b",
    r"\bcurrent\b",
    r"\blatest\b",
    r"\bnews\b",
    r"\bheadline\b",
    r"\bweather\b",
    r"\bforecast\b",
    r"\bprice\b",
    r"\bprices\b",
    r"\brate\b",
    r"\brates\b",
    r"\bstock\b",
    r"\bstocks\b",
    r"\bcrypto\b",
    r"\bbitcoin\b",
    r"\beth\b",
    r"\bscore\b",
    r"\bscores\b",
    r"\bgame\b",
    r"\bmatch\b",
    r"\bresult\b",
    r"\bresults\b",
    r"\bflight\b",
    r"\bflights\b",
    r"\bstatus\b",
    r"\bavailability\b",
    r"\brelease date\b",
    r"\btrending\b",
    r"\bexchange rate\b",
    r"\bwho is the current\b",
    r"\bwho won\b",
    r"\bwhen is (?:.*) released\b",
    r"\bAPI (?:status|docs|documentation)\b",
]

def _get_internet_hint_words() -> List[str]:
    cfg = _load_config()
    override_or_extend = str(cfg.get('internet_hint_words_mode', 'extend')).lower()
    custom = cfg.get('internet_hint_words') or []
    if isinstance(custom, list):
        custom_list = [str(x) for x in custom if isinstance(x, (str, bytes))]
    else:
        custom_list = []
    if override_or_extend == 'override' and custom_list:
        return custom_list
    return _BASE_INTERNET_HINT_WORDS + custom_list

def _build_agent_safely():
    """
    Build the LangChain agent defined in `web_search_llm.py` while suppressing
    its informational prints. Returns the agent or None on failure.
    """
    try:
        # Import lazily to avoid module import-time logs in some environments
        from . import web_search_llm  # type: ignore
    except Exception:
        try:
            # Fallback to absolute import if relative fails (when executed directly)
            import web_search_llm  # type: ignore
        except Exception:
            return None

    cfg = _load_config()
    base_url = str(cfg.get('ollama_base_url', '')).strip()
    if not base_url:
        host_env = os.environ.get("OLLAMA_HOST", "127.0.0.1").strip() or "127.0.0.1"
        port_env = os.environ.get("OLLAMA_PORT", "11434").strip() or "11434"
        base_url = f"http://{host_env}:{port_env}"
    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    try:
        port = int(parsed.port or 11434)
    except Exception:
        port = 11434

    # Silence common verbose loggers used by LangChain
    for name in (
        "langchain",
        "langchain_community",
        "httpx",
    ):
        logging.getLogger(name).setLevel(logging.ERROR)

    # Force quiet/streaming off to avoid token-by-token prints; allow config overrides
    verbose = bool(cfg.get('internet_classifier_verbose', False))
    max_iterations = int(cfg.get('internet_classifier_max_iterations', 1))
    streaming = bool(cfg.get('internet_classifier_streaming', False))
    model = str(cfg.get('internet_classifier_model', 'llama3.2:latest'))
    token = str(cfg.get('ollama_token', os.environ.get("OLLAMA_TOKEN", "")))
    agent = web_search_llm.create_ollama_agent(
        model=model,
        verbose=verbose,
        host=host,
        port=port,
        max_iterations=max_iterations,
        ollama_token=token,
        streaming=streaming,
    )
    return agent

def _classify_with_agent(agent, question: str) -> Optional[bool]:
    """
    Ask the agent to classify whether answering `question` requires internet.
    Returns True (internet required), False (not required), or None on failure.
    """
    if agent is None:
        return None

    prompt = (
        "You are a classifier. Decide if answering the user's question requires "
        "live internet or real-time web data beyond a local/offline knowledge base.\n"
        "Answer strictly with YES or NO.\n"
        "Rules:\n"
        "- Do NOT use any tools.\n"
        "- If the answer depends on current events, prices, weather, live scores, "
        "stock/crypto rates, schedules, availability, or up-to-the-minute facts, answer YES.\n"
        "- If the question can be answered from general knowledge or timeless facts, answer NO.\n\n"
        f"Question: {question}\n"
        "Only reply with YES or NO."
    )

    result = agent.invoke({"input": prompt})
    output = (result or {}).get("output", "").strip().upper()
    if output.startswith("YES"):
        return True
    if output.startswith("NO"):
        return False
    if "YES" in output and "NO" not in output:
        return True
    if "NO" in output and "YES" not in output:
        return False
    return None

def _heuristic_requires_internet(question: str) -> bool:
    q = question.lower()
    for pattern in _get_internet_hint_words():
        if re.search(pattern, q):
            return True
    # URLs or explicit web references imply internet
    if re.search(r"https?://|www\\.", q):
        return True
    # Dates like '2025 schedule', '2024 standings' often need current data
    if re.search(r"\\b(20\\d{2})\\b", q) and any(k in q for k in ["schedule", "standings", "rankings", "results", "fixtures"]):
        return True
    return False

def determine_internet_required(question: str) -> bool:
    agent = _build_agent_safely()
    classified = _classify_with_agent(agent, question)
    if classified is None:
        classified = _heuristic_requires_internet(question)
    return classified
