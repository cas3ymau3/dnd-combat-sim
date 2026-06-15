"""test_incoming_damage_thorns.py — substrates #4 (incoming-damage response) and
#5 (defender-side thorns rider), plus the Starfire Scion enemy-strikes-back loop.

See design/buff_primitive.md (registry rows 4 + 5).  Validation framing matches
the rest of the Scion work: consistency / sanity via deterministic FakeRNG, NOT
number-matching.  Specifically:

  #4  resolve_damage applies the DEFENDER's damage-type response after all other
      modifiers (2024 RAW): resistance halves (rounded down), vulnerability
      doubles, immunity zeroes; only the matching type; resistance+vulnerability
      cancel; an untyped hit is unaffected.  Real consumer: a fire-resistant
      enemy halves the Scion's Searing Arc (fire) but not Guiding Bolt (radiant)
      — the substrate the deferred Elemental Adept fire-bypass will toggle.  Also
      installable/sweepable via cast_effect (Fire Shield's resist-cold/fire).

  #5  on a LANDED melee hit the bearer deals automatic thorns damage to the
      attacker (no roll), routed as a DamageEvent bearer→attacker so it (a) runs
      through the attacker's own #4 response and (b) counts as the bearer's
      outgoing DPR.  Suppressed when the hit is parried to a miss.

  loop  ScriptedEnemyPolicy strikes the character (structurally identical to War
      Angel's enemy), wired in make_day_runner on an enemy_attack row — the loop
      that makes #4/#5 do real work.  DPR still reads the dummy's column, so the
      enemy's own damage to the character never pollutes it.
"""

import logging

from src.builds import starfire_scion as ss
from src.content import interpret_save_spell
from src.entity import Entity
from src.events import AttackRollEvent, DamageEvent, EventQueue, make_tick
from src.policy import (
    Choice,
    GameState,
    InterceptResponse,
    ReactiveDamageSpec,
)
from src.resources import ResourceEntry, ResourcePool
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.verbs import resolve_attack_roll, resolve_damage

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; records (n, sides) per call (the suite's standard
    deterministic stub)."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _resolve_damage_to(target, dice, rolls, *, damage_type, halved=False, bonus=0):
    """Resolve one DamageEvent against *target* and return the total dealt."""
    ev = DamageEvent(
        tick=(1, 0, 1),
        actor=Entity(name="src", hp=10),
        target=target,
        is_crit=False,
        damage_dice=dice,
        damage_bonus=bonus,
        halved=halved,
        damage_type=damage_type,
        is_spell=False,
    )
    total, _ = resolve_damage(ev, FakeRNG(rolls), EventQueue(), 2)
    return total


# ===========================================================================
# #4 — incoming-damage response in resolve_damage (resistance/vuln/immunity)
# ===========================================================================

def test_resistance_halves_matching_type():
    # 4d6 = [6,6,6,5] = 23; fire-resistant target → 23 // 2 = 11 (rounded down).
    target = Entity(name="t", hp=10_000, damage_response={"fire": "resistance"})
    assert _resolve_damage_to(target, (4, 6), [6, 6, 6, 5], damage_type="fire") == 11


def test_resistance_applies_only_to_the_matching_type():
    # Same fire-resistant target, but RADIANT damage → untouched (23).
    target = Entity(name="t", hp=10_000, damage_response={"fire": "resistance"})
    assert _resolve_damage_to(target, (4, 6), [6, 6, 6, 5], damage_type="radiant") == 23


def test_immunity_zeroes():
    target = Entity(name="t", hp=10_000, damage_response={"fire": "immunity"})
    assert _resolve_damage_to(target, (4, 6), [6, 6, 6, 5], damage_type="fire") == 0


def test_vulnerability_doubles():
    target = Entity(name="t", hp=10_000, damage_response={"cold": "vulnerability"})
    assert _resolve_damage_to(target, (2, 8), [3, 4], damage_type="cold") == 14  # 7*2


def test_resistance_and_vulnerability_cancel():
    # 2024 RAW: same-type resistance + vulnerability net to no change.
    target = Entity(
        name="t", hp=10_000,
        damage_response={"fire": "resistance"},
    )
    target.add_damage_response("vuln_src", {"fire": "vulnerability"})
    assert _resolve_damage_to(target, (2, 8), [5, 5], damage_type="fire") == 10  # unchanged


def test_untyped_hit_is_unaffected():
    # A plain weapon hit carries damage_type=None → no response ever applies.
    target = Entity(name="t", hp=10_000, damage_response={"fire": "resistance"})
    assert _resolve_damage_to(target, (1, 8), [7], damage_type=None, bonus=3) == 10


def test_resistance_applies_after_save_for_half():
    # RAW order: phase-6 halving THEN phase-7 resistance.  4d6=23 → half 11 → resist 5.
    target = Entity(name="t", hp=10_000, damage_response={"fire": "resistance"})
    assert _resolve_damage_to(
        target, (4, 6), [6, 6, 6, 5], damage_type="fire", halved=True
    ) == 5


# --- #4 real consumer: a fire-resistant enemy halves Searing Arc, not Guiding Bolt

def test_fire_resistant_enemy_halves_searing_arc_but_not_guiding_bolt():
    # The L10 Scion's Searing Arc is fire (FROM DATA); Guiding Bolt is radiant.
    sas = interpret_save_spell(ss.SEARING_ARC_STRIKE, {"slot_level": 2})
    assert sas.damage_type == "fire"
    enemy = Entity(name="fire-resistant", hp=10_000,
                   damage_response={"fire": "resistance"})
    # 4d6 = [6,6,5,5] = 22.  Fire (Searing Arc) → halved to 11; the same dice as
    # radiant (a Guiding-Bolt-shaped instance) are untouched.
    fire = _resolve_damage_to(enemy, sas.damage_dice, [6, 6, 5, 5], damage_type="fire")
    radiant = _resolve_damage_to(enemy, (4, 6), [6, 6, 5, 5], damage_type="radiant")
    assert fire == 11
    assert radiant == 22


# --- #4 cast path: Fire Shield's resist-fire installs via cast_effect + is swept

class _OneShotPolicy:
    def __init__(self, choices):
        self._choices = choices

    def decide(self, snapshot):
        return self._choices if snapshot.round_number == 1 else []


def test_cast_effect_installs_and_sweeps_a_damage_response():
    scion = Entity(name="scion", hp=40, base_stats={"spell_save_dc": 16})
    # Fire Shield (chill): a non-damaging self-cast granting resist-fire.
    fire_shield = Choice(
        action_type="cast_effect",
        cost="action",
        effect_source="fire_shield",
        damage_response={"fire": "resistance"},
        duration="combat",
    )
    Scheduler(
        rng=SeededRNG(0),
        entities=[scion],
        policies={scion.id: _OneShotPolicy([fire_shield])},
        max_rounds=1,
    ).run()
    # Installed: a fire instance is now halved (2d8=[5,5]=10 → 5).
    assert scion.damage_response_for("fire") == "resistance"
    assert _resolve_damage_to(scion, (2, 8), [5, 5], damage_type="fire") == 5
    # Swept at the combat boundary → full damage again.
    scion.clear_combat_buffs()
    assert scion.damage_response_for("fire") is None
    assert _resolve_damage_to(scion, (2, 8), [5, 5], damage_type="fire") == 10


# ===========================================================================
# #5 — defender-side thorns rider on the intercept seam
# ===========================================================================

def _attacker(bonus=10):
    return Entity(name="attacker", hp=50, base_stats={"attack_bonus": bonus})


def _bearer(ac=15, **kw):
    return Entity(name="bearer", hp=50, base_stats={"ac": ac}, **kw)


def test_thorns_fires_on_a_landed_hit():
    a, b = _attacker(), _bearer(ac=10)
    q = EventQueue()
    thorns = ReactiveDamageSpec(damage_dice=(2, 8), damage_type="fire")
    # d20=15 + 10 = 25 vs AC 10 → a clean hit; ac_bonus 0 (no flip).
    resolve_attack_roll(
        AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=b),
        FakeRNG([15]), q, next_sequence=2,
        intercept_decider=lambda margin: (0, None, thorns),
    )
    # Two DamageEvents: the attacker's own hit AND the thorns back at the attacker.
    events = [q.pop() for _ in range(len(q))]
    assert all(isinstance(e, DamageEvent) for e in events)
    thorns_ev = next(e for e in events if e.actor is b)
    assert thorns_ev.target is a              # thorns hits the attacker
    assert thorns_ev.damage_dice == (2, 8)
    assert thorns_ev.damage_type == "fire"
    assert thorns_ev.is_crit is False
    # The attacker's own hit is still present (thorns is additive, not a replacement).
    assert any(e.actor is a and e.target is b for e in events)


def test_thorns_does_not_fire_on_a_miss():
    a, b = _attacker(), _bearer(ac=30)
    q = EventQueue()
    called = []
    # d20=5 + 10 = 15 vs AC 30 → a real miss; the interceptor is never consulted.
    resolve_attack_roll(
        AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=b),
        FakeRNG([5]), q, next_sequence=2,
        intercept_decider=lambda margin: called.append(margin)
        or (0, None, ReactiveDamageSpec((2, 8), "fire")),
    )
    assert called == []
    assert len(q) == 0


def test_thorns_suppressed_when_the_hit_is_parried_to_a_miss():
    a, b = _attacker(), _bearer(ac=10)
    q = EventQueue()
    thorns = ReactiveDamageSpec(damage_dice=(2, 8), damage_type="fire")
    # d20=12 + 10 = 22 vs AC 10 → hit by 12... use a marginal attacker to flip.
    a_low = _attacker(bonus=0)
    # d20=12 + 0 = 12 vs AC 10 → hit by 2; +5 AC flips it to a miss → no thorns.
    resolve_attack_roll(
        AttackRollEvent(tick=make_tick(1, 0, 1), actor=a_low, target=b),
        FakeRNG([12]), q, next_sequence=2,
        intercept_decider=lambda margin: (5, None, thorns),
    )
    assert len(q) == 0  # parried → no attacker damage, and the hit didn't land → no thorns


def test_thorns_routes_through_the_attackers_damage_response():
    # A fire-resistant attacker halves Fire Shield's fire thorns (substrate #4 on
    # the thorns DamageEvent's target).
    a = Entity(name="fire-imp", hp=50,
               base_stats={"attack_bonus": 10}, damage_response={"fire": "resistance"})
    b = _bearer(ac=10)
    q = EventQueue()
    thorns = ReactiveDamageSpec(damage_dice=(2, 8), damage_type="fire")
    resolve_attack_roll(
        AttackRollEvent(tick=make_tick(1, 0, 1), actor=a, target=b),
        FakeRNG([15]), q, next_sequence=2,
        intercept_decider=lambda margin: (0, None, thorns),
    )
    thorns_ev = next(e for e in (q.pop() for _ in range(len(q))) if e.actor is b)
    # 2d8 = [6,6] = 12; the attacker resists fire → 6.
    total, _ = resolve_damage(thorns_ev, FakeRNG([6, 6]), EventQueue(), 2)
    assert total == 6


# ===========================================================================
# Enemy-strikes-back loop — ScriptedEnemyPolicy + make_day_runner wiring
# ===========================================================================

class _FireShieldThornsPolicy:
    """A bearer that does nothing on its own turn and reflects thorns on every
    incoming melee hit (a Fire-Shield-shaped test policy — the substrate exercised
    against a real attacking enemy)."""

    def __init__(self, dice=(2, 8), dtype="fire"):
        self._dice = dice
        self._dtype = dtype

    def decide(self, snapshot):
        return []

    def on_incoming_hit(self, ctx):
        return InterceptResponse(
            reactive_damage=ReactiveDamageSpec(self._dice, self._dtype)
        )


class _AlwaysAttack:
    """Minimal enemy that swings once at its target each turn (no pre-roll, so it
    needs no on_combat_start) — isolates the thorns loop deterministically."""

    def __init__(self, target):
        self._target = target

    def decide(self, snapshot):
        if snapshot.resources.get("action", 0) < 1:
            return []
        return [Choice(action_type="attack", cost="action",
                       target=self._target, weapon_stat="attack_bonus")]


def test_thorns_counts_as_the_bearers_dpr_when_the_enemy_strikes():
    bearer = Entity(name="scion", hp=60, base_stats={"ac": 17})
    enemy = Entity(name="enemy", hp=10_000,
                   base_stats={"attack_bonus": 10, "damage_dice": (1, 4), "damage_bonus": 0})
    sched = Scheduler(
        rng=FakeRNG([
            15,        # enemy d20 → 25 vs AC 17 → hits the bearer
            5, 5,      # thorns 2d8 → 10 dealt to the enemy
            2,         # enemy's own 1d4 → 2 dealt to the bearer (irrelevant to DPR)
        ]),
        entities=[bearer, enemy],
        policies={bearer.id: _FireShieldThornsPolicy(), enemy.id: _AlwaysAttack(bearer)},
        max_rounds=1,
    )
    sched.run()
    # Thorns (bearer→enemy) is the bearer's outgoing DPR → the enemy's column.
    assert sum(sched.damage_received[enemy.id]) == 10
    # The enemy's own hit lands in the BEARER's column, never the enemy's → it
    # cannot pollute the bearer's DPR.
    assert sum(sched.damage_received[bearer.id]) == 2


def test_scripted_enemy_policy_emits_action_then_free_swings():
    enemy = Entity(name="enemy", hp=10, base_stats={"attack_bonus": 5})
    char = Entity(name="char", hp=50, base_stats={"ac": 15})
    pol = ss.ScriptedEnemyPolicy(target=char, n_attacks=2, char_target_prob=1.0,
                                 rounds_per_combat=4)
    pol.on_combat_start(0, SeededRNG(0))
    snap = GameState(actor=enemy, enemies=(char,), allies=(), round_number=1,
                     turn_index=1, tick=(1, 1, 0),
                     resources={"action": 1, "bonus_action": 1})
    choices = pol.decide(snap)
    assert len(choices) == 2
    assert choices[0].cost == "action" and choices[1].cost == "none"
    assert all(c.target is char for c in choices)


def test_scripted_enemy_policy_skips_party_aimed_attacks():
    enemy = Entity(name="enemy", hp=10, base_stats={"attack_bonus": 5})
    char = Entity(name="char", hp=50, base_stats={"ac": 15})
    # char_target_prob 0 → every pre-rolled slot is party-aimed (unmodeled) → no swings.
    pol = ss.ScriptedEnemyPolicy(target=char, n_attacks=3, char_target_prob=0.0,
                                 rounds_per_combat=4)
    pol.on_combat_start(0, SeededRNG(0))
    snap = GameState(actor=enemy, enemies=(char,), allies=(), round_number=1,
                     turn_index=1, tick=(1, 1, 0), resources={"action": 1})
    assert pol.decide(snap) == []


def test_make_day_runner_wires_the_enemy_loop(monkeypatch):
    # Inject an always-hitting enemy_attack onto an existing level row; the enemy
    # then strikes the character across the day (damage in the CHARACTER's column),
    # while DPR (the dummy's column) stays the Scion's own output.
    lvl = dict(ss.LEVELS[10])
    lvl["enemy_attack"] = {
        "n_attacks": 1, "char_target_prob": 1.0,
        "attack_bonus": 50, "damage_dice": (1, 4), "damage_bonus": 0,
    }
    monkeypatch.setitem(ss.LEVELS, 10, lvl)
    runner, char, dummy = ss.make_day_runner(10, SeededRNG(1))
    assert dummy.stat("attack_bonus") == 50          # dummy got an attack profile
    result = runner.run_day()
    assert result.damage_received_by(char.id) > 0    # the enemy struck the character
    assert result.damage_received_by(dummy.id) > 0   # ...and the Scion still dealt DPR
