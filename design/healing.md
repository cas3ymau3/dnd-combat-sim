# Healing — decision record and build plan

> **Status: SEMANTICS LOCKED (session 44; revised twice after user review, most
> recently 2026-08-20 on summon Hit Dice — §7(b2)).
> NOT YET BUILT.** This is the design note that precedes the build, per the standing
> rule that a broadly-reused primitive gets a corpus survey and a design note up front
> rather than the usual forcing-function minimum. The build is the next work item; §7
> lists what must be settled inside it.

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

| class | at ≤ 0 HP | `max_hp` cap on healing | healable |
|---|---|---|---|
| character, party ally | keeps acting; balance goes negative | **no cap** (§2) | yes |
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

**(b2) SUMMONS DO NOT SPEND HIT DICE (v1). DECIDED — user, s44 cont. 2026-08-20.**
Because summons are capped (§4), the character's spend-all rule does not transfer:
their HD healing would be bounded by damage already taken, unusable against damage
taken later, and worthless once the summon is destroyed. All three are TIMING
questions, and **the user's decision is that summon damage/healing timing is not worth
modelling** — the complexity it would add buys too little.

So the v1 rule is the simplest one that adds nothing: **a summon never expends Hit
Dice.** It can still be healed by anything else (§4) — this is only about the automatic
rest-time rule.

**Why this candidate over the other.** The alternative the user raised was "a summon
expends HD to heal to `max_hp` after EVERY combat, short rest or not" — a deliberate
RAW break, bounded by its HD pool. It is not harder to build (the `between_combats`
hook already exists), but it has two costs this one does not:

1. **It would flatten the summon-survival axis.** `mortal_beast` and the `recast` hook
   exist precisely to measure "does the companion die, and what does reviving cost"
   (substrate #7, sessions 18–24). Topping up after every fight makes death rarer and
   pushes `mortal_beast=True` toward the immortal case — degrading an axis the project
   deliberately built. How much depends entirely on pool size versus incoming damage.
2. **It moves a validated baseline; this one does not.** Summons receive no healing at
   all today, so "summons do not spend HD" is *no change to summon behaviour* and
   Silvertail's `mortal_beast` numbers stay exactly where they are.

**What it costs.** It under-credits a build whose companion genuinely has Hit Dice, in
the conservative direction — declining to invent survivability rather than inventing
it. **Whether that matters is an empirical question we cannot answer yet**, because it
is not established that the corpus's companions have Hit Dice in the PC sense at all
(§10.5). So the upgrade is PRE-AGREED rather than reopened: **if the corpus survey
finds HD-bearing companions where it matters, adopt the heal-to-max-after-each-combat
rule as specified above.** It is a switch, not a redesign.

**(c) Character-side HD healing moves NO baseline.** `hp` is behaviourally inert for
characters and allies (§3), and under (b2) summons are untouched. Combined with (a)'s
mean-field rule, **the Hit Dice piece should be byte-identical across every existing
build** — which makes the §12 parity proof a precise check on it rather than an
approximate one. If any baseline moves, something is wrong.

**(d) Hit Dice are build data we mostly do not have.** Only Starfire Scion has a
`hit_dice` pool. War Angel, Silvertail and the beast all need HD count, die size and
CON modifier added to their level tables. **Stated assumption (user, s44): a long rest
restores ALL expended Hit Dice**, which is what `restore_lr()` already does — flagged
for RAW verification (2024 may specify half your total), but harmless either way for
independent days.

## 8. Metrics — deliberately small (3 scalars + 1 breakdown)

Applying PROGRESS.md's parsimony rule. Note that under §2 there is no delivered /
effective split for characters, which keeps this smaller than an earlier draft.

- **`net_damage_taken_per_round`** — `(damage taken − healing received) / rounds`. The
  defensive headline. **May be negative** (surplus healing capacity); the definition
  must say so.
- **`external_healing_required_per_day`** — `max(0, damage_taken − self_healing)`.
  Literally the quantity a party healer would have to supply. The sharpest expression
  of §2's dynamic.
- **`healing_provided_to_others_per_day`** — output that saves the party's budget; zero
  for a selfish build, large for a healer.
- **breakdown: `healing_by_source`** — self / summon / ally, in one keyed vector rather
  than N flat rows.

**Dropped as algebraically derivable:** `self_sufficiency` =
`1 − external_required / damage_taken`; `net_hp_end_of_day` =
`max_hp − rounds_per_day × net_damage_taken_per_round`.

**These metrics WAIT on the output-kinds design.** `healing_by_source` is a keyed
breakdown, and the registry has no such shape yet — see `evaluation_framework.md` §14.
Do not add flat rows to a registry already flagged as bloated.

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
5. **Do the corpus's summons actually HAVE Hit Dice?** The §7(b2) decision — summons
   never expend HD in v1 — is deliberately conservative, and its cost is under-crediting
   a companion that really does have dice to spend. That cost is only real if such
   companions exist in the corpus, which is **not established**: it should not be
   assumed from the character rule that a summoned creature has Hit Dice in the PC sense,
   or can take a short rest at all. Settle this in the survey. If HD-bearing companions
   turn out to matter, the pre-agreed upgrade in §7(b2) is a switch, not a redesign.

6. **Verify no DPR baseline moves — and under these decisions, expect NONE.** Piece 2
   is pure observation. Piece 1 mutates `hp`, which is behaviourally inert for
   characters and allies (§3). Piece 4 is mean-field (no dice) and leaves summons alone
   (§7 a, b2). So nothing here should shift a single die: the §12 parity proof is a
   PRECISE check, not an approximate one, and any movement means something is wrong.
   The one place a baseline can legitimately move is a build that starts actually
   CASTING a healing spell in combat, since that spends an action or a slot that would
   otherwise have produced damage — a real change, not drift.
