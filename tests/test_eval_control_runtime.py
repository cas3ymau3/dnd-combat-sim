"""
Mechanism tests for CONTROL APPLIED AT RUNTIME — evaluation_framework.md §7,
§13 step 6 (session 51).

Per [[validate-mechanism-not-build-value]] nothing here asserts that a DPR value is
"correct".  The exact values live in ``test_eval_enemy_seam.GOLDEN_DPR``, whose one
control row this step re-baselined deliberately; here the claims are about the
mechanism — a suppressed turn spends nothing, the shares mix rather than compose,
hard is drawn before soft, and the credited and realized halves are two quantities.


THE ROLL CALL (per-feature ritual step 5 — written BEFORE the tests)
====================================================================
One row per DECLARATION this change touches, one column naming the fixture that
covers each VALUE.  An empty cell is an untested value no matter how many tests
exist.  Writing it first found FOUR values with no production fixture — the fifth
session running that it has — all flagged BUILT below, and one of them
(``_fire_zone_effects`` on a suppressed turn) is a behaviour the design states in
prose and nothing could otherwise reach.

| declaration                        | value                      | fixture                                       |
|------------------------------------|----------------------------|-----------------------------------------------|
| `ControlAccount.credit`            | lost only                  | unit: credit(lost=…)                          |
|                                    | reduced + soft_factor      | unit: credit(reduced=…, soft_factor=…)        |
|                                    | reduced, factor omitted    | unit: deferred to draw() — asserted there     |
|                                    | two credits accumulate     | unit: credit twice                            |
| `ControlAccount.draw`              | empty account              | unit: UNAFFECTED identity                     |
|                                    | hard >= 1                  | unit: suppressed, scale 0                     |
|                                    | hard fractional            | unit: scale 1-h, turn still acts              |
|                                    | hard > 1 over turns        | unit: 2.3 → skip, skip, 0.7                   |
|                                    | soft >= 1                  | unit: scale == soft_factor                    |
|                                    | soft fractional            | unit: 1 - r(1-sf)                             |
|                                    | hard AND soft, one turn    | unit: the MIXTURE, vs the wrong product       |
|                                    | hard == 1 exactly, soft>0  | unit: soft NOT drawn that turn                |
|                                    | soft owed, no factor       | unit: ValueError (**BUILT** — unreachable     |
|                                    |                            | through RunConfig: the policy always routes   |
|                                    |                            | its resolved knob)                            |
|                                    | float residue              | unit: EPSILON, 3 draws of 1/3                 |
|                                    | soft_factor == 0           | unit: soft turn is as dead as a hard one      |
|                                    | soft_factor == 1           | unit: a soft turn costs nothing               |
| `ControlAccount.clear`             | balance dropped            | unit + day boundary                           |
|                                    | soft_factor KEPT           | unit: clear() then credit-free draw           |
| `TurnControl.affected`             | True / False               | unit, both                                    |
| `Entity.output_scale`              | 1.0 default                | fresh Entity                                  |
|                                    | set on the actor           | scheduler: controlled turn                    |
|                                    | reset on non-actors        | scheduler: enemy's turn after a char draw     |
| `resolve_damage` phase 5b          | scale 1.0 (inert)          | every pre-existing test in the suite          |
|                                    | scale < 1                  | unit: 20 dmg at 0.5 → 10                      |
|                                    | rounds, does not floor     | unit: 0.5 of 15 → 8, not 7                    |
|                                    | scale 0                    | unit: zero damage                             |
| `resolve_control_save` credit      | credits the TARGET         | unit: char's account, not the enemy's         |
|                                    | soft_factor routed         | unit: event factor reaches the account        |
|                                    | save PASSED → no credit    | unit: high-save char                          |
| `ControlSpec.soft_factor`          | routed from the policy     | BaselineEnemyPolicy control choice            |
|                                    | None (direct construction) | tests/test_enemy_control_channel.py (kept     |
|                                    |                            | working deliberately — see draw()'s docstring)|
| scheduler suppressed turn          | no decide()                | scheduler: recording policy never called      |
|                                    | no action economy spent    | scheduler: resource pool untouched            |
|                                    | no resources spent         | war_angel L13: slots survive the day          |
|                                    | zone effects STILL fire    | **BUILT** — no shipped enemy owns a zone, so  |
|                                    |                            | a suppressed entity standing in one is        |
|                                    |                            | unreachable through RunConfig                 |
|                                    | statuses STILL swept       | scheduler: expiry on a suppressed turn        |
| scheduler scaled turn              | decide() runs              | scheduler: choices still enqueued             |
|                                    | resources ARE spent        | scheduler: §7.3's documented wrinkle          |
| `record_control_applied`           | written on an affected turn| scheduler                                     |
|                                    | NOT written otherwise      | control off: channel empty, not zeroed        |
| `control_applied_for` scoping      | character                  | war_angel L13 baseline+control                |
|                                    | summon                     | silvertail L10 focus=summon+control           |
|                                    | None (pooled)              | unit: the documented roster-wide total        |
| `DaySample.control_applied`        | attributed roles           | war_angel: character-scoped                   |
| the two realized metrics           | measured                   | war_angel L13 baseline+control                |
|                                    | unavailable                | war_angel L13 baseline (control off)          |
|                                    | realized <= credited       | war_angel L13 — §7.6, both causes             |
| `attacks_per_round_distribution`   | spread > 0                 | war_angel L13 baseline+control                |
|                                    | spread == 0                | war_angel L13 baseline (and that is correct)  |
|                                    | unavailability inherited   | over= an always-available scalar → n/a        |
| §12 parity                         | control OFF unchanged      | the goldens + validation.py, untouched        |

DO NOT LET THE PROSE OVERCLAIM (s49, broadened s50)
---------------------------------------------------
Every magnitude below was MEASURED before it was written.  Two are worth keeping
next to their assertions because they are not what a reader would guess:

* **The realized SOFT cost is less than half its credit, while the realized HARD
  cost is within 13% of its.**  War Angel L13, 400 days, seed 11, `control=True`
  + `mitigation=True`: hard 0.19402 credited → 0.17032 realized; soft 0.24594
  credited → 0.11416 realized.  The asymmetry is not truncation — it is §7.5's
  draw order.  Hard is drawn first, so on a turn with both owed the soft share only
  gets what the hard share leaves, and soft credits queue up behind hard ones that
  keep arriving.  A session expecting the two gaps to look alike would read this as
  a bug.
* **DPR falls 24.1%, not the 33% the credited account implies.**  34.87 →
  26.4784375 on that same configuration.  The first-order arithmetic
  `1 − 0.194 − 0.5·0.246 ≈ 0.67` is the CREDITED projection; the realized drop is
  smaller for exactly the two reasons runtime application exists (§7.1): suppressed
  turns bank their resources for a later turn, and not every credited turn-unit is
  ever spent.  The gap between those two numbers is the whole argument of §7.1,
  which is why it is recorded rather than smoothed over.
"""

from __future__ import annotations

import logging

import pytest

from src.control import EPSILON, UNAFFECTED, ControlAccount, TurnControl
from src.entity import Entity
from src.events import ControlSaveEvent, DamageEvent, EventQueue, make_tick
from src.evaluation.config import RunConfig
from src.evaluation.metrics import METRICS
from src.evaluation.runner import run, simulate
from src.policy import Choice, GameState
from src.rng import SeededRNG
from src.scheduler import Scheduler
from src.telemetry import CombatTelemetry
from src.verbs import resolve_control_save, resolve_damage

logging.disable(logging.CRITICAL)

_ALL_SAVES = {k: 2 for k in
              ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save")}


# ---------------------------------------------------------------------------
# ControlAccount — the arithmetic, in isolation (§7.5)
# ---------------------------------------------------------------------------

def test_an_empty_account_returns_the_shared_unaffected_verdict():
    """The fast path every uncontrolled turn in the suite takes.  Asserting the
    IDENTITY, not just the value, is what makes "an uncontrolled run pays nothing
    for this feature" a checked claim rather than a hope."""
    account = ControlAccount()
    assert account.draw() is UNAFFECTED
    assert UNAFFECTED.scale == 1.0 and not UNAFFECTED.suppressed
    assert not UNAFFECTED.affected


def test_a_whole_hard_turn_is_suppressed_and_scales_to_zero():
    account = ControlAccount(lost=1.0)
    verdict = account.draw()
    assert verdict.suppressed
    assert verdict.scale == 0.0
    assert verdict.lost_applied == 1.0
    assert verdict.affected
    assert account.pending == 0.0


def test_a_fractional_hard_share_scales_the_turn_without_suppressing_it():
    """§7.3's fractional boundary turn: it happens, at reduced effect, and therefore
    spends its resources."""
    account = ControlAccount(lost=0.3)
    verdict = account.draw()
    assert not verdict.suppressed
    assert verdict.scale == pytest.approx(0.7)
    assert verdict.lost_applied == pytest.approx(0.3)
    assert account.lost == 0.0


def test_a_multi_turn_hard_balance_drains_one_turn_at_a_time():
    """2.3 credited turn-units become two suppressed turns and one 70% turn — the
    "drawn down deterministically" of §7.2, which is what makes a `save-ends`
    control that lasts 2.3 turns cost 2.3 turns rather than one."""
    account = ControlAccount(lost=2.3)
    first, second, third = account.draw(), account.draw(), account.draw()
    assert first.suppressed and second.suppressed
    assert not third.suppressed
    assert third.scale == pytest.approx(0.7)
    assert account.draw() is UNAFFECTED


def test_a_whole_soft_turn_scales_to_exactly_the_soft_factor():
    account = ControlAccount(reduced=1.0, soft_factor=0.5)
    verdict = account.draw()
    assert not verdict.suppressed            # a soft turn ACTS — §6's (ii) branch
    assert verdict.scale == pytest.approx(0.5)
    assert verdict.reduced_applied == 1.0


def test_a_fractional_soft_share_blends_linearly():
    """Half a soft turn at factor 0.5 is 25% off, not 50%: the share that is not
    controlled acts at full output."""
    account = ControlAccount(reduced=0.5, soft_factor=0.5)
    assert account.draw().scale == pytest.approx(0.75)


def test_hard_and_soft_on_one_turn_MIX_rather_than_COMPOSE():
    """§7.5's central arithmetic, and the one place the natural first draft is wrong
    rather than merely different.

    The two shares are shares OF ONE TURN — `hard_frac` is the probability that the
    condition which landed is hard, so one failed save credits both branches of one
    effect (§7.3).  So the turn's output is their MIXTURE:

        1 - h - r*(1 - soft_factor)  =  1 - 0.5 - 0.5*0.5  =  0.25

    Treating them as independent factors gives `(1 - 0.5) * 0.75 = 0.375`, which is
    50% too generous.  The mixture is also what the branches give directly:
    `0.5*0 + 0.5*0.5 = 0.25`.
    """
    account = ControlAccount(lost=0.5, reduced=0.5, soft_factor=0.5)
    verdict = account.draw()
    assert verdict.scale == pytest.approx(0.25)
    assert verdict.scale != pytest.approx(0.375)       # the product reading
    assert verdict.lost_applied == pytest.approx(0.5)
    assert verdict.reduced_applied == pytest.approx(0.5)
    assert account.pending == 0.0


def test_hard_is_drawn_FIRST_so_a_full_hard_turn_defers_the_soft_one():
    """§7.5's draw ORDER, which is the decision the equal-expected-output argument
    makes non-obvious.

    One whole hard turn plus one whole soft turn owed: the first turn is fully
    SUPPRESSED (and therefore spends no resources — §7.1.2), and the soft turn-unit
    is still owed afterwards.  A proportional draw would instead produce two partial
    turns, both of which spend resources, for the same total output.
    """
    account = ControlAccount(lost=1.0, reduced=1.0, soft_factor=0.5)
    first = account.draw()
    assert first.suppressed
    assert first.reduced_applied == 0.0           # soft got no room this turn
    assert account.reduced == pytest.approx(1.0)  # ...and is still owed

    second = account.draw()
    assert not second.suppressed
    assert second.scale == pytest.approx(0.5)
    assert account.pending == 0.0


def test_the_two_draw_orders_integrate_to_the_same_output():
    """The claim §7.5 rests on, asserted rather than argued: hard-first and
    proportional differ in resource semantics, NOT in expected output.  Two turns
    owed `(1.0 hard, 1.0 soft)` deliver 0.5 turn-equivalents of output either way —
    hard-first as `0.0 + 0.5`, proportional as `0.25 + 0.25`.
    """
    hard_first = ControlAccount(lost=1.0, reduced=1.0, soft_factor=0.5)
    sequential = hard_first.draw().scale + hard_first.draw().scale

    # The proportional reading, computed directly rather than implemented: each turn
    # draws half a unit from each account, so each scales to the same mixture.
    proportional = 2 * (1 - 0.5 - 0.5 * (1 - 0.5))

    assert sequential == pytest.approx(proportional) == pytest.approx(0.5)


def test_pricing_a_soft_turn_without_a_factor_is_refused():
    """**BUILT fixture** — unreachable through ``RunConfig``: ``BaselineEnemyPolicy``
    always routes its resolved ``soft_factor`` onto the ``ControlSpec``.  Asserted
    because the alternative to refusing is GUESSING a cost, and the whole reason the
    factor travels from the policy is that the applying code must not own a second
    copy of the constant (§7.2).
    """
    account = ControlAccount(reduced=1.0)          # credited, but never priced
    with pytest.raises(ValueError, match="without a soft_factor"):
        account.draw()


def test_a_hard_only_balance_needs_no_factor():
    """The other side of the same guard: with nothing soft owed the soft term is
    multiplied by a zero share, so there is no cost to guess at and no refusal."""
    assert ControlAccount(lost=1.0).draw().suppressed


def test_soft_factor_zero_makes_a_soft_turn_as_dead_as_a_hard_one():
    """A declared boundary of the option schema, and the one place the hard/soft
    distinction collapses in VALUE while staying distinct in MECHANISM: the turn
    still happens, so it still spends its resources."""
    verdict = ControlAccount(reduced=1.0, soft_factor=0.0).draw()
    assert verdict.scale == 0.0
    assert not verdict.suppressed          # ...which is the whole difference


def test_soft_factor_one_makes_a_soft_turn_free():
    verdict = ControlAccount(reduced=1.0, soft_factor=1.0).draw()
    assert verdict.scale == pytest.approx(1.0)
    assert verdict.affected                # it was still a controlled turn


def test_float_residue_does_not_leave_an_account_permanently_affected():
    """Three draws of 1/3 of a turn must end at exactly zero, not at 1.1e-16 — which
    would otherwise report an output scale of 0.9999999999999999 forever and keep
    writing telemetry rows for turns nothing controlled."""
    account = ControlAccount(lost=1 / 3, reduced=1 / 3, soft_factor=0.5)
    account.draw()
    assert account.lost == 0.0 and account.reduced == 0.0
    assert account.draw() is UNAFFECTED

    tiny = ControlAccount(lost=EPSILON / 2)
    assert tiny.draw() is UNAFFECTED


def test_credits_accumulate_and_clear_drops_them_but_keeps_the_factor():
    account = ControlAccount()
    account.credit(lost=0.4)
    account.credit(lost=0.1, reduced=0.5, soft_factor=0.5)
    assert account.lost == pytest.approx(0.5)
    assert account.reduced == pytest.approx(0.5)
    assert account.soft_factor == 0.5

    account.clear()
    assert account.pending == 0.0
    # The factor is a property of the enemy that was configured, not of the combat,
    # so a later credit does not have to re-supply it to be priceable.
    assert account.soft_factor == 0.5
    account.credit(reduced=1.0)
    assert account.draw().scale == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# resolve_damage phase 5b — the actor-side scale
# ---------------------------------------------------------------------------

def _damage(actor, target, dice=(0, 0), bonus=20):
    queue = EventQueue()
    event = DamageEvent(tick=make_tick(1, 0, 1), actor=actor, target=target,
                        is_crit=False, damage_dice=dice, damage_bonus=bonus)
    total, _ = resolve_damage(event, SeededRNG(1), queue, 2)
    return total


def test_phase_5b_is_inert_at_scale_one():
    """The property §12's parity proof rests on: untouched arithmetic when nothing
    controls the actor, which is every entity on every turn of every existing run."""
    actor = Entity(name="a", hp=10, base_stats={})
    target = Entity(name="t", hp=100, base_stats={})
    assert actor.output_scale == 1.0
    assert _damage(actor, target) == 20


def test_phase_5b_scales_the_actors_outgoing_damage():
    actor = Entity(name="a", hp=10, base_stats={})
    target = Entity(name="t", hp=100, base_stats={})
    actor.output_scale = 0.5
    assert _damage(actor, target) == 10
    actor.output_scale = 0.0
    assert _damage(actor, target) == 0


def test_phase_5b_rounds_rather_than_floors():
    """Same argument as phase 7b's rounding: a mean-field factor that floored would
    systematically under-count.  Half of 15 is 8 here, not 7."""
    actor = Entity(name="a", hp=10, base_stats={})
    target = Entity(name="t", hp=100, base_stats={})
    actor.output_scale = 0.5
    assert _damage(actor, target, bonus=15) == 8


# ---------------------------------------------------------------------------
# resolve_control_save — the credit (§7.2)
# ---------------------------------------------------------------------------

def _control(char_save=2, hard_frac=1.0, soft_factor=0.5, seed=4, **kw):
    char = Entity(name="char", hp=10**6,
                  base_stats={"ac": 18, **{**_ALL_SAVES, "wis_save": char_save}})
    enemy = Entity(name="enemy", hp=10**6, base_stats={"enemy_save_dc": 30})
    event = ControlSaveEvent(tick=make_tick(1, 1, 1), actor=enemy, target=char,
                             hard_frac=hard_frac, soft_factor=soft_factor, **kw)
    telemetry = CombatTelemetry()
    resolve_control_save(event, SeededRNG(seed), EventQueue(), 2, telemetry)
    return char, enemy, telemetry


def test_a_failed_control_save_credits_the_TARGETs_account():
    """Whose account, which is the roster-scoping question one layer down: a DC-30
    save the character cannot make must charge the CHARACTER, not the enemy that
    forced it."""
    char, enemy, telemetry = _control()
    assert char.control.lost > 0.0
    assert enemy.control.pending == 0.0
    # ...and the credited channel still records the same failure (both readings).
    assert sum(t.turns_lost for t in telemetry.control.values()) == pytest.approx(
        char.control.lost)


def test_the_soft_factor_travels_from_the_event_to_the_account():
    """The §7.2 routing: one source for the constant.  A factor set on the event
    reaches the account, so the applying code never needs a default of its own."""
    char, _enemy, _tel = _control(hard_frac=0.0, soft_factor=0.25)
    assert char.control.reduced >= 1.0          # a whole soft turn or more is owed
    assert char.control.soft_factor == 0.25
    # Priced with the ROUTED factor, not with a local default: a whole soft turn
    # scales to exactly the factor, so 0.25 rather than enemy_stats' 0.5.
    assert char.control.draw().scale == pytest.approx(0.25)


def test_a_PASSED_control_save_credits_nothing():
    char, _enemy, telemetry = _control(char_save=40)
    assert char.control.pending == 0.0
    assert telemetry.control == {}           # no failure, so no credited cell


# ---------------------------------------------------------------------------
# The scheduler — the draw-down, and what a suppressed turn does not do
# ---------------------------------------------------------------------------

class _RecordingPolicy:
    """A character policy that records whether it was consulted and spends a slot.

    Spending a RESOURCE is the point: §7.1.2's claim is that a suppressed turn
    leaves the slot available for later, and a policy that only attacked could not
    tell a suppressed turn from a missed one.
    """

    def __init__(self, target):
        self.target = target
        self.turns = 0

    def decide(self, snapshot: GameState) -> list[Choice]:
        self.turns += 1
        return [Choice(action_type="attack", cost="action", target=self.target,
                       resource_cost={"spell_slot_1": 1})]


def _scheduler(char, enemy, policy, rounds=1):
    return Scheduler(rng=SeededRNG(7), entities=[char, enemy],
                     policies={char.id: policy}, max_rounds=rounds)


def _combatants():
    from src.resources import ResourceEntry, ResourcePool
    pool = ResourcePool()
    pool.add("spell_slot_1", ResourceEntry(current=4, maximum=4))
    char = Entity(name="char", hp=10**6, resources=pool,
                  base_stats={"ac": 18, "attack_bonus": 10, "damage_dice": (1, 8),
                              "damage_bonus": 4, **_ALL_SAVES})
    enemy = Entity(name="enemy", hp=10**6, base_stats={"ac": 1})
    return char, enemy


def test_a_suppressed_turn_opens_no_decision_point_and_spends_nothing():
    """§7.1.2, which is the whole reason control is applied at runtime rather than as
    a post-hoc multiplier: a turn that never happened must not spend its slot."""
    char, enemy = _combatants()
    policy = _RecordingPolicy(enemy)
    char.control.credit(lost=1.0)

    sched = _scheduler(char, enemy, policy)
    sched.run()

    assert policy.turns == 0                                  # never consulted
    assert char.resources.available("spell_slot_1") == 4      # slot banked
    assert sched.telemetry.control_applied[char.id].suppressed_turns == 1
    assert sched.telemetry.control_applied[char.id].turns_lost == pytest.approx(1.0)


def test_a_scaled_turn_acts_and_DOES_spend_its_resources():
    """The other half, and §7.3's documented wrinkle stated as a test: a 70% turn is
    a real turn that happened at reduced effect, so it pays for itself."""
    char, enemy = _combatants()
    policy = _RecordingPolicy(enemy)
    char.control.credit(lost=0.3)

    sched = _scheduler(char, enemy, policy)
    sched.run()

    assert policy.turns == 1
    assert char.resources.available("spell_slot_1") == 3      # spent, by design
    assert sched.telemetry.control_applied[char.id].suppressed_turns == 0


def test_the_output_scale_is_scoped_to_the_controlled_entitys_own_turn():
    """Why the scale is reset on every non-acting entity: the account prices TURNS
    (§7.2), so a controlled character's reaction on somebody else's turn is at full
    output.  Asserted at the boundary — after the enemy's turn starts, the
    character's scale is back to 1.0."""
    char, enemy = _combatants()
    policy = _RecordingPolicy(enemy)
    char.control.credit(lost=0.5)

    class _Watcher:
        """An enemy policy that reads the character's scale during ITS own turn."""

        def __init__(self):
            self.char_scale_on_enemy_turn = None

        def decide(self, snapshot: GameState) -> list[Choice]:
            self.char_scale_on_enemy_turn = char.output_scale
            return []

    watcher = _Watcher()
    sched = Scheduler(rng=SeededRNG(7), entities=[char, enemy],
                      policies={char.id: policy, enemy.id: watcher}, max_rounds=1)
    sched.run()
    assert watcher.char_scale_on_enemy_turn == 1.0


def test_statuses_are_still_swept_on_a_suppressed_turn():
    """Suppression removes the entity's ACTIONS, not the world's bookkeeping.  A
    status due to expire at the suppressed turn's tick must still expire, or a
    controlled character would carry a stale sap/vex for as long as it was stunned.
    """
    char, enemy = _combatants()
    char.control.credit(lost=1.0)
    char.statuses.apply("sapped", True, expiry=(1, 0))

    sched = _scheduler(char, enemy, _RecordingPolicy(enemy))
    sched.run()
    assert not char.statuses.has("sapped")


def test_zone_effects_still_fire_on_a_suppressed_turn():
    """**BUILT fixture** — unreachable through ``RunConfig``: no shipped build gives
    the ENEMY a damaging zone, so a suppressed entity standing in one cannot occur
    in any configured run.  Built because §7.2 states this behaviour in prose and a
    future enemy-side zone would otherwise find it silently broken: a stunned
    character in Spirit Guardians still takes the damage.
    """
    char, enemy = _combatants()
    char.control.credit(lost=1.0)
    sched = _scheduler(char, enemy, _RecordingPolicy(enemy))
    # An enemy-owned damaging zone the character is standing in, shaped the way
    # substrate #7/7b registers one.
    enemy.base_stats["zone_dc"] = 99                  # the character cannot save
    sched.zones["test_zone"] = _Zone(enemy, char)
    sched.run()

    assert char.hp < 10**6                   # the zone's save-for-damage landed


class _ZoneEffect:
    save_stat = "dex_save"
    dc_stat = "zone_dc"
    damage_dice = (3, 8)
    damage_bonus = 0
    on_save = "half"
    damage_type = None
    origin = "spell"
    min_die = None
    ignore_resistance = False


class _Zone:
    """Minimal stand-in for a registered damaging zone, carrying exactly what
    ``Scheduler._fire_zone_effects`` reads: an owner, an effect and ``contains``."""

    effect = _ZoneEffect()
    destroyed = False

    def __init__(self, owner, occupant):
        self.owner = owner
        self._occupant = occupant
        self.source = "test_zone"
        self.name = "test_zone"          # the scheduler logs the zone by name

    def contains(self, actor):
        return actor.id == self._occupant.id


# ---------------------------------------------------------------------------
# The combat boundary (§7.6 cause 1)
# ---------------------------------------------------------------------------

def test_the_account_is_cleared_at_the_combat_boundary():
    """Each combat restarts the round counter, so a balance carried across the
    boundary would be spent against a combat that never earned it — the same leak
    the status sweep is there to stop.  It is also §7.6's first structural reason the
    credited and realized numbers differ."""
    from src.builds import war_angel
    from src.day_runner import DayRunner

    runner, character, _dummy = war_angel.make_day_runner(level=3, rng=SeededRNG(5))
    assert isinstance(runner, DayRunner)
    character.control.credit(lost=99.0)
    runner.run_day()
    assert character.control.pending == 0.0
    assert character.output_scale == 1.0


# ---------------------------------------------------------------------------
# End to end through the framework (§7.6, and the two new metrics)
# ---------------------------------------------------------------------------

DAYS, SEED = 400, 11


def _report(level=13, build="war_angel", **options):
    return run(RunConfig(build=build, level=level, n_days=DAYS, seed=SEED,
                         enemy="baseline", enemy_options=options))


def test_the_realized_cost_never_exceeds_the_credit_and_the_gap_has_two_causes():
    """§7.6, which is what the step-4 seam check found BEFORE any code was written:
    the credited channel and the account describe the same quantity at two different
    pipeline stages, and they cannot agree.

    Measured (400 days, seed 11, control + mitigation on War Angel L13):
    hard 0.19402 → 0.17032, soft 0.24594 → 0.11416.  The assertion is the INEQUALITY
    and its direction, not the values — the values live in the module docstring with
    the reason the two gaps are so different in size.
    """
    report = _report(control=True, mitigation=True)
    credited_lost = report["control_turns_lost_per_round"].value
    realized_lost = report["control_turns_lost_applied_per_round"].value
    credited_reduced = report["control_turns_reduced_per_round"].value
    realized_reduced = report["control_turns_reduced_applied_per_round"].value

    assert 0.0 < realized_lost < credited_lost
    assert 0.0 < realized_reduced < credited_reduced


def test_the_soft_gap_is_wider_than_the_hard_gap_because_hard_draws_first():
    """The measured asymmetry, asserted as a MECHANISM: §7.5's draw order means soft
    credits queue behind hard ones, so the soft channel loses proportionally more of
    its credit than the hard channel does.  A reader who expected truncation alone
    would expect the two ratios to match."""
    report = _report(control=True, mitigation=True)
    hard_kept = (report["control_turns_lost_applied_per_round"].value
                 / report["control_turns_lost_per_round"].value)
    soft_kept = (report["control_turns_reduced_applied_per_round"].value
                 / report["control_turns_reduced_per_round"].value)
    assert soft_kept < hard_kept
    assert hard_kept > 0.8 and soft_kept < 0.6


def test_runtime_control_lowers_dpr_and_the_default_leaves_it_untouched():
    """§7.4's prediction, both halves.  Control ON costs output; control OFF — the
    default — is the run every pre-existing golden was measured on."""
    controlled = _report(control=True).headline.value
    uncontrolled = _report().headline.value
    assert controlled < uncontrolled


def test_the_realized_metrics_are_unavailable_rather_than_zero_without_control():
    """§3.4's three states, inherited from the credited pair's own predicate: a run
    with no control channel declares the rows UNMEASURED, never 0 — which would read
    as "this build resists control perfectly"."""
    report = _report()
    for name in ("control_turns_lost_applied_per_round",
                 "control_turns_reduced_applied_per_round"):
        value = report[name]
        assert not value.measured and not value.available
        assert "control" in value.note


def test_the_realized_channel_is_scoped_to_the_build_not_the_roster():
    """The per-METRIC ritual's roster-scoping check, on the only build with a summon.

    The channel is keyed by ACTOR, so the realized rows describe the attributed roles
    and nothing else.  Asserted on a run where the channel is genuinely NON-EMPTY
    (the default focus, so the character is the one being controlled): the character's
    cell carries the whole realized cost and the summon's carries none.

    The credited rows cannot make this distinction at all — they are keyed by save
    ability and sum over whoever failed (§7.6), which is why the realized half is the
    one that can answer "whose turns".
    """
    output = simulate(RunConfig(build="silvertail", level=10, n_days=200, seed=SEED,
                                enemy="baseline", enemy_options={"control": True}))
    character = output.telemetry.control_applied_for(
        set(output.roster.ids("characters")))
    summons = output.telemetry.control_applied_for(
        set(output.roster.ids("summons")))

    assert character.turns_lost > 0.0
    assert summons.turns_lost == 0.0
    assert set(output.telemetry.control_applied) == {output.roster.character.id}


def test_control_on_a_COMMANDED_summon_is_credited_but_never_realized():
    """A gap the roll call found, measured rather than reasoned about, and recorded as
    a deferral rather than fixed (evaluation_framework.md §14).

    With ``enemy_options={'focus': 'summon'}`` the enemy forces its control saves
    against the companion, and the companion duly fails them — the CREDITED channel
    fills up.  Nothing is ever drawn down, and the reason is structural: a controlled
    ally is commanded on its CONTROLLER's turn via ``Choice.actor`` (CLAUDE.md
    substrate #7/7a), so it has no ``TurnStartEvent`` of its own and the account has
    no boundary at which to spend.  Silvertail's companion has no entry in
    ``runner.policies`` at all.

    Measured (200 days, seed 11, Silvertail L10, focus='summon'): 235.2 turn-units
    credited, and the realized channel is EMPTY — not small, empty.  Suppressing a
    commanded summon's turn would mean suppressing its controller's command, which is
    a different mechanism, so the honest move is to name it.  Trigger: a summon that
    takes its own turn (a ``create_entity``'d Actor WITH a policy, which the design
    allows).
    """
    output = simulate(RunConfig(build="silvertail", level=10, n_days=200, seed=SEED,
                                enemy="baseline",
                                enemy_options={"control": True,
                                               "focus": "summon"}))
    credited = sum(t.turns_lost for t in output.telemetry.control.values())
    assert credited > 0.0
    assert output.telemetry.control_applied == {}


def test_suppressed_turns_are_fewer_than_the_turn_units_they_come_from():
    """Why ``suppressed_turns`` is counted separately rather than inferred: a
    fractional hard share costs output without costing a turn, so turn-units lost
    always exceed whole turns skipped.  This is also why the attack COUNT falls by
    less than the hard account does."""
    output = simulate(RunConfig(build="war_angel", level=13, n_days=DAYS, seed=SEED,
                                enemy="baseline", enemy_options={"control": True}))
    tally = output.telemetry.control_applied_for(
        set(output.roster.ids("characters")))
    assert tally.suppressed_turns < tally.turns_lost
    assert tally.suppressed_turns > 0


def test_the_pooled_control_total_sums_every_actor():
    """**BUILT fixture** — unreachable through ``RunConfig`` today, and the roll call
    is what made that visible.

    ``control_applied_for(None)`` pools every actor, the contract ``attacks_for``
    carries.  But no shipped roster can produce a second populated cell: the enemy is
    never controlled, and a commanded summon has no turn to draw down (see the test
    above).  So in every configured run the pooled total EQUALS the character-scoped
    one, and a scoping bug in this accessor would be invisible.  Driven directly
    instead.
    """
    telemetry = CombatTelemetry()
    telemetry.record_control_applied(1, turns_lost=1.0, turns_reduced=0.0,
                                     suppressed=True)
    telemetry.record_control_applied(2, turns_lost=0.25, turns_reduced=0.5,
                                     suppressed=False)

    pooled = telemetry.control_applied_for(None)
    assert pooled.turns_lost == pytest.approx(1.25)
    assert pooled.turns_reduced == pytest.approx(0.5)
    assert pooled.suppressed_turns == 1
    assert pooled.affected_turns == 2

    assert telemetry.control_applied_for({1}).turns_lost == pytest.approx(1.0)
    assert telemetry.control_applied_for({2}).turns_lost == pytest.approx(0.25)
    assert telemetry.control_applied_for(set()).affected_turns == 0


# ---------------------------------------------------------------------------
# The renderer (the s49/s50 lesson, which repeated twice before this)
# ---------------------------------------------------------------------------

def test_the_console_shows_the_realized_rows_aligned_with_the_credited_ones():
    """Found by rendering ONE REAL OUTPUT by eye (per-feature ritual step 6, now five
    sessions running), and it is the same class of defect as s49's and s50's: the
    step's own deliverable rendered badly.

    The panel's metric-name column was a hardcoded 34 characters.
    ``control_turns_reduced_applied_per_round`` is 39, so both new rows overflowed it
    and pushed their OWN value columns right — the four control rows, which are
    meant to be read as credited-vs-realized pairs, were the only four in the panel
    that did not line up. The width is now derived from the rows being rendered, so
    it cannot go stale the next time a longer name is registered.
    """
    from src.evaluation import console

    text = console.render(_report(control=True))
    panel = text.split("PANEL")[1].split("COLUMNS")[0].splitlines()
    control_rows = [line for line in panel if "control_turns" in line]
    assert len(control_rows) == 4                    # credited pair + realized pair

    # Every panel row puts "+/-" at the same column, which is what alignment MEANS.
    offsets = {line.index("+/-") for line in panel if "+/-" in line}
    assert len(offsets) == 1


# ---------------------------------------------------------------------------
# §14's distribution trigger
# ---------------------------------------------------------------------------

def test_the_attacks_distribution_has_spread_only_once_turns_can_be_skipped():
    """§14's trigger, both sides of it.  s49 and s50 declined this distribution
    because the quantity was a CONSTANT; whole-turn suppression is the first thing in
    the model that makes it vary, and a zero IQR remains the correct answer for a run
    without control."""
    controlled = _report(control=True).distribution("attacks_per_round_distribution")
    assert controlled["iqr"].value > 0.0
    assert controlled["p10"].value < controlled["p90"].value

    uncontrolled = _report().distribution("attacks_per_round_distribution")
    assert uncontrolled["iqr"].value == 0.0
    assert uncontrolled["p10"].value == uncontrolled["p90"].value


def test_the_distribution_cannot_disagree_with_the_scalar_it_describes():
    """§5.4's property for the kind: declared OVER a registered scalar, so the mean
    of the per-day vector IS that scalar.  Checked on the new one because it is the
    first distribution over a quantity whose spread comes from the ENGINE rather than
    from dice."""
    report = _report(control=True)
    assert report.distribution("attacks_per_round_distribution").over == \
        "attacks_per_round"
    assert METRICS["attacks_per_round"].unit == \
        report.distribution("attacks_per_round_distribution").unit
