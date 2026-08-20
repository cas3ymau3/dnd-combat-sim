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

#: What an entity does at 0 HP (design/healing.md §6).  A CLOSED three-value
#: vocabulary — extending it is a deliberate act, like adding a verb.
#:   "threshold" — nothing; `hp` is a signed balance nothing reads (the default)
#:   "vanishes"  — removed permanently (`destroyed`), unhealable once gone
#:   "downed"    — stops acting, `hp` floored at 0, healable back into the fight
ZERO_HP_CATEGORIES = ("threshold", "vanishes", "downed")


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
        # What happens to this entity AT 0 HP — design/healing.md §6.  A three-way
        # enum, because a boolean cannot express the corpus:
        #   "threshold" — nothing.  HP is a signed balance that never gates turns.
        #                 The character / enemy / party model, and the DEFAULT.
        #   "vanishes"  — removed PERMANENTLY (`destroyed`).  A summon-spell creature,
        #                 and the 2024 primal companion (its revival needs a Magic
        #                 action, a slot and 1 MINUTE, so it can never be healed back
        #                 inside a 4-round combat — healing.md §11.3).
        #   "downed"    — stops acting but REMAINS, `hp` floored at 0, and healing it
        #                 above 0 returns it to the fight.  A REVERSIBLE state, which
        #                 is why it cannot ride on `destroyed` (that is permanent).
        # `dies_at_zero_hp` below is the legacy boolean view of this field, kept so
        # every existing call site reads/writes the enum unchanged.
        self.zero_hp_category: str = "threshold"
        # The reversible half of "downed" (see above).  Distinct from `destroyed`:
        # a downed entity is still in the roster, still healable, and clears this
        # flag the moment a heal lifts it above 0 HP.
        self.downed: bool = False
        # Optional ON-ZERO effect (healing.md §6 case 3 — the reanimator artificer's
        # companion fires a death effect but is still revivable).  A callable taking
        # this entity, invoked ONCE by take_damage on the crossing to <= 0 HP.  It is
        # RESOLUTION-side data supplied by a build, never a policy decision.
        self.on_zero_hp = None
        # This entity's Hit Dice SHAPE (die sizes + CON modifier + which of the two
        # §7 rules applies) — a ``healing.HitDiceSpec``, or None for an entity with
        # no Hit Dice (the enemy dummy; a companion whose statblock lists none, in
        # which case the rule simply degrades to "never heals this way" rather than
        # needing a special case).  The COUNT is NOT here: it lives in
        # ``resources["hit_dice"]``, the single source of truth, which already
        # restores on a long rest and which the Starfire Scion already spends from
        # for Fueled Spellfire.
        self.hit_dice = None
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
        """Reduce HP by *amount*, then apply this entity's 0-HP CATEGORY.

        The sim never gates turn access on HP for a ``threshold`` entity — it
        always acts for the full scheduled rounds, and its HP is a signed balance
        that may go arbitrarily negative.  Use is_functionally_dead to detect
        death-proc thresholds (e.g. hungering hex on enemy kill).

        The two summon categories DO read HP (healing.md §6):
          - ``vanishes`` → crossing to <= 0 sets ``destroyed`` (permanent), the
            single 0-HP trigger; everything downstream (the scheduler skipping its
            turns, a commander declining to order it) reads that flag.
          - ``downed``  → crossing to <= 0 FLOORS ``hp`` at 0 and sets ``downed``
            (reversible), so a later heal can lift it back into the fight.  The
            floor is required: without it a heal after a large hit would have to
            climb out of a 30-point hole before reviving anything.

        An ``on_zero_hp`` effect, if set, fires ONCE on the crossing, for either
        summon category (§6 case 3).
        """
        self.hp -= amount
        log.info("%s takes %s damage → hp=%s/%s", self.name, amount, self.hp, self.max_hp)
        if self.hp > 0:
            return
        if self.zero_hp_category == "vanishes" and not self.destroyed:
            self.destroyed = True
            log.info("%s WINKS OUT at 0 HP (summon death)", self.name)
            self._fire_on_zero_hp()
        elif self.zero_hp_category == "downed" and not self.downed:
            self.hp = 0
            self.downed = True
            log.info("%s is DOWNED at 0 HP (healable back)", self.name)
            self._fire_on_zero_hp()

    def _fire_on_zero_hp(self) -> None:
        if self.on_zero_hp is not None:
            self.on_zero_hp(self)

    def heal(self, amount: int | float) -> int | float:
        """Restore HP by *amount*, capped per this entity's 0-HP CATEGORY.

        The cap follows the CATEGORY, not the roster role (healing.md §4):

          - ``threshold`` → **no cap**.  Its ``hp`` is a signed balance that
            nothing in the engine reads, so ``max_hp`` is not a ceiling on it and
            capping would make a heal's recorded value depend on when damage
            happened to land relative to it — a sequencing artifact (§2).  This
            covers characters, party allies, and the default immortal summon.
          - ``vanishes`` / ``downed`` → **capped at max_hp**, because there ``hp``
            is live state gating death and turn access; healing past ``max_hp``
            would make the creature genuinely tankier than it can be.

        Healing a ``downed`` entity above 0 clears the flag and returns it to the
        fight — the reversibility that ``destroyed`` cannot express.  A
        ``vanishes`` summon that has already gone is beyond help and absorbs no
        healing at all, which is what makes the ledger's numbers honest.

        Returns the AMOUNT ACTUALLY APPLIED, which is what the ledger records —
        not the amount rolled.  A vanished summon absorbs 0; a capped one absorbs
        only its deficit.  Reporting the applied figure is what keeps "healing
        provided by the summon" honest instead of a gross number that overstates
        what happened.
        """
        if self.destroyed or amount <= 0:
            return 0
        before = self.hp
        if self.zero_hp_category == "threshold":
            self.hp += amount
        else:
            self.hp = min(self.max_hp, self.hp + amount)
            if self.downed and self.hp > 0:
                self.downed = False
                log.info("%s is back up (healed above 0 HP)", self.name)
        applied = self.hp - before
        log.info("%s heals %s (applied %s) → hp=%s/%s",
                 self.name, amount, applied, self.hp, self.max_hp)
        return applied

    # -- the legacy boolean view of zero_hp_category ---------------------
    # Every existing call site (day_runner's long rest, silvertail's factory, the
    # summon-survival tests) speaks in "does this wink out at 0 HP?".  Keeping that
    # as a property over the enum means the enum lands WITHOUT touching them, and
    # `dies_at_zero_hp = True` still means exactly what it meant: "vanishes".

    @property
    def dies_at_zero_hp(self) -> bool:
        return self.zero_hp_category == "vanishes"

    @dies_at_zero_hp.setter
    def dies_at_zero_hp(self, value: bool) -> None:
        self.zero_hp_category = "vanishes" if value else "threshold"

    @property
    def is_out_of_action(self) -> bool:
        """True when this entity takes no turns: destroyed (permanent) or downed
        (reversible).  The single predicate the scheduler and any commander read,
        so adding ``downed`` did not need a second check at every site."""
        return self.destroyed or self.downed

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
