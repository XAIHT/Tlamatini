# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
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

# The Tlamatini Temp policy surfaces the ABSOLUTE temporary directory to the LLM
# so its instruction ("write all temp files under your Temp directory, never
# outside Tlamatini") is actionable — the LLM can pass this exact path to
# chat_agent_file_creator / execute_command. Resolved through path_guard so it is
# byte-identical to what manage.py / settings.py pin at runtime (frozen: next to
# the .exe; source: the application root).
TEMP_DIRECTORY_PLACEHOLDER = '{temp_directory}'


TEMPLATES_DIRECTORY_PLACEHOLDER = '{templates_directory}'

# ---------------------------------------------------------------------------
# Conditional (feature-gated) rule blocks — weak-model legibility
# ---------------------------------------------------------------------------
# Two large, feature-specific rule blocks in prompt.pmt — the ACPX mechanics
# rule (Rule 12, ~1.8k words) and the Templates-directory rule (Rule 16) — are
# only meaningful when the matching tool surface is actually bound for the
# request. They are wrapped in plain HTML-comment sentinels so the prompt
# assembler can DROP them when their tools are absent, instead of asking a
# smaller model to read and obey instructions for tools it does not have.
#
# The markers are HTML comments (no curly braces) on purpose, so they never
# collide with the f-string template variables ({context}, {system_context},
# {self_knowledge}, …) nor with the brace-escaping in
# mcp_agent._build_system_prompt. Each marker pair may appear MORE THAN ONCE
# (the full Rule block AND its one-line Quick-Map pointer share the same pair),
# so resolution loops over every occurrence. A simple index walk is used (no
# regex backtracking over the very large ACPX block).
ACPX_RULE_MARKERS = ('<!--ACPX_RULES_BEGIN-->', '<!--ACPX_RULES_END-->')
TEMPLATES_RULE_MARKERS = ('<!--TEMPLATES_RULES_BEGIN-->', '<!--TEMPLATES_RULES_END-->')


def _resolve_rule_block(prompt: str, markers: Tuple[str, str], include: bool) -> str:
    begin, end = markers
    while True:
        start = prompt.find(begin)
        if start == -1:
            break
        stop = prompt.find(end, start + len(begin))
        if stop == -1:
            # Unbalanced begin with no following end → strip the stray marker
            # so it never leaks, and stop (malformed prompt revision).
            return prompt.replace(begin, '', 1)
        seg_end = stop + len(end)
        # Swallow one trailing newline after the end marker so neither keeping
        # nor dropping the block leaves a dangling blank line.
        if seg_end < len(prompt) and prompt[seg_end] == '\n':
            seg_end += 1
        if include:
            # Keep the inner content (trim a leading/trailing newline that hugged
            # the markers) and re-terminate with a single newline.
            inner = prompt[start + len(begin):stop]
            if inner.startswith('\n'):
                inner = inner[1:]
            if inner.endswith('\n'):
                inner = inner[:-1]
            prompt = prompt[:start] + inner + '\n' + prompt[seg_end:]
        else:
            # Drop the whole block, markers included.
            prompt = prompt[:start] + prompt[seg_end:]
    return prompt


def apply_conditional_rule_blocks(prompt: str, *, include_acpx: bool,
                                  include_templates: bool) -> str:
    """Resolve the sentinel-wrapped ACPX / Templates rule blocks in a prompt.

    ``include_*=True`` keeps the block's content (stripping just the markers);
    ``False`` removes the whole block. Fails open — a missing marker pair leaves
    the prompt unchanged — so this is safe on any prompt revision and can never
    raise into the prompt-build path.
    """
    try:
        prompt = _resolve_rule_block(prompt, ACPX_RULE_MARKERS, include_acpx)
        prompt = _resolve_rule_block(prompt, TEMPLATES_RULE_MARKERS, include_templates)
    except Exception:
        return prompt
    return prompt


def _resolve_temp_directory_for_prompt() -> str:
    """Return the absolute app Temp directory for prompt injection (fail-open)."""
    try:
        from ..path_guard import get_app_temp_root
        root = get_app_temp_root()
        if root:
            # Brace-escape so a (hypothetical) brace in the path can't be read as
            # an f-string variable by ChatPromptTemplate.
            return root.replace('{', '{{').replace('}', '}}')
    except Exception:
        pass
    return ('your application root\'s "Temp" subdirectory (the folder named '
            'Temp next to your executable in frozen mode, or at the application '
            'root in source mode)')


def _resolve_templates_directory_for_prompt() -> str:
    """Return the absolute app Templates directory for prompt injection (fail-open)."""
    try:
        from ..path_guard import get_app_templates_root
        root = get_app_templates_root()
        if root:
            return root.replace('{', '{{').replace('}', '}}')
    except Exception:
        pass
    return ('your application root\'s "Templates" subdirectory (the folder named '
            'Templates next to your executable in frozen mode, or at the '
            'application root in source mode)')


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

    # Inject the absolute Temp directory into {temp_directory} (same single load
    # site, same .replace-before-template-parse pattern as self-knowledge) so the
    # LLM's "all temp files go under your Temp directory" rule is concrete.
    if TEMP_DIRECTORY_PLACEHOLDER in prompt_template:
        prompt_template = prompt_template.replace(
            TEMP_DIRECTORY_PLACEHOLDER,
            _resolve_temp_directory_for_prompt(),
        )

    # Inject the absolute Templates directory into {templates_directory} so the
    # LLM's "scaffold template projects under your Templates dir" rule is concrete.
    if TEMPLATES_DIRECTORY_PLACEHOLDER in prompt_template:
        prompt_template = prompt_template.replace(
            TEMPLATES_DIRECTORY_PLACEHOLDER,
            _resolve_templates_directory_for_prompt(),
        )

    return config, prompt_template, config_file_path
