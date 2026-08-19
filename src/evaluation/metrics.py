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

Not registered here: the ``attacks`` channel (hit %, crit %, advantage %).  §8.1
scopes it as step 4, and the ``CombatTelemetry`` field does not exist yet — a
declared-unavailable metric whose extractor references a missing attribute would be
dead code rather than an honest declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterator

from .statistics import (
    DEFAULT_CONVERGENCE,
    RARE_EVENT_CONVERGENCE,
    Convergence,
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

    def dealt(self, *roles: str) -> float:
        """Damage DEALT by every entity in the given roster roles."""
        return float(sum(self.damage_dealt[i] for i in self.roster.ids(*roles)))

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

    def control(self, attr: str) -> float:
        """A summed field of the §13 control channel (``failures`` /
        ``turns_lost`` / ``turns_reduced``)."""
        return float(sum(getattr(t, attr) for t in self.telemetry.control.values()))

    def mitigation(self, attr: str, *, damage_type: "str | None" = None,
                   roles: "tuple[str, ...]" = ("characters",)) -> float:
        """A summed field of the §13 mitigation channel.

        Scoped to the given roster ROLES by default — the channel is keyed
        ``(actor_id, damage_type)`` precisely so a summon's radiant damage and a
        typed-damage enemy's swings do not pool into the character's composition.
        """
        cells = self.telemetry.mitigation_by_type(set(self.roster.ids(*roles)))
        if damage_type is not None:
            cell = cells.get(damage_type)
            return float(getattr(cell, attr)) if cell is not None else 0.0
        return float(sum(getattr(m, attr) for m in cells.values()))

    def combat_damage(self, combat_num: int,
                      *, roles: "tuple[str, ...]" = ("characters",)) -> float:
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
        ids = set(self.roster.ids(*roles))
        return float(sum(
            damage for (source, _target), damage
            in combats[combat_num - 1].damage_by_source_target.items()
            if source in ids
        ))

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


def _denominator_family(prefix: str, description: str,
                        make: Callable[[str], Callable[[DaySample], float]],
                        keys: tuple[str, ...]) -> dict[str, Denominator]:
    """Build one random denominator per key (e.g. saves forced, per ability)."""
    return {
        f"{prefix}[{key}]": Denominator(
            name=f"{prefix}[{key}]",
            description=description.format(key=key),
            fixed=False,
            per_day=make(key),
        )
        for key in keys
    }


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
    "saves_forced": Denominator(
        name="saves_forced",
        description=(
            "Saving throws actually forced during the run (§13 saves channel, both "
            "channels). Random and correlated with the numerator, so rates over it "
            "use the ratio-of-means estimator."
        ),
        fixed=False,
        per_day=lambda s: s.saves(),
    ),
    "damage_saves_forced": Denominator(
        name="damage_saves_forced",
        description="Saves forced by DAMAGING effects (§13 saves channel, 'damage').",
        fixed=False,
        per_day=lambda s: s.saves(channel="damage"),
    ),
    "control_saves_forced": Denominator(
        name="control_saves_forced",
        description="Saves forced by CONTROL effects (§13 saves channel, 'control').",
        fixed=False,
        per_day=lambda s: s.saves(channel="control"),
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
DENOMINATORS["character_damage_dealt"] = Denominator(
    name="character_damage_dealt",
    description=(
        "All damage the build's own characters dealt (the headline column's "
        "numerator). The denominator for shares OF the build's output."
    ),
    fixed=False,
    per_day=lambda s: s.dealt("characters"),
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

DENOMINATORS.update(_denominator_family(
    "saves_forced",
    "Saves of type {key} actually forced (§13 saves channel, both channels).",
    lambda stat: (lambda s, _stat=stat: s.saves(stat=_stat)),
    SAVE_STATS,
))


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


def _requires_control_channel(ctx: RunContext) -> "str | None":
    """Control metrics are unavailable in EVERY run today (§3.4), for two different
    reasons depending on which enemy model the build's factory picked.

    Naming the reason per build matters: "War Angel cannot be measured" and
    "Silvertail's enemy has the channel but it is switched off" are different
    problems with different fixes, and the report should not flatten them.
    """
    policy = ctx.described.get("enemy_policy")
    if policy == "scripted":
        return (
            "the enemy is ScriptedEnemyPolicy, which has no control channel at all "
            "(§3.4: the three builds do not currently face the same enemy model). "
            "Measurable once the §13 step-5 enemy-construction seam installs the "
            "standardized enemy for every build."
        )
    if policy == "baseline":
        return (
            "the enemy is BaselineEnemyPolicy constructed with control=False, and "
            "RunConfig.enemy_options is hard-rejected until the §3.4 enemy seam "
            "(§13 step 5), so the control channel cannot be enabled from here."
        )
    return (
        "the enemy never acts at this level (the build's data row carries no "
        "enemy_attack), so no control save is ever forced"
    )


def _requires_mitigation_profile(ctx: RunContext) -> "str | None":
    """Evidence-based: §5's ``mult(t)`` lives on ``Entity.damage_multiplier``, so we
    can simply look at whether anyone in the roster carries a profile."""
    if any(e.damage_multiplier for e in ctx.roster.entities()):
        return None
    return (
        "no entity in this run carries a damage_multiplier profile — §5's mult(t) is "
        "installed at Entity construction and no build factory installs one today, so "
        "the mitigation channel records nothing. Goes live with the §13 step-5 enemy "
        "seam (enemy_stats.band_damage_multipliers)."
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

    def __post_init__(self) -> None:
        if self.group not in GROUPS:
            raise ValueError(f"Metric {self.name!r}: group must be one of {GROUPS}.")
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
            "convergence": self.convergence.describe(),
        }


class MetricRegistry:
    """The closed metric set.  Iterating it is the report's assembly order."""

    def __init__(self, definitions: "list[MetricDef] | None" = None) -> None:
        self._defs: dict[str, MetricDef] = {}
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition: MetricDef) -> MetricDef:
        if definition.name in self._defs:
            raise ValueError(f"Metric {definition.name!r} is already registered.")
        self._defs[definition.name] = definition
        return definition

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
        return iter(self._defs.values())

    def __len__(self) -> int:
        return len(self._defs)

    def names(self) -> list[str]:
        return list(self._defs)

    def group(self, group: str) -> list[MetricDef]:
        if group not in GROUPS:
            raise KeyError(f"Unknown metric group {group!r}; expected {GROUPS}.")
        return [d for d in self._defs.values() if d.group == group]

    @property
    def headline(self) -> MetricDef:
        """The single headline metric (§5.3): character-column DPR.

        Raises if the registry declares anything but exactly one, because "no
        composite build score" (§5.3) only means something if the headline stays a
        single declared quantity rather than drifting into a basket.
        """
        heads = self.group("headline")
        if len(heads) != 1:
            raise ValueError(
                f"Expected exactly one headline metric, found {[d.name for d in heads]}."
            )
        return heads[0]

    def data_dictionary(self) -> list[dict[str, Any]]:
        """Every metric's declaration — §5.1's "the registry IS the data dictionary"."""
        return [d.describe() for d in self._defs.values()]


# ---------------------------------------------------------------------------
# The shipped registry (§5.3's headline / panel / columns)
# ---------------------------------------------------------------------------

def _build_default_registry() -> MetricRegistry:
    registry = MetricRegistry()
    reg = registry.register

    # -- headline (§5.3): the character column, alone --------------------
    reg(MetricDef(
        name="dpr",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — DayResult.damage_by_source, roster role 'characters'",
        definition=(
            "Damage dealt by the build's OWN characters, per round of the "
            "standardized day. Summons and allies are excluded by construction."
        ),
        numerator=lambda s: s.dealt("characters"),
        group="headline",
    ))

    # -- roster columns (§5.3): beside the headline, never merged into it -
    reg(MetricDef(
        name="party_dpr",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — characters + summons + allies",
        definition=(
            "Roster total: damage dealt by the character plus everything fighting "
            "with it. Reported BESIDE the headline; merging the two would make a "
            "build's headline silently change meaning the moment it gains a summon."
        ),
        numerator=lambda s: s.dealt("characters", "summons", "allies"),
        group="column",
    ))
    reg(MetricDef(
        name="summon_dpr",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — roster role 'summons'",
        definition="Damage dealt by entities the build created and commands.",
        numerator=lambda s: s.dealt("summons"),
        availability=_requires_role("summons"),
        group="column",
    ))
    reg(MetricDef(
        name="ally_dpr",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — roster role 'allies'",
        definition="Damage dealt by friendly entities the build does not command.",
        numerator=lambda s: s.dealt("allies"),
        availability=_requires_role("allies"),
        group="column",
    ))

    # -- panel: defense ---------------------------------------------------
    reg(MetricDef(
        name="damage_taken_per_round",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — DayResult.damage_received_by, role 'characters'",
        definition="Damage the build's own characters absorb, per round.",
        numerator=lambda s: s.taken("characters"),
    ))
    reg(MetricDef(
        name="summon_damage_taken_per_round",
        unit="damage/round",
        denominator="rounds",
        source="damage ledger — role 'summons'",
        definition=(
            "Damage absorbed by the build's summons — the defensive half of a "
            "summon's contribution, which the DPR column alone does not show."
        ),
        numerator=lambda s: s.taken("summons"),
        availability=_requires_role("summons"),
    ))

    # -- panel: saves (§13 saves channel) ---------------------------------
    reg(MetricDef(
        name="saves_forced_per_round",
        unit="saves/round",
        denominator="rounds",
        source="§13 saves channel — every (ability, channel) cell",
        definition=(
            "Saving throws forced per round, either direction (the build forcing "
            "them and the enemy forcing them both land in this channel)."
        ),
        numerator=lambda s: s.saves(),
    ))
    reg(MetricDef(
        name="save_fail_rate",
        unit="fraction",
        denominator="saves_forced",
        source="§13 saves channel — failed / forced",
        definition=(
            "Share of forced saves that failed. A ratio over a RANDOM denominator: "
            "each save weighs equally, not each day."
        ),
        numerator=lambda s: s.saves(outcome="failed"),
        events=lambda s: s.saves(),
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
    ))
    reg(MetricDef(
        name="damage_save_fail_rate",
        unit="fraction",
        denominator="damage_saves_forced",
        source="§13 saves channel — channel 'damage'",
        definition="Share of DAMAGING-effect saves that failed.",
        numerator=lambda s: s.saves(channel="damage", outcome="failed"),
        events=lambda s: s.saves(channel="damage"),
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
    ))

    # Per-ability family (§5.3 "saves forced/failed BY TYPE"), generated over the
    # closed SAVE_STATS vocabulary so the panel is complete rather than whatever
    # happened to fire in one run.
    for stat in SAVE_STATS:
        reg(MetricDef(
            name=f"saves_forced_per_round_{stat}",
            unit="saves/round",
            denominator="rounds",
            source=f"§13 saves channel — ability {stat!r}, both channels",
            definition=f"{stat} saving throws forced per round.",
            numerator=(lambda s, _st=stat: s.saves(stat=_st)),
        ))
        reg(MetricDef(
            name=f"save_fail_rate_{stat}",
            unit="fraction",
            denominator=f"saves_forced[{stat}]",
            source=f"§13 saves channel — ability {stat!r}, failed / forced",
            definition=(
                f"Share of forced {stat} saves that failed. Has NO value on a run "
                f"that never forces one — reported as unmeasured, not as zero."
            ),
            numerator=(lambda s, _st=stat: s.saves(stat=_st, outcome="failed")),
            events=(lambda s, _st=stat: s.saves(stat=_st)),
            convergence=Convergence(rel_stderr=0.05, min_events=500.0),
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
        definition="Concentration losses per adventuring day.",
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
    reg(MetricDef(
        name="control_save_fail_rate",
        unit="fraction",
        denominator="control_saves_forced",
        source="§13 saves channel — channel 'control', failed / forced",
        definition=(
            "Share of CONTROL saves that failed — the build's control resilience. "
            "The metric the §3.4 enemy-independence gap makes unmeasurable today."
        ),
        numerator=lambda s: s.saves(channel="control", outcome="failed"),
        events=lambda s: s.saves(channel="control"),
        availability=_requires_control_channel,
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
    ))

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

    # -- panel: outgoing damage-type composition (§13 mitigation channel) --
    # The same channel cells the mitigation metrics read; with no resistance
    # profile installed before == after, and the numbers describe WHAT the build
    # deals rather than what the enemy removes.
    reg(MetricDef(
        name="typed_damage_per_round",
        unit="damage/round",
        denominator="rounds",
        source="§13 mitigation channel — outgoing_before, summed over types",
        definition=(
            "Outgoing damage that carries a damage TYPE, per round. Below the "
            "headline by exactly the untyped damage the build deals, which is why "
            "the share metrics below are shares of THIS, not of dpr."
        ),
        numerator=lambda s: s.mitigation("outgoing_before"),
    ))
    reg(MetricDef(
        name="typed_damage_share",
        unit="fraction",
        denominator="character_damage_dealt",
        source="§13 mitigation channel / damage ledger",
        definition=(
            "Share of the character column that carries a declared damage type. "
            "Reads 0 for a build whose damage is untyped in the model — which is "
            "worth knowing BEFORE reading any type share, and also means the §5 "
            "resistance multiplier can never touch that build's output."
        ),
        numerator=lambda s: s.mitigation("outgoing_before"),
        events=lambda s: s.dealt("characters"),
        convergence=Convergence(rel_stderr=0.05, min_events=500.0),
    ))
    for damage_type in DAMAGE_TYPES:
        reg(MetricDef(
            name=f"damage_share_{damage_type}",
            unit="fraction",
            denominator="outgoing_typed_damage",
            source=f"§13 mitigation channel — outgoing_before[{damage_type!r}]",
            definition=(
                f"Share of the build's TYPED output dealt as {damage_type}. A zero "
                f"is a real measurement; the family covers the closed type "
                f"vocabulary so composition is complete rather than partial."
            ),
            numerator=(lambda s, _t=damage_type: s.mitigation("outgoing_before",
                                                              damage_type=_t)),
            events=(lambda s, _t=damage_type: s.mitigation("outgoing_before",
                                                           damage_type=_t)),
            convergence=Convergence(rel_stderr=0.05, min_events=500.0),
        ))

    # -- panel: the shape of the day (damage ledger, per combat / per round) --
    # §5.3's panel is about what a mean hides. These are the cheapest such
    # metrics available: the four-combat day and the per-round log are already on
    # DayResult, and a day-level mean discards both.
    for combat_num in range(1, 5):
        reg(MetricDef(
            name=f"dpr_combat_{combat_num}",
            unit="damage/round",
            denominator="combat_rounds",
            source=f"damage ledger — DayResult.damage_by_combat[{combat_num - 1}]",
            definition=(
                f"DPR within combat {combat_num} of the day. The 1-vs-4 gap is the "
                f"resource-depletion curve: a build that front-loads its day looks "
                f"identical to a sustained one at the day level."
            ),
            numerator=(lambda s, _c=combat_num: s.combat_damage(_c)),
        ))
    reg(MetricDef(
        name="party_dpr_opening_round",
        unit="damage/round",
        denominator="opening_rounds",
        source="damage ledger — CombatResult.damage_received[enemy], round 1 of each combat",
        definition=(
            "Damage the enemy took in the FIRST round of each combat, per opening "
            "round — the front-loading figure (nova openers, pre-cast buffs, "
            "first-round riders). PARTY-scoped: the per-round log is keyed by "
            "target only, so this is comparable to party_dpr, not to the headline."
        ),
        numerator=lambda s: s.opening_round_damage(),
        group="column",
    ))

    return registry


#: The shipped registry.  A caller may build its own :class:`MetricRegistry` for a
#: bespoke analysis, but the reports this project commits use this one — that is
#: what makes the metric set "closed" in any meaningful sense.
METRICS = _build_default_registry()
