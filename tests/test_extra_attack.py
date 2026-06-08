"""
test_extra_attack.py — Extra Attack milestone tests.

Validates that ExtraAttackPolicy produces two (or more) attack rolls per turn
and that the action economy is correctly enforced.

Strategy for counting attacks without engine instrumentation:
  - Use a guaranteed-hit setup (attack_bonus=100, ac=10) so every roll
    produces a DamageEvent.  Damage instances per round == attack rolls per
    round (minus crits, which still produce exactly one DamageEvent).
  - Compare total damage vs. the DummySwingPolicy baseline to confirm the
    extra swing is doing real work.
"""

import math
import pytest

from src.entity import Entity
from src.policy import Choice, DummySwingPolicy, ExtraAttackPolicy, GameState
from src.rng import SeededRNG
from src.scheduler import Scheduler


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_fighter(attack_bonus=100, damage_dice=(1, 8), damage_bonus=0):
    return Entity(
        name="Fighter",
        hp=52,
        base_stats={
            "attack_bonus": attack_bonus,
            "damage_dice": damage_dice,
            "damage_bonus": damage_bonus,
        },
    )


def make_dummy(ac=10):
    return Entity(name="Dummy", hp=math.inf, base_stats={"ac": ac})


def run_extra_attack(seed=42, rounds=10, extra_attacks=1, bonus_action_attack=False):
    fighter = make_fighter()
    dummy = make_dummy()
    rng = SeededRNG(seed=seed)
    policy = ExtraAttackPolicy(
        target=dummy,
        extra_attacks=extra_attacks,
        bonus_action_attack=bonus_action_attack,
    )
    scheduler = Scheduler(
        rng=rng,
        entities=[fighter, dummy],
        policies={fighter.id: policy},
        max_rounds=rounds,
    )
    return scheduler.run()


def run_single_attack(seed=42, rounds=10):
    fighter = make_fighter()
    dummy = make_dummy()
    rng = SeededRNG(seed=seed)
    policy = DummySwingPolicy(target=dummy)
    scheduler = Scheduler(
        rng=rng,
        entities=[fighter, dummy],
        policies={fighter.id: policy},
        max_rounds=rounds,
    )
    return scheduler.run()


# ---------------------------------------------------------------------------
# Policy unit tests (no scheduler involved)
# ---------------------------------------------------------------------------

def _make_snapshot(resources):
    fighter = make_fighter()
    dummy = make_dummy()
    return GameState(
        actor=fighter,
        enemies=(dummy,),
        allies=(),
        round_number=1,
        turn_index=0,
        tick=(1, 0, 0),
        resources=resources,
    )


def test_policy_returns_two_choices_when_action_available():
    policy = ExtraAttackPolicy(target=make_dummy())
    snap = _make_snapshot({"action": 1, "bonus_action": 1, "reaction": 1})
    choices = policy.decide(snap)
    assert len(choices) == 2


def test_policy_first_choice_costs_action():
    policy = ExtraAttackPolicy(target=make_dummy())
    snap = _make_snapshot({"action": 1, "bonus_action": 1, "reaction": 1})
    choices = policy.decide(snap)
    assert choices[0].cost == "action"


def test_policy_second_choice_costs_none():
    policy = ExtraAttackPolicy(target=make_dummy())
    snap = _make_snapshot({"action": 1, "bonus_action": 1, "reaction": 1})
    choices = policy.decide(snap)
    assert choices[1].cost == "none"


def test_policy_returns_empty_when_no_action():
    policy = ExtraAttackPolicy(target=make_dummy())
    snap = _make_snapshot({"action": 0, "bonus_action": 1, "reaction": 1})
    choices = policy.decide(snap)
    assert choices == []


def test_policy_three_attacks_with_extra_attacks_2():
    policy = ExtraAttackPolicy(target=make_dummy(), extra_attacks=2)
    snap = _make_snapshot({"action": 1, "bonus_action": 1, "reaction": 1})
    choices = policy.decide(snap)
    assert len(choices) == 3
    assert choices[0].cost == "action"
    assert all(c.cost == "none" for c in choices[1:])


def test_policy_bonus_action_attack_interleaved():
    """Bonus action attack should appear between primary and extra attack."""
    policy = ExtraAttackPolicy(target=make_dummy(), bonus_action_attack=True)
    snap = _make_snapshot({"action": 1, "bonus_action": 1, "reaction": 1})
    choices = policy.decide(snap)
    assert len(choices) == 3
    costs = [c.cost for c in choices]
    assert costs == ["action", "bonus_action", "none"]


def test_policy_no_bonus_attack_when_bonus_action_spent():
    """If the bonus action is already used, don't try to spend it again."""
    policy = ExtraAttackPolicy(target=make_dummy(), bonus_action_attack=True)
    snap = _make_snapshot({"action": 1, "bonus_action": 0, "reaction": 1})
    choices = policy.decide(snap)
    # Only primary + extra, no bonus action
    assert len(choices) == 2
    costs = [c.cost for c in choices]
    assert costs == ["action", "none"]


# ---------------------------------------------------------------------------
# Integration tests (full scheduler run)
# ---------------------------------------------------------------------------

def test_extra_attack_deals_more_damage_than_single():
    """Two guaranteed hits per turn should roughly double damage."""
    single = sum(run_single_attack(seed=1, rounds=20))
    extra = sum(run_extra_attack(seed=1, rounds=20))
    # Extra attack should be meaningfully more — allow some variance but
    # two hits vs one hit on guaranteed-hit runs should be close to 2×.
    assert extra > single * 1.5, f"single={single}, extra={extra}"


def test_extra_attack_total_near_double(rounds=20):
    """Guaranteed-hit run: extra attack total should be roughly 2× single."""
    single = sum(run_single_attack(seed=42, rounds=rounds))
    extra = sum(run_extra_attack(seed=42, rounds=rounds))
    ratio = extra / single if single else float("inf")
    # Allow ±30% of the 2× ideal (crits can skew die counts)
    assert 1.4 <= ratio <= 2.6, f"ratio={ratio:.2f} single={single} extra={extra}"


def test_sim_runs_without_error_extra_attack():
    log = run_extra_attack()
    assert isinstance(log, list)


def test_damage_log_length_equals_rounds():
    log = run_extra_attack(rounds=5)
    assert len(log) == 5


def test_extra_attack_reproducible():
    log_a = run_extra_attack(seed=7)
    log_b = run_extra_attack(seed=7)
    assert log_a == log_b


def test_bonus_action_attack_higher_damage_than_two_attacks():
    """3 guaranteed hits (action + BA + extra) beats 2 hits."""
    two = sum(run_extra_attack(seed=3, rounds=20, extra_attacks=1))
    three = sum(run_extra_attack(seed=3, rounds=20, extra_attacks=1, bonus_action_attack=True))
    assert three > two, f"two={two}, three={three}"
