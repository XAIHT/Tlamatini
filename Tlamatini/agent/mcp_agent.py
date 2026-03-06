# MCP Agent (mcp_agent.py)
import os
import sys
import re
import json
from typing import Dict, Any, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Import the MCP tools defined in the same package
from .tools import get_mcp_tools

# Try to import ChatOllama (newer location) – fall back to the community package
try:
    from langchain_ollama import ChatOllama
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
    except ImportError:  # pragma: no cover
        ChatOllama = None  # type: ignore

_CONFIG_CACHE: Optional[Dict[str, Any]] = None


def _find_config_path() -> Optional[str]:
    """
    Locate ``config.json`` in a robust way for both dev and PyInstaller builds.
    Search order:
    1) ``CONFIG_PATH`` env var (if set)
    2) Directory of the executable when frozen (PyInstaller)
    3) Directory of this module (agent package dir)
    """
    env_path = os.environ.get("CONFIG_PATH", "").strip()
    if env_path and os.path.isfile(env_path):
        return env_path

    # PyInstaller executable directory
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        p = os.path.join(exe_dir, "config.json")
        if os.path.isfile(p):
            return p

    # Module directory (development)
    module_dir = os.path.dirname(os.path.abspath(__file__))
    p2 = os.path.join(module_dir, "config.json")
    if os.path.isfile(p2):
        return p2

    return None


def _load_config() -> Dict[str, Any]:
    """Load ``config.json`` with a simple in‑memory cache."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    path = _find_config_path()
    cfg: Dict[str, Any] = {}
    if path and os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:  # pragma: no cover
            print(f"--- Warning: Failed to load config.json: {e} ---")
            cfg = {}

    _CONFIG_CACHE = cfg
    return cfg


def create_unified_agent(llm, preeliminary_prompt: str) -> AgentExecutor:
    """
    Build a single tool‑calling agent that can both chat and invoke MCP tools.
    """
    tools = get_mcp_tools()
    print(f"--- create_unified_agent: {len(tools)} tools available:")
    for t in tools:
        print(f"    - {t.name}: {t.description[:50]}..." if len(t.description) > 50 else f"    - {t.name}: {t.description}")

    # Convert a plain OllamaLLM into ChatOllama (which supports bind_tools)
    from langchain_ollama.llms import OllamaLLM

    if isinstance(llm, OllamaLLM) and ChatOllama is not None:
        config = _load_config()

        # Resolve model, endpoint and temperature from config → llm → defaults
        model = (
            config.get("unified_agent_model")
            or getattr(llm, "model", None)
            or "llama3.2:latest"
        )
        base_url = (
            config.get("unified_agent_base_url")
            or getattr(llm, "base_url", None)
            or "http://localhost:11434"
        )
        temperature = (
            config.get("unified_agent_temperature")
            if config.get("unified_agent_temperature") is not None
            else (getattr(llm, "temperature", None) or 0.0)
        )

        # Logging source of each parameter
        if config.get("unified_agent_model"):
            print(f"--- Using unified_agent_model from config.json: {model} ---")
        elif getattr(llm, "model", None):
            print(f"--- Using model from LLM instance: {model} ---")
        else:
            print(f"--- Using default model: {model} ---")

        # Authentication / extra client kwargs
        client_kwargs: Dict[str, Any] = {}
        token = config.get("ollama_token", "")
        if token:
            client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
        elif hasattr(llm, "_client_kwargs"):
            client_kwargs = llm._client_kwargs or {}
        elif hasattr(llm, "client_kwargs"):
            client_kwargs = llm.client_kwargs or {}

        # Build kwargs accepted by ChatOllama
        chat_kwargs: Dict[str, Any] = {
            "model": model,
            "base_url": base_url,
            "temperature": temperature,
        }

        # Propagate optional Ollama parameters if they exist
        for attr in ["top_k", "top_p", "repeat_penalty", "num_ctx", "num_predict"]:
            if hasattr(llm, attr):
                val = getattr(llm, attr)
                if val is not None:
                    chat_kwargs[attr] = val

        # Pass auth headers if supported
        if client_kwargs:
            chat_kwargs["client_kwargs"] = client_kwargs

        # Instantiate ChatOllama – fall back to a minimal config on TypeError
        try:
            getted_llm = ChatOllama(**chat_kwargs)
        except TypeError as e:  # pragma: no cover
            print(
                f"--- Warning: Some parameters not supported by ChatOllama, retrying with basic config: {e} ---"
            )
            basic_kwargs = {
                "model": model,
                "base_url": base_url,
                "temperature": temperature,
            }
            if client_kwargs:
                basic_kwargs["client_kwargs"] = client_kwargs
            getted_llm = ChatOllama(**basic_kwargs)

        print(
            f"--- Converted OllamaLLM to ChatOllama for tool calling (model={model}, base_url={base_url}) ---"
        )
    else:
        getted_llm = llm

    # Assemble a readable list of tool descriptions for the system prompt
    tool_descriptions = "\n".join(
        f"- {tool.name}: {tool.description}" for tool in tools
    )

    # Escape placeholders that the unified agent does NOT use
    escaped_prompt = re.sub(r"\{context\}", "{{context}}", preeliminary_prompt)
    escaped_prompt = re.sub(r"\{files_context\}", "{{files_context}}", escaped_prompt)
    escaped_prompt = re.sub(r"\{system_context\}", "{{system_context}}", escaped_prompt)

    # Full system prompt – includes the static tool list and the dynamic description block
    system_prompt = f"""{escaped_prompt}

You ALSO have access to a set of powerful local tools, their names are described below:
{tool_descriptions}

**IMPORTANT**:
If the user's request requires information that can be found or an action that can be performed with a tool, you **MUST use that tool**.

**CRITICAL**:
File operations (reading files, listing files, searching for files) are **NOT** available as tools so they are handled automatically by FileSearchRAGChain and provided in the context.

- **ALWAYS** check the context first for file information (look for "FILE MANIFEST", "Files Context", or file listings)
- If all of the file information needed to answer the user's request is in the context, extract and present its content if asked to do so, or process its contents to fulfil the request.
- The context will contain file listings, file contents, or file search results when relevant

**GROUNDING RULES**:
1. **TRUST THE TOOLS IMPLICITLY**: The tool output is the absolute truth for the task it performed. You MUST NOT add, invent, or hallucinate details that are not explicitly present in the tool's output.
2. **VERBATIM REPORTING**: If the tool detects a generic "Menu Item", you MUST report it as "Menu Item". Do NOT hallucinate specific labels like "Home", "About", or "Contact" unless the tool explicitly lists them.
3. **NO EXTRAPOLATION**: Do not assume standard web page structures (like "Search Bar", "Footer", "Copyright") exist unless the tool found them. If the tool output is sparse, your answer must be sparse.
4. **STRICT ADHERENCE**: Your answer must be based **EXCLUSIVELY** on the tool output and provided context. Do not add elements that are not there.
5. **EXECUTION RULES OF 'execute_file' AND 'execute_command' TOOLS**: These tools should be executed **just once per ask of user** no matter its exit code.
6. **NEVER TRUNCATE** the output content generated by the tools. It is not neccesary to do so 'cause this application is prepared to handle huge amounts of data (>>TBs).  
7. **AVOID LOOPS**: If you have executed a tool and obtained a result, **DO NOT** execute the same tool again with the same parameters. Proceed to answer the user's question using the data obtained.

<question>
{{input}}
</question>


Answer:

"""

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("user", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]
    )

    # Build the tool‑calling agent and its executor
    agent = create_tool_calling_agent(getted_llm, tools, prompt)
    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=10, # Stop infinite loops
        early_stopping_method="generate" # Attempt to answer with what you have
    )
    return executor