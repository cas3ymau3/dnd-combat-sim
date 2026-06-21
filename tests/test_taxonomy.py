"""test_taxonomy.py — the modality/attack taxonomy (src/taxonomy.py), session 25.

The attack-taxonomy axis: a first-class, closed vocabulary that separates *what a
character does* (modality) from *what it costs* (the action-economy cost), and
describes *how it is resolved* (resolution), its *origin* (weapon / unarmed /
spell / feature), and its *range* (melee / ranged).  See src/taxonomy.py for the
full rationale and design/attack_taxonomy.md for the locked contract.

This is a backward-compatible refactor: the taxonomy fields are ADDED to Choice /
the events / the hit contexts and DERIVED from the legacy flags (action_type /
is_spell / is_unarmed / weapon_stat) so every existing construction carries
correct taxonomy values and behaviour is unchanged.  These tests pin:

  - the pure predicate + derivation helpers;
  - Choice.__post_init__ derivation from the legacy flags (each modality shape);
  - explicit origin overriding the legacy flags (the migration direction);
  - the descriptor threading Choice → AttackRollEvent → HitContext, and the
    HitContext is_physical / is_spell_origin predicates.

Behaviour-identity (495 prior tests byte-identical) is verified by the existing
suite; this file pins the NEW vocabulary's wiring only.
"""

from src import taxonomy
from src.policy import Choice, HitContext
from src.events import AttackRollEvent, DamageEvent, SaveDamageEvent


# ---------------------------------------------------------------------------
# Pure predicates + derivation helpers
# ---------------------------------------------------------------------------

def test_predicates():
    assert taxonomy.is_attack("attack_roll")
    assert not taxonomy.is_attack("saving_throw")
    assert not taxonomy.is_attack("automatic")
    assert not taxonomy.is_attack(None)

    # "Attack action" = the Attack modality AT AN ACTION cost specifically — a
    # bonus-action swing is the Attack modality but NOT the Attack action.
    assert taxonomy.is_attack_action("Attack", "action")
    assert not taxonomy.is_attack_action("Attack", "bonus_action")
    assert not taxonomy.is_attack_action("Magic", "action")

    # physical = weapon | unarmed; spell-origin = spell SPECIFICALLY (a feature
    # is magical but not a spell).
    assert taxonomy.is_physical("weapon")
    assert taxonomy.is_physical("unarmed")
    assert not taxonomy.is_physical("spell")
    assert not taxonomy.is_physical("feature")
    assert taxonomy.is_spell_origin("spell")
    assert not taxonomy.is_spell_origin("feature")
    assert not taxonomy.is_spell_origin("weapon")


def test_derive_resolution():
    assert taxonomy.derive_resolution("attack") == "attack_roll"
    assert taxonomy.derive_resolution("save_spell") == "saving_throw"
    assert taxonomy.derive_resolution("cast_effect") == "automatic"
    assert taxonomy.derive_resolution("dodge") is None


def test_derive_origin():
    assert taxonomy.derive_origin(is_spell=True, is_unarmed=False,
                                  weapon_stat="spell_attack_bonus") == "spell"
    assert taxonomy.derive_origin(is_spell=False, is_unarmed=True,
                                  weapon_stat="attack_bonus") == "unarmed"
    # spell_attack_bonus but NOT a spell → a magical FEATURE (Starry-Form Archer).
    assert taxonomy.derive_origin(is_spell=False, is_unarmed=False,
                                  weapon_stat="spell_attack_bonus") == "feature"
    assert taxonomy.derive_origin(is_spell=False, is_unarmed=False,
                                  weapon_stat="attack_bonus") == "weapon"


def test_vocabularies_closed():
    # The implemented combat subset is a subset of the full named modality set.
    assert set(taxonomy.COMBAT_MODALITIES) <= set(taxonomy.MODALITIES)
    # movement is a first-class cost now (no consumer yet — named, not exercised).
    assert "movement" in taxonomy.COSTS
    assert len(taxonomy.DAMAGE_TYPES) == 13


# ---------------------------------------------------------------------------
# Choice derivation (each modality shape)
# ---------------------------------------------------------------------------

def test_choice_weapon_attack_derives():
    ch = Choice(action_type="attack", cost="action")
    assert ch.modality == "Attack"
    assert ch.resolution == "attack_roll"
    assert ch.origin == "weapon"
    assert ch.range_ == "melee"          # default for an attack with no explicit range


def test_choice_spell_attack_derives():
    # Guiding Bolt: a Magic-modality attack delivered via an attack roll, ranged.
    ch = Choice(action_type="attack", cost="action", is_spell=True,
                damage_type="radiant", weapon_stat="spell_attack_bonus",
                range_="ranged")
    assert ch.resolution == "attack_roll"
    assert ch.origin == "spell"
    assert ch.range_ == "ranged"
    assert taxonomy.is_attack(ch.resolution)         # "an attack" in the rules sense


def test_choice_unarmed_attack_derives():
    ch = Choice(action_type="attack", cost="none", is_unarmed=True)
    assert ch.origin == "unarmed"
    assert ch.range_ == "melee"


def test_choice_feature_attack_derives():
    # Starry-Form Archer: a magical FEATURE (not a spell) making a ranged attack.
    ch = Choice(action_type="attack", cost="bonus_action",
                weapon_stat="spell_attack_bonus", damage_type="radiant",
                damage_dice=(1, 8), range_="ranged")
    assert ch.origin == "feature"
    assert not ch.is_spell           # a feature is NOT a spell (not fuelable)


def test_choice_save_spell_derives():
    # Burning Hands: Magic modality, resolved by a saving throw, spell origin.
    ch = Choice(action_type="save_spell", cost="action", save_stat="dex_save",
                damage_dice=(3, 6), damage_type="fire", is_spell=True,
                on_save="half")
    assert ch.modality == "Magic"
    assert ch.resolution == "saving_throw"
    assert ch.origin == "spell"
    assert ch.range_ is None          # range is meaningless for a save spell


def test_choice_buff_cast_has_no_origin():
    # A pure buff cast (no attack, no damage) has automatic resolution and NO
    # origin — origin is meaningful only for damage/save abilities.
    ch = Choice(action_type="cast_effect", cost="action",
                effect_source="bless", modality="Magic")
    assert ch.resolution == "automatic"
    assert ch.origin is None
    assert ch.range_ is None


def test_explicit_origin_overrides_legacy_flags():
    # The migration direction: setting origin keeps the legacy aliases consistent.
    ch = Choice(action_type="attack", origin="spell", damage_type="radiant")
    assert ch.is_spell is True
    assert ch.is_unarmed is False

    ch2 = Choice(action_type="attack", origin="unarmed")
    assert ch2.is_unarmed is True
    assert ch2.is_spell is False


def test_use_ability_modality_explicit():
    # A non-magical class feature (Rage) is the Use Ability modality — set
    # explicitly by the call site (not derivable from action_type alone).
    ch = Choice(action_type="cast_effect", cost="bonus_action",
                effect_source="rage", modality="Use Ability")
    assert ch.modality == "Use Ability"
    assert ch.resolution == "automatic"


# ---------------------------------------------------------------------------
# Descriptor threading Choice → events → HitContext
# ---------------------------------------------------------------------------

def test_events_carry_origin_and_range():
    ev = AttackRollEvent(tick=(1, 0, 0), actor=None, target=None,
                         origin="spell", range_="ranged")
    assert ev.origin == "spell"
    assert ev.range_ == "ranged"

    dmg = DamageEvent(tick=(1, 0, 1), actor=None, target=None, origin="feature")
    assert dmg.origin == "feature"

    sdmg = SaveDamageEvent(tick=(1, 0, 2), actor=None, target=None, origin="spell")
    assert sdmg.origin == "spell"


def test_hitcontext_predicates():
    ctx = HitContext(
        actor=None, target=None, is_crit=False, cost="action",
        bonus_action_available=True, resources={}, round_number=1,
        origin="weapon", range_="melee",
    )
    assert ctx.is_physical
    assert not ctx.is_spell_origin

    ctx_spell = HitContext(
        actor=None, target=None, is_crit=False, cost="action",
        bonus_action_available=True, resources={}, round_number=1,
        origin="spell", range_="ranged",
    )
    assert not ctx_spell.is_physical
    assert ctx_spell.is_spell_origin

    # A magical feature is neither physical nor a spell.
    ctx_feature = HitContext(
        actor=None, target=None, is_crit=False, cost="action",
        bonus_action_available=True, resources={}, round_number=1,
        origin="feature", range_="ranged",
    )
    assert not ctx_feature.is_physical
    assert not ctx_feature.is_spell_origin
