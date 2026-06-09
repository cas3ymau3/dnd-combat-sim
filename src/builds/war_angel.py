"""
war_angel.py — The War Angel build: per-level stat blocks + daily-plan policy.

Source of truth for intent:
  - design/build-guides/38_the_war_angel.txt  (level-by-level notes + DPR targets)
  - reference/r-prototype/war_angel_combat_policies.txt  (prototype policy prose)

This module currently covers PHASE A (levels 1–4): the mechanically simple
levels validated against an EXACT DPR target.  Levels 5+ (Phase B onward) add
true-strike, war priest, guided strike, wrathful smite, brutality, etc. and
will extend both LEVELS and WarAngelPolicy.

Phase A character (levels 1–4)
------------------------------
Stats: DEX 15 (+2), CHA 17 (+3), WIS 16 (+3); proficiency bonus +2.

  L1  Fighter-1.  Rapier (vex): 1d8, +DEX to atk/dmg, +2 dueling.
        attack +4 (PB 2 + DEX 2), damage 1d8 + 4 (DEX 2 + dueling 2).
  L2  +Warlock-1 (Pact of the Blade → CHA for weapon attacks).  Switch to the
        longsword (sap) — the character's identity weapon.
        attack +5 (PB 2 + CHA 3), damage 1d8 + 5 (CHA 3 + dueling 2).
  L3  +Cleric-1.  No combat-relevant change (policy identical to L2).
  L4  +Cleric-2.  No combat-relevant change (policy identical to L2).

Why DPR *drops* from L1 to L2 despite a higher modifier: vex (rapier) grants
advantage on every follow-up attack against the same target; sap (longsword)
only affects the enemy's attacks against us — irrelevant to our own DPR.  We
trade offense for defensive identity.  That asymmetry is itself a correctness
check: if L2 didn't drop below L1, vex isn't being modeled.

Daily plan (levels 1–4) — identical across all 4 combats and all 4 rounds:
  - one weapon attack with the action each round;
  - exactly one attack of opportunity per combat, its round pre-rolled at
    combat start (see WarAngelPolicy.on_combat_start and PROGRESS.md "AoO /
    spatial" decision — timing is collapsed to a single extra reaction-cost
    attack on the chosen round, since with no resources/buffs in play its
    position within the combat is immaterial to total damage).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..day_runner import (
    BeforeCombatContext,
    BetweenCombatsContext,
    DayRunner,
    DurationBuffTracker,
)
from ..entity import Entity
from ..modifiers import Modifier
from ..policy import (
    Choice,
    GameState,
    HitContext,
    HitResponse,
    MissContext,
    MissResponse,
)
from ..resources import ResourceEntry, ResourcePool

if TYPE_CHECKING:
    from ..rng import SeededRNG


# Magic Weapon (2024): non-concentration, 60-minute duration, +1 attack/+1 damage.
MAGIC_WEAPON_DURATION_MIN = 60
MAGIC_WEAPON_BONUS = 1
# Prayer of Healing needs a 10-minute rest window to cast.
POH_MIN_INTERVAL_MIN = 10


# ---------------------------------------------------------------------------
# Per-level build data
# ---------------------------------------------------------------------------
# Each entry is one level's combat-relevant stat block plus the validation
# context (the enemy AC assumed by the build guide and its simulated DPR
# target).  `char_hp` is recorded for completeness; it does not affect DPR in
# the threshold model (nothing damages us at these levels).

LEVELS: dict[int, dict] = {
    1: {
        "weapon": "rapier",
        "attack_bonus": 4,
        "damage_dice": (1, 8),
        "damage_bonus": 4,
        "weapon_mastery": "vex",
        "enemy_ac": 13,
        "char_hp": 12,
        "target_dpr": 8.32,
    },
    2: {
        "weapon": "longsword",
        "attack_bonus": 5,
        "damage_dice": (1, 8),
        "damage_bonus": 5,
        "weapon_mastery": "sap",
        "enemy_ac": 14,
        "char_hp": 18,   # guide lists 18.5 (avg); HP is DPR-irrelevant here
        "target_dpr": 7.39,
    },
    3: {
        "weapon": "longsword",
        "attack_bonus": 5,
        "damage_dice": (1, 8),
        "damage_bonus": 5,
        "weapon_mastery": "sap",
        "enemy_ac": 14,
        "char_hp": 25,
        "target_dpr": 7.39,
    },
    4: {
        "weapon": "longsword",
        "attack_bonus": 5,
        "damage_dice": (1, 8),
        "damage_bonus": 5,
        "weapon_mastery": "sap",
        "enemy_ac": 15,
        "char_hp": 31,
        "target_dpr": 6.81,
    },
    5: {
        "weapon": "longsword",
        "attack_bonus": 6,          # PB 3 + CHA 3
        "damage_dice": (1, 8),
        "damage_bonus": 5,          # CHA 3 + dueling 2
        "weapon_mastery": "sap",
        "enemy_ac": 15,
        "char_hp": 38,
        "target_dpr": 16.73,
        # True Strike now carries a +1d6 radiant rider on hit (cantrip scaling).
        "true_strike_dice": [(1, 6)],
        # Resource pools that come online at level 5.
        "resources": {
            "war_priest": (3, "full"),          # 3 / SR  → 9 / LR with PoH + SR
            "channel_divinity": (2, 1),         # 2 / LR, +1 / SR → 4 / LR
            "spell_slot_2": (2, 0),             # one for PoH, one earmarked Magic Weapon
        },
        # Daily-plan budgets (build-specific, stated explicitly per PROGRESS).
        "magic_weapon_casts_per_day": 1,        # 1 lvl-2 slot earmarked for MW
    },
    6: {
        "weapon": "longsword",
        "attack_bonus": 7,          # PB 3 + CHA 4 (shadow-touched → CHA 18)
        "damage_dice": (1, 8),
        "damage_bonus": 6,          # CHA 4 + dueling 2
        "weapon_mastery": "sap",
        "enemy_ac": 15,
        "char_hp": 44,
        "target_dpr": 21.03,
        "true_strike_dice": [(1, 6)],
        "resources": {
            "war_priest": (3, "full"),          # 9 / LR with PoH + SR
            "channel_divinity": (2, 1),         # 4 / LR
            "spell_slot_2": (3, 0),             # 1 PoH + 2 Magic Weapon
            "pact_magic_slot": (1, "full"),     # warlock L1 slot, recovers on SR
            "free_cast": (1, 0),                # shadow-touched wrathful smite, 1/LR
            "spell_slot_1": (4, 0),             # cleric L1 slots, fuel smites
        },
        "magic_weapon_casts_per_day": 2,        # 2 lvl-2 slots earmarked for MW
    },
    7: {
        "weapon": "longsword",
        "attack_bonus": 7,          # unchanged from L6 (Fighter-2: no stat/PB change)
        "damage_dice": (1, 8),
        "damage_bonus": 6,
        "weapon_mastery": "sap",
        "enemy_ac": 16,             # ↑ from 15 — most of why DPR barely moves
        "char_hp": 52,
        "target_dpr": 21.26,
        "true_strike_dice": [(1, 6)],
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (2, 1),
            "spell_slot_2": (3, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "spell_slot_1": (4, 0),
            "action_surge": (1, "full"),        # 1 / SR → 3 / LR with PoH + SR
        },
        "magic_weapon_casts_per_day": 2,
    },
}

# Phase A is exact-match; later phases are soft (±10%).  Recorded here so the
# validation harness can pick the right tolerance per level.
EXACT_MATCH_MAX_LEVEL = 4


# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------

def _make_resources(data: dict) -> ResourcePool:
    """Build the ResourcePool from a level's "resources" spec (may be absent)."""
    spec = data.get("resources", {})
    entries = {
        name: ResourceEntry(current=maximum, maximum=maximum, sr_restore=sr)
        for name, (maximum, sr) in spec.items()
    }
    return ResourcePool(entries)


def make_war_angel(level: int) -> Entity:
    """Build the War Angel Entity for the given level (1–5 for now)."""
    if level not in LEVELS:
        raise NotImplementedError(
            f"War Angel level {level} not yet implemented (have {sorted(LEVELS)})."
        )
    data = LEVELS[level]
    return Entity(
        name=f"WarAngel-L{level}",
        hp=data["char_hp"],
        base_stats={
            "attack_bonus": data["attack_bonus"],
            "damage_dice": data["damage_dice"],
            "damage_bonus": data["damage_bonus"],
            "weapon_mastery": data["weapon_mastery"],
        },
        resources=_make_resources(data),
    )


def make_training_dummy(level: int) -> Entity:
    """Build the AC-only target for the given level.

    HP is effectively infinite: in the threshold model the dummy never gates
    turns, and it has no policy so it never acts.  We only ever read its AC.
    """
    return Entity(
        name=f"Dummy-AC{LEVELS[level]['enemy_ac']}",
        hp=10**9,
        base_stats={"ac": LEVELS[level]["enemy_ac"]},
    )


# ---------------------------------------------------------------------------
# Daily-plan policy (levels 1–5)
# ---------------------------------------------------------------------------

class WarAngelPolicy:
    """War Angel daily plan.  Currently implements levels 1–5.

    Levels 1–4 (Phase A): one weapon attack with the action each round, plus one
    AoO per combat (round pre-rolled at combat start).

    Level 5 (Phase B): the action becomes a True Strike cast — a weapon attack
    carrying a +1d6 radiant rider (via `extra_damage_dice`) — and a bonus-action
    War Priest weapon attack is added whenever a charge remains.  The AoO is
    unchanged.  (Guided Strike — the post-roll decision point — is added in B2;
    this B1 form omits it.)

    The weapon's mastery (vex at L1, sap at L2+) rides on the entity's
    `weapon_mastery` base stat, so the scheduler applies it automatically.

    Parameters
    ----------
    level:
        Character level (1–5 for now).
    target:
        The entity to attack.  Fixed for the single-target validation setup.
    rounds_per_combat:
        Used only to bound the random AoO round.  Defaults to 4.
    """

    def __init__(self, level: int, target: Entity, rounds_per_combat: int = 4) -> None:
        if level not in LEVELS:
            raise NotImplementedError(
                f"WarAngelPolicy does not yet support level {level}."
            )
        self.level = level
        self._target = target
        self._rounds_per_combat = rounds_per_combat
        # True Strike's bonus dice (empty before level 5).
        self._true_strike_dice = list(LEVELS[level].get("true_strike_dice", []))
        # Per-combat state, (re)initialised by on_combat_start.
        self._aoo_round: int = 1
        self._combat_index: int = 0   # kept for L8 combat-aware husbanding

    # -- per-combat setup -------------------------------------------------

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        """Pre-roll which round carries this combat's single AoO, and record the
        combat index for any combat-aware logic.

        The build guide models 5 AoO timing slots (before turn 1, between each
        pair of turns, after turn 4).  Since at these levels an AoO is just one
        more identical attack with no timing-dependent payoff, we collapse it to
        a uniformly random round in [1, rounds_per_combat] and emit it that round.
        """
        self._aoo_round = rng.roll_one(self._rounds_per_combat)
        self._combat_index = combat_index

    # -- decision point ---------------------------------------------------

    def decide(self, snapshot: GameState) -> list[Choice]:
        # Pure read: no dice, no mutation.  decide() runs exactly once per round,
        # so the round check alone fires the AoO on exactly one round per combat
        # (no "already used" flag needed).
        choices: list[Choice] = []

        # Action attack.  At level 5 this is a True Strike cast — a weapon
        # attack carrying the cantrip's +1d6 radiant rider.  At 1–4 the rider
        # list is empty, so it's a plain weapon attack.
        if snapshot.resources.get("action", 0) >= 1:
            choices.append(Choice(
                action_type="attack",
                cost="action",
                target=self._target,
                weapon_stat="attack_bonus",
                extra_damage_dice=list(self._true_strike_dice),
            ))

        # Action Surge (L7+): one extra weapon attack, greedily on turn 1 of each
        # combat while a charge remains.  A PLAIN swing — no True Strike rider:
        # 2024 forbids the Magic action on the surged action, so it can't be a
        # True Strike cast.  cost="none" leaves the regular action untouched; the
        # action_surge resource is what's spent.
        if (snapshot.round_number == 1
                and snapshot.resources.get("action_surge", 0) >= 1):
            choices.append(Choice(
                action_type="attack",
                cost="none",
                target=self._target,
                weapon_stat="attack_bonus",
                resource_cost={"action_surge": 1},
            ))

        # Bonus action: War Priest weapon attack while a charge remains (L5+).
        # A plain weapon swing — no True Strike rider on the BA attack.
        if snapshot.resources.get("war_priest", 0) >= 1:
            choices.append(Choice(
                action_type="attack",
                cost="bonus_action",
                target=self._target,
                weapon_stat="attack_bonus",
                resource_cost={"war_priest": 1},
            ))

        # One AoO per combat, on the pre-rolled round (reaction cost).
        if (
            snapshot.round_number == self._aoo_round
            and snapshot.resources.get("reaction", 0) >= 1
        ):
            choices.append(Choice(
                action_type="attack",
                cost="reaction",
                target=self._target,
                weapon_stat="attack_bonus",
            ))

        return choices

    # -- post-roll decision point: Guided Strike (level 5+) ---------------

    def on_miss(self, ctx: MissContext) -> "MissResponse | None":
        """War Cleric's Guided Strike: spend a Channel Divinity charge to add
        +10 to a missed attack, turning it into a hit.

        Greedy rule (levels 5–7): use it on ANY flippable non-AoO miss while a
        charge remains.  See PROGRESS — the old "≤1 in combat 1" cap was a
        vestigial husbanding heuristic; Channel Divinity (max 2, +1 SR, +1 PoH)
        comes out to ~4 uses/day either way, so the cap was ~EV-neutral, and
        rescuing earlier (in combat 1, where magic weapon is most likely active)
        is marginally better.  The real optimization — preferring high-value
        (true-strike / setup) misses over plain swings — arrives at L8.

        Gates:
          - not available below level 5 (no Channel Divinity guided-strike use);
          - never on attacks of opportunity (a reaction off-turn; also matches the
            prototype's "no guided strike on AoOs");
          - only when +10 would actually flip the miss to a hit.
        """
        if self.level < 5:
            return None
        if ctx.is_aoo:
            return None
        if ctx.resources.get("channel_divinity", 0) < 1:
            return None
        if ctx.missed_by > 10:                      # +10 wouldn't flip it
            return None
        return MissResponse(resource_cost={"channel_divinity": 1}, bonus=10)

    # -- post-roll decision point: Wrathful Smite (level 6+) --------------

    # Slot priority for casting wrathful smite (cheapest-to-recover first):
    # the pact slot (back on a short rest), then the free shadow-touched cast,
    # then cleric level-1 slots.
    _SMITE_SLOT_PRIORITY = ("pact_magic_slot", "free_cast", "spell_slot_1")

    def on_hit(self, ctx: HitContext) -> "HitResponse | None":
        """Wrathful Smite (2024): cast as a bonus action immediately after a hit
        to add 1d6 (doubled on a crit).

        EV result (see PROGRESS): a war-priest swing dominates wrathful smite in
        every case, so war priest is the unconditional top bonus-action use and
        is already spent in decide() when a charge remains.  Smite therefore only
        fires when the bonus action is STILL FREE — i.e. on turns we had no war
        priest charge — weaponizing the bonus action instead of wasting it.

        Gates:
          - level 6+ only (the spell isn't available earlier);
          - never on a reaction/AoO (2024: bonus actions only on your own turn —
            our AoO is collapsed onto our turn, so the engine can't tell; we must);
          - only if the bonus action is unspent this turn (no war priest taken);
          - only if a smite slot remains.
        """
        if self.level < 6:
            return None
        if ctx.cost == "reaction":
            return None
        if not ctx.bonus_action_available:
            return None
        slot = self._next_smite_slot(ctx.resources)
        if slot is None:
            return None
        # +1d6 necrotic; doubles on a crit automatically (the DamageEvent carries
        # is_crit, and extra dice double like any others).
        return HitResponse(
            resource_cost={slot: 1},
            extra_damage_dice=[(1, 6)],
            action_cost="bonus_action",
        )

    def _next_smite_slot(self, resources: dict) -> "str | None":
        for name in self._SMITE_SLOT_PRIORITY:
            if resources.get(name, 0) >= 1:
                return name
        return None


# ---------------------------------------------------------------------------
# Daily plan: out-of-combat / day-clock logic (level 5+)
# ---------------------------------------------------------------------------

class WarAngelDailyPlan:
    """Holds the War Angel's out-of-combat decisions across one adventuring day.

    Two hooks plug into DayRunner:
      - before_combat: maintain Magic Weapon (day-clock, 60-min, non-conc.).
      - between_combats: cast Prayer of Healing once/day (an SR-equivalent
        recharge of War Priest, Channel Divinity, etc.).

    Per-day state (the Magic Weapon cast timeline, the cast budget, whether PoH
    has fired) is reset at the start of each day, detected when before_combat is
    called for combat 1 (DayRunner always runs combat 1 first, right after the
    long rest has refilled resources).
    """

    def __init__(self, character: Entity, level: int) -> None:
        self.character = character
        self.level = level
        data = LEVELS[level]
        self._mw_casts_per_day: int = data.get("magic_weapon_casts_per_day", 0)
        self._mw = DurationBuffTracker()
        self._mw_casts_used: int = 0
        self._poh_cast: bool = False

    # -- per-day reset ----------------------------------------------------

    def _reset_day(self) -> None:
        self._mw.reset()
        self._mw_casts_used = 0
        self._poh_cast = False

    # -- Magic Weapon (before_combat) ------------------------------------

    def before_combat(self, ctx: BeforeCombatContext) -> None:
        if ctx.combat_num == 1:
            self._reset_day()

        minute = ctx.combat_start_minute

        # Cast schedule (stated explicitly per build, not a hidden engine rule):
        #   - cast before combat 1;
        #   - before combat N>1, cast only if Magic Weapon is currently INACTIVE
        #     and an earmarked level-2 slot remains.
        want_cast = (
            self._mw_casts_used < self._mw_casts_per_day
            and (ctx.combat_num == 1 or not self._mw.active_at(minute))
        )
        if want_cast:
            self._mw.cast(minute, MAGIC_WEAPON_DURATION_MIN)
            self._mw_casts_used += 1
            self.character.resources.consume("spell_slot_2")

        # Sync the entity's modifier stack to whether MW is active this combat.
        self._sync_magic_weapon(self._mw.active_at(minute))

    def _sync_magic_weapon(self, active: bool) -> None:
        self.character.remove_modifier("magic_weapon")
        if active:
            self.character.add_modifier(
                Modifier("attack_bonus", MAGIC_WEAPON_BONUS, "magic_weapon"))
            self.character.add_modifier(
                Modifier("damage_bonus", MAGIC_WEAPON_BONUS, "magic_weapon"))

    # -- Prayer of Healing (between_combats) -----------------------------

    def between_combats(self, ctx: BetweenCombatsContext) -> None:
        # Cast PoH once per day, in the first valid interval that is NOT the
        # short-rest interval (so the two SR-equivalent recharges don't overlap
        # and waste each other), and only if the interval is long enough.
        if self._poh_cast:
            return
        if ctx.after_combat_num == ctx.sr_after_combat:
            return
        if ctx.interval_length < POH_MIN_INTERVAL_MIN:
            return
        # PoH consumes a level-2 slot and acts as a short-rest-equivalent
        # recharge (War Priest, Channel Divinity, pact slot, …).
        self.character.resources.consume("spell_slot_2")
        for entity in ctx.entities:
            entity.resources.restore_sr()
        self._poh_cast = True


# ---------------------------------------------------------------------------
# Full day-runner assembly (used by the validation harness)
# ---------------------------------------------------------------------------

def make_day_runner(level: int, rng: "SeededRNG", rounds_per_combat: int = 4):
    """Assemble (DayRunner, character, dummy) for the given level.

    Wires the policy plus, for level 5+, the daily-plan hooks (Magic Weapon /
    Prayer of Healing).  Keeps the validation harness build-agnostic.
    """
    char = make_war_angel(level)
    dummy = make_training_dummy(level)
    policy = WarAngelPolicy(level=level, target=dummy,
                            rounds_per_combat=rounds_per_combat)

    before_combat = None
    between_combats = None
    if level >= 5:
        plan = WarAngelDailyPlan(character=char, level=level)
        before_combat = plan.before_combat
        between_combats = plan.between_combats

    runner = DayRunner(
        rng=rng,
        entities=[char, dummy],
        policies={char.id: policy},
        rounds_per_combat=rounds_per_combat,
        before_combat=before_combat,
        between_combats=between_combats,
    )
    return runner, char, dummy
