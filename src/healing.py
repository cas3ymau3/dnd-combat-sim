"""
healing.py — the healing substrate (design/healing.md §9).

Three things live here:

  1. :class:`HealSpec` — the payload a ``Choice`` carries to produce healing, and
     :func:`resolve_healing`, the verb that applies it.  The §11.1 corpus survey
     collapsed eleven corpus shapes onto ONE verb: Second Wind, Healing Word, Cure
     Wounds, Lay on Hands, Mass Cure Wounds and Divine Spark all "restore
     ``Nd(S) + flat + ability modifier`` to a target" and differ only in cost,
     target count and action economy — every one of which ``Choice`` already
     carries.  Aura of Vitality is the recurring-zone substrate (#7b); Arcane
     Vigor sources its dice from a resource pool that exists; and the healing
     AMPLIFIERS (Chalice, Warrior of the Gods, Empowered Healing, Periapt of Wound
     Closure) are the modifier stack with a phase tag.

  2. :class:`HitDiceSpec` and the two Hit Dice rules (§7 a/b2), which are
     DELIBERATELY DIFFERENT because they measure different things — see
     :func:`spend_hit_dice_at_short_rest` and :func:`spend_summon_hit_dice`.

  3. The ROLLED-vs-MEAN-FIELD line, which is the one rule that keeps the §12
     parity proof alive:

       **Healing resolved INSIDE combat rolls its dice.  Healing applied OUTSIDE
       combat is MEAN-FIELD and draws nothing.**

     Between-combat healing is a day-clock quantity, and rolling it would pull
     from the shared RNG stream at a point every existing build passes through —
     shifting every subsequent die and breaking the bit-identical parity proof
     against ``validation.run_level``, the project's only end-to-end regression
     signal.  Mean-field draws nothing, preserves the proof, and matches the
     model's stated low-variance convention.  It also costs little: §11.1 found
     the corpus does the bulk of its healing out of combat by preference, so this
     is where the quantity is largest and its VARIANCE matters least.  A build
     that starts casting a heal in COMBAT does shift the stream, and that is a
     real modelling change rather than drift (healing.md §10.6).

Who writes the ledger: RESOLUTION, never policy (CLAUDE.md #7).  ``resolve_healing``
records into the §13 ``CombatTelemetry.healing`` channel; the policy only ever asks
for a heal.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:                                    # pragma: no cover
    from .entity import Entity
    from .rng import SeededRNG
    from .telemetry import CombatTelemetry

log = logging.getLogger(__name__)

#: The stat healing AMPLIFIERS modify (§11.1 shape 9).  A flat value folds in at
#: phase H6; a ``dice`` modifier on the same stat rolls there too (Chalice's
#: +1d8+WIS, Warrior of the Gods' +1d12).  Named as a stat so the existing
#: ModifierStack carries it with no new machinery.
HEALING_BONUS_STAT = "healing_bonus"

#: The modifier phase tag for that stat, mirroring the damage phase tags.
HEALING_PHASE = "healing"


# ---------------------------------------------------------------------------
# The heal EFFECT
# ---------------------------------------------------------------------------

@dataclass
class HealSpec:
    """One healing effect — the ``Choice.heal`` payload and the argument to
    :func:`resolve_healing`.

    Fields
    ------
    dice:
        ``(n, sides)`` rolled into the heal, or None for a flat-only heal
        (Lay on Hands draws flat points from a pool; Healing Light rolls).
    flat:
        Flat hit points added after the pool (phase H5).
    ability_stat:
        Name of a stat on the CASTER added at phase H5 — the spellcasting
        modifier in "2d8 + your spellcasting ability modifier".  None for the
        effects that add no modifier (Second Wind adds a class level, which the
        build passes as ``flat``).
    targets:
        Who is healed.  Empty means the actor heals ITSELF (Second Wind, Arcane
        Vigor).  A list covers the multi-target shapes (Prayer of Healing's five
        creatures, Mass Healing Word) without overloading ``Choice.target``; each
        target is resolved and ledgered SEPARATELY, so a multi-target heal
        produces one ``(source, target)`` cell per creature rather than one
        pooled number.
    """

    dice: tuple[int, int] | None = None
    flat: int = 0
    ability_stat: str | None = None
    targets: list["Entity"] = field(default_factory=list)


def resolve_healing(
    actor: "Entity",
    spec: "HealSpec",
    rng: "SeededRNG | None" = None,
    *,
    targets: "list[Entity] | None" = None,
    tick: tuple | None = None,
    mean_field: bool = False,
    telemetry: "CombatTelemetry | None" = None,
    context: str = "combat",
) -> dict[int, float]:
    """Apply one healing effect and return ``{target_id: hit points APPLIED}``.

    Phase order — the healing counterpart of CLAUDE.md §8, declared here so it has
    a stated place rather than an implied one:

      H1. determine the dice pool — **no crit doubling**; heals never crit, which
          is the one phase where healing and damage genuinely differ;
      H2. roll the pool (or take its mean when ``mean_field``);
      H3. per-die mods — the slot for Periapt of Wound Closure's "double the HP
          you regain from a Hit Die" and its kin;
      H4. sum;
      H5. flat bonuses — the effect's own flat plus the caster's ability modifier;
      H6. amplifier riders — the caster's ``healing_bonus`` modifiers at the
          ``healing`` phase (Chalice, Warrior of the Gods, Empowered Healing);
      H7. apply to each target, capped by ITS 0-HP category (healing.md §4);
      H8. ledger the amount ACTUALLY APPLIED, source-attributed.

    Position RELATIVE TO DAMAGE: a heal is its own event at its own sequence
    number in the ``(round, turn_index, sequence)`` tick, so it never interleaves
    with a damage resolution — it lands strictly before or after by sequence,
    exactly where the policy ordered it.  Nothing in damage resolution reads
    ``hp``, so the two are independent within a tick.

    H7/H8 record the APPLIED figure, not the rolled one.  A heal on a vanished
    summon applies nothing and is ledgered as nothing; a capped summon absorbs
    only its deficit.  That is what keeps "healing provided by the summon"
    honest rather than a gross number that overstates what happened.
    """
    who = targets if targets is not None else (spec.targets or [actor])

    # H1/H2 — the pool.  mean_field takes the die's expectation instead of rolling,
    # so out-of-combat healing draws NOTHING from the shared stream (see module
    # docstring: this is what keeps the §12 parity proof alive).
    if spec.dice is None:
        rolls: list[float] = []
    else:
        n, sides = spec.dice
        if n < 1:
            rolls = []
        elif mean_field:
            rolls = [(sides + 1) / 2.0] * n
        else:
            if rng is None:
                raise ValueError("resolve_healing needs an rng unless mean_field=True")
            rolls = list(rng.roll(n, sides))

    # H3 — per-die mods.  No consumer yet; the phase exists so Periapt of Wound
    # Closure lands as a per-die transform rather than as a special case bolted
    # onto the sum (the same discipline damage phase 3 keeps).

    # H4/H5 — sum, then flat bonuses.
    amount = float(sum(rolls)) + spec.flat
    if spec.ability_stat:
        amount += float(actor.stat(spec.ability_stat, tick))

    # H6 — amplifier riders off the caster's modifier stack.
    amount = float(actor.stat(HEALING_BONUS_STAT, tick, phase=HEALING_PHASE)) + amount
    if not mean_field and rng is not None:
        amount += actor.modifiers.roll_dice(HEALING_BONUS_STAT, rng, tick)

    if amount <= 0:
        return {}

    # H7/H8 — apply per target (each capped by its own category) and ledger the
    # APPLIED amount.  Enemies are never healed (healing.md §5); the policy layer
    # is what declines to target them, and nothing here silently filters, so a
    # build that tried would show up in the ledger rather than vanish.
    applied: dict[int, float] = {}
    for target in who:
        got = target.heal(amount)
        if got <= 0:
            continue
        applied[target.id] = applied.get(target.id, 0.0) + got
        if telemetry is not None:
            telemetry.record_healing(actor.id, target.id, got, context)
    return applied


# ---------------------------------------------------------------------------
# Hit Dice — TWO rules, deliberately (§7 a / b2)
# ---------------------------------------------------------------------------

@dataclass
class HitDiceSpec:
    """An entity's Hit Dice SHAPE.  The COUNT is not stored here — it lives in
    ``entity.resources["hit_dice"]``, the single source of truth, which already
    restores on a long rest (verified 2024 rule: a Long Rest returns ALL spent
    Hit Point Dice) and which the Starfire Scion already spends from.

    Fields
    ------
    dice:
        ``[(count, sides), ...]`` describing the pool's composition — a multiclass
        character has a mixed pool (War Angel at L16 is 9d10 + 7d8).  Dice are
        spent LARGEST FIRST, which is what a player healing up does.
    con_mod:
        Added to each die spent.  Floored at 0 per die (a Hit Die can never
        reduce your hit points), which matters for the CON-dumped builds: the War
        Angel has CON 8.
    rule:
        ``"character"`` or ``"summon"`` — which of the two rules below applies.
        The rules differ because they MEASURE different things (§7): a character's
        is POTENTIAL healing (nothing reads its ``hp``, so every die counts and
        spend-all is the right model), a summon's is ACTUAL healing (its HP gates
        death and turn access, so it spends only what it needs).  Two rules, not
        drift.
    available_for_healing:
        Optional ``(entity) -> int`` asking the BUILD how many of the remaining
        dice may be spent on healing.  Contested Hit Dice are a build-policy
        question ("policies are code"): the Starfire Scion spends ALL of its dice
        on Fueled Spellfire, and answers 0 here — without which an automatic
        spend-all at the short rest would silently drain the pool its damage
        depends on and move its DPR.  None = every remaining die is available.
    """

    dice: list[tuple[int, int]]
    con_mod: int = 0
    rule: str = "character"
    available_for_healing: "Callable[[Entity], int] | None" = None

    @property
    def total(self) -> int:
        return sum(n for n, _sides in self.dice)

    def die_sizes(self) -> list[int]:
        """The pool's individual die sizes, LARGEST FIRST — the spend order."""
        sizes: list[int] = []
        for n, sides in self.dice:
            sizes.extend([sides] * n)
        return sorted(sizes, reverse=True)

    def mean_field_value(self, n_dice: int, spent_already: int = 0) -> float:
        """Mean-field hit points from spending *n_dice*, skipping the first
        *spent_already* of the largest-first order.

        Mean-field, never rolled (§7a): rolling would draw from the shared RNG
        stream at the short rest, shifting every subsequent die for EVERY build
        and breaking the §12 parity proof.  Per die: ``max(0, avg + con_mod)``.
        """
        sizes = self.die_sizes()[spent_already:spent_already + max(0, n_dice)]
        return sum(max(0.0, (s + 1) / 2.0 + self.con_mod) for s in sizes)


def attach_hit_dice(entity: "Entity", spec: "HitDiceSpec") -> "Entity":
    """Give *entity* a Hit Dice pool: store the SHAPE on the entity and create the
    ``hit_dice`` COUNT in its resource pool (long-rest restore only, which is the
    verified 2024 rule — a Long Rest returns ALL spent Hit Point Dice).

    Idempotent-safe for a build that already declares its own ``hit_dice`` resource:
    the Starfire Scion's pool is created from its level table for Fueled Spellfire,
    and this leaves that entry alone rather than resetting a contested resource.
    """
    entity.hit_dice = spec
    if entity.resources.maximum("hit_dice") == 0:
        from .resources import ResourceEntry
        entity.resources.add("hit_dice", ResourceEntry(
            current=spec.total, maximum=spec.total, sr_restore=0))
    return entity


def _pool(entity: "Entity") -> tuple[int, int]:
    """(remaining, maximum) Hit Dice for *entity*, from its resource pool — the
    single source of truth for the COUNT (see :class:`HitDiceSpec`)."""
    return (entity.resources.available("hit_dice"),
            entity.resources.maximum("hit_dice"))


def spend_hit_dice_at_short_rest(
    entities: "list[Entity]",
    telemetry: "CombatTelemetry | None" = None,
    context: str = "between",
) -> dict[int, float]:
    """RULE (a) — CHARACTERS AND PARTY SPEND **ALL** THEIR HIT DICE, at every real
    short rest, unconditionally and UNCAPPED.  Returns ``{entity_id: hp healed}``.

    Elegant because it needs no policy — no conditions about when a character
    heals — and it lands at a well-defined moment.  Under §2's no-cap framing it is
    also the RIGHT model rather than merely convenient: spend-all is what produces
    the standardized POTENTIAL figure, independent of how much damage happened to
    land.  Every die counts, because nothing in the engine reads a character's
    ``hp``.

    Idempotent after the first call in a day, which is why it can be invoked from
    BOTH windows a build may have.  One short rest is the ENGINE baseline
    (design.md:96), but 2024 Prayer of Healing grants "the benefits of a Short
    Rest", and spending Hit Dice is one of those benefits — so War Angel's PoH
    window is a genuine second Hit Dice window (healing.md §11.2).  Hit Dice
    restore only on a LONG rest, so whichever window comes first drains the pool
    and the second heals nothing: two windows and one window give the same day
    total.  Calling this from both is therefore correct AND costless.

    Deliberately NOT recorded on the §13 economy channel.  ``resources_spent``
    measures what a POLICY chose to spend; these dice are spent automatically by
    the engine.  Pooling them under the same key would silently inflate
    ``resources_spent_per_day`` and, for the Starfire Scion, mix its Fueled
    Spellfire choices with an engine default.  Hit Dice healing is reported
    through the healing channel only.
    """
    healed: dict[int, float] = {}
    for entity in entities:
        spec = getattr(entity, "hit_dice", None)
        if spec is None or spec.rule != "character":
            continue
        remaining, maximum = _pool(entity)
        if remaining <= 0:
            continue
        n = remaining
        if spec.available_for_healing is not None:
            n = max(0, min(remaining, int(spec.available_for_healing(entity))))
        if n <= 0:
            continue
        spent_already = maximum - remaining
        amount = spec.mean_field_value(n, spent_already)
        entity.resources.consume("hit_dice", n)
        got = entity.heal(amount)
        if got <= 0:
            continue
        healed[entity.id] = healed.get(entity.id, 0.0) + got
        if telemetry is not None:
            # Self-healing: the entity is both source and target, which is what
            # makes "how much of this build's healing was its own" answerable.
            telemetry.record_healing(entity.id, entity.id, got, context)
        log.info("%s spends %d Hit Dice at the short rest → +%.1f hp", entity.name, n, got)
    return healed


def spend_summon_hit_dice(
    entities: "list[Entity]",
    telemetry: "CombatTelemetry | None" = None,
    context: str = "between",
) -> dict[int, float]:
    """RULE (b2) — SUMMONS SPEND HIT DICE **TO THE DEFICIT**, after EACH combat,
    bounded by the remaining pool.  Returns ``{entity_id: hp healed}``.

    Not "top up to full": the pool is the binding constraint, and once it is empty
    the summon gets nothing after later combats.  Stated as a deficit the rule
    never overheals, so §4's cap question does not arise for Hit Dice at all.

    It deliberately BREAKS RAW — Hit Dice are spent on short rests, and this
    spends them after every combat.  Accepted (user): the alternative is modelling
    summon damage/healing TIMING, and that complexity buys too little.

    Why this differs from the character rule, and why that is not an
    inconsistency: the character spends all dice unconditionally and uncapped —
    POTENTIAL healing, where every die counts because nothing reads its ``hp``.  A
    summon spends only what it needs — ACTUAL healing, mechanically real because
    its HP gates death and turn access.  Two rules because they measure two
    different things.

    What it buys that a never-spend rule would not: a DEPLETION CURVE bounded by
    the pool (the shape the four-combat day exists to show); DAMAGE-RESPONSIVE
    spending, which makes the pool a real resource rather than a fixed bonus; and
    an INTERACTION WITH EXTERNAL HEALING — if the character heals the beast, the
    beast spends fewer of its OWN dice, so character healing has knock-on value in
    preserving companion resources.

    Ordering against ``recast``: this must run AFTER the build's between-combats
    hook, because ``recast`` revives the beast at FULL HP, after which the deficit
    is zero and this is a no-op.  A ``vanishes`` summon that is destroyed and NOT
    revived cannot be helped by Hit Dice at all; a ``downed`` one can, and healing
    it above 0 is what returns it to acting (§6).
    """
    healed: dict[int, float] = {}
    for entity in entities:
        spec = getattr(entity, "hit_dice", None)
        if spec is None or spec.rule != "summon":
            continue
        if entity.destroyed:
            continue                      # gone; Hit Dice cannot reach it
        deficit = entity.max_hp - entity.hp
        if deficit <= 0:
            continue
        remaining, maximum = _pool(entity)
        if remaining <= 0:
            continue
        spent_already = maximum - remaining
        # Spend one die at a time until the deficit is covered or the pool empties.
        spent = 0
        amount = 0.0
        while spent < remaining and amount < deficit:
            amount += spec.mean_field_value(1, spent_already + spent)
            spent += 1
        if spent <= 0:
            continue
        entity.resources.consume("hit_dice", spent)
        got = entity.heal(amount)          # capped at max_hp by category (§4)
        if got <= 0:
            continue
        healed[entity.id] = healed.get(entity.id, 0.0) + got
        if telemetry is not None:
            telemetry.record_healing(entity.id, entity.id, got, context)
        log.info("%s (summon) spends %d Hit Dice after combat → +%.1f hp (deficit %.1f)",
                 entity.name, spent, got, deficit)
    return healed
