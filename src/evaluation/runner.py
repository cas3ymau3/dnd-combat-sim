"""
runner.py — execute a :class:`RunConfig` and collect its raw per-day columns.

This is deliberately THIN.  Step 1's job is the adapter/roster seam, so this
module only does what the seam needs to prove itself: resolve the config to an
adapter, build the runner + roster, drive ``n_days``, and record the per-day
damage columns keyed by ENTITY ID (never by position).

What lives here vs. what does NOT
---------------------------------
Here: raw collection.  Not here: the metric registry, ``(value, n, stderr,
converged)``, paired-comparison plumbing, provenance assembly, and serialization
— those are evaluation_framework.md §5/§6/§9, i.e. build-sequence steps 2 and 3.
:func:`mean_dpr` exists only as the step-1 stand-in that lets the parity proof
(§12) run before the metric registry exists, and is marked for replacement.

Why the RNG order matters
-------------------------
``simulate`` constructs ``SeededRNG(config.seed)``, then calls the adapter, then
loops ``run_day()`` — the exact order ``src/validation.py`` uses.  Any other
order would shift the dice stream and break the exact-reproduction proof.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from ..rng import SeededRNG
from ..telemetry import CombatTelemetry

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
    #: entity id → per-day damage DEALT by that entity (all targets).
    damage_dealt: dict[int, list[int]] = field(default_factory=dict)
    #: entity id → per-day damage RECEIVED by that entity (all sources).
    damage_taken: dict[int, list[int]] = field(default_factory=dict)
    #: §13 telemetry, merged across every day of the run.
    telemetry: CombatTelemetry = field(default_factory=CombatTelemetry)

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


def simulate(config: "RunConfig", *, collect_telemetry: bool = True,
             on_day: "Callable[[int, DayResult], None] | None" = None) -> RunOutput:
    """Run ``config`` for ``config.n_days`` adventuring days.

    ``on_day`` receives ``(day_index, DayResult)`` for callers that need something
    this collector does not keep; the ``DayResult`` itself is not retained, so a
    200k-day publication run holds per-day integers rather than 800k combat logs.
    """
    adapter = config.validate()

    rng = SeededRNG(config.seed)
    runner, roster = adapter.build(config, rng)

    ids = roster.ids()
    output = RunOutput(
        config=config,
        roster=roster,
        described=adapter.describe(config),
        damage_dealt={i: [] for i in ids},
        damage_taken={i: [] for i in ids},
    )

    for day_index in range(config.n_days):
        result = runner.run_day()
        for i in ids:
            output.damage_dealt[i].append(result.damage_by_source(i))
            output.damage_taken[i].append(result.damage_received_by(i))
        if collect_telemetry:
            output.telemetry.merge(result.telemetry)
        if on_day is not None:
            on_day(day_index, result)

    return output


def mean_dpr(output: RunOutput, *roles: str) -> tuple[float, float]:
    """``(mean, stderr)`` of per-round damage for the given roles (default: the
    headline character column).

    STEP-1 STAND-IN.  Step 2 replaces this with the metric registry, where every
    scalar carries ``(value, n, stderr, converged)`` and an explicitly declared
    denominator.  The arithmetic here is deliberately identical to
    ``validation.run_level``'s so the §12 parity proof compares like with like:
    per-day DPR = day damage / (combats_per_day × rounds_per_combat), then the
    sample mean and its standard error.
    """
    per_day = [d / config_rounds(output) for d in output.column(*(roles or ("characters",)))]
    n = len(per_day)
    mean = sum(per_day) / n
    var = sum((x - mean) ** 2 for x in per_day) / (n - 1) if n > 1 else 0.0
    return mean, math.sqrt(var / n) if n > 1 else 0.0


def config_rounds(output: RunOutput) -> int:
    """The DPR denominator for a run (§5.2).  A control-lost turn stays in it."""
    return output.config.rounds_per_day
