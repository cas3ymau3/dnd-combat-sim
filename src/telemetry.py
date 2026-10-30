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
churn the result dataclass per metric). The six fixed channels (extend deliberately,
like adding a verb — not casually; `healing` was the s45 addition and `attacks` the
s49 one):

  - **saves** — saves forced / passed / failed, keyed by ``(ability, channel)`` where
    ``channel`` is ``"damage"`` or ``"control"``. The §4b cross-axis split is VISIBLE
    here: a bundled (``also_damages``) ability records a save in BOTH channels, so the
    double-save is interpretable, not hidden.
  - **control** — TWO halves, because since control is applied at runtime they are two
    quantities rather than one (``evaluation_framework.md`` §7.6). The CREDITED half
    (``control``) is the enemy's pressure: expected turns lost (hard) and reduced
    (soft) at the moment a save fails, by save ability (§6). The REALIZED half
    (``control_applied``) is the character's cost: turn-units actually drawn out of its
    ``ControlAccount`` at its own turn boundaries, by ACTOR — the key that answers
    "whose turns were lost".
  - **mitigation** — outgoing damage before vs after ``mult(t)`` and incoming by type
    (§5), keyed ``(actor_id, damage_type)``. The ACTOR dimension was added in s44: the
    cells answer two questions — "what did the enemy's resistances remove from this
    build's output" (§5) and "what is this build's outgoing damage-type COMPOSITION"
    — and the second is meaningless without knowing WHOSE damage a cell holds. On a
    roster with a summon and a typed-damage enemy, a type-only key silently pools all
    three actors' damage into one number.
  - **healing** — hit points RESTORED, keyed ``(source_id, target_id, context)``
    where context is ``"combat"`` or ``"between"`` (design/healing.md §9.2). Source
    attribution is not optional: "healing provided by the summon" is a stated
    requirement, and an aggregate ledger would pool the character's and the summon's
    numbers exactly as the s44 per-metric lesson warned. The CONTEXT dimension is
    the §11.1 survey's finding — healing under fire is a different quantity from
    healing at leisure, and the corpus does most of its healing out of combat by
    preference, so pooling the two into one per-round number would mislead. Records
    the amount ACTUALLY APPLIED, never the amount rolled.
  - **attacks** — attack rolls made / hit / crit / at advantage / at disadvantage,
    keyed by ``actor_id`` (evaluation_framework.md §8.1, the s49 addition). Hits and
    crits were computed in ``resolve_attack_roll`` and thrown away; this keeps them,
    and unlocks §8's hit % / crit % / advantage %. The ACTOR key is not optional and
    the reason is sharper than it was for mitigation: a pooled AMOUNT still adds up,
    but a pooled RATE does not — one ledger holding the character's swings, a summon's
    and the ENEMY's gives a hit % that is a roll-weighted average over three different
    to-hit profiles and describes none of them. Recorded at the FINAL outcome, after
    the in-flight intercept block, so the attacks ledger can never disagree with the
    damage ledger: a recorded hit always has a ``DamageEvent`` behind it (a
    Guided-Strike rescue is a hit, a parried hit is a miss, a Protection re-roll can
    un-crit). ``disadvantage`` is recorded but has no registered metric today — it
    makes the stance a true three-way partition, which is a testable invariant, while
    no shipped build imposes disadvantage on its own attacks.
  - **economy** — concentration checks forced / broken, reactions used, resources spent
    (folds the existing slot-audit / parry-budget / concentration-count monkeypatches).
    The resource ledger went LIVE in s44: the scheduler records at every
    ``resources.consume`` site (the six decider closures plus the main choice loop), so
    "limited resources per day" (design.md §8) is measurable for every build. Keyed by
    resource NAME and summed across entities — per-entity keying would be a deliberate
    channel extension, not a free change.

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

# The closed healing-context vocabulary (design/healing.md §11.1 / §10.4): healing
# resolved INSIDE a combat vs applied in a between-combat interval (Prayer of
# Healing, Hit Dice at the short rest).  Kept as a key dimension rather than two
# fields so the read-outs filter uniformly.
HEAL_CONTEXTS = ("combat", "between")


# The closed attack-roll PROPERTY vocabulary the metrics layer keys on
# (evaluation_framework.md §8.1).  Deliberately a SUBSET of what ``AttackTally``
# records: ``disadvantage`` is tallied but not registered, because no shipped build
# imposes disadvantage on its own attacks.  These are attribute names on
# ``AttackTally``, so a metric reads a cell with ``getattr`` — the same idiom
# ``SaveTally`` already serves with ``outcome=``.
#
# NOTE these cells are NOT disjoint: a crit is also a hit, and advantage is a
# condition of the roll rather than an outcome of it.  That is why the breakdown over
# them declares ``sum_rule = cells_overlap_do_not_sum`` (§8.1).
ATTACK_PROPERTIES = ("hit", "crit", "advantage")


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
    """One save-ability cell of the CREDITED half of the control channel (§6).

    ``turns_lost`` is the HARD branch (output 0), ``turns_reduced`` the SOFT branch
    (output × ``soft_factor``), both as EXPECTED affected turns (§6 step 5's
    closed-form duration), as computed at the moment the save fails.

    **This is the ENEMY's PRESSURE, not the character's cost** — the two are
    different quantities since control began being applied at runtime
    (``evaluation_framework.md`` §7.6).  What was actually spent is the ACTOR-keyed
    :class:`ControlAppliedTally` below.  Two structural reasons they cannot agree:
    a control landing in the closing round of a fixed-length combat is credited and
    can never be drawn down, and the credit's cap counts the current round even
    though the enemy acts after the character.  Neither value moved when §7 landed;
    the realized half was added beside it."""
    failures: int = 0
    turns_lost: float = 0.0
    turns_reduced: float = 0.0

    def merge(self, other: "ControlTally") -> None:
        self.failures += other.failures
        self.turns_lost += other.turns_lost
        self.turns_reduced += other.turns_reduced


@dataclass
class ControlAppliedTally:
    """One ACTOR's cell of the REALIZED half of the control channel (§7.6).

    What control actually COST this entity: turn-units drawn out of its
    :class:`~src.control.ControlAccount` at its own turn boundaries, and how many
    of those draws took the whole turn.  Written by the scheduler, which is the
    only place that knows a turn happened.

    Keyed by ACTOR where the credited half is keyed by save ABILITY, and that
    asymmetry is deliberate: the realized question is "whose turns were lost",
    which is the per-METRIC ritual's roster-scoping check.  The credited half
    cannot answer it — with the enemy focused on a summon
    (``enemy_options={'focus': 'summon'}``) its rows pool the summon's lost turns
    with the character's, while these rows separate them.

    ``suppressed_turns`` is a COUNT of whole turns skipped, so it is the one cell
    here that is not in turn-units; it is also the only one with the resource
    preservation property (§7.1.2), which is why it is worth counting separately
    from ``turns_lost`` rather than inferred from it.
    """
    turns_lost: float = 0.0
    turns_reduced: float = 0.0
    suppressed_turns: int = 0
    affected_turns: int = 0

    def add(self, *, turns_lost: float, turns_reduced: float,
            suppressed: bool) -> None:
        self.turns_lost += turns_lost
        self.turns_reduced += turns_reduced
        self.affected_turns += 1
        if suppressed:
            self.suppressed_turns += 1

    def merge(self, other: "ControlAppliedTally") -> None:
        self.turns_lost += other.turns_lost
        self.turns_reduced += other.turns_reduced
        self.suppressed_turns += other.suppressed_turns
        self.affected_turns += other.affected_turns


@dataclass
class MitigationTally:
    """One damage-type cell of the mitigation channel (§5): the build's OUTGOING
    damage of this type before vs after the enemy's fractional ``mult(t)`` (the
    typed-damage-mitigated figure), and INCOMING damage of this type taken by the
    character.

    Recorded for EVERY typed hit since s44, not only hits a multiplier touched.
    With no profile installed ``outgoing_before == outgoing_after``, and the cell is
    then the build's outgoing damage-type COMPOSITION rather than a mitigation
    figure — the same numbers answering a different question, which is why one
    channel serves both."""
    outgoing_before: int = 0
    outgoing_after: int = 0
    incoming: int = 0

    def merge(self, other: "MitigationTally") -> None:
        self.outgoing_before += other.outgoing_before
        self.outgoing_after += other.outgoing_after
        self.incoming += other.incoming


@dataclass
class HealingTally:
    """One ``(source, target, context)`` cell of the healing channel."""
    healed: float = 0.0
    events: int = 0

    def merge(self, other: "HealingTally") -> None:
        self.healed += other.healed
        self.events += other.events


@dataclass
class AttackTally:
    """One ACTOR's cell of the attacks channel (§8.1).

    ``forced`` is attack rolls MADE (the denominator every rate here divides by);
    the rest are counts of rolls carrying each property.  The field names are the
    metrics layer's :data:`ATTACK_PROPERTIES` so a cell is read by ``getattr``.

    Two things the field list encodes rather than comments:

    * ``crit <= hit`` ALWAYS.  A crit that the defender's in-flight intercept flips
      to a miss is neither, which is the whole reason the record happens at the end
      of resolution rather than at the roll.
    * ``advantage + disadvantage + flat == forced``, with ``flat`` implicit.  The
      stance is the EFFECTIVE one after 2024 cancellation (``roll_d20``'s rule), so
      a roll with sources on both sides is flat, not both.  This partition is a
      self-consistency invariant a test asserts — it is how a miswired record call
      gets caught.
    """
    forced: int = 0
    hit: int = 0
    crit: int = 0
    advantage: int = 0
    disadvantage: int = 0

    def add(self, *, hit: bool, crit: bool,
            advantage: bool = False, disadvantage: bool = False) -> None:
        self.forced += 1
        if hit:
            self.hit += 1
            if crit:
                self.crit += 1
        if advantage:
            self.advantage += 1
        if disadvantage:
            self.disadvantage += 1

    def merge(self, other: "AttackTally") -> None:
        self.forced += other.forced
        self.hit += other.hit
        self.crit += other.crit
        self.advantage += other.advantage
        self.disadvantage += other.disadvantage


@dataclass
class CombatTelemetry:
    """The structured output accumulator for ONE combat (§13). Resolution records into
    it; ``DayResult`` sums combats via ``merge``. All channels default empty, so a
    combat that triggers none of them carries an inert telemetry object."""

    # saves: (ability, channel) -> SaveTally
    saves: dict[tuple[str, str], SaveTally] = field(default_factory=dict)
    # control, CREDITED half: save ability -> ControlTally
    control: dict[str, ControlTally] = field(default_factory=dict)
    # control, REALIZED half (§7.6): actor id -> ControlAppliedTally
    control_applied: dict[int, ControlAppliedTally] = field(default_factory=dict)
    # mitigation: (actor id, damage type) -> MitigationTally
    mitigation: dict[tuple[int, str], MitigationTally] = field(default_factory=dict)
    # healing: (source id, target id, context) -> HealingTally
    healing: dict[tuple[int, int, str], HealingTally] = field(default_factory=dict)
    # attacks: actor id -> AttackTally
    attacks: dict[int, AttackTally] = field(default_factory=dict)
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

    def record_control_applied(self, actor_id: int, *, turns_lost: float,
                               turns_reduced: float, suppressed: bool) -> None:
        """Record what control actually COST *actor* on ONE of its turns (§7.6).

        Written by ``Scheduler._handle_turn_start`` immediately after the account is
        drawn down, from the verdict it already holds — so the call draws nothing
        and cannot move a baseline (the per-feature ritual's step 3).  Called only
        on a turn control actually touched, so an uncontrolled run leaves this
        channel empty rather than filling it with zeros.
        """
        self.control_applied.setdefault(actor_id, ControlAppliedTally()).add(
            turns_lost=turns_lost, turns_reduced=turns_reduced,
            suppressed=suppressed)

    def record_mitigation(self, actor_id: int, damage_type: str, *,
                         outgoing_before: int = 0, outgoing_after: int = 0,
                         incoming: int = 0) -> None:
        """Record typed outgoing (before/after ``mult(t)``) or incoming damage (§5).

        Written by ``resolve_damage`` phase 7b on every TYPED hit — with a profile
        installed the before/after pair prices the enemy's resistances; without one
        it records the dealer's damage-type composition.  ``actor_id`` is WHO dealt
        it, without which a roster's cells cannot be told apart."""
        m = self.mitigation.setdefault((actor_id, damage_type), MitigationTally())
        m.outgoing_before += outgoing_before
        m.outgoing_after += outgoing_after
        m.incoming += incoming

    def record_healing(self, source_id: int, target_id: int, amount: float,
                       context: str = "combat") -> None:
        """Record hit points ACTUALLY RESTORED by *source* to *target*.

        Written by RESOLUTION only (``healing.resolve_healing`` and the two Hit
        Dice rules), never by a policy — a policy asks for a heal, it does not
        record one (CLAUDE.md #7).  Recording is pure observation and cannot move
        a die or an outcome, which is why the channel adds no baseline drift."""
        if context not in HEAL_CONTEXTS:
            raise ValueError(f"unknown heal context {context!r}; expected {HEAL_CONTEXTS}")
        cell = self.healing.setdefault((source_id, target_id, context), HealingTally())
        cell.healed += amount
        cell.events += 1

    def record_attack(self, actor_id: int, *, hit: bool, crit: bool,
                      advantage: bool = False, disadvantage: bool = False) -> None:
        """Record ONE resolved attack roll by *actor* and what became of it (§8.1).

        Written by ``resolve_attack_roll`` only, at the END of resolution — every
        value is already in a local variable there, so the call DRAWS NOTHING and
        cannot move a baseline (the per-feature ritual's step 3; §12's parity proof
        depends on it).

        ``hit`` / ``crit`` are the FINAL outcome, not the raw to-hit comparison: a
        Guided-Strike rescue arrives here as a hit, a parried hit as a miss.  That
        choice is what makes this ledger incapable of disagreeing with the damage
        ledger.  ``crit`` is ignored unless ``hit`` — a crit flipped to a miss is a
        miss, and nothing else.

        ``advantage`` / ``disadvantage`` are the EFFECTIVE stance after 2024
        cancellation, so passing both is a caller error rather than a "both" cell;
        it is rejected here rather than silently producing a tally whose stance
        counts exceed its roll count.
        """
        if advantage and disadvantage:
            raise ValueError(
                "record_attack takes the EFFECTIVE stance: advantage and "
                "disadvantage cancel under the 2024 rule (roll_d20), so a roll is "
                "at advantage, at disadvantage or flat — never both."
            )
        self.attacks.setdefault(actor_id, AttackTally()).add(
            hit=hit, crit=crit, advantage=advantage, disadvantage=disadvantage)

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
        for actor_id, ca in other.control_applied.items():
            self.control_applied.setdefault(
                actor_id, ControlAppliedTally()).merge(ca)
        for key, mt in other.mitigation.items():
            self.mitigation.setdefault(key, MitigationTally()).merge(mt)
        for key, ht in other.healing.items():
            self.healing.setdefault(key, HealingTally()).merge(ht)
        for actor_id, at in other.attacks.items():
            self.attacks.setdefault(actor_id, AttackTally()).merge(at)
        self.concentration_checks += other.concentration_checks
        self.concentration_breaks += other.concentration_breaks
        self.reactions_used += other.reactions_used
        for name, amount in other.resources_spent.items():
            self.resources_spent[name] = self.resources_spent.get(name, 0) + amount

    # -- convenience read-outs (the reporting layer / mechanism tests read these) -

    def mitigation_by_type(self, actor_ids: "set[int] | None" = None
                          ) -> dict[str, MitigationTally]:
        """Mitigation cells collapsed to damage type, optionally for one set of actors.

        ``actor_ids=None`` pools the whole combat, which is what "what did the enemy
        resist" wants; passing the roster's character ids is what a build's own
        damage-type composition needs."""
        out: dict[str, MitigationTally] = {}
        for (actor_id, damage_type), tally in self.mitigation.items():
            if actor_ids is not None and actor_id not in actor_ids:
                continue
            out.setdefault(damage_type, MitigationTally()).merge(tally)
        return out

    # -- healing read-outs (healing.md §8; the metrics layer reads these) -------

    def _healing_cells(self, *, context: "str | None" = None,
                       source_ids: "set[int] | None" = None,
                       target_ids: "set[int] | None" = None):
        for (src, tgt, ctx), cell in self.healing.items():
            if context is not None and ctx != context:
                continue
            if source_ids is not None and src not in source_ids:
                continue
            if target_ids is not None and tgt not in target_ids:
                continue
            yield (src, tgt, ctx), cell

    def healing_total(self, *, context: "str | None" = None,
                      source_ids: "set[int] | None" = None,
                      target_ids: "set[int] | None" = None) -> float:
        """Hit points restored, filtered on any combination of the three key
        dimensions.  ALWAYS pass a scope: an unfiltered total pools every actor's
        healing, which is the aggregate-ledger trap the per-metric ritual names."""
        return sum(c.healed for _k, c in self._healing_cells(
            context=context, source_ids=source_ids, target_ids=target_ids))

    def healing_by_source(self, **kw) -> dict[int, float]:
        """``{source_id: hp restored}`` — "healing PROVIDED", including by a summon."""
        out: dict[int, float] = {}
        for (src, _t, _c), cell in self._healing_cells(**kw):
            out[src] = out.get(src, 0.0) + cell.healed
        return out

    def healing_by_target(self, **kw) -> dict[int, float]:
        """``{target_id: hp restored}`` — "healing RECEIVED"."""
        out: dict[int, float] = {}
        for (_s, tgt, _c), cell in self._healing_cells(**kw):
            out[tgt] = out.get(tgt, 0.0) + cell.healed
        return out

    def healing_by_context(self, **kw) -> dict[str, float]:
        """``{context: hp restored}`` — the in-combat / between-combat split that
        §11.1 insists must not be pooled."""
        out: dict[str, float] = {}
        for (_s, _t, ctx), cell in self._healing_cells(**kw):
            out[ctx] = out.get(ctx, 0.0) + cell.healed
        return out

    # -- attacks read-out (§8.1; the metrics layer reads this) ------------------

    def attacks_for(self, actor_ids: "set[int] | None" = None) -> AttackTally:
        """The attacks channel collapsed to ONE tally over the given actors.

        ALWAYS pass a scope.  ``actor_ids=None`` pools every actor in the combat,
        the enemy included, and a pooled RATE is not a rate of anything — which is
        the whole reason this channel carries an actor dimension (§8.1).  The
        default exists only so a caller asking for the combat-wide roll COUNT does
        not have to assemble the id set.
        """
        out = AttackTally()
        for actor_id, tally in self.attacks.items():
            if actor_ids is not None and actor_id not in actor_ids:
                continue
            out.merge(tally)
        return out

    def control_applied_for(
            self, actor_ids: "set[int] | None" = None) -> ControlAppliedTally:
        """The REALIZED control channel collapsed to ONE tally over the given actors.

        Same contract as :meth:`attacks_for`, and the same reason for the actor
        dimension: with the enemy focused on a summon the pooled number describes
        neither entity.  ``None`` pools every actor, which is correct only for a
        roster-wide total.
        """
        out = ControlAppliedTally()
        for actor_id, tally in self.control_applied.items():
            if actor_ids is not None and actor_id not in actor_ids:
                continue
            out.merge(tally)
        return out

    def saves_forced(self, channel: str | None = None) -> int:
        """Total saves forced, optionally filtered to one channel."""
        return sum(t.forced for (_ab, ch), t in self.saves.items()
                   if channel is None or ch == channel)

    def saves_failed(self, channel: str | None = None) -> int:
        return sum(t.failed for (_ab, ch), t in self.saves.items()
                   if channel is None or ch == channel)
