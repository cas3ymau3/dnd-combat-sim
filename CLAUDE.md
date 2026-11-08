# CLAUDE.md — Project Orientation

This file is read automatically at the start of each session. It orients a fresh
session on what this project is, how it's structured, and the architectural
decisions already made. **Read `design/design.md` and `design/ability_schema.md`
in full before doing engine work** — they are the binding contracts. Also read
`design/buff_primitive.md` (the `cast_effect` buff/debuff primitive — envelope +
payload-substrate registry) before any buff/debuff or persistent-effect work.

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
  build-guides/        33 2024-ruleset build guides (schema corpus). WRITTEN BY THE
                       USER — these are not third-party material, and no DPR number in
                       them is an external validation source (see below).
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
    implement `Policy.decide(snapshot) → list[Choice]`. The definitive enemy
    data is `reference/data/monster_stats_by_level.csv` (AC + saves + to-hit /
    save DC / per-swing & AoE dice, per character level), loaded by
    `src/builds/enemy_stats.py`; `BaselineEnemyPolicy` (`src/builds/enemy.py`)
    is its full consumer (per-level dice → enemy crits, attack-vs-save mix,
    retargeting). The older `ScriptedEnemyPolicy` (targeting-only, same module —
    there is no `scripted_enemy.py`) and the AC/saves-only
    `monster_ac_and_saves_by_level.csv` (now the generation provenance) remain
    for the earlier builds. See PROGRESS.md for the full enemy-policy decision
    record.
    - **THE ENEMY IS NOT A PROPERTY OF THE BUILD (s50; the baked-in path DELETED s52).**
      `src/evaluation/enemy.py` is the framework's enemy-construction seam
      (`design/evaluation_framework.md` §3.4): `RunConfig.enemy` selects one of
      **three** declared kinds (`baseline` / `scripted` / `none`), `enemy_options`
      configures it against a closed schema, and §4 provenance records every
      resolved value. **`enemy` is a REQUIRED field with no default** — a default
      is an implicit enemy, and an implicit enemy is what makes two reports
      incomparable. Prefer `enemy="baseline"` for anything cross-build; `none` is
      a passive target carrying the table's full stat block, and `scripted` is a
      comparison arm (it swings but forces no saves).
      - **No build factory constructs an enemy policy, and no `LEVELS` row carries
        enemy data.** `enemy_stats.make_baseline_enemy` is the one enemy-`Entity`
        constructor AND NOW ITS ONLY NAME: the three per-build `make_training_dummy`
        wrappers that delegated to it are **DELETED (s61, PROGRESS item 5b)** and every
        caller names it directly. Two were pure one-line aliases; Starfire's also set a
        `damage_response` from its own `LEVELS` row, dead at all eight of its levels and
        deleted with it. A factory run on its own faces a PASSIVE target. A test that needs the enemy
        to act installs a policy itself (see `tests/test_summon_survival.py`'s
        `_install_l8_enemy` for the pattern), and `enemy.install` is called once, in
        `runner.simulate`, so no adapter can forget it.
      - **`src/validation.py` IS GONE (s52)**, and with it the §12 bit-identical
        parity proof and the last guide-target tests. The end-to-end signal is now
        `GOLDEN_DPR` in `tests/test_eval_enemy_seam.py` (13 exact points) plus the
        L2-4 closed-form check; `evaluation_framework.md` §12 records why that swap
        is asymmetric. Regenerating a golden is a DELIBERATE act with a decision
        record.

---

## Engine implementation — what exists

Engine fidelity build-up is well underway (live test count + current milestone:
see PROGRESS.md). The mechanical prerequisites for the War Angel validation
(levels 1–13) are in place; what remains is per-build policy + data, not new
engine primitives. Module map (`src/`):

- `rng.py` — SeededRNG, the single seed-logged dice channel, routed into per-`(purpose,
  owner)` SUBSTREAMS (`design/evaluation_framework.md` §6.3, framework step 9 / s60).
  Every `roll()` names its stream; the generator is DERIVED from
  `(seed, epoch, purpose, owner)` via a `spawn_key`, never handed out by
  `SeedSequence.spawn()` in call order. `PURPOSES` is a closed vocabulary of eight with
  NO catch-all, and `ALIGNMENT` (pinned `"day"`) is the epoch — the streams
  re-synchronize at every day, which is the estimator's replication unit and the thing
  that makes §6.1's paired seeding worth ~5.8x instead of ~1x. **Changing `ALIGNMENT`
  or adding a purpose re-baselines every seeded number in the project.** The owner is a
  stable LABEL (`entity.name`, a policy's declared `stream_owner`, or `"day"`) and
  NEVER `Entity.id`, which is process-global.
- `modifiers.py` — Modifier + ModifierStack (fold-left, tick expiry, phase filter).
- `resources.py` — ResourcePool/ResourceEntry (SR/LR restore; spell_slot_1..9).
- `statuses.py` — StatusSet (tick-expiring flags keyed on (round, turn_index)).
- `healing.py` — the healing substrate (design/healing.md): `HealSpec` + `resolve_healing`
  (phase order H1-H8, the healing counterpart of #8 — no crit doubling), `HitDiceSpec` and
  the TWO Hit Dice rules. **The rule to remember: healing resolved INSIDE combat rolls;
  healing applied OUTSIDE combat is MEAN-FIELD and draws nothing** — any out-of-combat
  dice source would shift the shared stream for every build and break every one of
  `GOLDEN_DPR`'s exact points (it was the §12 parity proof until s52 retired that).
- `entity.py` — Entity (threshold HP + base stats + modifier stack + pools); `stat()` folds the stack.
- `events.py` — Tick, event dataclasses, EventQueue (heapq, insertion tiebreak). `AttackRollEvent`/`DamageEvent` carry `extra_flat_damage` (bleed); `AttackRollEvent.policy_riders` gates the actor's post-roll deciders.
- `policy.py` — Policy protocol, GameState, Choice; post-roll Miss/Hit decision contexts (HitResponse carries `extra_damage_dice` AND `rider_damage` — substrate #6 outgoing riders, RiderDamageSpec); HitContext carries `origin`/`range_` (modality taxonomy) for rider gating; the DEFENDER-side intercept point (`on_incoming_hit` + IncomingAttackContext / InterceptResponse / CounterSpec); the failed-save reroll point (`on_failed_save` + FailedSaveContext / SaveRerollResponse — Indomitable); the caster post-damage rider (`on_deal_damage` — Fueled Spellfire); sample policies.
- `verbs.py` — resolve_attack_roll (+ on_miss/on_hit/intercept deciders) + resolve_damage (phase-ordered, sums extra_flat_damage); roll_d20; resolve_saving_throw (+ optional `reroll_decider`); apply_masteries_on_hit. The on_hit decider returns `(extra_dice, extra_masteries, rider_damage)`: `extra_dice` folds into the weapon hit (smite), `rider_damage` spawns SEPARATE typed DamageEvents (substrate #6 — Fount of Moonlight, Primal Strike).
- `scheduler.py` — pop-earliest loop + subscriber registry; decision-point → policy → enqueue; resource validation; status sweep; per-turn economy hung for mid-turn deciders; miss/hit/**intercept**/**save-reroll** decider closures (intercept = `intercept_event`, design §4 #15; save-reroll = Indomitable — both consult the *target's* policy).
- `entity.py`'s `zero_hp_category` — the closed enum {threshold, vanishes, downed}
  (design/healing.md §6) replacing the old `dies_at_zero_hp` boolean, which survives as a
  property over it. `downed` is a REVERSIBLE state (`destroyed` is permanent); the
  scheduler and every commander read `is_out_of_action`.
- `summons.py` — substrate #7 / 7a: `SummonSpec` + `create_entity`/`destroy_entity` (verb 12) on an `(entities, policies)` roster (day-start or mid-combat); a controlled ally is a `create_entity`'d Actor, COMMANDED on its controller's turn via `Choice.actor` (the cost is the controller's, the event's actor is the commanded entity → its own per-summon DPR column). Teardown keyed to `effect_source` via `Entity.remove_effect` (a `destroyed` flag).
- `day_runner.py` — one adventuring day (LR → 4 combats); samples combat times + SR placement; before/between-combat hooks. Also OWNS THE §6.3 ALIGNMENT EPOCH: `run_day` calls `rng.begin_day` / `rng.begin_combat`, and the call is deliberately NOT guarded with `getattr` — a defensive call would let the epoch go silently missing and make pairing inert again with nothing failing.
- `builds/war_angel.py` — first concrete build (per-level data + policy).
- `builds/enemy_stats.py` — the definitive per-level enemy table, AND
  `make_baseline_enemy(level)`: **the one enemy-`Entity` constructor** (s52). No build
  module builds an enemy of its own any more.
- `evaluation/` — the build-agnostic evaluation framework (`design/evaluation_framework.md`
  §13, steps 1-7 done; step 8 at 8e). `enemy.py` is the enemy-construction seam;
  `runner.simulate` is the single place `enemy.install` is called. **There is no
  `src/validation.py`** — step 5b deleted it; the end-to-end signal is `GOLDEN_DPR` in
  `tests/test_eval_enemy_seam.py`.
  - `sweep.py` + `sweeps/*.yaml` — the sweep driver (§10.1/§10.2): declaration → cells →
    a shared content-addressed record store keyed `(config_hash, engine_commit)` → a
    manifest and one concatenated tidy frame. `python -m src.evaluation.sweep {plan,run}`.
  - `baselines.py` + `baselines/*.yaml` — the §11 baselines registry: **its own** registry
    of DATA, never a declaration on `MetricDef`, because a target is a reference and not
    a property of the build. An entry's position is a `coordinate` dict over declared
    dimensions (`exact`/`contains`/`free`), its value is a POINT or an INTERVAL, and its
    `basis` is required with `unknown` legal. Scoring is report-layer and **opt-in**:
    `report_to_dict(report, baselines=…)` adds a `scores` section, and the record STORE
    deliberately writes records UNSCORED, because the cache key does not include the
    baseline set (§11.2).

Key invariants to preserve when extending:
- All dice through `SeededRNG.roll()` — never call random directly — and every call
  NAMES ITS STREAM (`stream=(purpose, owner)`, a required keyword with no default,
  because a default is a catch-all and a catch-all re-couples whatever lands in it).
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
  - **THAT NOTE DESCRIBES THE LOCAL MACHINE. A CLOUD SESSION IS DIFFERENT (s48).**
    Sessions started from the Claude app run in an ephemeral cloud container behind
    an agent proxy, and two independent guards apply there that do not apply locally.
    Diagnosed the hard way in s48 — twice mis-attributed before the 403 was found —
    so it is written down rather than re-derived:
    - **The agent proxy returns HTTP 403 for destructive ref updates and for
      repository-settings writes.** `git push origin --delete <branch>` fails as
      `RPC failed; HTTP 403` followed by `send-pack: unexpected disconnect`, which
      reads like a network blip and is not one. `gh api -X PATCH repos/...` answers
      plainly: *"Repository settings writes are not permitted through this proxy."*
      A delete of a NONEXISTENT branch returns a clean GitHub error instead, which is
      the cheap way to tell the two guards apart.
    - **The auto-mode classifier blocks commands it reads as destructive** before
      they reach the network: `--force-with-lease`, `gh api -X DELETE`.
    - **Everything that matters is unaffected:** commit, push, create branch, open PR,
      merge PR (via the `mcp__github__*` tools), and the full test suite all work
      normally. The only casualties are branch deletion and repo-settings changes,
      both of which are the user's to do in the GitHub UI.
    - **CONVENTION, adopted s48: ONE FRESH BRANCH PER PR — never recycle a merged
      branch name.** Reusing one after its PR squash-merges requires a force-push on
      ANY machine, because a squash leaves the old commits as non-ancestors of `main`.
      This is the convention that removes the only friction that actually cost
      anything; it is good hygiene locally too. When a session ships a second PR, give
      it a new branch rather than restarting the first one.
    - Branch cleanup is best handled by the repo's **Settings → General →
      "Automatically delete head branches"** rather than by Claude.
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
