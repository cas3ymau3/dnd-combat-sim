"""enemy.py — the shared scripted enemy policy used by the concrete builds.

CLAUDE.md decision #12: "Enemy policy is structurally identical to character
policy ... Near-term target is a ``ScriptedEnemyPolicy(archetype, stats_by_level)``
driven by ``reference/data/monster_ac_and_saves_by_level.csv``."

This module collapses the two byte-identical build-local enemy policies that grew
up in parallel — War Angel's ``WarAngelEnemyPolicy`` (forces concentration checks
on Bless, L13+) and the Starfire Scion's ``ScriptedEnemyPolicy`` (opens the
character's on_incoming_hit seam for Fire-Shield thorns) — into one reusable class
that both builds import.

What the policy itself owns is just the TARGETING shape: it makes ``n_attacks``
melee attacks per turn, each (pre-rolled at on_combat_start so ``decide()`` stays
dice-free, mirroring the character policies' AoO pre-roll) landing on the character
with probability ``char_target_prob`` — else a party member, which we don't model,
so a no-op for our metrics.  The first character-aimed swing costs the action; the
rest are free multiattack swings (cost "none").  The enemy makes no decisions
beyond targeting (flat damage, no riders).

What the policy does NOT own (deliberately, to keep this a pure refactor): the
enemy's numeric profile — attack_bonus / damage_dice / damage_bonus / intrinsic
damage_response — lives on the *dummy Entity*, assembled by each build's
``make_training_dummy`` from its per-level row (which is where the
monster_ac_and_saves_by_level.csv values are already sourced).  Pulling that CSV
into the policy by level is the unrealised half of decision #12 and is left for a
follow-up: it is a new capability, not part of merging the duplicates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..policy import Choice, GameState

if TYPE_CHECKING:
    from ..entity import Entity
    from ..rng import SeededRNG


class ScriptedEnemyPolicy:
    """Minimal melee enemy that strikes the character to make DEFENDER-side
    effects do real work (War Angel: concentration checks on Bless; Starfire
    Scion: the on_incoming_hit seam for Fire-Shield thorns — substrate #5, and
    incoming-damage resistance — substrate #4).

    Makes ``n_attacks`` attacks per turn; each independently targets the character
    with probability ``char_target_prob`` (else a party member — not modeled, so a
    no-op for our metrics).  Targeting is PRE-ROLLED per (round, attack slot) at
    ``on_combat_start`` so ``decide()`` stays dice-free, mirroring the character
    policies' AoO pre-roll.  The enemy's own damage to the character lands in the
    character's damage_received column, never the dummy's, so it never pollutes DPR.
    """

    def __init__(
        self,
        target: "Entity",
        n_attacks: int = 2,
        char_target_prob: float = 1.0,
        rounds_per_combat: int = 4,
    ) -> None:
        self._target = target
        self._n_attacks = n_attacks
        self._p_pct = int(round(char_target_prob * 100))
        self._rounds = rounds_per_combat
        self._targets_char: dict[int, list[bool]] = {}

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        # Pre-roll, per round and attack slot, whether it lands on the character.
        self._targets_char = {
            r: [rng.roll_one(100) <= self._p_pct for _ in range(self._n_attacks)]
            for r in range(1, self._rounds + 1)
        }

    def decide(self, snapshot: GameState) -> list[Choice]:
        if snapshot.resources.get("action", 0) < 1:
            return []
        choices: list[Choice] = []
        for targets_char in self._targets_char.get(snapshot.round_number, []):
            if not targets_char:
                continue  # party-aimed: unmodeled → no-op for our metrics
            # First attack at the character spends the action; the rest are
            # free multiattack swings (cost "none").
            choices.append(Choice(
                action_type="attack",
                cost="action" if not choices else "none",
                target=self._target,
                weapon_stat="attack_bonus",
            ))
        return choices
