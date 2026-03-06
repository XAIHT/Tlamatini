from django.contrib import admin
from .models import AgentMessage
from .models import LLMProgram
from .models import LLMSnippet
from .models import Prompt
from .models import Omission
from .models import ContextCache
from .models import Mcp
from .models import Tool
from .models import Agent
from .models import AgentProcess

admin.site.register(AgentMessage)
admin.site.register(LLMProgram)
admin.site.register(LLMSnippet)
admin.site.register(Prompt)
admin.site.register(Omission)
admin.site.register(ContextCache)
admin.site.register(Mcp)
admin.site.register(Tool)
admin.site.register(Agent)
admin.site.register(AgentProcess)
