"""
metrics.py — the metric registry (evaluation_framework.md §5.1 / §5.2).

Metrics are **registered, not incidental**.  Same philosophy as the closed verb set
and §13's closed telemetry-channel vocabulary: you extend it the way you add a verb
— deliberately, with the denominator stated — never by computing a number inline in
a report.  Three payoffs (§5.1): the metric set stays deliberate, the registry IS
the data dictionary a downstream site renders, and every denominator is forced into
the open.

Denominators are the comparability trap (§5.2)
----------------------------------------------
"Damage per round" and "damage per round the character actually acted" are
different numbers, and a report that does not say which it means is not
interpretable.  So a denominator is not a scalar buried in an expression — it is a
named entry in :data:`DENOMINATORS`, carrying its own description and the §5.2
rules that apply to it.  Two of those rules are load-bearing:

* **A control-lost turn STAYS in the ``rounds`` denominator.**  That is precisely
  how control pressure manifests as reduced DPR; removing it would make control
  free.
* **``fixed_length`` is the standard basis.**  ``finite_hp``'s emergent length would
  change ``rounds`` to ``total_rounds`` and silently break comparability with the
  4×4 baseline, so it is a flagged alternate mode, not a quiet substitution.

Availability — the reason this module is not just a list of lambdas
-------------------------------------------------------------------
Several §5.3 panel metrics read telemetry channels that are STRUCTURALLY EMPTY
today, and emitting their zeros would be actively misleading — a control-resilience
metric reading 0.0 says "this build resists control perfectly", which is the
opposite of the truth ("we cannot measure this yet").  Three such cases exist right
now, and none of them is War-Angel-specific:

1. **control** — no build constructs ``BaselineEnemyPolicy(control=True)``, and War
   Angel / Starfire Scion use ``ScriptedEnemyPolicy``, which has no control channel
   at all (§3.4: *the three builds do not currently face the same enemy model*).
   ``RunConfig.enemy_options`` is hard-rejected until the §13 step-5 enemy seam, so
   it cannot even be switched on from the framework.
2. **mitigation** — §5's ``mult(t)`` is installed on ``Entity.damage_multiplier`` at
   construction, and no build factory installs one.
3. **resource economy** — ``CombatTelemetry.record_resource`` exists but resolution
   has no call site for it, so the channel is scaffolding, not data.

Each metric therefore declares an ``availability`` predicate returning a REASON
string when the run cannot produce it.  The report renders those as explicit
"unavailable" rows (§3.4's requirement), never as zeros.

The ``attacks`` channel went LIVE in s49 (§13 step 4, shape locked in §8.1), which
leaves control and mitigation as the two structurally-empty channels above.  It is
worth recording what it cost to wire, because the number is the argument for the
seam: ONE record call in ``resolve_attack_roll``, from values already in local
variables, and the §12 parity proof did not move.  Its two declarations —
``attacks_per_round`` and the ``attack_roll_rate`` breakdown — also forced
``BreakdownDef.sum_rule`` from an inference to a declaration: it is the first
breakdown that is CROSSED and still non-additive, because a crit is also a hit.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from itertools import product
from typing import TYPE_CHECKING, Any, Callable, Iterator

from ..telemetry import ATTACK_PROPERTIES, HEAL_CONTEXTS, SAVE_CHANNELS
from .statistics import (
    DEFAULT_CONVERGENCE,
    SCALE_INTERVAL,
    SCALE_RATIO,
    SCALES,
    DEFAULT_DISTRIBUTION_CONVERGENCE,
    DEFAULT_RESAMPLES,
    DEFAULT_STATISTICS,
    RARE_EVENT_CONVERGENCE,
    Convergence,
    DistributionConvergence,
    Statistic,
)

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import DayResult
    from ..telemetry import CombatTelemetry
    from .config import RunConfig
    from .roster import Roster

#: The engine's saving-throw stat vocabulary (``resolve_saving_throw``'s
#: ``save_stat``; mirrors ``enemy_stats._SAVE_KEYS``).  The per-ability metric
#: family is generated over exactly this tuple, so "by type" in §5.3 means a
#: closed, complete set rather than whatever happened to fire.
SAVE_STATS = ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save")

#: The engine's damage-type vocabulary (mirrors ``enemy_stats._DAMAGE_TYPES``, the
#: 13 types the frozen band table prices).  The outgoing-composition family is
#: generated over all of them, so a zero is a real measurement ("this build deals no
#: cold damage") rather than an absent row — the same completeness argument as the
#: per-ability save family.
DAMAGE_TYPES = ("acid", "bludgeoning", "cold", "fire", "force", "lightning",
                "necrotic", "piercing", "poison", "psychic", "radiant",
                "slashing", "thunder")

#: The roster roles a breakdown may key on.  Deliberately NOT ``roster.ROLES`` —
#: ``enemies`` is excluded because no metric in this registry describes the enemy's
#: own column, and healing in particular never targets one (healing.md §5).
ATTRIBUTABLE_ROLES = ("characters", "summons", "allies")

#: §5.4's margin sentinel: a key position holding ``ALL`` means "every key on this
#: dimension", and every numerator maps it to "no filter".  One numerator function
#: therefore serves both the cells and their declared margins.
ALL = "*"

# ---------------------------------------------------------------------------
# The summing rule (§5.4) — a CLOSED vocabulary, DECLARED not inferred (s49)
# ---------------------------------------------------------------------------
# These lived in ``artifact.py`` until s49, where ``sum_rule_of`` DERIVED the rule
# as ``crossed ? partition : overlap``.  Every breakdown shipped before s49 happened
# to make that true, which is the only reason the inference survived — and the
# attacks breakdown (§8.1) is the counter-example: it is CROSSED, because the cross
# is the question, and its cells still do not partition, because a crit is a hit.
#
# Whether cells partition their total is a fact about WHAT THEY MEASURE, not about
# how many dimensions they have, so it is now a field on ``BreakdownDef`` — the same
# move s48 made with ``MetricDef.scale``, for the same reason.  They live here
# rather than in the serializer because the serializer must not be the place a
# semantic fact is decided; ``artifact`` re-exports them, so every existing import
# site is unaffected.

#: The cells are disjoint and DO sum to the declared margin.
SUM_RULE_PARTITION = "cells_partition_total"
#: Adding every cell double-counts.  Two independent reasons reach this value: an
#: UNCROSSED breakdown, where each dimension covers the whole quantity on its own
#: (read the declared margin instead), and a crossed breakdown whose KEYS are not
#: disjoint (``attack_roll_rate``: a crit is also a hit, and advantage is a condition
#: of the roll rather than an outcome of it, so there is nothing to read instead).
SUM_RULE_OVERLAP = "cells_overlap_do_not_sum"

SUM_RULES = (SUM_RULE_PARTITION, SUM_RULE_OVERLAP)


# ---------------------------------------------------------------------------
# What a metric extractor sees
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DaySample:
    """One adventuring day, as the metric extractors read it.

    ``damage_dealt`` / ``damage_taken`` are passed in already computed by the
    runner rather than re-derived per metric: ``DayResult.damage_by_source`` walks
    the whole per-(source, target) ledger, and ~27 registered metrics re-walking it
    every day turns an O(days) run into an O(days × metrics × ledger) one.
    ``telemetry`` is likewise the day's MERGED accumulator, computed once — the
    ``DayResult.telemetry`` property re-merges its four combats on every access.
    """

    config: "RunConfig"
    roster: "Roster"
    result: "DayResult"
    damage_dealt: dict[int, int]
    damage_taken: dict[int, int]
    telemetry: "CombatTelemetry"

    @property
    def own_roles(self) -> "tuple[str, ...]":
        """The roles this run attributes to the build (``RunConfig.attribution``).

        ``("characters",)`` or ``("characters", "summons")``. Read by every metric
        that means "the build's own output", so the headline, its per-combat
        decomposition and the typed-composition family can never disagree about
        whose damage they are describing.
        """
        return self.config.own_roles

    def dealt(self, *roles: str) -> float:
        """Damage DEALT by every entity in the given roster roles."""
        return float(sum(self.damage_dealt[i] for i in self.roster.ids(*roles)))

    def own_damage(self) -> float:
        """Damage dealt by whatever this run attributes to the build."""
        return self.dealt(*self.own_roles)

    def taken(self, *roles: str) -> float:
        """Damage RECEIVED by every entity in the given roster roles."""
        return float(sum(self.damage_taken[i] for i in self.roster.ids(*roles)))

    def saves(self, *, stat: "str | None" = None, channel: "str | None" = None,
              outcome: str = "forced") -> float:
        """A slice of the §13 saves channel: forced / passed / failed counts."""
        total = 0
        for (ab, ch), tally in self.telemetry.saves.items():
            if stat is not None and ab != stat:
                continue
            if channel is not None and ch != channel:
                continue
            total += getattr(tally, outcome)
        return float(total)

    def control(self, attr: str,
                *, roles: "tuple[str, ...] | None" = None) -> float:
        """A field of the CREDITED half of the §13 control channel (``failures`` /
        ``turns_lost`` / ``turns_reduced``), scoped to roster ROLES.

        Scoped since s51: the channel gained a controlled-ACTOR key so that this half
        and the realized half beside it answer the same question about the same
        entities (§7.6).  Before that it summed over whoever failed the save, which on
        a summon-focused run meant the two halves described different populations while
        sitting adjacent in the panel.
        """
        tally = self.telemetry.control_for(
            set(self.roster.ids(*(roles if roles is not None else self.own_roles))))
        return float(getattr(tally, attr))

    def control_applied(self, attr: str,
                        *, roles: "tuple[str, ...] | None" = None) -> float:
        """A field of the REALIZED half of the §13 control channel, scoped to roster
        ROLES (§7.6) — what control actually COST, as drawn out of the account.

        No metric reads this today, deliberately: the credited rows are now equal to
        it by construction, so publishing both would publish one quantity twice.  It
        stays because it is what PROVES that equality — a test asserts the two halves
        agree, which is a real check precisely because they are written at different
        places (save time vs turn boundary) — and because it carries
        ``suppressed_turns``, the count of WHOLE turns skipped, which the credited half
        cannot express and which is the only quantity here with the
        resource-preservation property (§7.1.2).
        """
        tally = self.telemetry.control_applied_for(
            set(self.roster.ids(*(roles if roles is not None else self.own_roles))))
        return float(getattr(tally, attr))

    def mitigation(self, attr: str, *, damage_type: "str | None" = None,
                   roles: "tuple[str, ...] | None" = None) -> float:
        """A summed field of the §13 mitigation channel.

        Scoped to the given roster ROLES by default — the channel is keyed
        ``(actor_id, damage_type)`` precisely so a summon's radiant damage and a
        typed-damage enemy's swings do not pool into the character's composition.
        """
        cells = self.telemetry.mitigation_by_type(
            set(self.roster.ids(*(roles if roles is not None else self.own_roles)))
        )
        if damage_type is not None:
            cell = cells.get(damage_type)
            return float(getattr(cell, attr)) if cell is not None else 0.0
        return float(sum(getattr(m, attr) for m in cells.values()))

    def combat_damage(self, combat_num: int,
                      *, roles: "tuple[str, ...] | None" = None) -> float:
        """Damage dealt in ONE of the day's combats (1-indexed) by the given roles.

        The four-combat day exists to expose resource depletion, and a day-level
        mean hides it completely: a nova build and a sustain build can post the
        same daily total with entirely different shapes.

        Read from the per-(source, target) ledger, NOT from ``damage_by_combat``:
        that property sums ``damage_log``, which is every actor's damage including
        the enemy's, so a per-combat figure built on it would silently stop being
        the character's column the moment the enemy strikes back.
        """
        combats = self.result.combats
        if len(combats) < combat_num:
            return 0.0
        ids = set(self.roster.ids(*(roles if roles is not None else self.own_roles)))
        return float(sum(
            damage for (source, _target), damage
            in combats[combat_num - 1].damage_by_source_target.items()
            if source in ids
        ))

    def healing(self, *, source_roles: "tuple[str, ...] | None" = None,
                target_roles: "tuple[str, ...] | None" = None,
                context: "str | None" = None) -> float:
        """A slice of the §13 healing channel, keyed ``(source, target, context)``.

        ALWAYS scoped by role rather than read as a bare total: the channel holds
        the character's Hit Dice, its Prayer of Healing and the summon's own
        self-healing in one ledger, and an unfiltered sum pools all three — the
        aggregate-ledger trap the per-METRIC ritual names.  ``context`` is a real
        filter and never a summed field: healing.md §11.1 found the corpus does
        most of its healing OUT of combat by preference, so healing under fire and
        healing at leisure are different quantities.
        """
        kwargs: dict[str, Any] = {}
        if source_roles is not None:
            kwargs["source_ids"] = set(self.roster.ids(*source_roles))
        if target_roles is not None:
            kwargs["target_ids"] = set(self.roster.ids(*target_roles))
        return float(self.telemetry.healing_total(context=context, **kwargs))

    def attacks(self, attr: str = "forced",
                *, roles: "tuple[str, ...] | None" = None) -> float:
        """A field of the §13 attacks channel, scoped to roster ROLES (§8.1).

        Scoped by role for a sharper reason than the other channels: the ledger is
        keyed by actor and holds the character's rolls, a summon's and the ENEMY's,
        and while a pooled damage TOTAL is still a total, a pooled hit RATE is a
        roll-weighted average over several to-hit profiles and describes none of
        them.  Defaults to the attributed roles, which is what the per-round COUNT
        wants; every rate cell passes its own single role.
        """
        tally = self.telemetry.attacks_for(
            set(self.roster.ids(*(roles if roles is not None else self.own_roles))))
        return float(getattr(tally, attr))

    def other_roles(self) -> "tuple[str, ...]":
        """The healable roles this run does NOT attribute to the build.

        Enemies are absent by construction (:data:`ATTRIBUTABLE_ROLES`) because they
        are never healed (healing.md §5).  Under ``attribution='character'`` this is
        ``("summons", "allies")``; under ``'character_and_summons'`` a summon is part
        of the build, so healing it stops being "provided to others" — which is what
        makes the output metric follow the attribution axis (§14 point 3).
        """
        return tuple(r for r in ATTRIBUTABLE_ROLES if r not in self.own_roles)

    def opening_round_damage(self) -> float:
        """Damage the ENEMIES took in the first round of each combat, summed over
        the day — i.e. the PARTY's opening-round output.

        Party-scoped, not character-scoped, and the metric using it says so: the
        per-round log (``CombatResult.damage_received``) is keyed by target only,
        while the source-attributed ledger (``damage_by_source_target``) is
        per-combat cumulative.  Character-only round-1 damage would need a
        per-(round, source) ledger, which is a real change and not this one.
        """
        enemy_ids = self.roster.ids("enemies")
        return float(sum(
            combat.damage_received[i][0]
            for combat in self.result.combats
            for i in enemy_ids
            if combat.damage_received.get(i)
        ))


@dataclass(frozen=True)
class RunContext:
    """What an availability predicate sees — everything a run knows about ITSELF
    before any day is simulated, so an unavailable metric costs no collection."""

    config: "RunConfig"
    roster: "Roster"
    described: dict[str, Any]

    @property
    def enemy(self) -> dict[str, Any]:
        """The §4 RESOLVED enemy block (``evaluation/enemy.resolve``).

        DERIVED rather than declared, and that is defensible under the s49 rule
        ("declare it, or prove the derivation") because the two facts cannot come
        apart: ``resolve`` is a pure function of exactly ``(config, described)``,
        both of which this context already holds, so there is no state in which a
        context's enemy block could legitimately differ from the one computed here.
        This is the s48 ``interval``-from-``statistic`` case, not the s49
        ``sum_rule`` case — the test is independence, and here there is none.

        Deriving it also means every existing ``RunContext`` construction — the
        runner's and every fixture's — gets a correct enemy block for free, so an
        availability predicate can read the enemy without the caller remembering to
        supply it.  A predicate that had to be handed the block would silently see
        ``{}`` wherever someone forgot.
        """
        from .enemy import resolve

        return resolve(self.config, self.described)


# ---------------------------------------------------------------------------
# Denominators — a named, closed vocabulary (§5.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Denominator:
    """What a metric is "per".

    ``fixed`` selects the estimator (``statistics``' two kinds): True when the
    per-day value is a run constant (rounds, days, combats) and the metric is a
    plain mean; False when the denominator is itself random and correlated with
    the numerator (saves actually forced, checks actually made), where the
    ratio-of-means estimator and its linearized standard error are required.
    """

    name: str
    description: str
    fixed: bool
    per_day: Callable[[DaySample], float]

    def describe(self) -> dict[str, Any]:
        return {"description": self.description,
                "per_day_constant": self.fixed}


DENOMINATORS: dict[str, Denominator] = {
    "rounds": Denominator(
        name="rounds",
        description=(
            "combats_per_day × rounds_per_combat — a fixed 16 in the standardized "
            "4×4 basis. A control-lost turn STAYS in it (§5.2): that is how control "
            "pressure shows up as reduced DPR. Under mode='finite_hp' the honest "
            "denominator becomes total_rounds instead, which is why that mode is a "
            "flagged alternate rather than a drop-in."
        ),
        fixed=True,
        per_day=lambda s: float(s.config.rounds_per_day),
    ),
    "days": Denominator(
        name="days",
        description="One adventuring day: a long rest plus four combats.",
        fixed=True,
        per_day=lambda s: 1.0,
    ),
    "combats": Denominator(
        name="combats",
        description="Combat encounters per day (fixed at 4 by DayRunner.run_day).",
        fixed=True,
        per_day=lambda s: float(s.config.combats_per_day),
    ),
    "concentration_checks": Denominator(
        name="concentration_checks",
        description=(
            "Concentration checks forced by incoming damage (§13 economy channel). "
            "Zero on any run where the build never concentrates — a rate over it "
            "then has NO value, which is reported as such rather than as 0."
        ),
        fixed=False,
        per_day=lambda s: float(s.telemetry.concentration_checks),
    ),
    "outgoing_damage_pre_mitigation": Denominator(
        name="outgoing_damage_pre_mitigation",
        description=(
            "Typed outgoing damage before the enemy's fractional mult(t) (§5 / §13 "
            "mitigation channel)."
        ),
        fixed=False,
        per_day=lambda s: s.mitigation("outgoing_before"),
    ),
}

DENOMINATORS["combat_rounds"] = Denominator(
    name="combat_rounds",
    description=(
        "Rounds in ONE combat — the denominator for a single combat's DPR, so a "
        "per-combat figure is directly comparable to the day-level headline rather "
        "than being a quarter of it."
    ),
    fixed=True,
    per_day=lambda s: float(s.config.rounds_per_combat),
)
DENOMINATORS["opening_rounds"] = Denominator(
    name="opening_rounds",
    description=(
        "One opening round per combat (four per day) — the denominator that makes "
        "round-1 output comparable to the all-rounds headline."
    ),
    fixed=True,
    per_day=lambda s: float(s.config.combats_per_day),
)
DENOMINATORS["own_damage_dealt"] = Denominator(
    name="own_damage_dealt",
    description=(
        "All damage this run ATTRIBUTES to the build (the headline column's "
        "numerator — characters, plus summons under attribution="
        "'character_and_summons'). The denominator for shares OF the build's output."
    ),
    fixed=False,
    per_day=lambda s: s.own_damage(),
)
DENOMINATORS["outgoing_typed_damage"] = Denominator(
    name="outgoing_typed_damage",
    description=(
        "The build's total TYPED outgoing damage (§13 mitigation channel, "
        "outgoing_before summed over types). Untyped damage is excluded because it "
        "declares no type to attribute — so type shares sum to 1 over typed output, "
        "not over the headline."
    ),
    fixed=False,
    per_day=lambda s: s.mitigation("outgoing_before"),
)


# ---------------------------------------------------------------------------
# Availability predicates (§3.4's honesty requirement)
# ---------------------------------------------------------------------------

def _always(ctx: RunContext) -> "str | None":
    return None


def _requires_role(role: str) -> Callable[[RunContext], "str | None"]:
    def check(ctx: RunContext, _role: str = role) -> "str | None":
        if getattr(ctx.roster, _role):
            return None
        return f"this build's roster has no {_role} — the column does not exist for it"
    return check


#: How a run turns the control channel on, quoted in every unavailability reason
#: so the reader is never told only what is wrong.
_CONTROL_FIX = (
    "Configure enemy='baseline' with enemy_options={'control': True} (§3.4's "
    "standardized enemy) to measure it."
)


def _requires_control_channel(ctx: RunContext) -> "str | None":
    """Why this run cannot measure control — in FOUR distinguishable ways.

    Before the step-5 seam this had two branches, because the only thing that could
    vary was which enemy model a build's factory happened to pick.  The seam adds a
    genuinely different situation — the standardized enemy IS installed and its
    control channel is simply off — and collapsing that into "constructed with
    control=False" would lose the distinction the per-METRIC ritual's availability
    check exists to protect: these are different problems with different fixes, and
    only one of them is now the caller's to fix in one keyword.

    The ordering matters: the STANDARDIZED cases are tested first, because under a
    standardized enemy the build's own ``described["enemy_policy"]`` describes the
    path that was OVERWRITTEN and is no longer the run's enemy.
    """
    block = ctx.enemy
    if block["standardized"]:
        kind = block["kind"]
        if kind == "baseline":
            if block["options"].get("control"):
                return None                      # the channel is live
            return (
                "the standardized enemy is installed, but its §6 control channel is "
                f"switched off (enemy_options['control'] is False). {_CONTROL_FIX}"
            )
        if kind == "scripted":
            return (
                "enemy='scripted' is the standardized enemy's ATTACK-ROLL half only "
                "— it makes weapon attacks and forces no saves of any kind, which is "
                f"what makes it the comparison arm for 'baseline'. {_CONTROL_FIX}"
            )
        return (
            "enemy='none' is a passive target: it carries the table's stat block and "
            f"never acts, so no control save is ever forced. {_CONTROL_FIX}"
        )

    # build_default — the enemy is still a property of the character build (§3.4).
    policy = ctx.described.get("enemy_policy")
    if policy == "scripted":
        return (
            "this run uses enemy='build_default', and the build factory installed "
            "ScriptedEnemyPolicy, which has no control channel at all (§3.4: the "
            f"three builds do not face the same enemy model on this path). {_CONTROL_FIX}"
        )
    if policy == "baseline":
        return (
            "this run uses enemy='build_default', and the build factory constructed "
            "BaselineEnemyPolicy with control=False without exposing the toggle, so "
            f"the channel cannot be enabled through the factory. {_CONTROL_FIX}"
        )
    return (
        "this run uses enemy='build_default', and the enemy never acts at this level "
        "(the build's data row carries no enemy_attack), so no control save is ever "
        f"forced. {_CONTROL_FIX}"
    )


def _requires_mitigation_profile(ctx: RunContext) -> "str | None":
    """Evidence-based: §5's ``mult(t)`` lives on ``Entity.damage_multiplier``, so we
    look at whether anyone in the roster actually carries a profile.

    Kept evidence-based rather than switched to reading
    ``enemy_options['mitigation']`` when the seam landed, and the reason is the
    point: ``damage_multiplier`` is an ENTITY attribute that a build factory may
    install itself (Starfire's ``enemy_resist`` block does install a
    ``damage_response``, and a future build could install a multiplier), so the
    config flag is one cause of a profile existing and not the definition of it.
    Reading the config here would report "unavailable" for a run whose roster
    plainly carries one.
    """
    if any(e.damage_multiplier for e in ctx.roster.entities()):
        return None
    return (
        "no entity in this run carries a damage_multiplier profile, so the §13 "
        "mitigation channel records nothing. §5's mult(t) is installed on the Entity, "
        "and no build factory installs one. Configure enemy='baseline' (or any "
        "standardized kind, including 'none') with enemy_options={'mitigation': True} "
        "to install the band's mean-field res/imm/vuln profile "
        "(enemy_stats.band_damage_multipliers)."
    )


# ---------------------------------------------------------------------------
# MetricDef and the registry
# ---------------------------------------------------------------------------

#: §5.3's report structure, encoded rather than left to a renderer's discretion.
#: ``column`` exists so a roster/party or per-summon figure is STRUCTURALLY
#: incapable of being merged into the headline.
GROUPS = ("headline", "panel", "column")


@dataclass(frozen=True)
class MetricDef:
    """One registered metric — §5.1's declaration, plus what it takes to compute it.

    The first five fields are exactly §5.1's ``MetricDef`` (name / unit /
    denominator / source / definition); the rest are the machinery that makes the
    declaration executable instead of documentation that can drift from the code.
    """

    name: str
    unit: str
    denominator: str
    source: str
    definition: str
    numerator: Callable[[DaySample], float]
    convergence: Convergence = DEFAULT_CONVERGENCE
    availability: Callable[[RunContext], "str | None"] = _always
    group: str = "panel"
    #: Per-day count of the EVENTS this metric is estimated from, for the
    #: ``min_events`` convergence guard.  ``None`` means "the day is the event",
    #: so the guard degenerates to a day-count floor.
    events: "Callable[[DaySample], float] | None" = None
    #: §5.4: the :class:`BreakdownDef` this is one CELL of, or ``None`` for a
    #: standalone scalar.  Cells still live in the flat ``_defs`` map because the
    #: collector and the estimator treat every cell as an ordinary metric — the
    #: structure exists for the REPORT and the artifact, not for the arithmetic.
    breakdown: "str | None" = None
    #: The cell's key tuple, positionally matching its breakdown's dimensions.
    #: :data:`ALL` in a position means this cell is a declared MARGIN over that
    #: dimension.
    key: "tuple[str, ...] | None" = None
    #: §6.2 (s48): the quantity's MEASUREMENT SCALE, which selects the convergence
    #: criterion the same way ``Denominator.fixed`` selects the estimator.
    #: :data:`SCALE_RATIO` (the default, and all but one metric) has a true zero, so
    #: "the standard error is 2% of the value" is a meaningful sentence.
    #: :data:`SCALE_INTERVAL` is a SIGNED quantity whose zero is a break-even point;
    #: relative error against one is a category error, because the value can sit
    #: near zero while the estimate is perfectly precise. Declared rather than
    #: inferred from observed signs: whether a quantity CAN go negative is a fact
    #: about what it measures, not about what this run happened to produce.
    scale: str = SCALE_RATIO

    def __post_init__(self) -> None:
        if self.group not in GROUPS:
            raise ValueError(f"Metric {self.name!r}: group must be one of {GROUPS}.")
        if self.scale not in SCALES:
            raise ValueError(
                f"Metric {self.name!r}: scale must be one of {SCALES}."
            )
        if self.denominator not in DENOMINATORS:
            raise ValueError(
                f"Metric {self.name!r} declares denominator {self.denominator!r}, "
                f"which is not in the closed vocabulary: {sorted(DENOMINATORS)}."
            )

    @property
    def denominator_spec(self) -> Denominator:
        return DENOMINATORS[self.denominator]

    def event_count(self, sample: DaySample) -> float:
        return 1.0 if self.events is None else self.events(sample)

    def describe(self) -> dict[str, Any]:
        """The data-dictionary entry (§5.1's second payoff)."""
        spec = self.denominator_spec
        return {
            "name": self.name,
            "unit": self.unit,
            "denominator": spec.name,
            "denominator_description": spec.description,
            "denominator_is_constant": spec.fixed,
            "estimator": "mean" if spec.fixed else "ratio-of-means (delta method)",
            "source": self.source,
            "definition": self.definition,
            "group": self.group,
            "scale": self.scale,
            "convergence": self.convergence.describe(),
            "breakdown": self.breakdown,
            "key": list(self.key) if self.key is not None else None,
            "is_margin": self.key is not None and ALL in self.key,
        }


# ---------------------------------------------------------------------------
# BreakdownDef — the second output kind (§5.4)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Dimension:
    """One axis of a breakdown's key space: a CLOSED, named vocabulary.

    Closed for the same reason the verb set and the telemetry channels are: a zero
    in a declared cell is a real measurement ("this build deals no cold damage"),
    while a missing row is an absence of information.  The two must not look alike.
    """

    name: str
    keys: tuple[str, ...]
    description: str

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "keys": list(self.keys),
                "description": self.description}


@dataclass(frozen=True)
class KeySpace:
    """A product of :class:`Dimension`s — what a breakdown is keyed BY.

    A product rather than a single list because the real breakdowns need it: the
    saves channel is keyed ``(ability, channel)`` in the telemetry itself, and
    healing is keyed ``(source_role, context)`` because healing.md §11.1's finding
    makes those two things different quantities rather than one summed one.
    """

    dimensions: tuple[Dimension, ...]

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.dimensions)

    def cells(self) -> tuple[tuple[str, ...], ...]:
        """Every full key — the Cartesian product, margins excluded."""
        return tuple(product(*(d.keys for d in self.dimensions)))

    def marginal_cells(self) -> tuple[tuple[str, ...], ...]:
        """One key per (dimension, key) pair, with :data:`ALL` in every OTHER
        position — the dimensions reported INDEPENDENTLY rather than crossed.

        For ``(ability, channel)`` that is the six per-ability profiles plus the
        two per-channel ones: 8 keys instead of the grid's 12.  See
        :attr:`BreakdownDef.crossed` for when a grid earns its cells.
        """
        out: list[tuple[str, ...]] = []
        for position, dimension in enumerate(self.dimensions):
            for key in dimension.keys:
                out.append(tuple(key if i == position else ALL
                                 for i in range(len(self.dimensions))))
        return tuple(out)

    def index_of(self, dimension: str) -> int:
        try:
            return self.names.index(dimension)
        except ValueError:
            raise KeyError(
                f"No dimension {dimension!r} in this key space: {self.names}."
            ) from None

    def describe(self) -> dict[str, Any]:
        return {"dimensions": [d.describe() for d in self.dimensions]}


def format_key(key: tuple[str, ...]) -> str:
    """``("dex_save", "control")`` -> ``"[dex_save|control]"``.

    A cell's flat name is ``breakdown + format_key(key)``.  It is readable and
    machine-parseable, but NOTHING downstream is expected to parse it: the whole
    point of §5.4 is that the key travels as data on the cell, so a renderer never
    has to reverse-engineer ``damage_share_acid`` back into ``("acid",)``.
    """
    return "[" + "|".join(key) + "]"


@dataclass(frozen=True)
class BreakdownDef:
    """§5.4's second output kind: ONE quantity over a closed key space.

    Registering a breakdown expands it into one :class:`MetricDef` per cell (plus
    one per declared margin), so the collector, the estimator and the convergence
    guard need no new code path — every cell is estimated exactly like a scalar,
    with its own ``(value, n, stderr, converged)``.  What is new is that the REPORT
    and the artifact keep those cells grouped under this declaration, keys intact.

    ``margins`` declares which dimension SUBSETS to collapse.  A margin is a cell
    whose key holds :data:`ALL` in the collapsed positions, and it is computed here
    rather than left to a consumer because **N correlated cell estimates cannot be
    combined into the aggregate's standard error downstream** — the covariance is
    visible only at this layer (§5.4's survival rule).

    ``denominator`` is either one name shared by every cell, or a callable keyed on
    the cell's key returning a :class:`Denominator` that is registered into the
    closed vocabulary at registration time.  The callable form is what makes
    ``save_fail_rate[dex_save|control]`` divide by the dex CONTROL saves actually
    forced rather than by the family total; it absorbs the hand-written per-key
    denominator family the flat registry needed.

    ``availability`` is asked PER CELL (§3.4's honesty requirement, carried through
    the collapse): the control-channel cells can be unmeasurable while the
    damage-channel cells of the same breakdown report normally.
    """

    name: str
    unit: str
    key_space: KeySpace
    source: str
    definition: str
    numerator: Callable[[DaySample, tuple[str, ...]], float]
    denominator: "str | Callable[[tuple[str, ...]], Denominator]"
    margins: tuple[tuple[str, ...], ...] = ()
    #: Are the dimensions CROSSED (materialize the full grid) or INDEPENDENT
    #: (materialize each dimension's own marginal profile)?  A grid must earn its
    #: cells: crossing multiplies them, and a cell whose denominator is
    #: structurally near-zero is a permanently-unmeasured row that a renderer still
    #: has to lay out.  ``saves`` is uncrossed because the per-ability profile and
    #: the damage/control split are the two questions anyone asks, while "dex saves
    #: forced by CONTROL specifically" has a denominator that rarely survives.
    #: ``healing_by_source`` IS crossed, because the cross-tab is the point: a
    #: summon healing under fire is a different fact from a summon healing at
    #: leisure (healing.md §11.1).
    crossed: bool = True
    #: As :attr:`MetricDef.scale`, applied to every cell. No shipped breakdown is
    #: signed today; the field exists so a breakdown cannot be the one place the
    #: declaration silently defaults.
    scale: str = SCALE_RATIO
    #: §5.4: do the cells PARTITION their total, or do they OVERLAP?  Declared, not
    #: inferred from :attr:`crossed` (s49) — the two are independent, and
    #: ``attack_roll_rate`` is both crossed and overlapping.  There is deliberately
    #: NO default: every breakdown states it, because a wrong value here is the
    #: double-count the field exists to prevent and a default is how one gets
    #: shipped unnoticed.
    sum_rule: str = ""
    convergence: Convergence = DEFAULT_CONVERGENCE
    availability: Callable[[RunContext, tuple[str, ...]], "str | None"] = (
        lambda ctx, key: None
    )
    group: str = "panel"
    events: "Callable[[DaySample, tuple[str, ...]], float] | None" = None
    #: Set when the margins are deliberately incomplete, naming WHY.  Read by the
    #: data dictionary so a refused margin is documented rather than looking like an
    #: oversight — ``healing_by_source`` refuses to sum its contexts.
    margin_note: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUPS:
            raise ValueError(f"Breakdown {self.name!r}: group must be one of {GROUPS}.")
        if self.group == "headline":
            raise ValueError(
                f"Breakdown {self.name!r} cannot be the headline: §5.3 allows exactly "
                f"one headline and §5.4 keeps it a SCALAR, so it can never be one cell "
                f"of something larger."
            )
        # Checked AFTER the identity guards: a breakdown that cannot be a headline
        # is malformed whatever its summing rule, and the more specific error is
        # the more useful one to raise.
        if self.sum_rule not in SUM_RULES:
            raise ValueError(
                f"Breakdown {self.name!r} must declare sum_rule as one of "
                f"{SUM_RULES}; got {self.sum_rule!r}. It is not inferred from "
                f"`crossed` (s49): a crossed breakdown whose keys are not disjoint "
                f"still overlaps, and getting this wrong is exactly the "
                f"double-count the field exists to prevent."
            )
        for collapse in self.margins:
            if not collapse:
                raise ValueError(
                    f"Breakdown {self.name!r} declares an empty margin; a margin "
                    f"collapses at least one dimension."
                )
            for dimension in collapse:
                self.key_space.index_of(dimension)          # raises if unknown

    # -- key expansion ----------------------------------------------------

    def cell_keys(self) -> tuple[tuple[str, ...], ...]:
        """The keys this breakdown MATERIALIZES, margins excluded."""
        return (self.key_space.cells() if self.crossed
                else self.key_space.marginal_cells())

    def margin_keys(self) -> tuple[tuple[str, ...], ...]:
        """Every declared margin key, in declaration order, de-duplicated.

        Computed by collapsing the MATERIALIZED cells, so an uncrossed breakdown's
        margins are collapses of its marginal profiles rather than of a grid it
        never built.  A collapse that lands back on an existing cell is skipped —
        it would be the same number under two names.
        """
        cells = set(self.cell_keys())
        out: list[tuple[str, ...]] = []
        seen: set[tuple[str, ...]] = set()
        for collapse in self.margins:
            positions = {self.key_space.index_of(d) for d in collapse}
            for key in self.cell_keys():
                margin = tuple(ALL if i in positions else v
                               for i, v in enumerate(key))
                if margin not in seen and margin not in cells:
                    seen.add(margin)
                    out.append(margin)
        return tuple(out)

    def keys(self) -> tuple[tuple[str, ...], ...]:
        """Cells first, then margins — the report's assembly order."""
        return self.cell_keys() + self.margin_keys()

    def cell_name(self, key: tuple[str, ...]) -> str:
        return self.name + format_key(key)

    # -- expansion into estimable cells -----------------------------------

    def denominator_for(self, key: tuple[str, ...]) -> "str | Denominator":
        if isinstance(self.denominator, str):
            return self.denominator
        return self.denominator(key)

    def cell_definitions(self) -> "list[MetricDef]":
        """One :class:`MetricDef` per key, with the key carried as DATA."""
        out: list[MetricDef] = []
        for key in self.keys():
            denominator = self.denominator_for(key)
            if not isinstance(denominator, str):
                DENOMINATORS.setdefault(denominator.name, denominator)
                denominator = denominator.name
            out.append(MetricDef(
                name=self.cell_name(key),
                unit=self.unit,
                denominator=denominator,
                source=self.source,
                definition=self.definition,
                numerator=(lambda s, _k=key: self.numerator(s, _k)),
                convergence=self.convergence,
                availability=(lambda ctx, _k=key: self.availability(ctx, _k)),
                group=self.group,
                scale=self.scale,
                events=(None if self.events is None
                        else (lambda s, _k=key: self.events(s, _k))),
                breakdown=self.name,
                key=key,
            ))
        return out

    def describe(self) -> dict[str, Any]:
        """The data-dictionary entry for the breakdown itself (§5.1's payoff,
        extended to the second kind)."""
        return {
            "name": self.name,
            "kind": "breakdown",
            "unit": self.unit,
            "key_space": self.key_space.describe(),
            "source": self.source,
            "definition": self.definition,
            "group": self.group,
            "crossed": self.crossed,
            "sum_rule": self.sum_rule,
            "cells": [list(k) for k in self.cell_keys()],
            "margins": [list(k) for k in self.margin_keys()],
            "margin_note": self.margin_note,
            "convergence": self.convergence.describe(),
        }


# ---------------------------------------------------------------------------
# DistributionDef — the third output kind (§5.4 "Kind 3 in full", s48)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DistributionDef:
    """§5.4's third output kind: the SHAPE of a per-day quantity.

    Every other output in this registry is a mean with a standard error, which
    says where the average lands and nothing about consistency — two builds with
    identical mean DPR and very different day-to-day spread are indistinguishable
    in all of it.

    **A distribution is declared OVER a registered scalar**, never as a new
    collected quantity, and that is what made the kind cheap.  It reads the per-day
    samples :class:`~src.evaluation.statistics.MetricSamples` already keeps for
    ``over``, so the runner, the collector and both estimators are untouched — the
    same move :class:`BreakdownDef` made in s46.  Two consequences are worth
    naming:

    * **The distribution and the scalar cannot disagree.**  The mean of the per-day
      vector IS the scalar's value, to the last bit, because it is the same vector.
      A distribution with its own numerator could drift from the metric it claims
      to describe.
    * **Unavailability is inherited.**  If ``over`` is unavailable for a run, so is
      this, with the same reason — §3.4's three states need no new vocabulary.

    ``unit`` is NOT declared: :meth:`MetricRegistry.register_distribution` fills it
    from ``over``.  It is the same quantity, so a second declaration of it could
    only ever drift.

    The interval method is not a field either — each
    :class:`~src.evaluation.statistics.Statistic` carries its own, because a
    quantile has an exact closed-form interval and an IQR does not.  See that
    class for why that is a derivation rather than a knob.
    """

    name: str
    #: The registered SCALAR metric whose per-day samples this describes.  Must
    #: have a FIXED denominator — checked at registration, because a ratio metric
    #: has no per-day value to take a quantile of.
    over: str
    definition: str
    statistics: "tuple[Statistic, ...]" = DEFAULT_STATISTICS
    convergence: DistributionConvergence = DEFAULT_DISTRIBUTION_CONVERGENCE
    group: str = "panel"
    #: Resamples for the bootstrap statistics.  Ignored by the exact method.
    resamples: int = DEFAULT_RESAMPLES
    #: Filled in at registration from ``over``; never declared by hand.
    unit: str = ""

    def __post_init__(self) -> None:
        if self.group not in GROUPS:
            raise ValueError(
                f"Distribution {self.name!r}: group must be one of {GROUPS}."
            )
        if self.group == "headline":
            raise ValueError(
                f"Distribution {self.name!r} cannot be the headline: §5.3 allows "
                f"exactly one headline and §5.4 keeps it a SCALAR. A build's "
                f"headline is where its average lands; its spread is reported "
                f"beside that, never as it."
            )
        if not self.statistics:
            raise ValueError(
                f"Distribution {self.name!r} declares no statistics; an empty "
                f"distribution is a section header, not an output."
            )
        labels = [s.label for s in self.statistics]
        if len(set(labels)) != len(labels):
            raise ValueError(
                f"Distribution {self.name!r} declares a duplicate statistic: {labels}."
            )

    @property
    def key_dimensions(self) -> tuple[str, ...]:
        """The dimensions a point's key carries — ``("statistic",)`` in v1.

        A property rather than a literal at the call sites so the tidy CSV's
        column derivation is UNIFORM across the kinds: it unions every breakdown's
        key-space names with every distribution's key dimensions, which means a
        later KEYED distribution (§5.4's named deferral) adds its column the same
        way a new breakdown dimension does, rather than needing the writer edited.
        """
        return ("statistic",)

    def point_name(self, statistic: str) -> str:
        """The flat row name, matching a breakdown cell's convention."""
        return self.name + format_key((statistic,))

    def describe(self) -> dict[str, Any]:
        """The data-dictionary entry for the third kind (§5.1's payoff, extended)."""
        return {
            "name": self.name,
            "kind": "distribution",
            "over": self.over,
            "unit": self.unit,
            "definition": self.definition,
            "group": self.group,
            "statistics": [s.describe() for s in self.statistics],
            "resamples": self.resamples,
            "convergence": self.convergence.describe(),
            "interval_note": (
                "Distribution points carry an ASYMMETRIC ci95 and NO stderr: a "
                "quantile is not a ratio and has no delta-method standard error, so "
                "value +/- 1.96*stderr is not available and would not be correct if "
                "it were. The method field on each row says how the interval was "
                "placed."
            ),
            "sum_note": (
                "Points are NOT additive under any rule, which is why a distribution "
                "carries no sum_rule: quantiles of one sample do not partition "
                "anything and summing them is meaningless."
            ),
        }


class MetricRegistry:
    """The closed metric set — §5.4's two live output kinds, in one home.

    Two views of the same content, and both are load-bearing:

    * **Flat.** Iterating the registry yields every estimable :class:`MetricDef`,
      breakdown CELLS included.  The collector and the estimator work entirely off
      this view, which is why the second output kind needed no new statistics code.
    * **Structured.** :attr:`breakdowns` and :meth:`scalars` keep the cells grouped
      under their declaration with their keys intact.  This is the view §9's
      artifact serializes and a website renders — so a consumer never parses a key
      back out of a metric NAME (§5.4).

    The third kind, distributions (s48), is registered here too but estimated
    differently: a :class:`DistributionDef` expands into no cells, because it
    describes the per-day samples of a metric that is ALREADY registered.  It
    therefore never appears in the flat view — iterating the registry still yields
    exactly the things the collector must sample.
    """

    def __init__(self, definitions: "list[MetricDef] | None" = None,
                 breakdowns: "list[BreakdownDef] | None" = None,
                 distributions: "list[DistributionDef] | None" = None) -> None:
        self._defs: dict[str, MetricDef] = {}
        self._scalars: list[str] = []
        self._breakdowns: dict[str, BreakdownDef] = {}
        self._distributions: dict[str, DistributionDef] = {}
        for definition in definitions or []:
            self.register(definition)
        for breakdown in breakdowns or []:
            self.register_breakdown(breakdown)
        for distribution in distributions or []:
            self.register_distribution(distribution)

    # -- registration -----------------------------------------------------

    def register(self, definition: MetricDef) -> MetricDef:
        """Register one standalone SCALAR (§5.4 kind 1)."""
        self._add(definition)
        self._scalars.append(definition.name)
        return definition

    def register_breakdown(self, breakdown: BreakdownDef) -> BreakdownDef:
        """Register one keyed BREAKDOWN (§5.4 kind 2) and expand its cells.

        The expansion is why nothing downstream of here needed changing: each cell
        is an ordinary :class:`MetricDef` carrying its key as data, so it is
        collected, estimated and convergence-checked exactly like a scalar.
        """
        if breakdown.name in self._breakdowns:
            raise ValueError(f"Breakdown {breakdown.name!r} is already registered.")
        self._breakdowns[breakdown.name] = breakdown
        for cell in breakdown.cell_definitions():
            self._add(cell)
        return breakdown

    def register_distribution(self, distribution: DistributionDef) -> DistributionDef:
        """Register one DISTRIBUTION (§5.4 kind 3) over an already-registered scalar.

        Two refusals happen here rather than being left to the author's care, and
        both are the kind of mistake that would otherwise produce a plausible
        number:

        * **``over`` must be a registered SCALAR.**  A breakdown CELL has per-day
          samples too, but keying a distribution is deliberately out of scope for
          v1 (§5.4) — accepting a cell name here would let one in by the side door
          with no key on its rows.
        * **``over`` must have a FIXED denominator.**  With a random denominator
          there is no per-day value to take a quantile OF: a day that forced no
          saves has no fail rate, and silently dropping those days would change the
          estimand from "the rate" to "the rate among days that had one".  The
          declaration ``Denominator.fixed`` already exists for the estimator's
          sake; this is the same fact doing a second job.

        ``unit`` is filled in from ``over`` rather than declared, so the two can
        never drift apart — it is the same quantity.
        """
        if distribution.name in self._distributions:
            raise ValueError(
                f"Distribution {distribution.name!r} is already registered."
            )
        if distribution.name in self._defs:
            raise ValueError(
                f"Distribution {distribution.name!r} collides with a registered "
                f"metric of the same name."
            )
        if distribution.over not in self._defs:
            raise ValueError(
                f"Distribution {distribution.name!r} is declared over "
                f"{distribution.over!r}, which is not a registered metric. "
                f"Registered scalars: {self._scalars}."
            )
        over = self._defs[distribution.over]
        if over.breakdown is not None:
            raise ValueError(
                f"Distribution {distribution.name!r} is declared over "
                f"{distribution.over!r}, which is a CELL of breakdown "
                f"{over.breakdown!r}. §5.4 keeps distributions 1-D in v1: a "
                f"distribution over a cell is a KEYED distribution, and its rows "
                f"would carry no key to say which cell they describe."
            )
        if not over.denominator_spec.fixed:
            raise ValueError(
                f"Distribution {distribution.name!r} is declared over "
                f"{distribution.over!r}, whose denominator "
                f"{over.denominator!r} is RANDOM. There is no per-day value to take "
                f"a quantile of: on a day whose denominator is zero the ratio is "
                f"undefined, not zero, so the sample a quantile would read does not "
                f"exist. Distributions are defined over fixed-denominator metrics "
                f"only (§5.4)."
            )
        resolved = replace(distribution, unit=over.unit)
        self._distributions[resolved.name] = resolved
        return resolved

    def _add(self, definition: MetricDef) -> None:
        if definition.name in self._defs:
            raise ValueError(f"Metric {definition.name!r} is already registered.")
        self._defs[definition.name] = definition

    # -- flat view (what the collector and the estimator use) -------------

    def __contains__(self, name: object) -> bool:
        return name in self._defs

    def __getitem__(self, name: str) -> MetricDef:
        try:
            return self._defs[name]
        except KeyError:
            raise KeyError(
                f"No metric registered as {name!r}. Registered: {self.names()}."
            ) from None

    def __iter__(self) -> Iterator[MetricDef]:
        """Every estimable metric, breakdown cells included."""
        return iter(self._defs.values())

    def __len__(self) -> int:
        return len(self._defs)

    def names(self) -> list[str]:
        return list(self._defs)

    def cell(self, breakdown: str, key: tuple[str, ...]) -> MetricDef:
        """One cell of a breakdown, addressed by key rather than by flat name."""
        return self[self.breakdown(breakdown).cell_name(key)]

    # -- structured view (what the report and the artifact use) -----------

    def scalars(self) -> list[MetricDef]:
        """Standalone scalars only — no breakdown cells (§5.4 kind 1)."""
        return [self._defs[n] for n in self._scalars]

    @property
    def breakdowns(self) -> list[BreakdownDef]:
        return list(self._breakdowns.values())

    def breakdown(self, name: str) -> BreakdownDef:
        try:
            return self._breakdowns[name]
        except KeyError:
            raise KeyError(
                f"No breakdown registered as {name!r}. "
                f"Registered: {list(self._breakdowns)}."
            ) from None

    def distributions(self) -> list[DistributionDef]:
        """§5.4's third kind (s48).

        s46 named the kind and reserved its place in the artifact; s47 built the
        reservation; s48 filled it — at ``schema_version`` 1, which is what the
        reservation was for.  The method kept its name and its place through all
        three, so the contract a consumer reads never moved.
        """
        return list(self._distributions.values())

    def distribution(self, name: str) -> DistributionDef:
        try:
            return self._distributions[name]
        except KeyError:
            raise KeyError(
                f"No distribution registered as {name!r}. "
                f"Registered: {list(self._distributions)}."
            ) from None

    def distributions_in_group(self, group: str) -> list[DistributionDef]:
        if group not in GROUPS:
            raise KeyError(f"Unknown metric group {group!r}; expected {GROUPS}.")
        return [d for d in self._distributions.values() if d.group == group]

    # -- grouping (§5.3) --------------------------------------------------

    def group(self, group: str) -> list[MetricDef]:
        """Standalone scalars in one §5.3 group.

        Scalars ONLY: a breakdown belongs to a group as a whole, and returning its
        cells here would flatten exactly the structure §5.4 exists to preserve.
        Use :meth:`breakdowns_in_group` for the other kind.
        """
        if group not in GROUPS:
            raise KeyError(f"Unknown metric group {group!r}; expected {GROUPS}.")
        return [d for d in self.scalars() if d.group == group]

    def breakdowns_in_group(self, group: str) -> list[BreakdownDef]:
        if group not in GROUPS:
            raise KeyError(f"Unknown metric group {group!r}; expected {GROUPS}.")
        return [b for b in self._breakdowns.values() if b.group == group]

    @property
    def headline(self) -> MetricDef:
        """The single headline metric (§5.3): character-column DPR.

        Raises if the registry declares anything but exactly one, because "no
        composite build score" (§5.3) only means something if the headline stays a
        single declared quantity rather than drifting into a basket.  §5.4 adds the
        other half of the guard: :class:`BreakdownDef` REFUSES the headline group,
        so the headline can never become one cell of something larger.
        """
        heads = self.group("headline")
        if len(heads) != 1:
            raise ValueError(
                f"Expected exactly one headline metric, found {[d.name for d in heads]}."
            )
        return heads[0]

    # -- the data dictionary (§5.1's second payoff) -----------------------

    def data_dictionary(self) -> dict[str, list[dict[str, Any]]]:
        """Every declaration, by output kind — §5.1's "the registry IS the data
        dictionary", extended to §5.4's kinds.

        Note what the s46 review optimized, and what it did not: the number of
        DECLARATIONS a human maintains fell from 51 to 22, while the number of
        ESTIMATED CELLS rose from 51 to 66.  That is the honest trade — the
        declarations carry the maintenance and interpretation cost, the cells are
        just numbers.  A first draft crossed the saves dimensions and reached 90
        cells; that grid was judged not to earn them, which is what
        ``BreakdownDef.crossed`` exists to express.
        """
        return {
            "scalars": [d.describe() for d in self.scalars()],
            "breakdowns": [b.describe() for b in self._breakdowns.values()],
            "distributions": [d.describe() for d in self._distributions.values()],
        }


# ---------------------------------------------------------------------------
# Key spaces — the closed vocabularies the breakdowns are keyed by (§5.4)
# ---------------------------------------------------------------------------

ABILITY = Dimension(
    name="ability",
    keys=SAVE_STATS,
    description=(
        "The engine's saving-throw stat vocabulary (resolve_saving_throw's "
        "save_stat). Complete rather than whatever happened to fire, so a zero cell "
        "means 'no save of this kind was forced' rather than 'not recorded'."
    ),
)
SAVE_CHANNEL = Dimension(
    name="channel",
    keys=SAVE_CHANNELS,
    description=(
        "§13 / enemy_model.md §4b's two independent pressure channels: a save "
        "against a DAMAGING effect and a save against a CONTROL effect. The "
        "telemetry is keyed (ability, channel) at the source, which is why this is "
        "a second dimension rather than three separate metrics."
    ),
)
DAMAGE_TYPE = Dimension(
    name="damage_type",
    keys=DAMAGE_TYPES,
    description=(
        "The engine's damage-type vocabulary (mirrors enemy_stats._DAMAGE_TYPES, "
        "the 13 types the frozen band table prices)."
    ),
)
ROLE = Dimension(
    name="role",
    keys=ATTRIBUTABLE_ROLES,
    description=(
        "Roster role. Enemies are absent by construction: no metric here describes "
        "the enemy's own column."
    ),
)
SOURCE_ROLE = Dimension(
    name="source_role",
    keys=ATTRIBUTABLE_ROLES,
    description="Roster role of the entity that PROVIDED the healing.",
)
HEAL_CONTEXT = Dimension(
    name="context",
    keys=HEAL_CONTEXTS,
    description=(
        "Healing resolved INSIDE a combat vs applied in a between-combat interval. "
        "healing.md §11.1 found the corpus does most of its healing out of combat "
        "by preference, so these are two different quantities — which is why no "
        "margin over this dimension is declared."
    ),
)
COMBAT = Dimension(
    name="combat",
    keys=("1", "2", "3", "4"),
    description=(
        "Which of the day's four combats. Fixed at four because RunConfig validates "
        "combats_per_day == 4; the day's SHAPE is the point, so this is a vector "
        "rather than four unrelated scalars."
    ),
)


ATTACK_PROPERTY = Dimension(
    name="property",
    keys=ATTACK_PROPERTIES,
    description=(
        "A property of ONE attack roll (§8.1): did it land (hit), was it a natural "
        "20 that landed (crit), and was it rolled at advantage. NOT a partition — a "
        "crit is also a hit, and advantage is a condition of the roll rather than an "
        "outcome of it — which is why the breakdown over this dimension declares "
        "sum_rule=cells_overlap_do_not_sum and refuses a margin. disadvantage is "
        "recorded in the channel but absent here: no shipped build imposes "
        "disadvantage on its OWN attacks, so the cells would be a column of zeros."
    ),
)


def _opt(key: str) -> "str | None":
    """A key position as a FILTER: :data:`ALL` becomes "no filter".

    This one line is what lets a single numerator serve both a breakdown's cells
    and its declared margins (§5.4).
    """
    return None if key == ALL else key


def _role_cell_availability(position: int) -> Callable[[RunContext, tuple[str, ...]], "str | None"]:
    """Per-cell availability for a role-keyed dimension: a build with no summons
    reports its ``summons`` cell as unavailable-with-a-reason, while the rest of
    the breakdown reports normally.  Margins are always available."""
    def check(ctx: RunContext, key: tuple[str, ...]) -> "str | None":
        role = key[position]
        return None if role == ALL else _requires_role(role)(ctx)
    return check


def _saves_cell_availability(ctx: RunContext, key: tuple[str, ...]) -> "str | None":
    """The control CHANNEL is unmeasurable in every run today (§3.4); the damage
    channel is not.  Per-cell availability is what keeps both facts in one
    breakdown instead of forcing the family back apart into flat rows."""
    return _requires_control_channel(ctx) if key[1] == "control" else None



def _saves_forced_denominator(key: tuple[str, ...]) -> Denominator:
    """The per-cell random denominator: saves of THIS ability in THIS channel."""
    ability, channel = key
    return Denominator(
        name="saves_forced" + format_key(key),
        description=(
            f"Saving throws actually forced with ability="
            f"{'any' if ability == ALL else ability} and channel="
            f"{'any' if channel == ALL else channel} (§13 saves channel). Random and "
            f"correlated with the numerator, so rates over it use the ratio-of-means "
            f"estimator. Has NO value on a run that forces none — reported as "
            f"unmeasured, never as zero."
        ),
        fixed=False,
        per_day=(lambda s, _a=_opt(ability), _c=_opt(channel):
                 s.saves(stat=_a, channel=_c)),
    )


def _attacks_made_denominator(key: tuple[str, ...]) -> Denominator:
    """The per-cell random denominator for ``attack_roll_rate``: attack rolls made
    by THIS ROLE (§8.1).

    Keyed on the role ALONE and not on the property — all three property cells of a
    role divide by the same roll count, which is the arithmetic statement of the
    cells overlapping.  Registration de-duplicates by name, so the three cells
    genuinely share one denominator entry rather than three identical ones.
    """
    role = key[0]
    return Denominator(
        name="attacks_made" + format_key((role,)),
        description=(
            f"Attack rolls actually made by roster role "
            f"{'any attributable' if role == ALL else role} (§13 attacks channel). "
            f"Random and correlated with the numerator, so rates over it use the "
            f"ratio-of-means estimator. A role that made none has NO rate — "
            f"reported as unmeasured, never as zero, because a build whose summon "
            f"never swings has not got a 0% hit rate."
        ),
        fixed=False,
        per_day=(lambda s, _r=role:
                 s.attacks("forced", roles=(None if _r == ALL else (_r,)))),
    )


def _requires_healable_other(ctx: RunContext) -> "str | None":
    """Is there anyone this build could even heal that is not itself?"""
    others = tuple(r for r in ATTRIBUTABLE_ROLES if r not in ctx.config.own_roles)
    if any(getattr(ctx.roster, role) for role in others):
        return None
    return (
        "this roster holds no healable entity outside the attributed roles — "
        "enemies are never healed (healing.md §5), and nothing else is present. A "
        "zero here would report ROSTER POVERTY as a build property: War Angel's "
        "Prayer of Healing heals five creatures RAW and heals one in this model "
        "only because the roster has one. Goes live with §3.3's multi-character "
        "party."
    )


# ---------------------------------------------------------------------------
# The shipped registry (§5.3's headline / panel / columns, in §5.4's two kinds)
# ---------------------------------------------------------------------------

def _build_default_registry() -> MetricRegistry:
    registry = MetricRegistry()
    reg = registry.register
    breakdown = registry.register_breakdown
    distribution = registry.register_distribution

    # == SCALARS (§5.4 kind 1) ==========================================

    # -- headline (§5.3): the character column, alone --------------------
    reg(MetricDef(
        name="dpr",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — DayResult.damage_by_source, the attributed roles",
        definition=(
            "Damage dealt by what this run attributes to the build, per round of "
            "the standardized day. WHICH roles that is depends on "
            "RunConfig.attribution: 'character' (the default and historical basis) "
            "or 'character_and_summons'. Allies are excluded under both — an ally "
            "is a party member the build does not command. The mode is recorded in "
            "provenance and reports under different modes must not be compared. "
            "Stays a SCALAR under §5.4 even though dpr_by_role carries the same "
            "quantity per role: §5.3 allows exactly one headline, and a headline "
            "that is one cell of a larger object is not a headline."
        ),
        numerator=lambda s: s.own_damage(),
        group="headline",
    ))

    # -- panel: concentration (§13 economy channel) -----------------------
    reg(MetricDef(
        name="concentration_checks_per_day",
        unit="checks/day",
        denominator="days",
        source="§13 economy channel — concentration_checks",
        definition=(
            "Concentration checks forced by incoming damage, per adventuring day."
        ),
        numerator=lambda s: float(s.telemetry.concentration_checks),
    ))
    reg(MetricDef(
        name="concentration_break_rate",
        unit="fraction",
        denominator="concentration_checks",
        source="§13 economy channel — breaks / checks",
        definition=(
            "Share of concentration checks that broke the spell. A RARE-EVENT "
            "metric: it needs far more days than DPR before it is worth reading, "
            "which is why its convergence heuristic carries an event floor."
        ),
        numerator=lambda s: float(s.telemetry.concentration_breaks),
        events=lambda s: float(s.telemetry.concentration_checks),
        convergence=RARE_EVENT_CONVERGENCE,
    ))
    reg(MetricDef(
        name="concentration_breaks_per_day",
        unit="breaks/day",
        denominator="days",
        source="§13 economy channel — concentration_breaks",
        definition=(
            "Concentration losses per adventuring day. KEPT in the s46 prune "
            "although it equals checks_per_day × break_rate exactly in VALUE: its "
            "standard error is not reconstructible from those two downstream (that "
            "needs their covariance), and for a rare event the uncertainty is most "
            "of what the number is worth. This is §5.4's survival rule."
        ),
        numerator=lambda s: float(s.telemetry.concentration_breaks),
        events=lambda s: float(s.telemetry.concentration_breaks),
        convergence=RARE_EVENT_CONVERGENCE,
    ))

    # -- panel: control resilience — UNAVAILABLE in every run today (§3.4) -
    reg(MetricDef(
        name="control_turns_lost_per_round",
        unit="turns/round",
        denominator="rounds",
        source="§13 control channel — ControlTally.turns_lost (HARD branch)",
        definition=(
            "Expected turns fully lost to control, per round — the closed-form "
            "duration from enemy_model.md §6 step 5."
        ),
        numerator=lambda s: s.control("turns_lost"),
        events=lambda s: s.control("failures"),
        availability=_requires_control_channel,
        convergence=RARE_EVENT_CONVERGENCE,
    ))
    reg(MetricDef(
        name="control_turns_reduced_per_round",
        unit="turns/round",
        denominator="rounds",
        source="§13 control channel — ControlTally.turns_reduced (SOFT branch)",
        definition=(
            "Expected turns at reduced output (scaled by soft_factor), per round."
        ),
        numerator=lambda s: s.control("turns_reduced"),
        events=lambda s: s.control("failures"),
        availability=_requires_control_channel,
        convergence=RARE_EVENT_CONVERGENCE,
    ))
    # The REALIZED pair was registered here in s51 and REMOVED in the same session
    # (user), once the credit was made exact.  The rows existed because the credited
    # and realized halves could not agree; §7.6's cap now counts the target's own
    # remaining TURNS net of what it already owes, so they are EQUAL by construction
    # and a second pair of rows would publish one quantity twice — which is the s46
    # survival rule's "derivable and nobody reads it" cut.  The realized half stays in
    # the §13 channel: it is what PROVES the equality (asserted in
    # tests/test_eval_control_runtime.py), and it carries `suppressed_turns`, the count
    # of whole turns skipped, which the credited half cannot express.

    # -- panel: typed mitigation — UNAVAILABLE without a mult(t) profile ---
    reg(MetricDef(
        name="damage_mitigated_per_round",
        unit="damage/round",
        denominator="rounds",
        source="§13 mitigation channel — outgoing_before − outgoing_after",
        definition=(
            "Outgoing damage absorbed by the enemy's fractional resistance profile "
            "(§5 mult(t)), per round — the cost of a build's damage-type choice."
        ),
        numerator=lambda s: s.mitigation("outgoing_before") - s.mitigation("outgoing_after"),
        availability=_requires_mitigation_profile,
    ))
    reg(MetricDef(
        name="mitigation_fraction",
        unit="fraction",
        denominator="outgoing_damage_pre_mitigation",
        source="§13 mitigation channel — 1 − after/before",
        definition=(
            "Share of the build's raw typed output the enemy's resistances remove."
        ),
        numerator=lambda s: s.mitigation("outgoing_before") - s.mitigation("outgoing_after"),
        availability=_requires_mitigation_profile,
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
        events=lambda s: s.mitigation("outgoing_before"),
    ))

    # -- panel: limited resources (§13 economy channel, live since s44) ----
    reg(MetricDef(
        name="limited_resources_per_day",
        unit="uses/day",
        denominator="days",
        source="§13 economy channel — resources_spent, summed over resource names",
        definition=(
            "Limited-resource expenditures per adventuring day (spell slots, "
            "Channel Divinity, superiority dice, …), summed across the roster. "
            "Turn-level action economy is NOT in here: action / bonus_action / "
            "reaction are scheduler state, not ResourcePool entries."
        ),
        numerator=lambda s: float(sum(s.telemetry.resources_spent.values())),
    ))
    reg(MetricDef(
        name="spell_slots_per_day",
        unit="slots/day",
        denominator="days",
        source="§13 economy channel — resources_spent, slot-shaped keys",
        definition=(
            "Spell slots of any level expended per adventuring day — the single "
            "resource almost every build in the corpus draws on, split out so it is "
            "not buried in the all-resources total. Counts 'spell_slot_1'..'_9' AND "
            "'pact_magic_slot': the War Angel spends the latter, so keying on the "
            "prefix alone would report a warlock-chassis build as casting nothing."
        ),
        numerator=lambda s: float(sum(
            v for k, v in s.telemetry.resources_spent.items()
            if k.startswith("spell_slot_") or k == "pact_magic_slot"
        )),
    ))

    # -- panel: attack volume (§13 attacks channel, live since s49) --------
    reg(MetricDef(
        name="attacks_per_round",
        unit="attacks/round",
        denominator="rounds",
        source="§13 attacks channel — AttackTally.forced, the attributed roles",
        definition=(
            "Attack rolls made per round by what this run attributes to the build "
            "(§8.1) — the action-economy figure: Extra Attack, a bonus-action "
            "swing, a summon's multiattack. A COUNT, so unlike the rates beside it "
            "this one pools legitimately across the attributed roles: swings add. "
            "It is also what makes a hit rate interpretable, because a build can "
            "trade accuracy for volume and the two numbers only mean something "
            "together. Save-for-damage output is NOT in here: an attack roll is an "
            "attack roll, and a build that forces saves instead reads low on this "
            "metric and high on saves_forced_per_round."
        ),
        numerator=lambda s: s.attacks("forced"),
    ))

    # -- panel: how much of the build's output is even TYPED --------------
    reg(MetricDef(
        name="typed_damage_share",
        unit="fraction",
        denominator="own_damage_dealt",
        source="§13 mitigation channel / damage ledger",
        definition=(
            "Share of the ATTRIBUTED column that carries a declared damage type. "
            "Reads 0 for a build whose damage is untyped in the model — which is "
            "worth knowing BEFORE reading any cell of the damage_share breakdown, "
            "and also means the §5 resistance multiplier can never touch that "
            "build's output. The meaningful aggregate of the composition family: "
            "damage_share's own total is 1.0 by construction, which is why that "
            "breakdown declares no margin. "
            "Reads outgoing_AFTER, not outgoing_before, and the asymmetry with "
            "damage_share (which reads before/before) is deliberate: this row's "
            "DENOMINATOR is the damage ledger, which records what actually landed, "
            "i.e. POST-mitigation. Mixing the two sides of mult(t) would make this "
            "a before/after ratio rather than a share — see the s50 note below."
        ),
        # s50 BUGFIX, found by rendering one real output (per-feature ritual step 6).
        # This numerator was `outgoing_before` for six sessions and was invisible for
        # a precise reason: no entity carried a `damage_multiplier`, so
        # `outgoing_before == outgoing_after` identically and the row was a correct
        # share by accident. The §13 step-5 enemy seam installs the first real
        # profile (enemy_options={'mitigation': True}), and the row immediately
        # printed **1.1054** — a "fraction" above 1 — because the numerator was
        # pre-mitigation typed damage over a post-mitigation denominator.
        #
        # The diagnosis is arithmetic rather than a reading of the code: on
        # Silvertail L10, where every point of the master's damage is typed,
        # `typed_damage_share == 1 / (1 - mitigation_fraction)` to the last bit
        # (1.1053677932405566 both ways). That identity holds only for before/after.
        #
        # Note which rows were NOT wrong, because the distinction is the lesson:
        # `damage_share` divides outgoing_before by outgoing_before summed over
        # types, so its cells still partition to 1.0, and `mitigation_fraction` is
        # (before - after)/before by definition. Only the row that crossed the
        # mitigation channel WITH the damage ledger could mix the two sides.
        numerator=lambda s: s.mitigation("outgoing_after"),
        events=lambda s: s.own_damage(),
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
    ))

    # -- panel: healing (design/healing.md §8) ----------------------------
    # The FIRST customer of §5.4's output kinds, and the test of whether they
    # work.  Per the per-METRIC ritual, each names WHOSE quantity it is — and the
    # answer is deliberately not the same for all three (healing.md §8): the two
    # DEFENSIVE scalars are character-scoped, mirroring damage_taken_per_round's
    # rule, while the OUTPUT scalar follows RunConfig.attribution.
    reg(MetricDef(
        name="net_damage_taken_per_round",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger (role 'characters') − §13 healing channel (targets)",
        definition=(
            "Damage the build's CHARACTERS absorb minus the healing they receive "
            "from any source, per round — the defensive headline. **MAY BE "
            "NEGATIVE**, and a negative value is not an error: it is surplus "
            "healing capacity, the quantity healing.md §2 exists to measure. "
            "CHARACTER-scoped, not attribution-scoped: a summon self-healing is "
            "reported in its own healing_by_source cell, not as a discount on the "
            "character's cost."
        ),
        numerator=lambda s: (s.taken("characters")
                             - s.healing(target_roles=("characters",))),
        # The ONLY interval-scale metric in the registry (s48). Its zero is a
        # break-even point, not an absence, so se/|value| is not a precision
        # statement about it — a build healing almost exactly what it takes would
        # report an arbitrarily bad verdict for an arbitrarily good estimate.
        # Convergence asks instead whether the SIGN is resolved.
        scale=SCALE_INTERVAL,
    ))
    reg(MetricDef(
        name="external_healing_required_per_day",
        unit="hp/day",
        denominator="days",
        source="damage ledger (role 'characters') − §13 healing channel (self-healing)",
        definition=(
            "max(0, character damage taken − character SELF-healing) per day, where "
            "self-healing means source AND target are both characters. Literally "
            "the hit points a party healer would have to supply — the sharpest "
            "expression of healing.md §2. The CLAMP IS PER DAY, so this is the mean "
            "of the clamped quantity and NOT the clamp of the mean: a consumer "
            "deriving it from damage_taken and healing means gets a different "
            "number. CHARACTER-scoped."
        ),
        numerator=lambda s: max(0.0, s.taken("characters") - s.healing(
            source_roles=("characters",), target_roles=("characters",))),
    ))
    reg(MetricDef(
        name="healing_provided_to_others_per_day",
        unit="hp/day",
        denominator="days",
        source="§13 healing channel — source in own_roles, target outside them",
        definition=(
            "Hit points this build restores to entities it does NOT attribute to "
            "itself, per day — output that saves the party's healing budget. Zero "
            "for a selfish build, large for a healer. Follows RunConfig.attribution "
            "(evaluation_framework.md §14 point 3), so a healer-SUMMON's output "
            "counts as the build's under 'character_and_summons' and stops counting "
            "as 'to others' at the same time. Enemies are never healed "
            "(healing.md §5), so they are not in the target set."
        ),
        numerator=lambda s: s.healing(source_roles=s.own_roles,
                                      target_roles=s.other_roles()),
        availability=_requires_healable_other,
    ))

    # -- column: front-loading (§5.3, party-scoped and labelled so) --------
    reg(MetricDef(
        name="party_dpr_opening_round",
        unit="damage/round",
        denominator="opening_rounds",
        source="damage ledger — CombatResult.damage_received[enemy], round 1 of each combat",
        definition=(
            "Damage the enemy took in the FIRST round of each combat, per opening "
            "round — the front-loading figure (nova openers, pre-cast buffs, "
            "first-round riders). PARTY-scoped: the per-round log is keyed by "
            "target only, so this is comparable to dpr_by_role[*], not to the "
            "headline."
        ),
        numerator=lambda s: s.opening_round_damage(),
        group="column",
    ))

    # == BREAKDOWNS (§5.4 kind 2) =======================================

    # -- the damage columns, keyed by role (§5.3's "beside, never merged") --
    breakdown(BreakdownDef(
        name="dpr_by_role",
        unit="damage/round",
        key_space=KeySpace((ROLE,)),
        source="damage ledger — DayResult.damage_by_source, by roster role",
        definition=(
            "Damage dealt per round, by who dealt it. The [*] margin is the ROSTER "
            "TOTAL — reported beside the headline and never merged into it, because "
            "merging would make a build's headline silently change meaning the "
            "moment it gains a summon."
        ),
        numerator=lambda s, key: (s.dealt(*ATTRIBUTABLE_ROLES) if key[0] == ALL
                                  else s.dealt(key[0])),
        denominator="rounds",
        sum_rule=SUM_RULE_PARTITION,  # the roles are disjoint; the [*] margin is their sum
        margins=(("role",),),
        availability=_role_cell_availability(0),
        group="column",
    ))

    # -- defense, keyed by role -------------------------------------------
    breakdown(BreakdownDef(
        name="damage_taken_per_round_by_role",
        unit="damage/round",
        key_space=KeySpace((ROLE,)),
        source="damage ledger — DayResult.damage_received_by, by roster role",
        definition=(
            "Damage absorbed per round, by who absorbed it. Deliberately NOT "
            "attribution-dependent: a summon soaking hits is a benefit shown in its "
            "own cell, not a cost folded into the character's. The summons cell is "
            "the defensive half of a summon's contribution, which the DPR side "
            "alone does not show."
        ),
        numerator=lambda s, key: (s.taken(*ATTRIBUTABLE_ROLES) if key[0] == ALL
                                  else s.taken(key[0])),
        denominator="rounds",
        sum_rule=SUM_RULE_PARTITION,  # disjoint roles again
        margins=(("role",),),
        availability=_role_cell_availability(0),
    ))

    # -- saves: ONE quantity over (ability × channel), twice ---------------
    # The telemetry is keyed (ability, channel) at the source, so the flat
    # registry's 16 rows were two margins of one grid.  Both margins are declared
    # here rather than left to a consumer: save_fail_rate[*|control] is the old
    # control_save_fail_rate, and its stderr cannot be rebuilt from the cells.
    breakdown(BreakdownDef(
        name="saves_forced_per_round",
        unit="saves/round",
        key_space=KeySpace((ABILITY, SAVE_CHANNEL)),
        source="§13 saves channel — SaveTally.forced, by (ability, channel)",
        definition=(
            "Saving throws forced per round, either direction (the build forcing "
            "them and the enemy forcing them both land in this channel). The "
            "[ability|*] is the per-ability exposure and [*|channel] splits damaging "
            "pressure from control pressure; the [*|*] margin is the total. "
            "UNCROSSED (§5.4): the grid's 'dex saves forced by control specifically' "
            "cells were dropped in the s46 review — they multiply the cell count and "
            "their denominators rarely survive."
        ),
        numerator=lambda s, key: s.saves(stat=_opt(key[0]), channel=_opt(key[1])),
        denominator="rounds",
        sum_rule=SUM_RULE_OVERLAP,  # UNCROSSED: each dimension covers the whole quantity
        margins=(("ability", "channel"),),
        crossed=False,
        availability=_saves_cell_availability,
    ))
    breakdown(BreakdownDef(
        name="save_fail_rate",
        unit="fraction",
        key_space=KeySpace((ABILITY, SAVE_CHANNEL)),
        source="§13 saves channel — SaveTally.failed / .forced, by (ability, channel)",
        definition=(
            "Share of forced saves that failed — the build's defensive profile "
            "against each kind of pressure. A ratio over a RANDOM per-cell "
            "denominator: each save weighs equally, not each day. [*|control] is "
            "control resilience; [ability|*] is the per-ability weakness. UNCROSSED "
            "(§5.4): the crossed grid's cells (a specific ability in a specific "
            "channel) were dropped in the s46 review — their per-cell denominators "
            "are structurally near-zero, so they would be permanently-unmeasured "
            "rows a renderer still has to lay out. A cell with no forced saves is "
            "still reported as unmeasured rather than as a zero."
        ),
        numerator=lambda s, key: s.saves(stat=_opt(key[0]), channel=_opt(key[1]),
                                         outcome="failed"),
        denominator=_saves_forced_denominator,
        sum_rule=SUM_RULE_OVERLAP,  # UNCROSSED, as above
        margins=(("ability", "channel"),),
        crossed=False,
        events=lambda s, key: s.saves(stat=_opt(key[0]), channel=_opt(key[1])),
        availability=_saves_cell_availability,
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
    ))

    # -- outgoing damage-type composition ---------------------------------
    breakdown(BreakdownDef(
        name="damage_share",
        unit="fraction",
        key_space=KeySpace((DAMAGE_TYPE,)),
        source="§13 mitigation channel — outgoing_before, by damage type",
        definition=(
            "Share of the build's TYPED output dealt as each damage type. A zero is "
            "a real measurement, and the closed type vocabulary makes the "
            "composition complete rather than partial. Shares are of TYPED output, "
            "not of dpr — untyped damage declares no type to attribute, which is "
            "what typed_damage_share reports separately."
        ),
        numerator=lambda s, key: s.mitigation("outgoing_before", damage_type=key[0]),
        denominator="outgoing_typed_damage",
        sum_rule=SUM_RULE_PARTITION,  # the 13 types are disjoint and the shares sum to 1
        events=lambda s, key: s.mitigation("outgoing_before", damage_type=key[0]),
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
        margin_note=(
            "NO margin is declared: the total is 1.0 by construction, so a margin "
            "row would be a fabricated number. typed_damage_share is the meaningful "
            "aggregate and is a separate scalar over a different denominator."
        ),
    ))

    # -- the shape of the day ---------------------------------------------
    breakdown(BreakdownDef(
        name="dpr_by_combat",
        unit="damage/round",
        key_space=KeySpace((COMBAT,)),
        source="damage ledger — per-(source,target), per combat, attributed roles",
        definition=(
            "DPR within each combat of the day, on the SAME per-round basis as the "
            "headline rather than a quarter of it. The 1-vs-4 gap is the "
            "resource-depletion curve: a build that front-loads its day looks "
            "identical to a sustained one at the day level. Follows the attribution "
            "axis, so it can never disagree with the headline about whose damage it "
            "describes. No margin: the day-level aggregate IS dpr."
        ),
        numerator=lambda s, key: s.combat_damage(int(key[0])),
        denominator="combat_rounds",
        sum_rule=SUM_RULE_PARTITION,  # the four combats are disjoint slices of the day
        margin_note="No margin: the day-level aggregate is the dpr scalar itself.",
    ))

    # -- healing, keyed (source_role × context) — healing.md §8 ------------
    breakdown(BreakdownDef(
        name="healing_by_source",
        unit="hp/day",
        key_space=KeySpace((SOURCE_ROLE, HEAL_CONTEXT)),
        source="§13 healing channel — HealingTally.healed, by (source role, context)",
        definition=(
            "Hit points restored per day, by WHO restored them and WHETHER it "
            "happened under fire. Source attribution is not optional: 'healing "
            "provided by the summon' is a stated requirement, and an aggregate "
            "counter cannot answer it. The [*|context] margin gives the per-context "
            "party total."
        ),
        numerator=lambda s, key: s.healing(
            source_roles=(None if key[0] == ALL else (key[0],)),
            context=_opt(key[1]),
        ),
        denominator="days",
        margins=(("source_role",),),
        availability=_role_cell_availability(0),
        sum_rule=SUM_RULE_PARTITION,  # (source_role x context) cells are disjoint events
        margin_note=(
            "NO margin over 'context' — deliberately, and this is the rule the "
            "shape enforces. healing.md §11.1 found the corpus does most of its "
            "healing OUT of combat by preference, so healing under fire is a "
            "different quantity from healing at leisure. Refusing the margin means "
            "no cell in the artifact ever sums them; a comment could be ignored, a "
            "missing cell cannot."
        ),
    ))

    # -- attack rolls, keyed (role × property) — §8.1 ----------------------
    # The registry's first CROSSED and NON-ADDITIVE breakdown, which is what turned
    # sum_rule from an inference into a declaration (s49).
    breakdown(BreakdownDef(
        name="attack_roll_rate",
        unit="fraction",
        key_space=KeySpace((ROLE, ATTACK_PROPERTY)),
        source="§13 attacks channel — AttackTally, by (actor role, property)",
        definition=(
            "Share of this ROLE's attack rolls carrying each property — §8's hit %, "
            "crit % and advantage %, read off the role whose rolls they describe. "
            "Keyed by role because a rate cannot pool: one number over the "
            "character's swings and a summon's is a roll-weighted average of two "
            "different to-hit profiles and describes neither (contrast "
            "attacks_per_round, a count, which pools fine). Recorded at the FINAL "
            "outcome, so a Guided-Strike rescue counts as a hit and a parried hit "
            "counts as a miss — which is what stops this ledger from ever "
            "disagreeing with the damage ledger."
        ),
        numerator=lambda s, key: s.attacks(key[1], roles=(key[0],)),
        denominator=_attacks_made_denominator,
        # CROSSED — the cross is the question ("how often does the SUMMON crit")...
        crossed=True,
        # ...and OVERLAPPING all the same, because the keys are not disjoint.
        sum_rule=SUM_RULE_OVERLAP,
        events=lambda s, key: s.attacks("forced", roles=(key[0],)),
        availability=_role_cell_availability(0),
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
        margin_note=(
            "NO margin over 'role' (it would pool to-hit profiles) and none over "
            "'property' (its cells overlap). The meaningful total is attack rolls "
            "made, reported as the scalar attacks_per_round."
        ),
    ))

    # == DISTRIBUTIONS (§5.4 kind 3) ====================================

    # Two, deliberately (user, s48). Each is declared over a scalar that is already
    # registered above, so neither adds a sample column, an estimator path or a
    # line of collection — the whole kind is a second READING of material the run
    # already produced.
    #
    # Considered and not taken: external_healing_required_per_day (heavily tied at
    # zero for most builds, so most of its quantiles would be an honest but
    # uninformative 0) and party_dpr_opening_round (party-scoped, so its spread is
    # not comparable to the headline's anyway). Both are one declaration away if a
    # reader turns up for them.
    distribution(DistributionDef(
        name="dpr_distribution",
        over="dpr",
        definition=(
            "The day-to-day SHAPE of the headline. Two builds with the same mean "
            "DPR and very different spread are the same number in every other row "
            "of this report, and they are not the same build: one wins the day it "
            "rolls well, the other wins every day. p10 is the bad-day floor, the "
            "quartiles bound a typical day, and the IQR is the single number that "
            "separates a swingy build from a steady one. Describes exactly the "
            "sample the dpr scalar averages, so its mean IS that scalar."
        ),
    ))
    distribution(DistributionDef(
        name="attacks_per_round_distribution",
        over="attacks_per_round",
        definition=(
            "The day-to-day SHAPE of the build's action economy. DECLINED in s49 and "
            "again in s50 for a measured reason — every turn acted, so the quantity "
            "was a CONSTANT (2.68750 with a standard error of exactly 0 on War Angel "
            "L13 under every enemy kind, control included). §7's whole-turn "
            "suppression is the first thing in the model that stops a turn from "
            "happening, so it varies for the first time, and the shape is the "
            "question control exists to ask: a mean of 2.4 attacks/round is a build "
            "that attacks a little less every round OR one that is occasionally "
            "stunned out of a turn entirely, and only p10 tells those apart. Zero "
            "spread remains the correct answer for any run without control. NOTE for "
            "the reader: this is a LATTICE quantity — a count over a fixed 16-round "
            "denominator, so it moves in steps of 1/16 and its whole IQR is about "
            "three steps. An exact interval cannot be narrower than one step, so the "
            "quantiles read [unconverged] at the quick tier for a reason that is "
            "discreteness rather than noise, and more days is the only thing that "
            "resolves them (measured: 20,000 days converges p10)."
        ),
        group="panel",
    ))
    distribution(DistributionDef(
        name="net_damage_taken_distribution",
        over="net_damage_taken_per_round",
        definition=(
            "The shape of the defensive cost — and the one place where the mean is "
            "most misleading, because the day that kills a character is a TAIL day, "
            "not an average one. p90 is the spike a build must survive; p10 may be "
            "NEGATIVE, which is not an error but surplus healing capacity "
            "(healing.md §2), so this is also the distribution whose interval can "
            "straddle zero. CHARACTER-scoped, inherited from the scalar it "
            "describes."
        ),
        group="panel",
    ))

    return registry


#: The shipped registry.  A caller may build its own :class:`MetricRegistry` for a
#: bespoke analysis, but the reports this project commits use this one — that is
#: what makes the metric set "closed" in any meaningful sense.
METRICS = _build_default_registry()
