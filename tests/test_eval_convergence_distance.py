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
| `criterion` = `ci_width_vs_spread`  | wide, floor ABOVE threshold  | `test_a_width_shortfall_REFUSES_a_day_count_only_when_PINNED` |
|                                     | wide, floor BELOW threshold  | `test_a_width_shortfall_QUOTES_a_day_count_below_the_floor` |
|                                     | point mass (no spread)       | `test_a_point_mass_converges_only_on_a_zero_width_interval` |
| `lattice_step` (s59)                | lattice sample, with repeats | `test_the_lattice_step_is_the_smallest_gap_between_observations` |
|                                     | repeats only (no gap)        | same |
|                                     | near-continuous sample       | same |
| `days_provisional` (s59)            | True (interval straddles 0)  | `test_a_near_breakeven_day_count_is_marked_a_PROJECTION` |
|                                     | False (sigmas >= 1.96)       | same |
|                                     | False (converged)            | `test_a_converged_row_carries_no_flag_at_all` |
| `days_required`                     | finite                       | the four scaling rows above |
|                                     | None (no finite n passes)    | `test_a_ratio_scale_zero_with_noise_admits_NO_day_count`, `test_a_width_shortfall_REFUSES_a_day_count_only_when_PINNED` |
| binding-gate selection              | largest finite wins          | `test_the_binding_gate_is_the_one_needing_the_MOST_days` |
|                                     | unreachable outranks finite  | `test_an_UNREACHABLE_gate_binds_AHEAD_of_a_larger_finite_one` |
| `days_factor`                       | finite / None                | `test_days_factor_is_derived_and_is_None_when_the_days_are` |
| artifact row                        | `convergence` object present | `test_every_row_in_a_real_artifact_carries_a_convergence_object` |
| tidy CSV                            | two new columns              | `test_the_tidy_csv_carries_the_criterion_and_the_days_required` |
| console flag                        | finite-days shape            | `test_the_console_flag_names_the_criterion_and_the_days` |
|                                     | no-day-count shape           | `test_the_console_flag_says_no_day_count_helps_for_a_width_shortfall` |
|                                     | "projection only" shape      | `test_the_console_flag_marks_a_PROVISIONAL_day_count` |
|                                     | absent when converged        | `test_a_converged_row_carries_no_flag_at_all` |
| fixture supplying the pinned branch | bespoke registry, real run   | `pinned_lattice_report` |
| `unconverged` warning               | partition sums to its total  | `test_the_distance_summary_PARTITIONS_the_unconverged_set` |

**The gap the table exposed before any test was written:** nothing in the suite pinned
that the refactor leaves the BOOLEAN alone.  `check()` now delegates to `verdict()`,
and the project's whole regression net for convergence is per-metric flags inside
larger assertions — so a gate order quietly reordered would surface as a changed
`[unconverged]` count in some unrelated test, or not at all.
`test_the_flag_is_UNCHANGED_against_the_pre_s56_gate_order` closes it directly, and it
is the most load-bearing test in this module.

**WHAT THE s59 ROWS ADD, AND THE GAP THEY EXPOSED.**  8e's calibration sweep found
that both of this module's "no finite day count" answers were being given where a day
count demonstrably existed — in opposite ways:

* `ci_width_vs_spread` refused one BLANKETLY.  That was true while the registry held a
  genuinely pinned row and became false the moment 8e cut it: measured on the 94-cell
  sweep, the gate then fired on exactly 2 rows at the quick tier and BOTH converged at
  20,000 days.  The refusal is now conditional on `step/spread`, the floor an exact
  order-statistic interval cannot go below.
* `resolution_sigmas` quoted one CONFIDENTLY on a near-break-even quantity, where the
  projection assumes the point estimate is the truth.  Measured on the baseline
  subject, of three straddling rows one converged at 20,000 days roughly as projected
  and one became LESS resolved.  Neither existing answer fits, so `days_provisional` is
  a third state rather than a different choice between the two.

The gap the table exposed this time was in the FIXTURES, not the assertions.  Of
8,366 sweep rows exactly 2 produced a `ci_width_vs_spread` verdict and ZERO produced
`undefined_at_zero`, so after the floor fix **no production run at any declared tier
yields an unreachable verdict at all** — and the guard that had owned that branch
would have gone inert while passing.  `pinned_lattice_report` is the answer: a bespoke
`MetricRegistry` (§5.4 permits one explicitly) re-declaring the cut distribution, so
the branch keeps a real end-to-end fixture instead of a hand-built verdict, and the
fixture itself records why the row is not in production.
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
from src.evaluation.metrics import DistributionDef, _build_default_registry
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
    NORMAL_95,
    SCALE_INTERVAL,
    SCALE_RATIO,
    Convergence,
    ConvergenceVerdict,
    DEFAULT_CONVERGENCE,
    DEFAULT_DISTRIBUTION_CONVERGENCE,
    RARE_EVENT_CONVERGENCE,
    DistributionConvergence,
    lattice_step,
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


def test_the_CALIBRATED_convergence_constants_are_pinned():
    """Framework step 8e's deliverable, as an ASSERTION rather than as prose.

    §14(a) said three times that the fix for these constants is a SWEEP ACROSS BUILDS
    AND TIERS, not a nudge to a value, because retuning on one build at one tier
    reproduces the original problem with different points. 8e ran that sweep — 94
    cells over 4 builds x `level: available` x {2,000, 20,000} days, 1,034,000
    simulated days, plus a 47-cell control arm to make the rare-event rows exist at
    all — and the answer is that **NOTHING MOVES**. That is a result and not an
    absence of one, so it is pinned here: a future session that nudges one of these
    has to come past this test and its decision record.

    What the sweep measured, gate by gate (attained values, which do not depend on
    the thresholds, so one sweep settles all six):

    * `rel_stderr` 0.02 / 0.05 / 0.10 — THE DOMINANT GATE, binding on 77.1% of
      unconverged rows at the quick tier and 78.9% at 20,000. Its attained
      distribution is SMOOTH: 0.02 passes 76.3% of rows at the quick tier and 92.8%
      at 20,000, and the pass rate rises steadily through 0.01/0.03/0.05/0.10 with no
      elbow anywhere. **There is no discoverable optimum to find**, so this constant
      is irreducibly a stated convention (§6.2) — but it is now a MEASURED one, which
      is what §14(a) asked for. Keeping it.
    * `min_events` 200 / 500 — binds on 21.2% at the quick tier, 19.3% at 20,000.
      Doing real work; keeping it.
    * `resolution_sigmas` 3.0 — **§14(a) said "no shipped build is close enough to
      break-even to exercise it" and that is FALSE.** 5 of 47 rows fail it at the
      quick tier and 2 of 47 at 20,000: `net_damage_taken_per_round` on the baseline
      subject at L3/L6/L7/L8 and silvertail L4 sits within +/-0.11 damage/round of
      break-even, and silvertail L4 reads 0.0039 +/- 0.02140. The gate is doing
      exactly the job it was designed for, on the subject. Keeping the value and
      correcting the claim.
    * `min_days` 100 and `min_tail_observations` 50 — **neither can bind at any
      declared tier, and that is structural rather than slack.** The smallest tail
      fraction is 0.10, so tail observations are 0.10*n and reach 50 at n=500; the
      smallest declared tier is 2,000. Measured minimum attained: 200 at the quick
      tier (4x) and 2,000 at 20,000 days (40x). They are SUB-TIER guards, which is
      what their docstrings say they are for ("a p90 off 60 days rests on six
      observations"), so being slack above 500 days is correct behaviour. Keeping
      both, now documented as sub-tier.
    * `ci_width_vs_spread` 0.10 — fires on 2 of 564 distribution points at the quick
      tier and 0 of 564 at 20,000. Both of the two converged at 20,000 days, which is
      what exposed the blanket refusal and produced the floor fix above. Keeping the
      threshold; the fix was to the day count, not the bar.

    And `RARE_EVENT_CONVERGENCE`'s relaxed bar is slack but defensibly so. The control
    arm made all four of its metrics produce rows, and **all 166 measured rare-event
    rows converge at the quick tier**: the worst attained `rel_stderr` across the
    family is 0.0468 against the declared 0.10, so every row would also pass at 0.05.
    Its docstring's premise — "you will not get 2% on a concentration break rate at
    any realistic day count" — is half right, holding for `control_turns_*` (0 of 47
    reach 0.02) and failing for `concentration_break_rate` (12 of 25 do). Keeping
    0.10: the bar is the right order of magnitude and `min_events` is the gate
    actually protecting these rows.
    """
    assert DEFAULT_CONVERGENCE.rel_stderr == 0.02
    assert DEFAULT_CONVERGENCE.min_events == 0.0
    assert DEFAULT_CONVERGENCE.min_days == 100
    assert DEFAULT_CONVERGENCE.resolution_sigmas == 3.0

    assert RARE_EVENT_CONVERGENCE.rel_stderr == 0.10
    assert RARE_EVENT_CONVERGENCE.min_events == 200.0

    assert DEFAULT_DISTRIBUTION_CONVERGENCE.ci_width_vs_spread == 0.10
    assert DEFAULT_DISTRIBUTION_CONVERGENCE.min_tail_observations == 50.0
    assert DEFAULT_DISTRIBUTION_CONVERGENCE.min_days == 100

    # The two floors cannot bind at the smallest DECLARED tier, which is the fact that
    # makes them sub-tier guards rather than miscalibrated. Asserted as arithmetic so
    # it cannot rot: if a tier or a tail fraction changes, this fails rather than the
    # docstring quietly going stale.
    quick_tier_days = 2_000
    smallest_tail_fraction = 0.10
    assert quick_tier_days > DEFAULT_DISTRIBUTION_CONVERGENCE.min_days
    assert (quick_tier_days * smallest_tail_fraction
            > DEFAULT_DISTRIBUTION_CONVERGENCE.min_tail_observations)


def test_a_width_shortfall_REFUSES_a_day_count_only_when_PINNED():
    """The second unreachable gate — REWRITTEN s59, because the refusal used to be
    BLANKET and a blanket refusal became false when 8e cut the one pinned row.

    s51 measured the pinned case on `attacks_per_round_distribution`: attacks per round
    is a count over a fixed 16-round denominator, so it moves in steps of 1/16, and an
    exact order-statistic interval is a PAIR OF OBSERVATIONS whose width is a whole
    number of steps. One step over the sample's spread is therefore the FLOOR on
    `width/spread`, and when that floor already exceeds the threshold the ratio is
    pinned at every n.

    s59 confirmed the pinning on that sample directly rather than inferring it — the
    p90 ratio reads 0.1429 at n=400, 0.1250 at n=2,000 and 0.1250 at n=20,000, while a
    1/sqrt(n) projection would have promised 816, then 3,125, then 31,250 days.
    **The prediction is falsified at every step and renews itself**, which is why this
    gate must refuse rather than extrapolate here.
    """
    verdict = DistributionConvergence().verdict(
        2.6875, (2.6875, 2.75), 2_000, 200.0, 0.5, step=0.0625)

    assert verdict.converged is False
    assert verdict.criterion == CRITERION_CI_WIDTH_VS_SPREAD
    assert verdict.attained == pytest.approx(0.0625 / 0.5)
    assert verdict.required == 0.10
    assert verdict.days_required is None
    assert verdict.days_provisional is False
    # The note states the FLOOR that justifies the refusal, with its inputs, so a
    # reader can check the arithmetic instead of taking "pinned" on trust.
    assert "0.1250" in verdict.note and "lattice step" in verdict.note


def test_a_width_shortfall_QUOTES_a_day_count_below_the_floor():
    """The OTHER value of the same declaration — and the one that had no fixture at all
    before s59, which is exactly the empty cell the roll call exists to expose.

    Below the one-step floor the ratio falls as 1/sqrt(n) like any other interval
    half-width, so a day count IS derivable and refusing one withholds the actionable
    half of §14(a)'s payload. Measured on `dpr_distribution` (war_angel L16, seed 11):
    `ratio * sqrt(n)` holds in a narrow band across a 200x range in n, and the
    projection from n=400 named 879 days against an observed crossing between 800 and
    1,000.

    The sample below is the real case this fired on — `dpr` on the baseline subject at
    L20 over 700 days, one 1/16 step against a spread of 4.0063, so a floor of 0.0156.
    A 0.109 ratio is then a 9% shortfall that 835 days fixes, which is what a reader
    needs to be told instead of "no day count helps".
    """
    verdict = DistributionConvergence().verdict(
        9.25, (9.0, 9.4375), 700, 70.0, 4.0063, step=0.0625)

    assert verdict.converged is False
    assert verdict.criterion == CRITERION_CI_WIDTH_VS_SPREAD
    assert verdict.attained == pytest.approx(0.4375 / 4.0063, rel=1e-6)
    assert verdict.days_required == pytest.approx(
        700 * (0.4375 / 4.0063 / 0.10) ** 2, rel=1e-6)
    assert verdict.days_required < 1_000          # measured crossing: 800-1,000
    assert verdict.days_provisional is False      # a scaling law, not a projection
    assert verdict.note == ""


def test_the_lattice_step_is_the_smallest_gap_between_observations():
    """`lattice_step`'s three values, one fixture each as the roll call requires — and
    writing that row is what showed a near-continuous sample had never been through it.

    The measurement that makes this function load-bearing rather than incidental: EVERY
    per-day quantity in this project is an integer total over a fixed round
    denominator, so `dpr`, `net_damage_taken_per_round` and `attacks_per_round` all
    live on the SAME 1/16 grid. "Is it a lattice quantity?" therefore separates none of
    them, which is what the retired wording of `NO_DAY_COUNT_FOR_WIDTH` assumed;
    `step / spread` separates them completely (0.0156, 0.0053, 0.1250).
    """
    # A lattice sample WITH repeats: the step is the grid, and duplicates must not
    # collapse it to zero.
    assert lattice_step([1.0, 1.0, 1.0625, 1.125, 1.125, 1.25]) == pytest.approx(0.0625)
    # Repeats only — no gap exists, so there is no floor and the gate must not refuse.
    assert lattice_step([2.6875] * 50) == 0.0
    assert lattice_step([]) == 0.0
    # Near-continuous: a tiny minimum gap gives a floor of essentially zero, which is
    # why applying the floor unconditionally is safe rather than needing a declaration.
    assert lattice_step(sorted(1.0 + i * 1e-9 for i in range(100))) == \
        pytest.approx(1e-9, rel=1e-6)


def test_a_near_breakeven_day_count_is_marked_a_PROJECTION():
    """`days_provisional` — the THIRD state s59 added to a pair that could not express
    what this gate actually knows.

    `resolution_sigmas` derives its day count from stderr's 1/sqrt(n) scaling, which
    assumes the POINT ESTIMATE is the true value. That assumption carries the whole
    claim exactly when the 95% interval straddles zero, and 8e's second tier measured
    it failing in BOTH directions on `net_damage_taken_per_round` over the baseline
    subject::

        level  sigmas @2,000  projected  outcome at 20,000
        L6         1.161        13,372   CONVERGED (sigmas 12.868)
        L3         1.617         6,887   NOT converged, and LESS resolved (0.550)

    So "no day count helps" would be FALSE for L6 and "~6.9k days" overstates what is
    known for L3. The number is kept and marked, which is the only answer that is true
    of both rows.

    Note the bound is the 95% multiplier and NOT the gate's own 3.0 threshold: between
    1.96 and 3.0 the sign IS resolved and only the stricter bar fails, so those rows
    get an unqualified day count — L7 (2.130) and L8 (2.548) both converged at 20,000
    about as projected.
    """
    conv = Convergence()
    straddling = conv.verdict(0.0302, 0.01868, 2_000, 2_000, SCALE_INTERVAL)
    assert straddling.converged is False
    assert straddling.criterion == CRITERION_RESOLUTION_SIGMAS
    assert straddling.days_provisional is True
    assert straddling.days_required == pytest.approx(
        2_000 * (3.0 / (0.0302 / 0.01868)) ** 2, rel=1e-6)
    assert "PROJECTION" in straddling.note

    # Sign resolved (2.13 sigmas), stricter bar still failed: a plain day count.
    resolved = conv.verdict(0.0838, 0.03935, 2_000, 2_000, SCALE_INTERVAL)
    assert resolved.converged is False
    assert resolved.criterion == CRITERION_RESOLUTION_SIGMAS
    assert resolved.days_provisional is False
    assert resolved.note == ""

    # The boundary IS the 95% multiplier, asserted so a later change to NORMAL_95
    # cannot drift away from the docstring above.
    assert conv.verdict(NORMAL_95 - 0.01, 1.0, 2_000, 2_000,
                        SCALE_INTERVAL).days_provisional is True
    assert conv.verdict(NORMAL_95 + 0.01, 1.0, 2_000, 2_000,
                        SCALE_INTERVAL).days_provisional is False

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


#: The l16 fixture's day count, deliberately BELOW every declared tier — see that
#: fixture's docstring for why that is the honest choice rather than a shortcut.
SUB_TIER_DAYS = 400


@pytest.fixture(scope="module")
def war_angel_l16():
    """The regime that produces a `ci_width_vs_spread` flag — REPOINTED (s59).

    Until s59 this was L16 at the quick tier, where `attacks_per_round_distribution`
    was the LATTICE case and the only row in the registry that could raise this gate.
    **That declaration was cut** (§14), and with it the gate's only instance at any
    declared tier: measured on war_angel L16, both surviving distributions clear 0.10
    comfortably at 2,000 days (dpr p10 = 0.0649, net_damage_taken p10 = 0.0187), and
    the gate stops firing anywhere above ~800 days.

    So the fixture drops to 400 days, which is where the gate still fires. Pinned to
    the REGIME and not to the number, per s55: what this must EXHIBIT is asserted in
    `test_the_fixtures_EXHIBIT_both_kinds_of_flag`, and if a later change moves the
    crossing, re-pick the day count rather than widen that assertion.

    **AND THE FLAG IT PRODUCES IS NOW THE FINITE KIND, WHICH IS THE POINT (s59).**
    The first s59 draft repointed this fixture to keep producing an UNREACHABLE flag,
    and then the floor fix in the same session made that impossible on any real run:
    every shipped distribution's one-step floor is far below 0.10 (dpr 0.0156,
    net_damage_taken 0.0053), so a width shortfall here always quotes a day count. The
    94-cell calibration sweep confirms there is no other source either — of 8,366 rows
    it produced exactly 2 `ci_width_vs_spread` verdicts and ZERO `undefined_at_zero`
    ones. **So no production run at any declared tier yields an unreachable verdict**,
    and `pinned_lattice_report` below is what covers that branch instead.
    """
    config = RunConfig(build="war_angel", level=16, enemy="baseline",
                       n_days=SUB_TIER_DAYS, seed=11)
    return build_report(simulate(config))


@pytest.fixture(scope="module")
def baseline_l3():
    """§3.5's baseline SUBJECT at L3 — the regime where `net_damage_taken_per_round`
    is genuinely at BREAK-EVEN, which is what `days_provisional` is about.

    8e measured 0.0302 +/- 0.01868 here (1.617 sigmas) and 0.0032 +/- 0.00589 at
    20,000 days (0.550 sigmas) — i.e. LESS resolved with ten times the data. Pinned to
    that regime rather than to a level that happens to be noisy: the projection is
    doing real work on this row, and on this row it is wrong.
    """
    config = RunConfig(build="baseline", level=3, enemy="baseline",
                       n_days=DAYS, seed=11)
    return build_report(simulate(config))


@pytest.fixture(scope="module")
def pinned_lattice_report():
    """A report whose `ci_width_vs_spread` is GENUINELY pinned — the only remaining
    cover for the unreachable branch, and a real run rather than a synthetic sample.

    §5.4 says in as many words that "a caller may build its own `MetricRegistry` for a
    bespoke analysis", so this re-declares the distribution 8e cut (§14) in a registry
    of its own and runs the engine against it. Three things that buys over a
    hand-built verdict: the whole path is exercised (estimator -> `lattice_step` ->
    gate -> console), the numbers are the engine's rather than mine, and the fixture
    DOCUMENTS why the row is not in the production registry instead of leaving a
    future reader to wonder why the branch has no caller.

    Measured here: `attacks_per_round` over a fixed 16-round denominator has a step of
    1/16 against a spread of 0.5, so the floor is 0.125 — above the 0.10 threshold, so
    p90 refuses a day count while the quantiles whose intervals collapse to zero width
    converge. That is the asymmetry s51 found and s59 explained.
    """
    registry = _build_default_registry()
    registry.register_distribution(DistributionDef(
        name="attacks_per_round_distribution", over="attacks_per_round",
        definition=("TEST-ONLY (s59). Re-declared here because the production registry "
                    "no longer carries it and this is the one branch that needs a "
                    "pinned quantity — see this fixture's docstring and §14."),
        group="panel",
    ))
    config = RunConfig(build="war_angel", level=16, enemy="baseline", n_days=DAYS,
                       seed=11, enemy_options={"control": True}, party_size=1)
    return build_report(simulate(config, registry=registry))


def test_the_fixtures_EXHIBIT_both_kinds_of_flag(war_angel_l4, war_angel_l16,
                                                 pinned_lattice_report):
    """The precondition, asserted separately from the properties under test (s55).

    Without this, a future change that stops either regime producing its kind of flag
    would leave the rendering tests below passing while testing nothing — which is
    exactly how `test_the_unconverged_warning_counts_DISTRIBUTION_points_too` went
    inert, and the only reason that was caught was a guard like this one.

    **THE THIRD ARM IS NEW (s59) AND IT CHANGED WHICH FIXTURE OWNS WHICH KIND.** The
    unreachable flag used to come from `war_angel_l16` and now cannot come from any
    production registry at all: the floor fix means a width shortfall quotes a day
    count whenever the one-step floor is below the threshold, which it is for both
    shipped distributions. So the unreachable arm moves to `pinned_lattice_report`,
    whose bespoke registry supplies a quantity that IS pinned, and `war_angel_l16`
    keeps the width-shortfall arm with a finite day count. Asserting all three here is
    what stops a later change quietly collapsing them back into two.
    """
    finite = [v for _n, v in war_angel_l4.unconverged_verdicts()
              if v.days_required is not None]
    assert finite, "L4 fixture must produce flags with a finite day count"

    # The width gate firing with a QUOTABLE day count — the shape that was a blanket
    # refusal before s59.
    widths = [v for _n, v in war_angel_l16.unconverged_verdicts()
              if v.criterion == CRITERION_CI_WIDTH_VS_SPREAD]
    assert widths, (
        "L16 fixture must produce at least one width shortfall — see its docstring "
        "for the day count where the gate stops firing, and re-pick rather than "
        "widen this"
    )
    assert all(v.days_required is not None for v in widths), (
        "a width shortfall below the one-step floor must QUOTE a day count: these "
        "are continuous-enough quantities and days do help (measured, §14(a))"
    )

    unreachable = [v for _n, v in pinned_lattice_report.unconverged_verdicts()
                   if v.days_required is None]
    assert unreachable, (
        "the pinned fixture must produce at least one flag no day count fixes — it "
        "exists for exactly that branch; see its docstring"
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
        # `days_provisional` joined s59, additive at `schema_version` 1 on the §9.1
        # precedent — a verdict's day count can be a PROJECTION rather than a
        # requirement, and neither the finite number nor the null said so.
        assert set(verdict) == {"criterion", "attained", "required", "days_run",
                                "days_required", "days_factor", "days_provisional",
                                "note"}
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


def test_the_console_flag_says_no_day_count_helps_for_a_width_shortfall(
        pinned_lattice_report):
    """RENAMED and REPOINTED s59 (was `..._for_the_lattice`, on `war_angel_l16`).

    The no-day-count shape is still the contract — the reason, and no multiplier — but
    the row that produces it changed twice in one session. It was the cut lattice
    distribution; then the first repoint put it on a continuous distribution at a
    sub-tier day count; then the floor fix made THAT quote a day count, which is the
    whole point of the fix. So the only honest source is a quantity that is genuinely
    pinned, which is what `pinned_lattice_report` builds.
    """
    text = render(pinned_lattice_report)
    shortfalls = [line for line in text.splitlines()
                  if "ci_width_vs_spread" in line]
    assert shortfalls, "the pinned fixture must render a width-shortfall flag"
    for line in shortfalls:
        assert "no day count helps" in line
        assert "days (" not in line          # no multiplier is quoted


def test_the_console_flag_marks_a_PROVISIONAL_day_count(baseline_l3):
    """The FOURTH console shape (s59), on a real run and through `render`, like the
    other console tests here, so the path under test is the one a reader gets.

    The marker is read from the verdict's own `days_provisional` field rather than
    re-derived in the renderer from `attained`, which would put the 1.96 multiplier in
    a renderer and make two places own one statistical constant — the s54 seam, one
    layer out. The NEGATIVE case (a `resolution_sigmas` shortfall with the sign
    resolved, which must not carry the marker) is asserted at unit level in
    `test_a_near_breakeven_day_count_is_marked_a_PROJECTION`, because no single real
    run is guaranteed to contain both arms and pinning one to a run that happens to
    would be the inert-fixture trap this module already has two instances of.
    """
    text = render(baseline_l3)
    flags = [line for line in text.splitlines()
             if "[unconverged:" in line and "net_damage_taken_per_round" in line]
    assert flags, (
        "fixture must EXHIBIT a near-break-even interval-scale row — see the "
        "baseline_l3 docstring for the measured sigmas (s55's guard)"
    )
    line = flags[0]
    assert "resolution_sigmas" in line
    assert "projection only" in line
    assert "no day count helps" not in line


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
