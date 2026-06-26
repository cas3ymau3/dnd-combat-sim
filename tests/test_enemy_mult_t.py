"""test_enemy_mult_t.py — the §5 fractional defense multiplier `mult(t)` (enemy_model.md
§5; roadmap step 4) and its §13 mitigation-channel emission.

Validation framing (validate-mechanism-not-build-value): we assert the MECHANISM — the
multiplier equals the documented `1 − 0.5·P_resist − P_immune + P_vulnerable`, it reduces
typed OUTGOING damage by exactly that factor at the enemy's damage-intake, the mitigation
channel records before/after by type, and the §7 res/imm/vuln-check OFF state (no profile
installed) is byte-identical (multiplier 1.0, no mitigation records, no baseline drift). We
do NOT assert any DPR value — the per-band prevalences are the census's job, frozen upstream.
"""

import logging

import pytest

from src.builds.enemy_stats import (
    band_damage_multiplier,
    band_damage_multipliers,
    band_for_level,
)
from src.builds import monster_profile as mp
from src.entity import Entity
from src.events import DamageEvent, EventQueue, make_tick
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.telemetry import CombatTelemetry

logging.disable(logging.CRITICAL)

# Representative level for each band (level selects band; band supplies the mix, §2).
_BAND_LEVEL = {"0-4": 2, "5-10": 7, "11-16": 13, "17+": 18}


def _flat_damage_event(target, damage_type, amount):
    """A deterministic flat-only DamageEvent (no dice rolled) of `amount` `damage_type`
    damage at `target` — isolates `mult(t)` from dice variance so the post-multiplier
    total is exactly round(amount * mult)."""
    return DamageEvent(
        tick=make_tick(1, 0, 0),
        actor=target,                 # actor irrelevant for the intake multiplier
        target=target,
        damage_dice=(0, 0),
        damage_bonus=amount,
        damage_type=damage_type,
        cost="none",
    )


def _resolve(event, telemetry=None):
    """Drive one DamageEvent through resolve_damage; return the total dealt."""
    from src.verbs import resolve_damage
    total, _seq = resolve_damage(event, SeededRNG(1), EventQueue(), 1, telemetry=telemetry)
    return total


# ---------------------------------------------------------------------------
# The accessor: mult(t) reproduces the documented formula / worked example
# ---------------------------------------------------------------------------

def test_fire_multiplier_matches_documented_worked_example():
    """§5's worked example: fire ≈ 0.93 / 0.84 / 0.79 / 0.64 across the four bands."""
    got = [band_damage_multiplier(_BAND_LEVEL[b], "fire") for b in mp.BANDS]
    assert got == pytest.approx([0.93, 0.84, 0.79, 0.64], abs=0.01)


def test_multiplier_matches_formula_from_frozen_table():
    """mult(t) == 1 − 0.5·res − imm + vul recomputed straight from the frozen table."""
    table = mp.load_band_table()
    for band in mp.BANDS:
        row = table[band]
        lvl = _BAND_LEVEL[band]
        for t in ("fire", "poison", "cold", "radiant"):
            expect = 1.0 - 0.5 * row[f"res_{t}"] / 100.0 \
                - row[f"imm_{t}"] / 100.0 + row[f"vul_{t}"] / 100.0
            assert band_damage_multiplier(lvl, t) == pytest.approx(expect)


def test_force_multiplier_is_one_in_every_band():
    """Force is essentially never resisted — so a FORCE-damage build keeps ~100% of its
    output in every tier (the outgoing-side 'force' behavior falls out of the lookup, no
    separate toggle needed)."""
    for band in mp.BANDS:
        assert band_damage_multiplier(_BAND_LEVEL[band], "force") == pytest.approx(1.0)


def test_poison_is_brutally_mitigated_at_top_band():
    """Poison immunity is widespread (§5: ~19/28/26/40%); the multiplier reflects it —
    a sanity check that the formula bites the type the design flags, not a value claim."""
    assert band_damage_multiplier(18, "poison") < band_damage_multiplier(18, "fire")


def test_profile_covers_all_thirteen_types_and_unknown_is_one():
    prof = band_damage_multipliers(7)
    assert len(prof) == 13 and "fire" in prof and "psychic" in prof
    assert band_damage_multiplier(7, "nonsense") == 1.0


# ---------------------------------------------------------------------------
# Entity: the fractional layer is inert until a profile is installed (no drift)
# ---------------------------------------------------------------------------

def test_entity_without_profile_returns_none():
    e = Entity(name="e", hp=100)
    assert e.damage_multiplier_for("fire") is None


def test_entity_untyped_hit_is_never_priced():
    e = Entity(name="e", hp=100, damage_multiplier=band_damage_multipliers(18))
    assert e.damage_multiplier_for(None) is None


def test_entity_returns_installed_band_multiplier():
    e = Entity(name="e", hp=100, damage_multiplier=band_damage_multipliers(18))
    assert e.damage_multiplier_for("fire") == pytest.approx(band_damage_multiplier(18, "fire"))


# ---------------------------------------------------------------------------
# resolve_damage: mult(t) reduces typed outgoing damage by exactly the factor
# ---------------------------------------------------------------------------

def test_mult_reduces_typed_outgoing_by_documented_factor():
    """A fire hit on the 17+ band enemy lands at round(raw * 0.64)."""
    enemy = Entity(name="enemy", hp=10**9, damage_multiplier=band_damage_multipliers(18))
    total = _resolve(_flat_damage_event(enemy, "fire", 100))
    assert total == round(100 * band_damage_multiplier(18, "fire"))   # 64


def test_different_types_priced_independently_on_same_enemy():
    """Each typed event is multiplied by its OWN mult — fire and radiant differ on the
    same enemy (the per-type pricing riders rely on)."""
    enemy = Entity(name="enemy", hp=10**9, damage_multiplier=band_damage_multipliers(18))
    fire = _resolve(_flat_damage_event(enemy, "fire", 200))
    radiant = _resolve(_flat_damage_event(enemy, "radiant", 200))
    assert fire == round(200 * band_damage_multiplier(18, "fire"))
    assert radiant == round(200 * band_damage_multiplier(18, "radiant"))
    assert fire != radiant


def test_mult_emits_mitigation_channel():
    """The §13 mitigation channel records OUTGOING before/after by type."""
    enemy = Entity(name="enemy", hp=10**9, damage_multiplier=band_damage_multipliers(18))
    tel = CombatTelemetry()
    total = _resolve(_flat_damage_event(enemy, "fire", 100), telemetry=tel)
    cell = tel.mitigation["fire"]
    assert cell.outgoing_before == 100
    assert cell.outgoing_after == total
    assert cell.outgoing_after < cell.outgoing_before     # fire IS mitigated at 17+


def test_force_outgoing_recorded_but_not_mitigated():
    """With the profile installed, FORCE damage is still recorded (full typed breakdown)
    but before == after (mult 1.0) — nothing is lost."""
    enemy = Entity(name="enemy", hp=10**9, damage_multiplier=band_damage_multipliers(18))
    tel = CombatTelemetry()
    total = _resolve(_flat_damage_event(enemy, "force", 100), telemetry=tel)
    assert total == 100
    assert tel.mitigation["force"].outgoing_before == tel.mitigation["force"].outgoing_after == 100


# ---------------------------------------------------------------------------
# res/imm/vuln check OFF (default — no profile): no drift, no mitigation records
# ---------------------------------------------------------------------------

def test_res_check_off_no_drift():
    """No profile installed (the default) → a typed hit deals its full raw damage, exactly
    as before this step — the §7 toggle defaults OFF, zero baseline drift."""
    enemy = Entity(name="enemy", hp=10**9)            # no damage_multiplier
    assert _resolve(_flat_damage_event(enemy, "fire", 100)) == 100


def test_res_check_off_records_no_mitigation():
    enemy = Entity(name="enemy", hp=10**9)
    tel = CombatTelemetry()
    _resolve(_flat_damage_event(enemy, "fire", 100), telemetry=tel)
    assert tel.mitigation == {}


def test_untyped_hit_unchanged_even_with_profile():
    """An untyped hit (damage_type None) declares no type to price → full damage, no record,
    even against an enemy carrying a profile."""
    enemy = Entity(name="enemy", hp=10**9, damage_multiplier=band_damage_multipliers(18))
    tel = CombatTelemetry()
    assert _resolve(_flat_damage_event(enemy, None, 100), telemetry=tel) == 100
    assert tel.mitigation == {}


# ---------------------------------------------------------------------------
# End-to-end: the character attacks the enemy dummy → mitigation on sched.telemetry
# ---------------------------------------------------------------------------

def test_mitigation_flows_through_scheduler_telemetry():
    """The §11 framing: a typed hit on the band-profiled enemy dummy is mitigated by
    `mult(t)` and surfaces on the scheduler's telemetry (the seam the reporting layer
    reads) — confirming the sink is threaded through resolution, not just a direct call."""
    char = Entity(name="char", hp=10**6)
    enemy = Entity(name="enemy", hp=10**9, damage_multiplier=band_damage_multipliers(18))
    sched = Scheduler(rng=SeededRNG(1), entities=[char, enemy], policies={}, max_rounds=1)
    sched.queue.push(DamageEvent(
        tick=make_tick(1, 0, 5), actor=char, target=enemy,
        damage_dice=(0, 0), damage_bonus=100, damage_type="fire", cost="none",
    ))
    sched.run()
    cell = sched.telemetry.mitigation["fire"]
    assert cell.outgoing_before == 100
    assert cell.outgoing_after == round(100 * band_damage_multiplier(18, "fire"))
