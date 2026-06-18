"""test_silvertail.py — substrate #7 / 7a SUMMON (controlled-ally summons).

The minimal 7a slice (session 20): the Blessed of Silvertail at char L4 with its
PRIMAL COMPANION as a create_entity'd ACTOR, COMMANDED on the master's turn (the
Choice.actor override), reported in its own per-summon DPR column.  Plus the
create_entity / destroy_entity verbs (design.md §4 #12) and their effect_source
teardown.

Validation framing (as the rest of the project): consistency / sanity via
deterministic FakeRNG (engine seams) + directional DPR off the per-(source,target)
ledger, NOT number-matching.
"""

import logging

from src.builds import silvertail as sv
from src.entity import Entity
from src.policy import Choice
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.summons import SummonSpec, create_entity, destroy_entity

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; d20 and damage rolls both go through .roll (the
    suite's standard deterministic stub)."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


class _OneShot:
    """Emit a fixed list of choices on round 1, nothing after."""

    def __init__(self, choices):
        self._choices = choices

    def decide(self, snapshot):
        return self._choices if snapshot.round_number == 1 else []


def _beast_strike(beast, target):
    """A commanded Beast's Strike: actor=beast (the override), cost=the commander's
    Bonus Action, 1d8 + 5 + 1d6 charge."""
    return Choice(
        action_type="attack",
        cost="bonus_action",
        actor=beast,
        target=target,
        weapon_stat="attack_bonus",
        damage_dice=(1, 8),
        damage_bonus=5,
        extra_damage_dice=[(1, 6)],
        damage_type="bludgeoning",
    )


# ===========================================================================
# Commanded action (Choice.actor) — the strike acts as, and is attributed to,
# the BEAST, while the COST is the commander's
# ===========================================================================

def test_commanded_strike_is_attributed_to_the_beast_not_the_commander():
    # A master commands the beast to strike; the strike must use the BEAST's stats
    # and land in the BEAST's (source, target) column — not the master's.
    master = Entity(name="master", hp=40, base_stats={"ac": 19, "spell_attack_bonus": 5})
    beast = Entity(name="beast", hp=20,
                   base_stats={"ac": 16, "attack_bonus": 5, "damage_dice": (1, 8),
                               "damage_bonus": 5})
    dummy = Entity(name="dummy", hp=10**9, base_stats={"ac": 15})
    # d20=15 (hit, +5 = 20 >= AC 15), 1d8=8, 1d6=6 → 8 + 6 + 5 = 19.
    sch = Scheduler(
        rng=FakeRNG([15, 8, 6]),
        entities=[master, beast, dummy],
        policies={master.id: _OneShot([_beast_strike(beast, dummy)])},
        max_rounds=1,
    )
    sch.run()
    # Attributed to the BEAST → dummy, not the master → dummy.
    assert sch.damage_by_source_target.get((beast.id, dummy.id)) == 19
    assert sch.damage_by_source_target.get((master.id, dummy.id)) is None
    # The dummy actually took it.
    assert sch.damage_received[dummy.id][0] == 19


def test_command_costs_the_commanders_bonus_action_only_once():
    # The command draws the MASTER's Bonus Action: emitting TWO commanded strikes
    # (both cost="bonus_action") resolves only the first — the second is skipped for
    # lack of a bonus action.  Proves the cost is on the commander, not the beast.
    master = Entity(name="master", hp=40, base_stats={"ac": 19})
    beast = Entity(name="beast", hp=20,
                   base_stats={"ac": 16, "attack_bonus": 5, "damage_dice": (1, 8),
                               "damage_bonus": 5})
    dummy = Entity(name="dummy", hp=10**9, base_stats={"ac": 15})
    # Only ONE strike resolves → only one (d20, d8, d6) triple is consumed.
    sch = Scheduler(
        rng=FakeRNG([15, 8, 6, 15, 8, 6]),
        entities=[master, beast, dummy],
        policies={master.id: _OneShot(
            [_beast_strike(beast, dummy), _beast_strike(beast, dummy)])},
        max_rounds=1,
    )
    sch.run()
    assert sch.damage_by_source_target.get((beast.id, dummy.id)) == 19   # one strike
    # The second strike never rolled (no BA left): three values remain unused.
    assert len(sch.rng._values) == 3


def test_commanded_strike_damage_math_is_exact():
    # 1d8 + 1d6 charge + (2 + WIS) flat = full Beast's-Strike-with-charge math.
    master = Entity(name="master", hp=40, base_stats={"ac": 19})
    beast = Entity(name="beast", hp=20, base_stats={"ac": 16, "attack_bonus": 5})
    dummy = Entity(name="dummy", hp=10**9, base_stats={"ac": 15})
    # d20=10 (10 + 5 = 15 >= AC 15, a hit, not a crit), 1d8=3, 1d6=4 → 3 + 4 + 5 = 12.
    sch = Scheduler(
        rng=FakeRNG([10, 3, 4]),
        entities=[master, beast, dummy],
        policies={master.id: _OneShot([_beast_strike(beast, dummy)])},
        max_rounds=1,
    )
    sch.run()
    assert sch.damage_by_source_target[(beast.id, dummy.id)] == 12


def test_commanded_beast_takes_no_turn_of_its_own():
    # The beast is commanded (no policy of its own), so it never gets a TurnStartEvent
    # — with NO master policy it deals nothing (it does not act independently).
    master = Entity(name="master", hp=40, base_stats={"ac": 19})
    beast = Entity(name="beast", hp=20, base_stats={"ac": 16, "attack_bonus": 5,
                                                    "damage_dice": (1, 8)})
    dummy = Entity(name="dummy", hp=10**9, base_stats={"ac": 15})
    sch = Scheduler(
        rng=FakeRNG([20] * 50),
        entities=[master, beast, dummy],
        policies={},                          # nobody acts
        max_rounds=2,
    )
    sch.run()
    assert sch.damage_by_source_target == {}


# ===========================================================================
# create_entity / destroy_entity verbs (design.md §4 #12) + teardown
# ===========================================================================

def test_create_entity_adds_to_roster_and_registers_policy():
    entities: list = []
    policies: dict = {}
    indep = Entity(name="indep", hp=10, base_stats={})
    pol = object()
    create_entity(entities, policies, indep, policy=pol)
    assert indep in entities
    assert policies[indep.id] is pol
    assert indep.destroyed is False
    # Idempotent — a second create is a no-op (no duplicate).
    create_entity(entities, policies, indep, policy=pol)
    assert entities.count(indep) == 1


def test_destroy_entity_removes_from_roster_and_marks_destroyed():
    entities: list = []
    policies: dict = {}
    ent = Entity(name="ent", hp=10, base_stats={})
    create_entity(entities, policies, ent)
    destroy_entity(entities, policies, ent)
    assert ent not in entities
    assert ent.id not in policies
    assert ent.destroyed is True


def test_remove_effect_winks_out_a_summon_keyed_to_its_source():
    # A summon noted under an effect_source is marked destroyed when that source is
    # removed (concentration drop / combat sweep) — the design.md §1 "wink out".
    caster = Entity(name="caster", hp=40, base_stats={})
    summon = Entity(name="summon", hp=20, base_stats={})
    caster.note_effect_summon("conjure_beast", summon)
    assert summon.destroyed is False
    caster.remove_effect("conjure_beast")
    assert summon.destroyed is True


def test_destroyed_independent_summon_takes_no_turns():
    # A summon WITH its own policy that has been destroyed is skipped in turn
    # enqueueing (it has winked out) — so it never decides.
    class _Recorder:
        def __init__(self):
            self.calls = 0

        def decide(self, snapshot):
            self.calls += 1
            return []

    ghost = Entity(name="ghost", hp=10, base_stats={"ac": 10})
    ghost.destroyed = True
    rec = _Recorder()
    Scheduler(
        rng=FakeRNG([]),
        entities=[ghost],
        policies={ghost.id: rec},
        max_rounds=2,
    ).run()
    assert rec.calls == 0


def test_cast_effect_summons_payload_creates_into_the_live_combat():
    # The general mid-combat verb: a cast_effect carrying a summons payload
    # create_entity's the summon into the LIVE scheduler roster + damage ledger, and
    # notes it under effect_source so remove_effect tears it down.
    caster = Entity(name="caster", hp=40, base_stats={"ac": 12})
    beast = Entity(name="beast", hp=20, base_stats={"ac": 16, "attack_bonus": 5})
    cast = Choice(
        action_type="cast_effect",
        cost="action",
        effect_source="conjure_beast",
        summons=[SummonSpec(entity=beast, source="conjure_beast", commander=caster)],
        duration="combat",
    )
    sch = Scheduler(
        rng=FakeRNG([]),
        entities=[caster],
        policies={caster.id: _OneShot([cast])},
        max_rounds=1,
    )
    sch.run()
    # The summon is now in the live roster + ledger.
    assert beast in sch.entities
    assert beast.id in sch.damage_received
    # ...and tracked under the source, so the combat-boundary / concentration sweep
    # winks it out.
    caster.remove_effect("conjure_beast")
    assert beast.destroyed is True


# ===========================================================================
# Integration — make_silvertail_runner: build column vs summon column (both,
# reported separately) over a long run
# ===========================================================================

def test_summon_is_an_actor_with_its_own_hp_and_ac():
    _runner, _char, beast, _dummy = sv.make_silvertail_runner(4, SeededRNG(0))
    assert beast.max_hp == 20            # 5 + 5 * ranger-3
    assert beast.stat("ac") == 16        # 13 + WIS(3)
    assert beast.stat("attack_bonus") == 5   # Beast's-Strike to-hit (PB + WIS)
    assert beast.destroyed is False      # summoned at day start, persists


def test_summon_column_is_separate_from_and_additive_to_the_build_column():
    # The headline 7a deliverable (user decision, session 17): the build's OWN column
    # and the summon column are reported SEPARATELY, and the party total is their sum.
    runner, char, beast, _dummy = sv.make_silvertail_runner(4, SeededRNG(7))
    build_total = 0
    summon_total = 0
    for _ in range(200):
        r = runner.run_day()
        b = r.damage_by_source(char.id)         # master's shocking grasp
        s = r.damage_by_source(beast.id)        # commanded Beast's Strike
        # Per-day: the party total is exactly the two columns summed.
        assert r.party_total([char.id, beast.id]) == b + s
        build_total += b
        summon_total += s
    # Both columns do real, distinct work; the cornerstone beast out-damages the
    # master's cantrip (the build is a support whose summon is the main output —
    # exactly the case the "report both, separately" decision exists for).
    assert build_total > 0
    assert summon_total > build_total


def test_master_and_beast_only_ever_damage_the_dummy():
    # Sanity: in this minimal slice neither friendly hits the other; all output lands
    # on the dummy (the per-(source,target) ledger keeps the columns clean).
    runner, char, beast, dummy = sv.make_silvertail_runner(4, SeededRNG(3))
    for _ in range(50):
        r = runner.run_day()
        assert r.damage_by_source(char.id) == r.damage_source_to(char.id, dummy.id)
        assert r.damage_by_source(beast.id) == r.damage_source_to(beast.id, dummy.id)
