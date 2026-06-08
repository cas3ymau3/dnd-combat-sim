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
    """

    action_type: str
    cost: str = "action"
    target: "Entity | None" = None
    weapon_stat: str = "attack_bonus"


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
