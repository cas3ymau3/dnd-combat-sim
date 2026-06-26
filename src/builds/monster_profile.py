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
_CONTROL = _DATA / "monster_profile_control.csv"

BANDS = ("0-4", "5-10", "11-16", "17+")
PHYSICAL = {"bludgeoning", "piercing", "slashing"}
DAMAGE_TYPES = (
    "acid", "bludgeoning", "cold", "fire", "force", "lightning", "necrotic",
    "piercing", "poison", "psychic", "radiant", "slashing", "thunder",
)
SAVE_ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")
SIZES = ("Tiny", "Small", "Medium", "Large", "Huge", "Gargantuan")
# The tracked condition vocabulary (the 2024 status set the censuses tag, used both as
# riders and as condition immunities).  Closed list → fixed columns in the frozen table.
CONDITIONS = (
    "blinded", "charmed", "deafened", "exhaustion", "frightened", "grappled",
    "incapacitated", "paralyzed", "petrified", "poisoned", "prone", "restrained",
    "stunned", "unconscious",
)
# Map the census's uppercase save-ability tag to the engine's save_stat key.
_SAVE_STAT = {ab: f"{ab.lower()}_save" for ab in SAVE_ABILITIES}

# The frozen band table (the §8 enemy-model INPUT the policy reads at runtime).
_BAND_TABLE_PATH = _DATA / "monster_profile_by_band.csv"


def _split(field: str) -> list[str]:
    return [x.strip() for x in (field or "").split(";") if x.strip()]


def _wnum(s: str) -> float:
    try:
        return float(s or 0)
    except ValueError:
        return 0.0


def cadence_factor(recharge: str) -> float:
    """The control census's cadence discount (at-will 1.0 / recharge 0.5 / limited
    0.25), exposed so the DAMAGING census (which counts every use at full) can be
    re-weighted onto the same basis. ``recharge`` is the raw CSV value: ``at-will``,
    a recharge range (``5-6``/``4-6``/``6``/``recharge``), or ``N/day``."""
    r = (recharge or "").strip().lower()
    if r in ("", "at-will"):
        return 1.0
    if "/day" in r:
        return 0.25
    return 0.5  # any recharge band


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

    # 10. size distribution (per monster, % of band) — preserved raw, NOT interpreted.
    # Strongly CR-dependent; relevant later to size-gated mechanics (grapple/shove/forced
    # movement). The per-monster `size` source stays in monster_profile_monsters.csv.
    size_counts: dict[str, int] = defaultdict(int)
    for m in mons:
        size_counts[m["size"]] += 1

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
        "size_distribution": {s: _pct(size_counts[s], n_mon) for s in SIZES if size_counts[s]},
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
        print(f"  SIZE distribution             : {_fmt_dist(p['size_distribution'])}")


def resolution_three_way(harmonized: bool = False) -> dict[str, dict]:
    """Per-band three-prong enemy-action mix — **attack-for-damage / save-for-damage /
    control-save** — combining the damaging census (``resolution`` field) with the
    control census (``monster_profile_control.csv``). Reported both as expected
    instances/round for the average band-monster and as shares.

    Weighting bases (the control census is ALREADY cadence-discounted at source —
    at-will 1.0 / recharge 0.5 / limited 0.25 — so it is used as stored in BOTH modes):
      - ``harmonized=False`` (raw): damaging rows at full weight. This MISMATCHES the
        control side (the damaging census never discounts recharge/limited uses), so
        the damage prongs are mildly inflated and the control share reads as a floor.
      - ``harmonized=True``: apply ``cadence_factor`` to the damaging rows too, putting
        both censuses on the same cadence-discounted basis. This is the apples-to-apples
        table.

    CAVEAT — the prongs are NOT disjoint (deferred to the enemy-behavior formalization /
    metrics-design + wiring discussion): a damage-coupled control ability (Mind Blast =
    save-for-damage AND stun) is counted in BOTH the save-for-damage and control prongs
    (the control CSV's ``also_damages`` flag marks these). See design/enemy_model.md.
    """
    actions, monsters = load()
    control = _load_rows(_CONTROL)
    nmon = {b: sum(1 for m in monsters if m["cr_band"] == b) for b in BANDS}
    out: dict[str, dict] = {}
    for b in BANDS:
        if not nmon[b]:
            continue
        atk = save = 0.0
        for r in actions:
            if r["cr_band"] != b:
                continue
            w = _wnum(r["instances_per_round"]) * (cadence_factor(r["recharge"]) if harmonized else 1.0)
            if r["resolution"] == "save":
                save += w
            else:  # attack / both / auto — the non-pure-save (has-attack-or-auto) prong
                atk += w
        ctl = sum(_wnum(r["instances_per_round"]) for r in control if r["cr_band"] == b)
        tot = atk + save + ctl
        out[b] = {
            "atk_dmg_per_mon": round(atk / nmon[b], 2),
            "save_dmg_per_mon": round(save / nmon[b], 2),
            "control_per_mon": round(ctl / nmon[b], 2),
            "share_atk_dmg": _pct(atk, tot),
            "share_save_dmg": _pct(save, tot),
            "share_control": _pct(ctl, tot),
        }
    return out


def action_budget(harmonized: bool = True) -> dict[str, dict]:
    """Per-band ACTION-LEVEL re-tabulation (design/enemy_model.md §4b) — the ternary
    per-turn action budget the enemy decision tree draws from: **attack / save-for-damage
    / pure-control**, plus the **bundled-control** rider rate.

    The crucial difference from ``resolution_three_way`` (which counts damage INSTANCES,
    so a 3-swing multiattack counts as 3): this counts action-economy SLOTS once — a
    monster's whole multiattack collapses to ONE attack action, cadence-weighting the
    alternatives (breath / limited spells discount). This yields the true per-turn mix
    and, as a side effect, **corrects ``save_round_prob`` from the instance basis to the
    per-action basis** (§4b): the runtime treats a round as one action choice, not N
    swings, so the save-for-damage SHARE belongs on the action basis.

    Sourcing rules (§4b implementation notes):
      - group a monster's ``multiattack-swing`` rows into ONE attack action (weight =
        the cadence of the multiattack, at-will → 1.0);
      - keep only the PRIMARY action slot — ``legendary`` is the separate cadence-bump
        knob (§10), ``bonus`` / ``trait`` / ``reaction`` are out of the per-turn budget;
      - each ``action``-section damaging row is a separate alternative action, weight =
        ``cadence_factor(recharge)`` (breath 0.5, limited 0.25); routed by ``resolution``
        — ``save`` → save-for-damage prong, else (attack / both / auto) → attack prong;
      - pure control (control census, ``also_damages == n``) → its stored
        cadence-discounted ``instances_per_round`` → the third budget prong; it
        DISPLACES attack (so ``save_dmg_action_share`` is invariant to control on/off);
      - bundled control (``also_damages == y``) is NOT in the budget — it rides as a
        second save on save-for-damage rounds (§4b), reported separately as a per-mon
        rate.

    ``harmonized`` cadence-discounts the damaging action rows; True (default) is
    apples-to-apples with the already-discounted control census. The collapsed
    multiattack is at-will either way, so harmonization mainly discounts breath/spells.
    """
    actions, monsters = load()
    control = _load_rows(_CONTROL)
    nmon = {b: sum(1 for m in monsters if m["cr_band"] == b) for b in BANDS}

    # Group damaging action rows by (band, monster) so a multiattack collapses to one.
    by_mon: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in actions:
        by_mon[(r["cr_band"], r["monster"])].append(r)

    out: dict[str, dict] = {}
    for b in BANDS:
        if not nmon[b]:
            continue
        attack_w = save_w = 0.0
        for (band, _mon), rows in by_mon.items():
            if band != b:
                continue
            ma = [r for r in rows if r["section"] == "multiattack-swing"]
            if ma:
                # one attack action; multiattacks are at-will → cadence 1.0 (use the
                # strongest cadence among them if a row were ever discounted).
                attack_w += max(cadence_factor(r["recharge"]) for r in ma)
            for r in rows:
                if r["section"] != "action":
                    continue  # primary action slot only (§4b (b))
                w = cadence_factor(r["recharge"]) if harmonized else 1.0
                if r["resolution"] == "save":
                    save_w += w
                else:  # attack / both / auto — the non-pure-save prong
                    attack_w += w
        pure_w = sum(_wnum(r["instances_per_round"]) for r in control
                     if r["cr_band"] == b and r["also_damages"] == "n")
        bundled_w = sum(_wnum(r["instances_per_round"]) for r in control
                        if r["cr_band"] == b and r["also_damages"] == "y")
        tot = attack_w + save_w + pure_w
        out[b] = {
            "attack_per_mon": round(attack_w / nmon[b], 3),
            "save_dmg_per_mon": round(save_w / nmon[b], 3),
            "pure_control_per_mon": round(pure_w / nmon[b], 3),
            "bundled_control_per_mon": round(bundled_w / nmon[b], 3),
            "share_attack": _pct(attack_w, tot),
            "share_save_dmg": _pct(save_w, tot),       # the corrected save_round_prob
            "share_pure_control": _pct(pure_w, tot),
        }
    return out


def print_action_budget() -> None:
    print(f"\n{'-'*72}\nACTION-LEVEL BUDGET (multiattack collapsed to 1 slot — §4b; "
          f"corrects save_round_prob)\n{'-'*72}")
    print(f"  {'band':<7}{'atk':>8}{'save-dmg':>10}{'pure-ctl':>10}{'bundled':>9}   "
          f"share (atk / save-dmg / pure-ctl)")
    for b, d in action_budget(harmonized=True).items():
        print(f"  {b:<7}{d['attack_per_mon']:>8}{d['save_dmg_per_mon']:>10}"
              f"{d['pure_control_per_mon']:>10}{d['bundled_control_per_mon']:>9}   "
              f"{d['share_attack']:>4.0f}% / {d['share_save_dmg']:>4.0f}% / "
              f"{d['share_pure_control']:>4.0f}%")


# ---------------------------------------------------------------------------
# Frozen per-band table (design/enemy_model.md §8) — the policy's runtime INPUT
# ---------------------------------------------------------------------------
#
# One row per band carrying everything the enemy policy reads: the action-budget
# shares (incl. the corrected save_round_prob), the six damaging-save weights, the
# damage-type mix, reach/AoE shares, the per-type res/imm/vuln prevalences (→ §5
# mult(t)), the per-condition immunity prevalences (→ rider pricing), and legendary
# cadence.  Frozen to CSV (not computed at import) so it is eyeball-able / hand-editable,
# matching enemy_stats.py's "table is the source of truth" philosophy, and kept
# in-sync-tested against the live aggregator (test_enemy_band_table.py), exactly like
# enemy_stats.regenerate() has a sync test.  Columns are built programmatically from the
# closed vocabularies so the writer and loader stay symmetric.


def band_table_columns() -> list[str]:
    """The fixed column order of the frozen band table."""
    cols = [
        "band", "n_monsters", "n_actions", "total_instances",
        "phys_share", "elem_share",
        # action-level budget (§4b); save_dmg_action_share IS the corrected save_round_prob
        "attack_action_share", "save_dmg_action_share", "pure_control_action_share",
        "bundled_control_per_mon",
        "save_round_prob_instance",   # the §4-footnote instance share, kept for eyeballing
        "aoe_share",
        "pct_with_legendary", "avg_legendary_actions", "pct_with_lair",
    ]
    cols += [f"savew_{ab}" for ab in SAVE_ABILITIES]
    cols += [f"dmix_{t}" for t in DAMAGE_TYPES]
    cols += [f"reach_{r}" for r in ("melee", "ranged", "both")]
    cols += [f"res_{t}" for t in DAMAGE_TYPES]
    cols += [f"imm_{t}" for t in DAMAGE_TYPES]
    cols += [f"vul_{t}" for t in DAMAGE_TYPES]
    cols += [f"cimm_{c}" for c in CONDITIONS]
    return cols


def _band_flat(profile: dict, budget: dict) -> dict:
    """Flatten one band's nested ``band_profile`` + ``action_budget`` into the fixed
    column schema (missing dict keys → 0.0)."""
    p, b = profile, budget
    row: dict[str, float | str] = {
        "band": p["band"],
        "n_monsters": p["n_monsters"],
        "n_actions": p["n_actions"],
        "total_instances": p["total_instances"],
        "phys_share": p["phys_vs_elem"]["physical"],
        "elem_share": p["phys_vs_elem"]["elemental_special"],
        "attack_action_share": b["share_attack"],
        "save_dmg_action_share": b["share_save_dmg"],
        "pure_control_action_share": b["share_pure_control"],
        "bundled_control_per_mon": b["bundled_control_per_mon"],
        "save_round_prob_instance": p["resolution_mix"].get("save", 0.0),
        "aoe_share": p["aoe_share"],
        "pct_with_legendary": p["legendary"]["pct_with_legendary"],
        "avg_legendary_actions": p["legendary"]["avg_legendary_actions"],
        "pct_with_lair": p["legendary"]["pct_with_lair"],
    }
    for ab in SAVE_ABILITIES:
        row[f"savew_{ab}"] = p["save_type_mix"].get(ab, 0.0)
    for t in DAMAGE_TYPES:
        row[f"dmix_{t}"] = p["damage_type_mix"].get(t, 0.0)
    for r in ("melee", "ranged", "both"):
        row[f"reach_{r}"] = p["reach_mix"].get(r, 0.0)
    for t in DAMAGE_TYPES:
        row[f"res_{t}"] = p["resistance_prevalence"].get(t, 0.0)
    for t in DAMAGE_TYPES:
        row[f"imm_{t}"] = p["immunity_prevalence"].get(t, 0.0)
    for t in DAMAGE_TYPES:
        row[f"vul_{t}"] = p["vulnerability_prevalence"].get(t, 0.0)
    for c in CONDITIONS:
        row[f"cimm_{c}"] = p["condition_immunity_prevalence"].get(c, 0.0)
    return row


def band_table_rows() -> list[dict]:
    """The frozen-table rows computed LIVE from the censuses (one per present band).
    The writer freezes these; the in-sync test compares the committed CSV to these."""
    profiles = all_profiles()
    budgets = action_budget(harmonized=True)
    return [_band_flat(profiles[b], budgets[b]) for b in BANDS
            if b in profiles and b in budgets]


def _write_band_csv(rows: list[dict]) -> None:
    cols = band_table_columns()
    with _BAND_TABLE_PATH.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, 0.0) for c in cols})


def regenerate_band_table(write: bool = True) -> list[dict]:
    """Recompute the frozen per-band table from the censuses and, if *write*, rewrite
    ``monster_profile_by_band.csv``.  The freeze entry point (mirror of
    ``enemy_stats.regenerate``); run ``python -m src.builds.monster_profile --write``."""
    rows = band_table_rows()
    if write:
        _write_band_csv(rows)
    return rows


def load_band_table() -> dict[str, dict]:
    """Load the frozen band table → ``{band: {column: value}}`` (floats parsed).  The
    runtime read path for the enemy policy (it never re-aggregates the raw census)."""
    out: dict[str, dict] = {}
    cols = set(band_table_columns())
    with _BAND_TABLE_PATH.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            row: dict[str, float | str] = {}
            for k, v in r.items():
                if k == "band":
                    row[k] = v
                elif k in cols:
                    row[k] = float(v)
            out[r["band"]] = row
    return out


def print_three_way() -> None:
    for label, harm in (("RAW (damaging census NOT cadence-discounted — control share is a floor)", False),
                        ("HARMONIZED (both censuses cadence-discounted — apples-to-apples)", True)):
        print(f"\n{'-'*72}\nTHREE-PRONG ACTION MIX — {label}\n{'-'*72}")
        print(f"  {'band':<7}{'atk-dmg/rd':>11}{'save-dmg/rd':>12}{'ctrl/rd':>9}   share (atk / save-dmg / control)")
        for b, d in resolution_three_way(harmonized=harm).items():
            print(f"  {b:<7}{d['atk_dmg_per_mon']:>11}{d['save_dmg_per_mon']:>12}{d['control_per_mon']:>9}   "
                  f"{d['share_atk_dmg']:>4.0f}% / {d['share_save_dmg']:>4.0f}% / {d['share_control']:>4.0f}%")


if __name__ == "__main__":
    import sys
    if "--write" in sys.argv:
        regenerate_band_table(write=True)
        print(f"wrote {_BAND_TABLE_PATH}")
    else:
        print_profiles()
        print_three_way()
        print_action_budget()
