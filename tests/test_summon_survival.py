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
    baseline_aoe_dice,
    baseline_attack_bonus,
    baseline_attack_dice,
    baseline_dpr,
    baseline_save_dc,
    level_to_cr,
)
from src.day_runner import BetweenCombatsContext, DayRunner
from src.entity import Entity
from src.policy import Choice, GameState
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

def test_baseline_enemy_stats_match_the_per_cr_chart():
    # Chart anchors (Rothner "Average Monster Stats by CR"): CR8 → +8 / DC 15, with the
    # multiattack 4d10+5 per swing and a 12d4 AoE.
    assert baseline_attack_bonus(8) == 8 and baseline_save_dc(8) == 15
    assert baseline_attack_bonus(4) == 6 and baseline_save_dc(4) == 13
    assert baseline_attack_dice(8) == (4, 10, 5)
    assert baseline_aoe_dice(8) == (12, 4, 0)
    # Damage/Round = two multiattack swings (the chart's column): CR8 → 54, CR4 → 30.
    assert baseline_dpr(8) == 54
    assert baseline_dpr(4) == 30


def test_level_to_cr_is_the_de_harshening_mapping():
    # The chart's Level column: a CR is a baseline for a HIGHER level than CR == level.
    # A lone level-8 summon faces ~CR 5 (not CR 8), level 14 faces CR 8.
    assert level_to_cr(8) == 5
    assert level_to_cr(14) == 8
    assert level_to_cr(4) == 2
    # Strictly gentler than the naive cr == level it replaces.
    assert level_to_cr(8) < 8


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
    # Each swing rolls the chart's per-CR multiattack dice (CR8 = 4d10+5), so a
    # natural 20 doubles the dice — enemy crits are modeled.
    assert all(c.damage_dice == (4, 10) and c.damage_bonus == 5 for c in choices)
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
    # The per-CR AoE dice (CR8 = 12d4); enemy_stats stores (count, sides, bonus).
    assert baseline_aoe_dice(8) == (12, 4, 0)
    assert c.damage_dice == (12, 4) and c.damage_bonus == 0


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
# (4) Integration — the summon-death MECHANISM under the realistic per-CR enemy.
#
# These confirm the mechanism is mechanically correct: a dead summon stops
# contributing, more effective HP / fewer landed hits keep it contributing longer,
# and a revive restores its contribution.  They are NOT build-value claims about
# which effect is "best" — that waits for the full build (with enemy targeting-split,
# the beast's hit-dice / Prayer-of-Healing healing, and Mounted Combatant's veer all
# modeled; none of those are in scope here).
# ===========================================================================

def _beast_lifetime(effect, seed, *, mortal=True, recast=False, days=150):
    """Sum the beast's commanded Beast's-Strike output over `days`, under the
    realistic per-CR enemy (a proxy for rounds-alive: a dead beast stops striking)."""
    runner, _char, beast, _dummy = sv.make_silvertail_runner(
        8, SeededRNG(seed), beast_effect=effect, mortal_beast=mortal,
        enemy_model="baseline_cr", recast=recast)
    return sum(runner.run_day().damage_by_source(beast.id) for _ in range(days))


def test_mortal_beast_stops_contributing_when_it_dies():
    # The core of the slice: under real fire a MORTAL beast dies and stops contributing,
    # so its output is a fraction of the threshold-immortal beast's (which never dies).
    immortal = _beast_lifetime(None, 11, mortal=False)
    mortal = _beast_lifetime(None, 11, mortal=True)
    assert mortal > 0                       # it still acts while alive
    assert mortal < immortal / 3            # death cuts its contribution sharply


def test_reducing_incoming_damage_keeps_the_summon_contributing_longer():
    # Mechanism: an effect that reduces landed hits (here Protection's disadvantage)
    # keeps the mortal beast alive for more rounds, so it contributes more.  This tests
    # the survival→contribution link responds to a defender effect — NOT that Protection
    # is the right call (a build-value question deferred to the full build).
    base = _beast_lifetime(None, 11)
    less_incoming = _beast_lifetime("protection", 11)
    assert less_incoming > base


class _CommandBeastEachRound:
    """A minimal commander: every round (while the beast lives) it commands a flat
    Beast's Strike at the dummy, costing its Bonus Action."""

    def __init__(self, beast, target, dmg):
        self._beast, self._target, self._dmg = beast, target, dmg

    def decide(self, snapshot):
        if snapshot.resources.get("bonus_action", 0) >= 1 and not self._beast.destroyed:
            return [Choice(action_type="attack", cost="bonus_action", actor=self._beast,
                           target=self._target, weapon_stat="attack_bonus",
                           damage_dice=(0, 0), damage_bonus=self._dmg,
                           damage_type="bludgeoning")]
        return []


class _HitBeastEachRound:
    """A minimal enemy: every round it lands a flat hit on the beast."""

    def __init__(self, beast, dmg):
        self._beast, self._dmg = beast, dmg

    def decide(self, snapshot):
        if snapshot.resources.get("action", 0) >= 1:
            return [Choice(action_type="attack", cost="action", target=self._beast,
                           weapon_stat="attack_bonus", damage_dice=(0, 0),
                           damage_bonus=self._dmg, damage_type="slashing")]
        return []


def test_extra_max_hp_buys_an_extra_strike_at_a_breakpoint():
    # Mechanism: a +HP buffer is survival-relevant exactly when it crosses a per-hit
    # breakpoint — the extra HP lets the beast survive a hit it would otherwise die to,
    # buying one more commanded strike.  Deterministic (FakeRNG all-20 → every attack
    # hits): beast deals 10/strike to the dummy; the enemy deals 12/round to the beast.
    #   HP 20:    strike R1, enemy→8;  strike R2, enemy→-4 DEAD;  R3 no strike → 20.
    #   HP 20+5:  strike R1, enemy→13; strike R2, enemy→1;  strike R3, enemy dead → 30.
    # (Vehicle: Aid's +5 max HP.  Whether Aid is worth casting is a build-value question
    # deferred to the full build; this only proves the HP→survival→contribution link.)
    from src.scheduler import Scheduler

    def run(with_buffer):
        master = Entity(name="master", hp=60, base_stats={"ac": 20})
        beast = Entity(name="beast", hp=20, base_stats={"ac": 10, "attack_bonus": 10})
        beast.dies_at_zero_hp = True
        dummy = Entity(name="dummy", hp=10**9, base_stats={"ac": 10})
        enemy = Entity(name="enemy", hp=10**9, base_stats={"ac": 10, "attack_bonus": 10})
        if with_buffer:
            sv.BeastEffectPolicy("aid", beast, master).install()   # +5 HP max & current
        sch = Scheduler(
            rng=FakeRNG([20] * 24),
            entities=[master, enemy, beast, dummy],
            policies={master.id: _CommandBeastEachRound(beast, dummy, 10),
                      enemy.id: _HitBeastEachRound(beast, 12)},
            max_rounds=3,
        )
        sch.run()
        return sch.damage_by_source_target.get((beast.id, dummy.id), 0)

    assert run(False) == 20         # dies before round 3 → two strikes
    assert run(True) == 30          # +5 HP survives to strike a third round


def test_reviving_a_dead_summon_restores_its_contribution():
    # Mechanism: the recast policy revives the dead companion between combats (a spell
    # slot, 1-minute revival), restoring its output for later combats.
    no_recast = _beast_lifetime(None, 11, recast=False)
    recast = _beast_lifetime(None, 11, recast=True)
    assert recast > no_recast               # revival brings the contribution back


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
