"""test_zone_buff_aura.py — substrate #7 / 7b ZONE / EMANATION, the BUFF flavor
(round-2 slice, session 24).

The session-23 7b core built the DAMAGE flavor (Spirit Guardians: a zone that FIRES a
recurring save-for-half on the enemies inside).  This is its mirror: a buff AURA that
confers a benefit on the FRIENDLY creatures inside instead — **Circle of Power** (2024
**Paladin** 5th-level abjuration, web-verified before modeling; NOT a cleric spell,
contrary to the old design-note attribution).  A 30-ft emanation anchored to the caster; each
friendly creature inside (including the caster) has ADVANTAGE on saving throws vs spells
and magical effects, and on a SUCCESS vs a save-for-half spell takes NO damage.

Because Circle of Power has no RAW vehicle in the (Cleric) silvertail, this validates
the MECHANISM with a synthetic vehicle (a caster owning the aura + a beneficiary ally +
a save-forcing enemy), exactly as session 19's 7c ally-effects used a synthetic ally —
per the project steer (validate the mechanism, not build value):

  - Zone.affects selects the owner + designated allies INSIDE (the friendly mirror of
    Zone.contains, which selects the enemies a damaging zone assails);
  - a buffed ally rolls its save vs an enemy spell at ADVANTAGE;
  - a SUCCESSFUL save vs a save-for-half spell takes NO damage (negated), where without
    the aura it would take HALF;
  - a FAILED save still takes full (the buff rescues a success, not a fail);
  - the buff applies ONLY to spells / magical effects (a non-spell save is unaffected);
  - an ally that LEAVES (move_entity) loses it; an anchored aura follows its owner;
  - a dropped concentration / destroyed aura winks the buff out (Entity.remove_effect).

Validation framing: engine seams via deterministic FakeRNG; one directional check under
the real SeededRNG.  A damaging zone fires a recurring SaveDamageEvent; a buff aura
fires nothing — it is queried on demand at save resolution (CLAUDE.md #6).
"""

import logging

from src.entity import Entity
from src.policy import Choice
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.zones import (
    DEFAULT_ZONE,
    Zone,
    ZoneBuffSpec,
    ZoneEffectSpec,
    move_entity,
)

logging.disable(logging.CRITICAL)


class FakeRNG:
    """Pops preloaded values; d20 / damage all go through .roll.  A save at advantage
    pops TWO d20s (max); a straight save pops one."""

    def __init__(self, values):
        self._values = list(values)

    def roll(self, n, sides):
        return [self._values.pop(0) for _ in range(n)]

    def roll_one(self, sides):
        return self.roll(1, sides)[0]


class _NoOp:
    """A policy that takes no action — its entity still gets turns but emits nothing."""

    def decide(self, snapshot):
        return []


class _CastSaveSpell:
    """An enemy policy that casts a save-for-half spell at a fixed target each turn —
    the save-forcing pressure a buff aura is meant to blunt."""

    def __init__(self, target, *, dice=(2, 8), on_save="half", is_spell=True,
                 save_stat="dex_save"):
        self._target = target
        self._dice = dice
        self._on_save = on_save
        self._is_spell = is_spell
        self._save_stat = save_stat

    def decide(self, snapshot):
        return [Choice(
            action_type="save_spell",
            cost="action",
            target=self._target,
            save_stat=self._save_stat,
            dc_stat="spell_save_dc",
            damage_dice=self._dice,
            on_save=self._on_save,
            damage_type="fire",
            is_spell=self._is_spell,
        )]


def _power_aura(owner, *, beneficiaries=()):
    """A Circle-of-Power buff aura anchored to *owner*, benefiting the given allies
    (the owner always benefits — "including you")."""
    return Zone(
        name="circle_of_power",
        owner=owner,
        effect_source="circle_of_power",
        buff=ZoneBuffSpec(save_advantage_vs_magic=True, success_negates_half=True),
        anchored_to=owner,
        beneficiaries={e.id for e in beneficiaries},
    )


# ===========================================================================
# (1) Zone.affects — the friendly-polarity membership (mirror of contains)
# ===========================================================================

def test_buff_aura_affects_owner_and_designated_allies_inside():
    owner = Entity(name="owner", hp=10, base_stats={})
    ally = Entity(name="ally", hp=10, base_stats={})
    enemy = Entity(name="enemy", hp=10, base_stats={})
    zone = _power_aura(owner, beneficiaries=(ally,))
    assert zone.affects(owner) is True     # "including you"
    assert zone.affects(ally) is True      # a designated friendly creature inside
    assert zone.affects(enemy) is False    # an enemy inside gets no friendly buff


def test_move_out_of_buff_aura_loses_it_and_anchored_follows_owner():
    owner = Entity(name="owner", hp=10, base_stats={})
    ally = Entity(name="ally", hp=10, base_stats={})
    zone = _power_aura(owner, beneficiaries=(ally,))
    assert zone.affects(ally) is True
    move_entity(ally, "ranged")            # the ally steps out of the aura
    assert zone.affects(ally) is False
    move_entity(owner, "ranged")           # the aura (anchored) follows the caster
    assert zone.affects(ally) is True      # owner + ally now share "ranged"


def test_destroyed_buff_aura_affects_nobody():
    owner = Entity(name="owner", hp=10, base_stats={})
    ally = Entity(name="ally", hp=10, base_stats={})
    zone = _power_aura(owner, beneficiaries=(ally,))
    zone.destroyed = True
    assert zone.affects(ally) is False


def test_damaging_and_buff_zones_have_opposite_polarity():
    # A damaging zone confers no buff (affects → False); a buff aura assails nobody
    # (contains → False).  The two flavors don't bleed into each other.
    owner = Entity(name="owner", hp=10, base_stats={})
    enemy = Entity(name="enemy", hp=10, base_stats={})
    dmg = Zone(name="sg", owner=owner, effect_source="sg",
               effect=ZoneEffectSpec(damage_type="radiant"), anchored_to=owner)
    buff = _power_aura(owner)
    assert dmg.affects(enemy) is False     # a damaging zone is not a buff aura
    assert buff.contains(enemy) is False   # a buff aura is not a damaging zone


# ===========================================================================
# (2) Lifecycle — remove_effect winks the buff aura out
# ===========================================================================

def test_remove_effect_destroys_the_buff_aura_and_clears_concentration():
    owner = Entity(name="owner", hp=10, base_stats={})
    zone = _power_aura(owner)
    owner.concentration = "circle_of_power"
    owner.note_effect_zone("circle_of_power", zone)
    owner.remove_effect("circle_of_power")     # a broken concentration routes here
    assert zone.destroyed is True
    assert owner.concentration is None


# ===========================================================================
# (3) Scheduler — the buff is queried at save resolution (advantage + negate)
# ===========================================================================

def _buff_scheduler(rng, *, max_rounds, with_buff=True, ally_zone=DEFAULT_ZONE,
                    on_save="half", is_spell=True):
    caster = Entity(name="caster", hp=100, base_stats={"spell_save_dc": 16})
    ally = Entity(name="ally", hp=100, base_stats={"dex_save": 0, "ac": 10})
    enemy = Entity(name="enemy", hp=100, base_stats={"spell_save_dc": 15, "ac": 10})
    ally.zone = ally_zone
    sch = Scheduler(
        rng=rng,
        entities=[caster, ally, enemy],
        policies={
            caster.id: _NoOp(),
            ally.id: _NoOp(),
            enemy.id: _CastSaveSpell(ally, on_save=on_save, is_spell=is_spell),
        },
        max_rounds=max_rounds,
    )
    zone = None
    if with_buff:
        zone = _power_aura(caster, beneficiaries=(ally,))
        sch.zones[zone.name] = zone
    return sch, caster, ally, enemy, zone


def test_buff_aura_grants_advantage_on_the_save():
    # The first d20 (1) would FAIL vs DC 15; advantage rolls a second (20) and takes the
    # max → the save SUCCEEDS (and, being save-for-half + negate, deals nothing).
    sch, _c, ally, enemy, _z = _buff_scheduler(FakeRNG([1, 20]), max_rounds=1)
    sch.run()
    assert sch.damage_by_source_target.get((enemy.id, ally.id), 0) == 0
    assert ally.saving_throws_made == 1
    assert ally.saving_throws_failed == 0      # advantage rescued the save


def test_successful_save_negates_only_with_the_aura():
    # WITH the aura: a made save vs a save-for-half spell takes NO damage.
    sch_b, _c, ally_b, enemy_b, _ = _buff_scheduler(FakeRNG([20, 1]), max_rounds=1)
    sch_b.run()
    assert sch_b.damage_by_source_target.get((enemy_b.id, ally_b.id), 0) == 0
    # WITHOUT the aura: the same made save takes HALF (2d8 = 6 → 3).
    sch_n, _c2, ally_n, enemy_n, _ = _buff_scheduler(
        FakeRNG([20, 3, 3]), max_rounds=1, with_buff=False)
    sch_n.run()
    assert sch_n.damage_by_source_target[(enemy_n.id, ally_n.id)] == 3


def test_buff_does_not_rescue_a_failed_save():
    # A failed save (advantage, both d20s = 1) takes FULL even inside the aura — the
    # buff converts a SUCCESS to no-damage, it does not save you on a fail.
    sch, _c, ally, enemy, _z = _buff_scheduler(FakeRNG([1, 1, 3, 3]), max_rounds=1)
    sch.run()
    assert sch.damage_by_source_target[(enemy.id, ally.id)] == 6     # full 2d8
    assert ally.saving_throws_failed == 1


def test_buff_aura_only_affects_spells_and_magic():
    # A NON-spell save (is_spell=False) is unaffected: no advantage (one d20), no negate
    # — a made save still takes HALF.
    sch, _c, ally, enemy, _z = _buff_scheduler(
        FakeRNG([20, 3, 3]), max_rounds=1, is_spell=False)
    sch.run()
    assert sch.damage_by_source_target[(enemy.id, ally.id)] == 3     # half, not negated


def test_ally_outside_the_aura_is_not_buffed():
    # An ally standing in a different zone gets no advantage and no negate (one d20; a
    # made save takes half).
    sch, _c, ally, enemy, _z = _buff_scheduler(
        FakeRNG([20, 3, 3]), max_rounds=1, ally_zone="ranged")
    sch.run()
    assert sch.damage_by_source_target[(enemy.id, ally.id)] == 3     # half (no buff)


def test_destroyed_aura_no_longer_buffs_in_the_scheduler():
    # A dropped concentration winked the aura out → the ally rolls a straight save and
    # a success takes half again (one d20).
    sch, _c, ally, enemy, zone = _buff_scheduler(FakeRNG([20, 3, 3]), max_rounds=1)
    zone.destroyed = True
    sch.run()
    assert sch.damage_by_source_target[(enemy.id, ally.id)] == 3     # half — no buff


# ===========================================================================
# (4) Directional integration under the real SeededRNG
# ===========================================================================

def test_buff_aura_reduces_enemy_spell_damage_directionally():
    # Over many enemy save-for-half spells, the buffed ally (advantage + success→none)
    # takes strictly LESS than the unbuffed ally.  Directional (NOT number-matching).
    def total(with_buff, seed, rounds=80):
        sch, _c, ally, enemy, _z = _buff_scheduler(
            SeededRNG(seed), max_rounds=rounds, with_buff=with_buff)
        sch.run()
        return sch.damage_by_source_target.get((enemy.id, ally.id), 0)

    assert total(True, 11) < total(False, 11)
