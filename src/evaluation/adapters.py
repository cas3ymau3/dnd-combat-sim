"""
adapters.py — the per-build seam and its registry (evaluation_framework.md §3.2).

**Adapt, do not rewrite** (§2's design consequence).  The three existing build
factories stay EXACTLY as they are — they back validated DPR baselines (War Angel
L1–16 against guide targets), and rewriting them would risk drift for no gain.
Each build instead registers a thin adapter that maps a :class:`RunConfig` to a
``DayRunner`` plus a role-tagged :class:`Roster`.

Adding a build = writing an adapter (~20 lines wrapping the existing factory) and
registering it.  No evaluation-layer code changes.  This mirrors the project's
standing rule that new content should never force engine edits.

The four axes of variance an adapter absorbs (§2):

1. factory name and signature (``make_day_runner`` vs ``make_silvertail_runner``);
2. build-specific, open-ended scenario axes (0–5 today) — declared via
   :class:`OptionSpec`;
3. roster SHAPE — the adapter tags entities by role, killing the tuple-position
   coupling that makes ``validation.py`` un-generalizable;
4. sparse, disjoint level sets — each adapter reports its own
   :meth:`~BuildAdapter.available_levels`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import DayRunner
    from ..rng import SeededRNG
    from .config import RunConfig
    from .roster import Roster


@dataclass(frozen=True)
class OptionSpec:
    """One build scenario axis — §3.2's ``option_schema`` entry.

    ``values=None`` means the axis is open (any value of the right shape, e.g. a
    probability); otherwise the tuple is the closed set of allowed values.
    """

    name: str
    default: Any
    values: "tuple[Any, ...] | None" = None
    description: str = ""

    def check(self, build: str, value: Any) -> None:
        """Raise if ``value`` is not allowed on this axis."""
        if self.values is None:
            return
        # Membership by equality, not identity: bools and Nones must compare by
        # value so ``False in (None, True, False)`` behaves as written.
        if not any(value == allowed and type(value) is type(allowed) for allowed in self.values):
            raise ValueError(
                f"Build {build!r} axis {self.name!r} got {value!r}; "
                f"allowed: {list(self.values)}."
            )

    def describe(self) -> dict[str, Any]:
        return {
            "default": self.default,
            "values": list(self.values) if self.values is not None else None,
            "description": self.description,
        }


@runtime_checkable
class BuildAdapter(Protocol):
    """The per-build seam (§3.2)."""

    name: str

    def available_levels(self) -> list[int]:
        """Levels this build implements, ascending.  SPARSE — never a range."""

    def option_schema(self) -> dict[str, OptionSpec]:
        """Scenario axis name → spec.  Empty dict = the build has no axes."""

    def build(self, config: "RunConfig", rng: "SeededRNG") -> "tuple[DayRunner, Roster]":
        """Construct the runner and the role-tagged roster for one config."""

    def describe(self, config: "RunConfig") -> dict[str, Any]:
        """RESOLVED build parameters for the §4 provenance block.

        A pure read — it must not roll a die or mutate anything.  ``resolved`` vs
        ``config`` is the load-bearing distinction (§4): an option the caller left
        unset must be reported as the value ACTUALLY used, not as "default".
        """


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_REGISTRY: dict[str, BuildAdapter] = {}
_BUILTINS_LOADED = False


def register(adapter: BuildAdapter) -> BuildAdapter:
    """Add an adapter to the registry (idempotent re-registration is an error —
    two builds sharing a key would silently shadow one another)."""
    if adapter.name in _REGISTRY and _REGISTRY[adapter.name] is not adapter:
        raise ValueError(f"A different adapter is already registered as {adapter.name!r}.")
    _REGISTRY[adapter.name] = adapter
    return adapter


def get_adapter(name: str) -> BuildAdapter:
    _ensure_builtin_adapters()
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"No build adapter registered as {name!r}. Known: {available_builds()}."
        ) from None


def available_builds() -> list[str]:
    _ensure_builtin_adapters()
    return sorted(_REGISTRY)


def _ensure_builtin_adapters() -> None:
    """Import the shipped adapters on first lookup.

    Lazy so that importing ``config``/``roster`` does not drag in every build
    module (and its content YAML).  Guarded by its own flag rather than by
    ``if _REGISTRY`` so that a caller registering a custom adapter first does not
    suppress the built-ins.
    """
    global _BUILTINS_LOADED
    if _BUILTINS_LOADED:
        return
    _BUILTINS_LOADED = True
    from . import build_adapters  # noqa: F401  (import registers)
