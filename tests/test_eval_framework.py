"""
test_eval_framework.py — step 1 of the evaluation framework (design/evaluation_framework.md
§13.1): RunConfig + BuildAdapter + Roster + the build registry.

Validation framing (§12, memory ``validate-mechanism-not-build-value``): these
tests assert the MECHANISM — that roles are tagged right, that a summon never
leaks into the headline column, that sparse level sets are respected, that a
config cannot claim an assumption the run did not apply, and that the framework
reproduces ``src/validation.py``'s numbers EXACTLY.  No test asserts that any
build's DPR value is "correct".

The exact-reproduction test is the correctness proof for the whole layer:
``validation.py`` stays untouched as the regression check until it passes.
"""

from __future__ import annotations

import logging

import pytest

from src import validation
from src.builds import silvertail, starfire_scion, war_angel
from src.evaluation import (
    RunConfig,
    Roster,
    available_builds,
    get_adapter,
    run,
    simulate,
)
from src.evaluation.adapters import BuildAdapter, OptionSpec

# Engine per-event logging dominates Monte Carlo runtime and says nothing here.
logging.disable(logging.CRITICAL)

#: Small but not trivial — enough days for the dice streams to diverge if the
#: framework did anything the validation harness does not.
PARITY_DAYS = 60


# ---------------------------------------------------------------------------
# The correctness proof (§12): exact reproduction of validation.py
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("level", [1, 4, 5, 12, 13, 16])
def test_framework_reproduces_validation_exactly(level):
    """Same seed, same day count → bit-identical mean DPR and standard error.

    Levels chosen to cover the structural regimes: L1 (plain attacks), L4 (the
    exact-match band's edge), L5 (daily-plan hooks appear), L12 (last level with
    an inert enemy), L13 (the enemy starts striking back — the case where the
    headline column and "damage taken by the dummy" could diverge), L16 (the top
    of the validated range).
    """
    reference = validation.run_level(level, n_days=PARITY_DAYS, seed=11)
    headline = run(RunConfig(build="war_angel", level=level,
                             n_days=PARITY_DAYS, seed=11)).headline

    # Step 2 routed this through the metric registry (the ``dpr`` MetricDef and
    # the fixed-denominator estimator).  The assertion stays EXACT equality: the
    # estimator deliberately mirrors validation.run_level's operation order, so an
    # algebraically-equivalent rearrangement that drifts by one ULP is a
    # regression, not a rounding detail.
    assert headline.metric == "dpr"
    assert headline.value == reference.mean_dpr
    assert headline.stderr == reference.stderr


def test_headline_column_is_the_characters_own_output():
    """The framework's headline reads ``damage_by_source(character)``, while
    ``validation.py`` reads ``damage_received_by(dummy)``.  For a single-character
    build with an inert-to-the-dummy enemy these must agree — if they ever stop
    agreeing, the parity proof above is measuring the wrong thing."""
    output = simulate(RunConfig(build="war_angel", level=13,
                                n_days=PARITY_DAYS, seed=5))
    dummy = output.roster.enemies[0]
    assert output.headline_damage == output.damage_taken[dummy.id]


# ---------------------------------------------------------------------------
# Roster: roles, not tuple positions (§3.3)
# ---------------------------------------------------------------------------

def test_war_angel_roster_roles():
    output = simulate(RunConfig(build="war_angel", level=1, n_days=2, seed=0))
    roster = output.roster
    assert [e.name for e in roster.characters] == [roster.character.name]
    assert roster.summons == [] and roster.allies == []
    assert len(roster.enemies) == 1
    assert roster.role_of(roster.character.id) == "characters"
    assert roster.role_of(roster.enemies[0].id) == "enemies"


def test_silvertail_roster_tags_the_beast_as_a_summon():
    """The build whose factory returns FOUR values with the summon in the MIDDLE —
    the exact shape that breaks any position-based reader."""
    output = simulate(RunConfig(build="silvertail", level=8, n_days=2, seed=0))
    roster = output.roster
    assert len(roster.characters) == 1
    assert len(roster.summons) == 1
    assert roster.role_of(roster.summons[0].id) == "summons"
    assert roster.summons[0].id not in roster.headline_source_ids
    assert roster.summons[0].id in roster.party_source_ids


def test_starfire_party_member_is_recovered_by_difference_not_position():
    """``with_party`` appends a party member the factory never returns; the adapter
    must find it without knowing where it sits in the entity list."""
    with_party = simulate(RunConfig(build="starfire_scion", level=15, n_days=2,
                                    seed=0, build_options={"with_party": True}))
    without = simulate(RunConfig(build="starfire_scion", level=15, n_days=2,
                                 seed=0, build_options={"with_party": False}))
    assert len(with_party.roster.allies) == 1
    assert with_party.roster.role_of(with_party.roster.allies[0].id) == "allies"
    assert without.roster.allies == []


def test_summon_damage_never_merges_into_the_headline():
    """§3.3's structural, permanent rule: the headline is the character's own
    column; the roster total sits BESIDE it under a different name.

    Asserted as a MECHANISM — that the two columns are the character's alone and
    the character's plus the beast's — not that either number is right."""
    output = simulate(RunConfig(build="silvertail", level=8, n_days=8, seed=2))
    char = output.roster.character
    beast = output.roster.summons[0]

    assert output.headline_damage == output.damage_dealt[char.id]
    assert output.party_damage == [
        c + b for c, b in zip(output.damage_dealt[char.id], output.damage_dealt[beast.id])
    ]
    # The beast contributes to the party column only (its own distinct column).
    assert output.damage_dealt[beast.id] != output.headline_damage


def test_roster_rejects_overlapping_roles_and_empty_characters():
    char = war_angel.make_war_angel(1)
    dummy = war_angel.make_training_dummy(1)
    with pytest.raises(ValueError, match="roles are exclusive"):
        Roster(characters=[char], summons=[char], enemies=[dummy])
    with pytest.raises(ValueError, match="at least one character"):
        Roster(characters=[], enemies=[dummy])


def test_roster_character_accessor_refuses_to_hide_plurality():
    char_a = war_angel.make_war_angel(1)
    char_b = war_angel.make_war_angel(2)
    roster = Roster(characters=[char_a, char_b],
                    enemies=[war_angel.make_training_dummy(1)])
    with pytest.raises(ValueError, match="multi-character"):
        _ = roster.character
    assert len(roster.headline_source_ids) == 2


# ---------------------------------------------------------------------------
# Registry + sparse level sets (§2 axis 4)
# ---------------------------------------------------------------------------

def test_registry_holds_the_three_builds_and_they_satisfy_the_protocol():
    assert available_builds() == ["silvertail", "starfire_scion", "war_angel"]
    for name in available_builds():
        assert isinstance(get_adapter(name), BuildAdapter)


def test_unknown_build_names_the_known_ones():
    with pytest.raises(KeyError, match="silvertail"):
        get_adapter("no_such_build")


@pytest.mark.parametrize("build,module", [
    ("war_angel", war_angel),
    ("starfire_scion", starfire_scion),
    ("silvertail", silvertail),
])
def test_available_levels_match_the_builds_own_sparse_level_set(build, module):
    assert get_adapter(build).available_levels() == sorted(module.LEVELS)


def test_sparse_levels_are_enforced_and_the_error_lists_them():
    """Silvertail implements 4, 8, 10 — level 6 is not "between", it does not exist."""
    with pytest.raises(ValueError, match=r"no level 6.*\[4, 8, 10\]"):
        RunConfig(build="silvertail", level=6, n_days=1).validate()


def test_a_level_valid_for_one_build_is_not_valid_for_another():
    RunConfig(build="war_angel", level=7, n_days=1).validate()      # contiguous 1-16
    with pytest.raises(ValueError, match="no level 7"):
        RunConfig(build="starfire_scion", level=7, n_days=1).validate()


# ---------------------------------------------------------------------------
# RunConfig validation: a config must not claim an unapplied assumption
# ---------------------------------------------------------------------------

def test_unknown_scenario_axis_is_rejected_with_the_known_axes():
    with pytest.raises(ValueError, match="no scenario axis"):
        RunConfig(build="silvertail", level=8, n_days=1,
                  build_options={"zone_efect": "spirit_guardians"}).validate()


def test_out_of_vocabulary_axis_value_is_rejected():
    with pytest.raises(ValueError, match="fourth_level_spell"):
        RunConfig(build="starfire_scion", level=15, n_days=1,
                  build_options={"fourth_level_spell": "fireball"}).validate()


def test_open_axis_accepts_any_value():
    """``precast_prob`` is a probability, not a closed vocabulary."""
    RunConfig(build="starfire_scion", level=15, n_days=1,
              build_options={"precast_mode": "rng", "precast_prob": 0.25}).validate()


def test_war_angel_has_no_scenario_axes():
    assert get_adapter("war_angel").option_schema() == {}
    with pytest.raises(ValueError, match="no scenario axis"):
        RunConfig(build="war_angel", level=1, n_days=1,
                  build_options={"with_party": True}).validate()


@pytest.mark.parametrize("kwargs,match", [
    ({"enemy_options": {"control": True}}, "enemy_options"),
    ({"enemy": "baseline"}, "enemy='baseline'"),
    ({"mode": "finite_hp"}, "finite_hp"),
])
def test_designed_but_unwired_fields_raise_rather_than_being_ignored(kwargs, match):
    """Step 1 cannot honour these (the factories own their enemy policy and combat
    loop).  Silently ignoring them would make the §4 provenance block document
    assumptions the run never applied — so they are hard errors, not warnings."""
    with pytest.raises(NotImplementedError, match=match):
        RunConfig(build="war_angel", level=1, n_days=1, **kwargs)


@pytest.mark.parametrize("kwargs", [
    {"combats_per_day": 3},
    {"rounds_per_combat": 0},
    {"n_days": 0},
])
def test_day_shape_is_validated(kwargs):
    with pytest.raises(ValueError):
        RunConfig(build="war_angel", level=1, **{"n_days": 1, **kwargs})


def test_rounds_per_day_is_the_declared_denominator():
    config = RunConfig(build="war_angel", level=1, n_days=1, rounds_per_combat=4)
    assert config.rounds_per_day == 16


# ---------------------------------------------------------------------------
# Config identity: hashing, canonical form, paired seeding groundwork (§6.1, §10)
# ---------------------------------------------------------------------------

def test_config_hash_ignores_dict_ordering_but_not_content():
    a = RunConfig(build="silvertail", level=8, n_days=10,
                  build_options={"recast": True, "mortal_beast": True})
    b = RunConfig(build="silvertail", level=8, n_days=10,
                  build_options={"mortal_beast": True, "recast": True})
    c = b.replace(build_options={"mortal_beast": True, "recast": False})

    assert a.config_hash() == b.config_hash()
    assert hash(a) == hash(b)
    assert a.config_hash() != c.config_hash()
    assert {a, b, c} == {a, c}          # usable as a cache key


def test_replace_keeps_the_shared_seed_for_paired_comparisons():
    base = RunConfig(build="starfire_scion", level=15, n_days=10, seed=99)
    variant = base.replace(build_options={"with_party": True})
    assert variant.seed == base.seed == 99
    assert variant.config_hash() != base.config_hash()


def test_day_tier_labels_the_standard_counts():
    assert RunConfig(build="war_angel", level=1, n_days=50_000).day_tier == "standard"
    assert RunConfig(build="war_angel", level=1, n_days=2_000).day_tier == "quick"
    assert RunConfig(build="war_angel", level=1, n_days=1_234).day_tier == "custom"


# ---------------------------------------------------------------------------
# describe(): RESOLVED values, not the word "default" (§4)
# ---------------------------------------------------------------------------

def test_describe_fills_unset_axes_with_the_value_actually_used():
    config = RunConfig(build="silvertail", level=8, n_days=1,
                       build_options={"recast": True})
    described = get_adapter("silvertail").describe(config)
    assert described["options"] == {
        "beast_effect": None, "mortal_beast": False,
        "recast": True, "zone_effect": None,
    }


def test_describe_resolves_none_to_the_data_rows_actual_value():
    """§4's load-bearing case: ``primal_strike_unarmed=None`` is not "default", it
    is whatever the level row's ``raw_unarmed`` flag says — and the source of that
    value is named alongside it."""
    config = RunConfig(build="starfire_scion", level=15, n_days=1)
    described = get_adapter("starfire_scion").describe(config)
    row_value = starfire_scion.LEVELS[15]["primal_strike"]["raw_unarmed"]

    assert described["options"]["primal_strike_unarmed"] is None
    assert described["primal_strike_unarmed_effective"] == row_value
    assert "raw_unarmed" in described["primal_strike_unarmed_source"]

    override = get_adapter("starfire_scion").describe(
        config.replace(build_options={"primal_strike_unarmed": True})
    )
    assert override["primal_strike_unarmed_effective"] is True
    assert override["primal_strike_unarmed_source"] == "config.build_options"


def test_describe_reports_the_structural_choices_the_factory_makes():
    """The factory picks the enemy's focus target off ``zone_effect``; provenance
    must record which way it went."""
    zoned = get_adapter("silvertail").describe(
        RunConfig(build="silvertail", level=10, n_days=1,
                  build_options={"zone_effect": "spirit_guardians"})
    )
    plain = get_adapter("silvertail").describe(
        RunConfig(build="silvertail", level=10, n_days=1)
    )
    assert zoned["enemy_focus"] == "character"
    assert plain["enemy_focus"] == "summon"


def test_describe_is_a_pure_read():
    """It must not roll a die: two describes of the same config are identical and
    no RNG is involved at all."""
    config = RunConfig(build="war_angel", level=13, n_days=1)
    adapter = get_adapter("war_angel")
    assert adapter.describe(config) == adapter.describe(config)


# ---------------------------------------------------------------------------
# Custom adapters register without touching evaluation code (§3.2)
# ---------------------------------------------------------------------------

def test_a_new_build_needs_only_an_adapter():
    """The layer's whole claim: adding a build is data + a ~20-line adapter, never
    an evaluation-layer edit."""

    class TinyAdapter:
        name = "test_tiny_build"

        def available_levels(self):
            return [3]

        def option_schema(self):
            return {"flavour": OptionSpec("flavour", default="plain",
                                          values=("plain", "spicy"))}

        def build(self, config, rng):
            runner, char, dummy = war_angel.make_day_runner(
                config.level, rng, config.rounds_per_combat)
            return runner, Roster(characters=[char], enemies=[dummy])

        def describe(self, config):
            return {"build": self.name, "options": {}}

    from src.evaluation import adapters as adapters_module

    adapter = TinyAdapter()
    adapters_module.register(adapter)
    try:
        assert isinstance(adapter, BuildAdapter)
        output = simulate(RunConfig(build="test_tiny_build", level=3, n_days=2,
                                    build_options={"flavour": "spicy"}))
        assert output.roster.role_of(output.roster.character.id) == "characters"
        with pytest.raises(ValueError, match="no level 4"):
            RunConfig(build="test_tiny_build", level=4, n_days=1).validate()
    finally:
        adapters_module._REGISTRY.pop("test_tiny_build", None)
