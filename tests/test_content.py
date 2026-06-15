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
    SaveSpellSpec,
    _resolve_scaling_dice,
    interpret_hit_rider,
    interpret_intercept,
    interpret_modifiers,
    interpret_on_hit_effects,
    interpret_roll_bonus,
    interpret_save_spell,
    interpret_scaled_dice,
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


def test_interpret_hit_rider_resolves_upcast_divine_smite():
    """Divine Smite carries upcast scaling (`increment`, +1d8 per slot level) —
    primitive #3 resolves it from data given the chosen slot in context.
    base 2d8 at slot 1; slot 3 → 4d8."""
    divine = load_abilities()["divine_smite"]
    rider = interpret_hit_rider(divine, {"slot_level": 3})
    assert rider.extra_damage_dice == [(4, 8)]
    assert rider.resource_type == "spell_slot"
    assert rider.min_level == 1


def test_interpret_hit_rider_upcast_needs_the_slot_level_in_context():
    """An upcast rider is interpretive — without the slot level it fails loudly
    (a missing context value, not a silent default)."""
    divine = load_abilities()["divine_smite"]
    with pytest.raises(ValueError):
        interpret_hit_rider(divine)


# ---------------------------------------------------------------------------
# _resolve_scaling_dice — the shared dice-scaling seam (primitive #2)
# ---------------------------------------------------------------------------

def test_scaling_dice_literal_forms_are_level_independent():
    """A bare string or a `{base: ...}` block with no scaling keys is a literal —
    it resolves the same at any level (and needs no context)."""
    assert _resolve_scaling_dice("1d6") == (1, 6)
    assert _resolve_scaling_dice("2d8") == (2, 8)
    assert _resolve_scaling_dice({"base": "1d6"}) == (1, 6)
    # Extra non-scaling keys (type, etc.) are ignored by the dice resolver.
    assert _resolve_scaling_dice({"base": "3d6", "type": "radiant"}) == (3, 6)


def test_scaling_dice_cantrip_steps_at_5_11_17():
    """The canonical cantrip rule: 1d8 at L1–4, 2d8 at L5–10, 3d8 at L11–16,
    4d8 at L17+ — pinned at every threshold and boundary."""
    spec = {"base": "1d8", "scaling": "cantrip", "level_reference": "character_level"}

    def dice_at(level: int) -> tuple[int, int]:
        return _resolve_scaling_dice(spec, {"character_level": level}, "sacred_flame")

    # die count steps up exactly at 5 / 11 / 17; die SIZE is always d8.
    assert [dice_at(lv) for lv in (1, 4)] == [(1, 8), (1, 8)]
    assert [dice_at(lv) for lv in (5, 10)] == [(2, 8), (2, 8)]
    assert [dice_at(lv) for lv in (11, 16)] == [(3, 8), (3, 8)]
    assert [dice_at(lv) for lv in (17, 20)] == [(4, 8), (4, 8)]


def test_scaling_dice_cantrip_needs_the_level_in_context():
    """`scaling: cantrip` is interpretive — it needs the level at fire-time;
    a missing context value raises (not a silent default)."""
    spec = {"base": "1d8", "scaling": "cantrip", "level_reference": "character_level"}
    with pytest.raises(ValueError):
        _resolve_scaling_dice(spec, None, "sacred_flame")
    with pytest.raises(ValueError):
        _resolve_scaling_dice(spec, {"slot_level": 3}, "sacred_flame")


def test_scaling_dice_cantrip_requires_character_level_reference():
    """Cantrip scaling is by character level only; a different reference raises."""
    spec = {"base": "1d8", "scaling": "cantrip", "level_reference": "slot_level"}
    with pytest.raises(NotImplementedError):
        _resolve_scaling_dice(spec, {"slot_level": 3}, "sacred_flame")


def test_scaling_dice_uniform_increment_scales_per_slot_level():
    """The uniform upcast form (primitive #3): base 2d8 at slot 1, +1d8 per slot
    level.  base_level defaults to 1, so slot N → (1 + N) d8."""
    spec = {
        "base": "2d8", "increment": "1d8",
        "every_n_levels": 1, "level_reference": "slot_level",
    }

    def dice_at(slot: int) -> tuple[int, int]:
        return _resolve_scaling_dice(spec, {"slot_level": slot}, "divine_smite")

    assert [dice_at(s) for s in (1, 2, 3, 4, 5)] == [
        (2, 8), (3, 8), (4, 8), (5, 8), (6, 8)
    ]


def test_scaling_dice_uniform_explicit_base_level_offset():
    """A spell whose base lands above slot 1 sets `base_level` (Spirit Guardians:
    3d8 at slot 3, +1d8 per slot level).  Steps are measured ABOVE base_level, and
    a slot below it clamps to the base pool (never shrinks)."""
    spec = {
        "base": "3d8", "increment": "1d8", "every_n_levels": 1,
        "level_reference": "slot_level", "base_level": 3,
    }

    def dice_at(slot: int) -> tuple[int, int]:
        return _resolve_scaling_dice(spec, {"slot_level": slot}, "spirit_guardians")

    assert [dice_at(s) for s in (3, 4, 5, 9)] == [(3, 8), (4, 8), (5, 8), (9, 8)]
    assert dice_at(2) == (3, 8)        # below base level → clamps to base, no shrink


def test_scaling_dice_uniform_every_n_levels_step():
    """`every_n_levels: 2` adds the increment once per two reference levels
    (Sneak Attack: 1d6 at rogue 1, +1d6 every 2 → 2d6 at L3, 3d6 at L5)."""
    spec = {
        "base": "1d6", "increment": "1d6",
        "every_n_levels": 2, "level_reference": "rogue_level",
    }

    def dice_at(level: int) -> tuple[int, int]:
        return _resolve_scaling_dice(spec, {"rogue_level": level}, "sneak_attack")

    assert [dice_at(lv) for lv in (1, 2, 3, 5, 20)] == [
        (1, 6), (1, 6), (2, 6), (3, 6), (10, 6)
    ]


def test_scaling_dice_uniform_needs_the_level_in_context():
    """Uniform scaling is interpretive — a missing reference level raises (no
    silent default), mirroring the cantrip case."""
    spec = {
        "base": "2d8", "increment": "1d8",
        "every_n_levels": 1, "level_reference": "slot_level",
    }
    with pytest.raises(ValueError):
        _resolve_scaling_dice(spec, None, "divine_smite")
    with pytest.raises(ValueError):
        _resolve_scaling_dice(spec, {"character_level": 5}, "divine_smite")


def test_scaling_dice_uniform_rejects_mismatched_die_size():
    """Only the die COUNT scales, never the size — a base/increment die-size
    mismatch can't fold into one (count, sides) and raises loudly."""
    spec = {
        "base": "2d8", "increment": "1d6",
        "every_n_levels": 1, "level_reference": "slot_level",
    }
    with pytest.raises(NotImplementedError):
        _resolve_scaling_dice(spec, {"slot_level": 3}, "frankenspell")


# ---------------------------------------------------------------------------
# _resolve_scaling_dice — the enumerated DICE LADDER (the die-size quantity)
# ---------------------------------------------------------------------------

def _shillelagh_ladder() -> dict:
    """The 2024 Shillelagh ladder spec (size grows, and the top step also changes
    the count): 1d8 / 1d10 / 1d12 / 2d6 at character levels 5 / 11 / 17."""
    return {
        "scaling": "ladder",
        "breaks": [5, 11, 17],
        "dice": ["1d8", "1d10", "1d12", "2d6"],
        "level_reference": "character_level",
    }


def test_scaling_dice_ladder_steps_at_5_11_17_including_count_change():
    """The ladder grows the die SIZE at each break and CHANGES THE COUNT at the
    top step (1d12 -> 2d6) — the case neither the cantrip nor the increment form
    can express.  Boundaries on both sides of every break are pinned."""
    spec = _shillelagh_ladder()

    def at(level: int) -> tuple[int, int]:
        return _resolve_scaling_dice(spec, {"character_level": level}, "shillelagh")

    assert at(1) == (1, 8) and at(4) == (1, 8)      # below the first break
    assert at(5) == (1, 10) and at(10) == (1, 10)   # first step
    assert at(11) == (1, 12) and at(16) == (1, 12)  # second step
    assert at(17) == (2, 6) and at(20) == (2, 6)    # top step: size AND count


def test_scaling_dice_ladder_is_general_across_drivers_and_breaks():
    """The ladder is a GENERAL shape, not a Shillelagh quirk — a pure die-SIZE
    walk on a CLASS-level driver with different breaks (bardic inspiration
    d6/d8/d10/d12 at bard 5/10/15; battlemaster superiority d8/d10/d12 at
    fighter 10/18).  Same mechanism, no per-feature code."""
    bardic = {
        "scaling": "ladder",
        "breaks": [5, 10, 15],
        "dice": ["1d6", "1d8", "1d10", "1d12"],
        "level_reference": "bard_level",
    }
    got = {lv: _resolve_scaling_dice(bardic, {"bard_level": lv}, "bardic_inspiration")
           for lv in (1, 5, 10, 15)}
    assert got == {1: (1, 6), 5: (1, 8), 10: (1, 10), 15: (1, 12)}

    superiority = {
        "scaling": "ladder",
        "breaks": [10, 18],
        "dice": ["1d8", "1d10", "1d12"],
        "level_reference": "fighter_level",
    }
    got2 = {lv: _resolve_scaling_dice(superiority, {"fighter_level": lv}, "superiority")
            for lv in (3, 10, 18)}
    assert got2 == {3: (1, 8), 10: (1, 10), 18: (1, 12)}


def test_scaling_dice_ladder_needs_the_level_in_context():
    """No driver value (or the wrong key) in context → loud failure, like every
    other scaling shape."""
    spec = _shillelagh_ladder()
    with pytest.raises(ValueError):
        _resolve_scaling_dice(spec, None, "shillelagh")
    with pytest.raises(ValueError):
        _resolve_scaling_dice(spec, {"slot_level": 11}, "shillelagh")


def test_scaling_dice_ladder_rejects_malformed_tables():
    """The break/dice lists must be coherent: present, ascending breaks, and
    exactly one more die than breaks (one die per step).  Each raises loudly."""
    base = {"level_reference": "character_level"}
    # Missing `dice`.
    with pytest.raises(NotImplementedError):
        _resolve_scaling_dice({**base, "scaling": "ladder", "breaks": [5]}, {"character_level": 5}, "x")
    # Missing `breaks`.
    with pytest.raises(NotImplementedError):
        _resolve_scaling_dice({**base, "scaling": "ladder", "dice": ["1d8", "1d10"]}, {"character_level": 5}, "x")
    # dice/breaks length mismatch (2 breaks need 3 dice, got 2).
    with pytest.raises(NotImplementedError):
        _resolve_scaling_dice(
            {**base, "scaling": "ladder", "breaks": [5, 11], "dice": ["1d8", "1d10"]},
            {"character_level": 11}, "x",
        )
    # Non-ascending breaks.
    with pytest.raises(NotImplementedError):
        _resolve_scaling_dice(
            {**base, "scaling": "ladder", "breaks": [11, 5], "dice": ["1d8", "1d10", "1d12"]},
            {"character_level": 11}, "x",
        )


# ---------------------------------------------------------------------------
# interpret_scaled_dice — the dice ladder driving an ability (Shillelagh)
# ---------------------------------------------------------------------------

def test_shillelagh_die_scales_on_the_ladder_from_data():
    """Shillelagh FROM DATA: the cantrip's force die climbs 1d8 / 1d10 / 1d12 /
    2d6 by character level — the first consumer of `scaling: ladder`."""
    sh = load_abilities()["shillelagh"]
    by_level = {
        lv: interpret_scaled_dice(sh, {"character_level": lv})
        for lv in (1, 5, 11, 17)
    }
    assert by_level == {1: (1, 8), 5: (1, 10), 11: (1, 12), 17: (2, 6)}


def test_interpret_scaled_dice_rejects_non_damage_shapes():
    """The reader resolves a single `damage` die only; anything else raises."""
    save_spell = load_abilities()["sacred_flame"]  # has a `save` block too
    with pytest.raises(NotImplementedError):
        interpret_scaled_dice(save_spell, {"character_level": 5})


# ---------------------------------------------------------------------------
# interpret_save_spell — Sacred Flame (primitive #2)
# ---------------------------------------------------------------------------

def test_sacred_flame_save_spell_spec_at_l1():
    """Sacred Flame FROM DATA at L1: DEX save vs spell_save_dc, 1d8, negates,
    radiant.  The `type: radiant` from the YAML now surfaces on the spec — it
    drives the caster-side Fueled-Spellfire gate (spell radiant damage)."""
    sf = load_abilities()["sacred_flame"]
    spec = interpret_save_spell(sf, {"character_level": 1})
    assert spec == SaveSpellSpec(
        save_stat="dex_save",
        dc_stat="spell_save_dc",
        damage_dice=(1, 8),
        on_save="none",
        damage_bonus=0,
        damage_type="radiant",
    )


def test_sacred_flame_dice_scale_with_character_level():
    """The same Sacred Flame data yields 1d8 / 2d8 / 3d8 / 4d8 at L1 / 5 / 11 / 17
    — the cantrip-scaling primitive driving a save-for-damage spell from data."""
    sf = load_abilities()["sacred_flame"]
    by_level = {
        lv: interpret_save_spell(sf, {"character_level": lv}).damage_dice
        for lv in (1, 5, 11, 17)
    }
    assert by_level == {1: (1, 8), 5: (2, 8), 11: (3, 8), 17: (4, 8)}


def test_interpret_save_spell_rejects_a_non_save_damage_shape():
    """An ability without the `save` + `damage` pair raises (loud gap)."""
    # Wrathful Smite is a bare damage rider — no `save` block.
    smite = load_abilities()["wrathful_smite"]
    with pytest.raises(NotImplementedError):
        interpret_save_spell(smite, {"character_level": 5})


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
