"""
evaluation — the build-agnostic evaluation framework (design/evaluation_framework.md).

§13's build sequence through step 6: ``RunConfig`` + ``BuildAdapter`` + ``Roster`` +
the build registry (1), the metric registry + ``EvalReport`` + the statistics layer
with paired seeding (2), serialization (3), the ``attacks`` channel (4), the
enemy-construction seam and the deletion of the baked-in path (5a/5b), and
control-at-runtime (6).

The layer's reason for existing (§1): ``src/validation.py`` was hardcoded to the War
Angel and read entities by tuple position, so it could not be generalized in place.
Everything here is built so that adding a build means writing an adapter, never
editing evaluation code — the same rule that keeps the engine free of D&D-specific
knowledge.

**``src/validation.py`` IS NOW DELETED (s52, framework step 5b).**  It stayed
untouched as the regression check from step 1 to step 6, the §12 bit-identical parity
proof holding the whole way; step 5b deleted the baked-in enemy path it read, and §12
records why the goldens that replace it are a stronger PHYSICS signal and a weaker
LAYER one.  The layer signal that survives is
``test_headline_column_is_the_characters_own_output``: the source-attributed headline
against the independent target-keyed ledger, two subsystems and one number.
"""

from .adapters import BuildAdapter, OptionSpec, available_builds, get_adapter, register
from .artifact import (
    SCHEMA_VERSION,
    STATUSES,
    SUM_RULES,
    WARNING_CODES,
    csv_columns,
    report_to_dict,
    report_to_rows,
    to_json,
    warnings_for,
    write_artifact,
    write_csv,
    write_json,
    write_sweep_csv,
)
from .config import ATTRIBUTIONS, DAY_TIERS, ENEMY_KINDS, MODES, RunConfig
from .console import print_report, render
from .metrics import (
    ALL,
    DENOMINATORS,
    METRICS,
    BreakdownDef,
    Denominator,
    Dimension,
    DistributionDef,
    KeySpace,
    MetricDef,
    MetricRegistry,
)
from .report import (
    BreakdownValue,
    Comparison,
    DistributionValue,
    EvalReport,
    Provenance,
    build_report,
    compare,
)
from .roster import ROLES, Roster
from .runner import RunOutput, run, simulate
from .statistics import (
    DEFAULT_STATISTICS,
    IQR,
    METHODS,
    SCALE_INTERVAL,
    SCALE_RATIO,
    SCALES,
    Convergence,
    DistributionConvergence,
    DistributionPoint,
    MetricValue,
    PairedDelta,
    Statistic,
    quantile_statistic,
)

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
    # §5.4 output kinds: scalar / keyed breakdown (s46) / distribution (s48)
    "BreakdownDef",
    "BreakdownValue",
    "Dimension",
    "KeySpace",
    "ALL",
    "DistributionDef",
    "DistributionValue",
    "DistributionPoint",
    "DistributionConvergence",
    "Statistic",
    "quantile_statistic",
    "DEFAULT_STATISTICS",
    "IQR",
    "METHODS",
    # §6.2 (s48): the measurement scale selects the convergence criterion
    "SCALE_RATIO",
    "SCALE_INTERVAL",
    "SCALES",
    "MetricValue",
    "Convergence",
    "PairedDelta",
    "EvalReport",
    "Provenance",
    "build_report",
    "compare",
    "Comparison",
    # step 3 (§9) — serialization: JSON + tidy CSV + console, one schema_version
    "SCHEMA_VERSION",
    "STATUSES",
    "SUM_RULES",
    "WARNING_CODES",
    "report_to_dict",
    "report_to_rows",
    "csv_columns",
    "to_json",
    "warnings_for",
    "write_json",
    "write_csv",
    "write_artifact",
    "write_sweep_csv",
    "render",
    "print_report",
]
