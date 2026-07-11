# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Start the Django server with the autoreloader OFF (the MCP helper servers are started once by AgentConfig.ready())."

    def add_arguments(self, parser):
        parser.add_argument('addrport', nargs='?', help='Optional port number, or ipaddr:port')
        parser.add_argument('--noreload', action='store_true', help='Disable Django autoreloader (already the default for this command)')

    def handle(self, *args, **options):
        """
        Delegate to Django's ``runserver`` with the autoreloader OFF.

        The two MCP helper servers (System-Metrics ws :8765, Files-Search grpc :50051)
        are started EXACTLY ONCE by ``agent.apps.AgentConfig.ready()`` — its
        ``should_start`` gate matches ``startserver`` too, and the start is guarded by
        the ``mcp_server_running`` flag — so this command must NOT start them again.

        It used to spawn its own ``run_mcp1`` / ``run_mcp2`` threads here, which
        DOUBLE-BOUND the ports in the same process: the second :8765 bind raised
        ``OSError [WinError 10048]`` (swallowed to stderr) and the second :50051 bind
        silently returned 0 (gRPC ``add_insecure_port`` never raises), parking a
        non-daemon gRPC thread on a dead socket forever. Delegating to ``runserver``
        and letting ``ready()`` own the MCP servers removes the collision. See
        ``docs/claude/recent-fixes.md`` (2026-07-11).
        """
        from django.core.management import call_command
        addrport = options.get('addrport')
        args_call = [addrport] if addrport else []
        # Autoreloader OFF on purpose: a reloader child would re-run ready() and
        # re-bind the two MCP ports. (Single process => ready() binds them once.)
        call_command('runserver', *args_call, use_reloader=False)
