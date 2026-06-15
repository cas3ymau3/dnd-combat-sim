# PROGRESS — live status & next steps

> A running handoff note so any session (or the user) can see where things stand
> and what comes next. Update this as milestones land. For project orientation and
> locked architectural decisions, see `CLAUDE.md`.

---

## Session startup & config ritual (do this first, every session)

At the start of every session, before diving into the work:

1. **Review upcoming tasks.** Read the **NEXT STEP** below plus the phase plan, and
   form a view of what's likely in scope.
2. **Recommend MCP toggles for agility, with how-to.** Identify which MCP connectors
   are irrelevant to the likely tasks and recommend the user disable them for the
   session. For this Python/CLI project that's typically all of: **computer-use,
   Claude-in-Chrome, Claude_Preview, scheduled-tasks, mcp-registry, Google Drive.**
   Tell the user *how*: these are **account/app-level connectors, NOT file-config** —
   Claude CANNOT disable them by editing settings (verified: no `.mcp.json`, empty
   `mcpServers`/`disabledMcpjsonServers`). The user flips them via `/mcp` in-session,
   or the Claude app → Settings → Connectors. Claude proposes the list + steps; the
   user toggles.
   - **Confirmed working on this machine (2026-06-10):** `/mcp` did NOT expose a
     disable control — use the app. Path: **Claude app → Settings → Connectors**, and
     check the **Customize** tab (some connectors live there). Only **Google Drive**
     (action: *Disconnect*) and **Claude-in-Chrome** (action: *Disable*) appeared as
     toggleable; **computer-use, Claude_Preview, scheduled-tasks, mcp-registry did NOT
     surface** as options (platform-managed — don't over-promise their removal).
3. **Ask the user to define session scope + a stopping point.** Get an explicit
   milestone/stopping point for the session. Record which connectors the user
   disabled in the "Currently disabled" line below. As the session nears that
   stopping point — or on end-of-session signals ("let's end here", "good place to
   stop"), or when Claude recognizes the milestone is complete — **prompt the user to
   re-enable** the disabled connectors, and clear the line.

## Session close-out ritual (do this last, every session)

When wrapping up a session (the milestone is complete, or the user signals an end):

1. **Land the work.** Make sure PROGRESS.md is updated (Done entry + the NEXT-STEP
   markers flipped), tests are green, and everything is committed and pushed. Confirm
   before merging to `main` / deleting branches (per CLAUDE.md git autonomy).
2. **Re-enable MCP connectors.** Prompt the user to re-enable anything in the
   "Currently disabled" line, then clear it.
3. **ALWAYS end with a copyable next-session starting prompt.** The last thing every
   session produces is a ready-to-paste prompt for the *next* session — fenced as a
   copyable block, written in the imperative to the next Claude. It must: name the
   exact next task (the NEXT-STEP item), point at the files/sections to re-read first
   (PROGRESS Done entries, the relevant `src/`/`content/` files, schema sections),
   recall any scoping decisions already made or still open, restate the validation
   framing, and remind it to run the startup ritual (MCP toggles + scope/stopping
   point) BEFORE coding. Mirror the style of the prompt that started *this* session.
   This is the project's handoff mechanism — never skip it.

## Per-feature ritual (when building a new game mechanic)

Whenever a feature introduces a new game mechanic (a new ability, spell, attack
type, condition, resource, …):

1. **Verify the rules text FIRST — do NOT model from memory.** Before interpreting
   a mechanic, look up its ACTUAL language: the build-guide section AND/OR the web
   (official 2024 rules). Confirm the reading, and cite the source (guide line /
   URL) in the code or commit. (Fueled Spellfire, session 6: the guide's "expend
   up to 2 Hit Dice and add the total" + its worked `4d6+2d8 (23)` example
   confirmed the rider adds N d8 with NO ability modifier — easy to get wrong from
   memory.)
2. **Reflect after building — STOP and ask.** Once the feature is built and green,
   pause and ask the user whether building it surfaced any open questions OR any
   updates to how we work (this ritual, the validation framing, the schema, the
   decision-record conventions). Capture the answers before moving on; process
   improvements compound and are cheapest to make while the context is fresh.

> **Currently disabled (re-enable before exit):** none reported. **Session scope
> (2026-06-15, session 8) — DONE:** wired **THREAD B at L9 + L10** (Extra Attack +
> martial-arts 1d8 + first Shillelagh) as pure DATA + POLICY — NO new engine
> primitive, as predicted. New **L9 LEVELS row** (Monk-5/Druid-4; stats identical to
> L10 — PB 4, WIS 19/+4; enemy AC 16 / DEX +2 from the monster CSV at cr==9; hit
> dice 9; Starry Form dropped in combat). **Extra Attack** = a 1→2 weapon-swing
> change in `decide()` (primary cost="action" + follow-up cost="none", the engine's
> standard shape). **Martial-arts die** → unarmed 1d6→1d8. **Shillelagh** = the
> per-attack override (#4): quarterstaff die → **1d10** (char L9-10 step of the
> 1d8/1d10/1d12/2d6 ladder, BAKED into the row — the `scaling: ladder` deliberately
> DODGED) + the **WIS option** (user-corrected: Shillelagh grants the OPTION, so the
> policy uses the HIGHER of WIS/DEX modifiers, defaulting to WIS on a tie — here
> WIS+4 > DEX+3). Cast as the **turn-1 BA** (modeled by withholding the turn-1 BA
> damage option; persists the combat). **L10 also upgraded**: its single quarterstaff
> → Extra Attack + Shillelagh + 1d8 unarmed. **331 tests green (+5).** L9 DPR 18.10
> (< 32 ceiling, > L5 12.61), L10 DPR 20.36 (< 36 ceiling, > L9); thread-B-on > off
> at the fixed L9 enemy (18.10 vs 12.95); Searing Arc still lifts L10 (20.34 vs
> 17.99). Touched the ATTACK-TAXONOMY flag (a weapon attack using a spellcasting
> stat) — reused `weapon_stat="spell_attack_bonus"` WITHOUT rebuilding vocabulary
> (typology stays deferred). MCP-toggle recommendation re-made.
>
> **Session scope (2026-06-13, session 7) — DONE:** wired **Searing Arc Strike at L10** (thread A,
> NO new engine primitive — pure data + policy on the ready primitive #3). Added
> the **L10 LEVELS row** (PB 4, WIS 19/+4, DC 16, enemy AC 16 / DEX +3 from the
> monster CSV at cr==10; L6–L9 SKIPPED — L5–L8 are identical on our side, L9's
> Extra Attack + Shillelagh are the separate martial thread B). Searing Arc Strike
> = a BA upcast **Burning Hands** (FIRE save-FOR-HALF, base 3d6 +1d6/slot resolved
> FROM DATA via `interpret_save_spell({"slot_level": 2})` → 4d6 at monk-6, FP cap
> ⌊monk/2⌋=3), gated on having taken a **weapon Attack action** (so a Guiding-Bolt
> spell turn does NOT enable it). New `focus_points` resource (6 at monk-6, refilled
> per combat in on_combat_start = Uncanny Metabolism). **The cross-check it
> validates:** Searing Arc is `is_spell=True` but `damage_type="fire"`, so Fueled
> Spellfire DECLINES it — proving the `damage_type` gate (not just `is_spell`) does
> real work. **326 tests green (+6).** L10 DPR 14.85 (> L5 12.59, < 28.0 ceiling);
> searing-arc-on > searing-arc-off at the fixed L10 enemy. MCP-toggle recommendation
> re-made (computer-use / Claude-in-Chrome / Claude_Preview / scheduled-tasks /
> mcp-registry / Google Drive).

---

## Done

- **THREAD B wired at L9 + L10 (Extra Attack + martial-arts 1d8 + first Shillelagh)
  — BUILT & VALIDATED (2026-06-15, session 8).** NO new engine primitive — pure
  DATA + POLICY (the Extra-Attack shape + the per-attack override #4 were already
  built). **331 tests green (+5).** Branch `feature/thread-b-extra-attack-shillelagh`.
  - **What it is** (guide 41:510-513, 526, 539, 545). Monk-5/Druid-4 (char L9): PB
    +4, martial-arts die → 1d8, **Extra Attack**, and the druid cantrip **Shillelagh**
    becomes the go-to (guide: "with extra attack in hand, shillelagh is now
    definitively the best way for us to deal damage"). Per the per-feature ritual the
    rules text was verified in the guide first: guide 41:545 `attack(x2):quarterstaff
    --> 2d8+2d10+2DEX+2WIS` confirms the Shillelagh quarterstaff is **1d10 + WIS**
    (the 2d8/2DEX is the flurry-of-blows unarmed pair we don't model).
  - **L9 LEVELS row** (PB 4, WIS 19/+4 — stats IDENTICAL to L10; enemy AC 16 / DEX
    save +2 live from `monster_ac_and_saves_by_level.csv` at cr==9; hit_dice 9 per
    guide 41:547). **L6-L8 still SKIPPED** (L5-L8 identical on our side). **Starry
    Form is DROPPED in combat from L9** (guide 41:539), so no archer/wild_shape and
    no focus_points here (Searing Arc is monk-6/L10).
  - **Extra Attack (monk-5).** A 1→2 weapon-swing change in `decide()`: the primary
    swing costs the action, the follow-up costs nothing (`cost="none"`) — the
    engine's standard Extra-Attack shape (cf. `ExtraAttackPolicy`). A Guiding-Bolt
    action is a spell and is correctly NOT doubled. `_extra_attacks` is a data-driven
    count (`extra_attack: True` on the row).
  - **Martial-arts die → 1d8.** Unarmed strike 1d6→1d8 at L9/L10 (quarterstaff was
    already 1d8 versatile). Fixed the stale L10 unarmed (1d6→1d8) too.
  - **Shillelagh (the headline).** Delivered via the per-attack override (#4), zero
    engine change. The quarterstaff die → **1d10** — the char L9-10 step of the
    2024 ladder (1d8/1d10/1d12/2d6) — **BAKED into the LEVELS row**, the data-driven
    `scaling: ladder` deliberately DODGED (see the "die-size scaling" flag).
    **User-corrected nuance (mid-session):** Shillelagh grants the *OPTION* to swing
    with the spellcasting (WIS) ability instead of the weapon's normal physical (DEX)
    stat — it is NOT an automatic override. So `_shillelagh_attack_choice` uses
    whichever ability **modifier is higher, defaulting to the spellcasting stat on a
    tie** (here WIS+4 > DEX+3 → WIS); the 1d10 die applies regardless of which stat
    wins. The comparison is kept explicit so the same data serves a future build
    whose physical stat is the higher one. Cast as the **turn-1 bonus action** (guide
    41:539), modeled by **withholding the turn-1 BA damage option** (the BA is spent
    on the cast) — pure policy-side, DPR-equivalent to consuming the BA, keeps
    `decide()` a pure read; the cantrip is flagged active for the combat in
    `on_combat_start` and then buffs every quarterstaff swing.
  - **L10 also upgraded.** Its single 1d8+3 quarterstaff (searing-arc axis in
    isolation) now carries Extra Attack + Shillelagh + 1d8 unarmed, sharing the L9
    martial bundle. The Searing Arc Attack-action gate still holds (the doubled
    quarterstaff IS a weapon Attack action); ceiling_dpr bumped 28→36.
  - **ATTACK-TAXONOMY touch-point (flagged, no change made).** Shillelagh is a
    *weapon attack that uses a spellcasting stat* — exactly the kind/action/economy
    conflation the ATTACK-TAXONOMY flag calls out (second concrete consumer after
    Searing Arc). We reused `weapon_stat="spell_attack_bonus"` as the numeric WIS
    to-hit WITHOUT rebuilding engine vocabulary; the first-class typology stays
    deferred (user-directed — discuss before any engine-vocabulary change).
  - **Validation (consistency/sanity — NOT number-matching).** `tests/
    test_starfire_scion.py` (+5): Extra Attack emits exactly action+none (a spell
    action is not doubled); the Shillelagh higher-modifier/tie-default logic (incl.
    the physical-stat-higher branch keeping the 1d10 die); unarmed 1d8 at L9/L10; the
    turn-1 BA-cast suppression (no BA round 1, BA ladder from round 2; L1 without
    Shillelagh never suppresses); L9 DPR a plausible fraction of the 32 ceiling
    (18.10); and a within-L9 ABLATION at the fixed enemy (thread-B-on 18.10 > off
    12.95, since L9/L10 don't share an enemy — L10 DEX save +3 vs L9 +2). L10 still
    20.36 (< 36; > L9), Searing Arc still lifts it (20.34 vs 17.99).
  - **Deferred (unchanged):** Elemental Adept fire (resistance bypass + 1→2 die
    high-grading); the data-driven die-size ladder; Flame Blade / Stunning Strike /
    Flurry of Blows; multi-enemy AoE; the attack-taxonomy typology.

- **Searing Arc Strike wired at L10 (thread A) — BUILT & VALIDATED (2026-06-13,
  session 7).** NO new engine primitive — pure DATA + POLICY on the already-built
  primitive #3 (upcast `increment` scaling) + the existing `searing_arc_strike`
  YAML. **326 tests green (+6).** Branch `feature/searing-arc-strike`.
  - **What it is** (guide 41, lines 561–563, 575). Sun-Soul Monk-6 (char L10):
    immediately after the **Attack action**, spend **2 FP** to cast **Burning Hands
    as a BA**; spend more FP to upcast, capped at **⌊monk level ÷ 2⌋** FP. At monk-6
    → max 3 FP → upcast to **slot 2 = 4d6**. Burning Hands = **DEX save FOR HALF**,
    type **fire**. (Verified against the guide per the per-feature ritual; the
    guide's 11.73 figure also folds in Elemental Adept fire high-grading — deferred.)
  - **L10 LEVELS row** (PB 4, WIS 19/+4, DC 16, enemy AC 16 / DEX-save +3 live from
    `monster_ac_and_saves_by_level.csv` at cr==10). **L6–L9 SKIPPED** (like L2/L3):
    L5–L8 are mechanically identical on our side (PB stays 3, WIS mod stays +4
    through L8 — only the enemy hardens), and **L9's Extra Attack + martial-arts-1d8
    + Shillelagh are the separate martial thread B** (deferred, with the user). So
    L10 here models the searing-arc/fire-gate axis ONLY — quarterstaff stays a
    single 1d8+3 attack, no Shillelagh. Thread B will later add Extra Attack +
    Shillelagh to both L9 and L10.
  - **Shape (all reused seams, zero engine change).** Searing Arc Strike is a
    `Choice(action_type="save_spell", on_save="half", damage_type="fire",
    is_spell=True)` — the SAME save-for-damage path Sacred Flame uses; its dice come
    FROM DATA via `interpret_save_spell(SEARING_ARC_STRIKE, {"slot_level": 2})` →
    (4,6) (primitive #3's `slot_level` upcast). Policy: `_searing_arc_choice()`;
    `_has_searing_arc` is the data-driven gate (level carries a `searing_arc_strike`
    block). FP cost (3) is the Choice's `resource_cost={"focus_points": 3}`; WHICH
    slot to spend (= how many FP) is policy arbitration.
  - **The Attack-action gate (user-clarified).** Searing Arc requires the **Attack
    action** — any *weapon* attack (quarterstaff or unarmed), but NOT casting a
    spell. Guiding Bolt is `action_type="attack"` in the engine yet is mechanically
    the Magic action, so it must NOT enable it. `decide()` tracks
    `action_is_weapon_attack` (true for quarterstaff, false for Guiding Bolt) and
    only offers Searing Arc on a weapon-attack turn. BA ladder at L10: Searing Arc
    (weapon-attack turn, FP≥3) > Sacred Flame (Spellfire Spark) > unarmed.
  - **`focus_points` resource** (6 at monk-6). Uncanny Metabolism + Prayer of
    Healing recharge FP fully between combats (guide), modeled by refilling the
    (LR-only) pool in `on_combat_start`. 3 FP/cast → 2 Searing Arc casts/combat.
  - **The cross-check this FIRE feature validates (the point of doing A first).**
    Searing Arc is `is_spell=True` but `damage_type="fire"`, so Fueled Spellfire —
    which gates on `damage_type == "radiant" AND is_spell` — **declines it**. Proves
    the `damage_type` gate, not just `is_spell`, does real work (a radiant spell of
    the same shape IS fueled). The engine offers `on_deal_damage` on every
    Searing-Arc DamageEvent; the policy returns None.
  - **Validation (consistency/sanity, per the Starfire framing — NOT
    number-matching).** `tests/test_starfire_scion.py` (+6): Searing Arc dice/on_save/
    type FROM DATA (4d6 / half / fire); per-cast Burning Hands math exact (full on a
    failed save / half ROUNDED DOWN on a made one, deterministic FakeRNG); the BA
    Attack-action gate (Guiding-Bolt turn → Sacred Flame, weapon-attack turn →
    Searing Arc, FP-out → Sacred Flame); the fire-not-fueled / radiant-fueled
    cross-check on `on_deal_damage`; per-combat FP refill; DPR 14.85 a plausible
    fraction of the 28.0 ceiling; and an our-side ABLATION at the fixed L10 enemy
    (searing-arc-on > searing-arc-off — the clean isolation, since L5 and L10 do not
    share an enemy).
  - **Deferred (unchanged):** Extra Attack + Shillelagh + martial-arts-1d8 (thread
    B, L9); Elemental Adept fire (resistance bypass — moot vs the dummy — + 1→2 die
    high-grading, a per-die `replace` modifier); die-size ladder; multi-enemy AoE.

- **Fueled Spellfire — engine primitive #5: a CASTER-side post-damage decision
  point — BUILT & VALIDATED (2026-06-13, session 6).** The last engine primitive
  on the Starfire Scion's critical path; completes L5's blaster convergence.
  **320 tests green (+18).** Branch `feature/fueled-spellfire`.
  - **What it is.** Spellfire Adept's Fueled Spellfire (guide line 357): ×1/turn,
    when a SPELL the caster casts deals RADIANT damage, expend up to 2 Hit Dice
    (d8) and add them to that damage roll. The on_hit analog on the *damage* side.
  - **Generalized per the user (key scoping refinement).** It must attach to ANY
    radiant SPELL damage instance, not just the save path — at L5 both Guiding
    Bolt (attack-roll) AND Sacred Flame (save-for-damage); later Sunbeam / Fount
    of Moonlight. So it hooks the **DamageEvent** — the single chokepoint
    `resolve_attack_roll` and `resolve_save_damage` BOTH funnel through — rather
    than `resolve_save_damage` alone. Future radiant spells get fueling for free.
  - **Shape (mirrors the existing decider closures).** `Policy.on_deal_damage(ctx)
    → DamageRiderResponse | None` (optional hook); `Scheduler._make_deal_damage_
    decider(event)` looks up the ACTOR's (caster's) policy, builds a
    `DealDamageContext`, validates/consumes the caster's resource, returns the
    dice; threaded into `resolve_damage` as `rider_decider` (phase 5.5). Built for
    every DamageEvent but draws no RNG unless a rider fires → every prior build is
    bit-identical (the 302 War Angel/save tests stayed green).
  - **Spell-radiant gating (the one architectural addition, user-approved).** NEW
    `damage_type` + `is_spell` fields threaded `Choice → AttackRollEvent /
    SaveDamageEvent → DamageEvent → DealDamageContext`. Fuel gate (policy-side) =
    `damage_type == "radiant" AND is_spell`. So Starry-Form Archer (radiant, but a
    FEATURE — `is_spell=False`) is correctly NOT fuelable, while Guiding Bolt /
    Sacred Flame (radiant spells) are. `SaveSpellSpec.damage_type` now surfaces the
    YAML `type:` field (Sacred Flame "radiant"). The engine stays D&D-agnostic —
    "radiant" lives in the policy, not verbs/scheduler.
  - **Dice semantics (user-approved).** Hit dice add just Nd8 (no CON mod — guide
    `4d6+2d8 (23)` confirms). NOT crit-doubled (a fixed expenditure, not the
    spell's own dice). Added BEFORE phase-6 halving (shares a save-for-half spell's
    fate; moot in current scope — Sacred Flame negates, Guiding Bolt doesn't halve).
  - **Hit-Dice pool.** `hit_dice: (5, 0)` at L5 (character-level d8, no SR restore;
    LR at day start refills). Its PRESENCE is the data-driven on/off gate for the
    feature in the policy (`self._fueled_spellfire`). Policy is greedy: fuel the
    first qualifying radiant spell each turn with up to 2 HD while any remain —
    the pool binds (drains in combat 1–2), exactly as the guide describes (~1–3
    fueled combats/day, all 5 HD spent). Because the action (Guiding Bolt) resolves
    before the BA (Sacred Flame), the fuel lands on Guiding Bolt while charges
    last, matching the guide's turn-1 `guiding-bolt_{fueled-spellfire(2)}`. The
    1/turn cap lives in the policy (a `(round, turn_index)` gate, cleared per
    combat in `on_combat_start`).
  - **Validation (consistency/sanity, per the Starfire framing — NOT
    number-matching).** `tests/test_fueled_spellfire.py` (18 tests): the rider
    MATH exact (deterministic FakeRNG) — dice rolled + added, NOT crit-doubled
    (2d8 not 4d8 on a Guiding Bolt crit), shared with save-for-half halving, inert
    when no rider is offered; the POLICY gating (spell+radiant only; Archer
    excluded; non-radiant excluded; 1/turn; per-combat reset; budget binds; off
    below L5); the scheduler closure consults the caster's policy and consumes Hit
    Dice; and end to end — fuel lifts L5 DPR (11.28 → 12.61), drains the pool over
    a day, stays < the no-fuel ceiling (23.0). `test_content.py` updated for the
    new `SaveSpellSpec.damage_type`.
  - **Deferred (unchanged):** Searing Arc Strike at L10 (primitive #3 + data
    ready, policy waits for the level); die-size ladder (Shillelagh at L9); Flame
    Blade / multi-enemy AoE / allies dimension.

- **Starfire Scion BUILD WIRED (L1, L4, L5) + per-attack damage override
  primitive (#4) — BUILT & VALIDATED (2026-06-13, session 5).** The second
  archetype is now a real build, not a scaffold: `make_starfire_scion`,
  `make_training_dummy`, `StarfireScionPolicy.decide` (pure read), and
  `make_day_runner` in `src/builds/starfire_scion.py`. **302 tests green (+18).**
  - **Engine primitive #4 — per-attack damage override (the multi-weapon gish
    primitive; NOT anticipated in the "no engine code" session framing).** The
    engine read ONE `actor.stat("damage_dice")` for every attack (fine for the
    single-weapon War Angel). The Scion mixes FOUR attack profiles with different
    dice on one body — quarterstaff (1d8+DEX), unarmed (1d6+DEX), Starry-Form
    Archer (1d8+WIS), Guiding Bolt (4d6) — so an override was forced. Decided with
    the user (over a no-engine "null-weapon via extra_damage_dice" trick, which
    was the abstraction leak CLAUDE.md #1 warns against): add it deliberately.
    Shape: `Choice.damage_dice`/`damage_bonus` (reused — they already existed for
    `save_spell`) → `AttackRollEvent.damage_dice_override`/`damage_bonus_override`
    → `DamageEvent.damage_dice`. `resolve_attack_roll` uses the override when
    present, else `actor.stat()`. **Override-present iff `damage_dice` is set**, so
    an override of +0 (Guiding Bolt) is distinguishable from "no override". Fully
    backward-compatible — every prior build leaves the fields None and is
    bit-identical (the 284 War Angel/save tests stayed green). Rides the normal
    DamageEvent path, so override dice crit-double like any weapon dice.
  - **Build wiring.** Rotation (a single representative blaster loop; the guide's
    full play splits melee/ranged combats + leans on deferred Flame Blade/forms):
    ACTION = Guiding Bolt (Star Map free cast, xWIS/LR) while charges remain, else
    quarterstaff; BONUS ACTION = **Sacred Flame** (Spellfire Spark, xPB/LR,
    save-NEGATES — the save-for-damage core) > Archer (if Starry Form active this
    combat) > unarmed. Sacred Flame dice come FROM DATA via `interpret_save_spell`
    (1d8 at L1/L4, 2d8 at L5 — cantrip scaling in content, not the policy). Slot/
    charge arbitration + the BA priority ladder stay Python. `decide()` is a pure
    read; the one per-combat resource decision (Starry Form activation, consuming a
    `wild_shape` charge: 2/LR +1 SR → ~3 of 4 combats) lives in `on_combat_start`.
  - **L2/L3 intentionally skipped** (no DPR-relevant mechanics — Druid
    spellcasting / wild-shape utility); easy to backfill for a continuous ladder.
  - **Starry Form engine assessment (user asked):** *Archer* = a BA WIS spell
    attack → reuses attack-roll machinery (delivered via primitive #4, no new
    verb). *Chalice* = extra healing → DPR-irrelevant in the threshold model
    (ignored). *Dragon* = a min-roll-10 floor on concentration saves → MOOT here
    (no offensive-concentration + incoming-damage loop at L1–L5, exactly like War
    Angel before L13); when it matters it's a small `floor` hook on
    `resolve_saving_throw`, not a new primitive.
  - **Enemy is a live CSV input.** `enemy_ac` + `enemy_dex_save` per level are the
    `ac` + `dex.save.mod` rows of `reference/data/monster_ac_and_saves_by_level.csv`
    (asserted against the CSV in the tests). The enemy does NOT strike back yet.
  - **Validation (consistency/sanity, per the Starfire framing — NOT
    number-matching):** `tests/test_starfire_scion.py` pins per-hit math exactly
    (quarterstaff 1d8+3, unarmed 1d6+3, Archer 1d8+WIS, Guiding Bolt 4d6 — each its
    OWN dice, proving the override; +0 bonus honored; crit-doubling), per-save math
    (Sacred Flame 2d8 from data, full on a failed DEX save / negated on a made
    one), the policy's rotation + BA priority + Wild-Shape gating, and that DPR is a
    plausible FRACTION of the ceiling. **Monotonicity is checked at a FIXED enemy**:
    L4 and L5 share the monster (AC 15 / DEX +2), so L5 (~11.15) > L4 (~9.08) cleanly
    isolates our-side scaling (PB+1, WIS+1, 1d8→2d8). Raw cross-level DPR is NOT
    expected monotonic — the enemy hardens (AC 13→15), so L1 (~9.27) ≈ L4 (~9.08),
    exactly as War Angel's own targets dip (L1 8.32 > L2 7.39).
  - **Deferred (in scope, with reasons):** Fueled Spellfire (needs a NEW post-save
    caster decision point — the on_hit analog on the save-damage path; a
    cast-time approximation would burn scarce hit dice on saved casts); Searing Arc
    Strike at L10 (primitive #3 + data ready, policy waits for the level); Flame
    Blade / Stunning Strike / Guiding Bolt's ally advantage-grant / multi-enemy AoE
    (unchanged deferrals).

- **Uniform upcast `increment` dice scaling — BUILT & VALIDATED (2026-06-12,
  session 4; Starfire Scion engine primitive #3).** The uniform branch of the
  shared `_resolve_scaling_dice` seam (was stubbed to RAISE, deferred from #2)
  now folds the schema's `dice: {base, increment, every_n_levels,
  level_reference, base_level}` form to concrete `(count, sides)` at fire-time —
  +`increment` dice per `every_n_levels` of the referenced level. Same machinery
  as #2 but keyed on **`level_reference: slot_level`** (upcast) instead of
  character_level. **284 tests green (+11).**
  - **Offset semantics (decided with user): explicit `base_level`, default 1.**
    The level at which `base` dice apply with zero increments is an optional
    `base_level` field on the dice block; omitted → 1 (the natural floor of
    character / rogue / minimum-slot levels). So Divine Smite (2d8 at slot 1),
    Searing Arc / Burning Hands (3d6 at slot 1) and Sneak Attack (1d6 at rogue 1)
    need NO new field; only a spell whose base lands higher (Spirit Guardians:
    3d8 at slot 3) sets `base_level: 3`. Chosen over deriving from
    `cost.resource.min_level` (which would couple the pure `_resolve_scaling_dice`
    helper to the cost block and not generalize to non-slot references) and over
    a hardcoded floor-of-1 (which would silently mis-scale Spirit Guardians).
    `steps = max(0, level - base_level) // every_n_levels` (clamped so a level
    below the base never shrinks the pool); `count = base_count + steps *
    increment_count`. The die SIZE never changes — a base/increment die-size
    mismatch raises loudly (`2d8` + `1d6` can't fold into one pool).
  - **`content.py`:** `_resolve_scaling_dice`'s `increment` branch implemented;
    `interpret_hit_rider` gained a `context` param so the canonical upcast hit
    rider (Divine Smite) resolves from data given the chosen slot — backward-
    compatible (Wrathful Smite is literal, needs no context). The two divine_smite
    "raises" tests FLIPPED from raise → resolve (per plan).
  - **`content/abilities/starfire_scion.yaml`:** new `searing_arc_strike` ability
    — upcast Burning Hands, DEX save vs `spell_save_dc` **FOR HALF**, base 3d6
    +1d6/slot (`level_reference: slot_level`), cast as a **bonus action**, modeled
    single-target (multi-enemy AoE still deferred).
  - **Validation (consistency/sanity, per the Starfire framing):**
    `test_content.py` pins the uniform steps exactly — per-slot-level for Divine
    Smite (2d8→6d8 at slots 1–5), the explicit `base_level: 3` offset (Spirit
    Guardians 3d8 at slot 3, clamp below base), the `every_n_levels: 2` step
    (Sneak Attack 1d6→10d6), missing-level / die-size-mismatch loud failures, and
    `interpret_hit_rider` resolving upcast Divine Smite. `test_save_for_damage.py`
    drives Searing Arc Strike FROM DATA: upcast dice exact per slot (3d6→7d6 at
    slots 1–5), save-for-half per-cast math exact at each slot (full on fail =
    6×count, half rounded down on a made save), the L10 slot-3 (5d6) Monte-Carlo
    mean a plausible fraction of the all-hit ceiling (DC 16, DEX +3 → P(fail)=0.60,
    mean≈13.9 between the save-negates 10.5 and the ceiling 17.5), strictly
    monotonic growth with slot level, and a BONUS-ACTION save-for-half delivery
    end to end through the scheduler.
  - **Deferred (in scope):** full Starfire Scion policy/build wiring
    (`make_starfire_scion` still raises) — it will read `damage_dice` from
    `interpret_save_spell({"slot_level": N})` and arbitrate which slot to spend.

- **Cantrip / `level_reference` dice scaling — BUILT & VALIDATED (2026-06-12,
  session 3; Starfire Scion engine primitive #2).** Sacred Flame's damage dice
  are now DATA-DRIVEN by character level (1d8→2d8→3d8→4d8 at L1/5/11/17) instead
  of a literal tuple on the `Choice`. **273 tests green (+11).** Scoping decision
  (with user): **Option B — data-driven in `content.py`** (the real Axis-1 win;
  the build was chosen to force exactly this), over Option A (literal dice per
  LEVELS row). Shape:
  - **`content.py` `_resolve_scaling_dice(spec, context, name)` — the shared
    dice-scaling seam.** Folds the schema's `dice` block to a concrete
    `(count, sides)` at fire-time; only the die COUNT scales, never the size.
    Three shapes: (a) **literal** (`"1d8"` / `{base: "1d8"}`, level-independent);
    (b) **cantrip** (`{base, scaling: cantrip, level_reference: character_level}`
    → canonical 5.5e rule: +1 die at char L5/11/17 — its own named mode because
    the thresholds are NON-uniform from L1); (c) **uniform** (`increment` /
    `every_n_levels`) → **raises, deferred to primitive #3** (Searing Arc Strike
    upcast, `level_reference: slot_level`) — same seam, surfaced loudly not
    silently dropped. `_level_from_context` mirrors `_resolve_amount` (data +
    context in → int out, interpreter stays pure).
  - **`content.py` `interpret_save_spell(ability, context) → SaveSpellSpec`**:
    reads the schema's canonical save-for-damage shape (a `verb: save` block —
    `ability` + `dc_reference` — plus a `verb: damage` block — scaled dice +
    `on_save`), resolves the dice via `_resolve_scaling_dice`, and maps the save
    ability → engine stat (`ABILITY_SAVE_MAP`: dexterity→`dex_save`, …). Returns
    `SaveSpellSpec(save_stat, dc_stat, damage_dice, on_save, damage_bonus)` — the
    fields the policy turns into a `Choice(action_type="save_spell")`. Raises
    loudly outside the single-save/single-damage shape.
  - **`interpret_hit_rider` refactored onto `_resolve_scaling_dice`** (DRY) — the
    `divine_smite` `increment` loud-failure test stays green (the shared helper
    still raises on uniform scaling).
  - **`content/abilities/starfire_scion.yaml`** — new file; `sacred_flame` ability
    (DEX save vs `spell_save_dc`, `scaling: cantrip` 1d8, save-negates).
  - **Schema doc** (`ability_schema.md` §4.5): documented the two `dice` scaling
    shapes — uniform `increment`/`every_n_levels`, and the new named **`cantrip`**
    mode. The only schema vocabulary addition this session.
  - **Validation (consistency/sanity, per the Starfire framing):** `test_content.py`
    pins the cantrip steps exactly at every threshold/boundary (1d8 L1–4, 2d8
    L5–10, 3d8 L11–16, 4d8 L17+), the missing-context / wrong-`level_reference` /
    uniform-deferred loud failures, and `interpret_save_spell` producing the right
    `SaveSpellSpec` at L1/5/11/17. `test_save_for_damage.py` extends the
    Monte-Carlo path to drive the dice FROM the interpreter: per-cast damage math
    exact at each tier (full = 8×count on a max-roll failed save), mean damage = the
    fail-rate fraction of the all-hit ceiling at L11 (3d8, DC 15, P(fail)=0.60,
    mean≈8.1 < 13.5), and strictly monotonic growth L1<L5<L11<L17.
  - **Deferred (in scope):** full Starfire Scion policy/build wiring
    (`make_starfire_scion` still raises) — it will read `damage_dice` from
    `interpret_save_spell` instead of a literal. Primitive #3 (upcast `increment`)
    reuses `_resolve_scaling_dice` with `level_reference: slot_level`.

- **Save-FOR-damage resolution — BUILT & VALIDATED (2026-06-12, session 2;
  Starfire Scion engine primitive #1).** The first attacker-side save: the
  TARGET rolls a saving throw vs the caster's `spell_save_dc`, and the result
  determines damage. Supports both *save-negates* (Sacred Flame: full on fail,
  nothing on success) and *save-for-half* (Burning Hands: full on fail, half —
  rounded down — on success). **262 tests green (+12).** Shape (decided with
  user, both the recommended options): a **damage-specialized `SaveDamageEvent`**
  (NOT a generic `SavingThrowEvent` — generalize when a non-damage payload like
  frightened forces it), mirroring the `AttackRollEvent → DamageEvent` split:
  - `events.py`: `SaveDamageEvent` (kind `"save_damage"`) carries `save_stat`
    (target's, e.g. `dex_save`), `dc_stat` (caster's, `spell_save_dc`),
    `damage_dice`/`damage_bonus` (the SPELL's own dice — carried on the event,
    not pulled from `actor.stat("damage_dice")` which is the weapon), and
    `on_save` ("none"|"half"). `DamageEvent` gains `halved: bool=False`.
  - `verbs.py`: `resolve_save_damage` calls `resolve_saving_throw` (REUSED
    unchanged, no reroll decider — enemies have no Indomitable) and, on the
    damage branch, **enqueues a normal `DamageEvent`** — so the phase-ordered
    damage roll, concentration check, and save-reroll machinery are reused
    untouched (the save verb never rolls a damage die itself). A made
    save-negates enqueues nothing (the missed-attack analog). `resolve_damage`
    gains **phase 6**: halve the post-phase-5 total when `halved` (inert on every
    existing path). Halving is applied before `take_damage`/`_check_concentration`
    so the halved amount drives any concentration DC.
  - `scheduler.py`: registers `resolve_save_damage` under `"save_damage"` (plain
    4-arg Handler → driven by the generic dispatch `else` branch, **no new
    `isinstance` branch in `run()`**; damage is accounted when the spawned
    DamageEvent resolves). New `action_type="save_spell"` branch in
    `_handle_turn_start` builds the event from a `Choice`.
  - `policy.py`: `Choice` gains `save_stat`/`dc_stat`/`damage_dice`/`damage_bonus`/
    `on_save` (read only for `action_type="save_spell"`).
  - `entity.py`: telemetry `saving_throws_made`/`saving_throws_failed` on the
    saver (mirrors `concentration_checks`; design §8 "saves forced/failed").
  - **Validation (consistency/sanity, per the Starfire framing — NOT number-
    matching):** deterministic FakeRNG pins the per-save damage math exactly
    (full / negated / half-rounded-down / nat-1-is-not-auto-fail); a Monte-Carlo
    check (`tests/test_save_for_damage.py`, 20k casts) confirms mean damage = the
    analytic fail-rate fraction of the all-hit ceiling at **L1** (DC 13, enemy
    DEX +1, 1d8 → P(fail)=0.55, mean≈2.475 < ceiling 4.5) and the **L5** Sacred
    Flame shape (DC 15, enemy DEX +2, 2d8 → P(fail)=0.60, mean≈5.40 < 9.0), and
    that 2d8 > 1d8 (monotonic growth). The enemy DEX save bonus is now a **live
    input** from `monster_ac_and_saves_by_level.csv`.
  - **Deferred (in scope):** the full Starfire Scion policy/build wiring
    (`make_starfire_scion` still raises) and a YAML `interpret_save_spell` in
    `content.py` — both later slices. Data-driven cantrip scaling is primitive #2.

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
- **Declarative ability layer — BOOTSTRAPPED (Slices 1+2).** `src/content.py`:
  a YAML loader (`load_abilities` → name→`Ability` library) + an **effect-
  interpreter** that translates ONE ability's effect/cost block into the engine
  objects the existing typed decision points already consume. NOT a verb VM —
  an *adapter* ("effect compiler"); the engine never built a generic verb
  executor, only typed seams (`decide`/`on_hit`/`on_miss`/`on_incoming_hit`/
  `on_failed_save` → `Choice`/`HitResponse`/`Modifier`/…). Confirmed boundary
  (this session): interpreter does effect→response translation; the Python
  policy keeps WHICH-ability/ordering/slot-arbitration. Two slices, both diffed
  bit-identical against the War Angel oracle (A/B at seed 1: L13 35.183, L16
  41.237 — identical before/after):
  - **Slice 1 — Bless** (`interpret_modifiers`, `bonus_die`+`flat` hooks):
    reads `core_examples.yaml`'s `bless` → the same two `Modifier(+1d4 on
    attack_bonus/con_save)` `_sync_bless` hand-built. Reuses the canonical
    example content (proves it's interpretable).
  - **Slice 2 — Wrathful Smite** (`interpret_hit_rider`, `damage` rider):
    new `content/abilities/war_angel.yaml` → `HitRiderSpec(1d6,
    bonus_action, spell_slot≥1)`; the policy's `on_hit` smite branch now takes
    its dice + action economy from data (slot PRIORITY stays Python).
  - `parse_dice` ("NdM"→(n,sides)); `DEFAULT_SCOPE_MAP` resolves the abstract
    `applies_to: attack_rolls_and_saving_throws` → the only two stats the engine
    rolls dice for (attack_bonus, con_save), injectable. 10 new tests (incl.
    loud-failure pins), **232 total green**. `requirements.txt` added (PyYAML).

- **Declarative ability layer — WIDENED (Slices 3–6, branch
  `declarative/brutality`).** Four more abilities now drive the War Angel FROM
  DATA, each diffed bit-identical against the oracle at seed 1 (L5/L7/L12–L16,
  no DPR change anywhere). Every slice climbed a *different* decision-point seam,
  and **zero new engine verbs were forced** — confirming again that "new ability
  = data + maybe a subscriber", not engine code. **250 total green** (+18).
  - **Slice 3 — Brutality bluff + bleed** (`interpret_on_hit_effects` →
    `OnHitEffectSpec`): `apply_status` routed by target (a TARGET status that
    names a known mastery → `extra_masteries`/`CounterSpec.masteries`; a SELF
    status → `self_status_on_hit`) + flat `damage`. bluff = vex +
    advantage_next_save (on_hit/HitResponse); bleed = sap + CHA flat (Flourish
    Counter/CounterSpec). **First runtime-dependent value**: bleed's +CHA is
    resolved against a policy-supplied `context` ({"charisma": cha_mod}) — the
    interpreter EVALUATES, not just compiles (the static-vs-interpretive line
    from gap #1). Interpreter kept PURE (data + context in → spec out).
  - **Slice 4 — Flourish Parry** (`interpret_intercept` → `InterceptSpec`): the
    `intercept_event` seam (design §4 #15) — a flat AC bump (+CHA, runtime), or a
    literal `value`. **Scoping finding (build guide):** War Angel's Flourish is
    parry (this) + counter (a bleed attack), NOT the schema's `choose_one`
    Flourish (distract/protect/strike) — that example is a *different* ability.
    So `choose_one` is NOT needed here and remains an unbuilt gap until a build
    uses those modes.
  - **Slice 5 — flat buffs** (`interpret_modifiers` flat hook, now literal-or-
    runtime): War God's Blessing (free Shield of Faith, literal +2 AC) and Magic
    Weapon (+1/+2 atk+dmg). MW's two flat mods (same value, both stats) is the
    ability intrinsic; the +1-vs-+2 cast TIER is policy arbitration, passed as a
    runtime `context` value (`amount: {context: magic_weapon_bonus}`).
    `_resolve_amount` now accepts `{ability_modifier: <stat>}` or
    `{context: <key>}`. Removed the now-dead `SHIELD_OF_FAITH_AC` const + direct
    `Modifier` import from war_angel.py.
  - **Slice 6 — Guided Strike** (`interpret_roll_bonus` → `RollBonusSpec`): the
    `on_miss` seam — a flat +10 attack-roll rescue + channel_divinity cost. Added
    an **`on_miss` event predicate** to the schema vocabulary (§3.1, the mirror of
    on_hit) — a cheap PREDICATE addition, not a verb (§9). The interpreter does
    not read the trigger; the policy owns WHEN.
  - **Indomitable — DELIBERATELY DEFERRED (decided with user this session).** It
    does NOT land cleanly: (a) the closed verb set has no save-reroll verb
    (`reroll_take_better` is dice-pool take-better, wrong — Indomitable's reroll
    *stands*), and (b) its bonus is a `level_reference` (the known scaling gap).
    Data-fying it honestly means inventing schema structure, which we won't do
    unilaterally. Left as a documented gap; `on_failed_save` stays hand-coded.
  - **Interpreter coverage now:** `apply_modifier` (bonus_die + flat, literal &
    runtime), `damage` rider (HitRiderSpec), on-hit `apply_status` + flat damage
    (OnHitEffectSpec), `intercept_event` flat AC bump (InterceptSpec), flat
    attack-roll rescue (RollBonusSpec). **Still-open gaps (interpreter raises
    LOUDLY):** scaling/upcast dice (`increment`/`level_reference` — real Divine
    Smite, Indomitable bonus), `choose_one` blocks, data-driven trigger/predicate
    dispatch (still Python — grow when a build makes policy-side gating painful),
    and a save-reroll representation.

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

### NEXT STEP — NEW PHASE: declarative ability layer (War Angel validation CONCLUDED at L16)

**War Angel validation is deliberately CONCLUDED at L16 (not abandoned — it did
its job).** Phases A–E (L1–16) are done & validated; the engine-primitive
build-up is complete. **222 tests green.** The decision to stop (user + Claude,
this session) and the rationale:
- **No remaining benchmark.** The guide's DPR is a literal `XXXX` placeholder
  from L16 on, and the R prototype ended at L10. So L17–20 would produce DPR
  numbers with nothing to validate them against — the whole point of the
  exercise (check the engine against an objective benchmark) no longer applies.
- **No new engine primitives in L17–20** (analyzed): L17 = data (PB +6; enemy
  hardens to +13 / 36 dmg → DC-18 concentration — exercises the *already-built*
  save stack); L18 Extra Attack ×2 = a 2→3 attack-count change in `decide()`;
  L19 boon = passive data; L20 **Blessed Strikes** = a 1/turn on-hit +1d8 rider
  that *reuses the existing `on_hit` decision point* + a per-turn gate (no new
  verb), and a L4 slot = more upcast fuel. Marginal engine learning ≈ zero.
- **Headline validation result:** across all of War Angel, **zero new verbs were
  forced.** Everything new was a *decision point* (miss / hit / intercept /
  save-reroll) — exactly the extensible seam the design predicted. The engine
  PRIMITIVES are validated.

**→ NEXT MAJOR FOCUS (agreed): build the declarative ability layer — the
project's #1 architectural bet (CLAUDE.md #1/#2), still UNBUILT in running
code.** Two architecture gaps War Angel left open (neither forced by it):
  1. **Abilities-as-data — WIDENED, most War Angel intrinsics now data (see Done
     "Declarative ability layer" Slices 1–6).** `src/content.py` loads
     `content/abilities/*.yaml` and the effect-interpreter now drives Bless,
     Wrathful Smite, **Brutality bluff+bleed, Flourish Parry, War God's Blessing,
     Magic Weapon, and Guided Strike** FROM DATA in `war_angel.py` (all
     bit-identical to the oracle). The central bet is de-risked across SIX
     decision-point seams (decide-buff / on_hit / intercept / on_miss) with zero
     new verbs forced. **What's left to fully realize "adding an ability = data":**
     - **Remaining hand-coded intrinsics**: Indomitable (`on_failed_save` reroll —
       DEFERRED this session, needs a save-reroll schema rep + level_reference;
       see Done). True Strike (1d6 cantrip rider applied in `decide()`, L5–9) and
       War Priest (a bonus-action weapon *attack* Choice) are more decide()-level
       action-economy than effect-intrinsics — lower-value to data-fy.
     - **Gaps the slices surfaced (interpreter raises LOUDLY on these today, by
       design):** (a) **scaling/upcast** dice (`increment`/`every_n_levels`/
       `level_reference`) — real Divine Smite, the Indomitable bonus; (b)
       **`choose_one`** effect blocks (a real distract/protect/strike Flourish on
       another build — War Angel does NOT use it, see Slice 4); (c) **a
       save-reroll representation** (Indomitable); (d) **trigger/predicate
       evaluation** is NOT yet data-driven — the policy still hand-codes
       `once_per_turn`, weapon type, bless-turn gating, and every slice's WHEN
       (the confirmed "effect-compiler first" scope; grow trigger-dispatch only
       when a build makes policy-side gating painful); (e) **resource-type→slot**
       resolution stays in the policy (correct per the boundary).
     - Vocabulary additions recorded this session: **`on_miss` event predicate**
       (§3.1, mirror of on_hit — Guided Strike); the runtime-`amount` forms
       `{ability_modifier: <stat>}` and `{context: <key>}`.

     **Architecture clarification (decided this session — "interpreter" vs
     "compiler").** Worth pinning so it isn't re-litigated: the design's word
     "interpreter" pins ONE axis — *D&D knowledge lives in data, not engine
     code* (CLAUDE.md #1). It is SILENT on the runtime *mechanism* (tree-walking
     evaluator vs. translate-to-engine-objects). So `content.py` being an
     effect-COMPILER/adapter does not violate the contract. Two clarifying
     points: (a) the "compiler" feel of Slice 1 is partly because Bless is
     *context-free* (`+1d4 always` → a static `Modifier`); the moment an ability
     has runtime-dependent values (scaling by slot, fire-time target, conditional
     value) the same functions evaluate at fire-time *with a context* = genuinely
     interpretive — we're at the static end of the SAME path, not a different one
     (this is also why the interpreter RAISES on `increment` today). (b) The
     destination is NOT "everything is data": cross-ability strategy (sequencing,
     slot arbitration) stays Python policy (CLAUDE.md #2); only ability INTRINSICS
     (trigger/effect/cost) become data. The real remaining Axis-1 debt is
     **trigger/predicate DISPATCH** — making an ability *fire* without the policy
     naming it (gap (c) above). It stacks cleanly ABOVE the effect-interpreter
     and calls it, so building effect-eval first does not lock it out — **as long
     as the interpreter stays PURE (data in → engine objects out, no policy state
     leaking in).** Guard that purity; it's what keeps the dispatch seam open.
     **Decision: proceed with the original plan** (widen effect-eval
     ability-by-ability against the oracle); build trigger-dispatch when a build
     makes the policy-side gating painful enough to warrant it, or as a
     deliberate slice if we want to prove the interpretive half early.
  2. **Outputs layer is ~10% built.** design §8 lists a rich set (hit/crit/adv
     rates, saves forced/failed by type, resource usage per day/combat, status
     uptimes, per-ability damage breakdown, damage taken/reduced/healed). We emit
     DPR + CI + a couple of internal counters. We kept *hand-rolling* telemetry
     by monkeypatching (the slot audit, parry-budget check, concentration count)
     — evidence the first-class layer is missing and wanted. **Slot this in
     alongside the ability-layer work** (it partly falls out of doing it well);
     it is lower-risk, high compounding payoff.

**Intended sequence after the ability layer:** then a **second, very different
archetype** (spellcaster / save-based / ranged / multi-target) — written *as
data* through the new loader, simultaneously testing the loader AND forcing the
breadth War Angel never did (enemy saves, AoE, the deferred spell-aggressive
enemy, maybe spatial). Richer enemy model + finite-HP toggle are real but later
("extension", not "core-thesis test"). See "Open threads" for the full deferred
list (spatial, spell-aggressive enemy, TurnEndEvent/reaction-economy, scheduled
saves + spell_save_dc, weapon slot, light/nick, frightened condition).

#### Second archetype — STARFIRE SCION (selected 2026-06-12; plan recorded, UNBUILT)

The second build is **The Starfire Scion** (`design/build-guides/41_spellfire_scion.txt`)
— **Monk-08 (Sun-Soul) / Druid-12 (Circle of Stars)**, a WIS-based spellfire
"blaster" gish. Scaffold: `src/builds/starfire_scion.py` (data + plan docstring
only so far). Chosen over the other save/AoE candidates (Voice of Heaven, Tech
War Priest, Reanimating Bloodshot) for a *capacity* reason, recorded so it isn't
re-litigated:

- **Why it maximizes model-capacity expansion.** It forces the two highest-value
  untouched gaps cleanly: (1) **save-FOR-DAMAGE resolution** — a save whose
  *result determines damage dealt* (Sacred Flame: DEX save, save-*negates*;
  Burning Hands / Searing Arc Strike: DEX save, save-*for-half*). This is new: our
  only save today is concentration (incoming-damage-driven, binary drop/keep), and
  no attacker has ever carried a `spell_save_dc`. (2) **upcast / `level_reference`
  scaling** — cantrip scaling (Sacred Flame 1d8→2d8→3d8→4d8 at char L5/11/17) and
  Searing Arc Strike (upcast Burning Hands, +1d6/slot level, from L10) — the
  `increment`/`level_reference` cases `content.py` currently raises LOUDLY on.
- **Crucially, it forces both via SINGLE-TARGET deliveries** (Sacred Flame /
  Guiding Bolt are single-target; Burning Hands modeled single-target for now). So
  it expands capacity on the axes we're ready for while **cleanly deferring the
  multi-enemy / spatial axis** (decided with user: that axis is the hardest, least
  isolated, and not yet touched — see the rejected candidates below).
- **Bonus capability it activates:** enemy saves now need the enemy's save bonus,
  so `reference/data/monster_ac_and_saves_by_level.csv` (per-level AC + all six
  `*.save.mod`, keyed by char level) becomes a **live input** — it has been
  read-only until now. Also exercises **concentration from the OFFENSE side**
  (Flame Blade; we only built it for defensive Bless), and adds **Fueled
  Spellfire** (≤2 hit dice added to a radiant damage roll, 1/turn) — a
  "smite-on-radiant-damage" rider that reuses the existing decision-point pattern
  (expected: no new verb).
- **Candidates rejected (with reasons, user-confirmed):**
  - *Voice of Heaven (25, Celestial Warlock / Glamour Bard)* — core loop bakes in
    **multi-enemy + spatial dynamics** (BA Command to herd enemies into AoE; spirit
    guardians ticking on several enemies). That's the one axis we have zero
    machinery for; forcing it first = the hardest, least-isolated bite.
  - *Tech War Priest (30, Artillerist / War Cleric)* — uses an **outdated 2024
    Artificer chassis** (guide itself would need correcting as we model, muddying
    validation) and is **L12-only** (no long-arc ladder).
  - *Reanimating Bloodshot (36)* — keep on the shelf as the future **separate
    on-field entity / summon** forcing build (reanimated minion), but it's
    **primarily our own weapon attacks** → structurally close to War Angel's
    attack-roll martial archetype, low novelty on the save/AoE/upcast axis.

**Two corrections folded into the plan (user, 2026-06-12):**
1. *Guiding Bolt is an ATTACK-ROLL spell in 2024*, not save-for-damage: 4d6 radiant
   on hit **+ a grant-advantage status** on the target (until end of our next
   turn). The attack half reuses existing machinery. The advantage grant
   realistically benefits an **ally** (we rarely consume it) → pokes the unmodeled
   **"allies in combat"** dimension. **Deferred sub-decision:** initially model
   Guiding Bolt as a plain 4d6 attack (advantage-grant ignored or self-consumed);
   do NOT build an ally model now (minor DPR effect, off critical path).
2. *The guide's per-level DPR numbers are "all-hit CEILINGS," not real targets* —
   they assume every attack hits and the enemy always fails its save (no AC, no
   misses, no successful saves, no stunning-strike resistance). Unlike War Angel
   (which had genuine R-prototype simulated DPR to match ±10%), Starfire Scion has
   **no ground-truth DPR ladder** — producing honest DPR for this build is itself a
   *goal* of the model, not an input. **Validation framing flips to
   consistency + sanity** (like War Angel L16): per-hit / per-save *damage math*
   exact; DPR grows monotonically; DPR is a *plausible fraction* of the ceiling
   given that level's hit / save-fail rates. The ceiling table is a loose upper
   bound only.

**First gap to force (agreed): save-FOR-DAMAGE resolution.** Foundational (appears
at L1 via Sacred Flame), and a prerequisite for Fueled Spellfire and Searing Arc
Strike. Upcast scaling comes later up the ladder.

**Engine-capacity build order:**
1. ~~`spell_save_dc` on the attacker + a **save-for-damage** resolution path~~ ✓
   **DONE & VALIDATED (2026-06-12, session 2; branch `feature/save-for-damage`).**
   The target rolls d20 + its save bonus (e.g. `dex_save`, from the monster CSV)
   vs the caster's `spell_save_dc`; the save result determines damage — *negates*
   (Sacred Flame) or *for-half* (Burning Hands). The first attacker-side save
   primitive (vs. concentration, which is target-side). See the Done entry below.
2. ~~Cantrip / `level_reference` dice scaling (Sacred Flame by character level).~~ ✓
   **DONE & VALIDATED (2026-06-12, session 3; Option B — data-driven).** Sacred
   Flame's dice are resolved from `content/abilities/starfire_scion.yaml`
   (`scaling: cantrip`) by character level via `content._resolve_scaling_dice` +
   `interpret_save_spell`. See the Done entry above.
3. ~~Upcast `increment` scaling (Searing Arc Strike = upcast Burning Hands).~~ ✓
   **DONE & VALIDATED (2026-06-12, session 4).** The uniform branch of
   `_resolve_scaling_dice` now folds `{base, increment, every_n_levels,
   level_reference, base_level}` to concrete dice keyed on `slot_level`; offset =
   explicit `base_level` (default 1). `searing_arc_strike` (save-for-half, upcast
   3d6+1d6/slot) drives FROM DATA through `interpret_save_spell`. See the Done
   entry above.
4. ~~Per-attack damage override (the multi-weapon gish primitive).~~ ✓ **DONE &
   VALIDATED (2026-06-13, session 5).** Surfaced when wiring the build, NOT
   anticipated by the "save-for-damage primitives are all the engine needs"
   framing: the Scion swings several attack profiles with different dice on one
   body (quarterstaff / unarmed / Archer / Guiding Bolt), but the engine read a
   single `actor.stat("damage_dice")`. `Choice.damage_dice`/`damage_bonus` →
   `AttackRollEvent.*_override` → `DamageEvent`, defaulting to the entity stat
   (backward-compatible). See the Done entry above. **The L1/L4/L5 build is now
   wired** (`make_starfire_scion` + `StarfireScionPolicy` + `make_day_runner`); the
   climb to L6+ is per-level data + policy from here.
5. ~~Fueled Spellfire (the post-damage caster decision point; completes L5).~~ ✓
   **DONE & VALIDATED (2026-06-13, session 6; branch `feature/fueled-spellfire`).**
   A CASTER-side post-damage decision point hooked on the **DamageEvent** (the
   chokepoint BOTH the attack-roll and save-for-damage paths funnel through), so
   it's a general radiant rider covering Guiding Bolt + Sacred Flame now and any
   future radiant spell. `Policy.on_deal_damage → DamageRiderResponse` via
   `Scheduler._make_deal_damage_decider`, threaded into `resolve_damage` as
   `rider_decider`; gated on "spell radiant damage" (NEW `damage_type` + `is_spell`
   threaded `Choice → events → DamageEvent`). Hit dice = scarce per-day pool; rider
   NOT crit-doubled. See the Done entry above.

**Next on the Scion's ladder.** Thread A (Searing Arc Strike, L10) is DONE (session
7). **Thread B (L9 + L10: Extra Attack + martial-arts 1d8 + Shillelagh) is DONE
(session 8)** — see the session-8 Done entry; NO new engine primitive, as predicted.
The L1/L4/L5/L9/L10 ladder is now wired. **Open next steps (pick with the user):**
(a) **L12** — WIS → 20 (a data row; +1 to-hit/DC/damage, Shillelagh die unchanged at
char L11+ would be 1d12 — note the die-size step at L11); (b) **L11+ Shillelagh die
→ 1d12** (still bake-able, or finally build the data-driven `scaling: ladder` if a
continuous ladder past L10 is wanted — see "die-size scaling" below); (c) the
**ATTACK-TAXONOMY** typology (engine-vocabulary work — discuss first); (d) the
**outputs layer** (still ~10% built — design §8). No remaining engine primitive is
forced by the Scion's offense axis; what's left is data rows, the deferred die-size
ladder, and the two cross-cutting investments (taxonomy, outputs).

**die-size scaling — the next unbuilt SCALED-QUANTITY (flagged, first consumer
SHILLELAGH at L9; recorded with user 2026-06-13).** 2024 Shillelagh has cantrip
scaling like any damaging cantrip, but it grows the **die SIZE** — and its top
step changes the COUNT too: **1d8 → 1d10 (L5) → 1d12 (L11) → 2d6 (L17)**. That is
NOT the uniform die-COUNT walk `_resolve_scaling_dice` handles (it holds size
fixed: `return base_count + steps, sides`), and NOT a pure die-size walk either
(the 2d6 step). The right primitive is an **enumerated DICE LADDER**: a break list
paired with an arbitrary `(count, sides)` per step (e.g. `scaling: ladder`,
`breaks: [5,11,17]`, `dice: ["1d8","1d10","1d12","2d6"]`) — a NEW scaled-quantity
in the §4.5 typology (the uniform die-count form is built; the dice ladder and
target-count are the unbuilt axes). It is a pure scaling-helper addition, small
and isolated — NOT blocked on any other model (unlike target-count, which waits on
multi-enemy). **The build can DODGE it** by baking the resolved die into each
LEVELS row (Shillelagh = (1,10) at char L9–10, (1,12) at L11–16, (2,6) at L17+),
exactly as weapon dice are already per-level data — so wiring L9 needs only
primitive #4 + a policy flag + this per-level die. Build the data-driven ladder
only when a die-size feature should resolve from YAML by character level. The
attack-profile half of Shillelagh (STR/DEX → WIS swap + d-size weapon) is already
covered by primitive #4. **And it is a GENERAL phenomenon, not a Shillelagh quirk
— bardic inspiration (d6→d8→d10→d12), battlemaster superiority die (d8→d10→d12),
psionic / psi-energy dice all scale their die by class level, and some are
`bonus_die` modifiers rather than damage pools** → build the dice LADDER ONCE as a
first-class shape (per-feature break list → per-step `(count, sides)`, which
covers pure die-size growth and Shillelagh's mixed 2d6 step alike), reused across
all of them, not re-solved per ability. See `design/ability_schema.md` §4.5
"Scaled quantity".

**ATTACK TAXONOMY — engine-vocabulary gap (flagged, surfaced session 7; FUTURE
work, discuss before any engine change).** Searing Arc Strike keys on the *Attack
action*, which forced disambiguating it from Guiding Bolt (a spell delivered via an
attack roll). The proxy used (`is_spell == False`) works, but it exposed that the
engine conflates three *distinct* rules axes the user wants cleanly mapped across
the whole model. The user's rules framing (2024), recorded verbatim so it isn't
re-derived:
  - An **attack** = anything requiring an **attack roll**. Exactly three KINDS:
    **weapon attack**, **unarmed strike**, **spell attack** (that's the full set).
  - The **Attack action** = specifically using your *action* to attack with a
    weapon or unarmed strike (Extra Attack scales this). It does NOT include
    casting a spell.
  - **Casting a spell** uses the **Magic action** (and some non-spell features also
    cost the Magic action).
  - Spells/features can grant attacks at OTHER action-economy costs: a **bonus
    action** (Starry-Form *Archer* = a ranged *spell attack* as a BA; *Spiritual
    Weapon* = a spell attack delivered by a separate summoned entity as a BA) or a
    **reaction**. A separate entity / companion can also attack (Beastmaster Primal
    Companion's *strike* ≈ an unarmed strike as a BA).
  The three axes the engine currently collapses into `Choice.action_type="attack"`
  + `cost` + `is_spell`: (1) the attack **KIND** (weapon / unarmed / spell attack —
  governs which dice/mods/feats apply); (2) the **action taken** (Attack action /
  Magic action / other — governs gating like "did you take the Attack action?");
  (3) the **economy cost** (action / bonus_action / reaction). A clean typology
  separates all three. Building it is FUTURE work (NOT done in session 7 — only
  flagged). The user offered to elaborate further on the rules distinctions when we
  take it up.

**VALIDATION TOOL — the ablation (adopted session 7).** When adjacent ladder levels
do NOT share an enemy (so the existing "fixed-enemy monotonic" check, e.g. L4 vs L5,
doesn't apply), isolate a feature's contribution by an **on-vs-off ablation at a
single fixed enemy**: run the level with the feature enabled vs. disabled (e.g.
`policy._has_searing_arc = False`) and assert the enabled DPR is strictly higher.
This is now a standard consistency tool alongside the fixed-enemy monotonic compare.

**Explicitly deferred (unchanged):** multi-enemy AoE + spatial (Burning Hands
modeled single-target until a multi-enemy model exists); separate-entity / summons
(→ Reanimating Bloodshot later); the allies dimension (Guiding Bolt advantage
grant). Validation = consistency/sanity, not number-matching.

*(War Angel L17–20, if ever resumed: `make_war_angel(17)` is the next-raises
level; all four are consistency-only, no primitives. Low priority.)*

| Level | DPR        | Target | Error  | Days |
|-------|------------|--------|--------|------|
| 8     | 23.48      | 23.36  | +0.5%  | 30k  |
| 9     | 27.60      | 27.59  | +0.0%  | 30k  |
| 10    | 35.34      | 35.32  | +0.1%  | 30k  |
| 11    | 33.665     | 33.70  | −0.1%  | 30k  |
| 12    | 38.074     | 38.11  | −0.1%  | 30k  |
| 13    | 35.145     | 34.68  | +1.3%  | 30k  |
| 14    | 39.543     | 37.96  | +4.2%  | 30k  |
| 15    | 38.675     | 36.59  | +5.7%  | 30k  |
| 16    | 41.247     | —      | n/a    | 30k  |

**E3 (L16) — DONE & VALIDATED (41.247, consistency-only — no guide target).**
The guide's L16 DPR is a literal `XXXX` placeholder and the R prototype stops at
L10, so L16 is validated for **consistency**, not against a number: L16 (41.247)
> L15 (38.675) by +6.6%, telemetry sanity holds, and L1–15 re-ran bit-identical.
The enemy is **unchanged from L15** (the L17 guide section confirms Monster AC
stays 18, +12, 32 dmg / DC-16) — the entire L16 gain is on our side. Two pieces:
- **Rapier switch + Tactical Master (data + policy; NO new primitive — the
  `mastery_override` field on `Choice` was ALREADY consumed by the scheduler at
  scheduler.py:461, so the old "stubbed, not wired" note was stale).** Longsword
  (sap) → rapier (vex): vex reapplies every attack, so the advantage chain runs
  ~100% instead of the ~1/3 we got from spending a bluff for vex each turn. The
  policy then sets `mastery_override="sap"` on the first on-turn attack
  (Tactical Master, 1/turn) and the existing on_hit bluff fires on it to re-add
  vex + grant the concentration save-advantage. Telemetry confirms the swap: the
  per-day vex/sap application ratio FLIPPED (L15 sap-dominant 130k:39k → L16
  vex-dominant 121k:55k).
- **Indomitable — NEW engine primitive: the failed-save reroll decision point.**
  `Policy.on_failed_save(ctx) → SaveRerollResponse | None` (optional hook);
  `resolve_saving_throw` gains a `reroll_decider` that, on a FAILURE, may reroll
  a fresh d20 + save bonus + flat bonus (the new result stands, per RAW). The
  scheduler's `_make_save_reroll_decider(event)` builds it from the damage
  TARGET's policy and threads it `resolve_damage → _check_concentration →
  resolve_saving_throw` (mirrors the intercept decider; backward-compatible —
  the decider is built for every DamageEvent but draws no RNG unless a reroll
  fires, so L1–15 are bit-identical). The symmetric analog of Guided Strike
  (which rescues a missed *attack*). Generalizes to any future save-reroll
  (Luck, Portent-style) and any scheduled save (frightened, enemy save-spells).
  *Indomitable policy = "greedy among positive-value failures"* (1/LR): spend on
  the first failed concentration check that (a) a +9 reroll is likely to clear
  (the **DC-assessment** gate, using the flat save bonus — inert at the uniform
  DC-16 where it always says yes, load-bearing once weaker/variable-DC saves
  exist) and (b) still has a round of the combat left to protect (last-round
  floor). Telemetry: ~0.64 rerolls/day, cutting concentration breaks ~in half
  (1.14 → 0.65/day). DPR impact is tiny (~the breaks it prevents lift Bless
  uptime slightly) — modeled for fidelity per the guide's "cherry on top".

**E2 (L15) — DONE & VALIDATED (38.675 vs 36.59, +5.7%, within soft ±10%).** A
pure **data row** — no new engine primitives, no policy change, exactly as
predicted. Fighter-08 → Resilient (DEX): +1 DEX (→17) + DEX-save proficiency, but
DEX is not our CHA attack stat (attack/damage UNCHANGED) and medium armor caps
DEX-to-AC at +2 (AC unchanged); the added `dex_save: 8` is cosmetic
(DPR-irrelevant in the threshold model). All movers are monster-side: enemy AC
17→**18** (main DPR drop), enemy to-hit +11→**+12**, enemy damage 28→**32**
(→ DC-16 concentration checks, `max(10, 32//2)=16`). Combat tactics identical to
L14 (bleed on every flourish counter; guide confirms bleed beats bluff by ~0.5
DPR even at AC 18). L13 (35.145) and L14 (39.543) re-ran bit-identical → no
regression.

*Validation story (+5.7% overshoot, larger than L14's +4.2%, explained).* Same
two user-approved EV-max choices as L14 (full counter budget + 40% targeting vs
the guide's 50%). The overshoot *grows* because the harder monster's higher
to-hit creates **more parry-flip opportunities** → more Flourish-Counter bleed
DPR, which partially offsets the AC-18 hit-rate loss (our DPR drops only 0.87,
39.543→38.675, vs the guide's target dropping 1.37). **Correction to the L14
"non-binding" prior:** at L15 the `flourish_counter`=6/day budget is now **mildly
binding** — mean 4.30 counters used/day, and **~27% of days hit the cap of 6**
(measured, 2k days). The binding *restrains* DPR on those days, so it makes the
overshoot conservative (not inflated). No hidden modeling error.

**E1 (L14) — DONE & VALIDATED (39.543 vs 37.96, +4.2%, within soft ±10%).** The
first reaction decision point on the enemy's turn. New engine primitives (all
backward-compatible — L1–13 DPR unchanged):
- **`intercept_event` (design §4 #15), AC-bump form** — a new DEFENDER-side
  decision point. `Policy.on_incoming_hit(ctx) → InterceptResponse | None`
  (optional hook); scheduler `_make_intercept_decider(event)` looks up the
  *target's* policy, validates/consumes the *defender's* resources, returns
  `(ac_bonus, counter_spec | None)`. `resolve_attack_roll` calls it on a hit
  AFTER any Guided-Strike rescue and BEFORE the attacker's on-hit rider: if
  `total_roll < AC + ac_bonus` the hit flips to a miss (→ no DamageEvent → no
  concentration check, automatically). Mirrors the on_miss/on_hit closure
  pattern. Generalizes to Shield / Defensive Duelist now, and to Uncanny Dodge
  once a damage-side hook is added in `resolve_damage`.
- **Flourish Counter** — on a parry-flip, `resolve_attack_roll` enqueues a
  counter `AttackRollEvent` (actor=defender, target=attacker, `cost="reaction"`,
  `policy_riders=False`, `masteries=["sap"]`, `extra_flat_damage`=CHA). Reuses
  normal attack resolution; the counter's damage counts as our DPR.
- **`extra_flat_damage`** — new field threaded `Choice → AttackRollEvent →
  DamageEvent`, summed in phase 5 (does NOT scale on a crit). Implements
  Brutality::bleed's +CHA flat damage.
- **`policy_riders: bool` on `AttackRollEvent`** (default True) — when False the
  scheduler passes `decider=None, hit_decider=None`, so a rider attack (the
  counter) carries its own bleed and never spawns Wrathful Smite / bluff.
  (on_miss was already gated off reaction-cost attacks via `is_aoo`.)

*Reaction model (locked):* the parry's once-per-round limit is **policy-gated**
(`WarAngelPolicy._last_parry_round`, reset in `on_combat_start`), **decoupled
from the once-per-combat AoO** per the guide's explicit "in addition to … no
other demands on our reaction" assumption. **No `TurnEndEvent` / engine
reaction-economy was built** — that stays deferred until a reaction-*gating*
status forces its shape (see Open threads). The "no-smite-on-AoO" gate
(`cost=="reaction"`) is also unchanged; the counter relies on `policy_riders`,
not on that gate.

*Validation story (+4.2% overshoot is intentional).* Two user-approved EV-max
choices push us above the guide's 37.96, both within tolerance and documented:
(i) **full-EV-max counter budget** — in the threshold-HP model healing is free,
so ALL 5 Second Winds (+ the free 1/LR) are available for counters
(`flourish_counter = 6/day`), and we counter on **every** parry-flip (~4/day
opportunity < 6 budget → non-binding) rather than reserving ~3 as the guide does;
(ii) the gentler **40% targeting** (vs the guide's 50%) already in play since L13,
which lifts Bless uptime. No hidden modeling error.

**Phase D was staged:** D1 = L11 (data row) → D2 = L12 (two-tier Magic Weapon,
content-only) → D3 = L13 sub-staged (D3a = save machinery + Bless as pure
offense buff with the enemy not yet attacking; D3b = the incoming-damage loop).

**D1 (L11) — DONE & VALIDATED (33.665 vs 33.70, −0.1%).** Pure data row: Mage
Slayer's +1 DEX doesn't touch CHA-based attacks, so L11 = L10 stats with
`enemy_ac` 16→17 (the AC bump is the whole reason DPR drops). No policy/engine.

**D2 (L12) — DONE & VALIDATED (38.074 vs 38.11, −0.1%).** Two-tier Magic Weapon:
`DurationBuffTracker` carries a per-cast value; `WarAngelDailyPlan` casts +2
(L3 slots) first while they last, else +1 (L2 slots), syncing the strongest
active tier. Content-only; combat tactics unchanged → no policy edits.

**D3 (L13) — DONE & VALIDATED (35.145 vs 34.68, +1.3%, within soft ±10%).**
The defensive bundle. New engine primitives (all backward-compatible — L1–12
unchanged):
- **Rolled-dice modifier** — `Modifier.dice` + `ModifierStack.roll_dice` +
  `Entity.roll_bonus`, folded into `resolve_attack_roll`/saves on the resolution
  path only; the pure `stat()` the policy reads stays dice-free. (Bless +1d4.)
- **Saving-throw verb** — `resolve_saving_throw(entity, save_stat, dc, rng, adv)`
  = d20 + flat save + rolled-dice bonus vs DC. Called inline for concentration;
  a `SavingThrowEvent` wrapper is deferred until scheduled saves are needed
  (frightened / enemy save-spells) — see Open threads.
- **Concentration** — a dedicated `Entity.concentration` field (NOT a tick-status;
  it's not tick-expiring and is global-per-entity). In `resolve_damage`, a
  concentrating entity taking damage forces a CON save (DC = max(10, dmg//2));
  failure drops the spell's modifiers + clears the field. `concentration_checks`
  / `concentration_breaks` telemetry counters added (design §8).
- **Enemy strikes back** — `WarAngelEnemyPolicy` (+11, 3 attacks, 28 flat dmg)
  with pre-rolled per-attack targeting; flat damage via `damage_dice (0, …)`
  (resolve_damage now skips a zero-die pool). Sap disadvantage on its attacks
  reuses the existing `sapped` status. `make_training_dummy` gives the dummy the
  attack profile and `make_day_runner` a policy from L13.
- **Brutality::bluff save-advantage half** (deferred since L8) — bluff now also
  sets `advantage_next_save` via `HitResponse.self_status_on_hit`, consumed by
  the concentration save.
- **DPR source fix** — validation now reads damage dealt TO THE DUMMY
  (`DayResult.damage_received_by`), not all-sources total, so the enemy's damage
  to us no longer inflates DPR. Equivalent for L1–12 (only the char dealt damage).

*Validation story (per the agreed concentration-check comparison):* at the
guide's own **50% targeting we make 9.06 concentration checks/day** — squarely
in the guide's stated ~9–10 — confirming the loop is calibrated. We operate at
**40%** (party of 4; 7.48 checks/day, ≈9.06×40/50). The +1.3% DPR bias vs 34.68
is fully explained by two user-approved choices: **allowing Action Surge attacks
on round 1** (the guide assumes a full round-1 sacrifice) and the gentler 40%
targeting (higher Bless uptime). No hidden modeling error.

*L1 spell-slot audit (verified, 8k days).* Bless (cast at each combat start) and
Wrathful Smite both draw on the level-1 pool, so we checked for overuse. Result:
**no overuse is possible or observed.** `spell_slot_1` consumes exactly 4.000/day
(its cap); zero blocked-consume attempts and zero "consume failed" warnings —
the `available()>=1` guard in `_sync_bless` and the scheduler's pre-consume
validation hold. free_cast (1.0/day) and pact (~1.0/day) are consumed by smite
only, per the `free_cast→pact→spell_slot_1` priority. The flagged smite-steals-a-
Bless-slot interaction is real but negligible: Bless is skipped ~0.019×/day (≈once
per 53 days). The model is in fact *conservative* — total L1-equiv ~6.0/day vs an
~8 ceiling, and smite fires ~2.0/day (vs the guide's assumed ~3) because War
Priest + Shield of Faith dominate the bonus action. No reservation logic needed.

`make_war_angel(14)` is the next-raises level.

**Phase D design decisions (locked this session, before any L13 code):**
- *Frightened — DEFERRED & flagged.* Wrathful Smite's WIS-save/frightened rider
  is out of scope for L13 (guide downplays it: smite drops to 3/day, high-CR
  immunity common; only second-order DPR effect via fewer enemy hits → fewer
  concentration checks). **When we DO build it, model a tunable random chance
  (default 50%, adjustable) that the enemy is frightened-immune — discuss this
  design at that point.** See Open threads.
- *Enemy 50%→40% targeting.* Model incoming damage with **pre-rolled per-attack
  targeting + untracked party** (enemy makes 3 attacks/turn; at `on_combat_start`
  pre-roll which target each — char vs party; party-aimed = no-op for our metrics;
  keeps `decide()` dice-free, preserves per-attack discreteness for separate
  concentration checks). **Per-attack char-target probability = 40%** (party of 4,
  more reasonable than the guide's 50%) — flagged as tunable. **At D3b, compare
  our actual concentration-check count/day to the guide's stated ~9–10 (and ~12
  under the 75%-all-3-attacks sensitivity case).**

**L8 engine widening:** `HitResponse` gains `extra_masteries` + optional `action_cost`;
hit_decider returns `(dice, masteries)`; hit_decider fires before `apply_masteries_on_hit`.
**L8 policy:** setup-first emit, bluff+smite compose in one `HitResponse`, `_bluffed_this_turn` flag.
**L9 policy:** TS bluff unlocked for rounds 1-3 (L9+ gate); T4 waste check extended.
**L10 policy:** Extra Attack — 2 attacks per action and surge; True Strike dropped;
T4 action bluff unblocked (attack 2 immediately consumes vex). **180 tests green.**

**Phase D (L11-13)** — defensive bundle: saves (`SavingThrowEvent`), frightened
condition, concentration, bless, war god's blessing. This is the first level where
incoming damage feeds back into DPR (concentration checks → bless uptime). Significant
new engine work. Read CLAUDE.md §"Phase D" and the Open Threads before starting.

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

**~~Known deferral inside this scope: Flourish Parry (lvl 14)~~ — LIFTED.** The
`intercept_event` decision point is built (Phase E stage E1, L14); validation now
extends through L14. See "Open threads" for the remaining deferred list
(TurnEndEvent / enemy reaction-economy, scheduled saves, spell-aggressive enemy,
weapon slot, light/nick, etc.).

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

- **Phase C — levels 8–10. ✓ DONE & VALIDATED.** Results (30k days, soft ±10%):
  L8 23.48/23.36 (+0.5%), L9 27.60/27.59 (+0.0%), L10 35.34/35.32 (+0.1%).
  L1–9 unchanged. **180 tests green.**
  *L8:* engine widening — `HitResponse` gains `extra_masteries` + optional `action_cost`;
  hit_decider returns `(dice, masteries)` tuple; hit_decider fires before
  `apply_masteries_on_hit`. Policy: setup-first emit (vex chaining); bluff+smite compose
  in one `HitResponse`; `_bluffed_this_turn` flag; smite priority free_cast→pact→L1.
  *L9:* TS hits bluffable at rounds 1-3 (L9+ gate); T4 waste check extended to include
  action cost.
  *L10:* Extra Attack — 2 attacks per action and surge; True Strike dropped; T4 action
  bluff allowed (attack 2 immediately consumes vex in same turn).
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

**Per-level EV re-examination (agreed — do this BEFORE coding each new level).**
When we move to a new level, an early step is to re-examine the prototype/build-guide
combat policy through two lenses, and reformulate it as needed:
  1. **EV maximization** — does the prototype's plan actually maximize expected DPR,
     or is some of it transcription / suboptimal husbanding? Cost out the marginal
     value of each resource use (advantage on which attack, which slot, which target)
     before accepting the prototype's sequencing.
  2. **Our modified day model** — the prototype assumes a fixed schedule (e.g. "PoH
     after combat 1, SR after combat 3" and a per-combat MW coin-flip). Our DayRunner
     instead uses **rng-driven SR/PoH placement** and a **day-clock MW duration model**,
     and our policies are **greedy + rest-timing-agnostic** (spend a resource whenever
     a charge exists; "mode" is emergent from what's available, never a combat index).
     Re-derive the plan under our model — it often *collapses* the prototype's
     per-combat branching (see the L8 worked example: combat-index branching and the
     "husband" flag fell out entirely). Match OUR formulation over the prototype's.

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

- **Scaling typology — RECORDED (2026-06-12, session 4); framework deliberately
  NOT generalized yet.** Discussed with the user after primitive #3: rather than
  treat the two dice-scaling "modes" (cantrip / uniform) as two kinds of ability,
  they decompose into three INDEPENDENT axes — **driver** (`level_reference`:
  slot/character/class level or a spent-resource count), **step function**
  (linear `increment`/`every_n_levels`/`base_level`, or a threshold list like
  cantrip's `[5,11,17]`), and **scaled quantity** (dice count / target count /
  #beams / duration). Full typology written up in `design/ability_schema.md` §4.5
  ("Scaling typology"). **Decision: keep building forcing-function-driven** — the
  current `_resolve_scaling_dice` (dice count × linear-or-threshold × any driver)
  is the right amount of machinery for every selected build; a generic framework
  would generalize 2 cases into a framework with 2 cases and unblock nothing. The
  typology confirmed the policy/resolution boundary is correctly placed (the
  driver value is always policy-supplied via context; "how much to spend" stays
  Python, "value → dice" stays data — so `base_level` belongs in the dice block).
  **Two cheap generalizations it surfaced, each forced only when a build needs
  it:** (a) lift the cantrip threshold list from the hardcoded
  `_CANTRIP_THRESHOLDS` to data (`scaling: thresholds`, `breaks: [...]`) when the
  first non-cantrip threshold scaler (Rage-style) appears; (b) **target-count
  scaling** (upcast Command / Charm Person) is blocked on the unbuilt multi-enemy
  / spatial model, NOT on scaling design — and is rare in the current build corpus
  (Voice of Heaven, the one build that leans on it, is itself deferred for the
  same multi-enemy reason). Cost-driven drivers (focus/ki/sorcery points) already
  work for free — they're just another `level_reference` key in `context`.

- **Idle Aid L2 slot → upcast Wrathful Smite — MEASURED, deliberately NOT
  implemented (known conservatism).** Spell-slot audit at L15 (5000 days,
  consume-counting): `spell_slot_3` 2.999/3 (MW eats all 3 ~every day),
  `spell_slot_2` 1.911/3, `spell_slot_1` 4.000/4 (all → Bless), free_cast 1.0,
  pact 0.996. Two findings:
  - *The "overlapping combats free a residual L3 slot" effect is negligible* —
    only **5/5000 days (0.1%)** used <3 L3 slots. Combat windows are 240 min wide
    but Magic Weapon lasts 60, so combats almost never fall within 60 min of each
    other → MW lapses and is recast each combat, burning all 3 L3 slots.
  - *But there is a structural ~1.09 residual L2 slot/day* — the **Aid slot** the
    guide earmarks, which we model as HP-only → **zero DPR in the threshold
    model, every day.** It could become **one extra 2d6 upcast Wrathful Smite**
    (L2 → 2d6), and there's bonus-action room: **1.468 "slot-starved smite
    opportunities"/day** (BA free + we hit, but no smite slot left). free_cast and
    pact are *fixed* level-1 (Shadow-Touched / warlock-01) so they can't upcast —
    the residual L2 is the only fungible higher slot.
  - *Estimated gain ≈ +0.5 DPR* (~1.09 conversions × ~7 dmg ÷ 16 rounds).
    **Decision (user, this session): DOCUMENT, don't implement.** It would (a)
    widen an already-positive bias (L15 +5.7% → ~+7%), (b) retroactively touch
    L13/L14 (same idle Aid slot) and reopen two validated levels, and (c) need a
    reservation mechanism (cleanest: a dedicated `smite_upcast_slot: (1, 0)`
    resource so the in-combat policy can't starve the daily plan's later MW +1
    cast). The audit's real value was confirming **no large unmodeled DPR source
    is hiding** — the gap is ~0.5 DPR. Revisit only if a later level's validation
    runs LOW and needs the headroom, or if we do a final EV-max purity pass.

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
  needs them. `mastery_override` (Tactical Master, lvl 16) is **WIRED** — consumed
  by the scheduler (scheduler.py:461) and used by the L16 policy to override the
  rapier's vex with sap on one attack/turn.

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
  - **Still deferred after L14 (deliberately).** L14's Flourish Parry is the first
    reaction on the *enemy's* turn, but it did NOT force a `TurnEndEvent` or an
    engine reaction-economy: the parry's once-per-round limit is **policy-gated**
    (`WarAngelPolicy._last_parry_round`), decoupled from the AoO per the guide. A
    real per-entity reaction resource + `TurnEndEvent` is still only forced by a
    reaction-*gating status* (stunned) or an end-of-turn proc — neither is in the
    War Angel arc. Revisit then.

- **Concentration — BUILT (Phase D), with a simplification.** Concentration lives
  on `Entity.concentration` (a dedicated field, since it is global-per-entity and
  NOT tick-expiring) and is dropped by `_check_concentration` in `resolve_damage`
  on a failed CON save. **Simplification taken at L13:** bless is modeled as a
  *combat-clock* buff applied fresh at each combat start (cast in the daily plan's
  `before_combat`, dropped only by a failed save), NOT on the day clock — bless's
  1-min duration never spans two of our 1-min combats anyway, so the day-clock
  half was unnecessary. If a *longer* concentration spell (10 min, e.g. a future
  spirit guardians / shield-of-faith-as-concentration build) needs to persist
  across combats, add the day-clock duration half then (the `DurationBuffTracker`
  is ready). Shield of Faith here is non-concentration (War God's Blessing).

- **Saving throws — BUILT (Phase D).** `resolve_saving_throw(entity, save_stat,
  dc, rng, adv/disadv, reroll_decider=None)` in `verbs.py` = d20 + flat save +
  rolled-dice bonus vs DC. Used inline for the concentration check. **Failed-save
  reroll BUILT (L16, Indomitable):** the `reroll_decider` hook + `Policy.
  on_failed_save` + `Scheduler._make_save_reroll_decider` let a policy reroll a
  failed save with a bonus (the new result stands, RAW). `dex_save` is now also
  modeled (cosmetic, on the L15+ character) alongside `con_save`. **Still
  deferred:** a *generic* `SavingThrowEvent` with an arbitrary on-fail payload
  (frightened, enemy save-spells) — its shape waits on a real non-damage case.
  **UPDATE (2026-06-12, session 2): the attacker-side save IS now built** — see
  the "Save-FOR-damage" Done entry. `spell_save_dc` is a live attacker stat and
  `SaveDamageEvent` is the first *scheduled* save event (damage-specialized on
  purpose; generalize when frightened / enemy-save-spells force a non-damage
  payload). `resolve_saving_throw` is reused unchanged.

- **Wrathful smite — frightened/save half (deferred to Phase D).** Wrathful smite
  also forces a WIS save vs. our spell DC; on a failure the target is frightened
  (disadvantage on its attacks; can't move toward us). **Decided:** we build only the
  *damage* half (1d6 on hit, added via the on-hit decision point) in Phase B, and defer
  the save + frightened condition to Phase D. Rationale: in the threshold-HP model frightened changes only
  *incoming* damage, which does not affect our DPR until level 13, where it loops back
  *second-order* (fewer enemy hits → fewer concentration checks → higher bless uptime).
  Building a save system at level 6 would change no DPR number before level 13, and
  saves are needed at 13 anyway (concentration *is* a save), so they bundle cleanly.
  **Re-confirmed deferred at Phase D L13 planning** (guide downplays it there too).
  **Design note for when we build it:** model a *tunable random chance* that the
  enemy is **frightened-immune** (default 50%, adjustable) — many high-CR creatures
  are immune, and this gates whether the smite's frightened effect ever lands.
  Discuss the exact treatment (per-combat roll? per-target archetype tag?) at that
  point rather than baking it in now.

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
  - **L14 update:** the Flourish Counter is a reaction-cost attack that must NOT
    spawn riders, but rather than lean on this `cost=="reaction"` gate (which the
    AoO still relies on for bluff/smite suppression) it uses the new
    `AttackRollEvent.policy_riders=False` flag — the scheduler skips building the
    actor's on_miss/on_hit deciders entirely for that attack. The two mechanisms
    are complementary; the gate is still in place and still non-permanent.

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
