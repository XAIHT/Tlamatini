import asyncio
import sys
import os
import json
import re
import grpc
import mimetypes
from typing import Optional, Dict, Any

# Handle both relative import from the same directory (when used as module) and direct import (when run as script)
try:
    from . import filesearch_pb2
    from . import filesearch_pb2_grpc
    from .path_guard import is_path_allowed, REJECTION_MESSAGE
except ImportError:
    # If relative import fails, try importing from the same directory
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import filesearch_pb2
        import filesearch_pb2_grpc
        from path_guard import is_path_allowed, REJECTION_MESSAGE
    except ImportError:
        print("ERROR: Could not find 'filesearch_pb2.py' or 'filesearch_pb2_grpc.py'.")
        print("Please ensure they are in the same directory as this script.")
        filesearch_pb2 = None
        filesearch_pb2_grpc = None

from langchain_ollama import OllamaLLM
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser

# --- 0. System policy for tool routing (copied from mcp_files_search_client.py) ---
SYSTEM_POLICY = (
    "You are an MCP-File-Manager named **FileSearchRAGChain**. Follow this tool-use policy **strictly**.\n"
    "When to call the tool:\n"
    "- Call remote_file_search when the user asks to find files or folders by name, glob/pattern, size, or modified time.\n"
    "- Call list_allowed_directories when the user asks to list available directories or allowed paths.\n"
    "When NOT to call the tool:\n"
    "- Do not call tools for purely conceptual questions (e.g., 'what is a glob?'); answer directly.\n"
    "- Do not call tools if required arguments are missing; first ask a concise clarifying question.\n"
    "Pre-call checklist (enforce before calling):\n"
    "- file_pattern is present and looks like a pattern or filename (e.g., '*.py', 'report.*', 'notes.txt').\n"
    "- If base_path_key is provided, it must be one of: docs, downloads, desktop, pictures, videos, music.\n"
    "- If NO base_path_key is provided, you should generally default to searching ALL allowed locations (send null/None for base_path_key) rather than asking for clarification, unless the request is ambiguous.\n"
    "Output rules after any tool call:\n"
    "- Summarize results succinctly. If many items are returned, show only the top results and note the total.\n"
    "- For empty results, say 'No files found for that criteria.'\n"
    "Examples (for routing intuition):\n"
    "- User: 'Explain glob patterns' -> No tool call; provide explanation.\n"
    "- User: 'Find all *.py in docs' -> Call remote_file_search with file_pattern='*.py', base_path_key='docs'.\n"
    "- User: 'Search for report.*' (no location) -> Call remote_file_search with file_pattern='report.*', base_path_key=null (search all).\n"
    "- User: 'show README.md' -> Use show action with file_name='README.md', base_path_key=null.\n"
    "- User: 'list available dirs' -> Use list_dirs action.\n"
)
ALLOWED_KEYS = ["application", "docs", "downloads", "desktop", "pictures", "videos", "music"]
_TEXT_LIKE_EXTENSIONS = {
    '.txt', '.md', '.py', '.json', '.xml', '.html', '.css', '.js', '.yml', '.yaml',
    '.toml', '.ini', '.cfg', '.csv', '.tsv', '.svg', '.log', '.bat', '.ps1', '.sh',
}
_PROJECT_HOME_HINTS = (
    'project home',
    'project root',
    'repo root',
    'repo home',
    'repository root',
    'repository home',
    'application root',
    'application home',
    'app root',
    'codebase root',
)
_DIRECT_FILE_ACTION_HINTS = (
    'show', 'read', 'open', 'view', 'display', 'summarize', 'summarise',
    'analyze', 'analyse', 'review', 'explain',
)
_EXACT_FILENAME_RE = re.compile(r"\b[\w.\-]+\.[A-Za-z0-9]{1,16}\b")


def _get_application_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(script_dir))


def _get_default_config_path() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.join(os.path.dirname(sys.executable), "config.json")
    return os.path.join(os.path.dirname(__file__), "config.json")


def _looks_like_text_file(path: str) -> bool:
    mime, _ = mimetypes.guess_type(path)
    ext = os.path.splitext(path)[1].lower()
    return bool((mime and mime.startswith('text/')) or ext in _TEXT_LIKE_EXTENSIONS)


def _extract_exact_filename(question: str) -> Optional[str]:
    for match in _EXACT_FILENAME_RE.finditer(str(question or "")):
        candidate = match.group(0).strip().strip("'\"")
        if any(sep in candidate for sep in ('*', '?', '/', '\\', ':')):
            continue
        return candidate
    return None


def _mentions_project_home_scope(question: str) -> bool:
    normalized = " ".join(str(question or "").lower().split())
    return any(hint in normalized for hint in _PROJECT_HOME_HINTS)


def _render_file_context(path: str, *, header: str, max_chars: int = 500000) -> str:
    resolved_path = os.path.realpath(os.path.abspath(path))
    if not is_path_allowed(resolved_path):
        return REJECTION_MESSAGE

    if _looks_like_text_file(resolved_path):
        with open(resolved_path, "r", encoding="utf-8", errors="replace") as file_handle:
            content = file_handle.read()
        if len(content) > max_chars:
            content = content[:max_chars] + "\n... [truncated]"
        return (
            f"{header}\n"
            f"{resolved_path}\n\n"
            "Full content of the file:\n"
            f"<FILE_CONTENT_START>\n{content}\n<FILE_CONTENT_END>\n"
        )

    return (
        f"{header}\n"
        f"{resolved_path}\n\n"
        "[INFO] The requested file appears to be binary (e.g., image/video/pdf). "
        "Content is not embedded in context to avoid corruption.\n"
        f"Suggested action: use tools like 'qwen_analyze_image', 'opus_analyze_image' or "
        f"'launch_view_image' with path '{resolved_path}'."
    )


class FileSearchRAGChain:
    def __init__(self, config_path=None):
        # Load configuration from config.json
        if config_path is None:
            config_path = _get_default_config_path()

        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
        except FileNotFoundError:
            print(f"Warning: config.json not found at {config_path}. Using defaults.")
            config = {}

        # Initialize Ollama LLM with values from config
        ollama_base_url = config.get("ollama_base_url", "http://127.0.0.1:11434")
        ollama_model = config.get("chained-model", "gpt-oss:120b-cloud")
        ollama_token = config.get("ollama_token", "")

        client_kwargs = {}
        if ollama_token:
            client_kwargs["headers"] = {"Authorization": f"Bearer {ollama_token}"}

        self.llm = OllamaLLM(
            base_url=ollama_base_url,
            model=ollama_model,
            format="json",  # Ensure LLM outputs JSON for planning
            client_kwargs=client_kwargs
        )

        # Get gRPC target from config, default to localhost
        self.grpc_target = config.get("mcp_files_search_grpc_target", "localhost:50051")

        # --- Prompts ---

        # 1. Routing prompt (like chain_system_lcel.py)
        self.routing_prompt = PromptTemplate.from_template(
            """Does this question ask to find, search for, list, or show files/folders on the local file system?

IMPORTANT: Answer YES only when the user wants to LOCATE, OPEN, or LIST files on disk.
Answer NO when file names appear as part of code examples, inline content, or refactoring/implementation requests.

Examples:
Q: "how does the system work?" → NO
Q: "find all python files" → YES
Q: "list all *.txt files in docs" → YES
Q: "what is a glob pattern?" → NO
Q: "where is the 'report.pdf' file?" → YES
Q: "show me the 'README.md' file" → YES
Q: "list available dirs" → YES
Q: "find all *.py in all allowed locations" → YES
Q: "Describe the image Kosana.jpg" → YES
Q: "Analyze the log file error.log" → YES
Q: "Process the data in data.csv" → YES
Q: "Implement a refactoring of the provided source code to replace NTLM with Kerberos" → NO
Q: "Here is my krb5.conf content: [libdefaults]..." → NO (file content provided inline, not a search)
Q: "Refactor this Java code that references login.conf" → NO (code discussion, not file search)
Q: "Create an implementation based on KerberosClientAuthenticator.java" → NO (code generation request)
Q: "The config.yaml file contains these settings..." → NO (describing content, not searching)

Question: {question}

Answer ONLY with YES or NO:"""
        )

        # 2. Planning prompt (from mcp_files_search_client.py)
        # We build the prompt string in steps to avoid f-string escaping issues
        
        # This is the template string for LangChain.
        # All braces for the JSON schema are doubled ({{ }}) to escape them for PromptTemplate.
        # {query} is the only variable LangChain should see.
        planning_template = """

You must decide one action: "search", "show", "list_dirs", "answer", or "clarify".
- action="search": Use when the user wants to find files/folders. Provide search inputs.
- action="show": Use only when the user provided the exact name of a single file (no wildcards, no paths). You must return the file_name and optionally base_path_key/include_hidden so the client can search for that exact file and display its full content.
- action="list_dirs": Use when the user asks to list available directories or allowed paths.
- action="answer": Use when the user asks a conceptual/explanatory question; provide a textual answer.
- action="clarify": Use when the user likely wants a search but didn't provide enough info; ask exactly one short clarifying question.

Output STRICT JSON only (no prose), following this schema:
{{
    "action": "search" | "show" | "list_dirs" | "answer" | "clarify",
    "search": {{
        "file_pattern": "string",
        "base_path_key": "one of {ALLOWED_KEYS_STR} or null",
        "include_hidden": true | false
    }},
    "show": {{
        "file_name": "string",  // exact filename only, e.g., "README.md"; no wildcards/paths
        "base_path_key": "one of {ALLOWED_KEYS_STR} or null",
        "include_hidden": true | false
    }},
    "list_dirs": {{}},
    "answer": "string",
    "clarify": "string"
}}

Fill only the relevant field(s) matching the action. Return JSON only.

User Query: {query}
"""
        # Now, we manually inject the Python-side constants
        # before creating the PromptTemplate.
        final_prompt_string = (
            SYSTEM_POLICY +
            planning_template.replace("{ALLOWED_KEYS_STR}", str(ALLOWED_KEYS))
        )
        
        self.planning_prompt = PromptTemplate.from_template(final_prompt_string)


    def _call_grpc_server_sync(self, file_pattern: str, base_key: Optional[str], hidden: bool, verbose: bool = True):
        """
        Synchronous gRPC client call.
        (Copied from mcp_files_search_client.py and adapted)
        """
        if filesearch_pb2 is None or filesearch_pb2_grpc is None:
            print("ERROR: gRPC modules not loaded. Cannot perform file search.")
            return []

        if verbose:
            print(f"\n--- [FileSearchRAGChain]: Attempting to connect to gRPC server at '{self.grpc_target}' ---")
        
        try:
            with grpc.insecure_channel(
                self.grpc_target,
                options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)],  # 16 MB
            ) as channel:
                stub = filesearch_pb2_grpc.FileSearcherStub(channel)
                
                request = filesearch_pb2.SearchRequest(  # type: ignore[attr-defined]
                    base_path_key=base_key, 
                    file_pattern=file_pattern,
                    include_hidden=hidden
                )
                
                if verbose:
                    print(f"--- [FileSearchRAGChain]: gRPC connection successful. Sending request: {{pattern: '{file_pattern}', key: '{base_key}'}} ---")
                response = stub.SearchFiles(request)
                if verbose:
                    print("--- [FileSearchRAGChain]: gRPC server responded. ---")
                
                if response.error_message:
                    if verbose:
                        print(f"❌ Server Error: {response.error_message}")
                    return []
                
                if not response.found_files:
                    if verbose:
                        print("\n✅ Server responded: No files found for that criteria.")
                    return []

                total = len(response.found_files)
                if verbose:
                    print(f"\n✅ Server found {total} files.")
                return list(response.found_files)

        except grpc.RpcError as e:
            if verbose:
                print(f"\n❌ [FileSearchRAGChain]: gRPC connection FAILED: {e.details()}")
                print("   Is the 'mcp_files_search_server.py' script running?")
            return []
        except Exception as e:
            if verbose:
                print(f"\n❌ [FileSearchRAGChain]: An unexpected error occurred in gRPC call: {e}")
            return []

    def _call_grpc_list_dirs_sync(self, verbose: bool = True):
        """
        Synchronous gRPC client call to list directories.
        """
        if filesearch_pb2 is None or filesearch_pb2_grpc is None:
            print("ERROR: gRPC modules not loaded. Cannot perform file search.")
            return {}

        if verbose:
            print(f"\n--- [FileSearchRAGChain]: Attempting to connect to gRPC server at '{self.grpc_target}' for ListAllowedDirs ---")
        
        try:
            with grpc.insecure_channel(
                self.grpc_target,
                options=[('grpc.max_receive_message_length', 16 * 1024 * 1024)],  # 16 MB
            ) as channel:
                stub = filesearch_pb2_grpc.FileSearcherStub(channel)
                
                request = filesearch_pb2.ListDirsRequest() # type: ignore[attr-defined]
                
                if verbose:
                    print("--- [FileSearchRAGChain]: gRPC connection successful. Sending ListAllowedDirs request ---")
                response = stub.ListAllowedDirs(request)
                if verbose:
                    print("--- [FileSearchRAGChain]: gRPC server responded. ---")
                
                return dict(response.allowed_dirs)

        except grpc.RpcError as e:
            if verbose:
                print(f"\n❌ [FileSearchRAGChain]: gRPC connection FAILED: {e.details()}")
                print("   Is the 'mcp_files_search_server.py' script running?")
            return {}
        except Exception as e:
            if verbose:
                print(f"\n❌ [FileSearchRAGChain]: An unexpected error occurred in gRPC call: {e}")
            return {}

    async def async_call_grpc_server(self, file_pattern: str, base_key: Optional[str], hidden: bool):
        """Async wrapper for the synchronous gRPC call"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,  # Use default thread pool
            self._call_grpc_server_sync,
            file_pattern,
            base_key,
            hidden,
            True # verbose
        )

    async def async_call_grpc_list_dirs(self):
        """Async wrapper for the synchronous gRPC list dirs call"""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,  # Use default thread pool
            self._call_grpc_list_dirs_sync,
            True # verbose
        )

    async def should_fetch_files_context(self, question: str):
        """Use LLM to decide if file search context is needed for this question"""
        try:
            # We must use .ainvoke for async, and must not use format="json" for this simple YES/NO route
            # Temporarily create a non-json LLM instance for routing
            non_json_llm = self.llm.with_config({"format": "text"})
            routing_chain = self.routing_prompt | non_json_llm | StrOutputParser()
            
            decision = await routing_chain.ainvoke({"question": question})
            decision_clean = decision.strip().upper()
            return "YES" in decision_clean
        except Exception as e:
            print(f"Error in file search routing: {e}")
            return False

    def _build_deterministic_plan(self, question: str) -> Optional[Dict[str, Any]]:
        normalized_question = " ".join(str(question or "").lower().split())
        file_name = _extract_exact_filename(question)
        if not file_name:
            return None

        if not any(hint in normalized_question for hint in _DIRECT_FILE_ACTION_HINTS):
            return None

        base_path_key = "application" if _mentions_project_home_scope(question) else None
        return {
            "action": "show",
            "show": {
                "file_name": file_name,
                "base_path_key": base_path_key,
                "include_hidden": False,
            },
        }

    async def plan_file_search(self, question: str):
        """Use LLM to generate a JSON plan for file searching"""
        planning_chain = self.planning_prompt | self.llm | StrOutputParser()
        try:
            ai_raw = await planning_chain.ainvoke({"query": question})
            
            # Parse JSON robustly
            plan: Dict[str, Any]
            try:
                plan = json.loads(ai_raw)
                return plan
            except Exception:
                start = ai_raw.find('{')
                end = ai_raw.rfind('}')
                if start != -1 and end != -1 and end > start:
                    try:
                        plan = json.loads(ai_raw[start:end+1])
                        return plan
                    except Exception:
                        pass
                # Fallback if JSON is truly broken
                print(f"--- [FileSearchRAGChain]: Failed to parse LLM JSON plan. Raw output: {ai_raw}")
                return {"action": "answer", "answer": ai_raw}
        except Exception as e:
            print(f"Error in file search planning: {e}")
            return {"action": "clarify", "clarify": "I had trouble understanding that file request."}

    async def fetch_files_context(self, plan: Dict[str, Any]):
        """Execute the gRPC call based on the plan and format the results.

        Robust behavior:
        - If the original question contains an explicit Windows path and filename,
          resolve that file directly only when it stays inside allowed paths.
          Otherwise, reject immediately.
        - Otherwise, fall back to the LLM-generated plan (search/show/answer/clarify).
        """
        files_context = ""
        multi_turn_enabled = bool(plan.get("__multi_turn_enabled", False))

        # --- 0. Direct path resolution from the original question (if available) ---
        raw_question = str(plan.get("__question", "") or "")
        if raw_question:
            try:
                # Heuristic 1: Extract a Windows-like path (e.g., C:\Users\...\SomeDir\)
                path_match = re.search(r"[A-Za-z]:\\[^\r\n'\"]*", raw_question)
                # Heuristic 2: Extract a candidate filename with extension (e.g., LICENSE.txt)
                fname_match = re.search(r"\b[\w\-]+\.[A-Za-z0-9]+\b", raw_question)

                candidate_path = None
                if path_match and fname_match:
                    dir_part = path_match.group(0).strip().strip("'\"")
                    filename = fname_match.group(0).strip().strip("'\"")
                    dir_part = os.path.normpath(dir_part)
                    candidate_path = os.path.realpath(os.path.abspath(os.path.join(dir_part, filename)))

                if candidate_path and not is_path_allowed(candidate_path):
                    return REJECTION_MESSAGE

                # If we can resolve a real file on disk from the question, use it directly.
                if candidate_path and os.path.isfile(candidate_path):
                    try:
                        return _render_file_context(
                            candidate_path,
                            header="File resolved directly from user-specified path:",
                            max_chars=100000,
                        )
                    except Exception as e:
                        files_context = (
                            f"[WARNING] Failed to read file directly from '{candidate_path}': {e}\n"
                        )

            except Exception:
                # Never block the normal flow on heuristic failure
                pass

        # --- 1. Normal plan-driven behavior (search/show/answer/clarify) ---
        action = (plan.get("action") or "").lower()
        try:
            if action == "list_dirs":
                allowed_dirs = await self.async_call_grpc_list_dirs()
                if not allowed_dirs:
                    files_context = "No allowed directories found or failed to retrieve them."
                else:
                    files_context = "Allowed Directories:\n"
                    for key, path in allowed_dirs.items():
                        files_context += f"- {key}: {path}\n"
            
            elif action == "search" or action == "show":
                args = plan.get("search") or plan.get("show") or {}
                
                # For 'show', the pattern is the exact filename
                file_pattern = args.get("file_pattern") or args.get("file_name")
                base_key = args.get("base_path_key")
                include_hidden = bool(args.get("include_hidden", False))

                # Validate
                if not file_pattern:
                    return "File search plan was missing a file_pattern or file_name."
                if base_key is not None and base_key not in ALLOWED_KEYS:
                    return f"File search plan had an invalid base_path_key: {base_key}."

                if (
                    multi_turn_enabled
                    and
                    action == "show"
                    and base_key == "application"
                    and file_pattern == os.path.basename(file_pattern)
                ):
                    direct_candidate = os.path.realpath(
                        os.path.abspath(os.path.join(_get_application_root(), file_pattern))
                    )
                    if is_path_allowed(direct_candidate) and os.path.isfile(direct_candidate):
                        return _render_file_context(
                            direct_candidate,
                            header="File resolved directly from the application root:",
                        )

                # Fetch files (paths only) via gRPC
                files_list = await self.async_call_grpc_server(
                    file_pattern=file_pattern,
                    base_key=base_key,
                    hidden=include_hidden
                )

                validated_files_list = []
                for found_path in files_list:
                    resolved_found_path = os.path.realpath(os.path.abspath(found_path))
                    if not is_path_allowed(resolved_found_path):
                        return REJECTION_MESSAGE
                    validated_files_list.append(resolved_found_path)
                files_list = validated_files_list

                # Format context
                if not files_list:
                    files_context = f"No files found matching '{file_pattern}'."
                else:
                    total = len(files_list)
                    if action == "show":
                        raw_question = str(plan.get("__question", ""))  # may contain a full or partial path
                        target_path: Optional[str] = None

                        # 1) If there's exactly one match, that's our target.
                        if total == 1:
                            target_path = files_list[0]
                        else:
                            if multi_turn_enabled and base_key == "application":
                                application_root = os.path.realpath(os.path.abspath(_get_application_root()))
                                root_level_match = os.path.join(application_root, file_pattern)
                                root_level_match = os.path.realpath(os.path.abspath(root_level_match))
                                if root_level_match in files_list:
                                    target_path = root_level_match

                            # 2) Try to disambiguate using the original question text:
                            #    pick the first candidate whose full path appears in the question.
                            if target_path is None:
                                q_lower = raw_question.lower()
                                for candidate in files_list:
                                    if candidate.lower() in q_lower:
                                        target_path = candidate
                                        break

                        if target_path:
                            target_path = os.path.realpath(os.path.abspath(target_path))
                            if not is_path_allowed(target_path):
                                return REJECTION_MESSAGE
                            try:
                                if multi_turn_enabled:
                                    files_context = f"Requested file resolved:\n{target_path}"
                                    if total > 1:
                                        files_context += (
                                            "\n"
                                            f"Additional matches with the same name in the selected scope: {total - 1}."
                                        )
                                    rendered = _render_file_context(
                                        target_path,
                                        header="",
                                    )
                                    _, separator, remainder = rendered.partition("\n\n")
                                    files_context += f"\n\n{remainder or rendered}"
                                else:
                                    mime, _ = mimetypes.guess_type(target_path)
                                    ext = os.path.splitext(target_path)[1].lower()
                                    is_text_like = False
                                    if mime and mime.startswith('text/'):
                                        is_text_like = True
                                    elif ext in {'.txt', '.md', '.py', '.json', '.xml', '.html', '.css', '.js', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.csv', '.tsv', '.svg'}:
                                        is_text_like = True

                                    max_files_in_context = 20
                                    files_to_show = files_list[:max_files_in_context]
                                    files_context = f"Found {total} files matching '{file_pattern}':\n"
                                    files_context += "\n".join(f"- {f}" for f in files_to_show)
                                    if total > max_files_in_context:
                                        files_context += f"\n... and {total - max_files_in_context} more."

                                    if is_text_like:
                                        try:
                                            with open(target_path, "r", encoding="utf-8", errors="replace") as f:
                                                content = f.read()
                                            max_chars = 500000
                                            if len(content) > max_chars:
                                                content = content[:max_chars] + "\n… [truncated]"
                                            files_context += (
                                                "\n\nFull content of the file:\n"
                                                f"<FILE_CONTENT_START>\n{content}\n<FILE_CONTENT_END>\n"
                                            )
                                        except Exception as e:
                                            files_context += f"\n\n[WARNING] Failed to read text content for '{target_path}': {e}"
                                    else:
                                        files_context += (
                                            "\n\n[INFO] The requested file appears to be binary (e.g., image/video). "
                                            "Content is not embedded in context to avoid corruption or token bloat.\n"
                                            f"Suggested action: use the tool 'launch_view_image' with path '{target_path}'."
                                        )
                            except Exception as e:
                                files_context += f"\n\n[WARNING] Failed to process target file '{target_path}': {e}"
                        else:
                            max_files_in_context = 8 if multi_turn_enabled else 20
                            files_to_show = files_list[:max_files_in_context]
                            if multi_turn_enabled:
                                files_context = (
                                    f"Multiple files matched '{file_pattern}' and the intended file could not be resolved:\n"
                                )
                            else:
                                files_context = f"Found {total} files matching '{file_pattern}':\n"
                            files_context += "\n".join(f"- {f}" for f in files_to_show)
                            if total > max_files_in_context:
                                files_context += f"\n... and {total - max_files_in_context} more."
                    else:
                        max_files_in_context = 20
                        files_to_show = files_list[:max_files_in_context]
                        files_context = f"Found {total} files matching '{file_pattern}':\n"
                        files_context += "\n".join(f"- {f}" for f in files_to_show)
                        if total > max_files_in_context:
                            files_context += f"\n... and {total - max_files_in_context} more."
            
            elif action == "answer":
                files_context = f"File search was not needed. LLM Answer: {plan.get('answer', 'N/A')}"
            
            elif action == "clarify":
                files_context = f"File search was not possible. LLM Clarification: {plan.get('clarify', 'N/A')}"
            
            else:
                files_context = f"Unknown file search action: {action}"

            return files_context

        except Exception as e:
            print(f"Error executing file search plan: {e}")
            return f"An error occurred during the file search: {e}"
    
    async def intelligent_context_fetch(self, input_data: dict):
        """
        Intelligently decide whether to fetch file context,
        then plan and execute the search.
        """
        question = input_data.get('question', '')
        multi_turn_enabled = bool(input_data.get('multi_turn_enabled', False))
        deterministic_plan = self._build_deterministic_plan(question) if multi_turn_enabled else None
        if deterministic_plan is not None:
            print(f"[INFO] Using deterministic file plan for question: {question}")
            deterministic_plan["__question"] = question
            deterministic_plan["__multi_turn_enabled"] = multi_turn_enabled
            files_context = await self.fetch_files_context(deterministic_plan)
            return {**input_data, "files_context": files_context or ""}
        
        # 1. Route
        needs_context = await self.should_fetch_files_context(question)
        
        if not needs_context:
            print(f"[INFO] No file search context needed for question: {question}")
            return {**input_data, "files_context": ""}
        
        print(f"[INFO] Fetching file search context for question: {question}")
        
        # 2. Plan
        plan = await self.plan_file_search(question)
        
        # 3. Fetch (pass original question through the plan for disambiguation)
        plan["__question"] = question
        plan["__multi_turn_enabled"] = multi_turn_enabled
        files_context = await self.fetch_files_context(plan)
        
        return {**input_data, "files_context": files_context or ""}

    async def run(self, question: str):
        """Standalone run method for testing"""
        result_dict = await self.intelligent_context_fetch({"question": question})
        
        # Create a final answer prompt for testing
        final_prompt = PromptTemplate.from_template(
            "File Search Context:\n{files_context}\n\nSystem Context:\n(Not provided)\n\nLocal RAG Context:\n(Not provided)\n\nQuestion: {question}\n\nAnswer based on all available context:"
        )
        
        # Use a non-JSON LLM for the final answer
        non_json_llm = self.llm.with_config({"format": "text"})
        final_chain = final_prompt | non_json_llm | StrOutputParser()
        
        answer = await final_chain.ainvoke(result_dict)
        return answer

# Example usage
async def main():
    chain = FileSearchRAGChain()
    
    questions = [
        "what is a python file?",
        "find all *.py files in docs",
        "show me the 'README.md' file",
        "list all files"
    ]
    
    for question in questions:
        print("\n--- Running Test Question ---")
        print(f"Question: {question}")
        try:
            answer = await chain.run(question)
            print(f"Answer: {answer}")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
