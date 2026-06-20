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

from .events import AttackRollEvent, DamageEvent, SaveDamageEvent, make_tick

if TYPE_CHECKING:
    from .entity import Entity
    from .events import Event, EventQueue, Tick
    from .rng import SeededRNG

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# d20 roll with advantage / disadvantage
# ---------------------------------------------------------------------------

def resolve_saving_throw(
    entity: "Entity",
    save_stat: str,
    dc: int,
    rng: "SeededRNG",
    advantage: bool = False,
    disadvantage: bool = False,
    reroll_decider: "Callable[[int, int], int | None] | None" = None,
    d20_floor: int | None = None,
) -> bool:
    """Resolve one saving throw: d20 + save bonus vs DC → True on success.

    The save bonus is the flat folded stat PLUS any rolled-dice modifiers on it
    (Bless's +1d4 to saves), rolled here on the resolution path.  Advantage /
    disadvantage cancel per RAW (handled in roll_d20).  This is the save verb
    (design §4 #3); concentration checks call it inline, and a SavingThrowEvent
    can wrap it later for scheduled saves (frightened, enemy save-spells).

    `reroll_decider` is the failed-save rescue hook (Indomitable / Luck): a
    `(dc, failed_total) -> bonus | None` callable.  On a FAILURE it is offered
    the result; if it returns a flat bonus, the save is rerolled (fresh d20 +
    the entity's save bonus + that bonus) and the new result stands, per RAW.
    The scheduler builds it from the entity's Policy.on_failed_save and has
    already validated/consumed the resource by the time the bonus comes back.

    `d20_floor` is a per-die FLOOR on the d20 (the substrate-#3 save-floor grant):
    a rolled value below it is treated as the floor — Starry-Form Dragon's "treat
    a 9 or lower as 10 when making a CON save to maintain concentration"
    (guide 41:308).  Applied after advantage/disadvantage to whichever d20 stands,
    on both the initial roll and any reroll.
    """
    d20 = roll_d20(rng, advantage, disadvantage)
    if d20_floor is not None:
        d20 = max(d20, d20_floor)
    bonus = int(entity.stat(save_stat)) + entity.roll_bonus(save_stat, rng)
    total = d20 + bonus
    success = total >= dc
    log.info(
        "%s %s save: d20=%d + %d = %d vs DC %d → %s",
        entity.name, save_stat, d20, bonus, total, dc,
        "PASS" if success else "FAIL",
    )
    if not success and reroll_decider is not None:
        extra = reroll_decider(dc, total)
        if extra is not None:
            d20b = roll_d20(rng, advantage, disadvantage)
            if d20_floor is not None:
                d20b = max(d20b, d20_floor)
            bonusb = int(entity.stat(save_stat)) + entity.roll_bonus(save_stat, rng) + extra
            totalb = d20b + bonusb
            success = totalb >= dc
            log.info(
                "%s REROLLS %s save (+%d): d20=%d + %d = %d vs DC %d → %s",
                entity.name, save_stat, extra, d20b, bonusb, totalb, dc,
                "PASS" if success else "FAIL",
            )
    return success


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
    hit_decider: "Callable[[bool], tuple[list[tuple[int, int]], list[str], list[object]]] | None" = None,
    intercept_decider: "Callable[[int], object | None] | None" = None,
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
        Optional callable `(is_crit) -> (extra_dice, extra_masteries,
        rider_damage)`.  Called on a hit (including a Guided-Strike-rescued hit),
        BEFORE the DamageEvent is built; the scheduler-side closure already
        validated/consumed any resource + action economy.  `extra_dice` and
        `extra_masteries` fold into THIS hit's own DamageEvent (smite, bluff).
        `rider_damage` is a list of substrate-#6 outgoing-rider specs (Fount of
        Moonlight, Primal Strike) — each is spawned as its OWN separately-typed
        DamageEvent from this hit, so its damage type / spell-source stay distinct
        (routes through the target's per-type response, reaches the caster's
        on_deal_damage rider on its own terms).  All these dice double on a crit.
        None = no on-hit decision available.
    intercept_decider:
        Optional callable `(hit_margin) -> InterceptResponse | None` for the
        DEFENDER's in-flight reaction (intercept_event — Flourish Parry / Shield /
        Fire Shield thorns, plus the 7c ally-effects riders).  Called on a confirmed
        hit, AFTER any Guided-Strike rescue and BEFORE the attacker's on-hit rider.
        `hit_margin = total_roll - AC` (>= 0).  The response object's riders are
        applied in order, each able to flip the hit to a miss (later riders skip
        once flipped): `ac_bonus` (flip + optional `counter`), `impose_disadvantage`
        (Protection — re-roll with disadvantage), `negate_save` (Sanctuary —
        attacker save-or-negate), `reactive_damage` (Fire Shield thorns if the hit
        still lands), and `redirect` (Warding Bond — threaded onto the DamageEvent,
        resolved at damage time).  The scheduler-side closure already
        validated/consumed the defender's resources.  None = no interceptor.
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

    # --- Persistent advantage grants from cast_effect status payloads (#3) ---
    # Unlike vex/sap (one-shot, consumed on use), these are duration buffs read
    # on EVERY qualifying roll until the cast ends (swept at the combat boundary
    # or dropped on lost concentration) — so they are read, never consumed.
    #   Faerie Fire: attack rolls against an outlined TARGET have advantage (any
    #   attacker who can see it — no spell gate).
    if target is not None and target.statuses.has("attack_advantage_against"):
        advantage = True
    #   Innate Sorcery: the caster has advantage on its own SPELL attack rolls
    #   (gated on the attack being a spell — weapon swings are unaffected).
    if event.is_spell and actor.statuses.has("spell_attack_advantage"):
        advantage = True

    # Roll d20 (with adv/disadv cancellation handled in the helper)
    d20 = roll_d20(rng, advantage, disadvantage)
    is_crit = (d20 == 20)
    is_auto_miss = (d20 == 1)

    # Effective attack bonus (flat modifiers folded in) PLUS any rolled-dice
    # modifiers (Bless +1d4) on this stat — rolled fresh per attack here, on the
    # resolution path, never via the pure stat() the policy reads.
    atk_bonus = actor.stat(event.weapon_stat, tick=tick)
    atk_bonus += actor.roll_bonus(event.weapon_stat, rng, tick=tick)
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

    # In-flight interception (intercept_event): on a confirmed hit, let the
    # DEFENDER react.  The decider returns a single InterceptResponse object
    # (refactored from a positional 3-tuple at the warding-bond redirect — the
    # session-12 engine-seam note); its riders are applied in order, each able to
    # flip the hit to a miss (later riders skip once the hit is flipped).  Runs
    # AFTER any Guided-Strike rescue (a rescued hit is still parryable) and BEFORE
    # the attacker's on-hit rider / masteries / damage (a flipped hit deals
    # nothing, forces no concentration check).
    redirect_spec = None
    if hit and intercept_decider is not None:
        hit_margin = int(total_roll) - int(target_ac)
        response = intercept_decider(hit_margin)
    else:
        response = None
    if response is not None:
        # 1. AC bump (Flourish Parry / Shield) — flip if it clears the margin.
        if response.ac_bonus > 0 and total_roll < int(target_ac) + response.ac_bonus:
            hit = False
            log.info(
                "  defender +%d AC -> %d vs roll %d  [INTERCEPTED -> MISS]",
                response.ac_bonus, int(target_ac) + response.ac_bonus, total_roll,
            )
            if response.counter is not None and target is not None:
                counter_spec = response.counter
                counter_event = AttackRollEvent(
                    tick=make_tick(round_, turn_idx, next_sequence),
                    actor=target,                       # the defender counters
                    target=counter_spec.target,         # ...the attacker
                    weapon_stat=counter_spec.weapon_stat,
                    cost="reaction",
                    masteries=list(counter_spec.masteries),
                    extra_flat_damage=counter_spec.extra_flat_damage,
                    policy_riders=False,                # carries its own bleed
                )
                queue.push(counter_event)
                next_sequence += 1
        # 2. Protection fighting style (7c): a nearby protector interposes a shield
        # and imposes DISADVANTAGE on the attack.  Modeled by rolling a SECOND d20
        # and flipping the hit to a miss if it now misses — distributionally exact
        # (P(hit)^2 either way, since we condition on the first roll being a hit).
        # The surviving hit keeps its crit only if the second die is also a 20.
        if hit and response.impose_disadvantage:
            d20_2 = roll_d20(rng, False, False)
            if d20_2 == 1 or (d20_2 + atk_bonus) < int(target_ac):
                hit = False
                log.info(
                    "  protector imposes disadvantage: d20=%d -> %d vs AC %d  "
                    "[PROTECTED -> MISS]", d20_2, d20_2 + atk_bonus, int(target_ac),
                )
            else:
                is_crit = is_crit and (d20_2 == 20)
        # 3. Sanctuary (7c): the ATTACKER must make a save or lose the attack.  On
        # a FAILED save the hit is negated (flipped to a miss).
        if hit and response.negate_save is not None:
            ns = response.negate_save
            if not resolve_saving_throw(actor, ns.save_stat, ns.dc, rng):
                hit = False
                log.info(
                    "  sanctuary: %s failed %s vs DC %d  [SANCTUARY -> MISS]",
                    actor.name, ns.save_stat, ns.dc,
                )
        # 4. Redirect (Warding Bond, 7c): if the hit STILL lands, capture the
        # redirect for the DamageEvent (resolved at damage time — the amount isn't
        # known until the bearer's damage resolves).
        if hit and response.redirect is not None:
            redirect_spec = response.redirect
        # 5. Thorns (Fire Shield, substrate #5): when the melee hit LANDS (not
        # flipped to a miss above), the bearer deals automatic damage to the
        # attacker — no attack roll.  Enqueued as a DamageEvent FROM the bearer
        # (the defender = this event's target) TO the attacker (this event's
        # actor), so it routes through the attacker's own damage-type response
        # and counts as the bearer's outgoing damage.
        reactive_damage = response.reactive_damage
        if hit and reactive_damage is not None and target is not None:
            thorns_event = DamageEvent(
                tick=make_tick(round_, turn_idx, next_sequence),
                actor=target,                       # the bearer deals the thorns
                target=actor,                       # ...to the attacker
                is_crit=False,
                damage_dice=reactive_damage.damage_dice,
                damage_bonus=0,
                damage_type=reactive_damage.damage_type,
                is_spell=False,
                min_die=reactive_damage.min_die,
                ignore_resistance=reactive_damage.ignore_resistance,
                cost="none",
            )
            queue.push(thorns_event)
            next_sequence += 1
            log.info(
                "  %s thorns -> %s  [%dd%d %s]",
                target.name, actor.name,
                reactive_damage.damage_dice[0], reactive_damage.damage_dice[1],
                reactive_damage.damage_type,
            )

    # On-hit decision point: fires BEFORE apply_masteries_on_hit so any extra
    # masteries returned by the policy (e.g. Brutality::bluff adding vex) are
    # folded into event.masteries and applied on this same hit.
    extra_dice = list(event.extra_damage_dice)
    rider_specs: list = []
    if hit and hit_decider is not None:
        extra_dice_from_hit, extra_masteries_from_hit, rider_specs = hit_decider(is_crit)
        extra_dice.extend(extra_dice_from_hit)
        event.masteries.extend(extra_masteries_from_hit)

    # Apply mastery on-hit effects (sap/vex set tick-expiring statuses).
    if hit and target is not None:
        apply_masteries_on_hit(event, actor, target)

    if hit and target is not None:
        # Damage profile: a per-attack override (the multi-weapon gish primitive)
        # if the Choice supplied one, else the actor's single weapon stat.  The
        # override lets one entity swing several distinct profiles (quarterstaff /
        # unarmed / Archer spell attack / Guiding Bolt); None preserves the
        # single-weapon path every prior build relies on.
        if event.damage_dice_override is not None:
            damage_dice: tuple[int, int] = event.damage_dice_override
            damage_bonus = int(event.damage_bonus_override or 0)
        else:
            damage_dice = actor.stat("damage_dice", tick=tick)  # type: ignore[assignment]
            damage_bonus = int(actor.stat("damage_bonus", tick=tick))

        damage_event = DamageEvent(
            tick=make_tick(round_, turn_idx, next_sequence),
            actor=actor,
            target=target,
            is_crit=is_crit,
            damage_dice=damage_dice,
            damage_bonus=damage_bonus,
            extra_damage_dice=extra_dice,
            extra_flat_damage=event.extra_flat_damage,
            damage_type=event.damage_type,
            is_spell=event.is_spell,
            min_die=event.min_die,
            ignore_resistance=event.ignore_resistance,
            redirect=redirect_spec,            # Warding Bond (7c) — resolved at damage time
            cost=event.cost,
        )
        queue.push(damage_event)
        next_sequence += 1

        # Substrate #6 — outgoing predicate riders (Fount of Moonlight, Primal
        # Strike).  Each rider spec is spawned as its OWN DamageEvent from this
        # same hit (same actor → target, same is_crit so its dice double on a
        # crit), AFTER the weapon's DamageEvent.  Keeping each rider a separate
        # typed event — rather than folding its dice into the weapon hit above —
        # is what lets its damage type / is_spell stay distinct: it routes through
        # the target's per-type response (substrate #4), carries its own Elemental
        # Adept treatment, and reaches the caster's on_deal_damage rider on its
        # own terms (FoM's radiant is is_spell → Fueled Spellfire fuels it; Primal
        # Strike's elemental is a feature → not fuelable).
        for spec in rider_specs:
            rider_event = DamageEvent(
                tick=make_tick(round_, turn_idx, next_sequence),
                actor=actor,
                target=target,
                is_crit=is_crit,
                damage_dice=spec.damage_dice,
                damage_bonus=spec.damage_bonus,
                damage_type=spec.damage_type,
                is_spell=spec.is_spell,
                min_die=spec.min_die,
                ignore_resistance=spec.ignore_resistance,
                cost="none",
            )
            queue.push(rider_event)
            next_sequence += 1
            log.info(
                "  %s rider -> %s  [%dd%d %s]",
                actor.name, target.name,
                spec.damage_dice[0], spec.damage_dice[1], spec.damage_type,
            )

    return next_sequence


# ---------------------------------------------------------------------------
# Save-for-damage resolution (Sacred Flame, Burning Hands)
# ---------------------------------------------------------------------------

def resolve_save_damage(
    event: "SaveDamageEvent",
    rng: "SeededRNG",
    queue: "EventQueue",
    next_sequence: int,
    save_advantage: bool = False,
    negate_on_save: bool = False,
) -> int:
    """Resolve a save-FOR-damage spell.  Returns the next available sequence.

    The mirror of resolve_attack_roll: the TARGET rolls a saving throw vs the
    ACTOR's spell save DC, and the result determines damage.  On the
    damage-dealing branch this enqueues a normal DamageEvent — so the phase-
    ordered damage roll, concentration check, and save-reroll machinery in
    resolve_damage / the scheduler are reused untouched (this verb never rolls a
    damage die itself).

      - save FAILS                  → full DamageEvent (halved=False)
      - save SUCCEEDS, on_save=none  → no damage (the missed-attack analog)
      - save SUCCEEDS, on_save=half  → DamageEvent(halved=True)

    The save itself goes through resolve_saving_throw with no reroll_decider:
    enemy targets carry no failed-save rescue, and an attacker-imposed save is
    not the kind of save Indomitable/Luck protect (those rescue the SAVER's own
    concentration / effects, handled on the spawned DamageEvent if relevant).

    ``save_advantage`` / ``negate_on_save`` are the BUFF-AURA grants (substrate #7 /
    7b, Circle of Power): a friendly creature inside an ally-buff zone rolls this save
    at ADVANTAGE (``save_advantage``), and on a SUCCESS vs a save-for-half spell takes
    NO damage instead of half (``negate_on_save`` upgrades ``on_save="half"`` to
    ``"none"``).  Both gate on the event being a spell/magical effect — the scheduler
    (which owns the zone registry) computes them and passes them in.
    """
    actor = event.actor
    target = event.target
    if target is None:
        return next_sequence

    round_, turn_idx, _ = event.tick
    dc = int(actor.stat(event.dc_stat, tick=event.tick))

    saved = resolve_saving_throw(target, event.save_stat, dc, rng,
                                 advantage=save_advantage)

    # Telemetry (design §8: saves forced / failed by type) — tracked on the
    # entity that MADE the save, mirroring concentration_checks on the saver.
    target.saving_throws_made += 1
    if not saved:
        target.saving_throws_failed += 1

    # Buff aura: a successful save vs a save-for-half spell takes NO damage instead
    # of half (Circle of Power).  Only changes the SUCCESS branch — a fail still
    # takes full — so upgrading on_save "half" → "none" is exactly the clause.
    on_save = "none" if (negate_on_save and event.on_save == "half") else event.on_save

    deals_damage = (not saved) or (on_save == "half")
    if not deals_damage:
        log.info(
            "%s SAVES vs %s's %s (DC %d) — negated, no damage",
            target.name, actor.name, event.save_stat, dc,
        )
        return next_sequence

    damage_event = DamageEvent(
        tick=make_tick(round_, turn_idx, next_sequence),
        actor=actor,
        target=target,
        is_crit=False,                 # saving-throw spells never crit
        damage_dice=event.damage_dice,
        damage_bonus=event.damage_bonus,
        halved=(saved and on_save == "half"),
        damage_type=event.damage_type,
        is_spell=event.is_spell,
        min_die=event.min_die,
        ignore_resistance=event.ignore_resistance,
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
    save_reroll_decider: "Callable[[int, int], int | None] | None" = None,
    rider_decider: "Callable[[str | None, bool, bool], list[tuple[int, int]]] | None" = None,
) -> tuple[int, int]:
    """Resolve damage for a confirmed hit.  Returns (total_damage, next_sequence).

    Follows the phase order from CLAUDE.md §8:
      1. Determine dice pool — crits double die count
      2. Roll pool
      3. Per-die mods — not implemented yet (milestone placeholder)
      4. Sum
      5. Flat bonus
      6. Save-for-half halving

    Parameters
    ----------
    event:
        The DamageEvent being resolved.
    rng, queue, next_sequence:
        Standard handler args.
    rider_decider:
        Optional `(damage_type, is_spell, is_crit) -> list[(n, sides)]` callable
        for the CASTER's post-damage rider (Fueled Spellfire).  Called as this
        damage resolves — the on_hit analog on the *damage* side, reachable from
        BOTH the attack-roll and save-for-damage paths (this verb is the single
        chokepoint both funnel through).  The scheduler-side closure has already
        consulted the caster's policy and validated/consumed the resource; it
        returns the dice to fold in.  None = no rider available.

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

    # Phase 2: roll the pool (weapon dice first, then each extra source).
    # A source with zero dice (pool_size 0) is a flat-only hit (e.g. the enemy's
    # fixed 28 damage) — skip the roll rather than calling rng.roll(0, …).
    rolls = rng.roll(pool_size, sides) if pool_size >= 1 else []
    extra_rolls: list[int] = []
    for n_extra, extra_sides in event.extra_damage_dice:
        count = n_extra * 2 if event.is_crit else n_extra
        if count >= 1:
            extra_rolls.extend(rng.roll(count, extra_sides))

    # Phase 3: per-die mods.  Elemental Adept's "treat any 1 on a damage die as a
    # 2" is a per-die FLOOR: each of the SPELL's own dice (the main pool) is raised
    # to at least event.min_die.  Applied here, before the sum, so it composes with
    # crit-doubling (the doubled dice are floored too).  Only the main pool is
    # floored — for the current consumers (fire Searing Arc, fire thorns) that IS
    # the feat's "spell you cast that deals damage of that type"; extra/rider dice
    # are separate sources/types and would generalize this when one needs it.
    if event.min_die is not None:
        rolls = [max(r, event.min_die) for r in rolls]

    # Phase 4: sum (weapon dice + extra dice)
    subtotal = sum(rolls) + sum(extra_rolls)

    # Phase 5: flat bonuses (weapon damage_bonus + any extra flat damage, e.g.
    # Brutality::bleed's +CHA mod; neither scales on a crit).
    total = subtotal + event.damage_bonus + event.extra_flat_damage

    # Phase 5.5: caster post-damage rider (Fueled Spellfire) — a CASTER decision
    # point offered as this damage resolves, the on_hit analog on the *damage*
    # side.  The scheduler-side closure already consulted the caster's policy
    # (which gates on "spell radiant damage") and validated/consumed the resource;
    # it returns the dice to fold in.  Per the design decision these rider dice are
    # NOT crit-doubled (a fixed Hit-Dice expenditure, not the spell's own dice) and
    # are added BEFORE phase-6 halving so they share a save-for-half spell's fate.
    rider_total = 0
    if rider_decider is not None:
        for n_rider, sides_rider in rider_decider(
            event.damage_type, event.is_spell, event.is_crit
        ):
            if n_rider >= 1:
                rider_total += sum(rng.roll(n_rider, sides_rider))
    total += rider_total

    # Phase 6: save-for-half halving (2024 RAW — a successful save against a
    # half-on-save spell takes half the TOTAL damage, rounded down).  Set only
    # by resolve_save_damage on a saved half-on-save spell; full hits and failed
    # saves never set it, so this is inert on every existing damage path.
    if event.halved:
        total //= 2

    # Phase 7: defender damage-type RESPONSE (substrate #4 — resistance /
    # vulnerability / immunity by type).  Applied AFTER all other modifiers
    # (2024 RAW), so it stacks after phase-6 halving, and BEFORE take_damage so
    # the post-response amount is what drives any concentration save.  Resistance
    # halves (rounded down), vulnerability doubles, immunity zeroes.  An untyped
    # hit (damage_type None) or a target with no matching response is unchanged,
    # so this is inert on every existing damage path.
    damage_response = (
        target.damage_response_for(event.damage_type) if target is not None else None
    )
    # Elemental Adept: the caster's spell ignores RESISTANCE to its type (the 2024
    # feat bypasses resistance only — immunity and vulnerability still bind).  So a
    # fire-resistant enemy takes FULL Searing Arc; a fire-immune one still takes 0.
    if event.ignore_resistance and damage_response == "resistance":
        damage_response = None
    if damage_response == "resistance":
        total //= 2
    elif damage_response == "vulnerability":
        total *= 2
    elif damage_response == "immunity":
        total = 0

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
        event.damage_bonus + event.extra_flat_damage,
        f" subtotal={subtotal}" if (event.damage_bonus or event.extra_flat_damage) else "",
    )
    if rider_total:
        log.info("  + fueled rider %d (spell radiant damage)", rider_total)
    if damage_response is not None:
        log.info("  %s applied %s to %s damage", target.name, damage_response, event.damage_type)

    if target is not None:
        target.take_damage(total)
        _check_concentration(target, total, rng, save_reroll_decider)

    # Damage REDIRECT (substrate #7 / 7c, Warding Bond): the bearer is warded, so a
    # share of the amount IT JUST TOOK (post-resistance — phase 7 already halved it)
    # is also dealt to the warding caster.  Spawned as a flat DamageEvent attributed
    # to the ORIGINAL attacker (event.actor) so it lands in that attacker's outgoing
    # column, with redirect=None so it never recurses.  Faithful to "you take the
    # same amount of damage": no dice, no further response, just the flat amount.
    if event.redirect is not None and total > 0:
        rspec = event.redirect
        amount = int(total * rspec.fraction)
        if amount > 0 and rspec.target is not None:
            round_, turn_idx, _ = event.tick
            redirect_event = DamageEvent(
                tick=make_tick(round_, turn_idx, next_sequence),
                actor=actor,                    # attributed to the original attacker
                target=rspec.target,            # ...the warding caster takes the share
                is_crit=False,
                damage_dice=(0, 0),
                damage_bonus=amount,
                cost="none",
            )
            queue.push(redirect_event)
            next_sequence += 1
            log.info(
                "  warding bond: %s also takes %d (redirected from %s)",
                rspec.target.name, amount, target.name,
            )

    return total, next_sequence


def _check_concentration(
    entity: "Entity",
    damage: int,
    rng: "SeededRNG",
    save_reroll_decider: "Callable[[int, int], int | None] | None" = None,
) -> None:
    """Force a concentration save when a concentrating entity takes damage.

    DC = max(10, ⌊damage/2⌋).  The save is a CON save (con_save), boosted by
    Bless's +1d4 if active (folded via roll_bonus inside resolve_saving_throw),
    and made at advantage if Brutality::bluff set `advantage_next_save` this
    round (consumed here).  A `concentration_save_floor` status (Starry-Form
    Dragon) floors the d20.  A failed save may be rerolled via `save_reroll_
    decider` (Indomitable) before concentration drops.  On a (final) failure,
    the concentrated spell's WHOLE bundle is dropped (remove_effect: modifiers +
    damage response + statuses) and concentration clears.
    """
    if entity.concentration is None or damage <= 0:
        return
    dc = max(10, damage // 2)
    advantage = entity.statuses.has("advantage_next_save")
    if advantage:
        entity.statuses.consume("advantage_next_save")
    # Starry-Form Dragon (substrate #3 save-floor): treat a d20 of 9 or lower as
    # 10 on this concentration save (guide 41:308).  None when not in Dragon form.
    d20_floor = entity.statuses.get("concentration_save_floor")
    entity.concentration_checks += 1
    if not resolve_saving_throw(
        entity, "con_save", dc, rng, advantage=advantage,
        reroll_decider=save_reroll_decider,
        d20_floor=d20_floor,
    ):
        log.info("%s LOSES concentration on %s", entity.name, entity.concentration)
        entity.remove_effect(entity.concentration)
        entity.concentration_breaks += 1
