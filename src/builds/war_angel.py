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

from ..content import (
    interpret_hit_rider,
    interpret_intercept,
    interpret_modifiers,
    interpret_on_hit_effects,
    interpret_roll_bonus,
    load_abilities,
)
from ..day_runner import (
    BeforeCombatContext,
    BetweenCombatsContext,
    DayRunner,
    DurationBuffTracker,
)
from ..entity import Entity
from ..healing import (HealSpec, HitDiceSpec, attach_hit_dice, resolve_healing,
                       spend_hit_dice_at_short_rest)
from ..policy import (
    Choice,
    CounterSpec,
    FailedSaveContext,
    GameState,
    HitContext,
    HitResponse,
    IncomingAttackContext,
    InterceptResponse,
    MissContext,
    MissResponse,
    SaveRerollResponse,
)
from ..resources import ResourceEntry, ResourcePool
from . import enemy_stats          # THE enemy-Entity constructor (evaluation_framework.md §3.4)
# PB is the UNIVERSAL character track, not this build's rule (PROGRESS item 5b, s61):
# imported rather than restated so `war_angel.proficiency_bonus` still resolves for any
# caller while there is exactly one source.  See progression.py for why the enemy
# table's numerically-identical column is NOT this fact.
from .progression import proficiency_bonus

if TYPE_CHECKING:
    from ..rng import SeededRNG


# Magic Weapon (2024): non-concentration, 60-minute duration.  Base cast (L2
# slot) is +1/+1; upcast with a level-3 slot (from character level 12) is +2/+2.
MAGIC_WEAPON_DURATION_MIN = 60
MAGIC_WEAPON_PLUS1 = 1
MAGIC_WEAPON_PLUS2 = 2
# Prayer of Healing needs a 10-minute rest window to cast.
POH_MIN_INTERVAL_MIN = 10

# Declarative ability layer (src/content.py): the abilities below are loaded
# FROM DATA (content/abilities/*.yaml) and translated into engine objects by the
# effect-interpreter, rather than hand-built in this module.  This realizes the
# project's #1 architectural bet (CLAUDE.md #1/#2) for these abilities; the
# build's POLICY (which ability fires, slot priority, sequencing) stays Python.
_ABILITIES = load_abilities()
BLESS = _ABILITIES["bless"]                  # core_examples.yaml (+1d4 bonus_die)
WRATHFUL_SMITE = _ABILITIES["wrathful_smite"]  # war_angel.yaml (1d6 on-hit rider)
BRUTALITY_BLUFF = _ABILITIES["brutality_bluff"]  # war_angel.yaml (vex + adv-next-save)
BRUTALITY_BLEED = _ABILITIES["brutality_bleed"]  # war_angel.yaml (sap + CHA flat dmg)
FLOURISH_PARRY = _ABILITIES["flourish_parry"]    # war_angel.yaml (intercept: +CHA AC)
WAR_GODS_BLESSING = _ABILITIES["war_gods_blessing"]  # war_angel.yaml (flat +2 AC)
MAGIC_WEAPON = _ABILITIES["magic_weapon"]        # war_angel.yaml (flat +1/+2 atk+dmg)
GUIDED_STRIKE = _ABILITIES["guided_strike"]      # war_angel.yaml (on_miss +10 flip)
# Shield of Faith / War God's Blessing (L13, non-conc. +2 AC) and Magic Weapon
# (+1/+2 atk+dmg) are both driven from the data above via interpret_modifiers.

# Indomitable (Fighter, L16 = fighter-09): 1/LR, reroll a failed save with a flat
# bonus equal to fighter level.  We only model concentration checks, so the
# policy applies it there.  INDOMITABLE_MIN_SUCCESS is the DC-assessment cutoff:
# only spend the 1/LR reroll if its success probability (using the FLAT save
# bonus, ignoring Bless) clears this.  Inert at the current uniform DC-16 (always
# ~90%+); it becomes load-bearing once we model weaker/variable-DC saves.
INDOMITABLE_BONUS = 9          # fighter level at character level 16
INDOMITABLE_MIN_SUCCESS = 0.5


# ---------------------------------------------------------------------------
# Per-level build data
# ---------------------------------------------------------------------------
# Each entry is one level's combat-relevant stat block.  It carries NO enemy
# material and no DPR target: s52 (evaluation_framework.md §3.4, step 5b) moved the
# enemy out of every build's table, and `target_dpr` went with `src/validation.py`.
# This comment described both until s55 and was stale on both counts.
#
# `char_hp` matters once the enemy acts (`enemy="baseline"`/`"scripted"`): the old
# "nothing damages us at these levels" was true only of the passive dummy.
#
# AC — WRITTEN OFF THE GUIDE (s55), NOT DERIVED.  `ac` was absent at L1-L12, so
# twelve of sixteen levels fought at AC 0 (`Entity.stat()` returns 0 for a missing
# key by design), making every defensive number below L13 garbage.  The values come
# from `design/build-guides/38_the_war_angel.txt`, which states AC explicitly four
# times and tracks the armor on exactly those lines:
#
#   line 170-171  Level-01  armor: chain shirt   AC: 13 + 2(DEX) + 2(shield) = 17
#   line 193-194  Level-02  armor: chain shirt   AC: 13 + 2(DEX) + 2(shield) = 17
#   line 272-273  Level-05  armor: breastplate   AC: 14 + 2(DEX) + 2(shield) = 18
#   line 608-609  Level-16  armor: breastplate   AC: 14 + 2 + 2 + 2(SoF)     = 20
#
# `armor:` appears nowhere else in the guide but the starting-equipment list, so
# there is ONE equipment change, at L5, and the twelve missing rows read 17 (L1-4)
# and 18 (L5-12).  Guide line 290 states it in prose as well ("breastplate armor,
# which boosts our base (shielded) AC to 18 (and 20 w/shield of faith)"), and 18 is
# what L13-L16 already declared.  Shield of Faith stays a POLICY modifier (the +2
# that makes the guide's 20) and is deliberately not baked into the row.
#
# SAVES are NOT in these rows: all six are DERIVED at every level by
# `save_bonuses(level)` below.  Until s55 only `con_save` was declared, and only at
# L13-L16, so five of six saves read 0 everywhere and all six read 0 below L13 — the
# same failure mode as the missing `ac`, and wider, because it reached the levels that
# DID declare one.  The four hand-written `"con_save": 4` rows were removed with that
# change: the derivation reproduces them, so keeping them would be a second source
# for a number the ability-score table already determines.

LEVELS: dict[int, dict] = {
    1: {
        "weapon": "rapier",
        "attack_bonus": 4,
        "damage_dice": (1, 8),
        "damage_bonus": 4,
        "weapon_mastery": "vex",
        "char_hp": 12,
        "extra_base_stats": {
            "ac": 17,               # chain shirt 13 + DEX 2 + shield 2
        },
    },
    2: {
        "weapon": "longsword",
        "attack_bonus": 5,
        "damage_dice": (1, 8),
        "damage_bonus": 5,
        "weapon_mastery": "sap",
        "char_hp": 18,   # guide lists 18.5 (avg); HP is DPR-irrelevant here
        "extra_base_stats": {
            "ac": 17,               # chain shirt 13 + DEX 2 + shield 2
        },
    },
    3: {
        "weapon": "longsword",
        "attack_bonus": 5,
        "damage_dice": (1, 8),
        "damage_bonus": 5,
        "weapon_mastery": "sap",
        "char_hp": 25,
        "extra_base_stats": {
            "ac": 17,               # chain shirt 13 + DEX 2 + shield 2
        },
    },
    4: {
        "weapon": "longsword",
        "attack_bonus": 5,
        "damage_dice": (1, 8),
        "damage_bonus": 5,
        "weapon_mastery": "sap",
        "char_hp": 31,
        "extra_base_stats": {
            "ac": 17,               # chain shirt 13 + DEX 2 + shield 2
        },
    },
    5: {
        "weapon": "longsword",
        "attack_bonus": 6,          # PB 3 + CHA 3
        "damage_dice": (1, 8),
        "damage_bonus": 5,          # CHA 3 + dueling 2
        "weapon_mastery": "sap",
        "char_hp": 38,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
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
        "char_hp": 44,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
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
        "char_hp": 52,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
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
        "char_hp": 59,              # build guide: 59.5
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
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
        "char_hp": 67,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
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
        "char_hp": 74,              # build guide: 74.5
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
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
    11: {
        # Fighter-06: Mage Slayer (+1 DEX). DEX is not our attack stat (Pact of
        # the Blade → CHA), so attack/damage are UNCHANGED from L10. The only
        # combat-relevant change is enemy AC 16 → 17 — which is exactly why the
        # guide's DPR drops (35.32 → 33.70). Still 2 attacks (Extra Attack x2 is
        # L18); brutality stays 5 (CHA 20). A pure data row: no policy change,
        # no new engine work. Validates the attack math at the new AC before
        # Phase D's defensive bundle lands at L13.
        "weapon": "longsword",
        "attack_bonus": 9,          # PB 4 + CHA 5 (unchanged)
        "damage_dice": (1, 8),
        "damage_bonus": 7,          # CHA 5 + dueling 2 (unchanged)
        "weapon_mastery": "sap",
        "char_hp": 82,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (2, 1),
            "spell_slot_2": (3, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "spell_slot_1": (4, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),
        },
        "magic_weapon_casts_per_day": 2,
    },
    12: {
        # Cleric-05: level-3 spell slots arrive → +2 Magic Weapon.  Combat
        # tactics are UNCHANGED from L10/L11 (Extra Attack, brutality::bluff on
        # first hit, War Priest / smite / surge) — the only difference is MW is
        # sometimes +2, which rides the modifier stack, not the policy.  Attack
        # stats unchanged (PB 4 + CHA 5).  Enemy AC stays 17 (→18 at L15).
        #
        # MW budget: 2× +2 casts (the two L3 slots) + 2× +1 casts (two of the
        # three L2 slots; the third is PoH) → 100% uptime, ~50/50 between tiers.
        "weapon": "longsword",
        "attack_bonus": 9,          # PB 4 + CHA 5
        "damage_dice": (1, 8),
        "damage_bonus": 7,          # CHA 5 + dueling 2
        "weapon_mastery": "sap",
        "char_hp": 88,              # build guide: 88.5
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2
        },
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (2, 1),
            "spell_slot_3": (2, 0),             # both earmarked for +2 Magic Weapon
            "spell_slot_2": (3, 0),             # 1 PoH + 2 (+1) Magic Weapon
            "spell_slot_1": (4, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),
        },
        "magic_weapon_casts_per_day": 2,        # +1 casts (L2 slots)
        "magic_weapon_plus2_casts_per_day": 2,  # +2 casts (L3 slots)
    },
    13: {
        # Cleric-06: the defensive bundle. PB → +5 (attack +10). We now
        # concentrate on BLESS (+1d4 to attack rolls & saves) and open every
        # combat by casting Bless (action) + Shield of Faith (BA via War God's
        # Blessing, +2 AC, 1 Channel Divinity) — sacrificing round-1 attacks
        # (Action Surge attacks on round 1 are still allowed, per design).
        #
        # Magic Weapon: 3× +2 (L3 slots) + 1× +1 (one L2 slot) → ~100% uptime,
        # 75% at +2.  The freed L2 slot is Aid (HP only, DPR-irrelevant).
        #
        # Slot competition: Bless is cast 4×/day (one per combat) from cleric L1
        # slots, draining the pool Wrathful Smite also draws on → smite drops to
        # the handful of L1-equivalent slots left (free_cast + pact recoveries).
        # Channel Divinity (5/day: 3 base +1 SR +1 PoH) is reserved 1/combat for
        # Shield of Faith → ~1/day left for Guided Strike.
        #
        # D3a scope: Bless + Shield of Faith applied as combat-start buffs with
        # the enemy NOT yet attacking → 100% Bless uptime. This isolates the
        # offense math; it reads HIGH vs the 34.68 target (which bakes in ~82%
        # uptime from concentration loss). D3b adds the incoming-damage loop.
        "weapon": "longsword",
        "attack_bonus": 10,         # PB 5 + CHA 5
        "damage_dice": (1, 8),
        "damage_bonus": 7,          # CHA 5 + dueling 2
        "weapon_mastery": "sap",
        "char_hp": 95,              # build guide: 95 (Aid +5 is HP-only)
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2 (+2 SoF buff)
        },
        # Enemy profile for the incoming-damage loop (D3b): a CR-appropriate
        # attacker so concentration on Bless can break.  Per the build guide:
        # +11 to hit, 3 attacks, 28 damage on hit, 40% chance to target us per
        # attack (party of 4 — guide uses 50%, we use a more conservative 40%).
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (3, 1),         # 3 base, +1 SR → 5/LR with PoH
            "spell_slot_3": (3, 0),             # 3× +2 Magic Weapon
            "spell_slot_2": (3, 0),             # 1 PoH + 1 (+1) Magic Weapon + 1 Aid
            "spell_slot_1": (4, 0),             # cleric L1: Bless ×4/day + smites
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),
        },
        "magic_weapon_casts_per_day": 1,        # +1 cast (one L2 slot)
        "magic_weapon_plus2_casts_per_day": 3,  # +2 casts (three L3 slots)
        "bless": True,                          # concentrate on Bless each combat
        "shield_of_faith": True,                # War God's Blessing each combat
    },
    14: {
        # Fighter-07 (Gladiator): Flourish Parry + Flourish Counter.  No ASI/PB
        # change → attack/damage IDENTICAL to L13 (PB 5 + CHA 5).  Enemy AC stays
        # 17 (→18 at L15).  Everything from L13 carries over (Bless, Shield of
        # Faith, two-tier Magic Weapon, the incoming-damage loop); the ONLY new
        # mechanics are the defender-side reaction and its counter.
        #
        # Flourish Parry (intercept_event): when an enemy hits us with a melee
        # attack we may, as a reaction, add CHA(5) to AC against that one attack
        # — flipping it to a miss iff it hit by 0–4 (we see the roll, Shield-
        # style, so we only react when it flips).  Free (the reaction is the only
        # cost).  Its DPR value is INDIRECT: a flipped hit deals no damage and
        # forces no concentration check → higher Bless uptime (guide: ~82% → 85%)
        # → marginally better hit rate.
        #
        # Flourish Counter: on a parry-flip we may make a free weapon attack at
        # the attacker carrying Brutality::bleed (sap mastery + CHA(5) flat
        # damage) WITHOUT spending a brutality charge — direct extra DPR.  Free
        # 1/LR, then by spending Second Wind charges.  EV-MAX MODELING DECISION:
        # in the threshold-HP sim healing is free (HP never gates anything), so
        # we make ALL Second Winds available for counters rather than reserving
        # ~2–3 for healing as the guide does — flourish_counter = 6/day (1 free +
        # 5 Second Wind, PoH-boosted).  This is non-binding anyway (parry-flip
        # opportunities ≈ 4/day < 6), so in practice we counter EVERY flip.  May
        # read slightly above the 37.96 target vs the guide's reserved ~3 — that
        # is the deliberate full-EV-max choice, not a modeling error.
        #
        # Reaction model: the parry is gated once-per-round inside the policy
        # (decoupled from the once-per-combat AoO, per the guide's explicit "in
        # addition to … no other demands on our reaction" assumption).  No
        # engine reaction-economy / TurnEndEvent — see PROGRESS Open threads.
        "weapon": "longsword",
        "attack_bonus": 10,         # PB 5 + CHA 5 (unchanged from L13)
        "damage_dice": (1, 8),
        "damage_bonus": 7,          # CHA 5 + dueling 2 (unchanged)
        "weapon_mastery": "sap",
        "char_hp": 102,             # build guide: 102.5 (Aid +5 is HP-only)
        "cha_mod": 5,               # Flourish Parry AC bonus & bleed flat damage
        "flourish_parry": True,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2 (+2 SoF)
        },
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (3, 1),
            "spell_slot_3": (3, 0),
            "spell_slot_2": (3, 0),
            "spell_slot_1": (4, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),
            # Flourish Counter budget: 1 free + 5 Second Wind (PoH-boosted), all
            # available for counters (threshold HP → healing is free).  LR pool.
            "flourish_counter": (6, 0),
        },
        "magic_weapon_casts_per_day": 1,        # +1 cast (one L2 slot)
        "magic_weapon_plus2_casts_per_day": 3,  # +2 casts (three L3 slots)
        "bless": True,
        "shield_of_faith": True,
    },
    15: {
        # Fighter-08: Resilient (DEX) feat.  A near-pure DATA ROW against the
        # L14 machinery — no new engine primitives, no policy change.  Resilient
        # gives +1 DEX (→17) and DEX-save proficiency, but DEX is NOT our
        # CHA-based attack stat (Pact of the Blade), so attack/damage are
        # UNCHANGED, and medium armor already caps DEX-to-AC at +2 so AC is
        # unchanged too.  The dex_save bonus (PB 5 + DEX 3 = +8) was written into
        # this row and L16's by hand and called "DPR-irrelevant in the threshold-HP
        # model"; s55 derives all six saves at every level (`save_bonuses`) and both
        # rows were removed because the derivation reproduces the +8 exactly.  It is
        # also no longer DPR-irrelevant: the enemy's §6 save channel resolves against
        # these, and a failed save can cost a turn.
        #
        # The real movers are all on the MONSTER side (CR-15): enemy AC 17→18
        # (the main DPR drop — harder for us to hit), enemy to-hit +11→+12 (more
        # enemy hits → more concentration checks → lower Bless uptime), and enemy
        # damage 28→32 on hit (→ DC-16 concentration checks: max(10, 32//2)=16).
        # All three flow through the existing Bless-uptime / Flourish-Parry loop
        # with zero code change.
        #
        # Combat tactics are IDENTICAL to L14: bleed (not bluff) on every
        # flourish counter — the guide confirms bleed still beats bluff (~0.5
        # DPR) even at the higher monster AC — and the full-EV-max counter budget
        # (all 5 Second Winds → flourish_counter = 6/day, non-binding since
        # parry-flip opportunities ≈ 4/day).
        "weapon": "longsword",
        "attack_bonus": 10,         # PB 5 + CHA 5 (unchanged from L14)
        "damage_dice": (1, 8),
        "damage_bonus": 7,          # CHA 5 + dueling 2 (unchanged)
        "weapon_mastery": "sap",
        "char_hp": 102,             # unchanged (Resilient adds no HP)
        "cha_mod": 5,               # Flourish Parry AC bonus & bleed flat damage
        "flourish_parry": True,
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2 (+2 SoF)
        },
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (3, 1),
            "spell_slot_3": (3, 0),
            "spell_slot_2": (3, 0),
            "spell_slot_1": (4, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),
            "flourish_counter": (6, 0),
        },
        "magic_weapon_casts_per_day": 1,        # +1 cast (one L2 slot)
        "magic_weapon_plus2_casts_per_day": 3,  # +2 casts (three L3 slots)
        "bless": True,
        "shield_of_faith": True,
    },
    16: {
        # Fighter-09: Tactical Master + Indomitable.  The DPR mover is the WEAPON
        # SWITCH, longsword → RAPIER, exploiting the difference between the two
        # masteries:
        #   - sap (longsword) only matters ONCE per turn (enemy disadvantage on
        #     its next attack; reapplying is wasted).
        #   - vex (rapier) reapplies EVERY attack (advantage on our next attack
        #     vs the target), so the advantage chain now runs ~100% instead of
        #     the ~1/3 we got from spending a bluff for vex each turn.
        # Tactical Master then lets us, once per turn, override the rapier's vex
        # with SAP on one attack (mastery_override="sap") to keep sap's defensive
        # value; we bluff on that same attack to re-add vex (so it carries both)
        # and to keep the save-advantage.  See WarAngelPolicy.decide / on_hit.
        #
        # Indomitable (engine: failed-save reroll decision point): 1/LR, reroll a
        # failed save with +9 (fighter level).  We only model concentration
        # checks; the policy spends it greedily on the first failed check that a
        # reroll is likely to clear AND that still has rounds left to protect
        # (see on_failed_save).  DPR impact is tiny (~0.05 — prevents ~one Bless
        # drop/day); modeled for fidelity, per the guide's "cherry on top".
        #
        # NO GUIDE DPR TARGET: the guide's L16 figure is a literal XXXX
        # placeholder and the R prototype stops at L10, so L16 is validated for
        # CONSISTENCY (DPR > L15, telemetry sanity, no L1–15 regression), not
        # against an external number.  The enemy is UNCHANGED from L15 (the L17
        # guide section confirms Monster AC stays 18, +12 to-hit, 32 damage / DC-
        # 16) — the entire L16 gain is on our side.
        "weapon": "rapier",
        "attack_bonus": 10,         # PB 5 + CHA 5 (unchanged from L15)
        "damage_dice": (1, 8),      # rapier = 1d8 piercing (same dice as longsword)
        "damage_bonus": 7,          # CHA 5 + dueling 2 (unchanged)
        "weapon_mastery": "vex",    # ← rapier (was sap); vex on every attack
        "tactical_master": True,    # 1 attack/turn overridden vex → sap
        "char_hp": 102,
        "cha_mod": 5,               # Flourish Parry AC bonus & bleed flat damage
        "flourish_parry": True,
        "indomitable_bonus": INDOMITABLE_BONUS,  # +9 reroll (fighter level)
        "extra_base_stats": {
            "ac": 18,               # breastplate 14 + DEX 2 + shield 2 (+2 SoF)
        },
        "resources": {
            "war_priest": (3, "full"),
            "channel_divinity": (3, 1),
            "spell_slot_3": (3, 0),
            "spell_slot_2": (3, 0),
            "spell_slot_1": (4, 0),
            "pact_magic_slot": (1, "full"),
            "free_cast": (1, 0),
            "action_surge": (1, "full"),
            "brutality": (5, "full"),
            "flourish_counter": (6, 0),
            "indomitable": (1, 0),  # 1/LR (LR-only restore)
        },
        "magic_weapon_casts_per_day": 1,        # +1 cast (one L2 slot)
        "magic_weapon_plus2_casts_per_day": 3,  # +2 casts (three L3 slots)
        "bless": True,
        "shield_of_faith": True,
    },
}

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


# ---------------------------------------------------------------------------
# Hit Dice (design/healing.md §7 / §11.2)
# ---------------------------------------------------------------------------
# Class levels per character level, from the guide's progression summary
# (38_the_war_angel.txt): Fighter (d10) / Warlock (d8) / Cleric (d8).  The pool is
# MIXED, which is why HitDiceSpec takes a list rather than one die size — dice are
# spent largest-first, as a player healing up would.
#
# CON = 8 (guide's point buy) → CON modifier **-1**.  The build dumps CON and buys
# HP back with Dwarven Toughness + the Tough feat, neither of which touches Hit
# Dice.  A negative modifier is exactly why HitDiceSpec floors each die at 0: RAW a
# Hit Die can never reduce your hit points.  Mean-field per die: d10 → 4.5, d8 → 3.5.
_WA_CLASS_LEVELS: dict[int, tuple[int, int, int]] = {
    #  char level: (fighter, warlock, cleric)
    1: (1, 0, 0),  2: (1, 1, 0),  3: (1, 1, 1),  4: (1, 1, 2),
    5: (1, 1, 3),  6: (1, 1, 4),  7: (2, 1, 4),  8: (3, 1, 4),
    9: (4, 1, 4), 10: (5, 1, 4), 11: (6, 1, 4), 12: (6, 1, 5),
    13: (6, 1, 6), 14: (7, 1, 6), 15: (8, 1, 6), 16: (9, 1, 6),
}
# ---------------------------------------------------------------------------
# Ability scores → saving-throw bonuses (DERIVED, s55)
# ---------------------------------------------------------------------------
# Until s55 only `con_save` was declared, and only at L13-L16, so the other five
# saves read 0 at EVERY level — the same failure mode as the missing `ac`, and
# wider, because it reached the levels that DID declare an AC.  The enemy's §6 save
# channel was therefore measuring a character with no save bonuses.
#
# DERIVED RATHER THAN DECLARED, and the s49 rule is the reason this is the right
# call rather than the convenient one: declare a fact, derive it only when the two
# facts CANNOT vary independently.  A 5e saving throw bonus IS `ability modifier +
# (PB if proficient)` — the same kind of necessity that made an interval method a
# property of its statistic in s48, not the kind of coincidence that made
# `sum_rule` look derivable from `crossed` until it wasn't.  Sixteen hand-written
# rows would also be 96 independent numbers, i.e. 96 chances to mistype one.
#
# EVERY INPUT IS STATED IN THE GUIDE'S HEADER (38_the_war_angel.txt:17-32), so this
# is reading, not modelling from memory (per-feature ritual rule 1):
#
#   Point-Buy Stats   STR 08  DEX 15  CON 08  INT 08  WIS 15(+1)=16  CHA 15(+2)=17
#   lvl-06  shadow touched  +1 CHA (CHA=18)
#   lvl-09  ASI             +2 CHA (CHA=20)
#   lvl-11  mage slayer     +1 DEX (DEX=16)
#   lvl-15  resilient (DEX) +1 DEX (DEX=17)   ← and DEX SAVE PROFICIENCY
#
# (lvl-19's epic boon of speed is past this build's L16 ceiling and is omitted.)
#
# AND THE DERIVATION IS CHECKED AGAINST THE GUIDE, not just against itself.  The
# guide states one complete save line, at L15 (line 600): "STR(+4), DEX(+8),
# CON(+4), INT(-1), WIS(+3), CHA(+5)".  `save_bonuses(15)` reproduces all six
# exactly, which is what makes the other fifteen levels trustworthy — asserted in
# `tests/test_war_angel.py`, not left as this comment.
_BASE_ABILITY_SCORES: dict[str, int] = {
    "str": 8, "dex": 15, "con": 8, "int": 8, "wis": 16, "cha": 17,
}

#: character level → the score changes that ARRIVE at it (cumulative from there on).
_ABILITY_SCORE_CHANGES: dict[int, dict[str, int]] = {
    6: {"cha": 1},      # shadow touched
    9: {"cha": 2},      # ASI
    11: {"dex": 1},     # mage slayer
    15: {"dex": 1},     # resilient (DEX)
}

#: ability → the character level its SAVE proficiency arrives.
#:
#: STR and CON come from the STARTING class (Fighter-01) and nothing else does:
#: multiclassing grants no saving-throw proficiencies, so Cleric's and Warlock's
#: WIS/CHA never arrive however many levels of each the build takes.  The guide's own
#: L15 line is the evidence rather than a rules memory — it shows WIS at +3 and CHA at
#: +5, the bare modifiers, while STR and CON carry the full +5 PB.
_SAVE_PROFICIENCY_AT: dict[str, int] = {"str": 1, "con": 1, "dex": 15}

ABILITIES = ("str", "dex", "con", "int", "wis", "cha")


def ability_scores(level: int) -> dict[str, int]:
    """The six ability SCORES at *level*, base plus everything that has arrived."""
    scores = dict(_BASE_ABILITY_SCORES)
    for arrives_at, changes in _ABILITY_SCORE_CHANGES.items():
        if level >= arrives_at:
            for ability, delta in changes.items():
                scores[ability] += delta
    return scores


def ability_mod(score: int) -> int:
    """A 5e ability modifier.  Floor division is correct for scores below 10:
    ``(8 - 10) // 2 == -1``, which is the CON/STR/INT modifier this build dumps to."""
    return (score - 10) // 2


def ability_mods(level: int) -> dict[str, int]:
    """The six ability MODIFIERS at *level*."""
    return {a: ability_mod(s) for a, s in ability_scores(level).items()}


def save_bonuses(level: int) -> dict[str, int]:
    """The six ``*_save`` base stats at *level*: modifier + PB where proficient.

    Keyed the way the verbs read them (``resolve_saving_throw`` takes a stat name),
    so this drops straight into ``Entity.base_stats`` and no level can silently
    omit one.
    """
    mods, pb = ability_mods(level), proficiency_bonus(level)
    return {
        f"{ability}_save": mods[ability]
        + (pb if level >= _SAVE_PROFICIENCY_AT.get(ability, 10 ** 6) else 0)
        for ability in ABILITIES
    }


# CON modifier — now READ FROM the table above rather than restated, since a second
# copy of a number the table already determines is a second source for it.  The build
# dumps CON and buys HP back with Dwarven Toughness + the Tough feat, neither of which
# touches Hit Dice.  A negative modifier is exactly why HitDiceSpec floors each die at
# 0: RAW a Hit Die can never reduce your hit points.
WAR_ANGEL_CON_MOD = ability_mod(_BASE_ABILITY_SCORES["con"])

# WIS modifier, same source.  Prayer of Healing is a CLERIC spell, so its
# "spellcasting ability modifier" is WIS, not the build's headline CHA.  Kept as a
# module constant rather than a `wis_mod` base stat because nothing else on this build
# reads WIS — adding a stat for one consumer would be the wrong trade.  WIS never
# changes on this build, so the level-free base score is the whole story.
WAR_ANGEL_WIS_MOD = ability_mod(_BASE_ABILITY_SCORES["wis"])


def _war_angel_hit_dice(level: int) -> HitDiceSpec:
    fighter, warlock, cleric = _WA_CLASS_LEVELS[level]
    dice = [(fighter, 10)] if fighter else []
    d8 = warlock + cleric
    if d8:
        dice.append((d8, 8))
    return HitDiceSpec(dice=dice, con_mod=WAR_ANGEL_CON_MOD, rule="character")


def make_war_angel(level: int) -> Entity:
    """Build the War Angel Entity for the given level (1–5 for now)."""
    if level not in LEVELS:
        raise NotImplementedError(
            f"War Angel level {level} not yet implemented (have {sorted(LEVELS)})."
        )
    data = LEVELS[level]
    return attach_hit_dice(Entity(
        name=f"WarAngel-L{level}",
        hp=data["char_hp"],
        base_stats={
            "attack_bonus": data["attack_bonus"],
            "damage_dice": data["damage_dice"],
            "damage_bonus": data["damage_bonus"],
            "weapon_mastery": data["weapon_mastery"],
            # All six saving throws at EVERY level, derived (see `save_bonuses`).
            # Before s55 only `con_save` was here, hand-written at L13-L16, so five
            # of six saves read 0 everywhere and all six read 0 below L13.
            **save_bonuses(level),
            # Per-level extras that are genuinely declared rather than derived.
            # Listed AFTER the saves so a row could deliberately override one; no
            # row does, and `test_no_level_row_restates_a_derived_save` keeps it
            # that way, because an override would be a silent second source.
            **data.get("extra_base_stats", {}),
        },
        resources=_make_resources(data),
    ), _war_angel_hit_dice(level))




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

    #: The §6.3 substream owner for this policy's own per-combat pre-rolls.
    #: DECLARED rather than derived from the class name: it is a DICE-STREAM
    #: IDENTITY, so changing it re-baselines every seeded number, and a label
    #: that says so is harder to rename by accident than ``__name__``.
    stream_owner: str = "war_angel_policy"

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
        # Flourish Parry / Counter (L14+): the AC bonus & bleed flat damage = CHA mod.
        self._flourish_parry: bool = bool(LEVELS[level].get("flourish_parry", False))
        self._cha_mod: int = LEVELS[level].get("cha_mod", 0)
        # Tactical Master (L16+): once per turn, override the rapier's native vex
        # with sap on one attack (we then bluff on it to re-add vex).
        self._tactical_master: bool = bool(LEVELS[level].get("tactical_master", False))
        # Indomitable (L16+): the +bonus on the 1/LR failed-save reroll (0 = off).
        self._indomitable_bonus: int = LEVELS[level].get("indomitable_bonus", 0)
        # Per-combat state, (re)initialised by on_combat_start.
        self._aoo_round: int = 1
        # Last round we used Flourish Parry — the once-per-round reaction gate.
        # Reset per combat (round numbers restart at 1 each combat).
        self._last_parry_round: int = -1
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
        self._aoo_round = rng.roll_one(
            self._rounds_per_combat, stream=("policy", self.stream_owner))
        # Reset the once-per-round Flourish Parry gate; round numbers restart at
        # 1 each combat, so a stale value would mis-gate the new combat.
        self._last_parry_round = -1

    # -- decision point ---------------------------------------------------

    def decide(self, snapshot: GameState) -> list[Choice]:
        # decide() is the turn-start commit point: reset per-turn flags here.
        self._bluffed_this_turn = False
        choices: list[Choice] = []

        # L13 round 1: the action goes to casting Bless and the bonus action to
        # Shield of Faith (War God's Blessing) — both applied as combat-start
        # buffs in the daily plan, so the policy just suppresses the normal
        # action attack and the War Priest BA this round.  Action Surge attacks
        # are still allowed (design decision), as is the AoO; Wrathful Smite is
        # suppressed in on_hit (the BA is spent on Shield of Faith).
        bless_turn = self.level >= 13 and snapshot.round_number == 1

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
        # at L8+ when the surge is taken (BA stays free for smite on TS hit), or
        # on an L13 bless turn (BA spent on Shield of Faith).
        skip_wp = (self.level >= 8 and has_surge) or bless_turn
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
        # On an L13 bless turn the action is spent casting Bless → no attack.
        if not bless_turn and snapshot.resources.get("action", 0) >= 1:
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

        # Tactical Master (L16+): override the first ON-TURN attack's native vex
        # (rapier) with sap, applying sap's once-per-turn defensive value while
        # the rest of our attacks keep vexing.  The on_hit bluff fires on this
        # same attack (first hit) to re-add vex — so it carries both sap AND vex
        # — and to grant the concentration save-advantage.  (We skip the AoO: its
        # reaction-cost slot is the once-per-combat opportunity attack, not part
        # of our action sequence.)
        if self._tactical_master:
            for ch in choices:
                if ch.action_type == "attack" and ch.cost != "reaction":
                    ch.mastery_override = "sap"
                    break

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
        # The +10 bonus and the channel_divinity cost come FROM DATA
        # (guided_strike); the gates (no AoO, only when it flips) stay policy.
        rescue = interpret_roll_bonus(GUIDED_STRIKE)
        if ctx.resources.get(rescue.resource_type, 0) < rescue.count:
            return None
        if ctx.missed_by > rescue.bonus:            # the bonus wouldn't flip it
            return None
        return MissResponse(
            resource_cost={rescue.resource_type: rescue.count},
            bonus=rescue.bonus,
        )

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
        # Suppress Wrathful Smite on an L13 bless turn: the bonus action is spent
        # on Shield of Faith (applied as a combat-start buff), so although the
        # scheduler's turn economy still shows the BA free, it is not ours to use.
        bless_turn = self.level >= 13 and ctx.round_number == 1
        want_smite = (
            self.level >= 6
            and not bless_turn
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
        self_status: "str | None" = None

        if want_bluff:
            # Bluff's effects come FROM DATA (brutality_bluff): vex applied to the
            # target + the save-advantage self-status (unlocked at L13 with
            # concentration: advantage on our next CON save, which the
            # concentration check reads).  The brutality CHARGE is policy
            # arbitration → stays here.
            resource_cost["brutality"] = 1
            bluff = interpret_on_hit_effects(BRUTALITY_BLUFF)
            extra_masteries = list(bluff.target_masteries)
            self_status = bluff.self_statuses[0] if bluff.self_statuses else None
            self._bluffed_this_turn = True  # commit: prevent a second bluff this turn

        if want_smite:
            # The slot PRIORITY (free_cast → pact → cleric L1) is build-specific
            # arbitration → stays here; the rider's dice + action economy come
            # from the Wrathful Smite DATA via the effect-interpreter.
            slot = self._next_smite_slot(ctx.resources)
            resource_cost[slot] = resource_cost.get(slot, 0) + 1
            rider = interpret_hit_rider(WRATHFUL_SMITE)
            extra_dice = list(rider.extra_damage_dice)
            action_cost = rider.action_cost

        return HitResponse(
            resource_cost=resource_cost,
            extra_damage_dice=extra_dice,
            extra_masteries=extra_masteries,
            action_cost=action_cost,
            self_status_on_hit=self_status,
        )

    def _next_smite_slot(self, resources: dict) -> "str | None":
        for name in self._SMITE_SLOT_PRIORITY:
            if resources.get(name, 0) >= 1:
                return name
        return None

    # -- in-flight interception: Flourish Parry + Flourish Counter (L14+) --

    def on_incoming_hit(self, ctx: IncomingAttackContext) -> "InterceptResponse | None":
        """Flourish Parry (intercept_event) + Flourish Counter (L14+).

        Flourish Parry: when an enemy melee attack HITS us, we may react to add
        CHA(5) to AC against that one attack.  We see the roll first (Shield-
        style), so we react ONLY when +CHA would actually flip the hit to a miss
        — i.e. when it hit by less than CHA (`ctx.hit_margin < cha_mod`).  Parry
        is free; its DPR value is indirect (a flipped hit forces no concentration
        check → higher Bless uptime).  Gated once per round (the policy is the
        reaction economy here — decoupled from the AoO per the guide).

        Flourish Counter: on a flip, if a flourish_counter charge remains, make a
        free bleed counter (sap mastery + CHA flat damage, no brutality charge)
        against the attacker.  We counter every flip while the budget lasts (full
        EV-max — see the L14 data note); the budget is non-binding in practice.
        """
        if not self._flourish_parry:
            return None
        # Melee-only: Flourish Parry triggers on a MELEE attack that hits us (2024
        # Battle Master).  Read the incoming attack's range axis (modality taxonomy)
        # rather than assuming melee; a ranged hit does not provoke the parry.  None
        # (an attacker that did not tag a range) is treated as melee for back-compat.
        if ctx.range_ == "ranged":
            return None
        # Once-per-round reaction gate.
        if self._last_parry_round == ctx.round_number:
            return None
        # The parry's AC bonus comes FROM DATA (flourish_parry: an intercept_event
        # flat AC bump), resolved against our CHA mod.  The DECISION to react —
        # only when the bump actually flips the hit to a miss (we see the roll;
        # hit_margin >= 0, flip iff ac_bonus > hit_margin) — stays policy.
        parry = interpret_intercept(FLOURISH_PARRY, context={"charisma": self._cha_mod})
        ac_bonus = parry.ac_bonus
        if ac_bonus <= ctx.hit_margin:
            return None

        # Commit the parry for this round (free — no engine resource).
        self._last_parry_round = ctx.round_number

        # Flourish Counter iff a charge remains.
        counter = None
        resource_cost: dict[str, int] = {}
        if ctx.resources.get("flourish_counter", 0) >= 1:
            resource_cost["flourish_counter"] = 1
            # Bleed's effects come FROM DATA (brutality_bleed): sap mastery + the
            # +CHA flat damage, the latter resolved against the policy's CHA mod
            # (the interpreter's first runtime-dependent value).  The counter
            # grants bleed for FREE (no brutality charge) — that cost override is
            # policy arbitration, so only flourish_counter is spent here.
            bleed = interpret_on_hit_effects(
                BRUTALITY_BLEED, context={"charisma": self._cha_mod}
            )
            counter = CounterSpec(
                target=ctx.attacker,
                weapon_stat="attack_bonus",
                masteries=list(bleed.target_masteries),
                extra_flat_damage=bleed.extra_flat_damage,
            )

        return InterceptResponse(
            ac_bonus=ac_bonus,
            # The parry IS a reaction (the guide: "can use rxn to add CHA(5) to AC"),
            # and the Counter rides the SAME one ("as part of rxn"), so one record
            # covers both. No economy debit — the guide prices the parry and the
            # opportunity attack as both happening, knowing they compete in RAW; this
            # records what is taken so that double-booking shows up in the output.
            reaction_by=ctx.defender.id,
            resource_cost=resource_cost,
            counter=counter,
        )

    # -- failed-save rescue: Indomitable (level 16+) ----------------------

    def on_failed_save(self, ctx: FailedSaveContext) -> "SaveRerollResponse | None":
        """Indomitable: spend the 1/LR reroll on a failed save.

        Policy = "greedy among positive-value failures".  Why greedy is (near-)
        optimal in our current model:
          - Every concentration check is the SAME DC (16), and the reroll
            (fresh d20 + con_save + Bless + 9) clears it with ~100% probability,
            so there is no "save it for a check we're likelier to win".
          - Failures are scarce (~1–2/day) vs a 1/day resource, so husbanding
            risks never using it; expected regret from waiting > expected gain.
          - The only thing that varies is how many Bless-rounds the rescue
            protects (∝ rounds left in the combat), which we cannot predict.
        So we spend it on the FIRST failed check that (a) a reroll is likely to
        clear and (b) still has a round of the combat left to protect.

        Gates:
          - off below L16 (no Indomitable);
          - concentration checks only (the only save we model);
          - 1/LR resource must be available;
          - DC-ASSESSMENT: only spend if the reroll's success probability —
            computed from the FLAT save bonus (Bless ignored → conservative) —
            clears INDOMITABLE_MIN_SUCCESS.  Inert at the uniform DC-16 (always
            ~90%+); becomes load-bearing once we model weaker/variable-DC saves;
          - LAST-ROUND FLOOR: decline on the final round, where a saved Bless
            has no future rounds of this combat to protect (Bless is recast
            fresh each combat, so a rescue's value is bounded by the rounds
            remaining here).
        """
        if self._indomitable_bonus <= 0:
            return None
        if ctx.save_kind != "concentration":
            return None
        if ctx.resources.get("indomitable", 0) < 1:
            return None
        # Last-round floor: no remaining rounds for Bless to protect.
        if ctx.round_number >= self._rounds_per_combat:
            return None
        # DC-assessment: P(reroll clears DC) using the flat save bonus only.
        needed = ctx.dc - ctx.save_bonus - self._indomitable_bonus
        success_prob = (21 - min(20, max(1, needed))) / 20 if needed <= 20 else 0.0
        if success_prob < INDOMITABLE_MIN_SUCCESS:
            return None
        return SaveRerollResponse(
            bonus=self._indomitable_bonus,
            resource_cost={"indomitable": 1},
        )


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
        # Magic Weapon cast budgets, by tier.  `magic_weapon_casts_per_day` is
        # the +1 budget (level-2 slots, all levels); `magic_weapon_plus2_casts_
        # per_day` is the +2 budget (level-3 slots, from level 12).  We cast +2
        # first while those slots remain, then fall back to +1 — strictly more
        # damage per cast, and order across statistically-identical combats does
        # not affect mean DPR.
        self._mw_plus1_budget: int = data.get("magic_weapon_casts_per_day", 0)
        self._mw_plus2_budget: int = data.get("magic_weapon_plus2_casts_per_day", 0)
        self._mw = DurationBuffTracker()
        self._mw_plus1_used: int = 0
        self._mw_plus2_used: int = 0
        self._poh_cast: bool = False
        # Combat-clock buffs cast at the start of every combat (L13): Bless
        # (concentration, +1d4 attack/saves, from a cleric L1 slot) and Shield
        # of Faith (War God's Blessing, +2 AC, non-concentration, 1 Channel
        # Divinity).  Greedy: cast each whenever its resource is available.
        self._cast_bless: bool = bool(data.get("bless", False))
        self._cast_shield_of_faith: bool = bool(data.get("shield_of_faith", False))

    # -- per-day reset ----------------------------------------------------

    def _reset_day(self) -> None:
        self._mw.reset()
        self._mw_plus1_used = 0
        self._mw_plus2_used = 0
        self._poh_cast = False

    # -- Magic Weapon (before_combat) ------------------------------------

    def before_combat(self, ctx: BeforeCombatContext) -> None:
        if ctx.combat_num == 1:
            self._reset_day()

        minute = ctx.combat_start_minute

        # Cast schedule (stated explicitly per build, not a hidden engine rule):
        #   - cast before combat 1;
        #   - before combat N>1, cast only if Magic Weapon is currently INACTIVE
        #     and an earmarked slot remains.
        # Tier choice: spend a +2 (level-3) cast first while any remain, else a
        # +1 (level-2) cast.  Each tier consumes its own slot resource.
        budget_left = (
            (self._mw_plus2_budget - self._mw_plus2_used)
            + (self._mw_plus1_budget - self._mw_plus1_used)
        )
        want_cast = (
            budget_left > 0
            and (ctx.combat_num == 1 or not self._mw.active_at(minute))
        )
        if want_cast:
            if self._mw_plus2_used < self._mw_plus2_budget:
                self._mw.cast(minute, MAGIC_WEAPON_DURATION_MIN, MAGIC_WEAPON_PLUS2)
                self._mw_plus2_used += 1
                self.character.resources.consume("spell_slot_3")
            else:
                self._mw.cast(minute, MAGIC_WEAPON_DURATION_MIN, MAGIC_WEAPON_PLUS1)
                self._mw_plus1_used += 1
                self.character.resources.consume("spell_slot_2")

        # Sync the entity's modifier stack to the strongest MW tier active this
        # combat (0 = inactive → no modifier).
        self._sync_magic_weapon(self._mw.strongest_at(minute))

        # Combat-clock buffs (L13): Bless (concentration) + Shield of Faith.
        # Applied AFTER the per-combat status clear (which runs inside
        # _run_combat, after this hook) is irrelevant for these because Bless
        # rides the modifier stack and concentration lives in a dedicated
        # Entity field — neither is touched by StatusSet.clear().
        self._sync_bless()
        self._sync_shield_of_faith()

    def _sync_magic_weapon(self, bonus: int) -> None:
        self.character.remove_modifier("magic_weapon")
        if bonus > 0:
            # Magic Weapon's flat attack+damage buff comes FROM DATA; the cast
            # TIER (+1 vs +2) is policy arbitration, passed in as a context value.
            for mod in interpret_modifiers(
                MAGIC_WEAPON, source="magic_weapon",
                context={"magic_weapon_bonus": bonus},
            ):
                self.character.add_modifier(mod)

    def _sync_bless(self) -> None:
        """Re-cast Bless for this combat if a cleric L1 slot remains.

        Bless is a rolled-dice modifier (+1d4) on both attack rolls and CON
        saves (the only stats that affect DPR), under source "bless".  We remove
        the prior combat's copy and re-add if a slot is available — greedy and
        rest-agnostic.  Concentration is recorded on the Entity so the D3b
        incoming-damage loop knows what to drop on a failed save.
        """
        if not self._cast_bless:
            return
        self.character.remove_modifier("bless")
        self.character.concentration = None
        if self.character.resources.available("spell_slot_1") >= 1:
            self.character.resources.consume("spell_slot_1")
            # Bless's modifiers (+1d4 on attack_bonus + con_save) come FROM DATA
            # via the effect-interpreter, replacing the hand-built Modifiers.
            for mod in interpret_modifiers(BLESS, source="bless"):
                self.character.add_modifier(mod)
            self.character.concentration = "bless"

    def _sync_shield_of_faith(self) -> None:
        """Re-cast Shield of Faith (War God's Blessing) for this combat if a
        Channel Divinity charge remains: +2 AC, non-concentration, whole combat.

        Spending CD here (greedily, once per combat) reserves it ahead of Guided
        Strike (which draws the same pool via on_miss) → ~1 CD/day left for
        Guided Strike, matching the build guide.
        """
        if not self._cast_shield_of_faith:
            return
        self.character.remove_modifier("shield_of_faith")
        if self.character.resources.available("channel_divinity") >= 1:
            self.character.resources.consume("channel_divinity")
            # +2 AC comes FROM DATA (war_gods_blessing, a flat apply_modifier).
            for mod in interpret_modifiers(
                WAR_GODS_BLESSING, source="shield_of_faith"
            ):
                self.character.add_modifier(mod)

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
        # PRAYER OF HEALING DOES TWO JOBS, and until s45 this hook modelled only
        # one of them (healing.md §11.2).  Verified 2024 text: up to five creatures
        # "gain the benefits of a Short Rest and also regain 2d8 Hit Points"
        # (+ the caster's spellcasting modifier).  The recharge above is the first
        # half; the two lines below are the second and the third:
        #
        #  (i) the 2d8 + WIS heal.  MEAN-FIELD (12.0), not rolled — an out-of-combat
        #      heal that drew from the shared RNG stream would shift every
        #      subsequent die and break every GOLDEN_DPR point (healing.py's module
        #      docstring).  Only the CHARACTER is healed: the roster is character +
        #      enemy, and enemies are never healed (§5).  A real party roster would
        #      extend the target list to five allies, which is why HealSpec takes a
        #      list rather than a single target.
        #  (ii) the Hit Dice window.  Spending Hit Dice IS one of the benefits of a
        #      Short Rest, so RAW this is a genuine second window — correcting the
        #      assumption that PoH grants none.  It costs nothing and changes no
        #      number: spend-all drains the pool at whichever window comes first and
        #      Hit Dice restore only on a LONG rest, so the second heals zero.
        resolve_healing(
            self.character,
            HealSpec(dice=(2, 8), flat=WAR_ANGEL_WIS_MOD,
                     targets=[self.character]),
            mean_field=True, telemetry=ctx.telemetry, context="between",
        )
        spend_hit_dice_at_short_rest([self.character], ctx.telemetry)
        self._poh_cast = True


# ---------------------------------------------------------------------------
# Enemy policy: NONE.  This module constructs no enemy policy (§3.4, step 5b) —
# `RunConfig.enemy` declares the model and `evaluation/enemy.py` installs it, so the
# enemy that forces concentration checks on Bless is the framework's, not this build's.
# Sap disadvantage on the enemy's first attack each turn is applied by the character's
# longsword via the existing `sapped` status, read in resolve_attack_roll — nothing any
# enemy policy needs to do.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Full day-runner assembly (used by the validation harness)
# ---------------------------------------------------------------------------

def make_day_runner(level: int, rng: "SeededRNG", rounds_per_combat: int = 4):
    """Assemble (DayRunner, character, dummy) for the given level.

    Wires the character policy plus, for level 5+, the daily-plan hooks (Magic
    Weapon / Prayer of Healing).  The enemy is a PASSIVE target at every level
    (§3.4, step 5b): it carries the definitive table's full stat block and no
    policy, and the framework's seam installs whatever enemy a run declares.
    """
    char = make_war_angel(level)
    dummy = enemy_stats.make_baseline_enemy(level)
    policy = WarAngelPolicy(level=level, target=dummy,
                            rounds_per_combat=rounds_per_combat)
    policies: dict[int, object] = {char.id: policy}

    # THE ENEMY NEVER ACTS HERE (evaluation_framework.md §3.4, step 5b).  Until s52 the
    # factory installed an enemy policy off this build's own data row, so "whether the
    # enemy acts" was a character-build property.  It is now a declared RunConfig.enemy
    # and evaluation/enemy.py installs the policy over this roster; a factory run on its
    # own faces a passive target carrying the definitive table's full stat block.

    before_combat = None
    between_combats = None
    if level >= 5:
        plan = WarAngelDailyPlan(character=char, level=level)
        before_combat = plan.before_combat
        between_combats = plan.between_combats

    runner = DayRunner(
        rng=rng,
        entities=[char, dummy],
        policies=policies,
        rounds_per_combat=rounds_per_combat,
        before_combat=before_combat,
        between_combats=between_combats,
    )
    return runner, char, dummy
