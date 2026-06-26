"""
telemetry.py — CombatTelemetry: the structured output seam (design/enemy_model.md §13).

The model's INPUT is the frozen per-band table (``monster_profile_by_band.csv``, §8);
this is its OUTPUT seam. Today the only structured outputs are the damage ledgers on
``CombatResult`` / ``DayResult``; *everything else* a build's resilience depends on
(saves forced/failed by type, control uptime, typed-damage mitigated, slots/parry/
concentration budget) was audited by reaching into resource pools and policy internals
from tests. ``CombatTelemetry`` gives those quantities ONE structured home.

Shape — a typed accumulator with a small CLOSED channel vocabulary (the §13 decision;
mirrors the project's "closed verb set" + "table is the source of truth" philosophy —
NOT a free-form ``record(channel, key, value)`` sink, and NOT ad-hoc flat fields that
churn the result dataclass per metric). The four fixed channels (extend deliberately,
like adding a verb — not casually):

  - **saves** — saves forced / passed / failed, keyed by ``(ability, channel)`` where
    ``channel`` is ``"damage"`` or ``"control"``. The §4b cross-axis split is VISIBLE
    here: a bundled (``also_damages``) ability records a save in BOTH channels, so the
    double-save is interpretable, not hidden.
  - **control** — turns lost (hard) and turns reduced (soft), by save ability (§6).
    Scaffolded now; populated when the §6 control channel wires (roadmap step 5).
  - **mitigation** — outgoing damage before vs after ``mult(t)`` and incoming by type
    (§5). Scaffolded now; populated when the §5 multiplier wires (roadmap step 4).
  - **economy** — concentration checks forced / broken, reactions used, resources spent
    (folds the existing slot-audit / parry-budget / concentration-count monkeypatches).

Who writes it — RESOLUTION only, never policy (preserves CLAUDE.md #7). The scheduler /
verb handlers record outcomes as they roll dice and mutate state; the policy stays a pure
read. Recording is pure observation — it never changes a die or an outcome, so adding a
channel cannot move a DPR baseline. (In the verbs the telemetry sink is an OPTIONAL
trailing argument defaulting to ``None``; a direct caller that passes nothing gets the
exact prior behavior, which is why wiring this is byte-identical.)

Granularity — typed aggregate counters / distributions per combat, summed across the day
(matching §1's mean-field, low-variance values), NOT a per-event log. ``CombatTelemetry``
is carried on ``CombatResult`` and aggregated onto ``DayResult`` exactly like the damage
ledgers, via ``merge``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The closed save-channel vocabulary (§13 / §4b): a damaging save vs a control save.
SAVE_CHANNELS = ("damage", "control")


@dataclass
class SaveTally:
    """One ``(ability, channel)`` cell of the saves channel."""
    forced: int = 0
    passed: int = 0
    failed: int = 0

    def add(self, passed: bool) -> None:
        self.forced += 1
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def merge(self, other: "SaveTally") -> None:
        self.forced += other.forced
        self.passed += other.passed
        self.failed += other.failed


@dataclass
class ControlTally:
    """One save-ability cell of the control channel (§6). ``turns_lost`` is the HARD
    branch (output 0), ``turns_reduced`` the SOFT branch (output × ``soft_factor``),
    both as EXPECTED affected turns (§6 step 5's closed-form duration). Scaffolded
    until the §6 channel wires (roadmap step 5)."""
    failures: int = 0
    turns_lost: float = 0.0
    turns_reduced: float = 0.0

    def merge(self, other: "ControlTally") -> None:
        self.failures += other.failures
        self.turns_lost += other.turns_lost
        self.turns_reduced += other.turns_reduced


@dataclass
class MitigationTally:
    """One damage-type cell of the mitigation channel (§5): the build's OUTGOING
    damage of this type before vs after the enemy's fractional ``mult(t)`` (the
    typed-damage-mitigated figure), and INCOMING damage of this type taken by the
    character. Scaffolded until the §5 multiplier wires (roadmap step 4)."""
    outgoing_before: int = 0
    outgoing_after: int = 0
    incoming: int = 0

    def merge(self, other: "MitigationTally") -> None:
        self.outgoing_before += other.outgoing_before
        self.outgoing_after += other.outgoing_after
        self.incoming += other.incoming


@dataclass
class CombatTelemetry:
    """The structured output accumulator for ONE combat (§13). Resolution records into
    it; ``DayResult`` sums combats via ``merge``. All channels default empty, so a
    combat that triggers none of them carries an inert telemetry object."""

    # saves: (ability, channel) -> SaveTally
    saves: dict[tuple[str, str], SaveTally] = field(default_factory=dict)
    # control: save ability -> ControlTally
    control: dict[str, ControlTally] = field(default_factory=dict)
    # mitigation: damage type -> MitigationTally
    mitigation: dict[str, MitigationTally] = field(default_factory=dict)
    # economy
    concentration_checks: int = 0
    concentration_breaks: int = 0
    reactions_used: int = 0
    resources_spent: dict[str, int] = field(default_factory=dict)

    # -- record methods (the only way resolution writes; closed vocabulary) -------

    def record_save(self, ability: str, channel: str, passed: bool) -> None:
        """Record one forced save and its outcome. ``channel`` ∈ ``SAVE_CHANNELS``."""
        if channel not in SAVE_CHANNELS:
            raise ValueError(f"unknown save channel {channel!r}; expected {SAVE_CHANNELS}")
        self.saves.setdefault((ability, channel), SaveTally()).add(passed)

    def record_concentration(self, broke: bool) -> None:
        """Record one concentration check forced by incoming damage (economy)."""
        self.concentration_checks += 1
        if broke:
            self.concentration_breaks += 1

    def record_control(self, ability: str, *, turns_lost: float = 0.0,
                       turns_reduced: float = 0.0) -> None:
        """Record one FAILED control save's cost (§6); for roadmap step 5."""
        t = self.control.setdefault(ability, ControlTally())
        t.failures += 1
        t.turns_lost += turns_lost
        t.turns_reduced += turns_reduced

    def record_mitigation(self, damage_type: str, *, outgoing_before: int = 0,
                         outgoing_after: int = 0, incoming: int = 0) -> None:
        """Record typed outgoing (before/after ``mult(t)``) or incoming damage (§5);
        for roadmap step 4."""
        m = self.mitigation.setdefault(damage_type, MitigationTally())
        m.outgoing_before += outgoing_before
        m.outgoing_after += outgoing_after
        m.incoming += incoming

    def record_reaction(self) -> None:
        self.reactions_used += 1

    def record_resource(self, name: str, amount: int = 1) -> None:
        self.resources_spent[name] = self.resources_spent.get(name, 0) + amount

    # -- aggregation (DayResult sums combats, like the damage ledgers) -----------

    def merge(self, other: "CombatTelemetry") -> None:
        """Fold ``other`` into self (used to aggregate combats onto the day)."""
        for key, tally in other.saves.items():
            self.saves.setdefault(key, SaveTally()).merge(tally)
        for key, ct in other.control.items():
            self.control.setdefault(key, ControlTally()).merge(ct)
        for key, mt in other.mitigation.items():
            self.mitigation.setdefault(key, MitigationTally()).merge(mt)
        self.concentration_checks += other.concentration_checks
        self.concentration_breaks += other.concentration_breaks
        self.reactions_used += other.reactions_used
        for name, amount in other.resources_spent.items():
            self.resources_spent[name] = self.resources_spent.get(name, 0) + amount

    # -- convenience read-outs (the reporting layer / mechanism tests read these) -

    def saves_forced(self, channel: str | None = None) -> int:
        """Total saves forced, optionally filtered to one channel."""
        return sum(t.forced for (_ab, ch), t in self.saves.items()
                   if channel is None or ch == channel)

    def saves_failed(self, channel: str | None = None) -> int:
        return sum(t.failed for (_ab, ch), t in self.saves.items()
                   if channel is None or ch == channel)
