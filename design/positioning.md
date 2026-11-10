# positioning.md — the positioning / opportunity-attack arc (DESIGN RECORD)

> **Status: DESIGN ONLY (session 63). No prerequisite is built.** Two
> zero-number fixes ship alongside this document (§9); everything in §7 is
> scoped, not implemented.
>
> Roadmap item 5d. Read with `design/design.md` §3.1 (the zonal model as
> decided), `design/enemy_model.md` §9/§10 (the arc's prior record, **whose
> framing this document corrects — see §3**), and `src/zones.py` (substrate 7b,
> the parts already built).
>
> **§12 IS BINDING AND SUPERSEDES §3, §7.3, §5, §10 AND §11 WHERE THEY DIFFER.**
> It records the decisions from the s63 review with the user — above all **the
> ENGAGEMENT GUARANTEE (§12.0)**, which scopes the arc's subtractive term OUT by
> decision and thereby dissolves the speed blocker §7.3 names. **§13 is the
> build plan.** Read §12 and §13 before acting on anything earlier in this file.
>
> **This design starts from the 33-guide corpus, not from War Angel** (user,
> s63). War Angel is the arc's *degenerate* case, and building the model around
> it is the specific failure this document exists to avoid.

---

## 1. Why this arc, and what closing it buys

Three things, in descending order of how much they are worth.

1. **It lifts the scope bound on #6b.** The definitive War Angel evaluation
   (s62) carries a user-imposed bound: *its numbers may not be used to compare
   alternative behaviours or policies*, because the positioning model is absent
   and `war_angel.py:1187` lets Flourish Parry and the opportunity attack both
   fire off one reaction. Until this arc lands, the project can measure a build
   but cannot compare two ways of playing one. **That is the real reason the arc
   is next** — not the opportunity attacks themselves.
2. **It unblocks mechanics that are already in the corpus and already half in
   the engine.** Three of the six deferred weapon masteries (`topple`, `slow`,
   `push` — `src/verbs.py:162`) are purely positional, and they are 2024 core
   mechanics available to every weapon build. Sentinel, reach weapons, forced
   movement and hazard-zone trapping are all in the same position: declared in
   the corpus, inert in the model.
3. **It replaces three declared constants with emergent quantities** (§6). This
   is the deliverable that re-baselines the project, and it is first-class
   rather than a side effect.

---

## 2. THE CORPUS SURVEY — what 33 build guides actually ask for

Counted over `design/build-guides/` (33 files, the user's own build corpus, the
same corpus the ability schema was validated against). Counts are *guides
mentioning the term*, grep-verified, and the two false-positive traps found
while counting are recorded because they would each have inflated the case:

- **`Sentinel` is mostly the Sentinel *Shield* magic item**, not the feat
  (advantage on initiative/perception — nothing to do with positioning). 8
  guides match the word; **only 2 take the FEAT**
  (`36_hellshadow_bloodhunter` L4/L5, `37_white_dragon_warrior` L8).
- `grapple` and `fly` first counted **0/33** because the pattern used `\|`
  under `grep -E`, which matches a literal pipe. Corrected below.

| mechanic | guides | note |
|---|---:|---|
| `speed` | 31/33 | near-universal; **no speed exists in the engine** (§7.3) |
| `slow` | 28/33 | the weapon mastery, deferred at `verbs.py:162` |
| `push` | 23/33 | forced movement + the mastery |
| `fly` / `flying` / `flight` | 22/33 | a speed differential the model cannot express |
| `Dash` | 21/33 | |
| `Disengage` | 21/33 | the AoO-denial action |
| `longstrider` / `haste` | 19/33 | speed buffs |
| `topple` | 18/33 | the mastery → prone |
| `reach` | 18/33 | 5ft vs 10ft changes the AoO rate directly |
| `Misty Step` | 18/33 | teleport: **does not provoke** |
| `teleport` | 17/33 | |
| `grapple` | 16/33 | lockdown — denies kiting outright |
| `nets` | 15/33 | same |
| `prone` | 15/33 | |
| **`kite` / `kiting`** | **11/33** | **named as a tactic — see §3** |
| `difficult terrain` | 11/33 | |
| Sentinel **feat** | 2/33 | speed-0 on hit |

**26 of 33 guides** carry explicit positioning or reaction tactical language,
and **26 of 33** mention reactions at all. This is not a one-build concern.

### 2.1 Six distinct positioning patterns, none of them War Angel's

1. **Character-side kiting as the damage engine.** `20_the_wardancer`: Tavern
   Brawler shoves 5ft on an unarmed hit, so *"we can effectively kite creatures
   with standard reach"*, and the L1 tactics are *"use the kiting combo to deal
   damage while staying out of reach of heavy hitters."* The build's damage loop
   **is** a positioning loop.
2. **Positional lockdown / zone-trapping.** `37_white_dragon_warrior` is built
   on it end to end: *"take sentinel feat so that we can use our reaction to
   lock enemies within our fog cloud/sleet storm"*, *"we use sentinel/grapple/
   nets to lock enemies inside a fog cloud or sleet storm"*. Its damage comes
   from the enemy **failing to leave** a hazard zone.
3. **Reach differentials farmed deliberately.** `25_the_voice_of_heaven` L8:
   War Caster, and then *"to make this more useful, start holding a reach weapon
   (a whip ...)"* — reach is bought to raise the reaction-attack rate.
4. **Mount-based kiting.** `42_lost_voice_of_the_old_ones`: *"use high mobility
   on mount to kite in and out of danger (note deer doesn't proc opportunity
   attacks)"*; `39_the_preservation_outrider` kites in and out of its own zone.
5. **AoO avoidance as the stated goal.** `32_silvertails_blessing` — an
   ALREADY-MODELLED build — states its tactic as *"prone enemies, and kite
   in/out w/o provoking AoOs"*.
6. **Speed as the enabling stat.** `26_the_shadow_giant`: *"Kiting playstyle"*,
   *"epic boon of speed to make kiting even more reliable"*, and a section
   headed *"Sources of (pseudo) disengage / protection while kiting"*.

### 2.2 What the corpus spends REACTIONS on — six consumer classes

Extracted from the 114 reaction-bearing lines. The reaction is the scarcest slot
in the action economy and the corpus contends for it six ways:

| class | corpus examples | engine seam today |
|---|---|---|
| **A. reaction ATTACK** | opportunity attack; AoO + armor of agathys proc; inspiring movement attack; blood curse | `Choice(cost="reaction")` — **debits** |
| **B. damage mitigation** | parry; halve/reduce incoming damage; +PB to AC vs melee; reflect | `on_incoming_hit` intercept — **does NOT debit** |
| **C. roll manipulation** | reroll with advantage; neutralize adv/disadv; self-guidance; empower next Sneak Attack | `on_miss` / `on_failed_save` |
| **D. reaction MOVEMENT** | *"expend a BI and move up to 1/2 your speed"*; *"move up to speed"*; switch places; misty escape | **none — does not exist** |
| **E. ally protection** | reduce damage to allies within X | partial (`InterceptResponse.reaction_by`) |
| **F. positional denial** | *"lock enemies within our fog cloud"* (Sentinel) | **none** |

**Classes D and F have no representation at all, and they are exactly what this
arc needs.** Class B's non-debit is the double-book measured in §4.2.

---

## 3. THE PREMISE IS INVERTED — and this is the survey's main finding

`enemy_model.md` §9 models **one** direction: the enemy kites the character.
It states the consequence as settled —

> kiting *"forces a melee build to spend movement / forgo attacks, lowering its
> true uptime below the 'everyone stands in melee for 4 rounds' assumption."*

and PROGRESS item 5d promotes that to the fact to plan around: *"a positioning
model does not mainly ADD opportunity attacks — it SUBTRACTS attacks ... this
arc re-baselines every number in the project, downward."*

**Three independent checks say the dominant term points the other way.**

### 3.1 The rules make the subtraction conditional (verified, not recalled)

2024 rules, per the per-feature ritual's step 1:

- An opportunity attack triggers when a creature you can see **leaves your
  reach** using its action, bonus action, reaction, or one of its speeds.
- **Disengage is an ACTION.** A monster with Multiattack must forfeit its entire
  Multiattack to deny one opportunity attack — so it will almost always **eat
  the AoO** instead.
- **Movement is not an action.** A 30ft character closes a 30ft gap *for free*
  and keeps its full Attack action.

So the character forgoes attacks only when the gap **exceeds its speed** — which
requires the enemy to out-pace it (higher speed, flight, or Dash, and Dash costs
the enemy its own attack). Under equal speeds against an enemy that wants to
attack, the character loses **nothing** and the enemy feeds it an AoO every time
it steps away.

### 3.2 The corpus asks for the mirror direction, 11 guides to 0

Every one of the 11 kiting guides in §2 has the **character** as the kiter. Not
one describes an enemy kiting the character.

**This is weak evidence on its own and is labelled as such:** these are
character build guides, so they would not document the opposition's tactics. But
two things make it more than silence. The corpus's tactical language assumes an
enemy that *closes* — *"staying out of reach of heavy hitters"*, *"sources of
(pseudo) disengage ... while kiting"* — and the census agrees: **54.9-79.8% of
cadence-weighted enemy actions are melee-only** (§4.3). The modal enemy pursues.
§9 modelled the minority case and modelled nothing else.

### 3.3 The magnitude is measured, and it is large and positive

> **CORRECTED BY §12.0c (s63 review): the +46% below is the value of ONE CELL of
> the movement matrix (melee character vs ranged enemy), not of the arc.** Under
> the locked typology a melee-type enemy never leaves reach, so it generates ZERO
> opportunity attacks, and melee-only is 54.9-79.8% of cadence-weighted enemy
> actions. The arc's real re-baseline is **band-dependent and crosses zero** —
> negative at band 0-4, ≈zero at 5-10, positive from 11-16. Read §12.0c.

§4.1. The arc's measured dominant term is **+46%**, not negative.

> **The honest summary:** positioning has an additive term that is measured,
> large and reliable, and a subtractive term that is conditional on a speed
> differential **for which the project holds no data at all** (§7.3). Planning
> this arc as a downward re-baseline would get the sign wrong. Planning it as
> "numbers move, direction known per build" is right.
>
> **UPDATED BY §12.0 (s63 review): the subtractive term is now scoped OUT by
> decision**, so the additive term stands unopposed and the re-baseline direction
> is **KNOWN AND UPWARD** with the magnitude §4.1 bounds. That is a stronger
> position than the "direction unknown" this paragraph settled for.

---

## 4. MEASURED MAGNITUDES

All at engine `a56ae31` (clean), seed 20261110, `enemy="baseline"`.

### 4.1 What an opportunity attack is worth

> **SCOPE (corrected, §12.0c):** this measures the value of an AoO COUNT, which
> is sound and is reused by §12.0c. What it does NOT establish is that the arc
> delivers 4 per combat — that holds only against a ranged-type enemy. The
> headline percentage here is a CELL value, not the arc's effect.

The framework's declared subject at L11, 6,000 days, sweeping the declared
`aoo_per_combat` option:

| aoo/combat | dpr | stderr | vs declared | reactions/round |
|---:|---:|---:|---:|---:|
| 0 | 9.3405 | 0.0186 | −1.7106 | 0.0000 |
| **1** (declared default) | 11.0512 | 0.0204 | — | 0.2500 |
| 2 | 12.7658 | 0.0222 | +1.7146 | 0.5000 |
| 4 | 16.1702 | 0.0247 | **+5.1190** | 1.0000 |

- **Linear at ~1.71 DPR per opportunity attack** (1.7106 / 1.7146 / 1.7097 per
  step) — so the arc's effect scales with the AoO *count*, which is the quantity
  the model currently declares as a constant.
- The 1→4 span — a ranged enemy stepping out of melee every round and eating the
  AoO, the §3.1 branch — is **+5.12 DPR, +46.3%**.
- Scaled by the band-11-16 ranged share (45.1%), a crude mixed estimate is
  ≈ 0.451×4 + 0.549×1 ≈ 2.35 AoO/combat ≈ **+2.3 DPR, ≈+20%**. Labelled crude:
  it linearly interpolates a measured scale and assumes every ranged enemy kites
  every round.
- For scale: this is **an order of magnitude larger** than the Guided Strike
  defect (0.74% at L5) that occupied s62.
- **At 4 the subject is reaction-SATURATED at exactly 1.0/round** — the economy
  cap. An AoO-every-round model leaves **no reaction** for classes B-F in §2.2,
  which is a structural constraint the arc must confront rather than a detail.

### 4.2 The reaction double-book that bounds #6b

War Angel, 4,000 days. Flourish Parry is live at L14-16 only, so L13 is the
clean control arm:

| level | reactions/round | parry live? |
|---:|---:|---|
| 13 | **0.2500 ± 0.0000** | no |
| 14 | 0.3288 ± 0.0011 | yes |
| 15 | 0.3325 ± 0.0011 | yes |
| 16 | 0.3309 ± 0.0011 | yes |

- **The overage is ~0.081 reactions/round — about 33% more reactions than the
  economy permits — and it is exactly zero at L1-L13.** So #6b's scope bound is
  real in kind but **small in magnitude and confined to three levels**. Worth
  stating plainly, because the bound as written reads as though it applied to the
  whole table.
- The average never approaches the 1.0 cap, so the collision only bites on
  rounds carrying both. If AoO round and parry are independent, that is
  ≈ 0.25 × 0.081 ≈ **2% of rounds** — an inference from the aggregate, not a
  direct count.
- **L13 reads 0.2500 ± 0.0000, and naming what makes it exact is the point**
  (s54's rule): the AoO is a *declared constant* of one per combat, pre-rolled
  onto one of four rounds, so every combat contributes exactly one reaction and
  the variance is structurally zero. **A declared constant has a visible
  signature in the output, and this is it.** Under §6 that row acquires variance.

### 4.3 The census reach distribution — and a correction

Cadence-weighted, from the frozen `monster_profile_by_band.csv`:

| band | melee | ranged | both | **ranged+both** |
|---|---:|---:|---:|---:|
| 0-4 | 79.8 | 12.3 | 7.8 | **20.1** |
| 5-10 | 66.0 | 21.7 | 12.3 | **34.0** |
| 11-16 | 54.9 | 32.2 | 12.9 | **45.1** |
| 17+ | 56.4 | 37.8 | 5.8 | **43.6** |

**Both prior records state this loosely and both miss its shape.**
`enemy_model.md` §9 says "climbing 20% → 40% with CR"; PROGRESS item 5d says
"20% -> 42% by band". The series is **not monotonic** — it peaks at 11-16
(45.1) and dips at 17+ (43.6). Correct both when this arc lands.

---

## 5. REQUIREMENTS, derived from §2 and not from one build

A positioning model that serves this corpus must express:

- **R1. Both kiting directions.** Character-kites-enemy (11/33 guides) *and*
  enemy-kites-character (§9). R1 is the requirement §9 does not meet.
- **R2. Reach as a per-entity quantity**, 5ft vs 10ft, because the corpus buys
  reach weapons specifically to change the AoO rate (§2.1 pattern 3).
- **R3. Speed as a per-entity quantity**, with a differential that decides
  whether a gap can be closed. 31/33 guides; the enabling stat for pattern 6.
- **R4. Movement that does not provoke** — teleport (18/33), Disengage (21/33),
  the mount exception, and reaction-movement (class D).
- **R5. Positional denial** — Sentinel's speed-0, grapple (16/33), nets (15/33),
  the three deferred masteries. The mechanics that *stop* a kite.
- **R6. Zone retention as a damage source** — an enemy failing to leave a hazard
  zone (pattern 2). `src/zones.py` has the zone; it has no reason for an
  occupant to stay or go.
- **R7. A contended reaction** — one slot, six consumer classes (§2.2), with the
  policy choosing. Today two of the six debit nothing.

**War Angel exercises R7 weakly and nothing else.** Its AoO is one per combat,
collapsed from the guide's five timing slots into a frequency, with the guide's
own note that it prices parry and AoO as both happening. A model that satisfied
only War Angel would satisfy none of R1-R6 — which is why this document starts
where it does.

---

## 6. THE SEAM CHECK (run at design time, per the promoted ritual)

The arc converts **three declared constants into emergent quantities**. That
conversion *is* the re-baseline, and each one is a two-writer risk of exactly the
shape s62's finding 3 caught (a channel with two writers reporting one).

| # | quantity | declared today | emergent under the arc | dormancy answer |
|---|---|---|---|---|
| 1 | opportunity attacks | `aoo_per_combat` (declared option, §4-provenanced) / War Angel's hardcoded 1 | a count of zone exits within reach | **not equal — unconnected.** The declared value must be deleted or demoted to an override, not left as a second writer |
| 2 | melee uptime | implicit in `rounds_per_combat=4` ("everyone stands in melee") | rounds on which the character could reach a target | **equal today for a reason that stops**: uptime ≡ 1.0 because nothing moves |
| 3 | the reaction | one slot; A debits, B does not | one slot, genuinely contended | **the THIRD answer — already unequal where nobody looks.** Quantified in §4.2 |

Two further seam findings:

- **Same quantity, two STAGES.** The AoO is decided at *policy* time today
  (`decide()` emits it on a pre-rolled round) and would be decided at
  *resolution* time under the arc (a subscriber fires when an exit happens).
  Those cannot agree, because one is a plan and the other is an event. The
  arc must pick one and delete the other.
- **Same quantity, two SCOPES.** `aoo_per_combat` is declared *per combat*;
  the emergent count is naturally *per round* and per (attacker, target) pair.
  `reactions_per_round` already reports per round (metrics.py:1851), so the
  registry is on the emergent side and the declaration is not.

### 6.1 Roll call — the declarations this arc touches, and the fixture per value

Written ahead of the code, per the promoted ritual. **Empty cells are the
finding.**

| declaration | values | fixture that covers each value |
|---|---|---|
| `Cost` (`taxonomy.COSTS`) | action / bonus_action / reaction | covered (existing economy tests) |
| | **movement** | **NONE — and it silently resolves. §9.1 closes this** |
| | free / none | covered |
| `aoo_per_combat` | 0, 1, ≥2 | covered (`test_baseline_character.py`) |
| | emergent (no declaration) | **NONE — does not exist yet** |
| reach | 5ft | implicit everywhere, declared nowhere |
| | 10ft | **NONE** |
| speed | any value | **NONE, at any value, and no data to ground one (§7.3)** |
| `entity_leaves_zone` | subscribed | **NONE — nothing subscribes; the string exists only in `ability_schema.md:93`** |
| | unsubscribed | the whole current engine |
| zone occupancy | shared `"melee"` blob | every production run |
| | genuinely differentiated | `test_zone_emanation.py` / `test_zone_buff_aura.py` only, via `move_entity` |

---

## 7. THE PREREQUISITES, RE-RANKED — there are FIVE, not four

Item 5d lists four, "three tractable and ONE BLOCKING". The survey adds one and
moves another.

### 7.1 An enemy movement option in the action budget — TRACTABLE
Grounded in §4.3's reach distribution. `BaselineEnemyPolicy`'s budget is ternary
(attack / save-damage / pure-control); this adds a fourth prong. Note it must
model the **Disengage choice** (§3.1), not just movement, or the enemy will
never pay to deny an AoO and the model will over-produce them.

### 7.2 An `entity_leaves_zone` subscriber — TRACTABLE
A new **trigger**, not a new verb, with `on_incoming_hit` as the precedent
(`policy.py`'s defender-side intercept). Nothing subscribes today. This is the
decision point where class A and class B of §2.2 finally compete for one slot.

### 7.3 Reach AND speed on entities — **SPLITS; and the SPEED half is RESOLVED by §12.0**

> **SUPERSEDED IN PART (s63 review).** This section's conclusion — that speed is
> a second blocker, because the subtractive term's sign depends on a speed
> differential with no data — **no longer holds**, because §12.0's ENGAGEMENT
> GUARANTEE scopes the pursuit problem out by decision. Speed is still needed,
> but only to gate ZONE EXIT against a footprint, which needs a **per-band
> mean-field scalar** rather than a distribution. **The census does NOT need
> reopening**, which withdraws option (b)/(c) below. The reasoning is kept
> because the measurement that forced the question stands.

Item 5d lists this as tractable. Half of it is not.

- **Reach is grounded.** The census carries a `reach` column, cadence-weighted
  into §4.3.
- **Speed has no data anywhere in the project.** Verified across every table in
  `reference/data/`: there is no speed column and no flight column. The census
  carries `reach` and per-monster `size`; the frozen band table carries neither
  size nor speed.
- And **§3.1 makes the whole subtractive term a function of the speed
  differential**. So the one quantity that decides this arc's *sign* for a melee
  build is the one quantity with no empirical basis.
- Sourcing it means **reopening the census/Chrome arc that s36 deliberately
  closed**. That is a user decision, not an implementation detail. The cheaper
  alternatives, in preference order: (a) a declared mean-field speed per band
  with the §7-style toggle and honest provenance; (b) the 2024 Monster Manual
  distribution that `design.md` §3.5 already names as the intended source,
  entered by hand for the band representatives rather than re-censused;
  (c) treat equal speed as the standardized basis and make any differential an
  opt-in sensitivity axis.

### 7.4 The character-side cost — **THE BLOCKER, and it is FAIL-OPEN rather than absent**
Item 5d records this as "an injection point ... that doesn't exist yet". It is
worse than that, and §9.1 fixes the dangerous half now.

`src/taxonomy.py:135` already puts `"movement"` in the closed `Cost` vocabulary.
`Scheduler.DEFAULT_RESOURCES` grants action / bonus_action / reaction only, and
the drain is `if cost in econ` — so a movement cost **falls through unmetered**.
Measured, five choices emitted in one turn:

| cost | choices emitted | resolved |
|---|---:|---:|
| `action` | 5 | 1 |
| `bonus_action` | 5 | 1 |
| **`movement`** | 5 | **5** |
| `free` | 5 | 5 |

**A naive implementation emitting `Choice(cost="movement")` gets free, unlimited
movement and no error** — and the attack-subtraction that is the entire point of
the arc silently never happens. This is the s62 shape again: not dead at both
ends, but live at one end and wrong, which is strictly harder to notice.

What the real injection point needs, beyond metering: the snapshot must carry
spatial state the policy can read (entities already have `.zone`, so this is
reach + speed + "can I close?"), and the policy must be able to emit a movement
choice *instead of* an attack. Per CLAUDE.md #7 the policy decides and never
rolls; "can I close?" must therefore be a pure read.

### 7.5 A reaction-contention model — **NEW, and R7 implies it**
Not in item 5d's list. Once exits generate AoO opportunities (§7.2), the
reaction is contended for real (§4.1 shows saturation at 4 AoO/combat), and
class B currently takes a reaction without debiting one (§4.2). **The arc cannot
land without deciding whether the intercept starts debiting** — and that
decision moves War Angel's L14-16 numbers on its own, independently of
positioning.

---

## 8. THE RE-BASELINE PROTOCOL — a first-class deliverable

Every number in the project moves when this arc lands. Treat that as a product
with its own decision record, in the shape of the s60 and s52 records in
`tests/test_eval_enemy_seam.py`.

1. **Separate the physics change from the stream change, the way s60 did.** A
   `git worktree` at the pre-arc commit works in this container (s62 used one);
   measure old-vs-new at a fixed day count and report signs and |z|, so a
   re-shuffled RNG stream is not mistaken for a mechanical effect.
2. **Default OFF, as every §7 enemy toggle did.** Positioning ships inert, so
   landing it moves nothing, and the re-baseline is a separate deliberate act.
   This is the project's own discipline (s38-s41: "all default-OFF → no drift").
3. **Expect the sign to be positive** (§3.3) and say so in advance, so a
   measurement that disagrees is informative rather than reassuring.
4. **Re-baseline `GOLDEN_DPR` and `AXIS_GOLDEN` only as a deliberate act with a
   decision record**, per CLAUDE.md.
5. **Do NOT relax `no-new-dice-outside-combat`.** It is a convention with its
   cost stated in `evaluation_framework.md` §14, not a rule — but this arc
   already moves every number, and it must not also move the dice for a second
   independent reason.

---

## 9. WHAT SHIPS WITH THIS DOCUMENT (session 63) — two zero-number fixes

### 9.1 `cost="movement"` now REFUSES instead of silently passing
The §7.4 fail-open, closed by the rule the project already has: **a declared
parameter must deliver its declared value, or refuse** (s54). The scheduler
asserts a **partition over the closed `Cost` vocabulary** — every member of
`taxonomy.COSTS` must be either *metered* (in `DEFAULT_RESOURCES`) or
*explicitly unmetered* (`free` / `none`). `movement` is in neither, so a choice
costing it raises instead of resolving.

A partition over a closed vocabulary is a guard that **cannot go stale**: adding
a cost to the taxonomy forces it to be classified. That is the s62 lesson
(enforce a sequence with a test, not a docstring) applied to a vocabulary.

**Moves no number**: nothing in production emits a movement-cost choice —
`move_entity` has zero production callers, and the only `Zone` in production is
Silvertail's ally-buff aura, a footprint rather than movement.

### 9.2 The §4 provenance gap in `WarAngelAdapter.describe()`
Found in s62 and left unfixed at the user's call. `describe()` returned
`build / level / options / daily_plan` and said nothing about opportunity
attacks, while `BaselineCharacterPolicy.describe_parameters()` spells the same
assumption out in full **and credits it to War Angel**. So the build that
ORIGINATED the convention did not record it and the build that BORROWED it did,
and an authoritative War Angel artifact buried exactly the assumption that
prompted this arc.

**Moves no number**: `described` feeds only the report's provenance block
(`report.py:673`). It is not in `config_hash` (which hashes `RunConfig` alone,
`config.py:320`), and no availability predicate reads it — its last reader was
the baked-in enemy path, deleted in s52.

> Shape worth keeping, generalised: **a convention documented where it was
> BORROWED rather than where it ORIGINATED.** Same family as s54's "two lists"
> rule — the easy list to write is the one you are looking at.

---

## 10. EXPLICITLY NOT IN SCOPE

- **A grid.** `design.md` §3.1 decided zones, and nothing in §2 needs more.
- **Multi-character parties / AoE share.** Still gated on multi-character
  support (`enemy_model.md` §10), though R1 and the AoE deferral will want
  settling together.
- **Riders as real status objects.** `topple`'s prone and Sentinel's speed-0
  need a real status; §7.5 and `enemy_model.md` §10's "rider effects as real
  status objects" are the same deferral seen from two sides.
- **Targeting tendencies.** `enemy_model.md` §9 bundles targeting with
  positioning. They are separable and should be separated: targeting is a
  tactical-prior layer with no census basis, and none of R1-R7 needs it.

---

## 11. OPEN QUESTIONS FOR THE USER — **ALL FOUR ANSWERED IN THE s63 REVIEW**

> 1. **Speed data → ANSWERED by §12.0:** standardize on the engagement
>    guarantee; speed becomes a per-band mean-field scalar for zone exit only,
>    and the census stays closed.
> 2. **Does the intercept start debiting → STILL OPEN, and §13 Phase 3 proposes
>    landing it FIRST**, separately, since it moves only War Angel L14-16 and
>    needs no spatial model.
> 3. **Which direction first → ANSWERED:** both, via §12.5's build-declared
>    Disengage cost, which is what makes the enemy feed AoOs while the corpus's
>    kiting builds deny them cheaply. The asymmetry does the work, not a choice
>    of direction.
> 4. **Does `aoo_per_combat` survive → STILL OPEN**, settled in §13 Phase 2.
>
> Original text:

1. **Speed data (§7.3)** — reopen the census, hand-enter the Monster Manual
   distribution for band representatives, or standardize on equal speed and make
   the differential an opt-in axis? This decides the arc's sign for melee builds.
2. **Does the intercept start debiting the reaction (§7.5)?** It moves War Angel
   L14-16 on its own, so it could land before positioning as its own measured
   change — which would also lift the §4.2 half of #6b's scope bound early.
3. **Which direction is built first (R1)?** The corpus wants character-side
   kiting (11/33); §9 and War Angel want enemy-side. Character-side is the
   larger prize and the one with no prior design at all.
4. **Does `aoo_per_combat` survive as an override, or get deleted (§6, row 1)?**
   Keeping it is a second writer of an emergent quantity.

---

## 12. DECISIONS TAKEN (session 63 review with the user)

This section is binding and supersedes §3, §7.3, §10 and §11 where they differ.
It is the outcome of walking the user's own eight-category reaction taxonomy
against the corpus survey.

### 12.0 THE SPATIAL MODEL — LOCKED (user, s63)

> **This replaces the first draft of §12.0, which proposed a bounded arena of
> declared size. Two intermediate proposals were worked and REJECTED on
> measurement/argument, and both rejections are recorded because each was
> plausible and the reasons are not recoverable from the final form.**

**THE MODEL.**

1. **An infinite-width band.** No corners, so a fleeing entity is never trapped
   and forced movement always has room. (The bounded arena of the first draft had
   a cornering problem: in a bounded space pursuit eventually succeeds regardless
   of speed, because the fleeing side runs out of room and must pass the pursuer.)
2. **Distance is REAL SCALAR STATE** — `distance(character, enemy)` in feet,
   updated by both sides' movement and by forced movement. **There is no per-turn
   reset.**
   - **REJECTED: re-placing the enemy at `S_c` at every character turn start.**
     It would delete the MOVEMENT ECONOMY — position would be handed to the
     character each turn regardless of what it spent, so closing and withdrawing
     would never trade off. That economy is precisely the character-side cost
     §7.4 names as the arc's blocker, and a reset re-creates that fail-open at the
     design level: `Choice(cost="movement")` goes back to meaning nothing.
   - **REJECTED: arena length = `S_c`.** It confounds speed with room-to-run, so
     a fast build's survivability cannot be separated from the larger space its
     speed conjured. Under the infinite band there is no arena length at all, so
     the question dissolves rather than needing a declared constant.
3. **Combat starts at `d₀ = S_c`** (the character's speed). This is the
   ENGAGEMENT GUARANTEE in its final form — the character can always close in one
   move and never spends a turn walking to the fight. **It is build-dependent by
   design** (user): a build-dependent *environment* is not the failure a
   build-dependent *enemy* would be, because the enemy is the instrument held
   fixed while the environment is where the measurement happens.
   - **Priced:** closing from `S_c` costs `S_c − R_c`, leaving nothing to withdraw
     with, so **round 1 the character attacks and ends in melee.** With
     `rounds_per_combat = 4` the kiting benefit is **3 rounds of 4**, not 4.
4. **Forced movement and teleportation never provoke** (§12.3), and forced
   movement costs the character no movement at all.

**THE TWO CONDITIONS — independent, and tangling them produced a wrong answer
once already.**

**(A) GEOMETRY — can the character get beyond walk-in range?** The enemy attacks
iff it can end its movement within its own reach:

```
enemy attacks  iff  G ≤ S_e + R_e

character achieves  G = R_c + p + g_m    at cost  (d − R_c) + g_m ≤ S_c
      escape  iff  p + g_m > S_e
      sustained from adjacency  iff  S_c + p > S_e
```

where `p` is free forced movement per turn and `g_m` is movement spent
withdrawing. Grid-verified: a 30ft character with no push withdraws from
adjacency to `G = 35`, the enemy walks 30 to 5ft and **attacks** — no escape;
**with 5ft of push** it reaches `G = 40`, the enemy walks 30 to 10ft and cannot
reach. That 5ft flip is why push mastery is load-bearing for the corpus's kiting
builds, and `26_the_shadow_giant:70` states it outright: *"push mastery will
auto-disengage if you hit with the rapier."*

**DASH DROPS OUT, and this corrected an intermediate `S_c + p > 2·S_e`.** A
melee enemy that cannot reach should Dash — but **Dash is its Action and
Multiattack is its Action**, so a Dashing enemy buys adjacency and deals
nothing. *Being reached is harmless; being attacked is not.* So the condition is
against the enemy's WALK speed. Stated generally, with `c` the enemy's realized
closing distance, escape is `S_c + p > c`; only the walk case binds, because a
non-chaser is not melee-ing and a Dasher cannot attack.

> **CORRECTION, recorded because it was briefly stated as a crisp falsifiable
> prediction and is FALSE:** slow is *not* worth twice push per foot. That was
> downstream of the `2·S_e` form, where the enemy's speed entered doubled. Under
> `S_c + p > S_e` a slow of `s` and a push of `p` each move the threshold by the
> same amount — **1:1**.

**(B) PROVOCATION — does getting out cost an opportunity attack?**
**BUILD-DECLARED, and NOT generalizable** (user: *"There are lots of builds that
kite, and only some of them are monks ... the idea behind kiting builds will be
to leverage game mechanics (like weapon masteries such as push) to
'auto-disengage' without having to spend action economy resources"*):

| route out of reach | action-economy cost | provokes? |
|---|---|---|
| forced movement (push / shove mastery) | **none** | **no** — the enemy is moved, it is not moving |
| Disengage via a class feature | a **bonus action** (Cunning Action; Monk Patient Defense — a BA is always spent, *"for free"* in `16_bounty_hunter:109` means no FOCUS POINT) | no |
| Disengage as an Action | the **Action** — self-defeating, no attack | no |
| teleport (Misty Step etc.) | varies (BA + slot) | no |
| simply walk away | none | **YES — one opportunity attack** |

**WHAT KITING IS WORTH.** Against a melee-type enemy at L11
(`baseline_attack_dice` = 22.0 per swing, `baseline_n_attacks` = 2 → 44.0/round):

| character's route | enemy output that round |
|---|---:|
| cannot satisfy (A) | **44.0** — full Multiattack |
| walks away (provokes) | **22.0** — one AoO swing only |
| pushes, Disengages, or teleports | **0** |

So the mechanism rewards exactly what the corpus leverages, in the right order:
free forced movement > a bonus-action Disengage > walking > standing in melee.

**TWO DATA PREREQUISITES, both real work.**

- **Enemy speed as a DISTRIBUTION, not a scalar.** `p + g_m > S_e` is a step
  function, so a mean-field speed sitting near the character's threshold turns a
  coin-flip into a certainty. This is the one place mean-field misleads most, and
  it **reverses this document's earlier conclusion that a per-band scalar would
  do** (first-draft §12.0.4). Escape should be a PROBABILITY over the band's
  speed distribution.
- **Character speed per (build, level)** — verified absent from every `LEVELS`
  row of all three builds. Derivable like AC and the six saves (race base +
  Monk Unarmored Movement + Barbarian Fast Movement + boons), so it follows the
  §14 sparse-build-data pattern, across all 27 modelled pairs.

### 12.0a THE SUPERSEDED FIRST DRAFT — the engagement guarantee as originally written

**Decided (user, s63).** The combat area is defined so that **any entity can
reach any other within its normal movement, and never has to Dash to engage.**
The model is explicitly not about whether a character can get into melee:

> *"I don't really want to push the model into one where enemies with high speed
> just run away from the character and force us to use our action to dash up to
> them. That's not really what this model is for ... the model is meant to focus
> on DPR conditional on the character being able to deploy its damaging
> resources efficiently/effectively."*

**Five consequences, and they are large:**

1. **The arc's SUBTRACTIVE term is scoped OUT by decision, not blocked by
   missing data.** §7.3 called speed a second blocker because the subtraction's
   sign depended on a speed differential nobody had measured. Under the
   guarantee there is no pursuit problem to measure. **The blocker dissolves
   into a deliberate modelling boundary**, which is a far better place to be.
2. **The measured additive term (§4.1, +1.71 DPR per opportunity attack, +46.3%
   over the 1→4 span) now stands unopposed.** The re-baseline direction is
   therefore **KNOWN AND UPWARD**, not unknown. §8's protocol keeps its "state
   the expected sign in advance" step and the sign is now positive with a
   measured magnitude.
3. **Speed's only remaining job is ZONE EXIT** — which is exactly the mechanic
   `design.md` §3.1 already names: *"footprint vs. mover speed gates zone
   exit."* Speed is compared against a zone's footprint, never against another
   entity's speed.
4. **The enemy speed-data requirement collapses.** Not a distribution for chase
   mechanics: a **per-band mean-field scalar** answering "can it clear a
   footprint-F zone this turn?", with a §7-style toggle. Hand-enterable, or a
   single declared default. **The census/Chrome arc does NOT need reopening** —
   which withdraws §7.3's most expensive option.
5. **The range-band pressure largely dissolves too (see §12.6).** If the arena
   is about one move across, a 30ft reaction range covers it by construction.

**Accepted lost realism, recorded qualitatively and NOT quantified** (user's
explicit call): high-mobility builds are **undervalued** — they cannot cash in
an enemy's inability to close, and kiting-for-safety earns no survivability
credit. Note it in the per-build qualitative notes, as the guides already do.
This is the [[standardized-dpr-baseline-not-realism]] family: a bound on what
the number means, not a defect in it.

### 12.0b MOVEMENT TYPOLOGY — three character types, two enemy types (user, s63)

**Declared per (build, LEVEL), not per build**, because builds switch: at
`26_the_shadow_giant:270` *"we officially switch over to preferring melee combat
with our warhammer."*

**Character types** (a property of the build's policy — "policies are code"):

1. **Ranged attacker** — does not approach; attacks from range; retreats if the
   enemy closes into melee. Prioritizes movement/spells/abilities that keep it
   out of melee reach.
2. **Melee attacker** — approaches and STAYS in melee; chases enemies that want
   to shoot. Does not want to disengage or move away. **Includes grapplers and
   high-AC tanks**, and may use SLOWING tactics to keep enemies in range (which
   is `37_white_dragon_warrior`'s whole build).
3. **Kiting attacker** — approaches, makes melee attacks, retreats back out of
   melee and ideally out of reach of the follow-up. Uses mounts, movement
   abilities, push mastery and other forced movement / teleport / disengage
   routes to get out WITHOUT provoking (§12.0 condition B).

**Enemy types — and they are GROUNDED IN THE CENSUS, not invented.** The frozen
`reach` column maps straight onto them:

1. **Melee attacker** (`reach_melee`: 79.8 / 66.0 / 54.9 / 56.4% by band) — closes
   and attacks from melee; does **not** flee when approached, and therefore
   **never provokes an opportunity attack.**
2. **Ranged attacker** (`reach_ranged`: 12.3 / 21.7 / 32.2 / 37.8%) — avoids
   melee; spends movement to get out of melee when it starts its turn adjacent,
   **provoking.**

`reach_both` (7.8 / 12.3 / 12.9 / 5.8%) is a **DECLARED CHOICE** between the two,
and §12.0c shows it is first-order: it decides the SIGN of the re-baseline in
band 5-10.

### 12.0c THE 3x2 MATRIX — and it OVERTURNS this document's own headline

| | **Enemy 1: melee** | **Enemy 2: ranged** |
|---|---|---|
| **Char 1: ranged** | enemy closes; char retreats; char eats the enemy's AoO unless its route is free; a Dashing enemy deals nothing | static exchange, **no AoOs either way** |
| **Char 2: melee** | **both stand in melee — ZERO AoOs** | **char gets one AoO per round** |
| **Char 3: kiting** | char kites; needs `S_c + p > S_e`; converts the enemy's Multiattack into one AoO swing or nothing | behaves like Char 2 — it gets AoOs and kiting adds nothing |

**Only three of six cells produce an opportunity attack at all**, and the
decisive cell is `Char 2 x Enemy 1`: two melee combatants both want contact, so
**nobody leaves reach and the correct count is ZERO** — where the model today
declares **one per combat**.

**So the AoO count is `P(enemy is ranged-type) x 4`, against a declared 1.0.**
Measured per-AoO value (baseline subject, 6,000 days, seed 20261110), combined
with the census reach mix:

| lvl | band | DPR per AoO | wide `E[AoO]` | narrow | wide ΔDPR | narrow ΔDPR |
|---:|---|---:|---:|---:|---:|---:|
| 3 | 0-4 | 1.2642 ± 0.0207 | 0.80 | 0.49 | **−0.25** | **−0.64** |
| 8 | 5-10 | 1.6931 ± 0.0296 | 1.36 | 0.87 | **+0.61** | **−0.22** |
| 11 | 11-16 | 1.7146 ± 0.0301 | 1.80 | 1.29 | **+1.38** | **+0.49** |
| 16 | 11-16 | 1.6959 ± 0.0302 | 1.80 | 1.29 | **+1.36** | **+0.49** |

("wide" treats `both` as ranged-type, "narrow" as melee-type.)

> **THIS CORRECTS §3.3 AND §4.1's HEADLINE.** Those report **+46.3%**, measured
> by sweeping `aoo_per_combat` 1→4 — i.e. assuming an opportunity attack EVERY
> ROUND. Under the typology that happens only against a **ranged-type** enemy,
> and melee-only is **54.9-79.8%** of cadence-weighted enemy actions. The +46.3%
> is therefore the value of the `Char 2 x Enemy 2` CELL, **not of the arc**.
>
> **The arc's actual re-baseline is band-dependent and CROSSES ZERO:** negative
> at band 0-4, approximately zero in band 5-10 (sign set by the `both` choice),
> positive from 11-16 up. Neither "downward" (item 5d) nor "upward" (§3.3) was
> right, and **the typology is what revealed it** — not a new measurement of the
> same thing.
>
> **Magnitude bracket, stated rather than hidden:** the count uses 4 AoOs per
> 4-round combat, which assumes the character acts first in round 1. If the
> enemy acts first it is 3, which moves band 5-10 to ≈ +0.03 and band 11-16 to
> ≈ +0.60. **The qualitative conclusion is robust across 3-vs-4 and across the
> `both` choice; only the magnitude moves.**
>
> **BUT IT IS NOT ROBUST TO PARTY RETARGETING — see §12.0e, which supersedes the
> sign-crossing above.** The zero in the melee x melee cell assumed the enemy
> only ever wants to attack our character. It does not: at `party_size=4` with
> uniform weights it wants someone else on ~94% of its turns, and reaching them
> may force it out of the character's reach. The sign-crossing holds only at
> `m = 0`.

### 12.0e PARTY RETARGETING — the melee×melee cell is NOT zero, and this now DOMINATES

**Raised by the user, s63, and it is the largest single correction in this
document.** §12.0c concluded that two melee combatants both want contact, so
nobody leaves reach and the AoO count is zero. **That ignored the party.**

The model already has the enemy spreading attacks over a friendly roster. So:

- A **ranged** enemy can attack any party member from where it stands — no
  movement, no provocation. Positioning is irrelevant to its retargeting.
- A **melee** enemy in melee with the character that wants to attack a DIFFERENT
  party member **must move, and provokes** (user). We deliberately do **not**
  model party-member locations, so we assume a party member is always reachable
  once it leaves the character's reach.
- But some party members may be reachable **without** leaving the character's
  reach, which provokes nothing. So the rate is probabilistic.

**The retarget probability is already in the model, and it is high.**
`evaluation/enemy.py:_ally_roster` uses **UNIFORM** integer weights over the
friendlies, so at `party_size=4` (1 character + 3 stand-ins) each draws **25**:

| `n_attacks` | P(every swing on the character) | **P(wants someone else)** |
|---:|---:|---:|
| 1 | 0.2500 | **0.7500** |
| 2 | 0.0625 | **0.9375** |
| 3 | 0.0156 | 0.9844 |

**DECIDED (user, s63): targeting commits PER ROUND, not per attack.** If the
enemy aims its first attack at the character, all its subsequent attacks that
round go to the character too (or at minimum switching is very improbable). The
mechanic is meant to capture *"the enemy decides it wants a different target that
ROUND"*, not per swing. This **changes the retarget probability from 0.9375 to
0.7500** at `n_attacks=2` — one draw per round, not `n` independent draws — and
`src/builds/enemy.py` must change accordingly (it currently pre-rolls
`[_weighted_pick(rng) for _ in range(n_attacks)]`).

> **It is MEAN-PRESERVING, which bounds what it can move.** Expected attacks on
> the character per round is `0.25 x n_attacks` either way (independent: `n`
> draws at 25%; committed: one draw at 25% delivering all `n`). Only the
> CORRELATION changes, so damage taken keeps its mean and gains variance.
> Whether it is BIT-IDENTICAL is build-dependent and must be MEASURED, not
> assumed: party stand-ins take `baseline_ac(level)`
> (`character_stats.make_party_member`), which **equals** the baseline subject's
> own AC — so for that subject a swapped target resolves against the same number
> and nothing downstream diverges — but War Angel's `char_ac` comes from its own
> `LEVELS` row and does not. It can also be made draw-count-preserving by
> continuing to draw `n_attacks` values and using only the first.

Let `m` = P(the chosen target is outside the character's reach | retargeting).
The enemy moves at most once per turn and the character has one reaction, so:

```
melee x melee AoO per round  = 0.75 * m   (capped at 1)
melee x melee AoO per combat = 4 * 0.75 * m = 3 * m
```

**DECIDED (user, s63): `m = 1/3`.** From experience, and the user is explicit
that it is empirically ungrounded and cannot be made otherwise — *"It's just a
real constraint on the realism we are building into this framework ... let's just
make sure this value is documented and visible as an assumption."* So it is
recorded here, belongs in §4 provenance on every run, and stays a swept
sensitivity axis.

> ### THE TWO DECISIONS ARE MUTUALLY CALIBRATING, AND THE RESULT IS EXACT
>
> ```
> 4 rounds  x  0.75 retarget  x  1/3  =  1.000 AoO per combat
> ```
>
> **The melee x melee cell reproduces the 1-AoO-per-combat convention the model
> declares today, EXACTLY.** Per-round commitment and `m = 1/3` were decided
> independently and land on the existing baseline. Three consequences:
>
> 1. **The entire re-baseline is attributable to the RANGED-enemy cell**, where it
>    comes from a modelled mechanism rather than from a free parameter.
> 2. **The sign is now POSITIVE EVERYWHERE under BOTH readings of `both`** — so
>    the `reach_both` choice no longer sets the sign, only the magnitude. That
>    retires the "first-order" warning this section carried an hour ago.
> 3. §12.0c's band-dependent sign-crossing is **superseded**: it was the `m = 0`
>    corner, and `m = 0` is now excluded by decision.
>
> **CONTINGENT, and this is the catch:** the exactness rests on **uniform weights
> at `party_size = 4`**, i.e. on the very placeholder the threat class (§12.0g) is
> about to replace. Under uniform weights `P(retarget) = 1 - 1/party_size`, so the
> melee cell is `4 * (1 - 1/party_size) * m`:
>
> | `party_size` | melee x melee AoO/combat |
> |---:|---:|
> | 1 (solo basis) | **0.000** — no allies, so no retargeting at all |
> | 2 | 0.667 |
> | 3 | 0.889 |
> | **4 (the declared default)** | **1.000** |
> | 5 | 1.067 |
>
> So the coincidence is specific to the declared default, and **once the threat
> class changes the weights, either `m` is re-derived to preserve the convention
> or the melee cell is allowed to move as part of the re-baseline.** That is a
> decision to make deliberately, not to let drift — and it is exactly why the
> threat class is sequenced FIRST.

**THE RE-BASELINE UNDER THE LOCKED PARAMETERS.** `E[AoO/combat] =
P_melee x 1.0 + P_ranged x 4`, against the declared 1.0, with the measured
per-AoO values. **Baseline-subject figures — they bound the SHAPE, and are not
War Angel predictions**, whose per-AoO value differs (more on-hit riders):

| band | lvl | DPR per AoO | `E[AoO]` wide | ΔDPR | % | narrow | ΔDPR | % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 0-4 | 3 | 1.2642 | 1.603 | +0.76 | **+14.6%** | 1.369 | +0.47 | **+8.9%** |
| 5-10 | 8 | 1.6931 | 2.020 | +1.73 | **+15.8%** | 1.651 | +1.10 | **+10.1%** |
| 11-16 | 11 | 1.7146 | 2.353 | +2.32 | **+21.0%** | 1.966 | +1.66 | **+15.0%** |
| 17+ | 16 | 1.6959 | 2.308 | +2.22 | **+20.0%** | 2.134 | +1.92 | **+17.4%** |

**So the arc's predicted effect is +9% to +21%, positive at every band, rising
with the band's ranged share.** That is the fourth and current headline, and the
three it replaces are all recorded above: "downward" (item 5d), "+46.3%" (§3.3,
one cell), and "crosses zero" (§12.0c, the `m = 0` corner).

### 12.0g THREAT CLASS — SEQUENCED FIRST, and declared per (build, LEVEL)

**DECIDED (user, s63).** §3.5.4's threat class replaces `_ally_roster`'s uniform
weights, and it lands **before** Phase 1 so that `m` is not calibrated against a
placeholder and then re-calibrated.

- **It is a per-(build, LEVEL) declaration** (user): every build defines its
  character's threat class at every level. Same shape as AC and the six saves —
  a `LEVELS` row field, following the §14 sparse-build-data pattern.
- **It affects BOTH targeting probability AND tactics** (user), so it is coupled
  to the movement typology (§12.0b): a high-threat melee build is both targeted
  more AND wants to stay in contact. The two declarations should be settled
  together rather than one at a time.
- **It will move numbers, and which ones must be measured.** Changing the
  character's weight changes who absorbs swings. If nothing reads character HP
  the DPR may be untouched while `net_damage_taken_per_round` and the mitigation
  channel move — but that is a prediction, not a result, and it needs its own
  decision record.
- **It changes `P(retarget)` and therefore the melee x melee AoO rate**, which is
  the dependency that put it first.



**`m` IS NOW THE DOMINANT PARAMETER IN THE ENTIRE RE-BASELINE, AND IT IS
UNMEASURABLE.** Combining with §12.0c's measured per-AoO values and the census
reach mix, `E[AoO/combat] = P_melee*3.75m + P_ranged*4` against the declared 1.0:

| band | per-AoO | m=0 | m=0.27 | m=0.5 | m=1.0 |
|---|---:|---:|---:|---:|---:|
| 0-4 (lvl 3) | 1.264 | **-0.25** | +0.77 | +1.64 | +3.54 |
| 11-16 (lvl 11) | 1.715 | **+1.38** | +2.33 | +3.14 | +4.90 |

> **So §12.0c's band-dependent sign-crossing holds ONLY at `m = 0`.** For any
> `m` above ~0.1 the re-baseline is **positive everywhere and dominated by a
> declared parameter with no empirical basis.** That is an uncomfortable result
> and it is recorded rather than smoothed: `m` MUST be a swept sensitivity axis
> with its value in provenance, never a buried default.

~~**A CONVENTION-PRESERVING ANCHOR FOR `m`.**~~ **SUPERSEDED:** the anchor
proposed `m ~ 0.27` under the per-ATTACK retarget rate of 0.9375. Under the
per-ROUND commitment now decided, the rate is 0.75 and the user's experiential
`m = 1/3` reproduces the convention EXACTLY, so no anchor is needed. Kept
because the two arrived at nearly the same place by independent routes, which is
weak mutual corroboration and worth not forgetting. **Neither is a validation** —
the convention is from the user's own guide, and CLAUDE.md is explicit that no
number in the guides is an external validation source.

**AND THIS COUPLES THE ARC TO §3.5.4, WHICH WAS NOT ON ANY DEPENDENCY LIST.** The
uniform weights are described in the code itself as *"a PLACEHOLDER with its
replacement already designed: §3.5.4's threat class"*. Under threat weighting the
character — a melee threat — would draw MORE attacks, which LOWERS the retarget
rate and therefore lowers the melee x melee AoO rate. So the arc's magnitude
depends on a placeholder, and the two must be settled together.

### 12.0f CONDITIONAL KITING ROUTES — the free route can FAIL

**Raised by the user, s63.** Several of the corpus's kiting tactics are
**conditional**: they need an attack to land, or a save to fail, before they
produce the gap.

- **push / slow** — require a **hit**.
- **topple** — requires a hit **and** a failed CON save (doubly conditional).
- Tavern Brawler's shove — requires a hit with an unarmed strike.

So §12.0's condition-B route is not simply "declared and free". On a **miss** the
free gap never materialises, and the character falls back to a provoking retreat
or to standing in melee:

```
E[enemy output | kiting] = P(hit)*0 + P(miss)*(22.0 walking | 44.0 standing)
```

**Two consequences.**

1. **Accuracy buys defence for a kiting build.** The defensive value scales with
   the hit rate — a real emergent coupling the model produces for free, and a
   genuinely new output, since nothing today connects to-hit to damage taken.
2. **ARCHITECTURAL: the retreat is a POST-ROLL decision point, not a turn-start
   plan.** The policy cannot decide its movement at turn start, because it does
   not yet know whether the push landed. Movement must be a decision point the
   engine opens **after the attack resolves** — exactly the existing miss/hit
   decider seam (CLAUDE.md #7: *"decision points are events the engine opens for
   the policy to fill"*). **So Phase 1 must NOT model movement as a turn-start
   commitment.** Recorded here because getting it wrong would be an abstraction
   leak discovered late.

### 12.0d TWO DESIGN DECISIONS THE TYPOLOGY FORCES

1. **Enemy movement type must be drawn PER COMBAT, not per round.** Every other
   enemy axis (attack-vs-save mix, control budget) is a per-ROUND draw, but a
   creature that is melee one round and ranged the next produces incoherent
   movement — it would teleport between behaviours. So this is **the first
   quantity in the enemy model that must be fixed for a whole combat.**
   Consequence to price: 4 draws per day instead of ~16, so **more variance per
   day**, which bears on convergence and therefore on day-count tiers.
2. **The ranged enemy's step-out choice should be a DECLARED TOGGLE.** Starting
   its turn adjacent, it can (a) step out, eat one opportunity attack, and shoot
   cleanly, or (b) shoot from melee at disadvantage and provoke nothing. Both
   cost roughly one swing's worth, so the choice is not obvious and must not be
   assumed — and it directly sets the character's AoO rate in the one cell that
   generates them.

### 12.1 The user's eight categories, as accepted

Character-side reactions the model must account for. Spatial implication in the
third column — **that is the only column the spatial layer reads.**

| # | category | what the SPATIAL model must answer |
|---|---|---|
| 1 | standard opportunity attack | is the enemy leaving my reach, and HOW (§12.5)? |
| 2 | War Caster reactive spell (single-target, attack roll — typically True Strike) | same trigger as 1; **reach is bought to widen it** (a whip, `25_the_voice_of_heaven`) |
| 3 | self-defensive (Defensive Duelist, Flourish Parry, Stone Endurance, Deflect Attacks — some multi-tiered) | is the attacker within melee reach of me? |
| 4 | ally-defensive (Interception, Protection) | is the ally within R of me (**R=5ft — one of the few genuinely binding ranges**)? |
| 5 | condition create/prevent | within R (mostly 30ft ⇒ non-binding, §12.6) |
| 6 | on enemy death | **DEFERRED — §12.8** |
| 7 | spell-granted / spell-as-reaction (Blinding Retort, Hellish Rebuke, Counterspell) | within the spell's own R |
| 8 | Readied action | **DEFERRED — §12.7** |
| **9** | **reaction MOVEMENT (self or ally)** | **NEW — accepted as an oversight (user). The only category whose EFFECT is a spatial change** |

**Category 9's corpus instances**, all four distinct: Wardancer L4 College of
Dance (*"reaction to expend a BI and move up to 1/2 your speed"*, non-provoking);
`25_the_voice_of_heaven` granting an **ALLY** *"reaction to move up to speed w/o
provoking OAs"* (category 4 crossed with 9); Psionic Feystepper's Misty Escape
(reaction **teleport** on taking damage) and Duplicitous Target (reaction
**position swap** with a willing creature within 30ft).

### 12.2 Sentinel — RULED

- **Halt**: a hit with an opportunity attack sets the target's Speed to **0 for
  the rest of the turn**. Under §12.0 this is the model's primary *trapping*
  mechanic, not a damage rider: it ends the exit.
- **Guardian**: an opportunity attack triggers when a creature within 5ft
  **takes the Disengage action** (or hits someone other than you). So Sentinel is
  **the only thing in the corpus that defeats Disengage**, and
  `37_white_dragon_warrior` is built end-to-end on it.
- **RULED (user, s63): a War Caster reactive spell used in place of the
  opportunity attack does NOT proc Halt.** Settled as a decision rather than
  left to interpretation; currently moot (no guide takes both feats) but it must
  not be re-litigated when one does.
- Only **2 of 33** guides take the FEAT; the other six matches are the Sentinel
  *Shield* item.

### 12.3 Forced movement and teleportation DO NOT provoke — CONFIRMED

The 2024 trigger is leaving reach using an *action, bonus action, reaction, or
one of its speeds*. Being shoved is none of those; teleporting is not either.
**Several kiting builds depend on this** (user). Consequences:

- `20_the_wardancer`'s Tavern-Brawler shove-kite loop generates **zero**
  opportunity attacks for anyone. Its value is damage plus denying the enemy its
  melee — not AoO farming.
- `26_the_shadow_giant:70` states the corollary as a tactic: **"push mastery
  will auto-disengage if you hit with the rapier"** — forced movement is a
  *free* Disengage, costing no action economy at all.
- The three deferred positional masteries split asymmetrically: **push** exits
  reach with no AoO; **slow** (−10ft) is a speed DEBUFF that feeds §12.0's
  trapping mechanic; **topple** makes standing cost half movement.
- Teleports (18/33 guides) are AoO-free exits.

### 12.4 Mounts — the AoO carries a TARGET CHOICE

**New from the user, s63.** When a mounted rider leaves an enemy's reach, **the
enemy chooses whether to target the mount or the rider.** That choice is a real
build axis: Mounted Combatant redirects attacks aimed at the mount onto the
rider (veer), and `42_lost_voice_of_the_old_ones` uses a deer familiar
specifically to discourage targeting the mount while kiting. So the enemy AoO is
not just "attack the provoker" — it needs a target selection over
{mount, rider}, which the existing trait-weighted friendly roster (design §3.5)
is the natural place for. Mount and rider share a zone and move at the mount's
speed (`design.md` §3.1), and the rider spends none of its own movement.

### 12.5 Disengage — to be MODELLED, and its cost is BUILD-DECLARED

**Decided (user, s63): add the mechanical realism, as part of this arc.**

What it does: a declared action that consumes action economy and prevents
movement from provoking opportunity attacks for the turn — **unless the
observer has Sentinel or equivalent** (§12.2).

**The cost is NOT a constant, and the asymmetry is the design's whole point:**

| actor | what Disengage costs | therefore |
|---|---|---|
| the baseline enemy | an **Action** — i.e. its entire Multiattack | almost never worth it to deny ONE opportunity attack ⇒ **it eats the AoO** |
| Rogue (Cunning Action) | a **bonus action** | cheap |
| Monk (Patient Defense) | a **bonus action, FREE in 2024** (`16_bounty_hunter:109`: *"patient defense (PD) to disengage as a BA for free"*, Dodge too for a focus point) | nearly free |
| Barbarian Wildheart (eagle) | **BA Disengage + Dash** (`17_feyheart_barbarian:157`) | nearly free |
| Nimble Escape | **BA disengage or hide** (`18_witchdoctor:30`) | nearly free |
| anyone with push mastery | **nothing** — forced movement (§12.3) | free |

So Disengage is a **cost-tagged modality with a per-build declared cost**, not a
fixed Action. This asymmetry is what makes the enemy feed the character
opportunity attacks (§3.1) while the corpus's kiting builds deny them cheaply —
and it is therefore load-bearing for the §4.1 magnitude.

> **RULES-VERIFICATION FLAG.** The exact 2024 *Player's Handbook* wording for
> Disengage itself could not be retrieved from an official source; the web
> results were secondary or 2014-era. What IS verified: the bonus-action
> variants above, from the user's own 2024-based guides at the cited lines, and
> the trigger/Disengage interaction from §3.1's search. **Open and unconfirmed:
> whether 2024 Disengage grants anything BESIDES provocation immunity.** Confirm
> against the PHB or SRD 5.2 before implementing, per the per-feature ritual.

### 12.6 Range bands — DEFERRED, and the arena is why

**The user's objection is correct and my §5/§9 derivation was biased.** I derived
range bands from the ranges attached to *reaction* features (5/20/30/45/55/60ft,
30ft modal). But ranges govern **non-reaction** abilities too, so the reaction
corpus is a biased sample and the arc must not settle a general
spatial-resolution question from it.

**And under §12.0 the question is mostly moot.** If the arena is about one move
across, then:

- a **30ft+** reaction range covers the whole arena ⇒ **satisfied by
  construction**, always has a legal target, needs no spatial check;
- **5ft** ranges (Interception, Protection, Sentinel Guardian) are genuinely
  binding and need a real check;
- **melee reach (5 vs 10ft)** is the one distinction that must be modelled
  properly.

> So the spatial layer needs **ONE relation — `within_reach(A, B)` — plus zone
> membership for hazard zones.** Not a global zone lattice, not range bands.
> That is a large simplification and it is forced by the user's own constraint
> rather than chosen for convenience.

Range bands return as a general question when a non-reaction ability makes them
bind — most likely alongside multi-character party support and the AoE share
(§10). Not this arc.

### 12.7 Readied actions — DEFERRED, with the canonical case recorded

Zero of 33 guides mention readying an action, so this is deferred on **evidence**
rather than judgement. But the user named the case that will force it, and it is
recorded so it is recognised rather than re-derived:

> A **hasted rogue** gets two Attack actions. It spends the first on its own turn
> to proc Sneak Attack, then **readies** the second with any trigger to get Sneak
> Attack again on an enemy's turn. A **melee** rogue already achieves this with a
> standard opportunity attack; a **ranged** rogue cannot — so the readied action
> is what lets a hand-crossbow or pistol rogue reach **two Sneak Attacks per
> round**.

Build it when a real build forces it (user). Note that `Ready` is already in
`taxonomy.MODALITIES` **and wrongly in `COMBAT_MODALITIES`** (§12.9).

### 12.8 On-death reactions — DEFERRED, and the gap is wider than finite HP

Fiend warlock's Dark One's Blessing and similar trigger on an enemy dropping
within range. Deferred, and the reason is structural rather than just
`mode="finite_hp"` being unwired:

> **The model fields ONE enemy, so if it dies the COMBAT ENDS** (user). There is
> no BBEG-plus-adds roster for on-death reactions to fire against repeatedly, so
> even with finite HP staging in place the gap is several steps wide, not one.

Recorded so the finite-HP mode is not mistaken for sufficient.

### 12.9 A SECOND fail-open found in the same family as §7.4

`taxonomy.COMBAT_MODALITIES` is documented as *"the subset that has
combat-resolution machinery in the engine"* and lists `Attack`, `Magic`,
`Use Ability`, `Dash`, `Disengage`, `Dodge`, `Help`, `Ready`. **Five of those
eight have no machinery anywhere** — the only non-`taxonomy.py` hits for
Dash/Disengage/Dodge/Help/Ready are two comments. So the comment asserts
machinery that does not exist, in the MODALITY vocabulary, exactly as §7.4 found
in the COST vocabulary.

This matters directly: §12.5 makes Disengage load-bearing, and it does not
exist for either side today. Fix it the same way — classify the vocabulary and
let an unimplemented member refuse — when Phase 2 lands.

---

## 13. THE BUILD PLAN

Phases are ordered by what each one BUYS, not by implementation convenience.
Every phase ships **default-OFF** per §8.

**Phase 0 — THE THREAT CLASS (§12.0g), sequenced FIRST.** §3.5.4's threat class
replaces `_ally_roster`'s uniform weights; declared per (build, LEVEL) alongside
the movement type (§12.0b), since both affect tactics and targeting. It goes
first because `P(retarget)` sets the melee x melee AoO rate, and calibrating `m`
against a placeholder would mean calibrating twice. Needs its own re-baseline
decision record: it changes who absorbs swings, which may leave DPR untouched
while moving the damage-taken and mitigation channels — a prediction to measure,
not assume. **Also lands the per-ROUND targeting commitment** (§12.0e), which is
mean-preserving but not necessarily bit-identical.

**Phase 1 — the spatial substrate.** `reach` on entities (5/10ft); a typed
**exit event** carrying its exit KIND (own-speed/action/BA/reaction → provokes;
forced/teleport → does not; Disengage → does not, unless Sentinel);
`distance(A, B)` and `within_reach(A, B)` readable from the policy snapshot as a
pure read (CLAUDE.md #7). No speed. **Movement must NOT be a turn-start
commitment** — §12.0f shows the kiting retreat depends on whether the attack
landed, so it is a post-roll decision point. **The exit-kind vocabulary is the load-bearing decision of the
whole arc** — get it right and §12.3's three masteries, 18 guides' teleports and
Sentinel all become data.

**Phase 2 — the two opportunity attacks, and THE RE-BASELINE.** The character
AoO as a subscriber to the exit event, replacing the declared `aoo_per_combat`
(§6 row 1 — decide override-vs-delete); the enemy AoO as **one**
`baseline_attack_dice` roll (no scaling — §12.5's table in the review, already
per-swing); Disengage as a cost-tagged modality with a build-declared cost
(§12.5); the mount/rider target choice (§12.4). **This is the phase that moves
every number, upward, by a magnitude §4.1 already bounds.** Fix §12.9 here.

**Phase 3 — reaction contention.** One slot, nine categories. Settle whether the
defender-side intercept starts debiting (§7.5). **This is the phase that lifts
#6b's scope bound** — and its intercept half can land EARLIER and separately,
since it moves only War Angel L14-16 (§4.2) and needs no spatial model at all.
Worth doing first for that reason.

**Phase 4 — speed, kiting and trapping (REBUILT on §12.0's locked model).**
Carries §12.0e's `m` (the retarget-requires-movement probability) as a **swept
axis with provenance, not a default**, settled together with §3.5.4's threat
class, since the uniform party weights it depends on are a placeholder; and
§12.0f's conditional routes, whose retreat decision is a POST-ROLL decision
point rather than a turn-start plan. Not
zone-exit gating any more: the mechanism is the **geometry condition
`S_c + p > S_e`** against a **build-declared provocation route** (§12.0 condition
B). Deliverables: character speed per (build, level); enemy speed as a
**distribution** per band, with escape resolved as a PROBABILITY rather than a
threshold on a mean; the three character types and two enemy types (§12.0b) as
declared policy attributes; the per-COMBAT enemy-type draw and the ranged-enemy
step-out toggle (§12.0d); `slow`, Sentinel's Halt and grapple as speed
modifiers; forced movement as free, non-provoking gap. **This is what makes
`37_white_dragon_warrior` and the corpus's eleven kiting builds modellable at
all**, and it is where the band-dependent re-baseline of §12.0c is measured
rather than predicted.

**Phase 5 — reaction movement (category 9).** Self and ally movement reactions,
reaction teleports, position swaps. Needs Phase 1's exit kinds (all of these are
non-provoking) and Phase 3's contention.

**Deferred with named reasons, not silently:** readied actions (§12.7, zero
corpus support, canonical case recorded), on-death reactions (§12.8, one-enemy
model), range bands (§12.6, biased sample + mostly moot under the arena),
targeting tendencies and a grid (§10).
