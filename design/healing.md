# Healing — decision record and build plan

> **Status: BUILT (session 45). Semantics locked in session 44 and revised twice
> after user review, most recently 2026-08-20 on summon Hit Dice — §7(b2).**
> §§1-10 are the design record that preceded the build; **§11 is the session-45
> settlement of §10's six open questions plus the measured validation.** Steps (a)-(d)
> of the §9 build plan are done; step (e), the metrics, remains deliberately deferred
> on the output-kinds design (§8).

---

## 1. The finding: healing is not modelled at all

`design.md` §8 lists "HP recovered" as a missing *output channel*, and
`evaluation_framework.md` §14 carried it as a metric gap. Both understate it.

- **`Entity.heal()` exists and has ZERO callers in `src/`.** There is no healing verb,
  no `Choice` that produces healing, and no policy path that requests it.
- **What looks like healing in the build data is not.** War Angel's Prayer of Healing
  is modelled as a **short-rest-equivalent for resource recovery**
  (`war_angel.py:1263` calls `resources.restore_sr()`), never as HP restored.
- The only HP-restoring line in the whole engine is Silvertail's Aid effect bumping
  `max_hp`/`hp` at cast time (`silvertail.py:601`), which is a buff, not healing.

So "track healing, including healing provided by summons" (user, s44) is not a metric
addition. It is a missing subsystem.

**31 of the 33 build guides reference healing** — Cure Wounds, Prayer of Healing,
Healing Word, Second Wind, Lay on Hands, Aura of Vitality, Goodberry, Mass Healing
Word, Healing Light. Raw keyword counts **overstate combat relevance** (many are
spells-known lists rather than combat policy; §7.1's survey is what separates them),
but the breadth is not in doubt. This is a cross-cutting primitive, which is exactly
the case where designing up front is cheaper than discovering the shape from the
first build.

## 2. What healing MEASURES here (user, s44) — the framing that drives everything

The purpose is **not** to simulate in-play healing decisions. It is to produce a
standardized survivability quantity: **potential healing, stacked against expected
incoming damage.**

The dynamic being proxied is real and otherwise invisible to the 4×4 basis. Two
sustained-damage builds can post similar DPR while one has internal healing; that
build is genuinely better, because the party's healer spends fewer of *their* limited
resources on it and shared consumables (potions) are freed for others. **We do not
model party healers or consumables.** Quantifying a build's healing output is the
rough standardized capture of that advantage.

**Consequences of taking this framing seriously** (all decided by the user, s44):

- **No `max_hp` cap on the unbounded trackers.** Capping would make healing's value
  depend on when damage happened to land relative to when healing was applied — a
  sequencing artifact the model does not represent well. Potential healing is a
  property of the BUILD; the reader compares it against incoming damage, which the
  report also carries. Realism is not the objective here.
- **Delivered and effective healing are therefore the same number** for characters and
  allies. The delivered/effective split an earlier draft proposed collapses, and the
  metric set gets smaller.
- **`net_damage_taken_per_round` can go NEGATIVE** for a high-healing build. That is
  correct under a balance reading — surplus capacity — and the metric definition must
  say so, because it is not "hit points gained".

## 3. The constraint: what `hp` actually is in this engine

`hp` is read in **exactly four places**, and everything that gates behaviour reads
`destroyed`, not `hp`:

| site | what it gates |
|---|---|
| `entity.py:217` (`take_damage`) | `dies_at_zero_hp` → sets `destroyed` |
| `entity.py:234` (`is_functionally_dead`) | **no callers outside `entity.py`** |
| `entity.py:239` (`is_alive`) | **no callers outside `entity.py`** |
| `scheduler.py:351` | finite-HP combat termination (enemies only) |

So for a character, `hp` is effectively **write-only**: it is `max_hp − cumulative
damage`, a signed balance that can go arbitrarily negative, and nothing consults it.

**A superseded claim, recorded so it is not re-derived.** An earlier draft of this note
argued that applying healing to that tracker is "incoherent" because real D&D floors at
0. That was wrong (user correction, s44). It assumed the tracker ought to behave like
hit points; it should not, because once negative it already is not hit points. As a
signed balance, `net_hp = max_hp − damage + healing` is well-defined and comparable
across builds. What remains true from that analysis — and is now load-bearing in the
opposite direction — is that healing a character is **behaviourally inert**, which is
precisely what makes it safe to apply: it cannot move any DPR baseline.

## 4. LOCKED semantics

**Healing applies to the tracker. Cap only where `hp` is live. Enemies are never
healed.**

The cap follows the zero-HP CATEGORY (§6), not the roster role — a `threshold` summon
is an unbounded tracker exactly like a character, which is what Silvertail's default
(`mortal_beast=False`) immortal beast already is.

| class | at ≤ 0 HP | `max_hp` cap on healing | healable |
|---|---|---|---|
| character, party ally | keeps acting; balance goes negative | **no cap** (§2) | yes |
| summon — `threshold` | keeps acting; balance goes negative | **no cap** | yes |
| summon — `vanishes` | removed permanently | **capped** | no, once gone |
| summon — `downed` | stops acting; `hp` floored at 0 | **capped** | yes → resumes acting |
| enemy | unchanged | — | **never** (§5) |

**Why summons keep the cap.** A summon's `hp` is not a balance — it is live state that
gates death and turn access. Healing one past `max_hp` would make it genuinely tankier
than it can be: a behaviour change, not a reported number. The floor at 0 for `downed`
is required for the same reason: without it, a heal after a large hit would not revive
a companion that took 30 damage past zero.

**Every heal is recorded in a SOURCE-ATTRIBUTED `(source, target)` ledger**, mirroring
`damage_by_source_target`. Source attribution is not optional — "healing provided by
the summon" is a stated requirement, and the s44 lesson was that aggregate ledgers
silently pool the character's, the summon's and the enemy's numbers (see PROGRESS.md's
per-metric ritual).

## 5. The enemy is never healed (user, s44)

Healing applies to summons, the party, and the character only. No enemy healing
capability is modelled, and none is planned; a future build needing it makes a
specific exception. This removes the `finite_hp` enemy-healing case an earlier draft
carried, and means healing never affects combat termination.

**Deferred, named:** party members with finite HP feeding enemy TARGETING (a dead ally
makes the character likelier to be hit). This is a `BaselineEnemyPolicy` target-weight
change and needs the multi-character roster work already blocking two `enemy_model.md`
§7 toggles. Explicitly deferred (user, s44); recorded beside those.

## 6. Summon categories — a three-way axis, not a boolean

`Entity.dies_at_zero_hp` is a boolean and cannot express the corpus (user, s44):

1. **`vanishes`** — summon-spell creatures disappear at 0 HP and cannot be healed back.
   This is what the current boolean models.
2. **`downed`** — the creature drops but remains present and can be healed back into
   the fight.
3. **`downed` + an on-zero trigger** — e.g. the reanimator artificer's companion fires
   a death effect but is still revivable.

Cases 2 and 3 are mechanically identical; they differ only by an effect, and the
existing `effect_source` substrate already handles that. So the shape is an **enum
`{threshold, vanishes, downed}` plus an optional on-zero effect**, not four classes.
**All types are healable while above 0** — the universal rule the engine supports not
at all today.

**Engine cost, contained but not trivial.** `destroyed` is currently PERMANENT
(`if ... and not self.destroyed`). `downed` needs a *reversible* state, and the
scheduler's skip at `scheduler.py:969` must honour both.

**RULES-VERIFICATION FLAG.** `silvertail.py:633` carries a web-verified note dated
2026-06-19 for the **2024** Primal Companion: the beast *dies* at 0, and revival takes
a Magic action, a spell slot, and **1 minute** — which is why revival was built as a
between-combats action that can never land inside a 4-round fight. That conflicts with
"a beastmaster companion can be downed and healed within combat" (user, s44), which may
be 2014 wording. It does not threaten the taxonomy: the reanimator case still needs it,
and "healable above 0" is universal and entirely absent today. But **each companion's
category must be assigned from verified 2024 text**, per the per-feature ritual — not
from the archetype's reputation, and not from this note.

## 7. Hit Dice at the short rest (user, s44)

**The model: every entity spends ALL its Hit Dice at the short rest, automatically.**
This is elegant because it needs no policy — no conditions to specify about when a
character heals — and it lands at a well-defined moment. Under §2's no-cap framing it
is also the *right* model rather than merely a convenient one: spend-all is what
produces the standardized potential figure, independent of how much damage happened to
land. (An earlier draft argued spend-all equals spend-to-deficit; that argument
depended entirely on the `max_hp` cap and no longer applies.)

**Exception:** a build that spends Hit Dice on something else. Starfire Scion does —
Fueled Spellfire expends up to 2 HD into a radiant spell's damage
(`starfire_scion.py:1594`), and its `hit_dice` pool is that resource. Contested HD are
a build-policy question ("policies are code"), so the short-rest hook asks the build
how many HD are available for healing.

**Four notes the build must carry:**

**(a) Mean-field, not rolled.** Use `N × (avg die + CON modifier)`. Rolling would draw
dice and shift the RNG stream for every existing build, breaking the `§12`
bit-identical parity proof against `validation.py` — the project's only end-to-end
regression signal after guide-replication was retired. Mean-field draws nothing,
preserves the proof, and matches the model's stated low-variance convention. This is
the same problem RNG substreams (`evaluation_framework.md` §13 step 8) exist to solve,
and it is evidence that *any* new dice source will hit it.

**(b) One short rest is the ENGINE baseline; a second is something a build BUYS.**
`design.md:96` and `model_setup_notes.md:37` both lock **one** short rest per day, and
`_determine_sr_placement` implements exactly that. War Angel nonetheless gets two rest
events, because its Prayer of Healing hook calls `resources.restore_sr()` as a
"short-rest-equivalent" in a different interval — hence its `# 9 / LR with PoH + SR`
data comments. **HD spending attaches to REAL short rests only**: RAW, Prayer of
Healing is not a short rest and grants no Hit Dice. So War Angel gets one HD window,
not two.

**(b2) SUMMONS SPEND HIT DICE AFTER EACH COMBAT, TO THE DEFICIT. DECIDED — user,
2026-08-20.** After every combat (the `between_combats` hook already fires after each,
including combat 4), a summon spends Hit Dice to **heal its deficit — `max_hp − hp` —
bounded by its remaining pool.** Not "top up to full": the pool is the binding
constraint, and once it is empty the summon gets nothing after later combats.

**Stated as a deficit, this rule never overheals**, so the §4 cap question does not
arise for Hit Dice at all — it is well-defined for any entity with a `max_hp`,
including a `threshold` summon.

**It deliberately breaks RAW** — Hit Dice are spent on short rests, and this spends
them after every combat. Accepted (user): the alternative is modelling summon
damage/healing TIMING, and the complexity that would add buys too little.

**Why this differs from the character rule, and why that is not an inconsistency.**
The character spends all dice unconditionally and uncapped — *potential* healing,
§2's survivability proxy, where every die counts because nothing reads a character's
`hp`. A summon spends only what it needs — *actual* healing, mechanically real because
its HP gates death and turn access. Two rules because they measure two different
things; it is the §2/§4 split appearing again, not a rule that drifted.

**What this buys that a simpler rule would not.** Three things, and the third is the
reason a "summons never spend HD" draft of this section was rejected:
1. a **depletion curve** bounded by the pool — the same shape `dpr_combat_1..4`
   exposes, and what the four-combat day exists to show;
2. **damage-responsive spending** — a lightly-damaged companion keeps dice for later,
   which makes the pool a real resource rather than a fixed bonus;
3. **an interaction with external healing**: if the character heals the beast, the
   beast spends fewer of its OWN dice. Character healing therefore has knock-on value
   in preserving companion resources — exactly the kind of mechanism this subsystem
   exists to surface, and one a never-spend rule would hide completely.

**Ordering against the `recast` hook.** Both live in `between_combats`. Revive FIRST
(`recast` restores the beast at full HP — `silvertail.py:649`), then apply HD healing,
which is then a no-op because the deficit is zero. A `vanishes` summon that is
destroyed and NOT revived cannot be helped by Hit Dice at all; a `downed` one can, and
healing it above 0 is what returns it to acting (§6).

**(c) One baseline moves: Silvertail at `mortal_beast=True`, and nothing else.**
Character-side HD healing moves nothing — `hp` is behaviourally inert for characters
and allies (§3) — and (a)'s mean-field rule draws no dice. Summon HD healing under
(b2) DOES change behaviour, but only where a summon's HP gates something: that is
`mortal_beast=True`, a NON-DEFAULT toggle (`mortal_beast` defaults to `False`). The
default Silvertail path is a `threshold` summon whose `hp` nothing reads, so it moves
no dice either. Expect exactly one intended diff, and treat any other movement as a
bug.

**(d) Hit Dice are build data we mostly do not have.** Only Starfire Scion has a
`hit_dice` pool. War Angel, Silvertail and the beast all need HD count, die size and
CON modifier added to their level tables. **Stated assumption (user, s44): a long rest
restores ALL expended Hit Dice**, which is what `restore_lr()` already does — flagged
for RAW verification (2024 may specify half your total), but harmless either way for
independent days.

## 8. Metrics — deliberately small (3 scalars + 1 breakdown)

**BUILT s46**, as the first customer of `evaluation_framework.md` §5.4's output kinds.
Applying PROGRESS.md's parsimony rule. Note that under §2 there is no delivered /
effective split for characters, which keeps this smaller than an earlier draft.

Every one of these went through the per-METRIC ritual's question 1 — *whose quantity is
this?* — and the answer is NOT the same for all four (settled with the user, s46):

> **The two DEFENSIVE scalars are CHARACTER-scoped; the OUTPUT scalar follows
> `RunConfig.attribution`.** Defence mirrors `damage_taken_per_round`'s deliberate rule
> (§5.3): a summon self-healing is its own column, not a discount on the character's
> cost. Output follows `own_roles`, so a healer-summon's contribution counts as the
> build's under `attribution="character_and_summons"` — which is what
> `evaluation_framework.md` §14 point 3 asked for.

- **`net_damage_taken_per_round`** — `(damage taken by CHARACTERS − healing received by
  CHARACTERS, any source) / rounds`. The defensive headline. **May be negative** — that
  is surplus healing capacity, not an error, and the registered `definition` says so in
  those words.
- **`external_healing_required_per_day`** — `max(0, character damage taken − character
  SELF-healing)`, where self-healing means `source ∈ characters AND target ∈ characters`.
  Literally the quantity a party healer would have to supply; the sharpest expression of
  §2's dynamic. **The clamp is PER DAY**, so the metric is the mean of the clamped
  quantity, not the clamp of the mean — a consumer deriving it from two other means gets
  a different number, and the definition says so.
- **`healing_provided_to_others_per_day`** — healing whose SOURCE is in `own_roles` and
  whose TARGET is not. Output that saves the party's budget; zero for a selfish build,
  large for a healer. Carries an availability predicate: on a roster with no healable
  entity outside `own_roles` (enemies are never healed, §5) the metric is **unavailable
  with a stated reason**, not a zero — a 0 there would be roster poverty (§3.3's
  multi-character party is deferred) misreported as a build property.
- **breakdown: `healing_by_source`** — keyed **`source_role × context`** (3 × 2 cells),
  per day. **NO margin over `context` is declared**, so no cell in the artifact ever sums
  healing under fire with healing at leisure — §11.1 found the corpus does most of its
  healing out of combat by preference, and the two are different quantities. The
  don't-pool rule is thereby enforced by the SHAPE rather than by a comment. Collapsing
  `source_role` IS declared, giving a per-context total.

**Dropped as algebraically derivable:** `self_sufficiency` =
`1 − external_required / damage_taken`; `net_hp_end_of_day` =
`max_hp − rounds_per_day × net_damage_taken_per_round`. (Both fail §5.4's survival rule
on the second clause too: nobody reads them.)

### 8.1 What the three builds actually measure (s46, live)

The per-METRIC ritual's Silvertail test, run against the shipped registry:

| build | `healing_by_source` cells | reading |
|---|---|---|
| War Angel L13 | `characters × between` = 63.5 | PoH's mean-field 2d8+WIS plus Hit Dice at two short-rest windows |
| Starfire Scion L15 | *none* | its Hit Dice are reserved for Fueled Spellfire (`available_for_healing=False`), so `external_healing_required_per_day` equals its FULL damage taken — the metric doing exactly §2's job |
| Silvertail L10 | `characters × between` = 60.0, `summons × between` = 26.0 | the beast heals ITSELF from its own Hit Dice (§7 b2) |

Two facts this pinned down. **The summon's 26.0 appears in the `summons` cell and moves
no character-scoped scalar** — that is the roster-scoping check passing, and it is why
Silvertail is the build the ritual names. And **every healing cell in the corpus today
has `source == target`**, so `healing_provided_to_others_per_day` is 0 everywhere: a
genuine measured zero for Silvertail (another entity exists and the character does not
heal it) and an *unavailable* for War Angel and Starfire, whose rosters hold nothing
healable but themselves. War Angel's Prayer of Healing heals five creatures RAW and one
here purely because the roster has one — the availability predicate is what keeps that
modelling limit visible instead of reporting it as selfishness.

## 9. Build plan

1. **A healing EFFECT in the verb/effect layer** — a `Choice` must be able to produce
   healing, with a declared place in the resolution phase order relative to damage.
   This is the piece that does not exist at all.
2. **The source-attributed ledger + a §13 telemetry channel** — `(source, target)`
   keyed, carried on `CombatResult` → `DayResult` like the damage ledger. RESOLUTION
   writes it, never policy (CLAUDE.md #7).
3. **The summon-category enum** (§6) — self-contained and independent of the corpus
   survey; can land first if convenient.
4. **Hit Dice at the short rest** (§7) — needs the HD build data.
5. **Metrics LAST** (§8) — gated on the output-kinds design.

## 10. Open questions the build session must settle FIRST

1. **The corpus survey (§1).** Which of the 31 guides' healing references are actual
   combat policy versus spells-known noise? That determines the effect layer's
   vocabulary: single-target in-combat (Healing Word), action-cost burst (Cure Wounds),
   over-time (Aura of Vitality), self-only (Second Wind), pool-based (Lay on Hands),
   out-of-combat/interval (Prayer of Healing, Goodberry).
2. **Prayer of Healing is currently doing two jobs.** It is abstracted as a
   short-rest-equivalent for resource recovery (§7b). RAW it restores
   `2d8 + spellcasting modifier` to up to six creatures — directly modellable once
   healing exists. **Adding the RAW effect without revisiting the abstraction would
   count PoH twice.** Reconcile explicitly.
3. **Temporary hit points are a DIFFERENT primitive.** Temp HP is a damage buffer, not
   HP restoration — it does not stack, it expires, and it is consumed before HP. It
   most likely belongs on the modifier/status substrate (`buff_primitive.md`). Decide
   explicitly rather than letting it drift into "healing".
4. **In-combat versus between-combat healing.** The day model has between-combat
   windows, and PoH occupies one. Healing under fire is a different quantity from
   healing at leisure and should not be pooled into one per-round number.
5. **Which summons have Hit Dice, and how many?** §7(b2) now makes a summon's pool
   load-bearing — it sets both how much recovery the companion gets and how fast it
   runs out — so this is DATA the build needs, not a footnote. It should not be assumed
   from the character rule that a summoned creature has Hit Dice in the PC sense. Get
   the count and die size per companion from verified 2024 text in the survey. A
   companion with NO Hit Dice simply never heals this way, which is the rule degrading
   gracefully rather than a special case.

6. **Verify baseline movement is confined to the ONE expected place.** The ledger is
   pure observation; character-side `hp` is behaviourally inert (§3); Hit Dice are
   mean-field and draw no dice (§7a). The only intended diff is **Silvertail at
   `mortal_beast=True`**, where summon HD healing changes whether the companion
   survives later combats (§7c) — a non-default toggle. The §12 parity proof
   (bit-identical against `validation.run_level`) must stay green throughout, and any
   movement outside that one scenario is a bug, not drift. The other legitimate source
   of change is a build that starts actually CASTING a healing spell in combat, since
   that spends an action or a slot that would otherwise have produced damage — a real
   modelling change, not drift.

---

## 11. §10 SETTLED — corpus survey + rules verification (session 45)

Done BEFORE any code, per §10 and the design-first rule. Method: all 33 guides
scanned for the healing vocabulary; 1,023 matching lines reduced to ~350 carrying
policy language, then read. **The raw counts do overstate combat relevance** exactly
as §1 predicted — the bulk are spell-list entries (`lvl-1 (cleric): cure wounds, …`)
and per-level feature restatements (`lay on hands (25)`), which repeat one decision
once per level. The distinct *policy* statements number in the low dozens.

### 11.1 The effect layer's vocabulary (§10.1)

Eleven shapes appear. The first eight are heals; #9–#11 are adjacent primitives that
the survey separated out — and that separation is most of this section's value.

| # | shape | corpus instances | in / between combat |
|---|---|---|---|
| 1 | **self-only, BA, non-spell, per-day uses** | Second Wind (1d10 + fighter level, x2-3/LR, +1/SR) — 9 guides | in-combat |
| 2 | **single-target, BA, ranged, slot** | Healing Word — 11 guides | in-combat |
| 3 | **single-target, ACTION, touch, slot, upcasts hard** | Cure Wounds (2d8+mod, +2d8/level) — the most-cited spell in the corpus | both |
| 4 | **pool-based, BA, flat points, no roll** | Lay on Hands (5 x paladin level) — 5 guides; Healing Light (celestial warlock, Nd6 pool, SR-recharge) — guide 25 | in-combat |
| 5 | **over-time, concentration, per-turn** | Aura of Vitality (2d6 on cast + 2d6 each turn, 1 min, up to 20d6) — 5 guides | between (explicitly) |
| 6 | **interval, multi-target, + short-rest benefit** | Prayer of Healing — 9 guides | between only (10-min cast) |
| 7 | **Hit-Dice-as-a-heal** | Arcane Vigor (BA, self, roll 1-2 unexpended HD + spellcasting mod) — 5 guides | in-combat |
| 8 | **multi-target burst** | Mass Healing Word (BA), Mass Cure Wounds (action) — mostly "break glass" | in-combat |
| 9 | **healing AMPLIFIERS (not heals)** | Chalice (+1d8 then 2d8+WIS when you restore HP with a slot), Warrior of the Gods (+1d12, CON x/day), Empowered Healing (add a psionic die), Periapt of Wound Closure (double HP from a Hit Die), Uncanny Metabolism | rider on any heal |
| 10 | **at-will / resource-free heals** | Divine Spark (CD: 1d8+WIS), undying rite focus, Goodberry (10 x 1 HP; used as a *revive* utility) | both |
| 11 | **TEMPORARY HP** | False Life (91 mentions), Armor of Agathys, Aid, Heightened Focus, Bolstering Performance | — |

**What this buys the build: ONE new verb, not a family.** Shapes 1-4, 8 and 10 are all
"restore `Nd(S) + mod` (or a flat pool draw) to a target" and differ only in cost,
target count, and action economy — all of which `Choice` already carries. Shape 5 is a
RECURRING heal, which is the existing zone/turn-boundary substrate (#7b), not a new
primitive. Shape 7 sources its dice from a resource pool the engine already has. Shape
9 is the modifier stack with a healing phase tag. So the effect layer needs:

- a **`heal` verb** (dice + flat + ability modifier, targeted), and
- a **healing phase** on the modifier hook so #9 folds in,

and nothing else. This is the design-first payoff: surveying first turned what looked
like six spell implementations into one verb plus reuse.

**§10.4 — in-combat vs between-combat is REAL and the corpus insists on it.** The
guides are strikingly consistent that healing is preferentially done out of combat
("we really prefer to do the majority of our healing out of combat, if we can" —
guide 41), and shapes 5 and 6 are between-combat by construction (concentration over
1 minute; a 10-minute cast). Pooling these into one per-round number would be wrong.
Healing is therefore ledgered with its combat context, not as a single day total.

**§10.3 — TEMPORARY HP IS NOT HEALING. Decided, and out of scope here.** It is a
damage BUFFER: it does not stack, it expires, it is consumed before HP, and it cannot
be "overhealed". It belongs on the modifier/status substrate (`buff_primitive.md`),
and Silvertail's Aid already bumps `max_hp`/`hp` as a buff (§1). The survey shows the
temp-HP vocabulary is large enough (False Life alone: 91 mentions) to deserve its own
note later; it is named here so it cannot drift into "healing".

### 11.2 §10.2 — Prayer of Healing does two jobs, and the abstraction is HALF of it

**Verified 2024 text** (aidedd 5.5e / D&D Beyond / Roll20, 2026-08-20): up to five
creatures within 30 ft that remain there for the whole 10-minute casting "gain the
benefits of a Short Rest and also regain 2d8 Hit Points"; +1d8 per slot level above
2nd; a creature cannot be affected again until it finishes a Long Rest.

So PoH genuinely IS two effects, and `war_angel.py:1263` models exactly one of them
(the short-rest-equivalent recharge). **Adding the 2d8 + spellcasting-modifier HP
therefore does NOT double-count** — it supplies the half that is missing. The
double-count risk §10.2 flagged would only materialise if the RAW effect were added
*alongside* a second `restore_sr()`; it is not.

**RULES CORRECTION to §7(b)'s framing.** The handoff assumed "RAW PoH grants no Hit
Dice, so character HD attach to the REAL short rest only." That is wrong: PoH grants
*the benefits of a Short Rest*, and spending Hit Dice is one of those benefits. War
Angel's PoH window is a genuine second Hit Dice window.

**It is numerically inert, so nothing changes.** Under §7's spend-ALL rule the pool is
drained at whichever window comes first and Hit Dice restore only on a Long Rest
(verified below), so one window and two windows give the same day total. The
correction is recorded because it is a real rules fact, not because it moves a number.

**Also verified: 2024 Long Rest restores ALL spent Hit Point Dice** ("you regain all
lost Hit Points and all spent Hit Point Dice") — the 2014 half-your-total rule is
gone. §7(d)'s flagged assumption is CORRECT as stated, and `restore_lr()` is right.

### 11.3 §10.5 — which summons have Hit Dice (load-bearing data)

**Beast of the Land, 2024 statblock (verified, Roll20 compendium 2026-08-20):**
AC 13 + your WIS modifier; **HP = 5 + (5 x ranger level)**; **Hit Dice = a number of
d8s equal to your ranger level**. Its CON modifier is +2 (consistent with
`BEAST_BASE_SAVES["con_save"] = 2`, which is the base before the master's PB).

So the companion DOES have Hit Dice in the PC sense — the question §10.5 correctly
refused to assume. Per modelled Silvertail level:

| char level | ranger level | beast `max_hp` | Hit Dice | mean-field pool (`N x (4.5 + 2)`) |
|---|---|---|---|---|
| 4 | 3 | 20 | 3d8 | 19.5 |
| 8 | 4 | 25 | 4d8 | 26.0 |
| 10 | 4 | 25 | 4d8 | 26.0 |

That is roughly ONE full heal's worth spread across a four-combat day — enough to
matter and small enough to run out, which is exactly the depletion curve §7(b2) wants.

**Summon CATEGORY, assigned from verified 2024 text (not archetype reputation).**
Re-verified 2026-08-20: if the beast has died within the last hour the master may take
a Magic action, touch it, and expend a spell slot; it returns to life **after 1 minute**
at full HP. One minute is about 10 rounds, so revival can never land inside a 4-round
combat. The companion therefore **cannot be healed back into a fight it dropped in**:

- `mortal_beast=True` → **`vanishes`** (dies at 0; unhealable back within combat;
  between-combats revival is the existing `recast` hook).
- `mortal_beast=False` (the DEFAULT) → **`threshold`**, unchanged.

**This confirms the §6 RULES-VERIFICATION FLAG in the direction it feared.** The 2024
Beast Master is NOT a "downed and healable" companion. `downed` is still required by
the taxonomy — the reanimator artificer's companion (guide 36) is the corpus case —
but **no currently-modelled build uses it**, so it will be built and exercised by
tests rather than by a build. That is worth stating plainly rather than discovering
later.

### 11.4 §10.6 — baseline movement, MEASURED (session 45)

The subsystem was built and then diffed against `main` across **36 scenarios**: War
Angel DPR + standard error at every level 1–16 (40 days, seed 11); Silvertail's full
`level × mortal_beast × recast` matrix, both the character column and the summon
column (25 days each); and Starfire Scion at every modelled level. **One scenario
moved, and it is the predicted one.**

Re-run at 200 days per scenario to see it clearly (mean damage per day,
character / beast):

| scenario | main | branch | moved |
|---|---|---|---|
| L8 `mortal=0` (either recast) | 93.40 / 141.28 | 93.40 / 141.28 | — |
| L10 `mortal=0` (either recast) | 101.83 / 150.51 | 101.83 / 150.51 | — |
| L8 `mortal=1 recast=0` | 93.19 / 17.76 | 93.17 / **17.84** | ✓ |
| L8 `mortal=1 recast=1` | 95.31 / 68.89 | 95.19 / **69.11** | ✓ |
| L10 `mortal=1 recast=0` | 103.21 / 14.71 | 103.37 / **14.84** | ✓ |
| L10 `mortal=1 recast=1` | 101.75 / 60.59 | 102.02 / **60.74** | ✓ |

**Movement is confined to `mortal_beast=True` — a non-default toggle — exactly as
§7(c) predicted, and every other scenario is bit-identical.** The War Angel is
bit-identical at all sixteen levels despite now casting PoH's RAW heal and spending
its Hit Dice, because both are mean-field and a character's `hp` is behaviourally
inert. The Starfire Scion is bit-identical because it answers **0** to
`available_for_healing` — its dice belong to Fueled Spellfire. The default Silvertail
path is bit-identical because a `threshold` summon's `hp` is a balance nothing reads.
The §12 parity proof stayed green throughout.

**The mechanism, traced.** Seed 15 at L10 with `mortal=1 recast=1` shows it end to
end. The beast dies in combat 1 and `recast` revives it at full HP; combat 2 leaves
it alive at 2 HP. On `main` it enters combat 3 at 2 HP and drops to the first hit,
after which the enemy retargets the master, which eats 86 damage and deals 16. On the
branch it spends Hit Dice at that boundary (deficit 23, pool 26.0) and enters combat 3
at full, absorbs 34, and the master takes 37 and deals 37. **That is the whole point
of the subsystem in one seed: healing bought the companion live rounds, the companion
kept the enemy off the master, and the master's own output went up as a
consequence** — a knock-on that no ledger could have reported and only a behavioural
change can produce.

**A caveat on how often it fires.** This is RARE. The rule needs the beast to end a
combat *alive and damaged*, and Silvertail's usually dies inside one — over seeds 0–14
it never happened at all. The day-level effect is therefore small (beast damage per
day +0.1 to +0.2) and shows up as a measurement rather than a per-seed assertion. The
mechanism test with teeth (`tests/test_healing.py`) is consequently built on a
constructed scenario that reaches the boundary alive, plus a scheduler-level test that
a `downed` summon healed above 0 re-enters the turn order.

**What did NOT move, and why that is the interesting half.** The healing ledger is
pure observation; character-side `hp` is inert; Hit Dice draw no dice; and
out-of-combat healing is mean-field by the rule stated in `src/healing.py`. Adding a
whole subsystem — a new verb, a new event, a new telemetry channel, a category enum,
two Hit Dice rules, and a build that now actually casts a healing spell — moved
exactly one non-default toggle. That is the design working, not luck.
