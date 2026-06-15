"""test_cast_effect.py — the `cast_effect` combat-effect primitive (buffs & debuffs).

A first-class NON-DAMAGING cast: the scheduler drains action economy + resources
(as for any Choice), installs the persisting payload, and pushes NO DamageEvent.
See design/buff_primitive.md.  Now-scope payloads exercised here: ModifierStack
mods (self-buff and target debuff), concentration, the capability case (no
payload), and the combat-boundary sweep.
"""

import logging

from src.entity import Entity
from src.modifiers import Modifier
from src.policy import Choice, GameState
from src.resources import ResourceEntry, ResourcePool
from src.rng import SeededRNG
from src.scheduler import Scheduler

logging.disable(logging.CRITICAL)


class _OneShotPolicy:
    """Emit a fixed list of choices on round 1 only, then nothing."""

    def __init__(self, choices):
        self._choices = choices

    def decide(self, snapshot: GameState):
        return self._choices if snapshot.round_number == 1 else []


def _run(actor, others, choices, rounds: int = 1):
    sched = Scheduler(
        rng=SeededRNG(0),
        entities=[actor, *others],
        policies={actor.id: _OneShotPolicy(choices)},
        max_rounds=rounds,
    )
    return sched.run()


def test_cast_effect_self_buff_installs_modifier_and_deals_no_damage():
    actor = Entity(name="Caster", hp=50, base_stats={"ac": 15})
    choice = Choice(
        action_type="cast_effect", cost="bonus_action",
        effect_source="shield_of_faith",
        modifiers=[Modifier(stat="ac", value=2, source="shield_of_faith")],
    )
    log = _run(actor, [], [choice])
    assert sum(log) == 0                        # no DamageEvent was enqueued
    assert actor.stat("ac") == 17               # +2 folded onto the stack (bearer = actor)


def test_cast_effect_sets_concentration_on_the_actor():
    actor = Entity(name="Caster", hp=50, base_stats={"attack_bonus": 5})
    choice = Choice(
        action_type="cast_effect", cost="action",
        effect_source="bless", concentration=True,
        modifiers=[Modifier(stat="attack_bonus", value=0, source="bless", dice=(1, 4))],
    )
    _run(actor, [], [choice])
    assert actor.concentration == "bless"


def test_cast_effect_debuff_installs_on_the_target_not_the_actor():
    actor = Entity(name="Caster", hp=50, base_stats={"ac": 15})
    enemy = Entity(name="Foe", hp=50, base_stats={"ac": 16})
    choice = Choice(
        action_type="cast_effect", cost="action", target=enemy,
        effect_source="bane",
        modifiers=[Modifier(stat="ac", value=-2, source="bane")],
    )
    _run(actor, [enemy], [choice])
    assert enemy.stat("ac") == 14               # the debuff lands on the target
    assert actor.stat("ac") == 15               # the caster is untouched


def test_cast_effect_consumes_action_economy_and_resources():
    actor = Entity(
        name="Caster", hp=50, base_stats={"ac": 15},
        resources=ResourcePool(
            {"channel_divinity": ResourceEntry(current=2, maximum=2, sr_restore=0)}
        ),
    )
    choice = Choice(
        action_type="cast_effect", cost="bonus_action",
        effect_source="shield_of_faith",
        resource_cost={"channel_divinity": 1},
        modifiers=[Modifier(stat="ac", value=2, source="shield_of_faith")],
    )
    _run(actor, [], [choice])
    assert actor.resources.available("channel_divinity") == 1   # one charge spent


def test_capability_cast_effect_installs_nothing_but_runs_cleanly():
    # A capability buff (Shillelagh / Starry Form) carries NO payload — it exists
    # only to consume the economy honestly; nothing is installed, no damage dealt,
    # and (with no modifier) it is not tracked for the combat-boundary sweep.
    actor = Entity(name="Caster", hp=50, base_stats={"ac": 15})
    choice = Choice(action_type="cast_effect", cost="bonus_action", effect_source="shillelagh")
    log = _run(actor, [], [choice])
    assert sum(log) == 0
    assert actor._combat_buff_sources == set()


def test_clear_combat_buffs_sweeps_combat_clock_modifier_and_concentration():
    actor = Entity(name="Caster", hp=50, base_stats={"ac": 15})
    choice = Choice(
        action_type="cast_effect", cost="action",
        effect_source="bless", concentration=True, duration="combat",
        modifiers=[Modifier(stat="ac", value=3, source="bless")],
    )
    _run(actor, [], [choice])
    assert actor.stat("ac") == 18 and actor.concentration == "bless"
    actor.clear_combat_buffs()                  # the combat boundary sweep
    assert actor.stat("ac") == 15               # combat-clock modifier removed
    assert actor.concentration is None          # its concentration cleared
    assert actor._combat_buff_sources == set()
