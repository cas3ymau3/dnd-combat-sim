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
    """

    action_type: str
    cost: str = "action"
    target: "Entity | None" = None
    weapon_stat: str = "attack_bonus"
    resource_cost: dict[str, int] | None = None
    extra_masteries: list[str] = field(default_factory=list)
    mastery_override: "str | None" = None


# ---------------------------------------------------------------------------
# Policy protocol
# ---------------------------------------------------------------------------

class Policy(Protocol):
    """Interface every policy (character or enemy) must satisfy.

    decide() is called by the scheduler at each decision point.  It must:
      - read only (no dice, no state mutation)
      - return a list of Choices in the order they should be executed
      - respect the resources dict in snapshot (don't spend what isn't there)
    """

    def decide(self, snapshot: GameState) -> list[Choice]:
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
