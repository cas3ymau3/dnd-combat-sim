"""test_ally_effects.py — substrate #7 / 7c ALLY-EFFECTS (the second 7c slice).

A `cast_effect` (or an intercept rider) whose target is an ALLY, on the multi-entity
foundation built in slice 1 (session 18).  Three effects, all verified against the
2024 rules text before modeling (per the per-feature ritual):

  - ALLY-BUFF RETARGET (Bless / Aid) — `cast_effect target=ally` lands the existing
    substrate-#1/#3/#4 payloads on the ALLY entity instead of the caster.  No engine
    change was needed: the scheduler's cast_effect branch already installs on
    `choice.target or actor`.

  - WARDING BOND (redirect) — "each time it takes damage, you take the same amount":
    the ally's on_incoming_hit returns a RedirectSpec; resolve_attack_roll threads it
    onto the DamageEvent and resolve_damage spawns a copy of the taken amount onto the
    caster.  Adding this is the trigger that refactored the on_incoming_hit positional
    3-tuple into a single InterceptResponse object (the session-12 engine-seam note).

  - PROTECTION fighting style (disadvantage) — a nearby shield-bearer imposes
    Disadvantage: modeled as a SECOND attack d20, flipping the hit to a miss if it now
    misses (distributionally exact — P(hit)^2 either way).

  - SANCTUARY (save-or-negate) — the ATTACKER makes a WIS save vs the caster's DC or
    loses the attack: a failed save flips the hit to a miss.

Validation framing matches the rest of the Scion work: consistency / sanity via
deterministic FakeRNG (engine seams) + directional DPR off the per-(source,target)
ledger (the Scion + synthetic-ally integration), NOT number-matching.
"""

import logging

from src.builds import starfire_scion as ss
from src.entity import Entity
from src.events import AttackRollEvent, DamageEvent, EventQueue, make_tick
from src.modifiers import Modifier
from src.policy import (
    Choice,
    InterceptResponse,
    NegateSaveSpec,
    RedirectSpec,
)
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.verbs import resolve_attack_roll, resolve_damage

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; records (n, sides) per call (the suite's standard
    deterministic stub).  d20 rolls and damage rolls both go through .roll."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _attacker(bonus=10):
    return Entity(name="enemy", hp=100,
                  base_stats={"attack_bonus": bonus, "damage_dice": (1, 6),
                              "damage_bonus": 0, "wis_save": 0})


def _defender(ac=10):
    return Entity(name="ally", hp=100, base_stats={"ac": ac})


def _attack(actor, target, rng, q, *, intercept, seq=2):
    return resolve_attack_roll(
        AttackRollEvent(tick=make_tick(1, 0, 1), actor=actor, target=target),
        rng, q, next_sequence=seq, intercept_decider=intercept,
    )


# ===========================================================================
# Ally-buff retarget — cast_effect target=ally lands the payload on the ally
# ===========================================================================

class _OneShotPolicy:
    def __init__(self, choices):
        self._choices = choices

    def decide(self, snapshot):
        return self._choices if snapshot.round_number == 1 else []


def test_cast_effect_target_ally_lands_the_payload_on_the_ally_not_the_caster():
    # Bless/Aid retargeted onto an ally: a modifier (#1) + a damage-type response
    # (#4) installed on the ALLY via one cast_effect with target=ally.  The engine
    # already routes the payload to `choice.target or actor`, so this is the
    # retarget seam working with no engine change — just a non-self target.
    caster = Entity(name="caster", hp=40, base_stats={"spell_save_dc": 16})
    ally = Entity(name="ally", hp=40, base_stats={"attack_bonus": 5, "ac": 12})
    cast = Choice(
        action_type="cast_effect",
        cost="action",
        target=ally,                       # ← the retarget: land on the ally
        effect_source="bless",
        duration="combat",
        modifiers=[Modifier(stat="attack_bonus", value=2, source="bless")],
        damage_response={"fire": "resistance"},
    )
    Scheduler(
        rng=SeededRNG(0),
        entities=[caster, ally],
        policies={caster.id: _OneShotPolicy([cast])},
        max_rounds=1,
    ).run()
    # The modifier + response landed on the ALLY ...
    assert ally.stat("attack_bonus") == 7                  # 5 + 2
    assert ally.damage_response_for("fire") == "resistance"
    # ... and NOT on the caster.
    assert caster.damage_response_for("fire") is None
    assert ally.remove_modifier("bless") == 1
    assert caster.remove_modifier("bless") == 0


# ===========================================================================
# Warding Bond — redirect a share of the ally's taken damage to the caster
# ===========================================================================

def test_warding_bond_threads_the_redirect_onto_the_damage_event():
    enemy, ally = _attacker(), _defender(ac=10)
    caster = Entity(name="caster", hp=100)
    q = EventQueue()
    redirect = RedirectSpec(target=caster, fraction=1.0)
    # d20=15 + 10 = 25 vs AC 10 → a clean hit; the intercept returns the redirect.
    _attack(enemy, ally, FakeRNG([15]), q,
            intercept=lambda m: InterceptResponse(redirect=redirect))
    dmg_ev = q.pop()
    assert isinstance(dmg_ev, DamageEvent)
    assert dmg_ev.redirect is redirect                     # threaded for damage time


def test_warding_bond_redirects_the_taken_amount_to_the_caster():
    enemy, ally = _attacker(), _defender(ac=10)
    caster = Entity(name="caster", hp=100)
    q = EventQueue()
    redirect = RedirectSpec(target=caster, fraction=1.0)
    # Resolve a 2d8+5 hit on the warded ally: ally takes 6+6+5 = 17; the caster
    # takes the SAME 17 (a spawned redirect copy attributed to the attacker).
    total, _ = resolve_damage(
        DamageEvent(tick=make_tick(1, 0, 2), actor=enemy, target=ally,
                    damage_dice=(2, 8), damage_bonus=5, redirect=redirect),
        FakeRNG([6, 6]), q, next_sequence=3,
    )
    assert total == 17
    redirect_ev = q.pop()
    assert redirect_ev.actor is enemy and redirect_ev.target is caster
    assert redirect_ev.redirect is None                    # never recurses
    rtotal, _ = resolve_damage(redirect_ev, FakeRNG([]), EventQueue(), 4)
    assert rtotal == 17


def test_warding_bond_redirect_respects_the_ally_resistance_and_fraction():
    # The ally takes resisted damage (2024 Warding Bond grants resistance), and the
    # caster takes the SAME post-resistance amount — redirect reads the final total.
    enemy = _attacker()
    ally = Entity(name="ally", hp=100, base_stats={"ac": 10},
                  damage_response={"fire": "resistance"})
    caster = Entity(name="caster", hp=100)
    q = EventQueue()
    total, _ = resolve_damage(
        DamageEvent(tick=make_tick(1, 0, 2), actor=enemy, target=ally,
                    damage_dice=(2, 8), damage_bonus=0, damage_type="fire",
                    redirect=RedirectSpec(target=caster, fraction=0.5)),
        FakeRNG([6, 6]), q, next_sequence=3,
    )
    assert total == 6                                      # 12 resisted → 6
    assert q.pop().damage_bonus == 3                       # int(6 * 0.5) redirected


# ===========================================================================
# Protection fighting style — impose disadvantage (re-roll, flip on a miss)
# ===========================================================================

def test_protection_flips_a_hit_when_the_disadvantage_reroll_misses():
    enemy, ally = _attacker(bonus=0), _defender(ac=12)
    q = EventQueue()
    # First d20=15 (hit by 3); the protector imposes disadvantage → second d20=5,
    # 5 < AC 12 → the hit flips to a miss (no DamageEvent).
    _attack(enemy, ally, FakeRNG([15, 5]), q,
            intercept=lambda m: InterceptResponse(impose_disadvantage=True))
    assert len(q) == 0


def test_protection_leaves_a_hit_when_the_disadvantage_reroll_also_hits():
    enemy, ally = _attacker(bonus=0), _defender(ac=12)
    q = EventQueue()
    # First d20=15 hit; second d20=18 >= AC 12 → the hit stands.
    _attack(enemy, ally, FakeRNG([15, 18]), q,
            intercept=lambda m: InterceptResponse(impose_disadvantage=True))
    assert len(q) == 1 and isinstance(q.pop(), DamageEvent)


def test_protection_disadvantage_downgrades_a_crit_unless_both_dice_are_20():
    enemy, ally = _attacker(bonus=0), _defender(ac=12)
    q = EventQueue()
    # First d20=20 (a crit); the surviving second d20=18 is not a 20 → keep the hit
    # but drop the crit (true disadvantage crits only on a double-20).
    _attack(enemy, ally, FakeRNG([20, 18]), q,
            intercept=lambda m: InterceptResponse(impose_disadvantage=True))
    ev = q.pop()
    assert isinstance(ev, DamageEvent) and ev.is_crit is False


# ===========================================================================
# Sanctuary — the ATTACKER saves or the attack is negated
# ===========================================================================

def test_sanctuary_negates_the_attack_when_the_attacker_fails_the_save():
    enemy, ally = _attacker(bonus=10), _defender(ac=10)
    q = EventQueue()
    # Attack d20=15 hits; the attacker's WIS save d20=3 (+0) = 3 < DC 15 → FAIL →
    # the attack is negated (no DamageEvent).
    _attack(enemy, ally, FakeRNG([15, 3]), q,
            intercept=lambda m: InterceptResponse(
                negate_save=NegateSaveSpec(save_stat="wis_save", dc=15)))
    assert len(q) == 0


def test_sanctuary_lets_the_attack_through_when_the_attacker_saves():
    enemy, ally = _attacker(bonus=10), _defender(ac=10)
    q = EventQueue()
    # Attack d20=15 hits; the attacker's WIS save d20=18 >= DC 15 → PASS → the attack
    # proceeds normally.
    _attack(enemy, ally, FakeRNG([15, 18]), q,
            intercept=lambda m: InterceptResponse(
                negate_save=NegateSaveSpec(save_stat="wis_save", dc=15)))
    assert len(q) == 1 and isinstance(q.pop(), DamageEvent)


# ===========================================================================
# Integration — Scion + synthetic ally via make_ally_effects_runner
# ===========================================================================

def _ally_damage_total(effect, n_days=40, seed=0):
    """Sum of enemy→ally damage over many days — a robust directional metric
    (protection/sanctuary perturb the RNG stream, so a single day is not a clean
    controlled comparison; the sum over a long run is)."""
    runner, _char, ally, dummy = ss.make_ally_effects_runner(15, SeededRNG(seed), effect)
    return sum(runner.run_day().damage_source_to(dummy.id, ally.id)
               for _ in range(n_days))


def test_warding_bond_integration_redirects_the_full_share_to_the_caster():
    runner, char, ally, dummy = ss.make_ally_effects_runner(15, SeededRNG(0), "warding_bond")
    result = runner.run_day()
    to_ally = result.damage_source_to(dummy.id, ally.id)
    to_caster = result.damage_source_to(dummy.id, char.id)
    assert to_ally > 0                                     # the enemy hit the ally
    assert to_caster == to_ally                            # fraction 1.0 → same total
    # The +1 AC retarget (#1) landed on the ally.
    assert ally.stat("ac") == ss.LEVELS[15]["char_ac"] + 1


def test_protection_integration_reduces_incoming_damage_to_the_ally():
    assert _ally_damage_total("protection") < _ally_damage_total(None)


def test_sanctuary_integration_reduces_incoming_damage_to_the_ally():
    assert _ally_damage_total("sanctuary") < _ally_damage_total(None)


def test_no_effect_baseline_takes_full_damage_and_does_not_redirect():
    # The effect=None baseline: the ally has no rider, so attacks land in full and
    # nothing is redirected to the caster (the control for the two tests above).
    runner, char, ally, dummy = ss.make_ally_effects_runner(15, SeededRNG(0), None)
    result = runner.run_day()
    assert result.damage_source_to(dummy.id, ally.id) > 0
    assert result.damage_source_to(dummy.id, char.id) == 0
