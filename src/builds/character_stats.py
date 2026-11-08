"""
character_stats.py — the DEFINITIVE per-level progression for the BASELINE CHARACTER
(evaluation_framework.md §3.5.1), and the one constructor for the framework's own
declared SUBJECT.

This is the player-side mirror of ``enemy_stats``, and it exists for the same reason
one layer over: §3.4 removed the enemy from the build, and §3.5 removes the
*subject*.  The framework has been validated against three builds that were written
as scaffolding for engine development, and their data is sparse exactly where the
framework needs it complete — ``ac`` is absent in 20 of 27 (build, level) pairs, and
``Entity.stat()`` returns 0 for a missing key *by design*, so those characters fight
at AC 0.  **A framework defect and a content gap are indistinguishable when the only
subjects are partial builds.**  So the framework declares a subject of its own.

WHY A PROGRESSION RATHER THAN HAND-AUTHORED LEVELS
--------------------------------------------------
Mirroring ``enemy_stats`` and for the same three reasons: it is regenerable, it is
comparable across levels BY CONSTRUCTION, and no session has to invent numbers.  The
difference from ``enemy_stats`` is that its table was FITTED from a chart and therefore
lives in a CSV, while every column here is closed-form, so the rules ARE the
provenance and the table is built at import by :func:`_build_table`.  The approved
§3.5.1 numbers are pinned as an ASSERTION (``tests/test_character_stats.py``) rather
than as a comment — a tallied table in prose has nothing behind it.

THE DECLARED COLUMNS, AND THE RULE BEHIND EACH (§3.5.1, approved by the user, s53)
----------------------------------------------------------------------------------
``pb``
    Proficiency bonus by level: +2/+3/+4/+5/+6 at 1/5/9/13/17.
``primary``
    ONE primary-ability MODIFIER driving both weapon attacks and spell DC: 16 (+3),
    18 (+4) at the level-4 ASI, 20 (+5) at the level-8 ASI.  **No single real class
    works this way** — a paladin's spell DC is CHA while its attacks are STR — and
    that is a deliberate simplification, recorded rather than buried: the progression
    gets ONE ability knob, so a retune moves one track instead of two that have to be
    kept in step.  §3.5's whole argument is that the subject exists to test the
    framework, not to be a build.
``ac``
    A 16/17/18/19 track (16 at L1-4, 17 at L5-10, 18 at L11-16, 19 at L17-20).
    *The most arguable single number in the table is AC 16 at L1*: chain mail plus a
    shield is 18 from level 1 with no DEX investment, so a heavier track would drop
    the incoming hit rate by about ten points everywhere.  The mid-range track was
    chosen deliberately (§3.5.1) so the alternative is a decision rather than a
    rediscovery.
``attack``
    ``pb + primary``.
``spell_dc``
    ``8 + pb + primary``.
``attacks``
    Attacks per action: 1, then 2 from level 5 (Extra Attack).
``hp``
    A d8 hit die with CON +2: ``10`` at L1, then ``+6.5`` per level
    (``round()`` is round-half-even, which is what reproduces the approved table's
    16 / 30 / 42 / 56 … exactly).
``damage_dice``
    ``1d8`` — a d8 versatile weapon (used one-handed, so the d8 face), plus
    ``primary`` as the flat damage bonus.
``saves``
    The six saving throws, with **two proficient** (§3.5.1).  The ability array is
    DECLARED here because the approved table printed only the CON save, which is the
    one concentration reads:

      =========  =====  ============  ===========================
      ability    score  modifier      saving throw
      =========  =====  ============  ===========================
      primary    16/18/20  +3/+4/+5   ``pb + primary``  (proficient)
      CON        14     +2            ``pb + 2``        (proficient)
      DEX        14     +2            +2
      WIS        12     +1            +1
      INT        10     +0            0
      CHA        10     +0            0
      =========  =====  ============  ===========================

    Primary + CON is the fighter's own save-proficiency pair, so the one authored
    choice here is RAW-plausible rather than synthetic.  §3.5.1 flags the
    consequence: ``CON save`` reaches +7 at L13, better than either real build (War
    Angel +4, Starfire +2), so baseline concentration figures look markedly healthier
    than the ones measured on the existing builds — deliberate, because a baseline
    should be REPRESENTATIVE rather than weak.
``spell_slots``
    The half-caster (paladin/ranger) table, since this is a d8-HP martial with Extra
    Attack.  **ONE deliberate deviation, stated because it is the only place the
    table is not the published one:** a half-caster has no slots at level 1, but the
    §3.5.1 capability set makes a concentration spell, a save-forcing spell and
    healing CORE *at every level*, and the approved table prints a ``conc DC`` /
    ``conc pass`` pair at L1.  A core capability that is off at L1 makes L1 a
    different measurement from L2-20, which is the comparability defect the whole
    section exists to remove.  So L1 is given the half-caster's L2 row.

THE THREE PROPERTIES A RETUNE MUST PRESERVE (§3.5.1) — not the individual numbers
---------------------------------------------------------------------------------
1. **Hit rates stay inside a 60-70% band in BOTH directions across all 20 levels** —
   the signal that this track and ``enemy_stats`` are scaled against each other
   rather than drifting apart.  *The cheapest available check on the whole
   progression*, and asserted as such.
2. **``conc pass`` falls 75% → 35%** as enemy damage grows, so concentration becomes
   a genuine cost at high level instead of a formality.
3. **``CON save`` reaches +7 at L13**, better than either real build — see ``saves``
   above.

NO NEW DICE
-----------
Nothing in this module rolls (per-feature ritual step 3).  Every function is table
lookup or ``Entity`` construction, so importing it and constructing a subject or a
party member shifts no stream and breaks no ``GOLDEN_DPR`` point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# The `pb` column's rule, shared with every character-side table rather than restated
# here (PROGRESS item 5b, s61).  The SUBJECT is not the owner of the universal track —
# that is the point of progression.py existing instead of the builds importing this
# module.
from .progression import proficiency_bonus

if TYPE_CHECKING:                                    # pragma: no cover
    from ..entity import Entity


#: The engine's saving-throw stat vocabulary, in canonical order.
SAVE_KEYS = ("str_save", "dex_save", "con_save", "int_save", "wis_save", "cha_save")

#: The ABILITY the ``primary`` track stands for.  STR, so that "primary + CON
#: proficient" is the fighter's own pair and the one authored choice in the save
#: array is RAW-plausible.  Named rather than implied because ``primary`` also
#: drives the spell DC, which no real STR class does (see the module docstring).
PRIMARY_SAVE_KEY = "str_save"

#: The non-primary, non-CON abilities' MODIFIERS (DEX 14 / WIS 12 / INT 10 / CHA 10),
#: unproficient, flat across all 20 levels: the baseline invests its ASIs in the
#: primary track, which is what the 16 → 18 → 20 progression says.
_SECONDARY_SAVE_MODS = {"dex_save": 2, "wis_save": 1, "int_save": 0, "cha_save": 0}

#: CON score 14 → +2, with save proficiency, so ``con_save == pb + CON_MOD``.
CON_MOD = 2

#: The weapon: a d8 versatile weapon wielded one-handed (so the d8 face, not the d10).
WEAPON_DICE = (1, 8)

#: Hit-die size and the per-level HP step: a d8 (average 4.5) plus CON +2.
_HIT_DIE = 8
_HP_AT_L1 = _HIT_DIE + CON_MOD                 # max at first level, the 2024 rule
_HP_PER_LEVEL = (_HIT_DIE + 1) / 2 + CON_MOD   # 4.5 + 2

#: The half-caster slot table, keyed by the level whose row it is, as published
#: (paladin/ranger).  Level 1 is ABSENT here on purpose: see the ``spell_slots``
#: paragraph in the module docstring for the one deliberate deviation, applied in
#: :func:`_build_table` rather than hidden in this literal.
_HALF_CASTER_SLOTS: dict[int, tuple[int, ...]] = {
    2: (2,),
    3: (3,),
    4: (3,),
    5: (4, 2),
    6: (4, 2),
    7: (4, 3),
    8: (4, 3),
    9: (4, 3, 2),
    10: (4, 3, 2),
    11: (4, 3, 3),
    12: (4, 3, 3),
    13: (4, 3, 3, 1),
    14: (4, 3, 3, 1),
    15: (4, 3, 3, 2),
    16: (4, 3, 3, 2),
    17: (4, 3, 3, 3, 1),
    18: (4, 3, 3, 3, 1),
    19: (4, 3, 3, 3, 2),
    20: (4, 3, 3, 3, 2),
}

LEVELS = tuple(range(1, 21))


# ---------------------------------------------------------------------------
# The rules behind the declared columns
# ---------------------------------------------------------------------------

def _primary_mod(level: int) -> int:
    """The primary-ability MODIFIER: 16 (+3) → 18 (+4) at the L4 ASI → 20 (+5) at L8."""
    if level >= 8:
        return 5
    if level >= 4:
        return 4
    return 3


def _ac(level: int) -> int:
    """The 16/17/18/19 AC track."""
    if level >= 17:
        return 19
    if level >= 11:
        return 18
    if level >= 5:
        return 17
    return 16


def _hp(level: int) -> int:
    """d8 + CON 2: 10 at L1, +6.5 per level after.

    ``round()`` is round-half-even, which is exactly what reproduces the approved
    table's 16 / 30 / 42 / 56 / 68 / 82 / 94 / 108 / 120 / 134 — the ten levels where
    the running total lands on a half.  Pinned as an assertion, not trusted here.
    """
    return int(round(_HP_AT_L1 + _HP_PER_LEVEL * (level - 1)))


def _saves(level: int) -> dict[str, int]:
    """The six saving throws, two proficient (primary + CON)."""
    pb = proficiency_bonus(level)
    saves = dict(_SECONDARY_SAVE_MODS)
    saves[PRIMARY_SAVE_KEY] = pb + _primary_mod(level)
    saves["con_save"] = pb + CON_MOD
    return {key: saves[key] for key in SAVE_KEYS}


def _spell_slots(level: int) -> tuple[int, ...]:
    """Slots per spell level, index 0 = 1st level.

    Level 1 borrows the half-caster's level-2 row — the module docstring's one
    stated deviation, so the §3.5.1 core capability set is on at EVERY level.
    """
    return _HALF_CASTER_SLOTS[max(level, 2)]


def _build_table() -> dict[int, dict]:
    """The full per-level progression.  Derived, not transcribed."""
    table: dict[int, dict] = {}
    for level in LEVELS:
        pb = proficiency_bonus(level)
        primary = _primary_mod(level)
        table[level] = {
            "level": level,
            "pb": pb,
            "primary": primary,
            "ac": _ac(level),
            "attack_bonus": pb + primary,
            "spell_save_dc": 8 + pb + primary,
            "attacks": 1 if level < 5 else 2,
            "hp": _hp(level),
            "damage_dice": WEAPON_DICE,
            "damage_bonus": primary,
            "saves": _saves(level),
            "spell_slots": _spell_slots(level),
        }
    return table


_LEVEL_ROWS: dict[int, dict] = _build_table()


def _row(level: int) -> dict:
    try:
        return _LEVEL_ROWS[level]
    except KeyError:
        raise KeyError(
            f"No baseline-character row for level {level}; have {LEVELS[0]}-{LEVELS[-1]}."
        ) from None


# ---------------------------------------------------------------------------
# Accessors (the ``baseline_*`` naming mirrors enemy_stats)
# ---------------------------------------------------------------------------

def baseline_pb(level: int) -> int:
    """Proficiency bonus at *level*."""
    return _row(level)["pb"]


def baseline_primary_mod(level: int) -> int:
    """The primary-ability modifier at *level* (+3 / +4 / +5)."""
    return _row(level)["primary"]


def baseline_ac(level: int) -> int:
    """The baseline character's AC at *level*."""
    return _row(level)["ac"]


def baseline_attack_bonus(level: int) -> int:
    """The baseline character's weapon attack bonus at *level*."""
    return _row(level)["attack_bonus"]


def baseline_spell_dc(level: int) -> int:
    """The DC of a save the baseline character forces at *level*."""
    return _row(level)["spell_save_dc"]


def baseline_attacks(level: int) -> int:
    """Attacks per action at *level* (Extra Attack at 5)."""
    return _row(level)["attacks"]


def baseline_hp(level: int) -> int:
    """The baseline character's hit points at *level*."""
    return _row(level)["hp"]


def baseline_save(level: int, stat: str) -> int:
    """One of the six saving-throw bonuses at *level*."""
    saves = _row(level)["saves"]
    try:
        return saves[stat]
    except KeyError:
        raise KeyError(f"Unknown save {stat!r}; expected one of {SAVE_KEYS}.") from None


def baseline_saves(level: int) -> dict[str, int]:
    """All six saving-throw bonuses at *level* (a copy)."""
    return dict(_row(level)["saves"])


def baseline_damage_dice(level: int) -> tuple[int, int, int]:
    """``(count, sides, flat)`` for one weapon hit at *level*."""
    row = _row(level)
    n, sides = row["damage_dice"]
    return n, sides, row["damage_bonus"]


def baseline_spell_slots(level: int) -> tuple[int, ...]:
    """Slots per spell level at *level*; index 0 is 1st-level slots."""
    return _row(level)["spell_slots"]


def character_base_stats(level: int) -> dict[str, int | tuple]:
    """An ``Entity.base_stats`` dict for the baseline character at *level*.

    Deliberately COMPLETE rather than minimal, for the reason §3.5 exists: a
    missing ``base_stats`` key reads as a silent 0 (``Entity.stat()``'s documented
    behaviour), and that is how 20 of 27 (build, level) pairs came to fight at AC 0
    and how War Angel's old dummy came to resolve saves against +0.  Every key the
    verbs can read on the character's side is present at every level.
    """
    row = _row(level)
    n, sides = row["damage_dice"]
    stats: dict[str, int | tuple] = {
        "ac": row["ac"],
        "attack_bonus": row["attack_bonus"],
        # One primary drives both, so the weapon and spell attack bonuses coincide.
        "spell_attack_bonus": row["attack_bonus"],
        "spell_save_dc": row["spell_save_dc"],
        "damage_dice": (n, sides),
        "damage_bonus": row["damage_bonus"],
        **row["saves"],
    }
    return stats


def level_table() -> dict[int, dict]:
    """The full per-level table (a deep-ish copy), for inspection and for the
    assertion that pins §3.5.1's approved numbers."""
    return {
        lvl: {**row, "saves": dict(row["saves"])}
        for lvl, row in _LEVEL_ROWS.items()
    }


# ---------------------------------------------------------------------------
# The constructors
# ---------------------------------------------------------------------------

def _resource_pool(level: int) -> "object":
    """The baseline character's spell-slot ledger — the §3.5.1 "slot budget" core
    capability, and what the §13 resource channel reads.

    Long-rest restore only (the 2024 rule for a half-caster's slots); nothing here
    restores on a short rest, so the daily budget is the measured quantity.
    """
    from ..resources import ResourceEntry, ResourcePool

    entries = {
        f"spell_slot_{i + 1}": ResourceEntry(current=n, maximum=n, sr_restore=0)
        for i, n in enumerate(baseline_spell_slots(level))
    }
    return ResourcePool(entries)


def make_baseline_character(level: int, name: "str | None" = None) -> "Entity":
    """THE baseline-character ``Entity`` constructor (§3.5.1).

    The player-side counterpart of ``enemy_stats.make_baseline_enemy``, and the same
    rule applies: ONE source for the subject's stat block.  A fixture that needs a
    complete character asks for one here rather than reaching into a build's sparse
    ``LEVELS`` row.

    Carries a Hit Dice pool, because §3.5.1 makes healing in BOTH contexts core and
    ``healing_by_source`` needs both to have a producer.  Nothing here rolls: Hit Dice
    applied OUTSIDE combat are MEAN-FIELD and draw nothing (``design/healing.md`` §7a,
    CLAUDE.md), which is what keeps every ``GOLDEN_DPR`` point still.
    """
    from ..entity import Entity
    from ..healing import HitDiceSpec, attach_hit_dice

    return attach_hit_dice(
        Entity(
            name=name or f"Baseline-L{level}",
            hp=baseline_hp(level),
            base_stats=character_base_stats(level),
            resources=_resource_pool(level),
        ),
        HitDiceSpec(dice=[(level, _HIT_DIE)], con_mod=CON_MOD, rule="character"),
    )


#: A party member's HP.  Effectively infinite, for the same reason the enemy dummy's
#: is: in the threshold model a friendly HP pool exists to ABSORB a share of the
#: enemy's swings, and a pool that runs out would turn "how often is the character
#: attacked" into a function of how long the day has been running (memory
#: ``standardized-dpr-baseline-not-realism``).
PARTY_MEMBER_HP = 10 ** 9


def make_party_member(level: int, index: int = 1) -> "Entity":
    """THE party-member ``Entity`` constructor (§3.5.2).

    A **passive HP pool**: a peer's AC and the six saves so that anything aimed at it
    resolves against real numbers, no resources, and NO POLICY, so it never acts.  Its
    whole job is to absorb its share of the enemy's attacks, which is what takes every
    defensive measurement out of the focus-fire scenario no character is ever in.

    One source, here, and that is the point of the function existing at all.  Before
    §3.5.2 the only party member in the project was
    ``starfire_scion.make_party_member``, which reads ``LEVELS[level]['char_ac']`` —
    *that build's* data.  A framework that called it would have taken the standardized
    party's AC from one particular character's level row, which is §3.4's coupling with
    the labels swapped.

    The cost is STATED rather than hidden (§3.5.2): a passive member means
    ``dpr_by_role[allies]`` reads a TRUE ZERO and ``attack_roll_rate[allies|hit]`` is
    UNMEASURED (no attacks, so no denominator), so provenance must say the party
    members are non-combatant stand-ins.  §3.3's multi-character party stays deferred.
    """
    from ..entity import Entity

    return Entity(
        name=f"PartyMember-{index}-L{level}",
        hp=PARTY_MEMBER_HP,
        base_stats={"ac": baseline_ac(level), **baseline_saves(level)},
    )
