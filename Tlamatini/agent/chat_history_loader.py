# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
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

class DBChatHistoryLoader:
    """
    Safely loads the entire chat transcript (oldest->newest) from AgentMessage,
    converts it to LangChain messages (Human/AI), and lightly sanitizes HTML
    (your bot saves <br>, <strong>, etc.).
    """
    BOT_USERNAME = "Tlamatini"

    # Conversation-memory window. load() returns AT MOST this many messages — an
    # UPPER bound (the window is 0..N inclusive), never a per-turn minimum. The
    # value is intentionally small so the prompt stays lean while still carrying
    # enough turns for Step-by-Step / multi-turn continuity.
    HISTORY_WINDOW_MAX = 8

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
    def load(cls, limit: Optional[int] = None, conversation_user=None, conversation_user_id=None):
        try:
            out = []
            # Window is a HARD UPPER bound of HISTORY_WINDOW_MAX (=8): the loader
            # returns BETWEEN 0 AND 8 messages, whatever the conversation holds. It
            # is a "superior" cap, never a per-turn minimum. We NO LONGER shrink it
            # to chat_hist_summarizer_counter — that counted TURNS (a turn is ~2
            # messages), so on the first follow-up after a Clear-history the window
            # collapsed to a single message and the executor then dropped it as the
            # current input, leaving EMPTY history (Step-by-Step / multi-turn could
            # not continue). Clear-history deletes the rows and the per-user filter
            # below keep sessions isolated, so honouring the caller's window is safe.
            if not limit or limit <= 0 or limit > cls.HISTORY_WINDOW_MAX:
                limit = cls.HISTORY_WINDOW_MAX

            if limit and limit > 0:
                # Get the N newest messages (descending), then reverse to chronological
                qs = AgentMessage.objects.select_related("user")
                if conversation_user is not None:
                    qs = qs.filter(conversation_user=conversation_user)
                elif conversation_user_id is not None:
                    qs = qs.filter(conversation_user_id=conversation_user_id)
                qs = qs.order_by("-timestamp", "-pk")[:limit]
                qs = reversed(qs)
            else:
                # No limit: get everything oldest -> newest
                qs = AgentMessage.objects.select_related("user")
                if conversation_user is not None:
                    qs = qs.filter(conversation_user=conversation_user)
                elif conversation_user_id is not None:
                    qs = qs.filter(conversation_user_id=conversation_user_id)
                qs = qs.order_by("timestamp", "pk")

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
