"""enemy.py — the shared scripted enemy policy used by the concrete builds.

CLAUDE.md decision #12: "Enemy policy is structurally identical to character
policy ... Near-term target is a ``ScriptedEnemyPolicy(archetype, stats_by_level)``
driven by per-level monster data."  Decision #12's "stats_by_level" is now the
definitive ``reference/data/monster_stats_by_level.csv`` (loaded by ``enemy_stats``);
``BaselineEnemyPolicy`` below is its full realisation (per-level attack bonus / save DC
/ DICE + an attack-vs-save mix), while the legacy ``ScriptedEnemyPolicy`` keeps the
simpler targeting-only behavior the earlier builds rely on.

This module collapses the two byte-identical build-local enemy policies that grew
up in parallel — War Angel's ``WarAngelEnemyPolicy`` (forces concentration checks
on Bless, L13+) and the Starfire Scion's ``ScriptedEnemyPolicy`` (opens the
character's on_incoming_hit seam for Fire-Shield thorns) — into one reusable class
that both builds import.

What the policy itself owns is just the TARGETING shape, in one of two modes:

  - LEGACY single-target (``roster=None``): it makes ``n_attacks`` melee attacks
    per turn, each landing on the character with probability ``char_target_prob`` —
    else a party member, which we don't model, so a no-op for our metrics.  This is
    the original 1-vs-1 behavior and stays byte-identical (every prior build/test
    runs through it unchanged).

  - MULTI-ENTITY (``roster=[(entity, weight), ...]``): substrate #7 / design.md
    §3.5 — each attack is split across the FRIENDLY ROSTER by trait-adjusted
    integer WEIGHTS (the melee character weighted higher than a passive party
    member), so attacks aimed at the party DON'T reach the character's defender-side
    reactions (Fire-Shield thorns), dissolving the single-dummy thorns over-count.

Either way targeting is PRE-ROLLED per (round, attack slot) at ``on_combat_start``
so ``decide()`` stays dice-free, mirroring the character policies' AoO pre-roll.
The first swing costs the action; the rest are free multiattack swings (cost
"none").  The enemy makes no decisions beyond targeting (flat damage, no riders).

``ScriptedEnemyPolicy``'s own numeric profile (attack_bonus / damage / intrinsic
damage_response) lives on the *dummy Entity*.  ``BaselineEnemyPolicy`` (below) instead
draws its full numeric profile from the definitive per-level table via ``enemy_stats``
— decision #12's previously-unrealised half: the dummy Entity carries the table's AC /
saves / attack bonus / save DC, and the policy supplies the per-level per-swing /
AoE DICE (so enemy crits fall out) plus an attack-vs-save round mix and retargeting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..policy import Choice, GameState
from .enemy_stats import (
    SAVE_ROUND_PROB,
    SAVE_TYPE_WEIGHTS,
    baseline_aoe_dice,
    baseline_attack_dice,
    baseline_n_attacks,
)

if TYPE_CHECKING:
    from ..entity import Entity
    from ..rng import SeededRNG


class ScriptedEnemyPolicy:
    """Minimal melee enemy that strikes the character to make DEFENDER-side
    effects do real work (War Angel: concentration checks on Bless; Starfire
    Scion: the on_incoming_hit seam for Fire-Shield thorns — substrate #5, and
    incoming-damage resistance — substrate #4).

    Makes ``n_attacks`` attacks per turn.  In the LEGACY mode (``roster=None``) each
    independently targets the character with probability ``char_target_prob`` (else
    a party member — not modeled, so a no-op for our metrics).  In MULTI-ENTITY mode
    (``roster`` given) each is split across the weighted friendly roster.  Targeting
    is PRE-ROLLED per (round, attack slot) at ``on_combat_start`` so ``decide()``
    stays dice-free, mirroring the character policies' AoO pre-roll.  The enemy's own
    damage to the character lands in the character's damage_received column, never
    the dummy's, so it never pollutes DPR.
    """

    def __init__(
        self,
        target: "Entity",
        n_attacks: int = 2,
        char_target_prob: float = 1.0,
        rounds_per_combat: int = 4,
        roster: "list[tuple[Entity, int]] | None" = None,
        damage_type: "str | None" = None,
    ) -> None:
        self._target = target
        self._n_attacks = n_attacks
        self._p_pct = int(round(char_target_prob * 100))
        self._rounds = rounds_per_combat
        # Optional damage TYPE on the enemy's swings (default None = untyped, the
        # legacy behavior).  A typed swing lets a defender's typed/all damage
        # response bite — e.g. Warding Bond's resistance-to-all on the silvertail
        # beast (substrate #7 / 7c-on-summon) halves a typed hit before redirect.
        self._damage_type = damage_type
        # Multi-entity targeting roster: [(friendly_entity, integer_weight), ...].
        # None → legacy single-target behavior (char_target_prob).  Given → weighted
        # split across the roster (design.md §3.5 trait-weighted targeting).
        self._roster = roster
        self._targets_char: dict[int, list[bool]] = {}
        self._picks: dict[int, list["Entity"]] = {}

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        if self._roster is None:
            # LEGACY: pre-roll, per round and attack slot, whether it lands on char.
            self._targets_char = {
                r: [rng.roll_one(100) <= self._p_pct for _ in range(self._n_attacks)]
                for r in range(1, self._rounds + 1)
            }
        else:
            # MULTI-ENTITY: pre-roll WHICH roster entity each slot lands on,
            # weighted per design.md §3.5, through the seeded dice channel.
            self._picks = {
                r: [self._weighted_pick(rng) for _ in range(self._n_attacks)]
                for r in range(1, self._rounds + 1)
            }

    def _weighted_pick(self, rng: "SeededRNG") -> "Entity":
        """Pick a roster entity with probability proportional to its weight, using
        the single seeded channel: roll over the total weight and walk the cumulative
        buckets.  Generalises ``char_target_prob`` to N friendly targets."""
        total = sum(w for _, w in self._roster)
        roll = rng.roll_one(total)              # 1..total
        cum = 0
        for ent, w in self._roster:
            cum += w
            if roll <= cum:
                return ent
        return self._roster[-1][0]              # numerical safety (unreachable)

    def decide(self, snapshot: GameState) -> list[Choice]:
        if snapshot.resources.get("action", 0) < 1:
            return []
        choices: list[Choice] = []
        if self._roster is None:
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
                    damage_type=self._damage_type,
                ))
        else:
            # Multi-entity: every pre-rolled slot lands on a real roster entity.
            for ent in self._picks.get(snapshot.round_number, []):
                choices.append(Choice(
                    action_type="attack",
                    cost="action" if not choices else "none",
                    target=ent,
                    weapon_stat="attack_bonus",
                    damage_type=self._damage_type,
                ))
        return choices


class BaselineEnemyPolicy:
    """A per-CR baseline enemy (decision #12's realised half — see enemy_stats.py).

    Each round it does ONE of two things, pre-rolled at ``on_combat_start`` so
    ``decide()`` stays dice-free (CLAUDE.md #7/#9):

      - an ATTACK-ROLL round → ``n_attacks`` melee swings vs the target's AC
        (``weapon_stat="attack_bonus"`` read off the enemy Entity, set to the per-CR
        baseline attack bonus); the per-CR damage budget is split across the swings
        as flat on-hit damage.
      - a SAVE-FORCING round (with probability ``save_round_prob``) → one effect that
        makes the target roll one of its SIX saving throws, chosen by weighted
        probability (``save_weights``), vs the enemy's per-CR save DC (``dc_stat`` on
        the Entity); full damage on a fail, half on a save (the per-CR AoE dice).

    This is the "test all our different saving throws, with varying probability, AND
    make attack rolls" model the user asked for: the engine rolls the d20s and saves.

    Damage is rolled from the chart's PER-CR DICE (``enemy_stats`` — multiattack dice
    per swing, AoE dice for a save), NOT a flat number, so a natural-20 attack DOUBLES
    the dice (enemy CRITS are modeled).  The dice already total the chart's Damage/Round
    across the 2-attack routine.

    TARGETING with summon survival (substrate #7 / 7a): the enemy focus-fires
    ``primary``; the instant ``primary`` winks out (a dead summon — ``destroyed``) the
    load shifts to ``fallback`` (the master).  So keeping the beast alive (warding bond
    / protection / aid) genuinely *tanks* for the master, and a slain beast's incoming
    damage is not wasted on a corpse — which is what makes the defender effects and the
    enemy's damage profile DPR-load-bearing.

    Keyed by the character ``level`` (CR == level; ``enemy_stats`` already applies the
    ÷1.5 party-size correction), so the per-level dice / to-hit / DC pair 1:1 with the
    AC/saves table.
    """

    def __init__(
        self,
        level: int,
        primary: "Entity",
        fallback: "Entity | None" = None,
        n_attacks: "int | None" = None,
        rounds_per_combat: int = 4,
        save_round_prob: float = SAVE_ROUND_PROB,
        save_weights: "dict[str, int] | None" = None,
        dc_stat: str = "enemy_save_dc",
        damage_type: "str | None" = None,
    ) -> None:
        self._level = level
        self._primary = primary
        self._fallback = fallback
        self._n_attacks = max(1, n_attacks if n_attacks is not None
                              else baseline_n_attacks(level))
        self._rounds = rounds_per_combat
        self._save_round_pct = int(round(save_round_prob * 100))
        self._save_weights = dict(save_weights or SAVE_TYPE_WEIGHTS)
        self._dc_stat = dc_stat
        self._damage_type = damage_type
        # Per-level damage DICE (the chart, ÷1.5, re-diced): one multiattack swing
        # (N dX + PB) and the AoE save effect (M dY).
        an, asides, abonus = baseline_attack_dice(level)
        self._attack_dice = (an, asides)
        self._attack_bonus = abonus
        sn, ssides, sbonus = baseline_aoe_dice(level)
        self._aoe_dice = (sn, ssides)
        self._aoe_bonus = sbonus
        # Pre-rolled per round: whether it is a save round, and (if so) which save.
        self._save_round: dict[int, bool] = {}
        self._save_stat: dict[int, str] = {}

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        self._save_round = {}
        self._save_stat = {}
        for r in range(1, self._rounds + 1):
            is_save = rng.roll_one(100) <= self._save_round_pct
            self._save_round[r] = is_save
            if is_save:
                self._save_stat[r] = self._weighted_save(rng)

    def _weighted_save(self, rng: "SeededRNG") -> str:
        """Pick a save type with probability proportional to its weight, through the
        single seeded channel (generalises ScriptedEnemyPolicy._weighted_pick)."""
        items = list(self._save_weights.items())
        total = sum(w for _, w in items)
        roll = rng.roll_one(total)              # 1..total
        cum = 0
        for stat, w in items:
            cum += w
            if roll <= cum:
                return stat
        return items[-1][0]                     # numerical safety (unreachable)

    def _current_target(self) -> "Entity | None":
        """Focus-fire the primary; shift to the fallback once the primary winks out."""
        if not self._primary.destroyed:
            return self._primary
        if self._fallback is not None and not self._fallback.destroyed:
            return self._fallback
        return None

    def decide(self, snapshot: GameState) -> list[Choice]:
        if snapshot.resources.get("action", 0) < 1:
            return []
        target = self._current_target()
        if target is None:
            return []
        r = snapshot.round_number
        if self._save_round.get(r, False):
            # Save-forcing round: one effect, the per-CR AoE dice, half on a save.
            return [Choice(
                action_type="save_spell",
                cost="action",
                target=target,
                save_stat=self._save_stat[r],
                dc_stat=self._dc_stat,
                damage_dice=self._aoe_dice,
                damage_bonus=self._aoe_bonus,
                on_save="half",
                damage_type=self._damage_type,
            )]
        # Attack-roll round: n swings, each rolling the per-CR multiattack dice (so a
        # natural 20 doubles the dice — enemy crits).
        choices: list[Choice] = []
        for i in range(self._n_attacks):
            choices.append(Choice(
                action_type="attack",
                cost="action" if i == 0 else "none",
                target=target,
                weapon_stat="attack_bonus",
                damage_dice=self._attack_dice,
                damage_bonus=self._attack_bonus,
                damage_type=self._damage_type,
            ))
        return choices
