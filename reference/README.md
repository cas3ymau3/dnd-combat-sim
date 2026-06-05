# reference/ — prior art (read-only)

This directory holds earlier work that informs the Python build but is **not part
of it**. Do not run, extend, or import from this code. It exists as a reference
for *how combat resolution was previously done*, so the Python re-implementation
can reuse hard-won logic without inheriting the old architecture.

## r-prototype/

Earlier **R** implementations of this same simulator. They are monolithic and
predate the verb/layer architecture in `design/design.md`, but they encode real,
working combat-resolution logic (attack resolution vs. monster AC, opportunity
attacks, smite/resource pools, rest rules, per-level combat policies).

The most developed and useful as a reference:

- `war_angel_sim.R` (+ `war_angel_phase1.R`, `war_angel_runsim.R`,
  `war_angel_combat_policies.txt`) — the most complete single build sim
  (levels 1–12). Best reference for overall structure.
- `optimized_war_angel.R`, `optimized_holy_hunter.R`,
  `optimized_champion_lancer.R` — later per-build sims.
- `darkmoon_piercer.R`, `soulknife_metamorph.R`,
  `white_dragon_warrior_monk.R`, `sorcerous_burst.R` — additional per-build
  sims / component experiments.

**Suggested use:** a good first Python milestone is to reproduce the War Angel
DPR-by-level output in the new architecture, validating against the R sim as a
known-good reference.

## data/

Reusable tables, several directly consumable by the Python content layer:

- `monster_ac_and_saves_by_level.csv` — clean CR-scaling table (AC + per-save
  modifiers, levels 1–20). This is the §3.5 enemy parameter table, already built.
- `monster_ac_and_saves.csv` — related monster stat data.
- `ability_mods_DCs.csv`, `resources.csv`, `features_abilities.csv` — tables
  from the older R project (ability modifiers/DCs, resource definitions,
  feature/ability data). Useful as a starting point for the content layer; review
  for ruleset currency before relying on them.
- `2014_monster_stats.csv` — older-ruleset monster stats; lowest priority.
