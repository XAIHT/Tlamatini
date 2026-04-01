# MCP Agent (mcp_agent.py)
import os
import sys
import re
import json
from typing import Dict, Any, Optional

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

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


def _ensure_chat_tool_model(llm):
    """Return a chat model that supports ``bind_tools`` when possible."""
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
        return getted_llm

    return llm


class MultiTurnToolAgentExecutor:
    """
    Explicit multi-turn tool-calling executor.

    This avoids the opaque AgentExecutor path and gives the backend direct
    control over tool-call / observation turns, which is required for the
    wrapped chat-agent runtime tools.
    """

    def __init__(self, llm, system_prompt: str, tools, max_iterations: int = 20):
        self.llm = llm
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.max_iterations = max_iterations
        self.bound_llm = llm.bind_tools(self.tools)

    def _invoke_tool(self, tool_call: Dict[str, Any]) -> str:
        tool_name = tool_call.get("name", "")
        tool = self.tool_map.get(tool_name)
        if tool is None:
            return json.dumps({
                "status": "error",
                "message": f"Tool '{tool_name}' is not available in this session.",
                "retryable": False,
            })

        raw_args = tool_call.get("args", {})
        tool_input = raw_args if raw_args not in (None, "") else {}

        try:
            result = tool.invoke(tool_input)
        except Exception as exc:
            return json.dumps({
                "status": "error",
                "message": f"Tool '{tool_name}' raised an exception: {exc}",
                "retryable": False,
            })

        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_text = payload.get("input", "")
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=input_text),
        ]

        for iteration in range(self.max_iterations):
            response = self.bound_llm.invoke(messages)
            messages.append(response)
            tool_calls = getattr(response, "tool_calls", None) or []

            print(f"--- MultiTurnToolAgentExecutor iteration {iteration + 1}/{self.max_iterations}")
            if tool_calls:
                print(f"--- Tool calls requested: {[call.get('name') for call in tool_calls]}")

            if not tool_calls:
                answer = getattr(response, "content", "") or ""
                if not str(answer).strip():
                    answer = "The tool-calling model returned an empty final response."
                return {"output": str(answer)}

            for tool_call in tool_calls:
                tool_result = self._invoke_tool(tool_call)
                messages.append(
                    ToolMessage(
                        tool_call_id=tool_call.get("id", ""),
                        name=tool_call.get("name", ""),
                        content=tool_result,
                    )
                )

        return {
            "output": (
                "The tool-calling loop hit its iteration limit before producing a final answer. "
                "Summarize the latest observed tool state or refine the request."
            )
        }


def create_unified_agent(llm, preeliminary_prompt: str):
    """
    Build a single multi-turn tool‑calling agent that can both chat and invoke MCP tools.
    """
    tools = get_mcp_tools()
    print(f"--- create_unified_agent: {len(tools)} tools available:")
    for t in tools:
        print(f"    - {t.name}: {t.description[:50]}..." if len(t.description) > 50 else f"    - {t.name}: {t.description}")

    getted_llm = _ensure_chat_tool_model(llm)
    if not hasattr(getted_llm, "bind_tools"):
        raise RuntimeError("The configured unified agent model does not support bind_tools().")

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
7. **SMART LOOPING**: Avoid repeating the same raw tool call with the same parameters unless the tool output explicitly indicates a retryable state.
8. **WRAPPED CHAT AGENT RUNS**: Tools named `chat_agent_*` launch isolated subprocess agents. When they return a `run_id` with `status="running"`, you may continue by calling `chat_agent_run_status`, `chat_agent_run_log`, or `chat_agent_run_stop`.
9. **POLLING IS ALLOWED FOR RUN IDs**: It is valid to call the runtime status/log tools multiple times for the SAME `run_id` while you are monitoring progress. This is not considered a bad loop.
10. **DO NOT CLAIM SUCCESS EARLY**: If a wrapped chat-agent run is still `running`, say that it is running and use the returned observations. Do not present the task as completed unless the runtime state or log proves it.
11. **FOR TRUSTED WRAPPED AGENT TOOLS**: They manage their own isolated runtime directories and may legitimately operate outside the normal chat path restrictions.

<question>
{{input}}
</question>


Answer:

"""
    config = _load_config()
    max_iterations = int(config.get("unified_agent_max_iterations", 20))
    return MultiTurnToolAgentExecutor(
        llm=getted_llm,
        system_prompt=system_prompt,
        tools=tools,
        max_iterations=max_iterations,
    )
