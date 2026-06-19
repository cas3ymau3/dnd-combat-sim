"""test_zone_emanation.py — substrate #7 / 7b ZONE / EMANATION (session 23).

The LAST unbuilt #7 sub-kind: a created **Object** (design.md §1) defining a named
zone (§3.1) whose recurring effect fires on the creatures **inside** it at their turn
boundaries.  Vehicle: the silvertail's **Spirit Guardians** at char L10 — a 15-ft
emanation anchored to the caster, forcing a Wisdom save-for-half (3d8 radiant) on each
enemy inside (2024 text web-verified before modeling).

These validate the MECHANISM (NOT build value — per the project steer):
  - a damaging zone fires RECURRINGLY on an occupant inside, once per its turn;
  - save-for-half (a made save halves; a failed save takes full);
  - the zone's damage is attributed to its OWNER (the caster's zone-DPR column);
  - an occupant that LEAVES (move_entity) escapes it; an ANCHORED emanation follows
    its owner (move the owner → the occupant is now outside);
  - the owner and designated-unaffected allies inside take nothing;
  - a dropped concentration WINKS THE EMANATION OUT (Entity.remove_effect).

Validation framing: engine seams via deterministic FakeRNG; the integration check is
directional off the per-(source, target) ledger over many days, NOT number-matching.
"""

import logging

from src.builds import silvertail as sv
from src.entity import Entity
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.zones import DEFAULT_ZONE, Zone, ZoneEffectSpec, move_entity

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; d20 / damage / percentile all go through .roll."""

    def __init__(self, values):
        self._values = list(values)

    def roll(self, n, sides):
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


class _NoOp:
    """A policy that takes no action — so its entity still gets turns (and thus a
    zone trigger) but emits no choices of its own."""

    def decide(self, snapshot):
        return []


def _radiant_emanation(owner, *, unaffected=()):
    return Zone(
        name="spirit_guardians",
        owner=owner,
        effect_source="spirit_guardians",
        effect=ZoneEffectSpec(
            save_stat="wis_save", dc_stat="spell_save_dc",
            damage_dice=(3, 8), on_save="half", damage_type="radiant", is_spell=True,
        ),
        anchored_to=owner,
        unaffected={owner.id, *(e.id for e in unaffected)},
    )


# ===========================================================================
# (1) Zonal spatial state — Zone.contains + move_entity (§3.1)
# ===========================================================================

def test_entities_share_the_implicit_melee_zone_by_default():
    e = Entity(name="e", hp=10, base_stats={})
    assert e.zone == DEFAULT_ZONE


def test_zone_contains_only_affected_occupants_inside():
    owner = Entity(name="owner", hp=10, base_stats={})
    ally = Entity(name="ally", hp=10, base_stats={})
    enemy = Entity(name="enemy", hp=10, base_stats={})
    zone = _radiant_emanation(owner, unaffected=(ally,))
    # An enemy sharing the owner's zone is inside; the owner and the designated ally
    # are NOT (you designate creatures unaffected — Spirit Guardians).
    assert zone.contains(enemy) is True
    assert zone.contains(owner) is False
    assert zone.contains(ally) is False


def test_move_entity_out_escapes_the_zone():
    owner = Entity(name="owner", hp=10, base_stats={})
    enemy = Entity(name="enemy", hp=10, base_stats={})
    zone = _radiant_emanation(owner)
    assert zone.contains(enemy) is True
    move_entity(enemy, "ranged")          # the enemy leaves the emanation's location
    assert enemy.zone == "ranged"
    assert zone.contains(enemy) is False


def test_anchored_emanation_follows_its_owner():
    # An emanation is wherever the caster stands — moving the OWNER carries the aura
    # with it, so an enemy left behind is now outside.
    owner = Entity(name="owner", hp=10, base_stats={})
    enemy = Entity(name="enemy", hp=10, base_stats={})
    zone = _radiant_emanation(owner)
    assert zone.contains(enemy) is True
    move_entity(owner, "ranged")          # the caster (and its aura) moves away
    assert zone.contains(enemy) is False
    move_entity(enemy, "ranged")          # the enemy follows back in
    assert zone.contains(enemy) is True


def test_destroyed_zone_contains_nobody():
    owner = Entity(name="owner", hp=10, base_stats={})
    enemy = Entity(name="enemy", hp=10, base_stats={})
    zone = _radiant_emanation(owner)
    zone.destroyed = True
    assert zone.contains(enemy) is False


# ===========================================================================
# (2) Lifecycle — remove_effect winks the emanation out (concentration drop)
# ===========================================================================

def test_remove_effect_destroys_the_zone_and_clears_concentration():
    owner = Entity(name="owner", hp=10, base_stats={})
    zone = _radiant_emanation(owner)
    owner.concentration = "spirit_guardians"
    owner.note_effect_zone("spirit_guardians", zone)
    owner.remove_effect("spirit_guardians")     # a broken concentration save routes here
    assert zone.destroyed is True
    assert owner.concentration is None


# ===========================================================================
# (3) Scheduler — the recurring zone trigger (fires each turn, save-for-half)
# ===========================================================================

def _zone_scheduler(rng, *, max_rounds, occupant_zone=DEFAULT_ZONE, owner_zone=DEFAULT_ZONE):
    owner = Entity(name="caster", hp=100, base_stats={"spell_save_dc": 16})
    occupant = Entity(name="occupant", hp=100, base_stats={"wis_save": 0, "ac": 10})
    owner.zone = owner_zone
    occupant.zone = occupant_zone
    zone = _radiant_emanation(owner)
    sch = Scheduler(
        rng=rng,
        entities=[owner, occupant],
        policies={owner.id: _NoOp(), occupant.id: _NoOp()},
        max_rounds=max_rounds,
    )
    sch.zones[zone.name] = zone
    return sch, owner, occupant, zone


def test_zone_fires_recurringly_on_an_occupant_each_turn():
    # Failed save (d20=1) every turn → full 3d8 (3+3+3=9) each of the occupant's 3
    # turns.  The recurrence falls out of turns recurring: 3 rounds → 3 saves → 27.
    sch, owner, occupant, _z = _zone_scheduler(
        FakeRNG([1, 3, 3, 3] * 3), max_rounds=3)
    sch.run()
    # Attributed to the OWNER → the caster's zone-DPR column falls out of the ledger.
    assert sch.damage_by_source_target[(owner.id, occupant.id)] == 27
    # The occupant rolled a save each of its turns (recurring, once per turn).
    assert occupant.saving_throws_made == 3
    assert occupant.saving_throws_failed == 3


def test_zone_is_save_for_half():
    # A made save (d20=20 vs DC 16) halves: 3d8=9 → 4.  A failed save takes full 9.
    sch_s, owner_s, occ_s, _ = _zone_scheduler(FakeRNG([20, 3, 3, 3]), max_rounds=1)
    sch_s.run()
    assert sch_s.damage_by_source_target[(owner_s.id, occ_s.id)] == 4   # half of 9
    sch_f, owner_f, occ_f, _ = _zone_scheduler(FakeRNG([1, 3, 3, 3]), max_rounds=1)
    sch_f.run()
    assert sch_f.damage_by_source_target[(owner_f.id, occ_f.id)] == 9   # full


def test_occupant_outside_the_zone_takes_nothing():
    # An occupant standing in a different zone is never assailed (no RNG consumed).
    sch, owner, occupant, _z = _zone_scheduler(
        FakeRNG([]), max_rounds=3, occupant_zone="ranged")
    sch.run()
    assert sch.damage_by_source_target.get((owner.id, occupant.id), 0) == 0
    assert occupant.saving_throws_made == 0


def test_owner_inside_its_own_emanation_is_unaffected():
    # The caster shares the melee blob with the occupant but is the owner → it never
    # makes the save (only the occupant is assailed).
    sch, owner, occupant, _z = _zone_scheduler(
        FakeRNG([1, 3, 3, 3] * 3), max_rounds=3)
    sch.run()
    assert sch.damage_by_source_target.get((owner.id, owner.id), 0) == 0
    assert owner.saving_throws_made == 0


# ===========================================================================
# (4) Integration — Spirit Guardians on the silvertail at char L10
# ===========================================================================

def _run_l10(zone, seed, days=40):
    runner, char, _beast, dummy = sv.make_silvertail_runner(
        10, SeededRNG(seed), zone_effect=zone)
    char_to_dummy = 0
    for _ in range(days):
        res = runner.run_day()
        char_to_dummy += res.damage_source_to(char.id, dummy.id)
    return char_to_dummy, dummy.saving_throws_made


def test_spirit_guardians_forces_recurring_saves_and_adds_zone_dpr():
    # With the emanation the enemy is forced WIS saves while inside it each combat and
    # the recurring radiant raises the caster's own damage column; without it, the
    # enemy is never forced a save and the column is lower (only shocking grasp).
    with_dpr, with_saves = _run_l10("spirit_guardians", 7)
    without_dpr, without_saves = _run_l10(None, 7)
    assert with_saves > 0           # the emanation forced WIS saves on the enemy
    assert without_saves == 0       # no zone → the enemy is never forced a save
    assert with_dpr > without_dpr   # the recurring radiant lifts the caster's column


def test_l10_builds_and_summons_the_companion():
    # The L10 row stands up (master + commanded beast both deal their columns) — the
    # zone is additive beside the existing 7a summon machinery, not a replacement.
    runner, char, beast, _dummy = sv.make_silvertail_runner(
        10, SeededRNG(3), zone_effect="spirit_guardians")
    res = runner.run_day()
    assert res.damage_by_source(beast.id) > 0    # the commanded Beast's Strike column
    assert res.damage_by_source(char.id) > 0     # the master's own column (SG + cantrip)
