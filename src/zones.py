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
class Zone:
    """A created Object defining a named zone (substrate #7 / 7b).

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
        The recurring ``ZoneEffectSpec`` forced on affected occupants.
    anchored_to:
        For an **emanation**, the entity the zone follows (Spirit Guardians is
        anchored to the caster — it is wherever the caster stands).  None for a
        **static** placed zone (which uses ``location`` instead).
    location:
        A static zone's fixed abstract-zone key.  Ignored when ``anchored_to`` is
        set (an emanation's location is read off the anchor each time).
    unaffected:
        Entity ids the caster designated safe (the owner + its allies) — they are
        never made to save even while standing in the zone.
    destroyed:
        Set True by ``Entity.remove_effect`` when the cast ends; the scheduler
        skips a destroyed zone (and ``contains`` returns False).
    """
    name: str
    owner: "Entity"
    effect_source: str
    effect: ZoneEffectSpec
    anchored_to: "Entity | None" = None
    location: "str | None" = None
    unaffected: set[int] = field(default_factory=set)
    destroyed: bool = False

    def current_location(self) -> "str | None":
        """Which abstract zone this Object currently occupies: the anchor's zone for
        an emanation (it follows the caster), else its fixed ``location``."""
        if self.anchored_to is not None:
            return getattr(self.anchored_to, "zone", DEFAULT_ZONE)
        return self.location

    def contains(self, entity: "Entity") -> bool:
        """Whether *entity* is currently inside this zone AND affected by it — it
        shares the zone's abstract location and is neither the owner nor a
        designated-unaffected ally.  Returns False for a destroyed zone."""
        if self.destroyed:
            return False
        if entity.id == self.owner.id or entity.id in self.unaffected:
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
