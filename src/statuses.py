"""
statuses.py — StatusSet: tick-expiring status flags on an entity.

Statuses are short-to-medium-lived boolean/valued flags an entity carries:
sapped, vex_advantage, blessed, concentrating, frightened, etc.  Unlike
base_stats (permanent) and the modifier stack (numeric folding), statuses are
discrete on/off conditions that expire at a defined tick.

Expiry model
------------
Each entry carries an optional expiry keyed on (round, turn_index) — NOT the
full (round, turn_index, sequence) tick, because statuses expire at turn
boundaries, not mid-turn.  An entry is expired once the current
(round, turn_index) has reached or passed its expiry:

    (current_round, current_turn_index) >= entry.expiry   →  expired

`expire()` is called by the scheduler for every entity at each TurnStartEvent,
so a status set to expire "at the start of the applier's next turn" is purged
exactly when that turn begins.

Worked example (turn order: character=turn 0, enemy=turn 1)
  - Character applies SAP to enemy on (round R, turn 0).
    Sap expires at the start of the character's next turn → expiry (R+1, 0).
  - Enemy's turn (R, 1):  (R,1) >= (R+1,0)? No → sap still active, enemy
    attacks at disadvantage. Correct.
  - Character's next turn (R+1, 0):  (R+1,0) >= (R+1,0)? Yes → sap purged.

Consumption model
------------------
Some statuses are also consumed on use *before* their expiry — e.g. vex and
sap both apply to the holder's "next attack roll".  The attack resolver calls
`consume(name)` when it uses such a status; the expiry tick is only the backstop
for the case where the holder never makes the qualifying roll.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# StatusEntry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StatusSpec:
    """A status to GRANT, carried as a cast_effect payload (substrate #3).

    The declarative twin of `Modifier` (the modifier payload): a `cast_effect`
    Choice lists the statuses it installs, and the scheduler applies each onto
    the bearer's StatusSet under the cast's `effect_source`.  See
    design/buff_primitive.md substrate (3) — advantage / condition / immunity
    grants.

    Fields mirror StatusSet.apply: `name` (the status key the engine reads —
    e.g. "attack_advantage_against" on a Faerie-Fire'd target, or
    "spell_attack_advantage" on an Innate-Sorcery caster), `value` (payload —
    True for a plain flag, or e.g. a target id), and `expiry` (None for a
    combat-clock status that the combat-boundary StatusSet.clear() sweeps, since
    a 1-minute buff spans the whole encounter and never tick-expires mid-combat).
    """
    name: str
    value: Any = True
    expiry: tuple[int, int] | None = None


@dataclass
class StatusEntry:
    """One active status.

    Fields
    ------
    value:
        Payload.  True for a plain flag; can hold data, e.g. vex_advantage
        stores the target entity id the advantage applies against.
    expiry:
        (round, turn_index) at/after which the status is purged, or None for
        a permanent status (cleared only by explicit remove/consume).
    """
    value: Any = True
    expiry: tuple[int, int] | None = None


# ---------------------------------------------------------------------------
# StatusSet
# ---------------------------------------------------------------------------

class StatusSet:
    """The set of statuses currently on one entity.

    A thin keyed store with tick-based expiry.  Presence in the set means the
    status is active (expired entries are swept by expire() at turn starts).
    """

    def __init__(self) -> None:
        self._entries: dict[str, StatusEntry] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def apply(
        self,
        name: str,
        value: Any = True,
        expiry: tuple[int, int] | None = None,
    ) -> None:
        """Add or overwrite a status.

        Re-applying an existing status replaces it (refreshing value/expiry),
        which matches "the most recent application wins" for stacking flags.
        """
        self._entries[name] = StatusEntry(value=value, expiry=expiry)
        log.debug("apply status %r value=%r expiry=%s", name, value, expiry)

    def remove(self, name: str) -> None:
        """Remove a status if present (no error if absent)."""
        self._entries.pop(name, None)

    def clear(self) -> None:
        """Remove all statuses.

        Used at combat boundaries: tick-expiring statuses (vex, sap) are keyed
        on (round, turn_index), and each combat restarts the round counter at 1,
        so a status carried over from a previous fight would never be swept and
        would leak (e.g. a free vex advantage on the next combat's first attack).
        Encounters are minutes/hours apart, so clearing between them is also
        semantically correct.
        """
        self._entries.clear()

    def consume(self, name: str) -> Any:
        """Remove a status and return its value (None if it wasn't present).

        Used for one-shot-on-use statuses like vex/sap that are spent by the
        holder's next qualifying roll.
        """
        entry = self._entries.pop(name, None)
        if entry is None:
            return None
        log.debug("consume status %r → value=%r", name, entry.value)
        return entry.value

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def has(self, name: str) -> bool:
        return name in self._entries

    def get(self, name: str, default: Any = None) -> Any:
        entry = self._entries.get(name)
        return entry.value if entry is not None else default

    def active_names(self) -> list[str]:
        return list(self._entries.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------------
    # Expiry sweep
    # ------------------------------------------------------------------

    def expire(self, current_round: int, current_turn_index: int) -> list[str]:
        """Purge entries whose expiry has been reached.  Returns purged names.

        An entry with expiry E is purged when (current_round, current_turn_index)
        >= E.  Permanent entries (expiry=None) are never purged here.
        """
        now = (current_round, current_turn_index)
        purged: list[str] = []
        for name, entry in list(self._entries.items()):
            if entry.expiry is not None and now >= entry.expiry:
                del self._entries[name]
                purged.append(name)
        if purged:
            log.debug("expired statuses %s at %s", purged, now)
        return purged

    # ------------------------------------------------------------------
    # Repr
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        parts = ", ".join(
            f"{n}={e.value!r}@{e.expiry}" for n, e in self._entries.items()
        )
        return f"StatusSet({parts})"
