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

§4.1. The arc's measured dominant term is **+46%**, not negative.

> **The honest summary:** positioning has an additive term that is measured,
> large and reliable, and a subtractive term that is conditional on a speed
> differential **for which the project holds no data at all** (§7.3). Planning
> this arc as a downward re-baseline would get the sign wrong. Planning it as
> "numbers move, direction known per build" is right.

---

## 4. MEASURED MAGNITUDES

All at engine `a56ae31` (clean), seed 20261110, `enemy="baseline"`.

### 4.1 What an opportunity attack is worth

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

### 7.3 Reach AND speed on entities — **SPLITS: reach is grounded, SPEED IS A SECOND BLOCKER**
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

## 11. OPEN QUESTIONS FOR THE USER

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
