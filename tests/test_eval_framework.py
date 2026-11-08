"""
test_eval_framework.py — step 1 of the evaluation framework (design/evaluation_framework.md
§13.1): RunConfig + BuildAdapter + Roster + the build registry.

Validation framing (§12, memory ``validate-mechanism-not-build-value``): these
tests assert the MECHANISM — that roles are tagged right, that a summon never
leaks into the headline column, that sparse level sets are respected, and that a
config cannot claim an assumption the run did not apply.  No test asserts that any
build's DPR value is "correct".

THE PARITY PROOF IS GONE (s52), AND WHAT STANDS IN ITS PLACE IS HERE
--------------------------------------------------------------------
``test_framework_reproduces_validation_exactly`` lived here from s43 to s51 and was
called "the correctness proof for the whole layer".  Step 5b deleted
``src/validation.py`` (§3.4, §12), so it is gone with it.  Read §12's retirement
record before concluding that the goldens simply replaced it, because the swap is
asymmetric: parity was never a PHYSICS signal — ``validation.py`` and
``src/evaluation`` were two readers of the SAME engine, so bit-identity proved the
framework had not corrupted the reading and would have been equally satisfied by an
engine that was wrong.

The LAYER half of what parity bought survives in this module, and it was always
here: ``test_headline_column_is_the_characters_own_output`` compares the framework's
source-attributed headline against the independent target-keyed ledger on one run.
Two subsystems, one number — which is the property parity was protecting, obtained
without a second harness.  The PHYSICS half is ``GOLDEN_DPR`` in
``test_eval_enemy_seam.py``, which now also carries the levels this module's parity
test parametrized, for the structural reasons it named.
"""

from __future__ import annotations

import logging

import pytest

from src.builds import enemy_stats, silvertail, starfire_scion, war_angel
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

#: Small but not trivial — enough days for the dice streams to diverge if two readings
#: of one run disagreed.  Named for the retired parity proof (s43-s51) and kept at its
#: value, because the tests below still use it and changing it would move numbers for
#: no reason.
PARITY_DAYS = 60


# ---------------------------------------------------------------------------
# The layer check (§12) — what survives the parity proof's retirement
# ---------------------------------------------------------------------------

def test_headline_column_is_the_characters_own_output():
    """The framework's headline reads ``damage_by_source(character)``, while
    ``validation.py`` reads ``damage_received_by(dummy)``.  For a single-character
    build with an inert-to-the-dummy enemy these must agree — if they ever stop
    agreeing, the parity proof above is measuring the wrong thing."""
    output = simulate(RunConfig(enemy="baseline", build="war_angel", level=13,
                                n_days=PARITY_DAYS, seed=5))
    dummy = output.roster.enemies[0]
    assert output.headline_damage == output.damage_taken[dummy.id]


# ---------------------------------------------------------------------------
# Roster: roles, not tuple positions (§3.3)
# ---------------------------------------------------------------------------

def test_war_angel_roster_roles():
    """``party_size=1`` for the SOLO roster — the basis every pre-s54 number was
    measured on, and still reachable by declaring it (§3.5.2)."""
    output = simulate(RunConfig(enemy="none", build="war_angel", level=1, n_days=2,
                                seed=0, party_size=1))
    roster = output.roster
    assert [e.name for e in roster.characters] == [roster.character.name]
    assert roster.summons == [] and roster.allies == []
    assert len(roster.enemies) == 1
    assert roster.role_of(roster.character.id) == "characters"
    assert roster.role_of(roster.enemies[0].id) == "enemies"


def test_silvertail_roster_tags_the_beast_as_a_summon():
    """The build whose factory returns FOUR values with the summon in the MIDDLE —
    the exact shape that breaks any position-based reader."""
    output = simulate(RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=8, n_days=2, seed=0))
    roster = output.roster
    assert len(roster.characters) == 1
    assert len(roster.summons) == 1
    assert roster.role_of(roster.summons[0].id) == "summons"
    assert roster.summons[0].id not in roster.headline_source_ids
    assert roster.summons[0].id in roster.party_source_ids


def test_the_declared_party_is_tagged_allies_on_every_build():
    """**REPLACES ``test_starfire_party_member_is_recovered_by_difference_not_position``
    (s54).** That test's fixture was Starfire's ``with_party`` axis, retired as a second
    source for the party now that ``RunConfig.party_size`` declares it; the adapter's
    recover-by-difference helper survives with no shipped producer, which
    ``build_adapters`` records.

    The coverage it had — allies present, correctly role-tagged, versus a roster with
    none — is kept here on the live mechanism, and widened to every build: the party is
    the framework's, so it must appear identically on all three rather than only on the
    one whose factory happened to build one.
    """
    for build, level in (("war_angel", 13), ("starfire_scion", 15), ("silvertail", 10)):
        party = simulate(RunConfig(enemy="baseline", build=build, level=level,
                                   n_days=2, seed=0))
        assert len(party.roster.allies) == 3, build          # 4 - the character
        for ally in party.roster.allies:
            assert party.roster.role_of(ally.id) == "allies"
        # Distinct entities, and none of them is the character or a summon.
        assert len({a.id for a in party.roster.allies}) == 3
        assert not ({a.id for a in party.roster.allies}
                    & set(party.roster.ids("characters", "summons", "enemies")))

        solo = simulate(RunConfig(enemy="baseline", build=build, level=level,
                                  n_days=2, seed=0, party_size=1))
        assert solo.roster.allies == [], build


def test_summon_damage_never_merges_into_the_headline():
    """§3.3's structural, permanent rule: the headline is the character's own
    column; the roster total sits BESIDE it under a different name.

    Asserted as a MECHANISM — that the two columns are the character's alone and
    the character's plus the beast's — not that either number is right."""
    output = simulate(RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=8, n_days=8, seed=2))
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
    dummy = enemy_stats.make_baseline_enemy(1)
    with pytest.raises(ValueError, match="roles are exclusive"):
        Roster(characters=[char], summons=[char], enemies=[dummy])
    with pytest.raises(ValueError, match="at least one character"):
        Roster(characters=[], enemies=[dummy])


def test_roster_character_accessor_refuses_to_hide_plurality():
    char_a = war_angel.make_war_angel(1)
    char_b = war_angel.make_war_angel(2)
    roster = Roster(characters=[char_a, char_b],
                    enemies=[enemy_stats.make_baseline_enemy(1)])
    with pytest.raises(ValueError, match="multi-character"):
        _ = roster.character
    assert len(roster.headline_source_ids) == 2


# ---------------------------------------------------------------------------
# Registry + sparse level sets (§2 axis 4)
# ---------------------------------------------------------------------------

def test_registry_holds_the_three_builds_plus_the_baseline_subject():
    """FOUR entries since s54, and the fourth is not a build.

    ``baseline`` is the framework's own declared SUBJECT (§3.5), registered through
    the same seam precisely so that every mechanism test can reach it the way it
    reaches a build — which is what lets framework correctness move off the three
    real builds (§3.5.5) without a second code path.
    """
    assert available_builds() == ["baseline", "silvertail", "starfire_scion",
                                  "war_angel"]
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
        RunConfig(enemy="none", build="silvertail", level=6, n_days=1).validate()


def test_a_level_valid_for_one_build_is_not_valid_for_another():
    RunConfig(enemy="none", build="war_angel", level=7, n_days=1).validate()      # contiguous 1-16
    with pytest.raises(ValueError, match="no level 7"):
        RunConfig(enemy="none", build="starfire_scion", level=7, n_days=1).validate()


# ---------------------------------------------------------------------------
# RunConfig validation: a config must not claim an unapplied assumption
# ---------------------------------------------------------------------------

def test_unknown_scenario_axis_is_rejected_with_the_known_axes():
    with pytest.raises(ValueError, match="no scenario axis"):
        RunConfig(enemy="baseline", build="silvertail", level=8, n_days=1,
                  build_options={"zone_efect": "spirit_guardians"}).validate()


def test_out_of_vocabulary_axis_value_is_rejected():
    with pytest.raises(ValueError, match="fourth_level_spell"):
        RunConfig(enemy="baseline", build="starfire_scion", level=15, n_days=1,
                  build_options={"fourth_level_spell": "fireball"}).validate()


def test_open_axis_accepts_any_value():
    """``precast_prob`` is a probability, not a closed vocabulary."""
    RunConfig(enemy="baseline", build="starfire_scion", level=15, n_days=1,
              build_options={"precast_mode": "rng", "precast_prob": 0.25}).validate()


def test_war_angel_has_no_scenario_axes():
    assert get_adapter("war_angel").option_schema() == {}
    with pytest.raises(ValueError, match="no scenario axis"):
        RunConfig(enemy="none", build="war_angel", level=1, n_days=1,
                  build_options={"with_party": True}).validate()


@pytest.mark.parametrize("kwargs,match", [
    ({"mode": "finite_hp"}, "finite_hp"),
])
def test_designed_but_unwired_fields_raise_rather_than_being_ignored(kwargs, match):
    """Silently ignoring a designed-but-unwired field would make the §4 provenance
    block document assumptions the run never applied — so it is a hard error, not a
    warning.

    **This test lost two of its three cases in s50, deliberately.** ``enemy`` and
    ``enemy_options`` were rejected here from step 1 until the §13 step-5
    enemy-construction seam landed; they are now HONOURED, which is the whole point
    of that step, and the behaviour they used to assert is covered from the other
    side by ``test_the_enemy_fields_are_no_longer_rejected`` below and in full by
    ``tests/test_eval_enemy_seam.py``.  ``mode="finite_hp"`` is the one case that
    remains designed-but-unwired: it needs ``DayRunner(enemy_ids=…)``, which no
    factory passes.
    """
    with pytest.raises(NotImplementedError, match=match):
        RunConfig(enemy="none", build="war_angel", level=1, n_days=1, **kwargs)


def test_the_enemy_fields_are_no_longer_rejected():
    """The other side of the change above: the §3.4 seam honours both fields now.

    The REFUSALS did not go away, they became per-option and moved into
    ``evaluation/enemy.validate_options`` — an option the chosen enemy kind cannot
    honour is still a hard error, for the identical §4 reason.  See
    ``tests/test_eval_enemy_seam.py`` for that surface.
    """
    RunConfig(build="war_angel", level=1, n_days=1, enemy="baseline",
              enemy_options={"control": True}).validate()


@pytest.mark.parametrize("kwargs", [
    {"combats_per_day": 3},
    {"rounds_per_combat": 0},
    {"n_days": 0},
])
def test_day_shape_is_validated(kwargs):
    with pytest.raises(ValueError):
        RunConfig(enemy="none", build="war_angel", level=1, **{"n_days": 1, **kwargs})


def test_rounds_per_day_is_the_declared_denominator():
    config = RunConfig(enemy="none", build="war_angel", level=1, n_days=1, rounds_per_combat=4)
    assert config.rounds_per_day == 16


# ---------------------------------------------------------------------------
# Config identity: hashing, canonical form, paired seeding groundwork (§6.1, §10)
# ---------------------------------------------------------------------------

def test_config_hash_ignores_dict_ordering_but_not_content():
    a = RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=8, n_days=10,
                  build_options={"recast": True, "mortal_beast": True})
    b = RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=8, n_days=10,
                  build_options={"mortal_beast": True, "recast": True})
    c = b.replace(build_options={"mortal_beast": True, "recast": False})

    assert a.config_hash() == b.config_hash()
    assert hash(a) == hash(b)
    assert a.config_hash() != c.config_hash()
    assert {a, b, c} == {a, c}          # usable as a cache key


def test_replace_keeps_the_shared_seed_for_paired_comparisons():
    base = RunConfig(enemy="baseline", build="starfire_scion", level=15, n_days=10, seed=99)
    variant = base.replace(build_options={"with_party": True})
    assert variant.seed == base.seed == 99
    assert variant.config_hash() != base.config_hash()


def test_day_tier_labels_the_standard_counts():
    assert RunConfig(enemy="none", build="war_angel", level=1, n_days=50_000).day_tier == "standard"
    assert RunConfig(enemy="none", build="war_angel", level=1, n_days=2_000).day_tier == "quick"
    assert RunConfig(enemy="none", build="war_angel", level=1, n_days=1_234).day_tier == "custom"


# ---------------------------------------------------------------------------
# describe(): RESOLVED values, not the word "default" (§4)
# ---------------------------------------------------------------------------

def test_describe_fills_unset_axes_with_the_value_actually_used():
    config = RunConfig(enemy="baseline", enemy_options={"focus": "summon"}, build="silvertail", level=8, n_days=1,
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
    config = RunConfig(enemy="baseline", build="starfire_scion", level=15, n_days=1)
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


def test_describe_reports_no_enemy_fact_at_all():
    """s52 INVERTS this test, which is the cleanest statement of what 5b removed.

    It was written to assert that provenance recorded "the structural choices the
    factory makes" about the enemy — Silvertail's factory picked the enemy's focus
    target off its own ``zone_effect`` axis, so ``describe()`` reported
    ``enemy_focus: character`` or ``summon``.  That was honest reporting of a real
    coupling, and the coupling is what §3.4 exists to delete.

    Nothing reads these keys now: ``enemy.resolve``'s only consumer of ``described``
    was its ``build_default`` branch, and the authoritative enemy block is assembled
    from the config alone.  Leaving them would have left plausible-looking enemy
    numbers in provenance with no consumer and no claim to truth — the §7.6 trap — so
    what is asserted is their ABSENCE, across all three builds, since a leftover on
    one adapter is exactly how this would come back.

    Where the fact went: ``enemy_options['focus']``, declared by the caller and
    recorded in ``provenance.resolved["enemy"]["options"]``.
    """
    for build, level in (("silvertail", 10), ("war_angel", 13), ("starfire_scion", 15)):
        described = get_adapter(build).describe(
            RunConfig(build=build, level=level, n_days=1, enemy="baseline"))
        assert not [key for key in described if key.startswith("enemy")], described

    # ...and the focus it used to derive is now declared and resolved, so the fact is
    # recorded rather than merely gone.
    options = simulate(RunConfig(build="silvertail", level=10, n_days=1,
                                 enemy="baseline",
                                 enemy_options={"focus": "summon"}))
    assert options is not None       # the run is valid; the block is asserted below
    from src.evaluation.enemy import resolve as resolve_enemy
    block = resolve_enemy(RunConfig(build="silvertail", level=10, n_days=1,
                                    enemy="baseline",
                                    enemy_options={"focus": "summon"}))
    assert block["options"]["focus"] == "summon"


def test_describe_is_a_pure_read():
    """It must not roll a die: two describes of the same config are identical and
    no RNG is involved at all."""
    config = RunConfig(enemy="baseline", build="war_angel", level=13, n_days=1)
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

        def forced_save_abilities(self, config):
            """The build's half of the §13 saves channel (s56, step 8b).

            Declared here because the protocol requires it of every adapter and
            `_producible_saves` raises rather than guessing — the `needs_roster`
            precedent, so an adapter that forgets fails loudly instead of silently
            re-creating the unflagged-zero defect.  Empty, because this adapter
            wraps War Angel's factory and that build forces no saves at all.
            """
            return frozenset()

    from src.evaluation import adapters as adapters_module

    adapter = TinyAdapter()
    adapters_module.register(adapter)
    try:
        assert isinstance(adapter, BuildAdapter)
        output = simulate(RunConfig(enemy="none", build="test_tiny_build", level=3, n_days=2,
                                    build_options={"flavour": "spicy"}))
        assert output.roster.role_of(output.roster.character.id) == "characters"
        with pytest.raises(ValueError, match="no level 4"):
            RunConfig(enemy="none", build="test_tiny_build", level=4, n_days=1).validate()
    finally:
        adapters_module._REGISTRY.pop("test_tiny_build", None)


# ---------------------------------------------------------------------------
# §14's sparse-build-data deferral, as an assertion rather than a prose tally
# ---------------------------------------------------------------------------

#: build -> how many of the six saves the character carries at EVERY modeled level.
#:
#: The CURRENT state, deliberately, not the desired one.  `evaluation_framework.md`
#: §14's sparse-build-data entry and the Track 2 pointer in PROGRESS both quote these
#: tallies, and a tallied count in prose has nothing behind it — so they are pinned
#: here, where closing the gap makes the test fail and sends whoever closed it at the
#: notes to update them.
_SAVE_COVERAGE: dict[str, int] = {
    "war_angel": 6,        # all six, every level (s55, derived from the guide)
    "starfire_scion": 1,   # con_save only — War Angel's exact pre-s55 state
}

#: build -> the levels it models today.  The TARGET is 1-20 for all three (user, s55),
#: so this is the other half of the gap and the larger half: 33 of 60 pairs do not exist.
_MODELED_LEVELS: dict[str, list[int]] = {
    "war_angel": list(range(1, 17)),
    "silvertail": [4, 8, 10],
    "starfire_scion": [1, 4, 5, 9, 10, 11, 12, 15],
}


def test_the_sparse_build_data_is_what_section_14_says_it_is():
    """Read through each FACTORY, because that is what the engine reads.

    A `LEVELS`-table check would miss both halves of how this defect appears: the
    Starfire Scion's `ac` was declared in its table for sessions while
    `make_starfire_scion` never read it, and War Angel's saves are now DERIVED and so
    appear in no table at all.  Only the constructed Entity knows.

    And "nonzero" is NOT the property to assert for a save — 0 is a legal bonus for a
    dumped stat (War Angel's own INT is -1, and a +0 would be unremarkable).  PRESENCE
    is the property, because `Entity.stat()` returns 0 for a missing key BY DESIGN,
    which is what makes absent data indistinguishable from a real zero at the point of
    use.

    **This test is a TRIPWIRE and is MEANT to fail when either gap closes.** It pins
    the state §14 describes — the sparse LEVEL SETS and the sparse saves within them.
    Bringing a build toward 1-20, or giving the Scion or Silvertail L4 its saves, should
    break it, and the fix is then to update these dicts AND the two notes that quote
    them, not to loosen the assertion.
    """
    saves = {f"{a}_save" for a in ("str", "dex", "con", "int", "wis", "cha")}
    builds = {"war_angel": (war_angel.make_war_angel, war_angel.LEVELS),
              "silvertail": (silvertail.make_silvertail, silvertail.LEVELS),
              "starfire_scion": (starfire_scion.make_starfire_scion,
                                 starfire_scion.LEVELS)}

    # --- half one: the LEVEL SETS, against the 1-20 target -------------------
    for name, (_, levels) in builds.items():
        assert sorted(levels) == _MODELED_LEVELS[name], (name, sorted(levels))
    missing = sum(len([l for l in range(1, 21) if l not in _MODELED_LEVELS[name]])
                  for name in builds)
    assert missing == 33, missing
    assert sum(len(v) for v in _MODELED_LEVELS.values()) == 27

    # --- half two: the SAVES within the levels that do exist -----------------
    present: dict[str, dict[int, int]] = {}
    for name, (factory, levels) in builds.items():
        present[name] = {level: len(saves & set(factory(level).base_stats))
                         for level in sorted(levels)}
    for build, expected in _SAVE_COVERAGE.items():
        assert set(present[build].values()) == {expected}, (build, present[build])

    # Silvertail is the only build that varies BY LEVEL, which is why it is not in the
    # dict above: L4 predates the saves its later rows declare.
    assert present["silvertail"] == {4: 0, 8: 6, 10: 6}

    # The headline tally, derived from the three readings rather than restated.
    short = [(b, lv) for b, by_level in present.items()
             for lv, n in by_level.items() if n < 6]
    assert len(short) == 9, short
    assert sorted(short) == [("silvertail", 4)] + [
        ("starfire_scion", lv) for lv in _MODELED_LEVELS["starfire_scion"]]
