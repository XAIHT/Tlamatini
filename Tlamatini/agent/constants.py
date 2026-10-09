# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# agent/constants.py

# ── Tlamatini speaks in the FIRST PERSON (Angela, 2026-10-09) ──────────────
# Every fixed line below is a chat message FROM Tlamatini, and the chat avatar
# reads each one aloud word for word (avatar.js). So they are written the way
# she talks: in the first person, warmly, and to the user by NAME.
#
#   ``{name}`` is filled by ``say(template, name)`` at the send site, with
#   ``display_name(user)``. With no name it drops out cleanly.
#
# ⚠️ Several of these lines are RECOGNISED BY THEIR WORDS. Change a phrase
# here and update its matchers in the same pass, or the chat page stops
# knowing it is busy / ready / restored:
#   * agent_page_ui.js   isBusyMessageRequest / isBusyMessageContext /
#                        isSessionRestoredInfoMessage
#   * agent_page_chat.js the context-directory error branch
#   * avatar.js          classify()
#   * agents/teletlamatini/teletlamatini.py  _NOISE / _FAILURE substrings
#   * .claude/skills/tlamatini-daily-chat-test/harness/config.py markers
# The old (third-person) phrases stay in those matchers on purpose, so a
# chat history or an older server still reads correctly.


def display_name(user):
    """The name Tlamatini calls the user by: the first word of the first
    name, else the username with a capital letter, else ''. Never raises."""
    try:
        first = str(getattr(user, 'first_name', '') or '').strip()
        if first:
            return first.split()[0]
        raw = str(getattr(user, 'username', '') or '').strip()
        return raw[:1].upper() + raw[1:]
    except Exception:  # noqa: BLE001 - a greeting must never break a send
        return ''


def say(template, name=''):
    """Fill ``{name}`` in one of the lines below. With no name the
    placeholder and its comma vanish: "I'm ready, {name}!" -> "I'm ready!"."""
    text = str(template or '')
    name = str(name or '').strip()
    if name:
        return text.replace('{name}', name)
    for gap, keep in ((', {name},', ','), (', {name}', ''), (' {name}', ''), ('{name}', '')):
        text = text.replace(gap, keep)
    return text


# Error messages
ERROR_AGENT_NOT_READY = "I'm sorry, {name}, I can't process your requests right now. <br> Please check that you didn't give me a context outside of the root directory. <br> And please make sure your request can be fitted in my CONTEXT WINDOW: watch the CONTEXT-WINDOW gauge above the message box - when it is red or past 100%, untick agents or tools in Config > Configure Agents / Configure MCPs, or turn on Compact mode. <br> If everything looks right, please check that Ollama is running and that my config.json file is correct."
ERROR_NOT_AUTHENTICATED = "I'm sorry, but you're not authenticated, so I can't help you yet. Please sign in again."
ERROR_AGENT_NOT_READY_SIMPLE = "I'm not ready yet, {name}. Please give me a moment and try again."
ERROR_DIRECTORY_OUTSIDE_ROOT = "I'm sorry, {name}, that directory is outside my application root path, so I'm not allowed to use it."
ERROR_FILE_OUTSIDE_ROOT = "I'm sorry, {name}, that file is outside my application root path, so I'm not allowed to use it."
ERROR_NOT_A_DIRECTORY = "I'm sorry, {name}, what you picked is not a valid directory."
ERROR_INVALID_CANVAS_FILENAME = "I'm sorry, {name}, I received an invalid canvas filename, so I couldn't use it."
ERROR_DETAIL_PREFIX = "This is the error I ran into: "

# System messages
MSG_AGENT_LOADING = "Please wait a moment, {name} - I'm getting myself ready."
MSG_AGENT_LOADING_CONTEXT = "Please wait a moment, {name} - I'm loading the context you gave me."
MSG_AGENT_STILL_LOADING = "I'm still getting ready, {name}. Please wait a moment and try again."
MSG_AGENT_READY = "I'm ready, {name}! You can start chatting with me now."
MSG_AGENT_FALLBACK = "I ran into a problem, {name}, so I switched to my Basic Prompt Only Chain - I'll answer without any context for now."
MSG_OVERSIZED_DOCS_WARNING = "I'm ready, {name}! But some of your documents are too large, so I might not be able to load them completely."
MSG_PROCESSING_REQUEST = "I'm working on your request, {name}. Please wait a moment."
MSG_LLM_CANCELLED = "Okay, {name}, you cancelled it, so I stopped generating. I won't send that answer, and I've erased the context."
MSG_LLM_CONNECTION_DESTROYED = "✓ I've closed my connection to Ollama, so Ollama is free now."
MSG_LLM_REBUILDING = "⏳ I'm rebuilding myself with a fresh connection..."
MSG_LLM_REESTABLISHED = "✓ I'm back and ready, {name}. We can keep chatting now."
MSG_LLM_CANCEL_WARNING = "⚠ I finished cancelling, {name}, but with a warning: "
MSG_LLM_RECONNECT = "I've completed the reconnection you asked for, {name}. I erased the context and I'm connected again."
MSG_LLM_CLEARCONTEXT = "I've cleared the context as you asked, {name}, and I'm connected again."
MSG_LLM_HISTORY_CLEANED = "I've cleared our chat history, {name}, and I'm connected again. We have a fresh start!"
MSG_SESSION_RESTORED = "Welcome back, {name}! I restored our session."
MSG_SESSION_AND_CONTEXT_RESTORED = "Welcome back, {name}! I restored our session and your context."
MSG_GREETING_RESPONSE = "It's a pleasure, {name}! I'm here to help you."
MSG_OMISSIONS_EMPTY = "I need at least one file extension, {name}. Please give them to me in this format: jpg,bmp,etc."
# {omissions} is filled AFTER say(), so the user's own text is never expanded.
MSG_OMISSIONS_SAVED = "I've saved the file extensions I'll skip when I load context: {omissions}.\n\nPlease reconnect me so I can apply the changes, {name}."
MSG_SKILLS_SAVED = "I've updated your skills, {name} ({touched} skill(s)). I'll use the change from your next request."
MSG_TOGGLES_LINKED = "\n\nI also switched these to match: "
MSG_TOGGLES_APPLY = "\n\nI'll use it from your next message, {name} - no restart needed."
MSG_COMPACT_BUSY = "I didn't change Compact mode, {name}: I'm still answering. Please try again when I finish."
MSG_COMPACT_ERROR = "I couldn't change Compact mode, {name}: "
MSG_COMPACT_ON = ("Done, {name}! Compact mode is ON: I unticked every MCP, tool, agent and skill except "
                  "System-Metrics, Files-Search and Current-Time. Tick what you need in "
                  "Config > Configure MCPs / Configure Agents - the CONTEXT-WINDOW gauge shows "
                  "what it costs.")
MSG_COMPACT_OFF = ("Done, {name}! Compact mode is OFF: I ticked every MCP, tool, agent and skill again, "
                   "and your External MCPs are back.")
MSG_SELF_MODIFY_BUSY = "I didn't change Self-modify, {name}: I'm still answering. Please try again when I finish."
MSG_SELF_MODIFY_ERROR = "I couldn't change Self-modify, {name}: "
MSG_SELF_MODIFY_ON = ("Done, {name}! Self-modify is ON: my self-knowledge now goes with every request my model "
                      "can hold, so I can read, change and rebuild my own source.")
MSG_SELF_MODIFY_OFF = ("Done, {name}! Self-modify is OFF: I no longer receive my self-knowledge, and I won't "
                       "read, edit or rebuild my own source code.")
MSG_DROP_NOT_SAVED = "I never saved this message in our history, {name}, so there's nothing for me to drop."
MSG_DROP_STILL_ANSWERING = "I'm still answering, {name}. Please drop the message again when I've finished."

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

# Regex pattern for ASCII / box-drawing diagrams emitted by the LLM
# between BEGIN-DIAGRAM / END-DIAGRAM wrappers (rule 13 in prompt.pmt).
# Mirrors the BEGIN-CODE / END-CODE pair but without a filename slot.
REGEX_DIAGRAM_BLOCK = r'(?:BEGIN-DIAGRAM|begin-diagram)\s*\r?\n([\s\S]*?)\r?\n?(?:END-DIAGRAM|end-diagram)'

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