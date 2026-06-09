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
from typing import Callable, TYPE_CHECKING

from .events import AttackRollEvent, DamageEvent, make_tick

if TYPE_CHECKING:
    from .entity import Entity
    from .events import Event, EventQueue, Tick
    from .rng import SeededRNG

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# d20 roll with advantage / disadvantage
# ---------------------------------------------------------------------------

def roll_d20(rng: "SeededRNG", advantage: bool, disadvantage: bool) -> int:
    """Roll a d20, honoring advantage/disadvantage with RAW cancellation.

    Per the 2024 rules: if ANY source of advantage and ANY source of
    disadvantage both apply, they cancel and the roll is straight — regardless
    of how many sources are on each side.  So callers pass two booleans
    ("is there any advantage?" / "is there any disadvantage?"), not counts.
    """
    if advantage and not disadvantage:
        return max(rng.roll(2, 20))
    if disadvantage and not advantage:
        return min(rng.roll(2, 20))
    return rng.roll_one(20)


# ---------------------------------------------------------------------------
# Mastery on-hit application
# ---------------------------------------------------------------------------

def apply_masteries_on_hit(
    event: "AttackRollEvent",
    actor: "Entity",
    target: "Entity",
) -> None:
    """Apply each mastery property's on-hit effect.

    Called only on a confirmed hit.  Each mastery sets a tick-expiring status:

      sap → target has disadvantage on its next attack roll, until the START
            of the attacker's next turn → expiry (round+1, attacker_turn_index).

      vex → attacker has advantage on its next attack roll against THIS target,
            until the END of the attacker's next turn → modeled as expiry
            (round+2, attacker_turn_index).  (Consumed earlier on first use.)

    Both statuses are also consumed by the holder's next attack roll in
    resolve_attack_roll; the expiry tick is the backstop if no such roll occurs.
    """
    round_, turn_idx, _ = event.tick
    for mastery in event.masteries:
        if mastery == "sap":
            target.statuses.apply("sapped", True, expiry=(round_ + 1, turn_idx))
            log.debug("%s SAPs %s (expiry r%d t%d)", actor.name, target.name, round_ + 1, turn_idx)
        elif mastery == "vex":
            actor.statuses.apply("vex_advantage", target.id, expiry=(round_ + 2, turn_idx))
            log.debug("%s gains VEX advantage vs %s", actor.name, target.name)
        # Other masteries (topple, slow, push, nick, cleave, graze) deferred.


# ---------------------------------------------------------------------------
# Attack roll resolution
# ---------------------------------------------------------------------------

def resolve_attack_roll(
    event: "AttackRollEvent",
    rng: "SeededRNG",
    queue: "EventQueue",
    next_sequence: int,
    decider: "Callable[[int], int] | None" = None,
    hit_decider: "Callable[[bool], list[tuple[int, int]]] | None" = None,
) -> int:
    """Resolve one attack roll.  Returns the next available sequence number.

    Rolls 1d20 + actor's attack_bonus vs target's AC.
    On a hit (or crit) enqueues a DamageEvent.
    On a miss, optionally consults `decider` (a post-roll decision point — e.g.
    Guided Strike) which may add to the roll and turn the miss into a hit.

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
    decider:
        Optional callable `(missed_by) -> bonus`.  Called only on a non-auto
        miss; returns a positive bonus if the policy chose to spend a resource
        (the scheduler-side closure already validated/consumed it), else 0.
        A bonus that lifts the total to >= AC converts the miss to a (non-crit)
        hit.  None = no post-roll decision available.
    hit_decider:
        Optional callable `(is_crit) -> list[(n, sides)]`.  Called on a hit
        (including a Guided-Strike-rescued hit), BEFORE the DamageEvent is built;
        returns extra damage dice to fold into this hit (the scheduler-side
        closure already validated/consumed the resource + action economy).  The
        returned dice double on a crit like any others.  None = no on-hit
        decision available.
    """
    actor = event.actor
    target = event.target
    tick = event.tick
    round_, turn_idx, _ = tick

    # --- Determine advantage / disadvantage from statuses ---
    # These are "next attack roll" effects: consumed by making this roll,
    # whether or not they end up cancelling each other.
    advantage = False
    disadvantage = False

    # Vex: attacker has advantage on its next attack vs the specific vexed target.
    if target is not None and actor.statuses.get("vex_advantage") == target.id:
        advantage = True
        actor.statuses.consume("vex_advantage")

    # Sap: attacker has disadvantage on its next attack roll.
    if actor.statuses.has("sapped"):
        disadvantage = True
        actor.statuses.consume("sapped")

    # Roll d20 (with adv/disadv cancellation handled in the helper)
    d20 = roll_d20(rng, advantage, disadvantage)
    is_crit = (d20 == 20)
    is_auto_miss = (d20 == 1)

    # Effective attack bonus (modifiers folded in)
    atk_bonus = actor.stat(event.weapon_stat, tick=tick)
    total_roll = d20 + atk_bonus

    # Effective AC of target
    target_ac = target.stat("ac", tick=tick) if target is not None else 10

    adv_tag = " ADV" if (advantage and not disadvantage) else (" DIS" if (disadvantage and not advantage) else "")
    log.info(
        "%s attacks %s: d20=%d%s + bonus=%d = %d vs AC %d  [%s]",
        actor.name,
        target.name if target else "??",
        d20,
        adv_tag,
        atk_bonus,
        total_roll,
        target_ac,
        "CRIT" if is_crit else ("AUTO-MISS" if is_auto_miss else ("HIT" if total_roll >= target_ac else "MISS")),
    )

    hit = (not is_auto_miss) and (is_crit or total_roll >= target_ac)

    # Post-roll decision point (Guided Strike): on a genuine miss, let the
    # policy add to the roll.  A nat-1 auto-miss can't be rescued.
    if (not hit) and (not is_auto_miss) and decider is not None:
        missed_by = int(target_ac) - int(total_roll)
        bonus = decider(missed_by)
        if bonus > 0 and (total_roll + bonus) >= target_ac:
            total_roll += bonus
            hit = True  # rescued hit — NOT a crit (the d20 was not a 20)
            log.info(
                "  post-roll boost +%d -> %d vs AC %d  [RESCUED HIT]",
                bonus, total_roll, target_ac,
            )

    # Apply mastery on-hit effects (sap/vex set tick-expiring statuses).
    if hit and target is not None:
        apply_masteries_on_hit(event, actor, target)

    if hit and target is not None:
        # Pull damage dice from actor stats
        damage_dice: tuple[int, int] = actor.stat("damage_dice", tick=tick)  # type: ignore[assignment]
        damage_bonus = int(actor.stat("damage_bonus", tick=tick))

        # On-hit decision point (Wrathful/Divine Smite): the policy may add dice
        # to this hit, spending a resource + the bonus action (handled in the
        # scheduler-side closure).  These dice double on a crit like any others.
        extra_dice = list(event.extra_damage_dice)
        if hit_decider is not None:
            extra_dice.extend(hit_decider(is_crit))

        damage_event = DamageEvent(
            tick=make_tick(round_, turn_idx, next_sequence),
            actor=actor,
            target=target,
            is_crit=is_crit,
            damage_dice=damage_dice,
            damage_bonus=damage_bonus,
            extra_damage_dice=extra_dice,
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

    # Phase 1: determine dice pool (crits double die count) — for the weapon
    # dice AND every extra-damage source (True Strike rider, Wrathful Smite).
    pool_size = n_dice * 2 if event.is_crit else n_dice

    # Phase 2: roll the pool (weapon dice first, then each extra source)
    rolls = rng.roll(pool_size, sides)
    extra_rolls: list[int] = []
    for n_extra, extra_sides in event.extra_damage_dice:
        count = n_extra * 2 if event.is_crit else n_extra
        extra_rolls.extend(rng.roll(count, extra_sides))

    # Phase 3: per-die mods — placeholder, nothing wired yet
    # (reroll-once, replace-with-floor, etc. will hook in here)

    # Phase 4: sum (weapon dice + extra dice)
    subtotal = sum(rolls) + sum(extra_rolls)

    # Phase 5: flat bonus
    total = subtotal + event.damage_bonus

    log.info(
        "%s deals %d damage to %s  [%dd%d%s rolls=%s%s bonus=%d%s]",
        actor.name,
        total,
        target.name if target else "??",
        pool_size,
        sides,
        " (CRIT)" if event.is_crit else "",
        rolls,
        f" extra={extra_rolls}" if extra_rolls else "",
        event.damage_bonus,
        f" subtotal={subtotal}" if event.damage_bonus else "",
    )

    if target is not None:
        target.take_damage(total)

    return total, next_sequence
