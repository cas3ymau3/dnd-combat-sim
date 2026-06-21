# Attack / action MODALITY taxonomy (the locked contract)

> Status: **LOCKED (session 25, 2026-06-21).** The vocabulary lives in
> `src/taxonomy.py` (the single source of truth). This note is the design
> rationale + the migration plan. Read it before adding attack-like content or
> touching the attack/cast vocabulary. Supersedes the "ATTACK TAXONOMY —
> engine-vocabulary gap" flag in PROGRESS.md (which is now being closed).

---

## The problem this fixes

The word **action** was doing double duty — both in casual D&D speech and in our
engine — for two independent things:

1. the **economy cost** of doing something (you have one *action*, one *bonus
   action*, one *reaction*, your *movement* per turn); and
2. the **thing being done** ("the attack action", "the magic action").

That conflation breaks the moment a feature decouples them. Using your *bonus
action* to attack (off-hand swing, a Cunning-Action-granted strike) is still the
**Attack** thing — but it is **not** "the Attack action", because no *action*
(economy sense) was spent, so gates that key on "you took the Attack action" must
read False. Likewise a quickened spell is the **Magic** thing at a bonus-action
cost. The engine encoded this with ad-hoc proxies (`action_type`, `is_spell`,
`is_unarmed`, `weapon_stat`) that collapsed several distinct rules axes.

**Resolution of the naming clash:** we reserve **action** for the economy cost
only, and use **modality** for the thing done.

---

## The axes

Two PRIMARY axes (every Choice has both) + four DESCRIPTORS (present only when
meaningful):

| Axis | Kind | Values | Governs |
|---|---|---|---|
| **modality** | primary | Attack · Magic · Use Ability · Dash · Disengage · Dodge · Help · Hide · Influence · Ready · Search · Study · Utilize | what the character is doing |
| **cost** | primary | action · bonus_action · reaction · movement · free · none | the action-economy resource spent |
| **resolution** | descriptor | attack_roll · saving_throw · automatic | how the effect is evaluated |
| **origin** | descriptor | weapon · unarmed · spell · feature | the source of a damage/save ability |
| **range** | descriptor | melee · ranged | for attack_roll abilities (unarmed ⇒ melee) |
| **damage_type** | descriptor | the 13 core types | for damaging abilities |

### Modality

The full PHB-2024 set of things that cost an action-economy resource, **plus our
addition `Use Ability`** = a *non-magical* class/subclass feature (Rage, Second
Wind, Steady Aim) that does something for an economy cost but is neither an attack
nor magic. By default every modality costs an *action*; features change the cost
(Cunning Action → bonus action; Quicken → bonus action; War Magic → replace one
Attack-modality swing with a Magic cantrip).

Two naming notes:
- **"the Magic action" is a misnomer** — the Magic modality can be used at a bonus
  action / reaction / free cost. We say "uses magic" / "casts a spell" for the
  modality; "the magic action" is only the special case `modality==Magic and
  cost==action` (mirrors "the attack action"), and gates on it in no modelled
  build.
- The **combat-relevant subset** (`COMBAT_MODALITIES`) is Attack, Magic, Use
  Ability, Dash, Disengage, Dodge, Help, Ready. The rest are NAMED for a closed
  vocabulary but given no resolution machinery — they never touch DPR /
  survivability (enumerate them all; implement the subset).

### Resolution — and its relationship to the engine's `action_type`

`resolution` describes *how the effect is evaluated by dice*: an **attack_roll**
(roll d20 vs AC), a **saving_throw** (target rolls vs the DC), or **automatic**
(no roll gates the effect — a buff install, Magic Missile, ongoing damage).

The 2024 rules call **any** `resolution==attack_roll` ability "an attack",
regardless of modality. That is why **Guiding Bolt** (a Magic-modality spell
delivered via an attack roll) counts as "an attack" for riders/advantage, while
**Sacred Flame** (a saving_throw spell) does not. The predicate `is_attack` ==
`resolution=="attack_roll"` captures this; when this note says "an attack" loosely
it means exactly that.

`resolution` is **related but not identical** to the engine's `Choice.action_type`
dispatch discriminator (`"attack"` / `"save_spell"` / `"cast_effect"`).
`action_type` also selects the *install-vs-damage payload*: a debuff `cast_effect`
WITH an `application_save` has `resolution=="saving_throw"` but still dispatches as
`"cast_effect"` because it installs a payload rather than dealing damage. So we
KEEP `action_type` as the scheduler's dispatch selector and carry `resolution` as
the orthogonal descriptor. (A future cleanup may fold `action_type` into
`resolution` + a payload tag, but that is not required.)

### Origin — and why `feature` is its own value

`origin` is the source of a damage- or save-forcing ability. The grouping
`physical = {weapon, unarmed}` is your old "physical damage"; `spell` is the
Fueled-Spellfire / Elemental-Adept gate. **`feature` is a distinct value** for a
magical source that is **not a spell** — e.g. the Starfire Scion's **Starry-Form
Archer**, a magical feature making a ranged attack dealing radiant. This is why
its radiant is correctly NOT fuelable and NOT Elemental-Adept-treated: those gate
on `origin=="spell"` specifically, and a feature is magical-but-not-a-spell. The
engine already encoded exactly this distinction via `is_spell=False`; the taxonomy
just names it. `is_spell` ≡ `origin=="spell"`.

### Range — the defense-side gap it closes

`range` (melee / ranged) applies only to attack_roll abilities; a weapon attack
can be either (longsword vs longbow), and so can a spell attack (Shocking Grasp vs
Fire Bolt). All unarmed strikes are melee (true for every modelled build). This is
the axis the engine previously **lacked entirely**: Fire-Shield thorns and
Flourish Parry only fire on MELEE hits but had no range to read, so they silently
assumed melee. `range` is now carried on `AttackRollEvent` / `HitContext` /
`IncomingAttackContext` for those gates to read.

---

## Derived predicates (computed, never stored)

```
is_attack(resolution)            := resolution == "attack_roll"
is_attack_action(modality, cost) := modality == "Attack" and cost == "action"
is_physical(origin)              := origin in {"weapon", "unarmed"}
is_spell_origin(origin)          := origin == "spell"
```

`HitContext` exposes `is_physical` / `is_spell_origin` as properties; riders
should prefer these over the legacy `is_spell` / `is_unarmed` flags.

> ⚠️ `is_attack_action` identifies the Attack-action **expenditure** (you spend
> your action to Attack). It is **NOT** the gate GWM / Searing-Arc features key on
> — those want "made *as part of* the Attack action", which is the PROVENANCE
> property below, not derivable from `(modality, cost)`.

---

## Worked example — Eldritch Knight, War Magic, True Strike (every axis decouples)

War Magic (2024) lets you replace one attack of the Attack action with casting a
cantrip. True Strike (2024) is a cantrip that makes one **weapon** attack with the
casting weapon, using your spellcasting mod (INT), damage = the weapon's type *or*
radiant (choice), plus a radiant rider at higher levels. So an EK who swings a
longsword then War-Magics True Strike maps as:

| | modality | cost | resolution | origin | range | damage_type | stat |
|---|---|---|---|---|---|---|---|
| *Take the Attack action* | Attack | action | — | — | — | — | — |
| Swing 1 — longsword | Attack | action | attack_roll | weapon | melee | slashing | STR |
| Swing 2 — cast True Strike (the hit) | **Magic** | **none** | attack_roll | **weapon** | melee | slashing *or* radiant | INT |
| ↳ True Strike's radiant rider | Magic | none | (rider) | **spell** | — | radiant | — |

Lessons it pins:
- **modality ⊥ resolution** (Magic, yet attack_roll) and **modality ⊥ origin**
  (Magic-modality, yet weapon-origin — True Strike attacks *with* the weapon).
- **cost ⊥ modality** — Magic at `cost=none` (War Magic slots the cast into an
  Attack-action swing; casting True Strike *normally* would be Magic at
  `cost=action`).
- **origin ⊥ damage_type** — if the EK renders the weapon damage as radiant, that
  is a *weapon-origin* hit dealing radiant, which is **not** spell damage (not
  fuelable). Only the rider (`origin=spell`) is.
- **Engine gotcha:** swing 2 uses the spell-attack stat (INT) but is `origin=weapon`
  — the back-compat `derive_origin` would mis-infer `feature`, so the call site
  must set `origin="weapon"` explicitly. The legacy flags can't represent
  "weapon attack with a spell stat" (the Shillelagh family) — the reason we want a
  first-class axis.

---

## Provenance — "made as part of the Attack action" (descriptor, deferred build)

GWM's +PB damage, and Searing-Arc-style gates, apply to attacks **made as part of
the Attack action**. The True Strike/GWM stress test (session 25, web-verified
against the 2024 RAW + community consensus) shows this is a **provenance** property
— *which action granted the attack* — and that it is **not** the sub-attack's
modality and **not** derivable from `(modality, cost)`:

- GWM's +PB applies to **both** EK swings above, including the War-Magic True
  Strike (`modality=Magic, cost=none`) — because War Magic casts the cantrip "as
  part of the Attack action".
- It does **not** apply to a normally-cast True Strike (Magic action), nor to a
  bonus-action attack or an opportunity attack.
- It already isn't `is_attack_action(modality, cost)`: a plain Extra Attack
  follow-up is `cost=none` yet GWM applies to it.

Model: a per-attack flag `part_of_attack_action: bool`, set by whatever GRANTS the
attack (the Attack action sets it True on every swing it grants, incl. a War-Magic
replacement; BA / reaction / standalone-cast attacks leave it False). GWM reads it;
the turn-level "did you take the Attack action this turn?" gate is the OR of it over
the turn. Generalises later to a "granting action" tag. **Build when a GWM /
War-Magic build forces it** — no current build uses it.

## Weapon properties are NOT taxonomy axes

GWM's gate is also "a **Heavy** weapon" — excluding an off-hand dagger (Light) and,
via `origin`, Shocking Grasp (spell) and an unarmed strike. The **origin** part is
taxonomy and already does that work; **Heavy / Light / Finesse / Reach / Thrown /
Versatile** are properties of the WEAPON (equipment data), not a classification of
the action. Keep them on the weapon-data layer (alongside `weapon_mastery`) and
compose GWM's gate as `part_of_attack_action AND origin==weapon AND
weapon.has("Heavy") AND hit`. Build the weapon-property data when a build forces it.

---

## Deferred (named, not yet built)

- **`magical` boolean** distinct from origin. Under the 2024 rules monsters no
  longer resist "nonmagical" B/P/S (resistances are flat by damage type — verified
  2026-06-21), so magical-vs-nonmagical earns nothing for resistance math today.
  Add only when a feature forces it.
- **Splitting `feature` origin** into magical-feature vs nonmagical-feature (Sea
  druid's Wrath of the Sea vs Phantom rogue's Wails from the Grave). Irrelevant to
  the near-term builds.
- **The non-combat modalities** (Influence / Study / Search / Hide-as-skill) are
  named for closure but given no resolution machinery.
- **The `part_of_attack_action` provenance flag** (see the Provenance section) —
  the gate GWM / Searing-Arc features actually need. Build when a GWM / War-Magic
  build forces it.
- **Weapon-property data** (Heavy / Light / Finesse / Reach / Thrown / Versatile)
  on the weapon-data layer — NOT a taxonomy axis. Build when a build (e.g. GWM)
  forces it.
- **Runtime gate migration** (see below).

---

## Migration status & plan

**DONE (session 25) — backward-compatible refactor, 495 prior tests byte-identical:**
- `src/taxonomy.py` — the closed vocabularies + Literal types + pure predicates +
  back-compat derivation helpers (`derive_resolution`, `derive_origin`).
- `Choice` gained `modality` / `resolution` / `origin` / `range_`, filled in
  `__post_init__` from the legacy flags when not set (so every existing Choice
  carries correct taxonomy values, behaviour unchanged); an explicit `origin`
  keeps the `is_spell` / `is_unarmed` aliases consistent.
- `AttackRollEvent` / `DamageEvent` / `SaveDamageEvent` gained `origin`
  (+ `range_` on the attack event); `HitContext` / `IncomingAttackContext` gained
  `origin` / `range_` (+ the `is_physical` / `is_spell_origin` properties).
  Threaded Choice → events → contexts in `scheduler.py` / `verbs.py`.
- `is_spell` / `is_unarmed` remain as **transitional aliases** for
  `origin=="spell"` / `origin=="unarmed"`, slated for removal once every reader
  uses `origin`.
- Tests: `tests/test_taxonomy.py` (+14) pins the derivation + threading.

**NOT YET DONE (deliberate follow-ups — each its own validated change, because
each can subtly change behaviour and so is NOT byte-identical):**
1. **Migrate the runtime gates** to the new vocabulary:
   - FoM's `not ctx.is_spell` → `ctx.is_physical and ctx.range_ == "melee"`
     (this also FIXES a latent edge: under `not is_spell`, a `feature`-origin or
     ranged attack would wrongly satisfy the gate).
   - Primal Strike's `not is_spell and (not is_unarmed or toggle)` → origin-based.
   - Searing Arc's policy-local "weapon Attack action" boolean → derive from the
     emitted Choice's `is_attack_action(modality, cost)`.
2. **Set `modality` / `origin` / `range_` explicitly at the build call sites**
   (war_angel / starfire_scion / silvertail / enemy) rather than relying on
   derivation — especially `range_="ranged"` on Guiding Bolt / Archer and
   `modality="Use Ability"` on non-magical feature casts.
3. **Exercise the range gate with a real ranged attacker** (the first thing the
   taxonomy unlocks: melee-only thorns/Parry correctly NOT firing on a ranged hit).
4. **Remove the `is_spell` / `is_unarmed` transitional aliases** once 1–2 land.
