"""The action-economy cost PARTITION, and the War Angel §4 AoO provenance.

Both guards added session 63 with `design/positioning.md` (roadmap item 5d, the
design pass).  Neither moves a number; both close a gap the positioning arc
would otherwise fall into.

WHAT THIS GUARDS
----------------
`src/taxonomy.py` declares a closed `Cost` vocabulary of six.  The scheduler
grants three of them (`DEFAULT_RESOURCES`) and drains with `if cost in econ`, so
a declared-but-ungranted cost FELL THROUGH UNMETERED.  `"movement"` is exactly
that case, and it is the character-side injection point the positioning arc
needs: a policy emitting `Choice(cost="movement")` got free, unlimited movement
and no error, so the attack-SUBTRACTION the arc exists to model would never have
happened while looking like it had.

MEASURED before the fix (five choices emitted in one turn, not asserted here
because the fix removes the behaviour -- recorded so the claim is a measurement
and not an argument):

    cost=action        5 emitted -> 1 resolved
    cost=bonus_action  5 emitted -> 1 resolved
    cost=movement      5 emitted -> 5 resolved   <-- the defect
    cost=free          5 emitted -> 5 resolved

The guard is stated as a PARTITION over the closed vocabulary rather than as a
blocklist on `"movement"`, so it cannot go stale: a seventh cost added to
`taxonomy.COSTS` is either classified or raises on first use.

ROLL CALL -- one row per declaration VALUE this change touches, one column for
the fixture covering it.  Written before the tests, per the promoted ritual.

    declaration / value          | fixture
    -----------------------------+------------------------------------------
    Cost: "action"               | test_a_metered_cost_is_still_metered
    Cost: "bonus_action"         | test_a_metered_cost_is_still_metered
    Cost: "reaction"             | pre-existing economy tests (AoO path);
                                 |   partition membership here
    Cost: "movement"             | test_an_unmodelled_cost_refuses
    Cost: "free"                 | test_an_unmetered_cost_is_still_free
    Cost: "none"                 | partition membership (UNMETERED_COSTS);
                                 |   Extra Attack follow-ups in build tests
    the partition is TOTAL       | test_every_declared_cost_is_classified
    UNMODELLED_COSTS content     | test_movement_is_the_only_unmodelled_cost
    WarAngel AoO provenance      | test_war_angel_describe_records_the_aoo_assumption
      level < 14 (no parry)      | test_the_reaction_double_book_flag_tracks_level
      level >= 14 (parry live)   | test_the_reaction_double_book_flag_tracks_level

Note the one row whose fixture is inherited rather than new: `"reaction"` is
exercised as a METERED cost by the existing opportunity-attack path, so this
module asserts only its partition membership.
"""

import logging

import pytest

from src.entity import Entity
from src.evaluation.build_adapters import WarAngelAdapter
from src.evaluation.config import RunConfig
from src.policy import Choice
from src.scheduler import (
    DEFAULT_RESOURCES,
    UNMETERED_COSTS,
    UNMODELLED_COSTS,
    Scheduler,
)
from src.taxonomy import COSTS

logging.disable(logging.CRITICAL)


class _NoOp:
    def decide(self, snapshot):
        return []


class _Spam:
    """Emits five attacks at one cost, so a metered cost resolves 1 and an
    unmetered one resolves 5.  Five rather than two so the two outcomes cannot
    be confused with an off-by-one."""

    def __init__(self, target, cost, n=5):
        self.target, self.cost, self.n = target, cost, n

    def decide(self, snapshot):
        return [Choice(action_type="attack", cost=self.cost,
                       target=self.target, weapon_stat="attack_bonus")
                for _ in range(self.n)]


class _FixedRNG:
    """d20 -> 20 (auto-hit, and a crit so dice double), every other die -> 1.
    Damage is therefore 2 per landed attack: a pure COUNT of what resolved."""

    def roll(self, n, sides, *, stream=None):
        return [20 if sides == 20 else 1 for _ in range(n)]

    def roll_one(self, sides, *, stream=None):
        return self.roll(1, sides, stream=stream)[0]


def _run(cost):
    char = Entity(name="Probe", hp=100,
                  base_stats={"attack_bonus": 50, "damage_dice": (1, 4)})
    foe = Entity(name="Target", hp=10 ** 6, base_stats={"ac": 1})
    sch = Scheduler(rng=_FixedRNG(), entities=[char, foe],
                    policies={char.id: _Spam(foe, cost), foe.id: _NoOp()},
                    max_rounds=1)
    sch.run()
    return sch.damage_by_source_target.get((char.id, foe.id), 0)


# ---------------------------------------------------------------------------
# The partition itself
# ---------------------------------------------------------------------------

def test_every_declared_cost_is_classified():
    """The partition is TOTAL over the closed vocabulary.

    This is the assertion that cannot go stale: a cost added to taxonomy.COSTS
    lands in exactly one of the three sets, and if its author classifies it
    nowhere it surfaces here rather than at a silent unmetered resolve.
    """
    metered = frozenset(DEFAULT_RESOURCES)
    classified = metered | UNMETERED_COSTS | UNMODELLED_COSTS
    assert classified == frozenset(COSTS)
    # And the three sets are disjoint -- a cost cannot be metered AND free.
    assert not (metered & UNMETERED_COSTS)
    assert not (metered & UNMODELLED_COSTS)
    assert not (UNMETERED_COSTS & UNMODELLED_COSTS)


def test_movement_is_the_only_unmodelled_cost():
    """Recorded as an equality, not a membership, so that modelling movement
    (the positioning arc's §7.4 prerequisite) MUST come back and empty this set
    rather than quietly adding a second unmodelled cost beside it."""
    assert UNMODELLED_COSTS == frozenset({"movement"})


# ---------------------------------------------------------------------------
# Behaviour at each cost value
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cost", ["action", "bonus_action"])
def test_a_metered_cost_is_still_metered(cost):
    """Unchanged by the guard: 5 emitted, 1 resolved (2 damage at 2/hit)."""
    assert _run(cost) == 2


def test_an_unmetered_cost_is_still_free():
    """Also unchanged: "free" really is free, 5 emitted and 5 resolved.

    This is the control arm that makes the movement test meaningful -- without
    it, a refusal could be mistaken for the scheduler having become strict
    about repeated choices in general.
    """
    assert _run("free") == 10


def test_an_unmodelled_cost_refuses():
    """"movement" is declared in taxonomy.COSTS, metered nowhere, and now
    REFUSES rather than resolving for free.

    NotImplementedError and not a skip-with-warning: skipping would read as
    "the character could not afford it", which is a different and
    plausible-looking answer, and the plausible-looking wrong answer is the
    whole failure mode here.
    """
    with pytest.raises(NotImplementedError, match="movement"):
        _run("movement")


# ---------------------------------------------------------------------------
# The §4 AoO provenance (design/positioning.md §9.2)
# ---------------------------------------------------------------------------

def test_war_angel_describe_records_the_aoo_assumption():
    """The build that ORIGINATED the no-spatial-model convention now records it.

    It did not until s63, while the baseline subject that BORROWED the
    convention documented it in full and credited War Angel -- so an
    authoritative War Angel artifact buried the assumption that prompted the
    positioning arc.
    """
    described = WarAngelAdapter().describe(
        RunConfig(build="war_angel", level=5, enemy="baseline"))
    aoo = described["opportunity_attacks"]
    assert aoo["per_combat"] == 1
    # NOT a declared option, unlike the baseline subject's aoo_per_combat --
    # which is exactly why it needed stating outright rather than resolving.
    assert aoo["declared"] is False
    assert described["options"] == {}
    assert "NO SPATIAL MODEL" in aoo["assumption"]


@pytest.mark.parametrize("level,expected", [(5, False), (13, False),
                                            (14, True), (16, True)])
def test_the_reaction_double_book_flag_tracks_level(level, expected):
    """The double-book is confined to L14-16, where Flourish Parry goes live.

    Measured at 4,000 days: reactions_per_round reads 0.2500 +/- 0.0000 at L13
    (exact because the AoO is a declared constant -- one per combat, pre-rolled
    onto one of four rounds, so the variance is structurally zero) against
    0.3288 / 0.3325 / 0.3309 at L14 / L15 / L16.  So the overage is ~0.081
    reactions/round and EXACTLY ZERO below L14.

    Asserted against the level rather than against the measured rate because
    this is provenance: the flag's job is to say which rows the scope bound
    reaches, and #6b's bound as written reads as though it reached all sixteen.
    """
    described = WarAngelAdapter().describe(
        RunConfig(build="war_angel", level=level, enemy="baseline"))
    assert described["opportunity_attacks"][
        "reaction_double_books_from_level_14"] is expected
