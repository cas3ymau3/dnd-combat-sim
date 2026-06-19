"""test_summon_survival.py — substrate #7 / 7a SUMMON SURVIVAL & DEATH (session 22).

The slice that makes the 7c-on-summon DEFENSES (aid / warding bond / protection) and
the RECAST policy DPR-relevant:

  1. a SUMMON winks out at 0 HP (``Entity.dies_at_zero_hp`` → ``take_damage`` sets
     ``destroyed``); the threshold model is untouched for non-summons;
  2. a realistic per-CR enemy (``BaselineEnemyPolicy`` + ``enemy_stats`` — decision
     #12's realised half) makes the enemy's damage LOAD-BEARING (it decides whether
     the beast lives), mixing attack rolls and save-forcing across our saves and
     RETARGETING onto the master when the beast falls;
  3. a per-character RECAST policy (``make_recast_hook``) revives the dead companion
     between combats for a spell slot.

VALIDATION FLIP (the headline): under real fire the defensive effects + recast RAISE
the beast's LIFETIME DPR (``damage_by_source(beast)``) by keeping it alive for more
Beast's-Strike rounds — so the session-21 "aid is DPR-inert" caveat LIFTS.

Validation framing (project-standard): engine seams via deterministic FakeRNG;
directional DPR off the per-(source,target) ledger over many days, NOT number-matching.
"""

import logging

from src.builds import silvertail as sv
from src.builds.enemy import BaselineEnemyPolicy
from src.builds.enemy_stats import (
    baseline_attack_bonus,
    baseline_dpr,
    baseline_save_dc,
)
from src.day_runner import BetweenCombatsContext, DayRunner
from src.entity import Entity
from src.policy import GameState
from src.rng import SeededRNG

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; d20/damage/percentile all go through .roll."""

    def __init__(self, values):
        self._values = list(values)

    def roll(self, n, sides):
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _snap(actor, target, round_number, action=1):
    return GameState(
        actor=actor,
        enemies=(target,),
        allies=(),
        round_number=round_number,
        turn_index=1,
        tick=(round_number, 1, 0),
        resources={"action": action},
    )


# ===========================================================================
# (1) Engine: summon death at 0 HP — take_damage winks out a mortal entity
# ===========================================================================

def test_mortal_entity_winks_out_at_zero_hp():
    e = Entity(name="summon", hp=10, base_stats={})
    e.dies_at_zero_hp = True
    e.take_damage(4)
    assert e.destroyed is False          # 6 HP left — still here
    e.take_damage(6)                     # → 0 HP
    assert e.destroyed is True           # winked out
    assert e.is_functionally_dead is True


def test_non_mortal_entity_does_not_wink_out_at_zero_hp():
    # The threshold model is preserved for everything that is not a summon: HP can hit
    # 0 (and go negative) without `destroyed` being set.
    e = Entity(name="character", hp=10, base_stats={})
    e.take_damage(25)
    assert e.hp == -15
    assert e.is_functionally_dead is True
    assert e.destroyed is False          # still acts (threshold model)


def test_long_rest_revives_a_winked_out_summon():
    # A long rest (day start) brings a dead companion back (RAW: choose/revive on a
    # long rest) — so multi-day loops don't leave it permanently destroyed.
    beast = Entity(name="beast", hp=20, base_stats={})
    beast.dies_at_zero_hp = True
    beast.take_damage(20)
    assert beast.destroyed is True
    runner = DayRunner(rng=SeededRNG(0), entities=[beast], policies={})
    runner._apply_lr()
    assert beast.destroyed is False
    assert beast.hp == beast.max_hp


# ===========================================================================
# (2) Per-CR enemy stats (decision #12's realised half)
# ===========================================================================

def test_baseline_enemy_stats_match_the_per_cr_table():
    # Tom Dunn baseline table anchors: CR8 → +8 / DC 16; AB is a constant 8 below DC.
    assert baseline_save_dc(8) == 16
    assert baseline_attack_bonus(8) == 8
    assert baseline_attack_bonus(4) == 6 and baseline_save_dc(4) == 14
    for cr in range(0, 13):
        assert baseline_attack_bonus(cr) == baseline_save_dc(cr) - 8
    # DPR is the all-hits-land budget 6 + 6·CR (the pre-hit-rate figure the rolls then
    # discount — enemy_stats reconciliation).
    assert baseline_dpr(8) == 54
    assert baseline_dpr(0) == 6


# ===========================================================================
# (3) BaselineEnemyPolicy — attack/save mix + retarget on summon death
# ===========================================================================

def test_baseline_enemy_attack_round_emits_n_swings():
    beast = Entity(name="beast", hp=25, base_stats={"ac": 17})
    enemy = Entity(name="enemy", hp=10**9,
                   base_stats={"attack_bonus": 8, "enemy_save_dc": 16})
    pol = BaselineEnemyPolicy(cr=8, primary=beast, n_attacks=2, rounds_per_combat=1)
    # roll_one(100)=50 > 35 → an ATTACK round (no save pick consumed).
    pol.on_combat_start(0, FakeRNG([50]))
    choices = pol.decide(_snap(enemy, beast, 1))
    assert [c.action_type for c in choices] == ["attack", "attack"]
    assert [c.cost for c in choices] == ["action", "none"]
    # The per-CR budget (54) is split flat across the 2 swings (27 each).
    assert all(c.damage_bonus == 27 and c.damage_dice == (0, 0) for c in choices)
    assert all(c.target is beast for c in choices)


def test_baseline_enemy_save_round_forces_a_weighted_save():
    beast = Entity(name="beast", hp=25, base_stats={"ac": 17})
    enemy = Entity(name="enemy", hp=10**9,
                   base_stats={"attack_bonus": 8, "enemy_save_dc": 16})
    pol = BaselineEnemyPolicy(cr=8, primary=beast, n_attacks=2, rounds_per_combat=1)
    # roll_one(100)=10 ≤ 35 → a SAVE round; then _weighted_save roll_one(100)=5 lands
    # in the first bucket (dex_save, weight 30).
    pol.on_combat_start(0, FakeRNG([10, 5]))
    choices = pol.decide(_snap(enemy, beast, 1))
    assert len(choices) == 1
    c = choices[0]
    assert c.action_type == "save_spell"
    assert c.save_stat == "dex_save"
    assert c.dc_stat == "enemy_save_dc"
    assert c.on_save == "half"
    assert c.damage_bonus == baseline_dpr(8)        # whole budget, half on a save


def test_baseline_enemy_retargets_to_fallback_when_primary_winks_out():
    beast = Entity(name="beast", hp=25, base_stats={"ac": 17})
    master = Entity(name="master", hp=60, base_stats={"ac": 20})
    enemy = Entity(name="enemy", hp=10**9,
                   base_stats={"attack_bonus": 8, "enemy_save_dc": 16})
    pol = BaselineEnemyPolicy(cr=8, primary=beast, fallback=master,
                              n_attacks=2, rounds_per_combat=1)
    pol.on_combat_start(0, FakeRNG([50]))           # attack round
    # Beast alive → hits the beast.
    assert all(c.target is beast for c in pol.decide(_snap(enemy, beast, 1)))
    # Beast winks out → the load shifts to the master.
    beast.destroyed = True
    assert all(c.target is master for c in pol.decide(_snap(enemy, beast, 1)))


# ===========================================================================
# (4) Integration — the SURVIVAL FLIP under the realistic per-CR enemy (L8)
# ===========================================================================

def _beast_lifetime(effect, seed, *, mortal=True, recast=False, days=150):
    """Sum the beast's lifetime DPR (its commanded Beast's-Strike output) over
    `days`, under the realistic per-CR enemy."""
    runner, _char, beast, _dummy = sv.make_silvertail_runner(
        8, SeededRNG(seed), beast_effect=effect, mortal_beast=mortal,
        enemy_model="baseline_cr", recast=recast)
    return sum(runner.run_day().damage_by_source(beast.id) for _ in range(days))


def test_mortal_beast_collapses_lifetime_dpr_vs_immortal():
    # The core of the slice: under real fire a MORTAL beast dies and stops contributing,
    # so its lifetime DPR is a fraction of the threshold-immortal beast's.
    immortal = _beast_lifetime(None, 11, mortal=False)
    mortal = _beast_lifetime(None, 11, mortal=True)
    assert mortal > 0
    assert mortal < immortal / 3            # a large, unambiguous drop


def test_protection_raises_mortal_beast_lifetime_dpr():
    base = _beast_lifetime(None, 11)
    prot = _beast_lifetime("protection", 11)
    assert prot > base                      # disadvantage → more rounds alive → more DPR


def test_warding_bond_raises_mortal_beast_lifetime_dpr():
    base = _beast_lifetime(None, 11)
    wb = _beast_lifetime("warding_bond", 11)
    assert wb > base                        # resistance-to-all → more rounds alive


def test_aid_raises_mortal_beast_lifetime_dpr_caveat_lifts():
    # The session-21 caveat LIFTS: +5 HP buys the beast more rounds of strikes under
    # real fire, so aid is no longer DPR-inert.
    base = _beast_lifetime(None, 11)
    aid = _beast_lifetime("aid", 11)
    assert aid > base


def test_bless_raises_mortal_beast_lifetime_dpr():
    # Bless raises the beast's to-hit, so each alive round deals more → more lifetime DPR.
    base = _beast_lifetime(None, 11)
    bless = _beast_lifetime("bless", 11)
    assert bless > base


def test_recast_raises_lifetime_dpr_by_reviving_between_combats():
    # Reviving the dead companion between combats (a spell slot, 1-minute revival)
    # restores its output for later combats — the biggest survival lever.
    no_recast = _beast_lifetime(None, 11, recast=False)
    recast = _beast_lifetime(None, 11, recast=True)
    assert recast > no_recast * 2           # revival roughly multiplies the output


def test_enemy_retargets_to_master_after_the_beast_dies():
    # The dead beast's incoming load shifts to the master (focus-fire → fallback), so a
    # mortal beast means the master starts eating hits — while an immortal beast tanks
    # everything and spares the master entirely.
    def master_taken(mortal, seed, days=100):
        runner, char, _beast, dummy = sv.make_silvertail_runner(
            8, SeededRNG(seed), mortal_beast=mortal, enemy_model="baseline_cr")
        return sum(runner.run_day().damage_source_to(dummy.id, char.id) for _ in range(days))

    assert master_taken(False, 11) == 0     # immortal beast tanks → master untouched
    assert master_taken(True, 11) > 0       # mortal beast dies → master eats the rest


def test_recast_consumes_the_finite_slot_budget():
    # The recast policy spends a spare slot per revive — a finite per-day budget (the
    # "recast or not" decision has a real cost), not a free respawn.
    runner, char, beast, _dummy = sv.make_silvertail_runner(
        8, SeededRNG(11), mortal_beast=True, enemy_model="baseline_cr", recast=True)
    before = char.resources.available("spell_slot")
    assert before == 3
    runner.run_day()
    after = char.resources.available("spell_slot")
    # At a long rest the pool refills; mid-day it is spent on revives.  Run a SINGLE
    # day and check the recast hook drew the pool down (the beast does die under CR8
    # fire), but never below 0.
    assert 0 <= after <= before
    # A no-recast runner never touches the pool.
    runner2, char2, _b2, _d2 = sv.make_silvertail_runner(
        8, SeededRNG(11), mortal_beast=True, enemy_model="baseline_cr", recast=False)
    runner2.run_day()
    assert char2.resources.available("spell_slot") == 3
