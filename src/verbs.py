"""
verbs.py — Verb handlers: resolve_attack_roll and resolve_damage.

Design contract (CLAUDE.md §8 — damage resolution phase order):
  1. Determine dice pool — crits double die *count* here
  2. Roll the pool
  3. Per-die mods (reroll, replace, floor) — not wired for milestone
  4. Sum
  5. Flat bonuses

These are the only two verbs needed for the "swing at the dummy" milestone.
They are registered with the Scheduler as handlers for "attack_roll" and
"damage" events respectively.

Each handler receives:
  - the Event that triggered it
  - the SeededRNG instance (all dice go through here)
  - the EventQueue (so it can enqueue follow-on events, e.g. DamageEvent)
  - the current tick (so follow-on events get the right sequence number)

Handlers NEVER call policy.decide().  They resolve what the policy decided.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .events import AttackRollEvent, DamageEvent, make_tick

if TYPE_CHECKING:
    from .events import Event, EventQueue, Tick
    from .rng import SeededRNG

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Attack roll resolution
# ---------------------------------------------------------------------------

def resolve_attack_roll(
    event: "AttackRollEvent",
    rng: "SeededRNG",
    queue: "EventQueue",
    next_sequence: int,
) -> int:
    """Resolve one attack roll.  Returns the next available sequence number.

    Rolls 1d20 + actor's attack_bonus vs target's AC.
    On a hit (or crit) enqueues a DamageEvent.
    On a miss, logs and does nothing.

    Parameters
    ----------
    event:
        The AttackRollEvent being resolved.
    rng:
        The seeded RNG — all dice through here.
    queue:
        The event queue — used to push a DamageEvent on a hit.
    next_sequence:
        The next available sequence number within this turn.  Returned
        (possibly incremented) so the scheduler can track the counter.
    """
    actor = event.actor
    target = event.target
    tick = event.tick
    round_, turn_idx, _ = tick

    # Roll d20
    d20 = rng.roll_one(20)
    is_crit = (d20 == 20)
    is_auto_miss = (d20 == 1)

    # Effective attack bonus (modifiers folded in)
    atk_bonus = actor.stat(event.weapon_stat, tick=tick)
    total_roll = d20 + atk_bonus

    # Effective AC of target
    target_ac = target.stat("ac", tick=tick) if target is not None else 10

    log.info(
        "%s attacks %s: d20=%d + bonus=%d = %d vs AC %d  [%s]",
        actor.name,
        target.name if target else "??",
        d20,
        atk_bonus,
        total_roll,
        target_ac,
        "CRIT" if is_crit else ("AUTO-MISS" if is_auto_miss else ("HIT" if total_roll >= target_ac else "MISS")),
    )

    hit = (not is_auto_miss) and (is_crit or total_roll >= target_ac)

    if hit and target is not None:
        # Pull damage dice from actor stats
        damage_dice: tuple[int, int] = actor.stat("damage_dice", tick=tick)  # type: ignore[assignment]
        damage_bonus = int(actor.stat("damage_bonus", tick=tick))

        damage_event = DamageEvent(
            tick=make_tick(round_, turn_idx, next_sequence),
            actor=actor,
            target=target,
            is_crit=is_crit,
            damage_dice=damage_dice,
            damage_bonus=damage_bonus,
            cost=event.cost,
        )
        queue.push(damage_event)
        next_sequence += 1

    return next_sequence


# ---------------------------------------------------------------------------
# Damage resolution
# ---------------------------------------------------------------------------

def resolve_damage(
    event: "DamageEvent",
    rng: "SeededRNG",
    queue: "EventQueue",
    next_sequence: int,
) -> tuple[int, int]:
    """Resolve damage for a confirmed hit.  Returns (total_damage, next_sequence).

    Follows the phase order from CLAUDE.md §8:
      1. Determine dice pool — crits double die count
      2. Roll pool
      3. Per-die mods — not implemented yet (milestone placeholder)
      4. Sum
      5. Flat bonus

    Parameters
    ----------
    event:
        The DamageEvent being resolved.
    rng, queue, next_sequence:
        Standard handler args.

    Returns
    -------
    (total_damage, next_sequence)
        total_damage: the final damage number dealt.
        next_sequence: unchanged for now (damage spawns no follow-on events
        at this milestone stage).
    """
    actor = event.actor
    target = event.target
    n_dice, sides = event.damage_dice

    # Phase 1: determine dice pool (crits double die count)
    pool_size = n_dice * 2 if event.is_crit else n_dice

    # Phase 2: roll the pool
    rolls = rng.roll(pool_size, sides)

    # Phase 3: per-die mods — placeholder, nothing wired yet
    # (reroll-once, replace-with-floor, etc. will hook in here)

    # Phase 4: sum
    subtotal = sum(rolls)

    # Phase 5: flat bonus
    total = subtotal + event.damage_bonus

    log.info(
        "%s deals %d damage to %s  [%dd%d%s rolls=%s bonus=%d%s]",
        actor.name,
        total,
        target.name if target else "??",
        pool_size,
        sides,
        " (CRIT)" if event.is_crit else "",
        rolls,
        event.damage_bonus,
        f" subtotal={subtotal}" if event.damage_bonus else "",
    )

    if target is not None:
        target.take_damage(total)

    return total, next_sequence
