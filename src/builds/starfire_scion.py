"""
starfire_scion.py — The Starfire Scion build: per-level stat blocks + daily-plan
policy.  The project's SECOND archetype — a WIS-based spellfire "blaster" gish
(Monk-08 Sun-Soul / Druid-12 Circle of Stars), chosen to force the save-FOR-damage
and dice-scaling axes the attack-roll War Angel never exercised.

Source of truth for intent:
  - design/build-guides/41_spellfire_scion.txt  (level-by-level notes + DPR
    *ceilings* — see the validation-framing note below)

This module covers L1, L4, L5 (the slice wired the first build session): the
melee baseline (L1), the level Starry Form + Star Map come online (L4), and the
first "interesting" level where the blaster identity converges (L5: Spellfire
Adept → cantrip-scaled 2d8 Sacred Flame).  L2/L3 are intentionally SKIPPED — they
add no DPR-relevant mechanics (Druid spellcasting / wild-shape utility) — and are
easy to backfill if a continuous ladder is ever wanted.  L6+ extend both LEVELS
and the policy as the ladder is climbed.

The build (see PROGRESS.md "Second archetype — STARFIRE SCION")
---------------------------------------------------------------
Point-buy DEX 16 (+3), CON 14 (+2), WIS 17 (+3 → 18 at L5), STR 8.  WIS is the
spell stat (Sacred Flame / Guiding Bolt / Starry-Form Archer); DEX is the
martial-arts melee stat (quarterstaff / unarmed).  It forces:

  1. **Save-FOR-DAMAGE** — Sacred Flame (DEX save-NEGATES) is the recurring
     bonus-action spell.  Its dice are pulled FROM DATA via
     ``interpret_save_spell(sacred_flame, {"character_level": L})`` — not a literal
     tuple — so the cantrip scaling (1d8 → 2d8 at L5) is data-driven (primitive #2).
  2. **Multiple attack PROFILES on one body** — quarterstaff (1d8+DEX), unarmed
     (1d6+DEX), Archer-form spell attack (1d8+WIS), Guiding Bolt (4d6).  The engine
     read a single ``actor.stat("damage_dice")`` for every attack (fine for the
     one-weapon War Angel); this build forced **per-attack damage override**
     (primitive #4 — a ``damage_dice``/``damage_bonus`` on the ``Choice``, threaded
     ``Choice → AttackRollEvent → DamageEvent``, defaulting to the entity stat).

VALIDATION FRAMING (important — differs from War Angel)
-------------------------------------------------------
The guide's per-level DPR numbers are **"all-hit CEILINGS," not targets**: they
assume every attack hits and the enemy always fails its save (no AC, no misses, no
successful saves).  This build has **no ground-truth DPR ladder** — producing
honest DPR for it is itself a goal of the model.  So validation is **consistency +
sanity** (like War Angel L16), NOT number-matching: per-hit / per-save damage math
exact; DPR grows monotonically up the ladder; computed DPR is a *plausible
fraction* of the ceiling given that level's hit / save-fail rates.  The
``ceiling_dpr`` field below is a loose UPPER BOUND, never a target.

Enemy model: the enemy save bonus + AC are live inputs sourced per character level
from ``reference/data/monster_ac_and_saves_by_level.csv`` (level == cr row; ``ac``
+ ``dex.save.mod``).  The enemy does NOT yet strike back (no incoming-damage loop
at these levels — exactly like War Angel before L13), so concentration is never
checked here and the Starry-Form/Flame-Blade concentration axis stays deferred.

What IS modeled here beyond the per-attack profiles
---------------------------------------------------
  3. **Fueled Spellfire** (Spellfire Adept, L5; engine primitive #5) — a
     CASTER-side POST-DAMAGE decision point: ×1/turn, when a SPELL deals RADIANT
     damage, expend up to 2 Hit Dice (d8) and add them to that damage roll.  Built
     as a general radiant rider hooked on the DamageEvent (the chokepoint BOTH
     the attack-roll path — Guiding Bolt — and the save-for-damage path — Sacred
     Flame — funnel through), so future radiant spells (Sunbeam, Fount of
     Moonlight) get it for free.  See ``StarfireScionPolicy.on_deal_damage`` and
     ``Scheduler._make_deal_damage_decider``.  Hit dice are a scarce per-day pool
     (5 at L5); the rider dice are NOT crit-doubled (a fixed expenditure).

What is NOT modeled here (deferred — see PROGRESS "Open threads")
----------------------------------------------------------------
  - **Searing Arc Strike** (L10 upcast Burning Hands, save-for-half): the
    primitive (#3) is built and data exists; the policy wiring waits for L10.
  - **Starry Form: Chalice** (extra healing — DPR-irrelevant) and **Dragon** (a
    concentration-save floor — moot without the incoming-damage loop).
  - **Flame Blade** (concentration L2 spell — the melee-rotation alternative),
    **Stunning Strike**, **Guiding Bolt's advantage grant → allies** (modeled as a
    plain 4d6 attack), multi-enemy AoE / spatial, wild-shape beast forms, healing.

Ability-online timeline (abridged; full version in git history / the guide)
---------------------------------------------------------------------------
  L1  Monk-1.  Unarmored defense.  Martial arts (1d6): quarterstaff action + BA
        unarmed strike.  Spellfire Spark → Sacred Flame (1d8), castable as a BA
        xPB/LR.  [Melee bread-and-butter; first save-for-damage delivery.]
  L4  +Druid-3 (Stars).  Star Map → free Guiding Bolt xWIS/LR (ATTACK roll, 4d6).
        Starry Form (Archer = BA ranged spell attack 1d8+WIS).  L2 spells.
  L5  +Druid-4.  Spellfire Adept: +1 WIS (→18); Fueled Spellfire (deferred);
        cantrip scaling → Sacred Flame 2d8.  [Blaster identity online.]
  L9  Extra Attack; martial arts 1d8.    L10 Searing Arc Strike (upcast Burning
        Hands, BA).    L12 WIS 20.    L17 Sacred Flame 4d8.    (see the guide)

Engine-capacity build order (see PROGRESS):
  1. [DONE] save-FOR-damage resolution path (negates + for-half).
  2. [DONE] cantrip / level_reference dice scaling (Sacred Flame by char level).
  3. [DONE] upcast `increment` scaling (Searing Arc Strike) — data ready, policy
     wiring waits for L10.
  4. [DONE] per-attack damage override (the multi-weapon gish primitive) —
     Choice.damage_dice/damage_bonus → AttackRollEvent → DamageEvent.
  5. [DONE, this session] Fueled Spellfire — a caster-side post-damage decision
     point (Policy.on_deal_damage → DamageRiderResponse), threaded through
     resolve_damage as `rider_decider`; gated on "spell radiant damage" via
     damage_type + is_spell threaded Choice → events → DamageEvent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..content import interpret_save_spell, load_abilities
from ..day_runner import DayRunner
from ..entity import Entity
from ..policy import Choice, DamageRiderResponse, DealDamageContext, GameState
from ..resources import ResourceEntry, ResourcePool

if TYPE_CHECKING:
    from ..rng import SeededRNG


# Declarative ability layer: Sacred Flame's dice are read FROM DATA
# (content/abilities/starfire_scion.yaml) and resolved against the character level
# by interpret_save_spell — NOT a literal tuple on the LEVELS row.  This is the
# whole reason the build was chosen (the data-driven save-spell scaling axis).
_ABILITIES = load_abilities()
SACRED_FLAME = _ABILITIES["sacred_flame"]   # DEX save-negates, cantrip-scaling dice


# ---------------------------------------------------------------------------
# Per-level build data
# ---------------------------------------------------------------------------
# Each entry carries:
#   attack_bonus        — DEX-based martial-arts attack bonus (quarterstaff/unarmed)
#   spell_attack_bonus  — WIS-based spell-attack bonus (Archer / Guiding Bolt)
#   spell_save_dc       — our DC for Sacred Flame (8 + PB + WIS)
#   <weapon profiles>   — per-attack (dice, bonus, weapon_stat) for the override
#   enemy_ac/enemy_dex_save — live from monster_ac_and_saves_by_level.csv (cr==level)
#   ceiling_dpr         — guide all-hit UPPER BOUND (NOT a target; see docstring)
#   resources           — name → (maximum, sr_restore) for the ResourcePool
#
# Sacred Flame's dice are deliberately ABSENT here — they come from the YAML via
# interpret_save_spell(character_level), so the cantrip scaling lives in data.
LEVELS: dict[int, dict] = {
    1: {
        # Monk-1, PB 2, WIS 17 (+3), DEX 16 (+3).
        "attack_bonus": 5,                 # PB 2 + DEX 3 (martial-arts melee)
        "spell_attack_bonus": 5,           # PB 2 + WIS 3 (unused at L1 — no WIS attacks)
        "spell_save_dc": 13,               # 8 + PB 2 + WIS 3
        "char_ac": 16,                     # 10 + DEX 3 + WIS 3 (unarmored defense)
        "char_hp": 8,                      # DPR-irrelevant (threshold model)
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 6), "bonus": 3, "weapon_stat": "attack_bonus"},
        "starry_form": False,
        "guiding_bolt": False,
        "resources": {
            "spellfire_spark": (2, 0),     # Sacred Flame as a BA, x PB / LR (LR-only)
        },
        "enemy_ac": 13,
        "enemy_dex_save": 1,               # csv level 1
        "ceiling_dpr": 14.0,               # loose: quarterstaff 7.5 + unarmed 6.5
    },
    4: {
        # Monk-1/Druid-3 (Stars), PB 2, WIS 17 (+3).  Star Map (free Guiding Bolt
        # xWIS/LR) + Starry Form (Archer) come online — both delivered via the
        # per-attack damage override (primitive #4).
        "attack_bonus": 5,                 # PB 2 + DEX 3
        "spell_attack_bonus": 5,           # PB 2 + WIS 3
        "spell_save_dc": 13,               # 8 + PB 2 + WIS 3
        "char_ac": 16,
        "char_hp": 22,
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 6), "bonus": 3, "weapon_stat": "attack_bonus"},
        # Archer form: BA ranged spell attack 1d8 + WIS, WIS-based to-hit.  It
        # deals RADIANT damage, but it is a starry-form FEATURE, not a spell — so
        # is_spell stays False and Fueled Spellfire (L5+) does NOT fuel it.
        "archer":       {"dice": (1, 8), "bonus": 3, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant"},
        # Guiding Bolt: 4d6 radiant SPELL, ranged spell attack, no damage modifier.
        # radiant + is_spell → a Fueled-Spellfire target at L5+.
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": True,
        "resources": {
            "spellfire_spark": (2, 0),     # x PB / LR
            "guiding_bolt_free": (3, 0),   # Star Map: free Guiding Bolt x WIS / LR
            "wild_shape": (2, 1),          # 2 / LR, +1 on SR → Starry Form ~3 of 4 combats
        },
        "enemy_ac": 15,
        "enemy_dex_save": 2,               # csv level 4
        "ceiling_dpr": 21.5,               # loose: Guiding Bolt 14 + Archer 7.5
    },
    5: {
        # Monk-1/Druid-4 (Stars), PB 3, WIS 18 (+4, Spellfire Adept).  Cantrip
        # scaling lifts Sacred Flame to 2d8 (resolved from data).  Fueled Spellfire
        # unlocks here (the hit_dice pool below + on_deal_damage) — primitive #5.
        "attack_bonus": 6,                 # PB 3 + DEX 3
        "spell_attack_bonus": 7,           # PB 3 + WIS 4
        "spell_save_dc": 15,               # 8 + PB 3 + WIS 4
        "char_ac": 17,                     # 10 + DEX 3 + WIS 4
        "char_hp": 30,
        "quarterstaff": {"dice": (1, 8), "bonus": 3, "weapon_stat": "attack_bonus"},
        "unarmed":      {"dice": (1, 6), "bonus": 3, "weapon_stat": "attack_bonus"},
        "archer":       {"dice": (1, 8), "bonus": 4, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant"},  # radiant FEATURE (not a spell)
        "guiding_bolt": {"dice": (4, 6), "bonus": 0, "weapon_stat": "spell_attack_bonus",
                          "damage_type": "radiant", "is_spell": True},
        "starry_form": True,
        "resources": {
            "spellfire_spark": (3, 0),     # x PB / LR (PB 3 now)
            "guiding_bolt_free": (4, 0),   # x WIS / LR (WIS 4 now)
            "wild_shape": (2, 1),
            # Fueled Spellfire (Spellfire Adept, L5): the per-day Hit-Dice pool
            # (character level d8, all 5 spent on radiant spell damage; no SR
            # restore — a long rest at day start refills).  Its PRESENCE here is
            # what turns Fueled Spellfire on in the policy (data-driven gate).
            "hit_dice": (5, 0),
        },
        "enemy_ac": 15,
        "enemy_dex_save": 2,               # csv level 5
        "ceiling_dpr": 23.0,               # loose: Guiding Bolt 14 + Sacred Flame 2d8 9
    },
}


# ---------------------------------------------------------------------------
# Entity factories
# ---------------------------------------------------------------------------

def _make_resources(data: dict) -> ResourcePool:
    """Build the ResourcePool from a level's "resources" spec (may be absent)."""
    spec = data.get("resources", {})
    entries = {
        name: ResourceEntry(current=maximum, maximum=maximum, sr_restore=sr)
        for name, (maximum, sr) in spec.items()
    }
    return ResourcePool(entries)


def make_starfire_scion(level: int) -> Entity:
    """Build the Starfire Scion Entity for the given level (1, 4, 5 for now)."""
    if level not in LEVELS:
        raise NotImplementedError(
            f"Starfire Scion level {level} not yet implemented (have {sorted(LEVELS)})."
        )
    data = LEVELS[level]
    return Entity(
        name=f"StarfireScion-L{level}",
        hp=data["char_hp"],
        base_stats={
            "attack_bonus": data["attack_bonus"],          # DEX martial-arts melee
            "spell_attack_bonus": data["spell_attack_bonus"],  # WIS spell attacks
            "spell_save_dc": data["spell_save_dc"],        # Sacred Flame DC
            # Fallback weapon profile — every attack the policy emits carries its
            # own damage override, so these are only read if a future Choice omits
            # one.  Default to the quarterstaff so the fallback is sensible.
            "damage_dice": data["quarterstaff"]["dice"],
            "damage_bonus": data["quarterstaff"]["bonus"],
        },
        resources=_make_resources(data),
    )


def make_training_dummy(level: int) -> Entity:
    """Build the target for the given level.

    HP is effectively infinite (threshold model).  The dummy carries the enemy AC
    (for attack rolls) and the DEX save bonus (for Sacred Flame's save) — both
    live from monster_ac_and_saves_by_level.csv.  It has no policy and never acts
    (the enemy does not strike back at these levels).
    """
    data = LEVELS[level]
    return Entity(
        name=f"Dummy-AC{data['enemy_ac']}",
        hp=10**9,
        base_stats={
            "ac": data["enemy_ac"],
            "dex_save": data["enemy_dex_save"],
        },
    )


# ---------------------------------------------------------------------------
# Daily-plan policy
# ---------------------------------------------------------------------------

class StarfireScionPolicy:
    """Starfire Scion daily plan (L1, L4, L5).

    Per-turn rotation (a single representative blaster loop — the guide's full
    optimal play splits melee vs ranged combats and leans on Flame Blade / Starry
    Form forms we defer; validation is consistency/sanity, not number-matching):

      ACTION:        Guiding Bolt (Star Map free cast, while charges remain; L4+)
                     else a quarterstaff attack.
      BONUS ACTION:  Sacred Flame (Spellfire Spark, while charges remain) — the
                     save-FOR-damage core; else an Archer spell attack (if Starry
                     Form is active this combat); else an unarmed strike.

    Sacred Flame's dice are pulled FROM DATA (interpret_save_spell, by character
    level), so cantrip scaling (1d8 → 2d8 at L5) lives in content, not here.  WHICH
    slot/charge to spend, and the BA priority ladder, are policy (Python).

    decide() stays a pure read (no dice, no mutation, no queue).  Starry Form
    activation — the one per-combat resource decision — happens in on_combat_start,
    where it consumes a Wild Shape charge and sets the form active for the combat.
    """

    def __init__(
        self,
        level: int,
        character: Entity,
        target: Entity,
        rounds_per_combat: int = 4,
    ) -> None:
        if level not in LEVELS:
            raise NotImplementedError(
                f"StarfireScionPolicy does not yet support level {level}."
            )
        self.level = level
        self._character = character
        self._target = target
        self._rounds = rounds_per_combat
        data = LEVELS[level]
        # Per-attack profiles available at this level (the override fields).
        self._profiles: dict[str, dict] = {
            "quarterstaff": data["quarterstaff"],
            "unarmed": data["unarmed"],
        }
        self._has_starry_form: bool = bool(data.get("starry_form"))
        self._has_guiding_bolt: bool = "guiding_bolt" in data
        if self._has_starry_form:
            self._profiles["archer"] = data["archer"]
        if self._has_guiding_bolt:
            self._profiles["guiding_bolt"] = data["guiding_bolt"]
        # Sacred Flame dice + damage TYPE FROM DATA — resolved once for this
        # character level.  The type ("radiant") drives Fueled Spellfire gating.
        _sf = interpret_save_spell(SACRED_FLAME, {"character_level": level})
        self._sacred_flame_dice = _sf.damage_dice
        self._sacred_flame_type = _sf.damage_type
        # Fueled Spellfire (Spellfire Adept, L5+): enabled iff the level carries a
        # Hit-Dice pool (data-driven gate — see LEVELS[5]["resources"]).  1/turn,
        # when a SPELL deals RADIANT damage, expend up to 2 Hit Dice into it.
        self._fueled_spellfire: bool = "hit_dice" in data.get("resources", {})
        # Per-combat state, (re)set by on_combat_start.
        self._starry_form_active: bool = False
        # 1/turn Fueled-Spellfire gate: the (round, turn_index) we last fueled on,
        # so a turn that deals radiant damage twice (Guiding Bolt + Sacred Flame)
        # fuels only once.  Keyed by turn → auto-resets across turns; cleared per
        # combat (round numbers restart at 1) in on_combat_start.
        self._fueled_turn: "tuple[int, int] | None" = None

    # -- per-combat setup -------------------------------------------------

    def on_combat_start(self, combat_index: int, rng: "SeededRNG") -> None:
        """Activate Starry Form (Archer) for this combat if a Wild Shape charge
        remains.  Wild Shape is 2/LR + 1 on a short rest, so across a day the form
        is up in roughly 3 of the 4 combats; when it is down the BA falls back to
        an unarmed strike.  (rng is unused — activation is deterministic given the
        resource pool; the parameter matches the on_combat_start hook signature.)
        """
        self._starry_form_active = False
        # Clear the per-turn Fueled-Spellfire gate (round numbers restart at 1 each
        # combat, so a stale (round, turn) would mis-gate the new combat).
        self._fueled_turn = None
        if (
            self._has_starry_form
            and self._character.resources.available("wild_shape") >= 1
        ):
            self._character.resources.consume("wild_shape")
            self._starry_form_active = True

    # -- decision point ---------------------------------------------------

    def decide(self, snapshot: GameState) -> list[Choice]:
        res = snapshot.resources
        choices: list[Choice] = []

        # ACTION: Guiding Bolt (free Star Map cast) while charges remain, else a
        # quarterstaff attack.  Greedy on the free casts — across statistically
        # identical combats, when they fire does not change mean DPR.
        if res.get("action", 0) >= 1:
            if self._has_guiding_bolt and res.get("guiding_bolt_free", 0) >= 1:
                choices.append(self._attack_choice(
                    "guiding_bolt", "action",
                    resource_cost={"guiding_bolt_free": 1},
                ))
            else:
                choices.append(self._attack_choice("quarterstaff", "action"))

        # BONUS ACTION: Sacred Flame (the save-FOR-damage core) while a Spellfire
        # Spark charge remains; else an Archer attack (Starry Form active); else
        # an unarmed strike.
        if res.get("bonus_action", 0) >= 1:
            if res.get("spellfire_spark", 0) >= 1:
                choices.append(Choice(
                    action_type="save_spell",
                    cost="bonus_action",
                    target=self._target,
                    save_stat="dex_save",
                    dc_stat="spell_save_dc",
                    damage_dice=self._sacred_flame_dice,   # FROM DATA
                    on_save="none",                        # save NEGATES
                    damage_type=self._sacred_flame_type,   # "radiant" (FROM DATA)
                    is_spell=True,                         # a cantrip → fuelable
                    resource_cost={"spellfire_spark": 1},
                ))
            elif self._starry_form_active:
                choices.append(self._attack_choice("archer", "bonus_action"))
            else:
                choices.append(self._attack_choice("unarmed", "bonus_action"))

        return choices

    def _attack_choice(
        self,
        profile: str,
        cost: str,
        resource_cost: "dict[str, int] | None" = None,
    ) -> Choice:
        """Build an attack Choice carrying a per-attack damage override (the
        multi-weapon primitive): its own dice/bonus and the WIS-or-DEX to-hit stat.
        """
        p = self._profiles[profile]
        return Choice(
            action_type="attack",
            cost=cost,
            target=self._target,
            weapon_stat=p["weapon_stat"],
            damage_dice=p["dice"],
            damage_bonus=p["bonus"],
            damage_type=p.get("damage_type"),       # "radiant" for GB/Archer
            is_spell=p.get("is_spell", False),       # only Guiding Bolt is a spell
            resource_cost=resource_cost or {},
        )

    # -- post-damage decision point: Fueled Spellfire (level 5+) ----------

    def on_deal_damage(self, ctx: DealDamageContext) -> "DamageRiderResponse | None":
        """Fueled Spellfire (Spellfire Adept, L5): ×1/turn, when a SPELL we cast
        deals RADIANT damage, expend up to 2 Hit Dice (d8) and add them to that
        damage roll.

        Policy = "greedy on the first qualifying radiant spell each turn, spend up
        to 2 HD while any remain".  The build's whole concept is to burn ALL the
        Hit Dice this way (5 at L5), so there is nothing to husband: the pool is
        the binding constraint (it empties in the first combat or two, exactly as
        the guide describes ~1-3 fueled combats/day).  Because the action (Guiding
        Bolt) resolves before the bonus action (Sacred Flame), the fuel naturally
        lands on Guiding Bolt while charges last — matching the guide's turn-1
        `guiding-bolt_{fueled-spellfire(2)}`.

        Gates (all policy-side; the engine just offers the seam on every DamageEvent
        we deal):
          - off unless Fueled Spellfire is online (Hit-Dice pool present, L5+);
          - SPELL radiant damage only (so Starry-Form Archer — radiant, but a
            feature — and our weapon strikes are excluded);
          - 1/turn (a turn dealing radiant damage twice fuels only the first);
          - a Hit Die must remain.
        """
        if not self._fueled_spellfire:
            return None
        if ctx.damage_type != "radiant" or not ctx.is_spell:
            return None
        turn = (ctx.round_number, ctx.turn_index)
        if self._fueled_turn == turn:                  # already fueled this turn
            return None
        available = ctx.resources.get("hit_dice", 0)
        if available < 1:
            return None
        n = min(2, available)                          # expend up to 2 Hit Dice
        self._fueled_turn = turn                       # commit the 1/turn use
        return DamageRiderResponse(
            extra_damage_dice=[(n, 8)],                # Nd8 added (no CON mod)
            resource_cost={"hit_dice": n},
        )


# ---------------------------------------------------------------------------
# Full day-runner assembly (used by the validation harness / tests)
# ---------------------------------------------------------------------------

def make_day_runner(level: int, rng: "SeededRNG", rounds_per_combat: int = 4):
    """Assemble (DayRunner, character, dummy) for the given level.

    The enemy carries no attack profile at these levels, so it gets no policy and
    never acts; DPR = damage dealt to the dummy = the character's whole output.
    """
    char = make_starfire_scion(level)
    dummy = make_training_dummy(level)
    policy = StarfireScionPolicy(
        level=level, character=char, target=dummy, rounds_per_combat=rounds_per_combat
    )
    runner = DayRunner(
        rng=rng,
        entities=[char, dummy],
        policies={char.id: policy},
        rounds_per_combat=rounds_per_combat,
    )
    return runner, char, dummy
