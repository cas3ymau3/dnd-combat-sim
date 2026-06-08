"""Tests for Modifier and ModifierStack."""

import pytest
from src.modifiers import Modifier, ModifierStack


def test_compute_no_modifiers_returns_base():
    stack = ModifierStack()
    assert stack.compute("attack_bonus", base=5) == 5


def test_flat_modifier_adds():
    stack = ModifierStack()
    stack.add(Modifier(stat="attack_bonus", value=2, source="bless"))
    assert stack.compute("attack_bonus", base=5) == 7


def test_multiple_flat_modifiers_stack():
    stack = ModifierStack()
    stack.add(Modifier(stat="attack_bonus", value=2, source="bless"))
    stack.add(Modifier(stat="attack_bonus", value=3, source="rage"))
    assert stack.compute("attack_bonus", base=5) == 10


def test_callable_modifier():
    """A callable modifier (e.g. multiply by 2) should be applied correctly."""
    stack = ModifierStack()
    stack.add(Modifier(stat="damage_bonus", value=lambda x: x * 2, source="double_damage"))
    assert stack.compute("damage_bonus", base=4) == 8


def test_remove_modifier():
    stack = ModifierStack()
    stack.add(Modifier(stat="ac", value=5, source="shield_spell"))
    assert stack.compute("ac", base=16) == 21
    removed = stack.remove("shield_spell")
    assert removed == 1
    assert stack.compute("ac", base=16) == 16


def test_remove_nonexistent_returns_zero():
    stack = ModifierStack()
    assert stack.remove("nonexistent") == 0


def test_expired_modifier_ignored():
    """A modifier past its expiry tick should not be applied."""
    stack = ModifierStack()
    # Expires at tick (1, 0, 5) — should be inactive at tick (1, 0, 5) or later
    stack.add(Modifier(stat="attack_bonus", value=2, source="bless", expires_at=(1, 0, 5)))
    # Active before expiry
    assert stack.compute("attack_bonus", base=5, tick=(1, 0, 4)) == 7
    # Inactive at expiry tick
    assert stack.compute("attack_bonus", base=5, tick=(1, 0, 5)) == 5
    # Inactive after
    assert stack.compute("attack_bonus", base=5, tick=(2, 0, 0)) == 5


def test_modifier_with_no_tick_always_active():
    """Calling compute with tick=None treats all modifiers as active."""
    stack = ModifierStack()
    stack.add(Modifier(stat="ac", value=2, source="defensive_stance", expires_at=(1, 0, 0)))
    # No tick provided — should apply regardless of expires_at
    assert stack.compute("ac", base=16, tick=None) == 18


def test_phase_filter():
    """Modifiers with a phase tag should only apply when that phase is queried."""
    stack = ModifierStack()
    stack.add(Modifier(stat="damage_bonus", value=10, source="sneak_attack", phase="roll"))
    # Querying with phase="roll" should include it
    assert stack.compute("damage_bonus", base=0, phase="roll") == 10
    # Querying with a different phase should exclude it
    assert stack.compute("damage_bonus", base=0, phase="flat_bonus") == 0
    # Querying with phase=None should include everything
    assert stack.compute("damage_bonus", base=0, phase=None) == 10


def test_stat_mismatch_ignored():
    """Modifiers for a different stat should not affect the queried stat."""
    stack = ModifierStack()
    stack.add(Modifier(stat="ac", value=5, source="shield"))
    assert stack.compute("attack_bonus", base=3) == 3
