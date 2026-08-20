"""
test_healing.py — the healing subsystem (design/healing.md).

Four parts, matching the §9 build plan:
  1. the summon-category enum (§6) — {threshold, vanishes, downed} + on-zero effect;
  2. the `heal` verb and its phase order (§9.1);
  3. the source-attributed healing ledger / §13 telemetry channel (§9.2);
  4. Hit Dice, which are TWO DIFFERENT RULES (§7 a/b2) — spend-all at the short rest
     for characters, spend-to-the-deficit after each combat for summons.

The framing test the whole subsystem exists to support is at the bottom: healing a
MORTAL summon keeps it acting.  That is the one place healing changes behaviour
([[validate-mechanism-not-build-value]]) — everywhere else healing is pure
observation and must move nothing.
"""

from __future__ import annotations

import logging

import pytest

from src.entity import ZERO_HP_CATEGORIES, Entity
from src.resources import ResourceEntry, ResourcePool

logging.disable(logging.CRITICAL)


def _summon(category: str, hp: int = 20) -> Entity:
    e = Entity(name=f"{category}-summon", hp=hp, base_stats={"ac": 15})
    e.zero_hp_category = category
    return e


# ---------------------------------------------------------------------------
# 1. Summon categories (§6)
# ---------------------------------------------------------------------------

def test_category_vocabulary_is_closed_and_defaults_to_threshold():
    assert ZERO_HP_CATEGORIES == ("threshold", "vanishes", "downed")
    assert Entity(name="Char", hp=40).zero_hp_category == "threshold"


def test_threshold_entity_ignores_zero_hp_entirely():
    """The character model: `hp` is a signed balance and nothing gates on it."""
    e = Entity(name="Char", hp=10)
    e.take_damage(30)
    assert e.hp == -20
    assert not e.destroyed and not e.downed and not e.is_out_of_action


def test_vanishes_summon_is_destroyed_permanently_and_absorbs_no_healing():
    e = _summon("vanishes", hp=10)
    e.take_damage(12)
    assert e.destroyed and e.is_out_of_action
    e.heal(50)
    assert e.destroyed, "a vanished summon cannot be healed back (healing.md §4)"
    assert e.hp <= 0


def test_downed_summon_floors_at_zero_and_heals_back_into_the_fight():
    """The REVERSIBLE state `destroyed` cannot express (§6)."""
    e = _summon("downed", hp=10)
    e.take_damage(40)
    assert e.hp == 0, "floored at 0 so a heal does not have to climb out of a hole"
    assert e.downed and e.is_out_of_action and not e.destroyed
    e.heal(5)
    assert e.hp == 5
    assert not e.downed and not e.is_out_of_action


def test_on_zero_effect_fires_once_for_either_summon_category():
    """§6 case 3 — the reanimator's companion fires a death effect but stays
    revivable.  Cases 2 and 3 differ only by this effect, not by class."""
    fired: list[str] = []
    for category in ("vanishes", "downed"):
        e = _summon(category, hp=8)
        e.on_zero_hp = lambda ent: fired.append(ent.zero_hp_category)
        e.take_damage(10)
        e.take_damage(10)                      # already at 0 — must not re-fire
    assert fired == ["vanishes", "downed"]


def test_legacy_boolean_view_still_means_vanishes():
    """`dies_at_zero_hp` is the property over the enum, so every pre-existing call
    site (day_runner's long rest, silvertail's factory, the survival tests) reads
    and writes the enum unchanged."""
    e = Entity(name="Beast", hp=25)
    assert e.dies_at_zero_hp is False
    e.dies_at_zero_hp = True
    assert e.zero_hp_category == "vanishes" and e.dies_at_zero_hp is True
    e.dies_at_zero_hp = False
    assert e.zero_hp_category == "threshold"


# ---------------------------------------------------------------------------
# 1b. The healing CAP follows the category, not the roster role (§4)
# ---------------------------------------------------------------------------

def test_threshold_entities_are_uncapped_summons_are_capped():
    char = Entity(name="Char", hp=40)
    char.take_damage(10)
    char.heal(100)
    assert char.hp == 130, "no max_hp cap where hp is a signed balance (§2/§4)"

    for category in ("vanishes", "downed"):
        s = _summon(category, hp=20)
        s.take_damage(5)
        s.heal(100)
        assert s.hp == 20, f"{category} summon capped at max_hp (§4)"


# ---------------------------------------------------------------------------
# 2. The heal VERB and its phase order (§9.1)
# ---------------------------------------------------------------------------

from src.healing import (                                          # noqa: E402
    HEALING_BONUS_STAT,
    HEALING_PHASE,
    HealSpec,
    HitDiceSpec,
    attach_hit_dice,
    resolve_healing,
    spend_hit_dice_at_short_rest,
    spend_summon_hit_dice,
)
from src.modifiers import Modifier                                 # noqa: E402
from src.rng import SeededRNG                                      # noqa: E402
from src.telemetry import CombatTelemetry                          # noqa: E402


def test_heal_phases_h4_h5_h6_compose():
    """Pool + flat + the caster's ability modifier + an AMPLIFIER rider."""
    caster = Entity(name="Cleric", hp=40, base_stats={"wis_mod": 3})
    target = Entity(name="Ally", hp=40)
    target.take_damage(30)
    # H6: Chalice-style amplifier, a flat +5 on the caster's healing_bonus stat.
    caster.add_modifier(Modifier(stat=HEALING_BONUS_STAT, value=5,
                                 source="chalice", phase=HEALING_PHASE))
    applied = resolve_healing(
        caster,
        HealSpec(dice=(2, 8), flat=1, ability_stat="wis_mod", targets=[target]),
        mean_field=True,
    )
    # H2 mean-field 2d8 = 9.0, +1 flat, +3 WIS, +5 amplifier = 18.0
    assert applied == {target.id: 18.0}


def test_mean_field_draws_no_dice_which_is_what_keeps_parity_alive():
    """The §12 parity proof lives on this line: out-of-combat healing must not
    touch the shared RNG stream, or every subsequent die in every build shifts."""
    caster = Entity(name="Cleric", hp=40)
    control = SeededRNG(seed=99)
    healed = SeededRNG(seed=99)
    resolve_healing(caster, HealSpec(dice=(2, 8)), healed, mean_field=True)
    # Identical seeds, one of which has had a mean-field heal resolved against it:
    # the next 10 draws must still match exactly.
    assert healed.roll(10, 20) == control.roll(10, 20)


def test_in_combat_heal_rolls_and_a_capped_target_ledgers_only_what_APPLIED():
    """H7/H8 record the APPLIED figure, not the rolled one — the thing that keeps
    'healing provided by the summon' from overstating what happened."""
    caster = Entity(name="Cleric", hp=40)
    summon = _summon("downed", hp=20)
    summon.take_damage(3)                        # deficit of only 3
    tel = CombatTelemetry()
    applied = resolve_healing(
        caster, HealSpec(dice=(10, 8), targets=[summon]),
        SeededRNG(seed=1), telemetry=tel, context="combat",
    )
    assert applied == {summon.id: 3}
    assert tel.healing_total(source_ids={caster.id}) == 3
    assert summon.hp == summon.max_hp


def test_heal_on_a_vanished_summon_applies_and_ledgers_nothing():
    caster = Entity(name="Cleric", hp=40)
    gone = _summon("vanishes", hp=10)
    gone.take_damage(15)
    tel = CombatTelemetry()
    assert resolve_healing(caster, HealSpec(flat=50, targets=[gone]),
                           mean_field=True, telemetry=tel) == {}
    assert tel.healing == {}


# ---------------------------------------------------------------------------
# 3. The SOURCE-ATTRIBUTED ledger / §13 channel (§9.2)
# ---------------------------------------------------------------------------

def test_ledger_attributes_source_target_and_context_separately():
    """The per-metric ritual's roster-scoping check: an aggregate ledger would pool
    the character's and the summon's healing into one unreadable number."""
    char = Entity(name="Char", hp=40)
    summon = Entity(name="Summon", hp=20)
    tel = CombatTelemetry()
    resolve_healing(char, HealSpec(flat=10, targets=[summon]),
                    mean_field=True, telemetry=tel, context="combat")
    resolve_healing(summon, HealSpec(flat=4, targets=[char]),
                    mean_field=True, telemetry=tel, context="combat")
    resolve_healing(char, HealSpec(flat=7, targets=[char]),
                    mean_field=True, telemetry=tel, context="between")

    assert tel.healing_by_source() == {char.id: 17.0, summon.id: 4.0}
    assert tel.healing_by_target() == {summon.id: 10.0, char.id: 11.0}
    assert tel.healing_by_context() == {"combat": 14.0, "between": 7.0}
    # "healing PROVIDED to others" — the metric §8 names — is source minus self-cells.
    assert tel.healing_total(source_ids={char.id}, target_ids={summon.id}) == 10.0
    # And the in/between split §11.1 insists must not be pooled:
    assert tel.healing_total(source_ids={char.id}, context="between") == 7.0


def test_healing_channel_rejects_an_unknown_context():
    with pytest.raises(ValueError):
        CombatTelemetry().record_healing(1, 2, 5.0, "mid-air")


def test_day_and_combat_telemetry_merge_the_healing_channel():
    a, b = CombatTelemetry(), CombatTelemetry()
    a.record_healing(1, 1, 3.0, "combat")
    b.record_healing(1, 1, 4.0, "combat")
    b.record_healing(1, 2, 5.0, "between")
    a.merge(b)
    assert a.healing_total(source_ids={1}) == 12.0
    assert a.healing[(1, 1, "combat")].events == 2


# ---------------------------------------------------------------------------
# 4. Hit Dice — TWO rules (§7 a / b2)
# ---------------------------------------------------------------------------

def _character_with_hd(dice, con_mod=0, **kw) -> Entity:
    e = Entity(name="Char", hp=100)
    return attach_hit_dice(e, HitDiceSpec(dice=dice, con_mod=con_mod,
                                          rule="character", **kw))


def test_character_rule_spends_ALL_dice_mean_field_and_uncapped():
    """Rule (a): potential healing.  Every die counts, because nothing reads a
    character's hp — so the figure is a property of the BUILD, not of when damage
    happened to land."""
    char = _character_with_hd([(2, 10), (3, 8)], con_mod=-1)   # 2*4.5 + 3*3.5 = 19.5
    tel = CombatTelemetry()
    healed = spend_hit_dice_at_short_rest([char], tel)
    assert healed == {char.id: 19.5}
    assert char.resources.available("hit_dice") == 0
    assert char.hp == 119.5, "uncapped: hp is a signed balance (§2/§4)"
    assert tel.healing_total(source_ids={char.id}, context="between") == 19.5


def test_negative_con_floors_each_die_at_zero():
    """RAW a Hit Die can never reduce your hit points — and the War Angel has CON 8,
    so this is not a theoretical corner."""
    char = _character_with_hd([(4, 4)], con_mod=-5)     # each die -> max(0, 2.5 - 5)
    assert char.hit_dice.mean_field_value(4) == 0.0
    assert spend_hit_dice_at_short_rest([char]) == {}
    assert char.hp == 100, "no healing, and certainly no DAMAGE from a Hit Die"


def test_second_window_is_a_no_op_because_hit_dice_restore_only_on_a_LONG_rest():
    """The §11.2 correction, made harmless: 2024 Prayer of Healing grants Short Rest
    benefits and therefore a genuine second Hit Dice window — but spend-all drains
    the pool at whichever window comes first, so one window and two give the same
    day total."""
    char = _character_with_hd([(4, 8)], con_mod=2)
    first = spend_hit_dice_at_short_rest([char])
    second = spend_hit_dice_at_short_rest([char])
    assert first == {char.id: 26.0} and second == {}


def test_a_build_may_RESERVE_its_hit_dice_for_something_else():
    """Contested Hit Dice are a build-POLICY question (§7).  The Starfire Scion
    spends all of its dice on Fueled Spellfire and answers 0 here; without that the
    engine's spend-all would silently drain the pool its damage depends on."""
    char = _character_with_hd([(5, 8)], con_mod=2,
                              available_for_healing=lambda e: 0)
    assert spend_hit_dice_at_short_rest([char]) == {}
    assert char.resources.available("hit_dice") == 5


def test_an_entity_with_no_hit_dice_simply_never_heals_this_way():
    """The rule degrading gracefully rather than needing a special case (§10.5)."""
    plain = Entity(name="Dummy", hp=10 ** 9)
    assert spend_hit_dice_at_short_rest([plain]) == {}
    assert spend_summon_hit_dice([plain]) == {}


def _summon_with_hd(n, sides=8, con_mod=2, hp=25, category="vanishes") -> Entity:
    e = _summon(category, hp=hp)
    return attach_hit_dice(e, HitDiceSpec(dice=[(n, sides)], con_mod=con_mod,
                                          rule="summon"))


def test_summon_rule_spends_to_the_DEFICIT_not_to_full():
    """Rule (b2): ACTUAL healing.  A lightly-damaged companion keeps dice for later,
    which is what makes the pool a real resource rather than a fixed bonus."""
    beast = _summon_with_hd(4)                       # 4d8 + 2 -> 6.5 per die
    beast.take_damage(6)
    healed = spend_summon_hit_dice([beast])
    assert healed == {beast.id: 6}, "capped at the deficit, so it never overheals"
    assert beast.resources.available("hit_dice") == 3, "one die spent, three kept"
    assert beast.hp == beast.max_hp


def test_summon_pool_is_the_BINDING_CONSTRAINT_and_depletes():
    """The depletion curve §7(b2) exists to show: once the pool empties, later
    combats get nothing."""
    beast = _summon_with_hd(2)                       # 13.0 hp of pool, max_hp 25
    beast.take_damage(24)
    assert spend_summon_hit_dice([beast]) == {beast.id: 13.0}
    assert beast.resources.available("hit_dice") == 0
    assert beast.hp == 14, "topped up only as far as the pool reached"
    beast.take_damage(10)
    assert spend_summon_hit_dice([beast]) == {}, "pool empty — later combats get none"


def test_a_revived_summon_has_zero_deficit_so_hit_dice_are_a_no_op():
    """The ordering §7(b2) fixes: `recast` revives at FULL HP first, after which
    this rule must do nothing."""
    beast = _summon_with_hd(4)
    beast.take_damage(30)
    assert beast.destroyed
    beast.destroyed, beast.hp = False, beast.max_hp          # what `recast` does
    assert spend_summon_hit_dice([beast]) == {}
    assert beast.resources.available("hit_dice") == 4


def test_a_destroyed_summon_cannot_be_helped_by_hit_dice():
    beast = _summon_with_hd(4)
    beast.take_damage(30)
    assert beast.destroyed
    assert spend_summon_hit_dice([beast]) == {}
    assert beast.resources.available("hit_dice") == 4, "dice not burned on a corpse"


# ---------------------------------------------------------------------------
# 5. THE MECHANISM TEST WITH TEETH — healing a mortal summon keeps it acting
# ---------------------------------------------------------------------------
# Everywhere else in this subsystem healing is pure observation: a character's hp is
# behaviourally inert (§3), Hit Dice are mean-field, and the ledger cannot move a
# die.  These two tests are the ONE place healing changes what happens, which is
# what [[validate-mechanism-not-build-value]] asks a slice to demonstrate.

def test_healing_a_DOWNED_summon_puts_it_back_in_the_turn_order():
    """The reversible state, end to end through the scheduler."""
    from src.policy import Choice
    from src.scheduler import Scheduler

    beast = _summon("downed", hp=10)
    beast.base_stats.update({"attack_bonus": 20, "damage_dice": (1, 6), "damage_bonus": 3})
    target = Entity(name="Dummy", hp=10 ** 9, base_stats={"ac": 1})

    class Swing:
        def decide(self, snapshot):
            return [Choice(action_type="attack", target=target)]

    beast.take_damage(30)
    assert beast.downed
    sched = Scheduler(rng=SeededRNG(seed=4), entities=[beast, target],
                      policies={beast.id: Swing()}, max_rounds=3)
    assert sum(sched.run()) == 0, "a downed summon takes no turns"

    beast.heal(4)
    assert not beast.downed and beast.hp == 4
    sched2 = Scheduler(rng=SeededRNG(seed=4), entities=[beast, target],
                       policies={beast.id: Swing()}, max_rounds=3)
    assert sum(sched2.run()) > 0, "healed above 0 → it acts again"


def test_summon_hit_dice_keep_a_MORTAL_companion_alive_into_a_later_combat():
    """The day-level version: a `vanishes` summon that survives a combat damaged
    spends dice between combats, and that is what carries it through the next one.

    Constructed rather than taken from Silvertail because Silvertail exercises this
    only RARELY: its mortal beast usually dies inside a combat, and the rule needs it
    to end one ALIVE and damaged.  That does happen (healing.md §11.4 measures it —
    every `mortal_beast=True` scenario moves, and only those), but it is too
    infrequent to make a crisp assertion out of.  So the mechanism is shown here on a
    scenario built to reach the boundary alive, and the build-level effect is
    reported as a measurement rather than asserted seed by seed.
    """
    from src.day_runner import DayRunner
    from src.policy import Choice

    def build():
        beast = _summon_with_hd(4, hp=25)                    # 26.0 hp of pool
        beast.base_stats.update({"attack_bonus": 20, "damage_dice": (1, 6),
                                 "damage_bonus": 3})
        biter = Entity(name="Biter", hp=10 ** 9,
                       base_stats={"attack_bonus": 20, "damage_dice": (0, 6),
                                   "damage_bonus": 6, "ac": 1})

        class Bite:
            def decide(self, snapshot):
                return [Choice(action_type="attack", target=beast)]

        class Swing:
            def decide(self, snapshot):
                return [Choice(action_type="attack", target=biter)]

        return beast, biter, Swing(), Bite()

    def day(hit_dice_on: bool) -> float:
        beast, biter, swing, bite = build()
        if not hit_dice_on:
            beast.hit_dice = None                            # the rule switched off
        runner = DayRunner(rng=SeededRNG(seed=11), entities=[beast, biter],
                           policies={beast.id: swing, biter.id: bite})
        return runner.run_day().damage_by_source(beast.id)

    without = day(hit_dice_on=False)
    with_hd = day(hit_dice_on=True)
    assert with_hd > without, (
        "summon Hit Dice must buy the companion more live rounds — this is the one "
        f"place healing changes behaviour (got {with_hd} vs {without})"
    )
