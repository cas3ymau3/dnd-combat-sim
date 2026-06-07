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
  vocabulary additions recorded (aura broadcast, ally-damage intercept, external
  death trigger, external spell trigger, counter-damage brand, magic_action vs
  spell tag, choose_one effect construct, action_cost_override hook). Zero new
  engine verbs forced.
- **Example content written & committed** — `content/abilities/`:
  - `core_examples.yaml` — 9 canonical coverage tests (Tough → Prayer of Healing)
  - `psionic_critfisher.yaml` — the hard 5-hook stack with phase annotations
  - `stress_test_patterns.yaml` — one ability per new schema pattern
- **Repo pushed to GitHub** — https://github.com/cas3ymau3/dnd-combat-sim

---

## Next step: engine skeleton — "swing at the dummy" milestone

Build the **smallest possible vertical slice** that proves the architecture end to
end, then thicken it. Target:

> One character with a longsword swings at the infinite-HP target dummy for a few
> rounds, with seeded dice, and we get a damage number out.

This deliberately forces us to stand up a minimal version of each core piece, and
**nothing more** — no spells, zones, or resources yet:

- **Entity** — a minimal bag of state (HP, base stats, modifier stack).
- **Seeded RNG wrapper** — single channel for all dice; logs the seed.
- **Modifier stack** — compute effective stats (attack bonus, AC) on demand by
  folding modifiers over base values.
- **Minimal scheduler** — turns and rounds only; the pop-earliest-event loop.
- **Two verbs** — `attack_roll` and `damage`, only as deep as the swing needs.
- **A trivial policy** — a `decide` function that always returns "swing", to make
  the policy/resolution boundary concrete from day one.
- **Tests (pytest)** — pin down each piece; this is also how we'll later prove the
  engine matches the R reference.

The user asked (before the session break) to next see **the minimal class/file
structure** for this milestone — what objects exist, what each owns, and exactly
where the `decide` function plugs into the scheduler loop. Start there: propose the
structure, get feedback, then implement incrementally.

### After the skeleton breathes

Per `design/design.md` §7 and `reference/README.md`: work toward reproducing the
**War Angel DPR-by-level** output in the new architecture, validating against the R
prototype (`reference/r-prototype/war_angel_*`) as a known-good reference. The
War Angel combat policy (`reference/r-prototype/war_angel_combat_policies.txt`) is
effectively a written spec for that build's `decide` function.

---

## Notes / open threads

- Enemy scope is still a flagged open decision (design.md §6): infinite-HP dummy by
  default, possible optional finite-HP mode; build the enemy save math regardless
  (needed for character-imposed conditions).
- `reference/data/monster_ac_and_saves_by_level.csv` is the §3.5 enemy CR-scaling
  table, already built and directly consumable by the content layer.
