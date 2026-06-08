"""Tests for SeededRNG."""

import pytest
from src.rng import SeededRNG


def test_roll_returns_correct_count():
    rng = SeededRNG(seed=1)
    results = rng.roll(4, 6)
    assert len(results) == 4


def test_roll_values_in_range():
    rng = SeededRNG(seed=1)
    for _ in range(100):
        val = rng.roll_one(20)
        assert 1 <= val <= 20


def test_seeded_reproducibility():
    """Same seed must produce same sequence."""
    rng_a = SeededRNG(seed=42)
    rng_b = SeededRNG(seed=42)
    for _ in range(20):
        assert rng_a.roll_one(20) == rng_b.roll_one(20)


def test_different_seeds_differ():
    """Different seeds should (almost certainly) diverge."""
    rng_a = SeededRNG(seed=1)
    rng_b = SeededRNG(seed=2)
    rolls_a = [rng_a.roll_one(20) for _ in range(10)]
    rolls_b = [rng_b.roll_one(20) for _ in range(10)]
    assert rolls_a != rolls_b


def test_invalid_n_raises():
    rng = SeededRNG(seed=1)
    with pytest.raises(ValueError):
        rng.roll(0, 6)


def test_invalid_sides_raises():
    rng = SeededRNG(seed=1)
    with pytest.raises(ValueError):
        rng.roll(1, 1)
