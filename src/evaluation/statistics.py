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

import math
from array import array
from dataclasses import dataclass, field
from typing import Iterable

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
