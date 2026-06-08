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

---

## Current phase: fidelity build-up → War Angel validation

The skeleton proved the architecture end-to-end. Now we thicken it, in this order:

### Step 1 — Extra Attack (start here next session)

The most common action-economy pattern: two weapon attacks using the same action.
What needs to happen:
- The policy emits two `Choice(action_type="attack", cost="none")` after the first
  `cost="action"` swing (cost="none" = extra attack, action already spent).
- The scheduler enqueues them as sequential AttackRollEvents within the same turn.
- Tests: confirm 2 attack rolls fire per turn, total damage increases roughly 2×.

This also forces us to validate that the policy can correctly interleave a bonus
action between the two swings (the policy controls sequence by emission order).

### Step 2 — Scripted attacker (enemy fights back)

Add a `ScriptedEnemyPolicy` so the character takes damage and resource decisions
become meaningful. Key decisions already made (see "Enemy policy" section below):
- Structurally identical to character policy: `decide(snapshot) → list[Choice]`.
- Stats from `reference/data/monster_ac_and_saves_by_level.csv`, matched to level.
- Start with `archetype="melee_aggressive"` — stays adjacent, swings each turn.

### Step 3 — Resource tracking (spell slots, limited-use features)

Without resources, smite/channel divinity/etc. can't be modeled. Need:
- Per-entity resource pool (spell slots by level, ki points, superiority dice…).
- Cost declared in ability YAML consumed by the scheduler before enqueuing.
- Reset logic at short/long rest boundaries (simulated-day structure).

### Step 4 — War Angel DPR-by-level

Build the War Angel character policy (`reference/r-prototype/war_angel_combat_policies.txt`
is the written spec) and run DPR across levels 1–20. Validate against the R
prototype output in `reference/r-prototype/war_angel_*`. This is the first real
regression test of engine correctness.

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

- **Initiative / turn order** — currently list order. Real sims need rolled or
  fixed initiative. Defer until the scripted attacker step.
- **Finite vs. infinite enemy HP** — still infinite-HP dummy by default. Finite HP
  matters for encounter structure (enemies die, waves, action economy shifts).
  Build the toggle when the scripted attacker lands.
- **Advantage/disadvantage** — not yet wired. Needed soon (many abilities grant or
  impose it). Likely a modifier that wraps the d20 roll with `roll(2,20).max()`.
- **Saving throws** — needed for spells and conditions but not for the basic melee
  path. Wire in when the first save-based ability is modeled.
