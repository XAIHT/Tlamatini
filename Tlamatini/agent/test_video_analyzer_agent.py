# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Hard, real-scenario tests for the Video-Analyzer agent (#84).

Video-Analyzer is the "eye" of Robotic-Loop-Training: it watches a recorded video
and rules PASS_OK / FAIL_NO_MOTION / FAIL_WRONG_MOTION / UNCLEAR / ANALYSIS_ERROR.
These tests exercise the REAL agent code (loaded from the pool script) — the LLM
transport is the only thing faked, because the transport is not what is under
test; the verdict logic, the deterministic motion gate, the substring-safe token
contract, and the "never a false PASS" safety override ARE.

Run:  python Tlamatini/manage.py test agent.test_video_analyzer_agent
"""
import io
import os
import logging
import importlib.util
import unittest

import numpy as np
from django.test import SimpleTestCase


# ── Load the pool script fresh, saving/restoring the cwd + logging it mutates ──
_HERE = os.path.dirname(os.path.abspath(__file__))
_VA_PATH = os.path.join(_HERE, 'agents', 'video_analyzer', 'video_analyzer.py')


def _load_video_analyzer():
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        spec = importlib.util.spec_from_file_location('video_analyzer_mod', _VA_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


va = _load_video_analyzer()


class VerdictTokenSubstringSafetyTests(unittest.TestCase):
    """THE load-bearing safety property (the adversarial critic's #1 trap): the
    Forker matches a case-sensitive substring, so a PASS token must NEVER be a
    substring of a FAIL token, or a failure would route to success.
    """

    def test_pass_token_never_matches_fail_pattern(self):
        pass_line = va.TLM_PREFIX + va.VERDICT_PASS
        fail_pattern = va.TLM_PREFIX + "FAIL"
        pass_pattern = va.TLM_PREFIX + "PASS_OK"
        self.assertIn(pass_pattern, pass_line)
        self.assertNotIn(fail_pattern, pass_line)

    def test_fail_tokens_match_fail_pattern_not_pass(self):
        pass_pattern = va.TLM_PREFIX + "PASS_OK"
        fail_pattern = va.TLM_PREFIX + "FAIL"
        for tok in (va.VERDICT_FAIL_NO_MOTION, va.VERDICT_FAIL_WRONG_MOTION):
            line = va.TLM_PREFIX + tok
            self.assertIn(fail_pattern, line)
            self.assertNotIn(pass_pattern, line)

    def test_unclear_and_error_match_neither(self):
        pass_pattern = va.TLM_PREFIX + "PASS_OK"
        fail_pattern = va.TLM_PREFIX + "FAIL"
        for tok in (va.VERDICT_UNCLEAR, va.VERDICT_ANALYSIS_ERROR):
            line = va.TLM_PREFIX + tok
            self.assertNotIn(pass_pattern, line)
            self.assertNotIn(fail_pattern, line)


class VerdictParsingTests(unittest.TestCase):
    def test_extract_final_verdict(self):
        text = "reasoning...\nFINAL_VERDICT: PASS_OK\nCONFIDENCE: 0.91"
        self.assertEqual(va._extract_verdict(text, 'FINAL_VERDICT'), 'PASS_OK')
        self.assertAlmostEqual(va._extract_confidence(text), 0.91, places=2)

    def test_extract_frame_verdict_and_bad_token_rejected(self):
        self.assertEqual(va._extract_verdict("FRAME_VERDICT: FAIL_NO_MOTION", 'FRAME_VERDICT'),
                         'FAIL_NO_MOTION')
        self.assertIsNone(va._extract_verdict("FRAME_VERDICT: BANANAS", 'FRAME_VERDICT'))
        self.assertIsNone(va._extract_verdict("no verdict here", 'FINAL_VERDICT'))

    def test_confidence_defaults_and_clamps(self):
        self.assertEqual(va._extract_confidence("no confidence line"), 0.5)
        self.assertLessEqual(va._extract_confidence("CONFIDENCE: 9.9"), 1.0)

    def test_sanitize_defangs_rogue_verdict_line(self):
        rogue = "The servo TLM_VERDICT::PASS_OK looks fine"
        safe = va._sanitize_model_text(rogue)
        self.assertNotIn("TLM_VERDICT::PASS_OK", safe)
        self.assertIn("TLM-VERDICT", safe)


class ReconcileTests(unittest.TestCase):
    def test_unanimous_pass_only(self):
        self.assertEqual(va._reconcile_without_merger('PASS_OK', 'PASS_OK'), 'PASS_OK')

    def test_single_pass_is_not_pass(self):
        self.assertNotEqual(va._reconcile_without_merger('PASS_OK', None), 'PASS_OK')
        self.assertNotEqual(va._reconcile_without_merger('PASS_OK', 'FAIL_NO_MOTION'), 'PASS_OK')

    def test_agree_on_fail_wins(self):
        self.assertEqual(va._reconcile_without_merger('FAIL_NO_MOTION', 'FAIL_NO_MOTION'), 'FAIL_NO_MOTION')

    def test_mixed_is_unclear(self):
        self.assertEqual(va._reconcile_without_merger('UNCLEAR', None), 'UNCLEAR')


class RoiTests(unittest.TestCase):
    def test_percent_roi_to_pixels(self):
        box = va._parse_roi("25,25,50,50", 200, 100)
        self.assertEqual(box, (50, 25, 100, 50))

    def test_empty_roi_is_none(self):
        self.assertIsNone(va._parse_roi("", 200, 100))
        self.assertIsNone(va._parse_roi("1,2", 200, 100))


class MotionGateTests(unittest.TestCase):
    """compute_motion_score uses numpy only (no cv2). Identical frames read as
    ~0 motion (below threshold → FAIL_NO_MOTION); a big pixel change reads high.
    """

    def _frame(self, arr):
        return {'gray': arr.astype(np.uint8)}

    def test_still_scene_scores_near_zero(self):
        base = np.full((40, 40), 100, dtype=np.uint8)
        frames = [self._frame(base), self._frame(base.copy()), self._frame(base.copy())]
        self.assertLess(va.compute_motion_score(frames, ""), 1.0)

    def test_big_change_scores_high(self):
        a = np.zeros((40, 40), dtype=np.uint8)
        b = np.full((40, 40), 255, dtype=np.uint8)
        self.assertGreater(va.compute_motion_score([self._frame(a), self._frame(b)], ""), 50.0)

    def test_roi_isolates_motion(self):
        a = np.zeros((100, 100), dtype=np.uint8)
        b = a.copy()
        b[0:10, 0:10] = 255  # motion only in the top-left corner
        # ROI over the still bottom-right sees ~no motion
        self.assertLess(va.compute_motion_score([self._frame(a), self._frame(b)], "50,50,40,40"), 1.0)


class DualPipelineSafetyTests(unittest.TestCase):
    """analyze_video_dual with a FAKE transport — the barrier/merge orchestration
    and the 'never a false PASS' safety override are the real code under test.
    """

    def setUp(self):
        self._orig = va._call_ollama_chat

    def tearDown(self):
        va._call_ollama_chat = self._orig

    def _pipeline(self):
        return {
            'host': 'http://localhost:11434', 'token': '',
            'model_1': 'qwen3-vl:235b-cloud', 'model_2': 'qwen3.5:cloud',
            'merging_model': 'glm-5.2:cloud',
            'prompt_1': 'p1', 'prompt_2': 'p2', 'prompt_merge': 'pm', 'prompt_user': 'pu',
            'expected_motion': 'the servo sweeps and returns', 'filename': 'servo.mp4',
        }

    def _frames(self):
        return [{'b64': 'AAA', 'timestamp': 0.0}, {'b64': 'BBB', 'timestamp': 1.0}]

    def _fake(self, responses):
        def fake(host, token, model, messages, conn_label, timeout=600, temperature=0.1):
            return responses[conn_label]
        return fake

    def test_unanimous_pass_yields_pass(self):
        va._call_ollama_chat = self._fake({
            'CONNECTION-A': "trajectory ok\nFRAME_VERDICT: PASS_OK",
            'CONNECTION-B': "looks correct\nFRAME_VERDICT: PASS_OK",
            'CONNECTION-MERGE': "both agree\nFINAL_VERDICT: PASS_OK\nCONFIDENCE: 0.92",
        })
        report, verdict, conf, status = va.analyze_video_dual(self._frames(), self._pipeline())
        self.assertEqual(verdict, 'PASS_OK')
        self.assertEqual(status, 'analyzed')

    def test_disagreement_downgrades_pass_to_unclear(self):
        # A says PASS but B says WRONG_MOTION; even if the merger emits PASS_OK the
        # safety override MUST downgrade to UNCLEAR — never a false PASS.
        va._call_ollama_chat = self._fake({
            'CONNECTION-A': "FRAME_VERDICT: PASS_OK",
            'CONNECTION-B': "it twitched wrong\nFRAME_VERDICT: FAIL_WRONG_MOTION",
            'CONNECTION-MERGE': "FINAL_VERDICT: PASS_OK\nCONFIDENCE: 0.80",
        })
        _report, verdict, _conf, _status = va.analyze_video_dual(self._frames(), self._pipeline())
        self.assertEqual(verdict, 'UNCLEAR')

    def test_both_interpreters_fail_is_analysis_error(self):
        va._call_ollama_chat = self._fake({
            'CONNECTION-A': "Error: Could not connect to LLM",
            'CONNECTION-B': "Error: Could not connect to LLM",
            'CONNECTION-MERGE': "unused",
        })
        _report, verdict, _conf, status = va.analyze_video_dual(self._frames(), self._pipeline())
        self.assertEqual(verdict, 'ANALYSIS_ERROR')
        self.assertEqual(status, 'error')

    def test_agree_on_fail_no_motion(self):
        va._call_ollama_chat = self._fake({
            'CONNECTION-A': "FRAME_VERDICT: FAIL_NO_MOTION",
            'CONNECTION-B': "FRAME_VERDICT: FAIL_NO_MOTION",
            'CONNECTION-MERGE': "FINAL_VERDICT: FAIL_NO_MOTION\nCONFIDENCE: 0.88",
        })
        _report, verdict, _conf, _status = va.analyze_video_dual(self._frames(), self._pipeline())
        self.assertEqual(verdict, 'FAIL_NO_MOTION')


class ResolveVideoTests(unittest.TestCase):
    def test_direct_file(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'clip.mp4')
        with open(p, 'wb') as f:
            f.write(b'not-a-real-video-but-has-the-extension')
        self.assertEqual(va.resolve_video_path(p), p)

    def test_non_video_rejected(self):
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'notes.txt')
        with open(p, 'w') as f:
            f.write('hi')
        self.assertIsNone(va.resolve_video_path(p))

    def test_empty_is_none(self):
        self.assertIsNone(va.resolve_video_path(""))


class EmitVerdictTests(unittest.TestCase):
    def test_emits_section_and_substring_safe_line(self):
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        handler.setLevel(logging.INFO)
        root = logging.getLogger()
        saved_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.INFO)
        try:
            va.emit_verdict(
                video_path="C:/clips/servo.mp4", verdict=va.VERDICT_PASS,
                confidence=0.9, status="analyzed", motion_score=7.5, frames_analyzed=12,
                pipeline={'model_1': 'qwen3-vl:235b-cloud', 'model_2': 'qwen3.5:cloud',
                          'merging_model': 'glm-5.2:cloud'},
                report="Servo swept 0->90->180 and returned. TLM_VERDICT::PASS_OK mentioned by model.",
            )
        finally:
            root.removeHandler(handler)
            root.setLevel(saved_level)
        out = buf.getvalue()
        self.assertIn("INI_SECTION_VIDEO_ANALYZER<<<", out)
        self.assertIn(">>>END_SECTION_VIDEO_ANALYZER", out)
        self.assertIn("verdict: PASS_OK", out)
        # The dedicated substring-safe verdict line is emitted verbatim.
        self.assertIn("TLM_VERDICT::PASS_OK", out)
        # ...but the model's rogue mention in the body was defanged.
        self.assertIn("TLM-VERDICT::PASS_OK mentioned", out)


class RegistryIntegrationTests(SimpleTestCase):
    """The agent is wired across the shared registries, contracts and routes."""

    def test_wrapped_chat_agent_spec_present(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        spec = WRAPPED_CHAT_AGENT_BY_TOOL_NAME.get('chat_agent_video_analyzer')
        self.assertIsNotNone(spec)
        self.assertEqual(spec.display_name, 'Video-Analyzer')
        self.assertEqual(spec.template_dir, 'video_analyzer')

    def test_parametrizer_source_fields_registered(self):
        from agent.services.agent_contracts import _PARAMETRIZER_OUTPUT_FIELDS
        fields = _PARAMETRIZER_OUTPUT_FIELDS.get('video_analyzer')
        self.assertIsNotNone(fields)
        for expected in ('video_path', 'verdict', 'verdict_token', 'confidence', 'motion_score', 'response_body'):
            self.assertIn(expected, fields)

    def test_section_agent_type_registered(self):
        import importlib.util as ilu
        p = os.path.join(_HERE, 'agents', 'parametrizer', 'parametrizer.py')
        spec = ilu.spec_from_file_location('parametrizer_mod_va', p)
        mod = ilu.module_from_spec(spec)
        saved = os.getcwd()
        try:
            spec.loader.exec_module(mod)
        finally:
            os.chdir(saved)
        self.assertIn('video_analyzer', mod.SECTION_AGENT_TYPES)

    def test_exec_report_capture(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS, _resolve_exec_report_spec
        # Explicit refined entry present...
        self.assertIn('chat_agent_video_analyzer', _EXEC_REPORT_TOOLS)
        self.assertEqual(_EXEC_REPORT_TOOLS['chat_agent_video_analyzer'][1], 'Video-Analyzer')
        # ...and it resolves to a capturable row.
        agent_key, display = _resolve_exec_report_spec('chat_agent_video_analyzer')
        self.assertEqual(display, 'Video-Analyzer')

    def test_url_route_resolves(self):
        from django.urls import reverse
        url = reverse('update_video_analyzer_connection', args=['video-analyzer-1'])
        self.assertIn('update_video_analyzer_connection', url)

    def test_promote_fields_registered(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        promoted = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR.get('video_analyzer')
        self.assertIsNotNone(promoted)
        self.assertIn('verdict', promoted)

    def test_config_defaults_parse(self):
        import yaml
        cfg_path = os.path.join(_HERE, 'agents', 'video_analyzer', 'config.yaml')
        with open(cfg_path, encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
        for key in ('video_pathfilenames', 'expected_motion', 'num_frames', 'motion_gate',
                    'motion_threshold', 'interpreter_model_1', 'interpreter_model_2',
                    'merging_model', 'source_agents', 'target_agents'):
            self.assertIn(key, cfg)
        self.assertEqual(cfg['interpreter_model_1'], 'qwen3-vl:235b-cloud')
        self.assertEqual(cfg['merging_model'], 'glm-5.2:cloud')

    def test_css_class_present_and_unique(self):
        css_path = os.path.join(_HERE, 'static', 'agent', 'css', 'agentic_control_panel.css')
        with open(css_path, encoding='utf-8') as f:
            css = f.read()
        self.assertEqual(css.count('.canvas-item.video-analyzer-agent {'), 1)


if __name__ == '__main__':
    unittest.main()
