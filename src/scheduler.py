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
    SaveDamageEvent,
    TurnStartEvent,
    make_tick,
)
from .verbs import resolve_attack_roll, resolve_damage, resolve_save_damage, resolve_saving_throw
from .taxonomy import is_spell_origin

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
        enemy_ids: "set[int] | None" = None,
    ) -> None:
        self.rng = rng
        self.entities = entities
        self.policies = policies
        self.max_rounds = max_rounds
        # Finite-HP combat termination (the emergent-length capacity axis).  When a set
        # of opposition entity ids is given, the combat ENDS the moment they are all
        # functionally dead (hp <= 0) rather than always running the full max_rounds —
        # so fight LENGTH becomes an emergent output (see rounds_elapsed).  Default
        # None = the legacy fixed-length model (enemy on the threshold model / inf HP),
        # which keeps every prior combat byte-identical.  max_rounds stays the cap.
        self._enemy_ids: "set[int] | None" = set(enemy_ids) if enemy_ids else None
        # How many rounds this combat actually ran (== max_rounds in the legacy model;
        # < max_rounds when the enemy dropped early in finite-HP mode).  Set by run().
        self.rounds_elapsed: int = 0

        self.queue = EventQueue()
        self._registry: dict[str, list[Handler]] = {}
        # Current turn's action economy; (re)set at each TurnStartEvent.  Lives
        # here (not as a local in _handle_turn_start) so mid-turn decision points
        # during resolution can read/consume it (e.g. smite spending the BA).
        self._turn_economy: dict[str, int] = dict(DEFAULT_RESOURCES)
        self._damage_log: list[int] = []  # total damage dealt each round
        # Per-entity damage received log: entity_id → list[int] per round.
        # Populated as DamageEvents resolve; callers read it after run().
        self.damage_received: dict[int, list[int]] = {
            e.id: [] for e in entities
        }
        self._round_damage_received: dict[int, int] = {
            e.id: 0 for e in entities
        }
        # Per-(source, target) damage ledger — CUMULATIVE total per (source_id,
        # target_id) across this combat (NOT per-round; the runner sums across
        # combats).  The foundation for multi-entity DPR accounting (substrate #7 /
        # design.md §8): attribute every DamageEvent to WHO dealt it and WHO took it,
        # so the runner can report the build's own column (source == character)
        # separately from a party/roster total once allies also deal damage.  In the
        # single-entity case the character only ever damages the dummy, so the
        # character's column here equals its damage_received[dummy] number — the
        # invariant that keeps the prior test corpus bit-comparable.
        self.damage_by_source_target: dict[tuple[int, int], int] = {}

        # Active zones (substrate #7 / 7b — design.md §3.1).  name → Zone Object,
        # installed by a cast_effect's `zones` payload.  At each entity's turn
        # boundary the scheduler fires every damaging zone the entity is inside on it
        # (_fire_zone_effects), so the "recurring zone event" falls out of turns
        # recurring each round (CLAUDE.md #5: a trigger on the TurnStartEvent).  The
        # registry is per-combat (a fresh Scheduler each fight); a Spirit-Guardians-
        # style emanation is recast each combat under the combat-clock model, and a
        # dropped concentration marks its Zone `destroyed` mid-combat.
        self.zones: dict[str, object] = {}

        # Register the verb handlers.  save_damage uses the plain 4-arg Handler
        # signature, so the generic dispatch branch in run() drives it — it
        # enqueues a DamageEvent that is accounted when that event resolves.
        self._subscribe("attack_roll", resolve_attack_roll)  # type: ignore[arg-type]
        self._subscribe("damage", resolve_damage)            # type: ignore[arg-type]
        self._subscribe("save_damage", resolve_save_damage)  # type: ignore[arg-type]

        # Seed the queue with Round 1 turn starts
        self._enqueue_round(round_=1)

    # ------------------------------------------------------------------
    # Subscription (internal wiring — external callers can use this later
    # for trigger subscribers, e.g. on_hit, incoming_attack)
    # ------------------------------------------------------------------

    def _subscribe(self, kind: str, handler: Handler) -> None:
        self._registry.setdefault(kind, []).append(handler)

    # ------------------------------------------------------------------
    # Live-roster mutation (the create_entity / destroy_entity verbs,
    # substrate #7 — design.md §4 #12).  Keep the per-combat damage ledgers
    # in sync when an entity winks in/out of a combat already in progress.
    # ------------------------------------------------------------------

    def add_entity(self, entity: "Entity", policy: "Policy | None" = None) -> None:
        """create_entity against the LIVE combat: add a summon to this scheduler's
        roster and damage ledgers so it can deal/take damage immediately.  If it has
        its own policy it is registered, but its turns are NOT spliced into the round
        already in flight (a mid-combat conjure-style summon that must act THIS round
        is deferred — see summons.py); a COMMANDED summon (policy=None) needs no
        turn slot, so the primal-companion case is fully covered."""
        from .summons import create_entity
        create_entity(self.entities, self.policies, entity, policy)
        self.damage_received.setdefault(entity.id, [])
        self._round_damage_received.setdefault(entity.id, 0)

    def remove_entity(self, entity: "Entity") -> None:
        """destroy_entity against the LIVE combat: drop a summon from the roster and
        policies (its accumulated damage ledger entries are kept for accounting)."""
        from .summons import destroy_entity
        destroy_entity(self.entities, self.policies, entity)

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
                # resolve_damage returns (total_damage, next_seq).  The TARGET's
                # failed-save rescue (Indomitable) is offered if a concentration
                # check this damage triggers fails — consults the target's policy.
                handlers = self._registry.get("damage", [])
                seq_counter = seq + 1
                save_decider = self._make_save_reroll_decider(event)
                # The CASTER's post-damage rider (Fueled Spellfire) — consults the
                # ACTOR's policy as this damage resolves.
                rider_decider = self._make_deal_damage_decider(event)
                for handler in handlers:
                    result = handler(event, self.rng, self.queue, seq_counter, save_decider, rider_decider)  # type: ignore[call-arg]
                    if isinstance(result, tuple):
                        total_dmg, seq_counter = result
                        round_damage += total_dmg
                        if event.target is not None:
                            if event.target.id in self._round_damage_received:
                                self._round_damage_received[event.target.id] += total_dmg
                            # Attribute this damage to its (source, target) pair.
                            key = (event.actor.id, event.target.id)
                            self.damage_by_source_target[key] = (
                                self.damage_by_source_target.get(key, 0) + total_dmg
                            )
                    else:
                        seq_counter = result

            elif isinstance(event, AttackRollEvent):
                handlers = self._registry.get("attack_roll", [])
                seq_counter = seq + 1
                # The ACTING entity's post-roll riders (Guided Strike / Wrathful
                # Smite / bluff) are suppressed for rider attacks (policy_riders
                # =False) such as the Flourish Counter, which carries its own
                # bleed and must not spawn further riders.
                if event.policy_riders:
                    decider = self._make_miss_decider(event)
                    hit_decider = self._make_hit_decider(event)
                else:
                    decider = None
                    hit_decider = None
                # The DEFENDER's in-flight interceptor (Flourish Parry / Shield)
                # is always offered — it consults the TARGET's policy, orthogonal
                # to the attacker's riders.
                intercept_decider = self._make_intercept_decider(event)
                for handler in handlers:
                    seq_counter = handler(event, self.rng, self.queue, seq_counter, decider, hit_decider, intercept_decider)  # type: ignore[call-arg]

            elif isinstance(event, SaveDamageEvent):
                # Save-for-damage delivery (an enemy spell, or a damaging zone's
                # recurring save).  Before resolving, query any ally-buff aura the
                # TARGET is inside (substrate #7 / 7b, Circle of Power): a friendly
                # creature inside gets ADVANTAGE on the save and, on a success vs a
                # save-for-half spell, takes NO damage.  Only spells/magic qualify.
                handlers = self._registry.get("save_damage", [])
                seq_counter = seq + 1
                save_adv, negate = self._zone_save_buffs(event.target, event.origin)
                for handler in handlers:
                    seq_counter = handler(  # type: ignore[call-arg]
                        event, self.rng, self.queue, seq_counter,
                        save_advantage=save_adv, negate_on_save=negate,
                    )

            elif isinstance(event, RoundEndEvent):
                log.debug("RoundEndEvent fired, round=%d", round_)

            else:
                # Generic dispatch for future event kinds
                handlers = self._registry.get(event.kind, [])
                seq_counter = seq + 1
                for handler in handlers:
                    seq_counter = handler(event, self.rng, self.queue, seq_counter)  # type: ignore[call-arg]

            # Finite-HP termination: HP only changes inside a DamageEvent handler
            # (take_damage), so by here the latest hit is applied.  Once every
            # opposition entity is functionally dead the combat is over — stop popping
            # events (the rest of this turn / the enemy's queued turns are moot) and let
            # the post-loop block finalise the partial round's accounting.
            if self._enemy_ids is not None and self._all_enemies_dead():
                log.info("Enemy down — combat ends in round %d (emergent length).", current_round)
                break

        # The combat ran through `current_round` (the round of the last processed
        # event), capped at max_rounds.  This is the emergent fight length.
        self.rounds_elapsed = min(current_round, self.max_rounds)

        # Capture last round
        if round_damage > 0 or current_round <= self.max_rounds:
            log.info("--- Round %d ended, total damage this round: %d ---", current_round, round_damage)
            self._damage_log.append(round_damage)
            for eid in self._round_damage_received:
                self.damage_received[eid].append(self._round_damage_received[eid])

        return self._damage_log

    def _all_enemies_dead(self) -> bool:
        """True when every designated opposition entity is functionally dead (hp <= 0).

        Only entities whose id is in ``self._enemy_ids`` AND present in the roster are
        considered; an empty intersection returns False (nothing to end the combat on).
        An inf-HP enemy (mis-set finite-HP mode) never satisfies ``hp <= 0``, so the
        combat simply runs to the cap — a safe degenerate case."""
        present = [e for e in self.entities if e.id in self._enemy_ids]  # type: ignore[operator]
        return bool(present) and all(e.hp <= 0 for e in present)

    # ------------------------------------------------------------------
    # Post-roll decision point: build a miss-decider for one attack
    # ------------------------------------------------------------------

    def _make_miss_decider(self, event: "AttackRollEvent"):
        """Return a `(missed_by) -> bonus` callable for this attack's actor.

        The closure mediates the policy/resolution boundary: resolve_attack_roll
        (resolution) never calls the policy directly — it calls this closure,
        which the scheduler owns.  The closure consults policy.on_miss (if any),
        validates and CONSUMES the resource the policy asked to spend, and
        returns the roll bonus to apply (0 if the policy declines or can't pay).
        """
        from .policy import MissContext

        policy = self.policies.get(event.actor.id)
        on_miss = getattr(policy, "on_miss", None) if policy is not None else None
        if not callable(on_miss):
            return None

        actor = event.actor
        round_ = event.tick[0]
        is_aoo = (event.cost == "reaction")

        def decider(missed_by: int) -> int:
            ctx = MissContext(
                actor=actor,
                target=event.target,
                missed_by=missed_by,
                is_aoo=is_aoo,
                resources=actor.resources.as_dict(),
                round_number=round_,
            )
            response = on_miss(ctx)
            if response is None:
                return 0
            # Validate affordability, then consume.
            if any(actor.resources.available(n) < a
                   for n, a in response.resource_cost.items()):
                return 0
            for n, a in response.resource_cost.items():
                actor.resources.consume(n, a)
            return response.bonus

        return decider

    def _make_hit_decider(self, event: "AttackRollEvent"):
        """Return an `(is_crit) -> list[(n, sides)]` callable for this attack.

        Mirror of `_make_miss_decider` for the on-HIT decision point (Wrathful /
        Divine Smite).  Consults policy.on_hit; validates and consumes BOTH the
        persistent resource (slot) AND the action-economy slot (the bonus action,
        read from the current turn's economy hung on the scheduler); returns the
        extra damage dice to fold into this hit (empty if declined / unaffordable).
        """
        from .policy import HitContext

        policy = self.policies.get(event.actor.id)
        on_hit = getattr(policy, "on_hit", None) if policy is not None else None
        if not callable(on_hit):
            return None

        actor = event.actor
        round_ = event.tick[0]
        cost = event.cost

        def hit_decider(is_crit: bool):
            ba_available = self._turn_economy.get("bonus_action", 0) >= 1
            ctx = HitContext(
                actor=actor,
                target=event.target,
                is_crit=is_crit,
                cost=cost,
                bonus_action_available=ba_available,
                resources=actor.resources.as_dict(),
                round_number=round_,
                origin=event.origin,
                range_=event.range_,
            )
            response = on_hit(ctx)
            if response is None:
                return [], [], []
            # Validate action-economy slot; None means no economy cost (e.g. bluff
            # or a free outgoing rider — Primal Strike / Fount of Moonlight).
            ac = response.action_cost
            if ac is not None and ac in self._turn_economy and self._turn_economy[ac] < 1:
                return [], [], []
            # ...and the persistent resource is affordable.
            if any(actor.resources.available(n) < a
                   for n, a in response.resource_cost.items()):
                return [], [], []
            # Consume action economy (if any), then persistent resources.
            if ac is not None and ac in self._turn_economy:
                self._turn_economy[ac] -= 1
            for n, a in response.resource_cost.items():
                actor.resources.consume(n, a)
            # Apply any self-status (e.g. Brutality::bluff's save advantage),
            # lasting until the end of the actor's next turn (mirrors vex), and
            # consumed earlier by the next qualifying save.
            if response.self_status_on_hit is not None:
                r, t, _ = event.tick
                actor.statuses.apply(response.self_status_on_hit, True, expiry=(r + 2, t))
            # The third element is the substrate-#6 rider damage: separately-typed
            # DamageEvents resolve_attack_roll spawns FROM this hit (see verbs.py).
            return (
                list(response.extra_damage_dice),
                list(response.extra_masteries),
                list(response.rider_damage),
            )

        return hit_decider

    def _make_intercept_decider(self, event: "AttackRollEvent"):
        """Return a `(hit_margin) -> InterceptResponse | None` callable for the
        TARGET's in-flight reaction (intercept_event — Flourish Parry, Shield, Fire
        Shield thorns, and the 7c ally-effects redirect/protect/sanctuary).

        Mirror of the miss/hit deciders, but it consults the DEFENDER's policy
        (event.target), not the attacker's.  The closure calls
        policy.on_incoming_hit; validates and consumes the DEFENDER's resources;
        and hands the WHOLE InterceptResponse back to resolve_attack_roll (refactored
        from a positional 3-tuple to a single response object at the warding-bond
        redirect — the session-12 engine-seam note).  resolve_attack_roll reads the
        riders off it (AC bump / disadvantage / save-or-negate / thorns / redirect).
        None = no interceptor (declined or unaffordable).
        """
        from .policy import IncomingAttackContext

        target = event.target
        if target is None:
            return None
        policy = self.policies.get(target.id)
        on_incoming = getattr(policy, "on_incoming_hit", None) if policy is not None else None
        if not callable(on_incoming):
            return None

        attacker = event.actor
        round_ = event.tick[0]
        cost = event.cost

        def intercept_decider(hit_margin: int):
            ctx = IncomingAttackContext(
                defender=target,
                attacker=attacker,
                hit_margin=hit_margin,
                cost=cost,
                resources=target.resources.as_dict(),
                round_number=round_,
                range_=event.range_,
            )
            response = on_incoming(ctx)
            if response is None:
                return None
            # Validate affordability against the DEFENDER's resources, then
            # consume.  (The reaction itself is the policy's once-per-round gate,
            # not an engine resource — see InterceptResponse.)
            if any(target.resources.available(n) < a
                   for n, a in response.resource_cost.items()):
                return None
            for n, a in response.resource_cost.items():
                target.resources.consume(n, a)
            return response

        return intercept_decider

    def _make_save_reroll_decider(self, event: "DamageEvent"):
        """Return a `(dc, failed_total) -> bonus | None` callable for the failed-
        save rescue (Indomitable), or None if the damage target has no such hook.

        Consults the TARGET's policy (the entity that may have to make a
        concentration save from this damage), mirroring the intercept decider.
        The closure bakes in `save_kind="concentration"` and the round number:
        this damage→concentration path is the only scheduled save today, so the
        D&D specifics live here while resolve_saving_throw stays generic.  When
        scheduled saves arrive (frightened, enemy save-spells) they will build
        their own deciders with their own save_kind.
        """
        from .policy import FailedSaveContext

        target = event.target
        if target is None:
            return None
        policy = self.policies.get(target.id)
        on_failed = getattr(policy, "on_failed_save", None) if policy is not None else None
        if not callable(on_failed):
            return None

        round_ = event.tick[0]

        def save_reroll_decider(dc: int, failed_total: int):
            ctx = FailedSaveContext(
                entity=target,
                save_kind="concentration",
                save_stat="con_save",
                dc=dc,
                save_bonus=int(target.stat("con_save")),
                failed_total=failed_total,
                resources=target.resources.as_dict(),
                round_number=round_,
            )
            response = on_failed(ctx)
            if response is None:
                return None
            if any(target.resources.available(n) < a
                   for n, a in response.resource_cost.items()):
                return None
            for n, a in response.resource_cost.items():
                target.resources.consume(n, a)
            return response.bonus

        return save_reroll_decider

    def _make_deal_damage_decider(self, event: "DamageEvent"):
        """Return a `(damage_type, origin, is_crit) -> list[(n, sides)]` callable
        for the CASTER's post-damage rider (Fueled Spellfire), or None if the
        actor's policy has no such hook.

        Consults the ACTOR's policy (the entity DEALING the damage), mirroring the
        other deciders.  The closure builds the context, calls
        policy.on_deal_damage; validates and consumes the caster's resources;
        returns the dice to fold into this damage roll.  The policy owns the
        gating ("spell radiant damage", 1/turn); the engine stays D&D-agnostic and
        simply offers the seam.  None = no rider for this caster.
        """
        from .policy import DealDamageContext

        actor = event.actor
        policy = self.policies.get(actor.id)
        on_deal = getattr(policy, "on_deal_damage", None) if policy is not None else None
        if not callable(on_deal):
            return None

        round_, turn_idx, _ = event.tick

        def rider_decider(damage_type, origin, is_crit):
            ctx = DealDamageContext(
                actor=actor,
                target=event.target,
                damage_type=damage_type,
                origin=origin,
                is_crit=is_crit,
                base_damage_dice=event.damage_dice,
                resources=actor.resources.as_dict(),
                round_number=round_,
                turn_index=turn_idx,
            )
            response = on_deal(ctx)
            if response is None:
                return []
            if any(actor.resources.available(n) < a
                   for n, a in response.resource_cost.items()):
                return []
            for n, a in response.resource_cost.items():
                actor.resources.consume(n, a)
            return list(response.extra_damage_dice)

        return rider_decider

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

        # Turn-level action economy (action / bonus_action / reaction).  Stored
        # on the scheduler for the duration of this turn so mid-turn decision
        # points (e.g. a smite-on-hit deciding whether the bonus action is still
        # free) can read and consume it during attack RESOLUTION, not just here
        # at decision time.  Reset fresh every turn.
        econ = dict(DEFAULT_RESOURCES)
        self._turn_economy = econ

        # Policy reads a merged view (action economy + persistent pool snapshot).
        resources = dict(econ)
        resources.update(actor.resources.as_dict())

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

        # Recurring zone effects (substrate #7 / 7b): any active damaging zone this
        # entity is currently inside forces its per-turn save at its turn boundary
        # (Spirit Guardians: WIS save vs the owner's DC, 3d8 radiant, half on save),
        # BEFORE the entity acts.  Reuses the save-for-damage path (SaveDamageEvent →
        # resolve_save_damage), attributed to the zone's owner so the caster's zone
        # DPR falls out of the per-(source, target) ledger (like the 7a summon
        # column).  Sequence 0 was the TurnStartEvent itself.
        seq = self._fire_zone_effects(actor, round_, turn_idx, start_seq=1)
        for choice in choices:
            cost = choice.cost

            # --- Action economy check ---
            if cost in econ and econ[cost] < 1:
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
            if cost in econ:
                econ[cost] -= 1

            # --- Consume persistent resources ---
            if choice.resource_cost:
                for name, amount in choice.resource_cost.items():
                    actor.resources.consume(name, amount)

            # The entity that ACTS this choice.  For a COMMANDED action (substrate
            # #7 / 7a — the Beast Master directing the primal companion) the choice
            # carries an `actor` override: the cost was just drained from the
            # commanding `actor` (the master's Bonus Action), but the spawned event's
            # actor is the commanded entity so its stats/damage apply and the damage
            # is attributed to it (its own DPR column).  None → the deciding entity.
            acting = choice.actor or actor

            if choice.action_type == "attack":
                # Build the combined mastery list:
                #   base = mastery_override if set, else weapon's natural mastery
                #   then add any extra_masteries (Brutality, etc.) on top
                base_mastery = choice.mastery_override or acting.base_stats.get("weapon_mastery")
                masteries: list[str] = []
                if base_mastery:
                    masteries.append(base_mastery)
                masteries.extend(choice.extra_masteries)

                # Per-attack damage override (multi-weapon gish): when the Choice
                # carries its own damage_dice, that attack uses it (with its own
                # damage_bonus, defaulting to 0); otherwise both stay None and the
                # resolver reads the actor's single weapon stat as before.
                dmg_dice_override = choice.damage_dice
                dmg_bonus_override = (
                    choice.damage_bonus if choice.damage_dice is not None else None
                )
                atk_event = AttackRollEvent(
                    tick=make_tick(round_, turn_idx, seq),
                    actor=acting,                       # commanded actor (7a) or self
                    target=choice.target,
                    weapon_stat=choice.weapon_stat,
                    cost=cost,
                    masteries=masteries,
                    extra_damage_dice=list(choice.extra_damage_dice),
                    extra_flat_damage=choice.extra_flat_damage,
                    damage_dice_override=dmg_dice_override,
                    damage_bonus_override=dmg_bonus_override,
                    damage_type=choice.damage_type,
                    min_die=choice.min_die,
                    ignore_resistance=choice.ignore_resistance,
                    origin=choice.origin,
                    range_=choice.range_,
                )
                self.queue.push(atk_event)
                seq += 1
            elif choice.action_type == "save_spell":
                # Save-FOR-damage delivery (Sacred Flame, Burning Hands): the
                # target rolls a save vs our spell DC; resolve_save_damage decides
                # full / half / none and enqueues the DamageEvent.
                save_event = SaveDamageEvent(
                    tick=make_tick(round_, turn_idx, seq),
                    actor=acting,                       # commanded actor (7a) or self
                    target=choice.target,
                    save_stat=choice.save_stat or "dex_save",
                    dc_stat=choice.dc_stat,
                    damage_dice=choice.damage_dice or (1, 8),
                    damage_bonus=choice.damage_bonus,
                    on_save=choice.on_save,
                    damage_type=choice.damage_type,
                    min_die=choice.min_die,
                    ignore_resistance=choice.ignore_resistance,
                    origin=choice.origin,
                    cost=cost,
                )
                self.queue.push(save_event)
                seq += 1
            elif choice.action_type == "cast_effect":
                # First-class non-damaging cast (buff/debuff): the action economy
                # and resources were already drained above.  Install the persisting
                # effect and push NO event (no roll, no damage).  See
                # design/buff_primitive.md.
                #   - application_save (debuff-only) → the BEARER rolls to resist
                #     vs the CASTER's DC; a made save negates the whole payload;
                #   - modifiers → the BEARER's ModifierStack (an explicit target =
                #     a debuff, else the actor = a self-buff); combat-clock sources
                #     are noted for the combat-boundary sweep;
                #   - statuses → the BEARER's StatusSet (substrate #3 — these are
                #     swept unconditionally by StatusSet.clear at the boundary);
                #   - concentration → recorded on the ACTOR;
                #   - capability buffs carry no payload (the policy reads its flag).
                bearer = choice.target or actor

                # Debuff resist roll (reuses the save machinery — debuffs are the
                # same primitive, target-parameterised).  A made save negates the
                # whole effect; the cast still happened (economy/resources spent).
                resisted = False
                if choice.application_save is not None:
                    appsave = choice.application_save
                    dc = int(actor.stat(appsave.dc_stat))
                    made = resolve_saving_throw(bearer, appsave.save_stat, dc, self.rng)
                    resisted = made and appsave.on_success == "negate"

                if not resisted:
                    for mod in choice.modifiers:
                        bearer.add_modifier(mod)
                    for spec in choice.statuses:
                        bearer.statuses.apply(spec.name, spec.value, spec.expiry)
                        # Index the status under effect_source so remove_effect
                        # (concentration break) can drop it with the rest of the
                        # bundle, not only the unconditional boundary sweep.
                        if choice.effect_source:
                            bearer.note_effect_status(choice.effect_source, spec.name)
                    # Damage-type responses (substrate #4 — Fire Shield resist):
                    # installed on the bearer under effect_source; add_damage_response
                    # notes the source so the boundary sweep clears it.
                    if choice.damage_response and choice.effect_source:
                        bearer.add_damage_response(choice.effect_source, choice.damage_response)
                    # Note the source for the combat-boundary sweep so remove_effect
                    # tears down the whole bundle together: modifiers are not
                    # auto-swept, and although statuses ARE cleared by StatusSet.clear,
                    # noting the source also clears the _effect_statuses index entry
                    # (and lets a status-only combat buff drop via the same path).
                    if (
                        (choice.modifiers or choice.statuses)
                        and choice.effect_source
                        and choice.duration == "combat"
                    ):
                        bearer.note_combat_buff(choice.effect_source)
                    # Concentration always lives on the CASTER; record the source on
                    # the ACTOR too so the actor's own boundary sweep drops it (the
                    # bearer may be a different entity for a debuff).
                    if choice.concentration and choice.effect_source:
                        actor.concentration = choice.effect_source
                        actor.note_combat_buff(choice.effect_source)
                    # Summons (substrate #7 / 7a): create_entity each into the LIVE
                    # combat, labelled under effect_source so remove_effect winks them
                    # out with the rest of the bundle.  (Silvertail's permanent
                    # companion is summoned at DAY START via the runner instead — this
                    # mid-combat branch is the general verb, built + lightly exercised.)
                    for spec in choice.summons:
                        self.add_entity(spec.entity, spec.policy)
                        if choice.effect_source:
                            actor.note_effect_summon(choice.effect_source, spec.entity)
                            actor.note_combat_buff(choice.effect_source)
                    # Zones (substrate #7 / 7b): register each created zone Object in
                    # the live registry so it fires on occupants at their turn
                    # boundaries (_fire_zone_effects).  Labelled under effect_source so
                    # remove_effect (concentration drop / boundary sweep) marks it
                    # destroyed and the emanation winks out with the bundle.
                    for zone in choice.zones:
                        self.zones[zone.name] = zone
                        if choice.effect_source:
                            actor.note_effect_zone(choice.effect_source, zone)
                            actor.note_combat_buff(choice.effect_source)
                # No event enqueued — seq is not advanced.
            else:
                log.warning("Unknown action_type %r — skipped.", choice.action_type)

        return 0  # damage accumulates when DamageEvents resolve

    # ------------------------------------------------------------------
    # Recurring zone effects (substrate #7 / 7b — design.md §3.1)
    # ------------------------------------------------------------------

    def _fire_zone_effects(
        self, actor: "Entity", round_: int, turn_idx: int, start_seq: int = 1
    ) -> int:
        """Fire every active damaging zone *actor* is currently inside, at the start
        of its turn (the recurring zone trigger — CLAUDE.md #5: a synchronous trigger
        on the TurnStartEvent, recurring because turns recur each round).

        For each zone whose ``contains(actor)`` holds (actor shares the zone's
        location and is not the owner / not designated-unaffected), enqueue a
        ``SaveDamageEvent`` from the zone's OWNER to the actor — reusing the
        save-for-damage path (the target rolls the zone's save vs the owner's DC;
        half on a save).  Spirit Guardians' "a creature makes this save only once per
        turn" falls out: we fire once, at the actor's turn boundary.

        Returns the next available sequence number so the choice loop continues past
        the zone events.
        """
        seq = start_seq
        for zone in self.zones.values():
            # Buff-only auras (effect is None — Circle of Power) fire nothing; they are
            # queried at save resolution instead (see _zone_save_buffs).
            if getattr(zone, "destroyed", False) or getattr(zone, "effect", None) is None:
                continue
            if not zone.contains(actor):
                continue
            eff = zone.effect
            self.queue.push(SaveDamageEvent(
                tick=make_tick(round_, turn_idx, seq),
                actor=zone.owner,                   # attributed to the caster (zone DPR)
                target=actor,                       # the occupant rolls the save
                save_stat=eff.save_stat,
                dc_stat=eff.dc_stat,
                damage_dice=eff.damage_dice,
                damage_bonus=eff.damage_bonus,
                on_save=eff.on_save,
                damage_type=eff.damage_type,
                origin=eff.origin,
                cost="none",
            ))
            seq += 1
            log.info(
                "  zone %r assails %s (save %s vs %s's DC)",
                zone.name, actor.name, eff.save_stat, zone.owner.name,
            )
        return seq

    def _zone_save_buffs(self, target: "Entity | None", origin: "str | None"):
        """Buff-aura query (substrate #7 / 7b, Circle of Power): does an active
        ally-buff zone the *target* is inside grant it advantage on this save and/or
        negate damage on a successful save?

        Returns ``(save_advantage, negate_on_save)``.  Only spells / magical effects
        qualify ("advantage on saving throws against spells and other magical
        effects") — a non-spell save (a trap, an enemy's natural breath that is not
        magical) is unaffected.  Computed here because the scheduler owns the live zone
        registry; the flags are threaded into ``resolve_save_damage``.
        """
        if target is None or not is_spell_origin(origin):
            return (False, False)
        advantage = False
        negate = False
        for zone in self.zones.values():
            buff = getattr(zone, "buff", None)
            if buff is None or getattr(zone, "destroyed", False):
                continue
            if zone.affects(target):
                advantage = advantage or buff.save_advantage_vs_magic
                negate = negate or buff.success_negates_half
        return (advantage, negate)

    # ------------------------------------------------------------------
    # Round seeding
    # ------------------------------------------------------------------

    def _enqueue_round(self, round_: int) -> None:
        """Push TurnStartEvents for every entity that has a policy."""
        for turn_idx, entity in enumerate(self.entities):
            if entity.destroyed:
                continue  # a summon that has winked out takes no turns (design.md §1)
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
