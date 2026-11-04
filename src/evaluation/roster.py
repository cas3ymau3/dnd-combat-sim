"""
roster.py — role-tagged entity roster (evaluation_framework.md §3.3).

The single coupling that made ``src/validation.py`` un-generalizable (deleted s52 —
see ``evaluation/__init__``) was that it read entities by TUPLE POSITION:
``runner, char, dummy = make_day_runner(...)``
works for the War Angel and breaks the moment a build returns a summon
(``silvertail.make_silvertail_runner`` returns four things, with the beast in the
middle).  A ``Roster`` replaces position with an explicit ROLE tag, so every
downstream consumer — metrics, reports, the artifact schema, a website — asks
"which entities are characters?" rather than "which index was the character?".

Roles
-----
characters
    The build's OWN actors.  **A LIST from day one**, even though every build
    today has exactly one (§3.3): §7's AoE-share and ranged-kiting toggles are
    blocked on multi-character party support, and retrofitting plurality after
    an artifact schema and a site assume a scalar is not free.
summons
    Entities the build CREATED (``create_entity`` / substrate #7) and commands —
    Silvertail's primal companion.
allies
    Friendly entities the build does not command.  Since s54 these are the
    framework's declared PARTY (``RunConfig.party_size``, built by
    ``evaluation/party.py``) — passive HP pools that absorb their share of the
    enemy's attacks and never act, so ``dpr_by_role[allies]`` is a TRUE ZERO
    (§3.5.2).  A build may still field its own; the role does not care which.
enemies
    The opposition.

The headline/total distinction (§3.3, generalizing the session-17 decision) is
structural and **never collapsed**: :meth:`headline_source_ids` is the characters
alone, and :meth:`party_source_ids` — characters + summons + allies — is reported
BESIDE it under a different name.  That is what stops a build's headline DPR from
silently changing meaning when the build gains a summon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:                                    # pragma: no cover
    from ..entity import Entity


#: The closed role vocabulary, in report order.  Extending it is a deliberate
#: act (same philosophy as the closed verb set and §13's channel vocabulary),
#: not something a build does casually from its adapter.
ROLES = ("characters", "summons", "allies", "enemies")


@dataclass(frozen=True)
class Roster:
    """Entities of one simulated run, tagged by role."""

    characters: list["Entity"] = field(default_factory=list)
    summons: list["Entity"] = field(default_factory=list)
    allies: list["Entity"] = field(default_factory=list)
    enemies: list["Entity"] = field(default_factory=list)
    #: Ids of the allies the FRAMEWORK added as declared-party stand-ins
    #: (``evaluation/party.install``), as opposed to friendlies a build fielded itself.
    #:
    #: **DECLARED, not inferred** (the s49 rule).  The two facts can come apart: a
    #: build may field its own ally, and a run may declare a party, and counting
    #: ``len(allies)`` against ``party_size`` would conflate them the moment both
    #: happen.  It is a list of IDS rather than entities so that role exclusivity and
    #: id uniqueness keep checking exactly the four role lists.
    #:
    #: Read by availability predicates that need to know whether there is anyone in the
    #: roster a build could MEANINGFULLY interact with: a passive non-combatant
    #: stand-in is present but is not an ally who chose not to act
    #: (``_requires_a_healable_other``), which is the distinction §3.5.2 says
    #: provenance has to carry.
    party_stand_ins: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.characters:
            raise ValueError("Roster needs at least one character entity.")
        seen: dict[int, str] = {}
        for role in ROLES:
            for entity in getattr(self, role):
                if entity.id in seen:
                    raise ValueError(
                        f"Entity {entity.name!r} (id {entity.id}) is tagged both "
                        f"{seen[entity.id]!r} and {role!r} — roles are exclusive."
                    )
                seen[entity.id] = role

    # -- role queries ---------------------------------------------------

    def entities(self, *roles: str) -> list["Entity"]:
        """All entities in the given roles (default: every role, in ROLES order)."""
        wanted = roles or ROLES
        for role in wanted:
            if role not in ROLES:
                raise KeyError(f"Unknown roster role {role!r}; expected one of {ROLES}.")
        return [e for role in wanted for e in getattr(self, role)]

    def ids(self, *roles: str) -> list[int]:
        """Entity ids in the given roles (default: every role)."""
        return [e.id for e in self.entities(*roles)]

    def role_of(self, entity_id: int) -> str:
        """The role tag of an entity id."""
        for role in ROLES:
            if any(e.id == entity_id for e in getattr(self, role)):
                return role
        raise KeyError(f"Entity id {entity_id} is not in this roster.")

    @property
    def character(self) -> "Entity":
        """The single character — for the one-character builds that exist today.

        Raises if a build ever has more than one, rather than silently picking
        the first: a multi-character build must be read through
        :attr:`characters`, not through an accessor that hides the plurality.
        """
        if len(self.characters) != 1:
            raise ValueError(
                f"Roster has {len(self.characters)} characters; use .characters "
                "(this build is multi-character)."
            )
        return self.characters[0]

    # -- damage-column source sets (§3.3) -------------------------------

    @property
    def headline_source_ids(self) -> list[int]:
        """Sources of the HEADLINE column — the build's own actors, nothing else."""
        return self.ids("characters")

    @property
    def party_source_ids(self) -> list[int]:
        """Sources of the roster/party TOTAL — reported beside the headline, never
        merged into it."""
        return self.ids("characters", "summons", "allies")

    @property
    def build_fielded_allies(self) -> list["Entity"]:
        """Allies the BUILD constructed — the roster's allies minus the framework's
        declared-party stand-ins."""
        return [e for e in self.allies if e.id not in set(self.party_stand_ins)]

    def summary(self) -> dict[str, list[str]]:
        """Role → entity names.  For provenance and human-readable output."""
        return {role: [e.name for e in getattr(self, role)] for role in ROLES}
