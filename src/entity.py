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
from .resources import ResourcePool
from .statuses import StatusSet

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
    resources:
        Optional ResourcePool of persistent limited-use resources (spell slots,
        ki, war priest charges, etc.).  Defaults to an empty pool.
        Turn-level action economy (action, bonus_action, reaction) is managed
        by the Scheduler and is NOT stored here.
    """

    def __init__(
        self,
        name: str,
        hp: int | float,
        base_stats: dict[str, int | float | tuple] | None = None,
        resources: ResourcePool | None = None,
    ) -> None:
        self.id: int = next(_id_counter)
        self.name = name
        self.hp: int | float = hp
        self.max_hp: int | float = hp
        self.base_stats: dict[str, int | float | tuple] = base_stats or {}
        self.modifiers = ModifierStack()
        self.resources: ResourcePool = resources if resources is not None else ResourcePool()
        self.statuses: StatusSet = StatusSet()
        # Concentration is global-per-entity (only one effect at a time), and it
        # is NOT tick-expiring — it lasts until the spell ends or a failed save
        # drops it — so it lives here as a dedicated first-class field rather
        # than in the tick-expiring StatusSet.  Value is the modifier source to
        # drop when concentration breaks (e.g. "bless"), or None.
        self.concentration: str | None = None
        # Cumulative telemetry (design §8 outputs): concentration checks forced
        # by incoming damage and how many broke a spell.  Never auto-reset;
        # callers diff or average across runs.
        self.concentration_checks: int = 0
        self.concentration_breaks: int = 0
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

    def roll_bonus(self, name: str, rng, tick: tuple | None = None) -> int:
        """Rolled contribution to *name* from dice-modifiers (e.g. Bless +1d4).

        Resolution-only: this rolls dice via the RNG, so it must be called from
        the attack/save resolvers, NEVER from policy.decide().  The pure stat()
        above stays dice-free.  Returns 0 if no dice-modifiers apply.
        """
        return self.modifiers.roll_dice(name, rng, tick=tick)

    # ------------------------------------------------------------------
    # HP tracking
    # ------------------------------------------------------------------

    def take_damage(self, amount: int | float) -> None:
        """Reduce HP by *amount*.  HP can go negative (threshold model).

        The sim never gates turn access on HP — entities always act for the
        full scheduled rounds.  HP is a tracker; use is_functionally_dead to
        detect death-proc thresholds (e.g. hungering hex on enemy kill).
        """
        self.hp -= amount
        log.info("%s takes %s damage → hp=%s/%s", self.name, amount, self.hp, self.max_hp)

    def heal(self, amount: int | float) -> None:
        """Restore HP by *amount*.  Clamps at max_hp."""
        self.hp = min(self.max_hp, self.hp + amount)
        log.info("%s heals %s → hp=%s/%s", self.name, amount, self.hp, self.max_hp)

    @property
    def is_functionally_dead(self) -> bool:
        """True when cumulative damage has met or exceeded max_hp.

        Does NOT stop the entity from acting — the scheduler always runs every
        entity for the full max_rounds.  Use this in on_kill trigger subscribers
        to proc death effects (e.g. hungering hex, kill-conditional abilities).
        """
        return self.hp <= 0

    @property
    def is_alive(self) -> bool:
        """Kept for backward compatibility.  Prefer is_functionally_dead."""
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
