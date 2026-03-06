import sys
import asyncio
from django.core.management.base import BaseCommand
from agent.mcp_system_server import main as mcp1_main
from agent.mcp_files_search_server import serve as mcp2_serve


class Command(BaseCommand):
    help = "Start Django dev server and run MCP system server in background (no auto-reload)."

    def add_arguments(self, parser):
        parser.add_argument('addrport', nargs='?', help='Optional port number, or ipaddr:port')
        parser.add_argument('--noreload', action='store_true', help='Disable Django autoreloader')

    def handle(self, *args, **options):
        """
        Runs MCP server in the same process event loop, then delegates to runserver
        with --noreload to prevent double-spawn. Ensures MCP task lives until
        process exit.
        """
        import threading

        def run_mcp1():
            try:
                asyncio.run(mcp1_main())
            except KeyboardInterrupt:
                pass
            except Exception as e:
                sys.stderr.write(f"MCP-1 server error: {e}\n")

        def run_mcp2():
            try:
                asyncio.run(mcp2_serve())
            except KeyboardInterrupt:
                pass
            except Exception as e:
                sys.stderr.write(f"MCP-2 server error: {e}\n")

        mcp1_thread = threading.Thread(target=run_mcp1, daemon=False, name="MCPSystemServerThread")
        mcp1_thread.start()
        mcp2_thread = threading.Thread(target=run_mcp2, daemon=False, name="MCPFilesSearchServerThread")
        mcp2_thread.start()
        from django.core.management import call_command
        addrport = options.get('addrport')
        noreload = True
        args_call = []
        
        if addrport:
            args_call.append(addrport)

        call_command('runserver', *args_call, use_reloader=not noreload)
