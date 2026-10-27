"""
artifact.py — serializing an :class:`~src.evaluation.report.EvalReport` (§9, §9.1).

```
sim -> EvalReport (structured) -> artifact (JSON + tidy CSV) -> analysis (R) / static site
```

**The firm architectural line: the sim never knows about the website.**  The contract
is this file's output under a declared :data:`SCHEMA_VERSION`; the site is a downstream
consumer, exactly as the engine is a consumer of ability data rather than a knower of
spells.  Both renderers here — and the console one next door — render from the SAME
:class:`EvalReport`, which is why the JSON and the CSV cannot drift from each other.

What §9.1 locked, and why each piece is load-bearing
----------------------------------------------------
**Three result sections from version 1 — and the third one FILLED at s48, still at
version 1.**  s46 named §5.4's third output kind, s47 reserved its section empty, and
s48 built the estimator into it without touching :data:`SCHEMA_VERSION`.  That is the
reservation doing exactly the job it was for, and it worked for a reason worth keeping
in view: the locked ROW shape already carried ``stderr`` and ``ci95`` as SEPARATE
fields, so a quantile — which has no delta-method standard error and an asymmetric
interval — was always representable in it.  A row shape that had stored a half-width
instead would have forced a version bump here.

A distribution block is ``{name, over, unit, group, statistics, points}``: the same
declaration-then-rows layout as a breakdown, with ``points`` in place of
``cells``/``margins`` because a distribution has neither, and with **no ``sum_rule``** —
quantiles of one sample partition nothing and no sum of them means anything, so
offering a value from that two-value vocabulary would imply a choice exists.

**One ROW shape** for scalars, breakdown cells and margins alike, so a consumer writes
one parser.  A cell's key travels as a DICT of dimension -> value.  Nothing downstream
ever parses ``damage_share[fire]`` back into ``("fire",)`` — that reversal is the exact
failure §5.4 removed from the registry, and re-introducing it at the artifact boundary
would undo the whole exercise.

**Three states, never two** (§3.4).  ``measured`` / ``unavailable`` / ``unmeasured`` are
a closed vocabulary on every row, and ``value`` is ``null`` for the latter two.  A
serializer that writes ``0.0`` for an unavailable control metric is asserting that the
build resists control perfectly, which is the opposite of what is known.  The CSV writes
an empty field for the same reason: R reads it as ``NA``, and ``mean(x, na.rm=TRUE)``
then does the right thing where ``mean(c(0, ...))`` would not.

**Comparability warnings are TOP LEVEL.**  The authority is still §4's
``coverage.comparability_warning``, but a reader who must open the provenance block to
discover that two artifacts are incomparable will not open it.  :func:`warnings_for`
promotes that to a first-class array under a closed ``code`` vocabulary a site can style.

**The summing trap is a FIELD, not a comment.**  An UNCROSSED breakdown's cells do not
partition its total: each dimension covers the whole quantity on its own, so summing
every cell of ``save_fail_rate`` double-counts every save.  Rather than trust a renderer
to know that, each breakdown carries :data:`SUM_RULE_OVERLAP` or
:data:`SUM_RULE_PARTITION`, and cells and margins are serialized into SEPARATE lists so
the two can never be concatenated by accident.

**What is deliberately absent:** ``EvalReport.influence``.  A per-day vector per metric
at a 200k-day publication tier would be the bulk of the artifact, for a quantity only a
paired comparison consumes (§6.1).  A comparison artifact is its own shape and its own
decision.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

from .metrics import (
    SUM_RULE_OVERLAP,
    SUM_RULE_PARTITION,
    SUM_RULES,
    MetricRegistry,
)
from .statistics import DistributionPoint, MetricValue

if TYPE_CHECKING:                                    # pragma: no cover
    from .report import BreakdownValue, DistributionValue, EvalReport

#: §9: *"mandatory, because a site will be built against it"*.  Bump this only for a
#: change a version-1 consumer could not survive; ADDING the distributions section's
#: contents is explicitly not such a change, which is why it is reserved here at 1.
SCHEMA_VERSION = 1

#: The artifact unit (§9): one ``RunConfig`` -> one report -> one record.  A sweep is a
#: collection of these plus a manifest, so no sweep-cube schema is ever needed.
ARTIFACT_KIND = "run_record"


# ---------------------------------------------------------------------------
# The three report states (§3.4) — a CLOSED vocabulary
# ---------------------------------------------------------------------------

#: The run produced a number.
STATUS_MEASURED = "measured"
#: The run structurally CANNOT produce this metric — an unwired channel, or an
#: enemy model that has no such channel at all.  ``note`` carries the reason.
STATUS_UNAVAILABLE = "unavailable"
#: Available, but this run's denominator was zero (no charisma save was forced).
#: Not a gap in the model — a gap in this particular run.
STATUS_UNMEASURED = "unmeasured"

STATUSES = (STATUS_MEASURED, STATUS_UNAVAILABLE, STATUS_UNMEASURED)


def status_of(value: MetricValue) -> str:
    """Which of the three states this estimate is in.

    The distinction ``unavailable`` vs ``unmeasured`` is worth the extra vocabulary
    entry: one says the model cannot answer, the other says this run had nothing to
    answer about.  A reader decides very different things from the two, and both are
    destroyed by rounding them to a zero.
    """
    if not value.available:
        return STATUS_UNAVAILABLE
    return STATUS_MEASURED if value.measured else STATUS_UNMEASURED


# ---------------------------------------------------------------------------
# The summing rule (§5.4) — a CLOSED vocabulary, re-exported from the registry
# ---------------------------------------------------------------------------
# The vocabulary MOVED to ``metrics.py`` at s49 and is re-exported here so every
# existing import site is unaffected.  Until then this module DERIVED the rule from
# ``crossed``; the attacks breakdown (§8.1) is crossed AND overlapping, which showed
# the two to be independent facts.  A serializer is the wrong place for a semantic
# decision, so it now reads a declaration instead of making one.

_UNCROSSED_NOTE = (
    "This breakdown reports its dimensions INDEPENDENTLY (crossed=false): every cell "
    "covers the whole quantity along its own dimension, so summing the cells "
    "double-counts. Read the declared margin instead."
)

_NON_DISJOINT_NOTE = (
    "This breakdown is crossed, but its KEYS are not disjoint: one roll or event can "
    "satisfy several of them at once (a crit is also a hit), so summing the cells "
    "double-counts. There is no aggregate to read instead — the cells are each a "
    "share of the same denominator, and the denominator is the meaningful total."
)


def sum_rule_of(breakdown: "BreakdownValue") -> str:
    """The breakdown's DECLARED summing rule (§5.4; a declaration since s49)."""
    return breakdown.definition.sum_rule


def sum_rule_note_of(breakdown: "BreakdownValue") -> "str | None":
    """The prose a consumer needs when the cells do not sum — or ``None``.

    Two different warnings, because overlap has two different causes and the remedy
    differs: an uncrossed breakdown HAS a margin to read instead, and a crossed
    non-disjoint one does not.  Collapsing them into one note would tell half of its
    readers to go and read a cell that was deliberately never materialized.
    """
    if sum_rule_of(breakdown) != SUM_RULE_OVERLAP:
        return None
    return (_UNCROSSED_NOTE if not breakdown.definition.crossed
            else _NON_DISJOINT_NOTE)


# ---------------------------------------------------------------------------
# Warnings (§9.1) — surfaced, not buried
# ---------------------------------------------------------------------------

#: A closed code vocabulary so a downstream renderer can style or filter without
#: pattern-matching on prose.
WARNING_CODES = (
    "comparability",     # mode / attribution / enemy_path change what the number MEANS
    "coverage_gap",      # some part of §4 provenance is not resolved
    "engine_dirty",      # uncommitted tree: not reproducible from engine_commit
    "precision",         # a 'quick' iteration tier, not a publishable one
    "unconverged",       # a measured metric fails its own declared heuristic
)


def warnings_for(report: "EvalReport") -> list[dict[str, str]]:
    """The top-level warnings array for one report.

    ``comparability`` is UNCONDITIONAL.  The three axes it names — ``mode``,
    ``attribution``, ``enemy_path`` — do not merely move the headline number, they
    change what it means, so there is no run for which the warning is noise.  Emitting
    it always is also what makes its ABSENCE meaningless: a consumer never has to ask
    whether the writer forgot.
    """
    prov = report.provenance
    coverage = prov.coverage
    out: list[dict[str, str]] = [{
        "code": "comparability",
        "message": (
            f"mode={prov.config.get('mode')!r}, "
            f"attribution={coverage.get('attribution')!r}, "
            f"enemy_path={coverage.get('enemy_path')!r}. "
            + str(coverage.get("comparability_warning", ""))
        ),
    }]

    gaps = [k for k, v in coverage.items()
            if k.endswith("_side") and isinstance(v, str)
            and v.strip().upper().startswith("NOT RESOLVED")]
    for gap in gaps:
        out.append({"code": "coverage_gap",
                    "message": f"{gap}: {coverage[gap]}"})

    if prov.engine_dirty:
        out.append({
            "code": "engine_dirty",
            "message": (
                "The working tree had uncommitted changes when this ran, so the "
                f"recorded engine_commit ({prov.engine_commit}) does NOT identify the "
                "code that produced these numbers. Not reproducible."
            ),
        })

    if prov.day_tier == "quick":
        out.append({
            "code": "precision",
            "message": (
                "day_tier='quick' (§10): an iteration/smoke tier. Intervals are wide "
                "and this artifact is not a publishable one."
            ),
        })

    unconverged = [v.metric for v in report.unconverged()]
    if unconverged:
        out.append({
            "code": "unconverged",
            "message": (
                f"{len(unconverged)} measured metric(s) fail their own declared "
                f"convergence heuristic (§6.2) and should not be read yet: "
                + ", ".join(sorted(unconverged)[:12])
                + (", ..." if len(unconverged) > 12 else "")
            ),
        })
    return out


# ---------------------------------------------------------------------------
# The ROW — one shape for scalars, cells and margins
# ---------------------------------------------------------------------------

def _row(report: "EvalReport", name: str, *,
         breakdown: "str | None" = None,
         key: "tuple[str, ...] | None" = None,
         dimensions: tuple[str, ...] = (),
         is_margin: bool = False) -> dict[str, Any]:
    """One estimate, in the single row shape §9.1 locked.

    ``unit`` / ``denominator`` / ``group`` are repeated onto every row even though the
    embedded data dictionary also carries them: a row must be readable on its own,
    because the tidy CSV has no dictionary attached and a reader joining on ``metric``
    to get a unit is exactly the friction §5.1 exists to remove.

    ``is_margin`` is PASSED IN, from which list the caller is building — it is never
    inferred from the key.  ``ALL`` in a key does not mean margin: an uncrossed
    breakdown materializes marginal PROFILES as its cells, so ``save_fail_rate``'s
    ordinary ``("dex_save", "*")`` cell carries one.  Inferring it would flag all 8
    cells of both uncrossed breakdowns as margins and invert the filter a consumer
    uses to keep the two apart.
    """
    definition = report.registry[name]
    value = report.values[name]
    status = status_of(value)
    ci = value.ci95()
    return {
        "metric": name,
        "kind": "scalar" if breakdown is None else "breakdown",
        "breakdown": breakdown,
        "distribution": None,
        "key": None if key is None else dict(zip(dimensions, key)),
        "is_margin": is_margin,
        "unit": definition.unit,
        "denominator": definition.denominator,
        "group": definition.group,
        "method": None,
        "status": status,
        # None, never 0.0, for anything but `measured` — see the module docstring.
        "value": value.value if status == STATUS_MEASURED else None,
        "stderr": value.stderr if status == STATUS_MEASURED else None,
        "ci95": list(ci) if (status == STATUS_MEASURED and ci is not None) else None,
        "n": value.n,
        "n_events": value.n_events,
        "converged": value.converged,
        "note": value.note,
    }


def _distribution_row(report: "EvalReport", distribution: "DistributionValue",
                      point: DistributionPoint) -> dict[str, Any]:
    """One distribution statistic, in the SAME row shape (§9.1).

    Three fields behave differently here, and each difference is the honest one
    rather than a convenience:

    * **``stderr`` is always ``None``.**  A quantile is not a ratio; there is no
      delta-method standard error to report.  Writing the interval's half-width
      into it would invite a reader to rebuild a SYMMETRIC interval that the
      estimator never produced.
    * **``ci95`` is the whole of the uncertainty, and it is asymmetric.**  It can
      also be ``None`` on a measured row — when the sample is too small to place a
      bound (see ``order_statistic_interval``), the honest report is the estimate
      without an interval, not an interval clamped to the sample's extreme.
    * **``n_events`` carries the point's TAIL observations** — ``n × min(p, 1−p)``
      rather than a declared event count.  The column's meaning is unchanged (the
      observation count the convergence verdict rests on); only the way to compute
      it differs by kind, exactly as the estimator does.

    ``unit`` and ``denominator`` are inherited from the metric this describes, so a
    distribution row reads on its own like every other row.
    """
    over = report.registry[distribution.over]
    return {
        "metric": distribution.definition.point_name(point.statistic),
        "kind": "distribution",
        "breakdown": None,
        "distribution": distribution.name,
        "key": {"statistic": point.statistic},
        "is_margin": False,
        "unit": distribution.unit,
        "denominator": over.denominator,
        "group": distribution.definition.group,
        "method": point.method,
        "status": (STATUS_UNAVAILABLE if not point.available
                   else STATUS_MEASURED if point.measured else STATUS_UNMEASURED),
        "value": point.value,
        "stderr": None,
        "ci95": list(point.ci95) if point.ci95 is not None else None,
        "n": point.n,
        "n_events": point.tail_observations,
        "converged": point.converged,
        "note": point.note,
    }


def _distribution_block(report: "EvalReport",
                        distribution: "DistributionValue") -> dict[str, Any]:
    """One distribution: its declaration, then its points.

    No ``cells``/``margins`` split and no ``sum_rule``.  A breakdown needs both
    because its margins are sums a consumer must not add to the cells; a
    distribution has nothing of the kind, and handing it a field from the
    two-value sum vocabulary would imply that summing quantiles is a question with
    an answer.
    """
    definition = distribution.definition
    return {
        "name": distribution.name,
        "over": distribution.over,
        "unit": distribution.unit,
        "group": definition.group,
        "dimensions": list(definition.key_dimensions),
        "statistics": [s.label for s in definition.statistics],
        "points": [_distribution_row(report, distribution, point)
                   for point in distribution.points.values()],
    }


def _breakdown_block(report: "EvalReport", breakdown: "BreakdownValue") -> dict[str, Any]:
    """One breakdown: its declaration, then its cells and margins in SEPARATE lists."""
    definition = breakdown.definition
    dimensions = breakdown.dimensions
    block: dict[str, Any] = {
        "name": breakdown.name,
        "unit": breakdown.unit,
        "group": definition.group,
        "dimensions": list(dimensions),
        "crossed": definition.crossed,
        "sum_rule": sum_rule_of(breakdown),
        "margin_note": definition.margin_note,
        "cells": [
            _row(report, definition.cell_name(k), breakdown=breakdown.name,
                 key=k, dimensions=dimensions, is_margin=False)
            for k in breakdown.cells
        ],
        "margins": [
            _row(report, definition.cell_name(k), breakdown=breakdown.name,
                 key=k, dimensions=dimensions, is_margin=True)
            for k in breakdown.margins
        ],
    }
    note = sum_rule_note_of(breakdown)
    if note is not None:
        block["sum_rule_note"] = note
    return block


def run_id(report: "EvalReport") -> str:
    """A stable, human-legible identifier: ``build@Llevel-confighash``.

    Legible so a directory of artifacts can be read by eye, hashed so two runs that
    differ in any resolved config field cannot collide.  The engine commit is NOT in
    it — that lives in provenance, and folding it in would make the id churn on every
    commit for runs that are otherwise the same scenario.
    """
    config = report.provenance.config
    return f"{config['build']}@L{config['level']}-{_config_hash(report)}"


def _config_hash(report: "EvalReport") -> str:
    """The §10 cache key's config half, recomputed from the serialized config.

    Recomputed rather than carried because :class:`Provenance` stores the canonical
    dict, not the ``RunConfig`` — and the hash is defined as a function of exactly
    that dict, so this is the same number by construction.
    """
    payload = json.dumps(report.provenance.config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# JSON — the faithful form
# ---------------------------------------------------------------------------

def report_to_dict(report: "EvalReport", *,
                   include_data_dictionary: bool = True) -> dict[str, Any]:
    """The full run record (§9.1), as JSON-safe primitives.

    ``include_data_dictionary`` defaults ON so a single artifact is SELF-DESCRIBING:
    a website or an R script renders units, definitions, key spaces and refused-margin
    notes without importing the Python registry.  That is §5.1's "the registry IS the
    data dictionary" delivered across the process boundary, and it costs a few KB of
    static text against a run that took minutes to produce.
    """
    provenance = report.provenance
    record: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": ARTIFACT_KIND,
        "run_id": run_id(report),
        "config_hash": _config_hash(report),
        "warnings": warnings_for(report),
        "provenance": _provenance_to_dict(provenance),
        "results": {
            "headline": report.registry.headline.name,
            "scalars": [_row(report, d.name) for d in report.registry.scalars()],
            "breakdowns": [_breakdown_block(report, report.breakdowns[b.name])
                           for b in report.registry.breakdowns
                           if b.name in report.breakdowns],
            # §5.4's third kind. Reserved empty at s47, filled at s48 — and the
            # reservation held: SCHEMA_VERSION is still 1.
            "distributions": [_distribution_block(report, report.distributions[d.name])
                              for d in report.registry.distributions()
                              if d.name in report.distributions],
        },
    }
    if include_data_dictionary:
        record["data_dictionary"] = report.registry.data_dictionary()
    return record


def _provenance_to_dict(provenance: Any) -> dict[str, Any]:
    """The §4 block, WHOLE.

    Every field, including ``coverage``'s explicit not-resolved statement and the
    ``EPISTEMIC_NOTE``.  Trimming provenance to "the interesting parts" is how a
    reader ends up believing an assumption was recorded when it was not — the block
    exists precisely to make the gaps visible, so a serializer that drops the gaps
    inverts its purpose.
    """
    return {
        "config": provenance.config,
        "resolved": provenance.resolved,
        "coverage": provenance.coverage,
        "roster": provenance.roster,
        "engine_commit": provenance.engine_commit,
        "engine_dirty": provenance.engine_dirty,
        "generated_at": provenance.generated_at,
        "day_tier": provenance.day_tier,
        "pairing": provenance.pairing,
        "epistemic_note": provenance.epistemic_note,
    }


def to_json(report: "EvalReport", *, include_data_dictionary: bool = True,
            indent: "int | None" = 2) -> str:
    return json.dumps(report_to_dict(report,
                                     include_data_dictionary=include_data_dictionary),
                      indent=indent, sort_keys=False)


def write_json(report: "EvalReport", path: "str | Path", *,
               include_data_dictionary: bool = True) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        to_json(report, include_data_dictionary=include_data_dictionary) + "\n",
        encoding="utf-8",
    )
    return target


# ---------------------------------------------------------------------------
# Tidy long CSV — the analysis form
# ---------------------------------------------------------------------------

#: Run-identifying columns, repeated on EVERY row.  That repetition is what makes a
#: sweep's CSVs concatenate into one frame that ``group_by(run_id)`` can split again —
#: the defining property of tidy long form, and the reason not to normalize them out.
RUN_COLUMNS = ("run_id", "config_hash", "schema_version", "build", "level",
               "mode", "attribution", "day_tier", "engine_commit")

#: What the row IS.  ``distribution`` and ``method`` joined at s48: a distribution
#: row needs to name its parent without a consumer parsing ``dpr_distribution[p50]``
#: (the reversal §5.4 exists to remove), and an ASYMMETRIC interval is unreadable
#: without knowing how it was placed.  ``sum_rule`` is blank on them — quantiles are
#: not additive under any rule, so the field does not apply rather than taking a value.
META_COLUMNS = ("metric", "kind", "breakdown", "distribution", "group", "unit",
                "denominator", "is_margin", "sum_rule", "method")

#: What the row SAYS.
VALUE_COLUMNS = ("status", "value", "stderr", "ci_low", "ci_high", "n", "n_events",
                 "converged", "note")


def dimension_columns(registry: MetricRegistry) -> tuple[str, ...]:
    """The union of every registered breakdown's dimension names, in declaration order.

    Derived from the registry rather than hardcoded, so adding a dimension adds a
    column automatically — and visibly, since the header is part of the contract.

    Two different emptinesses share these columns and must not be conflated: a BLANK
    means *this row is not keyed by that dimension at all*, while ``*`` means *this row
    is a margin over it*.  A scalar's ``ability`` is blank; ``save_fail_rate[*|control]``
    has ``ability='*'``.  Collapsing those would silently turn "not applicable" into
    "aggregated", which is the same class of error as writing 0 for unmeasured.
    """
    names: list[str] = []
    for breakdown in registry.breakdowns:
        for dimension in breakdown.key_space.names:
            if dimension not in names:
                names.append(dimension)
    # §5.4 kind 3 keys its points the same way, so its dimension joins the same
    # union rather than getting a bespoke column. Today that is just 'statistic';
    # a later KEYED distribution adds its dimensions here with no change to this
    # function, which is the point of DistributionDef.key_dimensions.
    for distribution in registry.distributions():
        for dimension in distribution.key_dimensions:
            if dimension not in names:
                names.append(dimension)
    return tuple(names)


def csv_columns(registry: MetricRegistry) -> tuple[str, ...]:
    """The tidy CSV header for ``registry``."""
    return RUN_COLUMNS + META_COLUMNS + dimension_columns(registry) + VALUE_COLUMNS


def report_to_rows(report: "EvalReport") -> list[dict[str, Any]]:
    """One flat dict per estimate — the tidy long form (§9).

    Built from the SAME rows :func:`report_to_dict` serializes, so the CSV and the JSON
    are two views of one computation and cannot disagree about a value.
    """
    record = report_to_dict(report, include_data_dictionary=False)
    provenance = report.provenance
    config = provenance.config
    dimensions = dimension_columns(report.registry)

    common = {
        "run_id": record["run_id"],
        "config_hash": record["config_hash"],
        "schema_version": SCHEMA_VERSION,
        "build": config["build"],
        "level": config["level"],
        "mode": config["mode"],
        "attribution": config["attribution"],
        "day_tier": provenance.day_tier,
        "engine_commit": provenance.engine_commit,
    }

    def flatten(row: dict[str, Any], sum_rule: "str | None") -> dict[str, Any]:
        key = row["key"] or {}
        ci = row["ci95"]
        flat = dict(common)
        flat.update({
            "metric": row["metric"],
            "kind": row["kind"],
            "breakdown": row["breakdown"],
            "distribution": row["distribution"],
            "group": row["group"],
            "unit": row["unit"],
            "denominator": row["denominator"],
            "is_margin": row["is_margin"],
            "sum_rule": sum_rule,
            "method": row["method"],
        })
        # Blank for a dimension this row is not keyed by; '*' where the key says so.
        for dimension in dimensions:
            flat[dimension] = key.get(dimension)
        flat.update({
            "status": row["status"],
            "value": row["value"],
            "stderr": row["stderr"],
            "ci_low": ci[0] if ci else None,
            "ci_high": ci[1] if ci else None,
            "n": row["n"],
            "n_events": row["n_events"],
            "converged": row["converged"],
            "note": row["note"],
        })
        return flat

    rows = [flatten(r, None) for r in record["results"]["scalars"]]
    for block in record["results"]["breakdowns"]:
        rule = block["sum_rule"]
        rows.extend(flatten(r, rule) for r in block["cells"])
        rows.extend(flatten(r, rule) for r in block["margins"])
    # sum_rule stays None for every distribution point: see META_COLUMNS.
    for block in record["results"]["distributions"]:
        rows.extend(flatten(r, None) for r in block["points"])
    return rows


def _csv_field(value: Any) -> str:
    """R-friendly rendering of one field.

    ``TRUE``/``FALSE`` so R reads a logical column rather than text, and EMPTY for
    ``None`` so it reads ``NA`` rather than a number.  The second is the load-bearing
    one: an unavailable metric written as ``0`` would be averaged into a mean.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value)


def write_csv(report: "EvalReport", path: "str | Path", *,
              append: bool = False) -> Path:
    """Write the tidy long CSV.

    ``append`` exists for a sweep: many run records share one header and concatenate,
    which is only sound because the header is a function of the registry and every row
    carries its own ``run_id``.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    columns = csv_columns(report.registry)
    rows = report_to_rows(report)
    exists = target.exists() and target.stat().st_size > 0
    mode = "a" if append else "w"
    with target.open(mode, encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if not (append and exists):
            writer.writerow(columns)
        for row in rows:
            writer.writerow([_csv_field(row.get(c)) for c in columns])
    return target


# ---------------------------------------------------------------------------
# Both at once
# ---------------------------------------------------------------------------

def write_artifact(report: "EvalReport", directory: "str | Path", *,
                   stem: "str | None" = None,
                   include_data_dictionary: bool = True) -> dict[str, Path]:
    """Write ``<stem>.json`` and ``<stem>.csv`` into ``directory``.

    ``stem`` defaults to the run id, which already identifies the scenario and hashes
    the config — so re-running the same scenario overwrites its own artifact rather
    than accumulating near-duplicates, and two different scenarios cannot collide.
    """
    root = Path(directory)
    name = stem or run_id(report)
    return {
        "json": write_json(report, root / f"{name}.json",
                           include_data_dictionary=include_data_dictionary),
        "csv": write_csv(report, root / f"{name}.csv"),
    }


def write_sweep_csv(reports: "Iterable[EvalReport]", path: "str | Path") -> Path:
    """Concatenate several reports into ONE tidy frame (§9's sweep = a collection).

    Every report must share a registry, because the header is a function of it; a
    frame whose columns meant different things in different blocks would not be tidy,
    it would be two frames stacked.
    """
    target = Path(path)
    first = True
    header: "tuple[str, ...] | None" = None
    for report in reports:
        columns = csv_columns(report.registry)
        if header is None:
            header = columns
        elif columns != header:
            raise ValueError(
                "write_sweep_csv needs one registry across the group: got columns "
                f"{columns} after {header}."
            )
        write_csv(report, target, append=not first)
        first = False
    if first:
        raise ValueError("write_sweep_csv got no reports.")
    return target
