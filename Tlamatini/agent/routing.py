# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# agent/routing.py
from django.urls import re_path
from . import consumers
from .prompt_flow_panel_consumer import PromptFlowPanelConsumer
from .chat_voice_consumer import ChatVoiceConsumer
from .terminal_consumer import TerminalConsumer
from .interactor.consumer import InteractorConsumer

websocket_urlpatterns = [
    re_path(r'ws/interactor/$', InteractorConsumer.as_asgi()),
    re_path(r'ws/terminals/$', TerminalConsumer.as_asgi()),
    re_path(r'ws/chat-voice/$', ChatVoiceConsumer.as_asgi()),
    re_path(r'ws/prompt-flow-panel/$', PromptFlowPanelConsumer.as_asgi()),
    re_path(r'ws/agent/$', consumers.AgentConsumer.as_asgi()),
]
