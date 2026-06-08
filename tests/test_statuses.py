"""
test_statuses.py — StatusSet unit tests.

Covers apply / has / get / consume / remove and the tick-based expire() sweep.
"""

import pytest
from src.statuses import StatusEntry, StatusSet


# ---------------------------------------------------------------------------
# Basic apply / query
# ---------------------------------------------------------------------------

def test_apply_and_has():
    s = StatusSet()
    s.apply("blessed")
    assert s.has("blessed")
    assert "blessed" in s

def test_get_returns_value():
    s = StatusSet()
    s.apply("vex_advantage", value=42)
    assert s.get("vex_advantage") == 42

def test_get_missing_returns_default():
    s = StatusSet()
    assert s.get("nope") is None
    assert s.get("nope", default="x") == "x"

def test_apply_default_value_is_true():
    s = StatusSet()
    s.apply("sapped")
    assert s.get("sapped") is True

def test_reapply_overwrites():
    s = StatusSet()
    s.apply("vex_advantage", value=1)
    s.apply("vex_advantage", value=2)
    assert s.get("vex_advantage") == 2

def test_len_and_active_names():
    s = StatusSet()
    s.apply("a")
    s.apply("b")
    assert len(s) == 2
    assert set(s.active_names()) == {"a", "b"}


# ---------------------------------------------------------------------------
# remove / consume
# ---------------------------------------------------------------------------

def test_remove():
    s = StatusSet()
    s.apply("blessed")
    s.remove("blessed")
    assert not s.has("blessed")

def test_remove_missing_is_noop():
    s = StatusSet()
    s.remove("nothing")  # no error
    assert len(s) == 0

def test_consume_returns_value_and_removes():
    s = StatusSet()
    s.apply("vex_advantage", value=7)
    val = s.consume("vex_advantage")
    assert val == 7
    assert not s.has("vex_advantage")

def test_consume_missing_returns_none():
    s = StatusSet()
    assert s.consume("absent") is None


# ---------------------------------------------------------------------------
# expire() — tick-based sweep
# ---------------------------------------------------------------------------

def test_permanent_status_never_expires():
    s = StatusSet()
    s.apply("permanent", expiry=None)
    s.expire(99, 5)
    assert s.has("permanent")

def test_expire_removes_at_exact_tick():
    s = StatusSet()
    s.apply("sapped", expiry=(2, 0))
    purged = s.expire(2, 0)
    assert "sapped" in purged
    assert not s.has("sapped")

def test_expire_removes_when_past_tick():
    s = StatusSet()
    s.apply("sapped", expiry=(2, 0))
    s.expire(3, 0)
    assert not s.has("sapped")

def test_expire_keeps_before_tick():
    s = StatusSet()
    s.apply("sapped", expiry=(2, 0))
    purged = s.expire(1, 5)
    assert purged == []
    assert s.has("sapped")

def test_expire_compares_turn_index_within_round():
    s = StatusSet()
    # expires at (round 2, turn 1)
    s.apply("vex_advantage", expiry=(2, 1))
    # (2, 0) is before (2, 1) → still active
    s.expire(2, 0)
    assert s.has("vex_advantage")
    # (2, 1) reaches it → purged
    s.expire(2, 1)
    assert not s.has("vex_advantage")

def test_expire_returns_purged_names():
    s = StatusSet()
    s.apply("a", expiry=(1, 0))
    s.apply("b", expiry=(5, 0))
    s.apply("c", expiry=None)
    purged = s.expire(1, 0)
    assert purged == ["a"]
    assert s.has("b") and s.has("c")
