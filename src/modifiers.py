"""
modifiers.py — Modifier dataclass and ModifierStack.

Design contract (from CLAUDE.md §6):
  "Modifier stack, not mutated stats.  Effective stats are computed on demand
   by folding active modifiers over a base value.  Adding/removing a buff =
   pushing/popping a modifier, never editing a number in place."

A Modifier carries:
  - which stat it affects
  - which damage-resolution phase it belongs to (None for non-damage stats)
  - the adjustment: either a flat int/float OR a callable that takes the
    running value and returns a new value (enables multiplicative, conditional,
    and replace-style modifiers)
  - a source string so modifiers can be removed by name (e.g. "bless",
    "rage", "shield_spell")
  - an optional expiry tick — the modifier is ignored at or after this tick

ModifierStack.compute(stat, base, tick) folds all active modifiers for that
stat left-to-right over the base value and returns the result.  Callers never
mutate base stats; they always go through compute().
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from typing import Callable

log = logging.getLogger(__name__)

# A modifier value is either a flat number or a function (running_value → new_value).
ModifierValue = int | float | Callable[[int | float], int | float]


@dataclass
class Modifier:
    """A single buff, debuff, or transformation applied to one stat.

    Parameters
    ----------
    stat:
        The stat this modifier affects, e.g. "attack_bonus", "ac",
        "damage_bonus".  Must match the key used in Entity.base_stats and
        in ModifierStack.compute() calls.
    value:
        Flat number (added to running total) OR a callable that transforms
        the running total.  Use a callable for multiplicative effects,
        conditional bonuses, or "replace with X" overrides.
    source:
        Human-readable name of the ability/feature granting this modifier,
        e.g. "bless", "rage", "shield_spell".  Used to remove the modifier
        when it expires or is consumed.
    phase:
        Damage-resolution phase this modifier belongs to (see ability_schema.md
        §phase tags).  None for non-damage stats (AC, attack_bonus, etc.).
        When computing damage, only modifiers whose phase matches the current
        phase in the resolution pipeline are applied.
    expires_at:
        Tick at or after which this modifier is inactive.  None means it
        never expires (e.g. a class feature like Rage must be removed
        explicitly via ModifierStack.remove()).
    dice:
        Optional (n, sides) of a ROLLED contribution to the stat — e.g.
        Bless's +1d4 to attack rolls and saves.  This part is NEVER folded by
        compute() (which must stay pure/dice-free, since the policy reads it);
        it is summed only on a resolution-only path via ModifierStack.roll_dice
        / Entity.roll_bonus, called by the attack/save resolvers with the RNG.
        A modifier may carry both `value` (flat) and `dice` (rolled); Bless
        carries value=0 + dice=(1, 4).  None = no rolled contribution.
    """

    stat: str
    value: ModifierValue
    source: str
    phase: str | None = None
    expires_at: tuple | None = None  # Tick tuple (round, turn_index, sequence)
    dice: tuple[int, int] | None = None  # (n, sides) of a rolled contribution

    def is_active(self, tick: tuple | None) -> bool:
        """Return True if this modifier should be applied at *tick*.

        If tick is None (e.g. during setup before the sim starts), expiry is
        ignored and the modifier is always considered active.
        """
        if self.expires_at is None or tick is None:
            return True
        return tick < self.expires_at


class ModifierStack:
    """Ordered collection of Modifiers with a fold-left compute interface.

    Usage
    -----
    stack = ModifierStack()
    stack.add(Modifier(stat="attack_bonus", value=2, source="bless"))
    effective_bonus = stack.compute("attack_bonus", base=5, tick=current_tick)
    # → 7
    """

    def __init__(self) -> None:
        self._modifiers: list[Modifier] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, modifier: Modifier) -> None:
        """Push a modifier onto the stack."""
        self._modifiers.append(modifier)
        log.debug("Modifier added: %s (+%s to %s)", modifier.source, modifier.value, modifier.stat)

    def remove(self, source: str) -> int:
        """Remove all modifiers with the given source name.

        Returns the number of modifiers removed (0 if none found).
        """
        before = len(self._modifiers)
        self._modifiers = [m for m in self._modifiers if m.source != source]
        removed = before - len(self._modifiers)
        if removed:
            log.debug("Modifier removed: source=%s (%d entries)", source, removed)
        return removed

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def compute(
        self,
        stat: str,
        base: int | float,
        tick: tuple | None = None,
        phase: str | None = None,
    ) -> int | float:
        """Fold all active modifiers for *stat* (and optionally *phase*) over *base*.

        Parameters
        ----------
        stat:
            Which stat to compute.
        base:
            The entity's unmodified base value for this stat.
        tick:
            Current simulation tick (round, turn_index, sequence).  Used to
            filter out expired modifiers.  Pass None during setup.
        phase:
            If provided, only modifiers whose phase matches (or whose phase
            is None) are included.  Pass None for non-damage stats so all
            modifiers for that stat are included regardless of their phase tag.
        """
        active = [
            m for m in self._modifiers
            if m.stat == stat
            and m.is_active(tick)
            and (phase is None or m.phase is None or m.phase == phase)
        ]

        def _apply(running: int | float, mod: Modifier) -> int | float:
            if callable(mod.value):
                return mod.value(running)
            return running + mod.value

        result = functools.reduce(_apply, active, base)
        log.debug(
            "compute(%s, base=%s, tick=%s, phase=%s) → %s  [%d modifier(s)]",
            stat, base, tick, phase, result, len(active),
        )
        return result

    def roll_dice(self, stat: str, rng, tick: tuple | None = None) -> int:
        """Sum the ROLLED contribution of all active dice-modifiers for *stat*.

        This is the resolution-only counterpart to compute(): it rolls each
        active modifier's `dice` (via the seeded RNG) and returns the total.
        Kept SEPARATE from compute() so the pure stat() the policy reads never
        rolls a die.  Called by the attack/save resolvers, never by decide().

        Returns 0 if no dice-modifiers are active for this stat.
        """
        total = 0
        for m in self._modifiers:
            if m.stat == stat and m.dice is not None and m.is_active(tick):
                n, sides = m.dice
                total += sum(rng.roll(n, sides))
        return total

    def active_modifiers(self, tick: tuple | None = None) -> list[Modifier]:
        """Return all currently active modifiers (for inspection/debugging)."""
        return [m for m in self._modifiers if m.is_active(tick)]
