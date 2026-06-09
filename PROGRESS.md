# PROGRESS — live status & next steps

> A running handoff note so any session (or the user) can see where things stand
> and what comes next. Update this as milestones land. For project orientation and
> locked architectural decisions, see `CLAUDE.md`.

---

## Done

- **Design contract captured** — `design/design.md` (entity model, simulated-day
  structure, verb engine spec, content schema, open decisions).
- **Ability schema locked & committed** — `design/ability_schema.md`. Three-layer
  structure (trigger/effect/cost), closed ~19-verb set, trigger/predicate
  vocabulary, modifier hooks, damage-resolution phase order, status & magic-item
  formats.
- **Schema validated against the corpus** — coverage-tested against the 9 canonical
  examples, the hard psionic crit-fisher stack, and a 7-build stress test (builds
  24, 25, 26, 36, 43, 44, 45). Verb set confirmed closed; 8 trigger/predicate
  vocabulary additions recorded. Zero new engine verbs forced.
- **Example content written & committed** — `content/abilities/`:
  `core_examples.yaml`, `psionic_critfisher.yaml`, `stress_test_patterns.yaml`.
- **Engine skeleton built & tested** — `src/` + `tests/`, 29 tests all green.
  One fighter swings a longsword at an infinite-HP dummy for N rounds; seeded
  dice, reproducible output, damage number comes out. All core architectural
  invariants are live in code (see `CLAUDE.md` §"Engine implementation").
- **Repo pushed to GitHub** — https://github.com/cas3ymau3/dnd-combat-sim
- **Extra Attack** — `ExtraAttackPolicy` in `src/policy.py`; supports N extra
  attacks and an optional interleaved bonus-action attack. 13 new tests, all green.
- **Scripted enemy + threshold HP model** — `ScriptedEnemyPolicy` (melee_aggressive
  archetype, stat-block dict interface). Entity HP now tracks into negatives; both
  sides act for the full `max_rounds` regardless of HP. `Scheduler.damage_received`
  exposes per-entity incoming damage per round. 20 new tests, all green.
- **Resource tracking + DayRunner** — `src/resources.py`: `ResourcePool` /
  `ResourceEntry` with full/partial SR restore and LR restore. `src/day_runner.py`:
  `DayRunner` orchestrates 4 combats, non-deterministic SR placement, LR at day
  start, `between_combats` hook for out-of-combat actions (e.g. Prayer of Healing).
  `Choice.resource_cost` wired into scheduler validation/consumption. Entity carries
  a `ResourcePool`. 44 new tests, all green (102 total).
- **Advantage/disadvantage + status flags + weapon mastery (sap/vex)** —
  `src/statuses.py`: `StatusSet` with tick-based expiry keyed on (round, turn_index),
  swept for all entities at each TurnStartEvent. `roll_d20()` honors RAW adv/disadv
  cancellation. `resolve_attack_roll` reads/consumes sapped & vex_advantage; masteries
  apply on hit (sap → target disadvantage until applier's next turn; vex → applier
  advantage vs that target). `Choice` gains `extra_masteries` (additive) and
  `mastery_override` (replace); `AttackRollEvent.masteries` built by scheduler. Entity
  carries a `StatusSet`. 32 new tests, all green (134 total).

---

## Current phase: fidelity build-up → War Angel validation

The skeleton proved the architecture end-to-end; we then thickened it through the
engine prerequisites for the War Angel validation. **All engine prerequisites are
now done.** What remains is the character itself (policy + build plan) and the
validation run — not more engine primitives.

Engine prerequisites, in the order we built them:
- ~~Extra Attack~~ ✓  — `ExtraAttackPolicy` (N extra attacks + optional interleaved BA).
- ~~Scripted enemy + threshold HP~~ ✓  — `ScriptedEnemyPolicy`; HP tracks into negatives,
  both sides always act the full round count.
- ~~Resource tracking + DayRunner~~ ✓  — `ResourcePool`, full/partial SR + LR restore,
  4-combat day with non-deterministic SR placement, `between_combats` hook for PoH.
- ~~Advantage/disadvantage + statuses + weapon mastery (sap/vex)~~ ✓  — `StatusSet`,
  `roll_d20`, sap/vex applied on hit and consumed on the holder's next roll.

### NEXT STEP — War Angel level 8 (Phase C: brutality)

**Levels 1–7 are DONE & VALIDATED** (Phases A + B; see the dated entries below).
The next level is **8 = Phase C (brutality / gladiator subclass)** — the first level
where attack *order* starts to matter (vex chaining), bringing:
- **Brutality** (xCHA/SR resource): `bleed` = add sap + CHA-mod damage; `bluff` = add
  vex + advantage on the next save (the save-advantage side is DPR-irrelevant until
  L13, so model only the vex effect now); applied via the existing `extra_masteries`
  on a Choice / the on-hit decision point.
- **Guided-strike prioritization** finally earns its keep: prefer high-value
  (true-strike / "setup") misses over plain swings (deferred from L5–7 deliberately).
- The build guide's L8 note is the longest in the doc — work the policy up in readable
  form against that prose BEFORE coding, per the standing process.
Still deferred past here: the on-hit *crit-redirect* / smite-on-crit selection (lands
at L10 with Extra Attack), and all defensive machinery (saves, frightened,
concentration, bless) → Phase D (L11–13).

---

#### Original scope note — War Angel character policy + build plan (levels 1–13)

This is the first concrete character. Two pieces:

1. **Build plan** (data): the character's stat block at each level 1–13 — attack
   bonus, damage dice/bonus, AC, HP, spell slots and limited-use resources, weapon
   mastery, and which abilities are online. Derived from
   `design/build-guides/38_the_war_angel.txt` (the detailed level-by-level notes,
   including the per-level simulated DPR targets to validate against) and
   `reference/r-prototype/war_angel_*` (the prototype's structure).

2. **Daily plan / policy** (Python): the `decide()` logic implementing the build's
   per-round action economy — e.g. at lvl 1 a single rapier (vex) attack + 1 AoO
   per combat; by lvl 5+ war priest BA, true-strike, guided strike, wrathful smite;
   by lvl 8+ brutality::bluff. The build guide spells out the exact decision rules
   per level and per combat (see the lvl-08 and lvl-10 notes especially).

**Validation framing (agreed):**
- Levels 1–4 are mechanically simple → expect a CLOSE match to the build guide's
  simulated DPR (1: 8.32, 2: 7.39, 3: 7.39, 4: 6.81). A miss here means a basic
  attack-math bug — find it before layering on complexity.
- Levels 5–13 → SOFT validation. Same ballpark (±~10%), not exact. The R prototype
  and build-guide numbers are a compass, not ground truth (policy logic differs).
- Build the simplest level (1) first and climb the ladder.

**Known deferral inside this scope:** Flourish Parry (lvl 14) needs the reaction /
`intercept_event` decision point, which we have NOT built — fine, validation stops
at level 13. See "Open threads" for the full deferred list (TurnEndEvent, saves,
spell-aggressive enemy, weapon slot, light/nick, etc.).

**Agreed build sequence (phased — discussed & locked).** The organizing principle:
*everything that only affects INCOMING damage is deferred to level 13*, because
that's the first level where incoming damage loops back into our own DPR (via
concentration on bless). Levels 1–12 are pure offense and need none of the
defensive machinery.

- **Phase B — level 7. ✓ DONE & VALIDATED. Phase B (levels 5–7) complete.** Result:
  **21.04 DPR vs. target 21.26, −1.0%** (20k days, soft ±10%). **No new engine
  primitives** — action surge is just a `Choice(cost="none", resource_cost=
  {"action_surge": 1})` (one plain extra weapon attack; 2024 forbids the Magic action on
  the surged action, so no True Strike rider), fired greedily on turn 1 while a charge
  remains. Data only: `action_surge` resource (1/full → 3/day) + enemy AC 16 (↑ from 15).
  **Also switched Guided Strike to greedy** (dropped the vestigial "≤1 in combat 1" cap):
  Channel Divinity (max 2, +1 SR, +1 PoH) comes out to ~4 uses/day either way, so the cap
  was ~EV-neutral, and rescuing earlier (combat 1, where magic weapon is most likely up)
  is marginally better. The genuine guided-strike optimization — preferring high-value
  (true-strike / setup) misses — is deferred to L8 where attack-value gaps widen. 1 new
  test + greedy-cap test rewritten.

- **Phase B — level 6. ✓ DONE & VALIDATED.** Result: **20.80 DPR vs. target 21.03,
  −1.1%** (20k days, soft ±10%); L1–5 unchanged. Built the **on-hit decision point**
  (`Policy.on_hit` + `HitContext`/`HitResponse`, mediated by `Scheduler._make_hit_decider`,
  consulted in `resolve_attack_roll`'s hit branch before the DamageEvent — returned dice
  fold in and double on crit) and **hung the current turn's action economy on the
  scheduler** (`self._turn_economy`) so a mid-turn smite can read/consume the bonus action
  during resolution. War Angel L6 adds wrathful smite via `on_hit` (war-priest-first,
  smite-fills-the-BA, slot priority pact → free cast → cleric L1, gated off AoOs), the
  pact/free-cast/cleric-L1 resources, and magic_weapon_casts_per_day=2. 7 new tests, 158
  total green. Decisions that drove this design are recorded below.

- **Phase B — levels 5–7. ✓ DONE & VALIDATED.** Final DPR vs. target (30k days,
  soft ±10%): **L5 16.55/16.73 (−1.1%), L6 20.88/21.03 (−0.7%), L7 21.01/21.26
  (−1.2%)**; L1–4 unchanged and still exact. **159 tests green.** All offense
  primitives in place: `extra_damage_dice` (true-strike 1d6, doubles on crit); the
  **on-miss decision point** (guided strike) and the **on-hit decision point**
  (wrathful smite), both mediated by scheduler closures so resolution never calls the
  policy directly; **per-turn action economy hung on the scheduler** (`_turn_economy`)
  so a mid-turn smite can read/consume the bonus action at resolution time; the
  **day-clock duration-buff model** (`DurationBuffTracker` + `DayRunner.before_combat`)
  for magic weapon; **action surge** (greedy, turn-1, plain swing — no Magic action /
  true-strike allowed on the surged action per 2024 RAW). Two policy decisions settled
  this phase: (a) **war priest is the unconditional top bonus action**, smite only fills
  the BA when no charge remains (war-priest EV ≥ smite in every case — see L6 entry);
  (b) **guided strike is greedy** — the old "≤1 in combat 1" cap was vestigial
  (~EV-neutral, ~4 CD/day either way) and was dropped; the high-value-miss prioritization
  it gestured at is deferred to L8. Per-level data + policy in `src/builds/war_angel.py`
  (`LEVELS` 1–7, `WarAngelPolicy.decide/on_miss/on_hit`, `WarAngelDailyPlan`,
  `make_day_runner`); `make_war_angel(8)` raises (next level). The detailed L6 rationale
  is kept below as the design record.

- **Phase B — level 6 design decisions (locked & implemented).**
  - *Wrathful smite is POST-HIT, non-concentration (2024 RAW).* It is cast as a bonus
    action immediately AFTER a melee hit (like Divine Smite), adding 1d6 (doubled on a
    crit). So it is modeled as an **on-hit decision point** (`Policy.on_hit` +
    `HitContext`/`HitResponse`, the mirror of `on_miss`), NOT the "pending status applied
    before the attack" idea floated earlier — that was a misreading of the spell.
  - *EV result: war priest dominates wrathful smite.* A fresh war-priest swing is worth
    7.05 DPR (8.28 with magic weapon) vs. smite's 3.5 (normal hit) or 7.0 (crit). Because
    the war-priest EV already prices in its miss chance, it is ≥ smite in EVERY case,
    including a crit, and ≫ with magic weapon. So the build-guide intuition was right.
    **Policy: war priest is the unconditional top BA priority; wrathful smite only fills
    the BA on turns war priest is depleted, riding whatever hit lands ON OUR OWN TURN**
    (slot priority pact → free cast → cleric L1). The guide's "smite the crit *instead
    of* war priest" redirect is EV-negative and dropped.
  - *General rule — bonus actions only on your own turn (2024).* A BA can only be taken
    on the turn you take an action, so a smite (or any BA response) can NEVER ride a
    reaction/AoO that resolves on an enemy's turn. Our model collapses the AoO onto the
    character's own turn, so the per-turn BA economy can't distinguish it — the **policy**
    must gate it: `on_hit` returns None when `ctx.cost == "reaction"`. This rule holds for
    all future BA-on-hit effects (Divine Smite, brutality riders, etc.).
  - *This makes the policy greedy and rest-timing-agnostic.* Spending war priest whenever
    a charge exists maximizes the daily count (9 across LR + PoH + SR) with no hardcoded
    per-combat logic and no dependence on when the SR/PoH fall. Husbanding war priest into
    magic-weapon-on combats is worth ~0.2 DPR and is SKIPPED (revisit only if L6 validates
    low). The policy doesn't even need to read MW-active — MW just boosts numbers via the
    modifier.
  - *Magic weapon stays on the explicit day-clock model* (NOT the prototype's 50% coin):
    2 casts/day at L6 (3 L2 slots = 1 PoH + 2 MW), cast before combat 1, recast on lapse
    while an earmarked slot remains.
  - *Engine work required:* the `on_hit` decision point (consulted in
    `resolve_attack_roll`'s hit branch before the DamageEvent is built; returns extra dice
    that fold in and double on crit), and **making the current turn's action economy
    visible at resolution time** (hang it on the scheduler) so a mid-turn smite can read
    and consume the bonus action. Both generalize to L8 brutality-on-hit, L10
    smite-on-crit, and any Divine-Smite-style build.
  - L6 stats: attack +7, damage 1d8+6, AC 15, true-strike rider 1d6. Target DPR 21.03.

- **Phase B — level 5 sub-staged validation (detail).** B1
  (true-strike rider + war priest + magic weapon, no guided strike) → 13.65 DPR, which
  isolated and confirmed the attack math. B2 (added guided strike) → **16.48 DPR vs.
  target 16.73, −1.5%** (40k days, soft ±10%); L1–4 unchanged. New engine primitives,
  all reusable downstream: `extra_damage_dice` on Choice/AttackRollEvent/DamageEvent
  (true-strike's 1d6, doubles on crit); the **first post-roll decision point** —
  `Policy.on_miss` + `MissContext`/`MissResponse`, mediated by
  `Scheduler._make_miss_decider` so resolution never calls the policy directly (reused
  later for smite-on-hit / brutality-on-hit); the **day-clock duration-buff model** —
  `DurationBuffTracker` + `DayRunner.before_combat` hook (magic weapon, 60-min,
  non-conc.); resource pools (war_priest 3/full, channel_divinity 2/+1-SR) + the
  `WarAngelDailyPlan` (magic-weapon maintenance + Prayer-of-Healing recharge). 6 new
  tests, 151 total green. See `make_day_runner` for the full assembly.

- **Phase A — levels 1–4 (NO engine changes). ✓ DONE & VALIDATED.** Build data +
  `decide()` policy + DPR harness. Results vs. target (50k days): L1 8.310/8.32,
  L2 7.410/7.39, L3 7.410/7.39, L4 6.821/6.81 — all within ~0.3% and within the
  Monte Carlo CI. Lives in `src/builds/war_angel.py` (`LEVELS` data, `make_war_angel`,
  `make_training_dummy`, `WarAngelPolicy`) and `src/validation.py` (`run_level`,
  `python -m src.validation`). Engine touch-ups made: optional `Policy.on_combat_start`
  hook (generalises to enemy-archetype selection), `StatusSet.clear()` + clearing
  tick-statuses at each combat boundary (fixed a cross-combat vex leak), DayRunner
  calls the hook. 11 new tests (`tests/test_war_angel.py`), 145 total green.
- **Phase B — levels 5–7 (offense primitives). ✓ DONE & VALIDATED** (see the dated
  entry below for final numbers). `extra_damage_dice` on `Choice`
  (true-strike cantrip dice); wrathful-smite *damage* via an **on-hit decision point**
  (post-hit, non-concentration per 2024 RAW — the frightened/save half is deferred, see
  Open threads); war priest (resource); guided strike (**on-miss decision point** — see
  below); action surge; random-slot AoO + `on_combat_start(n, rng)` policy hook;
  magic-weapon via the day-clock duration model (see below). Soft ±10%. **Level-5
  sub-staged validation:** B1 = true-strike + war priest + magic weapon, *no* guided
  strike (sanity-check attack math below 16.73); B2 = add guided strike, re-validate to
  16.73. (Level 5 ✓ done; level 6 design locked, see the dated entry above.)

  *Guided strike = the first post-roll decision point.* The scheduler, on one of the
  actor's attacks **missing**, opens a decision point and consults the policy
  (`on_miss`-style hook) before finalizing the roll; the policy may spend a Channel
  Divinity charge to add +10 if it flips the miss to a hit (subject to per-combat
  caps; not on AoOs at L5). This is the CLAUDE.md §7 "consulted mid-turn after rolls
  resolve" case, and it's reused later for wrathful-smite-on-hit, brutality-on-hit,
  and smite-on-crit — so build it carefully here.

  *Out-of-combat buffs via the DAY CLOCK (decided — magic weapon is the first case).*
  The sim has two clocks: the **combat clock** (rounds/ticks inside a Scheduler) and
  the **day clock** (minutes 0–960, on which DayRunner already samples combat start
  times). Out-of-combat buff *durations* live on the day clock. We model magic weapon
  (2024: **non-concentration**, 60 min) explicitly instead of a per-level uptime
  fraction: a small duration tracker ("buff cast at minute M, lasts D") plus a new
  **`before_combat` hook on DayRunner** (the mirror of `between_combats`) that syncs
  the entity's modifiers to whatever buffs are active at this combat's start-minute
  (push `magic_weapon` +1/+1 when active, pop when lapsed). A buff is treated as
  covering a combat if active at that combat's **start-minute** (the ~1-min combat
  length is immaterial against 60). The cast SCHEDULE is stated explicitly in the
  *build* (not a hidden engine rule): cast before combat 1; before combat N>1 if magic
  weapon is inactive AND an earmarked level-2 slot remains. This deletes the hand-fit
  1/3 (L5) / 1/2 (L6) / 3/4 (L12–13) uptimes — they now emerge from slots × duration ×
  sampled combat spacing. Note the emergent uptime is *correlated* across nearby
  combats (more faithful than the prototype's independent per-combat coin), so small
  divergence from prototype DPR is expected, not a bug.
- **Phase C — levels 8–10 (brutality + weapon switch).** Brutality: vex via the
  existing `extra_masteries`; bleed = sap + CHA-mod damage. Weapon switch via
  `base_stats` at the level transition. The bluff *save-advantage* effect is
  DPR-irrelevant until level 13, so model only its vex effect here. Soft ±10%.
- **Phase D — levels 11–13 (the defensive bundle).** Saves (`SavingThrowEvent`,
  spell save DC), the frightened condition, concentration-as-a-save, and
  **rolled-dice modifiers** (a `Modifier` gains an optional `dice` field; folded only
  on a resolution-only path — e.g. `entity.roll_bonus(stat, tick, rng)` — never by
  the pure `stat()` the policy reads, so `decide()` stays dice-free) → bless,
  war god's blessing (non-concentration shield of faith). Soft ±10%, stop at 13.

**Policy process (agreed).** For each level we read the build-guide prose and the
prototype policy as a statement of *intent*, then write readable Python and check it
together against that prose before moving on. The prototype's R control flow is not
ported verbatim — its value is the DPR target, not its structure.

---

## Enemy policy — decisions recorded

1. **Same interface as character policy.** Both implement
   `Policy.decide(snapshot) → list[Choice]`. Scheduler loop is unchanged.

2. **`ScriptedEnemyPolicy(archetype, stats_by_level)`** — behavior is a
   constructor param, not a subclass. Keeps the door open to sampling archetypes
   across Monte Carlo runs (enemy behavioral variance as a first-class concern).

3. **Stats from CR-scaling table.** `reference/data/monster_ac_and_saves_by_level.csv`
   is the source of truth for AC, attack bonus, save DCs, damage by CR/level.
   Enemy `Entity` is constructed from a row matched to character level at sim setup.

4. **Behavioral axis for later:** melee-stays-close vs. ranged-kiter. Affects
   opportunity attacks, forced movement, DPR for position-sensitive builds
   (Sentinel fighter cares; ranged Ranger largely does not).

---

## Open threads / deferred decisions

- **Initiative / turn order** — currently list order (character first, enemy
  second). Real sims need rolled or fixed initiative. Low priority until we have
  multiple enemy archetypes and need to study action-order sensitivity.

- **Formal weapon slot** — deferred. For now a weapon's mastery is declared via
  `base_stats["weapon_mastery"]`, and weapon switches (e.g. War Angel longsword →
  rapier at lvl 16) are modeled by the build plan updating base_stats at the level
  transition. Build a proper `Weapon` dataclass (name, damage_dice, mastery,
  `properties: list[str]`) when the first **dual-wielder** forces simultaneous
  multi-weapon tracking. Not needed for War Angel validation.

- **Light weapons / two-weapon fighting / nick mastery** — architecture is believed
  sufficient as-is: the light-weapon BA second attack is just
  `Choice(cost="bonus_action")`; nick mastery moves it to `cost="none"` (structurally
  identical to Extra Attack). No engine change anticipated, but **verify against a
  real dual-wield build** before relying on it. War Angel uses no light/nick weapons,
  so deferred.

- **Weapon mastery — remaining properties** — sap and vex are built (the only two
  War Angel needs). topple, slow, push, nick, cleave, graze deferred until a build
  needs them. `mastery_override` (Tactical Master, lvl 16) field stubbed on `Choice`
  but not yet consumed by the scheduler.

- **`TurnEndEvent` / end-of-turn trigger point** — the scheduler currently emits
  only `TurnStartEvent`, and status expiry is swept lazily at each turn start.
  This is **provably correct for the current statuses** (sap, vex) because each is
  read only during its holder's own turn, so lazy expiry is never observable. It
  **breaks** for: (a) statuses that gate reactions (e.g. stunned — a reaction could
  fire in the gap between true end-of-turn expiry and the next start-of-turn sweep,
  wrongly seeing the status as still active); (b) effects that *proc* on turn end
  rather than expire (e.g. spirit guardians dealing damage when an entity ends its
  turn in the emanation — must fire at that turn-end tick with correct attribution).
  Both need an explicit `TurnEndEvent` as a symmetric counterpart to `TurnStartEvent`.
  Deferred until the first end-of-turn proc or reaction-gating condition is modeled,
  so its shape is driven by a real case. Not needed for War Angel validation.

- **Concentration spells live on BOTH clocks (deferred to Phase D).** The day-clock
  duration model built in Phase B handles *non-concentration* out-of-combat buffs
  (magic weapon). Concentration spells are harder because they exist on both clocks
  simultaneously: a day-clock *duration cap* (bless 1 min, shield of faith 10 min —
  though War God's Blessing makes the cleric's shield of faith non-concentration) AND
  a combat-clock *concentration check* that can drop them mid-combat on a failed save
  when the caster takes damage. Phase B's duration tracker supplies the day-clock half
  and is reused as-is at Phase D; the combat-clock half (a concentration-check decision
  point keyed on incoming damage, plus the save machinery) is the new Phase D work.
  No Phase B rework anticipated.

- **Saving throws** — needed for spells and conditions. Deferred until the first
  save-based ability is modeled. **Decided (War Angel planning):** this lands in
  **Phase D (levels 11–13)**, bundled with the frightened condition, concentration,
  and rolled-dice modifiers (bless), because that's the first point where incoming
  damage feeds back into our own DPR via concentration. Will add `SavingThrowEvent`,
  a `spell_save_dc` stat on attackers, and save-bonus stats on defenders.

- **Wrathful smite — frightened/save half (deferred to Phase D).** Wrathful smite
  also forces a WIS save vs. our spell DC; on a failure the target is frightened
  (disadvantage on its attacks; can't move toward us). **Decided:** we build only the
  *damage* half (1d6 on hit, added via the on-hit decision point) in Phase B, and defer
  the save + frightened condition to Phase D. Rationale: in the threshold-HP model frightened changes only
  *incoming* damage, which does not affect our DPR until level 13, where it loops back
  *second-order* (fewer enemy hits → fewer concentration checks → higher bless uptime).
  Building a save system at level 6 would change no DPR number before level 13, and
  saves are needed at 13 anyway (concentration *is* a save), so they bundle cleanly.

- **Attacks of opportunity & spatial representation.** The engine has **no spatial
  model today** (no positions, distance, reach, or movement). **Decided (War Angel
  planning):** do NOT build one now — instead match the prototype's simplification of
  **one AoO per combat**, with its timing drawn at `on_combat_start` from the seeded
  RNG (random slot: before turn 1, between turns, or after turn 4), not smeared as an
  expected-value addition. Rationale: a spatial subsystem (positions, movement, threat
  zones, OA triggers, enemy movement policy) is large and nothing in the War Angel's
  DPR targets depends on it; the build guide itself uses the once-per-combat
  assumption. Build spatial when the first *position-sensitive* build needs it (e.g.
  a Sentinel reach-fisher or ranged kiter) so its shape is driven by a real case —
  same forcing-function philosophy as the deferred `TurnEndEvent`.
  - **Knock-on for the "no smite on AoO" gate (flagged for future work).** Because we
    currently collapse the once-per-combat AoO onto the character's own turn, the policy
    hard-gates bonus-action responses off reaction-cost attacks (`on_hit` returns None
    when `ctx.cost == "reaction"`). Once AoOs arise *organically* from spatial dynamics
    they will resolve on the *enemy's* actual turn, and the action-economy model itself
    should enforce "no bonus action off-turn" — at which point this policy-level gate
    should be revisited and likely replaced by an engine-level rule. Do NOT treat the
    current `cost == "reaction"` check as permanent.

- **Spell-aggressive enemy archetype** — enemies that target saving throws rather
  than making attack rolls. Required for full defensive assessment (not just AC,
  but also save proficiency). Deferred after `melee_aggressive` is validated.
  Longer-term goal: run across a distribution of archetypes and aggregate, rather
  than a single archetype.

- **Monster stat table (CSV)** — `reference/data/monster_ac_and_saves_by_level.csv`
  is read-only reference for now. Before using it as a live input, it needs
  enrichment: number of attacks per CR, damage-per-hit, enemy HP distribution from
  MM analysis. `ScriptedEnemyPolicy` already accepts a dict interface so swapping
  in a CSV row later requires no policy changes.

- **Grapple / shove / unarmed strike variants** — some builds (e.g. Cursed Kensei)
  choose attack flavor per-swing. Extend `Choice` with an optional `attack_kind`
  field when the first such build is modeled. Grappler-feat compound effects
  (damage + condition on same hit) belong in an `on_hit` subscriber.

- **War Angel validation** — treat the R prototype as a soft compass, not ground
  truth. Per-hit damage math (smite dice, wrathful smite) should be near-exact.
  DPR totals may diverge due to policy differences and hit-rate modeling; ±10% is
  acceptable noise, not a regression.

- **Finite HP as a toggle** — considered and deferred. The threshold model (HP
  tracks into negatives, entities always act) is the default. If variable-length
  encounters become a research question, revisit then — don't add the toggle
  preemptively.
