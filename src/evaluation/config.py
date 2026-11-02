"""
config.py — ``RunConfig``, one fully-specified simulation (evaluation_framework.md §3.1).

A run is a point in a parameter space.  The design's key insight: a build's
scenario axes (``primal_strike_unarmed``, ``zone_effect``, …) and the enemy's §7
sensitivity toggles are *the same kind of thing* — configuration of one
measurement — so they live in one object and sensitivity analysis works
identically on both sides.

``RunConfig`` is simultaneously the run instruction, the cache key (§10), and the
provenance block's ``config`` half (§4).  It is frozen, canonically serializable,
and hashable.

THE ENEMY FIELDS WENT LIVE IN s50 (§13 step 5)
----------------------------------------------
``enemy`` and ``enemy_options`` were hard-rejected through steps 1-4, because all
three build factories constructed their enemy policy off the *character's* own level
row, so a config claiming to configure the enemy would have claimed an assumption the
run never applied — the §4 failure the rejection protected against.  Step 5a (s50)
built the framework's own enemy-construction seam (``evaluation/enemy.py``) alongside
the baked-in path; step 5b (s52) DELETED the baked-in path.  So:

* ``enemy`` — one of :data:`ENEMY_KINDS`, and **REQUIRED**.  There is no default,
  because a default is an implicit enemy and §3.4's whole point is that an implicit
  enemy is not comparable.  :data:`RETIRED_ENEMY_KINDS` makes the old default's name
  fail with an explanation rather than as an unknown value.
* ``enemy_options`` — validated against ``enemy.ENEMY_OPTION_SCHEMA``, a closed
  schema; an option that cannot APPLY to the chosen kind is refused, not ignored.

``mode="finite_hp"`` is still rejected: it needs ``DayRunner(enemy_ids=…)``, which
no factory passes, and it is not part of step 5.

``combats_per_day`` is likewise validated ``== 4``: ``DayRunner.run_day`` hardcodes
``for i in range(4)``.  The field stays because it is the DPR denominator and
belongs in provenance (§5.2) — it just cannot yet vary.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:                                    # pragma: no cover
    from .adapters import BuildAdapter

#: §10 day-count tiers.  Recorded in provenance so a reader knows the precision
#: of what they are looking at.
DAY_TIERS: dict[str, int] = {
    "quick": 2_000,          # iteration, smoke checks
    "standard": 50_000,      # matches validation.py's default
    "publication": 200_000,  # committed artifacts / site content
}

#: The enemy-selection vocabulary from §3.1.  THREE kinds since s52: the
#: transitional ``build_default`` is retired along with the baked-in path it named
#: (§3.4, step 5b), so every kind is built by ``evaluation/enemy.py`` from the
#: definitive per-level table and every run's enemy assumptions are recorded.
ENEMY_KINDS = ("baseline", "scripted", "none")

#: Retired kinds, kept only so the refusal can say what happened.  A config asking
#: for one gets an error naming its replacement rather than ``not one of (...)``:
#: the name was the DEFAULT for two sessions, so it will appear in old scripts and
#: in anyone's muscle memory, and "unknown value" would send them looking for a typo.
RETIRED_ENEMY_KINDS = {
    "build_default": (
        "retired in s52 (evaluation_framework.md §3.4, step 5b) along with the "
        "baked-in enemy path it named: the enemy material is gone from every build's "
        "LEVELS table and no factory constructs an enemy policy. Pass "
        "enemy='baseline' for the standardized enemy (what any cross-build comparison "
        "wants), 'scripted' for its attack-roll half, or 'none' for a passive target "
        "— which is what build_default resolved to at every level below the build's "
        "old enemy_attack row, bit-identically."
    ),
}

MODES = ("fixed_length", "finite_hp")
_SUPPORTED_MODES = ("fixed_length",)

#: What counts as "the build's own output" for the headline column (§5.3).
#:
#: The s17/§3.3 rule was that a summon's damage NEVER enters the headline, so a
#: build's number could not silently change meaning when it gained a companion.
#: **Amended s44 (user): that is a real modelling CHOICE, not a fact.** A summoner
#: casts a spell and a bear bites — most published build evaluations count that as
#: the caster's damage, because the summon is what the caster's action economy
#: bought. But when the question is "does casting THIS summon beat casting THAT
#: spell", separating the columns is what makes the comparison legible.
#:
#: So the attribution becomes a declared, recorded axis rather than a hidden
#: assumption. Allies are in NEITHER mode: an ally is a party member the build does
#: not command, so its damage was never the build's to claim.
#:
#: The `summon_dpr` and `party_dpr` columns stay registered under both modes — the
#: toggle changes which number is the HEADLINE, never which numbers exist.
ATTRIBUTIONS = ("character", "character_and_summons")

#: role tuples the attribution modes resolve to.
ATTRIBUTION_ROLES: dict[str, tuple[str, ...]] = {
    "character": ("characters",),
    "character_and_summons": ("characters", "summons"),
}

#: The engine's fixed day shape (``DayRunner.run_day``).
COMBATS_PER_DAY = 4


@dataclass(frozen=True)
class RunConfig:
    """One fully-specified simulation.

    Parameters
    ----------
    build:
        Registry key of the build adapter, e.g. ``"war_angel"``.
    level:
        Character level.  Must be in the adapter's ``available_levels()`` — level
        sets are SPARSE and disjoint across builds (§2), so this is checked
        against the build, never against a shared 1–20 range.
    build_options:
        The build's own scenario axes, validated against the adapter's
        ``option_schema()``.
    enemy / enemy_options:
        Which enemy the run faces, and how it is configured (§3.4).  **``enemy`` is
        REQUIRED and has no default** (s52).  Retiring ``"build_default"`` retired
        the four-kind schema's transitional default, and the replacement is not
        another default: if the enemy is not a property of the build, it is not a
        property of a run that forgot to mention it either, and a default is exactly
        an implicit enemy.  §4 already refuses a config that claims an assumption the
        run did not apply; a silent default is the same failure with the claim left
        blank.  Reports produced under different ``enemy`` values must not be
        compared — the same §5.2 rule that governs ``mode`` and ``attribution``.
    rounds_per_combat / combats_per_day:
        The DPR denominator (§5.2).  16 rounds/day is the standardized baseline.
    n_days:
        Adventuring days to simulate.  See :data:`DAY_TIERS`.
    seed:
        Base seed for the run's ``SeededRNG``.  Paired comparisons (§6.1) share
        this across configs.
    mode:
        ``"fixed_length"`` is the standard, comparable basis; ``"finite_hp"`` is
        the alternate emergent-length mode (§5.2), not yet reachable.
    attribution:
        Whether a summon's damage counts as the build's own output — see
        :data:`ATTRIBUTIONS`. Defaults to ``"character"``, the historical basis, so
        no existing baseline moves; the value is recorded in provenance and reports
        under different attributions must not be compared (§5.2's rule, the same one
        that governs ``mode`` and the enemy path).
    """

    build: str
    level: int
    #: REQUIRED — no default (§3.4, step 5b).  Positioned here, ahead of every
    #: defaulted field, because a dataclass cannot put a required field after an
    #: optional one; that it reads as (build, level, enemy) is apt rather than
    #: incidental, since those three are what a measurement is OF.
    enemy: str
    build_options: dict[str, Any] = field(default_factory=dict)
    enemy_options: dict[str, Any] = field(default_factory=dict)
    rounds_per_combat: int = 4
    combats_per_day: int = COMBATS_PER_DAY
    n_days: int = DAY_TIERS["standard"]
    seed: int = 0
    mode: str = "fixed_length"
    attribution: str = "character"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        """Self-contained checks — everything not needing the build registry."""
        if self.rounds_per_combat < 1:
            raise ValueError(f"rounds_per_combat must be >= 1, got {self.rounds_per_combat}.")
        if self.n_days < 1:
            raise ValueError(f"n_days must be >= 1, got {self.n_days}.")
        if self.combats_per_day != COMBATS_PER_DAY:
            raise ValueError(
                f"combats_per_day must be {COMBATS_PER_DAY}: DayRunner.run_day "
                f"hardcodes a four-combat day (got {self.combats_per_day})."
            )
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}.")
        if self.mode not in _SUPPORTED_MODES:
            raise NotImplementedError(
                f"mode={self.mode!r} is designed (evaluation_framework.md §5.2) but "
                "not reachable in step 1: no build factory passes DayRunner(enemy_ids=…). "
                f"Supported today: {_SUPPORTED_MODES}."
            )
        if self.attribution not in ATTRIBUTIONS:
            raise ValueError(
                f"attribution must be one of {ATTRIBUTIONS}, got {self.attribution!r}."
            )
        if self.enemy in RETIRED_ENEMY_KINDS:
            raise ValueError(
                f"enemy={self.enemy!r} is {RETIRED_ENEMY_KINDS[self.enemy]}"
            )
        if self.enemy not in ENEMY_KINDS:
            raise ValueError(f"enemy must be one of {ENEMY_KINDS}, got {self.enemy!r}.")
        # enemy_options are validated in validate(), not here: the schema lives in
        # evaluation/enemy.py, which imports the build data, and __post_init__ stays
        # importable without pulling that in (the same split the build options use).

    def validate(self) -> "BuildAdapter":
        """Registry-dependent checks; returns the resolved adapter.

        Kept separate from ``__post_init__`` so ``RunConfig`` stays importable
        without pulling in every build module.
        """
        from .adapters import get_adapter

        adapter = get_adapter(self.build)

        levels = adapter.available_levels()
        if self.level not in levels:
            raise ValueError(
                f"Build {self.build!r} has no level {self.level}. "
                f"Available (sparse): {levels}."
            )

        schema = adapter.option_schema()
        unknown = sorted(set(self.build_options) - set(schema))
        if unknown:
            raise ValueError(
                f"Build {self.build!r} has no scenario axis {unknown}. "
                f"Known axes: {sorted(schema)}."
            )
        for name, value in self.build_options.items():
            schema[name].check(self.build, value)

        from .enemy import validate_options

        validate_options(self.enemy, self.enemy_options)

        return adapter

    # ------------------------------------------------------------------
    # Serialization / identity
    # ------------------------------------------------------------------

    @property
    def rounds_per_day(self) -> int:
        """The DPR denominator (§5.2).  A control-lost turn STAYS in it — that is
        precisely how control pressure manifests as reduced DPR."""
        return self.combats_per_day * self.rounds_per_combat

    @property
    def own_roles(self) -> "tuple[str, ...]":
        """The roster roles whose damage this run counts as the build's OWN.

        One definition, read by every "the build's output" metric — the headline,
        its per-combat decomposition, and the typed-composition family — so the
        modes cannot drift apart between metrics.
        """
        return ATTRIBUTION_ROLES[self.attribution]

    @property
    def day_tier(self) -> str:
        """The §10 tier name for ``n_days``, or ``"custom"``."""
        for name, days in DAY_TIERS.items():
            if days == self.n_days:
                return name
        return "custom"

    def canonical(self) -> dict[str, Any]:
        """Key-sorted, JSON-safe dict — the serialized form and the hash input."""
        return {
            "build": self.build,
            "level": self.level,
            "build_options": {k: self.build_options[k] for k in sorted(self.build_options)},
            "enemy": self.enemy,
            "enemy_options": {k: self.enemy_options[k] for k in sorted(self.enemy_options)},
            "rounds_per_combat": self.rounds_per_combat,
            "combats_per_day": self.combats_per_day,
            "n_days": self.n_days,
            "seed": self.seed,
            "mode": self.mode,
            "attribution": self.attribution,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"))

    def config_hash(self) -> str:
        """Stable content hash.  Half of §10's cache key — the other half is the
        engine commit, which lives in the provenance block, not here."""
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()[:16]

    def replace(self, **changes: Any) -> "RunConfig":
        """A copy with fields overridden — the natural way to build a comparison
        group where every config shares one ``seed`` (§6.1 paired seeding)."""
        return dataclasses.replace(self, **changes)


# ``frozen=True`` makes the dataclass generate a field-tuple ``__hash__``, which
# blows up on the dict fields.  Hash the canonical form instead, so a config is
# usable as a cache key (§10) exactly as the design requires.
def _run_config_hash(self: RunConfig) -> int:
    return hash(self.canonical_json())


RunConfig.__hash__ = _run_config_hash  # type: ignore[assignment]
