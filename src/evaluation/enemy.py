"""
enemy.py — the enemy-construction seam (evaluation_framework.md §3.4).

**The enemy is not a property of the build.**  Until this module existed it was:
three distinct enemy concerns lived inside the *character* build modules — the
enemy's stat block (``war_angel.LEVELS[13]["enemy_ac"]``), which enemy model is
used at all (War Angel and Starfire construct ``ScriptedEnemyPolicy``, Silvertail
constructs ``BaselineEnemyPolicy``), and whether the enemy acts (the
``LEVELS[level].get("enemy_attack")`` switch).  Cross-build comparison, the whole
purpose of a build-agnostic framework (§1), was not valid.

This module is the framework's own answer: given a :class:`RunConfig` and a
:class:`Roster`, it builds a STANDARDIZED enemy — one declared model, one declared
option set, drawn entirely from the definitive per-level table
(``builds/enemy_stats``) — and installs it over whatever the build factory made.

WHAT THE MIGRATION ACTUALLY IS — the s50 measurement, because it is not what §3.4
predicted
---------------------------------------------------------------------------------
Before building anything, the baked-in enemy data was diffed against the
definitive table.  The result corrects §3.4's own example:

* **Every baked-in ``enemy_ac`` ALREADY equals ``enemy_stats.baseline_ac(level)``** —
  all 16 War Angel levels, all 8 Starfire Scion levels — and Starfire's
  ``enemy_dex_save`` matches ``baseline_save(level, "dex_save")`` too.  They were
  copied out of the same CSV.  ``test_eval_enemy_seam`` pins this as a test rather
  than a comment, because it is the fact the next session will otherwise re-derive.
* So the real coupling is **not the AC**.  It is (a) the enemy's OFFENSE — War Angel
  hardcodes a flat 28 × 3 swings at +11, Starfire a ``2d8+5`` × 2 at +9 whose own
  comment calls it "ILLUSTRATIVE", Silvertail alone uses the table's dice; (b) the
  MODEL, which decides whether saves and control exist at all; (c) whether the enemy
  ACTS, passive below L13 / L15 / L8 respectively; and (d) the enemy's SIX SAVES,
  of which War Angel's dummy carries none and Starfire's carries one.

**The consequence for anyone reading the attacks channel (§8.1).**  A character's
``attack_roll_rate[characters|hit]`` is a function of the enemy's AC and nothing
else.  The AC does not change here, so that rate must NOT move systematically when
the standardized enemy is installed — it moves only by RNG reshuffling, within a
standard error or two.  A large move would be a DEFECT, not a demonstration.  What
the seam genuinely changes is the DEFENDER side (incoming damage, concentration
checks, the control and mitigation channels) and the enemy's own swings.

THE THREE KINDS (four until s52 — see the end of this docstring)
----------------------------------------------------------------
``baseline``
    The standardized enemy: :class:`BaselineEnemyPolicy` at the character's level —
    per-level to-hit / save DC / per-swing and AoE DICE, an attack-vs-save round
    mix, optional control.  This is the one every cross-build comparison should
    use.
``scripted``
    The standardized enemy's attack-roll half only: :class:`ScriptedEnemyPolicy`
    with the table's to-hit and dice on the Entity.  It exists as a COMPARISON ARM,
    not as a legacy shim — ``baseline`` vs ``scripted`` at the same level isolates
    "the enemy forces saves" from "the enemy swings", which is the one comparison
    the baked-in paths could never express because they differed in both at once.
``none``
    A passive target carrying the table's full stat block and no policy.  Measured
    (s52): this is **bit-identical** to what ``build_default`` produced at every level
    below a build's old ``enemy_attack`` row, which is the end-to-end confirmation of
    the AC-equality finding above.

WHY INSTALLATION IS AN OVERLAY RATHER THAN A FACTORY ARGUMENT
-------------------------------------------------------------
§3.4 asks for the standardized enemy to be built "in parallel and deliberately
redundantly while the existing factories stay intact for benchmarking".  Taken
literally that is an overlay: let the factory build its enemy, then replace the
policy and complete the Entity's stat block.  The alternative — an ``enemy=`` kwarg
threaded through all three factories — edits the three modules whose stability the
parity proof rests on, to no benefit while ``build_default`` still has to work.

The overlay is safe because of one checked property: **no enemy policy draws a die
in its constructor.**  Both ``__init__`` methods are pure assignment and all dice
come from ``on_combat_start``, which runs long after installation.  So the discarded
policy costs nothing and shifts no stream.  (``test_eval_enemy_seam`` asserts the
replacement happened, which is what makes "shifts no stream" checkable rather than
asserted.)

**AFTER THE DELETION (s52) there is no policy to discard** — the factories install
none — so the overlay installs rather than replaces.  What it still overlays is the
``Entity``, and that write is now redundant *by construction*: the factories build
their enemy with ``enemy_stats.make_baseline_enemy``, which reads the same
``enemy_base_stats`` / ``baseline_attack_dice`` that ``_complete_stat_block`` writes.
One source, two writers.  "Identical today" is the phrase §3.4 exists to distrust, so
the redundancy is pinned as an assertion rather than left as this paragraph.

NO NEW DICE, AND A DELIBERATE RE-BASELINE
-----------------------------------------
Nothing here rolls (per-feature ritual step 3): ``resolve`` is a pure read and
``install`` writes data.  But installing a different enemy changes what is drawn
*inside* combat, and s52 removed the ``build_default`` escape hatch that had kept
every existing baseline still.  The re-baseline it cost was MEASURED and confined:
``none`` is bit-identical to the old default at every passive level, Silvertail's
baked-in enemy was already the standardized one bit-identically, and what actually
moved was War Angel L13-16 and Starfire L15 — the two builds whose enemy OFFENSE was
hand-written (§3.4's table).  There is no longer a default to shield a baseline:
``RunConfig.enemy`` is a required field.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..builds.enemy import BaselineEnemyPolicy, ScriptedEnemyPolicy
from ..builds.enemy_stats import (
    band_damage_multipliers,
    band_for_level,
    enemy_base_stats,
    baseline_attack_dice,
    baseline_n_attacks,
)
from .adapters import OptionSpec

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import DayRunner
    from ..entity import Entity
    from .config import RunConfig
    from .roster import Roster


#: Kinds this module constructs.  Since s52 that is EVERY kind — ``config.ENEMY_KINDS``
#: and this tuple are now the same set, and the predicate "is this enemy standardized?"
#: is a constant True.  Both names are kept because they answer different questions
#: (what may a config ask for / what does this module build), and collapsing them would
#: make a future non-standardized kind a two-file change instead of a one-line one.
STANDARDIZED_KINDS = ("baseline", "scripted", "none")

#: Which kinds install a policy at all.  ``none`` is a target, not an actor.
ACTING_KINDS = ("baseline", "scripted")

#: Roster roles the enemy can be told to focus (§3.4's "whether the enemy acts"
#: generalized: WHO it acts against is equally not a character-build property —
#: Silvertail's factory picks master-vs-beast off its own ``zone_effect`` axis).
FOCUS_ROLES = ("character", "summon")


# ---------------------------------------------------------------------------
# The declared option surface (§3.1 / §7)
# ---------------------------------------------------------------------------
#
# A CLOSED schema, validated like the build side's, for the same §4 reason: a
# config that claims an assumption the run did not apply poisons provenance.  An
# option that does not APPLY to the chosen kind is refused rather than ignored —
# `control=True` with `enemy="scripted"` is a request the run cannot honour, and
# silently dropping it is exactly the failure mode the step-1 hard rejection was
# protecting against.

ENEMY_OPTION_SCHEMA: dict[str, OptionSpec] = {
    "control": OptionSpec(
        "control", default=False, values=(True, False),
        description=(
            "§6 control channel: the enemy spends part of its action budget on "
            "incapacitation saves. baseline only. THE STEP-6 PREREQUISITE — control "
            "lives on BaselineEnemyPolicy, so no build could measure control "
            "resilience while its factory installed ScriptedEnemyPolicy."
        ),
    ),
    "mitigation": OptionSpec(
        "mitigation", default=False, values=(True, False),
        description=(
            "§5 mult(t): install the band's mean-field res/imm/vuln profile on the "
            "enemy Entity's damage_multiplier, so the §13 mitigation channel records "
            "outgoing damage before and after type mitigation. Independent of the "
            "policy — it lives on the Entity — so it applies to every kind including "
            "'none'."
        ),
    ),
    "focus": OptionSpec(
        "focus", default="character", values=FOCUS_ROLES,
        description=(
            "Which roster role the enemy focus-fires; the other is its fallback once "
            "the first is out of action. DECLARED rather than derived from the build: "
            "the two facts vary independently (Silvertail's own factory switches "
            "master-vs-beast off its zone_effect axis), which is precisely the "
            "per-feature step-4 test."
        ),
    ),
    "char_target_prob": OptionSpec(
        "char_target_prob", default=1.0, values=None,
        description=(
            "scripted only: probability each swing lands on the focus target. Default "
            "1.0 (focus-fire) because the standardized basis is comparable rather than "
            "realistic (memory standardized-dpr-baseline-not-realism); War Angel's "
            "baked-in 0.40 was a PARTY-SIZE assumption, and party size is an "
            "enemy-side scenario axis, not a character-build property. WHERE THE "
            "OFF-TARGET SHARE LANDS is derived from the roster, not declared: on the "
            "build's ALLIES if it fields any (a real HP pool — Starfire's with_party "
            "member), otherwise on an unmodelled party member, i.e. nowhere. Derived "
            "because the two facts cannot come apart — 'which entities can absorb a "
            "swing' IS the roster — so this is the s48 interval-from-statistic case, "
            "not the s49 sum_rule case."
        ),
    ),
    "band_override": OptionSpec(
        "band_override", default=None, values=(None, "0-4", "5-10", "11-16", "17+"),
        description=(
            "§7 CR-band override: force the band's qualitative MIX while level still "
            "drives the magnitudes. Also overrides the band read for 'mitigation'."
        ),
    ),
    "damage_type": OptionSpec(
        "damage_type", default=None, values=None,
        description=(
            "A fixed damage TYPE on the enemy's swings; None = untyped (the legacy "
            "default). 'force' is the documented force-mode probe: force has no "
            "res/imm/vul prevalence columns, so §5's mult(t) is 1.0 for it in every "
            "band, isolating flat mitigation from typed."
        ),
    ),
    "damage_type_mix": OptionSpec(
        "damage_type_mix", default=False, values=(True, False),
        description=(
            "§7: per-round weighted draw from the band-empirical incoming "
            "damage-type mix instead of the fixed scalar. baseline only."
        ),
    ),
    "legendary_cadence": OptionSpec(
        "legendary_cadence", default=False, values=(True, False),
        description=(
            "§7: add the band's mean-field number of extra legendary swings to every "
            "round (0 at bands 0-4/5-10, so a no-op below L11). baseline only."
        ),
    ),
    "control_displacement": OptionSpec(
        "control_displacement", default="displace", values=("displace", "ride"),
        description=(
            "§4b: 'displace' = a pure-control round replaces the damage action; "
            "'ride' keeps the damage action and layers control on top, isolating the "
            "lost-turn effect. Requires control=True."
        ),
    ),
    "soft_factor": OptionSpec(
        "soft_factor", default=None, values=None,
        description=(
            "§6: the output fraction a SOFT-controlled turn retains. None resolves to "
            "enemy_stats.SOFT_FACTOR, and provenance records the resolved value with "
            "its source — the §4 example the design uses by name. Requires "
            "control=True."
        ),
    ),
}

#: Options that only a policy can honour, by the kind that can honour them.  The
#: refusal messages are generated from this, so a new option cannot be added
#: without saying which kinds it applies to.
_OPTION_KINDS: dict[str, tuple[str, ...]] = {
    "control": ("baseline",),
    "control_displacement": ("baseline",),
    "soft_factor": ("baseline",),
    "damage_type_mix": ("baseline",),
    "legendary_cadence": ("baseline",),
    "char_target_prob": ("scripted",),
    "damage_type": ACTING_KINDS,
    "focus": ACTING_KINDS,
    # 'mitigation' and 'band_override' live on the Entity / the band lookup, so
    # they apply to every kind — absent from this map means "applies to all".
}

#: Options that are meaningless unless control is on.  Refused rather than
#: ignored, same argument as above.
_CONTROL_DEPENDENT = ("control_displacement", "soft_factor")


def validate_options(kind: str, options: dict[str, Any]) -> None:
    """Check ``options`` against the schema for ``kind``; raise on anything the run
    could not actually honour.

    Three refusals, each the same §4 argument: a provenance block that claims an
    assumption the run did not apply documents nothing.
    """
    unknown = sorted(set(options) - set(ENEMY_OPTION_SCHEMA))
    if unknown:
        raise ValueError(
            f"Unknown enemy option(s) {unknown}. Known: "
            f"{sorted(ENEMY_OPTION_SCHEMA)}."
        )
    for name, value in options.items():
        ENEMY_OPTION_SCHEMA[name].check(f"enemy:{kind}", value)
        applies = _OPTION_KINDS.get(name)
        if applies is not None and kind not in applies:
            raise ValueError(
                f"Enemy option {name!r} applies only to enemy kind(s) "
                f"{list(applies)}, not to {kind!r}. Ignoring it would make "
                "provenance claim an assumption the run never applied (§4)."
            )
    if not options.get("control", ENEMY_OPTION_SCHEMA["control"].default):
        for name in _CONTROL_DEPENDENT:
            if name in options:
                raise ValueError(
                    f"Enemy option {name!r} is meaningless without control=True — "
                    "the control channel is off, so nothing would read it (§4)."
                )
    prob = options.get("char_target_prob")
    if prob is not None and not 0.0 <= float(prob) <= 1.0:
        raise ValueError(f"char_target_prob must be in [0, 1], got {prob!r}.")
    soft = options.get("soft_factor")
    if soft is not None and not 0.0 <= float(soft) <= 1.0:
        raise ValueError(f"soft_factor must be in [0, 1], got {soft!r}.")


def resolved_options(config: "RunConfig") -> dict[str, Any]:
    """Every declared enemy option with the value ACTUALLY used (§4).

    The build side's ``_resolved_options`` for the enemy half: the caller's value
    where given, the schema default otherwise — never the word "default".  Options
    that do not apply to the chosen kind are omitted entirely rather than reported
    at their default, because reporting them would imply they were in force.
    """
    kind = config.enemy
    out: dict[str, Any] = {}
    for name, spec in ENEMY_OPTION_SCHEMA.items():
        applies = _OPTION_KINDS.get(name)
        if applies is not None and kind not in applies:
            continue
        out[name] = config.enemy_options.get(name, spec.default)
    if not out.get("control", False):
        for name in _CONTROL_DEPENDENT:
            out.pop(name, None)
    return out


# ---------------------------------------------------------------------------
# Resolution for provenance (§4) — a pure read
# ---------------------------------------------------------------------------

def resolve(config: "RunConfig") -> dict[str, Any]:
    """The RESOLVED enemy block for §4 provenance.

    Pure: it rolls nothing and mutates nothing, so it is safe to call before the
    run and again when the report is assembled.

    It takes the CONFIG and nothing else since s52, and that signature change is the
    deletion in miniature.  Through s50-s51 it also took the build adapter's
    ``described`` block, for one purpose: under ``build_default`` the enemy genuinely
    WAS a property of the build, so the only place its model could be named was the
    adapter, and the block said ``resolved: False`` to avoid implying otherwise.  With
    the baked-in path gone there is no such asymmetry left to report — every run's
    enemy is built here, from the declared kind and the definitive table, so
    ``resolved`` is unconditionally True and the adapter has nothing to contribute.
    """
    kind = config.enemy
    options = resolved_options(config)
    band = options.get("band_override") or band_for_level(config.level)
    block: dict[str, Any] = {
        "kind": kind,
        "standardized": True,
        "resolved": True,
        "policy": {"baseline": "baseline", "scripted": "scripted",
                   "none": None}[kind],
        "acts": kind in ACTING_KINDS,
        "options": options,
        "level": config.level,
        "band": band,
        "band_source": ("enemy_options['band_override']" if options.get("band_override")
                        else f"enemy_stats.band_for_level({config.level})"),
        "stat_block": dict(enemy_base_stats(config.level)),
        "stat_block_source": (
            f"enemy_stats.enemy_base_stats({config.level}) — "
            "reference/data/monster_stats_by_level.csv"
        ),
        "source": (
            "evaluation/enemy.py — the framework's own seam, drawn entirely from the "
            "definitive per-level table (§3.4)"
        ),
    }
    if kind in ACTING_KINDS:
        block["n_attacks"] = baseline_n_attacks(config.level)
        block["attack_dice"] = baseline_attack_dice(config.level)
    if options.get("mitigation"):
        block["damage_multiplier"] = band_damage_multipliers(config.level, band=band)
    return block


# ---------------------------------------------------------------------------
# Installation — the only mutating entry point
# ---------------------------------------------------------------------------

def install(runner: "DayRunner", roster: "Roster", config: "RunConfig") -> dict[str, Any]:
    """Replace the factory's enemy with the standardized one; return the resolved block.

    Unconditional since s52: there is no longer a kind that leaves the factory's own
    enemy in place, because the factories no longer build one that acts.  What they do
    build is an ``Entity`` from ``enemy_stats.make_baseline_enemy`` — the same source
    ``_complete_stat_block`` writes from — so the overlay's stat-block write is now
    provably a no-op and the only thing it adds is the option-dependent part.

    Order matters and is deliberate: the Entity's stat block is completed FIRST, so
    a policy constructed against it reads final numbers; then the policy is
    installed.  Neither step draws a die.
    """
    if not roster.enemies:
        raise ValueError(
            f"Build {config.build!r} returned a roster with no enemies, so there is "
            "nothing to install a standardized enemy onto."
        )
    if len(roster.enemies) > 1:
        raise NotImplementedError(
            f"Build {config.build!r} fields {len(roster.enemies)} enemies; the §3.4 "
            "seam installs ONE standardized enemy. Multi-enemy standardization waits "
            "on the multi-enemy / spatial model (§10)."
        )
    enemy = roster.enemies[0]
    options = resolved_options(config)
    band = options.get("band_override") or band_for_level(config.level)

    _complete_stat_block(enemy, config.level, options, band)

    policy = _make_policy(roster, config, options)
    if policy is None:
        runner.policies.pop(enemy.id, None)
    else:
        runner.policies[enemy.id] = policy
    return resolve(config)


def _complete_stat_block(enemy: "Entity", level: int, options: dict[str, Any],
                         band: str) -> None:
    """Write the table's full profile onto the enemy Entity.

    The Entity keeps anything the factory put there that the table does not name
    (so a build's own dummy extras survive), and the table wins on everything it
    does name.  In practice the AC never changes — see the module docstring — but
    the overlay is written unconditionally and the no-change property is a TEST,
    not an assumption.

    ``damage_dice`` / ``damage_bonus`` are set because a ``ScriptedEnemyPolicy``
    swing carries no dice on its ``Choice``: resolution reads them off the actor
    (``verbs.resolve_damage`` → ``actor.stat("damage_dice")``).  Setting them for
    every kind keeps the Entity a complete, inspectable stat block rather than one
    whose contents depend on which policy happens to be attached.
    """
    n, sides, bonus = baseline_attack_dice(level)
    enemy.base_stats.update(enemy_base_stats(level))
    enemy.base_stats["damage_dice"] = (n, sides)
    enemy.base_stats["damage_bonus"] = bonus
    if options.get("mitigation"):
        enemy.damage_multiplier = dict(band_damage_multipliers(level, band=band))


def _focus_pair(roster: "Roster", focus: str) -> "tuple[Entity, Entity | None]":
    """``(primary, fallback)`` for the declared focus role.

    ``focus="summon"`` on a build with no summon is an ERROR rather than a silent
    fall back to the character: the config asked for a measurement this roster
    cannot produce, and quietly measuring a different one is how a report comes to
    describe something nobody configured.
    """
    character = roster.character
    summons = roster.summons
    if focus == "summon":
        if not summons:
            raise ValueError(
                "enemy_options['focus']='summon' but this build's roster has no "
                "summons, so there is nothing to focus. The character is a different "
                "measurement, not a fallback."
            )
        return summons[0], character
    return character, summons[0] if summons else None


def _ally_roster(roster: "Roster", primary: "Entity",
                 char_target_prob: float) -> "list[tuple[Entity, int]] | None":
    """The weighted friendly roster for a ``scripted`` enemy, or ``None`` for the
    single-target path.

    This is what step 5b does with the one capability the deletion would otherwise have
    stranded.  ``ScriptedEnemyPolicy`` has always supported a weighted split across
    several friendlies, and until s52 the ONLY caller was Starfire's factory, reading
    ``char_weight``/``party_weight`` off its own ``LEVELS`` row — baked-in enemy
    behaviour of exactly the kind §3.4 removes.  s50 noted the branch was already
    unreachable through ``RunConfig``; deleting the row would have made it unreachable
    full stop, i.e. dead code, which is the trap §7.6 was written about.  So rather
    than invent a second option for it, the EXISTING ``char_target_prob`` gains teeth:
    the off-target share lands on the build's allies when it fields any.

    **The dice stream is unchanged, and that is a property rather than a hope.**  The
    weights are integers summing to exactly 100, so the policy's multi-entity pre-roll
    is ``roll_one(100)`` per attack slot — the same die, in the same order, as the
    single-target path's ``roll_one(100) <= p_pct``, and the same primary/not-primary
    verdict.  Only the DESTINATION of an off-target swing changes: a real ally's HP
    pool instead of nowhere.  With the default ``char_target_prob=1.0`` the allies get
    weight 0 and can never be picked, so a standardized focus-fire run is unaffected
    even on a build that fields a party.
    """
    allies = roster.allies
    if not allies:
        return None                       # nothing to absorb it — legacy path
    primary_weight = int(round(char_target_prob * 100))
    share, extra = divmod(100 - primary_weight, len(allies))
    weights = [(primary, primary_weight)]
    for i, ally in enumerate(allies):
        weights.append((ally, share + (extra if i == 0 else 0)))
    return weights


def _make_policy(roster: "Roster", config: "RunConfig", options: dict[str, Any]):
    """Construct the standardized policy, or ``None`` for a passive target."""
    kind = config.enemy
    if kind == "none":
        return None

    primary, fallback = _focus_pair(roster, options["focus"])

    if kind == "scripted":
        return ScriptedEnemyPolicy(
            target=primary,
            n_attacks=baseline_n_attacks(config.level),
            char_target_prob=options["char_target_prob"],
            rounds_per_combat=config.rounds_per_combat,
            damage_type=options["damage_type"],
            roster=_ally_roster(roster, primary, options["char_target_prob"]),
        )

    return BaselineEnemyPolicy(
        level=config.level,
        primary=primary,
        fallback=fallback,
        rounds_per_combat=config.rounds_per_combat,
        damage_type=options["damage_type"],
        control=options["control"],
        control_displacement=options.get("control_displacement", "displace"),
        soft_factor=options.get("soft_factor"),
        band_override=options["band_override"],
        damage_type_mix=options["damage_type_mix"],
        legendary_cadence=options["legendary_cadence"],
    )
