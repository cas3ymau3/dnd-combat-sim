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

STEP-1 SCOPE NOTE (named deferral, not silent)
----------------------------------------------
Three fields are part of the LOCKED §3.1 shape but have nowhere to land yet,
because all three existing build factories construct their enemy policy and their
combat loop internally:

* ``enemy`` — the factories pick the enemy policy themselves off the level's data
  row (``ScriptedEnemyPolicy`` / ``BaselineEnemyPolicy`` / none).  Only
  ``"build_default"`` is honourable today; ``"baseline"`` / ``"scripted"`` /
  ``"none"`` are rejected with an explicit message rather than silently ignored.
* ``enemy_options`` — the §7 toggles are ``BaselineEnemyPolicy`` constructor
  kwargs the factories never expose.  Must be empty; a non-empty dict is an error.
* ``mode="finite_hp"`` — needs ``DayRunner(enemy_ids=…)``, which no factory passes.

Rejecting is deliberate: a config that *claims* an assumption the run did not
apply would poison the provenance block, which is the whole point of §4.  These
unlock when the framework grows its own enemy-construction seam (a later step),
not by weakening the check here.

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

#: The enemy-selection vocabulary from §3.1.  Only the first is honourable in
#: step 1 (see the module docstring).
ENEMY_KINDS = ("build_default", "baseline", "scripted", "none")
_SUPPORTED_ENEMY_KINDS = ("build_default",)

MODES = ("fixed_length", "finite_hp")
_SUPPORTED_MODES = ("fixed_length",)

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
        See the module docstring — shape is locked, only ``"build_default"`` with
        no options is honourable in step 1.
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
    """

    build: str
    level: int
    build_options: dict[str, Any] = field(default_factory=dict)
    enemy: str = "build_default"
    enemy_options: dict[str, Any] = field(default_factory=dict)
    rounds_per_combat: int = 4
    combats_per_day: int = COMBATS_PER_DAY
    n_days: int = DAY_TIERS["standard"]
    seed: int = 0
    mode: str = "fixed_length"

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
        if self.enemy not in ENEMY_KINDS:
            raise ValueError(f"enemy must be one of {ENEMY_KINDS}, got {self.enemy!r}.")
        if self.enemy not in _SUPPORTED_ENEMY_KINDS:
            raise NotImplementedError(
                f"enemy={self.enemy!r} is designed (evaluation_framework.md §3.1) but not "
                "wired in step 1: each build factory constructs its own enemy policy off "
                f"the level's data row. Supported today: {_SUPPORTED_ENEMY_KINDS}."
            )
        if self.enemy_options:
            raise NotImplementedError(
                "enemy_options (the §7 sensitivity toggles) are BaselineEnemyPolicy "
                "constructor kwargs that no build factory exposes, so step 1 cannot "
                "honour them. Passing them silently would make the provenance block "
                f"claim assumptions the run never applied. Got: {sorted(self.enemy_options)}."
            )

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
