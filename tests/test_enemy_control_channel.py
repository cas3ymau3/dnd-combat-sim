"""test_enemy_control_channel.py — the §6 control-save channel (design/enemy_model.md
§6 / §4b, roadmap step 5).

Validation framing (validate-mechanism-not-build-value): we assert the MECHANISM, never
a DPR value.  Specifically — control saves fire at the band rate; a failed save costs a
turn (hard) or scales output (soft); a `save-ends` control's expected lost-turns scales as
1/s with the character's save (a high-save build recovers in fewer turns); a fixed
duration is capped at the rounds remaining; the ternary action budget's pure-control round
DISPLACES damage (deals zero) while ride-on-top keeps it; a bundled (also-damages) round
forces BOTH a damage save and a control save (visible in both telemetry channels); the
low-CR overflow spills to an independent any-round draw; and control OFF (the default)
restores the exact binary attack/save behavior — zero control activity, no baseline drift.
"""

import logging

import pytest

from src.builds.enemy import BaselineEnemyPolicy
from src.builds.enemy_stats import (
    band_bundled_control_rider,
    band_control_weights,
    band_save_weights,
    enemy_base_stats,
)
from src.entity import Entity
from src.events import ControlSaveEvent
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.telemetry import CombatTelemetry
from src.verbs import resolve_control_save, save_success_prob

logging.disable(logging.CRITICAL)

_ALL_SAVES = {k: 2 for k in
              ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save")}


def _run(level, seed=11, rounds=300, char_saves=None, **kw):
    """Run one control-channel combat and return (total_damage, telemetry)."""
    base = dict(_ALL_SAVES)
    if char_saves:
        base.update(char_saves)
    char = Entity(name="char", hp=10**6, base_stats={"ac": 18, **base})
    enemy = Entity(name="enemy", hp=10**9, base_stats=enemy_base_stats(level))
    pol = BaselineEnemyPolicy(level=level, primary=char, rounds_per_combat=rounds, **kw)
    pol.on_combat_start(0, SeededRNG(seed))
    sched = Scheduler(rng=SeededRNG(seed), entities=[char, enemy],
                      policies={enemy.id: pol}, max_rounds=rounds)
    total = sum(sched.run())
    return total, sched.telemetry


# ---------------------------------------------------------------------------
# save_success_prob — the closed-form s feeding E[turns]
# ---------------------------------------------------------------------------

def test_save_success_prob_formula_and_clamp():
    # needs = dc - bonus; s = (21 - needs)/20.  dc 15, bonus 4 → needs 11 → 10/20 = 0.5
    assert save_success_prob(4, 15) == pytest.approx(0.5)
    # dc 10, bonus 9 → needs 1 → 20/20 = 1.0 (an easy save, ceilinged)
    assert save_success_prob(9, 10) == pytest.approx(1.0)
    # hopeless save floored at 0.05 (keeps 1/s finite; rounds_remaining caps it anyway)
    assert save_success_prob(-100, 30) == pytest.approx(0.05)
    # a huge bonus never exceeds 1.0
    assert save_success_prob(100, 15) == pytest.approx(1.0)


def test_save_success_prob_monotonic_in_bonus():
    dc = 16
    probs = [save_success_prob(b, dc) for b in range(-4, 12)]
    assert probs == sorted(probs)               # more bonus → never lower success


# ---------------------------------------------------------------------------
# resolve_control_save — the closed-form duration math (unit, deterministic)
# ---------------------------------------------------------------------------

def _forced_fail_control(save_bonus, dc, **event_kw):
    """Resolve one control save the target ALWAYS fails (bonus far below the DC → total
    < DC on every d20 — RAW has no nat-20 auto-success on a save), returning the tally."""
    target = Entity(name="t", hp=100, base_stats={"wis_save": save_bonus})
    actor = Entity(name="e", hp=100, base_stats={"enemy_save_dc": dc})
    ev = ControlSaveEvent(tick=(1, 0, 0), actor=actor, target=target,
                          save_stat="wis_save", dc_stat="enemy_save_dc", **event_kw)
    tel = CombatTelemetry()
    resolve_control_save(ev, SeededRNG(1), None, 0, telemetry=tel)
    return tel


def test_short_duration_costs_one_turn():
    tel = _forced_fail_control(-50, 20, hard_frac=1.0,
                               dur_short=1.0, dur_save_ends=0.0, dur_fixed=0.0,
                               rounds_remaining=4)
    ct = tel.control["wis_save"]
    assert ct.failures == 1
    assert ct.turns_lost == pytest.approx(1.0)      # short → exactly one turn
    assert ct.turns_reduced == pytest.approx(0.0)


def test_fixed_duration_capped_at_rounds_remaining():
    tel = _forced_fail_control(-50, 20, hard_frac=1.0,
                               dur_short=0.0, dur_save_ends=0.0, dur_fixed=1.0,
                               rounds_remaining=3)
    assert tel.control["wis_save"].turns_lost == pytest.approx(3.0)   # fixed → cap


def test_save_ends_duration_is_one_over_s_capped():
    # bonus -50 vs DC 20 → s floored at 0.05 → 1/s = 20, capped to rounds_remaining=5.
    tel = _forced_fail_control(-50, 20, hard_frac=1.0,
                               dur_short=0.0, dur_save_ends=1.0, dur_fixed=0.0,
                               rounds_remaining=5)
    assert tel.control["wis_save"].turns_lost == pytest.approx(5.0)


def test_hard_soft_split_by_hard_frac():
    tel = _forced_fail_control(-50, 20, hard_frac=0.25,
                               dur_short=1.0, dur_save_ends=0.0, dur_fixed=0.0,
                               rounds_remaining=4)
    ct = tel.control["wis_save"]
    assert ct.turns_lost == pytest.approx(0.25)     # hard share
    assert ct.turns_reduced == pytest.approx(0.75)  # soft share (both are affected turns)


def test_passed_control_records_the_save_but_no_lost_turns():
    tel = _forced_fail_control(100, 10, hard_frac=1.0,
                               dur_short=1.0, dur_save_ends=0.0, dur_fixed=0.0)  # PASSES
    assert tel.saves[("wis_save", "control")].passed == 1
    assert "wis_save" not in tel.control            # a pass costs nothing


# ---------------------------------------------------------------------------
# End-to-end through the scheduler — the channel fires and prices investment
# ---------------------------------------------------------------------------

def test_control_off_is_the_default_and_has_no_control_activity():
    """The default (control=False) forces zero control saves and loses zero turns, while
    the damaging-save path is untouched — no baseline drift."""
    _dmg, tel = _run(8, control=False, save_round_prob=0.5)
    assert tel.saves_forced("control") == 0
    assert tel.control == {}
    assert tel.saves_forced("damage") > 0           # damage-save path still works


def test_control_fires_control_saves_when_on():
    _dmg, tel = _run(8, control=True, control_save_prob=1.0, save_round_prob=0.0, rounds=50)
    assert tel.saves_forced("control") == 50        # pure control every round


def test_failed_control_costs_lost_turns():
    _dmg, tel = _run(8, control=True, control_save_prob=1.0, save_round_prob=0.0,
                     control_hard_frac=1.0, control_weights={"wis_save": 1},
                     char_saves={"wis_save": 0})
    ct = tel.control["wis_save"]
    assert ct.failures > 0
    assert ct.turns_lost > 0
    assert ct.turns_reduced == pytest.approx(0.0)   # hard_frac=1 → all lost, none reduced


def test_soft_control_reduces_rather_than_loses():
    _dmg, tel = _run(8, control=True, control_save_prob=1.0, save_round_prob=0.0,
                     control_hard_frac=0.0, control_weights={"wis_save": 1},
                     char_saves={"wis_save": 0})
    ct = tel.control["wis_save"]
    assert ct.turns_reduced > 0
    assert ct.turns_lost == pytest.approx(0.0)      # hard_frac=0 → all soft


def test_save_ends_lost_turns_scale_as_one_over_s_with_the_char_save():
    """The whole point of the channel: a good save both FAILS LESS and RECOVERS FASTER
    (save-ends E[turns]=1/s), so a high-save build loses far fewer turns than the fail-rate
    ratio alone — double-pricing mental-save investment."""
    common = dict(control=True, control_save_prob=1.0, save_round_prob=0.0,
                  control_hard_frac=1.0, control_weights={"wis_save": 1},
                  control_duration_mix=(0.0, 1.0, 0.0), rounds=400)  # all save-ends
    _d1, hi = _run(8, char_saves={"wis_save": 10}, **common)
    _d2, lo = _run(8, char_saves={"wis_save": -2}, **common)
    hi_ct, lo_ct = hi.control["wis_save"], lo.control["wis_save"]
    # low-save build fails more...
    assert lo.saves_failed("control") > hi.saves_failed("control")
    # ...and loses turns MORE than proportionally (fail more AND recover slower):
    hi_per_fail = hi_ct.turns_lost / hi_ct.failures
    lo_per_fail = lo_ct.turns_lost / lo_ct.failures
    assert lo_per_fail > hi_per_fail                # slower recovery at the low save


def test_pure_control_displaces_damage_but_ride_keeps_it():
    """§4b: a pure-control round REPLACES the damage action (deals zero) under the default
    displace mode; the ride-on-top toggle keeps the damage and layers control on top."""
    dmg_displace, t_d = _run(8, control=True, control_save_prob=1.0, save_round_prob=0.0)
    dmg_ride, t_r = _run(8, control=True, control_save_prob=1.0, save_round_prob=0.0,
                         control_displacement="ride")
    assert dmg_displace == 0                        # every round is pure control → no damage
    assert t_d.saves_forced("control") > 0
    assert dmg_ride > 0                             # attacks still happen under ride
    assert t_r.saves_forced("control") > 0


def test_bundled_round_forces_both_a_damage_and_a_control_save():
    """A bundled (also-damages) ability's TWO consequences are priced independently — the
    save-for-damage round records a DAMAGE save AND the rider records a CONTROL save, both
    visible (the §4b cross-axis double-save, not netted)."""
    # save rounds only, no pure control → the ONLY control source is the bundled rider.
    _dmg, tel = _run(11, control=True, control_save_prob=0.0, save_round_prob=1.0)
    assert tel.saves_forced("damage") > 0
    assert tel.saves_forced("control") > 0          # bundled rider on the save-dmg rounds


def test_low_cr_overflow_spills_onto_attack_rounds():
    """At band 0-4 the bundled-control mass exceeds the save-for-damage budget it rides on,
    so the overflow spills onto the ATTACK rounds (a bottom-band-only patch): with NO save
    rounds and NO pure control (⇒ every round is an attack round), control still fires at low
    CR but not at higher CR."""
    rider_lo, overflow_lo = band_bundled_control_rider(2)
    rider_hi, overflow_hi = band_bundled_control_rider(8)
    assert overflow_lo > 0 and overflow_hi == 0     # the patch is band-0-4 only
    _d_lo, tel_lo = _run(2, control=True, control_save_prob=0.0, save_round_prob=0.0)
    _d_hi, tel_hi = _run(8, control=True, control_save_prob=0.0, save_round_prob=0.0)
    assert tel_lo.saves_forced("control") > 0       # overflow rides the attack rounds
    assert tel_hi.saves_forced("control") == 0      # no overflow above band 0-4


def test_pure_control_round_never_carries_a_second_control_save():
    """The overflow is gated to ATTACK rounds, so a pure-control round forces EXACTLY ONE
    control save — never a second overflow rider stacked on the same control action (one
    control action = one control save).  At band 0-4 (which HAS overflow), forcing every
    round to be pure control ⇒ control saves == rounds exactly (no extras)."""
    assert band_bundled_control_rider(2)[1] > 0     # band 0-4 has overflow that could stack
    rounds = 300
    _dmg, tel = _run(2, control=True, control_save_prob=1.0, save_round_prob=0.0,
                     rounds=rounds)
    assert tel.saves_forced("control") == rounds    # one per pure-control round, no overflow


def test_overflow_never_lands_on_a_save_round():
    """Overflow rides ATTACK rounds only: with a save forced every round (so there are NO
    attack rounds), the band-0-4 overflow cannot fire — control comes ONLY from the bundled
    rider on those save rounds (≤ one per round), never an extra stacked overflow draw."""
    rounds = 300
    _dmg, tel = _run(2, control=True, control_save_prob=0.0, save_round_prob=1.0,
                     rounds=rounds)
    assert tel.saves_forced("control") <= rounds    # no overflow stacked on save rounds


# ---------------------------------------------------------------------------
# The control save-type mix is DISTINCT from the damaging mix (mental saves)
# ---------------------------------------------------------------------------

def test_control_weights_lift_wis_over_the_damaging_mix():
    """The control channel's whole reason for existing: WIS is a top control save (charm /
    fear / dominate), where the DAMAGING census has WIS near-zero.  So a build's mental-save
    investment is priced by the control weights, not the CON/DEX-dominant damaging ones."""
    for level in (2, 8, 14, 20):
        ctrl = band_control_weights(level)
        dmg = band_save_weights(level)
        assert ctrl.get("wis_save", 0) > 0
        # WIS carries far more weight in the control mix than in the damaging mix
        assert ctrl.get("wis_save", 0) > dmg.get("wis_save", 0)
