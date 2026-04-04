import os
import sys
from asgiref.sync import async_to_sync
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_ollama import OllamaLLM, OllamaEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from ..global_state import global_state
from agent.rag_enhancements import enrich_documents_with_metadata, get_project_summary
from .config import load_config_and_prompt
from .loaders import report_oversized_docs
from .splitters import get_text_splitter
from .prompts import get_contextualize_q_prompt
from .chains.basic import BasicPromptOnlyChain
from .chains.history_aware import HistoryAwareNoDocsChain, OptimizedHistoryAwareRAGChain
from .chains.unified import UnifiedAgentChain, UnifiedAgentRAGChain
from .utils import _pack_context, _unique_filenames_from_split

# Try to import SystemRAGChain for system resource integration
try:
    from ..chain_system_lcel import SystemRAGChain
except (ImportError, ModuleNotFoundError):
    # Fallback for legacy path
    try:
        from ..applications.chain_system_lcel import SystemRAGChain
    except (ImportError, ModuleNotFoundError) as e:
        SystemRAGChain = None
        print(f"Warning: SystemRAGChain not available: {e}")

# Try to import FileSearchRAGChain for file search integration
try:
    from ..chain_files_search_lcel import FileSearchRAGChain
except (ImportError, ModuleNotFoundError) as e:
    FileSearchRAGChain = None
    print(f"Warning: FileSearchRAGChain not available: {e}")

try:
    from langchain_community.retrievers import BM25Retriever
except Exception:
    BM25Retriever = None

if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
else:
    application_path = os.path.dirname(os.path.abspath(__file__))
    # Go up one level to get to the root of the agent app
    application_path = os.path.dirname(application_path)

# Helper functions for context fetching
def get_system_context_sync(payload):
    """Synchronously fetch system context using SystemRAGChain."""
    if SystemRAGChain is None:
        return payload
    
    try:
        # Instantiate chain (could be optimized to reuse instance)
        chain = SystemRAGChain()
        # Wrap async call
        async_fetch = async_to_sync(chain.intelligent_context_fetch)
        # Call with payload (expects 'question' key, payload has 'input')
        input_data = {"question": payload.get("input", "")}
        result = async_fetch(input_data)
        
        # Merge result into payload
        # SystemRAGChain returns {'context': ..., 'question': ...}
        # We want to add 'system_context' to payload
        new_payload = payload.copy()
        new_payload["system_context"] = result.get("context", "")
        return new_payload
    except Exception as e:
        print(f"Error fetching system context: {e}")
        return payload

def get_files_context_sync(payload):
    """Synchronously fetch files context using FileSearchRAGChain."""
    if FileSearchRAGChain is None:
        return payload
    
    try:
        chain = FileSearchRAGChain()
        async_fetch = async_to_sync(chain.intelligent_context_fetch)
        input_data = {"question": payload.get("input", "")}
        result = async_fetch(input_data)
        
        # FileSearchRAGChain returns {..., 'files_context': ...}
        new_payload = payload.copy()
        new_payload["files_context"] = result.get("files_context", "")
        return new_payload
    except Exception as e:
        print(f"Error fetching files context: {e}")
        return payload


def _build_loaded_documents_fallback_context(documents, config):
    if not documents:
        return ""

    try:
        docs_list = list(documents)
    except TypeError:
        docs_list = [documents]

    docs_list = [doc for doc in docs_list if getattr(doc, "page_content", None)]
    if not docs_list:
        return ""

    max_ctx_chars = int(config.get("max_context_chars", 24000))
    redact = bool(config.get("redact_secrets_in_context", False))
    use_hierarchical = bool(config.get("retrieval_strategy", {}).get("enable_hierarchical_context", True))

    try:
        packed_context = _pack_context(docs_list, max_ctx_chars, redact, use_hierarchical)
    except Exception as exc:
        print(f"Warning: failed to build loaded-documents fallback context ({exc})")
        return ""

    manifest = _unique_filenames_from_split(docs_list)
    if manifest:
        manifest_block = "FILE MANIFEST (loaded files):\n" + "\n".join(f"- {name}" for name in manifest)
        if packed_context:
            return f"{manifest_block}\n\n{packed_context}"
        return manifest_block

    return packed_context

def build_prompt_only_chain(config, prompt_template_string, documents=None):
    """Builds a simple prompt-only chain with the same interface as the retrieval chain."""
    token = config.get('ollama_token')
    client_kwargs = {'headers': {'Authorization': f'Bearer {token}'}} if token else {}

    stop_tokens = [
        "<|endoftext|>", "<|im_start|>", "<|im_end|>",
        "\nHuman:", "\nUser:", "\nAssistant:", "\nSystem:", "\nAI:",
        "\nEND-RESPONSE\n"
    ]

    llm = OllamaLLM(
        model=config.get('chained-model'),
        base_url=config.get('ollama_base_url'),
        streaming=True,
        stop=stop_tokens,
        temperature=0.0,
        top_k=20,
        top_p=0.8,
        repeat_penalty=1.9,
        thinking=True,
        context_window=128000,
        handle_parsing_errors=True,
        client_kwargs=client_kwargs
    )

    if llm is None:
        print("Error: LLM model not found or Ollama is not running.")
        return None

    ollama_client_instance = llm._client
    print(f"Found ollama.Client: {ollama_client_instance}")
    httpx_client_instance = ollama_client_instance._client
    print(f"Found httpx.Client: {httpx_client_instance}")
   
    history_summary_cfg = {
        "enable": bool(config.get("history_summary_enable", False)),
        "trigger_tokens": int(config.get("history_summary_trigger_tokens", 800)),
        "keep_last_turns": int(config.get("history_keep_last_turns", 6)),
    }

    loaded_context = _build_loaded_documents_fallback_context(documents, config)
    if loaded_context:
        print(f"--- Loaded-documents fallback context prepared ({len(loaded_context)} chars) ---")

    contextualize_q_prompt = get_contextualize_q_prompt()

    # Create unified prompt that supports all contexts
    final_qa_prompt = ChatPromptTemplate.from_messages([
        ("system", prompt_template_string),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        ("system", "Apply all of the Rules only to the **CURRENT** human input ({input}); ignore chat_history for all of the Rules.")
    ])
    
    if SystemRAGChain is not None:
        print("[SystemRAGChain] Integration enabled - system context will be fetched when needed")
    else:
        print("[SystemRAGChain] Integration disabled - SystemRAGChain not available")
    
    if FileSearchRAGChain is not None:
        print("[FileSearchRAGChain] Integration enabled - file search context will be fetched when needed")
    else:
        print("[FileSearchRAGChain] Integration disabled - FileSearchRAGChain not available")

    use_unified_agent = bool(config.get("enable_unified_agent", False))
    
    if use_unified_agent:
        print("--- UnifiedAgentChain: Building tool-enabled chain ---")
        chain = UnifiedAgentChain(llm, prompt_template_string, history_summary_cfg, loaded_context=loaded_context)
    else:
        chain = BasicPromptOnlyChain(
            llm,
            contextualize_q_prompt,
            final_qa_prompt,
            prompt_template_string,
            history_summary_cfg
            ,loaded_context=loaded_context
        )
    
    chain.setHttpxClientInstance(httpx_client_instance)

    # Add system context preprocessing to the chain
    if SystemRAGChain is not None or FileSearchRAGChain is not None:
        original_invoke = chain.invoke

        def invoke_with_system_context(payload: dict):
            if SystemRAGChain is not None and global_state.get_state('mcp_system_status') == 'enabled':
                print("--- [SystemRAGChain] Integration enabled - system context will be fetched when needed")
                enhanced_payload = get_system_context_sync(payload)
            else:
                print("--- [SystemRAGChain] **WARNING(1)** Integration disabled - SystemRAGChain not available")
                enhanced_payload = payload
            
            if FileSearchRAGChain is not None and global_state.get_state('mcp_files_search_status') == 'enabled':
                print("--- [FileSearchRAGChain] Integration enabled - file search context will be fetched when needed")
                enhanced_payload = get_files_context_sync(enhanced_payload)
            else:
                print("--- [FileSearchRAGChain] **WARNING(1)** Integration disabled - FileSearchRAGChain not available")
                enhanced_payload = enhanced_payload
            
            return original_invoke(enhanced_payload)            

        chain.invoke = invoke_with_system_context

    return chain

def build_retrieval_chain(documents, config, prompt_template_string):
    """Builds the retrieval chain."""
    print("Building retrieval chain...")

    try:
        token = config.get('ollama_token')
        client_kwargs = {'headers': {'Authorization': f'Bearer {token}'}} if token else {}

        stop_tokens = [
            "<|endoftext|>", "<|im_start|>", "<|im_end|>",
            "\nHuman:", "\nUser:", "\nAssistant:", "\nSystem:", "\nAI:",
            "\nEND-RESPONSE\n"
        ]

        llm = OllamaLLM(
            model=config.get('chained-model'),
            base_url=config.get('ollama_base_url'),
            streaming=True,
            stop=stop_tokens,
            temperature=0.0,
            top_k=20,
            top_p=0.8,
            repeat_penalty=1.9,
            thinking=True,
            context_window=128000,
            handle_parsing_errors=True,
            client_kwargs=client_kwargs
        )

        if llm is None:
            print("Error: LLM model not found or Ollama is not running.")
            return None

        ollama_client_instance = llm._client
        print(f"Found ollama.Client: {ollama_client_instance}")
        httpx_client_instance = ollama_client_instance._client
        print(f"Found httpx.Client: {httpx_client_instance}")

        contextualize_q_prompt = get_contextualize_q_prompt()

        has_docs = True
        docs_list = []
        split_docs = []

        if documents is None:
            has_docs = False
        else:
            try:
                docs_list = list(documents)
            except TypeError:
                docs_list = [documents]
            docs_list = [d for d in docs_list if getattr(d, "page_content", None)]
            if not docs_list:
                has_docs = False

        if has_docs:
            chunk_size = int(config.get("chunk_size", 500))
            chunk_overlap = int(config.get("chunk_overlap", 100))
            text_splitter = get_text_splitter(chunk_size, chunk_overlap)

            try:
                split_docs = text_splitter.split_documents(docs_list)
            except Exception as e:
                print(f"Warning: failed to split documents ({e}); falling back to no-docs contextual chain.")
                split_docs = []

            if not split_docs:
                has_docs = False

        history_summary_cfg = {
            "enable": bool(config.get("history_summary_enable", False)),
            "trigger_tokens": int(config.get("history_summary_trigger_tokens", 800)),
            "keep_last_turns": int(config.get("history_keep_last_turns", 6)),
        }

        if not has_docs:
            final_qa_prompt = ChatPromptTemplate.from_messages([
                ("system", prompt_template_string),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
                ("system", "Apply all of the Rules only to the **CURRENT** human input ({input}); ignore chat_history for all of the Rules.")
            ])
            
            if SystemRAGChain is not None:
                print("[SystemRAGChain] Integration enabled - system context will be fetched when needed")
            else:
                print("[SystemRAGChain] Integration disabled - SystemRAGChain not available")
            
            if FileSearchRAGChain is not None:
                print("[FileSearchRAGChain] Integration enabled - file search context will be fetched when needed")
            else:
                print("[FileSearchRAGChain] Integration disabled - FileSearchRAGChain not available")

            use_unified_agent = bool(config.get("enable_unified_agent", False))
            
            if use_unified_agent:
                print("--- UnifiedAgentChain: Building tool-enabled chain (no docs path) ---")
                chain = UnifiedAgentChain(llm, prompt_template_string, history_summary_cfg)
            else:
                chain = HistoryAwareNoDocsChain(
                    llm, 
                    contextualize_q_prompt, 
                    final_qa_prompt,
                    history_summary_cfg
                )
            
            chain.setHttpxClientInstance(httpx_client_instance)

            if SystemRAGChain is not None or FileSearchRAGChain is not None:
                original_invoke = chain.invoke

                def invoke_with_system_context(payload: dict):
                    if SystemRAGChain is not None and global_state.get_state('mcp_system_status') == 'enabled':
                        print("--- [SystemRAGChain] Integration enabled - system context will be fetched when needed")
                        enhanced_payload = get_system_context_sync(payload)
                    else:
                        print("--- [SystemRAGChain] **WARNING(2)** Integration disabled - SystemRAGChain not available")
                        enhanced_payload = payload
                    
                    if FileSearchRAGChain is not None and global_state.get_state('mcp_files_search_status') == 'enabled':
                        print("--- [FileSearchRAGChain] Integration enabled - file search context will be fetched when needed")
                        enhanced_payload = get_files_context_sync(enhanced_payload)
                    else:
                        print("--- [FileSearchRAGChain] **WARNING(2)** Integration disabled - FileSearchRAGChain not available")
                        enhanced_payload = enhanced_payload
                    
                    return original_invoke(enhanced_payload)

                chain.invoke = invoke_with_system_context
            return chain

        embeddings = OllamaEmbeddings(
            model=config.get('embeding-model'),
            base_url=config.get('ollama_base_url'),
            client_kwargs=client_kwargs
        )
        if embeddings is None:
            print("Error: Embeddings model not found or Ollama is not running.")
            return None

        vector_store = FAISS.from_documents(split_docs, embeddings)

        bm25 = None
        if bool(config.get("enable_bm25", False)) and BM25Retriever is not None:
            try:
                bm25 = BM25Retriever.from_documents(split_docs)
            except Exception:
                bm25 = None

        # Helper to safely get nested config values
        def get_cfg(key, default, parent_key=None):
            if parent_key and parent_key in config and isinstance(config[parent_key], dict):
                return config[parent_key].get(key, default)
            return config.get(key, default)

        retrieval_cfg = {
            "use_mmr": bool(config.get("use_mmr", True)),
            "k_vector": int(config.get("k_vector", 8)),
            "fetch_k": int(config.get("fetch_k", 32)),
            "mmr_lambda": float(config.get("mmr_lambda", 0.5)),
            "k_bm25": int(config.get("k_bm25", 8)),
            "rrf_k": int(config.get("rrf_k", 60)),
            "k_fused": int(config.get("k_fused", 10)),
            "max_chunks_per_file": int(config.get("max_chunks_per_file", 1)),
            
            # Read from retrieval_strategy section or fall back to root
            "enable_multi_stage": bool(get_cfg("enable_multi_stage", False, "retrieval_strategy")),
            "enable_query_expansion": bool(get_cfg("enable_query_expansion", False, "retrieval_strategy")),
            "enable_context_budget_allocation": bool(get_cfg("enable_context_budget_allocation", False, "retrieval_strategy")),
            "enable_hierarchical_context": bool(get_cfg("enable_hierarchical_context", True, "retrieval_strategy")),
            
            # Always enable cross references if not specified
            "enable_cross_references": bool(get_cfg("enable_cross_references", True, "metadata_extraction"))
        }

        compression_cfg = {
            "use_llm_extractor": bool(config.get("use_llm_extractor", True)),
            "use_embeddings_filter": bool(config.get("use_embeddings_filter", False)),
            "use_long_context_reorder": bool(config.get("use_long_context_reorder", True)),
            "max_doc_chars": int(config.get("max_doc_chars", 8000)),
            "max_context_chars": int(config.get("max_context_chars", 24000)),
            "redact_secrets_in_context": bool(config.get("redact_secrets_in_context", False))
        }

        final_prompt_string = prompt_template_string
        
        if SystemRAGChain is not None:
            print("[SystemRAGChain] Integration enabled - system context will be fetched when needed")
        else:
            print("[SystemRAGChain] Integration disabled - SystemRAGChain not available")
        
        if FileSearchRAGChain is not None:
            print("[FileSearchRAGChain] Integration enabled - file search context will be fetched when needed")
        else:
            print("[FileSearchRAGChain] Integration disabled - FileSearchRAGChain not available")

        use_unified_agent = bool(config.get("enable_unified_agent", False))
        
        if use_unified_agent:
            print("--- UnifiedAgentRAGChain: Building tool-enabled RAG chain ---")
            chain = UnifiedAgentRAGChain(
                llm=llm,
                prompt_template_string=final_prompt_string,
                contextualize_q_prompt=contextualize_q_prompt,
                vector_store=vector_store,
                split_docs=split_docs,
                retrieval_cfg=retrieval_cfg,
                compression_cfg=compression_cfg,
                history_summary_cfg=history_summary_cfg,
                bm25=bm25,
            )
        else:
            chain = OptimizedHistoryAwareRAGChain(
                llm=llm,
                prompt_template_string=final_prompt_string,
                contextualize_q_prompt=contextualize_q_prompt,
                vector_store=vector_store,
                split_docs=split_docs,
                retrieval_cfg=retrieval_cfg,
                compression_cfg=compression_cfg,
                history_summary_cfg=history_summary_cfg,
                bm25=bm25,
            )
        
        chain.setHttpxClientInstance(httpx_client_instance)

        if SystemRAGChain is not None or FileSearchRAGChain is not None:
            original_invoke = chain.invoke

            def invoke_with_system_context(payload: dict):
                if SystemRAGChain is not None and global_state.get_state('mcp_system_status') == 'enabled':
                    print("--- [SystemRAGChain] Integration enabled - system context will be fetched when needed")
                    enhanced_payload = get_system_context_sync(payload)
                else:
                    print("--- [SystemRAGChain] **WARNING(3)** Integration disabled - SystemRAGChain not available")
                    enhanced_payload = payload
                
                if FileSearchRAGChain is not None and global_state.get_state('mcp_files_search_status') == 'enabled':
                    print("--- [FileSearchRAGChain] Integration enabled - file search context will be fetched when needed")
                    enhanced_payload = get_files_context_sync(enhanced_payload)
                else:
                    print("--- [FileSearchRAGChain] **WARNING(3)** Integration disabled - FileSearchRAGChain not available")
                    enhanced_payload = enhanced_payload
                
                return original_invoke(enhanced_payload)

            chain.invoke = invoke_with_system_context
        return chain

    except Exception as e:
        print(f"Error: {e}")
        return None

class CustomTextLoader(TextLoader):
    def __init__(self, file_path, encoding=None, autodetect_encoding=False, exclusions=None):
        if exclusions:
            base_name = os.path.basename(file_path)
            # Check for exact filename matches
            if base_name in exclusions.get('filenames', []):
                raise ValueError(f"File {base_name} is excluded by filename.")
            # Check for extension matches
            for ext in exclusions.get('extensions', []):
                if base_name.endswith(ext):
                    raise ValueError(f"File {base_name} is excluded by extension {ext}.")
        
        super().__init__(file_path, encoding=encoding, autodetect_encoding=autodetect_encoding)

def setup_llm_with_context(path_only, agents=None, mcps=None, tools=None, omissions=None, filename=None):
    global_state.set_state('rag_chain_ready', False)
    
    if agents is not None:
        for agent in agents:
            descr = agent.get('agentDescription')
            content = agent.get('agentContent')
            global_state.set_state('agent_'+descr.lower()+'_status', 'enabled' if content == 'true' else 'disabled')
            print(f"--- Agent: {descr} [agent_{descr.lower()}_status] - Status: {global_state.get_state('agent_'+descr.lower()+'_status')}")

    if mcps is not None:
        system_enabled = any(
            (m.get('mcpDescription') == 'System-Metrics' and m.get('mcpContent') == 'true')
            for m in mcps
        )
        files_enabled = any(
            (m.get('mcpDescription') == 'Files-Search' and m.get('mcpContent') == 'true')
            for m in mcps
        )
        global_state.set_state('mcp_system_status', 'enabled' if system_enabled else 'disabled')
        global_state.set_state('mcp_files_search_status', 'enabled' if files_enabled else 'disabled')
    print(f"--- MCP: System-Metrics - Status: {global_state.get_state('mcp_system_status')}")
    print(f"--- MCP: Files-Search - Status: {global_state.get_state('mcp_files_search_status')}")

    if tools is not None:
        for tool in tools:
            descr = tool.get('toolDescription')
            content = tool.get('toolContent')
            global_state.set_state('tool_'+descr.lower()+'_status', 'enabled' if content == 'true' else 'disabled')
            print(f"--- Tool: {descr} [tool_{descr.lower()}_status] - Status: {global_state.get_state('tool_'+descr.lower()+'_status')}")

    # Parse omissions
    default_excluded_filenames = ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb']
    excluded_filenames = list(default_excluded_filenames)
    excluded_extensions = []
    if omissions:
        for o in omissions.split(','):
            o = o.strip()
            if o.startswith('*.'):
                excluded_extensions.append(o[1:]) # Remove '*' to get '.doc'
            else:
                excluded_filenames.append(o)
    
    exclusions = {
        'filenames': excluded_filenames,
        'extensions': excluded_extensions
    }

    print("--- Loading all files with exclusions:")
    if excluded_filenames:
        print(f"--- Excluded filenames: {excluded_filenames}")
    if excluded_extensions:
        print(f"--- Excluded extensions: {['*' + ext for ext in excluded_extensions]}")

    config, prompt_template, _ = load_config_and_prompt(application_path)
    oversizedDocs = False

    if os.path.exists(path_only):
        if os.path.isdir(path_only) and filename is None:
            print(f"--- Detected directory path: {path_only}")
            print("--- Scanning for documents (excluding specified patterns)...")
            loader = DirectoryLoader(
                path_only,
                glob="**/*",
                recursive=True,
                use_multithreading=True,
                max_concurrency=12,
                load_hidden=bool(config.get("load_hidden", True)),
                show_progress=True,
                loader_cls=CustomTextLoader,
                loader_kwargs={
                    "autodetect_encoding": True,
                    "exclusions": exclusions
                },
                silent_errors=True
            )
            documents = loader.load() if loader else None
            if documents:
                oversizedDocs = report_oversized_docs(documents, int(config.get("max_doc_chars", 8000)))
        elif filename is not None and os.path.isfile(os.path.join(path_only, filename)):
            print(f"--- Loading specific file: {os.path.join(path_only, filename)}")
            print("--- Processing single document for context...")
            loader = DirectoryLoader(
                path_only,
                glob=filename,
                recursive=False,
                use_multithreading=False,
                load_hidden=bool(config.get("load_hidden", True)),
                show_progress=True,
                loader_cls=CustomTextLoader,
                loader_kwargs={
                    "autodetect_encoding": True,
                    "exclusions": exclusions
                },
                silent_errors=True
            )
            documents = loader.load() if loader else None
            if documents:
                oversizedDocs = report_oversized_docs(documents, int(config.get("max_doc_chars", 8000)))
        else:
            print(f"--- Error: Target path '{os.path.join(path_only, (filename or ''))}' is not accessible.")
            print("--- Please verify the file path and permissions.")
            return None
    else:
        print(f"--- Error: Source path '{path_only}' does not exist.")
        print("--- Please check the path and try again.")
        return None

    if documents:
        for doc in documents:
            full_path = doc.metadata["source"]
            doc.metadata["filename"] = os.path.basename(full_path)
            doc.metadata["file_extension"] = os.path.splitext(full_path)[1]
            doc.metadata["directory"] = os.path.dirname(full_path)
            try:
                doc.metadata["file_size"] = os.path.getsize(full_path)
                doc.metadata["last_modified_at"] = os.path.getmtime(full_path)
                doc.metadata["created_at"] = os.path.getctime(full_path)
            except Exception:
                pass
        print("--- Enriching documents with metadata...")
        all_file_paths = [doc.metadata.get('source', '') for doc in documents]
        documents = enrich_documents_with_metadata(documents, all_file_paths)
    
        project_summary = get_project_summary(documents)
        print(f"--- Project summary: {project_summary['total_files']} files, "
              f"{project_summary['total_lines']} lines across "
              f"{len(project_summary['file_types'])} file types")

    print(f"--- Document loading status: {'No documents loaded' if documents is None else f'{len(documents)} documents loaded successfully'}")
    retrieval_chain = build_retrieval_chain(documents, config, prompt_template)
    if retrieval_chain is None:
        print("Error: RAG chain not built successfully; falling back to prompt-only mode.")
        prompt_only_chain = build_prompt_only_chain(config, prompt_template, documents=documents)
        if prompt_only_chain is None:
            return None
        print("--- Prompt-only chain ready (loaded-documents fallback mode).")
        global_state.set_state('rag_chain_ready', True)
        return prompt_only_chain
    if isinstance(retrieval_chain, (OptimizedHistoryAwareRAGChain, UnifiedAgentRAGChain)):
        retrieval_chain.setDetectedOversizedDocs(bool(oversizedDocs))
    global_state.set_state('rag_chain_ready', True)
    return retrieval_chain

def setup_llm(agents=None, mcps=None, tools=None, omissions=None):
    global_state.set_state('rag_chain_ready', False)

    if agents is not None:
        for agent in agents:
            descr = agent.get('agentDescription')
            content = agent.get('agentContent')
            global_state.set_state('agent_'+descr.lower()+'_status', 'enabled' if content == 'true' else 'disabled')
            print(f"--- Agent: {descr} [agent_{descr.lower()}_status] - Status: {global_state.get_state('agent_'+descr.lower()+'_status')}")

    if mcps is not None:
        system_enabled = any(
            (m.get('mcpDescription') == 'System-Metrics' and m.get('mcpContent') == 'true')
            for m in mcps
        )
        files_enabled = any(
            (m.get('mcpDescription') == 'Files-Search' and m.get('mcpContent') == 'true')
            for m in mcps
        )
        global_state.set_state('mcp_system_status', 'enabled' if system_enabled else 'disabled')
        global_state.set_state('mcp_files_search_status', 'enabled' if files_enabled else 'disabled')
    print(f"--- MCP: System-Metrics - Status: {global_state.get_state('mcp_system_status')}")
    print(f"--- MCP: Files-Search - Status: {global_state.get_state('mcp_files_search_status')}")

    if tools is not None:
        for tool in tools:
            descr = tool.get('toolDescription')
            content = tool.get('toolContent')
            global_state.set_state('tool_'+descr.lower()+'_status', 'enabled' if content == 'true' else 'disabled')
            print(f"--- Tool: {descr} [tool_{descr.lower()}_status] - Status: {global_state.get_state('tool_'+descr.lower()+'_status')}")

    # Parse omissions
    default_excluded_filenames = ['package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb']
    excluded_filenames = list(default_excluded_filenames)
    excluded_extensions = []
    if omissions:
        for o in omissions.split(','):
            o = o.strip()
            if o.startswith('*.'):
                excluded_extensions.append(o[1:]) # Remove '*' to get '.doc'
            else:
                excluded_filenames.append(o)
    
    exclusions = {
        'filenames': excluded_filenames,
        'extensions': excluded_extensions
    }

    print("--- Loading all files with exclusions:")
    if excluded_filenames:
        print(f"--- Excluded filenames: {excluded_filenames}")
    if excluded_extensions:
        print(f"--- Excluded extensions: {['*' + ext for ext in excluded_extensions]}")

    config, prompt_template, _ = load_config_and_prompt(application_path)
    application_context_path = os.path.join(application_path, 'application')
    oversizedDocs = False

    if os.path.isdir(application_context_path):
        print(f"The directory '{application_context_path}' exists.\nLoading documents (excluding specified patterns)...")
        loader = DirectoryLoader(
            application_context_path,
            glob="**/*",
            recursive=True,
            use_multithreading=True,
            max_concurrency=12,
            load_hidden=bool(config.get("load_hidden", True)),
            show_progress=True,
            loader_cls=CustomTextLoader,
            loader_kwargs={
                "autodetect_encoding": True,
                "exclusions": exclusions
            },
            silent_errors=True
        )
        documents = loader.load() if loader else None
        if documents:
            oversizedDocs = report_oversized_docs(documents, int(config.get("max_doc_chars", 8000)))
            for doc in documents:
                src = doc.metadata["source"]
                doc.metadata["filename"] = os.path.basename(src)
                doc.metadata["file_extension"] = os.path.splitext(src)[1]
                doc.metadata["directory"] = os.path.dirname(src)
                try:
                    doc.metadata["file_size"] = os.path.getsize(src)
                    doc.metadata["last_modified_at"] = os.path.getmtime(src)
                    doc.metadata["created_at"] = os.path.getctime(src)
                except Exception:
                    pass
            print("--- Enriching documents with metadata...")
            all_file_paths = [doc.metadata.get('source', '') for doc in documents]
            documents = enrich_documents_with_metadata(documents, all_file_paths)

            project_summary = get_project_summary(documents)
            print(f"--- Project summary: {project_summary['total_files']} files, "
                  f"{project_summary['total_lines']} lines")
        else:
            documents = None
            print(f"The directory '{application_context_path}' does not contain loadable files.")
    else:
        documents = None

    if documents:
        retrieval_chain = build_retrieval_chain(documents, config, prompt_template)
        if retrieval_chain is None:
            print("Error: RAG chain not built successfully; falling back to prompt-only mode.")
            prompt_only_chain = build_prompt_only_chain(config, prompt_template, documents=documents)
            if prompt_only_chain is None:
                return None
            print("--- Prompt-only chain ready (loaded-documents fallback mode).")
            global_state.set_state('rag_chain_ready', True)
            return prompt_only_chain
        else:
            if isinstance(retrieval_chain, (OptimizedHistoryAwareRAGChain, UnifiedAgentRAGChain)):
                retrieval_chain.setDetectedOversizedDocs(bool(oversizedDocs))
        print("--- RAG chain built successfully.")
        global_state.set_state('rag_chain_ready', True)
        return retrieval_chain
    else:
        print("No files found in ./application; starting in no-documents mode.")
        prompted_chain = build_retrieval_chain(documents, config, prompt_template)
        if prompted_chain is None:
            prompt_only_chain = build_prompt_only_chain(config, prompt_template, documents=documents)
            if prompt_only_chain is None:
                return None
            print("--- Prompt-only chain ready (no documents loaded).")
            global_state.set_state('rag_chain_ready', True)
            return prompt_only_chain
        if isinstance(prompted_chain, (OptimizedHistoryAwareRAGChain, UnifiedAgentRAGChain)):
            prompted_chain.setDetectedOversizedDocs(bool(oversizedDocs))
        global_state.set_state('rag_chain_ready', True)
        return prompted_chain
