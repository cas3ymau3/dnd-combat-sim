"""
evaluation — the build-agnostic evaluation framework (design/evaluation_framework.md).

Steps 1–2 of §13's build sequence: ``RunConfig`` + ``BuildAdapter`` + ``Roster`` +
the build registry (step 1), and the metric registry + ``EvalReport`` + the
statistics layer with paired seeding (step 2).

The layer's reason for existing (§1): ``src/validation.py`` is hardcoded to the
War Angel and reads entities by tuple position, so it cannot be generalized in
place.  Everything here is built so that adding a build means writing an adapter,
never editing evaluation code — the same rule that keeps the engine free of
D&D-specific knowledge.

``src/validation.py`` stays untouched as the regression check until the framework
reproduces its numbers exactly (§13); ``tests/test_eval_framework.py`` is that
proof.
"""

from .adapters import BuildAdapter, OptionSpec, available_builds, get_adapter, register
from .config import ATTRIBUTIONS, DAY_TIERS, ENEMY_KINDS, MODES, RunConfig
from .metrics import (
    ALL,
    DENOMINATORS,
    METRICS,
    BreakdownDef,
    Denominator,
    Dimension,
    KeySpace,
    MetricDef,
    MetricRegistry,
)
from .report import (
    BreakdownValue,
    Comparison,
    EvalReport,
    Provenance,
    build_report,
    compare,
)
from .roster import ROLES, Roster
from .runner import RunOutput, run, simulate
from .statistics import Convergence, MetricValue, PairedDelta

__all__ = [
    "BuildAdapter",
    "OptionSpec",
    "register",
    "get_adapter",
    "available_builds",
    "RunConfig",
    "DAY_TIERS",
    "ENEMY_KINDS",
    "MODES",
    "ATTRIBUTIONS",
    "Roster",
    "ROLES",
    "simulate",
    "run",
    "RunOutput",
    # step 2 — metrics, statistics, report
    "MetricDef",
    "MetricRegistry",
    "METRICS",
    "Denominator",
    "DENOMINATORS",
    # §5.4 output kinds (s46): scalar / keyed breakdown / (reserved) distribution
    "BreakdownDef",
    "BreakdownValue",
    "Dimension",
    "KeySpace",
    "ALL",
    "MetricValue",
    "Convergence",
    "PairedDelta",
    "EvalReport",
    "Provenance",
    "build_report",
    "compare",
    "Comparison",
]
