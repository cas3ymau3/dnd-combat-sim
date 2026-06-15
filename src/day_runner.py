"""
day_runner.py — DayRunner: orchestrates one full adventuring day.

Design contract (design.md §2, PROGRESS.md):
  One adventuring day = long rest → 4 combats → long rest.
  One short rest occurs during one of the three inter-combat intervals.
  Each combat is run by a fresh Scheduler for rounds_per_combat rounds.
  Entities and their resource pools persist across combats; only SR/LR events
  reset resources.  HP carries over (threshold model — never gates turns).

Short rest placement rule (from model_setup_notes.md):
  - Compute three inter-combat intervals (each combat lasts 1 minute).
  - If interval 2 (between combats 2 and 3) is ≥ 60 minutes → SR there.
  - Otherwise randomly pick interval 1 or interval 3 with equal probability.
    (Given how combat times are sampled, if interval 2 < 60 then both 1 and
    3 are guaranteed ≥ 60, so this is always valid.)

Combat timing:
  - Day = 960 minutes (16h of adventuring after an 8h long rest).
  - Each quarter-day (240 min) contains exactly one combat, start time
    sampled uniformly from that quarter:
      Combat 1: t ∈ [1, 239]
      Combat 2: t ∈ [240, 479]
      Combat 3: t ∈ [480, 719]
      Combat 4: t ∈ [720, 960]

Out-of-combat actions (e.g. Prayer of Healing):
  An optional `between_combats` hook is called after each combat with a
  BetweenCombatsContext.  The hook can fire PoH or other out-of-combat
  spells by mutating entity state and resource pools directly.  This is
  where daily plan logic (cast PoH in interval 3 if slot available) lives.
  The hook is None by default — no out-of-combat actions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, TYPE_CHECKING

from .scheduler import Scheduler

if TYPE_CHECKING:
    from .entity import Entity
    from .policy import Policy
    from .rng import SeededRNG

log = logging.getLogger(__name__)

# Combat start-time windows: (inclusive_start, inclusive_end) per quarter-day.
_COMBAT_WINDOWS: list[tuple[int, int]] = [
    (1, 239),
    (240, 479),
    (480, 719),
    (720, 960),
]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CombatResult:
    """Results from a single combat encounter."""
    combat_num: int                             # 1–4
    damage_log: list[int]                       # total damage dealt per round
    damage_received: dict[int, list[int]]       # entity_id → damage per round


@dataclass
class DayResult:
    """Results from one full adventuring day."""
    combats: list[CombatResult]
    sr_after_combat: int        # which combat (1–3) the short rest follows
    combat_times: list[int]     # sampled start-minute for each of the 4 combats

    # Convenience aggregates
    @property
    def total_damage(self) -> int:
        return sum(sum(c.damage_log) for c in self.combats)

    @property
    def damage_by_combat(self) -> list[int]:
        return [sum(c.damage_log) for c in self.combats]

    @property
    def damage_by_round(self) -> list[int]:
        """Flat list of per-round damage across all combats in order."""
        rounds = []
        for c in self.combats:
            rounds.extend(c.damage_log)
        return rounds

    def damage_received_by(self, entity_id: int) -> int:
        """Total damage dealt TO a specific entity across the day.

        For DPR we want the character's output = damage taken by the dummy.
        Through L12 this equals total_damage (only the character deals damage);
        from L13 the enemy strikes back, so DPR must read the dummy's column
        specifically rather than the all-sources total.
        """
        return sum(
            sum(c.damage_received.get(entity_id, []))
            for c in self.combats
        )


# ---------------------------------------------------------------------------
# Between-combats hook context
# ---------------------------------------------------------------------------

@dataclass
class BetweenCombatsContext:
    """Passed to the between_combats hook after each combat.

    The hook uses this to decide whether to fire out-of-combat actions
    (e.g. cast Prayer of Healing).

    Fields
    ------
    after_combat_num:
        Which combat just finished (1–4).
    sr_after_combat:
        Which combat the SR follows this day (1–3).  Hook can compare
        after_combat_num to decide whether PoH is appropriate.
    interval_length:
        Minutes available before the next combat (or end of day for combat 4).
        Minimum 10 min required to cast Prayer of Healing.
    entities:
        The full entity list — hook may call entity.resources.restore_sr()
        or entity.resources.consume() directly.
    rng:
        The shared RNG — hook uses this if PoH healing needs dice rolled.
    """
    after_combat_num: int
    sr_after_combat: int
    interval_length: int
    entities: list["Entity"]
    rng: "SeededRNG"


# Type alias for the hook.
BetweenCombatsHook = Callable[[BetweenCombatsContext], None]


# ---------------------------------------------------------------------------
# Before-combat hook context + day-clock buff duration tracking
# ---------------------------------------------------------------------------

@dataclass
class BeforeCombatContext:
    """Passed to the before_combat hook just before each combat starts.

    This is the mirror of BetweenCombatsContext, and the home for pre-combat /
    out-of-combat buffs whose DURATION lives on the DAY CLOCK (minutes) rather
    than the combat clock — e.g. Magic Weapon (60 min, non-concentration).  The
    hook decides whether to (re)cast such buffs and syncs the entities' modifier
    stacks to whatever is active at this combat's start-minute.  See PROGRESS.md
    "Out-of-combat buffs via the DAY CLOCK".

    Fields
    ------
    combat_num:
        Which combat is about to run (1–4).
    combat_start_minute:
        This combat's start time on the day clock (minutes since long rest).
        A day-clock buff covers this combat iff it is active at this minute.
    combat_times:
        All four sampled combat start-minutes — lets the hook reason about
        whether a buff cast now will persist into later combats.
    entities:
        The full entity list — hook applies/removes modifiers directly.
    rng:
        The shared RNG (for any randomized pre-combat choice).
    """
    combat_num: int
    combat_start_minute: int
    combat_times: list[int]
    entities: list["Entity"]
    rng: "SeededRNG"


BeforeCombatHook = Callable[[BeforeCombatContext], None]


class DurationBuffTracker:
    """Records day-clock buff casts and answers "is it active at minute t?".

    A buff is active in the half-open-ish window [cast_minute, cast_minute +
    duration] (inclusive on both ends — the boundary case is immaterial at
    minute granularity).  Reusable for any timed out-of-combat buff; it holds
    no entity reference and applies no modifiers itself — the daily plan owns
    that, so one tracker can model one buff (e.g. magic_weapon) across a day.

    Each cast carries an optional `value` (default 1) so a single tracker can
    hold multiple *tiers* of the same buff — e.g. Magic Weapon cast at +1 (L2
    slot) and +2 (L3 slot, from level 12).  `strongest_at` returns the largest
    active value, since the highest-tier cast wins where windows overlap.
    """

    def __init__(self) -> None:
        # (cast_minute, duration_min, value)
        self._casts: list[tuple[int, int, int]] = []

    def cast(self, minute: int, duration_min: int, value: int = 1) -> None:
        self._casts.append((minute, duration_min, value))

    def active_at(self, minute: int) -> bool:
        return any(c <= minute <= c + dur for c, dur, _ in self._casts)

    def strongest_at(self, minute: int) -> int:
        """Largest active value at `minute`, or 0 if no cast is active."""
        active = [v for c, dur, v in self._casts if c <= minute <= c + dur]
        return max(active) if active else 0

    def reset(self) -> None:
        """Clear all recorded casts (call at long rest / day start)."""
        self._casts.clear()


# ---------------------------------------------------------------------------
# DayRunner
# ---------------------------------------------------------------------------

class DayRunner:
    """Runs one full adventuring day (LR → 4 combats → LR-implied).

    Parameters
    ----------
    rng:
        Shared SeededRNG — all randomness goes through here, including combat
        timing and SR placement rolls.
    entities:
        All entities that participate in combat.  Shared across all 4 combats;
        HP and resources carry over between fights.
    policies:
        entity_id → Policy mapping, same as Scheduler.
    rounds_per_combat:
        How many rounds each combat runs.  Default 4 per the design contract.
    between_combats:
        Optional hook called after each combat (including combat 4).  Use to
        model out-of-combat actions like Prayer of Healing.  None = no
        out-of-combat actions.
    """

    def __init__(
        self,
        rng: "SeededRNG",
        entities: list["Entity"],
        policies: dict[int, "Policy"],
        rounds_per_combat: int = 4,
        between_combats: BetweenCombatsHook | None = None,
        before_combat: BeforeCombatHook | None = None,
    ) -> None:
        self.rng = rng
        self.entities = entities
        self.policies = policies
        self.rounds_per_combat = rounds_per_combat
        self.between_combats = between_combats
        self.before_combat = before_combat

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_day(self) -> DayResult:
        """Run one adventuring day.  Returns aggregated results.

        Steps:
          1. Long rest: restore all entity HP and resources to maximum.
          2. Sample combat start times and determine SR placement.
          3. Run 4 combats.  After the SR-indexed combat apply the short rest.
             After every combat call the between_combats hook (if provided).
        """
        # Step 1: long rest
        self._apply_lr()

        # Step 2: timing
        combat_times = self._roll_combat_times()
        sr_after_combat = self._determine_sr_placement(combat_times)
        log.info(
            "Day start: combat times=%s, SR after combat %d",
            combat_times, sr_after_combat,
        )

        # Step 3: combats
        combats: list[CombatResult] = []
        for i in range(4):
            combat_num = i + 1

            # Pre-combat / day-clock buff setup (Magic Weapon, etc.).
            if self.before_combat is not None:
                ctx = BeforeCombatContext(
                    combat_num=combat_num,
                    combat_start_minute=combat_times[i],
                    combat_times=combat_times,
                    entities=self.entities,
                    rng=self.rng,
                )
                self.before_combat(ctx)

            result = self._run_combat(combat_num)
            combats.append(result)

            # Short rest fires after the designated combat.
            if sr_after_combat == combat_num:
                log.info("Short rest fires after combat %d.", combat_num)
                self._apply_sr()

            # Between-combats hook (PoH, pre-cast spells, etc.)
            if self.between_combats is not None:
                interval = self._interval_length(combat_num, combat_times)
                ctx = BetweenCombatsContext(
                    after_combat_num=combat_num,
                    sr_after_combat=sr_after_combat,
                    interval_length=interval,
                    entities=self.entities,
                    rng=self.rng,
                )
                self.between_combats(ctx)

        return DayResult(
            combats=combats,
            sr_after_combat=sr_after_combat,
            combat_times=combat_times,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_lr(self) -> None:
        """Long rest: restore HP and all resources to maximum."""
        for entity in self.entities:
            entity.hp = entity.max_hp
            entity.resources.restore_lr()
        log.debug("Long rest applied — all entities at full HP and resources.")

    def _apply_sr(self) -> None:
        """Short rest: restore SR-recharging resources for all entities."""
        for entity in self.entities:
            entity.resources.restore_sr()
        log.debug("Short rest applied.")

    def _roll_combat_times(self) -> list[int]:
        """Sample one start minute per combat from its quarter-day window."""
        times: list[int] = []
        for start, end in _COMBAT_WINDOWS:
            # roll_one(n) gives [1, n]; shift to [start, end]
            t = self.rng.roll_one(end - start + 1) + (start - 1)
            times.append(t)
        return times

    def _determine_sr_placement(self, combat_times: list[int]) -> int:
        """Return which inter-combat interval (1, 2, or 3) the SR falls in.

        Each combat lasts 1 minute.  Interval N = gap between end of combat N
        and start of combat N+1.
        """
        # Interval lengths (combat lasts 1 minute → end = start + 1)
        interval_2 = combat_times[2] - (combat_times[1] + 1)

        if interval_2 >= 60:
            return 2
        else:
            # Both interval 1 and 3 are guaranteed ≥ 60 min given how
            # combat times are sampled — pick one at random.
            return 1 if self.rng.roll_one(2) == 1 else 3

    def _interval_length(self, after_combat_num: int, combat_times: list[int]) -> int:
        """Minutes available after combat *after_combat_num* before the next event.

        For combats 1–3 this is the gap to the next combat start.
        For combat 4 this is the remainder of the 960-minute day.
        """
        if after_combat_num < 4:
            return combat_times[after_combat_num] - (combat_times[after_combat_num - 1] + 1)
        else:
            return 960 - (combat_times[3] + 1)

    def _run_combat(self, combat_num: int) -> CombatResult:
        """Run a single combat encounter and return its results."""
        log.info("=== Combat %d start ===", combat_num)

        # Combat boundary: clear tick-expiring statuses (vex, sap, …) so nothing
        # leaks across encounters.  Each combat restarts the round counter at 1,
        # so a carried-over status would never be swept (see StatusSet.clear).
        for entity in self.entities:
            entity.statuses.clear()
            # Sweep combat-clock cast_effect buffs (modifiers + their concentration)
            # so a combat-long cast does not leak into the next encounter
            # (design/buff_primitive.md).  No-op for builds that manage their own
            # buff sync (e.g. War Angel's Bless via before_combat).
            entity.clear_combat_buffs()

        # Optional per-combat policy setup (AoO slot, enemy archetype, …).
        # combat_num is 1-based; hand policies a 0-based index.
        for policy in self.policies.values():
            hook = getattr(policy, "on_combat_start", None)
            if callable(hook):
                hook(combat_num - 1, self.rng)

        scheduler = Scheduler(
            rng=self.rng,
            entities=self.entities,
            policies=self.policies,
            max_rounds=self.rounds_per_combat,
        )
        damage_log = scheduler.run()
        log.info("=== Combat %d end: damage=%s ===", combat_num, damage_log)
        return CombatResult(
            combat_num=combat_num,
            damage_log=damage_log,
            damage_received=dict(scheduler.damage_received),
        )
