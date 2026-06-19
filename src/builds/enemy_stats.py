"""
enemy_stats.py — per-Challenge-Rating baseline monster offense (decision #12's
unrealised half).

CLAUDE.md decision #12 said the enemy's numeric profile — attack bonus / save DC /
damage — should come from per-CR data, but only AC + saves were ever pulled in.
This module supplies the missing half from the user's "Average Monster Stats by CR"
chart (Rothner), verified 2026-06-19 (per-feature ritual):

  - per-CR ATTACK BONUS, SAVE DC, and — crucially — the actual MULTIATTACK DICE (a
    2-attack routine) and the AoE save-for-half DICE.  Because we carry the dice (not
    just an averaged number), the engine rolls REAL attacks → enemy CRITS fall out
    (resolve_attack_roll doubles the dice count on a natural 20).
  - a LEVEL → CR mapping (the chart's "Level" column): a given CR is a baseline for a
    much HIGHER character level than CR == level would suggest — CR 8 ↔ level 14, CR 5
    ↔ level 9.  So a level-8 character's baseline solo enemy is ~CR 5, not CR 8; using
    ``level_to_cr`` (instead of cr == level) is what makes the enemy's damage realistic
    rather than brutal for a lone summon.

The chart's "To Hit Bonus" / "DC" are half-integer averages; they are rounded to the
nearest integer here (a d20 bonus must be integral).  The "Damage/Round" column equals
twice the per-attack multiattack average (2-attack routine), so we derive DPR from the
dice rather than storing it separately.
"""

from __future__ import annotations

# Per-CR baseline rows from the chart.  Each value:
#   (to_hit, save_dc, attack_dice, aoe_dice)
# where attack_dice / aoe_dice are (count, sides, flat_bonus):
#   - attack_dice: the damage of ONE swing of the 2-attack multiattack routine
#     (the engine emits two of these and rolls each; crits double the dice).
#   - aoe_dice: the save-for-half AoE damage (one effect, half on a made save).
# to_hit / save_dc are the chart's averages rounded to the nearest integer (.5 up).
_CR_ROWS: dict[int, tuple[int, int, tuple[int, int, int], tuple[int, int, int]]] = {
    0:  (4, 11, (1, 8, 2),  (1, 8, 0)),    # CR 1/4
    1:  (5, 12, (1, 8, 2),  (2, 6, 0)),
    2:  (5, 12, (1, 12, 3), (3, 6, 0)),
    3:  (6, 13, (2, 8, 3),  (4, 6, 2)),
    4:  (6, 13, (2, 10, 4), (5, 6, 2)),
    5:  (7, 14, (4, 6, 3),  (6, 6, 0)),
    6:  (7, 14, (5, 6, 4),  (7, 6, 0)),
    7:  (8, 15, (3, 12, 4), (6, 8, 0)),
    8:  (8, 15, (4, 10, 5), (12, 4, 0)),
    9:  (9, 16, (4, 12, 4), (6, 10, 0)),
    10: (9, 16, (8, 6, 5),  (8, 8, 0)),
    11: (10, 17, (7, 8, 5), (9, 8, 0)),
    12: (10, 17, (6, 10, 6), (8, 10, 0)),
    13: (11, 18, (8, 8, 5), (7, 12, 0)),
    14: (11, 18, (6, 12, 6), (9, 10, 0)),
    15: (12, 19, (12, 6, 6), (15, 6, 0)),
    16: (12, 19, (8, 10, 7), (16, 6, 0)),
    17: (13, 20, (14, 6, 6), (17, 6, 0)),
}

# Character LEVEL → baseline solo-enemy CR (the chart's "Level" column, inverted +
# interpolated across its gaps).  A CR is a baseline for a much higher level than
# CR == level: CR 8 ↔ L14, CR 5 ↔ L9.  This is the "less harsh" lever — a lone
# level-8 summon faces ~CR 5, not CR 8.
_LEVEL_TO_CR: dict[int, int] = {
    1: 0, 2: 1, 3: 1, 4: 2, 5: 3, 6: 4, 7: 4, 8: 5, 9: 5, 10: 6,
    11: 7, 12: 7, 13: 8, 14: 8, 15: 9, 16: 9, 17: 10, 18: 11, 19: 12, 20: 13,
}

# Default split of save-forcing effects across the SIX save types ("varying
# probability for each" — the user's request).  Reflects typical monster effects:
# physical/AoE leans DEX + CON, fear/charm WIS, grapple/shove STR, banish/dominate
# CHA, psychic INT.  Weights are relative (need not sum to 1); pre-rolled through the
# seeded channel so decide() stays dice-free.
SAVE_TYPE_WEIGHTS: dict[str, int] = {
    "dex_save": 30,
    "con_save": 25,
    "wis_save": 20,
    "str_save": 12,
    "cha_save": 8,
    "int_save": 5,
}

# Fraction of an enemy's rounds spent forcing a SAVE (an AoE / breath / gaze) rather
# than making attack rolls.  Most monsters mostly attack; ~1/3 save rounds is a
# reasonable default for a save-capable bruiser.  Tunable per enemy.
SAVE_ROUND_PROB = 0.35


def _row(cr: int) -> tuple[int, int, tuple[int, int, int], tuple[int, int, int]]:
    cr = max(0, min(17, cr))
    return _CR_ROWS[cr]


def level_to_cr(level: int) -> int:
    """The baseline solo-enemy CR for a character *level* (the chart's Level column).

    CR is a baseline for a much higher level than CR == level (CR 8 ↔ L14), so this is
    what keeps a lone summon's enemy from being brutally over-CR."""
    if level in _LEVEL_TO_CR:
        return _LEVEL_TO_CR[level]
    return 0 if level < 1 else 13


def baseline_save_dc(cr: int) -> int:
    """The enemy's save DC at challenge rating *cr* (chart, rounded)."""
    return _row(cr)[1]


def baseline_attack_bonus(cr: int) -> int:
    """The enemy's attack bonus at *cr* (chart, rounded)."""
    return _row(cr)[0]


def baseline_attack_dice(cr: int) -> tuple[int, int, int]:
    """The per-swing damage dice (count, sides, flat_bonus) of the enemy's 2-attack
    multiattack routine at *cr* — rolled per attack so crits double the dice."""
    return _row(cr)[2]


def baseline_aoe_dice(cr: int) -> tuple[int, int, int]:
    """The save-for-half AoE damage dice (count, sides, flat_bonus) at *cr*."""
    return _row(cr)[3]


def baseline_dpr(cr: int) -> float:
    """The all-hits-land damage-per-round budget at *cr*, derived from the multiattack
    dice (two swings).  Used for reference / sanity checks; the policy rolls the dice."""
    n, sides, bonus = baseline_attack_dice(cr)
    return 2 * (n * (sides + 1) / 2 + bonus)
