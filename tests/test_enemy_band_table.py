"""test_enemy_band_table.py — the frozen per-band table (design/enemy_model.md §8)
and the action-level re-tabulation (§4b).

Validation framing (validate-mechanism-not-build-value): we assert the MECHANISM — the
committed CSV is in sync with the live aggregator, the action budget collapses multiattack
to one slot and corrects save_round_prob to the per-action basis, and the band-grounded
policy knobs read the frozen table. We do NOT assert that any specific band number is
"right" — that's the census's job, frozen upstream.
"""

import pytest

from src.builds import monster_profile as mp
from src.builds.enemy_stats import (
    band_for_level,
    band_save_round_prob,
    band_save_weights,
)


# ---------------------------------------------------------------------------
# Frozen table ↔ aggregator in-sync (mirror of enemy_stats' regenerate sync test)
# ---------------------------------------------------------------------------

def test_band_table_in_sync_with_aggregator():
    """The committed monster_profile_by_band.csv matches the live aggregator output.
    If this fails, the census changed underneath the freeze — run:
        python -m src.builds.monster_profile --write
    and re-commit the CSV (exactly like enemy_stats.regenerate)."""
    committed = mp.load_band_table()
    live = {r["band"]: r for r in mp.band_table_rows()}
    assert set(committed) == set(live)
    for band in live:
        for col in mp.band_table_columns():
            cv, lv = committed[band][col], live[band][col]
            if col == "band":
                assert cv == lv
            else:
                assert cv == pytest.approx(lv), f"{band}.{col}: {cv} != {lv}"


def test_band_table_has_all_four_bands_and_full_schema():
    table = mp.load_band_table()
    assert set(table) == set(mp.BANDS)
    # every column present in every row
    for band, row in table.items():
        assert set(row) == set(mp.band_table_columns())


# ---------------------------------------------------------------------------
# Action-level re-tabulation (§4b): multiattack collapses, save_round_prob corrected
# ---------------------------------------------------------------------------

def test_action_budget_shares_sum_to_100():
    for band, d in mp.action_budget(harmonized=True).items():
        total = d["share_attack"] + d["share_save_dmg"] + d["share_pure_control"]
        assert total == pytest.approx(100.0, abs=0.2), f"{band}: {total}"


def test_action_budget_collapses_multiattack_to_one_slot():
    """The whole point of the action-level re-tab: a monster's multiattack counts as ONE
    attack action, so attack-per-monster sits near 1 (NOT the 1.3–2.7 swing-instances
    that resolution_three_way reports)."""
    budget = mp.action_budget(harmonized=True)
    for band, d in budget.items():
        assert d["attack_per_mon"] <= 1.2, f"{band}: {d['attack_per_mon']}"
    # contrast: the instance-level three-way reports far more "attacks" per monster
    three = mp.resolution_three_way(harmonized=True)
    assert three["17+"]["atk_dmg_per_mon"] > budget["17+"]["attack_per_mon"] * 2


def test_save_dmg_action_share_rises_with_cr():
    """save_dmg_action_share (the corrected save_round_prob) climbs monotonically with CR
    — the empirical shape the §4b correction preserves."""
    d = mp.action_budget(harmonized=True)
    shares = [d[b]["share_save_dmg"] for b in mp.BANDS]
    assert shares == sorted(shares)
    assert shares[0] < shares[-1]


def test_action_basis_differs_from_instance_basis():
    """The correction is real: the per-ACTION save share is NOT the per-INSTANCE save
    share the §4 footnote flagged (multiattack counted once vs N times shifts it)."""
    inst = mp.load_band_table()
    act = mp.action_budget(harmonized=True)
    # at low CR the action basis is much LOWER (a 0-4 monster almost always just swings)
    assert act["0-4"]["share_save_dmg"] < inst["0-4"]["save_round_prob_instance"]


# ---------------------------------------------------------------------------
# Band-grounded policy knobs read the frozen table (§4 correction)
# ---------------------------------------------------------------------------

def test_band_for_level_step_function():
    assert band_for_level(1) == "0-4"
    assert band_for_level(4) == "0-4"
    assert band_for_level(5) == "5-10"
    assert band_for_level(10) == "5-10"
    assert band_for_level(11) == "11-16"
    assert band_for_level(16) == "11-16"
    assert band_for_level(17) == "17+"
    assert band_for_level(20) == "17+"


def test_band_save_round_prob_matches_frozen_table():
    table = mp.load_band_table()
    for lvl, band in ((3, "0-4"), (8, "5-10"), (13, "11-16"), (18, "17+")):
        assert band_save_round_prob(lvl) == pytest.approx(
            table[band]["save_dmg_action_share"] / 100.0)


def test_band_save_weights_are_con_dex_dominant_not_wis():
    """The §4 correction: damaging-save weights are CON/DEX-dominant; WIS is small or
    absent (the mental-save mass is the control channel's job, §6) — NOT the placeholder
    DEX==WIS ranking."""
    for lvl in (8, 13, 18):
        w = band_save_weights(lvl)
        top2 = sorted(w, key=w.get, reverse=True)[:2]
        assert set(top2) <= {"dex_save", "con_save"}
        # WIS is never a top-2 damaging save in any band
        assert "wis_save" not in top2
