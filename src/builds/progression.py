"""
progression.py — the UNIVERSAL per-level character-progression rules.

The rules that belong to every character-side table and to no particular build.  One
function lives here today; it is a module rather than a line in ``builds/__init__.py``
so that the next shared track (spell slots by caster level, ASI timing) has an obvious
home, and so that the seam argument below has somewhere to be written down.

WHY THIS MODULE EXISTS: FOUR COPIES, THREE OF THEM ONE FACT (PROGRESS item 5b, s62)
-----------------------------------------------------------------------------------
``2 + (level - 1) // 4`` had accumulated FOUR copies — ``war_angel.proficiency_bonus``,
``silvertail._char_pb``, ``character_stats._pb`` and ``enemy_stats._pb`` — and s59
recorded that four is enough to lift it somewhere shared.  The §3.4 seam check applied
to an arithmetic expression asks a question the copy count does not: *are these the
same quantity, or different quantities that agree?*

**Three of the four are one fact and are now imported from here:** a CHARACTER's
proficiency bonus at a given character LEVEL (PHB "Proficiency Bonus" column).  That
is one rule in the 2024 ruleset, and the three call sites want exactly it —
``war_angel`` for its own attack/save bonuses, ``character_stats`` for the baseline
subject's ``pb`` column, and ``silvertail`` for the MASTER's PB, which the 2024 Primal
Companion rule gives to the beast's saves.

**The fourth is a different fact and deliberately stays in ``enemy_stats``.**
``enemy_stats._pb`` is the DMG "Monster Statistics by Challenge Rating" Proficiency
Bonus column, read at a CR and not at a character level, and used only inside
:func:`enemy_stats.regenerate` to back the per-swing die count out of a target average.
The project sets CR == character level over 1–20, and over that range the two tables
agree at every single point — which is precisely the shape the dormancy question exists
to catch.  They are two tables in the rules, not one:

* they are indexed by different things (character level vs challenge rating), and the
  monster table extends to CR 0 and the fractional CRs, where "character level" has no
  value at all;
* they can be retuned independently — the enemy table is FITTED (``regenerate`` fits
  polynomials to a chart and the committed CSV is the artifact), while the character
  track is closed-form rules text;
* nothing in the ruleset makes the agreement load-bearing.  It is the DMG having been
  built to mirror the PC track, which is a design coincidence of the ruleset, not a
  derivation.

So importing the enemy's PB from here would be the §3.4 coupling one layer down: the
enemy's to-hit would become a property of the character progression.  Collapsing the
three real duplicates and leaving the fourth alone is the answer the seam check gives,
and "they agree on 1–20" is written here so the next session does not have to
rediscover that the agreement is a coincidence rather than evidence.

(For the same reason, nothing here imports from ``character_stats``: a real build
taking its PB from the framework's own stand-in SUBJECT would be a worse coupling than
a repeated rule.  That was the argument the four copies were defended with, and it
holds against every home except a neutral one — which is this module.)
"""

from __future__ import annotations


def proficiency_bonus(level: int) -> int:
    """A character's proficiency bonus at character *level*: +2/+3/+4/+5/+6 at
    1/5/9/13/17 (the universal 2024 track).

    Floor division gives the whole track in one expression; ``level`` is a CHARACTER
    level and not a challenge rating (see this module's docstring for why the enemy
    table's numerically-identical column is a different fact).
    """
    return 2 + (level - 1) // 4
