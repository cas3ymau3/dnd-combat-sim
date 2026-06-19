"""
silvertail.py — The Blessed of Silvertail build: the project's THIRD archetype and
the vehicle for substrate #7 / 7a (controlled-ally SUMMONS) and 7c-ON-SUMMON (the
summon as a buff / redirect / protect target).  A mounted Air-Genasi
Fighter/Beast-Master-Ranger/Trickery-Cleric whose CORNERSTONE is the PRIMAL
COMPANION — a giant snow fox that fights alongside it.

Source of truth for intent:
  - design/build-guides/32_silvertails_blessing.txt  (level-by-level notes; the
    L4 Primal Companion statblock at guide 32:326; the 7c-on-summon kit + intent at
    guide 32:436-471)

Two level rows:
  - char L4 (Fighter-1 / Ranger-3 Beast Master) — the MINIMAL 7a SUMMON slice
    (session 20): the companion stands up the engine primitive (create_entity /
    destroy_entity, the Choice.actor COMMANDED-action override, a per-summon DPR
    column) on the lightest possible build.  The dummy is passive.
  - char L8 (Fighter-1 / Ranger-4 / Cleric-3 Trickery) — the 7c-ON-SUMMON slice
    (session 21): the level where the build's PROTECTIVE/SUPPORT kit for the beast
    comes online (Protection fighting style + Bless + Aid + Warding Bond), so the
    built 7c ally-effect machinery (session 19) lands ON the 7a beast.  The dummy
    STRIKES THE BEAST (typed) so warding bond (resistance + redirect to the master)
    and protection (disadvantage) do real work; bless raises the beast's outgoing
    DPR; aid bumps its HP max.  See BeastEffectPolicy.

Deferred to later slices (each gated up front): higher rows; Spirit Guardians
(7b emanation); invoke duplicity; mounted combat; the charge-PRONE→advantage /
shocking-grasp-denies-reactions control cluster (an on-hit-applies-status seam +
an opportunity-attack model — the build kites in/out + charges repeatedly, which
only works because shocking grasp suppresses the enemy's OA).

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

from ..builds.enemy import BaselineEnemyPolicy
from ..builds.enemy_stats import enemy_base_stats
from ..day_runner import BetweenCombatsContext, DayRunner
from ..entity import Entity
from ..modifiers import Modifier
from ..policy import Choice, InterceptResponse, RedirectSpec
from ..resources import ResourceEntry, ResourcePool
from ..summons import SummonSpec, create_entity

if TYPE_CHECKING:
    from ..rng import SeededRNG


# Beast of the Land — base ability saving-throw modifiers from the 2024 Beast Master
# statblock (per the user): STR/DEX/CON +2, INT -1, WIS +2, CHA +0.  The companion adds
# the MASTER's proficiency bonus to ANY save it makes (2024 Primal Companion: it uses
# your PB), so make_primal_companion stores base + char PB.
BEAST_BASE_SAVES: dict[str, int] = {
    "str_save": 2, "dex_save": 2, "con_save": 2,
    "int_save": -1, "wis_save": 2, "cha_save": 0,
}


def _char_pb(level: int) -> int:
    """The master's proficiency bonus at character *level* (2 / 3 / 4 / 5 / 6)."""
    return 2 + (level - 1) // 4


# ---------------------------------------------------------------------------
# Per-level build data — char L4 only (the minimal 7a row)
# ---------------------------------------------------------------------------
# Master = Air Genasi Fighter-1 / Ranger-3 (Beast Master).  WIS 17 (+3), PB +2.
#   shocking_grasp — the master's go-to ranged/melee cantrip (Air Genasi "mingle
#     with wind" makes it WIS-based): a WIS spell attack, 1d8 lightning, no ability
#     modifier to damage (cantrips add none until Blessed Strikes at char L15).
#     Char L4 → 1d8 (cantrip scaling is char L5+).
#   The enemy's full profile (AC / saves / attack bonus / save DC / per-level DICE) is
#     drawn from the definitive table (enemy_stats; monster_stats_by_level.csv), so the
#     rows carry no enemy numbers — only an ``enemy_attack`` marker (+ damage type) on
#     levels where the enemy strikes the beast.
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
            # saves: the full 2024 statblock (BEAST_BASE_SAVES + char PB) in the factory.
        },
        # No enemy_attack at L4: the dummy is a passive target (the 7a summon scenario).
        # Its AC / saves still come from the table (make_training_dummy) so the master's
        # shocking grasp resolves against a real AC.
        # Loose all-hit upper bound (NOT a target): beast strike 1d8+1d6+5 ≈ 13 +
        # shocking grasp 1d8 ≈ 4.5 → ~18.  24 cushion.
        "ceiling_dpr": 24.0,
    },
    # -----------------------------------------------------------------------
    # char L8 (Fighter-1 / Ranger-4 / Cleric-3 Trickery) — the 7c-ON-SUMMON row.
    # The level where the build's PROTECTIVE/SUPPORT kit for the beast comes
    # online: Protection fighting style (fighter-1), Bless (cleric-1), and Aid +
    # Warding Bond (cleric-3, lvl-2 spells).  This is the RAW access level for the
    # whole 7c-on-summon cluster (guide 32:436-471) — the same per-feature ACCESS
    # discipline that put Fire Shield at the Scion's L15, not the L4 summon row.
    #   PB +3, WIS 18 (+4) (mounted combatant L5 → WIS 18, guide 32:23,27).
    #   shocking grasp scales to 2d8 (char L5-10 cantrip step); no mod (Blessed
    #     Strikes is char L15).
    #   enemy: the full per-level profile (AC 16 / saves / +8 / DC 15 / 3d8+3 ×2 / 8d4
    #     AoE) is drawn from the definitive table (monster_stats_by_level.csv at L8).
    # -----------------------------------------------------------------------
    8: {
        "char_ac": 20,                     # splint(17) + cloak of protection(+1) + shield(2), guide 32:453
        "char_hp": 60,                     # DPR-irrelevant (threshold model)
        "spell_attack_bonus": 7,           # PB 3 + WIS 4 (shocking grasp + Beast's-Strike to-hit)
        "spell_save_dc": 15,               # 8 + PB 3 + WIS 4
        "wis_mod": 4,                      # WIS 18
        # Master saves — so a save-forcing enemy retargeted onto the master (after the
        # beast dies) resolves against a real line, not auto-fail.  Cleric/Ranger:
        # WIS + CHA proficient; modest physical saves.  (PB 3.)
        "char_saves": {"str_save": 0, "dex_save": 2, "con_save": 4,
                       "int_save": 1, "wis_save": 7, "cha_save": 6},
        # Spare leveled spell slots reserved for REVIVING the companion (2024 Primal
        # Companion: expend a slot, 1-minute revival → between-combats).  The buff
        # casts (bless/aid/warding bond) are modeled pre-cast/concentration and their
        # slot cost is abstracted; this is the revive economy the recast policy spends
        # against (the "recast or not" decision has a finite budget).  LR-restored.
        "resources": {"spell_slot": (3, 0)},
        "shocking_grasp": {"dice": (2, 8), "bonus": 0,
                           "weapon_stat": "spell_attack_bonus",
                           "damage_type": "lightning", "is_spell": True},
        # Beast of the Land (ranger-4): AC 13+WIS=17, HP 5+5*4=25, Beast's Strike
        # 1d8+2+WIS=1d8+6, to-hit = spell attack mod (+7), charge +1d6.
        "beast": {
            "ac": 17, "hp": 25,
            "attack_bonus": 7,
            "strike_dice": (1, 8),
            "strike_bonus": 6,             # 2 + WIS(4)
            "charge_dice": (1, 6),
            "strike_type": "bludgeoning",
            # saves: the full 2024 statblock (BEAST_BASE_SAVES + char PB) in the factory.
        },
        # Enemy strikes the BEAST (TYPED slashing) so the 7c-on-summon DEFENDER effects
        # (warding bond resistance+redirect, protection disadvantage) do real work.  A
        # MARKER only — the actual numbers (to-hit / save DC / per-level DICE) come from
        # the definitive table via BaselineEnemyPolicy; ``damage_type`` lets warding
        # bond's resistance bite before the redirect.
        "enemy_attack": {"damage_type": "slashing"},
        # Loose all-hit upper bound (NOT a target): beast 1d8+1d6+6 ≈ 14 + shocking
        # grasp 2d8 ≈ 9 → ~23, + Bless accuracy.  40 cushion.
        "ceiling_dpr": 40.0,
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
    base_stats = {
        "ac": data["char_ac"],
        "spell_attack_bonus": data["spell_attack_bonus"],
        "spell_save_dc": data["spell_save_dc"],
        # Fallback weapon profile (every emitted attack carries its own override).
        "damage_dice": data["shocking_grasp"]["dice"],
        "damage_bonus": 0,
    }
    base_stats.update(data.get("char_saves", {}))   # master saves (L8+: for retargeting)
    return Entity(
        name=f"Silvertail-L{level}",
        hp=data["char_hp"],
        base_stats=base_stats,
        resources=_make_resources(data),
    )


def make_primal_companion(level: int, mortal: bool = False) -> Entity:
    """Build the PRIMAL COMPANION (Beast of the Land) — the 7a summon (an ACTOR with
    its own HP / AC / saves; design.md §1).  Commanded by the master, so it carries
    NO policy of its own (the master's policy emits its Beast's Strike).

    Its ``attack_bonus`` is the Beast's-Strike to-hit (= the master's spell attack
    modifier, 2024 RAW); its ``damage_dice``/``damage_bonus`` are the strike fallback
    (the commanded Choice also carries them explicitly).  AC + HP let the enemy
    target it once a 7c-on-summon slice (warding bond / protection) lands here.

    ``mortal`` arms summon survival (substrate #7 / 7a — session 22): a mortal
    companion WINKS OUT at 0 HP (``dies_at_zero_hp``), so under real enemy fire it can
    die mid-combat and stop contributing — which is what makes aid / warding bond /
    protection DPR-relevant (more rounds alive = more Beast's-Strike DPR).  Default
    False keeps the threshold-immortal beast the session-21 mechanism tests use.
    """
    b = LEVELS[level]["beast"]
    # Beast of the Land — the full 2024 Beast Master statblock saves.  Base ability-save
    # modifiers (per the user): STR/DEX/CON +2, INT -1, WIS +2, CHA +0.  The companion
    # adds the MASTER's proficiency bonus to ANY save it makes (2024 Primal Companion —
    # it uses your PB), so the effective save = base + char PB.
    pb = _char_pb(level)
    saves = {stat: base + pb for stat, base in BEAST_BASE_SAVES.items()}
    beast = Entity(
        name=f"PrimalCompanion-L{level}",
        hp=b["hp"],
        base_stats={
            "ac": b["ac"],
            "attack_bonus": b["attack_bonus"],       # Beast's Strike to-hit (+5)
            "damage_dice": b["strike_dice"],
            "damage_bonus": b["strike_bonus"],
            **saves,
        },
    )
    beast.dies_at_zero_hp = mortal
    return beast


def make_training_dummy(level: int) -> Entity:
    """The target: an effectively infinite-HP dummy carrying the enemy's full profile —
    AC + the six saves + attack bonus + save DC — drawn from the definitive per-level
    table (``enemy_stats.enemy_base_stats``; ``reference/data/monster_stats_by_level.csv``).

    Through the L4 summon row it has no policy and never acts (a passive target).  On a
    row that carries an ``enemy_attack`` marker (L8 — the 7c-on-summon slice) a
    ``BaselineEnemyPolicy`` drives it to strike the BEAST with the table's per-level
    DICE — the enemy-strikes-back loop that makes the beast's defender-side effects
    (warding bond / protection) do real work."""
    stats = enemy_base_stats(level)
    return Entity(
        name=f"Dummy-AC{stats['ac']}",
        hp=10**9,
        base_stats=stats,
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
# 7c-ON-SUMMON: the summon (beast) as a buff / redirect / protect TARGET
# ---------------------------------------------------------------------------

class BeastEffectPolicy:
    """The master's protective/support kit applied TO the commanded primal companion
    (substrate #7 / 7c-on-summon — connecting the 7a summon to the built 7c
    ally-effect machinery).  The beast is a real ``Entity``, so the same `cast_effect
    target=ally` payloads and `on_incoming_hit` riders that session 19 built for a
    synthetic ally land on it directly.

    This is a DEFENDER-side policy registered for the BEAST so the intercept seam
    (``Scheduler._make_intercept_decider``) consults it when the enemy hits the beast.
    The beast is still COMMANDED by the master (the master's ``SilvertailPolicy``
    emits its Beast's-Strike via ``Choice.actor``); this policy's ``decide`` returns
    ``[]``, so the beast still takes no turn of its own — it just gains a reaction
    response and pre-cast persistent buffs.

    Per the session-19 convention, the protector/caster's reaction economy is
    ABSTRACTED into the beast's self-gated response (the master's Protection reaction /
    Warding Bond is folded in, not separately ticked).

      - ``warding_bond`` → the beast gains +1 AC, +1 saves, and RESISTANCE TO ALL
        damage (substrate #4, the ``_all`` key), and each time it takes damage the
        MASTER takes the same (post-resistance) amount (RedirectSpec → master).  2024:
        "+1 bonus to AC and saving throws, resistance to all damage ... each time it
        takes damage, you take the same amount" (web-verified 2026-06-18).
      - ``protection`` → impose DISADVANTAGE on attacks against the beast (the master
        interposes a shield; guide 32:227 = 2024 Protection: "interpose shield to
        impose disadvantage on the triggering attack and all other attacks").
      - ``bless`` → +1d4 to the beast's attack rolls and saves (raises the beast's
        OUTGOING DPR), concentration on the master.  A `cast_effect target=ally`
        rolled-modifier payload (substrate #1), retargeted onto the beast.
      - ``aid`` → +5 to the beast's HP maximum and current HP (2nd-level Aid; the
        guide upcasts to +10 at a later row with 3rd-level slots).  DPR-INERT in the
        threshold HP model (HP never gates turns) — installed as an assertion that the
        target=ally HP buff lands on the beast.

    RAW ACCESS (per-feature ritual): Protection at fighter-1, Bless at cleric-1, Aid +
    Warding Bond at cleric-3 → all online at char L8 (guide 32:436-471).
    """

    _AID_HP = 5                                  # 2nd-level Aid (+5 HP max & current)
    _SAVES = ("str_save", "dex_save", "con_save", "wis_save")

    def __init__(self, effect: str, beast: Entity, master: Entity) -> None:
        if effect not in ("warding_bond", "protection", "bless", "aid"):
            raise ValueError(f"unknown beast-effect {effect!r}")
        self._effect = effect
        self._beast = beast
        self._master = master
        self._aid_applied = False

    def install(self) -> None:
        """Install the persistent (non-intercept) part of the effect on the BEAST.

        Idempotent: it ``remove_effect``s its own source before re-adding, so it can
        be called both once at setup AND again each combat (``on_combat_start``)
        without stacking — necessary because ``DayRunner`` sweeps combat-clock buffs
        at every combat boundary (the Scion's Fire Shield / War Angel's Bless re-cast
        the same way).  Aid (a day-clock +HP, never swept) is applied exactly once.
        """
        if self._effect == "warding_bond":
            # +1 AC / +1 saves + resistance to ALL damage (the _all key).  Noted as a
            # combat buff (add_damage_response notes it) so the boundary sweep tears
            # the whole bundle down; re-added here each combat.
            self._beast.remove_effect("warding_bond")
            self._beast.add_modifier(Modifier(stat="ac", value=1, source="warding_bond"))
            for s in self._SAVES:
                self._beast.add_modifier(Modifier(stat=s, value=1, source="warding_bond"))
            self._beast.add_damage_response("warding_bond", {"_all": "resistance"})
        elif self._effect == "bless":
            # +1d4 (rolled) to attack rolls and saves; concentration on the master.
            self._beast.remove_effect("bless")
            self._beast.add_modifier(
                Modifier(stat="attack_bonus", value=0, source="bless", dice=(1, 4)))
            for s in self._SAVES:
                self._beast.add_modifier(Modifier(stat=s, value=0, source="bless", dice=(1, 4)))
            self._beast.note_combat_buff("bless")     # so the modifiers are swept too
            self._master.concentration = "bless"
        elif self._effect == "aid" and not self._aid_applied:
            # +5 HP maximum and current (DPR-inert under the threshold model); a
            # day-clock buff, applied once (max_hp is not swept).
            self._beast.max_hp += self._AID_HP
            self._beast.hp += self._AID_HP
            self._aid_applied = True

    def on_combat_start(self, combat_index: int, rng) -> None:
        """Re-apply the combat-clock payload each combat (it was swept at the boundary
        by ``DayRunner``), mirroring Fire Shield / Bless re-casting per encounter."""
        self.install()

    def on_incoming_hit(self, ctx) -> "InterceptResponse | None":
        if self._effect == "warding_bond":
            # Each time the warded beast takes damage, the master takes the same
            # (post-resistance) amount.
            return InterceptResponse(
                redirect=RedirectSpec(target=self._master, fraction=1.0))
        if self._effect == "protection":
            return InterceptResponse(impose_disadvantage=True)
        return None                              # bless / aid carry no intercept rider

    def decide(self, snapshot) -> list[Choice]:
        return []                                # passive — the master COMMANDS the beast


# ---------------------------------------------------------------------------
# Full day-runner assembly
# ---------------------------------------------------------------------------

def make_recast_hook(master: Entity, beast: Entity, slot_resource: str = "spell_slot"):
    """The silvertail's per-character RECAST policy (substrate #7 / 7a summon
    survival — "policies are code"): a BETWEEN-COMBATS decision to revive the
    companion after it died.

    2024 Primal Companion revival (web-verified 2026-06-19): if the beast has died
    within the last hour, the master takes a Magic action, touches it, and expends a
    spell slot; it returns to life after **1 minute** with full HP.  One minute is
    ~10 rounds, so revival NEVER lands inside a 4-round combat — it is inherently a
    between-combats action (the dead beast contributes nothing for the rest of the
    combat it died in; the survivability payoff).  The decision: revive iff the beast
    is dead, a revive slot remains, and a LATER combat remains to use it in.  Greedy
    with a finite slot budget — the simplest "recast or not" policy; it can grow.
    """
    def hook(ctx: BetweenCombatsContext) -> None:
        if (
            beast.destroyed
            and ctx.after_combat_num < 4                  # a later combat to use it in
            and master.resources.consume(slot_resource)   # spend a spare slot
        ):
            beast.destroyed = False
            beast.hp = beast.max_hp                        # revived with full HP (RAW)
    return hook


def make_silvertail_runner(
    level: int,
    rng: "SeededRNG",
    rounds_per_combat: int = 4,
    beast_effect: "str | None" = None,
    mortal_beast: bool = False,
    recast: bool = False,
):
    """Assemble (DayRunner, master, beast, dummy) for the given level.

    The primal companion is SUMMONED AT DAY START, out of combat, via the
    ``create_entity`` verb (substrate #7 / 7a) — it is a PERMANENT companion, so it
    is created once and persists the whole day (it is in the roster every combat;
    mid-combat summon lifecycle is the deferred conjure case).  The beast has no
    policy of its own (it is COMMANDED by the master); ``create_entity`` adds it to
    the entity roster, and — when a ``beast_effect`` is requested — a passive
    ``BeastEffectPolicy`` is registered for it so the intercept seam can consult its
    defender-side rider (the beast still takes no turn of its own).

    Parameters that select the scenario
    ------------------------------------
    beast_effect:
        The 7c-on-summon effect ON the beast (session 21): None (baseline — beast
        takes full), "warding_bond", "protection", "bless", "aid".
    mortal_beast:
        If True the companion WINKS OUT at 0 HP (summon survival, session 22), so it
        can die mid-combat and stop contributing.  Default False = the threshold-
        immortal beast the session-21 mechanism tests isolate effects against.  When the
        row has an ``enemy_attack`` marker the enemy is driven by ``BaselineEnemyPolicy``
        off the definitive per-level table (``enemy_stats``): per-level attack bonus /
        save DC / DICE, mixing attack rolls and save-forcing across the target's saves,
        and RETARGETING onto the master when the beast dies.
    recast:
        If True, register the between-combats RECAST policy (``make_recast_hook``) so
        a dead beast is revived (spending a spare slot) before the next combat.

    Read the DPR columns SEPARATELY off the result (user decision, session 17):
      - build column   = ``damage_by_source(master.id)``  (the master's shocking grasp)
      - summon column  = ``damage_by_source(beast.id)``    (the Beast's Strike — also the
        beast's LIFETIME DPR, the survival validation's headline: aid / warding bond /
        protection / recast RAISE it by keeping the beast alive for more strikes)
      - party total    = ``party_total([master.id, beast.id])``
    The 7c-on-summon effects are read off the INCOMING ledger instead:
      - ``damage_source_to(dummy.id, beast.id)`` — what the enemy deals to the beast
        (protection / warding-bond resistance cut it below baseline);
      - ``damage_source_to(dummy.id, master.id)`` — warding bond's redirected share
        (and, under ``mortal_beast`` + retargeting, the hits the master eats after the
        beast falls).
    """
    char = make_silvertail(level)
    beast = make_primal_companion(level, mortal=mortal_beast)
    dummy = make_training_dummy(level)

    entities: list[Entity] = [char, dummy]
    policies: dict[int, object] = {}

    # create_entity (verb 12): summon the controlled ally into the day's roster at
    # day start.  Commanded → no INDEPENDENT policy; a passive BeastEffectPolicy is
    # attached below only to carry the requested 7c defender rider / pre-cast buff.
    create_entity(entities, policies, beast)

    policies[char.id] = SilvertailPolicy(
        level=level, character=char, beast=beast, target=dummy,
        rounds_per_combat=rounds_per_combat,
    )

    # 7c-on-summon: install the requested effect ON the beast (summon as buff /
    # redirect / protect target).  install() pre-casts the persistent payload; the
    # policy carries the on_incoming_hit rider.
    if beast_effect is not None:
        bep = BeastEffectPolicy(effect=beast_effect, beast=beast, master=char)
        bep.install()
        policies[beast.id] = bep

    # Enemy strikes back (L8): the dummy attacks the BEAST so the beast's defender
    # effects modulate real incoming damage.  The enemy is driven entirely by the
    # definitive per-level table (decision #12's realised half; enemy_stats.py): the
    # dummy Entity already carries the table's AC / saves / attack bonus / save DC
    # (make_training_dummy), and BaselineEnemyPolicy supplies the per-level attack /
    # AoE DICE + the attack-vs-save mix.  It focus-fires the beast, shifting to the
    # master when the beast winks out.
    ea = LEVELS[level].get("enemy_attack")
    if ea:
        policies[dummy.id] = BaselineEnemyPolicy(
            level=level,
            primary=beast,
            fallback=char,
            rounds_per_combat=rounds_per_combat,
            damage_type=ea.get("damage_type"),
        )

    runner = DayRunner(
        rng=rng,
        entities=entities,
        policies=policies,
        rounds_per_combat=rounds_per_combat,
        between_combats=make_recast_hook(char, beast) if recast else None,
    )
    return runner, char, beast, dummy
