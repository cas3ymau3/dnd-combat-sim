"""test_taxonomy.py — the modality/attack taxonomy (src/taxonomy.py), session 25.

The attack-taxonomy axis: a first-class, closed vocabulary that separates *what a
character does* (modality) from *what it costs* (the action-economy cost), and
describes *how it is resolved* (resolution), its *origin* (weapon / unarmed /
spell / feature), and its *range* (melee / ranged).  See src/taxonomy.py for the
full rationale and design/attack_taxonomy.md for the locked contract.

`origin` is now the canonical axis (the legacy is_spell / is_unarmed flags were
removed in the gate-migration pass): a Choice that omits `origin` defaults to
"weapon" for any attack/damage, and spell / unarmed / feature sources set it
explicitly at the call site.  These tests pin:

  - the pure predicates + the resolution-derivation helper;
  - Choice.__post_init__ defaults (modality / resolution / origin / range_) per
    modality shape, and explicit origin at the call site;
  - the descriptor threading Choice → AttackRollEvent → HitContext, and the
    HitContext is_physical / is_spell_origin predicates.
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

    # is_attack_action = the Attack-action EXPENDITURE (spend your action to
    # Attack) — a bonus-action swing is the Attack modality but not the
    # expenditure.
    assert taxonomy.is_attack_action("Attack", "action")
    assert not taxonomy.is_attack_action("Attack", "bonus_action")
    assert not taxonomy.is_attack_action("Magic", "action")
    # ...and it is deliberately NOT the GWM / Searing-Arc "made as part of the
    # Attack action" gate, which is a provenance property (deferred build): an
    # Extra Attack FOLLOW-UP (Attack, none) and a War-Magic cantrip (Magic, none)
    # are both part of the Attack action yet return False here.
    assert not taxonomy.is_attack_action("Attack", "none")   # Extra Attack follow-up
    assert not taxonomy.is_attack_action("Magic", "none")    # War-Magic True Strike

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


def test_choice_spell_attack_explicit_origin():
    # Guiding Bolt: a Magic-modality attack delivered via an attack roll, ranged.
    # origin / modality / range_ are set explicitly at the call site.
    ch = Choice(action_type="attack", cost="action", origin="spell",
                modality="Magic", damage_type="radiant",
                weapon_stat="spell_attack_bonus", range_="ranged")
    assert ch.resolution == "attack_roll"
    assert ch.modality == "Magic"
    assert ch.origin == "spell"
    assert ch.range_ == "ranged"
    assert taxonomy.is_attack(ch.resolution)         # "an attack" in the rules sense
    assert not taxonomy.is_attack_action(ch.modality, ch.cost)   # Magic, not the Attack action


def test_choice_unarmed_attack_explicit_origin():
    ch = Choice(action_type="attack", cost="none", origin="unarmed")
    assert ch.origin == "unarmed"
    assert ch.range_ == "melee"


def test_choice_feature_attack_explicit_origin():
    # Starry-Form Archer: a magical FEATURE (not a spell) making a ranged attack.
    # Without the legacy weapon_stat derivation, origin is set explicitly.
    ch = Choice(action_type="attack", cost="bonus_action", origin="feature",
                weapon_stat="spell_attack_bonus", damage_type="radiant",
                damage_dice=(1, 8), range_="ranged")
    assert ch.origin == "feature"
    assert not taxonomy.is_spell_origin(ch.origin)   # a feature is NOT a spell (not fuelable)


def test_choice_weapon_attack_with_spell_stat_stays_weapon():
    # The EK / True Strike / Shillelagh gotcha: a WEAPON attack made with the
    # spellcasting stat must set origin="weapon" explicitly — there is no
    # weapon_stat-based derivation that would mis-classify it as a feature now.
    ch = Choice(action_type="attack", cost="action", origin="weapon",
                weapon_stat="spell_attack_bonus", damage_dice=(1, 10))
    assert ch.origin == "weapon"
    assert taxonomy.is_physical(ch.origin)


def test_choice_save_spell_explicit_origin():
    # Burning Hands: Magic modality, resolved by a saving throw, spell origin.
    ch = Choice(action_type="save_spell", cost="action", save_stat="dex_save",
                damage_dice=(3, 6), damage_type="fire", origin="spell",
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
