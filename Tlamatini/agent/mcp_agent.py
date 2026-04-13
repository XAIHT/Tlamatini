# MCP Agent (mcp_agent.py)
import json
import re
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage

from .capability_registry import select_tools_for_request
from .config_loader import get_int_config_value, load_config as _shared_load_config
from .global_execution_planner import (
    selected_tool_names_from_plan,
    summarize_global_execution_plan,
)
from .global_state import scoped_request_state
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


def _load_config() -> Dict[str, Any]:
    """Load ``config.json`` using the shared frozen/source-aware loader."""
    return _shared_load_config()


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
        private_client_kwargs = getattr(llm, "_client_kwargs", None)
        public_client_kwargs = getattr(llm, "client_kwargs", None)
        if token:
            client_kwargs["headers"] = {"Authorization": f"Bearer {token}"}
        elif private_client_kwargs:
            client_kwargs = private_client_kwargs or {}
        elif public_client_kwargs:
            client_kwargs = public_client_kwargs or {}

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

    def __init__(self, llm, system_prompt: str, tools, max_iterations: int = 256):
        self.llm = llm
        self.system_prompt = system_prompt
        self.tools = list(tools)
        self.tool_map = {tool.name: tool for tool in self.tools}
        self.max_iterations = max_iterations
        self.bound_llm = llm.bind_tools(self.tools) if self.tools else None

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

    # ------------------------------------------------------------------
    # Repetition detection helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _call_signature(tool_calls) -> str:
        """Return a deterministic string fingerprint for a list of tool calls."""
        parts = []
        for call in sorted(tool_calls, key=lambda c: c.get("name", "")):
            name = call.get("name", "")
            args = call.get("args") or {}
            parts.append(f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False)}")
        return "|".join(parts)

    # Maximum consecutive identical tool-call rounds before the loop is
    # broken.  Keeping this small prevents runaway iteration while still
    # allowing legitimate retries (e.g. polling a running agent twice).
    _REPEAT_LIMIT = 3

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_text = payload.get("input", "")
        planner_summary = str(payload.get("planner_summary", "") or "").strip()
        messages = [
            SystemMessage(content=self.system_prompt),
        ]
        if planner_summary:
            messages.append(SystemMessage(
                content=(
                    "REQUEST-SCOPED GLOBAL EXECUTION PLAN:\n"
                    f"{planner_summary}\n\n"
                    "Follow this planner output. Prefetch stages have already been applied before this executor runs. "
                    "Use only the planned tool and monitor stages unless the plan is empty."
                )
            ))
        messages.append(HumanMessage(content=input_text))

        if not self.tools:
            response = self.llm.invoke(messages)
            answer = getattr(response, "content", "") or ""
            if not str(answer).strip():
                answer = "The planner selected no tools for this request, and the model returned an empty response."
            return {"output": str(answer)}

        # --- Repetition tracking state ---
        last_signature: str | None = None
        repeat_count: int = 0

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
                    # The model finished tool-calling but returned empty content.
                    # Nudge it once to produce a summary from the collected tool results.
                    print("--- MultiTurnToolAgentExecutor: empty final response, nudging model to summarize ---")
                    # response already appended at line 211 — just add the nudge
                    messages.append(HumanMessage(content=(
                        "You have finished executing tools but returned an empty response. "
                        "Please now provide your final answer summarizing what you did and "
                        "the results you obtained. Do NOT call any more tools."
                    )))
                    retry_response = self.bound_llm.invoke(messages)
                    answer = getattr(retry_response, "content", "") or ""
                    retry_tool_calls = getattr(retry_response, "tool_calls", None) or []
                    if not str(answer).strip() or retry_tool_calls:
                        # Nudge failed — collect last real tool results as fallback answer.
                        print("--- MultiTurnToolAgentExecutor: nudge failed, collecting tool results as fallback ---")
                        last_real_results = []
                        for msg in reversed(messages):
                            if isinstance(msg, ToolMessage) and "[REPETITION BREAKER]" not in msg.content:
                                last_real_results.append(msg.content)
                                if len(last_real_results) >= 5:
                                    break
                        if last_real_results:
                            answer = (
                                "Here are the results from the executed tool calls:\n\n"
                                + "\n---\n".join(reversed(last_real_results))
                            )
                        else:
                            answer = "The tool-calling model returned an empty final response."
                return {"output": str(answer)}

            # --- Repetition detection ---
            sig = self._call_signature(tool_calls)
            if sig == last_signature:
                repeat_count += 1
            else:
                last_signature = sig
                repeat_count = 1

            if repeat_count >= self._REPEAT_LIMIT:
                # Give the LLM one chance to wrap up by injecting a
                # nudge message instead of executing the duplicate calls.
                tool_names = [c.get("name") for c in tool_calls]
                print(
                    f"--- Repetition breaker activated: '{tool_names}' "
                    f"called {repeat_count} times with identical args. "
                    "Injecting stop nudge."
                )
                # Append synthetic ToolMessage results so the message
                # list stays schema-valid, then add a nudge.
                for tool_call in tool_calls:
                    messages.append(
                        ToolMessage(
                            tool_call_id=tool_call.get("id", ""),
                            name=tool_call.get("name", ""),
                            content=(
                                "[REPETITION BREAKER] This exact tool call with identical "
                                "parameters has already been executed and its output was "
                                "returned in a previous iteration. Repeating it will not "
                                "produce new information. You MUST now produce your final "
                                "answer based on the results you already have. Do NOT call "
                                "any more tools."
                            ),
                        )
                    )
                # Give the model one more chance to produce a final answer.
                final_response = self.bound_llm.invoke(messages)
                answer = getattr(final_response, "content", "") or ""
                final_tool_calls = getattr(final_response, "tool_calls", None) or []
                if final_tool_calls:
                    # Model still insists on calling tools — force-stop.
                    print("--- Repetition breaker: model still requesting tools after nudge. Force-stopping.")
                    if not str(answer).strip():
                        # Collect the last real tool result to include in the answer.
                        last_real_results = []
                        for msg in reversed(messages):
                            if isinstance(msg, ToolMessage) and "[REPETITION BREAKER]" not in msg.content:
                                last_real_results.append(msg.content)
                                if len(last_real_results) >= 3:
                                    break
                        answer = (
                            "The tool-calling loop was stopped because the model kept "
                            "repeating the same tool call. Here are the last tool results "
                            "before the loop was broken:\n\n"
                            + "\n---\n".join(reversed(last_real_results))
                        )
                return {"output": str(answer)}

            # --- Normal tool execution ---
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


def _build_system_prompt(preeliminary_prompt: str, tools) -> str:
    import platform
    import sys as _sys

    tool_descriptions = "\n".join(
        f"- {tool.name}: {tool.description}" for tool in tools
    )

    # Remove the empty placeholder blocks from the base prompt since context
    # is injected into the user message by the chain, not into the system prompt.
    cleaned_prompt = re.sub(
        r"<system_context>\s*\{system_context\}\s*</system_context>",
        "",
        preeliminary_prompt,
    )
    cleaned_prompt = re.sub(
        r"<files_context>\s*\{files_context\}\s*</files_context>",
        "",
        cleaned_prompt,
    )
    cleaned_prompt = re.sub(
        r"<context>\s*\{context\}\s*</context>",
        "",
        cleaned_prompt,
    )
    # Escape any remaining curly braces that could break .format()
    escaped_prompt = cleaned_prompt.replace("{", "{{").replace("}", "}}")

    # Build a live platform information block
    os_name = platform.system()  # 'Windows', 'Linux', 'Darwin'
    os_version = platform.version()
    os_arch = platform.machine()
    is_windows = os_name == "Windows"
    is_frozen = getattr(_sys, "frozen", False)

    platform_block = (
        f"**PLATFORM INFORMATION** (live detection — use the correct commands for this OS):\n"
        f"- Operating System: {os_name} {platform.release()} ({os_version})\n"
        f"- Architecture: {os_arch}\n"
        f"- Runtime: {'Frozen executable' if is_frozen else 'Python source'}\n"
    )
    if is_windows:
        platform_block += (
            "- Shell: cmd.exe / PowerShell (Windows)\n"
            "- Package managers: winget, choco, pip, npm (NOT apt, yum, pacman, brew)\n"
            "- Path separator: backslash (\\)\n"
            "- Use Windows-native commands: dir (not ls), type (not cat), mkdir, rmdir, copy, move, del\n"
            "- NEVER use Linux/macOS commands (apt, sudo, chmod, chown, ln, grep) — they do not exist on this system\n"
        )
    else:
        platform_block += (
            "- Shell: bash / sh\n"
            "- Use Unix-native commands: ls, cat, mkdir, rm, cp, mv\n"
        )

    return f"""{escaped_prompt}

{platform_block}

You have access to the following tools. Use them proactively whenever the user's request can benefit from them:

{tool_descriptions}

**TOOL SELECTION GUIDE** (pick the right tool for the task):
- **Run a shell/system command** → `execute_command` (install packages, build software, run any CLI command)
- **Run a Python script file** → `execute_file`
- **Run inline Python code** → `chat_agent_pythonxer` (with script='...')
- **Crawl/scrape a website** → `chat_agent_crawler` (with url='...' and system_prompt='...')
- **Search the web** → `googler` (with query='...')
- **Call an HTTP API** → `chat_agent_apirer` (with url='...' and method='GET/POST')
- **Run SQL on a database** → `chat_agent_sqler` (with connection_string='...' and query='...')
- **Run MongoDB queries** → `chat_agent_mongoxer` (with mongodb.connection_string='...')
- **SSH into a remote host** → `chat_agent_ssher` (with host='...' and command='...')
- **Transfer files via SCP** → `chat_agent_scper` (with host='...' and local_path='...')
- **Git operations** → `chat_agent_gitter` (with repo_path='...' and operation='...')
- **Docker operations** → `chat_agent_dockerer` (with command='docker ...')
- **Kubernetes operations** → `chat_agent_kuberneter` (with command='kubectl ...')
- **Send email** → `chat_agent_send_email` (with smtp.username='...' and to='...')
- **Send Telegram message** → `chat_agent_telegramer`
- **Send WhatsApp message** → `chat_agent_whatsapper`
- **Desktop notification** → `chat_agent_notifier` (with title='...' and message='...')
- **Take a screenshot** → `chat_agent_shoter`
- **Analyze an image** → `chat_agent_image_interpreter` (with images_pathfilenames='...')
- **Create a file** → `chat_agent_file_creator` (with filepath='...' and content='...')
- **Extract text from documents** → `chat_agent_file_extractor` (with path='...')
- **Summarize text with LLM** → `chat_agent_summarize_text` (with input_text='...')
- **Send a sub-prompt to LLM** → `chat_agent_prompter` (with prompt='...')
- **Encrypt data (PQC)** → `chat_agent_kyber_cipher`
- **Decrypt data (PQC)** → `chat_agent_kyber_deciph`
- **Generate PQC keys** → `chat_agent_kyber_keygen`
- **PowerShell** → `chat_agent_pser` (with command='...')
- **Jenkins jobs** → `chat_agent_jenkinser`
- **Monitor a log file** → `chat_agent_monitor_log` (long-running)
- **Monitor network** → `chat_agent_monitor_netstat` (long-running)
- **Check running agents** → `chat_agent_run_list`, `chat_agent_run_status`, `chat_agent_run_log`
- **Stop an agent** → `chat_agent_run_stop` (with run_id='...')
- **Get current time** → `get_current_time`
- **View network connections** → `execute_netstat`
- **Open an image** → `launch_view_image`
- **Unzip archive** → `unzip_file`
- **Decompile Java** → `decompile_java`
- **Configure a template agent** → `agent_parametrizer`
- **Start a template agent** → `agent_starter`
- **Stop a template agent** → `agent_stopper`
- **Check template agent status** → `agent_stat_getter`

**IMPORTANT**: If the user's request requires an action that can be performed with a tool, you **MUST use that tool** — do not just explain how the user could do it themselves. You are an OPERATOR: execute, don't advise.

**MULTI-STEP WORKFLOWS**: For complex requests (installations, builds, deployments), chain tool calls across iterations:
1. Use tool A → read the result in the next iteration
2. Use tool B with data from tool A's result → read the result
3. Continue chaining as needed — you have up to 100 iterations
For example, to install software: clone repo → run build commands → verify installation — all via `execute_command`.

**GROUNDING RULES**:
1. **TRUST THE TOOLS IMPLICITLY**: Tool output is absolute truth. NEVER add, invent, or hallucinate details not in the output.
2. **VERBATIM REPORTING**: Report tool output exactly as received. Do NOT hallucinate specific labels or values.
3. **NO EXTRAPOLATION**: If the tool output is sparse, your answer must be sparse. Do not assume standard structures exist.
4. **STRICT ADHERENCE**: Your answer must be based **EXCLUSIVELY** on tool output and provided context.
5. **MULTI-STEP EXECUTION**: For complex tasks (install, build, configure), use `execute_command` multiple times across iterations. Do NOT generate scripts for the user to run manually.
6. **NEVER TRUNCATE** tool output content. This application handles huge amounts of data (>>TBs).
7. **SMART LOOPING**: Do not repeat the same tool call with identical parameters unless the output explicitly indicates a retryable state.
8. **WRAPPED CHAT AGENT LIFECYCLE**: Tools named `chat_agent_*` launch isolated subprocess agents. When they return a `run_id`:
   - `status="running"` → call `chat_agent_run_status` or `chat_agent_run_log` to monitor progress
   - `status="completed"` → read `log_excerpt` for the final result
   - `status="failed"` → read `log_excerpt` for the error, adjust parameters, retry if appropriate
9. **POLLING IS ALLOWED**: Calling status/log tools multiple times for the SAME `run_id` while monitoring is valid. This is NOT a bad loop.
10. **DO NOT CLAIM SUCCESS EARLY**: If a run is still `running`, say so. Only report completion when the runtime state or log proves it.
11. **TRUSTED WRAPPED AGENTS**: They manage their own isolated runtime directories and may operate outside normal path restrictions.
12. **PARAMETER FORMAT FOR chat_agent_* TOOLS**: Pass parameters as `key='value'` pairs in the request string. For nested config, use dotted notation: `llm.model='gpt-4'`, `smtp.username='user@example.com'`. Include ALL required parameters.

<question>
{{input}}
</question>


Answer:

"""


class CapabilityAwareToolAgentExecutor:
    """
    Delegates to the legacy full-tool executor by default and only applies
    Phase 1 selective capability binding when the request explicitly enables it.
    """

    def __init__(self, llm, preeliminary_prompt: str, tools, max_iterations: int = 256):
        self.llm = llm
        self.preeliminary_prompt = preeliminary_prompt
        self.tools = list(tools)
        self.max_iterations = max_iterations
        self._executor_cache: Dict[tuple[str, ...], MultiTurnToolAgentExecutor] = {}
        self.legacy_executor = self._get_executor_for_tools(self.tools)

    def _get_executor_for_tools(self, tools_subset):
        key = tuple(tool.name for tool in tools_subset)
        cached = self._executor_cache.get(key)
        if cached is not None:
            return cached

        executor = MultiTurnToolAgentExecutor(
            llm=self.llm,
            system_prompt=_build_system_prompt(self.preeliminary_prompt, tools_subset),
            tools=tools_subset,
            max_iterations=self.max_iterations,
        )
        self._executor_cache[key] = executor
        return executor

    def invoke(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        input_text = payload.get("input", "")
        multi_turn_enabled = bool(payload.get("multi_turn_enabled", False))
        global_execution_plan = payload.get("global_execution_plan")

        with scoped_request_state(
            multi_turn_enabled=multi_turn_enabled,
            suppress_visible_consoles=multi_turn_enabled,
        ):
            if not multi_turn_enabled:
                print("--- CapabilityAwareToolAgentExecutor: multi-turn disabled; using legacy full-tool binding ---")
                return self.legacy_executor.invoke({"input": input_text})

            selected_tools = None
            if global_execution_plan:
                planned_tool_names = selected_tool_names_from_plan(global_execution_plan)
                if planned_tool_names:
                    selected_tools = [
                        tool for tool in self.tools
                        if tool.name in set(planned_tool_names)
                    ]
                    print(
                        "--- CapabilityAwareToolAgentExecutor: using request-scoped global execution plan "
                        f"with {len(selected_tools)} planned tools"
                    )
                else:
                    print(
                        "--- CapabilityAwareToolAgentExecutor: planner selected no tools; "
                        "falling back to capability-based selection"
                    )
            if not selected_tools:
                selected_tools = select_tools_for_request(input_text, self.tools)
                if not selected_tools:
                    selected_tools = self.tools

            selected_names = [tool.name for tool in selected_tools]
            print(
                "--- CapabilityAwareToolAgentExecutor: multi-turn enabled; "
                f"selected {len(selected_tools)}/{len(self.tools)} tools: {selected_names}"
            )
            executor = self._get_executor_for_tools(selected_tools)
            executor_payload = {"input": input_text}
            if global_execution_plan:
                executor_payload["global_execution_plan"] = global_execution_plan
                executor_payload["planner_summary"] = (
                    payload.get("planner_summary")
                    or summarize_global_execution_plan(global_execution_plan)
                )
            return executor.invoke(executor_payload)


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

    max_iterations = get_int_config_value("unified_agent_max_iterations", 256, minimum=1)
    print(f"--- Unified agent max iterations: {max_iterations} ---")
    return CapabilityAwareToolAgentExecutor(
        llm=getted_llm,
        preeliminary_prompt=preeliminary_prompt,
        tools=tools,
        max_iterations=max_iterations,
    )
