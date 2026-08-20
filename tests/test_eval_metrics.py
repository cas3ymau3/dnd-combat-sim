"""
test_eval_metrics.py — step 2 of the evaluation framework (design/evaluation_framework.md
§13.2): the metric registry, the statistics layer, ``EvalReport``, and paired seeding.

Validation framing (§12, memory ``validate-mechanism-not-build-value``): every test
here asserts a MECHANISM.  Denominators are declared and applied; a rare-event
metric reports ``converged=False`` where DPR reports True; a metric the run cannot
produce says so with a reason instead of emitting a zero; two paired configs
differing only in an inert toggle draw byte-identical dice.  **No test asserts that
any build's DPR value is "correct"** — there is no external standard for it to be
correct against (§11).

The step-1 parity proof stays in ``test_eval_framework.py`` and is re-pointed at the
registry's ``dpr`` metric, which is what step 2 replaced the ``mean_dpr`` stand-in with.
"""

from __future__ import annotations

import logging
import math

import pytest

from src.evaluation import (
    DENOMINATORS,
    METRICS,
    Convergence,
    MetricDef,
    MetricRegistry,
    MetricValue,
    RunConfig,
    compare,
    run,
)
from src.evaluation.metrics import (
    ALL,
    ATTRIBUTABLE_ROLES,
    DAMAGE_TYPES,
    GROUPS,
    HEAL_CONTEXTS,
    SAVE_CHANNELS,
    SAVE_STATS,
    BreakdownDef,
    Dimension,
    KeySpace,
)
from src.evaluation.report import build_report
from src.evaluation.runner import simulate
from src.evaluation.statistics import (
    MetricSamples,
    fixed_estimate,
    paired_delta,
    ratio_estimate,
)
from src.rng import SeededRNG

logging.disable(logging.CRITICAL)

#: Enough days for the two estimators and the convergence heuristics to have
#: something to say, few enough to keep the suite's runtime honest.
DAYS = 300

#: The one Silvertail scenario that lights up saves AND concentration: the zone
#: makes the enemy tank the master, so its hits force concentration checks.
ZONE = {"zone_effect": "spirit_guardians"}


# ---------------------------------------------------------------------------
# The estimators (§6.2) — the two kinds are one theory
# ---------------------------------------------------------------------------

def test_fixed_estimator_is_the_plain_mean_and_its_standard_error():
    ys = [10.0, 20.0, 30.0, 40.0]
    value, stderr, influence = fixed_estimate(ys, [4.0] * 4)

    per_day = [y / 4.0 for y in ys]
    mean = sum(per_day) / 4
    var = sum((x - mean) ** 2 for x in per_day) / 3
    assert value == mean
    assert stderr == math.sqrt(var / 4)
    # Influence values are the centered per-day values, which is what makes a
    # paired delta on DPR reduce to sd(vA - vB)/sqrt(N).
    assert influence == [x - mean for x in per_day]


def test_ratio_estimator_collapses_to_the_fixed_one_when_the_denominator_is_constant():
    """The two estimator kinds are ONE theory: substituting a constant denominator
    into the ratio estimator reproduces the plain mean.  Two code paths exist only
    to pin the fixed one's floating-point operation order to validation.py's."""
    ys = [7.0, 11.0, 3.0, 19.0, 5.0]
    fixed_value, fixed_stderr, _ = fixed_estimate(ys, [16.0] * 5)
    ratio_value, ratio_stderr, _ = ratio_estimate(ys, [16.0] * 5)

    assert ratio_value == pytest.approx(fixed_value, rel=1e-12)
    assert ratio_stderr == pytest.approx(fixed_stderr, rel=1e-12)


def test_ratio_estimator_weights_events_not_days():
    """A fail RATE must weigh each save equally, not each day.  Mean-of-ratios would
    give the one-save day the same say as the twelve-save day; ratio-of-means does
    not, which is why it is the estimator for a random denominator."""
    failures = [1.0, 0.0]
    forced = [1.0, 9.0]
    value, _stderr, _ = ratio_estimate(failures, forced)

    assert value == pytest.approx(1 / 10)                    # ratio of means
    mean_of_ratios = (1 / 1 + 0 / 9) / 2
    assert mean_of_ratios == pytest.approx(0.5)              # the wrong answer
    assert value != pytest.approx(mean_of_ratios)


def test_a_zero_denominator_has_no_value_rather_than_a_zero():
    """A rate over "saves that were never forced" is undefined, and reporting 0.0
    would be a fabricated measurement."""
    value, stderr, influence = ratio_estimate([0.0, 0.0], [0.0, 0.0])
    assert value is None and stderr is None and influence == []

    samples = MetricSamples(metric="save_fail_rate[cha_save|*]", fixed_denominator=False)
    for _ in range(5):
        samples.record(0.0, 0.0, 0.0)
    metric_value, _ = samples.estimate(Convergence())
    assert metric_value.value is None
    assert metric_value.available is True         # the channel works; nothing fired
    assert "zero" in metric_value.note


# ---------------------------------------------------------------------------
# Convergence is a DECLARED heuristic (§6.2)
# ---------------------------------------------------------------------------

def test_convergence_requires_precision_events_and_replicates():
    heuristic = Convergence(rel_stderr=0.05, min_events=100.0, min_days=50)

    assert heuristic.check(1.0, 0.04, n=50, n_events=100.0) is True
    assert heuristic.check(1.0, 0.06, n=50, n_events=100.0) is False    # too noisy
    assert heuristic.check(1.0, 0.04, n=50, n_events=99.0) is False     # too few events
    assert heuristic.check(1.0, 0.04, n=49, n_events=100.0) is False    # too few days


def test_an_unmeasured_metric_is_never_converged():
    assert Convergence().check(None, None, n=10_000, n_events=1e9) is False


def test_a_zero_estimate_converges_only_when_every_day_agreed():
    """A relative criterion is undefined at zero, so the rule is explicit: an exactly
    zero standard error (nothing ever happened) converges; a noisy number straddling
    zero does not."""
    heuristic = Convergence(min_days=1)
    assert heuristic.check(0.0, 0.0, n=100, n_events=100.0) is True
    assert heuristic.check(0.0, 0.01, n=100, n_events=100.0) is False


# ---------------------------------------------------------------------------
# The registry: declared, closed, with denominators forced into the open (§5.1/§5.2)
# ---------------------------------------------------------------------------

def test_every_registered_metric_declares_a_complete_data_dictionary_entry():
    """§5.4: the dictionary is now keyed by OUTPUT KIND, and both live kinds carry
    a complete declaration."""
    dictionary = METRICS.data_dictionary()
    assert set(dictionary) == {"scalars", "breakdowns", "distributions"}

    for entry in dictionary["scalars"]:
        assert entry["unit"], entry
        assert entry["definition"], entry
        assert entry["source"], entry
        assert entry["denominator"] in DENOMINATORS, entry
        assert entry["denominator_description"], entry
        assert entry["group"] in GROUPS, entry
        assert entry["breakdown"] is None, entry      # a scalar is nobody's cell

    for entry in dictionary["breakdowns"]:
        assert entry["kind"] == "breakdown", entry
        assert entry["unit"] and entry["definition"] and entry["source"], entry
        assert entry["group"] in GROUPS, entry
        assert entry["key_space"]["dimensions"], entry
        for dimension in entry["key_space"]["dimensions"]:
            assert dimension["keys"], dimension       # a CLOSED, non-empty vocabulary
            assert dimension["description"], dimension
        assert entry["cells"], entry

    # Every cell of every breakdown is also an estimable metric with a real
    # denominator — the expansion is what let the second kind reuse the estimator.
    for breakdown in METRICS.breakdowns:
        for key in breakdown.keys():
            cell = METRICS[breakdown.cell_name(key)]
            assert cell.denominator in DENOMINATORS, cell.name
            assert cell.breakdown == breakdown.name
            assert cell.key == key


def test_the_distribution_kind_is_a_reserved_seam_not_a_built_one():
    """§5.4 kind 3: s46 named it and reserved its artifact section so it can land
    without a schema break; the estimator is still deferred to after step 3."""
    assert METRICS.distributions() == []
    assert METRICS.data_dictionary()["distributions"] == []


def test_a_metric_cannot_declare_a_denominator_outside_the_closed_vocabulary():
    with pytest.raises(ValueError, match="closed vocabulary"):
        MetricDef(name="bogus", unit="x", denominator="per_fortnight",
                  source="nowhere", definition="", numerator=lambda s: 0.0)


def test_a_metric_cannot_invent_a_report_group():
    with pytest.raises(ValueError, match="group must be one of"):
        MetricDef(name="bogus", unit="x", denominator="rounds", source="", definition="",
                  numerator=lambda s: 0.0, group="sidebar")


def test_registering_the_same_name_twice_is_an_error():
    registry = MetricRegistry()
    definition = MetricDef(name="dpr", unit="damage/round", denominator="rounds",
                           source="ledger", definition="", numerator=lambda s: 0.0)
    registry.register(definition)
    with pytest.raises(ValueError, match="already registered"):
        registry.register(definition)


def test_there_is_exactly_one_headline_and_it_is_the_character_column():
    """§5.3: no composite build score.  That only means something if the headline
    stays ONE declared quantity rather than drifting into a basket."""
    assert METRICS.headline.name == "dpr"
    assert [d.name for d in METRICS.group("headline")] == ["dpr"]


def test_roster_totals_are_columns_so_they_cannot_reach_the_headline():
    """The §3.3 rule is structural: party and per-summon figures are in a different
    report group, so no renderer can fold them into the headline by oversight.

    §5.4 collapsed the three flat rows into ``dpr_by_role``; the guarantee is
    unchanged, because the whole breakdown carries the ``column`` group.
    """
    assert METRICS.breakdown("dpr_by_role").group == "column"
    for key in METRICS.breakdown("dpr_by_role").keys():
        assert METRICS.cell("dpr_by_role", key).group == "column"


def test_a_breakdown_can_never_become_the_headline():
    """§5.4's other half of the one-headline guard: §5.3 allows exactly one
    headline, and a headline that is one cell of a larger object is not one."""
    with pytest.raises(ValueError, match="cannot be the headline"):
        BreakdownDef(
            name="bogus", unit="x",
            key_space=KeySpace((Dimension("role", ("characters",), "…"),)),
            source="", definition="", numerator=lambda s, k: 0.0,
            denominator="rounds", group="headline",
        )


def test_the_per_ability_save_family_covers_the_closed_stat_vocabulary():
    """§5.4: the family is a KEY SPACE, not 16 flat rows, and it is UNCROSSED — the
    two dimensions are reported independently.  The completeness argument survives:
    every ability and every channel has a cell, so a zero is a measurement."""
    saves = METRICS.breakdown("saves_forced_per_round")
    rates = METRICS.breakdown("save_fail_rate")
    for family in (saves, rates):
        assert family.key_space.names == ("ability", "channel")
        assert family.crossed is False
        assert set(family.cell_keys()) == (
            {(stat, ALL) for stat in SAVE_STATS}
            | {(ALL, channel) for channel in SAVE_CHANNELS}
        )
        # The grid's cells ("dex saves forced by CONTROL specifically") are NOT
        # materialized: the s46 review dropped them because their per-cell
        # denominators are structurally near-zero.
        assert (SAVE_STATS[0], SAVE_CHANNELS[0]) not in family.cell_keys()
        assert family.margin_keys() == ((ALL, ALL),)


def test_a_crossed_breakdown_materializes_the_grid_where_the_cross_tab_is_the_point():
    """The other side of the same choice.  A summon healing UNDER FIRE is a
    different fact from a summon healing at leisure (healing.md §11.1), so that
    breakdown earns its grid — crossing is a declaration, not a default that
    quietly multiplies cells."""
    healing = METRICS.breakdown("healing_by_source")
    assert healing.crossed is True
    assert (("summons", "combat") in healing.cell_keys()
            and ("summons", "between") in healing.cell_keys())


def test_a_margin_is_computed_here_because_its_stderr_cannot_be_rebuilt_downstream():
    """§5.4's survival rule, made concrete. The [*|*] margin's VALUE is recoverable
    from one dimension's cells, but its standard error is not any function of
    theirs — that needs their covariance, which only this layer sees."""
    report = run(RunConfig(build="silvertail", level=10, n_days=40, seed=11,
                           build_options=ZONE))
    forced = report.breakdown("saves_forced_per_round")

    total = forced.total()
    by_ability = [v for k, v in forced.cells.items() if k[1] == ALL]
    assert total is not None and total.measured and total.value > 0
    assert total.value == pytest.approx(sum(v.value for v in by_ability))
    # The naive downstream reconstruction (assume independence) is NOT what we report.
    naive = math.sqrt(sum(v.stderr ** 2 for v in by_ability))
    assert total.stderr != pytest.approx(naive, rel=1e-6)


def test_an_uncrossed_breakdowns_cells_do_not_partition_the_total():
    """A warning the serializer has to respect: with the dimensions reported
    INDEPENDENTLY, each dimension's profile covers the whole quantity on its own.
    Adding every cell up double-counts — which is why the total is a declared
    margin rather than something a renderer computes."""
    report = run(RunConfig(build="silvertail", level=10, n_days=40, seed=11,
                           build_options=ZONE))
    forced = report.breakdown("saves_forced_per_round")

    total = forced.total().value
    by_ability = sum(v.value for k, v in forced.cells.items() if k[1] == ALL)
    by_channel = sum(v.value for k, v in forced.cells.items()
                     if k[0] == ALL and v.measured)
    every_cell = sum(v.value for v in forced.cells.values() if v.measured)

    assert by_ability == pytest.approx(total)
    assert by_channel == pytest.approx(total)
    assert every_cell == pytest.approx(2 * total)      # …and that is the trap


def test_rate_metrics_declare_random_denominators_and_counts_declare_fixed_ones():
    """The declaration drives the estimator, so getting it wrong is a real bug, not
    a documentation slip."""
    assert METRICS["dpr"].denominator_spec.fixed is True
    assert METRICS["concentration_checks_per_day"].denominator_spec.fixed is True
    assert METRICS["concentration_break_rate"].denominator_spec.fixed is False
    # §5.4: a breakdown's denominator is a TEMPLATE over the key, so the per-cell
    # denominator is the saves forced with THAT ability in THAT channel — not the
    # family total, which would make every cell a share of the same number.
    assert METRICS.cell("save_fail_rate", (ALL, ALL)).denominator_spec.fixed is False
    assert METRICS.cell("save_fail_rate", ("dex_save", ALL)).denominator \
        == "saves_forced[dex_save|*]"
    assert METRICS.cell("save_fail_rate", (ALL, "control")).denominator \
        == "saves_forced[*|control]"
    assert METRICS.cell("saves_forced_per_round", ("dex_save", ALL)).denominator \
        == "rounds"


# ---------------------------------------------------------------------------
# Denominators are APPLIED, not just declared (§5.2)
# ---------------------------------------------------------------------------

def test_the_dpr_denominator_is_the_configured_rounds_per_day():
    """Not a hardcoded 16: change the day's shape and the denominator follows it,
    which is the whole reason it is a named entry rather than a literal."""
    for rounds_per_combat in (2, 4):
        config = RunConfig(build="war_angel", level=5, n_days=4, seed=1,
                           rounds_per_combat=rounds_per_combat)
        output = simulate(config)
        column = output.samples["dpr"].denominator
        assert set(column) == {float(config.rounds_per_day)}
        assert config.rounds_per_day == 4 * rounds_per_combat


def test_dpr_equals_its_own_declared_definition():
    """The registry's ``dpr`` really is characters' damage over rounds_per_day —
    recomputed here straight from the raw per-day column."""
    config = RunConfig(build="war_angel", level=13, n_days=20, seed=4)
    output = simulate(config)
    report = build_report(output)

    per_day = [d / config.rounds_per_day for d in output.headline_damage]
    assert report.headline.value == pytest.approx(sum(per_day) / len(per_day))


def test_a_ratio_metrics_denominator_is_the_random_per_day_count():
    output = simulate(RunConfig(build="silvertail", level=10, n_days=20, seed=3,
                                build_options=ZONE))
    checks = output.samples["concentration_break_rate"].denominator
    # Random, not constant — that is precisely why it needs the ratio estimator.
    assert len(set(checks)) > 1
    assert sum(checks) == output.telemetry.concentration_checks


def test_under_the_default_attribution_the_headline_excludes_summon_damage():
    """The historical basis (``attribution="character"``) — see the attribution tests
    below for the mode where a summon DOES count as the build's output."""
    report = run(RunConfig(build="silvertail", level=10, n_days=30, seed=3))
    headline = report.headline.value
    summon = report["dpr_by_role[summons]"].value
    party = report["dpr_by_role[*]"].value

    assert summon > 0                       # the beast really does contribute
    assert party == pytest.approx(headline + summon)
    assert headline < party


# ---------------------------------------------------------------------------
# Every scalar carries uncertainty (§6.2)
# ---------------------------------------------------------------------------

def test_every_metric_in_a_report_carries_value_n_stderr_and_converged():
    """Not just DPR — §6.2's requirement is that the whole panel does."""
    report = run(RunConfig(build="silvertail", level=10, n_days=40, seed=3,
                           build_options=ZONE))
    assert set(report.values) == set(METRICS.names())
    for value in report.values.values():
        assert isinstance(value, MetricValue)
        assert isinstance(value.converged, bool)
        if value.measured:
            assert value.n == 40
            assert value.stderr is not None
            assert value.ci95() is not None
        else:
            assert value.value is None and value.stderr is None
            assert value.converged is False
            assert value.note


def test_a_rare_event_metric_is_unconverged_where_dpr_is_converged():
    """The point of §6.2: metrics converge at wildly different rates, so one global
    day count cannot certify them all.  A report that showed the rare number without
    its verdict would invite over-reading it."""
    report = run(RunConfig(build="silvertail", level=10, n_days=DAYS, seed=3,
                           build_options=ZONE))
    dpr = report.headline
    rare = report["save_fail_rate[int_save|*]"]

    assert dpr.converged is True
    assert rare.measured is True              # it HAS a value…
    assert rare.converged is False            # …that is not yet worth reading
    assert rare.n_events < METRICS["save_fail_rate[int_save|*]"].convergence.min_events
    # Same run, same day count — the verdict differs because the heuristics do.
    assert rare.n == dpr.n


# ---------------------------------------------------------------------------
# Unavailable vs. measured-zero (§3.4) — the honesty requirement
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("build,level,options", [
    ("war_angel", 13, {}),
    ("starfire_scion", 15, {}),
    ("silvertail", 10, ZONE),
])
def test_control_resilience_is_declared_unavailable_never_a_silent_zero(build, level, options):
    """§3.4 is not yet built, so NO build can measure control resilience today.  A
    zero here would read as "this build resists control perfectly" — the opposite of
    what is known."""
    report = run(RunConfig(build=build, level=level, n_days=10, seed=1,
                           build_options=options))
    for name in ("control_turns_lost_per_round", "control_turns_reduced_per_round",
                 "save_fail_rate[*|control]"):
        value = report[name]
        assert value.available is False
        assert value.value is None
        assert value.converged is False
        assert value.note


def test_the_unavailability_reason_names_which_enemy_model_blocked_it():
    """"War Angel's enemy has no control channel at all" and "Silvertail's enemy has
    one but it is switched off" are different problems with different fixes; the
    report must not flatten them into one message."""
    war_angel = run(RunConfig(build="war_angel", level=13, n_days=4, seed=1))
    silvertail = run(RunConfig(build="silvertail", level=10, n_days=4, seed=1))

    scripted = war_angel["save_fail_rate[*|control]"].note
    baseline = silvertail["save_fail_rate[*|control]"].note
    assert "ScriptedEnemyPolicy" in scripted
    assert "BaselineEnemyPolicy" in baseline and "control=False" in baseline
    assert scripted != baseline


def test_the_mitigation_channel_declares_itself_too():
    """No build installs a mult(t) profile, so "damage mitigated" is structurally
    unmeasurable in the same way control is.

    (The resource ledger was the third such case until s44 wired
    ``record_resource`` at the scheduler's consume sites; it is now measured, and
    its test lives with the other s44 additions below.)"""
    report = run(RunConfig(build="war_angel", level=13, n_days=4, seed=1))
    assert report["damage_mitigated_per_round"].available is False
    assert "damage_multiplier" in report["damage_mitigated_per_round"].note


def test_an_unavailable_metric_costs_no_collection():
    output = simulate(RunConfig(build="war_angel", level=13, n_days=4, seed=1))
    assert "save_fail_rate[*|control]" in output.unavailable
    assert "save_fail_rate[*|control]" not in output.samples


def test_a_missing_role_column_is_unavailable_not_zero():
    """War Angel has no summon, so "summon DPR = 0" would be a category error."""
    report = run(RunConfig(build="war_angel", level=5, n_days=4, seed=1))
    assert report["dpr_by_role[summons]"].available is False
    assert "summons" in report["dpr_by_role[summons]"].note


def test_unmeasured_is_a_distinct_state_from_unavailable():
    """A charisma-save fail rate on a run that forced no charisma save is a
    denominator of zero, not a broken channel.  Both refuse to report a zero; only
    one of them is a gap in the model."""
    report = run(RunConfig(build="silvertail", level=10, n_days=30, seed=3,
                           build_options=ZONE))
    unmeasured = {v.metric for v in report.unmeasured()}
    unavailable = {v.metric for v in report.unavailable()}

    assert "save_fail_rate[cha_save|*]" in unmeasured
    assert not (unmeasured & unavailable)
    assert report["save_fail_rate[cha_save|*]"].available is True
    # …while the count metric over the SAME empty channel is a real measured zero,
    # because its denominator (rounds) is never zero.
    assert report["saves_forced_per_round[cha_save|*]"].value == 0.0


# ---------------------------------------------------------------------------
# Provenance (§4) — including what it cannot say yet
# ---------------------------------------------------------------------------

def test_provenance_resolves_the_build_side_to_the_value_actually_used():
    """§4's load-bearing distinction, at the report level: an option left as ``None``
    is recorded as what the run USED, with the source path named."""
    report = run(RunConfig(build="starfire_scion", level=15, n_days=2, seed=1))
    resolved = report.provenance.resolved["build"]

    assert resolved["options"]["primal_strike_unarmed"] is None      # as requested
    assert resolved["primal_strike_unarmed_effective"] is not None   # as used
    assert "LEVELS[15]" in resolved["primal_strike_unarmed_source"]


def test_provenance_says_plainly_that_the_enemy_side_is_not_resolved():
    """Shipping a plausible-looking but empty ``enemy`` block would imply the
    assumptions were recorded when they were not."""
    provenance = run(RunConfig(build="war_angel", level=13, n_days=2, seed=1)).provenance

    assert provenance.resolved["enemy"] is None
    assert "NOT RESOLVED" in provenance.coverage["enemy_side"]
    assert "§3.4" in provenance.coverage["enemy_side"] or "step 5" in provenance.coverage["enemy_side"]
    # Which enemy path produced the run IS recorded, so §3.4's "never silently
    # compared" rule has something to check against.
    assert provenance.coverage["enemy_path"] == "scripted"


def test_provenance_records_the_config_the_engine_version_and_the_day_tier():
    config = RunConfig(build="war_angel", level=5, n_days=2, seed=17)
    provenance = run(config).provenance

    assert provenance.config == config.canonical()
    assert provenance.day_tier == "custom"
    assert provenance.engine_commit is None or len(provenance.engine_commit) == 40
    assert isinstance(provenance.engine_dirty, bool)
    assert "No external validation source" in provenance.epistemic_note


def test_two_builds_record_different_enemy_paths_so_they_are_not_silently_compared():
    """The §3.4 coupling made visible: War Angel and Silvertail face different enemy
    MODELS, and the reports say so rather than presenting two comparable numbers."""
    war_angel = run(RunConfig(build="war_angel", level=13, n_days=2, seed=1))
    silvertail = run(RunConfig(build="silvertail", level=10, n_days=2, seed=1))

    assert war_angel.provenance.coverage["enemy_path"] == "scripted"
    assert silvertail.provenance.coverage["enemy_path"] == "baseline"
    assert "must not be compared" in war_angel.provenance.coverage["comparability_warning"]


# ---------------------------------------------------------------------------
# Paired seeding / common random numbers (§6.1)
# ---------------------------------------------------------------------------

class _RecordingRNG(SeededRNG):
    """A ``SeededRNG`` that keeps every roll, so "byte-identical dice stream" can be
    asserted directly rather than inferred from equal results."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.stream: list[tuple[int, int, tuple[int, ...]]] = []

    def roll(self, n: int, sides: int) -> list[int]:
        result = super().roll(n, sides)
        self.stream.append((n, sides, tuple(result)))
        return result


def _dice_stream(config: RunConfig) -> list:
    rng = _RecordingRNG(config.seed)
    simulate(config, rng=rng)
    return rng.stream


def test_an_inert_toggle_produces_a_byte_identical_dice_stream():
    """§12's paired-seeding proof.  ``primal_strike_unarmed`` gates a rider that does
    not exist below L15, so at L5 it cannot touch a die."""
    base = RunConfig(build="starfire_scion", level=5, n_days=8, seed=99)
    inert = base.replace(build_options={"primal_strike_unarmed": True})

    stream = _dice_stream(base)
    assert len(stream) > 100                       # the run really did roll dice
    assert _dice_stream(inert) == stream


def test_a_live_toggle_does_move_the_dice_stream():
    """The negative control that keeps the test above from passing vacuously."""
    base = RunConfig(build="starfire_scion", level=15, n_days=6, seed=99)
    live = base.replace(build_options={"fourth_level_spell": "fire_shield"})

    assert _dice_stream(live) != _dice_stream(base)


def test_compare_reseeds_every_config_to_one_shared_base_seed():
    base = RunConfig(build="starfire_scion", level=5, n_days=10, seed=7)
    other = base.replace(seed=999, build_options={"primal_strike_unarmed": True})

    comparison = compare([base, other], labels=["a", "b"])

    assert comparison.seed == 7
    for report in comparison.reports:
        assert report.provenance.config["seed"] == 7
        assert report.provenance.pairing["paired"] is True
        assert report.provenance.pairing["seed"] == 7


def test_a_paired_delta_on_an_inert_toggle_is_exactly_zero():
    """Common random numbers at their limit: identical streams, so the difference
    carries no noise at all."""
    base = RunConfig(build="starfire_scion", level=5, n_days=40, seed=42)
    inert = base.replace(build_options={"primal_strike_unarmed": True})

    delta = compare([base, inert], labels=["raw", "inert"]).delta("inert", "dpr")

    assert delta.paired is True
    assert delta.delta == 0.0
    assert delta.stderr == 0.0


def test_a_paired_delta_is_never_wider_than_the_independent_one():
    """The reason §6.1 makes pairing the default: the shared noise cancels in the
    DIFFERENCE.  How much it cancels depends on how fast the two runs diverge, so
    the assertion is the guaranteed direction, not a promised factor."""
    base = RunConfig(build="starfire_scion", level=15, n_days=DAYS, seed=42)
    alt = base.replace(build_options={"fourth_level_spell": "fire_shield"})

    delta = compare([base, alt], labels=["fount", "fire_shield"]).delta("fire_shield", "dpr")
    independent = math.sqrt(delta.a.stderr ** 2 + delta.b.stderr ** 2)

    assert delta.paired is True
    assert delta.delta == pytest.approx(delta.a.value - delta.b.value)
    assert delta.stderr <= independent


def test_a_delta_against_an_unavailable_metric_reports_no_delta():
    base = RunConfig(build="war_angel", level=13, n_days=6, seed=1)
    alt = base.replace(level=12)

    delta = compare([base, alt], labels=["l13", "l12"]).delta("l12", "save_fail_rate[*|control]")

    assert delta.delta is None and delta.stderr is None
    assert "no delta" in delta.note


def test_an_unpairable_comparison_falls_back_and_says_so():
    """Different day counts cannot be matched day-wise, so the interval reverts to
    the independent one — and the note tells the reader which they are reading."""
    a = MetricValue(metric="dpr", value=10.0, n=5, stderr=0.3, converged=True)
    b = MetricValue(metric="dpr", value=8.0, n=3, stderr=0.4, converged=True)

    delta = paired_delta("dpr", a, [0.1] * 5, b, [0.2] * 3)

    assert delta.paired is False
    assert delta.delta == pytest.approx(2.0)
    assert delta.stderr == pytest.approx(math.sqrt(0.3 ** 2 + 0.4 ** 2))
    assert "unpaired" in delta.note


def test_a_comparison_needs_something_to_compare():
    with pytest.raises(ValueError, match="at least two configs"):
        compare([RunConfig(build="war_angel", level=1, n_days=2, seed=0)])


# ---------------------------------------------------------------------------
# The s44 ex-post additions: resource ledger, damage-type composition, day shape
# ---------------------------------------------------------------------------

def test_the_resource_ledger_is_live_and_excludes_turn_level_action_economy():
    """``record_resource`` now fires at every scheduler ``resources.consume`` site.

    The exclusion matters: action / bonus_action / reaction are scheduler state,
    not ``ResourcePool`` entries, so a "limited resources per day" figure that
    counted them would be reporting "the character took its turns".

    That the recording moved no die is proved by the §12 parity test in
    ``test_eval_framework.py``: ``validation.run_level`` drives this same scheduler,
    so a consumed or reordered roll would break its bit-identical comparison."""
    output = simulate(RunConfig(build="war_angel", level=13, n_days=20, seed=11))
    spent = output.telemetry.resources_spent

    assert spent, "the ledger recorded nothing at all"
    assert not ({"action", "bonus_action", "reaction"} & set(spent))
    assert build_report(output)["limited_resources_per_day"].available is True


def test_spell_slot_metric_counts_the_pact_chassis_too():
    """The War Angel spends ``pact_magic_slot``; keying on the ``spell_slot_``
    prefix alone would report a warlock chassis as casting nothing."""
    report = run(RunConfig(build="war_angel", level=13, n_days=40, seed=11))
    assert report["spell_slots_per_day"].value > 0


def test_damage_type_composition_is_scoped_to_the_characters_own_output():
    """The §13 mitigation channel is keyed ``(actor_id, damage_type)`` precisely so
    a summon's typed damage and a typed-damage enemy's swings cannot pool into the
    build's composition."""
    output = simulate(RunConfig(build="silvertail", level=10, n_days=30, seed=3))
    report = build_report(output)

    character_ids = set(output.roster.ids("characters"))
    everyone = output.telemetry.mitigation_by_type()
    character_only = output.telemetry.mitigation_by_type(character_ids)

    # The channel really does hold more than the character's damage…
    assert sum(c.outgoing_before for c in everyone.values()) >            sum(c.outgoing_before for c in character_only.values())
    # …and the composition shares are computed from the character's slice.
    shares = [report[f"damage_share[{t}]"].value for t in DAMAGE_TYPES]
    assert sum(v for v in shares if v is not None) == pytest.approx(1.0)


def test_typed_damage_share_reports_a_fully_untyped_build_as_zero():
    """A real measurement with a real consequence: the War Angel's output carries no
    damage type in the model, so §5's mult(t) can never price it."""
    report = run(RunConfig(build="war_angel", level=13, n_days=20, seed=11))
    assert report["typed_damage_share"].value == 0.0
    # Every cell of the composition breakdown is unmeasured rather than zero: with
    # no typed output at all the shares' denominator is zero, and "0% radiant" would
    # be a fabricated answer to a question this run cannot answer.
    composition = report.breakdown("damage_share")
    assert composition.measured() == {}
    # s46 dropped typed_damage_per_round: it was exactly dpr × typed_damage_share
    # and nothing read it (§5.4's survival rule).
    assert "typed_damage_per_round" not in METRICS


def test_per_combat_dpr_partitions_the_headline_exactly():
    """The four per-combat figures are the headline decomposed, not a different
    quantity: equal round counts, so their mean IS the day's DPR.  This is what
    catches a per-combat metric that quietly reads an all-sources log."""
    report = run(RunConfig(build="war_angel", level=13, n_days=60, seed=11))
    per_combat = [report[f"dpr_by_combat[{i}]"].value for i in (1, 2, 3, 4)]

    assert sum(per_combat) / 4 == pytest.approx(report.headline.value)


def test_per_combat_dpr_exposes_a_depletion_curve_the_daily_mean_hides():
    """Mechanism, not value: the four numbers are allowed to differ from each other
    and from the day mean.  A build that spends its day early is invisible at the
    day level, which is the reason these are registered."""
    report = run(RunConfig(build="war_angel", level=13, n_days=60, seed=11))
    per_combat = [report[f"dpr_by_combat[{i}]"].value for i in (1, 2, 3, 4)]

    assert len(set(per_combat)) > 1
    assert min(per_combat) < report.headline.value < max(per_combat)


def test_the_opening_round_metric_is_labelled_party_scoped():
    """The per-round log is keyed by target only, so round-1 damage cannot be
    attributed to a source.  Rather than silently mixing a summon into a
    character metric, it is named and grouped as a party column (§3.3)."""
    assert "party_dpr_opening_round" in METRICS
    assert METRICS["party_dpr_opening_round"].group == "column"
    assert "PARTY-scoped" in METRICS["party_dpr_opening_round"].definition


# ---------------------------------------------------------------------------
# Summon attribution (§3.3 as amended s44) — a declared axis, not a hidden rule
# ---------------------------------------------------------------------------

def test_the_default_attribution_is_the_historical_character_only_basis():
    """No existing baseline moves: the toggle is opt-in."""
    assert RunConfig(build="silvertail", level=10).attribution == "character"


def test_attributing_summons_moves_the_headline_and_nothing_else():
    """The toggle changes WHICH number is the headline, never which numbers exist:
    the summon and party columns are registered and identical under both modes."""
    base = RunConfig(build="silvertail", level=10, n_days=40, seed=3)
    character = run(base)
    with_summons = run(base.replace(attribution="character_and_summons"))

    assert with_summons.headline.value == pytest.approx(
        character.headline.value + character["dpr_by_role[summons]"].value)
    assert with_summons["dpr_by_role[summons]"].value == character["dpr_by_role[summons]"].value
    assert with_summons["dpr_by_role[*]"].value == character["dpr_by_role[*]"].value


def test_the_per_combat_decomposition_follows_the_attribution():
    """One definition of "the build's output", read by every metric that means it —
    so the headline and its decomposition cannot disagree about whose damage they
    describe."""
    report = run(RunConfig(build="silvertail", level=10, n_days=40, seed=3,
                           attribution="character_and_summons"))
    per_combat = [report[f"dpr_by_combat[{i}]"].value for i in (1, 2, 3, 4)]

    assert sum(per_combat) / 4 == pytest.approx(report.headline.value)


def test_allies_are_excluded_under_both_attributions():
    """An ally is a party member the build does not COMMAND, so its damage was never
    the build's to claim — unlike a summon, which is what the build's action economy
    bought."""
    base = RunConfig(build="starfire_scion", level=15, n_days=20, seed=1,
                     build_options={"with_party": True})
    for attribution in ("character", "character_and_summons"):
        report = run(base.replace(attribution=attribution))
        ally = report["dpr_by_role[allies]"]
        assert ally.available is True
        assert report.headline.value == pytest.approx(
            report["dpr_by_role[*]"].value - ally.value)


def test_a_build_without_summons_is_unaffected_by_the_attribution():
    base = RunConfig(build="war_angel", level=13, n_days=20, seed=11)
    assert run(base).headline.value ==         run(base.replace(attribution="character_and_summons")).headline.value


def test_an_unknown_attribution_is_rejected():
    with pytest.raises(ValueError, match="attribution must be one of"):
        RunConfig(build="silvertail", level=10, attribution="everything_nearby")


def test_the_attribution_is_recorded_in_provenance_and_in_the_config_hash():
    """§5.2's rule: it changes what the headline MEANS, so two modes must never be
    compared silently, and they must not collide as cache keys."""
    base = RunConfig(build="silvertail", level=10, n_days=4, seed=3)
    other = base.replace(attribution="character_and_summons")

    provenance = run(other).provenance
    assert provenance.config["attribution"] == "character_and_summons"
    assert provenance.coverage["attributed_roles"] == ["characters", "summons"]
    assert "attribution" in provenance.coverage["comparability_warning"]
    assert base.config_hash() != other.config_hash()


# ---------------------------------------------------------------------------
# §5.4's output kinds, exercised on the mechanism rather than on any value
# ---------------------------------------------------------------------------

def test_a_breakdown_cell_can_be_unavailable_while_its_siblings_report():
    """PER-CELL availability is the property that let the saves family collapse.

    The flat registry needed ``control_save_fail_rate`` as its own row purely so it
    could carry its own "unmeasurable until the §13 step-5 enemy seam" reason. Under
    §5.4 the reason rides on the CELL, so one breakdown holds a measurable damage
    channel and an unmeasurable control channel at the same time.
    """
    report = run(RunConfig(build="silvertail", level=10, n_days=40, seed=11,
                           build_options=ZONE))
    rates = report.breakdown("save_fail_rate")

    damage_side = rates[(ALL, "damage")]
    control_side = rates[(ALL, "control")]
    assert damage_side.available is True
    assert control_side.available is False
    assert "control" in control_side.note
    # …and the two live under one declaration, not two.
    assert rates.name == "save_fail_rate"


def test_the_key_travels_as_data_so_nothing_downstream_parses_a_metric_name():
    """§5.4's decisive argument. ``damage_share_acid`` forced every consumer to
    parse the key back out of the name; the tidy rows carry it as a column."""
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11))
    rows = report.breakdown("healing_by_source").rows()

    assert rows, "a breakdown with a closed key space always has rows"
    for row in rows:
        assert set(row) >= {"breakdown", "source_role", "context", "is_margin",
                            "value", "stderr", "n", "converged"}
        assert row["source_role"] in ATTRIBUTABLE_ROLES + (ALL,)
        assert row["context"] in HEAL_CONTEXTS
    assert any(row["is_margin"] for row in rows)
    assert any(not row["is_margin"] for row in rows)


def test_a_breakdowns_margins_are_kept_apart_from_its_cells():
    """A consumer must never sum cells and margins together: the margins ARE the
    sums.  Keeping them in separate maps makes the mistake unavailable."""
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11))
    dpr_by_role = report.breakdown("dpr_by_role")

    assert set(dpr_by_role.cells) == {("characters",), ("summons",), ("allies",)}
    assert set(dpr_by_role.margins) == {(ALL,)}
    assert dpr_by_role.total() is dpr_by_role[(ALL,)]
    assert dpr_by_role.total().value == pytest.approx(
        dpr_by_role["characters"].value + dpr_by_role["summons"].value)


def test_is_margin_is_where_the_estimate_LIVES_not_whether_its_key_holds_a_star():
    """Regression (found s47, building §9's CSV renderer).

    An UNCROSSED breakdown materializes marginal PROFILES as its cells, so an
    ordinary cell key holds ``ALL`` in the collapsed positions —
    ``saves_forced_per_round[dex_save|*]`` is a cell, not a margin.  ``rows()``
    originally flagged ``is_margin`` as ``ALL in key``, which labelled all 8 cells of
    both uncrossed breakdowns as margins and left ONE unflagged row nowhere.  That
    inverts the only filter a consumer has for keeping the two apart: selecting
    ``is_margin == FALSE`` to get the cells returned an empty set, and selecting
    ``TRUE`` returned cells and the total mixed together — which is precisely the
    double-count the flag exists to prevent.
    """
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11,
                           build_options=ZONE))
    saves = report.breakdown("saves_forced_per_round")
    assert saves.definition.crossed is False

    rows = {tuple(row[d] for d in saves.dimensions): row for row in saves.rows()}
    # Every cell key carries a star, and NOT ONE of them is a margin.
    assert all(ALL in key for key in saves.cells)
    assert all(rows[key]["is_margin"] is False for key in saves.cells)
    # The single declared margin is the only flagged row.
    assert [key for key, row in rows.items() if row["is_margin"]] == [(ALL, ALL)]


# ---------------------------------------------------------------------------
# Healing (design/healing.md §8) — the first customer of the output kinds
# ---------------------------------------------------------------------------

def test_healing_by_source_separates_the_summons_healing_from_the_characters():
    """The per-METRIC ritual's roster-scoping check, on the only build with a summon.

    Silvertail's beast heals ITSELF from its own Hit Dice (healing.md §7 b2). That
    healing must land in the ``summons`` cell and nowhere else — a metric built on
    an aggregate ledger would pool it with the character's.
    """
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11))
    healing = report.breakdown("healing_by_source")

    assert healing[("characters", "between")].value > 0
    assert healing[("summons", "between")].value > 0
    assert healing[("characters", "between")].value != \
        healing[("summons", "between")].value
    # The party margin is the sum; the cells are not each other.
    assert healing[(ALL, "between")].value == pytest.approx(
        healing[("characters", "between")].value
        + healing[("summons", "between")].value)


def test_a_build_with_no_summon_reports_the_summon_cell_as_unavailable():
    """The other half of the same check: a build the summon column does not exist
    for says so, rather than reporting a zero that reads as 'heals nothing'."""
    report = run(RunConfig(build="war_angel", level=13, n_days=10, seed=11))
    cell = report.breakdown("healing_by_source")[("summons", "between")]
    assert cell.available is False
    assert "summons" in cell.note


def test_healing_by_source_refuses_to_pool_the_two_contexts():
    """healing.md §11.1: the corpus does most of its healing OUT of combat by
    preference, so healing under fire is a different quantity from healing at
    leisure.  §5.4 enforces that by SHAPE — the breakdown declares no margin over
    ``context``, so no cell in the artifact ever sums them.  A comment can be
    ignored; a cell that does not exist cannot."""
    healing = METRICS.breakdown("healing_by_source")

    assert healing.key_space.names == ("source_role", "context")
    # Collapsing the source role IS declared…
    assert all(ALL not in key[1:] for key in healing.margin_keys())
    assert (ALL, "combat") in healing.margin_keys()
    # …and the fully-collapsed total, which would pool the contexts, is refused.
    assert (ALL, ALL) not in healing.margin_keys()
    assert "context" in healing.margin_note
    report = run(RunConfig(build="silvertail", level=10, n_days=10, seed=11))
    assert report.breakdown("healing_by_source").total() is None


def test_net_damage_taken_may_go_negative_and_says_so():
    """healing.md §8: a negative value is not an error, it is surplus healing
    capacity — the quantity §2 exists to measure.  Silvertail's default policy is
    the live case: the beast draws the enemy, so the character takes nothing and
    still heals its Hit Dice."""
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11))
    net = report["net_damage_taken_per_round"]

    assert net.value < 0
    assert "NEGATIVE" in METRICS["net_damage_taken_per_round"].definition
    assert "surplus" in METRICS["net_damage_taken_per_round"].definition


def test_net_damage_taken_is_character_scoped_and_ignores_the_summons_healing():
    """The roster-scoping check applied to a SCALAR, which is where s44 found the
    bug three times.  The beast's self-healing appears in its own breakdown cell and
    must not discount the character's cost."""
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11))
    healing = report.breakdown("healing_by_source")
    taken = report.breakdown("damage_taken_per_round_by_role")
    rounds = RunConfig(build="silvertail", level=10).rounds_per_day

    character_only = (taken["characters"].value
                      - healing[("characters", "between")].value / rounds)
    pooled = (taken["characters"].value
              - healing[(ALL, "between")].value / rounds)

    assert report["net_damage_taken_per_round"].value == pytest.approx(character_only)
    assert report["net_damage_taken_per_round"].value != pytest.approx(pooled)


def test_external_healing_required_is_clamped_and_never_negative():
    """The clamp is PER DAY, so the metric is the mean of the clamped quantity and
    not the clamp of the mean.  Silvertail is the case that shows the clamp firing:
    the character heals more than it takes, and the answer is 0 rather than the
    negative surplus that net_damage_taken_per_round reports."""
    report = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11))
    assert report["net_damage_taken_per_round"].value < 0        # surplus…
    assert report["external_healing_required_per_day"].value == 0.0  # …clamped

    # And where damage genuinely exceeds self-healing, it is the shortfall.
    under_fire = run(RunConfig(build="silvertail", level=10, n_days=20, seed=11,
                               build_options=ZONE))
    taken = under_fire.breakdown("damage_taken_per_round_by_role")["characters"].value
    healed = under_fire.breakdown("healing_by_source")[("characters", "between")].value
    rounds = RunConfig(build="silvertail", level=10).rounds_per_day
    assert under_fire["external_healing_required_per_day"].value == pytest.approx(
        taken * rounds - healed)


def test_a_build_that_reserves_its_hit_dice_needs_its_full_damage_healed():
    """The metric doing healing.md §2's job. The Starfire Scion spends its Hit Dice
    on Fueled Spellfire (``available_for_healing=False``), so it heals NOTHING and a
    party healer must cover every point it takes."""
    report = run(RunConfig(build="starfire_scion", level=15, n_days=20, seed=11))
    rounds = RunConfig(build="starfire_scion", level=15).rounds_per_day
    taken = report.breakdown("damage_taken_per_round_by_role")["characters"].value

    assert report.breakdown("healing_by_source").measured() != {}   # channel works…
    assert all(v.value == 0.0                                       # …and is empty
               for v in report.breakdown("healing_by_source").measured().values())
    assert report["net_damage_taken_per_round"].value == pytest.approx(taken)
    assert report["external_healing_required_per_day"].value == pytest.approx(
        taken * rounds)


def test_healing_provided_to_others_is_unavailable_where_there_is_no_other():
    """A 0 here would report ROSTER POVERTY as a build property. War Angel's Prayer
    of Healing heals five creatures RAW and heals one in this model only because the
    roster HAS one — so the availability predicate keeps the modelling limit visible
    instead of scoring the build as selfish."""
    alone = run(RunConfig(build="war_angel", level=13, n_days=10, seed=11))
    provided = alone["healing_provided_to_others_per_day"]
    assert provided.available is False
    assert "roster" in provided.note.lower()

    # Silvertail HAS another entity, so the same zero is a real measurement: the
    # character could heal the beast and does not.
    with_summon = run(RunConfig(build="silvertail", level=10, n_days=10, seed=11))
    measured = with_summon["healing_provided_to_others_per_day"]
    assert measured.available is True
    assert measured.value == 0.0


def test_healing_provided_follows_the_attribution_axis():
    """§14 point 3: a summon's healing counts as the build's under
    'character_and_summons' — and at the same moment the summon stops being
    "others", so there is nobody left to provide to."""
    character = RunConfig(build="silvertail", level=10, n_days=10, seed=11)
    with_summons = RunConfig(build="silvertail", level=10, n_days=10, seed=11,
                             attribution="character_and_summons")

    assert run(character)["healing_provided_to_others_per_day"].available is True
    assert run(with_summons)["healing_provided_to_others_per_day"].available is False
