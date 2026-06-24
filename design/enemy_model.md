# Enemy model — how the generalized enemy operates (design-first contract)

> Status: **DESIGN (session 33, 2026-06-24). Not yet wired.** This is the
> `design/buff_primitive.md`-style design-first note for the generalized enemy
> policy. It decides HOW the enemy behaves in combat before any policy code is
> written. Companion to `design/enemy_profile.md` (the empirical census — the
> DATA this consumes) and `design/design.md` §8 (the outputs this must drive).
> The census is COMPLETE (510 monsters, 851 action rows, four CR bands); this
> note turns that data into enemy decisions.
>
> Project memory: `enemy-profile-empirical-direction`,
> `standardized-dpr-baseline-not-realism`, `validate-mechanism-not-build-value`,
> `build-selection-prioritizes-capacity`, `design-first-for-cross-cutting-primitives`.

---

## 1. The governing principle — the enemy is an INSTRUMENT, not an opponent

The sim's purpose (memory `standardized-dpr-baseline-not-realism`) is a
**standardized DPR estimate AND a defensive-resilience estimate** for a build,
measured against the conventional 4×4-round content-creator baseline. The enemy
exists to *take those measurements*, not to be a faithful simulation of any
particular monster.

So the enemy is the **representative average enemy of the character's CR band**.
Its job is twofold:

- **Incoming (enemy offense):** throw a representative *mix* of damage —
  attack-vs-save split, save-type spread, reach, AoE — so the character's
  defensive features (AC vs save bonuses, Evasion, Uncanny Dodge, typed
  resistance, intercepts/reactions) are exercised *in proportion to how often
  they would actually matter* across the monster population.
- **Outgoing (enemy defense):** present a representative *defensive profile* —
  damage resistances / immunities / vulnerabilities and condition immunities —
  so the character's **damage-type choice and rider conditions are priced**:
  a fire build should lose value as it climbs into fire-immune tiers; a
  frightened-on-hit rider should be worth nothing against things immune to it.

This principle resolves nearly every modeling fork toward the **low-variance,
mean-field, reproducible, interpretable** option. Realism is explicitly
deprioritized; representativeness + reproducibility + interpretability win.

---

## 2. Two-axis representation: magnitudes per-LEVEL, qualitative mix per-BAND

Two datasets feed the enemy, on two different axes, at their native granularity:

- **Magnitudes — per character level** (`reference/data/monster_stats_by_level.csv`,
  loaded by `src/builds/enemy_stats.py`): AC, the six save bonuses, to-hit, save
  DC, `n_attacks`, per-swing dice, AoE dice. Derived from the Rothner "Average
  Monster Stats by CR" chart, smooth in CR, already ÷1.5 party-corrected. CR ==
  level. **Unchanged by this work.**
- **Qualitative mix — per CR band** (the census, `design/enemy_profile.md`):
  damage-type distribution, attack-vs-save resolution split, save-type weights,
  reach/AoE shares, res/imm/vuln prevalence, condition-immunity prevalence.

**The join:** a character's level selects the band (`0-4 / 5-10 / 11-16 / 17+`);
the band supplies the *mix*, the level supplies the *magnitudes*. A level-7
character faces the 5-10 band's qualitative profile at level-7 magnitudes.

**Why not rebuild magnitudes from the census:** the census tagged *instances*
(how often each type/save appears), NOT damage amounts. Instance-weighting is
exactly right for the qualitative mix and **wrong** for magnitudes — which is
why magnitudes stay on the chart. This also retires the open "move instances →
damage-weighting" question *for the policy*: it would only matter if the census
also had to set magnitudes, which it does not. (Damage-weighting remains a
possible v2 refinement of the census itself, independent of this note.)

**Band selection is a step function, deliberately.** The bands were chosen
because the mix changes *steeply* with CR (§4 table). A step at the band
boundary is honest; do not interpolate the mix across bands. (The magnitudes
already vary smoothly per level underneath.)

---

## 3. Offense model — the expected-value BLEND (blend-only; user-locked s33)

Each round the enemy realizes the band distributions as an **expected-value
mean-field blend**: it does not impersonate a drawn monster, it *is* the average
monster. Concretely, extending the existing `BaselineEnemyPolicy` (which already
pre-rolls a binary attack-round-vs-save-round at `on_combat_start` to keep
`decide()` dice-free):

1. **Attack-vs-save round split.** Pre-roll each round as a save-forcing round
   with probability `save_round_prob[band]` (grounding the current placeholder
   `SAVE_ROUND_PROB = 0.35`), else an attack round.
2. **Save type.** On a save round pick the save ability by
   `save_type_weights[band]` (grounding the placeholder `SAVE_TYPE_WEIGHTS`,
   which is currently *wrong* — see §4), vs the level's `save_dc`, AoE dice,
   half on a save.
3. **Attack round.** `n_attacks` swings vs AC at the level's to-hit, per-swing
   dice (nat-20 doubles dice → enemy crits, already built).
4. **Incoming damage type** (optional knob, §6): type the enemy's output by the
   band damage-type mix so a character's *typed* incoming resistance (resist
   fire, resist nonmagical B/P/S) fires at the right rate.

**Why blend-only (sampling rejected, user call s33).** The alternative —
drawing a real census monster per combat so deal-type/resist *correlations* are
preserved ("a fire dragon resists fire AND deals fire") — is a *realism*
feature, and realism is deprioritized. Blend-only is the coherent instrument: a
single enemy with **fractional** resistances and a **blended** action mix IS the
mean-field monster. It is lower-variance, reproducible, and interpretable, and
needs only the band aggregates at runtime, not the full per-monster table. We do
not carry a sampling mode at all; revisit only if a future build genuinely needs
correlated structure (it would be a new toggle, not a redesign).

**The key modeling move:** mean-field turns binary D&D resistance into a
**continuous multiplier** (§5). That is exactly what makes blend-only coherent
rather than a lossy hack — the "average enemy" legitimately resists fire 6.4/10
of the way at the top tier.

---

## 4. The grounded per-band knobs (the actionable payload for wiring)

From the complete census (`python -m src.builds.monster_profile`). These are the
values the wiring session installs; they will live in the frozen band table
(§7), not be hand-typed into code.

| knob | 0-4 | 5-10 | 11-16 | 17+ |
|---|---|---|---|---|
| **save_round_prob** (save-resolution instance share)¹ | 0.09 | 0.13 | 0.24 | 0.32 |
| **save weights** STR/DEX/CON/INT/WIS/CHA | 7/32/48/4/10/0 | 16/36/30/6/12/0 | 5/41/34/3/15/3 | 3/53/37/0/0/7 |
| elemental share (of all damage instances) | 37% | 44% | 60% | 65% |
| reach ranged+both | 20% | 30% | 42% | 40% |
| AoE share | 7% | 8% | 18% | 26% |
| legendary prevalence | 0% | 2% | 35% | 89% |

¹ **save_round_prob** is set to the band's **save**-resolution instance share.
The `both` rows (attack-then-save riders, e.g. a bite that also forces a CON
save) are NOT folded into the binary save-round — they are attacks that *also*
force a save, a refinement noted in §8. Using the save-only share keeps the knob
clean and interpretable; document the slight under-count of save events.

**Note the correction:** the placeholder `SAVE_TYPE_WEIGHTS` ranks `DEX==WIS >
STR > CON`. The data says **CON and DEX dominate; WIS is near-zero as a *damaging*
save** (the WIS effects in statblocks are pure control — frightening roars,
charms — which the census does not tag, by design). So grounding these weights is
a *correction*, not just a fill-in.

---

## 5. Defense pricing — expected damage-multiplier on the character's output

For the build's outgoing damage of type `t`, against the band, multiply by

```
mult(t) = 1 − 0.5·P_resist(t) − P_immune(t) + P_vulnerable(t)
```

derived from: none → ×1, resist → ×0.5 (loss 0.5), immune → ×0 (loss 1.0),
vulnerable → ×2 (gain 1.0); `P_*` are the band prevalences. This is literally
"the fraction of your type-`t` damage that lands against the representative
enemy" — the **defensive denominator on offense** the model has been missing.

Worked example — **fire** by band: `mult = 1 − 0.5·res − imm + vuln`:

| band | resist | immune | vuln | **fire mult** |
|---|---|---|---|---|
| 0-4 | 6.3% | 5.9% | 2.3% | **0.93** |
| 5-10 | 14.3% | 9.5% | 0.8% | **0.84** |
| 11-16 | 10.9% | 17.4% | 2.2% | **0.79** |
| 17+ | 20.0% | 25.7% | 0% | **0.64** |

A fire build keeps ~93% of its damage at low tiers but loses ~36% by CR 17+.
That is the kind of priced-by-the-population number this model produces; the same
table exists for every damage type (e.g. **poison** is brutal — 19/28/26/40%
immune across bands — and **physical** is lightly resisted at the top tiers).

**Condition-riders** are priced the same way: a rider imposing condition `c` is
worth `1 − P_cond_immune(c)` of its nominal effect (e.g. frightened vs 17+:
`1 − 0.514 = 0.49`). This is forward-looking — most riders are not yet *modeled*
as doing anything — but it names the seam so rider value is priced when riders
land.

**Mechanism (named, not built):** the enemy carries a **per-type fractional
resistance profile** for its band, applied at the enemy's damage-*intake* during
damage resolution. Reuse / extend the existing incoming-resistance substrate
(#4, already built for the character side — Fire Shield etc.) rather than invent
a new one; the only twist is that the multiplier is **fractional** (`mult(t)`)
instead of the binary ×0.5. It folds in at the damage-resolution multiplicative
phase (design.md §8 phase order). The character attacks the enemy dummy; the
multiplier reduces the damage that lands → the character's reported DPR is the
*effective* DPR against the population.

---

## 6. Toggles for sensitivity analysis

Each toggle isolates one axis (memory `build-selection-prioritizes-capacity` —
isolate hard axes; `validate-mechanism-not-build-value` — we test the toggle
flips behavior, not that a DPR is "right"). Defaults are the band-grounded
values; each can be overridden per evaluation run.

| toggle | values | isolates / purpose |
|---|---|---|
| **CR-band override** | band ∈ {0-4,5-10,11-16,17+} | stress a build vs a harder/softer tier than its level |
| **save_round_prob** | empirical[band] / 0 (all-attack) / high | how much pressure is save-based; isolate save defenses |
| **save_type_weights** | empirical[band] / uniform / single-type | single-type (e.g. all-DEX) isolates Evasion / a save proficiency |
| **res/imm/vuln check** | ON / OFF | the defensive-offense pricing (§5) on or off |
| **condition-immunity check** | ON / OFF | rider pricing on or off |
| **incoming damage-type mix** | empirical[band] / untyped / single-type | gates the character's *incoming* typed resistance |
| **ranged-kiting fraction** | 0 (full melee uptime) / band ranged share / custom | melee build uptime loss vs ranged/kiting share — STUB now (see §8) |
| **AoE share** | empirical[band] / 0 | matters for Evasion / multi-target defenses |
| **legendary cadence** | OFF / band bump | extra incoming actions/round at 11-16 / 17+ |

**Default discipline:** the res/imm/vuln and condition-immunity checks and the
kiting fraction default **OFF** (multiplier 1.0, full uptime) so wiring them does
NOT silently move existing DPR baselines; they are opt-in measurements. The save
split + weights default to the band-empirical values (they replace placeholders
that are already in the live path, and the correction is wanted).

---

## 7. Consolidated enemy reference dataset (the schema decision)

Today there are four scattered tables. The coherent set is **three live tables on
two axes**, plus a retired provenance file:

1. **Magnitudes, per level** — `reference/data/monster_stats_by_level.csv`
   (existing; the Rothner-chart magnitudes). Loaded by `enemy_stats.py`. **Keep
   as-is**; do not merge it with the band profile — different axis (magnitude vs
   mix) and different provenance (chart vs MM census).
2. **Qualitative mix + defensive prevalence, per band** — NEW
   `reference/data/monster_profile_by_band.csv`. The **frozen aggregator output**:
   one row per band carrying save_round_prob, the six save weights, the damage-type
   mix, reach/AoE shares, the per-type res/imm/vuln prevalences (→ `mult(t)`), the
   per-condition immunity prevalences, and legendary cadence. This is what the
   policy READS at runtime — the policy never re-aggregates 851 rows. Frozen to
   CSV (not computed at import) so it is eyeball-able / hand-editable, matching the
   project's "table is the source of truth" philosophy (`enemy_stats.py`). Kept
   **in-sync-tested** against `monster_profile.all_profiles()` exactly like
   `enemy_stats.regenerate()` has a sync test — regenerate via a `--write` entry
   point on `monster_profile.py`.
3. **Raw census** (the regenerable empirical record) —
   `reference/data/monster_profile_{monsters,raw}.csv`. Source of #2; kept as the
   normalized ground truth. Not read by the policy.

**Retire** `reference/data/monster_ac_and_saves_by_level.csv` to documented
provenance only (it is already the generation input for #1; note it in the
header and stop treating it as a live table).

Read path for the policy: `band_profile(level→band)` from #2 + `level_table(level)`
from #1.

---

## 8. Open items, sequencing, and deferrals

- **v2 cross-band reconciliation** (open follow-up from the census; refinement 10).
  Bands 11-16/17+/5-10 were tagged under the OLD omit rules; only ~30-45 monsters
  (casters-with-damaging-spells + at-will damaging alternatives) are affected.
  **The policy code is identical whether or not this lands** — reconciliation only
  changes the numbers in the frozen band table (#2). So: **wire with the caveat
  documented; reconcile as a separable data pass** (re-freeze the band table after).
  Until it lands, cross-band comparisons of elemental/AoE/save shares read slightly
  high for 0-4 purely from the rule change.
- **`both`-resolution riders** (attack-then-save): folded into attack rounds, not
  the binary save-round, in v1 (§4 note). A refinement would let an attack round
  *also* force a save (modeling e.g. poison-on-bite) — defer until a build's
  defense makes it matter.
- **Ranged-kiting / positioning** is a STUB knob here (default OFF = full melee
  uptime). The real model — movement, opportunity attacks, melee uptime loss — is
  its own multi-session arc (`Entity.zone`/`move_entity`/`range_` exist but no
  enemy policy uses them tactically). This note only reserves the knob so wiring it
  later does not disturb the blend.
- **Legendary action-economy** at 11-16/17+ is a cadence *bump* knob (extra
  incoming actions/round), grounded to band prevalence; the census deliberately
  captures ≤1 damaging legendary use (documented undercount). Default OFF.
- **Rider effects** are mostly not yet *modeled* as doing anything; §5's
  condition-immunity pricing names the seam for when they are.

---

## 9. Validation framing (when this is wired)

Per `validate-mechanism-not-build-value`: tests assert the MECHANISM, never a
DPR value. Specifically — the blend fires save vs attack rounds at the band rate
over many seeds; save-type frequencies match the band weights; the `mult(t)`
multiplier reduces typed outgoing damage by the documented factor; each toggle
flips the corresponding behavior (all-attack → zero save rounds; res check OFF →
multiplier 1.0; band override → the other band's mix); the frozen band table is
in sync with the aggregator. We do NOT assert that "fire build DPR at CR17 is
correct" — only that the model prices it the way the census says.

---

## 10. Downstream sequence (unchanged from `enemy_profile.md`)

1. ~~Census + methodology~~ DONE (s28–32).
2. **This note** — enemy-model design (s33).
3. **Wire the blend into `BaselineEnemyPolicy`** — freeze the band table (§7),
   ground save_round_prob + save weights, add the `mult(t)` enemy-defense
   multiplier + the toggles (§6), mechanism-validated (§9). NEXT session.
4. Positioning / kiting arc (its own multi-session lift).
5. Reporting / aggregation layer (design.md §8 outputs) + the 4×4 baseline
   comparison.
6. First honest end-to-end build evaluation (offense + profile-driven defense).
