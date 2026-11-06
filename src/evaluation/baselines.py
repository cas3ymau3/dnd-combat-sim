"""
baselines.py — the §11 baselines registry: declared references, and scoring against them.

A baseline is a **reference**, not a property of a build (§11).  Pulling them into their
own registry is what lets one run be scored against an external figure or against
another of our own runs without a build implicitly owning the standard it is judged by.

**The shape was LOCKED in §11.1-§11.3 before this file existed**, per the per-feature
ritual's step 4 and on the §9.1 / §10.1 precedent — both were settled ahead of their
writers and then absorbed later additions at version 1 without a break.  Everything
this module serializes is specified there; what lives here is the mechanism.

```
baselines/*.yaml  ->  BaselineRegistry  ->  score(report, registry)  ->  [Score]
                                                                     ->  record["scores"]
                                                                     ->  the tidy score frame
```

Four things worth knowing before reading the code
-------------------------------------------------
**1. The §11 tuple does not survive contact with the only external source there is.**
§11 says an entry is ``(source, build, level, metric, value, provenance)``.  Treantmonk's
Damage Classes by Tier — the project's one genuinely external reference — is keyed by
``(class, tier)``: no build, ``level`` is a BAND, and the value is an INTERVAL.  So an
entry's position is a :class:`dict` ``coordinate`` over declared dimensions, the same
decision §5.4 forced on breakdown keys and §10.1 on sweep cells.

**2. A value is a POINT or an INTERVAL, and the two score differently.**  A point yields
a delta and a ratio; an interval yields ``inside`` / ``above`` / ``below`` and NO delta,
because the distance to a band is not a number the band supports.  Collapsing a range to
its midpoint is refused: it fabricates precision, which is what §11's own correction is
about.

**3. ``basis`` is REQUIRED and ``unknown`` is legal.**  This is the seam check's finding
at design time, and it is the dormancy question's third answer — already unequal,
somewhere nobody looks.  Our ``dpr`` is ``damage/round`` over ``rounds`` in
``fixed_length`` mode, character-scoped, post-mitigation, against the standardized
enemy.  An external figure shares the UNIT and almost certainly not the DENOMINATOR
(§5.2's comparability trap).  With a silent default, every score would render valid
while some compared two different quantities that happen to share a unit, and nothing
would fail.

**4. Scores are NOT written into a cached record.**  §10.2's cache key is
``(config_hash, engine_commit)`` and nothing else, so a ``scores`` block inside a stored
record would be served to a later run asking for a DIFFERENT baseline set.  The store
writes records unscored (``RecordStore.put`` never passes a registry) and scoring a
record is a cheap derivation anyone can redo — which is what "scoring is a report-layer
operation" means taken literally.  Widening the cache key instead would pay a
SIMULATION cache's price for a post-hoc join on data the record already holds.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Sequence

from .metrics import METRICS, MetricRegistry

if TYPE_CHECKING:                                    # pragma: no cover
    from .report import EvalReport

#: §11.1.  Separate from the declaration's, the manifest's and the record's, by s57's
#: three-objects-three-churn-rates argument: a format question, where the FINGERPRINT
#: below answers the different, content question a reader of a score actually asks.
BASELINES_SCHEMA_VERSION = 1

# ---------------------------------------------------------------------------
# The closed vocabularies (§11.1)
# ---------------------------------------------------------------------------

#: How a score must be READ.  **No catch-all, deliberately** (§11.1): s57's step-4
#: lesson is that a catch-all is unambiguous only while something OUTSIDE the data
#: supplies the missing information, and for a record read months later by an R script
#: nothing does.  Which of these three a baseline is decides whether a delta may be read
#: as a shortfall, so an ``other`` would be the one cell where that caveat goes missing.
SOURCE_KINDS: dict[str, str] = {
    "internal_run":
        "another run of this engine against our standardized enemy: a delta is "
        "meaningful",
    "external_published":
        "a figure published by someone else under their OWN enemy assumptions: a "
        "REFERENCE POINT, not a target to match (§11)",
    "hand_calculation":
        "a careful calculation made outside the engine, the user's own included: the "
        "retired target_dpr class, present so one can never be mistaken for an "
        "internal_run",
}

#: How a coordinate dimension matches a run (§11.1).  Two of these are matching rules
#: and the third is an explicit refusal to match, which is what makes "which damage
#: class is this build in?" expressible without a consumer parsing names.
MATCH_EXACT = "exact"
MATCH_CONTAINS = "contains"
MATCH_FREE = "free"
MATCH_RULES: dict[str, str] = {
    MATCH_EXACT: "the run's own field must equal the entry's value",
    MATCH_CONTAINS: "the entry declares a BAND and matches any run whose field falls "
                    "inside it",
    MATCH_FREE: "not matched at all; the dimension LABELS the entry and rides into the "
                "score",
}

#: An interval baseline's verdict.  Three values rather than one "outside", because at
#: a class boundary the PAIR of verdicts is the answer: a DPR of 33.75 is ``above`` T3's
#: D class and ``below`` its C class, i.e. between two classes (§11.3).
VERDICT_INSIDE = "inside"
VERDICT_ABOVE = "above"
VERDICT_BELOW = "below"
VERDICTS = (VERDICT_INSIDE, VERDICT_ABOVE, VERDICT_BELOW)

#: A score's state — §9.1's three-state row vocabulary, one layer up, plus the one
#: state that has no §9.1 analogue.  **None of these is ever a 0.**
STATE_SCORED = "scored"
STATE_UNMEASURED = "unmeasured"
STATE_UNAVAILABLE = "unavailable"
STATE_UNMATCHED = "unmatched"
SCORE_STATES = (STATE_SCORED, STATE_UNMEASURED, STATE_UNAVAILABLE, STATE_UNMATCHED)

#: Closed warning vocabulary for ONE score, the same contract §9.1's ``warnings`` array
#: gives a run record: a reader who must reason about a nested block to learn that a
#: comparison is not apples-to-apples will not do it.
SCORE_WARNING_CODES: dict[str, str] = {
    "basis_unknown": "the baseline does not state the basis it was computed on, so this "
                     "comparison shares a unit and may not share a denominator",
    "basis_differs": "the baseline states a basis that differs from this run's resolved "
                     "basis: the two numbers are not the same quantity",
    "reference_point": "an external_published baseline was produced under its author's "
                       "own assumptions: a reference point, not a target to match (§11)",
    "ratio_undefined": "the point baseline is exactly zero, so the ratio has no value; "
                       "the delta is still meaningful",
}

#: What an entry may say about the basis it was computed on when it cannot say more.
#: A legal, MEANINGFUL value rather than a missing field (§11.1).
BASIS_UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CoordinateDimension:
    """One axis of a source's coordinate space, with how it matches a run."""

    name: str
    match: str
    description: str = ""
    #: For ``MATCH_EXACT`` / ``MATCH_CONTAINS``: the run field this is compared against.
    #: Defaults to :attr:`name`, which is right for ``build`` and ``level`` and wrong
    #: for ``tier`` — a band over ``level`` under a different name.
    run_field: "str | None" = None

    def __post_init__(self) -> None:
        if self.match not in MATCH_RULES:
            raise ValueError(
                f"Coordinate dimension {self.name!r}: match must be one of "
                f"{sorted(MATCH_RULES)}, got {self.match!r}."
            )
        if self.match == MATCH_FREE and self.run_field is not None:
            raise ValueError(
                f"Coordinate dimension {self.name!r} is declared 'free' but names a "
                f"run_field ({self.run_field!r}). A free dimension is not matched "
                f"against the run at all; naming a field it is not compared to is the "
                f"kind of declaration that reads as a match and is not one."
            )

    @property
    def field_name(self) -> str:
        return self.run_field or self.name

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "match": self.match,
                "run_field": None if self.match == MATCH_FREE else self.field_name,
                "match_description": MATCH_RULES[self.match],
                "description": self.description}


@dataclass(frozen=True)
class Interval:
    """A baseline BAND, with each bound's closure declared (§11.1).

    Closure is a field rather than a convention because a source's bands are usually
    meant to PARTITION, and a published listing in whole numbers does not say how.
    Treantmonk's classes are the case that forced this: listed as ``26-33`` and
    ``34-41``, they leave every real value between 33 and 34 in no class at all.  The
    fix is the user's call (s58) and it is a declared INTERPRETATION, not a reading of
    the source: the upper bound is inclusive, the adjoining band's lower bound is
    exclusive at that same number, and the top band of a scale is unbounded above.
    :attr:`published` keeps the source's own listing beside the applied bounds so the
    transcription stays auditable.

    ``None`` means unbounded on that side.  At least one bound must be finite — an
    interval open at both ends matches everything and says nothing.
    """

    low: "float | None" = None
    high: "float | None" = None
    low_inclusive: bool = True
    high_inclusive: bool = True
    #: The source's own listing, verbatim, e.g. ``"26-33"``.  Audit trail for the
    #: extension above: a reader can always recover what was published.
    published: "str | None" = None

    def __post_init__(self) -> None:
        if self.low is None and self.high is None:
            raise ValueError(
                "An interval unbounded on BOTH sides matches every value and says "
                "nothing; declare at least one bound."
            )
        if self.low is not None and self.high is not None and self.low > self.high:
            raise ValueError(
                f"Interval low {self.low} is above high {self.high}."
            )

    def verdict(self, value: float) -> str:
        """Where ``value`` sits relative to this band."""
        if self.low is not None:
            if value < self.low or (value == self.low and not self.low_inclusive):
                return VERDICT_BELOW
        if self.high is not None:
            if value > self.high or (value == self.high and not self.high_inclusive):
                return VERDICT_ABOVE
        return VERDICT_INSIDE

    def contains(self, value: float) -> bool:
        return self.verdict(value) == VERDICT_INSIDE

    def label(self) -> str:
        """Standard interval notation, so the closure is visible wherever it prints."""
        left = "[" if self.low_inclusive else "("
        right = "]" if self.high_inclusive else ")"
        low = "-inf" if self.low is None else f"{self.low:,.4g}"
        high = "inf" if self.high is None else f"{self.high:,.4g}"
        if self.low is None:
            left = "("
        if self.high is None:
            right = ")"
        return f"{left}{low}, {high}{right}"

    def describe(self) -> dict[str, Any]:
        return {"low": self.low, "high": self.high,
                "low_inclusive": self.low_inclusive,
                "high_inclusive": self.high_inclusive,
                "label": self.label(), "published": self.published}


def _as_interval(raw: Any) -> "Interval | None":
    """Accept either a 2-element ``[low, high]`` closed band or the full mapping."""
    if raw is None or isinstance(raw, Interval):
        return raw
    if isinstance(raw, (list, tuple)):
        if len(raw) != 2:
            raise ValueError(
                f"An interval given as a list must have exactly two elements, got "
                f"{list(raw)!r}. Use the mapping form to declare bound closure."
            )
        low, high = raw
        return Interval(low=None if low is None else float(low),
                        high=None if high is None else float(high))
    if isinstance(raw, dict):
        unknown = set(raw) - {"low", "high", "low_inclusive", "high_inclusive",
                              "published"}
        if unknown:
            raise ValueError(f"Unknown interval key(s) {sorted(unknown)}.")
        low, high = raw.get("low"), raw.get("high")
        return Interval(
            low=None if low is None else float(low),
            high=None if high is None else float(high),
            low_inclusive=bool(raw.get("low_inclusive", True)),
            high_inclusive=bool(raw.get("high_inclusive", True)),
            published=raw.get("published"),
        )
    raise ValueError(f"An interval must be a list or a mapping, got {type(raw).__name__}.")


@dataclass(frozen=True)
class BaselineEntry:
    """One reference value at one coordinate.

    Exactly one of :attr:`value` and :attr:`interval` is set — the POINT/INTERVAL fork
    of §11.1.
    """

    coordinate: dict[str, Any]
    metric: str
    basis: str
    value: "float | None" = None
    interval: "Interval | None" = None
    note: str = ""

    def __post_init__(self) -> None:
        if (self.value is None) == (self.interval is None):
            raise ValueError(
                f"Baseline entry at {self.coordinate!r} for {self.metric!r} must "
                f"declare exactly one of value (a POINT) or interval (a BAND); got "
                f"value={self.value!r}, interval={self.interval!r}. A point and a band "
                f"score differently (§11.1), so which one this is cannot be left open."
            )
        if not self.basis:
            raise ValueError(
                f"Baseline entry at {self.coordinate!r} for {self.metric!r} declares no "
                f"basis. §11.1 makes it REQUIRED with no default: an external figure "
                f"shares the UNIT and may not share the DENOMINATOR (§5.2), and a "
                f"silent default would render every score valid while some compared two "
                f"different quantities. Use {BASIS_UNKNOWN!r} if that is the honest "
                f"answer."
            )

    @property
    def is_interval(self) -> bool:
        return self.interval is not None

    def describe(self) -> dict[str, Any]:
        return {"coordinate": dict(self.coordinate), "metric": self.metric,
                "basis": self.basis,
                "value": self.value,
                "interval": self.interval.describe() if self.interval else None,
                "note": self.note or None}


@dataclass(frozen=True)
class BaselineSource:
    """One declared source of baselines, and its entries."""

    name: str
    kind: str
    provenance: str
    dimensions: tuple[CoordinateDimension, ...]
    entries: tuple[BaselineEntry, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SOURCE_KINDS:
            raise ValueError(
                f"Baseline source {self.name!r}: kind must be one of "
                f"{sorted(SOURCE_KINDS)}, got {self.kind!r}. The vocabulary is CLOSED "
                f"and has no catch-all on purpose (§11.1): which kind a baseline is "
                f"decides whether a delta may be read as a shortfall, and nothing "
                f"outside the data supplies that for a later reader."
            )
        if not self.provenance:
            raise ValueError(
                f"Baseline source {self.name!r} declares no provenance. §11's whole "
                f"correction is that where a number came from is what makes it readable."
            )
        names = [d.name for d in self.dimensions]
        if len(names) != len(set(names)):
            raise ValueError(
                f"Baseline source {self.name!r} declares a duplicate coordinate "
                f"dimension: {names}."
            )
        declared = set(names)
        for entry in self.entries:
            unknown = set(entry.coordinate) - declared
            if unknown:
                raise ValueError(
                    f"Baseline source {self.name!r}: entry at {entry.coordinate!r} uses "
                    f"undeclared coordinate dimension(s) {sorted(unknown)}. Declared: "
                    f"{names}."
                )
            missing = declared - set(entry.coordinate)
            if missing:
                raise ValueError(
                    f"Baseline source {self.name!r}: entry at {entry.coordinate!r} is "
                    f"missing declared coordinate dimension(s) {sorted(missing)}. An "
                    f"entry with a hole in its coordinate would match more runs than it "
                    f"describes."
                )

    @property
    def dimension(self) -> dict[str, CoordinateDimension]:
        return {d.name: d for d in self.dimensions}

    @property
    def is_reference_point(self) -> bool:
        """§11: an externally published figure is a reference point, NOT a target."""
        return self.kind == "external_published"

    def metrics(self) -> list[str]:
        seen: list[str] = []
        for entry in self.entries:
            if entry.metric not in seen:
                seen.append(entry.metric)
        return seen

    def matching(self, run: dict[str, Any], metric: str) -> list[BaselineEntry]:
        """Every entry of this source that describes ``run`` for ``metric``.

        A ``free`` dimension is skipped here by construction, which is what makes a
        source return SEVERAL entries for one run — the four damage classes at a tier,
        whose verdicts together locate the build (§11.1).
        """
        dims = self.dimension
        out: list[BaselineEntry] = []
        for entry in self.entries:
            if entry.metric != metric:
                continue
            if all(_matches(dims[name], value, run)
                   for name, value in entry.coordinate.items()):
                out.append(entry)
        return out

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "kind_description": SOURCE_KINDS[self.kind],
            "is_reference_point": self.is_reference_point,
            "provenance": self.provenance,
            "description": self.description or None,
            "dimensions": [d.describe() for d in self.dimensions],
            "n_entries": len(self.entries),
            "metrics": self.metrics(),
        }


def _matches(dimension: CoordinateDimension, declared: Any,
             run: dict[str, Any]) -> bool:
    """Does one coordinate position describe this run?

    ``free`` returns True unconditionally — it is a label, not a filter.  That is the
    one branch an implementation could plausibly get backwards, and getting it backwards
    would silently score every build against every entry.
    """
    if dimension.match == MATCH_FREE:
        return True
    actual = run.get(dimension.field_name)
    if actual is None:
        return False
    if dimension.match == MATCH_EXACT:
        return actual == declared
    low, high = declared
    return low <= actual <= high


# ---------------------------------------------------------------------------
# A score
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Score:
    """One run's estimate placed against one baseline entry (§11.1).

    Four states, and **none of them is ever a 0** — the §9.1 refusal one layer up.
    ``value`` is the run's own estimate and is ``None`` outside :data:`STATE_SCORED`.
    """

    metric: str
    source: str
    source_kind: str
    state: str
    coordinate: dict[str, Any] = field(default_factory=dict)
    value: "float | None" = None
    baseline: "float | None" = None
    baseline_interval: "Interval | None" = None
    basis: "str | None" = None
    run_basis: "str | None" = None
    delta: "float | None" = None
    ratio: "float | None" = None
    verdict: "str | None" = None
    warnings: tuple[str, ...] = ()
    note: "str | None" = None

    def __post_init__(self) -> None:
        if self.state not in SCORE_STATES:
            raise ValueError(
                f"Score for {self.metric!r}: state must be one of {SCORE_STATES}, got "
                f"{self.state!r}."
            )
        if self.verdict is not None and self.verdict not in VERDICTS:
            raise ValueError(
                f"Score for {self.metric!r}: verdict must be one of {VERDICTS}, got "
                f"{self.verdict!r}."
            )

    @property
    def is_interval(self) -> bool:
        return self.baseline_interval is not None

    def describe(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "source": self.source,
            "source_kind": self.source_kind,
            "coordinate": dict(self.coordinate),
            "state": self.state,
            "value": self.value,
            "baseline": self.baseline,
            "baseline_interval": (self.baseline_interval.describe()
                                  if self.baseline_interval else None),
            "basis": self.basis,
            "run_basis": self.run_basis,
            "delta": self.delta,
            "ratio": self.ratio,
            "verdict": self.verdict,
            "warnings": [{"code": c, "message": SCORE_WARNING_CODES[c]}
                         for c in self.warnings],
            "note": self.note,
        }


# ---------------------------------------------------------------------------
# The registry
# ---------------------------------------------------------------------------

@dataclass
class BaselineRegistry:
    """The loaded set of baseline sources (§11.1).

    Its own registry, and DATA: ``baselines/*.yaml`` loaded here, the same shape as
    ``sweeps/*.yaml`` -> ``SweepDeclaration``.  A declaration on ``MetricDef`` is
    refused for the reason §11 exists — it would make the metric registry carry
    per-``(build, level)`` values, which is "a build implicitly owning the standard it
    is judged by" one layer up.

    Baseline declarations do NOT count toward the metric registry's declaration total,
    and the periodic metric-set review's trigger stays tied to that registry: a baseline
    is an INPUT datum about one coordinate, and the review's survival rule ("does anyone
    read this row?") has no meaning for an input.
    """

    sources: tuple[BaselineSource, ...] = ()

    def __post_init__(self) -> None:
        names = [s.name for s in self.sources]
        if len(names) != len(set(names)):
            raise ValueError(f"Duplicate baseline source name(s) in {names}.")

    def __len__(self) -> int:
        return len(self.sources)

    def __iter__(self):
        return iter(self.sources)

    def source(self, name: str) -> BaselineSource:
        for candidate in self.sources:
            if candidate.name == name:
                return candidate
        raise KeyError(
            f"No baseline source {name!r}. Loaded: {[s.name for s in self.sources]}."
        )

    @property
    def n_entries(self) -> int:
        return sum(len(s.entries) for s in self.sources)

    def validate_against(self, registry: MetricRegistry = METRICS) -> None:
        """Refuse an entry naming a metric that is not registered.

        The same refusal ``MetricRegistry.register_distribution`` makes, and for the
        same reason: a baseline for a metric nothing measures is a silent no-op, and a
        typo in a metric name is exactly how one gets written.
        """
        for src in self.sources:
            for entry in src.entries:
                if entry.metric not in registry:
                    raise ValueError(
                        f"Baseline source {src.name!r} declares an entry for metric "
                        f"{entry.metric!r}, which is not registered. A baseline for a "
                        f"metric nothing measures can never be scored, so it is a "
                        f"silent no-op rather than a reference. Registered scalars: "
                        f"{[d.name for d in registry.scalars()]}."
                    )

    def fingerprint(self) -> str:
        """A content fingerprint over the loaded declarations and entries.

        A fingerprint rather than only a version number because the question a reader of
        a score asks is *which baseline set scored this*, which is a CONTENT question;
        :data:`BASELINES_SCHEMA_VERSION` answers the different, format question.  Same
        role ``sweep.registry_fingerprint`` plays for the metric registry, and quoted
        beside it on a scored record.
        """
        payload = json.dumps(
            [{"source": s.describe(),
              "entries": [e.describe() for e in s.entries]} for s in self.sources],
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def describe(self) -> dict[str, Any]:
        return {
            "baselines_schema_version": BASELINES_SCHEMA_VERSION,
            "baselines_fingerprint": self.fingerprint(),
            "n_sources": len(self.sources),
            "n_entries": self.n_entries,
            "sources": [s.describe() for s in self.sources],
        }


# ---------------------------------------------------------------------------
# Loading (§11.1 — committed YAML, the sweeps/*.yaml precedent)
# ---------------------------------------------------------------------------

DEFAULT_BASELINE_ROOT = Path("baselines")


def parse_source(data: dict[str, Any], *, where: str = "<dict>") -> BaselineSource:
    """One source declaration, from the parsed YAML."""
    if not isinstance(data, dict):
        raise ValueError(f"{where}: a baseline declaration must be a mapping.")
    version = data.get("baselines_schema_version")
    if version != BASELINES_SCHEMA_VERSION:
        raise ValueError(
            f"{where}: baselines_schema_version is {version!r}; this reader "
            f"understands {BASELINES_SCHEMA_VERSION}. A declaration whose version is "
            f"absent or newer is refused rather than read on a guess."
        )
    unknown = set(data) - {
        "baselines_schema_version", "name", "kind", "provenance", "description",
        "dimensions", "entries",
    }
    if unknown:
        raise ValueError(
            f"{where}: unknown key(s) {sorted(unknown)} in the baseline declaration. "
            f"A key that is silently ignored is a declaration the reader does not honour."
        )
    dims = tuple(
        CoordinateDimension(
            name=d["name"], match=d["match"],
            description=d.get("description", ""),
            run_field=d.get("run_field"),
        )
        for d in data.get("dimensions") or []
    )
    entries: list[BaselineEntry] = []
    for raw in data.get("entries") or []:
        entries.append(BaselineEntry(
            coordinate=dict(raw.get("coordinate") or {}),
            metric=raw["metric"],
            basis=raw.get("basis", ""),
            value=raw.get("value"),
            interval=_as_interval(raw.get("interval")),
            note=raw.get("note", ""),
        ))
    return BaselineSource(
        name=data["name"], kind=data["kind"], provenance=data["provenance"],
        description=data.get("description", ""),
        dimensions=dims, entries=tuple(entries),
    )


def load_source(path: "str | Path") -> BaselineSource:
    import yaml

    target = Path(path)
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    return parse_source(data, where=str(target))


def load_registry(root: "str | Path" = DEFAULT_BASELINE_ROOT, *,
                  registry: MetricRegistry = METRICS) -> BaselineRegistry:
    """Load every ``*.yaml`` under ``root``, in sorted order for a stable fingerprint."""
    base = Path(root)
    paths = sorted(base.glob("*.yaml")) if base.is_dir() else []
    loaded = BaselineRegistry(sources=tuple(load_source(p) for p in paths))
    loaded.validate_against(registry)
    return loaded


# ---------------------------------------------------------------------------
# Scoring — a REPORT-LAYER operation (§11.1)
# ---------------------------------------------------------------------------

def run_coordinate(report: "EvalReport") -> dict[str, Any]:
    """The run's own position, as the fields a coordinate may match on."""
    config = report.provenance.config
    return {"build": config["build"], "level": config["level"],
            "mode": config["mode"], "attribution": config["attribution"]}


def run_basis(report: "EvalReport", metric: str) -> str:
    """How THIS run computed ``metric``, in the same vocabulary an entry declares.

    Deliberately a composition of facts the provenance block already resolved rather
    than a new declaration: unit, denominator, mode and attribution are the four that
    decide whether two numbers of the same name are the same quantity (§5.2, §5.3).
    """
    definition = report.registry[metric]
    config = report.provenance.config
    return (f"{definition.unit} per {definition.denominator}; "
            f"mode={config['mode']}; attribution={config['attribution']}")


def _score_one(report: "EvalReport", src: BaselineSource,
               entry: BaselineEntry) -> Score:
    metric = entry.metric
    basis_now = run_basis(report, metric)
    warnings: list[str] = []
    if src.is_reference_point:
        warnings.append("reference_point")
    if entry.basis == BASIS_UNKNOWN:
        warnings.append("basis_unknown")
    elif entry.basis != basis_now:
        warnings.append("basis_differs")

    common: dict[str, Any] = {
        "metric": metric, "source": src.name, "source_kind": src.kind,
        "coordinate": dict(entry.coordinate),
        "baseline": entry.value,
        "baseline_interval": entry.interval,
        "basis": entry.basis, "run_basis": basis_now,
    }

    value = report.values.get(metric)
    if value is None or not value.available:
        return Score(state=STATE_UNAVAILABLE, warnings=tuple(warnings),
                     note=(value.note if value is not None and value.note
                           else "the run structurally cannot produce this metric"),
                     **common)
    if not value.measured:
        return Score(state=STATE_UNMEASURED, warnings=tuple(warnings),
                     note=(value.note or
                           "available, but this run produced no estimate (§9.1)"),
                     **common)

    if entry.is_interval:
        verdict = entry.interval.verdict(value.value)   # type: ignore[union-attr]
        return Score(state=STATE_SCORED, value=value.value, verdict=verdict,
                     warnings=tuple(warnings), note=entry.note or None, **common)

    delta = value.value - entry.value        # type: ignore[operator]
    if entry.value == 0:
        warnings.append("ratio_undefined")
        ratio = None
    else:
        ratio = value.value / entry.value    # type: ignore[operator]
    return Score(state=STATE_SCORED, value=value.value, delta=delta, ratio=ratio,
                 warnings=tuple(warnings), note=entry.note or None, **common)


def score(report: "EvalReport",
          baselines: BaselineRegistry) -> list[Score]:
    """Every score this run and this baseline set produce together (§11.1).

    Includes :data:`STATE_UNMATCHED` rows: a source that covers levels 11-20 says
    nothing about L4, and that SILENCE is information rather than an error — so a
    reader is told the source had nothing for this coordinate instead of being left to
    infer it from an absent row.
    """
    run = run_coordinate(report)
    out: list[Score] = []
    for src in baselines:
        for metric in src.metrics():
            matched = src.matching(run, metric)
            if not matched:
                out.append(Score(
                    metric=metric, source=src.name, source_kind=src.kind,
                    state=STATE_UNMATCHED,
                    run_basis=(run_basis(report, metric)
                               if metric in report.registry else None),
                    note=(f"{src.name} declares no entry for "
                          f"{_run_label(run)} on {metric}"),
                ))
                continue
            out.extend(_score_one(report, src, entry) for entry in matched)
    return out


def _run_label(run: dict[str, Any]) -> str:
    return f"{run.get('build')}@L{run.get('level')}"


def scores_block(report: "EvalReport",
                 baselines: BaselineRegistry) -> dict[str, Any]:
    """The run record's ``scores`` section (§11.2).

    **Absent rather than present-and-empty when no baselines were supplied** — that
    decision lives in ``artifact.report_to_dict``; this function is only called when
    they were.  "Not scored" and "scored, nothing matched" are different facts, and the
    project already distinguishes exactly that pair twice (blank vs ``*`` in the tidy
    frame, ``unavailable`` vs ``unmeasured`` in a row).
    """
    rows = score(report, baselines)
    return {
        "baselines_schema_version": BASELINES_SCHEMA_VERSION,
        "baselines_fingerprint": baselines.fingerprint(),
        "sources": [s.describe() for s in baselines],
        "scores": [s.describe() for s in rows],
    }


# ---------------------------------------------------------------------------
# The tidy score frame (§11.2) — ONE renderer, built from the block above
# ---------------------------------------------------------------------------

#: The score frame's own grain: ``(run, metric, source, coordinate)``.  SEPARATE from
#: the run record's tidy frame, whose grain is ``(run, metric)`` — two sources for one
#: metric are two rows here, and folding them into that frame would put a blank on every
#: row that has no baseline and change what one row of it means (the s46 flattened-key
#: failure one layer up).
SCORE_RUN_COLUMNS = ("run_id", "config_hash", "build", "level", "engine_commit",
                     "baselines_fingerprint")
SCORE_VALUE_COLUMNS = ("metric", "source", "source_kind", "coordinate", "state",
                       "value", "baseline", "baseline_low", "baseline_high",
                       "baseline_low_inclusive", "baseline_high_inclusive",
                       "baseline_band", "baseline_published",
                       "delta", "ratio", "verdict", "basis", "run_basis",
                       "warnings", "note")
SCORE_COLUMNS = SCORE_RUN_COLUMNS + SCORE_VALUE_COLUMNS


def scores_to_rows(report: "EvalReport",
                   baselines: BaselineRegistry) -> list[dict[str, Any]]:
    """One flat dict per score — the tidy long form of the block above.

    Built from the SAME ``scores_block`` the JSON serializes, so the two are two views
    of one computation and cannot disagree: the s57 cached-versus-computed lesson
    applied before it could bite.
    """
    from .artifact import run_id as _run_id, _config_hash

    block = scores_block(report, baselines)
    config = report.provenance.config
    common = {
        "run_id": _run_id(report),
        "config_hash": _config_hash(report),
        "build": config["build"],
        "level": config["level"],
        "engine_commit": report.provenance.engine_commit,
        "baselines_fingerprint": block["baselines_fingerprint"],
    }
    rows: list[dict[str, Any]] = []
    for row in block["scores"]:
        interval = row["baseline_interval"]
        flat = dict(common)
        flat.update({
            "metric": row["metric"],
            "source": row["source"],
            "source_kind": row["source_kind"],
            # A dict has no tidy cell, and §5.4 refuses a parsed string — so the frame
            # carries the SORTED key=value rendering for display and a consumer that
            # needs the parts reads the JSON block, which keeps them as a dict.
            "coordinate": ";".join(f"{k}={row['coordinate'][k]}"
                                   for k in sorted(row["coordinate"])) or None,
            "state": row["state"],
            "value": row["value"],
            "baseline": row["baseline"],
            # Each bound and its CLOSURE get their own column: an exclusive bound and
            # an inclusive one at the same number are different bands, and a frame that
            # printed only the numbers could not tell them apart. `baseline_band` is the
            # same fact in interval notation for a human skimming the frame.
            "baseline_low": interval["low"] if interval else None,
            "baseline_high": interval["high"] if interval else None,
            "baseline_low_inclusive": interval["low_inclusive"] if interval else None,
            "baseline_high_inclusive": interval["high_inclusive"] if interval else None,
            "baseline_band": interval["label"] if interval else None,
            "baseline_published": interval["published"] if interval else None,
            "delta": row["delta"],
            "ratio": row["ratio"],
            "verdict": row["verdict"],
            "basis": row["basis"],
            "run_basis": row["run_basis"],
            "warnings": ";".join(w["code"] for w in row["warnings"]) or None,
            "note": row["note"],
        })
        rows.append(flat)
    return rows


def write_scores_csv(report: "EvalReport", baselines: BaselineRegistry,
                     path: "str | Path", *, append: bool = False) -> Path:
    """Write the tidy score frame (§11.2)."""
    import csv

    from .artifact import _csv_field

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = scores_to_rows(report, baselines)
    exists = target.exists() and target.stat().st_size > 0
    with target.open("a" if append else "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if not (append and exists):
            writer.writerow(SCORE_COLUMNS)
        for row in rows:
            writer.writerow([_csv_field(row.get(c)) for c in SCORE_COLUMNS])
    return target


def summarize(rows: "Sequence[Score] | Iterable[Score]") -> dict[str, int]:
    """Counts by state — what a console line reports about a score set.

    One traversal feeding both the count and its breakdown, per s56's
    ``unconverged_verdicts`` rule: a count and a breakdown of that count must not be
    computable from two different lists.
    """
    counts = {state: 0 for state in SCORE_STATES}
    for row in rows:
        counts[row.state] += 1
    return counts
