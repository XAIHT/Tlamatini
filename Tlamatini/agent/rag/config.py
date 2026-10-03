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
import re
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

# The Self-modify SWITCH (Angela, 2026-10-03).  A build that CAN self-modify
# (``build.py --self-modify``, and EVERY source checkout: dev mode is always
# like --self-modify) may still switch it OFF from the chat toolbar - or have it
# locked OFF because the model cannot hold the self-knowledge.  Then the
# identity bullets give way to this one line and the <self_knowledge> section
# is not sent.  No braces: it is inserted into a prompt template verbatim.
SELF_MODIFY_OFF_NOTICE = (
    "- **Self-modify is switched OFF** (the Self-modify box in the chat toolbar): your "
    "self-knowledge (`Tlamatini.md`) is not loaded into this request, and you must not "
    "read, edit or rebuild your own source code now. If the user asks about your "
    "internals or asks you to change yourself, say so plainly and tell them to tick "
    "Self-modify; answer everything else from these rules and from what your tools observe."
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


# This file lives in agent/rag/, so this is the agent/ directory of the
# checkout: the application directory of a source (not frozen) run.
_SOURCE_AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_application_path() -> str:
    """Where prompt.pmt / config.json live: beside the .exe when frozen, the
    agent/ directory from source - the same rule rag/factory.py follows."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return _SOURCE_AGENT_DIR


def is_source_checkout(application_path) -> bool:
    """True for a source (NOT frozen) run of THIS checkout - dev mode."""
    if getattr(sys, 'frozen', False):
        return False
    try:
        return (os.path.normcase(os.path.realpath(str(application_path)))
                == os.path.normcase(os.path.realpath(_SOURCE_AGENT_DIR)))
    except Exception:
        return False


def self_modify_available(application_path=None) -> bool:
    """Can this deployment self-modify at all?  (Angela, 2026-10-03)

    Dev mode is ALWAYS like ``--self-modify``: a source run of this checkout
    has its own source and its Tlamatini.md, folder or no folder.  A FROZEN
    build only when ``build.py --self-modify`` bundled TlamatiniSourceCode/.
    It decides what the prompt loader injects AND whether the chat shows the
    Self-modify box at all (hidden completely when False).  Fails CLOSED, like
    ``is_self_able_modify``.
    """
    try:
        if application_path is None:
            application_path = default_application_path()
        return is_source_checkout(application_path) or is_self_able_modify(application_path)
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
    if not self_modify_available(application_path):
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
        prompt_template, self_modify_available(application_path))

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


# ---------------------------------------------------------------------------
# The Self-modify SWITCH at request time (Angela, 2026-10-03)
# ---------------------------------------------------------------------------
# load_config_and_prompt resolves the self-knowledge ONCE, for what the build
# CAN do.  The switch decides, per request, whether that text is SENT.  The
# exact text a self-able load injects is recomputed from the files themselves
# (cached on their size and time), so the switch can take it out of any prompt
# built from that load - no marker is ever left in a prompt for this.

_SEGMENT_CACHE: Dict[Any, Tuple[str, ...]] = {}
_SELF_KNOWLEDGE_TAG_RE = re.compile(r"<self_knowledge>.*?</self_knowledge>\n?", re.DOTALL)


def _file_stamp(path):
    try:
        st = os.stat(path)
        return (st.st_mtime_ns, st.st_size)
    except Exception:
        return None


def self_knowledge_segments(application_path=None) -> Tuple[str, ...]:
    """The EXACT text a self-able load puts in the prompt for each
    SELF_KNOWLEDGE block of prompt.pmt: the identity bullets, then the
    <self_knowledge> section with Tlamatini.md injected (brace-escaped, as the
    loader leaves it).  Empty when this deployment cannot self-modify.  Never
    raises."""
    try:
        app = application_path or default_application_path()
        if not self_modify_available(app):
            return ()
        prompt_path = os.path.join(app, 'prompt.pmt')
        key = (os.path.normcase(os.path.abspath(app)), _file_stamp(prompt_path),
               _file_stamp(os.path.join(app, SELF_KNOWLEDGE_FILENAME)))
        cached = _SEGMENT_CACHE.get(key)
        if cached is not None:
            return cached
        with open(prompt_path, 'r', encoding='utf-8') as f:
            text = f.read()
        begin, end = SELF_KNOWLEDGE_MARKERS
        segments = []
        cursor = 0
        while True:
            start = text.find(begin, cursor)
            if start == -1:
                break
            stop = text.find(end, start + len(begin))
            if stop == -1:
                break
            inner = text[start + len(begin):stop]
            # Exactly the trimming _resolve_rule_block does when it KEEPS a block.
            if inner.startswith('\n'):
                inner = inner[1:]
            if inner.endswith('\n'):
                inner = inner[:-1]
            segment = inner + '\n'
            # ...and the same replacements, in the same order, as the loader.
            if SELF_KNOWLEDGE_PLACEHOLDER in segment:
                segment = segment.replace(SELF_KNOWLEDGE_PLACEHOLDER, _load_self_knowledge_block(app))
            if TEMP_DIRECTORY_PLACEHOLDER in segment:
                segment = segment.replace(TEMP_DIRECTORY_PLACEHOLDER, _resolve_temp_directory_for_prompt())
            if TEMPLATES_DIRECTORY_PLACEHOLDER in segment:
                segment = segment.replace(TEMPLATES_DIRECTORY_PLACEHOLDER,
                                          _resolve_templates_directory_for_prompt())
            if segment.strip():
                segments.append(segment)
            cursor = stop + len(end)
        result = tuple(segments)
        if len(_SEGMENT_CACHE) > 8:
            _SEGMENT_CACHE.clear()
        _SEGMENT_CACHE[key] = result
        return result
    except Exception:
        return ()


def self_knowledge_text(application_path=None) -> str:
    """The self-knowledge as plain text (braces NOT escaped) - what Compact
    mode appends to its own prompt when Self-modify is ON and fits."""
    return "".join(self_knowledge_segments(application_path)).replace('{{', '{').replace('}}', '}')


def apply_self_modify_switch(prompt: str, on: bool, application_path=None) -> str:
    """Self-modify OFF: the identity bullets become SELF_MODIFY_OFF_NOTICE and
    the <self_knowledge> section is NOT sent.  ON - or a build that cannot
    self-modify, whose prompt never carried it - returns the prompt unchanged.
    Fail-open: never raises."""
    if on or not prompt:
        return prompt
    try:
        out = prompt
        found = False
        for segment in self_knowledge_segments(application_path):
            if segment in out:
                out = out.replace(segment, '' if found else SELF_MODIFY_OFF_NOTICE + '\n', 1)
                found = True
        if '<self_knowledge>' in out and '</self_knowledge>' in out:
            # A prompt reshaped since the load: never send the section anyway.
            out = _SELF_KNOWLEDGE_TAG_RE.sub('', out, count=1)
        return out
    except Exception:
        return prompt


def self_modify_on() -> bool:
    """The switch as every prompt builder reads it: the build can self-modify,
    the user wants it, and the self-knowledge was not found too big for the
    model.  Fail-open ON - a broken switch keeps the prompt exactly as loaded."""
    try:
        from .. import compact_mode
        return bool(compact_mode.self_modify_active())
    except Exception:
        return True
