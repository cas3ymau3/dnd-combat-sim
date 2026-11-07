"""
test_eval_party_seam.py — the party-construction seam (evaluation_framework.md §3.5.2).

The third of the framework's three "not a property of the build" declarations, after
``enemy`` (§3.4) and the baseline subject (§3.5.1).

**WHY THE STANDARD HAS A PARTY.** Step 5b set ``char_target_prob`` to 1.0 and argued the
standardized basis should be comparable rather than realistic.  The comparability
argument was right and focus-fire was the wrong way to get it: with no party in the
roster the character absorbs EVERY incoming attack, so every defensive measurement is
taken in a scenario no character is ever in.  A DECLARED party size is comparable *and*
realistic, and the number is in §4 provenance.

**AND IT DEFAULTS TO 4.** The draft proposed 1 so nothing existing would move. The user
overruled it: if most runs use the default, defaulting to 1 leaves every defensive number
in the project still measured under focus-fire, which is the defect the party exists to
remove. A default nobody uses is not a default.

THE ROLL CALL (per-feature ritual step 5):

| declaration | values | fixture covering each |
|---|---|---|
| ``RunConfig.party_size`` | 1 (solo) | ``test_party_size_1_is_the_solo_roster`` |
| | 4 (the default) | ``test_the_default_is_four_and_it_adds_three_members`` |
| | an intermediate value | ``test_an_intermediate_party_size_adds_the_right_count`` |
| | < 1 | ``test_a_party_size_below_one_is_refused`` |
| ``members_to_add`` | roster below the size | ``test_the_default_is_four_and_it_adds_three_members`` |
| | roster already at the size | ``test_a_roster_already_at_size_gets_nothing_added`` |
| | roster ABOVE the size | ``test_a_build_fielding_more_friendlies_than_declared_keeps_them`` |
| summons vs party slots | a build with a summon | ``test_a_summon_does_not_occupy_a_party_slot`` |
| ``party.describe`` | — | ``test_provenance_records_the_party_and_says_the_members_are_stand_ins`` |
| no new dice | — | ``test_installing_the_party_draws_no_dice`` |
| the re-baseline's BOUND | ``enemy="none"`` (bit-identical) | ``test_a_party_under_a_passive_enemy_is_BIT_IDENTICAL`` |
| | acting enemy (moves) | ``test_a_party_under_an_acting_enemy_cuts_incoming_damage`` |
| the seven ``allies`` cells | UNAVAILABLE -> measurable | ``test_the_seven_allies_cells_leave_the_unavailable_state`` |

**THE BOUND IS THE LOAD-BEARING TEST.** §3.5.2 claims the re-basline is confined to
acting-enemy rows because "a passive entity that nothing targets is bit-identical", and
that was measured BEFORE the code existed. ``test_a_party_under_a_passive_enemy_is_BIT
_IDENTICAL`` is that claim as an assertion, which matters because it is what makes 4 of
``GOLDEN_DPR``'s 13 rows *provably* unmoved rather than apparently unmoved.
"""

from __future__ import annotations

import pytest

from src.builds.character_stats import baseline_ac, baseline_saves
from src.evaluation import party as party_seam
from src.evaluation.config import RunConfig
from src.evaluation.report import build_report
from src.evaluation.runner import assemble, simulate
from src.rng import SeededRNG


def _built(config: RunConfig):
    config.validate()
    return assemble(config, SeededRNG(config.seed))


# ---------------------------------------------------------------------------
# party_size's values
# ---------------------------------------------------------------------------

def test_the_default_is_four_and_it_adds_three_members():
    """``party_size`` counts the WHOLE party INCLUDING the character (§3.5.2), so the
    default of 4 on a one-character build adds three."""
    config = RunConfig(build="war_angel", level=13, enemy="baseline", n_days=1)
    assert config.party_size == 4
    _, roster = _built(config)
    assert len(roster.characters) == 1
    assert len(roster.allies) == 3


def test_party_size_1_is_the_solo_roster():
    """The basis every pre-s54 number was measured on, still reachable by declaring
    it — which is what makes this a change of DEFAULT rather than a loss of
    capability."""
    _, roster = _built(RunConfig(build="war_angel", level=13, enemy="baseline",
                                 n_days=1, party_size=1))
    assert roster.allies == []


@pytest.mark.parametrize("size,expected", [(1, 0), (2, 1), (3, 2), (4, 3), (6, 5)])
def test_an_intermediate_party_size_adds_the_right_count(size, expected):
    _, roster = _built(RunConfig(build="war_angel", level=13, enemy="baseline",
                                 n_days=1, party_size=size))
    assert len(roster.allies) == expected


def test_a_party_size_below_one_is_refused():
    """It counts the character, so 0 is not "no party" — it is incoherent, and the
    error says which value gives the solo basis."""
    for bad in (0, -1):
        with pytest.raises(ValueError, match="INCLUDING the character"):
            RunConfig(build="war_angel", level=13, enemy="baseline", party_size=bad)


def test_a_roster_already_at_size_gets_nothing_added():
    config = RunConfig(build="war_angel", level=13, enemy="baseline", n_days=1,
                       party_size=1)
    _, roster = _built(config)
    assert party_seam.members_to_add(roster, 1) == 0


def test_a_build_fielding_more_friendlies_than_declared_keeps_them():
    """Never negative: deleting an entity a build constructed would make the run
    measure a different build.  ``describe`` reports the resolved size, so the
    discrepancy is recorded rather than silent."""
    config = RunConfig(build="war_angel", level=13, enemy="baseline", n_days=1,
                       party_size=4)
    _, roster = _built(config)
    assert len(roster.allies) == 3
    assert party_seam.members_to_add(roster, 2) == 0        # already past it
    assert party_seam.members_to_add(roster, 4) == 0        # exactly at it


def test_a_summon_does_not_occupy_a_party_slot():
    """A DECISION, not an oversight (``evaluation/party.py`` says why).

    §3.3's roles already separate them: a summon is an entity the build CREATED and
    commands. Counting Silvertail's companion against the party would make
    ``party_size`` mean something different for a summoner than for everyone else,
    and would mean the build silently fielded a smaller party than the config
    declared — the §4 failure the schema exists to refuse.
    """
    _, roster = _built(RunConfig(build="silvertail", level=10, enemy="baseline",
                                 n_days=1))
    assert len(roster.summons) == 1
    assert len(roster.allies) == 3                          # not 2
    assert len(roster.characters) + len(roster.allies) == 4


# ---------------------------------------------------------------------------
# What a party member IS
# ---------------------------------------------------------------------------

def test_members_come_from_the_baseline_progression_not_the_builds_own_row():
    """The whole reason ``character_stats.make_party_member`` exists.

    Starfire's retired ``make_party_member`` read ``LEVELS[level]['char_ac']`` — that
    build's data. A framework-standard party taking its AC from one particular
    character's level row is §3.4's coupling with the labels swapped, so the AC is
    asserted against the §3.5.1 progression and NOT against the build.
    """
    for build, level in (("war_angel", 13), ("starfire_scion", 15)):
        _, roster = _built(RunConfig(build=build, level=level, enemy="baseline",
                                     n_days=1))
        for ally in roster.allies:
            assert ally.stat("ac", (1, 0, 0)) == baseline_ac(level)
            for key, value in baseline_saves(level).items():
                assert ally.stat(key, (1, 0, 0)) == value


def test_members_are_passive_and_never_act():
    """§3.5.2: passive HP pools.  No policy, so the roster-wide damage ledger shows
    them dealing exactly nothing — which is the TRUE ZERO provenance has to explain."""
    output = simulate(RunConfig(build="war_angel", level=13, enemy="baseline",
                                n_days=4, seed=5))
    for ally in output.roster.allies:
        assert output.damage_dealt[ally.id] == [0, 0, 0, 0]
        assert ally.id not in output.roster.headline_source_ids


def test_installing_the_party_draws_no_dice():
    """Per-feature ritual step 3: a stray draw outside combat shifts the shared stream
    and breaks every ``GOLDEN_DPR`` point at once.

    Counted on a real generator, because ``install`` reaches into ``character_stats``
    and the claim is about everything it transitively calls.
    """
    class CountingRNG(SeededRNG):
        draws = 0

        def roll(self, n, sides, *, stream=None):
            CountingRNG.draws += 1
            return super().roll(n, sides, stream=stream)

    config = RunConfig(build="war_angel", level=13, enemy="baseline", n_days=1)
    adapter = config.validate()
    rng = CountingRNG(0)
    runner, roster = adapter.build(config, rng)
    before = CountingRNG.draws
    party_seam.install(runner, roster, config)
    assert CountingRNG.draws == before
    rng.roll_one(20, stream=("attack_d20", "probe"))
    assert CountingRNG.draws == before + 1      # the probe works


# ---------------------------------------------------------------------------
# THE BOUND on the re-baseline
# ---------------------------------------------------------------------------

def test_a_party_under_a_passive_enemy_is_BIT_IDENTICAL():
    """§3.5.2's measured bound, as an assertion.

    Adding friendlies costs nothing until something aims at them, so a run under
    ``enemy="none"`` is unchanged **to the last bit** — which is what makes 4 of
    ``GOLDEN_DPR``'s 13 rows provably unmoved rather than apparently unmoved, and what
    confines step 7's re-baseline to the acting-enemy rows.

    Asserted with ``==`` on the float and not ``approx``: "bit-identical" is the claim.
    """
    for build, level in (("war_angel", 12), ("starfire_scion", 15),
                         ("silvertail", 10)):
        base = RunConfig(build=build, level=level, enemy="none", n_days=40, seed=11,
                         party_size=1)
        assert (build_report(simulate(base)).headline.value
                == build_report(simulate(base.replace(party_size=4))).headline.value)


def test_a_party_under_an_acting_enemy_cuts_incoming_damage():
    """The other side of the bound — the rows that DO move, and the direction the
    change exists to produce.

    Measured rather than argued, and on the DEFENDER side, because that is where the
    change is meant to show and because s53's lesson is that an ablation test is blind
    to anything moving both arms: incoming damage is pinned here precisely so the
    defensive side is not in that blind spot.
    """
    base = RunConfig(build="war_angel", level=13, enemy="baseline", n_days=60,
                     seed=11, party_size=1)
    solo = simulate(base)
    party = simulate(base.replace(party_size=4))

    def taken(output):
        char = output.roster.character.id
        return sum(output.damage_taken[char]) / output.n_days

    solo_taken, party_taken = taken(solo), taken(party)
    assert party_taken < solo_taken
    # Four friendlies at uniform weights, so roughly a quarter of the swings — the
    # "incoming damage falls by roughly three quarters" §3.5.2 predicted in advance.
    assert 0.15 < party_taken / solo_taken < 0.40, (solo_taken, party_taken)
    # And the party absorbed what the character did not.
    assert sum(sum(party.damage_taken[a.id]) for a in party.roster.allies) > 0


# ---------------------------------------------------------------------------
# The seven allies cells (§3.5.5's metric-set review trigger)
# ---------------------------------------------------------------------------

def test_the_seven_allies_cells_leave_the_unavailable_state():
    """§3.5.5: seven ``allies``-keyed registry cells change state, and the three-state
    machinery distinguishes the two ways they land.

    With a party they are no longer "this build's roster has no allies". For PASSIVE
    members ``dpr_by_role[allies]`` and ``damage_taken_per_round_by_role[allies]``
    become MEASURED (a true zero for the first — the allies exist, they just do not
    attack), while ``attack_roll_rate[allies|*]`` is UNMEASURED: no attacks, so no
    denominator. More honest than "unavailable" either way.
    """
    report = build_report(simulate(RunConfig(build="war_angel", level=13,
                                             enemy="baseline", n_days=20, seed=11)))
    cells = [
        "dpr_by_role[allies]",
        "damage_taken_per_round_by_role[allies]",
        "attack_roll_rate[allies|hit]",
        "attack_roll_rate[allies|crit]",
        "attack_roll_rate[allies|advantage]",
        "healing_by_source[allies|combat]",
        "healing_by_source[allies|between]",
    ]
    assert len(cells) == 7
    for name in cells:
        value = report[name]
        assert "no allies" not in (value.note or ""), name
    # dpr_by_role[allies] is a measured TRUE ZERO, not an absence.
    ally_dpr = report["dpr_by_role[allies]"]
    assert ally_dpr.available is True
    assert ally_dpr.value == 0.0
    # The rates have no denominator, so they are UNMEASURED rather than 0.0.
    assert report["attack_roll_rate[allies|hit]"].value is None


def test_provenance_records_the_party_and_says_the_members_are_stand_ins():
    """§3.5.2 requires provenance to SAY the members are non-combatant stand-ins,
    because without that ``dpr_by_role[allies] == 0`` reads as a measurement of allies
    who tried and failed."""
    config = RunConfig(build="war_angel", level=13, enemy="baseline", n_days=1)
    _, roster = _built(config)
    block = party_seam.describe(roster, config)
    assert block["party_size"] == 4
    assert block["fielded"] == {"characters": 1, "allies": 3, "summons": 0}
    assert "TRUE ZERO" in block["member_kind"]
    assert "non-combatant" in block["member_kind"]
    assert "character_stats.make_party_member" in block["member_source"]
    # And it names the derivation, so a reader does not go looking for a declared split.
    assert "REFUSED" in block["targeting"]


def test_party_size_is_in_the_config_hash_and_the_canonical_form():
    """It changes what the defensive numbers MEAN, so two runs differing only in it
    must not collide in the §10 cache."""
    a = RunConfig(build="war_angel", level=13, enemy="baseline", party_size=1)
    b = a.replace(party_size=4)
    assert a.canonical()["party_size"] == 1
    assert b.canonical()["party_size"] == 4
    assert a.config_hash() != b.config_hash()
