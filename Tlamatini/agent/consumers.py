# agent/consumers.py
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
import json
import asyncio
import re
import sys
import ssl
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from .models import AgentMessage, LLMProgram, LLMSnippet, Omission, Mcp, Tool, Agent, AgentProcess, SessionState
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
from .rag import (
    ask_rag, 
    setup_llm, 
    setup_llm_with_context, 
    request_cancel_generation,
    clear_cancel_generation,
    BasicPromptOnlyChain, 
    OptimizedHistoryAwareRAGChain
)
from .services import (
    generate_tree_view_content, 
    save_files_from_db, 
    process_llm_response
)
from .global_state import global_state
from . import constants

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

class AgentConsumer(AsyncWebsocketConsumer):
    groups = []
    omissions = None

    def __init__(self):
        self.rag_lock = asyncio.Lock()
        self.inet_enabled = False
        self.omissions = ""
        self.mcps = []
        self.tools = []
        self.agents = None
        self.rag_chain = None  # Initialize to None, will be set by setup_rag_chain()

    async def connect(self):
        print("--- WebSocket connect initiated.")
        try:
            self.room_name = 'llm_chat'
            self.room_group_name = f'chat_{self.room_name}'
            print(f"--- Joining room: {self.room_group_name}")

            await self.channel_layer.group_add(  # type: ignore
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            print("--- WebSocket connection accepted and successful.")

        except Exception as e:
            print(f"!!! CONNECTION FAILED: {e}")
            await self.close()
        
        self.heartbeat_task = asyncio.create_task(self.heartbeat())
        
        # Check for existing RAG chain in global_state (persists across WebSocket reconnections)
        user = self.scope.get('user')
        user_id = user.id if user and user.is_authenticated else 'anonymous'
        
        # Key for storing RAG chain per user
        rag_chain_key = f'rag_chain_{user_id}'
        context_key = f'context_path_{user_id}'
        
        existing_rag_chain = global_state.get_state(rag_chain_key)
        existing_context = global_state.get_state(context_key)
        
        if existing_rag_chain is not None:
            # Reuse existing RAG chain - don't rebuild
            print(f"--- Reusing existing RAG chain from global_state for user {user_id}")
            self.rag_chain = existing_rag_chain
            
            # Notify frontend of restored session
            if existing_context:
                session_state = await self.get_session_state(user) if user and user.is_authenticated else None
                if session_state:
                    await self.send_session_restored(session_state)
            
            # Send "Restored the last session" message - with or without context
            if existing_context:
                restore_message = constants.MSG_SESSION_AND_CONTEXT_RESTORED if hasattr(constants, 'MSG_SESSION_AND_CONTEXT_RESTORED') else 'Welcome back, session and context restored.'
            else:
                restore_message = constants.MSG_SESSION_RESTORED if hasattr(constants, 'MSG_SESSION_RESTORED') else 'Welcome back, session restored'
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': restore_message, 'username': 'LLM_Bot'}
            )
            print("--- Session restored message broadcast to room.")
            
            # Re-send MCPs, tools, and agents establishment messages so the frontend gets populated
            mcps = await self.get_all_mcps()
            for mcp in mcps:
                await self.mcp_establishment(mcp['mcpName'], mcp['mcpDescription'], mcp['mcpContent'])
            print("--- MCPs re-established on session restore")
            
            tools = await self.get_all_tools()
            for tool in tools:
                await self.tool_establishment(tool['toolName'], tool['toolDescription'], tool['toolContent'])
            print("--- Tools re-established on session restore")
            
            agents = await self.get_all_agents()
            for agent in agents:
                await self.agent_establishment(agent['agentName'], agent['agentDescription'], agent['agentContent'])
            print("--- Agents re-established on session restore")
        else:
            # No existing RAG chain - check session state for context to restore
            if user and user.is_authenticated:
                session_state = await self.get_session_state(user)
                if session_state and session_state.context_path and not session_state.is_expired():
                    print(f"--- Restoring session state: {session_state.context_type} - {session_state.context_path}")
                    # Notify frontend of restored session
                    await self.send_session_restored(session_state)
                    # Send welcome message with context restored
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_SESSION_AND_CONTEXT_RESTORED if hasattr(constants, 'MSG_SESSION_AND_CONTEXT_RESTORED') else 'Welcome back, session and context restored.', 'username': 'LLM_Bot'}
                    )
                    print("--- Session with context restored message broadcast to room.")
                    # Restore the contextual RAG chain
                    if session_state.context_type == 'directory':
                        asyncio.create_task(self.setup_contextual_rag_chain(session_state.context_path))
                    elif session_state.context_type == 'file':
                        asyncio.create_task(self.setup_contextual_rag_chain(
                            session_state.context_path, 
                            session_state.context_filename
                        ))
                else:
                    asyncio.create_task(self.setup_rag_chain())
            else:
                asyncio.create_task(self.setup_rag_chain())
    
    async def send_session_restored(self, session_state):
        """Notify frontend that a session was restored."""
        try:
            await self.send(text_data=json.dumps({
                'type': 'session-restored',
                'context_path': session_state.context_path,
                'context_type': session_state.context_type,
                'context_filename': session_state.context_filename
            }))
            print("--- Session restored notification sent to client.")
        except Exception as e:
            print(f"Error sending session restored notification: {e}")
    
    @database_sync_to_async
    def get_session_state(self, user):
        """Get session state for user."""
        try:
            return SessionState.objects.get(user=user)
        except SessionState.DoesNotExist:
            return None
    
    @database_sync_to_async
    def save_session_state(self, user, context_path, context_type, context_filename=None):
        """Save session state for user."""
        SessionState.objects.update_or_create(
            user=user,
            defaults={
                'context_path': context_path,
                'context_type': context_type,
                'context_filename': context_filename
            }
        )
    
    @database_sync_to_async
    def clear_session_state(self, user):
        """Clear session state for user."""
        SessionState.objects.filter(user=user).delete()
        
    async def setup_rag_chain(self):
        """Runs the setup_llm in a separate thread to avoid blocking."""
        print("--- Starting RAG chain setup in background thread.")

        db_omisions = await self.get_omission_by_name("omission-1")
        if db_omisions is not None:
            self.omissions = db_omisions.omissionContent
        else:
            self.omissions = ""

        self.mcps = []
        mcps = await self.get_all_mcps()
        for mcp in mcps:
            name = mcp['mcpName']
            desc = mcp['mcpDescription']
            content = mcp['mcpContent']
            await self.mcp_establishment(name, desc, content)
            self.mcps.append({'mcpName': name, 'mcpDescription': desc, 'mcpContent': content})
        print("--- MCPs appended:")
        for mcp in self.mcps:
            print(f"\tMCP: {mcp['mcpName']}, {mcp['mcpDescription']}, {mcp['mcpContent']}")

        self.tools = []
        tools = await self.get_all_tools()
        for tool in tools:
            name = tool['toolName']
            desc = tool['toolDescription']
            content = tool['toolContent']
            await self.tool_establishment(name, desc, content)
            self.tools.append({'toolName': name, 'toolDescription': desc, 'toolContent': content})
        print("--- Tools appended:")
        for tool in self.tools:
            print(f"\tTool: {tool['toolName']}, {tool['toolDescription']}, {tool['toolContent']}")

        self.agents = []
        agents = await self.get_all_agents()
        for agent in agents:
            name = agent['agentName']
            desc = agent['agentDescription']
            content = agent['agentContent']
            await self.agent_establishment(name, desc, content)
            self.agents.append({'agentName': name, 'agentDescription': desc, 'agentContent': content})
        print("--- Agents appended:")
        for agent in self.agents:
            print(f"\tAgent: {agent['agentName']}, {agent['agentDescription']}, {agent['agentContent']}")

        async with self.rag_lock:
            try:
                # Check for cancellation before starting the heavy operation
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Setup cancelled before starting ---")
                    return
                
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.MSG_AGENT_LOADING, 'username': 'LLM_Bot'}
                )
                print("--- Bot loading message broadcast to room.")
                
                # Check for cancellation before the blocking call
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Setup cancelled before LLM creation ---")
                    return
                
                self.rag_chain = await asyncio.to_thread(setup_llm, self.agents, self.mcps, self.tools, self.omissions)
                
                # Check for cancellation after the blocking call completed
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Setup cancelled after LLM creation - discarding result ---")
                    self.rag_chain = None
                    return
                if self.rag_chain is None:
                    print("!!! RAG chain setup failed. Please check the config.json file and Ollama is running.")
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.ERROR_AGENT_NOT_READY, 'username': 'LLM_Bot'}
                    )
                    print("--- Bot error message broadcast to room.")
                    return
                else:
                    print("--- RAG chain setup complete.")
                    # Store RAG chain in global_state for persistence across reconnections
                    user = self.scope.get('user')
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', self.rag_chain)
                    global_state.set_state(f'context_path_{user_id}', None)  # No custom context
                    print(f"--- RAG chain stored in global_state for user {user_id}")
                    
                    if isinstance(self.rag_chain, BasicPromptOnlyChain):
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': constants.MSG_AGENT_FALLBACK, 'username': 'LLM_Bot'}
                        )
                    else:
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': constants.MSG_AGENT_READY, 'username': 'LLM_Bot'}
                        )
                    if isinstance(self.rag_chain, OptimizedHistoryAwareRAGChain):
                        if self.rag_chain.getDetectedOversizedDocs():
                            await self.channel_layer.group_send(   # type: ignore
                                self.room_group_name,
                                {'type': 'agent_message', 'message': constants.MSG_OVERSIZED_DOCS_WARNING, 'username': 'LLM_Bot'}
                            )
                    print("--- Bot ready message broadcast to room.")
                    return
            except Exception as e:
                print(f"!!! ERROR during RAG chain setup: {e}")
                self.rag_chain = None
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.ERROR_AGENT_NOT_READY, 'username': 'LLM_Bot'}
                )
                errorDetail = "Error detail: " + str(e)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': errorDetail, 'username': 'LLM_Bot'}
                )
                print("--- Bot error message broadcast to room.")

    async def setup_contextual_rag_chain(self, path_only, filename=None):
        """Runs the setup_llm_with_context in a separate thread to avoid blocking."""
        print("--- Starting Contextual RAG chain setup in background thread.")

        db_omisions = await self.get_omission_by_name("omission-1")
        if db_omisions:
            self.omissions = db_omisions.omissionContent
        else:
            self.omissions = ""

        self.mcps = []
        mcps = await self.get_all_mcps()
        for mcp in mcps:
            name = mcp['mcpName']
            desc = mcp['mcpDescription']
            content = mcp['mcpContent']
            await self.mcp_establishment(name, desc, content)
            self.mcps.append({'mcpName': name, 'mcpDescription': desc, 'mcpContent': content})
        print("--- MCPs appended:")
        for mcp in self.mcps:
            print(f"\tMCP: {mcp['mcpName']}, {mcp['mcpDescription']}, {mcp['mcpContent']}")

        self.tools = []
        tools = await self.get_all_tools()
        for tool in tools:
            name = tool['toolName']
            desc = tool['toolDescription']
            content = tool['toolContent']
            await self.tool_establishment(name, desc, content)
            self.tools.append({'toolName': name, 'toolDescription': desc, 'toolContent': content})
        print("--- Tools appended:")
        for tool in self.tools:
            print(f"\tTool: {tool['toolName']}, {tool['toolDescription']}, {tool['toolContent']}")

        self.agents = []
        agents = await self.get_all_agents()
        for agent in agents:
            name = agent['agentName']
            desc = agent['agentDescription']
            content = agent['agentContent']
            await self.agent_establishment(name, desc, content)
            self.agents.append({'agentName': name, 'agentDescription': desc, 'agentContent': content})
        print("--- Agents appended:")
        for agent in self.agents:
            print(f"\tAgent: {agent['agentName']}, {agent['agentDescription']}, {agent['agentContent']}")

        async with self.rag_lock:
            try:
                # Check for cancellation before starting the heavy operation
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Contextual setup cancelled before starting ---")
                    return
                
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.MSG_AGENT_LOADING_CONTEXT, 'username': 'LLM_Bot'}
                )
                print("--- Bot loading context broadcast to room.")
                
                # Check for cancellation before the blocking call
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Contextual setup cancelled before LLM creation ---")
                    return
                
                self.rag_chain = await asyncio.to_thread(setup_llm_with_context, path_only, self.agents, self.mcps, self.tools, self.omissions, filename)
                
                # Check for cancellation after the blocking call completed
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Contextual setup cancelled after LLM creation - discarding result ---")
                    self.rag_chain = None
                    return
                
                if self.rag_chain is None:
                    print("!!! Contextual RAG chain setup failed. Please check the config.json file and Ollama is running.")
                    not_ready_response = "Your agent cannot process your requests. <br> check you didn't specify context out of the root directory. <br> If everything is correct, then check Ollama is running and the config.json file is correct."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': not_ready_response, 'username': 'LLM_Bot'}
                    )
                    print("--- Bot error contextual_rag_chain message broadcast to room.")
                    return
                else:
                    # Store RAG chain in global_state for persistence across reconnections
                    user = self.scope.get('user')
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', self.rag_chain)
                    global_state.set_state(f'context_path_{user_id}', path_only)  # Store context path
                    print(f"--- Contextual RAG chain stored in global_state for user {user_id}")
                    
                    if isinstance(self.rag_chain, BasicPromptOnlyChain):
                        fallback_llm_response = "There was a problem, so the agent fallback to a Basic Prompt Only Chain (No context is used)."
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': fallback_llm_response, 'username': 'LLM_Bot'}
                        )
                    else:
                        ready_response = "Your agent is ready. You can now start chatting with the LLM."
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': ready_response, 'username': 'LLM_Bot'}
                        )
                    if isinstance(self.rag_chain, OptimizedHistoryAwareRAGChain):
                        if self.rag_chain.getDetectedOversizedDocs():
                            detected_oversized_docs_warning = "Your agent is ready. But some documents are too large, be aware the LLM might not be able to load them completely."
                            await self.channel_layer.group_send(   # type: ignore
                                self.room_group_name,
                                {'type': 'agent_message', 'message': detected_oversized_docs_warning, 'username': 'LLM_Bot'}
                            )
                    print("--- Bot ready message broadcast to room.")
                    return
            except Exception as e:
                print(f"!!! ERROR during Contextual RAG chain setup: {e}")
                self.rag_chain = None
                not_ready_response = "Your agent cannot process your requests. <br> check you didn't specify context out of the root directory. <br> If everything is correct, then check Ollama is running and the config.json file is correct."
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': not_ready_response, 'username': 'LLM_Bot'}
                )
                errorDetail = "Error detail: " + str(e)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': errorDetail, 'username': 'LLM_Bot'}
                )
                print("--- Bot error message broadcast to room.")

    async def heartbeat(self):
        """
        Sends a heartbeat message every 20 seconds to keep the connection alive.
        """
        while True:
            try:
                await asyncio.sleep(20)
                await self.send(text_data=json.dumps({
                    'type': 'heartbeat',
                    'message': 'ping',
                    'username': 'ping'
                }))
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in heartbeat: {e}")
                break

    async def mcp_establishment(self, mcp_name, mcp_description, mcp_content):
        """
        Sends a mcp establishment message
        """
        print(f"--- Sending establishment of mcp: {mcp_name}...")
        try:
            await self.send(text_data=json.dumps({
                'type': 'mcp',
                'message': mcp_name + '|' + mcp_description + '|' + mcp_content,
                'username': 'system'
            }))
        except Exception as e:
            print(f"Error in mcp_establishment: {e}")

    async def tool_establishment(self, tool_name, tool_description, tool_content):
        """
        Sends a tool establishment message
        """
        print(f"--- Sending establishment of tool: {tool_name}...")
        try:
            await self.send(text_data=json.dumps({
                'type': 'tool',
                'message': tool_name + '|' + tool_description + '|' + tool_content,
                'username': 'system'
            }))
        except Exception as e:
            print(f"Error in tool_establishment: {e}")

    async def agent_establishment(self, agent_name, agent_description, agent_content):
        """
        Sends an agent establishment message
        """
        print(f"--- Sending establishment of agent: {agent_name}...")
        try:
            await self.send(text_data=json.dumps({
                'type': 'agent',
                'message': agent_name + '|' + agent_description + '|' + agent_content,
                'username': 'system'
            }))
        except Exception as e:
            print(f"Error in agent_establishment: {e}")
            
    async def disconnect(self, close_code):   # type: ignore
        print("--- WebSocket disconnected.")
        await self.channel_layer.group_discard(   # type: ignore
            self.room_group_name,
            self.channel_name
        )

    async def queue_llm_retrieval(self, message):
        try:
            # Check if rag_chain is ready
            if self.rag_chain is None:
                print("!!! ERROR: rag_chain is not initialized yet. Please wait for the agent to finish loading.")
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': 'The agent is still loading. Please wait a moment and try again.', 'username': 'LLM_Bot'}
                )
                return
            
            print("--- The message is being procesed by the LLM")
            ask_rag_async = sync_to_async(ask_rag, thread_sensitive=False)
            llm_response = await ask_rag_async(self.rag_chain, {"input": message}, inet_enabled=self.inet_enabled)
            await process_llm_response(llm_response, self.rag_chain, self.channel_layer, self.room_group_name)
        except Exception as e:
            print(f"!!! ERROR in queue_llm_retrieval method: {e}")
            if global_state.get_state('cancel_generation'):
                return
            not_ready_response = "Your agent cannot process your requests. <br> check you didn't specify context out of the root directory. <br> If everything is correct, then check Ollama is running and the config.json file is correct."
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': not_ready_response, 'username': 'LLM_Bot'}
            )
            errorDetail = "Error detail: " + str(e)
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': errorDetail, 'username': 'LLM_Bot'}
            )
            print("--- Bot error message broadcast to room.")

    async def receive(self, text_data):   # type: ignore
        print(f">>> [RECEIVE] Got message: {text_data[:100]}...", flush=True)
        sys.stdout.flush()
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']

            if 'type' in text_data_json:
                type = text_data_json['type']
                print(f">>> [RECEIVE] Message type: {type}", flush=True)
            else:
                type = None
            user = self.scope['user']

            if message == 'ping':
                print("--- Received heartbeat message from client.")
                return
            
            if 'Referenced Rephrase:' in message:
                print("--- Received rephrased-question message from client. It will be ignored...")
                print(f"--- The message(rephrased question) is: {message}")
                return

            if not user.is_authenticated:
                print("!!! User not authenticated. Message rejected.")
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.ERROR_NOT_AUTHENTICATED, 'username': 'LLM_Bot'}
                )
                return
        
            if type == 'set-canvas-as-context':
                print("--- Received set-canvas-as-context message from client.")
                print(f"--- The message(filename) is: {message}")
                if getattr(sys, 'frozen', False):
                    application_path = os.path.dirname(sys.executable)
                else:
                    application_path = os.path.dirname(os.path.abspath(__file__))
                context_files_path = os.path.join(application_path, 'context_files')
                print(f"--- The context_files_path is: {context_files_path}")
                content = text_data_json['content']
                with open(os.path.join(context_files_path, message), 'w', encoding='utf-8') as f:
                    f.write(content)
                print("--- Rebuilding contextual RAG chain....")
                global_state.set_state('chat_hist_summarizer_counter', 0)
                full_context_path = os.path.join(context_files_path, message)
                await self.save_session_state(user, context_files_path, 'file', message)
                print(f"--- Session state saved: file - {full_context_path}")
                await self.send(text_data=json.dumps({
                    'type': 'context-path-set',
                    'context_path': full_context_path
                }))
                asyncio.create_task(self.setup_contextual_rag_chain(context_files_path, message))
                return
            if type == 'unset-canvas-as-context':
                print("--- Received unset-canvas-as-context message from client.")
                global_state.set_state('chat_hist_summarizer_counter', 0)                
                asyncio.create_task(self.setup_rag_chain())
                return
            if type == 'set-directory-as-context':
                print("--- Received set-directory-as-context message from client.")
                print(f"--- The message(directory) is: {message}")
                if getattr(sys, 'frozen', False):
                    application_path = os.path.dirname(sys.executable)
                else:
                    application_path = os.path.dirname(os.path.abspath(__file__))

                selected_path = os.path.join(application_path, message)
                print(f"--- The selected_path is: {selected_path}")
                print(f"--- The application_path is: {application_path}")
                print(f"--- The os.path.commonpath([application_path, selected_path]) is: {os.path.commonpath([application_path, selected_path])}")
                if not os.path.commonpath([application_path, selected_path]) == application_path:
                    error_message = "Selected directory is outside the application root path and is not allowed."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': error_message, 'username': 'LLM_Bot'}
                    )
                    return

                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Your request is being processed by the LLM. Please wait a moment.", 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                print("--- Rebuilding contextual RAG chain....")
                global_state.set_state('chat_hist_summarizer_counter', 0)
                # Save session state for persistence
                context_path = application_path + '/' + message
                await self.save_session_state(user, context_path, 'directory', None)
                print(f"--- Session state saved: directory - {context_path}")
                await self.send(text_data=json.dumps({
                    'type': 'context-path-set',
                    'context_path': context_path
                }))
                asyncio.create_task(self.setup_contextual_rag_chain(context_path))
                return
            
            if type == 'set-file-as-context':
                print("--- Received set-file-as-context message from client.")
                print(f"--- The message(filename) is: {message}")
                if getattr(sys, 'frozen', False):
                    application_path = os.path.dirname(sys.executable) + '/applications/'
                else:
                    application_path = os.path.dirname(os.path.abspath(__file__))
                    
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Your request is being processed by the LLM. Please wait a moment.", 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                global_state.set_state('chat_hist_summarizer_counter', 0)
                # Save session state for persistence
                await self.save_session_state(user, application_path, 'file', message)
                print(f"--- Session state saved: file - {application_path}/{message}")
                asyncio.create_task(self.setup_contextual_rag_chain(application_path, message))
                return            

            if type == 'cancel-current':
                print("--- Received cancel-current message from client. AGGRESSIVELY cancelling LLM...")
                try:
                    # Step 1: Set cancellation flag FIRST (callbacks will check this)
                    request_cancel_generation()
                    print("--- [CANCEL] Cancellation flag set ---")
                    
                    # Step 2: Broadcast cancellation message immediately
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_CANCELLED, 'username': 'LLM_Bot'}
                    )
                    print("--- [CANCEL] Bot message broadcast to room ---")
                    
                    # Step 3: Mark chain as ready (so UI unlocks)
                    global_state.set_state('rag_chain_ready', True)
                    
                    # Step 4: AGGRESSIVELY abort the connection (not graceful close!)
                    connection_destroyed = False
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        if hasattr(self.rag_chain, 'abort_connection'):
                            print("--- [CANCEL] Using abort_connection for AGGRESSIVE teardown ---")
                            self.rag_chain.abort_connection()
                            connection_destroyed = True
                        else:
                            # Fallback to close if abort_connection not available
                            print("--- [CANCEL] Falling back to graceful close ---")
                            client = self.rag_chain.getHttpxClientInstance()
                            if client:
                                client.close()
                                connection_destroyed = True
                    
                    # Step 5: Send confirmation that connection is destroyed
                    if connection_destroyed:
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': constants.MSG_LLM_CONNECTION_DESTROYED, 'username': 'LLM_Bot'}
                        )
                        print("--- [CANCEL] Connection destruction confirmed to user ---")
                    
                    # Step 6: Reset counters
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                    
                    # Step 7: Notify user we are rebuilding
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_REBUILDING, 'username': 'LLM_Bot'}
                    )
                    print("--- [CANCEL] Rebuilding notification sent ---")
                    
                    # Step 8: Clear the cancellation flag BEFORE rebuilding
                    clear_cancel_generation()
                    print("--- [CANCEL] Cancellation flag cleared ---")
                    
                    # Step 8.5: Clear session state and global_state cache to erase context
                    await self.clear_session_state(user)
                    print("--- [CANCEL] Session state cleared ---")
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- [CANCEL] Cleared global_state cache for user {user_id} ---")
                    
                    # Step 9: Rebuild the RAG chain with fresh connection (non-blocking)
                    # Use create_task to avoid deadlock - the old task may still hold the lock
                    print("--- [CANCEL] Scheduling RAG chain rebuild (non-blocking) ---")
                    asyncio.create_task(self.setup_rag_chain())
                    
                    # Step 10: Send confirmation that rebuild is in progress
                    # Note: actual ready message will come from setup_rag_chain when it completes
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_REESTABLISHED, 'username': 'LLM_Bot'}
                    )
                    print("--- [CANCEL] Agent rebuild scheduled, user notified ---")
                    
                except Exception as e:
                    print(f"!!! ERROR while requesting cancellation: {e}")
                    # Still try to notify user of error
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': f'⚠ Cancellation completed with warning: {str(e)[:100]}', 'username': 'LLM_Bot'}
                    )
                return

            if type == 'reconnect-llm-agent':
                print("--- Received reconnect-llm-agent message from client. Attempting to reconnect LLM...")
                try:
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        self.rag_chain.getHttpxClientInstance().close()
                    # Clear global_state cache to force new RAG chain creation
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- Cleared global_state cache for user {user_id}")
                    asyncio.create_task(self.setup_rag_chain())
                    print("--- LLM reconnected.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_RECONNECT, 'username': 'LLM_Bot'}
                    )
                    global_state.set_state('chat_hist_summarizer_counter', 0)                    
                    print("--- LLM reconnected message broadcasted to room.")
                except Exception as e:
                    print(f"!!! ERROR while requesting reconnection: {e}")
                return

            if type == 'clean-history-and-reconnect':
                print("--- Received clean-history-and-reconnect message from client.")
                try:
                    # Delete all AgentMessage records
                    await self.delete_all_messages()
                    print("--- All AgentMessage records deleted.")
                    
                    # Clear global_state cache to force new RAG chain creation
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- Cleared global_state cache for user {user_id}")
                    
                    # Proceed with reconnection
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        self.rag_chain.getHttpxClientInstance().close()
                    asyncio.create_task(self.setup_rag_chain())
                    print("--- LLM reconnected after history clean.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_HISTORY_CLEANED, 'username': 'LLM_Bot'}
                    )
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                except Exception as e:
                    print(f"!!! ERROR while cleaning history: {e}")
                return

            if type == 'clear-context':
                print("--- Received clear-context message from client. Attempting to reconnect LLM...")
                try:
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        self.rag_chain.getHttpxClientInstance().close()
                    # Clear session state
                    await self.clear_session_state(user)
                    print("--- Session state cleared.")
                    # Clear global_state cache to force new RAG chain creation
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- Cleared global_state cache for user {user_id}")
                    asyncio.create_task(self.setup_rag_chain())
                    print("--- LLM context cleaned and reconnected.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_CLEARCONTEXT, 'username': 'LLM_Bot'}
                    )
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                    print("--- LLM context cleaned and reconnected message broadcasted to room.")
                except Exception as e:
                    print(f"!!! ERROR while requesting context clean and reconnection: {e}")
                return

            if type == 'cancel-all':
                print("--- Received cancel-all message from client. Attempting to cancel LLM...")
                try:
                    request_cancel_generation()
                    global_state.set_state('rag_chain_ready', True)
                    if(self.rag_chain):
                        self.rag_chain.getHttpxClientInstance().close()
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                    print("--- LLM cancelled.")
                except Exception as e:
                    print(f"!!! ERROR while requesting cancellation: {e}")
                return

            if type == 'save-files-from-db':
                print("--- Received save-files-from-db message from client.")
                try:
                    print("Wanted to save the following files:")
                    print(message)
                    await save_files_from_db(message, self.channel_layer, self.room_group_name)
                except Exception as e:
                    print(f"!!! ERROR while saving files from DB: {e}")
                return

            if type == 'enable-llm-internet-access':
                print("--- Received enable-llm-internet-access message from client.")
                self.inet_enabled = True
                return
                
            if type == 'disable-llm-internet-access':
                print("--- Received disable-llm-internet-access message from client.")
                self.inet_enabled = False
                return

            if type == 'view-context-dir-in-canvas':
                print("--- Received view-context-dir-in-canvas message from client.")
                directory_name = message
                tree_view_content = generate_tree_view_content(directory_name)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "_tree_:"+tree_view_content, 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-file-omissions':
                print("--- Received set-file-omissions message from client.")
                omissions = message
                if(omissions == '' or omissions.isspace()):
                    print("--- Error omissions are empty. Message rejected.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': "Omissions can't be empty, be sure you introduce extension in the format: jpg,bmp,etc.", 'username': 'LLM_Bot'}
                    )
                    print("--- Bot message broadcast to room.")
                    return
                await self.save_omissions("omission-1", omissions)
                self.omissions = omissions
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Files by extension that will be omitted during context loading saved: "+omissions+".\n\nYou need to restart the agent/connection to apply the changes.", 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-mcps':
                print(f"--- Received set-mcps message from client, message: {message}")
                mcps = message
                if(mcps == '' or mcps.isspace()):
                    print("--- Error mcps are empty. Message rejected.")
                    return
                mcps = message.split(',')
                for mcp in mcps:
                    descAndContent = mcp.split('=')
                    mcpName = 'mcp-' + descAndContent[0] 
                    mcpDescription = descAndContent[1]
                    mcpContent = descAndContent[2]
                    await self.save_mcp(mcpName, mcpDescription, mcpContent)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "MCPs activation: "+message+".\n\nYou need to restart the agent/connection to apply the changes.", 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-tools':
                print(f"--- Received set-tools message from client, message: {message}")
                tools = message
                if(tools == '' or tools.isspace()):
                    print("--- Error tools are empty. Message rejected.")
                    return
                tools = message.split(',')
                for tool in tools:
                    if(tool == '' or tool.isspace()):
                        print("--- End of tools list.")
                        break
                    descAndContent = tool.split('=')
                    toolName = 'tool-' + descAndContent[0]
                    toolDescription = descAndContent[1]
                    toolContent = descAndContent[2]
                    await self.save_tool(toolName, toolDescription, toolContent)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Tools activation: "+message+".\n\nYou need to restart the agent/connection to apply the changes.", 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-agents':
                print(f"--- Received set-agents message from client, message: {message}")
                agents = message
                if(agents == '' or agents.isspace()):
                    print("--- Error agents are empty. Message rejected.")
                    return
                agents = message.split(',')
                for agent in agents:
                    if(agent == '' or agent.isspace()):
                        print("--- End of agents list.")
                        break
                    descAndContent = agent.split('=')
                    agentName = 'agent-' + descAndContent[0]
                    agentDescription = descAndContent[1]
                    agentContent = descAndContent[2]
                    await self.save_agent(agentName, agentDescription, agentContent)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Agents activation: "+message+".\n\nYou need to restart the agent/connection to apply the changes.", 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                return

            if re.match(constants.REGEX_GREETING, message, flags=re.IGNORECASE):
                print("--- User message saved to DB.")
                await self.save_message(user, message)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': message, 'username': user.username}
                )
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.MSG_GREETING_RESPONSE, 'username': 'LLM_Bot'}
                )
                print("--- User question broadcasted to room.")
                return
            
            if not global_state.get_state('rag_chain_ready'):
                print("!!! RAG chain not ready. Message rejected.")
                bot_user, _ = await self.get_or_create_bot_user()
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.ERROR_AGENT_NOT_READY_SIMPLE, 'username': 'LLM_Bot'}
                )
                print("--- Bot message broadcast to room.")
                return
            
            print(f"--- Message parsed: '{message}' from user '{user.username}' **** to be sent to LLM")
            await self.save_message(user, message)
            print("--- User message saved to DB.")
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': message, 'username': user.username}
            )
            print("--- User question broadcasted to room.")
            print("--- User question is now being processed by the LLM.")
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': constants.MSG_PROCESSING_REQUEST, 'username': 'LLM_Bot'}
            )
            print("--- Bot message broadcast to room.")
            asyncio.create_task(self.queue_llm_retrieval(message))
        except Exception as e:
            print(f"!!! ERROR in receive method: {e}")
            not_ready_response = "Your agent cannot process your requests. <br> check you didn't specify context out of the root directory. <br> If everything is correct, then check Ollama is running and the config.json file is correct."
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': not_ready_response, 'username': 'LLM_Bot'}
            )
            errorDetail = "Error detail: " + str(e)
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': errorDetail, 'username': 'LLM_Bot'}
            )
            print("--- Bot error message broadcast to room.")

    async def agent_message(self, event):
        message = event['message']
        username = event['username']
        print(f"--- Sending message to WebSocket: '{message}' from '{username}'")
        await self.send(text_data=json.dumps({
            'message': message,
            'username': username
        }))

    @database_sync_to_async
    def save_message(self, user, message):
        AgentMessage.objects.create(user=user, message=message)

    @database_sync_to_async
    def delete_all_messages(self):
        AgentMessage.objects.all().delete()

    @database_sync_to_async
    def save_program(self, programName, programLanguage, programContent):
        LLMProgram.objects.create(programName=programName, programLanguage=programLanguage, programContent=programContent)

    @database_sync_to_async
    def get_program_by_name(self, programName):
        return LLMProgram.objects.get(programName=programName)

    @database_sync_to_async
    def save_snippet(self, snippetName, snippetLanguage, snippetContent):
        LLMSnippet.objects.create(snippetName=snippetName, snippetLanguage=snippetLanguage, snippetContent=snippetContent)

    @database_sync_to_async
    def save_omissions(self, omissionName, omissionContent):
        Omission.objects.filter(omissionName=omissionName).delete()
        Omission.objects.create(omissionName=omissionName, omissionContent=omissionContent)

    @database_sync_to_async
    def get_omission_by_name(self, omissionName):
        try:
            return Omission.objects.get(omissionName=omissionName)
        except Omission.DoesNotExist:
            return None

    @database_sync_to_async
    def save_mcp(self, mcpName, mcpDescription, mcpContent):
        Mcp.objects.filter(mcpName=mcpName).delete()
        Mcp.objects.create(mcpName=mcpName, mcpDescription=mcpDescription, mcpContent=mcpContent)

    @database_sync_to_async
    def save_tool(self, toolName, toolDescription, toolContent):
        Tool.objects.filter(toolName=toolName).delete()
        Tool.objects.create(toolName=toolName, toolDescription=toolDescription, toolContent=toolContent)

    @database_sync_to_async
    def save_agent(self, agentName, agentDescription, agentContent):
        Agent.objects.filter(agentName=agentName).delete()
        Agent.objects.create(agentName=agentName, agentDescription=agentDescription, agentContent=agentContent)

    @database_sync_to_async
    def save_agent_process(self, agentProcessDescription, agentProcessPid):
        AgentProcess.objects.filter(agentProcessPid=agentProcessPid).delete()
        AgentProcess.objects.create(agentProcessDescription=agentProcessDescription, agentProcessPid=agentProcessPid)

    @database_sync_to_async
    def get_agent_process_by_pid(self, pid):
        try:
            return AgentProcess.objects.get(agentProcessPid=pid)
        except AgentProcess.DoesNotExist:
            return None

    @database_sync_to_async
    def get_agent_process_by_description(self, description):
        try:
            return AgentProcess.objects.get(agentProcessDescription=description)
        except AgentProcess.DoesNotExist:
            return None

    @database_sync_to_async
    def delete_agent_process_by_description(self, description):
        AgentProcess.objects.filter(agentProcessDescription=description).delete()

    @database_sync_to_async
    def get_mcp_by_name(self, mcpName):
        try:
            return Mcp.objects.get(mcpName=mcpName)
        except Mcp.DoesNotExist:
            return None

    @database_sync_to_async
    def get_tool_by_name(self, toolName):
        try:
            return Tool.objects.get(toolName=toolName)
        except Tool.DoesNotExist:
            return None

    @database_sync_to_async
    def get_agent_by_name(self, agentName):
        try:
            return Agent.objects.get(agentName=agentName)
        except Agent.DoesNotExist:
            return None

    @database_sync_to_async
    def get_all_mcps(self):
        """Return all Mcp records (name, description, content) as list of dicts."""
        return list(Mcp.objects.values('mcpName', 'mcpDescription', 'mcpContent'))

    @database_sync_to_async
    def get_all_tools(self):
        """Return all Tool records (name, content) as list of dicts."""
        return list(Tool.objects.values('toolName', 'toolDescription', 'toolContent'))

    @database_sync_to_async
    def get_all_agents(self):
        """Return all Agent records (name, content) as list of dicts."""
        return list(Agent.objects.values('agentName', 'agentDescription', 'agentContent'))

    @database_sync_to_async
    def get_all_agent_processes(self):
        """Return all AgentProcess records (description, pid) as list of dicts."""
        return list(AgentProcess.objects.values('agentProcessDescription', 'agentProcessPid'))

    @database_sync_to_async
    def get_or_create_bot_user(self):
        return User.objects.get_or_create(username='LLM_Bot')
