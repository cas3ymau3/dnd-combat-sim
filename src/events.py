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
    cost: str = "action"
    kind: str = field(default="damage", init=False)


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
