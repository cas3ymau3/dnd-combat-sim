"""
test_baseline_enemy_roster.py — ``BaselineEnemyPolicy``'s weighted friendly roster
(evaluation_framework.md §3.5.3).

**A PREREQUISITE, NOT POLISH, and the seam check is what established that** (s53,
before any code existed).  The two enemy policies answered "which friendly does it
attack" in two different ways: ``ScriptedEnemyPolicy`` takes a weighted roster,
``BaselineEnemyPolicy`` took ``primary``/``fallback`` and focus-fired.  They AGREED
only because the standardized default was focus-fire onto an empty ally roster —
measured on Starfire L15 over 120 days, ``scripted`` put 126,661 on the character and
**0** on the party, ``baseline`` 105,484 and **0**.

§3.4 claims ``baseline`` vs ``scripted`` at the same level "isolates the enemy forces
saves from the enemy swings".  **The moment a party exists that claim becomes false**
unless both policies split the same way — the two arms would differ in targeting MODEL
as well as in save-forcing, so the one comparison the baked-in paths could never
express would stop being a comparison of one thing.

THE ROLL CALL (per-feature ritual step 5):

| declaration | values | fixture covering each |
|---|---|---|
| ``BaselineEnemyPolicy.roster`` | ``None`` (focus-fire) | ``test_without_a_roster_the_policy_draws_no_targeting_dice`` + ``test_without_a_roster_every_swing_lands_on_the_primary`` |
| | a weighted roster | ``test_with_a_roster_the_swings_split_across_the_friendlies`` |
| | a roster whose other weights are ZERO | ``test_a_zero_weighted_roster_is_focus_fire_by_another_name`` |
| ``_slot_targets`` fallback | the pick is available | ``test_with_a_roster_the_swings_split_across_the_friendlies`` |
| | the pick has winked out | ``test_a_winked_out_pick_hands_its_slot_to_the_focus_target`` |
| | nothing is left to hit | ``test_with_everything_out_of_action_the_policy_declines`` |
| round type under a roster | attack round | ``test_with_a_roster_the_swings_split_across_the_friendlies`` |
| | save-for-damage round | ``test_a_save_round_aims_its_aoe_at_the_first_slots_target`` |
| | control round | ``test_a_control_round_aims_at_the_first_slots_target`` |
| ``describe_parameters`` targeting | ``single_target`` / ``weighted_roster`` | ``test_provenance_names_the_targeting_mode`` |

**WHY THE DRAW COUNT IS UNCONDITIONAL**, which is the one design choice here worth
pinning: ``n_attacks`` target picks are drawn every round whatever the round type turns
out to be, even on a save or control round that uses only the first.  Conditioning them
on the round type would COUPLE the targeting draws to the round-type draws, so a change
to either would move the other's stream — and the round type is itself pre-rolled in the
same loop.  ``test_the_draw_count_does_not_depend_on_the_round_type`` is that property.
"""

from __future__ import annotations

import pytest

from src.builds import enemy_stats
from src.builds.enemy import BaselineEnemyPolicy, ScriptedEnemyPolicy
from src.entity import Entity
from src.policy import GameState
from src.rng import SeededRNG

LEVEL = 10


class CountingRNG(SeededRNG):
    """A real seeded generator that also counts draws — so "no new dice" is a
    measurement rather than a reading of the code."""

    def __init__(self, seed):
        super().__init__(seed)
        self.draws = []

    def roll(self, n, sides):
        self.draws.append((n, sides))
        return super().roll(n, sides)


def _friendly(name, ac=18):
    return Entity(name=name, hp=10 ** 9, base_stats={"ac": ac, "con_save": 5})


def _snapshot(round_number, actor):
    return GameState(
        actor=actor, enemies=(), allies=(), round_number=round_number,
        turn_index=1, tick=(round_number, 1, 0), resources={"action": 1},
    )


def _policy(primary, *, roster=None, fallback=None, **kw):
    return BaselineEnemyPolicy(
        level=LEVEL, primary=primary, fallback=fallback, roster=roster,
        rounds_per_combat=4, **kw,
    )


# ---------------------------------------------------------------------------
# roster=None — the pre-party behaviour, which must not move at all
# ---------------------------------------------------------------------------

def test_without_a_roster_the_policy_draws_no_targeting_dice():
    """The bit-identity guarantee, as a draw-by-draw comparison.

    §3.5.3 requires ``primary``/``fallback`` to keep working as "weight everything
    else zero" so Silvertail stays bit-identical. The strongest available form of that
    is not "the DPR matches" but "the dice stream is the same sequence of draws", which
    is what this asserts: adding the capability must cost nothing when it is unused.
    """
    char = _friendly("Char")
    before = CountingRNG(11)
    _policy(char).on_combat_start(0, before)
    after = CountingRNG(11)
    _policy(char, roster=None).on_combat_start(0, after)
    assert before.draws == after.draws


def test_without_a_roster_every_swing_lands_on_the_primary():
    char = _friendly("Char")
    policy = _policy(char)
    policy.on_combat_start(0, SeededRNG(3))
    n = enemy_stats.baseline_n_attacks(LEVEL)
    for round_number in range(1, 5):
        choices = policy.decide(_snapshot(round_number, _friendly("Enemy")))
        assert choices, "the policy should always do something"
        assert {c.target for c in choices} == {char}
        if all(c.action_type == "attack" for c in choices):
            assert len(choices) == n


# ---------------------------------------------------------------------------
# A weighted roster
# ---------------------------------------------------------------------------

def test_with_a_roster_the_swings_split_across_the_friendlies():
    """The capability itself: over many combats, every roster entity is hit, in
    proportion to its weight.

    Asserted as "all four appear and the character's share is near its weight" rather
    than as exact counts, which would be a seed fixture dressed up as a property.
    """
    friendlies = [_friendly(f"F{i}") for i in range(4)]
    roster = [(f, 25) for f in friendlies]
    policy = _policy(friendlies[0], roster=roster)
    rng = SeededRNG(11)
    hits = {f.id: 0 for f in friendlies}
    for combat in range(400):
        policy.on_combat_start(combat, rng)
        for round_number in range(1, 5):
            for choice in policy.decide(_snapshot(round_number, _friendly("Enemy"))):
                hits[choice.target.id] += 1
    assert all(count > 0 for count in hits.values()), hits
    total = sum(hits.values())
    for f in friendlies:
        share = hits[f.id] / total
        assert 0.2 < share < 0.3, f"{f.name} took {share:.3f} of the swings"


def test_a_zero_weighted_roster_is_focus_fire_by_another_name():
    """§3.5.4's "uniform is the special case where every class is equal" has a twin:
    focus-fire is the special case where every OTHER weight is zero.

    This is the property that lets threat class land later without a structural
    change — the mechanism already spans both ends of its range.
    """
    char = _friendly("Char")
    party = [_friendly("P1"), _friendly("P2")]
    roster = [(char, 100), (party[0], 0), (party[1], 0)]
    policy = _policy(char, roster=roster)
    rng = SeededRNG(5)
    for combat in range(50):
        policy.on_combat_start(combat, rng)
        for round_number in range(1, 5):
            for choice in policy.decide(_snapshot(round_number, _friendly("Enemy"))):
                assert choice.target is char


def test_the_draw_count_does_not_depend_on_the_round_type():
    """The design choice pinned: ``n_attacks`` picks every round, whatever the round
    turns out to be.

    Conditioning the targeting draws on the round type would couple two streams that
    are pre-rolled in the same loop, so a change to either would silently move the
    other. Compared across TWO save-round probabilities, which is the knob that
    changes the round-type mix — so if the draws were conditional the two totals would
    differ.
    """
    char = _friendly("Char")
    roster = [(char, 50), (_friendly("P1"), 50)]
    counts = []
    for save_prob in (0.0, 1.0):
        rng = CountingRNG(11)
        _policy(char, roster=roster, save_round_prob=save_prob).on_combat_start(0, rng)
        picks = [d for d in rng.draws if d == (1, 100)]
        counts.append(len(rng.draws) - len(picks))
    # The TOTAL draws differ (a save round also draws a save type), but the number of
    # targeting picks is 4 rounds x n_attacks either way.
    n = enemy_stats.baseline_n_attacks(LEVEL)
    for save_prob in (0.0, 1.0):
        rng = CountingRNG(11)
        policy = _policy(char, roster=roster, save_round_prob=save_prob)
        policy.on_combat_start(0, rng)
        assert sum(len(v) for v in policy._picks.values()) == 4 * n


# ---------------------------------------------------------------------------
# The summon-survival fallback, under a roster
# ---------------------------------------------------------------------------

def test_a_winked_out_pick_hands_its_slot_to_the_focus_target():
    """Substrate #7 / 7a survives the roster path: a slain beast's share of the
    incoming damage is not wasted on a corpse.

    This is the behaviour the pre-roll could easily have destroyed — the pick is made
    at ``on_combat_start`` and the death happens later, so a naive implementation
    keeps swinging at the dead entity.
    """
    master = _friendly("Master")
    beast = _friendly("Beast")
    policy = _policy(master, fallback=None,
                     roster=[(master, 0), (beast, 100)])
    policy.on_combat_start(0, SeededRNG(5))
    # Every pick is the beast (weight 100 vs 0).
    assert all(e is beast for picks in policy._picks.values() for e in picks)
    beast.destroyed = True
    assert beast.is_out_of_action
    choices = policy.decide(_snapshot(1, _friendly("Enemy")))
    assert choices and all(c.target is master for c in choices)


def test_with_everything_out_of_action_the_policy_declines():
    master = _friendly("Master")
    beast = _friendly("Beast")
    policy = _policy(master, roster=[(master, 50), (beast, 50)])
    policy.on_combat_start(0, SeededRNG(5))
    master.destroyed = True
    beast.destroyed = True
    assert policy.decide(_snapshot(1, _friendly("Enemy"))) == []


# ---------------------------------------------------------------------------
# The single-target round types under a roster
# ---------------------------------------------------------------------------

def test_a_save_round_aims_its_aoe_at_the_first_slots_target():
    """A save-for-damage round has ONE target, and it is the first slot's pick — so a
    round aimed at a party member is aimed at it consistently.

    (§7's AoE-share stays deferred: an AoE still resolves against one target, which
    this change does not quietly settle.)
    """
    char = _friendly("Char")
    party = _friendly("Party")
    policy = _policy(char, roster=[(char, 0), (party, 100)], save_round_prob=1.0)
    policy.on_combat_start(0, SeededRNG(5))
    choices = policy.decide(_snapshot(1, _friendly("Enemy")))
    assert [c.action_type for c in choices] == ["save_spell"]
    assert choices[0].target is party


def test_a_control_round_aims_at_the_first_slots_target():
    char = _friendly("Char")
    party = _friendly("Party")
    policy = _policy(char, roster=[(char, 0), (party, 100)],
                     control=True, save_round_prob=0.0, control_save_prob=1.0)
    policy.on_combat_start(0, SeededRNG(5))
    choices = policy.decide(_snapshot(1, _friendly("Enemy")))
    assert [c.action_type for c in choices] == ["control_save"]
    assert choices[0].target is party


# ---------------------------------------------------------------------------
# The two policies now answer the question the same way
# ---------------------------------------------------------------------------

def test_both_policies_draw_the_same_targeting_pick_for_the_same_roster():
    """§3.5.3's actual requirement: the two policies must split by the same RULE, or
    §3.4's comparison arm differs in targeting MODEL as well as in save-forcing.

    Asserted as an equality of the DRAWN SEQUENCE rather than of the code, because
    the implementations are deliberately duplicated (see ``describe_parameters``) and
    what has to match is the contract, not the source.
    """
    friendlies = [_friendly(f"F{i}") for i in range(3)]
    roster = [(f, w) for f, w in zip(friendlies, (50, 30, 20))]
    n = enemy_stats.baseline_n_attacks(LEVEL)

    scripted = ScriptedEnemyPolicy(target=friendlies[0], n_attacks=n,
                                   rounds_per_combat=4, roster=roster)
    scripted.on_combat_start(0, SeededRNG(11))

    baseline = _policy(friendlies[0], roster=roster, n_attacks=n)
    # The baseline draws its picks FIRST in each round's body, then the round-type
    # draws, so a shared seed gives the same picks only if the pick procedure matches.
    baseline_rng = SeededRNG(11)
    picks = {r: [baseline._weighted_pick(baseline_rng) for _ in range(n)]
             for r in range(1, 5)}
    assert picks == scripted._picks


def test_provenance_names_the_targeting_mode():
    """§4: a provenance block that makes the reader deduce which of two measurements
    ran is not documenting the assumption.

    Both policies now use the SAME vocabulary for it, which is what makes their blocks
    comparable at all — before this they could not even be lined up.
    """
    char = _friendly("Char")
    party = _friendly("Party")
    plain = _policy(char).describe_parameters()
    assert plain["targeting"] == "single_target"
    assert plain["roster_weights"] is None

    weighted = _policy(char, roster=[(char, 60), (party, 40)]).describe_parameters()
    assert weighted["targeting"] == "weighted_roster"
    assert weighted["roster_weights"] == {"Char": 60, "Party": 40}

    scripted = ScriptedEnemyPolicy(
        target=char, roster=[(char, 60), (party, 40)]).describe_parameters()
    assert scripted["targeting"] == weighted["targeting"]
    assert set(scripted) >= {"targeting", "roster_weights"}
