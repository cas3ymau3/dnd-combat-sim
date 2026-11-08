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

THE FIVE METHODS AND WHAT EACH ABSORBS
--------------------------------------
Counted against the PROTOCOL rather than against §2's prose, because the protocol is
the thing that can be counted mechanically.  §2 enumerates FOUR axes of variance,
which was the whole of it when this module was written; step 8b added a fifth that
§2's factory table cannot show (see axis 5).  The divergence sat open from s56 to s61
as "four axes, five methods" — recorded here rather than silently renumbered.

1. **Factory name and signature** differ (``make_day_runner`` vs
   ``make_silvertail_runner``) — absorbed by :meth:`~BuildAdapter.build`.
2. **Scenario axes** are build-specific and open-ended (0–5 today) — declared via
   :class:`OptionSpec` and reported by :meth:`~BuildAdapter.option_schema`.
3. **Roster SHAPE** differs — :meth:`~BuildAdapter.build` tags entities by role,
   killing the tuple-position coupling that made ``src/validation.py``
   un-generalizable (that module was deleted in s52; the coupling is the record).
4. **Sparse, disjoint level sets** — each adapter reports its own
   :meth:`~BuildAdapter.available_levels`.
5. **Which save abilities the build's own PLAN can force** (§13's saves channel,
   added at step 8b) — :meth:`~BuildAdapter.forced_save_abilities`.  This one is
   invisible in §2's factory table because it is a property of the POLICY, not of the
   factory signature, and a Python ``decide()`` cannot be inspected for it; that is
   exactly why it is declared.  See the method's own docstring.

:meth:`~BuildAdapter.describe` is the fifth method but NOT a sixth axis: it is the §4
provenance obligation taken over all five, reporting the RESOLVED value of each.
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

    def forced_save_abilities(self, config: "RunConfig") -> "frozenset[str]":
        """Save abilities this build's OWN plan can force, in the §13 saves channel.

        **Why this is DECLARED and not derived (s49's rule, applied at step 8b).**
        The saves channel pools both directions — ``telemetry.record_save`` is called
        from ``resolve_save_damage`` and ``resolve_control_save``, neither keyed by
        actor, and ``saves_forced_per_round``'s own definition says so.  So a cell
        like ``[dex_save|*]`` has TWO producers: the enemy forcing a save on the
        character, and the build forcing one on the enemy.  Per-cell availability
        (§3.4's three states) has to consult both, or it declares a cell structurally
        empty while real data flows into it.

        The enemy side is readable before day 1 — ``RunContext.enemy`` resolves the
        band's save weights.  The build side is NOT: the plan is a Python policy, and
        no amount of inspection tells the framework which ``Choice`` it will emit.
        The two also vary independently (the enemy's abilities move with the band, the
        build's with its level and its options), which is exactly the independence
        test that makes this a declaration rather than a derivation.

        **OVER-INCLUSIVE IS SAFE; UNDER-INCLUSIVE HIDES DATA.**  Naming an ability the
        plan merely MIGHT force leaves its cell available, which is the behaviour
        before this method existed.  Omitting one the plan does force marks the cell
        unavailable and the collection is skipped, so a real measurement is thrown
        away.  Declare the union over everything the plan can do at this config and do
        not try to be precise about which round or which resource state.

        **Only what reaches the CHANNEL counts, which is narrower than "saves this
        build forces".**  Two of the engine's five ``resolve_saving_throw`` call sites
        write to no channel at all: a buff's ``application_save``
        (``scheduler._handle_cast_effect``) and Sanctuary's ``negate_save``
        (``resolve_attack_roll``).  Starfire's Sanctuary rolls a ``wis_save`` that no
        metric can see, so ``wis_save`` is NOT declared for it — declaring it would
        keep an empty cell available on the strength of a save the channel never
        records.  See §8's coverage map.

        Return an empty frozenset for a build that forces none.  That is not a
        degenerate case: it is War Angel, and it is the value that makes this whole
        mechanism fire.
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
