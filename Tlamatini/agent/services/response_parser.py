import re
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from ..models import LLMProgram, LLMSnippet, AgentMessage
from .. import constants
from .filesystem import get_time_stamp

# Database operations wrapped for async
@sync_to_async
def save_message(user, message):
    AgentMessage.objects.create(user=user, message=message)

@sync_to_async
def save_program(programName, programLanguage, programContent):
    LLMProgram.objects.create(programName=programName, programLanguage=programLanguage, programContent=programContent)

@sync_to_async
def save_snippet(snippetName, snippetLanguage, snippetContent):
    LLMSnippet.objects.create(snippetName=snippetName, snippetLanguage=snippetLanguage, snippetContent=snippetContent)

@sync_to_async
def get_or_create_bot_user():
    return User.objects.get_or_create(username='LLM_Bot')

async def process_llm_response(llm_response, rag_chain, channel_layer, room_group_name):
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
    await save_message(bot_user, llm_response)
    
    if channel_layer:
        await channel_layer.group_send(
            room_group_name,
            {'type': 'agent_message', 'message': llm_response, 'username': 'LLM_Bot'}
        )
    print("--- Bot message broadcast to room.")
    return llm_response
