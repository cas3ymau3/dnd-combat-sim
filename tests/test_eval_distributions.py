"""
test_eval_distributions.py — §5.4's THIRD output kind (evaluation_framework.md
§5.4 "Kind 3 in full", s48): quantiles and spread, with order-statistic and
bootstrap intervals.

Validation framing (§12, memory ``validate-mechanism-not-build-value``): nothing
here asserts that any build's p90 DPR is "correct".  The assertions are about the
MECHANISM — that the estimator says what it claims, that the honest refusals
happen, and that the kind did not disturb anything it was supposed to leave alone.

Per-feature ritual step 5 — TEST THE BRANCH, NOT THE CONVENIENT INSTANCE
------------------------------------------------------------------------
That rule was added at s47 from a bug this exact shape of work produced, and this
change introduces several multi-valued declarations.  The roll call, so that a
value with no fixture is visible rather than merely absent:

==============================  ==============================================
declaration (its values)        fixture that covers each value
==============================  ==============================================
``Statistic.method``            ``order_statistic`` -> every pN point;
  (2 values)                    ``bootstrap`` -> the ``iqr`` point. BOTH ship in
                                the production registry, which is why the method
                                is derived from the statistic rather than chosen
                                (a declared knob would have left one branch to be
                                exercised by a test-only fixture).
``order_statistic_interval``    placeable -> ``_normal_sample`` (n=400);
  (placeable / lower off the    lower off the end -> n=2 at p=0.5;
   end / upper off the end)     upper off the end -> n=20 at p=0.9.
``bootstrap_interval``          n>=2 -> ``_normal_sample``; n<2 -> ``[7.0]``.
  (resamplable / not)
``DistributionConvergence``     each of the six rejection paths plus the accept
  (7 outcomes, incl. the        path has its own case in
   spread denominator added     ``test_distribution_convergence_*``; the
   at s48)                      ``spread == 0`` point-mass branch has its own test,
                                and the PROPERTY the spread denominator exists for
                                (translation invariance) is asserted directly rather
                                than inferred from the rejection table.
``register_distribution``       all six refusals + the accept path, one case
  (7 outcomes)                  each, in ``test_registration_refuses_*``.
``MetricSamples.per_day_values``fixed -> ``dpr``; random -> ``save_fail_rate``'s
  (fixed / random denominator)  cell, which must RAISE.
row ``status`` on a point       measured -> a real run; unavailable -> the
  (3 values)                    bespoke registry in ``_unavailable_registry``,
                                because no SHIPPED metric is unavailable for
                                these two distributions; unmeasured -> an empty
                                sample, which ``RunConfig`` cannot produce but
                                ``estimate_distribution`` must still handle.
==============================  ==============================================

The two that would otherwise have gone untested are worth naming: the
INHERITED-unavailable path has no production fixture at all (both shipped
distributions are over always-available scalars), and the unmeasured path is
unreachable through ``RunConfig`` because ``n_days >= 1`` is validated.  Both get
built fixtures rather than being left to the next session to discover.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pytest

from src.evaluation import (
    IQR,
    METRICS,
    RunConfig,
    build_report,
    render,
    report_to_dict,
    report_to_rows,
    run,
    simulate,
)
from src.evaluation.metrics import (
    DENOMINATORS,
    Denominator,
    DistributionDef,
    MetricDef,
    MetricRegistry,
)
from src.evaluation.statistics import (
    DEFAULT_STATISTICS,
    DEFAULT_DISTRIBUTION_CONVERGENCE,
    METHOD_BOOTSTRAP,
    METHOD_ORDER_STATISTIC,
    DistributionConvergence,
    MetricSamples,
    Statistic,
    bootstrap_interval,
    estimate_distribution,
    order_statistic_interval,
    quantile,
    quantile_statistic,
)
from src.rng import SeededRNG

logging.disable(logging.CRITICAL)

#: Enough days for an order-statistic interval to be placeable at every declared
#: quantile, small enough to stay fast.
DAYS = 120


@pytest.fixture(scope="module")
def report():
    """One real run.  Silvertail because the per-METRIC ritual's roster-scoping
    fixture is the one with a summon, and a distribution inherits its scope from
    the metric it describes."""
    return run(RunConfig(build="silvertail", level=10, n_days=DAYS, seed=7))


def _normal_sample(n=400, seed=0):
    return [float(x) for x in np.random.default_rng(seed).normal(50.0, 10.0, n)]


# ---------------------------------------------------------------------------
# The point estimate: the ecosystem's definition, not a bespoke one
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("p", [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0])
def test_quantile_is_the_numpy_and_r_default_definition(p):
    """Type-7 linear interpolation, to the last bit.

    This matters more than it looks: a reader who exports the per-day column and
    runs ``quantile()`` in R must get the artifact's number back. A bespoke
    definition would make the obvious check disagree with the published figure and
    cost an afternoon of someone's trust.
    """
    sample = _normal_sample()
    assert quantile(sorted(sample), p) == pytest.approx(
        float(np.quantile(sample, p)), abs=1e-12)


def test_quantile_of_a_single_observation_is_that_observation():
    assert quantile([3.5], 0.9) == 3.5


# ---------------------------------------------------------------------------
# Branch 1 of 2: the ORDER-STATISTIC interval
# ---------------------------------------------------------------------------

def test_order_statistic_interval_brackets_the_estimate_and_is_asymmetric():
    """Two order statistics straddling the estimate — NOT ``value +/- 1.96*se``.

    The asymmetry is the whole reason this kind could not reuse ``MetricValue``,
    whose ``ci95()`` derives a symmetric interval from a standard error. If the
    bounds came out symmetric by construction we would have built the wrong thing.
    """
    sample = sorted(_normal_sample())
    asymmetric = 0
    for p in (0.1, 0.25, 0.5, 0.75, 0.9):
        ci, note = order_statistic_interval(sample, p)
        assert note == ""
        assert ci is not None
        value = quantile(sample, p)
        assert ci[0] <= value <= ci[1]
        if not math.isclose(value - ci[0], ci[1] - value, rel_tol=1e-9):
            asymmetric += 1
    assert asymmetric, "every interval came out symmetric — suspect a derived half-width"


def test_order_statistic_interval_has_the_published_coverage_ranks():
    """n=100, p=0.5 -> [X_(40), X_(61)], the textbook 95% CI for a median.

    An independent check on the binomial arithmetic: this pair appears in standard
    nonparametric tables, so it pins the construction against something that was
    not computed by this code.
    """
    sample = [float(i) for i in range(1, 101)]      # X_(k) == k
    ci, note = order_statistic_interval(sample, 0.5)
    assert note == ""
    assert ci == (40.0, 61.0)


def test_order_statistic_interval_is_conservative_at_the_nominal_level():
    """Coverage of the constructed interval is at least 95%, computed exactly from
    the binomial it is built on rather than simulated."""
    from src.evaluation.statistics import _binomial_ranks
    n, p = 100, 0.5
    r, s = _binomial_ranks(n, p, 0.05)
    # P(r <= B <= s-1) with B ~ Bin(n, p), summed exactly.
    coverage = sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k)
                   for k in range(r, s))
    assert coverage >= 0.95


@pytest.mark.parametrize("n, p, missing", [
    (2, 0.5, "lower"),        # both ends unplaceable; the lower is reported first
    (20, 0.9, "upper"),       # the tail runs off the top of the sample
])
def test_order_statistic_interval_refuses_rather_than_clamping(n, p, missing):
    """The honest report is a measured value with NO interval.

    Clamping the bound to the sample's extreme would assert a precision the data
    does not have — the same class of error as writing 0 for an unmeasured metric
    (§3.4), and harder to spot because the number looks reasonable.
    """
    sample = [float(i) for i in range(n)]
    ci, note = order_statistic_interval(sample, p)
    assert ci is None
    assert missing in note and f"n={n}" in note


# ---------------------------------------------------------------------------
# Branch 2 of 2: the BOOTSTRAP interval
# ---------------------------------------------------------------------------

def test_bootstrap_interval_brackets_the_estimate():
    sample = sorted(_normal_sample())
    ci, note = bootstrap_interval(
        sample, lambda block: (np.quantile(block, 0.75, axis=1)
                               - np.quantile(block, 0.25, axis=1)),
        seed=1, resamples=500)
    assert note == ""
    assert ci is not None
    iqr = quantile(sample, 0.75) - quantile(sample, 0.25)
    assert ci[0] <= iqr <= ci[1]


def test_bootstrap_interval_is_reproducible_from_its_seed():
    """An artifact's interval must not change between two renderings of the same
    report, which is why the seed is a SHA of the label rather than ``hash()``
    (salted per process)."""
    sample = sorted(_normal_sample())
    fn = (lambda block: np.quantile(block, 0.75, axis=1)
          - np.quantile(block, 0.25, axis=1))
    first, _ = bootstrap_interval(sample, fn, seed=99, resamples=400)
    again, _ = bootstrap_interval(sample, fn, seed=99, resamples=400)
    other, _ = bootstrap_interval(sample, fn, seed=100, resamples=400)
    assert first == again
    assert first != other


def test_bootstrap_interval_refuses_a_sample_it_cannot_resample():
    ci, note = bootstrap_interval([7.0], lambda block: block[:, 0], seed=1,
                                  resamples=10)
    assert ci is None and "nothing to resample" in note


def test_the_two_methods_agree_on_the_same_quantile():
    """A cross-check between the branches, which is only possible because both are
    built: the exact binomial interval and a percentile bootstrap of the same
    quantile should land in the same place. They are different constructions, so
    agreement is evidence neither is simply wrong."""
    sample = sorted(_normal_sample(n=2000, seed=5))
    exact, _ = order_statistic_interval(sample, 0.5)
    boot, _ = bootstrap_interval(
        sample, lambda block: np.quantile(block, 0.5, axis=1),
        seed=3, resamples=2000)
    assert exact is not None and boot is not None
    width_exact = exact[1] - exact[0]
    width_boot = boot[1] - boot[0]
    assert width_boot == pytest.approx(width_exact, rel=0.25)


# ---------------------------------------------------------------------------
# The statistic vocabulary: the method is DERIVED, not chosen
# ---------------------------------------------------------------------------

def test_the_statistic_carries_its_own_method():
    assert all(s.method == METHOD_ORDER_STATISTIC
               for s in DEFAULT_STATISTICS if s.p is not None)
    assert IQR.method == METHOD_BOOTSTRAP
    assert IQR.p is None


def test_a_non_quantile_cannot_claim_the_exact_method():
    """The order-statistic interval places its bounds at two RANKS of the sorted
    sample, which means nothing for a statistic that is not a quantile. Declaring
    it anyway is refused rather than silently producing ranks of an IQR."""
    with pytest.raises(ValueError, match="QUANTILE only"):
        Statistic(label="bogus", description="", method=METHOD_ORDER_STATISTIC,
                  tail_fraction=0.5, point=lambda v: 0.0)


def test_a_bootstrap_statistic_needs_a_vectorized_form():
    with pytest.raises(ValueError, match="vectorized form"):
        Statistic(label="bogus", description="", method=METHOD_BOOTSTRAP,
                  tail_fraction=0.5, point=lambda v: 0.0)


def test_the_tail_fraction_is_not_hostage_to_float_noise():
    """``1.0 - 0.9`` is 0.09999999999999998, which would make a p90 at exactly the
    ``min_tail_observations`` boundary fail by 1e-14. A convergence verdict that
    flips on the last bit of a subtraction is not a verdict."""
    assert quantile_statistic(0.90).tail_fraction == 0.1
    assert 500 * quantile_statistic(0.90).tail_fraction >= 50.0


# ---------------------------------------------------------------------------
# Convergence — the §6.2 heuristic in the terms a quantile has
# ---------------------------------------------------------------------------

def test_distribution_convergence_accepts_a_tight_well_supported_estimate():
    rule = DistributionConvergence(ci_width_vs_spread=0.1,
                                   min_tail_observations=50, min_days=100)
    assert rule.check(10.0, (9.5, 10.5), n=1000, tail_observations=100, spread=20.0)


@pytest.mark.parametrize("value, ci, n, tail, spread, why", [
    (None, (9.5, 10.5), 1000, 100, 20.0, "no value"),
    (10.0, None,        1000, 100, 20.0, "no interval could be placed"),
    (10.0, (9.5, 10.5),   50, 100, 20.0, "too few days"),
    (10.0, (9.5, 10.5), 1000,  10, 20.0, "too few tail observations"),
    (10.0, (5.0, 15.0), 1000, 100, 20.0, "interval too wide for the spread"),
    (10.0, (9.5, 10.5), 1000, 100,  0.0, "point mass, but the interval has width"),
    (10.0, (9.5, 10.5), 1000, 100, None, "no spread at all (empty sample)"),
])
def test_distribution_convergence_rejects_each_way_it_can(value, ci, n, tail,
                                                          spread, why):
    rule = DistributionConvergence(ci_width_vs_spread=0.1,
                                   min_tail_observations=50, min_days=100)
    assert not rule.check(value, ci, n=n, tail_observations=tail,
                          spread=spread), why


def test_a_point_mass_converges_only_on_a_point_interval():
    """``spread == 0`` means p10 == p90: there is nothing to resolve, so the only
    readable interval is a degenerate one. This falls OUT of the ratio rather than
    needing the special case for a zero VALUE that the old criterion required."""
    rule = DistributionConvergence(ci_width_vs_spread=0.1,
                                   min_tail_observations=1, min_days=1)
    assert rule.check(7.0, (7.0, 7.0), n=100, tail_observations=50, spread=0.0)


def test_the_convergence_criterion_is_translation_invariant():
    """THE s48 REASON for dividing by the sample's spread instead of by the point's
    value. ``width / abs(value)`` changes when you add a constant to every day —
    which changes nothing whatever about the estimate's precision.

    Measured on the real thing before the fix (net_damage_taken_per_round, war_angel
    L13, 2000 days): a flat +100 per day moved the p90 criterion's input from 0.0932
    to 0.0147, making the same estimate look 6.3x more precise for being relabelled.
    Zero was never the real problem; it was only where the misbehaviour became
    infinite.
    """
    base = _normal_sample(n=600, seed=11)
    verdicts = {}
    for shift in (0.0, 1000.0):
        sample = [v + shift for v in base]
        points = estimate_distribution(
            "d", sample, DEFAULT_STATISTICS,
            convergence=DistributionConvergence(min_days=1,
                                                min_tail_observations=1),
            seed=5)
        verdicts[shift] = {p.statistic: p.converged for p in points}
        # And the yardstick itself is unmoved by the shift.
        shifted = sorted(sample)
        assert quantile(shifted, 0.9) - quantile(shifted, 0.1) == pytest.approx(
            quantile(sorted(base), 0.9) - quantile(sorted(base), 0.1))
    assert verdicts[0.0] == verdicts[1000.0]


def test_the_yardstick_is_shared_by_every_point_of_one_distribution():
    """One spread per distribution, so 'p10 unconverged but p50 converged' says
    something about those two ESTIMATES rather than about which denominator each
    happened to be judged against.

    Uses ``simulate`` rather than the module fixture because the check needs the
    per-day samples, which an ``EvalReport`` deliberately does not carry.
    """
    output = simulate(RunConfig(build="war_angel", level=13, n_days=DAYS, seed=7))
    shape = build_report(output).distribution("dpr_distribution")
    sample = sorted(output.samples["dpr"].per_day_values())
    spread = quantile(sample, 0.90) - quantile(sample, 0.10)
    rule = DistributionConvergence()
    for point in shape.points.values():
        assert point.converged == rule.check(
            point.value, point.ci95, point.n, point.tail_observations, spread)


def test_a_refused_interval_is_never_converged():
    """Precision cannot be asserted without a bound, so the two refusals compose:
    an estimate the estimator declined to bracket fails the guard automatically."""
    points = estimate_distribution("d", [float(i) for i in range(20)],
                                   (quantile_statistic(0.9),),
                                   convergence=DistributionConvergence(
                                       min_days=1, min_tail_observations=0),
                                   seed=1)
    assert points[0].measured and points[0].ci95 is None
    assert not points[0].converged


def test_an_exactly_degenerate_distribution_converges_at_zero():
    """Every day identical: the value is 0 and the interval has zero width, so the
    zero-valued branch of the guard accepts it. A noisy estimate straddling zero
    must not."""
    points = estimate_distribution("d", [0.0] * 200, (quantile_statistic(0.5),),
                                   convergence=DistributionConvergence(
                                       min_days=10, min_tail_observations=10),
                                   seed=1)
    assert points[0].value == 0.0 and points[0].ci95 == (0.0, 0.0)
    assert points[0].converged


# ---------------------------------------------------------------------------
# Registration: the refusals that keep a dishonest declaration out
# ---------------------------------------------------------------------------

def _scalar(name, denominator="rounds", availability=None, **kwargs):
    return MetricDef(
        name=name, unit="damage/round", denominator=denominator,
        source="test", definition="test", numerator=lambda s: 1.0,
        **({"availability": availability} if availability else {}),
        **kwargs,
    )


def test_registration_accepts_a_distribution_over_a_fixed_denominator_scalar():
    registry = MetricRegistry([_scalar("thing")])
    registered = registry.register_distribution(
        DistributionDef(name="thing_distribution", over="thing", definition="d"))
    # The unit is FILLED IN from the metric, never declared, so the two cannot drift.
    assert registered.unit == "damage/round"
    assert registry.distribution("thing_distribution") is registered


def test_registration_refuses_an_unregistered_over():
    registry = MetricRegistry([_scalar("thing")])
    with pytest.raises(ValueError, match="not a registered metric"):
        registry.register_distribution(
            DistributionDef(name="d", over="ghost", definition="d"))


def test_registration_refuses_a_random_denominator():
    """THE eligibility rule, and the reason it is structural rather than advisory:
    on a day whose denominator is zero the ratio is undefined, not zero, so the
    per-day sample a quantile would read does not exist."""
    DENOMINATORS.setdefault("test_random", Denominator(
        name="test_random", description="t", fixed=False, per_day=lambda s: 1.0))
    registry = MetricRegistry([_scalar("rate", denominator="test_random")])
    with pytest.raises(ValueError, match="RANDOM"):
        registry.register_distribution(
            DistributionDef(name="d", over="rate", definition="d"))


def test_registration_refuses_a_breakdown_cell():
    """A cell has per-day samples too, so this would otherwise let a KEYED
    distribution in by the side door — with no key on its rows to say which cell
    it describes."""
    cell = next(d for d in METRICS if d.breakdown is not None
                and d.denominator_spec.fixed)
    registry = MetricRegistry()
    registry.register_breakdown(METRICS.breakdown(cell.breakdown))
    with pytest.raises(ValueError, match="is a CELL of breakdown"):
        registry.register_distribution(
            DistributionDef(name="d", over=cell.name, definition="d"))


def test_registration_refuses_a_duplicate_or_colliding_name():
    registry = MetricRegistry([_scalar("thing")])
    registry.register_distribution(
        DistributionDef(name="thing_distribution", over="thing", definition="d"))
    with pytest.raises(ValueError, match="already registered"):
        registry.register_distribution(
            DistributionDef(name="thing_distribution", over="thing", definition="d"))
    with pytest.raises(ValueError, match="collides"):
        registry.register_distribution(
            DistributionDef(name="thing", over="thing", definition="d"))


def test_a_distribution_cannot_be_the_headline():
    """§5.3 allows exactly one headline and §5.4 keeps it a scalar. A build's
    headline is where its average lands; its spread is reported beside that."""
    with pytest.raises(ValueError, match="cannot be the headline"):
        DistributionDef(name="d", over="dpr", definition="d", group="headline")


def test_a_distribution_needs_at_least_one_distinct_statistic():
    with pytest.raises(ValueError, match="declares no statistics"):
        DistributionDef(name="d", over="dpr", definition="d", statistics=())
    with pytest.raises(ValueError, match="duplicate statistic"):
        DistributionDef(name="d", over="dpr", definition="d",
                        statistics=(quantile_statistic(0.5),
                                    quantile_statistic(0.5)))


# ---------------------------------------------------------------------------
# per_day_values: the same refusal, one layer down
# ---------------------------------------------------------------------------

def test_per_day_values_refuses_a_random_denominator():
    samples = MetricSamples(metric="rate", fixed_denominator=False)
    samples.record(1.0, 2.0, 1.0)
    with pytest.raises(ValueError, match="no per-day value"):
        samples.per_day_values()


def test_per_day_values_is_the_vector_the_scalar_averages(report):
    """The payoff of declaring a distribution OVER a metric rather than beside it:
    the median and the mean describe the SAME sample, bit for bit, so the two
    sections of the artifact can never be talking about different runs."""
    output = simulate(RunConfig(build="war_angel", level=5, n_days=40, seed=2))
    values = output.samples["dpr"].per_day_values()
    assert len(values) == 40
    assert sum(values) / len(values) == build_report(output)["dpr"].value


# ---------------------------------------------------------------------------
# The kind, end to end on a real run
# ---------------------------------------------------------------------------

def test_both_shipped_distributions_estimate_every_declared_statistic(report):
    assert set(report.distributions) == {"dpr_distribution",
                                         "net_damage_taken_distribution"}
    shape = report.distribution("dpr_distribution")
    assert list(shape.points) == ["p10", "p25", "p50", "p75", "p90", "iqr"]
    assert shape.over == "dpr" and shape.unit == "damage/round"
    assert all(point.measured for point in shape.points.values())


def test_the_quantiles_are_ordered_and_the_iqr_matches_them(report):
    shape = report.distribution("dpr_distribution")
    values = [shape[label].value for label in ("p10", "p25", "p50", "p75", "p90")]
    assert values == sorted(values)
    assert shape["iqr"].value == pytest.approx(
        shape["p75"].value - shape["p25"].value)


def test_the_iqr_row_survives_the_prune_rule_it_looks_like_it_fails(report):
    """IQR equals p75 - p25 in VALUE, which under a naive 'derivable => cut' rule
    would delete the row. §5.4's actual survival rule keeps it: the uncertainty is
    NOT reconstructible downstream, because that needs the two quantiles'
    covariance, which only this layer sees. The test of that claim is that its
    interval is not the difference of theirs."""
    shape = report.distribution("dpr_distribution")
    naive = (shape["p75"].ci95[0] - shape["p25"].ci95[1],
             shape["p75"].ci95[1] - shape["p25"].ci95[0])
    assert shape["iqr"].ci95 != naive


def test_every_point_reports_an_interval_and_no_standard_error(report):
    """A quantile has no delta-method standard error. Writing the interval's
    half-width into ``stderr`` would invite a reader to rebuild a symmetric
    interval the estimator never produced."""
    rows = [r for r in report_to_rows(report) if r["kind"] == "distribution"]
    assert rows
    for row in rows:
        assert row["stderr"] is None, row["metric"]
        if row["status"] == "measured" and row["ci_low"] is not None:
            assert row["ci_low"] <= row["value"] <= row["ci_high"]


def test_the_mean_of_the_sample_is_the_scalar_it_is_declared_over(report):
    """Stated as a property of the ARTIFACT, not just of the samples: the headline
    and its distribution describe one quantity."""
    shape = report.distribution("dpr_distribution")
    assert shape["p10"].value <= report["dpr"].value <= shape["p90"].value


# ---------------------------------------------------------------------------
# §3.4's three states, on the third kind
# ---------------------------------------------------------------------------

def _unavailable_registry():
    """A registry whose distribution is over a metric no run can produce.

    Built rather than borrowed: BOTH shipped distributions are declared over
    always-available scalars, so the inherited-unavailable branch has no
    production fixture. Per-feature ritual step 5 — a value with no fixture is
    untested however many tests exist.
    """
    registry = MetricRegistry()
    registry.register(MetricDef(
        name="dpr", unit="damage/round", denominator="rounds", source="t",
        definition="t", numerator=lambda s: s.own_damage(), group="headline"))
    registry.register(_scalar(
        "unwired",
        availability=lambda ctx: "the channel this reads is not wired yet"))
    registry.register_distribution(
        DistributionDef(name="unwired_distribution", over="unwired", definition="d"))
    return registry


def test_an_unavailable_metric_makes_its_distribution_unavailable_with_the_same_reason():
    """Not a different kind of gap — the SAME gap, so §3.4 needs no new vocabulary
    and a reader is not told two stories about one missing channel."""
    output = simulate(RunConfig(build="war_angel", level=1, n_days=6, seed=1),
                      registry=_unavailable_registry())
    shape = build_report(output).distribution("unwired_distribution")
    assert all(not point.available for point in shape.points.values())
    assert all("not wired yet" in point.note for point in shape.points.values())
    assert all(point.value is None and point.ci95 is None
               for point in shape.points.values())

    rows = [r for r in report_to_rows(build_report(output))
            if r["kind"] == "distribution"]
    assert {r["status"] for r in rows} == {"unavailable"}
    assert all(r["value"] is None for r in rows)


def test_an_empty_sample_is_unmeasured_not_zero():
    """Unreachable through ``RunConfig`` (``n_days >= 1`` is validated), and tested
    anyway: the estimator must not answer 0.0 for a sample it never saw."""
    points = estimate_distribution("d", [], DEFAULT_STATISTICS,
                                   convergence=DEFAULT_DISTRIBUTION_CONVERGENCE,
                                   seed=1)
    assert all(p.value is None and p.available and not p.converged for p in points)


# ---------------------------------------------------------------------------
# The artifact (§9.1) — one row shape, no schema break
# ---------------------------------------------------------------------------

def test_the_third_section_landed_without_a_schema_break(report):
    record = report_to_dict(report, include_data_dictionary=True)
    assert record["schema_version"] == 1
    assert record["results"]["distributions"]
    assert record["data_dictionary"]["distributions"]


def test_all_three_kinds_share_one_row_shape(report):
    """§9.1's central promise: a consumer writes ONE parser. If the third kind had
    needed a field the others lack, that promise would be broken at the boundary
    where it matters most — the first new section a site has to handle."""
    record = report_to_dict(report, include_data_dictionary=False)
    rows = list(record["results"]["scalars"])
    for block in record["results"]["breakdowns"]:
        rows.extend(block["cells"] + block["margins"])
    for block in record["results"]["distributions"]:
        rows.extend(block["points"])
    assert len({frozenset(row) for row in rows}) == 1


def test_a_distribution_block_declares_no_sum_rule(report):
    """Quantiles of one sample partition nothing, so offering a value from the
    two-value sum vocabulary would imply a choice exists. The field is absent on
    the block and blank in the CSV — the same 'not applicable' convention the
    dimension columns already use."""
    record = report_to_dict(report, include_data_dictionary=False)
    for block in record["results"]["distributions"]:
        assert "sum_rule" not in block
        assert "cells" not in block and "margins" not in block
    rows = [r for r in report_to_rows(report) if r["kind"] == "distribution"]
    assert rows and all(r["sum_rule"] is None for r in rows)


def test_the_statistic_travels_as_a_key_not_inside_the_metric_name(report):
    """The §5.4 failure this layer exists to prevent, checked at the third kind's
    boundary: a consumer must never parse ``dpr_distribution[p50]`` back into
    ``p50``. Carrying it in the same ``key`` dict a breakdown cell uses is also
    what keeps a later KEYED distribution additive rather than a schema change."""
    rows = [r for r in report_to_rows(report) if r["kind"] == "distribution"]
    assert {r["statistic"] for r in rows} == {"p10", "p25", "p50", "p75",
                                              "p90", "iqr"}
    assert all(r["distribution"] in ("dpr_distribution",
                                     "net_damage_taken_distribution")
               for r in rows)
    # And the other kinds leave the column blank — 'not keyed by it', not 'margin'.
    others = [r for r in report_to_rows(report) if r["kind"] != "distribution"]
    assert all(r["statistic"] is None for r in others)


def test_every_distribution_row_names_the_method_that_placed_its_interval(report):
    """An asymmetric interval is unreadable without knowing how it was placed, and
    the two methods are not interchangeable: one is exact, one is resampled."""
    rows = [r for r in report_to_rows(report) if r["kind"] == "distribution"]
    by_statistic = {r["statistic"]: r["method"] for r in rows}
    assert by_statistic["p50"] == METHOD_ORDER_STATISTIC
    assert by_statistic["iqr"] == METHOD_BOOTSTRAP
    others = [r for r in report_to_rows(report) if r["kind"] != "distribution"]
    assert all(r["method"] is None for r in others)


def test_the_console_prints_the_shape_without_claiming_a_standard_error(report):
    text = render(report)
    assert "DISTRIBUTIONS" in text
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("DISTRIBUTIONS"))
    end = next(i for i, line in enumerate(lines[start + 1:], start + 1)
               if line and line[0].isupper() and not line.startswith("DISTRIBUTIONS"))
    section = lines[start:end]
    body = "\n".join(section)
    assert "dpr_distribution" in body and "p50" in body
    assert "order_statistic" in body and "bootstrap" in body
    # A '+/-' on a point line would assert a symmetric interval the estimator never
    # produced; the scalar sections above print one and are deliberately excluded.
    assert not any("+/-" in line for line in section
                   if "ASYMMETRIC" not in line)


# ---------------------------------------------------------------------------
# The constraint that outranks the feature: NO NEW DICE OUTSIDE COMBAT
# ---------------------------------------------------------------------------

class _CountingRNG(SeededRNG):
    """A ``SeededRNG`` that counts draws — the instrumented generator
    ``simulate(rng=...)`` exists for."""

    def __init__(self, seed):
        super().__init__(seed)
        self.draws = 0

    def roll(self, n, sides):
        self.draws += 1
        return super().roll(n, sides)


def test_building_the_report_draws_nothing_from_the_combat_stream():
    """Per-feature ritual step 3, as a direct measurement rather than a promise.

    Every die in a run comes off ONE ``SeededRNG`` tape, so a single extra draw
    from it outside combat shifts every subsequent roll and breaks §12's
    bit-identical parity proof against ``validation.run_level``. The bootstrap
    therefore resamples from its own ``numpy.random.default_rng``. This asserts the
    tape did not move while two full reports — bootstrap included — were built.
    """
    rng = _CountingRNG(4)
    output = simulate(RunConfig(build="war_angel", level=5, n_days=30, seed=4),
                      rng=rng)
    after_run = rng.draws
    assert after_run > 0

    first = build_report(output)
    second = build_report(output)
    assert rng.draws == after_run

    # And the resampler's own stream is a pure function of the run's seed, so the
    # same report rendered twice carries the same interval.
    assert (first.distribution("dpr_distribution")["iqr"].ci95
            == second.distribution("dpr_distribution")["iqr"].ci95)


def test_the_uncertainty_layer_cannot_reach_the_combat_rng():
    """A structural assertion, in the spirit of s47's 'the string ``influence`` does
    not appear in the record': the module that resamples does not import the dice
    channel, so the rule above cannot be broken by a later edit that looks local."""
    import ast
    import pathlib

    import src.evaluation.statistics as module

    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            imported.update(alias.name for alias in node.names)
    # Parsed rather than grepped: the module DISCUSSES SeededRNG at length in its
    # docstrings, and a test that cannot tell prose from code is a test that will be
    # deleted the next time someone edits a comment.
    assert not any("rng" == name or name.endswith(".rng") or name == "SeededRNG"
                   for name in imported), sorted(imported)
