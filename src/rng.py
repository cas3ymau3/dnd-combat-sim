"""
rng.py — Seeded RNG, the single dice channel for the entire simulation.

All dice rolls everywhere must go through ``SeededRNG.roll()``.  Nothing in the
engine calls random directly.  This guarantees:
  - Any run can be exactly reproduced by re-using the seed.
  - The seed is always logged so replays are possible.
  - We can swap the underlying generator later without touching call sites.

SUBSTREAMS (framework step 9, ``evaluation_framework.md`` §6.3 — LOCKED s60)
---------------------------------------------------------------------------
Until s60 this class wrapped ONE numpy generator, so every die in the
simulation was a single tape read in order.  That made §6.1's common random
numbers **statistically inert**: the moment two configs drew a different number
of dice, every later draw in one of them was offset by a position on the shared
tape, and a tape read at a shifted offset is no better than a fresh one.
§6.1 measured the result — a paired covariance of −0.12…+0.06 and a variance
reduction of 0.892…1.069, i.e. *worse* than independent seeding in 3 of 9
diverging cells.

So the single tape is replaced by a **routed set of substreams**.  Every
``roll`` names its stream as ``(purpose, owner)``; the router derives that
stream's generator deterministically from the run's seed, the current ALIGNMENT
EPOCH and the key.  Two consequences, and they are the whole point:

  * A change to what the CHARACTER draws cannot move what the ENEMY draws.  The
    streams are addressed, not sequential, so there is no shared cursor to
    shift.
  * The epoch RE-SYNCHRONIZES the streams at every day (and every combat), so a
    divergence is confined to the epoch it happens in instead of contaminating
    the rest of the run.  The day is the estimator's replication unit
    (``runner.simulate`` loops ``run_day`` ``n_days`` times), which is where
    textbook common random numbers synchronize.

**Nothing here is a free change: it moves every seeded number by construction.**
That is why it is a roadmap step with a decision record (§13 step 9) rather
than a tweak — see the re-baseline record above ``GOLDEN_DPR`` in
``tests/test_eval_enemy_seam.py``.

Three properties worth knowing before touching this module:

  * **The key is DERIVED, not spawned in sequence.**  ``SeedSequence.spawn()``
    hands out children in call order, which would make a stream's identity
    depend on the order streams were first touched — the single-tape problem one
    level up.  A ``spawn_key`` is a pure function of the key instead, so a
    stream's dice depend on nothing but ``(seed, epoch, purpose, owner)``.
  * **The owner is a stable LABEL, never ``Entity.id``.**  ``Entity.id`` comes
    from a module-global ``itertools.count`` that never resets, so it depends on
    how many entities the PROCESS built earlier — keying on it would make a
    run's dice depend on test ordering.  Entity-owned streams use
    ``entity.name``; a policy's own pre-rolls use its declared ``stream_owner``.
  * **The router method is ``substream``, not ``stream``.**  ``stream`` collided
    with the ordinary ``self.stream`` attribute a recording wrapper wants, so the
    router silently became a list and every roll raised — found by a test, which
    is the only reason it was not shipped.  The ``roll(stream=...)`` keyword keeps
    its name: that one is a KEY, not the generator.
  * **``PURPOSES`` is CLOSED and has no catch-all.**  An unrecognised purpose
    raises.  A catch-all stream would quietly re-couple whatever landed in it,
    which is the failure the whole module exists to remove, and it would be
    invisible — the dice would still look fine.
"""

import logging
import zlib

import numpy as np

log = logging.getLogger(__name__)


#: The closed purpose vocabulary.  One tape per (purpose, owner); a purpose
#: boundary is where a change in HOW MANY dice one kind of roll draws stops
#: shifting another kind.  Splitting ``attack_d20`` from ``damage`` is the
#: within-entity half of that: a toggle that adds damage dice to a hit leaves
#: the entity's own to-hit sequence untouched.
#:
#: NO CATCH-ALL, deliberately (the s57 lesson: a closed vocabulary's catch-all
#: is only unambiguous while something outside the data supplies the missing
#: information, and here nothing does).
PURPOSES: tuple[str, ...] = (
    "attack_d20",       # the d20 of an attack roll (incl. the adv/disadv pair)
    "attack_dice",      # rolled modifiers on attack_bonus (Bless's +1d4)
    "damage",           # damage pool + extra dice + rider dice
    "save_d20",         # the d20 of a saving throw (incl. an Indomitable reroll)
    "save_dice",        # rolled modifiers on the save stat
    "healing",          # in-combat healing dice (out-of-combat is mean-field)
    "policy",           # a policy's own per-combat pre-rolls
    "schedule",         # the day's combat times and short-rest placement
)

_PURPOSE_CODE: dict[str, int] = {p: i for i, p in enumerate(PURPOSES)}

#: The alignment epoch: which simulation coordinates enter the stream key, i.e.
#: where the streams re-synchronize.
#:
#:   ``"run"``        — ``()``.  §6.1's literal wording ("per entity or per
#:                      (entity, purpose)").  Streams never realign, so pairing
#:                      only survives on streams whose DRAW COUNT is unchanged.
#:   ``"day"``        — ``(day,)``.  Realign at the estimator's replication unit.
#:   ``"day_combat"`` — ``(day, combat)``.  Realign four times a day; this is
#:                      what §6.1's promise literally describes ("the enemy's
#:                      attack roll in round 3 of combat 2 draws the same value
#:                      no matter what changed about the character's spell").
ALIGNMENTS: tuple[str, ...] = ("run", "day", "day_combat")

#: The PINNED alignment.  Chosen by measurement, not by argument — see §6.3 and
#: the s60 decision record.  Changing it re-baselines every seeded number.
ALIGNMENT: str = "day"

#: The owner label for the day-structure stream, which belongs to no entity.
SCHEDULE_OWNER = "day"


def _owner_code(owner: str) -> int:
    """A stable 32-bit code for an owner label.

    ``zlib.crc32`` rather than ``hash()``: Python's string hash is randomized
    per process (PYTHONHASHSEED), so it would make a run's dice depend on the
    interpreter invocation — the same class of defect as keying on
    ``Entity.id``, and harder to notice because it only shows up across
    processes.
    """
    return zlib.crc32(owner.encode("utf-8"))


class SeededRNG:
    """Single controlled channel for all dice in a simulation run, routed into
    per-``(purpose, owner)`` substreams (§6.3).

    Parameters
    ----------
    seed:
        Integer seed.  Pass the same seed to replay a run identically.
        If None, numpy picks a random seed (non-reproducible — fine for
        exploratory runs, not for regression tests).  The resolved entropy is
        captured either way, so a single run's streams are mutually consistent
        even when the seed was not given.
    alignment:
        One of :data:`ALIGNMENTS`.  Defaults to the pinned :data:`ALIGNMENT`.
        A caller passes this only to MEASURE the alignment's effect; a run that
        reports numbers uses the pinned value, which is what provenance records.
    """

    def __init__(self, seed: int | None = None, *,
                 alignment: str | None = None) -> None:
        self.seed = seed
        self.alignment = ALIGNMENT if alignment is None else alignment
        if self.alignment not in ALIGNMENTS:
            raise ValueError(
                f"alignment must be one of {ALIGNMENTS}, got {self.alignment!r}"
            )
        # The RESOLVED entropy.  With seed=None, SeedSequence draws from the OS;
        # reading `.entropy` back pins it for the life of this object so every
        # substream of this run derives from one root even though the run is not
        # reproducible across invocations.
        root = np.random.SeedSequence(seed)
        self._entropy = root.entropy
        self._epoch: tuple[int, ...] = ()
        self._streams: dict[tuple[int, ...], np.random.Generator] = {}
        self._day_index = 0
        self._combat_index = 0
        log.info("SeededRNG initialised with seed=%s alignment=%s",
                 seed, self.alignment)

    # ------------------------------------------------------------------
    # The alignment epoch
    # ------------------------------------------------------------------

    def begin_day(self, day_index: int) -> None:
        """Enter day *day_index* (0-based).  Called by ``DayRunner.run_day``.

        Under ``"day"`` / ``"day_combat"`` alignment this re-synchronizes every
        stream: whatever diverged in the previous day cannot carry into this one.
        Under ``"run"`` alignment it only records the index.
        """
        self._day_index = day_index
        self._combat_index = 0
        self._refresh_epoch()

    def begin_combat(self, combat_index: int) -> None:
        """Enter combat *combat_index* (1-based) of the current day.

        Called by ``DayRunner.run_day``'s combat loop.  Under ``"day_combat"``
        alignment this re-synchronizes every stream at the combat boundary.
        """
        self._combat_index = combat_index
        self._refresh_epoch()

    def _refresh_epoch(self) -> None:
        if self.alignment == "run":
            epoch: tuple[int, ...] = ()
        elif self.alignment == "day":
            epoch = (self._day_index,)
        else:
            epoch = (self._day_index, self._combat_index)
        if epoch != self._epoch:
            # Streams of the old epoch are unreachable from here on (the epoch
            # only moves forward), so the cache is dropped rather than grown.
            # Under "run" alignment the epoch never changes, so this never
            # fires and the run's streams persist — which is exactly what that
            # alignment means.
            self._epoch = epoch
            self._streams.clear()

    # ------------------------------------------------------------------
    # Stream routing
    # ------------------------------------------------------------------

    def substream(self, purpose: str, owner: str) -> np.random.Generator:
        """The generator for ``(purpose, owner)`` in the current epoch.

        Derived from a ``spawn_key`` rather than from ``SeedSequence.spawn()``,
        so a stream's identity does not depend on the order streams were first
        touched.  Cached per epoch; the cache is a speed device only, and
        dropping it mid-epoch would change the run's dice.
        """
        code = _PURPOSE_CODE.get(purpose)
        if code is None:
            raise ValueError(
                f"Unknown dice purpose {purpose!r}. PURPOSES is CLOSED and has "
                f"no catch-all (see the module docstring); add the purpose "
                f"deliberately — it re-baselines every seeded number. "
                f"Known: {PURPOSES}"
            )
        key = (*self._epoch, code, _owner_code(owner))
        generator = self._streams.get(key)
        if generator is None:
            generator = np.random.default_rng(
                np.random.SeedSequence(entropy=self._entropy, spawn_key=key)
            )
            self._streams[key] = generator
        return generator

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def roll(self, n: int, sides: int, *, stream: tuple[str, str]) -> list[int]:
        """Roll *n* dice each with *sides* faces on *stream*.  Returns ints.

        ``stream`` is ``(purpose, owner)`` and is REQUIRED — there is no default
        stream, because a default is a catch-all and a catch-all re-couples
        whatever lands in it (see the module docstring).

        Examples
        --------
        >>> rng = SeededRNG(42)
        >>> rng.roll(1, 20, stream=("attack_d20", "War Angel"))   # one d20
        [some int 1-20]
        >>> rng.roll(2, 6, stream=("damage", "War Angel"))        # 2d6
        [int, int]
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        if sides < 2:
            raise ValueError(f"sides must be >= 2, got {sides}")
        purpose, owner = stream
        results = self.substream(purpose, owner).integers(
            1, sides + 1, size=n).tolist()
        log.debug("roll(%d, d%d) on %s/%s → %s", n, sides, purpose, owner,
                  results)
        return results

    def roll_one(self, sides: int, *, stream: tuple[str, str]) -> int:
        """Convenience wrapper: roll a single die, return a scalar int."""
        return self.roll(1, sides, stream=stream)[0]

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    def describe(self) -> dict[str, object]:
        """The §4 provenance block for the dice channel.

        The alignment is recorded because it CHANGES THE NUMBERS: two runs at
        the same seed and different alignments are different runs, and a reader
        comparing them without knowing that would be comparing two streams.
        """
        return {
            "seed": self.seed,
            "alignment": self.alignment,
            "purposes": list(PURPOSES),
        }
