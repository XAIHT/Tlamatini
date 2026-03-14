from typing import List, Dict, Any
import httpx
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from ...chat_history_loader import DBChatHistoryLoader
from ...global_state import global_state
from ..utils import _approx_tokens, _sanitize_rewritten_question, _sanitize_and_redact, _normalize_text
from ..interaction import show_rephrased_question
from .base import Callbacks

class BasicPromptOnlyChain:
    """
    Minimal chain that uses only the provided prompt template and LLM, but supports conversation history.
    Keeps the same .invoke(payload) -> {"answer": str} contract.
    """
    def __init__(self, llm,  contextualize_q_prompt: ChatPromptTemplate, qa_prompt_no_ctx: ChatPromptTemplate,  prompt_template_string: str, history_summary_cfg: Dict[str, Any]):
        self.llm = llm
        self.contextualize_chain = (contextualize_q_prompt | llm).with_config({"callbacks": [Callbacks()]})
        self.answer_chain = (qa_prompt_no_ctx | llm).with_config({"callbacks": [Callbacks()]})
        self.history_summary_cfg = history_summary_cfg
        self.prompt_template_string = prompt_template_string
        self.last_programs_name: List[str] = []  # avoid attribute errors
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
        # Keep the last few turns verbatim for recency, prepend the summary as a system message
        keep_last = mh.get("keep_last_turns", 6)
        tail = chat_history[-keep_last:] if keep_last > 0 else []
        return [SystemMessage(content=f"CHAT HISTORY SUMMARY:\n{summary}")] + tail
    
    def get_history_summary(self, chat_history: List[Any], question: str) -> str:
        mh = self.history_summary_cfg
        if not mh.get("enable", False) or not chat_history:
            return ""
        return self._summarize_history_if_needed(chat_history, question)

    def invoke(self, payload: dict):
        print("--- BasicPromptOnlyChain: Processing request without document context ---")
        print("--- Analyzing conversation history for possible question rephrasing ---")
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
            rewritten = self.contextualize_chain.invoke({"input": payload["input"], "chat_history": hist})
            rewritten_text = _sanitize_rewritten_question(self._to_text(rewritten))
            show_rephrased_question(rewritten_text, payload.get("conversation_user_id"))
        else:
            rewritten_text = original_input
            print("\n--- No chat history found, using original question without rephrasing")
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

        # 4) Answer w/o {context} (but potentially with system_context)
        answer_payload = {
            #"input": original_input,
            "input": rewritten_text,
            "chat_history": hist
        }
        # Ensure all placeholders exist
        answer_payload["system_context"] = payload.get("system_context", "")
        answer_payload["files_context"] = payload.get("files_context", "") # <NEW>
        answer_payload["context"] = ""

        answered = self.answer_chain.invoke(answer_payload)
        invokes_counter = global_state.get_state('chat_hist_summarizer_counter', 0)
        global_state.set_state('chat_hist_summarizer_counter', invokes_counter + 1)
        return {"answer": self._to_text(answered)}
