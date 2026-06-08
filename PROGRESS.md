# PROGRESS — live status & next steps

> A running handoff note so any session (or the user) can see where things stand
> and what comes next. Update this as milestones land. For project orientation and
> locked architectural decisions, see `CLAUDE.md`.

---

## Done

- **Design contract captured** — `design/design.md` (entity model, simulated-day
  structure, verb engine spec, content schema, open decisions).
- **Ability schema locked & committed** — `design/ability_schema.md`. Three-layer
  structure (trigger/effect/cost), closed ~19-verb set, trigger/predicate
  vocabulary, modifier hooks, damage-resolution phase order, status & magic-item
  formats.
- **Schema validated against the corpus** — coverage-tested against the 9 canonical
  examples, the hard psionic crit-fisher stack, and a 7-build stress test (builds
  24, 25, 26, 36, 43, 44, 45). Verb set confirmed closed; 8 trigger/predicate
  vocabulary additions recorded. Zero new engine verbs forced.
- **Example content written & committed** — `content/abilities/`:
  `core_examples.yaml`, `psionic_critfisher.yaml`, `stress_test_patterns.yaml`.
- **Engine skeleton built & tested** — `src/` + `tests/`, 29 tests all green.
  One fighter swings a longsword at an infinite-HP dummy for N rounds; seeded
  dice, reproducible output, damage number comes out. All core architectural
  invariants are live in code (see `CLAUDE.md` §"Engine implementation").
- **Repo pushed to GitHub** — https://github.com/cas3ymau3/dnd-combat-sim
- **Extra Attack** — `ExtraAttackPolicy` in `src/policy.py`; supports N extra
  attacks and an optional interleaved bonus-action attack. 13 new tests, all green.
- **Scripted enemy + threshold HP model** — `ScriptedEnemyPolicy` (melee_aggressive
  archetype, stat-block dict interface). Entity HP now tracks into negatives; both
  sides act for the full `max_rounds` regardless of HP. `Scheduler.damage_received`
  exposes per-entity incoming damage per round. 20 new tests, all green.
- **Resource tracking + DayRunner** — `src/resources.py`: `ResourcePool` /
  `ResourceEntry` with full/partial SR restore and LR restore. `src/day_runner.py`:
  `DayRunner` orchestrates 4 combats, non-deterministic SR placement, LR at day
  start, `between_combats` hook for out-of-combat actions (e.g. Prayer of Healing).
  `Choice.resource_cost` wired into scheduler validation/consumption. Entity carries
  a `ResourcePool`. 44 new tests, all green (102 total).
- **Advantage/disadvantage + status flags + weapon mastery (sap/vex)** —
  `src/statuses.py`: `StatusSet` with tick-based expiry keyed on (round, turn_index),
  swept for all entities at each TurnStartEvent. `roll_d20()` honors RAW adv/disadv
  cancellation. `resolve_attack_roll` reads/consumes sapped & vex_advantage; masteries
  apply on hit (sap → target disadvantage until applier's next turn; vex → applier
  advantage vs that target). `Choice` gains `extra_masteries` (additive) and
  `mastery_override` (replace); `AttackRollEvent.masteries` built by scheduler. Entity
  carries a `StatusSet`. 32 new tests, all green (134 total).

---

## Current phase: fidelity build-up → War Angel validation

The skeleton proved the architecture end-to-end; we then thickened it through the
engine prerequisites for the War Angel validation. **All engine prerequisites are
now done.** What remains is the character itself (policy + build plan) and the
validation run — not more engine primitives.

Engine prerequisites, in the order we built them:
- ~~Extra Attack~~ ✓  — `ExtraAttackPolicy` (N extra attacks + optional interleaved BA).
- ~~Scripted enemy + threshold HP~~ ✓  — `ScriptedEnemyPolicy`; HP tracks into negatives,
  both sides always act the full round count.
- ~~Resource tracking + DayRunner~~ ✓  — `ResourcePool`, full/partial SR + LR restore,
  4-combat day with non-deterministic SR placement, `between_combats` hook for PoH.
- ~~Advantage/disadvantage + statuses + weapon mastery (sap/vex)~~ ✓  — `StatusSet`,
  `roll_d20`, sap/vex applied on hit and consumed on the holder's next roll.

### NEXT STEP — War Angel character policy + build plan (levels 1–13)

This is the first concrete character. Two pieces:

1. **Build plan** (data): the character's stat block at each level 1–13 — attack
   bonus, damage dice/bonus, AC, HP, spell slots and limited-use resources, weapon
   mastery, and which abilities are online. Derived from
   `design/build-guides/38_the_war_angel.txt` (the detailed level-by-level notes,
   including the per-level simulated DPR targets to validate against) and
   `reference/r-prototype/war_angel_*` (the prototype's structure).

2. **Daily plan / policy** (Python): the `decide()` logic implementing the build's
   per-round action economy — e.g. at lvl 1 a single rapier (vex) attack + 1 AoO
   per combat; by lvl 5+ war priest BA, true-strike, guided strike, wrathful smite;
   by lvl 8+ brutality::bluff. The build guide spells out the exact decision rules
   per level and per combat (see the lvl-08 and lvl-10 notes especially).

**Validation framing (agreed):**
- Levels 1–4 are mechanically simple → expect a CLOSE match to the build guide's
  simulated DPR (1: 8.32, 2: 7.39, 3: 7.39, 4: 6.81). A miss here means a basic
  attack-math bug — find it before layering on complexity.
- Levels 5–13 → SOFT validation. Same ballpark (±~10%), not exact. The R prototype
  and build-guide numbers are a compass, not ground truth (policy logic differs).
- Build the simplest level (1) first and climb the ladder.

**Known deferral inside this scope:** Flourish Parry (lvl 14) needs the reaction /
`intercept_event` decision point, which we have NOT built — fine, validation stops
at level 13. See "Open threads" for the full deferred list (TurnEndEvent, saves,
spell-aggressive enemy, weapon slot, light/nick, etc.).

---

## Enemy policy — decisions recorded

1. **Same interface as character policy.** Both implement
   `Policy.decide(snapshot) → list[Choice]`. Scheduler loop is unchanged.

2. **`ScriptedEnemyPolicy(archetype, stats_by_level)`** — behavior is a
   constructor param, not a subclass. Keeps the door open to sampling archetypes
   across Monte Carlo runs (enemy behavioral variance as a first-class concern).

3. **Stats from CR-scaling table.** `reference/data/monster_ac_and_saves_by_level.csv`
   is the source of truth for AC, attack bonus, save DCs, damage by CR/level.
   Enemy `Entity` is constructed from a row matched to character level at sim setup.

4. **Behavioral axis for later:** melee-stays-close vs. ranged-kiter. Affects
   opportunity attacks, forced movement, DPR for position-sensitive builds
   (Sentinel fighter cares; ranged Ranger largely does not).

---

## Open threads / deferred decisions

- **Initiative / turn order** — currently list order (character first, enemy
  second). Real sims need rolled or fixed initiative. Low priority until we have
  multiple enemy archetypes and need to study action-order sensitivity.

- **Formal weapon slot** — deferred. For now a weapon's mastery is declared via
  `base_stats["weapon_mastery"]`, and weapon switches (e.g. War Angel longsword →
  rapier at lvl 16) are modeled by the build plan updating base_stats at the level
  transition. Build a proper `Weapon` dataclass (name, damage_dice, mastery,
  `properties: list[str]`) when the first **dual-wielder** forces simultaneous
  multi-weapon tracking. Not needed for War Angel validation.

- **Light weapons / two-weapon fighting / nick mastery** — architecture is believed
  sufficient as-is: the light-weapon BA second attack is just
  `Choice(cost="bonus_action")`; nick mastery moves it to `cost="none"` (structurally
  identical to Extra Attack). No engine change anticipated, but **verify against a
  real dual-wield build** before relying on it. War Angel uses no light/nick weapons,
  so deferred.

- **Weapon mastery — remaining properties** — sap and vex are built (the only two
  War Angel needs). topple, slow, push, nick, cleave, graze deferred until a build
  needs them. `mastery_override` (Tactical Master, lvl 16) field stubbed on `Choice`
  but not yet consumed by the scheduler.

- **`TurnEndEvent` / end-of-turn trigger point** — the scheduler currently emits
  only `TurnStartEvent`, and status expiry is swept lazily at each turn start.
  This is **provably correct for the current statuses** (sap, vex) because each is
  read only during its holder's own turn, so lazy expiry is never observable. It
  **breaks** for: (a) statuses that gate reactions (e.g. stunned — a reaction could
  fire in the gap between true end-of-turn expiry and the next start-of-turn sweep,
  wrongly seeing the status as still active); (b) effects that *proc* on turn end
  rather than expire (e.g. spirit guardians dealing damage when an entity ends its
  turn in the emanation — must fire at that turn-end tick with correct attribution).
  Both need an explicit `TurnEndEvent` as a symmetric counterpart to `TurnStartEvent`.
  Deferred until the first end-of-turn proc or reaction-gating condition is modeled,
  so its shape is driven by a real case. Not needed for War Angel validation.

- **Saving throws** — needed for spells and conditions. Deferred until the first
  save-based ability is modeled (Step 3+). Will add `SavingThrowEvent`, a
  `spell_save_dc` stat on attackers, and save-bonus stats on defenders.

- **Spell-aggressive enemy archetype** — enemies that target saving throws rather
  than making attack rolls. Required for full defensive assessment (not just AC,
  but also save proficiency). Deferred after `melee_aggressive` is validated.
  Longer-term goal: run across a distribution of archetypes and aggregate, rather
  than a single archetype.

- **Monster stat table (CSV)** — `reference/data/monster_ac_and_saves_by_level.csv`
  is read-only reference for now. Before using it as a live input, it needs
  enrichment: number of attacks per CR, damage-per-hit, enemy HP distribution from
  MM analysis. `ScriptedEnemyPolicy` already accepts a dict interface so swapping
  in a CSV row later requires no policy changes.

- **Grapple / shove / unarmed strike variants** — some builds (e.g. Cursed Kensei)
  choose attack flavor per-swing. Extend `Choice` with an optional `attack_kind`
  field when the first such build is modeled. Grappler-feat compound effects
  (damage + condition on same hit) belong in an `on_hit` subscriber.

- **War Angel validation** — treat the R prototype as a soft compass, not ground
  truth. Per-hit damage math (smite dice, wrathful smite) should be near-exact.
  DPR totals may diverge due to policy differences and hit-rate modeling; ±10% is
  acceptable noise, not a regression.

- **Finite HP as a toggle** — considered and deferred. The threshold model (HP
  tracks into negatives, entities always act) is the default. If variable-length
  encounters become a research question, revisit then — don't add the toggle
  preemptively.
