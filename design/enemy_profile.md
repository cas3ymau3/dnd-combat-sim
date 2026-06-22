# Empirical enemy profile — design SEED (not yet locked)

> Status: **SEED / planning (2026-06-22).** This note records the GOAL, the
> decisions to settle, and the agreed sequencing for the next major arc. The
> first working session FILLS IN the locked methodology + the profile tables
> (this is a deliberate `design/buff_primitive.md`-style design-first pass — see
> the project memory `enemy-profile-empirical-direction` and CLAUDE.md's
> "design-first for cross-cutting primitives" working agreement). Until those are
> filled in and the user signs off, nothing here is binding.

---

## Why we're doing this

The sim's purpose is **standardized DPR AND defensive-resilience estimates** vs
the conventional 4×4-round content-creator baseline. So far almost everything is
offense or self-buffs; the **defensive half is barely modeled** because the enemy
deals a single undifferentiated melee damage stream. You cannot price resistance
to a damage type, Deflect Attacks/Missiles, Evasion, Uncanny Dodge, a save
proficiency, or a Fire-Shield-style intercept without a realistic distribution of
*what is actually coming at the character*.

It also **fixes the offensive denominator**: if a real share of monsters are
ranged kiters, a melee build's true uptime is lower than the implicit "everyone
stands in melee and trades for 4 rounds" assumption — a systematic dishonesty in
every melee DPR number we produce.

So we build an **empirical profile of the "average" 2024-Monster-Manual enemy**
and use it to give the enemy realistic offensive variety and (later) positioning.

---

## The core questions (tabulate AS A FUNCTION OF CR)

For damaging monster abilities, across the MM:

1. **Damage type** — share dealing acid / bludgeoning / cold / fire / force /
   lightning / necrotic / piercing / poison / psychic / radiant / slashing /
   thunder. (Analyze **physical B/P/S separately from elemental/special** — see
   below.)
2. **Resolution** — share using an **attack roll** vs **forcing a saving throw**
   vs **both** (attack-then-save, or save-then-attack).
3. **Save type** — of the save-forcing abilities, the share forcing
   STR / DEX / CON / WIS / INT / CHA saves.
4. **Range** — share **melee** vs **ranged** (and abilities that are either).

Plus, cheap-to-grab-now / expensive-to-re-scrape extras:

5. **AoE vs single-target.**
6. **Rider conditions imposed** (prone / grappled / restrained / frightened /
   poisoned / blinded / stunned / …) — these drive the value of save
   proficiencies and condition immunities.
7. **High-CR legendary / lair-action cadence** (action-economy realism at the top
   end).

---

## Methodology decisions to LOCK in the first working session

1. **CR-band, do NOT global-average.** The sim is per-level; elemental, ranged,
   and save-based abilities climb steeply with CR while low-CR monsters are mostly
   physical melee. A single average misleads a per-level model. Proposed bands:
   **0–4 / 5–10 / 11–16 / 17+** (revisit granularity once data is in).
2. **Physical (B/P/S) vs elemental/special, separated.** The raw damage-type
   histogram is dominated by B/P/S and says little; the **elemental/special slice
   is what defensive features bite on**, so report it as its own distribution.
3. **Tagging unit / weighting.** Per-ability over-counts a rare rider and
   under-counts a monster's main multiattack. v1: tag each damaging ability,
   **weight by multiattack count**, ignore recharge probabilities (flag as a
   known simplification — the honest unit is "expected damage instances per
   round").
4. **Census vs stratified SAMPLE.** The MM is ~500 stat blocks. A **CR-stratified
   random sample (~10–15 per band)** likely yields a robust profile for a fraction
   of the Claude-in-Chrome effort; census later if a band looks noisy. *(Working
   lean: sample-first — confirm with the user before scraping.)*

---

## The corollary that is bigger than the data (downstream arc, NOT this slice)

"X% ranged → model them moving away" is an **engine lift**, not just analysis. The
zonal model already exists (`Entity.zone`, `move_entity`, the melee/ranged `range_`
axis made live in the session-27 attack-taxonomy migration), but **no enemy policy
uses it tactically yet**. Turning the ranged share into kiting / open-distance /
chase-or-eat-the-ranged-attack tradeoffs + an opportunity-attack model is its own
multi-session arc. Named here so the profile is not mistaken for finishing the job.

---

## Agreed sequencing toward the first TRUE build evaluation

1. **This arc, session 1: design note + profile tables.** Settle the methodology
   above, scrape a stratified MM sample via Claude-in-Chrome, produce the
   per-CR-band distribution tables, get user sign-off. (Output is DATA + a locked
   note, not engine code.)
2. **Wire the static profile into the enemy policy** — damage-type + save-type
   VARIETY first (cheapest win; immediately makes resistances / save-profs
   valuable). Validate as a MECHANISM, not a build-value claim.
3. **Positioning / kiting arc** (the melee/ranged share → movement model + OAs).
4. **Reporting / aggregation layer** — DPR-by-level curve + defensive summary
   (% turns under each status, damage taken, survivability) + the 4×4 baseline
   comparison. *(Existence in the current day_runner/reporting code is unconfirmed
   — check first.)*
5. **First honest end-to-end build evaluation** — War Angel (L1–13/14, the
   closest-to-complete target) with real output: offense (positioning-aware) and
   defense (profile-driven), against the baseline.

---

## Where data lands (proposed — confirm at build time)

- Raw per-statblock taggings and the derived per-CR-band distribution tables under
  `reference/data/` (alongside `monster_stats_by_level.csv`, which already supplies
  per-level AC / saves / to-hit / DC / dice and is the enemy accessor layer).
- An accessor in `src/builds/` (mirroring `enemy_stats.py`) that the enriched enemy
  policy draws the offensive-variety distributions from.
