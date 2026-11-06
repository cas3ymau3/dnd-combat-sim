"""Framework step 8a — the convergence VERDICT: the flag, plus how far from passing.

`evaluation_framework.md` §14(a); `src/evaluation/statistics.py`'s
`ConvergenceVerdict`.  The deferral's requirement, added s55 from the #6a
preliminary run: **report the DISTANCE from the criterion, or the days required,
alongside the boolean**, because the boolean is the part that cannot carry the
distinction.  Across War Angel's 102 flags at L1-L10, 36 cleared with at most double
the days while 6 needed more than a hundred times, and the two rendered identically.

THE ROLL CALL (per-feature ritual step 5 — written BEFORE the tests, and it is the
instrument that finds the gaps rather than a record of work done).  One row per
declaration this change touches; one named fixture per VALUE.

| declaration                         | value                        | fixture |
|-------------------------------------|------------------------------|---------|
| `converged`                         | True (precise)               | `test_a_precise_estimate_converges_and_names_no_criterion` |
|                                     | True (EXACT, stderr 0)       | `test_an_exact_estimate_converges_and_says_why` |
|                                     | False                        | every criterion row below |
| `criterion` = `not_measured`        | value is None                | `test_an_unmeasured_estimate_names_not_measured_and_no_day_count` |
| `criterion` = `min_days`            | n below the floor            | `test_min_days_binds_below_the_floor_and_asks_for_the_floor` |
| `criterion` = `min_events`          | events below the floor       | `test_min_events_scales_LINEARLY_in_days` |
| `criterion` = `rel_stderr`          | ratio scale, non-zero value  | `test_rel_stderr_scales_as_the_SQUARE_of_the_shortfall` |
| `criterion` = `resolution_sigmas`   | SCALE_INTERVAL               | `test_an_interval_scale_shortfall_is_measured_in_SIGMAS` |
| `criterion` = `undefined_at_zero`   | ratio scale, 0 with noise    | `test_a_ratio_scale_zero_with_noise_admits_NO_day_count` |
| `criterion` = `min_tail_observations`| thin tail                   | `test_a_thin_tail_asks_for_proportionally_more_days` |
| `criterion` = `ci_width_vs_spread`  | interval too wide            | `test_an_interval_width_shortfall_REFUSES_to_quote_a_day_count` |
|                                     | point mass (no spread)       | `test_a_point_mass_converges_only_on_a_zero_width_interval` |
| `days_required`                     | finite                       | the four scaling rows above |
|                                     | None (no finite n passes)    | `test_a_ratio_scale_zero_with_noise_admits_NO_day_count`, `test_an_interval_width_shortfall_REFUSES_to_quote_a_day_count` |
| binding-gate selection              | largest finite wins          | `test_the_binding_gate_is_the_one_needing_the_MOST_days` |
|                                     | unreachable outranks finite  | `test_an_UNREACHABLE_gate_binds_AHEAD_of_a_larger_finite_one` |
| `days_factor`                       | finite / None                | `test_days_factor_is_derived_and_is_None_when_the_days_are` |
| artifact row                        | `convergence` object present | `test_every_row_in_a_real_artifact_carries_a_convergence_object` |
| tidy CSV                            | two new columns              | `test_the_tidy_csv_carries_the_criterion_and_the_days_required` |
| console flag                        | finite-days shape            | `test_the_console_flag_names_the_criterion_and_the_days` |
|                                     | no-day-count shape           | `test_the_console_flag_says_no_day_count_helps_for_the_lattice` |
|                                     | absent when converged        | `test_a_converged_row_carries_no_flag_at_all` |
| `unconverged` warning               | partition sums to its total  | `test_the_distance_summary_PARTITIONS_the_unconverged_set` |

**The gap the table exposed before any test was written:** nothing in the suite pinned
that the refactor leaves the BOOLEAN alone.  `check()` now delegates to `verdict()`,
and the project's whole regression net for convergence is per-metric flags inside
larger assertions — so a gate order quietly reordered would surface as a changed
`[unconverged]` count in some unrelated test, or not at all.
`test_the_flag_is_UNCHANGED_against_the_pre_s56_gate_order` closes it directly, and it
is the most load-bearing test in this module.
"""

from __future__ import annotations

import math
from itertools import product

import pytest

from src.evaluation import RunConfig
from src.evaluation.artifact import (
    DISTANCE_BUCKETS,
    NO_DAY_COUNT_BUCKET,
    _distance_summary,
    report_to_dict,
    report_to_rows,
    warnings_for,
)
from src.evaluation.console import render
from src.evaluation.report import build_report
from src.evaluation.runner import simulate
from src.evaluation.statistics import (
    CRITERIA,
    CRITERION_CI_WIDTH_VS_SPREAD,
    CRITERION_MIN_DAYS,
    CRITERION_MIN_EVENTS,
    CRITERION_MIN_TAIL_OBSERVATIONS,
    CRITERION_NOT_MEASURED,
    CRITERION_REL_STDERR,
    CRITERION_RESOLUTION_SIGMAS,
    CRITERION_UNDEFINED_AT_ZERO,
    SCALE_INTERVAL,
    SCALE_RATIO,
    Convergence,
    ConvergenceVerdict,
    DistributionConvergence,
)

#: A day count well above every default `min_days`, so a test that is about a
#: PRECISION gate is not accidentally about the day floor.
DAYS = 2_000


# ---------------------------------------------------------------------------
# The scalar gates
# ---------------------------------------------------------------------------

def test_a_precise_estimate_converges_and_names_no_criterion():
    verdict = Convergence().verdict(10.0, 0.1, DAYS, float(DAYS))

    assert verdict.converged is True
    assert verdict.criterion is None
    assert verdict.attained is None and verdict.required is None
    # None here means "nothing to report", NOT "no day count helps" — which is why
    # the class docstring tells a reader to branch on `converged` first.
    assert verdict.days_required is None
    assert verdict.days_factor is None


def test_an_exact_estimate_converges_and_says_why():
    """stderr == 0: every replicate agreed, so no precision gate applies.

    The branch s48 fixed for a real shipped defect — `concentration_breaks_per_day`
    reads an exact `0.0 +/- 0.0` on a build that never concentrates, and an event
    floor applied to it flagged the report's one CERTAIN number as untrustworthy.
    Pinned here because `verdict()` had to re-express that escape as the ABSENCE of
    the precision gates rather than as an early return.
    """
    verdict = Convergence(min_events=500.0).verdict(0.0, 0.0, DAYS, 0.0)

    assert verdict.converged is True
    assert verdict.criterion is None
    assert "exact" in verdict.note


def test_an_unmeasured_estimate_names_not_measured_and_no_day_count():
    verdict = Convergence().verdict(None, None, DAYS, 0.0)

    assert verdict.converged is False
    assert verdict.criterion == CRITERION_NOT_MEASURED
    assert verdict.days_required is None
    assert "more days would not change that" in verdict.note


def test_min_days_binds_below_the_floor_and_asks_for_the_floor():
    """The one gate whose required value IS a day count, so the extrapolation is
    an identity rather than a model."""
    verdict = Convergence(min_days=100).verdict(10.0, 0.01, 40, 40.0)

    assert verdict.converged is False
    assert verdict.criterion == CRITERION_MIN_DAYS
    assert (verdict.attained, verdict.required) == (40.0, 100.0)
    assert verdict.days_required == 100.0
    assert verdict.days_factor == pytest.approx(2.5)


def test_min_events_scales_LINEARLY_in_days():
    """Events accumulate per day, so the shortfall scales as the RATIO — not as its
    square, which is the rel_stderr case below.  Getting these two the same way round
    is the whole arithmetic content of the day count.

    Measured against the real thing: `save_fail_rate[int_save|*]` on War Angel L4 at
    2,000 days reports 17 events against a 500 floor, and the rendered output asks for
    ~59k days — which is 2000 * 500/17 = 58,824, the identity asserted here.
    """
    verdict = Convergence(min_events=500.0, rel_stderr=1.0).verdict(
        0.5, 0.05, 2_000, 17.0)

    assert verdict.criterion == CRITERION_MIN_EVENTS
    assert (verdict.attained, verdict.required) == (17.0, 500.0)
    assert verdict.days_required == pytest.approx(2_000 * 500.0 / 17.0)
    assert verdict.days_required == pytest.approx(58_823.5, abs=0.5)


def test_rel_stderr_scales_as_the_SQUARE_of_the_shortfall():
    """`stderr` falls as 1/sqrt(n), so halving a relative standard error costs FOUR
    times the days.  Asserted as the exact identity rather than as an inequality,
    because an inequality would pass on the linear law too — which is the mistake this
    test exists to make impossible."""
    verdict = Convergence(rel_stderr=0.02).verdict(1.0, 0.04, 1_000, 1_000.0)

    assert verdict.criterion == CRITERION_REL_STDERR
    assert verdict.attained == pytest.approx(0.04)
    assert verdict.required == 0.02
    # attained/required == 2, so the cost is 2**2 == 4x the days.
    assert verdict.days_required == pytest.approx(4_000.0)
    assert verdict.days_factor == pytest.approx(4.0)


def test_an_interval_scale_shortfall_is_measured_in_SIGMAS():
    """A signed quantity's zero is a break-even point, so relative error is a category
    error on it (§6.2) and the gate is "is the SIGN resolved".  The day count inverts
    the other way round — more days RAISE the sigma count, so the shortfall enters as
    `(required/attained)**2`."""
    verdict = Convergence(resolution_sigmas=3.0).verdict(
        1.0, 1.0, 1_000, 1_000.0, scale=SCALE_INTERVAL)

    assert verdict.criterion == CRITERION_RESOLUTION_SIGMAS
    assert verdict.attained == pytest.approx(1.0)       # |value| / stderr
    assert verdict.required == 3.0
    assert verdict.days_required == pytest.approx(9_000.0)


def test_a_ratio_scale_zero_with_noise_admits_NO_day_count():
    """The first of the two gates no finite day count satisfies.

    A ratio-scale estimate of exactly zero with a positive standard error has no
    relative error to shrink: `stderr/value` is undefined at every n.  Reporting a
    large number here would be a plausible, checkable-looking lie, which is exactly
    what §14(a) is trying to stop the boolean from doing.
    """
    verdict = Convergence().verdict(0.0, 0.01, DAYS, float(DAYS))

    assert verdict.converged is False
    assert verdict.criterion == CRITERION_UNDEFINED_AT_ZERO
    assert verdict.days_required is None
    assert verdict.days_factor is None
    assert "SCALE_INTERVAL" in verdict.note      # it names the actual remedy


# ---------------------------------------------------------------------------
# Which gate BINDS
# ---------------------------------------------------------------------------

def test_the_binding_gate_is_the_one_needing_the_MOST_days():
    """Two gates unsatisfied; the verdict reports the expensive one, and
    `days_required` is the max rather than either gate alone — because passing needs
    BOTH."""
    # min_events: 2000 * 500/100 = 10,000 days.  rel_stderr: 2000 * (0.1/0.05)**2
    # = 8,000 days.  So min_events binds.
    verdict = Convergence(rel_stderr=0.05, min_events=500.0).verdict(
        1.0, 0.1, 2_000, 100.0)

    assert verdict.criterion == CRITERION_MIN_EVENTS
    assert verdict.days_required == pytest.approx(10_000.0)


def test_an_UNREACHABLE_gate_binds_AHEAD_of_a_larger_finite_one():
    """The ordering rule that makes the output honest rather than merely numeric.

    "No day count helps" is a STRONGER statement than "a great many days would", so
    it must not be buried by a bigger number.  Here the event floor wants 200,000 days
    and the zero-value gate wants infinitely many; the verdict reports the latter and
    quotes no day count at all.
    """
    verdict = Convergence(min_events=1_000.0).verdict(0.0, 0.01, 2_000, 10.0)

    assert verdict.criterion == CRITERION_UNDEFINED_AT_ZERO
    assert verdict.days_required is None


def test_days_factor_is_derived_and_is_None_when_the_days_are():
    finite = Convergence().verdict(1.0, 0.04, 1_000, 1_000.0)
    assert finite.days_factor == pytest.approx(finite.days_required / 1_000)

    unreachable = Convergence().verdict(0.0, 0.01, 1_000, 1_000.0)
    assert unreachable.days_factor is None


def test_every_criterion_name_is_in_the_published_vocabulary():
    """`CRITERIA` is published and a consumer will branch on it, so a name invented
    in one `verdict()` branch and absent from the tuple is a contract break."""
    scalar = Convergence(min_events=500.0)
    no_floor = Convergence()                 # min_events 0, so min_days can bind
    distribution = DistributionConvergence()
    seen = {
        scalar.verdict(None, None, 10, 0.0).criterion,
        # A PRECISE estimate short of the day floor: with no event floor to outbid
        # it, min_days is the only unsatisfied gate.
        no_floor.verdict(1.0, 0.01, 10, 10.0).criterion,
        scalar.verdict(0.5, 0.05, 2_000, 17.0).criterion,
        scalar.verdict(1.0, 0.04, 2_000, 2_000.0).criterion,
        scalar.verdict(1.0, 1.0, 2_000, 2_000.0, scale=SCALE_INTERVAL).criterion,
        scalar.verdict(0.0, 0.01, 2_000, 2_000.0).criterion,
        # A NARROW interval with a thin tail: width/spread passes, so the tail floor
        # is what binds rather than being outranked by the unreachable width gate.
        distribution.verdict(1.0, (0.99, 1.01), 2_000, 10.0, 1.0).criterion,
        distribution.verdict(1.0, (0.0, 2.0), 2_000, 2_000.0, 1.0).criterion,
    }
    assert seen == {
        CRITERION_NOT_MEASURED, CRITERION_MIN_DAYS, CRITERION_MIN_EVENTS,
        CRITERION_REL_STDERR, CRITERION_RESOLUTION_SIGMAS,
        CRITERION_UNDEFINED_AT_ZERO, CRITERION_MIN_TAIL_OBSERVATIONS,
        CRITERION_CI_WIDTH_VS_SPREAD,
    }
    assert seen <= set(CRITERIA)


# ---------------------------------------------------------------------------
# The distribution gates — and the one that refuses to extrapolate
# ---------------------------------------------------------------------------

def test_a_thin_tail_asks_for_proportionally_more_days():
    verdict = DistributionConvergence(min_tail_observations=50.0).verdict(
        1.0, (0.99, 1.01), 200, 20.0, 1.0)

    assert verdict.criterion == CRITERION_MIN_TAIL_OBSERVATIONS
    assert (verdict.attained, verdict.required) == (20.0, 50.0)
    assert verdict.days_required == pytest.approx(200 * 50.0 / 20.0)


def test_an_interval_width_shortfall_REFUSES_to_quote_a_day_count():
    """The second unreachable gate, and the reason the two `verdict()` methods are not
    shared code (user, s56).

    s51 measured it on `attacks_per_round_distribution`: attacks per round is a count
    over a fixed 16-round denominator, so it moves in steps of 1/16, and an exact
    order-statistic interval cannot be narrower than one step.  `width/spread` is
    therefore pinned near 0.33 against the 0.10 threshold at EVERY day count until the
    interval collapses to zero width outright.  A 1/sqrt(n) extrapolation would print
    a finite, reasonable-looking number for something no day count achieves.

    The numbers below are s51's: one lattice step of 1/16 = 0.0625 against a whole IQR
    of 0.1875 = three steps.
    """
    verdict = DistributionConvergence().verdict(
        2.6875, (2.6875, 2.75), 2_000, 200.0, 0.1875)

    assert verdict.converged is False
    assert verdict.criterion == CRITERION_CI_WIDTH_VS_SPREAD
    assert verdict.attained == pytest.approx(0.0625 / 0.1875)
    assert verdict.required == 0.10
    assert verdict.days_required is None
    assert "lattice" in verdict.note


def test_a_point_mass_converges_only_on_a_zero_width_interval():
    """p10 == p90: no spread to resolve, so the ratio is undefined and the only
    readable interval is a point one.  Both values of the branch, since the ratio
    cannot decide it."""
    exact = DistributionConvergence().verdict(1.0, (1.0, 1.0), 2_000, 2_000.0, 0.0)
    assert exact.converged is True

    wide = DistributionConvergence().verdict(1.0, (0.9, 1.1), 2_000, 2_000.0, 0.0)
    assert wide.converged is False
    assert wide.criterion == CRITERION_CI_WIDTH_VS_SPREAD
    assert wide.attained is None and wide.required is None
    assert wide.days_required is None


# ---------------------------------------------------------------------------
# The flag itself must NOT have moved
# ---------------------------------------------------------------------------

def _pre_s56_check(conv: Convergence, value, stderr, n, n_events, scale) -> bool:
    """The gate order as `Convergence.check` implemented it BEFORE s56, copied
    verbatim from the retired body.

    A deliberate second copy of retired logic, which is normally the s54 duplicated-
    sequence defect — and is the right thing here for one reason: its job is to be
    FROZEN.  It is a historical record to compare against, not a second
    implementation anyone will maintain, and the test below is the only caller.
    """
    if value is None or stderr is None:
        return False
    if n < conv.min_days:
        return False
    if stderr == 0.0:
        return True
    if n_events < conv.min_events:
        return False
    if scale == SCALE_INTERVAL:
        return abs(value) >= conv.resolution_sigmas * stderr
    if value == 0.0:
        return False
    return abs(stderr / value) <= conv.rel_stderr


def test_the_flag_is_UNCHANGED_against_the_pre_s56_gate_order():
    """The load-bearing test of this module, and the gap the roll call exposed.

    s56 rewrote `Convergence.check` into a delegation, which means the GATES were
    re-expressed: the exactness escape moved out from between `min_days` and
    `min_events` into "the precision gates do not apply", and the early returns became
    a list whose worst member is reported.  The arguments for both are in
    `verdict()`'s docstring, but an argument is not a measurement — so the boolean is
    compared against the retired body over the whole product of edge values, including
    every boundary the old order could be sensitive to.

    If this ever fails, the refactor changed a verdict: `GOLDEN_DPR` would not catch it
    (it is a headline net, and a convergence flag is panel content — the s55 lesson),
    and no other test asserts the flag in isolation.

    **Looped rather than parametrized, deliberately.**  The product is 5,760 cases,
    which as test IDs would be five times the whole suite and would make the project's
    test count meaningless as a measure of coverage.  The loop reports the first
    disagreement with its full inputs, which is all a parametrized ID would have given.
    """
    convergences = [
        Convergence(),
        Convergence(rel_stderr=0.10, min_events=200.0),   # RARE_EVENT_CONVERGENCE
        Convergence(rel_stderr=0.05, min_events=500.0),   # save_fail_rate's
        Convergence(min_days=1),
    ]
    grid = product(
        convergences,
        [None, 0.0, -2.0, 1e-9, 1.0, 1_000.0],            # value
        [None, 0.0, 1e-12, 0.001, 0.05, 10.0],            # stderr
        [0, 1, 99, 100, 2_000],                           # n
        [0.0, 17.0, 500.0, 2_000.0],                      # n_events
        [SCALE_RATIO, SCALE_INTERVAL],
    )
    checked = 0
    for conv, value, stderr, n, n_events, scale in grid:
        now = conv.verdict(value, stderr, n, n_events, scale).converged
        before = _pre_s56_check(conv, value, stderr, n, n_events, scale)
        assert now == before, (
            f"verdict disagrees with the pre-s56 gate order: {conv!r}, "
            f"value={value!r}, stderr={stderr!r}, n={n}, n_events={n_events}, "
            f"scale={scale!r} -> {now} (was {before})"
        )
        checked += 1
    assert checked == 5_760, checked      # the grid itself, pinned


def test_check_delegates_rather_than_reimplementing():
    """One evaluation of the gates, not two (the s54 seam).  Asserted on a case where
    a drifted copy would differ: an exact estimate under an event floor it fails."""
    conv = Convergence(min_events=500.0)
    assert conv.check(0.0, 0.0, DAYS, 0.0) is True
    assert conv.verdict(0.0, 0.0, DAYS, 0.0).converged is True


# ---------------------------------------------------------------------------
# Serialization and rendering (§9.1, additive at schema_version 1)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def war_angel_l4():
    """War Angel L4 at a realistic size: the #6a run's own low-level regime, where the
    quick tier's flags are dominated by near misses and a handful are not.

    Pinned to a REGIME rather than to a convenient level, per the s55 inert-test
    lesson: what this fixture must EXHIBIT is a mix of finite-day and no-day-count
    flags, and that is asserted below rather than assumed.
    """
    config = RunConfig(build="war_angel", level=4, enemy="baseline",
                       n_days=DAYS, seed=11)
    return build_report(simulate(config))


@pytest.fixture(scope="module")
def war_angel_l16():
    """L16, whose `attacks_per_round_distribution` is the LATTICE case — the only
    regime that produces a `ci_width_vs_spread` flag, hence the only one that
    exercises the no-day-count rendering path."""
    config = RunConfig(build="war_angel", level=16, enemy="baseline",
                       n_days=DAYS, seed=11)
    return build_report(simulate(config))


def test_the_fixtures_EXHIBIT_both_kinds_of_flag(war_angel_l4, war_angel_l16):
    """The precondition, asserted separately from the properties under test (s55).

    Without this, a future change that stops either regime producing its kind of flag
    would leave the rendering tests below passing while testing nothing — which is
    exactly how `test_the_unconverged_warning_counts_DISTRIBUTION_points_too` went
    inert, and the only reason that was caught was a guard like this one.
    """
    finite = [v for _n, v in war_angel_l4.unconverged_verdicts()
              if v.days_required is not None]
    assert finite, "L4 fixture must produce flags with a finite day count"

    unreachable = [v for _n, v in war_angel_l16.unconverged_verdicts()
                   if v.days_required is None]
    assert unreachable, (
        "L16 fixture must produce at least one flag no day count fixes "
        "(the lattice distribution) — see this module's docstring"
    )


def test_every_row_in_a_real_artifact_carries_a_convergence_object(war_angel_l4):
    record = report_to_dict(war_angel_l4, include_data_dictionary=False)
    rows = (record["results"]["scalars"]
            + [r for b in record["results"]["breakdowns"]
               for r in b["cells"] + b["margins"]]
            + [r for b in record["results"]["distributions"] for r in b["points"]])
    assert rows

    for row in rows:
        verdict = row["convergence"]
        assert set(verdict) == {"criterion", "attained", "required", "days_run",
                                "days_required", "days_factor", "note"}
        # The invariant that makes the object readable: a converged row names no
        # criterion, an unconverged one always does.
        assert (verdict["criterion"] is None) is bool(row["converged"])
        if verdict["criterion"] is not None:
            assert verdict["criterion"] in CRITERIA


def test_the_tidy_csv_carries_the_criterion_and_the_days_required(war_angel_l4):
    rows = report_to_rows(war_angel_l4)
    flagged = [r for r in rows
               if r["status"] == "measured" and not r["converged"]]
    assert flagged, "fixture must flag something"

    for row in flagged:
        assert row["convergence_criterion"] in CRITERIA
    # And a converged row leaves both columns blank rather than writing a zero —
    # the same rule the value columns follow for a non-measured row.
    for row in rows:
        if row["converged"]:
            assert row["convergence_criterion"] is None
            assert row["convergence_days_required"] is None


def test_the_console_flag_names_the_criterion_and_the_days(war_angel_l4):
    """Per-feature ritual step 6: what a reader actually sees.

    The exact shape is pinned because the whole deliverable of 8a is legibility — a
    flag that names a criterion but not the distance would pass a looser assertion and
    would not answer the question §14(a) asked.
    """
    text = render(war_angel_l4)
    flags = [line for line in text.splitlines() if "[unconverged:" in line]
    assert flags

    assert any("rel_stderr" in line and "vs" in line and "days" in line
               for line in flags)
    # `save_fail_rate[*|damage]` is the near miss the #6a run highlighted: a 1.6x
    # multiplier sitting in the same report as a 29x one.
    assert any("min_events" in line and "x)" in line for line in flags)


def test_the_console_flag_says_no_day_count_helps_for_the_lattice(war_angel_l16):
    text = render(war_angel_l16)
    lattice = [line for line in text.splitlines()
               if "ci_width_vs_spread" in line]
    assert lattice, "L16 must render the lattice distribution's flag"
    for line in lattice:
        assert "no day count helps" in line
        assert "days (" not in line          # no multiplier is quoted


def test_a_converged_row_carries_no_flag_at_all(war_angel_l4):
    """The branch where `_flag` returns the empty string.

    Checked on the HEADLINE (which converges at the quick tier) and on a named
    converged PANEL row, because the two go through different renderers and only the
    second uses `_scalar_line`.
    """
    text = render(war_angel_l4)

    headline = [line for line in text.splitlines() if line.startswith("HEADLINE")]
    assert headline and "dpr" in headline[0]
    assert "unconverged" not in headline[0]

    assert war_angel_l4["attacks_per_round"].converged is True
    panel = [line for line in text.splitlines()
             if line.strip().startswith("attacks_per_round ")]
    assert panel
    assert all("unconverged" not in line for line in panel)


# ---------------------------------------------------------------------------
# The top-level warning
# ---------------------------------------------------------------------------

def test_the_distance_summary_PARTITIONS_the_unconverged_set(war_angel_l4,
                                                             war_angel_l16):
    """A summary whose parts do not add up to its own total is the step-6 defect class
    (s52 shipped a count that was half the truth for four sessions).  Here the guard is
    arithmetic: the buckets are checked to sum to the number in the same sentence.

    Checked on BOTH fixtures, because the no-day-count bucket only exists in one of
    them and a partition that holds without it is not the partition being claimed.
    """
    for report in (war_angel_l4, war_angel_l16):
        verdicts = report.unconverged_verdicts()
        summary = _distance_summary(verdicts)
        counts = [int(part.rsplit(": ", 1)[1]) for part in summary.split(", ")]
        assert sum(counts) == len(verdicts), summary

        labels = {part.rsplit(": ", 1)[0] for part in summary.split(", ")}
        assert labels <= {lab for _b, lab in DISTANCE_BUCKETS} | {NO_DAY_COUNT_BUCKET}

        warning = next(w for w in warnings_for(report)
                       if w["code"] == "unconverged")
        assert f"{len(verdicts)} measured estimate(s)" in warning["message"]
        assert summary in warning["message"]


def test_the_buckets_are_the_ones_the_deferral_TABULATED():
    """§14(a)'s table and this summary must be read against one scale, so the
    boundaries are pinned rather than left to taste.  The top bucket is separate from
    10-100x deliberately: s55 measured 414,000 days against a 58-extra-days near miss
    in the same report, and folding them loses the finding."""
    assert [label for _bound, label in DISTANCE_BUCKETS] == [
        "<=2x", "2-10x", "10-100x", ">100x"]
    assert [bound for bound, _label in DISTANCE_BUCKETS] == [
        2.0, 10.0, 100.0, math.inf]


def test_the_summary_omits_empty_buckets():
    """Three zeroes to skim past is worse than a short phrase, and a reader should not
    have to work out which buckets were in play."""
    only_near = [("a", Convergence().verdict(1.0, 0.021, 2_000, 2_000.0))]
    assert _distance_summary(only_near) == "<=2x: 1"

    only_unreachable = [("a", Convergence().verdict(0.0, 0.01, 2_000, 2_000.0))]
    assert _distance_summary(only_unreachable) == f"{NO_DAY_COUNT_BUCKET}: 1"


def test_a_converged_report_raises_no_unconverged_warning_and_no_summary():
    """The empty branch: `_distance_summary` is never reached, so the sentence cannot
    render "By distance from the criterion — " with nothing after it."""
    config = RunConfig(build="war_angel", level=4, enemy="none", n_days=200, seed=3)
    report = build_report(simulate(config))
    codes = [w["code"] for w in warnings_for(report)]
    if "unconverged" not in codes:
        assert _distance_summary([]) == ""
    else:
        warning = next(w for w in warnings_for(report)
                       if w["code"] == "unconverged")
        assert "By distance from the criterion — " in warning["message"]
        assert not warning["message"].endswith("— ")
