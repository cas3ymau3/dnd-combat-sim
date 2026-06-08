"""
test_scripted_enemy.py — Scripted enemy milestone tests.

Validates:
  - ScriptedEnemyPolicy produces attack choices against the character
  - Both sides act for the full max_rounds regardless of HP (threshold model)
  - Character takes incoming damage (damage_received log is populated)
  - is_functionally_dead fires when cumulative damage exceeds max_hp
  - HP can go negative (no clamp)
  - Entities still act after HP goes negative
"""

import math
import pytest

from src.entity import Entity
from src.policy import ExtraAttackPolicy, GameState, ScriptedEnemyPolicy
from src.rng import SeededRNG
from src.scheduler import Scheduler


# ---------------------------------------------------------------------------
# Stat blocks
# ---------------------------------------------------------------------------

LEVEL_5_ENEMY = {
    "attack_bonus": 5,
    "damage_dice": (1, 8),
    "damage_bonus": 3,
    "ac": 13,
}


def make_fighter(hp=52, attack_bonus=7, damage_dice=(1, 8), damage_bonus=4, ac=16):
    return Entity(
        name="Fighter",
        hp=hp,
        base_stats={
            "attack_bonus": attack_bonus,
            "damage_dice": damage_dice,
            "damage_bonus": damage_bonus,
            "ac": ac,
        },
    )


def make_enemy(stat_block=None, hp=52):
    sb = stat_block or LEVEL_5_ENEMY
    return Entity(
        name="Enemy",
        hp=hp,
        base_stats=sb,
    )


def run_two_sided(seed=42, rounds=4, fighter_hp=52, enemy_hp=52):
    fighter = make_fighter(hp=fighter_hp)
    enemy = make_enemy(hp=enemy_hp)
    rng = SeededRNG(seed=seed)
    fighter_policy = ExtraAttackPolicy(target=enemy)
    enemy_policy = ScriptedEnemyPolicy(stat_block=LEVEL_5_ENEMY)
    scheduler = Scheduler(
        rng=rng,
        entities=[fighter, enemy],
        policies={fighter.id: fighter_policy, enemy.id: enemy_policy},
        max_rounds=rounds,
    )
    damage_log = scheduler.run()
    return scheduler, fighter, enemy, damage_log


# ---------------------------------------------------------------------------
# ScriptedEnemyPolicy unit tests
# ---------------------------------------------------------------------------

def test_enemy_policy_attacks_first_enemy():
    enemy_entity = make_enemy()
    fighter = make_fighter()
    policy = ScriptedEnemyPolicy(stat_block=LEVEL_5_ENEMY)
    snap = GameState(
        actor=enemy_entity,
        enemies=(fighter,),
        allies=(),
        round_number=1,
        turn_index=1,
        tick=(1, 1, 0),
        resources={"action": 1, "bonus_action": 1, "reaction": 1},
    )
    choices = policy.decide(snap)
    assert len(choices) == 1
    assert choices[0].cost == "action"
    assert choices[0].target is fighter


def test_enemy_policy_no_choices_without_action():
    enemy_entity = make_enemy()
    fighter = make_fighter()
    policy = ScriptedEnemyPolicy(stat_block=LEVEL_5_ENEMY)
    snap = GameState(
        actor=enemy_entity,
        enemies=(fighter,),
        allies=(),
        round_number=1,
        turn_index=1,
        tick=(1, 1, 0),
        resources={"action": 0},
    )
    assert policy.decide(snap) == []


def test_enemy_policy_no_choices_without_targets():
    enemy_entity = make_enemy()
    policy = ScriptedEnemyPolicy(stat_block=LEVEL_5_ENEMY)
    snap = GameState(
        actor=enemy_entity,
        enemies=(),
        allies=(),
        round_number=1,
        turn_index=1,
        tick=(1, 1, 0),
        resources={"action": 1},
    )
    assert policy.decide(snap) == []


def test_enemy_policy_multi_attack():
    enemy_entity = make_enemy()
    fighter = make_fighter()
    policy = ScriptedEnemyPolicy(stat_block=LEVEL_5_ENEMY, extra_attacks=1)
    snap = GameState(
        actor=enemy_entity,
        enemies=(fighter,),
        allies=(),
        round_number=1,
        turn_index=1,
        tick=(1, 1, 0),
        resources={"action": 1, "bonus_action": 1, "reaction": 1},
    )
    choices = policy.decide(snap)
    assert len(choices) == 2
    assert choices[0].cost == "action"
    assert choices[1].cost == "none"


def test_enemy_policy_rejects_unknown_archetype():
    with pytest.raises(ValueError, match="Unknown archetype"):
        ScriptedEnemyPolicy(stat_block=LEVEL_5_ENEMY, archetype="flanking_rogue")


# ---------------------------------------------------------------------------
# Entity HP threshold model
# ---------------------------------------------------------------------------

def test_hp_can_go_negative():
    e = make_fighter(hp=10)
    e.take_damage(20)
    assert e.hp == -10


def test_is_functionally_dead_at_zero():
    e = make_fighter(hp=10)
    e.take_damage(10)
    assert e.is_functionally_dead


def test_is_functionally_dead_below_zero():
    e = make_fighter(hp=10)
    e.take_damage(15)
    assert e.is_functionally_dead


def test_not_functionally_dead_above_zero():
    e = make_fighter(hp=10)
    e.take_damage(9)
    assert not e.is_functionally_dead


# ---------------------------------------------------------------------------
# Integration: two-sided combat
# ---------------------------------------------------------------------------

def test_two_sided_sim_runs_without_error():
    scheduler, fighter, enemy, log = run_two_sided()
    assert isinstance(log, list)


def test_damage_log_has_entry_per_round():
    scheduler, fighter, enemy, log = run_two_sided(rounds=4)
    assert len(log) == 4


def test_fighter_takes_incoming_damage():
    """Enemy's attacks should register in the fighter's damage_received log."""
    scheduler, fighter, enemy, log = run_two_sided(seed=1, rounds=4)
    fighter_received = scheduler.damage_received[fighter.id]
    assert len(fighter_received) == 4
    assert sum(fighter_received) > 0, "Fighter should take at least some damage"


def test_enemy_takes_outgoing_damage():
    """Fighter's attacks should register in the enemy's damage_received log."""
    scheduler, fighter, enemy, log = run_two_sided(seed=1, rounds=4)
    enemy_received = scheduler.damage_received[enemy.id]
    assert sum(enemy_received) > 0, "Enemy should take at least some damage"


def test_both_sides_act_full_rounds_even_with_low_hp():
    """Both entities act all 4 rounds even if HP would go very negative."""
    scheduler, fighter, enemy, log = run_two_sided(
        seed=42, rounds=4, fighter_hp=1, enemy_hp=1
    )
    # If both sides act every round, the fighter deals damage every round
    # (guaranteed-hit config is not used here, but at least the log length
    # confirms the sim ran to completion without short-circuiting)
    assert len(log) == 4


def test_fighter_hp_can_go_negative_during_sim():
    """With very low fighter HP, HP should go negative rather than clamping."""
    scheduler, fighter, enemy, log = run_two_sided(
        seed=1, rounds=4, fighter_hp=1, enemy_hp=999
    )
    # Fighter likely accumulated more than 1 HP worth of damage
    total_received = sum(scheduler.damage_received[fighter.id])
    if total_received > 1:
        assert fighter.hp < 0, f"Expected negative HP, got {fighter.hp}"


def test_two_sided_reproducible():
    s1, _, _, log1 = run_two_sided(seed=99)
    s2, _, _, log2 = run_two_sided(seed=99)
    assert log1 == log2
