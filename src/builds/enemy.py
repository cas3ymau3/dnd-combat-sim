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

from ..policy import Choice, ControlSpec, GameState
from .enemy_stats import (
    SOFT_FACTOR,
    band_bundled_control_rider,
    band_control_duration_mix,
    band_control_hard_frac,
    band_control_save_prob,
    band_control_weights,
    band_save_round_prob,
    band_save_weights,
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

    CONTROL CHANNEL (§6, ``control=True``; default OFF → no baseline drift).  A second,
    independent save-pressure axis for incapacitation — the mental-save mass the damaging
    census cannot see.  Turning it on makes the per-round action budget TERNARY (§4b):

      - a PURE-control round (prob ``control_save_prob``) DISPLACES a damage action — the
        enemy spends its whole turn on a control effect and deals no damage;
      - a save-for-damage round may ALSO impose a BUNDLED control save (rider, e.g. Mind
        Blast) — a second save on the same action, priced independently (the cross-axis
        double-save shows in both telemetry channels);
      - at band 0-4 the bundled mass exceeds the save-for-damage budget it rides on, so
        the OVERFLOW spills to an independent any-round draw (a bottom-band-only patch).

    The character rolls its OWN save (its build's bonus) vs the enemy DC; on a FAILURE it
    loses ``E[turns]`` of output (hard control → turn wasted; soft → output × soft_factor)
    over a closed-form expected duration (``save-ends`` → ``1/s`` on the char's own save →
    a good save both fails less AND recovers faster).  All of it is recorded through the
    §13 control telemetry channel — v1 is an OUTPUT FACTOR, not a status object (the
    character's turn is not actually skipped; that ongoing-save fidelity is the §10
    deferral).  The ``control_displacement="ride"`` toggle keeps the damage action and
    layers control on top (isolating the lost-turn effect).

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
        save_round_prob: "float | None" = None,
        save_weights: "dict[str, int] | None" = None,
        dc_stat: str = "enemy_save_dc",
        damage_type: "str | None" = None,
        control: bool = False,
        control_save_prob: "float | None" = None,
        control_weights: "dict[str, int] | None" = None,
        control_hard_frac: "float | None" = None,
        soft_factor: "float | None" = None,
        control_duration_mix: "tuple[float, float, float] | None" = None,
        control_displacement: str = "displace",
    ) -> None:
        self._level = level
        self._primary = primary
        self._fallback = fallback
        self._n_attacks = max(1, n_attacks if n_attacks is not None
                              else baseline_n_attacks(level))
        self._rounds = rounds_per_combat
        # Damaging-save knobs default to the band-EMPIRICAL values (enemy_model.md §4/§4b):
        # the per-action save-for-damage share and the CON/DEX-dominant save-type mix for
        # this level's CR band.  An explicit arg still overrides (toggles / tests).
        if save_round_prob is None:
            save_round_prob = band_save_round_prob(level)
        self._save_round_pct = int(round(save_round_prob * 100))
        self._save_weights = dict(save_weights) if save_weights is not None \
            else band_save_weights(level)
        self._dc_stat = dc_stat
        self._damage_type = damage_type
        # --- Control channel (§6) — the incapacitation-pressure axis, default OFF so
        # turning it on is the ONLY thing that changes behavior (no baseline drift).
        # When ON, the per-round action budget goes TERNARY (attack / save-dmg /
        # pure-control), pure-control DISPLACES a damage action (§4b), bundled control
        # rides as a second save on save-dmg rounds, and the low-CR overflow spills to
        # an independent any-round draw.  All control knobs default to the band-empirical
        # values; explicit args override (the §7 toggles).
        self._control = control
        self._control_displacement = control_displacement
        if control:
            cp = control_save_prob if control_save_prob is not None \
                else band_control_save_prob(level)
            self._control_prob_pct = int(round(cp * 100))
            self._control_weights = dict(control_weights) if control_weights is not None \
                else band_control_weights(level)
            self._control_hard_frac = control_hard_frac if control_hard_frac is not None \
                else band_control_hard_frac(level)
            # soft_factor is surfaced for the reporting layer (it scales the reduced-turn
            # output); resolution records only the AFFECTED turns, so it is not threaded
            # into the event.  Stored so tests / reporting can read it.
            self._soft_factor = soft_factor if soft_factor is not None else SOFT_FACTOR
            self._control_dur = control_duration_mix if control_duration_mix is not None \
                else band_control_duration_mix(level)
            rider_frac, overflow = band_bundled_control_rider(level)
            self._rider_frac_pct = int(round(rider_frac * 100))
            self._overflow_pct = int(round(overflow * 100))
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
        # Control pre-rolls (only populated when self._control): the pure-control round
        # flag + its save type, the bundled-rider flag + save type (on save rounds), and
        # the overflow independent-draw flag + save type (§4b low-CR patch / ride-on-top).
        self._pure_control: dict[int, bool] = {}
        self._control_stat: dict[int, str] = {}
        self._bundled_fire: dict[int, bool] = {}
        self._bundled_stat: dict[int, str] = {}
        self._overflow_fire: dict[int, bool] = {}
        self._overflow_stat: dict[int, str] = {}

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        self._save_round = {}
        self._save_stat = {}
        self._pure_control = {}
        self._control_stat = {}
        self._bundled_fire = {}
        self._bundled_stat = {}
        self._overflow_fire = {}
        self._overflow_stat = {}
        for r in range(1, self._rounds + 1):
            if not self._control:
                # OFF: the exact prior binary attack/save pre-roll (no drift).
                is_save = rng.roll_one(100) <= self._save_round_pct
                self._save_round[r] = is_save
                if is_save:
                    self._save_stat[r] = self._weighted_save(rng)
                continue

            # --- control ON: the §4b ternary action budget ---
            if self._control_displacement == "displace":
                # One draw over the whole budget: save-dmg | pure-control (displaces
                # attack) | attack.  Shares are of the action budget and sum to ≤100%.
                roll = rng.roll_one(100)
                if roll <= self._save_round_pct:
                    self._save_round[r] = True
                    self._save_stat[r] = self._weighted_save(rng)
                elif roll <= self._save_round_pct + self._control_prob_pct:
                    self._pure_control[r] = True
                    self._control_stat[r] = self._weighted_control(rng)
                # else: an attack round (both dicts default absent → False).
            else:
                # ride-on-top: keep the binary save/attack round AND layer pure control
                # on top (isolates the lost-turn effect without dropping damage — §7).
                is_save = rng.roll_one(100) <= self._save_round_pct
                self._save_round[r] = is_save
                if is_save:
                    self._save_stat[r] = self._weighted_save(rng)
                if rng.roll_one(100) <= self._control_prob_pct:
                    self._pure_control[r] = True
                    self._control_stat[r] = self._weighted_control(rng)

            # Bundled rider (§4b): a save-for-damage round's AoE ALSO imposes control on
            # a second (control) save, with per-save-round probability rider_frac.
            if self._save_round.get(r) and rng.roll_one(100) <= self._rider_frac_pct:
                self._bundled_fire[r] = True
                self._bundled_stat[r] = self._weighted_control(rng)

            # Low-CR overflow (§4b patch): where bundled control exceeds the save-dmg
            # budget it rides on, the excess spills to an independent any-round draw.
            if self._overflow_pct and rng.roll_one(100) <= self._overflow_pct:
                self._overflow_fire[r] = True
                self._overflow_stat[r] = self._weighted_control(rng)

    def _weighted_save(self, rng: "SeededRNG") -> str:
        """Pick a save type with probability proportional to its weight, through the
        single seeded channel (generalises ScriptedEnemyPolicy._weighted_pick)."""
        return self._weighted_pick_stat(self._save_weights, rng)

    def _weighted_control(self, rng: "SeededRNG") -> str:
        """Pick a CONTROL save type by the control weights (WIS-heavy — §6)."""
        return self._weighted_pick_stat(self._control_weights, rng)

    @staticmethod
    def _weighted_pick_stat(weights: dict[str, int], rng: "SeededRNG") -> str:
        items = list(weights.items())
        total = sum(w for _, w in items)
        # A single option (or a degenerate total < 2 the d-channel can't roll) → return
        # it directly; this also makes a single-type toggle (§7, e.g. all-WIS) work.
        if len(items) == 1 or total < 2:
            return items[0][0]
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

    def _control_choice(self, target: "Entity", save_stat: str, cost: str,
                        rounds_remaining: int) -> Choice:
        """Build one control_save Choice (§6).  The ControlSpec carries the qualitative
        shape (hard/soft split + duration mix + rounds_remaining) the policy read from
        the band table; resolution rolls the save and prices the failed-save cost."""
        short, save_ends, fixed = self._control_dur
        return Choice(
            action_type="control_save",
            cost=cost,
            target=target,
            save_stat=save_stat,
            dc_stat=self._dc_stat,
            control=ControlSpec(
                hard_frac=self._control_hard_frac,
                dur_short=short, dur_save_ends=save_ends, dur_fixed=fixed,
                rounds_remaining=rounds_remaining,
            ),
        )

    def decide(self, snapshot: GameState) -> list[Choice]:
        if snapshot.resources.get("action", 0) < 1:
            return []
        target = self._current_target()
        if target is None:
            return []
        r = snapshot.round_number
        rounds_remaining = max(1, self._rounds - r + 1)
        choices: list[Choice] = []

        # A pure-control round in DISPLACE mode replaces the damage action entirely
        # (§4b: "the monster controls instead of swinging" — deals no damage).
        displaced = (self._control and self._control_displacement == "displace"
                     and self._pure_control.get(r, False))

        if displaced:
            choices.append(self._control_choice(
                target, self._control_stat[r], "action", rounds_remaining))
        elif self._save_round.get(r, False):
            # Save-forcing round: one effect, the per-CR AoE dice, half on a save.
            choices.append(Choice(
                action_type="save_spell",
                cost="action",
                target=target,
                save_stat=self._save_stat[r],
                dc_stat=self._dc_stat,
                damage_dice=self._aoe_dice,
                damage_bonus=self._aoe_bonus,
                on_save="half",
                damage_type=self._damage_type,
            ))
            # Bundled control rider: a SECOND (control) save on the same action (§4b) —
            # cost "none" so it rides rather than costing a fresh action.
            if self._control and self._bundled_fire.get(r, False):
                choices.append(self._control_choice(
                    target, self._bundled_stat[r], "none", rounds_remaining))
        else:
            # Attack-roll round: n swings, each rolling the per-CR multiattack dice (so a
            # natural 20 doubles the dice — enemy crits).
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

        # Extra control saves layered on top (cost "none"): ride-on-top pure control
        # (the §7 non-displacing toggle) and the low-CR overflow independent draw.
        if self._control:
            if self._control_displacement == "ride" and self._pure_control.get(r, False):
                choices.append(self._control_choice(
                    target, self._control_stat[r], "none", rounds_remaining))
            if self._overflow_fire.get(r, False):
                choices.append(self._control_choice(
                    target, self._overflow_stat[r], "none", rounds_remaining))
        return choices
