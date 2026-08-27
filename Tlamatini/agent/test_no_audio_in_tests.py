"""A test run must NEVER make a sound on the developer's desktop.

``manage.py`` sets ``TLAMATINI_NO_AUDIO=1`` when ``sys.argv[1] == 'test'`` (before
anything else initialises, so every spawned pool agent inherits it), and the audio
agents (Talker / AudioPlayer / VideoPlayer) check it at the single point where sound
leaves the machine. This pins both halves.
"""
import os
import unittest
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANAGE = REPO_ROOT / "Tlamatini" / "manage.py"
AGENTS = REPO_ROOT / "Tlamatini" / "agent" / "agents"


def _read(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


class ManageSetsTheFlagTests(unittest.TestCase):
    def test_manage_py_silences_tests(self):
        src = _read(MANAGE)
        self.assertIn("_silence_the_tests", src)
        self.assertIn("TLAMATINI_NO_AUDIO", src)

    def test_the_flag_is_live_during_this_very_test_run(self):
        # We are running inside `manage.py test`, so the flag must be set NOW.
        self.assertEqual(os.environ.get("TLAMATINI_NO_AUDIO"), "1")


class AudioAgentsCheckTheFlagTests(unittest.TestCase):
    def test_each_audio_agent_honours_the_flag(self):
        for name in ("talker", "audioplayer", "videoplayer"):
            src = _read(AGENTS / name / f"{name}.py")
            self.assertIn("TLAMATINI_NO_AUDIO", src, f"{name}.py must honour TLAMATINI_NO_AUDIO")


class TalkerStaysSilentTests(unittest.TestCase):
    def test_play_pcm_returns_the_no_audio_shape(self):
        os.environ["TLAMATINI_NO_AUDIO"] = "1"
        cwd = os.getcwd()
        try:
            spec = importlib.util.spec_from_file_location(
                "talker_no_audio_ut", str(AGENTS / "talker" / "talker.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            result = mod.play_pcm([0.0] * 8, 24000, {})
        finally:
            try:
                os.chdir(cwd)
            except OSError:
                pass
        self.assertEqual(result, (-1, "no-audio(test)", 0))


if __name__ == "__main__":
    unittest.main()
