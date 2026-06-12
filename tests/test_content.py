"""
test_content.py — the declarative ability layer (src/content.py).

These tests pin the effect-interpreter against the War Angel oracle: the
Modifiers / rider it builds FROM DATA must equal what the build hand-coded
(src/builds/war_angel.py) before this layer existed.  Equal engine inputs →
bit-identical simulation, which is the whole de-risking argument for doing this
against a validated build.

They also pin the LOUD-failure behavior: anything the interpreter does not yet
model raises NotImplementedError rather than silently dropping the effect.
"""

from __future__ import annotations

import pytest

from src.content import (
    Ability,
    HitRiderSpec,
    interpret_hit_rider,
    interpret_modifiers,
    load_abilities,
    parse_dice,
)
from src.modifiers import Modifier


# ---------------------------------------------------------------------------
# parse_dice
# ---------------------------------------------------------------------------

def test_parse_dice_basic():
    assert parse_dice("1d6") == (1, 6)
    assert parse_dice("2d8") == (2, 8)
    assert parse_dice(" 1d4 ") == (1, 4)


def test_parse_dice_rejects_garbage():
    for bad in ("d6", "1d", "1x6", "1d6+2", "", "three"):
        with pytest.raises(ValueError):
            parse_dice(bad)


# ---------------------------------------------------------------------------
# load_abilities
# ---------------------------------------------------------------------------

def test_load_abilities_builds_a_unique_library():
    lib = load_abilities()
    # The corpus loads and is keyed by unique name.
    assert "bless" in lib                 # core_examples.yaml
    assert "wrathful_smite" in lib        # war_angel.yaml
    assert "tough" in lib
    assert all(isinstance(a, Ability) for a in lib.values())
    assert lib["bless"].name == "bless"


# ---------------------------------------------------------------------------
# interpret_modifiers — Bless (Slice 1)
# ---------------------------------------------------------------------------

def test_bless_modifiers_match_the_handcoded_oracle():
    """The data-driven Bless must produce EXACTLY the two Modifiers the build
    hand-built before this layer: +1d4 on attack_bonus and on con_save."""
    bless = load_abilities()["bless"]
    mods = interpret_modifiers(bless, source="bless")

    oracle = [
        Modifier("attack_bonus", 0, "bless", dice=(1, 4)),
        Modifier("con_save", 0, "bless", dice=(1, 4)),
    ]
    assert mods == oracle


def test_interpret_modifiers_rejects_non_modifier_verb():
    """Wrathful Smite is a damage rider, not an apply_modifier — loud failure."""
    smite = load_abilities()["wrathful_smite"]
    with pytest.raises(NotImplementedError):
        interpret_modifiers(smite)


def test_interpret_modifiers_rejects_unknown_scope():
    ability = Ability.from_dict({
        "name": "x",
        "effect": [{"verb": "apply_modifier", "hook": "bonus_die",
                    "die": "1d4", "applies_to": "some_unknown_scope"}],
    })
    with pytest.raises(NotImplementedError):
        interpret_modifiers(ability)


def test_interpret_modifiers_flat_hook():
    """A flat hook (e.g. Shield of Faith +2 AC) reads `stat` + `value`."""
    ability = Ability.from_dict({
        "name": "shield_of_faith_like",
        "effect": [{"verb": "apply_modifier", "hook": "flat",
                    "stat": "ac", "value": 2}],
    })
    assert interpret_modifiers(ability, source="sof") == [Modifier("ac", 2, "sof")]


# ---------------------------------------------------------------------------
# interpret_hit_rider — Wrathful Smite (Slice 2)
# ---------------------------------------------------------------------------

def test_wrathful_smite_rider_matches_the_handcoded_oracle():
    """The data-driven Wrathful Smite must produce the same rider the build
    hand-built: +1d6, bonus-action cost, a level-1+ spell slot."""
    smite = load_abilities()["wrathful_smite"]
    rider = interpret_hit_rider(smite)

    assert rider == HitRiderSpec(
        extra_damage_dice=[(1, 6)],
        action_cost="bonus_action",
        resource_type="spell_slot",
        min_level=1,
    )


def test_interpret_hit_rider_rejects_non_damage_verb():
    """Bless is an apply_modifier, not a damage rider — loud failure."""
    bless = load_abilities()["bless"]
    with pytest.raises(NotImplementedError):
        interpret_hit_rider(bless)


def test_interpret_hit_rider_rejects_unmodeled_scaling():
    """Divine Smite carries upcast scaling (`increment`) we don't model yet —
    it must raise, not silently drop the extra dice."""
    divine = load_abilities()["divine_smite"]
    with pytest.raises(NotImplementedError):
        interpret_hit_rider(divine)
