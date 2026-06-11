"""
validation.py — Monte Carlo DPR validation harness.

Runs a build for many adventuring days and reports mean damage-per-round (DPR)
against the build guide's target.  DPR is defined exactly as the prototype does:

    DPR = total damage dealt across the day / total rounds in the day
        = total damage / (4 combats * rounds_per_combat)

For the War Angel only the character deals damage, so total damage dealt equals
total damage received by the dummy — we read it straight off DayResult.

Validation framing (PROGRESS.md):
  - Levels 1–4: EXACT target match expected (simple attack math).
  - Levels 5+: SOFT (±10%) — the prototype is a compass, not ground truth.

Usage (from repo root):
    python -m src.validation            # validate all implemented levels
    python -m src.validation 1          # just level 1
    python -m src.validation 1 --days 200000 --seed 7
"""

from __future__ import annotations

import argparse
import logging
import math
from dataclasses import dataclass

from .builds import war_angel
from .rng import SeededRNG


@dataclass
class ValidationResult:
    level: int
    n_days: int
    rounds_per_day: int
    mean_dpr: float
    stderr: float            # standard error of the mean DPR
    target_dpr: float
    exact: bool              # True if this level expects an exact match

    @property
    def delta(self) -> float:
        return self.mean_dpr - self.target_dpr

    @property
    def pct_error(self) -> float:
        if self.target_dpr == 0:
            return float("nan")
        return 100.0 * self.delta / self.target_dpr

    def summary(self) -> str:
        kind = "exact" if self.exact else "soft ±10%"
        # 95% CI half-width on the mean.
        ci = 1.96 * self.stderr
        return (
            f"L{self.level:>2}  DPR {self.mean_dpr:6.3f} ± {ci:.3f}  "
            f"(target {self.target_dpr:5.2f}, {kind})  "
            f"diff {self.delta:+.3f} ({self.pct_error:+.1f}%)  "
            f"[{self.n_days} days]"
        )


def run_level(level: int, n_days: int, seed: int, rounds_per_combat: int = 4) -> ValidationResult:
    """Simulate `n_days` adventuring days at `level`; return DPR statistics."""
    rng = SeededRNG(seed)
    rounds_per_day = 4 * rounds_per_combat

    # Persistent entities + policy across the whole run.  A long rest at the
    # start of each day resets everything, so reuse is safe and faster.
    runner, char, dummy = war_angel.make_day_runner(level, rng, rounds_per_combat)

    # Welford-free: collect per-day DPR, then mean/stderr.  n_days is modest
    # enough that holding the list is fine, and it keeps the math obvious.
    # DPR = the CHARACTER's output = damage dealt to the dummy.  Through L12 this
    # equals total_damage; from L13 the enemy strikes back, so we must read the
    # dummy's received-damage column rather than the all-sources total.
    day_dprs: list[float] = []
    for _ in range(n_days):
        result = runner.run_day()
        day_dprs.append(result.damage_received_by(dummy.id) / rounds_per_day)

    n = len(day_dprs)
    mean = sum(day_dprs) / n
    var = sum((x - mean) ** 2 for x in day_dprs) / (n - 1) if n > 1 else 0.0
    stderr = math.sqrt(var / n) if n > 1 else 0.0

    return ValidationResult(
        level=level,
        n_days=n,
        rounds_per_day=rounds_per_day,
        mean_dpr=mean,
        stderr=stderr,
        target_dpr=war_angel.LEVELS[level]["target_dpr"],
        exact=(level <= war_angel.EXACT_MATCH_MAX_LEVEL),
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="War Angel DPR validation.")
    parser.add_argument("level", nargs="?", type=int, default=None,
                        help="Level to validate (default: all implemented).")
    parser.add_argument("--days", type=int, default=50_000,
                        help="Adventuring days to simulate (default 50000).")
    parser.add_argument("--seed", type=int, default=0, help="RNG seed.")
    args = parser.parse_args(argv)

    # Silence the engine's per-event logging — it dominates runtime in a
    # large Monte Carlo sweep and we only want the summary lines here.
    logging.disable(logging.CRITICAL)

    levels = [args.level] if args.level is not None else sorted(war_angel.LEVELS)
    for level in levels:
        result = run_level(level, n_days=args.days, seed=args.seed)
        print(result.summary())


if __name__ == "__main__":
    main()
