"""
taxonomy.py — the attack/action MODALITY taxonomy (the closed vocabularies).

This module is the single source of truth for the vocabulary that describes
*what a character does on its turn* and *how that thing is resolved*.  It exists
to undo a long-standing conflation in the codebase (and in casual D&D speech) of
the word **action**, which was doing double duty as both:

  (a) the economy COST of doing something (you have one action, one bonus action,
      one reaction, your movement, per turn); and
  (b) the THING you are doing ("the attack action", "the magic action").

Those are independent.  Using your *bonus action* to attack (e.g. a Cunning
Action / off-hand swing) is still the **Attack modality** — but it is NOT "the
Attack action", because no *action* (economy sense) was spent.  Likewise a
quickened spell is the **Magic modality** at a bonus-action cost.  So we reserve
the word **action** for the economy cost and use **modality** for the thing done.

The taxonomy has two PRIMARY axes (every Choice has both) and four DESCRIPTORS
(present only when meaningful):

  PRIMARY
    - modality:   what the character is doing (Attack, Magic, Use Ability, Dash …)
    - cost:       the action-economy resource it spends (action, bonus_action …)

  DESCRIPTORS
    - resolution: how the effect is evaluated — attack_roll / saving_throw /
                  automatic.  (The 2024 rules call any resolution==attack_roll
                  thing "an attack", regardless of modality — that is why a
                  Guiding Bolt spell counts as "an attack" for riders/advantage
                  but Sacred Flame, a saving_throw spell, does not.)
    - origin:     the source of a damaging / save-forcing ability — weapon,
                  unarmed, spell, or feature.  `physical` = {weapon, unarmed};
                  `spell` damage (the Fueled Spellfire / Elemental Adept gate) is
                  origin == "spell" SPECIFICALLY — a magical *feature* (e.g.
                  Starry-Form Archer's radiant) is origin == "feature", which is
                  magical but NOT a spell, so it is correctly not fuelable.
    - range:      melee / ranged — only for resolution == attack_roll abilities.
                  All unarmed strikes are melee (true for every modelled build).
    - damage_type: one of the 13 core types — only for damaging abilities.

Derived predicates (helpers below) — NOT stored, computed from the axes:
    is_attack        := resolution == "attack_roll"   (the rules' "an attack")
    attack_action    := modality == "Attack" and cost == "action"
    is_physical      := origin in {"weapon", "unarmed"}
    is_spell_origin  := origin == "spell"

DEFERRED (named here, not yet carried as data):
    - a `magical` flag distinct from origin.  Under the 2024 rules monsters no
      longer resist "nonmagical" B/P/S (resistances are flat by damage type), so
      magical-vs-nonmagical earns nothing for resistance math today — add it only
      when a feature forces it.
    - splitting `feature` origin into magical-feature vs nonmagical-feature
      (e.g. a Sea-druid's Wrath of the Sea vs a Phantom-rogue's Wails from the
      Grave).  Irrelevant to the near-term builds.
    - the non-combat modalities (Influence / Study / Search / Hide-as-skill) are
      NAMED for a closed vocabulary but given no resolution machinery — they
      never touch DPR.

This module carries vocabulary + pure predicates ONLY.  It imports nothing from
the engine, so any layer may depend on it.
"""

from __future__ import annotations

from typing import Literal

# ---------------------------------------------------------------------------
# PRIMARY axis 1 — modality (what the character is doing)
# ---------------------------------------------------------------------------
# The full PHB (2024) set of things that cost an action-economy resource, plus
# "Use Ability" (our addition: a non-magical class/subclass feature — Rage,
# Second Wind, Steady Aim — that does something for an economy cost but is
# neither an attack nor magic).  By default every modality costs an *action*;
# features can change the cost (Cunning Action → bonus action, Quicken → bonus
# action, War Magic → replace one Attack-modality swing with a Magic cantrip).
Modality = Literal[
    "Attack",       # attack with a weapon or an unarmed strike
    "Magic",        # cast a spell, use a magic item, or use a magical feature
    "Use Ability",  # use a non-magical class/subclass feature (Rage, Second Wind)
    "Dash",
    "Disengage",
    "Dodge",
    "Help",
    "Hide",
    "Influence",
    "Ready",
    "Search",
    "Study",
    "Utilize",
]

MODALITIES: tuple[str, ...] = (
    "Attack", "Magic", "Use Ability", "Dash", "Disengage", "Dodge", "Help",
    "Hide", "Influence", "Ready", "Search", "Study", "Utilize",
)

# The subset that has combat-resolution machinery in the engine.  The rest are
# named (above) for a closed vocabulary but never modelled — they do not touch
# DPR / survivability.
COMBAT_MODALITIES: tuple[str, ...] = (
    "Attack", "Magic", "Use Ability", "Dash", "Disengage", "Dodge", "Help",
    "Ready",
)

# ---------------------------------------------------------------------------
# PRIMARY axis 2 — cost (the action-economy resource spent)
# ---------------------------------------------------------------------------
Cost = Literal["action", "bonus_action", "reaction", "movement", "free", "none"]

COSTS: tuple[str, ...] = (
    "action", "bonus_action", "reaction", "movement", "free", "none",
)

# ---------------------------------------------------------------------------
# DESCRIPTOR — resolution (how the effect is evaluated)
# ---------------------------------------------------------------------------
Resolution = Literal["attack_roll", "saving_throw", "automatic"]

RESOLUTIONS: tuple[str, ...] = ("attack_roll", "saving_throw", "automatic")

# ---------------------------------------------------------------------------
# DESCRIPTOR — origin (the source of damage / a forced save)
# ---------------------------------------------------------------------------
Origin = Literal["weapon", "unarmed", "spell", "feature"]

ORIGINS: tuple[str, ...] = ("weapon", "unarmed", "spell", "feature")

# ---------------------------------------------------------------------------
# DESCRIPTOR — range (only for attack_roll abilities)
# ---------------------------------------------------------------------------
Range = Literal["melee", "ranged"]

RANGES: tuple[str, ...] = ("melee", "ranged")

# ---------------------------------------------------------------------------
# DESCRIPTOR — damage type (the 13 core 2024 types)
# ---------------------------------------------------------------------------
DamageType = Literal[
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
]

DAMAGE_TYPES: tuple[str, ...] = (
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
)


# ---------------------------------------------------------------------------
# Derived predicates (pure functions over the axes — nothing is stored)
# ---------------------------------------------------------------------------

def is_attack(resolution: str | None) -> bool:
    """True if this is "an attack" in the rules sense — it forces an attack
    roll — regardless of modality (Guiding Bolt is a Magic-modality attack)."""
    return resolution == "attack_roll"


def is_attack_action(modality: str | None, cost: str | None) -> bool:
    """True only when the Attack modality is taken with an *action* — the gate
    a number of features key on (e.g. Searing Arc Strike requires that you
    "took the Attack action").  A bonus-action swing is the Attack modality but
    NOT the Attack action."""
    return modality == "Attack" and cost == "action"


def is_physical(origin: str | None) -> bool:
    """True for weapon and unarmed sources (the 'physical' grouping).  Contrast
    `is_spell_origin`; a `feature` origin is neither physical nor a spell."""
    return origin in ("weapon", "unarmed")


def is_spell_origin(origin: str | None) -> bool:
    """True only for an actual spell source — the Fueled Spellfire / Elemental
    Adept gate.  A magical FEATURE (origin == 'feature') is NOT a spell, so it
    does not qualify."""
    return origin == "spell"


# ---------------------------------------------------------------------------
# Back-compat derivation — fill the new axes from the legacy flags
# ---------------------------------------------------------------------------
# During the migration, Choices/events constructed with only the old flags
# (action_type / is_spell / is_unarmed / weapon_stat) still need correct
# taxonomy values.  These derive them so behaviour is unchanged; explicit call
# sites override by passing the new fields directly.

def derive_resolution(action_type: str | None) -> str | None:
    """Map the engine's dispatch discriminator to the resolution descriptor.

    Note these are *related but not identical*: `action_type` also selects the
    install-vs-damage payload (a debuff cast_effect WITH an application_save has
    resolution == 'saving_throw' but still dispatches as 'cast_effect').  This
    derivation gives the primary resolution for the common cases.
    """
    return {
        "attack": "attack_roll",
        "save_spell": "saving_throw",
        "cast_effect": "automatic",
    }.get(action_type or "")


def derive_origin(is_spell: bool, is_unarmed: bool, weapon_stat: str) -> str:
    """Derive the origin from the legacy flags.

    - is_spell            → "spell"   (a spell source)
    - is_unarmed          → "unarmed"
    - weapon_stat is the  → "feature" (a magical/feature attack that is NOT a
      spell-attack stat        spell — e.g. Starry-Form Archer's radiant, which
      but not a spell           uses spell_attack_bonus yet has is_spell=False)
    - otherwise           → "weapon"

    The `feature` case is best-effort from the legacy flags; a feature attack
    that used the plain attack_bonus would derive as "weapon".  Explicit call
    sites should set `origin` directly rather than rely on this.
    """
    if is_spell:
        return "spell"
    if is_unarmed:
        return "unarmed"
    if weapon_stat == "spell_attack_bonus":
        return "feature"
    return "weapon"
