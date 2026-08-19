"""
evaluation — the build-agnostic evaluation framework (design/evaluation_framework.md).

Step 1 of §13's build sequence: ``RunConfig`` + ``BuildAdapter`` + ``Roster`` +
the build registry, with adapters for the three builds that exist today.

The layer's reason for existing (§1): ``src/validation.py`` is hardcoded to the
War Angel and reads entities by tuple position, so it cannot be generalized in
place.  Everything here is built so that adding a build means writing an adapter,
never editing evaluation code — the same rule that keeps the engine free of
D&D-specific knowledge.

``src/validation.py`` stays untouched as the regression check until the framework
reproduces its numbers exactly (§13); ``tests/test_eval_framework.py`` is that
proof.
"""

from .adapters import BuildAdapter, OptionSpec, available_builds, get_adapter, register
from .config import DAY_TIERS, ENEMY_KINDS, MODES, RunConfig
from .roster import ROLES, Roster
from .runner import RunOutput, mean_dpr, simulate

__all__ = [
    "BuildAdapter",
    "OptionSpec",
    "register",
    "get_adapter",
    "available_builds",
    "RunConfig",
    "DAY_TIERS",
    "ENEMY_KINDS",
    "MODES",
    "Roster",
    "ROLES",
    "simulate",
    "RunOutput",
    "mean_dpr",
]
