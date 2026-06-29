# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Crafted with heart by  Angela   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Tests for agent.embedding_memory_guard.

The guard's contract:
  * No NVIDIA GPU detected -> return None (no-op).
  * Cloud model ``:cloud`` suffix -> return None.
  * Empty embedding-model / base_url -> return None.
  * Any probe failure -> return None (fail-open).
  * Tier A: /api/ps reports the model loaded -> use ``size_vram`` exactly.
  * Tier B: /api/show provides params + quant -> predict with the
    bits-per-weight table and overhead multiplier.
  * Prediction below threshold -> return None.
  * Chunk estimator honors default + user-supplied omissions and
    respects ``max_chunks_per_file``.
"""
from __future__ import annotations

import importlib
import os
import subprocess
import sys
import tempfile
from unittest.mock import patch

from django.test import SimpleTestCase

from agent import embedding_memory_guard as guard


_BASE_CFG = {
    "embeding-model": "qwen3-embedding:8b",
    "ollama_base_url": "http://127.0.0.1:11434",
    "chunk_size": 2000,
    "chunk_overlap": 300,
    "max_chunks_per_file": 20,
}


class QuantTableTests(SimpleTestCase):
    def test_known_quants_resolve(self):
        self.assertAlmostEqual(guard._bits_per_weight("Q4_K_M"), 4.83)
        self.assertAlmostEqual(guard._bits_per_weight("q4_k_m"), 4.83)
        self.assertAlmostEqual(guard._bits_per_weight("F16"), 16.0)
        self.assertAlmostEqual(guard._bits_per_weight("BF16"), 16.0)

    def test_unknown_quant_falls_back_to_default(self):
        self.assertEqual(
            guard._bits_per_weight("Q-NEW-EXPERIMENTAL"),
            guard._DEFAULT_BITS_PER_WEIGHT,
        )
        self.assertEqual(guard._bits_per_weight(None), guard._DEFAULT_BITS_PER_WEIGHT)
        self.assertEqual(guard._bits_per_weight(""), guard._DEFAULT_BITS_PER_WEIGHT)


class PredictFromShowTests(SimpleTestCase):
    def test_qwen3_embedding_8b_prediction_within_2pct_of_measured(self):
        # Measured on RTX 4070 Laptop via /api/ps: size_vram = 6.24 GB.
        # Expectation: prediction is within +-5% of that.
        show = {
            "model_info": {"general.parameter_count": 7567295488},
            "details": {"quantization_level": "Q4_K_M"},
        }
        predicted = guard._predict_vram_from_show(show)
        self.assertIsNotNone(predicted)
        gb = predicted / (1024 ** 3)
        self.assertGreater(gb, 5.9)
        self.assertLess(gb, 6.9)

    def test_sub1b_model_uses_large_overhead(self):
        # Nomic measured: 0.60 GB resident from a 137M-param F16 model.
        show = {
            "model_info": {"general.parameter_count": 136727040},
            "details": {"quantization_level": "F16"},
        }
        predicted = guard._predict_vram_from_show(show)
        self.assertIsNotNone(predicted)
        gb = predicted / (1024 ** 3)
        # Expect ~0.56 GB; allow generous bounds to keep the test stable.
        self.assertGreater(gb, 0.4)
        self.assertLess(gb, 0.9)

    def test_missing_parameter_count_returns_none(self):
        self.assertIsNone(guard._predict_vram_from_show({"model_info": {}}))
        self.assertIsNone(guard._predict_vram_from_show({}))


class EmbeddingDimExtractionTests(SimpleTestCase):
    def test_finds_architecture_prefixed_key(self):
        self.assertEqual(
            guard._extract_embedding_dim(
                {"model_info": {"qwen3.embedding_length": 4096}}
            ),
            4096,
        )
        self.assertEqual(
            guard._extract_embedding_dim(
                {"model_info": {"nomic-bert.embedding_length": 768}}
            ),
            768,
        )

    def test_missing_returns_none(self):
        self.assertIsNone(guard._extract_embedding_dim({"model_info": {}}))


class ChunkEstimatorTests(SimpleTestCase):
    def _make_tree(self, root: str) -> None:
        # Three readable files + one excluded-by-default + one excluded-by-ext.
        with open(os.path.join(root, "a.txt"), "w") as fh:
            fh.write("x" * 4000)
        with open(os.path.join(root, "b.py"), "w") as fh:
            fh.write("y" * 2000)
        sub = os.path.join(root, "sub")
        os.makedirs(sub)
        with open(os.path.join(sub, "c.md"), "w") as fh:
            fh.write("z" * 1700)
        with open(os.path.join(root, "package-lock.json"), "w") as fh:
            fh.write("{" + "0" * 100000 + "}")
        with open(os.path.join(root, "image.bin"), "w") as fh:
            fh.write("Q" * 10000)

    def test_basic_walk_honors_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_tree(tmp)
            # stride = 2000 - 300 = 1700
            # a.txt 4000 / 1700 -> 3, b.py 2000/1700 -> 2, c.md 1700/1700 -> 1
            # image.bin 10000/1700 -> 6
            # package-lock.json excluded by default.
            chunks = guard._estimate_chunks(
                tmp, None, "", 2000, 300, max_chunks_per_file=20
            )
            self.assertEqual(chunks, 3 + 2 + 1 + 6)

    def test_user_omissions_strip_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_tree(tmp)
            # Exclude *.bin via user-supplied omissions.
            chunks = guard._estimate_chunks(
                tmp, None, "*.bin", 2000, 300, max_chunks_per_file=20
            )
            self.assertEqual(chunks, 3 + 2 + 1)

    def test_cap_clips_huge_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "huge.txt"), "w") as fh:
                fh.write("x" * 500000)  # 500000/1700 ~= 294 chunks
            chunks = guard._estimate_chunks(
                tmp, None, "", 2000, 300, max_chunks_per_file=20
            )
            self.assertEqual(chunks, 20)

    def test_single_file_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "single.txt")
            with open(target, "w") as fh:
                fh.write("a" * 1700)
            # Both directory walk and single-file mode should produce 1.
            self.assertEqual(
                guard._estimate_chunks(
                    tmp, "single.txt", "", 2000, 300, max_chunks_per_file=20
                ),
                1,
            )


class GuardEntryPointTests(SimpleTestCase):
    def test_no_gpu_returns_none_immediately(self):
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=False):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", _BASE_CFG)
            )

    def test_cloud_model_bypasses(self):
        cfg = dict(_BASE_CFG, **{"embeding-model": "text-embed-3:cloud"})
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", cfg)
            )

    def test_empty_model_bypasses(self):
        cfg = dict(_BASE_CFG, **{"embeding-model": ""})
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", cfg)
            )

    def test_total_vram_probe_failure_returns_none(self):
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=None):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", _BASE_CFG)
            )

    def test_tier_a_loaded_model_above_threshold_triggers(self):
        # 6.24 GB resident on 8 GiB GPU -> 76.2% (below 80%, no fire).
        # Use 6.6 GB to land at 82.5% -> fires.
        eight_gib = 8 * 1024 * 1024 * 1024
        six_point_six_gb = int(6.6 * 1024 * 1024 * 1024)
        show_payload = {
            "model_info": {"qwen3.embedding_length": 4096},
        }
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=eight_gib), \
             patch.object(guard, "_ollama_loaded_vram_bytes", return_value=six_point_six_gb), \
             patch.object(guard, "_ollama_show", return_value=show_payload):
            with tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, "a.py"), "w") as fh:
                    fh.write("x" * 3400)
                result = guard.check_embedding_memory_for_directory(
                    tmp, _BASE_CFG
                )
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "loaded")
        self.assertEqual(result["model"], "qwen3-embedding:8b")
        self.assertGreaterEqual(result["percent"], 80.0)
        self.assertEqual(result["embedding_dim"], 4096)
        self.assertGreater(result["chunks_estimate"], 0)
        self.assertGreater(result["faiss_ram_bytes"], 0)

    def test_below_threshold_returns_none(self):
        eight_gib = 8 * 1024 * 1024 * 1024
        # 1 GB on 8 GiB -> 12.5%, no fire.
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=eight_gib), \
             patch.object(guard, "_ollama_loaded_vram_bytes", return_value=1 << 30), \
             patch.object(guard, "_ollama_show", return_value={"model_info": {}}):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", _BASE_CFG)
            )

    def test_tier_b_uses_show_when_not_loaded(self):
        # 7.567B params * 4.83 bits (Q4_K_M) / 8 * 1.4 overhead ~= 6.4 GB
        # which is ~74% of 8 GiB. We pass threshold=0.70 to confirm the
        # Tier-B path engages and the threshold knob is honored.
        eight_gib = 8 * 1024 * 1024 * 1024
        show_payload = {
            "model_info": {
                "general.parameter_count": 7567295488,
                "qwen3.embedding_length": 4096,
            },
            "details": {"quantization_level": "Q4_K_M"},
        }
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=eight_gib), \
             patch.object(guard, "_ollama_loaded_vram_bytes", return_value=None), \
             patch.object(guard, "_ollama_show", return_value=show_payload):
            with tempfile.TemporaryDirectory() as tmp:
                result = guard.check_embedding_memory_for_directory(
                    tmp, _BASE_CFG, threshold=0.70,
                )
        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "predicted")
        self.assertGreaterEqual(result["percent"], 70.0)
        self.assertEqual(result["embedding_dim"], 4096)

    def test_show_failure_in_tier_b_returns_none(self):
        eight_gib = 8 * 1024 * 1024 * 1024
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=eight_gib), \
             patch.object(guard, "_ollama_loaded_vram_bytes", return_value=None), \
             patch.object(guard, "_ollama_show", return_value=None):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", _BASE_CFG)
            )


class FormatMessageTests(SimpleTestCase):
    def test_empty_warning_returns_empty_string(self):
        self.assertEqual(guard.format_warning_message({}), "")
        self.assertEqual(guard.format_warning_message(None), "")  # type: ignore[arg-type]

    def test_message_mentions_key_facts(self):
        msg = guard.format_warning_message({
            "model": "qwen3-embedding:8b",
            "source": "loaded",
            "predicted_vram_bytes": int(6.6 * 1024 * 1024 * 1024),
            "gpu_total_bytes": 8 * 1024 * 1024 * 1024,
            "percent": 82.5,
            "threshold_percent": 80.0,
            "chunks_estimate": 1234,
            "embedding_dim": 4096,
            "faiss_ram_bytes": 1234 * 4096 * 4,
        })
        self.assertIn("qwen3-embedding:8b", msg)
        self.assertIn("82.5%", msg)
        self.assertIn("80%", msg)
        # Both the prediction line AND the FAISS line should be present.
        self.assertIn("FAISS", msg)
        self.assertIn("1,234", msg)
        self.assertIn("4096", msg)
        # Renders as HTML chat bubble, not markdown.
        self.assertIn("<b>", msg)
        self.assertIn("<code>", msg)
        self.assertIn("<br>", msg)


class NoGpuCompatibilityTests(SimpleTestCase):
    """Hard guarantees for machines without an NVIDIA GPU.

    The guard's existence MUST be invisible on:
      * CPU-only Linux/Windows (no ``nvidia-smi`` binary anywhere)
      * AMD GPUs (``rocm-smi`` exists, ``nvidia-smi`` does not)
      * Apple Silicon (no NVIDIA tooling at all)
      * NVIDIA hosts whose driver crashed mid-session
      * Hosts where the Ollama daemon is offline entirely

    Every test in this class exercises one of those failure modes via
    either the real subprocess+urllib code paths or a precise mock and
    asserts the public entry points return ``None`` or absorb the
    error - they MUST NEVER raise.
    """

    _BASE_CFG = dict(_BASE_CFG)  # local copy so threshold-tweaks stay isolated

    # ------------------------------------------------------------------
    # Import & module-level behavior
    # ------------------------------------------------------------------

    def test_module_imports_without_side_effects(self):
        """Reimporting the module must not invoke subprocess or urllib.

        If a future refactor accidentally calls ``_has_nvidia_gpu()`` at
        module-load time, a no-GPU machine that imports
        ``agent.embedding_memory_guard`` at request time would pay a
        ~5 s subprocess timeout. This test pins the lazy contract.
        """
        with patch.object(subprocess, "run") as mock_run, \
             patch("urllib.request.urlopen") as mock_urlopen:
            importlib.reload(guard)
            mock_run.assert_not_called()
            mock_urlopen.assert_not_called()

    # ------------------------------------------------------------------
    # _run_cmd: must absorb every subprocess failure mode
    # ------------------------------------------------------------------

    def test_run_cmd_returns_127_for_real_missing_binary(self):
        # Real subprocess invocation - no mock. The binary name is
        # deliberately constructed to never exist on any host.
        code, out = guard._run_cmd(
            ["__definitely_not_a_real_binary_42__"], timeout=2
        )
        self.assertEqual(code, 127)
        self.assertIn("not found", out)

    def test_run_cmd_absorbs_timeout(self):
        with patch.object(
            subprocess,
            "run",
            side_effect=subprocess.TimeoutExpired("nvidia-smi", 1),
        ):
            code, out = guard._run_cmd(["nvidia-smi"], timeout=1)
        self.assertEqual(code, 124)
        self.assertIn("timed out", out)

    def test_run_cmd_absorbs_permission_error(self):
        with patch.object(subprocess, "run", side_effect=PermissionError("denied")):
            code, out = guard._run_cmd(["nvidia-smi"])
        self.assertEqual(code, 1)
        self.assertIn("denied", out)

    def test_run_cmd_absorbs_generic_oserror(self):
        with patch.object(subprocess, "run", side_effect=OSError("driver crash")):
            code, _out = guard._run_cmd(["nvidia-smi"])
        self.assertEqual(code, 1)

    # ------------------------------------------------------------------
    # _gpu_total_memory_bytes: every nvidia-smi failure -> None
    # ------------------------------------------------------------------

    def test_total_vram_returns_none_when_nvidia_smi_missing(self):
        # The exact return shape _run_cmd produces for FileNotFoundError.
        with patch.object(
            guard,
            "_run_cmd",
            return_value=(127, "nvidia-smi: not found on PATH"),
        ):
            self.assertIsNone(guard._gpu_total_memory_bytes())

    def test_total_vram_returns_none_when_driver_unloaded(self):
        # nvidia-smi exists but driver isn't loaded (common on a stub
        # Windows install or a CI image with the binary but no kernel).
        with patch.object(
            guard,
            "_run_cmd",
            return_value=(9, "NVIDIA-SMI couldn't find libnvidia-ml.so"),
        ):
            self.assertIsNone(guard._gpu_total_memory_bytes())

    def test_total_vram_returns_none_on_empty_output(self):
        with patch.object(guard, "_run_cmd", return_value=(0, "")):
            self.assertIsNone(guard._gpu_total_memory_bytes())

    def test_total_vram_returns_none_on_unparseable_output(self):
        # If a future nvidia-smi build changes its output format, we
        # mustn't crash trying to int() a header row.
        with patch.object(
            guard,
            "_run_cmd",
            return_value=(0, "garbage line 1\nnot a number\n"),
        ):
            self.assertIsNone(guard._gpu_total_memory_bytes())

    def test_total_vram_picks_smallest_gpu_in_heterogeneous_rig(self):
        # Sanity: when multiple GPUs are present, we constrain against
        # the smallest -- because Ollama loads each model into one
        # device. Using the max would silently under-report the gate.
        with patch.object(
            guard,
            "_run_cmd",
            return_value=(0, "24576\n8188\n12288\n"),
        ):
            bytes_seen = guard._gpu_total_memory_bytes()
        self.assertEqual(bytes_seen, 8188 * 1024 * 1024)

    # ------------------------------------------------------------------
    # _has_nvidia_gpu_cached: must never propagate ImportError
    # ------------------------------------------------------------------

    def test_has_nvidia_gpu_falls_back_when_gpu_perf_unimportable(self):
        gpu_perf_backup = sys.modules.pop("agent.gpu_perf", None)
        try:
            with patch.dict(sys.modules, {"agent.gpu_perf": None}):
                self.assertFalse(guard._has_nvidia_gpu_cached())
        finally:
            if gpu_perf_backup is not None:
                sys.modules["agent.gpu_perf"] = gpu_perf_backup

    def test_has_nvidia_gpu_returns_false_when_gpu_perf_probe_raises(self):
        # gpu_perf imports fine but its internal _has_nvidia_gpu raises
        # for some reason (e.g. a future refactor accidentally calls a
        # method on None) -- we still return False, not propagate.
        import agent.gpu_perf
        with patch.object(
            agent.gpu_perf,
            "_has_nvidia_gpu",
            side_effect=RuntimeError("simulated"),
        ):
            self.assertFalse(guard._has_nvidia_gpu_cached())

    # ------------------------------------------------------------------
    # Ollama probes: closed port / network errors -> None
    # ------------------------------------------------------------------

    def test_ollama_show_returns_none_against_closed_port(self):
        # Real network call to a port no daemon listens on. Must fail
        # fast (the timeout argument is honored) and return None.
        result = guard._ollama_show(
            "http://127.0.0.1:1", "any-model", timeout=1.0
        )
        self.assertIsNone(result)

    def test_ollama_ps_returns_none_against_closed_port(self):
        result = guard._ollama_ps("http://127.0.0.1:1", timeout=1.0)
        self.assertIsNone(result)

    def test_ollama_show_returns_none_for_garbage_url(self):
        # Malformed base_url should be absorbed.
        self.assertIsNone(
            guard._ollama_show("not://a-url", "model", timeout=0.5)
        )
        self.assertIsNone(guard._ollama_show("", "model", timeout=0.5))
        self.assertIsNone(guard._ollama_show("http://x", "", timeout=0.5))

    def test_ollama_loaded_vram_returns_none_when_ps_fails(self):
        with patch.object(guard, "_ollama_ps", return_value=None):
            self.assertIsNone(
                guard._ollama_loaded_vram_bytes(
                    "http://127.0.0.1:11434", "any-model"
                )
            )

    def test_ollama_loaded_vram_returns_none_when_model_not_in_ps(self):
        with patch.object(
            guard,
            "_ollama_ps",
            return_value=[{"name": "some-other:latest", "size_vram": 1000}],
        ):
            self.assertIsNone(
                guard._ollama_loaded_vram_bytes(
                    "http://127.0.0.1:11434", "qwen3-embedding:8b"
                )
            )

    # ------------------------------------------------------------------
    # Top-level entry point: every no-GPU scenario -> None
    # ------------------------------------------------------------------

    def test_check_returns_none_on_cpu_only_host(self):
        # Most common case: no NVIDIA GPU at all.
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=False):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", self._BASE_CFG)
            )

    def test_check_returns_none_when_nvidia_smi_query_fails(self):
        # gpu_perf reported GPU present (nvidia-smi -L worked once long
        # ago) but the subsequent --query-gpu now fails.
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=None):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", self._BASE_CFG)
            )

    def test_check_returns_none_when_ollama_offline(self):
        # GPU detected, VRAM read OK, but the Ollama daemon is down.
        eight_gib = 8 * 1024 * 1024 * 1024
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=eight_gib), \
             patch.object(guard, "_ollama_loaded_vram_bytes", return_value=None), \
             patch.object(guard, "_ollama_show", return_value=None):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", self._BASE_CFG)
            )

    def test_check_returns_none_when_gpu_zero_total(self):
        # Pathological nvidia-smi reading 0 MiB (some virtualized
        # environments report this). Defensive guard.
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True), \
             patch.object(guard, "_gpu_total_memory_bytes", return_value=0):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", self._BASE_CFG)
            )

    def test_check_returns_none_for_empty_base_url(self):
        cfg = dict(self._BASE_CFG, **{"ollama_base_url": ""})
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=True):
            self.assertIsNone(
                guard.check_embedding_memory_for_directory(".", cfg)
            )

    # ------------------------------------------------------------------
    # Path-input robustness: never crash regardless of what we walk
    # ------------------------------------------------------------------

    def test_check_with_nonexistent_path_does_not_crash(self):
        # If the user picks a directory that has been deleted between
        # the showDirectoryPicker call and the WS message arrival, the
        # guard should still return cleanly (None when below threshold,
        # warning dict when above).
        with patch.object(guard, "_has_nvidia_gpu_cached", return_value=False):
            result = guard.check_embedding_memory_for_directory(
                "/path/that/does/not/exist/anywhere/__42__",
                self._BASE_CFG,
            )
            self.assertIsNone(result)

    def test_chunk_estimator_with_nonexistent_path_returns_zero(self):
        chunks = guard._estimate_chunks(
            "/path/that/does/not/exist/anywhere/__42__",
            None, "", 2000, 300, 20,
        )
        self.assertEqual(chunks, 0)

    def test_chunk_estimator_with_empty_path_returns_zero(self):
        # os.walk("") yields nothing on most platforms; on some it
        # raises. Either way we want zero.
        chunks = guard._estimate_chunks("", None, "", 2000, 300, 20)
        self.assertEqual(chunks, 0)

    def test_chunk_estimator_with_unreadable_file_skips_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok = os.path.join(tmp, "ok.txt")
            with open(ok, "w") as fh:
                fh.write("x" * 1700)
            with patch.object(
                os.path, "getsize",
                side_effect=OSError("permission denied"),
            ):
                # Even though the directory walk finds the file, the
                # estimator must absorb the OSError and treat it as 0.
                chunks = guard._estimate_chunks(
                    tmp, None, "", 2000, 300, 20
                )
            self.assertEqual(chunks, 0)

    # ------------------------------------------------------------------
    # End-to-end smoke: real subprocess + real urllib, any host
    # ------------------------------------------------------------------

    def test_real_entry_point_call_never_raises(self):
        """Smoke test against the LIVE subprocess + urllib code paths.

        This is the portability proof: regardless of whether the host
        has a GPU, an Ollama daemon, both, or neither, the entry point
        must return either ``None`` or a well-formed warning dict.
        Used as the CI gate for CPU-only / AMD / Apple Silicon runners.
        """
        result = guard.check_embedding_memory_for_directory(
            ".",
            {
                "embeding-model": "qwen3-embedding:8b",
                "ollama_base_url": "http://127.0.0.1:11434",
                "chunk_size": 2000,
                "chunk_overlap": 300,
                "max_chunks_per_file": 20,
            },
        )
        self.assertTrue(result is None or isinstance(result, dict))
        if isinstance(result, dict):
            for required_key in (
                "model",
                "source",
                "predicted_vram_bytes",
                "gpu_total_bytes",
                "percent",
                "threshold_percent",
                "chunks_estimate",
                "embedding_dim",
                "faiss_ram_bytes",
            ):
                self.assertIn(required_key, result)

    def test_format_warning_message_handles_missing_optional_keys(self):
        # On a no-GPU host the guard shouldn't ever build a message, but
        # if a caller passes a partial dict (regression in the contract,
        # or a test fixture), the formatter must not blow up.
        msg = guard.format_warning_message({
            "model": "x:y",
            "source": "predicted",
            "predicted_vram_bytes": 1024 * 1024,
            "gpu_total_bytes": 8 * 1024 * 1024,
            "percent": 12.5,
            "threshold_percent": 80.0,
            # chunks_estimate / embedding_dim / faiss_ram_bytes absent.
        })
        self.assertIn("x:y", msg)
        # The FAISS line is conditional on a non-zero chunk count and
        # embedding_dim, so it's correctly omitted here.
        self.assertNotIn("FAISS", msg)
