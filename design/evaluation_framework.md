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

**3. Distribution** — `DistributionDef`: the SHAPE of a per-day quantity rather than
where its average lands. **SEAM RESERVED s46, ESTIMATOR LOCKED AND BUILT s48** — see
*Kind 3 in full* at the end of this section. The reservation held: the estimator landed
at `schema_version` 1, unchanged.

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

#### Kind 3 in full: the distribution estimator (LOCKED s48)

Every other output in this framework is a MEAN with a standard error. That says where
the average lands and nothing about consistency: two builds with identical mean DPR and
very different day-to-day spread are indistinguishable in everything above. A quantile
is not a ratio — it has no delta-method standard error — so it does not fit `MetricDef`
and needed this parallel kind. The shape was settled with the user BEFORE the estimator
was written (per-feature ritual step 4).

**A distribution is declared OVER a registered scalar, not as a new collected
quantity.**

```python
DistributionDef(name="dpr_distribution", over="dpr",
                statistics=(P10, P25, P50, P75, P90, IQR))
```

That single choice is what made the kind cheap, and four consequences are load-bearing:

- **Nothing upstream changed.** It reads the per-day samples `MetricSamples` already
  keeps for `dpr`, so the runner, the collector and both estimators are untouched — the
  same move `BreakdownDef` made in s46, which is the evidence that the three kinds
  really are one registry and not three.
- **The distribution and the scalar cannot disagree.** The mean of the per-day vector IS
  the scalar's value, to the last bit, because it is the same vector. A distribution
  declaring its own numerator could drift from the metric it claims to describe.
- **Eligibility is STRUCTURAL, not a judgement.** A distribution requires
  `Denominator.fixed == True`, checked at registration. A ratio metric has no per-day
  value at all — a day that forced no saves has no fail rate — so "the distribution of
  `save_fail_rate`" is not something to be careful about, it is something the registry
  REFUSES. This reuses the declaration `statistics.py` already branches on.
- **Unavailability is inherited.** If `over` is unavailable for a run, so is the
  distribution, with the same reason. §3.4's three states need no new vocabulary.

**THE STATISTIC SELECTS THE METHOD — it is not a per-distribution knob.** This is the
section's main structural decision, and it is the direct analogue of `Denominator.fixed`
selecting the estimator in `statistics.py`:

| statistic | interval method | why that one |
|---|---|---|
| `quantile(p)` — `p10`/`p25`/`p50`/`p75`/`p90` | **order statistic** (exact binomial) | A distribution-free interval exists in closed form. It is exact at every N, costs nothing, and draws nothing. |
| `iqr` = `p75 − p25` | **bootstrap** (percentile, 2000 resamples) | No closed form. Its uncertainty needs the covariance of the two quantiles — exactly what a consumer holding `p25` and `p75` cannot reconstruct. §5.4's survival rule, now applying to the third kind. |

Making the method a declared option would have invited choosing a bootstrap where an
exact answer was free. Deriving it also means **both branches have a real production
consumer**, which is what makes the two-method requirement testable rather than a
fixture built to exercise dead code (per-feature ritual step 5).

**The interval is ASYMMETRIC, and that is why it is carried as an interval.** A
quantile's order-statistic bounds are two order statistics straddling the estimate; they
are not `value ± 1.96·se`, and on a skewed daily distribution they are visibly not
centred. So a distribution row reports `stderr = null` and a real `ci95`. §9.1's locked
ROW shape already carries those as separate fields, which is why filling this seam needs
no `schema_version` break — the reservation was not merely a space in the JSON, it was a
row contract that already fitted.

**When the interval cannot be placed, say so rather than shrink it.** At small N the
binomial bound for an extreme quantile falls off the end of the sample (there is no
`X_(0)`). The honest report is a measured `value` with `ci95 = null`, a note naming the
cause, and `converged = false` — never a bound silently clamped to the sample minimum,
which would read as a precision the data does not have.

**Convergence needs its own heuristic.** `Convergence` is written for
`rel_stderr`/`min_events` and neither exists here, so `DistributionConvergence` mirrors
it term for term over the quantities that do:

| `Convergence` | `DistributionConvergence` | |
|---|---|---|
| `rel_stderr` | `ci_width_vs_spread` | `(hi − lo) / spread`, where `spread` is the SAMPLE's own p90 − p10 — **not** the point's value. See below. |
| `min_events` | `min_tail_observations` | `N · min(p, 1−p)`. The real guard: a `p90` off 60 days rests on six observations, however tight its interval looks |
| `min_days` | `min_days` | unchanged |

**Why the denominator is the sample's SPREAD and not the point's value (corrected
s48).** The first cut divided by `abs(value)`, mirroring `rel_stderr`. That criterion
is **not translation-invariant**, and the defect is not confined to values near zero —
it is wrong everywhere and merely becomes infinite there. Measured on
`net_damage_taken_per_round` (war_angel L13, 2000 days): adding a flat +100 to every
day, which changes nothing about the estimate's precision, moved the p90 criterion's
input from **0.0932 to 0.0147** — the same estimate looking 6.3× more precise for
being relabelled.

Dividing by the sample's own p90 − p10 is invariant to shift and to rescaling, needs
no declared constant, and asks the question a reader actually has: *is this interval
narrow compared with the spread it is describing?* The spread is computed ONCE per
distribution and shared by all its points, so a verdict that differs between p10 and
p50 says something about those estimates rather than about which denominator each got.
Two further properties:

- **It does real work rather than collapsing into a day count.** `width / spread` is
  roughly `C/√N` where `C` depends on the density at that quantile relative to the
  overall spread, so a tail legitimately needs more days than the median — at N=2000,
  war_angel L13 lands p50 at 0.044 and p10 at 0.074. Threshold **0.10**: the quick tier
  (2,000 days) clears it except for genuinely lumpy discrete tails, and the standard
  tier clears it by ~5×.
- **The degenerate case falls out instead of being special-cased.** `spread == 0` is a
  point mass, so the only readable interval is a zero-width one — which is exactly the
  rule the old criterion needed a separate `value == 0` branch to express.

**1-D in v1, but shaped so keying is additive.** A distribution is not crossed with a
breakdown key today. The s46 argument applies unchanged — a grid must earn its cells,
and `dpr_by_role × 3 roles × 6 statistics` is 18 rows nobody has asked to read. But the
row carries its statistic in the SAME `key` dict a breakdown cell uses
(`{"statistic": "p50"}`), so adding a dimension later is `{"role": "summons",
"statistic": "p50"}` and not a schema change.

**What earns a distribution (user, s48).** Two, deliberately:

| distribution | over | what it answers |
|---|---|---|
| `dpr_distribution` | `dpr` | offensive consistency — the headline's shape, the §14 question verbatim |
| `net_damage_taken_distribution` | `net_damage_taken_per_round` | defensive spike risk: the day you take a huge spike is the day you die, and a mean hides it. Also the branch where the quantity can be NEGATIVE (surplus healing), so `rel_ci_width` is exercised against a value that can straddle zero |

Considered and not taken: `external_healing_required_per_day` (heavily tied at zero for
most builds — honest but uninformative rows) and `party_dpr_opening_round` (party-scoped,
so not comparable to the headline anyway). Both remain one declaration away.

**Paired comparison on a quantile: DEFERRED, with the construction named.** §6.1's
machinery is built on per-day INFLUENCE VALUES, and a quantile has no influence-value
representation, so `paired_delta` does not extend to it. The correct construction is a
PAIRED BOOTSTRAP: resample day indices ONCE, apply the same index vector to both runs'
per-day vectors, recompute the difference of quantiles, and take percentiles of the
resampled differences — the pairing is preserved exactly because both runs are indexed
identically. It is not built because §6.1 MEASURED that pairing is worth ~1× in this
engine until RNG substreams land (§13 step 8), and because the comparison artifact is
its own deferred shape. Naming the construction makes this a known path rather than an
open question.

**The bootstrap draws, and it must never draw from the combat stream.** Per-feature
ritual step 3: any new dice source outside combat shifts the shared tape and kills §12's
bit-identical parity proof. The resampler therefore uses its OWN
`numpy.random.default_rng`, seeded from a stable hash of `(run seed, distribution name,
statistic label)` — reproducible across processes, and structurally incapable of
reaching `SeededRNG`. Resampling is also post-processing: it runs in `build_report`,
after the last die of the run has been cast.

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

**The MEASUREMENT SCALE is declared too, and it selects the criterion (s48).**
`rel_stderr` is only a precision statement for a quantity with a TRUE ZERO, where "the
standard error is 2% of the value" means something. `MetricDef.scale` makes that
explicit the same way `Denominator.fixed` selects the estimator:

- **`ratio`** (the default, and every metric but one) — DPR, counts, rates, shares,
  hit points restored. Zero is an absence. `se/|value|` as before.
- **`interval`** — a SIGNED quantity whose zero is a break-even point. Today only
  `net_damage_taken_per_round` (damage absorbed minus healing received; a negative
  value is surplus healing capacity). Relative error against one of these is a
  category error, not merely awkward: the value can sit near zero while the estimate
  is perfectly precise. The criterion instead asks whether the **sign is resolved**
  (`|value| ≥ 3·stderr`), because for a signed quantity that is the interpretive
  content — is this build net-positive or net-negative?

It is DECLARED rather than inferred from observed signs: whether a quantity *can* go
negative is a fact about what it measures, not about what one run happened to produce.

**What was tried and rejected:** judging the scalar's `stderr` against the per-day
sample's spread, the way a distribution does. For a MEAN that is degenerate — `se/sd`
is exactly `1/√N` — and the measurement confirmed it: `se/IQR` for `dpr` came out
0.01677 / 0.01676 / 0.01691 / 0.01692 across four different builds, because every
build's daily DPR is near-normal. It would have been `min_days` wearing a disguise.
The trick works for a quantile only because the density at the quantile and the
overall spread are independent facts about the shape.

**An ordering defect fixed at the same time.** `min_events` was checked BEFORE the
exact-estimate escape, so a rare-event metric that is deterministically zero could
never converge: `concentration_breaks_per_day` reads an exact `0.0 ± 0.0` on any build
that never concentrates and was flagged unconverged forever, while
`concentration_checks_per_day` — the identical number — was flagged converged because
it declares no event floor. The floor exists to catch the delta method being optimistic
on few observations, and there is no delta method to be optimistic about when the
variance is zero. An exact estimate now escapes first, which also subsumes the old
`value == 0` special case rather than sitting beside it.

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
    "distributions": [ {"name": ..., "over": ..., "points": [ROW...]}, ... ]
  },
  "data_dictionary": { "scalars": [...], "breakdowns": [...], "distributions": [...] }
}
```

**Three sections from version 1. The third was reserved empty at s47 and FILLED at
s48 — at `schema_version` 1, as promised.** A `distributions` entry is
`{name, over, unit, group, statistics, points: [ROW...]}`: the same declaration-then-rows
layout as a breakdown block, with `points` in place of `cells`/`margins` because a
distribution has neither. There is deliberately **no `sum_rule`** on it — quantiles are
not additive under any rule, so offering a field from that two-value vocabulary would
imply a choice exists. The CSV's `sum_rule` column is blank for these rows, which is the
same "blank means not applicable" convention the dimension columns already use.

A distribution's ROW is the one locked row shape, with three things worth stating:
`stderr` is **always null** (a quantile has no delta-method standard error), `ci95` is
**asymmetric** and is the only uncertainty the row carries, and `key` is
`{"statistic": "p50"}` — the same dict a breakdown cell uses, so a consumer's key parser
is unchanged and a later keyed distribution is additive. Two columns join the tidy CSV:
`statistic` (alongside the dimension columns, derived from the registry the same way)
and `method` (`order_statistic` / `bootstrap`, a meta column beside `sum_rule`), because
an asymmetric interval is unreadable without knowing how it was placed.

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
3. ~~Serialization: JSON + tidy CSV + console renderer; `schema_version`.~~ **DONE (s47)** — `evaluation_framework.md` §9.1 locks the schema; `src/evaluation/{artifact,console}.py` + 44 tests.
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
- ~~**Distribution shape (quantiles, spread)**~~ *(added s44; seam reserved s46, built
  s47)* — **SETTLED AND BUILT (s48) — see §5.4's "Kind 3 in full".** `DistributionDef`
  is declared OVER a registered fixed-denominator scalar, so the runner and both
  estimators were untouched; the statistic SELECTS the interval method (quantiles →
  exact binomial order statistics, IQR → percentile bootstrap), mirroring how
  `Denominator.fixed` selects the estimator; `DistributionConvergence` mirrors
  `Convergence` term for term (`rel_ci_width` / `min_tail_observations` / `min_days`).
  **The s46/s47 reservation held: it landed at `schema_version` 1 with no break.** Two
  distributions ship (`dpr`, `net_damage_taken_per_round`). Still open below: a PAIRED
  quantile delta, and keying a distribution.
- **Paired comparison ON A QUANTILE** *(added s48)* — §6.1's machinery runs on per-day
  influence values and a quantile has none, so `paired_delta` does not extend to it. The
  construction that WOULD work is named in §5.4 (a paired bootstrap over one shared
  resampled index vector). Deferred because §6.1 measured pairing at ~1× in this engine
  until RNG substreams land (§13 step 8), and because the comparison artifact is its own
  deferred shape — building a paired quantile interval now would buy nothing measurable.
- **A KEYED distribution** *(added s48)* — v1 is 1-D: quantiles of `dpr`, not quantiles
  of `dpr_by_role[summons]`. The s46 "a grid must earn its cells" argument applies
  unchanged. Non-blocking by construction: the row already carries its statistic in the
  same `key` dict a breakdown cell uses, so adding a dimension is additive rather than a
  schema change. The first real customer would be per-combat DPR spread, which also
  wants a note that four combats within a day are not independent replicates the way
  days are.
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
