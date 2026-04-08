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
from ..utils import _approx_tokens, _sanitize_rewritten_question, _sanitize_and_redact, _normalize_text, _unique_filenames_from_split, _pack_context
from ..interaction import show_rephrased_question, save_context_blob
from ..retrieval import retrieve_documents
from agent.rag_enhancements import expand_query_with_context, allocate_context_budget, add_cross_references
from .base import Callbacks

# Regex to strip code blocks (``` or ''') so embedded code doesn't cause
# false-positive file-listing detection.
_CODE_BLOCK_RE = re.compile(r"```[\s\S]*?```|'''[\s\S]*?'''")

# Helper for file listing queries
def _is_list_files_query(q: str) -> bool:
    if not q:
        return False

    # Strip code blocks to avoid false positives from embedded code content
    # (e.g. a Java comment saying "The login.conf FILE is not needed")
    cleaned_q = _CODE_BLOCK_RE.sub("", q)

    pat = r"(show|enlist|list|enumerate|display|print)\s+(all\s+)?(of\s+)?(the\s+)?(snippets|programs|files|documents|docs|file)"
    extension_pat = r"(files?\s+with\s+(the\s+)?extension|files?\s+ending\s+in|(?<!\w)\.\w+\s+files?|\*\.\w+)"
    detectedFilesPrompt = bool(re.search(pat, cleaned_q, flags=re.IGNORECASE))
    detectedExtensionQuery = bool(re.search(extension_pat, cleaned_q, flags=re.IGNORECASE))

    # For long prompts (likely containing inline code/context even without
    # fences), require an explicit listing verb — the extension pattern alone
    # is too easy to trigger on incidental mentions of file names.
    if detectedExtensionQuery and not detectedFilesPrompt and len(cleaned_q.strip()) > 500:
        print("--- _is_list_files_query: extension pattern matched but prompt is long and has no listing verb → ignoring ---\n")
        return False

    result = detectedFilesPrompt or detectedExtensionQuery
    if result:
        print("--- Detected files prompt! ---\n")
    return result

class HistoryAwareNoDocsChain:
    """
    Uses the SAME contextualize_q_prompt (history-aware rewrite) but skips retrieval.
    Contract: .invoke({"input": str, "chat_history": list}) -> {"answer": str}
    """
    def __init__(self, llm, contextualize_q_prompt: ChatPromptTemplate, qa_prompt_no_ctx: ChatPromptTemplate,
                 history_summary_cfg: Dict[str, Any]):
        self.llm = llm
        self.contextualize_chain = (contextualize_q_prompt | llm).with_config({"callbacks": [Callbacks()]})
        self.answer_chain = (qa_prompt_no_ctx | llm).with_config({"callbacks": [Callbacks()]})
        self.last_programs_name: List[str] = []
        self.history_summary_cfg = history_summary_cfg
        self.httpx_client_instance = None

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

    def _to_text(self, response) -> str:
        if isinstance(response, str):
            return response
        return getattr(response, "content", str(response))

    def _summarize_history_if_needed(self, chat_history: List[Any], question: str) -> List[Any]:
        mh = self.history_summary_cfg
        if not mh.get("enable", False) or not chat_history:
            return chat_history

        # Rough length check
        est_tokens = sum(_approx_tokens(getattr(m, "content", str(m))) for m in chat_history)
        if est_tokens <= mh.get("trigger_tokens", 800):
            return chat_history

        # Build a temporary summary
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
        # Keep the last few turns verbatim for recency, prepend the summary as a system message
        keep_last = mh.get("keep_last_turns", 6)
        tail = chat_history[-keep_last:] if keep_last > 0 else []
        return [SystemMessage(content=f"CHAT HISTORY SUMMARY:\n{summary}")] + tail

    def invoke(self, payload: dict):
        print("--- HistoryAwareNoDocsChain: Processing contextual request without retrieval ---")
        print("--- Evaluating conversation history for intelligent rephrasing ---")
        payload = {
            "input": payload.get("input", ""),
            "chat_history": payload.get("chat_history", []),
            "external_context": payload.get("external_context", ""),
            "external_sources": payload.get("external_sources", []),
            "system_context": payload.get("system_context", ""),
            "files_context": payload.get("files_context", ""), # <NEW>
        }

        if not payload["chat_history"]:
            payload["chat_history"] = DBChatHistoryLoader.load(limit=3)

        # 1) Optional history summarization + keep tail
        hist = self._summarize_history_if_needed(payload["chat_history"], payload["input"])

        # 2) History-aware rewrite (only if there's meaningful chat history)
        original_input = payload["input"]
        print(f"\n--- Original input: {original_input}")
        print(f"\n--- History: {hist}")
        if hist and len(hist) > 0:
            rewritten = self.contextualize_chain.invoke({"input": original_input, "chat_history": hist})
            rewritten_text = _sanitize_rewritten_question(self._to_text(rewritten))
            show_rephrased_question(rewritten_text, payload.get("conversation_user_id"))
        else:
            rewritten_text = original_input
            print("--- No significant chat history detected, proceeding with original question ---")
        # 3) Optional web context merge (inject as a SystemMessage)
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
            ext_block = f"WEB CONTEXT (summarized from live search):\n{ext}{sources_str}"
            hist = [SystemMessage(content=ext_block)] + (hist or [])

        # 4) Answer w/o {context}
        answer_payload = {
            #"input": original_input,
            "input": rewritten_text,
            "chat_history": hist,
        }
        # Provide all placeholders
        answer_payload["system_context"] = payload.get("system_context", "")
        answer_payload["files_context"] = payload.get("files_context", "") # <NEW>
        answer_payload["context"] = ""

        answered = self.answer_chain.invoke(answer_payload)
        invokes_counter = global_state.get_state('chat_hist_summarizer_counter', 0)
        global_state.set_state('chat_hist_summarizer_counter', invokes_counter + 1)
        return {"answer": self._to_text(answered)}

class OptimizedHistoryAwareRAGChain:
    """
    Enhanced RAG that:
    - rewrites the question from chat history (same contextualize prompt),
    - retrieves with vector (MMR) + optional BM25, fuses with RRF,
    - optionally compresses/reorders docs,
    - packs context with clear labels,
    - answers with your same prompt (expects {context}) and chat history.
    Contract preserved: .invoke({"input": str, "chat_history": list}) -> {"answer": str}
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
        # Build QA prompt first so it is available for the answer chain
        self.qa_prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_template_string),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
            ("system", "Apply all of the Rules only to the **CURRENT** human input ({input}); ignore chat_history for all of the Rules.")
        ])
        # Chains with cancellation callbacks
        self.contextualize_chain = (contextualize_q_prompt | llm).with_config({"callbacks": [Callbacks()]})
        self.answer_chain = (self.qa_prompt | llm).with_config({"callbacks": [Callbacks()]})
        self.vector_store = vector_store
        self.split_docs = split_docs
        self.retrieval_cfg = retrieval_cfg
        self.compression_cfg = compression_cfg
        self.history_summary_cfg = history_summary_cfg
        self.bm25 = bm25
        self.last_programs_name: List[str] = []
        self.detected_oversized_docs = False
        self.httpx_client_instance = None

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
            # Threshold tuned conservatively; adjustable in config
            compressors.append(EmbeddingsFilter(embeddings=self.vector_store.embedding_function, similarity_threshold=0.3))

        # Long-context reorder to move the most relevant lines toward the end of each chunk
        if ccfg.get("use_long_context_reorder", True) and LongContextReorder is not None:
            compressors.append(LongContextReorder())

        pipeline = DocumentCompressorPipeline(compressors=compressors)

        # Wrap a dummy retriever that returns our already-retrieved docs,
        # then run the pipeline with the user query to focus content.
        class _FixedRetriever:
            def __init__(self, docs): self._docs = docs
            def get_relevant_documents(self, _): return self._docs

        retr = _FixedRetriever(docs)
        comp = ContextualCompressionRetriever(base_compressor=pipeline, base_retriever=retr)
        try:
            # The compressor expects a "query" string; we will provide it upstream.
            # Here we return a callable that accepts query later.
            return comp
        except Exception:
            return docs

    def invoke(self, payload: dict):
        print(f"\n--- OptimizedHistoryAwareRAGChain::invoke(): >>>>>>>>>>{payload}<<<<<<<<<<")
        print("--- OptimizedHistoryAwareRAGChain: Processing request with document retrieval ---")
        print("--- Analyzing conversation context and preparing intelligent document search ---")
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
        
        if files_ctx and files_ctx.strip() and not explicit_kb_request:
            # Check if files_context is a clarification request (not actual file results)
            is_not_useful = (
                "LLM Clarification" in files_ctx or
                "File search was not possible" in files_ctx or
                "File search was not needed" in files_ctx or
                "No files found" in files_ctx or
                "No files matching" in files_ctx or
                "clarify" in files_ctx.lower() or
                "Which base location" in files_ctx
            )
            if not is_not_useful:
                # FileSearchRAGChain already found files, use that result
                print("--- Using files_context from FileSearchRAGChain ---")
                return {"answer": files_ctx}
            else:
                # It's a clarification/empty result - ignore it and use knowledge base files instead
                print("--- FileSearchRAGChain returned non-useful result, using knowledge base instead ---")
                files_ctx = ""  # Clear it so we proceed to knowledge base check
        elif explicit_kb_request:
            print("--- User explicitly requested 'provided context', ignoring FileSearchRAGChain results ---")
            files_ctx = "" # Clear it so we proceed to knowledge base check
        
        # In Multi-Turn mode, NEVER short-circuit with a file listing.
        # Multi-Turn is LLM-free thinking: the user's request (e.g. "Make a .js
        # file…") must always reach the LLM / agent pipeline, even if the
        # regex accidentally matches an extension pattern in the prompt.
        multi_turn_enabled = bool(payload.get("multi_turn_enabled", False))

        if not multi_turn_enabled and (_is_list_files_query(question) or _is_list_files_query(q_rewritten)):
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
        elif multi_turn_enabled and (_is_list_files_query(question) or _is_list_files_query(q_rewritten)):
            print("--- Multi-Turn mode: file-listing detection triggered but BYPASSED → request goes to LLM ---")

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
            # Prefer web context first for recency, then local context
            ext_header = "WEB CONTEXT (summarized from live search):\n"
            if len(ext) > max(1000, max_ctx_chars // 2):
                ext = ext[: max(1000, max_ctx_chars // 2)] + "…"
            sources_str = ""
            if isinstance(external_sources, list) and external_sources:
                safe_sources = [str(s) for s in external_sources[:8]]
                sources_str = "\n\nSources:\n" + "\n".join(f"- {s}" for s in safe_sources)
            merged = f"{ext_header}{ext}{sources_str}\n\nLOCAL CONTEXT:\n{context_blob}" if context_blob else f"{ext_header}{ext}{sources_str}"
            # Respect overall context cap
            if len(merged) > max_ctx_chars:
                merged = merged[: max_ctx_chars] + "…"
            context_blob = merged

        if _is_list_files_query(question) or _is_list_files_query(q_rewritten):
            manifest = _unique_filenames_from_split(self.split_docs)
            header = "FILE MANIFEST (all loaded):\n" + "\n".join(f"- {f}" for f in manifest)
            context_blob = header + "\n\n" + context_blob

        print(f"\n--- Original input: {original_input}")
        print(f"\n--- Rewritten input: {q_rewritten}")
        print(f"\n--- History: {hist}")
        # 6) Answer with your same QA prompt
        format_kwargs = {
            #"input": original_input,
            "input": q_rewritten,
            "chat_history": hist,
        }

        # Always provide all placeholders independently
        sys_ctx = payload.get("system_context", "")
        files_ctx = payload.get("files_context", "") # <NEW>

        format_kwargs["system_context"] = sys_ctx or ""
        format_kwargs["files_context"] = files_ctx or "" # <NEW>
        format_kwargs["context"] = context_blob or ""

        msgs = self.qa_prompt.format_messages(**format_kwargs)
        #Get hash of original_input...
        hash_object = hashlib.sha256(q_rewritten.encode())
        hex_dig = hash_object.hexdigest()
        save_context_blob(hex_dig, context_blob)
        print("--- Context blob saved with hash: " + hex_dig + " ---")
        out = self.llm.invoke(msgs)
        invokes_counter = global_state.get_state('chat_hist_summarizer_counter', 0)
        global_state.set_state('chat_hist_summarizer_counter', invokes_counter + 1)        
        text = getattr(out, "content", str(out))
        return {"answer": text}
