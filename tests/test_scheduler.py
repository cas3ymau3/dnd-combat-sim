"""Tests for the EventQueue and Scheduler tick ordering."""

import pytest
from src.events import (
    AttackRollEvent,
    DamageEvent,
    EventQueue,
    TurnStartEvent,
    make_tick,
)
from src.entity import Entity


def _dummy_entity(name="X", ac=10):
    return Entity(name=name, hp=999, base_stats={"ac": ac})


def test_event_queue_ordering():
    """Events should pop in ascending tick order."""
    q = EventQueue()
    e1 = _dummy_entity()
    q.push(TurnStartEvent(tick=make_tick(2, 0, 0), actor=e1))
    q.push(TurnStartEvent(tick=make_tick(1, 0, 0), actor=e1))
    q.push(TurnStartEvent(tick=make_tick(1, 1, 0), actor=e1))

    first = q.pop()
    second = q.pop()
    third = q.pop()

    assert first.tick == (1, 0, 0)
    assert second.tick == (1, 1, 0)
    assert third.tick == (2, 0, 0)


def test_event_queue_tiebreak_by_insertion():
    """Equal ticks should pop in insertion order."""
    q = EventQueue()
    e1 = _dummy_entity("A")
    e2 = _dummy_entity("B")
    tick = make_tick(1, 0, 0)
    q.push(TurnStartEvent(tick=tick, actor=e1))
    q.push(TurnStartEvent(tick=tick, actor=e2))

    first = q.pop()
    second = q.pop()
    assert first.actor.name == "A"
    assert second.actor.name == "B"


def test_event_queue_empty_raises():
    q = EventQueue()
    with pytest.raises(IndexError):
        q.pop()


def test_event_queue_len_and_bool():
    q = EventQueue()
    assert not q
    assert len(q) == 0
    e = _dummy_entity()
    q.push(TurnStartEvent(tick=make_tick(1, 0, 0), actor=e))
    assert q
    assert len(q) == 1


def test_make_tick():
    t = make_tick(3, 2, 1)
    assert t == (3, 2, 1)
