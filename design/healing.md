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
