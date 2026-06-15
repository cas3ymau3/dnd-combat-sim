"""
policy.py — Policy protocol and the milestone's trivial DummySwingPolicy.

Design contract (CLAUDE.md §7):
  "Policy (the decide function) reads game state and returns choices; it
   never rolls dice or mutates state."

The Policy protocol defines the interface every policy (character or enemy)
must implement.  GameState is a read-only snapshot passed by the scheduler.

Choice carries the policy's intent for a single action.  The scheduler reads
the choice, checks resource availability, and enqueues the appropriate event.
The policy never touches the event queue directly.

For this milestone there is only one policy: DummySwingPolicy, which always
returns a single melee attack action against its configured target.  This is
the minimum needed to make the policy/resolution boundary concrete.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from .entity import Entity
    from .rng import SeededRNG


# ---------------------------------------------------------------------------
# GameState — read-only view the scheduler hands to the policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GameState:
    """A read-only snapshot of sim state at a decision point.

    frozen=True enforces that the policy cannot mutate it.  The scheduler
    constructs a fresh snapshot each time it opens a decision point.

    Fields
    ------
    actor:
        The entity whose turn it is (the one making decisions).
    enemies:
        List of entities that actor may target.
    allies:
        List of allied entities (excluding actor).
    round_number:
        Current round (1-based).
    turn_index:
        Global turn counter within this round (0-based).
    tick:
        Full current tick tuple, (round, turn_index, sequence).
    resources:
        Dict of remaining resources for actor this turn, e.g.
        {"action": 1, "bonus_action": 1, "reaction": 1}.
        The policy reads this to decide what's still available.
    """

    actor: "Entity"
    enemies: tuple["Entity", ...]
    allies: tuple["Entity", ...]
    round_number: int
    turn_index: int
    tick: tuple[int, int, int]
    resources: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ApplicationSave — the optional debuff resist roll on a cast_effect
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ApplicationSave:
    """A target's saving throw to resist a debuff cast (cast_effect only).

    When a `cast_effect` Choice carries one, the BEARER (the debuff's target)
    rolls `save_stat` (e.g. "dex_save") vs the CASTER's `dc_stat` (the actor's
    spell save DC) before the payload installs.  This reuses the exact save
    machinery (`resolve_saving_throw`) the save-for-damage path uses — debuffs
    are the same primitive, target-parameterised (design/buff_primitive.md).

    `on_success` decides what a made save does to the WHOLE payload (modifiers
    and statuses both): "negate" — the only mode built — means a successful save
    blocks the entire effect (Faerie Fire, Bane).  A lesser-effect-on-success
    debuff would be a new mode added when a consumer needs it.
    """
    save_stat: str
    dc_stat: str = "spell_save_dc"
    on_success: str = "negate"


# ---------------------------------------------------------------------------
# Choice — what the policy wants to do
# ---------------------------------------------------------------------------

@dataclass
class Choice:
    """One action the policy wants to take.

    The scheduler translates each Choice into one or more Events.

    Fields
    ------
    action_type:
        What to do.  For the milestone only "attack" is handled.
        Future values: "cast_spell", "dash", "dodge", "help", "use_item", ...
    cost:
        Which action economy resource this spends.
        One of: "action", "bonus_action", "reaction", "free", "none".
        "none" = Extra Attack follow-up (action cost already paid).
    target:
        The entity being acted on.  None for self-targeting or area effects.
    weapon_stat:
        Stat key for attack bonus lookup.  Default "attack_bonus" covers
        most melee/ranged weapon attacks.  Spell attacks might use
        "spell_attack_bonus".
    resource_cost:
        Optional persistent resource cost, e.g. {"spell_slot_2": 1} for a
        2nd-level spell or {"war_priest": 1} for a War Priest attack.
        The scheduler validates and consumes these from entity.resources
        before enqueuing the event.  None means no persistent resource cost.
    extra_masteries:
        Mastery properties ADDED to this attack on top of the weapon's natural
        mastery, e.g. ["vex"] for Brutality::bluff on a longsword (sap) → the
        attack carries both sap and vex.  Additive, not a replacement.
    mastery_override:
        If set, REPLACES the weapon's natural mastery for this attack (e.g.
        Tactical Master, lvl 16: swap a weapon's mastery for push/sap/slow).
        extra_masteries still stack on top.  None = use the weapon's natural
        mastery unchanged.
    extra_damage_dice:
        Additional dice added to this attack's damage ON HIT, beyond the
        weapon's own dice — e.g. [(1, 6)] for the True Strike cantrip's radiant
        rider (and, later, Wrathful Smite).  Each (n, sides) tuple is rolled
        into the damage pool and, like the weapon dice, has its die count
        doubled on a crit (CLAUDE.md §8).  Empty = a plain weapon attack.
    """

    action_type: str
    cost: str = "action"
    target: "Entity | None" = None
    weapon_stat: str = "attack_bonus"
    resource_cost: dict[str, int] | None = None
    extra_masteries: list[str] = field(default_factory=list)
    mastery_override: "str | None" = None
    extra_damage_dice: list[tuple[int, int]] = field(default_factory=list)
    # Flat damage added to this attack on hit beyond the weapon's damage_bonus,
    # e.g. Brutality::bleed's +CHA mod.  Threaded to the AttackRollEvent.
    extra_flat_damage: int = 0
    # --- Per-attack damage profile / save-FOR-damage dice ---
    # `damage_dice`/`damage_bonus` carry this Choice's OWN damage, used in two
    # ways depending on action_type:
    #   - action_type == "attack": a PER-ATTACK OVERRIDE of the actor's weapon
    #     (the multi-weapon gish primitive — quarterstaff 1d8 vs unarmed 1d6 vs an
    #     Archer spell attack 1d8+WIS vs Guiding Bolt 4d6).  Left None for a
    #     single-weapon build → the resolver reads actor.stat("damage_dice").
    #   - action_type == "save_spell": the SPELL's own dice (Sacred Flame, Burning
    #     Hands), carried here rather than pulled from the weapon stat.
    # For save_spell the TARGET rolls `save_stat` (e.g. "dex_save") vs the actor's
    # `dc_stat` (spell save DC) and `on_save` decides the result — "none" (save
    # negates — Sacred Flame) or "half" (save for half — Burning Hands).
    save_stat: "str | None" = None
    dc_stat: str = "spell_save_dc"
    damage_dice: "tuple[int, int] | None" = None
    damage_bonus: int = 0
    on_save: str = "none"
    # Damage type + spell-source flag, threaded to the spawned event → DamageEvent.
    # The caster-side Fueled-Spellfire decision point gates on "spell radiant
    # damage" (damage_type == "radiant" and is_spell).  So Guiding Bolt / Sacred
    # Flame set damage_type="radiant", is_spell=True; Starry-Form Archer is
    # radiant but a feature (is_spell=False); plain weapon attacks leave both unset.
    damage_type: "str | None" = None
    is_spell: bool = False
    # --- cast_effect: a first-class non-damaging cast (buff/debuff) ---
    # action_type="cast_effect" installs a PERSISTING effect and pushes NO
    # DamageEvent (the honest model for raising a combat-long buff, or a debuff on
    # an enemy — see design/buff_primitive.md).  The scheduler drains `cost` +
    # `resource_cost` generically (as for any Choice), then routes the payload:
    #   - `modifiers`: pushed onto the BEARER's ModifierStack under `effect_source`
    #     (bearer = `target` if set — a debuff — else the actor — a self-buff);
    #   - `statuses`: applied to the BEARER's StatusSet under the same bearer rule
    #     (substrate #3 — advantage/condition/immunity grants, e.g. Faerie Fire on
    #     a target or Innate Sorcery on self);
    #   - `concentration`: when True, sets the ACTOR's concentration = effect_source;
    #   - `application_save`: debuff-only — the bearer rolls to resist; a made save
    #     negates the WHOLE payload (modifiers + statuses).  None = it always lands.
    #   - capability buffs carry NO payload — the policy reads its own flag; the
    #     cast_effect exists only to consume the action economy honestly.
    # `duration="combat"` modifiers are swept at the combat boundary; "day" (10-min/
    # 1-hr buffs spanning combats) is reserved for the DurationBuffTracker path.
    # (Combat-clock STATUSES are swept unconditionally by StatusSet.clear, so they
    # need no duration bookkeeping.)
    # `modifiers`/`statuses` hold Modifier/StatusSpec instances (typed loosely to
    # avoid an import cycle); `application_save` holds an ApplicationSave.
    effect_source: "str | None" = None
    modifiers: list = field(default_factory=list)
    statuses: list = field(default_factory=list)
    concentration: bool = False
    duration: str = "combat"
    application_save: "ApplicationSave | None" = None


# ---------------------------------------------------------------------------
# Post-roll decision point: a MISS the policy may respond to (Guided Strike)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissContext:
    """Read-only context handed to Policy.on_miss when one of the actor's
    attacks misses.  The policy inspects it and decides whether to spend a
    resource to add to the roll (e.g. War Cleric's Guided Strike: +10).

    Fields
    ------
    actor / target:
        The attacker and its target.
    missed_by:
        How far the roll fell short: target_ac - total_roll (> 0 on a miss).
        Guided Strike (+10) flips the miss iff missed_by <= 10.
    is_aoo:
        True if the missed attack was an opportunity attack (cost="reaction").
        (At level 5 the build forbids Guided Strike on AoOs.)
    resources:
        Flat {name: current} view of the actor's persistent resources.
    round_number:
        Current combat round (1-based) — lets the policy apply per-combat caps.
    """
    actor: "Entity"
    target: "Entity | None"
    missed_by: int
    is_aoo: bool
    resources: dict[str, int]
    round_number: int


@dataclass(frozen=True)
class MissResponse:
    """The policy's answer to a MissContext: spend `resource_cost` to add
    `bonus` to the attack roll.  Return None from on_miss to decline.

    The scheduler validates the resource is affordable, consumes it, and adds
    `bonus` to the roll; if that turns the miss into a hit, damage resolves
    normally (a Guided-Strike-rescued hit is NOT a crit — the d20 wasn't 20).
    """
    resource_cost: dict[str, int]
    bonus: int


# ---------------------------------------------------------------------------
# Post-roll decision point: a HIT the policy may respond to (Wrathful Smite)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HitContext:
    """Read-only context handed to Policy.on_hit when one of the actor's
    attacks hits, BEFORE the DamageEvent is built.  The policy may choose to
    spend a resource (and an action-economy slot) to add damage dice to this
    hit — e.g. a smite spell adding 1d6, doubled on a crit.

    Fields
    ------
    actor / target:
        The attacker and its target.
    is_crit:
        Whether the hit was a crit (so the policy knows the extra dice double).
    cost:
        The action-economy tag of the HITTING attack ("action", "bonus_action",
        "reaction", "none").  A bonus-action response (smite) may NOT ride a
        reaction/AoO — 2024 bonus actions only happen on your own turn.
    bonus_action_available:
        Whether the current turn's bonus action is still unspent (e.g. it was
        already used on a War Priest attack this turn).
    resources:
        Flat {name: current} view of the actor's persistent resources.
    round_number:
        Current combat round (1-based).
    """
    actor: "Entity"
    target: "Entity | None"
    is_crit: bool
    cost: str
    bonus_action_available: bool
    resources: dict[str, int]
    round_number: int


@dataclass(frozen=True)
class HitResponse:
    """The policy's answer to a HitContext: spend `resource_cost` and optionally
    an action-economy slot (`action_cost`) to add `extra_damage_dice` and/or
    `extra_masteries` to this hit.  Return None from on_hit to decline.

    The scheduler validates affordability (both the persistent resource AND, if
    action_cost is not None, the action-economy slot in the current turn),
    consumes them, and folds the dice + masteries into this hit's DamageEvent
    (dice double on a crit like any others; masteries are applied on the hit).

    action_cost=None means no action-economy slot is consumed (e.g. Brutality::
    bluff — it costs only a brutality charge, not a bonus action).

    self_status_on_hit, if set, is a status applied to the ATTACKER on this hit,
    lasting until the end of its next turn (consumed earlier on first use) — e.g.
    Brutality::bluff's "advantage on your next saving throw", which the
    concentration save reads.  None = no self-status.
    """
    resource_cost: dict[str, int]
    extra_damage_dice: list[tuple[int, int]]
    extra_masteries: list[str] = field(default_factory=list)
    action_cost: "str | None" = "bonus_action"
    self_status_on_hit: "str | None" = None


# ---------------------------------------------------------------------------
# In-flight interception: a DEFENDER reacting to an incoming hit (intercept_event)
# ---------------------------------------------------------------------------
# Design §4 #15 (intercept_event): a reaction that reaches into an in-flight
# incoming attack and alters it — change AC after seeing the roll (Shield,
# Defensive Duelist, Flourish Parry), force a miss, etc.  Unlike on_miss/on_hit
# (which consult the ATTACKER's policy), this consults the DEFENDER's policy: the
# scheduler offers it to the target of a hit BEFORE damage resolves.

@dataclass(frozen=True)
class IncomingAttackContext:
    """Read-only context handed to the DEFENDER's Policy.on_incoming_hit when an
    attack has hit them, BEFORE the DamageEvent is built.  The defender has seen
    the roll (Shield-spell-style) and may spend a reaction/resource to raise AC.

    Fields
    ------
    defender / attacker:
        The entity that was hit (and reacts) and the entity that hit it.
    hit_margin:
        total_roll - target_ac (>= 0, since this fires only on a hit).  A +N AC
        bump flips the hit to a miss iff N > hit_margin.
    cost:
        The action-economy tag of the INCOMING attack ("action"/"none"/...).
        Flourish Parry only triggers on melee attacks; our only attacker is
        melee, so the policy treats every incoming hit as meleeable.
    resources:
        Flat {name: current} view of the DEFENDER's persistent resources.
    round_number:
        Current combat round (1-based) — the policy self-gates the once-per-round
        reaction by comparing this to the last round it parried.
    """
    defender: "Entity"
    attacker: "Entity"
    hit_margin: int
    cost: str
    resources: dict[str, int]
    round_number: int


@dataclass(frozen=True)
class CounterSpec:
    """A follow-up attack the defender makes AS PART OF the same reaction (e.g.
    Flourish Counter).  Built by the policy; the scheduler turns it into an
    AttackRollEvent with policy_riders=False (so it carries its own bleed and
    does NOT spawn Wrathful Smite / bluff).

    Fields
    ------
    target:
        Whom to counter — normally the attacker (ctx.attacker).
    weapon_stat:
        Attack-bonus stat key (default "attack_bonus").
    masteries:
        Mastery properties applied on the counter's hit, e.g. ["sap"] (bleed).
    extra_flat_damage:
        Flat bonus damage on the counter's hit, e.g. +CHA mod (bleed).
    """
    target: "Entity"
    weapon_stat: str = "attack_bonus"
    masteries: list[str] = field(default_factory=list)
    extra_flat_damage: int = 0


@dataclass(frozen=True)
class InterceptResponse:
    """The defender's answer to an IncomingAttackContext: spend `resource_cost`
    to add `ac_bonus` to AC against this one attack (potentially flipping it to a
    miss), and optionally make a `counter` attack.  Return None to decline.

    The scheduler validates affordability against the DEFENDER's resources,
    consumes them, applies the AC bump in resolve_attack_roll, and — if the bump
    flips the hit to a miss and a counter is present — enqueues the counter.

    The reaction itself is NOT modeled as an engine resource here: the policy
    self-gates it (once per round), decoupled from the opportunity-attack
    reaction per the build guide's explicit assumption.
    """
    ac_bonus: int
    resource_cost: dict[str, int] = field(default_factory=dict)
    counter: "CounterSpec | None" = None


# ---------------------------------------------------------------------------
# Failed-save rescue: rerolling a save you just failed (Indomitable / Luck)
# ---------------------------------------------------------------------------
# The symmetric analog of Guided Strike (which rescues a missed ATTACK): a
# resource that lets you reroll a save you just FAILED.  The scheduler offers it
# (if the policy implements on_failed_save) at the moment a save fails, BEFORE
# the failure's consequences land (e.g. before concentration drops).  Like the
# other post-roll deciders it consults the policy, which alone decides whether
# the rescue is worth spending the resource on.

@dataclass(frozen=True)
class FailedSaveContext:
    """Read-only context handed to Policy.on_failed_save the instant a save
    fails, so the policy may spend a resource to reroll it.

    Fields
    ------
    entity:
        The entity that failed the save (and would reroll).
    save_kind:
        What the save was for, so the policy can scope its rescue rule.  The
        only scheduled save today is "concentration"; future kinds (e.g.
        "frightened") will flow through here unchanged.
    save_stat:
        The save's stat key (e.g. "con_save") — lets the policy reason about
        which saves it is weak at once multiple kinds exist.
    dc:
        The save DC.  Together with `save_bonus` this is the policy's
        DC-assessment input: "can a reroll plausibly clear this?"
    save_bonus:
        The entity's FLAT save bonus on this stat (no rolled-dice buffs like
        Bless folded in), so the assessment is deterministic and conservative.
    failed_total:
        What the failed roll totaled (d20 + bonus) — how close the miss was.
    resources:
        Flat {name: current} view of the entity's persistent resources.
    round_number:
        Current combat round (1-based).  Lets the policy decline a rescue with
        no remaining value (e.g. a concentration check on the final round, with
        no future rounds for the spell to protect).
    """
    entity: "Entity"
    save_kind: str
    save_stat: str
    dc: int
    save_bonus: int
    failed_total: int
    resources: dict[str, int]
    round_number: int


@dataclass(frozen=True)
class SaveRerollResponse:
    """The policy's answer to a FailedSaveContext: spend `resource_cost` to
    reroll the save with a flat `bonus` added to the new roll (Indomitable adds
    the fighter level).  Return None to accept the failure.

    The scheduler validates affordability and consumes the resource; the verb
    rerolls a fresh d20 (+ the entity's save bonus + this `bonus`) and the new
    result stands, per RAW (you must use the reroll).
    """
    bonus: int
    resource_cost: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Post-damage caster decision point: a damage roll the caster may augment
# (Fueled Spellfire — the on_hit analog on the *damage* side)
# ---------------------------------------------------------------------------
# Unlike on_hit (which fires before the DamageEvent is built and only on the
# attack-roll path), this fires AS a DamageEvent resolves — the one chokepoint
# every damage delivery funnels through — so a single hook covers attack-roll
# spells (Guiding Bolt) and save-for-damage spells (Sacred Flame) alike, and any
# future radiant spell (Sunbeam, Fount of Moonlight) for free.  It consults the
# CASTER's policy (the entity dealing the damage).

@dataclass(frozen=True)
class DealDamageContext:
    """Read-only context handed to the CASTER's Policy.on_deal_damage as one of
    its damage rolls resolves, so the policy may spend a resource to add dice to
    that roll (Fueled Spellfire: expend Hit Dice into a radiant spell's damage).

    Fields
    ------
    actor / target:
        The entity dealing the damage (the caster) and the entity taking it.
    damage_type:
        The damage's type, e.g. "radiant" (None = untyped).  Fueled Spellfire
        fires only on radiant damage.
    is_spell:
        Whether the damage is from a SPELL (vs a weapon/feature).  Fueled
        Spellfire requires a spell — so Starry-Form Archer (radiant, but a
        feature) is correctly excluded.
    is_crit:
        Whether the hitting attack was a crit.  Informational: the engine does
        NOT crit-double the rider dice (they are a fixed Hit-Dice expenditure).
    base_damage_dice:
        The spell's own (count, sides) for this roll — lets the policy gauge how
        much the rider adds relative to the base.
    resources:
        Flat {name: current} view of the caster's persistent resources.
    round_number / turn_index:
        The current (round, turn) — lets the policy enforce a per-turn cap
        (Fueled Spellfire is 1/turn) across multiple radiant rolls in one turn.
    """
    actor: "Entity"
    target: "Entity | None"
    damage_type: "str | None"
    is_spell: bool
    is_crit: bool
    base_damage_dice: tuple[int, int]
    resources: dict[str, int]
    round_number: int
    turn_index: int


@dataclass(frozen=True)
class DamageRiderResponse:
    """The caster's answer to a DealDamageContext: spend `resource_cost` to add
    `extra_damage_dice` to this damage roll (Fueled Spellfire = up to 2 Hit Dice
    → [(n, 8)]).  Return None to decline.

    The scheduler validates affordability and consumes the resource; the verb
    rolls the dice and adds them to the damage total.  Per the design decision the
    rider dice are NOT crit-doubled (a fixed expenditure, not the spell's own
    dice) and are added before save-for-half halving (sharing the spell's fate).
    """
    extra_damage_dice: list[tuple[int, int]]
    resource_cost: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Policy protocol
# ---------------------------------------------------------------------------

class Policy(Protocol):
    """Interface every policy (character or enemy) must satisfy.

    decide() is called by the scheduler at each decision point.  It must:
      - read only (no dice, no state mutation)
      - return a list of Choices in the order they should be executed
      - respect the resources dict in snapshot (don't spend what isn't there)

    on_combat_start() is OPTIONAL.  DayRunner calls it (if defined) before each
    combat so a policy can reconfigure its per-combat internal state using the
    shared seeded RNG.  Two intended uses:
      - a character policy pre-rolls a per-combat random choice (e.g. the War
        Angel's single attack-of-opportunity slot);
      - an enemy meta-policy rolls to pick its archetype for the upcoming combat
        (e.g. melee_aggressive vs. ranged_kiter), which decide() then reads.
    The contract is the same in both cases: receive the combat index and the
    RNG, mutate the policy's own state, return nothing.  decide() stays
    dice-free; any per-combat randomness is drawn here instead.
    """

    def decide(self, snapshot: GameState) -> list[Choice]:
        ...

    # Optional — not all policies implement it; DayRunner checks with hasattr.
    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        ...

    # Optional post-roll decision point.  The scheduler calls it (if defined)
    # when one of the actor's attacks misses, BEFORE finalizing the roll, so the
    # policy may spend a resource to add to the roll (Guided Strike).  Return a
    # MissResponse to spend, or None to decline.  This is a *commit* point, so —
    # unlike decide() — the policy may update its own per-combat bookkeeping
    # (e.g. a Guided-Strike-per-combat counter) when it returns a response.
    def on_miss(self, ctx: MissContext) -> "MissResponse | None":
        ...

    # Optional post-roll decision point on a HIT, BEFORE the DamageEvent is
    # built, so the policy may spend a resource + action-economy slot to add
    # damage dice to this hit (Wrathful Smite / Divine Smite).  Return a
    # HitResponse to spend, or None to decline.  Also a commit point.
    def on_hit(self, ctx: HitContext) -> "HitResponse | None":
        ...

    # Optional in-flight interception (intercept_event).  The scheduler calls it
    # (if defined) on the DEFENDER's policy when an attack HITS this entity,
    # BEFORE the DamageEvent is built, so the defender may spend a reaction/
    # resource to raise AC (Shield, Flourish Parry) and possibly counter.  Return
    # an InterceptResponse to react, or None to decline.  A commit point: the
    # policy may update its own bookkeeping (e.g. the once-per-round parry gate).
    def on_incoming_hit(self, ctx: IncomingAttackContext) -> "InterceptResponse | None":
        ...

    # Optional failed-save rescue (Indomitable / Luck).  The scheduler calls it
    # (if defined) the instant one of this entity's saves FAILS, BEFORE the
    # failure's consequences land, so the policy may spend a resource to reroll
    # with a bonus.  Return a SaveRerollResponse to spend, or None to accept the
    # failure.  A commit point: the policy may update its own bookkeeping.
    def on_failed_save(self, ctx: FailedSaveContext) -> "SaveRerollResponse | None":
        ...

    # Optional post-damage CASTER decision point.  The scheduler calls it (if
    # defined) as one of this entity's damage rolls resolves, so the policy may
    # spend a resource to add dice to that roll (Fueled Spellfire).  Return a
    # DamageRiderResponse to spend, or None to decline.  A commit point: the
    # policy may update its own bookkeeping (e.g. the 1/turn fuel gate).
    def on_deal_damage(self, ctx: DealDamageContext) -> "DamageRiderResponse | None":
        ...


# ---------------------------------------------------------------------------
# DummySwingPolicy — always swing, nothing else
# ---------------------------------------------------------------------------

class DummySwingPolicy:
    """Trivial policy: spend the action on a single melee attack, every turn.

    Used for the "swing at the dummy" milestone.  Makes the policy/resolution
    boundary concrete with the minimum possible logic.

    Parameters
    ----------
    target:
        The entity to attack.  Fixed at construction time for simplicity.
        Real policies will choose dynamically from snapshot.enemies.
    """

    def __init__(self, target: "Entity") -> None:
        self._target = target

    def decide(self, snapshot: GameState) -> list[Choice]:
        # Only spend the action if we still have one.
        if snapshot.resources.get("action", 0) < 1:
            return []
        return [
            Choice(
                action_type="attack",
                cost="action",
                target=self._target,
                weapon_stat="attack_bonus",
            )
        ]


class ScriptedEnemyPolicy:
    """Melee-aggressive enemy: attacks the first visible character every turn.

    Designed to accept a flat stat block dict so the interface is identical
    whether the stats come from a hardcoded value or a CSV row lookup.  When
    the monster table is ready, callers just pass ``csv_row.to_dict()`` as
    ``stat_block`` and nothing else changes.

    Parameters
    ----------
    stat_block:
        Dict of the enemy's combat stats, same key conventions as Entity:
          "attack_bonus"  — added to d20 rolls
          "damage_dice"   — (n, sides) tuple
          "damage_bonus"  — flat damage bonus
        Any key not present defaults to 0 / (1, 4) via Entity.stat().
    archetype:
        Behavioral tag.  Currently only "melee_aggressive" is implemented:
        spend the action on one melee attack against snapshot.enemies[0].
        Future archetypes: "spell_aggressive" (save-targeting), "ranged", …
    extra_attacks:
        Number of additional no-cost attacks beyond the primary action swing.
        Defaults to 0 (one swing per turn).  Set to 1 for multi-attack enemies.
    """

    SUPPORTED_ARCHETYPES = {"melee_aggressive"}

    def __init__(
        self,
        stat_block: dict,
        archetype: str = "melee_aggressive",
        extra_attacks: int = 0,
    ) -> None:
        if archetype not in self.SUPPORTED_ARCHETYPES:
            raise ValueError(
                f"Unknown archetype {archetype!r}. "
                f"Supported: {self.SUPPORTED_ARCHETYPES}"
            )
        self.stat_block = stat_block
        self.archetype = archetype
        self.extra_attacks = extra_attacks

    def decide(self, snapshot: GameState) -> list[Choice]:
        if not snapshot.enemies:
            return []
        if snapshot.resources.get("action", 0) < 1:
            return []

        target = snapshot.enemies[0]
        choices: list[Choice] = []

        choices.append(Choice(
            action_type="attack",
            cost="action",
            target=target,
            weapon_stat="attack_bonus",
        ))
        for _ in range(self.extra_attacks):
            choices.append(Choice(
                action_type="attack",
                cost="none",
                target=target,
                weapon_stat="attack_bonus",
            ))
        return choices


class ExtraAttackPolicy:
    """Policy for a fighter with Extra Attack: two weapon attacks per action.

    Emits the primary attack (cost="action") followed by one extra attack
    (cost="none" — action already spent).  The scheduler enqueues them in
    emission order so they resolve sequentially within the same turn.

    An optional bonus_action_attack parameter adds a third attack charged to
    the bonus action (e.g. Nick mastery or two-weapon fighting).  When
    included, it is emitted between the two main swings so its sequence slot
    falls naturally after the first hit (for policies that would smite on that
    hit — not wired yet, but the ordering is correct).

    Parameters
    ----------
    target:
        Fixed target entity.  Real policies pick from snapshot.enemies.
    extra_attacks:
        Number of *additional* attacks beyond the primary action attack.
        1 → two total (standard Extra Attack at level 5).
        2 → three total (level-11 fighter, etc.).
    bonus_action_attack:
        If True, also emit one bonus-action attack (cost="bonus_action")
        interleaved after the first main swing.
    """

    def __init__(
        self,
        target: "Entity",
        extra_attacks: int = 1,
        bonus_action_attack: bool = False,
    ) -> None:
        self._target = target
        self._extra_attacks = extra_attacks
        self._bonus_action_attack = bonus_action_attack

    def decide(self, snapshot: GameState) -> list[Choice]:
        if snapshot.resources.get("action", 0) < 1:
            return []

        choices: list[Choice] = []

        # Primary attack spends the action.
        choices.append(Choice(
            action_type="attack",
            cost="action",
            target=self._target,
            weapon_stat="attack_bonus",
        ))

        # Optional bonus-action attack interleaved right after the first swing.
        if self._bonus_action_attack and snapshot.resources.get("bonus_action", 0) >= 1:
            choices.append(Choice(
                action_type="attack",
                cost="bonus_action",
                target=self._target,
                weapon_stat="attack_bonus",
            ))

        # Extra Attack follow-ups; action already paid.
        for _ in range(self._extra_attacks):
            choices.append(Choice(
                action_type="attack",
                cost="none",
                target=self._target,
                weapon_stat="attack_bonus",
            ))

        return choices
