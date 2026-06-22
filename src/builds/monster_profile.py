"""
monster_profile.py — aggregate the empirical 2024-Monster-Manual census tags into
per-CR-band distribution tables (the enemy-profile arc; see ``design/enemy_profile.md``).

Two source tables under ``reference/data/`` (the census output):
  - ``monster_profile_raw.csv``      one row per damaging action component (offense).
  - ``monster_profile_monsters.csv`` one row per monster (defense: res/imm/vuln + cond imm).

This module is a PURE raw->band tabulator (analysis). It does NOT touch the engine or
the enemy policy; wiring the distributions into ``BaselineEnemyPolicy`` (grounding the
``SAVE_TYPE_WEIGHTS`` / ``SAVE_ROUND_PROB`` placeholders in ``enemy_stats.py``) is the
NEXT arc. Run ``python -m src.builds.monster_profile`` to print the tables for whatever
bands the CSVs currently cover (the census runs across sessions; partial bands still
tabulate).

All offense distributions are INSTANCE-WEIGHTED by ``instances_per_round`` (the v1
weighting unit; see the design note). A multi-type action contributes its full instance
weight to EACH of its damage types. Defense prevalences are per-MONSTER (unweighted).
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

_DATA = Path(__file__).resolve().parents[2] / "reference" / "data"
_RAW = _DATA / "monster_profile_raw.csv"
_MON = _DATA / "monster_profile_monsters.csv"

BANDS = ("0-4", "5-10", "11-16", "17+")
PHYSICAL = {"bludgeoning", "piercing", "slashing"}
DAMAGE_TYPES = (
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
)
SAVE_ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


def _split(field: str) -> list[str]:
    return [x.strip() for x in (field or "").split(";") if x.strip()]


def _load_rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load() -> tuple[list[dict], list[dict]]:
    """Return ``(action_rows, monster_rows)`` from the two census CSVs."""
    return _load_rows(_RAW), _load_rows(_MON)


def _pct(part: float, whole: float) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


def band_profile(band: str, actions: list[dict], monsters: list[dict]) -> dict:
    """Compute the full distribution profile for one CR band."""
    acts = [r for r in actions if r["cr_band"] == band]
    mons = [r for r in monsters if r["cr_band"] == band]

    def w(r) -> float:
        try:
            return float(r["instances_per_round"] or 0)
        except ValueError:
            return 0.0

    total_w = sum(w(r) for r in acts)

    # 1. damage-type mix (instance-weighted; multi-type splits to each type)
    dtype_w: dict[str, float] = defaultdict(float)
    phys_w = elem_w = 0.0
    for r in acts:
        types = _split(r["damage_types"])
        for t in types:
            dtype_w[t] += w(r)
            if t in PHYSICAL:
                phys_w += w(r)
            else:
                elem_w += w(r)
    type_total = phys_w + elem_w

    # 2. resolution mix
    res_w: dict[str, float] = defaultdict(float)
    for r in acts:
        res_w[r["resolution"]] += w(r)

    # 3. save-type mix (among save & both rows that name an ability)
    save_w: dict[str, float] = defaultdict(float)
    for r in acts:
        if r["resolution"] in ("save", "both") and r["save_ability"]:
            save_w[r["save_ability"].upper()] += w(r)
    save_total = sum(save_w.values())

    # 4. reach mix
    reach_w: dict[str, float] = defaultdict(float)
    for r in acts:
        reach_w[r["reach"]] += w(r)

    # 5. AoE share
    aoe_w = sum(w(r) for r in acts if (r["aoe"] or "").lower() == "y")

    # 6. rider frequencies (count of distinct conditions across actions, weighted)
    rider_w: dict[str, float] = defaultdict(float)
    for r in acts:
        for cond in _split(r["riders"]):
            rider_w[cond] += w(r)

    # 7. legendary / lair cadence (per monster)
    n_mon = len(mons)
    n_leg = sum(1 for m in mons if (m["has_legendary"] or "").lower() == "y")
    n_lair = sum(1 for m in mons if (m["has_lair"] or "").lower() == "y")
    leg_counts = [int(m["legendary_action_count"] or 0) for m in mons if (m["has_legendary"] or "").lower() == "y"]
    avg_leg = round(sum(leg_counts) / len(leg_counts), 1) if leg_counts else 0.0

    # 8. damage res/imm/vuln prevalence (per monster, % of band)
    res_prev: dict[str, int] = defaultdict(int)
    imm_prev: dict[str, int] = defaultdict(int)
    vul_prev: dict[str, int] = defaultdict(int)
    for m in mons:
        for t in _split(m["damage_resistances"]):
            res_prev[t] += 1
        for t in _split(m["damage_immunities"]):
            imm_prev[t] += 1
        for t in _split(m["damage_vulnerabilities"]):
            vul_prev[t] += 1

    # 9. condition-immunity prevalence (per monster, % of band)
    cond_prev: dict[str, int] = defaultdict(int)
    for m in mons:
        for c in _split(m["condition_immunities"]):
            cond_prev[c] += 1

    return {
        "band": band,
        "n_monsters": n_mon,
        "n_actions": len(acts),
        "total_instances": round(total_w, 1),
        "phys_vs_elem": {
            "physical": _pct(phys_w, type_total),
            "elemental_special": _pct(elem_w, type_total),
        },
        "damage_type_mix": {t: _pct(dtype_w[t], type_total) for t in DAMAGE_TYPES if dtype_w[t]},
        "resolution_mix": {k: _pct(v, total_w) for k, v in sorted(res_w.items())},
        "save_type_mix": {k: _pct(save_w.get(k, 0), save_total) for k in SAVE_ABILITIES if save_w.get(k)},
        "reach_mix": {k: _pct(v, total_w) for k, v in sorted(reach_w.items())},
        "aoe_share": _pct(aoe_w, total_w),
        "rider_freq": {k: _pct(v, total_w) for k, v in sorted(rider_w.items(), key=lambda kv: -kv[1])},
        "legendary": {
            "pct_with_legendary": _pct(n_leg, n_mon),
            "avg_legendary_actions": avg_leg,
            "pct_with_lair": _pct(n_lair, n_mon),
        },
        "resistance_prevalence": {k: _pct(v, n_mon) for k, v in sorted(res_prev.items(), key=lambda kv: -kv[1])},
        "immunity_prevalence": {k: _pct(v, n_mon) for k, v in sorted(imm_prev.items(), key=lambda kv: -kv[1])},
        "vulnerability_prevalence": {k: _pct(v, n_mon) for k, v in sorted(vul_prev.items(), key=lambda kv: -kv[1])},
        "condition_immunity_prevalence": {k: _pct(v, n_mon) for k, v in sorted(cond_prev.items(), key=lambda kv: -kv[1])},
    }


def all_profiles() -> dict[str, dict]:
    actions, monsters = load()
    present = [b for b in BANDS if any(m["cr_band"] == b for m in monsters)]
    return {b: band_profile(b, actions, monsters) for b in present}


def _fmt_dist(d: dict) -> str:
    return ", ".join(f"{k} {v}%" for k, v in d.items()) or "(none)"


def print_profiles() -> None:
    for band, p in all_profiles().items():
        print(f"\n{'='*72}\nCR BAND {band}  --  {p['n_monsters']} monsters, "
              f"{p['n_actions']} damaging actions, {p['total_instances']} instances/round (weighted)\n{'='*72}")
        print(f"  Physical vs elemental/special : {_fmt_dist(p['phys_vs_elem'])}")
        print(f"  Damage-type mix               : {_fmt_dist(p['damage_type_mix'])}")
        print(f"  Resolution (atk/save/both/auto): {_fmt_dist(p['resolution_mix'])}")
        print(f"  Save-type (of save-forcing)   : {_fmt_dist(p['save_type_mix'])}")
        print(f"  Reach                         : {_fmt_dist(p['reach_mix'])}")
        print(f"  AoE share of instances        : {p['aoe_share']}%")
        print(f"  Rider conditions imposed      : {_fmt_dist(p['rider_freq'])}")
        leg = p["legendary"]
        print(f"  Legendary / lair cadence      : {leg['pct_with_legendary']}% legendary "
              f"(avg {leg['avg_legendary_actions']} actions), {leg['pct_with_lair']}% have lairs")
        print(f"  Damage RESISTANCE prevalence  : {_fmt_dist(p['resistance_prevalence'])}")
        print(f"  Damage IMMUNITY prevalence    : {_fmt_dist(p['immunity_prevalence'])}")
        print(f"  Damage VULNERABILITY prevalence: {_fmt_dist(p['vulnerability_prevalence'])}")
        print(f"  CONDITION-IMMUNITY prevalence  : {_fmt_dist(p['condition_immunity_prevalence'])}")


if __name__ == "__main__":
    print_profiles()
