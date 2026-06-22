"""test_fueled_spellfire.py — Fueled Spellfire (Starfire Scion L5; engine
primitive #5): a CASTER-side post-damage decision point.

×1/turn, when a SPELL the caster casts deals RADIANT damage, expend up to 2 Hit
Dice (d8) and add them to that damage roll.  Built as a general radiant rider
hooked on the DamageEvent — the single chokepoint BOTH delivery paths funnel
through — so it covers the attack-roll path (Guiding Bolt) and the
save-for-damage path (Sacred Flame) with one hook (and future radiant spells for
free).

Validation framing (PROGRESS "STARFIRE SCION"): consistency + sanity, NOT
number-matching.  We pin:
  - the rider MATH exactly (deterministic FakeRNG): dice added, NOT crit-doubled,
    shared with save-for-half halving, inert when no rider is offered;
  - the POLICY gating (spell + radiant only; Archer's radiant feature excluded;
    1/turn; budget binds; off below L5);
  - the scheduler closure consults the CASTER's policy and consumes Hit Dice;
  - end to end: fuel lifts L5 DPR, drains the Hit-Dice pool, stays a plausible
    fraction of the (no-fuel) ceiling.
"""

import logging

import pytest

from src.builds import starfire_scion as ss
from src.entity import Entity
from src.events import DamageEvent, EventQueue
from src.policy import DamageRiderResponse, DealDamageContext, GameState
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.verbs import resolve_damage

logging.disable(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeRNG:
    """Pops preloaded values; records (n, sides) per call (same shape as the
    stub in test_starfire_scion.py / test_save_for_damage.py)."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _damage(dice, rng, *, is_crit=False, halved=False, damage_type="radiant",
            origin="spell", bonus=0, rider_decider=None):
    """Resolve one DamageEvent and return the total dealt to a dummy target."""
    actor = Entity(name="caster", hp=20)
    target = Entity(name="t", hp=10_000)
    ev = DamageEvent(
        tick=(1, 0, 1), actor=actor, target=target,
        is_crit=is_crit, damage_dice=dice, damage_bonus=bonus,
        halved=halved, damage_type=damage_type, origin=origin,
    )
    total, _ = resolve_damage(ev, rng, EventQueue(), 2, None, rider_decider)
    return total


def _ctx(damage_type="radiant", origin="spell", hit_dice=5, round_=1, turn=0,
         is_crit=False):
    return DealDamageContext(
        actor=Entity(name="c", hp=10), target=Entity(name="t", hp=10),
        damage_type=damage_type, origin=origin, is_crit=is_crit,
        base_damage_dice=(4, 6),
        resources={"hit_dice": hit_dice}, round_number=round_, turn_index=turn,
    )


def _l5_policy():
    char = ss.make_starfire_scion(5)
    return ss.StarfireScionPolicy(5, char, ss.make_training_dummy(5)), char


# ---------------------------------------------------------------------------
# Engine: the rider math in resolve_damage
# ---------------------------------------------------------------------------

def test_rider_dice_are_rolled_and_added_to_the_damage():
    """A radiant spell hit + a rider of 2d8: Guiding Bolt 4d6 (all 5) = 20, plus
    fueled 2d8 (both 8) = 16 → 36."""
    rng = FakeRNG([5, 5, 5, 5, 8, 8])
    total = _damage((4, 6), rng, rider_decider=lambda dt, isp, ic: [(2, 8)])
    assert total == 36
    assert (4, 6) in rng.roll_calls and (2, 8) in rng.roll_calls


def test_rider_dice_are_not_crit_doubled():
    """On a crit the SPELL's dice double (4d6 → 8d6) but the rider Hit Dice do
    NOT — they are a fixed expenditure, rolled once as 2d8 (design decision)."""
    rng = FakeRNG([6, 6, 6, 6, 6, 6, 6, 6, 8, 8])   # 8d6=48 + 2d8=16
    total = _damage((4, 6), rng, is_crit=True,
                    rider_decider=lambda dt, isp, ic: [(2, 8)])
    assert total == 64
    # The rider rolled exactly 2 dice, not 4 — proving it did not double.
    assert (2, 8) in rng.roll_calls and (4, 8) not in rng.roll_calls


def test_rider_shares_save_for_half_halving():
    """A save-for-half spell halves the post-bonus total INCLUDING the rider:
    (4d6=24 + rider 2d8=16) = 40, halved → 20."""
    rng = FakeRNG([6, 6, 6, 6, 8, 8])
    total = _damage((4, 6), rng, halved=True,
                    rider_decider=lambda dt, isp, ic: [(2, 8)])
    assert total == 20


def test_decider_receiving_empty_list_adds_nothing():
    """A rider_decider that declines (returns []) draws no extra dice."""
    rng = FakeRNG([5, 5, 5, 5])
    total = _damage((4, 6), rng, rider_decider=lambda dt, isp, ic: [])
    assert total == 20 and rng.roll_calls == [(4, 6)]


def test_no_rider_decider_is_inert():
    """Backward-compat: no rider_decider → identical to before (no extra draw)."""
    rng = FakeRNG([5, 5, 5, 5])
    total = _damage((4, 6), rng, rider_decider=None)
    assert total == 20 and rng.roll_calls == [(4, 6)]


# ---------------------------------------------------------------------------
# Policy: on_deal_damage gating (Fueled Spellfire)
# ---------------------------------------------------------------------------

def test_fuels_radiant_spell_damage_up_to_two_hit_dice():
    policy, _ = _l5_policy()
    resp = policy.on_deal_damage(_ctx(hit_dice=5))
    assert resp == DamageRiderResponse(extra_damage_dice=[(2, 8)],
                                       resource_cost={"hit_dice": 2})


def test_fuels_with_one_hit_die_when_only_one_remains():
    policy, _ = _l5_policy()
    resp = policy.on_deal_damage(_ctx(hit_dice=1))
    assert resp == DamageRiderResponse(extra_damage_dice=[(1, 8)],
                                       resource_cost={"hit_dice": 1})


def test_does_not_fuel_when_no_hit_dice_remain():
    policy, _ = _l5_policy()
    assert policy.on_deal_damage(_ctx(hit_dice=0)) is None


def test_does_not_fuel_a_radiant_feature_only_a_spell():
    """Starry-Form Archer deals RADIANT damage but is a FEATURE, not a spell —
    origin="feature" must exclude it (the whole reason origin is threaded)."""
    policy, _ = _l5_policy()
    assert policy.on_deal_damage(_ctx(damage_type="radiant", origin="feature")) is None


def test_does_not_fuel_non_radiant_spell_damage():
    policy, _ = _l5_policy()
    assert policy.on_deal_damage(_ctx(damage_type="fire", origin="spell")) is None
    assert policy.on_deal_damage(_ctx(damage_type=None, origin="weapon")) is None


def test_once_per_turn():
    """A turn dealing radiant damage twice (Guiding Bolt + Sacred Flame) fuels
    only the first; a later turn fuels again."""
    policy, _ = _l5_policy()
    assert policy.on_deal_damage(_ctx(round_=1, turn=0)) is not None   # 1st this turn
    assert policy.on_deal_damage(_ctx(round_=1, turn=0)) is None       # 2nd this turn
    assert policy.on_deal_damage(_ctx(round_=2, turn=0)) is not None   # next turn


def test_per_combat_reset_clears_the_turn_gate():
    """on_combat_start clears the 1/turn gate (round numbers restart per combat)."""
    policy, _ = _l5_policy()
    assert policy.on_deal_damage(_ctx(round_=1, turn=0)) is not None
    assert policy.on_deal_damage(_ctx(round_=1, turn=0)) is None
    policy.on_combat_start(1, SeededRNG(0))
    assert policy.on_deal_damage(_ctx(round_=1, turn=0)) is not None


def test_off_below_level_5():
    """Fueled Spellfire is a L5 feat — the L4 policy has no Hit-Dice pool and the
    hook declines even on radiant spell damage."""
    char = ss.make_starfire_scion(4)
    policy = ss.StarfireScionPolicy(4, char, ss.make_training_dummy(4))
    assert not policy._fueled_spellfire
    assert policy.on_deal_damage(_ctx(hit_dice=0)) is None


# ---------------------------------------------------------------------------
# Scheduler closure: consults the CASTER's policy and consumes Hit Dice
# ---------------------------------------------------------------------------

def test_scheduler_closure_consumes_hit_dice():
    """_make_deal_damage_decider consults the actor's on_deal_damage and consumes
    the Hit Dice it commits to; the returned dice are what the verb rolls."""
    policy, char = _l5_policy()
    sched = Scheduler(rng=SeededRNG(0), entities=[char],
                      policies={char.id: policy}, max_rounds=1)
    ev = DamageEvent(tick=(1, 0, 1), actor=char, target=Entity(name="t", hp=10),
                     damage_dice=(4, 6), damage_type="radiant", origin="spell")
    decider = sched._make_deal_damage_decider(ev)
    assert char.resources.available("hit_dice") == 5
    dice = decider("radiant", "spell", False)
    assert dice == [(2, 8)]
    assert char.resources.available("hit_dice") == 3   # 2 consumed


def test_scheduler_closure_is_none_without_the_hook():
    """An actor whose policy has no on_deal_damage (the dummy) gets no decider —
    so every existing build is bit-identical (no rider, no RNG draw)."""
    dummy = ss.make_training_dummy(5)
    sched = Scheduler(rng=SeededRNG(0), entities=[dummy], policies={}, max_rounds=1)
    ev = DamageEvent(tick=(1, 0, 1), actor=dummy, target=None,
                     damage_dice=(1, 6), damage_type="radiant", origin="spell")
    assert sched._make_deal_damage_decider(ev) is None


# ---------------------------------------------------------------------------
# End to end: fuel lifts DPR, drains the pool, stays under the ceiling
# ---------------------------------------------------------------------------

def _mean_dpr(level, n_days, seed=0, rounds_per_combat=4, disable_fuel=False):
    rng = SeededRNG(seed)
    runner, char, dummy = ss.make_day_runner(level, rng, rounds_per_combat)
    if disable_fuel:
        runner.policies[char.id]._fueled_spellfire = False
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_fuel_increases_l5_dpr():
    """Fueling radiant spells with Hit Dice must raise mean DPR vs the same build
    with Fueled Spellfire switched off."""
    with_fuel = _mean_dpr(5, n_days=600)
    without_fuel = _mean_dpr(5, n_days=600, disable_fuel=True)
    assert with_fuel > without_fuel


def test_fuel_drains_the_hit_dice_pool_over_a_day():
    """The build's concept is to spend ALL Hit Dice on radiant spell damage; over
    a full day (≥1 hit lands) the pool should be substantially drained."""
    rng = SeededRNG(0)
    runner, char, _ = ss.make_day_runner(5, rng)
    runner.run_day()
    assert char.resources.available("hit_dice") < 5


def test_l5_with_fuel_stays_under_the_no_fuel_ceiling():
    """Even fueled, L5 DPR is a plausible fraction of the all-hit ceiling (the
    ceiling assumes every attack hits / every save fails, with no fuel — the
    fuel's ~1.4 DPR contribution does not breach it)."""
    dpr = _mean_dpr(5, n_days=400)
    assert 0 < dpr < ss.LEVELS[5]["ceiling_dpr"]
