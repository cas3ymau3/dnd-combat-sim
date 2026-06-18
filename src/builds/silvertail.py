"""
silvertail.py — The Blessed of Silvertail build: the project's THIRD archetype and
the vehicle for substrate #7 / 7a (controlled-ally SUMMONS).  A mounted Air-Genasi
Fighter/Beast-Master-Ranger/Trickery-Cleric whose CORNERSTONE is the PRIMAL
COMPANION — a giant snow fox that fights alongside it.

Source of truth for intent:
  - design/build-guides/32_silvertails_blessing.txt  (level-by-level notes; the
    L4 Primal Companion statblock at guide 32:326)

Scope (session 20, confirmed with the user up front): the MINIMAL 7a slice — a
SINGLE level row, char L4 (Fighter-1 / Ranger-3 Beast Master — where the primal
companion comes online), with the companion as the 7a summon.  It stands up the
engine primitive (create_entity / destroy_entity, the Choice.actor COMMANDED-action
override, a per-summon DPR column) on the lightest possible build.  Deferred to
later slices (each gated up front): the 7c effects ON the beast (warding bond
redirect / protection / aid-bless retarget — the beast as a buff/redirect target);
the higher rows; Spirit Guardians (7b emanation); invoke duplicity; mounted combat.

The 7a primitive this row forces
--------------------------------
  1. **Summon = an ACTOR** (design.md §1: own HP / AC / saves / economy), NOT the
     threshold-immortal dummy.  The Beast of the Land is a real ``Entity`` with 20
     HP and AC 16 (``make_primal_companion``).
  2. **Commanded on the controller's turn** (design.md §1: "controlled allies act
     on their controller's turn").  The beast has NO policy of its own; the
     master's ``SilvertailPolicy`` emits the beast's Beast's-Strike ``Choice`` with
     ``actor=beast`` (the COMMANDED-action override) on the master's turn.  The
     command COSTS the master's **Bonus Action** (2024 Primal Companion: "you can
     take a Bonus Action to command the beast to take an action") — the real
     action-economy contention 7a exists to model.
  3. **A per-summon DPR column** (design.md §8).  Because the beast's Beast's Strike
     is attributed to the beast (``actor=beast``), the per-(source,target) ledger
     reports the build's OWN column (``damage_by_source(char)`` — the master's
     shocking grasp) SEPARATELY from the summon column (``damage_by_source(beast)``
     — the Beast's Strike), with a party total beside them (user decision, s17).
  4. **create_entity / destroy_entity** (verbs 11/12).  The companion is summoned at
     DAY START via ``create_entity`` (it is a permanent companion — created once,
     persists the day; ``make_silvertail_runner`` assembles the roster with it), and
     ``destroy_entity`` / ``Entity.remove_effect`` is the teardown path (built; the
     permanent companion is not torn down mid-day — mid-combat summon lifecycle is
     deferred until a per-combat conjure build forces it).

Rules verified (per-feature ritual — BEFORE modeling)
-----------------------------------------------------
Beast of the Land, D&D 2024 (Roll20 / D&D Beyond, 2026-06-17; matches guide 32:326):
  - AC = 13 + WIS modifier  → 16 at WIS+3.
  - HP = 5 + 5 × ranger level → 20 at ranger-3.
  - Beast's Strike (melee): to-hit = YOUR SPELL ATTACK MODIFIER (PB + WIS = +5 at
    L4); Hit = 1d8 + 2 + WIS damage (bludgeoning/piercing/slashing, chosen on
    summon) → 1d8 + 5 at WIS+3.
  - CHARGE: if the beast moved ≥ 20 ft straight toward the target before the hit,
    +1d6 of the same type AND the target is knocked Prone (Large or smaller).  The
    guide's plan always charges in, so we bake the +1d6 into the commanded strike.
  - In combat the beast acts on YOUR turn; uncommanded it takes the Dodge action,
    and you spend a BONUS ACTION to command it to Beast's Strike.

VALIDATION FRAMING (same as the Scion — consistency/sanity, NOT number-matching):
  the guide's "decent but not max DPR" support character has no ground-truth DPR
  ladder; we validate that the commanded attack attributes to the BEAST, the summon
  column is reported separately from the build column, the Beast's-Strike math is
  exact under a deterministic RNG, and the create/destroy verbs behave.

DEFERRALS (flagged, not modeled this slice)
-------------------------------------------
  - **Charge PRONE → advantage** on the master's follow-up shocking grasp (the
    guide's "shocking grasp w/advantage since they're prone").  Prone-grants-
    advantage needs an on-hit-applies-status seam (the beast's hit installs prone on
    the enemy, read by the later shocking-grasp roll) — out of the minimal slice;
    the master's shocking grasp resolves at straight odds for now.  (ATTACK-TAXONOMY
    is adjacent — prone's melee-advantage/ranged-disadvantage split — left untouched.)
  - The enemy does not strike back (no defender-side effect in scope — protection /
    warding bond are the deferred 7c-on-summon slice), so the dummy is a passive
    target as in the pre-L13 Scion rows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..day_runner import DayRunner
from ..entity import Entity
from ..policy import Choice
from ..resources import ResourceEntry, ResourcePool
from ..summons import SummonSpec, create_entity

if TYPE_CHECKING:
    from ..rng import SeededRNG


# ---------------------------------------------------------------------------
# Per-level build data — char L4 only (the minimal 7a row)
# ---------------------------------------------------------------------------
# Master = Air Genasi Fighter-1 / Ranger-3 (Beast Master).  WIS 17 (+3), PB +2.
#   shocking_grasp — the master's go-to ranged/melee cantrip (Air Genasi "mingle
#     with wind" makes it WIS-based): a WIS spell attack, 1d8 lightning, no ability
#     modifier to damage (cantrips add none until Blessed Strikes at char L15).
#     Char L4 → 1d8 (cantrip scaling is char L5+).
#   enemy_ac / enemy_dex_save — live from monster_ac_and_saves_by_level.csv (cr 4),
#     the same source the Scion's rows use (AC 15, DEX save +2 at cr 4).
# Beast (primal companion, Beast of the Land) — see make_primal_companion.
LEVELS: dict[int, dict] = {
    4: {
        "char_ac": 19,                     # splint (17) + shield (2), guide 32 L4
        "char_hp": 40,                     # DPR-irrelevant (threshold model)
        "spell_attack_bonus": 5,           # PB 2 + WIS 3 (shocking grasp to-hit)
        "spell_save_dc": 13,               # 8 + PB 2 + WIS 3 (unused — no save spell)
        "wis_mod": 3,
        # shocking grasp: WIS spell attack, 1d8 lightning, no damage modifier.
        "shocking_grasp": {"dice": (1, 8), "bonus": 0,
                           "weapon_stat": "spell_attack_bonus",
                           "damage_type": "lightning", "is_spell": True},
        # Beast of the Land (ranger-3): AC 13+WIS, HP 5+5*ranger, Beast's Strike
        # 1d8+2+WIS, to-hit = spell attack modifier (+5), charge +1d6.
        "beast": {
            "ac": 16, "hp": 20,
            "attack_bonus": 5,             # = master's spell attack modifier (PB+WIS)
            "strike_dice": (1, 8),
            "strike_bonus": 5,             # 2 + WIS(3)
            "charge_dice": (1, 6),         # +1d6 on a ≥20ft straight charge (always)
            "strike_type": "bludgeoning",  # chosen on summon
            "save_bonus": 5,               # primal bond: +PB to all saves (PB 2 + base)
        },
        "enemy_ac": 15,
        "enemy_dex_save": 2,               # csv level 4
        # Loose all-hit upper bound (NOT a target): beast strike 1d8+1d6+5 ≈ 13 +
        # shocking grasp 1d8 ≈ 4.5 → ~18.  24 cushion.
        "ceiling_dpr": 24.0,
    },
}


# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------

def _make_resources(data: dict) -> ResourcePool:
    spec = data.get("resources", {})
    entries = {
        name: ResourceEntry(current=maximum, maximum=maximum, sr_restore=sr)
        for name, (maximum, sr) in spec.items()
    }
    return ResourcePool(entries)


def make_silvertail(level: int) -> Entity:
    """Build the Silvertail MASTER Entity (the controller) for the given level."""
    if level not in LEVELS:
        raise NotImplementedError(
            f"Silvertail level {level} not yet implemented (have {sorted(LEVELS)})."
        )
    data = LEVELS[level]
    return Entity(
        name=f"Silvertail-L{level}",
        hp=data["char_hp"],
        base_stats={
            "ac": data["char_ac"],
            "spell_attack_bonus": data["spell_attack_bonus"],
            "spell_save_dc": data["spell_save_dc"],
            # Fallback weapon profile (every emitted attack carries its own override).
            "damage_dice": data["shocking_grasp"]["dice"],
            "damage_bonus": 0,
        },
        resources=_make_resources(data),
    )


def make_primal_companion(level: int) -> Entity:
    """Build the PRIMAL COMPANION (Beast of the Land) — the 7a summon (an ACTOR with
    its own HP / AC / saves; design.md §1).  Commanded by the master, so it carries
    NO policy of its own (the master's policy emits its Beast's Strike).

    Its ``attack_bonus`` is the Beast's-Strike to-hit (= the master's spell attack
    modifier, 2024 RAW); its ``damage_dice``/``damage_bonus`` are the strike fallback
    (the commanded Choice also carries them explicitly).  AC + HP let the enemy
    target it once a 7c-on-summon slice (warding bond / protection) lands here.
    """
    b = LEVELS[level]["beast"]
    return Entity(
        name=f"PrimalCompanion-L{level}",
        hp=b["hp"],
        base_stats={
            "ac": b["ac"],
            "attack_bonus": b["attack_bonus"],       # Beast's Strike to-hit (+5)
            "damage_dice": b["strike_dice"],
            "damage_bonus": b["strike_bonus"],
            # Primal bond (+PB to all checks/saves) — a flat peer save line so a
            # future ally-effect / hostile save resolves against the beast.
            "str_save": b["save_bonus"], "dex_save": b["save_bonus"],
            "con_save": b["save_bonus"], "wis_save": b["save_bonus"],
        },
    )


def make_training_dummy(level: int) -> Entity:
    """The target: an effectively infinite-HP dummy carrying the enemy AC + DEX save
    (live from monster_ac_and_saves_by_level.csv at cr==level).  No policy → it never
    acts (a passive target; the enemy-strikes-back loop is the deferred 7c-on-summon
    slice)."""
    data = LEVELS[level]
    return Entity(
        name=f"Dummy-AC{data['enemy_ac']}",
        hp=10**9,
        base_stats={"ac": data["enemy_ac"], "dex_save": data["enemy_dex_save"]},
    )


# ---------------------------------------------------------------------------
# Daily-plan policy — the master COMMANDS the beast
# ---------------------------------------------------------------------------

class SilvertailPolicy:
    """Silvertail daily plan (char L4): the master fights alongside the COMMANDED
    primal companion (substrate #7 / 7a).

    Per-turn rotation (guide 32:353 — "run in, use our BA to command the beast to do
    a charge attack beast strike ..., then use our action to cast shocking grasp"):

      BONUS ACTION:  COMMAND the beast → Beast's Strike (charge).  Emitted FIRST so
                     it resolves before the master's action (the guide's order).  The
                     Choice carries ``actor=beast`` (the commanded-action override),
                     so the strike uses the BEAST's stats and is attributed to the
                     beast — the command's COST is the master's Bonus Action.
      ACTION:        shocking grasp (the master's own attack → the build column).

    ``decide`` stays a pure read (no dice, no mutation).  The beast reference is held
    at construction (it was summoned at day start via create_entity); the policy
    checks it is not destroyed before commanding.
    """

    def __init__(
        self,
        level: int,
        character: Entity,
        beast: Entity,
        target: Entity,
        rounds_per_combat: int = 4,
    ) -> None:
        if level not in LEVELS:
            raise NotImplementedError(
                f"SilvertailPolicy does not yet support level {level}."
            )
        self.level = level
        self._character = character
        self._beast = beast
        self._target = target
        self._rounds = rounds_per_combat
        data = LEVELS[level]
        self._shocking_grasp = data["shocking_grasp"]
        self._beast_data = data["beast"]

    def decide(self, snapshot) -> list[Choice]:
        res = snapshot.resources
        choices: list[Choice] = []

        # BONUS ACTION: command the beast to Beast's Strike (charge).  The command
        # costs the master's Bonus Action; the strike acts as the BEAST (actor
        # override) so it uses the beast's stats and lands in the beast's DPR column.
        # Skipped if the beast has winked out (destroy_entity / 0 HP) — a commanded
        # ally that no longer exists cannot be ordered.
        if (
            res.get("bonus_action", 0) >= 1
            and not self._beast.destroyed
        ):
            choices.append(self._beast_strike_choice())

        # ACTION: shocking grasp — the master's own attack (the build column).
        if res.get("action", 0) >= 1:
            sg = self._shocking_grasp
            choices.append(Choice(
                action_type="attack",
                cost="action",
                target=self._target,
                weapon_stat=sg["weapon_stat"],
                damage_dice=sg["dice"],
                damage_bonus=sg["bonus"],
                damage_type=sg.get("damage_type"),
                is_spell=sg.get("is_spell", False),
            ))

        return choices

    def _beast_strike_choice(self) -> Choice:
        """The COMMANDED Beast's Strike (charge): a melee attack made BY the beast
        (actor override) against the master's target.  Damage = 1d8 + 2 + WIS, plus
        the charge's +1d6 (the guide's plan always charges in) — the +1d6 rides as an
        extra damage die on the same hit.  Cost = the master's Bonus Action (the
        command)."""
        b = self._beast_data
        return Choice(
            action_type="attack",
            cost="bonus_action",                 # the master's command (Bonus Action)
            actor=self._beast,                   # COMMANDED: the beast acts (7a)
            target=self._target,
            weapon_stat="attack_bonus",          # beast's Beast's-Strike to-hit (+5)
            damage_dice=b["strike_dice"],        # 1d8
            damage_bonus=b["strike_bonus"],      # 2 + WIS(3) = 5
            extra_damage_dice=[b["charge_dice"]],  # +1d6 charge (same hit)
            damage_type=b["strike_type"],        # bludgeoning
        )


# ---------------------------------------------------------------------------
# Full day-runner assembly
# ---------------------------------------------------------------------------

def make_silvertail_runner(
    level: int,
    rng: "SeededRNG",
    rounds_per_combat: int = 4,
):
    """Assemble (DayRunner, master, beast, dummy) for the given level.

    The primal companion is SUMMONED AT DAY START, out of combat, via the
    ``create_entity`` verb (substrate #7 / 7a) — it is a PERMANENT companion, so it
    is created once and persists the whole day (it is in the roster every combat;
    mid-combat summon lifecycle is the deferred conjure case).  The beast has no
    policy of its own (it is COMMANDED by the master), so create_entity adds it to
    the entity roster but not the policy map.

    Read the two DPR columns SEPARATELY off the result (user decision, session 17):
      - build column   = ``damage_by_source(master.id)``  (the master's shocking grasp)
      - summon column  = ``damage_by_source(beast.id)``    (the Beast's Strike)
      - party total    = ``party_total([master.id, beast.id])``
    """
    char = make_silvertail(level)
    beast = make_primal_companion(level)
    dummy = make_training_dummy(level)

    entities: list[Entity] = [char, dummy]
    policies: dict[int, object] = {}

    # create_entity (verb 12): summon the controlled ally into the day's roster at
    # day start.  Commanded → no policy registered for the beast.
    create_entity(entities, policies, beast)

    policy = SilvertailPolicy(
        level=level, character=char, beast=beast, target=dummy,
        rounds_per_combat=rounds_per_combat,
    )
    policies[char.id] = policy

    runner = DayRunner(
        rng=rng,
        entities=entities,
        policies=policies,
        rounds_per_combat=rounds_per_combat,
    )
    return runner, char, beast, dummy
