"""
party.py — the party-construction seam (evaluation_framework.md §3.5.2).

The third of the framework's three "not a property of the build" seams, and the
cheapest of them, because the mechanism it needs already existed:

===================  ==========================  ==========================
seam                 declared by                 built by
===================  ==========================  ==========================
the ENEMY (§3.4)     ``RunConfig.enemy``         ``evaluation/enemy.py``
the SUBJECT (§3.5.1) a build adapter             ``builds/character_stats``
the PARTY (§3.5.2)   ``RunConfig.party_size``    this module
===================  ==========================  ==========================

WHY THE STANDARD HAS A PARTY AT ALL
-----------------------------------
Step 5b set ``char_target_prob`` to 1.0 and argued the standardized basis should be
comparable rather than realistic.  **The comparability argument was right and
focus-fire was the wrong way to get it.**  With no party in the roster the character
absorbs EVERY incoming attack, so every defensive measurement — damage taken,
concentration, control uptime — is taken in a scenario no character is ever in.  5b had
already built ``enemy._ally_roster`` so off-target swings could land on real allies, and
then left the default at 1.0, so it had nothing to split onto.

A DECLARED party size is comparable *and* realistic: two runs with the same party size
are comparable, and the number is in §4 provenance.

WHAT ``party_size`` COUNTS, stated because it is the one arguable edge
----------------------------------------------------------------------
**Characters + allies.**  ``party_size=4`` on a one-character build adds three passive
members; the WHOLE party including the character, per §3.5.2.

**A SUMMON does not occupy a party slot**, and that is a decision rather than an
oversight.  §3.3's roles already separate them: a summon is an entity the build CREATED
and commands, an ally is a friendly it does not.  Counting Silvertail's companion
against the party would mean a build silently fielded a smaller party than the config
declared — the provenance failure §4 exists to refuse — and it would make ``party_size``
mean something different for a summoner than for everyone else, which is the opposite of
why it is declared.  Who the enemy attacks among {character, summon} is the separate,
already-declared ``enemy_options['focus']`` axis.

PASSIVE HP POOLS, with the cost stated rather than hidden
----------------------------------------------------------
Party members absorb their share of incoming attacks and do nothing else (§3.5.2), which
keeps the baseline character's own output the measured quantity rather than a party
total, and keeps §3.3's multi-character party deferred.  The cost: ``dpr_by_role[allies]``
reads a TRUE ZERO and ``attack_roll_rate[allies|hit]`` is UNMEASURED (no attacks, so no
denominator).  More honest than the "unavailable" those cells used to report — the allies
DO exist, they just do not attack — and the registry's three-state machinery already
distinguishes the two.  :func:`describe` says so in provenance.

NO NEW DICE, AND A BOUNDED RE-BASELINE
--------------------------------------
Nothing here rolls (per-feature ritual step 3): ``install`` constructs entities and
rebuilds a frozen ``Roster``.  But adding friendlies the enemy aims at changes what is
drawn INSIDE combat, so the re-baseline is real — and it is bounded, and the bound was
MEASURED before the code existed (§3.5.2): a passive entity that nothing targets is
**bit-identical**, so ``enemy="none"`` runs are provably unchanged and only acting-enemy
rows move.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from ..builds.character_stats import make_party_member

if TYPE_CHECKING:                                    # pragma: no cover
    from ..day_runner import DayRunner
    from .config import RunConfig
    from .roster import Roster


def members_to_add(roster: "Roster", party_size: int) -> int:
    """How many passive members this roster still needs to reach *party_size*.

    Never negative: a build that already fields more friendlies than the declared
    party size keeps them, because deleting an entity a build constructed would make
    the run measure a different build.  :func:`describe` reports the resolved size, so
    the discrepancy is recorded rather than silent.
    """
    present = len(roster.characters) + len(roster.allies)
    return max(0, party_size - present)


def install(runner: "DayRunner", roster: "Roster", config: "RunConfig") -> "Roster":
    """Add the declared party to *runner* and return the Roster that includes it.

    Called from ``runner.simulate``, immediately before ``enemy.install``, and the
    ORDER is load-bearing: the enemy's weighted targeting roster is DERIVED from the
    friendly roster (§3.5.3), so the party has to exist before the enemy is built
    against it.  This is the same argument that moved ``enemy.install`` out of the three
    adapters in s52 — a call that must always happen belongs in the one function every
    run goes through, not in three that each have to remember it.

    Returns a NEW ``Roster`` rather than mutating one: ``Roster`` is frozen, and its
    ``__post_init__`` re-checks that roles are exclusive and ids unique, which is a free
    check that the members really are new entities.
    """
    n = members_to_add(roster, config.party_size)
    if n == 0:
        return roster
    members = [make_party_member(config.level, i + 1) for i in range(n)]
    # Appended to the live list the DayRunner holds, so they join every combat of the
    # day.  They carry no policy, so the scheduler gives them a turn in which they do
    # nothing — which is what makes a member that nothing targets bit-identical.
    runner.entities.extend(members)
    return replace(
        roster,
        allies=[*roster.allies, *members],
        # DECLARED (see Roster.party_stand_ins): which allies are the framework's
        # non-combatant stand-ins, rather than left to be inferred from a count.
        party_stand_ins=[*roster.party_stand_ins, *(m.id for m in members)],
    )


def describe(roster: "Roster", config: "RunConfig") -> dict[str, Any]:
    """The RESOLVED party block for §4 provenance.  A pure read.

    Reports what the run ACTUALLY fielded, not the requested number, and names the
    members' nature — §3.5.2 requires provenance to say they are non-combatant
    stand-ins, because without that ``dpr_by_role[allies] == 0`` reads as a measurement
    of allies who tried.
    """
    return {
        "party_size": config.party_size,
        "party_size_counts": "characters + allies (a summon is not a party slot)",
        "members_added": members_to_add(roster, config.party_size),
        "fielded": {
            "characters": len(roster.characters),
            "allies": len(roster.allies),
            "summons": len(roster.summons),
        },
        "stand_ins": len(roster.party_stand_ins),
        "build_fielded_allies": len(roster.build_fielded_allies),
        "member_kind": (
            "passive HP pool — a peer's AC and six saves, no resources and no policy, "
            "so it absorbs its share of incoming attacks and never acts. "
            "dpr_by_role[allies] is therefore a TRUE ZERO and "
            "attack_roll_rate[allies|*] is UNMEASURED: these are non-combatant "
            "stand-ins, not allies who failed to contribute (§3.5.2)."
        ),
        "member_source": (
            f"builds/character_stats.make_party_member(level={config.level}) — "
            "AC and saves from the §3.5.1 baseline progression, NOT from the "
            "character build's own level row"
        ),
        "targeting": (
            "DERIVED from this roster, not declared: the enemy splits its attacks "
            "across the friendlies, and enemy_options['char_target_prob'] is REFUSED "
            "when the roster has allies, because party size and 'how often is the "
            "character attacked' are one quantity in two places (§3.5.3)."
        ),
    }
