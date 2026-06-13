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
    InterceptSpec,
    OnHitEffectSpec,
    RollBonusSpec,
    interpret_hit_rider,
    interpret_intercept,
    interpret_modifiers,
    interpret_on_hit_effects,
    interpret_roll_bonus,
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


def test_war_gods_blessing_matches_the_handcoded_oracle():
    """War God's Blessing (free Shield of Faith) must produce the same +2 AC
    Modifier the build hand-built, under the 'shield_of_faith' source."""
    sof = load_abilities()["war_gods_blessing"]
    assert interpret_modifiers(sof, source="shield_of_faith") == [
        Modifier("ac", 2, "shield_of_faith")
    ]


def test_magic_weapon_flat_buff_tracks_the_cast_tier():
    """Magic Weapon's two flat modifiers (attack + damage) take the SAME value
    from the runtime cast tier the policy supplies — +1 and +2 in turn, matching
    the hand-built pair."""
    mw = load_abilities()["magic_weapon"]
    assert interpret_modifiers(mw, source="magic_weapon",
                               context={"magic_weapon_bonus": 1}) == [
        Modifier("attack_bonus", 1, "magic_weapon"),
        Modifier("damage_bonus", 1, "magic_weapon"),
    ]
    assert interpret_modifiers(mw, source="magic_weapon",
                               context={"magic_weapon_bonus": 2}) == [
        Modifier("attack_bonus", 2, "magic_weapon"),
        Modifier("damage_bonus", 2, "magic_weapon"),
    ]


def test_magic_weapon_requires_a_cast_tier_context():
    """The runtime tier is mandatory — no context is a loud error, not a +0 buff."""
    mw = load_abilities()["magic_weapon"]
    with pytest.raises(ValueError):
        interpret_modifiers(mw, source="magic_weapon")


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


# ---------------------------------------------------------------------------
# interpret_on_hit_effects — Brutality bluff / bleed (Slice 3)
# ---------------------------------------------------------------------------

def test_brutality_bluff_matches_the_handcoded_oracle():
    """The data-driven bluff must produce what the build hand-coded: vex on the
    target (extra mastery) + the advantage_next_save self-status.  No damage."""
    bluff = load_abilities()["brutality_bluff"]
    spec = interpret_on_hit_effects(bluff)

    assert spec == OnHitEffectSpec(
        target_masteries=["vex"],
        self_statuses=["advantage_next_save"],
        extra_flat_damage=0,
    )


def test_brutality_bleed_matches_the_handcoded_oracle():
    """The data-driven bleed must produce what the counter hand-coded: sap on the
    target + the +CHA flat damage, resolved against the supplied context."""
    bleed = load_abilities()["brutality_bleed"]
    spec = interpret_on_hit_effects(bleed, context={"charisma": 5})

    assert spec == OnHitEffectSpec(
        target_masteries=["sap"],
        self_statuses=[],
        extra_flat_damage=5,
    )


def test_brutality_bleed_flat_damage_tracks_the_context():
    """The flat amount is runtime-dependent — a different CHA mod yields a
    different value (the interpreter is genuinely evaluating, not compiling)."""
    bleed = load_abilities()["brutality_bleed"]
    assert interpret_on_hit_effects(bleed, context={"charisma": 3}).extra_flat_damage == 3


def test_interpret_on_hit_effects_requires_context_for_runtime_amount():
    """A flat ability-modifier amount with no context value is a loud error,
    not a silent zero."""
    bleed = load_abilities()["brutality_bleed"]
    with pytest.raises(ValueError):
        interpret_on_hit_effects(bleed)            # context omitted
    with pytest.raises(ValueError):
        interpret_on_hit_effects(bleed, context={})  # wrong key


def test_interpret_on_hit_effects_rejects_non_mastery_target_status():
    """A TARGET status that is not a known weapon mastery has no engine field —
    it must raise rather than be silently routed into masteries."""
    ability = Ability.from_dict({
        "name": "frightener",
        "effect": [{"verb": "apply_status", "status": "frightened",
                    "target": "target"}],
    })
    with pytest.raises(NotImplementedError):
        interpret_on_hit_effects(ability)


def test_interpret_on_hit_effects_rejects_damage_without_flat_amount():
    """A damage verb here must carry a flat `amount` (dice riders go through
    interpret_hit_rider) — otherwise loud failure."""
    ability = Ability.from_dict({
        "name": "dicey",
        "effect": [{"verb": "damage", "dice": {"base": "1d6"}}],
    })
    with pytest.raises(NotImplementedError):
        interpret_on_hit_effects(ability)


def test_interpret_on_hit_effects_rejects_choose_one():
    """choose_one (a dict effect, not a list) is the Flourish slice's gap — it
    must raise here, not be silently mishandled."""
    bleed = load_abilities()["brutality_bleed"]
    choose_one = Ability.from_dict({
        "name": "modal",
        "effect": {"choose_one": []},
    })
    with pytest.raises(NotImplementedError):
        interpret_on_hit_effects(choose_one)


# ---------------------------------------------------------------------------
# interpret_intercept — Flourish Parry (Slice 4)
# ---------------------------------------------------------------------------

def test_flourish_parry_matches_the_handcoded_oracle():
    """The data-driven parry must produce the same AC bump the build hand-coded:
    +CHA, resolved against the supplied context."""
    parry = load_abilities()["flourish_parry"]
    assert interpret_intercept(parry, context={"charisma": 5}) == InterceptSpec(ac_bonus=5)


def test_flourish_parry_ac_bonus_tracks_the_context():
    parry = load_abilities()["flourish_parry"]
    assert interpret_intercept(parry, context={"charisma": 4}).ac_bonus == 4


def test_interpret_intercept_supports_a_literal_ac_value():
    """A literal `value` AC bump (schema §4.5 example) needs no context."""
    ability = Ability.from_dict({
        "name": "shield_like",
        "effect": [{"verb": "intercept_event", "modification": "apply_modifier",
                    "hook": "flat", "stat": "ac", "value": 5}],
    })
    assert interpret_intercept(ability) == InterceptSpec(ac_bonus=5)


def test_interpret_intercept_rejects_non_ac_bump():
    """Only a flat AC bump is modeled; a force-miss / other-stat interception
    must raise rather than be silently treated as an AC bump."""
    ability = Ability.from_dict({
        "name": "weird",
        "effect": [{"verb": "intercept_event", "modification": "apply_modifier",
                    "hook": "flat", "stat": "saving_throw", "value": 5}],
    })
    with pytest.raises(NotImplementedError):
        interpret_intercept(ability)


def test_interpret_intercept_rejects_non_intercept_verb():
    bless = load_abilities()["bless"]
    with pytest.raises(NotImplementedError):
        interpret_intercept(bless)


# ---------------------------------------------------------------------------
# interpret_roll_bonus — Guided Strike (Slice 6)
# ---------------------------------------------------------------------------

def test_guided_strike_matches_the_handcoded_oracle():
    """The data-driven Guided Strike must produce the same rescue the build
    hand-coded: +10 to the attack roll, costing one channel_divinity."""
    gs = load_abilities()["guided_strike"]
    assert interpret_roll_bonus(gs) == RollBonusSpec(
        bonus=10, resource_type="channel_divinity", count=1
    )


def test_interpret_roll_bonus_rejects_non_attack_roll_stat():
    ability = Ability.from_dict({
        "name": "ac_bumper",
        "effect": [{"verb": "apply_modifier", "hook": "flat",
                    "stat": "ac", "value": 10}],
    })
    with pytest.raises(NotImplementedError):
        interpret_roll_bonus(ability)


def test_interpret_roll_bonus_rejects_non_flat_verb():
    smite = load_abilities()["wrathful_smite"]   # a damage rider, not a flat bonus
    with pytest.raises(NotImplementedError):
        interpret_roll_bonus(smite)
