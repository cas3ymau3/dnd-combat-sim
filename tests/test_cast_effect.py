"""test_cast_effect.py — the `cast_effect` combat-effect primitive (buffs & debuffs).

A first-class NON-DAMAGING cast: the scheduler drains action economy + resources
(as for any Choice), installs the persisting payload, and pushes NO DamageEvent.
See design/buff_primitive.md.  Now-scope payloads exercised here: ModifierStack
mods (self-buff and target debuff), concentration, the capability case (no
payload), and the combat-boundary sweep.
"""

import logging
import math

from src.entity import Entity
from src.events import AttackRollEvent, EventQueue, make_tick
from src.modifiers import Modifier
from src.policy import ApplicationSave, Choice, GameState
from src.resources import ResourceEntry, ResourcePool
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.statuses import StatusSpec
from src.verbs import resolve_attack_roll

logging.disable(logging.CRITICAL)


class _OneShotPolicy:
    """Emit a fixed list of choices on round 1 only, then nothing.

    Note this is a pure read (the design's decide() contract): it inspects the
    snapshot and returns Choices — it never rolls dice or mutates state.  Every
    cast_effect roll below (the application_save) happens in the SCHEDULER, not
    here, exactly as the policy/resolution split requires (CLAUDE.md §7).
    """

    def __init__(self, choices):
        self._choices = choices

    def decide(self, snapshot: GameState):
        return self._choices if snapshot.round_number == 1 else []


def _run(actor, others, choices, rounds: int = 1, rng=None):
    sched = Scheduler(
        rng=rng if rng is not None else SeededRNG(0),
        entities=[actor, *others],
        policies={actor.id: _OneShotPolicy(choices)},
        max_rounds=rounds,
    )
    return sched.run()


class FakeRNG:
    """Pops preloaded values; records (n, sides) per call (mirrors the suite's
    standard deterministic RNG — see test_weapon_mastery)."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        self.roll_calls.append((1, sides))
        return self._values.pop(0)


def _attack_event(actor, target, is_spell=False):
    return AttackRollEvent(
        tick=make_tick(1, 0, 1),
        actor=actor,
        target=target,
        is_spell=is_spell,
    )


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


# ===========================================================================
# Substrate #3 — StatusSet payload (advantage grants) + the debuff
# application_save.  Consumers: Innate Sorcery (self-grant, no save) and
# Faerie Fire (debuff, DEX save → advantage-against-target).
# ===========================================================================

# --- The granted statuses actually change a downstream attack roll ----------

def test_faerie_fire_status_grants_attackers_advantage_against_target():
    # A target carrying attack_advantage_against → ANY attacker rolls with
    # advantage (no spell gate, per Faerie Fire), and the status PERSISTS (a
    # duration buff, read not consumed — unlike one-shot vex/sap).
    attacker = Entity(name="Ally", hp=50, base_stats={"attack_bonus": 0, "damage_dice": (1, 8), "damage_bonus": 0})
    foe = Entity(name="Foe", hp=math.inf, base_stats={"ac": 10})
    foe.statuses.apply("attack_advantage_against")
    rng = FakeRNG([4, 19])                       # advantage → max(4, 19)
    resolve_attack_roll(_attack_event(attacker, foe), rng, EventQueue(), next_sequence=2)
    assert rng.roll_calls[0] == (2, 20)          # rolled with advantage
    assert foe.statuses.has("attack_advantage_against")   # not consumed


def test_innate_sorcery_status_grants_advantage_on_spell_attacks_only():
    # spell_attack_advantage on the caster → advantage on a SPELL attack, but a
    # weapon swing (is_spell=False) is unaffected.  Persists either way.
    caster = Entity(name="Caster", hp=50, base_stats={"attack_bonus": 0, "damage_dice": (1, 8), "damage_bonus": 0})
    foe = Entity(name="Foe", hp=math.inf, base_stats={"ac": 10})
    caster.statuses.apply("spell_attack_advantage")

    spell_rng = FakeRNG([4, 19])
    resolve_attack_roll(_attack_event(caster, foe, is_spell=True), spell_rng, EventQueue(), next_sequence=2)
    assert spell_rng.roll_calls[0] == (2, 20)    # spell attack → advantage

    weapon_rng = FakeRNG([7])
    resolve_attack_roll(_attack_event(caster, foe, is_spell=False), weapon_rng, EventQueue(), next_sequence=2)
    assert weapon_rng.roll_calls[0] == (1, 20)   # weapon swing → straight
    assert caster.statuses.has("spell_attack_advantage")  # not consumed


# --- cast_effect installs the StatusSet payload (self-grant, no save) -------

def test_cast_effect_self_grant_installs_status_and_deals_no_damage():
    # Innate Sorcery: a no-save self-buff that grants a STATUS (not a modifier).
    actor = Entity(name="Sorcerer", hp=50, base_stats={"spell_attack_bonus": 5})
    choice = Choice(
        action_type="cast_effect", cost="bonus_action",
        effect_source="innate_sorcery",
        statuses=[StatusSpec("spell_attack_advantage")],
    )
    log = _run(actor, [], [choice])
    assert sum(log) == 0
    assert actor.statuses.has("spell_attack_advantage")   # landed on the actor


# --- The debuff application_save: status lands on a fail, resisted on a make -

def test_cast_effect_debuff_status_lands_on_a_FAILED_application_save():
    # Faerie Fire: the target rolls DEX vs the caster's DC; on a FAIL the
    # advantage-granting status lands on the target (not the caster).
    actor = Entity(name="Caster", hp=50, base_stats={"spell_save_dc": 15})
    enemy = Entity(name="Foe", hp=50, base_stats={"ac": 16, "dex_save": 0})
    choice = Choice(
        action_type="cast_effect", cost="action", target=enemy,
        effect_source="faerie_fire", concentration=True,
        statuses=[StatusSpec("attack_advantage_against")],
        application_save=ApplicationSave(save_stat="dex_save"),
    )
    _run(actor, [enemy], [choice], rng=FakeRNG([5]))   # 5 + 0 = 5 < DC 15 → FAIL
    assert enemy.statuses.has("attack_advantage_against")
    assert not actor.statuses.has("attack_advantage_against")
    assert actor.concentration == "faerie_fire"


def test_cast_effect_debuff_whole_payload_negated_on_a_MADE_application_save():
    # A made save negates the ENTIRE payload — both the status AND any modifier
    # in the same cast (e.g. a Bane-shaped debuff bundling -1d4 with a flag).
    actor = Entity(name="Caster", hp=50, base_stats={"spell_save_dc": 15})
    enemy = Entity(name="Foe", hp=50, base_stats={"ac": 16, "dex_save": 0})
    choice = Choice(
        action_type="cast_effect", cost="action", target=enemy,
        effect_source="faerie_fire",
        statuses=[StatusSpec("attack_advantage_against")],
        modifiers=[Modifier(stat="ac", value=-2, source="faerie_fire")],
        application_save=ApplicationSave(save_stat="dex_save"),
    )
    _run(actor, [enemy], [choice], rng=FakeRNG([19]))  # 19 + 0 = 19 >= DC 15 → MADE
    assert not enemy.statuses.has("attack_advantage_against")  # status resisted
    assert enemy.stat("ac") == 16                              # modifier resisted too


def test_application_save_is_target_save_vs_caster_dc_exact_at_the_boundary():
    # Per-save resolution exact: enemy dex_save +2 vs caster DC 15.  d20=12 →
    # 14 < 15 fails (lands); d20=13 → 15 >= 15 makes it (resisted).
    def cast(d20):
        actor = Entity(name="Caster", hp=50, base_stats={"spell_save_dc": 15})
        enemy = Entity(name="Foe", hp=50, base_stats={"ac": 16, "dex_save": 2})
        choice = Choice(
            action_type="cast_effect", cost="action", target=enemy,
            effect_source="faerie_fire",
            statuses=[StatusSpec("attack_advantage_against")],
            application_save=ApplicationSave(save_stat="dex_save"),
        )
        _run(actor, [enemy], [choice], rng=FakeRNG([d20]))
        return enemy.statuses.has("attack_advantage_against")

    assert cast(12) is True     # 14 < 15 → fail → status lands
    assert cast(13) is False    # 15 >= 15 → save made → resisted


# --- Combat-boundary sweep of a status-only concentration buff --------------

def test_status_only_concentration_buff_is_swept_at_the_combat_boundary():
    # Faerie Fire is concentration but carries NO modifier — so its concentration
    # must still be swept off the CASTER at the boundary (the bug-prone case: the
    # bearer is the enemy, but concentration lives on the caster).
    actor = Entity(name="Caster", hp=50, base_stats={"spell_save_dc": 15})
    enemy = Entity(name="Foe", hp=50, base_stats={"ac": 16, "dex_save": 0})
    choice = Choice(
        action_type="cast_effect", cost="action", target=enemy,
        effect_source="faerie_fire", concentration=True,
        statuses=[StatusSpec("attack_advantage_against")],
        application_save=ApplicationSave(save_stat="dex_save"),
    )
    _run(actor, [enemy], [choice], rng=FakeRNG([5]))   # FAIL → lands
    assert actor.concentration == "faerie_fire" and enemy.statuses.has("attack_advantage_against")

    # The combat boundary (day_runner): statuses cleared on every entity + buff sweep.
    enemy.statuses.clear()
    actor.clear_combat_buffs()
    assert not enemy.statuses.has("attack_advantage_against")  # status swept
    assert actor.concentration is None                         # concentration dropped
