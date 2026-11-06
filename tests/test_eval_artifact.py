"""
test_eval_artifact.py — step 3 of the evaluation framework (§13.3, §9/§9.1):
JSON + tidy CSV + console, under a declared ``schema_version``.

Validation framing (§12, memory ``validate-mechanism-not-build-value``): every test
here asserts a SERIALIZATION MECHANISM.  No test asserts that any build's DPR value
is right — there is no external standard for it to be right against (§11) — only that
whatever the estimating layer produced arrives at the artifact boundary intact, and
that the four things a careless serializer destroys are structurally impossible to
destroy here:

1. the three reserved sections, with ``distributions`` present and EMPTY;
2. the three report states (measured / unavailable / unmeasured) staying DISTINCT,
   and never becoming a zero;
3. the uncrossed-breakdown trap — cells that do not partition their total are never
   summed, and cells and margins never share a container;
4. the provenance block whole, including its explicit not-resolved statement, and the
   comparability warnings surfaced rather than buried.
"""

from __future__ import annotations

import csv
import json
import logging

import pytest

from src.evaluation import RunConfig, run
from src.evaluation.artifact import (
    ARTIFACT_KIND,
    SCHEMA_VERSION,
    STATUS_MEASURED,
    STATUS_UNAVAILABLE,
    STATUS_UNMEASURED,
    STATUSES,
    SUM_RULE_OVERLAP,
    SUM_RULE_PARTITION,
    SUM_RULES,
    WARNING_CODES,
    csv_columns,
    dimension_columns,
    report_to_dict,
    report_to_rows,
    run_id,
    status_of,
    to_json,
    warnings_for,
    write_artifact,
    write_csv,
    write_json,
    write_sweep_csv,
)
from src.evaluation.console import render
from src.evaluation.metrics import ALL, METRICS
from src.evaluation.statistics import ConvergenceVerdict, MetricValue

logging.disable(logging.CRITICAL)

#: The one Silvertail scenario that lights up saves, concentration AND a summon, so a
#: single cheap run exercises every output kind plus the roster-scoping dimensions.
ZONE = {"zone_effect": "spirit_guardians"}


@pytest.fixture(scope="module")
def report():
    """One small run, reused: assembling a report is pure post-processing (no dice),
    so every test here can share it without ordering coupling."""
    return run(RunConfig(enemy="baseline", build="silvertail", level=10, n_days=30, seed=3,
                         build_options=ZONE))


@pytest.fixture(scope="module")
def record(report):
    return report_to_dict(report)


# ---------------------------------------------------------------------------
# The envelope (§9: schema_version is mandatory)
# ---------------------------------------------------------------------------

def test_the_record_declares_its_schema_version_and_kind(record):
    assert record["schema_version"] == SCHEMA_VERSION
    assert record["kind"] == ARTIFACT_KIND == "run_record"


def test_run_id_is_legible_and_hashes_the_config(report, record):
    """Legible enough to read a directory by eye, hashed so two scenarios cannot
    collide.  The hash must be the SAME number §10's cache key uses, or a cached
    artifact and its config would disagree about their own identity."""
    assert record["run_id"] == "silvertail@L10-" + record["config_hash"]
    assert record["config_hash"] == RunConfig(enemy="baseline", 
        build="silvertail", level=10, n_days=30, seed=3, build_options=ZONE,
    ).config_hash()


def test_the_record_round_trips_through_json(report):
    """Everything in the record is a JSON primitive — no dataclass, no tuple key, no
    NaN.  A record that only serializes under a custom encoder is not a contract."""
    reloaded = json.loads(to_json(report))
    assert reloaded == json.loads(json.dumps(report_to_dict(report)))


# ---------------------------------------------------------------------------
# The three sections — the third reserved at s47, FILLED at s48 (§5.4 kind 3)
# ---------------------------------------------------------------------------

def test_results_carry_all_three_sections_and_the_third_is_now_populated(record):
    """The s46/s47 hand-off's first requirement, now discharged: §14's quantile work
    had to land without a ``schema_version`` break.  It did — this asserts both halves
    at once, so the reservation cannot be quietly abandoned by a later change."""
    assert list(record["results"]) == [
        "headline", "scalars", "breakdowns", "distributions",
    ]
    assert record["results"]["distributions"], "the seam was filled at s48"
    assert record["schema_version"] == 1 == SCHEMA_VERSION


def test_the_data_dictionary_describes_the_same_third_section(record):
    """One contract, expressed in two places — they must agree, or a consumer reading
    the dictionary's kinds would disagree with one reading the results'."""
    assert list(record["data_dictionary"]) == ["scalars", "breakdowns", "distributions"]
    declared = {d["name"] for d in record["data_dictionary"]["distributions"]}
    assert declared == {b["name"] for b in record["results"]["distributions"]}
    assert all(d["kind"] == "distribution"
               for d in record["data_dictionary"]["distributions"])


def test_the_data_dictionary_is_embedded_by_default_and_can_be_dropped(report):
    with_dict = report_to_dict(report)
    without = report_to_dict(report, include_data_dictionary=False)
    assert with_dict["data_dictionary"]["scalars"]
    assert "data_dictionary" not in without
    # Dropping it changes NOTHING about the numbers.
    assert without["results"] == with_dict["results"]


def test_the_headline_is_a_name_pointer_into_scalars_not_a_duplicated_row(record):
    """§5.3's 'exactly one headline' only means something if the artifact cannot grow a
    second copy of it that drifts."""
    name = record["results"]["headline"]
    matches = [r for r in record["results"]["scalars"] if r["metric"] == name]
    assert len(matches) == 1
    assert matches[0]["group"] == "headline"
    assert matches[0]["kind"] == "scalar"


# ---------------------------------------------------------------------------
# The three states (§3.4) — the zero that must never be written
# ---------------------------------------------------------------------------

def test_status_of_maps_the_three_states_to_the_closed_vocabulary():
    # The verdict is built explicitly rather than through `Convergence.verdict`
    # because this test is about `status_of`, which reads `value`/`available` and
    # never looks at convergence — and a real verdict at n=5 would be False on
    # min_days, which would say something about convergence that is not the point.
    measured = MetricValue(metric="m", value=1.0, n=5, stderr=0.1,
                           convergence=ConvergenceVerdict(
                               converged=True, criterion=None, attained=None,
                               required=None, days_required=None, days_run=5))
    unmeasured = MetricValue(metric="m", value=None, n=5, stderr=None,
                             convergence=ConvergenceVerdict.not_measured(5))
    unavailable = MetricValue.unavailable("m", "no such channel", n=5)

    assert status_of(measured) == STATUS_MEASURED
    assert status_of(unmeasured) == STATUS_UNMEASURED
    assert status_of(unavailable) == STATUS_UNAVAILABLE
    assert set(STATUSES) == {STATUS_MEASURED, STATUS_UNMEASURED, STATUS_UNAVAILABLE}


def _all_rows(record):
    rows = list(record["results"]["scalars"])
    for block in record["results"]["breakdowns"]:
        rows.extend(block["cells"] + block["margins"])
    for block in record["results"]["distributions"]:
        rows.extend(block["points"])
    return rows


def test_every_row_declares_one_of_the_three_states(record):
    rows = _all_rows(record)
    assert rows
    assert {r["status"] for r in rows} <= set(STATUSES)


def test_this_run_actually_exercises_all_three_states(record):
    """The guard tests below are only meaningful if the fixture produces all three.
    Silvertail does: the control channel is unavailable (no control-enabled enemy
    until the §13 step-5 seam), and no charisma save is forced in 30 days."""
    present = {r["status"] for r in _all_rows(record)}
    assert present == set(STATUSES)


def test_a_non_measured_row_carries_null_never_zero(record):
    """§3.4's central rule at the serialization boundary: a zero for control resilience
    reads as 'this build resists control perfectly', which is the opposite of what is
    known.  ``value``, ``stderr`` and ``ci95`` all have to go, not just ``value``."""
    for row in _all_rows(record):
        if row["status"] != STATUS_MEASURED:
            assert row["value"] is None, row["metric"]
            assert row["stderr"] is None, row["metric"]
            assert row["ci95"] is None, row["metric"]


def test_unavailable_and_unmeasured_rows_carry_a_reason(record):
    """Two builds blocked for different reasons must give different reasons (the
    per-metric ritual's availability check, carried through serialization)."""
    for row in _all_rows(record):
        if row["status"] == STATUS_UNAVAILABLE:
            assert row["note"].strip(), row["metric"]


def test_a_measured_row_carries_its_full_uncertainty_payload(record):
    measured = [r for r in _all_rows(record) if r["status"] == STATUS_MEASURED]
    assert measured
    for row in measured:
        assert isinstance(row["value"], float)
        assert isinstance(row["n"], int) and row["n"] > 0
        assert isinstance(row["converged"], bool)
        if row["stderr"] is not None:
            low, high = row["ci95"]
            assert low <= row["value"] <= high


# ---------------------------------------------------------------------------
# Breakdowns: the key as DATA, and the uncrossed trap
# ---------------------------------------------------------------------------

def test_a_cell_carries_its_key_as_a_dict_never_as_a_string_to_parse(record):
    """The whole point of §5.4: nothing downstream reverses ``damage_share[fire]``
    back into ``("fire",)``."""
    block = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "damage_share")
    assert block["dimensions"] == ["damage_type"]
    fire = next(r for r in block["cells"] if r["key"] == {"damage_type": "fire"})
    assert fire["metric"] == "damage_share[fire]"
    assert fire["breakdown"] == "damage_share"
    assert fire["is_margin"] is False


def test_cells_and_margins_are_never_in_the_same_container(record):
    """The s46 hand-off's fourth requirement, structurally: they answer different
    questions, and the artifact must make concatenating them an act of will."""
    for block in record["results"]["breakdowns"]:
        assert all(r["is_margin"] is False for r in block["cells"]), block["name"]
        assert all(r["is_margin"] is True for r in block["margins"]), block["name"]
        cell_names = {r["metric"] for r in block["cells"]}
        assert cell_names.isdisjoint({r["metric"] for r in block["margins"]})


def test_every_breakdown_serializes_its_DECLARED_sum_rule(record):
    """A DECLARATION since s49, not an inference (§8.1).

    This test previously asserted ``sum_rule == (partition if crossed else overlap)``.
    That held for every breakdown shipped before s49 and was still wrong: the two are
    independent facts, and ``attack_roll_rate`` is the counter-example — crossed,
    because the cross is the question, and overlapping all the same, because a crit is
    also a hit.  So what the artifact owes a consumer is that the serialized value is
    the one the registry DECLARED, which is the only invariant that survives a
    breakdown whose keys are not disjoint.
    """
    assert record["results"]["breakdowns"]
    for block in record["results"]["breakdowns"]:
        assert block["sum_rule"] in SUM_RULES
        declared = METRICS.breakdown(block["name"]).sum_rule
        assert block["sum_rule"] == declared, block["name"]
        # And the data dictionary cannot disagree with the results about it.
        entry = next(d for d in record["data_dictionary"]["breakdowns"]
                     if d["name"] == block["name"])
        assert entry["sum_rule"] == declared


def test_the_old_crossed_inference_is_really_gone(record):
    """The regression guard for the change itself.  If someone re-derives the rule
    from ``crossed`` — the obvious-looking simplification, since six of the eight
    breakdowns still satisfy it — this is the test that notices."""
    inferred = {b["name"]: (SUM_RULE_PARTITION if b["crossed"] else SUM_RULE_OVERLAP)
                for b in record["results"]["breakdowns"]}
    declared = {b["name"]: b["sum_rule"] for b in record["results"]["breakdowns"]}
    assert inferred != declared
    disagree = {n for n in declared if declared[n] != inferred[n]}
    assert disagree == {"attack_roll_rate"}


def test_an_uncrossed_breakdown_is_flagged_do_not_sum_and_its_cells_really_overlap(record):
    """THE TRAP the s46 hand-off named. ``saves_forced_per_round`` is uncrossed: the
    per-ability cells and the per-channel cells each cover the WHOLE quantity, so
    summing every cell double-counts every save.  The artifact says so in a FIELD, and
    the arithmetic proves the field is not decoration — the naive sum overshoots the
    declared total, which is what a renderer that added the rows up would print."""
    block = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "saves_forced_per_round")
    assert block["crossed"] is False
    assert block["sum_rule"] == SUM_RULE_OVERLAP
    assert "double-counts" in block["sum_rule_note"]

    total = next(r for r in block["margins"] if set(r["key"].values()) == {ALL})
    naive = sum(r["value"] for r in block["cells"] if r["value"] is not None)
    assert total["value"] is not None and total["value"] > 0
    # Roughly double: the ability profile and the channel profile each sum to the total.
    assert naive > total["value"] * 1.5


def test_a_partitioning_breakdown_carries_no_do_not_sum_note(record):
    block = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "healing_by_source")
    assert block["crossed"] is True
    assert block["sum_rule"] == SUM_RULE_PARTITION
    assert "sum_rule_note" not in block


def test_a_crossed_but_overlapping_breakdown_gets_its_OWN_note(record):
    """Overlap has two causes and the remedies differ, so one note cannot serve both.
    An uncrossed breakdown is told to read its declared margin instead; a crossed
    non-disjoint one has no margin to read — materializing one was refused — so a note
    sending its reader to a margin would send them to a cell that does not exist."""
    attacks = next(b for b in record["results"]["breakdowns"]
                   if b["name"] == "attack_roll_rate")
    saves = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "saves_forced_per_round")
    assert attacks["crossed"] is True
    assert attacks["sum_rule"] == saves["sum_rule"] == SUM_RULE_OVERLAP
    assert "double-counts" in attacks["sum_rule_note"]
    assert attacks["sum_rule_note"] != saves["sum_rule_note"]
    # The uncrossed one points at a margin; the crossed one must NOT, having none.
    assert "margin" in saves["sum_rule_note"]
    assert not attacks["margins"]
    assert "no aggregate to read instead" in attacks["sum_rule_note"]


def test_a_refused_margin_is_documented_rather_than_missing(record):
    """``damage_share`` refuses a margin (its total is 1.0 by construction) and
    ``healing_by_source`` refuses one over ``context`` (healing.md §11.1).  A refusal
    must reach the artifact as a stated reason, or it reads as an oversight."""
    share = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "damage_share")
    assert share["margins"] == []
    assert share["margin_note"].strip()

    healing = next(b for b in record["results"]["breakdowns"]
                   if b["name"] == "healing_by_source")
    # Collapsing source_role is declared; collapsing context is not, and no margin in
    # the artifact may pool healing under fire with healing at leisure.
    assert healing["margins"]
    assert all(m["key"]["context"] != ALL for m in healing["margins"])


def test_per_cell_availability_survives_the_collapse(record):
    """§3.4's honesty requirement carried through §5.4: within ONE breakdown, some
    cells report and others declare themselves unavailable with their own reason."""
    block = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "save_fail_rate")
    statuses = {r["status"] for r in block["cells"] + block["margins"]}
    assert STATUS_MEASURED in statuses
    assert STATUS_UNAVAILABLE in statuses


# ---------------------------------------------------------------------------
# Provenance and warnings (§4, §9.1)
# ---------------------------------------------------------------------------

def test_the_provenance_block_serializes_whole(record):
    prov = record["provenance"]
    assert set(prov) == {
        "config", "resolved", "coverage", "roster", "engine_commit", "engine_dirty",
        "generated_at", "day_tier", "pairing", "epistemic_note",
    }
    assert prov["epistemic_note"].startswith("No external validation source exists")
    assert prov["resolved"]["build"]


def test_coverage_now_states_that_BOTH_sides_are_resolved(record):
    """s52 INVERTS this test.  It was ``test_coverage_keeps_its_explicit_not_resolved_
    statement``, and it is kept under a new name because the sentence it guarded is one
    the project spent nine sessions being able to say.

    The history, because the SHAPE moved twice.  Before the §13 step-5 seam
    ``resolved["enemy"]`` was literally ``None`` — there was no resolver to call.  s50
    gave it a block saying ``resolved: False`` that named the build factory as the
    source, which is strictly more honest than ``None`` (``None`` could not distinguish
    "nothing resolved it" from "it resolved to nothing").  s52 deleted the path that
    could be unresolved, so the only remaining state is resolved, and the assertion
    flips.
    """
    coverage = record["provenance"]["coverage"]
    assert coverage["enemy_side"].startswith("resolved")
    assert coverage["build_side"].startswith("resolved")
    assert "NOT RESOLVED" not in coverage["enemy_side"]
    enemy = record["provenance"]["resolved"]["enemy"]
    assert enemy["resolved"] is True
    assert enemy["standardized"] is True
    assert "note" not in enemy


def test_comparability_is_warned_unconditionally_and_names_all_three_axes(record):
    warning = next(w for w in record["warnings"] if w["code"] == "comparability")
    for axis in ("mode", "attribution", "enemy_path"):
        assert axis in warning["message"]


def test_no_run_can_emit_a_coverage_gap_warning_any_more(record):
    """The warning this used to assert the PRESENCE of.  Its one producer was the
    ``build_default`` path (§4's honest gap), which s52 deleted — so what is asserted
    is that no run emits it, and that every code emitted is still in the vocabulary."""
    codes = [w["code"] for w in record["warnings"]]
    assert "coverage_gap" not in codes
    assert set(codes) <= set(WARNING_CODES)


def test_the_coverage_gap_detector_still_works_on_a_synthetic_gap(report):
    """``coverage_gap`` is KEPT in the vocabulary with no production producer, and this
    is what keeps that from being an untested branch.

    The reasoning is in ``artifact.warnings_for``: the detector is generic over any
    ``*_side`` key, it emits nothing when there is nothing to emit, and
    ``WARNING_CODES`` is a published vocabulary a downstream renderer styles on — so a
    third provenance section that forgets to resolve itself should surface
    automatically rather than silently.  That is a different case from s51's "delete
    the branch nothing reaches", which is about a plausible NUMBER or a stated REASON
    that misleads whoever sees it; an empty detector misleads nobody.

    The synthetic gap is injected rather than configured, because by construction no
    config can produce one.
    """
    report.provenance.coverage["future_side"] = (
        "NOT RESOLVED. A synthetic third provenance section, to prove the detector "
        "fires on something other than the enemy."
    )
    try:
        emitted = [w for w in warnings_for(report) if w["code"] == "coverage_gap"]
    finally:
        del report.provenance.coverage["future_side"]

    assert len(emitted) == 1
    assert emitted[0]["message"].startswith("future_side: NOT RESOLVED")


def test_a_quick_tier_run_is_warned_as_imprecise(report):
    quick = run(RunConfig(enemy="none", build="war_angel", level=5, n_days=2000, seed=1))
    assert quick.provenance.day_tier == "quick"
    assert any(w["code"] == "precision" for w in warnings_for(quick))
    # ... and a non-tiered run is not.
    assert not any(w["code"] == "precision" for w in warnings_for(report))


def test_an_unconverged_run_says_so_at_the_top_level(report):
    """A 30-day run cannot have converged; the warning is what stops a reader taking
    the panel at face value without opening every row's ``converged`` flag."""
    assert report.unconverged()
    assert any(w["code"] == "unconverged" for w in warnings_for(report))


def test_the_unconverged_warning_counts_DISTRIBUTION_points_too():
    """THE s52 BUG, found by rendering one real output (per-feature ritual step 6 —
    sixth session running, and the sixth defect).

    The warning read ``EvalReport.unconverged()``, which iterates ``values`` only, so a
    War Angel L13 quick-tier run announced "3 measured metric(s)" while the artifact
    flagged **6**: the other three were ``attacks_per_round_distribution``'s p10, p25
    and iqr.  The whole point of promoting convergence to a TOP-LEVEL warning (§9.1) is
    that a reader should not have to dig; one that undercounts by half is worse than
    none, because it reads as a complete answer.

    Why it stayed invisible for four sessions is the dormancy question one layer out:
    the warning predates distributions (s47 vs s48), and the two originally shipped
    distributions converged at every tier, so the two sides agreed BY ACCIDENT.  s51's
    ``attacks_per_round_distribution`` is the first LATTICE distribution and the first
    that is legitimately unconverged at the quick tier (``ci_width_vs_spread`` pinned
    near 0.33 because its whole IQR is three 1/16 steps), which made the gap reachable.

    The fixture is a quick-tier War Angel L13 run with control on, because that is the
    configuration where BOTH kinds are non-empty — the branch that matters is "some of
    each", which neither kind alone exercises.

    **``party_size=1`` since s54, and the reason is the same mechanism in reverse.**
    The unconverged DISTRIBUTION point needs ``attacks_per_round`` to VARY. The declared
    party aims ~3/4 of the enemy's control at PASSIVE stand-ins, so the character is
    suppressed far less often, the quantity collapses back toward a constant and the
    distribution converges — leaving this fixture with no unconverged points and the
    test asserting over an empty list. So the solo roster is pinned here deliberately:
    it is the regime that produces the branch, not a leftover default.

    **L13 -> L16 (s55), and the fixture's guard is what caught it.** Deriving War
    Angel's save bonuses made the character resist control markedly better (control
    turns lost per round 0.0310 -> 0.0259, -16.5%), so at L13 ``attacks_per_round``
    stopped varying enough to leave any point unconverged and
    ``assert points`` fired on an empty list. That guard exists for exactly this —
    a fixture going inert is the failure mode that makes a regression test pass
    while testing nothing — and it is why it is asserted rather than assumed.

    L16 is the replacement because its branch rests on something STURDIER than the
    character failing its saves: Fighter-07's Flourish Counter converts an incoming hit
    into an outgoing attack, so ``attacks_per_round`` varies with how often the enemy
    connects rather than with how often control lands. Measured at the quick tier,
    L15 and L16 both produce the branch (3 unconverged scalars, 1 unconverged point)
    while L13 and the baseline SUBJECT at L5/L13/L20 produce no unconverged points at
    all — so the subject cannot host this test today, which is worth recording against
    §3.5.5's intent to move framework correctness onto it.

    **THE DAY COUNT IS NOW THE FIXTURE'S AXIS, NOT THE ROSTER (s59), AND THE SUBJECT
    CAN HOST THIS TEST AFTER ALL — the paragraphs above are history, not
    instructions.** 8e CUT ``attacks_per_round_distribution`` (§14), which was this
    fixture's only source of an unconverged point, so ``control=True`` and
    ``party_size=1`` — both of which existed solely to make ``attacks_per_round``
    vary — no longer buy anything and are dropped. The two surviving distributions
    clear ``ci_width_vs_spread`` comfortably at every DECLARED tier (measured on
    war_angel L16 at 2,000 days: dpr p10 = 0.0649, net_damage_taken p10 = 0.0187
    against the 0.10 threshold), and the gate stops firing above roughly 800 days. So
    the branch is now reached by LOWERING the day count, which any build can do —
    including §3.5's baseline SUBJECT, which the paragraph above records as unable to
    host this test. That is one line of §3.5.5's intent discharged as a side effect of
    the cut, and it is why the fixture moved rather than merely shrinking.

    **Measured at baseline L20, 700 days: 6 unconverged scalars and 3 unconverged
    distribution points, 9 names in total.** Both kinds non-empty, which is the
    branch. The 9 matters for the LAST assertion in this test rather than for the
    branch: ``warnings_for`` truncates its name list at 12 sorted entries, so a
    fixture with more unconverged rows than that cannot assert that every point is
    NAMED — it would be asserting against an ellipsis. The old fixture never met the
    limit because it had four names; the first s59 repoint (war_angel L16 at 400 days)
    produced 25 and failed here, which is how the limit was found. Candidates were
    measured rather than guessed: war_angel L16 reaches 9 names only at 900 days with
    the points down to 3, while the subject sits at 9 across 700-900 days.

    The s55 guard below is what will catch the next drift, and it now has a specific
    thing to catch in EACH direction: lower the estimators' variance and the fixture
    goes inert as the points rise above the threshold; raise the count of unconverged
    scalars and the truncation assertion starts failing instead. Re-pick the day count
    in either case, and do not relax either assertion.
    """
    report = run(RunConfig(build="baseline", level=20, n_days=700, seed=11,
                           enemy="baseline"))

    scalars = [v.metric for v in report.unconverged()]
    points = [f"{name}:{point.statistic}"
              for name, point in report.unconverged_points()]
    assert scalars, "fixture must have unconverged scalars/cells"
    assert points, "fixture must have unconverged DISTRIBUTION points"

    names = report.unconverged_names()
    assert set(names) == set(scalars) | set(points)
    assert len(names) == len(scalars) + len(points)

    warning = next(w for w in warnings_for(report) if w["code"] == "unconverged")
    assert warning["message"].startswith(f"{len(names)} measured estimate")
    # ...and the distribution points are NAMED, not merely counted: a reader has to be
    # able to tell which rows the count refers to.
    for point in points:
        assert point in warning["message"]


# ---------------------------------------------------------------------------
# The tidy CSV (§9) — the analysis form
# ---------------------------------------------------------------------------

def test_dimension_columns_are_derived_from_the_registry_not_hardcoded(report):
    """Every KIND that keys its rows contributes its dimensions to the same union —
    breakdowns by key space, distributions by ``key_dimensions``.  Asserting the union
    rather than a literal list is what makes a new dimension show up as a column
    automatically, and visibly, instead of needing the writer edited."""
    columns = dimension_columns(report.registry)
    declared = {d for b in report.registry.breakdowns for d in b.key_space.names}
    declared |= {d for x in report.registry.distributions()
                 for d in x.key_dimensions}
    assert set(columns) == declared
    assert "statistic" in columns
    assert len(columns) == len(set(columns))       # union, de-duplicated


def test_the_csv_has_one_row_per_estimate_and_matches_the_json(report, record):
    rows = report_to_rows(report)
    assert len(rows) == len(_all_rows(record))
    by_name = {r["metric"]: r for r in rows}
    for json_row in _all_rows(record):
        flat = by_name[json_row["metric"]]
        assert flat["value"] == json_row["value"]
        assert flat["stderr"] == json_row["stderr"]
        assert flat["status"] == json_row["status"]


def test_a_blank_dimension_and_a_star_dimension_are_different_facts(report):
    """Blank = *this row is not keyed by that dimension at all*; ``*`` = *margin over
    it*.  Conflating them would silently turn 'not applicable' into 'aggregated'."""
    rows = {r["metric"]: r for r in report_to_rows(report)}

    scalar = rows["dpr"]
    assert scalar["ability"] is None and scalar["damage_type"] is None

    cell = rows["save_fail_rate[dex_save|*]"]
    assert cell["ability"] == "dex_save"
    assert cell["channel"] == ALL              # a margin over channel, not "absent"
    assert cell["damage_type"] is None         # genuinely not keyed by damage type


def test_run_identifying_columns_repeat_on_every_row(report):
    """What makes a sweep's CSVs concatenate into one frame that ``group_by(run_id)``
    can split again."""
    rows = report_to_rows(report)
    assert {r["run_id"] for r in rows} == {run_id(report)}
    assert {r["build"] for r in rows} == {"silvertail"}
    assert {r["schema_version"] for r in rows} == {SCHEMA_VERSION}


def test_the_written_csv_is_r_friendly(report, tmp_path):
    """``TRUE``/``FALSE`` so R reads a logical column, and EMPTY (not 0) for anything
    not measured so it reads ``NA``.  The second is load-bearing: a zero written for
    an unavailable metric would be averaged into a mean."""
    path = write_csv(report, tmp_path / "run.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert list(rows[0]) == list(csv_columns(report.registry))
    assert {r["converged"] for r in rows} <= {"TRUE", "FALSE"}
    assert {r["is_margin"] for r in rows} <= {"TRUE", "FALSE"}
    for row in rows:
        if row["status"] != STATUS_MEASURED:
            assert row["value"] == "", row["metric"]
            assert row["stderr"] == ""
            assert row["ci_low"] == "" and row["ci_high"] == ""


def test_the_csv_carries_the_sum_rule_onto_every_breakdown_row(report, tmp_path):
    """The trap must survive the flattening too — a CSV row is where a reader is most
    likely to reach for ``sum()``."""
    path = write_csv(report, tmp_path / "run.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for row in rows:
        if row["kind"] == "breakdown":
            assert row["sum_rule"] in SUM_RULES
        else:
            # A scalar has no cells to sum; a DISTRIBUTION's points are not additive
            # under any rule, so the field does not apply rather than taking a value
            # from a two-value vocabulary that would imply a choice exists.
            assert row["sum_rule"] == "", row["metric"]
    saves = [r for r in rows if r["breakdown"] == "saves_forced_per_round"]
    assert saves and all(r["sum_rule"] == SUM_RULE_OVERLAP for r in saves)


def test_a_sweep_csv_concatenates_under_one_header(tmp_path):
    # enemy='baseline' at BOTH levels, which is the point a sweep makes: the two rows
    # are comparable because they declare the same enemy.  Before s52 this swept L5
    # (whose row carried no enemy_attack, so nothing acted) against L13 (where the
    # factory installed a ScriptedEnemyPolicy) and concatenated them under one header
    # regardless — exactly the silent comparison §3.4 forbids, in the artifact whose
    # job is to make runs comparable.
    reports = [run(RunConfig(build="war_angel", level=level, n_days=4, seed=1,
                             enemy="baseline"))
               for level in (5, 13)]
    path = write_sweep_csv(reports, tmp_path / "sweep.csv")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len({r["run_id"] for r in rows}) == 2
    assert len(rows) == sum(len(report_to_rows(r)) for r in reports)
    # One header line only — the second report appended rows, not a second header.
    assert not any(r["metric"] == "metric" for r in rows)


def test_influence_is_not_serialized(report, record):
    """The s46 hand-off's third requirement.  A per-day vector per metric at a 200k-day
    tier would be the bulk of the artifact, for a quantity only a comparison reads."""
    assert report.influence                      # it exists on the report ...
    assert "influence" not in json.dumps(record)  # ... and nowhere in the artifact.


# ---------------------------------------------------------------------------
# Writing files
# ---------------------------------------------------------------------------

def test_write_artifact_emits_both_forms_named_by_run_id(report, tmp_path):
    paths = write_artifact(report, tmp_path)
    assert paths["json"].name == f"{run_id(report)}.json"
    assert paths["csv"].name == f"{run_id(report)}.csv"
    assert json.loads(paths["json"].read_text(encoding="utf-8"))["run_id"] == run_id(report)


def test_rewriting_the_same_scenario_overwrites_rather_than_accumulates(report, tmp_path):
    write_artifact(report, tmp_path)
    write_artifact(report, tmp_path)
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_write_json_creates_missing_directories(report, tmp_path):
    path = write_json(report, tmp_path / "a" / "b" / "run.json")
    assert path.exists()


# ---------------------------------------------------------------------------
# The console renderer (§9: "a third renderer, not a special case")
# ---------------------------------------------------------------------------

def test_the_console_renders_the_headline_and_never_a_composite_score(report):
    text = render(report)
    assert "HEADLINE" in text
    assert report.registry.headline.name in text
    assert "no composite build score" in text


def test_the_console_never_prints_a_fabricated_total_for_an_uncrossed_breakdown(report):
    """It prints the DECLARED margin, labelled as such, and warns that the cells
    overlap — it never adds a column up."""
    text = render(report)
    assert "cells overlap; do NOT sum them" in text
    assert "NOT a sum: the cells above overlap" in text


def test_the_console_labels_a_crossed_margin_by_its_real_reason(report):
    """For a crossed breakdown the margin DOES equal the sum in value; what a consumer
    cannot rebuild is its standard error.  Saying 'not a sum' there would be false."""
    text = render(report)
    assert "stderr is not reconstructible from the cells" in text


def test_the_console_separates_the_two_non_measured_states(report):
    text = render(report)
    assert "UNAVAILABLE" in text and "UNMEASURED" in text
    assert "NOT a measured zero" in text
    # The reason travels with them.  **Updated s50:** the reason text changed when
    # the §13 step-5 seam made the control channel reachable — it used to end at
    # "the control channel cannot be enabled from here", and now every reason names
    # the config that WOULD measure it, because one keyword is the fix.
    assert "Configure enemy='baseline'" in text


def test_the_console_surfaces_the_warnings_and_the_epistemic_note(report):
    text = render(report)
    assert "WARNINGS" in text
    assert "[comparability]" in text
    assert "EPISTEMIC NOTE" in text


def test_the_console_writes_ascii_and_survives_a_narrow_console(report, tmp_path):
    """The scaffolding is ASCII; the quoted registry text is not.  Printing must
    degrade rather than take a whole run's output down on cp1252."""
    text = render(report)
    assert "+/-" in text and "±" not in text
    # The whole block must survive a cp1252 encode under the replacement policy the
    # printer uses -- i.e. no exception, and the numbers still there.
    degraded = text.encode("cp1252", "replace").decode("cp1252")
    assert "HEADLINE" in degraded


def test_a_dirty_tree_is_flagged_in_both_the_console_and_the_warnings(report):
    """An artifact whose engine_commit does not identify the code that made it is not
    reproducible, and that has to be impossible to miss."""
    if not report.provenance.engine_dirty:
        pytest.skip("clean working tree — nothing to flag")
    assert "DIRTY TREE" in render(report)
    assert any(w["code"] == "engine_dirty" for w in warnings_for(report))
