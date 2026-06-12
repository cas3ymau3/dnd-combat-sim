# CLAUDE.md — Project Orientation

This file is read automatically at the start of each session. It orients a fresh
session on what this project is, how it's structured, and the architectural
decisions already made. **Read `design/design.md` and `design/ability_schema.md`
in full before doing engine work** — they are the binding contracts.

---

## What this project is

A **Monte Carlo simulator for D&D 5.5e (2024 rules)** that evaluates character
builds quantitatively, primarily via **average damage per round (DPR)** across a
simulated adventuring day, run many times. It is explicitly **not** a full rules
engine and **not** a play aid — fidelity is traded for tractability wherever the
design notes say so.

The user has strong R background, less Python. They are learning game/engine
design while building this — favor conceptual explanation alongside code, and
explain Python-specific idioms where they differ from R.

---

## Repo layout

```
design/
  design.md            ← the design contract (read first)
  ability_schema.md    ← the locked ability/content schema (read second)
  model_setup_notes.md
  build-guides/        33 curated 2024-ruleset build guides (schema corpus)
reference/             Read-only prior art (R prototype + data tables). Do NOT
                       run, extend, or import from this — it informs the build.
  r-prototype/         Earlier R sims; war_angel_* is the best structural reference
  data/                Reusable CR-scaling / monster / ability tables (some
                       directly consumable, e.g. monster_ac_and_saves_by_level.csv)
content/
  abilities/           Declarative ability data (YAML) — the "verbs as data" layer
src/                   Python engine (to build)
tests/                 Tests (to build)
```

---

## Architectural decisions already locked

These were reached deliberately; do not silently revisit them.

1. **Engine is a generic interpreter, not D&D-aware code.** The engine knows
   nothing about specific spells. All "D&D knowledge" lives in content data
   (`content/abilities/*.yaml`). Adding an ability should require writing data,
   never engine code. If it forces an engine change, it's either a genuinely new
   primitive (add deliberately) or an abstraction leak (fix it).

2. **Abilities are declarative data; policies are Python code.** Abilities are
   reused across builds and compose from a fixed verb vocabulary → data. Daily
   plans (combat policies) are bespoke per-build conditional logic → ordinary
   Python functions. Don't try to data-fy policies (that's reinventing Python).

3. **Three-layer ability schema** (see `ability_schema.md`): trigger (when) /
   effect (what — ordered verbs) / cost (what it consumes). Strictly separated.

4. **Closed verb set** (~19 primitives) + trigger/predicate vocabulary + modifier
   hooks. Validated against all 33 build guides. Zero new engine verbs were forced
   during coverage testing; 8 trigger/predicate vocabulary additions were recorded.

5. **Discrete-event scheduler is the engine's spine.** A time-ordered queue of
   future events (pop earliest → process → maybe enqueue more → repeat) plus a
   subscriber registry for synchronous triggers. Key consequences:
   - **Durations are future-dated expiry events in the queue**, NOT counters that
     get decremented across the code.
   - **Triggers (on_hit, incoming_attack, etc.) are subscribers** fired
     synchronously when an event resolves. These map 1:1 to the schema's trigger
     vocabulary.

6. **Modifier stack, not mutated stats.** Effective stats (AC, attack bonus, etc.)
   are computed on demand by folding active modifiers over a base value. Adding/
   removing a buff = pushing/popping a modifier, never editing a number in place.
   This also makes "% of turns under status X" outputs fall out for free.

7. **Policy vs. resolution is sacred.** Policy (the `decide` function) reads game
   state and returns choices; it never rolls dice or mutates state. Resolution
   (engine handlers) rolls dice and mutates state; it never makes choices. The
   policy is consulted at **decision points** — not just turn start, but also
   mid-turn after rolls resolve (e.g. "smite on hit", "guided strike on a miss it
   would flip"). Decision points are events the engine opens for the policy to fill.

8. **Damage resolution phase order** (fixed): (1) determine dice pool — crits
   double die *count* here; (2) roll pool; (3) per-die mods (reroll, replace,
   floor); (4) sum; (5) flat bonuses. Modifier hooks carry a `phase` tag.

9. **Determinism via seeded RNG** with per-run seed logging. All dice go through
   one controlled channel so any run can be replayed.

10. **Implementation language: Python** (numpy/pandas/pytest ecosystem).

11. **Tick tuple is `(round, turn_index, sequence)`** — not a named phase enum.
    Action economy phase (action / bonus_action / reaction) is a **cost tag**
    on `Choice` and events, not a position in the tuple. The policy controls
    ordering by controlling what it emits first; the scheduler assigns
    sequence numbers in that order. Reactions slot into the current
    (round, turn_index) at the next available sequence number.

12. **Enemy policy is structurally identical to character policy** — both
    implement `Policy.decide(snapshot) → list[Choice]`. Near-term target is a
    `ScriptedEnemyPolicy(archetype, stats_by_level)` driven by
    `reference/data/monster_ac_and_saves_by_level.csv`. See PROGRESS.md for
    the full enemy-policy decision record.

---

## Engine implementation — what exists

Engine fidelity build-up is well underway (live test count + current milestone:
see PROGRESS.md). The mechanical prerequisites for the War Angel validation
(levels 1–13) are in place; what remains is per-build policy + data, not new
engine primitives. Module map (`src/`):

- `rng.py` — SeededRNG, the single seed-logged dice channel.
- `modifiers.py` — Modifier + ModifierStack (fold-left, tick expiry, phase filter).
- `resources.py` — ResourcePool/ResourceEntry (SR/LR restore; spell_slot_1..9).
- `statuses.py` — StatusSet (tick-expiring flags keyed on (round, turn_index)).
- `entity.py` — Entity (threshold HP + base stats + modifier stack + pools); `stat()` folds the stack.
- `events.py` — Tick, event dataclasses, EventQueue (heapq, insertion tiebreak). `AttackRollEvent`/`DamageEvent` carry `extra_flat_damage` (bleed); `AttackRollEvent.policy_riders` gates the actor's post-roll deciders.
- `policy.py` — Policy protocol, GameState, Choice; post-roll Miss/Hit decision contexts; the DEFENDER-side intercept point (`on_incoming_hit` + IncomingAttackContext / InterceptResponse / CounterSpec); the failed-save reroll point (`on_failed_save` + FailedSaveContext / SaveRerollResponse — Indomitable); sample policies.
- `verbs.py` — resolve_attack_roll (+ on_miss/on_hit/intercept deciders) + resolve_damage (phase-ordered, sums extra_flat_damage); roll_d20; resolve_saving_throw (+ optional `reroll_decider`); apply_masteries_on_hit.
- `scheduler.py` — pop-earliest loop + subscriber registry; decision-point → policy → enqueue; resource validation; status sweep; per-turn economy hung for mid-turn deciders; miss/hit/**intercept**/**save-reroll** decider closures (intercept = `intercept_event`, design §4 #15; save-reroll = Indomitable — both consult the *target's* policy).
- `day_runner.py` — one adventuring day (LR → 4 combats); samples combat times + SR placement; before/between-combat hooks.
- `builds/war_angel.py` — first concrete build (per-level data + policy).

Key invariants to preserve when extending:
- All dice through `SeededRNG.roll()` — never call random directly.
- All stat reads through `entity.stat(name, tick)` — never read `base_stats` directly.
- Persistent resources through `entity.resources` (ResourcePool); turn-level action
  economy (action/bonus_action/reaction) is managed by the scheduler, NOT in the pool.
- Statuses through `entity.statuses` (StatusSet); expiry is swept at turn starts only
  (see PROGRESS.md "TurnEndEvent" note for when that lazy model needs extending).
- Policy's `decide()` is pure read — no dice, no mutation, no queue access.
- Verb handlers receive the queue and push follow-on events; they never call `decide()`.
- New abilities → new content YAML + maybe a new subscriber. Not new engine verbs.

---

## Working agreements

- The user reviews decisions iteratively — present design choices and trade-offs,
  invite feedback, don't barrel ahead on consequential structure.
- Co-author trailer on commits per the user's harness settings. Remote is
  `origin` → https://github.com/cas3ymau3/dnd-combat-sim.
- **GitHub ops work in-shell (verified 2026-06-12).** `gh` 2.93 is on PATH and
  authenticated as `cas3ymau3` via the system keyring (token scopes `repo` +
  `workflow`); git uses the `manager` credential helper over the HTTPS `origin`
  remote. Claude can push, open/merge PRs, and delete branches directly. (The
  prior note that auth "isn't visible to the sandboxed shell" was stale.)
- **Agreed git/GitHub autonomy (2026-06-12, updated): manage git on your own.**
  Claude commits changes as it makes them (no need to be told), branches off
  `main` for new work, pushes feature branches, and opens PRs autonomously.
  Claude CONFIRMS with the user ONLY before: merging to `main`, pushing to
  `main` directly, force-pushing, or deleting branches. (`git + files are the
  real save`; the chat is scratch — so commit early rather than hoarding
  working-tree changes.)

---

## Current status & next step

See `PROGRESS.md` for the live status and the immediate next task.
