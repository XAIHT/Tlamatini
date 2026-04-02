from typing import List, Dict, Any, Optional
import httpx
import hashlib
import re
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from ...chat_history_loader import DBChatHistoryLoader
from ...global_state import global_state
from ...mcp_agent import create_unified_agent
from ..utils import _approx_tokens, _sanitize_rewritten_question, _sanitize_and_redact, _normalize_text, _unique_filenames_from_split, _pack_context
from ..interaction import show_rephrased_question, save_context_blob
from ..retrieval import retrieve_documents
from agent.rag_enhancements import expand_query_with_context, allocate_context_budget, add_cross_references
from .base import Callbacks
from .history_aware import _is_list_files_query, _CODE_BLOCK_RE

class UnifiedAgentChain:
    """
    Chain wrapper that uses the unified agent (with tool support) while maintaining
    compatibility with the existing chain interface.
    Contract: .invoke(payload) -> {"answer": str}
    """
    def __init__(self, llm, prompt_template_string: str, history_summary_cfg: Dict[str, Any]):
        self.llm = llm
        self.prompt_template_string = prompt_template_string
        self.history_summary_cfg = history_summary_cfg
        self.last_programs_name: List[str] = []
        self.httpx_client_instance = None
        self.unified_agent = None
        self._initialize_agent()

    def _initialize_agent(self):
        """Initialize the unified agent with the prompt template."""
        try:
            self.unified_agent = create_unified_agent(self.llm, self.prompt_template_string)
            print("--- UnifiedAgentChain: Tool-enabled agent initialized successfully ---")
        except Exception as e:
            print(f"--- UnifiedAgentChain: Failed to initialize agent ({e}), falling back to basic LLM ---")
            self.unified_agent = None

    def setHttpxClientInstance(self, httpx_client_instance: httpx.Client):
        self.httpx_client_instance = httpx_client_instance

    def getHttpxClientInstance(self):
        return self.httpx_client_instance

    def abort_connection(self):
        """
        AGGRESSIVELY abort the httpx connection - close immediately without waiting.
        This forcibly terminates any pending HTTP requests to Ollama.
        """
        if self.httpx_client_instance:
            try:
                print("--- [ABORT] Forcibly closing httpx transport ---")
                # First, try to close the underlying transport (socket level)
                if hasattr(self.httpx_client_instance, '_transport') and self.httpx_client_instance._transport:
                    try:
                        self.httpx_client_instance._transport.close()
                        print("--- [ABORT] Transport closed ---")
                    except Exception as te:
                        print(f"--- [ABORT] Transport close error (expected): {te}")
                
                # Then close the client itself
                try:
                    self.httpx_client_instance.close()
                    print("--- [ABORT] Client closed ---")
                except Exception as ce:
                    print(f"--- [ABORT] Client close error (expected): {ce}")
                
            except Exception as e:
                print(f"--- [ABORT] Error during abort (connection may already be closed): {e}")
            finally:
                self.httpx_client_instance = None
                print("--- [ABORT] Connection reference cleared ---")

    def setLastProgramName(self, name):
        self.last_programs_name.append(name)

    def getLastProgramName(self):
        return self.last_programs_name[-1] if self.last_programs_name else None

    def _summarize_history_if_needed(self, chat_history: List[Any], question: str) -> List[Any]:
        """Summarize chat history if it exceeds token limits."""
        mh = self.history_summary_cfg
        if not mh.get("enable", False) or not chat_history:
            return chat_history

        est_tokens = sum(_approx_tokens(getattr(m, "content", str(m))) for m in chat_history)
        if est_tokens <= mh.get("trigger_tokens", 800):
            return chat_history

        sum_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a conversation summarizer. Create **JUST ONCE** concise, factual summary of the dialogue that captures information relevant to answering the user's current question.\n\n"
                       "STRICT GUIDELINES:\n"
                       "a. Focus on: key facts, decisions made, technical details, entity names, constraints, and ongoing context\n"
                       "b. Exclude: pleasantries, acknowledgments, clarifying questions, and redundant information\n"
                       "c. Format: Single paragraph, factual statements only, no conversational markers\n"
                       "d. Length: Maximum 120 words\n"
                       "e. Style: Neutral, technical documentation tone\n\n"
                       "f. Return ONLY the summary content - no prefixes, role indicators, or meta-commentary."),
            MessagesPlaceholder("chat_history"),
            ("human", "Current user question: {q}\n\nGenerate summary focusing on information relevant to this question:")
        ])
        msgs = sum_prompt.format_messages(chat_history=chat_history, q=question)
        out = self.llm.with_config({"callbacks": [Callbacks()]}).invoke(msgs)
        summary = getattr(out, "content", str(out))
        keep_last = mh.get("keep_last_turns", 6)
        tail = chat_history[-keep_last:] if keep_last > 0 else []
        return [SystemMessage(content=f"CHAT HISTORY SUMMARY:\n{summary}")] + tail

    def invoke(self, payload: dict):
        """Invoke the unified agent with tool support."""
        print("--- UnifiedAgentChain: Processing request with tool-enabled agent ---")
        
        payload = {
            "input": payload.get("input", ""),
            "chat_history": payload.get("chat_history", []),
            "external_context": payload.get("external_context", ""),
            "external_sources": payload.get("external_sources", []),
            "system_context": payload.get("system_context", ""),
            "files_context": payload.get("files_context", ""),
        }

        if not payload["chat_history"]:
            payload["chat_history"] = DBChatHistoryLoader.load(limit=3)

        # Summarize history if needed
        hist = self._summarize_history_if_needed(payload["chat_history"], payload["input"])

        # Build enhanced input with context
        original_input = payload["input"]
        
        # Incorporate system context and files context into the input if available
        enhanced_input = original_input
        
        # Add files context first (from FileSearchRAGChain) with clear instructions
        if payload.get("files_context"):
            enhanced_input = f"""Files Context (from FileSearchRAGChain - file system search results):
{payload['files_context']}

IMPORTANT: File operations are handled by FileSearchRAGChain and provided above.
You do NOT need to use any tools for file operations - the file information is already provided in the context.

User Question: {enhanced_input}"""
        
        # Add system context
        if payload.get("system_context"):
            enhanced_input = f"System Context: {payload['system_context']}\n\n{enhanced_input}"
        
        # Incorporate external web context
        ext_raw = payload.get("external_context", "")
        ext_srcs = payload.get("external_sources", []) or []
        if isinstance(ext_raw, str) and ext_raw.strip():
            ext = _sanitize_and_redact(_normalize_text(ext_raw), redact=False)
            if len(ext) > 6000:
                ext = ext[:6000] + "…"
            sources_str = ""
            if isinstance(ext_srcs, list) and ext_srcs:
                safe_sources = [str(s) for s in ext_srcs[:8]]
                sources_str = "\n\nSources:\n" + "\n".join(f"- {s}" for s in safe_sources)
            enhanced_input = f"Web Context: {ext}{sources_str}\n\n{enhanced_input}"

        # Use unified agent if available, otherwise fall back to basic LLM
        if self.unified_agent is not None:
            try:
                print(f"--- UnifiedAgentChain: Invoking unified agent with input length: {len(enhanced_input)} chars")
                result = self.unified_agent.invoke({"input": enhanced_input})
                print(f"--- UnifiedAgentChain: Agent returned result type: {type(result)}")
                if isinstance(result, dict):
                    print(f"--- UnifiedAgentChain: Result keys: {list(result.keys())}")
                    print(f"--- UnifiedAgentChain: output value: '{result.get('output', '<NOT PRESENT>')}' (length: {len(result.get('output', ''))})")
                answer = result.get("output", str(result)) if isinstance(result, dict) else str(result)
                if not answer or not answer.strip():
                    print(f"--- UnifiedAgentChain: WARNING - Empty answer received! Full result: {result}")
            except Exception as e:
                print(f"--- UnifiedAgentChain: Agent invocation failed ({e}), falling back to basic LLM ---")
                # Fallback to basic LLM call
                answer_payload = {
                    "input": original_input,
                    "chat_history": hist,
                    "system_context": payload.get("system_context", ""),
                    "files_context": payload.get("files_context", ""),
                    "context": "",
                }
                qa_prompt = ChatPromptTemplate.from_messages([
                    ("system", self.prompt_template_string),
                    MessagesPlaceholder("chat_history"),
                    ("human", "{input}"),
                ])
                answer_chain = (qa_prompt | self.llm).with_config({"callbacks": [Callbacks()]})
                answered = answer_chain.invoke(answer_payload)
                answer = getattr(answered, "content", str(answered))
        else:
            # Fallback to basic LLM call
            answer_payload = {
                "input": original_input,
                "chat_history": hist,
                "system_context": payload.get("system_context", ""),
                "files_context": payload.get("files_context", ""),
                "context": "",
            }
            qa_prompt = ChatPromptTemplate.from_messages([
                ("system", self.prompt_template_string),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ])
            answer_chain = (qa_prompt | self.llm).with_config({"callbacks": [Callbacks()]})
            answered = answer_chain.invoke(answer_payload)
            answer = getattr(answered, "content", str(answered))

        invokes_counter = global_state.get_state('chat_hist_summarizer_counter', 0)
        global_state.set_state('chat_hist_summarizer_counter', invokes_counter + 1)
        return {"answer": answer}

class UnifiedAgentRAGChain:
    """
    RAG chain that combines document retrieval with tool-enabled unified agent.
    Performs all RAG operations (retrieval, compression, context packing) but uses
    the unified agent for final answer generation with tool support.
    Contract: .invoke({"input": str, "chat_history": list}) -> {"answer": str}
    """
    def __init__(
        self,
        llm,
        prompt_template_string: str,
        contextualize_q_prompt: ChatPromptTemplate,
        vector_store: FAISS,
        split_docs: List[Document],
        retrieval_cfg: Dict[str, Any],
        compression_cfg: Dict[str, Any],
        history_summary_cfg: Dict[str, Any],
        bm25: Optional[Any] = None
    ):
        self.llm = llm
        self.prompt_template_string = prompt_template_string
        self.contextualize_q_prompt = contextualize_q_prompt
        self.vector_store = vector_store
        self.split_docs = split_docs
        self.retrieval_cfg = retrieval_cfg
        self.compression_cfg = compression_cfg
        self.history_summary_cfg = history_summary_cfg
        self.bm25 = bm25
        self.last_programs_name: List[str] = []
        self.detected_oversized_docs = False
        self.httpx_client_instance = None
        self.unified_agent = None
        self._initialize_agent()
        
        # Build contextualize chain for history-aware rewrite
        self.contextualize_chain = (contextualize_q_prompt | llm).with_config({"callbacks": [Callbacks()]})

    def _initialize_agent(self):
        """Initialize the unified agent with the prompt template."""
        try:
            self.unified_agent = create_unified_agent(self.llm, self.prompt_template_string)
            print("--- UnifiedAgentRAGChain: Tool-enabled agent initialized successfully ---")
        except Exception as e:
            print(f"--- UnifiedAgentRAGChain: Failed to initialize agent ({e}), will fall back to basic LLM ---")
            self.unified_agent = None

    def setHttpxClientInstance(self, httpx_client_instance: httpx.Client):
        self.httpx_client_instance = httpx_client_instance

    def getHttpxClientInstance(self):
        return self.httpx_client_instance

    def abort_connection(self):
        """
        AGGRESSIVELY abort the httpx connection - close immediately without waiting.
        This forcibly terminates any pending HTTP requests to Ollama.
        """
        if self.httpx_client_instance:
            try:
                print("--- [ABORT] Forcibly closing httpx transport ---")
                # First, try to close the underlying transport (socket level)
                if hasattr(self.httpx_client_instance, '_transport') and self.httpx_client_instance._transport:
                    try:
                        self.httpx_client_instance._transport.close()
                        print("--- [ABORT] Transport closed ---")
                    except Exception as te:
                        print(f"--- [ABORT] Transport close error (expected): {te}")
                
                # Then close the client itself
                try:
                    self.httpx_client_instance.close()
                    print("--- [ABORT] Client closed ---")
                except Exception as ce:
                    print(f"--- [ABORT] Client close error (expected): {ce}")
                
            except Exception as e:
                print(f"--- [ABORT] Error during abort (connection may already be closed): {e}")
            finally:
                self.httpx_client_instance = None
                print("--- [ABORT] Connection reference cleared ---")

    def setDetectedOversizedDocs(self, detected_oversized_docs: bool):
        self.detected_oversized_docs = detected_oversized_docs

    def getDetectedOversizedDocs(self):
        return self.detected_oversized_docs

    def setLastProgramName(self, name):
        self.last_programs_name.append(name)

    def getLastProgramName(self):
        return self.last_programs_name[-1] if self.last_programs_name else None

    def _to_text(self, response) -> str:
        if isinstance(response, str):
            return response
        return getattr(response, "content", str(response))

    def _summarize_history_if_needed(self, chat_history: List[Any], question: str) -> List[Any]:
        mh = self.history_summary_cfg
        if not mh.get("enable", False) or not chat_history:
            return chat_history
        est_tokens = sum(_approx_tokens(getattr(m, "content", str(m))) for m in chat_history)
        if est_tokens <= mh.get("trigger_tokens", 800):
            return chat_history
        sum_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a conversation summarizer. Create **JUST ONCE** a concise, factual summary of the dialogue that captures information relevant to answering the user's current question.\n\n"
                       "STRICT GUIDELINES:\n"
                       "a. Focus on: key facts, decisions made, technical details, entity names, constraints, and ongoing context\n"
                       "b. Exclude: pleasantries, acknowledgments, clarifying questions, and redundant information\n"
                       "c. Format: Single paragraph, factual statements only, no conversational markers\n"
                       "d. Length: Maximum 120 words\n"
                       "e. Style: Neutral, technical documentation tone\n\n"
                       "f. Return ONLY the summary content - no prefixes, role indicators, or meta-commentary."),
            MessagesPlaceholder("chat_history"),
            ("human", "Current user question: {q}\n\nGenerate summary focusing on information relevant to this question:")
        ])
        msgs = sum_prompt.format_messages(chat_history=chat_history, q=question)
        out = self.llm.with_config({"callbacks": [Callbacks()]}).invoke(msgs)
        summary = getattr(out, "content", str(out))
        keep_last = mh.get("keep_last_turns", 6)
        tail = chat_history[-keep_last:] if keep_last > 0 else []
        return [SystemMessage(content=f"CHAT HISTORY SUMMARY:\n{summary}")] + tail

    def _retrieve(self, q: str) -> List[Document]:
        return retrieve_documents(q, self.vector_store, self.bm25, self.retrieval_cfg, self.split_docs)

    def _compress_and_reorder(self, docs: List[Document]) -> List[Document]:
        ccfg = self.compression_cfg
        if not docs:
            return []
        # Early soft filter by size per doc
        max_doc_chars = int(ccfg.get("max_doc_chars", 8000))
        for d in docs:
            if d.page_content and len(d.page_content) > max_doc_chars:
                d.page_content = d.page_content[:max_doc_chars] + "…"

        # If no compression components available, return quickly
        try:
            from langchain.retrievers.document_compressors import (
                LLMChainExtractor,
                EmbeddingsFilter,
                LongContextReorder,
                DocumentCompressorPipeline,
            )
            from langchain.retrievers import ContextualCompressionRetriever
        except ImportError:
            return docs

        compressors = []

        # Extractive compressor (LLM-driven)
        if ccfg.get("use_llm_extractor", True) and LLMChainExtractor is not None:
            compressors.append(LLMChainExtractor.from_llm(self.llm))

        # Embedding-based semantic filter (keeps only on-topic chunks)
        if ccfg.get("use_embeddings_filter", False) and EmbeddingsFilter is not None:
            compressors.append(EmbeddingsFilter(embeddings=self.vector_store.embedding_function, similarity_threshold=0.3))

        # Long-context reorder to move the most relevant lines toward the end of each chunk
        if ccfg.get("use_long_context_reorder", True) and LongContextReorder is not None:
            compressors.append(LongContextReorder())

        pipeline = DocumentCompressorPipeline(compressors=compressors)

        # Wrap a dummy retriever that returns our already-retrieved docs
        class _FixedRetriever:
            def __init__(self, docs): self._docs = docs
            def get_relevant_documents(self, _): return self._docs

        retr = _FixedRetriever(docs)
        comp = ContextualCompressionRetriever(base_compressor=pipeline, base_retriever=retr)
        try:
            return comp
        except Exception:
            return docs

    def invoke(self, payload: dict):
        """Invoke the RAG chain with unified agent for final answer."""
        print(f"\n--- UnifiedAgentRAGChain::invoke(): >>>>>>>>>>{payload}<<<<<<<<<<")
        print("--- UnifiedAgentRAGChain: Processing request with document retrieval and tool support ---")
        question = payload.get("input", "")
        original_input = question
        chat_history = payload.get("chat_history", [])
        external_context_raw = payload.get("external_context", "")
        external_sources = payload.get("external_sources", [])
        
        if not payload["chat_history"]:
            payload["chat_history"] = DBChatHistoryLoader.load(limit=3)
            chat_history = payload.get("chat_history", [])
        
        # 1) History summarization (optional) + keep last few turns
        hist = self._summarize_history_if_needed(chat_history, question)

        # 2) History-aware rewrite of the question (only if there's meaningful chat history)
        if hist and len(hist) > 0:
            rewritten = self.contextualize_chain.invoke({
                "input": original_input, 
                "chat_history": hist
            })
            q_rewritten = _sanitize_rewritten_question(self._to_text(rewritten))
            print("--- Conversation context available, proceeding with added history ---")
            show_rephrased_question(q_rewritten, payload.get("conversation_user_id"))
        else:
            q_rewritten = original_input
            print("--- No conversation context available, proceeding with original query ---")
        
        # NEW: Expand query with technical context if enabled
        if self.retrieval_cfg.get("enable_query_expansion", False):
            try:
                q_rewritten = expand_query_with_context(q_rewritten, hist)
                print(f"--- Expanded query: {q_rewritten}")
            except Exception as e:
                print(f"Warning: Query expansion failed: {e}")

        # SPECIAL CASE: corpus catalog (bypass retrieval)
        files_ctx = payload.get("files_context", "")
        
        # Check if user explicitly asks for "provided context" - if so, prioritize knowledge base
        explicit_kb_request = "provided context" in question.lower() or "provided context" in q_rewritten.lower()
        
        if explicit_kb_request:
            print("--- User explicitly requested 'provided context', ignoring FileSearchRAGChain results ---")
            files_ctx = "" # Clear it so we proceed to knowledge base check
        
        if (_is_list_files_query(question) or _is_list_files_query(q_rewritten)) and not files_ctx:
            self.retrieval_cfg["k_fused"] = max(30, int(self.retrieval_cfg.get("k_fused", 10)))
            files = _unique_filenames_from_split(self.split_docs)
            if not files:
                return {"answer": "No files are currently loaded in the knowledge base. Please load documents to enable file listing."}
            
            # Check if user is asking for files with a specific extension
            # Strip code blocks first to avoid matching extensions inside embedded code
            cleaned_question = _CODE_BLOCK_RE.sub("", question)
            extension_match = re.search(r'\*\.(\w+)|(?<!\w)\.(\w+)(?:\s+files?|$)|(\w+)\s+files?\s+(?:with|ending|extension)', cleaned_question, flags=re.IGNORECASE)
            if extension_match:
                # Extract extension (prioritize *.ext format, then .ext, then "ext files")
                ext = extension_match.group(1) or extension_match.group(2) or extension_match.group(3)
                if ext:
                    # Normalize extension (remove * if present, ensure it starts with .)
                    ext = ext.lower().replace('*', '').lstrip('.')
                    # Validate it's a reasonable extension (not common words like "the", "all", etc.)
                    common_words = {'the', 'all', 'with', 'file', 'files', 'name', 'named', 'search', 'find', 'locate'}
                    if ext not in common_words and len(ext) <= 10:  # Extensions are usually short
                        # Filter files by extension
                        filtered_files = [f for f in files if f.lower().endswith(f'.{ext}')]
                        if filtered_files:
                            listing = f"Files with extension .{ext} in knowledge base ({len(filtered_files)} total):\n" + "\n".join(f"• {f}" for f in filtered_files)
                            return {"answer": listing}
                        else:
                            return {"answer": f"No files with extension .{ext} found in the knowledge base."}

            # No extension filter - return all files
            listing = f"Available files in knowledge base ({len(files)} total):\n" + "\n".join(f"• {f}" for f in files)
            return {"answer": listing}

        # 3) Retrieve
        #docs = self._retrieve(original_input)
        docs = self._retrieve(q_rewritten)

        # 4) Contextual compression (optional)
        comp = self._compress_and_reorder(docs)
        if isinstance(comp, list):
            focused_docs = comp
        else:
            # comp is a ContextualCompressionRetriever -> compress using query
            try:
                #focused_docs = comp.get_relevant_documents(original_input)
                focused_docs = comp.get_relevant_documents(q_rewritten)
            except Exception:
                focused_docs = docs
        
        # NEW: Apply context budget allocation if enabled
        if self.retrieval_cfg.get("enable_context_budget_allocation", False):
            try:
                max_tokens = int(self.compression_cfg.get("max_context_chars", 32000)) // 4
                focused_docs = allocate_context_budget(focused_docs, max_tokens)
            except Exception as e:
                print(f"Warning: Context budget allocation failed: {e}")
        
        # 5) Build compact, labeled CONTEXT
        max_ctx_chars = int(self.compression_cfg.get("max_context_chars", 24000))
        redact = bool(self.compression_cfg.get("redact_secrets_in_context", False))
        
        # NEW: Add cross-references if enabled
        if self.retrieval_cfg.get("enable_cross_references", True):
            try:
                focused_docs = add_cross_references(focused_docs)
            except Exception as e:
                print(f"Warning: Cross-reference addition failed: {e}")
        
        # NEW: Use hierarchical context if enabled
        use_hierarchical = self.retrieval_cfg.get("enable_hierarchical_context", True)
        context_blob = _pack_context(focused_docs, max_ctx_chars, redact, use_hierarchical)

        # Optionally merge external web context if provided
        if isinstance(external_context_raw, str) and external_context_raw.strip():
            ext = _sanitize_and_redact(_normalize_text(external_context_raw), redact)
            ext_header = "WEB CONTEXT (summarized from live search):\n"
            if len(ext) > max(1000, max_ctx_chars // 2):
                ext = ext[: max(1000, max_ctx_chars // 2)] + "…"
            sources_str = ""
            if isinstance(external_sources, list) and external_sources:
                safe_sources = [str(s) for s in external_sources[:8]]
                sources_str = "\n\nSources:\n" + "\n".join(f"- {s}" for s in safe_sources)
            merged = f"{ext_header}{ext}{sources_str}\n\nLOCAL CONTEXT:\n{context_blob}" if context_blob else f"{ext_header}{ext}{sources_str}"
            if len(merged) > max_ctx_chars:
                merged = merged[: max_ctx_chars] + "…"
            context_blob = merged

        # Always include file manifest in context for file-related queries or when files_context is available
        if _is_list_files_query(question) or _is_list_files_query(q_rewritten) or payload.get("files_context", ""):
            manifest = _unique_filenames_from_split(self.split_docs)
            if manifest:
                header = "FILE MANIFEST (all loaded files in knowledge base):\n" + "\n".join(f"- {f}" for f in manifest)
                if "FILE MANIFEST" not in context_blob:
                    context_blob = header + "\n\n" + context_blob if context_blob else header

        print(f"\n--- Original input: {original_input}")
        print(f"\n--- Rewritten input: {q_rewritten}")
        print(f"\n--- History: {hist}")
        
        # 6) Build enhanced input with all context for unified agent
        sys_ctx = payload.get("system_context", "")
        files_ctx = payload.get("files_context", "")
        
        # Construct enhanced input with all context
        #enhanced_input = original_input
        enhanced_input = q_rewritten
        
        # Add files context first (highest priority - from FileSearchRAGChain)
        if files_ctx:
            enhanced_input = f"""Files Context (from FileSearchRAGChain - file system search results):
{files_ctx}

CRITICAL: File operations (reading files, listing files, searching for files) are handled by FileSearchRAGChain and provided above.
You do NOT need to use any tools for file operations - the file information is already provided in the context.
File operations are NOT available as tools - they are handled automatically by FileSearchRAGChain.

User Question: {enhanced_input}"""
        
        # Add retrieved context (contains file information from knowledge base)
        if context_blob:
            # Check if context contains file manifest or file listings
            if "FILE MANIFEST" in context_blob or "files" in context_blob.lower() or _is_list_files_query(question):
                enhanced_input = f"""Retrieved Context from Knowledge Base:
{context_blob}

CRITICAL: File operations are handled by FileSearchRAGChain (see Files Context above if provided) or by the knowledge base context.
- If file information is in the context above, extract and present it directly
- You do NOT need to use any tools for file operations - file operations are NOT available as tools
- File listings, file contents, and file search results are provided in the context automatically
- Simply extract and format the file information from the context to answer file-related queries

User Question: {enhanced_input}"""
            else:
                enhanced_input = f"Retrieved Context from Knowledge Base:\n{context_blob}\n\nUser Question: {enhanced_input}"
        
        # Add system context
        if sys_ctx:
            enhanced_input = f"System Context: {sys_ctx}\n\n{enhanced_input}"

        # Save context blob (for compatibility)
        hash_object = hashlib.sha256(original_input.encode())
        hex_dig = hash_object.hexdigest()
        save_context_blob(hex_dig, context_blob)
        print("--- Context blob saved with hash: " + hex_dig + " ---")

        # 7) Use unified agent if available, otherwise fall back to basic LLM
        if self.unified_agent is not None:
            try:
                result = self.unified_agent.invoke({"input": enhanced_input})
                answer = result.get("output", str(result)) if isinstance(result, dict) else str(result)
            except Exception as e:
                print(f"--- UnifiedAgentRAGChain: Agent invocation failed ({e}), falling back to basic LLM ---")
                # Fallback to basic LLM call with context
                qa_prompt = ChatPromptTemplate.from_messages([
                    ("system", self.prompt_template_string),
                    MessagesPlaceholder("chat_history"),
                    ("human", "{input}"),
                ])
                answer_payload = {
                    #"input": original_input,
                    "input": q_rewritten,
                    "chat_history": hist,
                    "system_context": sys_ctx or "",
                    "files_context": files_ctx or "",
                    "context": context_blob or "",
                }
                answer_chain = (qa_prompt | self.llm).with_config({"callbacks": [Callbacks()]})
                answered = answer_chain.invoke(answer_payload)
                answer = getattr(answered, "content", str(answered))
        else:
            # Fallback to basic LLM call with context
            qa_prompt = ChatPromptTemplate.from_messages([
                ("system", self.prompt_template_string),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ])
            answer_payload = {
                #"input": original_input,
                "input": q_rewritten,
                "chat_history": hist,
                "system_context": sys_ctx or "",
                "files_context": files_ctx or "",
                "context": context_blob or "",
            }
            answer_chain = (qa_prompt | self.llm).with_config({"callbacks": [Callbacks()]})
            answered = answer_chain.invoke(answer_payload)
            answer = getattr(answered, "content", str(answered))

        invokes_counter = global_state.get_state('chat_hist_summarizer_counter', 0)
        global_state.set_state('chat_hist_summarizer_counter', invokes_counter + 1)
        return {"answer": answer}
