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
from ..policy import Choice, DamageRiderResponse, DealDamageContext, GameState
from ..resources import ResourceEntry, ResourcePool
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
        # Per-combat state, (re)set by on_combat_start.
        self._starry_form_active: bool = False
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

    # -- decision point ---------------------------------------------------

    def decide(self, snapshot: GameState) -> list[Choice]:
        res = snapshot.resources
        choices: list[Choice] = []

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

        # ACTION: Guiding Bolt (free Star Map cast) while charges remain, else a
        # quarterstaff attack.  Greedy on the free casts — across statistically
        # identical combats, when they fire does not change mean DPR.
        #
        # Track whether this turn's action is a WEAPON attack (quarterstaff/unarmed)
        # vs. casting a spell (Guiding Bolt): Searing Arc Strike requires the *Attack
        # action*, which Guiding Bolt — though delivered via an attack roll in the
        # engine — does NOT count as (it is the Magic action).  So the gate is "a
        # weapon attack was the action", true for quarterstaff, false for Guiding Bolt.
        action_is_weapon_attack = False
        if res.get("action", 0) >= 1:
            if self._has_guiding_bolt and res.get("guiding_bolt_free", 0) >= 1:
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
        # EXCEPT turn 1 of each combat, when the bonus action is spent CASTING
        # Shillelagh (guide 41:539 — "BA:shillelagh").  This is now a first-class
        # cast_effect that CONSUMES the bonus action (no damage) — the honest model,
        # replacing the former "withhold the BA option" suppression (DPR-identical:
        # the BA is consumed either way).  Shillelagh then persists and buffs every
        # quarterstaff swing for the rest of the combat (the weapon swings read
        # _shillelagh_active), so the BA damage ladder runs from round 2.  (Pure
        # read: the cantrip was flagged active in on_combat_start; here we only
        # consult round_number.)  See design/buff_primitive.md.
        if res.get("bonus_action", 0) >= 1:
            if self._shillelagh_active and snapshot.round_number == 1:
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
        """
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
            resource_cost=resource_cost or {},
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

def make_day_runner(level: int, rng: "SeededRNG", rounds_per_combat: int = 4):
    """Assemble (DayRunner, character, dummy) for the given level.

    Through L12 the enemy carries no attack profile, so it gets no policy and
    never acts; DPR = damage dealt to the dummy = the character's whole output.
    From the level where the row carries an ``enemy_attack`` profile, the enemy
    also gets a ScriptedEnemyPolicy so it strikes the character — the
    enemy-strikes-back loop that makes Fire Shield thorns (#5) and incoming-damage
    resistance (#4) do real work.  DPR still reads the dummy's column, so the
    enemy's own damage to the character never pollutes it.
    """
    char = make_starfire_scion(level)
    dummy = make_training_dummy(level)
    policy = StarfireScionPolicy(
        level=level, character=char, target=dummy, rounds_per_combat=rounds_per_combat
    )
    policies: dict[int, object] = {char.id: policy}

    ea = LEVELS[level].get("enemy_attack")
    if ea:
        policies[dummy.id] = ScriptedEnemyPolicy(
            target=char,
            n_attacks=ea.get("n_attacks", 2),
            char_target_prob=ea.get("char_target_prob", 1.0),
            rounds_per_combat=rounds_per_combat,
        )

    runner = DayRunner(
        rng=rng,
        entities=[char, dummy],
        policies=policies,
        rounds_per_combat=rounds_per_combat,
    )
    return runner, char, dummy
