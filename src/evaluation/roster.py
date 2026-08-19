"""
roster.py — role-tagged entity roster (evaluation_framework.md §3.3).

The single coupling that makes ``src/validation.py`` un-generalizable is that it
reads entities by TUPLE POSITION: ``runner, char, dummy = make_day_runner(...)``
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
    Friendly entities the build does not command (Starfire Scion's passive party
    member under ``with_party``).
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

    def summary(self) -> dict[str, list[str]]:
        """Role → entity names.  For provenance and human-readable output."""
        return {role: [e.name for e in getattr(self, role)] for role in ROLES}
