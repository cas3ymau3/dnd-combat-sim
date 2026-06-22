"""test_ranged_melee_gate.py — the melee/ranged range axis doing real runtime work.

The attack-taxonomy gate migration (attack_taxonomy.md, item 3) makes `range_`
(melee / ranged) gate the defender-side melee-only reactions — Fire-Shield thorns
and Flourish Parry — instead of silently assuming every incoming hit is melee.
The capability this unlocks is the first thing a REAL ranged attacker exercises:
its hit provokes NO thorns / NO parry, because those fire only on MELEE attacks.

Two levels of validation (validate-mechanism-not-build-value — we pin the
MECHANISM, not a DPR number):

  1. the BUILD gates read `ctx.range_` (Scion Fire Shield, War Angel Flourish
     Parry): a melee hit fires the reaction, a ranged hit does not, and an
     untagged (None) attacker is treated as melee for back-compat;
  2. the ENGINE threads `event.range_` → `IncomingAttackContext.range_`, so a
     real ranged-tagged attack delivered through the scheduler reaches the gate
     with the right range — a ranged attacker draws no thorns, a melee one does.
"""

from src.builds import starfire_scion as ss
from src.builds import war_angel as wa
from src.entity import Entity
from src.events import AttackRollEvent, DamageEvent, make_tick
from src.policy import (
    Choice,
    IncomingAttackContext,
    InterceptResponse,
    ReactiveDamageSpec,
)
from src.scheduler import Scheduler
from src.verbs import resolve_attack_roll


class FakeRNG:
    """Pops preloaded d20 / damage rolls; records (n, sides) per call."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _incoming(range_, *, hit_margin=0, resources=None):
    return IncomingAttackContext(
        defender=Entity(name="d", hp=10), attacker=Entity(name="a", hp=10),
        hit_margin=hit_margin, cost="action",
        resources=resources or {}, round_number=1, range_=range_,
    )


# ---------------------------------------------------------------------------
# (1a) Fire-Shield thorns gate on the REAL Scion policy
# ---------------------------------------------------------------------------

def _fire_shield_scion():
    char = ss.make_starfire_scion(15)
    policy = ss.StarfireScionPolicy(15, char, ss.make_training_dummy(15),
                                    fourth_level_spell="fire_shield")
    policy._fire_shield_active = True            # simulate the pre-cast install
    return policy


def test_fire_shield_thorns_fire_on_a_melee_hit():
    resp = _fire_shield_scion().on_incoming_hit(_incoming("melee"))
    assert resp is not None and resp.reactive_damage is not None
    assert resp.reactive_damage.damage_dice == ss.FIRE_SHIELD_THORNS_DICE


def test_fire_shield_thorns_do_not_fire_on_a_ranged_hit():
    # The capability the range axis unlocks: a ranged attacker takes no thorns.
    assert _fire_shield_scion().on_incoming_hit(_incoming("ranged")) is None


def test_fire_shield_thorns_treat_an_untagged_attacker_as_melee():
    # Back-compat: an attacker that did not tag a range (None) still provokes
    # thorns — every modelled attacker is melee unless it says otherwise.
    resp = _fire_shield_scion().on_incoming_hit(_incoming(None))
    assert resp is not None and resp.reactive_damage is not None


# ---------------------------------------------------------------------------
# (1b) Flourish Parry gate on the REAL War Angel policy
# ---------------------------------------------------------------------------

def _flourish_war_angel():
    # Level 14 carries Flourish Parry (cha_mod 5).
    policy = wa.WarAngelPolicy(14, Entity(name="foe", hp=10, base_stats={"ac": 10}))
    return policy


def test_flourish_parry_fires_on_a_melee_hit_it_would_flip():
    # hit_margin 0 < cha_mod 5 → the +CHA bump flips the hit, so the parry fires.
    resp = _flourish_war_angel().on_incoming_hit(_incoming("melee", hit_margin=0))
    assert resp is not None and resp.ac_bonus == 5


def test_flourish_parry_does_not_fire_on_a_ranged_hit():
    # Same flip-worthy margin, but a RANGED attack — Battle Master parry is
    # melee-only, so no reaction even though the bump would have flipped it.
    assert _flourish_war_angel().on_incoming_hit(_incoming("ranged", hit_margin=0)) is None


# ---------------------------------------------------------------------------
# (2) The ENGINE threads event.range_ → IncomingAttackContext.range_
# ---------------------------------------------------------------------------

class _MeleeOnlyThorns:
    """A bearer that reflects thorns ONLY on a melee incoming hit — it reads the
    range axis off the IncomingAttackContext (the engine-threaded value), the same
    gate the real Fire-Shield bearer uses.  Exercising it through the scheduler
    proves event.range_ reaches the defender's gate."""

    def decide(self, snapshot):
        return []

    def on_incoming_hit(self, ctx):
        if ctx.range_ == "ranged":
            return None
        return InterceptResponse(reactive_damage=ReactiveDamageSpec((2, 8), "fire"))


class _AttackOnce:
    """An enemy that swings once at its target, tagging the attack's range_."""

    def __init__(self, target, range_):
        self._target = target
        self._range = range_

    def decide(self, snapshot):
        if snapshot.resources.get("action", 0) < 1:
            return []
        return [Choice(action_type="attack", cost="action", target=self._target,
                       weapon_stat="attack_bonus", range_=self._range)]


def _run_one_swing(attacker_range):
    bearer = Entity(name="bearer", hp=60, base_stats={"ac": 17})
    enemy = Entity(name="enemy", hp=10_000,
                   base_stats={"attack_bonus": 10, "damage_dice": (1, 4), "damage_bonus": 0})
    sched = Scheduler(
        rng=FakeRNG([
            15,        # enemy d20 → 25 vs AC 17 → hits the bearer
            5, 5,      # thorns 2d8 → 10 (only rolled if thorns fire)
            2,         # enemy's own 1d4 → 2 to the bearer
        ]),
        entities=[bearer, enemy],
        policies={bearer.id: _MeleeOnlyThorns(), enemy.id: _AttackOnce(bearer, attacker_range)},
        max_rounds=1,
    )
    sched.run()
    return sum(sched.damage_received[enemy.id])      # thorns land in the enemy's column


def test_engine_threads_range_a_ranged_attacker_draws_no_thorns():
    # The melee attacker provokes 2d8 thorns (10); the ranged attacker provokes
    # none — proving event.range_ threads end-to-end to the defender's gate.
    assert _run_one_swing("melee") == 10
    assert _run_one_swing("ranged") == 0
