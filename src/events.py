"""
events.py — Event dataclasses and the EventQueue.

Tick design (decided in session, recorded in PROGRESS.md):
  tick = (round, turn_index, sequence)

  round      — which round of combat (1-based)
  turn_index — global turn counter across all entities this round (0-based)
  sequence   — monotonically increasing within a turn, assigned by the
               scheduler as events are enqueued.  Determines resolution order
               within a turn.  The policy controls order by controlling what
               it emits first — phase (action vs bonus_action) is a *cost tag*
               on the Choice, NOT a position in the tuple.

Reaction events are slotted into the current (round, turn_index) with the
next available sequence number, so they interrupt naturally without a
separate queue lane.

EventQueue wraps a heapq.  Events are popped smallest-tick-first.  Within an
equal tick, event_id (insertion order) is the tiebreaker.
"""

from __future__ import annotations

import heapq
import itertools
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .entity import Entity

log = logging.getLogger(__name__)

_event_id_counter = itertools.count(0)


# ---------------------------------------------------------------------------
# Tick helper
# ---------------------------------------------------------------------------

Tick = tuple[int, int, int]  # (round, turn_index, sequence)


def make_tick(round_: int, turn_index: int, sequence: int) -> Tick:
    return (round_, turn_index, sequence)


# ---------------------------------------------------------------------------
# Base event
# ---------------------------------------------------------------------------

@dataclass
class Event:
    """Base class for all simulation events.

    All events carry a tick (ordering key), a kind string (used by the
    subscriber registry to dispatch to the right handlers), and the actor
    who triggered the event.  target is optional — some events have no target
    (e.g. RoundEndEvent).

    event_id is assigned automatically from a global counter; it is the
    tiebreaker when two events share the same tick, preserving insertion order.
    """

    tick: Tick
    kind: str
    actor: "Entity"
    target: "Entity | None" = None
    event_id: int = field(default_factory=lambda: next(_event_id_counter))

    # Make events sortable by (tick, event_id) for the heapq
    def __lt__(self, other: "Event") -> bool:
        return (self.tick, self.event_id) < (other.tick, other.event_id)

    def __le__(self, other: "Event") -> bool:
        return (self.tick, self.event_id) <= (other.tick, other.event_id)


# ---------------------------------------------------------------------------
# Concrete event types for the "swing at the dummy" milestone
# ---------------------------------------------------------------------------

@dataclass
class TurnStartEvent(Event):
    """Fired at the beginning of an entity's turn.

    The scheduler uses this as the primary decision point: it pops this event,
    calls policy.decide(), and enqueues whatever the policy returns.
    """
    kind: str = field(default="turn_start", init=False)


@dataclass
class AttackRollEvent(Event):
    """Represents one attack roll attempt (one d20 roll against target AC).

    Fields
    ------
    weapon_stat:
        The stat name to look up for the attack bonus, e.g. "attack_bonus".
        Default covers the common case; ranged or spell attacks can override.
    cost:
        Which action economy resource was spent to make this attack.
        One of: "action", "bonus_action", "reaction", "free", "none".
        "none" is used for Extra Attack follow-up swings within the same
        action — the action cost was already paid by the first swing.
    masteries:
        The combined list of mastery properties in effect for this attack,
        e.g. ["sap"] or ["sap", "vex"] (longsword + Brutality::bluff).
        Built by the scheduler from the weapon's natural mastery (or the
        Choice's mastery_override) plus any extra_masteries.  Applied on hit.
    """
    weapon_stat: str = "attack_bonus"
    cost: str = "action"
    masteries: list[str] = field(default_factory=list)
    extra_damage_dice: list[tuple[int, int]] = field(default_factory=list)
    # Flat damage added to this attack's hit beyond the weapon's damage_bonus —
    # e.g. Brutality::bleed's +CHA mod.  Threaded into the DamageEvent (phase 5).
    extra_flat_damage: int = 0
    # Per-attack damage PROFILE override (the multi-weapon gish primitive).  When
    # an entity makes attacks with DIFFERENT dice (quarterstaff 1d8 vs unarmed 1d6
    # vs an Archer-form spell attack 1d8+WIS vs Guiding Bolt 4d6), one
    # actor.stat("damage_dice") no longer suffices.  A Choice may carry its own
    # damage_dice/damage_bonus; the scheduler threads them here.  None → fall back
    # to the actor's weapon stat (every single-weapon build, incl. War Angel, is
    # unchanged — they leave these None).  damage_bonus_override is only consulted
    # when damage_dice_override is set, so an override of +0 (Guiding Bolt) is
    # distinguishable from "no override".
    damage_dice_override: "tuple[int, int] | None" = None
    damage_bonus_override: "int | None" = None
    # Damage type (e.g. "radiant"), threaded to the spawned DamageEvent.
    # Default None = an untyped weapon attack.
    damage_type: "str | None" = None
    # Elemental Adept: per-die floor + resistance bypass, threaded to the spawned
    # DamageEvent (see DamageEvent.min_die / ignore_resistance).  Default off.
    min_die: "int | None" = None
    ignore_resistance: bool = False
    # Modality taxonomy (src/taxonomy.py), threaded from the Choice — the canonical
    # axes the on-hit / defense-side gates read:
    #   origin — weapon / unarmed / spell / feature (the caster-side Fueled-Spellfire
    #     gate keys on origin == "spell"; `weapon_stat` can't tell quarterstaff from
    #     unarmed, nor a weapon attack made with a spell stat from a spell).
    #   range_ — melee / ranged (defense-side gates like Fire-Shield thorns and
    #     Flourish Parry that only fire on MELEE hits read this; the on_hit FoM
    #     rider reads it too — previously these silently assumed melee).
    origin: "str | None" = None
    range_: "str | None" = None
    # Whether the ACTING entity's post-roll decision points (on_miss / on_hit)
    # may fire for this attack.  False for "rider" attacks that are themselves a
    # reaction and must not spawn further riders — e.g. the Flourish Counter,
    # which carries its own bleed and must NOT trigger Wrathful Smite / bluff.
    # (on_miss is already gated off reaction-cost attacks via is_aoo; this flag
    # generalises the suppression and covers on_hit too.)
    policy_riders: bool = True
    kind: str = field(default="attack_roll", init=False)


@dataclass
class DamageEvent(Event):
    """Represents damage being dealt after a confirmed hit.

    Fields
    ------
    is_crit:
        True if the attack roll was a natural 20 (crit).  The damage verb
        doubles the die *count* (not the total) per the phase-order spec.
    damage_dice:
        (n, sides) tuple, e.g. (1, 8) for 1d8.  Pulled from actor.stat()
        by the attack resolver and stored here so the damage verb is
        self-contained.
    damage_bonus:
        Flat bonus to add after rolling, e.g. Strength modifier.
    cost:
        Inherited from the AttackRollEvent that spawned this — just for
        traceability.
    """
    is_crit: bool = False
    damage_dice: tuple[int, int] = (1, 6)  # (n, sides)
    damage_bonus: int = 0
    extra_damage_dice: list[tuple[int, int]] = field(default_factory=list)
    # Extra flat damage beyond damage_bonus (e.g. Brutality::bleed's +CHA mod),
    # added in phase 5 alongside damage_bonus.  Does NOT scale on a crit.
    extra_flat_damage: int = 0
    # Save-for-half: when True, resolve_damage halves the post-phase-5 total
    # (rounded down) — the 2024 "half damage on a successful save" rule (Burning
    # Hands).  Set by resolve_save_damage when a target SAVES against a half-on-
    # save spell; left False for every attack-roll hit and every failed save.
    halved: bool = False
    # Damage type (e.g. "radiant").  Threaded from the source event.  Read by the
    # caster-side post-damage decision point (Fueled Spellfire fires only on SPELL
    # radiant damage — see `origin` below) and available for resistance modeling.
    damage_type: "str | None" = None
    # Elemental Adept (and any future per-die floor / resistance-bypass effect):
    #   min_die — treat any rolled die BELOW this value as this value, applied in
    #     resolve_damage phase 3 to the spell's own dice ("treat any 1 on a damage
    #     die as a 2" → min_die=2).  None = no floor.
    #   ignore_resistance — the source ignores the target's RESISTANCE to this
    #     damage type (phase 7).  Immunity and vulnerability still apply (2024
    #     Elemental Adept bypasses resistance only).  Both default off → inert on
    #     every existing damage path.
    min_die: "int | None" = None
    ignore_resistance: bool = False
    # Modality taxonomy (src/taxonomy.py): the damage's origin — weapon / unarmed
    # / spell / feature.  The caster-side Fueled-Spellfire gate keys on a SPELL
    # origin specifically (a magical FEATURE such as Starry-Form Archer's radiant
    # is origin="feature", not fuelable).
    origin: "str | None" = None
    # Damage REDIRECT (substrate #7 / 7c, Warding Bond): a RedirectSpec set by
    # resolve_attack_roll when the DEFENDER's on_incoming_hit returns one.  After
    # this event's damage resolves, resolve_damage spawns a copy of the taken amount
    # (× fraction) onto redirect.target (the warding caster).  None on every other
    # path.  Typed as a string forward-ref so events.py needn't import policy.py.
    redirect: "object | None" = None
    cost: str = "action"
    kind: str = field(default="damage", init=False)


@dataclass
class SaveDamageEvent(Event):
    """A save-FOR-DAMAGE spell delivery (Sacred Flame, Burning Hands).

    The mirror of AttackRollEvent: instead of the ACTOR rolling d20 vs the
    target's AC, the TARGET rolls a saving throw vs the actor's spell save DC,
    and the save result determines damage.  resolve_save_damage resolves the
    save and (on the appropriate result) enqueues a normal DamageEvent — so the
    entire phase-ordered damage path, concentration check, and save-reroll
    machinery are reused untouched.

    Fields
    ------
    save_stat:
        The TARGET's saving-throw stat, e.g. "dex_save" (Sacred Flame / Burning
        Hands are DEX saves).  Looked up on the target via resolve_saving_throw.
    dc_stat:
        The ACTOR's stat that supplies the save DC — "spell_save_dc" (= 8 + PB +
        casting-mod, stored on the caster's base_stats).
    damage_dice / damage_bonus:
        The spell's damage on a full hit, e.g. (1, 8) for Sacred Flame at L1.
        Carried on the event (NOT pulled from actor.stat("damage_dice"), which is
        the weapon) because a spell's dice differ from the caster's weapon dice.
    on_save:
        "none"  → save NEGATES (Sacred Flame): a successful save deals nothing.
        "half"  → save FOR HALF (Burning Hands): a successful save deals half
                  (the spawned DamageEvent carries halved=True).
        A FAILED save always deals full damage regardless.
    cost:
        Action-economy tag of the cast, for traceability (mirrors AttackRollEvent).
    """
    save_stat: str = "dex_save"
    dc_stat: str = "spell_save_dc"
    damage_dice: tuple[int, int] = (1, 8)
    damage_bonus: int = 0
    on_save: str = "none"
    # Damage type, threaded to the spawned DamageEvent.
    damage_type: "str | None" = None
    # Elemental Adept: per-die floor + resistance bypass, threaded to the spawned
    # DamageEvent (see DamageEvent.min_die / ignore_resistance).  Default off.
    min_die: "int | None" = None
    ignore_resistance: bool = False
    # Modality taxonomy (src/taxonomy.py): a save spell's damage origin — usually
    # "spell" (set at the call site; the caster-side Fueled-Spellfire gate keys on
    # it).  Zone emanations also deliver via this event with origin from the zone.
    origin: "str | None" = None
    cost: str = "action"
    kind: str = field(default="save_damage", init=False)


@dataclass
class RoundEndEvent(Event):
    """Fired after all entities have taken their turns in a round.

    Used to tick duration-based modifiers, reset per-round resources, etc.
    target is always None for this event.
    """
    kind: str = field(default="round_end", init=False)


# ---------------------------------------------------------------------------
# EventQueue
# ---------------------------------------------------------------------------

class EventQueue:
    """Min-heap priority queue ordered by (tick, event_id).

    Usage
    -----
    q = EventQueue()
    q.push(TurnStartEvent(tick=(1, 0, 0), actor=fighter))
    event = q.pop()
    """

    def __init__(self) -> None:
        self._heap: list[Event] = []

    def push(self, event: Event) -> None:
        heapq.heappush(self._heap, event)
        log.debug("Enqueued %s tick=%s actor=%s", event.kind, event.tick, event.actor.name)

    def pop(self) -> Event:
        if not self._heap:
            raise IndexError("pop from empty EventQueue")
        event = heapq.heappop(self._heap)
        log.debug("Popped   %s tick=%s actor=%s", event.kind, event.tick, event.actor.name)
        return event

    def peek(self) -> Event | None:
        return self._heap[0] if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)

    def __bool__(self) -> bool:
        return bool(self._heap)
