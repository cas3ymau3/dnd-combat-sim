# buff_primitive.md — the `cast_effect` combat-effect primitive (buffs & debuffs)

> Design note for the first-class **non-damaging cast** action. Read alongside
> `design/design.md` (§4 decision points, §6 modifier stack) and
> `ability_schema.md` (§4.5 scaling, the trigger/effect/cost layers). Status:
> **design locked 2026-06-15**; built so far = substrates (1) ModifierStack,
> (2) policy-flag (session 9), and (3) StatusSet + `application_save` (session 11).

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
| 4 | **incoming-damage modifier** | `resolve_damage`, defender-side | resistance / vulnerability / immunity by damage type | designed-in (Fire Shield) |
| 5 | **defender-side reactive rider** ("thorns") | `on_incoming_hit` seam | deal damage to whoever melee-hits the bearer | designed-in (Fire Shield) |
| 6 | **outgoing rider** | `on_hit` / `on_deal_damage` seams | predicate-gated extra damage (Rage melee-STR, Hunter's Mark vs-target, Divine Favor per-hit) | designed-in |
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

- **Mode-choice** (`choose_one`): Fire Shield warm/chill; the deferred schema block.
  The chosen mode selects which payload items install.
- **Source-gating tag**: Innate Sorcery applies only to *sorcerer spells* → the
  spell `Choice` carries a class-of-origin tag (same flavor as the existing
  `is_spell` / `damage_type` tags) that the StatusSet predicate reads.
- **Duration clock**: combat-clock (swept at combat boundary, like
  `StatusSet.clear()`) vs day-clock (10 min / 1 hr spanning combats →
  `DurationBuffTracker`). Both mechanisms already exist.
- **`application_save`**: debuff resist roll, reuses the save machinery.

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
2. **Incoming-damage modifier (4) + defender-side thorns rider (5)** — first
   consumer Fire Shield (and Rage's resistances). Couples to the incoming-damage
   loop (enemy strikes back), so it lands naturally when a Scion level faces an
   attacking enemy. Thorns is *outgoing* DPR (counts for us); resistance is
   second-order (eases our concentration saves).
3. **Outgoing predicate riders (6)** — Rage damage, Hunter's Mark; `choose_one`
   modes; source-gating tags. Then zones/summons (7), gated on the multi-enemy /
   spatial model.

---

## Verification debt (per the per-feature ritual)

- **Mode-choice (`choose_one`)** — the canonical consumer is Fire Shield (warm/
  chill). (A "distract/protect/strike" feature was floated in discussion but
  misremembered: the Depth Guard L3 feature is **Spiritual Protectors** (Ancestral
  Guardian), a debuff-on-hit → substrate (3)/(6), not a mode-choice. Confirm any
  mode-choice feature's exact 2024 wording before modeling.)
- **Innate Sorcery / Sacred Weapon / Rage / Fire Shield** wording verified at
  build time, not from memory. Fire Shield confirmed 2026-06-15 (D&D Beyond /
  aidedd): action, 10 min, non-conc; warm = resist cold + 2d8 fire thorns; chill =
  resist fire + 2d8 cold thorns.
