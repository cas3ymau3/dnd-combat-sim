"""
control.py — the affected-turns ACCOUNT (design/evaluation_framework.md §7).

Control is priced at RUNTIME, not post-hoc.  `enemy_model.md` §6 computes, on each
failed control save, a closed-form EXPECTED number of affected turns, split HARD
(the turn is wasted) vs SOFT (the turn happens at reduced effect).  Until this
module existed that number was only RECORDED: the §13 control channel carried it
and the reporting layer was supposed to convert it into a DPR delta by multiplying
the build's raw output by `(1 − lost_fraction)`.

§7.1 says why that is wrong, and both reasons are about what a multiplier cannot
see.  It assumes **every turn is worth the same** (losing the nova turn is not
losing a cantrip turn), and it **spends the resources of a turn that never
happened** (a genuinely lost turn should leave the slot available for later).  So
the same closed-form quantity is applied instead: credited into an account here,
and drawn down by the scheduler at the controlled entity's own turn boundary.

WHAT THIS IS NOT
----------------
This is **not** the stateful control engine.  There is no condition object, no
per-turn save-ends re-roll, and no rolled duration — that remains the
`enemy_model.md` §10 fidelity deferral.  Nothing here draws a die (the per-feature
ritual's step 3): the account is a deterministic function of control saves that
were already being rolled, which is what keeps the model low-variance per §1 of the
enemy model.

It is also not a status.  A status is a flag that expires at a tick; this is a
BALANCE that is spent.  Mixing the two would mean the scheduler's status sweep
could silently cancel a cost that had already been priced.

THE TWO SHARES MIX — THEY DO NOT COMPOSE (§7.5)
-----------------------------------------------
`hard_frac` is the probability that the condition which landed is a hard one, so
ONE failed save credits `hard_frac · E[turns]` to `lost` and
`(1 − hard_frac) · E[turns]` to `reduced`.  Those are the two branches of one
effect, so on any given turn they are shares OF THAT TURN:

    scale = 0·h + soft_factor·r + 1·(1 − h − r)
          = 1 − h − r·(1 − soft_factor)

The natural first draft — treat them as independent factors, `(1 − h) × soft` — is
wrong, not merely different.  At `h = r = 0.5, soft_factor = 0.5` it gives
`0.5 × 0.75 = 0.375`, where the branches give `0.5·0 + 0.5·0.5 = 0.25` directly.

HARD IS DRAWN FIRST, AND THAT IS A DECISION (§7.5)
--------------------------------------------------
Drawing hard to exhaustion before soft, versus drawing both in proportion, gives
**the same expected output** — `scale` is linear in the two shares.  They differ in
exactly one place, and it is the place §7.1.2 exists for: only a turn whose hard
share is the WHOLE turn can skip `decide()` and preserve its resources.  A
proportional draw never produces such a turn, so it would average the
resource-preservation property away while reporting an identical DPR — the post-hoc
multiplier's own defect, reintroduced inside the runtime path where nothing would
see it.  Hard-first is the rule BECAUSE the two readings are numerically
indistinguishable and only one of them keeps the mechanism.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: Below this, a share is treated as zero.  Floating-point draw-down leaves
#: residues like 1.1e-16 that would otherwise make a turn "partially suppressed"
#: forever and report an output scale of 0.9999999999999999.
EPSILON = 1e-9


@dataclass(frozen=True)
class TurnControl:
    """What control costs ONE turn — the verdict a draw-down returns.

    Attributes
    ----------
    suppressed:
        The whole turn is gone: the entity does not decide, spends no action
        economy and spends no resources (§7.1.2).  True only when the HARD share
        is the entire turn.
    scale:
        The factor this turn's damage output is multiplied by (``1.0`` = untouched,
        ``0.0`` = suppressed).  Read by ``resolve_damage`` phase 5b off
        ``Entity.output_scale``.
    lost_applied:
        The hard share actually drawn this turn, in turn-units.  This is the
        REALIZED cost — the §7.6 counterpart of the credited
        ``ControlTally.turns_lost``.
    reduced_applied:
        The soft share actually drawn this turn, in turn-units.
    """

    suppressed: bool = False
    scale: float = 1.0
    lost_applied: float = 0.0
    reduced_applied: float = 0.0

    @property
    def affected(self) -> bool:
        """True when control touched this turn at all — the cheap guard that keeps
        an uncontrolled run from paying for any of this."""
        return self.lost_applied > 0.0 or self.reduced_applied > 0.0


#: The verdict for a turn nothing has controlled.  A single shared instance because
#: it is frozen and it is the answer on the overwhelming majority of turns.
UNAFFECTED = TurnControl()


@dataclass
class ControlAccount:
    """A per-entity balance of EXPECTED affected turns, in turn-units.

    Credited by ``verbs.resolve_control_save`` on each failed control save; drawn
    down by ``Scheduler._handle_turn_start`` at the entity's own turn boundary.
    Zero on every entity unless the enemy's §6 control channel is switched on
    (``enemy_options={'control': True}``), so this is inert — and therefore
    baseline-preserving — on every pre-existing run.

    Cleared at the combat boundary by ``DayRunner._run_combat``, beside
    ``StatusSet.clear()`` and for the same reason: a fresh ``Scheduler`` per combat
    restarts the round counter, so a balance carried across the boundary would be
    spent against a combat that never earned it.
    """

    #: Hard control owed: turns to be lost outright.
    lost: float = 0.0
    #: Soft control owed: turns to be spent at :attr:`soft_factor` output.
    reduced: float = 0.0
    #: How many FUTURE turns this entity will take in the current combat — the
    #: ceiling on what any control can cost it.  Maintained by the scheduler, which is
    #: the only thing that knows the turn order (CLAUDE.md #7 keeps that out of a
    #: policy), and read by :meth:`room` at credit time.  Entities that take no turns
    #: at all — a COMMANDED summon, which acts on its controller's turn via
    #: ``Choice.actor`` and has no ``TurnStartEvent`` of its own — sit at 0 and are
    #: therefore credited nothing, which is the honest number rather than a credit
    #: that could never be spent.
    turns_remaining: int = 0
    #: The output fraction a soft turn retains, ROUTED here from the policy that
    #: forced the save (``ControlSpec.soft_factor`` → ``ControlSaveEvent`` → here)
    #: rather than defaulted locally.  There is exactly one source for this number —
    #: the enemy policy's resolved knob, ``enemy_stats.SOFT_FACTOR`` unless a config
    #: overrode it — and a second default declared next to the applying code would be
    #: the same quantity in two places, identical today for a reason that stops
    #: holding the moment anybody retunes the constant.  ``None`` means nothing has
    #: credited a soft turn, in which case the soft term is zero anyway.
    soft_factor: "float | None" = None

    def credit(self, *, lost: float = 0.0, reduced: float = 0.0,
               soft_factor: "float | None" = None) -> None:
        """Add one failed control save's expected cost to the balance.

        ``soft_factor`` is optional HERE and checked in :meth:`draw` instead, which is
        where it is used: crediting a soft turn-unit is meaningful on its own (it is
        what the §13 credited channel reports), and only pricing one needs the factor.
        Putting the check at the point of use also means a caller that merely records
        the enemy's pressure — which is every direct unit test of the credit — does not
        have to supply a number it never consumes.

        Last write wins if two policies ever disagree, a configuration that cannot
        arise today (one enemy, one policy); recorded rather than guarded.
        """
        self.lost += lost
        self.reduced += reduced
        if soft_factor is not None:
            self.soft_factor = soft_factor

    @property
    def room(self) -> float:
        """Turn-units this entity could still lose — its remaining turns minus what it
        already owes (``evaluation_framework.md`` §7.6).

        **This is why overlapping control cannot be double-counted.**  Two effects that
        each last "the rest of the fight" do not cost twice the rest of the fight; they
        cost it once.  Before the cap read this, each was credited its own full
        duration, so the credited channel over-reported whenever two controls
        overlapped — a defect that was invisible while nothing drew the account down.
        """
        return max(0.0, self.turns_remaining - self.pending)

    @property
    def pending(self) -> float:
        """Total turn-units owed — what a combat-end clear would discard (§7.6)."""
        return self.lost + self.reduced

    def clear(self) -> None:
        """Drop the whole balance (the combat boundary).

        ``soft_factor`` is deliberately NOT cleared: it is a property of the enemy
        that was configured, not of the combat, and re-crediting sets it anyway.
        ``turns_remaining`` is not cleared either — the scheduler sets it for the new
        combat, and zeroing it here would make a credit arriving before the first turn
        boundary saturate to nothing.
        """
        self.lost = 0.0
        self.reduced = 0.0

    def draw(self, soft_factor: "float | None" = None) -> TurnControl:
        """Spend up to one turn-unit of the balance and return the turn's verdict.

        HARD FIRST (§7.5), then soft, then the remainder of the turn acts at full
        output.  Mutates the balance: this is the draw-down, so calling it twice for
        one turn would charge that turn twice.  Called exactly once per
        ``TurnStartEvent``, by the scheduler.

        ``soft_factor`` defaults to the routed :attr:`soft_factor`; passing it
        explicitly is for testing the arithmetic in isolation.
        """
        if self.lost <= EPSILON and self.reduced <= EPSILON:
            return UNAFFECTED

        if soft_factor is None:
            soft_factor = self.soft_factor
        if soft_factor is None:
            if self.reduced > EPSILON:
                raise ValueError(
                    "cannot price a SOFT control turn without a soft_factor: route "
                    "it from the policy that forced the save (ControlSpec.soft_factor "
                    "→ ControlSaveEvent.soft_factor → ControlAccount.credit). The "
                    "applying code deliberately declares no default of its own, "
                    "because a second copy of this constant is the same quantity in "
                    "two places (evaluation_framework.md §7.2)."
                )
            # Hard-only balance: the soft term is multiplied by a zero share, so any
            # value is equivalent here and none is a guess about a cost.
            soft_factor = 1.0

        h = min(self.lost, 1.0)
        self.lost -= h
        if self.lost <= EPSILON:
            self.lost = 0.0

        r = min(self.reduced, 1.0 - h)
        if r <= EPSILON:
            r = 0.0
        else:
            self.reduced -= r
            if self.reduced <= EPSILON:
                self.reduced = 0.0

        # The mixture, not the product (§7.5).  Clamped because soft_factor is
        # declared in [0, 1] but is a config value, and a scale outside [0, 1]
        # would silently turn a debuff into a buff.
        scale = 1.0 - h - r * (1.0 - soft_factor)
        scale = max(0.0, min(1.0, scale))
        suppressed = h >= 1.0 - EPSILON
        if suppressed:
            # A fully suppressed turn has no output to scale, and saying so
            # explicitly keeps the two facts from being able to disagree.
            scale = 0.0
        return TurnControl(suppressed=suppressed, scale=scale,
                           lost_applied=h, reduced_applied=r)
