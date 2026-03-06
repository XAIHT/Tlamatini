# agent/constants.py

# Error messages
ERROR_AGENT_NOT_READY = "Your agent cannot process your requests. <br> check you didn't specify context out of the root directory. <br> If everything is correct, then check Ollama is running and the config.json file is correct."
ERROR_NOT_AUTHENTICATED = "You're not authenticated."
ERROR_AGENT_NOT_READY_SIMPLE = "Agent is not ready. Please try again later."
ERROR_DIRECTORY_OUTSIDE_ROOT = "Selected directory is outside the application root path and is not allowed."

# System messages
MSG_AGENT_LOADING = "Your agent is loading. Please wait a moment."
MSG_AGENT_LOADING_CONTEXT = "Your agent is loading the context. Please wait a moment."
MSG_AGENT_READY = "Your agent is ready. You can now start chatting with the LLM."
MSG_AGENT_FALLBACK = "There was a problem, so the agent fallback to a Basic Prompt Only Chain (No context is used)."
MSG_OVERSIZED_DOCS_WARNING = "Your agent is ready. But some documents are too large, be aware the LLM might not be able to load them completely."
MSG_PROCESSING_REQUEST = "Your request is being processed by the LLM. Please wait a moment."
MSG_LLM_CANCELLED = 'LLM generation was cancelled by user. No message will be broadcast. Context will be erased.'
MSG_LLM_CONNECTION_DESTROYED = '✓ Connection to Ollama has been forcibly terminated. Ollama is now free.'
MSG_LLM_REBUILDING = '⏳ Rebuilding agent with fresh connection...'
MSG_LLM_REESTABLISHED = '✓ Agent successfully re-established. You can now start chatting again.'
MSG_LLM_RECONNECT = "LLM re-connection issued by user. Context will be erased and reconnection has been made."
MSG_LLM_CLEARCONTEXT = "LLM clear-context issued by user. Context will be erased and reconnection has been made."
MSG_LLM_HISTORY_CLEANED = "Chat history has been cleared. LLM agent reconnected successfully."
MSG_SESSION_RESTORED = "Welcome back, session restored"
MSG_SESSION_AND_CONTEXT_RESTORED = "Welcome back, session and context restored."
MSG_GREETING_RESPONSE = "It's a pleasure, I'm here to help you!"

# Regex patterns for code extraction
REGEX_NAMED_CODE_BLOCK = r'(BEGIN-CODE<<<|begin-code)([-\w./\\]+)>>>([\s\S]*?)(END-CODE|end-code)'
REGEX_UNNAMED_CODE_BLOCK = r'(?:BEGIN-CODE|begin-code)\s*\r?\n([\s\S]*?)\r?\n?(?:END-CODE|end-code)'
REGEX_CODE_BEGIN = r'(BEGIN-CODE<<<|begin-code)([-\w./\\]+)>>>'
REGEX_CODE_BEGIN_NO_NAME = r'(?:BEGIN-CODE|begin-code)'
REGEX_CODE_END = r'(END-CODE|end-code)'
REGEX_CODE_APOS = r'```'
REGEX_SNIPPET_WITH_LANG = r'```(python|bash|javascript|java|c|c\+\+|c#|php|ruby|go|lisp|fortran|basic|assembler|html|css|sql|yaml|typescript|cuda|xml|json)\r?\n([\s\S]*?)\r?\n?```'
REGEX_DOUBLE_BR = r'(<br>\n?)+'
REGEX_LANG_MARKER = r'\r?\n[ \t]*(python|bash|javascript|java|c|c\+\+|c#|php|ruby|go|lisp|fortran|basic|assembler|html|css|sql|yaml|typescript|cuda|xml|json)\r?\n'

# Greeting patterns
REGEX_GREETING = r"^\s*(hello|hi|hey|thanks|thank you|you are awesome|awesome)\b.*$"

# File extension map for code snippets
EXTENSION_MAP = {
    'python': '.py',
    'bash': '.sh',
    'javascript': '.js',
    'java': '.java',
    'c': '.c',
    'c++': '.cpp',
    'c#': '.cs',
    'php': '.php',
    'ruby': '.rb',
    'go': '.go',
    'lisp': '.lisp',
    'fortran': '.f90',
    'basic': '.bas',
    'assembler': '.asm',
    'html': '.html',
    'css': '.css',
    'sql': '.sql',
    'typescript': '.ts',
    'yaml': '.yaml',
    'cuda': '.cu',
    'xml': '.xml',
    'json': '.json',
}

# Canvas Undo/Redo configuration
CANVAS_UNDO_HISTORY_LIMIT = 1024