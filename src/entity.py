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
        damage_multiplier: dict[str, float] | None = None,
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
        # FRACTIONAL per-type damage multiplier (enemy_model.md §5 — the mean-field
        # band `mult(t)`).  The third, CONTINUOUS layer of substrate #4: where
        # `damage_response` above is the binary D&D ×0.5/×2/×0, this is a real factor
        # in roughly [0, 2] — "the fraction of incoming type-t damage that LANDS
        # against the representative enemy of this CR band" (1 − 0.5·P_resist −
        # P_immune + P_vulnerable).  Blend-only mean-field turns the population's
        # binary resistances into one continuous multiplier (§3), so the average
        # enemy can resist fire 6.4/10 of the way.  INTRINSIC to the enemy dummy
        # (set at construction from its band, never swept — mirrors `damage_response`
        # the trait), read defender-side in resolve_damage AFTER the categorical
        # response.  Empty (the default everywhere) → inert → no baseline drift:
        # installing it IS the §7 res/imm/vuln-check toggle turning ON.
        self.damage_multiplier: dict[str, float] = dict(damage_multiplier or {})
        # Statuses installed by the cast_effect primitive (substrate #3), labelled
        # by effect_source: source → [status name, ...].  StatusSet is keyed by
        # status NAME (not source), so this index is what lets remove_effect drop a
        # cast's statuses together with the rest of its bundle when its source is
        # removed (e.g. a concentration break), rather than waiting for the
        # unconditional combat-boundary StatusSet.clear().
        self._effect_statuses: dict[str, list[str]] = {}
        # Summons (substrate #7 / 7a) this entity created via the cast_effect
        # `summons` payload, labelled by effect_source: source → [summon Entity, ...].
        # remove_effect(source) marks each `destroyed` so a controlled ally winks out
        # WITH the rest of its cast's bundle (a dropped concentration / combat sweep),
        # design.md §1.  The roster removal itself is done by the scheduler/runner
        # (Entity holds no roster reference); the flag is the Entity-level teardown.
        self._effect_summons: dict[str, list["Entity"]] = {}
        # Zones (substrate #7 / 7b) this entity created via the cast_effect `zones`
        # payload, labelled by effect_source: source → [Zone, ...].  remove_effect(
        # source) marks each `destroyed` so an emanation winks out WITH the rest of
        # its cast's bundle (a dropped concentration / combat sweep), design.md §1 —
        # mirroring _effect_summons for the 7a Actor case.  The scheduler holds the
        # live zone registry; this index is the Entity-level teardown hook.
        self._effect_zones: dict[str, list] = {}
        # Which abstract zone this entity occupies (design.md §3.1 zonal model;
        # substrate #7 / 7b).  Everything shares the implicit "melee" blob by default
        # (the literal mirrors zones.DEFAULT_ZONE — hard-coded here to avoid an import
        # cycle); a damaging emanation fires on occupants whose zone matches its
        # location, and `move_entity` (zones.py) changes it.
        self.zone: str = "melee"
        # Whether this entity has been destroyed (destroy_entity / a summon whose
        # source was removed).  A created Object/ally that has winked out; the
        # scheduler skips a destroyed entity's turns and a controller checks it before
        # commanding.  False for every omnipresent entity (character / enemy / party).
        self.destroyed: bool = False
        # Whether this entity WINKS OUT at 0 HP (substrate #7 / 7a summon survival).
        # The character / enemy / party use the threshold model (HP never gates turns),
        # so they leave this False.  A SUMMON (the primal companion) sets it True: when
        # cumulative damage drops it to 0 HP, take_damage marks it `destroyed` so it
        # stops acting / being commanded, and its DPR contribution disappears for the
        # rest of the combat (a dead summon does nothing).  This is the 0-HP trigger
        # that arms the already-present `destroyed` plumbing (scheduler skips destroyed
        # turns; a commander checks `destroyed` before ordering).
        self.dies_at_zero_hp: bool = False
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

        The ONE exception is a SUMMON (``dies_at_zero_hp``): a controlled ally
        winks out at 0 HP (substrate #7 / 7a summon survival).  Crossing to ≤ 0
        sets ``destroyed`` here — the single 0-HP trigger; everything downstream
        (the scheduler skipping its turns, the commander declining to order it)
        already reads ``destroyed``.  Non-summons are unaffected (threshold model).
        """
        self.hp -= amount
        log.info("%s takes %s damage → hp=%s/%s", self.name, amount, self.hp, self.max_hp)
        if self.dies_at_zero_hp and self.hp <= 0 and not self.destroyed:
            self.destroyed = True
            log.info("%s WINKS OUT at 0 HP (summon death)", self.name)

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

    def note_effect_summon(self, source: str, summon: "Entity") -> None:
        """Record that *summon* was created by the cast_effect labelled *source*
        (substrate #7 / 7a), so remove_effect winks it out when the source ends."""
        self._effect_summons.setdefault(source, []).append(summon)

    def note_effect_zone(self, source: str, zone: object) -> None:
        """Record that *zone* was created by the cast_effect labelled *source*
        (substrate #7 / 7b), so remove_effect winks it out (marks it destroyed) when
        the source ends — e.g. a dropped concentration ending Spirit Guardians."""
        self._effect_zones.setdefault(source, []).append(zone)

    def remove_effect(self, source: str) -> None:
        """Remove every payload a cast_effect installed under *source* — its
        ModifierStack modifiers, its damage-type response (substrate #4), any
        statuses it granted (substrate #3), any summons it created (substrate #7
        / 7a), and any zones it created (substrate #7 / 7b) — and stop tracking it
        for the combat sweep, clearing concentration if it held it.

        This is the single place a cast's whole bundle is torn down.  Both a
        concentration break (verbs._check_concentration) and the combat-boundary
        sweep route through it, so the non-modifier payloads (a radiant resistance,
        a granted status, a controlled ally) drop WITH the modifiers instead of
        leaking — the effect_source thread of design/buff_primitive.md.  Summons are
        marked `destroyed` here (the Entity-level teardown); the scheduler/runner
        does the actual roster removal (Entity holds no roster reference)."""
        self.remove_modifier(source)
        self._effect_damage_response.pop(source, None)
        for name in self._effect_statuses.pop(source, ()):
            self.statuses.remove(name)
        for summon in self._effect_summons.pop(source, ()):
            summon.destroyed = True
        for zone in self._effect_zones.pop(source, ()):
            zone.destroyed = True
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

        The reserved key ``"_all"`` is a catch-all that applies to ANY typed hit —
        "resistance to all damage" (Warding Bond, Rage; substrate #7 / 7c, the
        session-19 deferral).  Both the type-specific key and ``"_all"`` feed the
        kinds set, so the same dominate/cancel rules apply (e.g. an ``"_all"``
        resistance + a type-specific vulnerability still cancel).
        """
        if damage_type is None:
            return None
        kinds: set[str] = set()
        for key in (damage_type, "_all"):
            intrinsic = self.damage_response.get(key)
            if intrinsic:
                kinds.add(intrinsic)
        for responses in self._effect_damage_response.values():
            for key in (damage_type, "_all"):
                kind = responses.get(key)
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

    def damage_multiplier_for(self, damage_type: str | None) -> float | None:
        """The effective FRACTIONAL multiplier for *damage_type* (enemy_model.md §5
        `mult(t)`), or None if no fractional profile applies to this type.

        Distinct from `damage_response_for` (the binary kind): this is the continuous
        mean-field band factor.  None damage_type (untyped weapon hits) → None: an
        untyped hit declares no type to price, so it is never mitigated.  A target with
        an empty profile (the default — res/imm/vuln check OFF) also returns None, so
        resolve_damage's fractional step is inert on every existing path.
        """
        if damage_type is None or not self.damage_multiplier:
            return None
        return self.damage_multiplier.get(damage_type)

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Entity({self.name!r}, hp={self.hp}/{self.max_hp})"
