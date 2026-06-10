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
    8: {
        "weapon": "longsword",
        "attack_bonus": 7,          # unchanged (no ASI this level)
        "damage_dice": (1, 8),
        "damage_bonus": 6,
        "weapon_mastery": "sap",
        "enemy_ac": 16,
        "char_hp": 59,              # build guide: 59.5
        "target_dpr": 23.36,
        "true_strike_dice": [(1, 6)],
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (2, 1),
            "spell_slot_2": (3, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "spell_slot_1": (4, 0),
            "action_surge": (1, "full"),
            "brutality": (4, "full"),           # Gladiator: CHA mod (4) charges / SR
        },
        "magic_weapon_casts_per_day": 2,
    },
    9: {
        "weapon": "longsword",
        "attack_bonus": 9,          # PB 4 + CHA 5  (fighter-04: PB ↑; ASI: CHA 20)
        "damage_dice": (1, 8),
        "damage_bonus": 7,          # CHA 5 + dueling 2
        "weapon_mastery": "sap",
        "enemy_ac": 16,
        "char_hp": 67,
        "target_dpr": 27.59,
        "true_strike_dice": [(1, 6)],
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (2, 1),
            "spell_slot_2": (3, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "spell_slot_1": (4, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),           # CHA mod 5 now
        },
        "magic_weapon_casts_per_day": 2,
    },
    10: {
        "weapon": "longsword",
        "attack_bonus": 9,          # unchanged (fighter-05: Extra Attack, no stat change)
        "damage_dice": (1, 8),
        "damage_bonus": 7,
        "weapon_mastery": "sap",
        "enemy_ac": 16,
        "char_hp": 74,              # build guide: 74.5
        "target_dpr": 35.32,
        # No true_strike_dice: True Strike is dropped; action = 2 plain weapon attacks
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (2, 1),
            "spell_slot_2": (3, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "spell_slot_1": (4, 0),
            "action_surge": (1, "full"),        # surge now also gives 2 attacks
            "brutality": (5, "full"),
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
        # Per-turn state, reset at the start of each decide() call.
        self._bluffed_this_turn: bool = False

    # -- per-combat setup -------------------------------------------------

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        """Pre-roll which round carries this combat's single AoO.

        The build guide models 5 AoO timing slots (before turn 1, between each
        pair of turns, after turn 4).  Since at these levels an AoO is just one
        more identical attack with no timing-dependent payoff, we collapse it to
        a uniformly random round in [1, rounds_per_combat] and emit it that round.
        """
        self._aoo_round = rng.roll_one(self._rounds_per_combat)

    # -- decision point ---------------------------------------------------

    def decide(self, snapshot: GameState) -> list[Choice]:
        # decide() is the turn-start commit point: reset per-turn flags here.
        self._bluffed_this_turn = False
        choices: list[Choice] = []

        # Setup attacks are emitted BEFORE True Strike so any bluff-applied vex
        # (L8+) is consumed by the TS rather than expiring unused.

        # Action Surge (L7+): extra weapon attack(s) on round 1, greedily.
        # At L8+: taking the surge swing means skipping War Priest this turn so
        # the BA stays free for a smite on the first hit.
        # At L10+: surge gives 2 attacks (Extra Attack applies to the surged action).
        has_surge = (
            snapshot.round_number == 1
            and snapshot.resources.get("action_surge", 0) >= 1
        )
        if has_surge:
            choices.append(Choice(
                action_type="attack",
                cost="none",
                target=self._target,
                weapon_stat="attack_bonus",
                resource_cost={"action_surge": 1},
            ))
            if self.level >= 10:
                choices.append(Choice(
                    action_type="attack",
                    cost="none",
                    target=self._target,
                    weapon_stat="attack_bonus",
                ))

        # War Priest BA swing: use whenever a charge remains, EXCEPT on round 1
        # at L8+ when the surge is taken (BA stays free for smite on TS hit).
        skip_wp = self.level >= 8 and has_surge
        if not skip_wp and snapshot.resources.get("war_priest", 0) >= 1:
            choices.append(Choice(
                action_type="attack",
                cost="bonus_action",
                target=self._target,
                weapon_stat="attack_bonus",
                resource_cost={"war_priest": 1},
            ))

        # Action: True Strike cast (L5-L9) or plain Attack action (L10+).
        # Levels 1–4: no rider (empty list) → plain weapon attack.
        # Levels 5–9: True Strike carries a +1d6 radiant rider.
        # Level 10+: Extra Attack replaces True Strike — emit 2 plain weapon attacks.
        #   The extra_damage_dice list is empty at L10+ (no true_strike_dice in data).
        if snapshot.resources.get("action", 0) >= 1:
            choices.append(Choice(
                action_type="attack",
                cost="action",
                target=self._target,
                weapon_stat="attack_bonus",
                extra_damage_dice=list(self._true_strike_dice),
            ))
            if self.level >= 10:
                choices.append(Choice(
                    action_type="attack",
                    cost="none",
                    target=self._target,
                    weapon_stat="attack_bonus",
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

    # Slot priority for casting wrathful smite: free_cast first (can ONLY be
    # used for wrathful smite — most constrained), then pact slot (SR-recharge,
    # but theoretically fungible for other utility spells), then cleric L1 slots.
    _SMITE_SLOT_PRIORITY = ("free_cast", "pact_magic_slot", "spell_slot_1")

    def on_hit(self, ctx: HitContext) -> "HitResponse | None":
        """Brutality::bluff (L8+) and Wrathful Smite (L6+).

        Both can fire on the same hit.  The combined HitResponse is built and
        returned as one; the scheduler validates and consumes all costs together.

        Brutality::bluff: spend 1 brutality charge to add vex mastery to this
        attack (applied on-hit; gives attacker advantage on the next attack vs
        this target).  No action-economy cost.  Only on the first setup hit per
        turn (BA/none/reaction).  Skipped on the final round's AoO (vex would
        expire before any follow-on attack could use it).

        Wrathful Smite: spend a spell slot + bonus action to add 1d6 (doubled on
        a crit).  Never on a reaction; only when the BA is still unspent.
        War Priest is the top BA priority and is already spent in decide(), so
        smite fires on turns where the BA stayed free.
        """
        # L8: setup attacks only (BA/none/reaction); vex chains to same-turn TS.
        # L9+: any attack type; TS hits carry vex to the *next* turn's first attack.
        bluff_cost_ok = (
            self.level >= 9
            or ctx.cost in ("bonus_action", "none", "reaction")
        )
        # Waste gate: don't bluff when vex would expire before any follow-on.
        # L8-L9: action (TS) and reaction (AoO) on the final round have no
        #   follow-on to consume vex (no round 5 / no further own-turn attacks).
        # L10+: action attack 1's vex chains to action attack 2 in the same turn
        #   (Extra Attack follow-up); only the T4 AoO still wastes.
        last_round = ctx.round_number == self._rounds_per_combat
        if self.level >= 10:
            bluff_no_waste = not (ctx.cost == "reaction" and last_round)
        else:
            bluff_no_waste = not (last_round and ctx.cost in ("action", "reaction"))
        want_bluff = (
            self.level >= 8
            and bluff_cost_ok
            and bluff_no_waste
            and ctx.resources.get("brutality", 0) >= 1
            and not self._bluffed_this_turn
        )
        want_smite = (
            self.level >= 6
            and ctx.cost != "reaction"
            and ctx.bonus_action_available
            and self._next_smite_slot(ctx.resources) is not None
        )

        if not want_bluff and not want_smite:
            return None

        resource_cost: dict[str, int] = {}
        extra_masteries: list[str] = []
        extra_dice: list[tuple[int, int]] = []
        action_cost: "str | None" = None

        if want_bluff:
            resource_cost["brutality"] = 1
            extra_masteries = ["vex"]
            self._bluffed_this_turn = True  # commit: prevent a second bluff this turn

        if want_smite:
            slot = self._next_smite_slot(ctx.resources)
            resource_cost[slot] = resource_cost.get(slot, 0) + 1
            extra_dice = [(1, 6)]
            action_cost = "bonus_action"

        return HitResponse(
            resource_cost=resource_cost,
            extra_damage_dice=extra_dice,
            extra_masteries=extra_masteries,
            action_cost=action_cost,
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
