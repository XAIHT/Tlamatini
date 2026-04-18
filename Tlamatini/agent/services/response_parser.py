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

    parts = ['<div class="exec-report-block">']
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
    parts.append('</div>')
    return "".join(parts)


async def process_llm_response(llm_response, rag_chain, channel_layer, room_group_name, conversation_user=None, tool_calls_log=None, multi_turn_used=None, exec_report_enabled=False, exec_report_entries=None):
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
    print("\n--- The LLM response after cleaning is: <<<<<\n"+llm_response+"\n>>>>>")   

    print("\n--- The final parsed/cleaned LLM response is: "+llm_response)
    print("\n--- We take the parsed/processed response by the LLM and save it to the DB")
    bot_user, _ = await get_or_create_bot_user()
    await save_message(bot_user, llm_response, conversation_user=conversation_user)
    
    # When multi-turn was used with tool calls, ask the LLM to classify
    # the answer as success or failure so the frontend can decide whether
    # to show the "Create Flow" button.
    answer_success = None
    if multi_turn_used and tool_calls_log:
        print("--- AnswerAnalizer: classifying multi-turn answer...")
        answer_success = await analyze_answer_success(llm_response)
        print(f"--- AnswerAnalizer: verdict = {'SUCCESS' if answer_success else 'FAILURE'}")

    # Append the Exec report HTML (one per-agent table per state-changing
    # tool that fired) to the final answer, but only when the user enabled
    # the Exec report checkbox AND at least one capture was recorded. The
    # SUCCESS/FAILURE classification above already ran against the original
    # answer, so the appended tables don't bias that verdict.
    entries_count = len(exec_report_entries) if exec_report_entries else 0
    print(
        f"--- process_llm_response: exec_report_enabled={exec_report_enabled} "
        f"exec_report_entries_count={entries_count}"
    )
    if exec_report_enabled:
        exec_report_html = _render_exec_report_html(exec_report_entries)
        if exec_report_html:
            llm_response = llm_response + exec_report_html
            print(f"--- process_llm_response: appended exec_report HTML ({len(exec_report_html)} chars)")
        else:
            print("--- process_llm_response: exec_report HTML empty (no state-changing tool rows captured)")

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
