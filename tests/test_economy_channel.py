"""
test_economy_channel.py — the §13 ECONOMY CHANNEL's writer invariant (s62).

Validation framing (§12, memory ``validate-mechanism-not-build-value``): every test
here asserts a MECHANISM — that each resource a run spends REACHES the channel that
reports it.  No test asserts that any build's resource count is "correct"; the
assertion is only that the measured total equals the spend that actually happened.

Why this file exists
--------------------
Spending a resource is a TWO-CALL SEQUENCE: ``pool.consume(name, amount)`` then
``telemetry.record_resource(name, amount)``.  The scheduler performed both at its six
call sites; every out-of-combat caller performed only the first.  So the channel had
TWO WRITERS and reported ONE, and both metrics that read it were wrong without being
flagged — measured at War Angel L13, ``spell_slots_per_day`` reported **1.022**
against **9.908** actually spent (a 9.7x undercount), and
``limited_resources_per_day`` missed all 13 Hit Dice and 3.7 of 4.8 daily-plan
Channel Divinity charges.  Neither metric's declared definition is qualified with
"in combat", so both were false as implemented rather than merely narrow.

The fix is ``resources.spend_recorded``, which performs the pair.  A helper alone is
still a convention, though — the same convention the 11 out-of-combat sites had
already failed to follow — so the ENFORCEMENT is the invariant below, asserted end to
end against an instrumented ``ResourcePool.consume``.  That is the s54 seam lesson
applied to a sequence: when an ordering must always hold, make the guard a test that
cannot go stale rather than a docstring explaining why the duplication is safe.
"""

from __future__ import annotations

import logging
from collections import Counter

import pytest

import src.evaluation.build_adapters        # noqa: F401  (registers the adapters)
from src import resources as res_mod
from src.evaluation import runner
from src.evaluation.config import RunConfig

DAYS = 60          # enough for every daily-plan path to fire; cheap enough for CI


def _spend_vs_recorded(build: str, level: int, *, days: int = DAYS):
    """Run one config and return (actually_consumed, recorded_in_channel) Counters."""
    actual: Counter = Counter()
    original = res_mod.ResourcePool.consume

    def spy(self, name, amount=1, _o=original):
        ok = _o(self, name, amount)
        if ok:                      # a REFUSED spend must not be counted either side
            actual[name] += amount
        return ok

    res_mod.ResourcePool.consume = spy
    try:
        out = runner.simulate(RunConfig(build=build, level=level, enemy="baseline",
                                        n_days=days, seed=11))
    finally:
        res_mod.ResourcePool.consume = original
    return actual, Counter(out.telemetry.resources_spent)


@pytest.mark.parametrize("level", [5, 6, 12, 13, 16])
def test_every_resource_spend_reaches_the_economy_channel(level, caplog):
    """Every resource War Angel spends is reported by the channel, exactly.

    L5 is the level where the whole defect was invisible: the only slots spent there
    are Magic Weapon's and Prayer of Healing's, both out of combat, so the metric
    read a confident, converged, available **0.000** while two slots a day went out
    the door.  L13 is where it was worst (Bless + Shield of Faith + Magic Weapon +2
    are all daily-plan casts).  L16 adds the reaction-economy resources on top.
    """
    caplog.set_level(logging.ERROR)
    actual, recorded = _spend_vs_recorded("war_angel", level)
    assert actual, "the instrumentation caught nothing — the probe itself is broken"
    missing = {name: (count, recorded[name])
               for name, count in actual.items() if recorded[name] != count}
    assert not missing, (
        f"War Angel L{level}: resources spent but not reported by the §13 economy "
        f"channel {{name: (spent, recorded)}} = {missing}"
    )


def test_the_channel_reports_nothing_the_run_did_not_spend(caplog):
    """The invariant runs both ways: no phantom credits.

    ``spend_recorded`` records only when ``consume`` SUCCEEDS, so a refused spend
    cannot inflate the channel.  Asserted because the natural implementation —
    record first, consume second — passes the test above and fails this one.
    """
    caplog.set_level(logging.ERROR)
    actual, recorded = _spend_vs_recorded("war_angel", 13)
    phantom = {name: (actual[name], count)
               for name, count in recorded.items() if count > actual[name]}
    assert not phantom, (
        f"the channel reported more than was spent {{name: (spent, recorded)}} = {phantom}"
    )


# ---------------------------------------------------------------------------
# The ONE path still unrecorded, pinned by CONTAINMENT rather than left as prose
# ---------------------------------------------------------------------------

#: Resources spent inside ``Policy.on_combat_start``, which ``DayRunner._run_combat``
#: calls BEFORE constructing the ``Scheduler`` — so no ``CombatTelemetry`` exists yet
#: and there is no handle to record against.  Closing it means changing
#: ``on_combat_start``'s signature on every policy, which is a wider change than the
#: s62 fix was scoped to, and it is deliberately NOT done here: the residual is two
#: resources at 1/day on the one build that spends them.
KNOWN_UNRECORDED = frozenset({"slot_4th", "wild_shape"})


def test_the_on_combat_start_spend_path_is_STILL_unrecorded_and_no_wider(caplog):
    """A CONTAINMENT assertion, not an approval of the gap.

    This fails in BOTH directions, which is the point.  If someone wires
    ``on_combat_start`` to the channel, the gap closes and this test fails — forcing
    the decision record to be updated rather than letting a fixed defect sit
    described as open.  If a NEW unrecorded spend path appears anywhere, the gap
    widens and this also fails.  A comment saying "two resources are missing" does
    neither; this is step 5's "prefer an assertion, prose cannot fail".
    """
    caplog.set_level(logging.ERROR)
    actual, recorded = _spend_vs_recorded("starfire_scion", 15)
    gap = {name for name, count in actual.items() if recorded[name] != count}
    assert gap == set(KNOWN_UNRECORDED), (
        f"the unrecorded-spend set MOVED: expected {set(KNOWN_UNRECORDED)}, got {gap}. "
        "If you wired on_combat_start to the telemetry, delete this test and update "
        "KNOWN_UNRECORDED's rationale in PROGRESS.md; if a new path appeared, it is a "
        "regression of the s62 fix."
    )
