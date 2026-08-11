# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove
"""The file agents must see dot-directories, and still spare `.git`."""
from __future__ import annotations

import os
import re
import unittest

AGENTS = ("globber", "mover", "deleter")
_HERE = os.path.dirname(os.path.abspath(__file__))


def _source(agent):
    p = os.path.join(_HERE, "agents", agent, "%s.py" % agent)
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()


class AgentsSeeHiddenDirectoriesTests(unittest.TestCase):

    def test_every_file_agent_globs_with_hidden_included(self):
        for agent in AGENTS:
            with self.subTest(agent=agent):
                self.assertIn(
                    "include_hidden", _source(agent),
                    "%s globs without include_hidden, so it is BLIND to "
                    "`.claude/`, `.github/`, `.agents/` - and reports 'nothing "
                    "found' / 'done' either way" % agent)

    def test_every_file_agent_prunes_the_noise_dirs(self):
        for agent in AGENTS:
            with self.subTest(agent=agent):
                src = _source(agent)
                self.assertIn("NOISE_DIRS", src,
                              "%s must prune machine-noise dirs" % agent)
                self.assertIn(".git", src,
                              "%s must keep .git out of a hidden-inclusive "
                              "glob - this is the half that makes the other "
                              "half safe" % agent)

    def test_the_hidden_flag_degrades_instead_of_crashing(self):
        # include_hidden is Python 3.11+. A frozen build on an older runtime
        # must lose the feature, never the agent.
        for agent in AGENTS:
            with self.subTest(agent=agent):
                src = _source(agent)
                self.assertIn(
                    "TypeError", src,
                    "%s must fall back when include_hidden is unsupported, "
                    "rather than raising on every run" % agent)

    def test_the_prune_backs_off_when_the_caller_asks_for_a_noise_dir(self):
        # A deliberate search inside .git must still work; the prune is a
        # default, not a prohibition.
        for agent in AGENTS:
            with self.subTest(agent=agent):
                src = _source(agent)
                self.assertTrue(
                    re.search(r"asked\s*=", src),
                    "%s must skip the prune for a noise dir the caller named "
                    "explicitly" % agent)


if __name__ == "__main__":
    unittest.main()
