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
    damage_response:
        Optional INTRINSIC damage-type responses (a monster trait) — a
        {damage_type: kind} dict where kind is "resistance" / "vulnerability" /
        "immunity", e.g. {"fire": "resistance"} for a fire-resistant enemy.
        Read defender-side in resolve_damage (substrate #4).  Cast-installed
        responses (Fire Shield's resist-cold/fire) are added separately via
        add_damage_response and swept at the combat boundary.
    """

    def __init__(
        self,
        name: str,
        hp: int | float,
        base_stats: dict[str, int | float | tuple] | None = None,
        resources: ResourcePool | None = None,
        damage_response: dict[str, str] | None = None,
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
        # Sources of combat-clock buffs installed via the cast_effect primitive
        # (design/buff_primitive.md).  Combats restart the round counter, so these
        # cannot tick-expire — they are swept at each combat boundary by
        # clear_combat_buffs (mirrors StatusSet.clear).  Capability buffs carry no
        # modifier and are not tracked here (the policy resets its own flag).
        self._combat_buff_sources: set[str] = set()
        # Damage-type responses (substrate #4 — design/buff_primitive.md): how this
        # entity reacts to INCOMING damage of a given type, read defender-side in
        # resolve_damage.  Two layers, combined by damage_response_for:
        #   - `damage_response`: INTRINSIC (a monster trait, e.g. fire resistance),
        #     set at construction and never swept.
        #   - `_effect_damage_response`: source → {type: kind} payloads installed by
        #     the cast_effect primitive (Fire Shield's resist-cold/fire), labelled
        #     by effect_source and swept at the combat boundary like the modifiers.
        self.damage_response: dict[str, str] = dict(damage_response or {})
        self._effect_damage_response: dict[str, dict[str, str]] = {}
        # Statuses installed by the cast_effect primitive (substrate #3), labelled
        # by effect_source: source → [status name, ...].  StatusSet is keyed by
        # status NAME (not source), so this index is what lets remove_effect drop a
        # cast's statuses together with the rest of its bundle when its source is
        # removed (e.g. a concentration break), rather than waiting for the
        # unconditional combat-boundary StatusSet.clear().
        self._effect_statuses: dict[str, list[str]] = {}
        # Cumulative telemetry (design §8 outputs): concentration checks forced
        # by incoming damage and how many broke a spell.  Never auto-reset;
        # callers diff or average across runs.
        self.concentration_checks: int = 0
        self.concentration_breaks: int = 0
        # Saving throws this entity was forced to MAKE and how many it FAILED
        # (design §8 outputs — "saves forced / failed by type").  Incremented by
        # resolve_save_damage when this entity is the target of a save-for-damage
        # spell.  Never auto-reset; callers diff or average across runs.
        self.saving_throws_made: int = 0
        self.saving_throws_failed: int = 0
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

    def note_combat_buff(self, source: str) -> None:
        """Record a combat-clock cast_effect source so its modifiers are swept at
        the next combat boundary (see clear_combat_buffs)."""
        self._combat_buff_sources.add(source)

    def note_effect_status(self, source: str, name: str) -> None:
        """Record that status *name* was installed by the cast_effect labelled
        *source*, so remove_effect can drop it when the source is removed."""
        self._effect_statuses.setdefault(source, []).append(name)

    def remove_effect(self, source: str) -> None:
        """Remove every payload a cast_effect installed under *source* — its
        ModifierStack modifiers, its damage-type response (substrate #4), and any
        statuses it granted (substrate #3) — and stop tracking it for the combat
        sweep, clearing concentration if it held it.

        This is the single place a cast's whole bundle is torn down.  Both a
        concentration break (verbs._check_concentration) and the combat-boundary
        sweep route through it, so the non-modifier payloads (a radiant resistance,
        a granted status) drop WITH the modifiers instead of leaking — the
        effect_source thread of design/buff_primitive.md."""
        self.remove_modifier(source)
        self._effect_damage_response.pop(source, None)
        for name in self._effect_statuses.pop(source, ()):
            self.statuses.remove(name)
        self._combat_buff_sources.discard(source)
        if self.concentration == source:
            self.concentration = None

    def clear_combat_buffs(self) -> None:
        """Remove all combat-clock cast_effect payloads (and clear concentration if
        a swept source held it).  Called at each combat boundary (day_runner),
        mirroring StatusSet.clear() — combat-clock effects cannot tick-expire
        because each combat restarts the round counter."""
        for source in list(self._combat_buff_sources):
            self.remove_effect(source)

    # ------------------------------------------------------------------
    # Damage-type responses (substrate #4 — resistance / vuln / immunity)
    # ------------------------------------------------------------------

    def add_damage_response(self, source: str, responses: dict[str, str]) -> None:
        """Install a cast_effect damage-type response payload under *source*.

        `responses` is a {damage_type: kind} dict (kind ∈ resistance /
        vulnerability / immunity), e.g. {"fire": "resistance"} for Fire Shield's
        chill mode.  Labelled by `source` (the effect_source) and noted for the
        combat-boundary sweep, so it clears with the rest of the cast's payload.
        """
        self._effect_damage_response[source] = dict(responses)
        self.note_combat_buff(source)

    def damage_response_for(self, damage_type: str | None) -> str | None:
        """The effective response to *damage_type* — "resistance" / "vulnerability"
        / "immunity" / None — combining the intrinsic trait and every installed
        cast_effect payload.

        2024 RAW combination: immunity dominates; resistance and vulnerability to
        the same type CANCEL (net no change → None); otherwise whichever is
        present.  Multiple instances of the same kind don't stack (resistance
        halves once).  None damage_type (untyped weapon hits) → no response.
        """
        if damage_type is None:
            return None
        kinds: set[str] = set()
        intrinsic = self.damage_response.get(damage_type)
        if intrinsic:
            kinds.add(intrinsic)
        for responses in self._effect_damage_response.values():
            kind = responses.get(damage_type)
            if kind:
                kinds.add(kind)
        if "immunity" in kinds:
            return "immunity"
        has_res = "resistance" in kinds
        has_vuln = "vulnerability" in kinds
        if has_res and has_vuln:
            return None  # cancel (2024 RAW)
        if has_res:
            return "resistance"
        if has_vuln:
            return "vulnerability"
        return None

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Entity({self.name!r}, hp={self.hp}/{self.max_hp})"
