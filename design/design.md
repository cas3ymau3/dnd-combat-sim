# D&D 5.5e Combat Simulator — Design Document

> Status: design spec, pre-implementation. This document is the contract the
> engine is built to serve. Code should conform to this; where code and this
> document disagree, one of them is wrong and it should be reconciled
> deliberately, not silently.

> Scope note: this is a Monte Carlo simulator for **quantitatively evaluating
> character builds**, primarily via average damage per round (DPR) across a
> simulated adventuring day, run many times. It is not a full D&D rules engine
> and not a play aid. Fidelity is traded for tractability wherever the notes
> below say so.

---

## 0. How to read this document

The design was derived in three passes:

1. The original model-setup notes (entity/actor model, adventuring-day
   structure, simplified spatial model, outputs).
2. A **verb-first** reframing: rather than designing the ability schema around
   example abilities (which causes path dependence), we enumerate the
   primitive state-mutations the engine supports ("verbs"). An ability is then
   *data* describing which verbs fire, under what conditions, at what cost. A
   new ability should require writing data, never engine code; if it forces an
   engine change, that is either a genuinely new primitive (rare, add
   deliberately) or a leak in the abstraction (fix it).
3. Two rounds of **coverage testing** against 29 real, deliberately diverse,
   deliberately messy build guides. The verb set survived both rounds; only a
   small number of true additions were forced. That convergence is the evidence
   the verb set is closed over the intended design space.

Sections 1–3 are the state model and simulation structure (mostly from the
original notes). Section 4 is the verb list (the engine contract). Section 5 is
the ability/content schema (verbs as data). Section 6 records decisions and open
questions. Section 7 is suggested implementation architecture.

---

## 1. Core entity model

The interacting elements of the model are **entities**, of two types:

- **Objects** — inanimate. No HP, no game statistics, no action-economy
  resources. They *do* have a **physical presence**: a spatial **footprint** and
  spatial relationships with other entities. Used mainly to represent
  spell/ability effects with an area (e.g. an emanation, a hazardous zone, a
  conjured wall). Objects may be created and destroyed mid-combat.
- **Actors** — have HP, game statistics, physical presence, AND
  **action-economy resources**. Actors can take actions in combat.

### Actor subtypes

1. **Character** — the build under evaluation. A state dictionary: HP, temp HP,
   AC, equipped gear, current levels of expendable resources, active
   status/condition flags (e.g. concentration), etc.
2. **Enemy** — a single generic combatant with effectively infinite HP (the
   "target dummy"). Stats scale with CR / character level via a parameter
   table. See §3.5 and the scope flag in §6.
3. **Controlled allies** — mounts, summons, companions. Directed by the
   character; have their own stat blocks and action economy.
4. **Party members** — an amalgamated single entity representing the rest of the
   party (assume 3 members). Modeled as one entity for *acting* purposes, but
   holds **3 separate HP pools** so it can be a realistic *target* for enemy
   attacks and a recipient of the character's support effects. Party members do
   nothing by default; the framework allows them generic actions so support
   builds (healing, buffs, advantage generation) can be evaluated.

Character, enemy, and party members are **omnipresent** (exist for the whole
simulated day). Objects and controlled allies wink in/out (e.g. a summon appears
when cast, vanishes when concentration drops).

### Action-economy resources (per the 2024 core rules)

`action`, `bonus_action`, `reaction`, `movement`. All actors have at least one;
objects have none. **Action-economy resources are modeled as ordinary resources**
(see §4) with one use that recharges each turn/round — this avoids special-casing.

---

## 2. Simulation structure: the adventuring day

One model run = one **standard adventuring day**, repeated N times for Monte
Carlo averaging. Seed the RNG and log the seed per run for reproducibility.

- Day = 16 hours = **960 minutes** (assumes 8h long rest outside the window).
- t=1 begins post-long-rest: recover all HP and LR-resources, reset temp HP,
  decrement exhaustion, etc.
- **Four combats per day**, each starting at a random minute in its quarter:
  combat 1 ∈ [1,239], combat 2 ∈ [240,479], combat 3 ∈ [480,719],
  combat 4 ∈ [720,960]. Start times redrawn each simulated day. Consequence:
  long-duration effects (10m, 1h) can occasionally span two combats; never more
  than 2 combats within any 240-minute span.
- Each combat lasts **1 minute = 4 rounds** (16 combat rounds/day).
- **One short rest/day** (60 min). The three inter-combat intervals define
  candidate windows. Rule: if interval 2 (between combats 2 and 3) is ≥ 60 min,
  the SR happens there; otherwise pick interval 1 or 3 with equal probability
  (given combat timing, if interval 2 < 60 then both 1 and 3 are > 60). SR
  begins at the first minute of the chosen interval.
- **Out-of-combat actions**: resource use outside combat (e.g. precasting mage
  armor, magic weapon, longstrider). Timing/manner specified by the
  **daily plan** (§3.4).
- The long rest is an implicit event from the timing structure, not an explicit
  modeled event.

### Combat progression

- Roll initiative separately for character, party members (as one entity), and
  enemy. Controlled allies and objects act on their controller's turn.
- A turn ends when the actor has used (or explicitly skipped) all available
  action-economy resources. A round ends when the last actor in initiative
  finishes. Combat ends when the last actor finishes round 4.

---

## 3. Subsystems

### 3.1 Spatial model — ZONES (decision: see §6)

Not an explicitly spatial grid. **Zonal abstraction**: each entity occupies one
of a small number of abstract zones (e.g. "melee blob", "ranged", and named
zones attached to emanation/area objects). Movement = changing zones.

Rationale: a large fraction of the build corpus depends on *differential*
positioning — staying inside your own aura/hazard zone while the enemy is
outside it, kiting at range, trapping an enemy in a hazardous zone. The earlier
"transitive clump" model (everyone-near-everyone collapses to one bit) cannot
express this and was rejected.

Zone mechanics to support:
- Area objects (Spirit Guardians, fog cloud, darkness, sleet storm, spike
  growth, hunger of hadar, web, entangle, eldritch cannon area, etc.) are
  objects-with-footprint that define a zone; effects fire on entities entering /
  starting their turn in / remaining in that zone.
- Footprint vs. mover speed gates zone exit (an enemy needs enough speed to
  leave a large emanation; difficult terrain can double the effective cost).
- Forced movement (push/pull, prone, telekinetic shove, repelling effects) moves
  a *target* between zones ignoring its own speed — clean in the zone model.
- Objects are tagged `anchored_to: <entity>` (emanation follows its creator) vs.
  `static` (placed zone stays put).
- Mounts: a mount and rider share a zone; a mounted character moves at the
  mount's speed.

### 3.2 Statuses & conditions

- Tracked as boolean flags; a status typically *carries* a bundle of modifiers
  (e.g. `poisoned` ⇒ disadvantage on attack rolls & ability checks).
- Drawn from 2024 core rules (grappled, restrained, incapacitated, stunned,
  prone, frightened, blinded, invisible, etc.) plus ability-specific statuses
  (e.g. `hexblades_curse`).
- **Concentration is a first-class status**, globally constrained to one
  concentration effect at a time. The daily-plan logic must never hold two. The
  enemy-damage → concentration-save loop must be modeled.
- **Conditions the *character* imposes on the *enemy* are central, not
  peripheral** (stun, prone, restrain, frighten, slow, blind, disadvantage-on-
  saves). They are the win condition for a large share of builds. This implies
  the enemy needs real saving-throw math and condition tracking (see §3.5, §6).

### 3.3 Character: stats, resources, abilities, progression

- **Build plan**: a table specifying the character at each level 1–20 — stats,
  HP, gear/AC, proficiency bonus, ability scores, saves, attack/spell bonuses,
  flat damage bonuses, and (the main driver) the abilities & resources gained.
- **Resources**: anything limited and consumable (spell slots, sorcery points,
  psionic dice, channel divinity, focus points, second wind, charges, per-day
  uses). Each defined by (i) number of uses and (ii) recharge rule (LR, SR,
  partial-on-SR, per-turn, etc.). Action-economy resources are a special case
  (§1). Tracked across the whole day.
- **Abilities** are *active* (cost an action-economy resource and/or a resource;
  e.g. spells, rage, action surge) or *passive* (modify the stat block or an
  existing ability; e.g. sneak attack, fast movement, the Tough feat). Both can
  have durations (minutes / conditional / permanent) and resource costs. Baseline
  active abilities every character has: attack, dodge, disengage, unarmed strike
  (damage / shove / grapple). Abilities live in an ever-expanding declarative
  dictionary (§5) — "like skills" — referenced by build/daily plans.

### 3.4 Character: daily plan (combat policy)

- Conditional logic dictating how the character behaves each round of each combat
  and how/when resources are used (in and out of combat). One plan per level
  1–20 (may repeat across levels). This is the **policy** layer and must be kept
  strictly separate from mechanical **resolution** (§7).

### 3.5 Enemy behavior & stats

- Action economy: `action` + `movement` only. By default acts, doesn't move.
- Two generic actions: **enemy attack** (represents any attack-roll damage,
  scaled to a CR-appropriate number of attacks) and **enemy spell** (represents
  any save-based damage; save type drawn from a CR-varying distribution; half
  damage on success). Fixed probability of choosing attack vs. spell, weighted
  toward attacks per core-book prevalence. Both assumed infinite range.
- **Targeting**: random by default among character + party HP pools (no AoE
  modeled). Target traits adjust probability statically and dynamically
  (`melee` tag raises it, `invisible` lowers it, grappling-the-enemy raises it).
  When using attack rolls, the enemy prefers targets it has advantage against,
  then even, avoids disadvantage.
- **Reactions**: only an opportunity attack, only if the character provokes one
  (modeled via a `provoked_enemy_OoA` flag set by character actions/movement).
  Modeled as a single-attack instance of enemy-attack. No general enemy reaction
  resource.
- Enemy responses: stands up if prone (half move); may try to break a grapple
  (fixed probability) instead of attacking; removes action-removable conditions
  immediately; tries to leave a damaging zone at start of turn (dash if needed).
- Static stats scale with CR via a parameter table (AC, save/check bonuses,
  spell save DC, attack bonus, damage per action, #attacks, save-type
  distribution). Dynamic stats: targeting probability, status flags, size,
  speed. Size/speed drawn from the 2024 Monster Manual distribution.
- Enemy-imposed conditions on the character are **not** modeled by default; but
  the engine needs enough enemy save math to resolve character-imposed
  conditions (see §6 scope flag).

### 3.6 Party members: stats & behavior

- One entity, 3 infinite HP pools. Statuses (advantage, AC boosts) apply to all
  sub-pools at once; healing/THP applied per-pool.
- Saving-throw bonus, attack/spell bonus, AC, etc. scale with CR/level via a
  parameter table (note: the original "save bonus = character's PB" was flagged
  as too low; track the CR table instead — see §6).
- Do nothing by default; can take generic actions to model support evaluation;
  move to avoid damaging zones.

---

## 4. The verb list (engine contract)

Every ability bottoms out in a composition of these primitives. Each verb is
named by the state it mutates. This is the closed set the engine implements;
content (§5) may only compose these.

### Core verbs

1. **roll** — evaluate a dice expression under an advantage state
   (normal/adv/disadv). Foundational.
2. **attack_roll** — d20 + bonus vs. AC → miss / hit / crit.
3. **save** — d20 + bonus vs. DC → pass/fail (often "half on save" for damage).
4. **damage** — apply a typed damage delta to an HP pool, respecting
   resistance/immunity/vulnerability. Carries damage *type* and *source*. May
   target self or an ally (self-damage as cost — see below).
5. **heal** — apply a positive delta to an HP pool.
6. **temp_hp** — set/refresh a temp-HP pool (max, not additive).
7. **apply_modifier / remove_modifier** — push/pop an entry on the modifier
   stack (see modifier-hook vocabulary).
8. **apply_status / remove_status** — set/clear a flag (usually bundles
   modifiers).
9. **spend_resource / restore_resource** — decrement/credit a resource pool,
   including action-economy resources.
10. **grant_action** — add an action-economy resource mid-turn (action surge,
    haste, war-priest BA attack, soul-knife BA blade).
11. **move_entity** — change spatial (zone) state. Self-directed or forced.
12. **create_entity / destroy_entity** — bring an object or controlled ally
    into/out of existence.
13. **transform_statblock** — temporarily swap the acting entity's stat block
    for another's, with rules for what carries over (Wild Shape, polymorph,
    alter self granting INT-based unarmed strikes).
14. **convert_resource** — move resources between pools / emulate a rest or
    partial refresh (font of magic slots↔points, prayer of healing as
    short-rest, uncanny metabolism, magical cunning, psionic restoration). Hooks
    into the short-rest event logic. Near-universal in the corpus.
15. **intercept_event** — a reaction that reaches into an *in-flight* incoming
    attack/damage event and alters it: change AC after seeing the roll (shield,
    defensive duelist), impose disadvantage on an attack against self/ally
    (blade ward, protection style), halve/negate damage (uncanny dodge, spirit
    shield), or force a miss (illusory self). Distinct from a normal reaction
    because it modifies an event already being resolved.

### Cost can invoke effect verbs

A cost is not always a resource decrement. Sometimes the cost *is* an effect
verb aimed at self or an ally — e.g. crimson rite / blood maledict cost HP
(`damage` on self), and deliberately destroying one's own summon to trigger a
death-burst (`destroy_entity` on an ally). The cost layer must be able to invoke
effect verbs, not only `spend_resource`.

### Modifier-hook vocabulary (modifiers carry logic, not just numbers)

The corpus made this non-negotiable: flat-integer modifiers are insufficient.
Supported hook kinds:

- **flat** — +2 dueling, +CHA aura, +PB GWM.
- **bonus_die** — bless (+1d4), bardic/combat inspiration (d6→d12), guidance.
- **dice_injection** — conditional extra dice loaded onto a specific roll
  (divine smite, sneak attack, crimson rite, searing spellfire).
- **reroll / take_better** — savage attacker (roll twice keep either), Great
  Weapon Fighting style.
- **die_value_replacement** — sharpened mind (replace rolled number with a PED
  roll), psionic surge (treat 1/2/3 as 4). Operates on individual die results.
- **crit_behavior** — crit-range expansion (improved critical 19–20), and the
  crit-doubles-dice interaction with dice_injection.
- **advantage_state** — the most pervasive: anything that changes *how* the d20
  is rolled (bless-adjacent sources, vex, innate sorcery, steady aim, prone,
  invisibility, blinded). Touches no number.
- **ability_score_substitution** — override which ability score feeds a roll
  (battle smith / EK true-strike / shillelagh / organic weapons using INT or
  WIS for attack & damage). Upgraded to first-class; appears in ~half the corpus.

### Trigger-predicate vocabulary (the condition layer must be this expressive)

Triggers must express at least:
- on your action / bonus action / reaction
- as a rider when you hit with a weapon / on a specific attack
- when the enemy fails a save / when you deal damage of type X
- "first time this turn" / once-per-turn gating
- target below max HP / HP-threshold conditions
- start/end of an affected creature's turn; entity entering/remaining in a zone
- external reactive triggers (being hit, taking damage, a creature leaving reach)

---

## 5. Ability / content schema (verbs as data)

An ability is declarative data with three **strictly separated** layers. Keeping
them separate is what prevents path dependence (an emanation spell and a passive
on-hit rider can have identical *effect* layers and differ only in trigger/cost).

1. **Trigger / condition** — *when* it fires (event-match against the scheduler,
   using the predicate vocabulary above).
2. **Effect** — *what* happens: an ordered list of verbs (§4) with parameters. A
   small composable DSL, not prose.
3. **Cost / requirement** — *what it consumes / requires*: action-economy,
   resources, concentration, prerequisites. May invoke effect verbs (self-cost).

Statuses, magic items, and (most) class/species/feat features are all the same
kind of declarative object, distinguished by tags and slot-economy rather than
by bespoke code:

- **Statuses** — a flag plus a bundle of modifiers and possibly recurring
  triggers.
- **Magic items / infusions** — a bundle of passive modifiers and/or created
  entities, with attunement/slot rules. Same shape as an ability, different tag.
  (Artificer replicate-magic-item, enspelled weapons, +1 gear, mithral armor,
  homunculus/eldritch cannon.)

### Schema validation procedure (use, don't skip)

Examples are **coverage tests**, not design drivers. To validate the schema,
take a deliberately diverse basket spanning the verb and trigger space and
confirm each is expressible as data:
- pure passive stat-mod (Tough) — modifier-only, no trigger, no cost
- conditional on-hit rider (sneak attack) — conditional rider trigger
- persistent save-based zone (Spirit Guardians / fog cloud) — duration, zone,
  recurring trigger
- action granter (action surge) — grant_action
- ally buff (bless) — modifiers on other entities + concentration
- resource-flexible spell (upcast) — parameterized cost/scaling
- reactive interceptor (shield / uncanny dodge) — intercept_event
- stat-block swap (Wild Shape) — transform_statblock
- rest-emulation (prayer of healing) — convert_resource

If a new ability forces engine code, it is a new primitive (add deliberately) or
an abstraction leak (fix). Use the messiest real build (e.g. the psionic
crit-fisher with its savage-attacker + sharpened-mind + psionic-surge +
sneak-attack + improved-critical stack) as the first hard coverage test.

---

## 6. Decisions & open questions

### Decided
- **Spatial model: zonal**, not transitive-clump. Strongly validated by the
  corpus (control/zone builds are a large fraction of it).
- **Modifiers carry functions/hooks**, not just flat values. Forced by the
  roll-transforming builds.
- **Verb set is closed** over the design space, on the evidence of two coverage
  rounds against 29 diverse builds producing only `intercept_event` and a richer
  predicate/hook vocabulary as additions.
- **Implementation language: Python** (Monte Carlo + numpy/pandas/pytest
  ecosystem; clean fit for a GitHub repo and markdown-driven content).

### Open / flagged
- **Enemy scope.** The original "infinite-HP target dummy with no save math" is
  too thin: (a) character-imposed conditions need real enemy saving throws and
  condition tracking + concentration; (b) infinite HP disables execute/bloodied
  effects and the "fights end early when DPR is high" resource dynamic. Decide
  whether to add an optional finite-HP enemy mode and how much enemy save
  fidelity to build. Recommendation: build the save math (needed anyway for
  control builds); keep infinite HP as default with finite-HP as an option.
- **Party-member stats.** Track a CR/level parameter table rather than the
  original "save bonus = character PB" (flagged too low), if support builds and
  party survivability outputs are to be meaningful.
- **Enemy attack-vs-spell balance.** The "equal damage potential" assumption
  interacts heavily with AC-boosting vs. save-boosting builds; worth a
  sensitivity check against source data so the tool doesn't systematically favor
  one defensive strategy.
- **Magic-item / attunement economy.** Decide the acquisition/attunement rules
  and how items slot into the build plan.
- **Movement open questions from the original notes** (moveable objects, forced
  movement details, mounts) are largely resolved by the zone model but need
  concrete rules when the spatial layer is built.

---

## 7. Suggested implementation architecture

Layered, with policy strictly separated from resolution:

- **Core engine**: entities; the modifier stack (compute effective stats by
  folding active modifiers over base stats on demand); a discrete-event
  scheduler (initiative order, durations, "until next attack" triggers, readied
  actions, zone enter/exit); resource & action-economy resolution; seeded RNG
  with per-run seed logging.
- **Content layer**: abilities, statuses, magic items, enemy/party CR tables —
  loaded from declarative data (YAML/JSON or structured markdown), never
  hardcoded into the engine. This is the "verbs as data" layer (§5).
- **Character layer**: build plan → leveled stat blocks; daily plan → combat
  policy. Policy decides *what to do*; the engine resolves *what happens*. Never
  mix the two.
- **Simulation runner**: schedules the day, runs N iterations, aggregates
  outputs.

Engineering practices to hold to: data-driven design (engine is a generic
interpreter of content data); the effect/modifier pattern (abilities emit
modifiers onto a stack, never mutate stats directly — this also makes
"share of turns under status X" outputs fall out for free); discrete-event
simulation for all timing/duration bookkeeping; determinism via seeding;
separation of decision (policy) from resolution.

### Repo / workflow shape
- The existing build-guides folder becomes a **git repo** worked in via Claude
  Code; eventually pushes to GitHub.
- `design/` (or `docs/`) holds this document and later the formal ability schema
  — version-controlled alongside code, and in the same markdown form as the
  Obsidian build guides, preserving the "model + guides share one source of
  truth" goal.

---

## 8. Outputs to track

Primary: character **damage per combat round (DPR)**. Also: damage taken;
damage reduced; HP recovered; attack-roll counts (hits, crits, hit %, crit %,
attacks at advantage and %); saving throws forced by type, enemy failures by
type and %, ; limited resources used per day and per combat; share of turns
concentrating and concentration-breaks; share of turns the character / party /
summons / enemy are under specified statuses; average damage per use / on-hit /
on-crit of each damaging ability; HP/damage taken by party and created allies;
and (if specified) success rate of party/ally attacks and spells.
