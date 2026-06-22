"""test_finite_hp_combat.py — the finite-HP enemy / EMERGENT combat-length axis.

The new capacity axis (build-selection-prioritizes-capacity): an OPT-IN combat mode in
which the enemy has real hit points and the combat ENDS the instant the enemy drops,
rather than always running a fixed round count.  Fight LENGTH becomes an emergent output
(``rounds_elapsed`` / ``DayResult.rounds_by_combat``), which is what later unlocks
execute/bloodied thresholds, regain-on-kill, death-procs, and nova-vs-sustain resource
realism.

These tests validate the MECHANISM (validate-mechanism-not-build-value), NOT any build's
DPR number:
  - combat ends when the (single / multi) enemy hits 0 HP, before the round cap;
  - lower HP → fewer rounds; higher damage (nova) → fewer rounds;
  - a too-tough enemy runs to the round cap and no further;
  - the mode is opt-in: default OFF runs the full fixed length (byte-identical intent);
  - each combat in a day faces a FRESH full-HP enemy (per-combat reset);
  - the rules-grounded per-level HP table (baseline_hp) feeds it.
"""

from __future__ import annotations

import logging

from src.builds.enemy_stats import baseline_hp, baseline_hp_midpoint
from src.day_runner import DayRunner
from src.entity import Entity
from src.policy import Choice, GameState
from src.scheduler import Scheduler

logging.disable(logging.CRITICAL)


class StubRNG:
    """Deterministic dice: every d20 == ``d20`` (a hit, non-crit), every other die ==
    ``die``.  So one attack does a fixed, predictable amount and round counts are exact."""

    def __init__(self, d20: int = 18, die: int = 4):
        self._d20 = d20
        self._die = die

    def roll(self, n, sides):
        v = self._d20 if sides == 20 else self._die
        return [v] * n

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


class AttackPolicy:
    """Emits ``n_attacks`` weapon swings per turn at a fixed target (always — even a
    dead one), each rolling ``damage_dice`` + ``damage_bonus``."""

    def __init__(self, target, damage_dice=(1, 6), damage_bonus=3, n_attacks=1):
        self._target = target
        self._dd = damage_dice
        self._db = damage_bonus
        self._n = n_attacks

    def decide(self, snap: GameState):
        if snap.resources.get("action", 0) < 1:
            return []
        return [
            Choice(
                action_type="attack",
                cost="action" if i == 0 else "none",
                target=self._target,
                weapon_stat="attack_bonus",
                damage_dice=self._dd,
                damage_bonus=self._db,
            )
            for i in range(self._n)
        ]


class FirstAlivePolicy:
    """Attacks the first still-alive enemy in a list (for the multi-enemy case)."""

    def __init__(self, targets, damage_dice=(1, 6), damage_bonus=3):
        self._targets = targets
        self._dd = damage_dice
        self._db = damage_bonus

    def decide(self, snap: GameState):
        if snap.resources.get("action", 0) < 1:
            return []
        for t in self._targets:
            if t.hp > 0:
                return [Choice(
                    action_type="attack", cost="action", target=t,
                    weapon_stat="attack_bonus",
                    damage_dice=self._dd, damage_bonus=self._db,
                )]
        return []


def _char() -> Entity:
    # attack_bonus 20 vs the enemy's AC 5 → a d20 of 18 always hits (and is not a crit).
    return Entity(name="hero", hp=100, base_stats={"attack_bonus": 20})


def _enemy(hp) -> Entity:
    return Entity(name="enemy", hp=hp, base_stats={"ac": 5})


def _run_combat(enemy_hp, *, max_rounds=10, enemy_ids_on=True,
                damage_dice=(1, 6), damage_bonus=3, n_attacks=1, die=4):
    """Run ONE combat (hero first in turn order) and return the Scheduler.

    With die=4 / damage_bonus=3, one 1d6+3 swing deals 7; n_attacks scales the
    per-round damage.  enemy_ids_on toggles the finite-HP termination mode."""
    char = _char()
    enemy = _enemy(enemy_hp)
    policy = AttackPolicy(enemy, damage_dice, damage_bonus, n_attacks)
    rng = StubRNG(d20=18, die=die)
    sched = Scheduler(
        rng=rng,
        entities=[char, enemy],
        policies={char.id: policy},
        max_rounds=max_rounds,
        enemy_ids={enemy.id} if enemy_ids_on else None,
    )
    sched.run()
    return sched, char, enemy


# ===========================================================================
# (1) Core termination: combat ends the round the enemy drops
# ===========================================================================

def test_combat_ends_when_enemy_drops_before_the_cap():
    # 7 dmg/round, 20 HP → 13 (r1), 6 (r2), -1 (r3): dead in round 3, well under the cap.
    sched, _char, enemy = _run_combat(20, max_rounds=10)
    assert enemy.hp <= 0
    assert sched.rounds_elapsed == 3
    assert sched.rounds_elapsed < 10
    # The per-round damage log only spans the rounds actually fought.
    assert len(sched._damage_log) == 3


def test_lower_hp_dies_in_fewer_rounds():
    # 7 dmg/round: 10 HP → 3 (r1), -4 (r2): dead in round 2 (fewer than the 20-HP case).
    sched, _c, enemy = _run_combat(10, max_rounds=10)
    assert enemy.hp <= 0
    assert sched.rounds_elapsed == 2


def test_more_damage_kills_faster_nova():
    # Same 20 HP, but a bigger swing (1d12+5; die=8 → 13/round) ends it in round 2 vs the
    # 7/round build's round 3 — the nova-vs-sustain distinction the axis exists to show.
    slow, _c1, _e1 = _run_combat(20, max_rounds=10, damage_dice=(1, 6), damage_bonus=3, die=4)
    fast, _c2, _e2 = _run_combat(20, max_rounds=10, damage_dice=(1, 12), damage_bonus=5, die=8)
    assert fast.rounds_elapsed < slow.rounds_elapsed
    assert (fast.rounds_elapsed, slow.rounds_elapsed) == (2, 3)


# ===========================================================================
# (2) The round cap still bounds a too-tough enemy
# ===========================================================================

def test_tough_enemy_runs_to_the_cap_and_no_further():
    # 7 dmg/round vs 1000 HP never drops it inside the cap → the combat runs exactly
    # max_rounds and stops there (max_rounds stays the safety bound).
    sched, _c, enemy = _run_combat(1000, max_rounds=5)
    assert enemy.hp > 0
    assert sched.rounds_elapsed == 5
    assert len(sched._damage_log) == 5


# ===========================================================================
# (3) The mode is OPT-IN — default OFF runs the full fixed length
# ===========================================================================

def test_mode_off_runs_full_length_even_when_enemy_would_be_dead():
    # enemy_ids OFF: even a 5-HP enemy taking 7/round does not end the combat early —
    # the legacy fixed-length model is preserved (the byte-identical default).
    sched, _c, enemy = _run_combat(5, max_rounds=4, enemy_ids_on=False)
    assert enemy.hp <= 0                 # it "died" on the threshold model
    assert sched.rounds_elapsed == 4     # …but the combat still ran the full 4 rounds
    assert len(sched._damage_log) == 4


# ===========================================================================
# (4) Multi-enemy: combat ends only when ALL opposition is down
# ===========================================================================

def test_combat_continues_until_all_enemies_dead():
    char = _char()
    e1 = _enemy(7)        # dies round 1 (7 dmg)
    e2 = _enemy(7)        # dies round 2
    policy = FirstAlivePolicy([e1, e2])
    rng = StubRNG(d20=18, die=4)
    sched = Scheduler(
        rng=rng,
        entities=[char, e1, e2],
        policies={char.id: policy},
        max_rounds=10,
        enemy_ids={e1.id, e2.id},
    )
    sched.run()
    assert e1.hp <= 0 and e2.hp <= 0
    # e1 dropped in round 1 but the fight continued because e2 was still up.
    assert sched.rounds_elapsed == 2


# ===========================================================================
# (5) DayRunner: each combat faces a FRESH full-HP enemy
# ===========================================================================

def test_each_combat_resets_enemy_to_full_hp():
    char = _char()
    enemy = _enemy(14)            # 7 dmg/round → 2 rounds, every combat
    policy = AttackPolicy(enemy)
    runner = DayRunner(
        rng=StubRNG(d20=18, die=4),
        entities=[char, enemy],
        policies={char.id: policy},
        rounds_per_combat=10,
        enemy_ids={enemy.id},
    )
    result = runner.run_day()
    # If HP did NOT reset, combats 2-4 would start with a dead enemy and end in round 1
    # → [2, 1, 1, 1].  A per-combat reset gives a fresh full-HP enemy every fight.
    assert result.rounds_by_combat == [2, 2, 2, 2]
    assert result.total_rounds == 8


def test_legacy_day_runner_reports_full_length_rounds():
    # Mode off (no enemy_ids): every combat reports the fixed rounds_per_combat.
    char = _char()
    enemy = _enemy(float("inf"))
    policy = AttackPolicy(enemy)
    runner = DayRunner(
        rng=StubRNG(d20=18, die=4),
        entities=[char, enemy],
        policies={char.id: policy},
        rounds_per_combat=4,
    )
    result = runner.run_day()
    assert result.rounds_by_combat == [4, 4, 4, 4]
    assert result.total_rounds == 16


# ===========================================================================
# (6) The rules-grounded per-level HP table feeds the mode
# ===========================================================================

def test_baseline_hp_table_is_dmg_midpoint_and_divisor_applied():
    # Raw values are the verified DMG midpoints; baseline_hp applies the default divisor.
    assert baseline_hp_midpoint(1) == 78
    assert baseline_hp_midpoint(5) == 138
    assert baseline_hp_midpoint(15) == 288
    assert baseline_hp_midpoint(20) == 378
    assert baseline_hp(5) == round(138 / 2.5)          # default HP_DIVISOR == 2.5 → 55
    assert baseline_hp(5, divisor=1.0) == 138          # full-party calibration knob


def test_real_level_hp_yields_a_sane_emergent_length():
    # A level-5 enemy at the table's effective HP (55), against a 1d10+5 swing (die=8 →
    # 13/round): 55 → 42, 29, 16, 3, -10 → dead in round 5.  Inside the cap, > 1 round.
    sched, _c, enemy = _run_combat(
        baseline_hp(5), max_rounds=10, damage_dice=(1, 10), damage_bonus=5, die=8,
    )
    assert enemy.hp <= 0
    assert 1 < sched.rounds_elapsed < 10
    assert sched.rounds_elapsed == 5
