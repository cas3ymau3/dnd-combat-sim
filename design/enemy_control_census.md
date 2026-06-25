# Supplementary CONTROL-SAVE census — methodology (LOCKED v1) + codebook

> Status: **CODEBOOK LOCKED (s34). CENSUS COMPLETE (s35, 2026-06-25) — 218 control
> rows across all four bands in `reference/data/monster_profile_control.csv`; see
> "Census status" at the bottom for headlines + the two execution-time methodology
> calls.** This is
> the `design/buff_primitive.md`-style design-first contract for the supplementary
> control-save census — the empirical grounding for the **control-save channel** in
> `design/enemy_model.md` §6, which today runs on a designer prior. It is the
> companion to `design/enemy_profile.md` (the *damaging* census): it **mirrors** that
> note's locked decisions (CR bands, instance weighting, Chrome `fetch()` workflow,
> resumability) and restates only the **deltas** for control. Read `enemy_profile.md`
> first; this note assumes it.
>
> Project memory: `enemy-profile-empirical-direction`,
> `standardized-dpr-baseline-not-realism`, `validate-mechanism-not-build-value`,
> `design-first-for-cross-cutting-primitives`, `build-selection-prioritizes-capacity`.
>
> Decisions confirmed with the user (s34): (B) **separate `control.csv`**; (C) scope
> = **save-forcing control, including damage-coupled**; (F) weighting =
> **cadence-discounted prior** (divergence from the damaging census, justified below).

---

## Why a SECOND census

The damaging census (`enemy_profile.md`) deliberately tagged only **damaging**
actions — pure-control abilities (no damage) were never put on the books (its
"keep damage-only" decision). But the thing that makes mental saves frightening in
play is exactly the **pure control**: lose your turn (paralyzed / stunned /
dominated), and those abilities deal no damage. So the damaging census's save-type
weights are honestly **CON/DEX-dominant** (poison, breath, area), which is the
**wrong instrument** for pricing a build's investment in mental-save protection
(Aura of Protection, save proficiency, "can't be charmed", advantage-on-saves,
magic resistance). `enemy_model.md` §6 closes that gap with a separate control-save
channel; this census replaces that channel's **designer prior** with measured data:
`control_save_prob`, `control_save_weights`, and the `hard_vs_soft` split, per CR
band.

This census is **bounded** (only save-forcing control abilities — a minority of
statblock content) and runs over the *same* 510 statblocks the damaging census
already fetched, so it is much smaller than the damaging census.

---

## The core questions (tabulated AS A FUNCTION OF CR BAND)

Per control action, per CR band:

1. **Control frequency** — expected control saves the average band monster forces
   per round (→ `control_save_prob[band]`).
2. **Save type** — of control abilities, the STR/DEX/CON/INT/WIS/CHA shares (→
   `control_save_weights[band]`; DISTINCT from the damaging save weights).
3. **Severity** — the HARD (turn-wasting) vs SOFT (output-reducing) split (→
   `hard_vs_soft[band]`), and the condition-frequency histogram.

The defensive half (condition-immunity prevalence — which prices whether a control
condition even lands) is **already** in `monster_profile_monsters.csv` from the
damaging census; this census does not re-tag it.

---

## Methodology decisions — LOCKED (deltas from `enemy_profile.md`)

These MIRROR the damaging census unless noted:

1. **Full census, not a sample.** Same 510 monsters (D&D Beyond `filter-source=147`),
   same index, same resumability. (Same as damaging census.)
2. **CR bands `0-4` / `5-10` / `11-16` / `17+`.** Identical bands; band sizes
   303 / 126 / 46 / 35. (Same.)
3. **Source = 2024 Monster Manual ONLY** (`source=147`). (Same.)
4. **Scope = SAVE-FORCING control (incl. damage-coupled).** DELTA — see "What counts
   as a control ability" below. The unit of a tag is a *save that defends against a
   condition*, which maps 1:1 onto §6's mechanism (the character rolls its real save
   vs `save_dc`; fail → hard/soft outcome).
5. **Weighting = cadence-discounted instances/round.** DELTA from the damaging
   census's no-discount rule — see "The weighting rule" below.

---

## What counts as a "control ability" (scope — LOCKED, fork C)

**A control ability is one that forces a saving throw to avoid (or end) a HARD or
SOFT condition (see the classification table), whether or not it also deals damage.**

Decompose each statblock action into its channels and tag the **control channel**
here:

- **INCLUDE — pure-control saves** (the core target the damaging census skipped):
  Petrifying Gaze (CON-save-or-petrified), Frightful Presence (WIS-save-or-
  frightened), Horrifying Visage, Dominate, charm gazes, Hold/paralysis effects, a
  maw that forces a STR save or be restrained/swallowed. No damaging row exists for
  these in `raw.csv`; they appear **only** here.
- **INCLUDE — damage-coupled control** (the ability also deals damage, but forces a
  save against a condition): Mind Blast (psychic damage **+** INT-save-or-stunned),
  a bite that hits then forces a CON-save-or-poisoned (`resolution=both` in the
  damaging census). Tag the **control half** here for its condition, regardless of
  it having a damaging row in `raw.csv`. The two censuses measure orthogonal things
  (damage instances vs control instances); an ability legitimately appears in both.
  *No double-count within either channel.* This is what makes `control.csv`
  **self-contained** — §6 reads ONLY this file for control pressure.
- **EXCLUDE — no-save, auto-on-hit riders**: "on a hit, the target is knocked prone
  / grappled" with NO save. These are not part of §6's save channel; they remain
  captured as `riders` on the damaging action in `raw.csv` (a positioning/to-hit
  refinement for a later arc, `enemy_model.md` §9). Tagging them here would balloon
  the census (every slam/bite has one) and mismatch the save mechanism.
- **EXCLUDE — `NONE`-severity conditions** (deafened): no combat-output effect; do
  not tag.

**Seeding efficiency:** the existing `raw.csv` rows with `resolution ∈ {save, both}`
and a non-empty `riders` already half-identify the damage-coupled control; start
from those per monster, then add the pure-control abilities the damaging census
skipped entirely.

**Attack-roll-only control (no save).** A handful of pure-control effects land on an
attack roll with no save (rare). v1 EXCLUDES them — §6 is a save channel. Flag in
`notes` if encountered; revisit in v2 only if prevalence is non-trivial.

---

## HARD vs SOFT classification (LOCKED, fork D)

§6 has two failure branches: **HARD** = the turn is wasted (character output → 0);
**SOFT** = output × `soft_factor`. Because we tag the *actual condition*, the census
**measures** the hard/soft split per band rather than inferring it from save type —
this is a strict upgrade over §6's "mental→hard / physical→soft" prior skew (which
becomes the fallback only).

| condition | severity | rationale |
|---|---|---|
| paralyzed | **HARD** | can't act; auto-crits if hit |
| petrified | **HARD** | can't act; incapacitated + more |
| stunned | **HARD** | can't act; auto-fail STR/DEX saves |
| unconscious | **HARD** | can't act |
| incapacitated | **HARD** | can't take actions/bonus actions/reactions |
| charmed | **HARD** | can't attack the charmer (= the single enemy dummy) → wasted turn |
| dominated (Dominate ●) | **HARD** | enemy controls the turn |
| frightened | SOFT | disadvantage on attacks while source in sight; can't approach |
| blinded | SOFT | disadvantage on attacks |
| restrained | SOFT | speed 0, disadvantage on attacks |
| poisoned | SOFT | disadvantage on attacks and ability checks |
| prone | SOFT | disadvantage on attacks (unless adjacent) |
| grappled | SOFT | speed 0; 2024 disadvantage vs non-grappler (mostly out of scope — usually no-save) |
| exhaustion | SOFT | 2024: −2×level penalty to d20 tests; output-reducing (variable — note level) |
| deafened | NONE | no combat-output effect — **do not tag** |

**Multiple conditions on one ability** (e.g. "restrained, and at start of its turns
takes … and is frightened") → tag the **most severe** for the `hard_soft` field
(HARD wins), list all in `condition`. The most-severe rule keeps the lost-turn
estimate honest.

**Duration / "save-ends" is NOT modeled in v1** (`enemy_model.md` §10 defers
control-as-real-status). A `duration` note column is captured for a future fidelity
pass but does not affect v1 weighting — each control instance is a single
hard/soft draw at the per-round rate.

---

## Save keying (LOCKED, fork E)

Record the forced save ability verbatim from the statblock: `STR` / `DEX` / `CON` /
`INT` / `WIS` / `CHA`. Typical control mappings (tag what the statblock says, not
this table): charm/fear/dominate → WIS or CHA; paralysis/hold → WIS; petrify →
CON; Mind Blast → INT; restrain/grapple/swallow → STR or DEX. The instance-weighted
distribution of these becomes `control_save_weights[band]`.

---

## The weighting rule (LOCKED, fork F — DIVERGES from the damaging census)

`instances_per_round` = **cadence-discounted** expected control-save instances the
ability contributes in a representative round. **This deliberately diverges from the
damaging census's "per-use 1, no discount" rule**, because control is
**cadence-dominated**: the strongest control (Dominate, Mass Suggestion, many
paralysis effects) is mostly recharge or limited-use, and counting a 1/Day Dominate
at 1.0/round would wildly inflate `control_save_prob` (§6's headline knob) at
exactly the high-CR tiers where that control lives. (The damaging census could
accept its over-count because damage is magnitude-weighted and recharge AoEs are a
minority of damage mass; for control the recharge/limited abilities ARE the mass.)

**3-bucket cadence prior** (baked into `instances_per_round` at tag time; the
`recharge` column preserves raw cadence for a v2 re-weight):

| cadence | `instances_per_round` factor |
|---|---|
| at-will / every-round (gaze, aura, Multiattack-embedded control) | **1.0** |
| recharge (4–6 / 5–6 / 6) | **0.5** |
| limited-use (1/Day, 2/Day, …) | **0.25** |

Then, mirroring the damaging census's structural rules:

- **Choice-of / random-menu control** (a gaze menu, "choose one of N effects") →
  split the (already cadence-discounted) instance weight evenly across the options
  (damaging refinement 7).
- **Multiattack-embedded control** (e.g. "uses Frightful Presence and makes two
  attacks") → at-will (1.0), it fires every round.
- **Legendary control actions** → tag NATIVE control legendaries (e.g. a Frightful
  Presence or gaze legendary) at the cadence factor; do NOT tag "uses Spellcasting
  to cast [control spell]" recasts (mirror damaging refinement 6). Documented
  undercount, consistent with the damaging census.
- **Per-monster, one row per control ability.** A monster forcing two different
  control saves gets two rows; the per-round expectation respects single-action
  economy (damaging refinement 9) — if two control options compete for the same
  action, split as a 50/50 mix (each at ×0.5 of its cadence factor), per the at-will
  alternative rule (refinement 10/1b).

`recharge` column values: `at-will` / `4-6` / `5-6` / `6` / `1/day` / `2/day` / … —
**captured verbatim** so the discount is reproducible and re-weightable.

---

## Table schema (LOCKED, fork B — a SEPARATE file)

A **new** action-level table; the monster-level table is **reused unchanged**.

### `reference/data/monster_profile_control.csv` (one row per control ability)

| field | values |
|---|---|
| `monster`, `cr`, `cr_band` | keys (denormalized for aggregation; same as `raw.csv`) |
| `section` | `action` / `bonus` / `reaction` / `legendary` / `lair` / `trait` / `multiattack-embedded` |
| `ability` | e.g. `Frightful Presence`, `Mind Blast`, `Petrifying Gaze` |
| `save_ability` | `STR/DEX/CON/INT/WIS/CHA` |
| `save_effect` | `negates` / `partial` / `ends` (save ends the condition) / `other` |
| `condition` | `;`-joined condition(s) imposed (paralyzed, frightened, …) |
| `hard_soft` | `hard` / `soft` (most-severe rule for multi-condition) |
| `also_damages` | `y`/`n` (y ⇒ this ability ALSO has a row in `raw.csv`; bookkeeping only, never joined) |
| `instances_per_round` | cadence-discounted numeric weight (see rule) |
| `recharge` | raw cadence: `at-will` / `5-6` / `1/day` / … |
| `duration` | freetext note (e.g. `save-ends`, `1 min`, `until-removed`) — captured, NOT used in v1 |
| `notes` | freetext |

**Why a separate file (not extending `raw.csv`):** the damaging aggregator
(`monster_profile.py`) computes damage-type / resolution / reach / AoE distributions
over *every* row of `raw.csv`. Injecting control rows (no `damage_types`, no reach
in the damaging sense) would force a control-filter into every one of those
functions or pollute the damage denominators. A separate table keeps the two
censuses orthogonal and each aggregator path clean — the same reason the schema
fields here don't reuse the damage-centric ones (`damage_types`, `save_effect`
half/negates).

**Monster-level table:** **reused as-is** — `monster_profile_monsters.csv` already
carries all 510 monsters with `cr_band` and `condition_immunities`. The control
census adds **no** monster-level columns. (Condition-immunity prevalence already
prices whether a control condition lands, via the damaging census's defense half.)

---

## Aggregation outputs (per CR band → feeds `enemy_model.md` §6)

A new tabulator path (a function in `src/builds/monster_profile.py` reading
`monster_profile_control.csv`, OR a sibling module — implementation call at wiring
time #1). Per band, instance-weighted by `instances_per_round`:

1. **`control_save_prob[band]`** = Σ `instances_per_round` over the band ÷
   `n_monsters` in the band = **expected control saves the average band monster
   forces per round**. §6 consumes this as the per-round control-save probability
   (Bernoulli; if a band's rate exceeds 1, §6 may treat it as an expected count).
   Expected to **rise with CR** (control density climbs at the top tiers).
2. **`control_save_weights[band]`** = STR/DEX/CON/INT/WIS/CHA instance-weighted
   distribution. **Replaces** §6's community-rule-of-thumb prior
   (`DEX ≈ WIS > CON > INT ≈ CHA ≈ STR`); expected to lift WIS/CHA/INT relative to
   the *damaging* save weights (which are CON/DEX-dominant by design).
3. **`hard_vs_soft[band]`** = HARD-instance share vs SOFT-instance share.
   **Replaces** §6's "mental→hard / physical→soft" inferred skew with the measured
   split. Optionally also report `hard_vs_soft` **conditioned on save type** (to
   keep §6's per-save severity skew, now empirical).
4. **Condition-frequency histogram** per band (byproduct, analogous to the damaging
   `rider_freq`): which conditions dominate the control mass per tier.

**Freeze decision (defer to wiring #1):** whether these three quantities are
appended as columns to the existing frozen `monster_profile_by_band.csv` (one band
row carries every knob — convenient for the policy's single read) OR frozen to a
sibling `monster_control_by_band.csv` (keeps damaging vs control provenance fully
separate, in the spirit of `enemy_model.md` §8) is a #1 call. Recommendation:
**append columns** to the one band table the policy already reads; document the
provenance split in the header. **Note:** this makes §6's control channel
**census-derived**, so `enemy_model.md` §8's line "the control prior is NOT in this
census-derived table — keep it separate" is superseded once this census lands (the
*prior* becomes the fallback/toggle default only).

---

## Census workflow (LOCKED — reuses `enemy_profile.md` §"Census workflow" verbatim)

Identical Claude-in-Chrome `javascript_tool` `fetch()` workflow: same index (already
regenerable in one call), same statblock fetch (`[class*="stat-block"]`, full slug
href, `(async()=>{…})()` wrapper, no query-string URL returns), same batch-of-6,
same resumability (append rows; record DONE bands in "Census status" below; the
aggregator tabulates whatever rows exist). **Only delta:** for each statblock, scan
for **save-forcing control** (per the scope above) and tag into
`monster_profile_control.csv` instead of (in addition to) the damaging tags. Because
the damaging census already fetched every statblock, and `raw.csv`'s
`save`/`both`-resolution rows seed the damage-coupled control, the per-monster effort
is small.

**Required setup for the #3b scrape** (the next session, NOT this design pass):
Claude-in-Chrome ON + the full per-machine allowlist (CONFIG LEDGER). After #3b +
#2 complete, that setup is **torn down** (allowlist reset, Chrome off) — the planned
end of the empirical arc; everything downstream is pure Python.

---

## Census status

- **Codebook:** LOCKED (s34). **Census: COMPLETE (s35, 2026-06-25).** All four bands
  tagged into `reference/data/monster_profile_control.csv` — **218 control rows**.
- **Bands DONE:** **11-16 (36 rows / 25 of 46 monsters), 17+ (28 rows / 19 of 35),
  5-10 (55 rows / 48 of 126), 0-4 (66 native rows / 61 monsters)** + **33 cross-band
  spell-cast rows** (see below).
- **Headline (preview aggregation, instance-weighted):** `control_save_prob` RISES
  monotonically with CR exactly as predicted — **0-4 = 0.19 / 5-10 = 0.38 / 11-16 =
  0.54 / 17+ = 0.68** control saves per band-monster per round. **`control_save_weights`:
  WIS is now a top-2 save (30-35% across bands), CON also high** — the mental-save mass
  the damaging census's CON/DEX-dominant weights could not price (the whole reason for
  this second census). `hard_vs_soft` varies by band (hard 26-53%; 17+ is soft-dominant
  74%, driven by dragon/giant frightened+prone).
- **Batched with:** the #2 v2 cross-band reconciliation of the damaging census (done
  same session; see PROGRESS Track 1 #3b/#2).

### Scanner + two methodology calls made during execution (s35)

A browser-side scanner (`enemy_profile.md` §"Census workflow" `fetch()`) collected, per
statblock, ability blocks containing **both** a `... Saving Throw:` line **and** a
control-condition keyword, across `<p>` AND `<ol>`/`<li>` (eye-ray menu) layouts. Two
calls beyond the codebook, both documented here as part of the executed census:

1. **Non-standard conditions excluded.** Effects that reduce output but impose **no
   tracked condition** (Confusion, Slowing Ray, "bewildered", "grafted"-as-such) are NOT
   tagged — consistent with the codebook's named-condition table. Documented undercount of
   confusion/slow-style control.
2. **Spell-cast control IS tagged (refinement-10 symmetry) — the one scope extension.**
   Control delivered by **casting a spell** (Frightful Presence = *Fear*; "At Will: Hold
   Person"; Succubus *Dominate Person*; Vampire *Charm Person*) has no inline `Saving
   Throw:` line, so the native scan missed it. Rather than leave it as the codebook's
   "don't tag recasts" undercount (which is scoped to **legendary** recasts, mirroring
   damaging refinement 6), these were tagged for **non-legendary** actions per the
   damaging census's **refinement 10** (which symmetrically tags at-will/limited spell-cast
   *damage*): a dedicated spell-NAME scan over all 510 statblocks → a spell->save/condition
   lookup (all WIS saves) at refinement-10 cadence (at-will alternative 0.5 / limited-use
   0.25). 33 rows. Legendary spell-recasts remain untagged (codebook rule preserved).
   **Caveat for a v2 verification pass:** dragon Frightful-Presence coverage was data-driven
   (only Black/White carry *Fear*, Silver *Hold Monster* — Red/Blue/Green/Brass/Copper/
   Gold/Bronze verified to have none); and generic caster *Spellcasting-list* control beyond
   the matched spell set may be lightly under-scanned.

**False positives dropped (per band, recorded so the census is reproducible):** Evasion /
Avoidance / Prone-Deficiency self-referential traits; Aura-of-Authority / Marshal-Undead
auras (no save); targeting-prerequisite conditions ("a creature **Grappled by** … " +
HP-drain: Vampire/Vampire-Spawn Bite, Glabrezu Pummel, Tree Blight Gnash, Aboleth Consume
Memories, Succubus Draining Kiss); situational finishers on an already-grappled/
incapacitated target (Mind Flayer Extract Brain, Intellect Devourer Steal Body, and swallow
finishers where the monster already has other save-control: Behir, Kraken, Tarrasque).

---

## Downstream sequence

1. **This note** — control codebook design (s34, #3a). DONE.
2. **#3b — run the control census** (+ #2 damaging reconciliation, batched). **DONE
   (s35):** 218 rows in `monster_profile_control.csv`. Chrome + allowlist torn down at
   session close (the planned end of the empirical arc).
3. **Metrics design**, then **#1 — wire** `control_save_prob` / `control_save_weights`
   / `hard_vs_soft` into the §6 control channel (default OFF/neutral so no baseline
   drift), mechanism-validated (`validate-mechanism-not-build-value`).
4. Outputs/reporting (#4), then the first full build evaluation (#6).
