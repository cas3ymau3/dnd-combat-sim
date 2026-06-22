# Empirical enemy profile — methodology (LOCKED v1) + profile tables

> Status: **METHODOLOGY LOCKED (2026-06-22).** The codebook, CR bands, weighting
> rule, data layout, and census workflow below are signed off and binding for the
> census. The **profile tables are IN PROGRESS** — being filled band-by-band as the
> census runs (pilot = CR 11–16 first; see "Census status" at the bottom). This note
> is the `design/buff_primitive.md`-style design-first contract for the enemy-profile
> arc (project memory `enemy-profile-empirical-direction`; CLAUDE.md "design-first
> for cross-cutting primitives").

---

## Why we're doing this

The sim's purpose is **standardized DPR AND defensive-resilience estimates** vs the
conventional 4×4-round content-creator baseline. So far almost everything modeled is
the character's offense or self-buffs; the **defensive half is barely modeled** because
the enemy deals one undifferentiated melee damage stream. You cannot price resistance
to a damage type, Deflect Attacks/Missiles, Evasion, Uncanny Dodge, a save proficiency,
or a Fire-Shield-style intercept without a realistic distribution of *what is actually
coming at the character*.

It also **fixes the offensive denominator on BOTH sides**:

- **Incoming side (enemy offense).** If a real share of monsters are ranged kiters, a
  melee build's true uptime is lower than the implicit "everyone stands in melee and
  trades for 4 rounds" assumption.
- **Outgoing side (enemy defense).** The enemy's **damage resistances / immunities /
  vulnerabilities** and **condition immunities** price the character's *damage-type
  choice and rider conditions*. A fire-heavy build looks great until you account for how
  many high-CR monsters resist or are immune to fire; a frightened-on-hit rider is worth
  nothing against the many things immune to Frightened. (Added to scope 2026-06-22.)

So we build an **empirical profile of the "average" 2024-Monster-Manual enemy** — both
its offense (what it throws) and its defense (what bounces off it) — and later use it to
give the enemy realistic variety and positioning.

---

## The core questions (tabulated AS A FUNCTION OF CR BAND)

**Enemy offense** (per damaging action):
1. **Damage type** — share dealing each of the 13 types, reported as **physical B/P/S
   vs elemental/special** first, then the elemental/special sub-distribution.
2. **Resolution** — attack roll vs save vs both vs auto.
3. **Save type** — of save-forcing abilities, the STR/DEX/CON/INT/WIS/CHA shares.
4. **Reach** — melee vs ranged.
5. **AoE vs single-target.**
6. **Rider conditions imposed** (prone/grappled/restrained/frightened/poisoned/…).
7. **Legendary / lair cadence** (action-economy realism at the top end).

**Enemy defense** (per monster):
8. **Damage resistances / immunities / vulnerabilities** — per type.
9. **Condition immunities** — per condition.

---

## Methodology decisions — LOCKED

1. **Full census, not a sample.** All ~510 monsters in the 2024 Monster Manual (D&D
   Beyond `filter-source=147`). A sample can't give good coverage across this many
   facets simultaneously (user call, 2026-06-22). The workflow below makes the census
   tractable and resumable across sessions.
2. **CR bands: `0-4` / `5-10` / `11-16` / `17+`.** Banding (not global average) because
   elemental/ranged/save abilities climb steeply with CR. Band sizes from the census
   index: **0-4 = 303, 5-10 = 126, 11-16 = 46, 17+ = 35** (510 total). Revisit
   granularity if a band looks internally noisy once data is in.
3. **Physical (B/P/S) vs elemental/special, separated.** The raw histogram is dominated
   by B/P/S; the elemental/special slice is what defensive features bite on, so report
   it as its own distribution.
4. **Weighting unit = expected damage INSTANCES per round** (not damage dealt). v1
   counts instances, so a breath weapon's big hit counts the same as one claw swing
   (documented simplification; v2 can move to damage-weighting). See the weighting rule.
5. **Source = 2024 Monster Manual ONLY.** D&D Beyond "Monster Manual" (NOT "Monster
   Manual (2014)" legacy, NOT AideDD/fandom). Source id `147`.

---

## The tagging codebook (LOCKED)

Two normalized tables. Monster-level (defensive) facts live in the monster table;
per-action (offensive) facts in the action table, keyed by `monster`.

### Table 1 — `reference/data/monster_profile_monsters.csv` (one row per monster)

| field | values |
|---|---|
| `monster` | name (size-variant statblocks counted separately, as the MM presents them) |
| `cr` | raw CR string (`1/8`,`1/4`,`1/2`,`1`…`30`) |
| `cr_band` | `0-4` / `5-10` / `11-16` / `17+` |
| `type` | creature type (Dragon, Fiend, Construct, …) |
| `size` | Tiny…Gargantuan |
| `damage_vulnerabilities` | `;`-joined types, or empty |
| `damage_resistances` | `;`-joined types, or empty |
| `damage_immunities` | `;`-joined types, or empty |
| `condition_immunities` | `;`-joined conditions, or empty |
| `has_legendary` | `y`/`n` (has a **Legendary Actions** section) |
| `legendary_action_count` | integer uses/round (0 if none) |
| `has_lair` | `y`/`n` (has a Lair / lair-action section) |
| `notes` | freetext |

### Table 2 — `reference/data/monster_profile_raw.csv` (one row per damaging action component)

| field | values |
|---|---|
| `monster`, `cr`, `cr_band` | keys (denormalized for easy aggregation) |
| `section` | `multiattack-swing` / `action` / `bonus` / `reaction` / `legendary` / `lair` / `trait` |
| `ability` | e.g. `Rend`, `Acid Breath (Recharge 5–6)` |
| `resolution` | `attack` / `save` / `both` / `auto` (both = attack-then-save or save-then-attack; auto = no roll, e.g. aura/automatic on grapple) |
| `reach` | `melee` (needs adjacency: Melee attack, ≤10 ft emanation) / `ranged` (deliverable at distance: Ranged attack, a save effect with a ft range, cone/line/sphere) |
| `aoe` | `y`/`n` (cone/line/sphere/cube/emanation/"each creature in…") |
| `damage_types` | `;`-joined of the 13 types this action deals |
| `save_ability` | `STR/DEX/CON/INT/WIS/CHA` or empty (for resolution ∈ {save, both}) |
| `save_effect` | `half` / `negates` / `other` or empty |
| `riders` | `;`-joined conditions imposed, or empty |
| `instances_per_round` | numeric weight (see rule) |
| `recharge` | `at-will` / `5-6` / `6` / `1/day` / `2/day` … (captured, NOT discounted in v1) |
| `notes` | freetext |

**Damage types (13):** acid, bludgeoning, cold, fire, force, lightning, necrotic,
piercing, poison, psychic, radiant, slashing, thunder. **Physical = {bludgeoning,
piercing, slashing}; elemental/special = the other 10.**

### The weighting rule (v1, LOCKED, flagged as a simplification)

`instances_per_round` = expected uses in a representative round at full action economy:

- **Multiattack swings** → their stated counts (the bulk of the mass). Multiattack
  itself gets NO row — it is a router; its counts land on the swing rows it names.
- **"Replace one/N attacks with X"** (e.g. "can replace one Rend with Spellcasting") →
  model the typical line as using the replacement once: reduce the base attack count by
  N and add N instances of X. (Adult Black Dragon → Rend ×2 + Melf's Acid Arrow ×1.)
- **Recharge AoEs / limited actions** (breath weapons, X/Day) → per-use count (usually
  1), NOT discounted by recharge probability — the documented over-count (v2: recharge
  expectation ≈ once per 2–3 rounds). `recharge` column preserves the truth.
- **Damaging reactions / auras / damaging traits** → 1 if reliably used each round,
  else 0 by judgment (recorded in `notes`).
- **Legendary actions** → best estimate of typical damaging uses/round (matters for
  bands 11-16 / 17+).
- **Multi-type single attack** (e.g. Rend = slashing + acid) → list ALL types in
  `damage_types`; in aggregation each type receives the row's full instance weight (so
  the unit is "instances of each damage type delivered per round").
- **Non-damaging actions** (pure control, buffs, Multiattack lines, Dominate with no
  damage) → NOT tagged in Table 2; their imposed conditions ARE captured via `riders`
  on the relevant damaging action when co-located, and pure-control riders can be noted.
  (v1 keeps the action table damage-centric; revisit if pure-control prevalence matters.)

---

## Aggregation outputs (per CR band, instance-weighted)

Produced by `src/builds/monster_profile.py` (pure raw→band tabulation; becomes the enemy
policy's accessor in the NEXT arc — not wired into the policy this session):

1. **Damage-type mix** — physical vs elemental/special headline split, then the
   elemental sub-distribution.
2. **Resolution** mix (attack/save/both/auto).
3. **Save-type** mix (among save & both rows).
4. **Reach** mix (melee/ranged).
5. **AoE vs single** share.
6. **Rider-condition** frequencies.
7. **Legendary/lair cadence** (# monsters with legendary actions, avg count, # with lairs).
8. **Damage res/imm/vuln prevalence** — % of band's monsters resistant / immune /
   vulnerable to each type (prices the character's damage-type choice).
9. **Condition-immunity prevalence** — % immune to each condition (prices riders).

Plus per-band monster count + tagging coverage.

---

## Census workflow (LOCKED — built for throughput + resumability)

Treat Chrome as a **text-fetch tool, not a vision tool**. All via the Claude-in-Chrome
`javascript_tool` (authenticated same-origin `fetch()` with `credentials:'include'`):

1. **Index build** (once; deterministic, ~26 fetches in one JS call). Page the list
   `/monsters?filter-source=147&page=N` (N=1.. until a page yields <20 rows). Per row,
   parse `div.info` → `{name, cr (.monster-challenge span), href (.monster-name a.link)}`.
   Dedupe by href. Result: the 510-monster worklist (id, name, cr, band). *(The site's
   CR-range filter is broken — it is ignored. Band yourself from the parsed CR. The
   list is alphabetical; statblock content is NOT in the list DOM — it loads via AJAX on
   expand, so do NOT try to click-expand; fetch the monster page instead.)*
2. **Statblock fetch + tag** (the bulk; batch ~6 monsters per JS call to stay under the
   tool's output cap). For each monster's full href (`/monsters/{id}-{slug}` — ID-only
   does NOT return the statblock), `fetch()` the page, parse the LARGEST
   `[class*="stat-block"]` element (the class suffix varies, so match by substring),
   take `innerText`, normalize whitespace. Tag per the codebook into the two CSVs.
3. **Resumability.** The census runs across many sessions. Append rows to the two CSVs;
   record which CR band(s) are DONE in "Census status" below. The aggregator recomputes
   from whatever rows exist, so partial bands still produce (partial) tables.

**Gotchas locked from the pilot:** `[class*="stat-block"]` not `.mon-stat-block` (class
varies); use the full slug href; returning query-string URLs from `javascript_tool` is
blocked by a safety filter (return names/ids/innerText, never raw `?`-bearing URLs);
top-level `await` in `javascript_tool` errors — wrap in `(async()=>{…})()`.

---

## Downstream arc (NOT this slice — named so the profile isn't mistaken for the finish)

1. **This arc, session 1: methodology note + profile tables** (DATA + locked note).
2. **Wire the static profile into the enemy policy** — damage-type + save-type variety,
   AND the enemy res/imm checks against the character's damage (cheapest wins). Validate
   as a MECHANISM, not a build-value claim. (Grounds the `SAVE_TYPE_WEIGHTS` /
   `SAVE_ROUND_PROB` placeholders in `enemy_stats.py`.)
3. **Positioning / kiting arc** — melee/ranged share → movement model + opportunity
   attacks. An engine lift (`Entity.zone`/`move_entity`/`range_` exist but no enemy
   policy uses them tactically yet); its own multi-session arc.
4. **Reporting / aggregation layer** — DPR-by-level curve + defensive summary (% turns
   under each status, damage taken, survivability) + the 4×4 baseline comparison.
5. **First honest end-to-end build evaluation** — War Angel (L1–13/14), offense
   (positioning-aware) + defense (profile-driven), against the baseline.

---

## Census status

- **Index:** built (510 monsters; CR-band counts above). Regenerable in one
  `javascript_tool` call via the step-1 workflow (not persisted as a file — the tagged
  CSVs are the record of what's done; TODO = any `source=147` monster not yet in them).
- **Bands DONE:** **11-16 (PILOT, 46 monsters)** — tagged 2026-06-22; aggregated by
  `src/builds/monster_profile.py`. Pilot simplifications applied (to revisit at scale,
  flagged in the rows' `notes`): (a) dragons' "replace one attack with a spell" option
  left unmodeled (Rend at full ×3); (b) beholder/death-tyrant eye-ray menus approximated
  (3 of ~10 rays/round, damaging rays at 0.3 each); (c) a few spell save-types/damage-
  types inferred (Giggling Magic, Baleful Command, Shadow Breath, Githyanki strike);
  (d) spellcasters' 1/Day damage spells omitted as negligible per-round; (e) pure-control
  actions (no damage) not tagged as rows — their conditions under-counted (beholder/sphinx
  especially). These need a methodology call before the full census (see PROGRESS NEXT).
- **Regroup decisions (user-confirmed 2026-06-22, binding for the full census):**
  - **Keep damage-only** — pure-control (no-damage) save actions are NOT tagged as rows.
    Condition-immunity prevalence (per monster) still prices riders; the offense table
    stays damage-centric.
  - **Approximate menu/choice attackers** — eye-ray menus stay at the 3-of-N weighting;
    dragons' "replace one attack with a spell" stays unmodeled. Both are a small share of
    total instances and are flagged in `notes`.
- **Bands TODO:** 0-4 (303), 5-10 (126), 17+ (35).

## Codebook refinements surfaced by the pilot (folded into the codebook above)

1. **Combined Immunities line.** 2024 statblocks put damage AND condition immunities on
   one `Immunities` line, split by `;` (e.g. "Acid, Poison; Charmed, Poisoned" → dmg-imm
   acid+poison, cond-imm charmed+poisoned). There is NO separate "Condition Immunities"
   line. Parse accordingly.
2. **`reach = both`** added (the seed's "either" case): "Melee or Ranged Attack Roll"
   attacks (very common in 2024 — Arcane Burst, Fiendish Burst, Ice Spear, …) get
   `reach=both` — they can operate at range, so they are NOT counted as melee-only uptime.
3. **Self-centered Emanation → `reach=melee`** (the monster is amid its targets);
   Cone / Line / Sphere / targeted-at-range → `reach=ranged`.
4. **"X of A OR Y of B in any combination"** → split 50/50 (A at X/2, B at Y/2).
5. **Special / conditional res-imm-vuln** (Rakshasa's "piercing from Bless-blessed
   weapons"; Shadow Dragon's dim-light Living Shadow) → NOT entered as a standard type;
   recorded in the monster `notes` so they don't distort prevalence.
