"""
summons.py — the create_entity / destroy_entity verbs (design.md §4 #12) and the
SummonSpec cast_effect payload (substrate #7 / 7a — controlled-ally summons).

These are the engine primitive behind a summon: a `cast_effect` whose payload
brings a *new Actor* into the combat — its own Entity (HP / AC / saves /
ModifierStack / ResourcePool / StatusSet — all already supported) and, optionally,
its own policy.  Per design.md §1 a controlled ally either acts on its own turn (an
independent policy) or is COMMANDED by its controller (no policy of its own — the
controller's policy emits the ally's Choices on the controller's turn, via the
`Choice.actor` override).  The primal companion is the COMMANDED case.

Lifecycle is keyed to the `effect_source` label (the same thread the rest of the
cast_effect envelope uses): the source's teardown — combat-boundary sweep or a
dropped concentration — routes through `Entity.remove_effect`, which marks any
summons it spawned `destroyed` so they wink out (design.md §1: "objects and
controlled allies wink in/out").

`create_entity` / `destroy_entity` operate on a plain (entities, policies) roster,
so they work both:
  - at DAY START, out of combat (the runner assembles the day's roster — how the
    silvertail's permanent primal companion is summoned: created once, persists the
    whole day), and
  - MID-COMBAT, against a live Scheduler's roster (Scheduler.add_entity /
    remove_entity keep the per-combat damage ledgers in sync).  The mid-combat path
    is built but lightly exercised; a per-combat conjure-style summon (whose turns
    must be spliced into a round already in flight) is deferred until a build forces
    it (user decision, session 20).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity import Entity


@dataclass
class SummonSpec:
    """A controlled-ally summon, the `summons` payload kind on a cast_effect
    (substrate #7 / 7a; design.md §1, verbs 11/12).

    Fields
    ------
    entity:
        The already-built summon Entity (own HP / AC / saves / economy).
    source:
        The effect_source label that owns this summon's lifecycle — the cast that
        created it.  Entity.remove_effect(source) tears the summon down with the
        rest of the cast's bundle (concentration drop / combat-boundary sweep).
    commander:
        The controller that commands the summon, when it is COMMANDED (acts on the
        controller's turn — the controller's policy emits its Choices).  None for a
        summon that acts independently on its own turn.
    policy:
        The summon's OWN policy when it acts independently; None when commanded
        (the commander's policy drives it) or passive.  Threaded to create_entity
        so an independent summon gets its own turns.
    """
    entity: "Entity"
    source: str
    commander: "Entity | None" = None
    policy: "object | None" = None


def create_entity(
    entities: list["Entity"],
    policies: dict[int, object],
    entity: "Entity",
    policy: "object | None" = None,
) -> "Entity":
    """Verb 12 (design.md §4): bring an Object or controlled ally into existence —
    add it to the roster (and register its policy if it acts independently).

    Operates on the (entities, policies) pair the runner / scheduler hold, so the
    same verb summons at day start (out of combat) or mid-combat.  Idempotent: a
    no-op if the entity is already present.  Clears any prior `destroyed` mark so a
    re-summon (e.g. the primal companion recovered on a long rest) reanimates.
    """
    entity.destroyed = False
    if entity not in entities:
        entities.append(entity)
    if policy is not None:
        policies[entity.id] = policy
    return entity


def destroy_entity(
    entities: list["Entity"],
    policies: dict[int, object],
    entity: "Entity",
) -> None:
    """Verb 12 (design.md §4): remove a created entity from existence — drop it from
    the roster and its policy registration, and mark it `destroyed` (so anything
    still holding a reference — a controller about to command it — can tell it is
    gone).  A no-op if it was never in the roster."""
    entity.destroyed = True
    if entity in entities:
        entities.remove(entity)
    policies.pop(entity.id, None)
