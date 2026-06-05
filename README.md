# D&D 5.5e Combat Simulator

A Monte Carlo simulator for quantitatively evaluating D&D 5.5e (2024 rules)
character builds, primarily via **average damage per combat round (DPR)** across
a simulated adventuring day, run many times.

**Start here:** [`design/design.md`](design/design.md) is the design contract —
the entity/actor model, the simulated-day structure, the verb-based engine
specification, the ability/content schema, and the open decisions. Code conforms
to that document.

## Layout

```
design/          The spec and its source material
  design.md          ← the design contract (read this first)
  model_setup_notes.md   original model notes
  build-guides/      33 curated 2024-ruleset character build guides (the corpus
                     the verb set was validated against)
reference/       Prior art — informs the build, is NOT part of it
  r-prototype/       earlier R implementations of this simulator (see note below)
  data/              reusable CR-scaling / monster / ability / resource tables
src/             Python engine (to build)
content/         Declarative ability/status/item data (to build)
tests/           Tests (to build)
```

## Status

Pre-implementation. The design is captured; the Python build has not started.
Per `design/design.md` §5/§7, the intended first steps are: pin the ability
schema (using the messiest build as a coverage test), then the engine skeleton.

## Note on `reference/`

`reference/` is read-only prior art. It is here to inform the Python build — not
to be run, extended, or confused with it. See `reference/README.md`.
