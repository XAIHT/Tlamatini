import re
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from ..models import LLMProgram, LLMSnippet, AgentMessage
from .. import constants
from .filesystem import get_time_stamp
from .answer_analizer import analyze_answer_success

# Database operations wrapped for async
@sync_to_async
def save_message(user, message, conversation_user=None):
    AgentMessage.objects.create(user=user, conversation_user=conversation_user, message=message)

@sync_to_async
def save_program(programName, programLanguage, programContent):
    LLMProgram.objects.create(programName=programName, programLanguage=programLanguage, programContent=programContent)

@sync_to_async
def save_snippet(snippetName, snippetLanguage, snippetContent):
    LLMSnippet.objects.create(snippetName=snippetName, snippetLanguage=snippetLanguage, snippetContent=snippetContent)

@sync_to_async
def get_or_create_bot_user():
    return User.objects.get_or_create(username='Tlamatini')

# Sentinel string inserted between the answer prose and the system-appended
# Execution Report / Ask-Execs denial banner. The frontend
# (agent_page_chat.js::buildAutomatedMessageElement) splits the saved message on
# this marker and renders each half in its OWN innerHTML parse, so a malformed /
# unclosed HTML table in the answer body (prompt.pmt rule 6) can NEVER absorb the
# execution tables via the browser's HTML-parser foster-parenting. It is an HTML
# comment so that an old / cached frontend that doesn't know to split degrades
# gracefully (the marker renders invisibly instead of as literal text). Keep this
# value byte-for-byte in sync with the constant in agent_page_chat.js.
EXEC_REPORT_BOUNDARY = "<!--TLAMATINI_EXEC_REPORT_BOUNDARY-->"


def _html_escape(text):
    if text is None:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# --- ASCII / box-drawing diagram rendering ----------------------------------
# Diagrams produced by the LLM (rule 13 in prompt.pmt) need a fixed-width font
# and preserved whitespace, otherwise the columns drift in the chat's default
# proportional font. Two pipelines feed the same renderer:
#   1. Explicit BEGIN-DIAGRAM / END-DIAGRAM blocks (when the LLM cooperates).
#   2. Auto-detection of consecutive lines that look like ASCII art (safety
#      net for older messages and uncooperative outputs).
# Both replace the matched region with a placeholder of the form
#   \x00DGRM_<idx>\x00
# so the bold/inline-code/lang-marker substitutions that run later cannot
# touch the diagram contents. Placeholders are restored last, expanding into
# <pre class="ascii-diagram">HTML-escaped diagram</pre>.

# U+2500..U+257F = the full Unicode "Box Drawing" block (─, │, ┌, ┐, ┼, etc.)
_BOX_DRAWING_RE = re.compile('[─-╿]')
# Common arrow / triangle glyphs used in flowcharts: ▲ ▼ ▶ ◀ → ← ↑ ↓ and the
# 8 directional arrows in U+2190..U+2199.
_FLOWCHART_ARROW_RE = re.compile('[▲▼▶◀←-↙]')
_ASCII_ART_RUN_RE = re.compile(r'[+\-=|]{3,}')
_PIPED_BOX_LINE_RE = re.compile(r'^\s*\|.*\|\s*$')
_DIAGRAM_PLACEHOLDER_RE = re.compile(r'\x00DGRM_\d+\x00')
# A genuine ASCII / box-drawing diagram is PLAIN TEXT. A line carrying a real
# HTML tag must NEVER be auto-detected as a diagram row — otherwise
# _html_escape() turns it into unclickable raw source text. This is the root of
# two reported bugs that fire only when >= 2 such lines are consecutive (the
# auto-detector's minimum run):
#   1. The injected "Load in canvas" anchors — `<a ... onclick="loadCanvas(..)">
#      ---Load in canvas: NAME---</a>` — whose `---` label matches the ASCII-art
#      run, so a multi-program answer renders its anchors as escaped text and the
#      user cannot click them to load the code into the canvas.
#   2. An LLM-emitted HTML list whose <li> lines contain a `->`/arrow glyph that
#      matches the flowchart-arrow heuristic, so the list shows as raw source.
# The pattern matches an actual tag open/close (`<a `, `<li>`, `<code…`, `<br>`,
# `</a>`, `<h2>`, …) WITHOUT tripping on ASCII art like `<--->`, `<==`, or
# `a < b` (a `<` not immediately followed by a letter is left alone).
_HTML_TAG_RE = re.compile(r'</?[A-Za-z][A-Za-z0-9]*(?:\s|/?>)')


def _is_diagram_line(line):
    """Heuristic: does this single line look like part of an ASCII diagram?"""
    if not line.strip():
        return False
    if _HTML_TAG_RE.search(line):
        # Carries real HTML markup (anchor / list / inline code / break) — this
        # is rendered prose, not a fixed-width diagram. Never auto-wrap it.
        return False
    if _DIAGRAM_PLACEHOLDER_RE.search(line):
        # Lines that already collapsed into a placeholder count as diagram
        # rows so adjacent diagram-like lines extend the same block.
        return True
    if _BOX_DRAWING_RE.search(line):
        return True
    if _FLOWCHART_ARROW_RE.search(line):
        return True
    if _ASCII_ART_RUN_RE.search(line):
        return True
    if _PIPED_BOX_LINE_RE.match(line):
        return True
    return False


def _wrap_diagram_blocks(llm_response):
    """Replace explicit BEGIN-DIAGRAM blocks AND auto-detected ASCII-art runs
    with `\\x00DGRM_<idx>\\x00` placeholders. Returns
    (transformed_text, placeholder_html_list). Pure text-in / text-out — no
    side effects, so the caller can run later HTML substitutions safely.
    """
    placeholders = []

    def _make_placeholder(body):
        body = body.strip("\r\n")
        idx = len(placeholders)
        placeholders.append(
            f'<pre class="ascii-diagram">{_html_escape(body)}</pre>'
        )
        return f'\x00DGRM_{idx}\x00'

    # Pass 1 — explicit BEGIN-DIAGRAM / END-DIAGRAM blocks (the cooperative
    # path; mirrors the BEGIN-CODE / END-CODE convention).
    llm_response = re.sub(
        constants.REGEX_DIAGRAM_BLOCK,
        lambda m: _make_placeholder(m.group(1)),
        llm_response,
        flags=re.IGNORECASE,
    )

    # Pass 2 — auto-detect runs of >= 2 consecutive diagram-like lines, with
    # at most one blank line allowed inside the run. Trims trailing blanks.
    lines = llm_response.split("\n")
    out_lines = []
    i = 0
    n = len(lines)
    while i < n:
        if _is_diagram_line(lines[i]):
            j = i + 1
            saw_blank = False
            while j < n:
                if _is_diagram_line(lines[j]):
                    saw_blank = False
                    j += 1
                elif not lines[j].strip() and not saw_blank:
                    saw_blank = True
                    j += 1
                else:
                    break
            while j > i and not lines[j - 1].strip():
                j -= 1
            if j - i >= 2:
                out_lines.append(_make_placeholder("\n".join(lines[i:j])))
                i = j
                continue
        out_lines.append(lines[i])
        i += 1
    llm_response = "\n".join(out_lines)

    return llm_response, placeholders


def _restore_diagram_placeholders(text, placeholders):
    """Swap each `\\x00DGRM_<idx>\\x00` token back to its
    <pre class="ascii-diagram">…</pre> HTML."""
    for idx, html in enumerate(placeholders):
        text = text.replace(f'\x00DGRM_{idx}\x00', html)
    return text


def _render_exec_report_html(exec_report_entries):
    """Build the HTML rendered at the tail of a multi-turn answer when the
    user enabled the Exec report toggle. Entries are grouped by
    ``agent_key`` and each group becomes a separate table with a caption
    like "List of <Agent> Operations". Each table uses the CSS class
    ``exec-report-<agent_key>`` / ``exec-report-caption-<agent_key>`` so
    its colours mirror the matching canvas-item gradient. Returns an empty
    string when no state-changing tool calls were captured, letting the
    caller skip appending anything.
    """
    entries = [row for row in (exec_report_entries or []) if (row or {}).get("command")]
    if not entries:
        return ""

    # Preserve first-appearance order of agent_keys so the tables stack in
    # execution order rather than alphabetical order.
    ordered_keys: list[str] = []
    buckets: dict[str, list[dict]] = {}
    display_names: dict[str, str] = {}
    for row in entries:
        agent_key = str(row.get("agent_key") or "").strip() or "other"
        if agent_key not in buckets:
            ordered_keys.append(agent_key)
            buckets[agent_key] = []
            display_names[agent_key] = str(row.get("agent_display") or agent_key.title())
        buckets[agent_key].append(row)

    # Wrap the whole report in a self-contained FRAME so the execution tables
    # can never visually blend into the answer body (or the answer's own HTML
    # tables — prompt.pmt rule 6). The frame opens with a divider + a labelled
    # header bar, then the per-agent tables, so the boundary is unmistakable.
    parts = [
        '<div class="exec-report-frame">',
        '<div class="exec-report-divider" aria-hidden="true"></div>',
        '<div class="exec-report-header">',
        '<span class="exec-report-header-icon" aria-hidden="true">&#9881;</span>',
        '<span class="exec-report-header-title">Last Executions</span>',
        '<span class="exec-report-header-sub">A standalone card of the tools that '
        'actually ran &mdash; kept completely separate from the answer above.</span>',
        '</div>',
        '<div class="exec-report-block">',
    ]
    for agent_key in ordered_keys:
        rows = buckets[agent_key]
        display = display_names[agent_key]
        parts.append(
            f'<table class="exec-report-table exec-report-{_html_escape(agent_key)}">'
        )
        parts.append(
            f'<caption class="exec-report-caption exec-report-caption-{_html_escape(agent_key)}">'
            f'List of {_html_escape(display)} Operations</caption>'
        )
        parts.append(
            '<thead><tr>'
            '<th class="exec-report-col-cmd">Command</th>'
            '<th class="exec-report-col-status">Status</th>'
            '</tr></thead><tbody>'
        )
        for row in rows:
            success = bool(row.get("success"))
            status_cls = "exec-report-success" if success else "exec-report-failure"
            status_txt = "SUCCESS" if success else "FAILURE"
            parts.append(
                '<tr>'
                '<td class="exec-report-col-cmd"><pre class="exec-report-cmd">'
                f'{_html_escape(row.get("command", ""))}</pre></td>'
                f'<td class="exec-report-col-status {status_cls}">{status_txt}</td>'
                '</tr>'
            )
        parts.append('</tbody></table>')
    parts.append('</div>')   # .exec-report-block
    parts.append('</div>')   # .exec-report-frame
    return "".join(parts)


def _render_exec_denied_banner(exec_report_denied):
    """Build the big red "Execution interrupted" banner shown when the user
    DENIED a tool under Ask Execs. Surfaces what was denied (kind, agent/tool,
    program/command, and shell). Returns an empty string when nothing was
    denied. Independent of the Exec report toggle — the banner always shows on
    a denial so the user can see exactly which step was stopped."""
    denied = exec_report_denied or {}
    if not denied:
        return ""
    kind = _html_escape(denied.get("kind") or "Tool")
    agent = _html_escape(denied.get("agent_display") or denied.get("tool_name") or "operation")
    command = _html_escape(denied.get("command") or "")
    shell = _html_escape(denied.get("shell") or "")
    parameters = _html_escape(denied.get("parameters") or "")

    parts = ['<div class="exec-denied-banner">']
    parts.append('<div class="exec-denied-icon" aria-hidden="true">&#9940;</div>')
    parts.append('<div class="exec-denied-body">')
    parts.append('<div class="exec-denied-title">Execution interrupted</div>')
    parts.append(
        '<div class="exec-denied-sub">You denied the '
        f'{kind} <strong>{agent}</strong> from executing. The Multi-Turn chain '
        'was halted at this step — no further tools were run.</div>'
    )
    if command:
        parts.append(
            '<div class="exec-denied-detail">'
            '<span class="exec-denied-label">Denied program / command</span>'
            f'<pre class="exec-denied-cmd">{command}</pre></div>'
        )
    if shell:
        parts.append(
            '<div class="exec-denied-detail">'
            '<span class="exec-denied-label">Shell</span>'
            f'<pre class="exec-denied-cmd">{shell}</pre></div>'
        )
    if parameters:
        parts.append(
            '<div class="exec-denied-detail">'
            '<span class="exec-denied-label">Parameters</span>'
            f'<pre class="exec-denied-cmd">{parameters}</pre></div>'
        )
    parts.append('</div></div>')
    return "".join(parts)


async def process_llm_response(llm_response, rag_chain, channel_layer, room_group_name, conversation_user=None, tool_calls_log=None, multi_turn_used=None, exec_report_enabled=False, exec_report_entries=None, exec_report_denied=None):
    """
    Process the LLM response: extract snippets/programs, save to DB, clean response, and broadcast.
    """
    print("\n--- The Original LLM response is: <<<<<\n"+llm_response+"\n>>>>>")
    
    # Extract and save snippets
    snippets = re.findall(constants.REGEX_SNIPPET_WITH_LANG, llm_response, flags=re.IGNORECASE)
    for snippet in snippets:
        snippetLanguage = snippet[0]
        snippetContent = snippet[1]
        extension = constants.EXTENSION_MAP.get(snippetLanguage, '.txt')
        snippetName = get_time_stamp() + "_" + snippetLanguage + extension
        await save_snippet(snippetName, snippetLanguage, snippetContent)
        print("\n--- Saved snippet: "+snippetName)

        # ALWAYS escape HTML entities for display to prevent browser rendering of tags
        # This fixes the issue where XML/HTML content was invisible
        htmlToRenderAsText = re.sub("<", "&lt;", snippetContent, flags=re.IGNORECASE)
        htmlToRenderAsText = re.sub(">", "&gt;", htmlToRenderAsText, flags=re.IGNORECASE)
        llm_response = llm_response.replace(snippetContent, htmlToRenderAsText)
        
        if (snippetLanguage == 'html' or snippetLanguage == 'xml'):
             print(f"\n--- {snippetLanguage} snippet re-rendered as text for visibility")

    # Extract and save programs
    programs = re.findall(constants.REGEX_NAMED_CODE_BLOCK, llm_response, flags=re.IGNORECASE)
    for program in programs:
        programName = program[1]
        programContent = program[2]
        programCodeInAposLang = re.match(constants.REGEX_SNIPPET_WITH_LANG, programContent, flags=re.IGNORECASE)
        
        program2Save = ""
        finalProgramName = ""
        lang = ""
        
        if programCodeInAposLang:
            programContent = programCodeInAposLang.group(2)
            program2Save = programContent.replace('```', '')
            lang = programCodeInAposLang.group(1)
            
            # Sanitize name
            programName = re.sub(r'[\\]+', '(backslash)', programName)
            programName = re.sub(r'[/]+', '(slash)', programName)
            programName = re.sub(r'[\s]+', '(space)', programName)
            finalProgramName = get_time_stamp() + "_" + programName
            
            await save_program(finalProgramName, lang, program2Save)
            if rag_chain:
                rag_chain.setLastProgramName(finalProgramName)
            print("\n--- Saved program: "+finalProgramName)
            llm_response = llm_response.replace(programCodeInAposLang.group(0), "<a href='#' style='font-weight: 600; color: white !important;' onclick='loadCanvas(" + '"' + finalProgramName + '"' + ");'>---Load in canvas: "+finalProgramName+"---</a><br>")
        else:
            program2Save = programContent.replace('```', '')
            
            # Sanitize name
            programName = re.sub(r'[\\]+', '(backslash)', programName)
            programName = re.sub(r'[/]+', '(slash)', programName)
            programName = re.sub(r'[\s]+', '(space)', programName)
            finalProgramName = get_time_stamp() + "_" + programName
            
            await save_program(finalProgramName, 'by-extension', program2Save)
            if rag_chain:
                rag_chain.setLastProgramName(finalProgramName)
            print("\n--- Saved program: "+finalProgramName)
            llm_response = llm_response.replace(programContent, "<a href='#' style='font-weight: 600; color: white !important;' onclick='loadCanvas(" + '"' + finalProgramName + '"' + ");'>---Load in canvas: "+finalProgramName+"---</a><br>")

    # Handle unnamed code blocks
    for m in re.finditer(constants.REGEX_UNNAMED_CODE_BLOCK, llm_response, flags=re.IGNORECASE):
        programContent = m.group(1)
        baseName = 'Without_Name'
        programName = get_time_stamp() + "_" + baseName
        programCodeInAposLang = re.match(constants.REGEX_SNIPPET_WITH_LANG, programContent, flags=re.IGNORECASE)
        
        if programCodeInAposLang:
            contentInner = programCodeInAposLang.group(2)
            program2Save = contentInner.replace('```', '')
            await save_program(programName, programCodeInAposLang.group(1), program2Save)
            if rag_chain:
                rag_chain.setLastProgramName(programName)
            print("\n--- Saved program: "+programName)
            llm_response = llm_response.replace(m.group(0), "<a href='#' style='font-weight: 600; color: white !important;' onclick='loadCanvas(" + '"' + programName + '"' + ");'>---Load in canvas: "+programName+"---</a><br>")
        else:
            program2Save = programContent.replace('```', '')
            await save_program(programName, 'by-extension', program2Save)
            if rag_chain:
                rag_chain.setLastProgramName(programName)
            print("\n--- Saved program: "+programName)
            llm_response = llm_response.replace(m.group(0), "<a href='#' style='font-weight: 600; color: white !important;' onclick='loadCanvas(" + '"' + programName + '"' + ");'>---Load in canvas: "+programName+"---</a><br>")
    
    # Clean up response
    llm_response = re.sub(constants.REGEX_CODE_BEGIN, "", llm_response)
    llm_response = re.sub(constants.REGEX_CODE_END, "", llm_response)
    llm_response = re.sub(constants.REGEX_CODE_APOS, "", llm_response)

    # ASCII / box-drawing diagram capture — must run BEFORE the bold / inline
    # code / lang-marker / END-RESPONSE substitutions below, otherwise those
    # regex passes can mangle box-drawing characters and inline `*` / `` ` ``
    # glyphs that legitimately appear inside a diagram. Placeholders are
    # restored after every substitution has finished.
    llm_response, _diagram_placeholders = _wrap_diagram_blocks(llm_response)

    langs = re.findall(constants.REGEX_LANG_MARKER, llm_response)
    for lang in langs:
        llm_response = re.sub(r'\r?\n[ \t]*' + re.escape(lang) + r'\r?\n', f'\n  {lang}:\n', llm_response)

    llm_response = re.sub(constants.REGEX_DOUBLE_BR, '<br>', llm_response)
    llm_response = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', llm_response)

    llm_response = re.sub(
        r'`([^`]+)`',
        lambda m: '<code>' + m.group(1).replace('<', '&lt;').replace('>', '&gt;') + '</code>',
        llm_response
    )

    llm_response = re.sub(
        r'\r?\n?END-RESPONSE\r?\n?',
        lambda m: '<br>',
        llm_response
    )

    # Swap diagram placeholders back to their <pre class="ascii-diagram">…
    # </pre> HTML now that no further regex passes will run over the answer.
    llm_response = _restore_diagram_placeholders(llm_response, _diagram_placeholders)

    print("\n--- The LLM response after cleaning is: <<<<<\n"+llm_response+"\n>>>>>")

    print("\n--- The final parsed/cleaned LLM response is: "+llm_response)

    # When multi-turn was used with tool calls, ask the LLM to classify
    # the answer as success or failure so the frontend can decide whether
    # to show the "Create Flow" button. Classification runs against the
    # prose answer BEFORE the exec report tables are appended so the
    # tables don't bias the verdict.
    answer_success = None
    if multi_turn_used and tool_calls_log:
        print("--- AnswerAnalizer: classifying multi-turn answer...")
        answer_success = await analyze_answer_success(llm_response)
        print(f"--- AnswerAnalizer: verdict = {'SUCCESS' if answer_success else 'FAILURE'}")

    # Build the system-appended section (Exec report tables + Ask-Execs denial
    # banner) SEPARATELY from the answer prose, then join it on with the
    # EXEC_REPORT_BOUNDARY sentinel. The sentinel — not bare concatenation — is
    # what guarantees the execution tables can never visually merge into the
    # answer body: the frontend splits on it and parses each half as its own
    # innerHTML, so an unclosed HTML table in the prose (prompt.pmt rule 6)
    # cannot foster-parent the exec tables into itself. The frame markup +
    # boundary together are belt-and-suspenders.
    system_section_parts = []

    # Exec report HTML (one per-agent table per state-changing tool that fired),
    # but only when the user enabled the Exec report checkbox AND at least one
    # capture was recorded.
    entries_count = len(exec_report_entries) if exec_report_entries else 0
    print(
        f"--- process_llm_response: exec_report_enabled={exec_report_enabled} "
        f"exec_report_entries_count={entries_count}"
    )
    if exec_report_enabled:
        exec_report_html = _render_exec_report_html(exec_report_entries)
        if exec_report_html:
            system_section_parts.append(exec_report_html)
            print(f"--- process_llm_response: appended exec_report HTML ({len(exec_report_html)} chars)")
        else:
            print("--- process_llm_response: exec_report HTML empty (no state-changing tool rows captured)")

    # The red "Execution interrupted" banner when the user DENIED a tool under
    # Ask Execs. It goes AFTER the exec report tables (so the user first sees
    # what DID execute, then the big stop indicating where the chain was halted)
    # but is NOT gated on exec_report_enabled — a denial always shows the banner.
    if exec_report_denied:
        denied_banner = _render_exec_denied_banner(exec_report_denied)
        if denied_banner:
            system_section_parts.append(denied_banner)
            print("--- process_llm_response: appended Ask-Execs denial banner")

    # Join the isolated system section onto the answer with the boundary
    # sentinel — only when there is something to append, so a plain answer is
    # never followed by a stray marker. Persisted into the saved message verbatim
    # so a chat reload splits and re-isolates it identically.
    if system_section_parts:
        llm_response = llm_response + EXEC_REPORT_BOUNDARY + "".join(system_section_parts)

    # Persist the final message — including any appended exec report tables —
    # so reloading the chat history restores the exec report HTML verbatim,
    # independently of the SUCCESS/FAILURE verdict above.
    print("\n--- We take the parsed/processed response by the LLM and save it to the DB")
    bot_user, _ = await get_or_create_bot_user()
    await save_message(bot_user, llm_response, conversation_user=conversation_user)

    if channel_layer:
        broadcast_msg = {'type': 'agent_message', 'message': llm_response, 'username': 'Tlamatini'}
        if tool_calls_log:
            broadcast_msg['tool_calls_log'] = tool_calls_log
        if multi_turn_used:
            broadcast_msg['multi_turn_used'] = True
        if answer_success is not None:
            broadcast_msg['answer_success'] = answer_success
        await channel_layer.group_send(room_group_name, broadcast_msg)
    print("--- Bot message broadcast to room.")
    return llm_response
