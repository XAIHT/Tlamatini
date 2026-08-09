# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
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

# Self-knowledge is GATED on the self-modify source tree (2026-08-08). A build
# invoked WITHOUT `--self-modify` ships neither TlamatiniSourceCode/ nor
# Tlamatini.md, so the two now travel together: the presence of this directory
# in the application directory is the single runtime marker of a
# self-able-modify build (prompt.pmt identity rules), and when it is absent
# NOTHING about Tlamatini herself is injected into the system prompt.
SELF_MODIFY_DIRNAME = 'TlamatiniSourceCode'
NOT_SELF_ABLE_MODIFY_NOTICE = (
    "(This is a not-self-able-modify build: your own source tree "
    "'TlamatiniSourceCode/' is not bundled, so no self-knowledge is injected "
    "here. Do not claim to read, edit or rebuild your own code. Speak about "
    "yourself only from these prompt rules and, in Multi-Turn, from your tools "
    "inspecting the running system.)"
)

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

# Self-knowledge is the SAME kind of feature-gated block (2026-08-08). The whole
# <self_knowledge> section — its two long identity bullets AND the injected
# Tlamatini.md — is sentinel-wrapped so a not-self-able-modify build DROPS it
# entirely instead of carrying a large block describing something this build
# does not have. That is the POINT of the default mode: fewer prompt tokens on
# every single request, with the truth stated in ONE short line instead
# (NOT_SELF_MODIFY_MARKERS, kept exactly when the other pair is dropped).
SELF_KNOWLEDGE_MARKERS = ('<!--SELF_KNOWLEDGE_BEGIN-->', '<!--SELF_KNOWLEDGE_END-->')
NOT_SELF_MODIFY_MARKERS = ('<!--NOT_SELF_MODIFY_BEGIN-->', '<!--NOT_SELF_MODIFY_END-->')


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


def is_self_able_modify(application_path: str) -> bool:
    """True when this deployment bundles its OWN source tree.

    ``TlamatiniSourceCode/`` beside prompt.pmt is the single runtime marker of a
    ``build.py --self-modify`` build. Fails CLOSED (False) on any error: the
    cheap, honest answer is "you do not carry your own source", and guessing the
    other way would make Tlamatini claim a capability she does not have.
    """
    try:
        return os.path.isdir(os.path.join(application_path, SELF_MODIFY_DIRNAME))
    except Exception:
        return False


def apply_self_knowledge_blocks(prompt: str, self_able: bool) -> str:
    """Keep XOR drop the whole <self_knowledge> section (fail-open)."""
    try:
        prompt = _resolve_rule_block(prompt, SELF_KNOWLEDGE_MARKERS, self_able)
        prompt = _resolve_rule_block(prompt, NOT_SELF_MODIFY_MARKERS, not self_able)
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

    Gated on the self-modify source tree: when ``TlamatiniSourceCode/`` is NOT
    present beside prompt.pmt, this is a not-self-able-modify build and NO
    self-knowledge is injected — only a short notice saying so. Source and
    self-description ship together (``build.py --self-modify``) or not at all.

    Fails open: a missing, empty, or unreadable file yields a short literal
    notice instead of raising, so it can never break the system prompt.
    """
    # Gate: no bundled source tree => not-self-able-modify => no self-knowledge.
    # The placeholder is still REPLACED (with this notice) rather than left raw:
    # an unreplaced '{self_knowledge}' would become an unexpected f-string input
    # variable in ChatPromptTemplate and break every chain.
    if not is_self_able_modify(application_path):
        return NOT_SELF_ABLE_MODIFY_NOTICE

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

    # Resolve the sentinel-wrapped self-knowledge XOR *first*: in a
    # not-self-able-modify build this drops the whole <self_knowledge> section
    # -- placeholder included -- and keeps the one short honest line instead.
    # ORDER MATTERS: it has to run BEFORE the placeholder replacement below, or
    # the file would be injected into a block that is about to be deleted (and
    # the markers would leak into the prompt the LLM actually reads).
    prompt_template = apply_self_knowledge_blocks(
        prompt_template, is_self_able_modify(application_path))

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
