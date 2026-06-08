"""
rng.py — Seeded RNG, the single dice channel for the entire simulation.

All dice rolls everywhere must go through SeededRNG.roll().  Nothing in the
engine calls random directly.  This guarantees:
  - Any run can be exactly reproduced by re-using the seed.
  - The seed is always logged so replays are possible.
  - We can swap the underlying generator later without touching call sites.
"""

import logging
from typing import Sequence

import numpy as np

log = logging.getLogger(__name__)


class SeededRNG:
    """Single controlled channel for all dice in a simulation run.

    Parameters
    ----------
    seed:
        Integer seed.  Pass the same seed to replay a run identically.
        If None, numpy picks a random seed (non-reproducible — fine for
        exploratory runs, not for regression tests).
    """

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed
        self._rng = np.random.default_rng(seed)
        log.info("SeededRNG initialised with seed=%s", seed)

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def roll(self, n: int, sides: int) -> list[int]:
        """Roll *n* dice each with *sides* faces.  Returns a list of ints.

        Examples
        --------
        >>> rng = SeededRNG(42)
        >>> rng.roll(1, 20)   # one d20
        [some int 1-20]
        >>> rng.roll(2, 6)    # 2d6
        [int, int]
        """
        if n < 1:
            raise ValueError(f"n must be >= 1, got {n}")
        if sides < 2:
            raise ValueError(f"sides must be >= 2, got {sides}")
        results = self._rng.integers(1, sides + 1, size=n).tolist()
        log.debug("roll(%d, d%d) → %s", n, sides, results)
        return results

    def roll_one(self, sides: int) -> int:
        """Convenience wrapper: roll a single die, return a scalar int."""
        return self.roll(1, sides)[0]
