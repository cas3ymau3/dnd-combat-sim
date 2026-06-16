# buff_primitive.md — the `cast_effect` combat-effect primitive (buffs & debuffs)

> Design note for the first-class **non-damaging cast** action. Read alongside
> `design/design.md` (§4 decision points, §6 modifier stack) and
> `ability_schema.md` (§4.5 scaling, the trigger/effect/cost layers). Status:
> **design locked 2026-06-15**; built so far = substrates (1) ModifierStack,
> (2) policy-flag (session 9), (3) StatusSet + `application_save` (session 11),
> (4) incoming-damage response + (5) defender thorns rider (session 12), and
> (6) outgoing predicate riders (session 14).  Only (7) zone/summon remains.

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
| 3 | **StatusSet** | `statuses.py`, consumed by `roll_d20` (+ saves) | advantage / disadvantage grant; condition; immunity; save floor | **BUILT** (session 11) |
| 4 | **incoming-damage modifier** | `resolve_damage`, defender-side | resistance / vulnerability / immunity by damage type | **BUILT** (session 12) |
| 5 | **defender-side reactive rider** ("thorns") | `on_incoming_hit` seam | deal damage to whoever melee-hits the bearer | **BUILT** (session 12) |
| 6 | **outgoing rider** | `on_hit` seam → separate typed DamageEvents | predicate-gated extra damage (Fount of Moonlight +2d6 radiant, Primal Strike +1d8, Rage melee-STR, Hunter's Mark) | **BUILT** (session 14) |
| 7 | **zone / summon** | (none yet — multi-enemy/spatial) | damaging emanation / placed entity | DEFERRED |

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
  `StatusSet.clear()`) vs day-clock (10 min / 1 hr spanning combats →
  `DurationBuffTracker`). Both mechanisms already exist.
- **`application_save`**: debuff resist roll, reuses the save machinery.

### Engine-seam notes (session 12 — flagged with the user, deferred deliberately)

- **The `on_incoming_hit` intercept seam is near its shape limit.** It now serves
  Flourish Parry (AC-flip + counter), Shield (AC-flip), and Fire Shield thorns
  (automatic `reactive_damage`), and the scheduler closure returns a positional
  3-tuple `(ac_bonus, counter, reactive_damage)`. The NEXT defender reaction added
  should refactor that to a single richer response object (mirror the
  Miss/Hit/InterceptResponse pattern) rather than a growing tuple.
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
     vocabulary).  FoM is modeled NON-concentration this session (pre-cast like
     Fire Shield); the in-combat Magic-action cast + concentration + the
     Starry-Form Dragon save-floor are the next session's work.  Melee-vs-ranged
     stays gated as "not a spell attack" (no ranged non-spell attacker at L15 —
     the existing deferral).
   Then **zones/summons (7)**, gated on the multi-enemy / spatial model — the last
   unbuilt substrate (Sunbeam L19, Spirit Guardians, the elemental node, AoE).

---

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
