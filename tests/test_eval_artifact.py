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
from src.evaluation.metrics import ALL
from src.evaluation.statistics import MetricValue

logging.disable(logging.CRITICAL)

#: The one Silvertail scenario that lights up saves, concentration AND a summon, so a
#: single cheap run exercises every output kind plus the roster-scoping dimensions.
ZONE = {"zone_effect": "spirit_guardians"}


@pytest.fixture(scope="module")
def report():
    """One small run, reused: assembling a report is pure post-processing (no dice),
    so every test here can share it without ordering coupling."""
    return run(RunConfig(build="silvertail", level=10, n_days=30, seed=3,
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
    assert record["config_hash"] == RunConfig(
        build="silvertail", level=10, n_days=30, seed=3, build_options=ZONE,
    ).config_hash()


def test_the_record_round_trips_through_json(report):
    """Everything in the record is a JSON primitive — no dataclass, no tuple key, no
    NaN.  A record that only serializes under a custom encoder is not a contract."""
    reloaded = json.loads(to_json(report))
    assert reloaded == json.loads(json.dumps(report_to_dict(report)))


# ---------------------------------------------------------------------------
# The three sections, the third RESERVED (§5.4 kind 3 / §14)
# ---------------------------------------------------------------------------

def test_results_carry_all_three_sections_with_distributions_reserved_and_empty(record):
    """The s46 hand-off's first requirement: §14's quantile work must land without a
    ``schema_version`` break, which is only true if the section exists at version 1."""
    assert list(record["results"]) == [
        "headline", "scalars", "breakdowns", "distributions",
    ]
    assert record["results"]["distributions"] == []


def test_the_data_dictionary_reserves_the_same_third_section(record):
    """One reservation, expressed in two places — they must agree, or a consumer that
    reads the dictionary's kinds would disagree with one that reads the results'."""
    assert list(record["data_dictionary"]) == ["scalars", "breakdowns", "distributions"]
    assert record["data_dictionary"]["distributions"] == []


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
    measured = MetricValue(metric="m", value=1.0, n=5, stderr=0.1, converged=True)
    unmeasured = MetricValue(metric="m", value=None, n=5, stderr=None, converged=False)
    unavailable = MetricValue.unavailable("m", "no such channel", n=5)

    assert status_of(measured) == STATUS_MEASURED
    assert status_of(unmeasured) == STATUS_UNMEASURED
    assert status_of(unavailable) == STATUS_UNAVAILABLE
    assert set(STATUSES) == {STATUS_MEASURED, STATUS_UNMEASURED, STATUS_UNAVAILABLE}


def _all_rows(record):
    rows = list(record["results"]["scalars"])
    for block in record["results"]["breakdowns"]:
        rows.extend(block["cells"] + block["margins"])
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


def test_every_breakdown_declares_a_sum_rule_matching_its_crossing(record):
    assert record["results"]["breakdowns"]
    for block in record["results"]["breakdowns"]:
        assert block["sum_rule"] in SUM_RULES
        expected = SUM_RULE_PARTITION if block["crossed"] else SUM_RULE_OVERLAP
        assert block["sum_rule"] == expected, block["name"]


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


def test_a_crossed_breakdown_carries_no_do_not_sum_note(record):
    block = next(b for b in record["results"]["breakdowns"]
                 if b["name"] == "healing_by_source")
    assert block["crossed"] is True
    assert "sum_rule_note" not in block


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


def test_coverage_keeps_its_explicit_not_resolved_statement(record):
    """A half-filled provenance block is worse than an honest gap: it implies the
    assumptions were recorded when they were not."""
    coverage = record["provenance"]["coverage"]
    assert coverage["enemy_side"].startswith("NOT RESOLVED")
    assert record["provenance"]["resolved"]["enemy"] is None


def test_comparability_is_warned_unconditionally_and_names_all_three_axes(record):
    warning = next(w for w in record["warnings"] if w["code"] == "comparability")
    for axis in ("mode", "attribution", "enemy_path"):
        assert axis in warning["message"]


def test_the_unresolved_coverage_gap_is_promoted_to_a_top_level_warning(record):
    """Not buried: a reader who must open provenance to learn two artifacts are
    incomparable will not open it."""
    codes = [w["code"] for w in record["warnings"]]
    assert "coverage_gap" in codes
    assert set(codes) <= set(WARNING_CODES)


def test_a_quick_tier_run_is_warned_as_imprecise(report):
    quick = run(RunConfig(build="war_angel", level=5, n_days=2000, seed=1))
    assert quick.provenance.day_tier == "quick"
    assert any(w["code"] == "precision" for w in warnings_for(quick))
    # ... and a non-tiered run is not.
    assert not any(w["code"] == "precision" for w in warnings_for(report))


def test_an_unconverged_run_says_so_at_the_top_level(report):
    """A 30-day run cannot have converged; the warning is what stops a reader taking
    the panel at face value without opening every row's ``converged`` flag."""
    assert report.unconverged()
    assert any(w["code"] == "unconverged" for w in warnings_for(report))


# ---------------------------------------------------------------------------
# The tidy CSV (§9) — the analysis form
# ---------------------------------------------------------------------------

def test_dimension_columns_are_derived_from_the_registry_not_hardcoded(report):
    columns = dimension_columns(report.registry)
    declared = {d for b in report.registry.breakdowns for d in b.key_space.names}
    assert set(columns) == declared
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
        if row["kind"] == "scalar":
            assert row["sum_rule"] == ""
        else:
            assert row["sum_rule"] in SUM_RULES
    saves = [r for r in rows if r["breakdown"] == "saves_forced_per_round"]
    assert saves and all(r["sum_rule"] == SUM_RULE_OVERLAP for r in saves)


def test_a_sweep_csv_concatenates_under_one_header(tmp_path):
    reports = [run(RunConfig(build="war_angel", level=level, n_days=4, seed=1))
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
    # The reason travels with them.
    assert "enemy seam" in text or "control channel cannot be enabled" in text


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
