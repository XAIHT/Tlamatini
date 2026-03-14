# --- DB-backed chat history loader (safe, transparent) ---
import html as _html
import re as _re2
from typing import Optional
from .models import AgentMessage
try:
    from langchain_core.messages import HumanMessage, AIMessage
except Exception:
    # Fallback shim if import path changes; we’ll degrade gracefully to strings.
    HumanMessage = AIMessage = None  # type: ignore
from .global_state import global_state

class DBChatHistoryLoader:
    """
    Safely loads the entire chat transcript (oldest->newest) from AgentMessage,
    converts it to LangChain messages (Human/AI), and lightly sanitizes HTML
    (your bot saves <br>, <strong>, etc.).
    """
    BOT_USERNAME = "LLM_Bot"

    @staticmethod
    def _sanitize(text: str) -> str:
        if not text:
            return ""
        # 1) normalize line breaks saved as HTML
        t = text.replace("<br />", "\n").replace("<br/>", "\n").replace("<br>", "\n")
        # 2) strip residual HTML tags (but keep the text)
        t = _re2.sub(r"<[^>]+>", "", t)
        # 3) unescape entities (&lt; &gt; &amp;)
        t = _html.unescape(t)
        return t.strip()

    @classmethod
    def load(cls, limit: Optional[int] = None):
        try:
            out = []
            invokes_counter = global_state.get_state('chat_hist_summarizer_counter', 0)
            
            if invokes_counter > 0 and (limit is None or invokes_counter < limit):
                limit = invokes_counter

            if limit and limit > 0:
                # Get the N newest messages (descending), then reverse to chronological
                qs = AgentMessage.objects.select_related("user").order_by("-timestamp")[:limit]
                qs = reversed(qs)
            else:
                # No limit: get everything oldest -> newest
                qs = AgentMessage.objects.select_related("user").order_by("timestamp")

            for m in qs:
                username = getattr(m.user, "username", "")
                content = cls._sanitize(m.message)
                if not content:
                    continue

                if content.startswith("Referenced Rephrase:") or content.startswith("---"):
                    continue

                if out and out[-1] and out[-1].content == content:
                    continue

                if HumanMessage is None or AIMessage is None:
                    role = "assistant" if username == cls.BOT_USERNAME else "human"
                    out.append({"type": role, "content": content})
                else:
                    if username == cls.BOT_USERNAME:
                        out.append(AIMessage(content=content))
                        print(f"--- Added AI message to chat history: {content}")
                    else:
                        out.append(HumanMessage(content=content))
                        print(f"--- Added Human message to chat history: {content}")
            return out
        except Exception as e:
            # Never fail the request because of history; just log and return empty.
            print(f"--- DBChatHistoryLoader.load failed: {e} (returning empty history)")
            return []