"""
Mechanism tests for the §11 baselines registry (framework step 8d, s58).

Per ``validate-mechanism-not-build-value``: nothing here asserts a DPR value.  What is
asserted is that a reference is declared, matched, scored and serialized the way §11.1-
§11.3 lock it, and that each of the four score states stays distinguishable from a zero.

THE ROLL CALL (per-feature ritual step 5 — written BEFORE the tests, because it is the
instrument that finds the gaps rather than documentation of work already done)
===============================================================================
One row per declaration this change touches, one column naming the fixture that covers
each VALUE.  An empty cell is the finding.

| declaration / branch            | value              | fixture                                        |
|---------------------------------|--------------------|------------------------------------------------|
| ``BaselineSource.kind``         | external_published | ``treantmonk_damage_classes`` (PRODUCTION)     |
|                                 | internal_run       | ``_internal_source`` — TEST-ONLY, see below     |
|                                 | hand_calculation   | ``_hand_source`` — TEST-ONLY BY DESIGN, below   |
|                                 | (unknown kind)     | ``test_the_source_kind_vocabulary_is_closed``   |
| ``CoordinateDimension.match``   | exact              | ``_internal_source`` (build + level)           |
|                                 | contains           | ``treantmonk`` tier → level band (PRODUCTION)  |
|                                 | free               | ``treantmonk`` damage_class (PRODUCTION)       |
|                                 | (unknown rule)     | ``test_the_match_vocabulary_is_closed``        |
| entry value kind                | point              | ``_internal_source``                           |
|                                 | interval           | ``treantmonk`` (PRODUCTION)                    |
|                                 | both / neither     | ``test_an_entry_declares_exactly_one_of_...``  |
| interval verdict                | inside             | ``test_the_four_classes_LOCATE_a_run``         |
|                                 | above              | ``test_the_four_classes_LOCATE_a_run``         |
|                                 | below              | ``test_the_four_classes_LOCATE_a_run``         |
| ``Interval.low_inclusive`` /    | inclusive          | ``treantmonk`` class D's floor (PRODUCTION)    |
| ``Interval.high_inclusive``     | exclusive          | ``treantmonk`` classes C/B/A's floors          |
| ``Interval.high``               | finite             | ``treantmonk`` classes D/C/B (PRODUCTION)      |
|                                 | unbounded (None)   | ``treantmonk`` class A (PRODUCTION)            |
|                                 | both ends open     | ``test_an_interval_open_at_both_ends_...``     |
| ``interval`` declaration form   | 2-element list     | ``test_an_interval_may_be_given_as_a_list``    |
|                                 | full mapping       | ``treantmonk`` (PRODUCTION)                    |
| point score                     | delta + ratio      | ``test_a_point_baseline_yields_delta_...``     |
|                                 | baseline == 0      | ``test_a_zero_point_baseline_refuses_...``    |
| ``Score.state``                 | scored             | ``test_the_four_classes_LOCATE_a_run``         |
|                                 | unavailable        | ``test_an_unavailable_metric_scores_...``      |
|                                 | unmeasured         | ``test_an_unmeasured_metric_scores_...``       |
|                                 | unmatched          | ``test_a_source_that_says_nothing_...``        |
| ``basis``                       | unknown            | ``treantmonk`` (PRODUCTION)                    |
|                                 | differs from run   | ``test_a_basis_that_DIFFERS_is_warned``        |
|                                 | agrees with run    | ``test_a_basis_that_AGREES_raises_no_...``     |
|                                 | absent (refused)   | ``test_basis_is_REQUIRED_with_no_default``     |
| metric name                     | registered         | every scoring fixture                          |
|                                 | unregistered       | ``test_a_baseline_for_an_unregistered_...``    |
| ``baselines_schema_version``    | 1                  | ``test_the_production_source_loads``           |
|                                 | absent / newer     | ``test_an_unknown_schema_version_is_refused``  |
| fingerprint                     | stable             | ``test_the_fingerprint_is_CONTENT_addressed``  |
|                                 | changes on content | ``test_the_fingerprint_is_CONTENT_addressed``  |
| record ``scores`` key           | absent (no bl.)    | ``test_the_scores_key_is_ABSENT_...``          |
|                                 | present (bl.)      | ``test_the_scores_key_is_ABSENT_...``          |
| cache soundness                 | store writes bare  | ``test_the_record_STORE_writes_records_...``   |

TWO EMPTY PRODUCTION CELLS, NAMED RATHER THAN HIDDEN (the s48 precedent — writing this
table first is what exposed two declaration values with no production fixture that
session, and the same thing happens here):

* ``internal_run`` has NO production source until roadmap item 5c, which is the first
  thing that wants to score one run against another.  It is covered by a test fixture
  only, and that is a gap in the CORPUS, not in the tests.
* ``hand_calculation`` has no production source **by design**.  §11's correction retires
  the user's own ``target_dpr`` figures, so shipping one would re-add the thing the
  correction removed.  The kind exists so that if one is ever entered it cannot be read
  as an ``internal_run``.  This cell is expected to stay empty.

WHAT THIS MODULE DELIBERATELY DOES NOT ASSERT
---------------------------------------------
Where a build actually lands against Treantmonk's classes.  That is a DPR claim, it
would move with every re-baseline (step 9 is next and re-baselines every seeded number
by construction), and §11 is explicit that an external figure is a reference point
rather than a target — so an assertion that War Angel "should" be class C would be the
retired guide-replication habit coming back in through §11's own front door.  The
verdict-vocabulary tests therefore drive the three branches with SYNTHETIC values and
let the real run only prove that the plumbing produces a verdict at all.
"""

from __future__ import annotations

import json
import logging

import pytest

from src.evaluation import artifact as artifact_module
from src.evaluation.baselines import (
    BASELINES_SCHEMA_VERSION,
    BASIS_UNKNOWN,
    MATCH_CONTAINS,
    MATCH_EXACT,
    MATCH_FREE,
    MATCH_RULES,
    SCORE_STATES,
    SOURCE_KINDS,
    STATE_SCORED,
    STATE_UNAVAILABLE,
    STATE_UNMATCHED,
    STATE_UNMEASURED,
    VERDICT_ABOVE,
    VERDICT_BELOW,
    VERDICT_INSIDE,
    VERDICTS,
    BaselineEntry,
    BaselineRegistry,
    BaselineSource,
    CoordinateDimension,
    Interval,
    _as_interval,
    load_registry,
    load_source,
    parse_source,
    run_basis,
    score,
    scores_block,
    scores_to_rows,
    summarize,
)
from src.evaluation.config import RunConfig
from src.evaluation.enemy import resolve
from src.evaluation.console import render
from src.evaluation.metrics import METRICS
from src.evaluation.report import build_report
from src.evaluation.runner import simulate

logging.disable(logging.WARNING)

PRODUCTION_SOURCE = "treantmonk_damage_classes"


# ---------------------------------------------------------------------------
# Fixtures — one per roll-call row that production does not cover
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def production() -> BaselineRegistry:
    """The committed ``baselines/`` set."""
    return load_registry()


def _internal_source(*, metric: str = "dpr", value: float = 30.0,
                     basis: str | None = None,
                     build: str = "war_angel", level: int = 13) -> BaselineSource:
    """``internal_run`` + ``exact`` matching + a POINT value — three roll-call cells
    production does not cover, and will not until item 5c."""
    return BaselineSource(
        name="prior_run",
        kind="internal_run",
        provenance="a synthetic prior run of this engine, for the point-score branch",
        dimensions=(
            CoordinateDimension(name="build", match=MATCH_EXACT),
            CoordinateDimension(name="level", match=MATCH_EXACT),
        ),
        entries=(
            BaselineEntry(coordinate={"build": build, "level": level}, metric=metric,
                          basis=BASIS_UNKNOWN if basis is None else basis, value=value),
        ),
    )


def _hand_source() -> BaselineSource:
    """``hand_calculation`` — the kind that is test-only BY DESIGN (§11.3)."""
    return BaselineSource(
        name="a_hand_calculation",
        kind="hand_calculation",
        provenance="a hand calculation, present only to prove the kind is reachable",
        dimensions=(CoordinateDimension(name="level", match=MATCH_EXACT),),
        entries=(BaselineEntry(coordinate={"level": 13}, metric="dpr",
                               basis=BASIS_UNKNOWN, value=30.0),),
    )


@pytest.fixture(scope="module")
def war_angel_report():
    """One short real run — the plumbing's subject, never the source of a DPR claim."""
    config = RunConfig(build="war_angel", level=13, n_days=60, enemy="baseline")
    return build_report(simulate(config))


# ---------------------------------------------------------------------------
# The production source
# ---------------------------------------------------------------------------

def test_the_production_source_loads(production):
    """The committed set loads, validates against the metric registry, and is what
    §11.3 says ships: one ``external_published`` source, 16 interval entries."""
    assert len(production) == 1
    src = production.source(PRODUCTION_SOURCE)
    assert src.kind == "external_published"
    assert src.is_reference_point is True
    assert len(src.entries) == 16
    assert src.metrics() == ["dpr"]
    assert all(e.is_interval for e in src.entries)
    assert all(e.basis == BASIS_UNKNOWN for e in src.entries), (
        "every Treantmonk entry must declare basis unknown: the figures were produced "
        "under his own assumptions, which this project does not know"
    )
    production.validate_against(METRICS)


def test_the_production_source_cites_its_provenance(production):
    """§11's correction is that where a number came from is what makes it readable, and
    the per-feature ritual's rule 1 wants the source CITED rather than remembered."""
    src = production.source(PRODUCTION_SOURCE)
    assert "36_the_reanimating_bloodshot" in src.provenance
    assert "107" in src.provenance, "the provenance must cite the line, not just the file"


def test_the_four_classes_LOCATE_a_run(production, war_angel_report):
    """A ``free`` dimension is what makes "which class is this build in?" expressible.

    Covers THREE roll-call cells at once — ``match=free``, ``match=contains`` and
    ``state=scored`` — and asserts the STRUCTURE of the answer rather than which class
    comes out, for the reason the module docstring gives.
    """
    rows = score(war_angel_report, production)
    assert len(rows) == 4, "all four damage classes at the run's tier, not one"
    assert {r.coordinate["damage_class"] for r in rows} == {"A", "B", "C", "D"}
    assert all(r.state == STATE_SCORED for r in rows)
    assert all(r.verdict in VERDICTS for r in rows)
    assert all(r.delta is None and r.ratio is None for r in rows), (
        "an interval baseline must yield NO delta: the distance to a band is not a "
        "number the band supports (§11.1)"
    )
    # Every entry matched is at the run's own tier, which is the `contains` branch.
    assert all(r.coordinate["tier"] == [11, 16] for r in rows)
    # The verdicts must be CONSISTENT with the class ordering: once a run is at or
    # above a class it cannot be below a lower one. A below/inside/above sequence read
    # down from A to D is monotone, and a renderer that scrambled the pairing would
    # break it.
    order = {VERDICT_BELOW: 0, VERDICT_INSIDE: 1, VERDICT_ABOVE: 2}
    by_class = {r.coordinate["damage_class"]: order[r.verdict] for r in rows}
    descending = [by_class[c] for c in ("A", "B", "C", "D")]
    assert descending == sorted(descending), (
        f"verdicts must not contradict the class ordering, got {by_class}"
    )
    # Since the bands partition the scale above D's floor (user, s58), a run at or
    # above it lands in EXACTLY ONE class -- so the four verdicts locate it rather
    # than merely bracketing it. WHICH class is a DPR claim and is not asserted.
    inside = [r.coordinate["damage_class"] for r in rows
              if r.verdict == VERDICT_INSIDE]
    assert len(inside) == 1, (
        f"exactly one class must contain the run, got {inside}; zero would mean the "
        f"run is below the whole scale, which is possible but is a different finding"
    )


def test_the_published_classes_TILE_over_the_integers(production):
    """What WARRANTS the bound extension, asserted rather than assumed.

    The applied bounds are a declared interpretation (§11.1), and the thing that makes
    it an interpretation of THIS source rather than an invention is that the published
    listing already tiles: in all four tiers each class begins exactly one above the
    ceiling of the class below it.  If a future re-transcription broke that, the
    extension would no longer be warranted — so the premise is a test, not a comment.
    """
    src = production.source(PRODUCTION_SOURCE)
    ascending = ("D", "C", "B", "A")
    for tier_band in ([1, 4], [5, 10], [11, 16], [17, 20]):
        published = {}
        for entry in src.entries:
            if entry.coordinate["tier"] == tier_band:
                low, high = entry.interval.published.split("-")
                published[entry.coordinate["damage_class"]] = (int(low), int(high))
        assert set(published) == set(ascending)
        for lower, upper in zip(ascending, ascending[1:]):
            assert published[lower][1] + 1 == published[upper][0], (
                f"tier {tier_band}: published {upper} ({published[upper]}) does not "
                f"begin one above {lower} ({published[lower]}), so the bound extension "
                f"is not warranted for this listing"
            )


def test_the_bands_PARTITION_the_scale_above_D(production):
    """The extension's payoff, as an assertion (user, s58).

    Before it, the bands tiled only over the integers: at tier 3, D topped at 33 and C
    started at 34, so **every real value between them belonged to no class** — found
    while writing this roll call, against a first draft of §11.3 that claimed they tile
    without qualification.  Now the upper bound is inclusive, the adjoining lower bound
    exclusive at that same number, and A is unbounded above, so exactly one class
    contains any value at or above D's floor.

    Below D's floor there is deliberately still no class, and that is a real answer
    rather than a gap: the source says nothing about output beneath its own scale.
    """
    src = production.source(PRODUCTION_SOURCE)
    tier3 = {e.coordinate["damage_class"]: e.interval
             for e in src.matching({"build": "x", "level": 13}, "dpr")}

    # The old gap, and both sides of the shared boundary.
    for value, expected in ((33.0, "D"), (33.5, "C"), (33.75, "C"), (34.0, "C"),
                            (41.0, "C"), (41.000001, "B"), (1e6, "A")):
        holding = [cls for cls, band in tier3.items() if band.contains(value)]
        assert holding == [expected], f"{value} -> {holding}, expected [{expected}]"

    # Exactly one class, everywhere at or above D's floor -- a partition, not a cover.
    floor = tier3["D"].low
    for value in (floor, floor + 0.5, 30.0, 33.0, 33.5, 49.0, 49.5, 200.0):
        assert sum(band.contains(value) for band in tier3.values()) == 1, value
    # ... and none below it.
    assert all(not band.contains(floor - 0.01) for band in tier3.values())


def test_the_published_range_SURVIVES_the_extension(production):
    """The applied bounds are an interpretation, so the source's own listing stays
    recoverable from the data rather than only from the commit message."""
    src = production.source(PRODUCTION_SOURCE)
    assert all(e.interval.published for e in src.entries)
    tier3 = {e.coordinate["damage_class"]: e.interval
             for e in src.matching({"build": "x", "level": 13}, "dpr")}
    assert tier3["C"].published == "34-41"
    assert tier3["C"].low == 33.0 and tier3["C"].low_inclusive is False, (
        "the APPLIED lower bound is the band below's ceiling, exclusive"
    )
    assert tier3["A"].high is None, "the top band of a scale is unbounded above"
    assert tier3["A"].published == "50-57"


# ---------------------------------------------------------------------------
# The closed vocabularies (§11.1)
# ---------------------------------------------------------------------------

def test_the_source_kind_vocabulary_is_closed():
    """Three values and NO catch-all (§11.1).

    The absence is the point: s57's step-4 lesson is that a catch-all is unambiguous
    only while something outside the data supplies the missing information, and for a
    record read months later nothing supplies which kind a baseline is — which is
    exactly the fact deciding whether a delta may be read as a shortfall.
    """
    assert set(SOURCE_KINDS) == {"internal_run", "external_published",
                                 "hand_calculation"}
    assert "other" not in SOURCE_KINDS and "unknown" not in SOURCE_KINDS
    with pytest.raises(ValueError, match="kind must be one of"):
        BaselineSource(name="x", kind="other", provenance="p", dimensions=(), entries=())


def test_every_source_kind_is_CONSTRUCTIBLE():
    """One fixture per value of the kind vocabulary — the roll call's first row.

    ``internal_run`` and ``hand_calculation`` have no production instance, so without
    this they would be declared values with no fixture at all.
    """
    kinds = {_internal_source().kind, _hand_source().kind,
             load_registry().source(PRODUCTION_SOURCE).kind}
    assert kinds == set(SOURCE_KINDS)


def test_the_match_vocabulary_is_closed():
    assert set(MATCH_RULES) == {MATCH_EXACT, MATCH_CONTAINS, MATCH_FREE}
    with pytest.raises(ValueError, match="match must be one of"):
        CoordinateDimension(name="tier", match="overlaps")


def test_a_free_dimension_may_not_name_a_run_field():
    """A declaration that reads as a match and is not one.

    ``free`` means "not compared to the run at all"; naming a field it is not compared
    to is the kind of thing a later reader would take for a matching rule.
    """
    with pytest.raises(ValueError, match="declared 'free' but names a run_field"):
        CoordinateDimension(name="damage_class", match=MATCH_FREE, run_field="build")


def test_the_score_state_vocabulary_has_four_values():
    """And ``unmatched`` is the one with no §9.1 analogue."""
    assert SCORE_STATES == (STATE_SCORED, STATE_UNMEASURED, STATE_UNAVAILABLE,
                            STATE_UNMATCHED)


# ---------------------------------------------------------------------------
# Entry refusals
# ---------------------------------------------------------------------------

def test_an_entry_declares_exactly_one_of_value_or_interval():
    with pytest.raises(ValueError, match="exactly one of value"):
        BaselineEntry(coordinate={"level": 1}, metric="dpr", basis="x")
    with pytest.raises(ValueError, match="exactly one of value"):
        BaselineEntry(coordinate={"level": 1}, metric="dpr", basis="x",
                      value=1.0, interval=(1.0, 2.0))


def test_basis_is_REQUIRED_with_no_default():
    """The seam check's finding at design time, as a refusal.

    Our ``dpr`` is ``damage/round`` over ``rounds`` in ``fixed_length`` mode; an
    external figure shares the UNIT and may not share the DENOMINATOR (§5.2).  With a
    silent default every score would render valid while some compared two different
    quantities that happen to share a unit, and NOTHING would fail — the dormancy
    question's third answer, already unequal somewhere nobody looks.
    """
    with pytest.raises(ValueError, match="declares no basis"):
        BaselineEntry(coordinate={"level": 1}, metric="dpr", basis="", value=1.0)
    # ... and `unknown` is a legal, meaningful value rather than a missing field.
    entry = BaselineEntry(coordinate={"level": 1}, metric="dpr",
                          basis=BASIS_UNKNOWN, value=1.0)
    assert entry.basis == BASIS_UNKNOWN


def test_an_interval_may_not_be_inverted():
    with pytest.raises(ValueError, match="is above high"):
        Interval(low=9.0, high=2.0)


def test_an_interval_open_at_both_ends_is_refused():
    """It matches every value and therefore says nothing — the same class of refusal as
    a baseline with no basis: a declaration that cannot be wrong."""
    with pytest.raises(ValueError, match="unbounded on BOTH sides"):
        Interval()


def test_an_interval_may_be_given_as_a_list():
    """The convenience form a simple source or a fixture uses: a 2-element list is a
    CLOSED band, and anything needing bound closure uses the mapping."""
    band = _as_interval([2, 5])
    assert (band.low, band.high) == (2.0, 5.0)
    assert band.low_inclusive and band.high_inclusive
    assert band.label() == "[2, 5]"
    with pytest.raises(ValueError, match="exactly two elements"):
        _as_interval([1, 2, 3])


def test_the_interval_label_shows_the_CLOSURE():
    """The closure is load-bearing, so it must be visible wherever a band prints: two
    bands sharing a number differ only in which side is open."""
    assert Interval(low=33, high=41, low_inclusive=False).label() == "(33, 41]"
    assert Interval(low=26, high=33).label() == "[26, 33]"
    assert Interval(low=49, high=None, low_inclusive=False).label() == "(49, inf)"
    assert Interval(low=None, high=10).label() == "(-inf, 10]"


def test_an_unbounded_band_still_reaches_a_verdict():
    """Class A is unbounded above, so nothing can ever be ABOVE it — and the branch that
    would compare against a None bound must not raise."""
    top = Interval(low=49, high=None, low_inclusive=False)
    assert top.verdict(49.0) == VERDICT_BELOW
    assert top.verdict(49.5) == VERDICT_INSIDE
    assert top.verdict(1e9) == VERDICT_INSIDE
    bottom = Interval(low=None, high=10)
    assert bottom.verdict(-1e9) == VERDICT_INSIDE
    assert bottom.verdict(10.0) == VERDICT_INSIDE
    assert bottom.verdict(10.0001) == VERDICT_ABOVE


def test_a_shared_boundary_belongs_to_exactly_one_band():
    """The whole point of declaring closure: at the number two bands share, the lower
    one's inclusive ceiling takes it and the upper one's exclusive floor does not."""
    lower = Interval(low=26, high=33)
    upper = Interval(low=33, high=41, low_inclusive=False)
    assert lower.contains(33.0) and not upper.contains(33.0)
    assert not lower.contains(33.0001) and upper.contains(33.0001)


def test_an_entrys_coordinate_must_match_the_declared_dimensions():
    """Both directions: an undeclared dimension, and a HOLE in the coordinate.

    The hole is the one that matters — an entry missing a matched dimension would
    match more runs than it describes, silently.
    """
    dims = (CoordinateDimension(name="build", match=MATCH_EXACT),
            CoordinateDimension(name="level", match=MATCH_EXACT))
    with pytest.raises(ValueError, match="undeclared coordinate dimension"):
        BaselineSource(name="s", kind="internal_run", provenance="p", dimensions=dims,
                       entries=(BaselineEntry(coordinate={"build": "x", "level": 1,
                                                          "tier": 2},
                                              metric="dpr", basis="b", value=1.0),))
    with pytest.raises(ValueError, match="missing declared coordinate dimension"):
        BaselineSource(name="s", kind="internal_run", provenance="p", dimensions=dims,
                       entries=(BaselineEntry(coordinate={"build": "x"}, metric="dpr",
                                              basis="b", value=1.0),))


def test_a_source_must_declare_its_provenance():
    with pytest.raises(ValueError, match="declares no provenance"):
        BaselineSource(name="s", kind="internal_run", provenance="", dimensions=(),
                       entries=())


def test_a_baseline_for_an_unregistered_metric_is_refused():
    """The same refusal ``register_distribution`` makes, for the same reason: a baseline
    for a metric nothing measures can never be scored, so it is a silent no-op."""
    bad = BaselineRegistry(sources=(_internal_source(metric="dpr_but_misspelled"),))
    with pytest.raises(ValueError, match="which is not registered"):
        bad.validate_against(METRICS)


def test_duplicate_source_names_are_refused():
    with pytest.raises(ValueError, match="Duplicate baseline source name"):
        BaselineRegistry(sources=(_internal_source(), _internal_source()))


# ---------------------------------------------------------------------------
# Loading (§11.1)
# ---------------------------------------------------------------------------

def test_an_unknown_schema_version_is_refused(tmp_path):
    """Absent and newer are both refused rather than read on a guess."""
    for version in (None, BASELINES_SCHEMA_VERSION + 1):
        payload: dict = {"name": "s", "kind": "internal_run", "provenance": "p",
                         "dimensions": [], "entries": []}
        if version is not None:
            payload["baselines_schema_version"] = version
        with pytest.raises(ValueError, match="baselines_schema_version"):
            parse_source(payload)


def test_an_unknown_declaration_key_is_refused():
    """A key silently ignored is a declaration the reader does not honour — the same
    strictness ``SweepDeclaration`` applies one object over."""
    with pytest.raises(ValueError, match="unknown key"):
        parse_source({"baselines_schema_version": BASELINES_SCHEMA_VERSION,
                      "name": "s", "kind": "internal_run", "provenance": "p",
                      "dimensions": [], "entries": [], "sources": []})


def test_the_loader_round_trips_the_production_yaml(tmp_path, production):
    """Loading the committed file twice gives the same fingerprint, and loading a
    directory with no YAML gives an empty registry rather than an error."""
    direct = load_source("baselines/treantmonk_damage_classes.yaml")
    assert direct.name == PRODUCTION_SOURCE
    assert len(load_registry(tmp_path)) == 0


def test_the_fingerprint_is_CONTENT_addressed(production):
    """A fingerprint rather than only a version number, because the question a reader of
    a score asks is *which baseline set scored this* — a content question."""
    assert production.fingerprint() == load_registry().fingerprint()
    assert len(production.fingerprint()) == 16
    widened = BaselineRegistry(sources=production.sources + (_internal_source(),))
    assert widened.fingerprint() != production.fingerprint()
    # ... and a changed VALUE moves it, not just a changed source count.
    moved = BaselineRegistry(sources=(_internal_source(value=31.0),))
    unmoved = BaselineRegistry(sources=(_internal_source(value=30.0),))
    assert moved.fingerprint() != unmoved.fingerprint()


# ---------------------------------------------------------------------------
# Scoring — the four states and the two value kinds
# ---------------------------------------------------------------------------

def test_a_point_baseline_yields_delta_and_ratio(war_angel_report):
    rows = score(war_angel_report, BaselineRegistry(sources=(_internal_source(
        value=30.0),)))
    assert len(rows) == 1
    row = rows[0]
    assert row.state == STATE_SCORED
    assert row.verdict is None, "a point baseline has no band to be inside"
    assert row.delta == pytest.approx(row.value - 30.0)
    assert row.ratio == pytest.approx(row.value / 30.0)


def test_a_zero_point_baseline_refuses_the_ratio_rather_than_inventing_one(
        war_angel_report):
    """``null`` with a note, never a sentinel and never ``inf`` (§11.1).

    Worth stating what this is NOT: §9.1's deferred ``PairedDelta.variance_reduction``
    trap, whose ``inf`` comes from a PAIRED variance of exactly zero across two runs.
    A score is a property of ONE run, so that decision is still deferred and unmade.
    The two merely rhyme, and the delta stays meaningful here where a variance ratio
    would not.
    """
    rows = score(war_angel_report,
                 BaselineRegistry(sources=(_internal_source(value=0.0),)))
    row = rows[0]
    assert row.ratio is None
    assert row.delta == pytest.approx(row.value)
    assert "ratio_undefined" in row.warnings
    serialized = row.describe()
    assert serialized["ratio"] is None
    # The whole point: it survives JSON, which `inf` would not.
    assert json.loads(json.dumps(serialized))["ratio"] is None


def test_a_source_that_says_nothing_about_this_run_is_UNMATCHED(war_angel_report):
    """And ``unmatched`` is NOT an error: a source covering L11-20 says nothing about L4,
    and that silence is information rather than an absent row to be inferred."""
    elsewhere = _internal_source(level=4)
    rows = score(war_angel_report, BaselineRegistry(sources=(elsewhere,)))
    assert len(rows) == 1
    row = rows[0]
    assert row.state == STATE_UNMATCHED
    assert row.value is None and row.baseline is None
    assert row.delta is None and row.ratio is None and row.verdict is None
    assert "war_angel@L13" in (row.note or "")


def test_an_unavailable_metric_scores_UNAVAILABLE_and_never_zero(war_angel_report):
    """A baseline on a metric this run structurally cannot produce.

    REACHABILITY asserted separately from absence, per s56's lesson: the fixture must
    exhibit "available elsewhere, unavailable here", not "impossible everywhere".
    ``mitigation_fraction`` is unavailable with no mitigation profile and AVAILABLE
    under ``enemy_options={'mitigation': True}`` — checked below, so this cell is a real
    unavailability rather than a structurally impossible one.
    """
    metric = "mitigation_fraction"
    assert not war_angel_report.values[metric].available

    # Reachability: the same metric on a run that CAN produce it.
    reachable = build_report(simulate(RunConfig(
        build="war_angel", level=13, n_days=2, enemy="baseline",
        enemy_options={"mitigation": True})))
    assert reachable.values[metric].available, (
        "fixture guard: mitigation_fraction must be REACHABLE, or this test is "
        "asserting over a structurally impossible cell (s56)"
    )

    rows = score(war_angel_report,
                 BaselineRegistry(sources=(_internal_source(metric=metric, value=0.2),)))
    row = rows[0]
    assert row.state == STATE_UNAVAILABLE
    assert row.value is None and row.delta is None and row.ratio is None
    assert row.baseline == 0.2, "the baseline itself is still reported"
    assert row.note


#: The UNMEASURED-state fixture's coordinate, in ONE place.
#:
#: ``save_fail_rate[int_save|*]`` at band 11-16 is AVAILABLE (an INT save carries
#: weight 20 of ~999 in that band's damage channel) and a two-day run usually forces
#: none, which is the rare-but-reachable cell §9.1's third state needs.
#:
#: **It is a shared constant because it DRIFTED (s60).** §6.3's substreams reshuffled
#: the stream and ``seed=11`` started forcing an INT save, failing both tests that
#: hard-coded it — in two places, with one cause.  The fixture guards below are what
#: caught it, and they say to re-pick the coordinate rather than widen the assertion;
#: re-picking it twice is how a duplicated sequence gets out of step.
_UNMEASURED_LEVEL = 13
_UNMEASURED_DAYS = 2
_UNMEASURED_SEED = 1


def test_an_unmeasured_metric_scores_UNMEASURED_and_never_zero():
    """Available, but this run produced no estimate — §9.1's third state, one layer up.

    Uses ``save_fail_rate[int_save|*]`` at band 11-16, where an INT save genuinely CAN
    be forced and a short run simply did not.  s56 repointed its own fixture here for
    exactly this reason: at band 5-10 the cell is structurally impossible, and from the
    outside an impossible cell and an unmeasured one look identical.
    """
    config = RunConfig(build="war_angel", level=_UNMEASURED_LEVEL,
                       n_days=_UNMEASURED_DAYS, seed=_UNMEASURED_SEED,
                       enemy="baseline")
    report = build_report(simulate(config))
    metric = "save_fail_rate[int_save|*]"
    value = report.values[metric]

    # REACHABILITY, from the run's own RESOLVED parameters rather than from a second
    # simulation — which is how s56 says to ask it. An INT save carries weight 20 of
    # ~999 in band 11-16's damage channel, so the cell is genuinely rare rather than
    # structurally impossible, and those two look identical from the outside.
    weights = resolve(config)["save_weights"]["damage"]
    assert weights.get("int_save", 0) > 0, (
        "fixture guard: int_save must be REACHABLE in this band, or this test asserts "
        "over a structurally impossible cell rather than an unmeasured one (s56)"
    )
    assert value.available, "fixture guard: the cell must be AVAILABLE at band 11-16"
    assert not value.measured, (
        "fixture guard: this run must not have forced an INT save; if it did, this test "
        "is no longer exercising the unmeasured branch. It is rare, not impossible, so "
        "a changed dice stream can flip it — re-pick (n_days, seed) rather than "
        "widening the assertion"
    )

    source = BaselineSource(
        name="prior_run", kind="internal_run", provenance="p",
        dimensions=(CoordinateDimension(name="level", match=MATCH_EXACT),),
        entries=(BaselineEntry(coordinate={"level": _UNMEASURED_LEVEL},
                               metric=metric,
                               basis=BASIS_UNKNOWN, value=0.4),))
    row = score(report, BaselineRegistry(sources=(source,)))[0]
    assert row.state == STATE_UNMEASURED
    assert row.value is None


def test_every_score_state_is_reachable(war_angel_report, production):
    """The roll call's ``Score.state`` row, closed by addition.

    Each state has its own test above; this asserts the SET is covered, so a fifth
    state added later without a fixture fails here rather than silently.
    """
    seen = {r.state for r in score(war_angel_report, production)}
    seen |= {r.state for r in score(war_angel_report, BaselineRegistry(
        sources=(_internal_source(level=4),)))}
    seen |= {r.state for r in score(war_angel_report, BaselineRegistry(
        sources=(_internal_source(metric="mitigation_fraction", value=0.2),)))}
    report = build_report(simulate(RunConfig(
        build="war_angel", level=_UNMEASURED_LEVEL, n_days=_UNMEASURED_DAYS,
        seed=_UNMEASURED_SEED, enemy="baseline")))
    source = BaselineSource(
        name="prior_run", kind="internal_run", provenance="p",
        dimensions=(CoordinateDimension(name="level", match=MATCH_EXACT),),
        entries=(BaselineEntry(coordinate={"level": _UNMEASURED_LEVEL},
                               metric="save_fail_rate[int_save|*]",
                               basis=BASIS_UNKNOWN, value=0.4),))
    seen |= {r.state for r in score(report, BaselineRegistry(sources=(source,)))}
    assert seen == set(SCORE_STATES)


def test_summarize_counts_and_its_breakdown_come_from_ONE_traversal(war_angel_report,
                                                                    production):
    """s56's ``unconverged_verdicts`` rule: a count and a breakdown of that count must
    not be computable from two different lists."""
    rows = score(war_angel_report, production)
    counts = summarize(rows)
    assert sum(counts.values()) == len(rows)
    assert counts[STATE_SCORED] == sum(1 for r in rows if r.state == STATE_SCORED)


# ---------------------------------------------------------------------------
# basis — the three answers
# ---------------------------------------------------------------------------

def test_a_basis_that_AGREES_raises_no_basis_warning(war_angel_report):
    agreeing = run_basis(war_angel_report, "dpr")
    row = score(war_angel_report, BaselineRegistry(sources=(
        _internal_source(basis=agreeing),)))[0]
    assert "basis_differs" not in row.warnings
    assert "basis_unknown" not in row.warnings
    assert row.basis == row.run_basis


def test_a_basis_that_DIFFERS_is_warned(war_angel_report):
    row = score(war_angel_report, BaselineRegistry(sources=(
        _internal_source(basis="damage/round over total_rounds; mode=finite_hp"),)))[0]
    assert "basis_differs" in row.warnings
    assert row.basis != row.run_basis


def test_an_unknown_basis_gets_a_DIFFERENT_warning(war_angel_report, production):
    """Two facts, two distinguishable answers — the availability mechanism's own rule.

    "The baseline does not say" and "the baseline says something else" are not the same
    problem and do not have the same remedy.
    """
    unknown = score(war_angel_report, production)[0]
    differs = score(war_angel_report, BaselineRegistry(sources=(
        _internal_source(basis="something else entirely"),)))[0]
    assert "basis_unknown" in unknown.warnings
    assert "basis_differs" not in unknown.warnings
    assert "basis_differs" in differs.warnings
    assert "basis_unknown" not in differs.warnings


def test_an_external_published_score_is_flagged_a_REFERENCE_POINT(war_angel_report,
                                                                  production):
    """§11's correction, carried on every score rather than left in the prose."""
    rows = score(war_angel_report, production)
    assert all("reference_point" in r.warnings for r in rows)
    internal = score(war_angel_report,
                     BaselineRegistry(sources=(_internal_source(),)))[0]
    assert "reference_point" not in internal.warnings


# ---------------------------------------------------------------------------
# Serialization (§11.2)
# ---------------------------------------------------------------------------

def test_the_scores_key_is_ABSENT_when_no_baselines_were_supplied(war_angel_report,
                                                                  production):
    """ABSENT, not present-and-empty (§11.2).

    "This record was not scored" and "it was scored and nothing matched" are different
    facts, and the project already distinguishes exactly that pair twice: blank vs ``*``
    in the tidy frame's dimension columns, and ``unavailable`` vs ``unmeasured`` in a
    row's status.  It also means no existing record's bytes change.
    """
    bare = artifact_module.report_to_dict(war_angel_report,
                                          include_data_dictionary=False)
    assert "scores" not in bare

    scored = artifact_module.report_to_dict(war_angel_report,
                                            include_data_dictionary=False,
                                            baselines=production)
    assert "scores" in scored
    assert scored["schema_version"] == artifact_module.SCHEMA_VERSION, (
        "additive at version 1, on the convergence and distributions precedent"
    )
    # Every other section is untouched by scoring.
    assert {k: v for k, v in scored.items() if k != "scores"} == bare


def test_the_scores_block_names_its_own_baseline_set(war_angel_report, production):
    block = scores_block(war_angel_report, production)
    assert block["baselines_schema_version"] == BASELINES_SCHEMA_VERSION
    assert block["baselines_fingerprint"] == production.fingerprint()
    assert [s["name"] for s in block["sources"]] == [PRODUCTION_SOURCE]
    assert len(block["scores"]) == 4


def test_the_whole_record_survives_JSON(war_angel_report, production):
    text = artifact_module.to_json(war_angel_report, include_data_dictionary=False,
                                   baselines=production)
    round_tripped = json.loads(text)
    assert len(round_tripped["scores"]["scores"]) == 4


def test_the_tidy_score_frame_has_its_OWN_grain(war_angel_report, production):
    """Keyed ``(run, metric, source, coordinate)``, not ``(run, metric)`` (§11.2).

    Folding scores into the run record's frame would put a blank on every row that has
    no baseline and change what one row of that frame means — the s46 flattened-key
    failure one layer up.
    """
    rows = scores_to_rows(war_angel_report, production)
    assert len(rows) == 4
    keys = {(r["run_id"], r["metric"], r["source"], r["coordinate"]) for r in rows}
    assert len(keys) == 4, "the grain must separate the four classes"
    assert all(r["baselines_fingerprint"] == production.fingerprint() for r in rows)
    # The record's own frame is unchanged by scoring.
    assert "baseline" not in artifact_module.csv_columns(war_angel_report.registry)


def test_the_tidy_frame_and_the_JSON_block_share_ONE_renderer(war_angel_report,
                                                              production):
    """s57's cached-versus-computed lesson, applied before it could bite: two renderers
    for one quantity drift inside two sessions."""
    block = scores_block(war_angel_report, production)
    rows = scores_to_rows(war_angel_report, production)
    for json_row, flat in zip(block["scores"], rows):
        assert flat["metric"] == json_row["metric"]
        assert flat["state"] == json_row["state"]
        assert flat["verdict"] == json_row["verdict"]
        assert flat["value"] == json_row["value"]
        band = json_row["baseline_interval"]
        if band:
            assert flat["baseline_low"] == band["low"]
            assert flat["baseline_high"] == band["high"]
            assert flat["baseline_low_inclusive"] == band["low_inclusive"]
            assert flat["baseline_high_inclusive"] == band["high_inclusive"]
            assert flat["baseline_band"] == band["label"]
            assert flat["baseline_published"] == band["published"]


def test_the_score_csv_is_written_as_a_THIRD_file(tmp_path, war_angel_report,
                                                  production):
    written = artifact_module.write_artifact(war_angel_report, tmp_path,
                                             stem="run", baselines=production)
    assert set(written) == {"json", "csv", "scores_csv"}
    lines = written["scores_csv"].read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 5, "one header plus four scores"
    assert lines[0].startswith("run_id,config_hash,build,level")
    # ... and without baselines the output is exactly the two files it always was.
    bare = artifact_module.write_artifact(war_angel_report, tmp_path, stem="bare")
    assert set(bare) == {"json", "csv"}


def test_the_record_STORE_writes_records_UNSCORED(tmp_path, war_angel_report,
                                                  production):
    """§11.2's correctness decision, as an assertion.

    §10.2's cache key is ``(config_hash, engine_commit)`` and nothing else.  A ``scores``
    block inside a stored record would be scored against whichever baseline set was
    loaded at compute time, and a later run asking for a DIFFERENT set would be served
    it — §10.2's named failure, reached through a path neither module mentions.  The
    alternative, widening the key, pays a SIMULATION cache's price for a post-hoc join
    on data the record already holds.
    """
    from src.evaluation.sweep import RecordStore

    store = RecordStore.open(tmp_path, engine_commit="abc123", engine_dirty=False)
    paths = store.put("abc123-key", war_angel_report)
    assert set(paths) == {"json", "csv"}
    stored = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert "scores" not in stored, (
        "a cached record must be unscored, or a later run asking for a different "
        "baseline set is served this one's scores"
    )


# ---------------------------------------------------------------------------
# The console — the production READER of the scores block
# ---------------------------------------------------------------------------

def test_the_console_RENDERS_the_scores_block(war_angel_report, production):
    """Named in the roll call as the block's production reader.

    s53 found a telemetry channel dead at both ends and s56 found a §4 requirement
    satisfied in code nothing serialized.  A scores section no renderer reads would be
    the third instance of the same defect in three sessions, so the reader is asserted
    rather than assumed.
    """
    text = render(war_angel_report, baselines=production)
    assert "BASELINE SCORES" in text
    assert PRODUCTION_SOURCE in text
    assert "REFERENCE POINT, not a target" in text
    assert production.fingerprint() in text
    # Each of the four classes gets its own line, and each carries SOME verdict.
    # WHICH verdict is a DPR claim and is deliberately not asserted (see the module
    # docstring) — that the plumbing produced one for every class is the mechanism.
    section = text[text.index("BASELINE SCORES"):]
    for damage_class in ("A", "B", "C", "D"):
        line = next(ln for ln in section.split("\n")
                    if f"damage_class={damage_class}" in ln)
        assert any(v in line for v in ("BELOW", "INSIDE", "ABOVE")), line


def test_the_console_is_UNCHANGED_without_baselines(war_angel_report, production):
    """No existing rendered artifact moves: scoring is opt-in at every layer."""
    assert "BASELINE SCORES" not in render(war_angel_report)
    assert render(war_angel_report) != render(war_angel_report, baselines=production)


def test_the_console_HOISTS_a_warning_that_holds_for_every_score(war_angel_report,
                                                                 production):
    """Found by rendering it by eye (step 6).

    The first draft printed ``reference_point`` and ``basis_unknown`` on all four damage
    classes — two facts, eight lines, burying the four verdicts that are the answer.  A
    warning constant across a source's scores is a fact about the SOURCE.
    """
    text = render(war_angel_report, baselines=production)
    section = text[text.index("BASELINE SCORES"):text.index("WARNINGS",
                                                            text.index("BASELINE SCORES"))]
    assert section.count("[reference_point]") == 1
    assert section.count("[basis_unknown]") == 1
    assert "(all 4 score(s))" in section
    # The other branch — a warning that does NOT hold for every score — is covered by
    # test_a_row_specific_warning_is_not_hoisted below.


def test_a_row_specific_warning_is_not_hoisted(war_angel_report):
    """The other branch of the hoist: ``ratio_undefined`` belongs to ONE score."""
    two_entries = BaselineSource(
        name="prior_run", kind="internal_run", provenance="p",
        dimensions=(CoordinateDimension(name="damage_class", match=MATCH_FREE),
                    CoordinateDimension(name="level", match=MATCH_EXACT)),
        entries=(
            BaselineEntry(coordinate={"damage_class": "zero", "level": 13},
                          metric="dpr", basis=BASIS_UNKNOWN, value=0.0),
            BaselineEntry(coordinate={"damage_class": "normal", "level": 13},
                          metric="dpr", basis=BASIS_UNKNOWN, value=30.0),
        ))
    registry = BaselineRegistry(sources=(two_entries,))
    text = render(war_angel_report, baselines=registry)
    section = text[text.index("BASELINE SCORES"):]
    assert section.count("[ratio_undefined]") == 1, (
        "it holds for one of the two scores, so it must not be hoisted to the source"
    )
    assert section.count("[basis_unknown]") == 1, "this one holds for both, so hoisted"
    assert "(all 2 score(s))" in section
