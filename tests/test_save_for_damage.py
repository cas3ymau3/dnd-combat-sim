"""test_save_for_damage.py — engine primitive #1 for the Starfire Scion:
`spell_save_dc` on the attacker + a save-FOR-damage resolution path.

The mirror of an attack roll: the TARGET rolls a saving throw vs the caster's
spell save DC, and the result determines damage.  Two modes:
  - save NEGATES (Sacred Flame): full on a failed save, nothing on a success.
  - save FOR HALF (Burning Hands): full on a fail, half (rounded down) on a save.

Validation framing (PROGRESS "STARFIRE SCION"): consistency + sanity, NOT
number-matching.  We check the per-save DAMAGE MATH exactly (deterministic
FakeRNG), then a Monte-Carlo SANITY check that the mean damage is the analytic
fail-rate fraction of the all-hit ceiling at the L1 and L5 data points.
"""

import logging

from src.entity import Entity
from src.events import DamageEvent, EventQueue, SaveDamageEvent
from src.policy import Choice, GameState
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.verbs import resolve_damage, resolve_save_damage

logging.disable(logging.CRITICAL)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeRNG:
    """Pops preloaded values; records (n, sides) per call.  Same shape as the
    stub in test_flourish_parry.py."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _caster(dc: int) -> Entity:
    return Entity(name="Scion", hp=50, base_stats={"spell_save_dc": dc})


def _enemy(dex_save: int) -> Entity:
    return Entity(name="Target", hp=10_000, base_stats={"dex_save": dex_save})


def _resolve_one_cast(caster, enemy, dice, on_save, rng) -> int:
    """Run one save-for-damage cast end to end (save → spawned DamageEvent) and
    return the damage dealt (0 if the save negated it)."""
    q = EventQueue()
    ev = SaveDamageEvent(
        tick=(1, 0, 1), actor=caster, target=enemy,
        save_stat="dex_save", damage_dice=dice, on_save=on_save,
    )
    resolve_save_damage(ev, rng, q, 2)
    if len(q) == 0:
        return 0
    dmg_ev = q.pop()
    total, _ = resolve_damage(dmg_ev, rng, q, 3)
    return total


# ---------------------------------------------------------------------------
# Mechanics — save NEGATES (Sacred Flame)
# ---------------------------------------------------------------------------

def test_failed_save_deals_full_damage():
    caster, enemy = _caster(13), _enemy(1)
    # save d20=5 → 5+1=6 < 13 FAIL; then 1d8 rolls 7.
    dmg = _resolve_one_cast(caster, enemy, (1, 8), "none", FakeRNG([5, 7]))
    assert dmg == 7


def test_made_save_negates_no_damage_event():
    caster, enemy = _caster(13), _enemy(1)
    q = EventQueue()
    ev = SaveDamageEvent(
        tick=(1, 0, 1), actor=caster, target=enemy,
        save_stat="dex_save", damage_dice=(1, 8), on_save="none",
    )
    # save d20=20 → 21 >= 13 PASS; negates → no DamageEvent enqueued.
    next_seq = resolve_save_damage(ev, FakeRNG([20]), q, 2)
    assert len(q) == 0
    assert next_seq == 2  # unchanged — nothing pushed


# ---------------------------------------------------------------------------
# Mechanics — save FOR HALF (Burning Hands)
# ---------------------------------------------------------------------------

def test_made_save_for_half_deals_half_rounded_down():
    caster, enemy = _caster(13), _enemy(1)
    # save d20=20 PASS; 3d6 rolls [4,4,4]=12; half → 6.
    dmg = _resolve_one_cast(caster, enemy, (3, 6), "half", FakeRNG([20, 4, 4, 4]))
    assert dmg == 6


def test_failed_save_for_half_deals_full():
    caster, enemy = _caster(13), _enemy(1)
    # save d20=1 → 1+1=2 < 13 FAIL (saves do NOT auto-fail on a nat 1); full 12.
    dmg = _resolve_one_cast(caster, enemy, (3, 6), "half", FakeRNG([1, 4, 4, 4]))
    assert dmg == 12


def test_half_rounds_down_to_floor():
    caster, enemy = _caster(13), _enemy(1)
    # save PASS; 1d8 rolls 7; half of 7 → 3 (rounded down).
    dmg = _resolve_one_cast(caster, enemy, (1, 8), "half", FakeRNG([20, 7]))
    assert dmg == 3


def test_damage_event_halved_flag_directly():
    """The halving lives in resolve_damage (phase 6), inert unless halved=True."""
    enemy = _enemy(1)
    q = EventQueue()
    ev = DamageEvent(
        tick=(1, 0, 1), actor=_caster(13), target=enemy,
        damage_dice=(2, 8), halved=True,
    )
    total, _ = resolve_damage(ev, FakeRNG([8, 8]), q, 2)
    assert total == 8  # 16 // 2


# ---------------------------------------------------------------------------
# Telemetry (design §8: saves forced / failed)
# ---------------------------------------------------------------------------

def test_save_telemetry_counts_made_and_failed():
    caster, enemy = _caster(13), _enemy(1)
    _resolve_one_cast(caster, enemy, (1, 8), "none", FakeRNG([5, 7]))   # fail
    _resolve_one_cast(caster, enemy, (1, 8), "none", FakeRNG([20]))     # pass
    assert enemy.saving_throws_made == 2
    assert enemy.saving_throws_failed == 1


# ---------------------------------------------------------------------------
# Scheduler integration — a save_spell Choice flows end to end
# ---------------------------------------------------------------------------

class _SaveSpellPolicy:
    """Minimal policy: cast one Sacred Flame (save_spell) at the target on round 1."""

    def __init__(self, target):
        self._target = target

    def decide(self, snapshot: GameState):
        if snapshot.resources.get("action", 0) < 1:
            return []
        return [Choice(
            action_type="save_spell",
            cost="action",
            target=self._target,
            save_stat="dex_save",
            damage_dice=(1, 8),
            on_save="none",
        )]


def test_scheduler_runs_save_spell_failed_save():
    caster, enemy = _caster(13), _enemy(1)
    sched = Scheduler(
        rng=FakeRNG([3, 6]),       # save d20=3 (fail), then 1d8=6
        entities=[caster, enemy],  # enemy has no policy → takes no turn
        policies={caster.id: _SaveSpellPolicy(enemy)},
        max_rounds=1,
    )
    log = sched.run()
    assert sum(log) == 6
    assert enemy.saving_throws_made == 1
    assert enemy.saving_throws_failed == 1


def test_scheduler_runs_save_spell_made_save_no_damage():
    caster, enemy = _caster(13), _enemy(1)
    sched = Scheduler(
        rng=FakeRNG([20]),         # save d20=20 → negated, no damage roll
        entities=[caster, enemy],
        policies={caster.id: _SaveSpellPolicy(enemy)},
        max_rounds=1,
    )
    log = sched.run()
    assert sum(log) == 0
    assert enemy.saving_throws_made == 1
    assert enemy.saving_throws_failed == 0


# ---------------------------------------------------------------------------
# Monte-Carlo SANITY — mean damage = fail-rate fraction of the all-hit ceiling
# ---------------------------------------------------------------------------

def _monte_carlo(dc, dex_save, dice, on_save, n):
    """Return (empirical_fail_rate, mean_damage) over n independent casts."""
    total_dmg = 0
    fails = 0
    for s in range(n):
        caster, enemy = _caster(dc), _enemy(dex_save)
        rng = SeededRNG(s)
        dmg = _resolve_one_cast(caster, enemy, dice, on_save, rng)
        total_dmg += dmg
        fails += enemy.saving_throws_failed
    return fails / n, total_dmg / n


def test_sacred_flame_l1_sanity():
    """L1 (LEVELS data): DC 13, enemy DEX +1, 1d8.  P(fail)=11/20=0.55;
    ceiling (all-fail) = E[1d8]=4.5; mean ≈ 0.55*4.5 = 2.475."""
    n = 20_000
    rate, mean = _monte_carlo(dc=13, dex_save=1, dice=(1, 8), on_save="none", n=n)
    assert abs(rate - 0.55) < 0.02            # fail-rate matches the d20 math
    assert mean < 4.5                          # below the all-hit ceiling
    assert abs(mean - 0.55 * 4.5) < 0.2        # = fail-rate fraction of ceiling


def test_sacred_flame_l5_sanity():
    """L5 Sacred Flame shape: DC 15 (8+PB3+WIS4), enemy DEX +2, 2d8 (cantrip
    scaling — the dice are fed in; data-driven scaling is primitive #2).
    P(fail)=12/20=0.60; ceiling = E[2d8]=9.0; mean ≈ 0.60*9.0 = 5.4."""
    n = 20_000
    rate, mean = _monte_carlo(dc=15, dex_save=2, dice=(2, 8), on_save="none", n=n)
    assert abs(rate - 0.60) < 0.02
    assert mean < 9.0
    assert abs(mean - 0.60 * 9.0) < 0.3


def test_dpr_grows_with_cantrip_scaling():
    """Sanity: 2d8 Sacred Flame out-damages 1d8 at the same hit/save profile
    (monotonic growth up the ladder — the consistency check, not a target)."""
    n = 8_000
    _, mean_1d8 = _monte_carlo(dc=15, dex_save=2, dice=(1, 8), on_save="none", n=n)
    _, mean_2d8 = _monte_carlo(dc=15, dex_save=2, dice=(2, 8), on_save="none", n=n)
    assert mean_2d8 > mean_1d8
