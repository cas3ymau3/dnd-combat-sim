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

> **Currently disabled (re-enable before exit):** none reported (session 21 toggle
> recommendation re-made; nothing confirmed disabled). **Session scope (2026-06-18,
> session 21) — DONE (SUBSTRATE #7 — 7c-ON-SUMMON):** wired the built 7c ally-effect
> machinery (session 19) ONTO the 7a primal companion (session 20) — the summon as a
> **buff / redirect / protect target**. **Scope settled with the user up front (A,
> full slice).** Per-feature ACCESS finding: the full kit isn't online at the L4
> summon row — only Protection is (fighter-1); Bless is char L6, Aid + Warding Bond
> char L8 (guide 32:436-471). So built RAW-faithfully at a **new char L8 row**
> (Fighter-1 / Ranger-4 / Cleric-3 Trickery), mirroring the Fire-Shield→L15 access
> discipline (user picked "wire onto L4" by mis-click, then corrected to "your
> recommendation" = the L8 row). **The vehicle:** `BeastEffectPolicy`
> (`src/builds/silvertail.py`) — a PASSIVE defender policy registered for the beast
> (`decide → []`, so the beast is still COMMANDED by the master), carrying the 7c
> rider + pre-cast payload: **warding bond** (+1 AC/+1 saves + RESISTANCE TO ALL +
> redirect the post-resistance taken amount to the master), **protection** (impose
> disadvantage on attacks vs the beast), **bless** (+1d4 to the beast's attacks/saves
> → raises its OUTGOING DPR, concentration on the master), **aid** (+5 HP max/current
> — DPR-inert under the threshold model). The enemy now **STRIKES THE BEAST** (typed)
> so the defender effects do real work; the combat-clock payload is re-applied each
> combat via `on_combat_start` (the Fire Shield / Bless re-cast pattern — `DayRunner`
> sweeps combat-clock buffs at every boundary). **Engine seam (resolves the session-19
> deferral):** `Entity.damage_response_for` now honors a reserved **`"_all"` key** —
> "resistance to all damage" applies to any TYPED hit (still None for untyped),
> feeding the same 2024 dominate/cancel rules; `ScriptedEnemyPolicy` gained an optional
> `damage_type` (backward-compatible default None → War Angel / Scion byte-identical).
> **Rules verified BEFORE modeling (per-feature ritual, web + guide 32):** Warding Bond
> / Aid / Bless / Protection 2024 text + ACCESS levels. **455 tests green (+11).**
> Branch `feature/substrate-7c-on-summon` → confirm before merging to main. ATTACK-
> TAXONOMY NOT forced (the enemy melee-attacks the beast; no melee/ranged gate yet) —
> flagged, untouched. Carry-over flag (ii) `snapshot.allies=()` **NOT forced** (all
> policies use explicit refs). **Forward-looking:** the charge-PRONE→advantage work is
> entangled with **shocking grasp denying the enemy's reactions (no OA)** — the build
> kites in/out + charges repeatedly only because shocking grasp suppresses the OA; the
> on-hit-applies-status seam + a reaction-denial status + an opportunity-attack model
> are ONE connected control cluster (user note, session 21). **Per-feature reflection
> DONE (2026-06-18 discussion):** three forward items recorded (no rework) — (1)
> uncommanded summon → Dodge (reuses `impose_disadvantage`; build when forced); (2) full
> day-clock integration of `duration="day"` into `cast_effect` (a partial day-clock —
> minute clock + `DurationBuffTracker` — already exists; War Angel hand-wires it); (3)
> summon DEATH at 0 HP + per-character recast policy → makes aid/warding/protection
> DPR-relevant (lifts the "aid inert" caveat) + needs real per-CR enemy damage (decision
> #12). **NEXT (user decision: summon-death FIRST, then 7b): SUMMON SURVIVAL & DEATH**
> (item 3b) — wire `is_functionally_dead` → `destroyed` for summons + a recast decision
> point + real per-CR enemy damage; THEN **7b zone/emanation** (Spirit Guardians, §3.1
> zonal model — the LAST unbuilt #7 sub-kind).
>
> **Session scope (2026-06-17,
> session 20) — DONE (SUBSTRATE #7 — 7a SUMMON):** built the MINIMAL 7a slice — the
> **Blessed of Silvertail** (guide 32) at **char L4** with its **PRIMAL COMPANION as
> a `create_entity`'d ACTOR**, COMMANDED on the master's turn, in its own per-summon
> DPR column. **Scope settled with the user up front (3 questions):** (1) **L4
> beast-only** (the prompt's minimal — verbs + commanded actions + the summon column;
> NO 7c-on-summon); (2) command model = **fully commanded on the master's turn**
> (design-literal — the controller's policy emits the beast's Choice, attributed to
> the beast, command costs the master's BA — not the lighter own-turn abstraction);
> (3) lifecycle = **build `create_entity` as a real mid-combat verb but invoke it at
> DAY START out of combat** for the silvertail (the permanent companion persists the
> day; defer *testing* the mid-combat conjure-spawn until a build forces it). **The
> engine primitive:** (a) **`Choice.actor`** — the COMMANDED-action override
> (design.md §1: controlled allies act on their controller's turn): the cost (action
> economy + resources) is drained from the CONTROLLER (the master's Bonus Action
> commands the beast), but the spawned event's actor is the commanded entity, so the
> attack uses ITS stats and is attributed to it — the **summon DPR column falls out
> of the per-(source,target) ledger for free**; (b) **`src/summons.py`** — `SummonSpec`
> + **`create_entity`/`destroy_entity`** (verb 12) on an (entities, policies) roster,
> + `Scheduler.add_entity`/`remove_entity` (live-ledger sync) + the cast_effect
> **`summons`** payload (the general mid-combat verb, lightly exercised); (c)
> **`Entity.remove_effect` winks out summons** keyed to `effect_source` (a `destroyed`
> flag + `note_effect_summon`; the scheduler skips destroyed entities' turns) —
> design.md §1 "controlled allies wink in/out". **Build (`src/builds/silvertail.py`,
> L4 only):** master (Air Genasi Fighter-1/Ranger-3, AC 19, **shocking grasp = the
> build column**) + **Beast of the Land** (AC 16, HP 20, Beast's Strike 1d8+2+WIS,
> to-hit +5, +1d6 charge — verified vs 2024 Roll20/D&D Beyond + guide 32:326 BEFORE
> modeling); `SilvertailPolicy` commands the beast via the master's BA; the runner
> summons it at day start via `create_entity` and reports the **build column,
> summon column, AND party total SEPARATELY** (user decision s17 — the beast
> ≈121.5/day dominates the master's cantrip ≈43.9/day, and the party total 165.4 is
> exactly their sum: the case "report both" exists for). **444 tests green (+12.)**
> Branch `feature/substrate-7a-summon` → confirm before merging to main. Per-feature
> ritual: Beast of the Land's 2024 statblock web-verified BEFORE modeling; reflection
> done — user chose **no ritual change**, with THREE forward-looking flags captured
> (below). **DEFERRED (flagged):** charge PRONE → advantage on shocking grasp (needs
> an **on-hit-applies-status seam** — a hit installs a condition the later roll reads);
> the **7c effects ON the beast** (warding bond redirect / protection / aid retarget
> — the beast as a buff/redirect target); higher rows; 7b zone; mid-combat conjure
> summon lifecycle (testing). The scheduler's **`snapshot.enemies` labels every
> non-actor (incl. friendlies) as an enemy and always sets `allies=()`** — harmless
> today (policies use explicit target refs) but a known seam to fix when a policy
> must read its allies. **Revisit commanded-vs-DPR-faithful** before the next summon
> slice now that the commanded model is concrete. ATTACK-TAXONOMY untouched. **NEXT:
> 7c-on-summon** (the beast as a buff/redirect/protect target — connect 7a to the
> built 7c machinery) and/or **7b zone/emanation** (Spirit Guardians — the §3.1
> zonal model).
>
> **Session scope (2026-06-17,
> session 19) — DONE (SUBSTRATE #7 — 7c ALLY-EFFECTS):** built the SECOND 7c slice —
> `cast_effect` / intercept riders whose target is an ALLY, on the session-18
> multi-entity foundation. **Three effects, each verified against 2024 text FIRST**
> (warding bond / protection style / sanctuary / bless / aid): (1) **ally-buff
> retarget** (Bless/Aid) — `cast_effect target=ally` lands the existing #1/#3/#4
> payloads on the ally entity, **NO engine change** (the cast_effect branch already
> installs on `choice.target or actor`); (2) **warding bond** (redirect) — the ally's
> `on_incoming_hit` returns a `RedirectSpec`; `resolve_attack_roll` threads it onto the
> `DamageEvent` and `resolve_damage` spawns a copy of the taken amount onto the caster
> (attributed to the original attacker, never recursing); (3) **protection fighting
> style** (disadvantage) — `impose_disadvantage` re-rolls the attack with a second d20,
> flipping the hit on a miss (P(hit)² exact; crit kept only on a double-20); (4)
> **sanctuary** (save-or-negate) — `negate_save` makes the ATTACKER save vs the
> caster's DC or the attack is negated. **The load-bearing engine change:** adding
> warding-bond redirect was the trigger that **REFACTORED the `on_incoming_hit`
> positional 3-tuple (`ac_bonus, counter, reactive_damage`) into the single
> `InterceptResponse` object returned by the decider** — the session-12 engine-seam
> note paid off (new riders are fields, not tuple positions; two test files that
> hand-built 3-tuples updated). **Vehicle:** Scion + a synthetic ally (`make_ally` +
> `AllyEffectPolicy` + `make_ally_effects_runner`) — silvertail deferred to the 7a
> summon slice (user decision: lighter first; silvertail stands up at 7a as the
> eventual 7a/7b stress vehicle). **432 tests green (+13).** Branch
> `feature/substrate-7c-ally-effects` → confirm before merging to main. Per-feature
> ritual: all five spells' 2024 wording web-verified before modeling; reflection done
> — user chose to KEEP the reactor-economy abstraction (the protector/caster reaction
> is folded into the ally's self-gated response, like Fire-Shield thorns; multi-reactor
> contention unmodeled — recorded as a known simplification) and noted the "resistance
> to ALL damage" per-type gap. ATTACK-TAXONOMY NOT forced (no rider gated on
> melee/ranged) — flagged, untouched. **NEXT: 7a summon** (silvertail primal companion
> — `create_entity`/`destroy_entity` an Actor; commanded actions; summon DPR column;
> summon as a buff/redirect target); then 7b zone/emanation.
>
> **Session scope (2026-06-17,
> session 18) — DONE (SUBSTRATE #7 — 7c MULTI-ENTITY FOUNDATION-MIN):** built the
> FIRST SLICE of substrate #7 (the last `cast_effect` buff substrate) — the
> multi-entity-combat foundation + the 7c multi-entity-targeting sub-kind. **Three
> pieces:** (1) a PASSIVE PARTY MEMBER (`make_party_member` — one infinite-HP
> friendly pool, design.md §3.6; an AC so attacks resolve, NO policy → never acts);
> (2) `ScriptedEnemyPolicy` MULTI-ENTITY mode — a weighted friendly roster
> (`roster=[(char, w), (party, w)]`), §3.5 trait-weighted (melee Scion 2 : party 1),
> pre-rolled at `on_combat_start` so `decide()` stays dice-free (CLAUDE.md #7/#9);
> (3) per-(source,target) DPR accounting — `Scheduler.damage_by_source_target`
> ledger → `DayResult.damage_by_source` / `damage_source_to` / `party_total`, so the
> runner reports the build's OWN column (source==character) AND a party/roster total
> SEPARATELY (the session-17 user decision). **Wired on the Scion at L15 via
> `make_day_runner(..., with_party=True)` — DEFAULT False keeps the 1-vs-1 scenario
> bit-identical** (the build column `damage_by_source(char)` == the legacy
> `damage_received_by(dummy)`, 619==619; all 414 prior tests untouched). **HEADLINE
> VALIDATION (consistency/sanity, FakeRNG + directional DPR — NOT number-matching):**
> with the enemy splitting attacks, Fire Shield's thorns fire on a FRACTION of
> incoming hits → its DPR drops (32.5→31.2) while pre-cast FoM's own-hit riders are
> untouched (≈31.8) → **the pre-cast FoM loadout OVERTAKES Fire Shield** (solo gap
> +0.44 → party gap −0.56) — the session-16 ~0.5 near-tie finally REVERSES, closing
> both the substrate-#7 gap and the session-16 thorns-over-count artifact. **419
> tests green (+5).** Branch `feature/substrate-7c-multientity-foundation` → confirm
> before merging to main. SCOPE held to 7c foundation-min ONLY (no summons/zones/
> ally-buff/redirect — those are later slices). Per-feature ritual: the "new
> mechanic" was the §3.5 enemy-targeting weighting + the §3.6 party-member model —
> both design.md contracts (not D&D rules text), re-read & honored; reflection
> pending user input. ATTACK-TAXONOMY NOT forced (the foundation runs in the implicit
> single melee zone; melee-vs-ranged didn't yet matter) — flagged, untouched.
> **NEXT: 7c ally-effects** (bless/aid retarget onto an ally; warding-bond REDIRECT —
> the trigger to refactor the `on_incoming_hit` 3-tuple into a response object;
> protection/sanctuary PROTECT) via the silvertail build; then 7a summon, 7b zone.
>
> **Session scope (2026-06-17,
> session 17) — DONE (SUBSTRATE #7 DESIGN NOTE — DESIGN-ONLY):** wrote the design
> note for the LAST unbuilt `cast_effect` buff substrate — zone / summon /
> multi-entity — into `design/buff_primitive.md` (no engine code; 414 tests green,
> unchanged). **Scope settled with the user up front (4 questions):** (1)
> **design-only** (corpus survey + note, no code); (2) **multi-entity targeting**
> is the primary focus / first-to-build sub-kind; (3) **silvertail (guide 32)** is
> the survey + validation vehicle; (4) DPR with multiple friendly entities = report
> **both** the build's own column AND a party/roster total **separately**. **The
> core realization:** #7 is NOT a new payload bolted onto `cast_effect` — it is the
> `cast_effect` ON-RAMP to the multi-entity / spatial model already specified (but
> unbuilt) in `design.md` §1 (objects vs actors; controlled allies; party 3-HP-pools),
> §3.1 (zonal model), §3.5/§3.6 (enemy targeting + party), verbs 11/12. It
> decomposes into **7c multi-entity targeting + ally-effects (lightest)**, **7a
> summon (own-HP ally)**, **7b zone/emanation**, on a shared multi-entity-combat
> foundation. **Sequenced 7c→7a→7b**, each gated design-first. **The first slice
> (next session) = 7c foundation-min** (passive party member + enemy split-targeting
> + per-(source,target) DPR accounting) — which ALSO fixes the session-16
> Fire-Shield thorns over-count artifact (predicted: FoM overtakes Fire Shield once
> incoming hits spread across the party). **Silvertail is the stress test** (forces
> summon + emanation + buff-aura + ally-buff + redirect + protect + targeting-split
> with NO envelope growth — the design-first "hard case", mirroring Fire Shield for
> #4/#5). Per-feature ritual: no NEW mechanic modeled (design note) — rules-verify
> half N/A; the surveyed spells are pointers, exact wording to be verified at each
> build session. Branch `design/substrate-7-zones-summons-multientity` (pushed) →
> confirm before merging to main. **NEXT: build the 7c foundation-min slice** (see
> the "Substrate #7" section of `design/buff_primitive.md`).
>
> **Session scope
> (2026-06-17, session 16) — DONE (PRE-CAST ASSUMPTION TOGGLE):** made "is this
> combat-long buff PRE-CAST (before initiative, free) vs CAST IN COMBAT (a real turn
> cost + concentration)" a tunable SETTING on the Scion's L15 4th-level loadout (FoM
> + Fire Shield), rather than the session-15 hard-coded branch. **Scope settled with
> the user up front (4 questions):** setting lives as a **policy/make_day_runner
> param** (like `fourth_level_spell`); rng mode = a **single probability p, rolled
> once per combat** through the seeded dice channel (a percentile d100) in
> `on_combat_start` — NOT in decide(); applied to **just the L15 4th-level spell**
> (not Shillelagh/Starry-Form/Bless); validation = **three-mode ordering + FoM
> re-passing Fire Shield**. `precast_mode` ("always"/"rng"/"never"/None) +
> `precast_prob` thread through `StarfireScionPolicy` + `make_day_runner`. `decide()`
> emits each 4th-level cast as a free turn-1 install (pre-cast, cost="none") or a
> real in-combat action/BA cost; Shillelagh's cast-round + Dragon's cost track the
> same per-combat flag. **None mode = each effect's LEGACY default** (Fire Shield
> pre-cast, FoM in-combat) and draws **NO dice**, so the existing RNG stream + every
> prior DPR/ablation test stay **bit-identical** (only "rng" mode touches the
> stream). **MODELING FINDING (prompt's hypothesis only HALF-confirmed):** the three
> modes order — always **32.1** > rng@0.5 **30.5** > in-combat **29.6** — but
> pre-casting FoM narrows its gap to the Fire-Shield loadout (~32.5) from ~3.0 to
> only **~0.5 (a near-tie), NOT a full reversal**, in the single-dummy model; the
> residual is Fire Shield's thorns over-count (lone dummy always targets us — the
> SEPARATE multi-entity arc). So pre-cast alone ties FoM to Fire Shield; the full
> re-pass needs the multi-entity fix too. **414 tests green (+8).** Branch
> `feature/precast-assumption-toggle` → confirm before merging to main. Per-feature
> ritual: no NEW mechanic (a modeling knob; FoM/Fire-Shield/Dragon rules verified
> sessions 13-15) — reflection done, user chose **no process change**. MCP-toggle
> recommendation re-made. **NEXT: substrate #7 (zones/summons / multi-entity)** via
> the silvertail's-blessing build — the last unbuilt buff substrate AND the fix that
> lets FoM truly pass Fire Shield (design-survey first; multi-session).
>
> **Session scope
> (2026-06-17, session 15) — DONE (FoM CONCENTRATION FOLLOW-UP):** retired the
> session-14 FoM debt — modeled **Fount of Moonlight as a real in-combat cast WITH
> concentration**, plus the **Starry-Form Dragon** concentration-save floor (the
> Scion's FIRST in-combat concentration). **Scope settled with the user up front (4
> questions):** task (A) the FoM follow-up (not (B) zones); Dragon modeled as a
> **full second Starry Form** (Wild-Shape cost + turn-1 BA, not just the floor
> flag); FoM **back to a real turn-1 Magic-action cast** (turn 1 = 0 damage); FoM +
> Fire Shield now **SHARE the single druid-7 4th-level slot** (over-count dropped).
> Engine seam: `resolve_saving_throw` gained a **`d20_floor`** (the substrate-#3
> SAVE-FLOOR grant — designed-in since session 11, first consumer now); Dragon's
> turn-1 BA `cast_effect` installs a `concentration_save_floor`=10 status that
> `_check_concentration` reads (guide 41:308 "treat 9 or lower as 10"). Also fixed
> a real bug: a broken concentration only dropped MODIFIERS — added
> **`Entity.remove_effect`** (modifier + damage-response #4 + statuses #3, tracked
> by source) so FoM's radiant resistance + any granted status drop WITH it (routed
> `_check_concentration` AND `clear_combat_buffs` through it). Build: FoM is a
> turn-1 `cost="action"` concentration cast_effect (installs the radiant resistance,
> sets concentration); the on_hit +2d6 radiant rider now gates on
> **concentration being held** (`character.concentration == "fount_of_moonlight"`),
> so it drops the instant a save breaks; the FoM combat's turn-1 BA is Dragon (guide
> 41:779 `BA:starry-form(dragon) + magic-action:fount-of-moonlight --> 0`),
> Shillelagh slides to turn 2. New `slot_4th` (1/LR) + `wild_shape` + `con_save` on
> the L15 row; `fourth_level_spell` selector ("fount_of_moonlight" default /
> "fire_shield") threaded through the policy + `make_day_runner` — exactly one
> loadout casts per day (the slot they compete for). **MODELING FINDING:** the
> honest cast cost (turn-1 = 0 damage, occasional breaks) + the shared slot (Fire
> Shield no longer ALSO in the default loadout) drop L15 DPR from session-14's
> ~36.2 to **~29.6** — near, not above, session-13's Fire-Shield-only ~29.7; the
> stale "rises above 29.7" test was reframed to FoM-loadout > unused-4th-slot (net
> still positive) + < ceiling. **406 tests green (+7).** Branch
> `feature/fom-concentration-dragon-form` → confirm before merging to main.
> Per-feature ritual honored (Dragon 41:308 + FoM concentration 41:779 re-verified
> BEFORE modeling). MCP-toggle recommendation re-made. ATTACK-TAXONOMY untouched
> (no new attack tag this session). **Substrate #7 (zones/summons) is now the ONLY
> unbuilt buff substrate** — the next big design step (task (B)).
>
> **Session scope
> (2026-06-16, session 14) — DONE (substrate #6 — OUTGOING RIDERS):** built the
> `cast_effect` **outgoing predicate rider** substrate (#6, the next item in the
> buff-primitive "Next-steps sequence") with first consumers on the Starfire Scion
> at L15: **Fount of Moonlight** (+2d6 radiant on every melee hit incl. unarmed,
> FUELED by Fueled Spellfire for free) and **Primal Strike** (+1d8 once/turn on a
> weapon hit — built TOGGLEABLE RAW weapon-only vs a non-RAW also-unarmed option,
> per the user's standing decision). The engine seam: `HitResponse.rider_damage`
> (a list of `RiderDamageSpec`) → `resolve_attack_roll` spawns each as its OWN
> typed `DamageEvent` (so the rider's type / `is_spell` / Elemental-Adept flags
> stay distinct — FoM's radiant is_spell makes it fuelable for free; Primal
> Strike, a FEATURE, is NOT fueled and NOT EA-treated, the is_spell-gate
> cross-check); `HitContext` gained `is_spell` + `is_unarmed` (a minimal tag — the
> THIRD attack-taxonomy touch, typology still deferred) for the rider gates.
> **Scope settled with the user up front (4 questions):** #6 with **FoM + Primal
> Strikes ONLY** (elemental weapon dropped); rider home = policy method + separate
> typed DamageEvent; FoM modeled **NON-concentration** this session (pre-cast like
> Fire Shield) with concentration + the Starry-Form Dragon save-floor flagged for
> NEXT session; clean standalone L15. Found + fixed a rotation bug: the Scion was
> greedily casting Guiding Bolt in the FoM combat (no melee hits → FoM inert), so
> the policy now MELEES while FoM is up (matches the guide's melee FoM combat).
> **399 tests green (+18).** L15 DPR ~36.2 (> session-13's ~29.7, < 52 ceiling);
> FoM-on > off and Primal-on > off at the fixed L15 enemy isolate each rider.
> Branch `feature/cast-effect-outgoing-riders` → confirm before merging to main.
> Per-feature ritual honored (FoM + Primal Strike rules + ACCESS re-verified via
> web + guide 41 BEFORE modeling). MCP-toggle recommendation re-made. ALSO produced
> the requested **MODEL BUILD-PLAN OVERVIEW** (visual diagram + roadmap, confirmed
> with the user) at session start.
>
> **Session scope
> (2026-06-16, session 13) — DONE (the TIER-4 row, L15):** built **Elemental Adept
> (fire) as a general engine primitive + its first consumer**, and **wired Fire
> Shield on the Starfire Scion at char L15** — the FIRST REAL BUILD CONSUMER of
> substrates #4 (incoming-damage resistance) + #5 (defender thorns) + the warm/chill
> **`choose_one`** seam. **Scope confirmed with the user up front + deliberately
> SPLIT:** Sunbeam was found to be a 6th-level spell = char **L19** (the prompt
> conflated it with FoM), and **Fount of Moonlight + Primal Strikes are both
> outgoing riders = substrate #6 (UNBUILT)** — so those + Sunbeam were DEFERRED to a
> follow-up tier-4 session; this session shipped Elemental Adept → Fire Shield (a
> clean standalone L15 row, no L13/L14). **Elemental Adept** = `DamageEvent.min_die`
> (per-die floor, "treat 1 as 2", phase 3) + `ignore_resistance` (phase 7, bypasses
> RESISTANCE only — not immunity/vulnerability), threaded `Choice → AttackRollEvent
> /SaveDamageEvent → DamageEvent` (also on `ReactiveDamageSpec` for the thorns);
> applied to the Scion's fire Searing Arc on L10/L11/L12/L15 (held from monk-4/L8 —
> a low-risk retrofit; the L10-12 DPR tests are relational, not exact). **Fire
> Shield (4th-lvl, L15)** = ONE pre-cast `cast_effect` (cost="none", 10-min
> non-conc) installs the WARM mode's cold resistance (#4); `on_incoming_hit`
> reflects 2d8 fire thorns (#5, Elemental-Adept-treated) on every incoming melee
> hit, with the **enemy-strikes-back loop turned on** (an `enemy_attack` row →
> `ScriptedEnemyPolicy`) so thorns do real DPR work (the dummy is both target and
> attacker → thorns land in its column). Pre-cast in ONE combat/day (one 4th-lvl
> slot = `fire_shield_use`). The warm/chill **`choose_one`** is the
> `FIRE_SHIELD_MODES` data table the policy indexes (YAML `choose_one` still
> deferred until cast_effect is data-driven). **381 tests green (+10).** L15 DPR
> ~29.7 (< 48 ceiling — a fraction, since Primal Strikes/FoM/elemental weapon are
> deferred); fire-shield-on > off at the fixed L15 enemy isolates the thorns. Branch
> `feature/tier4-fire-shield-elemental-adept` → confirm before merging to main.
> Per-feature ritual honored (FoM / Elemental Adept / Primal Strikes / Sunbeam
> rules + ACCESS verified via web BEFORE modeling). MCP-toggle recommendation
> re-made.
>
> **Session scope (2026-06-15, session 12) — DONE:** built **`cast_effect` substrates #4
> (incoming-damage response) + #5 (defender thorns rider)** + the **Starfire Scion
> enemy-strikes-back loop** (step 2 of the buff-primitive "Next-steps sequence").
> Substrate #4 = a defender-side phase-7 step in `resolve_damage`
> (`Entity.damage_response_for` folds an intrinsic trait + cast-installed payloads:
> 2024 RAW immunity/resistance/vulnerability, res+vuln cancel; applied after the
> save-for-half halving, before `take_damage`). Substrate #5 rides the existing
> `on_incoming_hit` intercept seam: `InterceptResponse` gained `reactive_damage`
> (`ReactiveDamageSpec`), and on a LANDED melee hit `resolve_attack_roll` enqueues
> an automatic thorns `DamageEvent` bearer→attacker (routes through the attacker's
> own #4 response; counts as the bearer's outgoing DPR). `ScriptedEnemyPolicy`
> (structurally identical to War Angel's, wired in `make_day_runner` on an
> `enemy_attack` row) is the loop that makes both do real work. **Per-feature
> verification (Option B, user-chosen):** Fire Shield is 4th-level → char **L15**
> for this build (Druid-7; guide 41:48), OUTSIDE the L1–L12 ladder — so #4's real
> in-scope consumer is a **fire-resistant enemy halving Searing Arc** (sets up the
> deferred Elemental Adept fire-bypass) and #5 is loop-validated via a Fire-Shield
> test policy; Fire-Shield-on-Scion build-wiring deferred to a tier-4 row.
> **371 tests green (+17;** 4 Flourish-Parry tests updated for the intercept
> closure's new 3-tuple). Branch `feature/cast-effect-incoming-damage-thorns` →
> confirm before merging to main. MCP-toggle recommendation re-made.
>
> **Session scope (2026-06-15, session 11) — DONE:** built **`cast_effect` substrate #3 — the
> StatusSet payload + the debuff `application_save`** (step 1 of the buff-primitive
> "Next-steps sequence"). `Choice` gained a `statuses` (list of `StatusSpec`)
> payload + an optional `application_save` (`ApplicationSave`); the scheduler
> `cast_effect` branch rolls the bearer's resist save vs the caster's DC (reusing
> `resolve_saving_throw`) and, on no-resist, installs the statuses on the bearer
> (a made save negates the whole payload). `resolve_attack_roll` reads two new
> PERSISTENT advantage grants — `attack_advantage_against` (Faerie Fire, on the
> target) + `spell_attack_advantage` (Innate Sorcery, on the actor, `is_spell`-
> gated). Consumers Innate Sorcery (self-grant, no save) + Faerie Fire (debuff, DEX
> save) verified per the per-feature ritual + validated via test policies (both
> speculative — no Scion consumer). Fixed a status-only-concentration sweep leak.
> **354 tests green (+7).** Branch `feature/cast-effect-statusset-payload` →
> merging to main this session (user-approved, confirm before the actual merge).
> MCP-toggle recommendation re-made.
>
> **Session scope (2026-06-15, session 9) — DONE:** built the **`cast_effect` combat-effect
> PRIMITIVE** — a first-class NON-DAMAGING cast (buffs AND debuffs) the scheduler
> spends action economy + resources on and that pushes NO DamageEvent. Surveyed the
> build-guide corpus for buffs/debuffs FIRST (user-directed) and locked the design in
> `design/buff_primitive.md`: a general **envelope** (cost / resource / target /
> duration+clock / concentration / source-labelled payload + optional debuff
> application-save) over a **7-substrate payload registry** (ModifierStack /
> policy-flag / StatusSet / incoming-damage-mod / defender-rider / outgoing-rider /
> zone), where ONE cast installs a SET of labelled payloads across substrates (forced
> by the **Fire Shield** stress test = resistance + thorns + mode-choice). **Debuffs
> are the SAME primitive, target-parameterised** (not a parallel one). NOW-SCOPE
> built: ModifierStack + policy-flag payloads, concentration, and a combat-boundary
> sweep (`Entity.clear_combat_buffs`). Retrofitted **Shillelagh** (turn-1 BA
> `cast_effect`, replacing the suppression hack — DPR-identical) and **Starry Form**
> activation (a `cost="none"` BUNDLED cast_effect — DPR-neutral; the same shape will
> carry a real BA for Chalice/Dragon). **338 tests green (+7).** DESIGNED-IN &
> sequenced for next sessions: StatusSet payload + application-save
> (advantage/condition/immunity + debuff resist), then incoming-damage resistance +
> defender thorns (Fire Shield / Rage). MCP-toggle recommendation re-made.
>
> **Session scope (2026-06-15, session 8) — DONE:** wired **THREAD B at L9 + L10** (Extra Attack +
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

- **SUBSTRATE #7 — 7c-ON-SUMMON (beast as buff/redirect/protect target) — BUILT &
  VALIDATED (2026-06-18, session 21).** The built 7c ally-effect machinery (session
  19) wired ONTO the 7a primal companion (session 20): the summon as a buff / redirect
  / protect target. **455 tests green (+11).** Branch `feature/substrate-7c-on-summon`
  → confirm before merge. Design contract: `design/buff_primitive.md` (registry row 7
  + build-sequence item 3 note flipped to 7c-on-summon BUILT; the `_all` resistance-key
  deferral resolved).
  - **Scope settled with the user up front: (A) 7c-on-summon, full slice.** Per-feature
    ACCESS finding (the per-feature ritual's "verify access, not just wording" — the
    same lesson that put Fire Shield at L15): the full kit is NOT online at the L4
    summon row — only Protection is (fighter-1); Bless is char L6, Aid + Warding Bond
    char L8 (guide 32:436-471). Built RAW-faithfully at a **new char L8 row**
    (Fighter-1 / Ranger-4 / Cleric-3 Trickery). (The user first selected "wire onto L4"
    by an accidental click, then asked for "your recommendation" = the L8 row.)
  - **`BeastEffectPolicy` (`src/builds/silvertail.py`) — the vehicle.** A PASSIVE
    defender policy registered for the beast (`decide → []`, so the beast still takes
    no turn of its own — the master COMMANDS it via `Choice.actor`). The beast is a
    real `Entity`, so the same `on_incoming_hit` riders + `cast_effect target=ally`
    payloads session 19 built for a synthetic ally land on it directly:
    - **warding bond** → +1 AC / +1 saves + RESISTANCE TO ALL damage on the beast, and
      each time it takes damage the MASTER takes the same (post-resistance) amount
      (`RedirectSpec`, fraction 1.0). Exact per-run invariant validated:
      `damage_source_to(enemy, beast) == damage_source_to(enemy, master)`.
    - **protection** → impose disadvantage on attacks vs the beast (the master
      interposes; guide 32:227 = 2024 Protection).
    - **bless** → +1d4 (rolled modifier) to the beast's attacks/saves → raises its
      OUTGOING DPR; concentration on the master.
    - **aid** → +5 HP max/current. **DPR-INERT *only under the current threshold HP
      model*** (HP never gates turns) — installed as an assertion that the target=ally
      HP buff lands on the beast. **This caveat LIFTS with the planned summon-survival
      slice** (when summons die at 0 HP, aid's +HP buys more rounds of summon DPR →
      DPR-relevant). Modeled +5 (2nd-level, the slot L8 has); the guide upcasts to +10
      at L10+ (3rd-level slots) — a future row.
  - **Enemy strikes the beast (the loop that makes the defender effects matter).** The
    L8 row carries an `enemy_attack` profile; `make_silvertail_runner` registers a
    `ScriptedEnemyPolicy(target=beast, damage_type="slashing")` so the typed swing lets
    warding bond's resistance bite before the redirect. The combat-clock payload is
    re-applied each combat via `BeastEffectPolicy.on_combat_start` (the Fire Shield /
    Bless re-cast pattern — `DayRunner` sweeps combat-clock buffs at every boundary; a
    one-time pre-cast would be wiped before combat 1).
  - **Engine seam — the `_all` damage-response key (resolves the session-19
    deferral).** `Entity.damage_response_for` now honors a reserved `"_all"` key that
    applies to any TYPED hit (still None for an untyped attack), feeding the same 2024
    dominate/cancel rules (an `_all` resistance + a type-specific vulnerability still
    cancel). `ScriptedEnemyPolicy` gained an optional `damage_type` threaded onto its
    swings (backward-compatible default None → War Angel / Scion byte-identical).
  - **Rules verified BEFORE modeling (per-feature ritual, 2026-06-18, web + guide 32).**
    Warding Bond (+1 AC/saves, resistance to all, "each time it takes damage you take
    the same amount"; ends if caster hits 0 / >60 ft — unmodeled), Aid (+5 HP max &
    current, +5/slot above 2nd → 2nd-level here = +5; 8 hr, non-conc), Bless (+1d4
    attacks/saves, conc, 3 targets), Protection (guide 32:227 = impose disadvantage).
    Direction confirmed: the beast is WARDED → the master takes the share (guide 32:471).
  - **Validation (`tests/test_silvertail.py`, +11).** Unit (FakeRNG): the `_all` key
    resists any type + honors cancel; warding bond resists the hit AND redirects an
    equal share to the master; protection flips a hit via the disadvantage reroll;
    bless's +1d4 turns a miss into a hit; aid bumps HP max; the beast stays commanded
    (not self-acting) with an effect attached. Integration (`make_silvertail_runner` at
    L8, per-(source,target) ledger): baseline enemy damages the beast and spares the
    master; warding bond cuts the beast's incoming below baseline and the redirected
    share equals it exactly; protection cuts incoming with no redirect; bless raises the
    beast's outgoing DPR; the beast keeps dealing commanded DPR with an effect active.
  - **Process / flags.** ATTACK-TAXONOMY NOT forced (the enemy melee-attacks the beast;
    no melee/ranged gate). Carry-over flag (ii) `snapshot.allies=()` NOT forced (all
    policies use explicit refs). **Forward-looking (user note):** the deferred
    charge-PRONE→advantage is entangled with **shocking grasp denying the enemy's
    reactions (no opportunity attack)** — the build's kite-in/out + repeated-charge
    pattern only works because shocking grasp suppresses the OA, so the
    on-hit-applies-status seam + a reaction-denial status + an opportunity-attack model
    are ONE connected control cluster (build deliberately when forced).
  - **Reflection (per-feature ritual, done 2026-06-18 — user discussion).** Three
    forward items surfaced, each recorded (no rework of this session's machinery — it is
    correct under the current model):
    1. **Uncommanded summon → Dodge** (disadvantage on incoming + advantage on DEX
       saves) — the general summon default; **reuses `impose_disadvantage`**; NOT forced
       (silvertail always commands → never dodges); build when a build leaves a summon
       uncommanded.
    2. **Full day-clock integration** — a day-clock partially EXISTS (the minute clock +
       `DurationBuffTracker`, War Angel hand-wires it for Magic Weapon); the full version
       integrates `duration="day"` into the `cast_effect` envelope (one cast persists
       across combats + minute-accurate expiry) for slot-economy fidelity on hour+ buffs
       (warding bond 1 hr / aid 8 hr). Planned slice; pairs with summon-survival.
    3. **Summon death at 0 HP** (+ per-character recast policy) — makes aid / warding
       bond / protection DPR-RELEVANT; needs real per-CR enemy damage (decision #12).
       See `design/buff_primitive.md` for all three.
  - **Deferred / NEXT (user decision 2026-06-18: summon-death FIRST, then 7b).**
    **SUMMON SURVIVAL & DEATH + recast policy** (item 3b in the build sequence) is the
    NEXT slice — wire `is_functionally_dead` → `destroyed` for summons, add a recast
    decision point, pull in real per-CR enemy damage; it lifts the "aid DPR-inert"
    caveat. THEN **7b zone / emanation** (Spirit Guardians — the §3.1 zonal model + a
    recurring scheduled event), the LAST unbuilt #7 sub-kind. Also deferred: the full
    day-clock integration; the uncommanded-Dodge default; higher silvertail rows; the
    full §3.6 three-HP-pool party entity; aid upcast (+10); the charge/prone +
    reaction-denial (shocking-grasp-denies-OA) control cluster.

- **SUBSTRATE #7 — 7a SUMMON (commanded primal companion) — BUILT & VALIDATED
  (2026-06-17, session 20).** The minimal 7a slice: a controlled-ally SUMMON as a
  real `create_entity`'d Actor, COMMANDED on its controller's turn, in its own
  per-summon DPR column. The combat now hosts a friendly that ACTS (not just the
  passive party member of slice 1). **444 tests green (+12).** Branch
  `feature/substrate-7a-summon` → confirm before merge. Design contract:
  `design/buff_primitive.md` (registry row 7 + build-sequence item 3 flipped to BUILT;
  `design.md` §1 controlled allies / §4 verbs 11/12 / §8 per-summon output).
  - **Scope settled with the user up front (3 questions).** (1) **L4 beast-only**
    (the prompt's minimal — the verbs + commanded actions + the summon column; NO
    7c-on-summon). (2) Command model = **fully commanded on the master's turn**
    (design-literal, not the lighter own-turn+BA-cost abstraction). (3) Lifecycle =
    **build `create_entity` as a real mid-combat verb, but invoke it at DAY START out
    of combat** for the silvertail's permanent companion; defer *testing* the
    mid-combat conjure-spawn until a build forces it.
  - **Commanded actions — `Choice.actor` (the load-bearing primitive).** A choice may
    carry an `actor` override: the controller's policy emits it, the COST (action
    economy + `resource_cost`) is drained from the CONTROLLER (the Beast Master spends
    a **Bonus Action** to command the beast), but the spawned event's actor is the
    commanded entity. So the attack uses the BEAST's stats and is attributed to the
    beast — the **per-summon DPR column falls out of the existing per-(source,target)
    ledger for free** (`damage_by_source(beast.id)`). Threaded in the scheduler's
    attack + save_spell branches (`acting = choice.actor or actor`); cost/resource
    checks stay on the commanding `actor`. design.md §1: "controlled allies act on
    their controller's turn."
  - **create_entity / destroy_entity (verbs 11/12) — `src/summons.py`.** `SummonSpec`
    (entity + lifecycle source + commander/policy) + `create_entity`/`destroy_entity`
    operating on a plain `(entities, policies)` roster, so the SAME verb summons at
    **day start out of combat** (the runner assembles the day's roster — how the
    permanent companion is created once and persists the day) or **mid-combat**
    (`Scheduler.add_entity`/`remove_entity` keep the live per-combat damage ledgers in
    sync; the cast_effect **`summons`** payload create_entity's into the live combat).
    The mid-combat path is built + lightly exercised; a per-combat conjure summon whose
    turns must splice into a round already in flight is **deferred** until a build forces
    it (user decision).
  - **Lifecycle teardown — `Entity.remove_effect` winks out summons.** A `destroyed`
    flag on Entity + `note_effect_summon(source, summon)`; `remove_effect(source)` now
    marks any summons it created `destroyed` alongside the modifiers/statuses/response
    of the bundle, so a controlled ally winks out with a dropped concentration / the
    combat-boundary sweep (design.md §1). The scheduler skips a `destroyed` entity's
    turns; a commander checks `beast.destroyed` before commanding.
  - **Build — `src/builds/silvertail.py` (char L4 only, the minimal row).**
    `make_silvertail` (Air Genasi Fighter-1/Ranger-3, AC 19; **shocking grasp** = a
    WIS spell attack, 1d8 lightning = the BUILD column) + `make_primal_companion`
    (Beast of the Land — an ACTOR: AC 16, HP 20, own saves). `SilvertailPolicy`
    commands the beast via the master's Bonus Action (`actor=beast`) and casts shocking
    grasp with the action (guide 32:353 rotation). `make_silvertail_runner` summons the
    beast at day start via `create_entity` and reports the **build column / summon
    column / party total SEPARATELY** (user decision s17). The beast (≈121.5/day) is the
    cornerstone and out-damages the master's cantrip (≈43.9/day); the party total
    (165.4) is exactly their sum — the case "report both, separately" exists for.
  - **Rules verified BEFORE modeling (per-feature ritual).** Beast of the Land, D&D
    2024 (Roll20 / D&D Beyond, 2026-06-17; matches guide 32:326): AC 13+WIS, HP
    5+5·ranger, Beast's Strike to-hit = your spell attack modifier (+5), Hit 1d8+2+WIS,
    Charge (moved ≥20 ft) +1d6 + Prone, command = a Bonus Action on your turn. The
    +1d6 charge is baked into the commanded strike (the guide's plan always charges).
  - **Validation (`tests/test_silvertail.py`, +12).** Engine seams via deterministic
    FakeRNG: the commanded strike is attributed to the BEAST not the master; the
    command draws the MASTER's Bonus Action only (two commands → one resolves); exact
    Beast's-Strike-with-charge damage math; a commanded beast takes no turn of its own;
    `create_entity`/`destroy_entity` roster ops; `remove_effect` winks out a noted
    summon; a destroyed independent summon takes no turns; the cast_effect `summons`
    payload creates into the live combat + ledger. Integration via
    `make_silvertail_runner`: the summon is a real Actor (HP 20 / AC 16); the summon
    column is separate from AND additive to the build column over 200 days; both
    friendlies only ever damage the dummy.
  - **Process / reflection.** Per-feature ritual honored (statblock verified first);
    user chose **no ritual change**, with THREE forward-looking flags captured: (i) the
    deferred charge-PRONE→advantage needs an **on-hit-applies-status seam** (a hit
    installs a condition the later roll reads) — the designed-in next control primitive;
    (ii) the scheduler's `snapshot.enemies` labels every non-actor (incl. friendlies)
    as an enemy and always sets `allies=()` — harmless today (policies use explicit
    refs) but a seam to fix when a policy must read its allies; (iii) **revisit
    commanded-vs-DPR-faithful** before the next summon slice now that the commanded
    model is concrete. ATTACK-TAXONOMY NOT forced this slice — flagged, untouched.
  - **Deferred / next.** **7c-on-summon** (the beast as a buff/redirect/protect target
    — connect 7a to the built 7c warding-bond/protection/aid machinery) and/or **7b
    zone/emanation** (Spirit Guardians — the §3.1 zonal spatial model, the heaviest
    and last sub-kind). Also still deferred: higher silvertail rows; the full §3.6
    three-HP-pool party entity; "resistance to all" (#4); generalizing `precast_mode`.

- **SUBSTRATE #7 — 7c ALLY-EFFECTS — BUILT & VALIDATED (2026-06-17, session 19).**
  The second 7c slice: `cast_effect` / intercept riders whose target is an ALLY, on
  the session-18 multi-entity foundation. **432 tests green (+13).** Branch
  `feature/substrate-7c-ally-effects` → confirm before merge. Design contract:
  `design/buff_primitive.md` (registry row 7 + build-sequence item 2 flipped to BUILT;
  the 3-tuple seam note marked refactored).
  - **The load-bearing engine change — the `on_incoming_hit` 3-tuple REFACTOR.**
    Adding warding-bond redirect was the trigger (the session-12 engine-seam note's
    own prediction): the decider's positional `(ac_bonus, counter, reactive_damage)`
    is now the single `InterceptResponse` object returned whole by
    `_make_intercept_decider`, and `resolve_attack_roll` reads the riders off it. New
    riders are now FIELDS, not tuple positions. The two test files that hand-built
    3-tuple deciders (`test_flourish_parry`, `test_incoming_damage_thorns`) were
    updated to `InterceptResponse`; all prior intercept behavior (parry / counter /
    Shield / thorns) byte-unchanged.
  - **(a) Ally-buff retarget (Bless/Aid) — NO engine change.** A `cast_effect` with
    `target=ally` lands the existing substrate-#1 (modifier) / #3 (status) / #4
    (damage-response) payloads on the ALLY's own `Entity` — the scheduler's cast_effect
    branch already installs on `choice.target or actor`. Validated: a `target=ally`
    cast puts the modifier + response on the ally and NOT the caster.
  - **(b) Warding bond (redirect).** The ally's `on_incoming_hit` returns a new
    `RedirectSpec(target, fraction)`; `resolve_attack_roll` threads it onto the spawned
    `DamageEvent` (new `DamageEvent.redirect` field) and `resolve_damage`, after the
    bearer takes its (post-resistance) damage, spawns a flat copy of `int(taken *
    fraction)` onto the caster — attributed to the ORIGINAL attacker (so it lands in
    that attacker's outgoing column) and `redirect=None` so it never recurses. "Each
    time it takes damage, you take the same amount" (2024, web-verified).
  - **(c) Protection fighting style (disadvantage).** `InterceptResponse.
    impose_disadvantage` re-rolls the attack with a SECOND d20 and flips the hit to a
    miss if it now misses — distributionally exact (P(hit)² either way, conditioning on
    the first roll being a hit); the surviving hit keeps its crit only on a double-20.
    2024 Protection (web-verified): reaction + shield → impose Disadvantage on the
    attack (and all attacks vs the target until your next turn → always-on while active
    is RAW-correct for a single attacker).
  - **(d) Sanctuary (save-or-negate).** `InterceptResponse.negate_save` (new
    `NegateSaveSpec(save_stat, dc)`) makes the ATTACKER roll a save vs the caster's DC;
    a FAILURE negates the attack (flips to a miss). 2024 Sanctuary (web-verified):
    attacker makes a WIS save or loses the attack; outcome-equivalent to the RAW
    pre-roll save for our DPR model (damage lands iff attacker-saves AND attack-hits).
  - **Vehicle — Scion + a synthetic ally.** `make_ally` (a passive infinite-HP friendly
    pool at peer AC/saves), `AllyEffectPolicy` (the defender-side reaction policy + the
    persistent-payload install; one vehicle covers all three intercept-riding effects),
    and `make_ally_effects_runner(level, rng, effect)` (Scion caster + ally + a melee
    enemy whose every swing targets the ally, isolating the effect). The protector/
    caster's reaction economy is ABSTRACTED into the ally's self-gated response (the
    seam consults the DEFENDER's policy) — the same convention as Fire-Shield thorns /
    Flourish Parry (user decision: keep; multi-reactor contention is unmodeled, a
    recorded simplification). Silvertail (the design note's named 7c stress vehicle)
    deferred to the 7a summon slice (user decision: lighter first).
  - **Validation (`tests/test_ally_effects.py`, +13).** Engine seams via deterministic
    FakeRNG: `target=ally` lands the payload on the ally not the caster; redirect is
    threaded onto the DamageEvent and spawns the taken amount (respecting the ally's
    resistance + the fraction); protection flips on a missed reroll / keeps a hit on a
    made one / downgrades a single-20 crit; sanctuary negates on a failed attacker save
    / lets a made save through. Integration via `make_ally_effects_runner` + the
    per-(source,target) ledger: warding bond redirects the FULL share to the caster
    (`damage_source_to(enemy, char) == damage_source_to(enemy, ally)`) and the +1 AC
    lands on the ally; protection and sanctuary each cut the ally's incoming damage
    below the `effect=None` baseline (directional, summed over a long run); the baseline
    takes full damage and redirects nothing (the control).
  - **Process / per-feature ritual.** All five spells' 2024 wording web-verified
    (D&D 2024 wikidot / Roll20 / D&D Beyond) BEFORE modeling. Reflection done — user
    chose to KEEP the reactor-economy abstraction and noted the "resistance to ALL
    damage" per-type gap (`damage_response` is keyed per type; add an `_all`/default key
    when a build needs it; #4 retarget validated with a typed test meanwhile).
    ATTACK-TAXONOMY NOT forced (no rider gated on melee/ranged) — flagged, untouched.
  - **Deferred / next.** **7a summon** — `create_entity`/`destroy_entity` an Actor with
    own HP/AC/saves/economy, commanded by the character policy, lifecycle keyed to
    `effect_source`; a summon DPR column; the summon as a buff/redirect target. Vehicle:
    stand up SILVERTAIL (guide 32) here (its primal companion), doubling as the eventual
    7a/7b stress test. Then **7b zone/emanation** (the §3.1 zonal model). Also still
    deferred: the full §3.6 three-HP-pool party entity; "resistance to all" (#4);
    generalizing `precast_mode` beyond the L15 4th-level slot.

- **SUBSTRATE #7 — 7c MULTI-ENTITY FOUNDATION-MIN — BUILT & VALIDATED (2026-06-17,
  session 18).** The first slice of the last unbuilt `cast_effect` buff substrate:
  the multi-entity-combat foundation + the 7c multi-entity-targeting sub-kind. The
  combat is no longer hard-wired 1-character-vs-1-dummy — it can host a friendly
  roster, the enemy splits its attacks across it, and DPR is attributed
  per-(source,target). **419 tests green (+5).** Branch
  `feature/substrate-7c-multientity-foundation` → confirm before merge. Design
  contract: `design/buff_primitive.md` (registry row 7 + build-sequence item 1
  flipped to "7c foundation-min BUILT").
  - **Scope held to 7c foundation-min ONLY** (the session-17 plan): passive party
    member + enemy split-targeting + per-(source,target) DPR accounting. NO summons,
    NO zones, NO ally-buff / warding-bond redirect / protection-protect (later
    slices). Validated against the EXISTING Scion at L15 (silvertail not stood up
    yet — that's the slice-2/3/4 vehicle).
  - **Passive party member (`make_party_member`, design.md §3.6).** One extra
    FRIENDLY infinite-HP pool carrying just an AC (so the enemy's attacks against it
    resolve) and NO policy (so it never acts — it draws attacks, deals nothing). The
    foundation-min stand-in for §3.6's full three-HP-pool party entity (deferred).
    Its only job: pull a share of the enemy's swings off the character so the
    character's defender-side reactions (Fire-Shield thorns, #5) fire on a FRACTION
    of incoming hits instead of every one.
  - **Enemy MULTI-ENTITY targeting (`ScriptedEnemyPolicy` roster mode, design.md
    §3.5).** A new optional `roster=[(entity, int_weight), …]` param: each attack is
    split across the weighted friendly roster (the melee Scion weighted 2 : party 1
    per §3.5 "melee tag raises targeting probability"), pre-rolled per (round, slot)
    at `on_combat_start` through the seeded channel (roll over the total weight, walk
    the cumulative buckets — generalises `char_target_prob` to N targets), so
    `decide()` stays dice-free. `roster=None` → the LEGACY single-target behavior,
    byte-identical (War Angel + every prior Scion test runs through it unchanged).
  - **Per-(source,target) DPR accounting.** `Scheduler.damage_by_source_target` —
    a cumulative `(source_id, target_id) → total` ledger populated as DamageEvents
    resolve (every event already knows `actor` + `target`). Surfaced on
    `CombatResult.damage_by_source_target` and three `DayResult` accessors:
    `damage_by_source(src)` (the build's OWN column — damage BY the character,
    regardless of target), `damage_source_to(src, tgt)` (one cell), `party_total
    (src_ids)` (the roster total). The user's session-17 decision: report the build
    column AND the party total SEPARATELY, so the headline never silently changes
    meaning when allies appear.
  - **The bit-comparable invariant (preserved).** In the single-entity case the
    character only ever damages the dummy, so `damage_by_source(char)` ==
    `damage_received_by(dummy)` (verified 619==619); `with_party` defaults False, so
    the entire prior test corpus + every DPR/ablation number is untouched. The new
    multi-entity scenario is opt-in (`make_day_runner(..., with_party=True)`).
  - **HEADLINE VALIDATION — the FoM↔Fire-Shield near-tie REVERSES (consistency/
    sanity, FakeRNG + directional DPR, NOT number-matching).** Session 16 found
    pre-cast FoM only NARROWED its gap to the Fire-Shield loadout to ~0.5 (not a
    reversal), the residual being Fire Shield's thorns over-proc against the lone
    dummy (which always targets the Scion → every incoming hit reflects). With a
    party member splitting the attacks: Fire Shield's thorns DPR drops (~32.5→31.2)
    while FoM's OWN-hit riders are untouched (~31.8) → **pre-cast FoM OVERTAKES Fire
    Shield** (solo gap +0.44 → party gap −0.56). Closes BOTH the substrate-#7 gap
    (7c) and the session-16 modeling artifact, exactly as the design note predicted.
  - **Validation (`tests/test_starfire_scion.py`, +5).** The build column equals the
    dummy column without a party (bit-comparable invariant); the roster splits
    attacks by weight through the seeded channel (FakeRNG — first swing action, rest
    free); the party member soaks real damage and the character is hit less than
    solo; the party split cuts Fire-Shield DPR; and the party split REVERSES the
    FoM-vs-Fire-Shield order (solo FS > FoM, party FoM > FS).
  - **Engine seams touched.** `Scheduler` (the source-target ledger), `DayRunner`
    (`CombatResult`/`DayResult` plumbing + accessors), `ScriptedEnemyPolicy` (roster
    mode), `starfire_scion` (`make_party_member`, the L15 row's char/party weights,
    `make_day_runner(with_party=...)`). NO new engine verb; `create_entity`/
    `move_entity` (verbs 11/12) + the §3.1 zonal state are still deferred to 7a/7b.
  - **Per-feature ritual / process.** The "new mechanic" was the §3.5 enemy-targeting
    weighting + the §3.6 party-member model — both `design.md` CONTRACTS (not D&D
    rules text), re-read and honored (no external wording to verify). ATTACK-TAXONOMY
    NOT forced this slice (the foundation runs in the implicit single melee zone;
    melee-vs-ranged hasn't yet mattered) — flagged, untouched per the standing
    "discuss before rebuilding the attack vocabulary" decision. Reflection half
    pending user input.
  - **Deferred / next.** 7c ally-effects (bless/aid retarget; warding-bond REDIRECT —
    the trigger to refactor the `on_incoming_hit` 3-tuple → response object;
    protection/sanctuary PROTECT) via the silvertail build; then 7a summon
    (`create_entity` an Actor), 7b zone/emanation (§3.1 zonal model). Generalising
    the full §3.6 three-HP-pool party entity, and `precast_mode` beyond the L15
    4th-level slot, also still deferred.

- **SUBSTRATE #7 DESIGN NOTE — zone / summon / multi-entity — WRITTEN (design-only,
  2026-06-17, session 17).** The last unbuilt `cast_effect` buff substrate is now
  DESIGNED (still unbuilt). Surveyed the build-guide corpus for zone/summon/aura/
  multi-entity effects and wrote the design note into `design/buff_primitive.md`
  (registry row 7 flipped DEFERRED → DESIGNED; header + next-steps updated; new
  "Substrate #7" section). **No engine code; 414 tests green (unchanged).** Branch
  `design/substrate-7-zones-summons-multientity` (pushed) → confirm before merge.
  - **Scope settled with the user up front (4 questions).** (1) **Design-only**
    (survey + note, no code). (2) **Multi-entity targeting** = primary focus /
    first-to-build. (3) **Silvertail (guide 32)** = survey + validation vehicle.
    (4) DPR with multiple friendly entities = report **both** the build's own
    column AND a party/roster total **separately**.
  - **The core realization (the note's spine).** #7 is the `cast_effect` ON-RAMP to
    the multi-entity/spatial model `design.md` already specifies but the engine has
    never needed (every build so far = 1 character vs 1 infinite-HP dummy): §1
    (Objects vs Actors; Controlled allies; Party = one actor, 3 HP pools), §3.1
    (zonal spatial model), §3.5 (enemy targeting over character+party), §3.6 (party),
    verbs 11/12 (`move_entity`, `create_entity`/`destroy_entity`), §8 (already lists
    summon/party damage as outputs). #7 implements against that contract — it does
    NOT redesign it. `design.md` left unchanged.
  - **Decomposition — 3 sub-kinds on 1 foundation.** FOUNDATION = multi-entity
    combat (roster of >2 entities, enemy targeting layer, per-(source,target) DPR).
    **7c** multi-entity targeting + ally-effects (target=ally|set; bless/aid
    retargeted; warding-bond redirect; protection/veer/sanctuary protect via the
    `on_incoming_hit` seam) — LIGHTEST, needs no zones/summons. **7a** summon
    (`create_entity` an Actor with own HP/AC/saves/economy, commanded by the
    character policy, lifecycle keyed to `effect_source`; summon DPR column;
    buffable + redirect target). **7b** zone/emanation (`create_entity` an Object +
    footprint defining a named zone + a recurring future-dated scheduled event;
    damage/debuff OR buff flavor; anchored-to-caster vs static; needs the §3.1
    zonal model). Sequenced **7c → 7a → 7b**, each gated design-first.
  - **Envelope extension.** Shape unchanged; adds payload kinds `summons`
    (`SummonSpec`) + `zones` (`ZoneSpec`) and uses the target axis `ally|set`; the
    `effect_source` label already drives teardown (`Entity.remove_effect`, session
    15) — extended to also `destroy_entity` summons/zones on the same source.
    Redirect/protect ride the existing intercept seam; adding warding-bond redirect
    is the trigger to refactor that seam's 3-tuple into a response object (the
    session-12 deferred note).
  - **DPR accounting (user decision: both, separately).** Attribute every
    `DamageEvent` to its (source, target); the runner reports the **build's own
    column** (`source==character` — stays bit-comparable to all prior numbers, the
    invariant that keeps the test corpus meaningful), a **party/roster total**
    (sum over character+summons+party), and a **per-summon column**.
  - **First slice (next session) = 7c foundation-min.** Register a passive party
    member (one extra friendly HP pool); extend `ScriptedEnemyPolicy` target set to
    {character, party}, pre-rolled at `on_combat_start` (dice-free decide), §3.5
    trait-weighted; per-(source,target) DPR accounting. **Predicted sanity check
    (consistency, FakeRNG — NOT number-matching):** spreading incoming hits across
    the party drops Fire Shield's thorns DPR and the pre-cast FoM loadout OVERTAKES
    it — the session-16 ~0.5 near-tie finally reverses. Closes BOTH the substrate
    gap (7c) and the session-16 modeling artifact.
  - **Stress test = silvertail (guide 32).** Forces the whole cluster at once
    (primal companion = 7a; Spirit Guardians = 7b emanation; circle of power = 7b
    buff-aura; aid/bless on beast = 7c ally-buff; warding bond = 7c redirect;
    protection/veer/sanctuary/arrow-catching = 7c protect; invoke duplicity =
    Object-as-token degenerate zone; mounted combat = zonal mount rule + the 7c
    targeting split). All absorbed with no envelope growth — the evidence the shape
    is settled, mirroring Fire Shield for #4/#5.
  - **Engine seams enumerated (NOT built):** roster in the runner; enemy targeting
    layer; per-(source,target) DPR; verbs 11/12; recurring zone event; the §3.1
    zonal state (deferred to 7b — 7c/7a run in the implicit single melee zone);
    intercept-seam refactor at warding-bond.
  - **Reflection / process.** Design-only → per-feature ritual's rules-verify half
    is N/A (surveyed spells are pointers, to be verified at each build session); the
    reflection half ran (see end-of-session — pending user input on process
    changes). ATTACK-TAXONOMY flagged as most likely to be forced by multi-entity
    combat (melee-vs-ranged finally matters) — revisit, but discuss before
    rebuilding the attack vocabulary. Memory `zone-summon-substrate-via-silvertail`
    updated to BUILT-design / scope-decided.

- **PRE-CAST ASSUMPTION TOGGLE — pre-cast vs in-combat as a tunable SETTING on the
  Scion's L15 4th-level loadout — BUILT & VALIDATED (2026-06-17, session 16).**
  Whether a combat-long buff is PRE-CAST (before initiative, free) vs CAST IN COMBAT
  (a real turn cost + concentration) is now a knob, not a hard-coded branch — so the
  DPR figure's assumption is EXPOSED rather than hidden (the all-in-combat figure is
  a lower bound, all-pre-cast an upper bound). **414 tests green (+8).** Branch
  `feature/precast-assumption-toggle`. Memory: `precast-assumption-as-a-toggle`
  (flipped to BUILT + the near-tie finding).
  - **Scope settled with the user up front (4 questions).** (1) Setting lives as a
    **policy / `make_day_runner` param** (mirroring `fourth_level_spell` /
    `primal_strike_unarmed`), not LEVELS data or a global knob. (2) rng mode = a
    **single probability p, rolled ONCE per combat** through the seeded channel. (3)
    Applies to **just the L15 4th-level spell (FoM + Fire Shield)** — Shillelagh /
    Starry Form / War Angel's Bless left alone. (4) Validation = **three-mode
    ordering + the FoM↔Fire-Shield re-pass** (consistency/sanity, FakeRNG).
  - **The shape.** `precast_mode` ("always" / "rng" / "never" / None) + `precast_prob`
    on `StarfireScionPolicy.__init__` + `make_day_runner`. The coin is resolved ONCE
    per combat in **`on_combat_start`** (when the `slot_4th` slot is spent) via a
    percentile **d100 through the seeded RNG** — so `decide()` stays a pure read
    (CLAUDE.md #7/#9). `decide()` reads the per-combat `_precast_this_combat` flag:
    pre-cast → a free turn-1 install (`cost="none"`, full-damage opening turn);
    in-combat → the buff is the turn-1 action (FoM/Fire Shield) ± BA (Dragon), a
    0-damage opening turn. Shillelagh's cast-round (1 vs 2) and Dragon's activation
    cost (`none` vs `bonus_action`) track the same flag.
  - **Bit-identical default (the key invariant).** `_roll_precast` draws NO dice in
    "always" / "never" / None modes; **only "rng" mode** consumes the d100. None =
    each effect's LEGACY default (Fire Shield pre-cast = True; FoM in-combat = False),
    so the pre-toggle behaviour — and the entire existing RNG stream — is preserved:
    all 53 prior starfire tests (and the full 406) stayed green untouched.
  - **MODELING FINDING (the prompt's hypothesis only HALF-confirmed).** The three
    modes order cleanly on L15 DPR (n=400, seed 0): always-precast **32.1** >
    rng@0.5 **30.5** > in-combat **29.6** (robust across 5 seeds). BUT pre-casting
    FoM narrows its gap to the Fire-Shield loadout (~32.5) from ~3.0 (in-combat) to
    only **~0.5 — a NEAR-TIE, not a full reversal** — in the single-dummy model. The
    residual is exactly Fire Shield's **thorns over-count** (the lone dummy always
    targets the Scion, so every incoming hit reflects), the SEPARATE multi-entity
    arc. So **pre-cast alone ties FoM to Fire Shield; the full re-pass needs the
    multi-entity fix too.** Validation asserts that honestly ("narrows the gap
    sharply," gap_precast < 0.5·gap_in_combat) rather than forcing an unsupported
    full-re-pass claim.
  - **Validation (consistency/sanity, FakeRNG — NOT number-matching;
    `tests/test_starfire_scion.py`, +8).** "always" makes FoM a free turn-1 install
    with a full melee opening turn (+ free Dragon, + Shillelagh BA); "never" matches
    the session-15 in-combat 0-damage opening (FoM cost="action", Dragon BA); None =
    legacy per-effect default (FoM in-combat, Fire Shield pre-cast); the precast coin
    is drawn ONLY in "rng" mode (a `_RecordingRNG` counts d100s); the d100 resolves
    against the threshold (roll ≤ p·100 pre-casts); the three modes order with rng
    strictly between; "never" DPR is exactly bit-identical to the legacy default; and
    pre-casting FoM narrows the Fire-Shield gap to under half the in-combat shortfall.
  - **Reflection / process.** No NEW game mechanic this session (a modeling knob —
    FoM / Fire Shield / Dragon rules were verified sessions 13-15), so the
    rules-verification half of the per-feature ritual was N/A; the reflection half
    ran and the user chose **no process change**. Judgment call flagged: in the
    pre-cast FoM combat Shillelagh is still a turn-1 BA cast (scoped OUT of the
    toggle), making the upper bound slightly conservative — acceptable.
  - **Deferred / next.** **Substrate #7 (zones / summons / multi-entity)** via the
    silvertail's-blessing build is the last unbuilt buff substrate AND the fix that
    lets FoM truly pass Fire Shield (the thorns over-count) — design-survey first,
    multi-session (memory `zone-summon-substrate-via-silvertail`). Generalizing the
    pre-cast knob beyond the L15 4th-level slot (to Shillelagh / Starry Form / Bless)
    is a possible smaller thread, not built.

- **FoM CONCENTRATION FOLLOW-UP — Fount of Moonlight in-combat cast + concentration
  + the Starry-Form Dragon save-floor — BUILT & VALIDATED (2026-06-17, session
  15).** Retires the session-14 FoM debt: FoM is now a real in-combat cast that
  concentrates, and the Scion's FIRST in-combat concentration is guarded by Dragon
  form. Also fixed a latent concentration-break bug and reconciled the 4th-level
  slot. **406 tests green (+7).** Branch `feature/fom-concentration-dragon-form`.
  Design contract: `design/buff_primitive.md` (substrate #3 SAVE-FLOOR sub-kind
  flipped to BUILT; substrate #7 noted as the only remaining gap).
  - **Scope settled with the user up front (4 questions).** (1) Task **(A)** — the
    FoM follow-up — over (B) zones/summons (the big multi-enemy/spatial design step,
    deferred). (2) Model the Dragon save-floor as a **FULL second Starry Form**
    (Wild-Shape cost + a real turn-1 BA activation), not just the floor flag. (3)
    FoM back to a **real turn-1 Magic-action cast** (turn 1 = 0 damage). (4) FoM +
    Fire Shield **SHARE the single druid-7 4th-level slot** (drop session-14's
    over-count).
  - **Engine — the substrate-#3 SAVE-FLOOR grant (designed-in since session 11,
    first consumer now).** `resolve_saving_throw` gained `d20_floor` (a per-die
    floor on the d20, applied after adv/disadv to the initial roll AND any reroll).
    `_check_concentration` reads a `concentration_save_floor` status off the saver
    and passes it — Starry-Form Dragon's "treat 9 or lower as 10 on a CON save to
    maintain concentration" (guide 41:308).  Inert when the status is absent (every
    prior save path unchanged).
  - **Engine — `Entity.remove_effect(source)` (a real bug fix).** A broken
    concentration previously called `remove_modifier` only, so a cast's NON-modifier
    payloads (a `_effect_damage_response` like FoM's radiant resistance, a granted
    status) LEAKED past the break.  `remove_effect` tears down the whole bundle —
    modifiers + damage response (#4) + statuses (#3, now indexed by source via
    `note_effect_status`, populated in the scheduler's cast_effect branch) — and
    clears concentration if the source held it.  BOTH `_check_concentration` (on a
    break) and `clear_combat_buffs` (the boundary sweep) route through it; the
    scheduler now notes a combat-buff source for status-only casts too, so Dragon's
    floor status drops cleanly.  (This also retro-fixes the latent Faerie-Fire
    concentration-status leak from session 11 — no current consumer, but correct.)
  - **Build — FoM as a turn-1 Magic-action concentration cast.** decide() emits FoM
    as a `cost="action"` concentration `cast_effect` on turn 1 of the FoM combat
    (sets concentration, installs the radiant resistance #4) → **turn 1 deals 0
    damage** (guide 41:779).  The on_hit +2d6 radiant rider (#6) now gates on
    **concentration being HELD** (`self._character.concentration ==
    "fount_of_moonlight"`), so it rides turns 2-4 while concentration lasts and
    drops the instant a failed CON save breaks it — not on a combat-scoped flag.
    The FoM combat's turn-1 BA is **Starry-Form Dragon** (a `cost="bonus_action"`
    cast_effect installing the floor status; a Wild Shape charge spent in
    on_combat_start), so Shillelagh slides to turn 2 (guide 41:780).
  - **Build — the shared 4th-level slot.** `fire_shield_use` + `fom_use` (two 1/LR
    uses → the over-count) replaced by ONE `slot_4th` (1/LR) the two loadouts
    compete for, plus `wild_shape` (Dragon) and `con_save` (the FoM concentration
    save: CON 14 +2, NOT proficient) on the L15 row.  A `fourth_level_spell`
    selector ("fount_of_moonlight" default — the guide's L15 pick — / "fire_shield")
    threads through `StarfireScionPolicy` + `make_day_runner`; exactly one loadout
    casts per day.
  - **MODELING FINDING (the honest cast cost lowers FoM's net DPR).** Default L15
    DPR fell from session-14's ~36.2 to **~29.6**: the turn-1 = 0-damage cast +
    occasional concentration breaks cost FoM a turn, and the SHARED slot means Fire
    Shield's thorns are no longer ALSO in the default loadout (session 14
    double-counted the slot).  So FoM lands NEAR — not clearly above — session-13's
    Fire-Shield-only ~29.7; they are now mutually-exclusive loadouts, not additive.
    The stale `test_l15_dpr_rises_above_the_session13_baseline` was reframed to
    **FoM-loadout > unused-4th-slot** (net still positive even paying the cast cost)
    + < ceiling — a non-magic-number consistency check.
  - **Validation (consistency/sanity, FakeRNG — NOT number-matching).** Engine
    (`tests/test_concentration.py`, +3): `d20_floor` treats sub-floor rolls as the
    floor (all-pass vs some-fail); the `concentration_save_floor` status protects an
    end-to-end concentration through `_check_concentration`; a broken concentration
    drops the FULL bundle (modifier + damage response + status).  Build
    (`tests/test_starfire_scion.py`, +4 net): FoM cast as a turn-1 `cost="action"`
    concentration cast_effect (radiant resistance, 0-damage turn); the FoM-combat
    turn-1 is FoM + Dragon (both cast_effects → 0 damage, Dragon installs the
    floor=10 status); the rider gates on concentration (silent before the cast /
    after a break); FoM + Fire Shield share `slot_4th` (the other never casts); the
    Dragon floor sharply cuts FoM concentration breaks at the fixed L15 enemy;
    FoM-on > off and Primal-on > off still hold; the FoM loadout nets positive over
    an unused slot and stays under the ceiling.
  - **Deferred / flagged.** Substrate **#7 (zones/summons)** is now the ONLY unbuilt
    buff substrate — the next big design step (multi-enemy/spatial; survey the
    corpus first).  FoM's reaction-blind (control, not DPR) stays deferred.  The
    `intercept`-seam 3-tuple refactor still waits for another defender reaction.
    `is_unarmed` remains the third ATTACK-TAXONOMY tag (typology still deferred — no
    new attack tag this session).  Fire Shield's 10-min day-clock stays
    combat-clock.

- **`cast_effect` substrate #6 — OUTGOING PREDICATE RIDERS — BUILT & VALIDATED
  (2026-06-16, session 14).** The last damage-rider substrate; only #7
  (zone/summon) remains. First consumers: Fount of Moonlight + Primal Strike on
  the Starfire Scion at L15. **399 tests green (+18).** Branch
  `feature/cast-effect-outgoing-riders`. Design contract:
  `design/buff_primitive.md` (registry row 6 flipped to BUILT). Also produced the
  user-requested **MODEL BUILD-PLAN OVERVIEW** (visual diagram + the ~5–10-session
  roadmap, confirmed with the user) at the top of the session.
  - **Scope settled with the user up front (4 questions).** (1) Build #6 with
    **FoM + Primal Strikes ONLY** — elemental weapon (L13) dropped. (2) Rider home
    = a **policy-side on_hit method + a SEPARATE typed DamageEvent** (not folding
    into the weapon hit), so FoM's radiant reaches the existing `on_deal_damage`
    fuel path on its own terms. (3) FoM modeled **NON-concentration this session**
    (pre-cast like Fire Shield) — model the in-combat Magic-action cast +
    concentration + the **Starry-Form Dragon concentration-save floor NEXT
    session** (the Scion's first in-combat concentration). (4) **Clean standalone
    L15** (no L13/L14 rows). The RAW-vs-unarmed Primal Strike toggle was a standing
    user decision (memory `primal-strikes-explore-unarmed`).
  - **The engine seam.** `HitResponse` gained `rider_damage: list[RiderDamageSpec]`
    (dice / type / is_spell / damage_bonus / Elemental-Adept flags).  On a confirmed
    hit `resolve_attack_roll` spawns each spec as its OWN `DamageEvent`
    (actor→target, same is_crit so the rider doubles on a crit) AFTER the weapon's
    DamageEvent.  Keeping each rider a separate TYPED event — rather than folding
    its dice into the weapon hit like `extra_damage_dice` (smite) — is what lets
    its damage type / `is_spell` stay distinct: it (a) routes through the target's
    per-type response (#4), (b) carries its own Elemental Adept treatment, and (c)
    reaches the caster's `on_deal_damage` rider on its own terms.  The `on_hit`
    decider return grew 2-tuple → `(extra_dice, extra_masteries, rider_damage)`;
    the smite/bluff `extra_damage_dice` path is untouched (War Angel green).
    `HitContext` gained `is_spell` + `is_unarmed` so a rider can gate on attack
    kind.
  - **Fount of Moonlight (4th-level, char L15; verified D&D Beyond / wikidot /
    Roll20, access guide 41:48/758).** "Resistance to Radiant + your MELEE attacks
    deal an extra 2d6 Radiant on a hit" (+ a reaction-blind deferred).  on_hit adds
    the +2d6 RADIANT rider on every melee hit (quarterstaff AND unarmed; gated as
    `not is_spell` — the only spell attack, Guiding Bolt, is ranged).  The rider is
    `is_spell=True`, so **Fueled Spellfire fuels the FIRST such radiant each turn
    for free** (the guide's `quarterstaff_{...fueled-spellfire(2)} --> ...+4d6`).
    Pre-cast in ONE combat/day (its own `fom_use` slot); the turn-1 cast_effect
    installs the radiant RESISTANCE (#4).
  - **Primal Strike (Elemental Fury, druid-7; verified D&D Beyond / Roll20).**
    "Once on each of your turns when you hit with an attack roll using a WEAPON
    (or a Beast form), +1d8 Cold/Fire/Lightning/Thunder (choose on hit)"; the 2d8
    step is DRUID-15 → **1d8** here.  on_hit adds a +1d8 (we pick fire) rider,
    round-gated once/turn, on a weapon hit.  It is a FEATURE (`is_spell=False`) →
    **NOT fueled and NOT Elemental-Adept-treated** even though fire — the
    cross-check that the is_spell gate does real work on the rider path (contrast
    the fire Searing Arc / Fire Shield thorns, which ARE spells and DO get the EA
    bypass).  **Built TOGGLEABLE:** RAW rides weapon attacks only; the non-RAW
    option (`primal_strike_unarmed`, threaded through `make_day_runner`) also rides
    unarmed strikes — to compare DPR in tier-4/5 where the action is Sunbeam and
    the attacks are Flurry of Blows (`is_unarmed` is what distinguishes the two).
  - **Rotation fix (found via the FoM ablation showing zero effect).** The Scion
    greedily casts Guiding Bolt every turn while Star-Map charges last, so the FoM
    combat (combat 0) had NO melee hits → FoM rode nothing.  The guide's FoM
    combats are MELEE (`attack(x2):quarterstaff_{...}`).  Fixed: `decide()`
    suppresses Guiding Bolt while FoM is up, so the Scion melees that combat (which
    also enables Searing Arc); the unused GB charges carry to the other combats, so
    total GB casts — and DPR outside the FoM combat — are unchanged.
  - **Validation (consistency/sanity, FakeRNG — NOT number-matching).** Engine
    (`tests/test_outgoing_riders.py`, +7): a rider spawns its OWN typed DamageEvent
    (not folded into the weapon hit) / multiple riders each spawn after the weapon
    hit / rider dice double on a crit / the rider routes through the target's
    per-type response and `ignore_resistance` bypasses / `min_die` floors / the
    smite-style `extra_damage_dice` still fold in (War Angel path unchanged).
    Build (`tests/test_starfire_scion.py`, +11): FoM rides quarterstaff + unarmed
    with a fuelable radiant; FoM skips Guiding Bolt; the FoM radiant qualifies for
    Fueled Spellfire (on_deal_damage → +2d8); Primal Strike fires once/turn on
    weapon hits; RAW declines unarmed / non-RAW rides it; Primal Strike is NOT
    EA-treated (contrast Searing Arc); FoM + Primal combine on the first swing; FoM
    pre-cast in one combat/day; **FoM-on > off and Primal-on > off** at the fixed
    L15 enemy isolate each rider; L15 DPR ~36.2 rises above session-13's ~29.7 and
    stays under the 52 ceiling.
  - **Fidelity notes / deferred.** druid-7 has only ONE 4th-level slot, so Fire
    Shield + FoM truly COMPETE for it; we model each with its own 1/LR use (a
    4th-slot over-count) so their DPR contributions isolate cleanly — reconcile in
    the level-by-level re-walk.  FoM concentration + the Dragon save-floor + the
    in-combat Magic-action cast cost are NEXT session.  `is_unarmed` is a minimal
    tag, not the first-class attack typology (ATTACK-TAXONOMY flag, third consumer).
    Melee-vs-ranged stays gated as "not a spell attack" (no ranged non-spell
    attacker at L15).

- **TIER-4 row (char L15): Elemental Adept (fire) engine primitive + Fire Shield
  wired on the Starfire Scion — BUILT & VALIDATED (2026-06-16, session 13).** The
  first REAL build consumer of substrates #4 + #5 + the warm/chill `choose_one`.
  **381 tests green (+10).** Branch `feature/tier4-fire-shield-elemental-adept`.
  Design contract: `design/buff_primitive.md` (choose_one + Elemental Adept flipped
  to BUILT).
  - **Scope confirmed + SPLIT with the user up front (per the prompt's instruction
    + the per-feature ACCESS ritual).** Web-verified rules/access surfaced two
    things the prompt conflated: **Sunbeam is 6th-level = char L19** (not L15), and
    **Fount of Moonlight (4th, L15) + Primal Strikes (druid-7, L15) are both
    outgoing riders = substrate #6 (UNBUILT)** (FoM = +2d6 radiant on melee hits,
    concentration; Primal Strikes = +1d8 once/turn, not radiant). So the user chose
    **Elemental Adept → Fire Shield this session** (clean standalone L15, no L13/L14
    rows), deferring #6 / FoM / Primal Strikes / Sunbeam to a follow-up tier-4
    session. This retires the #4/#5/Elemental-Adept verification debt with real
    consumers without dragging in a new substrate.
  - **Elemental Adept (fire) — a general engine primitive.** `DamageEvent` gained
    `min_die` (per-die FLOOR — "treat any 1 on a damage die as a 2", applied in
    `resolve_damage` phase 3 to the spell's own dice) and `ignore_resistance`
    (phase 7 — the cast bypasses the target's RESISTANCE to its type; immunity and
    vulnerability still bind, per 2024 RAW). Threaded `Choice → AttackRollEvent /
    SaveDamageEvent → DamageEvent`, and onto `ReactiveDamageSpec` so Fire Shield's
    fire thorns get the same treatment. Inert by default (the 371 prior tests
    stayed green). Consumer: the Scion's fire Searing Arc carries the flags on
    L10/L11/L12/L15 (the feat is held from monk-4/L8) — so a **fire-resistant enemy
    takes FULL, high-graded Searing Arc**, the real in-scope #4 consumer session 12
    set up. (The L10-12 retrofit is low-risk: those DPR tests are relational —
    monotonic / ablation — not exact, and `min_die` draws no extra dice so the RNG
    stream is unchanged.) The radiant half (Spellfire Adept's radiant-resistance
    bypass) is the symmetric deferral — no radiant-resistant enemy is modeled.
  - **Fire Shield on the Scion at L15.** New `LEVELS[15]` row (monk-8/druid-7, PB
    5, WIS 20 +5, DEX 16 +3; enemy cr15 = AC 18 / DEX +4 live from the CSV).
    Offense vs L12 changes only by PB 4→5 (Shillelagh stays 1d12, Searing Arc stays
    5d6, WIS already capped) — Primal Strikes / FoM / elemental weapon (L13)
    deferred, so DPR is a deliberate fraction of the guide's ~50 tier-4 ceiling.
    Fire Shield (verified: action, 10 min, NON-conc; warm = resist cold + 2d8 fire
    thorns / chill = resist fire + 2d8 cold thorns) is modeled as a **pre-cast**:
    `on_combat_start` consumes one 4th-level slot (`fire_shield_use`, 1/LR) and sets
    the combat flag for ONE combat/day; `decide()` emits a `cost="none"`
    `cast_effect` on turn 1 installing the WARM mode's cold resistance (#4);
    `StarfireScionPolicy.on_incoming_hit` reflects the 2d8 fire thorns (#5,
    Elemental-Adept-treated) on every incoming melee HIT.
  - **The warm/chill `choose_one` (first consumer).** A `FIRE_SHIELD_MODES` data
    table (`warm` → resist cold + fire thorns; `chill` → resist fire + cold thorns)
    the policy indexes by the row's chosen mode — the chosen mode selects WHICH
    payload items install (resist via the cast_effect, thorns via on_incoming_hit).
    The YAML `choose_one` construct in `content.py` stays deferred until cast_effect
    Choices are data-driven (today they're built in Python policies).
  - **The enemy-strikes-back loop makes thorns real DPR.** The L15 row carries an
    `enemy_attack` block (cr15 melee, attack_bonus/damage ILLUSTRATIVE — the CSV
    has only AC + saves), so `make_day_runner` attaches a `ScriptedEnemyPolicy`.
    Because the dummy is BOTH the Scion's target and the attacker, the thorns
    (bearer→attacker = char→dummy) land in the **dummy's** damage_received column —
    so they correctly count toward DPR. Fire-shield-on > off at the fixed L15 enemy
    isolates the thorns contribution.
  - **Validation (consistency/sanity, FakeRNG — NOT number-matching).** Engine
    (`test_incoming_damage_thorns.py`, +5): `min_die` floors each die / is inert
    above the floor; `ignore_resistance` makes a resistant target take full but does
    NOT bypass immunity/vulnerability; the real consumer — the L15 Searing Arc
    Choice's flags drive a fire-resistant enemy to FULL, high-graded damage. Build
    (`test_starfire_scion.py`, +5): the L15 Searing Arc is Elemental-Adept-treated;
    the WARM choose_one installs cold resistance + fire thorns (and chill the
    opposite, with cold thorns NOT Elemental-Adept-treated); Fire Shield is pre-cast
    in only one combat/day; and **fire-shield-on > off** at the fixed L15 enemy
    (thorns lift DPR through the loop). L15 added to the factory-stats / enemy-CSV /
    DPR-fraction / Shillelagh-die sweeps. L15 DPR ~29.7 (< 48).
  - **Deferred (next tier-4 session):** substrate **#6 (outgoing predicate riders)**
    + **Fount of Moonlight** (+2d6 radiant on melee hits, fuelable, concentration —
    FoM's rider also applies to UNARMED strikes per the spell text) + **Primal
    Strikes** (+1d8 once/turn) + **elemental weapon** (L13, +1d4 fire/+hit); then
    **Sunbeam** at L19 (a direct radiant save-for-half spell — fueled for free on the
    existing path). Also still designed-in: a melee-vs-ranged tag on incoming attacks
    (thorns assumes melee); Fire Shield's 10-min day-clock spanning combats (modeled
    combat-clock); the radiant-resistance bypass (Spellfire Adept).
  - **User reflections captured (session 13):** (1) applying Elemental Adept across
    L10–L12 (not just L15) is FINE — we'll eventually re-walk this build level by
    level with full output + enemy behavior, so a working interim version is good
    enough. (2) The `choose_one`-as-Python-data-table is fine for now; data-driven
    `cast_effect` (YAML choose_one) stays deferred ("bigger fish"). (3) **Primal
    Strikes — when built, ALSO model a NON-RAW option to proc on UNARMED strikes.**
    RAW (2024 PHB) it's weapon attacks only, but the user wants to EXPLORE the
    Scion's DPR if Primal Strikes also rides unarmed — especially in T4 where the
    action goes to Sunbeam and attacks are Flurry of Blows (FoM already covers
    unarmed). Build it toggleable so RAW vs non-RAW DPR can be compared. (4) The
    intercept-seam 3-tuple refactor stays deferred until more defender reactions
    exist. **(5) NEXT SESSION should ALSO produce a MODEL BUILD-PLAN OVERVIEW** —
    what's accomplished, where we are, and the roadmap for the next ~5–10 sessions —
    ideally **VISUAL** (a diagram of how the pieces fit), a wall of text acceptable.

- **`cast_effect` substrates #4 (incoming-damage response) + #5 (defender thorns
  rider) + the Starfire Scion enemy-strikes-back loop — BUILT & VALIDATED
  (2026-06-15, session 12).** Step 2 of `design/buff_primitive.md` "Next-steps
  sequence": resistance/vulnerability/immunity on incoming damage, and "deal
  damage to whoever melee-hits the bearer" (Fire Shield thorns). **371 tests
  green (+17).** Branch `feature/cast-effect-incoming-damage-thorns`. Design
  contract: `design/buff_primitive.md` (registry rows 4 + 5 flipped to BUILT).
  - **Order chosen with the user — Option (a) then Option B.** (a) Wire the loop
    FIRST so #4/#5 have a real incoming-attack path (the speculative test-policy
    validation of #3 left verification debt; building two MORE defender mechanics
    with no real loop would compound it). Then, per the per-feature ritual, Fire
    Shield's rules + ACCESS were verified BEFORE modeling: it is **4th-level →
    char L15** for this build (Druid-7; guide 41:48), OUTSIDE the modeled L1–L12
    ladder. So **Option B**: ship #4/#5 as engine substrates; give #4 a REAL
    in-scope consumer (fire-resistant enemy vs Searing Arc) and #5 a loop-
    validated Fire-Shield test policy; defer Fire-Shield-on-Scion build-wiring to
    a tier-4 row (dragging in Sunbeam / Fount of Moonlight / Primal Strikes is a
    separate session).
  - **#4 — incoming-damage response (`resolve_damage` phase 7).**
    `Entity.damage_response_for(type)` folds an INTRINSIC trait (`damage_response`
    ctor arg — a monster's fire resistance) + cast-installed payloads
    (`add_damage_response`, swept at the combat boundary like the modifiers).
    2024 RAW combination: immunity dominates; resistance halves (rounded down);
    vulnerability doubles; resistance + vulnerability of the SAME type cancel.
    Applied AFTER phase-6 save-for-half halving and BEFORE `take_damage`, so the
    post-response amount drives any concentration save. Inert on every existing
    path (untyped hits → `damage_type` None → no response). `Choice` gained a
    `damage_response` payload; the scheduler `cast_effect` branch installs it on
    the bearer under `effect_source` (Fire Shield's resist-cold/fire).
  - **#5 — defender thorns rider (the `on_incoming_hit` intercept seam).**
    `InterceptResponse` (whose `ac_bonus` now defaults to 0) gained a
    `reactive_damage` (`ReactiveDamageSpec(damage_dice, damage_type)`); the
    scheduler intercept closure now returns a 3-tuple `(ac_bonus, counter,
    reactive_damage)`. On a LANDED melee hit (NOT one parried to a miss),
    `resolve_attack_roll` enqueues an automatic thorns `DamageEvent` FROM the
    bearer (the attack's target) TO the attacker (the attack's actor) — no roll —
    so it (a) routes through the attacker's own #4 response (a fire-resistant
    attacker halves fire thorns) and (b) counts as the bearer's OUTGOING DPR
    (lands in the attacker's damage_received column). Melee-only follows the
    existing Flourish-Parry convention (our only attacker is melee).
  - **The enemy-strikes-back loop (the headline of (a)).** `ScriptedEnemyPolicy`
    in `starfire_scion.py` — structurally identical to `WarAngelEnemyPolicy`
    (CLAUDE.md #12): n melee attacks/turn, targeting pre-rolled at on_combat_start
    so `decide()` stays dice-free. `make_training_dummy` gains an `attack_bonus` +
    flat damage profile (and an optional intrinsic `enemy_resist`) when the row
    carries an `enemy_attack` block; `make_day_runner` attaches the enemy policy
    then. **No shipped L1–L12 row turns it on** (which keeps the existing Scion
    RNG stream — and all prior DPR/ablation tests — bit-identical); it is ready
    machinery for the L15 Fire Shield row, exercised end-to-end by the tests. DPR
    still reads the DUMMY's column (`damage_received_by`), so the enemy's own
    damage to the character can never pollute it.
  - **Validation (consistency/sanity, FakeRNG — NOT number-matching).**
    `tests/test_incoming_damage_thorns.py` (+17): #4 resistance halves the
    matching type only / immunity zeroes / vulnerability doubles / res+vuln cancel
    / untyped unaffected / resistance applies AFTER save-for-half (¼ total); the
    real consumer (Searing Arc fire FROM DATA halved, radiant untouched); the
    cast_effect install + boundary sweep of a resistance. #5 thorns lands on the
    attacker on a hit / never fires on a real miss / is suppressed when the hit is
    parried to a miss / routes through the attacker's fire resistance; the loop
    end-to-end (thorns counts as the bearer's DPR in the enemy's column, the
    enemy's own hit stays in the bearer's column); `ScriptedEnemyPolicy` emits
    action+none swings and honors `char_target_prob`; and `make_day_runner` wires
    the enemy loop (enemy strikes the character while the dummy column still shows
    Scion DPR). The 4 Flourish-Parry tests were updated for the intercept
    closure's new 3-tuple (the only existing tests the contract change touched).
  - **Designed-in, not yet built (registry 4/5 remainder + sequence):** the
    warm/chill **`choose_one`** mode (selects which payload items install); a
    melee-vs-ranged tag on the incoming attack (today thorns assumes melee); the
    10-min day-clock for Fire Shield spanning combats (modeled combat-clock); and
    the L15 Fire-Shield build row. Next in the sequence: outgoing predicate riders
    (6) — Rage / Hunter's Mark — + source-gating tags; then zones (7). See
    `design/buff_primitive.md`.

- **`cast_effect` substrate #3 — StatusSet payload + the debuff `application_save`
  — BUILT & VALIDATED (2026-06-15, session 11).** Step 1 of
  `design/buff_primitive.md` "Next-steps sequence": a `cast_effect` that GRANTS a
  status (advantage/condition/immunity) on its bearer, plus the DEBUFF case where
  the target rolls to resist. **354 tests green (+7).** Branch
  `feature/cast-effect-statusset-payload`. Design contract:
  `design/buff_primitive.md` (registry row 3 flipped to BUILT).
  - **The shape (all reused seams; one named-vocabulary addition).** `Choice`
    gains a `statuses` payload (list of `StatusSpec(name, value, expiry)` — the
    declarative twin of the `modifiers`/`Modifier` payload, new in `statuses.py`)
    and an optional `application_save` (`ApplicationSave(save_stat, dc_stat=
    "spell_save_dc", on_success="negate")`, new in `policy.py`). The scheduler
    `cast_effect` branch: if `application_save` is set, the BEARER (the debuff's
    target) rolls `resolve_saving_throw(bearer, save_stat, caster_dc, rng)` —
    **the exact save machinery save-for-damage uses, debuffs being the same
    primitive target-parameterised**; a made save (`on_success=="negate"`) negates
    the WHOLE payload (modifiers AND statuses). On no-resist, statuses install on
    `bearer.statuses` under `effect_source`.
  - **Statuses change a downstream roll (the substrate's whole point).**
    `resolve_attack_roll` now reads two PERSISTENT advantage grants — read, NEVER
    consumed (unlike one-shot vex/sap), since a 1-minute buff applies on every
    qualifying roll until swept: **`attack_advantage_against`** on the TARGET
    (Faerie Fire — any attacker who can see it, no spell gate) and
    **`spell_attack_advantage`** on the ACTOR (Innate Sorcery — gated on
    `event.is_spell`). The status NAMES are the content↔engine contract, exactly
    like the existing `vex_advantage`/`sapped` keys; the engine stays D&D-agnostic.
  - **First consumers (verified per the per-feature ritual, both speculative — no
    Scion consumer; validated via test policies, not wired into a build).**
    **Innate Sorcery** (2024 Sorcerer L1; D&D Beyond / Roll20): BA, 1 min, 2/LR,
    NO save — advantage on the caster's own Sorcerer-spell attacks + DC +1; modeled
    as the self-grant `spell_attack_advantage` (the "Sorcerer spells only" nuance
    is simplified to the `is_spell` gate — correct for a pure caster; a multiclass
    would need a class-of-origin tag, flagged in the design note). **Faerie Fire**
    (2024 1st-level, Action, Concentration 1 min; D&D Beyond / Roll20 / wikidot):
    DEX save; on FAIL the target is outlined → attacks against it have advantage;
    modeled as a `target`ed `cast_effect` with `application_save(dex_save)` granting
    `attack_advantage_against`. The corpus uses both (neurosoldier 34 "concentrate
    on faerie fire for adv"; lost-voice 42 "innate sorcery … advantage").
  - **Concentration-sweep fix.** A status-only concentration buff (Faerie Fire: no
    modifier, bearer = the enemy, but concentration on the CASTER) would have leaked
    the caster's concentration across combats. The branch now also calls
    `actor.note_combat_buff(effect_source)` when concentration is set, so the
    actor's own combat-boundary `clear_combat_buffs()` drops it. Statuses themselves
    are swept unconditionally by the existing `StatusSet.clear()` at the boundary —
    no new sweep machinery needed.
  - **Validation (consistency/sanity, FakeRNG — NOT number-matching).**
    `tests/test_cast_effect.py` (+7): the granted statuses flip a downstream roll
    (advantage taken, status NOT consumed); the `spell_attack_advantage` spell-gate
    (spell attack → adv, weapon swing → straight); the self-grant installs with no
    DamageEvent; the debuff lands on the target on a FAILED save / the whole payload
    (status + modifier) is negated on a MADE save; **per-save resolution exact at
    the boundary** (dex_save +2 vs DC 15: d20=12 fails/lands, d20=13 makes/resists);
    and the status-only concentration buff is swept (status + caster concentration)
    at the combat boundary. All dice via the seeded/FakeRNG channel; `decide()`
    stays a pure read (the application_save rolls in the SCHEDULER).
  - **Designed-in, not yet built (substrate 3 remainder + sequence):** conditions
    (frightened/restrained), immunity / save-floor grants, the sorcerer-class
    source-gating tag, and a non-"negate" `on_success` mode (lesser effect on a made
    save). Next in the sequence: incoming-damage modifier (4) + defender thorns (5)
    — Fire Shield / Rage, landing with the enemy-strikes-back loop. See
    `design/buff_primitive.md`.

- **Enumerated DICE LADDER (`scaling: ladder`) — the die-SIZE scaled quantity —
  BUILT & VALIDATED (2026-06-15, session 10).** The §4.5 scaling typology's
  next axis after dice-count: a break list paired with an arbitrary `(count,
  sides)` per step, so BOTH size and count can change per break. GENERAL by
  design (build once, reuse) — Shillelagh now, bardic inspiration / superiority /
  psi dice later. **347 tests green (+9).** Branch `feature/dice-size-ladder`.
  - **The shape.** `_resolve_scaling_dice` gains a `scaling: ladder` branch
    (`_resolve_ladder`): reads `breaks` (ascending) + `dice` (one entry per step,
    = len(breaks)+1), resolves the driver via the existing `_level_from_context`
    (any `level_reference`), and indexes with the shared **threshold-list step
    function** `_threshold_index` (factored out, now used by BOTH the cantrip
    count rule and the ladder — `_CANTRIP_THRESHOLDS` is the cantrip's instance of
    the per-feature `breaks` the schema flagged). The ladder resolves BEFORE the
    `base`-parsing the count shapes share (it has no `base`, enumerating a full
    die per step). Loud failures on missing/non-ascending `breaks`, missing
    `dice`, or a length mismatch. Public reader `interpret_scaled_dice(ability,
    context)` folds an ability's single `damage` die (Shillelagh's force die;
    later feeds a `bonus_die` for inspiration/superiority — same scaled quantity).
  - **First consumer — Shillelagh, Starfire Scion L11 (with L11 + L12 rows).**
    Verified vs the 2024 spell (D&D Beyond / Roll20 / dnd2024.wikidot.com +
    build-guide 41:353) per the per-feature ritual: the die scales on the cantrip
    threshold list `[5, 11, 17]` BY CHARACTER LEVEL — **1d8 / 1d10 / 1d12 / 2d6**.
    New `content/abilities/starfire_scion.yaml` `shillelagh` ability carries the
    ladder; the build resolves the die via `interpret_scaled_dice({"character_
    level": L})` at policy init and injects it into `_shillelagh_wis["dice"]`. The
    baked `(1,10)` was REMOVED from the L9/L10 rows (the WIS attack OPTION —
    bonus + which to-hit stat — stays row data; only the DIE is now data-driven).
    L9/L10 retrofit is **DPR-neutral** (ladder yields the same 1d10 — all prior
    L9/L10 tests stayed green). New **L11** (monk-7/druid-4, WIS 19 +4: only
    offense change vs L10 is the 1d10→**1d12** step; monk-7 = Evasion, DPR-inert)
    and **L12** (monk-8/druid-4, **WIS 20** via Resilient → +1 spell to-hit/DC/
    damage; Searing Arc 4d6→**5d6** at slot 3, guide 41:106). Enemy AC/saves live
    from the monster CSV at cr==level (cr11 & cr12 are BOTH AC17/DEX+3).
  - **Validation (consistency/sanity — NOT number-matching).** `test_content.py`
    (+6): ladder steps exact at every break boundary incl. the count-changing top
    step (1d12→2d6); GENERAL across drivers/breaks (a bardic d6→d12 @5/10/15 and a
    superiority d8→d12 @10/18); loud failures (missing level, malformed tables);
    Shillelagh FROM DATA (1d8/1d10/1d12/2d6 @1/5/11/17); `interpret_scaled_dice`
    rejects non-damage shapes. `test_starfire_scion.py` (+3): the die resolves off
    the ladder by character level (1d10 @L9/10, 1d12 @L11/12) and reaches the
    swing; an **L11 die ablation** at the fixed L11 enemy (1d12 20.85 > 1d10 19.89,
    isolating the ladder step — L10/L11 don't share an enemy, AC 16→17); and a
    **fixed-enemy monotonic** L12 > L11 (both AC17/DEX+3, isolating WIS-20 + the
    4d6→5d6 upcast). DPR ladder L9 18.04 / L10 20.41 / L11 20.85 / L12 24.34, all
    under their ceilings (32/36/38/44).
  - **Deferred (unchanged):** the 2d6 L17+ step is in the ladder data but no L17
    row is wired yet; `_CANTRIP_THRESHOLDS`-as-literal stays (the cantrip count
    rule doesn't need a per-feature `breaks` until a non-`[5,11,17]` count scaler
    appears); inspiration/superiority `bonus_die` consumers; ATTACK-TAXONOMY
    typology; Elemental Adept fire; outputs layer.

- **`cast_effect` combat-effect PRIMITIVE — a first-class NON-DAMAGING cast (buffs
  & debuffs) — BUILT & VALIDATED (2026-06-15, session 9).** The first engine
  primitive built design-first against the WHOLE corpus rather than one build's
  immediate need. **338 tests green (+7).** Branch
  `feature/cast-effect-buff-primitive`. Design contract: `design/buff_primitive.md`.
  - **Why / how it was scoped.** The model raised "a combat-long buff" three ad-hoc
    ways (Bless = modifier-stack + `before_combat` sync with round-1 *suppression*;
    Starry Form = free flag in `on_combat_start`; Shillelagh = turn-1 BA
    *suppression*), each faking a different part of the cast. User directed a
    corpus-wide survey of buffs/debuffs BEFORE locking the Choice shape (Rage,
    Sacred Weapon's +CHA-on-attacks, Innate Sorcery's spell-class gating, the auras /
    Gnome Cunning advantage-grants, Fire Shield, the Depth Guard elemental node, …).
  - **The locked design (`design/buff_primitive.md`).** A general **envelope** —
    `Choice(action_type="cast_effect", cost, resource_cost, target, effect_source,
    concentration, duration)` — over a **7-substrate payload registry**:
    (1) ModifierStack [numeric], (2) policy-flag [capability], (3) StatusSet
    [advantage/condition/immunity], (4) incoming-damage modifier [resistance/vuln],
    (5) defender-side reactive rider [thorns], (6) outgoing predicate rider [Rage,
    Hunter's Mark], (7) zone/summon [deferred — multi-enemy/spatial]. Two findings
    fixed the shape: **(a)** ONE cast installs a *set* of labelled payloads across
    substrates — forced by the **Fire Shield** stress test (resistance + thorns +
    warm/chill mode-choice); **(b)** **debuffs are the same primitive,
    target-parameterised** (ModifierStack/StatusSet act on whichever entity holds
    them), needing only an optional `application_save` (reuses the save machinery).
    The `effect_source` label is the thread that makes the whole bundle removable
    (sweep / failed-conc drop) and, later, attachable (riders/zones).
  - **Now-scope built (substrates 1 + 2).** `Choice` gains `effect_source`,
    `modifiers`, `concentration`, `duration`; scheduler `cast_effect` branch
    (`scheduler.py`) installs `modifiers` on the bearer (`target or actor`) under
    `effect_source`, sets the actor's concentration if asked, and pushes NO event —
    action economy + `resource_cost` are drained by the SAME generic code every
    Choice uses. `Entity.note_combat_buff`/`clear_combat_buffs` + a `day_runner`
    combat-boundary sweep remove combat-clock buffs (mirrors `StatusSet.clear()`),
    so a combat-long cast does not leak. War Angel's Bless/MW/Shield are untouched
    (they keep their own `before_combat` sync — not routed through `cast_effect`).
  - **Retrofits (both DPR-neutral, per the build finding).** **Shillelagh** — the
    turn-1 BA is now an honest `cast_effect(cost="bonus_action")` that consumes the
    BA, replacing the "withhold the BA option" suppression (DPR-identical: the BA is
    spent either way; the weapon swings still read `_shillelagh_active`). **Starry
    Form** — activation is a `cast_effect(cost="none")` emitted on turn 1 (the Archer
    form's activation is BUNDLED with its BA attack, so it consumes no separate
    economy — DPR-neutral); the Wild-Shape availability decision stays in
    `on_combat_start`. The same activation shape will carry `cost="bonus_action"` for
    the bare-BA Chalice/Dragon forms when modelled (user's consistency rationale).
  - **Validation (consistency, not number-matching).** `tests/test_cast_effect.py`
    (+6): the self-buff installs a modifier with NO DamageEvent; concentration is set
    on the actor; a `target`ed debuff lands on the enemy not the caster; economy +
    resources are consumed; a capability (no-payload) cast runs clean and is not
    tracked for sweep; `clear_combat_buffs` removes the combat-clock modifier + its
    concentration. `tests/test_starfire_scion.py` (+1, 1 rewritten): the turn-1
    Shillelagh BA is now a `cast_effect` (not a damage option), the BA ladder runs
    from round 2, L1 (no Shillelagh) never casts it; Starry Form activation emits a
    bundled `cost="none"` cast_effect only on round 1 when the form is active. The
    L4/L5/L9/L10 DPR + ablation tests stayed green unchanged → the retrofits are
    DPR-neutral as designed.
  - **DESIGNED-IN, sequenced (not built):** StatusSet payload (3) + `application_save`
    (advantage/condition/immunity + debuff resist — first consumer Innate Sorcery /
    Faerie Fire / Bane); then incoming-damage resistance (4) + defender thorns (5)
    (Fire Shield / Rage, lands with the enemy-strikes-back loop); then outgoing
    riders (6), `choose_one` modes, source-gating tags; zones (7) gated on
    multi-enemy/spatial. See `design/buff_primitive.md` "Next-steps sequence".

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
The L1/L4/L5/L9/L10 ladder is now wired. **The `cast_effect` combat-buff/debuff
PRIMITIVE is DONE (session 9)** — see its Done entry + `design/buff_primitive.md`;
Shillelagh + Starry Form now raise their buffs through it (DPR-neutral). **The
DICE LADDER (`scaling: ladder`) is DONE (session 10)** — see its Done entry; the
Shillelagh die now resolves from YAML by character level (1d8/1d10/1d12/2d6), and
the **L11 + L12 rows are wired** (L11 = the 1d10→1d12 step; L12 = WIS 20 + Searing
Arc 5d6). **The StatusSet payload + `application_save` (substrate #3) is DONE
(session 11)** — see its Done entry; Innate Sorcery / Faerie Fire validated via
test policies. **Substrates #4 + #5 are DONE (session 12)**, **Elemental Adept +
Fire Shield at L15 DONE (session 13)**, and **substrate #6 (outgoing riders) is
DONE (session 14)** — Fount of Moonlight + Primal Strike on the Scion at L15; see
their Done entries + `design/buff_primitive.md`. **Only buff-substrate #7
(zone/summon) remains, gated on the multi-enemy/spatial model.**
**Open next steps (pick with the user):** (0) **FoM concentration follow-up** —
model FoM cast in combat (Magic action turn 1) WITH concentration + the
Starry-Form Dragon concentration-save floor (the Scion's first in-combat
concentration; flagged at session 14); (1) **substrate #7 — zones/summons** (the
last unbuilt substrate: Sunbeam at L19, Spirit Guardians, the elemental node, AoE)
— the biggest remaining engine chunk; (a) **L13/L14/L16+** — backfill / continue
the Scion ladder (data rows; next die-size step is L17 Shillelagh → 2d6, already
in the ladder data; elemental weapon at L13 was dropped from session 14);
(b) the **ATTACK-TAXONOMY** typology (engine-vocabulary work — now THREE consumers:
Searing Arc, Shillelagh, Primal Strike's is_unarmed gate — discuss first); (c) the
**outputs layer** (still ~10% built — design §8). No remaining engine primitive is
forced by the Scion's offense axis below L19; what's left is the zone substrate,
data rows, and the two cross-cutting investments (taxonomy, outputs).

**die-size scaling — BUILT 2026-06-15 (session 10; `scaling: ladder`), first
consumer Shillelagh at Starfire Scion L11.** See the session-10 Done entry. The
original flag (kept for the rationale) follows. 2024 Shillelagh has cantrip
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
