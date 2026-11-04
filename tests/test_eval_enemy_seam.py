"""
Mechanism tests for the ENEMY-CONSTRUCTION SEAM — evaluation_framework.md §3.4,
§13 step 5: the parallel half (5a, session 50) and the DELETION half (5b, session 52).

Per [[validate-mechanism-not-build-value]] nothing here asserts that a DPR value is
"correct".  The one place exact values appear is :func:`test_golden_dpr_under_the_
standardized_enemy`, which is §12 replacement 1 and asserts "nothing changed",
never "this is right".


THE ROLL CALL (per-feature ritual step 5 — written BEFORE the tests)
====================================================================
One row per DECLARATION this change touches, one column naming the fixture that
covers each VALUE.  An empty cell is an untested value no matter how many tests
exist.  Writing it first found three values with no production fixture at all (the
fourth session running that it has) — all three are flagged BUILT below.

THE s52 (5b) ROLL CALL — the DELETION's declarations
---------------------------------------------------
Written before the deletion, and it found a gap: **the six saves the dummy GAINS have
no fixture anywhere in the corpus.**  Nothing forces a save on the enemy except
Starfire's dex path, so "the dummy now carries the table's saves" would have shipped as
an untested claim about a stat block — while what matters is whether a SAVE RESOLVES
against it.  Hence `test_a_save_forced_on_the_dummy_now_resolves_against_the_tables_
bonus`, which drives a real `resolve_saving_throw` and asserts the counterfactual too.

| declaration                        | value                   | fixture                                      |
|------------------------------------|-------------------------|----------------------------------------------|
| `RunConfig.enemy` required         | omitted                 | `..._is_required_and_has_no_default` (TypeError) |
|                                    | retired name            | `..._fails_with_an_explanation_not_as_an_unknown_value` |
|                                    | unknown name            | `test_unknown_enemy_kind_still_rejected`     |
| `enemy.resolve()["resolved"]`      | True (only value now)   | all three kinds, `..._reports_a_RESOLVED_enemy` |
| overlay stat-block write           | provably redundant      | full build × level cross-product             |
| dummy's six saves                  | present on every build  | `..._carries_all_six_saves`, all three       |
|                                    | RESOLVES a save         | **THE GAP** — war_angel L13 + counterfactual |
| factory enemy policy               | none, on every build    | `..._installs_an_enemy_policy_any_more`, ×3  |
| `_ally_roster`                     | allies present          | starfire L15, party_size=4 → uniform 25×4 (s54) |
|                                    | no allies               | war_angel L13, party_size=1 → None (solo path)  |
| `_requires_control_channel`        | 3 answers (was 7)       | `..._three_control_unavailability_reasons_...`|
| console "NOT RESOLVED"             | unreachable             | all three kinds assert its ABSENCE           |
| `enemy_path` prefix                | constant, kept          | `test_enemy_path_still_distinguishes_...`    |

THE s50 (5a) ROLL CALL, kept for the record.  Three rows are struck through below:
their VALUES were `build_default`, which no longer exists, and the s52 rows above are
what replaced each one.

| declaration                        | value                   | fixture                                      |
|------------------------------------|-------------------------|----------------------------------------------|
| ~~`RunConfig.enemy`~~              | ~~build_default~~       | ~~war_angel L13~~ — RETIRED s52              |
| `RunConfig.enemy`                  | baseline                | all three builds, L10/L13/L15                |
|                                    | scripted                | war_angel L13                                |
|                                    | none                    | war_angel L13                                |
| ~~`enemy.resolve()["resolved"]`~~  | ~~False~~               | ~~enemy="build_default"~~ — UNREACHABLE s52  |
|                                    | True                    | enemy="baseline"                             |
| `enemy.resolve()["acts"]`          | True                    | baseline, scripted                           |
|                                    | False                   | none                                         |
| `enemy_options["control"]`         | False (default)         | war_angel L13 baseline                       |
|                                    | True                    | war_angel L13 baseline + control             |
| `enemy_options["mitigation"]`      | False (default)         | war_angel L13 baseline                       |
|                                    | True                    | silvertail L10 (typed damage — the only      |
|                                    |                         | roster whose damage mitigation can TOUCH)    |
| `enemy_options["focus"]`           | character (default)     | silvertail L10                               |
|                                    | summon                  | silvertail L10 focus=summon                  |
|                                    | summon, no summon       | war_angel L13 → ValueError                   |
| `enemy_options["band_override"]`   | None (default)          | every other case                             |
|                                    | "17+"                   | war_angel L13 band_override                  |
| `enemy_options["soft_factor"]`     | None → resolved default | baseline + control (the §4 example by NAME)  |
|                                    | explicit                | baseline + control + soft_factor=0.25        |
| `enemy_options["legendary_cadence"]`| False (default)        | every other case                             |
|                                    | True, band with 0 swings| war_angel L4  (bands 0-4/5-10 round to 0)    |
|                                    | True, band with >0      | war_angel L13 (band 11-16 → 1)               |
| `_OPTION_KINDS` refusal            | option applies          | control on baseline                          |
|                                    | option does NOT apply   | control on scripted → ValueError             |
| `_CONTROL_DEPENDENT` refusal       | control on              | soft_factor + control=True accepted          |
|                                    | control off             | soft_factor alone → ValueError               |
| ~~`validate_options` build_default~~| ~~empty / non-empty~~  | ~~enemy="build_default"~~ — the whole branch |
|                                    |                         | is DELETED s52                               |
| ~~`install()` no-op branch~~       | ~~no-op~~               | ~~build_default~~ — install is unconditional |
|                                    | overlay                 | enemy="baseline"/"scripted"                  |
|                                    | policy removed          | enemy="none"                                 |
|                                    | no enemies in roster    | **BUILT** — no shipped build fields zero     |
|                                    | >1 enemy in roster      | **BUILT** — no shipped build fields two      |
| `_complete_stat_block`             | AC unchanged            | every build × every level (the s50 finding)  |
|                                    | saves ADDED             | war_angel (its dummy carries none)           |
|                                    | saves already present   | silvertail (its dummy carries all six)       |
| `ScriptedEnemyPolicy.describe_`    | single_target           | standardized scripted                        |
|   `parameters()["targeting"]`      | weighted_roster         | **BUILT** — unreachable through RunConfig:   |
|                                    |                         | the standardized kind never passes a roster, |
|                                    |                         | and build_default never calls describe_      |
|                                    |                         | parameters(). Trigger: a standardized multi- |
|                                    |                         | entity kind, blocked on §3.3 multi-character |
| `BaselineEnemyPolicy.describe_`    | control off             | baseline, control absent from the block      |
|   `parameters()`                   | control on              | baseline + control, nine extra keys          |
| `_requires_control_channel`        | std baseline, control on| available (None)                             |
|   (SEVEN distinguishable answers)  | std baseline, off       | war_angel L13 baseline                       |
|                                    | std scripted            | war_angel L13 scripted                       |
|                                    | std none                | war_angel L13 none                           |
|  ~~(three bd branches)~~          | ~~bd + scripted /~~     | ~~build_default~~ — DELETED s52; the three   |
|                                    | ~~baseline / passive~~  | surviving answers are in the s52 table above |
| `_requires_mitigation_profile`     | available               | any kind + mitigation=True                   |
|                                    | unavailable             | any kind WITHOUT mitigation=True (s52)       |
| `typed_damage_share` numerator     | no profile installed    | silvertail L10, no mitigation                 |
|   (the s50 BUGFIX)                 | profile installed       | silvertail L10 + mitigation (was 1.1054)     |

DO NOT LET THE PROSE OVERCLAIM (s49's half of step 5)
-----------------------------------------------------
Every magnitude claim below was MEASURED before it was written, and one of them
killed the assertion this session was handed:

* The handoff expected ``attack_roll_rate[characters|hit]`` to move by many standard
  errors.  **It does — and the first version of this module asserted the opposite and
  was caught by its own test at 7.7σ.**  The reasoning that failed: a hit rate is a
  function of the enemy's AC, the baked-in AC already equals the table's AC at every
  level of every build (pinned at the top of this module), therefore the rate cannot
  move.  The missing term is that a hit rate also depends on the character's
  attack-roll MODIFIER STACK, and War Angel concentrates on Bless (+1d4 to its own
  attacks) — so incoming pressure reaches its accuracy through concentration breaks.
  The honest claim is about the MECHANISM, and it is in
  ``test_the_attacks_channel_detects_the_seam_through_bless_not_through_ac``.
* What makes that an explanation rather than a story is that it predicts WHICH cells
  move: Bless is flat, so it cannot change P(natural 20), and the crit cell duly
  stays put (1.2σ) while the hit cell moves 15σ.  Both are asserted.
* The same mechanism orders the DPR goldens:  more incoming attacks → more
  concentration checks → more broken Bless → less of the character's own damage.
  Measured at 400 days, seed 11: ``none`` 35.458 > ``scripted`` 34.941 >
  ``baseline`` 34.763 > ``legendary_cadence`` 34.430.  That ORDERING is the
  assertion, not any of the values.
* The lesson, recorded because it is the ritual's own: the overclaim here was not a
  careless adjective, it was a plausible mechanical argument with one term missing,
  and nothing but running it would have found that.
"""

from __future__ import annotations

import math

import pytest

from src.builds import enemy_stats, silvertail, starfire_scion, war_angel
from src.builds.enemy import BaselineEnemyPolicy, ScriptedEnemyPolicy
from src.entity import Entity
from src.evaluation import console
from src.evaluation import enemy as enemy_seam
from src.evaluation.config import RunConfig
from src.evaluation.metrics import METRICS, RunContext
from src.evaluation.roster import Roster
from src.evaluation.runner import assemble, run, simulate
from src.verbs import resolve_saving_throw
from src.rng import SeededRNG


def _ctx(config: RunConfig) -> RunContext:
    """A :class:`RunContext` for *config*, built the way the runner builds it."""
    adapter = config.validate()
    _, roster = adapter.build(config, SeededRNG(config.seed))
    return RunContext(config=config, roster=roster,
                      described=adapter.describe(config))


def _control_reason(config: RunConfig) -> str:
    value = run(config.replace(n_days=2)).values["control_turns_lost_per_round"]
    assert not value.available
    return value.note or ""


def built(config: RunConfig):
    """``(runner, roster)`` assembled exactly as a real run assembles it.

    **NOW DELEGATES TO ``runner.assemble`` (s54), and the reason is a finding.** This
    helper used to hand-mirror ``simulate``'s body — ``adapter.build`` then
    ``enemy.install`` — with a docstring saying it existed "so the install step cannot
    silently go missing from a test the way it could have gone missing from an adapter".
    When step 7 added ``party.install`` to ``simulate``, this mirror kept producing
    PARTYLESS rosters and three tests asserted the pre-party behaviour while passing.
    It went missing in precisely the way it was written to prevent, which is the seam
    check applied to a test helper: a duplicated SEQUENCE is as much a second source as
    a duplicated number.
    """
    config.validate()
    return assemble(config, SeededRNG(0))


# ---------------------------------------------------------------------------
# The s50 migration finding, carried into s52 as its CONSEQUENCE
# ---------------------------------------------------------------------------
#
# s50 pinned `war_angel.LEVELS[level]["enemy_ac"] == enemy_stats.baseline_ac(level)` at
# all 16 levels, and the Starfire equivalent, because that equality is what falsified
# the "standardizing the enemy will move the hit rate a lot" expectation.  Step 5b
# DELETED the left-hand side of both: there is no baked-in `enemy_ac` to compare.
#
# Those tests are not simply gone, though, because the equality they proved is exactly
# what made 5b safe — and §3.4 warns against trusting an equality that holds "for a
# reason that will stop holding".  So they are replaced by the assertion the deletion
# actually needs: that the factory's dummy ALREADY equals what the overlay would write.
# One source (`enemy_stats`), two writers (`make_baseline_enemy` and
# `_complete_stat_block`), and the second write proved redundant rather than assumed —
# which is the §3.4 s52 block's own promise, discharged here.

_ALL_BUILD_LEVELS = (
    [("war_angel", lvl) for lvl in sorted(war_angel.LEVELS)]
    + [("starfire_scion", lvl) for lvl in sorted(starfire_scion.LEVELS)]
    + [("silvertail", lvl) for lvl in sorted(silvertail.LEVELS)]
)


@pytest.mark.parametrize("build,level", _ALL_BUILD_LEVELS)
def test_the_overlays_stat_block_write_is_provably_redundant(build, level):
    """The factory's enemy already carries every stat the overlay writes, at the same
    value, for every build at every level.

    This is the s52 replacement for s50's AC pin, and it is the stronger statement:
    s50 could only compare ONE key (the AC) because the baked-in rows carried only
    that one, and it compared two hand-copied constants.  Here both sides are reads of
    `enemy_stats`, so what is asserted is that the two WRITERS agree — which is what
    makes `_complete_stat_block` a no-op on the stat block and keeps the AC-stability
    premise the two attack-rate tests below rest on.

    Asserted across the full cross-product rather than at a sample, for the same reason
    s50 did: this is a premise, and a premise sampled is a premise assumed.
    """
    config = RunConfig(build=build, level=level, n_days=1, enemy="baseline")
    adapter = config.validate()

    # The factory's roster, with nothing installed: `build()` no longer overlays (s52
    # moved the install into `runner.simulate`), so this is the un-overlaid enemy.
    _, roster = adapter.build(config, SeededRNG(0))
    before = dict(roster.enemies[0].base_stats)

    # Now apply the overlay by hand and require it to change nothing.
    runner_after, roster_after = adapter.build(config, SeededRNG(0))
    enemy_seam.install(runner_after, roster_after, config)
    after = roster_after.enemies[0].base_stats

    assert after == before
    assert before["ac"] == enemy_stats.baseline_ac(level)


@pytest.mark.parametrize("build", ["war_angel", "starfire_scion", "silvertail"])
def test_every_builds_dummy_now_carries_all_six_saves(build):
    """§3.4 item 1's REAL content, as opposed to the AC — and the one place where the
    two sides of the seam were not merely "equal for now" but silently UNEQUAL.

    Before s52 War Angel's dummy carried `{ac, attack_bonus, damage_dice,
    damage_bonus}` and NO saves; Starfire's carried one (`dex_save`); Silvertail's
    carried all six.  `Entity.stat()` returns 0 for a missing key by design, so a save
    forced on the first two resolved against a +0 modifier.  Nothing surfaced it
    because no War Angel ability forces a save on its target — the inequality was
    unreachable, not absent, which is strictly worse than a dormant equality because
    no equality was holding it stable and nothing would have failed when it was first
    reached.  Now every build's dummy is the same complete stat block.
    """
    level = max(getattr(__import__("src.builds." + build, fromlist=["LEVELS"]), "LEVELS"))
    config = RunConfig(build=build, level=level, n_days=1, enemy="baseline")
    _, roster = config.validate().build(config, SeededRNG(0))
    stats = roster.enemies[0].base_stats
    for save in ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save"):
        assert stats[save] == enemy_stats.baseline_save(level, save)
    assert stats["enemy_save_dc"] == enemy_stats.baseline_save_dc(level)


def test_a_save_forced_on_the_dummy_now_resolves_against_the_tables_bonus():
    """THE ROLL-CALL GAP, found at design time and measured rather than argued.

    The six saves the dummy gains are a DECLARATION value with no fixture anywhere in
    the corpus: nothing forces a save on the enemy except Starfire's dex path, so
    "the dummy now carries the table's saves" would have shipped as an untested claim
    about a stat block, while the thing that matters is whether a SAVE RESOLVES against
    it.  This drives a real `resolve_saving_throw` against War Angel's L13 dummy — the
    build whose dummy carried no saves at all — and asserts the outcome flips exactly
    where the table's +7 CON bonus says it should.

    Measured, not reasoned: at DC 15 against con_save +7, a d20 of 7 clears it (7+7=14
    fails, so the boundary is 8: 8+7=15 >= 15 succeeds).  Under the OLD +0 default the
    same roll of 8 gave 8, a clear failure.  So the identical die flips the verdict,
    which is the smallest demonstration that the +0 default was a wrong answer and not
    a missing one.
    """
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline")
    _, roster = config.validate().build(config, SeededRNG(0))
    dummy = roster.enemies[0]
    assert dummy.stat("con_save") == enemy_stats.baseline_save(13, "con_save") == 7

    class _FixedDie:
        """A d20 that always shows 8 — the boundary the docstring names."""
        def __init__(self): self.rolls = []
        def roll_one(self, sides):
            self.rolls.append(sides)
            return 8
        def roll(self, n, sides):
            return [self.roll_one(sides) for _ in range(n)]

    rng = _FixedDie()
    assert resolve_saving_throw(dummy, "con_save", dc=15, rng=rng) is True, \
        "d20 8 + the table's +7 = 15, which meets DC 15"
    assert rng.rolls == [20], "one d20 and nothing else — no dice-modifiers on the dummy"

    # The counterfactual, asserted rather than described: strip the save the way the
    # pre-5b dummy had it and the SAME die fails.
    del dummy.base_stats["con_save"]
    assert dummy.stat("con_save") == 0
    assert resolve_saving_throw(dummy, "con_save", dc=15, rng=_FixedDie()) is False


def test_overlay_leaves_an_already_complete_stat_block_alone():
    """Silvertail's dummy is already built from ``enemy_base_stats``, so the overlay
    is a no-op on it.  The uncovered VALUE of the saves-already-present branch."""
    config = RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=10, n_days=1)
    adapter = config.validate()
    _, before = adapter.build(config, SeededRNG(0))
    baseline_block = dict(before.enemies[0].base_stats)

    _, after = adapter.build(config.replace(enemy="baseline"), SeededRNG(0))
    for key, value in baseline_block.items():
        assert after.enemies[0].base_stats[key] == value


# ---------------------------------------------------------------------------
# RunConfig: the fields went live (§3.1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["baseline", "scripted", "none"])
def test_every_enemy_kind_is_now_accepted(kind):
    """Steps 1-4 raised ``NotImplementedError`` for all three; step 5a accepted them
    alongside a fourth, ``build_default``, which step 5b retired (see below)."""
    RunConfig(build="war_angel", level=13, n_days=1, enemy=kind).validate()


def test_enemy_is_required_and_has_no_default():
    """§3.4's principle one level up: a run cannot decline to say what it faced.

    Retiring ``build_default`` retired the schema's transitional default, and s52's
    decision was NOT to choose another one — a default is an implicit enemy, and an
    implicit enemy is exactly what makes two reports incomparable.  Asserted at the
    dataclass level rather than as a validation rule, which is what makes it
    unforgettable: a caller cannot construct the config at all.
    """
    with pytest.raises(TypeError, match="enemy"):
        RunConfig(build="war_angel", level=13, n_days=1)      # type: ignore[call-arg]


def test_the_retired_kind_fails_with_an_explanation_not_as_an_unknown_value():
    """``build_default`` was the DEFAULT for two sessions, so it will appear in old
    scripts and in anyone's muscle memory.  "not one of (...)" would send a reader
    looking for a typo; the refusal names what happened and what to pass instead,
    including the one substitution that is bit-identical rather than merely close.
    """
    with pytest.raises(ValueError) as excinfo:
        RunConfig(build="war_angel", level=13, n_days=1, enemy="build_default")
    message = str(excinfo.value)
    assert "retired in s52" in message
    assert "enemy='baseline'" in message
    assert "'none' for a passive target" in message
    assert "bit-identically" in message


def test_unknown_enemy_kind_still_rejected():
    with pytest.raises(ValueError, match="enemy must be one of"):
        RunConfig(build="war_angel", level=13, n_days=1, enemy="dragon")


def test_unknown_enemy_option_rejected():
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                       enemy_options={"ferocity": 3})
    with pytest.raises(ValueError, match="Unknown enemy option"):
        config.validate()


def test_option_that_the_chosen_kind_cannot_honour_is_refused_not_ignored():
    """The §4 argument, applied per option instead of to the whole field: a config
    claiming ``control=True`` against an enemy with no control channel would make
    provenance document an assumption the run never applied."""
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="scripted",
                       enemy_options={"control": True})
    with pytest.raises(ValueError, match="applies only to enemy kind"):
        config.validate()


def test_control_dependent_option_without_control_is_refused():
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                       enemy_options={"soft_factor": 0.25})
    with pytest.raises(ValueError, match="meaningless without control=True"):
        config.validate()


def test_control_dependent_option_is_accepted_with_control_on():
    RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
              enemy_options={"control": True, "soft_factor": 0.25}).validate()


@pytest.mark.parametrize("options", [
    {"char_target_prob": 1.5},
    {"char_target_prob": -0.1},
])
def test_char_target_prob_must_be_a_probability(options):
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="scripted",
                       enemy_options=options)
    with pytest.raises(ValueError, match="char_target_prob must be in"):
        config.validate()


def test_enemy_is_part_of_the_config_identity():
    """The enemy is a comparability axis (§5.2), so it must change the cache key —
    otherwise two runs against different enemies would collide in the §10 cache.

    All three surviving kinds are compared pairwise rather than against the retired
    default, which is the stronger version of the same check: it is the kinds that
    must not collide with each other, and before s52 one leg of this test leaned on
    ``build_default`` being distinct from everything.
    """
    base = RunConfig(enemy="baseline", build="war_angel", level=13, n_days=1)
    hashes = {kind: base.replace(enemy=kind).config_hash()
              for kind in ("baseline", "scripted", "none")}
    assert len(set(hashes.values())) == 3, hashes
    assert (hashes["baseline"]
            != base.replace(enemy="baseline",
                            enemy_options={"control": True}).config_hash())


# ---------------------------------------------------------------------------
# enemy.resolve() — the §4 provenance block
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["baseline", "scripted", "none"])
def test_every_run_now_reports_a_RESOLVED_enemy(kind):
    """The honest-gap branch is gone, because the gap is gone (s52).

    Through s50-s51 one path reported ``resolved: False`` and a "NOT RESOLVED" note,
    on the principle that a half-filled provenance block is worse than an honest gap
    because it implies the assumptions were recorded when they were not.  That path
    was ``build_default``, and it is deleted — so what replaces the test is the
    assertion that NO run can produce the honest gap any more.  Checked across all
    three kinds, because "unconditionally true" is the claim.
    """
    report = run(RunConfig(build="war_angel", level=13, n_days=2, enemy=kind))
    block = report.provenance.resolved["enemy"]
    assert block["standardized"] is True
    assert block["resolved"] is True
    assert "note" not in block
    assert report.provenance.coverage["enemy_path"] == f"standardized:{kind}"
    assert report.provenance.coverage["enemy_side"].startswith("resolved")


def test_standardized_enemy_reports_the_stat_block_it_installed():
    report = run(RunConfig(build="war_angel", level=13, n_days=2, enemy="baseline"))
    block = report.provenance.resolved["enemy"]
    assert block["standardized"] is True
    assert block["resolved"] is True
    assert block["stat_block"] == enemy_stats.enemy_base_stats(13)
    assert block["band"] == enemy_stats.band_for_level(13)
    assert block["band_source"] == "enemy_stats.band_for_level(13)"
    assert report.provenance.coverage["enemy_path"] == "standardized:baseline"
    assert report.provenance.coverage["enemy_side"].startswith("resolved")


def test_band_override_is_reported_with_its_source():
    block = enemy_seam.resolve(
        RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                  enemy_options={"band_override": "17+"}))
    assert block["band"] == "17+"
    assert block["band_source"] == "enemy_options['band_override']"
    # The MAGNITUDE axis still follows the level (§8's two-axis join).
    assert block["level"] == 13
    assert block["attack_dice"] == enemy_stats.baseline_attack_dice(13)


@pytest.mark.parametrize("kind,acts", [("baseline", True), ("scripted", True),
                                       ("none", False)])
def test_whether_the_enemy_acts_is_now_a_declared_fact(kind, acts):
    """§3.4 item 3: "at what level does the enemy fight back" was a CHARACTER-build
    property (the ``LEVELS[level].get("enemy_attack")`` switch).  Under the seam it
    is declared by the config and recorded in provenance."""
    block = enemy_seam.resolve(
        RunConfig(build="war_angel", level=13, n_days=1, enemy=kind))
    assert block["acts"] is acts


def test_resolved_soft_factor_names_its_source():
    """§4's own worked example: "a config of ``soft_factor=None`` must be recorded as
    ``0.5, from enemy_stats.SOFT_FACTOR``", not as the word "default"."""
    policy = BaselineEnemyPolicy(level=13, primary=Entity(name="c", hp=50),
                                 control=True)
    params = policy.describe_parameters()
    assert params["soft_factor"] == enemy_stats.SOFT_FACTOR
    assert params["soft_factor_source"] == "enemy_stats.SOFT_FACTOR"

    explicit = BaselineEnemyPolicy(level=13, primary=Entity(name="c", hp=50),
                                   control=True, soft_factor=0.25)
    params = explicit.describe_parameters()
    assert params["soft_factor"] == 0.25
    assert params["soft_factor_source"] == "enemy_options['soft_factor']"


def test_options_that_do_not_apply_are_omitted_rather_than_reported_at_default():
    """Reporting ``control: False`` for a ``scripted`` enemy would imply the knob was
    in force and simply off, when in fact the kind has no such knob."""
    scripted = enemy_seam.resolved_options(
        RunConfig(build="war_angel", level=13, n_days=1, enemy="scripted"))
    assert "control" not in scripted
    assert "char_target_prob" in scripted

    baseline = enemy_seam.resolved_options(
        RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline"))
    assert baseline["control"] is False
    assert "char_target_prob" not in baseline
    # control-dependent knobs are absent until control is on.
    assert "soft_factor" not in baseline
    assert "soft_factor" in enemy_seam.resolved_options(
        RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                  enemy_options={"control": True}))


def test_mitigation_option_reports_the_installed_multiplier_profile():
    block = enemy_seam.resolve(
        RunConfig(build="silvertail", level=10, n_days=1, enemy="baseline",
                  enemy_options={"mitigation": True}))
    assert block["damage_multiplier"] == enemy_stats.band_damage_multipliers(
        10, band=enemy_stats.band_for_level(10))


# ---------------------------------------------------------------------------
# enemy.install() — the policy is actually replaced
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("build,level", [("war_angel", 13), ("starfire_scion", 15),
                                         ("silvertail", 10)])
def test_no_factory_installs_an_enemy_policy_any_more(build, level):
    """§3.4 item 3 closed, asserted from the factory side.

    This is the s52 inverse of s50's ``test_build_default_leaves_the_factory_policy_
    untouched``, which checked that the no-op path left the factory's policy as the
    SAME OBJECT.  There is no factory policy to leave: all three builds returned one at
    these levels (War Angel and Starfire a ``ScriptedEnemyPolicy``, Silvertail a
    ``BaselineEnemyPolicy``), and now none does.  Checked at the three levels where
    each build's old ``enemy_attack`` row made its enemy act, which is exactly where a
    leftover would hide.
    """
    config = RunConfig(build=build, level=level, n_days=1, enemy="baseline")
    runner, roster = config.validate().build(config, SeededRNG(0))
    assert roster.enemies[0].id not in runner.policies
    assert not any(isinstance(pol, (ScriptedEnemyPolicy, BaselineEnemyPolicy))
                   for pol in runner.policies.values())


def test_baseline_kind_installs_the_table_driven_policy():
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline")
    runner, roster = built(config)
    policy = runner.policies[roster.enemies[0].id]
    assert isinstance(policy, BaselineEnemyPolicy)
    params = policy.describe_parameters()
    assert params["policy"] == "baseline"
    assert params["n_attacks"] == enemy_stats.baseline_n_attacks(13)
    assert params["forces_saves"] is True


def test_scripted_kind_is_the_attack_roll_half_only():
    """Why ``scripted`` exists at all: ``baseline`` vs ``scripted`` at one level is
    the comparison the baked-in paths could never express, because they differed in
    the model AND the numbers at once."""
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="scripted")
    runner, roster = built(config)
    policy = runner.policies[roster.enemies[0].id]
    assert isinstance(policy, ScriptedEnemyPolicy)
    params = policy.describe_parameters()
    assert params["forces_saves"] is False
    assert params["control_channel"] is False
    assert params["n_attacks"] == enemy_stats.baseline_n_attacks(13)
    # `weighted_roster` since s54: the declared party means BOTH kinds split their
    # swings across the friendlies, which is §3.5.3's requirement rather than a
    # property of this kind — if the two kinds differed here, §3.4's comparison arm
    # would differ in targeting MODEL as well as in save-forcing.
    assert params["targeting"] == "weighted_roster"
    # Its damage comes off the Entity (no dice on the Choice), so the overlay must
    # have put the table's dice there.
    n, sides, bonus = enemy_stats.baseline_attack_dice(13)
    assert roster.enemies[0].base_stats["damage_dice"] == (n, sides)
    assert roster.enemies[0].base_stats["damage_bonus"] == bonus


def test_none_kind_removes_the_policy_entirely():
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="none")
    runner, roster = built(config)
    assert roster.enemies[0].id not in runner.policies
    # ...but it is still a complete stat block, not a bare AC.
    assert roster.enemies[0].base_stats["enemy_save_dc"] == \
        enemy_stats.baseline_save_dc(13)


def test_focus_declares_which_entity_the_enemy_fights():
    """DECLARED, not derived from the build — the per-feature step-4 test.  The two
    facts vary independently: Silvertail's own factory switches master-vs-beast off
    its ``zone_effect`` axis, so no derivation from the build could be right."""
    config = RunConfig(build="silvertail", level=10, n_days=1, enemy="baseline")

    runner, roster = built(config)
    assert (runner.policies[roster.enemies[0].id].describe_parameters()["focus"]
            == roster.character.name)

    runner, roster = built(config.replace(enemy_options={"focus": "summon"}))
    params = runner.policies[roster.enemies[0].id].describe_parameters()
    assert params["focus"] == roster.summons[0].name
    assert params["fallback"] == roster.character.name


def test_focus_summon_on_a_build_with_no_summon_is_an_error():
    """Not a silent fall back to the character: that would quietly measure a
    different thing than the config asked for."""
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                       enemy_options={"focus": "summon"})
    with pytest.raises(ValueError, match="has no summons"):
        simulate(config)


def test_install_refuses_a_roster_with_no_enemy():
    """BUILT fixture — no shipped build fields zero enemies."""
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline")
    runner, roster = config.validate().build(config, SeededRNG(0))
    with pytest.raises(ValueError, match="no enemies"):
        enemy_seam.install(runner, Roster(characters=[roster.character]), config)


def test_install_refuses_a_roster_with_two_enemies():
    """BUILT fixture — no shipped build fields two enemies.  The refusal names the
    multi-enemy / spatial deferral rather than silently standardizing one of them."""
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline")
    runner, roster = config.validate().build(config, SeededRNG(0))
    two = Roster(characters=[roster.character],
                 enemies=[roster.enemies[0], Entity(name="second", hp=10 ** 9)])
    with pytest.raises(NotImplementedError, match="installs ONE standardized enemy"):
        enemy_seam.install(runner, two, config)


def test_scripted_policy_reports_weighted_roster_targeting():
    """NO LONGER A BUILT FIXTURE — s52 made this value REACHABLE, and the roll-call
    entry that recorded why it was not is the reason it got fixed rather than deleted.

    s50 wrote: "unreachable through ``RunConfig`` today — the standardized ``scripted``
    kind never passes a roster, and ``build_default`` never calls
    ``describe_parameters()`` at all".  Deleting the baked-in path would have made it
    unreachable full stop, i.e. dead code — which is the trap §7.6 was written about.
    So 5b gave ``char_target_prob`` teeth instead: the off-target share lands on the
    build's ALLIES when it fields any.  s54's declared PARTY is now the production
    fixture — every run with ``party_size > 1`` reaches it — exercised in
    ``test_a_party_splits_the_enemys_swings_by_UNIFORM_weights`` below.  This
    direct-construction case stays as the unit-level check.
    """
    char, ally = Entity(name="char", hp=40), Entity(name="ally", hp=40)
    params = ScriptedEnemyPolicy(target=char, n_attacks=2,
                                 roster=[(char, 2), (ally, 1)]).describe_parameters()
    assert params["targeting"] == "weighted_roster"


def test_declaring_char_target_prob_alongside_a_party_is_REFUSED():
    """§3.5.3's refusal, and the §4 argument behind it.

    **Party size and "how often is the character attacked" are ONE QUANTITY IN TWO
    PLACES.** A config declaring a party of four *and* ``char_target_prob`` claims a
    party the enemy ignores, which is the same failure this option schema already
    refuses for ``focus='summon'`` on a summonless roster. So the split is DERIVED from
    the roster and declaring it as well is refused rather than silently losing.

    **THIS REPLACES ``test_the_off_target_share_lands_on_a_real_ally``**, whose fixture
    was Starfire's ``with_party`` axis — retired in s54 as a second source for the party
    (the seam check's third catch of that shape in s53).
    """
    config = RunConfig(build="starfire_scion", level=15, n_days=1, enemy="scripted",
                       enemy_options={"char_target_prob": 0.4})
    with pytest.raises(ValueError, match="cannot be declared alongside a party"):
        built(config)


def test_a_party_splits_the_enemys_swings_by_UNIFORM_weights():
    """The capability ``char_target_prob`` used to reach, now derived from the roster.

    Asserted as the WEIGHTS rather than as a DPR, because a weight cannot be right by
    luck of the seed. They are integers summing to exactly 100 — not cosmetic: that is
    what makes the multi-entity pre-roll ``roll_one(100)``, the same die the solo path
    rolls, so the two paths stay comparable draw for draw.

    Uniform is a PLACEHOLDER whose replacement is already designed (§3.5.4's threat
    class), and **uniform is the special case where every class is equal**, so nothing
    structural changes when it arrives.
    """
    config = RunConfig(build="starfire_scion", level=15, n_days=1, enemy="scripted")
    runner, roster = built(config)
    policy = runner.policies[roster.enemies[0].id]
    assert policy.describe_parameters()["targeting"] == "weighted_roster"
    assert len(roster.allies) == 3                      # party_size 4 - the character

    weights = dict(policy._roster)                      # noqa: SLF001 — the point
    assert sum(weights.values()) == 100
    # 100 / 4 divides exactly here; where it does not, the remainder goes to the
    # CHARACTER, so the rounding never favours the party.
    assert weights[roster.character] == 25
    assert all(weights[a] == 25 for a in roster.allies)


def test_BOTH_enemy_kinds_now_split_the_same_way():
    """§3.5.3's actual requirement, at the seam rather than at the policy.

    §3.4 claims ``baseline`` vs ``scripted`` isolates "the enemy forces saves" from
    "the enemy swings". **Before s54 that became false the moment a party existed** —
    ``ScriptedEnemyPolicy`` took a weighted roster and ``BaselineEnemyPolicy``
    focus-fired, so the two arms would have differed in targeting MODEL as well. They
    agreed only because the standardized default was focus-fire onto an empty ally
    roster (measured s53: 126,661 vs 105,484 on the character and **0** on the party,
    either way).
    """
    weights = {}
    for kind in ("scripted", "baseline"):
        runner, roster = built(RunConfig(build="starfire_scion", level=15, n_days=1,
                                         enemy=kind))
        policy = runner.policies[roster.enemies[0].id]
        assert policy.describe_parameters()["targeting"] == "weighted_roster"
        weights[kind] = sorted(w for _, w in policy._roster)     # noqa: SLF001
    assert weights["scripted"] == weights["baseline"] == [25, 25, 25, 25]


def test_party_size_1_keeps_char_target_prob_as_the_live_knob():
    """The OTHER branch of the refusal: with no allies the option is still honoured,
    because a config that has not declared a party has not claimed anything.

    This is the solo basis every pre-s54 number was measured on, and it is still
    reachable by declaring it — which is what makes the re-baseline a change of
    DEFAULT rather than a loss of capability.
    """
    config = RunConfig(build="starfire_scion", level=15, n_days=1, enemy="scripted",
                       party_size=1, enemy_options={"char_target_prob": 0.4})
    runner, roster = built(config)
    policy = runner.policies[roster.enemies[0].id]
    assert roster.allies == []
    assert policy.describe_parameters()["targeting"] == "single_target"
    assert policy._roster is None                        # noqa: SLF001
    assert policy.describe_parameters()["char_target_prob"] == 0.4


def test_a_build_with_no_allies_keeps_the_single_target_path():
    """``_ally_roster`` returns None when there is nothing to absorb the off-target
    share, which is what keeps ``char_target_prob`` meaning what it always meant: the
    share goes to an unmodelled party member, i.e. nowhere.

    Needs ``party_size=1`` since s54 — the default of 4 gives every roster allies.
    """
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="scripted",
                       party_size=1, enemy_options={"char_target_prob": 0.4})
    runner, roster = built(config)
    policy = runner.policies[roster.enemies[0].id]
    assert policy.describe_parameters()["targeting"] == "single_target"
    assert policy._roster is None                        # noqa: SLF001


def test_legendary_cadence_is_inert_in_the_low_bands():
    """The toggle's TRUE value has two outcomes and only one is interesting: the
    mean-field count rounds to 0 below band 11-16, so ``True`` at L4 is a no-op."""
    low = enemy_seam.resolve(RunConfig(build="war_angel", level=4, n_days=1,
                                       enemy="baseline",
                                       enemy_options={"legendary_cadence": True}))
    assert enemy_stats.band_legendary_cadence(4) == 0
    assert low["options"]["legendary_cadence"] is True       # declared...

    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                       enemy_options={"legendary_cadence": True})
    runner, roster = built(config)
    params = runner.policies[roster.enemies[0].id].describe_parameters()
    assert params["legendary_swings"] == enemy_stats.band_legendary_cadence(13) > 0


# ---------------------------------------------------------------------------
# No new dice (per-feature ritual step 3)
# ---------------------------------------------------------------------------

class _CountingRNG(SeededRNG):
    """A ``SeededRNG`` that counts calls through the single dice channel."""

    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.calls = 0

    def roll(self, n: int, sides: int) -> list[int]:
        self.calls += 1
        return super().roll(n, sides)


def test_resolve_and_install_draw_no_dice():
    """``resolve`` is a pure read and ``install`` writes data.  Neither may touch
    the dice channel: installation happens once per run, outside combat, which is
    exactly where [[no-new-dice-outside-combat]] applies.
    """
    config = RunConfig(build="silvertail", level=10, n_days=1, enemy="baseline",
                       enemy_options={"control": True, "mitigation": True})
    adapter = config.validate()
    rng = _CountingRNG(0)
    runner, roster = adapter.build(config, rng)
    after_factory = rng.calls

    enemy_seam.resolve(config)
    enemy_seam.install(runner, roster, config)
    assert rng.calls == after_factory


# ---------------------------------------------------------------------------
# §12: enemy independence
# ---------------------------------------------------------------------------

#: The one level ALL THREE builds implement — so the §12 requirement can be stated
#: across the whole corpus rather than across a pair.
SHARED_LEVEL = 10
SHARED_LEVEL_BUILDS = ("war_angel", "starfire_scion", "silvertail")


def test_different_builds_at_one_level_face_an_identical_resolved_enemy():
    """§12's enemy-independence requirement, verbatim: "two different builds at the
    same level, configured with the same ``enemy`` + ``enemy_options``, face an
    enemy with identical resolved parameters".

    This is the assertion the framework could not make before the seam existed: at
    L10 War Angel faced a passive AC-only dummy, Starfire a passive dummy with one
    save, and Silvertail a table-driven ``BaselineEnemyPolicy``.
    """
    blocks = []
    policies = []
    weights = []
    for build in SHARED_LEVEL_BUILDS:
        config = RunConfig(build=build, level=SHARED_LEVEL, n_days=1,
                           enemy="baseline", enemy_options={"control": True})
        runner, roster = built(config)
        blocks.append(enemy_seam.resolve(config))
        params = runner.policies[roster.enemies[0].id].describe_parameters()
        # 'focus'/'fallback' name the ROSTER, which differs by construction — the
        # enemy's own parameters are what must agree.  Since s54 'roster_weights' is a
        # third such key: it is keyed by entity NAME, and the character's name is a
        # property of the build. The WEIGHTS still have to agree, which is checked
        # separately below — that is the §3.4 claim, and "the enemy attacks whichever
        # friendlies are present" was never part of it.
        policies.append({k: v for k, v in params.items()
                         if k not in ("focus", "fallback", "roster_weights")})
        weights.append(sorted(params["roster_weights"].values()))

    first, *rest = blocks
    for other in rest:
        assert other == first
    first_policy, *other_policies = policies
    for other in other_policies:
        assert other == first_policy
    # The DISTRIBUTION of incoming attention is identical even though the names are
    # not: every build at this level is attacked on the same share of swings, which is
    # what makes two builds' defensive numbers comparable at all (§3.5.2).
    first_weights, *other_weights = weights
    assert first_weights == [25, 25, 25, 25]
    for other in other_weights:
        assert other == first_weights


@pytest.mark.parametrize("build", SHARED_LEVEL_BUILDS)
def test_every_build_at_one_level_faces_the_same_stat_block(build):
    """The defensive half of the same requirement, read off the Entity rather than
    the policy — so a future policy change cannot make the test vacuous."""
    config = RunConfig(build=build, level=SHARED_LEVEL, n_days=1, enemy="baseline")
    _, roster = built(config)
    stats = roster.enemies[0].base_stats
    for key, value in enemy_stats.enemy_base_stats(SHARED_LEVEL).items():
        assert stats[key] == value


def test_enemy_path_still_distinguishes_every_run_that_must_not_be_pooled():
    """§3.4's comparability requirement, after the two paths became one (s52).

    s50 wrote this against the pair it had: ``build_default:baseline`` vs
    ``standardized:baseline``, which both said merely "baseline" before the prefix
    existed.  With the baked-in path deleted the prefix is a constant, so the
    requirement reduces to the surviving axis — the KIND — and that is what is
    asserted: three kinds, three paths, no two alike.

    The prefix is kept rather than dropped (see ``report.Provenance.build``) and that
    is asserted here too, because it is what distinguishes a post-5b artifact from the
    pre-s50 ones that rendered the bare word, and ``schema_version`` does not cover
    provenance string shapes.
    """
    config = RunConfig(build="silvertail", level=10, n_days=2, enemy="baseline",
                       enemy_options={"focus": "summon"})
    paths = {kind: run(config.replace(enemy=kind, enemy_options={})
                       ).provenance.coverage["enemy_path"]
             for kind in ("baseline", "scripted", "none")}
    assert paths == {"baseline": "standardized:baseline",
                     "scripted": "standardized:scripted",
                     "none": "standardized:none"}
    assert len(set(paths.values())) == 3


# ---------------------------------------------------------------------------
# §12 replacement 2: the L1-4 closed-form check, recomputed for the seam
# ---------------------------------------------------------------------------

CLOSED_FORM_DAYS = 5_000


def _closed_form_dpr(level: int, rounds_per_combat: int = 4,
                     combats: int = 4) -> float:
    """Expected DPR at a War Angel level with no accuracy feedback, by arithmetic.

    Independent of who authored the build data: it reads the character's own attack
    profile and the enemy's AC and does the probability by hand.  The policy at
    these levels is one action attack per round plus one opportunity attack per
    combat, so the day holds ``rounds + combats`` attacks over ``rounds`` rounds.

    Crit handling mirrors the design's phase order (#8: a crit doubles the die
    COUNT, the flat bonus stays single), which is why the crit term adds one extra
    expected dice roll rather than doubling the whole expression.
    """
    row = war_angel.LEVELS[level]
    attack_bonus = row["attack_bonus"]
    count, sides = row["damage_dice"]
    flat = row["damage_bonus"]
    needed = enemy_stats.baseline_ac(level) - attack_bonus
    # A natural 20 always hits and a natural 1 always misses, whatever the maths.
    hits = sum(1 for face in range(1, 21)
               if face == 20 or (face != 1 and face >= needed))
    p_hit, p_crit = hits / 20.0, 1 / 20.0
    expected_dice = count * (sides + 1) / 2.0
    per_attack = p_hit * (expected_dice + flat) + p_crit * expected_dice
    attacks = combats * rounds_per_combat + combats
    return per_attack * attacks / (combats * rounds_per_combat)


@pytest.mark.parametrize("level", [2, 3, 4])
def test_dpr_matches_the_closed_form_under_the_standardized_enemy(level):
    """§12 replacement 2 — the check that survives the retirement of the guide
    targets, because it tests the attack pipeline against ARITHMETIC rather than
    against a number the model's own author computed.

    Three things worth keeping from the measurement rather than re-deriving:

    * It needed no recomputation for the standardized enemy's AC after all — §12
      anticipated one, but the AC is unchanged (see the tests at the top).
    * Agreement at 20,000 days, seed = level: L2 **1.18σ**, L3 **0.79σ**, L4
      **1.83σ**.  The band below is 4σ at 5,000 days, which is ~1.2% — comfortable
      against a largest observed deviation of 0.28%, and the seed is fixed so there
      is no flake to absorb.
    * The closed form independently reproduces the retired guide targets to two
      decimals (7.41 vs 7.39, 7.41 vs 7.39, 6.81 vs 6.81).  That is a pleasant
      confirmation that the author's hand calculation was right; it is NOT the
      assertion, which is against the arithmetic.

    **L1 is deliberately excluded, and the reason was measured, not assumed.** Its
    rapier has the *vex* mastery, so a hit grants advantage on the next attack
    against the same target: expected DPR becomes a two-state Markov chain whose
    transition structure depends on the engine's status-expiry model rather than on
    arithmetic.  A closed form for it would be testing my model of the engine. The
    magnitude confirms it rather than hand-waving: the no-feedback formula misses
    L1 by **156σ** (6.656 vs 8.295 ± 0.011).  Levels 2-4 carry *sap*, which imposes
    disadvantage on the ENEMY's next attack and so feeds back into nothing the
    character's own damage depends on.
    """
    expected = _closed_form_dpr(level)
    value = run(RunConfig(build="war_angel", level=level, n_days=CLOSED_FORM_DAYS,
                          seed=level, enemy="baseline")).headline
    assert abs(value.value - expected) < 4 * value.stderr, (
        f"L{level}: closed form {expected:.4f}, simulated {value.value:.4f} "
        f"± {value.stderr:.4f} ({abs(value.value - expected) / value.stderr:.2f}σ)"
    )


def test_the_closed_form_is_only_valid_without_accuracy_feedback():
    """Guards the exclusion above.  If someone later extends the closed form to L1
    without modelling vex, this test says what they have to account for."""
    value = run(RunConfig(build="war_angel", level=1, n_days=CLOSED_FORM_DAYS,
                          seed=1, enemy="baseline")).headline
    sigmas = abs(value.value - _closed_form_dpr(1)) / value.stderr
    assert sigmas > 50, (
        "vex's hit-grants-advantage feedback is supposed to make the no-feedback "
        f"formula badly wrong at L1; it is only off by {sigmas:.1f}σ"
    )
    assert war_angel.LEVELS[1]["weapon_mastery"] == "vex"
    assert war_angel.LEVELS[2]["weapon_mastery"] == "sap"


def test_attacks_per_round_is_exactly_the_action_economy():
    """The arithmetic half of the same check, and the s49 decision to decline a
    distribution for this row — WHICH STEP 6 THEN OVERTURNED, exactly where this test
    said it would.

    §5.4's third ground for refusing a distribution is "near-deterministic", and s50
    asked whether the standardized enemy breaks that: if the enemy starts killing or
    controlling the character, the attack count stops being constant.  It did not,
    for two reasons, and one of them has since changed.  The character's HP is a
    threshold balance, so incoming damage still never costs it a turn — that half
    holds, and the two enemy kinds below are still exactly constant.  But §7's
    control was an OUTPUT FACTOR, so a controlled turn still ACTED; framework step 6
    (s51) makes a fully-suppressed turn skip the turn entirely, so under
    ``control=True`` the count both FALLS and VARIES for the first time.

    **UPDATED (s51), and the update is the point:** the two uncontrolled kinds keep
    the exact 1.25 and the exact zero, and the control case asserts the opposite of
    what it used to.  That the prediction in this docstring came true is why the
    distribution is now registered (§14).
    """
    for kind, options in [("none", {}), ("baseline", {})]:
        value = run(RunConfig(build="war_angel", level=3, n_days=50, seed=3,
                              enemy=kind, enemy_options=options)
                    ).values["attacks_per_round"]
        assert value.value == pytest.approx(1.25)      # 16 rounds + 4 AoOs
        assert value.stderr == 0.0

    controlled = run(RunConfig(build="war_angel", level=3, n_days=50, seed=3,
                               enemy="baseline", enemy_options={"control": True})
                     ).values["attacks_per_round"]
    assert controlled.value < 1.25        # whole turns are now skipped, not scaled
    assert controlled.stderr > 0.0        # ...and how many varies by day


# ---------------------------------------------------------------------------
# §12 replacement 1: exact golden values under the standardized enemy
# ---------------------------------------------------------------------------

GOLDEN_DAYS, GOLDEN_SEED = 400, 11

#: ``(build, level, enemy, sorted option items) -> exact headline DPR``.
#:
#: §12 replacement 1.  A STRICTER check than the ±10% band it replaces: it detects
#: any drift, not just large drift.  It asserts "nothing changed", never "this value
#: is correct" — so it stays inside [[validate-mechanism-not-build-value]].
#:
#: Regenerating these is a DELIBERATE act with a decision record, exactly as the
#: numbers in ``src/validation.py`` were.  An engine change that moves them has
#: moved the physics, and the commit that does it should say which physics.
# ===========================================================================
# RE-BASELINED (s54, framework step 7) — ONE combined record for TWO changes
# ===========================================================================
#
# Two of step 7's items move these rows, and they are recorded together rather than
# twice because they were applied together and a reader cannot separate them from the
# values alone (PROGRESS items iv and viii):
#
#   (iv) `RunConfig.party_size` DEFAULTS TO 4 (§3.5.2) — the enemy spreads its swings
#        across four friendlies instead of focus-firing the character. The user
#        overruled the draft's default of 1 and accepted the re-baseline now, because
#        a default of 1 would leave every defensive number still measured under
#        focus-fire, which is the defect the party exists to remove.
#  (viii) `make_starfire_scion` now sets `ac` — it never did, so the Scion fought at
#        AC 0, its own data having declared `char_ac` 16-18 all along.
#
# WHAT MOVED, AND THE BOUND HELD EXACTLY. §3.5.2 predicted 9 of 13 rows would move
# with 4 untouched, the 4 being `enemy="none"`, because a passive entity nothing
# targets is bit-identical. Measured: exactly that, with the four `none` rows equal to
# the last bit (and asserted directly in `test_eval_party_seam`).
#
#   row                                                old  ->  new        move
#   war_angel  1 none                           8.29234375      unchanged
#   war_angel  5 none                          16.45281250      unchanged
#   war_angel 12 none                          37.91640625      unchanged
#   war_angel 13 none                          35.45781250      unchanged
#   war_angel  4 baseline                       6.99390625 ->  6.94234375   -0.74%
#   war_angel 13 baseline                      34.76328125 -> 35.32109375   +1.60%
#   war_angel 13 scripted                      34.94093750 -> 35.42390625   +1.38%
#   war_angel 13 baseline control+mitigation   27.93671875 -> 33.53046875  +20.02%
#   war_angel 13 baseline legendary_cadence    34.43031250 -> 35.24687500   +2.37%
#   war_angel 16 baseline                      41.16687500 -> 38.03234375   -7.61%
#   silvertail 10 baseline                      6.33437500 ->  6.29640625   -0.60%
#   silvertail 10 baseline focus=summon         6.31828125 ->  6.38718750   +1.09%
#   starfire_scion 15 baseline                 27.42734375 -> 28.82609375   +5.10%
#
# THE STARFIRE ROW DECOMPOSES EXACTLY, which is what keeps the combined record
# honest: at `party_size=1` it reads **27.22875000**, the value the `ac` fix alone was
# predicted to produce, so the AC contributes -0.1986 and the party the remaining
# +1.5973.
#
# THREE DIRECTIONS WERE MEASURED RATHER THAN ARGUED, per the standing rule that a
# mechanical argument is not a measurement — and the third is a sign flip no
# prediction had:
#
#  * **war_angel 13 rises** (+1.60%) because the party absorbs ~3/4 of the swings, so
#    concentration checks fall 11.41 -> 3.79 per day and Bless survives. §3.5.2
#    predicted a concentration-dependent build's own DPR would go UP, and it does.
#  * **the control row rises most** (+20.02%) because control is aimed by the same
#    uniform weights, so ~3/4 of it lands on PASSIVE stand-ins, where a lost turn
#    costs nothing: control turns lost fall 0.1138 -> 0.0303 per round, a 73.4% drop.
#    This is a MEASURED argument for §3.5.4's threat class, which until now was
#    justified only qualitatively — see §14.
#  * **war_angel 16 FALLS** (-7.61%), the only sizeable move against the grain, and
#    the NEW reaction channel is what diagnosed it. L14+ has Flourish Parry and its
#    Counter, which converts an incoming hit into an outgoing attack, so a build whose
#    damage partly depends on BEING ATTACKED loses output when a party absorbs the
#    attacks. `reactions_per_round` goes 0.54766 -> 0.33578; subtracting the constant
#    0.25 opportunity attack leaves the parry component at 0.29766 -> 0.08578, a
#    **71.2% drop**, which is the ~3/4 reduction in incoming swings. L13 has no parry,
#    which is exactly why L13 rises and L16 falls. Worth noting on its own: the channel
#    that was dead at BOTH ENDS one PR ago is what made this legible in one run.
#
GOLDEN_DPR: dict[tuple, float] = {
    # ------------------------------------------------------------------
    # THE RETIRED PARITY PROOF'S COVERAGE, carried forward (s52).
    #
    # `test_framework_reproduces_validation_exactly` parametrized War Angel at
    # L1 / 4 / 5 / 12 / 13 / 16 for stated STRUCTURAL reasons — plain attacks, the
    # exact-match band's edge, where the daily-plan hooks appear, the last level with
    # an inert enemy, where the enemy strikes back, and the top of the validated
    # range.  §12 retires that test with `src/validation.py`; those six levels are
    # pinned here so its COVERAGE is not lost along with its role.
    #
    # L1 / L5 / L12 are pinned under `none`, and that is not an arbitrary choice:
    # `none` is BIT-IDENTICAL to what the retired harness printed at those levels
    # (§3.4's measurement — the baked-in enemy was passive there and its AC already
    # equalled the table's).  So for the three levels where it is possible, these
    # goldens literally ARE validation.py's numbers, carried forward as exact
    # constants rather than re-derived.
    ("war_angel", 1, "none", ()): 8.29234375,
    ("war_angel", 5, "none", ()): 16.4528125,
    ("war_angel", 12, "none", ()): 37.91640625,
    # L16 under `baseline` — the top of the range, with the enemy acting.  NOT
    # bit-identical to the retired harness (41.247656 there), because L16 is one of
    # the four War Angel levels whose baked-in enemy swung for a hand-written flat 32
    # instead of the table's 9d6+5.  That is the re-baseline 5b was for.
    ("war_angel", 16, "baseline", ()): 38.03234375,
    # ------------------------------------------------------------------
    ("war_angel", 4, "baseline", ()): 6.94234375,
    ("war_angel", 13, "baseline", ()): 35.32109375,
    ("war_angel", 13, "scripted", ()): 35.42390625,
    ("war_angel", 13, "none", ()): 35.4578125,
    # RE-BASELINED (s51), deliberately and with a decision record: framework step 6
    # applies the control cost at RUNTIME (evaluation_framework.md §7), so this is the
    # one golden in the table that control was ever going to move — and §7.4 said in
    # advance that it would.  34.87 → 27.93671875, a 19.9% drop where a naive reading
    # of the account implies ~33% (1 − 0.194 − 0.5·0.246).  Two reasons it is smaller,
    # and they compound: a suppressed turn BANKS its resources for a later turn (§7.1.2,
    # the whole argument for applying control at runtime rather than as a multiplier),
    # and overlapping controls no longer each claim the whole rest of the fight (§7.6 —
    # you cannot lose the same turn twice).  It moved TWICE within s51: 26.4784375 was
    # committed first, with the first of those two effects but not the second, before
    # the credit was made exact at the user's direction.  Every other row in this table
    # is UNCHANGED, which is the assertion that the default (control off) moved nothing.
    ("war_angel", 13, "baseline",
     (("control", True), ("mitigation", True))): 33.53046875,
    ("war_angel", 13, "baseline", (("legendary_cadence", True),)): 35.246875,
    ("silvertail", 10, "baseline", ()): 6.29640625,
    ("silvertail", 10, "baseline", (("focus", "summon"),)): 6.3871875,
    ("starfire_scion", 15, "baseline", ()): 28.82609375,
}


@pytest.mark.parametrize("key", list(GOLDEN_DPR))
def test_golden_dpr_under_the_standardized_enemy(key):
    build, level, kind, options = key
    value = run(RunConfig(build=build, level=level, n_days=GOLDEN_DAYS,
                          seed=GOLDEN_SEED, enemy=kind,
                          enemy_options=dict(options))).headline
    assert value.value == GOLDEN_DPR[key]


def test_incoming_pressure_orders_war_angels_dpr_the_right_way():
    """The MECHANISM behind the goldens, asserted as an ordering rather than as
    values — this is what a reader should take from the diff of the two enemy paths.

    War Angel concentrates on Bless, so every incoming hit is a chance to lose
    +1d4 on its own attacks.  More enemy attacks therefore mean strictly less of the
    character's own damage, and the four standardized configurations line up in
    exactly that order.  Measured, not assumed: 35.458 / 34.941 / 34.763 / 34.430.
    """
    def dpr(kind, **options):
        return run(RunConfig(build="war_angel", level=13, n_days=GOLDEN_DAYS,
                             seed=GOLDEN_SEED, enemy=kind,
                             enemy_options=options)).headline.value

    passive = dpr("none")
    attacks_only = dpr("scripted")
    attacks_and_saves = dpr("baseline")
    legendary = dpr("baseline", legendary_cadence=True)
    assert passive > attacks_only > attacks_and_saves > legendary


def test_concentration_checks_are_the_seams_real_detector_on_war_angel():
    """Which channel actually moves, and by how much — the correction to the
    handoff's expectation that the ATTACKS channel would show this.

    A concentration check happens when the character is hit, so this counts the
    enemy's landed swings. ``none`` must read exactly zero (nothing attacks), and
    the acting kinds must read many standard errors above it.
    """
    def checks(kind):
        value = run(RunConfig(build="war_angel", level=13, n_days=GOLDEN_DAYS,
                              seed=GOLDEN_SEED, enemy=kind)
                    ).values["concentration_checks_per_day"]
        return value.value, value.stderr

    passive, _ = checks("none")
    acting, stderr = checks("baseline")
    assert passive == 0.0
    assert acting > 10 * stderr


def test_the_attacks_channel_detects_the_seam_through_bless_not_through_ac():
    """The handoff's expected detector — right about the CHANNEL, wrong about the
    mechanism, and this test was wrong about both until it was run.

    The reasoning I wrote first was: a hit rate is a function of the enemy's AC
    alone, the AC does not change, therefore the rate must not move.  **The first
    clause is false**, and the test caught it at 7.7σ.  A hit rate is a function of
    the AC *and of the character's whole attack-roll modifier stack* — and War Angel
    concentrates on **Bless**, which adds +1d4 to its own attack rolls.  So incoming
    pressure reaches the character's accuracy by a real causal path: more enemy hits
    → more concentration checks → more broken Bless → fewer attacks made with the
    +1d4 → a lower hit rate.

    Measured at 2,000 days, seed 11, War Angel L13 (hit rate / concentration checks
    per day), and the two columns are perfectly inversely ordered:

        none                 0.95102   0.000
        build_default        0.94338   7.405
        scripted             0.93531  11.387
        baseline             0.93409  11.485
        baseline+legendary   0.92565  13.634

    So the attacks channel IS the sensitive detector the handoff expected — just not
    via the AC, which is identical on both paths.  The ORDERING is the assertion here,
    because it is the mechanism; the values are a record, not a target.

    **PARAMETRIZED OVER ``party_size`` (s54), because the party ATTENUATES the detector
    and the attenuation is the same mechanism one step on.** A party absorbing ~3/4 of
    the swings forces ~3/4 fewer concentration checks, so Bless survives and the hit
    rate moves far less. Measured at 2,000 days / seed 11:

        ======================  =============  =============
        arm                     party_size=1   party_size=4
        ======================  =============  =============
        none                    0.95102 / 0.0  0.95102 / 0.0
        scripted                0.93531 / 11.4 0.95002 / 3.65
        baseline                0.93409 / 11.5 0.94793 / 3.67
        baseline+legendary      0.92565 / 13.6 0.94570 / 5.17
        none vs +legendary      **20.7σ**      **4.8σ**
        ======================  =============  =============

    The ordering is strict in BOTH columns, so the detector is intact either way; what
    changes is its power, by a factor of about four. Testing both arms rather than
    relaxing the threshold is step 5's "test the BRANCH" applied to a declaration that
    only just gained a second value — and the σ claim is kept where it was measured
    instead of being quietly weakened to fit.

    Note the ``none`` row is IDENTICAL across the two columns to five decimal places,
    which is §3.5.2's bit-identity bound showing up in the attacks channel rather than
    in DPR: a passive entity nothing targets changes nothing at all.
    """
    def measure(kind, party_size, **options):
        report = run(RunConfig(build="war_angel", level=13, n_days=2_000, seed=11,
                               enemy=kind, enemy_options=options,
                               party_size=party_size))
        return (report.values["attack_roll_rate[characters|hit]"],
                report.values["concentration_checks_per_day"].value)

    gaps = {}
    for party_size, min_sigma in ((1, 10.0), (4, 3.0)):
        passive, passive_checks = measure("none", party_size)
        attacks_only, attacks_only_checks = measure("scripted", party_size)
        with_saves, _ = measure("baseline", party_size)
        legendary, legendary_checks = measure("baseline", party_size,
                                              legendary_cadence=True)

        # The pressure axis: strictly more incoming attacks, left to right.
        assert passive_checks == 0.0
        assert passive_checks < attacks_only_checks < legendary_checks
        # ...and the accuracy axis moves strictly the other way.
        assert (passive.value > attacks_only.value > with_saves.value
                > legendary.value), party_size
        # The move is large, which is what makes the channel a detector: a seam that
        # was NOT installed would leave these equal.
        pooled = math.hypot(passive.stderr, legendary.stderr)
        sigma = (passive.value - legendary.value) / pooled
        assert sigma > min_sigma, (party_size, sigma)
        gaps[party_size] = sigma

    # The attenuation itself, asserted rather than left in the table above: a party
    # weakens the detector by roughly 4x because it is what removes the pressure.
    assert gaps[1] > 3 * gaps[4]


def test_bless_cannot_touch_the_crit_rate_and_the_data_agrees():
    """The other half of the same mechanism, and the reason to believe it.

    Bless is a FLAT bonus, so it can change whether an attack lands but not whether
    the d20 shows a 20 — a crit rate is nat-20-gated and must therefore be
    insensitive to the pressure that moves the hit rate by 15σ.  Measured: 0.06291
    (``none``) vs 0.06437 (``baseline``), a 1.2σ difference against a per-run
    standard error of ~0.00084.

    This is what makes the Bless explanation an explanation rather than a story: it
    predicts WHICH cells move and which do not, and the breakdown's three cells
    behave as predicted.
    """
    def crit(kind):
        value = run(RunConfig(build="war_angel", level=13, n_days=2_000, seed=11,
                              enemy=kind)).values["attack_roll_rate[characters|crit]"]
        return value.value, value.stderr

    passive, passive_err = crit("none")
    with_saves, with_saves_err = crit("baseline")
    pooled = math.hypot(passive_err, with_saves_err)
    assert abs(with_saves - passive) < 4 * pooled, (
        f"the crit rate moved by {abs(with_saves - passive) / pooled:.1f}σ; a flat "
        "+1d4 cannot change P(natural 20), so something else changed"
    )


# ---------------------------------------------------------------------------
# Availability: the control channel's SEVEN answers, and mitigation's two
# ---------------------------------------------------------------------------

def test_control_channel_is_live_under_the_standardized_enemy():
    """The whole point of sequencing this step before step 6: control resilience was
    unmeasurable for every build in the corpus, for two different reasons, and one
    keyword now fixes it."""
    report = run(RunConfig(build="war_angel", level=13, n_days=60, enemy="baseline",
                           enemy_options={"control": True}))
    for name in ("control_turns_lost_per_round", "control_turns_reduced_per_round"):
        value = report.values[name]
        assert value.available
        assert value.value is not None and value.value > 0


def test_the_three_control_unavailability_reasons_stay_distinguishable():
    """The per-METRIC ritual's availability check: two runs blocked for different
    reasons get different reasons.

    THE COUNT HAS MOVED TWICE, for opposite reasons, and both moves are the check
    working rather than the check being retuned.  s50 took it from two to SEVEN,
    because the seam added a genuinely new situation — "the standardized enemy is
    installed and its channel is simply off" — and folding that into the pre-existing
    "constructed with control=False" would have lost the distinction, since only one
    of the two is the caller's to fix in one keyword.  s52 takes it to THREE: the four
    it loses are the baked-in path's ways of being unmeasurable, and no run can reach
    them, so each stated a reason nobody can be in.  That is worse than no branch —
    a reader who somehow saw one would go looking for a cause that does not exist.

    What survives is the property the check is for: the reasons are DISTINCT, and each
    one says how to fix it rather than only what is wrong.
    """
    reasons = {
        "std_baseline_off": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2, enemy="baseline")),
        "std_scripted": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2, enemy="scripted")),
        "std_none": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2, enemy="none")),
    }
    assert len(set(reasons.values())) == len(reasons)
    for reason in reasons.values():
        assert "enemy='baseline'" in reason
    assert "switched off" in reasons["std_baseline_off"]
    assert "ATTACK-ROLL half" in reasons["std_scripted"]
    assert "passive target" in reasons["std_none"]

    # And the reasons that are GONE are gone: a run cannot be told the build factory
    # chose its enemy model, because no build factory chooses one any more.
    for reason in reasons.values():
        assert "build factory" not in reason
        assert "build_default" not in reason


def test_mitigation_channel_is_live_under_the_standardized_enemy():
    """The second structurally-empty §8 channel.  Measured on Silvertail because it
    is the only build whose damage the multiplier can TOUCH: War Angel's output is
    0% typed, so its mitigation row is a true zero explained by the adjacent
    ``typed_damage_share``."""
    report = run(RunConfig(build="silvertail", level=10, n_days=60, enemy="baseline",
                           enemy_options={"mitigation": True}))
    for name in ("damage_mitigated_per_round", "mitigation_fraction"):
        value = report.values[name]
        assert value.available
        assert value.value is not None and value.value > 0

    unavailable = run(RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=10, n_days=2)
                      ).values["damage_mitigated_per_round"]
    assert not unavailable.available
    assert "enemy_options={'mitigation': True}" in (unavailable.note or "")


def test_war_angels_mitigation_zero_is_explained_by_the_adjacent_row():
    """A zero that IS a measurement, and the row that makes it readable.

    ``damage_mitigated_per_round`` reads 0 for War Angel even with a profile
    installed, because none of its damage carries a type for ``mult(t)`` to reduce.
    That is the job ``typed_damage_share``'s definition claims for itself — "worth
    knowing BEFORE reading any cell of the damage_share breakdown" — so this asserts
    the pair reads coherently rather than treating the zero as a defect.
    """
    report = run(RunConfig(build="war_angel", level=13, n_days=60, enemy="baseline",
                           enemy_options={"mitigation": True}))
    assert report.values["typed_damage_share"].value == 0.0
    assert report.values["damage_mitigated_per_round"].value == 0.0


# ---------------------------------------------------------------------------
# The s50 typed_damage_share bugfix (found by per-feature ritual step 6)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("build,level", [("war_angel", 13), ("starfire_scion", 15),
                                         ("silvertail", 10)])
def test_typed_damage_share_is_a_share_even_with_mitigation_installed(build, level):
    """Regression for the s50 defect, which was invisible for six sessions because
    nothing installed a ``damage_multiplier``: with ``outgoing_before`` over a
    POST-mitigation denominator the row printed **1.1054** on Silvertail L10.

    The diagnosis was arithmetic, which is why this test can be precise about what
    went wrong: where all of a build's damage is typed,
    ``typed_damage_share == 1 / (1 - mitigation_fraction)`` to the last bit if and
    only if the numerator is pre-mitigation.  The assertion below is the invariant
    that could not hold then and must hold now.
    """
    value = run(RunConfig(build=build, level=level, n_days=60, enemy="baseline",
                          enemy_options={"mitigation": True})
                ).values["typed_damage_share"]
    assert 0.0 <= value.value <= 1.0


def test_typed_damage_share_no_longer_tracks_the_mitigation_fraction():
    """The specific algebraic signature of the old bug, asserted as absent."""
    report = run(RunConfig(build="silvertail", level=10, n_days=60, enemy="baseline",
                           enemy_options={"mitigation": True}))
    share = report.values["typed_damage_share"].value
    fraction = report.values["mitigation_fraction"].value
    assert fraction > 0, "the profile must actually be mitigating for this to mean anything"
    assert not math.isclose(share, 1 / (1 - fraction), rel_tol=1e-9)


# ---------------------------------------------------------------------------
# The console names the enemy (step-6 ritual; the s49 renderer lesson)
# ---------------------------------------------------------------------------

def _enemy_header(config: RunConfig) -> str:
    lines = console.render(run(config.replace(n_days=3))).splitlines()
    return next(line for line in lines if line.startswith("  enemy"))


def test_console_header_names_the_resolved_enemy():
    """Found by rendering one real output, and it is the s49 defect pattern exactly:
    the enemy block is this step's whole deliverable, the JSON artifact carried it
    from the first commit, and the console — the renderer a person actually reads —
    mentioned the enemy ONCE, buried inside a comparability warning paragraph.

    §4 calls the provenance block "the source for the model-description /
    baseline-assumptions page".  A renderer that drops it makes that false.
    """
    line = _enemy_header(RunConfig(build="war_angel", level=13, n_days=3,
                                   enemy="baseline"))
    assert "standardized:baseline" in line
    assert "band 11-16" in line
    assert "all options at default" in line


def test_console_header_shows_only_the_options_in_force():
    """Non-default options only — printing all nine at their defaults would bury the
    one or two that matter, which is the over-long-note mistake s49 fixed."""
    line = _enemy_header(RunConfig(
        build="war_angel", level=13, n_days=3, enemy="baseline",
        enemy_options={"control": True, "mitigation": True, "band_override": "17+"}))
    assert "band_override='17+'" in line
    assert "control=True" in line
    assert "mitigation=True" in line
    assert "legendary_cadence" not in line        # left at its default
    assert "band 17+" in line                     # the override reached the band


@pytest.mark.parametrize("kind", ["baseline", "scripted", "none"])
def test_the_console_never_says_NOT_RESOLVED_any_more(kind):
    """s50 shipped a console branch that told a reader the enemy assumptions were not
    recorded, because on the ``build_default`` path they genuinely were not.  s52
    deleted the path, so the branch has no reachable case — asserted across all three
    kinds, because "no run can produce it" is the claim."""
    line = _enemy_header(RunConfig(build="war_angel", level=13, n_days=3, enemy=kind))
    assert f"standardized:{kind}" in line
    assert "NOT RESOLVED" not in line


# ---------------------------------------------------------------------------
# The registry still describes itself (the data dictionary is published)
# ---------------------------------------------------------------------------

def test_every_enemy_option_is_documented():
    """``ENEMY_OPTION_SCHEMA`` is half of the published data dictionary now that
    provenance reports it, so an undocumented knob is a gap in the output."""
    for name, spec in enemy_seam.ENEMY_OPTION_SCHEMA.items():
        assert spec.description.strip(), name
        assert spec.name == name


def test_the_metric_set_grew_only_by_the_declared_rows():
    """The s50 metric-set review kept all 26 declarations (nothing failed the
    survival rule) and step 5 added none — this test asserted that.

    **RENAMED AND UPDATED (s51):** step 6 added exactly ONE declaration, and the
    count is here so a second cannot arrive silently.

    * ``attacks_per_round_distribution`` — §14's trigger fired (see
      ``test_attacks_per_round_is_exactly_the_action_economy``).

    It briefly added three. The REALIZED control pair
    (``control_turns_lost_applied_per_round`` and its soft twin) was registered and
    then REMOVED in the same session, once §7.6's cap was made exact at the user's
    direction: the realized numbers are now equal to the credited ones by
    construction, so a second pair of rows would publish one quantity twice — the s46
    survival rule's "derivable and nobody reads it" cut. The realized half remains in
    the §13 channel, where it PROVES the equality.

    **UPDATED (s54):** step 7 added exactly ONE declaration, and it is the READ half
    of the reaction channel §3.5.1 found dead at both ends:

    * ``reactions_per_round`` — the §8 coverage map did not list the reaction economy
      at all, in either direction. ``record_reaction()``'s only caller was a unit test
      and no metric read ``reactions_used``, so War Angel's once-per-combat
      opportunity attack recorded 0 over 800 rounds.

    The same session ACTOR-KEYED the channel (``reactions_used: int`` →
    ``reactions: dict[int, int]``), which is a telemetry change rather than a
    declaration: a bare counter has no answer to the per-METRIC ritual's first
    question, since one combat holds the character's reaction, a commanded summon's
    and the enemy's.

    28 declarations: 17 scalars + 8 breakdowns + 3 distributions.
    """
    assert len(METRICS.scalars()) == 17
    assert len(METRICS.breakdowns) == 8
    assert len(METRICS.distributions()) == 3
    assert len(METRICS.names()) == 77
