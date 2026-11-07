"""Tests for SeededRNG — the single dice channel, and its §6.3 SUBSTREAMS.

THE ROLL CALL (per-feature ritual step 5, written BEFORE the tests).  One row per
declaration framework step 9 adds, one column per value, naming the fixture that
covers it.  An empty cell is an untested value no matter how many tests exist.

| declaration        | value          | fixture                                      |
|--------------------|----------------|----------------------------------------------|
| ``ALIGNMENTS``     | ``run``        | ``test_run_alignment_never_resynchronizes``   |
|                    | ``day``        | ``test_day_alignment_resynchronizes_per_day`` |
|                    | ``day_combat`` | ``test_day_combat_alignment_resynchronizes_``
                                         ``per_combat``                              |
|                    | (invalid)      | ``test_an_unknown_alignment_is_refused``      |
| ``ALIGNMENT``      | pinned value   | ``test_the_PINNED_alignment_is_day``          |
| ``PURPOSES``       | each of the 8  | ``test_every_declared_purpose_is_a_distinct_``
                                         ``tape``                                     |
|                    | unknown        | ``test_an_unknown_purpose_is_refused``        |
| ``seed``           | int            | ``test_seeded_reproducibility``               |
|                    | ``None``       | ``test_an_unseeded_run_still_has_ONE_root``   |
| ``roll`` n         | ``>= 1``       | ``test_roll_returns_correct_count``           |
|                    | ``< 1``        | ``test_invalid_n_raises``                     |
| ``roll`` sides     | ``>= 2``       | ``test_roll_values_in_range``                 |
|                    | ``< 2``        | ``test_invalid_sides_raises``                 |
| ``describe()``     | serialized     | ``test_the_dice_channel_is_SERIALIZED_and_``
                                         ``not_merely_computed`` (3 layers)            |

What the roll call found, and it is the reason two of these tests exist: the
``seed=None`` branch had no fixture at all, and nothing pinned the ALIGNMENT —
which is the one declaration here whose value changes every number in the
project, so leaving it to prose is exactly what step 5's "prefer an assertion,
prose cannot fail" refuses.
"""

import numpy as np
import pytest

from src.rng import ALIGNMENT, ALIGNMENTS, PURPOSES, SCHEDULE_OWNER, SeededRNG

ANY = ("damage", "T")


# ---------------------------------------------------------------------------
# 1. The core interface
# ---------------------------------------------------------------------------

def test_roll_returns_correct_count():
    rng = SeededRNG(seed=1)
    results = rng.roll(4, 6, stream=ANY)
    assert len(results) == 4


def test_roll_values_in_range():
    rng = SeededRNG(seed=1)
    for _ in range(100):
        val = rng.roll_one(20, stream=ANY)
        assert 1 <= val <= 20


def test_seeded_reproducibility():
    """Same seed must produce the same sequence on the same stream."""
    rng_a = SeededRNG(seed=42)
    rng_b = SeededRNG(seed=42)
    for _ in range(20):
        assert rng_a.roll_one(20, stream=ANY) == rng_b.roll_one(20, stream=ANY)


def test_different_seeds_differ():
    """Different seeds should (almost certainly) diverge."""
    rng_a = SeededRNG(seed=1)
    rng_b = SeededRNG(seed=2)
    rolls_a = [rng_a.roll_one(20, stream=ANY) for _ in range(10)]
    rolls_b = [rng_b.roll_one(20, stream=ANY) for _ in range(10)]
    assert rolls_a != rolls_b


def test_invalid_n_raises():
    rng = SeededRNG(seed=1)
    with pytest.raises(ValueError):
        rng.roll(0, 6, stream=ANY)


def test_invalid_sides_raises():
    rng = SeededRNG(seed=1)
    with pytest.raises(ValueError):
        rng.roll(1, 1, stream=ANY)


def test_a_stream_is_REQUIRED():
    """There is no default stream, and that is a design decision rather than an
    oversight: a default is a catch-all, and a catch-all silently re-couples
    whatever lands in it — the exact failure substreams exist to remove, and one
    that would be invisible because the dice would still look fine."""
    rng = SeededRNG(seed=1)
    with pytest.raises(TypeError):
        rng.roll(1, 20)                                  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# 2. Stream identity
# ---------------------------------------------------------------------------

def test_every_declared_purpose_is_a_distinct_tape():
    """Each value of the closed ``PURPOSES`` vocabulary addresses its own tape.

    Asserted over ALL EIGHT rather than over a convenient one (step 5: test the
    branch), as 20 draws per purpose so a collision cannot hide behind a short
    sample.
    """
    rng = SeededRNG(seed=7)
    tapes = {p: [rng.roll_one(20, stream=(p, "owner")) for _ in range(20)]
             for p in PURPOSES}
    assert len(PURPOSES) == 8
    seen: dict[tuple, str] = {}
    for purpose, tape in tapes.items():
        key = tuple(tape)
        assert key not in seen, f"{purpose} collides with {seen.get(key)}"
        seen[key] = purpose


def test_distinct_owners_are_distinct_tapes():
    rng = SeededRNG(seed=7)
    a = [rng.roll_one(20, stream=("damage", "War Angel")) for _ in range(20)]
    b = [rng.roll_one(20, stream=("damage", "Dummy")) for _ in range(20)]
    assert a != b


def test_an_unknown_purpose_is_refused():
    rng = SeededRNG(seed=1)
    with pytest.raises(ValueError, match="CLOSED"):
        rng.roll(1, 20, stream=("initiative", "T"))


def test_a_streams_dice_do_not_depend_on_the_ORDER_streams_were_TOUCHED():
    """The key is DERIVED from ``(seed, epoch, purpose, owner)``, not handed out
    by ``SeedSequence.spawn()`` in call order.

    This is the single-tape problem one level up, and it is the reason
    ``spawn()`` — which §6.1 names by name — is NOT what this module uses.  With
    ``spawn()``, touching the enemy's tape before the character's would give each
    of them different dice than the other order, so a change in *which entity
    acts first* would still reshuffle everything.
    """
    first = SeededRNG(seed=5)
    a1 = [first.roll_one(20, stream=("attack_d20", "A")) for _ in range(10)]
    b1 = [first.roll_one(20, stream=("attack_d20", "B")) for _ in range(10)]

    second = SeededRNG(seed=5)                    # same seed, OPPOSITE order
    b2 = [second.roll_one(20, stream=("attack_d20", "B")) for _ in range(10)]
    a2 = [second.roll_one(20, stream=("attack_d20", "A")) for _ in range(10)]

    assert a1 == a2 and b1 == b2


def test_the_owner_label_is_not_an_Entity_id():
    """Found by surveying the call sites before designing, and worth an assertion
    because the obvious implementation is the broken one.

    ``Entity.id`` comes from a module-global ``itertools.count`` that never
    resets, so it depends on how many entities the PROCESS built earlier.  Keying
    a substream on it would make a run's dice depend on test ordering — a
    reproducibility defect that passes every single-process test.
    """
    from src.entity import Entity
    a = Entity(name="Twin", hp=10)
    b = Entity(name="Twin", hp=10)
    assert a.id != b.id                           # ids differ...
    rng_a, rng_b = SeededRNG(seed=3), SeededRNG(seed=3)
    assert ([rng_a.roll_one(20, stream=("damage", a.name)) for _ in range(10)]
            == [rng_b.roll_one(20, stream=("damage", b.name)) for _ in range(10)])
    #       ...but the NAME is what addresses the tape, so these agree.


def test_the_owner_code_is_stable_across_PROCESSES():
    """``zlib.crc32``, not ``hash()``.  Python's string hash is randomized per
    process, so a ``hash()``-keyed stream would give a different run on every
    interpreter invocation — the same defect as keying on ``Entity.id``, and
    harder to notice because it needs two processes to see it.

    Pinned as a literal so the function cannot be swapped without this failing.
    """
    from src.rng import _owner_code                     # noqa: SLF001
    assert _owner_code("War Angel") == 1063043837
    assert _owner_code(SCHEDULE_OWNER) == 3852478864


# ---------------------------------------------------------------------------
# 3. The alignment epoch
# ---------------------------------------------------------------------------

def test_the_PINNED_alignment_is_day():
    """The pinned value, asserted rather than left to prose.

    ``ALIGNMENT`` is the one declaration in this module whose value changes
    every number in the project, so §13 step 5's rule applies at its sharpest:
    prefer an assertion, because prose cannot fail.  Changing this constant
    re-baselines ``GOLDEN_DPR`` and belongs in a decision record — see §6.3 and
    the s60 entry in PROGRESS.md for the measurement that chose it.
    """
    assert ALIGNMENT == "day"
    assert ALIGNMENTS == ("run", "day", "day_combat")


def test_an_unknown_alignment_is_refused():
    with pytest.raises(ValueError, match="alignment must be"):
        SeededRNG(seed=1, alignment="per_round")


def test_run_alignment_never_resynchronizes():
    """``"run"`` is §6.1's literal wording, and the branch is covered because
    the MEASUREMENT needed it: it is the arm that showed §6.1's own prescription
    does not work (see §6.3).

    Entering a new day leaves the tape where it was, so draw 11 of the run is
    draw 11 whatever day it falls in.
    """
    rng = SeededRNG(seed=4, alignment="run")
    rng.begin_day(0)
    before = [rng.roll_one(20, stream=ANY) for _ in range(10)]
    rng.begin_day(1)
    after = [rng.roll_one(20, stream=ANY) for _ in range(10)]

    flat = SeededRNG(seed=4, alignment="run")
    flat.begin_day(0)
    assert before + after == [flat.roll_one(20, stream=ANY) for _ in range(20)]


def test_day_alignment_resynchronizes_per_day():
    """Each day is its own tape, so a day's dice do not depend on how many dice
    the PREVIOUS days drew.  That is the property the pairing is built on.
    """
    a = SeededRNG(seed=4, alignment="day")
    a.begin_day(0)
    [a.roll_one(20, stream=ANY) for _ in range(3)]        # a short day 0
    a.begin_day(1)
    day1_after_short = [a.roll_one(20, stream=ANY) for _ in range(10)]

    b = SeededRNG(seed=4, alignment="day")
    b.begin_day(0)
    [b.roll_one(20, stream=ANY) for _ in range(97)]       # a LONG day 0
    b.begin_day(1)
    day1_after_long = [b.roll_one(20, stream=ANY) for _ in range(10)]

    assert day1_after_short == day1_after_long
    # ...and day 1 is a different tape from day 0, not a replay of it.
    c = SeededRNG(seed=4, alignment="day")
    c.begin_day(0)
    assert day1_after_short != [c.roll_one(20, stream=ANY) for _ in range(10)]


def test_day_combat_alignment_resynchronizes_per_combat():
    """The finest declared arm.  Covered because it is a declared VALUE (step 5),
    and because §6.3's measurement rests on it being genuinely finer than
    ``"day"`` — it is, per combat; it just loses at the DAY level, which is the
    level the estimator averages over.
    """
    a = SeededRNG(seed=4, alignment="day_combat")
    a.begin_day(0); a.begin_combat(1)
    [a.roll_one(20, stream=ANY) for _ in range(3)]
    a.begin_combat(2)
    after_short = [a.roll_one(20, stream=ANY) for _ in range(10)]

    b = SeededRNG(seed=4, alignment="day_combat")
    b.begin_day(0); b.begin_combat(1)
    [b.roll_one(20, stream=ANY) for _ in range(97)]
    b.begin_combat(2)
    after_long = [b.roll_one(20, stream=ANY) for _ in range(10)]

    assert after_short == after_long
    # Under "day" the same two sequences must NOT agree — which is what makes
    # this a distinct arm rather than a second fixture for the same branch.
    c = SeededRNG(seed=4, alignment="day")
    c.begin_day(0); c.begin_combat(1)
    [c.roll_one(20, stream=ANY) for _ in range(3)]
    c.begin_combat(2)
    d = SeededRNG(seed=4, alignment="day")
    d.begin_day(0); d.begin_combat(1)
    [d.roll_one(20, stream=ANY) for _ in range(97)]
    d.begin_combat(2)
    assert ([c.roll_one(20, stream=ANY) for _ in range(10)]
            != [d.roll_one(20, stream=ANY) for _ in range(10)])


def test_an_unseeded_run_still_has_ONE_root():
    """The ``seed=None`` branch, which the roll call found had no fixture.

    An unseeded run is not reproducible across invocations — that is the point of
    it — but its substreams must still derive from ONE root, or two streams of
    the same run would be unrelated to each other in a way no provenance records.
    Checked by deriving the same stream twice and by confirming the entropy was
    pinned rather than re-drawn.
    """
    rng = SeededRNG(seed=None)
    assert rng.seed is None
    assert rng._entropy is not None                      # noqa: SLF001
    first = [rng.roll_one(20, stream=ANY) for _ in range(5)]
    twin = SeededRNG(seed=None)
    twin._entropy = rng._entropy                         # noqa: SLF001
    twin._streams.clear()                                # noqa: SLF001
    assert first == [twin.roll_one(20, stream=ANY) for _ in range(5)]


def test_the_cache_is_a_SPEED_device_and_not_part_of_the_contract():
    """A stream's dice are a function of its key, so re-deriving a generator
    mid-epoch would be wrong — the cache is what makes the position persist.

    Asserted because the invalidation rule ("clear when the epoch changes") is
    easy to loosen into "clear whenever", which would silently reset every tape
    to its first draw and make every roll in a combat the same number.
    """
    rng = SeededRNG(seed=4, alignment="day")
    rng.begin_day(0)
    first = rng.roll_one(20, stream=ANY)
    rest = [rng.roll_one(20, stream=ANY) for _ in range(30)]
    assert rest.count(first) < 30            # not a stuck tape
    assert len(set(rest)) > 5                # ...and genuinely varying

    # Re-entering the SAME day is a no-op, so the tape does not rewind.
    rng.begin_day(0)
    assert rng.roll_one(20, stream=ANY) != first or len(set(rest)) > 1


def test_describe_records_the_alignment_because_it_changes_the_numbers():
    """§4 provenance.  Two runs at one seed and two alignments are DIFFERENT
    RUNS, and a reader comparing them without knowing that would be comparing
    two streams — which is the §4 failure of an assumption recorded without
    what it was worth."""
    block = SeededRNG(seed=11).describe()
    assert block["seed"] == 11
    assert block["alignment"] == ALIGNMENT
    assert block["purposes"] == list(PURPOSES)


def test_the_dice_channel_is_SERIALIZED_and_not_merely_computed():
    """§6.3 says provenance carries the alignment.  This asserts that the thing a
    READER sees carries it, which is a different claim from "a method computes it".

    **This is the defect per-feature ritual step 6 found in s60**, and it is the s56
    pattern verbatim: `SeededRNG.describe()` was written, §6.3 claimed §4 carried it,
    and for one commit NOTHING SERIALIZED IT — the method had no caller, the artifact
    had no key and the console header had no field.  It surfaced by rendering one real
    output and looking at it, not by re-reading the design note.  The reusable form,
    from s56: **when a design document states that something must be RECORDED, grep
    for what SERIALIZES it, not for what COMPUTES it.**

    Asserted at all three layers, because each is a separate writer and the defect was
    that two of the three did not exist.  The value is the one the RUN used, taken from
    the generator rather than from ``src.rng.ALIGNMENT``, so a run through a
    differently-aligned channel cannot report the pinned constant.
    """
    from src.evaluation.artifact import report_to_dict
    from src.evaluation.config import RunConfig
    from src.evaluation import console
    from src.evaluation.runner import run

    report = run(RunConfig(build="war_angel", level=5, n_days=3, seed=1,
                           enemy="none"))

    # 1. the structured block
    block = report.provenance.dice_channel
    assert block["alignment"] == ALIGNMENT
    assert block["purposes"] == list(PURPOSES)
    assert block["seed"] == 1

    # 2. the JSON artifact (additive at schema_version 1)
    assert report_to_dict(report)["provenance"]["dice_channel"] == block

    # 3. the console header, which is what a human actually reads
    assert f"dice {ALIGNMENT}" in console.render(report)


def test_a_substream_is_a_real_numpy_generator():
    """Guards the one thing a hand-rolled key scheme could get wrong invisibly:
    the key must reach numpy, not be swallowed.

    The method is ``substream`` and not ``stream`` for a measured reason: the first
    cut named it ``stream``, which collided with the ``self.stream`` attribute
    ``tests/test_eval_metrics._RecordingRNG`` keeps its recording in — so the router
    became a LIST and every roll raised ``TypeError``.  Caught by that test, which
    is the only thing between it and shipping."""
    rng = SeededRNG(seed=1)
    gen = rng.substream("damage", "T")
    assert isinstance(gen, np.random.Generator)
    assert gen is rng.substream("damage", "T")              # cached, same object
