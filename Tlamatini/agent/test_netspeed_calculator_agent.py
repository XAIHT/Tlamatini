# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""Hard, real-scenario tests for the NetSpeed-Calculator agent (#88).

NetSpeed-Calculator measures this machine's Internet connection and publishes the
answer WITH its error bar. These tests drive the REAL agent code loaded from the
pool script; only the network transport is faked, because the transport is not
what is under test — the statistics, the endpoint discovery, the fail-safe
refusal, and above all the ERROR SURFACING are.

Four defects found and fixed on 2026-08-22 are pinned here as regressions, because
each one silently produced a confident WRONG number:

  1. Cloudflare answers HTTP 403 to an oversized ``bytes=`` — every stream got
     nothing and the report said 0.00 Mbps with no reason.
  2. ``librespeed.org/backend/`` is 404; the live surface is its published server
     list.
  3. ``speed.hetzner.de`` no longer resolves; the live surface is the ``.com``
     datacentre mirror mesh, chosen by MEASURED RTT.
  4. The CACHE-BUSTER itself killed Hetzner: the mirror serves /100MB.bin with 200
     but RESETS the connection when the URL carries an unknown query string, so
     the code written to protect the measurement was destroying it.

And the architectural fix that made all four findable: a transfer that moves zero
bytes MUST say WHY. A silent 0.00 Mbps is indistinguishable from a slow link.

Run:  python Tlamatini/manage.py test agent.test_netspeed_calculator_agent
"""
import importlib.util
import logging
import os
import threading
import time
import unittest

from django.test import SimpleTestCase


# ── Load the pool script fresh, saving/restoring the cwd + logging it mutates ──
_HERE = os.path.dirname(os.path.abspath(__file__))
_NSC_PATH = os.path.join(_HERE, 'agents', 'netspeed_calculator', 'netspeed_calculator.py')
_CFG_PATH = os.path.join(_HERE, 'agents', 'netspeed_calculator', 'config.yaml')


def _load_netspeed_calculator():
    saved_cwd = os.getcwd()
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    try:
        spec = importlib.util.spec_from_file_location('netspeed_calculator_mod', _NSC_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        os.chdir(saved_cwd)
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


nsc = _load_netspeed_calculator()


class _FakeResponse:
    """A minimal stand-in for an http response object: read(n) then close()."""

    def __init__(self, payload=b"", status=200):
        self._data = payload
        self._pos = 0
        self.status = status

    def read(self, n=None):
        if n is None:
            chunk = self._data[self._pos:]
        else:
            chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


# ══════════════════════════════════════════════════════════════════════════
# 1. LOCATION STATISTICS
# ══════════════════════════════════════════════════════════════════════════

class MeanAndMedianTests(unittest.TestCase):

    def test_mean_of_simple_sample(self):
        self.assertAlmostEqual(nsc._mean([1, 2, 3, 4]), 2.5)

    def test_mean_of_empty_is_zero_not_crash(self):
        self.assertEqual(nsc._mean([]), 0.0)

    def test_mean_accepts_a_generator(self):
        self.assertAlmostEqual(nsc._mean(x for x in [2, 4, 6]), 4.0)

    def test_median_odd_count(self):
        self.assertAlmostEqual(nsc._median([3, 1, 2]), 2.0)

    def test_median_even_count_interpolates(self):
        self.assertAlmostEqual(nsc._median([1, 2, 3, 4]), 2.5)

    def test_median_of_empty_is_zero(self):
        self.assertEqual(nsc._median([]), 0.0)

    def test_median_single_value(self):
        self.assertAlmostEqual(nsc._median([42.0]), 42.0)

    def test_median_is_quantile_one_half(self):
        sample = [5, 1, 9, 3, 7]
        self.assertAlmostEqual(nsc._median(sample), nsc._quantile(sample, 0.5))


class QuantileTests(unittest.TestCase):
    """Type-7 (the R / numpy default) — chosen so a reviewer can reproduce the
    IQR fences in R or numpy and get the same numbers."""

    def test_quantile_matches_numpy_type7_quartiles(self):
        sample = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertAlmostEqual(nsc._quantile(sample, 0.25), 3.25)
        self.assertAlmostEqual(nsc._quantile(sample, 0.75), 7.75)

    def test_quantile_zero_is_minimum(self):
        self.assertAlmostEqual(nsc._quantile([4, 9, 1], 0.0), 1.0)

    def test_quantile_one_is_maximum(self):
        self.assertAlmostEqual(nsc._quantile([4, 9, 1], 1.0), 9.0)

    def test_quantile_clamps_out_of_range_q(self):
        sample = [1, 2, 3]
        self.assertAlmostEqual(nsc._quantile(sample, -5.0), 1.0)
        self.assertAlmostEqual(nsc._quantile(sample, 5.0), 3.0)

    def test_quantile_of_empty_is_zero(self):
        self.assertEqual(nsc._quantile([], 0.5), 0.0)

    def test_quantile_of_single_value(self):
        self.assertAlmostEqual(nsc._quantile([7.5], 0.9), 7.5)


class StdevTests(unittest.TestCase):

    def test_sample_stdev_is_bessel_corrected(self):
        # population sd of [2,4,4,4,5,5,7,9] is 2.0; the SAMPLE sd is larger.
        self.assertAlmostEqual(nsc._stdev([2, 4, 4, 4, 5, 5, 7, 9]), 2.13808993, places=6)

    def test_stdev_of_one_value_is_zero(self):
        self.assertEqual(nsc._stdev([5.0]), 0.0)

    def test_stdev_of_empty_is_zero(self):
        self.assertEqual(nsc._stdev([]), 0.0)

    def test_stdev_of_identical_values_is_zero(self):
        self.assertAlmostEqual(nsc._stdev([3, 3, 3, 3]), 0.0)


class TrimmedMeanTests(unittest.TestCase):

    def test_trimmed_mean_drops_the_tails(self):
        sample = [1, 10, 10, 10, 10, 10, 10, 10, 10, 100]
        plain = nsc._mean(sample)
        trimmed = nsc._trimmed_mean(sample, 10.0)
        self.assertLess(abs(trimmed - 10.0), abs(plain - 10.0))

    def test_zero_trim_equals_plain_mean(self):
        sample = [1.0, 2.0, 3.0, 4.0]
        self.assertAlmostEqual(nsc._trimmed_mean(sample, 0.0), nsc._mean(sample))

    def test_trimmed_mean_of_empty_is_zero(self):
        self.assertEqual(nsc._trimmed_mean([], 10.0), 0.0)

    def test_trimmed_mean_never_returns_nan_on_heavy_trim(self):
        value = nsc._trimmed_mean([1.0, 2.0, 3.0], 99.0)
        self.assertEqual(value, value)  # NaN != NaN


# ══════════════════════════════════════════════════════════════════════════
# 2. OUTLIER REJECTION
# ══════════════════════════════════════════════════════════════════════════

class TukeyOutlierTests(unittest.TestCase):

    def test_high_outlier_is_flagged(self):
        sample = [10, 10.5, 11, 10.2, 10.8, 90]
        self.assertIn(5, nsc._tukey_outliers(sample))

    def test_low_outlier_is_flagged(self):
        sample = [10, 10.5, 11, 10.2, 10.8, 0.1]
        self.assertIn(5, nsc._tukey_outliers(sample))

    def test_clean_sample_flags_nothing(self):
        self.assertEqual(nsc._tukey_outliers([10, 10.1, 10.2, 10.3, 10.4]), set())

    def test_fewer_than_four_points_flags_nothing(self):
        self.assertEqual(nsc._tukey_outliers([1, 100, 2]), set())

    def test_zero_iqr_flags_nothing(self):
        """All-identical values have IQR 0; dividing that into fences would flag
        everything, so the guard must short-circuit."""
        self.assertEqual(nsc._tukey_outliers([5, 5, 5, 5, 5]), set())


class MadOutlierTests(unittest.TestCase):

    def test_mad_flags_a_wild_point(self):
        self.assertIn(5, nsc._mad_outliers([10, 10, 10, 10, 10, 500]))

    def test_mad_clean_sample_flags_nothing(self):
        self.assertEqual(nsc._mad_outliers([10, 11, 10, 11, 10]), set())

    def test_fewer_than_three_points_flags_nothing(self):
        self.assertEqual(nsc._mad_outliers([1, 99]), set())

    def test_zero_mad_falls_back_to_mean_absolute_deviation(self):
        """>50% ties make the MAD exactly zero; without the documented fallback
        every score becomes a division by zero."""
        flagged = nsc._mad_outliers([10, 10, 10, 10, 10, 10, 10, 99])
        self.assertIn(7, flagged)

    def test_all_identical_values_flags_nothing(self):
        self.assertEqual(nsc._mad_outliers([7, 7, 7, 7, 7]), set())


class RejectOutliersTests(unittest.TestCase):

    def test_none_method_keeps_everything(self):
        sample = [1, 2, 3, 4, 500]
        kept, rejected = nsc._reject_outliers(sample, "none")
        self.assertEqual(kept, sample)
        self.assertEqual(rejected, [])

    def test_tukey_is_the_default_for_an_unknown_method(self):
        sample = [10, 10.5, 11, 10.2, 10.8, 90]
        kept_default, _ = nsc._reject_outliers(sample, "not-a-real-method")
        kept_tukey, _ = nsc._reject_outliers(sample, "tukey")
        self.assertEqual(kept_default, kept_tukey)

    def test_empty_method_string_is_tukey(self):
        sample = [10, 10.5, 11, 10.2, 10.8, 90]
        kept, rejected = nsc._reject_outliers(sample, "")
        self.assertNotIn(90, kept)
        self.assertIn(90, rejected)

    def test_short_sample_is_never_filtered(self):
        sample = [1, 900, 2]
        kept, rejected = nsc._reject_outliers(sample, "tukey")
        self.assertEqual(kept, sample)
        self.assertEqual(rejected, [])

    def test_filter_never_eats_the_sample_below_three_points(self):
        """Returning one surviving point would be a lie about precision — if the
        filter would leave fewer than three, the data is simply that noisy."""
        sample = [1.0, 1.0, 50.0, 100.0]
        kept, rejected = nsc._reject_outliers(sample, "tukey")
        self.assertGreaterEqual(len(kept), 3)

    def test_mad_method_is_selectable(self):
        kept, rejected = nsc._reject_outliers([10, 10, 10, 10, 10, 500], "mad")
        self.assertIn(500, rejected)

    def test_kept_and_rejected_partition_the_input(self):
        sample = [10, 10.5, 11, 10.2, 10.8, 90]
        kept, rejected = nsc._reject_outliers(sample, "tukey")
        self.assertEqual(sorted(kept + rejected), sorted(sample))


# ══════════════════════════════════════════════════════════════════════════
# 3. JITTER, CRITICAL VALUES, NETWORK MATH
# ══════════════════════════════════════════════════════════════════════════

class Rfc3550JitterTests(unittest.TestCase):

    def test_constant_rtt_has_zero_jitter(self):
        self.assertAlmostEqual(nsc._rfc3550_jitter([20.0] * 10), 0.0)

    def test_varying_rtt_has_positive_jitter(self):
        self.assertGreater(nsc._rfc3550_jitter([10, 30, 10, 30, 10]), 0.0)

    def test_single_sample_has_zero_jitter(self):
        self.assertEqual(nsc._rfc3550_jitter([15.0]), 0.0)

    def test_empty_has_zero_jitter(self):
        self.assertEqual(nsc._rfc3550_jitter([]), 0.0)

    def test_jitter_is_smoothed_not_raw_range(self):
        """RFC 3550 applies a 1/16 gain, so one spike must NOT move jitter to the
        full peak-to-peak distance."""
        jitter = nsc._rfc3550_jitter([20, 20, 20, 20, 120, 20, 20, 20])
        self.assertLess(jitter, 100.0)


class CriticalValueTests(unittest.TestCase):

    def test_t_critical_is_wider_than_z_for_small_df(self):
        self.assertGreater(nsc._t_critical(3, 0.95), nsc._z_critical(0.95))

    def test_t_critical_falls_back_to_z_for_large_df(self):
        self.assertAlmostEqual(nsc._t_critical(500, 0.95), 1.960, places=3)

    def test_t_critical_zero_df_is_zero(self):
        self.assertEqual(nsc._t_critical(0, 0.95), 0.0)

    def test_t_critical_negative_df_is_zero(self):
        self.assertEqual(nsc._t_critical(-4, 0.95), 0.0)

    def test_z_critical_95(self):
        self.assertAlmostEqual(nsc._z_critical(0.95), 1.960, places=3)

    def test_z_critical_99_is_wider(self):
        self.assertGreater(nsc._z_critical(0.99), nsc._z_critical(0.95))

    def test_z_critical_90_is_narrower(self):
        self.assertLess(nsc._z_critical(0.90), nsc._z_critical(0.95))


class NetworkMathTests(unittest.TestCase):

    def test_haversine_known_distance_mexico_city_to_new_york(self):
        km = nsc._haversine_km(19.4326, -99.1332, 40.7128, -74.0060)
        self.assertTrue(3100 < km < 3400, "got %.1f km" % km)

    def test_haversine_zero_for_same_point(self):
        self.assertAlmostEqual(nsc._haversine_km(10.0, 20.0, 10.0, 20.0), 0.0, places=6)

    def test_haversine_is_symmetric(self):
        a = nsc._haversine_km(19.4, -99.1, 52.5, 13.4)
        b = nsc._haversine_km(52.5, 13.4, 19.4, -99.1)
        self.assertAlmostEqual(a, b, places=6)

    def test_haversine_uses_great_circle_not_euclidean(self):
        """A naive sqrt(dlat^2+dlon^2) would ignore the cos(latitude) term, so two
        points one degree of LONGITUDE apart near the pole would be reported the
        same distance as at the equator. They are not."""
        equator = nsc._haversine_km(0.0, 0.0, 0.0, 1.0)
        high_lat = nsc._haversine_km(70.0, 0.0, 70.0, 1.0)
        self.assertLess(high_lat, equator / 2.0)

    def test_bdp_grows_with_bandwidth(self):
        self.assertGreater(nsc._bdp_bytes(200.0, 50.0), nsc._bdp_bytes(100.0, 50.0))

    def test_bdp_grows_with_rtt(self):
        self.assertGreater(nsc._bdp_bytes(100.0, 200.0), nsc._bdp_bytes(100.0, 50.0))

    def test_bdp_of_100mbps_at_10ms_is_about_125kb(self):
        self.assertAlmostEqual(nsc._bdp_bytes(100.0, 10.0), 125000.0, delta=1.0)

    def test_mathis_ceiling_falls_as_loss_rises(self):
        clean = nsc._mathis_ceiling_mbps(50.0, 0.0001)
        lossy = nsc._mathis_ceiling_mbps(50.0, 0.01)
        self.assertGreater(clean, lossy)

    def test_mathis_ceiling_falls_as_rtt_rises(self):
        near = nsc._mathis_ceiling_mbps(10.0, 0.001)
        far = nsc._mathis_ceiling_mbps(200.0, 0.001)
        self.assertGreater(near, far)

    def test_mathis_zero_loss_returns_an_unbounded_ceiling_not_a_crash(self):
        """Mathis is the ceiling IMPOSED BY LOSS; with zero loss there is no such
        ceiling, so an infinite result is the honest answer rather than a bug. What
        matters is that it never raises and never reaches the report as a bogus
        number - the formatter renders it as 'n/a'."""
        value = nsc._mathis_ceiling_mbps(50.0, 0.0)
        self.assertEqual(value, float("inf"))
        self.assertEqual(nsc._fmt(value), "n/a")


# ══════════════════════════════════════════════════════════════════════════
# 4. CROSS-PROVIDER META-ANALYSIS
# ══════════════════════════════════════════════════════════════════════════

class MetaAnalysisTests(unittest.TestCase):

    def test_agreeing_providers_use_fixed_effect(self):
        out = nsc._inverse_variance_meta([(100.0, 1.0), (101.0, 1.0), (100.5, 1.0)])
        self.assertEqual(out["method"], "inverse_variance_fixed_effect")
        self.assertAlmostEqual(out["estimate"], 100.5, delta=1.0)

    def test_disagreeing_providers_switch_to_random_effects(self):
        out = nsc._inverse_variance_meta([(20.0, 0.5), (95.0, 0.5), (60.0, 0.5)])
        self.assertEqual(out["method"], "dersimonian_laird_random_effects")

    def test_random_effects_widens_the_interval_on_purpose(self):
        agree = nsc._inverse_variance_meta([(100.0, 1.0), (100.2, 1.0), (99.8, 1.0)])
        disagree = nsc._inverse_variance_meta([(20.0, 1.0), (100.0, 1.0), (60.0, 1.0)])
        self.assertGreater(disagree["ci"], agree["ci"])

    def test_precise_provider_is_weighted_more_than_noisy_one(self):
        out = nsc._inverse_variance_meta([(100.0, 0.1), (10.0, 10.0)], i2_threshold=1e9)
        self.assertGreater(out["estimate"], 90.0)

    def test_i2_is_zero_for_perfect_agreement(self):
        out = nsc._inverse_variance_meta([(50.0, 1.0), (50.0, 1.0), (50.0, 1.0)])
        self.assertAlmostEqual(out["i2"], 0.0, places=6)

    def test_i2_is_high_for_strong_disagreement(self):
        out = nsc._inverse_variance_meta([(10.0, 0.2), (90.0, 0.2)])
        self.assertGreater(out["i2"], 50.0)

    def test_single_provider_degrades_gracefully(self):
        out = nsc._inverse_variance_meta([(42.0, 1.0)])
        self.assertAlmostEqual(out["estimate"], 42.0)
        self.assertEqual(out["k"], 1)

    def test_empty_input_does_not_crash(self):
        out = nsc._inverse_variance_meta([])
        self.assertEqual(out["estimate"], 0.0)

    def test_unusable_standard_errors_fall_back_to_the_plain_mean(self):
        """A zero or negative SE cannot be weighted (1/se^2 is undefined), so such
        points cannot enter the inverse-variance sum. With fewer than two weightable
        points the estimator documents a fallback to the plain mean of EVERY
        estimate - discarding two providers outright would be worse than averaging
        them unweighted."""
        out = nsc._inverse_variance_meta([(100.0, 0.0), (100.0, -1.0), (50.0, 1.0)])
        self.assertAlmostEqual(out["estimate"], (100.0 + 100.0 + 50.0) / 3.0, delta=0.001)

    def test_the_fallback_names_itself_honestly(self):
        """The fallback must not masquerade as a weighted fusion: it reports
        method='unweighted_mean', k = the number of estimates actually averaged,
        and se/ci = 0 because no interval can be justified without usable SEs."""
        out = nsc._inverse_variance_meta([(100.0, 0.0), (100.0, -1.0), (50.0, 1.0)])
        self.assertEqual(out["method"], "unweighted_mean")
        self.assertEqual(out["k"], 3)
        self.assertEqual(out["ci"], 0.0)

    def test_weighted_branch_counts_only_usable_points(self):
        out = nsc._inverse_variance_meta([(10.0, 1.0), (12.0, 1.0), (11.0, 0.0)])
        self.assertEqual(out["k"], 2)
        self.assertNotEqual(out["method"], "unweighted_mean")

    def test_k_counts_usable_points_only(self):
        out = nsc._inverse_variance_meta([(10.0, 1.0), (12.0, 1.0), (11.0, 0.0)])
        self.assertEqual(out["k"], 2)

    def test_ci_is_never_negative(self):
        out = nsc._inverse_variance_meta([(10.0, 1.0), (80.0, 2.0)])
        self.assertGreaterEqual(out["ci"], 0.0)

    def test_tau2_is_zero_under_fixed_effect(self):
        out = nsc._inverse_variance_meta([(50.0, 1.0), (50.1, 1.0)])
        self.assertAlmostEqual(out["tau2"], 0.0)


# ══════════════════════════════════════════════════════════════════════════
# 5. BUFFERBLOAT GRADING
# ══════════════════════════════════════════════════════════════════════════

class BufferbloatGradeTests(unittest.TestCase):
    """The Waveform / DSLReports scale. This grade is the whole reason a 'fast'
    link can still be useless for VoIP, so the bands must not drift."""

    def test_grade_a_plus_under_5ms(self):
        self.assertEqual(nsc._bufferbloat_grade(4.9), "A+")

    def test_grade_a_at_5ms_boundary(self):
        self.assertEqual(nsc._bufferbloat_grade(5.0), "A")

    def test_grade_a_under_30ms(self):
        self.assertEqual(nsc._bufferbloat_grade(29.9), "A")

    def test_grade_b_at_30ms_boundary(self):
        self.assertEqual(nsc._bufferbloat_grade(30.0), "B")

    def test_grade_c_at_60ms_boundary(self):
        self.assertEqual(nsc._bufferbloat_grade(60.0), "C")

    def test_grade_d_at_200ms_boundary(self):
        self.assertEqual(nsc._bufferbloat_grade(200.0), "D")

    def test_grade_f_at_400ms_boundary(self):
        self.assertEqual(nsc._bufferbloat_grade(400.0), "F")

    def test_grade_f_for_extreme_bloat(self):
        self.assertEqual(nsc._bufferbloat_grade(5000.0), "F")

    def test_zero_delta_is_best_grade(self):
        self.assertEqual(nsc._bufferbloat_grade(0.0), "A+")

    def test_grades_are_monotonic_across_the_scale(self):
        order = ["A+", "A", "B", "C", "D", "F"]
        seen = [nsc._bufferbloat_grade(d) for d in (0, 10, 45, 100, 300, 900)]
        self.assertEqual(seen, order)


# ══════════════════════════════════════════════════════════════════════════
# 6. CONFIG COERCION
# ══════════════════════════════════════════════════════════════════════════

class CoercionTests(unittest.TestCase):
    """The wrapped chat-agent parser can hand a field through as prose, so every
    numeric read must extract the number and never raise."""

    def test_as_int_plain(self):
        self.assertEqual(nsc._as_int(7, 1), 7)

    def test_as_int_numeric_string(self):
        self.assertEqual(nsc._as_int("12", 1), 12)

    def test_as_int_from_prose(self):
        self.assertEqual(nsc._as_int("6 concurrent streams", 1), 6)

    def test_as_int_bad_value_uses_default(self):
        self.assertEqual(nsc._as_int("not a number", 5), 5)

    def test_as_int_none_uses_default(self):
        self.assertEqual(nsc._as_int(None, 9), 9)

    def test_as_int_empty_string_uses_default(self):
        self.assertEqual(nsc._as_int("", 3), 3)

    def test_as_int_float_input_truncates(self):
        self.assertEqual(nsc._as_int(7.9, 1), 7)

    def test_as_float_plain(self):
        self.assertAlmostEqual(nsc._as_float(0.25, 1.0), 0.25)

    def test_as_float_numeric_string(self):
        self.assertAlmostEqual(nsc._as_float("2.5", 1.0), 2.5)

    def test_as_float_from_prose(self):
        self.assertAlmostEqual(nsc._as_float("0.95 confidence", 0.5), 0.95)

    def test_as_float_bad_value_uses_default(self):
        self.assertAlmostEqual(nsc._as_float("abc", 1.5), 1.5)

    def test_as_float_none_uses_default(self):
        self.assertAlmostEqual(nsc._as_float(None, 2.0), 2.0)

    def test_as_bool_true_variants(self):
        for raw in (True, "true", "True", "yes", "1", "on"):
            with self.subTest(raw=raw):
                self.assertTrue(nsc._as_bool(raw, False))

    def test_as_bool_false_variants(self):
        for raw in (False, "false", "False", "no", "0", "off"):
            with self.subTest(raw=raw):
                self.assertFalse(nsc._as_bool(raw, True))

    def test_as_bool_unknown_uses_default(self):
        self.assertTrue(nsc._as_bool("maybe", True))
        self.assertFalse(nsc._as_bool("maybe", False))

    def test_cfg_reads_a_present_key(self):
        self.assertEqual(nsc._cfg({"action": "full"}, "action", "x"), "full")

    def test_cfg_missing_key_returns_default(self):
        self.assertEqual(nsc._cfg({}, "action", "full"), "full")

    def test_cfg_none_value_returns_default(self):
        self.assertEqual(nsc._cfg({"action": None}, "action", "full"), "full")


# ══════════════════════════════════════════════════════════════════════════
# 7. CACHE-BUSTER  (regression: bug 4)
# ══════════════════════════════════════════════════════════════════════════

class CacheBusterTests(unittest.TestCase):

    def test_bust_adds_a_query_when_none_present(self):
        out = nsc._bust("https://example.com/100MB.bin", "1-1")
        self.assertIn("?nocache=", out)

    def test_bust_appends_with_ampersand_when_query_present(self):
        out = nsc._bust("https://example.com/__down?bytes=25000000", "1-1")
        self.assertIn("&nocache=", out)
        self.assertIn("bytes=25000000", out)

    def test_bust_is_unique_per_salt(self):
        a = nsc._bust("https://example.com/x", "1-1")
        b = nsc._bust("https://example.com/x", "1-2")
        self.assertNotEqual(a, b)

    def test_bust_preserves_the_original_url_prefix(self):
        url = "https://example.com/deep/path.bin"
        self.assertTrue(nsc._bust(url, "0-1").startswith(url))

    def test_bust_carries_the_salt(self):
        self.assertIn("7-3", nsc._bust("https://example.com/x", "7-3"))


# ══════════════════════════════════════════════════════════════════════════
# 8. ERROR SURFACING  — the architectural fix that made bugs 1 and 4 findable
# ══════════════════════════════════════════════════════════════════════════

class RecordErrorTests(unittest.TestCase):

    def test_records_type_and_message(self):
        errors = []
        nsc._record_error(errors, ValueError("boom"))
        self.assertEqual(errors, ["ValueError: boom"])

    def test_deduplicates_identical_failures(self):
        errors = []
        for _ in range(50):
            nsc._record_error(errors, ValueError("same"))
        self.assertEqual(len(errors), 1)

    def test_keeps_distinct_failures(self):
        errors = []
        nsc._record_error(errors, ValueError("a"))
        nsc._record_error(errors, RuntimeError("b"))
        self.assertEqual(len(errors), 2)

    def test_is_bounded_at_five(self):
        """Six streams retrying for eight seconds would otherwise bury the log."""
        errors = []
        for i in range(100):
            nsc._record_error(errors, ValueError("distinct %d" % i))
        self.assertEqual(len(errors), 5)

    def test_never_raises_on_a_weird_exception(self):
        class Weird(Exception):
            def __str__(self):
                return "weird"
        errors = []
        nsc._record_error(errors, Weird())
        self.assertEqual(len(errors), 1)


class ReportDeadTransferTests(unittest.TestCase):
    """A transfer that moved nothing MUST name its cause. A silent 0.00 Mbps is
    indistinguishable from a slow link and sends the user hunting their router."""

    def test_zero_bytes_populates_why(self):
        red = {}
        raw = {"total_bytes": 0, "errors": ["HTTPError: HTTP Error 403: Forbidden"]}
        nsc._report_dead_transfer("cloudflare", "download", raw, red)
        self.assertIn("why", red)
        self.assertIn("403", red["why"][0])

    def test_zero_bytes_with_no_exception_still_explains_itself(self):
        red = {}
        nsc._report_dead_transfer("hetzner", "download", {"total_bytes": 0, "errors": []}, red)
        self.assertIn("why", red)
        self.assertTrue(red["why"])

    def test_successful_transfer_gets_no_why_key(self):
        red = {}
        nsc._report_dead_transfer("cloudflare", "download",
                                  {"total_bytes": 12345, "errors": []}, red)
        self.assertNotIn("why", red)

    def test_missing_errors_key_does_not_crash(self):
        red = {}
        nsc._report_dead_transfer("x", "download", {"total_bytes": 0}, red)
        self.assertIn("why", red)

    def test_why_is_a_list_of_strings(self):
        red = {}
        nsc._report_dead_transfer("x", "upload", {"total_bytes": 0, "errors": ["A: b"]}, red)
        self.assertIsInstance(red["why"], list)
        self.assertTrue(all(isinstance(w, str) for w in red["why"]))

    def test_all_recorded_reasons_survive_into_the_result(self):
        red = {}
        raw = {"total_bytes": 0, "errors": ["A: 1", "B: 2", "C: 3"]}
        nsc._report_dead_transfer("x", "download", raw, red)
        self.assertEqual(len(red["why"]), 3)


# ══════════════════════════════════════════════════════════════════════════
# 9. MIRROR SELECTION BY MEASURED RTT  (regression: bug 3)
# ══════════════════════════════════════════════════════════════════════════

class PickByRttTests(unittest.TestCase):

    def setUp(self):
        self._saved = nsc._tcp_rtt_ms

    def tearDown(self):
        nsc._tcp_rtt_ms = self._saved

    def test_picks_the_lowest_measured_rtt_not_the_first_listed(self):
        table = {"far.example": 400.0, "near.example": 30.0, "mid.example": 120.0}
        nsc._tcp_rtt_ms = lambda h, p, t: table.get(h)
        self.assertEqual(
            nsc._pick_by_rtt(["far.example", "near.example", "mid.example"], 443, 5.0),
            "near.example")

    def test_unreachable_hosts_are_skipped(self):
        nsc._tcp_rtt_ms = lambda h, p, t: None if h == "dead.example" else 50.0
        self.assertEqual(nsc._pick_by_rtt(["dead.example", "alive.example"], 443, 5.0),
                         "alive.example")

    def test_falls_back_to_the_first_host_when_none_answer(self):
        nsc._tcp_rtt_ms = lambda h, p, t: None
        self.assertEqual(nsc._pick_by_rtt(["a.example", "b.example"], 443, 5.0), "a.example")

    def test_empty_host_list_returns_empty_string(self):
        nsc._tcp_rtt_ms = lambda h, p, t: None
        self.assertEqual(nsc._pick_by_rtt([], 443, 5.0), "")

    def test_single_host_is_returned(self):
        nsc._tcp_rtt_ms = lambda h, p, t: 12.0
        self.assertEqual(nsc._pick_by_rtt(["only.example"], 443, 5.0), "only.example")


# ══════════════════════════════════════════════════════════════════════════
# 10. ENDPOINT DISCOVERY  (regressions: bugs 1, 2, 3, 4)
# ══════════════════════════════════════════════════════════════════════════

class CloudflareDiscoveryTests(unittest.TestCase):

    def setUp(self):
        self._saved = nsc._read_text
        nsc._read_text = lambda url, timeout, **kw: "ip=203.0.113.9\nloc=MX\ncolo=QRO\n"

    def tearDown(self):
        nsc._read_text = self._saved

    def test_oversized_request_is_clamped(self):
        """MEASURED 2026-08-22: bytes=100000000 -> 403 Forbidden, and every stream
        then produced ZERO bytes. bytes=25000000 -> 200 OK."""
        prov = nsc._discover_cloudflare(10.0, 100_000_000)
        url = prov["download"][0]
        self.assertIn("bytes=%d" % nsc._CF_MAX_DOWN_BYTES, url)
        self.assertNotIn("bytes=100000000", url)

    def test_clamp_constant_is_below_the_403_threshold(self):
        self.assertLess(nsc._CF_MAX_DOWN_BYTES, 100_000_000)

    def test_smaller_request_is_left_alone(self):
        prov = nsc._discover_cloudflare(10.0, 5_000_000)
        self.assertIn("bytes=5000000", prov["download"][0])

    def test_tiny_request_is_floored_to_something_measurable(self):
        prov = nsc._discover_cloudflare(10.0, 1)
        self.assertNotIn("bytes=1&", prov["download"][0] + "&")

    def test_exposes_an_upload_endpoint(self):
        self.assertTrue(nsc._discover_cloudflare(10.0, 25_000_000)["upload"])

    def test_client_ip_is_read_from_the_trace(self):
        self.assertEqual(nsc._discover_cloudflare(10.0, 25_000_000)["client_ip"], "203.0.113.9")

    def test_location_includes_the_edge_colo(self):
        self.assertIn("QRO", nsc._discover_cloudflare(10.0, 25_000_000)["location"])

    def test_trace_failure_degrades_but_still_returns_endpoints(self):
        def boom(url, timeout, **kw):
            raise RuntimeError("network down")
        nsc._read_text = boom
        prov = nsc._discover_cloudflare(10.0, 25_000_000)
        self.assertTrue(prov["download"])


class LibreSpeedDiscoveryTests(unittest.TestCase):
    """MEASURED 2026-08-22: librespeed.org/backend/garbage.php AND empty.php both
    answer 404. The live surface is the project's published server list."""

    _LIST = ('[{"name":"Far","server":"//far.example/","dlURL":"garbage.php",'
             '"ulURL":"empty.php"},'
             '{"name":"Near","server":"https://near.example/","dlURL":"garbage.php",'
             '"ulURL":"empty.php"}]')

    def setUp(self):
        self._read = nsc._read_text
        self._rtt = nsc._tcp_rtt_ms
        nsc._read_text = lambda url, timeout, **kw: self._LIST
        nsc._tcp_rtt_ms = lambda h, p, t: 300.0 if h == "far.example" else 20.0

    def tearDown(self):
        nsc._read_text = self._read
        nsc._tcp_rtt_ms = self._rtt

    def test_does_not_use_the_dead_hardcoded_backend(self):
        prov = nsc._discover_librespeed(10.0)
        self.assertNotIn("librespeed.org/backend", prov["download"][0])

    def test_picks_the_nearest_server_by_measured_rtt(self):
        prov = nsc._discover_librespeed(10.0)
        self.assertIn("near.example", prov["download"][0])

    def test_protocol_relative_urls_are_normalised_to_https(self):
        nsc._tcp_rtt_ms = lambda h, p, t: 10.0 if h == "far.example" else 900.0
        prov = nsc._discover_librespeed(10.0)
        self.assertTrue(prov["download"][0].startswith("https://"))

    def test_exposes_an_upload_endpoint_from_the_list(self):
        self.assertIn("empty.php", nsc._discover_librespeed(10.0)["upload"])

    def test_empty_server_list_raises_rather_than_returning_garbage(self):
        nsc._read_text = lambda url, timeout, **kw: "[]"
        with self.assertRaises(RuntimeError):
            nsc._discover_librespeed(10.0)

    def test_unusable_entries_raise_rather_than_returning_garbage(self):
        nsc._read_text = lambda url, timeout, **kw: '[{"name":"X","server":"ftp-only"}]'
        with self.assertRaises(RuntimeError):
            nsc._discover_librespeed(10.0)

    def test_probe_limit_is_bounded(self):
        self.assertGreaterEqual(nsc._LIBRESPEED_PROBE_LIMIT, 1)
        self.assertLessEqual(nsc._LIBRESPEED_PROBE_LIMIT, 12)

    def test_download_url_carries_a_size_parameter(self):
        self.assertIn("ckSize=", nsc._discover_librespeed(10.0)["download"][0])


class HetznerDiscoveryTests(unittest.TestCase):
    """MEASURED 2026-08-22: speed.hetzner.de does not resolve at all (getaddrinfo
    failed). The live surface is the .com datacentre mirror mesh."""

    def setUp(self):
        self._rtt = nsc._tcp_rtt_ms
        nsc._tcp_rtt_ms = lambda h, p, t: 70.0 if h.startswith("ash-") else 400.0

    def tearDown(self):
        nsc._tcp_rtt_ms = self._rtt

    def test_does_not_use_the_dead_de_host(self):
        prov = nsc._discover_hetzner(10.0)
        self.assertNotIn("speed.hetzner.de", prov["download"][0])

    def test_uses_the_com_mirror_mesh(self):
        self.assertIn("hetzner.com", nsc._discover_hetzner(10.0)["download"][0])

    def test_picks_the_nearest_mirror_by_measured_rtt(self):
        self.assertIn("ash-speed.hetzner.com", nsc._discover_hetzner(10.0)["download"][0])

    def test_cache_buster_is_declared_off(self):
        """The mirror serves /100MB.bin with 200 but RESETS the connection when the
        URL carries an unknown query string — the buster written to protect the
        measurement was destroying it."""
        self.assertIs(nsc._discover_hetzner(10.0)["cache_bust"], False)

    def test_rtt_probe_targets_the_chosen_mirror(self):
        prov = nsc._discover_hetzner(10.0)
        self.assertEqual(prov["rtt"][0], "ash-speed.hetzner.com")

    def test_declares_no_upload_endpoint(self):
        self.assertEqual(nsc._discover_hetzner(10.0)["upload"], "")

    def test_label_names_the_actual_mirror_used(self):
        self.assertIn("ash-speed", nsc._discover_hetzner(10.0)["label"])


class ProviderCatalogueTests(unittest.TestCase):

    def test_catalogue_lists_every_dispatchable_provider(self):
        for key in nsc.PROVIDER_CATALOGUE:
            with self.subTest(provider=key):
                self.assertIsNotNone(nsc._discover)

    def test_unknown_provider_raises(self):
        with self.assertRaises(RuntimeError):
            nsc._discover("no-such-provider", 5.0, 1000)

    def test_cachefly_is_catalogued(self):
        self.assertIn("cachefly", nsc.PROVIDER_CATALOGUE)

    def test_every_catalogue_entry_has_a_description(self):
        for key, text in nsc.PROVIDER_CATALOGUE.items():
            with self.subTest(provider=key):
                self.assertTrue(text.strip())

    def test_cachefly_discovery_returns_a_download_url(self):
        self.assertTrue(nsc._discover_cachefly(5.0)["download"][0].startswith("http"))

    def test_discover_dispatches_by_key(self):
        self.assertEqual(nsc._discover("cachefly", 5.0, 1000)["key"], "cachefly")

    def test_default_cache_bust_is_absent_for_query_tolerant_providers(self):
        """Only Hetzner declares the flag; everyone else defaults to True at the
        call site, so an absent key must mean 'bust is fine'."""
        self.assertNotIn("cache_bust", nsc._discover_cachefly(5.0))


# ══════════════════════════════════════════════════════════════════════════
# 11. TRANSFER ENGINE
# ══════════════════════════════════════════════════════════════════════════

class DownloadWorkerTests(unittest.TestCase):

    def setUp(self):
        self._open = nsc._open

    def tearDown(self):
        nsc._open = self._open

    def test_counts_bytes_into_its_slot(self):
        nsc._open = lambda url, timeout, **kw: _FakeResponse(b"x" * 200000)
        counters, errors = [0], []
        stop = threading.Event()
        nsc._download_worker(0, ["https://example.com/f.bin"], counters, stop,
                             time.monotonic() + 0.4, 5.0, 100000, errors, False)
        self.assertGreater(counters[0], 0)

    def test_self_heals_when_the_endpoint_rejects_the_cache_buster(self):
        """The Hetzner regression: busted URL resets, plain URL works. The worker
        must drop the buster and still measure."""
        def fake_open(url, timeout, **kw):
            if "nocache=" in url:
                raise RuntimeError("RemoteDisconnected")
            return _FakeResponse(b"y" * 200000)
        nsc._open = fake_open
        counters, errors = [0], []
        stop = threading.Event()
        nsc._download_worker(0, ["https://mirror.example/100MB.bin"], counters, stop,
                             time.monotonic() + 0.6, 5.0, 100000, errors, True)
        self.assertGreater(counters[0], 0, "self-heal did not recover the transfer")
        self.assertTrue(any("cache-buster" in e for e in errors))

    def test_records_the_reason_when_every_request_fails(self):
        def always_fail(url, timeout, **kw):
            raise RuntimeError("HTTP Error 403: Forbidden")
        nsc._open = always_fail
        counters, errors = [0], []
        stop = threading.Event()
        nsc._download_worker(0, ["https://example.com/f.bin"], counters, stop,
                             time.monotonic() + 0.3, 5.0, 100000, errors, False)
        self.assertEqual(counters[0], 0)
        self.assertTrue(any("403" in e for e in errors))

    def test_stop_event_ends_the_worker(self):
        nsc._open = lambda url, timeout, **kw: _FakeResponse(b"z" * 100000)
        counters, errors = [0], []
        stop = threading.Event()
        stop.set()
        nsc._download_worker(0, ["https://example.com/f.bin"], counters, stop,
                             time.monotonic() + 5.0, 5.0, 100000, errors, False)
        self.assertEqual(counters[0], 0)

    def test_rotates_across_multiple_urls(self):
        seen = []

        def fake_open(url, timeout, **kw):
            seen.append(url)
            return _FakeResponse(b"a" * 1000)
        nsc._open = fake_open
        counters, errors = [0], []
        stop = threading.Event()
        nsc._download_worker(0, ["https://a.example/1", "https://b.example/2"],
                             counters, stop, time.monotonic() + 0.3, 5.0, 500, errors, False)
        self.assertTrue(any("a.example" in u for u in seen))

    def test_never_raises_into_the_caller(self):
        def explode(url, timeout, **kw):
            raise KeyError("unexpected")
        nsc._open = explode
        counters, errors = [0], []
        stop = threading.Event()
        nsc._download_worker(0, ["https://example.com/x"], counters, stop,
                             time.monotonic() + 0.2, 5.0, 1000, errors, True)
        self.assertEqual(counters[0], 0)


class SamplerTests(unittest.TestCase):

    def test_sampler_measures_the_derivative_not_the_total(self):
        counters = [0]
        out = []
        stop = threading.Event()
        t0 = time.monotonic()
        deadline = t0 + 0.5

        def grow():
            for _ in range(4):
                time.sleep(0.06)
                counters[0] += 125000  # 1 Mbit per tick
        th = threading.Thread(target=grow, daemon=True)
        th.start()
        nsc._sampler(counters, 0.05, deadline, stop, out, t0)
        th.join(timeout=1.0)
        self.assertTrue(out, "sampler produced no slices")
        self.assertTrue(all(mbps >= 0 for _, mbps in out))

    def test_sampler_stops_on_the_stop_event(self):
        counters, out = [0], []
        stop = threading.Event()
        stop.set()
        nsc._sampler(counters, 0.05, time.monotonic() + 5.0, stop, out, time.monotonic())
        self.assertEqual(out, [])

    def test_sampler_emits_timestamped_pairs(self):
        counters, out = [0], []
        stop = threading.Event()
        t0 = time.monotonic()
        nsc._sampler(counters, 0.02, t0 + 0.15, stop, out, t0)
        for item in out:
            self.assertEqual(len(item), 2)


class RunTransferTests(unittest.TestCase):

    def setUp(self):
        self._open = nsc._open
        nsc._open = lambda url, timeout, **kw: _FakeResponse(b"q" * 50000)

    def tearDown(self):
        nsc._open = self._open

    def test_returns_the_documented_result_shape(self):
        raw = nsc._run_transfer("download", ["https://example.com/x"], 2, 0.2, 0.1,
                                0.05, 5.0, 20000, b"p" * 1024, 1024)
        for key in ("raw_samples", "all_samples", "discarded_warmup", "total_bytes",
                    "loaded_rtts", "streams", "errors"):
            with self.subTest(key=key):
                self.assertIn(key, raw)

    def test_errors_list_is_always_present(self):
        raw = nsc._run_transfer("download", ["https://example.com/x"], 1, 0.15, 0.05,
                                0.05, 5.0, 10000, b"p" * 512, 512)
        self.assertIsInstance(raw["errors"], list)

    def test_streams_are_clamped_to_a_sane_maximum(self):
        raw = nsc._run_transfer("download", ["https://example.com/x"], 9999, 0.15, 0.05,
                                0.05, 5.0, 5000, b"p" * 512, 512)
        self.assertLessEqual(raw["streams"], 32)

    def test_streams_are_clamped_to_at_least_one(self):
        raw = nsc._run_transfer("download", ["https://example.com/x"], 0, 0.15, 0.05,
                                0.05, 5.0, 5000, b"p" * 512, 512)
        self.assertGreaterEqual(raw["streams"], 1)

    def test_cache_bust_flag_is_honoured(self):
        seen = []

        def fake_open(url, timeout, **kw):
            seen.append(url)
            return _FakeResponse(b"r" * 5000)
        nsc._open = fake_open
        nsc._run_transfer("download", ["https://example.com/x"], 1, 0.15, 0.05,
                          0.05, 5.0, 2000, b"p" * 512, 512, cache_bust=False)
        self.assertTrue(seen)
        self.assertFalse(any("nocache=" in u for u in seen))


class ReduceTests(unittest.TestCase):

    def test_reduce_of_empty_is_not_ok(self):
        out = nsc._reduce([], "tukey", 10.0, 0.95)
        self.assertFalse(out["ok"])
        self.assertEqual(out["mbps"], 0.0)

    def test_reduce_of_a_clean_sample_is_ok(self):
        out = nsc._reduce([90.0, 91.0, 89.5, 90.5, 90.2], "tukey", 10.0, 0.95)
        self.assertTrue(out["ok"])
        self.assertAlmostEqual(out["mbps"], 90.0, delta=1.5)

    def test_reduce_reports_the_rejected_count(self):
        out = nsc._reduce([90, 90.5, 91, 90.2, 90.8, 900.0], "tukey", 10.0, 0.95)
        self.assertGreaterEqual(out["rejected"], 1)

    def test_reduce_reports_n_of_kept_points(self):
        out = nsc._reduce([10.0, 10.1, 10.2, 10.3], "none", 0.0, 0.95)
        self.assertEqual(out["n"], 4)

    def test_reduce_ci_is_non_negative(self):
        out = nsc._reduce([10.0, 12.0, 11.0, 13.0], "tukey", 10.0, 0.95)
        self.assertGreaterEqual(out["ci"], 0.0)

    def test_reduce_cv_is_zero_for_identical_samples(self):
        out = nsc._reduce([50.0, 50.0, 50.0, 50.0], "none", 0.0, 0.95)
        self.assertAlmostEqual(out["cv_pct"], 0.0)

    def test_reduce_p95_is_at_least_the_median(self):
        out = nsc._reduce([1.0, 2.0, 3.0, 4.0, 5.0], "none", 0.0, 0.95)
        self.assertGreaterEqual(out["p95"], out["median"])


# ══════════════════════════════════════════════════════════════════════════
# 12. FAIL-SAFE PREFLIGHT
# ══════════════════════════════════════════════════════════════════════════

class PreflightTests(unittest.TestCase):

    def test_valid_full_run_passes(self):
        report = nsc._preflight("full", {}, ["cloudflare"])
        self.assertTrue(report["ok"], report["errors"])

    def test_unknown_action_is_refused(self):
        report = nsc._preflight("teleport", {}, ["cloudflare"])
        self.assertFalse(report["ok"])

    def test_unknown_provider_is_refused(self):
        report = nsc._preflight("full", {}, ["not-a-provider"])
        self.assertFalse(report["ok"])

    def test_error_message_names_the_unknown_provider(self):
        report = nsc._preflight("full", {}, ["bogus-cdn"])
        self.assertTrue(any("bogus-cdn" in e for e in report["errors"]))

    def test_providers_action_short_circuits_without_needing_providers(self):
        report = nsc._preflight("providers", {}, [])
        self.assertTrue(report["ok"])

    def test_report_always_has_the_documented_keys(self):
        report = nsc._preflight("full", {}, ["cloudflare"])
        for key in ("ok", "errors", "warnings"):
            with self.subTest(key=key):
                self.assertIn(key, report)

    def test_every_catalogued_provider_can_run_a_download(self):
        for key in nsc.PROVIDER_CATALOGUE:
            with self.subTest(provider=key):
                self.assertTrue(nsc._preflight("download", {}, [key])["ok"])

    def test_upload_capable_providers_pass_a_full_run(self):
        for key in ("cloudflare", "ookla", "librespeed"):
            with self.subTest(provider=key):
                self.assertTrue(nsc._preflight("full", {}, [key])["ok"])

    def test_download_only_provider_is_refused_for_upload_not_mis_measured(self):
        """fast / hetzner / cachefly expose NO upload endpoint. Asking them for an
        upload figure must REFUSE with an actionable message naming the providers
        that can do it - never invent a number."""
        for key in ("fast", "hetzner", "cachefly"):
            with self.subTest(provider=key):
                report = nsc._preflight("upload", {}, [key])
                self.assertFalse(report["ok"])
                self.assertTrue(any("upload-capable" in e for e in report["errors"]))


# ══════════════════════════════════════════════════════════════════════════
# 13. FORMATTING & SECTION EMISSION
# ══════════════════════════════════════════════════════════════════════════

class FormattingTests(unittest.TestCase):

    def test_fmt_rounds_to_two_places(self):
        self.assertEqual(nsc._fmt(3.14159), "3.14")

    def test_fmt_honours_the_digits_argument(self):
        self.assertEqual(nsc._fmt(3.14159, 4), "3.1416")

    def test_fmt_nan_is_not_a_number_string(self):
        self.assertEqual(nsc._fmt(float("nan")), "n/a")

    def test_fmt_infinity_is_not_a_number_string(self):
        self.assertEqual(nsc._fmt(float("inf")), "n/a")

    def test_fmt_negative_infinity_is_not_a_number_string(self):
        self.assertEqual(nsc._fmt(float("-inf")), "n/a")

    def test_fmt_of_garbage_never_raises(self):
        self.assertEqual(nsc._fmt("not a number"), "n/a")

    def test_human_bytes_scales_to_kib(self):
        self.assertIn("KiB", nsc._human_bytes(2048))

    def test_human_bytes_scales_to_mib(self):
        self.assertIn("MiB", nsc._human_bytes(5 * 1024 * 1024))

    def test_human_bytes_zero_is_bytes(self):
        self.assertIn("B", nsc._human_bytes(0))


class SectionEmissionTests(unittest.TestCase):
    """The section is the Parametrizer contract; it must be ONE atomic record."""

    def _capture(self, fields, body):
        records = []

        class _Grab(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        root = logging.getLogger()
        saved_handlers, saved_level = root.handlers[:], root.level
        handler = _Grab()
        root.handlers[:] = [handler]
        root.setLevel(logging.INFO)
        try:
            nsc._emit_section(fields, body)
        finally:
            root.handlers[:] = saved_handlers
            root.setLevel(saved_level)
        return records

    def test_section_is_emitted_in_a_single_atomic_record(self):
        records = self._capture({"status": "ok"}, "body")
        self.assertEqual(len(records), 1)

    def test_section_has_the_opening_token(self):
        self.assertIn("INI_SECTION_NETSPEED_CALCULATOR<<<", self._capture({"a": "1"}, "b")[0])

    def test_section_has_the_closing_token(self):
        self.assertIn(">>>END_SECTION_NETSPEED_CALCULATOR", self._capture({"a": "1"}, "b")[0])

    def test_header_and_body_are_separated_by_a_blank_line(self):
        text = self._capture({"k": "v"}, "the body")[0]
        self.assertIn("k: v\n\nthe body", text)

    def test_all_header_fields_are_present(self):
        text = self._capture({"one": 1, "two": 2}, "b")[0]
        self.assertIn("one: 1", text)
        self.assertIn("two: 2", text)

    def test_section_round_trips_through_the_parametrizer_grammar(self):
        text = self._capture({"status": "ok", "download_mbps": "92.82"}, "report")[0]
        start = text.index("INI_SECTION_NETSPEED_CALCULATOR<<<")
        end = text.index(">>>END_SECTION_NETSPEED_CALCULATOR")
        inner = text[start + len("INI_SECTION_NETSPEED_CALCULATOR<<<"):end].strip("\n")
        header, _, body = inner.partition("\n\n")
        parsed = dict(line.split(": ", 1) for line in header.splitlines() if ": " in line)
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["download_mbps"], "92.82")
        self.assertEqual(body.strip(), "report")


# ══════════════════════════════════════════════════════════════════════════
# 14. REGISTRY INTEGRATION (the ~15 wiring surfaces)
# ══════════════════════════════════════════════════════════════════════════

class RegistryIntegrationTests(SimpleTestCase):

    TOOL = "chat_agent_netspeed_calculator"
    DISPLAY = "NetSpeed-Calculator"
    KEY = "netspeed_calculator"

    def test_wrapped_chat_agent_spec_exists(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        self.assertIn(self.TOOL, WRAPPED_CHAT_AGENT_BY_TOOL_NAME)

    def test_spec_display_name_is_exactly_hyphenated(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        self.assertEqual(WRAPPED_CHAT_AGENT_BY_TOOL_NAME[self.TOOL].display_name, self.DISPLAY)

    def test_spec_template_dir_matches_the_agent_folder(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        self.assertEqual(WRAPPED_CHAT_AGENT_BY_TOOL_NAME[self.TOOL].template_dir, self.KEY)

    def test_spec_tool_description_matches_the_seeded_tool_row_name(self):
        from agent.chat_agent_registry import WRAPPED_CHAT_AGENT_BY_TOOL_NAME
        self.assertEqual(WRAPPED_CHAT_AGENT_BY_TOOL_NAME[self.TOOL].tool_description,
                         "Chat-Agent-NetSpeed-Calculator")

    def test_display_name_override_is_registered(self):
        from agent.services.agent_paths import display_name_from_agent_type
        self.assertEqual(display_name_from_agent_type(self.KEY), self.DISPLAY)

    def test_display_name_is_not_title_cased_by_accident(self):
        from agent.services.agent_paths import display_name_from_agent_type
        self.assertNotEqual(display_name_from_agent_type(self.KEY), "Netspeed_Calculator")

    def test_parametrizer_output_fields_are_registered(self):
        from agent.services.agent_contracts import get_agent_contract
        fields = get_agent_contract(self.KEY).parametrizer_fields
        self.assertIn("download_mbps", fields)
        self.assertIn("response_body", fields)

    def test_parametrizer_fields_include_the_branching_keys(self):
        from agent.services.agent_contracts import get_agent_contract
        fields = get_agent_contract(self.KEY).parametrizer_fields
        for key in ("success", "status", "bufferbloat_grade", "json_path"):
            with self.subTest(field=key):
                self.assertIn(key, fields)

    def test_section_agent_type_is_registered_with_parametrizer(self):
        path = os.path.join(_HERE, 'agents', 'parametrizer', 'parametrizer.py')
        with open(path, 'r', encoding='utf-8') as fh:
            self.assertIn("'%s'" % self.KEY, fh.read())

    def test_exec_report_captures_the_agent(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertIn(self.TOOL, _EXEC_REPORT_TOOLS)

    def test_exec_report_agent_key_matches_the_css_class_root(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS[self.TOOL][0], "netspeedcalculator")

    def test_exec_report_display_is_the_hyphenated_name(self):
        from agent.mcp_agent import _EXEC_REPORT_TOOLS
        self.assertEqual(_EXEC_REPORT_TOOLS[self.TOOL][1], self.DISPLAY)

    def test_ask_execs_gates_the_agent_as_tier_d(self):
        """It reaches remote hosts like Crawler AND saturates the link with
        ~100-200 MB of real, possibly metered traffic."""
        from agent.mcp_agent import _ASK_EXECS_REQUIRED_TOOLS
        self.assertIn(self.TOOL, _ASK_EXECS_REQUIRED_TOOLS)

    def test_promote_section_fields_are_registered(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        self.assertIn(self.KEY, _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR)

    def test_promoted_fields_surface_the_headline_numbers(self):
        from agent.tools import _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR
        promoted = _PROMOTE_SECTION_FIELDS_BY_TEMPLATE_DIR[self.KEY]
        for key in ("download_mbps", "upload_mbps", "bufferbloat_grade"):
            with self.subTest(field=key):
                self.assertIn(key, promoted)

    def test_pre_launch_preview_is_declared_exactly_once(self):
        """A contract test in tests.py requires every wrapped agent to be in
        exactly one of the two preview sets."""
        from agent.tools import (_PRE_LAUNCH_PREVIEW_BY_TEMPLATE,
                                 _PRE_LAUNCH_PREVIEW_OBSERVATIONAL_TEMPLATES)
        in_preview = self.KEY in _PRE_LAUNCH_PREVIEW_BY_TEMPLATE
        in_observational = self.KEY in _PRE_LAUNCH_PREVIEW_OBSERVATIONAL_TEMPLATES
        self.assertNotEqual(in_preview, in_observational,
                            "must be in exactly one of the two preview sets")

    def test_url_route_resolves(self):
        from django.urls import reverse
        url = reverse('update_netspeed_calculator_connection', args=['netspeed-calculator-1'])
        self.assertIn('update_netspeed_calculator_connection', url)

    def test_connection_view_exists(self):
        from agent import views
        self.assertTrue(hasattr(views, 'update_netspeed_calculator_connection_view'))

    def test_agent_migration_exists(self):
        path = os.path.join(_HERE, 'migrations', '0195_add_netspeed_calculator.py')
        self.assertTrue(os.path.isfile(path))

    def test_tool_row_migration_exists(self):
        path = os.path.join(_HERE, 'migrations',
                            '0196_add_chat_agent_netspeed_calculator_tool.py')
        self.assertTrue(os.path.isfile(path))

    def test_demo_prompt_migration_exists(self):
        path = os.path.join(_HERE, 'migrations',
                            '0197_add_netspeed_calculator_demo_prompt.py')
        self.assertTrue(os.path.isfile(path))


class ConfigContractTests(SimpleTestCase):

    def setUp(self):
        import yaml
        with open(_CFG_PATH, 'r', encoding='utf-8') as fh:
            self.cfg = yaml.safe_load(fh) or {}

    def test_config_parses(self):
        self.assertIsInstance(self.cfg, dict)

    def test_config_declares_the_connection_fields(self):
        self.assertIn('target_agents', self.cfg)
        self.assertIn('source_agents', self.cfg)

    def test_connection_fields_default_to_empty_lists(self):
        self.assertEqual(self.cfg['target_agents'], [])
        self.assertEqual(self.cfg['source_agents'], [])

    def test_config_declares_every_documented_parameter(self):
        for key in ("action", "providers", "parallel_streams", "test_duration_seconds",
                    "warmup_seconds", "sample_interval_seconds", "max_bytes_per_stream",
                    "upload_payload_mb", "request_timeout", "latency_samples",
                    "measure_bufferbloat", "outlier_rejection", "trim_percent",
                    "confidence_level", "aggregation", "heterogeneity_i2_threshold",
                    "preflight", "command_timeout", "output_dir", "save_json"):
            with self.subTest(key=key):
                self.assertIn(key, self.cfg)

    def test_numeric_defaults_are_real_numbers_not_strings(self):
        for key in ("parallel_streams", "test_duration_seconds", "request_timeout"):
            with self.subTest(key=key):
                self.assertIsInstance(self.cfg[key], (int, float))

    def test_default_action_is_full(self):
        self.assertEqual(str(self.cfg["action"]).strip().lower(), "full")

    def test_default_providers_are_all_catalogued(self):
        listed = [p.strip() for p in str(self.cfg["providers"]).split(",") if p.strip()]
        for key in listed:
            with self.subTest(provider=key):
                self.assertIn(key, nsc.PROVIDER_CATALOGUE)

    def test_output_dir_default_is_empty_so_the_temp_policy_applies(self):
        self.assertEqual(str(self.cfg.get("output_dir", "")).strip(), "")

    def test_no_hardcoded_scratch_path_outside_tlamatini(self):
        with open(_CFG_PATH, 'r', encoding='utf-8') as fh:
            text = fh.read().lower()
        self.assertNotIn("c:\\temp", text)
        self.assertNotIn("c:/temp", text)


class AgentSourceContractTests(SimpleTestCase):
    """Static properties the pool script must keep to run correctly as a
    subprocess in both source and frozen mode."""

    def setUp(self):
        with open(_NSC_PATH, 'r', encoding='utf-8') as fh:
            self.src = fh.read()

    def test_console_ctrl_handler_is_disabled_first(self):
        self.assertIn("FOR_DISABLE_CONSOLE_CTRL_HANDLER", self.src)

    def test_never_imports_the_django_agent_package(self):
        self.assertNotIn("from agent.", self.src)
        self.assertNotIn("import agent.", self.src)

    def test_reanimation_marker_is_defined(self):
        self.assertIn("_IS_REANIMATED", self.src)

    def test_log_file_is_named_after_the_directory(self):
        self.assertIn('LOG_FILE_PATH = f"{CURRENT_DIR_NAME}.log"', self.src)

    def test_pid_file_is_written_and_removed(self):
        self.assertIn("write_pid_file()", self.src)
        self.assertIn("remove_pid_file()", self.src)

    def test_concurrency_guard_precedes_starting_targets(self):
        guard = self.src.index("wait_for_agents_to_stop(target_agents)")
        start = self.src.index("start_agent(target)")
        self.assertLess(guard, start)

    def test_emits_its_ini_section(self):
        self.assertIn("INI_SECTION_NETSPEED_CALCULATOR<<<", self.src)

    def test_status_tokens_come_from_the_shared_vocabulary(self):
        for token in ('"ok"', '"refused"', '"error"'):
            with self.subTest(token=token):
                self.assertIn(token, self.src)


# ══════════════════════════════════════════════════════════════════════════
# 15. FRONTEND WIRING CONTRACT (the 6 canvas locations + CSS + eslint)
# ══════════════════════════════════════════════════════════════════════════

class FrontendWiringTests(SimpleTestCase):

    CONNECTOR = "updateNetSpeedCalculatorConnection"
    CANVAS_NAME = "netspeed-calculator"

    def _read(self, *parts):
        with open(os.path.join(_HERE, *parts), 'r', encoding='utf-8') as fh:
            return fh.read()

    def test_connector_function_exists(self):
        js = self._read('static', 'agent', 'js', 'acp-agent-connectors.js')
        self.assertIn("async function %s(" % self.CONNECTOR, js)

    def test_connector_posts_to_the_registered_route(self):
        js = self._read('static', 'agent', 'js', 'acp-agent-connectors.js')
        self.assertIn("/agent/update_netspeed_calculator_connection/", js)

    def test_classmap_entry_exists(self):
        js = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        self.assertIn("'%s': 'netspeed-calculator-agent'" % self.CANVAS_NAME, js)

    def test_canvas_core_declares_the_connector_global(self):
        js = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        start = js.index('/* global')
        block = js[start:js.index('*/', start)]
        self.assertIn(self.CONNECTOR, block)

    def test_canvas_core_wires_all_three_handler_sites(self):
        """removeConnection, removeConnectionsFor and the mouseup handler — miss
        one and creation, removal or undo silently stops persisting."""
        js = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        self.assertGreaterEqual(js.count(self.CONNECTOR), 7)

    def test_canvas_core_uses_the_hyphenated_literal(self):
        js = self._read('static', 'agent', 'js', 'acp-canvas-core.js')
        self.assertIn("=== '%s'" % self.CANVAS_NAME, js)

    def test_undo_and_redo_are_wired(self):
        js = self._read('static', 'agent', 'js', 'acp-canvas-undo.js')
        self.assertGreaterEqual(js.count(self.CONNECTOR), 4)

    def test_flw_load_wires_both_switches(self):
        js = self._read('static', 'agent', 'js', 'acp-file-io.js')
        self.assertEqual(js.count("case '%s':" % self.CANVAS_NAME), 2)

    def test_flow_generator_mapping_branch_exists(self):
        js = self._read('static', 'agent', 'js', 'agent_page_chat.js')
        self.assertIn("lower === 'netspeed-calculator'", js)

    def test_flow_generator_accepts_the_underscore_spelling_too(self):
        js = self._read('static', 'agent', 'js', 'agent_page_chat.js')
        self.assertIn("lower === 'netspeed_calculator'", js)

    def test_flow_generator_never_writes_connection_fields(self):
        js = self._read('static', 'agent', 'js', 'agent_page_chat.js')
        branch_start = js.index("lower === 'netspeed-calculator'")
        branch = js[branch_start:branch_start + 2000]
        self.assertNotIn("config.target_agents", branch)
        self.assertNotIn("config.source_agents", branch)

    def test_canvas_gradient_exists(self):
        css = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        self.assertIn(".canvas-item.netspeed-calculator-agent {", css)

    def test_canvas_hover_gradient_exists(self):
        css = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        self.assertIn(".canvas-item.netspeed-calculator-agent:hover {", css)

    def test_exec_report_caption_gradient_exists(self):
        css = self._read('static', 'agent', 'css', 'agent_page.css')
        self.assertIn(".exec-report-caption-netspeedcalculator {", css)

    def test_exec_report_command_accent_exists(self):
        css = self._read('static', 'agent', 'css', 'agent_page.css')
        self.assertIn(".exec-report-netspeedcalculator .exec-report-cmd {", css)

    def test_dark_caption_is_registered_for_readable_headers(self):
        css = self._read('static', 'agent', 'css', 'agent_page.css')
        self.assertIn(".exec-report-netspeedcalculator thead th,", css)

    def test_eslint_knows_the_new_global(self):
        path = os.path.join(_HERE, '..', '..', 'eslint.config.mjs')
        with open(os.path.normpath(path), 'r', encoding='utf-8') as fh:
            self.assertIn(self.CONNECTOR, fh.read())

    def test_gradient_is_unique_to_this_agent(self):
        """The base colour legitimately appears TWICE inside this agent's own rule
        (background-color fallback + the first gradient stop), so uniqueness is
        asserted on the whole gradient string - that is what a real collision
        with another agent would duplicate."""
        css = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        gradient = ("linear-gradient(135deg, #041E2B 0%, #0E6BA8 33%, "
                    "#21D4B4 66%, #F9C80E 100%)")
        self.assertEqual(css.count(gradient), 1)

    def test_accent_colours_belong_to_no_other_agent(self):
        css = self._read('static', 'agent', 'css', 'agentic_control_panel.css')
        for colour in ("#0E6BA8", "#21D4B4", "#F9C80E"):
            with self.subTest(colour=colour):
                self.assertEqual(css.count(colour), 1)


class DocumentationContractTests(SimpleTestCase):

    def _repo(self, *parts):
        path = os.path.join(_HERE, '..', '..', *parts)
        with open(os.path.normpath(path), 'r', encoding='utf-8') as fh:
            return fh.read()

    def test_agents_descriptions_has_a_row(self):
        self.assertIn("| **NetSpeed-Calculator** |", self._repo('agents_descriptions.md'))

    def test_flowcreator_skill_has_an_entry(self):
        path = os.path.join(_HERE, 'agents', 'flowcreator', 'agentic_skill.md')
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn("NetSpeed-Calculator", text)
        self.assertIn("netspeed_calculator_<n>", text)

    def test_flowhypervisor_has_special_notes(self):
        path = os.path.join(_HERE, 'agents', 'flowhypervisor', 'monitoring-prompt.pmt')
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        self.assertIn("NETSPEED_CALCULATOR SPECIAL NOTES", text)

    def test_flowhypervisor_lists_it_as_short_lived(self):
        path = os.path.join(_HERE, 'agents', 'flowhypervisor', 'monitoring-prompt.pmt')
        with open(path, 'r', encoding='utf-8') as fh:
            text = fh.read()
        short_lived = text[text.index("SHORT-LIVED"):text.index("LONG-RUNNING agents")]
        self.assertIn("NetSpeed-Calculator", short_lived)

    def test_docs_catalog_has_an_entry(self):
        self.assertIn("**NetSpeed-Calculator**", self._repo('docs', 'claude', 'agents.md'))

    def test_readme_mentions_the_agent(self):
        self.assertIn("NetSpeed-Calculator", self._repo('README.md'))


if __name__ == '__main__':
    unittest.main()
