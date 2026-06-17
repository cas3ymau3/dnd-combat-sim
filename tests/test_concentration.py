"""Tests for the saving-throw verb and the concentration-on-damage loop (D3b).

Covers:
  - resolve_saving_throw: pass/fail vs DC, advantage, Bless's +1d4 fold.
  - _check_concentration: a concentrating entity taking damage forces a CON
    save (DC = max(10, dmg//2)); a failure drops the spell's modifiers and
    clears concentration; a success keeps them; Brutality::bluff's
    advantage_next_save is consumed by the check.
"""

import logging

from src.entity import Entity
from src.events import DamageEvent
from src.modifiers import Modifier
from src.rng import SeededRNG
from src.verbs import resolve_saving_throw, resolve_damage

logging.disable(logging.CRITICAL)


def _con_saver(bonus: int) -> Entity:
    return Entity(name="Saver", hp=50, base_stats={"con_save": bonus})


# ---------------------------------------------------------------------------
# resolve_saving_throw
# ---------------------------------------------------------------------------

def test_save_trivial_dc_always_passes():
    e = _con_saver(0)
    # DC 1: d20 (>=1) + 0 >= 1 always.
    assert resolve_saving_throw(e, "con_save", dc=1, rng=SeededRNG(0)) is True


def test_save_impossible_dc_always_fails():
    e = _con_saver(0)
    # DC 100: d20 (<=20) + 0 can never reach it.
    assert resolve_saving_throw(e, "con_save", dc=100, rng=SeededRNG(0)) is False


def test_bless_dice_raise_the_save():
    """At a borderline DC, adding Bless's +1d4 can only help, never hurt."""
    base = _con_saver(10)
    blessed = _con_saver(10)
    blessed.add_modifier(Modifier("con_save", 0, "bless", dice=(1, 4)))
    # DC 15 with +10: base needs d20>=5 (80%); blessed needs d20 >= 5-1d4 (more).
    n = 4000
    base_pass = sum(resolve_saving_throw(base, "con_save", 15, SeededRNG(s)) for s in range(n))
    blessed_pass = sum(resolve_saving_throw(blessed, "con_save", 15, SeededRNG(s)) for s in range(n))
    assert blessed_pass > base_pass


def test_advantage_helps_on_average():
    n = 3000
    straight = sum(resolve_saving_throw(_con_saver(0), "con_save", 15, SeededRNG(s))
                   for s in range(n))
    adv = sum(resolve_saving_throw(_con_saver(0), "con_save", 15, SeededRNG(s), advantage=True)
              for s in range(n))
    assert adv > straight


# ---------------------------------------------------------------------------
# _check_concentration via resolve_damage
# ---------------------------------------------------------------------------

def _concentrating_target(con_save: int) -> Entity:
    """An entity concentrating on Bless (its modifier present), to be damaged."""
    e = Entity(name="Caster", hp=100, base_stats={"con_save": con_save})
    e.add_modifier(Modifier("attack_bonus", 0, "bless", dice=(1, 4)))
    e.concentration = "bless"
    return e


def _hit_for(target: Entity, damage: int) -> DamageEvent:
    attacker = Entity(name="Ogre", hp=100, base_stats={})
    return DamageEvent(
        tick=(1, 1, 1), actor=attacker, target=target,
        is_crit=False, damage_dice=(0, 6), damage_bonus=damage,
    )


def test_damage_forces_check_and_break_drops_modifier():
    # con_save hugely negative → save can't beat DC=max(10, 28//2)=14 → break.
    target = _concentrating_target(con_save=-100)
    queue = None  # resolve_damage pushes no follow-on events here
    resolve_damage(_hit_for(target, 28), SeededRNG(0), queue, next_sequence=2)
    assert target.concentration is None
    assert target.modifiers.compute("attack_bonus", base=0) == 0  # bless removed
    assert target.concentration_checks == 1
    assert target.concentration_breaks == 1


def test_successful_save_keeps_concentration():
    # con_save absurdly high → always passes → keeps Bless.
    target = _concentrating_target(con_save=100)
    resolve_damage(_hit_for(target, 28), SeededRNG(0), None, next_sequence=2)
    assert target.concentration == "bless"
    assert target.concentration_checks == 1
    assert target.concentration_breaks == 0


def test_no_concentration_no_check():
    target = Entity(name="Caster", hp=100, base_stats={"con_save": 0})
    target.concentration = None
    resolve_damage(_hit_for(target, 28), SeededRNG(0), None, next_sequence=2)
    assert target.concentration_checks == 0


def test_advantage_next_save_consumed_by_check():
    target = _concentrating_target(con_save=0)
    target.statuses.apply("advantage_next_save", True)
    resolve_damage(_hit_for(target, 28), SeededRNG(0), None, next_sequence=2)
    # The check consumes the one-shot advantage whether or not it broke.
    assert not target.statuses.has("advantage_next_save")
    assert target.concentration_checks == 1


def test_dc_floor_is_ten():
    """Small hits still force a DC-10 check, not DC = dmg//2 below 10."""
    target = _concentrating_target(con_save=-100)  # fails any real DC
    resolve_damage(_hit_for(target, 4), SeededRNG(0), None, next_sequence=2)
    # 4//2 = 2 but the floor is 10, so an impossible-for-this-saver DC still
    # applies and breaks concentration.
    assert target.concentration_breaks == 1


# ---------------------------------------------------------------------------
# d20 floor on saves (substrate-#3 save-floor grant — Starry-Form Dragon)
# ---------------------------------------------------------------------------

def test_d20_floor_treats_low_rolls_as_the_floor():
    """A d20_floor raises any sub-floor roll to the floor (Dragon's "treat 9 or
    lower as 10").  With floor 10, save bonus 0 vs DC 10 EVERY save passes (any
    floored d20 ≥ 10); without the floor a fair share fail."""
    e = Entity(name="C", hp=100, base_stats={"con_save": 0})
    n = 100
    floored = sum(resolve_saving_throw(e, "con_save", 10, SeededRNG(s), d20_floor=10)
                  for s in range(n))
    straight = sum(resolve_saving_throw(e, "con_save", 10, SeededRNG(s))
                   for s in range(n))
    assert floored == n          # every roll floored to ≥10, +0 ≥ DC 10
    assert straight < n          # unfloored, the ≤9 rolls fail


def test_concentration_save_floor_status_protects_concentration():
    """End-to-end: a concentration_save_floor status (Dragon form) floors the CON
    save in _check_concentration, so a low-CON concentrator that would often break
    NEVER does over many small hits with the floor up — and breaks without it."""
    def breaks(with_floor: bool) -> int:
        broken = 0
        for s in range(60):
            t = _concentrating_target(con_save=0)
            if with_floor:
                t.statuses.apply("concentration_save_floor", 10)
            resolve_damage(_hit_for(t, 6), SeededRNG(s), None, next_sequence=2)  # DC 10
            broken += t.concentration_breaks
        return broken
    assert breaks(with_floor=True) == 0
    assert breaks(with_floor=False) > 0


# ---------------------------------------------------------------------------
# A broken concentration drops the WHOLE effect bundle (remove_effect), not just
# the modifier — so a cast's damage response (#4) and statuses (#3) clear with it.
# ---------------------------------------------------------------------------

def test_concentration_break_removes_the_full_effect_bundle():
    target = Entity(name="Caster", hp=100, base_stats={"con_save": -100})
    target.add_modifier(Modifier("attack_bonus", 2, "fom"))
    target.add_damage_response("fom", {"radiant": "resistance"})  # substrate #4
    target.statuses.apply("fom_flag", True)
    target.note_effect_status("fom", "fom_flag")                  # substrate #3, tracked
    target.concentration = "fom"
    resolve_damage(_hit_for(target, 30), SeededRNG(0), None, next_sequence=2)
    assert target.concentration is None
    assert target.modifiers.compute("attack_bonus", base=0) == 0      # modifier gone
    assert target.damage_response_for("radiant") is None              # #4 response gone
    assert not target.statuses.has("fom_flag")                        # #3 status gone
