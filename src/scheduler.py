"""
scheduler.py — The Scheduler: discrete-event loop + subscriber registry.

Design contract (CLAUDE.md §5):
  "A time-ordered queue of future events (pop earliest → process → maybe
   enqueue more → repeat) plus a subscriber registry for synchronous triggers."

The Scheduler owns:
  - The EventQueue
  - The subscriber registry: dict[event_kind → list[handler]]
  - The SeededRNG (shared across all handlers)
  - The per-turn resource pools (reset each TurnStartEvent)
  - The sequence counter within a turn

The main loop (run):
  1. Pop earliest event
  2. If TurnStartEvent → open a decision point (call policy.decide)
     and enqueue one AttackRollEvent per Choice returned
  3. Otherwise → dispatch to all registered handlers for that event kind
  4. Repeat until the queue is empty or max_rounds is reached

Policy is called ONLY at decision points.  Handlers NEVER call policy.
The sequence counter is managed here; handlers receive it and return it
so they can push follow-on events with the next valid sequence number.
"""

from __future__ import annotations

import logging
from typing import Callable, TYPE_CHECKING

from .events import (
    AttackRollEvent,
    DamageEvent,
    EventQueue,
    RoundEndEvent,
    TurnStartEvent,
    make_tick,
)
from .verbs import resolve_attack_roll, resolve_damage

if TYPE_CHECKING:
    from .entity import Entity
    from .events import Event
    from .policy import GameState, Policy
    from .rng import SeededRNG

log = logging.getLogger(__name__)

# Type alias for a verb handler callable.
# Signature: (event, rng, queue, next_sequence) → int (updated next_sequence)
Handler = Callable[["Event", "SeededRNG", EventQueue, int], int]


# Default resource pool for one entity's turn.
DEFAULT_RESOURCES = {
    "action": 1,
    "bonus_action": 1,
    "reaction": 1,
}


class Scheduler:
    """Discrete-event scheduler.

    Parameters
    ----------
    rng:
        The shared seeded RNG.  All dice everywhere go through this.
    entities:
        Ordered list of entities that take turns each round.  Turn order
        follows list order (initiative is outside scope for now).
    policies:
        Dict mapping entity id → Policy.  Entities without a policy entry
        take no actions (e.g. the infinite-HP dummy).
    max_rounds:
        Stop after this many rounds even if the queue still has events.
    """

    def __init__(
        self,
        rng: "SeededRNG",
        entities: list["Entity"],
        policies: dict[int, "Policy"],
        max_rounds: int = 3,
    ) -> None:
        self.rng = rng
        self.entities = entities
        self.policies = policies
        self.max_rounds = max_rounds

        self.queue = EventQueue()
        self._registry: dict[str, list[Handler]] = {}
        self._damage_log: list[int] = []  # total damage dealt each round
        # Per-entity damage received log: entity_id → list[int] per round.
        # Populated as DamageEvents resolve; callers read it after run().
        self.damage_received: dict[int, list[int]] = {
            e.id: [] for e in entities
        }
        self._round_damage_received: dict[int, int] = {
            e.id: 0 for e in entities
        }

        # Register the two milestone verb handlers
        self._subscribe("attack_roll", resolve_attack_roll)  # type: ignore[arg-type]
        self._subscribe("damage", resolve_damage)            # type: ignore[arg-type]

        # Seed the queue with Round 1 turn starts
        self._enqueue_round(round_=1)

    # ------------------------------------------------------------------
    # Subscription (internal wiring — external callers can use this later
    # for trigger subscribers, e.g. on_hit, incoming_attack)
    # ------------------------------------------------------------------

    def _subscribe(self, kind: str, handler: Handler) -> None:
        self._registry.setdefault(kind, []).append(handler)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> list[int]:
        """Run the simulation.  Returns the per-round damage log.

        The damage log is a flat list of every damage instance recorded.
        Callers (or tests) aggregate it however they like.
        """
        current_round = 1
        round_damage: int = 0

        while self.queue:
            event = self.queue.pop()
            round_, turn_idx, seq = event.tick

            # Safety: don't run past max_rounds
            if round_ > self.max_rounds:
                log.info("Reached max_rounds=%d, stopping.", self.max_rounds)
                break

            # Transition to new round
            if round_ > current_round:
                log.info("--- Round %d ended, total damage this round: %d ---", current_round, round_damage)
                self._damage_log.append(round_damage)
                round_damage = 0
                for eid in self._round_damage_received:
                    self.damage_received[eid].append(self._round_damage_received[eid])
                    self._round_damage_received[eid] = 0
                current_round = round_

            # Dispatch
            if isinstance(event, TurnStartEvent):
                round_damage += self._handle_turn_start(event)

            elif isinstance(event, DamageEvent):
                # resolve_damage returns (total_damage, next_seq)
                handlers = self._registry.get("damage", [])
                seq_counter = seq + 1
                for handler in handlers:
                    result = handler(event, self.rng, self.queue, seq_counter)  # type: ignore[call-arg]
                    if isinstance(result, tuple):
                        total_dmg, seq_counter = result
                        round_damage += total_dmg
                        if event.target is not None and event.target.id in self._round_damage_received:
                            self._round_damage_received[event.target.id] += total_dmg
                    else:
                        seq_counter = result

            elif isinstance(event, AttackRollEvent):
                handlers = self._registry.get("attack_roll", [])
                seq_counter = seq + 1
                for handler in handlers:
                    seq_counter = handler(event, self.rng, self.queue, seq_counter)  # type: ignore[call-arg]

            elif isinstance(event, RoundEndEvent):
                log.debug("RoundEndEvent fired, round=%d", round_)

            else:
                # Generic dispatch for future event kinds
                handlers = self._registry.get(event.kind, [])
                seq_counter = seq + 1
                for handler in handlers:
                    seq_counter = handler(event, self.rng, self.queue, seq_counter)  # type: ignore[call-arg]

        # Capture last round
        if round_damage > 0 or current_round <= self.max_rounds:
            log.info("--- Round %d ended, total damage this round: %d ---", current_round, round_damage)
            self._damage_log.append(round_damage)
            for eid in self._round_damage_received:
                self.damage_received[eid].append(self._round_damage_received[eid])

        return self._damage_log

    # ------------------------------------------------------------------
    # Decision point: TurnStartEvent handling
    # ------------------------------------------------------------------

    def _handle_turn_start(self, event: TurnStartEvent) -> int:
        """Open a decision point for event.actor, enqueue their choices.

        Returns the total damage dealt this turn (0 at decision time —
        damage events resolve later in the same sequence).
        """
        from .policy import GameState

        actor = event.actor
        round_, turn_idx, _ = event.tick

        log.info("=== Turn start: %s (round=%d, turn=%d) ===", actor.name, round_, turn_idx)

        # Expire tick-based statuses on ALL entities at this turn boundary.
        # (A status set to expire at the applier's next turn is keyed to that
        # turn's (round, turn_index), which may belong to a different entity
        # than the one acting now — so we sweep everyone.)
        for ent in self.entities:
            ent.statuses.expire(round_, turn_idx)

        policy = self.policies.get(actor.id)
        if policy is None:
            log.debug("%s has no policy, skipping turn.", actor.name)
            return 0

        # Build read-only snapshot
        enemies = tuple(e for e in self.entities if e.id != actor.id)
        allies: tuple = ()  # single-actor milestone; expand later

        # Merge turn-level action economy with actor's persistent resources.
        # Policy reads the merged dict; scheduler tracks action economy locally.
        resources = dict(DEFAULT_RESOURCES)  # fresh per-turn action economy
        resources.update(actor.resources.as_dict())  # persistent pool (read view)

        snapshot = GameState(
            actor=actor,
            enemies=enemies,
            allies=allies,
            round_number=round_,
            turn_index=turn_idx,
            tick=(round_, turn_idx, 0),
            resources=resources,
        )

        choices = policy.decide(snapshot)
        log.debug("%s policy returned %d choice(s).", actor.name, len(choices))

        # Enqueue one event per choice, consuming resources as we go
        seq = 1  # sequence 0 was the TurnStartEvent itself
        for choice in choices:
            cost = choice.cost

            # --- Action economy check ---
            if cost in resources and resources[cost] < 1:
                log.warning(
                    "%s tried to spend %s but none remaining — choice skipped.",
                    actor.name, cost,
                )
                continue

            # --- Persistent resource check ---
            if choice.resource_cost:
                can_afford = all(
                    actor.resources.available(name) >= amount
                    for name, amount in choice.resource_cost.items()
                )
                if not can_afford:
                    log.warning(
                        "%s cannot afford resource_cost %r — choice skipped.",
                        actor.name, choice.resource_cost,
                    )
                    continue

            # --- Consume action economy ---
            if cost in resources:
                resources[cost] -= 1

            # --- Consume persistent resources ---
            if choice.resource_cost:
                for name, amount in choice.resource_cost.items():
                    actor.resources.consume(name, amount)

            if choice.action_type == "attack":
                # Build the combined mastery list:
                #   base = mastery_override if set, else weapon's natural mastery
                #   then add any extra_masteries (Brutality, etc.) on top
                base_mastery = choice.mastery_override or actor.base_stats.get("weapon_mastery")
                masteries: list[str] = []
                if base_mastery:
                    masteries.append(base_mastery)
                masteries.extend(choice.extra_masteries)

                atk_event = AttackRollEvent(
                    tick=make_tick(round_, turn_idx, seq),
                    actor=actor,
                    target=choice.target,
                    weapon_stat=choice.weapon_stat,
                    cost=cost,
                    masteries=masteries,
                )
                self.queue.push(atk_event)
                seq += 1
            else:
                log.warning("Unknown action_type %r — skipped.", choice.action_type)

        return 0  # damage accumulates when DamageEvents resolve

    # ------------------------------------------------------------------
    # Round seeding
    # ------------------------------------------------------------------

    def _enqueue_round(self, round_: int) -> None:
        """Push TurnStartEvents for every entity that has a policy."""
        for turn_idx, entity in enumerate(self.entities):
            if entity.id in self.policies:
                self.queue.push(
                    TurnStartEvent(
                        tick=make_tick(round_, turn_idx, 0),
                        actor=entity,
                    )
                )
        # Also enqueue the next round's turns so the loop keeps going
        if round_ < self.max_rounds:
            self._enqueue_round(round_ + 1)
