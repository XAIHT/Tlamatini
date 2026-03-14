import os
import re
import sys
import json
import logging
import requests
from typing import List
from ..global_state import global_state
from ..models import LLMProgram
from .. import inet_determiner
from .. import web_search_llm
from ..path_guard import is_path_allowed, REJECTION_MESSAGE
from .utils import _approx_tokens

try:
    import nltk
    try:
        nltk.data.find('tokenizers/punkt')
    except Exception:
        try:
            nltk.download('punkt', quiet=True)
        except Exception:
            pass
    try:
        nltk.data.find('taggers/averaged_perceptron_tagger')
    except Exception:
        for _pkg in ('averaged_perceptron_tagger', 'averaged_perceptron_tagger_eng'):
            try:
                nltk.download(_pkg, quiet=True)
                break
            except Exception:
                continue
except Exception:
    nltk = None

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
    application_path = os.path.dirname(application_path)

def request_cancel_generation():
    global_state.set_state('cancel_generation', True)

def clear_cancel_generation():
    global_state.set_state('cancel_generation', False)

def get_program_by_name(programName):
    """Retrieve a program by its name from the database."""
    try:
        return LLMProgram.objects.get(programName=programName)
    except LLMProgram.DoesNotExist:
        return None

def tokenCounterOfAsk(question: str):
    """
    Counts tokens using Ollama /api/tokenize. Falls back to char-based estimate.
    Respects "ssl_verify" and optional auth, preserving your previous behavior by default.
    """
    config_file_path = os.path.join(application_path, 'config.json')
    if not os.path.exists(config_file_path):
        print("Warning: config.json not found for token counting. Falling back to character estimation.")
        num_tokens = _approx_tokens(question)
        print(f"Number of tokens in input (estimated): {num_tokens}")
        return num_tokens

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        ollama_base_url = config.get('ollama_base_url')
        model = config.get('chained-model')
        token = config.get('ollama_token')
        verify = bool(config.get("ssl_verify", False))  # default False to preserve old behavior
        if not ollama_base_url or not model:
            raise ValueError("Ollama base URL or model not found in config.json")

        api_url = f"{ollama_base_url.rstrip('/')}/api/tokenize"
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        payload = {"model": model, "prompt": question}

        session = requests.Session()
        if config.get("disable_proxies", False):
            session.trust_env = False

        response = session.post(api_url, json=payload, headers=headers, timeout=20, verify=verify)
        response.raise_for_status()
        num_tokens = len(response.json().get('tokens', []))
        print(f"Number of tokens in input: {num_tokens}")
        return num_tokens

    except (requests.exceptions.RequestException, FileNotFoundError, ValueError, KeyError) as e:
        print(f"Could not use Ollama for token counting due to an error: {e}. Falling back to character estimation.")
        num_tokens = _approx_tokens(question)
        print(f"Number of tokens in input (estimated): {num_tokens}")
        return num_tokens

def is_valid_prompt(text: str) -> bool:
    """
    Analyzes a string to determine if it's a question or a prompt.
    """
    if not isinstance(text, str) or not text.strip():
        return False

    normalized_text = text.lower().strip()

    if normalized_text.endswith('?'):
        return True

    tokens: List[str]
    if nltk is not None:
        try:
            tokens = nltk.word_tokenize(normalized_text)
        except Exception:
            tokens = normalized_text.split()
    else:
        tokens = normalized_text.split()
    if not tokens:
        return False

    question_words = [
        'what', 'who', 'where', 'when', 'why', 'how', 'which', 'whose',
        'is', 'are', 'am', 'was', 'were', 'do', 'does', 'did', 'have', 'has', 'had',
        'can', 'could', 'will', 'would', 'should', 'may', 'might', 'must', 'shall',
        'code', 'codify', 'program', 'make', 'implement', 'create', 'build', 'develop', 'design',
        'write', 'generate', 'produce', 'construct', 'draft', 'compose',
        'list', 'enumerate', 'display', 'show', 'view', 'explain', 'describe', 'tell', 'provide', 'give',
        'find', 'search', 'locate', 'identify', 'determine', 'calculate', 'compute',
        'analyze', 'review', 'check', 'verify', 'validate', 'test', 'debug', 'fix', 'repair',
        'modify', 'update', 'change', 'improve', 'optimize', 'refactor', 'enhance',
        'document', 'comment', 'annotate', 'summarize', 'outline', 'help', 'assist',
        'execute', 'run', 'analyze', 'review', 'check', 'verify', 'validate', 'test', 'debug', 'fix', 'repair',
        'modify', 'update', 'change', 'improve', 'optimize', 'refactor', 'enhance',
        'document', 'comment', 'annotate', 'summarize', 'outline', 'help', 'assist', 'stop', 'terminate', 'kill',
        'unzip', 'decompile', 'decompress',
    ]

    multiword_patterns = [
        'tell me', 'show me', 'provide me', 'give me', 'help me', 'can you',
        'could you', 'would you', 'please help', 'please show', 'please explain',
        'please analyze', 'please review', 'please check', 'please verify', 'please validate', 'please test', 'please debug', 'please fix', 'please repair',
        'please modify', 'please update', 'please change', 'please improve', 'please optimize', 'please refactor', 'please enhance',
        'please document', 'please comment', 'please annotate', 'please summarize', 'please outline', 'please help', 'please assist', 'please unzip', 'please decompile',
    ]

    if tokens[0] in question_words:
        return True

    for pattern in multiword_patterns:
        pattern_words = pattern.split()
        if len(tokens) >= len(pattern_words):
            if tokens[:len(pattern_words)] == pattern_words:
                return True

    first_word_tag = None
    if nltk is not None:
        try:
            pos_tags = nltk.pos_tag(tokens)
            first_word_tag = pos_tags[0][1] if pos_tags else None
        except Exception:
            first_word_tag = None

    if first_word_tag in ['MD', 'VBP', 'VBZ', 'VBD']:
        return True

    if first_word_tag == 'VB':
        if len(tokens) > 1 and tokens[1] not in ['is', 'are', 'was', 'were']:
            return True

    return False

# ── Prompt-level access validation ───────────────────────────────────────────

# Regex to extract path-like tokens from a prompt.
# Matches Windows absolute paths (e.g. C:\folder\file.txt, D:/path),
# UNC paths (\\server\share), and Unix absolute paths (/usr/bin).
_PATH_PATTERN = re.compile(
    r'(?:'
    r'[A-Za-z]:[\\/_][^\s,;"\'\)]*'   # Windows drive letter paths
    r'|\\\\[^\s,;"\'\)]*'              # UNC paths
    r'|/(?:[a-zA-Z0-9_.\-]+/)+[a-zA-Z0-9_.\-]*'  # Unix absolute paths
    r')'
)


# Regex to detect relative paths (./something, ../something, or bare name\something)
_RELATIVE_PATH_PATTERN = re.compile(
    r'(?:^|\s)(?:\.\.?[\\/_]|[a-zA-Z0-9_.\-]+[\\/_][a-zA-Z0-9_.\-]+)'
)

_ALLOWED_SYNONYMS = re.compile(
    r'\b(?:allowed|permitted|configured|authorized|approved|valid|designated)\b'
    r'[\s\-]*'
    r'\b(?:path|paths|location|locations|directory|directories|folder|folders|route|routes|area|areas)\b',
    re.IGNORECASE
)

_CONTEXT_REFS = re.compile(
    r'\b(?:provided|loaded|given|attached|uploaded|current|above|this)\b'
    r'[\s\-]*'
    r'\b(?:context|document|documents|content|code|source\s*code|codebase|project|files|data|information|text)\b',
    re.IGNORECASE
)

_SYSTEM_QUERY = re.compile(
    r'\b(?:cpu\s*usage|memory\s*usage|disk\s*(?:space|usage)'
    r'|current\s*time|time\s*now)\b',
    re.IGNORECASE
)

_RUN_COMMAND = re.compile(
    r'\b(?:run|execute)\s+(?:command|cmd)\b',
    re.IGNORECASE
)

_IMAGE_DESCRIBE = re.compile(
    r'\b(?:describe|analyze|analyse)\s+with\s+(?:qwen|opus)\b',
    re.IGNORECASE
)

_CODE_GEN = re.compile(
    r'\b(?:create|generate|write|build|implement)\s+'
    r'(?:a\s+|an\s+|the\s+|a\s+new\s+)?'
    r'(?:implementation|web\s*page|version|program|code|script'
    r'|application|app|document|documentation)\b',
    re.IGNORECASE
)

_LIST_DIRS = re.compile(
    r'\blist\s+(?:available|configured|allowed)\s+'
    r'(?:director(?:y|ies)|folder|folders)\b',
    re.IGNORECASE
)

_DECOMPILE = re.compile(
    r'\b(?:decompile|disassemble)\s+(?:file|class|jar|binary)\b',
    re.IGNORECASE
)

_EXEC_SCRIPT = re.compile(
    r'\b(?:execute|run)\s+[\w\-]+\.(?:py|sh|bat|ps1|js|rb|pl)\b',
    re.IGNORECASE
)

_VIEW_IMAGE = re.compile(
    r'\b(?:view|show|display|open)\s+image\b',
    re.IGNORECASE
)

_CONCEPTUAL_PROMPT_START = re.compile(
    r'^\s*(?:what|why|how|explain|describe|summarize|analyse|analyze|review|discuss|compare)\b',
    re.IGNORECASE
)

_DIRECT_FILESYSTEM_ACTION = re.compile(
    r'^\s*(?:please\s+)?'
    r'(?:(?:can|could|would)\s+you\s+|help\s+me(?:\s+to)?\s+)?'
    r'(?:open|show|read|view|display|execute|run|list|search|find|locate'
    r'|delete|remove|move|copy|decompile|disassemble|unzip|extract|load'
    r'|save|edit|modify)\b',
    re.IGNORECASE
)


def _has_deterministic_filesystem_intent(question: str) -> bool:
    """
    Detect high-confidence filesystem-action intent without asking an LLM.

    This stays intentionally conservative: it only returns True for prompts
    that read like top-level action requests. Ambiguous or conceptual prompts
    keep flowing to the existing classifier fallback.
    """
    normalized = " ".join((question or "").split())
    if not normalized:
        return False
    if _CONCEPTUAL_PROMPT_START.search(normalized):
        return False
    return bool(_DIRECT_FILESYSTEM_ACTION.search(normalized))


def _relative_path_rejection_message() -> str:
    return (
        "The actions to routes or files must exclusively be in absolute "
        "format (not relative routes/paths are allowed) and within the "
        "allowed paths previously configured, so you must re-formulate "
        "your prompt."
    )


def _acces_aimed_prompt(question: str) -> bool:
    """
    Classify whether a user question INTENDS to access/read/write/execute files
    at the paths mentioned, or if the paths are merely informative/contextual.

    Connects to Ollama using the ``access_aimed_prompt_model`` from config.json
    (same connection pattern as SystemRAGChain / inet_determiner).

    Returns True if the LLM determines INTENT, False otherwise.
    """
    try:
        config_path = os.path.join(application_path, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception as exc:
        logging.error("_acces_aimed_prompt: cannot load config.json: %s", exc)
        # Fail-safe: assume intent (block the action)
        return True

    model = str(cfg.get('access_aimed_prompt_model',
                        cfg.get('chained-model', 'llama3.2:latest')))
    base_url = str(cfg.get('ollama_base_url', 'http://127.0.0.1:11434')).strip()
    token = str(cfg.get('ollama_token', '')).strip()

    try:
        from langchain_ollama import OllamaLLM
    except ImportError:
        logging.error("_acces_aimed_prompt: langchain_ollama not installed")
        return True       # fail-safe: assume intent

    client_kwargs = {}
    if token:
        client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}

    try:
        llm = OllamaLLM(
            base_url=base_url,
            model=model,
            client_kwargs=client_kwargs,
        )

        classification_prompt = (
            "You are a strict classifier.  Decide whether the user's question "
            "INTENDS to access, read, write, execute, move, copy, delete, or "
            "manipulate files/folders at the routes or paths mentioned in the "
            "question, OR whether the routes/paths are merely informative, "
            "contextual, or illustrative (the user is NOT asking the system to "
            "touch those paths).\n\n"
            "Rules:\n"
            "- If the user wants the system to perform any action ON or WITH "
            "the paths (open, run, view, unzip, decompile, move, copy, delete, "
            "list, search), answer INTENT.\n"
            "- If the paths are just part of an explanation, comparison, "
            "example, or informational discussion, answer NOT-INTENT.\n\n"
            f"Question: {question}\n\n"
            "Answer ONLY with the single word: INTENT or NOT-INTENT"
        )

        response = llm.invoke(classification_prompt)
        output = (response or "").strip().upper()
        print(f"--- _acces_aimed_prompt LLM response: '{output}'")

        if "NOT-INTENT" in output or "NOT INTENT" in output:
            return False
        if "INTENT" in output:
            return True
        # Ambiguous response: fail-safe → assume intent
        return True
    except Exception as exc:
        logging.error("_acces_aimed_prompt: LLM call failed: %s", exc)
        return True       # fail-safe: assume intent


def _indirect_file_access_prompt(question: str) -> bool:
    """
    Detect whether a prompt implicitly tries to access, execute, or manipulate
    files WITHOUT specifying an explicit absolute path.

    Examples that should return True:
      - "Execute cat_art.py, located in the root of this application."
      - "Open the config file in the downloads folder."
      - "Run the script in the desktop directory."
      - "Show me the logs from the server folder."

    Examples that should return False:
      - "What is a Python file?"
      - "Explain how config.json works."
      - "How do I run a .py script in general?"

    Returns True if indirect access is detected, False otherwise.
    """
    try:
        config_path = os.path.join(application_path, 'config.json')
        with open(config_path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
    except Exception as exc:
        logging.error("_indirect_file_access_prompt: cannot load config.json: %s", exc)
        return True  # fail-safe

    model = str(cfg.get('access_aimed_prompt_model',
                        cfg.get('chained-model', 'llama3.2:latest')))
    base_url = str(cfg.get('ollama_base_url', 'http://127.0.0.1:11434')).strip()
    token = str(cfg.get('ollama_token', '')).strip()

    try:
        from langchain_ollama import OllamaLLM
    except ImportError:
        logging.error("_indirect_file_access_prompt: langchain_ollama not installed")
        return True

    client_kwargs = {}
    if token:
        client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}

    try:
        llm = OllamaLLM(
            base_url=base_url,
            model=model,
            client_kwargs=client_kwargs,
        )

        classification_prompt = (
            "You are a security classifier for a local computer assistant. "
            "Determine whether the user's question tries to ACCESS, EXECUTE, "
            "RUN, OPEN, READ, WRITE, MOVE, COPY, DELETE, LIST, SEARCH, UNZIP, "
            "or MANIPULATE a specific file or folder on the local computer, "
            "but WITHOUT providing an explicit absolute file system path "
            "(e.g. C:\\\\Users\\\\... or /home/user/...).\n\n"
            "Examples of INDIRECT access (answer YES):\n"
            "- 'Execute cat_art.py, located in the root of this application.'\n"
            "- 'Open the config file in the downloads folder.'\n"
            "- 'Run the script on my desktop.'\n"
            "- 'Show me the logs from the server folder.'\n"
            "- 'Delete the temp files in this project.'\n\n"
            "Examples of NO indirect access (answer NO):\n"
            "- 'What is a Python file?'\n"
            "- 'Explain how config.json works in general.'\n"
            "- 'How do I unzip a file?'\n"
            "- 'What are the best practices for logging?'\n"
            "- 'Summarize the project source code in the provided context.'\n"
            "- 'Analyze the code in the loaded context.'\n"
            "- 'Explain this project based on the given documents.'\n"
            "- 'What does the provided code do?'\n\n"
            "**IMPORTANT: If the user is asking about already loaded/provided "
            "context, documents, or code (not requesting to access NEW files), "
            "answer NO.**\n\n"
            f"Question: {question}\n\n"
            "Does this question attempt to access or manipulate a specific "
            "file or folder WITHOUT providing an explicit absolute path?\n"
            "Answer ONLY with: YES or NO"
        )

        response = llm.invoke(classification_prompt)
        output = (response or "").strip().upper()
        print(f"--- _indirect_file_access_prompt LLM response: '{output}'")

        if output.startswith("NO") or ("NO" in output and "YES" not in output):
            return False
        if output.startswith("YES") or "YES" in output:
            return True
        # Ambiguous → fail-safe: assume indirect access
        return True
    except Exception as exc:
        logging.error("_indirect_file_access_prompt: LLM call failed: %s", exc)
        return True  # fail-safe


def _validate_accesses_in_prompt(question: str):
    """
    Inspect a user prompt for file-system paths and enforce allowed_paths policy.

    Returns:
        None   – the prompt may proceed normally.
        str    – a rejection message to return to the user.
    """
    # 1) Extract all path-like tokens from the prompt
    found_paths = _PATH_PATTERN.findall(question)
    if not found_paths:
        deterministic_intent = _has_deterministic_filesystem_intent(question)

        # If the prompt references "allowed paths/locations" (or synonyms),
        # it is a valid way to indicate scope → skip indirect access check.
        if _ALLOWED_SYNONYMS.search(question):
            print("--- _validate_accesses_in_prompt: prompt references allowed paths/locations → proceed")
            return None

        # If the prompt refers to already-loaded context / documents,
        # it is NOT an indirect file access — the user is querying the RAG context.
        if _CONTEXT_REFS.search(question):
            print("--- _validate_accesses_in_prompt: prompt references loaded context → proceed")
            return None

        # System-metrics or time queries → tool-routed, not file access.
        if _SYSTEM_QUERY.search(question):
            print("--- _validate_accesses_in_prompt: system/time query → proceed")
            return None

        # Command execution requests (ping, netstat, ipconfig …) → tool-routed.
        if _RUN_COMMAND.search(question):
            print("--- _validate_accesses_in_prompt: command execution → proceed")
            return None

        # Image description via a model (Qwen, Opus) → tool-routed.
        if _IMAGE_DESCRIBE.search(question):
            print("--- _validate_accesses_in_prompt: image description via model → proceed")
            return None

        # Code / web-page / documentation generation → creative output, not
        # file access.
        if _CODE_GEN.search(question):
            print("--- _validate_accesses_in_prompt: code/content generation → proceed")
            return None

        # Listing available/configured directories → informational.
        if _LIST_DIRS.search(question):
            print("--- _validate_accesses_in_prompt: listing available dirs → proceed")
            return None

        # Decompilation requests → tool-routed.
        if _DECOMPILE.search(question):
            print("--- _validate_accesses_in_prompt: decompile request → proceed")
            return None

        # Execute / run a named script file → tool-routed
        # (e.g. "Execute cat_art.py, located in the root of this application.")
        if _EXEC_SCRIPT.search(question):
            print("--- _validate_accesses_in_prompt: script execution → proceed")
            return None

        # View / search image in allowed locations → tool-routed.
        if _VIEW_IMAGE.search(question):
            print("--- _validate_accesses_in_prompt: image view request → proceed")
            return None

        if bool(_RELATIVE_PATH_PATTERN.search(question)) and deterministic_intent:
            print("--- _validate_accesses_in_prompt: deterministic relative-path access request → reject")
            return _relative_path_rejection_message()

        # No explicit paths and no "allowed" reference — check for indirect access
        # (e.g. "Open the config file in the downloads folder").
        if _indirect_file_access_prompt(question):
            return (
                "In order to implement any actions to files or routes within "
                "the local computer you must provide explicit and absolute "
                "routes/paths to elements only in the allowed paths configured, "
                "and not suggested locations."
            )
        return None          # genuinely no file access intent → proceed normally

    print(f"--- _validate_accesses_in_prompt: detected paths: {found_paths}")

    # 2) Check if ALL paths are inside allowed_paths
    outside_paths = [p for p in found_paths if not is_path_allowed(p)]
    if not outside_paths:
        return None          # all paths are allowed → proceed normally

    print(f"--- _validate_accesses_in_prompt: paths outside allowed: {outside_paths}")

    deterministic_intent = _has_deterministic_filesystem_intent(question)
    if deterministic_intent:
        print("--- _validate_accesses_in_prompt: deterministic outside-path access intent detected → reject")
        return REJECTION_MESSAGE

    # 3) Some paths are outside allowed → ask the LLM to classify intent
    is_intent = _acces_aimed_prompt(question)
    print(f"--- _validate_accesses_in_prompt: LLM intent classification: {is_intent}")

    if not is_intent:
        return None          # NOT-INTENT → paths are informative, proceed normally

    # 4) INTENT detected — check if the offending paths are relative
    has_relative = bool(_RELATIVE_PATH_PATTERN.search(question))
    # Also flag absolute paths that simply aren't inside allowed dirs
    absolute_outside = [p for p in outside_paths if os.path.isabs(p)]

    if has_relative and not absolute_outside:
        # Only relative paths detected
        return _relative_path_rejection_message()

    # Absolute paths outside allowed_paths
    return REJECTION_MESSAGE


def ask_rag(rag_chain, question, chat_history=None, inet_enabled=False):
    print(f"\n--- ask_rag: >>>>>>>>>>{question}<<<<<<<<<<")
    global_state.set_state('rag_chain_ready', False)
    clear_cancel_generation()
    if chat_history is None:
        chat_history = []

    if isinstance(question, dict):
        raw_text = question.get("input", "")
    elif isinstance(question, str):
        raw_text = question
    else:
        raw_text = str(question)

    try:
        with open(os.path.join(application_path, 'config.json'), 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        max_input_tokens = int(cfg.get("max_input_tokens", 300))
    except Exception:
        max_input_tokens = 300

    if tokenCounterOfAsk(raw_text) > max_input_tokens:
        response = (f'Your input exceeds the {max_input_tokens} token limit. Please break it into smaller, '
                   f'more focused questions or remove unnecessary details to fit within the limit.')
        global_state.set_state('rag_chain_ready', True)
        return str(response)

    if not is_valid_prompt(raw_text):
        response = ('Please rephrase your input as a clear question or command. '
                   'Examples: "How do I...?", "What is...?", "Show me...", "Create a...", or "Explain..."')
        global_state.set_state('rag_chain_ready', True)
        return str(response)

    # ── Prompt-level access validation ──
    access_rejection = _validate_accesses_in_prompt(raw_text)
    if access_rejection:
        print("--- ask_rag: prompt rejected by access validation")
        global_state.set_state('rag_chain_ready', True)
        return str(access_rejection)

    payload = {"input": raw_text, "chat_history": chat_history}
    if isinstance(question, dict) and question.get("conversation_user_id") is not None:
        payload["conversation_user_id"] = question["conversation_user_id"]

    # Import the exception type for catching cancel during streaming
    from .chains.base import GenerationCancelledException

    # Check if already cancelled before even starting
    if global_state.get_state('cancel_generation'):
        print("--- [CANCEL] Generation cancelled before starting ---")
        global_state.set_state('rag_chain_ready', True)
        return "Generation was cancelled."

    try:
        if inet_enabled:
            inet_required = inet_determiner.determine_internet_required(raw_text)
            print(f"\n--- Internet may be required: {inet_required}")
            
            # Check for cancellation before web search
            if global_state.get_state('cancel_generation'):
                print("--- [CANCEL] Cancelled before web search ---")
                global_state.set_state('rag_chain_ready', True)
                return "Generation was cancelled."
            
            if inet_required:
                print("--- Internet search required. Enriching with web context before answering. ---")
                web_search_llm_instance = web_search_llm.build_web_search_llm(rag_chain.getHttpxClientInstance())
                if web_search_llm_instance:
                    web_result = web_search_llm_instance.invoke(payload)
                    if isinstance(web_result, dict):
                        payload["external_context"] = web_result.get("external_context", "")
                        payload["external_sources"] = web_result.get("sources", [])
                else:
                    print("--- Web search component unavailable; proceeding without web context ---")
            
            # Check for cancellation before LLM invoke
            if global_state.get_state('cancel_generation'):
                print("--- [CANCEL] Cancelled before LLM invoke ---")
                global_state.set_state('rag_chain_ready', True)
                return "Generation was cancelled."
            
            response = rag_chain.invoke(payload)
        else:
            # Check for cancellation before LLM invoke
            if global_state.get_state('cancel_generation'):
                print("--- [CANCEL] Cancelled before LLM invoke ---")
                global_state.set_state('rag_chain_ready', True)
                return "Generation was cancelled."
            
            response = rag_chain.invoke(payload)
            
    except GenerationCancelledException:
        print("--- [CANCEL] Generation cancelled during streaming ---")
        global_state.set_state('rag_chain_ready', True)
        return "Generation was cancelled."
    except Exception as e:
        # Re-raise if not a cancellation-related error
        if global_state.get_state('cancel_generation'):
            print(f"--- [CANCEL] Error during cancelled generation: {e} ---")
            global_state.set_state('rag_chain_ready', True)
            return "Generation was cancelled."
        raise
    
    global_state.set_state('rag_chain_ready', True)

    if isinstance(response, dict):
        return response.get("answer", "I was unable to generate a response. Please try rephrasing your question or check the system status.")
    
    global_state.set_state('rag_chain_ready', True)
    return str(response)
