# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.apps import AppConfig


class AgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'

    def ready(self):
        """
        Ensure the MCP system server runs in the background for the lifetime
        of the Django process (e.g., `runserver` with OR without `--noreload`,
        or our custom `startserver`). We start it once in a daemon thread — the
        RUN_MAIN gate below makes plain `runserver` (reloader ON) start it in the
        worker only, so the two MCP helper ports are never double-bound.
        """
        # Contacts book: export TLAMATINI_CONTACTS so every spawned pool agent
        # (Telegrammer / Whatsapper) inherits the resolved contacts.json path —
        # the same mechanism as TLAMATINI_TEMP. Fail-open; cheap on every init.
        try:
            import os as _os
            from . import contacts as _contacts
            _os.environ.setdefault('TLAMATINI_CONTACTS', _contacts.get_contacts_path())
        except Exception:
            pass
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

            # Reloader-awareness (fixes plain `runserver` colliding on :8765 / :50051).
            # `runserver` WITHOUT --noreload runs TWO processes — the autoreload watcher
            # AND the worker child — and BOTH execute ready(). Without this gate the MCP
            # helper servers (System-Metrics ws :8765 / Files-Search grpc :50051) get
            # started twice and the second bind fails with WinError 10048
            # ("only one usage of each socket address ..."). Django's autoreloader sets
            # RUN_MAIN=true ONLY in the worker child; the watcher parent leaves it unset.
            # So under the runserver reloader, start everything below ONLY in the worker.
            # --noreload / daphne / asgi / startserver run a SINGLE process (no reloader,
            # RUN_MAIN unset) and correctly fall through and start exactly once.
            import os as _os
            _runserver_reloader = ('runserver' in argv) and ('--noreload' not in argv)
            if _runserver_reloader and _os.environ.get('RUN_MAIN') != 'true':
                return

            # GPU max-performance + Ollama keep_alive=-1 pin. Runs on a
            # daemon thread so a slow nvidia-smi or cold-loading model
            # never delays Daphne. See agent/gpu_perf.py for the full
            # contract and the reason this fixes the "context loading
            # sometimes takes hours" PC-GPU thermal-throttle +
            # model-eviction symptom.
            try:
                from .gpu_perf import start_in_background as _start_gpu_perf
                from .config_loader import load_config as _load_config_for_perf
                try:
                    _perf_cfg = _load_config_for_perf()
                except Exception:
                    _perf_cfg = None
                _start_gpu_perf(_perf_cfg)
            except Exception:
                logging.exception("Failed to launch gpu_perf boot")

            # Autonomous command watchdog. An independent daemon thread that
            # kills hung console children (a malformed/interactive shell stuck
            # waiting on stdin) on its own, so a blocked tool call can never
            # freeze the whole chat. Runs off the worker thread, so it stays
            # alive even while a Multi-Turn tool is wedged. Fail-open.
            # See agent/command_watchdog.py for the full contract.
            try:
                from .command_watchdog import start_in_background as _start_cmd_watchdog
                try:
                    _wd_cfg = _load_config_for_perf()
                except Exception:
                    _wd_cfg = None
                _start_cmd_watchdog(_wd_cfg)
            except Exception:
                logging.exception("Failed to launch command watchdog boot")

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
                        elif display_name.lower() == 'stm32er':
                            # str.title() mangles 'stm32er' -> 'Stm32Er' (it
                            # capitalises the letter after the digit). The agent's
                            # canonical display name is EXACTLY 'STM32er'
                            # (chat_agent_registry.display_name). This is the single
                            # source the canvas sidebar renders verbatim, so it MUST
                            # be exact — never STM32Er / Stm32Er / STM32ER.
                            display_name = 'STM32er'

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

            # Cleanup .tlamatini runtime artifact directories on startup.
            # Two siblings live under <app-base>/.tlamatini/ and accumulate
            # garbage every run:
            #   - acpx-state/   ACPX session JSON + per-session transcript
            #                   NDJSON written by AcpSession.send_turn /
            #                   _oneshot_send_turn (agent/acpx/runtime.py)
            #   - skill-audit/<YYYY-MM>/  one NDJSON per SkillHarness invocation
            #                             written by SkillAuditLog
            #                             (agent/skills/harness.py)
            # We wipe their CONTENTS (not the parent .tlamatini/ folder) so
            # any future sibling under .tlamatini/ is preserved untouched.
            # Path resolution mirrors _app_base_dir() in agent/acpx/config.py
            # and SkillAuditLog.__init__ in agent/skills/harness.py — the
            # writers' authoritative source of truth.
            try:
                import os
                import shutil

                if getattr(sys, "frozen", False):
                    app_base = os.path.dirname(sys.executable)
                else:
                    app_base = os.path.dirname(os.path.abspath(__file__))  # agent/

                for subdir in ('acpx-state', 'skill-audit'):
                    target = os.path.join(app_base, '.tlamatini', subdir)
                    if not os.path.exists(target):
                        print(f"--- {subdir} directory does not exist, skipping cleanup: {target}")
                        continue

                    removed = 0
                    for item in os.listdir(target):
                        item_path = os.path.join(target, item)
                        try:
                            if os.path.isdir(item_path):
                                shutil.rmtree(item_path)
                            else:
                                os.remove(item_path)
                            removed += 1
                        except Exception as inner_err:
                            print(f"--- Warning: failed to remove {item_path}: {inner_err}")
                    print(f"--- Cleaned up {removed} entr{'y' if removed == 1 else 'ies'} from {target}")
            except Exception:
                logging.exception("Failed to cleanup .tlamatini runtime artifact directories")

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

                    # 4. Tier-3 final sweep: kill any conhost.exe orphans
                    #    that the tracked / pool-cmdline passes above
                    #    missed. This is the LAST chance to keep
                    #    Tlamatini-iconned conhost.exe processes from
                    #    surviving the parent — once Tlamatini.exe exits
                    #    the user will see them in Task Manager with our
                    #    icon and reasonably assume we leaked them.
                    #
                    #    Any survivor is logged with name + PID to
                    #    tlamatini.log so the user can post-mortem the
                    #    surviving processes if they need to.
                    try:
                        from .orphan_reaper import reap_orphans
                        result = reap_orphans(
                            scope="tier3:shutdown",
                            include_self_tree=True,
                            include_pool_scan=True,
                            include_console_host_sweep=True,
                            # At app exit EVERY spawned child must die so no
                            # Tlamatini-icon process is left orphaned — so the
                            # running-media protection is intentionally OFF here
                            # (it is ON for the Tier-1/Tier-2 in-session sweeps,
                            # where a Talker/AudioPlayer/VideoPlayer must keep
                            # playing to its natural end).
                            protect_running_tracked=False,
                        )
                        print(
                            f"--- [Tier-3 reaper] killed={result.killed_count} "
                            f"survivors={result.survivor_count} "
                            f"errors={len(result.errors)}"
                        )
                        if result.survivors:
                            print(
                                "--- [Tier-3 reaper] WARNING: the following "
                                "Tlamatini-spawned process(es) refused to "
                                "terminate. End them manually from Task Manager:"
                            )
                            for name, pid in result.survivors:
                                print(f"---   {name} (PID {pid})")
                    except Exception as reap_err:
                        print(f"--- [Tier-3 reaper] failed (non-fatal): {reap_err}")
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

            # ── Windows "Installed apps" / Programs-and-Features entry ──
            # Self-heal the per-user (HKCU, no-admin) Add/Remove-Programs entry
            # on every frozen launch so Tlamatini shows up in Windows' uninstall
            # list — including installs made before this feature existed. No-ops
            # in source mode (no Uninstaller.exe next to a python.exe). Fail-open.
            try:
                from . import windows_app_registration
                from .version import get_version
                windows_app_registration.self_heal_for_frozen(version=get_version())
            except Exception:
                logging.exception("Windows app registration failed (non-fatal)")

            # ── ACPX runtime + skill registry boot ──────────────────
            # Both of these are best-effort: if ACPX cannot probe a CLI
            # or the skills package is missing, Django keeps starting.
            try:
                from .acpx.service import boot_acpx, boot_skills
                # Run on a background thread so health-probes don't block startup.
                def run_acpx_boot():
                    try:
                        boot_acpx()
                        boot_skills()
                    except Exception:
                        logging.exception("ACPX/Skills boot failed")
                threading.Thread(target=run_acpx_boot,
                                 name="ACPXBoot", daemon=True).start()
            except Exception:
                logging.exception("Could not import agent.acpx.service")
        except Exception:
            # Never block Django startup if MCP fails; just log.
            import logging
            logging.exception("Failed to initialize MCP system server background thread")
