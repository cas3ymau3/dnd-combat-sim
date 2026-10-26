"""
statistics.py — the uncertainty layer (evaluation_framework.md §6.2).

**Every scalar carries ``(value, n, stderr, converged)`` — not just DPR.**  Metrics
converge at wildly different rates: DPR is fast, but rare events (concentration
breaks, control failures against a high-save build) can be badly under-converged at
a day count that looks generous for DPR.  A report that shows a noisy rare-event
number without an interval invites over-reading it, so the interval is not optional
and neither is the convergence verdict.

The estimator, in one idea
--------------------------
Every metric is a RATIO: a per-day numerator over a denominator, with the
adventuring DAY as the independent replicate.  Two kinds, differing only in whether
the denominator is itself random:

* **fixed denominator** — DPR's denominator is ``rounds_per_day`` (16), identical
  every day.  Then ``v_d = y_d / 16`` is an i.i.d. sample and the estimate is a
  plain mean with ``se = sd(v)/sqrt(N)``.
* **random denominator** — a fail RATE's denominator is "saves actually forced
  today", which varies and is *correlated* with the numerator (a day forcing more
  saves also fails more).  The estimate is ratio-of-means ``r = Σy / Σx``, whose
  standard error comes from the delta-method linearization — the classic survey
  ratio estimator (Cochran; ``survey::svyratio`` in R).

Not two theories — one.  Both are ``se = sd(infl)/sqrt(N)`` over the per-day
INFLUENCE VALUES::

    infl_d = (y_d - r * x_d) / mean(x)

Substituting a constant ``x_d ≡ D`` gives ``infl_d = y_d/D - r = v_d - mean(v)``, so
the fixed case is a special case of the random one, not a rival to it.

Why two code paths then?  **Floating-point exactness only.**  ``sd(y)/D/sqrt(N)``
and ``sd(y/D)/sqrt(N)`` are algebraically identical but take different rounding
paths, and §12's parity proof asserts BIT-IDENTICAL floats against
``validation.run_level``.  :func:`fixed_estimate` therefore mirrors that function's
exact operation order (``sum(v)/n``; ``sum((v-mean)**2)/(n-1)``; ``sqrt(var/n)``).
Declaring which kind a metric uses is also information the reader wants: "per 16
rounds, always" is a different claim from "per save actually forced".

Two honest limits, both surfaced rather than hidden:

* the delta method is first-order and asymptotic in N, so it is optimistic when few
  events were observed — which is exactly what :class:`Convergence`'s ``min_events``
  guard exists to catch;
* when ``Σx == 0`` the ratio has NO value.  It is reported as ``None`` with a note,
  never as ``0.0`` — a zero would read as a measured result (the same honesty rule
  §5.2 applies to mixed-mode comparison).

Why influence values are worth the concept
------------------------------------------
They make §6.1's paired comparison exact and uniform: the paired delta's standard
error is ``sd(inflA - inflB)/sqrt(N)``, which for DPR collapses to
``sd(vA - vB)/sqrt(N)`` — the textbook common-random-numbers result — and stays
correct for ratio metrics where a naive per-day difference is not even defined.
"""

from __future__ import annotations

import hashlib
import math
from array import array
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

def _new_samples() -> "array[float]":
    """A fresh per-day sample column.

    ``array("d")`` rather than ``list[float]``: a publication-tier run (§10:
    200,000 days) times ~30 registered metrics times three columns is tens of
    millions of numbers — 8 bytes each in an array, roughly 32 with Python float
    objects.  That is the difference between a run that fits in memory and one
    that does not.
    """
    return array("d")


# ---------------------------------------------------------------------------
# The value type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricValue:
    """One metric's estimate for one run — §6.2's ``(value, n, stderr, converged)``.

    Attributes
    ----------
    value:
        ``None`` means NOT MEASURED, never "measured as zero".  Two distinct
        causes, both explained by ``note``: the metric is unavailable for this run
        (:attr:`available` is False), or its denominator summed to zero.
    n:
        Independent replicates — adventuring days.
    stderr:
        Standard error of :attr:`value`.  ``None`` whenever ``value`` is.
    converged:
        The metric's OWN declared heuristic (:class:`Convergence`), read from the
        registry.  A metric is never converged when it has no value.
    n_events:
        The metric's declared event count, summed over the run — what the
        ``min_events`` guard reads.  For a metric that declares no event count this
        is the day count, so the guard degenerates to "enough days".
    available:
        False when the run structurally cannot produce this metric (§3.4: the
        channel is not wired, or this build's enemy model has no such channel).
        Distinguishing this from a measured zero is the point — a silent zero for
        control resilience reads as "this build resists control perfectly".
    """

    metric: str
    value: "float | None"
    n: int
    stderr: "float | None"
    converged: bool
    n_events: float = 0.0
    available: bool = True
    note: str = ""

    @property
    def measured(self) -> bool:
        """True when the run produced an actual number."""
        return self.value is not None

    def ci95(self) -> "tuple[float, float] | None":
        """Normal-approximation 95% interval, or ``None`` if not measured."""
        if self.value is None or self.stderr is None:
            return None
        half = 1.96 * self.stderr
        return (self.value - half, self.value + half)

    @classmethod
    def unavailable(cls, metric: str, reason: str, n: int = 0) -> "MetricValue":
        """The honest declaration for a metric this run cannot produce (§3.4)."""
        return cls(metric=metric, value=None, n=n, stderr=None, converged=False,
                   n_events=0.0, available=False, note=reason)


# ---------------------------------------------------------------------------
# Convergence — a DECLARED heuristic, living in the registry (§6.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Convergence:
    """When a metric's estimate is precise enough to read at face value.

    Declared per metric in the registry, not applied globally, because the whole
    point of §6.2 is that metrics converge at wildly different rates.

    Parameters
    ----------
    rel_stderr:
        Standard error as a fraction of the estimate must be at or below this.
    min_events:
        Minimum observed events (the metric's declared event count).  This is the
        guard that keeps a rare-event metric honest: a fail rate estimated off six
        saves can show a small relative stderr by luck, and the delta method is
        optimistic in exactly that regime.
    min_days:
        Minimum replicates.  A stderr from a handful of days is not trustworthy
        regardless of what it says about itself.
    """

    rel_stderr: float = 0.02
    min_events: float = 0.0
    min_days: int = 100

    def check(self, value: "float | None", stderr: "float | None",
              n: int, n_events: float) -> bool:
        """The verdict.  Not measured → never converged."""
        if value is None or stderr is None:
            return False
        if n < self.min_days or n_events < self.min_events:
            return False
        if value == 0.0:
            # A relative criterion is undefined at zero.  Only an EXACTLY zero
            # standard error (every day agreed) counts as converged; otherwise the
            # estimate is a noisy number straddling zero and must say so.
            return stderr == 0.0
        return abs(stderr / value) <= self.rel_stderr

    def describe(self) -> dict:
        return {"rel_stderr": self.rel_stderr, "min_events": self.min_events,
                "min_days": self.min_days}


#: The default for a fast-converging ledger metric like DPR.
DEFAULT_CONVERGENCE = Convergence()

#: For rare events: the relative-stderr bar relaxes (you will not get 2% on a
#: concentration break rate at any realistic day count) but a hard floor on the
#: number of observed events replaces it.
RARE_EVENT_CONVERGENCE = Convergence(rel_stderr=0.10, min_events=200.0)


# ---------------------------------------------------------------------------
# The estimators
# ---------------------------------------------------------------------------

def fixed_estimate(numerators: Iterable[float],
                   denominator_per_day: Iterable[float]) -> "tuple[float | None, float | None, list[float]]":
    """Plain mean of ``v_d = y_d / x_d`` where ``x_d`` is the same every day.

    Returns ``(value, stderr, influence_values)``.

    The operation order here is load-bearing and must not be "simplified": it
    mirrors ``validation.run_level`` exactly (``sum(v)/n``; ``sum((v-mean)**2)/(n-1)``;
    ``sqrt(var/n)``) so the §12 parity proof compares bit-identical floats.  Any
    algebraically-equivalent rearrangement can differ in the last ULP.
    """
    values = [y / x for y, x in zip(numerators, denominator_per_day)]
    n = len(values)
    if n == 0:
        return None, None, []
    mean = sum(values) / n
    var = sum((x - mean) ** 2 for x in values) / (n - 1) if n > 1 else 0.0
    stderr = math.sqrt(var / n) if n > 1 else 0.0
    # Influence values for a fixed denominator are the centered per-day values;
    # computed this way (not as (y - r*x)/x) so a paired delta on DPR reduces to
    # sd(vA - vB)/sqrt(N) with the same rounding path as the stderr above.
    return mean, stderr, [v - mean for v in values]


def ratio_estimate(numerators: Iterable[float],
                   denominators: Iterable[float]) -> "tuple[float | None, float | None, list[float]]":
    """Ratio-of-means with the delta-method standard error (Cochran's ratio estimator).

    Returns ``(value, stderr, influence_values)``.  ``(None, None, [])`` when the
    denominator sums to zero — the ratio genuinely has no value, and reporting
    ``0.0`` would be a fabricated measurement.

    ``r = Σy / Σx``; ``infl_d = (y_d - r·x_d) / mean(x)``; ``se = sd(infl)/sqrt(N)``.
    Weighting each EVENT equally (rather than each day) is what makes this the
    quantity a rate is supposed to name.
    """
    ys = list(numerators)
    xs = list(denominators)
    n = len(ys)
    if n == 0:
        return None, None, []
    total_x = sum(xs)
    if total_x == 0.0:
        return None, None, []
    ratio = sum(ys) / total_x
    mean_x = total_x / n
    influence = [(y - ratio * x) / mean_x for y, x in zip(ys, xs)]
    if n > 1:
        # mean(influence) is 0 by construction, so the centered sum of squares is
        # the raw one up to floating-point noise; subtracting the computed mean
        # keeps it exact rather than nearly so.
        m = sum(influence) / n
        var = sum((v - m) ** 2 for v in influence) / (n - 1)
        stderr = math.sqrt(var / n)
    else:
        stderr = 0.0
    return ratio, stderr, influence


# ---------------------------------------------------------------------------
# Per-metric sample collection
# ---------------------------------------------------------------------------

@dataclass
class MetricSamples:
    """The per-day columns one metric needs, accumulated during a run.

    Kept as raw per-day samples rather than running sums because §6.1's paired
    comparison needs to line day ``d`` of run A up against day ``d`` of run B —
    a running-sums accumulator would collapse exactly the information that makes
    common random numbers worth having.
    """

    metric: str
    fixed_denominator: bool
    numerator: "array[float]" = field(default_factory=_new_samples)
    denominator: "array[float]" = field(default_factory=_new_samples)
    events: "array[float]" = field(default_factory=_new_samples)

    def record(self, numerator: float, denominator: float, events: float) -> None:
        self.numerator.append(float(numerator))
        self.denominator.append(float(denominator))
        self.events.append(float(events))

    @property
    def n(self) -> int:
        return len(self.numerator)

    def per_day_values(self) -> "list[float]":
        """``v_d = y_d / x_d`` — the per-day column §5.4's third kind describes.

        Defined ONLY for a fixed denominator, and the refusal is the point rather
        than a limitation: with a random denominator there is no per-day value to
        take a quantile of.  A day that forced no saves has no fail rate, and
        dropping those days would quietly change the estimand from "the rate" to
        "the rate among days that had one".  :class:`DistributionDef` therefore
        refuses such a declaration at registration instead of leaving the trap for
        a caller to avoid.
        """
        if not self.fixed_denominator:
            raise ValueError(
                f"Metric {self.metric!r} has a RANDOM denominator, so it has no "
                f"per-day value: on a day whose denominator is zero the ratio is "
                f"undefined, not zero. A distribution over it is not a thing this "
                f"layer can honestly produce."
            )
        return [y / x for y, x in zip(self.numerator, self.denominator)]

    def estimate(self, convergence: Convergence) -> "tuple[MetricValue, list[float]]":
        """``(MetricValue, influence_values)`` for this metric.

        The influence values are returned alongside rather than stored on the
        value, so a serialized report (step 3) carries the estimate without
        carrying a per-day vector.
        """
        if self.fixed_denominator:
            value, stderr, influence = fixed_estimate(self.numerator, self.denominator)
            note = ""
        else:
            value, stderr, influence = ratio_estimate(self.numerator, self.denominator)
            note = "" if value is not None else (
                "denominator summed to zero across the run — the ratio has no value "
                "(reported as None rather than 0.0)"
            )
        n_events = float(sum(self.events))
        return (
            MetricValue(
                metric=self.metric,
                value=value,
                n=self.n,
                stderr=stderr,
                converged=convergence.check(value, stderr, self.n, n_events),
                n_events=n_events,
                available=True,
                note=note,
            ),
            influence,
        )


# ---------------------------------------------------------------------------
# Paired differences (§6.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PairedDelta:
    """``A - B`` for one metric under common random numbers.

    ``paired`` records whether the reported interval is the paired one.  It is
    False when the two runs have different day counts (nothing to pair day-wise),
    in which case ``stderr`` falls back to the independent ``sqrt(seA² + seB²)``
    and the note says so — §6.1 requires that a reader can tell which they are
    looking at, because a paired interval is typically far narrower.
    """

    metric: str
    delta: "float | None"
    stderr: "float | None"
    n: int
    paired: bool
    a: MetricValue
    b: MetricValue
    note: str = ""


def paired_delta(metric: str, a: MetricValue, influence_a: list[float],
                 b: MetricValue, influence_b: list[float]) -> PairedDelta:
    """The §6.1 paired difference.

    Under common random numbers the two runs share their dice stream wherever they
    have not diverged, so the shared noise cancels in the DIFFERENCE.  The
    linearized form is uniform across metric kinds::

        se(A - B) = sd(inflA_d - inflB_d) / sqrt(N)

    For a fixed-denominator metric this is exactly ``sd(vA - vB)/sqrt(N)``.  For a
    ratio metric a naive per-day difference is not even defined (a day may force no
    saves at all), whereas the influence-value form always is.
    """
    if a.value is None or b.value is None:
        missing = a if a.value is None else b
        return PairedDelta(metric=metric, delta=None, stderr=None, n=min(a.n, b.n),
                           paired=False, a=a, b=b,
                           note=f"no delta: {missing.metric} has no value "
                                f"({missing.note or 'unavailable'})")

    delta = a.value - b.value
    if len(influence_a) == len(influence_b) and len(influence_a) > 1:
        n = len(influence_a)
        diffs = [ia - ib for ia, ib in zip(influence_a, influence_b)]
        mean = sum(diffs) / n
        var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
        return PairedDelta(metric=metric, delta=delta, stderr=math.sqrt(var / n),
                           n=n, paired=True, a=a, b=b)

    stderr = None
    if a.stderr is not None and b.stderr is not None:
        stderr = math.sqrt(a.stderr ** 2 + b.stderr ** 2)
    return PairedDelta(
        metric=metric, delta=delta, stderr=stderr, n=min(a.n, b.n), paired=False,
        a=a, b=b,
        note="unpaired interval: the two runs have different day counts, so days "
             "cannot be matched up; sqrt(seA^2 + seB^2) is reported instead",
    )


# ---------------------------------------------------------------------------
# §5.4 kind 3 — DISTRIBUTIONS (the shape, not the average)
# ---------------------------------------------------------------------------
#
# Everything above estimates a MEAN and attaches a standard error.  That answers
# where the average lands and says nothing about consistency: two builds with the
# same mean DPR and very different day-to-day spread are indistinguishable in it.
#
# A quantile does not fit any of it.  It is not a ratio, so there is no
# linearization and no delta-method standard error, and the interval that IS
# available is ASYMMETRIC — two order statistics straddling the estimate, not
# ``value +/- 1.96*se``.  Hence a parallel set of types rather than a new flag on
# :class:`MetricValue`, whose ``ci95()`` would quietly symmetrize it.
#
# The one structural decision, and the analogue of ``Denominator.fixed`` selecting
# the estimator above: **the statistic selects the interval method.**  A quantile
# has an exact distribution-free interval in closed form, so it uses one and draws
# nothing.  An IQR has no closed form — its uncertainty needs the covariance of two
# quantiles, which is exactly what a consumer holding both cannot reconstruct — so
# it bootstraps.  Making that a caller's option would have invited a bootstrap
# where an exact answer was free.

#: Exact binomial order-statistic bounds.  Distribution-free, exact at every N,
#: and it draws nothing.
METHOD_ORDER_STATISTIC = "order_statistic"
#: Percentile bootstrap.  For a statistic with no closed-form interval.
METHOD_BOOTSTRAP = "bootstrap"

METHODS = (METHOD_ORDER_STATISTIC, METHOD_BOOTSTRAP)

#: Resamples for :data:`METHOD_BOOTSTRAP`.  2000 is the conventional floor for a
#: percentile interval; the cost is bounded by chunking (see :func:`bootstrap_interval`).
DEFAULT_RESAMPLES = 2000


def quantile(sorted_values: "list[float]", p: float) -> float:
    """The ``p``-quantile of an ALREADY SORTED sample, by linear interpolation.

    This is the type-7 definition — numpy's default and R's ``quantile()`` default.
    Matching the ecosystem default is the point: a reader who recomputes the median
    from the per-day column in R must get this number back, and a bespoke definition
    would make the artifact disagree with the obvious check.

    Implemented here rather than called out to numpy so the definition is visible at
    the one place the artifact's meaning is fixed; a test pins it against
    ``numpy.quantile``.
    """
    n = len(sorted_values)
    if n == 0:
        raise ValueError("quantile of an empty sample")
    if n == 1:
        return sorted_values[0]
    h = (n - 1) * p
    lo = int(math.floor(h))
    if lo >= n - 1:
        return sorted_values[-1]
    frac = h - lo
    return sorted_values[lo] + frac * (sorted_values[lo + 1] - sorted_values[lo])


def _binomial_ranks(n: int, p: float, alpha: float) -> "tuple[int | None, int | None]":
    """1-indexed order-statistic ranks ``(r, s)`` for a conservative CI on the
    ``p``-quantile, or ``None`` for an end that falls OFF the sample.

    The classical distribution-free construction: with ``B ~ Binomial(n, p)``,

        P(X_(r) <= xi_p <= X_(s)) = P(r <= B <= s-1)

    so taking ``r`` as the largest rank with ``P(B <= r-1) <= alpha/2`` and ``s`` as
    the smallest with ``P(B >= s) <= alpha/2`` gives coverage of at least
    ``1 - alpha``.  Conservative, never anti-conservative — the right direction for
    an interval a reader will take at face value.

    ``None`` is returned rather than a clamp.  At small N the lower bound for an
    extreme quantile wants ``X_(0)``, which does not exist; clamping it to the sample
    minimum would report a bound the data cannot support, which is the same class of
    dishonesty as writing 0 for an unmeasured metric (§3.4).

    The CDF is accumulated over a window of +/-10 standard deviations about the mode
    using log-space pmf terms (scipy is not a dependency).  Outside that window the
    mass is below 1e-20 and cannot move either rank; the window also degenerates to
    the whole support at the small N where that matters, so this is ONE code path
    rather than an exact-vs-approximate branch.
    """
    if n <= 0 or not (0.0 < p < 1.0):
        return None, None

    mean = n * p
    sd = math.sqrt(n * p * (1.0 - p))
    width = int(math.ceil(10.0 * sd)) + 10
    lo_k = max(0, int(mean) - width)
    hi_k = min(n, int(mean) + width + 1)

    log_p, log_q = math.log(p), math.log1p(-p)
    log_fact_n = math.lgamma(n + 1)
    half = alpha / 2.0

    lower: "int | None" = None       # largest k with F(k) <= alpha/2
    upper: "int | None" = None       # smallest k with F(k) >= 1 - alpha/2
    cumulative = 0.0
    for k in range(lo_k, hi_k + 1):
        log_pmf = (log_fact_n - math.lgamma(k + 1) - math.lgamma(n - k + 1)
                   + k * log_p + (n - k) * log_q)
        cumulative += math.exp(log_pmf)
        if cumulative <= half:
            lower = k
        if upper is None and cumulative >= 1.0 - half:
            upper = k

    r = (lo_k if lower is None else lower + 1)
    # `lower is None` means even F(lo_k) already exceeds alpha/2; with lo_k == 0 that
    # is the genuine off-the-end case, and with lo_k > 0 the truncated head carried
    # no mass, so rank lo_k is the first usable one.
    if lower is None and lo_k == 0:
        r = 0
    s = None if upper is None else upper + 1
    return (r if 1 <= r <= n else None), (s if s is not None and s <= n else None)


def order_statistic_interval(sorted_values: "list[float]", p: float, *,
                             alpha: float = 0.05) -> "tuple[tuple[float, float] | None, str]":
    """``((lo, hi), note)`` — the exact distribution-free interval for a quantile.

    ``(None, reason)`` when the sample is too small to place one end of it.  That is
    a real outcome at the day counts a 'quick' tier uses, not an error: a p90 off
    twenty days has no 95% upper bound inside the sample.
    """
    n = len(sorted_values)
    r, s = _binomial_ranks(n, p, alpha)
    if r is None or s is None:
        missing = "lower" if r is None else "upper"
        return None, (
            f"no 95% interval: with n={n} the {missing} order-statistic bound for the "
            f"p={p:g} quantile falls outside the sample. Reported without an interval "
            f"rather than clamped to the sample's extreme, which would assert a "
            f"precision the data does not have."
        )
    return (sorted_values[r - 1], sorted_values[s - 1]), ""


def _stable_seed(*parts: object) -> int:
    """A reproducible 64-bit seed from a label.

    ``hash()`` is salted per process (PYTHONHASHSEED), so an artifact's bootstrap
    interval would change between runs of the same report. SHA-256 of the joined
    label does not.
    """
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def bootstrap_interval(values: "Iterable[float]",
                       statistic: "Callable[[Any], Any]", *,
                       seed: int, resamples: int = DEFAULT_RESAMPLES,
                       alpha: float = 0.05) -> "tuple[tuple[float, float] | None, str]":
    """``((lo, hi), note)`` — the percentile bootstrap interval for ``statistic``.

    ``statistic`` is VECTORIZED: it receives a ``(resamples_in_chunk, n)`` array and
    returns one value per row.  Resampling row-wise in chunks keeps peak memory at a
    few tens of MB even at the §10 publication tier, where a single
    ``(2000, 200_000)`` index array would be 3 GB.

    **This function draws, and it draws from its OWN generator.**  Per-feature ritual
    step 3: every die in a run comes off one ``SeededRNG`` tape, so a single extra
    draw from it outside combat shifts every subsequent roll and kills §12's
    bit-identical parity proof against ``validation.run_level``.  A
    ``numpy.random.default_rng`` seeded from a stable hash of the caller's label is
    reproducible, independent, and structurally incapable of touching that tape.
    """
    import numpy as np

    arr = np.asarray(list(values), dtype=float)
    n = int(arr.size)
    if n < 2:
        return None, (
            f"no bootstrap interval: n={n} leaves nothing to resample. A bootstrap "
            f"estimates a sampling distribution from the sample's own variation, and "
            f"one observation has none."
        )

    generator = np.random.default_rng(seed)
    chunk = max(1, 4_000_000 // n)
    drawn = np.empty(resamples, dtype=float)
    done = 0
    while done < resamples:
        size = min(chunk, resamples - done)
        indices = generator.integers(0, n, size=(size, n))
        drawn[done:done + size] = statistic(arr[indices])
        done += size

    lo = float(np.quantile(drawn, alpha / 2.0))
    hi = float(np.quantile(drawn, 1.0 - alpha / 2.0))
    return (lo, hi), ""


# ---------------------------------------------------------------------------
# The statistic vocabulary — CLOSED, and it carries its own method
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Statistic:
    """One summary of a per-day sample's SHAPE, and how to put an interval on it.

    ``method`` is a property of the statistic, not a caller's choice.  A quantile
    has an exact closed-form interval; an IQR does not.  Letting a declaration pick
    would allow a bootstrap where an exact answer was free, and would make two
    artifacts' ``p50`` intervals incomparable for no reason.

    ``tail_fraction`` is what :class:`DistributionConvergence`'s event guard reads:
    the share of the sample the statistic actually rests on.  A p90 estimated from
    200 days rests on 20 observations however tight its interval looks, which is the
    same trap ``Convergence.min_events`` exists to catch for a rare-event rate.
    """

    label: str
    description: str
    method: str
    tail_fraction: float
    #: Point estimate from an ALREADY SORTED sample.
    point: "Callable[[list[float]], float]"
    #: Row-wise form for :data:`METHOD_BOOTSTRAP`; ``None`` for the exact method.
    vectorized: "Callable[[Any], Any] | None" = None
    #: ``p`` for a quantile statistic; ``None`` for anything else.  Read by the
    #: order-statistic method, and by the data dictionary.
    p: "float | None" = None

    def __post_init__(self) -> None:
        if self.method not in METHODS:
            raise ValueError(
                f"Statistic {self.label!r}: method must be one of {METHODS}."
            )
        if self.method == METHOD_ORDER_STATISTIC and self.p is None:
            raise ValueError(
                f"Statistic {self.label!r}: the order-statistic method is defined for "
                f"a QUANTILE only — it places the interval at two ranks of the sorted "
                f"sample, which means nothing for a statistic that is not one."
            )
        if self.method == METHOD_BOOTSTRAP and self.vectorized is None:
            raise ValueError(
                f"Statistic {self.label!r}: the bootstrap method needs a vectorized "
                f"form to evaluate on each resample."
            )

    def describe(self) -> dict:
        return {"statistic": self.label, "description": self.description,
                "method": self.method, "p": self.p,
                "tail_fraction": self.tail_fraction}


def quantile_statistic(p: float, label: "str | None" = None) -> Statistic:
    """A declared quantile — the exact-interval branch."""
    name = label or f"p{round(p * 100)}"
    return Statistic(
        label=name,
        description=(
            f"The p={p:g} quantile of the per-day values (type-7 interpolation, the "
            f"numpy/R default). Interval: exact distribution-free order statistics."
        ),
        method=METHOD_ORDER_STATISTIC,
        # Rounded because ``1.0 - 0.9`` is 0.09999999999999998, which makes a p90 at
        # exactly the min_tail_observations boundary fail by 1e-14 — a convergence
        # verdict flipping on float noise is not a verdict.
        tail_fraction=round(min(p, 1.0 - p), 12),
        point=(lambda values, _p=p: quantile(values, _p)),
        p=p,
    )


def _iqr_point(sorted_values: "list[float]") -> float:
    return quantile(sorted_values, 0.75) - quantile(sorted_values, 0.25)


def _iqr_vectorized(block: Any) -> Any:
    import numpy as np
    return (np.quantile(block, 0.75, axis=1) - np.quantile(block, 0.25, axis=1))


#: The spread statistic, and the reason the bootstrap branch exists in production.
#: IQR is p75 - p25, so its VALUE is derivable by a consumer holding both — but its
#: uncertainty is not, because that needs their covariance, which only this layer
#: sees.  That is §5.4's survival rule applied to the third output kind, and it is
#: why the row is here rather than left to a reader's subtraction.
IQR = Statistic(
    label="iqr",
    description=(
        "Interquartile range (p75 - p25) of the per-day values — the robust spread "
        "measure, and the single number that separates two builds with the same mean. "
        "Interval: percentile bootstrap, because no closed form exists; a consumer "
        "cannot rebuild it from the p25 and p75 rows without their covariance."
    ),
    method=METHOD_BOOTSTRAP,
    tail_fraction=0.25,
    point=_iqr_point,
    vectorized=_iqr_vectorized,
)

#: The shipped quantile ladder.  Five points: the median, the quartiles that bound
#: a typical day, and the p10/p90 tails that answer "how bad is a bad day".
P10 = quantile_statistic(0.10)
P25 = quantile_statistic(0.25)
P50 = quantile_statistic(0.50)
P75 = quantile_statistic(0.75)
P90 = quantile_statistic(0.90)

DEFAULT_STATISTICS: "tuple[Statistic, ...]" = (P10, P25, P50, P75, P90, IQR)


# ---------------------------------------------------------------------------
# Convergence for a distribution — the §6.2 heuristic, in the terms that exist
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DistributionConvergence:
    """When a distribution point is precise enough to read at face value.

    A parallel class rather than extra fields on :class:`Convergence`, because
    neither of that one's criteria is defined here: there is no standard error to
    take a ratio of, and "events" are not what a quantile rests on.  The three terms
    mirror it one for one over the quantities that DO exist.

    Parameters
    ----------
    rel_ci_width:
        ``(hi - lo) / abs(value)`` must be at or below this — the question
        ``rel_stderr`` asks, in the only form an asymmetric interval can answer.
        Looser than the scalar default by construction: a quantile is a far noisier
        functional of the same sample than its mean.
    min_tail_observations:
        ``n * statistic.tail_fraction``.  The guard that keeps an extreme quantile
        honest — a p90 off 60 days rests on six observations, and six observations
        can produce a narrow interval by luck.
    min_days:
        Minimum replicates, as above.
    """

    rel_ci_width: float = 0.20
    min_tail_observations: float = 50.0
    min_days: int = 100

    def check(self, value: "float | None", ci95: "tuple[float, float] | None",
              n: int, tail_observations: float) -> bool:
        """The verdict.  No value, or no interval, is never converged.

        An interval the estimator REFUSED to place (see
        :func:`order_statistic_interval`) fails here by construction, which is the
        behaviour we want: precision cannot be asserted without a bound.
        """
        if value is None or ci95 is None:
            return False
        if n < self.min_days or tail_observations < self.min_tail_observations:
            return False
        width = ci95[1] - ci95[0]
        if value == 0.0:
            # A relative criterion is undefined at zero; only an exactly degenerate
            # interval (every resample agreed) counts.
            return width == 0.0
        return abs(width / value) <= self.rel_ci_width

    def describe(self) -> dict:
        return {"rel_ci_width": self.rel_ci_width,
                "min_tail_observations": self.min_tail_observations,
                "min_days": self.min_days}


#: The default for a day-level distribution.
DEFAULT_DISTRIBUTION_CONVERGENCE = DistributionConvergence()


# ---------------------------------------------------------------------------
# The value type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DistributionPoint:
    """One statistic of one distribution — §5.4 kind 3's unit of answer.

    Deliberately NOT a :class:`MetricValue` with ``stderr=None``.  That class
    DERIVES its interval as ``value +/- 1.96*stderr``, and a quantile's interval is
    asymmetric: two order statistics straddling the estimate, typically unevenly on
    a skewed daily distribution.  Reusing the type would have let a symmetric
    interval be computed from a null standard error and silently returned ``None``,
    or worse, be reconstructed wrongly downstream.  Here ``ci95`` is STORED, and it
    is the only uncertainty the point carries.
    """

    distribution: str
    statistic: str
    method: str
    value: "float | None"
    ci95: "tuple[float, float] | None"
    n: int
    tail_observations: float
    converged: bool
    available: bool = True
    note: str = ""

    @property
    def measured(self) -> bool:
        return self.value is not None

    @classmethod
    def unavailable(cls, distribution: str, statistic: Statistic, reason: str,
                    n: int = 0) -> "DistributionPoint":
        """Inherited from the metric this distribution is declared OVER (§3.4)."""
        return cls(distribution=distribution, statistic=statistic.label,
                   method=statistic.method, value=None, ci95=None, n=n,
                   tail_observations=0.0, converged=False, available=False,
                   note=reason)


def estimate_distribution(distribution: str, values: "Iterable[float]",
                          statistics: "Iterable[Statistic]", *,
                          convergence: DistributionConvergence,
                          seed: int,
                          resamples: int = DEFAULT_RESAMPLES,
                          ) -> "list[DistributionPoint]":
    """Estimate every declared statistic of one per-day sample.

    The sample is sorted ONCE and shared: both the point estimates and the
    order-statistic bounds are ranks into the same sorted vector, so they cannot
    disagree about which observation they mean.
    """
    sample = sorted(float(v) for v in values)
    n = len(sample)
    out: list[DistributionPoint] = []

    for statistic in statistics:
        tail = n * statistic.tail_fraction
        if n == 0:
            out.append(DistributionPoint(
                distribution=distribution, statistic=statistic.label,
                method=statistic.method, value=None, ci95=None, n=0,
                tail_observations=0.0, converged=False,
                note="no days were simulated",
            ))
            continue

        value = statistic.point(sample)
        if statistic.method == METHOD_ORDER_STATISTIC:
            assert statistic.p is not None          # enforced in Statistic.__post_init__
            ci95, note = order_statistic_interval(sample, statistic.p)
        else:
            ci95, note = bootstrap_interval(
                sample, statistic.vectorized,       # type: ignore[arg-type]
                seed=_stable_seed(seed, distribution, statistic.label),
                resamples=resamples,
            )

        out.append(DistributionPoint(
            distribution=distribution,
            statistic=statistic.label,
            method=statistic.method,
            value=value,
            ci95=ci95,
            n=n,
            tail_observations=tail,
            converged=convergence.check(value, ci95, n, tail),
            note=note,
        ))
    return out
