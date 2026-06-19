"""
enemy_stats.py — the loader + accessors for the DEFINITIVE per-character-level
monster/enemy stat table (``reference/data/monster_stats_by_level.csv``).

This is the single reference the engine draws enemy numbers from.  One row per
character level (1-20) carries BOTH halves of the enemy profile:

  - DEFENSE: ``ac`` + the six saving-throw modifiers (``str_save`` … ``cha_save``).
  - OFFENSE (decision #12's previously-unrealised half): ``to_hit``, ``save_dc``,
    ``n_attacks``, the per-swing ``attack_dice`` and the save-for-half ``aoe_dice``.

At import the CSV is read into ``_LEVEL_ROWS``; the ``baseline_*`` accessors and
``enemy_base_stats`` serve it.  Nothing here computes — the table is the source of
truth, so it can be eyeballed / hand-edited and the engine simply follows it.

How the table was generated (``regenerate()`` below; run ``python -m
src.builds.enemy_stats`` to rewrite the CSV)
-------------------------------------------------------------------------------------
DEFENSE columns are copied from ``reference/data/monster_ac_and_saves_by_level.csv``
(its provenance; level == CR).  OFFENSE columns come from the user's "Average Monster
Stats by CR" chart (Rothner; ``_CR_ROWS``):
  1. fit each chart column vs CR (linear to-hit/DC, quadratic damage; R²>0.99) and
     evaluate at CR == level (the chart's "Level" column is deliberately ignored);
  2. divide the DAMAGE outputs by ``DAMAGE_DIVISOR`` = 1.5 (a CR-N monster is built
     for FOUR level-N PCs, but here ≤3 friendlies fight and never kill it → its
     un-attrited incoming damage is over-inflated; to-hit / DC are not damage, so
     they are not divided);
  3. re-express each damage average as DICE so enemy CRITS fall out of the engine
     (a natural 20 doubles the dice): per-swing = ``N dX + PB`` (X = the chart's
     matched attack-die size, PB = the level's proficiency bonus as the flat,
     non-crit-doubling part); AoE = ``M dY`` (matched die, no flat — saves don't crit);
  4. apply ``_OVERRIDES`` — a few hand-tuned dice so every damage column rises
     monotonically (the matched-die sizes otherwise dip where they jump).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Runtime: load the definitive table
# ---------------------------------------------------------------------------

_TABLE_PATH = Path(__file__).resolve().parents[2] / "reference" / "data" / "monster_stats_by_level.csv"
_SAVE_KEYS = ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save")
_DICE_RE = re.compile(r"^\s*(\d+)d(\d+)(?:\+(\d+))?\s*$")


def _parse_dice(text: str) -> tuple[int, int, int]:
    """Parse a ``"NdX"`` / ``"NdX+B"`` dice string into ``(count, sides, bonus)``."""
    m = _DICE_RE.match(text)
    if not m:
        raise ValueError(f"bad dice string {text!r}")
    n, sides, bonus = m.group(1), m.group(2), m.group(3)
    return int(n), int(sides), int(bonus or 0)


def _load_table(path: Path) -> dict[int, dict]:
    rows: dict[int, dict] = {}
    with path.open(newline="") as f:
        for r in csv.DictReader(f):
            level = int(r["level"])
            rows[level] = {
                "ac": int(r["ac"]),
                "saves": {k: int(r[k]) for k in _SAVE_KEYS},
                "to_hit": int(r["to_hit"]),
                "save_dc": int(r["save_dc"]),
                "n_attacks": int(r["n_attacks"]),
                "attack_dice": _parse_dice(r["attack_dice"]),
                "aoe_dice": _parse_dice(r["aoe_dice"]),
            }
    return rows


def _row(level: int) -> dict:
    return _LEVEL_ROWS[max(1, min(20, level))]


def baseline_ac(level: int) -> int:
    """The enemy's armor class at character *level*."""
    return _row(level)["ac"]


def baseline_save(level: int, stat: str) -> int:
    """The enemy's saving-throw modifier *stat* (e.g. ``"dex_save"``) at *level*."""
    return _row(level)["saves"][stat]


def baseline_attack_bonus(level: int) -> int:
    """The enemy's attack bonus at character *level*."""
    return _row(level)["to_hit"]


def baseline_save_dc(level: int) -> int:
    """The enemy's save DC at character *level*."""
    return _row(level)["save_dc"]


def baseline_n_attacks(level: int) -> int:
    """How many swings the enemy's multiattack makes at *level*."""
    return _row(level)["n_attacks"]


def baseline_attack_dice(level: int) -> tuple[int, int, int]:
    """One swing's damage dice ``(count, sides, flat_PB)`` at *level* — rolled per
    attack, so a natural 20 doubles the dice (the flat PB stays single, RAW crit)."""
    return _row(level)["attack_dice"]


def baseline_aoe_dice(level: int) -> tuple[int, int, int]:
    """The save-for-half AoE damage dice ``(count, sides, 0)`` at *level*."""
    return _row(level)["aoe_dice"]


def baseline_dpr(level: int) -> float:
    """All-hits-land damage-per-round at *level* (n_attacks × per-swing average)."""
    n, sides, bonus = baseline_attack_dice(level)
    return baseline_n_attacks(level) * (n * (sides + 1) / 2 + bonus)


def enemy_base_stats(level: int) -> dict[str, int | tuple]:
    """An ``Entity.base_stats`` dict for the baseline enemy at *level*: AC + the six
    saves (its defenses) + ``attack_bonus`` and ``enemy_save_dc`` (read by the verbs
    when it attacks / forces saves).  The per-swing / AoE DICE + the attack-vs-save mix
    live in ``BaselineEnemyPolicy``; this is everything the Entity itself needs."""
    row = _row(level)
    stats: dict[str, int | tuple] = {"ac": row["ac"], **row["saves"]}
    stats["attack_bonus"] = row["to_hit"]
    stats["enemy_save_dc"] = row["save_dc"]
    return stats


def level_table() -> dict[int, dict]:
    """The full per-level table (a deep-ish copy), for inspection / CSV generation."""
    return {lvl: {**row, "saves": dict(row["saves"])} for lvl, row in _LEVEL_ROWS.items()}


# ---------------------------------------------------------------------------
# Enemy-policy tuning constants (used by BaselineEnemyPolicy, not stored per level)
# ---------------------------------------------------------------------------

# Default split of save-forcing effects across the SIX save types.  PLACEHOLDER values
# (unsubstantiated — user-approved as a knob to ground later from real 2024 monster
# data), ordered by the user's prevalence ranking: DEX == WIS > STR > CON > INT == CHA.
# Weights are relative (need not sum to 1).
SAVE_TYPE_WEIGHTS: dict[str, int] = {
    "dex_save": 25, "wis_save": 25, "str_save": 15,
    "con_save": 10, "int_save": 5, "cha_save": 5,
}

# Fraction of an enemy's rounds spent forcing a SAVE rather than attacking.
SAVE_ROUND_PROB = 0.35


# ---------------------------------------------------------------------------
# Generation (NOT run at import) — rewrites monster_stats_by_level.csv
# ---------------------------------------------------------------------------

DAMAGE_DIVISOR = 1.5     # 3-vs-4 party size + enemy-never-incapacitated correction
_N_ATTACKS = 2           # the chart's 2-attack multiattack routine
_AC_SAVES_PATH = Path(__file__).resolve().parents[2] / "reference" / "data" / "monster_ac_and_saves_by_level.csv"

# Source chart (Rothner "Average Monster Stats by CR").  Each value:
#   (to_hit, save_dc, attack_dice, aoe_dice)   with dice = (count, sides, flat_bonus)
# attack_dice is ONE swing of the 2-attack routine; aoe_dice is the save-for-half AoE.
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

# Hand-tuned overrides so the DAMAGE curve rises monotonically — the auto-derived
# matched-die table dips where the matched die size jumps (user, 2026-06-19):
#   L1: a single attack (the chart's "(1x)" low-CR routine), not two.
#   L2/L8/L9: per-swing dice picked to sit just above the previous level.
#   L16: per-swing nudged above L15 (9d6+5 ≈ 36.5, between L15's 33 and L17's 37.5).
_OVERRIDES: dict[int, dict] = {
    1:  {"n_attacks": 1},
    2:  {"attack_dice": (1, 8, 2)},
    8:  {"attack_dice": (3, 8, 3)},
    9:  {"attack_dice": (3, 10, 4)},
    16: {"attack_dice": (9, 6, 5)},
}


def _avg(count: int, sides: int, bonus: int) -> float:
    return count * (sides + 1) / 2 + bonus


def _pb(level: int) -> int:
    return 2 + (level - 1) // 4


def regenerate(write: bool = True) -> dict[int, dict]:
    """Derive the per-level table from ``_CR_ROWS`` + the AC/saves CSV (see the module
    docstring) and, if *write*, rewrite ``monster_stats_by_level.csv``.  Returns the
    rows in the same structure ``_load_table`` produces, so a test can assert the
    committed CSV is in sync with this generator.  numpy is imported lazily here so the
    runtime import path stays dependency-light."""
    import numpy as np

    crs = sorted(_CR_ROWS)
    x = np.array(crs, dtype=float)
    c_th = np.polyfit(x, [_CR_ROWS[c][0] for c in crs], 1)
    c_dc = np.polyfit(x, [_CR_ROWS[c][1] for c in crs], 1)
    c_ps = np.polyfit(x, [_avg(*_CR_ROWS[c][2]) for c in crs], 2)
    c_ao = np.polyfit(x, [_avg(*_CR_ROWS[c][3]) for c in crs], 2)

    ac_saves: dict[int, dict] = {}
    with _AC_SAVES_PATH.open(newline="") as f:
        for r in csv.DictReader(f):
            ac_saves[int(r["level"])] = r

    rows: dict[int, dict] = {}
    for level in range(1, 21):
        pb = _pb(level)
        ax, ay = _CR_ROWS[min(level, 17)][2][1], _CR_ROWS[min(level, 17)][3][1]
        target_swing = float(np.polyval(c_ps, level)) / DAMAGE_DIVISOR
        target_aoe = float(np.polyval(c_ao, level)) / DAMAGE_DIVISOR
        n = max(1, int(round((target_swing - pb) / ((ax + 1) / 2))))
        m = max(1, int(round(target_aoe / ((ay + 1) / 2))))
        row = {
            "ac": int(ac_saves[level]["ac"]),
            "saves": {k: int(ac_saves[level][k.replace("_save", ".save.mod")]) for k in _SAVE_KEYS},
            "to_hit": int(round(np.polyval(c_th, level))),
            "save_dc": int(round(np.polyval(c_dc, level))),
            "n_attacks": _N_ATTACKS,
            "attack_dice": (n, ax, pb),
            "aoe_dice": (m, ay, 0),
        }
        row.update(_OVERRIDES.get(level, {}))    # hand-tuned monotonicity
        rows[level] = row

    if write:
        _write_csv(rows)
    return rows


def _dice_str(dice: tuple[int, int, int]) -> str:
    n, sides, bonus = dice
    return f"{n}d{sides}+{bonus}" if bonus else f"{n}d{sides}"


def _write_csv(rows: dict[int, dict]) -> None:
    cols = (["level", "ac", *_SAVE_KEYS, "to_hit", "save_dc", "n_attacks",
             "attack_dice", "aoe_dice", "per_swing_avg", "dmg_per_round", "aoe_avg"])
    with _TABLE_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for level in range(1, 21):
            r = rows[level]
            ps = _avg(*r["attack_dice"])
            w.writerow([
                level, r["ac"], *[r["saves"][k] for k in _SAVE_KEYS],
                r["to_hit"], r["save_dc"], r["n_attacks"],
                _dice_str(r["attack_dice"]), _dice_str(r["aoe_dice"]),
                round(ps, 1), round(r["n_attacks"] * ps, 1), round(_avg(*r["aoe_dice"]), 1),
            ])


# Load the definitive table at import.  Self-bootstraps the first time ever (CSV
# absent) by generating it; once committed, the CSV exists so numpy is never imported
# on the runtime path.
try:
    _LEVEL_ROWS: dict[int, dict] = _load_table(_TABLE_PATH)
except FileNotFoundError:
    regenerate(write=True)
    _LEVEL_ROWS = _load_table(_TABLE_PATH)


if __name__ == "__main__":
    regenerate(write=True)
    print(f"wrote {_TABLE_PATH}")
