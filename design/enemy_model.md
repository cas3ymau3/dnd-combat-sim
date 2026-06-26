# Enemy model — how the generalized enemy operates (design-first contract)

> Status: **DESIGN (session 33, 2026-06-24; extended s37, 2026-06-26). WIRING IN
> PROGRESS — foundations (steps 1-3) wired s38.** This is the
> `design/buff_primitive.md`-style design-first note for the generalized enemy
> policy. It decides HOW the enemy behaves in combat before any policy code is
> written. **s38 wired the foundations (§12 step 3, steps 1-3 of 6):** the §13
> telemetry seam (`src/telemetry.py`, additive), the frozen `monster_profile_by_band.csv`
> (§8) + in-sync test, and the action-level re-tab (`monster_profile.action_budget`)
> grounding `BaselineEnemyPolicy`'s damaging-save rate/weights (§4 correction). **s39 wired
> step 4:** the §5 `mult(t)` fractional defense multiplier — `Entity.damage_multiplier`
> (substrate #4's continuous third layer) + `enemy_stats.band_damage_multiplier(s)` +
> `resolve_damage` phase 7b emitting the §13 mitigation channel; the §7 INCOMING force-mode
> was DEFERRED (it's enemy-offense typing, a no-op until the incoming-damage-type-mix knob /
> step 6). REMAINING: step 5 §6 control channel; step 6 §7 toggles. Companion to `design/enemy_profile.md` (the empirical
> census — the DATA this consumes) and `design/design.md` §8 (the outputs this must
> drive). The census is COMPLETE (510 monsters, 897 action rows + 218 control rows,
> four CR bands); this note turns that data into enemy decisions.
>
> **s37 (this metrics-design pass) added three LOCKED decisions ahead of #1 wiring:**
> §4b (the enemy action decision tree — ternary action budget + `also_damages` rider,
> resolving the §4a three-prong overlap; action budget sourced by an empirical
> action-level re-tabulation, not a carve), §6 step 5 (control persistence as a
> closed-form expected-duration grounded by the census `duration` column), and §13
> (the structured-telemetry seam #1 emits through, replacing the monkeypatch habit).
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

> **SOURCE OF TRUTH = the aggregator**, `python -m src.builds.monster_profile`
> (→ frozen `monster_profile_by_band.csv`, §8). The numbers below are an
> **illustrative snapshot** to convey the shape; do NOT treat them as canonical
> or hand-type them into code — read them from the frozen table at wiring time.
> **Updated to the FINAL post-reconciliation data (s36):** the v2 refinement-10
> cross-band reconciliation (§10) is DONE, so the four bands are now apples-to-apples
> and these numbers are stable (no further re-tag pending).

| knob | 0-4 | 5-10 | 11-16 | 17+ |
|---|---|---|---|---|
| **save_round_prob** (save-resolution instance share)¹ | 0.09 | 0.17 | 0.29 | 0.38 |
| **save weights** STR/DEX/CON/INT/WIS/CHA | 7/32/48/4/10/0 | 12/36/34/6/12/0 | 4/41/34/2/15/3 | 3/55/36/0/0/5 |
| elemental share (of all damage instances) | 37% | 47% | 61% | 67% |
| reach ranged+both | 20% | 30% | 42% | 40% |
| AoE share | 7% | 12% | 24% | 29% |
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

## 4a. Two more grounded facets (captured s36): size distribution + three-prong mix

Both are reproducible from the frozen census via `python -m src.builds.monster_profile`
(`band_profile(...)["size_distribution"]` and `resolution_three_way(harmonized=...)` /
`print_three_way()`). Snapshots below; read from the aggregator at wiring time.

### Monster SIZE distribution per band (per-monster, % of band)

Preserved raw — **not interpreted into a mechanic here.** Source = the `size` column of
`monster_profile_monsters.csv`; surfaced per-band by the aggregator. It is strongly
CR-dependent (so an aggregate average is misleading), which is why it is banded like
everything else. Relevant later to size-gated mechanics (grapple / shove / some forced
movement); how — if at all — to turn it into a knob is deferred to the enemy-behavior
formalization.

| size | 0-4 | 5-10 | 11-16 | 17+ |
|---|---|---|---|---|
| Tiny | 10.6% | 0.8% | 0% | 2.9% |
| Small | 11.2% | 0% | 0% | 0% |
| Medium | 52.8% | 36.5% | 34.8% | 17.1% |
| Large | 23.1% | 43.7% | 32.6% | 11.4% |
| Huge | 2.3% | 18.3% | 26.1% | 20.0% |
| Gargantuan | 0% | 0.8% | 6.5% | **48.6%** |

### Three-prong action mix — attack-for-damage / save-for-damage / control-save

The enemy's per-round action splits three ways for a decision tree: an **attack-roll**
damage ability, a **save-for-damage** ability, or a **control-save** ability. Built by
combining the damaging census (`resolution`) with the control census. The "attack" prong
folds in the small `both` (attack-then-save) and `auto` (no-roll, e.g. Magic Missile)
shares — i.e. it is "has an attack roll or auto-delivery," the not-pure-save bucket.

**Two weighting bases** (the control census is ALREADY cadence-discounted at source —
at-will 1.0 / recharge 0.5 / limited 0.25 — so it is used as stored in both):

- **RAW** — damaging rows at full weight. MISMATCHED: the damaging census never discounts
  recharge/limited uses, so the damage prongs are inflated and **control reads as a floor.**

| band | atk-dmg | save-dmg | control |
|---|---|---|---|
| 0-4 | 80% | 8% | 12% |
| 5-10 | 73% | 15% | 12% |
| 11-16 | 62% | 25% | 13% |
| 17+ | 54% | 32% | 14% |

- **HARMONIZED** (apples-to-apples — **prefer this for the decision tree**) — the same
  cadence discount applied to the damaging rows too. Much of the high-CR "save-for-damage"
  mass is recharge breath weapons + limited spells, which now discount down; the at-will
  multiattacks (attack prong) do not, so the attack share rises and control ticks up:

| band | atk-dmg | save-dmg | control |
|---|---|---|---|
| 0-4 | 83% | 5% | 12% |
| 5-10 | 78% | 9% | 13% |
| 11-16 | 69% | 17% | 14% |
| 17+ | 61% | 24% | 16% |

**Read:** as CR rises the damage side rotates attack → save-for-damage, while **control
sits at a steady ~12–16%** of save-or-attack actions across all tiers. ⚠️ **The three
prongs are NOT disjoint** — a damage-coupled control ability (Mind Blast = save-for-damage
AND stun) is counted in BOTH the save-for-damage and control prongs (the control CSV's
`also_damages` flag marks these; overlap ≈ 24–44% of control rows by band). **RESOLVED in
§4b (s37):** the runtime does NOT consume these prongs as a disjoint partition — the
`also_damages` flag *splits* the control mass into a pure-control prong (in the action
budget) and a bundled rider (on save-for-damage rounds), so the overlap is intentional
cross-axis pressure, not a double-count to net out.

---

## 4b. The enemy action decision tree — the structure §3/§6 wire to (s37, LOCKED)

> Design-pass decision (session 37). Settles how the per-band knobs (§4) and the
> control channel (§6) compose into the enemy's per-round behavior BEFORE the §12
> step-3 wiring consumes them. The three-prong overlap (§4a) and the carve-vs-census
> question are resolved here.

**The governing reframe: TWO independent per-axis pressure channels, not a partition.**
The §4a "three prongs summing to 100%" is *descriptive census color* for the action
MIX; it is NOT the object the runtime draws from. §3 (damaging) and §6 (control) are
**independent channels** — control fires *on top of* the damaging choice, not in
competition with it for a single action slot. Once you stop forcing the prongs to sum
to 100%, an `also_damages` ability is not double-counted by two branches fighting over
one slot: it contributes its *damage* to the damaging channel and its *control* to the
control channel — two different consequences feeding two different measurements. This is
the **B1** decision (s37): two saves for one bundled ability is the *better instrument*,
because each consequence is priced against the build's *relevant* defense (a no-Evasion /
high-mental-save build correctly eats Mind Blast's damage but dodges its stun — a single
netted save would mis-attribute one of the two). Realism (one save, coupled consequences)
is deprioritized per §1/§3, exactly as sampling was.

**The action budget — a ternary draw, one per round, sums to 1.** The control census
has two structurally different populations (`also_damages` flag), routed differently:

1. **(i) attack round** — multiattack vs AC (the existing attack branch).
2. **(ii) save-for-damage round** — one AoE, half on a save (the existing save branch).
3. **(iii) pure-control round** (`also_damages = N`) — the enemy spends its WHOLE action
   on a control effect and deals **no damage** (Hold Person, Dominate, a fear-only gaze).
   This **displaces** a damage action — the new prong.

**The bundled-control rider — on top of (ii).** Bundled control (`also_damages = Y`,
e.g. Mind Blast) IS a save-for-damage ability, so it lives in channel (ii): a
save-for-damage round has some probability its AoE *also* imposes control on the failed
save (a SECOND, control save — the agreed B1 cross-axis double-save), **conditioned on
save-for-damage rounds** (its true home; the rate is then naturally bounded ≤ 1).

**Why this resolves the save-frequency inflation.** The census control rate splits, it
does not stack. Worked at 17+ (harmonized control = 16%, overlap ≈ 40%):
- pure = 16 × 0.6 = **9.6%** → action-budget prong (iii), *displaces* a damage action;
- bundled = 16 × 0.4 = **6.4%** → rides on save-dmg rounds (6.4/24 ≈ 27% of them also stun).
- Total control saves/round = 9.6% + 6.4% = **16%, the original rate, fully preserved.**

Only the **6.4% bundled** portion adds an "extra save on top," and that is the *intended*
cross-axis double-save (price Evasion and mental-saves independently). The **9.6% pure**
portion *replaces* a damage action instead of stacking on it — so a turn the enemy spends
dominating you is not also a turn it breathes fire. Naive "all control on top" dumped the
full 16% on top (9.6% of it spurious) AND left the displaced damage in place; this model
cuts on-top inflation to the intended 6.4% and correctly zeroes damage on pure-control
rounds. So the §4a harmonized table is **promoted** from descriptive color to the *source
of the action budget*, with `also_damages` doing the pure-vs-rider split.

**Sourcing the action budget — EMPIRICAL action-level re-tabulation, not a carve (s37).**
The action budget is NOT obtained by arbitrarily carving the pure-control share out of the
attack share. It is re-tabulated from the **frozen** census at the ACTION level (no new
census): the damaging census stores a whole Multiattack as ONE `multiattack-swing` row
(with `instances_per_round = N`), so counting action-economy *slots* once — collapsing the
per-monster multiattack-swing rows into a single attack action, cadence-weighting the
alternatives — yields the true per-turn attack / save-dmg / pure-control budget. This also
**corrects `save_round_prob`**: §4 grounds it on the save *instance* share, but the runtime
treats a round as one *action* choice, so it belongs on the *action* basis (multiattack
counted once, not N times) — the re-tab fixes that for free. Implementation notes (deferred
to #1, a new accessor over frozen data like `resolution_three_way`): (a) group a monster's
multiattack-swing rows into one attack action; (b) keep only the PRIMARY action slot —
`legendary` is the separate cadence-bump knob (§10), `bonus`/`trait`/`reaction` are out of
the per-turn budget.

**Sub-decisions (s37, resolved):**
- **What pure-control displaces:** carve from the **attack** share, leaving the grounded
  `save_round_prob` (save-dmg rate) fixed — "the monster controls instead of swinging."
  (Now empirically grounded by the action-level re-tab, not a heuristic carve.)
- **Bundled rider placement:** conditioned on save-for-damage rounds (its real home),
  not an independent any-round draw. ⚠️ **LOW-CR reconciliation (flagged s38, decide at
  step-5 wiring):** the action-level re-tab (`monster_profile.action_budget`) shows that
  at band **0-4** the bundled-control mass (`bundled_control_per_mon ≈ 0.084`) is LARGER
  than the save-for-damage budget it is meant to ride on (`save_dmg_per_mon ≈ 0.007`) —
  there simply aren't enough save-for-damage rounds at low CR to host all the bundled
  control. "Bundled rides on save-dmg rounds, rate bounded ≤ 1" therefore *cannot absorb
  it* in the bottom band. Fix at step 5: where `bundled_per_mon > save_dmg_per_mon`, let
  the overflow fall back to its own independent any-round draw (i.e. treat the excess as
  pure-control-style on-top pressure) rather than silently capping/dropping it. The
  higher bands reconcile fine (save-dmg ≫ bundled), so this is a bottom-band-only patch.
- **Save-type weights:** one `control_save_weights` for both the pure and bundled control
  saves; a per-half split is a deferred refinement (likely over-fitting).

**Default discipline / no baseline drift.** Control OFF ⇒ p(iii) = 0 and no rider ⇒ the
exact current binary attack/save behavior. Turning control ON has a *coupled* effect by
design — incoming damage drops (pure-control rounds displace attacks) while lost-turns
rise — which is physically real (a turn spent dominating is not a turn spent hitting); it
is documented rather than fought. A build wanting to isolate only the lost-turn effect can
set the displacement knob to ride-on-top instead of displace.

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

Worked example — **fire** by band (illustrative snapshot; the live `P_*`
prevalences come from the aggregator / frozen band table, §8): `mult = 1 −
0.5·res − imm + vuln` yields roughly **0.93 / 0.84 / 0.79 / 0.64** across
`0-4 / 5-10 / 11-16 / 17+` — a fire build keeps ~93% of its damage at low tiers
but loses ~36% by CR 17+. The same multiplier exists for every damage type
(e.g. **poison** is brutal — immune ~19/28/26/40% across bands — and **physical**
is lightly resisted only at the top tiers). The policy computes `mult(t)` from
the table's prevalences at runtime; it is not a hand-entered constant.

**Condition-riders** are priced the same way: a rider imposing condition `c` is
worth `1 − P_cond_immune(c)` of its nominal effect (e.g. frightened vs 17+:
`1 − 0.514 = 0.49`). This is forward-looking — most riders are not yet *modeled*
as doing anything — but it names the seam so rider value is priced when riders
land.

**Mechanism (named s33, BUILT s39 — roadmap step 4):** the enemy carries a
**per-type fractional resistance profile** for its band (`Entity.damage_multiplier`,
built by `enemy_stats.band_damage_multipliers(level)`), applied at the enemy's
damage-*intake* during damage resolution (`resolve_damage` phase **7b**, after the
binary categorical response), **rounded** to the nearest int (mean-field expectation),
and emitted through the §13 mitigation channel (outgoing before/after by type). Empty
profile (the default — the §7 res/imm/vuln check OFF) → inert → no baseline drift.
Reuse / extend the existing incoming-resistance substrate
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
   *control* save (rises with CR; control density climbs at the top tiers). Per §4b
   this rate is *split* by the `also_damages` flag: the **pure-control** portion is a
   prong of the ternary action budget (it displaces a damage action), the **bundled**
   portion rides as a second save on save-for-damage rounds. The two channels are
   independent — control is not a slice of one action budget shared with damage.
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

**5. Duration — a closed-form EXPECTED-duration multiplier (s37, LOCKED), grounded by
the census `duration` column.** A failed control does not cost exactly one turn — the
scariest control *persists* (Dominate / Hold are `save-ends`; ~50% of the hard-control
census is `save-ends` or `1 min`), and truncating every effect to one turn would gut the
exact thing this channel exists to price. v1 models persistence as a **mean-field expected
number of affected turns** (no stateful status object — that is the §10-deferred fidelity
step), grounded by the *measured* `duration` tag on each control row:
   - `1 turn` → 1 affected turn.
   - `save-ends` → the character RE-saves with its OWN bonus each turn, so
     `E[turns] = 1/s` (s = the build's save-success prob). This **double-prices** save
     investment: good saves both fail the initial save less *and* recover faster
     (s = 0.6 → ~0.67 turns; s = 0.3 → ~2.3 turns), which a flat one-turn model cannot do.
   - `1 min` / `until-escape` / `until-removed` → capped fixed durations (cap at the
     remaining combat length; the per-tag mapping is a #1 wiring detail).
   A failed HARD control then costs `E[turns]` lost (output 0 each); a failed SOFT control
   reduces output by `soft_factor` for `E[turns]`. Stays low-variance (deterministic
   expectation, no duration roll). The full `StatusSet` save-ends re-roll engine (an
   *ongoing-save* system with emergent duration) remains the §10 fidelity deferral.

**How it prices investment.** Better mental-save bonuses → fewer control
failures → fewer lost turns → higher *effective* DPR. A build that buys
"can't be charmed" or Aura-of-Protection now shows a measurable resilience gain;
without §6 it showed none.

**Data sourcing — empirical census, ahead of wiring (codebook LOCKED s34).**
The damaging census deliberately skipped pure-control actions, so the control
channel's frequencies/weights/severity-split begin as a **designer prior** (the
hierarchy above + the mental→hard / physical→soft lean), tunable as toggles (§7).
**Decision (s33 roadmap): we WILL run a full supplementary control-save census
BEFORE the wiring** — its codebook-design pass is now **DONE and LOCKED**:
`design/enemy_control_census.md` (s34, #3a) settles the scope (save-forcing
control incl. damage-coupled), the HARD/SOFT per-condition table, save keying, the
**cadence-discounted** weighting (a deliberate divergence from the damaging census
— control is cadence-dominated), and a **separate `monster_profile_control.csv`**
(keeps the damaging aggregator clean). So the channel wires against EMPIRICAL
`control_save_prob` / `control_save_weights` / `hard_vs_soft` (and the per-condition
hard/soft split is now MEASURED, upgrading the prior skew above); the prior becomes
the interim/fallback + toggle default only. See PROGRESS NEXT-STEP Track 1 #3b for
the census run. The census tags each monster's control save-forcing abilities (save
type + condition + hard/soft), mirroring the damaging census.

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
| **control channel** | ON / OFF | §6 incapacitation pressure on or off (OFF ⇒ ternary budget collapses to the binary attack/save-dmg, no rider — zero baseline drift) |
| **control_save_prob** | band (census) / 0 / high | how much control pressure; splits into pure-control (budget prong iii) + bundled rider per `also_damages` (§4b) |
| **control displacement** | displace-attack (default) / ride-on-top | whether a pure-control round *replaces* a damage action (real, coupled) or stacks on top (isolates the lost-turn effect alone) — §4b |
| **control_save_weights** | census / uniform / single-type | single-type (e.g. all-WIS) isolates one mental-save investment |
| **hard_control_frac / soft_factor** | census (type-skewed) / scalar | lost-turn share vs debuff factor |
| **control duration** | census `duration` (`save-ends`→`1/s`) / fixed-1-turn | expected lost-turns; fixed-1-turn de-prices the save-ends recovery, isolating the initial-fail effect (§6 step 5) |
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
   point on `monster_profile.py`. (The §6 **control channel** becomes
   census-derived once the supplementary control census runs
   (`design/enemy_control_census.md`, codebook LOCKED s34); at wiring time #1
   decide whether its `control_save_prob` / `control_save_weights` / `hard_vs_soft`
   columns append to this band table or freeze to a sibling
   `monster_control_by_band.csv`. Until that census lands, §6 uses the designer
   prior — kept as a separate small constants module so prior and empirical never
   blur.)
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

- ~~**v2 cross-band reconciliation**~~ **DONE (s36, refinement 10).** All four bands
  re-tagged on the same basis; the §4 snapshot is now final. (33 monsters + 2 size
  variants; +46 rows → 897.)
- ~~**Supplementary control-save census**~~ **DONE (s35, #3b).** 218 rows in
  `monster_profile_control.csv`; the control channel (§6) now reads empirical data.
- ~~**Three-prong action-mix overlap**~~ **RESOLVED (s37, §4b).** The prongs are NOT a
  disjoint partition the runtime consumes; the `also_damages` flag *splits* the control
  mass into a pure-control action-budget prong (displaces damage) and a bundled rider (on
  save-for-damage rounds). The overlap is intentional cross-axis pressure, not a
  double-count. The action budget is sourced by an empirical action-level re-tabulation of
  the frozen census (collapse multiattack, cadence-weight), NOT a heuristic carve — which
  also corrects `save_round_prob` to a per-action basis. Derivation accessor deferred to #1.
- **Monster size as a knob** (§4a) — the per-band size distribution is now captured raw
  (aggregator + `monster_profile_monsters.csv`), deliberately NOT interpreted. Whether to
  gate size-dependent character mechanics (grapple/shove/forced movement) on a per-band
  size scalar is deferred to the enemy-behavior formalization.
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
  an output-factor / lost-turn over a **closed-form expected duration** (§6 step 5,
  grounded by the census `duration` column — `save-ends` → `1/s` on the character's own
  save), and riders via a multiplier (§5). Modeling them as actual `StatusSet` conditions
  with real per-turn save-ends re-rolls (an *ongoing-save* system with emergent, variance-
  carrying duration) is the later fidelity step; the seam is named.
- **Control-save-weights per-half split** (§4b) — pure vs bundled control may differ in
  save-type distribution; v1 uses one `control_save_weights` for both. Split only if a
  build's defenses make the difference matter (likely over-fitting).
- **Elemental Adept vs the fractional `mult(t)`** (flagged s39) — the binary categorical path
  honors `ignore_resistance` (Elemental Adept bypasses *resistance*, not immunity/vuln), but the
  step-4 fractional multiplier does NOT yet drop its `0.5·P_resist` term when the attacker has
  Elemental Adept for that type (the multiplier is precomputed per type, not split into
  components at apply time). A small refinement — recompute `mult` without the resist term, or
  store the three components — deferred until a build pairs Elemental Adept with the band-defense
  toggle ON (an edge case today; the enemy dummy defaults to no profile).
- **Low-CR bundled-control overflow** (§4b, flagged s38) — at band 0-4 the bundled-control
  mass exceeds the save-for-damage budget it rides on (`bundled ≈ 0.084` vs `save-dmg ≈
  0.007` per monster), so the "rides on save-dmg rounds" placement can't host it in the
  bottom band. Step-5 fix: spill the overflow to an independent any-round draw. A
  bottom-band-only patch (higher bands have save-dmg ≫ bundled). This is also the
  empirical confirmation that **low-CR save pressure is dominated by CONTROL** (≈11% of
  rounds force a save — almost all control), so saving-throw protection still prices into
  low-level builds via §6, not via the (near-zero) low-CR damaging-save rate.

---

## 11. Validation framing (when this is wired)

Per `validate-mechanism-not-build-value`: tests assert the MECHANISM, never a
DPR value. Specifically — the blend fires damaging-save vs attack rounds at the
band rate over many seeds; save-type frequencies match the band weights; the
`mult(t)` multiplier reduces typed outgoing damage by the documented factor;
force-mode zeroes the effect of a typed character resistance; the control channel
fires control saves at the band rate and a failed save costs a turn (hard) or
scales output (soft) as configured; each toggle flips the corresponding behavior
(all-attack → zero save rounds; res check OFF → multiplier 1.0; control OFF → no
lost turns; band override → the other band's mix); the frozen band table is in
sync with the aggregator. Plus the §4b/§6 structure (s37): the ternary action budget
fires attack / save-dmg / pure-control at the band's *action-level* shares; a
pure-control round deals zero damage (displaces); a bundled (`also_damages`) round
forces BOTH a damage save and a control save; control OFF restores the exact binary
attack/save behavior (no baseline drift); a `save-ends` control's expected lost-turns
scales as `1/s` with the character's save (a high-save build recovers in fewer turns);
the structured-telemetry channels (§13) emit the same counts the mechanism asserts. We
do NOT assert that "fire build DPR at CR17 is correct" — only that the model prices it
the way the census (and the measured control data) says.

---

## 12. Downstream sequence (extends `enemy_profile.md`)

1. ~~Census + methodology~~ DONE (s28–32).
2. **This note** — enemy-model design (s33); decision-tree structure + telemetry
   seam + control-duration model added (s37, §4b / §6 / §13).
3. **Wire the blend into `BaselineEnemyPolicy`** — 6 sub-steps. **FOUNDATIONS DONE
   (s38):** ~~add the §13 telemetry seam~~ (`src/telemetry.py`); ~~freeze the band table
   (§8)~~ (`monster_profile_by_band.csv` + in-sync test); ~~add the action-level
   re-tabulation accessor (§4b) → ground the ternary action budget (corrects
   `save_round_prob` to the action basis) + save weights~~ (`monster_profile.action_budget`
   + `enemy_stats.band_save_*`; `BaselineEnemyPolicy` defaults grounded). **s39 DONE:**
   ~~add the `mult(t)` enemy-defense multiplier (step 4)~~ (`Entity.damage_multiplier` +
   `enemy_stats.band_damage_multiplier(s)` + `resolve_damage` phase 7b → §13 mitigation
   channel; §7 incoming force-mode deferred to step 6). **REMAINING:** add the control-save
   channel (§6) with the pure/bundled split and the expected-duration model (step 5); wire the
   toggles (§7, step 6); emit every quantity through the §13 channels; mechanism-validated (§11).
4. Positioning / kiting + targeting arc (§9) — its own multi-session lift.
5. Reporting / aggregation layer (design.md §8 outputs) + the 4×4 baseline
   comparison — consumes the §13 telemetry channels.
6. First honest end-to-end build evaluation (offense + profile-driven defense +
   control resilience).

---

## 13. Structured telemetry seam — the single channel #1 emits through (s37, LOCKED)

> Design-pass decision (session 37), the Thread-A half of the metrics design. Settles
> HOW the enemy model (and, going forward, every build) reports the quantities a
> cross-build evaluation needs, BEFORE #1 wiring starts emitting them. The §8 frozen
> band table is the model's INPUT; this is its OUTPUT seam.

**The debt this pays down.** Today the only structured outputs are the damage ledgers on
`CombatResult` / `DayResult` (`damage_log`, `damage_received`, `damage_by_source_target`,
`rounds_elapsed`). *Everything else* a build's resilience depends on — slots spent,
concentration checks, parry / AoO budget — is audited by reaching into resource pools and
policy internals from tests (`char.resources.available(...)`, `p1._aoo_round`). That
monkeypatch-telemetry habit is fine for a one-off assertion but is the wrong substrate for
the enemy model, which needs a pile of *new* quantities that have no home at all: control
uptime, lost-turn rate, save-fail rates by type, typed-damage mitigated. So the seam is a
structural prerequisite for #1, not just cleanup.

**Shape — a typed accumulator with a small CLOSED channel vocabulary** (the chosen option,
s37; mirrors the project's "closed verb set" + "table is the source of truth" philosophy —
NOT a free-form `record(channel, key, value)` event sink, and NOT ad-hoc flat fields that
churn the result dataclass per metric). A `CombatTelemetry` object is carried on
`CombatResult` and aggregated onto `DayResult` exactly like the damage ledgers. The fixed
channels (extend deliberately, like adding a verb — not casually):

| channel | records | prices / feeds |
|---|---|---|
| **saves** | saves forced / passed / failed, keyed by (ability type, channel ∈ {damage, control}) | save-bonus + Evasion + typed-resistance investment; the §4b cross-axis split is *visible* here (saves split by channel, so the bundled double-save is interpretable, not hidden) |
| **control** | turns lost (hard) and turns reduced (soft) + the `soft_factor` applied + the expected-duration realized, by save type | mental-save investment, "can't be charmed", Aura of Protection (§6) — the lost-turn rate / control-uptime outputs |
| **mitigation** | outgoing damage before vs after `mult(t)`, by damage type (typed-damage mitigated); incoming damage by type | the §5 defensive denominator; the character's typed incoming resistance |
| **economy** | resources spent (slots, war_priest, brutality, …), concentration checks forced / failed, reactions used | folds the existing slot-audit / parry-budget / concentration-count monkeypatches into ONE home |

**Who writes it — RESOLUTION only, never policy (preserves CLAUDE.md #7).** The seam is
written by the scheduler / verb handlers as they roll dice and mutate state — they already
know the outcome (this save failed, this much was mitigated, this turn was lost). The
policy stays a pure read: the *enemy* policy CHOOSES which save to force; the *scheduler*
RECORDS the result. Recording is pure observation — it must never change a die or an
outcome, so adding a channel cannot move a DPR baseline.

**Granularity — typed aggregate counters / distributions per combat, summed across the
day** (matching the mean-field, low-variance, interpretable values of §1), NOT a per-event
log. Per-round resolution is kept only where an output needs it (e.g. control uptime as a
fraction of rounds). One structured surface; the §5 reporting layer (step 5) and the
mechanism tests (§11) both read it instead of re-deriving from internals.

**Checkpoint coupling (per the roadmap).** This is the *substantial* half of the metrics
design (seam + emittable set). The lighter finalization — cross-build reporting
*principles* once #1 produces real data — is the #4 pause; decide there whether #4 stays a
full design pause or becomes build-out.
