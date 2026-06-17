"""test_starfire_scion.py — the Starfire Scion build (L1, L4, L5) + the
per-attack damage override primitive (#4) it forced.

Validation framing (PROGRESS "STARFIRE SCION"): consistency + sanity, NOT
number-matching.  The guide's per-level DPR are ALL-HIT CEILINGS (every attack
hits, the enemy always fails its save), so there is no ground-truth ladder.  We
check:
  - factory stats + Sacred Flame dice pulled FROM DATA (interpret_save_spell);
  - the per-attack override delivers each weapon/spell's OWN dice (the primitive);
  - the policy's rotation / BA priority / Starry-Form gating;
  - per-hit and per-save DAMAGE MATH exactly (deterministic FakeRNG);
  - DPR is a plausible FRACTION of the ceiling, and grows monotonically when the
    enemy is held FIXED (L4 vs L5 share enemy AC 15 / DEX +2) — raw cross-level
    DPR is NOT expected monotonic, since the enemy hardens with level.
"""

import csv
import logging
from pathlib import Path

import pytest

from src.builds import starfire_scion as ss
from src.content import interpret_save_spell, load_abilities
from src.day_runner import DayRunner
from src.entity import Entity
from src.events import AttackRollEvent, EventQueue, SaveDamageEvent
from src.policy import Choice, DealDamageContext, GameState, HitContext
from src.rng import SeededRNG
from src.verbs import resolve_attack_roll, resolve_damage, resolve_save_damage

logging.disable(logging.CRITICAL)

_CSV = Path(__file__).resolve().parents[1] / "reference" / "data" / "monster_ac_and_saves_by_level.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeRNG:
    """Pops preloaded values; records (n, sides) per call (same shape as the
    stub in test_save_for_damage.py)."""

    def __init__(self, values):
        self._values = list(values)
        self.roll_calls = []

    def roll(self, n, sides):
        self.roll_calls.append((n, sides))
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


def _resolve_attack(actor, target, weapon_stat, dice, bonus, rng) -> int:
    """Resolve one attack with a per-attack damage override end to end; return
    the damage dealt (0 on a miss)."""
    q = EventQueue()
    ev = AttackRollEvent(
        tick=(1, 0, 1), actor=actor, target=target,
        weapon_stat=weapon_stat,
        damage_dice_override=dice, damage_bonus_override=bonus,
    )
    resolve_attack_roll(ev, rng, q, 2)
    if len(q) == 0:
        return 0
    dmg_ev = q.pop()
    total, _ = resolve_damage(dmg_ev, rng, q, 3)
    return total


def _resolve_sacred_flame(caster, enemy, dice, rng) -> int:
    """One Sacred Flame (save-NEGATES) cast end to end; return damage dealt."""
    q = EventQueue()
    ev = SaveDamageEvent(
        tick=(1, 0, 1), actor=caster, target=enemy,
        save_stat="dex_save", damage_dice=dice, on_save="none",
    )
    resolve_save_damage(ev, rng, q, 2)
    if len(q) == 0:
        return 0
    dmg_ev = q.pop()
    total, _ = resolve_damage(dmg_ev, rng, q, 3)
    return total


def _resolve_burning_hands(caster, enemy, dice, rng) -> int:
    """One Searing Arc Strike / Burning Hands (save-FOR-HALF, FIRE) cast end to end;
    return damage dealt (full on a failed save, half-rounded-down on a made one)."""
    q = EventQueue()
    ev = SaveDamageEvent(
        tick=(1, 0, 1), actor=caster, target=enemy,
        save_stat="dex_save", damage_dice=dice, on_save="half",
        damage_type="fire", is_spell=True,
    )
    resolve_save_damage(ev, rng, q, 2)
    if len(q) == 0:
        return 0
    dmg_ev = q.pop()
    total, _ = resolve_damage(dmg_ev, rng, q, 3)
    return total


def _snapshot(round_number: int, resources: dict) -> GameState:
    """Minimal snapshot for poking decide() directly (resources merges the action
    economy with the persistent pools, as the scheduler would)."""
    target = Entity(name="t", hp=10, base_stats={"ac": 15})
    return GameState(
        actor=Entity(name="a", hp=10),
        enemies=(target,),
        allies=(),
        round_number=round_number,
        turn_index=0,
        tick=(round_number, 0, 0),
        resources=resources,
    )


# ---------------------------------------------------------------------------
# Build data / factory
# ---------------------------------------------------------------------------

def test_factory_stats():
    expected = {
        1: {"attack_bonus": 5, "spell_attack_bonus": 5, "spell_save_dc": 13},
        4: {"attack_bonus": 5, "spell_attack_bonus": 5, "spell_save_dc": 13},
        5: {"attack_bonus": 6, "spell_attack_bonus": 7, "spell_save_dc": 15},
        9: {"attack_bonus": 7, "spell_attack_bonus": 8, "spell_save_dc": 16},
        10: {"attack_bonus": 7, "spell_attack_bonus": 8, "spell_save_dc": 16},
        15: {"attack_bonus": 8, "spell_attack_bonus": 10, "spell_save_dc": 18},
    }
    for level, want in expected.items():
        char = ss.make_starfire_scion(level)
        for stat, value in want.items():
            assert char.stat(stat) == value, f"L{level} {stat}"


def test_sacred_flame_dice_come_from_data():
    """The policy resolves Sacred Flame's dice via interpret_save_spell (cantrip
    scaling), NOT a literal tuple: 1d8 at L1/L4, 2d8 at L5 (Spellfire Adept)."""
    for level, dice in ((1, (1, 8)), (4, (1, 8)), (5, (2, 8))):
        char = ss.make_starfire_scion(level)
        policy = ss.StarfireScionPolicy(level, char, ss.make_training_dummy(level))
        assert policy._sacred_flame_dice == dice


def test_unimplemented_level_raises():
    with pytest.raises(NotImplementedError):
        ss.make_starfire_scion(2)


def test_enemy_stats_are_live_from_the_monster_csv():
    """enemy_ac / enemy_dex_save are the csv's ac + dex.save.mod at cr == level."""
    rows = {int(r["level"]): r for r in csv.DictReader(_CSV.open())}
    for level in (1, 4, 5, 9, 10, 11, 12, 15):
        data = ss.LEVELS[level]
        assert data["enemy_ac"] == int(rows[level]["ac"])
        assert data["enemy_dex_save"] == int(rows[level]["dex.save.mod"])


# ---------------------------------------------------------------------------
# Per-attack damage override — the primitive this build forced (#4)
# ---------------------------------------------------------------------------

def test_override_delivers_the_choices_own_dice():
    """One entity, two attacks with DIFFERENT overrides → different dice rolled.
    This is the whole point: a single actor.stat("damage_dice") no longer binds."""
    actor = Entity(name="scion", hp=20, base_stats={
        "attack_bonus": 10, "damage_dice": (1, 8), "damage_bonus": 3,
    })
    target = Entity(name="t", hp=10_000, base_stats={"ac": 1})  # always hit
    # Quarterstaff 1d8+3: d20=15 (hits, no crit), die=8 → 11.
    q = _resolve_attack(actor, target, "attack_bonus", (1, 8), 3, FakeRNG([15, 8]))
    # Unarmed 1d6+3: d20=15, die=6 → 9.
    u = _resolve_attack(actor, target, "attack_bonus", (1, 6), 3, FakeRNG([15, 6]))
    # Guiding Bolt 4d6+0: d20=15, four d6 → 24.
    g = _resolve_attack(actor, target, "attack_bonus", (4, 6), 0, FakeRNG([15, 6, 6, 6, 6]))
    assert (q, u, g) == (11, 9, 24)
    # The recorded die calls prove each pulled its OWN pool, not the entity's 1d8.
    rng = FakeRNG([15, 6, 6, 6, 6])
    _resolve_attack(actor, target, "attack_bonus", (4, 6), 0, rng)
    assert (4, 6) in rng.roll_calls


def test_no_override_falls_back_to_entity_weapon():
    """Backward-compat: an attack with no override reads actor.stat (the path
    every single-weapon build, incl. War Angel, relies on)."""
    actor = Entity(name="a", hp=20, base_stats={
        "attack_bonus": 10, "damage_dice": (1, 8), "damage_bonus": 5,
    })
    target = Entity(name="t", hp=10_000, base_stats={"ac": 1})
    q = EventQueue()
    ev = AttackRollEvent(tick=(1, 0, 1), actor=actor, target=target)
    resolve_attack_roll(ev, FakeRNG([15, 8]), q, 2)
    dmg_ev = q.pop()
    total, _ = resolve_damage(dmg_ev, FakeRNG([8]), q, 3)
    assert total == 13  # 1d8(8) + 5, from the entity stat


def test_override_bonus_zero_is_honored_not_entity_bonus():
    """Guiding Bolt has +0 damage; the override's 0 must win over the entity's
    damage_bonus (the 'override present iff damage_dice set' rule)."""
    actor = Entity(name="a", hp=20, base_stats={
        "attack_bonus": 10, "damage_dice": (1, 8), "damage_bonus": 5,
    })
    target = Entity(name="t", hp=10_000, base_stats={"ac": 1})
    dmg = _resolve_attack(actor, target, "attack_bonus", (4, 6), 0, FakeRNG([15, 6, 6, 6, 6]))
    assert dmg == 24  # 4d6, NO +5


def test_override_dice_double_on_a_crit():
    """The override rides the normal DamageEvent.damage_dice, so a nat-20 doubles
    its die COUNT (quarterstaff 1d8 → 2d8) while the flat bonus does not."""
    actor = Entity(name="a", hp=20, base_stats={
        "attack_bonus": 10, "damage_dice": (1, 6), "damage_bonus": 0,
    })
    target = Entity(name="t", hp=10_000, base_stats={"ac": 1})
    # d20=20 crit → 2d8 (both 8) + 3 → 19.  (Entity's fallback 1d6 is NOT used.)
    dmg = _resolve_attack(actor, target, "attack_bonus", (1, 8), 3, FakeRNG([20, 8, 8]))
    assert dmg == 19


# ---------------------------------------------------------------------------
# Policy structure / rotation
# ---------------------------------------------------------------------------

def _full_resources(level: int, **overrides) -> dict:
    """action+bonus_action plus this level's persistent pools at full, with
    optional overrides (e.g. spellfire_spark=0 to model exhaustion)."""
    res = {"action": 1, "bonus_action": 1, "reaction": 1}
    for name, (maximum, _sr) in ss.LEVELS[level].get("resources", {}).items():
        res[name] = maximum
    res.update(overrides)
    return res


def test_policy_emits_action_and_bonus_each_round():
    char = ss.make_starfire_scion(1)
    policy = ss.StarfireScionPolicy(1, char, ss.make_training_dummy(1))
    choices = policy.decide(_snapshot(1, _full_resources(1)))
    assert any(c.cost == "action" for c in choices)
    assert any(c.cost == "bonus_action" for c in choices)


def test_l1_bonus_priority_sacred_flame_then_unarmed():
    char = ss.make_starfire_scion(1)
    policy = ss.StarfireScionPolicy(1, char, ss.make_training_dummy(1))
    # Spellfire Spark available → BA is Sacred Flame (save_spell).
    ba = [c for c in policy.decide(_snapshot(1, _full_resources(1))) if c.cost == "bonus_action"]
    assert len(ba) == 1 and ba[0].action_type == "save_spell"
    assert ba[0].damage_dice == (1, 8) and ba[0].on_save == "none"
    # Exhausted → BA falls back to an unarmed strike (1d6+3, DEX to-hit).
    ba = [c for c in policy.decide(_snapshot(1, _full_resources(1, spellfire_spark=0)))
          if c.cost == "bonus_action"]
    assert len(ba) == 1 and ba[0].action_type == "attack"
    assert ba[0].damage_dice == (1, 6) and ba[0].weapon_stat == "attack_bonus"


def test_l4_action_guiding_bolt_then_quarterstaff():
    char = ss.make_starfire_scion(4)
    policy = ss.StarfireScionPolicy(4, char, ss.make_training_dummy(4))
    act = [c for c in policy.decide(_snapshot(1, _full_resources(4))) if c.cost == "action"]
    assert len(act) == 1 and act[0].damage_dice == (4, 6)             # Guiding Bolt
    assert act[0].weapon_stat == "spell_attack_bonus"
    act = [c for c in policy.decide(_snapshot(1, _full_resources(4, guiding_bolt_free=0)))
           if c.cost == "action"]
    assert len(act) == 1 and act[0].damage_dice == (1, 8)             # quarterstaff
    assert act[0].weapon_stat == "attack_bonus"


def test_l4_archer_only_when_starry_form_active():
    char = ss.make_starfire_scion(4)
    dummy = ss.make_training_dummy(4)
    policy = ss.StarfireScionPolicy(4, char, dummy)
    res = _full_resources(4, spellfire_spark=0)        # force the BA past Sacred Flame
    # Not activated yet → unarmed.
    ba = [c for c in policy.decide(_snapshot(1, res)) if c.cost == "bonus_action"][0]
    assert ba.damage_dice == (1, 6)
    # Activate Starry Form (consumes a Wild Shape charge) → Archer (1d8, WIS).
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._starry_form_active
    ba = [c for c in policy.decide(_snapshot(1, res)) if c.cost == "bonus_action"][0]
    assert ba.damage_dice == (1, 8) and ba.weapon_stat == "spell_attack_bonus"


def test_on_combat_start_consumes_wild_shape_and_runs_out():
    char = ss.make_starfire_scion(4)              # wild_shape (2, +1 SR)
    policy = ss.StarfireScionPolicy(4, char, ss.make_training_dummy(4))
    assert char.resources.available("wild_shape") == 2
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._starry_form_active and char.resources.available("wild_shape") == 1
    policy.on_combat_start(1, SeededRNG(0))
    assert policy._starry_form_active and char.resources.available("wild_shape") == 0
    # Pool empty → form down this combat (BA will fall back to unarmed).
    policy.on_combat_start(2, SeededRNG(0))
    assert not policy._starry_form_active


# ---------------------------------------------------------------------------
# Exact per-hit / per-save damage math (deterministic)
# ---------------------------------------------------------------------------

def test_quarterstaff_and_unarmed_hit_math_l1():
    char = ss.make_starfire_scion(1)
    target = ss.make_training_dummy(1)            # AC 13
    # Quarterstaff 1d8+3: d20=15 hits (no crit), die=5 → 8.
    assert _resolve_attack(char, target, "attack_bonus", (1, 8), 3, FakeRNG([15, 5])) == 8
    # Unarmed 1d6+3: d20=15, die=4 → 7.
    assert _resolve_attack(char, target, "attack_bonus", (1, 6), 3, FakeRNG([15, 4])) == 7
    # A miss deals nothing (d20=1 vs AC 13).
    assert _resolve_attack(char, target, "attack_bonus", (1, 8), 3, FakeRNG([1])) == 0


def test_archer_and_guiding_bolt_hit_math_l5():
    char = ss.make_starfire_scion(5)
    target = ss.make_training_dummy(5)            # AC 15
    # Archer 1d8 + WIS(4): d20=15 (hits, no crit), die=6 → 10.
    assert _resolve_attack(char, target, "spell_attack_bonus", (1, 8), 4, FakeRNG([15, 6])) == 10
    # Guiding Bolt 4d6 + 0: d20=15, dice all 5 → 20.
    assert _resolve_attack(char, target, "spell_attack_bonus", (4, 6), 0,
                           FakeRNG([15, 5, 5, 5, 5])) == 20


def test_sacred_flame_save_negates_from_data_l5():
    """Sacred Flame at L5 (2d8 from data, DC 15) — full on a failed DEX save,
    nothing on a made one.  Dice come from interpret_save_spell, not a literal."""
    char = ss.make_starfire_scion(5)              # spell_save_dc 15
    target = ss.make_training_dummy(5)            # dex_save +2
    dice = interpret_save_spell(load_abilities()["sacred_flame"],
                                {"character_level": 5}).damage_dice
    assert dice == (2, 8)
    # Failed save (d20=2 → 4 < 15): full 2d8, both max → 16.
    assert _resolve_sacred_flame(char, target, dice, FakeRNG([2, 8, 8])) == 16
    # Made save (d20=20 → 22 >= 15): negated → 0.
    assert _resolve_sacred_flame(char, target, dice, FakeRNG([20])) == 0


# ---------------------------------------------------------------------------
# Searing Arc Strike (L10) — upcast Burning Hands, FIRE save-FOR-HALF (NOT fueled)
# ---------------------------------------------------------------------------

def test_searing_arc_dice_come_from_data():
    """Searing Arc Strike upcast to slot 2 = 4d6, save-FOR-HALF, FIRE — all FROM
    DATA (interpret_save_spell with `slot_level`, primitive #3), and the policy
    resolves the same."""
    spec = interpret_save_spell(load_abilities()["searing_arc_strike"], {"slot_level": 2})
    assert spec.damage_dice == (4, 6)
    assert spec.on_save == "half"
    assert spec.damage_type == "fire"
    policy = ss.StarfireScionPolicy(10, ss.make_starfire_scion(10), ss.make_training_dummy(10))
    assert policy._sas_dice == (4, 6)
    assert policy._sas_on_save == "half"
    assert policy._sas_type == "fire"
    assert policy._sas_fp_cost == 3                  # floor(monk-6 / 2) FP → slot 2


def test_searing_arc_save_for_half_math_l10():
    """Burning Hands save-FOR-HALF at L10 (4d6, DC 16, enemy DEX +3): full on a
    failed save, half ROUNDED DOWN on a made one (deterministic FakeRNG)."""
    char = ss.make_starfire_scion(10)               # spell_save_dc 16
    target = ss.make_training_dummy(10)             # dex_save +3
    dice = (4, 6)
    # Failed save (d20=2 → 5 < 16): full 4d6 = 6+5+5+5 → 21.
    assert _resolve_burning_hands(char, target, dice, FakeRNG([2, 6, 5, 5, 5])) == 21
    # Made save (d20=20 → 23 >= 16): half of 21 = 10 (rounded DOWN, not 10.5).
    assert _resolve_burning_hands(char, target, dice, FakeRNG([20, 6, 5, 5, 5])) == 10


def test_l10_searing_arc_only_after_a_weapon_attack():
    """The BA gate: Searing Arc Strike requires the *Attack action*.  On a
    Guiding-Bolt turn (a spell action) it is unavailable → Sacred Flame fires; on a
    quarterstaff (weapon-attack) turn it leads the BA ladder; with FP spent it
    falls back to Sacred Flame."""
    char = ss.make_starfire_scion(10)
    dummy = ss.make_training_dummy(10)
    policy = ss.StarfireScionPolicy(10, char, dummy)
    policy.on_combat_start(0, SeededRNG(0))
    # NB: round 2, not round 1 — at L10 the turn-1 BA is spent casting Shillelagh
    # (thread B), so the BA ladder we gate here only runs from round 2 onward.
    # Guiding Bolt available → the action is a spell, NOT the Attack action → the BA
    # is Sacred Flame (radiant), never Searing Arc.
    ba = [c for c in policy.decide(_snapshot(2, _full_resources(10))) if c.cost == "bonus_action"][0]
    assert ba.action_type == "save_spell" and ba.damage_type == "radiant"
    # Guiding Bolt exhausted → the action is a quarterstaff weapon attack → the BA is
    # Searing Arc Strike (FIRE, 4d6, save-for-half, 3 FP).
    ba = [c for c in policy.decide(_snapshot(2, _full_resources(10, guiding_bolt_free=0)))
          if c.cost == "bonus_action"][0]
    assert ba.action_type == "save_spell" and ba.damage_type == "fire"
    assert ba.damage_dice == (4, 6) and ba.on_save == "half"
    assert ba.resource_cost == {"focus_points": 3} and ba.is_spell is True
    # Weapon-attack turn but FP exhausted → falls back to Sacred Flame (radiant).
    ba = [c for c in policy.decide(_snapshot(2, _full_resources(10, guiding_bolt_free=0, focus_points=0)))
          if c.cost == "bonus_action"][0]
    assert ba.action_type == "save_spell" and ba.damage_type == "radiant"


def test_searing_arc_fire_is_not_fueled_but_radiant_is():
    """The cross-check the FIRE Searing Arc Strike validates: Fueled Spellfire gates
    on `damage_type == radiant AND is_spell`, so a FIRE spell is declined even
    though it IS a spell — proving the damage_type gate, not just is_spell, does
    real work.  A RADIANT spell of the same shape is fueled."""
    char = ss.make_starfire_scion(10)
    dummy = ss.make_training_dummy(10)
    policy = ss.StarfireScionPolicy(10, char, dummy)

    def ctx(dtype):
        return DealDamageContext(
            actor=char, target=dummy, damage_type=dtype, is_spell=True,
            is_crit=False, base_damage_dice=(4, 6),
            round_number=1, turn_index=0, resources={"hit_dice": 10},
        )

    # FIRE spell (Searing Arc / Burning Hands): NOT fueled.
    assert policy.on_deal_damage(ctx("fire")) is None
    # RADIANT spell (Guiding Bolt / Sacred Flame): fueled with 2 Hit Dice.
    resp = policy.on_deal_damage(ctx("radiant"))
    assert resp is not None and resp.extra_damage_dice == [(2, 8)]


def test_focus_points_refill_between_combats():
    """Uncanny Metabolism + Prayer of Healing recharge focus points fully between
    combats (guide), modeled by on_combat_start refilling the (LR-only) pool."""
    char = ss.make_starfire_scion(10)
    policy = ss.StarfireScionPolicy(10, char, ss.make_training_dummy(10))
    assert char.resources.available("focus_points") == 6
    char.resources.consume("focus_points", 6)
    assert char.resources.available("focus_points") == 0
    policy.on_combat_start(1, SeededRNG(0))
    assert char.resources.available("focus_points") == 6


# ---------------------------------------------------------------------------
# THREAD B (L9-L10) — Extra Attack + martial-arts 1d8 + Shillelagh
# ---------------------------------------------------------------------------

def test_l9_extra_attack_emits_two_weapon_swings():
    """Extra Attack (monk-5): a weapon Attack action yields TWO swings — one
    cost="action" + one cost="none" (the engine's Extra-Attack shape).  A Guiding
    Bolt action is a spell and is NOT doubled."""
    char = ss.make_starfire_scion(9)
    policy = ss.StarfireScionPolicy(9, char, ss.make_training_dummy(9))
    policy.on_combat_start(0, SeededRNG(0))
    # GB exhausted → the action is the (Shillelagh) quarterstaff, doubled by Extra Attack.
    act = [c for c in policy.decide(_snapshot(2, _full_resources(9, guiding_bolt_free=0)))
           if c.action_type == "attack" and c.cost in ("action", "none")]
    assert [c.cost for c in act] == ["action", "none"]
    for c in act:                                    # both are Shillelagh swings
        assert c.damage_dice == (1, 10) and c.weapon_stat == "spell_attack_bonus"
        assert c.damage_bonus == 4
    # GB available → a single spell action (Extra Attack does not duplicate a spell).
    act = [c for c in policy.decide(_snapshot(2, _full_resources(9)))
           if c.action_type == "attack" and c.cost in ("action", "none")]
    assert len(act) == 1 and act[0].damage_dice == (4, 6)


def test_shillelagh_uses_higher_modifier_default_spellcasting_on_tie():
    """Shillelagh grants the OPTION to swing with WIS instead of DEX (user-flagged):
    use whichever ABILITY MODIFIER is higher, defaulting to the spellcasting (WIS)
    stat on a tie.  The 1d10 die applies regardless of which stat wins."""
    policy = ss.StarfireScionPolicy(9, ss.make_starfire_scion(9), ss.make_training_dummy(9))
    policy.on_combat_start(0, SeededRNG(0))
    # As built at L9: WIS(+4) > DEX(+3) → WIS wins (1d10, WIS to-hit, +4).
    c = policy._shillelagh_attack_choice("action")
    assert c.damage_dice == (1, 10) and c.weapon_stat == "spell_attack_bonus" and c.damage_bonus == 4
    # Tie (both +3) → still the spellcasting stat (the >= default).
    policy._shillelagh_wis = {"dice": (1, 10), "bonus": 3, "weapon_stat": "spell_attack_bonus"}
    c = policy._shillelagh_attack_choice("action")
    assert c.weapon_stat == "spell_attack_bonus" and c.damage_bonus == 3 and c.damage_dice == (1, 10)
    # Physical stat higher (DEX +3 > WIS +2) → swing with DEX, but the die STAYS 1d10.
    policy._shillelagh_wis = {"dice": (1, 10), "bonus": 2, "weapon_stat": "spell_attack_bonus"}
    c = policy._shillelagh_attack_choice("action")
    assert c.weapon_stat == "attack_bonus" and c.damage_bonus == 3 and c.damage_dice == (1, 10)


def test_shillelagh_die_resolves_off_the_ladder_by_character_level():
    """The Shillelagh die is FROM DATA on the dice ladder (interpret_scaled_dice),
    NOT baked per LEVELS row: 1d10 at char L9-10 (retrofit — DPR-neutral vs the
    formerly baked die) and 1d12 at char L11-16 (the [5,11,17] cantrip break).  The
    WIS modifier still rides the row (+4 through L11, +5 at L12)."""
    expected = {9: ((1, 10), 4), 10: ((1, 10), 4), 11: ((1, 12), 4), 12: ((1, 12), 5),
                15: ((1, 12), 5)}  # char L11-16 step holds at L15
    for level, (die, bonus) in expected.items():
        policy = ss.StarfireScionPolicy(
            level, ss.make_starfire_scion(level), ss.make_training_dummy(level))
        assert policy._shillelagh_wis["dice"] == die, f"L{level} die"
        assert policy._shillelagh_wis["bonus"] == bonus, f"L{level} bonus"
        # And it reaches the actual swing.
        policy.on_combat_start(0, SeededRNG(0))
        c = policy._shillelagh_attack_choice("action")
        assert c.damage_dice == die and c.damage_bonus == bonus


def test_unarmed_die_is_1d8_at_l9_and_l10():
    """Martial-arts die bumps 1d6 -> 1d8 at monk-5 (char L9) and holds at L10."""
    for level in (9, 10):
        assert ss.LEVELS[level]["unarmed"]["dice"] == (1, 8)
    # And the policy serves it: the BA falls back to a 1d8 unarmed when spells are spent.
    char = ss.make_starfire_scion(9)
    policy = ss.StarfireScionPolicy(9, char, ss.make_training_dummy(9))
    policy.on_combat_start(0, SeededRNG(0))
    ba = [c for c in policy.decide(_snapshot(2, _full_resources(9, spellfire_spark=0)))
          if c.cost == "bonus_action"][0]
    assert ba.action_type == "attack" and ba.damage_dice == (1, 8) and ba.weapon_stat == "attack_bonus"


def test_turn1_bonus_action_is_spent_casting_shillelagh():
    """Thread B models Shillelagh's turn-1 BA cast (guide 41:539) as a first-class
    cast_effect that CONSUMES the bonus action (no damage); from round 2 the BA
    damage ladder runs normally.  The action (and Extra Attack) is unaffected.
    (DPR-identical to the former 'withhold the BA option' suppression.)"""
    char = ss.make_starfire_scion(9)
    policy = ss.StarfireScionPolicy(9, char, ss.make_training_dummy(9))
    policy.on_combat_start(0, SeededRNG(0))
    r1 = policy.decide(_snapshot(1, _full_resources(9, guiding_bolt_free=0)))
    # Turn-1 BA is the Shillelagh cast: a cast_effect, not a damage option.
    ba1 = [c for c in r1 if c.cost == "bonus_action"]
    assert len(ba1) == 1 and ba1[0].action_type == "cast_effect"
    assert ba1[0].effect_source == "shillelagh"
    # No damage-dealing BA on round 1 (the BA went to the cast).
    assert not any(c.cost == "bonus_action" and c.action_type != "cast_effect" for c in r1)
    assert [c.cost for c in r1 if c.action_type == "attack"] == ["action", "none"]
    # Round 2: the BA damage ladder runs (no cast_effect).
    r2 = policy.decide(_snapshot(2, _full_resources(9, guiding_bolt_free=0)))
    ba2 = [c for c in r2 if c.cost == "bonus_action"]
    assert ba2 and all(c.action_type != "cast_effect" for c in ba2)
    # Levels without Shillelagh (L1) never cast it — the turn-1 BA is a damage option.
    p1 = ss.StarfireScionPolicy(1, ss.make_starfire_scion(1), ss.make_training_dummy(1))
    p1.on_combat_start(0, SeededRNG(0))
    r1_l1 = p1.decide(_snapshot(1, _full_resources(1)))
    assert any(c.cost == "bonus_action" and c.action_type != "cast_effect" for c in r1_l1)


def test_starry_form_activation_emits_a_bundled_cast_effect():
    """Starry Form: Archer activation is a first-class cast_effect on turn 1 — but
    BUNDLED (cost="none"), so it consumes no economy and the archer BA still fires
    (DPR-neutral).  Only round 1, only when the form is active."""
    char = ss.make_starfire_scion(4)
    policy = ss.StarfireScionPolicy(4, char, ss.make_training_dummy(4))
    res = _full_resources(4)
    # Not activated yet → no activation event.
    assert not any(c.action_type == "cast_effect" for c in policy.decide(_snapshot(1, res)))
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._starry_form_active
    r1 = policy.decide(_snapshot(1, res))
    act = [c for c in r1 if c.action_type == "cast_effect"]
    assert len(act) == 1 and act[0].effect_source == "starry_form" and act[0].cost == "none"
    # No activation event after round 1.
    assert not any(c.action_type == "cast_effect" for c in policy.decide(_snapshot(2, res)))


# ---------------------------------------------------------------------------
# DPR sanity — plausible fraction of the ceiling; monotonic at a FIXED enemy
# ---------------------------------------------------------------------------

def _mean_dpr(level: int, n_days: int, seed: int = 0, rounds_per_combat: int = 4) -> float:
    rng = SeededRNG(seed)
    runner, char, dummy = ss.make_day_runner(level, rng, rounds_per_combat)
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_dpr_is_a_plausible_fraction_of_the_ceiling():
    """Each level: 0 < DPR < ceiling (every attack can miss / every save can
    succeed, so the all-hit ceiling is a strict upper bound)."""
    for level in (1, 4, 5, 9, 10, 11, 12, 15):
        dpr = _mean_dpr(level, n_days=400)
        ceiling = ss.LEVELS[level]["ceiling_dpr"]
        assert 0 < dpr < ceiling, f"L{level}: {dpr:.2f} not in (0, {ceiling})"


def test_l5_outdamages_l4_against_the_same_enemy():
    """The monotonic consistency check, with the enemy held FIXED: L4 and L5 face
    the same monster (AC 15 / DEX +2), so L5's gains (PB +1, WIS +1, Sacred Flame
    1d8→2d8) must lift DPR.  (Raw cross-level DPR is NOT expected monotonic — the
    enemy hardens with level, exactly as War Angel's targets do.)"""
    assert ss.LEVELS[4]["enemy_ac"] == ss.LEVELS[5]["enemy_ac"] == 15
    assert ss.LEVELS[4]["enemy_dex_save"] == ss.LEVELS[5]["enemy_dex_save"] == 2
    assert _mean_dpr(5, n_days=600) > _mean_dpr(4, n_days=600)


def _mean_dpr_l10(searing_arc: bool, n_days: int, seed: int = 0, rounds_per_combat: int = 4) -> float:
    """L10 DPR with Searing Arc Strike enabled or ABLATED (the feature switched off
    so the BA falls back to Sacred Flame / unarmed) — same enemy either way."""
    rng = SeededRNG(seed)
    char = ss.make_starfire_scion(10)
    dummy = ss.make_training_dummy(10)
    policy = ss.StarfireScionPolicy(10, char, dummy, rounds_per_combat)
    if not searing_arc:
        policy._has_searing_arc = False             # ablate the feature
    runner = DayRunner(
        rng=rng, entities=[char, dummy],
        policies={char.id: policy}, rounds_per_combat=rounds_per_combat,
    )
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_searing_arc_strike_lifts_l10_dpr_at_a_fixed_enemy():
    """Our-side consistency check with the enemy held FIXED (the same L10 monster
    both ways): enabling Searing Arc Strike strictly raises DPR over the ablated
    build, isolating the feature's contribution.  (L5 and L10 do NOT share an enemy,
    so this within-L10 ablation — not a cross-level compare — is the clean isolation.)"""
    on = _mean_dpr_l10(searing_arc=True, n_days=600)
    off = _mean_dpr_l10(searing_arc=False, n_days=600)
    assert on > off, f"searing arc on {on:.2f} !> off {off:.2f}"


def _mean_dpr_l9(thread_b: bool, n_days: int, seed: int = 0, rounds_per_combat: int = 4) -> float:
    """L9 DPR with thread B (Extra Attack + Shillelagh) enabled or ABLATED — same
    enemy either way.  Ablating drops to a single DEX quarterstaff swing (no Extra
    Attack, no 1d10/WIS Shillelagh upgrade, no turn-1 BA cast cost)."""
    rng = SeededRNG(seed)
    char = ss.make_starfire_scion(9)
    dummy = ss.make_training_dummy(9)
    policy = ss.StarfireScionPolicy(9, char, dummy, rounds_per_combat)
    if not thread_b:
        policy._extra_attacks = 0
        policy._has_shillelagh = False        # on_combat_start then leaves _shillelagh_active False
    runner = DayRunner(
        rng=rng, entities=[char, dummy],
        policies={char.id: policy}, rounds_per_combat=rounds_per_combat,
    )
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_thread_b_lifts_l9_dpr_at_a_fixed_enemy():
    """Our-side consistency check with the enemy held FIXED (the same L9 monster
    both ways): enabling Extra Attack + Shillelagh strictly raises DPR over the
    ablated single-quarterstaff build, isolating thread B's contribution.  (L9 and
    L10 do NOT share an enemy — L10's DEX save is +3 vs L9's +2 — so this within-L9
    ablation, not a cross-level compare, is the clean isolation.)"""
    on = _mean_dpr_l9(thread_b=True, n_days=600)
    off = _mean_dpr_l9(thread_b=False, n_days=600)
    assert on > off, f"thread B on {on:.2f} !> off {off:.2f}"


def _mean_dpr_l11(shillelagh_die: tuple[int, int], n_days: int,
                  seed: int = 0, rounds_per_combat: int = 4) -> float:
    """L11 DPR with the Shillelagh die forced to a given value — same enemy either
    way.  Used to ablate the ladder's L11 step (1d12) against the prior step (1d10),
    isolating the die-size growth's contribution."""
    rng = SeededRNG(seed)
    char = ss.make_starfire_scion(11)
    dummy = ss.make_training_dummy(11)
    policy = ss.StarfireScionPolicy(11, char, dummy, rounds_per_combat)
    policy._shillelagh_wis = {**policy._shillelagh_wis, "dice": shillelagh_die}
    runner = DayRunner(
        rng=rng, entities=[char, dummy],
        policies={char.id: policy}, rounds_per_combat=rounds_per_combat,
    )
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_shillelagh_d12_lifts_l11_dpr_over_d10_at_a_fixed_enemy():
    """The dice ladder's payoff, isolated: at the fixed L11 enemy, the L11 step
    (Shillelagh 1d12) strictly out-damages the prior step (1d10).  (L10 and L11 do
    NOT share an enemy — the enemy hardens AC 16 -> 17 — so this within-L11 die
    ablation, not a cross-level compare, is the clean isolation of the ladder step.)"""
    bigger = _mean_dpr_l11(shillelagh_die=(1, 12), n_days=600)
    smaller = _mean_dpr_l11(shillelagh_die=(1, 10), n_days=600)
    assert bigger > smaller, f"1d12 {bigger:.2f} !> 1d10 {smaller:.2f}"


def test_l12_outdamages_l11_against_the_same_enemy():
    """The monotonic consistency check with the enemy held FIXED: cr 11 and cr 12
    are the SAME monster (AC 17 / DEX +3), so L12's gains (WIS 19 -> 20: +1 spell
    to-hit / DC / damage, and Searing Arc 4d6 -> 5d6) must lift DPR over L11.  The
    Shillelagh die is 1d12 at both, so this isolates the WIS-20 + upcast scaling."""
    assert ss.LEVELS[11]["enemy_ac"] == ss.LEVELS[12]["enemy_ac"] == 17
    assert ss.LEVELS[11]["enemy_dex_save"] == ss.LEVELS[12]["enemy_dex_save"] == 3
    assert _mean_dpr(12, n_days=600) > _mean_dpr(11, n_days=600)


# ---------------------------------------------------------------------------
# Tier-4 row (L15): Elemental Adept (fire) + Fire Shield (#4 resist + #5 thorns +
# the warm/chill choose_one).  Validation framing unchanged — consistency/sanity.
# ---------------------------------------------------------------------------

def test_l15_searing_arc_is_elemental_adept_treated():
    """The L15 Scion holds Elemental Adept (fire), so its Searing Arc Choice carries
    the bypass + 1->2 high-grade (min_die=2, ignore_resistance) — fire only."""
    policy = ss.StarfireScionPolicy(15, ss.make_starfire_scion(15),
                                    ss.make_training_dummy(15))
    c = policy._searing_arc_choice()
    assert c.damage_type == "fire" and c.is_spell is True
    assert c.min_die == 2 and c.ignore_resistance is True


def test_l15_fire_shield_warm_choose_one_selects_cold_resist_and_fire_thorns():
    """The warm/chill choose_one (first consumer): WARM installs ONLY the cold
    resistance (#4) on the turn-1 pre-cast and reflects FIRE thorns (#5).  The fire
    thorns match our Elemental Adept element, so they bypass + high-grade."""
    policy = ss.StarfireScionPolicy(15, ss.make_starfire_scion(15),
                                    ss.make_training_dummy(15),
                                    fourth_level_spell="fire_shield")
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._fire_shield_active
    fs = [c for c in policy.decide(_snapshot(1, {})) if c.effect_source == "fire_shield"]
    assert len(fs) == 1
    assert fs[0].action_type == "cast_effect" and fs[0].cost == "none"
    assert fs[0].damage_response == {"cold": "resistance"}      # warm resists COLD only
    thorns = policy.on_incoming_hit(None).reactive_damage
    assert thorns.damage_type == "fire" and thorns.damage_dice == (2, 8)
    assert thorns.min_die == 2 and thorns.ignore_resistance is True


def test_fire_shield_chill_mode_selects_the_other_payload():
    """Flipping the choose_one to CHILL installs the OTHER payload: resist FIRE +
    COLD thorns.  Cold thorns do NOT match the fire Elemental Adept, so no bypass."""
    policy = ss.StarfireScionPolicy(15, ss.make_starfire_scion(15),
                                    ss.make_training_dummy(15),
                                    fourth_level_spell="fire_shield")
    policy._fire_shield_mode = "chill"
    policy.on_combat_start(0, SeededRNG(0))
    fs = [c for c in policy.decide(_snapshot(1, {})) if c.effect_source == "fire_shield"]
    assert fs[0].damage_response == {"fire": "resistance"}      # chill resists FIRE
    thorns = policy.on_incoming_hit(None).reactive_damage
    assert thorns.damage_type == "cold"                         # ...and reflects COLD
    assert thorns.min_die is None and thorns.ignore_resistance is False


def test_fire_shield_is_pre_cast_in_only_one_combat_per_day():
    """With Fire Shield prepared, the single 4th-level slot (slot_4th) → pre-cast
    in a single combat; later combats have it down (no resist install, no thorns)."""
    char = ss.make_starfire_scion(15)
    policy = ss.StarfireScionPolicy(15, char, ss.make_training_dummy(15),
                                    fourth_level_spell="fire_shield")
    assert char.resources.available("slot_4th") == 1
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._fire_shield_active and char.resources.available("slot_4th") == 0
    policy.on_combat_start(1, SeededRNG(0))
    assert not policy._fire_shield_active
    assert policy.on_incoming_hit(None) is None                 # no thorns when down


def test_l15_fom_and_fire_shield_share_the_single_4th_level_slot():
    """The slot reconciliation (session 15): druid-7 has ONE 4th-level slot, so the
    two loadouts COMPETE — the prepared spell consumes slot_4th and the OTHER is
    never cast (no over-count).  FoM default; Fire Shield only when prepared."""
    # Default loadout = FoM: it claims the slot, Fire Shield stays down.
    char = ss.make_starfire_scion(15)
    fom_policy = ss.StarfireScionPolicy(15, char, ss.make_training_dummy(15))
    fom_policy.on_combat_start(0, SeededRNG(0))
    assert fom_policy._fount_of_moonlight_active and not fom_policy._fire_shield_active
    assert char.resources.available("slot_4th") == 0
    # Fire Shield loadout: it claims the slot, FoM stays down.
    char2 = ss.make_starfire_scion(15)
    fs_policy = ss.StarfireScionPolicy(15, char2, ss.make_training_dummy(15),
                                       fourth_level_spell="fire_shield")
    fs_policy.on_combat_start(0, SeededRNG(0))
    assert fs_policy._fire_shield_active and not fs_policy._fount_of_moonlight_active
    assert not fs_policy._has_fount_of_moonlight


def _mean_dpr_l15(fire_shield: bool, n_days: int, seed: int = 0,
                  rounds_per_combat: int = 4) -> float:
    """L15 DPR with Fire Shield enabled or ABLATED.  The enemy strikes back either
    way (same RNG), so the ONLY difference is the reflected thorns — which, since
    the dummy is BOTH the Scion's target and the attacker, land in the dummy's
    column and count toward DPR.  The Scion's offense is identical either way."""
    rng = SeededRNG(seed)
    char = ss.make_starfire_scion(15)
    dummy = ss.make_training_dummy(15)
    # Prepare the Fire Shield loadout (not the default FoM one) so the slot is spent
    # on Fire Shield; ablation switches its cast off, isolating ONLY the thorns.
    policy = ss.StarfireScionPolicy(15, char, dummy, rounds_per_combat,
                                    fourth_level_spell="fire_shield")
    if not fire_shield:
        policy._has_fire_shield = False             # ablate the cast (no resist, no thorns)
    ea = ss.LEVELS[15]["enemy_attack"]
    enemy_policy = ss.ScriptedEnemyPolicy(
        target=char, n_attacks=ea["n_attacks"],
        char_target_prob=ea["char_target_prob"], rounds_per_combat=rounds_per_combat)
    runner = DayRunner(
        rng=rng, entities=[char, dummy],
        policies={char.id: policy, dummy.id: enemy_policy},
        rounds_per_combat=rounds_per_combat)
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_fire_shield_thorns_lift_l15_dpr_at_a_fixed_enemy():
    """Fire Shield's reflected thorns strictly raise DPR over the ablated build at
    the same enemy — the clean isolation of substrate #5 doing real work through
    the enemy-strikes-back loop (thorns land in the dummy's column)."""
    on = _mean_dpr_l15(fire_shield=True, n_days=600)
    off = _mean_dpr_l15(fire_shield=False, n_days=600)
    assert on > off, f"fire shield on {on:.2f} !> off {off:.2f}"


# ---------------------------------------------------------------------------
# Tier-4 row (L15): substrate #6 — OUTGOING RIDERS (Fount of Moonlight + Primal
# Strike).  on_hit spawns separately-typed rider DamageEvents; FoM's radiant is
# fuelable, Primal Strike's elemental is a feature (not fueled, not EA-treated).
# Validation framing unchanged — consistency/sanity, not number-matching.
# ---------------------------------------------------------------------------

def _l15_policy(primal_strike_unarmed=None):
    char = ss.make_starfire_scion(15)
    policy = ss.StarfireScionPolicy(15, char, ss.make_training_dummy(15),
                                    primal_strike_unarmed=primal_strike_unarmed)
    return policy, char


def _hit_ctx(round_number=1, is_spell=False, is_unarmed=False, is_crit=False):
    """A HitContext for poking on_hit directly (the rider gate reads is_spell /
    is_unarmed / round_number; the rest are unused by the Scion's on_hit)."""
    return HitContext(
        actor=Entity(name="a", hp=10), target=Entity(name="t", hp=10),
        is_crit=is_crit, cost="action", bonus_action_available=True,
        resources={}, round_number=round_number,
        is_spell=is_spell, is_unarmed=is_unarmed,
    )


def _rider(resp, damage_type):
    """The rider of a given damage type in a HitResponse (None if absent)."""
    if resp is None:
        return None
    return next((r for r in resp.rider_damage if r.damage_type == damage_type), None)


def test_l15_fom_rides_every_melee_hit_with_fuelable_radiant():
    """Fount of Moonlight: +2d6 RADIANT on every melee hit — quarterstaff AND
    unarmed (both are melee attacks) — tagged is_spell so Fueled Spellfire can
    fuel it (the fueling itself is tested separately).  The rider gates on
    concentration being held (set by the turn-1 cast — simulated here)."""
    policy, char = _l15_policy()
    policy.on_combat_start(0, SeededRNG(0))               # FoM is the combat's 4th-lvl spell
    assert policy._fount_of_moonlight_active
    char.concentration = "fount_of_moonlight"             # the turn-1 Magic-action cast resolved
    fom = _rider(policy.on_hit(_hit_ctx(is_unarmed=False)), "radiant")   # quarterstaff
    assert fom is not None and fom.damage_dice == (2, 6) and fom.is_spell is True
    fom_u = _rider(policy.on_hit(_hit_ctx(round_number=2, is_unarmed=True)), "radiant")  # unarmed
    assert fom_u is not None and fom_u.damage_dice == (2, 6)


def test_l15_fom_rider_is_silent_until_concentration_is_established():
    """The rider gates on concentration, not the combat flag: before the turn-1
    cast resolves (no concentration yet) a melee hit gets no FoM radiant; once
    concentration drops (a broken save), it goes silent again."""
    policy, char = _l15_policy()
    policy._has_primal_strike = False                     # isolate FoM
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._fount_of_moonlight_active              # committed for the combat...
    assert policy.on_hit(_hit_ctx()) is None              # ...but no rider until concentration holds
    char.concentration = "fount_of_moonlight"
    assert _rider(policy.on_hit(_hit_ctx()), "radiant") is not None
    char.concentration = None                             # a failed CON save broke it
    assert policy.on_hit(_hit_ctx(round_number=2)) is None


def test_l15_fom_skips_the_ranged_guiding_bolt_spell():
    """FoM rides MELEE attacks only — the ranged Guiding Bolt (is_spell) gets no
    rider; Primal Strike also declines a spell (not a weapon attack) → None."""
    policy, char = _l15_policy()
    policy.on_combat_start(0, SeededRNG(0))
    char.concentration = "fount_of_moonlight"
    assert policy.on_hit(_hit_ctx(is_spell=True)) is None


def test_l15_fom_radiant_is_fueled_by_fueled_spellfire():
    """The FoM rider is radiant + is_spell, so it reaches on_deal_damage as a
    fuelable instance — Fueled Spellfire adds up to 2 Hit Dice into it (the
    interaction the guide writes `..._{fueled-spellfire(2)} --> ...+4d6`)."""
    policy, char = _l15_policy()
    policy.on_combat_start(0, SeededRNG(0))
    ctx = DealDamageContext(
        actor=char, target=ss.make_training_dummy(15),
        damage_type="radiant", is_spell=True, is_crit=False,
        base_damage_dice=(2, 6), resources=char.resources.as_dict(),
        round_number=1, turn_index=0,
    )
    resp = policy.on_deal_damage(ctx)
    assert resp is not None and resp.extra_damage_dice == [(2, 8)]


def test_l15_primal_strike_fires_once_per_turn_on_weapon_hits():
    """Primal Strike: a FEATURE (is_spell False) adding 1d8 of the chosen element,
    once on each of the character's turns (round-gated), on a weapon hit."""
    policy, _ = _l15_policy()                             # RAW (default)
    policy._has_fount_of_moonlight = False                # isolate Primal from FoM
    policy.on_combat_start(0, SeededRNG(0))
    r1 = _rider(policy.on_hit(_hit_ctx(round_number=1)), "fire")
    assert r1 is not None and r1.damage_dice == (1, 8) and r1.is_spell is False
    assert policy.on_hit(_hit_ctx(round_number=1)) is None      # once/turn — second hit declines
    assert _rider(policy.on_hit(_hit_ctx(round_number=2)), "fire") is not None  # next turn fires


def test_l15_primal_strike_raw_declines_unarmed_nonraw_rides_it():
    """The user-requested toggle (memory primal-strikes-explore-unarmed): RAW rides
    weapon attacks only (declines unarmed); the non-RAW option also rides unarmed."""
    raw, _ = _l15_policy()                                # default RAW
    raw._has_fount_of_moonlight = False
    raw.on_combat_start(0, SeededRNG(0))
    assert raw.on_hit(_hit_ctx(is_unarmed=True)) is None         # RAW: no Primal on unarmed

    nonraw, _ = _l15_policy(primal_strike_unarmed=True)
    nonraw._has_fount_of_moonlight = False
    nonraw.on_combat_start(0, SeededRNG(0))
    r = _rider(nonraw.on_hit(_hit_ctx(is_unarmed=True)), "fire")
    assert r is not None and r.damage_dice == (1, 8)             # non-RAW: rides unarmed


def test_l15_primal_strike_is_not_elemental_adept_treated():
    """Primal Strike is a FEATURE, not a spell — even though we pick fire it does
    NOT get Elemental Adept's bypass + 1->2, unlike the fire Searing Arc (a spell).
    The cross-check that the is_spell gate does real work on the rider path."""
    policy, _ = _l15_policy()
    policy._has_fount_of_moonlight = False
    policy.on_combat_start(0, SeededRNG(0))
    ps = _rider(policy.on_hit(_hit_ctx()), "fire")
    assert ps.is_spell is False and ps.min_die is None and ps.ignore_resistance is False
    sa = policy._searing_arc_choice()                            # ...contrast Searing Arc
    assert sa.min_die == 2 and sa.ignore_resistance is True


def test_l15_fom_and_primal_combine_on_the_first_weapon_hit():
    """The guide's turn-02 `quarterstaff_{primal-strike,fueled-spellfire(2)} -->
    2d12+3d8+4d6...`: the first melee swing carries BOTH riders — Primal (fire
    feature) and FoM (radiant spell)."""
    policy, char = _l15_policy()
    policy.on_combat_start(0, SeededRNG(0))
    char.concentration = "fount_of_moonlight"
    resp = policy.on_hit(_hit_ctx(round_number=1))
    assert sorted(r.damage_type for r in resp.rider_damage) == ["fire", "radiant"]
    assert _rider(resp, "radiant").is_spell is True              # FoM — fuelable
    assert _rider(resp, "fire").is_spell is False                # Primal — feature


def test_l15_fom_is_cast_as_a_turn1_magic_action_in_one_combat_per_day():
    """The single 4th-level slot (slot_4th) → FoM in ONE combat/day, cast as a
    turn-1 MAGIC ACTION (cost="action", concentration) that installs the radiant
    resistance (#4) and deals 0 damage that turn; later combats have it down."""
    policy, char = _l15_policy()
    assert char.resources.available("slot_4th") == 1
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._fount_of_moonlight_active and char.resources.available("slot_4th") == 0
    cast = [c for c in policy.decide(_snapshot(1, {"action": 1}))
            if c.effect_source == "fount_of_moonlight"]
    assert len(cast) == 1
    assert cast[0].action_type == "cast_effect" and cast[0].cost == "action"
    assert cast[0].concentration is True
    assert cast[0].damage_response == {"radiant": "resistance"}
    policy.on_combat_start(1, SeededRNG(0))                  # no slot left → no FoM combat
    assert not policy._fount_of_moonlight_active
    assert char.concentration != "fount_of_moonlight"
    # No FoM radiant rider when down (Primal Strike's fire rider may still fire).
    assert _rider(policy.on_hit(_hit_ctx(round_number=1)), "radiant") is None


def test_l15_fom_combat_turn1_casts_fom_and_activates_dragon_for_zero_damage():
    """Guide 41:779 `turn-01: BA:starry-form(dragon) + magic-action:fount-of-
    moonlight --> 0`: turn 1 of the FoM combat spends the ACTION on the FoM cast
    and the BONUS ACTION on the Dragon-form activation, so it deals no damage."""
    policy, char = _l15_policy()
    policy.on_combat_start(0, SeededRNG(0))
    assert policy._dragon_form_active and char.resources.available("wild_shape") == 1
    choices = policy.decide(_snapshot(1, {"action": 1, "bonus_action": 1}))
    sources = {c.effect_source for c in choices}
    assert sources == {"fount_of_moonlight", "starry_form_dragon"}
    # No attack/save_spell on turn 1 → 0 damage; both are cast_effects.
    assert all(c.action_type == "cast_effect" for c in choices)
    dragon = next(c for c in choices if c.effect_source == "starry_form_dragon")
    assert dragon.cost == "bonus_action"
    assert dragon.statuses[0].name == "concentration_save_floor"
    assert dragon.statuses[0].value == 10


def _mean_dpr_l15_rider(disable, n_days, seed=0, rounds_per_combat=4):
    """L15 DPR with one #6 rider ABLATED (FoM or Primal Strike switched off) — the
    enemy strikes back either way (same loop), so the difference isolates that
    rider's contribution to the Scion's outgoing DPR."""
    rng = SeededRNG(seed)
    char = ss.make_starfire_scion(15)
    dummy = ss.make_training_dummy(15)
    policy = ss.StarfireScionPolicy(15, char, dummy, rounds_per_combat)
    if disable == "fom":
        policy._has_fount_of_moonlight = False
    elif disable == "primal":
        policy._has_primal_strike = False
    ea = ss.LEVELS[15]["enemy_attack"]
    enemy_policy = ss.ScriptedEnemyPolicy(
        target=char, n_attacks=ea["n_attacks"],
        char_target_prob=ea["char_target_prob"], rounds_per_combat=rounds_per_combat)
    runner = DayRunner(
        rng=rng, entities=[char, dummy],
        policies={char.id: policy, dummy.id: enemy_policy},
        rounds_per_combat=rounds_per_combat)
    rounds_per_day = 4 * rounds_per_combat
    total = sum(runner.run_day().damage_received_by(dummy.id) for _ in range(n_days))
    return total / (n_days * rounds_per_day)


def test_fount_of_moonlight_lifts_l15_dpr_at_a_fixed_enemy():
    on = _mean_dpr_l15_rider(disable=None, n_days=400)
    off = _mean_dpr_l15_rider(disable="fom", n_days=400)
    assert on > off, f"FoM on {on:.2f} !> off {off:.2f}"


def test_primal_strike_lifts_l15_dpr_at_a_fixed_enemy():
    on = _mean_dpr_l15_rider(disable=None, n_days=400)
    off = _mean_dpr_l15_rider(disable="primal", n_days=400)
    assert on > off, f"primal strike on {on:.2f} !> off {off:.2f}"


def test_l15_fom_loadout_nets_positive_over_an_unused_4th_level_slot():
    """The FoM loadout's NET contribution is positive even paying the honest cast
    cost (session 15): the turn-1 Magic-action cast deals 0 damage and concentration
    can break, but the +2d6 fueled radiant on turns 2-4 more than pays for it — so
    the FoM loadout out-DPRs the same build leaving its single 4th-level slot UNUSED.
    (This replaces the stale "rises above session-13's 29.7" check: with the slot now
    SHARED, FoM and Fire Shield are mutually-exclusive loadouts, not additive, so the
    honest FoM figure sits near — not clearly above — that Fire-Shield-only baseline.)
    """
    rng_fom = SeededRNG(0)
    runner_fom, _, dummy_fom = ss.make_day_runner(15, rng_fom)
    rng_none = SeededRNG(0)
    runner_none, _, dummy_none = ss.make_day_runner(15, rng_none, fourth_level_spell="none")
    n_days, rounds_per_day = 400, 16
    fom = sum(runner_fom.run_day().damage_received_by(dummy_fom.id)
              for _ in range(n_days)) / (n_days * rounds_per_day)
    none = sum(runner_none.run_day().damage_received_by(dummy_none.id)
               for _ in range(n_days)) / (n_days * rounds_per_day)
    assert fom > none, f"FoM loadout {fom:.2f} !> unused-slot {none:.2f}"
    assert fom < ss.LEVELS[15]["ceiling_dpr"], f"L15 FoM DPR {fom:.2f} >= ceiling"


def test_l15_dragon_form_floor_protects_fom_concentration():
    """Starry-Form Dragon's save-floor (treat ≤9 as 10) sharply reduces FoM
    concentration breaks: with the floor active the Scion almost never loses FoM to
    the enemy's hits, but ablating the Dragon activation lets breaks happen — a clean
    isolation of the substrate-#3 save-floor doing real work on the concentration path.
    """
    def breaks(dragon: bool) -> int:
        rng = SeededRNG(1)
        char = ss.make_starfire_scion(15)
        dummy = ss.make_training_dummy(15)
        policy = ss.StarfireScionPolicy(15, char, dummy)
        if not dragon:
            policy._has_dragon_form = False          # cast FoM but DON'T guard it
        ea = ss.LEVELS[15]["enemy_attack"]
        enemy = ss.ScriptedEnemyPolicy(
            target=char, n_attacks=ea["n_attacks"], char_target_prob=ea["char_target_prob"])
        runner = DayRunner(rng=rng, entities=[char, dummy],
                           policies={char.id: policy, dummy.id: enemy})
        for _ in range(200):
            runner.run_day()
        return char.concentration_breaks
    with_floor = breaks(dragon=True)
    without_floor = breaks(dragon=False)
    assert without_floor > with_floor, (
        f"dragon floor breaks {with_floor} should be < no-floor {without_floor}")
