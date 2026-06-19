"""
enemy_stats.py — per-Challenge-Rating baseline monster offense (decision #12's
unrealised half).

CLAUDE.md decision #12 said the enemy's numeric profile — attack bonus / save DC /
damage — should come from per-CR data, but only AC + saves were ever pulled in
(``reference/data/monster_ac_and_saves_by_level.csv``).  Today's build rows carry
"illustrative" enemy_attack numbers.  This module supplies the missing half: a
per-CR baseline for the enemy's ATTACK BONUS, SAVE DC, and DAMAGE OUTPUT, so an
enemy can be stood up at the encounter's CR with realistic offense.

Sources (verified 2026-06-19, per-feature ritual)
-------------------------------------------------
- Tom Dunn, "Baseline Monster Statistics" (regression over published 5e monsters):
  Attack Bonus ≈ 3.5 + CR/2, Save DC ≈ 11.5 + CR/2, DPR ≈ 6 + 6·CR (CR < 20).
  https://tomedunn.github.io/the-finished-book/monsters/baseline-monster-stats/
- The user's secondary source (Reddit r/DMAcademy "average monster stats" chart):
  Average Damage per Round ≈ 6 + 3·CR.

Reconciling the two DPR figures — they are the SAME model from two ends:
  * Tom Dunn's 6 + 6·CR is the damage assuming **all attacks land** (the budget
    before any hit-rate discount).
  * The Reddit 6 + 3·CR is roughly the **expected** damage after a typical ~50%
    hit rate (6 + 6·CR halved).
Our engine ROLLS the enemy's attacks and saves (the user's explicit request: "the
enemy tests all our different saving throws ... and makes attack rolls"), so the
dice apply the hit/save rate themselves.  We therefore feed in the ALL-HITS-LAND
budget (``DPR_PER_CR``) and let the rolls discount it; using 6 + 3·CR as on-hit
damage AND rolling would double-discount.  ``DPR_COEFF`` is the one knob to retune
if a different magnitude is wanted.

The numbers below are the per-CR table values (CR 1–12 from Tom Dunn, lower/higher
CRs by formula).  Attack bonus and save DC differ by a constant 8 across the whole
table (AB = DC − 8), the standard 5e offense relationship.
"""

from __future__ import annotations

# All-hits-land damage-per-round budget: DPR = 6 + DPR_COEFF·CR (Tom Dunn = 6).
# The single knob to retune enemy lethality (e.g. drop to 3 for the Reddit
# "expected" magnitude — but then the engine's own rolls would under-count).
DPR_COEFF = 6

# Per-CR SAVE DC (Tom Dunn baseline table; AB = DC − 8).  CR 0–20.
_SAVE_DC_BY_CR: dict[int, int] = {
    0: 13, 1: 13, 2: 13, 3: 13, 4: 14, 5: 14, 6: 15, 7: 15, 8: 16, 9: 16,
    10: 17, 11: 17, 12: 18, 13: 18, 14: 19, 15: 19, 16: 20, 17: 20, 18: 21,
    19: 21, 20: 22,
}

# Default split of save-forcing effects across the SIX save types ("varying
# probability for each" — the user's request).  Reflects typical monster effects:
# physical/AoE leans DEX + CON, fear/charm WIS, grapple/shove STR, banish/dominate
# CHA, psychic INT.  Weights are relative (need not sum to 1); pre-rolled through
# the seeded channel so decide() stays dice-free.
SAVE_TYPE_WEIGHTS: dict[str, int] = {
    "dex_save": 30,
    "con_save": 25,
    "wis_save": 20,
    "str_save": 12,
    "cha_save": 8,
    "int_save": 5,
}

# Fraction of an enemy's rounds spent forcing a SAVE (an AoE / breath / gaze)
# rather than making attack rolls.  Most monsters mostly attack; ~1/3 save rounds
# is a reasonable default for a save-capable bruiser.  Tunable per enemy.
SAVE_ROUND_PROB = 0.35


def baseline_save_dc(cr: int) -> int:
    """The enemy's save DC at challenge rating *cr* (Tom Dunn baseline table)."""
    if cr in _SAVE_DC_BY_CR:
        return _SAVE_DC_BY_CR[cr]
    # Out-of-table fallback: DC ≈ 11.5 + CR/2 (round half up).
    return int(11.5 + cr / 2 + 0.5)


def baseline_attack_bonus(cr: int) -> int:
    """The enemy's attack bonus at *cr* — a constant 8 below the save DC across the
    whole 5e offense table (AB = DC − 8)."""
    return baseline_save_dc(cr) - 8


def baseline_dpr(cr: int) -> int:
    """The enemy's all-hits-land damage-per-round budget at *cr* (6 + DPR_COEFF·CR).

    This is split across the enemy's attacks (or delivered whole on a save-forcing
    round); the engine's to-hit / save rolls apply the hit-rate discount, so this is
    the PRE-discount budget (see the module docstring's reconciliation)."""
    return 6 + DPR_COEFF * cr
