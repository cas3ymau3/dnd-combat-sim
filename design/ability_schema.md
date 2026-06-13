# D&D 5.5e Combat Simulator — Ability Schema

> Status: locked design contract. This document defines the declarative data format
> for all abilities, statuses, and magic items in the content layer. The engine is a
> generic interpreter of this schema; new content should require writing data, not
> engine code. If adding a new ability forces an engine change, either a genuinely
> new primitive is needed (add deliberately) or there is an abstraction leak (fix it).

> Derived from: `design/design.md` §4–§5, plus two rounds of schema coverage testing
> against all 33 build guides in `design/build-guides/`. The verb set and predicate
> vocabulary below are closed over that design space.

---

## 1. Three-Layer Structure

Every ability — spell, class feature, feat, passive, status, magic item — is expressed
as the same three strictly-separated layers:

```
trigger   — WHEN it fires
effect    — WHAT happens (ordered list of verbs)
cost      — WHAT it consumes or requires
```

Keeping layers separate prevents path dependence: two abilities with identical effects
but different triggers (e.g. a concentration aura vs. an on-hit rider) differ only in
their trigger block and share the same effect block unchanged.

---

## 2. Top-Level Fields

```yaml
name: string                  # snake_case identifier, unique across content
tags: [list]                  # see tag vocabulary below
trigger: <trigger block>      # null for permanent passives
effect: [list of verb blocks]
cost: <cost block>            # null if free
duration: <duration block>    # null for instantaneous effects
```

### Tag vocabulary

| Tag | Meaning |
|---|---|
| `passive` | No activation; fires automatically when trigger fires |
| `active` | Requires deliberate activation (action economy cost) |
| `reaction` | Fires as a reaction to an event |
| `concentration` | Maintaining this ends all other concentration effects |
| `spell` | Subject to counterspell, dispel magic, anti-magic fields, and rage restriction |
| `magic_action` | Requires a magic action; **not** a spell (e.g. elemental node — usable while raging) |
| `cantrip` | Spell with no slot cost; scales with character level milestones |
| `aura` | Persistent modifier broadcast to all entities within a radius |
| `summon` | Creates a controlled-ally entity |

---

## 3. Trigger Layer

The trigger block expresses WHEN an ability fires using a nested `all` / `any` predicate
tree. All conditions in an `all` block must be true; at least one in an `any` block.
Predicates may be nested arbitrarily.

```yaml
trigger:
  all:
    - <predicate>
    - <predicate>
    - any:
        - <predicate>
        - <predicate>
```

A `null` trigger means the effect is permanent (e.g. Tough, Draconic Resilience).

### 3.1 Event predicates

These match named points in the simulation's discrete-event schedule:

| Predicate | Fires when… |
|---|---|
| `event: on_use` | The ability is deliberately activated |
| `event: on_hit` | An attack roll by the ability's owner results in a hit |
| `event: on_miss` | An attack roll by the ability's owner results in a miss (mirror of `on_hit`; the post-roll rescue point — Guided Strike) |
| `event: on_damage_roll` | Damage dice are being rolled for an attack or spell |
| `event: on_roll` | Any single die or dice pool is being rolled (with `die_type` filter) |
| `event: turn_start` | The owner's turn begins |
| `event: turn_end` | The owner's turn ends |
| `event: round_start` | A new combat round begins |
| `event: entity_enters_zone` | An entity moves into a named zone |
| `event: entity_starts_turn_in_zone` | An entity begins its turn inside a named zone |
| `event: entity_leaves_zone` | An entity moves out of a named zone |
| `event: incoming_attack_roll` | An attack roll is being made against the owner |
| `event: incoming_damage` | The owner is about to take damage |
| `event: ally_takes_damage` | An ally within `range` takes damage |
| `event: creature_drops_to_zero` | Any creature the owner can see drops to 0 HP |
| `event: creature_casts_spell` | Any creature within `range` casts a leveled spell |
| `event: concentration_check` | The owner must make a concentration saving throw |
| `event: on_short_rest` | A short rest completes |
| `event: on_long_rest` | A long rest completes |

### 3.2 Condition predicates

These filter or gate the event:

| Predicate | Description |
|---|---|
| `once_per_turn: true` | This ability can fire at most once per turn |
| `once_per_round: true` | At most once per round (across all turns) |
| `weapon: finesse_or_ranged` | Attack weapon must be finesse or ranged |
| `weapon: melee` | Attack weapon must be melee |
| `weapon: ranged` | Attack weapon must be ranged |
| `source: weapon_attack` | Damage source is a weapon (not a spell or unarmed strike) |
| `source: spell` | Damage source is a spell |
| `damage_type: <type>` | Damage being dealt is of the specified type |
| `die_type: <die>` | The die being rolled is of the specified type (e.g. `psionic_energy_die`) |
| `attacker_has_advantage: true` | The owner has advantage on the triggering attack roll |
| `ally_adjacent_to_target: true` | An ally is within 5ft of the attack target |
| `requires_status: <status_name>` | The owner must have the named status active |
| `target_has_status: <status_name>` | The target must have the named status |
| `out_of_combat: true` | The ability can only be used outside of combat |
| `in_combat: true` | The ability can only be used in combat |
| `while_raging: true` | The owner must be raging |
| `range: <feet>` | An entity/event must be within this distance |
| `self_only: true` | The target of the effect must be the owner |
| `d20_test: self` | For Lucky-type predicates: the d20 test is made by the owner |
| `incoming_attack_roll: true` | For Lucky-type predicates: an enemy is making an attack roll against the owner |

### 3.3 Zone predicates (spatial)

| Predicate | Description |
|---|---|
| `zone: self` | The zone centered on or anchored to the ability's owner |
| `zone: <name>` | A named zone created by a specific ability (e.g. `spirit_guardians_zone`) |
| `allies_within_radius: <feet>` | All allied entities currently within this distance of the owner |
| `enemies_within_radius: <feet>` | All enemy entities currently within this distance |

---

## 4. Effect Layer

The effect block is an ordered list of verb invocations. The engine executes them
in sequence; earlier verbs can store values (`store_as`) that later verbs reference
(`value_ref`).

### 4.1 Verb list (engine contract — closed set)

These 15 primitives are the only state mutations the engine implements. Content may
only compose these. Adding a new ability should never require adding a verb; if it
does, record the decision explicitly.

| # | Verb | Mutates |
|---|---|---|
| 1 | `roll` | Evaluates a dice expression under an advantage state; result can be stored |
| 2 | `attack_roll` | d20 + bonus vs. AC → miss / hit / crit |
| 3 | `save` | d20 + bonus vs. DC → pass / fail |
| 4 | `damage` | Applies typed damage delta to an HP pool |
| 5 | `heal` | Applies positive HP delta to a pool |
| 6 | `temp_hp` | Sets or refreshes a temp-HP pool (max, not additive) |
| 7 | `apply_modifier` | Pushes an entry onto the modifier stack |
| 8 | `remove_modifier` | Pops an entry from the modifier stack |
| 9 | `apply_status` | Sets a status flag; may carry a stored numeric value |
| 10 | `remove_status` | Clears a status flag |
| 11 | `spend_resource` | Decrements a resource pool |
| 12 | `restore_resource` | Credits a resource pool |
| 13 | `grant_action` | Adds an action-economy resource mid-turn |
| 14 | `move_entity` | Changes an entity's zone (self-directed or forced) |
| 15 | `create_entity` | Brings an object or controlled ally into existence |
| 16 | `destroy_entity` | Removes an object or controlled ally |
| 17 | `transform_statblock` | Temporarily swaps the acting entity's stat block |
| 18 | `convert_resource` | Moves resources between pools / emulates a rest |
| 19 | `intercept_event` | Modifies an in-flight incoming event before resolution |

### 4.2 `choose_one` construct

When an ability offers mutually exclusive options at activation time, the effect block
uses a `choose_one` key instead of a list:

```yaml
effect:
  choose_one:
    - label: distract
      verbs:
        - verb: apply_modifier
          hook: advantage_state
          target: target_attacks_non_owner
          value: disadvantage
    - label: protect
      verbs:
        - verb: apply_modifier
          hook: flat
          stat: incoming_damage
          target: ally_hit_by_target
          value: half
    - label: strike
      verbs:
        - verb: damage
          dice: "1d6"
          type: cold
```

### 4.3 Damage resolution phase order

When multiple modifier hooks apply to the same damage roll, the engine applies them
in this fixed sequence. Within a phase, order is commutative (hooks compose without
interdependency at the same phase).

| Phase | What happens |
|---|---|
| 1 | Determine dice pool — crits double die *count* here (not the summed result) |
| 2 | Roll all dice in the pool |
| 3 | Per-die modifications: `reroll_take_better`, `die_value_replacement`, `minimum_floor` |
| 4 | Sum all dice |
| 5 | Add flat bonuses (`flat` modifiers, ability score modifiers, magic weapon bonuses) |

### 4.4 Modifier hook vocabulary

Modifier hooks are the named logic types an `apply_modifier` verb can carry.

| Hook | Description | Example |
|---|---|---|
| `flat` | Constant numeric bonus/penalty | Dueling (+2), GWM (+PB) |
| `bonus_die` | Roll an extra die and add to result | Bless (+1d4), Bardic Inspiration |
| `dice_injection` | Inject extra dice onto a specific pool | Sneak Attack, Divine Smite |
| `reroll_take_better` | Re-roll a dice pool; take either result | Savage Attacker |
| `die_value_replacement` | Replace individual die results | Sharpened Mind, Psionic Surge |
| `minimum_floor` | Each die result is at least N | Psionic Surge (floor at 4) |
| `crit_behavior` | Adjusts crit threshold or crit-doubling interaction | Improved Critical |
| `advantage_state` | Changes how the d20 is rolled | Bless-adjacent, Vex, Prone |
| `ability_score_substitution` | Override which stat feeds a roll | True Strike (INT attacks), Shillelagh |
| `action_cost_override` | Reduce/change the action economy cost of a specific ability | Mantle of Majesty, Haste |

#### `die_value_replacement` sub-modes

```yaml
hook: die_value_replacement
mode: substitute_die        # replace one die with a roll of a different die type
mode: substitute_stored_value  # replace one die with a previously stored value
mode: minimum_floor         # treat any result below N as N
```

### 4.5 Common verb parameter patterns

#### `roll`
```yaml
- verb: roll
  die: psionic_energy_die
  store_as: ped_result       # name under which result is stored for later verbs
```

#### `damage`
```yaml
- verb: damage
  dice:
    base: "2d8"
    increment: "1d8"         # added per scaling step
    every_n_levels: 1        # how many levels per increment (omit if per-level)
    level_reference: slot_level  # what level value to use for scaling
    base_level: 1            # level at which `base` applies, 0 increments (default 1; omit)
  type: radiant
  on_save: half              # "half" | "none" (default: "none")
  target: self               # "self" | "target" | "ally" | "all_in_zone" | "allies_within_radius"
```

The `dice` block has two scaling shapes (both fold to a concrete `(count, sides)`
at fire-time; only the die *count* changes, never the size):

- **uniform** (`increment` / `every_n_levels`) — +`increment` dice per
  `every_n_levels` of the `level_reference` value, measured *above* `base_level`:
  `count = base + max(0, level − base_level) // every_n_levels × increment`. The
  `base_level` is the level at which the base dice apply with zero increments;
  it **defaults to 1** (the natural floor of character / rogue / minimum-slot
  levels) and is omitted in the common case. e.g. Divine Smite / Burning-Hands
  upcast (base at slot 1, +1d8 per slot level — `base_level` omitted); Spirit
  Guardians (3d8 at slot **3**, so `base_level: 3`). The `increment` die size
  must equal the `base` die size (only the count scales).
- **cantrip** — the canonical 5.5e cantrip rule (1 die, +1 at character level
  5 / 11 / 17), which is NON-uniform from level 1 so it gets its own named mode:

  ```yaml
  dice:
    base: "1d8"
    scaling: cantrip         # +1 die at character level 5 / 11 / 17
    level_reference: character_level
  ```

  (Sacred Flame: 1d8 → 2d8 → 3d8 → 4d8.)

##### Scaling typology (the map behind the two shapes)

The two `dice` shapes above are not two *kinds of ability* — they are two
**step functions** over a shared structure. Every scaling rule in 5.5e factors
into three INDEPENDENT axes; naming them keeps future additions coherent and
tells us exactly what each new build will force:

1. **Driver** (`level_reference`) — the integer that drives the scaling:
   `slot_level`, `character_level`, a class level (`rogue_level`, …), or a
   spent-resource count (focus/ki/sorcery points). All arrive the same way: an
   int the **policy** supplies at fire-time via `context` (`_level_from_context`).
   This is where the *cost-driven vs level-driven* distinction lives: cost-driven
   drivers (upcast slot, points spent) are a policy ARBITRATION choice; level
   drivers are a fixed lookup. Either way the interpreter just reads an int — so
   "how much to spend" stays Python policy (§decisions, CLAUDE.md #2) and
   "value → dice" stays data. Adding a new driver needs NO engine change.
2. **Step function** — how the driver maps to a step count:
   - **linear** (`increment` / `every_n_levels` / `base_level`):
     `steps = max(0, driver − base_level) // every_n_levels`. (Divine Smite,
     Sneak Attack, upcast spells.)
   - **threshold list** (`scaling: cantrip`): `steps = #{breaks ≤ driver}` for a
     fixed list. Cantrips use `[5, 11, 17]`; Rage-style features would use a
     different list. The list is hardcoded (`_CANTRIP_THRESHOLDS`) today —
     **lift it to data (`scaling: thresholds`, `breaks: [...]`) when the first
     non-cantrip threshold scaler appears.**
3. **Scaled quantity** — what the steps grow. Only **dice count** is built.
   Other quantities are real in 5.5e but each is blocked on a DIFFERENT
   primitive, not on scaling design:
   - **target count** (upcast Command / Charm Person hitting more creatures) —
     blocked on the multi-enemy / spatial model (deferred; see PROGRESS). Rare in
     the current build corpus.
   - **#beams / #attacks** (Eldritch Blast), **duration** — add when a build
     forces them.

Current code (`_resolve_scaling_dice`) sits at the narrow, correct corner:
**dice count**, scaled by **linear OR threshold-list** step functions, over **any
driver**. The decomposition is the map; we expand a single axis only when a
selected build makes that axis load-bearing.

#### `apply_modifier`
```yaml
- verb: apply_modifier
  hook: <hook_name>
  phase: 3                   # damage resolution phase (1–5); omit for non-damage modifiers
  applies_to: weapon_damage_dice   # scope: which dice/pool this hook targets
  stat: ac                   # for flat modifiers: which stat
  value: 5                   # for flat modifiers: the numeric value
  die: "1d4"                 # for bonus_die modifiers
  target_ability: command    # for action_cost_override: which ability is affected
  new_cost: bonus_action     # for action_cost_override: the new action economy cost
```

#### `apply_status`
```yaml
- verb: apply_status
  status: sharpened_mind_active
  value_ref: ped_result      # optional: attach a stored numeric value to the status
```

#### `intercept_event`
```yaml
- verb: intercept_event
  modification: apply_modifier
  hook: flat
  stat: ac
  value: 5
  duration:
    type: until_condition
    condition: start_of_next_turn
```

#### `convert_resource`
```yaml
- verb: convert_resource
  source_resource: spell_on_target    # what is consumed (can be a spell effect on an entity)
  target_resource:
    type: spell_slot
    max_level: 2
  target_entity: touched_creature     # who receives the restored resource
```

#### `create_entity`
```yaml
- verb: create_entity
  entity_type: controlled_ally        # "controlled_ally" | "object"
  stat_block_reference: reanimated_companion
  anchor: owner                       # "owner" (follows) | "static" (placed at location)
  zone: owner_zone
```

---

## 5. Cost Layer

```yaml
cost:
  action_economy: action | bonus_action | reaction | magic_action | null
  concentration: true | false         # defaults false
  resource:
    type: <resource_name>             # e.g. spell_slot, bardic_inspiration, psionic_energy_die
    min_level: <int>                  # for spell slots: minimum slot level
    count: <int>                      # number of uses consumed (default 1)
  cast_time: <string>                 # for out-of-combat cast times: "10_minutes", "1_hour"
  requires:                           # prerequisites checked before firing
    all:
      - <predicate>
```

### Resource type vocabulary (representative)

| Resource type | Recharge |
|---|---|
| `spell_slot` | Long rest (by class rules) |
| `pact_magic_slot` | Short rest |
| `sorcery_points` | Long rest |
| `bardic_inspiration` | Long rest (short rest at level 5+) |
| `channel_divinity` | Short rest |
| `rage` | Long rest |
| `ki_points` / `focus_points` | Short rest |
| `psionic_energy_die` | Long rest |
| `second_wind` | Short rest |
| `action_surge` | Short rest |
| `wild_shape` | Short rest |
| `lay_on_hands_pool` | Long rest (pool of HP) |
| `luck_point` | Long rest |
| `action` | Per-turn |
| `bonus_action` | Per-turn |
| `reaction` | Per-round |

---

## 6. Duration Block

```yaml
duration:
  type: instantaneous | rounds | minutes | hours | until_condition | permanent
  value: <int>               # number of rounds/minutes/hours; omit for other types
  anchor: concentration      # if "concentration", ends when concentration breaks
  condition: <string>        # for until_condition: e.g. "start_of_next_turn", "end_of_target_turn"
```

---

## 7. Status Definitions

A status is a flag plus an optional carried value plus optional bundled abilities.
Statuses are defined in the same declarative format as abilities.

```yaml
name: sharpened_mind_active
type: status
value_type: integer          # the status carries a stored numeric value
bundled_abilities:
  - sharpened_mind_rider     # abilities that are active while this status is set
duration:
  type: minutes
  value: 1
```

Core 2024 conditions (`poisoned`, `prone`, `stunned`, `frightened`, `blinded`,
`invisible`, `grappled`, `restrained`, `incapacitated`, `paralyzed`, `concentration`)
are pre-defined in the engine and need not be declared in content files.

---

## 8. Magic Items & Infusions

Magic items use the same three-layer schema, distinguished by tags:

```yaml
name: repeating_shot
tags: [magic_item, infusion, attunement_not_required]
trigger: null
effect:
  - verb: apply_modifier
    hook: flat
    stat: attack_roll
    value: 1
  - verb: apply_modifier
    hook: flat
    stat: damage
    value: 1
cost: null
duration:
  type: permanent
```

Attunement is tracked via a separate `attunement: true` field. Infusions follow the
same format with an `infusion: true` tag and a `slot: artificer_infusion` cost entry.

---

## 9. Schema Validation Procedure

When adding a new ability, validate it against this checklist:

1. **All three layers are present and separated.** Trigger says *when*, effect says
   *what*, cost says *what it consumes*. Nothing bleeds between layers.
2. **Every verb in the effect block is in the closed verb list (§4.1).** If not,
   either justify a new primitive or find the correct existing verb.
3. **Every predicate in the trigger block is in the predicate vocabulary (§3).** If
   not, add it to the vocabulary (a predicate addition is cheap; a verb addition is not).
4. **Scaling uses the structured object form (§4.5), not formula strings.**
5. **Resources are referenced by type, not hard-coded names** (e.g. `type: spell_slot`,
   not `type: spell_slot_3`). The build plan resolves which specific slot to spend.
6. **Run the hard coverage test**: express the full psionic crit-fisher stack
   (improved_critical + savage_attacker + sharpened_mind + psionic_surge + sneak_attack)
   as data and confirm each modifier's `phase` tag produces the correct resolution order.

---

## 10. Open Extensions (future work, not currently implemented)

- **Line-shaped zones** — Currently abstracted away; piercing shot applies damage
  without modeling a true geometric line through zone space.
- **External drain magic** — `convert_resource` currently only targets spells cast
  by the ability's owner. Extending to spells on party members requires expanding
  the party entity's action economy model.
- **Enemy-cast spell triggers** — `event: creature_casts_spell` is declared but
  modeling enemy spell frequency requires expanding the enemy behavior model.
