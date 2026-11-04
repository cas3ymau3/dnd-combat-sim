"""
baseline_character.py — ``BaselineCharacterPolicy``, the framework's declared SUBJECT
in motion (evaluation_framework.md §3.5.1).

``character_stats`` is the subject's STAT BLOCK; this is what it DOES.  The two are
separate for the same reason ``enemy_stats`` and ``BaselineEnemyPolicy`` are: a stat
block is data and a policy is code (CLAUDE.md #2), and the table is reusable by a
fixture that wants a complete character without wanting this behaviour.

WHY A SUBJECT AT ALL — the short version of §3.5
------------------------------------------------
The framework was validated against three builds written as scaffolding for engine
development, and their data is sparse exactly where the framework needs it complete.
**A framework defect and a content gap are indistinguishable when the only subjects are
partial builds**, and every session since s50 spent effort on content gaps while trying
to test framework behaviour.  §3.4 solved the same problem on the enemy side by
declaring the enemy; this declares the subject.

A CORE THAT IS ALWAYS ON, AND THE REST AS DECLARED AXES (user, s53)
-------------------------------------------------------------------
The same shape as ``enemy_options``, and for the same reason: every registry channel
gets a fixture that genuinely populates it, while the off-by-default axes keep the
baseline's own numbers stable.

================================  ==========================================
CORE (always on)                  the channel it exists to populate
================================  ==========================================
weapon attacks                    the §8.1 attacks channel (hit / crit / adv)
a concentration spell             concentration checks + breaks, and the only
                                  thing control pressure can take away
a save-forcing spell              the saves channel keyed by ability, from the
                                  CHARACTER's side (every other producer is
                                  the enemy)
healing, in combat and between    ``healing_by_source`` needs BOTH contexts
a spell-slot budget               the §13 resource ledger
an opportunity attack             the REACTION slot — a third of the action
                                  economy (CLAUDE.md #11)
================================  ==========================================

================================  ==========================================
AXIS (default off)                what it exercises
================================  ==========================================
``summon``                        the per-summon column + roster scoping
``ally_buff``                     the ``allies`` role as a buff TARGET rather
                                  than a damage sink
``reaction_mitigation``           the character side of §5's ``mult(t)`` and
                                  the defender-side ``on_incoming_hit`` seam
================================  ==========================================

THE OPPORTUNITY ATTACK IS CORE, AND THERE IS NO SPATIAL MODEL
-------------------------------------------------------------
So *"the enemy moves out of reach"* is a **FREQUENCY, not an event** — stated rather
than implied.  The established convention is War Angel's, which its own guide reached by
collapsing five AoO timing slots into one: one AoO per combat on a round **pre-rolled at
``on_combat_start``** through the seeded channel.  The baseline adopts it with the COUNT
as a declared parameter (``aoo_per_combat``, an adapter option), so §4 provenance records
the assumption instead of burying it.

A reaction-based *mitigation* is the declared axis on the other side of the economy.
Note the two are DOUBLE-BOOKED when both are on, exactly as War Angel's parry and AoO
are, and `reactions_per_round` is where that shows (§8.2a) — the baseline reproduces the
convention rather than quietly fixing it, because the alternative is a subject whose
reaction economy differs from the builds it is meant to make comparable.

NO NEW DICE OUTSIDE COMBAT
--------------------------
``decide`` is a pure read (CLAUDE.md #7) and ``between_combats`` heals MEAN-FIELD.  The
only draw here is ``on_combat_start``'s AoO round, which is inside a combat's own setup
and is where War Angel draws its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..healing import HealSpec, resolve_healing, spend_hit_dice_at_short_rest
from ..modifiers import Modifier
from ..policy import Choice, InterceptResponse
from ..summons import SummonSpec
from . import character_stats as cs

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import BetweenCombatsContext
    from ..entity import Entity
    from ..policy import GameState, IncomingAttackContext
    from ..rng import SeededRNG


#: The concentration spell: a flat attack-roll buff on the caster, held by
#: concentration so that incoming damage can take it away.  Deliberately the SIMPLEST
#: shape that populates the channel — a flat +1 rather than Bless's +1d4 — because the
#: subject exists to exercise concentration, and a die inside the buff would put the
#: baseline's own accuracy at the mercy of a second random variable.
CONCENTRATION_SOURCE = "baseline_focus"
CONCENTRATION_ATTACK_BONUS = 1

#: The save-forcing spell: save-for-half against the target's DEX, the character side
#: of the saves channel.  Scales with the slot level spent (2d8 at 1st, +1d8 per level
#: above) the way a damaging spell does; the policy spends the LOWEST slot it has, so
#: the resource ledger drains from the bottom like a real daily plan.
SAVE_SPELL_SOURCE = "baseline_burst"
SAVE_SPELL_BASE_DICE = (2, 8)
SAVE_SPELL_SAVE = "dex_save"
SAVE_SPELL_DAMAGE_TYPE = "fire"

#: The in-combat heal: a self-heal on the round the character has taken damage and a
#: slot to spare.  ``healing_by_source`` needs a producer in the ``combat`` context,
#: and every shipped build heals out of combat by preference (healing.md §11.1), so
#: without this the context is structurally empty for every subject.
HEAL_DICE = (2, 8)

#: The between-combats heal, MEAN-FIELD (healing.md §7a): it draws nothing, because an
#: out-of-combat die would shift the shared stream for every build and break every
#: ``GOLDEN_DPR`` point at once.
BETWEEN_HEAL_DICE = (2, 8)

#: The ally-targeted buff (axis): a flat AC modifier installed on one ally, so the
#: ``allies`` role is exercised as a buff TARGET and not only as a damage sink.
ALLY_BUFF_SOURCE = "baseline_ward"
ALLY_BUFF_AC = 2

#: The reaction-mitigation axis: a Shield-like AC bump offered on an incoming hit,
#: taken only when it would flip the hit to a miss (the policy sees the roll).
MITIGATION_AC_BONUS = 5


class BaselineCharacterPolicy:
    """The baseline character's daily plan (§3.5.1).

    Parameters
    ----------
    level:
        1-20.  Every capability is available at every level, which is deliberate:
        a core capability that switches on partway up would make the low levels a
        different measurement from the high ones, which is the comparability defect
        §3.5 exists to remove.
    character / target:
        The subject and what it attacks.
    rounds_per_combat:
        Bounds the pre-rolled AoO round.
    aoo_per_combat:
        **A DECLARED PARAMETER**, not a constant, because there is no spatial model:
        "the enemy moves out of reach" is a frequency and the frequency is an
        assumption §4 has to record.  Default 1, War Angel's convention.
    allies:
        Friendlies in the roster, read ONLY by the ``ally_buff`` axis.  Supplied by
        the adapter from the declared party (§3.5.2), so the buff lands on a real
        entity rather than on one this policy invents — which would be a second
        source for the party.
    summon_entity / ally_buff / reaction_mitigation:
        The three declared axes, all default OFF.  ``summon_entity`` is the entity
        itself rather than a boolean, because the factory has to create it so the
        ADAPTER can tag it ``summons`` in the roster — the per-summon column the axis
        exists to populate does not exist otherwise.
    """

    def __init__(
        self,
        level: int,
        character: "Entity",
        target: "Entity",
        rounds_per_combat: int = 4,
        aoo_per_combat: int = 1,
        allies: "list[Entity] | None" = None,
        summon_entity: "Entity | None" = None,
        ally_buff: bool = False,
        reaction_mitigation: bool = False,
    ) -> None:
        if level not in cs.LEVELS:
            raise ValueError(
                f"BaselineCharacterPolicy supports levels {cs.LEVELS[0]}-"
                f"{cs.LEVELS[-1]}, got {level}."
            )
        if aoo_per_combat < 0:
            raise ValueError(f"aoo_per_combat must be >= 0, got {aoo_per_combat}.")
        if aoo_per_combat > rounds_per_combat:
            # The rounds are DISTINCT (see on_combat_start), so more opportunity
            # attacks than rounds is not a bigger number — it is incoherent, and
            # silently capping it would make the declared parameter a wish.
            raise ValueError(
                f"aoo_per_combat={aoo_per_combat} exceeds rounds_per_combat="
                f"{rounds_per_combat}: there is one reaction per round, so the "
                "opportunity attacks are pre-rolled onto DISTINCT rounds and more "
                "of them than there are rounds cannot be delivered."
            )
        self.level = level
        self.character = character
        self._target = target
        self._rounds = rounds_per_combat
        self._aoo_per_combat = aoo_per_combat
        self._allies = list(allies or [])
        # The summon axis's entity, handed in by the factory rather than created
        # mid-combat. Silvertail's pattern (its companion is in the roster from day
        # start), and the reason is the ROSTER: a mid-combat `create_entity` never
        # reaches `Roster.summons`, so the per-summon damage column the axis exists
        # to populate would not exist. Measured — `dpr_by_role[summons]` read
        # UNAVAILABLE with the axis on. Mid-combat creation is already covered by
        # test_silvertail's cast_effect-summons test, so nothing is lost.
        self._summon_entity = summon_entity
        self._summon_axis = summon_entity is not None
        self._ally_buff_axis = ally_buff
        self._mitigation_axis = reaction_mitigation

        self._attacks = cs.baseline_attacks(level)
        self._slots = cs.baseline_spell_slots(level)

        # Pre-rolled at on_combat_start; the rounds that carry this combat's AoOs.
        self._aoo_rounds: list[int] = []
        # Per-combat flags, reset at on_combat_start (round numbers restart at 1).
        self._ally_buffed = False
        self._last_mitigation_round = -1
        # Per-day flag.
        self._between_healed = False

    # ------------------------------------------------------------------
    # Per-combat setup — the only place this policy draws
    # ------------------------------------------------------------------

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        """Pre-roll which rounds carry this combat's opportunity attacks.

        War Angel's convention, and the reason it is a pre-roll rather than a
        condition: **there is no spatial model**, so an AoO cannot be triggered by
        anything the engine knows about.  Collapsing the timing into a uniformly
        random round makes the frequency explicit and keeps ``decide`` dice-free
        (CLAUDE.md #7).

        ``aoo_per_combat=0`` draws NOTHING, so a run that declares the subject takes
        no opportunity attacks is not merely equivalent to one with a different AoO
        count — it is a different dice stream, which is what a declared parameter
        should be.

        **THE ROUNDS ARE DISTINCT, and the first cut's were not.** Drawing each round
        independently let two opportunity attacks land on the same round, where there
        is only ONE reaction — so the scheduler dropped the second and
        ``aoo_per_combat=2`` delivered fewer than 2, silently. A declared parameter
        that quietly means "at most this many" is not a declaration. Two reactions in
        one round is RAW-impossible anyway, so distinctness is both the honest model
        and what makes the parameter mean what it says.

        Drawing from the REMAINING rounds (``roll_one`` over a shrinking pool, then
        pop) costs exactly ``aoo_per_combat`` draws — a fixed count, so the stream
        shape does not depend on how many collisions happened to occur. And at
        ``aoo_per_combat=1`` it is bit-identical to the independent draw it replaces:
        ``roll_one(rounds)`` over the full pool, with the index mapping back to the
        same round number.
        """
        available = list(range(1, self._rounds + 1))
        self._aoo_rounds = []
        for _ in range(self._aoo_per_combat):
            if len(available) == 1:
                # A pool of one is DETERMINED, and the dice channel cannot roll a
                # 1-sided die (`SeededRNG.roll` refuses sides < 2). Taking it without
                # a draw is the same convention `BaselineEnemyPolicy._weighted_pick_stat`
                # already uses for a degenerate weight total. The draw count stays a
                # function of (aoo_per_combat, rounds_per_combat) alone, so the stream
                # shape is still fixed for a given config — which is the property that
                # matters.
                self._aoo_rounds.append(available.pop())
                continue
            self._aoo_rounds.append(available.pop(rng.roll_one(len(available)) - 1))
        self._ally_buffed = False
        self._last_mitigation_round = -1

    def on_day_start(self) -> None:
        """Reset the per-day flags.  Called by the factory's before-combat hook on
        the day's first combat; harmless to call more often."""
        self._between_healed = False

    # ------------------------------------------------------------------
    # The decision point — pure read, no dice, no mutation
    # ------------------------------------------------------------------

    def decide(self, snapshot: "GameState") -> list[Choice]:
        """The daily plan, one economy slot at a time.

        Structured as three independent blocks — ACTION, REACTION, BONUS ACTION —
        because the three slots ARE independent (CLAUDE.md #11) and the first cut did
        not keep them that way: a round-1 early return dropped the opportunity attack
        whenever its pre-rolled round was 1, so ``reactions_per_round`` read 0.184
        against the 0.25 that ``aoo_per_combat=1`` requires. A quarter of them, lost
        silently, because a quarter of rounds are round 1.

        THE ACTION's cadence is a real modelling choice: concentration on round 1,
        the save-forcing spell on round 2, weapon attacks on every other round. One
        save cast per combat rather than "cast whenever a slot remains", because the
        subject's job is to populate EVERY core channel and a policy that spends its
        action on a spell whenever it can leaves the §8.1 attacks channel reading
        ~0.95 attacks per round on a two-attack character — a measured number, and
        the wrong fixture.

        THE BONUS ACTION is contended, so its priority is DECLARED rather than
        emergent: ally buff (once per combat) > in-combat heal > commanding the
        summon. The heal outranks the summon because the heal is CORE and the summon
        is an axis, and an axis that empties a core channel would make the fixture
        worse the more of it you turn on. The once-per-combat buff outranks the heal
        because the heal can wait a round and the buff cannot. Resolving this here is
        the policy's job: ``decide`` is a pure read, so the snapshot's counts do not
        fall as choices are emitted, and emitting two bonus-action choices would have
        the scheduler drop the second with a warning (which is how the collision was
        found).
        """
        choices: list[Choice] = []
        round_ = snapshot.round_number
        resources = snapshot.resources

        # ---------------- THE ACTION ----------------------------------------
        if round_ == 1 and self.character.concentration is None:
            # Concentration: the only thing control pressure can take away, which is
            # why it is core rather than an axis.
            choices.append(Choice(
                action_type="cast_effect",
                cost="action",
                effect_source=CONCENTRATION_SOURCE,
                concentration=True,
                modifiers=[Modifier(stat="attack_bonus",
                                    value=CONCENTRATION_ATTACK_BONUS,
                                    source=CONCENTRATION_SOURCE)],
                duration="combat",
            ))
        elif round_ == 2 and (slot := self._lowest_slot(resources)) is not None:
            # The save-forcing spell — the saves channel keyed by ability, from the
            # CHARACTER's side. Every other producer in the corpus is the enemy, so
            # without this the channel has no subject-side fixture at all.
            #
            # Lowest slot first, so the ledger drains from the bottom: a plan that
            # spent its top slot in combat 1 would make dpr_by_combat's shape an
            # artifact of the policy rather than of resource depletion.
            level = int(slot.rsplit("_", 1)[1])
            n, sides = SAVE_SPELL_BASE_DICE
            choices.append(Choice(
                action_type="save_spell",
                cost="action",
                target=self._target,
                save_stat=SAVE_SPELL_SAVE,
                dc_stat="spell_save_dc",
                damage_dice=(n + level - 1, sides),
                on_save="half",
                damage_type=SAVE_SPELL_DAMAGE_TYPE,
                resource_cost={slot: 1},
                effect_source=SAVE_SPELL_SOURCE,
            ))
        else:
            # Weapon attacks — the §8.1 attacks channel.
            for i in range(self._attacks):
                choices.append(Choice(
                    action_type="attack",
                    cost="action" if i == 0 else "none",
                    target=self._target,
                    weapon_stat="attack_bonus",
                ))

        # ---------------- THE REACTION --------------------------------------
        #
        # Unconditional on what the action did — see the docstring.
        for _ in range(self._aoo_rounds.count(round_)):
            choices.append(Choice(
                action_type="attack",
                cost="reaction",
                target=self._target,
                weapon_stat="attack_bonus",
            ))

        # ---------------- THE BONUS ACTION (declared priority) --------------
        if resources.get("bonus_action", 0) >= 1:
            heal_slot = self._lowest_slot(resources,
                                          exclude=self._slots_used(choices))
            if (self._ally_buff_axis and not self._ally_buffed and round_ == 2
                    and self._allies):
                # AXIS: the `allies` role as a buff TARGET rather than a damage sink.
                # Lands on an ally from the ROSTER, handed in by the adapter — a
                # policy that invented its own ally would be a second source for the
                # party (§3.5.2), so with no allies the axis simply does not fire.
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="bonus_action",
                    target=self._allies[0],
                    effect_source=ALLY_BUFF_SOURCE,
                    modifiers=[Modifier(stat="ac", value=ALLY_BUFF_AC,
                                        source=ALLY_BUFF_SOURCE)],
                    duration="combat",
                ))
                self._ally_buffed = True
            elif (self.character.hp < self.character.max_hp
                    and heal_slot is not None):
                # CORE: the `combat` context of healing_by_source, which NO shipped
                # build populates — every one of them heals out of combat by
                # preference (healing.md §11.1), so this context was structurally
                # empty for every subject the framework had.
                choices.append(Choice(
                    action_type="heal",
                    cost="bonus_action",
                    heal=HealSpec(dice=HEAL_DICE, targets=[self.character]),
                    resource_cost={heal_slot: 1},
                    effect_source="baseline_mend",
                ))
            elif (self._summon_entity is not None
                    and not self._summon_entity.is_out_of_action):
                # AXIS: COMMAND the summon (substrate #7 / 7a). `actor=` is the
                # commanded-action override, so the swing uses the SUMMON's stats and
                # is attributed to it — which is what makes the per-summon damage
                # column fall out of the per-(source, target) ledger. The command
                # costs the COMMANDER's bonus action, which is the real
                # action-economy contention 7a exists to model.
                choices.append(Choice(
                    action_type="attack",
                    cost="bonus_action",
                    actor=self._summon_entity,
                    target=self._target,
                    weapon_stat="attack_bonus",
                ))

        return choices

    # ------------------------------------------------------------------
    # The defender side (axis) — the on_incoming_hit seam
    # ------------------------------------------------------------------

    def on_incoming_hit(self, ctx: "IncomingAttackContext") -> "InterceptResponse | None":
        """The reaction-mitigation axis: a Shield-like AC bump, once per round.

        Default OFF.  Taken only when it would flip the hit to a miss — the policy
        sees the roll, so reacting to a hit it cannot stop would spend the reaction
        for nothing.

        ``reaction_by`` is set, so this is counted by the §13 reactions channel
        (§8.2a).  No economy slot is debited, which is the convention
        ``InterceptResponse`` documents and the War Angel guide prices: with the
        opportunity attack also on, the subject double-books its reaction exactly as
        War Angel L14+ does, and ``reactions_per_round`` is where that shows. The
        baseline REPRODUCES the convention rather than quietly fixing it, because a
        subject whose reaction economy differs from the builds it exists to make
        comparable would be measuring something else.
        """
        if not self._mitigation_axis:
            return None
        if self._last_mitigation_round == ctx.round_number:
            return None
        if MITIGATION_AC_BONUS <= ctx.hit_margin:
            return None
        self._last_mitigation_round = ctx.round_number
        return InterceptResponse(ac_bonus=MITIGATION_AC_BONUS,
                                 reaction_by=ctx.defender.id)

    # ------------------------------------------------------------------
    # Out of combat
    # ------------------------------------------------------------------

    def between_combats(self, ctx: "BetweenCombatsContext") -> None:
        """The ``between`` context of ``healing_by_source``, once per day.

        **MEAN-FIELD, and that is load-bearing** (healing.md §7a, CLAUDE.md): healing
        applied outside combat draws NOTHING.  Out-of-combat code runs at a point
        every build passes through, so one ``rng.roll()`` here would shift every
        subsequent die for every build and break every ``GOLDEN_DPR`` point at once.
        """
        if self._between_healed:
            return
        resolve_healing(
            self.character,
            HealSpec(dice=BETWEEN_HEAL_DICE, targets=[self.character]),
            mean_field=True, telemetry=ctx.telemetry, context="between",
        )
        spend_hit_dice_at_short_rest([self.character], ctx.telemetry)
        self._between_healed = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _lowest_slot(self, resources: dict,
                     exclude: "set[str] | None" = None) -> "str | None":
        """The lowest-level spell slot with a charge left, skipping ``exclude``.

        Lowest-first rather than highest-first so the ledger drains from the bottom:
        a daily plan that spent its top slot on round 1 of combat 1 would make
        ``dpr_by_combat``'s shape an artifact of the policy rather than of resource
        depletion.
        """
        skip = exclude or set()
        for i in range(1, len(self._slots) + 1):
            name = f"spell_slot_{i}"
            if name not in skip and resources.get(name, 0) >= 1:
                return name
        return None

    @staticmethod
    def _slots_used(choices: list[Choice]) -> set[str]:
        """Slot names already claimed by choices emitted this turn.

        ``decide`` is a pure read, so the snapshot's resource counts do not fall as
        it emits; without this the save spell and the heal could both claim the same
        slot and the scheduler would silently drop the second (its affordability
        check is per choice, not per turn).
        """
        used: set[str] = set()
        for choice in choices:
            for name in (choice.resource_cost or {}):
                if name.startswith("spell_slot_"):
                    used.add(name)
        return used

    @staticmethod
    def _spent_action(choices: list[Choice]) -> bool:
        return any(c.cost == "action" for c in choices)

    # ------------------------------------------------------------------
    # Provenance (§4)
    # ------------------------------------------------------------------

    def describe_parameters(self) -> dict:
        """The RESOLVED knobs, for §4.  A pure read.

        ``aoo_per_combat`` is reported with its APPROXIMATION named, because the
        number alone does not tell a reader that it is a frequency standing in for an
        absent spatial model — which is precisely the kind of buried assumption §4
        exists to surface.
        """
        return {
            "policy": "baseline_character",
            "level": self.level,
            "rounds_per_combat": self._rounds,
            "attacks_per_action": self._attacks,
            "spell_slots": list(self._slots),
            "aoo_per_combat": self._aoo_per_combat,
            "aoo_model": (
                "one opportunity attack per combat on a round pre-rolled at "
                "on_combat_start through the seeded channel. THERE IS NO SPATIAL "
                "MODEL, so 'the enemy moves out of reach' is a FREQUENCY and not an "
                "event; the count is declared so this assumption is recorded rather "
                "than buried (§3.5.1). War Angel's convention, which its guide "
                "reached by collapsing five AoO timing slots into one."
            ),
            "core": ["weapon_attacks", "concentration_spell", "save_forcing_spell",
                     "healing_in_combat", "healing_between_combats",
                     "spell_slot_budget", "opportunity_attack"],
            "axes": {
                "summon": self._summon_axis,
                "ally_buff": self._ally_buff_axis,
                "reaction_mitigation": self._mitigation_axis,
            },
            "ally_buff_targets": [a.name for a in self._allies[:1]],
            "concentration_source": CONCENTRATION_SOURCE,
            "save_spell": {
                "save_stat": SAVE_SPELL_SAVE,
                "base_dice": list(SAVE_SPELL_BASE_DICE),
                "damage_type": SAVE_SPELL_DAMAGE_TYPE,
                "slot_order": "lowest available first",
            },
            "healing": {
                "in_combat": {"dice": list(HEAL_DICE), "rolled": True},
                "between_combats": {"dice": list(BETWEEN_HEAL_DICE),
                                    "rolled": False,
                                    "note": "MEAN-FIELD — draws no dice "
                                            "(healing.md §7a)"},
            },
        }


# ---------------------------------------------------------------------------
# The summon axis's entity
# ---------------------------------------------------------------------------

def make_baseline_summon(level: int, name: "str | None" = None) -> "Entity":
    """The ``summon`` axis's controlled ally.

    A deliberately WEAK attacker rather than a second baseline character: the axis
    exists to populate the per-summon column and exercise the roster-scoping checks
    (the per-METRIC ritual's first question), and a summon that matched the character
    would make "did this metric pool the two?" undetectable — which is the one thing
    the fixture is for.  Finite HP, so ``zero_hp_category`` is exercised too.
    """
    from ..entity import Entity

    return Entity(
        name=name or f"BaselineSummon-L{level}",
        hp=max(10, 5 * level),
        base_stats={
            "ac": cs.baseline_ac(level) - 2,
            "attack_bonus": cs.baseline_pb(level) + 2,
            "damage_dice": (1, 6),
            "damage_bonus": 2,
            **cs.baseline_saves(level),
        },
    )


# ---------------------------------------------------------------------------
# Full day-runner assembly
# ---------------------------------------------------------------------------

def make_day_runner(
    level: int,
    rng: "SeededRNG",
    rounds_per_combat: int = 4,
    aoo_per_combat: int = 1,
    summon: bool = False,
    ally_buff: bool = False,
    reaction_mitigation: bool = False,
):
    """Assemble ``(DayRunner, character, dummy, summon_or_None)``.

    FOUR values, like Silvertail's factory and for the same reason: a summon has to
    be in the roster for its damage column to exist, so the adapter needs it back.
    Returning ``None`` rather than omitting it keeps the arity fixed — the
    tuple-position coupling §3.3 exists to remove is at its worst when the LENGTH
    varies.

    The enemy NEVER acts here and the party is NOT built here (§3.4 / §3.5.2): the
    dummy is a passive target carrying the definitive table's full stat block, and
    ``RunConfig.enemy`` / ``RunConfig.party_size`` declare both, installed over this
    roster by the framework's seams.  So a bare factory run gives DPR = the
    character's whole output against a target that does nothing back.

    ``allies`` is deliberately NOT a parameter.  The ``ally_buff`` axis needs a
    target, and the only honest source for one is the roster the framework builds —
    a factory parameter would be a second place the party is declared, which is what
    retired ``with_party``.  The ADAPTER wires the roster's allies into the policy
    after ``party.install`` has run.
    """
    from ..day_runner import DayRunner
    from . import enemy_stats

    character = cs.make_baseline_character(level)
    dummy = enemy_stats.make_baseline_enemy(level)
    beast = make_baseline_summon(level) if summon else None
    policy = BaselineCharacterPolicy(
        level=level, character=character, target=dummy,
        rounds_per_combat=rounds_per_combat, aoo_per_combat=aoo_per_combat,
        summon_entity=beast, ally_buff=ally_buff,
        reaction_mitigation=reaction_mitigation,
    )
    entities = [character, dummy] if beast is None else [character, beast, dummy]
    runner = DayRunner(
        rng=rng,
        entities=entities,
        # The summon gets NO policy of its own: it is COMMANDED on its controller's
        # turn (design.md §1), which is what `Choice.actor` is for.
        policies={character.id: policy},
        rounds_per_combat=rounds_per_combat,
        between_combats=policy.between_combats,
    )
    return runner, character, dummy, beast
