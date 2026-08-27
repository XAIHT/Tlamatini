"""Keep ``agent/Tlamatini.md`` (the injected ``{self_knowledge}`` system-prompt
payload) from drifting behind source.

``rag/config.py`` injects ``Tlamatini.md`` into her SYSTEM PROMPT -- it is what she
answers from when a user asks what she is. A stale count there is not a typo: it
makes her state a falsehood about herself, confidently, with nothing for the user to
check it against, inside every ``--self-modify`` build.

EVERY expectation here is DERIVED FROM SOURCE -- nothing is hand-typed -- so agent
#89 (or a new wrapped launcher / skill) makes this fail and names the file to fix.
It also checks the Multi-Turn tool breakdown ADDS UP, which is how an inconsistent
edit is caught.

Ported from the Tlamatini-Spanish tree; the Spanish-only
``SpanishEditionSelfKnowledgeTests`` (which pinned the never-speak-English rule) is
dropped -- it is meaningless in English.
"""
import os
import re
import unittest
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent          # <repo>/Tlamatini/agent
AGENTS_DIR = AGENT_DIR / "agents"
REGISTRY = AGENT_DIR / "chat_agent_registry.py"
SKILLS_PKG = AGENT_DIR / "skills_pkg"
SELF_KNOWLEDGE = AGENT_DIR / "Tlamatini.md"

# Multi-Turn tool surface = these fixed classes + the wrapped launchers.
CORE_TOOLS = 20
ACPX_SKILL_TOOLS = 12
EXTERNAL_MCP_SUPERVISORS = 10


def derive_agent_count() -> int:
    return sum(
        1 for d in os.listdir(AGENTS_DIR)
        if (AGENTS_DIR / d / f"{d}.py").is_file()
        and (AGENTS_DIR / d / "config.yaml").is_file()
    )


def derive_wrapped_count() -> int:
    return len(re.findall(r"ChatWrappedAgentSpec\(", REGISTRY.read_text(encoding="utf-8")))


def derive_skill_count() -> int:
    return sum(
        1 for d in os.listdir(SKILLS_PKG)
        if (SKILLS_PKG / d / "SKILL.md").is_file()
    )


class SelfKnowledgeCountsMatchSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SELF_KNOWLEDGE.read_text(encoding="utf-8", errors="replace")
        cls.agents = derive_agent_count()
        cls.wrapped = derive_wrapped_count()
        cls.skills = derive_skill_count()

    def test_agent_count_is_correct_everywhere(self):
        self.assertIn(f"{self.agents} workflow agents", self.text,
                      f"Tlamatini.md must say '{self.agents} workflow agents'")
        self.assertIn(f"({self.agents} of them)", self.text,
                      f"the anatomy line must say '({self.agents} of them)'")
        # Catch the exact off-by-one drift this guard was written for.
        self.assertNotIn(f"({self.agents - 1} of them)", self.text)

    def test_wrapped_count_is_correct(self):
        self.assertIn(f"{self.wrapped} wrapped", self.text,
                      f"Tlamatini.md must say '{self.wrapped} wrapped'")

    def test_skill_count_is_correct(self):
        self.assertIn(f"{self.skills} markdown", self.text,
                      f"Tlamatini.md must say '{self.skills} markdown `SKILL.md`'")

    def test_multi_turn_tool_breakdown_adds_up(self):
        m = re.search(r"(\d+)\s+Multi-Turn tools\**\s*\(([^)]*)\)", self.text)
        self.assertIsNotNone(m, "could not find the 'N Multi-Turn tools (...)' breakdown")
        total = int(m.group(1))
        parts = [int(x) for x in re.findall(r"\d+", m.group(2))]
        self.assertEqual(sum(parts), total,
                         f"breakdown {parts} must sum to the stated total {total}")
        expected = CORE_TOOLS + self.wrapped + ACPX_SKILL_TOOLS + EXTERNAL_MCP_SUPERVISORS
        self.assertEqual(total, expected,
                         f"total tools must be {expected} (20 core + {self.wrapped} wrapped + 12 + 10)")
        self.assertIn(self.wrapped, parts,
                      "the wrapped-launcher number in the breakdown must match source")


class BlueHatToolkitSelfKnowledgeTests(unittest.TestCase):
    """G7: she must know her Blue-hat toolkit exists AND that she cannot invoke it."""

    @classmethod
    def setUpClass(cls):
        cls.text = SELF_KNOWLEDGE.read_text(encoding="utf-8", errors="replace")

    def test_knows_the_toolkit_exists(self):
        self.assertIn("Blue-hat", self.text)
        self.assertIn("security/", self.text)

    def test_knows_she_cannot_invoke_it(self):
        # The two failure modes are opposite and both bad: deny having it, or
        # claim to have run a sweep she cannot run. She must know it is
        # operator-launched only.
        self.assertRegex(self.text, r"(?i)cannot invoke")


if __name__ == "__main__":
    unittest.main()
