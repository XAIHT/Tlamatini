from django.apps import AppConfig


class AgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'

    def ready(self):
        """
        Ensure the MCP system server runs in the background for the lifetime
        of the Django process (e.g., when using `runserver --noreload` or our
        custom `startserver`). We start it once in a daemon thread.
        """
        try:
            # Lazy imports to avoid impacting management commands that scan apps
            import sys
            import threading
            import asyncio
            import logging
            from .global_state import global_state
            from .mcp_system_server import main as mcp_main
            from .mcp_files_search_server import serve as files_serve
            from .models import AgentProcess, ChatAgentRun

            # Do not start multiple times
            if global_state.get_state('mcp_server_running'):
                return

            # Only start during typical server runs
            argv = ' '.join(sys.argv).lower()
            should_start = (
                'runserver' in argv or
                'startserver' in argv or
                'daphne' in argv or
                'asgi' in argv
            )
            if not should_start:
                return

            # Cleanup AgentProcess records on startup
            try:
                AgentProcess.objects.all().delete()
                print("--- Cleaned up all AgentProcess records on startup.")
            except Exception:
                logging.exception("Failed to cleanup AgentProcess records")

            try:
                ChatAgentRun.objects.all().delete()
                print("--- Cleaned up all ChatAgentRun records on startup.")
            except Exception:
                logging.exception("Failed to cleanup ChatAgentRun records")

            # Repopulate Agent table on startup to ensure all agents in the directory are discovered
            # This is critical for "frozen" mode where migrations might not reflect the actual file system state
            try:
                from .models import Agent
                import os
                import sys

                # Determine agents directory logic (duplicate of pool path logic but for source agents)
                if getattr(sys, "frozen", False):
                    # In frozen mode, executable is in the root of the bundle
                    exe_dir = os.path.dirname(sys.executable)
                    agents_dir = os.path.join(exe_dir, 'agents')
                else:
                    # In dev mode, agents are in the agent app directory
                    module_dir = os.path.dirname(os.path.abspath(__file__))
                    agents_dir = os.path.join(module_dir, 'agents')

                if os.path.exists(agents_dir):
                    # Get all agent folders
                    agent_folders = []
                    for item in os.listdir(agents_dir):
                        item_path = os.path.join(agents_dir, item)
                        # Skip pools, pycache, and non-directories
                        if os.path.isdir(item_path) and item.lower() not in ['pools', '__pycache__']:
                            agent_folders.append(item)
                    
                    agent_folders.sort()
                    
                    # Clear existing agents
                    Agent.objects.all().delete()
                    
                    print(f"--- Repopulating {len(agent_folders)} agents from {agents_dir}...")

                    # Populate new agents
                    for index, folder_name in enumerate(agent_folders, start=1):
                        # Create display name logic
                        display_name = folder_name.replace('_', ' ')
                        
                        # Consistent casing logic
                        if len(display_name) <= 3:
                            display_name = display_name.upper()
                        else:
                            display_name = display_name.title()
                            
                        # Specific overrides
                        if display_name.lower() == 'and':
                            display_name = 'AND'
                        elif display_name.lower() == 'or':
                            display_name = 'OR'
                        elif display_name.lower() == 'monitor log':
                            display_name = 'Monitor Log'
                        elif display_name.lower() == 'monitor netstat':
                            display_name = 'Monitor Netstat'
                        elif display_name.lower() == 'recmailer':
                             display_name = 'RecMailer'
                            
                        agent_name = f"agent-{index}"
                        
                        Agent.objects.create(
                            idAgent=index,
                            agentName=agent_name,
                            agentDescription=display_name,
                            agentContent='true' # Keeps existing convention
                        )
                    print("--- Agent repopulation complete.")
                else:
                    print(f"--- Warning: Agents directory not found at {agents_dir} during startup population")

            except Exception as e:
                logging.exception(f"Failed to repopulate agents on startup: {e}")

            # Cleanup pool directory on startup
            try:
                import os
                import shutil
                
                # Determine pool path based on frozen mode
                if getattr(sys, "frozen", False):
                    exe_dir = os.path.dirname(sys.executable)
                    pool_path = os.path.join(exe_dir, 'agents', 'pools')
                else:
                    module_dir = os.path.dirname(os.path.abspath(__file__))
                    pool_path = os.path.join(module_dir, 'agents', 'pools')
                
                if os.path.exists(pool_path):
                    for item in os.listdir(pool_path):
                        item_path = os.path.join(pool_path, item)
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                    print(f"--- Cleaned up pools directory on startup: {pool_path}")
                else:
                    print(f"--- Pools directory does not exist, skipping cleanup: {pool_path}")
            except Exception:
                logging.exception("Failed to cleanup pool directory")

            # Register cleanup handlers for shutdown (Ctrl+C, window close, etc.)
            import atexit
            import signal
            import psutil
            
            def recursive_kill(pid):
                """Recursively kill a process and all its children (God Mode)."""
                try:
                    parent = psutil.Process(pid)
                    children = parent.children(recursive=True)
                except psutil.NoSuchProcess:
                    return

                # Kill children first
                for child in children:
                    try:
                        print(f"--- [GOD MODE] Killing child process PID {child.pid} ({child.name()})...")
                        child.kill()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass

                # Kill parent
                try:
                    print(f"--- [GOD MODE] Killing process PID {parent.pid} ({parent.name()})...")
                    parent.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            def cleanup_pool_on_shutdown():
                """Clear pool directory contents on application shutdown."""
                print("\n--- [SHUTDOWN] Initiating aggressive cleanup protocols...")
                try:
                    import os
                    import shutil
                    import sys
                    from concurrent.futures import ThreadPoolExecutor
                    
                    # 1. Kill tracked processes from DB (run in thread to avoid async context issues)
                    def kill_tracked_processes():
                        try:
                            processes = list(AgentProcess.objects.all())
                            if processes:
                                print(f"--- Found {len(processes)} tracked processes to exterminate.")
                                for proc in processes:
                                    recursive_kill(proc.agentProcessPid)
                                AgentProcess.objects.all().delete()
                        except Exception as e:
                            print(f"--- Warning: Failed to kill tracked processes: {e}")
                    
                    try:
                        # Execute DB operations in a separate thread to avoid async context issues
                        with ThreadPoolExecutor(max_workers=1) as executor:
                            future = executor.submit(kill_tracked_processes)
                            future.result(timeout=5)  # Wait max 5 seconds
                    except Exception as e:
                        print(f"--- Warning: Thread-based cleanup failed: {e}")

                    # 2. Kill untracked processes running from pool directory
                    if getattr(sys, "frozen", False):
                        exe_dir = os.path.dirname(sys.executable)
                        pool_path = os.path.join(exe_dir, 'agents', 'pools')
                    else:
                        module_dir = os.path.dirname(os.path.abspath(__file__))
                        pool_path = os.path.join(module_dir, 'agents', 'pools')
                    
                    try:
                        print(f"--- Scanning for survivors in {pool_path}...")
                        # Wrap entire iteration in try-except since process_iter can raise
                        # exceptions if processes disappear during iteration (race condition)
                        try:
                            # Get process list snapshot first to reduce race conditions
                            proc_list = list(psutil.process_iter(['pid', 'name', 'cmdline'], ad_value=None))
                        except Exception:
                            proc_list = []
                        
                        for proc in proc_list:
                            try:
                                cmdline = proc.info.get('cmdline')
                                if cmdline:
                                    cmdline_str = ' '.join(cmdline)
                                    if pool_path in cmdline_str:
                                        print(f"--- [GOD MODE] Found untracked survivor PID {proc.info['pid']}: {cmdline_str[:50]}...")
                                        recursive_kill(proc.info['pid'])
                            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError, KeyError):
                                # Process disappeared or became inaccessible - this is expected during shutdown
                                continue
                            except Exception:
                                # Catch any other unexpected errors gracefully
                                continue
                    except Exception as e:
                        print(f"--- Warning: Failed to scan for survivors: {e}")

                    # 3. Nuke the directories
                    if os.path.exists(pool_path):
                        for item in os.listdir(pool_path):
                            item_path = os.path.join(pool_path, item)
                            try:
                                if os.path.isdir(item_path):
                                    shutil.rmtree(item_path)
                                else:
                                    os.remove(item_path)
                            except Exception:
                                pass  # Best effort cleanup
                        print(f"--- Cleaned up pools directory on shutdown: {pool_path}")
                except Exception as e:
                    print(f"--- Warning: Failed to cleanup pools on shutdown: {e}")
            
            # Register atexit handler for normal shutdown
            if not global_state.get_state('shutdown_handler_registered'):
                atexit.register(cleanup_pool_on_shutdown)
                
                # Windows signal handling for Ctrl+C and console close
                def signal_handler(signum, frame):
                    print(f"\n--- Received signal {signum}, cleaning up...")
                    try:
                        cleanup_pool_on_shutdown()
                    except Exception as e:
                        print(f"--- Warning: Cleanup error (ignored): {e}")
                    # Use os._exit to avoid triggering atexit callbacks again
                    import os as os_module
                    os_module._exit(0)
                
                # Register signal handlers
                try:
                    signal.signal(signal.SIGINT, signal_handler)
                    # SIGBREAK is Windows-specific (console close button)
                    if hasattr(signal, 'SIGBREAK'):
                        signal.signal(signal.SIGBREAK, signal_handler)
                except Exception as sig_err:
                    print(f"--- Warning: Could not register signal handler: {sig_err}")
                
                global_state.set_state('shutdown_handler_registered', True)
                print("--- Registered pool cleanup handlers for shutdown")


            def run_mcp():
                try:
                    # Windows compatibility: ensure a selector loop if needed
                    if sys.platform.startswith('win'):
                        try:
                            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                        except Exception:
                            pass
                    asyncio.run(mcp_main())
                except Exception:
                    logging.exception("MCP system server crashed")

            t = threading.Thread(target=run_mcp, name="MCPSystemServer", daemon=True)
            t.start()
            global_state.set_state('mcp_server_running', True)

            # Start the File Search gRPC server as well
            if not global_state.get_state('mcp_files_server_running'):
                def run_mcp_files():
                    try:
                        if sys.platform.startswith('win'):
                            try:
                                asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
                            except Exception:
                                pass
                        asyncio.run(files_serve())
                    except Exception:
                        logging.exception("MCP files search server crashed")

                t2 = threading.Thread(target=run_mcp_files, name="MCPFilesSearchServer", daemon=True)
                t2.start()
                global_state.set_state('mcp_files_server_running', True)
        except Exception:
            # Never block Django startup if MCP fails; just log.
            import logging
            logging.exception("Failed to initialize MCP system server background thread")
