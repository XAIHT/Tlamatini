"""Non-inferiority statistics for the Spanish/English parity claim.

REFERENCE IMPLEMENTATION -- not wired into Tlamatini. See PAPER.md section 9.

WHAT THIS IS FOR
----------------
Proving "the Spanish build is as effective as the English build" is a
NON-INFERIORITY claim, not an equality test. Reporting "p > 0.05, therefore no
difference" is the single most common defect in bilingual evaluations, and it
is perversely incentivised: a smaller, noisier study is MORE likely to look
like parity. Under the framing implemented here, a small study produces a wide
interval whose lower bound falls below the margin and correctly FAILS.

    H0: delta <= -margin      versus      H1: delta > -margin
    delta = theta_ES - theta_EN,  one-sided alpha = 0.05

Parity is claimed only if the lower bound of the one-sided 95% CI exceeds
-margin.

A CATEGORY ERROR THIS MODULE REFUSES TO COMMIT
----------------------------------------------
McNemar's test -- exact, mid-p or asymptotic -- tests H0: delta = 0. It CANNOT
test a margin. It is provided here as a companion equality test and is
explicitly NOT used for the parity decision. The margin test is Tango's (1998)
efficient-score confidence interval for the paired difference of proportions.

Rather than transcribe Yang et al.'s (2013) non-iterative closed form -- which
must be copied byte-perfectly or it silently returns a wrong interval -- this
implementation solves the constrained maximum-likelihood problem numerically.
The profile log-likelihood in p21 is strictly concave on its domain, so a
bisection on the derivative is exact to machine precision and is auditable:

    L(t) = n21*ln(t) + n12*ln(t - d) + (n11 + n22)*ln(1 - 2t + d) + const
    L'(t) = n21/t + n12/(t - d) - 2*(n11 + n22)/(1 - 2t + d)

with p21 = t, p12 = t - d, and the score statistic

    T(d) = (n21 - n12 - N*d) / sqrt(N * (2*t~ - d - d^2))

whose variance term is Var(X21 - X12) = N*(p21 + p12 - delta^2).

Stdlib only: math, random, statistics, dataclasses.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from statistics import NormalDist
from typing import Callable, List, Sequence, Tuple

__all__ = [
    "PairedTable",
    "NonInferiorityResult",
    "tango_score_ci",
    "mcnemar_midp",
    "noninferiority_paired",
    "bca_bootstrap_ci",
    "n_pairs_required",
    "n_unpaired_required",
    "benjamini_hochberg",
]

_ND = NormalDist()
_EPS = 1e-12


# ---------------------------------------------------------------------------
# Paired binary data
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PairedTable:
    """2x2 discordance table for the SAME task run in both languages.

    n11 both succeed | n21 ES ok & EN fail | n12 ES fail & EN ok | n22 both fail
    """

    n11: int
    n21: int
    n12: int
    n22: int

    @property
    def n(self) -> int:
        return self.n11 + self.n21 + self.n12 + self.n22

    @property
    def delta_hat(self) -> float:
        return (self.n21 - self.n12) / max(self.n, 1)

    @property
    def discordant(self) -> int:
        return self.n21 + self.n12

    @classmethod
    def from_pairs(cls, es: Sequence[int], en: Sequence[int]) -> "PairedTable":
        if len(es) != len(en):
            raise ValueError("paired arms must have equal length")
        n11 = sum(1 for a, b in zip(es, en) if a and b)
        n21 = sum(1 for a, b in zip(es, en) if a and not b)
        n12 = sum(1 for a, b in zip(es, en) if not a and b)
        n22 = sum(1 for a, b in zip(es, en) if not a and not b)
        return cls(n11, n21, n12, n22)


def _constrained_p21(tbl: PairedTable, d: float) -> float:
    """Constrained MLE of p21 given delta = d, by bisection on L'(t).

    Domain: t in (max(0, d), (1 + d) / 2). L' is strictly decreasing there, so
    the root is unique. Boundary cases (no discordant pairs) clamp.
    """
    n = tbl.n
    if n == 0:
        return 0.0
    lo = max(0.0, d) + _EPS
    hi = (1.0 + d) / 2.0 - _EPS
    if hi <= lo:
        return max(lo, 0.0)

    k = tbl.n11 + tbl.n22

    def deriv(t: float) -> float:
        val = 0.0
        if tbl.n21:
            val += tbl.n21 / t
        if tbl.n12:
            val += tbl.n12 / (t - d)
        if k:
            val -= 2.0 * k / (1.0 - 2.0 * t + d)
        return val

    f_lo, f_hi = deriv(lo), deriv(hi)
    if f_lo <= 0.0:
        return lo
    if f_hi >= 0.0:
        return hi
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if deriv(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _score_stat(tbl: PairedTable, d: float) -> float:
    """Tango's efficient-score statistic at delta = d. Decreasing in d."""
    n = tbl.n
    if n == 0:
        return 0.0
    t = _constrained_p21(tbl, d)
    var = n * (2.0 * t - d - d * d)
    if var <= _EPS:
        var = _EPS
    return (tbl.n21 - tbl.n12 - n * d) / math.sqrt(var)


def tango_score_ci(
    tbl: PairedTable, alpha: float = 0.05, one_sided: bool = True
) -> Tuple[float, float]:
    """Tango score CI for the paired difference of proportions.

    ``one_sided=True`` returns the one-sided (1 - alpha) interval, i.e. the
    lower bound to compare against -margin. That is equivalent to the lower
    bound of the two-sided (1 - 2*alpha) interval, which is exactly the CONSORT
    non-inferiority convention.
    """
    if tbl.n == 0:
        return (-1.0, 1.0)
    z = _ND.inv_cdf(1.0 - alpha) if one_sided else _ND.inv_cdf(1.0 - alpha / 2.0)
    d_hat = tbl.delta_hat

    def _root(target: float, lo: float, hi: float) -> float:
        # _score_stat is decreasing in d, so g(d) = T(d) - target is decreasing.
        for _ in range(200):
            mid = 0.5 * (lo + hi)
            if _score_stat(tbl, mid) - target > 0.0:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    lower = _root(z, -1.0 + 1e-9, d_hat)
    upper = _root(-z, d_hat, 1.0 - 1e-9) if not one_sided else 1.0
    return (lower, upper)


def mcnemar_midp(tbl: PairedTable) -> float:
    """Two-sided mid-p McNemar p-value. TESTS EQUALITY, NOT A MARGIN.

    Reported alongside the Tango interval as a companion. Fagerland, Lydersen &
    Laake (2013) show the exact conditional test is markedly over-conservative
    and that mid-p dominates it.
    """
    b, c = tbl.n21, tbl.n12
    m = b + c
    if m == 0:
        return 1.0
    lo = min(b, c)
    cum = sum(math.comb(m, i) for i in range(lo + 1)) * (0.5 ** m)
    exact = min(1.0, 2.0 * cum)
    point = math.comb(m, b) * (0.5 ** m)
    return max(0.0, exact - point)


@dataclass(frozen=True)
class NonInferiorityResult:
    delta_hat: float
    lower_bound: float
    margin: float
    non_inferior: bool
    n_pairs: int
    discordant: int
    mcnemar_midp_p: float
    note: str


def noninferiority_paired(
    tbl: PairedTable, margin: float = 0.05, alpha: float = 0.05
) -> NonInferiorityResult:
    """The parity decision. Non-inferior iff CI lower bound > -margin."""
    lower, _ = tango_score_ci(tbl, alpha=alpha, one_sided=True)
    note = ""
    if tbl.discordant < 25:
        note = (
            f"WARNING: only {tbl.discordant} discordant pairs. Below ~25 the "
            "asymptotics are unreliable; the interval is wide and the claim "
            "rests on the score method's small-sample behaviour."
        )
    return NonInferiorityResult(
        delta_hat=round(tbl.delta_hat, 5),
        lower_bound=round(lower, 5),
        margin=margin,
        non_inferior=lower > -margin,
        n_pairs=tbl.n,
        discordant=tbl.discordant,
        mcnemar_midp_p=round(mcnemar_midp(tbl), 5),
        note=note,
    )


# ---------------------------------------------------------------------------
# BCa bootstrap for paired CONTINUOUS scores
# ---------------------------------------------------------------------------


def bca_bootstrap_ci(
    pairs: Sequence[Tuple[float, float]],
    statistic: Callable[[Sequence[Tuple[float, float]]], float] | None = None,
    alpha: float = 0.05,
    n_boot: int = 10000,
    seed: int = 1729,
) -> Tuple[float, float, float]:
    """BCa CI for a paired continuous endpoint, resampling ITEM PAIRS.

    Resampling individual observations instead of pairs destroys the pairing
    the whole design exists to exploit and inflates the variance back to the
    unpaired case -- so this function only ever resamples pair indices.

    Default statistic: mean of within-pair differences (ES minus EN).
    Returns ``(point, lower, upper)``.
    """
    if statistic is None:
        def statistic(sample):  # type: ignore[misc]
            return sum(a - b for a, b in sample) / max(len(sample), 1)

    n = len(pairs)
    if n < 3:
        pt = statistic(pairs) if n else 0.0
        return (pt, float("-inf"), float("inf"))

    rng = random.Random(seed)
    theta_hat = statistic(pairs)

    boots: List[float] = []
    for _ in range(n_boot):
        sample = [pairs[rng.randrange(n)] for _ in range(n)]
        boots.append(statistic(sample))
    boots.sort()

    # Bias correction.
    n_less = sum(1 for b in boots if b < theta_hat)
    prop = min(max(n_less / n_boot, 1.0 / (2 * n_boot)), 1.0 - 1.0 / (2 * n_boot))
    z0 = _ND.inv_cdf(prop)

    # Acceleration: leave-one-PAIR-out jackknife.
    jack = [statistic(pairs[:i] + pairs[i + 1:]) for i in range(n)]
    jbar = sum(jack) / n
    num = sum((jbar - j) ** 3 for j in jack)
    den = 6.0 * (sum((jbar - j) ** 2 for j in jack) ** 1.5)
    a = num / den if abs(den) > _EPS else 0.0

    def _endpoint(p: float) -> float:
        zp = _ND.inv_cdf(p)
        adj = z0 + (z0 + zp) / max(1.0 - a * (z0 + zp), _EPS)
        q = min(max(_ND.cdf(adj), 0.0), 1.0)
        idx = int(q * (n_boot - 1))
        return boots[max(0, min(n_boot - 1, idx))]

    return (theta_hat, _endpoint(alpha), _endpoint(1.0 - alpha))


# ---------------------------------------------------------------------------
# Planning
# ---------------------------------------------------------------------------


def n_pairs_required(
    p_discordant: float,
    margin: float = 0.05,
    assumed_delta: float = 0.0,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """Paired sample size. Driven by the DISCORDANCE rate, not the base rate.

    n = (z_{1-a} + z_{1-b})^2 * (p_d - delta^2) / (margin + delta)^2
    """
    z = _ND.inv_cdf(1.0 - alpha) + _ND.inv_cdf(power)
    denom = (margin + assumed_delta) ** 2
    if denom <= 0:
        raise ValueError("margin + assumed_delta must be positive")
    num = max(p_discordant - assumed_delta ** 2, _EPS)
    return math.ceil(z * z * num / denom)


def n_unpaired_required(
    p_en: float = 0.85,
    p_es: float | None = None,
    margin: float = 0.05,
    assumed_delta: float = 0.0,
    alpha: float = 0.05,
    power: float = 0.80,
) -> int:
    """Per-arm sample size for the UNPAIRED design (the sanity-check baseline)."""
    p_es = p_en + assumed_delta if p_es is None else p_es
    z = _ND.inv_cdf(1.0 - alpha) + _ND.inv_cdf(power)
    var = p_es * (1 - p_es) + p_en * (1 - p_en)
    denom = (margin - abs(assumed_delta)) ** 2
    if denom <= 0:
        raise ValueError("margin must exceed the assumed true difference")
    return math.ceil(z * z * var / denom)


def benjamini_hochberg(pvalues: Sequence[float], q: float = 0.10) -> List[bool]:
    """BH FDR control. NOTE the direction: in a non-inferiority framing the
    'discovery' whose false rate is bounded is THE PARITY CLAIM ITSELF."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: pvalues[i])
    k_max = -1
    for rank, idx in enumerate(order, start=1):
        if pvalues[idx] <= (rank / m) * q:
            k_max = rank
    out = [False] * m
    for rank, idx in enumerate(order, start=1):
        if rank <= k_max:
            out[idx] = True
    return out


# ---------------------------------------------------------------------------
# Self-check
# ---------------------------------------------------------------------------


def _demo() -> None:  # pragma: no cover - developer aid
    print("--- PLANNING (PAPER.md section 9.4) ---")
    print(f"  unpaired per arm, delta=0, margin=0.05 : "
          f"{n_unpaired_required()}   (expect 631)")
    for rho in (0.0, 0.6, 0.7, 0.8):
        p_d = 0.255 * (1 - rho)
        n = n_pairs_required(p_d)
        print(f"  rho={rho:<4} p_d={p_d:.3f} -> n_pairs={n:<5} "
              f"expected discordant m={round(n * p_d)}")

    print("\n--- THE PARITY DECISION (margin = 0.05) ---")
    scenarios = [
        ("true parity, well powered",  PairedTable(n11=200, n21=13, n12=12, n22=25)),
        ("underpowered, looks equal",  PairedTable(n11=20,  n21=2,  n12=2,  n22=6)),
        ("Spanish clearly worse",      PairedTable(n11=180, n21=5,  n12=40, n22=25)),
        ("Spanish slightly better",    PairedTable(n11=205, n21=20, n12=10, n22=15)),
    ]
    for label, tbl in scenarios:
        r = noninferiority_paired(tbl, margin=0.05)
        verdict = "PARITY CLAIMED" if r.non_inferior else "NOT NON-INFERIOR"
        print(f"  {label:<28} n={r.n_pairs:<4} d_hat={r.delta_hat:+.4f} "
              f"lower={r.lower_bound:+.4f}  {verdict}")
        print(f"       mid-p McNemar (EQUALITY, not the parity test) = "
              f"{r.mcnemar_midp_p}")
        if r.note:
            print(f"       {r.note}")

    print("\n  Note scenario 2: d_hat is EXACTLY 0.0 and the naive equality")
    print("  test returns p = 0.63 -- 'no significant difference', which is")
    print("  how an underpowered study gets spun as parity. Non-inferiority")
    print("  correctly REFUSES the claim: the lower bound is -0.13, far below")
    print("  the -0.05 margin, because 30 pairs cannot exclude a real deficit.")

    print("\n--- BCa on a paired continuous endpoint (plan length) ---")
    rng = random.Random(7)
    pairs = [(rng.gauss(3.4, 1.0), rng.gauss(3.2, 1.0)) for _ in range(120)]
    pt, lo, hi = bca_bootstrap_ci(pairs, n_boot=4000)
    print(f"  mean paired difference = {pt:+.3f}  BCa 90% CI [{lo:+.3f}, {hi:+.3f}]")

    print("\n--- BH FDR over an exploratory grid ---")
    pvals = [0.001, 0.008, 0.02, 0.04, 0.11, 0.30, 0.55, 0.90]
    print(f"  q=0.10 rejections: {benjamini_hochberg(pvals, 0.10)}")


if __name__ == "__main__":  # pragma: no cover
    _demo()
