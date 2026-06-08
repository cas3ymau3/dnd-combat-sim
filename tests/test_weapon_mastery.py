"""
test_weapon_mastery.py — advantage/disadvantage + sap/vex mastery.

Three layers:
  1. roll_d20 helper — advantage=max, disadvantage=min, both=straight.
  2. resolve_attack_roll — consumes sapped/vex statuses, rolls with the right
     adv/disadv, applies masteries on hit.
  3. Scheduler integration — masteries list built from weapon + extra_masteries
     + mastery_override; statuses applied on hit; expiry sweep at turn starts.
"""

import math
import pytest

from src.entity import Entity
from src.events import AttackRollEvent, make_tick
from src.events import EventQueue
from src.policy import Choice, ExtraAttackPolicy, GameState
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.verbs import apply_masteries_on_hit, resolve_attack_roll, roll_d20


# ---------------------------------------------------------------------------
# A deterministic fake RNG for exact-roll assertions
# ---------------------------------------------------------------------------

class FakeRNG:
    """Pops preloaded values; records how many dice each call requested."""
    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []  # list of (n, sides)

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        self.roll_calls.append((1, sides))
        return self._values.pop(0)


# ---------------------------------------------------------------------------
# 1. roll_d20 helper
# ---------------------------------------------------------------------------

def test_roll_d20_advantage_takes_max():
    rng = FakeRNG([5, 17])
    assert roll_d20(rng, advantage=True, disadvantage=False) == 17
    assert rng.roll_calls == [(2, 20)]

def test_roll_d20_disadvantage_takes_min():
    rng = FakeRNG([5, 17])
    assert roll_d20(rng, advantage=False, disadvantage=True) == 5
    assert rng.roll_calls == [(2, 20)]

def test_roll_d20_both_cancels_to_straight():
    rng = FakeRNG([11])
    assert roll_d20(rng, advantage=True, disadvantage=True) == 11
    assert rng.roll_calls == [(1, 20)]  # single die, not 2d20

def test_roll_d20_neither_is_straight():
    rng = FakeRNG([8])
    assert roll_d20(rng, advantage=False, disadvantage=False) == 8
    assert rng.roll_calls == [(1, 20)]

def test_roll_d20_advantage_higher_average_than_disadvantage():
    """Statistical sanity over many real rolls."""
    rng = SeededRNG(seed=1)
    adv = sum(roll_d20(rng, True, False) for _ in range(2000))
    dis = sum(roll_d20(rng, False, True) for _ in range(2000))
    assert adv > dis


# ---------------------------------------------------------------------------
# 2. apply_masteries_on_hit (direct)
# ---------------------------------------------------------------------------

def make_attacker(masteries=(), attack_bonus=100):
    e = Entity(name="Attacker", hp=50, base_stats={
        "attack_bonus": attack_bonus, "damage_dice": (1, 8), "damage_bonus": 0,
    })
    return e

def make_defender(ac=10):
    return Entity(name="Defender", hp=math.inf, base_stats={"ac": ac})

def make_attack_event(actor, target, masteries, round_=1, turn_idx=0):
    return AttackRollEvent(
        tick=make_tick(round_, turn_idx, 1),
        actor=actor,
        target=target,
        masteries=list(masteries),
    )

def test_sap_applies_sapped_to_target():
    a, d = make_attacker(), make_defender()
    ev = make_attack_event(a, d, ["sap"], round_=1, turn_idx=0)
    apply_masteries_on_hit(ev, a, d)
    assert d.statuses.has("sapped")
    # expiry = start of attacker's next turn = (2, 0)
    assert d.statuses._entries["sapped"].expiry == (2, 0)

def test_vex_applies_advantage_to_attacker_vs_target():
    a, d = make_attacker(), make_defender()
    ev = make_attack_event(a, d, ["vex"], round_=1, turn_idx=0)
    apply_masteries_on_hit(ev, a, d)
    assert a.statuses.get("vex_advantage") == d.id
    assert a.statuses._entries["vex_advantage"].expiry == (3, 0)

def test_both_masteries_apply_together():
    a, d = make_attacker(), make_defender()
    ev = make_attack_event(a, d, ["sap", "vex"])
    apply_masteries_on_hit(ev, a, d)
    assert d.statuses.has("sapped")
    assert a.statuses.get("vex_advantage") == d.id


# ---------------------------------------------------------------------------
# 2b. resolve_attack_roll consumes statuses & rolls adv/disadv
# ---------------------------------------------------------------------------

def test_resolve_consumes_sapped_and_rolls_disadvantage():
    a, d = make_attacker(attack_bonus=0), make_defender(ac=10)
    a.statuses.apply("sapped")
    q = EventQueue()
    rng = FakeRNG([18, 3])  # disadvantage → min = 3
    ev = make_attack_event(a, d, [])  # no new masteries on this swing
    resolve_attack_roll(ev, rng, q, next_sequence=2)
    assert not a.statuses.has("sapped")        # consumed
    assert rng.roll_calls[0] == (2, 20)        # rolled with disadvantage

def test_resolve_consumes_vex_and_rolls_advantage():
    a, d = make_attacker(attack_bonus=0), make_defender(ac=10)
    a.statuses.apply("vex_advantage", value=d.id)  # advantage vs this target
    q = EventQueue()
    rng = FakeRNG([4, 19])  # advantage → max = 19
    ev = make_attack_event(a, d, [])
    resolve_attack_roll(ev, rng, q, next_sequence=2)
    assert not a.statuses.has("vex_advantage")  # consumed
    assert rng.roll_calls[0] == (2, 20)         # rolled with advantage

def test_resolve_vex_only_applies_to_matching_target():
    a = make_attacker(attack_bonus=0)
    d1, d2 = make_defender(), make_defender()
    a.statuses.apply("vex_advantage", value=d1.id)  # advantage vs d1 only
    q = EventQueue()
    rng = FakeRNG([7])  # straight roll → single die
    ev = make_attack_event(a, d2, [])  # attacking d2, not the vexed target
    resolve_attack_roll(ev, rng, q, next_sequence=2)
    assert a.statuses.has("vex_advantage")  # NOT consumed (wrong target)
    assert rng.roll_calls[0] == (1, 20)     # straight roll


# ---------------------------------------------------------------------------
# 3. Scheduler integration
# ---------------------------------------------------------------------------

def make_fighter(weapon_mastery=None, attack_bonus=100):
    stats = {"attack_bonus": attack_bonus, "damage_dice": (1, 8), "damage_bonus": 0, "ac": 16}
    if weapon_mastery:
        stats["weapon_mastery"] = weapon_mastery
    return Entity(name="Fighter", hp=52, base_stats=stats)

def make_dummy(ac=10):
    return Entity(name="Dummy", hp=math.inf, base_stats={"ac": ac})


def test_scheduler_applies_sap_on_hit():
    fighter = make_fighter(weapon_mastery="sap")
    dummy = make_dummy()
    rng = SeededRNG(seed=1)
    sched = Scheduler(
        rng=rng,
        entities=[fighter, dummy],
        policies={fighter.id: ExtraAttackPolicy(target=dummy, extra_attacks=0)},
        max_rounds=1,  # single turn so no expiry sweep clears it
    )
    sched.run()
    assert dummy.statuses.has("sapped")


def test_scheduler_applies_vex_on_hit():
    fighter = make_fighter(weapon_mastery="vex")
    dummy = make_dummy()
    rng = SeededRNG(seed=1)
    sched = Scheduler(
        rng=rng,
        entities=[fighter, dummy],
        policies={fighter.id: ExtraAttackPolicy(target=dummy, extra_attacks=0)},
        max_rounds=1,
    )
    sched.run()
    assert fighter.statuses.get("vex_advantage") == dummy.id


def test_scheduler_builds_combined_masteries_from_extra():
    """extra_masteries stacks on top of the weapon's natural mastery."""
    fighter = make_fighter(weapon_mastery="sap")
    dummy = make_dummy()

    class BluffPolicy:
        def decide(self, snap: GameState):
            if snap.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="action",
                           target=dummy, extra_masteries=["vex"])]

    rng = SeededRNG(seed=1)
    sched = Scheduler(rng=rng, entities=[fighter, dummy],
                      policies={fighter.id: BluffPolicy()}, max_rounds=1)
    sched.run()
    # Both effects should have landed
    assert dummy.statuses.has("sapped")
    assert fighter.statuses.get("vex_advantage") == dummy.id


def test_scheduler_mastery_override_replaces_weapon():
    """mastery_override replaces the weapon's natural mastery."""
    fighter = make_fighter(weapon_mastery="sap")
    dummy = make_dummy()

    class OverridePolicy:
        def decide(self, snap: GameState):
            if snap.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="action",
                           target=dummy, mastery_override="vex")]

    rng = SeededRNG(seed=1)
    sched = Scheduler(rng=rng, entities=[fighter, dummy],
                      policies={fighter.id: OverridePolicy()}, max_rounds=1)
    sched.run()
    # sap was overridden → not applied; vex applied
    assert not dummy.statuses.has("sapped")
    assert fighter.statuses.get("vex_advantage") == dummy.id


def test_sap_expires_at_attacker_next_turn():
    """If the sapped entity never attacks, sap is purged at the applier's next turn.

    Fighter saps only in round 1 (one-shot policy), so round 2's turn-start
    expiry sweep at (2, 0) purges it with no reapplication.
    """
    fighter = make_fighter(weapon_mastery="sap")
    dummy = make_dummy()

    class SapOnceRound1:
        def decide(self, snap: GameState):
            if snap.round_number != 1 or snap.resources.get("action", 0) < 1:
                return []
            return [Choice(action_type="attack", cost="action", target=dummy)]

    rng = SeededRNG(seed=1)
    sched = Scheduler(
        rng=rng,
        entities=[fighter, dummy],
        policies={fighter.id: SapOnceRound1()},
        max_rounds=2,
    )
    sched.run()
    assert not dummy.statuses.has("sapped")
