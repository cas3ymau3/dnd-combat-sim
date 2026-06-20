"""
zones.py — the 7b ZONE / EMANATION substrate (substrate #7 / 7b; design.md §3.1
zonal spatial model + §4 verbs 11/12).

A zone is a created **Object** (design.md §1: a footprint, no HP / no action
economy — distinct from an Actor like the 7a primal companion) that defines a
named abstract zone (§3.1).  A recurring effect fires on the creatures **inside**
the zone at their turn boundaries (Spirit Guardians: a Wisdom save-for-half, 3d8
radiant — web-verified 2024 text before modeling).

The minimal-but-real spatial model (the scope settled with the user for 7b):

  - **Entity.zone** — each entity occupies ONE abstract zone (§3.1: "each entity
    occupies one of a small number of abstract zones").  Everything shares the
    implicit ``"melee"`` blob by default (the foundation-min slice and 7c ran in
    that single shared zone); ``move_entity`` is the membership-change verb.
  - **Zone** — the Object.  An **emanation** is ``anchored_to`` its owner: it is
    wherever the owner currently stands (``current_location`` reads the anchor's
    zone), so moving the caster moves the aura (Spirit Guardians follows you).  A
    **static** zone (spike growth, walls — a later flavor) sits at a fixed
    ``location`` instead.  ``unaffected`` holds the entity ids the caster
    designated safe (the owner + its allies) — Spirit Guardians "you can designate
    creatures to be unaffected by it".
  - The **recurring firing** lives in the Scheduler: at each entity's turn boundary
    it forces a save on the occupants inside (see ``Scheduler._fire_zone_effects``).
    The recurrence falls out of turns recurring each round (CLAUDE.md #5: triggers
    are subscribers fired synchronously when an event — here a TurnStartEvent —
    resolves); the zone's *duration* is the combat-clock / concentration part,
    swept via ``Entity.remove_effect`` like every other cast_effect bundle.

Lifecycle is keyed to the ``effect_source`` label (the cast_effect thread): a
dropped concentration or the combat-boundary sweep routes through
``Entity.remove_effect``, which marks any zones the cast created ``destroyed`` so
the emanation winks out with the rest of the bundle (design.md §1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity import Entity


# The implicit shared "melee blob" every entity occupies by default (§3.1).  Kept
# in sync with Entity.zone's initial value (entity.py hard-codes the literal to
# avoid an import cycle).
DEFAULT_ZONE = "melee"


@dataclass
class ZoneEffectSpec:
    """The recurring save-for-half effect a damaging zone forces on each affected
    occupant at its turn boundary.

    Defaults describe Spirit Guardians (2024): a Wisdom save vs the owner's spell
    save DC, 3d8 radiant, half on a save.  The same shape carries the other
    save-for-half hazards (cloud of daggers / spike growth — later flavors) by
    swapping the dice / save / type.  Resolved by reusing the save-for-damage path
    (``SaveDamageEvent`` → ``resolve_save_damage``), so the save machinery, crit
    rule (saves never crit), Elemental-Adept hooks, and per-type damage response
    all apply untouched.
    """
    save_stat: str = "wis_save"
    dc_stat: str = "spell_save_dc"
    damage_dice: tuple[int, int] = (3, 8)
    damage_bonus: int = 0
    on_save: str = "half"
    damage_type: "str | None" = None
    is_spell: bool = True


@dataclass
class ZoneBuffSpec:
    """The persistent BUFF an ally-buff aura confers on each FRIENDLY creature inside
    it (substrate #7 / 7b, the BUFF flavor — the mirror of the damaging
    ``ZoneEffectSpec``).

    Defaults describe **Circle of Power** (2024: a **Paladin** 5th-level abjuration —
    web-verified 2026-06-20 before modeling; NOT a Cleric spell, contrary to the old
    design-note attribution): each friendly creature in the 30-ft emanation (including
    the caster) has **advantage on saving throws against spells and other magical
    effects**, and when an affected creature **succeeds on a save vs a spell/effect that
    allows a save for half damage, it takes NO damage** instead of half.

    Unlike a damaging zone (which FIRES a recurring ``SaveDamageEvent`` on the enemies
    inside at their turn boundaries), a buff aura installs nothing and fires nothing: it
    is queried ON DEMAND at save resolution (CLAUDE.md #6 — effective state folds active
    membership), so entering / leaving the aura toggles the benefit with no enter/leave
    trigger needed (the deferred mid-turn "enters the zone" trigger is sidestepped).
    """
    save_advantage_vs_magic: bool = True
    success_negates_half: bool = True


@dataclass
class Zone:
    """A created Object defining a named zone (substrate #7 / 7b).

    A zone is either a **damaging** zone (``effect`` set — a ``ZoneEffectSpec`` it FIRES
    on the enemies inside, via ``contains`` / ``_fire_zone_effects``) or an **ally-buff
    aura** (``buff`` set — a ``ZoneBuffSpec`` it confers on the friendly creatures
    inside, via ``affects``, queried at save resolution).  Spirit Guardians is the
    former; Circle of Power the latter.

    Fields
    ------
    name:
        The zone's registry key (one per active zone in the scheduler registry).
    owner:
        The caster.  Supplies the save DC (its ``spell_save_dc``) and is the
        source the zone's damage is attributed to — so the caster's *zone DPR*
        column falls out of the per-(source, target) ledger for free, exactly like
        the 7a summon column.
    effect_source:
        The cast_effect lifecycle label.  ``Entity.remove_effect(effect_source)``
        marks this zone ``destroyed`` (concentration drop / combat-boundary sweep).
    effect:
        For a **damaging** zone, the recurring ``ZoneEffectSpec`` forced on the
        enemies inside.  None for a buff aura.
    buff:
        For an **ally-buff aura**, the ``ZoneBuffSpec`` conferred on the friendly
        creatures inside.  None for a damaging zone.
    anchored_to:
        For an **emanation**, the entity the zone follows (Spirit Guardians is
        anchored to the caster — it is wherever the caster stands).  None for a
        **static** placed zone (which uses ``location`` instead).
    location:
        A static zone's fixed abstract-zone key.  Ignored when ``anchored_to`` is
        set (an emanation's location is read off the anchor each time).
    unaffected:
        (Damaging zone) entity ids the caster designated safe (the owner + its
        allies) — they are never made to save even while standing in the zone.
    beneficiaries:
        (Buff aura) entity ids of the friendly creatures the aura confers its buff
        on (the caster's allies; the owner always benefits — "including you").
    destroyed:
        Set True by ``Entity.remove_effect`` when the cast ends; the scheduler
        skips a destroyed zone (and ``contains`` / ``affects`` return False).
    """
    name: str
    owner: "Entity"
    effect_source: str
    effect: "ZoneEffectSpec | None" = None
    buff: "ZoneBuffSpec | None" = None
    anchored_to: "Entity | None" = None
    location: "str | None" = None
    unaffected: set[int] = field(default_factory=set)
    beneficiaries: set[int] = field(default_factory=set)
    destroyed: bool = False

    def current_location(self) -> "str | None":
        """Which abstract zone this Object currently occupies: the anchor's zone for
        an emanation (it follows the caster), else its fixed ``location``."""
        if self.anchored_to is not None:
            return getattr(self.anchored_to, "zone", DEFAULT_ZONE)
        return self.location

    def contains(self, entity: "Entity") -> bool:
        """Whether *entity* is an enemy this DAMAGING zone currently assails — it
        shares the zone's abstract location and is neither the owner nor a
        designated-unaffected ally.  Returns False for a destroyed zone or a buff-only
        aura (no ``effect`` payload — use ``affects`` for the buff polarity)."""
        if self.destroyed or self.effect is None:
            return False
        if entity.id == self.owner.id or entity.id in self.unaffected:
            return False
        loc = self.current_location()
        if loc is None:
            return False
        return getattr(entity, "zone", DEFAULT_ZONE) == loc

    def affects(self, entity: "Entity") -> bool:
        """Whether *entity* is a FRIENDLY creature currently benefiting from this buff
        aura — it shares the aura's location AND is the owner or a designated
        beneficiary (Circle of Power: "each friendly creature in the area, including
        you").  The mirror of ``contains`` (which selects the enemies a damaging zone
        assails).  Returns False for a destroyed zone or a non-buff (damaging) zone."""
        if self.destroyed or self.buff is None:
            return False
        if entity.id != self.owner.id and entity.id not in self.beneficiaries:
            return False
        loc = self.current_location()
        if loc is None:
            return False
        return getattr(entity, "zone", DEFAULT_ZONE) == loc


def move_entity(entity: "Entity", to_zone: str) -> None:
    """Verb 11 (design.md §4): change which abstract zone *entity* occupies (§3.1).

    The minimal membership-change verb behind kiting, forced movement, and an enemy
    leaving a hazardous emanation (design.md §3.5: "tries to leave a damaging zone
    at start of turn").  Moving an entity OUT of an emanation's location stops the
    zone firing on it; moving the anchored caster moves the emanation with it.
    """
    entity.zone = to_zone
