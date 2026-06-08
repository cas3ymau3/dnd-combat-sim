"""
entity.py — Entity: the universal bag-of-state for characters and enemies.

An Entity owns:
  - identity (name, id)
  - current and max HP
  - a base_stats dict of unmodified numbers
  - a ModifierStack for computing effective stats on demand

Nothing combat-specific lives here.  No attack logic, no spell tracking.
The Entity is a passive data holder; the scheduler and verbs act on it.
"""

from __future__ import annotations

import itertools
import logging
from dataclasses import dataclass, field

from .modifiers import Modifier, ModifierStack

log = logging.getLogger(__name__)

_id_counter = itertools.count(1)


class Entity:
    """A character, enemy, or any game object that participates in combat.

    Parameters
    ----------
    name:
        Human-readable label, e.g. "Fighter", "Dummy", "Goblin".
    hp:
        Starting (and max) hit points.  Pass math.inf for the infinite-HP
        target dummy.
    base_stats:
        Dict of unmodified stats.  Common keys:
          "attack_bonus"  — added to d20 attack rolls
          "ac"            — armor class (target's defence)
          "damage_dice"   — (n, sides) tuple, e.g. (1, 8) for 1d8
          "damage_bonus"  — flat bonus added after the dice pool
          "spell_save_dc" — DC for saving throws imposed on others
          "str_save"      — this entity's Strength saving throw bonus
          ... etc.
        Any key can be queried via entity.stat(); missing keys return 0.
    """

    def __init__(
        self,
        name: str,
        hp: int | float,
        base_stats: dict[str, int | float | tuple] | None = None,
    ) -> None:
        self.id: int = next(_id_counter)
        self.name = name
        self.hp: int | float = hp
        self.max_hp: int | float = hp
        self.base_stats: dict[str, int | float | tuple] = base_stats or {}
        self.modifiers = ModifierStack()
        log.debug("Entity created: %s (id=%d, hp=%s)", name, self.id, hp)

    # ------------------------------------------------------------------
    # Stat access — always go through here, never read base_stats directly
    # ------------------------------------------------------------------

    def stat(self, name: str, tick: tuple | None = None, phase: str | None = None) -> int | float:
        """Return the effective value of *name* at *tick*, after all modifiers.

        For non-numeric stats (e.g. "damage_dice" which is a tuple), modifiers
        are not applied — the raw base value is returned.  Numeric stats are
        folded through the modifier stack.

        Returns 0 for any stat not in base_stats (so callers don't need to
        guard against missing keys).
        """
        base = self.base_stats.get(name, 0)
        if not isinstance(base, (int, float)):
            # Tuple or other non-numeric — return raw, no modifier folding
            return base
        return self.modifiers.compute(name, base, tick=tick, phase=phase)

    # ------------------------------------------------------------------
    # HP tracking
    # ------------------------------------------------------------------

    def take_damage(self, amount: int | float) -> None:
        """Reduce HP by *amount*.  Clamps at 0 (no negative HP)."""
        self.hp = max(0, self.hp - amount)
        log.info("%s takes %s damage → hp=%s/%s", self.name, amount, self.hp, self.max_hp)

    def heal(self, amount: int | float) -> None:
        """Restore HP by *amount*.  Clamps at max_hp."""
        self.hp = min(self.max_hp, self.hp + amount)
        log.info("%s heals %s → hp=%s/%s", self.name, amount, self.hp, self.max_hp)

    @property
    def is_alive(self) -> bool:
        return self.hp > 0

    # ------------------------------------------------------------------
    # Modifier pass-throughs (convenience)
    # ------------------------------------------------------------------

    def add_modifier(self, modifier: Modifier) -> None:
        self.modifiers.add(modifier)

    def remove_modifier(self, source: str) -> int:
        return self.modifiers.remove(source)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Entity({self.name!r}, hp={self.hp}/{self.max_hp})"
