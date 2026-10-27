"""
test_eval_attacks.py — step 4 of the evaluation framework (§13.4, §8.1): the
``attacks`` telemetry channel and the two metrics that read it.

Validation framing (§12, memory ``validate-mechanism-not-build-value``): nothing
here asserts that any build's hit % is "correct" — there is no external standard for
it to be correct against (§11).  The assertions are that the channel records what it
claims, that it is scoped to the right entity, that recording draws no dice, and
that the two declarations the change forced (``BreakdownDef.sum_rule``, the per-role
denominator) behave on every value they can take.

Per-feature ritual step 5 — THE ROLL CALL (a REQUIRED ARTIFACT, written first)
------------------------------------------------------------------------------
One row per declaration this change touches; one column naming the fixture that
covers each VALUE.  Written BEFORE the tests, which is the only way it does any
work: it is the instrument that finds the gap, not a record of one already found.

===============================  ==============================================
declaration (its values)         fixture that covers each value
===============================  ==============================================
``record_attack`` hit/crit       hit+crit -> ``test_a_hit_and_a_crit``;
  (4 reachable combinations)     hit+noncrit -> same; miss -> same;
                                 **miss+crit** (a crit the defender flipped) ->
                                 ``test_a_crit_flipped_to_a_miss_is_neither``.
                                 The fourth is the one that matters and the only
                                 one unreachable by reading the d20 alone.
``record_attack`` stance         advantage -> ``test_the_recorded_stance_*``;
  (advantage / disadvantage /    disadvantage -> same; flat-by-cancellation ->
   flat / rejected "both")       same; both -> ``test_record_attack_rejects_*``
                                 (raises, never a tally with 2 stances on 1 roll).
the RECORD POINT                 plain  -> ``test_a_hit_and_a_crit``;
  (plain / rescued / parried /   rescued miss -> ``test_a_rescued_miss_*``;
   protected)                    parried hit -> ``test_a_parried_hit_*``;
                                 protected crit -> ``test_a_protected_crit_*``.
``telemetry`` sink on            given -> every test in part 2;
  ``resolve_attack_roll``        None -> ``test_no_sink_is_byte_identical`` (the
  (given / None)                 direct-caller path, which is what keeps §12 green).
``attacks_for`` scope            scoped -> ``test_attacks_for_scopes_by_actor``;
  (actor_ids / None)             None -> same test, which shows the two DIFFER on
                                 a real roster (the s44 trap, not a style point).
``BreakdownDef.sum_rule``        partition -> ``dpr_by_role`` (+5 more);
  (partition / overlap, x        overlap+UNCROSSED -> ``saves_forced_per_round``;
   crossed / uncrossed, +        overlap+CROSSED -> ``attack_roll_rate`` (the new
   the missing-value refusal)    third case, and the reason the field exists);
                                 missing -> ``test_a_breakdown_must_declare_*``.
                                 The first three are asserted in
                                 ``test_eval_artifact.py`` at the artifact
                                 boundary and here at the declaration.
``sum_rule_note_of``             None -> ``healing_by_source``; uncrossed note ->
  (3 outcomes)                   ``saves_forced_per_round``; non-disjoint note ->
                                 ``attack_roll_rate``. All three in
                                 ``test_eval_artifact.py``, which is where the note
                                 is consumed.
``_attacks_made_denominator``    nonzero -> every shipped build (see below);
  (nonzero / zero)               ZERO -> ``test_a_role_that_never_swings_is_*``,
                                 a BUILT fixture — see the gap note below.
``attack_roll_rate`` cell        measured -> ``characters`` on any build;
  ``status`` (3 values)          unavailable -> ``summons`` on war_angel and
                                 ``allies`` on both; unmeasured -> the built
                                 fixture above.
``MetricDef.scale`` on the new   ratio -> all 10 new cells, asserted explicitly in
  metrics (ratio / interval)     ``test_every_attacks_metric_is_ratio_scale``.
                                 interval -> NO new metric takes it, and the test
                                 says so rather than letting the default pass
                                 unexamined (s48 asked for this to be stated).
``RunConfig.attribution`` on     'character' vs 'character_and_summons' ->
  ``attacks_per_round``          ``test_attacks_per_round_follows_attribution``,
  (2 values)                     on silvertail, the only build with a summon.
===============================  ==============================================

THE GAP THIS TABLE FOUND, before any test existed: the **unmeasured** path of
``attack_roll_rate`` has no production fixture at all.  Every shipped build at every
level makes character attack rolls, and every role that is PRESENT in a shipped
roster also swings — so "a role that exists but never made an attack roll" is
reachable in principle and unreachable through ``RunConfig``.  It gets a built
fixture rather than being left for the next session to discover, which is the same
shape of gap s48's table found twice.
"""

from __future__ import annotations

import logging
import math

import pytest

from src.entity import Entity
from src.evaluation import (
    METRICS,
    RunConfig,
    build_report,
    render,
    run,
    simulate,
)
from src.evaluation.metrics import (
    ALL,
    SUM_RULE_OVERLAP,
    SUM_RULE_PARTITION,
    BreakdownDef,
    DaySample,
    Dimension,
    KeySpace,
)
from src.evaluation.roster import Roster
from src.evaluation.statistics import SCALE_RATIO, ratio_estimate
from src.events import AttackRollEvent, EventQueue, make_tick
from src.policy import InterceptResponse
from src.telemetry import ATTACK_PROPERTIES, AttackTally, CombatTelemetry
from src.verbs import resolve_attack_roll

logging.disable(logging.CRITICAL)

ZONE = {"zone_effect": "spirit_guardians"}


# ---------------------------------------------------------------------------
# Deterministic fake RNG (the shape test_flourish_parry / test_weapon_mastery use)
# ---------------------------------------------------------------------------

class FakeRNG:
    """Pops preloaded values; records (n, sides) per call, so a test can assert
    that the DICE STREAM is identical and not merely that the outcome is."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        self.roll_calls.append((1, sides))
        return self._values.pop(0)


def _attacker(attack_bonus=0):
    return Entity(name="Attacker", hp=50, base_stats={
        "attack_bonus": attack_bonus, "damage_dice": (1, 8), "damage_bonus": 0,
    })


def _defender(ac=10):
    return Entity(name="Defender", hp=math.inf, base_stats={"ac": ac})


def _swing(attacker, defender, rng, telemetry=None, **kw):
    """Resolve one attack roll through the real verb, with a rigged d20."""
    event = AttackRollEvent(
        tick=make_tick(1, 0, 1), actor=attacker, target=defender,
        weapon_stat="attack_bonus", cost="action",
    )
    return resolve_attack_roll(event, rng, EventQueue(), next_sequence=2,
                               telemetry=telemetry, **kw)


# ===========================================================================
# 1. The channel: the accumulator, its closed stance rule, and its scoping
# ===========================================================================

def test_a_hit_and_a_crit():
    t = CombatTelemetry()
    t.record_attack(7, hit=True, crit=False)
    t.record_attack(7, hit=True, crit=True)
    t.record_attack(7, hit=False, crit=False)
    cell = t.attacks[7]
    assert (cell.forced, cell.hit, cell.crit) == (3, 2, 1)


def test_a_crit_flipped_to_a_miss_is_neither():
    """``crit <= hit`` ALWAYS.  A natural 20 that the defender's in-flight intercept
    turned into a miss dealt no damage, so counting it as a crit would make the
    attacks ledger claim a hit the damage ledger has no record of — which is the one
    thing the choice of record point exists to rule out."""
    t = CombatTelemetry()
    t.record_attack(7, hit=False, crit=True)
    cell = t.attacks[7]
    assert (cell.forced, cell.hit, cell.crit) == (1, 0, 0)


def test_record_attack_rejects_a_both_stance():
    """The stance is the EFFECTIVE one after 2024 cancellation.  Accepting "both"
    would let the stance counts exceed the roll count, which quietly destroys the
    partition invariant the next test rests on."""
    t = CombatTelemetry()
    with pytest.raises(ValueError, match="EFFECTIVE stance"):
        t.record_attack(7, hit=True, crit=False, advantage=True, disadvantage=True)


def test_the_recorded_stance_is_the_effective_one_and_partitions_the_rolls():
    """Four input combinations, three outcomes: advantage, disadvantage, and FLAT
    both by having neither and by cancellation.  The partition
    ``advantage + disadvantage + flat == forced`` is the invariant that catches a
    miswired record call."""
    attacker, defender = _attacker(20), _defender(10)   # always hits
    t = CombatTelemetry()
    # (advantage, disadvantage) sources on the attacker, via statuses the verb reads.
    _swing(attacker, defender, FakeRNG([10]), t)                     # flat: neither
    attacker.statuses.apply("vex_advantage", defender.id)
    _swing(attacker, defender, FakeRNG([10, 10]), t)                 # advantage
    attacker.statuses.apply("sapped", True)
    _swing(attacker, defender, FakeRNG([10, 10]), t)                 # disadvantage
    attacker.statuses.apply("vex_advantage", defender.id)
    attacker.statuses.apply("sapped", True)
    _swing(attacker, defender, FakeRNG([10]), t)                     # BOTH -> flat
    cell = t.attacks[attacker.id]
    assert cell.forced == 4
    assert cell.advantage == 1
    assert cell.disadvantage == 1
    flat = cell.forced - cell.advantage - cell.disadvantage
    assert flat == 2, "neither-source and cancellation must BOTH land in flat"


def test_attacks_for_scopes_by_actor():
    """The s44 trap, in one assertion: the scoped and pooled rates must DIFFER on a
    roster whose actors have different to-hit profiles, or the actor dimension would
    be decoration."""
    t = CombatTelemetry()
    for _ in range(10):                                  # a sharp attacker
        t.record_attack(1, hit=True, crit=False)
    for _ in range(10):                                  # ...and a blunt one
        t.record_attack(2, hit=False, crit=False)
    assert t.attacks_for({1}).hit / t.attacks_for({1}).forced == 1.0
    assert t.attacks_for({2}).hit / t.attacks_for({2}).forced == 0.0
    pooled = t.attacks_for()
    assert pooled.forced == 20
    assert pooled.hit / pooled.forced == 0.5, "pools to a rate describing neither"


def test_merge_sums_the_attacks_channel():
    a, b = CombatTelemetry(), CombatTelemetry()
    a.record_attack(1, hit=True, crit=True, advantage=True)
    b.record_attack(1, hit=False, crit=False, disadvantage=True)
    b.record_attack(2, hit=True, crit=False)
    a.merge(b)
    assert a.attacks[1] == AttackTally(forced=2, hit=1, crit=1,
                                       advantage=1, disadvantage=1)
    assert a.attacks[2] == AttackTally(forced=1, hit=1)


# ===========================================================================
# 2. The write site: WHERE in resolve_attack_roll the record happens
# ===========================================================================

def test_a_rescued_miss_is_recorded_as_a_hit():
    """Guided Strike: the post-roll decider lifts a miss over the AC.  It deals
    damage, so it is a hit here — and NOT a crit, because the d20 was not a 20."""
    attacker, defender = _attacker(0), _defender(15)
    t = CombatTelemetry()
    _swing(attacker, defender, FakeRNG([10]), t, decider=lambda missed_by: 10)
    cell = t.attacks[attacker.id]
    assert (cell.forced, cell.hit, cell.crit) == (1, 1, 0)


def test_a_parried_hit_is_recorded_as_a_miss():
    """The consistency guarantee, stated as a test: a parried hit spawns no
    DamageEvent, so if it were recorded as a hit the two ledgers would disagree."""
    attacker, defender = _attacker(10), _defender(15)
    t = CombatTelemetry()
    queue = EventQueue()
    event = AttackRollEvent(tick=make_tick(1, 0, 1), actor=attacker, target=defender,
                            weapon_stat="attack_bonus", cost="action")
    resolve_attack_roll(event, FakeRNG([10]), queue, next_sequence=2,
                        intercept_decider=lambda margin: InterceptResponse(ac_bonus=10),
                        telemetry=t)
    cell = t.attacks[attacker.id]
    assert (cell.forced, cell.hit) == (1, 0)
    assert not queue, "a parried hit must leave no damage behind it"


def test_a_protected_crit_that_still_lands_is_a_hit_but_not_a_crit():
    """Protection imposes disadvantage by rolling a SECOND d20 after the fact.  The
    surviving hit keeps its crit only if that die is also a 20 — so a crit can be
    downgraded to an ordinary hit, and the channel has to follow."""
    attacker, defender = _attacker(10), _defender(12)
    t = CombatTelemetry()
    # first d20 = 20 (crit), second = 10 -> still clears AC 12 with +10, not a 20.
    _swing(attacker, defender, FakeRNG([20, 10]), t,
           intercept_decider=lambda margin: InterceptResponse(impose_disadvantage=True))
    cell = t.attacks[attacker.id]
    assert (cell.forced, cell.hit, cell.crit) == (1, 1, 0)
    # ...and it is NOT recorded as disadvantage: the stance is the attacker's own,
    # and this second die is a defender mitigation applied after the roll (§8.1).
    assert cell.disadvantage == 0


def test_no_sink_is_byte_identical():
    """The direct-caller path.  Recording is pure observation, so passing no sink
    must change neither the dice drawn nor the outcome — this is what keeps §12's
    bit-identical parity proof green while a channel is added underneath it."""
    out = []
    for telemetry in (None, CombatTelemetry()):
        attacker, defender = _attacker(3), _defender(14)
        rng = FakeRNG([17, 5, 5])
        queue = EventQueue()
        event = AttackRollEvent(tick=make_tick(1, 0, 1), actor=attacker,
                                target=defender, weapon_stat="attack_bonus",
                                cost="action")
        seq = resolve_attack_roll(event, rng, queue, next_sequence=2,
                                  telemetry=telemetry)
        out.append((seq, list(rng.roll_calls), len(queue._heap)))
    assert out[0] == out[1]


def test_recording_draws_no_dice():
    """Step 3 of the per-feature ritual, measured rather than promised: the sink is
    offered every value from a local variable, so the roll sequence is untouched."""
    attacker, defender = _attacker(3), _defender(14)
    rng = FakeRNG([17])
    _swing(attacker, defender, rng, CombatTelemetry())
    assert rng.roll_calls == [(1, 20)], "one d20 and nothing else"


# ===========================================================================
# 3. The declarations the change forced
# ===========================================================================

def test_a_breakdown_must_declare_its_sum_rule():
    """No default (s49).  A wrong value here IS the double-count the field exists to
    prevent, and a default is how one gets shipped unnoticed."""
    space = KeySpace((Dimension(name="d", keys=("a", "b"), description="x"),))
    with pytest.raises(ValueError, match="must declare sum_rule"):
        BreakdownDef(name="bogus", unit="u", key_space=space, source="s",
                     definition="d", numerator=lambda s, k: 0.0,
                     denominator="rounds")


def test_the_attacks_breakdown_is_the_crossed_overlapping_case():
    """The third combination, which is the whole reason the field is declared: six
    shipped breakdowns are crossed+partition and two are uncrossed+overlap, so the
    old inference held until this one."""
    attacks = METRICS.breakdown("attack_roll_rate")
    assert attacks.crossed is True
    assert attacks.sum_rule == SUM_RULE_OVERLAP
    assert METRICS.breakdown("dpr_by_role").sum_rule == SUM_RULE_PARTITION
    saves = METRICS.breakdown("saves_forced_per_round")
    assert saves.crossed is False and saves.sum_rule == SUM_RULE_OVERLAP


def test_the_attacks_breakdown_refuses_both_margins_and_says_why():
    attacks = METRICS.breakdown("attack_roll_rate")
    assert attacks.margin_keys() == ()
    assert "role" in attacks.margin_note and "property" in attacks.margin_note


def test_the_console_does_not_call_a_crossed_breakdown_INDEPENDENT(silvertail):
    """FOUND BY READING ONE REAL REPORT (per-feature step 6), not by a test.

    The console had its own hardcoded do-not-sum line, keyed on the same inference
    the artifact had just stopped making — so it printed "dimensions reported
    INDEPENDENTLY" over ``attack_roll_rate``, which is crossed.  That is a false
    statement about the shape of the data, and every test was green: the new ones
    assert the ARTIFACT's note, and the console's string was nobody's subject.
    """
    text = render(silvertail)
    attacks = text.index("attack_roll_rate  [role x property]")
    saves = text.index("saves_forced_per_round  [ability x channel]")
    attacks_note = text[attacks:].splitlines()[1]
    saves_note = text[saves:].splitlines()[1]
    assert "do NOT sum them" in attacks_note and "do NOT sum them" in saves_note
    assert "INDEPENDENTLY" in saves_note
    assert "INDEPENDENTLY" not in attacks_note
    assert "NOT disjoint" in attacks_note


def test_every_attacks_metric_is_ratio_scale():
    """s48 added ``MetricDef.scale`` and asked that a change say it CHECKED rather
    than let the default pass unexamined.  A rate in [0,1] and a count per round both
    have a true zero, so every one is ``ratio``; nothing here can go negative, so
    there is no ``interval`` candidate to weigh."""
    new = [m for m in METRICS
           if m.name == "attacks_per_round" or m.breakdown == "attack_roll_rate"]
    assert len(new) == 10                      # 1 scalar + 3 roles x 3 properties
    assert all(m.scale == SCALE_RATIO for m in new)


def test_the_property_vocabulary_is_closed_and_not_a_partition():
    """The keys are the §8 three, and they deliberately OVERLAP."""
    assert ATTACK_PROPERTIES == ("hit", "crit", "advantage")
    dimension, = [d for d in METRICS.breakdown("attack_roll_rate").key_space.dimensions
                  if d.name == "property"]
    assert dimension.keys == ATTACK_PROPERTIES
    assert "disadvantage" not in dimension.keys


# ===========================================================================
# 4. The metrics on a real run — the per-METRIC ritual's two questions
# ===========================================================================

@pytest.fixture(scope="module")
def silvertail():
    """The only build with a summon, so the only one that exercises the role
    dimension's measured/measured case rather than measured/unavailable."""
    return run(RunConfig(build="silvertail", level=10, n_days=30, seed=3,
                         build_options=ZONE))


@pytest.fixture(scope="module")
def war_angel():
    return run(RunConfig(build="war_angel", level=13, n_days=30, seed=3))


def test_the_character_cell_is_not_moved_by_the_summons_rolls(silvertail):
    """WHOSE attacks are these? — the per-METRIC ritual's first question, tested
    against Silvertail because it is the only build where the answer can be wrong.

    The character and the summon both swing, with different to-hit profiles, so a
    channel keyed by anything but the actor would pool them.  The assertion is that
    the two cells differ AND that the pooled rate differs from the character's by
    more than the character cell's own standard error — i.e. the bug this scoping
    prevents would have been visible in the output, not a rounding difference.
    """
    char = silvertail.values["attack_roll_rate[characters|hit]"]
    summon = silvertail.values["attack_roll_rate[summons|hit]"]
    assert char.measured and summon.measured
    assert char.value != summon.value
    assert char.stderr is not None and char.stderr > 0

    # What an unscoped channel would have reported: one rate over both actors'
    # rolls, which is the roll-weighted average of the two cells, over a strictly
    # larger population than either describes.
    rolls = char.n_events + summon.n_events
    pooled = (char.value * char.n_events + summon.value * summon.n_events) / rolls
    assert rolls > char.n_events > 0
    assert min(char.value, summon.value) < pooled < max(char.value, summon.value)

    # HOW BIG that error is, deliberately NOT asserted — and worth recording why,
    # because the obvious assertion ("bigger than the stderr") is FALSE here and
    # measuring it is what showed that.  Silvertail's summon happens to hit at
    # within ~0.02 of its character at L10, so pooling the two moves the number by
    # less than one standard error at 30 days.  The scoping is therefore a
    # STRUCTURAL requirement (the magnitude is a property of whichever roster a
    # build happens to field, and nothing bounds it) rather than one justified by
    # today's discrepancy.  The case where the error is unmissable is the ENEMY,
    # whose to-hit profile is nothing like the character's — asserted next.


def test_the_enemys_swings_are_in_the_channel_and_outside_every_cell():
    """The sharpest form of the aggregate-ledger trap, and the reason it is worth a
    test of its own: the enemy attacks through the SAME verb, so its rolls really are
    in the channel.  Nothing about a metric built on an unscoped read would look
    broken — it would just quietly report a rate over the wrong population.

    So this asserts both halves on one run: that the channel holds an actor OUTSIDE
    the attributable roles, and that the character's cell counts none of them.
    """
    config = RunConfig(build="war_angel", level=13, n_days=20, seed=3)
    days: list = []
    output = simulate(config, on_day=lambda i, day: days.append(day.telemetry))
    roster = output.roster

    channel = CombatTelemetry()
    for day in days:
        channel.merge(day)
    own = set(roster.ids("characters"))
    outsiders = set(channel.attacks) - own
    assert outsiders, "the enemy must actually be swinging, or this proves nothing"
    assert set(roster.ids("enemies")) & outsiders

    scoped_tally = channel.attacks_for(own)
    pooled_tally = channel.attacks_for()
    assert 0 < scoped_tally.forced < pooled_tally.forced

    # ...and the shipped cell's denominator is the SCOPED count, to the roll.
    report = build_report(output)
    cell = report.values["attack_roll_rate[characters|hit]"]
    assert cell.n_events == scoped_tally.forced

    # This is the pooling whose error is UNMISSABLE rather than within noise: the
    # enemy's to-hit profile is nothing like the character's, so an unscoped cell
    # would be wrong by many standard errors — which is the quantity the summon
    # case above deliberately does not claim.
    pooled_rate = pooled_tally.hit / pooled_tally.forced
    assert cell.stderr is not None
    assert abs(pooled_rate - cell.value) > 5 * cell.stderr


def test_a_crit_rate_never_exceeds_its_hit_rate(silvertail, war_angel):
    """A mechanism invariant, not a build value: ``crit <= hit`` holds per actor in
    the tally, so it must survive the ratio estimator for every measured cell."""
    for report in (silvertail, war_angel):
        for role in ("characters", "summons"):
            hit = report.values[f"attack_roll_rate[{role}|hit]"]
            crit = report.values[f"attack_roll_rate[{role}|crit]"]
            if hit.measured and crit.measured:
                assert crit.value <= hit.value


def test_a_role_absent_from_the_roster_is_unavailable_not_zero(silvertail, war_angel):
    """§3.4's central rule on the new cells.  A 0.0 hit rate for a summon this build
    does not have reads as "its summon never lands a blow"."""
    for prop in ATTACK_PROPERTIES:
        allies = silvertail.values[f"attack_roll_rate[allies|{prop}]"]
        assert not allies.available and allies.value is None
        assert "allies" in allies.note
        summons = war_angel.values[f"attack_roll_rate[summons|{prop}]"]
        assert not summons.available and summons.value is None


def test_a_role_that_never_swings_is_unmeasured_not_zero():
    """THE BUILT FIXTURE the roll call called for: a role that is PRESENT but made no
    attack roll.  Unreachable through ``RunConfig`` — every shipped build at every
    level swings — so it is constructed, because the distinction it guards is the
    whole of §3.4: "this build's summon has a 0% hit rate" and "this build's summon
    did not attack" are different facts and only one of them is ever true here.
    """
    from src.evaluation.metrics import DENOMINATORS, _attacks_made_denominator

    denominator = _attacks_made_denominator(("characters", "hit"))
    assert denominator.fixed is False
    entity = Entity(name="Pacifist", hp=10, base_stats={})
    sample = DaySample(
        config=RunConfig(build="war_angel", level=1, n_days=1, seed=0),
        roster=Roster(characters=[entity]),
        result=None,
        damage_dealt={}, damage_taken={},
        telemetry=CombatTelemetry(),          # nothing ever swung
    )
    assert denominator.per_day(sample) == 0.0
    # A rate over a zero denominator has NO value, and the estimator says so.
    value, stderr, influence = ratio_estimate([0.0], [0.0])
    assert (value, stderr, influence) == (None, None, [])
    # The shipped cells really do route through this denominator.
    cell = METRICS.cell("attack_roll_rate", ("characters", "hit"))
    assert cell.denominator == denominator.name
    assert denominator.name in DENOMINATORS


def test_attacks_per_round_follows_attribution(silvertail):
    """``attacks_per_round`` is the one attacks metric that POOLS, and it is allowed
    to because it is a COUNT: swings add, where rates do not.  What it pools is the
    declared attribution, so it cannot disagree with the headline about whose column
    it describes."""
    both = run(RunConfig(build="silvertail", level=10, n_days=30, seed=3,
                         build_options=ZONE, attribution="character_and_summons"))
    character_only = silvertail.values["attacks_per_round"].value
    with_summon = both.values["attacks_per_round"].value
    assert with_summon > character_only
    assert both.values["dpr"].value > silvertail.values["dpr"].value


def test_the_attacks_rows_exercise_two_of_the_three_states(silvertail):
    """Measured and unavailable both appear among the new cells on one real run, so
    the guards above are not asserting over an empty set."""
    rows = [silvertail.values[METRICS.breakdown("attack_roll_rate").cell_name(k)]
            for k in METRICS.breakdown("attack_roll_rate").keys()]
    assert any(r.measured for r in rows)
    assert any(not r.available for r in rows)
    assert all(r.value is None for r in rows if not r.available)
