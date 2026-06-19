# buff_primitive.md — the `cast_effect` combat-effect primitive (buffs & debuffs)

> Design note for the first-class **non-damaging cast** action. Read alongside
> `design/design.md` (§4 decision points, §6 modifier stack) and
> `ability_schema.md` (§4.5 scaling, the trigger/effect/cost layers). Status:
> **design locked 2026-06-15**; built so far = substrates (1) ModifierStack,
> (2) policy-flag (session 9), (3) StatusSet + `application_save` (session 11; its
> SAVE-FLOOR sub-kind — Starry-Form Dragon — session 15), (4) incoming-damage
> response + (5) defender thorns rider (session 12), and (6) outgoing predicate
> riders (session 14).  Substrate (7) — zone / summon / multi-entity — is
> **DESIGNED** (the design note in "Substrate #7" below, session 17, 2026-06-17),
> with its **7c foundation-min slice BUILT** (session 18: passive party member +
> enemy split-targeting + per-(source,target) DPR accounting), its **7c
> ally-effects BUILT** (session 19, 2026-06-17: `cast_effect target=ally` retarget +
> warding-bond redirect + protection/sanctuary, on a refactored `on_incoming_hit`
> response object), its **7a summon BUILT** (session 20, 2026-06-17: a controlled
> ally as a `create_entity`'d Actor, COMMANDED on its controller's turn via the
> `Choice.actor` override, in its own per-summon DPR column — the silvertail primal
> companion), and its **7c-on-summon BUILT** (session 21, 2026-06-18: the 7c
> ally-effect machinery wired ONTO the 7a beast — warding bond / protection / aid /
> bless on the silvertail beast at char L8, with the enemy striking the beast; the
> session-19 `_all` resistance-key deferral resolved here), its **7a summon survival
> & death BUILT** (session 22, 2026-06-19: summons wink out at 0 HP + a between-combats
> recast policy + the definitive per-level enemy table), and its **7b zone/emanation
> BUILT** (session 23, 2026-06-19: Spirit Guardians at silvertail char L10 — a created
> Object defining a named zone (§3.1) whose recurring WIS save-for-half fires on
> occupants at their turn boundaries; the §3.1 zonal state + move_entity + the recurring
> zone trigger.  **Substrate #7 is now COMPLETE — all sub-kinds built.**).
> It is the `cast_effect` on-ramp to the
> multi-entity / spatial model already specified in `design/design.md` §1 (objects
> vs actors; controlled allies; party members with 3 HP pools), §3.1 (zonal spatial
> model), §3.5/§3.6 (enemy targeting + party), and verbs 11/12 (`move_entity`,
> `create_entity`/`destroy_entity`).

---

## Problem

The model currently raises "a combat-long buff" three ad-hoc ways, each faking a
different part of the cast:

| Consumer | Buff stored as | Economy cost modeled as |
|---|---|---|
| Bless (War Angel) | ModifierStack (+1d4) + `concentration` field | round-1 action+BA **suppression** (`bless_turn`) |
| Starry Form Archer (Scion) | policy flag `_starry_form_active` | **free** (activation is *bundled* with the BA archer attack) |
| Shillelagh (Scion) | policy flag `_shillelagh_active` | turn-1 BA **suppression** (`casting_shillelagh`) |

We want a first-class **non-damaging cast** — a `Choice` the scheduler consumes
action economy + resources for, that produces **no `DamageEvent`**, and installs a
persisting effect. It must also be the honest model for Flame Blade's cast turn,
and generalize to the full breadth of buffs/debuffs in the build-guide corpus.

The scheduler **already** drains `cost` (action economy) and `resource_cost`
generically *before* the `action_type` branch (`scheduler.py` ~552/556). So the
primitive adds only: a `cast_effect` branch that installs the payload and pushes no
event, plus a combat-boundary sweep for combat-clock effects.

---

## The envelope (general — one shape covers every surveyed buff/debuff)

```
Choice(
    action_type   = "cast_effect",
    cost          = action | bonus_action | reaction | none,  # "none" = bundled (Sacred Weapon, Starry Form Archer)
    resource_cost = {...},          # slot / pact / channel_divinity / rage / wild_shape — already generic
    target        = self (actor) | enemy,            # self-buff vs debuff (one primitive, target-parameterized)
    effect_source = "bless",        # LABEL: stacking, removal, concentration drop, rider/zone attach point
    concentration = bool,           # set actor.concentration = effect_source
    duration      = "combat" | "day",   # combat-clock (swept at combat end) vs day-clock (DurationBuffTracker)
    application_save = None,        # debuff-only: (save_stat, dc_stat, on_success) — reuses the save machinery
    # --- payload: a SET of items, each routed to its substrate, all sharing effect_source ---
    modifiers     = [...],          # → ModifierStack
    statuses      = [...],          # → StatusSet (advantage / condition / immunity)
    # capability buffs carry NO payload — the policy reads a round-derived/stored flag
)
```

**Key generalization (forced by Fire Shield):** one cast installs a *set* of
labeled payloads across *multiple* substrates — not one. Bless installs one
(modifier); Fire Shield installs three (mode-gated resistance + mode-gated thorns
rider + the mode choice); Rage installs several (outgoing rider + resistances +
advantage-on-STR-checks). The `effect_source` label is the thread that makes the
whole bundle removable (combat-end sweep / failed-concentration drop) and, later,
attachable (riders, zones).

**Debuffs are not a separate primitive.** ModifierStack and StatusSet act on
whichever entity holds them, so a debuff is a `cast_effect` with `target = enemy`.
The only debuff-specific need is the optional **`application_save`** (Bane / Slow /
Frighten / Hold Person let the target resist), which reuses `resolve_saving_throw`
and the save-for-half path we already built.

---

## Payload-substrate registry

The question "where does the buff live" is answered by *what kind of thing it
changes*. Every substrate below already exists in the engine (or is a small, named
addition); `cast_effect` just installs a labeled payload into the matching one.

| # | Substrate | Where it lives | Effect kinds | Status |
|---|---|---|---|---|
| 1 | **ModifierStack** | `modifiers.py`, folded by `entity.stat()` | flat / rolled / stat-derived / additive numeric on a rolled stat (attack, damage, AC, save) | **BUILD NOW** |
| 2 | **policy-flag** | the build's policy (read in `decide`) | a new attack option / capability becomes available | **BUILD NOW** |
| 3 | **StatusSet** | `statuses.py`, consumed by `roll_d20` (+ saves) | advantage / disadvantage grant; condition; immunity; save floor | **BUILT** (session 11; save-floor session 15) |
| 4 | **incoming-damage modifier** | `resolve_damage`, defender-side | resistance / vulnerability / immunity by damage type | **BUILT** (session 12) |
| 5 | **defender-side reactive rider** ("thorns") | `on_incoming_hit` seam | deal damage to whoever melee-hits the bearer | **BUILT** (session 12) |
| 6 | **outgoing rider** | `on_hit` seam → separate typed DamageEvents | predicate-gated extra damage (Fount of Moonlight +2d6 radiant, Primal Strike +1d8, Rage melee-STR, Hunter's Mark) | **BUILT** (session 14) |
| 7 | **zone / summon / multi-entity** | design.md §1/§3.1/§3.5/§3.6 + verbs 11/12 | summon (own-HP ally) / emanation-zone (damage·debuff·buff) / multi-entity targeting + ally-effects (redirect, ally-buff) | **DESIGNED**; **7c foundation-min BUILT** (session 18 — party member + enemy split-targeting + per-(source,target) DPR) + **7c ally-effects BUILT** (session 19 — target=ally retarget + warding-bond redirect + protection/sanctuary, on a refactored `on_incoming_hit` response object) + **7a summon BUILT** (session 20 — `create_entity`'d Actor COMMANDED on the controller's turn via the `Choice.actor` override + per-summon DPR column; silvertail primal companion) + **7c-on-summon BUILT** (session 21 — warding bond / protection / aid / bless ON the beast at char L8 via `BeastEffectPolicy`; the `_all` resistance-key resolved) + **7b zone/emanation BUILT**
(session 23 — Spirit Guardians at silvertail char L10: a created Object / named zone
(§3.1) + `Entity.zone` + `move_entity` + a recurring turn-boundary save-for-half trigger
in the scheduler).  **#7 COMPLETE** |

Examples mapped: Bless / Magic Weapon / **Sacred Weapon** (+CHA *stacking on*
STR/DEX via `amount:{ability_modifier:charisma}` — already supported) / Bane → (1).
Starry Form / Shillelagh / Flame Blade → (2). **Innate Sorcery** (advantage on
*sorcerer* spells + DC+1) / Faerie Fire / Vow of Enmity / Auras of Purity·Courage /
Gnome Cunning → (3). **Fire Shield** resistance → (4); its thorns → (5). Rage /
Hunter's Mark → (6) + (1)/(3). Elemental node / Spirit Guardians / Fount of
Moonlight → (7).

---

## Cross-cutting seams (designed-in, build at first consumer)

- **Mode-choice** (`choose_one`): Fire Shield warm/chill — **first consumer BUILT
  (session 13)**, modeled as a `FIRE_SHIELD_MODES` data table the Scion policy
  indexes (warm = resist cold + 2d8 fire thorns; chill = resist fire + 2d8 cold
  thorns); the chosen mode selects which payload items install. The YAML
  `choose_one` schema construct in `content.py` stays deferred until `cast_effect`
  itself is data-driven (today its Choices are built in Python policies).
- **Source-gating tag**: Innate Sorcery applies only to *sorcerer spells* → the
  spell `Choice` carries a class-of-origin tag (same flavor as the existing
  `is_spell` / `damage_type` tags) that the StatusSet predicate reads.
- **Duration clock**: combat-clock (swept at combat boundary, like
  `StatusSet.clear()`) vs day-clock (10 min / 1 hr / 8 hr spanning combats →
  `DurationBuffTracker`).
  - **FULL day-clock integration is DEFERRED (planned slice, 2026-06-18).** What
    EXISTS: the minute clock (`DayRunner` samples `combat_times` in minutes, 960-min
    day) + `DurationBuffTracker` (records `(cast_minute, duration, value)`, answers
    `active_at(minute)` / `strongest_at(minute)`) — but it is a STANDALONE helper the
    **daily plan hand-wires** (War Angel checks `active_at(combat_start_minute)` in a
    `before_combat` hook and adds/removes the Magic Weapon modifier per combat).  What
    is MISSING: the `cast_effect` envelope's `duration="day"` field is NOT integrated —
    the scheduler's `cast_effect` branch only does combat-clock (note → swept at every
    boundary).  So an hour+ buff today has two imperfect options: re-cast-each-combat
    (silvertail's warding bond / aid in session 21 — effectively "always on," does NOT
    model the single-cast slot economy) or a hand-rolled `DurationBuffTracker`.  The
    FULL version threads `duration="day"` through the `cast_effect` branch + a per-entity
    day-clock effect registry that survives `clear_combat_buffs` and expires when
    `combat_start_minute > cast_minute + duration` (combat-boundary granularity).
    **Payoff (concentrated on hour+ buffs):** slot-economy fidelity — warding bond (1 hr)
    / aid (8 hr) are ONE cast covering the day, not one-per-combat — which is the whole
    sim's per-day resource-budget metric.  Pairs with the summon-survival slice (both
    touch `DayRunner` + raise silvertail fidelity).
- **`application_save`**: debuff resist roll, reuses the save machinery.

### Engine-seam notes (session 12 — flagged with the user, deferred deliberately)

- **The `on_incoming_hit` intercept seam 3-tuple — REFACTORED (session 19).** It
  served Flourish Parry (AC-flip + counter), Shield (AC-flip), and Fire Shield thorns
  (automatic `reactive_damage`) via a positional 3-tuple `(ac_bonus, counter,
  reactive_damage)`. Adding the 7c ally-effects riders (warding-bond redirect,
  protection disadvantage, sanctuary save-or-negate) was the trigger (this note's
  prediction): the scheduler closure now returns the whole `InterceptResponse` object
  (or `None`) and `resolve_attack_roll` reads the riders off it, so new riders are
  added as fields, not tuple positions. Two test files that hand-built 3-tuple
  deciders (`test_flourish_parry`, `test_incoming_damage_thorns`) were updated to
  return `InterceptResponse`.
- **Melee-vs-ranged is unmodeled (attack-taxonomy gap).** Thorns and Flourish
  Parry both ASSUME the only attacker is melee (Fire Shield / Flourish only
  trigger on melee hits). `IncomingAttackContext` carries the economy `cost` but
  no melee/ranged tag, and `AttackRollEvent` has no range axis. The first ranged
  attacker breaks this silently — so it is a conscious deferral tied to the
  ATTACK-TAXONOMY flag (PROGRESS / CLAUDE memory `attack-taxonomy-three-axes`),
  to be made first-class when a ranged attacker or a melee-gated rider needs it.

---

## Now-scope (this work)

Build the **envelope** + substrates **(1) ModifierStack** and **(2) policy-flag**:
- `Choice` gains `effect_source`, `concentration`, `duration`, and a `modifiers`
  payload list; `action_type="cast_effect"`.
- Scheduler `cast_effect` branch: economy/resources already drained → push
  `modifiers` onto the bearer (`target or actor`) under `effect_source`, set
  `actor.concentration = effect_source` if asked, push **no event**.
- Combat-boundary sweep: remove combat-clock `cast_effect` modifiers + clear their
  concentration (mirrors the existing `StatusSet.clear()` at the combat boundary),
  so a combat-long cast does not leak into the next combat.
- Retrofit the capability consumers so the cast is an honest economy-consuming
  Choice (no more suppression/free-flag fakery) — see the per-build notes / PROGRESS.

What this leaves untouched: War Angel's Bless/Magic Weapon/Shield (frozen,
validated — they keep their own `before_combat` sync; not routed through
`cast_effect` yet).

## Next-steps sequence (subsequent sessions, in order)

1. ~~**StatusSet payload (3) + `application_save`**~~ ✓ **BUILT (session 11).**
   `Choice` gained a `statuses` (list of `StatusSpec`) payload and an optional
   `application_save` (`ApplicationSave(save_stat, dc_stat, on_success)`); the
   scheduler `cast_effect` branch rolls the bearer's resist save vs the caster's
   DC (reusing `resolve_saving_throw`), and on no-resist installs the statuses on
   the bearer's StatusSet (a made save negates the WHOLE payload — modifiers +
   statuses). `resolve_attack_roll` now reads two PERSISTENT (read-not-consumed)
   advantage grants: `attack_advantage_against` on the target (Faerie Fire — any
   attacker) and `spell_attack_advantage` on the actor (Innate Sorcery — gated on
   `is_spell`). Consumers Innate Sorcery (self-grant, no save) + Faerie Fire
   (debuff, DEX save) validated via test policies (both speculative — no Scion
   consumer). Status-only concentration buffs now note their source on the ACTOR
   so the combat-boundary sweep drops the caster's concentration even when the
   bearer is the enemy. **Still designed-in for (3): conditions (frightened, etc.),
   immunity/save-floor grants, and the sorcerer-class source-gating tag** (Innate
   Sorcery's "Sorcerer spells only" — modeled here as the simpler `is_spell` gate,
   correct for a pure-caster build; a multiclass needs a class-of-origin tag).
2. ~~**Incoming-damage modifier (4) + defender-side thorns rider (5)**~~
   ✓ **BUILT (session 12).** Substrate (4) lives in `resolve_damage` as a
   defender-side phase-7 step: `Entity.damage_response_for(type)` folds an
   intrinsic trait + cast-installed payloads (2024 RAW: immunity dominates,
   resistance halves, vulnerability doubles, res+vuln of one type cancel),
   applied AFTER phase-6 halving and BEFORE `take_damage`. Substrate (5) rides
   the existing `on_incoming_hit` intercept seam: `InterceptResponse` gained a
   `reactive_damage` (`ReactiveDamageSpec`), and on a LANDED melee hit
   `resolve_attack_roll` enqueues an automatic thorns `DamageEvent` from the
   bearer to the attacker (no roll) — so thorns runs through the attacker's own
   (4) response and counts as the bearer's outgoing DPR. The Scion
   enemy-strikes-back loop (`ScriptedEnemyPolicy`, structurally identical to War
   Angel's, wired in `make_day_runner` on an `enemy_attack` row) is the machinery
   that makes both do real work.
   - **Consumers (per Option B — Fire Shield is L15, outside the modeled L1–L12
     ladder, so the build-wiring waits for a tier-4 row).** (4)'s REAL in-scope
     consumer is a **fire-resistant enemy halving the Scion's Searing Arc** (fire,
     L10+) while leaving Guiding Bolt (radiant) untouched — the exact substrate
     the deferred **Elemental Adept (fire-bypass)** will toggle. (5) is validated
     against the real loop via a Fire-Shield-shaped test policy (thorns reflected
     on every incoming melee hit). Fire Shield itself (4th-level, char L15 =
     Druid-7, guide 41:48; verified action / 10 min / non-conc / warm=resist-cold
     +2d8-fire / chill=resist-fire +2d8-cold — aidedd, D&D Beyond) installs BOTH
     (4) resist + (5) thorns from ONE cast_effect when an L15 row is wired.
   - **Fire Shield WIRED on the Scion at char L15 (session 13).** The deferred
     tier-4 row is built: ONE `cast_effect` (pre-cast, `cost="none"`, the 10-min
     non-conc spell active from initiative) installs the WARM mode's cold
     resistance (#4) on the caster; `StarfireScionPolicy.on_incoming_hit` reflects
     the 2d8 fire thorns (#5) on every incoming melee hit, with the
     enemy-strikes-back loop (`enemy_attack` row → `ScriptedEnemyPolicy`) turned on
     so the thorns do real DPR work (they land in the dummy's column — the dummy is
     both target and attacker). The fire thorns are **Elemental-Adept-treated**
     (bypass + 1->2 high-grade). Pre-cast in ONE combat/day (one 4th-level slot =
     `fire_shield_use`, 1/LR). The warm/chill **`choose_one`** is BUILT (above).
   - **Elemental Adept (fire) BUILT (session 13) — the engine primitive + its
     first consumer.** A general per-die FLOOR + RESISTANCE-bypass on the
     `DamageEvent` (`min_die` / `ignore_resistance`, threaded from the `Choice`,
     applied in `resolve_damage` phases 3 + 7 — bypasses resistance only, not
     immunity/vulnerability). The Scion's fire spells (Searing Arc) and Fire
     Shield's fire thorns carry it on L10/L11/L12/L15 (the feat is held from
     monk-4/L8), so a fire-resistant enemy takes FULL, high-graded fire — the real
     in-scope consumer (4) was waiting for. (The radiant half — Spellfire Adept's
     radiant-resistance bypass — is the symmetric deferral; no radiant-resistant
     enemy is modeled.)
   - **Still designed-in for (4)/(5):** a melee-vs-ranged tag on the incoming
     attack (today thorns follows the existing Flourish-Parry convention that the
     only attacker is melee); day-clock (10-min) duration for Fire Shield spanning
     combats (modeled combat-clock for now).
3. ~~**Outgoing predicate riders (6)**~~ ✓ **BUILT (session 14).** `HitResponse`
   gained a `rider_damage` list of `RiderDamageSpec`; on a confirmed hit
   `resolve_attack_roll` spawns each spec as its OWN typed `DamageEvent` (same
   actor→target, same is_crit) AFTER the weapon hit — so the rider's damage type /
   `is_spell` / Elemental-Adept flags stay distinct (it routes through the
   target's per-type response #4 and reaches the caster's `on_deal_damage` rider
   on its own terms).  `HitContext` gained `is_spell` + `is_unarmed` so a rider can
   gate on attack kind.  First consumers (Starfire Scion L15): **Fount of
   Moonlight** (+2d6 radiant on every melee hit incl. unarmed — `is_spell=True` so
   Fueled Spellfire fuels the first each turn for free) and **Primal Strike**
   (+1d8 elemental once/turn on a weapon hit — a FEATURE, `is_spell=False`, so NOT
   fueled and NOT Elemental-Adept-treated; built TOGGLEABLE RAW weapon-only vs a
   non-RAW also-unarmed option).
   - **Engine-seam notes (session 14):** the `on_hit` decider's return grew from a
     2-tuple to `(extra_dice, extra_masteries, rider_damage)` — `extra_damage_dice`
     (smite/bluff) still fold into the weapon hit; `rider_damage` is the new
     separate-event path.  `is_unarmed` is a MINIMAL tactical tag (the flavour of
     `is_spell`) — `weapon_stat` can't tell quarterstaff from unarmed (both
     `attack_bonus`).  This is a THIRD concrete consumer of the deferred
     ATTACK-TAXONOMY axis (after Searing Arc and Shillelagh); the first-class
     typology stays deferred (reuse minimal tags, discuss before rebuilding
     vocabulary).  Melee-vs-ranged stays gated as "not a spell attack" (no ranged
     non-spell attacker at L15 — the existing deferral).
4. ~~**FoM concentration follow-up + the Starry-Form Dragon save-floor**~~ ✓ **BUILT
   (session 15).** FoM is now a real turn-1 Magic-action concentration cast
   (`cost="action"`, sets `actor.concentration`, installs the radiant resistance #4;
   turn 1 = 0 damage); the on_hit rider gates on concentration being HELD, dropping
   the instant a failed CON save breaks it.  The substrate-#3 SAVE-FLOOR sub-kind is
   built: `resolve_saving_throw` gained `d20_floor`, and Dragon form (a Wild-Shape
   + turn-1 BA `cast_effect`) installs a `concentration_save_floor`=10 status that
   `_check_concentration` reads (guide 41:308).  A broken concentration now drops the
   WHOLE bundle via `Entity.remove_effect` (modifier + damage response + statuses,
   the last indexed by source) — fixing a latent leak where only modifiers cleared.
   The single druid-7 4th-level slot (`slot_4th`) is shared between FoM and Fire
   Shield via a `fourth_level_spell` selector (separate daily loadouts).
5. **Zone / summon / multi-entity (7)** — the last unbuilt substrate, and the
   `cast_effect` on-ramp to the multi-entity / spatial model already designed in
   `design/design.md`.  **DESIGNED (session 17), unbuilt** — see the dedicated
   "Substrate #7" section below for the decomposition (7a summon / 7b zone / 7c
   multi-entity targeting), the engine seams, the build sequence, and the chosen
   first slice (7c, which also fixes the Fire-Shield thorns over-count artifact).

---

## Substrate #7 — zone / summon / multi-entity (DESIGNED session 17, unbuilt)

> Design-first per memory `design-first-for-cross-cutting-primitives`: this is the
> most cross-cutting substrate of all (it changes the *shape of combat* from 1-vs-1
> to a roster), so the full envelope is surveyed and written up before any engine
> code. **This session (17) is design-only.** Vehicle for the survey + eventual
> validation: the **silvertail's-blessing** build (`design/build-guides/32_*`) —
> chosen because, like Fire Shield forced #4+#5+choose_one, silvertail forces the
> whole #7 cluster at once (see "Stress test" below).

### The core realization

Substrate #7 is **not a single payload kind bolted onto `cast_effect`**. It is the
point where `cast_effect` meets the **multi-entity / spatial combat model that
`design/design.md` already specifies but the engine has never needed** (every build
to date is one character vs one infinite-HP dummy). The relevant design.md contract
is already locked and correct — #7 does not redesign it, it **implements against it**:

- **§1 Core entity model** — two entity types (**Objects**: footprint, no HP/economy;
  **Actors**: HP + stats + action economy) and four actor subtypes (Character, Enemy,
  **Controlled allies** = mounts/summons/companions, **Party members** = one acting
  entity holding **3 separate HP pools**). Character/enemy/party are omnipresent;
  objects and controlled allies wink in/out.
- **§3.1 Zonal spatial model** — abstract zones (melee blob / ranged / named zones
  attached to area objects), `move_entity` changes zone, area objects tagged
  `anchored_to:<entity>` (emanation follows creator) vs `static` (placed zone).
- **§3.5 Enemy targeting** — random by default among character + party HP pools,
  trait-adjusted probabilities (`melee` raises, `invisible` lowers, grapple raises);
  prefers targets it has advantage against.
- **§3.6 Party members** — 3 infinite HP pools; statuses apply to all, healing/THP
  per pool; do nothing by default, can take generic actions for support evaluation.
- **§4 verbs 11/12** — `move_entity`, `create_entity`/`destroy_entity` (both unbuilt).
- **§8 outputs** — already lists "damage by party and created allies" and "share of
  turns summons are under status X" as first-class outputs.

So the `cast_effect` envelope already designed (payload set under an `effect_source`
label, swept on combat end / concentration drop) extends cleanly: #7 just adds two
new **payload kinds** — `summon` (→ `create_entity` an Actor) and `zone` (→
`create_entity` an Object + a recurring scheduled trigger) — plus a **target axis**
already present in the envelope (`target = self | enemy | ally | set`). What is
genuinely new is **not the envelope** but the **foundation underneath it**: a combat
that hosts a roster of >2 entities, an enemy targeting layer, and DPR accounting
attributed per (source, target).

### Decomposition — three sub-kinds on one foundation

```
            ┌─────────────────────────────────────────────────────────┐
            │  FOUNDATION: multi-entity combat (design.md §1/§3.5/§3.6) │
            │  roster of entities · enemy targeting · per-(src,tgt) DPR │
            └─────────────────────────────────────────────────────────┘
              ▲                      ▲                       ▲
   ┌──────────┴────────┐  ┌──────────┴─────────┐  ┌──────────┴──────────────┐
   │ 7c MULTI-ENTITY   │  │ 7a SUMMON          │  │ 7b ZONE / EMANATION     │
   │ TARGETING +       │  │ (controlled ally   │  │ (object + footprint +   │
   │ ALLY-EFFECTS      │  │  Actor: own HP/AC/ │  │  recurring trigger;     │
   │ (lightest)        │  │  saves/economy)    │  │  needs §3.1 zonal model)│
   └───────────────────┘  └────────────────────┘  └─────────────────────────┘
```

**7c — multi-entity targeting & ally-effects (LIGHTEST; the chosen first slice).**
A `cast_effect` (or an attack) whose `target` is an **ally** or a **set** of
entities, plus an **enemy that splits its attacks** across the friendly roster.
Corpus: aid / bless on the beast or a party member (buff an ally — substrate #1/#3
payloads, just retargeted), warding bond (damage **redirect** — when the warded
ally is hit, the caster takes a share), protection fighting style / veer / sanctuary
/ arrow-catching shield (intercept *who gets hit* — rides the existing
`on_incoming_hit` seam, design.md §4 #15). Needs from the foundation: at least one
extra friendly pool (a passive party member is enough) + an enemy targeting layer.
**Needs NO zones and NO summon lifecycle** — which is exactly why it is the first
slice, and why it **fixes the Fire-Shield thorns over-count** (see below).

**7a — summon / controlled ally.** `create_entity` brings an **Actor** into being
with its own `Entity` (HP / AC / saves / ModifierStack / ResourcePool / StatusSet —
`Entity` already supports all of these) and its own action economy, **commanded by
the character's policy** (the controller emits the ally's `Choice`s; the ally acts on
the controller's turn per §1). Lifecycle is tied to the `effect_source` label:
winks out on `destroy_entity` at concentration drop / 0 HP / combat end. Corpus:
primal companion (beast-strike charge, commanded via the master's BA), find
steed/familiar (familiar delivers touch spells — a *channel*, not a damage dealer),
eldritch cannon (placed Actor that fires), homunculus servant (force-strike +
item-carry + touch-spell delivery), undead minions. Sub-features it forces:
a **summon DPR column** (§8), the summon as a **buffable ally** (7c bless/aid land on
it) and a **redirect/soak target** (7c warding-bond / protection protect it), and
**commanded actions** (the policy decides the ally's turn).

**7b — zone / emanation.** `create_entity` brings an **Object** with a **footprint**
that defines a **named zone** (§3.1); a **recurring future-dated scheduled event**
(CLAUDE.md #5 — *durations are events in the queue, not counters*) fires the zone's
effect on entities **entering / starting their turn in / remaining in** the zone
(design.md §3.2 predicate vocabulary already lists these triggers). Two effect
flavors, same machinery: **damage/debuff enemies in the zone** (Spirit Guardians,
cloud of daggers, spike growth, moonbeam, spirit shroud, walls — most are
save-for-half, reusing the save path) and **buff allies in the zone** (circle of
power = advantage on saves vs magic + success→no-damage; aura of vitality).
`anchored_to: caster` (emanation moves with you — Spirit Guardians) vs `static` (the
placed zone stays — spike growth, walls). Obscuring zones (fog cloud, darkness) are
the same Object but grant advantage/disadvantage statuses rather than damage. **Needs
the §3.1 zonal spatial model**, which the engine has wholly deferred (every fight so
far is "everyone in melee") — so 7b is the heaviest and last.

### Envelope extension (how `cast_effect` installs #7 payloads)

The envelope is unchanged in shape; two payload kinds and the target axis are the
additions:

```
Choice(action_type="cast_effect",
    target  = self | enemy | ally | set,   # 7c: ally / set retargets existing #1/#3 payloads
    summons = [SummonSpec(statblock, commander, lifecycle=effect_source)],  # 7a → create_entity(actor)
    zones   = [ZoneSpec(footprint, anchored_to, recurring_effect, save?)],  # 7b → create_entity(object) + schedule
    # plus the existing modifiers / statuses / damage_response / etc. payloads,
    # which 7c simply lets land on an ally entity instead of self.
)
```

`effect_source` remains the thread: combat-end / concentration-drop sweep already
calls `Entity.remove_effect(source)` (session 15) — #7 extends that teardown to also
`destroy_entity` any summons/zones labeled with the source. Redirect (warding bond)
and protect (protection style) are **7c riders on the existing `on_incoming_hit`
intercept seam** — and per the session-12 engine-seam note, the *next* defender
reaction added (warding-bond redirect) is the trigger to refactor that seam's
positional 3-tuple into a single response object.

### DPR accounting — "both, reported separately" (user decision, session 17)

Today `make_day_runner` reads ONE column: `damage_received_by[dummy]`. With a roster,
attribute every `DamageEvent` to its **(source, target)** pair (the event already
knows both), then the runner reports, **separately**:

- **the build's own DPR** — damage where `source == character` (the headline metric;
  **stays bit-comparable to every prior single-entity number** — this is the
  invariant that keeps the existing test corpus meaningful);
- **a party / roster total** — summed over `source ∈ {character, summons, party}`
  (what a summon/aura/support build actually contributes);
- **a per-summon column** — each controlled ally's own output (design.md §8).

This means the headline never silently changes meaning when allies appear; the party
total is additive information beside it.

### The first slice (next build session) — 7c, which also fixes the thorns artifact

Session 16 found that pre-casting Fount of Moonlight only **narrows** its gap to the
Fire-Shield loadout to a ~0.5 near-tie (not a reversal), because **Fire Shield's
thorns over-proc in the single-dummy model**: the lone dummy *always* targets the
Scion, so *every* incoming hit reflects 2d8. That is a **modeling artifact of 1-vs-1**,
not a real advantage. The minimal 7c slice dissolves it:

1. Foundation-min: register a **passive party member** (one extra friendly HP pool;
   §3.6 — it need not act) alongside the Scion in `make_day_runner`.
2. Enemy targeting: `ScriptedEnemyPolicy` already pre-rolls its target at
   `on_combat_start` (dice-free `decide`, per CLAUDE.md #7/#9); extend the target set
   from `{character}` to `{character, party}` with §3.5 trait weighting.
3. DPR accounting: the per-(source,target) attribution above.

**Predicted sanity check (consistency, FakeRNG — NOT number-matching, per the
Starfire framing):** with the enemy spreading attacks across the party, Fire Shield's
thorns fire on only a fraction of rounds → its DPR drops, and the pre-cast FoM
loadout **overtakes** it — the session-16 near-tie finally reverses. This is the
slice that closes BOTH the substrate-#7 gap (7c) and the session-16 modeling artifact.

### Build sequence (multi-session; each gated design-first against this note)

1. **7c multi-entity targeting (foundation-min)** — the slice above. **BUILT
   (session 18, 2026-06-17).** A passive party member (`make_party_member`, one
   infinite-HP friendly pool, no policy) + `ScriptedEnemyPolicy` MULTI-ENTITY mode
   (a weighted friendly roster, §3.5: melee Scion 2 : party 1, pre-rolled at
   `on_combat_start`) + per-(source,target) DPR accounting (a
   `Scheduler.damage_by_source_target` ledger → `DayResult.damage_by_source` /
   `damage_source_to` / `party_total`).  Wired on the Scion at L15 via
   `make_day_runner(..., with_party=True)` (default False → the 1-vs-1 scenario stays
   bit-identical).  Validated by reversing the FoM↔Fire-Shield near-tie: with the
   enemy splitting attacks, Fire Shield's thorns fire on a fraction of hits so the
   pre-cast FoM loadout overtakes it (consistency/sanity, FakeRNG + directional DPR).
   No summons, no zones.
2. **7c ally-effects** — bless/aid retargeted onto an ally; warding-bond **redirect**
   (refactor the `on_incoming_hit` 3-tuple → response object here); protection /
   sanctuary **protect** (who-gets-hit). **BUILT (session 19, 2026-06-17).** Vehicle:
   the Scion + a synthetic ally (`make_ally` + `AllyEffectPolicy` +
   `make_ally_effects_runner`) — silvertail deferred to the 7a summon slice (lighter
   first, per the user). Three effects, all verified against 2024 text first:
   (a) **ally-buff retarget** — `cast_effect target=ally` lands existing #1/#3/#4
   payloads on the ally, NO engine change (the cast_effect branch already installs on
   `choice.target or actor`); (b) **warding bond** — the ally's `on_incoming_hit`
   returns a `RedirectSpec`; `resolve_attack_roll` threads it onto the `DamageEvent`
   and `resolve_damage` spawns a copy of the taken amount onto the caster (attributed
   to the original attacker, never recursing); (c) **protection** — `impose_disadvantage`
   re-rolls the attack with a second d20 (flip on a miss; P(hit)² exact; crit kept only
   on a double-20); (d) **sanctuary** — `negate_save` makes the ATTACKER save vs the
   caster's DC or the attack is negated. Adding warding-bond redirect was the trigger
   that **refactored the `on_incoming_hit` positional 3-tuple
   (`ac_bonus, counter, reactive_damage`) into the single `InterceptResponse` object
   returned by the decider** (the session-12 engine-seam note paid off).
3. **7a summon** — `create_entity`/`destroy_entity` an Actor; commanded actions; the
   summon DPR column; summon as buff/redirect target. Vehicle: silvertail primal
   companion. (`transform_statblock`, §4 #13, is adjacent but distinct — Wild Shape.)
   **BUILT (session 20, 2026-06-17, the MINIMAL slice — char L4 only).** A controlled
   ally as a real `create_entity`'d **Actor** (`make_primal_companion` — own HP/AC/
   saves), **COMMANDED on the controller's turn** via the new **`Choice.actor`**
   override (the master's policy emits the beast's Beast's-Strike Choice; the cost is
   the master's **Bonus Action** — the command; the spawned event's actor is the
   beast, so it uses the beast's stats and is attributed to it). The **per-summon DPR
   column** falls out of the per-(source,target) ledger for free
   (`damage_by_source(beast)`), reported SEPARATELY from the build column + party
   total. **Verbs 11/12** = `src/summons.py` `create_entity`/`destroy_entity` on an
   `(entities, policies)` roster (exercised at DAY START for the permanent companion;
   `Scheduler.add_entity`/`remove_entity` + the cast_effect `summons` payload are the
   general mid-combat path, lightly exercised); lifecycle keyed to `effect_source`
   (`Entity.remove_effect` marks summons `destroyed`).  **Summon-as-buff/redirect
   target (7c-on-summon) BUILT (session 21, 2026-06-18, char L8.)** The beast is a
   real `Entity`, so the built 7c machinery lands on it directly via
   `BeastEffectPolicy` (a passive defender policy registered for the beast — it still
   takes no turn of its own, the master COMMANDS it): warding bond (+1 AC/saves +
   resistance-to-all + redirect the post-resistance share to the master), protection
   (impose disadvantage), bless (+1d4 to the beast's attacks/saves → raises its
   outgoing DPR), aid (+5 HP max — DPR-inert).  The enemy STRIKES THE BEAST (typed) so
   the defender effects do real work; the payload is re-applied each combat via
   `on_combat_start` (the Fire Shield / Bless re-cast pattern).  The session-19 `_all`
   resistance-key deferral was resolved here.  Built RAW-faithfully at the kit's access
   level (char L8: Protection fighter-1 / Bless cleric-1 / Aid + Warding Bond
   cleric-3), mirroring Fire Shield → L15.  Still deferred: charge-PRONE→advantage
   (needs an on-hit-applies-status seam — entangled with shocking-grasp-denies-
   reactions + an opportunity-attack model); mid-combat conjure summon lifecycle.
   - **Uncommanded summon → Dodge (DEFERRED, build when forced).** A controlled ally
     that is NOT commanded on a turn takes the **Dodge** action by default (2024 Primal
     Companion; design.md §1) → **disadvantage on attacks against it** (until its next
     turn) + **advantage on DEX saves**.  The disadvantage half **reuses the existing
     `impose_disadvantage` rider** (Protection / 7c-on-summon): the summon's
     `on_incoming_hit` returns it, gated on "not commanded this turn"; the DEX-save-
     advantage half matters against 7b save-for-half zones.  NOT forced yet — the
     silvertail always spends its BA to command the beast (max offense, never dodges);
     build at the first build that leaves a summon uncommanded.  This is the
     action-economy trade-off the command model exists to expose (command = offense,
     Dodge = defense).
3b. **SUMMON SURVIVAL & DEATH + recast policy — BUILT (session 22, 2026-06-19).** Wired
   `Entity.dies_at_zero_hp` → `take_damage` sets `destroyed` when a SUMMON crosses to
   ≤ 0 HP (the single 0-HP trigger; the scheduler already skips destroyed turns + the
   commander already checks `destroyed`, so a dead summon's DPR contribution
   disappears).  The threshold model is untouched for non-summons (they leave the flag
   False).  A **long rest revives a winked-out summon** (`DayRunner._apply_lr` — RAW:
   choose/revive a companion on a long rest; also keeps multi-day loops sane).
   **Recast policy** = a per-character BETWEEN-COMBATS decision (`make_recast_hook`):
   2024 Primal Companion revival is **1 minute** (web-verified) → never lands inside a
   4-round combat, so it is inherently between-combats — revive iff dead + a spare slot
   remains + a later combat remains (greedy, finite slot budget; "policies are code").
   **Coupled — the DEFINITIVE per-LEVEL enemy table (decision #12's realised half):** the
   single reference the engine draws enemy numbers from is now
   `reference/data/monster_stats_by_level.csv` — one row per character level 1-20 carrying
   BOTH halves: AC + the six saves (defense) AND to-hit / save DC / n_attacks / per-swing
   `attack_dice` / `aoe_dice` (offense).  `src/builds/enemy_stats.py` LOADS it at import and
   is the accessor layer; the generation (`regenerate()`, run `python -m
   src.builds.enemy_stats`) derives the offense from the user's "Average Monster Stats by
   CR" chart (Rothner) and copies AC/saves from `monster_ac_and_saves_by_level.csv`
   (provenance).  Derivation (user spec): fit each chart column vs CR (linear to-hit/DC,
   quadratic damage; R²>0.99), evaluate at **CR == level** (ignore the chart's Level
   column), **÷1.5 the damage** (a CR-N monster is built for FOUR level-N PCs; here ≤3
   friendlies and the enemy is never killed by them → incoming over-inflated), re-express
   each damage average as DICE (per-swing = `N dX + PB`, the chart's matched die size X +
   the level's proficiency bonus as the flat; AoE = `M dY`) so **enemy CRITS fall out** (a
   natural 20 doubles the dice; the flat PB stays single), and apply a few hand-tuned
   `_OVERRIDES` so every DAMAGE column rises MONOTONICALLY.  `BaselineEnemyPolicy`
   (`src/builds/enemy.py`, keyed by `level`) mixes attack-roll rounds (n swings, per-level
   dice) and SAVE-forcing rounds (one of the six saves, weighted, vs the per-level DC, AoE
   dice, half on a save), and RETARGETS onto the master when the beast winks out (focus-fire
   → fallback).  (L8 enemy: AC 16 / +8 / DC 15 / `3d8+3` ×2 / `8d4` AoE.)  **MECHANISM
   validated**
   (`tests/test_summon_survival.py`): a dead summon stops contributing (mortal
   lifetime output ≪ the threshold-immortal beast); a +HP buffer buys an extra strike
   when it crosses a per-hit breakpoint (deterministic); reducing landed hits keeps it
   contributing longer; reviving it restores the contribution; the enemy retargets to the
   master on death.  Wired on the silvertail L8 row, with `mortal_beast` / `recast` opt-in
   flags so the session-21 mechanism tests (immortal beast) stay byte-identical; the
   enemy is the definitive per-level table by default.  **These are MECHANISM checks, NOT
   build-value claims** — the
   survivability numbers are not meaningful as build evaluation yet because three build
   factors are unmodeled (each flagged for the full build, NOT this slice):
   (i) **enemy targeting split** — with a party present the beast should be hit ≤ 1/3 of
   the time, not focus-fired (the §3.5 weighted roster already exists in
   `ScriptedEnemyPolicy`; wire it into `BaselineEnemyPolicy`);
   (ii) **beast self-healing** — the companion has ranger-level d8 HIT DICE (spent on a
   short rest) and receives Prayer of Healing (the master gets it at L8) — neither
   hit-dice nor PoH healing is modeled (a real engine gap);
   (iii) **Mounted Combatant's VEER** (the master, L4) — redirect onto the master any hit
   that would drop the beast OR that beats the beast's AC but not the master's higher AC
   (a target-REASSIGNMENT intercept — a new `on_incoming_hit` flavor; relates to the
   attack-only seam below).  **Also still deferred:** aid upcast (+10 at L10+, 3rd-level
   slots); warding-bond redirect on save-damage (rides the attack-only `on_incoming_hit`
   seam — resistance applies to saves, the redirect doesn't); a smarter recast policy.
4. **7b zone / emanation** — the §3.1 zonal spatial model + recurring scheduled zone
   events; damage/debuff and buff flavors; anchored vs static. Vehicle: silvertail
   Spirit Guardians (emanation) + the wardancer's spike growth / cloud of daggers
   (static hazard, the design.md §3.1 canonical example).
   **BUILT (session 23, 2026-06-19 — Spirit Guardians, the minimal-but-real slice).**
   Scope settled with the user up front: minimal-but-real spatial model; Spirit
   Guardians ONLY; commit, stop before merge. 2024 text web-verified first (3rd-level,
   Self 15-ft emanation, **Wisdom** save (not WIS/DEX), 3d8 radiant good/neutral, half
   on a save, concentration, once per turn). Built:
   - **Zonal spatial state (§3.1)** — `Entity.zone` (every entity occupies one abstract
     zone; the implicit shared `"melee"` blob by default) + `zones.move_entity` (verb
     11, the membership-change behind kiting / leaving a hazard).
   - **`src/zones.py`** — `Zone` (a created **Object**: footprint, no HP/economy —
     modeled as a distinct lightweight type, NOT forced into the HP-bearing `Entity`
     roster, faithful to §1's Object/Actor split) + `ZoneEffectSpec`. An emanation is
     `anchored_to` its owner (`current_location` reads the anchor's zone → the aura
     follows the caster); `unaffected` designates the owner + allies safe; a `destroyed`
     flag is the teardown.
   - **Recurring zone trigger** — `Scheduler._fire_zone_effects` at each entity's turn
     boundary forces the save on every damaging zone it is inside, reusing the
     save-for-damage path (`SaveDamageEvent` → `resolve_save_damage`). The recurrence
     falls out of turns recurring (CLAUDE.md #5: a trigger on the `TurnStartEvent`),
     rather than a hand-rolled re-enqueued event — a deliberate decision (see the
     engine-seams note). Zone damage is attributed to the OWNER → the caster's zone-DPR
     column falls out of the per-(source, target) ledger, like the 7a summon column.
   - **Envelope** — `Choice.zones` (the `zones` payload, mirroring `summons`); the
     scheduler's `cast_effect` branch registers each Zone and labels it under
     `effect_source` so `Entity.remove_effect` (concentration drop / boundary sweep)
     marks it destroyed (a broken concentration ends the emanation). The 3rd-level slot
     is abstracted under the combat-clock recast model (full slot/day-clock economy
     deferred, as for Fire Shield / the L8 buffs).
   - **Build** — new silvertail char **L10** row (Fighter-1/Ranger-4/Cleric-5 Trickery,
     PB 4, WIS 19 → DC 16): the master opens each combat by casting the emanation
     (concentration) then melees under it; the enemy focus-fires the master so its hits
     can break concentration and end the zone.
   - **MECHANISM validated** (`tests/test_zone_emanation.py`, +12; NOT build value): a
     zone fires recurringly once per occupant turn; save-for-half; owner-attributed;
     `move_entity` escapes / an anchored emanation follows the owner; owner + allies
     unaffected; a dropped concentration winks it out. L10 integration: the emanation
     forces recurring WIS saves (~57% fail vs DC 16) and lifts the caster's column
     ~+81 radiant/day. ATTACK-TAXONOMY NOT forced (a save emanation, not an attack).
   - **DEFERRED:** static (placed) zones (spike growth / cloud of daggers) + buff-auras
     (circle of power) — same machinery, the anchored-vs-static + buff-target axes;
     footprint-vs-mover-speed exit gating; multi-named-zone maps; the "enters / emanation
     enters its space" triggers (only the turn-boundary "ends turn inside" is modeled);
     wiring an enemy's §3.5 "tries to leave the zone" into a policy.

### Stress test — silvertail forces the whole cluster (the "hard case")

Per the design-first ritual, the envelope is stress-tested against a build that needs
*all* of #7 at once, the way Fire Shield forced #4+#5+choose_one:

- **Primal companion** → 7a summon (own HP/AC/saves; beast-strike charge; commanded
  by the master's BA) — not the threshold-immortal dummy.
- **Spirit Guardians** (cleric-5 / char L10) → 7b emanation (recurring save-for-half
  to enemies in a 15-ft radius, anchored to the caster).
- **Circle of power** (cleric-9 / L17) → 7b **buff**-aura (allies in the zone get
  advantage on saves vs magic + success→no-damage) — the same Object machinery,
  buff flavor.
- **Aid / bless on the beast** → 7c ally-buff (retargeted #1/#3 payloads).
- **Warding bond** → 7c **redirect** (master takes half the beast's damage).
- **Protection fighting style / veer / sanctuary / arrow-catching shield** → 7c
  **protect** (impose disadvantage / reassign the target — `on_incoming_hit` riders).
- **Invoke duplicity** (the duplicate) → an Object-as-positional-token (no HP) that
  grants advantage to attacks near it — a degenerate zone (footprint, no recurring
  damage); confirms the Object/zone shape covers non-damaging placed entities too.
- **Mounted combat** (rider + mount share a zone, move at mount speed; §3.1) → the
  zonal model's mount rule; and the enemy choosing **beast OR master** is exactly the
  7c targeting split (same mechanism that fixes the thorns artifact).

The envelope absorbs every one of these as a payload kind + target/anchor parameter —
no new envelope field beyond `summons` / `zones` / the `ally|set` target. That
convergence (one diverse build hitting all three sub-kinds with no envelope growth) is
the evidence the #7 shape is settled, mirroring the Fire-Shield stress test for
#4/#5.

### Engine seams to build (enumerated; NOT built this session)

- **Roster in the runner** — `make_day_runner` / `day_runner` register a list of
  entities (character + party + later summons + enemy) instead of the hard-wired
  character + one dummy.
- **Enemy targeting layer** — extend `ScriptedEnemyPolicy` target selection over the
  friendly roster, pre-rolled at `on_combat_start`, §3.5 trait-weighted.
- **Per-(source,target) DPR accounting** — attribute every `DamageEvent`; runner
  reports build-column + party-total + per-summon (above).
- **verbs 11/12** — `create_entity`/`destroy_entity` (Actor for 7a, Object for 7b),
  `move_entity` (zone changes); lifecycle keyed to `effect_source`.  ✓ `create_entity`/
  `destroy_entity` DONE (session 20, `src/summons.py`) for the Actor/7a case —
  roster-level ops usable at day start or mid-combat, lifecycle keyed to
  `effect_source` via `Entity.remove_effect`.  Commanded actions DONE via the
  `Choice.actor` override.  ✓ `move_entity` DONE (session 23, `src/zones.py`).  ✓ The
  Object/7b create DONE (session 23) — a Zone is a distinct lightweight Object type
  registered in the scheduler's zone registry (NOT an HP-bearing `Entity`), labelled
  under `effect_source` so `Entity.remove_effect` winks it out.
- **Recurring zone event** — ✓ DONE (session 23): `Scheduler._fire_zone_effects` fires
  the zone's save-for-half on every occupant inside at its turn boundary (reusing the
  `SaveDamageEvent` path).  Implemented as a synchronous trigger on the recurring
  `TurnStartEvent` rather than a hand-rolled re-enqueued event — the recurrence comes
  from turns recurring (CLAUDE.md #5: triggers are subscribers fired when an event
  resolves), so no separate scheduled-event machinery duplicates the round seeding.
  (The "enters the zone / emanation enters its space" mid-turn triggers are deferred —
  only the turn-boundary "ends its turn inside" case is modeled.)
- **Zonal spatial state (§3.1)** — ✓ DONE (session 23): an explicit `Entity.zone`
  attribute (the implicit shared `"melee"` blob by default) + the scheduler's named-zone
  registry; `move_entity` changes membership; an anchored emanation reads its location
  off the anchor (it follows the caster).  Deferred: footprint-vs-mover-speed exit
  gating and richer multi-named-zone maps (the minimal model is one shared blob + the
  emanation's location).
- **Intercept-seam refactor** — ✓ DONE (session 19): the `on_incoming_hit` 3-tuple
  is now the single `InterceptResponse` object returned by the decider (warding-bond
  redirect was the trigger, exactly as the session-12 note predicted).

### Cross-cutting / deferred notes

- **Reactor economy is ABSTRACTED into the defender's response (session 19, user
  decision: keep).** The 7c riders (protection disadvantage, sanctuary save-or-negate,
  warding-bond redirect) are returned by the ALLY's `on_incoming_hit` (the seam
  consults the DEFENDER's policy), with the protector/caster's reaction folded in and
  self-gated — the same convention as Fire-Shield thorns and Flourish Parry. So a
  protector's single reaction is NOT a real engine resource and multi-reactor
  contention (two protectors, or a protector also wanting an opportunity attack) is
  unmodeled. A known simplification, fine for the single-attacker cases modeled;
  revisit only when a build with competing reactions forces it.
- **"Resistance to ALL damage" — BUILT (session 21).** The session-19 deferral is
  resolved: `Entity.damage_response_for` now honors a reserved `"_all"` key that
  applies to any TYPED hit (it still returns None for an untyped `None` attack),
  feeding the same 2024 dominate/cancel rules.  Warding Bond installs
  `{"_all": "resistance"}` on the beast; the silvertail enemy's swings are TYPED
  (`ScriptedEnemyPolicy(damage_type=...)`) so the resistance bites before the redirect
  copies the halved amount to the master.  (Warding Bond / Rage grant resistance to
  all damage; per-type keys remain for type-specific effects like Fire Shield.)

- **ATTACK-TAXONOMY (memory `attack-taxonomy-three-axes`).** Multi-entity combat is
  the most likely forcer of the first-class kind/action/economy typology — melee-vs-
  ranged finally matters (thorns/protection are melee-gated; an enemy targeting the
  back-line is ranged). Revisit, but per the standing decision *discuss before
  rebuilding the attack vocabulary* — keep using minimal tags until a slice truly
  forces it.
- **Per-feature ritual.** This is a DESIGN note, not a modeled mechanic, so the
  rules-verification half is N/A here — but every spell named above (Spirit
  Guardians, warding bond, circle of power, find steed/familiar, eldritch cannon,
  spike growth, cloud of daggers, aid) is cited from the build guides as a *survey
  signal only*; its **exact 2024 wording MUST be verified at its build session**
  before modeling (the cited guide lines are pointers, not authority).
- **`design.md` is unchanged.** It already specifies this model correctly; #7
  implements against it. If a build slice reveals a genuine gap in design.md,
  reconcile it there deliberately (per design.md §0), not silently.

## Verification debt (per the per-feature ritual)

- **Mode-choice (`choose_one`)** — canonical consumer Fire Shield (warm/chill),
  **BUILT session 13** as the `FIRE_SHIELD_MODES` data table (see above). (A
  "distract/protect/strike" feature was floated in discussion but misremembered:
  the Depth Guard L3 feature is **Spiritual Protectors** (Ancestral Guardian), a
  debuff-on-hit → substrate (3)/(6), not a mode-choice. Confirm any mode-choice
  feature's exact 2024 wording before modeling.)
- **Fount of Moonlight / Primal Strikes — verified + MODELED (session 14).** Per
  the per-feature ACCESS + rules ritual (re-verified 2026-06-16, D&D Beyond /
  dnd2024.wikidot.com / Roll20; access from build-guide 41:48, 739–742, 758):
  **Fount of Moonlight** (4th-level, char L15 = druid-7) — "Resistance to Radiant
  damage, and your MELEE attacks deal an extra 2d6 Radiant damage on a hit" (+ a
  reaction-blind deferred); the radiant is a spell's → fueled by Fueled Spellfire.
  **Primal Strike** (Elemental Fury, druid-7) — "Once on each of your turns when
  you hit with an attack roll using a WEAPON (or a Beast form's attack), +1d8
  Cold/Fire/Lightning/Thunder (choose on hit)"; the 2d8 step is DRUID-15 (so 1d8
  here), and it is a FEATURE (not a spell) → Elemental Adept does NOT treat it.
  Both built as substrate-(6) on_hit riders on the Scion at L15. **Sunbeam is a
  6th-level spell = char L19** (a separate later row); it fuels for free on the
  existing DamageEvent path — NOT built this session.
- **Innate Sorcery / Sacred Weapon / Rage / Fire Shield** wording verified at
  build time, not from memory. Fire Shield confirmed 2026-06-15 (D&D Beyond /
  aidedd): action, 10 min, non-conc; warm = resist cold + 2d8 fire thorns; chill =
  resist fire + 2d8 cold thorns.
- **Fire Shield ACCESS for this build is char L15** (Druid-7 → 4th-level spells;
  guide 41:48), outside the modeled L1–L12 ladder. Confirmed at session-12 build
  time (per the per-feature ritual: verify access, not just wording). So #4/#5
  shipped as engine substrates with (4) validated by a real in-scope consumer
  (fire-resistant enemy vs Searing Arc) and (5) by a Fire-Shield-shaped test
  policy against the real enemy loop; the Fire-Shield-on-Scion build-wiring is
  deferred to a tier-4 row.
