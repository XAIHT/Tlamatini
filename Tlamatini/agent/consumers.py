# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
# agent/consumers.py
import os
os.environ['OMP_NUM_THREADS'] = '1'
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
import json
import asyncio
import re
import sys
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import User
from django.db.models import Max
from .models import AgentMessage, LLMProgram, LLMSnippet, Omission, Mcp, Tool, Agent, AgentProcess, SessionState, Skill
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
from .chat_history_loader import DBChatHistoryLoader
from .global_state import global_state
from .path_guard import get_runtime_agent_root, resolve_runtime_agent_path, safe_join_under
from . import constants
# Per-line USER attribution for tlamatini.log. Importing it is all that is
# needed: the module installs itself into manage.py's tee hook and makes child
# threads inherit the tag. See agent/log_identity.py for the full contract.
from . import log_identity

# Per-frame WebSocket receive tracing (a print + forced stdout flush on EVERY
# incoming chat/control frame) is too expensive for default runtime. Deep
# tracing stays one environment variable away: set TLAMATINI_WS_TRACE=1 to
# restore it (speed batch, 2026-07-02). Errors, reaper notices and permission
# failures are NOT gated by this — only the per-frame trace prints are.
_WS_TRACE = (os.environ.get('TLAMATINI_WS_TRACE') or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def _sanitize_context_filename(filename):
    if not isinstance(filename, str):
        return None

    candidate = filename.strip()
    if not candidate or candidate in {'.', '..'}:
        return None

    if os.path.basename(candidate) != candidate:
        return None

    if re.search(r'[\/\x00-\x1F<>:"|?*]', candidate):
        return None

    return candidate


def _normalize_toggle_record_name(prefix, raw_name):
    if not isinstance(raw_name, str):
        return None

    candidate = raw_name.strip()
    if not candidate:
        return None

    expected_prefix = f'{prefix}-'
    if candidate.startswith(expected_prefix):
        suffix = candidate[len(expected_prefix):]
        return candidate if suffix.isdigit() else None

    if candidate.isdigit():
        return f'{expected_prefix}{candidate}'

    return None


def _get_next_integer_pk(model, pk_name):
    max_value = model.objects.aggregate(max_value=Max(pk_name)).get('max_value')
    return 1 if max_value is None else max_value + 1


class AgentConsumer(AsyncWebsocketConsumer):
    groups = []
    omissions = None

    def __init__(self):
        self.rag_lock = asyncio.Lock()
        # ── Cancellation bookkeeping (Angela, 2026-07-14) ──
        # ``_active_run`` is (user_key, run_epoch) for the request currently in flight,
        # so the cancel handler can latch EXACTLY that run dead. ``_status_emit`` is the
        # live self-healing status emitter, kept here so the cancel handler can REVOKE
        # it immediately — otherwise a dying executor keeps pushing "🔁 Tactic #…" lines
        # into the chat, and each one puts the browser back into its busy state (the
        # Send button flipping itself back to "Cancel", forever).
        self._active_run = None
        self._status_emit = None
        # The live Ask-Execs broker, so disconnect() can free a worker that is BLOCKED
        # on a Proceed/Deny prompt when the browser goes away.
        self._active_broker = None
        self.inet_enabled = False
        self.omissions = ""
        self.mcps = []
        self.tools = []
        self.agents = None
        self.rag_chain = None  # Initialize to None, will be set by setup_rag_chain()
        self.room_name = None
        self.room_group_name = None
        self.heartbeat_task = None

    async def connect(self):
        print("--- WebSocket connect initiated.")
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            print("!!! Rejecting anonymous WebSocket connection.")
            await self.close(code=4401)
            return

        try:
            self.room_name = f'user_{user.id}'
            self.room_group_name = f'chat_{self.room_name}'
            # Per-line log attribution for THIS connection (Angela, 2026-08-13).
            # Channels dispatches every frame of a connection from the SAME
            # asyncio task, so one ContextVar set here already names the user on
            # every line this consumer writes; receive() re-binds anyway so the
            # attribution can never depend on that implementation detail.
            log_identity.bind(user.id, user.username)
            print(f"--- Joining room: {self.room_group_name}")

            await self.channel_layer.group_add(  # type: ignore
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
            print("--- WebSocket connection accepted and successful.")
            self._ensure_connection_gauge_sink(user.id)
            await self._join_compact_mode_group()

        except Exception as e:
            print(f"!!! CONNECTION FAILED: {e}")
            await self.close()
        
        self.heartbeat_task = asyncio.create_task(self.heartbeat())
        
        # Check for existing RAG chain in global_state (persists across WebSocket reconnections)
        user_id = user.id
        
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
                    await self.send_session_restored(session_state, loading=False)
            
            # Send "Restored the last session" message - with or without context
            if existing_context:
                restore_message = constants.MSG_SESSION_AND_CONTEXT_RESTORED if hasattr(constants, 'MSG_SESSION_AND_CONTEXT_RESTORED') else 'Welcome back, session and context restored.'
            else:
                restore_message = constants.MSG_SESSION_RESTORED if hasattr(constants, 'MSG_SESSION_RESTORED') else 'Welcome back, session restored'
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': restore_message, 'username': 'Tlamatini'}
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

            skills = await self.get_all_skills()
            for skill in skills:
                await self.skill_establishment(skill['name'], skill['description'], 'true' if skill['enabled'] else 'false')
            print("--- Skills re-established on session restore")
            self._schedule_context_gauge_refresh("session restored")
        else:
            # No existing RAG chain - check session state for context to restore
            if user and user.is_authenticated:
                session_state = await self.get_session_state(user)
                if session_state and session_state.context_path and not session_state.is_expired():
                    print(f"--- Restoring session state: {session_state.context_type} - {session_state.context_path}")
                    # Notify frontend of restored session — loading=True so the
                    # client disables the input immediately, before the welcome
                    # message and well before the contextual setup eventually
                    # broadcasts MSG_AGENT_LOADING_CONTEXT.
                    await self.send_session_restored(session_state, loading=True)
                    # Send welcome message with context restored
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_SESSION_AND_CONTEXT_RESTORED if hasattr(constants, 'MSG_SESSION_AND_CONTEXT_RESTORED') else 'Welcome back, session and context restored.', 'username': 'Tlamatini'}
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
    
    async def send_session_restored(self, session_state, loading=False):
        """Notify frontend that a session was restored.

        ``loading`` is True when the consumer is about to schedule a heavy
        ``setup_contextual_rag_chain`` task — the client uses it to disable
        the chat input until ``MSG_AGENT_READY`` arrives, so the user cannot
        send a request that would be answered without the restored context
        actually being loaded yet.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'session-restored',
                'context_path': session_state.context_path,
                'context_type': session_state.context_type,
                'context_filename': session_state.context_filename,
                'loading': bool(loading),
            }))
            print(f"--- Session restored notification sent to client (loading={bool(loading)}).")
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

        skills = await self.get_all_skills()
        for skill in skills:
            await self.skill_establishment(skill['name'], skill['description'], 'true' if skill['enabled'] else 'false')
        print(f"--- Skills established: {len(skills)}")

        # A rebuild must NEVER leave the chat worse than it found it.
        #
        # ⚠️ Found 2026-07-29 (Angela): the self-heal used to NULL a perfectly
        # good chain whenever the rebuild failed or was cancelled — so the
        # attempt to heal is what finished killing the chat. Keep whatever is
        # working and only swap in a chain that actually built.
        _prev_chain = self.rag_chain
        async with self.rag_lock:
            try:
                # Check for cancellation before starting the heavy operation
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Setup cancelled before starting ---")
                    return
                
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.MSG_AGENT_LOADING, 'username': 'Tlamatini'}
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
                    self.rag_chain = _prev_chain   # keep what already worked
                    return
                if self.rag_chain is None:
                    print("!!! RAG chain setup failed. Please check the config.json file and Ollama is running.")
                    await self.channel_layer.group_send(
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.ERROR_AGENT_NOT_READY, 'username': 'Tlamatini'}
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
                            {'type': 'agent_message', 'message': constants.MSG_AGENT_FALLBACK, 'username': 'Tlamatini'}
                        )
                    else:
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': constants.MSG_AGENT_READY, 'username': 'Tlamatini'}
                        )
                    if isinstance(self.rag_chain, OptimizedHistoryAwareRAGChain):
                        if self.rag_chain.getDetectedOversizedDocs():
                            await self.channel_layer.group_send(   # type: ignore
                                self.room_group_name,
                                {'type': 'agent_message', 'message': constants.MSG_OVERSIZED_DOCS_WARNING, 'username': 'Tlamatini'}
                            )
                    print("--- Bot ready message broadcast to room.")
                    self._schedule_context_gauge_refresh(self._take_gauge_reason("agent ready"))
                    return
            except Exception as e:
                print(f"!!! ERROR during RAG chain setup: {e}")
                self.rag_chain = _prev_chain   # do NOT discard a working chain
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.ERROR_AGENT_NOT_READY, 'username': 'Tlamatini'}
                )
                errorDetail = "Error detail: " + str(e)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': errorDetail, 'username': 'Tlamatini'}
                )
                print("--- Bot error message broadcast to room.")
            finally:
                # ⚠️ THE SECOND HALF OF THE 2026-07-29 FIX — do not remove.
                #
                # Five exits inside this lock (two cancels, the None-chain
                # bail, the success return, and the except) used to leave the
                # process-global latch exactly as `setup_llm` left it. Combined
                # with a nulled chain that meant: chat permanently dead, immune
                # to a page reload, curable only by killing the process.
                #
                # Now the truth is restated on EVERY exit: keep the last
                # working chain, and let the latch simply mirror "do we have a
                # usable chain?".
                if self.rag_chain is None:
                    self.rag_chain = _prev_chain
                global_state.set_state('rag_chain_ready', self.rag_chain is not None)

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

        skills = await self.get_all_skills()
        for skill in skills:
            await self.skill_establishment(skill['name'], skill['description'], 'true' if skill['enabled'] else 'false')
        print(f"--- Skills established: {len(skills)}")

        # Same non-destructive contract as setup_rag_chain — see its comment.
        _prev_chain = self.rag_chain
        async with self.rag_lock:
            try:
                # Check for cancellation before starting the heavy operation
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Contextual setup cancelled before starting ---")
                    return
                
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.MSG_AGENT_LOADING_CONTEXT, 'username': 'Tlamatini'}
                )
                print("--- Bot loading context broadcast to room.")

                # Pre-flight: embedding-memory warning when an NVIDIA GPU is
                # detected AND the configured embedding model is predicted
                # to occupy more than 80% of total VRAM. Fail-open: any
                # probe error just skips the warning and the load proceeds.
                # CPU-only / AMD / Apple Silicon hosts return None and never
                # see this branch fire. See agent/embedding_memory_guard.py.
                try:
                    from .embedding_memory_guard import (
                        check_embedding_memory_for_directory,
                        format_warning_message,
                    )
                    from .config_loader import load_config as _load_cfg_for_guard
                    _guard_cfg = await asyncio.to_thread(_load_cfg_for_guard)
                    _guard_warning = await asyncio.to_thread(
                        check_embedding_memory_for_directory,
                        path_only, _guard_cfg, self.omissions, filename,
                    )
                    if _guard_warning:
                        _msg = format_warning_message(_guard_warning)
                        if _msg:
                            await self.channel_layer.group_send(   # type: ignore
                                self.room_group_name,
                                {'type': 'agent_message', 'message': _msg, 'username': 'Tlamatini'}
                            )
                            print(
                                f"--- [EMBED-MEM] Warning sent: model={_guard_warning['model']} "
                                f"predicted={_guard_warning['predicted_vram_bytes']/1024/1024:.0f} MiB "
                                f"percent={_guard_warning['percent']:.1f}%"
                            )
                except Exception as _guard_exc:
                    print(f"--- [EMBED-MEM] Pre-flight check skipped (fail-open): {_guard_exc}")

                # Check for cancellation before the blocking call
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Contextual setup cancelled before LLM creation ---")
                    return

                self.rag_chain = await asyncio.to_thread(setup_llm_with_context, path_only, self.agents, self.mcps, self.tools, self.omissions, filename)
                
                # Check for cancellation after the blocking call completed
                if global_state.get_state('cancel_generation'):
                    print("--- [CANCEL] Contextual setup cancelled after LLM creation - discarding result ---")
                    self.rag_chain = _prev_chain   # keep what already worked
                    return
                
                if self.rag_chain is None:
                    print("!!! Contextual RAG chain setup failed. Please check the config.json file and Ollama is running.")
                    not_ready_response = constants.ERROR_AGENT_NOT_READY
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': not_ready_response, 'username': 'Tlamatini'}
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
                        fallback_llm_response = "There was a problem, so the agent fell back to a Basic Prompt Only Chain (No context will be used)."
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': fallback_llm_response, 'username': 'Tlamatini'}
                        )
                    else:
                        ready_response = "Your agent is ready. You can now start chatting with Tlamatini."
                        await self.channel_layer.group_send(   # type: ignore
                            self.room_group_name,
                            {'type': 'agent_message', 'message': ready_response, 'username': 'Tlamatini'}
                        )
                    if isinstance(self.rag_chain, OptimizedHistoryAwareRAGChain):
                        if self.rag_chain.getDetectedOversizedDocs():
                            detected_oversized_docs_warning = "Your agent is ready. However, some documents are too large; please be aware that Tlamatini might not be able to load them completely."
                            await self.channel_layer.group_send(   # type: ignore
                                self.room_group_name,
                                {'type': 'agent_message', 'message': detected_oversized_docs_warning, 'username': 'Tlamatini'}
                            )
                    print("--- Bot ready message broadcast to room.")
                    self._gauge_reason = None
                    self._schedule_context_gauge_refresh("context loaded")
                    return not isinstance(self.rag_chain, BasicPromptOnlyChain)
            except Exception as e:
                print(f"!!! ERROR during Contextual RAG chain setup: {e}")
                self.rag_chain = _prev_chain   # do NOT discard a working chain
                not_ready_response = constants.ERROR_AGENT_NOT_READY
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': not_ready_response, 'username': 'Tlamatini'}
                )
                errorDetail = "Error detail: " + str(e)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': errorDetail, 'username': 'Tlamatini'}
                )
                print("--- Bot error message broadcast to room.")
            finally:
                # Same contract as setup_rag_chain: never leave the chat worse
                # than we found it, and always restate the latch truthfully.
                if self.rag_chain is None:
                    self.rag_chain = _prev_chain
                global_state.set_state('rag_chain_ready', self.rag_chain is not None)

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

    async def skill_establishment(self, skill_name, skill_description, skill_content):
        """
        Sends a skill establishment message.

        skill_content is 'true' / 'false' (string) — the same shape Mcps /
        Tools / Agents use, so the existing pipe-encoded message-payload
        decoder on the JS side can be reused verbatim.
        """
        try:
            await self.send(text_data=json.dumps({
                'type': 'skill',
                'message': skill_name + '|' + (skill_description or '') + '|' + skill_content,
                'username': 'system'
            }))
        except Exception as e:
            print(f"Error in skill_establishment: {e}")
            
    # ── The Compact-mode switch (Angela, 2026-10-02) ───────────────────────
    # Every chat tab joins ONE group, so a switch made in any tab - or made
    # automatically because the model is too small for everything - reaches
    # every tab at once, with the REAL Configure rows behind it.
    async def _join_compact_mode_group(self):
        try:
            from . import compact_mode
            compact_mode.register_loop(asyncio.get_running_loop(), self.channel_layer)
            await self.channel_layer.group_add(compact_mode.GROUP, self.channel_name)  # type: ignore
            self._in_compact_group = True
            await self._send_compact_state("connect")
        except Exception as exc:  # noqa: BLE001 - the switch owes the chat nothing
            print(f"--- [COMPACT] this tab is not subscribed to the switch ({exc})")

    async def _send_compact_state(self, kind="state"):
        """Send this tab the Compact-mode switch (``compact-mode-state``)."""
        try:
            from . import compact_mode
            snap = await database_sync_to_async(compact_mode.state)()
            await self.send(text_data=json.dumps({
                'type': 'compact-mode-state', 'kind': kind, 'state': snap,
            }))
        except Exception as exc:  # noqa: BLE001
            print(f"--- [COMPACT] switch state not sent ({exc})")

    async def _send_toggle_rows(self):
        """Re-send every Configure row, so every dialog shows the REAL state."""
        try:
            for mcp in await self.get_all_mcps():
                await self.mcp_establishment(mcp['mcpName'], mcp['mcpDescription'], mcp['mcpContent'])
            for tool in await self.get_all_tools():
                await self.tool_establishment(tool['toolName'], tool['toolDescription'], tool['toolContent'])
            for agent in await self.get_all_agents():
                await self.agent_establishment(agent['agentName'], agent['agentDescription'], agent['agentContent'])
            for skill in await self.get_all_skills():
                await self.skill_establishment(skill['name'], skill['description'], 'true' if skill['enabled'] else 'false')
        except Exception as exc:  # noqa: BLE001
            print(f"--- [COMPACT] Configure rows not re-sent ({exc})")

    async def compact_mode_changed(self, event):
        """Group handler: the switch, or a saved Configure dialog, changed the
        rows - send this tab the switch and the REAL rows, then re-measure."""
        try:
            await self.send(text_data=json.dumps({
                'type': 'compact-mode-state',
                'kind': event.get('kind') or 'state',
                'state': event.get('state') or {},
            }))
            await self._send_toggle_rows()
            self._schedule_context_gauge_refresh("Configure rows changed")
        except Exception as exc:  # noqa: BLE001
            print(f"--- [COMPACT] switch change not forwarded ({exc})")

    async def _handle_set_compact_mode(self, user, payload):
        """The toolbar's "Compact mode" box.  Refused while an answer runs, and
        - untick only - while the model is too small for everything (strict)."""
        from . import compact_mode
        enabled = bool(payload.get('enabled'))
        message = None
        if getattr(self, '_active_run', None):
            message = ("Compact mode was not changed: an answer is still running. "
                       "Try again when it finishes.")
            await self._send_compact_state("refused")
        else:
            result = await database_sync_to_async(compact_mode.set_active)(
                enabled, f"user {getattr(user, 'username', '') or '?'}")
            if result.get('refused'):
                message = result.get('message') or "Compact mode stays ON."
                await self._send_compact_state("refused")
            elif not result.get('ok'):
                message = "Compact mode could not be changed: " + str(result.get('error') or 'unknown error')
                await self._send_compact_state("error")
            elif not result.get('changed'):
                await self._send_compact_state("unchanged")
            elif enabled:
                message = ("Compact mode is ON: every MCP, tool, agent and skill was unticked except "
                           "System-Metrics, Files-Search and Current-Time. Tick what you need in "
                           "Config > Configure MCPs / Configure Agents - the CONTEXT-WINDOW gauge shows "
                           "what it costs.")
            else:
                message = ("Compact mode is OFF: every MCP, tool, agent and skill is ticked again, "
                           "and your External MCPs are back.")
        if message:
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': message, 'username': 'Tlamatini'}
            )
        self._schedule_context_gauge_refresh("compact mode " + ("on" if enabled else "off"))

    @staticmethod
    def _toggles_summary(label, message):
        """'agent-1=ACPXer=false,agent-23=ESPHomer=true,...' -> one readable
        line: how many are on, and which.  The raw payload used to be echoed
        into the chat whole - a wall of 90 'name=desc=false' items."""
        names, total = [], 0
        for item in str(message or '').split(','):
            parts = item.strip().split('=')
            if len(parts) < 3:
                continue
            total += 1
            if parts[-1].strip().lower() == 'true':
                names.append('='.join(parts[1:-1]).strip() or parts[0])
        shown = ', '.join(names[:15]) + (f" and {len(names) - 15} more" if len(names) > 15 else '')
        return (f"{label} activation saved: {len(names)} of {total} on"
                + (f" ({shown})" if names else '') + '.')

    async def _after_toggles_saved(self, kind, before, text):
        """A Configure dialog was saved: apply it AT ONCE (Angela, 2026-10-02) -
        chain agent <-> tool rows, refresh the gates, tell every tab."""
        linked = []
        try:
            from . import compact_mode
            result = await database_sync_to_async(compact_mode.after_toggles_saved)(kind, before or [])
            linked = result.get('linked') or []
        except Exception as exc:  # noqa: BLE001
            print(f"--- [TOGGLES] saved rows not applied at once ({exc})")
        if text:
            extra = ("\n\nAlso switched to match: " + "; ".join(linked) + ".") if linked else ""
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message',
                 'message': text + extra + "\n\nIt applies from your next message - no restart needed.",
                 'username': 'Tlamatini'}
            )
        self._schedule_context_gauge_refresh(f"{kind} rows changed")

    async def disconnect(self, close_code):   # type: ignore
        print("--- WebSocket disconnected.")
        if getattr(self, '_in_compact_group', False):
            try:
                from . import compact_mode
                await self.channel_layer.group_discard(compact_mode.GROUP, self.channel_name)  # type: ignore
            except Exception:  # noqa: BLE001 - teardown must never raise
                pass
        # ── Free a worker parked on an Ask-Execs prompt (Angela, 2026-07-14) ──
        # If this tab closed / hard-reloaded while a Proceed/Deny prompt was BLOCKING,
        # the executor thread is sitting inside request_permission() with no deadline —
        # and the `finally` that would close the broker is downstream of the still-blocked
        # ask_rag, so it can never run. The thread would park FOREVER. close() resolves
        # every pending prompt to "deny" (fail-safe: an unconfirmed tool never runs).
        # Identity-guarded, so a sibling tab of the same user keeps its own broker.
        try:
            broker = getattr(self, '_active_broker', None)
            if broker is not None and getattr(self, '_active_run', None):
                from .exec_permission import unregister_broker
                print("--- [AskExecs] browser gone while a prompt was open — denying and freeing the worker ---")
                broker.close()
                unregister_broker(self._active_run[0], broker)
                self._active_broker = None
        except Exception as exc:  # noqa: BLE001 — teardown must never raise
            print(f"--- [AskExecs] disconnect teardown skipped: {exc}")
        if self.heartbeat_task is not None:
            self.heartbeat_task.cancel()
            self.heartbeat_task = None
        # The connection's gauge sink goes with the socket - identity-guarded,
        # so another open tab of the same user keeps its own.
        try:
            if getattr(self, '_gauge_emit', None) is not None:
                from .context_governor import unregister_gauge_sink
                unregister_gauge_sink(self._gauge_user_id, self._gauge_emit)
                self._gauge_emit = None
        except Exception as exc:  # noqa: BLE001 — teardown must never raise
            print(f"--- [CONTEXT] gauge sink teardown skipped: {exc}")

        if self.room_group_name:
            await self.channel_layer.group_discard(   # type: ignore
                self.room_group_name,
                self.channel_name
            )

    async def queue_llm_retrieval(self, message, conversation_user, multi_turn_enabled=False, exec_report_enabled=False, acpx_enabled=False, ask_execs_enabled=False, step_by_step_enabled=False):
        broker = None
        broker_key = conversation_user.id
        status_registered = False
        gauge_registered = False
        _gauge_user_token = None
        _visual_error_token = None
        # Per-line log attribution (Angela, 2026-08-13). receive() already bound
        # this task, and the whole synchronous executor inherits it through
        # sync_to_async -- this re-bind is the safety net for any path that
        # reaches the LLM run from a context receive() did not open.
        log_identity.bind(broker_key, getattr(conversation_user, 'username', ''))
        # Mint THIS run's cancellation epoch up front, so the executor, the
        # self-healing invoker and the Ask-Execs broker all share ONE identity that a
        # Cancel can latch dead permanently. (Angela, 2026-07-14)
        from .cancellation import begin_llm_run, current_run_epoch, is_generation_cancelled, is_run_cancelled
        run_epoch = begin_llm_run(broker_key)
        self._active_run = (broker_key, run_epoch)
        try:
            # Check if rag_chain is ready
            if self.rag_chain is None:
                print("!!! ERROR: rag_chain is not initialized yet. Please wait for the agent to finish loading.")
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': 'The agent is still loading. Please wait a moment and try again.', 'username': 'Tlamatini'}
                )
                return

            print("--- The message is being procesed by the LLM")
            # Exec report and Ask-Execs are both multi-turn-only by design.
            exec_report_enabled = bool(exec_report_enabled) and bool(multi_turn_enabled)
            ask_execs_enabled = bool(ask_execs_enabled) and bool(multi_turn_enabled)

            # ── Context-gauge sink — EVERY request, not just Multi-Turn ──
            # (Angela, 2026-09-21: "MAKE THAT COUNT FOR EVERY CALL TO A MODEL,
            # EVERYWHERE: ONE-SHOT, ACPX, MULTI-TURN".)
            #
            # This used to live inside `if multi_turn_enabled:`, so a One-Shot
            # question registered no sink, pushed no frame, and left the ring
            # frozen on whatever the last Multi-Turn request had put there — a
            # gauge showing a stale number is worse than no gauge. It is now
            # registered unconditionally, and the user id is BOUND so a chain
            # callback deep inside LangChain can report without new plumbing.
            #
            # The exact byte count can only come from the server: the page
            # never sees the system prompt, the history as sent, or the bound
            # tool schemas. One-way, fire-and-forget, never awaited.
            from .context_governor import bind_user, register_gauge_sink
            _gauge_loop = asyncio.get_running_loop()
            _gauge_channel_layer = self.channel_layer
            _gauge_room = self.room_group_name

            def _emit_context_gauge(detail):
                try:
                    asyncio.run_coroutine_threadsafe(
                        _gauge_channel_layer.group_send(
                            _gauge_room,
                            {'type': 'context_gauge', 'detail': detail},
                        ),
                        _gauge_loop,
                    )
                except Exception as _ge:  # noqa: BLE001 — the gauge is best-effort
                    print(f"--- [CONTEXT] failed to emit gauge frame: {_ge}")

            from .visual_error_reporting import bind_visual_error_sink

            def _emit_visual_error(detail):
                asyncio.run_coroutine_threadsafe(
                    _gauge_channel_layer.group_send(
                        _gauge_room, {'type': 'visual_analysis_error', 'detail': detail}),
                    _gauge_loop,
                )

            _visual_error_token = bind_visual_error_sink(_emit_visual_error)
            register_gauge_sink(broker_key, _emit_context_gauge)
            gauge_registered = True
            _gauge_user_token = bind_user(broker_key)
            # This answer's REAL Ollama totals start here; while the turn is
            # open the at-rest gauge refresh stands aside (a live request owns
            # the ring).  Remember the toolbar flags for later at-rest rebuilds.
            from .context_governor import begin_turn
            begin_turn(broker_key, label=str(message or "")[:80])
            self._gauge_flags = (bool(multi_turn_enabled), bool(acpx_enabled),
                                 bool(step_by_step_enabled))

            # ── Self-healing LIVE status broadcaster (Angela, 2026-07-06) ──
            # The multi-turn executor's self-healing invoker pushes first-person
            # recovery status ("⚠️ transient error — switching tactic…", "🔁 Tactic
            # #3 …", "✅ recovered") to THIS user's chat AS IT WORKS THROUGH a
            # network problem, so the user SEES she is trying different tactics
            # and never hung. Fire-and-forget emit scheduled onto this event
            # loop, keyed by user id; the executor worker thread looks it up.
            # Registered for every multi-turn request (independent of Ask-Execs).
            if multi_turn_enabled:
                from .self_healing import register_status_broadcaster
                _status_loop = asyncio.get_running_loop()
                _status_channel_layer = self.channel_layer
                _status_room = self.room_group_name

                def _emit_status(text):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            _status_channel_layer.group_send(
                                _status_room,
                                {'type': 'agent_message', 'message': text, 'username': 'Tlamatini'},
                            ),
                            _status_loop,
                        )
                    except Exception as _se:  # noqa: BLE001 — status is best-effort
                        print(f"--- [SelfHealing] failed to emit status: {_se}")

                register_status_broadcaster(broker_key, _emit_status)
                status_registered = True
                # Keep the handle so `cancel-current` can revoke THIS emitter the
                # instant the user cancels (identity-guarded, so a second tab of the
                # same user keeps its own live emitter).
                self._status_emit = _emit_status

            # ── Ask-Execs broker ──
            # The multi-turn tool executor runs in a worker thread and must be
            # able to BLOCK on a browser Proceed/Deny prompt before each
            # state-changing tool. Register a per-request broker whose emit
            # schedules an `exec_permission_request` frame onto THIS event
            # loop; the executor thread looks it up by user id.
            if ask_execs_enabled:
                from .exec_permission import ExecPermissionBroker, register_broker
                loop = asyncio.get_running_loop()
                channel_layer = self.channel_layer
                room_group_name = self.room_group_name

                def _emit_permission_request(detail):
                    try:
                        asyncio.run_coroutine_threadsafe(
                            channel_layer.group_send(
                                room_group_name,
                                {'type': 'exec_permission_request', 'detail': detail},
                            ),
                            loop,
                        )
                    except Exception as emit_err:  # noqa: BLE001
                        print(f"--- [AskExecs] failed to emit permission request: {emit_err}")

                broker = ExecPermissionBroker(
                    _emit_permission_request,
                    run_user_id=broker_key,
                    run_epoch=run_epoch,
                )
                register_broker(broker_key, broker)
                self._active_broker = broker
                print(f"--- [AskExecs] broker registered for user {broker_key}")

            ask_rag_async = sync_to_async(ask_rag, thread_sensitive=False)
            chat_history = await self.load_recent_chat_history(conversation_user, limit=8)
            llm_response = await ask_rag_async(
                self.rag_chain,
                {
                    "input": message,
                    "conversation_user_id": conversation_user.id,
                    # This run's cancellation epoch — see agent/cancellation.py.
                    "cancel_run_epoch": run_epoch,
                    "multi_turn_enabled": bool(multi_turn_enabled),
                    "exec_report_enabled": exec_report_enabled,
                    "acpx_enabled": bool(acpx_enabled),
                    "ask_execs_enabled": ask_execs_enabled,
                    "step_by_step_enabled": bool(step_by_step_enabled),
                },
                chat_history=chat_history,
                inet_enabled=self.inet_enabled
            )
            # Pick up per-request metadata stored by ask_rag, KEYED by THIS user id so a
            # concurrent request (another tab / TeleTlamatini, a different user) can never
            # hand us its exec-report tables or its Create-Flow tool-call log. (re-audit [4])
            _meta_slot = f"last_request_meta::{conversation_user.id}"
            _meta = global_state.get_state(_meta_slot) or {}
            tool_calls_log = _meta.get('tool_calls_log')
            multi_turn_used = _meta.get('multi_turn_used')
            exec_report_used = _meta.get('exec_report_enabled')
            exec_report_entries = _meta.get('exec_report_entries') if exec_report_used else None
            # Ask-Execs denial — surfaced as the red "Execution interrupted"
            # banner regardless of the Exec report toggle.
            exec_report_denied = _meta.get('exec_report_denied')
            # Tier-1 survivor list carried over from the multi-turn executor —
            # processes the per-tool reaper failed to kill. KEYED by THIS user id
            # (like _meta_slot) so a concurrent request can't hand us its survivor
            # list or clear ours before we read it. (re-audit [3])
            _orphan_slot = f"last_orphan_survivors::{conversation_user.id}"
            tier1_orphans = global_state.get_state(_orphan_slot) or []
            # Clear immediately to avoid leaking into the next request.
            global_state.set_state(_meta_slot, None)
            global_state.set_state(_orphan_slot, None)

            # ── Stale-answer guard (Angela, 2026-07-14) ──
            # This run was CANCELLED and a NEWER run is already in flight. Broadcasting
            # this dead run's answer now would re-enable the controls in the middle of
            # the new run and contaminate it with the old run's Exec report. Drop it.
            # NOTE the second condition: when NO newer run has started we still deliver
            # the cancelled run's graceful answer, so the Exec report + Create-Flow
            # button for the agents that DID run are preserved.
            if is_run_cancelled(broker_key, run_epoch) and current_run_epoch(broker_key) > run_epoch:
                print(
                    "--- [CANCEL] dropping the cancelled run's late answer — a NEWER "
                    "run is already in flight ---"
                )
                return

            # ── A CUT answer says so (Angela, 2026-10-02: "yes show the warning") ──
            # The model could not read the whole request; its answer is shown,
            # but never without the CONTEXT-WINDOW warning above it.
            try:
                from .context_governor import turn_cut as _turn_cut
                from .compact_mode import cut_warning_html as _cut_warning_html
                _cut = _turn_cut(broker_key)
                if _cut and isinstance(llm_response, str):
                    llm_response = _cut_warning_html(_cut) + llm_response
                    print(f"--- [CONTEXT-FIT] this answer came from a CUT request ({_cut}) - "
                          "the CONTEXT-WINDOW warning is shown above it")
            except Exception as _cut_err:  # noqa: BLE001 - a warning must never cost the answer
                print(f"--- [CONTEXT-FIT] cut warning skipped ({_cut_err})")

            await process_llm_response(
                llm_response,
                self.rag_chain,
                self.channel_layer,
                self.room_group_name,
                conversation_user=conversation_user,
                tool_calls_log=tool_calls_log,
                multi_turn_used=multi_turn_used,
                exec_report_enabled=bool(exec_report_used),
                exec_report_entries=exec_report_entries,
                exec_report_denied=exec_report_denied,
            )

            # ── Tier-2 orphan-process sweep ───────────────────────
            # Now that the user has their answer, run the broader
            # reaper (this time including the pool-cmdline scan). If
            # anything survives — Tier-1 orphans from the executor or
            # fresh ones the broader sweep just turned up — send a
            # SECOND chat message listing process name + PID so the
            # user can end them manually. We deliberately run this
            # AFTER process_llm_response so the main answer reaches
            # the browser without being held up by the sweep (~100ms
            # on a busy host).
            try:
                await self._tier2_orphan_sweep(tier1_orphans)
            except Exception as sweep_err:  # noqa: BLE001 — never block on cleanup
                print(f"--- [Tier-2 reaper] sweep raised (non-fatal): {sweep_err}")
        except Exception as e:
            print(f"!!! ERROR in queue_llm_retrieval method: {e}")
            # A cancel-induced exception must stay silent — not surface the scary
            # "Your agent cannot process your requests" banner. This used to read the
            # raw boolean, which the cancel handler had already cleared. (2026-07-14)
            if is_generation_cancelled(broker_key, run_epoch):
                return
            not_ready_response = constants.ERROR_AGENT_NOT_READY
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': not_ready_response, 'username': 'Tlamatini'}
            )
            errorDetail = "Error detail: " + str(e)
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': errorDetail, 'username': 'Tlamatini'}
            )
            print("--- Bot error message broadcast to room.")
        finally:
            # Always tear down the Ask-Execs broker so a still-pending prompt
            # can never leave the executor thread blocked after the request
            # ends (close() resolves any outstanding prompt to "deny").
            if broker is not None:
                from .exec_permission import unregister_broker
                unregister_broker(broker_key, broker)
                print(f"--- [AskExecs] broker unregistered for user {broker_key}")
            if status_registered:
                from .self_healing import unregister_status_broadcaster
                unregister_status_broadcaster(broker_key, _emit_status)
            if gauge_registered:
                # Close this answer's REAL totals (logged once) while the sink
                # can still deliver the final frame.
                from .context_governor import end_turn
                end_turn(broker_key)
                # Pass the SPECIFIC emit so a finishing request cannot tear
                # down a concurrent same-user request's live sink — two browser
                # tabs share one user id.
                from .context_governor import unbind_user, unregister_gauge_sink
                unregister_gauge_sink(broker_key, _emit_context_gauge)
                unbind_user(_gauge_user_token)
                # Hand the ring back to this connection's persistent sink and
                # show what the NEXT message will send (the history just grew).
                self._restore_connection_gauge_sink()
                self._schedule_context_gauge_refresh("answer finished", after_answer=True)
            if _visual_error_token is not None:
                from .visual_error_reporting import unbind_visual_error_sink
                unbind_visual_error_sink(_visual_error_token)
            self._status_emit = None
            self._active_run = None
            self._active_broker = None

    async def visual_analysis_error(self, event):
        """Report an attempt without ending or pausing its recovery loop."""
        await self.send(text_data=json.dumps({
            'type': 'visual-analysis-error', 'detail': event.get('detail') or {},
        }))

    # ── The context gauge AT REST (Angela, 2026-09-28) ──────────────────────
    # The meter only measures a request while it is being SENT, so between
    # messages the ring froze: Clear history, Clear context, loading a context
    # or reconnecting changed nothing on screen.  These helpers rebuild "what
    # my NEXT message will send" with the main chain's own code and ask Ollama
    # for its real prompt_eval_count (agent/context_baseline.py) at every point
    # where that answer changes.  Per connected user; fail-open everywhere.
    def _ensure_connection_gauge_sink(self, user_id):
        """A sink that lives as long as this socket, so at-rest frames reach
        the page between requests.  Sends the latest frame at once, so a
        reopened tab shows the current state instead of an empty ring."""
        try:
            from .context_governor import latest_frame, register_gauge_sink
            loop = asyncio.get_running_loop()
            layer = self.channel_layer
            room = self.room_group_name

            def _emit(detail):
                try:
                    asyncio.run_coroutine_threadsafe(
                        layer.group_send(room, {'type': 'context_gauge', 'detail': detail}),
                        loop,
                    )
                except Exception as _ge:  # noqa: BLE001 — the gauge is best-effort
                    print(f"--- [CONTEXT] failed to emit gauge frame: {_ge}")

            self._gauge_emit = _emit
            self._gauge_user_id = user_id
            register_gauge_sink(user_id, _emit)
            frame = latest_frame(user_id)
            if frame:
                _emit(frame)
        except Exception as exc:  # noqa: BLE001
            print(f"--- [CONTEXT] connection gauge sink not registered ({exc})")

    def _restore_connection_gauge_sink(self):
        """After a request tears its own sink down, hand the ring back to the
        connection's sink.  Never raises."""
        try:
            emit = getattr(self, '_gauge_emit', None)
            user_id = getattr(self, '_gauge_user_id', None)
            if emit is not None and user_id is not None:
                from .context_governor import register_gauge_sink
                register_gauge_sink(user_id, emit)
        except Exception:  # noqa: BLE001
            pass

    def _take_gauge_reason(self, default):
        """The reason a pending chain rebuild was started (e.g. "history
        cleared"), consumed once so the ring can say WHY it changed."""
        reason = getattr(self, '_gauge_reason', None) or default
        self._gauge_reason = None
        return reason

    def _schedule_context_gauge_refresh(self, reason, after_answer=False):
        """Fire-and-forget: never delays the caller.  Never raises."""
        try:
            asyncio.get_running_loop().create_task(
                self._context_gauge_refresh(reason, after_answer=after_answer)
            )
        except Exception as exc:  # noqa: BLE001
            print(f"--- [CONTEXT-REST] refresh not scheduled ({exc})")

    async def _context_gauge_refresh(self, reason, after_answer=False):
        try:
            user = self.scope.get('user')
            if user is None or not user.is_authenticated:
                return
            chain = self.rag_chain or global_state.get_state(f'rag_chain_{user.id}')
            if chain is None:
                return
            history = await self.load_recent_chat_history(user, limit=8)
            multi_turn, acpx, step_by_step = (
                getattr(self, '_gauge_flags', None) or (False, False, False)
            )
            from .context_baseline import RefreshFlags, probe_settings, schedule_refresh
            probe = None
            if after_answer:
                from .config_loader import load_config as _cfg_loader
                _cfg = await asyncio.to_thread(_cfg_loader)
                if not probe_settings(_cfg)["after_answer"]:
                    probe = False
            schedule_refresh(
                user.id, chain, history,
                RefreshFlags(multi_turn, acpx, step_by_step),
                str(reason or "refresh"), probe=probe,
            )
        except Exception as exc:  # noqa: BLE001 — the gauge owes the chat nothing
            print(f"--- [CONTEXT-REST] refresh not scheduled ({exc})")

    async def context_gauge(self, event):
        """Group handler: forward one context-size measurement to this browser
        as a `context-gauge` frame. Scheduled from the executor's worker thread
        via run_coroutine_threadsafe, and never awaited by it — a failure here
        costs the ring one update, never the turn."""
        try:
            await self.send(text_data=json.dumps({
                'type': 'context-gauge',
                'detail': event.get('detail') or {},
            }))
        except Exception as e:
            print(f"Error in context_gauge: {e}")

    async def exec_permission_request(self, event):
        """Group handler: forward an Ask-Execs permission request to this
        browser as an `exec-permission-request` frame. Scheduled from the
        executor's worker thread via run_coroutine_threadsafe."""
        try:
            await self.send(text_data=json.dumps({
                'type': 'exec-permission-request',
                'detail': event.get('detail') or {},
            }))
        except Exception as e:
            print(f"Error in exec_permission_request: {e}")

    async def _tier2_orphan_sweep(self, tier1_survivors):
        """Post-answer orphan-process sweep + user notification.

        Runs the orphan reaper with the wider (pool-cmdline) scan now
        that the user has their answer. Any process that survives BOTH
        the per-tool reaper AND this final sweep is surfaced as an
        additional chat message so the user knows which name+PID to end
        manually from Task Manager.

        Implementation notes:
        - We hop to a thread for the sweep itself (psutil.process_iter
          is synchronous and can take tens of ms with hundreds of
          processes; we don't want to block the WebSocket loop).
        - The notification is a SECOND ``agent_message`` so it stacks
          beneath the main answer in the chat log; this is the same
          mechanism used for fallback/loading status messages.
        - If the sweep itself raises (psutil access denied, etc.) we
          swallow it: cleanup must never break the chat path.
        """
        from .orphan_reaper import reap_orphans, format_survivors_message

        def _do_sweep():
            try:
                return reap_orphans(
                    scope="tier2:post_answer",
                    include_self_tree=True,
                    include_pool_scan=True,
                    include_console_host_sweep=True,
                )
            except Exception as exc:  # noqa: BLE001
                print(f"--- [Tier-2 reaper] reap_orphans raised: {exc}")
                return None

        sweep_loop = asyncio.get_event_loop()
        result = await sweep_loop.run_in_executor(None, _do_sweep)

        # Merge Tier-1 leftovers with Tier-2 survivors. De-dup by PID
        # so the same orphan is only reported once even if both tiers
        # noticed it.
        merged: dict = {}
        for name, pid in (tier1_survivors or []):
            if isinstance(pid, int) and pid > 0:
                merged[pid] = name
        if result is not None:
            for name, pid in result.survivors:
                if isinstance(pid, int) and pid > 0:
                    merged[pid] = name
            # Verbose log of what we did so an oncall reader can audit
            # the cleanup pass without enabling debug logging.
            try:
                print(
                    f"--- [Tier-2 reaper] killed={result.killed_count} "
                    f"tier1_survivors={len(tier1_survivors or [])} "
                    f"tier2_survivors={len(result.survivors)} "
                    f"errors={len(result.errors)}"
                )
            except Exception:  # noqa: BLE001
                pass

        if not merged:
            return

        survivors_list = [(name, pid) for pid, name in merged.items()]
        message = format_survivors_message(survivors_list)
        if not message:
            return
        try:
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': message, 'username': 'Tlamatini'}
            )
            print(f"--- [Tier-2 reaper] notified user about {len(survivors_list)} surviving orphan(s)")
        except Exception as send_err:  # noqa: BLE001
            print(f"--- [Tier-2 reaper] failed to broadcast survivor list: {send_err}")

    async def receive(self, text_data):   # type: ignore
        if _WS_TRACE:
            print(f">>> [RECEIVE] Got message: {text_data[:100]}...", flush=True)
            sys.stdout.flush()
        try:
            text_data_json = json.loads(text_data)
            message = text_data_json['message']
            multi_turn_enabled = bool(text_data_json.get('multi_turn_enabled', False))
            exec_report_enabled = bool(text_data_json.get('exec_report_enabled', False)) and multi_turn_enabled
            # ACPX defaults to DISABLED. The frontend always sends an explicit
            # boolean, but if it is ever missing we drop back to the legacy
            # Multi-Turn / one-shot flow so the user must opt into ACPX
            # explicitly via the toolbar checkbox.
            acpx_enabled = bool(text_data_json.get('acpx_enabled', False))
            # Ask-Execs (per-tool permission prompt) is a Multi-Turn-only
            # modifier — gated to multi_turn_enabled like exec_report.
            ask_execs_enabled = bool(text_data_json.get('ask_execs_enabled', False)) and multi_turn_enabled
            step_by_step_enabled = bool(text_data_json.get('step_by_step_enabled', False))

            if 'type' in text_data_json:
                type = text_data_json['type']
                if _WS_TRACE:
                    print(f">>> [RECEIVE] Message type: {type}", flush=True)
            else:
                type = None
            user = self.scope['user']

            # Per-line log attribution (Angela, 2026-08-13). An UNTYPED frame is
            # a real prompt, so it OPENS a new turn -- that turn number is what
            # separates two concurrent requests of the same user (two tabs) in
            # tlamatini.log. A typed frame is a control message (toggles, cancel,
            # ping) and rides the current turn. Anonymous binds to nothing, which
            # writes bare, untagged lines.
            if getattr(user, 'is_authenticated', False):
                if type is None:
                    log_identity.begin_turn(user.id, user.username)
                else:
                    log_identity.bind(user.id, user.username)
            else:
                log_identity.bind(None)

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
                    {'type': 'agent_message', 'message': constants.ERROR_NOT_AUTHENTICATED, 'username': 'Tlamatini'}
                )
                return

            if type == 'exec-permission-response':
                # The browser answered an Ask-Execs Proceed/Deny prompt. Route
                # it to the request's broker so the blocked executor thread
                # unblocks with the user's decision.
                from .exec_permission import resolve_permission
                request_id = text_data_json.get('request_id')
                decision = text_data_json.get('decision', 'deny')
                resolved = resolve_permission(user.id, request_id, decision)
                print(
                    f"--- exec-permission-response: request_id={request_id} "
                    f"decision={decision} resolved={resolved}"
                )
                return

            if type == 'drop-message':
                # The Drop button on a chat card: erase ONE saved message from
                # this user's conversation, with no reconnect.
                await self._handle_drop_message(user, text_data_json)
                return

            if type == 'context-gauge-refresh':
                # The page asks what its NEXT message would send - on load and
                # whenever a toolbar switch that changes the request flips
                # (Multi-Turn / ACPX / Step-by-Step).  Remember the switches for
                # every later at-rest rebuild, then refresh (coalesced per user;
                # a request in flight owns the ring and is never overwritten).
                self._gauge_flags = (
                    bool(text_data_json.get('multi_turn_enabled', False)),
                    bool(text_data_json.get('acpx_enabled', False)),
                    bool(text_data_json.get('step_by_step_enabled', False)),
                )
                self._restore_connection_gauge_sink()
                _why = str(text_data_json.get('reason') or 'page request')[:60]
                self._schedule_context_gauge_refresh(_why)
                return

            if type == 'set-compact-mode':
                # The toolbar's "Compact mode" box (Angela, 2026-10-02).
                await self._handle_set_compact_mode(user, text_data_json)
                return

            if type == 'compact-mode-sync':
                # The page saw a newer switch/rows version on a gauge frame and
                # asks for the switch and the REAL rows.
                await self._send_compact_state("sync")
                await self._send_toggle_rows()
                return

            if type == 'set-ask-execs-runtime':
                # The user toggled the "Ask Execs" checkbox WHILE a Multi-Turn
                # run is in flight. Propagate the new choice to the live broker
                # so it takes effect for the REMAINDER of that run: unchecked
                # (enabled=False) → stop prompting / auto-proceed; re-checked
                # (enabled=True) → resume prompting. No effect if no broker is
                # registered (the run started with Ask Execs off, so there is
                # nothing to relax — applied=False).
                from .exec_permission import set_broker_auto_proceed
                desired = bool(text_data_json.get('ask_execs_runtime_enabled', False))
                applied = set_broker_auto_proceed(user.id, auto_proceed=not desired)
                print(
                    f"--- set-ask-execs-runtime: enabled={desired} "
                    f"auto_proceed={not desired} applied={applied}"
                )
                return

            if type == 'set-pdf-canvas-as-context':
                from .pdf_context import PdfContextError, resolve_pdf_context
                try:
                    directory, context_filename = await asyncio.to_thread(
                        resolve_pdf_context, text_data_json.get('context_token'), user.pk,
                    )
                except PdfContextError as error:
                    await self.send(text_data=json.dumps({
                        'type': 'pdf-canvas-context-error', 'message': str(error),
                    }))
                    return
                global_state.set_state('chat_hist_summarizer_counter', 0)
                await self.save_session_state(user, str(directory), 'file', context_filename)
                await self.send(text_data=json.dumps({
                    'type': 'context-path-set',
                    'context_path': str(directory / context_filename),
                    'context_type': 'file', 'context_filename': context_filename,
                }))
                context_token = text_data_json.get('context_token')
                async def load_pdf_context():
                    success = False
                    try:
                        success = await self.setup_contextual_rag_chain(str(directory), context_filename)
                    except Exception as error:
                        # Setup also reads configuration before its internal
                        # error handler. Always complete the progress dialog.
                        print(f'!!! PDF context setup failed: {error}')
                    await self.send(text_data=json.dumps({
                        'type': 'pdf-canvas-context-finished', 'context_token': context_token,
                        'success': success is True,
                    }))
                asyncio.create_task(load_pdf_context())
                return

            if type == 'set-canvas-as-context':
                print("--- Received set-canvas-as-context message from client.")
                print(f"--- The message(filename) is: {message}")
                safe_filename = _sanitize_context_filename(message)
                context_files_path = safe_join_under(get_runtime_agent_root(), 'context_files')

                if safe_filename is None or context_files_path is None:
                    error_message = "Invalid canvas filename received."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': error_message, 'username': 'Tlamatini'}
                    )
                    return

                os.makedirs(context_files_path, exist_ok=True)
                target_context_file = safe_join_under(context_files_path, safe_filename)
                if target_context_file is None:
                    error_message = "Invalid canvas filename received."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': error_message, 'username': 'Tlamatini'}
                    )
                    return

                print(f"--- The context_files_path is: {context_files_path}")
                content = text_data_json['content']
                with open(target_context_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                print("--- Rebuilding contextual RAG chain....")
                global_state.set_state('chat_hist_summarizer_counter', 0)
                await self.save_session_state(user, context_files_path, 'file', safe_filename)
                print(f"--- Session state saved: file - {target_context_file}")
                await self.send(text_data=json.dumps({
                    'type': 'context-path-set',
                    'context_path': target_context_file,
                    'context_type': 'file',
                    'context_filename': safe_filename
                }))
                asyncio.create_task(self.setup_contextual_rag_chain(context_files_path, safe_filename))
                return
            if type == 'unset-canvas-as-context':
                print("--- Received unset-canvas-as-context message from client.")
                self._gauge_reason = "context cleared"
                global_state.set_state('chat_hist_summarizer_counter', 0)                
                asyncio.create_task(self.setup_rag_chain())
                return
            if type == 'set-directory-as-context':
                print("--- Received set-directory-as-context message from client.")
                print(f"--- The message(directory) is: {message}")
                context_path = resolve_runtime_agent_path(message)

                print(f"--- The resolved context_path is: {context_path}")
                if context_path is None:
                    error_message = "Selected directory is outside the application root path and is not allowed."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': error_message, 'username': 'Tlamatini'}
                    )
                    return

                if os.path.exists(context_path) and not os.path.isdir(context_path):
                    error_message = "Selected directory is not a valid directory."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': error_message, 'username': 'Tlamatini'}
                    )
                    return

                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Your request is being processed by Tlamatini. Please wait a moment.", 'username': 'Tlamatini'}
                )
                print("--- Bot message broadcast to room.")
                print("--- Rebuilding contextual RAG chain....")
                global_state.set_state('chat_hist_summarizer_counter', 0)
                await self.save_session_state(user, context_path, 'directory', None)
                print(f"--- Session state saved: directory - {context_path}")
                await self.send(text_data=json.dumps({
                    'type': 'context-path-set',
                    'context_path': context_path,
                    'context_type': 'directory',
                    'context_filename': None
                }))
                asyncio.create_task(self.setup_contextual_rag_chain(context_path))
                return
            
            if type == 'set-file-as-context':
                print("--- Received set-file-as-context message from client.")
                print(f"--- The message(filename) is: {message}")
                safe_filename = _sanitize_context_filename(message)
                if getattr(sys, 'frozen', False):
                    application_path = safe_join_under(get_runtime_agent_root(), 'applications')
                else:
                    application_path = get_runtime_agent_root()

                target_context_file = safe_join_under(application_path, safe_filename) if application_path and safe_filename else None
                if target_context_file is None:
                    error_message = "Selected file is outside the application root path and is not allowed."
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': error_message, 'username': 'Tlamatini'}
                    )
                    return

                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Your request is being processed by Tlamatini. Please wait a moment.", 'username': 'Tlamatini'}
                )
                print("--- Bot message broadcast to room.")
                global_state.set_state('chat_hist_summarizer_counter', 0)
                await self.save_session_state(user, application_path, 'file', safe_filename)
                print(f"--- Session state saved: file - {target_context_file}")
                await self.send(text_data=json.dumps({
                    'type': 'context-path-set',
                    'context_path': target_context_file,
                    'context_type': 'file',
                    'context_filename': safe_filename
                }))
                asyncio.create_task(self.setup_contextual_rag_chain(application_path, safe_filename))
                return            

            if type == 'cancel-current':
                print("--- Received cancel-current message from client. AGGRESSIVELY cancelling LLM...")
                try:
                    # ── Step 1: LATCH this run dead, and SILENCE it (2026-07-14) ──
                    # `request_cancel_generation(uid)` raises the legacy boolean AND
                    # permanently latches the epoch of the run that is executing right
                    # now, so Step 8's `clear_cancel_generation()` below (which the
                    # chain rebuild needs) can no longer resurrect it. Prefer the key
                    # of the ACTUAL in-flight run over `user.id`, so the latch always
                    # lands on the run the user is looking at.
                    _cancel_key = (
                        self._active_run[0] if getattr(self, '_active_run', None)
                        else (user.id if user and user.is_authenticated else 'anonymous')
                    )
                    request_cancel_generation(_cancel_key)
                    print(f"--- [CANCEL] Run latched cancelled for {_cancel_key} ---")

                    # Revoke the self-healing status emitter IMMEDIATELY. Even a single
                    # late "🔁 Tactic #…" frame from the dying executor puts the browser
                    # back into its busy state — that is what flipped the Send button
                    # back to "Cancel" by itself, over and over. Pass the SPECIFIC emit
                    # handle: unregister is identity-guarded on purpose so a second tab
                    # of the same user keeps its own live emitter.
                    if getattr(self, '_status_emit', None):
                        from .self_healing import unregister_status_broadcaster
                        unregister_status_broadcaster(_cancel_key, self._status_emit)
                        self._status_emit = None
                        print("--- [CANCEL] self-healing status emitter revoked ---")
                    
                    # Step 2: Broadcast cancellation message immediately
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_CANCELLED, 'username': 'Tlamatini'}
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
                            {'type': 'agent_message', 'message': constants.MSG_LLM_CONNECTION_DESTROYED, 'username': 'Tlamatini'}
                        )
                        print("--- [CANCEL] Connection destruction confirmed to user ---")
                    
                    # Step 6: Reset counters
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                    
                    # Step 7: Notify user we are rebuilding
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_REBUILDING, 'username': 'Tlamatini'}
                    )
                    print("--- [CANCEL] Rebuilding notification sent ---")
                    
                    # Step 8: Lower the legacy BOOLEAN before rebuilding.
                    # This is required: setup_rag_chain() bails out while the boolean is
                    # up and would leave self.rag_chain = None. It is now SAFE — it
                    # clears only the boolean, NEVER the epoch latch set in Step 1, so
                    # the cancelled run stays cancelled. Lowering the boolean here used
                    # to be the whole bug. Do NOT "simplify" this into a full un-cancel.
                    clear_cancel_generation()
                    print("--- [CANCEL] Legacy boolean cleared (epoch latch KEPT) ---")
                    
                    # Step 8.5: Clear session state and global_state cache to erase context
                    await self.clear_session_state(user)
                    print("--- [CANCEL] Session state cleared ---")
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- [CANCEL] Cleared global_state cache for user {user_id} ---")
                    
                    # Step 9: Rebuild the RAG chain with fresh connection (BLOCKING)
                    # We must wait for the rebuild to complete before telling the
                    # user that the agent is ready.  Otherwise, a request that
                    # arrives before the rebuild finishes will hit
                    # "Cannot send a request, as the client has been closed".
                    print("--- [CANCEL] Scheduling RAG chain rebuild (awaiting completion) ---")
                    self._gauge_reason = "cancelled, agent rebuilt"
                    await self.setup_rag_chain()

                    # Step 10: Send confirmation that rebuild is done
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_REESTABLISHED, 'username': 'Tlamatini'}
                    )
                    print("--- [CANCEL] Agent rebuild completed, user notified ---")
                    
                except Exception as e:
                    print(f"!!! ERROR while requesting cancellation: {e}")
                    # Still try to notify user of error
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': f'⚠ Cancellation completed with warning: {str(e)[:100]}', 'username': 'Tlamatini'}
                    )
                return

            if type == 'reconnect-llm-agent':
                print("--- Received reconnect-llm-agent message from client. Attempting to reconnect LLM...")
                try:
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        client = self.rag_chain.getHttpxClientInstance()
                        if client:
                            client.close()
                    # Clear global_state cache to force new RAG chain creation
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- Cleared global_state cache for user {user_id}")
                    self._gauge_reason = "reconnected"
                    asyncio.create_task(self.setup_rag_chain())
                    print("--- LLM reconnected.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_RECONNECT, 'username': 'Tlamatini'}
                    )
                    global_state.set_state('chat_hist_summarizer_counter', 0)                    
                    print("--- LLM reconnected message broadcasted to room.")
                except Exception as e:
                    print(f"!!! ERROR while requesting reconnection: {e}")
                return

            if type == 'clean-history-and-reconnect':
                print("--- Received clean-history-and-reconnect message from client.")
                try:
                    # Delete only the requesting user's chat history.
                    await self.delete_messages_for_user(user)
                    print(f"--- AgentMessage records deleted for user {user.id}.")
                    
                    # Clear global_state cache to force new RAG chain creation
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- Cleared global_state cache for user {user_id}")
                    
                    # Proceed with reconnection
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        client = self.rag_chain.getHttpxClientInstance()
                        if client:
                            client.close()
                    self._gauge_reason = "history cleared"
                    asyncio.create_task(self.setup_rag_chain())
                    print("--- LLM reconnected after history clean.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_HISTORY_CLEANED, 'username': 'Tlamatini'}
                    )
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                except Exception as e:
                    print(f"!!! ERROR while cleaning history: {e}")
                return

            if type == 'clear-context':
                print("--- Received clear-context message from client. Attempting to reconnect LLM...")
                try:
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        client = self.rag_chain.getHttpxClientInstance()
                        if client:
                            client.close()
                    # Clear session state
                    await self.clear_session_state(user)
                    print("--- Session state cleared.")
                    # Clear global_state cache to force new RAG chain creation
                    user_id = user.id if user and user.is_authenticated else 'anonymous'
                    global_state.set_state(f'rag_chain_{user_id}', None)
                    global_state.set_state(f'context_path_{user_id}', None)
                    print(f"--- Cleared global_state cache for user {user_id}")
                    self._gauge_reason = "context cleared"
                    asyncio.create_task(self.setup_rag_chain())
                    print("--- LLM context cleaned and reconnected.")
                    await self.channel_layer.group_send(   # type: ignore
                        self.room_group_name,
                        {'type': 'agent_message', 'message': constants.MSG_LLM_CLEARCONTEXT, 'username': 'Tlamatini'}
                    )
                    global_state.set_state('chat_hist_summarizer_counter', 0)
                    print("--- LLM context cleaned and reconnected message broadcasted to room.")
                except Exception as e:
                    print(f"!!! ERROR while requesting context clean and reconnection: {e}")
                return

            if type == 'cancel-all':
                print("--- Received cancel-all message from client. Attempting to cancel LLM...")
                try:
                    _cancel_key = (
                        self._active_run[0] if getattr(self, '_active_run', None)
                        else (user.id if user and user.is_authenticated else 'anonymous')
                    )
                    request_cancel_generation(_cancel_key)
                    if getattr(self, '_status_emit', None):
                        from .self_healing import unregister_status_broadcaster
                        unregister_status_broadcaster(_cancel_key, self._status_emit)
                        self._status_emit = None
                    global_state.set_state('rag_chain_ready', True)
                    if hasattr(self, 'rag_chain') and self.rag_chain:
                        client = self.rag_chain.getHttpxClientInstance()
                        if client:
                            client.close()
                    # Lower the legacy boolean (the epoch latch above carries the real
                    # cancellation now). Leaving it up used to poison any later
                    # setup_rag_chain(), which bails on it and leaves the user with NO
                    # chain — a latent second cancel bug. (2026-07-14)
                    clear_cancel_generation()
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
                resolved_directory = resolve_runtime_agent_path(message)
                if resolved_directory is None:
                    tree_view_content = "Error: Directory is outside the allowed paths."
                else:
                    tree_view_content = generate_tree_view_content(resolved_directory)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "_tree_:"+tree_view_content, 'username': 'Tlamatini'}
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
                        {'type': 'agent_message', 'message': "Omissions can't be empty, be sure you introduce extension in the format: jpg,bmp,etc.", 'username': 'Tlamatini'}
                    )
                    print("--- Bot message broadcast to room.")
                    return
                await self.save_omissions("omission-1", omissions)
                self.omissions = omissions
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': "Files by extension that will be omitted during context loading saved: "+omissions+".\n\nYou need to restart the agent/connection to apply the changes.", 'username': 'Tlamatini'}
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
                await self._after_toggles_saved('mcp', None, self._toggles_summary("MCPs", message))
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-tools':
                print(f"--- Received set-tools message from client, message: {message}")
                tools = message
                if(tools == '' or tools.isspace()):
                    print("--- Error tools are empty. Message rejected.")
                    return
                before_rows = await self.get_all_tools()
                tools = message.split(',')
                for tool in tools:
                    if(tool == '' or tool.isspace()):
                        print("--- End of tools list.")
                        break
                    descAndContent = tool.split('=', 2)
                    if len(descAndContent) != 3:
                        print(f"--- Skipping malformed tool toggle payload: {tool}")
                        continue
                    toolName = _normalize_toggle_record_name('tool', descAndContent[0])
                    if toolName is None:
                        print(f"--- Skipping invalid tool name in payload: {descAndContent[0]}")
                        continue
                    toolDescription = descAndContent[1]
                    toolContent = descAndContent[2]
                    await self.save_tool(toolName, toolDescription, toolContent)
                await self._after_toggles_saved('tool', before_rows, self._toggles_summary("Tools", message))
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-agents':
                print(f"--- Received set-agents message from client, message: {message}")
                agents = message
                if(agents == '' or agents.isspace()):
                    print("--- Error agents are empty. Message rejected.")
                    return
                before_rows = await self.get_all_agents()
                agents = message.split(',')
                for agent in agents:
                    if(agent == '' or agent.isspace()):
                        print("--- End of agents list.")
                        break
                    descAndContent = agent.split('=', 2)
                    if len(descAndContent) != 3:
                        print(f"--- Skipping malformed agent toggle payload: {agent}")
                        continue
                    agentName = _normalize_toggle_record_name('agent', descAndContent[0])
                    if agentName is None:
                        print(f"--- Skipping invalid agent name in payload: {descAndContent[0]}")
                        continue
                    agentDescription = descAndContent[1]
                    agentContent = descAndContent[2]
                    await self.save_agent(agentName, agentDescription, agentContent)
                await self._after_toggles_saved('agent', before_rows, self._toggles_summary("Agents", message))
                print("--- Bot message broadcast to room.")
                return

            if type == 'set-skills':
                # Toggle ACPX-Skills enable/disable. The payload encoding
                # mirrors set-tools / set-agents: comma-separated
                # `<name>=<description>=<true|false>` triples. The skill
                # name is the SKILL.md frontmatter `name` directly (no
                # `skill-N` prefix) because the Skill model already keys
                # on `name`. Only the `enabled` boolean is updated here —
                # the disk-derived `description` / `runtime` / etc are
                # owned by boot_skills() and intentionally left alone.
                print(f"--- Received set-skills message from client, message: {message}")
                if (message == '' or message.isspace()):
                    print("--- Error skills are empty. Message rejected.")
                    return
                items = message.split(',')
                touched = 0
                for raw in items:
                    if (raw == '' or raw.isspace()):
                        continue
                    descAndContent = raw.split('=', 2)
                    if len(descAndContent) != 3:
                        print(f"--- Skipping malformed skill toggle payload: {raw}")
                        continue
                    skill_name = (descAndContent[0] or '').strip()
                    if not skill_name:
                        print(f"--- Skipping empty skill name in payload: {raw}")
                        continue
                    enabled = (descAndContent[2] or '').strip().lower() == 'true'
                    await self.save_skill(skill_name, enabled)
                    touched += 1
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message',
                     'message': f"Skills activation updated ({touched} skill(s)). The change applies to the next request.",
                     'username': 'Tlamatini'}
                )
                print(f"--- Bot message broadcast to room. Touched {touched} skill rows.")
                await self._after_toggles_saved('skill', None, None)
                return

            if re.match(constants.REGEX_GREETING, message, flags=re.IGNORECASE):
                print("--- User message saved to DB.")
                greeting_id = await self.save_message(user, message, conversation_user=user)
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': message, 'username': user.username,
                     'message_id': greeting_id}
                )
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.MSG_GREETING_RESPONSE, 'username': 'Tlamatini'}
                )
                print("--- User question broadcasted to room.")
                return
            
            if not global_state.get_state('rag_chain_ready'):
                print("!!! RAG chain not ready. Message rejected.")
                # Self-heal: a not-ready chain (a build that failed, or a
                # toggle-triggered rebuild that is mid-flight) would otherwise stay
                # dead until some UNRELATED event (a toggle / clear-history) happens
                # to trigger a successful rebuild -- so every message in between is
                # rejected with "agent not ready" (the dominant chat failure). Kick
                # off a rebuild here so the chain recovers on its own. ``rag_lock``
                # serializes rebuilds and ``.locked()`` prevents a rebuild storm
                # under repeated sends.
                try:
                    if not self.rag_lock.locked():
                        asyncio.create_task(self.setup_rag_chain())
                        print("--- Self-heal: triggered rag_chain rebuild after not-ready reject.")
                except Exception as _heal_err:  # never let self-heal break the reject path
                    print(f"--- Self-heal rebuild trigger failed (non-fatal): {_heal_err}")
                bot_user, _ = await self.get_or_create_bot_user()
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'agent_message', 'message': constants.ERROR_AGENT_NOT_READY_SIMPLE, 'username': 'Tlamatini'}
                )
                print("--- Bot message broadcast to room.")
                return
            
            print(f"--- Message parsed: '{message}' from user '{user.username}' **** to be sent to LLM")
            user_message_id = await self.save_message(user, message, conversation_user=user)
            print(f"--- User message saved to DB (id={user_message_id}).")
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': message, 'username': user.username,
                 'message_id': user_message_id}
            )
            print("--- User question broadcasted to room.")
            print("--- User question is now being processed by the LLM.")
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': constants.MSG_PROCESSING_REQUEST, 'username': 'Tlamatini'}
            )
            print("--- Bot message broadcast to room.")
            asyncio.create_task(self.queue_llm_retrieval(
                message, user,
                multi_turn_enabled=multi_turn_enabled,
                exec_report_enabled=exec_report_enabled,
                acpx_enabled=acpx_enabled,
                ask_execs_enabled=ask_execs_enabled,
                step_by_step_enabled=step_by_step_enabled,
            ))
        except Exception as e:
            print(f"!!! ERROR in receive method: {e}")
            not_ready_response = constants.ERROR_AGENT_NOT_READY
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': not_ready_response, 'username': 'Tlamatini'}
            )
            errorDetail = "Error detail: " + str(e)
            await self.channel_layer.group_send(   # type: ignore
                self.room_group_name,
                {'type': 'agent_message', 'message': errorDetail, 'username': 'Tlamatini'}
            )
            print("--- Bot error message broadcast to room.")

    async def agent_message(self, event):
        message = event['message']
        username = event['username']
        print(f"--- Sending message to WebSocket: '{message}' from '{username}'")
        ws_payload = {
            'message': message,
            'username': username
        }
        if event.get('tool_calls_log'):
            ws_payload['tool_calls_log'] = event['tool_calls_log']
        if event.get('multi_turn_used'):
            ws_payload['multi_turn_used'] = True
        # The AgentMessage primary key, present ONLY for frames that were
        # saved to the conversation (the user's prompt, Tlamatini's answer).
        # Live status lines carry none: they were never in the history.
        if event.get('message_id'):
            ws_payload['message_id'] = event['message_id']
        await self.send(text_data=json.dumps(ws_payload))

    async def message_dropped(self, event):
        """Group handler: a message was dropped from this user's history.
        Every open tab of the same user removes the card, not only the tab
        whose Drop button was pressed."""
        await self.send(text_data=json.dumps({
            'type': 'message-dropped',
            'message_id': event.get('message_id'),
            # Every row that went with it (the prompt's rephrase rows).
            'message_ids': event.get('message_ids') or [event.get('message_id')],
            'ok': True,
        }))

    async def _handle_drop_message(self, user, payload):
        """The Drop button on a chat card (Angela, 2026-09-30).

        WHERE THE LLM'S MEMORY LIVES. The conversation the model reads is
        rebuilt from the AgentMessage table on EVERY request
        (DBChatHistoryLoader.load, newest 8 rows of this user). No summary is
        cached, no LangGraph checkpoint exists, and the chain object holds no
        history of its own. So deleting the ONE row is the whole job: from the
        next request on, the model reads the conversation as if that message
        had never been written, the rows before and after it are untouched, and
        no reconnect or chain rebuild is needed. The window simply slides back
        to include one older message, exactly as if this one never existed.

        Refused while a request is being answered on this connection: that run
        already read its history, and the answer it is about to save must not
        land beside a history that changed under it.
        """
        raw_id = payload.get('message_id')
        try:
            message_id = int(raw_id)
        except (TypeError, ValueError):
            message_id = 0
        reply = {'type': 'message-dropped', 'message_id': raw_id, 'ok': False}
        if message_id <= 0:
            reply['reason'] = 'This message has no saved id, so there is nothing to drop from the history.'
        elif getattr(self, '_active_run', None):
            reply['reason'] = ('Tlamatini is still answering. Drop the message again '
                               'when she has finished.')
        else:
            deleted = await self.delete_message_for_user(user, message_id)
            if deleted:
                print(f"--- [DROP] message id={message_id} removed from user {user.id}'s "
                      f"history (rows {deleted}); the next request will not see it.")
                await self.channel_layer.group_send(   # type: ignore
                    self.room_group_name,
                    {'type': 'message_dropped', 'message_id': message_id,
                     'message_ids': deleted},
                )
                # The at-rest context gauge predicted the NEXT request with the
                # old history; recalculate it now that the history is shorter.
                self._schedule_context_gauge_refresh("message dropped")
                return
            # Nothing of THIS user's matched: already dropped in another tab, or
            # removed by Clear history. The goal state holds either way.
            print(f"--- [DROP] message id={message_id} was not in user {user.id}'s history.")
            reply['ok'] = True
            reply['already_gone'] = True
        await self.send(text_data=json.dumps(reply))

    @database_sync_to_async
    def save_message(self, user, message, conversation_user=None):
        # Returns the row's primary key so the broadcast frame can carry it as
        # `message_id` - the Drop button on the card needs it to name the row.
        return AgentMessage.objects.create(user=user, conversation_user=conversation_user, message=message).pk

    @database_sync_to_async
    def load_recent_chat_history(self, user, limit=8):
        return DBChatHistoryLoader.load(limit=limit, conversation_user=user)

    @database_sync_to_async
    def delete_messages_for_user(self, user):
        AgentMessage.objects.filter(conversation_user=user).delete()

    @database_sync_to_async
    def delete_message_for_user(self, user, message_id):
        """Drop ONE message from THIS user's conversation (the Drop button).

        Filtered by ``conversation_user`` as well as the primary key, so a
        forged id can never reach another user's history. Returns the list of
        deleted ids - empty when there was nothing of this user's to drop.

        A USER prompt also takes the "Referenced Rephrase:" rows the chain
        saved for it right after it (rag/interaction.py::show_rephrased_question
        - the question REWORDED against the history). The model never reads
        those rows (DBChatHistoryLoader skips them), but a page reload replays
        them, so leaving one behind would bring the dropped words back on
        screen. Only the rows directly following the prompt go, up to the
        first row that is not a rephrase (normally Tlamatini's answer, which
        stays unless she drops it too).
        """
        row = AgentMessage.objects.select_related('user').filter(
            pk=message_id, conversation_user=user).first()
        if row is None:
            return []
        doomed = [row.pk]
        if getattr(row.user, 'username', '') != DBChatHistoryLoader.BOT_USERNAME:
            following = (AgentMessage.objects
                         .filter(conversation_user=user, pk__gt=row.pk)
                         .order_by('pk')[:20])
            for later in following:
                if str(later.message or '').lstrip().lower().startswith('referenced rephrase:'):
                    doomed.append(later.pk)
                    continue
                break
        AgentMessage.objects.filter(pk__in=doomed, conversation_user=user).delete()
        return doomed

    @database_sync_to_async
    def save_program(self, programName, programLanguage, programContent):
        LLMProgram.objects.create(programName=programName, programLanguage=programLanguage, programContent=programContent)

    @database_sync_to_async
    def get_program_by_name(self, programName):
        # COLLISION-PROOF (Angela, 2026-09-06) - see
        # services/response_parser._uniquify_name. Two code blocks of the same
        # answer used to share one name, and `.get()` then raised
        # MultipleObjectsReturned instead of returning the file.
        program = LLMProgram.objects.filter(programName=programName).order_by('-idProgram').first()
        if program is None:
            raise LLMProgram.DoesNotExist(f"No LLMProgram named '{programName}'")
        return program

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
        existing = Mcp.objects.filter(mcpName=mcpName).order_by('idMcp').first()
        if existing is None:
            Mcp.objects.create(
                idMcp=_get_next_integer_pk(Mcp, 'idMcp'),
                mcpName=mcpName,
                mcpDescription=mcpDescription,
                mcpContent=mcpContent
            )
            return

        Mcp.objects.filter(mcpName=mcpName).exclude(pk=existing.pk).delete()
        existing.mcpDescription = mcpDescription
        existing.mcpContent = mcpContent
        existing.save(update_fields=['mcpDescription', 'mcpContent'])

    @database_sync_to_async
    def save_tool(self, toolName, toolDescription, toolContent):
        existing = Tool.objects.filter(toolName=toolName).order_by('idTool').first()
        if existing is None:
            Tool.objects.create(
                idTool=_get_next_integer_pk(Tool, 'idTool'),
                toolName=toolName,
                toolDescription=toolDescription,
                toolContent=toolContent
            )
            return

        Tool.objects.filter(toolName=toolName).exclude(pk=existing.pk).delete()
        existing.toolDescription = toolDescription
        existing.toolContent = toolContent
        existing.save(update_fields=['toolDescription', 'toolContent'])

    @database_sync_to_async
    def save_agent(self, agentName, agentDescription, agentContent):
        existing = Agent.objects.filter(agentName=agentName).order_by('idAgent').first()
        if existing is None:
            Agent.objects.create(
                idAgent=_get_next_integer_pk(Agent, 'idAgent'),
                agentName=agentName,
                agentDescription=agentDescription,
                agentContent=agentContent
            )
            return

        Agent.objects.filter(agentName=agentName).exclude(pk=existing.pk).delete()
        existing.agentDescription = agentDescription
        existing.agentContent = agentContent
        existing.save(update_fields=['agentDescription', 'agentContent'])

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
        return list(Mcp.objects.order_by('idMcp').values('mcpName', 'mcpDescription', 'mcpContent'))

    @database_sync_to_async
    def get_all_tools(self):
        """Return all Tool records (name, content) as list of dicts."""
        return list(Tool.objects.order_by('idTool').values('toolName', 'toolDescription', 'toolContent'))

    @database_sync_to_async
    def get_all_agents(self):
        """Return all Agent records (name, content) as list of dicts."""
        return list(Agent.objects.order_by('idAgent').values('agentName', 'agentDescription', 'agentContent'))

    @database_sync_to_async
    def get_all_skills(self):
        """
        Return all Skill rows ordered by name. Skills are keyed by `name`
        (the SKILL.md frontmatter name, e.g. `acp-router`) rather than the
        `skill-N` prefix pattern used by Mcps / Tools / Agents, because the
        underlying registry is keyed by name on disk.
        """
        return list(
            Skill.objects.order_by('name').values('name', 'description', 'enabled')
        )

    @database_sync_to_async
    def save_skill(self, name, enabled):
        """
        Toggle Skill.enabled on/off. Idempotent: missing rows are skipped
        rather than auto-created — boot_skills() owns row lifecycle (it
        seeds new disk skills + prunes orphans), so a toggle for an
        unknown name is treated as a stale-frontend race, not an error.
        """
        try:
            row = Skill.objects.filter(name=name).first()
            if row is None:
                print(f"--- save_skill: no Skill row named '{name}' (race with boot_skills?); ignoring")
                return
            if row.enabled != bool(enabled):
                row.enabled = bool(enabled)
                row.save(update_fields=['enabled', 'last_loaded_at'])
        except Exception as e:
            print(f"--- save_skill failed for '{name}': {e}")

    @database_sync_to_async
    def get_all_agent_processes(self):
        """Return all AgentProcess records (description, pid) as list of dicts."""
        return list(AgentProcess.objects.values('agentProcessDescription', 'agentProcessPid'))

    @database_sync_to_async
    def get_or_create_bot_user(self):
        return User.objects.get_or_create(username='Tlamatini')



