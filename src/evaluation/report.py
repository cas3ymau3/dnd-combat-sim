"""
report.py — ``EvalReport`` and the provenance block (evaluation_framework.md §4, §5.3, §6.1).

An :class:`EvalReport` is one :class:`~src.evaluation.config.RunConfig`'s worth of
answers: every registered metric estimated from the run's per-day samples, wrapped
in the block that makes those numbers interpretable and reproducible.

Structure follows §5.3 exactly, and structurally rather than by convention:

* **headline** — the character column's DPR, one declared metric.  There is **no
  composite build score**: a single ranked number would bake in offense/resilience
  weightings that are contestable, and would hide precisely the assumptions the
  provenance block exists to expose.
* **panel** — everything beside it: damage taken, saves by type, control turns,
  typed mitigation, concentration, resources.
* **columns** — roster total and per-summon figures.  A separate group, so a
  summon's damage cannot be merged into the headline by a renderer's oversight.

What §4 can and cannot say TODAY
--------------------------------
``resolved`` is the load-bearing half of provenance: a config of ``soft_factor=None``
must be recorded as the value ACTUALLY used, not as the word "default".  The build
side of that works now — each adapter's ``describe()`` does real resolution (e.g.
Starfire's ``primal_strike_unarmed=None`` resolves to the level row's ``raw_unarmed``
with the source path named).

**The enemy side does not exist yet.**  Each build factory constructs its own enemy
policy off its own level row, ``RunConfig.enemy_options`` is hard-rejected, and
there is no ``BaselineEnemyPolicy.describe_parameters()`` to call.  Rather than ship
a provenance block with a plausible-looking but empty ``enemy`` key, the block
carries an explicit :attr:`Provenance.coverage` statement naming what is resolved
and what is not.  A half-filled provenance block is worse than an honest gap: it
implies the assumptions were recorded when they were not.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .metrics import METRICS, MetricRegistry
from .statistics import MetricValue, PairedDelta, paired_delta

if TYPE_CHECKING:                                    # pragma: no cover
    from .config import RunConfig
    from .runner import RunOutput

#: §11 / §12: after guide-replication was retired, the project has NO external
#: validation source — everything is internal consistency plus face validity.  §12
#: requires this to be stated ONCE in the outputs rather than left implicit, and the
#: provenance block is where it belongs: it is a property of every number here.
EPISTEMIC_NOTE = (
    "No external validation source exists for this model. The build guides and the R "
    "prototype were written by the same author as the model, so reproducing their DPR "
    "figures was a one-time bootstrapping check, not an independent standard "
    "(evaluation_framework.md §11). Every number below is MODEL-RELATIVE: it is only "
    "meaningful against another number produced by the same engine commit under the "
    "same resolved assumptions."
)


# ---------------------------------------------------------------------------
# Engine version
# ---------------------------------------------------------------------------

_ENGINE_VERSION: "tuple[str | None, bool] | None" = None


def engine_version() -> "tuple[str | None, bool]":
    """``(commit_sha, dirty)`` for the working tree, cached for the process.

    §4: *"``engine_commit`` is not optional"* — artifacts are committed and displayed
    over time, and without the code version there is no way to tell whether two
    reports are comparable or separated by an engine change.  It cannot be
    reconstructed after the fact.

    Cached because a sweep produces many reports and each would otherwise shell out
    to git; the working tree cannot change mid-run in the single-process execution
    model (§10).  Returns ``(None, False)`` outside a git checkout rather than
    raising: an exploratory run in a tarball should still produce a report, and the
    ``None`` says plainly that the version is unknown.
    """
    global _ENGINE_VERSION
    if _ENGINE_VERSION is None:
        root = Path(__file__).resolve().parents[2]
        try:
            sha = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip() or None
            status = subprocess.run(
                ["git", "-C", str(root), "status", "--porcelain"],
                capture_output=True, text=True, timeout=10, check=True,
            ).stdout.strip()
            _ENGINE_VERSION = (sha, bool(status))
        except (OSError, subprocess.SubprocessError):
            _ENGINE_VERSION = (None, False)
    return _ENGINE_VERSION


# ---------------------------------------------------------------------------
# Provenance (§4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    """Parameters *and* code — the block that makes a report interpretable."""

    config: dict[str, Any]
    resolved: dict[str, Any]
    coverage: dict[str, Any]
    roster: dict[str, list[str]]
    engine_commit: "str | None"
    engine_dirty: bool
    generated_at: str
    day_tier: str
    #: §6.1: the pairing is recorded so a reader knows a reported delta is paired
    #: (and that its stated interval means the paired thing).  ``None`` for a
    #: standalone run.
    pairing: "dict[str, Any] | None" = None
    epistemic_note: str = EPISTEMIC_NOTE

    @classmethod
    def build(cls, config: "RunConfig", described: dict[str, Any],
              roster_summary: dict[str, list[str]],
              pairing: "dict[str, Any] | None" = None) -> "Provenance":
        sha, dirty = engine_version()
        return cls(
            config=config.canonical(),
            resolved={
                "build": described,
                # Deliberately absent, not empty: see the module docstring.
                "enemy": None,
            },
            coverage={
                "build_side": "resolved — the adapter reports the values actually used",
                "enemy_side": (
                    "NOT RESOLVED. Each build factory constructs its own enemy policy "
                    "off its own LEVELS row; RunConfig.enemy/enemy_options are "
                    "hard-rejected, and BaselineEnemyPolicy has no "
                    "describe_parameters() yet. Lands with the §3.4 enemy-construction "
                    "seam (§13 step 5)."
                ),
                "enemy_path": described.get("enemy_policy"),
                "comparability_warning": (
                    "Runs whose enemy_path differs faced DIFFERENT enemy models and "
                    "must not be compared (§3.4)."
                ),
            },
            roster=roster_summary,
            engine_commit=sha,
            engine_dirty=dirty,
            generated_at=datetime.now(timezone.utc).isoformat(),
            day_tier=config.day_tier,
            pairing=pairing,
        )


# ---------------------------------------------------------------------------
# The report (§5.3)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvalReport:
    """Every registered metric for one run, plus its provenance."""

    provenance: Provenance
    registry: MetricRegistry
    values: dict[str, MetricValue]
    #: Per-day influence values, kept for §6.1's paired deltas.  NOT part of the
    #: report's serialized form (step 3) — a 200k-day run would carry a per-metric
    #: vector into every artifact for a quantity only a comparison consumes.
    influence: dict[str, list[float]] = field(default_factory=dict, repr=False)

    # -- access ---------------------------------------------------------

    def __getitem__(self, name: str) -> MetricValue:
        return self.metric(name)

    def metric(self, name: str) -> MetricValue:
        if name not in self.values:
            raise KeyError(
                f"No metric {name!r} in this report. Registered: {self.registry.names()}."
            )
        return self.values[name]

    @property
    def headline(self) -> MetricValue:
        """§5.3's headline: the character column's DPR, and nothing else."""
        return self.values[self.registry.headline.name]

    def group(self, group: str) -> list[MetricValue]:
        return [self.values[d.name] for d in self.registry.group(group)]

    @property
    def panel(self) -> list[MetricValue]:
        """The §5.3 panel — reported beside the headline, never folded into it."""
        return self.group("panel")

    @property
    def columns(self) -> list[MetricValue]:
        """Roster / per-summon columns — separate by construction (§3.3, §5.3)."""
        return self.group("column")

    def measured(self) -> list[MetricValue]:
        """Metrics this run actually produced a number for."""
        return [v for v in self.values.values() if v.measured]

    def unavailable(self) -> list[MetricValue]:
        """Metrics the run structurally cannot produce (§3.4).

        These are the rows a report must render as "unavailable, because …" — a
        silent zero for control resilience would read as "this build resists
        control perfectly", which is the opposite of what is known.
        """
        return [v for v in self.values.values() if not v.available]

    def unmeasured(self) -> list[MetricValue]:
        """Metrics that ARE available but produced no value on this run.

        A distinct state from :meth:`unavailable`, and worth keeping distinct: a
        ``cha_save`` fail rate on a run that forced no charisma save is not a
        broken channel, it is a denominator of zero.  Both refuse to report a
        fabricated zero; only one of them is a gap in the model.
        """
        return [v for v in self.values.values() if v.available and not v.measured]

    def unconverged(self) -> list[MetricValue]:
        """Measured metrics whose own declared heuristic says do not read them yet."""
        return [v for v in self.values.values() if v.measured and not v.converged]


def build_report(output: "RunOutput", *,
                 pairing: "dict[str, Any] | None" = None) -> EvalReport:
    """Assemble an :class:`EvalReport` from a completed run.

    Pure post-processing: the run is over, no dice are rolled here, and calling it
    twice on the same :class:`~src.evaluation.runner.RunOutput` gives the same
    answer.  The registry used is the one the run collected against — asking for a
    metric the run never sampled would be a fabrication, not a computation.
    """
    values: dict[str, MetricValue] = {}
    influence: dict[str, list[float]] = {}

    for definition in output.registry:
        reason = output.unavailable.get(definition.name)
        if reason is not None:
            values[definition.name] = MetricValue.unavailable(
                definition.name, reason, n=output.n_days,
            )
            continue
        value, infl = output.samples[definition.name].estimate(definition.convergence)
        values[definition.name] = value
        influence[definition.name] = infl

    return EvalReport(
        provenance=Provenance.build(
            output.config, output.described, output.roster.summary(), pairing,
        ),
        registry=output.registry,
        values=values,
        influence=influence,
    )


# ---------------------------------------------------------------------------
# Paired comparison (§6.1) — the DEFAULT for any comparison
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Comparison:
    """A paired comparison group: reports plus per-metric deltas against a base.

    §6.1's decision is that paired seeding is the DEFAULT, not an option: running
    every config in a group from the same base seed cancels the shared noise, so the
    variance *of the difference* collapses — frequently worth 10–100× in effective
    sample size for exactly the sensitivity analysis §7 exists to support.
    """

    seed: int
    reports: list[EvalReport]
    labels: list[str]
    #: ``labels[i] → {metric name → PairedDelta}`` for every non-base report.
    deltas: dict[str, dict[str, PairedDelta]]

    @property
    def base(self) -> EvalReport:
        return self.reports[0]

    def delta(self, label: str, metric: str) -> PairedDelta:
        return self.deltas[label][metric]


def compare(configs: "Iterable[RunConfig]", *, seed: "int | None" = None,
            labels: "list[str] | None" = None,
            registry: MetricRegistry = METRICS,
            collect_telemetry: bool = True) -> Comparison:
    """Run a comparison group under common random numbers (§6.1).

    Every config is re-seeded to one shared base seed — the first config's, unless
    ``seed`` is given — so both scenarios see the same combat times, the same short-rest
    placement, and the same dice stream wherever the two runs have not diverged.
    The pairing is recorded in each report's provenance, so a reader can tell that a
    reported delta is paired and that its interval means the paired thing.

    Deltas are reported against the FIRST config, which is therefore the baseline of
    the group by position — the one place in this layer where order carries meaning,
    and it is a caller's explicit choice rather than a roster's accident.
    """
    from .runner import simulate                      # local: avoids an import cycle

    group = [c for c in configs]
    if len(group) < 2:
        raise ValueError("A comparison needs at least two configs.")

    base_seed = group[0].seed if seed is None else seed
    group = [c.replace(seed=base_seed) for c in group]
    names = labels if labels is not None else [_auto_label(c) for c in group]
    if len(names) != len(group):
        raise ValueError(f"Got {len(names)} labels for {len(group)} configs.")

    pairing_common = {
        "paired": True,
        "seed": base_seed,
        "members": [c.config_hash() for c in group],
        "note": ("common random numbers (§6.1): every config in this group ran from "
                 "the same base seed, so reported deltas are PAIRED"),
    }

    reports = []
    for label, config in zip(names, group):
        output = simulate(config, registry=registry, collect_telemetry=collect_telemetry)
        reports.append(build_report(output, pairing={**pairing_common, "label": label}))

    base = reports[0]
    deltas: dict[str, dict[str, PairedDelta]] = {}
    for label, report in zip(names[1:], reports[1:]):
        deltas[label] = {
            name: paired_delta(name, report.values[name], report.influence.get(name, []),
                               base.values[name], base.influence.get(name, []))
            for name in report.values
        }

    return Comparison(seed=base_seed, reports=reports, labels=names, deltas=deltas)


def _auto_label(config: "RunConfig") -> str:
    """A short human label for a config in a comparison group."""
    opts = ",".join(f"{k}={config.build_options[k]!r}"
                    for k in sorted(config.build_options))
    return f"{config.build}@L{config.level}" + (f"[{opts}]" if opts else "")
