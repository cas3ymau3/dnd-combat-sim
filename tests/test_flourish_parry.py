"""
test_flourish_parry.py — the intercept_event primitive (Flourish Parry) and its
counter (Flourish Counter), plus the supporting engine bits.

Three layers, mirroring test_weapon_mastery.py's structure:

  1. resolve_damage — extra_flat_damage (Brutality::bleed's +CHA) folds into the
     phase-5 flat bonus.
  2. resolve_attack_roll — the intercept decision point: a confirmed hit is
     offered to the DEFENDER, who may raise AC (flip to a miss) and counter.
     Tested with hand-built intercept_decider closures (no policy).
  3. WarAngelPolicy.on_incoming_hit — the L14 parry/counter logic (no RNG).
  4. Scheduler integration — a full mini-combat: an enemy hit is parried (no
     damage, no concentration check) and a policy_riders=False counter lands on
     the enemy without triggering the character's on_hit riders.
"""

import math

from src.entity import Entity
from src.events import AttackRollEvent, DamageEvent, EventQueue, make_tick
from src.policy import (
    Choice,
    CounterSpec,
    GameState,
    IncomingAttackContext,
    InterceptResponse,
)
from src.resources import ResourceEntry, ResourcePool
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.verbs import resolve_attack_roll, resolve_damage
from src.builds import war_angel


# ---------------------------------------------------------------------------
# Deterministic fake RNG (same shape as test_weapon_mastery.FakeRNG)
# ---------------------------------------------------------------------------

class FakeRNG:
    """Pops preloaded values; records (n, sides) per call."""
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


# ---------------------------------------------------------------------------
# 1. extra_flat_damage in resolve_damage
# ---------------------------------------------------------------------------

def test_extra_flat_damage_adds_to_phase5():
    target = Entity(name="T", hp=100, base_stats={})
    a = Entity(name="A", hp=10, base_stats={})
    # Flat-only hit (0 dice): 0 rolled + damage_bonus 2 + extra_flat 5 = 7.
    ev = DamageEvent(
        tick=(1, 0, 1), actor=a, target=target,
        damage_dice=(0, 6), damage_bonus=2, extra_flat_damage=5,
    )
    total, _ = resolve_damage(ev, FakeRNG([]), None, next_sequence=2)
    assert total == 7
    assert target.hp == 93


def test_extra_flat_damage_does_not_scale_on_crit():
    target = Entity(name="T", hp=100, base_stats={})
    a = Entity(name="A", hp=10, base_stats={})
    # 1d8 crit → 2d8 rolled (4+4=8); damage_bonus 0; extra_flat 5 stays flat.
    ev = DamageEvent(
        tick=(1, 0, 1), actor=a, target=target, is_crit=True,
        damage_dice=(1, 8), damage_bonus=0, extra_flat_damage=5,
    )
    total, _ = resolve_damage(ev, FakeRNG([4, 4]), None, next_sequence=2)
    assert total == 8 + 5  # dice doubled, flat not


# ---------------------------------------------------------------------------
# 2. resolve_attack_roll intercept (Flourish Parry) — hand-built deciders
# ---------------------------------------------------------------------------

def test_parry_flips_marginal_hit_to_miss():
    a, d = _attacker(), _defender(ac=10)
    q = EventQueue()
    # d20=13 vs AC 10 → hit by 3. +5 AC → AC 15 > 13 → flips to a miss.
    resolve_attack_roll(a_ev := AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=d),
                        FakeRNG([13]), q, next_sequence=2,
                        intercept_decider=lambda margin: (5, None))
    assert len(q) == 0  # no DamageEvent — the hit became a miss


def test_intercept_guard_rejects_insufficient_bonus():
    a, d = _attacker(), _defender(ac=10)
    q = EventQueue()
    # d20=18 vs AC 10 → hit by 8.  Even a returned +5 cannot flip it (resolve's
    # own guard: total 18 >= AC+bonus 15), so the hit stands and damage is pushed.
    resolve_attack_roll(AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=d),
                        FakeRNG([18]), q, next_sequence=2,
                        intercept_decider=lambda margin: (5, None))
    assert len(q) == 1
    assert isinstance(q.pop(), DamageEvent)


def test_intercept_not_consulted_on_a_miss():
    a, d = _attacker(), _defender(ac=20)
    q = EventQueue()
    called = []
    # d20=3 vs AC 20 → a real miss; the interceptor must never be offered.
    resolve_attack_roll(AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=d),
                        FakeRNG([3]), q, next_sequence=2,
                        intercept_decider=lambda margin: called.append(margin) or (5, None))
    assert called == []
    assert len(q) == 0


def test_counter_enqueued_on_flip():
    a, d = _attacker(), _defender(ac=10)
    q = EventQueue()
    counter = CounterSpec(target=a, masteries=["sap"], extra_flat_damage=5)
    # d20=12 vs AC 10 → hit by 2 → +5 flips it; counter is enqueued.
    next_seq = resolve_attack_roll(
        AttackRollEvent(tick=make_tick(1, 1, 1), actor=a, target=d),
        FakeRNG([12]), q, next_sequence=2,
        intercept_decider=lambda margin: (5, counter),
    )
    assert len(q) == 1
    ev = q.pop()
    assert isinstance(ev, AttackRollEvent)
    assert ev.actor is d              # the defender counters
    assert ev.target is a             # ...the original attacker
    assert ev.cost == "reaction"
    assert ev.policy_riders is False  # carries its own bleed; no smite/bluff
    assert ev.masteries == ["sap"]
    assert ev.extra_flat_damage == 5
    assert next_seq == 3              # consumed one sequence number for the counter


def test_no_counter_when_spec_absent():
    a, d = _attacker(), _defender(ac=10)
    q = EventQueue()
    resolve_attack_roll(AttackRollEvent(tick=make_tick(1, 1, 1), actor=a, target=d),
                        FakeRNG([12]), q, next_sequence=2,
                        intercept_decider=lambda margin: (5, None))
    assert len(q) == 0  # parried, but no counter spec → nothing enqueued


# ---------------------------------------------------------------------------
# 3. WarAngelPolicy.on_incoming_hit — parry/counter logic (no RNG)
# ---------------------------------------------------------------------------

def _l14_policy():
    char = war_angel.make_war_angel(14)
    enemy = war_angel.make_training_dummy(14)
    pol = war_angel.WarAngelPolicy(level=14, target=enemy)
    return pol, char, enemy


def _incoming(enemy, defender, margin, round_number=1, flourish_counter=6):
    return IncomingAttackContext(
        defender=defender, attacker=enemy, hit_margin=margin, cost="action",
        resources={"flourish_counter": flourish_counter}, round_number=round_number,
    )


def test_policy_parries_and_counters_a_flippable_hit():
    pol, char, enemy = _l14_policy()
    resp = pol.on_incoming_hit(_incoming(enemy, char, margin=2))
    assert resp is not None
    assert resp.ac_bonus == 5
    assert resp.resource_cost == {"flourish_counter": 1}
    assert resp.counter is not None
    assert resp.counter.target is enemy
    assert resp.counter.masteries == ["sap"]
    assert resp.counter.extra_flat_damage == 5
    assert pol._last_parry_round == 1  # committed


def test_policy_declines_a_solid_hit():
    pol, char, enemy = _l14_policy()
    # +5 cannot flip a hit by 5 or more.
    assert pol.on_incoming_hit(_incoming(enemy, char, margin=5)) is None
    assert pol.on_incoming_hit(_incoming(enemy, char, margin=9)) is None
    # Boundary: hit by 4 DOES flip (5 > 4).
    assert pol.on_incoming_hit(_incoming(enemy, char, margin=4)) is not None


def test_policy_parries_at_most_once_per_round():
    pol, char, enemy = _l14_policy()
    first = pol.on_incoming_hit(_incoming(enemy, char, margin=2, round_number=2))
    assert first is not None
    # A second flippable hit the same round is declined (reaction spent).
    assert pol.on_incoming_hit(_incoming(enemy, char, margin=1, round_number=2)) is None
    # A new round frees the reaction again.
    assert pol.on_incoming_hit(_incoming(enemy, char, margin=2, round_number=3)) is not None


def test_policy_still_parries_when_counter_budget_empty():
    pol, char, enemy = _l14_policy()
    resp = pol.on_incoming_hit(_incoming(enemy, char, margin=2, flourish_counter=0))
    assert resp is not None
    assert resp.ac_bonus == 5         # the free parry still happens
    assert resp.counter is None       # ...but no counter without a charge
    assert resp.resource_cost == {}


def test_policy_below_l14_never_intercepts():
    char = war_angel.make_war_angel(13)
    enemy = war_angel.make_training_dummy(13)
    pol = war_angel.WarAngelPolicy(level=13, target=enemy)
    assert pol.on_incoming_hit(_incoming(enemy, char, margin=1)) is None


def test_on_combat_start_resets_the_parry_gate():
    pol, char, enemy = _l14_policy()
    pol._last_parry_round = 3
    pol.on_combat_start(0, SeededRNG(0))
    assert pol._last_parry_round == -1


# ---------------------------------------------------------------------------
# 4. Scheduler integration — parry skips damage + concentration; counter lands
#    without firing the defender's on_hit riders (policy_riders=False).
# ---------------------------------------------------------------------------

class _ParryCounterDefender:
    """Minimal defender: makes no attacks of its own, parries+counters a flippable
    incoming hit, and records whether its on_hit was ever consulted."""

    def __init__(self, attacker):
        self._attacker = attacker
        self.on_hit_called = False

    def decide(self, snapshot: GameState):
        return []  # no offense on our own turn

    def on_hit(self, ctx):
        self.on_hit_called = True
        return None

    def on_incoming_hit(self, ctx: IncomingAttackContext):
        if ctx.hit_margin >= 5:
            return None
        counter = CounterSpec(target=ctx.attacker, masteries=["sap"], extra_flat_damage=5)
        return InterceptResponse(ac_bonus=5,
                                 resource_cost={"flourish_counter": 1},
                                 counter=counter)


class _EnemyOneSwing:
    def __init__(self, target):
        self._target = target

    def decide(self, snapshot: GameState):
        if snapshot.resources.get("action", 0) < 1:
            return []
        return [Choice(action_type="attack", cost="action", target=self._target)]


def test_scheduler_parry_skips_damage_and_concentration_then_counters():
    # Defender: AC 10, concentrating on bless, holds one flourish_counter charge.
    defender = Entity(
        name="WarAngel", hp=100,
        base_stats={"ac": 10, "attack_bonus": 0, "damage_dice": (1, 8),
                    "damage_bonus": 0, "weapon_mastery": "sap", "con_save": 0},
        resources=ResourcePool({"flourish_counter": ResourceEntry(1, 1, 0)}),
    )
    defender.concentration = "bless"

    enemy = Entity(name="Ogre", hp=100,
                   base_stats={"ac": 10, "attack_bonus": 0, "damage_dice": (1, 8),
                               "damage_bonus": 0})

    def_policy = _ParryCounterDefender(attacker=enemy)
    rng = FakeRNG([
        13,   # enemy d20 vs AC 10 → hit by 3 → parried (+5 → AC 15) → miss
        15,   # counter d20 vs enemy AC 10 → hits
        4,    # counter damage 1d8
    ])
    sched = Scheduler(
        rng=rng,
        entities=[defender, enemy],          # defender turn first, enemy second
        policies={defender.id: def_policy, enemy.id: _EnemyOneSwing(defender)},
        max_rounds=1,
    )
    sched.run()

    # The enemy's hit was parried → defender took no damage, no concentration check.
    assert defender.hp == 100
    assert defender.concentration == "bless"
    assert defender.concentration_checks == 0
    # The flourish charge was spent on the counter.
    assert defender.resources.available("flourish_counter") == 0
    # The counter landed on the enemy: 1d8 (4) + bleed flat (5) = 9.
    assert sched.damage_received[enemy.id] == [9]
    # policy_riders=False kept the counter from triggering the defender's on_hit.
    assert def_policy.on_hit_called is False
    # Bleed applied sap to the enemy on the counter's hit.
    assert enemy.statuses.has("sapped")
