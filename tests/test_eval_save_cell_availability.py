"""Framework step 8b — per-cell availability reads the ENEMY's resolved parameters.

`evaluation_framework.md` §14's "per-cell availability does not read the ENEMY's
resolved parameters" (added s55 from the #6a preliminary run — the exercise put it on
the list; it had not been on it).  §3.4's three states, and the promise one of them
makes: UNAVAILABLE is *not* a measured zero.

THE DEFECT, measured.  `cha_save` has no weight in `enemy_stats.band_save_weights`
below band 11-16, so the standardized enemy CANNOT force a CHA save below L11, and
War Angel's plan forces no saves of any ability at any level.  The cell therefore had
no producer at all — and at ten of War Angel's sixteen levels
`saves_forced_per_round[cha_save|*]` rendered `0.0 +/- 0.0`, `converged=True`,
`available=True`, **unflagged, and the only unflagged cell in its breakdown**, so the
cell carrying no information read as the most trustworthy one.  Its sibling
`save_fail_rate[cha_save|*]` reported UNMEASURED correctly, because its denominator is
the forced count.  One report, one structural fact, two incompatible renderings.

AND IT REACHES FURTHER THAN WAR ANGEL COULD SHOW (measured s56).  At band 17+ the
DAMAGE weights carry only `{str, dex, con, cha}` and the CONTROL weights only
`{str, dex, con, wis, cha}`, so `int_save` is impossible in BOTH channels at L17-20
under every option setting, and `wis_save` is impossible in the damage channel there.
On the BASELINE SUBJECT — §3.5's complete-at-every-level fixture, the one whose whole
job is to make a framework defect distinguishable from a content gap — that is four
more unflagged exact zeros.  War Angel stops at 16, so #6a could not see them.

WHY THE BUILD SIDE HAD TO BE DECLARED.  `telemetry.record_save` has two call sites and
neither is actor-keyed, so a cell pools saves the enemy forced ON the character with
saves the build forced ON the enemy — `saves_forced_per_round`'s own definition says
so.  The enemy half is readable before day 1; the build half is a Python policy and is
not.  They also vary independently (band vs level-and-options), which is the s49 rule's
independence test, so `BuildAdapter.forced_save_abilities` is a DECLARATION.

THE ROLL CALL (per-feature ritual step 5, written before the tests).

| declaration                            | value                       | fixture |
|----------------------------------------|-----------------------------|---------|
| `forced_save_abilities`                | EMPTY (war_angel)           | `test_war_angel_declares_no_save_forcing_at_any_level` |
|                                        | non-empty, level-free       | `test_the_two_save_spell_builds_declare_dex_at_every_level` |
|                                        | OPTION-dependent            | `test_silvertails_declaration_follows_the_zone_option` |
|                                        | adapter does not implement  | `test_an_adapter_that_does_not_declare_FAILS_LOUDLY` |
| `enemy.resolve()['save_weights']`      | kind baseline               | `test_the_resolved_block_publishes_the_bands_actual_weights` |
|                                        | kind scripted / none        | `test_a_non_forcing_enemy_publishes_two_empty_channels` |
|                                        | control off / on            | `test_the_control_channel_is_empty_until_the_option_is_on` |
| band                                   | 0-4 (no cha in damage)      | `test_a_structurally_impossible_cell_is_UNAVAILABLE_not_zero` |
|                                        | 11-16 (cha present)         | `test_the_same_cell_is_MEASURED_once_the_band_carries_it` |
|                                        | 17+ (no int, no wis)        | `test_the_defect_reaches_the_baseline_subject_at_L17_20` |
| ability key                            | specific                    | most rows above |
|                                        | ALL (a margin)              | `test_a_margin_is_unavailable_only_when_NOTHING_can_be_forced` |
| channel key                            | `damage`                    | `test_the_damage_channel_is_judged_on_the_damage_weights` |
|                                        | `control`                   | `test_the_control_channels_own_reason_still_comes_first` |
|                                        | ALL                         | `test_a_cell_is_available_if_EITHER_channel_can_produce_it` |
| producer that opens a cell             | the ENEMY                   | `test_the_same_cell_is_MEASURED_once_the_band_carries_it` |
|                                        | the BUILD                   | `test_the_build_side_alone_keeps_a_cell_available` |

**What the table exposed before any test existed:** the "the BUILD alone opens the
cell" row had no fixture anywhere in the suite, and it is the row that decides whether
this change discards real data.  Silvertail at L10 with the zone on, against
`enemy="none"`, is the only configuration in the project where the build is the sole
producer — `test_the_build_side_alone_keeps_a_cell_available` is that row, and without
it a predicate that ignored the declaration entirely would have passed every other
test in this module.
"""

from __future__ import annotations

import pytest

from src.builds import baseline_character, silvertail
from src.builds.enemy_stats import band_control_weights, band_save_weights
from src.entity import Entity
from src.evaluation.adapters import available_builds, get_adapter
from src.evaluation.config import RunConfig
from src.evaluation.enemy import resolve
from src.evaluation.metrics import ALL, METRICS, RunContext
from src.evaluation.report import build_report
from src.evaluation.roster import Roster
from src.evaluation.runner import simulate

SAVE_BREAKDOWNS = ("saves_forced_per_round", "save_fail_rate")


def _breakdown(name: str):
    return {b.name: b for b in METRICS.breakdowns}[name]


def _context(build: str, level: int, **kw) -> RunContext:
    """A `RunContext` with a minimal roster.

    The roster is irrelevant to this predicate and deliberately minimal, so a test
    that fails says something about the saves question rather than about roster
    construction.  `RunContext.enemy` derives the resolved block from the config
    alone, which is what makes this cheap (and is the s48 derive case, argued in
    `RunContext.enemy`'s own docstring).
    """
    config = RunConfig(
        build=build, level=level,
        enemy=kw.pop("enemy", "baseline"),
        enemy_options=kw.pop("enemy_options", {}),
        build_options=kw.pop("build_options", {}),
    )
    roster = Roster(characters=[Entity(name="c", hp=10, base_stats={})],
                    enemies=[Entity(name="e", hp=10, base_stats={})])
    return RunContext(config=config, roster=roster, described={})


def _availability(name: str, ctx: RunContext, key: tuple[str, ...]) -> "str | None":
    return _breakdown(name).availability(ctx, key)


# ---------------------------------------------------------------------------
# The declaration
# ---------------------------------------------------------------------------

def test_every_registered_adapter_declares_its_half():
    """The protocol gained a method, so the registry must answer it everywhere —
    including the baseline subject, which is not a build."""
    for name in available_builds():
        adapter = get_adapter(name)
        for level in adapter.available_levels():
            declared = adapter.forced_save_abilities(
                RunConfig(build=name, level=level, enemy="none"))
            assert isinstance(declared, frozenset)


def test_war_angel_declares_no_save_forcing_at_any_level():
    """The EMPTY value, and the one that makes the whole mechanism fire.

    Verified against the module rather than assumed: `war_angel.py` contains no
    `save_stat`, no `save_spell` choice and no zone, so nothing in its plan can put a
    save into the channel in either direction.
    """
    adapter = get_adapter("war_angel")
    for level in adapter.available_levels():
        assert adapter.forced_save_abilities(
            RunConfig(build="war_angel", level=level, enemy="none")) == frozenset()


@pytest.mark.parametrize("build", ["starfire_scion", "baseline"])
def test_the_two_save_spell_builds_declare_dex_at_every_level(build):
    adapter = get_adapter(build)
    for level in adapter.available_levels():
        assert adapter.forced_save_abilities(
            RunConfig(build=build, level=level, enemy="none")) == frozenset({"dex_save"})


def test_the_baseline_subjects_declaration_reads_its_own_constant():
    """One source: §3.5.1's save spell is declared once, in the build module."""
    assert get_adapter("baseline").forced_save_abilities(
        RunConfig(build="baseline", level=5, enemy="none")
    ) == frozenset({baseline_character.SAVE_SPELL_SAVE})


def test_silvertails_declaration_follows_the_zone_option():
    """The OPTION-dependent value — the reason the protocol takes a whole `RunConfig`
    rather than a level.

    It tracks the factory exactly, including the part that is easy to get wrong: only
    L10 carries a `spirit_guardians` row, so asking for the zone at L4 or L8 builds no
    zone and declares nothing, matching the factory's own `data.get(...)`.
    """
    adapter = get_adapter("silvertail")
    zone = {"zone_effect": "spirit_guardians"}

    assert adapter.forced_save_abilities(RunConfig(
        build="silvertail", level=10, enemy="none", build_options=zone,
    )) == frozenset({"wis_save"})

    # The ability is read off the level row, not written out here either.
    assert (silvertail.LEVELS[10]["spirit_guardians"]["save_stat"] == "wis_save")

    for level in (4, 8):
        assert adapter.forced_save_abilities(RunConfig(
            build="silvertail", level=level, enemy="none", build_options=zone,
        )) == frozenset()
    assert adapter.forced_save_abilities(RunConfig(
        build="silvertail", level=10, enemy="none",
    )) == frozenset()


def test_starfire_does_NOT_declare_its_sanctuary_wis_save():
    """Only what reaches the CHANNEL counts, which is narrower than "saves this build
    forces" — and this is the case that makes the distinction load-bearing.

    `starfire_scion.py` rolls a `wis_save` for Sanctuary's `negate_save`, but that save
    is resolved inside `resolve_attack_roll` and NOTHING records it: the channel has
    exactly two writers (`resolve_save_damage`, `resolve_control_save`) and that is not
    one of them.  Declaring `wis_save` would hold an empty cell open on the strength of
    a save no metric can see.
    """
    assert "wis_save" not in get_adapter("starfire_scion").forced_save_abilities(
        RunConfig(build="starfire_scion", level=15, enemy="none"))


def test_an_adapter_that_does_not_declare_FAILS_LOUDLY():
    """The `needs_roster` precedent: a capability detected by `hasattr` lets an adapter
    forget it silently, and forgetting here means either discarding a real measurement
    or re-creating the unflagged-zero defect.  So the predicate raises with a message
    that names the method, rather than guessing a default in either direction."""
    class Undeclared:
        name = "undeclared"

        def available_levels(self):
            return [1]

        def option_schema(self):
            return {}

        def build(self, config, rng):                      # pragma: no cover
            raise NotImplementedError

        def describe(self, config):                        # pragma: no cover
            return {}

    from src.evaluation import adapters as adapter_registry

    adapter_registry.register(Undeclared())
    try:
        ctx = _context("undeclared", 1, enemy="baseline")
        with pytest.raises(NotImplementedError, match="forced_save_abilities"):
            _availability("saves_forced_per_round", ctx, ("cha_save", ALL))
    finally:
        adapter_registry._REGISTRY.pop("undeclared", None)


# ---------------------------------------------------------------------------
# The resolved enemy block — the enemy half, and §4's unmet requirement
# ---------------------------------------------------------------------------

def test_the_resolved_block_publishes_the_bands_actual_weights():
    """§4 asked for exactly this and did not have it: "band save weights must be
    recorded as the actual weights drawn from the frozen table, not as 'default'".
    `BaselineEnemyPolicy.describe_parameters()` has published them since s38 and
    nothing serializes that block, so the one §4 requirement naming them by name was
    unmet in every artifact the project has written.

    Asserted as EQUALITY with the table rather than as a shape, so the block cannot
    drift into being a second source for the weights.
    """
    for level in (1, 4, 5, 10, 11, 16, 17, 20):
        block = resolve(RunConfig(build="baseline", level=level, enemy="baseline",
                                  enemy_options={"control": True}))
        assert block["save_weights"]["damage"] == dict(
            band_save_weights(level, band=block["band"]))
        assert block["save_weights"]["control"] == dict(
            band_control_weights(level, band=block["band"]))


@pytest.mark.parametrize("kind", ["scripted", "none"])
def test_a_non_forcing_enemy_publishes_two_empty_channels(kind):
    """An EMPTY channel means "cannot force a save here at all", which is a different
    statement from "every ability has weight zero" — and is what lets one predicate
    serve a passive target and a mis-banded ability alike."""
    block = resolve(RunConfig(build="war_angel", level=13, enemy=kind))
    assert block["save_weights"] == {"damage": {}, "control": {}}


def test_the_control_channel_is_empty_until_the_option_is_on():
    """Reporting weights the policy will never read is the §4 failure in the other
    direction, so the control channel is published only when it is live."""
    off = resolve(RunConfig(build="war_angel", level=13, enemy="baseline"))
    on = resolve(RunConfig(build="war_angel", level=13, enemy="baseline",
                           enemy_options={"control": True}))
    assert off["save_weights"]["control"] == {}
    assert on["save_weights"]["control"]
    assert off["save_weights"]["damage"] == on["save_weights"]["damage"]


def test_the_two_channels_carry_DIFFERENT_abilities_at_the_same_band():
    """Why the channels are nested rather than merged into one ability set.  Measured,
    at the two bands where they disagree in opposite directions."""
    low = resolve(RunConfig(build="war_angel", level=4, enemy="baseline",
                            enemy_options={"control": True}))["save_weights"]
    assert "cha_save" not in low["damage"]
    assert "cha_save" in low["control"]

    high = resolve(RunConfig(build="baseline", level=20, enemy="baseline",
                             enemy_options={"control": True}))["save_weights"]
    assert "wis_save" not in high["damage"]
    assert "wis_save" in high["control"]
    assert "int_save" not in high["damage"] and "int_save" not in high["control"]


# ---------------------------------------------------------------------------
# The predicate
# ---------------------------------------------------------------------------

def test_a_structurally_impossible_cell_is_UNAVAILABLE_not_zero():
    """The §14 defect, directly: War Angel below L11, where neither side can force a
    CHA save."""
    for level in (1, 4, 5, 10):
        reason = _availability("saves_forced_per_round",
                               _context("war_angel", level), ("cha_save", ALL))
        assert reason is not None, level
        assert "cha_save" in reason
        # Names BOTH producers, so a reader can see why the cell has none.
        assert "band_save_weights" in reason
        assert "forced_save_abilities" in reason


def test_the_same_cell_is_MEASURED_once_the_band_carries_it():
    """The other value of the branch, and the guard against over-reach: band 11-16
    gives `cha_save` a weight of 20, so the cell has a producer and must report
    normally.  A predicate that keyed on the ABILITY alone would fail here."""
    for level in (11, 16):
        assert _availability("saves_forced_per_round",
                             _context("war_angel", level),
                             ("cha_save", ALL)) is None


def test_the_defect_reaches_the_baseline_subject_at_L17_20():
    """What #6a could not see, because War Angel stops at 16.

    At band 17+ the damage weights are `{str, dex, con, cha}` and the control weights
    `{str, dex, con, wis, cha}`, so `int_save` has no producer in either channel at any
    option setting — on the framework's OWN subject, the fixture whose completeness is
    the reason framework correctness does not wait on content.
    """
    for level in (17, 20):
        for options in ({}, {"control": True}):
            ctx = _context("baseline", level, enemy_options=options)
            assert _availability("saves_forced_per_round", ctx,
                                 ("int_save", ALL)) is not None
        # `wis_save` is impossible in the DAMAGE channel but reachable through
        # control, so it is unavailable only while control is off — which is the pair
        # of values that proves the predicate reads the channel and not just the band.
        assert _availability("saves_forced_per_round", _context("baseline", level),
                             ("wis_save", ALL)) is not None
        assert _availability(
            "saves_forced_per_round",
            _context("baseline", level, enemy_options={"control": True}),
            ("wis_save", ALL)) is None


def test_the_build_side_alone_keeps_a_cell_available():
    """The row the roll call found unfixtured, and the one that decides whether this
    change throws real data away.

    Silvertail L10 with the Spirit Guardians zone against `enemy="none"` is the only
    configuration in the project where the BUILD is the sole producer: the enemy is
    passive and forces nothing, and the zone forces a `wis_save` on every occupant at
    its turn boundary.  The cell must stay available — and `str_save`, which neither
    side can force there, must not.
    """
    ctx = _context("silvertail", 10, enemy="none",
                   build_options={"zone_effect": "spirit_guardians"})
    assert _availability("saves_forced_per_round", ctx, ("wis_save", ALL)) is None
    assert _availability("saves_forced_per_round", ctx, ("str_save", ALL)) is not None

    # Drop the zone and the same cell loses its only producer.
    bare = _context("silvertail", 10, enemy="none")
    assert _availability("saves_forced_per_round", bare, ("wis_save", ALL)) is not None


def test_the_damage_channel_is_judged_on_the_damage_weights():
    """`[cha_save|damage]` at band 0-4 is impossible even with control ON, because
    turning control on cannot add an ability to the DAMAGE channel."""
    ctx = _context("war_angel", 4, enemy_options={"control": True})
    assert _availability("saves_forced_per_round", ctx,
                         ("cha_save", "damage")) is not None
    assert _availability("saves_forced_per_round", ctx,
                         ("cha_save", "control")) is None


def test_a_cell_is_available_if_EITHER_channel_can_produce_it():
    """The ALL-channel key is a margin over the channel dimension, so one producing
    channel is enough.  `cha_save` at band 0-4 is damage-impossible and
    control-possible, so the margin flips on the control option alone."""
    assert _availability("saves_forced_per_round", _context("war_angel", 4),
                         ("cha_save", ALL)) is not None
    assert _availability(
        "saves_forced_per_round",
        _context("war_angel", 4, enemy_options={"control": True}),
        ("cha_save", ALL)) is None


def test_the_control_channels_own_reason_still_comes_first():
    """Order is load-bearing: the control reason is the one a caller can act on in a
    single keyword and it says so, while the ability reason cannot be acted on at all.
    Folding them would lose exactly the distinction the per-METRIC ritual's
    availability check protects — so with control off, `[*|control]` must still return
    the control reason and not an ability one."""
    reason = _availability("saves_forced_per_round", _context("war_angel", 13),
                           (ALL, "control"))
    assert reason is not None
    assert "control channel is switched off" in reason
    assert "enemy_options={'control': True}" in reason


def test_a_margin_is_unavailable_only_when_NOTHING_can_be_forced():
    """Margins are NOT exempt here, unlike `_role_cell_availability`'s.

    A `[*|*]` zero on a run with no producer at all is the same false measurement one
    aggregation level up — and this is the configuration that reaches it: a passive
    enemy and a build that forces nothing.  With an acting enemy the margin must stay
    available, which is the other value.
    """
    assert _availability("saves_forced_per_round",
                         _context("war_angel", 13, enemy="none"),
                         (ALL, ALL)) is not None
    assert _availability("saves_forced_per_round", _context("war_angel", 13),
                         (ALL, ALL)) is None


# ---------------------------------------------------------------------------
# The two siblings must now state ONE fact ONE way
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level", [4, 20])
def test_the_two_save_breakdowns_AGREE_on_every_cell(level):
    """§14's complaint was not that a cell was wrong but that two cells describing one
    structural fact rendered incompatibly.  Asserted over the whole key space of both
    breakdowns, in both directions, rather than on the one cell that was noticed.
    """
    ctx = _context("baseline", level)
    forced_keys = _breakdown("saves_forced_per_round").keys()
    # The two breakdowns share one key space by declaration; asserted rather than
    # assumed, because the agreement below would be vacuous over a smaller set.
    assert set(forced_keys) == set(_breakdown("save_fail_rate").keys())
    for key in forced_keys:
        forced = _availability("saves_forced_per_round", ctx, key)
        rate = _availability("save_fail_rate", ctx, key)
        assert (forced is None) == (rate is None), (level, key, forced, rate)


def test_the_cell_that_started_this_no_longer_renders_as_a_confident_zero():
    """End to end, on a real run, which is where the defect was actually visible: not
    `0.0 +/- 0.0, converged=True, available=True` but UNAVAILABLE with a reason.

    War Angel L4 at a realistic size, the #6a regime.  `dex_save` beside it must still
    be measured, because the whole risk of this change is that it silences real data.
    """
    report = build_report(simulate(RunConfig(
        build="war_angel", level=4, enemy="baseline", n_days=400, seed=11)))
    breakdown = report.breakdowns["saves_forced_per_round"]

    cha = breakdown[("cha_save", ALL)]
    assert cha.available is False
    assert cha.value is None
    assert cha.converged is False
    assert "cha_save" in cha.note

    dex = breakdown[("dex_save", ALL)]
    assert dex.available is True and dex.value is not None and dex.value > 0
