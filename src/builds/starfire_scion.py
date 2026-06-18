"""
starfire_scion.py — The Starfire Scion build: per-level stat blocks + daily-plan
policy.  The project's SECOND archetype — a WIS-based spellfire "blaster" gish
(Monk-08 Sun-Soul / Druid-12 Circle of Stars), chosen to force the save-FOR-damage
and dice-scaling axes the attack-roll War Angel never exercised.

Source of truth for intent:
  - design/build-guides/41_spellfire_scion.txt  (level-by-level notes + DPR
    *ceilings* — see the validation-framing note below)

This module covers L1, L4, L5, L9, L10: the melee baseline (L1), the level Starry
Form + Star Map come online (L4), the first "interesting" level where the blaster
identity converges (L5: Spellfire Adept → cantrip-scaled 2d8 Sacred Flame), the
martial spike (L9: EXTRA ATTACK + martial-arts-1d8 + first SHILLELAGH — thread B),
and the Sun-Soul Monk-6 spike (L10: SEARING ARC STRIKE — upcast Burning Hands as a
BA — thread A, now ALSO carrying the L9 thread-B martial bundle).  L2/L3 are
intentionally SKIPPED (no DPR-relevant mechanics — Druid spellcasting / wild-shape
utility), and so are L6-L8: L5-L8 are mechanically IDENTICAL on our side (PB stays
3, WIS mod stays +4 through L8 — only the enemy hardens).  All skips are easy to
backfill if a continuous ladder is ever wanted.

The build (see PROGRESS.md "Second archetype — STARFIRE SCION")
---------------------------------------------------------------
Point-buy DEX 16 (+3), CON 14 (+2), WIS 17 (+3 → 18 at L5), STR 8.  WIS is the
spell stat (Sacred Flame / Guiding Bolt / Starry-Form Archer); DEX is the
martial-arts melee stat (quarterstaff / unarmed).  It forces:

  1. **Save-FOR-DAMAGE** — Sacred Flame (DEX save-NEGATES) is the recurring
     bonus-action spell.  Its dice are pulled FROM DATA via
     ``interpret_save_spell(sacred_flame, {"character_level": L})`` — not a literal
     tuple — so the cantrip scaling (1d8 → 2d8 at L5) is data-driven (primitive #2).
  2. **Multiple attack PROFILES on one body** — quarterstaff (1d8+DEX), unarmed
     (1d6+DEX), Archer-form spell attack (1d8+WIS), Guiding Bolt (4d6).  The engine
     read a single ``actor.stat("damage_dice")`` for every attack (fine for the
     one-weapon War Angel); this build forced **per-attack damage override**
     (primitive #4 — a ``damage_dice``/``damage_bonus`` on the ``Choice``, threaded
     ``Choice → AttackRollEvent → DamageEvent``, defaulting to the entity stat).

VALIDATION FRAMING (important — differs from War Angel)
-------------------------------------------------------
The guide's per-level DPR numbers are **"all-hit CEILINGS," not targets**: they
assume every attack hits and the enemy always fails its save (no AC, no misses, no
successful saves).  This build has **no ground-truth DPR ladder** — producing
honest DPR for it is itself a goal of the model.  So validation is **consistency +
sanity** (like War Angel L16), NOT number-matching: per-hit / per-save damage math
exact; DPR grows monotonically up the ladder; computed DPR is a *plausible
fraction* of the ceiling given that level's hit / save-fail rates.  The
``ceiling_dpr`` field below is a loose UPPER BOUND, never a target.

Enemy model: the enemy save bonus + AC are live inputs sourced per character level
from ``reference/data/monster_ac_and_saves_by_level.csv`` (level == cr row; ``ac``
+ ``dex.save.mod``).  The enemy does NOT yet strike back (no incoming-damage loop
at these levels — exactly like War Angel before L13), so concentration is never
checked here and the Starry-Form/Flame-Blade concentration axis stays deferred.

What IS modeled here beyond the per-attack profiles
---------------------------------------------------
  3. **Fueled Spellfire** (Spellfire Adept, L5; engine primitive #5) — a
     CASTER-side POST-DAMAGE decision point: ×1/turn, when a SPELL deals RADIANT
     damage, expend up to 2 Hit Dice (d8) and add them to that damage roll.  Built
     as a general radiant rider hooked on the DamageEvent (the chokepoint BOTH
     the attack-roll path — Guiding Bolt — and the save-for-damage path — Sacred
     Flame — funnel through), so future radiant spells (Sunbeam, Fount of
     Moonlight) get it for free.  See ``StarfireScionPolicy.on_deal_damage`` and
     ``Scheduler._make_deal_damage_decider``.  Hit dice are a scarce per-day pool
     (5 at L5); the rider dice are NOT crit-doubled (a fixed expenditure).

What IS modeled at L10 (beyond the L1-L5 mechanics above)
--------------------------------------------------------
  4. **Searing Arc Strike** (Sun-Soul Monk-6) — upcast Burning Hands as a BONUS
     ACTION: a FIRE save-FOR-HALF spell (DEX save, full on fail / half on a save),
     base 3d6 + 1d6/slot-level resolved FROM DATA (interpret_save_spell, primitive
     #3) at the slot the policy chooses.  FP cost = 2 + 1/upcast-level, capped at
     floor(monk/2) = 3 FP at monk-6 → upcast to slot 2 (4d6).  Gated on having taken
     a weapon Attack action this turn (NOT a Guiding-Bolt/spell turn).  Because it is
     FIRE (not radiant), Fueled Spellfire does NOT fuel it — the cross-check that the
     damage_type gate, not just is_spell, does real work.

What IS modeled at L9-L10 (thread B — the martial bundle)
--------------------------------------------------------
  5. **Extra Attack** (monk-5, char L9+): the Attack action yields two weapon
     swings.  Pure policy — the primary swing costs the action, the follow-up
     costs nothing (the engine's standard Extra-Attack shape; no new primitive).
  6. **Martial-arts die 1d8** (monk-5): the unarmed strike die bumps 1d6 -> 1d8.
  7. **Shillelagh** (druid cantrip, char L9+): upgrades the quarterstaff damage
     die to 1d10 (the char L9-10 step of the 1d8/1d10/1d12/2d6 ladder — BAKED into
     the LEVELS row, the data-driven `scaling: ladder` deliberately DODGED) AND
     grants the OPTION to swing with WIS (spellcasting) instead of DEX.  Per the
     2024 spell that is an OPTION, not an auto-override, so the policy uses the
     HIGHER of the two ability modifiers (defaulting to WIS on a tie); here WIS(+4)
     beats DEX(+3).  Delivered via the per-attack override (primitive #4) — a
     weapon attack that uses a spellcasting stat, which is exactly the conflation
     the ATTACK-TAXONOMY flag (PROGRESS) calls out; we reuse `weapon_stat=
     "spell_attack_bonus"` as the numeric WIS to-hit WITHOUT rebuilding engine
     vocabulary (that typology is deferred, user-directed).  Cast as the turn-1
     bonus action (guide 41:539); modeled by withholding the turn-1 BA damage
     option (the BA is spent on the cast), so it then persists the whole combat.

What is NOT modeled here (deferred — see PROGRESS "Open threads")
----------------------------------------------------------------
  - **Elemental Adept (fire)** (L8): fire-resistance bypass (moot — the dummy has
    no resistances) + 1->2 die high-grading (a small per-die `replace` modifier).
  - **Starry Form: Chalice** (extra healing — DPR-irrelevant) and **Dragon** (a
    concentration-save floor — moot without the incoming-damage loop).
  - **Flame Blade** (concentration L2 spell — the melee-rotation alternative),
    **Stunning Strike**, **Guiding Bolt's advantage grant → allies** (modeled as a
    plain 4d6 attack), multi-enemy AoE / spatial, wild-shape beast forms, healing.

Ability-online timeline (abridged; full version in git history / the guide)
---------------------------------------------------------------------------
  L1  Monk-1.  Unarmored defense.  Martial arts (1d6): quarterstaff action + BA
        unarmed strike.  Spellfire Spark → Sacred Flame (1d8), castable as a BA
        xPB/LR.  [Melee bread-and-butter; first save-for-damage delivery.]
  L4  +Druid-3 (Stars).  Star Map → free Guiding Bolt xWIS/LR (ATTACK roll, 4d6).
        Starry Form (Archer = BA ranged spell attack 1d8+WIS).  L2 spells.
  L5  +Druid-4.  Spellfire Adept: +1 WIS (→18); Fueled Spellfire (deferred);
        cantrip scaling → Sacred Flame 2d8.  [Blaster identity online.]
  L9  Extra Attack; martial arts 1d8.    L10 Searing Arc Strike (upcast Burning
        Hands, BA).    L12 WIS 20.    L17 Sacred Flame 4d8.    (see the guide)

Engine-capacity build order (see PROGRESS):
  1. [DONE] save-FOR-damage resolution path (negates + for-half).
  2. [DONE] cantrip / level_reference dice scaling (Sacred Flame by char level).
  3. [DONE] upcast `increment` scaling (Searing Arc Strike) — wired at L10 (BA,
     FIRE save-for-half, upcast Burning Hands to slot 2 = 4d6 via interpret_save_spell).
  4. [DONE] per-attack damage override (the multi-weapon gish primitive) —
     Choice.damage_dice/damage_bonus → AttackRollEvent → DamageEvent.
  5. [DONE, this session] Fueled Spellfire — a caster-side post-damage decision
     point (Policy.on_deal_damage → DamageRiderResponse), threaded through
     resolve_damage as `rider_decider`; gated on "spell radiant damage" via
     damage_type + is_spell threaded Choice → events → DamageEvent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..content import interpret_save_spell, interpret_scaled_dice, load_abilities
from ..day_runner import DayRunner
from ..entity import Entity
from ..modifiers import Modifier
from ..policy import (
    Choice,
    DamageRiderResponse,
    DealDamageContext,
    GameState,
    HitContext,
    HitResponse,
    InterceptResponse,
    NegateSaveSpec,
    ReactiveDamageSpec,
    RedirectSpec,
    RiderDamageSpec,
)
from ..resources import ResourceEntry, ResourcePool
from ..statuses import StatusSpec
from .enemy import ScriptedEnemyPolicy  # shared enemy loop (re-exported here)

if TYPE_CHECKING:
    from ..rng import SeededRNG


# Declarative ability layer: Sacred Flame's dice are read FROM DATA
# (content/abilities/starfire_scion.yaml) and resolved against the character level
# by interpret_save_spell — NOT a literal tuple on the LEVELS row.  This is the
# whole reason the build was chosen (the data-driven save-spell scaling axis).
_ABILITIES = load_abilities()
SACRED_FLAME = _ABILITIES["sacred_flame"]   # DEX save-negates, cantrip-scaling dice
# Searing Arc Strike (Sun-Soul Monk-6, char L10+): upcast Burning Hands as a BA —
# DEX save FOR HALF, FIRE, base 3d6 + 1d6/slot-level (upcast `increment` scaling,
# primitive #3).  Its dice resolve from data via interpret_save_spell against the
# chosen slot level.  type: fire (NOT radiant) — so Fueled Spellfire does NOT fuel
# it (the cross-check that the damage_type gate, not just is_spell, does real work).
SEARING_ARC_STRIKE = _ABILITIES["searing_arc_strike"]
# Shillelagh (druid cantrip, char L9+): the quarterstaff DAMAGE DIE upgrades on the
# enumerated dice ladder (1d8/1d10/1d12/2d6 at char L5/11/17) — resolved FROM DATA
# via interpret_scaled_dice by character level (the first consumer of `scaling:
# ladder`), NOT a literal baked per LEVELS row.  The WIS attack OPTION stays the
# build's profile choice (_shillelagh_attack_choice).
SHILLELAGH = _ABILITIES["shillelagh"]


# ---------------------------------------------------------------------------
# Fire Shield (4th-level spell, char L15 = Druid-7; guide 41:48) — the warm/chill
# CHOOSE_ONE.  Verified 2026-06-15 (D&D Beyond / aidedd): Action, 10 min, NON-
# concentration; warm = resist COLD + 2d8 FIRE thorns; chill = resist FIRE + 2d8
# COLD thorns.  ONE cast_effect installs BOTH the incoming-damage resistance
# (substrate #4) and the defender thorns rider (substrate #5); the chosen mode
# selects WHICH payload items install (the first consumer of the design note's
# `choose_one` seam — modeled here as a data table the policy indexes, the YAML
# `choose_one` construct in content.py staying deferred until cast_effect is
# data-driven).  The guide picks WARM (cold resist + fire thorns) so the fire
# thorns "qualify for our elemental adept feat" — bypassing fire resistance and
# benefitting from the 1->2 high-grade (guide 41:876).
FIRE_SHIELD_MODES: dict[str, dict] = {
    "warm":  {"resist": "cold", "thorns_type": "fire"},
    "chill": {"resist": "fire", "thorns_type": "cold"},
}
FIRE_SHIELD_THORNS_DICE: tuple[int, int] = (2, 8)


# ---------------------------------------------------------------------------
# Fount of Moonlight (4th-level spell, char L15 = Druid-7; guide 41:48, 758) — an
# OUTGOING RIDER (substrate #6) + a radiant resistance (substrate #4).  Verified
# 2026-06-16 (D&D Beyond / dnd2024.wikidot.com / Roll20): Action, Concentration up
# to 10 min; "you have Resistance to Radiant damage, and your MELEE attacks deal an
# extra 2d6 Radiant damage on a hit" (+ a reaction-blind we defer — control, not
# DPR).  The +2d6 RADIANT rides every melee hit — quarterstaff AND unarmed (both
# are melee attacks) — and, being a SPELL's radiant damage, is FUELED by Fueled
# Spellfire for free (it reaches on_deal_damage as its own is_spell radiant
# DamageEvent).  See guide 41:780 `quarterstaff_{primal-strike,fueled-spellfire(2)}
# --> 2d12+3d8+4d6+2WIS` (the 4d6 = FoM's +2d6 on each of two swings).
#
# Modeled WITH CONCENTRATION (session 15): FoM is a real turn-1 MAGIC-ACTION cast
# (cost="action") that sets concentration on the caster and installs the radiant
# resistance (#4) — so turn 1 of the FoM combat deals 0 damage (guide 41:779
# `magic-action:fount-of-moonlight --> 0`), and the +2d6 radiant melee rider (#6)
# is gated on concentration being held (drops the instant a failed CON save breaks
# it).  The enemy-strikes-back loop forces those CON saves; Starry-Form Dragon
# (below) is activated the same turn to guard them.  The single druid-7 4th-level
# slot is now shared with Fire Shield (slot_4th — they are separate daily
# loadouts; see fourth_level_spell).
FOUNT_OF_MOONLIGHT_DICE: tuple[int, int] = (2, 6)


# ---------------------------------------------------------------------------
# Starry Form: Dragon (Circle of Stars, druid-3; guide 41:308) — the SECOND form
# modeled (alongside Archer).  Verified 2026-06-17 (guide 41:304-308): an alternate
# Wild Shape use; "dragon = treat 9 or lower as 10 when making INT/WIS check or CON
# save to maintain concentration".  Modeled as a Wild-Shape-costing, turn-1 BA
# cast_effect that installs the `concentration_save_floor` status (value 10) on the
# caster — a substrate-#3 SAVE-FLOOR grant (the design note's designed-in "save
# floor" sub-kind, first consumer here).  _check_concentration reads the floor on
# the Scion's CON save.  At char L15 the Scion uses Dragon ONLY in the FoM combat
# (to protect FoM's concentration); Archer stays dropped in combat from L9.
DRAGON_CONCENTRATION_FLOOR: int = 10


# ---------------------------------------------------------------------------
# Per-level build data
# ---------------------------------------------------------------------------
# Each entry carries:
#   attack_bonus        — DEX-based martial-arts attack bonus (quarterstaff/unarmed)
#   spell_attack_bonus  — WIS-based spell-attack bonus (Archer / Guiding Bolt)
#   spell_save_dc       — our DC for Sacred Flame (8 + PB + WIS)
#   <weapon profiles>   — per-attack (dice, bonus, weapon_stat) for the override
#   enemy_ac/enemy_dex_save — live from monster_ac_and_saves_by_level.csv (cr==level)
#   ceiling_dpr         — guide all-hit UPPER BOUND (NOT a target; see docstring)
#   resources           — name → (maximum, sr_restore) for the ResourcePool
#
# Sacred Flame's dice are deliberately ABSENT here — they come from the YAML via
# interpret_save_spell(character_level), so the cantrip scaling lives in data.
LEVELS: dict[int, dict] = {
    1: {
        # Monk-1, PB 2, WIS 17 (+3), DEX 16 (+3).
        "attack_bonus": 5,                 # PB 2 + DEX 3 (martial-arts melee)
        "spell_attack_bonus": 5,           # PB 2 + WIS 3 (unused at L1 — no WIS attacks)
        "spell_save_dc": 13,               # 8 + PB 2 + WIS 3
        "char_ac": 16,                     # 10 + DEX 3 + WIS 3 (unarmored defense)
        "char_hp": 8,                      # DPR-irrelevant (threshold model)
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 6), "bonus": 3, "weapon_stat": "attack_bonus"},
        "starry_form": False,
        "guiding_bolt": False,
        "resources": {
            "spellfire_spark": (2, 0),     # Sacred Flame as a BA, x PB / LR (LR-only)
        },
        "enemy_ac": 13,
        "enemy_dex_save": 1,               # csv level 1
        "ceiling_dpr": 14.0,               # loose: quarterstaff 7.5 + unarmed 6.5
    },
    4: {
        # Monk-1/Druid-3 (Stars), PB 2, WIS 17 (+3).  Star Map (free Guiding Bolt
        # xWIS/LR) + Starry Form (Archer) come online — both delivered via the
        # per-attack damage override (primitive #4).
        "attack_bonus": 5,                 # PB 2 + DEX 3
        "spell_attack_bonus": 5,           # PB 2 + WIS 3
        "spell_save_dc": 13,               # 8 + PB 2 + WIS 3
        "char_ac": 16,
        "char_hp": 22,
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 6), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Archer form: BA ranged spell attack 1d8 + WIS, WIS-based to-hit.  It
        # deals RADIANT damage, but it is a starry-form FEATURE, not a spell — so
        # is_spell stays False and Fueled Spellfire (L5+) does NOT fuel it.
        "archer":       {"dice": (1, 8), "bonus": 3, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant"},
        # Guiding Bolt: 4d6 radiant SPELL, ranged spell attack, no damage modifier.
        # radiant + is_spell → a Fueled-Spellfire target at L5+.
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": True,
        "resources": {
            "spellfire_spark": (2, 0),     # x PB / LR
            "guiding_bolt_free": (3, 0),   # Star Map: free Guiding Bolt x WIS / LR
            "wild_shape": (2, 1),          # 2 / LR, +1 on SR → Starry Form ~3 of 4 combats
        },
        "enemy_ac": 15,
        "enemy_dex_save": 2,               # csv level 4
        "ceiling_dpr": 21.5,               # loose: Guiding Bolt 14 + Archer 7.5
    },
    5: {
        # Monk-1/Druid-4 (Stars), PB 3, WIS 18 (+4, Spellfire Adept).  Cantrip
        # scaling lifts Sacred Flame to 2d8 (resolved from data).  Fueled Spellfire
        # unlocks here (the hit_dice pool below + on_deal_damage) — primitive #5.
        "attack_bonus": 6,                 # PB 3 + DEX 3
        "spell_attack_bonus": 7,           # PB 3 + WIS 4
        "spell_save_dc": 15,               # 8 + PB 3 + WIS 4
        "char_ac": 17,                     # 10 + DEX 3 + WIS 4
        "char_hp": 30,
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 6), "bonus": 3, "weapon_stat": "attack_bonus"},
        "archer":       {"dice": (1, 8), "bonus": 4, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant"},  # radiant FEATURE (not a spell)
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": True,
        "resources": {
            "spellfire_spark": (3, 0),     # x PB / LR (PB 3 now)
            "guiding_bolt_free": (4, 0),   # x WIS / LR (WIS 4 now)
            "wild_shape": (2, 1),
            # Fueled Spellfire (Spellfire Adept, L5): the per-day Hit-Dice pool
            # (character level d8, all 5 spent on radiant spell damage; no SR
            # restore — a long rest at day start refills).  Its PRESENCE here is
            # what turns Fueled Spellfire on in the policy (data-driven gate).
            "hit_dice": (5, 0),
        },
        "enemy_ac": 15,
        "enemy_dex_save": 2,               # csv level 5
        "ceiling_dpr": 23.0,               # loose: Guiding Bolt 14 + Sacred Flame 2d8 9
    },
    9: {
        # Monk-5 (Sun Soul)/Druid-4 (Stars), PB 4, WIS 19 (+4, +1 from Elemental
        # Adept at L8), DEX 16 (+3).  Headline (THREAD B): EXTRA ATTACK (1->2
        # quarterstaff swings per Attack action), the martial-arts die bumps to 1d8
        # (unarmed 1d6->1d8; quarterstaff already 1d8 versatile), and the first
        # SHILLELAGH (quarterstaff die -> 1d10 with the WIS option).  To-hit / DC /
        # AC are IDENTICAL to L10 (PB and the WIS modifier do not change monk-5 ->
        # monk-6).  Starry Form is DROPPED in combat from L9 (guide 41:539 — "we no
        # longer need to use starry form in combat at all"), so there is no archer
        # profile / wild_shape here; and no focus_points (Searing Arc is monk-6/L10).
        "attack_bonus": 7,                 # PB 4 + DEX 3 (martial-arts melee / unarmed)
        "spell_attack_bonus": 8,           # PB 4 + WIS 4 (Guiding Bolt / Shillelagh option)
        "spell_save_dc": 16,               # 8 + PB 4 + WIS 4 (Sacred Flame)
        "char_ac": 17,                     # 10 + DEX 3 + WIS 4
        "char_hp": 54,                     # DPR-irrelevant (threshold model)
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Martial arts die 1d6 -> 1d8 at monk-5 (guide 41:512); unarmed uses it.
        "unarmed":      {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Extra Attack (monk-5): the Attack action yields two weapon swings (the
        # policy emits a primary cost="action" + one cost="none" follow-up).
        "extra_attack": True,
        # Shillelagh (druid cantrip, cast as the turn-1 BA, persists the combat):
        # upgrades the quarterstaff damage die on the 1d8/1d10/1d12/2d6 ladder
        # (1d10 at char L9-10) — resolved FROM DATA via interpret_scaled_dice
        # (`scaling: ladder`), NOT baked here — AND grants the OPTION to use WIS
        # (spellcasting) instead of DEX for attack & damage.  The block below is the
        # WIS option (bonus = WIS mod, WIS-based to-hit); the policy compares it to
        # the DEX quarterstaff and uses the HIGHER modifier (defaulting to WIS on a
        # tie) — see _shillelagh_attack_choice.  The die is injected at policy init.
        "shillelagh":   {"bonus": 4, "weapon_stat": "spell_attack_bonus"},
        # Guiding Bolt: 4d6 radiant SPELL (Star Map free cast) — a Fueled-Spellfire
        # target.  Starry Form (Archer) is dropped in combat, so the BA never falls
        # back to archer; only Sacred Flame / unarmed.
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": False,
        "resources": {
            "spellfire_spark":  (4, 0),    # Sacred Flame as a BA, x PB / LR (PB 4)
            "guiding_bolt_free": (4, 0),   # Star Map: free Guiding Bolt x WIS / LR
            # Fueled Spellfire pool: 9 hit dice at char L9 (guide 41:547 — "with 9
            # hit dice").  Its presence is the data-driven on/off gate in the policy.
            "hit_dice": (9, 0),
        },
        "enemy_ac": 16,
        "enemy_dex_save": 2,               # csv level 9
        # Loose all-hit/all-fail upper bound: GB turn 14 + fuel 2d8 9 = 23; attack
        # turns 2x(1d10+WIS) 19 + Sacred Flame 2d8 9 = 28.  ~30 max → 32 cushion.
        "ceiling_dpr": 32.0,
    },
    10: {
        # Monk-6 (Sun-Soul)/Druid-4 (Stars), PB 4, WIS 19 (+4, +1 from Elemental
        # Adept at L8).  Headlines: SEARING ARC STRIKE (upcast Burning Hands as a BA,
        # thread A) PLUS the thread-B martial bundle now shared with L9 — EXTRA ATTACK
        # (two quarterstaff swings per Attack action), the martial-arts die at 1d8
        # (unarmed 1d6->1d8), and SHILLELAGH (quarterstaff die -> 1d10, WIS option).
        # L6-L8 stay SKIPPED (mechanically identical on our side — PB & WIS mod hold;
        # only the enemy hardens).  (Elemental Adept's fire-resistance bypass + 1->2
        # die high-grading are still deferred — see PROGRESS; both are small DPR.)
        "attack_bonus": 7,                 # PB 4 + DEX 3 (martial-arts melee / unarmed)
        "spell_attack_bonus": 8,           # PB 4 + WIS 4 (Guiding Bolt / Shillelagh option)
        "spell_save_dc": 16,               # 8 + PB 4 + WIS 4 (Sacred Flame + Burning Hands)
        "char_ac": 17,                     # 10 + DEX 3 + WIS 4
        "char_hp": 64,                     # DPR-irrelevant (threshold model)
        # Elemental Adept (fire), taken at monk-4/char L8 (the +1 WIS source noted
        # above): the Scion's FIRE spells (Searing Arc Strike) IGNORE enemy fire
        # resistance and treat any 1 on a fire damage die as a 2.  Applied to the
        # Searing Arc Choice in the policy (ignore_resistance + min_die=2).
        "elemental_adept": "fire",
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Martial arts die 1d8 at monk-6; unarmed uses it (1d6 -> 1d8).
        "unarmed":      {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Extra Attack + Shillelagh (thread B — same as L9: die from the ladder
        # (1d10 at char L9-10, via interpret_scaled_dice), WIS option; the policy
        # uses the higher of WIS/DEX, default WIS).
        "extra_attack": True,
        "shillelagh":   {"bonus": 4, "weapon_stat": "spell_attack_bonus"},
        # Guiding Bolt: 4d6 radiant SPELL (Star Map free cast) — a Fueled-Spellfire
        # target.  Starry Form (Archer) is DROPPED in combat from L9 (guide), so no
        # archer profile here; the BA falls back to an unarmed strike.
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": False,
        # Searing Arc Strike (Sun-Soul Monk-6): upcast Burning Hands.  FP cost = 2
        # base + 1 per upcast slot level, capped at floor(monk_level / 2) = 3 FP at
        # monk-6.  Spending the max (3 FP) upcasts to slot level 2 = 4d6.  slot_level
        # = fp_cost - 1.  Dice resolve from the YAML via interpret_save_spell.
        "searing_arc_strike": {"slot_level": 2, "fp_cost": 3},
        "resources": {
            "spellfire_spark":  (4, 0),    # Sacred Flame as a BA, x PB / LR
            "guiding_bolt_free": (4, 0),   # Star Map: free Guiding Bolt x WIS / LR
            # Hit Dice (Fueled Spellfire): character-level d8, all spent on radiant
            # spell damage.  10 at L10 (vs 5 at L5) — fuels more combats per day.
            "hit_dice": (10, 0),
            # Monk focus points (monk-6 = 6).  Searing Arc Strike costs 3 FP/cast →
            # 2 casts/combat.  Uncanny Metabolism + Prayer of Healing recharge them
            # fully between combats (guide), modeled by a per-combat refill in
            # on_combat_start; LR at day start also refills (sr_restore=0).
            "focus_points": (6, 0),
        },
        "enemy_ac": 16,
        "enemy_dex_save": 3,               # csv level 10
        # Loose all-hit/all-fail upper bound (now with Extra Attack + Shillelagh):
        # turn-1 Guiding Bolt 14 + fuel 2d8 9 = 23; attack turns 2x(1d10+WIS) 19 +
        # Searing Arc full 4d6 14 = 33.  ~33 max → 36 cushion.
        "ceiling_dpr": 36.0,
    },
    11: {
        # Monk-7 (Sun-Soul)/Druid-4 (Stars), PB 4, WIS 19 (+4), DEX 16 (+3).
        # Headline (the dice-ladder consumer): SHILLELAGH die steps 1d10 -> 1d12
        # at character level 11 (the [5,11,17] cantrip break) — resolved FROM DATA
        # off `scaling: ladder`.  Monk-7 itself adds Evasion (defensive, DPR-
        # irrelevant in the threshold model), so on our OFFENSE side L11 == L10
        # except the bigger Shillelagh die (and the FP pool grows monk-6 -> 7).
        # To-hit / DC / AC are unchanged from L10 (PB 4 and WIS +4 both hold from
        # monk-6 -> monk-7); only the enemy hardens (AC 16 -> 17 at cr 11).
        "attack_bonus": 7,                 # PB 4 + DEX 3 (martial-arts melee / unarmed)
        "spell_attack_bonus": 8,           # PB 4 + WIS 4 (Guiding Bolt / Shillelagh option)
        "spell_save_dc": 16,               # 8 + PB 4 + WIS 4 (Sacred Flame + Burning Hands)
        "char_ac": 17,                     # 10 + DEX 3 + WIS 4
        "char_hp": 74,                     # DPR-irrelevant (threshold model)
        "elemental_adept": "fire",         # monk-4/L8 (see L10) — fire spells bypass resist + 1->2

        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Martial arts die still 1d8 at monk-7 (it next steps to 1d10 at monk-11).
        "unarmed":      {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "extra_attack": True,
        # Shillelagh die -> 1d12 at char L11 (resolved by interpret_scaled_dice).
        "shillelagh":   {"bonus": 4, "weapon_stat": "spell_attack_bonus"},
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": False,
        # Searing Arc Strike unchanged from L10: monk-7 cap = floor(7/2) = 3 FP →
        # slot 2 = 4d6 (FP cost 3).  (5d6 waits for monk-8 at L12.)
        "searing_arc_strike": {"slot_level": 2, "fp_cost": 3},
        "resources": {
            "spellfire_spark":  (4, 0),    # Sacred Flame as a BA, x PB / LR (PB 4)
            "guiding_bolt_free": (4, 0),   # Star Map: free Guiding Bolt x WIS mod / LR
            "hit_dice": (11, 0),           # Fueled Spellfire: char-level d8 (11 at L11)
            "focus_points": (7, 0),        # monk-7 = 7 FP
        },
        "enemy_ac": 17,
        "enemy_dex_save": 3,               # csv level 11
        # Loose upper bound (Shillelagh now 1d12): GB turn 14 + fuel 9 = 23; attack
        # turns 2x(1d12+4) 21 + Searing Arc full 4d6 14 = 35.  ~35 max → 38 cushion.
        "ceiling_dpr": 38.0,
    },
    12: {
        # Monk-8 (Sun-Soul)/Druid-4 (Stars), PB 4, WIS 20 (+5, Resilient (WIS) at
        # L12 — guide lines 30, 45), DEX 16 (+3).  Headlines: WIS 19 -> 20 lifts the
        # spell to-hit, save DC, and the Shillelagh/Archer/Guiding-Bolt damage by +1;
        # and monk-8 upcasts Burning Hands one slot higher — SEARING ARC STRIKE
        # 4d6 -> 5d6 (cap floor(8/2) = 4 FP → slot 3; guide line 106).  Shillelagh die
        # stays 1d12 (char L11-16 step).  Enemy at cr 12 is AC 17 / DEX +3 — IDENTICAL
        # to cr 11, so L11 vs L12 is a clean fixed-enemy monotonic check (isolates the
        # WIS +1 and the 4d6 -> 5d6 upcast).
        "attack_bonus": 7,                 # PB 4 + DEX 3 (DEX unchanged → martial to-hit holds)
        "spell_attack_bonus": 9,           # PB 4 + WIS 5 (Guiding Bolt / Shillelagh option)
        "spell_save_dc": 17,               # 8 + PB 4 + WIS 5
        "char_ac": 18,                     # 10 + DEX 3 + WIS 5
        "char_hp": 84,                     # DPR-irrelevant (threshold model)
        "elemental_adept": "fire",         # monk-4/L8 (see L10) — fire spells bypass resist + 1->2

        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "extra_attack": True,
        # Shillelagh die 1d12 (char L11-16); WIS mod now +5 (bonus 5).
        "shillelagh":   {"bonus": 5, "weapon_stat": "spell_attack_bonus"},
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": False,
        # monk-8: cap = floor(8/2) = 4 FP → upcast Burning Hands to slot 3 = 5d6
        # (guide line 106 — "upcast burning hands at lvl-03 (5d6)").  slot_level = 3.
        "searing_arc_strike": {"slot_level": 3, "fp_cost": 4},
        "resources": {
            "spellfire_spark":  (4, 0),    # Sacred Flame as a BA, x PB / LR (PB 4)
            "guiding_bolt_free": (5, 0),   # Star Map: free Guiding Bolt x WIS mod / LR (WIS 20 → 5)
            "hit_dice": (12, 0),           # Fueled Spellfire: char-level d8 (12 at L12)
            "focus_points": (8, 0),        # monk-8 = 8 FP
        },
        "enemy_ac": 17,
        "enemy_dex_save": 3,               # csv level 12
        # Loose upper bound (WIS +5, Shillelagh 1d12+5, Searing Arc 5d6): GB turn 14
        # + fuel 9 = 23; attack turns 2x(1d12+5) 23 + Searing Arc full 5d6 17.5 = 40.5.
        # ~41 max → 44 cushion.
        "ceiling_dpr": 44.0,
    },
    15: {
        # Monk-8 (Sun-Soul)/Druid-7 (Circle of Stars), PB 5, WIS 20 (+5), DEX 16
        # (+3).  The TIER-4 row.  Headlines wired this session: FIRE SHIELD (4th-
        # level, the first real consumer of substrates #4 + #5 + the warm/chill
        # CHOOSE_ONE) and ELEMENTAL ADEPT (fire) now has a real fire-resistant-enemy
        # consumer (validated in tests).  vs L12 our OFFENSE changes only by PB 4->5
        # (+1 spell to-hit / save DC) — WIS is already capped at 20, the Shillelagh
        # die stays 1d12 (char L11-16), and Searing Arc stays 5d6 (monk-8 cap).
        # DEFERRED to a follow-up tier-4 session (need the unbuilt outgoing-rider
        # substrate #6): Primal Strikes (druid-7, +1d8 once/turn), Fount of Moonlight
        # (4th-level, +2d6 radiant on melee hits), and elemental weapon (druid-5/L13).
        # Sunbeam is a 6th-level spell = char L19, outside this row entirely.  So our
        # modeled L15 DPR is a FRACTION of the guide's ~50 tier-4 ceiling — by design.
        "attack_bonus": 8,                 # PB 5 + DEX 3 (martial-arts melee / unarmed)
        "spell_attack_bonus": 10,          # PB 5 + WIS 5 (Guiding Bolt / Shillelagh option)
        "spell_save_dc": 18,               # 8 + PB 5 + WIS 5 (Sacred Flame + Burning Hands)
        "char_ac": 18,                     # 10 + DEX 3 + WIS 5
        "char_hp": 99,                     # DPR-irrelevant (threshold model)
        # CON save: CON 14 (+2), NOT proficient (monk grants STR/DEX, druid INT/WIS)
        # — used for FoM concentration saves now that the Scion concentrates here.
        "con_save": 2,
        "elemental_adept": "fire",         # monk-4/L8 — fire spells bypass resist + 1->2
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        # `is_unarmed` tags this as a monk unarmed strike (NOT a weapon attack) so
        # Primal Strike's RAW gate can decline it (the non-RAW toggle accepts it).
        "unarmed":      {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus",
                          "is_unarmed": True},
        "extra_attack": True,
        # Shillelagh die stays 1d12 (char L11-16 step); WIS mod +5 (bonus 5).
        "shillelagh":   {"bonus": 5, "weapon_stat": "spell_attack_bonus"},
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": False,
        # Searing Arc Strike: monk-8 cap floor(8/2)=4 FP → slot 3 = 5d6 (as L12).
        "searing_arc_strike": {"slot_level": 3, "fp_cost": 4},
        # Primal Strike (Elemental Fury, druid-7; guide 41:741, verified 2026-06-16
        # D&D Beyond / Roll20): once on each of your turns, when you HIT with an
        # attack roll using a WEAPON (or a Beast form), +1d8 cold/fire/lightning/
        # thunder (choose on hit).  An OUTGOING RIDER (substrate #6) on the on_hit
        # seam.  We pick FIRE for flavour, but it is a FEATURE (is_spell=False) so
        # Elemental Adept does NOT treat it (spells only) — unlike the fire Searing
        # Arc / Fire Shield thorns, the cross-check that the is_spell gate does real
        # work on the rider path.  The 2d8 step is DRUID-15 (far past druid-7) → 1d8
        # here.  Built TOGGLEABLE: RAW rides weapon attacks only (quarterstaff); the
        # non-RAW option (user-requested — see memory primal-strikes-explore-unarmed)
        # also rides unarmed strikes (Flurry of Blows), to compare DPR in tier-4/5
        # where the action is Sunbeam and the attacks are unarmed.  Default RAW.
        "primal_strike": {"dice": (1, 8), "damage_type": "fire", "raw_unarmed": False},
        # Fount of Moonlight (4th-level): +2d6 radiant on every MELEE hit (incl.
        # unarmed) — an outgoing rider (#6) that is FUELABLE (radiant spell damage)
        # — plus radiant resistance (#4).  Modeled WITH CONCENTRATION (session 15):
        # cast as a turn-1 Magic action, guarded by Starry-Form Dragon; shares the
        # single 4th-level slot with Fire Shield (slot_4th).  See the
        # FOUNT_OF_MOONLIGHT_DICE note.
        "fount_of_moonlight": {},
        # Starry Form: Dragon (druid-3) — the concentration-save floor used to
        # protect FoM (guide 41:308/779).  A Wild-Shape-costing turn-1 BA in the FoM
        # combat (decide()/on_combat_start).  See DRAGON_CONCENTRATION_FLOOR.
        "dragon_form": True,
        # Fire Shield (4th-level): pre-cast before ONE combat/day (one 4th-level
        # slot → the fire_shield_use resource).  WARM mode (the guide's pick): cold
        # resistance (#4) + 2d8 fire thorns (#5) reflected on every incoming melee
        # hit, the fire thorns Elemental-Adept-treated (bypass + high-grade).
        "fire_shield": {"mode": "warm"},
        # Enemy strikes back (cr15 melee) so Fire Shield's thorns do real DPR work.
        # attack_bonus / damage are ILLUSTRATIVE (the monster CSV carries only AC +
        # saves; per-CR attack/damage is the unrealised half of decision #12 —
        # see builds/enemy.py).  +9 vs char AC 18 → ~60% hit, exercising the thorns.
        "enemy_attack": {"n_attacks": 2, "char_target_prob": 1.0,
                          "attack_bonus": 9, "damage_dice": (2, 8), "damage_bonus": 5,
                          # Multi-entity targeting weights (substrate #7 / 7c slice;
                          # design.md §3.5).  Used ONLY when make_day_runner is called
                          # with_party=True: the enemy splits its swings across
                          # {character, party} by these integer weights.  The melee
                          # Scion is weighted higher than a passive party member (the
                          # §3.5 "melee tag raises targeting probability"): 2:1 → the
                          # character draws 2/3 of the attacks, the party 1/3.  So
                          # Fire-Shield thorns fire on a FRACTION of incoming hits (no
                          # longer every one, as against the lone dummy) — dissolving
                          # the single-dummy thorns over-count (PROGRESS session 16).
                          "char_weight": 2, "party_weight": 1},
        "resources": {
            "spellfire_spark":  (5, 0),    # Sacred Flame as a BA, x PB / LR (PB 5)
            "guiding_bolt_free": (5, 0),   # Star Map: free Guiding Bolt x WIS mod / LR (WIS 20 → 5)
            "hit_dice": (15, 0),           # Fueled Spellfire: char-level d8 (15 at L15)
            "focus_points": (8, 0),        # monk-8 = 8 FP
            # The SINGLE druid-7 4th-level spell slot (1/LR).  Fire Shield and Fount
            # of Moonlight COMPETE for it — they are separate daily loadouts (the
            # guide prepares ONE; see fourth_level_spell), so exactly one is cast
            # per day, in ONE combat.  (This replaces session-14's two separate 1/LR
            # uses, which over-counted the single real slot.)
            "slot_4th": (1, 0),
            # Wild Shape (2/LR + 1 on a short rest → ~4/day with Prayer of Healing,
            # guide 41:1069): spent to assume Starry-Form Dragon in the FoM combat.
            "wild_shape": (2, 1),
        },
        "enemy_ac": 18,
        "enemy_dex_save": 4,               # csv level 15
        # Loose upper bound for what we MODEL now (elemental weapon still deferred):
        # attack turns 2x(1d12+5) 23 + Primal Strike 1d8 4.5 + Searing Arc 5d6 17.5
        # = ~45; in the FoM combat add +2d6/swing (radiant, fueled) ~ +14.  The
        # guide's full-kit tier-4 figure is ~50; modeling FoM + Primal Strikes lifts
        # our DPR well above session-13's ~29.7 toward it.  52 cushion.
        "ceiling_dpr": 52.0,
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


def make_starfire_scion(level: int) -> Entity:
    """Build the Starfire Scion Entity for the given level (1, 4, 5, 9-12 for now)."""
    if level not in LEVELS:
        raise NotImplementedError(
            f"Starfire Scion level {level} not yet implemented (have {sorted(LEVELS)})."
        )
    data = LEVELS[level]
    return Entity(
        name=f"StarfireScion-L{level}",
        hp=data["char_hp"],
        base_stats={
            "attack_bonus": data["attack_bonus"],          # DEX martial-arts melee
            "spell_attack_bonus": data["spell_attack_bonus"],  # WIS spell attacks
            "spell_save_dc": data["spell_save_dc"],        # Sacred Flame DC
            "con_save": data.get("con_save", 0),           # CON save (FoM concentration)
            # Fallback weapon profile — every attack the policy emits carries its
            # own damage override, so these are only read if a future Choice omits
            # one.  Default to the quarterstaff so the fallback is sensible.
            "damage_dice": data["quarterstaff"]["dice"],
            "damage_bonus": data["quarterstaff"]["bonus"],
        },
        resources=_make_resources(data),
    )


def make_training_dummy(level: int) -> Entity:
    """Build the target for the given level.

    HP is effectively infinite (threshold model).  The dummy carries the enemy AC
    (for attack rolls) and the DEX save bonus (for Sacred Flame's save) — both
    live from monster_ac_and_saves_by_level.csv.  Through L12 it has no policy and
    never acts; if the level carries an ``enemy_attack`` profile it also gets an
    ``attack_bonus`` + a flat melee damage profile so a ScriptedEnemyPolicy can
    strike the character (the enemy-strikes-back loop — needed once defender-side
    effects like Fire Shield's thorns come online; see make_day_runner).  An
    ``enemy_resist`` block installs an INTRINSIC damage-type response (e.g. a
    fire-resistant enemy that halves Searing Arc — substrate #4).
    """
    data = LEVELS[level]
    base_stats: dict = {
        "ac": data["enemy_ac"],
        "dex_save": data["enemy_dex_save"],
    }
    ea = data.get("enemy_attack")
    if ea:
        base_stats["attack_bonus"] = ea["attack_bonus"]
        base_stats["damage_dice"] = ea.get("damage_dice", (1, 8))
        base_stats["damage_bonus"] = ea.get("damage_bonus", 0)
    return Entity(
        name=f"Dummy-AC{data['enemy_ac']}",
        hp=10**9,
        base_stats=base_stats,
        damage_response=data.get("enemy_resist"),
    )


def make_party_member(level: int) -> Entity:
    """A passive PARTY MEMBER (design.md §3.6) — one extra FRIENDLY HP pool that
    soaks a share of the enemy's attacks.

    The foundation-min piece of substrate #7's 7c slice (the multi-entity-combat
    on-ramp): a SINGLE infinite-HP pool — the full §3.6 three-HP-pool model is a
    later slice — carrying just an AC so the enemy's attacks against it resolve, and
    NO policy, so it never acts (it draws attacks, deals no damage).  Its whole job
    is to pull a fraction of the enemy's swings away from the character: with the
    enemy splitting attacks across {character, party}, the character's defender-side
    reactions (Fire-Shield thorns, substrate #5) fire on only a FRACTION of incoming
    hits instead of every one — dissolving the single-dummy thorns over-count
    (PROGRESS session 16 / the substrate-#7 design note's first slice).
    """
    data = LEVELS[level]
    return Entity(
        name=f"PartyMember-L{level}",
        hp=10**9,
        # A peer's AC (§3.6 says party AC scales with level via the CR table; a
        # melee peer at the Scion's own AC is the foundation-min stand-in).  No
        # saves/resources — the enemy here only melee-attacks, and the party never
        # acts, so nothing else is read.
        base_stats={"ac": data["char_ac"]},
    )


def make_ally(level: int) -> Entity:
    """A synthetic ALLY (substrate #7 / 7c ally-effects) — the friendly entity the
    Scion's ally-effect casts LAND ON (bless/aid retarget, warding bond, protection,
    sanctuary).  Like make_party_member it is a passive infinite-HP friendly pool at
    a peer's AC, but it ALSO carries the saving-throw stats an ally-effect reads (no
    policy of its own → it never acts; the AllyEffectPolicy is attached separately so
    the intercept seam consults it).
    """
    data = LEVELS[level]
    return Entity(
        name=f"Ally-L{level}",
        hp=10**9,
        base_stats={
            "ac": data["char_ac"],
            # A peer's saves — read only if an ally-effect ever rolls one ON the ally
            # (none of the 7c effects do; Sanctuary's save is the ATTACKER's).  Kept
            # for parity with a real party member.
            "con_save": 4, "wis_save": 4, "dex_save": 3,
        },
    )


# ---------------------------------------------------------------------------
# 7c ally-effects: the protected/warded/sanctified ALLY's reaction policy
# ---------------------------------------------------------------------------

class AllyEffectPolicy:
    """The defender-side policy for an ALLY benefiting from a 7c ally-effect, plus
    the cast that installs it (substrate #7 / 7c ally-effects).  One vehicle covers
    all three intercept-riding effects; the rider returned by ``on_incoming_hit``
    selects which.

    The seam consults the DEFENDER's policy (the ally), so the protector/warder's
    reaction economy is ABSTRACTED into the ally's response and self-gated — the same
    convention as Fire-Shield thorns and Flourish Parry (the reactor entity, here the
    Scion ``caster``, is not separately ticked).

      - ``warding_bond``  → REDIRECT a share of the ally's taken damage to the caster
        (RedirectSpec).  The cast ALSO installs the +1 AC modifier (substrate #1) and
        resistance-to-all (substrate #4) on the ally — the retargeted payloads.
      - ``protection``    → impose DISADVANTAGE on the attack (a nearby shield-bearer
        interposes; 2024 Protection makes ALL attacks vs the target disadvantaged
        until the protector's next turn, so always-on while active is RAW-correct for
        a single attacker).
      - ``sanctuary``     → the ATTACKER must make a WIS save (vs the caster's DC) or
        lose the attack (NegateSaveSpec).

    The ally never acts: ``decide`` returns [] so its TurnStartEvent is a no-op.
    """

    def __init__(self, effect: str, ally: "Entity", caster: "Entity"):
        if effect not in ("warding_bond", "protection", "sanctuary"):
            raise ValueError(f"unknown ally-effect {effect!r}")
        self._effect = effect
        self._ally = ally
        self._caster = caster

    def install(self) -> None:
        """Install the retargeted persistent payload on the ALLY (the part of the
        effect that is not an intercept rider).  Called once at setup (a pre-cast,
        like the Scion's Fire Shield) so the buff is live from initiative.

        Warding Bond's +1 AC (substrate #1) lands on the ally's ModifierStack — a
        ``cast_effect target=ally`` payload, here installed directly.  Its
        resistance-to-all (substrate #4) is also a target=ally payload, but our
        modeled enemy attack is UNTYPED (``damage_response_for(None) → None``), so it
        would be inert here; the #4 retarget is exercised in the typed-damage unit
        test instead (test_ally_effects).  Protection / Sanctuary carry no persistent
        payload — they are pure intercept riders.
        """
        if self._effect == "warding_bond":
            self._ally.add_modifier(Modifier(stat="ac", value=1, source="warding_bond"))

    def on_incoming_hit(self, ctx) -> "InterceptResponse | None":
        if self._effect == "warding_bond":
            # Each time the warded ally takes damage, the caster takes the same.
            return InterceptResponse(
                redirect=RedirectSpec(target=self._caster, fraction=1.0))
        if self._effect == "protection":
            return InterceptResponse(impose_disadvantage=True)
        if self._effect == "sanctuary":
            dc = int(self._caster.stat("spell_save_dc"))
            return InterceptResponse(
                negate_save=NegateSaveSpec(save_stat="wis_save", dc=dc))
        return None

    def decide(self, snapshot: "GameState") -> "list[Choice]":
        return []                                   # passive — never acts


# ---------------------------------------------------------------------------
# Daily-plan policy
# ---------------------------------------------------------------------------

class StarfireScionPolicy:
    """Starfire Scion daily plan (L1, L4, L5, L9-L12).

    Per-turn rotation (a single representative blaster loop — the guide's full
    optimal play splits melee vs ranged combats and leans on Flame Blade / Starry
    Form forms we defer; validation is consistency/sanity, not number-matching):

      ACTION:        Guiding Bolt (Star Map free cast, while charges remain; L4+)
                     else a quarterstaff attack.
      BONUS ACTION:  Sacred Flame (Spellfire Spark, while charges remain) — the
                     save-FOR-damage core; else an Archer spell attack (if Starry
                     Form is active this combat); else an unarmed strike.

    Sacred Flame's dice are pulled FROM DATA (interpret_save_spell, by character
    level), so cantrip scaling (1d8 → 2d8 at L5) lives in content, not here.  WHICH
    slot/charge to spend, and the BA priority ladder, are policy (Python).

    decide() stays a pure read (no dice, no mutation, no queue).  Starry Form
    activation — the one per-combat resource decision — happens in on_combat_start,
    where it consumes a Wild Shape charge and sets the form active for the combat.
    """

    def __init__(
        self,
        level: int,
        character: Entity,
        target: Entity,
        rounds_per_combat: int = 4,
        primal_strike_unarmed: "bool | None" = None,
        fourth_level_spell: str = "fount_of_moonlight",
        precast_mode: "str | None" = None,
        precast_prob: float = 0.5,
    ) -> None:
        if level not in LEVELS:
            raise NotImplementedError(
                f"StarfireScionPolicy does not yet support level {level}."
            )
        self.level = level
        self._character = character
        self._target = target
        self._rounds = rounds_per_combat
        data = LEVELS[level]
        # Per-attack profiles available at this level (the override fields).
        self._profiles: dict[str, dict] = {
            "quarterstaff": data["quarterstaff"],
            "unarmed": data["unarmed"],
        }
        self._has_starry_form: bool = bool(data.get("starry_form"))
        self._has_guiding_bolt: bool = "guiding_bolt" in data
        if self._has_starry_form:
            self._profiles["archer"] = data["archer"]
        if self._has_guiding_bolt:
            self._profiles["guiding_bolt"] = data["guiding_bolt"]
        # Extra Attack (monk-5, char L9+): the Attack action yields this many EXTRA
        # weapon swings beyond the primary (1 → two swings total; 0 when absent).
        self._extra_attacks: int = 1 if data.get("extra_attack") else 0
        # Shillelagh (druid cantrip, char L9+): present iff this level carries a
        # "shillelagh" block (data-driven gate).  That block is the WIS (spellcasting)
        # OPTION — die 1d10, WIS mod, WIS-based to-hit; _shillelagh_attack_choice
        # compares it to the DEX quarterstaff and swings with the HIGHER ability
        # modifier (defaulting to WIS on a tie), per the 2024 spell granting an
        # option rather than an automatic override.
        self._has_shillelagh: bool = "shillelagh" in data
        if self._has_shillelagh:
            # The LEVELS row carries the WIS attack OPTION (bonus + which to-hit
            # stat); the DAMAGE DIE is resolved FROM DATA off the dice ladder by
            # character level (1d10 at L9-10, 1d12 at L11-16) — interpret_scaled_dice,
            # the first consumer of `scaling: ladder`.  Retrofit is DPR-neutral at
            # L9/L10 (ladder yields the same 1d10 formerly baked here).
            die = interpret_scaled_dice(SHILLELAGH, {"character_level": level})
            self._shillelagh_wis = {**data["shillelagh"], "dice": die}
        # Sacred Flame dice + damage TYPE FROM DATA — resolved once for this
        # character level.  The type ("radiant") drives Fueled Spellfire gating.
        _sf = interpret_save_spell(SACRED_FLAME, {"character_level": level})
        self._sacred_flame_dice = _sf.damage_dice
        self._sacred_flame_type = _sf.damage_type
        # Fueled Spellfire (Spellfire Adept, L5+): enabled iff the level carries a
        # Hit-Dice pool (data-driven gate — see LEVELS[5]["resources"]).  1/turn,
        # when a SPELL deals RADIANT damage, expend up to 2 Hit Dice into it.
        self._fueled_spellfire: bool = "hit_dice" in data.get("resources", {})
        # Searing Arc Strike (Sun-Soul Monk-6, L10+): present iff this level carries
        # a "searing_arc_strike" block (data-driven gate).  Its FIRE damage dice are
        # resolved FROM DATA via interpret_save_spell against the chosen slot level
        # (upcast Burning Hands, +1d6/slot — primitive #3).  WHICH slot (= how many
        # FP to burn) is policy; here we always burn the cap (floor(monk/2) FP).
        sas = data.get("searing_arc_strike")
        self._has_searing_arc: bool = sas is not None
        if self._has_searing_arc:
            self._sas_fp_cost: int = sas["fp_cost"]
            _sas = interpret_save_spell(
                SEARING_ARC_STRIKE, {"slot_level": sas["slot_level"]}
            )
            self._sas_dice = _sas.damage_dice          # FROM DATA (4d6 at slot 2)
            self._sas_on_save = _sas.on_save           # "half"
            self._sas_type = _sas.damage_type          # "fire" (NOT fuelable)
        # Elemental Adept (fire, monk-4/char L8+): the Scion's FIRE spells ignore
        # enemy fire RESISTANCE and treat any 1 on a fire damage die as a 2.  data
        # carries the chosen element ("fire") or None; the policy applies it to any
        # fire save_spell (Searing Arc Strike) and to Fire Shield's fire thorns.
        self._elemental_adept: "str | None" = data.get("elemental_adept")
        # The prepared 4th-level spell (druid-7 has ONE 4th-level slot, slot_4th):
        # Fire Shield and Fount of Moonlight are SEPARATE daily loadouts competing
        # for it (the guide prepares one), so fourth_level_spell selects which the
        # build casts — exactly one consumes the slot per day.  Default FoM (the
        # guide's L15 pick); set to "fire_shield" to read the Fire-Shield loadout.
        self._fourth_level_spell = fourth_level_spell
        # PRE-CAST ASSUMPTION TOGGLE (session 16): whether a combat-long buff is
        # PRE-CAST (before initiative, free — no in-combat economy / 0-damage turn)
        # or CAST IN COMBAT (a real turn cost + concentration).  In real play this
        # varies, and reporting one number hides the assumption (memory
        # precast-assumption-as-a-toggle): the all-in-combat figure is a LOWER bound,
        # the all-pre-cast an UPPER bound.  A tunable knob spanning:
        #   "always" → always pre-cast (upper bound)
        #   "rng"    → pre-cast with probability precast_prob, rolled ONCE per combat
        #              through the seeded dice channel (a percentile d100), in
        #              on_combat_start — NOT in decide() (which stays a pure read).
        #   "never"  → always cast in combat (lower bound)
        #   None     → each effect's LEGACY default (Fire Shield pre-cast, FoM
        #              in-combat) — and, crucially, draws NO dice, so every existing
        #              run stays bit-identical (only "rng" mode touches the stream).
        # Applies to the prepared 4th-level loadout (Fire Shield / FoM) — the slot
        # where the assumption actually moves the FoM-vs-Fire-Shield verdict.
        self._precast_mode = precast_mode
        self._precast_prob = precast_prob
        # Fire Shield (4th-level, char L15+): available iff the level carries a
        # "fire_shield" block AND it is the prepared 4th-level spell.  ONE cast_effect
        # installs the chosen warm/chill mode's incoming-damage RESISTANCE (#4) +
        # thorns (#5); pre-cast (the slot_4th slot, NON-concentration) in ONE
        # combat/day, decided + consumed in on_combat_start.  See FIRE_SHIELD_MODES.
        fs = data.get("fire_shield")
        self._has_fire_shield: bool = fs is not None and fourth_level_spell == "fire_shield"
        self._fire_shield_mode: str = fs["mode"] if fs else "warm"
        # Primal Strike (Elemental Fury, druid-7, char L15+): an OUTGOING RIDER
        # (substrate #6) on the on_hit seam — once/turn, +1d8 of a chosen element
        # on a weapon (RAW) hit.  Present iff the level carries a "primal_strike"
        # block.  A FEATURE, not a spell → NOT Elemental-Adept-treated.  The
        # RAW-vs-unarmed toggle: the data row's "raw_unarmed" default, overridden
        # by the primal_strike_unarmed ctor arg when given (so tests / a day runner
        # can compare RAW weapon-only vs non-RAW also-unarmed DPR).
        ps = data.get("primal_strike")
        self._has_primal_strike: bool = ps is not None
        if self._has_primal_strike:
            self._primal_strike_dice = ps["dice"]            # (1, 8) at druid-7
            self._primal_strike_type = ps["damage_type"]     # "fire" (chosen)
            self._primal_strike_unarmed: bool = (
                ps.get("raw_unarmed", False)
                if primal_strike_unarmed is None
                else primal_strike_unarmed
            )
        # Fount of Moonlight (4th-level, char L15+): an OUTGOING RIDER (#6) +
        # radiant resistance (#4).  Available iff the level carries a
        # "fount_of_moonlight" block AND it is the prepared 4th-level spell.  +2d6
        # radiant on every MELEE hit (incl. unarmed), FUELABLE (radiant spell
        # damage).  Modeled WITH CONCENTRATION (session 15): cast as a turn-1 Magic
        # action in ONE combat/day (the slot_4th slot), guarded by Starry-Form Dragon.
        self._has_fount_of_moonlight: bool = (
            "fount_of_moonlight" in data and fourth_level_spell == "fount_of_moonlight"
        )
        # Starry Form: Dragon (druid-3, char L15+): available iff the level carries
        # a "dragon_form" block.  Assumed (a Wild Shape charge + a turn-1 BA) in the
        # FoM combat to install the concentration_save_floor that guards FoM.
        self._has_dragon_form: bool = bool(data.get("dragon_form"))
        # Per-combat state, (re)set by on_combat_start.
        self._starry_form_active: bool = False
        # Fire Shield up for this combat (pre-cast in on_combat_start while the
        # slot_4th slot remains).  Gates the turn-1 install in decide() and the
        # thorns in on_incoming_hit.
        self._fire_shield_active: bool = False
        # The FoM combat: this is the one combat/day the slot_4th slot is spent on
        # Fount of Moonlight (committed in on_combat_start).  Gates the turn-1 FoM
        # Magic-action cast + the Guiding-Bolt suppression in decide().  The on_hit
        # rider itself gates on concentration being HELD (self._character.
        # concentration == "fount_of_moonlight"), so it drops the instant a failed
        # CON save breaks it — not merely on this combat-scoped flag.
        self._fount_of_moonlight_active: bool = False
        # Whether THIS combat's 4th-level buff is pre-cast (True → free, before
        # initiative) or cast in combat (False → real turn cost).  Resolved once per
        # combat from _precast_mode/_precast_prob when the slot is spent
        # (on_combat_start); read by decide() to pick each cast's cost.  Default
        # False is irrelevant until a buff is committed.
        self._precast_this_combat: bool = False
        # Starry-Form Dragon assumed this combat (Wild Shape spent in on_combat_start
        # for the FoM combat).  Gates the turn-1 BA Dragon activation in decide().
        self._dragon_form_active: bool = False
        # Primal Strike's once/turn gate: the combat round we last fired it on.
        # The character takes exactly one turn per round, so the round number
        # identifies the turn (mirrors Flourish Parry's round-gating); reset per
        # combat in on_combat_start.  "Once on each of your turns" (RAW).
        self._primal_strike_round: "int | None" = None
        # Shillelagh up for this combat (cast as the turn-1 BA, then persists).  Set
        # by on_combat_start; consumed by the weapon-attack swings and by the turn-1
        # BA suppression in decide().
        self._shillelagh_active: bool = False
        # 1/turn Fueled-Spellfire gate: the (round, turn_index) we last fueled on,
        # so a turn that deals radiant damage twice (Guiding Bolt + Sacred Flame)
        # fuels only once.  Keyed by turn → auto-resets across turns; cleared per
        # combat (round numbers restart at 1) in on_combat_start.
        self._fueled_turn: "tuple[int, int] | None" = None

    # -- per-combat setup -------------------------------------------------

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        """Activate Starry Form (Archer) for this combat if a Wild Shape charge
        remains.  Wild Shape is 2/LR + 1 on a short rest, so across a day the form
        is up in roughly 3 of the 4 combats; when it is down the BA falls back to
        an unarmed strike.  (rng is unused — activation is deterministic given the
        resource pool; the parameter matches the on_combat_start hook signature.)
        """
        self._starry_form_active = False
        # Shillelagh (char L9+) is cast at the top of every combat (its turn-1 BA
        # cost is modeled in decide() by withholding the turn-1 BA damage option)
        # and then persists the whole combat, so flag it up here.  It is an at-will
        # cantrip — no slot / resource cost.
        self._shillelagh_active = self._has_shillelagh
        # Clear the per-turn Fueled-Spellfire gate (round numbers restart at 1 each
        # combat, so a stale (round, turn) would mis-gate the new combat).
        self._fueled_turn = None
        # Uncanny Metabolism + Prayer of Healing recharge focus points fully between
        # combats (guide), so the Scion starts every combat at full FP — model that
        # by refilling the pool here (the resource itself is LR-only, sr_restore=0).
        if self._has_searing_arc:
            self._character.resources.restore("focus_points", "full")
        if (
            self._has_starry_form
            and self._character.resources.available("wild_shape") >= 1
        ):
            self._character.resources.consume("wild_shape")
            self._starry_form_active = True
        # The single druid-7 4th-level slot (slot_4th): spend it on the ONE prepared
        # 4th-level spell, in ONE combat/day.  Fire Shield and FoM compete for it
        # (only one is "_has_*" true given fourth_level_spell), so at most one branch
        # fires and the slot is spent at most once per day.
        self._fire_shield_active = False
        self._fount_of_moonlight_active = False
        self._dragon_form_active = False
        self._precast_this_combat = False
        if self._character.resources.available("slot_4th") >= 1:
            # Roll the PRE-CAST coin ONCE for this combat (the only combat/day the
            # slot is spent) — through the seeded dice channel, in on_combat_start,
            # so decide() stays a pure read (CLAUDE.md #7/#9).  In the default and
            # "always"/"never" modes _roll_precast draws NO dice, so the existing
            # RNG stream — and every prior DPR/ablation test — stays bit-identical;
            # only "rng" mode consumes the percentile d100.
            self._precast_this_combat = self._roll_precast(rng)
            if self._has_fire_shield:
                # Fire Shield: NON-concentration.  decide() emits the resistance
                # install on turn 1 as cost="none" (pre-cast) or cost="action"
                # (in-combat — costs the turn-1 action); on_incoming_hit reflects
                # the mode's thorns on every incoming melee hit this combat.
                self._character.resources.consume("slot_4th")
                self._fire_shield_active = True
            elif self._has_fount_of_moonlight:
                # Fount of Moonlight: a CONCENTRATION spell cast as a turn-1 Magic
                # action (decide()).  Commit the slot for this combat here; the cast
                # itself sets concentration + installs the radiant resistance, and
                # the on_hit rider gates on concentration being held.  Also assume
                # Starry-Form Dragon (a Wild Shape charge) to guard that
                # concentration — its turn-1 BA install of the save-floor (guide
                # 41:779 `BA:starry-form(dragon) + magic-action:fount-of-moonlight`).
                self._character.resources.consume("slot_4th")
                self._fount_of_moonlight_active = True
                if (
                    self._has_dragon_form
                    and self._character.resources.available("wild_shape") >= 1
                ):
                    self._character.resources.consume("wild_shape")
                    self._dragon_form_active = True
        # Reset Primal Strike's once/turn gate (round numbers restart each combat).
        self._primal_strike_round = None

    def _roll_precast(self, rng: "SeededRNG") -> bool:
        """Resolve whether this combat's 4th-level buff is pre-cast (True) or cast
        in combat (False) — the pre-cast assumption toggle.

        Modes that DON'T draw dice (so the RNG stream stays bit-identical to before
        the toggle existed):
          - "always" → True  (upper bound)
          - "never"  → False (lower bound)
          - None     → each effect's LEGACY default: Fire Shield was always
                       pre-cast (True); FoM was always in-combat (False).
        Only "rng" mode consumes the seeded channel: a percentile d100, pre-cast
        when the roll is within precast_prob (e.g. p=0.5 → roll <= 50).  Going
        through rng.roll keeps the single dice channel invariant (CLAUDE.md).
        """
        if self._precast_mode == "always":
            return True
        if self._precast_mode == "never":
            return False
        if self._precast_mode == "rng":
            threshold = int(round(self._precast_prob * 100))
            return rng.roll_one(100) <= threshold
        # None → legacy per-effect default (no dice drawn).
        return self._has_fire_shield

    # -- decision point ---------------------------------------------------

    def decide(self, snapshot: GameState) -> list[Choice]:
        res = snapshot.resources
        choices: list[Choice] = []
        # Whether this combat's 4th-level buff is pre-cast (free, before initiative)
        # or cast in combat (real turn cost) — resolved in on_combat_start.  Drives
        # the COST of each 4th-level cast below: pre-cast → cost="none" turn-1
        # installs (no economy, full-damage turn 1); in-combat → the buff is the
        # turn-1 action/BA (a 0-damage opening turn).
        precast = self._precast_this_combat

        # Starry Form (L4/L5) activation as a first-class cast_effect on turn 1
        # (design/buff_primitive.md): the Star Druid activates the form, which then
        # grants its special ability.  For the ARCHER form the activation is BUNDLED
        # with its bonus-action archer attack, so the cast costs NO separate economy
        # (cost="none") and the archer BA still fires — DPR-neutral.  Chalice/Dragon
        # (later) would activate with a real cost="bonus_action".  Availability (a
        # Wild Shape charge) is decided + consumed in on_combat_start, which sets
        # _starry_form_active; decide() only emits the activation event.
        if self._starry_form_active and snapshot.round_number == 1:
            choices.append(Choice(
                action_type="cast_effect",
                cost="none",
                effect_source="starry_form",
            ))

        # 4th-level buff PRE-CAST installs (turn 1, cost="none") — only when this
        # combat's buff is pre-cast (before initiative, 10-min/concentration held
        # from before the fight, no in-combat economy — like Starry Form's
        # activation).  When NOT pre-cast, the buff is instead cast in combat down in
        # the action/BA blocks (a real turn cost).  The non-pre-cast path is the
        # session-15 lower-bound model; pre-cast is the upper bound.
        if precast and snapshot.round_number == 1:
            # Fire Shield: installs the chosen mode's incoming-damage RESISTANCE (#4)
            # under effect_source "fire_shield"; thorns (#5) ride on_incoming_hit.
            if self._fire_shield_active:
                mode = FIRE_SHIELD_MODES[self._fire_shield_mode]
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="none",
                    effect_source="fire_shield",
                    damage_response={mode["resist"]: "resistance"},
                    duration="combat",
                ))
            # Fount of Moonlight: a free concentration install (sets concentration +
            # radiant resistance #4) — so turn 1 is a full melee turn (the +2d6
            # radiant rider rides from the first swing) instead of a 0-damage cast.
            # Concentration is STILL held + breakable in combat, so Dragon's
            # save-floor still guards it — also installed free here (a pre-cast Wild
            # Shape activation).
            if self._fount_of_moonlight_active:
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="none",
                    effect_source="fount_of_moonlight",
                    concentration=True,
                    damage_response={"radiant": "resistance"},
                    duration="combat",
                ))
                if self._dragon_form_active:
                    choices.append(Choice(
                        action_type="cast_effect",
                        cost="none",
                        effect_source="starry_form_dragon",
                        statuses=[StatusSpec("concentration_save_floor",
                                             DRAGON_CONCENTRATION_FLOOR)],
                        duration="combat",
                    ))

        # ACTION: Guiding Bolt (free Star Map cast) while charges remain, else a
        # quarterstaff attack.  Greedy on the free casts — across statistically
        # identical combats, when they fire does not change mean DPR.
        #
        # EXCEPT in the Fount of Moonlight combat: FoM's whole value is +2d6 radiant
        # (fuelable) on every MELEE hit, so the Scion MELEES that combat (the guide's
        # FoM combats are `attack(x2):quarterstaff_{...}`, not Guiding Bolt).
        # Turn 1 of that combat the ACTION is the Magic-action CAST of FoM itself
        # (concentration; installs the radiant resistance #4) — so turn 1 deals 0
        # damage (guide 41:779).  Suppressing Guiding Bolt for the rest of the combat
        # makes the melee riders land AND enables Searing Arc (a weapon-Attack-action
        # BA); the unused free GB charges carry to the other (non-FoM) combats, so
        # total GB casts — and mean DPR outside the FoM combat — are unchanged.
        #
        # Track whether this turn's action is a WEAPON attack (quarterstaff/unarmed)
        # vs. casting a spell (Guiding Bolt / FoM): Searing Arc Strike requires the
        # *Attack action*, which a spell cast — though Guiding Bolt is delivered via
        # an attack roll in the engine — does NOT count as (it is the Magic action).
        # So the gate is "a weapon attack was the action", true for quarterstaff only.
        action_is_weapon_attack = False
        if res.get("action", 0) >= 1:
            if (
                self._fount_of_moonlight_active
                and not precast
                and snapshot.round_number == 1
            ):
                # IN-COMBAT FoM (lower bound): turn 1 of the FoM combat the Magic
                # action CASTS Fount of Moonlight — a CONCENTRATION cast_effect that
                # sets concentration and installs the radiant RESISTANCE (#4).  No
                # attack this turn (0 damage, guide 41:779).  From turn 2 the +2d6
                # radiant melee rider (#6, on_hit) rides every swing while
                # concentration holds.  (Pre-cast skips this — the install is free,
                # turn 1 above — so the action falls through to a melee swing.)
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="action",
                    effect_source="fount_of_moonlight",
                    concentration=True,
                    damage_response={"radiant": "resistance"},
                    duration="combat",
                ))
            elif (
                self._fire_shield_active
                and not precast
                and snapshot.round_number == 1
            ):
                # IN-COMBAT Fire Shield (lower bound): turn 1 the Action CASTS Fire
                # Shield (NON-concentration), installing the mode's resistance (#4) —
                # so turn 1 deals no Attack-action damage.  Thorns (#5) ride
                # on_incoming_hit from this turn on.  (Pre-cast installs it free
                # above and melees turn 1 instead.)
                mode = FIRE_SHIELD_MODES[self._fire_shield_mode]
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="action",
                    effect_source="fire_shield",
                    damage_response={mode["resist"]: "resistance"},
                    duration="combat",
                ))
            elif (
                self._has_guiding_bolt
                and res.get("guiding_bolt_free", 0) >= 1
                and not self._fount_of_moonlight_active
            ):
                choices.append(self._attack_choice(
                    "guiding_bolt", "action",
                    resource_cost={"guiding_bolt_free": 1},
                ))
            else:
                # Weapon Attack action: a (Shillelagh-buffed) quarterstaff swing,
                # repeated once per Extra Attack.  The primary swing spends the
                # action; each follow-up costs nothing (the action is already paid)
                # — the engine's standard Extra-Attack shape (see ExtraAttackPolicy).
                choices.append(self._weapon_attack_choice("action"))
                for _ in range(self._extra_attacks):
                    choices.append(self._weapon_attack_choice("none"))
                action_is_weapon_attack = True

        # BONUS ACTION priority ladder:
        #   1. Searing Arc Strike (L10+) — only after a weapon Attack action, and
        #      while focus points remain.  Upcast Burning Hands, FIRE save-for-half;
        #      the level's headline BA damage option, so it leads on attack turns.
        #   2. Sacred Flame (Spellfire Spark) — the radiant, FUELABLE save-negates
        #      core; fires on Guiding-Bolt turns (where Searing Arc is unavailable).
        #   3. Archer attack (if Starry Form active — dropped in combat from L9).
        #   4. Unarmed strike.
        #
        # EXCEPT the BA-cast turns: the bonus action is spent CASTING Shillelagh
        # (guide 41:539 — "BA:shillelagh"), a first-class cast_effect that CONSUMES
        # the bonus action (no damage) — the honest model, replacing the former
        # "withhold the BA option" suppression.  Shillelagh then persists and buffs
        # every quarterstaff swing (the swings read _shillelagh_active).  It is cast
        # on turn 1 normally; in the FoM combat turn 1's BA is instead Starry-Form
        # DRAGON (to guard FoM's concentration — guide 41:779), so Shillelagh slides
        # to turn 2 there (guide 41:780 `turn 02: BA:shillelagh`).  No swings happen
        # on turn 1 of either combat (the action is a spell cast), so the buff being
        # flagged from combat start is harmless.  (Pure read: the cantrip / form were
        # flagged in on_combat_start; here we only consult round_number.)
        # Shillelagh slides to turn 2 ONLY when the turn-1 BA is spent on the
        # IN-COMBAT Dragon activation (the FoM lower-bound model).  When FoM is
        # pre-cast, Dragon is installed free above, so the turn-1 BA is free for
        # Shillelagh (cast round 1); likewise the Fire-Shield / no-buff combats.
        shillelagh_cast_round = (
            2 if (self._fount_of_moonlight_active and not precast) else 1
        )
        if res.get("bonus_action", 0) >= 1:
            if self._dragon_form_active and not precast and snapshot.round_number == 1:
                # IN-COMBAT Dragon (lower bound): turn 1 of the FoM combat the BA
                # activates Starry-Form DRAGON — a cost="bonus_action" cast_effect
                # installing the concentration_save_floor status (substrate #3
                # save-floor) that floors FoM's CON saves.  (Pre-cast installs it
                # free above, so this branch is skipped and the BA casts Shillelagh.)
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="bonus_action",
                    effect_source="starry_form_dragon",
                    statuses=[StatusSpec("concentration_save_floor",
                                         DRAGON_CONCENTRATION_FLOOR)],
                    duration="combat",
                ))
            elif self._shillelagh_active and snapshot.round_number == shillelagh_cast_round:
                choices.append(Choice(
                    action_type="cast_effect",
                    cost="bonus_action",
                    effect_source="shillelagh",
                ))
            elif (
                self._has_searing_arc
                and action_is_weapon_attack
                and res.get("focus_points", 0) >= self._sas_fp_cost
            ):
                choices.append(self._searing_arc_choice())
            elif res.get("spellfire_spark", 0) >= 1:
                choices.append(Choice(
                    action_type="save_spell",
                    cost="bonus_action",
                    target=self._target,
                    save_stat="dex_save",
                    dc_stat="spell_save_dc",
                    damage_dice=self._sacred_flame_dice,   # FROM DATA
                    on_save="none",                        # save NEGATES
                    damage_type=self._sacred_flame_type,   # "radiant" (FROM DATA)
                    is_spell=True,                         # a cantrip → fuelable
                    resource_cost={"spellfire_spark": 1},
                ))
            elif self._starry_form_active:
                choices.append(self._attack_choice("archer", "bonus_action"))
            else:
                choices.append(self._attack_choice("unarmed", "bonus_action"))

        return choices

    def _searing_arc_choice(self) -> Choice:
        """Searing Arc Strike: upcast Burning Hands as a BA — a FIRE save-FOR-HALF
        save_spell.  Dice + on_save + type come FROM DATA (interpret_save_spell, at
        the chosen slot level); FP cost is policy arbitration.  is_spell=True (it IS
        a spell) but damage_type="fire", so Fueled Spellfire declines it — the
        cross-check that the damage_type gate, not just is_spell, does real work.

        Elemental Adept (fire): when the feat's element matches Searing Arc's fire,
        the cast IGNORES enemy fire resistance and high-grades each die 1->2
        (min_die=2) — so a fire-resistant enemy takes FULL Searing Arc.
        """
        ea = self._elemental_adept == self._sas_type   # "fire" == "fire"
        return Choice(
            action_type="save_spell",
            cost="bonus_action",
            target=self._target,
            save_stat="dex_save",
            dc_stat="spell_save_dc",
            damage_dice=self._sas_dice,                # FROM DATA (4d6 at slot 2)
            on_save=self._sas_on_save,                 # "half" (save-for-half)
            damage_type=self._sas_type,                # "fire" (NOT fuelable)
            is_spell=True,
            min_die=2 if ea else None,                 # Elemental Adept: treat 1 as 2
            ignore_resistance=ea,                      # Elemental Adept: bypass fire resist
            resource_cost={"focus_points": self._sas_fp_cost},
        )

    def _weapon_attack_choice(self, cost: str) -> Choice:
        """The Attack-action weapon swing: the Shillelagh-buffed quarterstaff while
        Shillelagh is up this combat (char L9+), else the plain quarterstaff."""
        if self._shillelagh_active:
            return self._shillelagh_attack_choice(cost)
        return self._attack_choice("quarterstaff", cost)

    def _shillelagh_attack_choice(self, cost: str) -> Choice:
        """Shillelagh quarterstaff: the damage die is upgraded along the dice
        ladder (1d10 at char L9-10, 1d12 at L11-16 — resolved FROM DATA into
        `_shillelagh_wis["dice"]` at policy init), and the swing MAY use WIS
        (spellcasting) instead of the weapon's normal DEX.

        Per the 2024 spell the stat is an OPTION, not an automatic override (user-
        flagged): use whichever ABILITY MODIFIER is higher, defaulting to the
        spellcasting stat on a tie.  The ladder die applies either way.  Here
        WIS(+4/+5) beats DEX(+3) so WIS wins; the comparison is kept explicit so
        the same data works for a future build whose physical stat is the higher one.
        """
        wis = self._shillelagh_wis            # 1d10, WIS mod, WIS-based to-hit
        dex = self._profiles["quarterstaff"]  # DEX mod, attack_bonus to-hit
        # bonus == the ability modifier, so comparing bonuses picks the higher
        # ability (PB is common to both to-hit values, so it cancels).  >= → tie
        # goes to the spellcasting (WIS) option.
        if wis["bonus"] >= dex["bonus"]:
            bonus, weapon_stat = wis["bonus"], wis["weapon_stat"]
        else:
            bonus, weapon_stat = dex["bonus"], dex["weapon_stat"]
        return Choice(
            action_type="attack",
            cost=cost,
            target=self._target,
            weapon_stat=weapon_stat,
            damage_dice=wis["dice"],           # 1d10 regardless of which stat wins
            damage_bonus=bonus,
        )

    def _attack_choice(
        self,
        profile: str,
        cost: str,
        resource_cost: "dict[str, int] | None" = None,
    ) -> Choice:
        """Build an attack Choice carrying a per-attack damage override (the
        multi-weapon primitive): its own dice/bonus and the WIS-or-DEX to-hit stat.
        """
        p = self._profiles[profile]
        return Choice(
            action_type="attack",
            cost=cost,
            target=self._target,
            weapon_stat=p["weapon_stat"],
            damage_dice=p["dice"],
            damage_bonus=p["bonus"],
            damage_type=p.get("damage_type"),       # "radiant" for GB/Archer
            is_spell=p.get("is_spell", False),       # only Guiding Bolt is a spell
            is_unarmed=p.get("is_unarmed", False),   # unarmed strike (Primal Strike gate)
            resource_cost=resource_cost or {},
        )

    # -- on-hit outgoing riders: Fount of Moonlight + Primal Strike (#6, L15+) --

    def on_hit(self, ctx: HitContext) -> "HitResponse | None":
        """Outgoing predicate riders (substrate #6) on a confirmed hit.

        Fount of Moonlight: while concentration is HELD (self._character.
        concentration == "fount_of_moonlight" — set by the turn-1 Magic-action cast,
        dropped on a failed CON save), every MELEE hit (quarterstaff AND unarmed)
        deals an extra 2d6 RADIANT.  The radiant is tagged
        is_spell=True, so when it resolves as its own DamageEvent the caster's
        on_deal_damage rider (Fueled Spellfire) fuels the FIRST such radiant each
        turn for free — matching the guide's `quarterstaff_{...fueled-spellfire(2)}
        --> 2d12+3d8+4d6...` (the 4d6 = FoM's +2d6 across two swings).  "Melee" is
        gated as "not a spell attack": at L15 every non-spell attack is melee
        (Guiding Bolt is the only is_spell attack, and is ranged), so the only
        ranged/melee subtlety — Starry-Form Archer — is moot (dropped from L9).

        Primal Strike: once on each of the character's turns, a WEAPON hit (RAW —
        the quarterstaff) deals an extra 1d8 of the chosen element (fire here).
        Built TOGGLEABLE: the non-RAW option (self._primal_strike_unarmed) also
        rides UNARMED strikes.  It is a FEATURE, not a spell (is_spell=False) → it
        is NOT Elemental-Adept-treated and NOT fueled — the cross-check that the
        is_spell gate does real work on the rider path (contrast the fire Searing
        Arc / Fire Shield thorns, which ARE spells and DO get the EA bypass).  The
        once/turn gate uses the round number (the character takes one turn/round).

        Both riders are FREE (no action economy, no resource), so the
        scheduler-side closure always accepts the HitResponse.  Returns None when
        neither applies (every level below L15 / a non-melee hit with no FoM).
        """
        riders: list[RiderDamageSpec] = []
        if self._character.concentration == "fount_of_moonlight" and not ctx.is_spell:
            riders.append(RiderDamageSpec(
                damage_dice=FOUNT_OF_MOONLIGHT_DICE,   # (2, 6)
                damage_type="radiant",
                is_spell=True,                         # a spell's radiant → fuelable
            ))
        if (
            self._has_primal_strike
            and not ctx.is_spell
            and (not ctx.is_unarmed or self._primal_strike_unarmed)
            and self._primal_strike_round != ctx.round_number
        ):
            self._primal_strike_round = ctx.round_number      # commit the 1/turn use
            riders.append(RiderDamageSpec(
                damage_dice=self._primal_strike_dice,  # (1, 8)
                damage_type=self._primal_strike_type,  # "fire" (chosen on hit)
                is_spell=False,                        # feature → not fueled / not EA
            ))
        if not riders:
            return None
        return HitResponse(
            resource_cost={},
            extra_damage_dice=[],
            action_cost=None,          # free riders — no economy slot consumed
            rider_damage=riders,
        )

    # -- defender-side reaction: Fire Shield thorns (substrate #5, L15+) ----

    def on_incoming_hit(self, ctx) -> "InterceptResponse | None":
        """Fire Shield thorns: while Fire Shield is up this combat, the bearer
        reflects the chosen mode's thorns (2d8 fire in WARM mode) at any enemy
        whose melee attack HITS — automatic, no roll (the intercept seam's
        reactive_damage, substrate #5).  When the thorns type matches our Elemental
        Adept element (warm = fire) the thorns bypass the attacker's resistance to
        that type and high-grade 1->2 (the thorns "qualify for our elemental adept
        feat" — guide 41:876).  Returns None when Fire Shield is down (the other
        ~3 combats/day), so no reaction fires.

        Note the thorns DamageEvent is bearer->attacker; since this build's enemy
        (the dummy) is BOTH the Scion's target and the attacker, the thorns land in
        the dummy's damage_received column — so they correctly count toward DPR.
        """
        if not self._fire_shield_active:
            return None
        mode = FIRE_SHIELD_MODES[self._fire_shield_mode]
        ttype = mode["thorns_type"]
        ea = self._elemental_adept == ttype
        return InterceptResponse(
            reactive_damage=ReactiveDamageSpec(
                damage_dice=FIRE_SHIELD_THORNS_DICE,
                damage_type=ttype,
                min_die=2 if ea else None,
                ignore_resistance=ea,
            )
        )

    # -- post-damage decision point: Fueled Spellfire (level 5+) ----------

    def on_deal_damage(self, ctx: DealDamageContext) -> "DamageRiderResponse | None":
        """Fueled Spellfire (Spellfire Adept, L5): ×1/turn, when a SPELL we cast
        deals RADIANT damage, expend up to 2 Hit Dice (d8) and add them to that
        damage roll.

        Policy = "greedy on the first qualifying radiant spell each turn, spend up
        to 2 HD while any remain".  The build's whole concept is to burn ALL the
        Hit Dice this way (5 at L5), so there is nothing to husband: the pool is
        the binding constraint (it empties in the first combat or two, exactly as
        the guide describes ~1-3 fueled combats/day).  Because the action (Guiding
        Bolt) resolves before the bonus action (Sacred Flame), the fuel naturally
        lands on Guiding Bolt while charges last — matching the guide's turn-1
        `guiding-bolt_{fueled-spellfire(2)}`.

        Gates (all policy-side; the engine just offers the seam on every DamageEvent
        we deal):
          - off unless Fueled Spellfire is online (Hit-Dice pool present, L5+);
          - SPELL radiant damage only (so Starry-Form Archer — radiant, but a
            feature — and our weapon strikes are excluded);
          - 1/turn (a turn dealing radiant damage twice fuels only the first);
          - a Hit Die must remain.
        """
        if not self._fueled_spellfire:
            return None
        if ctx.damage_type != "radiant" or not ctx.is_spell:
            return None
        turn = (ctx.round_number, ctx.turn_index)
        if self._fueled_turn == turn:                  # already fueled this turn
            return None
        available = ctx.resources.get("hit_dice", 0)
        if available < 1:
            return None
        n = min(2, available)                          # expend up to 2 Hit Dice
        self._fueled_turn = turn                       # commit the 1/turn use
        return DamageRiderResponse(
            extra_damage_dice=[(n, 8)],                # Nd8 added (no CON mod)
            resource_cost={"hit_dice": n},
        )


# ---------------------------------------------------------------------------
# Enemy-strikes-back loop: the shared ScriptedEnemyPolicy (src/builds/enemy.py),
# imported and re-exported above so ``ss.ScriptedEnemyPolicy`` still resolves.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Full day-runner assembly (used by the validation harness / tests)
# ---------------------------------------------------------------------------

def make_day_runner(
    level: int,
    rng: "SeededRNG",
    rounds_per_combat: int = 4,
    primal_strike_unarmed: "bool | None" = None,
    fourth_level_spell: str = "fount_of_moonlight",
    precast_mode: "str | None" = None,
    precast_prob: float = 0.5,
    with_party: bool = False,
):
    """Assemble (DayRunner, character, dummy) for the given level.

    `primal_strike_unarmed` (L15+) overrides the data row's RAW default for Primal
    Strike: None = RAW (weapon attacks only), True = the non-RAW option that also
    rides unarmed strikes — so a caller can compare the two DPR readings.

    `fourth_level_spell` (L15+) selects which 4th-level spell the build prepares for
    the single slot_4th slot — "fount_of_moonlight" (default, the guide's pick) or
    "fire_shield".  Exactly one is cast per day (they are separate daily loadouts).

    `precast_mode` / `precast_prob` (L15+) tune whether that 4th-level buff is
    PRE-CAST (free, before initiative) or CAST IN COMBAT (a real turn cost +
    concentration) — the pre-cast assumption toggle (memory
    precast-assumption-as-a-toggle).  "always" = always pre-cast (DPR upper bound),
    "never" = always in combat (lower bound), "rng" = pre-cast with probability
    precast_prob (rolled once per combat through the seeded channel), None = each
    effect's legacy default (Fire Shield pre-cast, FoM in-combat; draws no dice).

    Through L12 the enemy carries no attack profile, so it gets no policy and
    never acts; DPR = damage dealt to the dummy = the character's whole output.
    From the level where the row carries an ``enemy_attack`` profile, the enemy
    also gets a ScriptedEnemyPolicy so it strikes the character — the
    enemy-strikes-back loop that makes Fire Shield thorns (#5) and incoming-damage
    resistance (#4) do real work.  DPR still reads the dummy's column, so the
    enemy's own damage to the character never pollutes it.

    `with_party` (L15+, substrate #7 / 7c foundation-min) registers a passive PARTY
    MEMBER (``make_party_member`` — one extra friendly HP pool, design.md §3.6) and
    switches the enemy to MULTI-ENTITY targeting: it splits its swings across
    {character, party} by the row's ``char_weight``/``party_weight`` (design.md
    §3.5).  So the character is attacked on only a fraction of swings and its
    Fire-Shield thorns fire less — dissolving the single-dummy thorns over-count
    (PROGRESS session 16).  DEFAULT False keeps the legacy 1-vs-1 scenario
    bit-identical (every prior DPR/ablation number is unchanged).  Read the build's
    own DPR column from the result via ``damage_by_source(char.id)`` (equals the old
    ``damage_received_by(dummy.id)`` in the no-party case, since the character only
    damages the dummy); the passive party member itself deals nothing.
    """
    char = make_starfire_scion(level)
    dummy = make_training_dummy(level)
    policy = StarfireScionPolicy(
        level=level, character=char, target=dummy, rounds_per_combat=rounds_per_combat,
        primal_strike_unarmed=primal_strike_unarmed,
        fourth_level_spell=fourth_level_spell,
        precast_mode=precast_mode,
        precast_prob=precast_prob,
    )
    policies: dict[int, object] = {char.id: policy}
    entities: list[Entity] = [char, dummy]

    ea = LEVELS[level].get("enemy_attack")
    if ea:
        if with_party:
            # Multi-entity (7c): a passive party member soaks a share of attacks;
            # the enemy splits its swings across the weighted friendly roster.
            party = make_party_member(level)
            entities.append(party)
            policies[dummy.id] = ScriptedEnemyPolicy(
                target=char,
                n_attacks=ea.get("n_attacks", 2),
                rounds_per_combat=rounds_per_combat,
                roster=[(char, ea.get("char_weight", 2)),
                        (party, ea.get("party_weight", 1))],
            )
        else:
            policies[dummy.id] = ScriptedEnemyPolicy(
                target=char,
                n_attacks=ea.get("n_attacks", 2),
                char_target_prob=ea.get("char_target_prob", 1.0),
                rounds_per_combat=rounds_per_combat,
            )

    runner = DayRunner(
        rng=rng,
        entities=entities,
        policies=policies,
        rounds_per_combat=rounds_per_combat,
    )
    return runner, char, dummy


def make_ally_effects_runner(
    level: int,
    rng: "SeededRNG",
    effect: "str | None",
    rounds_per_combat: int = 4,
):
    """Assemble (DayRunner, char, ally, dummy) for the substrate-#7 / 7c ALLY-EFFECTS
    scenario (the Scion + synthetic-ally vehicle).

    The Scion is the CASTER; a synthetic ``make_ally`` is the friendly entity the
    ally-effect lands on; the enemy (``dummy``) is a melee attacker whose every swing
    targets the ALLY (a single-entity roster ``[(ally, 1)]``), isolating the effect.
    ``effect`` selects the ally-effect (``"warding_bond"`` / ``"protection"`` /
    ``"sanctuary"``), or ``None`` for the baseline (no rider — attacks land in full),
    so a test can read the effect's directional impact off the per-(source,target)
    DPR ledger:

      - warding bond: the enemy's damage to the ally is ALSO dealt to the caster —
        ``damage_source_to(enemy, char) ≈ damage_source_to(enemy, ally)`` (the share);
      - protection / sanctuary: ``damage_source_to(enemy, ally)`` drops below the
        ``effect=None`` baseline (disadvantage / save-or-negate cut the landed hits).
    """
    char = make_starfire_scion(level)
    ally = make_ally(level)
    dummy = make_training_dummy(level)
    policy = StarfireScionPolicy(
        level=level, character=char, target=dummy, rounds_per_combat=rounds_per_combat,
    )
    policies: dict[int, object] = {char.id: policy}
    entities: list[Entity] = [char, ally, dummy]

    if effect is not None:
        ally_policy = AllyEffectPolicy(effect=effect, ally=ally, caster=char)
        ally_policy.install()                       # pre-cast the persistent payload
        policies[ally.id] = ally_policy

    ea = LEVELS[level].get("enemy_attack")
    if ea:
        # The enemy attacks the ALLY on every swing (legacy single-target mode with
        # char_target_prob=1.0 — the friendly here is the ally), so the ally-effect
        # is the only thing modulating its incoming damage.  (A single-entity roster
        # would degenerate to a weight-1 d1 pick; single-target mode is the clean fit.)
        policies[dummy.id] = ScriptedEnemyPolicy(
            target=ally,
            n_attacks=ea.get("n_attacks", 2),
            char_target_prob=1.0,
            rounds_per_combat=rounds_per_combat,
        )

    runner = DayRunner(
        rng=rng,
        entities=entities,
        policies=policies,
        rounds_per_combat=rounds_per_combat,
    )
    return runner, char, ally, dummy
