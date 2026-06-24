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

- **Incoming (enemy offense):** throw a representative *mix* of damage AND
  control — attack-vs-save split, save-type spread, reach, AoE, and
  incapacitation pressure — so the character's defensive features (AC vs save
  bonuses, Evasion, Uncanny Dodge, typed resistance, mental-save investment,
  intercepts/reactions) are exercised *in proportion to how often they would
  actually matter* across the monster population.
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

1. **Attack-vs-save round split.** Pre-roll each round as a damaging-save round
   with probability `save_round_prob[band]` (grounding the current placeholder
   `SAVE_ROUND_PROB = 0.35`), else an attack round.
2. **Save type.** On a damaging-save round pick the save ability by
   `save_type_weights[band]` (grounding the placeholder `SAVE_TYPE_WEIGHTS`,
   which is currently *wrong* — see §4), vs the level's `save_dc`, AoE dice,
   half on a save.
3. **Attack round.** `n_attacks` swings vs AC at the level's to-hit, per-swing
   dice (nat-20 doubles dice → enemy crits, already built).
4. **Incoming damage type** (knob, §7): type the enemy's output by the band
   damage-type mix so a character's *typed* incoming resistance (resist fire,
   resist nonmagical B/P/S) fires at the right rate.

A SEPARATE **control-save channel** (§6) runs on top of this to model
incapacitation pressure — the thing the damaging census cannot see.

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
(§8), not be hand-typed into code.

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
force a save, a refinement noted in §10. Using the save-only share keeps the knob
clean and interpretable; document the slight under-count of save events.

**Note the correction:** the placeholder `SAVE_TYPE_WEIGHTS` ranks `DEX==WIS >
STR > CON`. The data says **CON and DEX dominate; WIS is near-zero as a *damaging*
save** (the WIS effects in statblocks are pure control — frightening roars,
charms — which the census does not tag, by design). So grounding these weights is
a *correction*, not just a fill-in. **The mental-save importance everyone feels
in play lives in the CONTROL channel (§6), not here** — these damaging-save
weights are correctly CON/DEX-dominant.

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
*effective* DPR against the population. **Fallback** if the continuous multiplier
ever feels too clever: per-combat Bernoulli (roll resist/immune/vuln per type at
the band prevalence, apply the binary D&D multiplier) — integrates to the same
mean with variance. The continuous form is the default for low variance.

---

## 6. Control-save channel — incapacitation pressure (so mental saves matter)

**The gap this closes.** The census tags only *damaging* saves, so it
structurally cannot see the thing that makes mental saves frightening in play:
the worst save failures are **pure control** (lose your turn, get dominated /
charmed / stunned), and those abilities deal no damage, so they were never
tagged. The §4 damaging-save weights are therefore honestly CON/DEX-dominant —
the wrong instrument for pricing a build's investment in mental (WIS/CHA/INT)
save protection (Aura of Protection, save proficiency, "can't be charmed",
advantage-on-saves, magic resistance). Without this channel the model gives those
investments zero value.

**Structure — a second, independent save-pressure channel** parallel to §3's
damaging-save channel:

1. **`control_save_prob[band]`** — probability per round the enemy forces a
   *control* save (rises with CR; control density climbs at the top tiers).
2. **`control_save_weights`** — the save-type distribution for control effects,
   DISTINCT from the damaging-save weights. Reflects the in-play hierarchy +
   physical control: `DEX ≈ WIS > CON > INT ≈ CHA ≈ STR` (community rule of
   thumb), broadened so STR/DEX also carry physical control (grapple / restrain /
   prone).
3. **The character rolls its ACTUAL save** (its build's save bonus) vs the
   per-level `save_dc` (already in the magnitude table). Condition immunities /
   advantage-on-saves / auto-pass features apply here — this is the seam that
   prices mental-save investment.
4. **On a failed control save, draw the outcome** (your two-branch model):
   - **(i) HARD control → the turn is wasted** (character output that turn → 0):
     paralyzed / petrified / stunned / incapacitated / charmed / dominated.
     This is the strongest DPR lever in the model, and correctly so — a
     turn-ending mental failure *should* dominate the resilience number.
   - **(ii) SOFT control → output × `soft_factor`** (e.g. ~0.5–0.75): blinded /
     frightened / restrained / poisoned / prone — the character still acts but at
     reduced effect (disadvantage on attacks, can't close, etc.).
   - **Severity skews by save type** to make mental saves *feel* dangerous, as in
     play: mental control (WIS/CHA/INT — charm/fear/dominate/stun) leans toward
     the HARD branch; physical control (STR/DEX/CON — grapple/restrain/poison)
     leans SOFT. So a failed WIS save is *probably* a lost turn; a failed STR save
     is *probably* a debuff.

**How it prices investment.** Better mental-save bonuses → fewer control
failures → fewer lost turns → higher *effective* DPR. A build that buys
"can't be charmed" or Aura-of-Protection now shows a measurable resilience gain;
without §6 it showed none.

**Data sourcing — designer prior now, optional census later (HONEST about this).**
The census deliberately skipped pure-control actions, so the control channel's
frequencies/weights/severity-split are a **designer prior** (the hierarchy above
+ the mental→hard / physical→soft lean), tunable as toggles (§7) and explicitly
flagged as NOT empirical. The empirical path, if we want it, is a **bounded
supplementary control-save census**: tag each monster's control save-forcing
abilities (save type + condition + hard/soft), mirroring the damaging census.
Roadmap item (§10), not required to wire the channel — the prior makes the
mechanism work; the census would only refine its numbers.

**Coupling to §5/§9.** The SOFT branch (restrained/prone/blinded) also makes the
character easier to *hit* (attacks against it at advantage) — so the control
channel feeds the to-hit side and connects to targeting/positioning (§9). v1 can
model soft control purely as the output-factor; the advantage coupling is a §9
refinement.

---

## 7. Toggles for sensitivity analysis

Each toggle isolates one axis (memory `build-selection-prioritizes-capacity` —
isolate hard axes; `validate-mechanism-not-build-value` — we test the toggle
flips behavior, not that a DPR is "right"). Defaults are the band-grounded
values; each can be overridden per evaluation run.

| toggle | values | isolates / purpose |
|---|---|---|
| **CR-band override** | band ∈ {0-4,5-10,11-16,17+} | stress a build vs a harder/softer tier than its level |
| **save_round_prob** | empirical[band] / 0 (all-attack) / high | how much pressure is damaging-save based; isolate Evasion etc. |
| **save_type_weights** | empirical[band] / uniform / single-type | single-type (e.g. all-DEX) isolates Evasion / a save proficiency |
| **res/imm/vuln check** | ON / OFF | the defensive-offense pricing (§5) on or off |
| **condition-immunity check** | ON / OFF | rider pricing on or off |
| **incoming damage-type mix** | empirical[band] / untyped / single-type / **force** | gates the character's *incoming* typed resistance |
| **— force-damage mode** | (a value of the row above) | all enemy damage → force ⇒ NO character typed resistance applies; **isolates flat/untyped mitigation** (raw AC, Uncanny Dodge, temp HP, heals) from typed mitigation — the delta vs res-check-on is the value of the build's typed defenses |
| **control channel** | ON / OFF | §6 incapacitation pressure on or off |
| **control_save_prob** | prior[band] / 0 / high | how much control pressure |
| **control_save_weights** | prior / uniform / single-type | single-type (e.g. all-WIS) isolates one mental-save investment |
| **hard_control_frac / soft_factor** | prior (type-skewed) / scalar | lost-turn share vs debuff factor |
| **ranged-kiting fraction** | 0 (full melee uptime) / band ranged share / custom | melee build uptime loss vs ranged/kiting share — STUB now (see §9/§10) |
| **AoE share** | empirical[band] / 0 | matters for Evasion / multi-target defenses |
| **legendary cadence** | OFF / band bump | extra incoming actions/round at 11-16 / 17+ |

**Default discipline:** the res/imm/vuln + condition-immunity checks, the control
channel, force-mode, and the kiting fraction all default **OFF / neutral**
(multiplier 1.0, no control, typed-as-empirical, full uptime) so wiring them does
NOT silently move existing DPR baselines; they are opt-in measurements. The
damaging-save split + weights default to the band-empirical values (they replace
placeholders already in the live path, and the correction is wanted).

---

## 8. Consolidated enemy reference dataset (the schema decision)

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
   point on `monster_profile.py`. (The **control-channel prior** of §6 is NOT in
   this census-derived table — it is a designer prior; keep it as a separate
   small constants table / module so the empirical and prior data never blur.)
3. **Raw census** (the regenerable empirical record) —
   `reference/data/monster_profile_{monsters,raw}.csv`. Source of #2; kept as the
   normalized ground truth. Not read by the policy.

**Retire** `reference/data/monster_ac_and_saves_by_level.csv` to documented
provenance only (it is already the generation input for #1; note it in the
header and stop treating it as a live table).

Read path for the policy: `band_profile(level→band)` from #2 + `level_table(level)`
from #1 + the control-prior constants (§6).

---

## 9. Enemy behavior — movement & targeting (connection points; mostly deferred)

Two behavior axes the user raised. Both belong primarily to the downstream
**positioning / targeting arc** (§10 step 4), but they have real connection
points to this work, recorded here so they are not lost.

- **Movement (melee vs kiting)** — *does* connect to the census. The **reach**
  distribution (ranged + both share, climbing 20% → 40% with CR, §4) is the
  empirical hook: a kiting enemy forces a melee build to spend movement / forgo
  attacks, lowering its true uptime below the "everyone stands in melee for 4
  rounds" assumption. v1 models this as the **kiting-fraction toggle** (§7),
  grounded to the band ranged share, default OFF (full uptime) so it doesn't
  silently move baselines. The *real* model — zones, opportunity attacks,
  approach turns — is the deferred arc (`Entity.zone` / `move_entity` / `range_`
  exist but no policy uses them tactically).
- **Targeting (who the blended enemy attacks)** — does NOT fall out of the census
  typing data; it is a **tactical-prior layer**. The machinery already exists:
  `BaselineEnemyPolicy` supports a trait-weighted friendly roster (design §3.5)
  and summon-survival focus-fire (kill the summon → load shifts to the master).
  What's missing is *behavior*: prefer attacking at advantage, avoid disadvantage,
  focus a target it has grappled / that is marked, spread vs focus-fire. These are
  designer priors, not census facts. Recommendation: keep them in the
  positioning/targeting arc; a v1 stub stays with the existing weighted roster.
- **The genuine coupling** (why these arcs touch §5/§6): the SOFT-control branch
  (restrained / prone / blinded character) makes the character easier to hit
  (attacks at advantage), so control pressure (§6), targeting (advantage-seeking),
  and the to-hit side are linked. When the targeting/positioning arc lands, wire
  the soft-control advantage coupling there rather than in §6.

**Net:** the census informs *reach* (movement) but NOT *targeting tendencies*
(tactical priors). Neither blocks the §3/§5/§6 wiring; both are recorded for the
later arc.

---

## 10. Open items, sequencing, and deferrals

- **v2 cross-band reconciliation** (open follow-up from the census; refinement 10).
  Bands 11-16/17+/5-10 were tagged under the OLD omit rules; only ~30-45 monsters
  (casters-with-damaging-spells + at-will damaging alternatives) are affected.
  **The policy code is identical whether or not this lands** — reconciliation only
  changes the numbers in the frozen band table (#2). So: **wire with the caveat
  documented; reconcile as a separable data pass** (re-freeze the band table after).
  Until it lands, cross-band comparisons of elemental/AoE/save shares read slightly
  high for 0-4 purely from the rule change.
- **Supplementary control-save census** (§6) — optional empirical grounding for the
  control channel's prior. Bounded data task (tag control abilities: save type +
  condition + hard/soft). Prior is sufficient to wire; census refines its numbers.
- **`both`-resolution riders** (attack-then-save): folded into attack rounds, not
  the binary damaging-save round, in v1 (§4 note). A refinement would let an attack
  round *also* force a save (modeling e.g. poison-on-bite) — defer until a build's
  defense makes it matter.
- **Ranged-kiting / positioning + targeting tendencies** (§9) — its own multi-session
  arc; only the kiting-fraction stub and the existing weighted roster are touched now.
- **Legendary action-economy** at 11-16/17+ is a cadence *bump* knob (extra
  incoming actions/round), grounded to band prevalence; the census deliberately
  captures ≤1 damaging legendary use (documented undercount). Default OFF.
- **Rider / control effects modeled as real status objects.** v1 prices control as
  an output-factor / lost-turn (§6) and riders via a multiplier (§5). Modeling them
  as actual `StatusSet` conditions with durations (save-ends re-rolls, etc.) is a
  later fidelity step; the seam is named.

---

## 11. Validation framing (when this is wired)

Per `validate-mechanism-not-build-value`: tests assert the MECHANISM, never a
DPR value. Specifically — the blend fires damaging-save vs attack rounds at the
band rate over many seeds; save-type frequencies match the band weights; the
`mult(t)` multiplier reduces typed outgoing damage by the documented factor;
force-mode zeroes the effect of a typed character resistance; the control channel
fires control saves at the prior rate and a failed save costs a turn (hard) or
scales output (soft) as configured; each toggle flips the corresponding behavior
(all-attack → zero save rounds; res check OFF → multiplier 1.0; control OFF → no
lost turns; band override → the other band's mix); the frozen band table is in
sync with the aggregator. We do NOT assert that "fire build DPR at CR17 is
correct" — only that the model prices it the way the census (and the stated
control prior) says.

---

## 12. Downstream sequence (extends `enemy_profile.md`)

1. ~~Census + methodology~~ DONE (s28–32).
2. **This note** — enemy-model design (s33).
3. **Wire the blend into `BaselineEnemyPolicy`** — freeze the band table (§8),
   ground save_round_prob + save weights, add the `mult(t)` enemy-defense
   multiplier + force-mode, add the control-save channel (§6), and the toggles
   (§7), mechanism-validated (§11). NEXT session.
4. Positioning / kiting + targeting arc (§9) — its own multi-session lift.
5. Reporting / aggregation layer (design.md §8 outputs) + the 4×4 baseline
   comparison.
6. First honest end-to-end build evaluation (offense + profile-driven defense +
   control resilience).
