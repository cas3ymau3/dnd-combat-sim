# Evaluation framework — the reporting / aggregation layer

> **Status: DESIGN LOCKED (session 42, 2026-08-17). §13 STEP 1 BUILT (session 43,
> 2026-08-18) — `src/evaluation/`; steps 2–6 outstanding.**
> This note settles the contract for `design.md` §8's outputs — how a build is
> evaluated, what a report contains, how it is serialized, and how the numbers stay
> comparable across builds, scenarios, and engine versions. It is the design-first
> pass required by `design-first-for-cross-cutting-primitives`: the evaluation layer
> is consumed by every build (present and future) and by a downstream website, so its
> shape is settled before it is built.
>
> **Reads on:** `design.md` §8 (the output list), `enemy_model.md` §7 (toggles),
> §11 (validation framing), §13 (the telemetry seam), §10 (deferrals).
> **Supersedes:** `enemy_model.md` §6's "v1 records control as an output factor and
> never applies it" stance — see §7 below.

---

## 1. Purpose and scope

**What this layer is for.** Turning simulation runs into *comparable, self-describing
measurements* of a build — offense (DPR) and resilience (damage taken, control
pressure survived, mitigation, resource economy) — against the standardized 4×4-round
baseline (memory `standardized-dpr-baseline-not-realism`).

**The hard constraint (user, s42).** It must work for **all existing builds** — which
were written as ad-hoc, partially-complete vehicles for building engine machinery —
**and for future builds not yet specified**. That rules out anything build-specific:
the current `src/validation.py` is hardcoded to War Angel and reads entities by tuple
position, and cannot be generalized in place.

**What it is NOT.** Not a rules engine change, not a new enemy model, and not a
website. It produces artifacts; presentation is downstream (§9).

---

## 2. What actually varies across builds (the grounded survey)

Measured against the three builds that exist today:

| build | factory | scenario axes | returns | levels |
|---|---|---|---|---|
| War Angel | `war_angel.make_day_runner(level, rng, rounds)` | none | `(runner, char, dummy)` | 1–16 (contiguous) |
| Starfire Scion | `starfire_scion.make_day_runner(…)` | 5 — `primal_strike_unarmed`, `fourth_level_spell`, `precast_mode`, `precast_prob`, `with_party` | `(runner, char, dummy)` | 1, 4, 5, 9, 10, 11, 12, 15 |
| Silvertail | `silvertail.make_silvertail_runner(…)` | 4 — `beast_effect`, `mortal_beast`, `recast`, `zone_effect` | `(runner, char, beast, dummy)` | 4, 8, 10 |

Four axes of variance the framework must absorb:

1. **Factory name and signature** differ (`make_day_runner` vs `make_silvertail_runner`).
2. **Scenario axes** are build-specific and open-ended (0–5 today, unbounded later).
3. **Roster shape** differs — Silvertail returns a summon; callers currently rely on
   *tuple position* to know which entity is the character. This is the specific coupling
   that makes `validation.py` un-generalizable.
4. **Level sets are sparse and disjoint.** There is no shared level axis; a sweep must
   intersect with each build's own `LEVELS` keys.

**Design consequence — adapt, do not rewrite.** The existing factories stay exactly as
they are. Each build registers a thin **adapter** that maps a config to a runner plus a
*role-tagged* roster. This is deliberate: those factories back validated DPR baselines
(War Angel L1–16 against guide targets), and rewriting them would risk drift for no gain.

---

## 3. Core abstractions

### 3.1 `RunConfig` — one fully-specified simulation

A run is a point in a parameter space. The **key insight**: a build's scenario axes and
the enemy's §7 sensitivity toggles are *the same kind of thing* — configuration of one
measurement. Unifying them means sensitivity analysis works identically on both sides.

```
RunConfig:
    build:            str                 # registry key, e.g. "war_angel"
    level:            int
    build_options:    dict[str, Any]      # the build's scenario axes
    enemy:            str                 # "baseline" | "scripted" | "none"
    enemy_options:    dict[str, Any]      # the §7 toggles
    rounds_per_combat: int = 4
    combats_per_day:  int = 4
    n_days:           int                 # see §10 tiers
    seed:             int
    mode:             str = "fixed_length"  # | "finite_hp"  (see §5.2)
```

`RunConfig` is hashable and serializable — it is simultaneously the run instruction,
the cache key (§10), and the provenance block (§4).

**Amendment (s43): `enemy` needs a `"build_default"` member — see §3.4.** This section
assumed the enemy is selectable independently of the build; it is not, yet. `ENEMY_KINDS`
is `("build_default", "baseline", "scripted", "none")` and step 1 honours only the first.
`enemy_options`, the other three `enemy` values, and `mode="finite_hp"` all raise rather
than being silently ignored: a config that *claimed* an assumption the run did not apply
would poison the §4 provenance block, which is that block's whole purpose.
`combats_per_day` is validated `== 4` — `DayRunner.run_day` hardcodes a four-combat day,
so the field records the denominator (§5.2) but cannot yet vary.

### 3.2 `BuildAdapter` — the per-build seam

```
BuildAdapter:
    name:              str
    available_levels() -> list[int]
    option_schema()    -> dict            # axis name -> allowed values / default
    build(config, rng) -> (DayRunner, Roster)
    describe()         -> dict            # resolved build parameters for provenance
```

Adding a build = writing an adapter (typically ~20 lines wrapping the existing
factory) and registering it. No evaluation-layer code changes. This mirrors the
project's standing rule that new content should never force engine edits.

### 3.3 `Roster` — role tags, not tuple positions

```
Roster:
    characters: list[Entity]     # the build's own actors — a LIST from day one
    summons:    list[Entity]     # created allies (Silvertail's beast)
    allies:     list[Entity]     # non-commanded party members
    enemies:    list[Entity]
```

**`characters` is a list even though it has length 1 today.** §7's AoE-share and
ranged-kiting toggles are both explicitly blocked on multi-character party support
(`enemy_model.md` §10). Designing the plural in now is free; retrofitting it after
reports, an artifact schema, and a website all assume a single character is not.

**The build column vs roster total distinction is structural, permanent, and never
collapsed** (the session-17 decision, generalized): the headline DPR is always the
character's own column, and any party/summon total is reported *beside* it under a
different name. This is what stops a headline number from silently changing meaning
when a build gains a summon.

### 3.4 Enemy independence — the enemy is not a property of the build

**Decision (user, s43). Character-build assumptions and enemy assumptions must be fully
independent.** Today they are not, and the coupling is data-level, not cosmetic. Three
distinct enemy concerns live inside the *character* build modules:

1. **The enemy's stat block.** `war_angel.LEVELS[13]` carries `enemy_ac`, and
   `enemy_attack = {attack_bonus: 11, damage: 28, n_attacks: 3, char_target_prob: 0.40}`
   — hardcoded in the character's own level table.
2. **Which enemy model is used at all.** War Angel and Starfire Scion construct
   `ScriptedEnemyPolicy`; Silvertail constructs `BaselineEnemyPolicy` (the per-level table
   plus the census bands). **The three builds do not currently face the same enemy model.**
3. **Whether the enemy acts.** The switch is `LEVELS[level].get("enemy_attack")` — so
   "at what level does the enemy fight back" is presently a *character-build* property.

**Why this is load-bearing, not tidiness.** A War Angel L13 number and a Silvertail L8
number are measured against enemies drawn from different sources under different models.
Cross-build comparison — the entire purpose of a build-agnostic framework (§1) — is not
valid today. No amount of report formatting fixes that; it has to be fixed at the seam.

**The resolution (user, s43).** The framework grows its **own enemy-construction seam**,
built *in parallel and deliberately redundantly* while the existing factories stay intact
for benchmarking. `RunConfig.enemy` / `enemy_options` become live; the adapter's `build()`
is told which enemy to install. Once the standardized enemy is in place, the enemy
material is **migrated out of the character factories and the baked-in path is deleted**.

**This is transitional, not a permanent two-mode split.** An earlier draft of this section
argued for keeping a "guide-replication" mode alongside the standardized one. That was
wrong on both halves — see §11.

**Requirement while both paths exist:** provenance must record *which* enemy the run used,
and reports from the two paths must not be silently compared. This is the same rule §5.2
already applies to `fixed_length` vs `finite_hp` — an existing pattern, not a new one.

---

## 4. Provenance — parameters *and* code

Every report embeds the block that makes it interpretable and reproducible:

```
Provenance:
    config:          RunConfig            # as requested
    resolved:        dict                 # as ACTUALLY used (see below)
    engine_commit:   str                  # git SHA
    engine_dirty:    bool                 # uncommitted changes present
    schema_version:  str                  # artifact schema (§9)
    generated_at:    ISO-8601 timestamp
```

**`resolved` vs `config` is the load-bearing distinction (user, s42).** A config of
`soft_factor=None` must be recorded as `0.5, from enemy_stats.SOFT_FACTOR`; band save
weights must be recorded as the actual weights drawn from the frozen table, not as
"default". Otherwise the assumptions page documents nothing.

This requires a small protocol addition: **`BaselineEnemyPolicy.describe_parameters()
-> dict`** returning its effective knobs, and the analogous `BuildAdapter.describe()`.
Both are pure reads and cannot affect a die roll.

**`engine_commit` is not optional.** Artifacts are committed and displayed by a static
site over time; without the code version there is no way to tell whether two reports
are comparable or separated by an engine change. It cannot be reconstructed after the
fact.

**This block is the source for the model-description / baseline-assumptions page** —
generated, never hand-maintained.

---

## 5. The report and the metric registry

### 5.1 A closed, declared metric set

Metrics are **registered, not incidental**. Each declares:

```
MetricDef:
    name:         str
    unit:         str          # "damage/round", "count/day", "fraction", …
    denominator:  str          # explicit — see 5.2
    source:       str          # which §13 channel / ledger it derives from
    definition:   str          # one line, human-readable
```

Three payoffs: the metric set stays deliberate (same philosophy as the closed verb set
and §13's closed channel vocabulary — extend like adding a verb, not casually); it *is*
the website's data dictionary; and it forces every denominator to be stated.

### 5.2 Denominators — the comparability trap

DPR today is `damage / (combats_per_day × rounds_per_combat)` = a fixed 16 rounds.
Two rules, both recorded in provenance:

- **A control-lost turn STAYS in the denominator.** That is precisely how control
  pressure manifests as reduced DPR. Removing it would make control free.
- **`fixed_length` is the standard basis; `finite_hp` is an alternate mode.** Emergent
  fight length changes the denominator to `total_rounds`, which makes those numbers
  silently incomparable to the 4×4 baseline that is the entire point of the exercise
  (memory `standardized-dpr-baseline-not-realism`: finite-HP is BUILT but
  DE-PRIORITIZED, comparison basis only). The mode is flagged prominently in the
  artifact, and mixed-mode comparisons are refused rather than silently rendered.

### 5.3 Headline vs panel

**No composite build score** (user decision, s42). A single ranked number would bake in
offense/resilience weightings that are contestable and would hide exactly the
assumptions the provenance block exists to expose.

- **Headline:** character-column DPR.
- **Panel beside it:** damage taken, control turns lost/reduced, saves forced/failed by
  type, typed damage mitigated, limited resources per day, concentration uptime/breaks.
- **Separate, never merged into the headline:** roster/party total, per-summon columns.

**Amendment (user, s44): summon attribution is a declared AXIS, not a fixed rule.**
The original rule — a summon's damage never enters the headline — protected against a
build's number silently changing meaning when it gained a companion. That protection is
real, but the rule overreached: whether a summon's damage is the summoner's damage is a
modelling CHOICE. Most published build evaluations count it as the caster's, because the
summon is what the caster's action economy bought; but when the question is "does casting
this summon beat casting that spell", the separated columns are what make the comparison
legible. Both readings are wanted, at different times.

So `RunConfig.attribution` selects it: `"character"` (the default and historical basis) or
`"character_and_summons"`. **Allies are excluded under both** — an ally is a party member
the build does not command, so its damage was never the build's to claim. The toggle
changes which number is the HEADLINE, never which numbers exist: `summon_dpr` and
`party_dpr` stay registered and identical under both modes. The mode is recorded in
provenance, and — like `mode` and the enemy path — reports under different attributions
must not be compared, because it changes what the headline MEANS rather than its value.

One definition serves every metric that means "the build's output" (`RunConfig.own_roles`),
so the headline, its per-combat decomposition and the typed-composition family cannot drift
apart. `damage_taken_per_round` deliberately does NOT follow it: a summon soaking hits is a
benefit reported in its own column, not a cost to fold into the character's.

### 5.4 Output kinds — scalar / keyed breakdown / distribution (LOCKED, s46)

§5.1 declared a metric set but only ONE output kind: a scalar carrying
`(value, n, stderr, converged)`. The registry grew to 51 entries under that single
shape, and the s46 review found that **25 of them were not 25 quantities** — they were
three keyed breakdowns with the key flattened into the metric NAME (`damage_share_acid`,
`save_fail_rate_dex_save`). That is the shape problem this section settles, and it is
settled BEFORE §9 serialization because §9 says a website will be built against the
artifact schema, and retrofitting a shape after artifacts exist is the expensive path.

**The decisive argument is not row count.** Flattening puts the key inside the name, so
every downstream consumer has to parse `damage_share_acid` back into `("acid",)` to
render a composition bar or a tidy CSV. A tidy CSV wants `metric, key, value` columns;
a website wants a vector it can iterate. Both want the key as DATA.

#### The three kinds

**1. Scalar** — `MetricDef`, exactly as §5.1 declares it. One quantity, one number,
one standard error. **The headline is always a scalar** (§5.3's "exactly one headline"
only means something if it cannot be a cell of something larger).

**2. Keyed breakdown** — `BreakdownDef`: ONE quantity over a CLOSED key space, where the
key space is a product of named `Dimension`s (`ability × channel`, `source_role ×
context`, `damage_type`). Four properties are load-bearing:

- **Every cell is a real estimate.** A cell carries its own `(value, n, stderr,
  converged)` from the same `statistics.py` machinery — a breakdown is not a dict of
  bare floats.
- **Availability is PER CELL, not per breakdown.** This is what lets the control-channel
  cells keep their own "unmeasurable until the §13 step-5 enemy seam" reason while the
  damage-channel cells of the same breakdown report normally, and what lets the
  `summons` cell of a role-keyed breakdown say "this build's roster has no summons"
  (§3.4's honesty requirement, preserved through the collapse).
- **The denominator is a template over the key.** `save_fail_rate[dex_save|control]`
  divides by the dex control saves actually forced, not by the family total. This
  absorbs the hand-written per-key denominator family the flat registry needed.
- **Margins are declared, not derived downstream.** A margin is a key tuple with `*` in
  the collapsed positions (`save_fail_rate[*|control]` is the old
  `control_save_fail_rate`). Margins are computed here because a consumer holding N
  correlated cell estimates CANNOT reconstruct the aggregate's standard error — see the
  survival rule below. The same numerator function serves cells and margins, because
  `*` maps to "no filter" in the telemetry read-outs.
- **CROSSING IS A DECLARATION, not a default** (`BreakdownDef.crossed`, added at the end
  of the s46 review). A multi-dimensional breakdown either materializes the full grid
  (**crossed**) or materializes each dimension's own marginal profile (**independent**).
  A grid must earn its cells: crossing multiplies them, and a cell whose denominator is
  structurally near-zero is a permanently-unmeasured row a renderer still has to lay out.
  - `save_fail_rate` is **independent**: the per-ability profile and the damage/control
    split are the two questions anyone asks, while "dex saves forced by CONTROL
    specifically" almost never has a surviving denominator. 8 cells, not 12+9.
  - `healing_by_source` is **crossed**: a summon healing under fire is a different fact
    from a summon healing at leisure, so the cross-tab IS the quantity.
  - **An independent breakdown's cells do not partition its total** — each dimension
    covers the whole quantity on its own, so summing every cell double-counts. That is a
    second reason the total is a declared margin and never something a renderer adds up,
    and it is asserted as a test.

**3. Distribution** — the third kind, **SEAM RESERVED, NOT BUILT (s46)**. §14's
distribution-shape deferral stands: a quantile is not a ratio, has no delta-method
standard error, and needs order-statistic or bootstrap intervals. What s46 fixes is that
the artifact reserves a `distributions` section from `schema_version` 1, so the work can
land later without a schema break. Designing the estimator remains scheduled for after
§9 serialization.

#### The survival rule for a prune (s46)

The obvious rule — *derivable ⇒ cut* — is wrong, and the review found the
counter-example immediately: `concentration_breaks_per_day` equals
`concentration_checks_per_day × concentration_break_rate` EXACTLY in value, but its
standard error is not reconstructible by a consumer holding the other two (that needs
the covariance, which only this layer sees). The same holds for every margin.

> **A row survives if someone reads it AND (it is not derivable, OR its uncertainty
> matters and cannot be reconstructed downstream).** Derivable-and-nobody-reads-it is
> the cut.

Under that rule the s46 prune removed exactly ONE row outright —
`typed_damage_per_round` (= `dpr × typed_damage_share`, and nothing reads it; the share
is the interpretive quantity and the gate on reading the type breakdown at all).
Everything else that "disappeared" became a cell or a declared margin.

#### What the review settled, family by family

| family | before | after |
|---|---|---|
| damage columns (`party`/`summon`/`ally_dpr`) | 3 scalars | `dpr_by_role` breakdown, `[*]` margin = party |
| damage taken (character / summon) | 2 scalars | `damage_taken_per_round_by_role` breakdown |
| saves (totals + per-channel + per-ability) | 16 scalars | 2 INDEPENDENT breakdowns over `ability`, `channel` (8 cells + total each) |
| damage-type composition | 15 scalars | 1 breakdown keyed `damage_type` + `typed_damage_share` scalar |
| per-combat DPR | 4 scalars | `dpr_by_combat` breakdown |
| healing (§ healing.md §8) | — | 3 scalars + `healing_by_source` keyed `source_role × context` |

**51 declarations → 22** (15 scalars + 7 breakdowns), and **51 estimated rows → 66
cells**. The first draft of the review crossed the saves dimensions and landed at 90
cells; the user's call at the end of the pass was that the grid did not earn them, which
is what `crossed` exists to express. The declarations are what humans maintain, and they
more than halved.

#### Two rules a breakdown ENFORCES structurally

- **`healing_by_source` declares NO margin over `context`.** `healing.md` §11.1 found
  the corpus does most of its healing out of combat by preference, so healing under fire
  and healing at leisure are different quantities. Refusing the margin means no cell in
  the artifact ever sums them — the rule is enforced by the SHAPE, not by a comment
  someone can ignore. (Collapsing `source_role` is fine and is declared.)
- **`damage_share` declares no margin at all** — its total is 1.0 by construction, so a
  margin would be a fabricated row. `typed_damage_share` is the meaningful aggregate and
  is a separate scalar with a different denominator.


---

## 6. Statistical treatment

### 6.1 Common random numbers (paired comparisons) — default ON

When comparing toggle A vs toggle B, independent seeds mean the difference carries the
variance of *both* runs. Running both on the **same seed stream** cancels the shared
noise and collapses the variance *of the difference* — frequently worth 10–100× in
effective sample size for exactly the sensitivity analysis §7 exists to support.

**Decision: paired seeding is the default for any comparison.** Every config in a
comparison group is run from the same base seed, so both scenarios see the same
combat times, the same SR placement, and the same dice stream wherever the two runs
have not diverged. The pairing is **recorded in provenance** so a reader knows a
reported delta is paired (and its stated interval means the paired thing).

Designed in now because it is nearly free (reset the seed per config) and awkward to
retrofit once artifacts exist.

**Correction (s44, MEASURED): in this engine the pairing is worth ~1×, not 10–100×.**
Five paired comparisons at 300 days each, comparing the paired standard error of the
delta against the independent `sqrt(seA² + seB²)`:

| comparison | delta | paired se | independent se | variance reduction |
|---|---|---|---|---|
| Starfire L15, FoM → Fire Shield | +3.132 | 0.2493 | 0.2700 | 1.17× |
| Starfire L15, `with_party` on | +0.004 | 0.2729 | 0.2765 | 1.03× |
| Silvertail L10, `mortal_beast` on | +0.019 | 0.1208 | 0.1177 | 0.95× |
| Silvertail L10, `beast_effect=bless` | −0.061 | 0.1151 | 0.1174 | 1.04× |
| Silvertail L10, `zone_effect` on | +5.601 | 0.1609 | 0.1586 | 0.97× |

Row 2 is the diagnostic one: a toggle that moves DPR by **0.004** still carries the
full 0.27 standard error. If pairing were working, a near-inert change would show a
tiny delta *and* a tiny interval.

**Why.** `SeededRNG` wraps ONE numpy generator, so all dice everywhere are a single
tape read in order. The moment scenario B draws one more or one fewer die than A,
every subsequent draw in B is offset by one position on that tape — and a tape read
at a shifted offset is statistically no better than a fresh one. Pairing is therefore
perfect up to the first divergence and worthless after it, and divergence normally
happens in round 1 of combat 1 of day 1. The inert-toggle case still pairs exactly
(delta `0 ± 0`), which is why the mechanism tests pass: the machinery is right, the
engine cannot feed it.

**The prerequisite for the real factor: RNG SUBSTREAMS.** Give each source of
randomness its own stream (`numpy.random.SeedSequence.spawn()`), keyed per entity or
per (entity, purpose). Then "the enemy's attack roll in round 3 of combat 2" draws
the same value in both runs no matter what changed about the character's spell, and
the enemy's entire contribution to the variance cancels exactly. **This is not a
tweak**: it changes the dice every existing run consumes, so every seeded baseline
moves and the §12 bit-identical parity proof against `validation.py` breaks. It gets
its own roadmap step and its own decision record (§13 step 8).

Pairing stays the DEFAULT meanwhile. It is never worse than independent seeding, it
costs nothing, and it becomes valuable the moment substreams land.

### 6.2 Every scalar metric carries uncertainty

`(value, n, stderr, converged: bool)` — **for every metric, not just DPR.** Metrics
converge at wildly different rates: DPR is fast, but rare events (concentration
breaks, crit-gated riders, control failures against a high-save build) can be badly
under-converged at a day count that looks generous for DPR. A site that displays a
noisy rare-event number without an interval invites over-reading it.

The convergence flag is a declared heuristic (e.g. relative stderr below a threshold,
plus a minimum event count), recorded in the metric registry.

---

## 7. Control applied at runtime (supersedes `enemy_model.md` §6 v1)

**Decision (user, s42): the character's output is scaled at RUNTIME, and the lost/
reduced turn counts are ALSO reported.** Both readings, not one.

### 7.1 Why runtime rather than post-hoc

Post-hoc `raw_DPR × (1 − lost_fraction)` has two defects that runtime application does
not:

1. It assumes **every turn is worth the same**. Losing the nova turn is not losing a
   cantrip turn.
2. It implicitly **spends the resources of a turn that never happened**. A genuinely
   lost turn should leave the slot available for later.

### 7.2 What is built — and what stays deferred

`resolve_control_save` (`verbs.py:581`) already computes the closed-form expected
affected turns and records them; it applies nothing. The change is to apply that same
closed-form quantity, **not** to build the stateful engine:

- **Applied:** a per-entity *affected-turns account* drawn down deterministically.
  Whole suppressed turns skip the character's turn entirely (so no resources are spent
  — the point of 7.1.2); the fractional remainder scales that boundary turn's output.
  `soft` turns scale output by `soft_factor` (default `0.5`, `enemy_stats.SOFT_FACTOR`).
- **Still deferred to §10:** the full `StatusSet` save-ends re-roll engine with rolled,
  variance-carrying durations. We keep the mean-field expected duration, so **no new
  variance is introduced** — the model stays low-variance per §1 of the enemy model.

### 7.3 The documented approximation

The **fractional boundary turn** is an honest wrinkle: a turn scaled to 60% output
still spends its resources, because it is a real turn that happened at reduced effect.
Only fully-suppressed turns preserve resources. This is a deliberate mean-field
simplification of the same family as the closed-form duration itself, and is recorded
as such rather than hidden.

### 7.4 Consequences to reconcile

- `enemy_model.md` §6 ("no status object; the reporting layer applies `soft_factor`")
  and §10's `soft_factor` deferral entry both need updating to point here.
- `resolve_control_save`'s docstring states the reporting layer applies the factor;
  that becomes only half true.
- **This moves DPR baselines whenever the control channel is ON.** It is default OFF,
  so no existing validated baseline shifts — but any run with `control=True` will now
  report lower DPR than the same run before this change, by design.

---

## 8. §8 coverage map

| §8 output | status |
|---|---|
| DPR (character column) | available — damage ledger |
| damage taken; per-(source,target) columns | available — ledger |
| damage reduced / typed mitigation | available — §13 mitigation channel (s39) |
| saves forced by type; failures by type and % | available — §13 saves channel |
| control turns lost / reduced | available — §13 control channel (s40) + §7 above |
| limited resources per day / per combat | available — §13 economy channel |
| concentration share and breaks | available — §13 economy channel |
| party / summon / ally damage columns | available — `damage_by_source`, `party_total` |
| **attack-roll counts: hits, crits, hit %, crit %, attacks at advantage and %** | **NOT available — needs a new channel (below)** |
| **average damage per use / on-hit / on-crit of each ability** | **NOT available — deferred (below)** |
| share of turns under specified statuses | partial — control covered; general status uptime needs `StatusSet` sampling |
| HP recovered | partial — no dedicated channel today |

### 8.1 New: an `attacks` telemetry channel (this arc)

Hits and crits are computed in `resolve_attack_roll` (`verbs.py:277`) and **discarded**.
Adding a fifth §13 channel — `attacks: {actor → forced / hit / crit / at_advantage}` —
is one record call at an existing decision point, and it unlocks hit %, crit %, and
advantage %, which are core §8 outputs and among the most diagnostic numbers for
understanding *why* a build's DPR is what it is.

Per §13's rule, this is a **deliberate** channel extension, documented like adding a
verb — not an ad-hoc field.

### 8.2 Deferred: per-ability damage attribution

`DamageEvent` carries no ability label, so per-ability averages would require threading
a label from `Choice` through to `DamageEvent` — a wider change touching every damage
path. **Deferred with the seam named** (`Choice.label → DamageEvent.label`), and
flagged as the *next* increment rather than a maybe: under a cross-build framework,
per-ability attribution is how you explain where a build's damage actually comes from,
so its value goes up, not down.

---

## 9. Artifact schema and the output pipeline

```
sim → EvalReport (structured) → artifact (JSON + tidy CSV) → analysis (R) / static site
```

**The firm architectural line: the sim never knows about the website.** The contract
is the serialized artifact with a versioned schema; the site is a downstream consumer.
This is the same separation as the engine knowing nothing about specific spells.

- **Artifact unit = one run record** (one `RunConfig` → one report). A sweep is a
  *collection* of records plus a manifest/index. No sweep-cube schema is needed, and an
  interactive site later requires no schema change (user, s42: static for now,
  interactive is a possible downstream goal).
- **JSON** is the faithful form — nested provenance, per-metric `(value, n, stderr,
  converged)`.
- **Tidy long CSV** is the analysis form — one row per (run, metric), flat, directly
  loadable in R. Renders from the same `EvalReport`, so it cannot drift from the JSON.
- **Console table** is a third renderer, not a special case.
- **`schema_version`** is mandatory, because a site will be built against it.

### 9.1 The artifact schema (LOCKED s47, `schema_version` 1)

Locked BEFORE the writer was built, per the per-feature ritual's step 4 — the rule s46
added for exactly this session. The unit is one run record; a sweep is a directory of
them plus a manifest (step 7).

```json
{
  "schema_version": 1,
  "kind": "run_record",
  "run_id": "war_angel@L13-8f2c1d0a4b6e7c95",
  "config_hash": "8f2c1d0a4b6e7c95",
  "warnings":   [ {"code": "...", "message": "..."} ],
  "provenance": { "...the whole §4 block..." },
  "results": {
    "headline": "dpr",
    "scalars":       [ ROW, ... ],
    "breakdowns":    [ {"name": ..., "cells": [ROW...], "margins": [ROW...]}, ... ],
    "distributions": []
  },
  "data_dictionary": { "scalars": [...], "breakdowns": [...], "distributions": [] }
}
```

**Three sections from version 1, the third reserved and empty.** `distributions` is
present and `[]` because §5.4's third kind is a reserved seam: §14's estimator lands
later without a `schema_version` break. `MetricRegistry.distributions()` already returns
`[]` for the same reason, so the reservation is one contract, not two.

**One ROW shape** serves scalars, breakdown cells and margins — the same fields in the
same order, so a consumer writes one parser:

| field | meaning |
|---|---|
| `metric` | the flat cell name (`save_fail_rate[dex_save\|*]`) |
| `breakdown` / `key` / `is_margin` | `null` for a scalar; for a cell, the breakdown name and the key as a **dict of dimension → value**, never a string to parse |
| `unit` / `denominator` / `group` | the declaration, so a row is readable without the dictionary |
| `status` | **the closed three-state vocabulary** (below) |
| `value` / `stderr` / `ci95` | `null` unless `status == "measured"` |
| `n` / `n_events` / `converged` / `note` | the §6.2 payload |

**The three report states survive serialization DISTINCTLY** (§3.4), as one `status`
field over a closed vocabulary, because collapsing any two of them is the failure the
whole layer is built to avoid:

- `measured` — the run produced a number.
- `unavailable` — the run structurally *cannot* produce it; `note` carries the reason.
- `unmeasured` — available, but the denominator was zero (no charisma save was forced).

`value` is `null` for both non-measured states. **A serializer must never write 0 for
either** — §3.4: a zero for control resilience reads as "this build resists control
perfectly", which is the opposite of what is known.

**Comparability warnings are TOP LEVEL, not buried in provenance.** §4's
`coverage.comparability_warning` is the authority, but a reader who has to open the
provenance block to find out that two artifacts are incomparable will not. The
`warnings` array carries a closed `code` vocabulary a site can style:

| code | raised when |
|---|---|
| `comparability` | always — names this run's resolved `mode` / `attribution` / `enemy_path`, the three that change what the headline MEANS |
| `coverage_gap` | any `coverage` entry is not resolved (today: the enemy side, until §13 step 5) |
| `engine_dirty` | the working tree had uncommitted changes: the artifact is not reproducible from its `engine_commit` |
| `precision` | `day_tier == "quick"` — an iteration run, not a publishable one |
| `unconverged` | ≥1 measured metric fails its own declared heuristic |

**The summing trap is a FIELD, not a comment.** An uncrossed breakdown's cells do not
partition its total — each dimension covers the whole quantity, so adding every cell
double-counts. The artifact therefore carries `sum_rule` on each breakdown, over a closed
two-value vocabulary:

- `cells_partition_total` — crossed; the cells are disjoint and sum to the margin.
- `cells_overlap_do_not_sum` — uncrossed (`save_fail_rate`, `saves_forced_per_round`);
  a renderer must read the declared margin and must never add cells up.

Cells and margins stay in **separate lists** in the JSON and are flagged `is_margin` in
the CSV, so the two can never be concatenated by accident. Margins belong to the
estimating layer (§5.4's corollary) and appear in the artifact only because they were
computed there.

**The tidy CSV gets one column per DIMENSION NAME** — the union over the registry's
breakdowns (`ability`, `channel`, `damage_type`, `role`, `source_role`, `context`,
`combat`), derived from the registry rather than hardcoded. Empty means *this row is not
keyed by that dimension*; `*` means *margin over it*; the two are different facts and get
different cell contents. The run-identifying columns repeat on every row, which is what
makes a sweep's CSVs concatenate into one frame. Booleans are written `TRUE`/`FALSE` and
non-measured values are written empty, so R reads them as `logical` and `NA` rather than
as text and as zero.

**What is NOT serialized:** `EvalReport.influence` — a per-day vector per metric, which
at 200k days would be the bulk of the artifact for a quantity only a paired comparison
consumes (§6.1). A comparison artifact is its own shape and its own decision, deferred.

The **data dictionary is embedded by default**, so a single artifact is self-describing:
a site or an R script renders units, definitions and refused-margin notes without
importing the Python registry. §5.1's "the registry IS the data dictionary", delivered
across the process boundary.

---

## 10. Sweeps, caching, day counts

- **Sweeps are declared in YAML**, not Python — configuration is data (matching the
  abilities-as-data / policies-as-code split), so a scenario is committable, diffable,
  and displayable next to the results it produced.
- **Caching keyed by a hash of `(resolved config + engine_commit)`.** Re-running a
  sweep recomputes only what changed. Execution stays **single-process** for now:
  correctness and reproducibility first; parallelism only if sweeps actually become the
  bottleneck (it interacts with RNG determinism, so it is not a free add).
- **Day-count tiers**, recorded in provenance so a reader knows the precision of what
  they are looking at:

  | tier | days | use |
  |---|---|---|
  | `quick` | ~2,000 | iteration, smoke checks |
  | `standard` | ~50,000 | matches today's `validation.py` default |
  | `publication` | ~200,000+ | committed artifacts / site content |

---

## 11. Baselines as a separate registry

`target_dpr` currently lives inside `war_angel.LEVELS`. A target is a **reference**, not
a property of the build. Pulling baselines into their own registry lets one run be scored
against a Treantmonk baseline (memory `treantmonk-baselines-for-build-eval`) or another
build's report — without touching build data, and without a build implicitly owning the
standard it is judged by.

**Correction (s43): the existing `target_dpr` values are NOT an external reference.** The
user wrote all 33 documents in `design/build-guides/` *and* the R prototype, so every
target in the build data traces to the user's own hand calculation. (CLAUDE.md described
the guides as "curated," which reads as third-party and caused exactly this mistake; the
wording is fixed.) Reproducing those numbers was a **one-time bootstrapping check** — "can
this machinery reproduce a careful hand calculation?" — asked and answered across ~40
sessions and the test suite. It is not a standard to keep re-meeting, and
**guide-replication is retired** (§3.4).

Two consequences for this registry. First, an external number plugged in later (e.g. a
Treantmonk figure) is a **reference point, not a target to match**: it was produced under
its author's own enemy assumptions, so the meaningful comparison is to recreate that build
and run it against *our* standardized enemy. Second, after this retirement the project has
**no external validation source at all** — everything is internal consistency plus face
validity. That is not a reason to keep the old targets; it is a reason for the provenance
block (§4) to make the model-relative nature of every number explicit.

A baseline entry is `(source, build, level, metric, value, provenance)`; scoring is a
report-layer operation.

---

## 12. Validation framing

Per `validate-mechanism-not-build-value` and `enemy_model.md` §11 — tests assert the
**mechanism**, never a DPR value:

- an adapter's roster tags the right entities by role; a build with a summon reports
  distinct character / summon columns and never merges them into the headline;
- the framework **reproduces `validation.py`'s numbers exactly** for War Angel at equal
  seed and day count (this is the correctness proof for the whole layer);
- paired seeding produces byte-identical dice streams for two configs that differ only
  in an inert toggle;
- provenance `resolved` reports the actual value where the config passed `None`;
- an artifact round-trips JSON → report → tidy CSV with matching values;
- the cache returns a hit for an identical config and a miss when the engine commit
  changes;
- control-at-runtime: a fully suppressed turn deals zero damage **and spends no
  resources**; telemetry's lost/reduced counts still match the closed-form expectation;
- **enemy independence (§3.4):** two different builds at the same level, configured with
  the same `enemy` + `enemy_options`, face an enemy with identical resolved parameters;
  and a run records which enemy path produced it, so the two are never silently compared.

We do NOT assert that any build's evaluated DPR is "correct".

**What replaces the retired guide targets (§11).** Dropping guide-replication removes the
project's only end-to-end "did an engine change move the physics?" signal — the unit tests
check mechanisms, not the composite. Three things carry that load instead:

1. **Exact golden values.** Once each build runs against the standardized enemy, pin the
   resulting per-level numbers as exact regression goldens. This is a *stricter* check than
   the ±10% band it replaces: it detects any drift, not just large drift. It asserts
   "nothing changed", never "this value is correct" — so it stays inside the
   `validate-mechanism-not-build-value` rule.
2. **The L1–4 closed-form check, kept.** At those levels the enemy is passive and only its
   AC matters, so expected DPR is computable in closed form by hand. That check verifies
   the attack pipeline against arithmetic and is independent of who authored what — it just
   needs its expected values recomputed for the standardized enemy's AC.
3. **The epistemic note, stated once in the outputs.** See §11: no external validation
   source remains, and the provenance block is where that is said rather than left implicit.

---

## 13. Build sequence

1. ~~`RunConfig` + `BuildAdapter` + `Roster` + the registry; adapters for the three
   existing builds. Prove it by reproducing `validation.py`'s War Angel numbers.~~
   **DONE (s43)** — `src/evaluation/{config,adapters,build_adapters,roster,runner}.py`,
   39 mechanism tests in `tests/test_eval_framework.py`. The proof PASSED EXACTLY:
   bit-identical mean *and* stderr against `validation.run_level` across all 16 War
   Angel levels (400 days) and at 5,000 days on L13/L16, the enemy-strikes-back regime.
   `describe()` already does real §4 resolution on the build side (Starfire's
   `primal_strike_unarmed=None` → the level row's `raw_unarmed`, with the source path
   named); the enemy side (`describe_parameters()`) waits on the `enemy_options` seam.
   `evaluation/runner.mean_dpr` is an explicit, in-code-marked stand-in for step 2.
2. ~~`EvalReport` + metric registry + statistics (stderr, convergence, paired
   seeding).~~ **DONE (s44)** — `src/evaluation/{statistics,metrics,report}.py`, 49
   mechanism tests in `tests/test_eval_metrics.py`. `runner.mean_dpr` is gone; the §12
   parity proof was re-pointed at the registry's `dpr` metric and still matches
   `validation.run_level` bit-identically. 51 registered metrics. Two estimator kinds
   (fixed vs random denominator) unified through per-day influence values. Three
   channels declare themselves UNAVAILABLE rather than emitting zeros (control, for
   two different per-build reasons; mitigation; and — until the same session wired it
   — the resource ledger). Provenance reports the build side resolved and says
   plainly that the enemy side is not. **Ex-post additions the same session:** the §13
   resource ledger went live (7 scheduler `consume` sites); the mitigation channel
   gained an ACTOR dimension and now records every typed hit, giving outgoing
   damage-type composition; and per-combat / opening-round shape metrics landed off
   the existing ledger.
3. Serialization: JSON + tidy CSV + console renderer; `schema_version`.
4. The `attacks` telemetry channel (§8.1).
5. **The enemy-construction seam (§3.4)** *(inserted s43, between the original steps 4 and
   5)* — `RunConfig.enemy` / `enemy_options` become live; adapters are told which enemy to
   install; the standardized enemy is built alongside the factories' baked-in one, then the
   baked-in path is migrated out and deleted. Carries the three §12 replacements for the
   retired guide targets. **Sequenced here because it is a hard prerequisite for step 6:**
   control lives on `BaselineEnemyPolicy(control=True)`, and War Angel uses
   `ScriptedEnemyPolicy`, which has no control channel at all — so War Angel's control
   resilience, a core resilience-panel metric, is unmeasurable until this seam exists.
   Placed after step 4 so the two enemy paths can be compared as artifacts, not by eye.
6. Control-at-runtime (§7) + the `enemy_model.md` §6/§10 reconciliation.
7. Sweep YAML + config-hash caching + baselines registry.
8. **RNG substreams** *(added s44)* — per-entity / per-(entity, purpose) generators via
   `SeedSequence.spawn()`, the prerequisite for §6.1's paired seeding to actually buy
   precision. Needs its own decision record: it moves every seeded baseline and breaks
   the §12 bit-identical parity proof, so it must be a deliberate, versioned change.
   Sequenced last because nothing else depends on it and the intervals reported before
   it are honest, just wider than they could be.

`src/validation.py` **stays as-is** throughout as the regression check, and is migrated
onto the framework only once step 1 reproduces its numbers exactly.

---

## 14. Deferrals (named, not silent)

- **Per-ability damage attribution** — needs `Choice.label → DamageEvent.label` (§8.2).
- **Parallel sweep execution** — interacts with RNG determinism; only if sweeps become
  the bottleneck (§10).
- **Interactive website** — the static artifact schema does not preclude it; no schema
  change required later (§9).
- **General status-uptime metric** — §8 asks for "share of turns under specified
  statuses" in general; only the control channel is covered today. Needs `StatusSet`
  sampling at turn boundaries.
- **HP recovered / healing — NO LONGER DEFERRED: promoted to the next work item
  (user, s44). Semantics LOCKED in `design/healing.md`.** Its *metrics* still wait on
  the output-kinds design below, because healing-by-source is a keyed breakdown and the
  registry does not have that shape yet. Summary of the finding that promoted it: §8 lists this as a
  missing channel, which understates it: **healing is not modelled at all.**
  `Entity.heal()` exists and has ZERO callers in `src/`; no verb, no `Choice`, and no
  policy path produces healing. What looks like healing in the build data is not — War
  Angel's Prayer of Healing is modelled purely as a short-rest ENABLER (it buys an extra
  SR's worth of resource recovery: see the `war_angel.LEVELS` resource comments), never as
  HP restored. So "track healing, including healing provided by summons" (user, s44) is
  three pieces of work, not a metric addition:
  1. a healing EFFECT in the verb/effect layer that a `Choice` can produce and resolution
     can apply, with its own place in the damage/heal phase ordering;
  2. a **source-attributed** ledger — `(source, target)` like the damage ledger, NOT an
     aggregate counter, so "healing provided by the summon" is answerable and the s44
     roster-scoping lesson is not repeated;
  3. only then the metrics, which should carry the same `attribution` axis as damage
     (§5.3) so a summon's healing counts as the build's under the same declared mode.
  **Needs its own decision first**: healing is only meaningful against a finite-HP model,
  and the standardized basis is fixed-length with a threshold-HP character (memory
  `standardized-dpr-baseline-not-realism`), so what a healing number would even MEAN in the
  4×4 comparison basis has to be settled before any of it is built.
- **Full stateful control durations** — remains the `enemy_model.md` §10 fidelity
  deferral; §7 above deliberately keeps the mean-field expectation (§7.2).
- ~~**OUTPUT KINDS — scalars vs keyed breakdowns vs distributions**~~ **SETTLED AND
  BUILT (s46) — see §5.4.** The registry modelled ONE output kind, so 25 of its 51
  entries were three keyed breakdowns flattened into one row per key and ~6 more were
  algebraically derivable. §5.4 locks the three kinds (scalar / keyed breakdown /
  distribution), the per-cell availability and key-templated denominator rules, the
  declared-margin rule, and the SURVIVAL RULE that replaced "derivable ⇒ cut" (a margin's
  standard error is not reconstructible downstream, so derivability alone never justifies
  a cut). Result: **51 declarations → 22** (15 scalars + 7 breakdowns), one row dropped
  outright (`typed_damage_per_round`). Healing's §8 metrics were the first customer and
  the test of whether the kinds work.
- **Distribution shape (quantiles, spread)** *(added s44; SEAM RESERVED s46, ESTIMATOR
  STILL DEFERRED)* — every scalar today is a mean with a standard error, which describes
  where the average lands and says nothing about consistency: two builds with identical
  mean DPR and very different day-to-day spread are indistinguishable in this report. A
  quantile is not a ratio and has no delta-method standard error, so it does not fit
  `MetricDef` — it needs a parallel `DistributionDef` kind with order-statistic or
  bootstrap intervals. **s46 named it as §5.4's third kind and reserved its artifact
  section so it can land without a `schema_version` break; the estimator itself is still
  scheduled for AFTER step 3**, once serialization has fixed the artifact shape.
- **Per-(round, source) damage ledger** *(added s44)* — `CombatResult.damage_received`
  is per round but keyed by target only; `damage_by_source_target` is attributed by
  source but per-combat cumulative. So no metric can say "how much did the CHARACTER
  deal in round 1". `party_dpr_opening_round` is labelled party-scoped for exactly this
  reason. Unblocks a character-scoped front-loading metric.
- **Per-entity resource keying** *(added s44)* — the §13 economy channel keys
  `resources_spent` by resource NAME and sums across the roster, so a summon build
  cannot separate the master's slots from the companion's. A deliberate channel
  extension when a build makes it matter, mirroring the actor dimension the mitigation
  channel gained in s44.
- **Multi-character party** — `Roster.characters` is plural in anticipation, but no
  build produces more than one character yet; unblocks §7's AoE-share and kiting
  toggles when it lands (§3.3).
- **Enemy material inside the character factories** — `enemy_ac` / `enemy_attack` rows and
  the choice of enemy policy class still live in each build's `LEVELS` table (§3.4).
  Scheduled for removal at step 5, not open-ended: the redundancy is transitional, and
  the baked-in path is deleted once the standardized enemy is in place.
