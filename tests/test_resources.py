"""
test_resources.py — ResourcePool unit tests.

Covers consume, restore, restore_sr, restore_lr, find_spell_slot, as_dict.
"""

import pytest
from src.resources import ResourceEntry, ResourcePool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_war_angel_pool_lvl5():
    """Approximate War Angel level-5 resource pool."""
    return ResourcePool({
        "spell_slot_1":    ResourceEntry(current=4, maximum=4, sr_restore=0),
        "spell_slot_2":    ResourceEntry(current=2, maximum=2, sr_restore=0),
        "pact_magic_slot": ResourceEntry(current=1, maximum=1, sr_restore="full"),
        "channel_divinity":ResourceEntry(current=2, maximum=2, sr_restore=1),
        "war_priest":      ResourceEntry(current=3, maximum=3, sr_restore="full"),
        "action_surge":    ResourceEntry(current=1, maximum=1, sr_restore="full"),
    })


# ---------------------------------------------------------------------------
# available / as_dict
# ---------------------------------------------------------------------------

def test_available_returns_current():
    pool = make_war_angel_pool_lvl5()
    assert pool.available("spell_slot_1") == 4
    assert pool.available("war_priest") == 3

def test_available_returns_zero_for_unknown():
    pool = make_war_angel_pool_lvl5()
    assert pool.available("ki_points") == 0

def test_maximum_returns_max():
    pool = make_war_angel_pool_lvl5()
    assert pool.maximum("spell_slot_1") == 4

def test_as_dict_flat():
    pool = make_war_angel_pool_lvl5()
    d = pool.as_dict()
    assert d["spell_slot_1"] == 4
    assert d["war_priest"] == 3
    assert "channel_divinity" in d


# ---------------------------------------------------------------------------
# consume
# ---------------------------------------------------------------------------

def test_consume_reduces_current():
    pool = make_war_angel_pool_lvl5()
    assert pool.consume("spell_slot_1")
    assert pool.available("spell_slot_1") == 3

def test_consume_returns_false_when_insufficient():
    pool = make_war_angel_pool_lvl5()
    pool.consume("pact_magic_slot")  # deplete it
    result = pool.consume("pact_magic_slot")
    assert result is False
    assert pool.available("pact_magic_slot") == 0  # unchanged

def test_consume_returns_false_for_unknown_resource():
    pool = make_war_angel_pool_lvl5()
    assert pool.consume("ki_points") is False

def test_consume_multi_amount():
    pool = make_war_angel_pool_lvl5()
    assert pool.consume("spell_slot_1", 3)
    assert pool.available("spell_slot_1") == 1

def test_consume_exact_amount_leaves_zero():
    pool = make_war_angel_pool_lvl5()
    assert pool.consume("war_priest", 3)
    assert pool.available("war_priest") == 0


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------

def test_restore_full_brings_to_max():
    pool = make_war_angel_pool_lvl5()
    pool.consume("spell_slot_1", 4)
    pool.restore("spell_slot_1")
    assert pool.available("spell_slot_1") == 4

def test_restore_int_is_clamped_to_max():
    pool = make_war_angel_pool_lvl5()
    pool.restore("war_priest", 999)
    assert pool.available("war_priest") == 3  # clamped to maximum

def test_restore_partial():
    pool = make_war_angel_pool_lvl5()
    pool.consume("spell_slot_1", 4)
    pool.restore("spell_slot_1", 2)
    assert pool.available("spell_slot_1") == 2


# ---------------------------------------------------------------------------
# restore_sr
# ---------------------------------------------------------------------------

def test_restore_sr_fully_restores_full_sr_resources():
    pool = make_war_angel_pool_lvl5()
    pool.consume("pact_magic_slot")
    pool.consume("war_priest", 3)
    pool.consume("action_surge")
    pool.restore_sr()
    assert pool.available("pact_magic_slot") == 1
    assert pool.available("war_priest") == 3
    assert pool.available("action_surge") == 1

def test_restore_sr_adds_partial_for_int_sr_restore():
    pool = make_war_angel_pool_lvl5()
    pool.consume("channel_divinity", 2)  # deplete
    pool.restore_sr()
    # sr_restore=1 → restored by 1, not fully
    assert pool.available("channel_divinity") == 1

def test_restore_sr_does_not_exceed_maximum():
    pool = make_war_angel_pool_lvl5()
    # channel_divinity already at max (2); SR adds 1 but clamps to 2
    pool.restore_sr()
    assert pool.available("channel_divinity") == 2

def test_restore_sr_does_not_touch_lr_only_resources():
    pool = make_war_angel_pool_lvl5()
    pool.consume("spell_slot_1", 2)
    pool.consume("spell_slot_2", 2)
    pool.restore_sr()
    # LR-only: unchanged
    assert pool.available("spell_slot_1") == 2
    assert pool.available("spell_slot_2") == 0


# ---------------------------------------------------------------------------
# restore_lr
# ---------------------------------------------------------------------------

def test_restore_lr_restores_everything():
    pool = make_war_angel_pool_lvl5()
    pool.consume("spell_slot_1", 4)
    pool.consume("spell_slot_2", 2)
    pool.consume("channel_divinity", 2)
    pool.consume("action_surge")
    pool.restore_lr()
    assert pool.available("spell_slot_1") == 4
    assert pool.available("spell_slot_2") == 2
    assert pool.available("channel_divinity") == 2
    assert pool.available("action_surge") == 1


# ---------------------------------------------------------------------------
# find_spell_slot
# ---------------------------------------------------------------------------

def test_find_spell_slot_returns_lowest_available():
    pool = make_war_angel_pool_lvl5()
    assert pool.find_spell_slot(1) == "spell_slot_1"

def test_find_spell_slot_respects_min_level():
    pool = make_war_angel_pool_lvl5()
    assert pool.find_spell_slot(2) == "spell_slot_2"

def test_find_spell_slot_skips_depleted():
    pool = make_war_angel_pool_lvl5()
    pool.consume("spell_slot_1", 4)  # deplete level-1 slots
    assert pool.find_spell_slot(1) == "spell_slot_2"

def test_find_spell_slot_returns_none_when_none_available():
    pool = make_war_angel_pool_lvl5()
    pool.consume("spell_slot_1", 4)
    pool.consume("spell_slot_2", 2)
    assert pool.find_spell_slot(1) is None

def test_find_spell_slot_returns_none_above_available_levels():
    pool = make_war_angel_pool_lvl5()
    assert pool.find_spell_slot(3) is None  # no level-3 slots in this pool


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------

def test_repr_is_readable():
    pool = ResourcePool({"ki": ResourceEntry(current=5, maximum=5, sr_restore="full")})
    r = repr(pool)
    assert "ki=5/5" in r
