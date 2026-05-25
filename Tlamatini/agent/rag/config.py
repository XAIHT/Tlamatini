import os
import sys
import json
from typing import Tuple, Dict, Any

# The LLM's self-knowledge file. It is read from the same application directory
# as prompt.pmt / config.json (the install root next to the executable in
# frozen mode, agent/ in source mode) and injected into the {self_knowledge}
# placeholder of prompt.pmt at prompt-build time.
SELF_KNOWLEDGE_FILENAME = 'Tlamatini.md'
SELF_KNOWLEDGE_PLACEHOLDER = '{self_knowledge}'


def _load_self_knowledge_block(application_path: str) -> str:
    """Return the contents of Tlamatini.md, brace-escaped for prompt templates.

    The prompt template is consumed via ``ChatPromptTemplate.from_messages``
    (f-string format), where single ``{`` / ``}`` mark input variables. The
    self-knowledge markdown may contain braces inside code snippets, so every
    brace is doubled here to keep the whole block literal — the real template
    variables ({system_context}, {files_context}, {context}) are untouched
    because they live in prompt.pmt, not inside this injected text.

    Fails open: a missing, empty, or unreadable file yields a short literal
    notice instead of raising, so it can never break the system prompt.
    """
    self_knowledge_path = os.path.join(application_path, SELF_KNOWLEDGE_FILENAME)
    try:
        with open(self_knowledge_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        if not content:
            raise ValueError('empty self-knowledge file')
    except Exception:
        content = (
            f"(Your self-knowledge file '{SELF_KNOWLEDGE_FILENAME}' is not "
            "available in this deployment; rely on these prompt rules and, in "
            "Multi-Turn, on your tools to inspect the running system.)"
        )
    return content.replace('{', '{{').replace('}', '}}')


def load_config_and_prompt(application_path: str) -> Tuple[Dict[str, Any], str, str]:
    config_file_path = os.path.join(application_path, 'config.json')
    prompt_file_path = os.path.join(application_path, 'prompt.pmt')

    for path, name in [(config_file_path, 'config.json'), (prompt_file_path, 'prompt.pmt')]:
        if not os.path.exists(path):
            print(f"--- Critical Error: Required configuration file '{name}' not found in application directory.")
            print(f"--- Expected location: {path}")
            print("--- Please ensure all required configuration files are present before running the application.")
            sys.exit(1)

    with open(config_file_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    with open(prompt_file_path, 'r', encoding='utf-8') as f:
        prompt_template = f.read()

    # Inject the live self-knowledge file into the {self_knowledge} placeholder
    # (when present) before the template reaches ChatPromptTemplate. Resolving
    # it here — the single load site for prompt.pmt — covers every chain (basic,
    # history-aware, unified, prompt-only) without adding a new input variable.
    if SELF_KNOWLEDGE_PLACEHOLDER in prompt_template:
        prompt_template = prompt_template.replace(
            SELF_KNOWLEDGE_PLACEHOLDER,
            _load_self_knowledge_block(application_path),
        )

    return config, prompt_template, config_file_path
