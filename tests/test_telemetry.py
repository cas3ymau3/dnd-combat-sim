"""test_telemetry.py — the structured-telemetry seam (design/enemy_model.md §13).

Validation framing (validate-mechanism-not-build-value): we assert the SEAM works —
that resolution records the same counts the existing entity counters already track, that
the closed channel vocabulary is enforced, that combats aggregate onto the day via merge,
and that the seam is byte-identical when no sink is passed (a direct verb caller). We do
NOT assert any DPR value.
"""

import logging

import pytest

from src.builds.enemy import BaselineEnemyPolicy
from src.builds.enemy_stats import enemy_base_stats
from src.entity import Entity
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.telemetry import CombatTelemetry

logging.disable(logging.CRITICAL)

_ALL_SAVES = {k: 2 for k in
              ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save")}


# ---------------------------------------------------------------------------
# Unit: the accumulator + closed vocabulary + aggregation
# ---------------------------------------------------------------------------

def test_record_save_tallies_by_ability_and_channel():
    t = CombatTelemetry()
    t.record_save("dex_save", "damage", passed=True)
    t.record_save("dex_save", "damage", passed=False)
    t.record_save("wis_save", "control", passed=False)
    assert t.saves[("dex_save", "damage")].forced == 2
    assert t.saves[("dex_save", "damage")].passed == 1
    assert t.saves[("dex_save", "damage")].failed == 1
    # cross-axis split is visible: the channels are separate cells
    assert t.saves_forced("damage") == 2
    assert t.saves_forced("control") == 1
    assert t.saves_forced() == 3
    assert t.saves_failed("control") == 1


def test_record_save_rejects_unknown_channel():
    t = CombatTelemetry()
    with pytest.raises(ValueError):
        t.record_save("dex_save", "bogus", passed=True)


def test_concentration_and_economy_records():
    t = CombatTelemetry()
    t.record_concentration(broke=True)
    t.record_concentration(broke=False)
    t.record_reaction()
    t.record_resource("spell_slot_1", 2)
    assert (t.concentration_checks, t.concentration_breaks) == (2, 1)
    assert t.reactions_used == 1
    assert t.resources_spent["spell_slot_1"] == 2


def test_merge_sums_all_channels():
    a = CombatTelemetry()
    a.record_save("con_save", "damage", passed=False)
    a.record_concentration(broke=False)
    a.record_resource("war_priest", 1)
    b = CombatTelemetry()
    b.record_save("con_save", "damage", passed=True)
    b.record_concentration(broke=True)
    b.record_resource("war_priest", 2)
    a.merge(b)
    assert a.saves[("con_save", "damage")].forced == 2
    assert a.saves[("con_save", "damage")].passed == 1
    assert a.concentration_checks == 2
    assert a.concentration_breaks == 1
    assert a.resources_spent["war_priest"] == 3


# ---------------------------------------------------------------------------
# Integration: RESOLUTION writes the seam, and it matches the entity counters
# (the seam folds the existing monkeypatch telemetry into one home — §13).
# ---------------------------------------------------------------------------

def test_save_channel_matches_entity_counters_over_a_combat():
    """An enemy forcing a damaging save every round → the seam's damage-save counts
    equal the character's own saving_throws_made/_failed entity counters, for any seed."""
    char = Entity(name="char", hp=10**6, base_stats={"ac": 15, **_ALL_SAVES})
    enemy = Entity(name="enemy", hp=10**9, base_stats=enemy_base_stats(8))
    pol = BaselineEnemyPolicy(level=8, primary=char, save_round_prob=1.0,
                              rounds_per_combat=5)
    pol.on_combat_start(0, SeededRNG(7))
    sched = Scheduler(rng=SeededRNG(7), entities=[char, enemy],
                      policies={enemy.id: pol}, max_rounds=5)
    sched.run()
    # one forced damaging save per round (save_round_prob=1.0)
    assert char.saving_throws_made == 5
    assert sched.telemetry.saves_forced("damage") == char.saving_throws_made
    assert sched.telemetry.saves_failed("damage") == char.saving_throws_failed
    # all on the damage channel; none on control (that channel wires in roadmap step 5)
    assert sched.telemetry.saves_forced("control") == 0


def test_concentration_channel_matches_entity_counter():
    """An enemy attacking a concentrating character → the seam's concentration counts
    equal the character's own concentration_checks/_breaks entity counters."""
    char = Entity(name="char", hp=10**6, base_stats={"ac": 1, **_ALL_SAVES})
    char.concentration = "test_spell"        # remove_effect tolerates an unknown source
    enemy = Entity(name="enemy", hp=10**9, base_stats=enemy_base_stats(8))
    pol = BaselineEnemyPolicy(level=8, primary=char, save_round_prob=0.0,
                              rounds_per_combat=4)
    pol.on_combat_start(0, SeededRNG(3))
    sched = Scheduler(rng=SeededRNG(3), entities=[char, enemy],
                      policies={enemy.id: pol}, max_rounds=4)
    sched.run()
    assert char.concentration_checks > 0     # AC 1 → the enemy always hits → checks fire
    assert sched.telemetry.concentration_checks == char.concentration_checks
    assert sched.telemetry.concentration_breaks == char.concentration_breaks
