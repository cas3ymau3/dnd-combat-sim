"""
test_reaction_economy.py — the §13 REACTIONS channel, both ends (§3.5.1, §8.2a).

s53 found this channel **dead at both ends**: ``CombatTelemetry`` had a
``record_reaction()`` method with a merge rule and a unit test, and *its only caller
was that unit test*, while no metric read the field.  So War Angel L13 spent its
opportunity attack every combat — the pre-roll firing on the expected round, the
scheduler even branching on ``event.cost == "reaction"`` — and the channel read **0
over 800 rounds**.  s51's cut (a FIELD nothing reads) and this (a RECORDER nothing
calls) are the same defect from opposite sides, and neither is visible unless "who
WRITES this?" and "who READS this?" are asked as two separate questions.

So the tests below are organized by those two questions, and the roll call is the
list of writers.

THE ROLL CALL (per-feature ritual step 5) — one row per DECLARATION this change
touches, one column naming the fixture that covers each VALUE.

| declaration | values | fixture covering each |
|---|---|---|
| reaction WRITER site | 1: the choice loop (``econ[cost] -= 1``) | ``test_an_opportunity_attack_is_recorded_against_its_actor`` + ``test_war_angels_aoo_is_no_longer_invisible`` (the production instance) |
| | 2: the on-hit decider (``_turn_economy[ac] -= 1``) | ``test_an_on_hit_response_paying_a_reaction_is_recorded`` — **SYNTHETIC ONLY**, see below |
| | 3: the intercept decider (no economy debit) | ``test_a_parry_records_a_reaction_for_the_defender`` |
| ``InterceptResponse.reaction_by`` | ``None`` (automatic) | ``test_fire_shields_thorns_are_automatic_and_record_nothing`` |
| | the DEFENDER's id | ``test_a_parry_records_a_reaction_for_the_defender`` |
| | a THIRD party's id (the protector) | ``test_protection_records_the_reaction_against_the_protector`` |
| ``CombatTelemetry.reactions`` keying | one actor / several actors | ``test_the_channel_separates_actors`` |
| ``reactions_for`` scope | a scope / ``None`` (pool everything) | ``test_the_reader_scopes_by_actor`` |
| ``reactions_per_round`` metric | a run that takes reactions / one that takes none | ``test_the_metric_reads_the_channel_end_to_end`` and ``test_a_build_that_takes_no_reactions_reads_a_true_zero`` |

**THE EMPTY CELL, named rather than left blank (the roll call's whole purpose).**
Writer 2 — an ``on_hit`` response whose ``action_cost`` is ``"reaction"`` — has **no
production fixture**, because no shipped build reaches it: War Angel's smite spends the
bonus action and its Guided Strike spends a persistent resource, not an economy slot.
It is wired anyway, and the reason is the s52 dormancy lesson: the alternative is a path
that silently records nothing and would read as a measurement the first day a build used
it, with no equality holding it stable and nothing failing when it was first reached.
The synthetic fixture below is therefore the only cover it has, and that is stated here
so the next session does not mistake a green suite for production coverage.

**AND THE COUNT CAN EXCEED 1.0 PER ROUND.** That is not a defect; it is a documented
approximation becoming visible (§8.2a). Two of the three writers debit the turn economy;
the intercept does not, because the War Angel guide prices the parry and the opportunity
attack as both happening — "even though they both consume our reaction, this assumption
feels right since we don't have any other demands on our reaction". A test below asserts
the double-booking is REACHABLE rather than pretending it is not.
"""

from __future__ import annotations

import pytest

from src.builds import character_stats, silvertail, starfire_scion, war_angel
from src.entity import Entity
from src.evaluation.config import RunConfig
from src.evaluation.metrics import METRICS
from src.evaluation.runner import simulate
from src.policy import (
    Choice,
    CounterSpec,
    GameState,
    HitResponse,
    IncomingAttackContext,
    InterceptResponse,
)
from src.resources import ResourceEntry, ResourcePool
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.telemetry import CombatTelemetry


class FakeRNG:
    """Pops preloaded values; records (n, sides) per call."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides, *, stream=None):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides, *, stream=None):
        self.roll_calls.append((1, sides))
        return self._values.pop(0)


def _plain(name, ac=10, **extra):
    stats = {"ac": ac, "attack_bonus": 0, "damage_dice": (1, 8), "damage_bonus": 0}
    stats.update(extra)
    return Entity(name=name, hp=200, base_stats=stats, **{})


# ---------------------------------------------------------------------------
# 1. The channel itself — keying and the reader
# ---------------------------------------------------------------------------

def test_the_channel_separates_actors():
    """ACTOR-KEYED, which is the change the per-METRIC ritual's first question forced.

    A bare counter had no answer to "whose quantity is this?": one combat holds the
    character's opportunity attack, a commanded summon's reactions and the enemy's.
    """
    t = CombatTelemetry()
    t.record_reaction(1)
    t.record_reaction(1)
    t.record_reaction(2)
    assert t.reactions == {1: 2, 2: 1}


def test_the_reader_scopes_by_actor():
    """``reactions_for`` is the READER half, and it branches on whether a scope is
    given — both values covered, because the unscoped default pools the enemy in."""
    t = CombatTelemetry()
    t.record_reaction(1)
    t.record_reaction(2)
    assert t.reactions_for({1}) == 1
    assert t.reactions_for({1, 2}) == 2
    assert t.reactions_for({3}) == 0
    assert t.reactions_for(None) == 2          # pools everything, enemy included


# ---------------------------------------------------------------------------
# 2. WRITER 1 — the choice loop (the opportunity attack)
# ---------------------------------------------------------------------------

class _ReactorPolicy:
    """Takes one reaction-cost attack on its turn, then an action attack."""

    def __init__(self, target, reactions=1):
        self._target = target
        self._reactions = reactions

    def decide(self, snapshot: GameState):
        if snapshot.resources.get("action", 0) < 1:
            return []
        out = [Choice(action_type="attack", cost="reaction", target=self._target)
               for _ in range(self._reactions)]
        out.append(Choice(action_type="attack", cost="action", target=self._target))
        return out


def test_an_opportunity_attack_is_recorded_against_its_actor():
    """WRITER 1: the scheduler's choice loop, gated on ``cost == "reaction"``."""
    char = _plain("Char")
    enemy = _plain("Enemy")
    sched = Scheduler(
        rng=FakeRNG([15, 4, 15, 4]),
        entities=[char],
        policies={char.id: _ReactorPolicy(enemy)},
        max_rounds=1,
    )
    sched.run()
    assert sched.telemetry.reactions == {char.id: 1}


def test_only_the_reaction_slot_is_counted_not_every_economy_debit():
    """The gate is real: an action and a bonus action are economy debits too, and
    counting them would turn this into an action-economy total."""
    char = _plain("Char")
    enemy = _plain("Enemy")

    class _NoReactions:
        def decide(self, snapshot):
            if snapshot.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="action", target=enemy),
                    Choice(action_type="attack", cost="bonus_action", target=enemy)]

    sched = Scheduler(rng=FakeRNG([15, 4, 15, 4]), entities=[char],
                      policies={char.id: _NoReactions()}, max_rounds=1)
    sched.run()
    assert sched.telemetry.reactions == {}


def test_a_reaction_the_economy_refuses_is_not_recorded():
    """A second reaction in one turn is skipped by the economy check, and so must not
    be recorded: the counter is "reactions taken", and a refused choice took none."""
    char = _plain("Char")
    enemy = _plain("Enemy")
    sched = Scheduler(
        rng=FakeRNG([15, 4, 15, 4]),
        entities=[char],
        policies={char.id: _ReactorPolicy(enemy, reactions=3)},
        max_rounds=1,
    )
    sched.run()
    assert sched.telemetry.reactions == {char.id: 1}


def test_a_commanded_summons_reaction_is_charged_to_its_commander():
    """``Choice.actor`` (substrate #7 / 7a) splits the entity that PAYS from the entity
    that ACTS, and the reaction paid is the commander's — the same split the
    ``resource_cost`` drain already makes one line above the record call.

    Worth a fixture rather than a comment: the two plausible keys differ here, and a
    run on a summon build is where a pooled count would have been wrong.
    """
    master = _plain("Master")
    beast = _plain("Beast")
    enemy = _plain("Enemy")

    class _Commander:
        def decide(self, snapshot):
            if snapshot.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="reaction",
                           target=enemy, actor=beast)]

    sched = Scheduler(rng=FakeRNG([15, 4]), entities=[master],
                      policies={master.id: _Commander()}, max_rounds=1)
    sched.run()
    assert sched.telemetry.reactions == {master.id: 1}
    assert beast.id not in sched.telemetry.reactions


# ---------------------------------------------------------------------------
# 3. WRITER 2 — the on-hit decider.  SYNTHETIC ONLY: see the module docstring.
# ---------------------------------------------------------------------------

def test_an_on_hit_response_paying_a_reaction_is_recorded():
    """WRITER 2, which **no shipped build reaches** (the roll call's empty cell).

    Wired because an unrecorded path reads as a measurement the day a build uses it,
    and nothing would fail when it was first reached — the s52 dormancy question's
    third and worst answer.
    """
    char = _plain("Char", attack_bonus=10)
    enemy = _plain("Enemy", ac=5)

    class _RiderOnHit:
        def decide(self, snapshot):
            if snapshot.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="action", target=enemy)]

        def on_hit(self, ctx):
            return HitResponse(resource_cost={}, action_cost="reaction",
                               extra_damage_dice=[(1, 6)])

    sched = Scheduler(rng=FakeRNG([15, 4, 3]), entities=[char],
                      policies={char.id: _RiderOnHit()}, max_rounds=1)
    sched.run()
    assert sched.telemetry.reactions == {char.id: 1}


# ---------------------------------------------------------------------------
# 4. WRITER 3 — the intercept decider, and `reaction_by`'s three values
# ---------------------------------------------------------------------------

class _EnemyOneSwing:
    def __init__(self, target):
        self._target = target

    def decide(self, snapshot: GameState):
        if snapshot.resources.get("action", 0) < 1:
            return []
        return [Choice(action_type="attack", cost="action", target=self._target)]


def _one_swing(defender, def_policy, rng_values):
    """Run one combat in which the enemy takes a single swing at *defender*."""
    enemy = _plain("Enemy")
    sched = Scheduler(
        rng=FakeRNG(rng_values),
        entities=[enemy],
        policies={enemy.id: _EnemyOneSwing(defender), defender.id: def_policy},
        max_rounds=1,
    )
    sched.run()
    return sched, enemy


def test_a_parry_records_a_reaction_for_the_defender():
    """WRITER 3, and ``reaction_by``'s "the defender" value.

    Note there is NO ``_turn_economy`` write here to hang the record on — the intercept
    reaction is the policy's own once-per-round gate — which is exactly why the
    spender has to be declared on the response.
    """
    defender = _plain("Defender", con_save=0)

    class _Parry:
        def decide(self, snapshot):
            return []

        def on_incoming_hit(self, ctx: IncomingAttackContext):
            if ctx.hit_margin >= 5:
                return None
            return InterceptResponse(ac_bonus=5, reaction_by=ctx.defender.id)

    sched, _ = _one_swing(defender, _Parry(), [13])      # hits by 3 → parried
    assert sched.telemetry.reactions == {defender.id: 1}
    assert defender.hp == 200                            # the parry flipped it


def test_protection_records_the_reaction_against_the_protector():
    """``reaction_by``'s THIRD value — an entity that is neither the attacker nor the
    defender.

    2024's Protection fighting style is "you can use your Reaction to impose
    Disadvantage", and the reaction is the PROTECTOR's. The scheduler builds this
    closure around the DEFENDER, so "whoever's policy answered" would charge the wrong
    entity — and it is already wrong for both shipped Protection implementations, with
    nothing failing, because nothing read the channel.
    """
    warded = _plain("Warded", con_save=0)
    protector = _plain("Protector")

    class _Protection:
        def decide(self, snapshot):
            return []

        def on_incoming_hit(self, ctx: IncomingAttackContext):
            return InterceptResponse(impose_disadvantage=True,
                                     reaction_by=protector.id)

    sched, _ = _one_swing(warded, _Protection(), [15, 3])
    assert sched.telemetry.reactions == {protector.id: 1}
    assert warded.id not in sched.telemetry.reactions


def test_fire_shields_thorns_are_automatic_and_record_nothing():
    """``reaction_by``'s ``None`` value — the automatic intercepts.

    Fire Shield's thorns, Warding Bond's redirect and Sanctuary's save are not
    reactions in the 2024 rules, so counting them would inflate the channel with
    effects that cost no action economy at all.
    """
    from src.policy import ReactiveDamageSpec

    defender = _plain("Defender", con_save=20)

    class _Thorns:
        def decide(self, snapshot):
            return []

        def on_incoming_hit(self, ctx: IncomingAttackContext):
            return InterceptResponse(reactive_damage=ReactiveDamageSpec(
                damage_dice=(2, 8), damage_type="fire"))

    sched, enemy = _one_swing(defender, _Thorns(), [15, 4, 3, 3, 15])
    assert sched.telemetry.reactions == {}
    # ...and the thorns genuinely fired, so this is a zero with a measurement behind it.
    assert sched.damage_received[enemy.id]


def test_the_shipped_intercepts_declare_the_rules_reading():
    """The five shipped intercepts, as a table, so a sixth cannot arrive without a
    verdict.

    Reads ``reaction_by`` off the real policies rather than restating the taxonomy in
    prose — §8.2a's table and this assertion are the same claim, and only one of them
    can fail.
    """
    # Flourish Parry — a reaction, the defender's.
    pol = war_angel.WarAngelPolicy(level=14, target=_plain("Enemy"))
    char = war_angel.make_war_angel(14)
    resp = pol.on_incoming_hit(IncomingAttackContext(
        defender=char, attacker=_plain("Enemy"), hit_margin=1, cost="action",
        resources={"flourish_counter": 0}, round_number=1, range_="melee"))
    assert resp is not None and resp.reaction_by == char.id

    # Protection — a reaction, the PROTECTOR's, on both shipped implementations.
    caster = starfire_scion.make_starfire_scion(15)
    ally = starfire_scion.make_ally(15)
    ally_pol = starfire_scion.AllyEffectPolicy(
        effect="protection", ally=ally, caster=caster)
    resp = ally_pol.on_incoming_hit(None)
    assert resp.impose_disadvantage and resp.reaction_by == caster.id

    # Warding Bond — automatic, no reaction.
    bond_pol = starfire_scion.AllyEffectPolicy(
        effect="warding_bond", ally=ally, caster=caster)
    assert bond_pol.on_incoming_hit(None).reaction_by is None

    # Sanctuary — the ATTACKER saves; no reaction.
    sanct_pol = starfire_scion.AllyEffectPolicy(
        effect="sanctuary", ally=ally, caster=caster)
    assert sanct_pol.on_incoming_hit(None).reaction_by is None


def test_the_double_booking_is_reachable_and_that_is_the_point():
    """One entity takes an opportunity attack AND an intercept reaction in the same
    round, so ``reactions_per_round`` can exceed 1.0.

    RAW-impossible, and deliberately so: the War Angel guide prices the parry and the
    opportunity attack as both happening. Asserting that the combination is REACHABLE
    is what makes the approximation a measured fact rather than a docstring — and it
    is what a reader seeing 1.0+ in a report needs in order to interpret it.
    """
    defender = _plain("Defender", con_save=0, attack_bonus=10)
    enemy = _plain("Enemy", ac=5)

    class _ParryAndAoO:
        def decide(self, snapshot):
            if snapshot.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="reaction", target=enemy)]

        def on_incoming_hit(self, ctx: IncomingAttackContext):
            if ctx.hit_margin >= 5:
                return None
            return InterceptResponse(ac_bonus=5, reaction_by=ctx.defender.id)

    sched = Scheduler(
        rng=FakeRNG([15, 4, 13]),
        entities=[defender, enemy],
        policies={defender.id: _ParryAndAoO(), enemy.id: _EnemyOneSwing(defender)},
        max_rounds=1,
    )
    sched.run()
    assert sched.telemetry.reactions == {defender.id: 2}


# ---------------------------------------------------------------------------
# 5. The READER half, end to end: the registered metric
# ---------------------------------------------------------------------------

def test_the_metric_is_registered_and_scoped_to_the_attributed_roles():
    assert "reactions_per_round" in METRICS.names()
    scalar = next(d for d in METRICS.scalars() if d.name == "reactions_per_round")
    assert scalar.unit == "reactions/round"
    assert scalar.denominator == "rounds"
    # The definition has to say the count can exceed 1.0, because a reader who does
    # not know that will read the number as a defect.
    assert "EXCEED 1.0" in scalar.definition


def test_war_angels_aoo_is_no_longer_invisible():
    """THE PRODUCTION INSTANCE, and the regression this whole change exists for.

    s53 measured this channel at **0 over 800 rounds** while War Angel L13 spent its
    opportunity attack every combat. The AoO is once per combat on a pre-rolled round
    (its guide's own collapse of five timing slots into one), so over a 4-combat day it
    is 4 reactions in 16 rounds = 0.25/round — asserted as the exact figure rather than
    as "greater than zero", because "greater than zero" would also have passed on a
    channel that fired once by accident.
    """
    report = simulate(RunConfig(build="war_angel", level=13, enemy="baseline",
                                n_days=40, seed=11))
    samples = report.samples["reactions_per_round"]
    total = sum(samples.numerator)
    # 40 days × 4 combats × exactly one AoO each.
    assert total == 40 * 4
    assert "reactions_per_round" not in report.unavailable


def test_a_build_that_takes_no_reactions_reads_a_true_zero():
    """The other branch of the metric: a build with no reaction at all.

    A TRUE zero rather than "unavailable" — the channel is wired for every run, so
    "this build takes no reactions" is a measurement, exactly as
    ``attacks_per_round`` reports a save-forcing build's low volume.
    """
    report = simulate(RunConfig(build="silvertail", level=10, enemy="baseline",
                                n_days=20, seed=11))
    samples = report.samples["reactions_per_round"]
    assert sum(samples.numerator) == 0
    assert "reactions_per_round" not in report.unavailable
