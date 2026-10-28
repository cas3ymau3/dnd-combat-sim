"""
Mechanism tests for the ENEMY-CONSTRUCTION SEAM — evaluation_framework.md §3.4,
§13 step 5 (session 50).

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

| declaration                        | value                   | fixture                                      |
|------------------------------------|-------------------------|----------------------------------------------|
| `RunConfig.enemy`                  | build_default           | war_angel L13 (parity suite + here)          |
|                                    | baseline                | all three builds, L10/L13/L15                |
|                                    | scripted                | war_angel L13                                |
|                                    | none                    | war_angel L13                                |
| `enemy.resolve()["resolved"]`      | False                   | enemy="build_default"                        |
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
| `validate_options` build_default   | empty                   | enemy="build_default"                        |
|                                    | non-empty               | build_default + any option → ValueError      |
| `install()` branch                 | no-op                   | enemy="build_default" (policy IDENTITY)      |
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
|                                    | bd + scripted           | war_angel L13 build_default                  |
|                                    | bd + baseline           | silvertail L10 build_default                 |
|                                    | bd + passive            | war_angel L3 build_default                   |
| `_requires_mitigation_profile`     | available               | any kind + mitigation=True                   |
|                                    | unavailable             | enemy="build_default"                        |
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
from src.evaluation.runner import run, simulate
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


# ---------------------------------------------------------------------------
# The s50 migration finding — pinned as a test, not left as a comment
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level", sorted(war_angel.LEVELS))
def test_baked_in_war_angel_enemy_ac_already_matches_the_definitive_table(level):
    """§3.4 item 1 cites ``war_angel.LEVELS[13]["enemy_ac"]`` as the coupling to
    remove.  The AC itself is NOT the coupling: it was copied out of the same CSV
    the standardized enemy reads, so it already agrees at every level.

    This is the fact that falsifies the "the hit rate will move a lot" expectation,
    and it is a test rather than a comment because the next session would otherwise
    re-derive it — or, worse, trust the expectation.
    """
    assert war_angel.LEVELS[level]["enemy_ac"] == enemy_stats.baseline_ac(level)


@pytest.mark.parametrize("level", sorted(starfire_scion.LEVELS))
def test_baked_in_starfire_enemy_defense_already_matches_the_definitive_table(level):
    """Same for the Starfire Scion, which carries one save as well as the AC."""
    row = starfire_scion.LEVELS[level]
    assert row["enemy_ac"] == enemy_stats.baseline_ac(level)
    assert row["enemy_dex_save"] == enemy_stats.baseline_save(level, "dex_save")


_ALL_BUILD_LEVELS = (
    [("war_angel", lvl) for lvl in sorted(war_angel.LEVELS)]
    + [("starfire_scion", lvl) for lvl in sorted(starfire_scion.LEVELS)]
    + [("silvertail", lvl) for lvl in sorted(silvertail.LEVELS)]
)


@pytest.mark.parametrize("build,level", _ALL_BUILD_LEVELS)
def test_standardized_overlay_never_changes_the_enemy_ac(build, level):
    """The overlay writes the table's whole stat block over the factory's dummy —
    and the AC it writes is the AC that was already there, for every build at every
    level.  So no character's own hit rate can move SYSTEMATICALLY under the seam.

    Asserted across the full cross-product rather than at a sample, because this is
    the premise the two attack-rate tests below rest on.
    """
    config = RunConfig(build=build, level=level, n_days=1, enemy="baseline")
    adapter = config.validate()
    _, roster = adapter.build(config.replace(enemy="build_default"), SeededRNG(0))
    before = roster.enemies[0].base_stats.get("ac")

    _, roster_after = adapter.build(config, SeededRNG(0))
    assert roster_after.enemies[0].base_stats["ac"] == before


def test_overlay_adds_the_six_saves_war_angels_dummy_never_carried():
    """War Angel's ``make_training_dummy`` sets ``ac`` and nothing else, so a save
    forced on its enemy read ``Entity.stat``'s 0 default.  The overlay completes the
    block — this is §3.4 item 1's REAL content, as opposed to the AC."""
    config = RunConfig(build="war_angel", level=13, n_days=1)
    adapter = config.validate()

    _, before = adapter.build(config, SeededRNG(0))
    assert "dex_save" not in before.enemies[0].base_stats

    _, after = adapter.build(config.replace(enemy="baseline"), SeededRNG(0))
    stats = after.enemies[0].base_stats
    for save in ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save"):
        assert stats[save] == enemy_stats.baseline_save(13, save)
    assert stats["enemy_save_dc"] == enemy_stats.baseline_save_dc(13)
    assert stats["attack_bonus"] == enemy_stats.baseline_attack_bonus(13)


def test_overlay_leaves_an_already_complete_stat_block_alone():
    """Silvertail's dummy is already built from ``enemy_base_stats``, so the overlay
    is a no-op on it.  The uncovered VALUE of the saves-already-present branch."""
    config = RunConfig(build="silvertail", level=10, n_days=1)
    adapter = config.validate()
    _, before = adapter.build(config, SeededRNG(0))
    baseline_block = dict(before.enemies[0].base_stats)

    _, after = adapter.build(config.replace(enemy="baseline"), SeededRNG(0))
    for key, value in baseline_block.items():
        assert after.enemies[0].base_stats[key] == value


# ---------------------------------------------------------------------------
# RunConfig: the fields went live (§3.1)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("kind", ["build_default", "baseline", "scripted", "none"])
def test_every_enemy_kind_is_now_accepted(kind):
    """Steps 1-4 raised ``NotImplementedError`` for three of these four."""
    RunConfig(build="war_angel", level=13, n_days=1, enemy=kind).validate()


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


def test_build_default_accepts_no_enemy_options():
    """It cannot honour one: the factory builds the enemy off the character's row."""
    config = RunConfig(build="war_angel", level=13, n_days=1,
                       enemy_options={"control": True})
    with pytest.raises(ValueError, match="can honour no enemy option"):
        config.validate()


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
    otherwise two runs against different enemies would collide in the §10 cache."""
    base = RunConfig(build="war_angel", level=13, n_days=1)
    assert base.config_hash() != base.replace(enemy="baseline").config_hash()
    assert (base.replace(enemy="baseline").config_hash()
            != base.replace(enemy="baseline",
                            enemy_options={"control": True}).config_hash())


# ---------------------------------------------------------------------------
# enemy.resolve() — the §4 provenance block
# ---------------------------------------------------------------------------

def test_build_default_reports_itself_as_not_resolved():
    """The honest gap.  A half-filled block would imply the assumptions were
    recorded when they were not."""
    report = run(RunConfig(build="war_angel", level=13, n_days=2))
    block = report.provenance.resolved["enemy"]
    assert block["standardized"] is False
    assert block["resolved"] is False
    assert block["policy"] == "scripted"
    assert "NOT RESOLVED" in block["note"]
    assert report.provenance.coverage["enemy_path"] == "build_default:scripted"
    assert report.provenance.coverage["enemy_side"].startswith("NOT RESOLVED")


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
                  enemy_options={"band_override": "17+"}), {})
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
        RunConfig(build="war_angel", level=13, n_days=1, enemy=kind), {})
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
                  enemy_options={"mitigation": True}), {})
    assert block["damage_multiplier"] == enemy_stats.band_damage_multipliers(
        10, band=enemy_stats.band_for_level(10))


# ---------------------------------------------------------------------------
# enemy.install() — the policy is actually replaced
# ---------------------------------------------------------------------------

def test_build_default_leaves_the_factory_policy_untouched():
    """Not merely "an equivalent policy": the SAME OBJECT.  Any replacement at all
    on this path would put the §12 bit-identical parity proof at risk."""
    config = RunConfig(build="war_angel", level=13, n_days=1)
    adapter = config.validate()
    runner, roster = adapter.build(config, SeededRNG(0))
    installed = runner.policies[roster.enemies[0].id]
    assert isinstance(installed, ScriptedEnemyPolicy)
    assert enemy_seam.install(runner, roster, config)["resolved"] is False
    assert runner.policies[roster.enemies[0].id] is installed


def test_baseline_kind_installs_the_table_driven_policy():
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline")
    adapter = config.validate()
    runner, roster = adapter.build(config, SeededRNG(0))
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
    adapter = config.validate()
    runner, roster = adapter.build(config, SeededRNG(0))
    policy = runner.policies[roster.enemies[0].id]
    assert isinstance(policy, ScriptedEnemyPolicy)
    params = policy.describe_parameters()
    assert params["forces_saves"] is False
    assert params["control_channel"] is False
    assert params["n_attacks"] == enemy_stats.baseline_n_attacks(13)
    assert params["targeting"] == "single_target"
    # Its damage comes off the Entity (no dice on the Choice), so the overlay must
    # have put the table's dice there.
    n, sides, bonus = enemy_stats.baseline_attack_dice(13)
    assert roster.enemies[0].base_stats["damage_dice"] == (n, sides)
    assert roster.enemies[0].base_stats["damage_bonus"] == bonus


def test_none_kind_removes_the_policy_entirely():
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="none")
    adapter = config.validate()
    runner, roster = adapter.build(config, SeededRNG(0))
    assert roster.enemies[0].id not in runner.policies
    # ...but it is still a complete stat block, not a bare AC.
    assert roster.enemies[0].base_stats["enemy_save_dc"] == \
        enemy_stats.baseline_save_dc(13)


def test_focus_declares_which_entity_the_enemy_fights():
    """DECLARED, not derived from the build — the per-feature step-4 test.  The two
    facts vary independently: Silvertail's own factory switches master-vs-beast off
    its ``zone_effect`` axis, so no derivation from the build could be right."""
    config = RunConfig(build="silvertail", level=10, n_days=1, enemy="baseline")
    adapter = config.validate()

    runner, roster = adapter.build(config, SeededRNG(0))
    assert (runner.policies[roster.enemies[0].id].describe_parameters()["focus"]
            == roster.character.name)

    runner, roster = adapter.build(
        config.replace(enemy_options={"focus": "summon"}), SeededRNG(0))
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
    runner, roster = config.validate().build(config.replace(enemy="build_default"),
                                             SeededRNG(0))
    with pytest.raises(ValueError, match="no enemies"):
        enemy_seam.install(runner, Roster(characters=[roster.character]), config)


def test_install_refuses_a_roster_with_two_enemies():
    """BUILT fixture — no shipped build fields two enemies.  The refusal names the
    multi-enemy / spatial deferral rather than silently standardizing one of them."""
    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline")
    runner, roster = config.validate().build(config.replace(enemy="build_default"),
                                             SeededRNG(0))
    two = Roster(characters=[roster.character],
                 enemies=[roster.enemies[0], Entity(name="second", hp=10 ** 9)])
    with pytest.raises(NotImplementedError, match="installs ONE standardized enemy"):
        enemy_seam.install(runner, two, config)


def test_scripted_policy_reports_weighted_roster_targeting():
    """BUILT fixture, and the roll call says why: this VALUE is unreachable through
    ``RunConfig`` today.  The standardized ``scripted`` kind never passes a roster,
    and ``build_default`` never calls ``describe_parameters()`` at all — so the
    branch would ship untested.  Trigger for a production fixture: a standardized
    multi-entity kind, blocked on §3.3's multi-character party.
    """
    char, ally = Entity(name="char", hp=40), Entity(name="ally", hp=40)
    params = ScriptedEnemyPolicy(target=char, n_attacks=2,
                                 roster=[(char, 2), (ally, 1)]).describe_parameters()
    assert params["targeting"] == "weighted_roster"
    assert params["char_target_prob"] is None
    assert params["roster_weights"] == {"char": 2, "ally": 1}


def test_legendary_cadence_is_inert_in_the_low_bands():
    """The toggle's TRUE value has two outcomes and only one is interesting: the
    mean-field count rounds to 0 below band 11-16, so ``True`` at L4 is a no-op."""
    low = enemy_seam.resolve(RunConfig(build="war_angel", level=4, n_days=1,
                                       enemy="baseline",
                                       enemy_options={"legendary_cadence": True}), {})
    assert enemy_stats.band_legendary_cadence(4) == 0
    assert low["options"]["legendary_cadence"] is True       # declared...

    config = RunConfig(build="war_angel", level=13, n_days=1, enemy="baseline",
                       enemy_options={"legendary_cadence": True})
    runner, roster = config.validate().build(config, SeededRNG(0))
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
    runner, roster = adapter.build(config.replace(enemy="build_default"), rng)
    after_factory = rng.calls

    enemy_seam.resolve(config, adapter.describe(config))
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
    for build in SHARED_LEVEL_BUILDS:
        config = RunConfig(build=build, level=SHARED_LEVEL, n_days=1,
                           enemy="baseline", enemy_options={"control": True})
        adapter = config.validate()
        runner, roster = adapter.build(config, SeededRNG(0))
        blocks.append(enemy_seam.resolve(config, adapter.describe(config)))
        params = runner.policies[roster.enemies[0].id].describe_parameters()
        # 'focus'/'fallback' name the ROSTER, which differs by construction — the
        # enemy's own parameters are what must agree.
        policies.append({k: v for k, v in params.items()
                         if k not in ("focus", "fallback")})

    first, *rest = blocks
    for other in rest:
        assert other == first
    first_policy, *other_policies = policies
    for other in other_policies:
        assert other == first_policy


@pytest.mark.parametrize("build", SHARED_LEVEL_BUILDS)
def test_every_build_at_one_level_faces_the_same_stat_block(build):
    """The defensive half of the same requirement, read off the Entity rather than
    the policy — so a future policy change cannot make the test vacuous."""
    config = RunConfig(build=build, level=SHARED_LEVEL, n_days=1, enemy="baseline")
    _, roster = config.validate().build(config, SeededRNG(0))
    stats = roster.enemies[0].base_stats
    for key, value in enemy_stats.enemy_base_stats(SHARED_LEVEL).items():
        assert stats[key] == value


def test_the_two_enemy_paths_are_never_silently_comparable():
    """§3.4's standing requirement while both paths exist.  ``enemy_path``
    distinguishes "standardized baseline" from "the factory happened to pick
    BaselineEnemyPolicy" — both would say "baseline" if the path named only the
    model, and pooling them is exactly what must not happen."""
    config = RunConfig(build="silvertail", level=10, n_days=2)
    default_path = run(config).provenance.coverage["enemy_path"]
    standardized = run(config.replace(enemy="baseline")).provenance.coverage[
        "enemy_path"]
    assert default_path == "build_default:baseline"
    assert standardized == "standardized:baseline"
    assert default_path != standardized


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
    """The arithmetic half of the same check, and a re-read of the s49 decision to
    decline a distribution for this row.

    §5.4's third ground for refusing a distribution is "near-deterministic", and the
    handoff asked whether the standardized enemy breaks that: if the enemy starts
    killing or controlling the character, the attack count stops being constant.
    **It does not, for two reasons that are both worth recording.**  The character's
    HP is a threshold balance, so incoming damage never costs it a turn; and §7's
    control is an OUTPUT FACTOR in v1 rather than a status object, so a controlled
    turn still acts.  So the stderr stays exactly 0 and the s49 decision stands —
    its trigger is step 6's runtime control, not this step.
    """
    for kind, options in [("none", {}), ("baseline", {}),
                          ("baseline", {"control": True})]:
        value = run(RunConfig(build="war_angel", level=3, n_days=50, seed=3,
                              enemy=kind, enemy_options=options)
                    ).values["attacks_per_round"]
        assert value.value == pytest.approx(1.25)      # 16 rounds + 4 AoOs
        assert value.stderr == 0.0


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
GOLDEN_DPR: dict[tuple, float] = {
    ("war_angel", 4, "baseline", ()): 6.99390625,
    ("war_angel", 13, "baseline", ()): 34.76328125,
    ("war_angel", 13, "scripted", ()): 34.9409375,
    ("war_angel", 13, "none", ()): 35.4578125,
    ("war_angel", 13, "baseline",
     (("control", True), ("mitigation", True))): 34.87,
    ("war_angel", 13, "baseline", (("legendary_cadence", True),)): 34.4303125,
    ("silvertail", 10, "baseline", ()): 6.334375,
    ("silvertail", 10, "baseline", (("focus", "summon"),)): 6.31828125,
    ("starfire_scion", 15, "baseline", ()): 27.42734375,
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

    So the attacks channel IS the sensitive detector the handoff expected (none vs
    baseline is ~15σ at a stderr of ~0.0008) — just not via the AC, which is
    identical on both paths.  The ORDERING is the assertion here, because it is the
    mechanism; the values are a record, not a target.
    """
    def measure(kind, **options):
        report = run(RunConfig(build="war_angel", level=13, n_days=2_000, seed=11,
                               enemy=kind, enemy_options=options))
        return (report.values["attack_roll_rate[characters|hit]"],
                report.values["concentration_checks_per_day"].value)

    passive, passive_checks = measure("none")
    attacks_only, attacks_only_checks = measure("scripted")
    with_saves, with_saves_checks = measure("baseline")
    legendary, legendary_checks = measure("baseline", legendary_cadence=True)

    # The pressure axis: strictly more incoming attacks, left to right.
    assert passive_checks == 0.0
    assert passive_checks < attacks_only_checks < legendary_checks
    # ...and the accuracy axis moves strictly the other way.
    assert (passive.value > attacks_only.value > with_saves.value
            > legendary.value)
    # The move is large, which is what makes the channel a detector: a seam that
    # was NOT installed would leave these equal.
    pooled = math.hypot(passive.stderr, legendary.stderr)
    assert (passive.value - legendary.value) > 10 * pooled


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


def test_the_four_control_unavailability_reasons_stay_distinguishable():
    """The per-METRIC ritual's availability check: two builds blocked for different
    reasons get different reasons.  The seam ADDS a reason — "the standardized enemy
    is installed and its channel is off" — and folding that into the pre-existing
    "constructed with control=False" would lose the distinction, because only one of
    the two is the caller's to fix in one keyword.
    """
    reasons = {
        "std_baseline_off": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2, enemy="baseline")),
        "std_scripted": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2, enemy="scripted")),
        "std_none": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2, enemy="none")),
        "bd_scripted": _control_reason(
            RunConfig(build="war_angel", level=13, n_days=2)),
        "bd_baseline": _control_reason(
            RunConfig(build="silvertail", level=10, n_days=2)),
        "bd_passive": _control_reason(
            RunConfig(build="war_angel", level=3, n_days=2)),
    }
    assert len(set(reasons.values())) == len(reasons)
    # Every reason tells the reader how to fix it, not only what is wrong.
    for reason in reasons.values():
        assert "enemy='baseline'" in reason
    assert "switched off" in reasons["std_baseline_off"]
    assert "ATTACK-ROLL half" in reasons["std_scripted"]
    assert "passive target" in reasons["std_none"]
    assert "build factory installed ScriptedEnemyPolicy" in reasons["bd_scripted"]
    assert "without exposing the toggle" in reasons["bd_baseline"]
    assert "never acts at this level" in reasons["bd_passive"]


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

    unavailable = run(RunConfig(build="silvertail", level=10, n_days=2)
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


def test_console_header_says_so_when_the_enemy_is_not_resolved():
    line = _enemy_header(RunConfig(build="war_angel", level=13, n_days=3))
    assert "build_default:scripted" in line
    assert "NOT RESOLVED" in line


# ---------------------------------------------------------------------------
# The registry still describes itself (the data dictionary is published)
# ---------------------------------------------------------------------------

def test_every_enemy_option_is_documented():
    """``ENEMY_OPTION_SCHEMA`` is half of the published data dictionary now that
    provenance reports it, so an undocumented knob is a gap in the output."""
    for name, spec in enemy_seam.ENEMY_OPTION_SCHEMA.items():
        assert spec.description.strip(), name
        assert spec.name == name


def test_the_metric_set_is_unchanged_by_this_step():
    """The s50 metric-set review kept all 26 declarations (nothing failed the
    survival rule), so this step must not have quietly added or dropped one."""
    assert len(METRICS.scalars()) == 16
    assert len(METRICS.breakdowns) == 8
    assert len(METRICS.distributions()) == 2
    assert len(METRICS.names()) == 76
