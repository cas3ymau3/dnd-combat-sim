"""
starfire_scion.py — The Starfire Scion build: per-level stat blocks + (eventually)
a daily-plan policy.  SCAFFOLD ONLY for now: per-level *data* + this plan
docstring.  No policy, no engine calls, no `make_*` assembly yet — those wait on
the first new engine primitive this build forces (save-FOR-damage resolution).

Source of truth for intent:
  - design/build-guides/41_spellfire_scion.txt  (level-by-level notes + DPR
    *ceilings* — see the validation-framing note below)

The build (see PROGRESS.md "Second archetype — STARFIRE SCION")
---------------------------------------------------------------
**Monk-08 (Sun-Soul) / Druid-12 (Circle of Stars)** — a WIS-based spellfire
"blaster" gish.  Point-buy DEX 16 (+3), CON 14, WIS 17 (+2, → 20 by L12), STR 8.
Selected as the second archetype because it forces the two highest-value untouched
model gaps via SINGLE-TARGET deliveries (so it sidesteps the unbuilt multi-enemy /
spatial axis):

  1. **Save-FOR-DAMAGE resolution** — a save whose *result determines damage
     dealt*.  Sacred Flame (DEX save, save-*negates*: full 2d8 on fail, nothing on
     success) and Burning Hands / Searing Arc Strike (DEX save, save-*for-half*).
     New: our only save today is concentration (target-side, incoming-damage-
     driven, binary drop/keep); no attacker has ever carried a `spell_save_dc`.
  2. **Upcast / `level_reference` scaling** — cantrip scaling (Sacred Flame
     1d8→2d8→3d8→4d8 at char L5/11/17) and Searing Arc Strike (upcast Burning
     Hands, +1d6/slot level, from L10).  These are the `increment`/`level_reference`
     cases `src/content.py` currently raises LOUDLY on.

VALIDATION FRAMING (important — differs from War Angel)
-------------------------------------------------------
The guide's per-level DPR numbers are **"all-hit CEILINGS,"  not targets**: they
assume every attack hits and the enemy always fails its save (no AC, no misses, no
successful saves, no stunning-strike resistance).  This build has **no ground-truth
DPR ladder** — producing honest DPR for it is itself a goal of the model.  So
validation is **consistency + sanity** (like War Angel L16), NOT number-matching:
per-hit / per-save *damage math* exact; DPR grows monotonically; computed DPR is a
*plausible fraction* of the ceiling given that level's hit / save-fail rates.  The
`ceiling_dpr` field below is a loose UPPER BOUND, never a target.

Enemy model: because we now force enemy saves, the enemy's save bonus is a live
input — sourced per character level from
`reference/data/monster_ac_and_saves_by_level.csv` (`ac` + `dex.save.mod`), which
has been read-only until this build.  `enemy_ac` / `enemy_dex_save` below are
copied from that table (level == cr row).

What is NOT modeled here (deferred — see PROGRESS "Open threads")
----------------------------------------------------------------
  - **Multi-enemy AoE / spatial** — Burning Hands is an AoE save spell; modeled
    SINGLE-TARGET until a multi-enemy model exists.
  - **Guiding Bolt's advantage grant → allies** — Guiding Bolt is an ATTACK-ROLL
    spell (2024): 4d6 radiant on hit + grant-advantage on the target until end of
    our next turn.  That advantage realistically benefits an ALLY (we rarely
    consume it).  We have no ally model; initially treat Guiding Bolt as a plain
    4d6 attack (advantage grant ignored or self-consumed).  Decide when we get
    there; do NOT build an ally model now.
  - **Stunning Strike, wild-shape beast forms, healing** — out of the DPR critical
    path in the threshold model.

Ability-online timeline (from the progression summary; drives where each gap
first becomes load-bearing)
---------------------------------------------------------------------------
  L1  Monk-1.  Unarmored defense (AC 16).  Martial arts (1d6): quarterstaff action
        + BA unarmed strike.  Spellfire Spark → Sacred Flame (1d8) castable as a BA
        xPB/LR.  [First save-for-damage delivery, but melee is the bread-and-butter.]
  L2  +Druid-1.  Spellcasting (L1 slots), cantrips (produce flame, etc.).
  L3  +Druid-2.  Wild shape (utility).
  L4  +Druid-3 (Stars).  Star Map → free Guiding Bolt xWIS/LR (ATTACK roll).
        Starry Form (archer = BA ranged spell attack; dragon = concentration aid).
        L2 spells: Flame Blade (concentration melee), Prayer of Healing.
  L5  +Druid-4.  **Spellfire Adept**: +1 WIS (→18); **Fueled Spellfire** (≤2 hit
        dice added to one radiant damage roll, 1/turn — the "smite-on-radiant"
        rider); Searing Spellfire (radiant ignores resistance).  **Cantrip scaling**
        → Sacred Flame 2d8.  [Blaster identity online: save-for-damage + scaling +
        radiant rider all converge here — the first "interesting" level.]
  L6  +Monk-2.  Focus points / unarmored movement.
  L7  +Monk-3 (Sun-Soul).  Radiant sun-bolt (backup), deflect attacks.
  L8  +Monk-4.  Elemental Adept (fire): +1 WIS (→19).
  L9  +Monk-5.  Extra Attack; martial arts 1d8.
  L10 +Monk-6.  **Searing Arc Strike** = cast (upcast) Burning Hands as a BA after
        the Attack action.  [First UPCAST `increment` scaling.]
  L11 +Monk-7.  Evasion.
  L12 +Monk-8.  Resilient (WIS → 20, WIS-save prof).  Burning Hands upcast to L3
        (5d6) via BA.
  L13 +Druid-5.  L3 spells (Elemental Weapon — flat radiant weapon buff).
  L14 +Druid-6.  Cosmic Omen.
  L15 +Druid-7.  Primal Strikes (flat melee radiant boost); L4 spells (Fount of
        Moonlight, Fire Shield).
  L16 +Druid-8.  ASI: +2 DEX (→18).
  L17 +Druid-9.  L5 spells.  Cantrip scaling → Sacred Flame 3d8... (4d8 at L17).
  L18 +Druid-10.  Twinkling Constellations.
  L19 +Druid-11.  L6 spells (Sunbeam — a real AoE line, save-for-half).
  L20 +Druid-12.  ASI: +2 DEX (→20); WIS/DEX attack modes equivalent.

Engine-capacity build order (NONE built yet — see PROGRESS):
  1. [DONE] `spell_save_dc` on the attacker + save-FOR-damage resolution path
     (negates + for-half).  Built & validated on Sacred Flame (L1/L5 data) via a
     `SaveDamageEvent` + `resolve_save_damage`; the policy emits a
     `Choice(action_type="save_spell", save_stat=..., damage_dice=..., on_save=...)`.
  2. [NEXT] Cantrip / `level_reference` dice scaling.
  3. Upcast `increment` scaling (Searing Arc Strike).
"""

from __future__ import annotations

# Spellfire Spark grants Sacred Flame, castable as a bonus action PB times per LR.
# (At higher levels the action economy is dominated by Sacred Flame / Searing Arc
# Strike / archer-form BA attacks — captured per level once the policy is built.)

# Spell save DC = 8 + PB + WIS mod.  Recorded per level below (`spell_save_dc`).

# ---------------------------------------------------------------------------
# Per-level build data — SCAFFOLD
# ---------------------------------------------------------------------------
# Mirrors war_angel.py's LEVELS convention, with build-specific additions for the
# new save-for-damage dimension:
#   spell_save_dc   — our DC for Sacred Flame / Burning Hands (8 + PB + WIS).
#   enemy_dex_save  — enemy d20 save BONUS, from monster_ac_and_saves_by_level.csv.
#   ceiling_dpr     — the guide's ALL-HIT upper bound (NOT a target; see docstring).
#   ba_*            — the bonus-action attack (monk martial-arts unarmed strike).
# Only L1 is filled in (well-understood melee baseline, already engine-supportable);
# L2+ are stubbed until we climb the ladder.  Sacred Flame as a save-for-damage
# delivery is the FIRST new primitive — validated at the level it becomes
# load-bearing (~L5, cantrip scaling), not necessarily L1.
LEVELS: dict[int, dict] = {
    1: {
        # Action: quarterstaff (versatile 1d8), DEX-based via monk martial arts.
        "weapon": "quarterstaff",
        "attack_bonus": 5,            # PB 2 + DEX 3
        "damage_dice": (1, 8),        # quarterstaff versatile die ≥ martial-arts 1d6
        "damage_bonus": 3,            # DEX
        # Bonus action: monk unarmed strike (martial-arts die 1d6 + DEX).
        "ba_attack_dice": (1, 6),
        "ba_attack_bonus": 5,         # PB 2 + DEX 3
        "ba_damage_bonus": 3,         # DEX
        # Sacred Flame (Spellfire Spark): BA cantrip, 1d8, DEX save-NEGATES, 2/LR.
        "sacred_flame_dice": (1, 8),
        "spell_save_dc": 13,          # 8 + PB 2 + WIS 3
        "char_ac": 16,                # 10 + DEX 3 + WIS 3 (unarmored defense)
        "char_hp": 8,                 # monk-1 d8 + CON 2 (DPR-irrelevant; threshold)
        # Enemy (monster_ac_and_saves_by_level.csv, level 1 / cr 1):
        "enemy_ac": 13,
        "enemy_dex_save": 1,
        "ceiling_dpr": 14.0,          # guide all-hit melee (1d8+3 + 1d6+3); NOT a target
    },
    # L2–L20: TODO — fill per level as we climb the validation ladder.  The first
    # "interesting" level is L5 (Spellfire Adept: cantrip scaling + Fueled Spellfire
    # converge — save-for-damage becomes the primary damage source there).
}


def make_starfire_scion(level: int):  # noqa: ANN201 — return type TBD with engine
    """Placeholder.  Returns the Entity for `level` once the build is implemented.

    Not built yet: this build needs the save-FOR-damage engine primitive (and
    `spell_save_dc` on the attacker) before its policy can be written.  See the
    module docstring's "Engine-capacity build order".
    """
    raise NotImplementedError(
        "starfire_scion is a scaffold (data + plan only); the save-for-damage "
        "engine primitive must be built first — see PROGRESS.md and the module "
        "docstring."
    )
