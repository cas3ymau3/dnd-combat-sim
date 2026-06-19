"""
enemy_stats.py — per-CHARACTER-LEVEL baseline monster offense (decision #12's
unrealised half).

CLAUDE.md decision #12 said the enemy's numeric profile — attack bonus / save DC /
damage — should come from per-CR data, but only AC + saves were ever pulled in
(``reference/data/monster_ac_and_saves_by_level.csv``, keyed by level == CR).  This
module supplies the missing OFFENSIVE half, per character level, so it pairs 1:1 with
that AC/saves table.

Derivation (user spec, 2026-06-19)
----------------------------------
1. Source chart: the user's "Average Monster Stats by CR" (Rothner) — ``_CR_ROWS``
   below (per-CR to-hit, save DC, multiattack dice, AoE dice).
2. Fit a simple curve to each column vs CR (linear for to-hit / DC, quadratic for the
   damage averages — all R² > 0.99) and evaluate it AT CR == LEVEL.  We deliberately
   IGNORE the chart's "Level" column (which pairs a CR with a higher party level) and
   instead treat CR == level, matching the AC/saves table's convention.
3. Divide the DAMAGE outputs (per-swing, AoE) by ``DAMAGE_DIVISOR`` = 1.5.  Rationale:
   a CR-N monster is balanced for a party of FOUR level-N PCs, but here we field at
   most three friendlies (character + summon + ally) and the enemy is never killed /
   incapacitated by them — so its un-attrited incoming damage is over-inflated.  To-hit
   and DC are NOT divided (they aren't damage).
4. Re-express each damage average as DICE so enemy CRITS fall out of the engine (a
   natural 20 doubles the dice, not the flat).  Per-swing = ``N dX + PB`` where:
     - X = the attack die SIZE from the matching CR == level chart row (the largest
       matched CR row, 17, is reused for levels 18-20);
     - PB = the character/monster proficiency bonus at that level, added as the FLAT
       (non-crit-doubling) part — a weapon swing's "+mod";
     - N = chosen so N·avg(dX) + PB matches the ÷1.5 per-swing target.
   AoE = ``M dY`` (matched AoE die size; NO flat — save spells don't crit, so there is
   nothing to keep out of the doubling).
5. ``n_attacks`` = 2 (the chart's two-attack multiattack routine), exposed as a column.

The whole per-level table is computed once at import from ``_CR_ROWS`` (so it never
goes stale if the source chart is edited); ``level_table()`` returns it for inspection,
and ``reference/data/enemy_stats_by_level.csv`` is a generated snapshot for eyeballing.
"""

from __future__ import annotations

import numpy as np

# 3-vs-4 party size + enemy-never-incapacitated correction (see derivation step 3).
DAMAGE_DIVISOR = 1.5

# Source chart (Rothner "Average Monster Stats by CR").  Each value:
#   (to_hit, save_dc, attack_dice, aoe_dice)   with dice = (count, sides, flat_bonus)
# attack_dice is ONE swing of the 2-attack routine; aoe_dice is the save-for-half AoE.
# to_hit / save_dc are the chart's averages rounded to the nearest integer.
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

_N_ATTACKS = 2                                 # the chart's 2-attack multiattack routine

# Default split of save-forcing effects across the SIX save types ("varying
# probability for each").  Physical/AoE leans DEX + CON; fear/charm WIS; grapple/shove
# STR; banish/dominate CHA; psychic INT.  Weights are relative (need not sum to 1).
SAVE_TYPE_WEIGHTS: dict[str, int] = {
    "dex_save": 30, "con_save": 25, "wis_save": 20,
    "str_save": 12, "cha_save": 8, "int_save": 5,
}

# Fraction of an enemy's rounds spent forcing a SAVE rather than attacking.
SAVE_ROUND_PROB = 0.35


def _avg(count: int, sides: int, bonus: int) -> float:
    return count * (sides + 1) / 2 + bonus


def _pb(level: int) -> int:
    """Proficiency bonus by character level (2 / 3 / 4 / 5 / 6)."""
    return 2 + (level - 1) // 4


def _attack_die(level: int) -> int:
    """Attack die SIZE matched from the CR == level chart row (clamp >17 to 17)."""
    return _CR_ROWS[min(level, 17)][2][1]


def _aoe_die(level: int) -> int:
    """AoE die SIZE matched from the CR == level chart row (clamp >17 to 17)."""
    return _CR_ROWS[min(level, 17)][3][1]


def _build_level_table() -> dict[int, dict]:
    """Fit the chart columns vs CR, evaluate at CR == level, ÷1.5 the damage, and
    re-express as dice (see the module docstring).  Computed once at import."""
    crs = sorted(_CR_ROWS)
    x = np.array(crs, dtype=float)
    th = np.array([_CR_ROWS[c][0] for c in crs], dtype=float)
    dc = np.array([_CR_ROWS[c][1] for c in crs], dtype=float)
    ps = np.array([_avg(*_CR_ROWS[c][2]) for c in crs], dtype=float)
    ao = np.array([_avg(*_CR_ROWS[c][3]) for c in crs], dtype=float)
    c_th = np.polyfit(x, th, 1)
    c_dc = np.polyfit(x, dc, 1)
    c_ps = np.polyfit(x, ps, 2)
    c_ao = np.polyfit(x, ao, 2)

    rows: dict[int, dict] = {}
    for level in range(1, 21):
        to_hit = int(round(np.polyval(c_th, level)))
        save_dc = int(round(np.polyval(c_dc, level)))
        target_swing = float(np.polyval(c_ps, level)) / DAMAGE_DIVISOR
        target_aoe = float(np.polyval(c_ao, level)) / DAMAGE_DIVISOR
        pb = _pb(level)
        ax, ay = _attack_die(level), _aoe_die(level)
        n = max(1, int(round((target_swing - pb) / ((ax + 1) / 2))))
        m = max(1, int(round(target_aoe / ((ay + 1) / 2))))
        rows[level] = {
            "to_hit": to_hit,
            "save_dc": save_dc,
            "n_attacks": _N_ATTACKS,
            "attack_dice": (n, ax, pb),       # one swing: N dX + PB
            "aoe_dice": (m, ay, 0),           # save-for-half AoE: M dY
        }
    return rows


_LEVEL_ROWS: dict[int, dict] = _build_level_table()


def _row(level: int) -> dict:
    return _LEVEL_ROWS[max(1, min(20, level))]


def baseline_attack_bonus(level: int) -> int:
    """The enemy's attack bonus at character *level*."""
    return _row(level)["to_hit"]


def baseline_save_dc(level: int) -> int:
    """The enemy's save DC at character *level*."""
    return _row(level)["save_dc"]


def baseline_n_attacks(level: int) -> int:
    """How many swings the enemy's multiattack makes at *level* (the chart's routine)."""
    return _row(level)["n_attacks"]


def baseline_attack_dice(level: int) -> tuple[int, int, int]:
    """One swing's damage dice ``(count, sides, flat_PB)`` at *level* — rolled per
    attack, so a natural 20 doubles the dice (the flat PB stays single, RAW crit)."""
    return _row(level)["attack_dice"]


def baseline_aoe_dice(level: int) -> tuple[int, int, int]:
    """The save-for-half AoE damage dice ``(count, sides, 0)`` at *level*."""
    return _row(level)["aoe_dice"]


def baseline_dpr(level: int) -> float:
    """All-hits-land damage-per-round at *level* (n_attacks × per-swing average).  For
    reference / sanity checks; the policy rolls the dice."""
    n, sides, bonus = baseline_attack_dice(level)
    return baseline_n_attacks(level) * _avg(n, sides, bonus)


def level_table() -> dict[int, dict]:
    """The full per-level offensive table (a copy), for inspection / CSV generation."""
    return {lvl: dict(row) for lvl, row in _LEVEL_ROWS.items()}
