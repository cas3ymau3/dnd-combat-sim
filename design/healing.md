# Healing — decision record and build plan

> **Status: SEMANTICS LOCKED (session 44). NOT YET BUILT.** This is the design note
> that precedes the build, per the standing rule that a broadly-reused primitive gets
> a corpus survey and a design note up front rather than the usual forcing-function
> minimum. The build is the next work item; §6 lists what must be settled inside it.

---

## 1. The finding: healing is not modelled at all

§8 of `design.md` lists "HP recovered" as a missing *output channel*, and
`evaluation_framework.md` §14 carried it as a metric gap. Both understate it.

- **`Entity.heal()` exists and has ZERO callers in `src/`.** There is no healing verb,
  no `Choice` that produces healing, and no policy path that requests it.
- **What looks like healing in the build data is not.** War Angel's Prayer of Healing
  is modelled purely as a **short-rest enabler** — it buys an extra SR's worth of
  resource recovery (see the resource comments in `war_angel.LEVELS`, e.g.
  `"war_priest": (3, "full")  # 9 / LR with PoH + SR`). No HP is ever restored.
- The only HP-restoring line in the whole engine is Silvertail's Aid effect bumping
  `max_hp`/`hp` at cast time (`silvertail.py:601`), which is a buff, not healing.

So "track healing provided by summons" (user, s44) is not a metric addition. It is a
missing subsystem.

## 2. Why this gets a design note first

31 of the 33 build guides mention healing; a keyword pass over the corpus finds Cure
Wounds, Prayer of Healing, Healing Word, Second Wind, Lay on Hands, Aura of Vitality,
Goodberry, Mass Healing Word and Healing Light. Those raw counts **overstate combat
relevance** — many are spells-known lists rather than combat policy, and the survey in
§6.1 is what will separate them. But the breadth is not in doubt: healing is a
cross-cutting primitive, not a one-build feature, which is exactly the case where
designing up front is cheaper than discovering the shape from the first build.

## 3. The constraint that determines everything: the threshold-HP model

`hp` is read in **exactly four places** in the engine:

| site | what it gates |
|---|---|
| `entity.py:217` (`take_damage`) | `dies_at_zero_hp` → sets `destroyed` |
| `entity.py:234` (`is_functionally_dead`) | death-proc triggers |
| `entity.py:239` (`is_alive`) | — |
| `scheduler.py:351` | finite-HP combat termination (all enemies at ≤ 0) |

Two consequences, and they point in opposite directions:

**On the character, healing is mechanically inert.** `dies_at_zero_hp` is False (the
threshold model): HP tracks into negatives, the character always acts for the full
scheduled rounds, and nothing gates on the value. Healing changes no behaviour — only
a reported number.

**On a mortal summon, healing is mechanically live.** With `mortal_beast=True` the
companion carries `dies_at_zero_hp=True`, crossing 0 sets `destroyed`, and the
scheduler stops giving it turns. Healing there genuinely keeps it fighting. **This is
the one place healing has real teeth in the model today**, and Silvertail already
carries the toggle to test it against.

**And a subtlety that makes "just apply it" wrong.** Under the threshold model `hp`
means *max_hp − cumulative damage*, unbounded below. Real D&D floors at 0. So healing
10 to a character sitting at −80 yields −70: it restores nothing, and the resulting
number describes nothing. Applying healing to a threshold tracker is not merely
inert — it is **incoherent**.

## 4. LOCKED semantics (user, s44)

**Ledger always; apply only where `hp` is live.**

1. **Every heal is recorded** in a **source-attributed `(source, target)` ledger**,
   mirroring `damage_by_source_target`. Source attribution is not optional: "healing
   provided by the summon" is a stated requirement, and the s44 lesson was that
   aggregate ledgers silently pool the character's, the summon's and the enemy's
   numbers (see PROGRESS.md's per-metric ritual).
2. **`Entity.heal()` is called only for entities whose `hp` gates behaviour** —
   `dies_at_zero_hp` entities (summons), and enemies under `mode="finite_hp"`. For
   those the existing `min(max_hp, hp + amount)` is already correct: a summon that
   reached 0 is `destroyed`, and revival is a separate concern the `recast` hook owns.
3. **On a threshold-HP character it is ledger-only.** No `hp` mutation.

**Why this is the right line.** It puts the mechanical effect exactly where the
mechanics exist, keeps the incoherent case out of the model rather than papering over
it, and — because a threshold character's `hp` is never read — **cannot move any
existing baseline**. The alternative considered and rejected was flooring the
character's `hp` at 0 so healing behaves like real D&D everywhere; that changes what
`hp` MEANS in a locked model for no measurable gain in the standardized basis.

**The comparable metric is net damage taken.** `net_damage_taken_per_round =
damage_taken − healing_received`, reported beside `healing_per_round`. That works in
the fixed-length 4×4 basis without depending on death, so it does not smuggle in the
de-prioritised finite-HP model (memory `standardized-dpr-baseline-not-realism`).

**The opportunity cost needs no new machinery.** A turn or a slot spent healing is a
turn or a slot not spent dealing damage, and that shows up in DPR automatically. The
healing ledger is the other side of a trade the model already prices.

## 5. Build plan — three pieces, in order

1. **A healing EFFECT in the verb/effect layer.** A `Choice` must be able to produce
   healing, with a declared place in the resolution phase order relative to damage.
   This is the piece that does not exist at all.
2. **The source-attributed ledger + a §13 telemetry channel.** `(source, target)`
   keyed, carried on `CombatResult` → `DayResult` like the damage ledger. Recording
   stays RESOLUTION-only (CLAUDE.md #7).
3. **Metrics — LAST, and as a keyed breakdown.** `healing_per_round`,
   `net_damage_taken_per_round`, and healing-by-source. They must carry the same
   `attribution` axis as damage (a summon's healing counts as the build's under
   `attribution="character_and_summons"`), and they should land as a **breakdown, not
   more flat rows** — the registry is already 51 entries and half of it is three
   vectors flattened. **So piece 3 waits on the output-kinds design** (see
   `evaluation_framework.md` §13 and PROGRESS.md's periodic metric-set review).

## 6. Open questions the build session must settle FIRST

1. **The corpus survey.** Which of the 31 guides' healing references are actual combat
   policy versus spells-known noise? That determines the vocabulary the effect layer
   needs: single-target in-combat (Healing Word), action-cost burst (Cure Wounds),
   over-time (Aura of Vitality), self-only (Second Wind), pool-based (Lay on Hands),
   and out-of-combat/interval (Prayer of Healing, Goodberry). Do this before designing
   the effect's shape, per `design-first-for-cross-cutting-primitives`.
2. **Temporary hit points are a DIFFERENT primitive.** Temp HP is a damage buffer, not
   HP restoration — it does not stack, it expires, and it is consumed before HP. It
   most likely belongs on the modifier/status substrate (`buff_primitive.md`), not
   here. Decide explicitly rather than letting it drift into "healing".
3. **Overhealing.** Healing above `max_hp` is wasted. The ledger should distinguish
   **delivered** from **effective** healing, or the metric overstates a healer's
   contribution. On a threshold character "effective" has no meaning at all — which is
   a reason the ledger records delivered and the *interpretation* is stated in the
   metric definition.
4. **In-combat versus between-combat healing.** The day model already has
   between-combat windows, and Prayer of Healing occupies one as a short-rest enabler.
   Healing that happens between combats is a different quantity from healing under
   fire and should not be pooled into one per-round number.
5. **Does anything about this change the DPR baseline?** It must not. Piece 2 is pure
   observation; piece 1 only mutates `hp` on entities whose `hp` is read, which today
   means mortal summons only. Verify with the §12 parity proof, which stays the
   canary.
