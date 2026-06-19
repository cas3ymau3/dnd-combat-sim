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


# ===========================================================================
# 7c-ON-SUMMON: the summon (beast) as a buff / redirect / protect TARGET.
# The 7c ally-effect machinery (session 19) wired onto the 7a beast (session 20).
# ===========================================================================

def _enemy_strike(target, damage_type="slashing"):
    """An enemy melee attack against `target` (typed, so a defender's all-damage
    response can bite)."""
    return Choice(
        action_type="attack",
        cost="action",
        target=target,
        weapon_stat="attack_bonus",
        damage_type=damage_type,
    )


# -- the `_all` damage-response key (substrate #4 — the session-19 deferral) -----

def test_all_key_damage_response_applies_to_any_type():
    # Warding Bond's "resistance to all damage" — the reserved "_all" key resists any
    # TYPED hit, but leaves an untyped hit (None) unchanged.
    e = Entity(name="e", hp=20, base_stats={})
    e.add_damage_response("warding_bond", {"_all": "resistance"})
    assert e.damage_response_for("slashing") == "resistance"
    assert e.damage_response_for("fire") == "resistance"
    assert e.damage_response_for(None) is None
    # 2024 dominate/cancel rules still apply across the _all key: an _all resistance
    # plus a type-specific VULNERABILITY cancel for that type.
    e.add_damage_response("curse", {"fire": "vulnerability"})
    assert e.damage_response_for("fire") is None
    assert e.damage_response_for("cold") == "resistance"


# -- warding bond: resistance + redirect the post-resistance share to the master ---

def test_warding_bond_resists_the_hit_and_redirects_the_share_to_the_master():
    master = Entity(name="master", hp=60, base_stats={"ac": 20})
    beast = sv.make_primal_companion(8)                  # AC 17, HP 25
    dummy = Entity(name="dummy", hp=10**9,
                   base_stats={"ac": 16, "attack_bonus": 7,
                               "damage_dice": (2, 6), "damage_bonus": 4})
    sv.BeastEffectPolicy("warding_bond", beast, master).install()
    # Beast AC 17 + warding-bond +1 = 18.  Enemy d20=15 (+7 = 22 ≥ 18 → hit);
    # 2d6=[6,6]=12 + 4 = 16 → resistance halves → 8 to the beast → 8 redirected.
    sch = Scheduler(
        rng=FakeRNG([15, 6, 6]),
        entities=[master, beast, dummy],
        policies={dummy.id: _OneShot([_enemy_strike(beast)]),
                  beast.id: sv.BeastEffectPolicy("warding_bond", beast, master)},
        max_rounds=1,
    )
    sch.run()
    assert sch.damage_by_source_target[(dummy.id, beast.id)] == 8       # halved
    assert sch.damage_by_source_target[(dummy.id, master.id)] == 8      # redirected share


# -- protection: impose disadvantage on attacks vs the beast ----------------------

def test_protection_flips_a_hit_to_a_miss_via_the_disadvantage_reroll():
    master = Entity(name="master", hp=60, base_stats={"ac": 20})
    beast = Entity(name="beast", hp=25, base_stats={"ac": 17, "attack_bonus": 7})
    dummy = Entity(name="dummy", hp=10**9,
                   base_stats={"ac": 16, "attack_bonus": 7,
                               "damage_dice": (2, 6), "damage_bonus": 4})
    # First d20=15 (+7 = 22 ≥ 17 → would HIT); protection rolls a SECOND d20=1
    # (1 + 7 = 8 < 17 → MISS) → the attack is flipped to a miss, no damage.
    sch = Scheduler(
        rng=FakeRNG([15, 1]),
        entities=[master, beast, dummy],
        policies={dummy.id: _OneShot([_enemy_strike(beast)]),
                  beast.id: sv.BeastEffectPolicy("protection", beast, master)},
        max_rounds=1,
    )
    sch.run()
    assert sch.damage_by_source_target.get((dummy.id, beast.id)) is None
    assert len(sch.rng._values) == 0                    # both d20s consumed, no dmg rolled


# -- bless: +1d4 (rolled) to the beast's commanded strike → raises its to-hit ------

def test_bless_raises_the_beasts_to_hit_via_a_rolled_d4():
    # A commanded strike at +7 vs AC 16 with d20=8 totals 15 → a MISS without bless.
    # Bless's +1d4 (=4) lifts it to 19 → a HIT.  Isolates the rolled-modifier retarget
    # landing on the BEAST (substrate #1, target=ally).
    def run(with_bless):
        master = Entity(name="master", hp=60, base_stats={})
        beast = Entity(name="beast", hp=25, base_stats={"ac": 17, "attack_bonus": 7})
        dummy = Entity(name="dummy", hp=10**9, base_stats={"ac": 16})
        if with_bless:
            sv.BeastEffectPolicy("bless", beast, master).install()
        vals = [8, 4, 5, 3] if with_bless else [8, 5, 3]
        sch = Scheduler(
            rng=FakeRNG(vals),
            entities=[master, beast, dummy],
            policies={master.id: _OneShot([_beast_strike(beast, dummy)])},
            max_rounds=1,
        )
        sch.run()
        return sch.damage_by_source_target.get((beast.id, dummy.id))

    assert run(False) is None                           # miss without bless
    assert run(True) and run(True) > 0                  # hit once the +1d4 lands


# -- aid: +5 to the beast's HP maximum (DPR-inert install assertion) --------------

def test_aid_raises_the_beasts_hp_maximum_and_current():
    beast = sv.make_primal_companion(8)                 # HP 25
    master = Entity(name="master", hp=60, base_stats={})
    before_max, before_hp = beast.max_hp, beast.hp
    sv.BeastEffectPolicy("aid", beast, master).install()
    assert beast.max_hp == before_max + 5
    assert beast.hp == before_hp + 5


def test_beast_with_an_effect_policy_is_still_commanded_not_self_acting():
    # Registering a BeastEffectPolicy (for on_incoming_hit) must NOT make the beast act
    # on its own turn — it is still COMMANDED by the master (its decide returns []).
    bep = sv.BeastEffectPolicy("protection", Entity(name="b", hp=25, base_stats={}),
                               Entity(name="m", hp=60, base_stats={}))
    assert bep.decide(None) == []


# -- integration (make_silvertail_runner at L8) — directional, per-(source,target) --

def _l8_incoming(effect, seed, days=100):
    """Sum, over `days`, the enemy's damage to the beast and to the master."""
    runner, char, beast, dummy = sv.make_silvertail_runner(8, SeededRNG(seed),
                                                           beast_effect=effect)
    to_beast = to_master = 0
    for _ in range(days):
        r = runner.run_day()
        to_beast += r.damage_source_to(dummy.id, beast.id)
        to_master += r.damage_source_to(dummy.id, char.id)
    return to_beast, to_master


def test_l8_baseline_enemy_hits_the_beast_and_spares_the_master():
    to_beast, to_master = _l8_incoming(None, 11)
    assert to_beast > 0                                 # the enemy strikes the beast
    assert to_master == 0                               # no redirect → master untouched


def test_warding_bond_cuts_beast_damage_and_redirects_the_attack_share_to_master():
    base_beast, _ = _l8_incoming(None, 11)
    wb_beast, wb_master = _l8_incoming("warding_bond", 11)
    assert wb_beast < base_beast                        # +1 AC + resistance cut incoming
    # The redirect rides the attack-hit intercept seam (fraction 1.0 per hit — the exact
    # equality is unit-tested with FakeRNG above).  The realistic enemy also forces
    # SAVES on the beast, and warding-bond-on-saves is DEFERRED (no redirect of save/AoE
    # damage yet), so the master's redirected share is the ATTACK portion only — positive
    # but strictly less than the beast's total incoming.
    assert 0 < wb_master < wb_beast


def test_protection_cuts_the_beasts_incoming_below_baseline_without_redirect():
    base_beast, _ = _l8_incoming(None, 11)
    prot_beast, prot_master = _l8_incoming("protection", 11)
    assert prot_beast < base_beast                      # disadvantage cuts landed hits
    assert prot_master == 0                             # protection never redirects


def test_bless_raises_the_beasts_outgoing_dpr():
    def beast_out(effect, seed, days=100):
        runner, _char, beast, _dummy = sv.make_silvertail_runner(
            8, SeededRNG(seed), beast_effect=effect)
        return sum(runner.run_day().damage_by_source(beast.id) for _ in range(days))

    assert beast_out("bless", 9) > beast_out(None, 9)


def test_l8_beast_is_still_commanded_and_deals_damage_with_an_effect_active():
    # The beast keeps dealing its commanded Beast's-Strike DPR even while a passive
    # BeastEffectPolicy is attached for its defender rider.
    runner, _char, beast, dummy = sv.make_silvertail_runner(
        8, SeededRNG(2), beast_effect="protection")
    total = sum(runner.run_day().damage_source_to(beast.id, dummy.id) for _ in range(50))
    assert total > 0
