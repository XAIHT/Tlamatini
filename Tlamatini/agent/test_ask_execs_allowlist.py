# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""Pins ANGELA'S Ask-Execs policy (2026-07-14).

She found that the "Ask Execs" toggle — which the toolbar and the docs promised
would confirm "every state-changing Tool/MCP/Agent" — actually gated ONLY the 15
command/script runners. So **Deleter could wipe a glob of files, and Whatsapper
could message a real human, with no prompt at all.**

Her decision, verbatim:

    "Implement A, B, D — not C! 'cause in the case of C I need the AI moves fast
     and they are operations of visible proceding: so don't make C set ask"

    A = destroys/overwrites data      (Deleter, Mover, File-Creator, Editor,
                                       De-Compresser, unzip_file)
    B = reaches real people           (Emailer, Whatsapper, Telegrammer, Zavuerer)
    D = touches remote systems / net  (SCPer, Apirer, Nmapper, Discoverer, Crawler)
    C = desktop UI + hardware         (Keyboarder, Mouser, Windower, Playwrighter,
                                       STM32er, ESP32er, Arduiner, ESPHomer,
                                       Blenderer, Unrealer)  ← DELIBERATELY UNGATED

Tier C is NOT an oversight — it is a considered trade-off: those operations are
VISIBLE while they happen (you watch the pointer move, the window shift, the board
flash), so a confirmation prompt buys no safety and only costs speed.

These tests exist so a future refactor cannot silently (a) drop a destructive agent
out of the gate, or (b) bury her fast desktop agents behind a popup.
"""

from django.test import SimpleTestCase

from .mcp_agent import _ASK_EXECS_REQUIRED_TOOLS, _MANAGEMENT_TOOLS

# ── Tier A — silent, irreversible data loss ──────────────────────────────────
TIER_A = [
    "chat_agent_deleter",
    "chat_agent_move_file",
    "chat_agent_file_creator",
    "chat_agent_editor",
    "chat_agent_de_compresser",
    "unzip_file",
]

# ── Tier B — you cannot unsend a message to a human ──────────────────────────
TIER_B = [
    "chat_agent_send_email",
    "chat_agent_whatsapper",
    "chat_agent_telegrammer",
    "chat_agent_zavuerer",
]

# ── Tier D — remote systems / the network ───────────────────────────────────
TIER_D = [
    "chat_agent_scper",
    "chat_agent_apirer",
    "chat_agent_nmapper",
    "chat_agent_discoverer",
    "chat_agent_crawler",
]

# ── The original command/script runners (unchanged) ─────────────────────────
RUNNERS = [
    "execute_command", "chat_agent_executer",
    "execute_file", "chat_agent_pythonxer",
    "chat_agent_ssher", "chat_agent_kalier",
    "chat_agent_pser", "chat_agent_dockerer", "chat_agent_kuberneter",
    "chat_agent_jenkinser", "chat_agent_gitter",
    "chat_agent_sqler", "chat_agent_mongoxer",
    "decompile_java", "chat_agent_j_decompiler",
]

# ── Tier C — MUST STAY UNGATED (Angela's explicit call: speed + visibility) ──
TIER_C_MUST_NOT_PROMPT = [
    "chat_agent_keyboarder",
    "chat_agent_mouser",
    "chat_agent_windower",
    "chat_agent_playwrighter",
    "chat_agent_stm32er",
    "chat_agent_esp32er",
    "chat_agent_arduiner",
    "chat_agent_esphomer",
    "chat_agent_blenderer",
    "chat_agent_unrealer",
]

# ── Read-only / observational — prompting on these would be pure noise ───────
READ_ONLY_MUST_NOT_PROMPT = [
    "chat_agent_globber",
    "chat_agent_grepper",
    "chat_agent_file_interpreter",
    "chat_agent_file_extractor",
    "chat_agent_image_interpreter",
    "chat_agent_summarize_text",
    "chat_agent_shoter",
    "chat_agent_camcorder",
    "chat_agent_recorder",
    "chat_agent_whisperer",
    "chat_agent_talker",
    "chat_agent_video_analyzer",
    "googler",
]


class AskExecsAllowlistTests(SimpleTestCase):
    """The gate must match Angela's policy exactly — in BOTH directions."""

    def _gated(self, name: str) -> bool:
        return name in _ASK_EXECS_REQUIRED_TOOLS

    # ── what MUST prompt ────────────────────────────────────────────────────
    def test_tier_A_destructive_agents_are_gated(self):
        missing = [t for t in TIER_A if not self._gated(t)]
        self.assertEqual(
            missing, [],
            "These DESTROY or OVERWRITE data silently and must ask first. "
            f"Not gated: {missing}",
        )

    def test_tier_B_human_contacting_agents_are_gated(self):
        missing = [t for t in TIER_B if not self._gated(t)]
        self.assertEqual(
            missing, [],
            f"These reach REAL PEOPLE and cannot be unsent. Not gated: {missing}",
        )

    def test_tier_D_remote_and_network_agents_are_gated(self):
        missing = [t for t in TIER_D if not self._gated(t)]
        self.assertEqual(
            missing, [],
            f"These touch remote systems / the network. Not gated: {missing}",
        )

    def test_the_original_command_runners_are_still_gated(self):
        missing = [t for t in RUNNERS if not self._gated(t)]
        self.assertEqual(missing, [], f"Regression — a command runner lost its gate: {missing}")

    # ── what MUST NOT prompt ────────────────────────────────────────────────
    def test_tier_C_desktop_and_hardware_agents_are_NOT_gated(self):
        """Angela: 'I need the AI moves fast and they are operations of visible
        proceding: so don't make C set ask'. Gating these is a REGRESSION."""
        gated = [t for t in TIER_C_MUST_NOT_PROMPT if self._gated(t)]
        self.assertEqual(
            gated, [],
            "Tier C must stay UNGATED by Angela's explicit decision (speed + the "
            f"operation is visible as it happens). Wrongly gated: {gated}",
        )

    def test_read_only_tools_are_NOT_gated(self):
        gated = [t for t in READ_ONLY_MUST_NOT_PROMPT if self._gated(t)]
        self.assertEqual(gated, [], f"Read-only tools must never prompt: {gated}")

    def test_management_polling_tools_are_never_gated(self):
        overlap = sorted(set(_MANAGEMENT_TOOLS) & set(_ASK_EXECS_REQUIRED_TOOLS))
        self.assertEqual(
            overlap, [],
            "A management/polling helper must never block on a permission prompt "
            f"(it would deadlock the poll loop): {overlap}",
        )

    # ── the whole set, so a silent addition/removal is caught ───────────────
    def test_the_allowlist_is_exactly_the_agreed_set(self):
        expected = set(RUNNERS) | set(TIER_A) | set(TIER_B) | set(TIER_D)
        actual = set(_ASK_EXECS_REQUIRED_TOOLS)
        self.assertEqual(
            actual, expected,
            "The Ask-Execs allowlist drifted from Angela's agreed policy.\n"
            f"  unexpectedly ADDED  : {sorted(actual - expected)}\n"
            f"  unexpectedly REMOVED: {sorted(expected - actual)}\n"
            "If this change is intentional, update THIS test and the docs together.",
        )
