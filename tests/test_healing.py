"""
test_healing.py — the healing subsystem (design/healing.md).

Four parts, matching the §9 build plan:
  1. the summon-category enum (§6) — {threshold, vanishes, downed} + on-zero effect;
  2. the `heal` verb and its phase order (§9.1);
  3. the source-attributed healing ledger / §13 telemetry channel (§9.2);
  4. Hit Dice, which are TWO DIFFERENT RULES (§7 a/b2) — spend-all at the short rest
     for characters, spend-to-the-deficit after each combat for summons.

The framing test the whole subsystem exists to support is at the bottom: healing a
MORTAL summon keeps it acting.  That is the one place healing changes behaviour
([[validate-mechanism-not-build-value]]) — everywhere else healing is pure
observation and must move nothing.
"""

from __future__ import annotations

import logging

import pytest

from src.entity import ZERO_HP_CATEGORIES, Entity
from src.resources import ResourceEntry, ResourcePool

logging.disable(logging.CRITICAL)


def _summon(category: str, hp: int = 20) -> Entity:
    e = Entity(name=f"{category}-summon", hp=hp, base_stats={"ac": 15})
    e.zero_hp_category = category
    return e


# ---------------------------------------------------------------------------
# 1. Summon categories (§6)
# ---------------------------------------------------------------------------

def test_category_vocabulary_is_closed_and_defaults_to_threshold():
    assert ZERO_HP_CATEGORIES == ("threshold", "vanishes", "downed")
    assert Entity(name="Char", hp=40).zero_hp_category == "threshold"


def test_threshold_entity_ignores_zero_hp_entirely():
    """The character model: `hp` is a signed balance and nothing gates on it."""
    e = Entity(name="Char", hp=10)
    e.take_damage(30)
    assert e.hp == -20
    assert not e.destroyed and not e.downed and not e.is_out_of_action


def test_vanishes_summon_is_destroyed_permanently_and_absorbs_no_healing():
    e = _summon("vanishes", hp=10)
    e.take_damage(12)
    assert e.destroyed and e.is_out_of_action
    e.heal(50)
    assert e.destroyed, "a vanished summon cannot be healed back (healing.md §4)"
    assert e.hp <= 0


def test_downed_summon_floors_at_zero_and_heals_back_into_the_fight():
    """The REVERSIBLE state `destroyed` cannot express (§6)."""
    e = _summon("downed", hp=10)
    e.take_damage(40)
    assert e.hp == 0, "floored at 0 so a heal does not have to climb out of a hole"
    assert e.downed and e.is_out_of_action and not e.destroyed
    e.heal(5)
    assert e.hp == 5
    assert not e.downed and not e.is_out_of_action


def test_on_zero_effect_fires_once_for_either_summon_category():
    """§6 case 3 — the reanimator's companion fires a death effect but stays
    revivable.  Cases 2 and 3 differ only by this effect, not by class."""
    fired: list[str] = []
    for category in ("vanishes", "downed"):
        e = _summon(category, hp=8)
        e.on_zero_hp = lambda ent: fired.append(ent.zero_hp_category)
        e.take_damage(10)
        e.take_damage(10)                      # already at 0 — must not re-fire
    assert fired == ["vanishes", "downed"]


def test_legacy_boolean_view_still_means_vanishes():
    """`dies_at_zero_hp` is the property over the enum, so every pre-existing call
    site (day_runner's long rest, silvertail's factory, the survival tests) reads
    and writes the enum unchanged."""
    e = Entity(name="Beast", hp=25)
    assert e.dies_at_zero_hp is False
    e.dies_at_zero_hp = True
    assert e.zero_hp_category == "vanishes" and e.dies_at_zero_hp is True
    e.dies_at_zero_hp = False
    assert e.zero_hp_category == "threshold"


# ---------------------------------------------------------------------------
# 1b. The healing CAP follows the category, not the roster role (§4)
# ---------------------------------------------------------------------------

def test_threshold_entities_are_uncapped_summons_are_capped():
    char = Entity(name="Char", hp=40)
    char.take_damage(10)
    char.heal(100)
    assert char.hp == 130, "no max_hp cap where hp is a signed balance (§2/§4)"

    for category in ("vanishes", "downed"):
        s = _summon(category, hp=20)
        s.take_damage(5)
        s.heal(100)
        assert s.hp == 20, f"{category} summon capped at max_hp (§4)"
