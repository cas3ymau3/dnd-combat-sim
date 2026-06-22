"""test_outgoing_riders.py — substrate #6 (outgoing predicate riders): the on_hit
seam that spawns SEPARATELY-TYPED rider DamageEvents (Fount of Moonlight's +2d6
radiant, Primal Strike's +1d8 elemental), the engine half of the build work.

Engine-level contract (consistency, NOT number-matching):
  - a rider spec spawns its OWN DamageEvent (NOT folded into the weapon hit), with
    its own damage_dice / damage_type / origin / Elemental-Adept flags;
  - rider dice double on a crit;
  - the rider routes through the target's per-type damage response (#4), and its
    own ignore_resistance / min_die ride along;
  - extra_damage_dice (smite/bluff style) still fold into the weapon hit (the War
    Angel path is unchanged) — the two mechanisms are independent.

The on_hit GATING (FoM melee-only, Primal weapon/unarmed once-per-turn) lives in
the build policy and is covered in test_starfire_scion.py; here we exercise the
generic verb contract with hand-built hit_deciders.
"""

import logging

from src.entity import Entity
from src.events import AttackRollEvent, DamageEvent, EventQueue, make_tick
from src.policy import RiderDamageSpec
from src.verbs import resolve_attack_roll, resolve_damage

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; records (n, sides) per call."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _attacker():
    return Entity(name="a", hp=10,
                  base_stats={"attack_bonus": 10, "damage_dice": (1, 8), "damage_bonus": 3})


def _target(ac=10, resp=None):
    return Entity(name="t", hp=10**9, base_stats={"ac": ac}, damage_response=resp)


def _drain(q):
    out = []
    while len(q):
        out.append(q.pop())
    return out


def _hit_with_riders(d20, riders, target=None):
    """Resolve one weapon hit whose hit_decider returns the given rider specs.
    Returns (queue, attacker, target).  resolve_attack_roll rolls only the d20 —
    the spawned DamageEvents are left unresolved for inspection."""
    q = EventQueue()
    a = _attacker()
    t = target if target is not None else _target()
    ev = AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=t)

    def hit_decider(is_crit):
        return [], [], list(riders)

    resolve_attack_roll(ev, FakeRNG([d20]), q, next_sequence=2, hit_decider=hit_decider)
    return q, a, t


# ---------------------------------------------------------------------------
# A rider spawns its OWN typed DamageEvent (not folded into the weapon hit)
# ---------------------------------------------------------------------------

def test_rider_spawns_a_separate_typed_damage_event():
    q, a, t = _hit_with_riders(
        15, [RiderDamageSpec(damage_dice=(2, 6), damage_type="radiant", origin="spell")])
    dmgs = [e for e in _drain(q) if isinstance(e, DamageEvent)]
    # main weapon DamageEvent (pushed first, lower sequence) + the rider event
    assert len(dmgs) == 2
    main, rider = dmgs[0], dmgs[1]
    # the weapon hit is untouched — the rider did NOT fold into it
    assert main.damage_dice == (1, 8) and main.damage_type is None and main.origin is None
    # the rider carries its OWN type / origin / dice
    assert rider.damage_dice == (2, 6) and rider.damage_type == "radiant"
    assert rider.origin == "spell" and rider.damage_bonus == 0


def test_multiple_riders_each_spawn_their_own_event_after_the_weapon_hit():
    q, a, t = _hit_with_riders(15, [
        RiderDamageSpec(damage_dice=(2, 6), damage_type="radiant", origin="spell"),
        RiderDamageSpec(damage_dice=(1, 8), damage_type="fire", origin="feature"),
    ])
    dmgs = [e for e in _drain(q) if isinstance(e, DamageEvent)]
    assert len(dmgs) == 3
    assert dmgs[0].damage_type is None                 # weapon hit first
    assert [d.damage_type for d in dmgs[1:]] == ["radiant", "fire"]


# ---------------------------------------------------------------------------
# Crit doubling + per-type response (#4) ride the rider event
# ---------------------------------------------------------------------------

def test_rider_dice_double_on_a_crit():
    q, a, t = _hit_with_riders(20, [RiderDamageSpec(damage_dice=(1, 8), damage_type="fire")])
    rider = [e for e in _drain(q) if isinstance(e, DamageEvent)][-1]
    assert rider.is_crit is True
    rng = FakeRNG([4, 5])
    total, _ = resolve_damage(rider, rng, EventQueue(), 9)
    assert rng.roll_calls[0] == (2, 8)                 # 1d8 doubled to 2d8 by the crit
    assert total == 9


def test_rider_routes_through_target_resistance_and_ignore_resistance_bypasses():
    # A fire-resistant target HALVES a fire rider...
    q, _, _ = _hit_with_riders(
        15, [RiderDamageSpec(damage_dice=(2, 8), damage_type="fire")],
        target=_target(resp={"fire": "resistance"}))
    rider = [e for e in _drain(q) if isinstance(e, DamageEvent)][-1]
    total, _ = resolve_damage(rider, FakeRNG([5, 5]), EventQueue(), 9)
    assert total == 5                                  # (5+5) halved by resistance
    # ...unless the rider carries ignore_resistance (Elemental Adept treatment).
    q2, _, _ = _hit_with_riders(
        15, [RiderDamageSpec(damage_dice=(2, 8), damage_type="fire", ignore_resistance=True)],
        target=_target(resp={"fire": "resistance"}))
    rider2 = [e for e in _drain(q2) if isinstance(e, DamageEvent)][-1]
    total2, _ = resolve_damage(rider2, FakeRNG([5, 5]), EventQueue(), 9)
    assert total2 == 10                                # resistance bypassed


def test_rider_min_die_floors_each_die():
    q, _, _ = _hit_with_riders(
        15, [RiderDamageSpec(damage_dice=(2, 8), damage_type="fire", min_die=2)])
    rider = [e for e in _drain(q) if isinstance(e, DamageEvent)][-1]
    total, _ = resolve_damage(rider, FakeRNG([1, 1]), EventQueue(), 9)
    assert total == 4                                  # both 1s floored to 2


# ---------------------------------------------------------------------------
# The smite-style extra_damage_dice path is independent and unchanged
# ---------------------------------------------------------------------------

def test_extra_damage_dice_still_fold_into_the_weapon_hit():
    q = EventQueue()
    a, t = _attacker(), _target()
    ev = AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=t)

    def hit_decider(is_crit):
        return [(1, 6)], [], []                        # smite dice, NO riders

    resolve_attack_roll(ev, FakeRNG([15]), q, next_sequence=2, hit_decider=hit_decider)
    dmgs = [e for e in _drain(q) if isinstance(e, DamageEvent)]
    assert len(dmgs) == 1                              # folded — no separate event
    assert dmgs[0].extra_damage_dice == [(1, 6)]


def test_no_rider_no_extra_event():
    q, _, _ = _hit_with_riders(15, [])                 # on_hit declined everything
    dmgs = [e for e in _drain(q) if isinstance(e, DamageEvent)]
    assert len(dmgs) == 1                              # only the weapon hit
