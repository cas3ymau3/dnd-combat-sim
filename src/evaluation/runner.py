"""
runner.py — execute a :class:`RunConfig` and collect the per-day samples a report needs.

The runner drives the simulation and records, per adventuring day, exactly two
kinds of raw material:

* the **damage columns** keyed by ENTITY ID (never by position), which the roster
  turns into role-scoped columns;
* the **per-metric (numerator, denominator, events) triples** declared by the metric
  registry, which the statistics layer turns into ``(value, n, stderr, converged)``.

Per-day samples rather than running sums
----------------------------------------
It would be cheaper to accumulate sums as the run proceeds, but §6.1's paired
comparison must line day ``d`` of run A up against day ``d`` of run B, and a
running-sums accumulator collapses precisely the information that makes common
random numbers worth having.  The samples live in ``array("d")`` so the
publication tier (§10: 200,000 days) stays affordable.

What lives here vs. what does NOT
---------------------------------
Here: collection.  Not here: the estimators (``statistics``), the metric
declarations (``metrics``), report assembly and provenance (``report``), or
serialization (§9, a later step).  The runner knows a registry exists and what
shape a sample is; it does not know what any metric MEANS.

Unavailable metrics (§3.4) are resolved ONCE, before the first day, from the run's
own context — so a metric this run structurally cannot produce costs no collection
at all, and its absence is recorded as a REASON rather than as a column of zeros.

Why the RNG order matters
-------------------------
``simulate`` constructs ``SeededRNG(config.seed)``, then calls the adapter, then
loops ``run_day()`` — the exact order ``src/validation.py`` uses.  Any other
order would shift the dice stream and break the exact-reproduction proof (§12).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from ..rng import SeededRNG
from ..telemetry import CombatTelemetry
from .metrics import METRICS, DaySample, MetricRegistry, RunContext
from .statistics import MetricSamples

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import DayResult
    from .config import RunConfig
    from .roster import Roster


@dataclass
class RunOutput:
    """Raw per-day columns from one simulated run.

    Every column is a list of length ``n_days``, so downstream statistics (§6.2
    stderr / convergence) have the per-day sample to work from rather than a
    pre-collapsed mean.
    """

    config: "RunConfig"
    roster: "Roster"
    described: dict[str, Any]
    #: The metric set this run collected against.  A report can only ask for what
    #: was sampled — requesting anything else would be fabrication, not computation.
    registry: MetricRegistry = METRICS
    #: entity id → per-day damage DEALT by that entity (all targets).
    damage_dealt: dict[int, list[int]] = field(default_factory=dict)
    #: entity id → per-day damage RECEIVED by that entity (all sources).
    damage_taken: dict[int, list[int]] = field(default_factory=dict)
    #: §13 telemetry, merged across every day of the run.
    telemetry: CombatTelemetry = field(default_factory=CombatTelemetry)
    #: metric name → its per-day (numerator, denominator, events) columns.
    samples: dict[str, MetricSamples] = field(default_factory=dict)
    #: metric name → REASON it could not be measured (§3.4).  A metric in here has
    #: no samples at all, and the report renders it as an explicit "unavailable"
    #: row rather than as a zero that would read as a measurement.
    unavailable: dict[str, str] = field(default_factory=dict)

    @property
    def n_days(self) -> int:
        return self.config.n_days

    def column(self, *roles: str) -> list[int]:
        """Per-day damage dealt by every entity in the given roster roles.

        ``column("characters")`` is the HEADLINE column; ``column("characters",
        "summons", "allies")`` is the party total reported BESIDE it.  §3.3's rule
        that the two are never collapsed is enforced by them being different calls
        with different names, not by a comment.
        """
        ids = self.roster.ids(*roles)
        return [sum(self.damage_dealt[i][d] for i in ids) for d in range(self.n_days)]

    @property
    def headline_damage(self) -> list[int]:
        """Per-day damage dealt by the build's own characters — the headline."""
        return self.column("characters")

    @property
    def party_damage(self) -> list[int]:
        """Per-day damage dealt by characters + summons + allies."""
        return self.column("characters", "summons", "allies")


def simulate(config: "RunConfig", *, registry: MetricRegistry = METRICS,
             collect_telemetry: bool = True, rng: "SeededRNG | None" = None,
             on_day: "Callable[[int, DayResult], None] | None" = None) -> RunOutput:
    """Run ``config`` for ``config.n_days`` adventuring days.

    ``on_day`` receives ``(day_index, DayResult)`` for callers that need something
    this collector does not keep; the ``DayResult`` itself is not retained, so a
    200k-day publication run holds per-day numbers rather than 800k combat logs.

    ``rng`` exists so a caller can supply an instrumented generator (a recording
    wrapper, for the §12 proof that two paired configs draw byte-identical dice).
    Passing one is equivalent to the default as long as it is freshly seeded with
    ``config.seed`` — the construction ORDER relative to the adapter is what the
    parity proof depends on, and that order is fixed here either way.
    """
    adapter = config.validate()

    if rng is None:
        rng = SeededRNG(config.seed)
    runner, roster = adapter.build(config, rng)
    described = adapter.describe(config)

    # Availability is decided ONCE, from the run's own context, before any day is
    # simulated (§3.4): an unmeasurable metric costs nothing and is recorded as a
    # reason rather than as a column of zeros.
    context = RunContext(config=config, roster=roster, described=described)
    unavailable: dict[str, str] = {}
    samples: dict[str, MetricSamples] = {}
    for definition in registry:
        reason = definition.availability(context)
        if reason is None:
            samples[definition.name] = MetricSamples(
                metric=definition.name,
                fixed_denominator=definition.denominator_spec.fixed,
            )
        else:
            unavailable[definition.name] = reason
    collected = [d for d in registry if d.name in samples]

    ids = roster.ids()
    output = RunOutput(
        config=config,
        roster=roster,
        described=described,
        registry=registry,
        damage_dealt={i: [] for i in ids},
        damage_taken={i: [] for i in ids},
        samples=samples,
        unavailable=unavailable,
    )

    for day_index in range(config.n_days):
        result = runner.run_day()
        dealt = {i: result.damage_by_source(i) for i in ids}
        taken = {i: result.damage_received_by(i) for i in ids}
        for i in ids:
            output.damage_dealt[i].append(dealt[i])
            output.damage_taken[i].append(taken[i])

        day_telemetry = result.telemetry
        sample = DaySample(
            config=config, roster=roster, result=result,
            damage_dealt=dealt, damage_taken=taken, telemetry=day_telemetry,
        )
        for definition in collected:
            samples[definition.name].record(
                definition.numerator(sample),
                definition.denominator_spec.per_day(sample),
                definition.event_count(sample),
            )

        if collect_telemetry:
            output.telemetry.merge(day_telemetry)
        if on_day is not None:
            on_day(day_index, result)

    return output


def run(config: "RunConfig", *, registry: MetricRegistry = METRICS, **kwargs):
    """Simulate ``config`` and assemble its :class:`~src.evaluation.report.EvalReport`.

    The one-call entry point for a single run.  For a COMPARISON use
    ``report.compare``, which applies §6.1's paired seeding — comparing two
    independently-seeded reports throws away most of the precision available.
    """
    from .report import build_report

    return build_report(simulate(config, registry=registry, **kwargs))


