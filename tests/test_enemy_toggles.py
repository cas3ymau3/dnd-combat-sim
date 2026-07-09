"""test_enemy_toggles.py — the §7 sensitivity-analysis toggles (design/enemy_model.md
§7, roadmap step 6): CR-band override, incoming damage-type mix (+ the already-free
force-mode), and legendary cadence.

Validation framing (validate-mechanism-not-build-value): each toggle FLIPS the
corresponding behavior and defaults OFF/None to the exact prior behavior (no baseline
drift). We do not assert any DPR value.
"""

import logging

import pytest

from src.builds import enemy as enemy_module
from src.builds import enemy_stats
from src.builds.enemy import BaselineEnemyPolicy
from src.builds.enemy_stats import (
    band_control_save_prob,
    band_damage_multiplier,
    band_damage_type_mix,
    band_for_level,
    band_legendary_cadence,
    band_save_round_prob,
    enemy_base_stats,
)
from src.entity import Entity
from src.policy import GameState
from src.rng import SeededRNG

logging.disable(logging.CRITICAL)

_BAND_LEVEL = {"0-4": 2, "5-10": 7, "11-16": 13, "17+": 18}


def _snapshot(actor, target, round_number):
    return GameState(
        actor=actor,
        enemies=(target,),
        allies=(),
        round_number=round_number,
        turn_index=1,
        tick=(round_number, 1, 0),
        resources={"action": 1, "bonus_action": 1, "reaction": 1},
    )


def _make(level, rounds=20, seed=7, **kw):
    """A BaselineEnemyPolicy + its target/actor entities, pre-rolled and ready to
    decide() round by round."""
    target = Entity(name="char", hp=10**6, base_stats={"ac": 5})
    enemy = Entity(name="enemy", hp=10**9, base_stats=enemy_base_stats(level))
    pol = BaselineEnemyPolicy(level=level, primary=target, rounds_per_combat=rounds, **kw)
    pol.on_combat_start(0, SeededRNG(seed))
    return pol, enemy, target


def _decide_all_rounds(pol, enemy, target, rounds):
    return [pol.decide(_snapshot(enemy, target, r)) for r in range(1, rounds + 1)]


# ---------------------------------------------------------------------------
# CR-band override — every band_*() accessor accepts an explicit band
# ---------------------------------------------------------------------------

def test_band_accessors_override_independent_of_level():
    """A low level (band 0-4) with band='17+' reads the SAME mix a level-18 char
    would get natively — the level→band join is bypassed, not just re-derived."""
    lvl2, band17 = 2, "17+"
    assert band_save_round_prob(lvl2, band=band17) == pytest.approx(
        band_save_round_prob(_BAND_LEVEL["17+"]))
    assert band_damage_multiplier(lvl2, "fire", band=band17) == pytest.approx(
        band_damage_multiplier(_BAND_LEVEL["17+"], "fire"))
    assert band_legendary_cadence(lvl2, band=band17) == band_legendary_cadence(
        _BAND_LEVEL["17+"])
    # And band=None (default) is byte-identical to the plain level→band join.
    assert band_save_round_prob(lvl2) == pytest.approx(
        band_save_round_prob(lvl2, band=band_for_level(lvl2)))


def test_policy_band_override_reaches_every_band_lookup():
    """band_override threaded through BaselineEnemyPolicy's constructor changes the
    save/control/legendary mix to the OVERRIDDEN band's, not the level's own band."""
    pol_native, _, _ = _make(2, control=True)                       # band 0-4
    pol_override, _, _ = _make(2, control=True, band_override="17+",
                                legendary_cadence=True)
    assert pol_native._band is None
    assert pol_override._band == "17+"
    # Band 0-4's control_save_prob differs from 17+'s (grounded in the census).
    assert pol_override._control_prob_pct != int(round(
        band_control_save_prob(2) * 100))
    assert pol_override._control_prob_pct == int(round(
        band_control_save_prob(2, band="17+") * 100))
    # Legendary cadence at native band 0-4 is 0 (no-op); at the 17+ override it isn't.
    assert pol_override._legendary_swings == band_legendary_cadence(2, band="17+")
    assert pol_override._legendary_swings > 0


# ---------------------------------------------------------------------------
# Incoming damage-type mix — OFF = no drift, ON = per-round empirical draw
# ---------------------------------------------------------------------------

def test_damage_type_mix_off_keeps_the_fixed_scalar():
    """Default OFF: every round's damage_type is exactly the fixed `damage_type` arg
    (None here = untyped, the legacy behavior) — no empirical draw happens."""
    pol, enemy, target = _make(13, rounds=30, damage_type=None)
    for choices in _decide_all_rounds(pol, enemy, target, 30):
        for c in choices:
            assert c.damage_type is None
    assert pol._round_damage_type == {}


def test_damage_type_mix_on_draws_from_band_empirical_weights(monkeypatch):
    """ON: a single-type band mix (isolating the mechanism, not fitting a distribution)
    makes EVERY round's damage_type that one type, deterministically."""
    monkeypatch.setattr(enemy_module, "band_damage_type_mix",
                         lambda level, band=None: {"radiant": 1})
    pol, enemy, target = _make(13, rounds=15, damage_type_mix=True)
    assert pol._type_weights == {"radiant": 1}
    saw_any = False
    for choices in _decide_all_rounds(pol, enemy, target, 15):
        for c in choices:
            if c.action_type in ("attack", "save_spell"):
                assert c.damage_type == "radiant"
                saw_any = True
    assert saw_any


def test_damage_type_mix_on_draws_multiple_types_from_real_band_table():
    """ON with the real (non-monkeypatched) band table: across many rounds, more than
    one damage type shows up (the mix is genuinely weighted, not collapsed to one)."""
    pol, enemy, target = _make(17, rounds=200, damage_type_mix=True)
    seen = set()
    for choices in _decide_all_rounds(pol, enemy, target, 200):
        for c in choices:
            if c.action_type in ("attack", "save_spell"):
                seen.add(c.damage_type)
    assert len(seen) > 1
    # Every observed type actually has nonzero weight in the band's mix.
    weights = band_damage_type_mix(17)
    assert seen <= set(weights)


def test_force_mode_already_reachable_via_fixed_damage_type():
    """§7's force-damage-mode row is just damage_type="force" on the existing scalar —
    no new toggle needed.  Regression: force has no res/imm/vuln prevalence columns, so
    mult(t) is 1.0 in every band (the isolating property force-mode relies on)."""
    pol, enemy, target = _make(7, rounds=10, damage_type="force")
    for choices in _decide_all_rounds(pol, enemy, target, 10):
        for c in choices:
            if c.action_type in ("attack", "save_spell"):
                assert c.damage_type == "force"
    for band in ("0-4", "5-10", "11-16", "17+"):
        assert band_damage_multiplier(_BAND_LEVEL[band], "force") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Legendary cadence — OFF = no-op, ON = a deterministic per-round swing bump
# ---------------------------------------------------------------------------

def test_legendary_cadence_off_never_adds_swings():
    pol, enemy, target = _make(18, rounds=12, legendary_cadence=False)
    assert pol._legendary_swings == 0
    baseline_counts = [len(c) for c in _decide_all_rounds(pol, enemy, target, 12)]

    pol2, enemy2, target2 = _make(18, rounds=12)   # legendary_cadence defaults False
    default_counts = [len(c) for c in _decide_all_rounds(pol2, enemy2, target2, 12)]
    assert baseline_counts == default_counts


def test_legendary_cadence_on_adds_exactly_n_swings_every_round(monkeypatch):
    """A monkeypatched cadence of 2 adds exactly 2 extra cost='none' attack Choices to
    EVERY round, regardless of whether that round was an attack/save/control round."""
    monkeypatch.setattr(enemy_module, "band_legendary_cadence", lambda level, band=None: 2)
    pol_off, enemy_off, target_off = _make(2, rounds=20, control=True)
    pol_on, enemy_on, target_on = _make(2, rounds=20, control=True, legendary_cadence=True)
    assert pol_on._legendary_swings == 2

    off_rounds = _decide_all_rounds(pol_off, enemy_off, target_off, 20)
    on_rounds = _decide_all_rounds(pol_on, enemy_on, target_on, 20)
    for off_choices, on_choices in zip(off_rounds, on_rounds):
        assert len(on_choices) == len(off_choices) + 2
        extra = on_choices[len(off_choices):]
        assert all(c.action_type == "attack" and c.cost == "none" for c in extra)


def test_legendary_cadence_is_a_noop_at_low_bands():
    """The real (non-monkeypatched) band table rounds to 0 extra swings at 0-4/5-10 —
    confirming the documented 'near-zero at low CR' claim, turning ON is inert there."""
    for level in (_BAND_LEVEL["0-4"], _BAND_LEVEL["5-10"]):
        assert band_legendary_cadence(level) == 0
        pol_off, enemy_off, target_off = _make(level, rounds=8)
        pol_on, enemy_on, target_on = _make(level, rounds=8, legendary_cadence=True)
        off_counts = [len(c) for c in _decide_all_rounds(pol_off, enemy_off, target_off, 8)]
        on_counts = [len(c) for c in _decide_all_rounds(pol_on, enemy_on, target_on, 8)]
        assert off_counts == on_counts
