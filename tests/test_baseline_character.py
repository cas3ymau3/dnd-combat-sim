"""
test_baseline_character.py — the framework's declared SUBJECT in motion
(evaluation_framework.md §3.5.1).

``character_stats`` is the subject's stat block and ``tests/test_character_stats.py``
pins the approved progression; this is what the subject DOES, and the question every
test below answers is the one §3.5 exists to make answerable: **does each core channel
have a producer, and does each axis move only the channel it exists to move?**

Why that matters more than any number here: the framework was validated against three
builds written as scaffolding, whose data is sparse exactly where the framework needs it
complete, so **a framework defect and a content gap were indistinguishable**. A complete
subject is what separates them.

THE ROLL CALL (per-feature ritual step 5) — one row per DECLARATION this change
touches, one column naming the fixture that covers each VALUE.

| declaration | values | fixture covering each |
|---|---|---|
| CORE: weapon attacks | — | ``test_the_attacks_channel_has_a_producer`` |
| CORE: concentration | held / broken | ``test_the_concentration_channel_has_a_producer`` |
| CORE: save-forcing spell | — | ``test_the_character_forces_saves_from_its_own_side`` |
| CORE: healing, in combat | — | ``test_BOTH_healing_contexts_have_a_producer`` — **the first in the project** |
| CORE: healing, between | — | same |
| CORE: slot budget | — | ``test_the_resource_ledger_has_a_producer`` |
| CORE: opportunity attack | — | ``test_the_reaction_slot_has_a_producer`` |
| ``aoo_per_combat`` | 1 (default) | ``test_the_reaction_slot_has_a_producer`` |
| | 0 | ``test_aoo_0_draws_no_dice_and_is_a_different_stream`` |
| | > 1 | ``test_more_than_one_aoo_per_combat_scales_the_rate`` |
| | < 0 | ``test_a_negative_aoo_count_is_refused`` |
| axis ``summon`` | off / on | ``test_the_summon_axis_populates_the_per_summon_column`` |
| axis ``ally_buff`` | off / on | ``test_the_ally_buff_axis_targets_a_declared_party_member`` |
| | on with NO allies | ``test_the_ally_buff_axis_does_not_fire_without_allies`` |
| axis ``reaction_mitigation`` | off / on | ``test_the_reaction_mitigation_axis_uses_the_defender_seam`` |
| bonus-action priority | buff / heal / summon command | ``test_the_bonus_action_priority_is_declared_and_nothing_is_dropped`` |
| ``level`` | all 20 | ``test_every_level_runs_and_populates_every_core_channel`` |
| | out of range | ``test_an_out_of_range_level_is_refused`` |
| ``BaselineCharacterAdapter`` | registered, 20 levels | ``test_the_adapter_is_registered_with_all_twenty_levels`` |
| ``bind_roster`` seam | ``needs_roster`` True | ``test_the_adapter_declares_that_it_needs_the_installed_roster`` |

**TWO DEFECTS THE FIXTURES FOUND, both in the first cut of the policy**, recorded
because each is a shape rather than a typo:

1. **A round-1 early return dropped the opportunity attack** whenever its pre-rolled
   round was 1, so ``reactions_per_round`` read **0.184** where ``aoo_per_combat=1``
   requires 0.25 — a quarter of them, silently, because a quarter of rounds are round 1.
   The three economy slots are independent (CLAUDE.md #11) and a policy structured
   around what the ACTION does will not keep them that way. Caught only because the
   declared parameter gives the channel an exact expected value: "greater than zero"
   would have passed.
2. **The summon axis populated no per-summon column**, because a mid-combat
   ``create_entity`` never reaches ``Roster.summons`` and the column is roster-keyed.
   The axis existed, the summon attacked, and the thing it was added to exercise was
   UNAVAILABLE. Fixed by Silvertail's pattern — the entity is in the roster from the
   start and is COMMANDED — and caught by looking at the metric rather than at the
   policy.
"""

from __future__ import annotations

import pytest

from src.builds import baseline_character as bc
from src.builds import character_stats as cs
from src.evaluation.adapters import available_builds, get_adapter
from src.evaluation.config import RunConfig
from src.evaluation.runner import run, simulate
from src.rng import SeededRNG

LEVEL = 13
DAYS = 200
SEED = 11


def _run(level=LEVEL, days=DAYS, **options):
    return run(RunConfig(build="baseline", level=level, enemy="baseline",
                         n_days=days, seed=SEED, build_options=options))


# ---------------------------------------------------------------------------
# The CORE capabilities: every channel has a producer
# ---------------------------------------------------------------------------

def test_the_attacks_channel_has_a_producer():
    """§8.1, from the subject's side.  A COUNT, so it pools legitimately."""
    report = _run()
    assert report["attacks_per_round"].value > 0
    rate = report.breakdown("attack_roll_rate")[("characters", "hit")]
    assert 0.0 < rate.value < 1.0


def test_the_concentration_channel_has_a_producer():
    """The concentration spell is CORE because it is the only thing control pressure
    can take away — a subject that never concentrates leaves the whole resilience
    panel measuring nothing."""
    report = _run()
    assert report["concentration_checks_per_day"].value > 0
    assert 0.0 < report["concentration_break_rate"].value < 1.0
    assert report["concentration_breaks_per_day"].value > 0


def test_the_character_forces_saves_from_its_own_side():
    """The saves channel keyed by ability, from the CHARACTER.

    Worth its own test because every other producer in the corpus is the ENEMY, so
    before this subject the channel's character-side half had no fixture at all.
    """
    report = _run()
    forced = report.breakdown("saves_forced_per_round")
    # The subject's save spell forces DEX. The breakdown is UNCROSSED (its cells
    # overlap, so the dimensions are reported independently), hence ('dex_save', '*')
    # rather than ('dex_save', 'damage') — the ability margin is the cell that exists.
    assert forced[("dex_save", "*")].value > 0
    assert forced[("*", "damage")].value > 0
    fail = report.breakdown("save_fail_rate")[("dex_save", "*")]
    assert 0.0 < fail.value < 1.0


def test_BOTH_healing_contexts_have_a_producer():
    """§3.5.1 makes healing core *in both contexts* because ``healing_by_source``
    needs both, and **this is the first subject in the project to populate
    ``combat``**: every shipped build heals out of combat by preference (healing.md
    §11.1), so that context was structurally empty for every subject the framework
    had.
    """
    report = _run()
    healing = report.breakdown("healing_by_source")
    assert healing[("characters", "combat")].value > 0
    assert healing[("characters", "between")].value > 0


def test_the_between_combats_healing_draws_no_dice():
    """Per-feature ritual step 3, and the rule that keeps every GOLDEN_DPR point
    still: healing applied OUTSIDE combat is MEAN-FIELD and draws nothing.

    Asserted by running a day with a counting generator and checking the between-heal
    contributed no draw — the between-combats hook runs at a point every build passes
    through, so one roll there would shift every subsequent die for every build.
    """
    class CountingRNG(SeededRNG):
        def __init__(self, seed):
            super().__init__(seed)
            self.draws = 0

        def roll(self, n, sides):
            self.draws += 1
            return super().roll(n, sides)

    probe = CountingRNG(SEED)
    runner, char, _dummy, _beast = bc.make_day_runner(LEVEL, probe)
    policy = runner.policies[char.id]
    result = runner.run_day()
    assert result.telemetry.healing_total(context="between") > 0

    class _Ctx:
        telemetry = result.telemetry
        entities = runner.entities
        after_combat_num = 1
        sr_after_combat = 2
        interval_length = 60
        rng = probe

    before = probe.draws
    policy._between_healed = False                      # noqa: SLF001
    char.hp = char.max_hp - 20                          # give it something to heal
    policy.between_combats(_Ctx())
    assert char.hp > char.max_hp - 20, "the heal must actually land"
    assert probe.draws == before


def test_the_resource_ledger_has_a_producer():
    """The slot budget is core because the §13 economy channel otherwise has nothing
    to count on a subject the framework controls."""
    report = _run()
    assert report["spell_slots_per_day"].value > 0
    assert report["limited_resources_per_day"].value > 0


def test_the_reaction_slot_has_a_producer():
    """The REACTION — a third of the action economy (CLAUDE.md #11), and the channel
    s53 found dead at both ends.

    ``aoo_per_combat=1`` over four combats and 16 rounds is EXACTLY 0.25 per round,
    asserted as the exact value rather than as "greater than zero". That precision is
    what caught the first cut's defect: a round-1 early return dropped the AoO
    whenever its pre-rolled round was 1, giving 0.1875 — which "greater than zero"
    would have passed.
    """
    report = _run()
    assert report["reactions_per_round"].value == 0.25


@pytest.mark.parametrize("count,expected",
                         [(0, 0.0), (1, 0.25), (2, 0.5), (3, 0.75), (4, 1.0)])
def test_more_than_one_aoo_per_combat_scales_the_rate(count, expected):
    """``aoo_per_combat`` is a DECLARED parameter, so its whole range has to work —
    the value is an assumption §4 records, not a constant.

    **EXACT at every count, and the first cut was not.** Drawing each AoO's round
    independently let two land on the same round, where there is only ONE reaction,
    so the scheduler dropped the second and ``aoo_per_combat=2`` delivered 0.44
    instead of 0.5 — a declared parameter quietly meaning "at most this many". The
    rounds are now drawn DISTINCT, which is also the honest model, since two
    reactions in one round is RAW-impossible.
    """
    assert _run(days=40, aoo_per_combat=count)["reactions_per_round"].value == expected


def test_more_aoos_than_rounds_is_refused():
    """The distinctness has a ceiling, and exceeding it is incoherent rather than
    merely large — silently capping would make the declared parameter a wish."""
    char, dummy = cs.make_baseline_character(5), cs.make_party_member(5)
    with pytest.raises(ValueError, match="exceeds rounds_per_combat"):
        bc.BaselineCharacterPolicy(5, char, dummy, rounds_per_combat=4,
                                   aoo_per_combat=5)


def test_one_aoo_is_bit_identical_to_the_independent_draw_it_replaced():
    """Distinctness changed the DRAW PROCEDURE, and at the default count it must not
    change the stream: ``roll_one(rounds)`` over the full pool maps back to the same
    round number, so every number measured at ``aoo_per_combat=1`` is unaffected.

    Asserted as the drawn ROUND for many seeds rather than as a DPR, because a DPR
    equality could hold while the procedure differed.
    """
    for seed in range(40):
        char, dummy = cs.make_baseline_character(5), cs.make_party_member(5)
        policy = bc.BaselineCharacterPolicy(5, char, dummy, rounds_per_combat=4)
        policy.on_combat_start(0, SeededRNG(seed))
        drawn = policy._aoo_rounds                       # noqa: SLF001
        assert drawn == [SeededRNG(seed).roll_one(4)]


def test_aoo_0_draws_no_dice_and_is_a_different_stream():
    """``aoo_per_combat=0`` draws NOTHING at ``on_combat_start``, so declaring that
    the subject takes no opportunity attacks is a different dice STREAM and not
    merely a different count — which is what a declared parameter should be.

    Checked as a draw count rather than as a DPR, because a DPR difference could come
    from the missing attacks alone.
    """
    class CountingRNG(SeededRNG):
        def __init__(self, seed):
            super().__init__(seed)
            self.draws = 0

        def roll(self, n, sides):
            self.draws += 1
            return super().roll(n, sides)

    counts = []
    for aoo in (0, 1):
        rng = CountingRNG(SEED)
        runner, char, _d, _b = bc.make_day_runner(LEVEL, rng, aoo_per_combat=aoo)
        before = rng.draws
        runner.policies[char.id].on_combat_start(0, rng)
        counts.append(rng.draws - before)
    assert counts == [0, 1]


def test_a_negative_aoo_count_is_refused():
    char, dummy = cs.make_baseline_character(5), cs.make_party_member(5)
    with pytest.raises(ValueError, match="aoo_per_combat"):
        bc.BaselineCharacterPolicy(5, char, dummy, aoo_per_combat=-1)


def test_an_out_of_range_level_is_refused():
    char, dummy = cs.make_baseline_character(5), cs.make_party_member(5)
    with pytest.raises(ValueError, match="supports levels"):
        bc.BaselineCharacterPolicy(21, char, dummy)


@pytest.mark.parametrize("level", list(cs.LEVELS))
def test_every_level_runs_and_populates_every_core_channel(level):
    """**The property that makes this a SUBJECT rather than a build.**

    Every core capability is on at every one of the 20 levels. A capability that
    switched on partway up would make the low levels a different measurement from the
    high ones, which is the comparability defect §3.5 exists to remove — and it is
    exactly the defect the three real builds have (`ac` absent in 20 of 27 pairs).
    """
    report = _run(level=level, days=20)
    assert report["attacks_per_round"].value > 0
    assert report["reactions_per_round"].value == 0.25
    assert report["concentration_checks_per_day"].value > 0
    assert report["spell_slots_per_day"].value > 0
    healing = report.breakdown("healing_by_source")
    assert healing[("characters", "between")].value > 0


# ---------------------------------------------------------------------------
# The AXES: each moves the channel it exists to move, and the core stays core
# ---------------------------------------------------------------------------

def test_the_summon_axis_populates_the_per_summon_column():
    """The axis exists for the per-summon column and the roster-scoping checks.

    **This is the defect the fixture found**: with the summon created mid-combat by a
    ``cast_effect``, it never reached ``Roster.summons``, so ``dpr_by_role[summons]``
    was UNAVAILABLE while the summon attacked happily. The axis existed and the thing
    it was added to exercise did not. Now the entity is in the roster from the start
    and is COMMANDED on the controller's turn (Silvertail's pattern).

    §3.3's rule is asserted alongside: the summon's damage lands in the party column
    and NEVER in the headline, so turning the axis on must not inflate ``dpr``.
    """
    core = _run()
    with_summon = _run(summon=True)

    assert core.breakdown("dpr_by_role")["summons"].value is None
    summon_dpr = with_summon.breakdown("dpr_by_role")["summons"]
    assert summon_dpr.value > 0

    # §3.3: the headline is the character's own column, and the summon sits BESIDE it.
    assert with_summon["dpr"].value < core["dpr"].value + summon_dpr.value
    party = with_summon.breakdown("dpr_by_role")["*"]
    assert party.value == pytest.approx(with_summon["dpr"].value + summon_dpr.value,
                                        rel=1e-9)


def test_the_ally_buff_axis_targets_a_declared_party_member():
    """The axis exercises the ``allies`` role as a buff TARGET rather than as a
    damage sink — the one thing the passive party cannot do by itself.

    Measured on the defender side, which is where s53 said to pin things: a +2 AC on
    one of three allies means the party takes strictly less.
    """
    core_taken = _run().breakdown("damage_taken_per_round_by_role")["allies"].value
    buffed_taken = _run(ally_buff=True).breakdown(
        "damage_taken_per_round_by_role")["allies"].value
    assert buffed_taken < core_taken


def test_the_ally_buff_axis_does_not_fire_without_allies():
    """``party_size=1`` leaves no ally to buff, and the policy does NOT invent one —
    that would be a second source for the party (§3.5.2), which is what retired
    ``with_party``.

    So the axis is inert rather than erroring: it is the roster's absence, not a
    contradiction in the config, and the run is still a valid measurement of the
    core. (Contrast ``focus='summon'`` on a summonless roster, which IS refused —
    there the config asked for a measurement the roster cannot produce.)
    """
    solo = RunConfig(build="baseline", level=LEVEL, enemy="baseline", n_days=20,
                     seed=SEED, party_size=1, build_options={"ally_buff": True})
    plain = solo.replace(build_options={})
    assert run(solo)["dpr"].value == run(plain)["dpr"].value


def test_the_reaction_mitigation_axis_uses_the_defender_seam():
    """The axis exercises ``on_incoming_hit`` from the CHARACTER's side, and shows up
    in two channels at once.

    The reaction count RISES above the opportunity attack's 0.25 — which is the
    double-booking §8.2a documents, reproduced rather than quietly fixed, because a
    subject whose reaction economy differs from the builds it exists to make
    comparable would be measuring something else.
    """
    core = _run()
    mitigated = _run(reaction_mitigation=True)
    assert core["reactions_per_round"].value == 0.25
    assert mitigated["reactions_per_round"].value > 0.25
    # ...and it genuinely mitigates: fewer hits land, so less healing is needed.
    core_heal = core.breakdown("healing_by_source")[("characters", "combat")].value
    mit_heal = mitigated.breakdown("healing_by_source")[("characters", "combat")].value
    assert mit_heal < core_heal


def test_all_three_axes_together_keep_every_core_channel_populated():
    """The axes are additive and none of them empties a core channel.

    This is what the declared bonus-action priority is FOR: with three axes on, the
    heal still fires, because an axis that silences a core channel makes the fixture
    worse the more of it you turn on.
    """
    report = _run(summon=True, ally_buff=True, reaction_mitigation=True)
    assert report["attacks_per_round"].value > 0
    assert report["reactions_per_round"].value > 0.25
    assert report["concentration_checks_per_day"].value > 0
    assert report["spell_slots_per_day"].value > 0
    healing = report.breakdown("healing_by_source")
    assert healing[("characters", "combat")].value > 0
    assert healing[("characters", "between")].value > 0
    assert report.breakdown("dpr_by_role")["summons"].value > 0


def test_the_bonus_action_priority_is_declared_and_nothing_is_dropped():
    """The bonus action is contended by three capabilities, and the priority is
    DECLARED (buff > heal > summon command) rather than emergent.

    ``decide`` is a pure read, so the snapshot's counts do not fall as choices are
    emitted; two bonus-action choices would be emitted and the scheduler would drop
    the second. Resolving that is the POLICY's job (CLAUDE.md #7), and the assertion
    is that at most one bonus-action choice is ever emitted — which is checkable
    directly, unlike "the scheduler logged no warning".
    """
    from src.policy import GameState

    char = cs.make_baseline_character(LEVEL)
    dummy = cs.make_party_member(LEVEL)
    allies = [cs.make_party_member(LEVEL, i) for i in (1, 2, 3)]
    policy = bc.BaselineCharacterPolicy(
        LEVEL, char, dummy, allies=allies,
        summon_entity=bc.make_baseline_summon(LEVEL), ally_buff=True,
    )
    policy.on_combat_start(0, SeededRNG(SEED))
    char.hp = char.max_hp - 20                 # make the heal want to fire
    for round_number in range(1, 5):
        snapshot = GameState(
            actor=char, enemies=(dummy,), allies=tuple(allies),
            round_number=round_number, turn_index=0,
            tick=(round_number, 0, 0),
            resources={"action": 1, "bonus_action": 1, "reaction": 1,
                       **char.resources.as_dict()},
        )
        choices = policy.decide(snapshot)
        assert sum(1 for c in choices if c.cost == "bonus_action") <= 1
        assert sum(1 for c in choices if c.cost == "action") <= 1
        assert sum(1 for c in choices if c.cost == "reaction") <= 1


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------

def test_the_adapter_is_registered_with_all_twenty_levels():
    """The only adapter whose level set is a full range rather than sparse — §3.2's
    sparseness note is about BUILDS, and this is why the framework never assumed
    otherwise."""
    assert "baseline" in available_builds()
    adapter = get_adapter("baseline")
    assert adapter.available_levels() == list(range(1, 21))


def test_the_adapter_declares_that_it_needs_the_installed_roster():
    """``needs_roster`` is DECLARED, not detected with ``hasattr``: an adapter that
    sets the flag and forgets ``bind_roster`` fails loudly rather than silently
    skipping the bind, and the three other adapters are unaffected."""
    adapter = get_adapter("baseline")
    assert adapter.needs_roster is True
    assert callable(adapter.bind_roster)
    for other in ("war_angel", "starfire_scion", "silvertail"):
        assert getattr(get_adapter(other), "needs_roster", False) is False


def test_the_policy_receives_the_frameworks_allies_not_its_own():
    """§3.5.2's single-source rule, at the seam that could break it.

    The ``ally_buff`` axis needs a target, and the only honest source is the roster
    the framework built. ``bind_roster`` is what hands it over, AFTER
    ``party.install`` — asserted by identity, so a policy that constructed an
    equivalent ally would fail.
    """
    output = simulate(RunConfig(build="baseline", level=LEVEL, enemy="baseline",
                                n_days=1, seed=SEED,
                                build_options={"ally_buff": True}))
    assert len(output.roster.allies) == 3
    policy = output.runner_policy if hasattr(output, "runner_policy") else None
    # The policy's allies must BE the roster's, by identity — a policy that
    # constructed an equivalent ally would pass an equality check and fail this.
    bound = output.roster.allies
    assert all(a.id in set(output.roster.party_stand_ins) for a in bound)
    assert policy is None or [a.id for a in policy._allies] == [a.id for a in bound]


def test_provenance_records_the_aoo_approximation_and_the_progression():
    """§4: the resolved block must say what was ASSUMED, not just what was set.

    ``aoo_per_combat`` is a frequency standing in for an absent spatial model, and
    the number alone does not tell a reader that — which is exactly the kind of
    buried assumption §4 exists to surface.
    """
    config = RunConfig(build="baseline", level=LEVEL, enemy="baseline", n_days=1,
                       seed=SEED)
    described = get_adapter("baseline").describe(config)
    assert described["options"]["aoo_per_combat"] == 1
    assert described["progression"]["ac"] == cs.baseline_ac(LEVEL)
    assert described["progression"]["spell_slots"] == list(
        cs.baseline_spell_slots(LEVEL))
    assert "character_stats" in described["progression_source"]

    char, dummy = cs.make_baseline_character(LEVEL), cs.make_party_member(LEVEL)
    params = bc.BaselineCharacterPolicy(LEVEL, char, dummy).describe_parameters()
    assert "NO SPATIAL MODEL" in params["aoo_model"]
    assert "FREQUENCY" in params["aoo_model"]
    assert params["axes"] == {"summon": False, "ally_buff": False,
                              "reaction_mitigation": False}
    assert params["healing"]["between_combats"]["rolled"] is False


def test_the_fully_configured_subject_leaves_NO_channel_unavailable():
    """**THE POINT OF §3.5, as one number.**

    With all three axes on and the enemy's two option toggles on, the registry reports
    **zero** unavailable cells — the first configuration in the project's history for
    which that is true. War Angel at the same enemy configuration reports 8 unavailable
    and 17 unmeasured; the subject reports 0 and 3.

    That is what "every registry channel gets a fixture that genuinely populates it"
    (§3.5.1) means operationally, and it is the property that lets framework
    correctness move off the three real builds (§3.5.5): a mechanism test that needs a
    populated channel now has somewhere to get one, instead of needing a build whose
    data happens to reach it.

    The three that stay UNMEASURED are correct and expected: the declared party's
    members are PASSIVE, so they roll no attacks and the rates have no denominator
    (§3.5.2). They go live with §3.3's multi-character party, not with anything here —
    which is why this asserts them explicitly rather than allowing any three.
    """
    full = RunConfig(
        build="baseline", level=LEVEL, enemy="baseline", n_days=40, seed=SEED,
        enemy_options={"control": True, "mitigation": True},
        build_options={"summon": True, "ally_buff": True,
                       "reaction_mitigation": True},
    )
    report = run(full)
    unavailable = sorted(n for n, v in report.values.items() if not v.available)
    unmeasured = sorted(n for n, v in report.values.items()
                        if v.available and v.value is None)
    assert unavailable == []
    assert unmeasured == ["attack_roll_rate[allies|advantage]",
                          "attack_roll_rate[allies|crit]",
                          "attack_roll_rate[allies|hit]"]

    # ...and the comparison that makes the number mean something: a real build at the
    # same enemy configuration cannot do this, which is the gap §3.5 exists to close.
    war_angel = run(RunConfig(build="war_angel", level=13, enemy="baseline",
                              n_days=40, seed=SEED,
                              enemy_options={"control": True, "mitigation": True}))
    assert sum(1 for v in war_angel.values.values() if not v.available) > 0


# ---------------------------------------------------------------------------
# The AXES' own goldens
# ---------------------------------------------------------------------------
#
# The subject's enemy-side goldens live in `test_eval_enemy_seam.GOLDEN_DPR`, whose key
# shape is (build, level, enemy, enemy_options).  The three AXES are BUILD options, so
# they cannot be expressed there — and a second dict with a different key shape is the
# honest answer rather than widening the first, since what these pin is a different
# thing: that each axis is WIRED, end to end, at an exact value.
#
# Each is 400 days at seed 11, the same tier as GOLDEN_DPR, so a move here and a move
# there are comparable.  Regenerating one is a DELIBERATE act with a decision record
# (§12), exactly as for GOLDEN_DPR.
AXIS_GOLDEN: dict[str, float] = {
    "summon": 11.84109375,
    "ally_buff": 11.8425,
    "reaction_mitigation": 11.58359375,
}


@pytest.mark.parametrize("axis", sorted(AXIS_GOLDEN))
def test_each_axis_is_wired_end_to_end_at_an_exact_value(axis):
    """An exact value per axis, so a change that silently stops an axis reaching the
    engine fails here rather than showing up as a plausible number.

    The ablation tests above assert each axis moves the channel it exists to move;
    this asserts it moves the headline by a specific amount, which is the check that
    survives a refactor of the channels themselves. Both are needed — s53's lesson is
    that an ablation test is blind to anything moving both arms, and an exact golden
    is blind to nothing but also explains nothing.
    """
    value = run(RunConfig(build="baseline", level=13, enemy="baseline", n_days=400,
                          seed=11, build_options={axis: True})).headline.value
    assert value == AXIS_GOLDEN[axis]
